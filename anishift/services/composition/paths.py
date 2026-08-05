"""Result placement, output naming, and FFmpeg-safe path handling."""

from __future__ import annotations

import hashlib
import os
import re
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

_FILTER_UNSAFE: Final[re.Pattern[str]] = re.compile(r"['\"]+")
"""Quote characters the FFmpeg subtitle filter drops regardless of escaping."""

_FILTER_ESCAPED: Final[tuple[str, ...]] = (":", "[", "]", ",")
"""Filter metacharacters neutralised with a backslash."""

_SAFE_STEM_LENGTH: Final[int] = 32
"""Maximum retained characters of a sanitised working-copy stem."""

_DIGEST_LENGTH: Final[int] = 12
"""Hex characters of the stem digest keeping working copies unique."""


def output_path(source: Path, variant: OutputVariant, destination_dir: Path) -> Path:
    """Return the finished artifact path for one source and variant.

    Args:
        source: Original container.
        variant: Assembling variant; ``PLAYERS`` has no single artifact.
        destination_dir: Directory the artifact is written to.

    Returns:
        The destination path carrying the Polish result infix.
    """
    suffix: str = _VARIANT_SUFFIX[variant]
    return destination_dir / f"{source.stem}{_RESULT_INFIX}{suffix}"


def escape_filter_path(path: Path) -> str:
    """Return a path usable inside an FFmpeg subtitle filter value.

    ``as_posix`` removes backslashes, then the drive colon and the remaining
    filter metacharacters are escaped. Apostrophes are NOT handled — the filter
    drops them whatever the escaping, so callers pass a
    :func:`filter_safe_copy` result instead.
    """
    text: str = path.as_posix()
    for character in _FILTER_ESCAPED:
        text = text.replace(character, f"\\{character}")
    return f"'{text}'"


def filter_safe_copy(subtitle: Path, work_dir: Path) -> Path:
    """Copy a subtitle to a deterministic name FFmpeg can always open.

    The copy is rewritten on every call: a subtitle is a small text file and a
    stale copy would silently burn the previous run's text.

    Args:
        subtitle: Subtitle file that may carry quote characters in its name.
        work_dir: Directory owned by this run for working copies.

    Returns:
        Path to the working copy.
    """
    digest: str = hashlib.sha256(subtitle.name.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    stem: str = _FILTER_UNSAFE.sub("", subtitle.stem)[:_SAFE_STEM_LENGTH].strip() or "subtitle"
    target: Path = work_dir / f"{stem}-{digest}{subtitle.suffix}"
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
