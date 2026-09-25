# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
#
# This file is part of pandoc-linguexx.
#
# pandoc-linguexx is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# pandoc-linguexx is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.

"""``python3 -m linguexx2odt`` — the CLI without an installed entry point.

The console script in pyproject.toml needs an install; a virtualenv is one
more thing that can be missing, out of date, or — as happened here — synced
between machines by a service that does not preserve the executable bit, so
that ``.venv/bin/linguexx2odt`` exists and will not run.

This module needs no venv and no install -- only ``src/`` on the import
path, which with this project's src-layout means saying so::

    PYTHONPATH=src python3 -m linguexx2odt paper.tex -o paper.odt

``pip install -e .`` arranges it permanently; pytest arranges it for the
suite through ``pythonpath`` in pyproject.toml, which is why the tests need
no PYTHONPATH.  Running the module from a bare checkout does.
"""

import sys

from .cli import main

sys.exit(main())
