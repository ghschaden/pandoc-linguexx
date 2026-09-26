# pandoc-linguexx — plan: a Word add-in and an OnlyOffice plugin

**Verdict: worth building, and it should start with experiments, not code.**
What `LinguExx.bas` does inside Writer — typeset the selected lines as a
numbered example with live fields, take it back apart, refer to it — can
plausibly be done in Word (Office.js) and in OnlyOffice (its plugin API),
from **one JavaScript core** with a thin layer per host. Whether it can is
decided by four questions about fields and tables that no documentation
settles; Phase 0 answers them by measurement before anything else is built.

This is a plan, not a commitment. Nothing below is built.

## What is known, and how well (read 2026-09-26; NOT yet verified here)

These come from the vendors' documentation and issue trackers. They are
not "Verified facts" in the sense of `plan.md` and `plan-docx.md`: none
has been run. Phase 0 turns each one into a measurement or refutes it.

1. **Office.js can insert fields, but not reliably on the web.**
   `Range.insertField(location, Word.FieldType.seq | .ref, ...)` exists
   since requirement set WordApi 1.5. The fields guide says Word on
   Windows and Mac support every `FieldType` except `others`. Word on the web does
   not: [office-js#3623](https://github.com/OfficeDev/office-js/issues/3623)
   reports `InvalidArgument` for `ref` on the web and closed as a
   *feature request*, not a bug. So `insertField` cannot be the path
   everywhere.
2. **Office.js can insert raw OOXML.** `Range.insertOoxml()` takes a flat
   OPC package — which is what `emit_docx` already writes: a `w:tbl` with
   `gridSpan`, `SEQ`/`REF` field runs with correct cached values, and
   `Lx*` style references. Word 365 reads that markup correctly
   (`WORD-TESTS-TODO.md`). Unknown: whether `insertOoxml` keeps the fields
   as fields, on the web in particular, and what it does with a style
   the document already defines.
3. **OnlyOffice has `ApiRange.AddField(code)` since 9.0** (June 2025): a
   field from its instruction text, e.g. `'SEQ NumEx \* ARABIC'`. Unknown:
   what cached value it gets, whether it counts, and whether a `REF` to a
   bookmark resolves. OnlyOffice 9.4 does not recalculate fields on open
   (plan-docx.md, fact 12), so a wrong cache is what the reader sees.
4. **OnlyOffice has no documented way to insert OOXML.** Its insertion
   routes are the builder API (`Api.CreateTable`, `MergeCells`, widths,
   styles), `PasteHtml` (no fields), and `InsertContent` of its own
   objects. So the OnlyOffice emitter builds the table object by object,
   the way the Basic macro does, and cannot reuse the Word markup.
   `Api.CreateTable` changed its argument order in 9.4 — `(rows, cols)`,
   formerly `(cols, rows)` — which is the kind of drift to pin a version
   against.
5. **OnlyOffice's builder API also runs headless** as ONLYOFFICE Document
   Builder, from the same scripts. If that holds, the OnlyOffice emitter
   can be tested in CI by building a `.docx` and reading it back with the
   tools that already check the converter's `.docx` output — the only
   route found so far to an editor test that needs no GUI.

## Verified facts — S7 (2026-09-26, Document Builder 9.4.0; do not re-litigate)

Run headless in Document Builder, which executes the same builder API a
plugin calls. The saved `.docx` was read back as XML, rendered by
Document Builder to PDF and by LibreOffice to PDF; all three agree.
**Confirmed in OnlyOffice Desktop 9.4.0** (the Flatpak), where a plugin
actually runs: `spikes/s7_onlyoffice_fields.js` pasted as a macro into a
blank document showed (1) NEW (2) A (3) B (4) C and "See (4) and (2).",
and the `.docx` it saved has the same fields, caches and bookmarks as the
Document Builder one, element for element.

1. **`AddField('SEQ NumEx \* ARABIC')` makes a real complex field** —
   `fldChar begin / instrText / separate / result / end` — and it counts
   on insertion: three examples read 1, 2, 3 with no update call.
2. **An example inserted in front leaves the rest stale** (1, 1, 2, 3)
   **until `ApiDocument.UpdateAllFields()`**, which renumbers them (1, 2,
   3, 4) and rewrites the cached values in the file. So the plugin calls
   it after every insertion. There is no narrower call — ApiRange and
   ApiParagraph have no update method — and after an insertion every
   later number and every reference to one can change, so a
   document-wide update is needed anyway, as in Word (Ctrl+A, F9). Its
   cost: a user's DATE fields and tables of contents refresh too.
3. **`AddField` deletes whatever is in its range, bookmarks included.**
   A bookmark put on the placeholder first is gone afterwards. It returns
   `true`, not the field, so there is no handle to bookmark after.
4. **The bookmark that works wraps the whole field**: every run strictly
   between the `(` and `)` runs, joined with `ApiRange.ExpandTo`, then
   `AddBookmark`. A `REF exC \h` then gives the bare number, and after an
   insertion plus update "See (3) and (1)" became "See (4) and (2)" — the
   renumbering the tool exists for. The same shape as fact 3 of
   plan-docx.md, arrived at from the other side.
5. **Bookmarking only the result run does not survive**: the update
   rewrites the result and `GetAllBookmarksNames()` comes back empty,
   leaving "Error! Reference source not found." in the text. Bookmarking
   by character position (`GetRange(s, e)`) is unusable: a field's
   characters count as positions but not as text, so the displayed
   number has no position of its own.
6. **The field and bookmark markup is schema-valid.** `validate_docx.py`
   finds nothing in `document.xml` but Word's own extension attributes
   (`w14:paraId`, `mc:Ignorable`), which Markup Compatibility permits and
   the validator does not strip. All ~800 real complaints are in
   OnlyOffice's *default* `styles.xml` (element order in `pPr`,
   `tcBorders`) — present in every file OnlyOffice saves, not added by
   this code, and a Word-repair question for OnlyOffice rather than for
   the plugin.
