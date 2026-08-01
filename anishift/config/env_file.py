"""Atomic edits for individual values in AniShift's UTF-8 ``.env`` file."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Final

from anishift.utils.logger import get_logger

__all__ = ["env_path", "update_env_value"]

logger = get_logger(__name__)

_ENV_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Z_][A-Z0-9_]*\Z")
"""Environment-variable names accepted by the editor."""

_NEWLINE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\r\n|\n|\r")
"""Recognized newline sequences in preference order at their first position."""

_UTF8_BOM: Final[bytes] = b"\xef\xbb\xbf"
"""UTF-8 byte-order mark preserved when already present."""


def env_path() -> Path:
    """Return the repository-level ``.env`` path."""
    return Path(__file__).resolve().parents[2] / ".env"


def update_env_value(
    key: str,
    value: str | None,
    *,
    path: Path | None = None,
) -> None:
    """Atomically set, clear, or remove one exact environment key."""
    if _ENV_KEY_PATTERN.fullmatch(key) is None:
        message: str = "Environment key must use uppercase letters, digits, and underscores"
        raise ValueError(message)
    target: Path = path or env_path()
    original: bytes = target.read_bytes() if target.is_file() else b""
    has_bom: bool = original.startswith(_UTF8_BOM)
    payload: bytes = original[len(_UTF8_BOM) :] if has_bom else original
    text: str = payload.decode("utf-8")
    newline: str = _detect_newline(text)
    updated: str = _updated_text(text, key=key, value=value, newline=newline)
    encoded: bytes = (_UTF8_BOM if has_bom else b"") + updated.encode("utf-8")
    _atomic_write(target, encoded)
    logger.info(
        "Environment setting updated",
        key=key,
        action="remove" if value is None else "set",
    )


def _detect_newline(text: str) -> str:
    match: re.Match[str] | None = _NEWLINE_PATTERN.search(text)
    return match.group() if match is not None else "\n"


def _updated_text(
    text: str,
    *,
    key: str,
    value: str | None,
    newline: str,
) -> str:
    assignment_pattern: re.Pattern[str] = re.compile(
        rf"^(?P<prefix>[ \t]*(?:export[ \t]+)?){re.escape(key)}[ \t]*=",
    )
    replacement: str | None = None if value is None else f"{key}={_encode_value(value)}"
    updated_lines: list[str] = []
    found: bool = False
    for line in text.splitlines(keepends=True):
        body, ending = _split_line_ending(line)
        match: re.Match[str] | None = assignment_pattern.match(body)
        if match is None:
            updated_lines.append(line)
            continue
        found = True
        if replacement is not None:
            updated_lines.append(f"{match.group('prefix')}{replacement}{ending}")
    if found or replacement is None:
        return "".join(updated_lines)
    if updated_lines and not updated_lines[-1].endswith(("\r", "\n")):
        updated_lines[-1] = f"{updated_lines[-1]}{newline}"
    updated_lines.append(f"{replacement}{newline}")
    return "".join(updated_lines)


def _split_line_ending(line: str) -> tuple[str, str]:
    for ending in ("\r\n", "\n", "\r"):
        if line.endswith(ending):
            return line[: -len(ending)], ending
    return line, ""


def _encode_value(value: str) -> str:
    if not value:
        return ""
    escaped: str = value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
    return f'"{escaped}"'


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode: int | None = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        if original_mode is not None:
            temporary_path.chmod(original_mode)
        temporary_path.replace(path)
        _fsync_directory(path.parent)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _fsync_directory(path: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
