"""Versioned repository for validated provider-native TTS clips."""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.artifacts import (
    TtsArtifactLayout,
    atomic_json_snapshot,
    sha256_file,
)
from anishift.services.tts.errors import (
    TtsCancelledError,
    TtsClipValidationError,
    TtsResumeConflictError,
    TtsResumeError,
    TtsResumeSchemaError,
)
from anishift.services.tts.fingerprint import (
    SynthesisIdentity,
    artifact_key,
    chunk_fingerprints,
    synthesis_fingerprint,
    text_hash,
)
from anishift.services.tts.types import AudioFormat, ClipExpectation, ClipValidation
from anishift.services.tts.validation import validate_scope_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from anishift.services.tts.protocols import ClipValidator

__all__ = [
    "CachedTtsClip",
    "ClipExpectation",
    "ClipValidation",
    "TtsResumeRepository",
    "ValidatedClipReceipt",
]

_MANIFEST_SCHEMA_VERSION: Final[int] = 1
"""Current all-or-nothing TTS resume manifest schema."""

_COMPLETE_STATUS: Final[str] = "complete"
"""Only durable status represented in a resume manifest."""

_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")
"""Exact digest syntax accepted from a persisted manifest."""

_REPOSITORY_LOCKS: Final[dict[Path, threading.RLock]] = {}
"""Process-local single-writer locks keyed by resolved repository root."""

_REPOSITORY_LOCKS_GUARD: Final[threading.Lock] = threading.Lock()
"""Protects creation of process-local repository locks."""


@dataclass(frozen=True, slots=True)
class CachedTtsClip:
    """Validated provider-native clip reusable by the TTS scheduler."""

    request_id: str
    synthesis_fingerprint: str
    chunk_fingerprints: tuple[str, ...]
    path: Path
    clip_hash: str
    format: AudioFormat
    size_bytes: int
    sample_rate: int
    channels: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ValidatedClipReceipt:
    """Bind trusted decode metadata to one unchanged repository temp clip."""

    path: Path
    validation: ClipValidation
    size_bytes: int
    modified_ns: int
    device: int
    inode: int
    repository_token: object


@dataclass(frozen=True, slots=True)
class _ManifestEntry:
    request_id: str
    text_hash: str
    synthesis_fingerprint: str
    chunk_fingerprints: tuple[str, ...]
    clip_path: str
    clip_hash: str
    clip_format: str
    size_bytes: int
    sample_rate: int
    channels: int
    duration_ms: int
    status: str


