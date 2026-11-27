"""ElevenReader engine; what is specific to this program lives in ``host.py``; importing it loads no Playwright."""

from __future__ import annotations

from .api_backend import await_sign_in, read_session, sign_in, sign_out
from .config import ElevenReaderConfig, find_chrome, resolve_voice
from .constants import DEFAULT_VOICE_ALIAS, MAX_PARALLEL_DOCUMENTS, PROVIDER_MODEL_ID, VOICES
from .host import CLEANUP_WARNING, DocumentPart, DocumentResult, DocumentSynthesisRequest, PartTiming
from .service import ElevenReaderTtsEngine
from .types import ElevenReaderVoice, Redo, SessionRecord, SignInOutcome, SignOutOutcome

__all__ = [
    "CLEANUP_WARNING",
    "DEFAULT_VOICE_ALIAS",
    "MAX_PARALLEL_DOCUMENTS",
    "PROVIDER_MODEL_ID",
    "VOICES",
    "DocumentPart",
    "DocumentResult",
    "DocumentSynthesisRequest",
    "ElevenReaderConfig",
    "ElevenReaderTtsEngine",
    "ElevenReaderVoice",
    "PartTiming",
    "Redo",
    "SessionRecord",
    "SignInOutcome",
    "SignOutOutcome",
    "await_sign_in",
    "find_chrome",
    "read_session",
    "resolve_voice",
    "sign_in",
    "sign_out",
]
