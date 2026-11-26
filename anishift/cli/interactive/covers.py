"""Encode cached AniList covers into native terminal images on one background thread."""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Final

from PIL import Image, ImageOps

from anishift.cli.interactive.native_image import NativeImage, encode_sixel
from anishift.paths import cover_name, covers_dir

__all__ = ["COVER_ASPECT", "COVER_ROWS", "CoverImages", "cover_image"]

# ── Constants ─────────────────────────────────────────────────────────────────

COVER_ROWS: Final[int] = 12
"""Text rows of the cover slot, the same for every cover."""

COVER_ASPECT: Final[float] = 0.72
"""Width to height ratio of an AniList cover, 460 x 636 pixels."""

_CACHED: Final[int] = 64
"""Most encoded covers kept in memory."""

_STATIC_SECONDS: Final[float] = 1.0
"""Cycle of a cover, which has one frame."""

type _Key = tuple[int, tuple[int, int]]
"""One cover in one cell size."""


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
    """Keep encoded covers in memory and encode the newest requested one on the thread anishift-cover."""

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
        self._ready: OrderedDict[_Key, NativeImage | None] = OrderedDict()
        self._wanted: _Key | None = None
        self._wake: threading.Event = threading.Event()
        self._worker: threading.Thread | None = None

    def box(self) -> tuple[int, int] | None:
        """Return the columns and rows of the cover slot, or None in a terminal without SIXEL."""
        cell: tuple[int, int] | None = self._cell()
        return None if cell is None else cover_box(cell)

    def image(self, anilist_id: int) -> NativeImage | None:
        """Return the encoded cover, or None while it is encoded, unreadable or without SIXEL."""
        cell: tuple[int, int] | None = self._cell()
        if cell is None:
            return None
        key: _Key = (anilist_id, cell)
        with self._lock:
            if key in self._ready:
                self._ready.move_to_end(key)
                return self._ready[key]
            self._wanted = key
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="anishift-cover", daemon=True)
                self._worker.start()
        self._wake.set()
        return None

    def _run(self) -> None:
        while self._wake.wait():
            self._wake.clear()
            with self._lock:
                key: _Key | None = self._wanted
                self._wanted = None
            if key is None or key in self._ready:
                continue
            encoded: NativeImage | None = cover_image(self._directory() / cover_name(key[0]), key[1])
            with self._lock:
                self._ready[key] = encoded
                while len(self._ready) > _CACHED:
                    self._ready.popitem(last=False)
            self._invalidate()
