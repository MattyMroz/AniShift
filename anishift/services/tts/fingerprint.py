"""Canonical synthesis identities and content fingerprints."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsConfigError, TtsInputError
from anishift.services.tts.types import AudioFormat, EngineOptions
from anishift.services.tts.validation import validate_scope_id

__all__ = [
    "SynthesisIdentity",
    "SynthesisProfile",
    "artifact_key",
    "chunk_fingerprints",
    "synthesis_fingerprint",
    "text_hash",
]

_FINGERPRINT_SCHEMA_VERSION: Final[int] = 1
"""Canonical synthesis fingerprint payload schema."""

_HASH_PREFIX: Final[str] = "sha256:"
"""Prefix identifying SHA-256 digests in manifests."""

_ARTIFACT_DOMAIN: Final[str] = "anishift-tts-artifact-v1"
"""Domain separator for deterministic artifact keys."""

_STABLE_IDENTIFIER: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z",
)
"""Non-secret provider identifier grammar."""

_CREDENTIAL_KEY: Final[re.Pattern[str]] = re.compile(
    r"(?:access[_-]?key|api[_-]?key|auth|bearer|credential|headers?|password|secret|subscription[_-]?key|token)",
    re.IGNORECASE,
)
"""Provider option keys that must never enter a fingerprint."""


@dataclass(frozen=True, slots=True)
class SynthesisProfile:
    """Fully resolved provider values that shape native speech audio."""

    engine_id: str
    endpoint_id: str
    provider_model_id: str
    resolved_voice_id: str
    provider_output_id: str
    provider_source_format: AudioFormat
    adapter_version: str
    contract_version: int = 1
    native_rate: str | float | None = None
    native_volume: str | float | None = None
    native_pitch: str | float | None = None
    voice_settings: EngineOptions = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze and validate every resolved fingerprint component."""
        for field_name in (
            "engine_id",
            "endpoint_id",
            "provider_model_id",
            "resolved_voice_id",
            "provider_output_id",
            "adapter_version",
        ):
            value: object = getattr(self, field_name)
            if type(value) is not str or not value.strip():
                _raise_config_error(
                    f"Resolved {field_name} must be a non-empty string",
                    field_name,
                )
        if type(self.provider_source_format) is not AudioFormat:
            _raise_config_error(
                "Provider source format must use AudioFormat",
                "provider_source_format",
            )
        if type(self.contract_version) is not int or self.contract_version <= 0:
            _raise_config_error(
                "Synthesis contract version must be a positive integer",
                "contract_version",
            )
        if _STABLE_IDENTIFIER.fullmatch(self.endpoint_id) is None:
            _raise_config_error(
                "Resolved endpoint must be a stable identifier without URL secrets",
                "endpoint_id",
            )
        _validate_native(self.native_rate, "native_rate")
        _validate_native(self.native_volume, "native_volume")
        _validate_native(self.native_pitch, "native_pitch")
        if not isinstance(self.voice_settings, Mapping):
            _raise_config_error(
                "Voice settings must be a scalar mapping",
                "voice_settings",
            )
        frozen_settings: EngineOptions = MappingProxyType(
            {key: _validated_setting(key, value) for key, value in self.voice_settings.items()},
        )
        object.__setattr__(self, "voice_settings", frozen_settings)


@dataclass(frozen=True, slots=True)
class SynthesisIdentity:
    """Exact request and resolved profile used for TTS resume."""

    scope_id: str
    request_id: str
    text: str
    chunks: tuple[str, ...]
    profile: SynthesisProfile

    def __post_init__(self) -> None:
        """Reject incomplete identities before hashing or filesystem use."""
        validate_scope_id(self.scope_id)
        if type(self.request_id) is not str or not self.request_id:
            _raise_input_error("Synthesis request id cannot be empty", "request_id")
        if type(self.text) is not str or not self.text:
            _raise_input_error("Synthesis text cannot be empty", "text")
        if (
            type(self.chunks) is not tuple
            or not self.chunks
            or any(type(chunk) is not str or not chunk for chunk in self.chunks)
        ):
            _raise_input_error("Synthesis chunks cannot be empty", "chunks")
        if type(self.profile) is not SynthesisProfile:
            _raise_input_error(
                "Synthesis profile must be fully resolved",
                "profile",
            )
        if "".join(self.chunks) != self.text:
            _raise_input_error(
                "Ordered synthesis chunks must reproduce the exact request text",
                "chunks",
            )


