"""Static, event-driven terminal mascot for the interactive command line."""

from __future__ import annotations

import threading
from collections.abc import Callable
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from typing import Final, cast

from PIL import Image, ImageOps
from rich.style import Style
from rich.text import Text

from anishift.application import TaskKind, TaskState

__all__ = ["MascotController", "MascotState", "mascot_art"]

# ── Constants ─────────────────────────────────────────────────────────────────

_ASSET_PACKAGE: Final[str] = "anishift.cli.interactive.assets"
"""Package containing runtime presentation assets."""

_ASSET_PARTS: Final[tuple[str, ...]] = ("mascot", "idle", "01.png")
"""Package-relative path of the optimized runtime mascot."""

_ALPHA_THRESHOLD: Final[int] = 32
"""Minimum alpha retained as visible terminal color."""

_REFERENCE_BACKGROUND: Final[tuple[int, int, int]] = (10, 10, 10)
"""Dark reference color used only to antialias translucent edge pixels."""

_ASCII_ROWS: Final[tuple[str, ...]] = ("  ╭╮  ", " (••) ", "  ╰╯  ")
"""Small renderer-independent fallback used when the PNG cannot be decoded."""


class MascotState(StrEnum):
    """Identify one presentation state derived from real application work."""

    IDLE = "idle"
    DISCOVER = "discover"
    EXTRACT = "extract"
    TRANSLATE = "translate"
    TTS = "tts"
    AUDIO = "audio"
    COMPOSE = "compose"
    SUCCESS = "success"
    ERROR = "error"


_TASK_STATE: Final[dict[TaskKind, MascotState]] = {
    TaskKind.EXTRACT_AUDIO: MascotState.EXTRACT,
    TaskKind.EXTRACT_SUBTITLES: MascotState.EXTRACT,
    TaskKind.EXTRACT_TRACKS: MascotState.EXTRACT,
    TaskKind.NORMALIZE_SUBTITLES: MascotState.EXTRACT,
    TaskKind.SPLIT_SUBTITLES: MascotState.EXTRACT,
    TaskKind.TRANSLATE_SUBTITLES: MascotState.TRANSLATE,
    TaskKind.SYNTHESIZE_SPEECH: MascotState.TTS,
    TaskKind.TRANSCODE_AUDIO: MascotState.AUDIO,
    TaskKind.MIX_NARRATION: MascotState.AUDIO,
    TaskKind.COMPOSE_MKV: MascotState.COMPOSE,
    TaskKind.COMPOSE_MP4: MascotState.COMPOSE,
    TaskKind.PUBLISH_ARTIFACT: MascotState.COMPOSE,
}
"""Exact projection from public task kinds to mascot states."""

_STATE_PRIORITY: Final[tuple[MascotState, ...]] = (
    MascotState.COMPOSE,
    MascotState.AUDIO,
    MascotState.TTS,
    MascotState.TRANSLATE,
    MascotState.EXTRACT,
)
"""Stable priority used while independent task kinds overlap."""

_STATE_MARKERS: Final[dict[MascotState, tuple[str, str]]] = {
    MascotState.IDLE: (" ", ""),
    MascotState.DISCOVER: ("◌", "purple_bold"),
    MascotState.EXTRACT: ("↓", "blue_bold"),
    MascotState.TRANSLATE: ("文", "purple_bold"),
    MascotState.TTS: ("♪", "magenta_bold"),
    MascotState.AUDIO: ("≋", "orange_bold"),
    MascotState.COMPOSE: ("◆", "yellow_bold"),
    MascotState.SUCCESS: ("✓", "success"),
    MascotState.ERROR: ("✗", "error"),
}
"""Static state decorations that retain the mascot's fixed geometry."""


class MascotController:
    """Own one thread-safe static mascot state without terminal I/O or workers."""

    def __init__(self, invalidate: Callable[[], None]) -> None:
        self._invalidate: Callable[[], None] = invalidate
        self._state: MascotState = MascotState.IDLE
        self._active_tasks: dict[str, MascotState] = {}
        self._failed: bool = False
        self._closed: bool = False
        self._lock: threading.Lock = threading.Lock()

    @property
    def state(self) -> MascotState:
        """Return the current immutable presentation state."""
        with self._lock:
            return self._state

    def show(self, state: MascotState) -> None:
        """Show an explicit lifecycle state and clear obsolete task activity."""
        with self._lock:
            if self._closed:
                return
            self._active_tasks.clear()
            self._failed = state is MascotState.ERROR
            changed: bool = self._replace_state(state)
        if changed:
            self._invalidate()

    def task_started(self, task_id: str, kind: TaskKind) -> None:
        """Add one active task and derive the highest-priority visible state."""
        with self._lock:
            if self._closed:
                return
            self._active_tasks[task_id] = _TASK_STATE[kind]
            changed: bool = self._replace_state(self._derived_state())
        if changed:
            self._invalidate()

    def task_finished(self, task_id: str, state: TaskState | None) -> None:
        """Remove one active task and retain a failure as the highest priority."""
        with self._lock:
            if self._closed:
                return
            self._active_tasks.pop(task_id, None)
            self._failed = self._failed or state is TaskState.FAILED
            changed: bool = self._replace_state(self._derived_state())
        if changed:
            self._invalidate()

    def run_finished(self, state: TaskState | None) -> None:
        """Freeze the mascot in the terminal result state."""
        if state is TaskState.SUCCEEDED:
            final_state: MascotState = MascotState.SUCCESS
        elif state is TaskState.CANCELLED:
            final_state = MascotState.IDLE
        else:
            final_state = MascotState.ERROR
        self.show(final_state)

    def reset(self) -> None:
        """Return to the idle Home state."""
        self.show(MascotState.IDLE)

    def close(self) -> None:
        """Dispose local state without creating or joining background workers."""
        with self._lock:
            self._active_tasks.clear()
            self._state = MascotState.IDLE
            self._failed = False
            self._closed = True

    def _derived_state(self) -> MascotState:
        if self._failed:
            return MascotState.ERROR
        active: set[MascotState] = set(self._active_tasks.values())
        return next((state for state in _STATE_PRIORITY if state in active), MascotState.IDLE)

    def _replace_state(self, state: MascotState) -> bool:
        if state is self._state:
            return False
        self._state = state
        return True


