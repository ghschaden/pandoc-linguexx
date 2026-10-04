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
r"""``docx2linguexx`` and ``odt2linguexx`` -- the way back to LaTeX.

For a document whose examples this project made (plan-reverse.md, tier A).
Each example table becomes a linguexx example again, each example number a
counter, each reference to one a ``\ref`` or ``\pref``; everything else is
pandoc's LaTeX writer, as everything else on the way in is pandoc's reader.

An .odt goes through LibreOffice to .docx first and is then read like any
other: pandoc's ODT reader drops a reference's text outright ("Refs: (),
(a)"), and LibreOffice's export keeps the styles, the sequence fields and
the references (plan-reverse.md, S3 and S4).

Labels are generated, ``ex:1``, ``ex:2a`` -- the document never had the
author's: the forward path names its bookmarks NumEx0, NumEx1.  An example
gets a label only if something refers to it.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from . import untypeset as U
from .ir import Body, Example
from .latexutil import Brackets
from .styles_docx import GAP_PARA

PROG = "docx2linguexx"

#: The package, as the converter's own test documents load it: the dot
#: syntax (\ex. \a.) is linguexx's [lazy] option.
PACKAGE = r"\usepackage[lazy]{linguexx}"


# -- the XML -------------------------------------------------------------

def _register_namespaces(xml: bytes) -> None:
    """Keep the document's own prefixes when it is written back.  pandoc
    does not care what they are called; a prefix ElementTree invented
    (ns0:) would be fine for it too, but a reader of the intermediate
    should be able to recognise a w:p."""
    for _event, (prefix, uri) in ET.iterparse(BytesIO(xml), events=("start-ns",)):
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass


def _token_run(text: str) -> ET.Element:
    r = ET.Element(U.w("r"))
    t = ET.SubElement(r, U.w("t"))
    t.text = text
    return r


def _token_para(text: str) -> ET.Element:
    p = ET.Element(U.w("p"))
    p.append(_token_run(text))
    return p


def _replace_refs(root: ET.Element, marks: set[str], ctx: U.Context) -> None:
    """Every REF field whose bookmark is an example's -> one placeholder
    run.  The cached number would otherwise reach the LaTeX as a number,
    which renumbers nothing; any other REF is left to pandoc."""
    parent = {c: p for p in root.iter() for c in p}

    def target(instr: str) -> str | None:
        words = instr.split()
        if len(words) > 1 and words[0].upper() == "REF" and words[1] in marks:
            return words[1]
        return None

    for fs in list(root.iter(U.w("fldSimple"))):
        name = target(fs.get(U.w("instr"), ""))
        if name:
            par = parent[fs]
            par.insert(list(par).index(fs), _token_run(ctx.ref_token(name)))
            par.remove(fs)

    for p in list(root.iter(U.w("p"))):
        depth, instr, members = 0, "", []
        for r in list(p.iter(U.w("r"))):
            fc = r.find(U.w("fldChar"))
            kind = fc.get(U.w("fldCharType")) if fc is not None else None
            if kind == "begin":
                if depth == 0:
                    instr, members = "", []
                depth += 1
            if depth == 0:
                continue
            members.append(r)
            it = r.find(U.w("instrText"))
            if depth == 1 and it is not None:
                instr += it.text or ""
            if kind == "end":
                depth -= 1
                if depth == 0:
                    name = target(instr)
                    if name:
                        first = members[0]
                        par = parent[first]
                        par.insert(list(par).index(first),
                                   _token_run(ctx.ref_token(name)))
                        for m in members:
                            parent[m].remove(m)


@dataclass
class Read:
    """What the .docx gave back."""

    examples: list[Example] = field(default_factory=list)
    marks: dict[str, int] = field(default_factory=dict)
    """bookmark -> the example's position in the document."""

    brackets: Brackets = field(default_factory=Brackets)
    ctx: U.Context | None = None
    members: dict[str, bytes] = field(default_factory=dict)
    """The rewritten parts, for pandoc."""


