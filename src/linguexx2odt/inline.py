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
from collections.abc import Callable

from . import macros as _macros
from .latexutil import (INLINE_VERBATIM, Brackets, find_group, rewrite_inline_verbatim,
                        verbatim_for_pandoc, visible_spaces)

XML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}

#: character style names, defined once in styles.xml (see styles.py)
LEIPZIG = "LxLeipzig"
ITALIC = "LxItalic"
BOLD = "LxBold"
SMALLCAPS = "LxSmallCaps"
JUDGMENT = "LxJudgment"
UNDERLINE = "LxUnderline"
SUBSCRIPT = "LxSubscript"
SUPERSCRIPT = "LxSuperscript"

WRAPPERS = {
    "lpzg": LEIPZIG,
    "jdg": JUDGMENT,
    "textit": ITALIC,
    "emph": ITALIC,
    "textbf": BOLD,
    "textsc": SMALLCAPS,
    # A paper that discusses one word of each example underlines it, so
    # this is not decoration -- it is which word the example is ABOUT.
    "underline": UNDERLINE,
    "textsubscript": SUBSCRIPT,
    "textsuperscript": SUPERSCRIPT,
    "textrm": "",
    "text": "",
    "mbox": "",
    "textnormal": "",
}

#: Size switches: declarations, so no braced argument to find -- they apply
#: to the rest of their group.  Dropped rather than unhandled, and the
#: difference is not cosmetic.  An unhandled command sends its whole
#: enclosing group to pandoc as a fragment, and `{\small \begin{forest}...}`
#: then came back as "] [Voice' ...": pandoc does not know forest either, so
#: the tree lost its head.  Nothing here carries a font size anyway, so
#: dropping the switch keeps everything that was inside it.
DECLARATIONS = frozenset({
    "tiny", "scriptsize", "footnotesize", "small", "normalsize",
    "large", "Large", "LARGE", "huge", "Huge",
})

#: Commands whose braced argument is a length, and which leave no text.
#: A kern has no inline equivalent here, and an example's columns are
#: measured, not spaced by hand.
DISCARD_ARG = frozenset({"hspace", "vspace"})

SYMBOLS = {
    "dag": "†", "ddag": "‡", "S": "§", "P": "¶",
    "copyright": "©", "pounds": "£", "ldots": "…",
    "dots": "…", "textasciitilde": "~", "textbackslash": "\\",
    # what the way back writes for a "^" (an \lstinline payload has one)
    "textasciicircum": "^",
    "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ",
    "aa": "å", "AA": "Å", "o": "ø", "O": "Ø",
    "ss": "ß", "l": "ł", "L": "Ł", "i": "ı",
    "j": "ȷ", "&": "&", "%": "%", "#": "#", "$": "$", "_": "_",
    "textunderscore": "_",
    "{": "{", "}": "}", " ": " ", ",": " ", "-": "",
}

#: ``\"a`` and friends: TeX accent command -> Unicode combining mark
ACCENTS = {
    '"': "̈", "'": "́", "`": "̀", "^": "̂",
    "~": "̃", "=": "̄", ".": "̇", "u": "̆",
    "v": "̌", "H": "̋", "c": "̧", "k": "̨",
    "d": "̣", "b": "̱", "r": "̊", "t": "͡",
}


#: A reference, as the renderer's own markup carries it until an emitter
#: says what it becomes: ``render()`` asks ``ref_markup`` for ODF,
#: ``segments()`` hands it to the .docx emitter, and ``runs()`` measures the
#: text inside, which is the number as the reader will see it.
REF_MARK = re.compile(
    r'<lx:ref index="(\d+)" letter="([^"]*)" bare="([01])">(.*?)</lx:ref>',
    re.S)


#: A reference as written, found again when the renderer has given up on
#: the text around it.
REF_SOURCE = re.compile(r"\\(p?ref)\s*\{[^}]*\}")

