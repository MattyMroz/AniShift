"""Fuzzy degrees from 0 to 1 and their combination for subtitle layout harms."""

from __future__ import annotations

from math import prod

__all__ = ["fall", "nor", "rise"]


def rise(x: float, a: float, b: float) -> float:
    """Return 0 for ``x <= a``, 1 for ``x >= b`` and a straight line between; a step at ``a`` when ``a == b``."""
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    return (x - a) / (b - a)


def fall(x: float, a: float, b: float) -> float:
    """Return the complement of ``rise``: 1 for ``x <= a``, 0 for ``x >= b``."""
    return 1.0 - rise(x, a, b)


def nor(*degrees: float) -> float:
    """Combine degrees so each one adds to the total: ``1 - prod(1 - d)``, 0 for none."""
    return 1.0 - prod(1.0 - degree for degree in degrees)