def read_docx(path: Path) -> Read:
    """Read the examples out of *path*, and rewrite it for pandoc with a
    placeholder where each example and each reference to one stood."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        doc_xml = z.read("word/document.xml")
        styles = U.Styles.read(z.read("word/styles.xml")
                               if "word/styles.xml" in names else None)
        notes_xml = {n: z.read(f"word/{n}s.xml") for n in ("footnote", "endnote")
                     if f"word/{n}s.xml" in names}
    for xml in (doc_xml, *notes_xml.values()):
        _register_namespaces(xml)

    root = ET.fromstring(doc_xml)
    note_roots = {n: ET.fromstring(x) for n, x in notes_xml.items()}
    ctx = U.Context(styles=styles)
    for kind, nroot in note_roots.items():
        for note in nroot.findall(U.w(kind)):
            ctx.notes[f"{kind}:{note.get(U.w('id'))}"] = note

    out = Read(ctx=ctx)
    parent = {c: p for p in root.iter() for c in p}

    tables = []
    for tbl in root.iter(U.w("tbl")):
        rows = U.read_rows(tbl, styles)
        if U.is_example_table(rows):
            tables.append((tbl, rows))
    # Bookmarks first: an example may refer to one further down.
    for k, (_tbl, rows) in enumerate(tables):
        body = [r for r in rows if r and not U.is_spacer(r)]
        for name in (body[0][0].bookmarks if body and body[0] else []):
            out.marks.setdefault(name, k)
    marks = set(out.marks)

    found_brackets = None
    for k, (tbl, rows) in enumerate(tables):
        ex, br, _ = U.read_example(rows, k, ctx, marks)
        out.examples.append(ex)
        if br is not None and found_brackets is None:
            found_brackets = br
        par = parent.get(tbl)
        if par is None:
            continue
        if par.tag == U.w("tc"):
            ctx.warnings.append(
                f"example {k + 1} is inside another table; it is set as an "
                f"example there, which linguexx may not allow")
        i = list(par).index(tbl)
        par.remove(tbl)
        par.insert(i, _token_para(U.EXAMPLE_TOKEN.format(n=k)))
    if found_brackets is not None:
        out.brackets = found_brackets
    out.brackets = _sub_brackets(out.examples, out.brackets)

    # The 1 pt paragraph that keeps two .docx examples apart in Word.
    for p in list(root.iter(U.w("p"))):
        if U.para_style(p, styles) == GAP_PARA and not "".join(p.itertext()).strip():
            parent[p].remove(p)

    for r in (root, *note_roots.values()):
        _replace_refs(r, marks, ctx)
    out.members["word/document.xml"] = ET.tostring(root, encoding="utf-8",
                                                   xml_declaration=True)
    for n, nroot in note_roots.items():
        out.members[f"word/{n}s.xml"] = ET.tostring(nroot, encoding="utf-8",
                                                    xml_declaration=True)
    return out


def _sub_brackets(examples: list[Example], br: Brackets) -> Brackets:
    """\\SubExLBr and friends, from the first marker at each level."""
    for level, (lf, rf) in ((1, ("sub_l", "sub_r")), (2, ("subsub_l", "subsub_r"))):
        it = next((i for e in examples for i in e.items if i.level == level), None)
        if it is None:
            continue
        core = U.marker_core(it.marker)
        if core and core in it.marker:
            left, _, right = it.marker.partition(core)
            br = Brackets(**{**br.__dict__, lf: left, rf: right})
    return br


# -- IR -> linguexx ------------------------------------------------------

def _word(cell: str) -> str:
    """A gloss word: empty is {}, and several words are one, braced."""
    if not cell:
        return "{}"
    if re.search(r"\s", _visible(cell)):
        return "{" + cell + "}"
    return cell


def _visible(latex: str) -> str:
    """The text of *latex* with its commands' names left out, to ask
    whether a cell is one word or several."""
    return re.sub(r"\\[a-zA-Z]+\s*|[{}]", "", latex)


def _guard(text: str) -> str:
    r"""Text that would read as something else at the head of an example:
    a [ as \ex.'s optional label, a mark as a judgment."""
    if text[:1] == "[" or (text[:1] in "*?" and text.strip()):
        return "{}" + text
    return text


def body_source(b: Body) -> str:
    j = b.judgment
    if b.tiers:
        n = len(b.tiers)
        cmd = {2: r"\gll", 3: r"\glll"}.get(n, r"\gl")
        lines = []
        for t, tier in enumerate(b.tiers):
            words = " ".join(_word(c) for c in tier.cells)
            if t == 0 and b.annot:
                words += f" \\exannot{{{b.annot}}}"
            lines.append(words + r"\\")
        src = f"{j}{cmd} " + "\n     ".join(lines)
        if cmd == r"\gl":
            src += r" \endgl"
    else:
        src = j + (b.text if b.text.startswith("%") else _guard(b.text) if not j else b.text)
        if b.annot:
            src += f"\\exannot{{{b.annot}}}"
    if b.translation:
        src += "\n\\glt " + b.translation
    return src


def _item_command(ordinal: int) -> str:
    r"""\a. opens a level; any other letter is the next item at it.  Only
    \a. to \f. exist (linguexx's [lazy]), so past the sixth, \f. it is."""
    return "\\" + "abcdef"[min(ordinal, 6) - 1] + "."


def example_source(ex: Example, label: str, sublabels: dict[int, str]) -> str:
    head = r"\ex."
    if ex.custom_label:
        head += f"[{ex.custom_label}]"
    if label:
        head += f"\\label{{{label}}}"
    if ex.body is not None:
        return f"{head} {body_source(ex.body)}"
    lines = [f"{head} {_guard(ex.head)}" if ex.head else head]
    level = 0
    for k, it in enumerate(ex.items):
        if it.level < level:
            lines.append(r"\z.")
        level = it.level
        cmd = _item_command(it.ordinal)
        if k in sublabels:
            cmd += f"\\label{{{sublabels[k]}}}"
        lines.append(f"{cmd} {body_source(it.body)}")
    return "\n".join(lines)


# -- references ----------------------------------------------------------

def _alternatives(s: str) -> str:
    """How a bracket may have reached the LaTeX: as itself, or as pandoc
    writes a [ or ] that could be taken for an optional argument."""
    if not s:
        return ""
    forms = {re.escape(s)}
    pandoc = s.replace("[", "{[}").replace("]", "{]}")
    forms.add(re.escape(pandoc))
    return "|".join(sorted(forms, key=len, reverse=True))


@dataclass
class Labels:
    examples: dict[int, str] = field(default_factory=dict)
    items: dict[int, dict[int, str]] = field(default_factory=dict)


class References:
    """Turns the placeholders back into \\ref and \\pref."""

    def __init__(self, read: Read):
        self.read = read
        br = read.brackets
        left, right = _alternatives(br.ex_l), _alternatives(br.ex_r)
        self.pattern = re.compile(
            (f"(?P<l>{left})?" if left else "(?P<l>)")
            + r"LXREF(?P<n>\d+)X(?P<tail>[a-z]*)"
            + (f"(?P<r>{right})?" if right else "(?P<r>)"))
        self.bare = not (br.ex_l or br.ex_r)

    def _target(self, m: re.Match) -> tuple[int, int | None, str]:
        """(example, item or None, the tail that is not a letter of it)."""
        k = self.read.marks[self.read.ctx.refs[int(m.group("n"))]]
        ex = self.read.examples[k]
        tail = m.group("tail")
        if tail:
            for i, it in enumerate(ex.items):
                if U.marker_core(it.marker) == tail:
                    return k, i, ""
        return k, None, tail

    def labels(self, text: str) -> Labels:
        out = Labels()
        used: set[str] = set()
        for m in self.pattern.finditer(text):
            k, item, _ = self._target(m)
            out.examples.setdefault(k, f"ex:{k + 1}")
            if item is not None:
                items = out.items.setdefault(k, {})
                if item not in items:
                    name = f"ex:{k + 1}{U.marker_core(self.read.examples[k].items[item].marker)}"
                    while name in used:
                        name += "x"
                    items[item] = name
            used.update(out.examples.values())
            for d in out.items.values():
                used.update(d.values())
        return out

    def resolve(self, text: str, labels: Labels) -> str:
        def sub(m: re.Match) -> str:
            k, item, tail = self._target(m)
            name = (labels.items[k][item] if item is not None
                    else labels.examples[k])
            left, right = m.group("l") or "", m.group("r") or ""
            if left and right and not tail and not self.bare:
                return f"\\ref{{{name}}}"
            return f"{left}\\pref{{{name}}}{tail}{right}"
        return self.pattern.sub(sub, text)


# -- the document --------------------------------------------------------

def _preamble(br: Brackets) -> str:
    lines = [PACKAGE]
    default = Brackets()
    for field_name, macro in (("ex_l", "ExLBr"), ("ex_r", "ExRBr"),
                              ("sub_l", "SubExLBr"), ("sub_r", "SubExRBr"),
                              ("subsub_l", "SubSubExLBr"),
                              ("subsub_r", "SubSubExRBr")):
        value = getattr(br, field_name)
        if value != getattr(default, field_name):
            lines.append(f"\\renewcommand{{\\{macro}}}{{{value}}}")
    return "\n".join(lines)


def _pandoc(args: list[str], **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["pandoc", *args], check=True,
                              capture_output=True, text=True, **kw)
    except FileNotFoundError:
        sys.exit(f"{PROG}: pandoc is not on PATH (see README for the minimum version)")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"{PROG}: pandoc failed\n{exc.stderr.strip()}")


