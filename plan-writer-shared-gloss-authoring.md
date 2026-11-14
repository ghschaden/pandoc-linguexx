# Shared-gloss authoring in LibreOffice Writer

Status: implemented in Writer; validation results recorded below.

## Intended behaviour

Select typed lines and run the existing **Typeset example** command. A
`\CommonGloss` line selects shared-gloss layout. The resulting table must
round-trip through Untypeset and Typeset, retaining text, formatting, gaps,
judgments, annotations and the existing example-number field identity.

Use the syntax already returned by Untypeset:

```text
Optional heading
a. *Alpha {} Cappa\exannot{ANNA}
b. Beta Longer Delta\exannot{ANNB}
\CommonGloss FIRST SECOND THIRD
\CommonGloss ONE TWO THREE
Translation.
```

The first version supports one shared group per selection: an optional
heading, one or more distinct marked variants with one object-language line
each, one or more consecutive shared tiers, and an optional final translation.
The translation need not be quoted: its position after the explicit shared
tiers distinguishes it. Existing marker syntax and heading rules apply.
`{two words}` occupies one alignment slot; `{}` occupies an empty slot.
Short rows are padded on the right; interior gaps must be explicit.

RTL remains excluded. Morpheme-aligned authoring, language declarations,
mixed ordinary/shared groups and tree/shared combinations are outside this
first implementation. Word and OnlyOffice retain their current refusal of
shared-gloss Typeset until separately implemented.

## 1. Parse a shared example explicitly

In `src/linguexx2odt/writermacro/LinguExx.bas`, replace the blanket rejection
in `LxParseItems` with exact command detection and a dedicated shared parser.
Do not interpret a longer word such as `\CommonGlossary` as the command.

Represent the group explicitly: heading, variant items, shared tier arrays
and translation. Reuse existing item fields for markers, judgments and
annotations. Carry the shared data explicitly to layout; do not disguise
shared tiers as another variant or spread additional mutable parser globals.
Keep the ordinary parsing and layout path intact.

Add a gap-preserving tokenization mode/helper. `LxSplitWords` currently
discards empty groups, which would shift every column after `{}`. Preserve
format tags, grouped words and empty slots, and report unbalanced braces.
Keep ordinary tokenization behaviour unless a deliberate compatibility
change is covered by existing tests.

Validate the complete selection before inserting styles or replacing text.
Reject missing variants, empty shared tiers, duplicate markers, variants
after shared tiers, extra variant tiers, shared tiers after translation,
and multiple translation paragraphs. Errors should identify the offending
line and explain the accepted syntax. A failed parse leaves the document
and numbering unchanged. Reject this syntax in the tree command as well.

## 2. Compute one shared layout

Introduce a shared layout path beside `LxLayOut`. Reuse font measurement,
page width, layout preferences, judgment-column geometry, annotation space,
band packing and grid helpers where their assumptions fit.

- Determine the slot count from the longest variant or shared tier.
- Measure each slot across **all** variants and shared tiers, including rich
  text. Empty cells retain their slot without contributing word width.
- Reserve number, marker, judgment and annotation space before packing.
- Compute one set of band boundaries for the whole group. A band contains
  every variant followed by every shared tier for the same slot range.
- Build the physical column grid from those bands, reusing `LxBuildGrid`
  through an adapter if appropriate; do not independently wrap variants.
- Apply the existing overwide-word policy and verify narrow-page behaviour.

Use `src/linguexx2odt/emit_odt.py` and the converter's shared-layout fixtures
as the structural reference. The macro's font measurement need not produce
byte-identical widths, but alignment and band ordering must agree.

## 3. Emit a table understood by existing readers

Add a shared emitter beside `LxEmitTable`, sharing the small cell, style,
number and width helpers. Avoid a broad rewrite of the ordinary emitter.

- Ensure `LxVariant`, `LxCommonGloss` and `LxCommonGlossBand` styles exist in
  new documents, inheriting the same defaults as converter-created tables.
  Preserve any existing user customizations.
- Emit the optional heading once and the example number exactly once.
  Reuse the number-field preservation path when re-typesetting.
- Emit all variants then all shared tiers in each band. Repeat variant
  markers, judgments and annotations using the converter's convention.
