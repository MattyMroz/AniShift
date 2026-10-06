"""Identify episode releases by their BTIH key without I/O."""

from __future__ import annotations

import base64
import re
from typing import Final

__all__ = ["info_hash_hex"]

# ── Constants ─────────────────────────────────────────────────────────────────

_HEX_HASH: Final[re.Pattern[str]] = re.compile(r"[0-9a-fA-F]{40}")
"""BTIH v1 hash written as forty hexadecimal digits."""

_BASE32_HASH: Final[re.Pattern[str]] = re.compile(r"[A-Za-z2-7]{32}")
"""BTIH v1 hash written as thirty-two base32 characters."""


def info_hash_hex(value: str) -> str | None:
    """Return the lowercase hexadecimal BTIH of a hex or base32 hash, or ``None`` for any other text."""
    if _HEX_HASH.fullmatch(value) is not None:
        return value.lower()
    if _BASE32_HASH.fullmatch(value) is None:
        return None
    return base64.b32decode(value.upper()).hex()
