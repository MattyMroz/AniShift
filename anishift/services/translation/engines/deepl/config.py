"""DeepL engine runtime config."""

from __future__ import annotations

from dataclasses import dataclass

from anishift.services.translation.constants import DEFAULT_BATCH_SIZE, DEFAULT_MAX_RETRIES


@dataclass(slots=True)
class DeeplConfig:
    """Runtime config for the DeepL engine.

    Attributes:
        api_key: DeepL auth key, injected from Settings at the composition root;
            an empty key disables the engine.
        batch_size: Maximum lines sent in one request (bounded further by the
            payload byte limit).
        max_retries: Rate-limit retry attempts.
    """

    api_key: str = ""
    batch_size: int = DEFAULT_BATCH_SIZE
    max_retries: int = DEFAULT_MAX_RETRIES


__all__ = ["DeeplConfig"]
