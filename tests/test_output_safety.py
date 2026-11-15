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

"""Conversion must never truncate its source or publish incomplete output."""

from pathlib import Path

import pytest

from linguexx2odt import cli, reverse
from linguexx2odt.output import atomic_output


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
@pytest.mark.parametrize("direction", ["forward", "reverse"])
def test_rejects_source_alias(tmp_path, monkeypatch, alias, direction):
    source = tmp_path / ("source.tex" if direction == "forward" else "source.docx")
    source.write_bytes(b"irreplaceable source")
    output = tmp_path / "alias"
    if alias == "same":
        output = source
    elif alias == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    monkeypatch.setattr(cli, "_check_pandoc_version", lambda: "test")
    command = cli.main if direction == "forward" else reverse.main_docx
    with pytest.raises(SystemExit, match="overwrite the input"):
        command([str(source), "-o", str(output)])
    assert source.read_bytes() == b"irreplaceable source"


@pytest.mark.parametrize("exists", [False, True])
def test_failed_write_preserves_destination_and_cleans_staging(tmp_path, exists):
    output = tmp_path / "document.odt"
    if exists:
        output.write_bytes(b"previous document")
    with pytest.raises(OSError, match="disk full"):
        with atomic_output(output) as staged:
            staged.write_bytes(b"incomplete")
            raise OSError("disk full")
    assert output.read_bytes() == b"previous document" if exists else not output.exists()
    assert list(tmp_path.iterdir()) == ([output] if exists else [])


def test_failed_replace_preserves_destination(tmp_path, monkeypatch):
    output = tmp_path / "document.tex"
    output.write_text("previous")

    def fail(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        with atomic_output(output) as staged:
            staged.write_text("new")
    assert output.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("target", ["odt", "docx"])
def test_forward_postprocessing_failure_preserves_output(tmp_path, monkeypatch, target):
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}\begin{document}Hello.\end{document}")
    output = tmp_path / ("result." + target)
    output.write_bytes(b"previous document")

    def fail(document, warn):
        document.write_bytes(b"incomplete")
        raise OSError("postprocessing failed")

    monkeypatch.setattr(cli.pages, "fill", fail)
    with pytest.raises(OSError, match="postprocessing failed"):
        cli.main([str(source), "--to", target, "-o", str(output)])
    assert output.read_bytes() == b"previous document"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([source.name, output.name])


def test_success_replaces_existing_output(tmp_path):
    output = tmp_path / "document.tex"
    output.write_text("previous")
    with atomic_output(output) as staged:
        staged.write_text("complete")
        assert output.read_text() == "previous"
    assert output.read_text() == "complete"
    assert list(tmp_path.iterdir()) == [output]


def test_reverse_write_failure_preserves_output(tmp_path, monkeypatch):
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}\begin{document}Hello.\end{document}")
    docx = tmp_path / "source.docx"
    cli.main([str(source), "--to", "docx", "-o", str(docx)])
    output = tmp_path / "result.tex"
    output.write_text("previous source")
    write_text = Path.write_text

    def fail_staged_write(path, *args, **kwargs):
        if path.name.startswith(".result.tex."):
            write_text(path, "incomplete")
            raise OSError("disk full")
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_staged_write)
    with pytest.raises(OSError, match="disk full"):
        reverse.main_docx([str(docx), "-o", str(output)])
    assert output.read_text() == "previous source"
    assert not list(tmp_path.glob(".result.tex.*"))
