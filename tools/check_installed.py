#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke-test a wheel installation: /fresh/venv/bin/python -I tools/check_installed.py.

Run outside the source tree, with no editable install or system site packages.
Requires pandoc and LibreOffice on PATH; missing tools fail the check.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import fontTools
import linguexx2odt
from linguexx2odt.extract import parse
from linguexx2odt import writermacro

SOURCE = r"""\documentclass{article}
\usepackage[lazy]{linguexx}
\begin{document}
\ex.\label{ex:first} Packaging sentinel.

\ex. \gll Alpha Beta \\
ONE TWO \\
\glt Translation sentinel.

See \ref{ex:first}.
\end{document}
"""


def main():
    prefix = Path(sys.prefix).resolve()
    assert sys.prefix != sys.base_prefix, "use a fresh virtual environment"
    for module in (linguexx2odt, fontTools):
        assert Path(module.__file__).resolve().is_relative_to(prefix), module.__file__
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["PYTHONNOUSERSITE"] = "1"
    scripts = Path(sys.executable).parent

    with tempfile.TemporaryDirectory(prefix="linguexx-installed-") as directory:
        work = Path(directory)

        def run(command, *args):
            executable = scripts / (command + (".exe" if os.name == "nt" else ""))
            result = subprocess.run([str(executable), *map(str, args)], cwd=work,
                                    env=env, capture_output=True, text=True, timeout=180)
            assert result.returncode == 0, result.stdout + result.stderr
            return result.stdout

        for command in ("linguexx2odt", "docx2linguexx", "odt2linguexx"):
            assert "usage:" in run(command, "--help")
        macro = run("linguexx2odt", "--print-macro")
        assert macro == writermacro.source()
        assert "Sub GlossSelection" in macro
        source = work / "sample.tex"
        source.write_text(SOURCE, encoding="utf-8")
        for target in ("odt", "docx"):
            document = work / f"sample.{target}"
            run("linguexx2odt", source, "--to", target, "-o", document)
            with zipfile.ZipFile(document) as archive:
                assert archive.testzip() is None
                member = "content.xml" if target == "odt" else "word/document.xml"
                xml = archive.read(member).decode("utf-8")
                assert "NumEx" in xml and "Alpha" in xml and "Beta" in xml
                assert ("text:sequence-ref" if target == "odt" else " REF ") in xml
            back = work / f"returned-{target}.tex"
            run(f"{target}2linguexx", document, "-o", back)
            text = back.read_text(encoding="utf-8")
            assert len(parse(text).examples) == 2, text
            for word in ("Packaging", "Alpha", "Beta", "ONE", "TWO", "Translation"):
                assert word in text, (target, word)
            print(f"OK installed {target} round trip", flush=True)
    print(f"OK wheel commands, dependency and macro from {prefix}")


if __name__ == "__main__":
    main()