class TtsResumeRepository:
    """Single-writer owner of one scope's TTS manifest and raw clips."""

    def __init__(
        self,
        root: Path,
        scope_id: str,
        validator: ClipValidator,
    ) -> None:
        """Open one isolated repository and load its trusted snapshot."""
        self._scope_id: str = validate_scope_id(scope_id)
        self._layout: TtsArtifactLayout = TtsArtifactLayout(root.absolute())
        self._validator: ClipValidator = validator
        self._receipt_token: object = object()
        self._lock: threading.RLock = _repository_lock(self._layout.root)
        self._warnings: list[ErrorContext] = []
        self._entries: dict[str, _ManifestEntry] = {}
        self._dirty_entries: dict[str, _ManifestEntry] = {}
        self._layout.initialize()
        with self._lock:
            self._load()

    @property
    def warnings(self) -> tuple[ErrorContext, ...]:
        """Return nonfatal corrupt-cache diagnostics."""
        with self._lock:
            return tuple(self._warnings)

    def temporary_clip_path(self, *, clip_format: AudioFormat) -> Path:
        """Reserve an owned same-filesystem path for an engine attempt."""
        return self._layout.temporary_clip_path(clip_format=clip_format)

    def flush(self) -> None:
        """Persist all staged entries in one durable manifest snapshot."""
        with self._lock:
            if not self._dirty_entries:
                return
            self._load()
            self._write_snapshot(self._entries)
            self._dirty_entries.clear()

    def lookup(
        self,
        identity: SynthesisIdentity,
        expectation: ClipExpectation,
    ) -> CachedTtsClip | None:
        """Return a fully revalidated hit or adopt one exact orphan clip."""
        self._require_scope(identity)
        self._require_format(identity, expectation)
        fingerprint: str = synthesis_fingerprint(identity)
        key: str = artifact_key(identity.request_id, fingerprint)
        with self._lock:
            self._load()
            entry: _ManifestEntry | None = self._entries.get(key)
            if entry is not None:
                return self._validated_entry(identity, expectation, entry)
            return self._adopt_orphan(identity, expectation, key)

    def validate_temporary_clip(
        self,
        path: Path,
        expectation: ClipExpectation,
    ) -> ValidatedClipReceipt | None:
        """Validate one owned temp clip and return metadata reusable at commit."""
        owned_path: Path = self._layout.validate_temporary_clip(
            path,
            clip_format=expectation.format,
        )
        validation: ClipValidation | None = self._validate_path(owned_path, expectation)
        if validation is None:
            return None
        try:
            stat = owned_path.stat()
        except OSError as error:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_ERROR,
                message="TTS clip validation could not access its artifact",
                suggestion="Check workspace permissions and file locks.",
                details={"operation": "validate_clip_receipt"},
            )
            raise TtsResumeError(context=context) from error
        return ValidatedClipReceipt(
            path=owned_path,
            validation=validation,
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            device=stat.st_dev,
            inode=stat.st_ino,
            repository_token=self._receipt_token,
        )

    def commit_clip(
        self,
        identity: SynthesisIdentity,
        temporary_path: Path,
        expectation: ClipExpectation,
        *,
        can_commit: Callable[[], bool],
        validation_receipt: ValidatedClipReceipt | None = None,
    ) -> CachedTtsClip:
        """Validate and atomically publish one provider result for later flush."""
        self._require_scope(identity)
        self._require_format(identity, expectation)
        owned_path: Path = self._layout.validate_temporary_clip(
            temporary_path,
            clip_format=expectation.format,
        )
        validation: ClipValidation | None = self._receipt_validation(
            owned_path,
            expectation,
            validation_receipt,
        )
        if validation is None:
            self._layout.discard_temporary_clip(owned_path)
            _raise_clip_invalid()
        if not can_commit():
            self._layout.discard_temporary_clip(owned_path)
            _raise_cancelled()

        fingerprint: str = synthesis_fingerprint(identity)
        key: str = artifact_key(identity.request_id, fingerprint)
        final_path: Path = self._layout.clip_path(
            request_id=identity.request_id,
            fingerprint=fingerprint,
            clip_format=expectation.format,
        )
        with self._lock:
            if not can_commit():
                self._layout.discard_temporary_clip(temporary_path)
                _raise_cancelled()
            self._load()
            existing: _ManifestEntry | None = self._entries.get(key)
            if existing is not None:
                hit: CachedTtsClip | None = self._validated_entry(
                    identity,
                    expectation,
                    existing,
                )
                if hit is not None:
                    self._layout.discard_temporary_clip(owned_path)
                    return hit
            elif final_path.is_file():
                orphan: CachedTtsClip | None = self._adopt_orphan(
                    identity,
                    expectation,
                    key,
                )
                if orphan is not None:
                    self._layout.discard_temporary_clip(owned_path)
                    return orphan
            self._layout.publish_clip(
                owned_path,
                final_path,
                clip_format=expectation.format,
            )
            clip: CachedTtsClip = self._cached_clip(
                identity,
                fingerprint,
                final_path,
                validation,
            )
            entry: _ManifestEntry = self._entry_from_clip(identity, clip)
            self._entries[key] = entry
            self._dirty_entries[key] = entry
            return clip

    def _receipt_validation(
        self,
        path: Path,
        expectation: ClipExpectation,
        receipt: ValidatedClipReceipt | None,
    ) -> ClipValidation | None:
        if receipt is None:
            return self._validate_path(path, expectation)
        try:
            stat = path.stat()
        except OSError:
            return self._validate_path(path, expectation)
        if (
            receipt.repository_token is self._receipt_token
            and receipt.path == path
            and receipt.validation.format is expectation.format
            and receipt.size_bytes == stat.st_size
            and receipt.modified_ns == stat.st_mtime_ns
            and receipt.device == stat.st_dev
            and receipt.inode == stat.st_ino
        ):
            return receipt.validation
        return self._validate_path(path, expectation)

    def _load(self) -> None:
        self._entries = dict(self._dirty_entries)
        manifest_path: Path = self._layout.manifest_path
        if not manifest_path.is_file():
            return
        try:
            raw: object = json.loads(manifest_path.read_text(encoding="utf-8"))
            schema_version: int = _manifest_schema_version(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            self._quarantine_corrupt(error)
            return
        if schema_version > _MANIFEST_SCHEMA_VERSION:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_SCHEMA,
                message="TTS resume manifest uses a newer schema",
                suggestion="Upgrade AniShift before continuing this resume state.",
                details={"schema_version": schema_version},
            )
            raise TtsResumeSchemaError(context=context)
        try:
            parsed_schema, scope_id, entries = _parse_manifest(raw)
        except (TypeError, ValueError) as error:
            self._quarantine_corrupt(error)
            return
        if schema_version != _MANIFEST_SCHEMA_VERSION or scope_id != self._scope_id:
            self._quarantine_corrupt(ValueError("manifest identity mismatch"))
            return
        if parsed_schema != schema_version:
            self._quarantine_corrupt(ValueError("manifest schema mismatch"))
            return
        self._entries = {**entries, **self._dirty_entries}

    def _validated_entry(
        self,
        identity: SynthesisIdentity,
        expectation: ClipExpectation,
        entry: _ManifestEntry,
    ) -> CachedTtsClip | None:
        fingerprint: str = synthesis_fingerprint(identity)
        expected_path: Path = self._layout.clip_path(
            request_id=identity.request_id,
            fingerprint=fingerprint,
            clip_format=expectation.format,
        )
        if (
            entry.request_id != identity.request_id
            or entry.text_hash != text_hash(identity.text)
            or entry.synthesis_fingerprint != fingerprint
            or entry.chunk_fingerprints != chunk_fingerprints(identity)
            or entry.clip_path != self._layout.relative_clip_path(expected_path)
            or entry.clip_format != expectation.format.value
            or entry.status != _COMPLETE_STATUS
        ):
            return None
        try:
            if not expected_path.is_file() or expected_path.is_symlink():
                return None
            stat_size: int = expected_path.stat().st_size
            if stat_size != entry.size_bytes or sha256_file(expected_path) != entry.clip_hash:
                return None
        except OSError as error:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_ERROR,
                message="TTS clip validation could not access its artifact",
                suggestion="Check workspace permissions and file locks.",
                details={"operation": "validate_clip"},
            )
            raise TtsResumeError(context=context) from error
        if stat_size <= 0:
            return None
        return CachedTtsClip(
            request_id=entry.request_id,
            synthesis_fingerprint=fingerprint,
            chunk_fingerprints=entry.chunk_fingerprints,
            path=expected_path,
            clip_hash=entry.clip_hash,
            format=expectation.format,
            size_bytes=stat_size,
            sample_rate=entry.sample_rate,
            channels=entry.channels,
            duration_ms=entry.duration_ms,
        )

    def _adopt_orphan(
        self,
        identity: SynthesisIdentity,
        expectation: ClipExpectation,
        key: str,
    ) -> CachedTtsClip | None:
        fingerprint: str = synthesis_fingerprint(identity)
        path: Path = self._layout.clip_path(
            request_id=identity.request_id,
            fingerprint=fingerprint,
            clip_format=expectation.format,
        )
        validation: ClipValidation | None = self._validate_path(path, expectation)
        if validation is None:
            return None
        clip: CachedTtsClip = self._cached_clip(
            identity,
            fingerprint,
            path,
            validation,
        )
        entry: _ManifestEntry = self._entry_from_clip(identity, clip)
        self._entries[key] = entry
        self._dirty_entries[key] = entry
        return clip

    def _cached_clip(
        self,
        identity: SynthesisIdentity,
        fingerprint: str,
        path: Path,
        validation: ClipValidation,
    ) -> CachedTtsClip:
        return CachedTtsClip(
            request_id=identity.request_id,
            synthesis_fingerprint=fingerprint,
            chunk_fingerprints=chunk_fingerprints(identity),
            path=path,
            clip_hash=sha256_file(path),
            format=validation.format,
            size_bytes=path.stat().st_size,
            sample_rate=validation.sample_rate,
            channels=validation.channels,
            duration_ms=validation.duration_ms,
        )

    def _entry_from_clip(
        self,
        identity: SynthesisIdentity,
        clip: CachedTtsClip,
    ) -> _ManifestEntry:
        return _ManifestEntry(
            request_id=identity.request_id,
            text_hash=text_hash(identity.text),
            synthesis_fingerprint=clip.synthesis_fingerprint,
            chunk_fingerprints=clip.chunk_fingerprints,
            clip_path=self._layout.relative_clip_path(clip.path),
            clip_hash=clip.clip_hash,
            clip_format=clip.format.value,
            size_bytes=clip.size_bytes,
            sample_rate=clip.sample_rate,
            channels=clip.channels,
            duration_ms=clip.duration_ms,
            status=_COMPLETE_STATUS,
        )

    def _validate_path(
        self,
        path: Path,
        expectation: ClipExpectation,
    ) -> ClipValidation | None:
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
                return None
            validation: ClipValidation | None = self._validator.validate_clip(
                path,
                expectation,
            )
        except OSError as error:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_ERROR,
                message="TTS clip validation could not access its artifact",
                suggestion="Check workspace permissions and file locks.",
                details={"operation": "validate_clip"},
            )
            raise TtsResumeError(context=context) from error
        if validation is None or validation.format is not expectation.format:
            return None
        return validation

    def _write_snapshot(self, entries: dict[str, _ManifestEntry]) -> None:
        payload: dict[str, object] = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "scope_id": self._scope_id,
            "entries": {
                key: {
                    **asdict(entry),
                    "chunk_fingerprints": list(entry.chunk_fingerprints),
                }
                for key, entry in sorted(entries.items())
            },
        }
        try:
            atomic_json_snapshot(self._layout.manifest_path, payload)
        except OSError as error:
            error_details: dict[str, str | int] = {
                "operation": "manifest_snapshot",
                "error_type": type(error).__name__,
                "reason": str(error),
            }
            if error.errno is not None:
                error_details["errno"] = error.errno
            winerror: int | None = getattr(error, "winerror", None)
            if winerror is not None:
                error_details["winerror"] = winerror
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_ERROR,
                message="Failed to persist the TTS resume manifest",
                suggestion="Check workspace permissions and free disk space.",
                details=error_details,
            )
            raise TtsResumeError(context=context) from error

    def _quarantine_corrupt(self, error: BaseException) -> None:
        manifest_path: Path = self._layout.manifest_path
        diagnostic: Path = self._layout.root / (f"manifest.corrupt.{time.time_ns()}.{secrets.token_hex(4)}.json")
        try:
            manifest_path.replace(diagnostic)
        except OSError as move_error:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_ERROR,
                message="Corrupt TTS manifest could not be preserved",
                suggestion="Check workspace permissions before retrying.",
                details={"operation": "manifest_quarantine"},
            )
            raise TtsResumeError(context=context) from move_error
        self._warnings.append(
            ErrorContext(
                code=ErrorCode.TTS_RESUME_ERROR,
                message="Corrupt TTS resume manifest was quarantined",
                suggestion="AniShift will validate exact orphan clips before reuse.",
                details={
                    "diagnostic": diagnostic.name,
                    "reason": type(error).__name__,
                },
            ),
        )

    def _require_scope(self, identity: SynthesisIdentity) -> None:
        if identity.scope_id != self._scope_id:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_CONFLICT,
                message="Synthesis identity belongs to a different resume scope",
                suggestion="Use one repository instance per opaque scope id.",
            )
            raise TtsResumeConflictError(context=context)

    @staticmethod
    def _require_format(
        identity: SynthesisIdentity,
        expectation: ClipExpectation,
    ) -> None:
        if expectation.format is not identity.profile.provider_source_format:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_RESUME_CONFLICT,
                message="Clip expectation conflicts with the resolved provider format",
                suggestion="Use the exact provider-native format from the synthesis profile.",
            )
            raise TtsResumeConflictError(context=context)