7. **Document Builder quirks that cost time**:
   - Uncaught script errors exit 1 with no message; wrap the body in
     `try` and write the error into the document.
   - A `builder.*` line is executed as a command of its own and cuts the
     JavaScript around it, so `builder.SaveFile` inside a block is a
     syntax error. Keep `builder.*` lines at top level.
   - A run must be in the document before `GetRange()` works, so tables
     and paragraphs are placed first and filled afterwards.
   - `Api.CreateTable(rows, cols)` inserted by `Push` gets an empty
     paragraph after it; one inserted by `AddElement` does not.
8. **`AddElement` can put two tables edge to edge** — seen in the
   desktop editor, where NEW and A were drawn as one block, and in its
   file as `tbl, tbl` with no `w:p` between. OnlyOffice keeps them
   apart; Word joins adjacent tables into one (measured in S6, fact 3).
   So the plugin always inserts a paragraph after an example it places,
   and a test asserts that no two example tables are siblings.

**S7 gate: passed**, headless and in the desktop editor. The OnlyOffice
half proceeds.

## Verified facts — S8 (2026-09-26, Document Builder 9.4.0)

The target is the converter's own table for "il mio libro" in
`tests/e2e/word-sample.tex`: 6 columns of 624/189/391/472/582/7380
twips, fixed layout, zero cell margins, no borders, spacer rows spanning
6, a translation spanning 4, a named paragraph style on every cell. The
same table was built through the builder API and both files rendered by
OnlyOffice (Document Builder → PDF) and by LibreOffice; positions are
read with `pdftotext -bbox`, in twips from the example number.
**Confirmed in OnlyOffice Desktop 9.4.0**: `spikes/s8_onlyoffice_table.js`
run as a macro — into the S7 document, as it happened, where the example
continued the numbering as (5) and its reference read (5) — and saved.
The editor's file keeps the corrected grid (624/189/391/472/582/7380),
the merged widths, `none` borders and fixed layout; LibreOffice renders
it at 813/1203/1676, the converter's positions. The editor does not
rewrite the grid from its own layout on save.

1. **The API sets everything but the grid.** `SetWidth("twips")`,
   `SetTableLayout("fixed")`, `SetTableCellMargin*(0)`, per-cell
   `SetWidth`, and `MergeCells` all land in the XML as asked — but
   `w:tblGrid` stays at six default 2 cm columns (1134 each), and a
   merged cell keeps its first cell's `tcW` (624 where 9638 is meant).
