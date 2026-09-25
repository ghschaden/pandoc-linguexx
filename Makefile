# pandoc-linguexx: the things done to the project as a whole.
#
#   make test      the suite (pytest); fails if a required tool is missing
#   make lint      ruff over src/, tests/ and tools/
#   make check     lint and test, which is what CI runs
#   make macro     rewrite the macro's constants from the converter's
#   make oxt       package the Writer macro as a LibreOffice extension
#   make advances  check the width table against the font it describes
#   make venv      recreate .venv (see the note below)
#   make clean     remove build artefacts and caches
#
# No PYTHONPATH anywhere: pyproject.toml sets `pythonpath = ["src"]` for
# pytest, and `python3 -m linguexx2odt` finds the package from a bare
# checkout.  If you have been exporting PYTHONPATH=src, you can stop.

PYTHON ?= python3

.PHONY: all check test lint macro oxt advances venv clean

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

# The macro is Basic and can import nothing, so the style names and layout
# lengths exist twice.  This writes the second copy from the first;
# tests/test_macro_sync.py fails when they drift.
macro:
	@$(PYTHON) tools/sync_macro.py

oxt:
	@$(PYTHON) tools/build_oxt.py

advances:
	@$(PYTHON) tools/measure_advances.py

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
