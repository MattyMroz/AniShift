from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from prompt_toolkit import Application
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from rich.text import Text

import anishift.cli.interactive.mascot_native as native_module
import anishift.cli.interactive.prompts as prompts_module
from anishift.cli.interactive.home import brand_for_geometry
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR, NativeMascotImage
from anishift.cli.interactive.prompts import HomeGeometry, TerminalRenderer, _native_anchor, resolve_home_geometry


def test_native_mascot_loads_one_valid_sixel_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)

    image: NativeMascotImage | None = native_module.load_native_mascot()

    assert image is not None
    assert len(image.payloads) == 46
    assert all(payload.startswith('\x1bP9;0;0q"1;1;128;128') for payload in image.payloads)
    assert all(payload.endswith("\x1b\\") for payload in image.payloads)
    assert image.frame_seconds == (0.06,) * 46
    assert image.cycle_seconds == pytest.approx(2.76)
    assert image.row_offset == 3
    assert image.column_offset == 3


def test_native_mascot_is_disabled_outside_supported_terminals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: False)

    assert native_module.load_native_mascot() is None


def test_native_brand_reserves_layout_and_exposes_one_anchor() -> None:
    geometry: HomeGeometry = resolve_home_geometry(120, 40)

    brand: Text = brand_for_geometry(geometry, native_mascot=True)
    position: tuple[int, int] | None = _native_anchor(brand.plain)

    assert brand.plain.count(NATIVE_MASCOT_ANCHOR) == 1
    assert position is not None
    assert len(brand.split("\n")) == geometry.mascot_rows


def test_terminal_renderer_captures_normal_mouse_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts_module, "load_native_mascot", lambda: None)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        renderer = TerminalRenderer(lambda _columns, _rows: Text(), lambda _key: None)

    assert renderer._application.mouse_support()


def test_native_mascot_is_redrawn_at_an_unchanged_position(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[str] = []
    output = SimpleNamespace(write_raw=writes.append, flush=lambda: None)
    application = cast("Application[None]", SimpleNamespace(output=output))
    renderer = object.__new__(TerminalRenderer)
    renderer._native_mascot = NativeMascotImage(
        payloads=("first", "second"),
        frame_seconds=(0.06, 0.06),
        cycle_seconds=0.12,
        row_offset=0,
        column_offset=0,
    )
    renderer._native_animation_started_at = 10.0
    renderer._native_position = (2, 3)
    renderer._native_drawn_position = (2, 3)
    monkeypatch.setattr("anishift.cli.interactive.prompts.time.monotonic", lambda: 10.07)

    renderer._draw_native_mascot(application)

    assert writes == ["\x1b7\x1b[3;4Hsecond\x1b8"]


def test_terminal_is_cleared_after_renderer_exits() -> None:
    writes: list[str] = []
    output = SimpleNamespace(write_raw=writes.append, flush=lambda: None)
    application = cast("Application[None]", SimpleNamespace(run=lambda: None, output=output))
    renderer = object.__new__(TerminalRenderer)
    renderer._application = application

    renderer.run()

    assert writes == ["\x1b[2J\x1b[3J\x1b[H"]


def test_native_mascot_is_erased_before_a_view_without_it() -> None:
    writes: list[str] = []
    output = SimpleNamespace(write_raw=writes.append, flush=lambda: None)
    application = cast("Application[None]", SimpleNamespace(output=output))
    renderer = object.__new__(TerminalRenderer)
    renderer._application = application
    renderer._native_drawn_position = (2, 3)

    renderer._erase_native_mascot()

    erase: str = "".join(f"\x1b[{row};4H\x1b[2K" for row in range(3, 11))
    assert writes == [f"\x1b7{erase}\x1b8"]
    assert renderer._native_drawn_position is None


def test_native_encoder_does_not_require_chafa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)

    assert native_module.load_native_mascot() is not None
