"""Lookup of a program installed in a standard location or on ``PATH``."""

from __future__ import annotations

import os
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["find_installed"]


def find_installed(locations: Iterable[tuple[str, str]], stem: str) -> Path | None:
    """Return the first file under an environment-variable root in *locations*, then *stem* on ``PATH``."""
    for variable, relative in locations:
        root: str = os.environ.get(variable, "")
        if not root:
            continue
        candidate: Path = Path(root) / relative
        if candidate.is_file():
            return candidate
    found: str | None = which(stem)
    return Path(found) if found else None
