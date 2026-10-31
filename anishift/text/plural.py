"""Polish noun forms agreeing with a count."""

from __future__ import annotations

__all__ = ["plural"]


def plural(count: int, one: str, few: str, many: str) -> str:
    """Return *one* for 1, *few* for 2–4 outside 12–14 in the last digits, otherwise *many*."""
    if count == 1:
        return one
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return few
    return many
