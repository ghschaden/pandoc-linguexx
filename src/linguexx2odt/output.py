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

"""Publish completed conversions without truncating an existing destination."""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


def same_file(source: Path, destination: Path) -> bool:
    """Recognize identical paths, symlinks and existing hard links."""
    return (source.resolve() == destination.resolve()
            or (destination.exists() and source.samefile(destination)))


@contextmanager
def atomic_output(destination: Path):
    """Yield a sibling staging file; replace the destination only on success."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{destination.name}.",
                                suffix=destination.suffix, dir=destination.parent)
    staged = Path(name)
    os.close(fd)
    try:
        yield staged
        if destination.exists():
            staged.chmod(destination.stat().st_mode & 0o777)
        staged.replace(destination)
    finally:
        staged.unlink(missing_ok=True)
