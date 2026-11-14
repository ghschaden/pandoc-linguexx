# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
"""Gloss declarations and morpheme boundaries from linguexx 1.5."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .latexutil import cmd_at, find_group, find_optional, live_mask

COMMANDS = frozenset({"GlossMorphAlign", "GlossMorphAlignOff", "GlossTierLang",
                      "GlossTransLang", "exrefcheck"})


@dataclass
class Settings:
    morph: bool = False
    languages: dict[int, str] = field(default_factory=dict)
    translation: str = ""

    def copy(self):
        return replace(self, languages=dict(self.languages))

    def command(self, src: str, name: str, end: int) -> int:
        """Apply a declaration; return its end (or the command's end)."""
        if name == "GlossMorphAlign":
            self.morph = True
        elif name == "GlossMorphAlignOff":
            self.morph = False
        elif name == "exrefcheck":
            opt = find_optional(src, end)
            return opt[1] if opt else end
        elif name in {"GlossTierLang", "GlossTransLang"}:
            arg = find_group(src, end)
            if arg:
                value, end = arg
                if name == "GlossTransLang":
                    self.translation = value.strip()
                else:
                    arg = find_group(src, end)
                    if arg:
                        language, end = arg
                        if value.strip().isdigit():
                            self.languages[int(value)] = language.strip()
        return end

    def strip(self, src: str) -> tuple[str, Settings]:
        """Read local declarations without exposing their arguments as words."""
        state = self.copy()
        live = live_mask(src)
        out, start, i = [], 0, 0
        while i < len(src):
            hit = cmd_at(src, i) if live[i] and src[i] == "\\" else None
            if hit:
                name, end = hit
                if name in COMMANDS:
                    out.append(src[start:i])
                    i = state.command(src, name, end)
                    start = i
                    continue
                i = end
            else:
                i += 1
        return "".join(out) + src[start:], state


def morphemes(word: str) -> tuple[str, ...]:
    """Split at unbraced -/=, keeping separators on the following segment.

    A leading/trailing separator, a TeX dash, and braced material stay whole.
    Movement and alternative stacks are deliberately measured as words.
    """
    if any("\\" + name in word for name in
           ("altg", "mvto", "mvfrom", "lxMoveTo", "lxMoveFrom")):
        return (word,)
    out, start, depth, i = [], 0, 0, 0
    while i < len(word):
        c = word[i]
        if c == "\\":
            hit = cmd_at(word, i)
            i = hit[1] if hit else i + 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif (depth == 0 and c in "-=" and i > 0 and i + 1 < len(word)
              and word[i - 1] not in "-=" and word[i + 1] not in "-="):
            out.append(word[start:i])
            start = i
        i += 1
    return tuple(out + [word[start:]])
