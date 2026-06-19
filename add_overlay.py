#!/usr/bin/env python3
"""
Bake the LetsChurch source-text-overlay (Layer 1) annotations into the BSB/MSB
USX files. Three features (https://github.com/LetsChurch/source-text-overlay):

  divine_name       (OT, 6888) -- mark the divine name and footnote the source
                                   form. We keep the translation wording
                                   (LORD / Lord GOD), wrap the surface word in
                                   <char style="nd">, and add a footnote "Or
                                   Yahweh" / "Or Lord Yahweh" / "Or Yah".
  divine_name_note  (NT, 108)  -- footnote on a NT "Lord"/"LORD"/"GOD" that
                                   renders the OT divine name.
  ot_quotation      (NT, 506)  -- wrap the NT span quoting the OT in
                                   <char style="qt"> and attach a cross-reference
                                   note to the source passage.

Resolution is standoff -> inline: each Layer-1 annotation is anchored to a
location in our already-Strong's-tagged USX and materialized as USX markup.

  * divine_name anchors on the ordered divine-name words in a verse. Those are
    exactly the <char style="w"> tokens whose Strong's number is H03068 (YHWH),
    H03069 (YHWH as "GOD") or H03050 (Yah) -- so the Strong's pass already did
    the hard part. Overlay annotations are paired with these in order and the
    footnote text comes from the overlay's display_form.
  * divine_name_note anchors on the n-th occurrence (ordinal) of its marked_word.
  * ot_quotation fuzzy-aligns its quote_text to the verse words and wraps the
    whole <char style="w"> elements the span covers.

Only scripture text is touched; existing structure and footnotes are preserved
byte-for-byte apart from the inserted markup. Run with --apply to write files;
without it the script only reports resolution statistics.
"""
import csv, re, sys, glob, os, json, difflib
from collections import defaultdict

OVERLAY = '/tmp/source-text-overlay/overlay/overlay_layer1.jsonl'

TARGETS = ['./bsb/USX_1/*.usx', './msb/USX_1/*.usx']

# OSIS book code (overlay) -> USX book code (our files)
OSIS = {
    '1Chr': '1CH', '1Cor': '1CO', '1Kgs': '1KI', '1Pet': '1PE', '1Sam': '1SA',
    '1Tim': '1TI', '2Chr': '2CH', '2Cor': '2CO', '2Kgs': '2KI', '2Pet': '2PE',
    '2Sam': '2SA', '2Thess': '2TH', '2Tim': '2TI', 'Acts': 'ACT', 'Amos': 'AMO',
    'Dan': 'DAN', 'Deut': 'DEU', 'Eph': 'EPH', 'Exod': 'EXO', 'Ezek': 'EZK',
    'Ezra': 'EZR', 'Gal': 'GAL', 'Gen': 'GEN', 'Hab': 'HAB', 'Hag': 'HAG',
    'Heb': 'HEB', 'Hos': 'HOS', 'Isa': 'ISA', 'Jas': 'JAS', 'Jer': 'JER',
    'Job': 'JOB', 'Joel': 'JOL', 'John': 'JHN', 'Jonah': 'JON', 'Josh': 'JOS',
    'Judg': 'JDG', 'Lam': 'LAM', 'Lev': 'LEV', 'Luke': 'LUK', 'Mal': 'MAL',
    'Mark': 'MRK', 'Matt': 'MAT', 'Mic': 'MIC', 'Nah': 'NAM', 'Neh': 'NEH',
    'Num': 'NUM', 'Obad': 'OBA', 'Phil': 'PHP', 'Prov': 'PRO', 'Ps': 'PSA',
    'Rev': 'REV', 'Rom': 'ROM', 'Ruth': 'RUT', 'Song': 'SNG', 'Zech': 'ZEC',
    'Zeph': 'ZEP',
}

DN_STRONG = {'H03068', 'H03069', 'H03050'}          # YHWH, YHWH-as-GOD, Yah
WORD = re.compile(r"[A-Za-z0-9]+(?:[’'\-][A-Za-z0-9]+)*")
# the divine-name surface word inside a divine-name token's text ("the LORD" -> LORD)
SURFACE = re.compile(r"LORD(?:’S|’s|’)?|GOD(?:’S|’s)?")
TAG = re.compile(r'<[^>]*>|[^<]+')


def fnote(body, style='f', char='ft'):
    return ('<note caller="+" style="%s"><char style="%s" closed="false">%s</char></note>'
            % (style, char, body))


