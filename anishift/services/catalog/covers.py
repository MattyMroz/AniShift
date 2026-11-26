"""Validate AniList cover images and keep them as JPEG files named only after their AniList ID."""

from __future__ import annotations

import re
from io import BytesIO
from typing import TYPE_CHECKING, Final

from PIL import Image

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.catalog.errors import TitleCatalogError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["cover_path", "store_cover", "stored_covers"]

# ── Constants ─────────────────────────────────────────────────────────────────

_COVER_NAME: Final[re.Pattern[str]] = re.compile(r"([1-9]\d*)\.jpg")
"""Name of a cached cover: the AniList ID and the JPEG suffix, nothing else."""

_JPEG_QUALITY: Final[int] = 90
"""JPEG quality of a stored cover, close to the CDN file it replaces."""

_TEMPORARY_SUFFIX: Final[str] = ".tmp"
"""Suffix of the file a cover is written to before it replaces the cached one."""

_UNREADABLE: Final[str] = "AniList returned an unreadable cover"
"""Message of a cover file Pillow cannot read."""


def cover_path(directory: Path, anilist_id: int) -> Path:
    """Return the cached cover file of one AniList entry."""
    return directory / f"{anilist_id}.jpg"


def stored_covers(directory: Path) -> frozenset[int]:
    """Return the AniList IDs whose covers are cached in *directory*, none when it does not exist."""
    try:
        names: list[str] = [item.name for item in directory.iterdir() if item.is_file()]
    except FileNotFoundError:
        return frozenset()
    return frozenset(int(match.group(1)) for name in names if (match := _COVER_NAME.fullmatch(name)))


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