@lru_cache(maxsize=32)
def mascot_art(columns: int, rows: int, state: MascotState = MascotState.IDLE) -> Text | None:
    """Render the packaged slime or a small ASCII fallback at fixed geometry."""
    if columns < 1 or rows < 1:
        return None
    pixels: Image.Image | None = _mascot_pixels(columns, rows)
    if pixels is None:
        return _ascii_art(columns, rows, state)
    return _terminal_blocks(pixels, rows, state)


@lru_cache(maxsize=4)
def _mascot_pixels(columns: int, rows: int) -> Image.Image | None:
    try:
        asset = files(_ASSET_PACKAGE).joinpath(*_ASSET_PARTS)
        with asset.open("rb") as stream, Image.open(stream) as source:
            image: Image.Image = source.convert("RGBA")
            cropped: Image.Image = _crop_visible(image)
            return _fit_pixels(cropped, columns, rows * 2)
    except OSError, ValueError:
        return None


def _crop_visible(image: Image.Image) -> Image.Image:
    alpha: Image.Image = image.getchannel("A")
    visible: Image.Image = alpha.point(lambda value: 255 if value >= _ALPHA_THRESHOLD else 0)
    bounds: tuple[int, int, int, int] | None = visible.getbbox()
    return image if bounds is None else image.crop(bounds)


def _fit_pixels(image: Image.Image, columns: int, pixel_rows: int) -> Image.Image:
    contained: Image.Image = ImageOps.contain(image, (columns, pixel_rows), Image.Resampling.LANCZOS)
    canvas: Image.Image = Image.new("RGBA", (columns, pixel_rows), (0, 0, 0, 0))
    offset: tuple[int, int] = ((columns - contained.width) // 2, (pixel_rows - contained.height) // 2)
    canvas.alpha_composite(contained, offset)
    return canvas


def _terminal_blocks(image: Image.Image, rows: int, state: MascotState) -> Text:
    result = Text()
    for row in range(rows):
        for column in range(image.width):
            if row == 0 and column == 0 and state is not MascotState.IDLE:
                marker, style = _STATE_MARKERS[state]
                result.append(marker, style=style)
                continue
            top: tuple[int, int, int, int] = _rgba(image, column, row * 2)
            bottom: tuple[int, int, int, int] = _rgba(image, column, row * 2 + 1)
            _append_cell(result, top, bottom)
        if row < rows - 1:
            result.append("\n")
    return result


def _ascii_art(columns: int, rows: int, state: MascotState) -> Text | None:
    width: int = max(len(line) for line in _ASCII_ROWS)
    if columns < width or rows < len(_ASCII_ROWS):
        return None
    marker, style = _STATE_MARKERS[state]
    top: int = (rows - len(_ASCII_ROWS)) // 2
    left: int = (columns - width) // 2
    result = Text("\n" * top)
    for index, line in enumerate(_ASCII_ROWS):
        result.append(" " * left)
        if index == 0 and state is not MascotState.IDLE:
            result.append(marker, style=style)
            result.append(line[1:])
        else:
            result.append(line)
        if index < len(_ASCII_ROWS) - 1:
            result.append("\n")
    return result


def _rgba(image: Image.Image, column: int, row: int) -> tuple[int, int, int, int]:
    return cast("tuple[int, int, int, int]", image.getpixel((column, row)))


def _append_cell(result: Text, top: tuple[int, int, int, int], bottom: tuple[int, int, int, int]) -> None:
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
    alpha: float = pixel[3] / 255
    red: int = round(pixel[0] * alpha + _REFERENCE_BACKGROUND[0] * (1 - alpha))
    green: int = round(pixel[1] * alpha + _REFERENCE_BACKGROUND[1] * (1 - alpha))
    blue: int = round(pixel[2] * alpha + _REFERENCE_BACKGROUND[2] * (1 - alpha))
    return f"#{red:02x}{green:02x}{blue:02x}"
