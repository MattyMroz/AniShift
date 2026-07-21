"""Google Translate engine package."""

from __future__ import annotations

from anishift.services.translation.engines.google.config import GoogleConfig
from anishift.services.translation.engines.google.service import GoogleService

__all__ = [
    "GoogleConfig",
    "GoogleService",
]
