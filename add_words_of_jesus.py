#!/usr/bin/env python3
"""
Add words-of-Jesus (red-letter) markup to the enhanced BSB USX.

The plain "bsb2usfm" BSB edition in bsb/ has no <char style="wj"> markup. The
publisher's richer BSB export (same critical-text wording) does, and its NT text
matches ours word-for-word, so the wj spans transfer by word index with no
fuzzy alignment.

Two modes:

  --generate <src_glob>   Read a wj-marked BSB (publisher export) and write
                          words_of_jesus.jsonl: per NT verse, the half-open
                          [start, end) runs over the verse's scripture words
                          that fall inside <char style="wj">.

  --apply (default dry)   Read words_of_jesus.jsonl and wrap those word runs in
                          <char style="wj"> in bsb/USX_1, nesting wj *outside*
                          the existing Strong's/overlay markup and splitting at
                          paragraph boundaries. Pass --apply to write files.

The MSB already ships with wj markup, so it is left untouched (the script only
reports its coverage).
"""
import re, glob, os, json, sys
from collections import defaultdict

DATA = 'words_of_jesus.jsonl'
BSB_GLOB = './bsb/USX_1/*.usx'
MSB_GLOB = './msb/USX_1/*.usx'

NT_CODES = {
    'MAT', 'MRK', 'LUK', 'JHN', 'ACT', 'ROM', '1CO', '2CO', 'GAL', 'EPH',
    'PHP', 'COL', '1TH', '2TH', '1TI', '2TI', 'TIT', 'PHM', 'HEB', 'JAS',
    '1PE', '2PE', '1JN', '2JN', '3JN', 'JUD', 'REV',
}
WORD = re.compile(r"[A-Za-z0-9]+(?:[’'\-][A-Za-z0-9]+)*")
TAG = re.compile(r'<[^>]*>|[^<]+')
# opening/closing quote+punctuation pulled into the wj span at its edges
# (no whitespace -- the inter-word space stays outside the span, matching the
# publisher's wj style)
LEAD = '“‘"('
TRAIL = '”’"),.;:!?'


def iter_tokens(text):
    for m in TAG.finditer(text):
        yield m.start(), m.end(), m.group(0)


def parse_wj_runs(text):
    """{ref -> [[start,end), ...]} for words inside <char style=wj>, from a source export."""
    runs = {}
    cur = None
    note_depth = 0
    char_styles = []
    words = []     # (is_wj) per scripture word of current verse
    def flush():
        if cur is None:
            return
        rs = []
        i = 0
        while i < len(words):
            if words[i]:
                j = i
                while j + 1 < len(words) and words[j + 1]:
                    j += 1
                rs.append([i, j + 1])
                i = j + 1
            else:
                i += 1
        if rs:
            runs['%s %d:%d' % cur] = rs
    for s, e, tok in iter_tokens(text):
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
            elif nm == 'char' and note_depth == 0:
                if closing:
                    if char_styles:
                        char_styles.pop()
                elif not selfclose:
                    st = re.search(r'style="([^"]+)"', tok)
                    char_styles.append(st.group(1) if st else '')
            elif nm == 'verse':
                if 'eid=' in tok:
                    flush(); cur = None; words = []
                else:
                    flush(); words = []
                    sid = re.search(r'sid="([A-Z0-9]+) (\d+):(\d+)"', tok)
                    cur = (sid.group(1), int(sid.group(2)), int(sid.group(3))) if sid else None
        elif note_depth == 0 and cur is not None:
            inwj = 'wj' in char_styles
            for _ in WORD.finditer(tok):
                words.append(inwj)
    flush()
    return runs


def generate(src_glob):
    out = []
    for f in sorted(glob.glob(src_glob)):
        code = re.search(r'book code="([A-Z0-9]+)"', open(f, encoding='utf-8').read()).group(1)
        if code not in NT_CODES:
            continue
        runs = parse_wj_runs(open(f, encoding='utf-8').read())
        for ref, rs in runs.items():
            out.append({'ref': ref, 'runs': rs})
    out.sort(key=lambda r: r['ref'])
    with open(DATA, 'w', encoding='utf-8') as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('wrote %d verses with wj runs to %s' % (len(out), DATA))


