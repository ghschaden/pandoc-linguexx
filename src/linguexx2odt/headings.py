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
r"""Numbered headings, as LaTeX numbers them.

A ``\ref`` to a section is a field that shows the heading's number, so the
heading must have one, and one the word processor keeps: an outline
numbering, which renumbers when a section is moved, and not a typed "1.1".
Pandoc numbers none (its ODT writer ignores ``--number-sections``), so the
three levels LaTeX's article numbers are numbered here.  A ``\section*``
is not: the inject pass put a bookmark named ``sections.UNNUMBERED...`` in
it, and that heading is taken out of the numbering without stepping it --
``text:is-list-header`` in ODF, ``numId 0`` in OOXML.
"""

from __future__ import annotations

import re

from .sections import NUMBERED_LEVELS, UNNUMBERED

# -- ODF ------------------------------------------------------------------

_OUTLINE_LEVEL = re.compile(
    r'<text:outline-level-style\b([^>]*)\btext:level="(\d+)"([^>]*)>')


def number_outline(styles_xml: str) -> str:
    """Levels 1-3 of the outline numbered "1", "1.1", "1.1.1"."""
    def fix(m: re.Match[str]) -> str:
        level = int(m.group(2))
        attrs = f"{m.group(1)}{m.group(3)}"
        if level > NUMBERED_LEVELS:
            return m.group(0)
        attrs = re.sub(r'\s*(?:style:num-format|text:display-levels'
                       r'|style:num-suffix)="[^"]*"', "", attrs)
        return (f'<text:outline-level-style text:level="{level}"'
                f' style:num-format="1" text:display-levels="{level}"{attrs}>')
    return _OUTLINE_LEVEL.sub(fix, styles_xml)


_ODF_HEADING = re.compile(r"<text:h\b([^>]*)>(.*?)</text:h>", re.S)


def unnumber_odt_headings(content_xml: str) -> str:
    def fix(m: re.Match[str]) -> str:
        if f'text:name="{UNNUMBERED}' not in m.group(2) \
                or "text:is-list-header" in m.group(1):
            return m.group(0)
        return f'<text:h{m.group(1)} text:is-list-header="true">{m.group(2)}</text:h>'
    return _ODF_HEADING.sub(fix, content_xml)


# -- OOXML ----------------------------------------------------------------

ABSTRACT_NUM_ID = 9100
NUM_ID = 9101


def _level(ilvl: int) -> str:
    text = ".".join(f"%{k}" for k in range(1, ilvl + 2))
    return (f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/>'
            '<w:numFmt w:val="decimal"/>'
            f'<w:pStyle w:val="Heading{ilvl + 1}"/>'
            # a space after the number, where Word's default is a tab
            '<w:suff w:val="space"/>'
            f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="0" w:firstLine="0"/></w:pPr></w:lvl>')


def number_docx_numbering(numbering_xml: str) -> str:
    abstract = (f'<w:abstractNum w:abstractNumId="{ABSTRACT_NUM_ID}">'
                '<w:multiLevelType w:val="multilevel"/>'
                + "".join(_level(i) for i in range(NUMBERED_LEVELS))
                + "</w:abstractNum>")
    num = (f'<w:num w:numId="{NUM_ID}">'
           f'<w:abstractNumId w:val="{ABSTRACT_NUM_ID}"/></w:num>')
    # every abstractNum before the first num, as the schema orders them
    m = re.search(r"<w:num\b", numbering_xml)
    if m is None:
        m = re.search(r"</w:numbering>", numbering_xml)
        if m is None:
            raise ValueError("numbering.xml has no </w:numbering>")
    out = numbering_xml[:m.start()] + abstract + numbering_xml[m.start():]
    return out.replace("</w:numbering>", num + "</w:numbering>", 1)


#: The children of a w:pPr that the schema puts before w:numPr.
_BEFORE_NUMPR = re.compile(
    r"\s*(?:<w:(?:pStyle|keepNext|keepLines|pageBreakBefore|framePr|widowControl)"
    r"\b[^>]*?(?:/>|>.*?</w:(?:pStyle|keepNext|keepLines|pageBreakBefore"
    r"|framePr|widowControl)>)\s*)*", re.S)


def _with_numpr(ppr_inner: str, numpr: str) -> str:
    inner = re.sub(r"<w:numPr\b.*?</w:numPr>\s*", "", ppr_inner, flags=re.S)
    m = _BEFORE_NUMPR.match(inner)
    return inner[:m.end()] + numpr + inner[m.end():]


def number_docx_styles(styles_xml: str) -> str:
    """Heading1-3 take their numbers from NUM_ID."""
    for ilvl in range(NUMBERED_LEVELS):
        numpr = (f'<w:numPr><w:ilvl w:val="{ilvl}"/>'
                 f'<w:numId w:val="{NUM_ID}"/></w:numPr>')
        style = re.compile(r'(<w:style\b[^>]*\bw:styleId="Heading%d"[^>]*>)(.*?)(</w:style>)'
                           % (ilvl + 1), re.S)
        m = style.search(styles_xml)
        if m is None:
            continue
        body = m.group(2)
        ppr = re.search(r"<w:pPr\s*/>|<w:pPr>(.*?)</w:pPr>", body, re.S)
        if ppr is None:
            # before the run properties, which follow it in a style
            r = body.find("<w:rPr")
            at = r if r >= 0 else len(body)
            body = body[:at] + f"<w:pPr>{numpr}</w:pPr>" + body[at:]
        else:
            body = (body[:ppr.start()]
                    + f"<w:pPr>{_with_numpr(ppr.group(1) or '', numpr)}</w:pPr>"
                    + body[ppr.end():])
        styles_xml = (styles_xml[:m.start()] + m.group(1) + body + m.group(3)
                      + styles_xml[m.end():])
    return styles_xml


_DOCX_PARA = re.compile(r"<w:p\b(?:[^>]*)>(?:(?!</w:p>).)*?</w:p>", re.S)
_NO_NUMBER = '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="0"/></w:numPr>'


def unnumber_docx_headings(document_xml: str) -> str:
    def fix(m: re.Match[str]) -> str:
        para = m.group(0)
        if f'w:name="{UNNUMBERED}' not in para:
            return para
        ppr = re.search(r"<w:pPr\s*/>|<w:pPr>(.*?)</w:pPr>", para, re.S)
        if ppr is None:
            at = para.index(">") + 1
            return para[:at] + f"<w:pPr>{_NO_NUMBER}</w:pPr>" + para[at:]
        return (para[:ppr.start()]
                + f"<w:pPr>{_with_numpr(ppr.group(1) or '', _NO_NUMBER)}</w:pPr>"
                + para[ppr.end():])
    return _DOCX_PARA.sub(fix, document_xml)