def _parse_manifest(
    raw: object,
) -> tuple[int, str, dict[str, _ManifestEntry]]:
    if type(raw) is not dict:
        raise TypeError
    manifest: dict[str, Any] = raw
    if set(manifest) != {"schema_version", "scope_id", "entries"}:
        raise ValueError
    schema_version: int = _exact_int(manifest.get("schema_version"))
    scope_id: str = _exact_str(manifest.get("scope_id"))
    raw_entries: object = manifest.get("entries")
    if type(raw_entries) is not dict:
        raise TypeError
    entries: dict[str, _ManifestEntry] = {}
    for key, value in raw_entries.items():
        if type(key) is not str or type(value) is not dict:
            raise TypeError
        entry_data: dict[str, Any] = value
        if set(entry_data) != {
            "request_id",
            "text_hash",
            "synthesis_fingerprint",
            "chunk_fingerprints",
            "clip_path",
            "clip_hash",
            "clip_format",
            "size_bytes",
            "sample_rate",
            "channels",
            "duration_ms",
            "status",
        }:
            raise ValueError
        entry = _ManifestEntry(
            request_id=_exact_str(entry_data.get("request_id")),
            text_hash=_exact_str(entry_data.get("text_hash")),
            synthesis_fingerprint=_exact_str(
                entry_data.get("synthesis_fingerprint"),
            ),
            chunk_fingerprints=_string_tuple(
                entry_data.get("chunk_fingerprints"),
            ),
            clip_path=_exact_str(entry_data.get("clip_path")),
            clip_hash=_exact_str(entry_data.get("clip_hash")),
            clip_format=_exact_str(entry_data.get("clip_format")),
            size_bytes=_exact_int(entry_data.get("size_bytes")),
            sample_rate=_exact_int(entry_data.get("sample_rate")),
            channels=_exact_int(entry_data.get("channels")),
            duration_ms=_exact_int(entry_data.get("duration_ms")),
            status=_exact_str(entry_data.get("status")),
        )
        expected_path: str = f"clips/clip-{key}.{entry.clip_format}"
        if (
            key != artifact_key(entry.request_id, entry.synthesis_fingerprint)
            or not entry.request_id
            or _SHA256_PATTERN.fullmatch(entry.text_hash) is None
            or _SHA256_PATTERN.fullmatch(entry.synthesis_fingerprint) is None
            or not entry.chunk_fingerprints
            or any(_SHA256_PATTERN.fullmatch(fingerprint) is None for fingerprint in entry.chunk_fingerprints)
            or _SHA256_PATTERN.fullmatch(entry.clip_hash) is None
            or entry.clip_path != expected_path
            or entry.size_bytes <= 0
            or entry.sample_rate <= 0
            or entry.channels <= 0
            or entry.duration_ms <= 0
            or entry.status != _COMPLETE_STATUS
            or entry.clip_format not in {item.value for item in AudioFormat}
        ):
            raise ValueError
        entries[key] = entry
    return schema_version, scope_id, entries


def _manifest_schema_version(raw: object) -> int:
    if type(raw) is not dict:
        raise TypeError
    manifest: dict[str, Any] = raw
    return _exact_int(manifest.get("schema_version"))


def _repository_lock(root: Path) -> threading.RLock:
    resolved: Path = root.resolve()
    with _REPOSITORY_LOCKS_GUARD:
        lock: threading.RLock | None = _REPOSITORY_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _REPOSITORY_LOCKS[resolved] = lock
        return lock


def _exact_str(value: object) -> str:
    if type(value) is not str:
        raise TypeError
    return value


def _exact_int(value: object) -> int:
    if type(value) is not int:
        raise TypeError
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise TypeError
    return tuple(value)


def _raise_cancelled() -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message="TTS clip commit was cancelled",
        suggestion="Resume will reuse clips committed before cancellation.",
    )
    raise TtsCancelledError(context=context)


def _raise_clip_invalid() -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="Provider clip failed full decode validation",
        suggestion="Retry this request; the invalid temporary clip was discarded.",
    )
    raise TtsClipValidationError(context=context)
