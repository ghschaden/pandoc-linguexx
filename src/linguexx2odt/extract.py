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
from dataclasses import dataclass, field, replace

from .ir import Body, Example, Item, Tier
from .latexutil import (
    Brackets,
    cmd_at,
    find_group,
    find_optional,
    live_mask,
    scan_brackets,
    split_cells,
    strip_comments,
    split_top,
)

#: Preamble settings that change how linguexx renders something this
#: converter already emits, mapped to what the reader should be told.
#:
#: These are the blind spot the unknown-command fallback cannot cover:
#: nothing unknown appears in the document body, so a run stays silent
#: while the output quietly stops matching the PDF.  \\GlossTransSide is
#: the case that proved it -- linguexx sets the free translation beside
#: the gloss, this converter sets it below, and until now neither the run
#: nor the README said so.
#:
#: Warning, and deliberately nothing more.  A side translation is a
#: placement of the same material, so normalising it to the ordinary
#: layout loses no content; reproducing it would mean deciding what the
#: column does when an example splits into bands -- repeat beside each,
#: sit beside the first, or suppress the split -- a question linguexx
#: never faces because it reflows and an ODT table does not.  Decided
#: 2026-09-25: not worth that, for a placement.
_UNSUPPORTED_SETTINGS = {
    "GlossTransSide":
        "sets the free translation in a column beside the gloss; converted "
        "as an ordinary example, with the translation below it",
    "GlossPhantomAlign":
        "hangs judgment marks into a gutter so the tiers stay aligned; "
        "this converter sets the mark in its own column instead",
    "GlossTierFont":
        "changes the font of a gloss tier; this converter uses the "
        "reference document's styles",
    "DeclareJudgment":
        "declares a judgment command; this converter knows the literal "
        "marks (*, ??, #, %) and \\jdg{...}, so the new name is not "
        "recognised as a judgment",
    "SetLeipzig":
        "declares a gloss abbreviation; \\lpzg renders it as small "
        "capitals here either way, but a redefined expansion is not applied",
}

#: Package options with the same problem.
_UNSUPPORTED_OPTIONS = {
    "phantomalign":
        "hangs judgment marks into a gutter; not reproduced here",
    "langsci":
        "selects the \\ea ... \\z front-end, which this converter does "
        "not parse; those examples are left as LaTeX",
    "legacy":
        "selects linguex's geometry; this converter targets the default",
}

_SETTING_USE = re.compile(r"\\([a-zA-Z@]+)")
_LINGUEXX_OPTS = re.compile(r"\\usepackage\s*\[([^\]]*)\]\s*\{\s*linguexx\s*\}")


def _scan_unsupported(src: str, warn) -> None:
    """Warn about preamble settings whose effect this converter cannot follow."""
    live = live_mask(src)
    body_at = src.find(r"\begin{document}")
    head = src[:body_at] if body_at >= 0 else src

    seen: set[str] = set()
    for m in _SETTING_USE.finditer(src):
        name = m.group(1)
        if name in _UNSUPPORTED_SETTINGS and name not in seen and live[m.start()]:
            seen.add(name)
            warn(f"\\{name} {_UNSUPPORTED_SETTINGS[name]}")

    m = _LINGUEXX_OPTS.search(head)
    if m:
        for opt in (o.strip() for o in m.group(1).split(",")):
            if opt in _UNSUPPORTED_OPTIONS:
                warn(f"[{opt}] {_UNSUPPORTED_OPTIONS[opt]}")


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
    # \Next, \Last and their kin used to be listed here.  They are resolved
    # now -- see RELATIVE and _resolve_relatives -- so an entry for them
    # would be a warning that never fires.
    "altn": "\\altn alternatives",
    "altg": "\\altg alternatives",
    "exsource": "\\exsource",
}

#: Relative reference -> (how many examples away, bare number?).  Negative
#: counts backwards.  These are resolved by POSITION, which the converter can
#: do and linguexx deliberately does not: linguexx only links to an anchor a
#: previous run wrote into the .aux, because at the moment it typesets
#: ``\Next`` the next example does not exist yet.  Here the whole document is
#: in hand before anything is emitted, so "the next example" is simply the
#: next one in the source.
RELATIVE = {
    "Next": (1, False), "pNext": (1, True),
    "NNext": (2, False), "pNNext": (2, True),
    "Last": (-1, False), "pLast": (-1, True),
    "LLast": (-2, False), "pLLast": (-2, True),
}

