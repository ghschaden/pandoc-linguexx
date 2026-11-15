# Release checklist

[Français](publication-fr.md) · [User guide](../README.md)

Use this checklist for a specific release candidate. Record its commit,
artifact filenames, tool versions, date and results. A previous successful
run does not validate later changes. The checklist below is a procedure,
not a claim that every item has passed.

## Automated checks

1. Install the candidate in a development environment (`pip install -e
   '.[dev]'`) and install Ruff. Provide pandoc, LibreOffice and Poppler;
   check out the target linguexx corpus (1.5) beside this repository.
2. Run `make check` and `make js-test` (Node ≥ 22). Do not enable
   `LINGUEXX2ODT_ALLOW_MISSING` for release validation.
3. Run the Writer suite with `python3 tools/run_macro_test.py`, using a
   Python with the LibreOffice UNO bridge. Run `make onlyoffice-test`
   with Document Builder configured as described in the CI workflow.
4. Build the distribution artifacts: `make oxt`, `make onlyoffice`,
   and `python -m pip wheel . --no-deps --wheel-dir dist`.
5. Install the wheel in a fresh environment. Check all three commands,
   `linguexx2odt --print-macro`, and a forward/reverse sample conversion.
6. Run compatibility checks at the declared minimum Python/Pandoc versions
   and a newer combination. CI now gates the full Python suite and the
   clean-wheel check on Python/Pandoc pairs 3.10/3.6.1, 3.12/3.6.1 and
   3.14/3.11. Inspect all three job results for the release candidate.

## Editor acceptance

- Writer: install the candidate `.oxt`; compose, decompose, edit, recompose
  and undo ordinary, shared-gloss and tree examples. Check numbering,
  references, styles and a narrow page.
- OnlyOffice: install the candidate plugin in the desktop application;
  repeat the authoring cycle and verify numbering in a converted document.
  Document Builder tests alone do not validate the desktop interface.
- Word: follow [the Word procedure](../WORD-TESTS-TODO.md), recording the
  host and version. Distinguish converter output from add-in behavior.

**Outstanding Word validation:** shared-gloss authoring introduced on
2026-11-14 has not been tested in live Word, web or desktop. Rendering,
insertion, repeated Typeset/Untypeset, malformed-selection handling and
desktop Undo remain pending. Mocked Office.js and OOXML tests do not close
this item. Keep the limitation visible in release notes until tested.

## Documentation and publication review

- Update the English README and French guide together: prerequisites,
  commands, supported constructs, limitations and validation status.
- Update both Writer manuals for changes to authoring or editing behavior.
- Update the English PDF source and run `make manual`; inspect the PDF.
- Match artifact names and package versions. Record changes, known limits
  and actual test results in release notes; distinguish implemented,
  automatically checked and manually verified behavior.
- Preserve the documented Word limitation if those checks remain pending.
  Review the complete candidate before publishing its artifacts.

## Maintaining shared behavioral fixtures

Add malformed shared-gloss selections to
[`tests/fixtures/shared-authoring.json`](../tests/fixtures/shared-authoring.json),
with a descriptive case name, input `lines` and the one-based `errorLine`
(including blank lines). These are reviewed expectations, not generated output.
The core parser, Word task-pane tests, OnlyOffice job tests and real Writer
macro suite all consume this file. Each checks rejection before replacement;
the suites also check that a subsequent valid operation succeeds.

Run `make js-test` and `python -m pytest tests/test_addin_core.py
 tests/test_macro_sync.py`, then the Writer macro suite for changes to this
contract. Keep host-specific assertions in their respective suites: Word
must not call insertion, OnlyOffice must not return a job or mutate its
input, and Writer must leave text, tables and numbering unchanged. These
checks complement the existing converter-generated layout/round-trip fixtures;
they do not establish live Word compatibility.

To reproduce the installed-package check, build a wheel, install it with
its dependencies into a fresh virtual environment, then run that environment's
Python with `-I tools/check_installed.py`. Do not install the project editably
or enable system site packages. The script checks import locations, all three
entry points, the bundled macro, live reference markup and ODT/DOCX round trips
from a temporary working directory. It requires pandoc and LibreOffice.

The minimum Pandoc version is now 3.6.1. A separate Python 3.10/Pandoc 3.0
run reproduced a nested DOCX list rendering failure; passing a simple wheel
smoke test alone was insufficient. The development extra includes `lxml`
for schema validation when the optional ECMA-376 schemas are available.
