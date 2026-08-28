"""Terminal renderer for the AniShift slime asset."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Final, cast

from PIL import Image, ImageOps
from rich.style import Style
from rich.text import Text

__all__ = ["mascot_art"]

# ── Constants ─────────────────────────────────────────────────────────────────

_ASSET_PACKAGE: Final[str] = "anishift.cli.interactive.assets"
"""Package containing the source mascot image."""

_ASSET_NAME: Final[str] = "slime_transparent_4k.png"
"""Transparent source image rendered as terminal half blocks."""

_ALPHA_THRESHOLD: Final[int] = 32
"""Minimum alpha retained as visible terminal color."""

_REFERENCE_BACKGROUND: Final[tuple[int, int, int]] = (10, 10, 10)
"""OpenCode-compatible background used only to antialias translucent edge pixels."""


@lru_cache(maxsize=4)
def mascot_art(columns: int, rows: int) -> Text | None:
    """Render the packaged slime into a transparent true-color terminal grid."""
    if columns < 1 or rows < 1:
        return None

    try:
        asset = files(_ASSET_PACKAGE).joinpath(_ASSET_NAME)
        with asset.open("rb") as stream, Image.open(stream) as source:
            image: Image.Image = source.convert("RGBA")
            cropped: Image.Image = _crop_visible(image)
            pixels: Image.Image = _fit_pixels(cropped, columns, rows * 2)
    except OSError, ValueError:
        return None
    return _terminal_blocks(pixels, rows)


def _crop_visible(image: Image.Image) -> Image.Image:
    """Crop transparent margins while ignoring nearly invisible edge noise."""
    alpha: Image.Image = image.getchannel("A")
    visible: Image.Image = alpha.point(lambda value: 255 if value >= _ALPHA_THRESHOLD else 0)
    bounds: tuple[int, int, int, int] | None = visible.getbbox()
    return image if bounds is None else image.crop(bounds)


def _fit_pixels(image: Image.Image, columns: int, pixel_rows: int) -> Image.Image:
    """Fit the mascot into a fixed transparent pixel grid without distortion."""
    contained: Image.Image = ImageOps.contain(image, (columns, pixel_rows), Image.Resampling.LANCZOS)
    canvas: Image.Image = Image.new("RGBA", (columns, pixel_rows), (0, 0, 0, 0))
    offset: tuple[int, int] = ((columns - contained.width) // 2, (pixel_rows - contained.height) // 2)
    canvas.alpha_composite(contained, offset)
    return canvas


def _terminal_blocks(image: Image.Image, rows: int) -> Text:
    """Convert pairs of source pixels into styled upper-half block cells."""
    result = Text()
    for row in range(rows):
        for column in range(image.width):
            top: tuple[int, int, int, int] = _rgba(image, column, row * 2)
            bottom: tuple[int, int, int, int] = _rgba(image, column, row * 2 + 1)
            _append_cell(result, top, bottom)
        if row < rows - 1:
            result.append("\n")
    return result


def _rgba(image: Image.Image, column: int, row: int) -> tuple[int, int, int, int]:
    """Return one RGBA pixel with a precise static type."""
    return cast("tuple[int, int, int, int]", image.getpixel((column, row)))


def _append_cell(result: Text, top: tuple[int, int, int, int], bottom: tuple[int, int, int, int]) -> None:
    """Append one transparent, upper, lower or two-color terminal cell."""
    top_visible: bool = top[3] >= _ALPHA_THRESHOLD
    bottom_visible: bool = bottom[3] >= _ALPHA_THRESHOLD
    if not top_visible and not bottom_visible:
        result.append(" ")
        return
    if top_visible and bottom_visible:
        result.append("▀", style=Style(color=_color(top), bgcolor=_color(bottom)))
        return
    if top_visible:
        result.append("▀", style=Style(color=_color(top)))
        return
    result.append("▄", style=Style(color=_color(bottom)))


def _color(pixel: tuple[int, int, int, int]) -> str:
    """Blend one translucent source pixel against the reference dark background."""
    alpha: float = pixel[3] / 255
    red: int = round(pixel[0] * alpha + _REFERENCE_BACKGROUND[0] * (1 - alpha))
    green: int = round(pixel[1] * alpha + _REFERENCE_BACKGROUND[1] * (1 - alpha))
    blue: int = round(pixel[2] * alpha + _REFERENCE_BACKGROUND[2] * (1 - alpha))
    return f"#{red:02x}{green:02x}{blue:02x}"
