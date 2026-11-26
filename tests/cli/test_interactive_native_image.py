from __future__ import annotations

import time
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image
from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from rich.text import Text

from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage, encode_sixel
from anishift.cli.interactive.prompts import TerminalRenderer, _native_anchor

pytestmark = pytest.mark.unit

_CLEAR: str = "\x1b[2J"


def _image(payload: str, *, columns: int = 4, rows: int = 3) -> NativeImage:
    return NativeImage((payload,), (1.0,), 1.0, columns, rows, rows)


class _Screen:
    def __init__(self, frame: str, image: NativeImage | None) -> None:
        self.frame: str = frame
        self.image: NativeImage | None = image
        self.writes: list[str] = []
        self.size: SimpleNamespace = SimpleNamespace(columns=40, rows=12)
        self.screen: SimpleNamespace = SimpleNamespace(reset=lambda **_kwargs: None, _last_screen=object())
        self.renderer: TerminalRenderer = object.__new__(TerminalRenderer)
        output = SimpleNamespace(get_size=lambda: self.size, write_raw=self.writes.append, flush=lambda: None)
        self.renderer._application = cast(
            "Application[None]", SimpleNamespace(output=output, is_done=False, renderer=self.screen)
        )
        self.renderer._frame_provider = lambda _columns, _rows: Text(self.frame)
        self.renderer._image_provider = lambda: self.image
        self.renderer._native_mascot = None
        self.renderer._native_animation_started_at = time.monotonic()
        self.renderer._render_width = 0
        self.renderer._render_stream = None
        self.renderer._rich_console = None
        self.renderer._terminal_size = None
        self.renderer._native_position = None
        self.renderer._native_slot = None
        self.renderer._native_drawn_position = None
        self.renderer._native_drawn_payload = None
        self.renderer._native_drawn_image = None
        self.renderer._native_drawn_slot = None
        self.renderer._native_drawn_size = None
        self.renderer._idle_handler = None

    def paint(self) -> str:
        start: int = len(self.writes)
        self.renderer._before_render(self.renderer._application)
        self.renderer._after_render(self.renderer._application)
        return "".join(self.writes[start:])


_SLOT: str = f"Tytuł  {NATIVE_IMAGE_ANCHOR}\nAlpha\nBeta\nGamma"


def test_new_image_in_place_erases_cells_without_clearing_the_screen() -> None:
    screen: _Screen = _Screen(_SLOT, _image("FIRST"))
    first: str = screen.paint()
    screen.image = _image("SECOND")

    second: str = screen.paint()

    assert "FIRST" in first
    assert "SECOND" in second
    assert "\x1b[1;8H\x1b[m    " in second
    assert _CLEAR not in first + second


def test_missing_image_in_place_erases_cells_without_clearing_the_screen() -> None:
    screen: _Screen = _Screen(_SLOT, _image("FIRST"))
    screen.paint()
    screen.image = None

    erased: str = screen.paint()
    again: str = screen.paint()

    assert "\x1b[1;8H\x1b[m    " in erased
    assert _CLEAR not in erased
    assert again == ""


def test_changed_text_beside_the_slot_writes_no_image() -> None:
    screen: _Screen = _Screen(_SLOT, _image("COVER"))
    screen.paint()
    screen.frame = _SLOT.replace("Beta", "B")

    assert screen.paint() == ""


def test_text_inside_the_slot_cells_redraws_the_same_image() -> None:
    screen: _Screen = _Screen(_SLOT, _image("COVER"))
    screen.paint()
    screen.frame = _SLOT.replace("Beta", "Beta    x")

    redrawn: str = screen.paint()

    assert "COVER" in redrawn
    assert "\x1b[m    " not in redrawn
    assert _CLEAR not in redrawn


def test_blank_slot_cells_are_styled_so_a_shortened_line_never_erases_the_image() -> None:
    screen: _Screen = _Screen(_SLOT, _image("COVER"))
    screen.paint()

    prepared: object = screen.renderer._prepared_frame
    rows: list[str] = cast("ANSI", prepared).value.split("\n")

    assert all("\x1b[1m" in row for row in rows[:3])
    assert "\x1b[1m" not in rows[3]


def test_full_repaint_by_prompt_toolkit_redraws_the_same_image() -> None:
    screen: _Screen = _Screen(_SLOT, _image("COVER"))
    screen.paint()
    screen.screen._last_screen = None

    redrawn: str = screen.paint()

    assert "COVER" in redrawn
    assert _CLEAR not in redrawn


def test_unchanged_frame_writes_no_image() -> None:
    screen: _Screen = _Screen(_SLOT, _image("COVER"))
    screen.paint()

    assert screen.paint() == ""


def test_moved_slot_erases_only_the_old_cells_before_drawing_at_the_new_row() -> None:
    screen: _Screen = _Screen(_SLOT, _image("COVER"))
    screen.paint()
    screen.frame = f"\n{_SLOT}"

    moved: str = screen.paint()

    assert _CLEAR not in moved
    assert moved.index("\x1b[1;8H\x1b[m    ") < moved.index("\x1b[2;8HCOVER")
    assert screen.renderer._native_drawn_position == (1, 7)


def test_moved_slot_after_a_resize_clears_the_screen_once() -> None:
    screen: _Screen = _Screen(_SLOT, _image("COVER"))
    screen.paint()
    screen.size = SimpleNamespace(columns=30, rows=10)
    screen.frame = f"\n{_SLOT}"

    moved: str = screen.paint()

    assert moved.count(_CLEAR) == 1
    assert "COVER" in moved


def test_sixel_bands_skip_transparent_pixels_and_trim_empty_columns() -> None:
    image: Image.Image = Image.new("RGBA", (2, 7), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 6), (255, 0, 0, 255))
    palette: Image.Image = Image.new("P", (1, 1))
    palette.putpalette([255, 0, 0] * 256)

    assert encode_sixel(image, palette) == '\x1bP9;1;0q"1;1;2;7#0;2;100;0;0#0@-#0?@\x1b\\'


def test_sixel_runs_of_four_use_the_repeat_introducer() -> None:
    image: Image.Image = Image.new("RGBA", (5, 1), (0, 0, 255, 255))
    palette: Image.Image = Image.new("P", (1, 1))
    palette.putpalette([0, 0, 255] * 256)

    assert encode_sixel(image, palette).endswith("#0!5@\x1b\\")


def test_anchor_column_counts_wide_characters_as_two_cells() -> None:
    assert _native_anchor(f"x\n日本 {NATIVE_IMAGE_ANCHOR}") == (1, 5)


def test_mascot_frames_match_the_previous_output(monkeypatch: pytest.MonkeyPatch) -> None:
    screen: _Screen = _Screen("", None)
    screen.renderer._image_provider = None
    screen.renderer._native_mascot = NativeImage(("first", "second"), (0.06, 0.06), 0.12, 18, 10, 10)
    screen.renderer._native_animation_started_at = 10.0
    screen.renderer._native_position = (2, 3)
    screen.renderer._native_drawn_position = (2, 3)
    screen.renderer._native_drawn_payload = "first"
    monkeypatch.setattr("anishift.cli.interactive.prompts.time.monotonic", lambda: 10.07)

    screen.renderer._draw_native_image(screen.renderer._application)

    erase: str = "".join(f"\x1b[{row};4H\x1b[m{' ' * 18}" for row in range(3, 13))
    assert screen.writes == [f"\x1b7{erase}\x1b[3;4Hsecond\x1b8"]
