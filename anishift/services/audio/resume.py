"""Crash-safe ownership metadata for audio narration and final sidecars."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.errors import AudioResumeError
from anishift.services.audio.fingerprint import sha256_file
from anishift.utils.logger import get_logger

__all__ = ["AudioResumeRepository"]

# ── Constants ────────────────────────────────────────────────────────────────

_SCHEMA_VERSION: Final[int] = 1
"""Current all-or-nothing Audio resume manifest schema."""

_LOCKS_GUARD: Final[threading.Lock] = threading.Lock()
"""Protects creation of process-local manifest locks."""

_LOCKS: Final[dict[Path, threading.RLock]] = {}
"""Process-local serialization by resolved Audio manifest path."""

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ArtifactEntry:
    fingerprint: str
    path: str
    file_hash: str


class AudioResumeRepository:
    """Own one scope's narration metadata and final sidecar ownership."""

    def __init__(self, root: Path, scope_id: str) -> None:
        """Initialize the Audio-only repository without touching TTS state."""
        self._root: Path = root
        self._scope_id: str = scope_id
        self._manifest_path: Path = root / "manifest.json"
        self._lock: threading.RLock = _manifest_lock(self._manifest_path)
        self._narration: _ArtifactEntry | None = None
        self._outputs: dict[str, _ArtifactEntry] = {}
        self._initialize()
        with self._lock:
            self._reload()

    @property
    def narration_dir(self) -> Path:
        """Return the directory containing Audio-owned narrator artifacts."""
        return self._root / "narration"

    def narration_hit(self, fingerprint: str) -> Path | None:
        """Return a valid narrator for the exact fingerprint."""
        with self._lock:
            self._reload()
            entry: _ArtifactEntry | None = self._narration
            if entry is None or entry.fingerprint != fingerprint:
                return None
            path: Path = self._relative_path(entry.path)
            if not _matches(path, entry.file_hash):
                return None
            return path

    def commit_narration(self, fingerprint: str, path: Path) -> None:
        """Record a validated Audio-owned narrator WAV."""
        with self._lock:
            self._reload()
            relative: str = self._relative_name(path)
            self._narration = _ArtifactEntry(
                fingerprint=fingerprint,
                path=relative,
                file_hash=sha256_file(path),
            )
            self._snapshot()

    def output_hit(self, path: Path, fingerprint: str) -> bool:
        """Return whether an existing final sidecar is a valid exact hit."""
        with self._lock:
            self._reload()
            key: str = _output_key(path)
            entry: _ArtifactEntry | None = self._outputs.get(key)
            return entry is not None and entry.fingerprint == fingerprint and _matches(path, entry.file_hash)

    def commit_output(self, fingerprint: str, path: Path) -> None:
        """Record ownership of one validated final sidecar."""
        with self._lock:
            self._reload()
            self._outputs[_output_key(path)] = _ArtifactEntry(
                fingerprint=fingerprint,
                path=str(path.resolve()),
                file_hash=sha256_file(path),
            )
            self._snapshot()

    def _initialize(self) -> None:
        if self._root.exists() and _is_redirect(self._root):
            _raise_resume("Audio repository root cannot be a symlink or junction")
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self.narration_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            _raise_resume("Audio repository could not be initialized", cause=error)
        if _is_redirect(self.narration_dir):
            _raise_resume("Audio narration directory cannot be a symlink or junction")

    def _reload(self) -> None:
        self._narration = None
        self._outputs = {}
        if not self._manifest_path.is_file():
            return
        try:
            raw: object = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            schema_version: int = _manifest_schema_version(raw)
            if schema_version > _SCHEMA_VERSION:
                _raise_resume("Audio resume manifest uses a newer schema")
            schema, scope_id, narration, outputs = _parse_manifest(raw)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            self._quarantine(error)
            return
        if schema != _SCHEMA_VERSION or scope_id != self._scope_id:
            self._quarantine(ValueError("manifest identity mismatch"))
            return
        self._narration = narration
        self._outputs = outputs

    def _snapshot(self) -> None:
        payload: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "scope_id": self._scope_id,
            "narration": _entry_payload(self._narration),
            "outputs": {key: _entry_payload(entry) for key, entry in sorted(self._outputs.items())},
        }
        _atomic_json(self._manifest_path, payload)

    def _quarantine(self, error: BaseException) -> None:
        diagnostic: Path = self._root / (f"manifest.corrupt.{time.time_ns()}.{secrets.token_hex(4)}.json")
        try:
            self._manifest_path.replace(diagnostic)
        except OSError as quarantine_error:
            _raise_resume(
                "Corrupt Audio manifest could not be preserved",
                cause=quarantine_error,
            )
        self._narration = None
        self._outputs = {}
        logger.warning(
            "Invalid audio resume manifest quarantined",
            scope_id=self._scope_id,
            error_type=type(error).__name__,
        )

    def _relative_name(self, path: Path) -> str:
        resolved: Path = path.resolve()
        try:
            relative: Path = resolved.relative_to(self._root.resolve())
        except ValueError as error:
            _raise_resume("Narrator path escapes the Audio repository", cause=error)
        return relative.as_posix()

    def _relative_path(self, relative: str) -> Path:
        path: Path = (self._root / relative).resolve()
        try:
            path.relative_to(self._root.resolve())
        except ValueError as error:
            _raise_resume("Manifest narrator path escapes the Audio repository", cause=error)
        return path


