"""Deduplicate identical lines so each unique text is translated once.

A line repeated N times costs one provider request, not N. The mapping is
deterministic (dict insertion order preserves first-seen order), so the same
input always yields the same unique set and redistribution.
"""

from __future__ import annotations

from dataclasses import dataclass

from anishift.services.translation.protocols import TranslationInputPolicy


@dataclass(frozen=True, slots=True)
class PreparedLines:
    """Prepared lines plus the mapping back to every occurrence.

    Attributes:
        texts: Non-empty texts sent to the engine.
        index_map: For each original line index, the position in ``texts`` it
            maps to, or ``-1`` when the line was empty (skipped).
    """

    texts: tuple[str, ...]
    index_map: tuple[int, ...]

    @property
    def unique(self) -> tuple[str, ...]:
        """Return the legacy name for prepared engine texts."""
        return self.texts


DedupResult = PreparedLines
"""Backward-compatible name for deduplicated prepared lines."""


def prepare_lines(lines: list[str], policy: TranslationInputPolicy) -> PreparedLines:
    """Prepare lines according to an engine stream policy.

    Args:
        lines: Cleaned single-line texts in order.
        policy: Whether identical non-empty texts collapse or stay separate.

    Returns:
        Engine texts and a per-position redistribution map.
    """
    if policy == "preserve":
        texts: list[str] = []
        index_map: list[int] = []
        for line in lines:
            if not line.strip():
                index_map.append(-1)
                continue
            index_map.append(len(texts))
            texts.append(line)
        return PreparedLines(texts=tuple(texts), index_map=tuple(index_map))

    order: dict[str, int] = {}
    index_map = []
    for line in lines:
        if not line.strip():
            index_map.append(-1)
            continue
        if line not in order:
            order[line] = len(order)
        index_map.append(order[line])
    return PreparedLines(texts=tuple(order), index_map=tuple(index_map))


def deduplicate(lines: list[str]) -> DedupResult:
    """Collapse repeated lines to a unique set with a redistribution map.

    Args:
        lines: Cleaned single-line texts in order.

    Returns:
        The unique lines and a per-index map back onto them.
    """
    return prepare_lines(lines, "deduplicate")


def redistribute(translations: list[str], result: PreparedLines, sources: list[str]) -> list[str]:
    """Fill every original position from the translated unique lines.

    Args:
        translations: Translated text per unique line (same length/order as
            ``result.unique``).
        result: The dedup result carrying the index map.
        sources: Original lines, used to pass empty lines through unchanged.

    Returns:
        One translated string per original line.
    """
    out: list[str] = []
    for position, source in zip(result.index_map, sources, strict=True):
        out.append(source if position < 0 else translations[position])
    return out


def redistribute_flags(flags: list[bool], result: PreparedLines) -> list[bool]:
    """Map per-unique ok flags back to every original line (empty -> True).

    Args:
        flags: Success flag per unique line, in ``result.unique`` order.
        result: The dedup result carrying the index map.

    Returns:
        One ok flag per original line; empty (skipped) lines are ``True``.
    """
    return [True if position < 0 else flags[position] for position in result.index_map]


__all__ = [
    "DedupResult",
    "PreparedLines",
    "deduplicate",
    "prepare_lines",
    "redistribute",
    "redistribute_flags",
]
