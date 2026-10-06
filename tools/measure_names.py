#!/usr/bin/env python3
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

r"""Check names.LANGUAGES against what LaTeX prints, language by language.

A reference prints a name -- "section 1", "Abschnitt 1" -- and three
packages supply them, each with its own idea of the language: the caption's
"Table 1:" is babel's (or polyglossia's), \autoref's "Table 1" is
hyperref's, following babel, and \cref's "table 1" is cleveref's, which
follows a language option given to it or to the class and NOT babel's
alone.  None of it is reasoned out here: a probe document is compiled per
language and the names are read off the PDF.

    python3 tools/measure_names.py            # check
    python3 tools/measure_names.py --print    # reprint the literal

Needs pdflatex, lualatex (polyglossia) and pdftotext.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from linguexx2odt.names import LANGUAGES  # noqa: E402

#: The languages measured, by babel's name and polyglossia's.
MEASURED = {
    "english": ("english", "english"),
    "french": ("french", "french"),
    "german": ("ngerman", "german"),
    "spanish": ("spanish", "spanish"),
    "italian": ("italian", "italian"),
    "portuguese": ("brazilian", "portuguese"),
    "dutch": ("dutch", "dutch"),
}

BODY = r"""
\begin{document}
\section{A}\label{s1}\subsection{AA}\label{ss1}\subsubsection{AAA}\label{sss1}
\section{B}\label{s2}\section{C}\label{s3}\section{D}\label{s4}
\begin{table}[h]\caption{T}\label{t1}\begin{tabular}{l}x\\\end{tabular}\end{table}
\begin{table}[h]\caption{U}\label{t2}\begin{tabular}{l}x\\\end{tabular}\end{table}
\begin{figure}[h]\rule{1pt}{1pt}\caption{F}\label{f1}\end{figure}
\begin{figure}[h]\rule{1pt}{1pt}\caption{G}\label{f2}\end{figure}
\begin{equation}\label{e1} a \end{equation}
\begin{equation}\label{e2} b \end{equation}
Text.\footnote{N.\label{n1}} Text.\footnote{M.\label{n2}}
\begin{enumerate}\item a\label{i1}\item b\label{i2}\end{enumerate}
"""

KINDS = {"section": ("s1", "s2"), "table": ("t1", "t2"), "figure": ("f1", "f2"),
         "equation": ("e1", "e2"), "footnote": ("n1", "n2"), "item": ("i1", "i2")}
AUTO = {"section": "s1", "subsection": "ss1", "subsubsection": "sss1", "table": "t1",
        "figure": "f1", "equation": "e1", "footnote": "n1", "item": "i1",
        "appendix": "ap1"}


def _lines() -> dict[str, str]:
    lines = {}
    for kind, (a, b) in KINDS.items():
        lines[f"c.{kind}"] = rf"\cref{{{a}}}"
        lines[f"cs.{kind}"] = rf"\cref{{{a},{b}}}"
        lines[f"C.{kind}"] = rf"\Cref{{{a}}}"
        lines[f"Cs.{kind}"] = rf"\Cref{{{a},{b}}}"
    for name, label in AUTO.items():
        lines[f"auto.{name}"] = rf"\autoref{{{label}}}"
    lines.update({
        "range": r"\cref{s1,s2,s3}", "list": r"\cref{s1,s3,s4}",
        "groups2": r"\cref{s1,t1}", "groups3": r"\cref{s1,t1,f1}",
        "page": r"\cpageref{s1}", "Page": r"\Cpageref{s1}",
        "pages": r"\cpageref{s1,p9}", "Pages": r"\Cpageref{s1,p9}",
    })
    return lines


LINES = _lines()


def _tag(n: int) -> str:
    return f"QQ{chr(65 + n // 26)}{chr(65 + n % 26)}QQ"


def compile_probe(preamble: str, engine: str, workdir: Path, name: str) -> str:
    body = BODY + "".join(f"\n\n{_tag(n)} {v}.\n" for n, v in enumerate(LINES.values()))
    # a last marker, so that every line ends at the next one: the notes
    # are printed after it, at the foot of the page
    body += f"\n\n{_tag(len(LINES))} end.\n"
    # a section on a later page, for the plural of "page"
    body += "\n\\clearpage\\section{Z}\\label{p9}\n"
    # an appendix section, whose \autoref name is its own ("Appendix A")
    body += "\\appendix\\section{Y}\\label{ap1}\n\\end{document}\n"
    tex = workdir / f"{name}.tex"
    tex.write_text(preamble + body, encoding="utf-8")
    for _ in range(2):
        subprocess.run([engine, "-interaction=batchmode", tex.name], cwd=workdir,
                       capture_output=True, timeout=300)
    return subprocess.run(["pdftotext", str(workdir / f"{name}.pdf"), "-"],
                          capture_output=True, text=True).stdout


def _word(text: str) -> str:
    """The name before the first number: "sections 1 et 2" -> "sections"."""
    return re.split(r"\s*[\d(]", text, maxsplit=1)[0].strip()


def derive(txt: str) -> dict:
    flat = " ".join(txt.split())
    said = {}
    for n, key in enumerate(LINES):
        m = re.search(rf"{_tag(n)} (.*?)\.(?= QQ)", flat)
        said[key] = m.group(1).strip() if m else ""
    out: dict = {"cref": {}, "autoref": {}}
    for kind in KINDS:
        out["cref"][kind] = [_word(said[f"{k}.{kind}"]) for k in ("c", "cs", "C", "Cs")]
    for name in AUTO:
        out["autoref"][name] = _word(said[f"auto.{name}"])
    # "Appendix A": its number is a letter, which _word does not stop at
    out["autoref"]["appendix"] = re.sub(r"\s+A$", "", said["auto.appendix"])
    out["page"] = [_word(said[k]) for k in ("page", "pages", "Page", "Pages")]
    # "sections 1 et 2": what joins two
    m = re.search(r"1(.*?)2", said["cs.section"])
    out["pair"] = m.group(1) if m else " and "
    # "sections 1, 3 et 5": what joins the last of several, and the others
    m = re.search(r"1(.*?)3(.*?)4", said["list"])
    out["list"] = [m.group(1), m.group(2)] if m else [", ", " and "]
    # "sezioni da 1 a 3": the range, with whatever goes before its first
    m = re.search(r"^\S+(?:\s+\S+)*?\s+(\D*?)1(\D+?)3$", said["range"])
    out["range"] = [m.group(1), m.group(2)] if m else ["", " to "]
    # "section 1 et tableau 1"; "section 1, tableau 1, et figure 1"
    m = re.search(r"1(\D+?)\S+\s1$", said["groups2"])
    out["groups_pair"] = m.group(1) if m else " and "
    m = re.search(r"1(\D+?)\S+\s1(\D+?)\S+\s1$", said["groups3"])
    out["groups_list"] = [m.group(1), m.group(2)] if m else [", ", ", and "]
    # "Table 1 – T", "Tabelle 1: T": the caption's name and what follows it
    for kind, text in (("table", "T"), ("figure", "F")):
        m = re.search(rf"(\S+) 1(\s*[:–—.-]\s*){text}\b", flat)
        out[f"caption_{kind}"] = [m.group(1), m.group(2)] if m else ["", ""]
    return out


def configs(lang: str) -> dict[str, tuple[str, str]]:
    babel, poly = MEASURED[lang]
    head = r"\documentclass{article}\usepackage[T1]{fontenc}"
    return {
        # cleveref told the language: localised
        "cleveref": (head + rf"\usepackage[{babel}]{{babel}}\usepackage{{hyperref}}"
                     rf"\usepackage[{babel}]{{cleveref}}", "pdflatex"),
        # babel alone: captions and \autoref localised, cleveref English
        "babel": (head + rf"\usepackage[{babel}]{{babel}}\usepackage{{hyperref}}"
                  r"\usepackage{cleveref}", "pdflatex"),
        "polyglossia": (r"\documentclass{article}\usepackage{fontspec}"
                        rf"\usepackage{{polyglossia}}\setmainlanguage{{{poly}}}"
                        r"\usepackage{hyperref}\usepackage{cleveref}", "lualatex"),
    }


def measure() -> dict:
    jobs = [(lang, cfg, pre, eng) for lang in MEASURED
            for cfg, (pre, eng) in configs(lang).items()]
    with tempfile.TemporaryDirectory() as tmp:
        def one(job):
            lang, cfg, pre, eng = job
            return lang, cfg, derive(compile_probe(pre, eng, Path(tmp), f"{lang}-{cfg}"))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(one, jobs))
    table: dict = {}
    for lang, cfg, d in results:
        entry = table.setdefault(lang, {})
        if cfg == "cleveref":
            for key in ("cref", "page", "pair", "list", "range", "groups_pair", "groups_list"):
                entry[key] = d[key]
        elif cfg == "babel":
            entry["autoref"] = d["autoref"]
            entry["caption"] = {"table": d["caption_table"], "figure": d["caption_figure"]}
        else:
            entry["polyglossia_caption"] = {"table": d["caption_table"],
                                            "figure": d["caption_figure"]}
            entry["polyglossia_autoref"] = d["autoref"]
    return table


def main() -> int:
    table = measure()
    if "--print" in sys.argv:
        print("LANGUAGES = " + json.dumps(table, ensure_ascii=False, indent=4))
        return 0
    if table != LANGUAGES:
        for lang in table:
            if table[lang] != LANGUAGES.get(lang):
                print(f"{lang}: measured\n  {json.dumps(table[lang], ensure_ascii=False)}\n"
                      f"carried\n  {json.dumps(LANGUAGES.get(lang), ensure_ascii=False)}")
        return 1
    print("names.LANGUAGES matches what LaTeX prints")
    return 0


if __name__ == "__main__":
    sys.exit(main())
