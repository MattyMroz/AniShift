from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO

from prompt_toolkit import Application
from prompt_toolkit.application.current import create_app_session, set_app
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.utils import get_cwidth
from rich.text import Text

from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage
from anishift.cli.interactive.prompts import TerminalRenderer

CELL: tuple[int, int] = (10, 20)
SIZE: tuple[int, int] = (140, 40)

_CSI: re.Pattern[str] = re.compile(r"\x1b\[([?>=]?)([\d;]*)([ -/]*)([@-~])")
_RASTER: re.Pattern[str] = re.compile(r'"1;1;(\d+);(\d+)')

type Pixel = tuple[str, int, int] | None


def sixel(tag: object, columns: int, rows: int) -> str:
    return f'\x1bP9;1;0q"1;1;{columns * CELL[0]};{rows * CELL[1]}#{tag}\x1b\\'


def image(tag: object, columns: int, rows: int) -> NativeImage:
    return NativeImage((sixel(tag, columns, rows),), (1.0,), 1.0, columns, rows, rows, opaque=True)


class VtScreen:
    def __init__(self, columns: int, rows: int) -> None:
        self.columns: int = columns
        self.rows: int = rows
        self.text: list[list[str]] = [[" "] * columns for _ in range(rows)]
        self.pixels: list[list[Pixel]] = [[None] * columns for _ in range(rows)]
        self.cursor: tuple[int, int] = (0, 0)
        self.saved: tuple[int, int] = (0, 0)
        self.draws: int = 0

    def resize(self, columns: int, rows: int) -> None:
        self.text = [
            [self.text[row][column] if row < self.rows and column < self.columns else " " for column in range(columns)]
            for row in range(rows)
        ]
        self.pixels = [
            [
                self.pixels[row][column] if row < self.rows and column < self.columns else None
                for column in range(columns)
            ]
            for row in range(rows)
        ]
        self.columns, self.rows = columns, rows
        self.cursor = (min(self.cursor[0], rows - 1), min(self.cursor[1], columns - 1))

    def feed(self, data: str) -> None:
        index: int = 0
        while index < len(data):
            character: str = data[index]
            if character != "\x1b":
                self._control(character)
                index += 1
                continue
            index = self._escape(data, index)

    def _escape(self, data: str, index: int) -> int:
        kind: str = data[index + 1]
        if kind == "[":
            match: re.Match[str] | None = _CSI.match(data, index)
            assert match is not None
            if not match.group(1) and not match.group(3):
                self._csi(match.group(2), match.group(4))
            return match.end()
        if kind in "P]":
            end: int = (
                data.index("\x1b\\", index)
                if kind == "P"
                else min(
                    position for position in (data.find("\x07", index), data.find("\x1b\\", index)) if position >= 0
                )
            )
            if kind == "P":
                self._sixel(data[index : end + 2])
            return end + (1 if data[end] == "\x07" else 2)
        if kind in "()":
            return index + 3
        if kind == "7":
            self.saved = self.cursor
        if kind == "8":
            self.cursor = self.saved
        return index + 2

    def _control(self, character: str) -> None:
        row, column = self.cursor
        if character == "\r":
            self.cursor = (row, 0)
        elif character == "\n":
            self.cursor = (min(row + 1, self.rows - 1), column)
        elif character == "\b":
            self.cursor = (row, max(column - 1, 0))
        elif character.isprintable():
            self._print(character)

    def _print(self, character: str) -> None:
        row, column = self.cursor
        width: int = get_cwidth(character)
        if width == 0:
            return
        for offset in range(width):
            if column + offset < self.columns:
                self.text[row][column + offset] = character if not offset else ""
                self.pixels[row][column + offset] = None
        self.cursor = (row, min(column + width, self.columns - 1))

    def _csi(self, parameters: str, final: str) -> None:
        values: list[int] = [int(item) if item else 0 for item in parameters.split(";")] if parameters else []
        first: int = values[0] if values else 0
        row, column = self.cursor
        moves: dict[str, tuple[int, int]] = {"A": (-1, 0), "B": (1, 0), "C": (0, 1), "D": (0, -1)}
        if final in moves:
            step: int = max(first, 1)
            down, right = moves[final]
            self.cursor = (
                min(max(row + down * step, 0), self.rows - 1),
                min(max(column + right * step, 0), self.columns - 1),
            )
        elif final in "Hf":
            self.cursor = (
                min(max(first, 1), self.rows) - 1,
                min(max(values[1] if len(values) > 1 else 1, 1), self.columns) - 1,
            )
        elif final == "K":
            start: int = 0 if first == 2 else column
            end: int = column + 1 if first == 1 else self.columns
            self.text[row][start:end] = [" "] * (end - start)
        elif final == "J" and first == 2:
            self.text = [[" "] * self.columns for _ in range(self.rows)]
            self.pixels = [[None] * self.columns for _ in range(self.rows)]
        elif final == "J":
            self.text[row][column:] = [" "] * (self.columns - column)
            for below in range(row + 1, self.rows):
                self.text[below] = [" "] * self.columns

    def _sixel(self, payload: str) -> None:
        raster: re.Match[str] | None = _RASTER.search(payload)
        assert raster is not None
        columns: int = math.ceil(int(raster.group(1)) / CELL[0])
        rows: int = math.ceil(int(raster.group(2)) / CELL[1])
        top, left = self.cursor
        self.draws += 1
        for row in range(top, min(top + rows, self.rows)):
            for column in range(left, min(left + columns, self.columns)):
                self.pixels[row][column] = (payload, row - top, column - left)
        self.cursor = (min(top + rows, self.rows - 1), left)

    def line(self, row: int) -> str:
        return "".join(self.text[row])


