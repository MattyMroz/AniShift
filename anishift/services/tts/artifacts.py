"""Crash-safe filesystem operations for TTS-owned resume artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsResumeError
from anishift.services.tts.fingerprint import artifact_key
from anishift.services.tts.types import AudioFormat

__all__ = ["TtsArtifactLayout", "atomic_json_snapshot", "sha256_file"]

_COPY_BUFFER_BYTES: Final[int] = 1024 * 1024
"""Streaming hash buffer size."""

_SNAPSHOT_REPLACE_ATTEMPTS: Final[int] = 5
"""Maximum attempts for a transiently blocked atomic snapshot replacement."""

_SNAPSHOT_RETRY_DELAY_S: Final[float] = 0.05
"""Base delay between atomic snapshot replacement attempts."""


@dataclass(frozen=True, slots=True)
class TtsArtifactLayout:
    """Controlled paths belonging exclusively to one TTS resume repository."""

    root: Path

    @property
    def manifest_path(self) -> Path:
        """Return the versioned TTS manifest path."""
        return self.root / "manifest.json"

    @property
    def clips_dir(self) -> Path:
        """Return the directory containing provider-native clips."""
        return self.root / "clips"

    def initialize(self) -> None:
        """Create only directories owned by this TTS repository."""
        if self.root.exists() and _is_redirect(self.root):
            root_message: str = "TTS repository root cannot be a symlink or junction"
            raise TtsResumeError(root_message)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            _raise_artifact_io("initialize_root", error)
        if self.clips_dir.exists() and _is_redirect(self.clips_dir):
            clips_message: str = "TTS clips directory cannot be a symlink or junction"
            raise TtsResumeError(clips_message)
        try:
            self.clips_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            _raise_artifact_io("initialize_clips", error)
        try:
            self.clips_dir.resolve().relative_to(self.root.resolve())
        except ValueError as error:
            escape_message = "TTS clips directory escapes the repository root"
            raise TtsResumeError(escape_message) from error

    def clip_path(
        self,
        *,
        request_id: str,
        fingerprint: str,
        clip_format: AudioFormat,
    ) -> Path:
        """Return the deterministic final path without exposing request ids."""
        key: str = artifact_key(request_id, fingerprint)
        return self.clips_dir / f"clip-{key}.{clip_format.value}"

    def temporary_clip_path(self, *, clip_format: AudioFormat) -> Path:
        """Reserve a unique sibling temp path for one provider attempt."""
        self.initialize()
        try:
            descriptor, raw_path = tempfile.mkstemp(
                dir=self.clips_dir,
                prefix=".clip-",
                suffix=f".{clip_format.value}.tmp",
            )
        except OSError as error:
            _raise_artifact_io("create_temporary_clip", error)
        os.close(descriptor)
        return Path(raw_path)

    def relative_clip_path(self, path: Path) -> str:
        """Return a canonical relative POSIX path after containment checks."""
        resolved: Path = self._contained_clip(path)
        return resolved.relative_to(self.root.resolve()).as_posix()

    def publish_clip(
        self,
        temporary_path: Path,
        final_path: Path,
        *,
        clip_format: AudioFormat,
    ) -> None:
        """Atomically publish a validated same-directory temporary clip."""
        temporary: Path = self.validate_temporary_clip(
            temporary_path,
            clip_format=clip_format,
        )
        final: Path = self._contained_clip(final_path)
        if temporary.parent != self.clips_dir.resolve() or final.parent != temporary.parent:
            message: str = "TTS clip commit must stay inside the owned clips directory"
            raise TtsResumeError(message)
        if temporary.is_symlink() or final.is_symlink():
            message = "TTS clip paths cannot be symbolic links"
            raise TtsResumeError(message)
        try:
            temporary.replace(final)
        except OSError as error:
            _raise_artifact_io("publish_clip", error)

    def discard_temporary_clip(self, path: Path) -> None:
        """Remove only one repository-created uncommitted clip."""
        temporary: Path = self._contained_clip(path)
        if temporary.parent != self.clips_dir.resolve() or not _is_temp_name(temporary.name):
            message: str = "Refusing to remove a non-temporary TTS artifact"
            raise TtsResumeError(message)
        try:
            temporary.unlink(missing_ok=True)
        except OSError as error:
            _raise_artifact_io("discard_temporary_clip", error)

    def validate_temporary_clip(
        self,
        path: Path,
        *,
        clip_format: AudioFormat,
    ) -> Path:
        """Prove a path matches this repository's reserved temp contract."""
        lexical: Path = path.absolute()
        expected_parent: Path = self.clips_dir.absolute()
        expected_suffix: str = f".{clip_format.value}.tmp"
        if (
            lexical.parent != expected_parent
            or not lexical.name.startswith(".clip-")
            or not lexical.name.endswith(expected_suffix)
            or _is_redirect(path)
        ):
            message: str = "TTS commit input is not a reserved temporary clip"
            raise TtsResumeError(message)
        return self._contained_clip(path)

    def _contained_clip(self, path: Path) -> Path:
        if path.is_symlink():
            symlink_message: str = "TTS artifact paths cannot be symbolic links"
            raise TtsResumeError(symlink_message)
        resolved: Path = path.resolve()
        try:
            resolved.relative_to(self.clips_dir.resolve())
        except ValueError as error:
            escape_message: str = "TTS artifact path escapes the owned clips directory"
            raise TtsResumeError(escape_message) from error
        return resolved


def _is_redirect(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _is_temp_name(name: str) -> bool:
    return name.startswith(".clip-") and name.endswith(".tmp")


def sha256_file(path: Path) -> str:
    """Return a prefixed streaming SHA-256 digest."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while block := stream.read(_COPY_BUFFER_BYTES):
                digest.update(block)
    except OSError as error:
        _raise_artifact_io("hash_clip", error)
    return f"sha256:{digest.hexdigest()}"


def atomic_json_snapshot(path: Path, payload: dict[str, object]) -> None:
    """Write canonical UTF-8 JSON through a flushed sibling temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded: str = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
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
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        _replace_snapshot(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _replace_snapshot(temporary_path: Path, path: Path) -> None:
    for attempt in range(1, _SNAPSHOT_REPLACE_ATTEMPTS + 1):
        try:
            temporary_path.replace(path)
        except OSError:
            if attempt == _SNAPSHOT_REPLACE_ATTEMPTS:
                raise
            time.sleep(_SNAPSHOT_RETRY_DELAY_S * attempt)
        else:
            return


def _raise_artifact_io(operation: str, error: OSError) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_RESUME_ERROR,
        message="TTS resume artifact operation failed",
        suggestion="Check workspace permissions, locks, and free disk space.",
        details={"operation": operation},
    )
    raise TtsResumeError(context=context) from error
