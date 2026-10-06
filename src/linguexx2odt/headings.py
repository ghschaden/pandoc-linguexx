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

The end of the module does the same for captions and footnotes: declaring
the sequences a caption's number counts in, and connecting a reference to a
footnote with the note, which pandoc names.
"""

from __future__ import annotations

import re

from .sections import (APPENDIX, CAPTION_NAMES, FOOTNOTE_MARK, FOOTNOTE_MARKER,
                       NUMBERED_LEVELS, UNNUMBERED)

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


# -- captions and footnotes -------------------------------------------------
#
# Not headings, but the same kind of work: what the inject pass could not
# write because pandoc decides it -- a note's id, the run its mark is in.

def declare_caption_sequences(content_xml: str) -> str:
    """Declare the Table and Figure sequences beside NumEx (which
    postprocess.inject_sequence_decls put there first)."""
    decls = "".join(
        f'<text:sequence-decl text:display-outline-level="0" text:name="{name}"/>'
        for name in CAPTION_NAMES.values()
        if f'text:sequence-decl text:display-outline-level="0" text:name="{name}"'
        not in content_xml)
    if not decls:
        return content_xml
    return content_xml.replace("</text:sequence-decls>",
                               decls + "</text:sequence-decls>", 1)


_ODF_NOTE = re.compile(r'<text:note\b[^>]*\btext:id="([^"]+)"[^>]*>.*?</text:note>', re.S)
_MARKER = re.compile(rf'text:name="{FOOTNOTE_MARKER}(\d+)"')


def name_odt_note_refs(content_xml: str) -> str:
    """Point each text:note-ref at the note that holds its marker."""
    ids = {}
    for note in _ODF_NOTE.finditer(content_xml):
        for marker in _MARKER.finditer(note.group(0)):
            ids[marker.group(1)] = note.group(1)
    return re.sub(rf'(<text:note-ref\b[^>]*\btext:ref-name="){FOOTNOTE_MARK}(\d+)"',
                  lambda m: f'{m.group(1)}{ids.get(m.group(2), "")}"', content_xml)


_DOCX_NOTE = re.compile(r'<w:footnote\b[^>]*\bw:id="(\d+)"[^>]*>.*?</w:footnote>', re.S)
_DOCX_MARKER = re.compile(rf'w:name="{FOOTNOTE_MARKER}(\d+)"')


def bookmark_docx_note_marks(document_xml: str, footnotes_xml: str) -> str:
    """Put bookmark _Reflxfn<n> around the run that carries the mark of the
    note holding marker _Reflxfnl<n>: NOTEREF points at the mark in the
    text, not at the note."""
    from .emit_docx import bookmark_id

    for note in _DOCX_NOTE.finditer(footnotes_xml):
        for marker in _DOCX_MARKER.finditer(note.group(0)):
            serial = int(marker.group(1))
            ident = bookmark_id(serial, 1)
            run = re.compile(r'<w:r>(?:(?!</w:r>).)*?<w:footnoteReference w:id="%s"\s*/>'
                             r'(?:(?!</w:r>).)*?</w:r>' % note.group(1), re.S)
            document_xml = run.sub(
                lambda m, s=serial, i=ident: (
                    f'<w:bookmarkStart w:id="{i}" w:name="{FOOTNOTE_MARK}{s}"/>'
                    f'{m.group(0)}<w:bookmarkEnd w:id="{i}"/>'),
                document_xml, count=1)
    return document_xml


_LIST_START = re.compile(
    r'(<text:list\b[^>]*?)\s+text:start-value="(\d+)"([^>]*>\s*<text:list-item)\b')


def start_odt_lists(content_xml: str) -> str:
    r"""Put a list's start number where ODF reads it, on its first item.

    Pandoc writes it on text:list, which has no such attribute, and
    LibreOffice numbers the list from 1: \setcounter{enumi}{4} gave "1."
    where LaTeX prints "5.", and a reference to the item said "1" with it.
    """
    return _LIST_START.sub(r'\1\3 text:start-value="\2"', content_xml)


def add_docx_footnotes(footnotes_xml: str, notes: list[tuple[int, str]],
                       document_xml: str) -> tuple[str, str]:
    """Add the footnotes of the examples (DocxEmitter.footnotes); return
    (footnotes.xml, document.xml) with every note numbered in the order its
    mark comes in the text.

    Word pairs a mark with its note by id; LibreOffice pairs them by the
    ids' order (measured): with the ids out of text order, a note in an
    example showed the next note's text under its number, and so did the
    notes in footnotes.xml put in text order.  Ids that rise with the text
    satisfy both.  The separators (no mark refers to them) keep theirs.
    """
    xml = footnotes_xml.replace(
        "</w:footnotes>", "".join(x for _id, x in notes) + "</w:footnotes>", 1)
    marks = re.findall(r'<w:footnoteReference\b[^>]*\bw:id="(-?\d+)"', document_xml)
    new = {old: str(k + 1) for k, old in enumerate(dict.fromkeys(marks))}

    def renumber(m: re.Match[str]) -> str:
        return f'{m.group(1)}{new.get(m.group(2), m.group(2))}"'
    entries = list(re.finditer(r'<w:footnote\b[^>]*\bw:id="(-?\d+)"[^>]*>.*?</w:footnote>',
                               xml, re.S))
    fixed = [e.group(0) for e in entries if e.group(1) not in new]
    marked = sorted((e for e in entries if e.group(1) in new),
                    key=lambda e: int(new[e.group(1)]))
    body = "".join(fixed + [re.sub(r'(<w:footnote\b[^>]*\bw:id=")(-?\d+)"', renumber,
                                   e.group(0), count=1) for e in marked])
    if entries:
        xml = xml[:entries[0].start()] + body + xml[entries[-1].end():]
    document_xml = re.sub(r'(<w:footnoteReference\b[^>]*\bw:id=")(-?\d+)"',
                          renumber, document_xml)
    return xml, document_xml


def unique_odt_note_ids(content_xml: str) -> str:
    """Give every text:note an id of its own.

    An example pandoc renders on its own (something in it the renderer does
    not handle) numbers its notes from ftn0 again, and a note reference
    found the first of two notes called ftn0 -- the wrong one.  A repeat is
    renamed; a reference never names one of those, whose \\label pandoc
    dropped.
    """
    seen: set[str] = set()
    n = [0]

    def fix(m: re.Match[str]) -> str:
        ident = m.group(2)
        if ident in seen:
            n[0] += 1
            ident = f"{ident}_{n[0]}"
        seen.add(ident)
        return f"{m.group(1)}{ident}{m.group(3)}"
    return re.sub(r'(<text:note\b[^>]*\btext:id=")([^"]+)(")', fix, content_xml)


# -- the appendix -----------------------------------------------------------
#
# After \appendix the sections are lettered, "A", "A.1".  One outline
# numbering cannot change its format mid-document, so the appendix's
# headings take a numbering of their own: in ODF a list around each, in
# OOXML a second numbering.  The references to them are fields on those
# numbers already, and follow them (spiked: LibreOffice recomputes "A.1").

APPENDIX_LIST = "LxAppendix"


def _appendix_list_style() -> str:
    levels = "".join(
        f'<text:list-level-style-number text:level="{n}"'
        f' style:num-format="{"A" if n == 1 else "1"}" text:display-levels="{n}">'
        '<style:list-level-properties text:list-level-position-and-space-mode='
        '"label-alignment"><style:list-level-label-alignment '
        'text:label-followed-by="space"/></style:list-level-properties>'
        "</text:list-level-style-number>"
        for n in range(1, NUMBERED_LEVELS + 1))
    return f'<text:list-style style:name="{APPENDIX_LIST}">{levels}</text:list-style>'


_ODF_APPENDIX_HEADING = re.compile(
    r'<text:h\b[^>]*\btext:outline-level="(\d+)"[^>]*>(?:(?!</text:h>).)*?'
    rf'text:name="{APPENDIX}\d+".*?</text:h>', re.S)


def letter_odt_appendix(content_xml: str) -> str:
    """Each appendix heading in a list of the lettered style, nested to its
    level, continuing the one before."""
    if f'text:name="{APPENDIX}' not in content_xml:
        return content_xml

    def wrap(m: re.Match[str]) -> str:
        inner = m.group(0)
        for _ in range(int(m.group(1)) - 1):
            inner = f"<text:list><text:list-item>{inner}</text:list-item></text:list>"
        return (f'<text:list text:style-name="{APPENDIX_LIST}" text:continue-numbering="true">'
                f"<text:list-item>{inner}</text:list-item></text:list>")
    content_xml = _ODF_APPENDIX_HEADING.sub(wrap, content_xml)
    return content_xml.replace("</office:automatic-styles>",
                               _appendix_list_style() + "</office:automatic-styles>", 1)


APPENDIX_ABSTRACT_ID = 9110
APPENDIX_NUM_ID = 9111


def letter_docx_appendix(document_xml: str, numbering_xml: str) -> tuple[str, str]:
    """The appendix's heading paragraphs numbered by a lettered numbering."""
    if f'w:name="{APPENDIX}' not in document_xml:
        return document_xml, numbering_xml

    def level(i: int) -> str:
        return (_level(i).replace('<w:numFmt w:val="decimal"/>', '<w:numFmt w:val="upperLetter"/>')
                if i == 0 else _level(i))
    abstract = (f'<w:abstractNum w:abstractNumId="{APPENDIX_ABSTRACT_ID}">'
                '<w:multiLevelType w:val="multilevel"/>'
                + "".join(level(i) for i in range(NUMBERED_LEVELS)) + "</w:abstractNum>")
    m = re.search(r"<w:num\b", numbering_xml) or re.search(r"</w:numbering>", numbering_xml)
    numbering_xml = numbering_xml[:m.start()] + abstract + numbering_xml[m.start():]
    numbering_xml = numbering_xml.replace(
        "</w:numbering>", f'<w:num w:numId="{APPENDIX_NUM_ID}"><w:abstractNumId'
        f' w:val="{APPENDIX_ABSTRACT_ID}"/></w:num></w:numbering>', 1)

    def fix(m: re.Match[str]) -> str:
        para = m.group(0)
        if f'w:name="{APPENDIX}' not in para:
            return para
        style = re.search(r'<w:pStyle w:val="Heading(\d)"', para)
        ilvl = int(style.group(1)) - 1 if style else 0
        numpr = (f'<w:numPr><w:ilvl w:val="{ilvl}"/>'
                 f'<w:numId w:val="{APPENDIX_NUM_ID}"/></w:numPr>')
        ppr = re.search(r"<w:pPr\s*/>|<w:pPr>(.*?)</w:pPr>", para, re.S)
        if ppr is None:
            at = para.index(">") + 1
            return para[:at] + f"<w:pPr>{numpr}</w:pPr>" + para[at:]
        return (para[:ppr.start()] + f"<w:pPr>{_with_numpr(ppr.group(1) or '', numpr)}</w:pPr>"
                + para[ppr.end():])
    return _DOCX_PARA.sub(fix, document_xml), numbering_xml
