"""Render the packaged mascot as a native SIXEL image of one fixed pixel size."""

from __future__ import annotations

import math
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from importlib.resources import files
from typing import Final

from PIL import Image, ImageSequence

from anishift.utils.logger import get_logger

__all__ = ["MASCOT_FRAME_ROWS", "NATIVE_MASCOT_ANCHOR", "NativeMascotImage", "load_native_mascot", "native_mascot_cell"]

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

_DEFAULT_FRAME_SECONDS: Final[float] = 0.1
"""Fallback duration used when an animation frame omits timing metadata."""

MASCOT_FRAME_ROWS: Final[int] = 10
"""Approved frame height counted in text rows, so the mascot follows the font."""

MASCOT_REST_TOP_ROWS: Final[int] = 3
"""Blank rows above the resting GIF silhouette: 46/160 of ten rows plus the half-row pad."""

_ASSUMED_CELL: Final[tuple[int, int]] = (8, 17)
"""Cell size in pixels assumed when the terminal reports no metrics."""

_TOP_PAD_DIVISOR: Final[int] = 2
"""Cell height fraction padded above the mascot, dropping it below a whole row."""

_EDGE_MARGIN_PIXELS: Final[int] = 2
"""Pixels kept between the widest frame and the frame edge it is pushed against."""

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
class NativeMascotImage:
    """Hold cached animation frames and the terminal cells one frame covers."""

    payloads: tuple[str, ...]
    frame_seconds: tuple[float, ...]
    cycle_seconds: float
    cell_columns: int
    cell_rows: int
    layout_rows: int

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


def load_native_mascot(
    *,
    cell_size: tuple[int, int] | None = None,
    query_terminal: bool = True,
) -> NativeMascotImage | None:
    """Encode the packaged image once and report the cells it covers here."""
    if not _is_windows():
        return None
    reported: tuple[int, int] | None = terminal_cell_size() if query_terminal else cell_size
    cell: tuple[int, int] = reported or _ASSUMED_CELL
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
                payloads.append(_encode_sixel(_placed(resized, top_pad, right_shift), palette_source))
                frame_seconds.append(_frame_duration(frame))
            return NativeMascotImage(
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
    return 255 if value >= _ALPHA_THRESHOLD else 0


def native_mascot_cell() -> tuple[int, int] | None:
    """Probe SIXEL support and cell metrics before the input loop starts."""
    report: str = _query_terminal(_CELL_SIZE_QUERY)
    attributes: re.Match[str] | None = re.search(r"\x1b\[\?([\d;]+)c", report)
    if attributes is None or "4" not in attributes.group(1).split(";"):
        return None
    match: re.Match[str] | None = _CELL_SIZE_REPORT.search(report)
    if match is None:
        return _ASSUMED_CELL
    cell: tuple[int, int] = (int(match.group(2)), int(match.group(1)))
    return cell if min(cell) > 0 else _ASSUMED_CELL


def terminal_cell_size() -> tuple[int, int] | None:
    """Return the cell size in pixels the terminal reports about itself."""
    cell: tuple[int, int] | None = _reported_pair(_CELL_SIZE_QUERY, _CELL_SIZE_REPORT)
    if cell is not None and cell[0] > 0 and cell[1] > 0:
        return cell
    return _cell_size_from_text_area()


def _is_windows() -> bool:
    """Return whether the active process can target the Windows terminal."""
    return sys.platform == "win32"


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
