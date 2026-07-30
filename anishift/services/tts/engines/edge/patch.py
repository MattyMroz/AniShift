"""Strict, version-aware edge-tts quality patch."""

from __future__ import annotations

import importlib.metadata
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Never

from .constants import OUTPUT_FORMAT, SUPPORTED_EDGE_TTS_VERSION
from .types import EdgePatchResult, EdgePatchStatus

__all__ = ["ensure_edge_quality_patch"]

_DISTRIBUTION_NAME: Final[str] = "edge-tts"
"""Installed distribution containing the Edge runtime."""

_COMMUNICATE_RELATIVE_PATH: Final[Path] = Path("edge_tts/communicate.py")
"""Source file containing the requested provider output format."""

_CONSTANTS_RELATIVE_PATH: Final[Path] = Path("edge_tts/constants.py")
"""Source file containing bitrate metadata used for timing."""

_OLD_OUTPUT_FORMAT: Final[str] = "audio-24khz-48kbitrate-mono-mp3"
"""Unpatched provider output format in the supported release."""

_OLD_BITRATE_ASSIGNMENT: Final[str] = "MP3_BITRATE_BPS = 48_000"
"""Unpatched bitrate metadata assignment in the supported release."""

_NEW_BITRATE_ASSIGNMENT: Final[str] = "MP3_BITRATE_BPS = 96_000"
"""Required bitrate metadata assignment after patching."""


@dataclass(frozen=True, slots=True)
class _EdgePackage:
    version: str
    communicate_path: Path
    constants_path: Path


def ensure_edge_quality_patch() -> EdgePatchResult:
    """Prepare the supported edge-tts package before any runtime import."""
    package: _EdgePackage | None = _locate_package()
    if package is None:
        result: EdgePatchResult = EdgePatchResult(
            status=EdgePatchStatus.PACKAGE_MISSING,
            message="edge-tts is not installed; reinstall AniShift dependencies.",
            detected_version="missing",
            changed=False,
        )
    elif package.version != SUPPORTED_EDGE_TTS_VERSION:
        result = _unsupported_version_result(package.version)
    else:
        try:
            result = _prepare_supported_package(package)
        except PermissionError:
            result = EdgePatchResult(
                status=EdgePatchStatus.READ_ONLY,
                message=_repair_message(
                    package.version,
                    "edge-tts installation is read-only",
                ),
                detected_version=package.version,
                changed=False,
            )
        except (FileNotFoundError, UnicodeDecodeError, OSError) as exc:
            result = _io_result(package.version, exc)
    return result


def _prepare_supported_package(package: _EdgePackage) -> EdgePatchResult:
    communicate_source: str = _read_source(package.communicate_path)
    constants_source: str = _read_source(package.constants_path)
    if not _has_known_output_layout(communicate_source) or not _has_known_bitrate_layout(constants_source):
        return EdgePatchResult(
            status=EdgePatchStatus.UNKNOWN_LAYOUT,
            message=_repair_message(
                package.version,
                "edge-tts source layout is unknown",
            ),
            detected_version=package.version,
            changed=False,
        )
    patched_communicate: str = communicate_source.replace(_OLD_OUTPUT_FORMAT, OUTPUT_FORMAT)
    patched_constants: str = constants_source.replace(
        _OLD_BITRATE_ASSIGNMENT,
        _NEW_BITRATE_ASSIGNMENT,
    )
    changed: bool = patched_communicate != communicate_source or patched_constants != constants_source
    if changed:
        _replace_sources(
            package,
            communicate_source=patched_communicate,
            constants_source=patched_constants,
        )
    verified_communicate: str = _read_source(package.communicate_path)
    verified_constants: str = _read_source(package.constants_path)
    if not _is_fully_patched(verified_communicate, verified_constants):
        return EdgePatchResult(
            status=EdgePatchStatus.UNKNOWN_LAYOUT,
            message=_repair_message(
                package.version,
                "edge-tts quality patch could not be verified",
            ),
            detected_version=package.version,
            changed=False,
        )
    return EdgePatchResult(
        status=EdgePatchStatus.READY,
        message=f"edge-tts {package.version} is ready for 24 kHz / 96 kb/s mono MP3",
        detected_version=package.version,
        changed=changed,
    )


