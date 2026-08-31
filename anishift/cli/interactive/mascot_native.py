"""Render the packaged mascot as a native 128×128 SIXEL image."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.resources import files
from typing import Final

from PIL import Image, ImageSequence

from anishift.utils.logger import get_logger

__all__ = ["NATIVE_MASCOT_ANCHOR", "NativeMascotImage", "load_native_mascot"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

NATIVE_MASCOT_ANCHOR: Final[str] = "\ue000"
"""Private-use marker replaced by the native image before terminal output."""

_ASSET_PACKAGE: Final[str] = "anishift.cli.interactive.assets"
"""Package containing runtime presentation assets."""

_ASSET_PARTS: Final[tuple[str, ...]] = ("mascot", "idle", "01.gif")
"""Package-relative path of the approved mascot animation."""

_SIXEL_COLORS: Final[int] = 255
"""Maximum opaque colors retained by the SIXEL palette."""

_ALPHA_THRESHOLD: Final[int] = 128
"""Alpha cutoff separating visible pixels from transparent pixels."""

_BAND_HEIGHT: Final[int] = 6
"""Pixel rows represented by one SIXEL character."""

_DATA_OFFSET: Final[int] = 63
"""ASCII offset applied to a six-bit SIXEL mask."""

_RLE_THRESHOLD: Final[int] = 4
"""Shortest repeated character sequence encoded with SIXEL RLE."""

_ROW_OFFSET: Final[int] = 3
"""Terminal rows centering the native image inside its reserved area."""

_COLUMN_OFFSET: Final[int] = 3
"""Terminal columns centering the native image inside its reserved area."""

_DEFAULT_FRAME_SECONDS: Final[float] = 0.1
"""Fallback duration used when an animation frame omits timing metadata."""

_FRAME_SIZE: Final[tuple[int, int]] = (128, 128)
"""Native screen-pixel size of every rendered animation frame."""


@dataclass(frozen=True, slots=True)
class NativeMascotImage:
    """Hold cached animation frames and their terminal placement."""

    payloads: tuple[str, ...]
    frame_seconds: tuple[float, ...]
    cycle_seconds: float
    row_offset: int
    column_offset: int

    def payload_at(self, elapsed_seconds: float) -> str:
        """Return the animation frame active at the given elapsed time."""
        position: float = elapsed_seconds % self.cycle_seconds
        for payload, duration in zip(self.payloads, self.frame_seconds, strict=True):
            if position < duration:
                return payload
            position -= duration
        return self.payloads[-1]


@dataclass(frozen=True, slots=True)
class _IndexedImage:
    """Hold indexed pixels and opacity for SIXEL encoding."""

    indices: bytes
    alpha: bytes
    width: int
    height: int


def load_native_mascot() -> NativeMascotImage | None:
    """Encode the packaged image on Windows without a text-cell fallback."""
    if not _is_windows():
        return None
    asset = files(_ASSET_PACKAGE).joinpath(*_ASSET_PARTS)
    try:
        with asset.open("rb") as stream, Image.open(stream) as source:
            palette_source: Image.Image = _palette_source(source)
            payloads: list[str] = []
            frame_seconds: list[float] = []
            for frame in ImageSequence.Iterator(source):
                resized: Image.Image = frame.convert("RGBA").resize(_FRAME_SIZE, Image.Resampling.NEAREST)
                payloads.append(_encode_sixel(resized, palette_source))
                frame_seconds.append(_frame_duration(frame))
            return NativeMascotImage(
                payloads=tuple(payloads),
                frame_seconds=tuple(frame_seconds),
                cycle_seconds=sum(frame_seconds),
                row_offset=_ROW_OFFSET,
                column_offset=_COLUMN_OFFSET,
            )
    except OSError, ValueError:
        logger.warning("Native mascot encoder failed")
        return None


def _is_windows() -> bool:
    """Return whether the active process can target the Windows terminal."""
    return os.name == "nt"


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


def _encode_sixel(image: Image.Image, palette_source: Image.Image | None = None) -> str:
    """Encode every source pixel with a square 1:1 SIXEL aspect ratio."""
    rgba: Image.Image = image.convert("RGBA")
    if palette_source is None:
        indexed: Image.Image = rgba.convert("RGB").quantize(
            colors=_SIXEL_COLORS,
            method=Image.Quantize.MEDIANCUT,
        )
    else:
        indexed = rgba.convert("RGB").quantize(palette=palette_source, dither=Image.Dither.NONE)
    palette: list[int] | None = indexed.getpalette()
    if palette is None:
        message: str = "SIXEL quantization did not produce a palette"
        raise ValueError(message)
    pixels = _IndexedImage(
        indices=indexed.tobytes(),
        alpha=rgba.getchannel("A").tobytes(),
        width=rgba.width,
        height=rgba.height,
    )
    colors: tuple[int, ...] = tuple(
        sorted(
            {color for color, opacity in zip(pixels.indices, pixels.alpha, strict=True) if opacity >= _ALPHA_THRESHOLD}
        )
    )
    output: list[str] = [f'\x1bP9;0;0q"1;1;{pixels.width};{pixels.height}']
    output.extend(_palette_register(color, palette) for color in colors)
    output.extend(_bands(pixels, colors))
    output.append("\x1b\\")
    return "".join(output)


def _palette_register(color: int, palette: list[int]) -> str:
    """Define one RGB palette register using percentage components."""
    offset: int = color * 3
    red: int = round(palette[offset] * 100 / 255)
    green: int = round(palette[offset + 1] * 100 / 255)
    blue: int = round(palette[offset + 2] * 100 / 255)
    return f"#{color};2;{red};{green};{blue}"


def _bands(image: _IndexedImage, colors: tuple[int, ...]) -> tuple[str, ...]:
    """Encode every six-row image band."""
    output: list[str] = []
    for top in range(0, image.height, _BAND_HEIGHT):
        rows: list[str] = []
        for color in _band_colors(image, top, colors):
            columns: str = _color_columns(image, top, color)
            rows.append(f"#{color}{_run_length_encode(columns)}")
        output.append("$".join(rows))
        if top + _BAND_HEIGHT < image.height:
            output.append("-")
    return tuple(output)


def _band_colors(
    image: _IndexedImage,
    top: int,
    colors: tuple[int, ...],
) -> tuple[int, ...]:
    """Return visible palette entries in one SIXEL band."""
    present: set[int] = set()
    bottom: int = min(top + _BAND_HEIGHT, image.height)
    for row in range(top, bottom):
        start: int = row * image.width
        for offset in range(start, start + image.width):
            if image.alpha[offset] >= _ALPHA_THRESHOLD:
                present.add(image.indices[offset])
    return tuple(color for color in colors if color in present)


def _color_columns(image: _IndexedImage, top: int, color: int) -> str:
    """Return trimmed SIXEL column characters for one color."""
    characters: list[str] = []
    for column in range(image.width):
        mask: int = 0
        for bit in range(_BAND_HEIGHT):
            row: int = top + bit
            if row >= image.height:
                break
            offset: int = row * image.width + column
            if image.alpha[offset] >= _ALPHA_THRESHOLD and image.indices[offset] == color:
                mask |= 1 << bit
        characters.append(chr(_DATA_OFFSET + mask))
    return "".join(characters).rstrip(chr(_DATA_OFFSET))


def _run_length_encode(value: str) -> str:
    """Compress repeated SIXEL characters without changing image pixels."""
    if not value:
        return value
    output: list[str] = []
    current: str = value[0]
    count: int = 1
    for character in value[1:]:
        if character == current:
            count += 1
            continue
        output.append(_encoded_run(current, count))
        current = character
        count = 1
    output.append(_encoded_run(current, count))
    return "".join(output)


def _encoded_run(character: str, count: int) -> str:
    """Encode one repeated character run."""
    if count >= _RLE_THRESHOLD:
        return f"!{count}{character}"
    return character * count