def convert(docx: Path, out: Path, warn) -> int:
    """*docx* -> *out*, a LaTeX document.  Returns the number of examples."""
    read = read_docx(docx)
    with tempfile.TemporaryDirectory(prefix="docx2linguexx-") as tmpdir:
        tmp = Path(tmpdir) / "placeholders.docx"
        _rewrite(docx, tmp, read.members)
        media = out.with_name(out.stem + "-media")
        latex = _pandoc(["-f", "docx", "-t", "latex", "-s",
                         "--extract-media", str(media),
                         "-V", "header-includes=" + _preamble(read.brackets),
                         str(tmp)], cwd=out.parent).stdout
    if media.is_dir() and not any(media.rglob("*")):
        media.rmdir()

    refs = References(read)
    drafts = [example_source(ex, "", {}) for ex in read.examples]
    labels = refs.labels(latex + "\n".join(drafts))
    sources = [example_source(ex, labels.examples.get(k, ""),
                              labels.items.get(k, {}))
               for k, ex in enumerate(read.examples)]

    placed: set[int] = set()

    def place(m: re.Match) -> str:
        k = int(m.group(1))
        placed.add(k)
        return sources[k]

    latex = re.sub(r"^[ \t]*LXEXAMPLE(\d+)X[ \t]*$", place, latex, flags=re.M)
    latex = refs.resolve(latex, labels)
    for w in read.ctx.warnings:
        warn(w)
    lost = [k + 1 for k in range(len(sources)) if k not in placed]
    if lost:
        warn(f"example(s) {', '.join(map(str, lost))} did not survive pandoc "
             f"and are missing from the output")
    if U.EXAMPLE_TOKEN_RE.search(latex) or "LXREF" in latex:
        warn("a placeholder is left in the output, where pandoc moved it "
             "away from a paragraph of its own; search the .tex for LXEXAMPLE "
             "or LXREF")
    out.write_text(latex, encoding="utf-8")
    return len(placed)


