# BSB / MSB Enriched USX

[USX](https://ubsicap.github.io/usx/) editions of the **Berean Standard Bible
(BSB)** and the **Majority Standard Bible (MSB)**, enriched in place with:

1. **Inline Strong's numbers** on every translated word.
2. **Words-of-Jesus** (red-letter) markup.

Both editions are the same translation; the **MSB differs from the BSB only in
the New Testament**, where it follows the Majority Text (e.g. Romans 8:1 and the
Matthew 6:13 doxology carry the longer Byzantine readings). The Old Testament is
identical between the two.

## Layout

```
bsb/                     Berean Standard Bible
  USX_1/*.usx            66 enriched book files
  styles.xml, versification.vrs, eng_en.ldml
msb/                     Majority Standard Bible
  USX_1/*.usx            66 enriched book files
  styles.xml, versification.vrs, eng_en.ldml, metadata.xml, license.xml

bsb_tables.tsv           BSB interlinear table (word -> Strong's), OT + NT
msb_nt_tables.tsv        MSB NT interlinear table (Majority Text)
words_of_jesus.jsonl     per-verse red-letter word runs for the BSB

add_strongs.py           inserts inline Strong's numbers
add_words_of_jesus.py    adds words-of-Jesus (red-letter) markup to the BSB
```

## Enrichments

### 1. Strong's numbers (`add_strongs.py`)

Every translated word/phrase is wrapped in the USX wordlist character style with
a `strong` attribute. Identifiers use the spec format: `H`/`G` prefix + the
number zero-padded to five digits (Hebrew & Aramaic → `H`, Greek → `G`).

```xml
<verse number="1" .../><char style="w" strong="H07225">In the beginning</char>
<char style="w" strong="H00430">God</char> <char style="w" strong="H01254">created</char> …
```

The mapping comes from the interlinear tables, whose English text reconstructs
the verse exactly. The OT and the BSB NT come from `bsb_tables.tsv`; the MSB NT
comes from `msb_nt_tables.tsv`. Resolution is word-aligned per verse, so
punctuation, quotation marks and footnotes stay outside the tags.

- BSB: 381,950 elements · MSB: 383,324 elements
- Every verse matched a table; ~22 words per edition are left untagged (stray
  source artifacts such as a literal `vvv` marker).

### 2. Words of Jesus (`add_words_of_jesus.py`)

Jesus's spoken words are wrapped in the red-letter character style,
`<char style="wj">`, nested *outside* the Strong's markup (with the
opening/closing quotation marks pulled inside the span).

```xml
<char style="wj">“<char style="w" strong="G03107">Blessed are</char>
  <char style="w" strong="G03588">the</char> …</char>
```

The MSB already ships with red-letter markup, so only the BSB needed it. The
plain "bsb2usfm" BSB has none; the publisher's richer BSB export carries it and
its NT text matches ours word-for-word, so the spans transfer by word index
(captured in `words_of_jesus.jsonl`) with no fuzzy alignment. Spans are split at
paragraph boundaries to stay well-formed.

- BSB: 2,302 wj spans added · MSB: 2,319 (pre-existing, untouched).

## Regenerating

The scripts edit the USX files **in place** and only ever *add* markup —
existing scripture text is preserved byte-for-byte (verified by XML
well-formedness plus a scripture-word diff). All are **idempotent**: a file that
already carries the markup is skipped, so re-running is safe.

```sh
python3 add_strongs.py                  # add Strong's numbers (BSB + MSB)
python3 add_words_of_jesus.py --apply   # add red-letter markup to the BSB
```

(Omit `--apply` to dry-run and print stats only.)

`add_words_of_jesus.py` reads the committed `words_of_jesus.jsonl`. To
regenerate that file from a wj-marked BSB export, run
`python3 add_words_of_jesus.py --generate '<export>/USX_1/*.usx'`.

Order matters: run `add_strongs.py` first — the red-letter nesting keys off the
Strong's markup it adds.
