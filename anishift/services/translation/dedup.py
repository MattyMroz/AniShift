"""Deduplicate identical lines so each unique text is translated once.

A line repeated N times costs one provider request, not N. The mapping is
deterministic (dict insertion order preserves first-seen order), so the same
input always yields the same unique set and redistribution.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DedupResult:
    """Deduplicated lines plus the mapping back to every occurrence.

    Attributes:
        unique: Distinct non-empty lines in first-seen order.
        index_map: For each original line index, the position in ``unique`` it
            maps to, or ``-1`` when the line was empty (skipped).
    """

    unique: tuple[str, ...]
    index_map: tuple[int, ...]


def deduplicate(lines: list[str]) -> DedupResult:
    """Collapse repeated lines to a unique set with a redistribution map.

    Args:
        lines: Cleaned single-line texts in order.

    Returns:
        The unique lines and a per-index map back onto them.
    """
    order: dict[str, int] = {}
    index_map: list[int] = []
    for line in lines:
        if not line.strip():
            index_map.append(-1)
            continue
        if line not in order:
            order[line] = len(order)
        index_map.append(order[line])
    return DedupResult(unique=tuple(order), index_map=tuple(index_map))


def redistribute(translations: list[str], result: DedupResult, sources: list[str]) -> list[str]:
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


def redistribute_flags(flags: list[bool], result: DedupResult) -> list[bool]:
    """Map per-unique ok flags back to every original line (empty -> True).

    Args:
        flags: Success flag per unique line, in ``result.unique`` order.
        result: The dedup result carrying the index map.

    Returns:
        One ok flag per original line; empty (skipped) lines are ``True``.
    """
    return [True if position < 0 else flags[position] for position in result.index_map]


__all__ = ["DedupResult", "deduplicate", "redistribute", "redistribute_flags"]
