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

"""Zip surgery helpers shared by the spikes (prototype of postprocess.py).

An ODT is a zip whose *first* entry must be an uncompressed ``mimetype``
member; everything else is deflated.  We rewrite only the members we care
about and copy the rest byte-for-byte.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

SEQ_DECL = (
    '<text:sequence-decls>'
    '<text:sequence-decl text:display-outline-level="0" text:name="NumEx"/>'
    '</text:sequence-decls>'
)


def read_member(odt: Path, name: str) -> str:
    with zipfile.ZipFile(odt) as z:
        return z.read(name).decode("utf-8")


def patch(odt: Path, out: Path, members: dict[str, str]) -> None:
    """Copy *odt* to *out*, replacing the named members with new text."""
    with zipfile.ZipFile(odt) as src:
        infos = src.infolist()
        names = [i.filename for i in infos]
        if names[0] != "mimetype":
            raise AssertionError(f"first zip entry is {names[0]!r}, not 'mimetype'")
        data = {i.filename: src.read(i.filename) for i in infos}

    for name, text in members.items():
        data[name] = text.encode("utf-8")

    with zipfile.ZipFile(out, "w") as dst:
        mt = zipfile.ZipInfo("mimetype")
        mt.compress_type = zipfile.ZIP_STORED
        dst.writestr(mt, data["mimetype"])
        for info in infos:
            if info.filename == "mimetype":
                continue
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            dst.writestr(zi, data[info.filename])


def inject_sequence_decls(content_xml: str) -> str:
    """Put a NumEx <text:sequence-decls> as the first child of <office:text>."""
    if "<text:sequence-decls>" in content_xml:
        raise AssertionError("content.xml already has sequence-decls; merge instead")
    m = re.search(r"<office:text[^>]*>", content_xml)
    if not m:
        raise AssertionError("no <office:text> in content.xml")
    return content_xml[: m.end()] + SEQ_DECL + content_xml[m.end() :]


def inject_automatic_styles(content_xml: str, styles_xml_fragment: str) -> str:
    """Append styles just before </office:automatic-styles> in content.xml."""
    tag = "</office:automatic-styles>"
    if tag not in content_xml:
        raise AssertionError("no <office:automatic-styles> in content.xml")
    return content_xml.replace(tag, styles_xml_fragment + tag, 1)


def soffice_convert(src: Path, fmt: str, outdir: Path) -> Path:
    """Headless conversion.  Returns the produced file path."""
    outdir.mkdir(parents=True, exist_ok=True)
    profile = outdir / ".loprofile"
    subprocess.run(
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            fmt,
            "--outdir",
            str(outdir),
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    produced = outdir / (src.stem + "." + fmt.split(":")[0])
    if not produced.exists():
        raise AssertionError(f"soffice produced no {produced}")
    return produced


def pdf_text(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def fresh(d: Path) -> Path:
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d
