from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from prompt_toolkit import Application
from rich.text import Text

import anishift.cli.interactive.mascot_native as native_module
from anishift.cli.interactive.home import brand_for_geometry
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR, NativeMascotImage
from anishift.cli.interactive.prompts import HomeGeometry, TerminalRenderer, _native_anchor, resolve_home_geometry


def test_native_mascot_loads_one_valid_sixel_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)

    image: NativeMascotImage | None = native_module.load_native_mascot()

    assert image is not None
    assert image.payload.startswith('\x1bP9;1;0q"1;1;128;128')
    assert image.payload.endswith("\x1b\\")
    assert image.row_offset == 0


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


def test_native_mascot_is_redrawn_at_an_unchanged_position() -> None:
    writes: list[str] = []
    output = SimpleNamespace(write_raw=writes.append, flush=lambda: None)
    application = cast("Application[None]", SimpleNamespace(output=output))
    renderer = object.__new__(TerminalRenderer)
    renderer._native_mascot = NativeMascotImage("payload", row_offset=0)
    renderer._native_position = (2, 3)
    renderer._native_drawn_position = (2, 3)

    renderer._draw_native_mascot(application)

    assert writes == ["\x1b7\x1b[3;4Hpayload\x1b8"]


def test_native_encoder_does_not_require_chafa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)

    assert native_module.load_native_mascot() is not None
