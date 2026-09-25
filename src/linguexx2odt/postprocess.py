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

"""Stage 4 — patch the ODT that pandoc produced.

A raw block in the document body cannot carry the automatic styles it
references, and pandoc emits no ``<text:sequence-decls>``, so both have to
be spliced in afterwards.  Everything not named here is copied through
byte-for-byte, and ``mimetype`` stays the first, STORED entry — an ODT
whose zip layout is wrong will not open.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

SEQ_DECLS = (
    "<text:sequence-decls>"
    '<text:sequence-decl text:display-outline-level="0" text:name="NumEx"/>'
    "</text:sequence-decls>"
)


def inject_sequence_decls(content: str) -> str:
    """Declare NumEx as the first child of ``<office:text>``.

    S2 showed LibreOffice tolerates the declaration being absent, but it
    writes one itself on every save, so emitting it keeps our output and a
    round-tripped file identical.
    """
    if "<text:sequence-decls" in content:
        if 'text:name="NumEx"' in content:
            return content
        return content.replace(
            "</text:sequence-decls>",
            '<text:sequence-decl text:display-outline-level="0" text:name="NumEx"/>'
            "</text:sequence-decls>",
            1,
        )
    m = re.search(r"<office:text[^>]*>", content)
    if not m:
        raise ValueError("content.xml has no <office:text> element")
    return content[: m.end()] + SEQ_DECLS + content[m.end() :]


def inject_automatic_styles(content: str, fragment: str) -> str:
    if not fragment:
        return content
    tag = "</office:automatic-styles>"
    if tag in content:
        return content.replace(tag, fragment + tag, 1)
    m = re.search(r"<office:body[^>]*>", content)
    if not m:
        raise ValueError("content.xml has neither automatic-styles nor a body")
    block = "<office:automatic-styles>" + fragment + tag
    return content[: m.start()] + block + content[m.start() :]


def inject_named_styles(styles_xml: str, fragment: str) -> str:
    if not fragment:
        return styles_xml
    tag = "</office:styles>"
    if tag not in styles_xml:
        raise ValueError("styles.xml has no <office:styles> element")
    return styles_xml.replace(tag, fragment + tag, 1)


def set_default_font(styles_xml: str, name: str) -> str:
    r"""Name *name* as the document's default face.

    The columns are computed for one face (`Layout.font_name`), so the
    document has to be set in that face or they are measured for something
    it does not use.  pandoc's reference.odt already happens to be Times,
    which is why this was not needed until `--font` existed: ask for
    anything else and the widths changed while the drawing did not.

    On the default paragraph style rather than on `LxExampleCell`, for the
    reason the .docx target learned the hard way: put it on the example
    style and the examples come out in a different face from the prose
    around them.
    """
    import re as _re

    # The `[^>]*?` is lazy and the `\s*` eats the space before a
    # self-closing slash, so the attributes go INSIDE the element.  Greedy,
    # it swallows the `/` itself and the result is `... / style:font-name=...>`
    # -- well-formed to a regex, and a file LibreOffice refuses to open.
    m = _re.search(r'(<style:default-style style:family="paragraph">.*?'
                   r'<style:text-properties\b[^>]*?)\s*(/?>)',
                   styles_xml, _re.S)
    if not m:
        return styles_xml
    # ODF wants the face DECLARED as well as named.  Without an entry in
    # office:font-face-decls a reader is free to substitute, and LibreOffice
    # does: asking for DejaVu Serif and declaring nothing produced Liberation
    # Serif, which is a perfectly good Times substitute and not what was
    # asked for.  OOXML needs no equivalent.
    if f'style:name="{name}"' not in styles_xml:
        decl = (f'<style:font-face style:name="{name}" '
                f'svg:font-family="&apos;{name}&apos;"/>')
        styles_xml = styles_xml.replace("</office:font-face-decls>",
                                        decl + "</office:font-face-decls>", 1)
        m = _re.search(r'(<style:default-style style:family="paragraph">.*?'
                       r'<style:text-properties\b[^>]*?)\s*(/?>)',
                       styles_xml, _re.S)
        if not m:
            return styles_xml

    head = _re.sub(r'\s+style:font-name(-\w+)?="[^"]*"', "", m.group(1))
    for attr in ("style:font-name", "style:font-name-asian",
                 "style:font-name-complex"):
        head += f' {attr}="{name}"'
    return styles_xml[:m.start()] + head + m.group(2) + styles_xml[m.end():]


def set_page_geometry(styles_xml: str, page: str) -> str:
    """Rewrite the page size/margins of every page layout.

    pandoc's default reference document is US Letter with 1in margins;
    ``--page a4`` gives the geometry the reference document uses.
    """
    if page == "keep":
        return styles_xml
    geom = {
        "a4": ('21cm', '29.7cm', '2cm'),
        "a4-wide": ('21cm', '29.7cm', '1.5cm'),
        "letter": ('8.5in', '11in', '1in'),
    }[page]
    width, height, margin = geom

    def fix(m: re.Match[str]) -> str:
        props = m.group(0)
        for attr, value in (
            ("fo:page-width", width),
            ("fo:page-height", height),
            ("fo:margin-left", margin),
            ("fo:margin-right", margin),
            ("fo:margin-top", margin),
            ("fo:margin-bottom", margin),
        ):
            if f"{attr}=" in props:
                props = re.sub(rf'{attr}="[^"]*"', f'{attr}="{value}"', props)
            else:
                props = props[:-1].rstrip() + f' {attr}="{value}">'
        return props

    return re.sub(r"<style:page-layout-properties\b[^>]*>", fix, styles_xml)


def rewrite(odt: Path, out: Path, members: dict[str, str]) -> None:
    """Copy *odt* to *out*, replacing the named members."""
    with zipfile.ZipFile(odt) as src:
        infos = src.infolist()
        if not infos or infos[0].filename != "mimetype":
            raise ValueError(
                f"{odt} is not a well-formed ODT: first entry is "
                f"{infos[0].filename if infos else '(empty)'}, not 'mimetype'"
            )
        data = {i.filename: src.read(i.filename) for i in infos}

    for name, text in members.items():
        if name not in data:
            raise KeyError(f"{odt} has no member {name}")
        data[name] = text.encode("utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as dst:
        first = zipfile.ZipInfo("mimetype", date_time=infos[0].date_time)
        first.compress_type = zipfile.ZIP_STORED
        dst.writestr(first, data["mimetype"])
        for info in infos:
            if info.filename == "mimetype":
                continue
            item = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = info.external_attr
            dst.writestr(item, data[info.filename])


def read(odt: Path, name: str) -> str:
    with zipfile.ZipFile(odt) as z:
        return z.read(name).decode("utf-8")
