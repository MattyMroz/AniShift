"""Strict JSON Lines messages for the SAPI worker."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never, cast

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsProviderUnavailableError
from anishift.services.tts.types import ProcessArchitecture

from .constants import MAX_IPC_MESSAGE_BYTES, PROTOCOL_VERSION
from .types import SapiVoiceRecord

__all__ = [
    "SapiWorkerRequest",
    "SapiWorkerResponse",
    "decode_voice_list",
]


@dataclass(frozen=True, slots=True)
class SapiWorkerRequest:
    """One correlated synthesis command sent to a persistent worker."""

    request_id: str
    voice_name: str
    text: str
    output_path: Path

    def encode(self) -> bytes:
        """Serialize one bounded UTF-8 JSON line."""
        payload: dict[str, object] = {
            "operation": "synthesize",
            "output_path": self.output_path.as_posix(),
            "protocol_version": PROTOCOL_VERSION,
            "request_id": self.request_id,
            "text": self.text,
            "voice_name": self.voice_name,
        }
        encoded: bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_IPC_MESSAGE_BYTES:
            _raise_protocol_error("SAPI worker request exceeds the IPC message limit")
        return encoded


@dataclass(frozen=True, slots=True)
class SapiWorkerResponse:
    """One correlated worker response."""

    request_id: str
    ok: bool
    output_path: Path | None
    error_code: str
    message: str

    @classmethod
    def decode(cls, raw_line: bytes) -> SapiWorkerResponse:
        """Parse and validate one bounded response line."""
        payload: dict[str, Any] = _decode_payload(raw_line)
        if payload.get("protocol_version") != PROTOCOL_VERSION:
            _raise_protocol_error("SAPI worker returned an unsupported protocol version")
        request_id: str = _required_string(payload, "request_id")
        ok: bool = _required_bool(payload, "ok")
        if ok:
            output_path: str = _required_string(payload, "output_path")
            return cls(
                request_id=request_id,
                ok=True,
                output_path=Path(output_path),
                error_code="",
                message="",
            )
        return cls(
            request_id=request_id,
            ok=False,
            output_path=None,
            error_code=_required_string(payload, "error_code"),
            message=_required_string(payload, "message"),
        )


def decode_voice_list(
    raw_line: bytes,
    *,
    architecture: ProcessArchitecture,
) -> tuple[SapiVoiceRecord, ...]:
    """Decode a passive voice-enumeration response."""
    if type(architecture) is not ProcessArchitecture:
        _raise_protocol_error("SAPI voice-list architecture is invalid")
    payload: dict[str, Any] = _decode_payload(raw_line)
    if payload.get("protocol_version") != PROTOCOL_VERSION or payload.get("operation") != "list_voices":
        _raise_protocol_error("SAPI voice-list response has an invalid protocol envelope")
    if payload.get("ok") is not True:
        _raise_protocol_error("SAPI voice enumeration failed")
    raw_voices: object = payload.get("voices")
    if not isinstance(raw_voices, list):
        _raise_protocol_error("SAPI voice-list response does not contain a voice array")
    voices: list[SapiVoiceRecord] = []
    for raw_voice in raw_voices:
        if not isinstance(raw_voice, dict):
            _raise_protocol_error("SAPI voice-list entry is invalid")
        voice_payload: dict[str, Any] = cast("dict[str, Any]", raw_voice)
        voices.append(
            SapiVoiceRecord(
                id=_required_string(voice_payload, "id"),
                name=_required_string(voice_payload, "name"),
                architecture=architecture,
            ),
        )
    return tuple(voices)


def _decode_payload(raw_line: bytes) -> dict[str, Any]:
    if not raw_line or len(raw_line) > MAX_IPC_MESSAGE_BYTES:
        _raise_protocol_error("SAPI worker returned an empty or oversized response")
    try:
        decoded: object = json.loads(raw_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        message: str = "SAPI worker returned malformed JSON"
        raise TtsProviderUnavailableError(message) from error
    if not isinstance(decoded, dict):
        _raise_protocol_error("SAPI worker response must be a JSON object")
    return cast("dict[str, Any]", decoded)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value: object = payload.get(key)
    if type(value) is not str or not value:
        _raise_protocol_error(f"SAPI worker response field {key!r} must be a non-empty string")
    return value


def _required_bool(payload: dict[str, Any], key: str) -> bool:
    value: object = payload.get(key)
    if type(value) is not bool:
        _raise_protocol_error(f"SAPI worker response field {key!r} must be boolean")
    return value


def _raise_protocol_error(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_ENGINE_UNAVAILABLE,
        message=message,
        suggestion="Restart the SAPI worker and retry the affected request.",
    )
    raise TtsProviderUnavailableError(context=context)
