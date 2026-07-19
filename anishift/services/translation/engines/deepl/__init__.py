"""DeepL engine package."""

from __future__ import annotations

from anishift.services.translation.engines.deepl.config import DeeplConfig
from anishift.services.translation.engines.deepl.service import DeeplService

__all__ = [
    "DeeplConfig",
    "DeeplService",
]
