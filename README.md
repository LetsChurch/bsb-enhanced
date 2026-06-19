# BSB / MSB Enhanced USX

[USX](https://ubsicap.github.io/usx/) editions of the **Berean Standard Bible
(BSB)** and the **Majority Standard Bible (MSB)**, enhanced in place with:

1. **Inline Strong's numbers** on every translated word.
2. **Source-text overlay** annotations baked into the markup — divine-name
   marking, divine-name footnotes, and OT-quotation tagging.

Both editions are the same translation; the **MSB differs from the BSB only in
the New Testament**, where it follows the Majority Text (e.g. Romans 8:1 and the
Matthew 6:13 doxology carry the longer Byzantine readings). The Old Testament is
identical between the two.

## Layout

```
bsb/                     Berean Standard Bible
  USX_1/*.usx            66 enhanced book files
  styles.xml, versification.vrs, eng_en.ldml
msb/                     Majority Standard Bible
  USX_1/*.usx            66 enhanced book files
  styles.xml, versification.vrs, eng_en.ldml, metadata.xml, license.xml

bsb_tables.tsv           BSB interlinear table (word -> Strong's), OT + NT
msb_nt_tables.tsv        MSB NT interlinear table (Majority Text)

add_strongs.py           inserts inline Strong's numbers
add_overlay.py           bakes in the source-text-overlay annotations
```

## Enhancements

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

### 2. Source-text overlay (`add_overlay.py`)

Bakes the three features of
[LetsChurch/source-text-overlay](https://github.com/LetsChurch/source-text-overlay)
(Layer 1) directly into the USX. Applied to **both** editions.

**`divine_name`** (OT) — the divine name keeps its traditional rendering but is
wrapped in `<char style="nd">` with a footnote giving the source form. The form
is taken from the Strong's number already attached (`H03068`→Yahweh,
`H03069`→Lord Yahweh, `H03050`→Yah).

```xml
<char style="w" strong="H03068">the <char style="nd">LORD</char><note caller="+"
  style="f"><char style="ft" closed="false">Or Yahweh</char></note></char>
```

**`divine_name_note`** (NT) — a footnote where a NT "Lord" represents the OT
divine name, located by surrounding context.

```xml
<char style="w" strong="G02962">of the Lord<note caller="+" style="f"><char
  style="ft" closed="false">In OT, Yahweh, cf. 1 Kin 1:3</char></note></char>
```

**`ot_quotation`** (NT) — the span quoting the OT is wrapped in
`<char style="qt">` and given a cross-reference note to the source passage.
Spans are fuzzy-aligned (the overlay's quote wording differs from the BSB/MSB),
split at paragraph boundaries to stay well-formed.

```xml
<char style="qt"><char style="w" strong="G02400">Behold</char>, … <char
  style="w" strong="G02192">will be with child</char></char><note caller="+"
  style="x"><char style="xt" closed="false">Is 7:14</char></note>
```

Per edition: ~6,720 divine-name marks, ~101–102 divine-name notes, ~503–505 of
the 506 OT quotations. A minority of quotation spans are approximate where the
translation paraphrases the quoted text; the cross-reference note is always
correct.

## Regenerating

The scripts edit the USX files **in place** and only ever *add* markup —
existing scripture text is preserved byte-for-byte (verified by XML
well-formedness plus a scripture-word diff). Both are **idempotent**: a file that
already carries the markup is skipped, so re-running is safe.

```sh
python3 add_strongs.py            # add Strong's numbers (BSB + MSB)
python3 add_overlay.py            # dry-run: print resolution stats only
python3 add_overlay.py --apply    # bake in the overlay annotations
```

`add_overlay.py` expects the overlay data at
`/tmp/source-text-overlay/overlay/overlay_layer1.jsonl`; clone the
[source-text-overlay](https://github.com/LetsChurch/source-text-overlay) repo
there (or edit the `OVERLAY` constant) before running.

Order matters: run `add_strongs.py` first — the overlay's divine-name resolution
keys off the Strong's numbers it adds.
