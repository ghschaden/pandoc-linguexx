# pandoc-linguexx: the things done to the project as a whole.
#
#   make test      the suite (pytest); fails if a required tool is missing
#   make lint      ruff over src/, tests/ and tools/
#   make check     lint and test, which is what CI runs
#   make js-test   the add-ins' suite (node --test); needs Node >= 22
#   make onlyoffice       build the OnlyOffice plugin into dist/
#   make onlyoffice-test  run its editor half in Document Builder
#   make macro     rewrite the macro's and the add-in core's constants
#   make oxt       package the Writer macro as a LibreOffice extension
#   make advances  check the width table against the font it describes
#   make schemas   fetch the ECMA-376 schemas a .docx is validated against
#   make venv      recreate .venv (see the note below)
#   make clean     remove build artefacts and caches
#
# `make test` needs no PYTHONPATH: pyproject.toml sets
# `pythonpath = ["src"]` for pytest.  Running the converter by hand from a
# bare checkout DOES, this being a src-layout project:
#     PYTHONPATH=src python3 -m linguexx2odt paper.tex -o paper.odt
# The two are different questions and were briefly answered as one.

PYTHON ?= python3

.PHONY: all check test js-test onlyoffice onlyoffice-test lint macro oxt advances schemas venv clean

all: check

check: lint test

# A missing pandoc or LibreOffice used to take 28 tests out of the run and
# leave the exit code at 0.  tests/test_tooling.py now fails instead and
# names them; LINGUEXX2ODT_ALLOW_MISSING=1 turns that back into a skip for
# a run you know is partial.
test:
	@$(PYTHON) -m pytest -q

# Deliberately not part of `test`, and part of `check`: a lint is not a
# test, and a contributor without ruff should still be able to run the
# suite.  Says so rather than failing with a 127 when it is absent.
lint:
	@if command -v ruff >/dev/null 2>&1; then \
	  ruff check . && echo "OK  ruff"; \
	else \
	  echo "ruff is not installed; skipping (see ruff.toml)"; \
	fi

# The add-in core (addin/core), held to the Writer macro's parse and the
# converter's plan_table() through the goldens in tests/fixtures/.  Node is
# needed here and nowhere else: `make test` stays Python-only, and CI runs
# this as a job of its own.  No npm install -- the core has no dependencies.
# The test files are named by glob, not by directory: Node 22, which CI
# runs, loads a directory argument as a module and fails before any test,
# where Node 26 expands it -- the first CI run found that out.
js-test: onlyoffice
	@if command -v node >/dev/null 2>&1; then \
	  cd addin && node --test "core/test/*.test.js" "word/test/*.test.js" "onlyoffice/test/*.test.js"; \
	else \
	  echo "node is not installed; the add-ins' suite needs Node >= 22"; \
	  exit 1; \
	fi

# The OnlyOffice plugin: the add-in modules joined into one classic script
# (a plugin is loaded from local files, where ES modules are not to be relied
# on), with config.json, the panel and icons, in dist/ -- and as a .plugin
# file for OnlyOffice's plugin manager.
onlyoffice:
	@$(PYTHON) tools/build_onlyoffice.py

# The plugin's editor half, headless: every fixture inserted by the plugin's
# own commands in Document Builder and held to the Word layer's markup, plus
# a renumbering scenario.  Needs Document Builder (plan-addins.md, S9); CI
# runs it in a job of its own, pinned to 9.4.0 by checksum.  The free build
# watermarks the page header, which nothing in the test reads.
onlyoffice-test: onlyoffice
	@node tools/run_onlyoffice_test.mjs

# The macro is Basic and the add-in core JavaScript; neither can import
# anything, so the style names and layout lengths exist three times.  This
# writes the other copies from styles.py and measure.py;
# tests/test_macro_sync.py fails when they drift.
macro:
	@$(PYTHON) tools/sync_macro.py --write

oxt:
	@$(PYTHON) tools/build_oxt.py

advances:
	@$(PYTHON) tools/measure_advances.py

# Into .ooxml-schemas/, which is gitignored: 968 KB of somebody else's
# standard, cached rather than vendored.  Transitional, from Part 4 -- the
# Strict schemas in Part 1 are a different namespace and validating against
# them fails on that alone.  tools/validate_docx.py uses them.
schemas:
	@$(PYTHON) tools/fetch_ooxml_schemas.py

# pCloud syncs this checkout between machines and does not preserve the
# executable bit, which leaves .venv/bin/linguexx2odt present and not
# runnable.  Recreating the venv is the fix; `python3 -m linguexx2odt`
# needs no venv at all and is the quicker way past it.
venv:
	@rm -rf .venv
	@$(PYTHON) -m venv .venv
	@.venv/bin/pip install --quiet -e ".[dev]"
	@echo "OK  .venv (run .venv/bin/linguexx2odt, or python3 -m linguexx2odt)"

clean:
	@rm -rf build dist .pytest_cache .ruff_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "build artefacts and caches removed"
