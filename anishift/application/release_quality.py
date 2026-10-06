"""Normalize release language declarations without I/O."""

from __future__ import annotations

import re
from typing import Final

__all__ = ["language_code"]

# ── Constants ─────────────────────────────────────────────────────────────────

_SUBTAG_SEPARATOR: Final[re.Pattern[str]] = re.compile(r"[-_]")
"""Separator between the primary language and the region or script subtags of a language tag."""


def language_code(code: str) -> str:
    """Return the lowercase primary language of a language tag, so ``pl-PL`` and ``PL`` both become ``pl``."""
    return _SUBTAG_SEPARATOR.split(code.strip(), maxsplit=1)[0].casefold()