2. **OnlyOffice lays out from the cells, LibreOffice from the grid.** So
   that table renders perfectly in OnlyOffice (813/1204/1676, as the
   converter's) and at 3212/4819/6425 in LibreOffice — six equal
   columns. A file the plugin writes is read by other people's software,
   and Word is expected to follow the grid of a fixed table as
   LibreOffice does — expected, not tested here. **This
   is the finding of S8: "looks right in OnlyOffice" proves nothing about
   the file.**
3. **The grid can be written through JSON.** `ApiTable.ToJSON()` carries
   `tblGrid` explicitly; setting it (and each cell's `tcW` to the sum of
   its span) and rebuilding with `Api.FromJSON()` + `ReplaceByElement`
   gives the converter's grid, and both renderers then agree with the
   converter's table to the twip (LibreOffice 813/1203/1676, as it
   renders the converter's own file). One merged width comes back 8825
   for 8826, a rounding in the JSON path.
4. **`FromJSON` loses paragraph styles and adds "Table Grid".** So the
   order is: structure and merges → grid through JSON → then styles,
   text, the S7 number field and its bookmark. And
   `SetTableBorderAll("none", 0, 0, 0, 0, 0)` after the rebuild, or the
   table is drawn with single black lines in both renderers. Built in
   that order, one table carries the grid, spans, styles, a `SEQ` field
   with a whole-field bookmark and a working `REF`.
5. **Risk carried forward:** the JSON is an internal format (keys like
   `reviewInfo`, `bPresentation`) that OnlyOffice does not document as
   stable. The plugin patches two keys of it and nothing more, and a
   test must pin the grid in the saved file so that a change in 9.x
   fails loudly.
6. **Style IDs are numeric.** `CreateStyle("LxExampleCell")` writes
   `w:styleId="697"` with `w:name="LxExampleCell"`. The name is what
   Word's Styles pane and a round trip go by, but the converter writes
   ID = name: in a document the converter made, the plugin must find the
   existing style by name (`GetStyle`) rather than create a second one.
   Not yet tested. The IDs are not even stable in form: Document Builder
   wrote `697`, the desktop editor `1_363`.

**S8 gate: passed**, headless and in the desktop editor — by the JSON
route, whose stability is the risk in fact 5.

## Verified facts — S6, Word on the web (2026-09-26)

Run by the user in Word on the web through Script Lab, with the snippet
`spikes/s6_word_snippet.py` generates: the converter's own `--to docx`
markup for `tests/e2e/word-sample.tex` — five example tables, the
cross-reference paragraph, `styles.xml` — packed as a flat OPC package
for `Body.insertOoxml`. Each step reports tables, fields (code and
displayed result), bookmarks and `Lx` styles back through the API.
**Word desktop was not tested, on purpose** — see the decision after
fact 5.

1. **Fields, bookmarks and styles survive `insertOoxml`.** All nine
   fields arrived as fields with their cached values (SEQ 1–5; REF 1,
   2, 5, 1), all five bookmarks, and all six `Lx*` paragraph styles.
   Word laid the examples out correctly: glosses under their words, the
   judged sub-example aligned, `[CP]` in its own column. The prose
   paragraph took Word's default face, since the converter's face is on
   the document defaults and those are not carried — for an add-in,
   which must not restyle the user's body text, that is right.
2. **`insertOoxml` into a blank document inserted everything and then
   threw** `GeneralException: Can't find the inserted content. Please
   refresh the page for the result.` After that, **every** further
   `insertOoxml` failed — at Start, at End, before the first paragraph,
   with or without a styles part, even a single paragraph holding one
   field — with `unknown`, `InvalidArgument`, and once a JavaScript
   crash inside Word (`Cannot read properties of null (reading 'Tcb')`).
   **After reloading the page, the same insertions worked without
   error.** So an insertion error leaves the page out of step with the
   document; the add-in must treat any error as "reload before
   anything else", and check the document rather than trust the call.
3. **Word joins adjacent tables.** The five example tables, which the
   converter writes with nothing between them, came back as **one table
   of 22 rows**. A table followed by a paragraph stayed separate (NEW,
   inserted with a paragraph after it: `tables: 2, rows 3,22`). The
   layout survives, since each row keeps its own widths, but in Word
   they are one object. **This is a finding about the converter too:**
   every `--to docx` document with consecutive examples is one table in
   Word. Not yet decided whether that matters enough to change
   `emit_docx`.
4. **Word on the web does not recalculate fields, and will not let an
   add-in do it.** A `SEQ` inserted in front kept its placeholder "0";
   a copied example kept its "1"; `Field.updateResult()` on every field
   ran **without error and changed nothing**. Writing the numbers by
   hand — `Field.result.insertText(n, "Replace")` — is refused with
   `NotAllowed: The action isn't supported by Word in a browser`.
5. **The numbering can be computed in the add-in.** `Body.fields` comes
   back in document order, and `Field.result.getBookmarks(true, true)`
   finds the whole-field bookmark round each `SEQ`; the map it gave
   (S6New→1, S6Seq→2, NumEx0…4→3…7) is exactly the right renumbering.
   Only writing it is refused (fact 4).

**S6 on the web: the gate's narrower case.** Examples go in intact, but
on the web their numbers are frozen at what was inserted. The web
promise is therefore "examples and live fields, renumbered by
LibreOffice on open, or by Word desktop on Ctrl+A, F9" (the latter as
plan-docx.md fact 15 found for the converter's files). Untested and the
last web route: replacing each whole field through `insertOoxml` at its
bookmark's range, which is the call fact 2 shows to be fragile.

**Decision (2026-09-26): no desktop test as a gate.** The web fixes the
design whatever desktop does. An add-in that must work in Word on the
web must work where nothing renumbers, so nothing in it may depend on
renumbering; a desktop test could only add a convenience on top, and
that convenience can be discovered at run time (call `updateResult()`,
read the results back) rather than settled in advance. Desktop Word is
tested in Phase 2 as ordinary testing of a working add-in, not as a
spike. What desktop Word does with these fields on Ctrl+A, F9 is
already known for the converter's markup (plan-docx.md fact 15).

## The shape

The markup rule from `plan-docx.md` holds a third time: **the arithmetic
is shared and the markup is not.**

- **`addin/core/`** — plain ES modules, no build step, no npm
  dependencies. Parses the typed lines into items (markers, judgment
  marks, braces, `\exannot` labels, quoted translation), measures words,
  packs bands, and returns a table plan — the JavaScript counterpart of
  `LxParseItems` … `LxPackBands` and of `emit_base.plan_table()`. It knows
  no markup, and a test enforces that, as one already does for
  `measure` and `emit_base`.
- **`addin/word/`** — renders the plan as OOXML (a JavaScript twin of
  `emit_docx`'s markup) and inserts it with `insertOoxml`; the Office.js
  manifest and task pane.
- **`addin/onlyoffice/`** — renders the plan through the builder API
  inside `callCommand`; `config.json`, the plugin page, a `.plugin`
  package from `make onlyoffice`.

**Constants are generated, not copied**, exactly as for the macro:
`tools/sync_macro.py` learns to write `addin/core/constants.js` from
`styles.py` (style names, lengths, `measure._ADVANCE`), and a pytest test
fails on drift. Python checks the generated file as text, so this needs
no Node in `make test`.

**Measuring.** The core estimates with `_ADVANCE`, as the converter does,
rather than measuring with `canvas.measureText`. A canvas in a web page
measures in the *browser's* fonts, which in Word on the web and in
OnlyOffice need not be the fonts the document is drawn in; the estimate is
deterministic and already checked against Liberation Serif
(`make advances`). Measuring for real is a later option once Phase 0 says
how far apart the two are. Small caps are estimated as drawn, as
`measure.py` does.

**Rejected: running the Python in the browser (Pyodide).** It would reuse
`emit_docx` itself, but it downloads megabytes into every task pane, starts
in seconds, and still needs a JavaScript layer to read the selection.

## Phases

### Phase 0 — settle the four questions (spikes, ~2 days)

Each is a throwaway script under `spikes/` whose answer is recorded here
under "Verified facts", as in the other two plans. Nothing after Phase 0
starts until its gate is decided.

- **S6 — Word, `insertOoxml`.** Insert the `emit_docx` output for
  `tests/e2e/word-sample.tex` (tables, `SEQ`, bookmarked `REF`) through a
  Script Lab snippet, in Word on the web **and** Word 365 desktop. Record:
  are they still fields (Alt+F9)? Is the cached value kept? Does inserting
  an example *before* existing ones renumber them — on its own, or only
  after `body.fields` / `Field.updateResult()`? Do `w:pStyle` references
  bind to styles the document already has, or do they bring their own?
  Measure the column positions off an exported PDF against the
  converter's own `.docx`, the way plan-docx.md did.
- **S7 — OnlyOffice, fields.** In OnlyOffice 9.4: `AddField('SEQ NumEx')`
  three times — do they read 1, 2, 3, and after an insert before them, do
  they renumber (on their own, or on F9)? A bookmark round the field, and
  a `REF` to it: does it give the bare number? Save as `.docx` and read
  `word/document.xml`: are they `w:fldSimple` / `w:fldChar` with the right
  cache?
- **S8 — OnlyOffice, tables.** Fixed layout, per-column widths, zero cell
  margins, merged translation cells, paragraph styles on cells. Measure
  the rendered columns against the requested widths, as fact 4 of
  plan-docx.md did for OOXML.
- **S9 — Document Builder headless.** Can the S7/S8 script run in
  `docbuilder` unmodified and save a `.docx`? If yes, the OnlyOffice layer
  gets CI tests; if not, it is tested by hand like the macro before CI
  ran it.

**Gate.** Word proceeds if S6 shows live, renumbering fields on desktop.
A web-only failure narrows the promise ("Word desktop; on the web the
numbers are fixed until opened on desktop") rather than stopping the work,
and the README says so. **Decided on the web results (S6): Word
proceeds, designed for a host that never renumbers** — see the decision
under S6 and "Numbering without recalculation" in Phase 2. OnlyOffice proceeds if S7 shows a `SEQ` with a
correct cache. Without that, the plugin would produce numbers that are
text by another route, which is the one thing this project exists not to
do, so OnlyOffice stops there.

### Phase 1 — the core — DONE (2026-09-26)

`addin/core/`: `constants.js` (generated), `measure.js`, `parse.js`,
`plan.js`, and `node --test` suites under `core/test/` — `make js-test`,
161 tests, and a CI job of its own. No dependencies, no build step.

**Two oracles, and the core is held to both exactly.**

- **The parse is the Writer macro's.** The typed-line cases moved out of
  `tools/run_macro_test.py` into `tests/fixtures/typed-examples.json`
  (every group the harness had, each case keeping the "why" it was added
  for), and the harness reads them from there. A new Basic entry point,
  `ParseLinesQuiet`, runs `LxParseItems` on lines and returns the items
  without building anything; the macro suite records its answer for every
  fixture as the file's `parsed` section (`LINGUEXX_UPDATE_GOLDEN=1
  python3 tools/run_macro_test.py`) and fails when the macro stops giving
  it. `parse.test.js` requires `parse.js` to give the same, case by case.
- **The plan is the converter's.** `tools/addin_oracle.py` builds the
  converter's IR from each recorded parse, runs `BaseEmitter.prepare()`
  and `plan_table()` at 17, 12 and 7 cm, and writes
  `tests/fixtures/typed-examples.plans.json`; `tests/test_addin_core.py`
  fails when that golden is stale. `plan.test.js` requires `planTable` to
  give the same bands, spans, warnings and widths — `deepStrictEqual`, no
  tolerance. It does, for 38 fixtures at three widths.

What the port taught, each found by that exact comparison or by a
mutation surviving it:

1. **Python's `sum()` of floats is compensated since 3.12** (Neumaier, as
   `Python/bltinmodule.c` does it). A plain JavaScript loop came out one
   unit in the last place away in half the fixtures. `measure.pySum`
   reproduces it, used exactly where the Python calls `sum()` and nowhere
   else — the `x += w` loops in `Grid` are plain addition in both. The
   drift test skips on Python < 3.12, where the golden would not reproduce.
2. **LibreOffice Basic's `InStr` compares case-blind by default**, so the
   macro finds `\EXANNOT{..}`; `pullAnnot` matches that.
3. **Basic resolves a `Const` in source order** — known, and still cost a
   run: `ParseLinesQuiet` placed beside `GlossSelectionQuiet` returned
   Empty ("Variable not defined: IT_TIERS", visible only once it trapped
   its own errors, which it now does).
4. **The converter reads a cell as LaTeX**, so a typed `'` would be
   measured as `’` and `--` as an en dash. The oracle escapes LaTeX's
   specials and then requires the converter's own reader to give the typed
   text back, failing loudly rather than comparing two different examples.
5. **Ten deliberate mutations of the core; three first survived**, each
   a gap in the fixtures: a lone judgment mark (`* Das Kind`), the guard
   against an empty band, and the annotation gap below `min_col_cm`. The
   last two are reachable only when a capped word is wider than the space
   left, hence the 7 cm width and the `PLAN_CASES` fixtures. All ten now
   fail at least one test.

**The add-in's selection rule is the macro's, not the converter's.**
`prepareSelection` reserves the judgment column always and sizes the
number for "(00)", as `LxLayOut` does: an add-in, like the macro, sees one
example and not the document. It is unit-tested, not held to an oracle —
the macro measures a real font and the core estimates, so there is no
exact answer to compare with.

**A converter bug the port exposed, fixed:** `emit_docx` summed a cell's
`w:tcW` from the columns at the word's *index*, which is its grid column
only in a one-band, one-body table. Word and LibreOffice lay out from
`w:tblGrid` and never showed it; OnlyOffice lays out from the cells (S8
fact 2) and drew a banded example as letters in slivers. Now summed from
the columns the cell actually covers; `test_every_cell_is_as_wide_as_the_
columns_it_spans` failed before and passes after, and OnlyOffice and
LibreOffice then agree on that example to 0.1 pt.

### Phase 2 — Word MVP — BUILT, first live test passed (2026-09-26)

*Typeset selection*, *Insert reference*, and the `Lx*` styles, which
travel in the inserted package's styles part (S6 fact 1). They are sent
only when `getStyles()` lacks one: whether re-sending a styles part the
document already has is harmless was never isolated from the page-state
failure of S6 fact 2. The markup is a port of
`emit_docx`, checked by a differential test: the same example through
Python and through JavaScript gives the same `w:tbl` modulo ids. Selection
formatting (italics, small caps, the three new character styles) is read
from `Range.getOoxml()` runs, not from the text, because the text loses it.
The macro learned this the hard way (`check_small_caps`).

**Numbering without recalculation.** S6 showed that Word on the web
neither recalculates fields nor lets an add-in write their values, so
the design assumes a host that never renumbers, and gets better where
one does:

- **The new example is right when it is inserted.** Before inserting,
  the add-in counts the `SEQ NumEx` fields ahead of the insertion point
  (`Body.fields` is in document order, S6 fact 5) and writes that number
  into the cached value of the field it inserts. The example the user
  just made never shows a wrong number, on any host. This is the
  converter's rule — the cache is what some reader sees — applied at
  insertion time.
- **A new *Insert reference* is right when it is inserted**, by the same
  map: bookmark → number, cached into the `REF` it writes.
- **What goes stale is said, not hidden.** Inserting before existing
  examples leaves the later numbers and the references to them stale on
  a host that does not recalculate. The add-in then tries
  `updateResult()` on every field and reads the results back; if they
  now match the map, it says nothing. If they do not — Word on the web
  — it tells the user which examples are stale and how they renumber:
  "Word desktop: Ctrl+A, F9; LibreOffice: on opening". It never claims
  numbers it has not checked.
- **No renumbering by rewriting.** Writing field values is refused on
  the web (`NotAllowed`, S6 fact 4); replacing whole fields through
  `insertOoxml` is the call S6 fact 2 found fragile. Neither is used.

**Two rules from S6 for every insertion:**

- **A paragraph after every example.** Word joins adjacent tables
  (S6 fact 3), so the add-in never leaves an example table touching
  another, and a test asserts it.
- **Check, don't trust; reload after an error.** `insertOoxml` can
  insert and still throw, and an error leaves the page unable to take
  another insertion until it is reloaded (S6 fact 2). After every
  insertion the add-in reads the document back; after any error it
  stops, says what it found, and asks for a reload before doing
  anything else.

Hosted for development from a local HTTPS server and sideloaded; for use,
from a static site (GitHub Pages). The manifest points at it. Tested in
Word on the web and, once the add-in works, in Word desktop — where the
`updateResult()` branch above is the thing to watch.

**What was built.** `addin/word/`: `ooxml.js` (emit_docx ported),
`selection.js` (a selection's OOXML as tagged lines), `numbering.js` (the
rules above, as pure functions), `xml.js` (a small strict parser, since
Node has no DOMParser and the core takes no dependencies), `styles.js`
(generated by `make macro` from `styles_docx.styles_fragment()` — the very
styles the converter injects), the task pane, `manifest.template.xml`, and
`tools/serve_addin.py`, which serves `addin/` over HTTPS on localhost with
a self-signed certificate and writes `manifest.xml`. Nothing is published.
`node --test` covers it: 129 tests beside the core's 161.

**Held to the converter, string for string.** `tools/addin_oracle.py` also
records `DocxEmitter.example()` for every fixture at every width
(`typed-examples.docx.json`), and the add-in's `w:tbl` must be identical —
111 tables. Two things made that exact: Python's `round()` sends halves to
even (`pyRound`), and emit_docx's sums are compensated like every other.
The one substitution is the translation, which the converter draws through
LaTeX (a typed `'` becomes `’`) and the add-in leaves as typed; the golden
records the drawn text. Formatted runs, which no fixture has, were checked
end to end instead: an example with small caps, a Leipzig character style,
italic, bold and a subscript, built by the add-in, is schema-valid, and
rendered by LibreOffice its glosses start exactly under their words and the
mark hangs.

**Mutation-tested like the core**, and it found a real bug: a field
nested in another field's code (Word's `IF { MERGEFIELD }` idiom) had its
result read as text, because only the innermost field was asked whether it
was showing its result. Every enclosing field must be.

**Live, in Word on the web (2026-09-26):**

1. *Typeset selection* inserts a real example — number in field shading,
   bookmark, gloss under its words, translation row, no borders — with no
   insertion error, which S6's first insertion had.
2. **Inserted ahead of existing examples, it numbers itself right and says
   exactly what is stale.** In the S6 document (nine numbers, some stale
   from the spikes) the new example got (1), and the pane reported the
   eight later numbers and four references with their correct values. The
   first version listed every pair, a wall of text in a real document; it
   now counts, and lists only up to three.
3. *Insert reference* goes in **inline**, as a field in shading, with the
   right number. The list shows the numbers as they should be, not as
   shown.
4. **Word on the web is slow enough to be clicked twice**: one reference
   went in five times. The pane now disables every button while Word
   works. The list read every field twice; it reads them once.
5. The list previewed the first row of the *table*, which in a converted
   document is every consecutive example's (S6 fact 3), and nothing for a
   number outside a table. It now previews the number's own row, or its
   paragraph.
6. After the reference insertions the document would not take typing
   until switched to Viewing and back to Editing. Observed once, not
   diagnosed; it looks like S6 fact 2's out-of-step page in another form.
   If it recurs, it points at inline `insertOoxml` in particular.

Re-checked in Word on the web: the counted stale note ("9 example numbers
and 7 cross-references still show their old value") and one click giving
one reference both confirmed. The previews (5) were not reported on.

Still to test: Word desktop (the `updateResult()` branch), the previews,
and a document whose body face is Times — the font note fired in both
live documents, which use a theme face.

### Phase 3 — OnlyOffice MVP — DONE, confirmed in OnlyOffice Desktop 9.4.0 (2026-09-26)

The same two commands through the builder API. Tested with Document
Builder in CI if S9 passed, otherwise by a script run by hand, like
`run_macro_test.py` before it had a CI job.

**What was built.** `addin/onlyoffice/`: `job.js` (pure: the editor's
report of a selection → tagged lines → the core's parse and plan → a
*job*, the example as plain data, styles included), `commands.js` (what
runs inside the editor through `callCommand`: self-contained functions,
input only through `Asc.scope`), the panel (`index.html`, `ui.js`,
`config.json` modelled on the bundled Typograf plugin). `make onlyoffice`
(`tools/build_onlyoffice.py`) joins the ES modules into one classic
script, `linguexx.js` — a plugin is loaded from local files, where module
loading is not to be relied on — and writes `dist/onlyoffice/{GUID}/` and
a `.plugin`. A node test holds the bundle to the modules.

**One row logic for both hosts.** The rows moved from `word/ooxml.js` into
`core/table.js` (no markup: which cell spans what, its width, its style,
whether it holds the number or text); `ooxml.js` now only serializes them,
and the 111-table comparison with the converter proved the move changed
nothing. The OnlyOffice layer builds the same rows. **The styles come from
one source too**: `job.stylesJob()` restates `STYLES_FRAGMENT` — the OOXML
the converter injects — as builder properties.

**S9, answered by use.** `make onlyoffice-test`
(`tools/run_onlyoffice_test.mjs`) runs the plugin's own editor code — the
shipped `linguexx.js` — in Document Builder: every fixture typed as
paragraphs, selected, and typeset into one document (37 examples and the
refusal refused), each table held to the Word layer's markup for the same
selection (grid, spans, widths to a twip, styles by name, text), numbers
1..37, whole-field bookmarks, fixed layout, no insets, no borders, and every
`Lx` style exactly as the converter defines it. A scenario adds what the
fixtures cannot reach: an example typed directly above another's table
(it must renumber at once and the tables must not touch), a reference
completed from a pasted placeholder, and formatted text compared exactly.
In CI as a job of its own (decided 2026-09-26): Document Builder pinned to
9.4.0 by version and SHA-256 and cached. The free build's watermark is a
page header ("Unregistered Version") that nothing in the test reads, and
the documents are thrown away; the risks that remained were the download's
— an unpinned "latest", a changed file, missing runner libraries — which
the pin and the checksum answer, and the first CI run settles the last.

**Mutation-tested: 13 breaks of `commands.js`, all caught** — after the
first run let three through (no renumbering, no paragraph after the table,
a format not applied), each a scenario that was missing. And a real bug:

- **The builder's `AddText` makes a run that INHERITS the previous run's
  formatting.** A plain ".3" after small-caps "pst" came out small caps,
  and a subscript after an `LxLeipzig` run took the style — the Writer
  macro's style leak (79e155f) in another API. Cells are now written with
  fresh runs (`Api.CreateRun` + `AddElement`), and the scenario compares
  every word's format exactly, plain words included; with the old code it
  fails on precisely those words. The test's own setup typed through
  `AddText` at first and so manufactured a leak of its own.

**Live, in OnlyOffice Desktop 9.4.0 (Flatpak), installed by copying the
built folder into the user's `sdkjs-plugins/`:** the panel opens from the
Plugins tab; two examples typeset, the one typed above numbered (1) and
the other renumbered to (2) without anyone updating fields; references go
in inline at the cursor through the pasted placeholder — the one path the
headless test cannot take — and read (1) and (2); the list shows both; the
font note fired correctly (Arial default).

### Phase 4 — Untypeset, in both — DONE, confirmed in Word on the web and OnlyOffice Desktop (2026-09-26)

Read a built table back into lines, by style name, as the macro does. The
macro's lessons carry over as tests from day one: the band mark, the
number that has to survive (`numex_ids`), and the character-style leak
fixed in `79e155f`. That bug looked right and was wrong. The
`MACRO_STYLES_NOT_SHARED` discipline carries over too: a style the add-in
cannot identify is a broken round trip.

**What was built.** `core/untypeset.js`: the macro's `LxReadTable`, ported
(trees aside), reading any host's table as rows of `{style, text}` — style
by name, text tagged. Word: `readExampleTable` and `untypesetPackage`
(`word/untypeset.js`), sharing one run reader with the selection reader;
OnlyOffice: `readExampleTable`/`writeLines` in the editor and
`untypesetJob` beside them. Out, the lines come back with the SAME number
field — bookmark name, shown value — then a tab, as `LxWriteLines` writes
it. Back in, **a number the selection leads with is taken over**, by the
macro's `LxTakeNumber` rules: its bookmark kept, its brackets dropped; two
numbers, or one part-way through, refused. Before, both hosts refused a
selection holding a number.

**Tested against the macro's own expectation.** All eight
`UNTYPESET_CASES` come back exactly as typed; every fixture, built and read
back, is the same example — at 17 and 7 cm, and built by the converter's
rule too, which is the only case where the text's first column is found
from the translation (a mutation there survived until that case was
added). In Word, typed → table → untypeset → read as a selection gives the
same example, the same number identity and the same formats, for every
fixture. In Document Builder, the example a reference points at goes out
and back in with its number taken over, its bookmark there once, its table
reading exactly as before — and the reference still reads 2.

**Refused on purpose:** a table holding several examples, which is what
Word makes of a converted document's consecutive examples (S6 fact 3).
Untypesetting "the table" there would take them all out as one.

**Live:** in OnlyOffice Desktop and in Word on the web, an example with a
reference to it, untypeset, edited and typeset again, kept its number and
the reference still resolved.

**Word on the web is slow**, and the add-in was part of why: after every
insertion it read every field and every field's bookmarks, and on the web
asked Word to update fields — which it ignores — and read them all again.
Now the audit is skipped when nothing can be stale (no example after the
insertion point, and a taken-over number kept its value — inserting at
the end, or editing in place), and on the web updateResult is not asked
for. Not yet measured live.

### The face an example is set in (2026-09-26)

**Found live:** in an Aptos document Word set the add-in's examples in
Times New Roman, and the Styles pane said why: `LxExampleCell` read
"Times New Roman, 12". The inserted package carried the Lx styles with no
document defaults, OOXML's implicit default face is Times New Roman, and
Word wrote the resolved face into the style on import.

- **The package now carries the document's own face and size as its
  defaults** (`ooxml.docDefaults`), whether or not the Lx styles travel,
  taken from the typeset lines themselves — Word reports the face resolved
  ("Aptos", not a theme slot). In a new document the example comes out in
  Aptos, the prose's face, as the converter's examples do in theirs
  (confirmed in Word on the web).
- **Aptos is measured.** It is 7–12% wider than Times, so columns
  estimated for Times would wrap it. Its advances were measured from
  Microsoft's own Aptos.ttf (Download Center 106087, fonts 4.40, Aptos 2.01)
  by `measure.measure_font_file()` — the converter's own method for an
  installed face — and committed as `measure._FACE_ADVANCE`, so it is
  estimated from its own metrics where it is not installed, CI included.
  `tools/measure_face.py` writes and checks that block; the font itself is
  not committed. The converter's `advances_for("Aptos")`, the add-in core
  (`advancesFor`, threaded through every width as Python's `Layout.advances`
  is) and both hosts use it; the oracle adds an Aptos layout for every
  fixture and the core matches it exactly (leaving the face out of the word
  widths fails 27 tests). OnlyOffice measures for the document's default
  face and size too.
- **Calibri, Arial, Cambria and Georgia are measured too** (the same day),
  from the Microsoft fonts installed on the measuring machine, and each
  checked against its free metric twin, so the numbers can be reproduced:
  Carlito is identical to Calibri in all 215 shared characters; Liberation
  Sans matches Arial but for "·"; Gelasio matches Georgia but for "¸" and
  "µ"; Caladea 1.001, the Google Fonts version, is NOT Cambria's twin (128
  of 201 characters differ), so Cambria rests on the original alone. All
  five are wider than Times, by 3% (Calibri) to 12%.
- **A face not measured** is estimated from Times's metrics, and the pane
  says so.
- **Not done:** repairing a document an earlier add-in version spoiled
  (its `LxExampleCell` already fixed at Times). Setting the style's font
  through Office.js had no effect on the web, and the attempt was removed;
  the manual fix is Styles ▸ LxExampleCell ▸ Modify ▸ the document's face.
  Only test documents are affected.
- The add-in reads back the face Word set the example in, and says so if
  it is not the one asked for.

### Phase 5 — say so — DONE (2026-09-26)

README section, `docs/guide-fr.md`, the "What it does not, and says so"
rows (trees; web limits if S6 finds any), and CLAUDE.md: a third copy of
the constants, where it is generated, and how its suite is run.

Done: "Writing examples in Word and OnlyOffice" in the README and Partie F
in the French guide — what the add-ins do, a table of what they do not
(Word on the web never renumbers; no trees; no layout dialog; a table of
several examples refused; documents spoiled by an earlier build; Word for
the desktop untried), and how to install them, with the one install path
actually tried said to be the one. The `.docx` section no longer says it
has never been opened in Word, which stopped being true on 2026-09-25, and
gains a row: Word joins a converted document's consecutive examples into
one table. CLAUDE.md was kept current phase by phase.

**Still open after the five phases**, each the user's to decide or to try:
Word for the desktop (the `updateResult()` branch); whether the converter
should put a paragraph between consecutive `.docx` examples -- decided and
done the same day: a 1 pt `LxExampleGap` paragraph, measured to move each
step between consecutive examples by 1.0 pt and nothing else; and
publishing either add-in, which the user has asked to wait. (Measuring the common
Office faces besides Aptos was done the same day.)

## Risks, and what would settle each

- **Word on the web drops or freezes fields** — S6. Mitigation above:
  narrow the promise, do not fake the numbers.
- **The three OOXML writers drift apart** (Python `emit_docx`, the
  JavaScript twin, and implicitly the macro's layout). Settled by the
  Phase 2 differential test and the Phase 1 shared fixtures, and by
  nothing less.
- **Estimated widths are wrong in a face other than Times.** The
  converter already has this and solved it by declaring the face
  (`b84e311`). The add-in inserts into a document whose face it does not
  choose, so it must read the paragraph's font and warn when it is not
  one `_ADVANCE` describes, until real measuring exists.
- **OnlyOffice's API moves under it** (the 9.4 `CreateTable` change).
  Pin a minimum version in `config.json`, and record it in the README the
  way the linguexx version is recorded.
- **What is installed here** (checked 2026-09-26). Node 26.8.1 (pacman).
  OnlyOffice Desktop 9.4.0 as a **Flatpak** (`org.onlyoffice.desktopeditors`,
  system install): no command on the PATH, it runs sandboxed, and its user
  data lives under `~/.var/app/org.onlyoffice.desktopeditors/`. S7 has to
  find where that build loads a hand-installed plugin from before anything
  else. **Document Builder 9.4.0** is unpacked under
  `~/.local/opt/documentbuilder/` from the release archive (no Arch
  package exists). Its launcher `usr/bin/onlyoffice-documentbuilder`
  hard-codes `/opt/onlyoffice/documentbuilder`, so call
  `opt/onlyoffice/documentbuilder/docbuilder SCRIPT.docbuilder` directly,
  with `LD_LIBRARY_PATH` set to that directory. A five-line smoke script
  built a `.docx` in ~15 s.
- **The free Document Builder watermarks** ("license is invalid!" on
  stderr, exit 0 regardless). Measured: the mark is a page *header*
  (`word/header1.xml`, "Unregistered Version" twice) referenced from
  `sectPr`; `word/document.xml`'s body held exactly the one test
  paragraph. So checks on the body XML are unaffected; a rendered-PDF
  check must ignore the header band. Whether a watermarking tool may run
  in CI is the user's call, not S9's.
  Word 365 desktop is available (it ran the .docx tests); Word on the web
  needs only a browser.

## Out of scope — do not implement without asking

- **Trees and movement arrows.** Office.js draws shapes poorly and the
  macro's tree code is a quarter of it. Revisit after Phase 4.
- **The layout dialog.** Defaults come from `styles.py`; a settings pane
  is later.
- **VBA.** Windows/Mac desktop only, has no text-width API, and would be
  a fourth implementation.
- **Publishing** to Microsoft AppSource or the OnlyOffice plugin
  marketplace: review processes, accounts and support promises are the
  user's decision.
- **A shared markup abstraction** over OOXML strings, the builder API and
  ODF. Same reasoning as plan-docx.md: they share arithmetic, not markup.
- **npm dependencies or a bundler.** The core is small enough to be plain
  modules; a toolchain is a maintenance cost this project has so far
  avoided entirely.