#: Prefix for the labels those get rewritten to.  They go through the same
#: path as a \ref the author wrote, which is the point: no second reference
#: mechanism to keep in step, and both targets get it for free.
REL_LABEL = "lx-relative-"

JUDG_RUN = re.compile(r"\A\s*((?:\*|\?|\\\#|\\%)+)")


@dataclass
class ParseResult:
    residue: str
    examples: list[Example] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    labels: dict[str, tuple[int, str]] = field(default_factory=dict)
    """label -> (example index, sub-example marker or '')."""
    brackets: Brackets = field(default_factory=Brackets)
    """What the preamble asked an example number to be wrapped in."""


def _alph(n: int) -> str:
    return chr(ord("a") + (n - 1) % 26)


_ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]


def _roman(n: int) -> str:
    return _ROMAN[n - 1] if 1 <= n <= len(_ROMAN) else f"({n})"


def _ordinal_text(level: int, ordinal: int) -> str:
    """``a`` / ``i`` -- the letter itself, with nothing around it."""
    return _alph(ordinal) if level == 1 else _roman(ordinal)


def _marker(level: int, ordinal: int, brackets: Brackets | None = None) -> str:
    br = brackets or Brackets()
    return br.wrap_sub(level, _ordinal_text(level, ordinal))


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


def _pull_annot(chunk: str) -> tuple[str, str]:
    r"""Remove ``\exannot[⟨spoken⟩]{⟨text⟩}``; return (text, rest).

    Unlike _pull_command this has to step over an optional argument.  The
    spoken form is dropped: it is what a PDF screen reader says, and an ODT
    has nowhere to put it.

    Taken from the body as a whole rather than from the object tier
    specifically.  linguexx allows it in exactly two places -- the end of an
    unglossed example, and the end of a gloss's OBJECT line -- and makes any
    other position an error, so a document that compiled has it in one of
    them and there is nothing here to disambiguate.
    """
    m = re.compile(r"\\exannot(?![a-zA-Z])").search(chunk)
    if not m:
        return "", chunk
    i = m.end()
    opt = find_optional(chunk, i)
    if opt is not None:
        i = opt[1]
    grp = find_group(chunk, i)
    if grp is None:
        return "", chunk[: m.start()] + chunk[m.end():]
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


def _parse_gloss(head: str, shorthand: bool, warn) -> tuple[tuple[Tier, ...], str, str]:
    """Split the pre-``\\glt`` part into tiers.

    Returns ``(tiers, before, trailing)``.  ``before`` is what stood in
    front of the ``\\gll``; ``trailing`` is the ``\\\\``-separated lines
    beyond the tier count, which are a different thing in a different place
    and used to be concatenated onto ``before`` as though they were not.
    """
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
        return (), head, ""

    trailing = ""
    pieces = [c for _, c in split_top(rest, DBLBACK)]
    while pieces and not pieces[-1].strip():
        pieces.pop()
    if limit is not None and len(pieces) > limit:
        extra = pieces[limit:]
        pieces = pieces[:limit]
        if any(p.strip() for p in extra):
            trailing = " ".join(" ".join(p.split()) for p in extra).strip()
    tiers = tuple(Tier(cells=split_cells(p)) for p in pieces)
    return tiers, before, trailing


