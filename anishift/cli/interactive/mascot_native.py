"""Render the packaged mascot as a native 128×128 SIXEL image."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.resources import files
from typing import Final

from PIL import Image

from anishift.utils.logger import get_logger

__all__ = ["NATIVE_MASCOT_ANCHOR", "NativeMascotImage", "load_native_mascot"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

NATIVE_MASCOT_ANCHOR: Final[str] = "\ue000"
"""Private-use marker replaced by the native image before terminal output."""

_ASSET_PACKAGE: Final[str] = "anishift.cli.interactive.assets"
"""Package containing runtime presentation assets."""

_ASSET_PARTS: Final[tuple[str, ...]] = ("mascot", "idle", "01.png")
"""Package-relative path of the approved mascot still."""

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


@dataclass(frozen=True, slots=True)
class NativeMascotImage:
    """Hold one cached terminal image and its vertical layout offset."""

    payload: str
    row_offset: int


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
            image: Image.Image = source.convert("RGBA")
            return NativeMascotImage(payload=_encode_sixel(image), row_offset=0)
    except OSError, ValueError:
        logger.warning("Native mascot encoder failed")
        return None


def _is_windows() -> bool:
    """Return whether the active process can target the Windows terminal."""
    return os.name == "nt"


def _encode_sixel(image: Image.Image) -> str:
    """Encode every source pixel with a square 1:1 SIXEL aspect ratio."""
    rgba: Image.Image = image.convert("RGBA")
    indexed: Image.Image = rgba.convert("RGB").quantize(
        colors=_SIXEL_COLORS,
        method=Image.Quantize.MEDIANCUT,
    )
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
    output: list[str] = [f'\x1bP9;1;0q"1;1;{pixels.width};{pixels.height}']
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