@dataclass(frozen=True, slots=True)
class Shown:
    row: int
    column: int
    image: NativeImage
    payload: str


class Terminal:
    def __init__(
        self,
        frames: Callable[[int, int], Text],
        images: Callable[[], NativeImage | None],
        *,
        nudge: Callable[[NativeImage], int] = lambda _image: 0,
        elapsed: Callable[[], float] = lambda: 0.0,
    ) -> None:
        self.elapsed: Callable[[], float] = elapsed
        self.frames: Callable[[int, int], Text] = frames
        self.images: Callable[[], NativeImage | None] = images
        self.nudge: Callable[[NativeImage], int] = nudge
        self.size: Size = Size(rows=SIZE[1], columns=SIZE[0])
        self.stream: StringIO = StringIO()
        self.screen: VtScreen = VtScreen(*SIZE)
        self.frame: Text = Text()
        self.shown: Shown | None = None
        output: Vt100_Output = Vt100_Output(self.stream, lambda: self.size, term="xterm-256color")
        with create_app_session(input=DummyInput(), output=output):
            self.renderer: TerminalRenderer = TerminalRenderer(
                self._frame, lambda _key: None, image_provider=self._image, use_mascot=False
            )
        self.application: Application[None] = self.renderer._application

    def _frame(self, columns: int, rows: int) -> Text:
        self.shown = None
        self.frame = self.frames(columns, rows)
        return self.frame

    def _image(self) -> NativeImage | None:
        shown: NativeImage | None = self.images()
        anchor: tuple[int, int] | None = _anchor(self.frame.plain)
        self.shown = None
        if shown is not None and anchor is not None:
            payload: str = shown.payload_at(self.elapsed())
            self.shown = Shown(anchor[0], anchor[1] + self.nudge(shown), shown, payload)
        return shown

    def paint(self) -> None:
        with set_app(self.application):
            self.application.render_counter += 1
            self.renderer._before_render(self.application)
            self.application.renderer.render(self.application, self.application.layout)
            self._settle()
            self.renderer._after_render(self.application)
            self._settle()

    def resize(self, columns: int, rows: int) -> None:
        self.size = Size(rows=rows, columns=columns)
        self.screen.resize(columns, rows)
        self.application.renderer.erase(leave_alternate_screen=False)
        self.screen.feed(self._taken())
        self.paint()

    def _taken(self) -> str:
        data: str = self.stream.getvalue()
        self.stream.seek(0)
        self.stream.truncate(0)
        return data

    def _settle(self) -> None:
        data: str = self._taken()
        if not data:
            return
        self.screen.feed(data)
        problems: list[str] = self.problems()
        assert not problems, problems[:5]

    def problems(self) -> list[str]:
        found: list[str] = []
        shown: Shown | None = self.shown
        lines: list[str] = self.frame.plain.replace(NATIVE_IMAGE_ANCHOR, " ").split("\n")
        for row in range(self.screen.rows):
            expected: list[str] = _cells(lines[row] if row < len(lines) else "", self.screen.columns)
            beside: bool = shown is None or not shown.row <= row < shown.row + shown.image.cell_rows
            if beside and self.screen.text[row] == expected and not any(self.screen.pixels[row]):
                continue
            for column in range(self.screen.columns):
                pixel: Pixel = self.screen.pixels[row][column]
                inside: bool = shown is not None and _holds(shown, row, column)
                if shown is not None and inside and pixel != (shown.payload, row - shown.row, column - shown.column):
                    found.append(f"slot cell {row},{column} shows {pixel and pixel[1:]} of {_tag(pixel)}")
                if not inside and pixel is not None:
                    found.append(f"stale pixel {row},{column} of {_tag(pixel)}")
                if not inside and self.screen.text[row][column] != expected[column]:
                    found.append(f"text {row},{column} {self.screen.text[row][column]!r} != {expected[column]!r}")
        return found


def _tag(pixel: Pixel) -> str:
    return "" if pixel is None else pixel[0][pixel[0].index("#") :]


def _holds(shown: Shown, row: int, column: int) -> bool:
    return (
        shown.row <= row < shown.row + shown.image.cell_rows
        and shown.column <= column < shown.column + shown.image.cell_columns
    )


def _cells(line: str, columns: int) -> list[str]:
    cells: list[str] = []
    for character in line:
        width: int = get_cwidth(character)
        if width:
            cells.extend([character, *[""] * (width - 1)])
    return (cells + [" "] * columns)[:columns]


def _anchor(frame: str) -> tuple[int, int] | None:
    for row, line in enumerate(frame.split("\n")):
        if NATIVE_IMAGE_ANCHOR in line:
            return row, sum(get_cwidth(character) for character in line[: line.index(NATIVE_IMAGE_ANCHOR)])
    return None
