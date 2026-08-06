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

"""The LibreOffice Writer macro, shipped with the converter.

It lives inside the package rather than beside it so that installing
``pandoc-linguexx`` actually puts the macro on disk — ``pip install`` ships
packages, not loose top-level directories, and for a while it silently
shipped the converter alone.

    linguexx2odt --print-macro > LinguExx.bas
"""

from __future__ import annotations

from pathlib import Path

NAME = "LinguExx.bas"


def path() -> Path:
    """Where the Basic source sits in this installation."""
    return Path(__file__).resolve().parent / NAME


def source() -> str:
    return path().read_text(encoding="utf-8")
