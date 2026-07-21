"""Translation domain constants. No provider secrets, no engine names.

Engine names live in the registry (single source of truth); API keys live in
:class:`anishift.config.settings.Settings`.
"""

from __future__ import annotations

from typing import Final

TARGET_LANG: Final[str] = "pl"
"""Translation target; always Polish (AniShift is a Polish anime lector)."""

DEFAULT_SOURCE_LANG: Final[str] = "auto"
"""Default source language; ``auto`` lets the provider detect it."""

DEFAULT_BATCH_SIZE: Final[int] = 50
"""Lines joined into one provider request (subtitle batching by line count)."""

DEFAULT_MAX_RETRIES: Final[int] = 3
"""Retry attempts on transient errors before giving up."""


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_SOURCE_LANG",
    "TARGET_LANG",
]
