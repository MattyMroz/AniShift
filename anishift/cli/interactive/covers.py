"""Keep cached AniList covers as native terminal images, read from stored payloads or encoded on one thread."""

from __future__ import annotations

import contextlib
import math
import os
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Final

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from anishift.cli.interactive.native_image import NativeImage, encode_sixel
from anishift.paths import COVER_PAYLOADS, cover_name, cover_payload_name, covers_dir
from anishift.utils.logger import get_logger

__all__ = ["COVER_ASPECT", "COVER_ROWS", "CROP_TOLERANCE", "CoverImages", "cover_payload", "filled_cover"]

logger = get_logger(__name__)

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

_SIXEL_START: Final[str] = "\x1bP"
"""Device control string opening every SIXEL payload."""

_SIXEL_END: Final[str] = "\x1b\\"
"""String terminator closing every SIXEL payload."""


def cover_box(cell: tuple[int, int]) -> tuple[int, int]:
    """Return the columns and rows of the cover slot for one cell size."""
    return math.ceil(COVER_ROWS * cell[1] * COVER_ASPECT / cell[0]), COVER_ROWS


def cover_payload(path: Path, cell: tuple[int, int]) -> str | None:
    """Fill the slot with one cover and encode it as SIXEL, or return None for a bad file."""
    columns, rows = cover_box(cell)
    size: tuple[int, int] = (columns * cell[0], rows * cell[1])
    try:
        with Image.open(path) as source:
            return encode_sixel(filled_cover(source.convert("RGB"), size).convert("RGBA"))
    except OSError, ValueError, Image.DecompressionBombError:
        return None


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
    """Keep listed covers in memory, read from their stored payloads or encoded on the thread anishift-cover."""

    def __init__(
        self,
        cell: Callable[[], tuple[int, int] | None],
        directory: Callable[[], Path] = covers_dir,
        *,
        shown: Callable[[], bool] = lambda: True,
        changed: Callable[[], None] = lambda: None,
    ) -> None:
        self._cell: Callable[[], tuple[int, int] | None] = cell
        self._shown: Callable[[], bool] = shown
        self._directory: Callable[[], Path] = directory
        self._changed: Callable[[], None] = changed
        self._lock: threading.Lock = threading.Lock()
        self._ready: dict[int, NativeImage | None] = {}
        self._unread: dict[int, None] = {}
        self._unencoded: dict[int, None] = {}
        self._wanted: int | None = None
        self._worker: threading.Thread | None = None

    def box(self) -> tuple[int, int] | None:
        """Return the columns and rows of the cover slot, or None with covers off or without SIXEL."""
        cell: tuple[int, int] | None = self._cell()
        return None if cell is None or not self._shown() else cover_box(cell)

    def image(self, anilist_id: int) -> NativeImage | None:
        """Return the cover held in memory, else None and prepare it before any other, calling *changed* when ready."""
        if self._cell() is None:
            return None
        with self._lock:
            if anilist_id in self._ready:
                return self._ready[anilist_id]
            self._wanted = anilist_id
            self._start()
        return None

    def prepare(self, anilist_ids: Iterable[int]) -> None:
        """Queue covers for the thread anishift-cover, which reads every stored payload before it encodes any."""
        if self.box() is None:
            return
        with self._lock:
            for anilist_id in anilist_ids:
                if anilist_id not in self._ready and anilist_id not in self._unencoded:
                    self._unread[anilist_id] = None
            if self._unread:
                self._start()

    def _start(self) -> None:
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, name="anishift-cover", daemon=True)
            self._worker.start()

    def _run(self) -> None:
        while (step := self._next()) is not None:
            anilist_id, read, encode = step
            cell: tuple[int, int] | None = self._cell()
            if cell is None:
                self._stop()
                return
            payload: str | None = self._read(anilist_id, cell) if read else None
            if payload is None and not encode:
                with self._lock:
                    self._unencoded[anilist_id] = None
                continue
            if payload is None:
                payload = self._encode(anilist_id, cell)
            image: NativeImage | None = None if payload is None else _static(payload, cell)
            with self._lock:
                self._ready.setdefault(anilist_id, image)
                wanted: bool = anilist_id == self._wanted
            if wanted:
                self._changed()

    def _next(self) -> tuple[int, bool, bool] | None:
        with self._lock:
            wanted: int | None = self._wanted
            if wanted is not None and wanted not in self._ready:
                self._unread.pop(wanted, None)
                self._unencoded.pop(wanted, None)
                return wanted, True, True
            for queue, read in ((self._unread, True), (self._unencoded, False)):
                while queue:
                    anilist_id: int = next(iter(queue))
                    del queue[anilist_id]
                    if anilist_id not in self._ready:
                        return anilist_id, read, not read
            self._worker = None
            return None

    def _stop(self) -> None:
        with self._lock:
            self._unread.clear()
            self._unencoded.clear()
            self._worker = None

    def _stored(self, anilist_id: int, cell: tuple[int, int]) -> Path:
        return self._directory() / COVER_PAYLOADS / cover_payload_name(anilist_id, cell)

    def _read(self, anilist_id: int, cell: tuple[int, int]) -> str | None:
        stored: Path = self._stored(anilist_id, cell)
        try:
            if stored.stat().st_mtime_ns < (self._directory() / cover_name(anilist_id)).stat().st_mtime_ns:
                return None
            payload: str = stored.read_bytes().decode("ascii")
        except OSError, UnicodeDecodeError:
            return None
        return payload if payload.startswith(_SIXEL_START) and payload.endswith(_SIXEL_END) else None

    def _encode(self, anilist_id: int, cell: tuple[int, int]) -> str | None:
        payload: str | None = cover_payload(self._directory() / cover_name(anilist_id), cell)
        if payload is None:
            return None
        stored: Path = self._stored(anilist_id, cell)
        temporary: Path = stored.with_name(f"{stored.name}.{os.getpid()}.tmp")
        try:
            stored.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(payload.encode("ascii"))
            temporary.replace(stored)
        except OSError as problem:
            logger.warning("Cover payload not stored", error_class=type(problem).__name__)
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
        return payload


def _static(payload: str, cell: tuple[int, int]) -> NativeImage:
    columns, rows = cover_box(cell)
    return NativeImage((payload,), (_STATIC_SECONDS,), _STATIC_SECONDS, columns, rows, rows, opaque=True)
