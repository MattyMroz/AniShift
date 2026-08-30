from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from rich.text import Text

import anishift.cli.interactive.mascot_native as native_module
from anishift.cli.interactive.home import brand_for_geometry
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR, NativeMascotImage
from anishift.cli.interactive.prompts import HomeGeometry, _native_anchor, resolve_home_geometry


def test_native_mascot_loads_one_valid_sixel_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload: bytes = b'\r\n\r\n\r\n\x1bP0;1;0q"1;1;130;140data\x1b\\\r\n'

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert "--format=sixels" in arguments
        assert "--exact-size=on" in arguments
        assert kwargs["timeout"] == 3.0
        return subprocess.CompletedProcess(arguments, 0, stdout=payload, stderr=b"")

    monkeypatch.setenv("WT_SESSION", "test-session")
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setattr("anishift.cli.interactive.mascot_native.shutil.which", lambda _command: "chafa")
    monkeypatch.setattr("anishift.cli.interactive.mascot_native.subprocess.run", fake_run)

    image: NativeMascotImage | None = native_module.load_native_mascot()

    assert image == NativeMascotImage(payload='\x1bP0;1;0q"1;1;130;140data\x1b\\', row_offset=3)


def test_native_mascot_is_disabled_outside_supported_terminals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WT_SESSION", raising=False)
    monkeypatch.setenv("TERM_PROGRAM", "unknown")
    monkeypatch.setattr("anishift.cli.interactive.mascot_native.shutil.which", lambda _command: "chafa")

    assert native_module.load_native_mascot() is None


def test_native_brand_reserves_layout_and_exposes_one_anchor() -> None:
    geometry: HomeGeometry = resolve_home_geometry(120, 40)

    brand: Text = brand_for_geometry(geometry, native_mascot=True)
    position: tuple[int, int] | None = _native_anchor(brand.plain)

    assert brand.plain.count(NATIVE_MASCOT_ANCHOR) == 1
    assert position is not None
    assert len(brand.split("\n")) == geometry.mascot_rows


def test_native_encoder_receives_packaged_png_path(monkeypatch: pytest.MonkeyPatch) -> None:
    received_path: Path | None = None

    def fake_run(arguments: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal received_path
        received_path = Path(arguments[-1])
        return subprocess.CompletedProcess(arguments, 0, stdout=b"\x1bPpayload\x1b\\", stderr=b"")

    monkeypatch.setenv("WT_SESSION", "test-session")
    monkeypatch.setattr("anishift.cli.interactive.mascot_native.shutil.which", lambda _command: "chafa")
    monkeypatch.setattr("anishift.cli.interactive.mascot_native.subprocess.run", fake_run)

    image: NativeMascotImage | None = native_module.load_native_mascot()

    assert image is not None
    assert received_path is not None
    assert received_path.name == "01.png"
