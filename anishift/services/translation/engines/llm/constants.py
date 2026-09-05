"""LLM translation prompt resource constants."""

from __future__ import annotations

from typing import Final

# ── Constants ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_NAME: Final[str] = "system.md"
"""Packaged system prompt resource name."""

TRANSLATION_PROMPT_NAME: Final[str] = "translation.md"
"""Packaged main translation prompt resource name."""

RETRY_PROMPT_NAME: Final[str] = "retry.md"
"""Packaged contract-correction prompt resource name."""

STYLES_DIRECTORY: Final[str] = "styles"
"""Packaged directory containing selectable style prompts."""

DEFAULT_STYLE_NAME: Final[str] = "neutral"
"""Default packaged translation style name."""

RETRY_ERROR_PLACEHOLDER: Final[str] = "{{validation_error}}"
"""Unique retry template token replaced with a safe validation diagnosis."""


__all__ = [
    "DEFAULT_STYLE_NAME",
    "RETRY_ERROR_PLACEHOLDER",
    "RETRY_PROMPT_NAME",
    "STYLES_DIRECTORY",
    "SYSTEM_PROMPT_NAME",
    "TRANSLATION_PROMPT_NAME",
]
