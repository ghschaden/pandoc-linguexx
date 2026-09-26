# pandoc-linguexx — notes for Claude

`linguexx2odt` converts a LaTeX document containing
[linguexx](../linguexx) examples into a LibreOffice Writer file **in which
every example number is a live field**, so inserting an example in Writer
renumbers the rest and cross-references follow. Everything that is not an
example is converted by pandoc.

There is a second deliverable in the same repository: `LinguExx.bas`, a
Writer macro that formats glossed examples inside Writer with no LaTeX at
all. It duplicates the converter's constants on purpose — see below.

A third is being built: a Word add-in and an OnlyOffice plugin over one
JavaScript core, `addin/`. `plan-addins.md` is its plan and records what
the spikes measured; Phase 1, the core, is done, and Phase 2, the Word
add-in (`addin/word/`), is built and has passed a first live test in Word
on the web. `python3 tools/serve_addin.py` serves it over HTTPS on
localhost and writes the `manifest.xml` Word's "Upload My Add-in" wants.

## Environment
- Python ≥ 3.10, standard library only. `pandoc ≥ 3.0` (the JSON AST is a
  versioned interface), LibreOffice for the rendering half, poppler for
  reading the result back.
- Node ≥ 18 for `make js-test` and nothing else: the add-in core is plain
  ES modules with no dependencies and no build step, and `make test` stays
  Python-only.
- **Two different path questions, easily conflated.** *pytest* needs no
  `PYTHONPATH`: `pyproject.toml` sets `pythonpath = ["src"]`, so plain
  `pytest` works, and a whole session was prefixed with `PYTHONPATH=src`
  before anyone read the config. *Running the module* does need it, this
  being a src-layout project:
  `PYTHONPATH=src python3 -m linguexx2odt paper.tex -o paper.odt`.
  Asserting the first about the second is an overclaim that reached the
  README before a probe caught it.
- `.venv/bin/linguexx2odt` may exist and refuse to run: pCloud syncs this
  checkout and does not preserve the executable bit. `make venv` rebuilds
  it; `python3 -m linguexx2odt` sidesteps it.
- Commits are **SSH-signed through 1Password**. When it is locked, `git
  commit` fails with "failed to fill whole buffer" and only the user can
  unlock it. `git commit --dry-run` does NOT sign, so it proves nothing
  about whether signing works — do not use it as the test.

## Make
`make check` is lint plus suite, which is what CI runs. `make test`,
`make js-test`, `make lint`, `make macro`, `make oxt`, `make advances`,
`make venv`, `make clean`. The Makefile's header says what each is for.

## Verification — non-negotiable
- **Measure the output; do not reason about it.** Every layout claim in
  this repository was read off a rendered PDF (`soffice --convert-to pdf`,
  then `pdftotext -bbox`) or off the emitted `content.xml`. An `\exannot`
  column was one em out of place in a version that looked perfectly
  correct in the source; the number came from measuring.
- **Check against linguexx, not against intent.** The question is never
  "is this reasonable" but "is this what linguexx renders". Build the same
  document with `TEXINPUTS=../linguexx: pdflatex` and compare coordinates.
  `\exannot` sits at 12.750 cm on a 17 cm block because that is where
  linguexx puts it, measured.
- **A golden is read before it is committed.** `LINGUEXX_UPDATE_GOLDEN=1
  pytest tests/test_extract.py` regenerates `tests/golden/*.json`;
  regenerating without reading records whatever the code now does,
  including the bug. When a field is added to the IR every golden
  changes — read the diff and confirm it is only the new key.
- **A new test is run against the old code.** A test that passes before
  the fix tests nothing. Every assertion added here has been shown to fail
  on the previous commit.
- `make test` before delivering. A missing pandoc or LibreOffice used to
  take 28 tests — every end-to-end one — out of the run and leave the exit
  code at 0; `tests/test_tooling.py` now fails instead and names them.
  `LINGUEXX2ODT_ALLOW_MISSING=1` turns that back into a skip for a run you
  know is partial. CI may not set it, and a test asserts that.

## Two targets, one IR
`--to odt` is the complete one; `--to docx` (plan-docx.md, Phases 1–4) does
numbers, references, the gloss grid and the named styles. The split is
deliberate and worth keeping:

- **Shared**: `extract.py` and `ir.py` (the parse), `measure.py` (widths,
  `Grid`, `_ADVANCE`), and `emit_base.BaseEmitter` — `prepare()`,
  `_bands()`, the lead widths, and `plan_table()`, which returns a
  `TablePlan` of pure measurements with no markup in it.
- **Not shared**: the markup. `emit_odt` and `emit_docx` render the same
  plan in different vocabularies and are not an abstraction over each
  other. A test enforces that `measure` and `emit_base` name no markup at
  all: an emitter reaching for `table:` in format-agnostic code breaks
  nothing today and breaks the other target the day it is written.
- An emitter registers itself with `@register("name")` and is reached
  through `emitter_for()`. `RAW_FORMAT` and `reference()` are what the
  inject pass asks it for — **`RAW_FORMAT` must be a `ClassVar`**: annotated
  plainly on a dataclass it becomes a field, every instance takes the base
  class's empty default, and every `RawBlock` goes out tagged `""`.

## Architecture invariants
- **Examples are never pandoc `Table` AST nodes.** Each becomes one opaque
  `RawBlock` — `opendocument` or `openxml` — that this code controls
  completely: column widths, merged cells, fields, styles. `plan.md`
  records why, under "Verified facts"; that section is not to be
  re-litigated without re-running its spikes.
- **Numbers are fields, not text.** `text:sequence` and
  `text:sequence-ref` in ODF; `SEQ` and `REF` in OOXML. That is the entire
  point of the tool: a number that is text renumbers nothing.
- **In .docx the cached value must be correct.** A field carries the text a
  reader shows when it does not recalculate, and readers differ —
  LibreOffice recalculates on open, OnlyOffice 9.4 does not. The cache is
  not a hint somebody's reader will fix; it is what somebody sees.
- **OOXML spans by `w:gridSpan`, with no covered cells.** ODF emits a
  `covered-table-cell` for each column a span swallows, so a row has one
  element per column; OOXML emits nothing for them, so a row is complete
  when its *spans* total the grid. A row with the right number of cells
  and the wrong spans is a table Word renders as a mess.
- **A `w:pStyle` naming an undefined style is not an error.** The reference
  survives and the paragraph renders with the default — so styles must be
  injected (`postprocess_docx`), and a missing injection looks like nothing
  rather than like a failure. It is also where the body face lives, and the
  columns are measured for that face.
- **Column widths are estimated**, from a table of per-character advances
  measured off Liberation Serif (`measure._ADVANCE`, checked by `make
  advances`). There are no font metrics at conversion time. Text is
  estimated as *drawn*, not as spelled — `\lpzg` and `\textsc` set small
  capitals, which are wider than the lowercase they replace.
- **Bands are frozen at conversion time.** Where an over-wide example
  breaks is computed from `--text-width` and baked in; the reference
  document fixes the band *pattern*, never the break points.
- **A node pandoc produces but cannot render is DELETED, not degraded.**
  Twice now the same shape: `\Next` arrives as `RawInline "latex"` and a
  `Cite` with no bibliography carries only the raw LaTeX the reader kept.
  Both writers drop raw LaTeX, so the text vanishes and the sentence closes
  over the hole -- "structures like , involving" -- with nothing on the page
  to show it. Neither had a test, and one of them had a *warning claiming
  the opposite* ("pandoc renders it literally"; it does not). When a
  construct is handed to pandoc, check what it renders, not what it parses:
  a `Cite` in the AST proves only that the AST has a `Cite`.
- **An unknown environment takes its content with it.** Pandoc returns one
  it does not know as a single `RawBlock "latex"`, so an example inside
  `multicols` never became a `Para` and never reached the injector.
  `inject._free_trapped_placeholders` splits such a block at each
  placeholder; it needs no list of environments, because a `RawBlock` can
  only ever be an element of a block list.
- **An unhandled inline command damages its neighbours.** The renderer falls
  back to handing the whole enclosing group to pandoc, so one unknown
  three-token command took a `forest` tree with it: `{\small
  \begin{forest}...}` came back as `] [Voice' ...`. Adding a command to
  `inline.DECLARATIONS` or `WRAPPERS` is therefore worth more than it looks.