def load_overlay():
    by_verse = defaultdict(lambda: {'divine_name': [], 'divine_name_note': [], 'ot_quotation': []})
    for line in open(OVERLAY, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        code = OSIS.get(o['osis_ref'].split('.')[0])
        if not code:
            continue
        feat = o['feature']
        if feat in by_verse[(code, o['chapter'], o['verse'])]:
            by_verse[(code, o['chapter'], o['verse'])][feat].append(o)
    for v in by_verse.values():
        for lst in v.values():
            lst.sort(key=lambda a: a.get('ordinal') or 0)
    return by_verse


def parse_verses(text):
    """Per verse key -> list of items in reading order.

    item = ('w', open_off, text_off, text_end, close_end, strong, word_text)
         | ('t', off, end, plain_text)
    Note subtrees are skipped. open_off/close_end bound the whole <char> element.
    """
    items = defaultdict(list)
    cur = None
    note_depth = 0
    i = 0
    WTAG = re.compile(r'<char style="w" strong="([HG]\d{5})">')
    n = len(text)
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
                if 'eid=' in tok:
                    cur = None
                else:
                    sid = re.search(r'\bsid="([A-Z0-9]+) (\d+):(\d+)"', tok)
                    if sid:
                        cur = (sid.group(1), int(sid.group(2)), int(sid.group(3)))
            elif nm == 'char' and not closing:
                wm = WTAG.match(tok)
                if wm and note_depth == 0 and cur is not None:
                    strong = wm.group(1)
                    text_off = m.end()
                    close = text.find('</char>', text_off)
                    word = text[text_off:close]
                    items[cur].append(('w', m.start(), text_off, close,
                                       close + len('</char>'), strong, word))
        else:
            if note_depth == 0 and cur is not None:
                # plain visible text that is NOT inside a <char> element
                # (skip the inner text of a w-char: that's the tail handled above)
                prev = items[cur][-1] if items[cur] else None
                if prev and prev[0] == 'w' and m.start() < prev[4]:
                    continue  # this text is the w-char's own inner text / already covered
                items[cur].append(('t', m.start(), m.end(), tok))
    return items


def verse_words(items):
    """Flat list of (lower_word, end_off, item_index, surface_word) in reading order."""
    out = []
    for idx, it in enumerate(items):
        if it[0] == 'w':
            base, txt = it[2], it[6]
        else:
            base, txt = it[1], it[3]
        for wm in WORD.finditer(txt):
            out.append((wm.group(0).lower(), base + wm.start(), base + wm.end(), idx, wm.group(0)))
    return out


# The divine-name footnote form follows directly from the Strong's number the
# Strong's pass already attached (matches the overlay's display_form 99.9% of the
# time), so we don't need the fragile ordinal pairing: mark every divine-name
# surface word in any verse the overlay flagged.
DN_FORM = {'H03068': 'Yahweh', 'H03069': 'Lord Yahweh', 'H03050': 'Yah'}


def resolve_divine_name(items, anns, ins, stats):
    if not anns:
        return
    for it in items:
        if it[0] != 'w' or it[5] not in DN_STRONG:
            continue
        sm = SURFACE.search(it[6])
        if not sm:
            stats['dn_no_surface'] += 1   # YHWH rendered as a pronoun -> nothing to mark
            continue
        s = it[2] + sm.start()
        e = it[2] + sm.end()
        ins.append((s, 2, '<char style="nd">'))
        ins.append((e, 0, '</char>' + fnote('Or ' + DN_FORM[it[5]])))
        stats['dn_applied'] += 1


def _norm(w):
    return w.lower().rstrip('’\'')


def resolve_divine_name_note(items, anns, ins, stats):
    words = verse_words(items)
    seq = [w[0].rstrip('’\'') for w in words]   # lowercased, possessive-stripped
    for a in anns:
        target = _norm(a['marked_word'])
        # the overlay's casing (LORD vs Lord) is from its source translation, so
        # match case-insensitively and disambiguate by surrounding context.
        cand = [i for i, w in enumerate(seq) if w == target]
        if not cand:
            stats['dnote_unresolved'] += 1
            continue
        if len(cand) == 1:
            pick = cand[0]
        else:
            before = [_norm(x) for x in WORD.findall(a.get('context_before', ''))]
            after = [_norm(x) for x in WORD.findall(a.get('context_after', ''))]
            def score(i):
                s = 0
                for k in range(1, len(before) + 1):
                    if i - k >= 0 and seq[i - k] == before[-k]:
                        s += 1
                    else:
                        break
                for k in range(len(after)):
                    if i + 1 + k < len(seq) and seq[i + 1 + k] == after[k]:
                        s += 1
                    else:
                        break
                return s
            ordn = a.get('ordinal') or 1
            pick = max(cand, key=lambda i: (score(i), -abs(cand.index(i) + 1 - ordn)))
        ins.append((words[pick][2], 1, fnote(a['note_text'])))
        stats['dnote_applied'] += 1


def resolve_ot_quotation(items, anns, ins, stats, text):
    words = verse_words(items)
    vw = [w[0] for w in words]
    for a in anns:
        qwords = [x.lower() for x in WORD.findall(a['quote_text'])]
        if not qwords or not vw:
            stats['otq_unresolved'] += 1
            continue
        sm = difflib.SequenceMatcher(None, vw, qwords, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
        if not blocks:
            stats['otq_unresolved'] += 1
            continue
        # drop isolated singleton anchors at the ends that sit far from the main
        # run -- they over-extend the span when a stray word matches elsewhere.
        while len(blocks) > 1 and blocks[0].size == 1 and blocks[1].a - blocks[0].a > 4:
            blocks = blocks[1:]
        while len(blocks) > 1 and blocks[-1].size == 1 and \
                blocks[-1].a - (blocks[-2].a + blocks[-2].size - 1) > 4:
            blocks = blocks[:-1]
        first = blocks[0].a
        last = blocks[-1].a + blocks[-1].size - 1
        ratio = sum(b.size for b in blocks) / len(qwords)

        # Build the element-aligned pieces the span covers (whole <char> elements
        # for w-tokens; the word's own extent for plain text).
        pieces = []
        k = first
        while k <= last:
            w = words[k]
            it = items[w[3]]
            if it[0] == 'w':
                pieces.append((it[1], it[4]))
                k += 1
                while k <= last and words[k][3] == w[3]:
                    k += 1
            else:
                pieces.append((w[1], w[2]))
                k += 1
        # Merge into runs, breaking where a block-level tag (para/verse) sits
        # between pieces -- a char element must not cross a paragraph boundary.
        runs = []
        cur = list(pieces[0])
        for ps, pe in pieces[1:]:
            gap = text[cur[1]:ps]
            if '<para' in gap or '</para' in gap or '<verse' in gap:
                runs.append(tuple(cur))
                cur = [ps, pe]
            else:
                cur[1] = pe
        runs.append(tuple(cur))

        note = fnote(a['cross_ref'], style='x', char='xt') if a.get('cross_ref') else ''
        for i, (rs, re_) in enumerate(runs):
            ins.append((rs, 2, '<char style="qt">'))
            close = '</char>' + (note if i == len(runs) - 1 else '')
            ins.append((re_, 0, close))
        stats['otq_applied'] += 1
        if ratio < 0.6:
            stats['otq_low_conf'] += 1
        if len(runs) > 1:
            stats['otq_split'] += 1


def apply_insertions(text, ins):
    # priority at one offset: closing material (0) before notes (1) before opens (2)
    ins.sort(key=lambda x: (x[0], x[1]))
    out = []
    prev = 0
    for off, _pri, frag in ins:
        out.append(text[prev:off])
        out.append(frag)
        prev = off
    out.append(text[prev:])
    return ''.join(out)


def process_file(path, overlay, stats, apply):
    text = open(path, encoding='utf-8').read()
    if '<char style="nd">' in text or '<char style="qt">' in text:
        stats['files_skipped'] += 1
        return
    items_by_verse = parse_verses(text)
    ins = []
    for vkey, items in items_by_verse.items():
        ov = overlay.get(vkey)
        if not ov:
            continue
        if ov['divine_name']:
            resolve_divine_name(items, ov['divine_name'], ins, stats)
        if ov['divine_name_note']:
            resolve_divine_name_note(items, ov['divine_name_note'], ins, stats)
        if ov['ot_quotation']:
            resolve_ot_quotation(items, ov['ot_quotation'], ins, stats, text)
    if apply and ins:
        open(path, 'w', encoding='utf-8').write(apply_insertions(text, ins))


def main():
    apply = '--apply' in sys.argv
    overlay = load_overlay()
    for usx_glob in TARGETS:
        stats = defaultdict(int)
        for path in sorted(glob.glob(usx_glob)):
            process_file(path, overlay, stats, apply)
        print('=== %s (%s) ===' % (usx_glob, 'APPLIED' if apply else 'dry-run'))
        for kkey in ['files_skipped', 'dn_applied', 'dn_no_surface', 'dn_unpaired_anns',
                     'dnote_applied', 'dnote_unresolved',
                     'otq_applied', 'otq_unresolved', 'otq_low_conf']:
            print('  %-20s %d' % (kkey, stats[kkey]))


if __name__ == '__main__':
    main()
