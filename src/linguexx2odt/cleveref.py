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
r"""What ``\cref`` prints for several labels, as cleveref sets it.

Measured (plan-crossrefs.md), with cleveref's defaults, sort and compress:

- the labels go in groups by kind, in the order each kind first comes:
  ``\cref{s1,t1,s2}`` is "sections 1 and 2 and table 1";
- within a group they are sorted and a repeat dropped, and a run of three
  or more consecutive numbers is a range, "sections 1 to 3" -- two stay
  "1 and 2";
- a group's items: "a and b", "a, b and c"; the groups: "A and B",
  "A, B, and C" (with that comma);
- a group of more than one takes the plural name; ``\Cref`` capitalises the
  first group's only.

The words are the document's language's (names.py): "sections 1 et 2",
"sezioni da 1 a 3", "Abschnitt 1, Tabelle 1 und Gleichung (1)" -- whose
groups take no comma before their last, where English and French do.

Format-agnostic: the parts it returns are words and the entries
themselves, which the inject pass makes fields of.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .names import ENGLISH, Names

@dataclass(frozen=True)
class Entry:
    kind: str
    key: tuple | None
    """Its number as a sort key, (1, 2) for "1.2"; None if it has no number
    to sort by (a \\tag, a custom label), which then keeps its place."""
    target: Any
    """Whatever the caller makes a field of."""


def _consecutive(a: tuple | None, b: tuple | None) -> bool:
    if a is None or b is None or len(a) != len(b) or a[:-1] != b[:-1]:
        return False
    x, y = a[-1], b[-1]
    if isinstance(x, str) and isinstance(y, str):
        return len(x) == len(y) == 1 and ord(y) == ord(x) + 1
    return isinstance(x, int) and isinstance(y, int) and y == x + 1


def _join(parts: list[list], pair: str, between: str, last: str) -> list:
    """*parts* joined: "a{pair}b", or "a{between}b{last}c"."""
    if len(parts) == 1:
        return parts[0]
    out: list = []
    for k, part in enumerate(parts):
        if k:
            out.append(between if k < len(parts) - 1
                       else pair if len(parts) == 2 else last)
        out.extend(part)
    return out


def phrase(entries: list[Entry], capital: bool, names: Names = ENGLISH) -> list:
    """The parts of what cleveref prints: strings, and Entry objects where
    a number goes."""
    groups: dict[str, list[Entry]] = {}
    for e in entries:
        groups.setdefault(e.kind, [])
        if e.key is None or all(o.key != e.key for o in groups[e.kind]):
            groups[e.kind].append(e)
    out_groups: list[list] = []
    for g, (kind, members) in enumerate(groups.items()):
        sortable = sorted((e for e in members if e.key is not None), key=lambda e: e.key)
        members = sortable + [e for e in members if e.key is None]
        runs: list[list[Entry]] = []
        for e in members:
            if runs and _consecutive(runs[-1][-1].key, e.key):
                runs[-1].append(e)
            else:
                runs.append([e])
        items: list[list] = []
        for run in runs:
            if len(run) >= 3:
                before, between = names.range
                items.append(([before] if before else []) + [run[0], between, run[-1]])
            else:
                items.extend([[e] for e in run])
        many = len(members) > 1
        word = "" if kind == "example" else names.cref(kind, many, capital and g == 0)
        body = _join(items, names.pair, *names.list)
        out_groups.append(([word + " "] if word else []) + body)
    return _join(out_groups, names.groups_pair, *names.groups_list)
