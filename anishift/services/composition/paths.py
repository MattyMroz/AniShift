"""Result placement, output naming, and FFmpeg-safe path handling."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Final

from anishift.services.composition.types import OutputVariant

__all__ = [
    "escape_filter_path",
    "filter_safe_copy",
    "output_path",
    "temporary_sibling",
]

# ── Constants ────────────────────────────────────────────────────────────────

_RESULT_INFIX: Final[str] = ".pl"
"""Infix marking a file as the Polish product of this application."""

_VARIANT_SUFFIX: Final[dict[OutputVariant, str]] = {
    OutputVariant.MERGE: ".mkv",
    OutputVariant.BURN: ".mp4",
}
"""Container extension produced by each assembling variant."""

_FILTER_ESCAPED: Final[tuple[str, ...]] = (":", "[", "]", ",")
"""Filter metacharacters neutralised with a backslash."""

_DIGEST_LENGTH: Final[int] = 12
"""Hex characters of the stem digest keeping working copies unique."""


def output_path(source: Path, variant: OutputVariant, destination_dir: Path) -> Path:
    """Return the finished artifact path for one source and variant."""
    suffix: str = _VARIANT_SUFFIX[variant]
    return destination_dir / f"{source.stem}{_RESULT_INFIX}{suffix}"


def escape_filter_path(path: Path) -> str:
    """Return a path usable inside an FFmpeg subtitle filter value."""
    text: str = path.as_posix().replace("\\", "/")
    for character in _FILTER_ESCAPED:
        text = text.replace(character, f"\\{character}")
    return f"'{text}'"


def filter_safe_copy(subtitle: Path, work_dir: Path) -> Path:
    """Copy a subtitle to a safe basename for FFmpeg's working directory."""
    digest: str = hashlib.sha256(subtitle.name.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    target: Path = work_dir / f"subtitle-{digest}{subtitle.suffix}"
    work_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(subtitle, target)
    return target


def temporary_sibling(path: Path) -> Path:
    """Reserve a unique temporary file beside the destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int
    raw_path: str
    descriptor, raw_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=f".tmp{path.suffix}",
    )
    os.close(descriptor)
    return Path(raw_path)
