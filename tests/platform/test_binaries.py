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
    exe.write_bytes(b"binary")
    assert resolve_binary(Binary.FFMPEG) == exe


def test_resolve_falls_back_to_path_on_non_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: False)
    executable: Path = tmp_path / "ffmpeg-on-path"
    executable.write_bytes(b"binary")
    monkeypatch.setattr(shutil, "which", lambda _name: str(executable))
    assert resolve_binary(Binary.FFMPEG) == executable


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
    exe.write_bytes(b"binary")
    assert require_binary(Binary.MKVEXTRACT) == exe


def test_resolve_rejects_zero_byte_bundled_binary_without_deleting_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable: Path = tmp_path / "ffmpeg" / "ffmpeg.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: True)

    assert resolve_binary(Binary.FFMPEG) is None
    assert executable.is_file()
    assert executable.stat().st_size == 0


def test_resolve_skips_zero_byte_bundle_and_uses_valid_path_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundled: Path = tmp_path / "ffmpeg" / "ffmpeg"
    bundled.parent.mkdir()
    bundled.touch()
    executable: Path = tmp_path / "path-ffmpeg"
    executable.write_bytes(b"binary")
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: False)
    monkeypatch.setattr(shutil, "which", lambda _: str(executable))

    assert resolve_binary(Binary.FFMPEG) == executable
    assert bundled.stat().st_size == 0


def test_resolve_rejects_zero_byte_path_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable: Path = tmp_path / "path-ffmpeg"
    executable.touch()
    monkeypatch.setattr(binaries, "external_bin_root", lambda: tmp_path)
    monkeypatch.setattr(binaries, "is_windows", lambda: False)
    monkeypatch.setattr(shutil, "which", lambda _: str(executable))

    assert resolve_binary(Binary.FFMPEG) is None
    assert executable.is_file()
