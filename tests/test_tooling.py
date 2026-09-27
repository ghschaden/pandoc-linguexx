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
r"""What the suite needs on PATH, and whether anything agrees about it.

This file exists because of a measurement.  Without pandoc and soffice the
suite reported

    169 passed, 28 skipped

and exited 0.  Twenty-eight tests — every end-to-end one, the half that
proves the .odt is right rather than the IR — vanished, and the run looked
green.  A contributor without LibreOffice would have seen that and shipped.

So the tools are named once, here, and checked two ways: present on PATH,
and installed by the CI workflow.  The sibling project solved exactly this
with its REQUIRED_TOOLS table after the same thing happened to it, and the
comment above that table is the argument for this one: a requirement that
lives only in prose is a requirement nothing enforces.

Running without them is still allowed — it is a reasonable thing to want
— but it has to be said out loud:

    LINGUEXX2ODT_ALLOW_MISSING=1 pytest

which turns the failure into a warning that still names what did not run.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

HERE = Path(__file__).parent
REPO = HERE.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

ALLOW_MISSING = os.environ.get("LINGUEXX2ODT_ALLOW_MISSING") == "1"

#: tool -> (what it is for, how CI provides it)
#:
#: "apt:<pkg>" must appear in the workflow's apt-get line; "step:<name>"
#: must appear as a step name.  Checked, not described.
REQUIRED_TOOLS: dict[str, tuple[str, str]] = {
    "pandoc": (
        "converting the residue — the document minus its examples; "
        "without it nothing converts at all",
        "step:Install pandoc",
    ),
    "soffice": (
        "rendering the .odt to PDF so the geometry can be measured; "
        "without it the end-to-end half of the suite does not run",
        "apt:libreoffice-writer",
    ),
    "pdftotext": (
        "word boxes from that PDF — every geometric assertion reads them",
        "apt:poppler-utils",
    ),
}


def missing() -> list[str]:
    return [t for t in REQUIRED_TOOLS if shutil.which(t) is None]


def test_every_required_tool_is_on_path() -> None:
    """Fail — do not skip — when a tool the suite needs is absent.

    Skipping is what made this invisible: 28 tests stepped aside quietly
    and the exit code stayed 0.  A red line naming the tool costs the
    reader one second and tells the truth.
    """
    absent = missing()
    if not absent:
        return
    detail = "\n".join(f"  {t}: {REQUIRED_TOOLS[t][0]}" for t in absent)
    message = (
        f"{len(absent)} required tool(s) not on PATH:\n{detail}\n"
        f"Tests that need them will SKIP, and the run will otherwise look "
        f"green.  Install them, or set LINGUEXX2ODT_ALLOW_MISSING=1 to say "
        f"deliberately that this run does not cover them."
    )
    if ALLOW_MISSING:
        pytest.skip(message)
    pytest.fail(message)


@pytest.mark.skipif(not WORKFLOW.exists(),
                    reason="no CI workflow in this tree")
def test_ci_installs_every_required_tool() -> None:
    r"""CI must provide what the table says it provides.

    The other half of the drift: a tool can be on the author's PATH for
    years and never reach the workflow, so every local run is green and CI
    fails somewhere unrelated — or worse, skips and does not.

    What is searched for an apt package is the apt-get command's argument
    list, not the file, because a workflow that merely mentions a package
    in a comment installs nothing.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    joined = re.sub(r"\\\n\s*", " ", text)     # undo line continuations
    apt: set[str] = set()
    for m in re.finditer(r"apt-get\s+install[^\n]*", joined):
        apt.update(m.group(0).split())

    problems = []
    for tool, (why, provided) in REQUIRED_TOOLS.items():
        kind, _, value = provided.partition(":")
        if kind == "apt":
            if value not in apt:
                problems.append(
                    f"{tool} needs the apt package {value!r}, which the "
                    f"workflow's apt-get line does not install")
        elif kind == "step":
            # Anchored to the end of the line: a substring test passes for
            # a step called "Install pandoc-x", which installs nothing of
            # the sort.  Found by mutating the name and watching the check
            # stay green.
            if not re.search(rf"^\s*-?\s*name:\s*{re.escape(value)}\s*$",
                             text, re.M):
                problems.append(
                    f"{tool} is provided by a step named {value!r}, which "
                    f"the workflow does not have")
        else:  # pragma: no cover - a typo in the table above
            problems.append(f"{tool}: unknown provider {provided!r}")
    assert not problems, "\n".join(problems)


