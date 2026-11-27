"""Probe SIXEL support and cell metrics and encode one native terminal image of fixed cells."""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Final

from PIL import Image

__all__ = [
    "ALPHA_THRESHOLD",
    "ASSUMED_CELL",
    "NATIVE_IMAGE_ANCHOR",
    "NativeImage",
    "encode_sixel",
    "native_cell",
    "terminal_cell_size",
]

# ── Constants ─────────────────────────────────────────────────────────────────

NATIVE_IMAGE_ANCHOR: Final[str] = ""
"""Private-use marker replaced by the native image before terminal output."""

ALPHA_THRESHOLD: Final[int] = 128
"""Alpha cutoff separating visible pixels from transparent pixels."""

ASSUMED_CELL: Final[tuple[int, int]] = (8, 17)
"""Cell size in pixels assumed when the terminal reports no metrics."""

_SIXEL_COLORS: Final[int] = 255
"""Maximum opaque colors retained by the SIXEL palette."""

_BAND_HEIGHT: Final[int] = 6
"""Pixel rows represented by one SIXEL character."""

_DATA_OFFSET: Final[int] = 63
"""ASCII offset applied to a six-bit SIXEL mask."""

_RLE_THRESHOLD: Final[int] = 4
"""Shortest repeated character sequence encoded with SIXEL RLE."""

_RUN: Final[re.Pattern[str]] = re.compile(rf"(.)\1{{{_RLE_THRESHOLD - 1},}}")
"""Run of one SIXEL character long enough for RLE."""

_SIXEL_CHARACTERS: Final[bytes] = bytes((value + _DATA_OFFSET) % 256 for value in range(256))
"""Translation of a six-bit column mask to its SIXEL data character."""

_CELL_SIZE_QUERY: Final[str] = "\x1b[16t"
"""Request for the terminal cell size in pixels."""

_TEXT_AREA_QUERY: Final[str] = "\x1b[14t"
"""Request for the terminal text area size in pixels."""

_CELL_SIZE_REPORT: Final[re.Pattern[str]] = re.compile(r"\x1b\[6;(\d+);(\d+)t")
"""Terminal reply carrying the cell height and width in pixels."""

_TEXT_AREA_REPORT: Final[re.Pattern[str]] = re.compile(r"\x1b\[4;(\d+);(\d+)t")
"""Terminal reply carrying the text area height and width in pixels."""

_ATTRIBUTES_QUERY: Final[str] = "\x1b[c"
"""Universally answered request sent last to close every metric reply."""

_REPORT_TERMINATOR: Final[str] = "c"
"""Final character of the device attributes reply closing one read."""

_REPORT_TIMEOUT_SECONDS: Final[float] = 0.25
"""Upper bound for one terminal metric reply."""

_REPORT_POLL_SECONDS: Final[float] = 0.002
"""Interval between console reads while waiting for a terminal reply."""

_ENABLE_VIRTUAL_TERMINAL_PROCESSING: Final[int] = 0x0004
"""Console output flag interpreting VT sequences."""

_ENABLE_VIRTUAL_TERMINAL_INPUT: Final[int] = 0x0200
"""Console input flag delivering terminal replies as characters."""

_COOKED_INPUT_FLAGS: Final[int] = 0x0007
"""Console input flags for processed, line and echo handling."""


@dataclass(frozen=True, slots=True)
class NativeImage:
    """Hold encoded frames, their timing and the terminal cells one frame covers."""

    payloads: tuple[str, ...]
    frame_seconds: tuple[float, ...]
    cycle_seconds: float
    cell_columns: int
    cell_rows: int
    layout_rows: int
    opaque: bool = False

    def payload_at(self, elapsed_seconds: float) -> str:
        """Return the frame active at the given elapsed time."""
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


def native_cell() -> tuple[int, int] | None:
    """Probe SIXEL support and cell metrics before the input loop starts."""
    report: str = _query_terminal(_CELL_SIZE_QUERY)
    attributes: re.Match[str] | None = re.search(r"\x1b\[\?([\d;]+)c", report)
    if attributes is None or "4" not in attributes.group(1).split(";"):
        return None
    match: re.Match[str] | None = _CELL_SIZE_REPORT.search(report)
    if match is None:
        return ASSUMED_CELL
    cell: tuple[int, int] = (int(match.group(2)), int(match.group(1)))
    return cell if min(cell) > 0 else ASSUMED_CELL


def terminal_cell_size() -> tuple[int, int] | None:
    """Return the cell size in pixels the terminal reports about itself."""
    cell: tuple[int, int] | None = _reported_pair(_CELL_SIZE_QUERY, _CELL_SIZE_REPORT)
    if cell is not None and cell[0] > 0 and cell[1] > 0:
        return cell
    return _cell_size_from_text_area()


def _cell_size_from_text_area() -> tuple[int, int] | None:
    """Derive the cell size from the reported text area and its cell grid."""
    area: tuple[int, int] | None = _reported_pair(_TEXT_AREA_QUERY, _TEXT_AREA_REPORT)
    if area is None:
        return None
    grid: os.terminal_size = shutil.get_terminal_size(fallback=(0, 0))
    if grid.columns < 1 or grid.lines < 1:
        return None
    width: int = area[0] // grid.columns
    height: int = area[1] // grid.lines
    if width < 1 or height < 1:
        return None
    return width, height


def _reported_pair(query: str, report: re.Pattern[str]) -> tuple[int, int] | None:
    """Return the width and height carried by one terminal window report."""
    match: re.Match[str] | None = report.search(_query_terminal(query))
    if match is None:
        return None
    return int(match.group(2)), int(match.group(1))


