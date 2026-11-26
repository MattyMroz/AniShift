"""Encode cached AniList covers into native terminal images ahead of use on one background thread."""

from __future__ import annotations

import math
import threading
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Final

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from anishift.cli.interactive.native_image import NativeImage, encode_sixel
from anishift.paths import cover_name, covers_dir

__all__ = ["COVER_ASPECT", "COVER_ROWS", "CROP_TOLERANCE", "CoverImages", "cover_image", "filled_cover"]

# ── Constants ─────────────────────────────────────────────────────────────────

COVER_ROWS: Final[int] = 13
"""Text rows of the cover slot, odd so the slot has a middle row, the same for every cover."""

COVER_ASPECT: Final[float] = 0.72
"""Width to height ratio of an AniList cover, 460 x 636 pixels."""

_STATIC_SECONDS: Final[float] = 1.0
"""Cycle of a cover, which has one frame."""

CROP_TOLERANCE: Final[float] = 0.08
"""Largest relative aspect difference between a cover and its slot that fills the slot by cropping the excess."""

_CROP_CENTERING: Final[tuple[float, float]] = (0.5, 0.25)
"""Crop anchor: even across, a quarter of the cut height from the top and the rest from the bottom."""

_BACKDROP_BLUR: Final[float] = 0.06
"""Gaussian blur radius of the backdrop behind an uncropped cover, as a share of the slot width."""

_BACKDROP_BRIGHTNESS: Final[float] = 0.6
"""Brightness factor of the blurred backdrop, dim enough for the whole cover to stand out."""


def cover_box(cell: tuple[int, int]) -> tuple[int, int]:
    """Return the columns and rows of the cover slot for one cell size."""
    return math.ceil(COVER_ROWS * cell[1] * COVER_ASPECT / cell[0]), COVER_ROWS


def cover_image(path: Path, cell: tuple[int, int]) -> NativeImage | None:
    """Fill the slot with one cover and encode it, or return None for a bad file."""
    columns, rows = cover_box(cell)
    size: tuple[int, int] = (columns * cell[0], rows * cell[1])
    try:
        with Image.open(path) as source:
            payload: str = encode_sixel(filled_cover(source.convert("RGB"), size).convert("RGBA"))
    except OSError, ValueError, Image.DecompressionBombError:
        return None
    return NativeImage((payload,), (_STATIC_SECONDS,), _STATIC_SECONDS, columns, rows, rows)


def filled_cover(picture: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Crop a cover close to the slot's shape to fill it, else show it whole on its own blurred, dimmed fill."""
    fill: Image.Image = ImageOps.fit(picture, size, Image.Resampling.LANCZOS, centering=_CROP_CENTERING)
    shape: float = picture.width / picture.height
    slot: float = size[0] / size[1]
    if max(shape, slot) / min(shape, slot) - 1 <= CROP_TOLERANCE:
        return fill
    backdrop: Image.Image = ImageEnhance.Brightness(
        fill.filter(ImageFilter.GaussianBlur(size[0] * _BACKDROP_BLUR))
    ).enhance(_BACKDROP_BRIGHTNESS)
    whole: Image.Image = ImageOps.contain(picture, size, Image.Resampling.LANCZOS)
    backdrop.paste(whole, ((size[0] - whole.width) // 2, (size[1] - whole.height) // 2))
    return backdrop


class CoverImages:
    """Keep every listed cover encoded in memory, encoding missing ones on the thread anishift-cover."""

    def __init__(
        self,
        invalidate: Callable[[], None],
        cell: Callable[[], tuple[int, int] | None],
        directory: Callable[[], Path] = covers_dir,
        *,
        shown: Callable[[], bool] = lambda: True,
    ) -> None:
        self._invalidate: Callable[[], None] = invalidate
        self._cell: Callable[[], tuple[int, int] | None] = cell
        self._shown: Callable[[], bool] = shown
        self._directory: Callable[[], Path] = directory
        self._lock: threading.Lock = threading.Lock()
        self._ready: dict[int, NativeImage | None] = {}
        self._queue: deque[int] = deque()
        self._worker: threading.Thread | None = None

    def box(self) -> tuple[int, int] | None:
        """Return the columns and rows of the cover slot, or None with covers off or without SIXEL."""
        cell: tuple[int, int] | None = self._cell()
        return None if cell is None or not self._shown() else cover_box(cell)

    def image(self, anilist_id: int) -> NativeImage | None:
        """Return the encoded cover, or None while it is encoded, unreadable or without SIXEL."""
        if self._cell() is None:
            return None
        with self._lock:
            if anilist_id in self._ready:
                return self._ready[anilist_id]
        self._request((anilist_id,), first=True)
        return None

    def prepare(self, anilist_ids: Iterable[int]) -> None:
        """Queue the covers of a shown list, so moving the highlight finds them encoded."""
        if self._cell() is not None:
            self._request(anilist_ids, first=False)

    def _request(self, anilist_ids: Iterable[int], *, first: bool) -> None:
        with self._lock:
            queued: set[int] = set(self._queue)
            missing: list[int] = [
                item for item in dict.fromkeys(anilist_ids) if item not in self._ready and (first or item not in queued)
            ]
            if not missing:
                return
            if first:
                self._queue.extendleft(reversed(missing))
            else:
                self._queue.extend(missing)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="anishift-cover", daemon=True)
                self._worker.start()

    def _run(self) -> None:
        while (anilist_id := self._next()) is not None:
            cell: tuple[int, int] | None = self._cell()
            encoded: NativeImage | None = (
                None if cell is None else cover_image(self._directory() / cover_name(anilist_id), cell)
            )
            with self._lock:
                self._ready[anilist_id] = encoded
            self._invalidate()

    def _next(self) -> int | None:
        with self._lock:
            while self._queue:
                anilist_id: int = self._queue.popleft()
                if anilist_id not in self._ready:
                    return anilist_id
            self._worker = None
            return None