def _locate_package() -> _EdgePackage | None:
    try:
        distribution: importlib.metadata.Distribution = importlib.metadata.distribution(_DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError:
        return None
    return _EdgePackage(
        version=distribution.version,
        communicate_path=Path(str(distribution.locate_file(_COMMUNICATE_RELATIVE_PATH))),
        constants_path=Path(str(distribution.locate_file(_CONSTANTS_RELATIVE_PATH))),
    )


def _read_source(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as source_file:
        return source_file.read()


def _has_known_output_layout(source: str) -> bool:
    old_count: int = source.count(_output_marker(_OLD_OUTPUT_FORMAT))
    new_count: int = source.count(_output_marker(OUTPUT_FORMAT))
    return old_count + new_count == 1


def _has_known_bitrate_layout(source: str) -> bool:
    old_count: int = source.count(_OLD_BITRATE_ASSIGNMENT)
    new_count: int = source.count(_NEW_BITRATE_ASSIGNMENT)
    return old_count + new_count == 1


def _is_fully_patched(communicate_source: str, constants_source: str) -> bool:
    return (
        _OLD_OUTPUT_FORMAT not in communicate_source
        and communicate_source.count(_output_marker(OUTPUT_FORMAT)) == 1
        and _OLD_BITRATE_ASSIGNMENT not in constants_source
        and constants_source.count(_NEW_BITRATE_ASSIGNMENT) == 1
    )


def _output_marker(output_format: str) -> str:
    return f'"outputFormat":"{output_format}"'


def _replace_sources(
    package: _EdgePackage,
    *,
    communicate_source: str,
    constants_source: str,
) -> None:
    original_communicate: str = _read_source(package.communicate_path)
    staged_communicate: Path = _stage_source(package.communicate_path, communicate_source)
    staged_constants: Path | None = None
    communicate_replaced: bool = False
    try:
        staged_constants = _stage_source(package.constants_path, constants_source)
        if not _is_fully_patched(
            _read_source(staged_communicate),
            _read_source(staged_constants),
        ):
            _raise_staged_validation_error()
        _replace_file(staged_communicate, package.communicate_path)
        communicate_replaced = True
        _replace_file(staged_constants, package.constants_path)
    except OSError:
        if communicate_replaced:
            rollback_path: Path = _stage_source(package.communicate_path, original_communicate)
            try:
                _replace_file(rollback_path, package.communicate_path)
            finally:
                rollback_path.unlink(missing_ok=True)
        raise
    finally:
        staged_communicate.unlink(missing_ok=True)
        if staged_constants is not None:
            staged_constants.unlink(missing_ok=True)


def _stage_source(destination: Path, source: str) -> Path:
    mode: int = stat.S_IMODE(destination.stat().st_mode)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_file.write(source)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_path: Path = Path(temp_file.name)
    temp_path.chmod(mode)
    return temp_path


def _replace_file(source: Path, destination: Path) -> None:
    source.replace(destination)


def _raise_staged_validation_error() -> Never:
    message: str = "Staged edge-tts patch failed validation"
    raise OSError(message)


def _unsupported_version_result(version: str) -> EdgePatchResult:
    return EdgePatchResult(
        status=EdgePatchStatus.UNSUPPORTED_VERSION,
        message=_repair_message(
            version,
            f"unsupported edge-tts version (expected {SUPPORTED_EDGE_TTS_VERSION})",
        ),
        detected_version=version,
        changed=False,
    )


def _io_result(version: str, exc: OSError | UnicodeDecodeError) -> EdgePatchResult:
    return EdgePatchResult(
        status=EdgePatchStatus.IO_ERROR,
        message=_repair_message(
            version,
            f"edge-tts files could not be prepared ({type(exc).__name__})",
        ),
        detected_version=version,
        changed=False,
    )


def _repair_message(version: str, reason: str) -> str:
    return (
        f"{reason}; detected {version}, supported {SUPPORTED_EDGE_TTS_VERSION}. "
        "Reinstall or update AniShift dependencies before using Edge."
    )