def _query_terminal(query: str) -> str:
    """Send one window report request, closed by an always-answered request."""
    handles: tuple[int, int] | None = _console_handles()
    if handles is None:
        return ""
    return _query_console(handles, query)


def _console_handles() -> tuple[int, int] | None:
    """Return the console input and output handles of an interactive session."""
    if sys.platform != "win32":
        return None
    import msvcrt  # noqa: PLC0415

    stream_in = sys.stdin
    stream_out = sys.stdout
    if stream_in is None or stream_out is None or not stream_in.isatty() or not stream_out.isatty():
        return None
    try:
        return msvcrt.get_osfhandle(stream_in.fileno()), msvcrt.get_osfhandle(stream_out.fileno())
    except OSError, ValueError:
        return None


def _query_console(handles: tuple[int, int], query: str) -> str:
    """Write one report request in raw console mode and restore the previous mode."""
    if sys.platform != "win32":
        return ""
    import ctypes  # noqa: PLC0415

    input_handle, output_handle = handles
    kernel32: ctypes.CDLL = ctypes.WinDLL("kernel32", use_last_error=True)
    previous_input = ctypes.c_ulong()
    previous_output = ctypes.c_ulong()
    modes_read: bool = bool(kernel32.GetConsoleMode(input_handle, ctypes.byref(previous_input))) and bool(
        kernel32.GetConsoleMode(output_handle, ctypes.byref(previous_output))
    )
    if not modes_read:
        return ""
    kernel32.SetConsoleMode(output_handle, previous_output.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    kernel32.SetConsoleMode(
        input_handle,
        (previous_input.value & ~_COOKED_INPUT_FLAGS) | _ENABLE_VIRTUAL_TERMINAL_INPUT,
    )
    try:
        sys.stdout.write(f"{query}{_ATTRIBUTES_QUERY}")
        sys.stdout.flush()
        return _read_report()
    except OSError:
        return ""
    finally:
        kernel32.SetConsoleMode(input_handle, previous_input.value)
        kernel32.SetConsoleMode(output_handle, previous_output.value)


def _read_report() -> str:
    """Read replies until the device attributes terminator or a short timeout."""
    if sys.platform != "win32":
        return ""
    import msvcrt  # noqa: PLC0415

    deadline: float = time.monotonic() + _REPORT_TIMEOUT_SECONDS
    characters: list[str] = []
    while time.monotonic() < deadline:
        if not msvcrt.kbhit():
            time.sleep(_REPORT_POLL_SECONDS)
            continue
        character: str = msvcrt.getwch()
        characters.append(character)
        if character == _REPORT_TERMINATOR:
            break
    return "".join(characters)


def encode_sixel(image: Image.Image, palette_source: Image.Image | None = None) -> str:
    """Encode every source pixel with a square 1:1 SIXEL aspect ratio."""
    rgba: Image.Image = image.convert("RGBA")
    rgb: Image.Image = rgba.convert("RGB")
    if palette_source is None:
        palette_image: Image.Image = rgb.quantize(colors=_SIXEL_COLORS, method=Image.Quantize.MEDIANCUT)
        indexed: Image.Image = rgb.quantize(palette=palette_image, dither=Image.Dither.FLOYDSTEINBERG)
    else:
        indexed = rgb.quantize(palette=palette_source, dither=Image.Dither.NONE)
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
    bands: list[dict[int, bytearray]] = [_band_masks(pixels, top) for top in range(0, pixels.height, _BAND_HEIGHT)]
    colors: list[int] = sorted({color for band in bands for color in band})
    output: list[str] = [f'\x1bP9;1;0q"1;1;{pixels.width};{pixels.height}']
    output.extend(_palette_register(color, palette) for color in colors)
    output.append("-".join("$".join(_color_row(color, band[color]) for color in sorted(band)) for band in bands))
    output.append("\x1b\\")
    return "".join(output)


def _palette_register(color: int, palette: list[int]) -> str:
    """Define one RGB palette register using percentage components."""
    offset: int = color * 3
    red: int = round(palette[offset] * 100 / 255)
    green: int = round(palette[offset + 1] * 100 / 255)
    blue: int = round(palette[offset + 2] * 100 / 255)
    return f"#{color};2;{red};{green};{blue}"


def _band_masks(image: _IndexedImage, top: int) -> dict[int, bytearray]:
    """Return the six-bit column masks of every visible color in one band, reading each pixel once."""
    masks: dict[int, bytearray] = {}
    for bit in range(min(_BAND_HEIGHT, image.height - top)):
        start: int = (top + bit) * image.width
        value: int = 1 << bit
        row: zip[tuple[int, int]] = zip(
            image.indices[start : start + image.width], image.alpha[start : start + image.width], strict=True
        )
        for column, (color, opacity) in enumerate(row):
            if opacity < ALPHA_THRESHOLD:
                continue
            mask: bytearray | None = masks.get(color)
            if mask is None:
                mask = masks[color] = bytearray(image.width)
            mask[column] |= value
    return masks


def _color_row(color: int, mask: bytearray) -> str:
    """Encode one color of a band as trimmed, run-length compressed SIXEL characters."""
    characters: str = mask.translate(_SIXEL_CHARACTERS).decode("ascii").rstrip(chr(_DATA_OFFSET))
    return f"#{color}{_RUN.sub(lambda run: f'!{len(run[0])}{run[1]}', characters)}"
