"""DeepL engine runtime config."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DeeplConfig:
    """Runtime config for the DeepL engine.

    Attributes:
        api_key: DeepL auth key, injected from Settings at the composition root;
            an empty key disables the engine.
        max_retries: Rate-limit retry attempts.
    """

    api_key: str = ""
    max_retries: int = 3


__all__ = ["DeeplConfig"]