@pytest.mark.skipif(not WORKFLOW.exists(),
                    reason="no CI workflow in this tree")
def test_ci_runs_the_macro_suite() -> None:
    """The Writer macro is checked by CI too, not only by hand.

    It is the half of this project that pytest cannot reach: `.bas` driven
    inside a real LibreOffice, minutes rather than seconds, and for a long
    time run only where somebody remembered to. A phase CI can silently
    omit is a phase CI eventually omits — which is the argument the sibling
    repository's tooling check makes about its own --documents flag.

    Its two round-trip checks need pandoc as well, because they take a
    CONVERTED document apart and skip themselves when the converter will
    not run.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "run_macro_test.py" in text, (
        "the CI workflow no longer runs tools/run_macro_test.py, so a "
        "change to LinguExx.bas would reach main unverified"
    )
    installs = len(re.findall(r"^\s*-?\s*name:\s*Install pandoc\s*$",
                              text, re.M))
    assert installs >= 2, (
        "the macro job needs pandoc too: without it the two checks that "
        "read a converted document back skip, and skipping is how this "
        "went unnoticed before"
    )


@pytest.mark.skipif(not WORKFLOW.exists(),
                    reason="no CI workflow in this tree")
def test_ci_runs_the_suite_without_the_escape_hatch() -> None:
    """CI must not set the variable that turns the tool check into a skip.

    It exists for a person who knows what they are not running.  In CI it
    would restore precisely the silence this file was written to end.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "LINGUEXX2ODT_ALLOW_MISSING" not in text, (
        "the CI workflow sets LINGUEXX2ODT_ALLOW_MISSING, which lets a "
        "runner missing a tool report green"
    )


#: The linguexx repository's own test documents, which
#: test_extract.test_corpus_never_crashes feeds through the parser.
CORPUS = REPO.parent / "linguexx" / "tests"
README = REPO / "README.md"


def test_the_linguexx_corpus_is_present() -> None:
    """Fail — do not vanish — when ../linguexx is not checked out.

    The corpus test is parametrized over the files it finds, so without
    them it is not skipped a hundred times, it is collected zero times:
    CI passed 177 tests where a local run passed 282, and nothing said so.
    """
    if any(CORPUS.glob("*.tex")):
        return
    message = (
        f"no linguexx test documents at {CORPUS}: the corpus test, one "
        f"parse per document, did not run.  Clone linguexx beside this "
        f"repository, or set LINGUEXX2ODT_ALLOW_MISSING=1 to say "
        f"deliberately that this run does not cover it."
    )
    if ALLOW_MISSING:
        pytest.skip(message)
    pytest.fail(message)


def _job(text: str, name: str) -> str:
    """One job's section of the workflow, so a step is found in the job
    that needs it and not merely somewhere in the file."""
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\n|\Z)",
                  text, re.M | re.S)
    return m.group(1) if m else ""


@pytest.mark.skipif(not WORKFLOW.exists(),
                    reason="no CI workflow in this tree")
def test_ci_checks_the_corpus_out_at_the_targeted_version() -> None:
    """The corpus CI parses is the linguexx this converter says it
    targets.  Bumping the README's version without the clone would test
    the new claim against the old documents, and pass."""
    target = re.search(r"\*\*Targets linguexx ([\d.]+)\.\*\*",
                       README.read_text(encoding="utf-8"))
    assert target, "the README no longer states the linguexx version targeted"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(rf'^\s*LINGUEXX_VER:\s*"{re.escape(target.group(1))}"\s*$',
                     text, re.M), (
        f"the workflow does not pin LINGUEXX_VER to {target.group(1)}, "
        f"the version the README says this converter targets")
    job = _job(text, "test")
    assert re.search(r"git clone\b.*--branch\s+\"?\$LINGUEXX_VER\"?"
                     r".*ghschaden/linguexx\S*\s+\.\./linguexx\s*$",
                     re.sub(r"\\\n\s*", " ", job), re.M), (
        "the test job does not clone linguexx at $LINGUEXX_VER into "
        "../linguexx, where the corpus test looks")
