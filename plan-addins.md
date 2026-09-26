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
   apart; Word joins adjacent tables into one on open. So the plugin
   always inserts a paragraph after an example it places, and a test
   asserts that no two example tables are siblings.

**S7 gate: passed**, headless and in the desktop editor. The OnlyOffice
half proceeds.

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
and the README says so. OnlyOffice proceeds if S7 shows a `SEQ` with a
correct cache. Without that, the plugin would produce numbers that are
text by another route, which is the one thing this project exists not to
do, so OnlyOffice stops there.

### Phase 1 — the core (~3 days)

Port the parse, the bands and the plan from `LinguExx.bas` to
`addin/core/`. **The macro's typed-line cases become shared fixtures**:
`CASES`, `SUB_CASES` and `UNTYPESET_CASES` move out of
`tools/run_macro_test.py` into `tests/fixtures/typed-examples.json`, and
both the macro suite and `node --test addin/core` read them. The two
implementations then answer the same inputs, and a case added for one is
a case for both.

Differential check against the converter: for each fixture there is an
equivalent linguexx source. The core's plan must agree with
`plan_table()` on the band breaks and span patterns. Widths may differ
only by the difference between measuring and estimating, and here both
estimate, so they should agree exactly.

New tooling: Node, only for `make js-test`, never for `make test`. CI gets
a job of its own, like the macro's.

### Phase 2 — Word MVP (~4 days)

*Typeset selection*, *Insert reference*, and the `Lx*` styles, injected
on first use as `postprocess_docx` injects them. The markup is a port of
`emit_docx`, checked by a differential test: the same example through
Python and through JavaScript gives the same `w:tbl` modulo ids. Selection
formatting (italics, small caps, the three new character styles) is read
from `Range.getOoxml()` runs, not from the text, because the text loses it.
The macro learned this the hard way (`check_small_caps`).

Hosted for development from a local HTTPS server and sideloaded; for use,
from a static site (GitHub Pages). The manifest points at it.

### Phase 3 — OnlyOffice MVP (~4 days, only if the S7 gate passed)

The same two commands through the builder API. Tested with Document
Builder in CI if S9 passed, otherwise by a script run by hand, like
`run_macro_test.py` before it had a CI job.

### Phase 4 — Untypeset, in both (~3 days)

Read a built table back into lines, by style name, as the macro does. The
macro's lessons carry over as tests from day one: the band mark, the
number that has to survive (`numex_ids`), and the character-style leak
fixed in `79e155f`. That bug looked right and was wrong. The
`MACRO_STYLES_NOT_SHARED` discipline carries over too: a style the add-in
cannot identify is a broken round trip.

### Phase 5 — say so (½ day)

README section, `docs/guide-fr.md`, the "What it does not, and says so"
rows (trees; web limits if S6 finds any), and CLAUDE.md: a third copy of
the constants, where it is generated, and how its suite is run.

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
