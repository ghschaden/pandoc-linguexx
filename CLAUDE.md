# pandoc-linguexx — notes for Claude

`linguexx2odt` converts a LaTeX document containing
[linguexx](../linguexx) examples into a LibreOffice Writer file **in which
every example number is a live field**, so inserting an example in Writer
renumbers the rest and cross-references follow. Everything that is not an
example is converted by pandoc.

There is a second deliverable in the same repository: `LinguExx.bas`, a
Writer macro that formats glossed examples inside Writer with no LaTeX at
all. It duplicates the converter's constants on purpose — see below.

## Environment
- Python ≥ 3.10, standard library only. `pandoc ≥ 3.0` (the JSON AST is a
  versioned interface), LibreOffice for the rendering half, poppler for
  reading the result back.
- **No `PYTHONPATH` needed.** `pyproject.toml` sets
  `pythonpath = ["src"]` for pytest, and `python3 -m linguexx2odt` runs
  from a bare checkout. Exporting `PYTHONPATH=src` is a habit worth
  dropping; it is what a whole session was prefixed with before anyone
  read the config.
- `.venv/bin/linguexx2odt` may exist and refuse to run: pCloud syncs this
  checkout and does not preserve the executable bit. `make venv` rebuilds
  it; `python3 -m linguexx2odt` sidesteps it.
- Commits are **SSH-signed through 1Password**. When it is locked, `git
  commit` fails with "failed to fill whole buffer" and only the user can
  unlock it. `git commit --dry-run` does NOT sign, so it proves nothing
  about whether signing works — do not use it as the test.

## Make
`make check` is lint plus suite, which is what CI runs. `make test`,
`make lint`, `make macro`, `make oxt`, `make advances`, `make venv`,
`make clean`. The Makefile's header says what each is for.

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

## Architecture invariants
- **Examples are never pandoc `Table` AST nodes.** Each becomes one opaque
  `RawBlock` of `opendocument` that this code controls completely — column
  widths, merged cells, fields, styles. `plan.md` records why, under
  "Verified facts"; that section is not to be re-litigated without
  re-running its spikes.
- **Numbers are `text:sequence` fields**, references are
  `text:sequence-ref`. That is the entire point of the tool: a number that
  is text renumbers nothing.
- **Column widths are estimated**, from a table of per-character advances
  measured off Liberation Serif (`emit_odt._ADVANCE`, checked by `make
  advances`). There are no font metrics at conversion time. Text is
  estimated as *drawn*, not as spelled — `\lpzg` and `\textsc` set small
  capitals, which are wider than the lowercase they replace.
- **Bands are frozen at conversion time.** Where an over-wide example
  breaks is computed from `--text-width` and baked in; the reference
  document fixes the band *pattern*, never the break points.
- **The macro duplicates the converter's constants, deliberately.** Basic
  can import nothing. `make macro` (`tools/sync_macro.py`) writes the
  second copy from the first and `tests/test_macro_sync.py` fails when
  they drift. Never hand-edit the constants in `LinguExx.bas`.

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
