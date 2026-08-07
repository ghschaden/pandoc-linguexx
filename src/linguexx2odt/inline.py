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

"""LaTeX inline fragment -> OpenDocument inline markup.

Two-tier strategy, exactly as the plan prescribes:

1. a hand-rolled renderer for the constructs that actually occur inside
   linguistic examples (accents, ``\\lpzg``, the font commands, quotes,
   dashes);
2. for anything it does not know, hand the *whole fragment* to
   ``pandoc -f latex -t opendocument`` and unwrap the paragraph — with a
   warning naming the construct, so silent degradation never happens.
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from typing import Callable

from .latexutil import find_group

XML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}

#: character style names, defined once in styles.xml (see styles.py)
LEIPZIG = "LxLeipzig"
ITALIC = "LxItalic"
BOLD = "LxBold"
SMALLCAPS = "LxSmallCaps"
JUDGMENT = "LxJudgment"

WRAPPERS = {
    "lpzg": LEIPZIG,
    "jdg": JUDGMENT,
    "textit": ITALIC,
    "emph": ITALIC,
    "textbf": BOLD,
    "textsc": SMALLCAPS,
    "textrm": "",
    "text": "",
    "mbox": "",
    "textnormal": "",
}

SYMBOLS = {
    "dag": "†", "ddag": "‡", "S": "§", "P": "¶",
    "copyright": "©", "pounds": "£", "ldots": "…",
    "dots": "…", "textasciitilde": "~", "textbackslash": "\\",
    "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ",
    "aa": "å", "AA": "Å", "o": "ø", "O": "Ø",
    "ss": "ß", "l": "ł", "L": "Ł", "i": "ı",
    "j": "ȷ", "&": "&", "%": "%", "#": "#", "$": "$", "_": "_",
    "{": "{", "}": "}", " ": " ", ",": " ", "-": "",
}

#: ``\"a`` and friends: TeX accent command -> Unicode combining mark
ACCENTS = {
    '"': "̈", "'": "́", "`": "̀", "^": "̂",
    "~": "̃", "=": "̄", ".": "̇", "u": "̆",
    "v": "̌", "H": "̋", "c": "̧", "k": "̨",
    "d": "̣", "b": "̱", "r": "̊", "t": "͡",
}


class Unsupported(Exception):
    """Raised when the hand-rolled renderer meets something it does not know."""


def esc(text: str) -> str:
    for k, v in XML_ESCAPES.items():
        text = text.replace(k, v)
    return text


class InlineRenderer:
    def __init__(self, warn: Callable[[str], None] | None = None) -> None:
        self.warn = warn or (lambda _m: None)
        self._cache: dict[str, str] = {}
        self.fallback_styles: list[str] = []
        """Automatic <style:style> definitions harvested from pandoc
        fallbacks; postprocess.py injects these into content.xml."""
        self._style_seq = 0

    # -- public ----------------------------------------------------------
    def render(self, latex: str) -> str:
        """Return OpenDocument inline XML for a LaTeX fragment."""
        if not latex.strip():
            return ""
        try:
            return self._render(latex)
        except Unsupported as exc:
            self.warn(f"{exc}; fragment rendered by pandoc: {latex.strip()[:50]!r}")
            return self._pandoc(latex)

    #: character styles that draw their text as small capitals
    SMALLCAPS_STYLES = frozenset({LEIPZIG, SMALLCAPS})

    def plain(self, latex: str) -> str:
        """Approximate rendered text, used only for column-width guessing."""
        return "".join(text for text, _small_caps in self.runs(latex))

    def runs(self, latex: str) -> list[tuple[str, bool]]:
        """Approximate rendered text as (text, is_small_caps) runs.

        Width estimation needs to know which parts are small caps and
        cannot get that from the flattened string: a small capital is the
        capital drawn at Layout.sc_ratio, which is *wider* than the
        lowercase letter it replaces, so a ``\\lpzg`` gloss measured as
        lowercase comes out too narrow for what is put in it.
        """
        try:
            xml = self._render(latex)
        except Unsupported:
            xml = ""
            depth = 0
            for ch in latex:
                if ch == "\\":
                    depth = 0
                xml += ch

        runs: list[tuple[str, bool]] = []
        spans: list[str] = []                  # open <text:span> styles
        buf: list[str] = []

        def flush() -> None:
            if buf:
                runs.append(("".join(buf), self._small_caps(spans)))
                buf.clear()

        i = 0
        while i < len(xml):
            if xml[i] == "<":
                j = xml.find(">", i)
                tag = xml[i + 1:j] if j >= 0 else ""
                if tag.startswith("text:span") and not tag.endswith("/"):
                    flush()
                    m = re.search(r'text:style-name="([^"]*)"', tag)
                    spans.append(m.group(1) if m else "")
                elif tag == "/text:span" and spans:
                    flush()
                    spans.pop()
                i = len(xml) if j < 0 else j + 1
                continue
            buf.append(xml[i])
            i += 1
        flush()

        return [
            (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"), sc)
            for t, sc in runs
        ]

    def _small_caps(self, spans: list[str]) -> bool:
        return any(name in self.SMALLCAPS_STYLES for name in spans)

    # -- hand-rolled renderer --------------------------------------------
    def _render(self, s: str) -> str:
        out: list[str] = []
        i, n = 0, len(s)
        while i < n:
            c = s[i]
            if c == "\\":
                i = self._command(s, i, out)
                continue
            if c == "{":
                grp = find_group(s, i)
                if grp is None:
                    raise Unsupported("unbalanced brace group")
                out.append(self._render(grp[0]))
                i = grp[1]
                continue
            if c == "}":
                raise Unsupported("unbalanced closing brace")
            if c == "~":
                out.append(" ")
                i += 1
                continue
            if c == "$":
                raise Unsupported("math mode is out of scope for v1")
            if c == "%":
                raise Unsupported("unescaped % in an example body")
            if c == "-":
                run = len(s[i:]) - len(s[i:].lstrip("-"))
                out.append({1: "-", 2: "–", 3: "—"}.get(run, "-" * run))
                i += run
                continue
            if c == "`":
                double = s[i : i + 2] == "``"
                out.append("“" if double else "‘")
                i += 2 if double else 1
                continue
            if c == "'":
                double = s[i : i + 2] == "''"
                out.append("”" if double else "’")
                i += 2 if double else 1
                continue
            out.append(esc(c))
            i += 1
        return "".join(out)

    def _command(self, s: str, i: int, out: list[str]) -> int:
        rest = s[i + 1 :]
        if not rest:
            raise Unsupported("trailing backslash")

        # \\ -> line break
        if rest[0] == "\\":
            out.append("<text:line-break/>")
            return i + 2

        name = ""
        j = i + 1
        while j < len(s) and (s[j].isalpha() or s[j] == "@"):
            name += s[j]
            j += 1
        if not name:  # single-character control sequence
            name, j = s[i + 1], i + 2

        if name in WRAPPERS:
            grp = find_group(s, j)
            if grp is None:
                raise Unsupported(f"\\{name} without a braced argument")
            style = WRAPPERS[name]
            inner = self._render(grp[0])
            out.append(
                f'<text:span text:style-name="{style}">{inner}</text:span>'
                if style
                else inner
            )
            return grp[1]

        if name in ACCENTS:
            grp = find_group(s, j)
            if grp is not None:
                base, end = grp[0], grp[1]
            else:
                k = j
                while k < len(s) and s[k] in " \t":
                    k += 1
                if k >= len(s):
                    raise Unsupported(f"accent \\{name} with nothing to put it on")
                base, end = s[k], k + 1
            base_rendered = self._render(base) if base != "" else ""
            out.append(unicodedata.normalize("NFC", base_rendered + ACCENTS[name]))
            return end

        if name in SYMBOLS:
            out.append(esc(SYMBOLS[name]))
            return j

        if name in ("begin", "end"):
            end = self._tree_environment(s, name, j, out)
            if end is not None:
                return end

        if name in ("Tree", "qtree"):
            return self._qtree(s, j, out)

        raise Unsupported(f"unhandled command \\{name}")

    # -- trees ------------------------------------------------------------
    #: environments whose body is bracket notation the Writer macro can draw
    TREE_ENVIRONMENTS = ("forest",)

    def _tree_environment(self, s: str, name: str, j: int, out: list[str]):
        """``\begin{forest} … \end{forest}`` -> its bracket notation, as text.

        Handed to pandoc this became ``]]]`` — the tree gone and three
        closing brackets left behind, which is not the "degrades to
        readable output" this converter promises anywhere else.  There is
        no way to *draw* it from here (that needs the draw shapes only
        Writer can make), but the brackets are exactly what the macro
        reads, so they are kept whole and the warning says what to do with
        them.
        """
        grp = find_group(s, j)
        if grp is None or grp[0] not in self.TREE_ENVIRONMENTS:
            return None
        env = grp[0]
        if name == "end":                     # a stray \end: nothing to keep
            return grp[1]

        close = f"\\end{{{env}}}"
        stop = s.find(close, grp[1])
        if stop < 0:
            raise Unsupported(f"\\begin{{{env}}} is never closed")

        body = " ".join(s[grp[1]:stop].split())
        self.warn(
            f"{env} tree kept as bracket notation; select it in Writer and "
            f"run LinguExx > Typeset unnumbered tree (the example already "
            f"supplies the number)"
        )
        out.append(esc(body))
        return stop + len(close)

    def _qtree(self, s: str, j: int, out: list[str]) -> int:
        """qtree's ``\Tree [.S [.NP ] ]`` -> the same notation, undotted.

        qtree marks a label with a leading dot; the macro does not, so the
        dots come off and what is left is notation it can draw.
        """
        depth, k = 0, j
        while k < len(s) and s[k] in " \t":
            k += 1
        start = k
        while k < len(s):
            if s[k] == "[":
                depth += 1
            elif s[k] == "]":
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
        if depth != 0:
            raise Unsupported("\\Tree without a balanced bracket group")

        body = " ".join(s[start:k].split()).replace("[.", "[")
        self.warn(
            "qtree tree kept as bracket notation; select it in Writer and "
            "run LinguExx > Typeset unnumbered tree (the example already "
            "supplies the number)"
        )
        out.append(esc(body))
        return k

    # -- pandoc fallback --------------------------------------------------
    def _pandoc(self, latex: str) -> str:
        key = latex.strip()
        if key in self._cache:
            return self._cache[key]
        try:
            doc = subprocess.run(
                ["pandoc", "-f", "latex", "-t", "opendocument", "-s"],
                input=key, capture_output=True, text=True, check=True, timeout=30,
            ).stdout
        except (subprocess.SubprocessError, OSError) as exc:
            self.warn(f"pandoc fallback failed ({exc}); emitting literal text")
            self._cache[key] = esc(key)
            return self._cache[key]

        body = _unwrap_paragraph(_body_of(doc))
        # pandoc names its automatic styles T1, T2, ... — those names mean
        # something else in the surrounding document, so rename before use.
        for old, block in _text_styles(doc).items():
            self._style_seq += 1
            new = f"LxFb{self._style_seq}"
            self.fallback_styles.append(
                block.replace(f'style:name="{old}"', f'style:name="{new}"', 1)
            )
            body = body.replace(f'text:style-name="{old}"', f'text:style-name="{new}"')
        if "<draw:" in body:
            self.warn("pandoc rendered the fragment as a drawing/formula object; "
                      "reduced to plain text")
            body = re.sub(r"<draw:[^>]*>.*?</draw:[^>]*>|<draw:[^>]*/>", "", body, flags=re.S)
        self._cache[key] = body
        return body


def _body_of(doc: str) -> str:
    i = doc.find("<office:text>")
    j = doc.rfind("</office:text>")
    return doc[i + len("<office:text>") : j] if i >= 0 and j > i else doc


def _text_styles(doc: str) -> dict[str, str]:
    """Automatic character styles from a standalone pandoc fragment."""
    i = doc.find("<office:automatic-styles>")
    j = doc.find("</office:automatic-styles>")
    if i < 0 or j < 0:
        return {}
    out = {}
    for m in re.finditer(
        r'<style:style style:name="([^"]+)" style:family="text".*?</style:style>',
        doc[i:j], flags=re.S,
    ):
        out[m.group(1)] = m.group(0)
    return out


def _unwrap_paragraph(xml: str) -> str:
    """Strip the outer <text:p …>…</text:p> pandoc wraps a fragment in."""
    xml = xml.strip()
    parts = []
    while xml.startswith("<text:p"):
        open_end = xml.find(">")
        close = xml.rfind("</text:p>")
        if open_end < 0 or close < 0:
            break
        parts.append(xml[open_end + 1 : close])
        xml = xml[close + len("</text:p>") :].strip()
    return "<text:line-break/>".join(parts) if parts else xml
