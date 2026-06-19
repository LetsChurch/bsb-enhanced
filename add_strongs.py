#!/usr/bin/env python3
"""
Insert Strong's numbers inline into the BSB USX files.

Source of truth for word -> Strong's mapping is bsb_tables.tsv, whose
" BSB version " column concatenates to the exact BSB English text found in the
USX files. Each table row is one translation token carrying a Strong's number
(Hebrew col "Str Heb" / Greek col "Str Grk").

For every verse we align the USX scripture words to the table's token words and
wrap each token's word(s) in a USX wordlist char element:

    <char style="w" strong="H07225">In the beginning</char>

Strong's identifiers follow the USX spec example format: H/G prefix + the number
zero-padded to 5 digits (H07225, G05485). Hebrew & Aramaic -> H, Greek -> G.

The USX files are edited in place, touching only scripture text: existing
structure, footnotes, headings, whitespace and formatting are preserved
byte-for-byte except for the inserted <char> tags.
"""
import csv, re, sys, glob, os
from collections import defaultdict
import difflib

# NT book codes -- for the MSB these come from the Majority Text table instead
# of the BSB table. (The MSB is the BSB using the Majority Text; only the NT
# differs.)
NT_CODES = {
    'MAT', 'MRK', 'LUK', 'JHN', 'ACT', 'ROM', '1CO', '2CO', 'GAL', 'EPH',
    'PHP', 'COL', '1TH', '2TH', '1TI', '2TI', 'TIT', 'PHM', 'HEB', 'JAS',
    '1PE', '2PE', '1JN', '2JN', '3JN', 'JUD', 'REV',
}

# Each target: a USX glob plus the table(s) that cover it. When more than one
# table is given, later tables override earlier ones per verse (used so the MSB
# NT comes from the Majority Text table while its OT reuses the BSB table).
TARGETS = [
    ('./bsb/USX_1/*.usx', ['bsb_tables.tsv']),
    ('./msb/USX_1/*.usx', ['bsb_tables.tsv', 'msb_nt_tables.tsv']),
]

# Column indices (identical layout in bsb_tables.tsv and msb_nt_tables.tsv)
C_LANG = 4
C_STR_HEB = 10
C_STR_GRK = 11
C_VERSEID = 12
C_TEXT = 18  # " BSB version " / " MSB version " -- the rendered English token

# A scripture "word": letters/digits with internal apostrophes or hyphens.
WORD = re.compile(r"[A-Za-z0-9]+(?:[’'\-][A-Za-z0-9]+)*")
TAG = re.compile(r'<[^>]*>|[^<]+')


def strong_id(heb, grk):
    # A handful of MSB NT rows carry a transliteration instead of a number in
    # the Strong's column; skip those rather than emit a malformed attribute.
    if grk.isdigit():
        return 'G' + grk.zfill(5)
    if heb.isdigit():
        return 'H' + heb.zfill(5)
    return None


def clean_phrase(s):
    """Reduce a raw BSB-version cell to the displayable English it contributes."""
    s = s.strip()
    s = re.sub(r'<[^>]*>', '', s)            # stray HTML fragments leaked into the table
    s = s.replace('[', '').replace(']', '')  # implied-word brackets -> keep inner text
    s = s.replace('{', '').replace('}', '')  # variant markers
    return s


def phrase_words(s):
    return [w for w in WORD.findall(clean_phrase(s)) if w != 'vvv']


def book_name_map(usx_glob):
    """USX book code -> the full book name used in the TSV VerseId (from <para style=h>)."""
    name2code = {}
    for f in glob.glob(usx_glob):
        t = open(f, encoding='utf-8').read()
        code = re.search(r'book code="([A-Z0-9]+)"', t).group(1)
        h = re.search(r'<para style="h">([^<]*)</para>', t).group(1)
        name2code[h] = code
    return name2code


def load_table(path, verses=None):
    """(bookname, chapter, verse) -> ordered list of word-units (word, strong, token_id).

    Rows from `path` are merged into `verses` (a fresh dict if None); any verse
    present in `path` fully replaces an earlier one, so later tables override.
    """
    if verses is None:
        verses = {}
    fresh = set()  # verses (re)started by this table -> they replace prior content
    cur = None
    units = None
    token_id = 0
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.reader(f, delimiter='\t')
        next(r)
        for row in r:
            vid = row[C_VERSEID].strip()
            if vid:
                m = re.match(r'^(.*?)\s+(\d+):(\d+)$', vid)
                if m:
                    cur = (m.group(1), int(m.group(2)), int(m.group(3)))
                    if cur not in fresh:
                        verses[cur] = []
                        fresh.add(cur)
                    units = verses[cur]
                    token_id = 0
            if units is None:
                continue
            words = phrase_words(row[C_TEXT])
            if not words:
                continue
            strong = strong_id(row[C_STR_HEB].strip(), row[C_STR_GRK].strip())
            for w in words:
                units.append((w.lower(), strong, token_id))
            token_id += 1
    return verses