- **The constants exist three times, deliberately.** Basic and a browser
  module can import nothing from here. `make macro` (`tools/sync_macro.py`)
  writes the generated block of `LinguExx.bas`, all of
  `addin/core/constants.js` from `styles.py` and `measure.py`, and all of
  `addin/word/styles.js` from `styles_docx.py`; `tests/test_macro_sync.py`
  fails when any drifts. Never hand-edit a generated copy.
- **The add-in core is held to two oracles, exactly.** Its parse must be
  the macro's: the typed-line cases live in
  `tests/fixtures/typed-examples.json`, shared by the macro suite and
  `node --test`, and the macro's own parse of each (Basic
  `ParseLinesQuiet`) is recorded there as `parsed` by
  `LINGUEXX_UPDATE_GOLDEN=1 python3 tools/run_macro_test.py`. Its plan must
  be the converter's: `tools/addin_oracle.py` writes `plan_table()`'s
  answers to `typed-examples.plans.json`, and the Word add-in's markup
  must be `DocxEmitter.example()`'s, string for string
  (`typed-examples.docx.json`). Compared with no tolerance — so a
  change to the macro's grammar or the converter's geometry fails a golden
  first, and the core after. Both goldens are read before committing.
- **Python's `sum()` of floats is compensated from 3.12 on**, and the exact
  comparison depends on it: `measure.js` has `pySum` (CPython's Neumaier
  loop) wherever the Python calls `sum()`, and plain `+=` wherever the
  Python writes `+=`. "Tidying" either into the other is a change of
  result in the last place, which the plan test reports. Likewise
  Python's `round()` sends halves to even; `ooxml.js` has `pyRound` for
  the twips.
- **A cell's `w:tcW` must equal the grid columns it spans.** Word and
  LibreOffice lay a fixed table out from `w:tblGrid`; OnlyOffice lays it
  out from the cells. The converter summed `tcW` from the columns at the
  word's index until 2026-09-26, invisible everywhere but OnlyOffice, which
  drew every banded or paradigm example as letters in slivers.
- **A style the macro does not know is a broken round trip, not a cosmetic
  gap.** It reads converted tables back cell by cell, so a cell it cannot
  identify becomes content: `LxAnnot` unknown meant an `\exannot` label
  returned as a fifth object word and the rebuilt grid gained a column.
  `MACRO_STYLES_NOT_SHARED` is where such a gap is recorded, and it is
  empty — keep it so, or say what the absence costs.
- **The macro's suite is `python3 tools/run_macro_test.py DIR`**, which
  drives a real LibreOffice. It is not part of `make test` — it is minutes,
  not seconds — so a change to `LinguExx.bas` is unverified locally until
  it is run by hand. CI runs it in a job of its own, which must use the
  system `python3`: `import uno` comes from the site-packages LibreOffice
  installs for it, and a `setup-python` interpreter cannot see it.
  `LX_MACRO_TIMEOUT` raises the wait for a cold headless start. Its
  typed-line cases are read from `tests/fixtures/typed-examples.json`, not
  written in the harness.

## Tracking linguexx
- **This converter targets a linguexx VERSION**, currently 1.3.2, and the
  README says so. It was written against 1.2 and went on silently emitting
  1.2's output for a month after 1.3 changed it, because nothing recorded
  which version it was for.
- The dangerous drift is not an unknown command — the pandoc fallback
  warns about those. It is **changed behaviour of a command the converter
  believes it already handles**: `\ExLBr` redefined and ignored,
  `\GlossTransSide` set and ignored. Nothing unknown appears in the
  document, so nothing warns. `_scan_unsupported()` in `extract.py` is
  where such a setting gets declared.
- The README's "What it does not, and says so" table is a promise. A
  construct that is dropped, normalised or approximated belongs in it, in
  English and in `docs/guide-fr.md`.

## Do Not
- Settle something `plan.md` puts under "Out of scope (v1) — do not
  implement without asking". Those are undecided on purpose.
- Reproduce a linguexx placement that would force an invented answer to a
  question linguexx never faces. `\GlossTransSide` is the worked example:
  a side translation is the same material in another place, and
  reproducing it meant deciding what that column does when an example
  splits into bands. It is normalised to an ordinary example and the run
  says so.
- Hand-edit `tests/golden/*.json`, or regenerate them without reading.
- Add `strict=` to the `zip()` calls as a lint fix. It changes truncation
  into an exception, which is a behaviour change and wants its own commit
  and test. `ruff.toml` says so where it ignores B905.
