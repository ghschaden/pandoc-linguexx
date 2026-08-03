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

"""Stage 1 — find linguexx examples in a .tex file and lift them out.

Returns the *residue* (the same document with each example replaced by a
placeholder paragraph) plus the parsed :class:`~.ir.Example` list.

The hard rule from the plan: an unknown construct inside an example never
crashes the run.  Everything unrecognised is kept as LaTeX source in the
IR, to be rendered later by the emitter's pandoc-fragment fallback, and a
warning names it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ir import Body, Example, Item, Tier
from .latexutil import (
    cmd_at,
    find_group,
    find_optional,
    live_mask,
    split_cells,
    strip_comments,
    split_top,
)

PLACEHOLDER = "\u27e8\u27e8LINGUEXX-{n:04d}\u27e9\u27e9"
PLACEHOLDER_RE = re.compile("\u27e8\u27e8LINGUEXX-(\\d{4})\u27e9\u27e9")

EX_CMDS = ("ex", "exg")
SUB_RE = re.compile(r"\\([a-y])(g?)\.")
DBLBACK = re.compile(r"\\\\")
GLT = re.compile(r"\\glt(?![a-zA-Z])")

#: Environments in which an example is not a top-level block.  The plan's
#: policy for these is warn-and-leave-alone, never rewrite.
SKIP_ENVS = frozenset(
    {
        "itemize", "enumerate", "description", "list",
        "exe", "xlist",                       # gb4e interface, out of scope v1
        "tabular", "tabularx", "array", "longtable",
        "table", "figure", "wrapfigure",
    }
)

#: Constructs we parse but cannot render faithfully in v1.
DEGRADE = {
    "refrange": "ranged reference",
    "prefrange": "bare ranged reference",
    "Last": "relative reference \\Last",
    "pLast": "relative reference \\pLast",
    "LLast": "relative reference \\LLast",
    "Next": "relative reference \\Next",
    "altn": "\\altn alternatives",
    "altg": "\\altg alternatives",
    "exsource": "\\exsource",
}

JUDG_RUN = re.compile(r"\A\s*((?:\*|\?|\\\#|\\%)+)")


@dataclass
class ParseResult:
    residue: str
    examples: list[Example] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    labels: dict[str, tuple[int, str]] = field(default_factory=dict)
    """label -> (example index, sub-example marker or '')."""


def _alph(n: int) -> str:
    return chr(ord("a") + (n - 1) % 26)


_ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]


def _roman(n: int) -> str:
    return _ROMAN[n - 1] if 1 <= n <= len(_ROMAN) else f"({n})"


def _marker(level: int, ordinal: int) -> str:
    return (_alph(ordinal) if level == 1 else _roman(ordinal)) + "."


# --------------------------------------------------------------------------
# locating an example's extent
# --------------------------------------------------------------------------

def _find_end(src: str, live: list[bool], i: int) -> tuple[int, str, int]:
    """Walk forward from *i* to the end of an example body.

    Mirrors linguexx.sty: collection stops, at brace depth 0, at the first
    of a blank line, a level-exhausting ``\\z.``, an unmatched ``\\end{…}``
    or ``}``, or the next ``\\ex.``.  ``\\a.`` deepens and ``\\z.`` pops the
    sub-example level, so ``\\z.`` only ends the example from the letter
    level or from no level at all.

    Returns (end of body, terminator kind, index to resume scanning at).
    """
    depth = env = subdepth = 0
    n = len(src)
    while i < n:
        if not live[i]:
            i += 1
            continue
        c = src[i]
        if c == "\\":
            hit = cmd_at(src, i)
            if hit is None:
                i += 1
                continue
            name, end = hit
            dotted = src[end : end + 1] == "."
            if name == "begin":
                env += 1
            elif name == "end":
                if depth == 0 and env == 0:
                    return i, "end", i
                env -= 1
            elif name == "endgroup" and depth == 0:
                return i, "endgroup", i
            elif depth == 0 and env == 0:
                if name == "z" and dotted:
                    if subdepth >= 2:
                        subdepth -= 1
                    else:
                        j = end + 1
                        while True:  # swallow a run of \z. we are ending on
                            m = re.match(r"\s*\\z\.", src[j:])
                            if not m:
                                break
                            j += m.end()
                        return i, "z", j
                if name == "a" and dotted:
                    subdepth = min(2, subdepth + 1)
                elif name in EX_CMDS and dotted:
                    return i, "ex", i
            i = end
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i, "brace", i
            depth -= 1
        elif c == "\n" and depth == 0:
            m = re.match(r"\n[ \t]*\r?\n", src[i:])
            if m:
                return i, "par", i
        i += 1
    return n, "eof", n


# --------------------------------------------------------------------------
# body parsing
# --------------------------------------------------------------------------

def _pull_command(chunk: str, name: str) -> tuple[str, str]:
    """Remove the first ``\\name{…}`` from *chunk*; return (arg, rest)."""
    pat = re.compile(r"\\" + name + r"(?![a-zA-Z])")
    m = pat.search(chunk)
    if not m:
        return "", chunk
    grp = find_group(chunk, m.end())
    if grp is None:
        return "", chunk[: m.start()] + chunk[m.end() :]
    arg, end = grp
    return arg, chunk[: m.start()] + chunk[end:]


def _pull_judgment(text: str, warn) -> tuple[str, str]:
    m = JUDG_RUN.match(text)
    if m:
        return m.group(1), text[m.end() :]
    m = re.match(r"\A\s*\\jdg(?![a-zA-Z])", text)
    if m:
        grp = find_group(text, m.end())
        if grp is not None:
            arg, end = grp
            return "\\jdg{" + arg + "}", text[end:]
    return "", text


def _parse_gloss(head: str, shorthand: bool, warn) -> tuple[tuple[Tier, ...], str]:
    """Split the pre-``\\glt`` part into tiers.  Returns (tiers, leftover)."""
    m = re.search(r"\\(glll|gll|gl)(?![a-zA-Z])", head)
    if m:
        kind = m.group(1)
        before = head[: m.start()]
        rest = head[m.end() :]
        limit = {"gll": 2, "glll": 3}.get(kind)
        if kind == "gl":
            stop = re.search(r"\\endgl(?![a-zA-Z])", rest)
            if stop:
                rest = rest[: stop.start()]
            else:
                warn("\\gl without \\endgl; taking every \\\\-separated tier")
    elif shorthand:
        kind, before, rest, limit = "gll", "", head, 2
    else:
        return (), head

    pieces = [c for _, c in split_top(rest, DBLBACK)]
    while pieces and not pieces[-1].strip():
        pieces.pop()
    if limit is not None and len(pieces) > limit:
        extra = pieces[limit:]
        pieces = pieces[:limit]
        if any(p.strip() for p in extra):
            warn(
                f"\\{kind} takes {limit} tiers; {len(extra)} further "
                f"\\\\-separated line(s) kept as trailing text"
            )
            before += " " + " ".join(extra)
    tiers = tuple(Tier(cells=split_cells(p)) for p in pieces)
    return tiers, before


def _parse_body(chunk: str, shorthand: bool, warn) -> Body:
    label, chunk = _pull_command(chunk, "sublabel")
    if not label:
        label, chunk = _pull_command(chunk, "label")
    source, chunk = _pull_command(chunk, "exsource")
    if source:
        warn("\\exsource rendered inline at the end of the example, not flush right")

    parts = split_top(chunk, GLT)
    head = parts[0][1]
    translation = " ".join(c for sep, c in parts[1:]).strip() if len(parts) > 1 else ""

    tiers, leftover = _parse_gloss(head, shorthand, warn)

    if tiers:
        judgment, first = _pull_judgment(leftover + " " + " ".join(tiers[0].cells), warn)
        if judgment:
            tiers = (Tier(cells=split_cells(first)),) + tiers[1:]
        else:
            leftover = leftover.strip()
            if leftover:
                warn(f"text before the gloss kept as body text: {leftover[:40]!r}")
        return Body(
            judgment=judgment,
            text=leftover.strip() if not judgment else "",
            tiers=tiers,
            translation=translation,
            source=source,
            label=label,
        )

    judgment, text = _pull_judgment(head, warn)
    return Body(
        judgment=judgment,
        text=" ".join(text.split()),
        translation=translation,
        source=source,
        label=label,
    )


def _parse_items(body_src: str, shorthand: bool, warn) -> tuple[Item, ...]:
    """Split an example body into sub-examples, honouring linguexx's
    counter semantics: ``\\a.`` opens a deeper level, any other letter is
    'next item here', ``\\z.`` pops one level."""
    pieces = split_top(body_src, SUB_RE)
    items: list[Item] = []
    level = 0
    counters = {1: 0, 2: 0}
    for sep, chunk in pieces:
        if not sep:
            continue
        m = SUB_RE.fullmatch(sep)
        letter, g = m.group(1), bool(m.group(2))
        if letter == "a":
            level = min(2, level + 1)
            counters[level] = 1
            if level == 2:
                warn("second sub-example level rendered as roman numerals, indented")
        else:
            level = max(1, level)
            counters[level] += 1
        # a \z. inside this chunk pops a level for whatever follows
        chunk_body, pops = _strip_pops(chunk)
        items.append(
            Item(
                level=level,
                ordinal=counters[level],
                marker=_marker(level, counters[level]),
                body=_parse_body(chunk_body, shorthand or g, warn),
            )
        )
        for _ in range(pops):
            level = max(1, level - 1)
    return tuple(items)


def _strip_pops(chunk: str) -> tuple[str, int]:
    pops = 0
    out = chunk
    while True:
        m = re.search(r"\\z\.\s*\Z", out)
        if not m:
            break
        out = out[: m.start()]
        pops += 1
    return out, pops


# --------------------------------------------------------------------------
# document scan
# --------------------------------------------------------------------------

def parse(src: str) -> ParseResult:
    live = live_mask(src)
    n = len(src)
    warnings: list[str] = []
    examples: list[Example] = []
    spans: list[tuple[int, int, str]] = []

    env_stack: list[str] = []
    group_stack: list[str] = []
    pending_footnote = False

    i = 0
    while i < n:
        if not live[i]:
            i += 1
            continue
        c = src[i]
        if c == "{":
            group_stack.append("footnote" if pending_footnote else "plain")
            pending_footnote = False
            i += 1
            continue
        if c == "}":
            if group_stack:
                group_stack.pop()
            i += 1
            continue
        if c != "\\":
            i += 1
            continue

        hit = cmd_at(src, i)
        if hit is None:
            i += 1
            continue
        name, end = hit

        if name == "begin":
            grp = find_group(src, end)
            if grp:
                env_stack.append(grp[0])
                end = grp[1]
        elif name == "end":
            grp = find_group(src, end)
            if grp:
                if env_stack:
                    env_stack.pop()
                end = grp[1]
        elif name in ("footnote", "footnotetext", "thanks"):
            pending_footnote = True
        elif name in EX_CMDS and src[end : end + 1] == ".":
            i = _handle_example(
                src, live, i, name, end, env_stack, group_stack,
                examples, spans, warnings,
            )
            continue
        elif name == "ex":
            warnings.append("gb4e \\ex item form found; left untouched (out of scope v1)")
        elif name in ("a", "b", "c", "z") and src[end : end + 1] == ".":
            line = src.count("\n", 0, i) + 1
            warnings.append(
                f"line {line}: stray \\{name}. outside any example, left untouched "
                f"(linguexx itself raises a package error here)"
            )
        elif name in DEGRADE and name != "exsource":
            warnings.append(f"{DEGRADE[name]} left as LaTeX; pandoc renders it literally")
        i = end

    return ParseResult(
        residue=_build_residue(src, spans),
        examples=examples,
        warnings=warnings,
        labels=_collect_labels(examples),
    )


def _handle_example(src, live, start, name, end, env_stack, group_stack,
                    examples, spans, warnings) -> int:
    custom = ""
    after = end + 1  # past the '.'
    opt = find_optional(src, after)
    if opt is not None:
        custom, after = opt

    body_end, kind, resume = _find_end(src, live, after)
    body_src = src[after:body_end]

    bad_env = next((e for e in env_stack if e in SKIP_ENVS), None)
    in_footnote = "footnote" in group_stack
    line = src.count("\n", 0, start) + 1

    if bad_env or in_footnote:
        where = f"inside {bad_env}" if bad_env else "inside a footnote"
        warnings.append(
            f"line {line}: example {where} left untouched "
            f"(nested examples are out of scope v1)"
        )
        return resume if resume > start else body_end

    index = len(examples)
    local: list[str] = []

    def warn(msg: str) -> None:
        local.append(f"line {line}: {msg}")

    if custom:
        warn(f"custom label {custom!r} printed literally; the NumEx counter is not stepped")

    shorthand = name == "exg"
    label, rest = _pull_command(strip_comments(body_src), "label")
    items = _parse_items(rest, shorthand, warn) if SUB_RE.search(rest) else ()
    body = None if items else _parse_body(rest, shorthand, warn)

    for cmd, desc in DEGRADE.items():
        if cmd != "exsource" and re.search(r"\\" + cmd + r"(?![a-zA-Z])", body_src):
            warn(f"{desc} inside an example is rendered literally")

    for nested in set(re.findall(r"\\begin\s*\{([^}]*)\}", body_src)) & SKIP_ENVS:
        warn(f"nested {nested} inside the example is kept as raw LaTeX, not aligned")

    examples.append(
        Example(
            index=index,
            placeholder=PLACEHOLDER.format(n=index),
            label=label,
            custom_label=custom,
            body=body,
            items=items,
            warnings=tuple(local),
            src=src[start:body_end],
            line=line,
        )
    )
    warnings.extend(local)
    spans.append((start, resume, PLACEHOLDER.format(n=index)))
    return resume


def _build_residue(src: str, spans: list[tuple[int, int, str]]) -> str:
    """Replace each example span with its placeholder, always as a
    paragraph of its own — S4 showed that is the whole requirement for
    pandoc to hand it back as a standalone Para."""
    out: list[str] = []
    prev = 0
    for start, stop, ph in spans:
        out.append(src[prev:start])
        out.append("\n\n" + ph + "\n\n")
        prev = stop
    out.append(src[prev:])
    return "".join(out)


def _collect_labels(examples: list[Example]) -> dict[str, tuple[int, str]]:
    labels: dict[str, tuple[int, str]] = {}
    for ex in examples:
        if ex.label:
            labels[ex.label] = (ex.index, "")
        if ex.body is not None and ex.body.label:
            labels[ex.body.label] = (ex.index, "")
        for it in ex.items:
            if it.body.label:
                labels[it.body.label] = (ex.index, it.marker.rstrip("."))
    return labels
