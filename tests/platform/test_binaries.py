from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from anishift.platform import binaries
from anishift.platform.binaries import (
    Binary,
    BinaryNotFoundError,
    require_binary,
    resolve_binary,
)


def test_resolve_prefers_bundled_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: False)
    tool_dir = tmp_path / "ffmpeg"
    tool_dir.mkdir()
    exe = tool_dir / "ffmpeg"
    exe.write_text("", encoding="utf-8")
    assert resolve_binary(Binary.FFMPEG) == exe


def test_resolve_falls_back_to_path_on_non_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: False)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    assert resolve_binary(Binary.FFMPEG) == Path("/usr/bin/ffmpeg")


def test_resolve_balcon_is_none_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binaries, "is_windows", lambda: False)
    assert resolve_binary(Binary.BALCON) is None


def test_resolve_missing_binary_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: True)
    assert resolve_binary(Binary.MKVMERGE) is None


def test_require_raises_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: True)
    with pytest.raises(BinaryNotFoundError, match="mkvmerge"):
        require_binary(Binary.MKVMERGE)


def test_require_returns_path_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: False)
    tool_dir = tmp_path / "mkvtoolnix"
    tool_dir.mkdir()
    exe = tool_dir / "mkvextract"
    exe.write_text("", encoding="utf-8")
    assert require_binary(Binary.MKVEXTRACT) == exe