def _parse_body(chunk: str, shorthand: bool, warn) -> Body:
    label, chunk = _pull_command(chunk, "sublabel")
    if not label:
        label, chunk = _pull_command(chunk, "label")
    source, chunk = _pull_command(chunk, "exsource")
    if source:
        warn("\\exsource rendered inline at the end of the example, not flush right")
    annot, chunk = _pull_annot(chunk)

    parts = split_top(chunk, GLT)
    head = parts[0][1]
    translation = " ".join(c for sep, c in parts[1:]).strip() if len(parts) > 1 else ""

    tiers, leftover, trailing = _parse_gloss(head, shorthand, warn)

    if trailing:
        # A line past the last tier IS the free translation.  linguexx
        # typesets it at the gloss indent on its own baseline, which is
        # pixel-for-pixel where \glt puts one -- measured both ways, same x
        # (88.6pt) and same y.  So this is not a degradation to warn about,
        # it is the other spelling of \glt, and the papers that use it write
        # every example that way.
        #
        # When there is a \glt as well, linguexx prints the trailing text
        # first and the \glt line after it.  The IR has one slot, so they
        # join in that order and the line break is lost -- the one case here
        # that really is a degradation.
        if translation:
            warn(
                "trailing line after the gloss and \\glt both present; "
                "joined into one translation line"
            )
            translation = trailing + " " + translation
        else:
            translation = trailing

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
            annot=annot,
            label=label,
        )

    judgment, text = _pull_judgment(head, warn)
    return Body(
        judgment=judgment,
        text=" ".join(text.split()),
        translation=translation,
        source=source,
        annot=annot,
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
    relatives: list[tuple[int, int, str]] = []   # (start, stop, command name)

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
        elif name in RELATIVE:
            relatives.append((i, end, name))
        elif name in DEGRADE and name != "exsource":
            warnings.append(f"{DEGRADE[name]} left as LaTeX; pandoc renders it literally")
        i = end

    _scan_unsupported(src, warnings.append)
    brackets = scan_brackets(src, warnings.append)
    if brackets != Brackets():
        examples = [_redecorate(ex, brackets) for ex in examples]

    labels = _collect_labels(examples)
    rel_spans = _resolve_relatives(src, relatives, spans, labels, warnings)

    return ParseResult(
        residue=_build_residue(src, spans, rel_spans),
        examples=examples,
        warnings=warnings,
        labels=labels,
        brackets=brackets,
    )


def _redecorate(ex: Example, brackets: Brackets) -> Example:
    """The same example with its sub-example markers rebuilt."""
    if not ex.items:
        return ex
    return replace(ex, items=tuple(
        replace(it, marker=_marker(it.level, it.ordinal, brackets))
        for it in ex.items
    ))


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


def _resolve_relatives(
    src: str,
    relatives: list[tuple[int, int, str]],
    spans: list[tuple[int, int, str]],
    labels: dict[str, tuple[int, str]],
    warnings: list[str],
) -> list[tuple[int, int, str]]:
    r"""``\Next`` & co. -> a ``\ref`` to the example they point at.

    These used to be left alone with a warning saying pandoc would render
    them literally.  It does not: ``+raw_tex`` keeps ``\Next`` as a
    ``RawInline "latex"`` and both writers drop one, so a sentence reading
    "structures like \Next, involving..." came out as "structures like ,
    involving..." -- a hole in the prose with a comma dangling in it, 26
    times in the paper this was found in.  A warning the output contradicts
    is worse than no warning.

    Resolved by position: the examples are already parsed and their source
    spans known, so "the next example" is the first one that starts after
    this point.  Rewriting to ``\ref`` rather than to a number keeps it a
    live cross-reference in the output, and reuses the path an author's own
    ``\ref`` takes -- so ODT and docx both get it without either emitter
    learning anything new.
    """
    # (source position, example index), in source order.  The index is read
    # back off the placeholder rather than taken to be the position in the
    # list: they agree today, and a positional assumption is the kind that
    # stops being true quietly.
    located = []
    for start, _stop, ph in spans:
        m = PLACEHOLDER_RE.fullmatch(ph)
        if m:
            located.append((start, int(m.group(1))))
    located.sort()

    out: list[tuple[int, int, str]] = []
    for n, (start, stop, name) in enumerate(relatives):
        offset, bare = RELATIVE[name]
        # How many examples begin before this point; that count is also the
        # position of the NEXT one, so \Next is `nxt` and \Last is nxt - 1.
        nxt = sum(1 for s, _ in located if s < start)
        at = nxt + offset - 1 if offset > 0 else nxt + offset
        line = src.count("\n", 0, start) + 1
        if not 0 <= at < len(located):
            warnings.append(
                f"line {line}: \\{name} points past the document's "
                f"{len(located)} examples; left as written"
            )
            continue
        label = f"{REL_LABEL}{n}"
        labels[label] = (located[at][1], "")
        out.append((start, stop, f"\\{'pref' if bare else 'ref'}{{{label}}}"))
    return out


def _build_residue(
    src: str,
    spans: list[tuple[int, int, str]],
    inline: list[tuple[int, int, str]] | None = None,
) -> str:
    """Replace each example span with its placeholder, always as a
    paragraph of its own — S4 showed that is the whole requirement for
    pandoc to hand it back as a standalone Para.

    `inline` replacements are substituted where they stand, with no blank
    lines: they sit inside a sentence, and a paragraph break there would
    split it in two.
    """
    marked = [(a, b, text, True) for a, b, text in spans]
    marked += [(a, b, text, False) for a, b, text in (inline or [])]
    marked.sort(key=lambda t: t[0])

    out: list[str] = []
    prev = 0
    for start, stop, text, block in marked:
        out.append(src[prev:start])
        out.append("\n\n" + text + "\n\n" if block else text)
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
                labels[it.body.label] = (ex.index, _ordinal_text(it.level, it.ordinal))
    return labels