def _parse_manifest(
    raw: object,
) -> tuple[int, str, _ArtifactEntry | None, dict[str, _ArtifactEntry]]:
    if not isinstance(raw, dict):
        raise TypeError
    manifest: dict[str, Any] = raw
    if set(manifest) != {"schema_version", "scope_id", "narration", "outputs"}:
        raise ValueError
    schema: object = manifest["schema_version"]
    scope_id: object = manifest["scope_id"]
    outputs_raw: object = manifest["outputs"]
    if type(schema) is not int or not isinstance(scope_id, str) or not scope_id:
        raise ValueError
    if not isinstance(outputs_raw, dict):
        raise TypeError
    narration: _ArtifactEntry | None = _parse_optional_entry(manifest["narration"])
    outputs: dict[str, _ArtifactEntry] = {}
    for key, value in outputs_raw.items():
        if not isinstance(key, str):
            raise TypeError
        outputs[key] = _parse_entry(value)
    return schema, scope_id, narration, outputs


def _manifest_schema_version(raw: object) -> int:
    if not isinstance(raw, dict):
        raise TypeError
    schema: object = raw.get("schema_version")
    if type(schema) is not int:
        raise ValueError
    return schema


def _parse_optional_entry(raw: object) -> _ArtifactEntry | None:
    if raw is None:
        return None
    return _parse_entry(raw)


def _parse_entry(raw: object) -> _ArtifactEntry:
    if not isinstance(raw, dict) or set(raw) != {"fingerprint", "path", "file_hash"}:
        raise ValueError
    values: dict[str, object] = raw
    fingerprint: object = values["fingerprint"]
    path: object = values["path"]
    file_hash: object = values["file_hash"]
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError
    if not isinstance(path, str) or not path:
        raise ValueError
    if not isinstance(file_hash, str) or not file_hash:
        raise ValueError
    return _ArtifactEntry(
        fingerprint=fingerprint,
        path=path,
        file_hash=file_hash,
    )


def _entry_payload(entry: _ArtifactEntry | None) -> dict[str, str] | None:
    if entry is None:
        return None
    return {
        "fingerprint": entry.fingerprint,
        "path": entry.path,
        "file_hash": entry.file_hash,
    }


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
            newline="\n",
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except OSError as error:
        _raise_resume("Audio manifest could not be committed", cause=error)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _manifest_lock(path: Path) -> threading.RLock:
    key: Path = path.resolve()
    with _LOCKS_GUARD:
        lock: threading.RLock | None = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


def _matches(path: Path, expected_hash: str) -> bool:
    return path.is_file() and path.stat().st_size > 0 and sha256_file(path) == expected_hash


def _output_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _is_redirect(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _raise_resume(message: str, *, cause: BaseException | None = None) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Check Audio resume directory permissions and integrity.",
        details={"operation": "audio_resume"},
    )
    error: AudioResumeError = AudioResumeError(context=context)
    if cause is not None:
        raise error from cause
    raise error