def text_hash(text: str) -> str:
    """Hash exact UTF-8 text without Unicode normalization."""
    return _digest(text.encode("utf-8"))


def chunk_fingerprints(identity: SynthesisIdentity) -> tuple[str, ...]:
    """Return ordered fingerprints for independently synthesized chunks."""
    profile_payload: dict[str, object] = _profile_payload(identity.profile)
    return tuple(
        _canonical_digest(
            {
                "fingerprint_schema_version": _FINGERPRINT_SCHEMA_VERSION,
                "kind": "chunk",
                "scope_id": identity.scope_id,
                "request_id": identity.request_id,
                "part_index": part_index,
                "text": chunk,
                "profile": profile_payload,
            },
        )
        for part_index, chunk in enumerate(identity.chunks)
    )


def synthesis_fingerprint(identity: SynthesisIdentity) -> str:
    """Hash every resolved value that shapes one native request clip."""
    chunks: tuple[str, ...] = chunk_fingerprints(identity)
    payload: dict[str, object] = {
        "fingerprint_schema_version": _FINGERPRINT_SCHEMA_VERSION,
        "kind": "request",
        "scope_id": identity.scope_id,
        "request_id": identity.request_id,
        "text": identity.text,
        "chunks": [
            {
                "part_index": part_index,
                "text": chunk,
                "fingerprint": chunks[part_index],
            }
            for part_index, chunk in enumerate(identity.chunks)
        ],
        "profile": _profile_payload(identity.profile),
    }
    return _canonical_digest(payload)


def artifact_key(request_id: str, fingerprint: str) -> str:
    """Return a fixed-length filesystem-safe key for an opaque request."""
    payload: bytes = f"{_ARTIFACT_DOMAIN}\0{request_id}\0{fingerprint}".encode()
    return hashlib.sha256(payload).hexdigest()


def _profile_payload(profile: SynthesisProfile) -> dict[str, object]:
    return {
        "engine_id": profile.engine_id,
        "endpoint_id": profile.endpoint_id,
        "provider_model_id": profile.provider_model_id,
        "resolved_voice_id": profile.resolved_voice_id,
        "provider_output_id": profile.provider_output_id,
        "provider_source_format": profile.provider_source_format.value,
        "adapter_version": profile.adapter_version,
        "contract_version": profile.contract_version,
        "native": {
            "rate": profile.native_rate,
            "volume": profile.native_volume,
            "pitch": profile.native_pitch,
        },
        "voice_settings": dict(profile.voice_settings),
    }


def _canonical_digest(payload: dict[str, object]) -> str:
    try:
        encoded: bytes = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _raise_config_error(
            f"Synthesis fingerprint payload is not canonical: {error}",
            "voice_settings",
        )
    return _digest(encoded)


def _digest(payload: bytes) -> str:
    return f"{_HASH_PREFIX}{hashlib.sha256(payload).hexdigest()}"


def _validated_setting(
    key: str,
    value: str | int | float | bool | None,
) -> str | int | float | bool | None:
    if type(key) is not str or not key:
        _raise_config_error("Voice setting keys must be non-empty strings", "voice_settings")
    if _CREDENTIAL_KEY.search(key) is not None:
        _raise_config_error(
            "Credential-like voice settings cannot enter a fingerprint",
            f"voice_settings.{key}",
        )
    _validate_scalar(value, f"voice_settings.{key}")
    return value


def _validate_scalar(
    value: str | int | float | bool | None,
    field_name: str,
) -> None:
    if type(value) is float and not math.isfinite(value):
        _raise_config_error("Fingerprint numbers must be finite", field_name)
    if value is not None and type(value) not in {str, int, float, bool}:
        _raise_config_error("Fingerprint settings must be scalar values", field_name)


def _validate_native(value: str | float | None, field_name: str) -> None:
    if value is not None and type(value) not in {str, float}:
        _raise_config_error(
            "Native synthesis values must be strings or finite floats",
            field_name,
        )
    _validate_scalar(value, field_name)


def _raise_config_error(message: str, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Resolve stable non-secret provider settings before synthesis.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)


def _raise_input_error(message: str, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message=message,
        suggestion="Prepare exact non-empty text chunks before synthesis.",
        details={"field": field_name},
    )
    raise TtsInputError(context=context)