#: What stands in for a reference while pandoc renders the rest: letters
#: and digits only, which pandoc passes through as they are.
REF_TOKEN = "LXREFTOKEN{n}X"

#: What stands in for an inline verbatim's payload while the rest of a .docx
#: cell is rendered: letters and digits only, like REF_TOKEN.
VERBATIM_TOKEN = "LXVERBTOKEN{n}X"


#: linguexx 1.4's movement arrows, \mvto{name}{text} and \mvfrom{name}{text}
#: (and their long names), with an optional [above|below|...] first.  The text
#: is a word of the example and stays; the arrow is not drawn.  Unhandled, the
#: fragment went to pandoc, which deleted the commands WITH their text:
#: "MVPLAIN \mvto{a}{LANDA} stays here \mvfrom{a}{BASEA} end." came out
#: "MVPLAIN stays here end.", the warning saying the opposite of what happened.
MOVES = frozenset({"mvto", "mvfrom", "lxMoveTo", "lxMoveFrom"})


#: Every command the renderer gives a meaning of its own.  A document's
#: \newcommand over one of these is refused, as LaTeX refuses it.
KNOWN_COMMANDS = frozenset(
    set(WRAPPERS) | set(SYMBOLS) | set(ACCENTS) | DECLARATIONS | DISCARD_ARG
    | MOVES | {"ref", "pref", "begin", "end", "Tree", "qtree"})


class Unsupported(Exception):
    """Raised when the hand-rolled renderer meets something it does not know."""


def esc(text: str) -> str:
    for k, v in XML_ESCAPES.items():
        text = text.replace(k, v)
    return text


