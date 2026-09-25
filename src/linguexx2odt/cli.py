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

"""``linguexx2odt`` — LaTeX with linguexx examples -> LibreOffice Writer."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from . import postprocess
from .emit_odt import Emitter
from .extract import parse
from .inject import inject
from .styles import Layout, named_styles

MIN_PANDOC = (3, 0)


def _pandoc(args: list[str], **kw) -> subprocess.CompletedProcess:
    """Run pandoc.  Callers pass absolute paths, so `cwd` is free to be the
    source document's directory — which is what makes relative \\input,
    \\include and \\includegraphics resolve the way latex would."""
    try:
        return subprocess.run(["pandoc", *args], check=True, capture_output=True,
                              text=True, **kw)
    except FileNotFoundError:
        sys.exit("linguexx2odt: pandoc is not on PATH (see README for the minimum version)")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"linguexx2odt: pandoc failed\n{exc.stderr.strip()}")


def _check_pandoc_version() -> str:
    line = _pandoc(["--version"]).stdout.splitlines()[0]
    try:
        version = tuple(int(p) for p in line.split()[1].split(".")[:2])
    except (IndexError, ValueError):
        return line
    if version < MIN_PANDOC:
        sys.exit(f"linguexx2odt: needs pandoc >= {'.'.join(map(str, MIN_PANDOC))}, found {line}")
    return line


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="linguexx2odt",
        description="Convert a LaTeX document with linguexx examples to .odt, "
                    "rendering every example with live number-range fields.",
    )
    p.add_argument("input", type=Path, nargs="?", help="the .tex file")
    p.add_argument("--print-macro", action="store_true",
                   help="print the LibreOffice Writer macro (LinguExx.bas) to "
                        "stdout and exit; see docs/macro.md for how to install it")
    p.add_argument("-o", "--output", type=Path, help="output .odt (default: input with .odt)")
    p.add_argument("--text-width", type=float, default=17.0, metavar="CM",
                   help="width of the text block in cm (default: 17, i.e. A4 with 2cm margins)")
    p.add_argument("--no-split", action="store_true",
                   help="do not break an overlong glossed example into stacked "
                        "bands; squeeze it into one instead")
    p.add_argument("--example-spacing", type=float, default=0.18, metavar="CM",
                   help="space above and below each example in cm (default: 0.18); "
                        "afterwards editable in Writer as the LxExampleSpace "
                        "paragraph style")
    p.add_argument("--space-above", type=float, metavar="CM",
                   help="space above each example, overriding --example-spacing "
                        "(style LxExampleSpaceAbove)")
    p.add_argument("--space-below", type=float, metavar="CM",
                   help="space below each example, overriding --example-spacing "
                        "(style LxExampleSpaceBelow)")
    p.add_argument("--font-pt", type=float, default=12.0, metavar="PT",
                   help="body font size assumed when estimating column widths "
                        "(default: 12)")
    p.add_argument("--page", choices=("a4", "a4-wide", "letter", "keep"), default="a4",
                   help="page geometry to write into the ODT (default: a4; "
                        "'keep' leaves pandoc's US Letter default alone)")
    p.add_argument("--reference-doc", type=Path,
                   help="pandoc reference.odt supplying the base styles")
    p.add_argument("--keep-intermediates", type=Path, metavar="DIR",
                   help="write residue.tex, ast.json and the unpatched odt here")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress warnings")
    p.add_argument("-v", "--verbose", action="store_true", help="report what was converted")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.print_macro:
        from . import writermacro
        print(writermacro.source(), end="")
        return 0
    if args.input is None:
        parser.error("the .tex file is required (or use --print-macro)")

    version = _check_pandoc_version()

    src_path: Path = args.input
    if not src_path.is_file():
        sys.exit(f"linguexx2odt: no such file: {src_path}")
    out_path: Path = args.output or src_path.with_suffix(".odt")

    src_path = src_path.resolve()
    out_path = out_path.resolve()
    workdir = src_path.parent

    source = src_path.read_text(encoding="utf-8")
    parsed = parse(source)

    for name in ("example_spacing", "space_above", "space_below"):
        value = getattr(args, name)
        if value is not None and value < 0:
            sys.exit(f"linguexx2odt: --{name.replace('_', '-')} cannot be negative")

    layout = Layout(
        text_width_cm=args.text_width,
        font_pt=args.font_pt,
        space_cm=args.example_spacing,
        space_above_cm=args.space_above,
        space_below_cm=args.space_below,
    )
    emitter = Emitter(layout=layout, split=not args.no_split,
                      brackets=parsed.brackets)
    emitter.prepare(parsed.examples)
    blocks = {ex.index: emitter.example(ex) for ex in parsed.examples}

    warnings = list(parsed.warnings) + list(emitter.warnings)

    with tempfile.TemporaryDirectory(prefix="linguexx2odt-") as tmpdir:
        tmp = Path(tmpdir)
        residue = tmp / "residue.tex"
        residue.write_text(parsed.residue, encoding="utf-8")

        # +raw_tex so that a command pandoc does not know survives as a
        # RawInline instead of being dropped on the floor.  \pref and the
        # relative references are linguexx's, so plain `latex` emitted
        # NOTHING for them -- the inject pass has always had a branch for
        # the RawInline they never arrived as, and a document's \pref came
        # out as an empty gap between two commas.  Checked before changing:
        # Emph, Strong, Note, Cite, Math and Header parse identically with
        # and without it, so this costs the prose nothing.
        ast = json.loads(
            _pandoc(
                ["-f", "latex+raw_tex", "-t", "json",
                 "--resource-path", str(workdir), str(residue)],
                cwd=workdir,
            ).stdout
        )
        doc, inj = inject(ast, blocks, parsed.labels, warnings.append,
                          brackets=parsed.brackets)

        ast_path = tmp / "ast.json"
        ast_path.write_text(json.dumps(doc), encoding="utf-8")

        raw_odt = tmp / "raw.odt"
        pandoc_args = ["-f", "json", str(ast_path), "-o", str(raw_odt)]
        if args.reference_doc:
            pandoc_args += ["--reference-doc", str(args.reference_doc)]
        _pandoc(pandoc_args, cwd=workdir)

        content = postprocess.read(raw_odt, "content.xml")
        content = postprocess.inject_sequence_decls(content)
        content = postprocess.inject_automatic_styles(content, emitter.styles_fragment())

        styles = postprocess.read(raw_odt, "styles.xml")
        styles = postprocess.inject_named_styles(styles, named_styles(layout))
        styles = postprocess.set_page_geometry(styles, args.page)

        postprocess.rewrite(raw_odt, out_path,
                            {"content.xml": content, "styles.xml": styles})

        if args.keep_intermediates:
            keep = args.keep_intermediates
            keep.mkdir(parents=True, exist_ok=True)
            for f in (residue, ast_path, raw_odt):
                shutil.copy2(f, keep / f.name)

    if warnings and not args.quiet:
        for w in warnings:
            print(f"linguexx2odt: warning: {w}", file=sys.stderr)

    if args.verbose:
        glossed = sum(1 for e in parsed.examples if e.glossed)
        print(
            f"{version}\n"
            f"{len(parsed.examples)} examples "
            f"({glossed} with gloss tiers), "
            f"{inj.placeholders_replaced} placed, {inj.refs_rewritten} cross-references, "
            f"{len(warnings)} warnings\n"
            f"-> {out_path}",
            file=sys.stderr,
        )

    if inj.placeholders_replaced != len(parsed.examples):
        lost = len(parsed.examples) - inj.placeholders_replaced
        print(
            f"linguexx2odt: warning: {lost} example(s) did not survive the pandoc "
            f"round-trip and are missing from the output",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
