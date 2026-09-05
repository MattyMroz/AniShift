"""Translation service public surface."""

from __future__ import annotations

from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines import TranslationEngineId, available_engine_ids
from anishift.services.translation.errors import (
    TranslationAuthError,
    TranslationConfigError,
    TranslationEngineError,
    TranslationError,
    TranslationQuotaError,
    TranslationRateLimitError,
)
from anishift.services.translation.service import TranslationService
from anishift.services.translation.types import FileTranslation, TranslatedLine

__all__ = [
    "FileTranslation",
    "TranslatedLine",
    "TranslationAuthError",
    "TranslationConfig",
    "TranslationConfigError",
    "TranslationEngineError",
    "TranslationEngineId",
    "TranslationError",
    "TranslationQuotaError",
    "TranslationRateLimitError",
    "TranslationService",
    "available_engine_ids",
]
