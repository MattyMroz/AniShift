"""Encode cached AniList covers into native terminal images ahead of use on one background thread."""

from __future__ import annotations

import math
import threading
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps

from anishift.cli.interactive.native_image import NativeImage, encode_sixel
from anishift.paths import cover_name, covers_dir

__all__ = ["COVER_ASPECT", "COVER_ROWS", "CoverImages", "cover_image"]

# ── Constants ─────────────────────────────────────────────────────────────────

COVER_ROWS: Final[int] = 13
"""Text rows of the cover slot, odd so the slot has a middle row, the same for every cover."""

COVER_ASPECT: Final[float] = 0.72
"""Width to height ratio of an AniList cover, 460 x 636 pixels."""

_STATIC_SECONDS: Final[float] = 1.0
"""Cycle of a cover, which has one frame."""


def cover_box(cell: tuple[int, int]) -> tuple[int, int]:
    """Return the columns and rows of the cover slot for one cell size."""
    return math.ceil(COVER_ROWS * cell[1] * COVER_ASPECT / cell[0]), COVER_ROWS


def cover_image(path: Path, cell: tuple[int, int]) -> NativeImage | None:
    """Scale one cover into the slot, centered on a transparent canvas, and encode it, or None for a bad file."""
    columns, rows = cover_box(cell)
    size: tuple[int, int] = (columns * cell[0], rows * cell[1])
    try:
        with Image.open(path) as source:
            picture: Image.Image = ImageOps.contain(source.convert("RGBA"), size, Image.Resampling.LANCZOS)
        canvas: Image.Image = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.paste(picture, ((size[0] - picture.width) // 2, (size[1] - picture.height) // 2))
        payload: str = encode_sixel(canvas)
    except OSError, ValueError, Image.DecompressionBombError:
        return None
    return NativeImage((payload,), (_STATIC_SECONDS,), _STATIC_SECONDS, columns, rows, rows)


class CoverImages:
    """Keep every listed cover encoded in memory, encoding missing ones on the thread anishift-cover."""

    def __init__(
        self,
        invalidate: Callable[[], None],
        cell: Callable[[], tuple[int, int] | None],
        directory: Callable[[], Path] = covers_dir,
    ) -> None:
        self._invalidate: Callable[[], None] = invalidate
        self._cell: Callable[[], tuple[int, int] | None] = cell
        self._directory: Callable[[], Path] = directory
        self._lock: threading.Lock = threading.Lock()
        self._ready: dict[int, NativeImage | None] = {}
        self._queue: deque[int] = deque()
        self._wake: threading.Event = threading.Event()
        self._worker: threading.Thread | None = None

    def box(self) -> tuple[int, int] | None:
        """Return the columns and rows of the cover slot, or None in a terminal without SIXEL."""
        cell: tuple[int, int] | None = self._cell()
        return None if cell is None else cover_box(cell)

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
        self._wake.set()

    def _run(self) -> None:
        while self._wake.wait():
            self._wake.clear()
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
            return None
