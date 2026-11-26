"""Render the packaged mascot as a native SIXEL image of one fixed pixel size."""

from __future__ import annotations

import math
import sys
from importlib.resources import files
from typing import Final

from PIL import Image, ImageSequence

from anishift.cli.interactive.native_image import (
    ALPHA_THRESHOLD,
    ASSUMED_CELL,
    NativeImage,
    encode_sixel,
    terminal_cell_size,
)
from anishift.utils.logger import get_logger

__all__ = ["MASCOT_FRAME_ROWS", "MASCOT_REST_TOP_ROWS", "load_native_mascot"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_ASSET_PACKAGE: Final[str] = "anishift.cli.interactive.assets"
"""Package containing runtime presentation assets."""

_ASSET_PARTS: Final[tuple[str, ...]] = ("mascot", "idle", "01.gif")
"""Package-relative path of the approved mascot animation."""

_DEFAULT_FRAME_SECONDS: Final[float] = 0.1
"""Fallback duration used when an animation frame omits timing metadata."""

MASCOT_FRAME_ROWS: Final[int] = 10
"""Approved frame height counted in text rows, so the mascot follows the font."""

MASCOT_REST_TOP_ROWS: Final[int] = 3
"""Blank rows above the resting GIF silhouette: 46/160 of ten rows plus the half-row pad."""

_TOP_PAD_DIVISOR: Final[int] = 2
"""Cell height fraction padded above the mascot, dropping it below a whole row."""

_EDGE_MARGIN_PIXELS: Final[int] = 2
"""Pixels kept between the widest frame and the frame edge it is pushed against."""


def load_native_mascot(
    *,
    cell_size: tuple[int, int] | None = None,
    query_terminal: bool = True,
) -> NativeImage | None:
    """Encode the packaged image once and report the cells it covers here."""
    if not _is_windows():
        return None
    reported: tuple[int, int] | None = terminal_cell_size() if query_terminal else cell_size
    cell: tuple[int, int] = reported or ASSUMED_CELL
    side: int = MASCOT_FRAME_ROWS * cell[1]
    top_pad: int = cell[1] // _TOP_PAD_DIVISOR
    columns: int = math.ceil(side / cell[0])
    painted_rows: int = math.ceil((side + top_pad) / cell[1])
    logger.info(
        "Native mascot sized",
        cell_reported=reported is not None,
        cell_width=cell[0],
        cell_height=cell[1],
        frame_side=side,
        top_pad=top_pad,
        cell_columns=columns,
        cell_rows=painted_rows,
        layout_rows=MASCOT_FRAME_ROWS,
    )
    asset = files(_ASSET_PACKAGE).joinpath(*_ASSET_PARTS)
    try:
        with asset.open("rb") as stream, Image.open(stream) as source:
            palette_source: Image.Image = _palette_source(source)
            right_shift: int = _shared_right_shift(source, side)
            payloads: list[str] = []
            frame_seconds: list[float] = []
            for frame in ImageSequence.Iterator(source):
                resized: Image.Image = frame.convert("RGBA").resize((side, side), Image.Resampling.NEAREST)
                payloads.append(encode_sixel(_placed(resized, top_pad, right_shift), palette_source))
                frame_seconds.append(_frame_duration(frame))
            return NativeImage(
                payloads=tuple(payloads),
                frame_seconds=tuple(frame_seconds),
                cycle_seconds=sum(frame_seconds),
                cell_columns=columns,
                cell_rows=painted_rows,
                layout_rows=MASCOT_FRAME_ROWS,
            )
    except OSError, ValueError:
        logger.warning("Native mascot encoder failed")
        return None


def _placed(frame: Image.Image, top_pad: int, right_shift: int) -> Image.Image:
    """Return the frame dropped by the pad and moved right by a shared shift."""
    canvas: Image.Image = Image.new("RGBA", (frame.width, frame.height + top_pad), (0, 0, 0, 0))
    canvas.paste(frame, (right_shift, top_pad))
    return canvas


def _shared_right_shift(source: Image.Image, side: int) -> int:
    """Return the shift every frame shares, bounded by the widest frame of all."""
    margins: list[int] = []
    for frame in ImageSequence.Iterator(source):
        opaque: Image.Image = frame.convert("RGBA").getchannel("A")
        box: tuple[int, int, int, int] | None = opaque.point(_opaque_mask).getbbox()
        if box is not None:
            margins.append(frame.width - box[2])
    if not margins:
        return 0
    return max(round((min(margins) - _EDGE_MARGIN_PIXELS) * side / source.width), 0)


def _opaque_mask(value: int) -> int:
    """Map one alpha value to a fully opaque or fully clear mask value."""
    return 255 if value >= ALPHA_THRESHOLD else 0


def _is_windows() -> bool:
    """Return whether the active process can target the Windows terminal."""
    return sys.platform == "win32"


def _palette_source(image: Image.Image) -> Image.Image:
    """Build one reusable palette from the GIF global color table."""
    palette: list[int] | None = image.getpalette()
    if palette is None:
        message: str = "Mascot animation does not contain a global palette"
        raise ValueError(message)
    palette_source: Image.Image = Image.new("P", (1, 1))
    palette_source.putpalette(palette)
    return palette_source


def _frame_duration(frame: Image.Image) -> float:
    """Return one positive GIF frame duration in seconds."""
    milliseconds: int = int(frame.info.get("duration", round(_DEFAULT_FRAME_SECONDS * 1000)))
    return max(milliseconds / 1000, _DEFAULT_FRAME_SECONDS / 10)
