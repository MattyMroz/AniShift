"""ElevenReader TTS engine package; importing it does not load Playwright."""

from __future__ import annotations

from .api_backend import read_session, sign_in
from .config import ElevenReaderConfig, find_chrome, resolve_voice
from .constants import DEFAULT_VOICE_ALIAS, MAX_PARALLEL_DOCUMENTS, PROVIDER_MODEL_ID, VOICES
from .hub import CLEANUP_WARNING
from .service import ElevenReaderTtsEngine
from .types import ElevenReaderVoice, SessionRecord, SignInOutcome

__all__ = [
    "CLEANUP_WARNING",
    "DEFAULT_VOICE_ALIAS",
    "MAX_PARALLEL_DOCUMENTS",
    "PROVIDER_MODEL_ID",
    "VOICES",
    "ElevenReaderConfig",
    "ElevenReaderTtsEngine",
    "ElevenReaderVoice",
    "SessionRecord",
    "SignInOutcome",
    "find_chrome",
    "read_session",
    "resolve_voice",
    "sign_in",
]
