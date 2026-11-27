"""Validate AniList cover images and keep them as JPEG files named only after their AniList ID."""

from __future__ import annotations

import re
from io import BytesIO
from typing import TYPE_CHECKING, Final

from PIL import Image

from anishift.errors import ErrorCode, ErrorContext
from anishift.paths import COVER_ENCODING, COVER_PAYLOADS, cover_name
from anishift.services.catalog.errors import TitleCatalogError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["cover_path", "prune_covers", "store_cover", "stored_covers"]

# ── Constants ─────────────────────────────────────────────────────────────────

_COVER_NAME: Final[re.Pattern[str]] = re.compile(r"([1-9]\d*)\.jpg")
"""Name of a cached cover: the AniList ID and the JPEG suffix, nothing else."""

_PAYLOAD_SUFFIX: Final[str] = ".six"
"""Suffix of every encoded SIXEL payload of a cover, whatever its encoding version."""

_PAYLOAD_NAME: Final[re.Pattern[str]] = re.compile(rf"([1-9]\d*)-\d+x\d+-v{COVER_ENCODING}\{_PAYLOAD_SUFFIX}")
"""Name of a payload in the current encoding: the AniList ID, the cell size and the encoding version."""

_PAYLOAD_TEMPORARY: Final[re.Pattern[str]] = re.compile(rf"(.+\{_PAYLOAD_SUFFIX})\.\d+\.tmp")
"""Name of a payload being written: the payload name, the writing process ID and a temporary suffix."""

_JPEG_QUALITY: Final[int] = 90
"""JPEG quality of a stored cover, close to the CDN file it replaces."""

_TEMPORARY_SUFFIX: Final[str] = ".tmp"
"""Suffix of the file a cover is written to before it replaces the cached one."""

_UNREADABLE: Final[str] = "AniList returned an unreadable cover"
"""Message of a cover file Pillow cannot read."""


def cover_path(directory: Path, anilist_id: int) -> Path:
    """Return the cached cover file of one AniList entry."""
    return directory / cover_name(anilist_id)


def stored_covers(directory: Path) -> frozenset[int]:
    """Return the AniList IDs whose covers are cached in *directory*, none when it does not exist."""
    return frozenset(int(match.group(1)) for item in _files(directory) if (match := _COVER_NAME.fullmatch(item.name)))


def prune_covers(directory: Path, kept: frozenset[int]) -> tuple[frozenset[int], int]:
    """Delete covers outside *kept* and payloads of no cover or another encoding; return deleted IDs and failures."""
    removed: set[int] = set()
    failed: int = 0
    for path in _files(directory):
        match: re.Match[str] | None = _COVER_NAME.fullmatch(path.name.removesuffix(_TEMPORARY_SUFFIX))
        if match is None or int(match.group(1)) in kept:
            continue
        if not _deleted(path):
            failed += 1
        elif path.name == match.group(0):
            removed.add(int(match.group(1)))
    covers: frozenset[int] = stored_covers(directory)
    for path in _files(directory / COVER_PAYLOADS):
        temporary: re.Match[str] | None = _PAYLOAD_TEMPORARY.fullmatch(path.name)
        target: str = path.name if temporary is None else temporary.group(1)
        current: re.Match[str] | None = _PAYLOAD_NAME.fullmatch(target)
        if target.endswith(_PAYLOAD_SUFFIX) and (current is None or int(current.group(1)) not in covers):
            failed += not _deleted(path)
    return frozenset(removed), failed


def store_cover(data: bytes, directory: Path, anilist_id: int) -> Path:
    """Verify *data* as an image and write it atomically as the RGB JPEG cover of one AniList entry."""
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        with Image.open(BytesIO(data)) as image:
            picture: Image.Image = image.convert("RGB")
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        raise TitleCatalogError(
            context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message=_UNREADABLE)
        ) from error
    path: Path = cover_path(directory, anilist_id)
    temporary: Path = path.with_name(f"{path.name}{_TEMPORARY_SUFFIX}")
    directory.mkdir(parents=True, exist_ok=True)
    picture.save(temporary, "JPEG", quality=_JPEG_QUALITY)
    temporary.replace(path)
    return path


def _files(directory: Path) -> list[Path]:
    try:
        return [item for item in directory.iterdir() if item.is_file()]
    except FileNotFoundError:
        return []


def _deleted(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True
