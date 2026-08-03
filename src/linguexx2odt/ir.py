"""Intermediate representation for linguexx examples.

Deliberately dumb and JSON-serialisable: the parser's whole output is a
list of :class:`Example`, and the golden tests snapshot exactly that.
Cell/text fields hold *LaTeX source*; turning that into ODT inline markup
is the emitter's job, not the parser's.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Tier:
    """One line of a gloss (object language, gloss, further tiers)."""

    cells: tuple[str, ...] = ()


@dataclass(frozen=True)
class Body:
    """The content of an example or of one sub-example."""

    judgment: str = ""
    """LaTeX source of the judgment mark ('*', '??', '\\jdg{\\dag}'), or ''."""

    text: str = ""
    """Body text, for an unglossed example.  Empty when ``tiers`` is set."""

    tiers: tuple[Tier, ...] = ()
    """Gloss tiers, top to bottom.  Empty for an unglossed example."""

    translation: str = ""
    """``\\glt`` content, LaTeX source, without the marker."""

    source: str = ""
    """``\\exsource`` content, LaTeX source."""

    label: str = ""
    """``\\label``/``\\sublabel`` target defined here, or ''."""

    @property
    def glossed(self) -> bool:
        return bool(self.tiers)

    @property
    def width(self) -> int:
        """Number of gloss columns (the widest tier)."""
        return max((len(t.cells) for t in self.tiers), default=0)


@dataclass(frozen=True)
class Item:
    """A sub-example.  ``level`` 1 prints a./b./c., level 2 prints i./ii."""

    level: int
    ordinal: int
    marker: str
    body: Body


@dataclass(frozen=True)
class Example:
    index: int
    """0-based order of appearance in the document."""

    placeholder: str

    label: str = ""
    custom_label: str = ""
    """``\\ex.[(4')]`` — printed literally, counter not stepped."""

    body: Body | None = None
    """Set when the example has no sub-examples."""

    items: tuple[Item, ...] = ()
    """Set when it does."""

    warnings: tuple[str, ...] = ()
    src: str = ""
    line: int = 0

    @property
    def bodies(self) -> tuple[Body, ...]:
        return (self.body,) if self.body is not None else tuple(i.body for i in self.items)

    @property
    def glossed(self) -> bool:
        """True if *any* body carries gloss tiers — then the whole example
        is rendered as one table, so the number cell stays aligned."""
        return any(b.glossed for b in self.bodies)


def to_json(examples: list[Example]) -> str:
    return json.dumps([asdict(e) for e in examples], indent=2, ensure_ascii=False)
