"""Constants for the ElevenBytes proxy engine."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

__all__ = [
    "DALLIN_ALIAS",
    "DALLIN_LABEL",
    "DALLIN_VOICE_ID",
    "ENDPOINTS",
    "MAX_TEXT_CHARS",
    "MIN_AUDIO_BYTES",
    "PUBLIC_PROXY_TOKEN",
    "REQUEST_HEADERS",
]

PUBLIC_PROXY_TOKEN: Final[str] = "wqpwgoGhADAwIdb1JRNTAEBgg="  # noqa: S105
"""Public proxy request token shipped by the ElevenBytes web client."""

ENDPOINTS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "run6": "https://teamsp.org/xi/run6.php",
        "run7": "https://teamsp.org/xi/run7.php",
    },
)
"""Exact ElevenBytes endpoints keyed by stable endpoint variant."""

REQUEST_HEADERS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
        "Origin": "https://teamsp.org",
        "Referer": "https://teamsp.org/xi/tts.html",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    },
)
"""Headers used by the public ElevenBytes browser client."""

DALLIN_ALIAS: Final[str] = "dallin"
"""Reserved alias of the built-in ElevenBytes voice."""

DALLIN_LABEL: Final[str] = "Dallin — Storyteller"
"""Display label of the built-in ElevenBytes voice."""

DALLIN_VOICE_ID: Final[str] = "alFofuDn3cOwyoz1i44T"
"""Provider identifier of the built-in ElevenBytes voice."""

MAX_TEXT_CHARS: Final[int] = 5000
"""Maximum number of characters accepted by one proxy request."""

MIN_AUDIO_BYTES: Final[int] = 1024
"""Minimum response size accepted before shared decode validation."""