def _rewrite(src: Path, dst: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = members.get(info.filename)
            zout.writestr(info, data if data is not None else zin.read(info.filename))


def odt_to_docx(odt: Path, outdir: Path) -> Path:
    """LibreOffice's .docx export of *odt*: the styles, the sequence fields
    and the references survive it, which pandoc's ODT reader does not
    give."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        sys.exit("odt2linguexx: LibreOffice (soffice) is not on PATH; it is "
                 "what reads the .odt")
    try:
        subprocess.run([soffice, "--headless", "--convert-to", "docx",
                        "--outdir", str(outdir), str(odt)],
                       check=True, capture_output=True, text=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"odt2linguexx: LibreOffice failed\n{exc.stderr.strip()}")
    except subprocess.TimeoutExpired:
        sys.exit("odt2linguexx: LibreOffice did not finish converting the .odt")
    docx = outdir / (odt.stem + ".docx")
    if not docx.is_file():
        sys.exit("odt2linguexx: LibreOffice wrote no .docx (is another "
                 "instance holding the profile?)")
    return docx


# -- the commands --------------------------------------------------------

def build_parser(prog: str, kind: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=f"Turn a .{kind} whose examples were made by linguexx2odt, "
                    f"the LinguExx Writer macro or an add-in back into LaTeX "
                    f"with linguexx examples.")
    p.add_argument("input", type=Path, help=f"the .{kind} file")
    p.add_argument("-o", "--output", type=Path,
                   help="the .tex to write (default: next to the input)")
    p.add_argument("-q", "--quiet", action="store_true", help="no warnings")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="say how many examples were read")
    return p


def run(argv: list[str] | None, kind: str) -> int:
    prog = f"{kind}2linguexx"
    args = build_parser(prog, kind).parse_args(argv)
    src: Path = args.input
    if not src.is_file():
        sys.exit(f"{prog}: no such file: {src}")
    if src.suffix.lower() != f".{kind}":
        sys.exit(f"{prog}: expected a .{kind} file, got {src.name}"
                 + ("; use odt2linguexx" if src.suffix.lower() == ".odt" else
                    "; use docx2linguexx" if src.suffix.lower() == ".docx" else ""))
    out: Path = (args.output or src.with_suffix(".tex")).resolve()
    if out.resolve() == src.resolve():
        sys.exit(f"{prog}: the output would overwrite the input")
    src = src.resolve()
    warnings: list[str] = []

    if kind == "odt":
        with tempfile.TemporaryDirectory(prefix="odt2linguexx-") as tmpdir:
            n = convert(odt_to_docx(src, Path(tmpdir)), out, warnings.append)
    else:
        n = convert(src, out, warnings.append)

    if not args.quiet:
        for w in warnings:
            print(f"{prog}: warning: {w}", file=sys.stderr)
    if args.verbose:
        print(f"{n} examples -> {out}", file=sys.stderr)
    return 1 if any("did not survive" in w for w in warnings) else 0


def main_docx(argv: list[str] | None = None) -> int:
    return run(argv, "docx")


def main_odt(argv: list[str] | None = None) -> int:
    return run(argv, "odt")


if __name__ == "__main__":
    args = sys.argv[1:]
    kind = "odt" if any(a.lower().endswith(".odt") for a in args) else "docx"
    raise SystemExit(run(args, kind))