def _unesc(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


class InlineRenderer:
    def __init__(self, warn: Callable[[str], None] | None = None) -> None:
        self.warn = warn or (lambda _m: None)
        self._cache: dict[str, str] = {}
        self.fallback_styles: list[str] = []
        """Automatic <style:style> definitions harvested from pandoc
        fallbacks; postprocess.py injects these into content.xml."""
        self._style_seq = 0
        self.labels: dict[str, tuple[int, str]] = {}
        """label -> (example index, sub-example letter): what \\ref names."""
        self.custom_labels: dict[str, tuple[str, str]] = {}
        """label -> (custom label, letter), for an example written \\ex.[(7)]."""
        self._moves_said = False
        self.brackets = None
        """The document's \\ExLBr/\\ExRBr, for the number a reference shows."""
        self.macros: dict[str, _macros.Macro] = {}
        """The document's own macros, expanded before anything is rendered."""
        self.ref_markup: Callable[..., str] | None = None
        """(index, letter, bare=) -> the target's reference markup, for
        render().  None leaves the number as text."""

    # -- public ----------------------------------------------------------
    def render(self, latex: str) -> str:
        """Return OpenDocument inline XML for a LaTeX fragment."""
        if not latex.strip():
            return ""
        latex = _macros.expand(latex, self.macros, self.warn)
        try:
            xml = self._render(latex)
        except Unsupported as exc:
            # Inline verbatim is pandoc's to render, and rendered right:
            # linguexx 1.4 allows it in an example, so it is no warning.
            if str(exc) not in {f"unhandled command \\{v}" for v in INLINE_VERBATIM}:
                self.warn(f"{exc}; fragment rendered by pandoc: {latex.strip()[:50]!r}")
            xml = self._pandoc_keeping_references(verbatim_for_pandoc(latex))
        if self.ref_markup is None:
            return REF_MARK.sub(lambda m: m.group(4), xml)
        return REF_MARK.sub(
            lambda m: self.ref_markup(int(m.group(1)), _unesc(m.group(2)),
                                      bare=m.group(3) == "1"), xml)

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
        return [(text, sc) for text, sc, _ref in self.segments(latex)]

    def segments(self, latex: str) -> list[tuple[str, bool, tuple | None]]:
        """``runs()``, with each reference kept apart as its own segment and
        its (index, letter, bare) attached -- what a target that builds
        its own reference markup (.docx) needs.  Its text is the number as
        it will be shown, so measuring it measures the page."""
        latex = _macros.expand(latex, self.macros, self.warn)
        try:
            xml = self._render(latex)
        except Unsupported:
            xml = self._verbatim_as_text(latex)
            if xml is None:
                # Nothing rendered it, so the source as written -- except its
                # references, which are still references: printed as source
                # they were "\ref{a}" in a .docx cell, and measured as that.
                xml = self._with_references(latex, esc)

        runs: list[tuple[str, bool, tuple | None]] = []
        spans: list[str] = []                  # open <text:span> styles
        buf: list[str] = []

        def flush() -> None:
            if buf:
                runs.append(("".join(buf), self._small_caps(spans), None))
                buf.clear()

        i = 0
        while i < len(xml):
            ref = REF_MARK.match(xml, i) if xml[i] == "<" else None
            if ref:
                flush()
                runs.append((ref.group(4), self._small_caps(spans),
                             (int(ref.group(1)), _unesc(ref.group(2)),
                              ref.group(3) == "1")))
                i = ref.end()
                continue
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

        return [(_unesc(t), sc, ref) for t, sc, ref in runs]

    def _verbatim_as_text(self, latex: str) -> str | None:
        r"""The fragment rendered with its inline verbatim as plain text, or
        None if something else in it is unhandled too.

        For the .docx, which has no pandoc fallback for a cell: the verbatim
        went there as source, "\verb|x_1|".  Each payload goes over as a
        token (letters only, which the renderer passes through) and comes
        back as its text -- the right characters, without the typewriter
        face, which a cell does not carry for code anyway.
        """
        payloads: list[str] = []

        def token(payload: str, starred: bool) -> str:
            payloads.append(visible_spaces(payload, starred))
            return VERBATIM_TOKEN.format(n=len(payloads) - 1)

        masked = rewrite_inline_verbatim(latex, token)
        if not payloads:
            return None
        try:
            xml = self._render(masked)
        except Unsupported:
            return None
        for n, payload in enumerate(payloads):
            xml = xml.replace(VERBATIM_TOKEN.format(n=n), esc(payload), 1)
        return xml

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

        if name in DECLARATIONS:
            # A control word absorbs the whitespace after it, so `{\small x}`
            # is "x" and not " x".  It matters: the width estimator measures
            # this string, and a leading space in a cell is a column that
            # does not line up with the one above it.
            while j < len(s) and s[j] in " \t\n":
                j += 1
            return j

        if name in DISCARD_ARG:
            k = j + 1 if j < len(s) and s[j] == "*" else j
            grp = find_group(s, k)
            if grp is None:
                raise Unsupported(f"\\{name} without a braced length")
            return grp[1]

        if name in ("begin", "end"):
            end = self._tree_environment(s, name, j, out)
            if end is not None:
                return end

        if name in ("Tree", "qtree"):
            return self._qtree(s, j, out)

        if name in ("ref", "pref"):
            return self._reference(s, name, j, out)

        if name in MOVES:
            k = j
            while k < len(s) and s[k] in " \t\n":
                k += 1
            if k < len(s) and s[k] == "[":  # [above], [level=2], ...
                close = s.find("]", k)
                if close < 0:
                    raise Unsupported(f"\\{name} with an unclosed [option]")
                k = close + 1
            named = find_group(s, k)
            text = find_group(s, named[1]) if named is not None else None
            if named is None or text is None:
                raise Unsupported(f"\\{name} without {{name}}{{text}}")
            if not self._moves_said:
                self._moves_said = True
                self.warn("movement arrows (\\mvto, \\mvfrom) are not drawn; "
                          "the words they mark are kept")
            out.append(self._render(text[0]))
            return text[1]

        raise Unsupported(f"unhandled command \\{name}")

    # -- references ---------------------------------------------------------
    def _reference(self, s: str, name: str, j: int, out: list[str]) -> int:
        r"""``\ref{x}``/``\pref{x}`` -> a reference the emitter makes a field.

        It was an unhandled command, so the .odt sent the whole cell to
        pandoc, which knows nothing of example labels and printed "[x]" or
        nothing, and the .docx printed the source.  A label no example
        carries is printed as LaTeX prints it, ``??``, and named.
        """
        grp = find_group(s, j)
        if grp is None:
            raise Unsupported(f"\\{name} without a braced label")
        label, bare = grp[0].strip(), name == "pref"
        br = self.brackets or Brackets()
        left, right = ("", "") if bare else (br.ex_l, br.ex_r)
        if label in self.custom_labels:
            # A custom label is not a number: text, which nothing renumbers.
            custom, letter = self.custom_labels[label]
            out.append(esc(br.custom_reference(custom, letter, bare)))
            return grp[1]
        if label not in self.labels:
            self.warn(f"\\{name}{{{label}}} inside an example: no example is "
                      f"labelled {label!r}; printed as ??")
            out.append(esc(f"{left}??{right}"))
            return grp[1]
        index, letter = self.labels[label]
        shown = f"{left}{index + 1}{letter}{right}"
        out.append(f'<lx:ref index="{index}" letter="{esc(letter)}" '
                   f'bare="{int(bare)}">{esc(shown)}</lx:ref>')
        return grp[1]

    def _with_references(self, latex: str, text) -> str:
        """*latex* with each \\ref and \\pref rendered as a reference, and
        everything between passed through *text*."""
        out, pos = [], 0
        for m in REF_SOURCE.finditer(latex):
            out.append(text(latex[pos:m.start()]))
            out.append(self._render(m.group(0)))
            pos = m.end()
        out.append(text(latex[pos:]))
        return "".join(out)

    def _pandoc_keeping_references(self, latex: str) -> str:
        r"""The pandoc fallback, with the references kept out of it.

        Pandoc knows no example label, so a cell sent to it for any one
        unknown command lost every \ref in it.  Each goes over as a token
        and comes back as the reference it stood for.
        """
        refs = [m.group(0) for m in REF_SOURCE.finditer(latex)]
        if not refs:
            return self._pandoc(latex)
        counter = iter(range(len(refs)))
        xml = self._pandoc(REF_SOURCE.sub(
            lambda _m: REF_TOKEN.format(n=next(counter)), latex))
        for n, ref in enumerate(refs):
            token = REF_TOKEN.format(n=n)
            if token not in xml:
                self.warn(f"{ref} was inside LaTeX pandoc dropped, and is "
                          f"missing from the output")
            xml = xml.replace(token, self._render(ref), 1)
        return xml

    # -- trees ------------------------------------------------------------
    #: environments whose body is bracket notation the Writer macro can draw
    TREE_ENVIRONMENTS = ("forest",)

    def _tree_environment(self, s: str, name: str, j: int, out: list[str]):
        r"""``\begin{forest} … \end{forest}`` -> its bracket notation, as text.

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
        # baseline only places the example number level with the root --
        # docx2linguexx writes it -- and the macro, which draws its own
        # number, refuses a node option it does not know.
        body = re.sub(r"\s*,\s*baseline(?=[\s,\]\[])", "", body)
        # The characters forest needs escaped (a gap "\_\_") are plain text
        # to the macro, which refuses anything with a backslash.
        body = re.sub(r"\\([_&#%$])", r"\1", body)
        self.warn(
            f"{env} tree kept as bracket notation; open the file in Writer, select it and "
            f"run LinguExx > Typeset unnumbered tree (the example already "
            f"supplies the number)"
        )
        out.append(esc(body))
        return stop + len(close)

    def _qtree(self, s: str, j: int, out: list[str]) -> int:
        r"""qtree's ``\Tree [.S [.NP ] ]`` -> the same notation, undotted.

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
            "qtree tree kept as bracket notation; open the file in Writer, select it and "
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