- Mark variant cells and shared cells with their structural paragraph
  styles; use the continuation style on the first shared tier of later
  bands. Preserve empty cells and the distinction from filler columns.
- Emit the translation once after the final band at the example indent,
  starting at the marker column, as the converter does.
- Retain spacer rows, tagged formatting, annotation-column styling and the
  existing single-step Undo behaviour.

Verify the existing `LxReadCommonTable` reads these tables without special
cases for their origin. Any reader fix must also retain converter-table
compatibility. Trailing unused padding may normalize away; interior gaps
and meaningful trailing slots in the group must survive.

## 4. Validate through real Writer operations

Extend `tools/run_macro_test.py` and reuse the reviewed expected lines in
`tests/fixtures/linguexx15-untypeset.json`. Replace Writer's current
shared-gloss-refusal assertion with successful Typeset assertions; leave
the Word/OnlyOffice refusal tests intact.

Cover these behaviours:

- Fresh typed input and converter table → Untypeset → Typeset → Untypeset.
- With/without heading and translation; one/multiple shared tiers; judged
  and unjudged variants; annotations; grouped phrases; interior and leading
  gaps; unequal row lengths; bold, italic and small-cap text.
- Forced continuation bands on a narrow page: correct row order, identical
  slot boundaries across variants/tiers, repeated markers/annotations and
  a single translation and number.
- Stable number-field identity and working references through repeated
  cycles; one Undo restores the original selection or table.
- Invalid input leaves text, tables and number fields unchanged, including
  a valid operation after a failed one to catch stale parser state.
- Save/reopen ODT and export/reopen DOCX; verify structural styles and
  Untypeset recovery. Check converter reverse-reading of authored tables.
- PDF coordinate checks for aligned slot starts, hanging judgments,
  annotation position, translation indent and absence of page overflow.

Run the full Writer integration suite to protect ordinary glosses, trees,
notes, references and formatting. Run `make check`, `make js-test`, lint
and macro-constant synchronization checks. Validate the packaged extension
in the isolated Writer profile used by the existing harness.

## 5. Document and package

Update README and the manual with the typed syntax, gaps, shared wrapping,
translation rule and supported scope. Distinguish Writer's new authoring
support from the remaining Word/OnlyOffice limitation. Update the 1.5 plan,
rebuild the PDF manual and Writer OXT, and record validation results.

## Delivery order and completion criteria

Implement parsing/tokenization first, then shared measurement and emission,
then round-trip/rendering coverage and documentation. Enable shared Typeset
only when the complete path works, so no intermediate implementation silently
turns a shared gloss into an ordinary paradigm.

Done means users can type the documented example or edit Untypeset output,
run Typeset, and repeat that cycle with stable content and numbering; all
shared rows align across bands, invalid input is non-destructive, and the
existing Writer integration suite passes.

## Implementation and validation (2026-11-14)

Implemented explicit shared parsing and gap-preserving tokenization, common
measurement/band boundaries, structural row emission, and shared styles.
Ordinary parsing/layout remains on its existing path. Annotation extraction
now retains rich-text tags. Reverse reading ignores authored physical grid
padding while retaining structural empty slots.

The Writer harness now checks fresh authoring, converter-table round trips,
invalid-input atomicity and recovery, single-step Undo, repeated cycles,
number identity, grouped phrases and gaps, unequal lengths, multiple tiers,
headings and translations, bold/italic/small caps, ODT/DOCX persistence,
forced continuation order, PDF slot/judgment/annotation/translation coordinates
and page bounds, and reverse conversion of authored tables. Word/OnlyOffice
refusal tests remain in place.

Validation commands and artifacts:

- `make check`: 615 tests; lint included.
- `make js-test`: all tests pass.
- `python3 tools/sync_macro.py`: all generated constants synchronized.
- `python3 -m pytest -q tests/test_reverse.py`: 72 tests pass.
- `python3 tools/run_macro_test.py /tmp/lx-shared-final-validation`: full
  isolated Writer suite, including packaged extension installation/commands.
- `make manual`: rebuilt `docs/manual/pandoc-linguexx.pdf`.
- `make oxt`: rebuilt `dist/linguexx-0.1.0.oxt`.