def parse_containers(text):
    """{ref -> (word_cont, conts)} for our enhanced USX.

    conts: list of [start_off, end_off] -- a top-level <char> element, or a bare
           depth-0 word's own extent.
    word_cont: per scripture word (in reading order), the index into conts.
    """
    res = {}
    cur = None
    note_depth = 0
    depth = 0
    cur_cont = None       # index of the open top-level container, or None
    word_cont = []
    conts = []
    def store():
        if cur is not None:
            res[cur] = (word_cont, conts)
    for s, e, tok in iter_tokens(text):
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
            elif nm == 'char' and note_depth == 0:
                if closing:
                    depth -= 1
                    if depth == 0 and cur_cont is not None:
                        conts[cur_cont][1] = e
                        cur_cont = None
                elif not selfclose:
                    if depth == 0:
                        conts.append([s, None])
                        cur_cont = len(conts) - 1
                    depth += 1
            elif nm == 'verse':
                store()
                word_cont = []; conts = []; depth = 0; cur_cont = None
                if 'eid=' in tok:
                    cur = None
                else:
                    sid = re.search(r'sid="([A-Z0-9]+) (\d+):(\d+)"', tok)
                    cur = (sid.group(1), int(sid.group(2)), int(sid.group(3))) if sid else None
        elif note_depth == 0 and cur is not None:
            for wm in WORD.finditer(tok):
                if cur_cont is not None:
                    word_cont.append(cur_cont)
                else:
                    conts.append([s + wm.start(), s + wm.end()])
                    word_cont.append(len(conts) - 1)
    store()
    return res


def apply_to_bsb(data, apply):
    stats = defaultdict(int)
    for f in sorted(glob.glob(BSB_GLOB)):
        text = open(f, encoding='utf-8').read()
        code = re.search(r'book code="([A-Z0-9]+)"', text).group(1)
        if code not in NT_CODES:
            continue
        if '<char style="wj">' in text:
            stats['files_skipped'] += 1
            continue
        verses = parse_containers(text)
        ins = []
        for ref, rs in data.items():
            bk = ref.split(' ')[0]
            if bk != code:
                continue
            wc, conts = verses.get(_key(ref), (None, None))
            if wc is None:
                stats['verses_missing'] += 1
                continue
            for a, b in rs:
                if b > len(wc):
                    stats['runs_oob'] += 1
                    continue
                # contiguous containers covered by this word run
                ci = []
                for w in range(a, b):
                    if not ci or ci[-1] != wc[w]:
                        ci.append(wc[w])
                # split into block-contiguous groups (no para/verse tag between)
                group = [ci[0]]
                groups = []
                for c in ci[1:]:
                    gap = text[conts[group[-1]][1]:conts[c][0]]
                    if '<para' in gap or '</para' in gap or '<verse' in gap:
                        groups.append(group); group = [c]
                    else:
                        group.append(c)
                groups.append(group)
                for g in groups:
                    s = conts[g[0]][0]
                    e = conts[g[-1]][1]
                    # pull adjacent opening/closing quote+punctuation into the span
                    while s > 0 and text[s - 1] in LEAD and text[s - 1] != '<':
                        s -= 1
                    while e < len(text) and text[e] in TRAIL and text[e] != '<':
                        e += 1
                    ins.append((s, 2, '<char style="wj">'))
                    ins.append((e, 0, '</char>'))
                stats['runs_applied'] += 1
        if apply and ins:
            ins.sort(key=lambda x: (x[0], x[1]))
            out = []; prev = 0
            for off, _p, frag in ins:
                out.append(text[prev:off]); out.append(frag); prev = off
            out.append(text[prev:])
            open(f, 'w', encoding='utf-8').write(''.join(out))
    return stats


def _key(ref):
    bk, cv = ref.split(' ')
    c, v = cv.split(':')
    return (bk, int(c), int(v))


def main():
    args = sys.argv[1:]
    if '--generate' in args:
        src = args[args.index('--generate') + 1]
        generate(src)
        return
    apply = '--apply' in args
    data = {}
    for line in open(DATA, encoding='utf-8'):
        line = line.strip()
        if line:
            o = json.loads(line)
            data[o['ref']] = o['runs']
    stats = apply_to_bsb(data, apply)
    print('=== BSB wj (%s) ===' % ('APPLIED' if apply else 'dry-run'))
    for k in ['files_skipped', 'verses_missing', 'runs_oob', 'runs_applied']:
        print('  %-16s %d' % (k, stats[k]))
    msb_wj = sum(open(f, encoding='utf-8').read().count('<char style="wj">')
                 for f in glob.glob(MSB_GLOB))
    print('MSB already carries %d wj spans (left untouched)' % msb_wj)


if __name__ == '__main__':
    main()