def parse_usx_words(text):
    """Return ordered list of scripture word records per verse key.

    Each record: [abs_start, abs_end, lower_word]. Only text outside <note>
    subtrees and inside an open verse is considered scripture.
    """
    per_verse = defaultdict(list)
    note_depth = 0
    cur = None
    for m in TAG.finditer(text):
        tok = m.group(0)
        if tok[0] == '<':
            nm = re.match(r'</?([A-Za-z0-9]+)', tok)
            nm = nm.group(1) if nm else ''
            closing = tok.startswith('</')
            selfclose = tok.endswith('/>')
            if nm == 'note':
                if closing:
                    note_depth = max(0, note_depth - 1)
                elif not selfclose:
                    note_depth += 1
            elif nm == 'verse':
                sid = re.search(r'\bsid="([^"]+)"', tok)
                eid = re.search(r'\beid="([^"]+)"', tok)
                if sid:
                    mm = re.match(r'([A-Z0-9]+) (\d+):(\d+)', sid.group(1))
                    cur = (mm.group(1), int(mm.group(2)), int(mm.group(3)))
                if eid:
                    cur = None
        else:
            if note_depth == 0 and cur is not None:
                base = m.start()
                for wm in WORD.finditer(tok):
                    per_verse[cur].append([base + wm.start(), base + wm.end(), wm.group(0).lower()])
    return per_verse


def process_file(path, table, name2code, stats):
    text = open(path, encoding='utf-8').read()
    if '<char style="w" strong="' in text:
        stats['files_skipped'] += 1   # already tagged; idempotent re-run
        return
    code = re.search(r'book code="([A-Z0-9]+)"', text).group(1)
    # find the table book name that maps to this code
    bookname = None
    for nm, cd in name2code.items():
        if cd == code:
            bookname = nm
            break

    per_verse = parse_usx_words(text)
    insertions = []  # (offset, text, sort_priority)

    for vkey, uwords in per_verse.items():
        _, chap, verse = vkey
        units = table.get((bookname, chap, verse))
        stats['verses'] += 1
        if not units:
            stats['verses_no_table'] += 1
            continue

        uw = [w[2] for w in uwords]
        tw = [u[0] for u in units]
        sm = difflib.SequenceMatcher(None, uw, tw, autojunk=False)

        # assign (strong, token_id) to matched usx words; None means leave unwrapped
        assigned = [None] * len(uwords)
        for a, b, n in sm.get_matching_blocks():
            for k in range(n):
                _, strong, tid = units[b + k]
                assigned[a + k] = (strong, tid)

        # group consecutive usx words sharing (strong, token_id) with no tag between them
        i = 0
        N = len(uwords)
        while i < N:
            ai = assigned[i]
            if ai is None or ai[0] is None:
                i += 1
                continue
            j = i
            while (j + 1 < N and assigned[j + 1] == ai and
                   '<' not in text[uwords[j][1]:uwords[j + 1][0]]):
                j += 1
            start = uwords[i][0]
            end = uwords[j][1]
            strong = ai[0]
            # close tag inserted first so that for equal offsets opens/closes order correctly
            insertions.append((start, '<char style="w" strong="%s">' % strong, 0))
            insertions.append((end, '</char>', -1))
            stats['wrapped'] += 1
            i = j + 1

        for k in range(N):
            if assigned[k] is None:
                stats['unaligned_words'] += 1

    if not insertions:
        return

    # apply from the end so earlier offsets stay valid; at the same offset a
    # closing tag (priority -1) must come before an opening tag (priority 0)
    insertions.sort(key=lambda x: (x[0], x[2]))
    out = []
    prev = 0
    for off, frag, _ in insertions:
        out.append(text[prev:off])
        out.append(frag)
        prev = off
    out.append(text[prev:])
    open(path, 'w', encoding='utf-8').write(''.join(out))


def main():
    for usx_glob, table_paths in TARGETS:
        print('=== target %s (tables: %s) ===' % (usx_glob, ', '.join(table_paths)),
              file=sys.stderr)
        name2code = book_name_map(usx_glob)
        table = {}
        for tp in table_paths:
            load_table(tp, table)
        print('loaded %d verses from table(s)' % len(table), file=sys.stderr)

        stats = defaultdict(int)
        for path in sorted(glob.glob(usx_glob)):
            process_file(path, table, name2code, stats)
            print('done', os.path.basename(path), file=sys.stderr)

        print('--- summary for %s ---' % usx_glob)
        print('files skipped (already tagged):', stats['files_skipped'])
        print('verses seen in USX            :', stats['verses'])
        print('verses with no table row      :', stats['verses_no_table'])
        print('char elements wrapped         :', stats['wrapped'])
        print('usx words left unwrapped      :', stats['unaligned_words'])


if __name__ == '__main__':
    main()