The final Writer and check logs are `/tmp/lx-shared-final-validation.log` and
`/tmp/lx-shared-check-final.log`; the focused authoring log is
`/tmp/shared-target.log`. No changes were committed.

## OnlyOffice follow-up (2026-11-14)

The user subsequently requested the same authoring support in OnlyOffice.
OnlyOffice now opts into the shared parser; Word keeps the existing refusal.
The core carries shared tiers explicitly and measures every variant/tier
before packing a common set of bands. The common table-row builder emits
converter-compatible variant, shared and continuation styles, repeated
markers/judgments/annotations, one number and one final translation.

Validation includes fresh typed input; rich text; leading/interior gaps,
grouped phrases and unequal lengths; invalid-input rejection followed by a
valid operation; repeated cycles with stable bookmarks; converter-table
round trips; DOCX save/reopen; reverse conversion; and PDF slot starts,
annotation positions, translation indent and page bounds on a narrow page.
Independent Node tests compare grid widths, cell spans, paragraph styles and
row text against the converter fixtures. Document Builder checks the actual
commands from the packaged bundle, alongside the ordinary examples, trees,
references, formatting, layout settings and note refusals.

Commands: `make js-test`, `make onlyoffice-test`, `make check`,
`python3 tools/sync_macro.py`, `make manual`, and `make onlyoffice`.
Logs: `/tmp/lx-oo-js-final.log`, `/tmp/lx-oo-release.log`,
`/tmp/lx-oo-check.log`, `/tmp/lx-oo-manual.log`.
The rebuilt plugin is `dist/linguexx-onlyoffice.plugin`.
Document Builder exercises the editor APIs headlessly; no interactive
OnlyOffice Desktop Undo check was performed in this follow-up.

OnlyOffice follow-up results: all 615 Python tests passed; all 12 JavaScript
test files passed; the full Document Builder suite passed (48 fresh-input
fixtures: 42 insertions and six refusals, plus converter/persistence/PDF
scenarios). Lint, whitespace checks and constant synchronization passed.
The PDF manual and plugin archive were rebuilt. No changes were committed.

## Word follow-up (2026-11-14)

The user then requested the same authoring support in Word. The Typeset
command now opts into shared parsing and carries the explicit shared group
into the existing common planner and OOXML table writer. Trees retain the
shared-input refusal. Converter fixtures now rebuild successfully in the
Word round-trip tests rather than asserting a refusal.

New Word tests exercise the real task-pane command with a minimal Office.js
boundary, verifying invalid-input rejection before insertion, success after
rejection, shared serialization, and number-bookmark takeover. Package tests
cover fresh input and converter tables, repeated narrow/wide cycles, gaps,
grouped phrases, rich text and stable numbering. A reverse-reader regression
fix drops physical filler across all rows of each shared band rather than
turning it into additional variant slots.

The generated samples in `build/word-shared-review/` include wide and narrow
DOCX, Flat OPC XML, PDF, and narrow reversed LaTeX. Both DOCX samples pass
ECMA-376 validation. LibreOffice opens/renders them; narrow PDF coordinate
checks pass for shared slots, hanging judgments, annotations, translation
indent and page bounds. Reverse conversion preserves variants, shared slots
and the reference.

Validation logs: `/tmp/lx-word-js-final.log`,
`/tmp/lx-word-check-final.log`, `/tmp/lx-word-manual.log`,
`/tmp/lx-word-render.log`. The PDF manual was rebuilt and all generated
constants remain synchronized. No connected Word document session was
available; live Word rendering, insertion and desktop Undo remain unverified.
`WORD-TESTS-TODO.md` records those host checks. No changes were committed.

Word follow-up results: all 13 JavaScript test files pass. The final Python
run reported 615 passed and one LibreOffice process failure in an appendix
PDF conversion while another suite was running. An isolated rerun of all
appendix and section-reference tests passed (15 tests), including the failed
case and two similar failures from the earlier overlapping run. The new
shared-band reverse regression passed. Both Word-generated DOCX samples
validate; narrow PDF coordinate and reverse-conversion checks pass.
Lint, whitespace checks and constant synchronization pass. Isolated retry
log: `/tmp/lx-word-lo-retry.log`.
