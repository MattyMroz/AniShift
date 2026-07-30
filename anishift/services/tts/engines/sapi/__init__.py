"""Windows SAPI speech engine."""

from __future__ import annotations

from .config import SapiConfig
from .service import SapiTtsEngine

__all__ = ["SapiConfig", "SapiTtsEngine"]
