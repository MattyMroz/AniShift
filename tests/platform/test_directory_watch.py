from __future__ import annotations

import queue
import stat
import struct
import sys
from pathlib import Path

import pytest

import anishift.platform.directory_watch as watch_module
from anishift.platform.directory_watch import DirectoryChange, DirectoryWatch, source_is_available


def _packet(name: str, following: int = 0) -> bytes:
    encoded: bytes = name.encode("utf-16-le")
    return struct.pack("<III", following, 1, len(encoded)) + encoded


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows power notification registration")
def test_power_callback_registers_and_forwards_resume_notifications() -> None:
    resumed: list[bool] = []
    notifications: watch_module._PowerNotifications = watch_module._PowerNotifications(lambda: resumed.append(True))
    try:
        assert notifications._handle.value
        assert notifications._callback(None, 4, None) == 0
        assert resumed == []
        assert notifications._callback(None, 18, None) == 0
        assert resumed == [True]
    finally:
        notifications.close()
    notifications.close()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows root replacement notifications")
def test_native_watcher_reopens_a_replaced_library_root(tmp_path: Path) -> None:
    root: Path = tmp_path / "library"
    root.mkdir()
    changes: queue.Queue[DirectoryChange] = queue.Queue()
    watch: DirectoryWatch = DirectoryWatch(root, changes.put)
    try:
        assert watch.mode == "native"
        root.rename(tmp_path / "old-library")
        root.mkdir()
        while changes.get(timeout=5.0).reason != "reconnected":
            pass
        source: Path = root / "new.mkv"
        source.write_bytes(b"complete")
        while source not in changes.get(timeout=5.0).paths:
            pass
        assert watch.mode == "native"
    finally:
        watch.close()


@pytest.mark.parametrize("payload", [b"", b"short", _packet("a", 4), _packet("../a")])
def test_lost_or_invalid_notifications_request_reconciliation(tmp_path: Path, payload: bytes) -> None:
    change: DirectoryChange = watch_module._decode_changes(tmp_path, payload)

    assert change.reconcile
    assert not change.paths


def test_notifications_keep_unicode_paths_and_deduplicate_changes(tmp_path: Path) -> None:
    packet: bytes = _packet("odcinek.mkv")
    length: int = (len(packet) + 3) & ~3
    combined: bytes = _packet("odcinek.mkv", length).ljust(length, b"\x00") + packet

    assert watch_module._decode_changes(tmp_path, combined).paths == (tmp_path / "odcinek.mkv",)
    assert watch_module._decode_changes(tmp_path, _packet("żółć.mkv")).paths == (tmp_path / "żółć.mkv",)


def test_unsupported_notifications_report_the_polling_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unsupported() -> object:
        raise OSError("unsupported filesystem")

    monkeypatch.setattr(watch_module, "_kernel32", unsupported)
    changes: queue.Queue[DirectoryChange] = queue.Queue()
    watch: DirectoryWatch = DirectoryWatch(tmp_path, changes.put)
    try:
        assert watch.mode == "polling"
        assert changes.get(timeout=2.0) == DirectoryChange(reconcile=True, reason="polling_fallback")
    finally:
        watch.close()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing and read-only attributes")
def test_read_only_sources_are_ready_but_sources_with_open_writers_are_not(tmp_path: Path) -> None:
    source: Path = tmp_path / "episode.mkv"
    source.write_bytes(b"complete")
    source.chmod(stat.S_IREAD)
    try:
        assert source_is_available(source)
    finally:
        source.chmod(stat.S_IREAD | stat.S_IWRITE)
    with source.open("r+b"):
        assert not source_is_available(source)
    assert source_is_available(source)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows native directory notifications")
def test_native_notifications_follow_files_rename_subdirectories_and_stop_while_idle(tmp_path: Path) -> None:
    changes: queue.Queue[DirectoryChange] = queue.Queue()
    watch: DirectoryWatch = DirectoryWatch(tmp_path, changes.put)
    try:
        assert watch.mode == "native"
        with pytest.raises(queue.Empty):
            changes.get(timeout=0.1)
        episode: Path = tmp_path / "żółć.mkv"
        episode.write_bytes(b"one")
        assert episode in changes.get(timeout=2.0).paths
        renamed: Path = tmp_path / "another.mkv"
        episode.rename(renamed)
        observed: set[Path] = set()
        while renamed not in observed:
            observed.update(changes.get(timeout=2.0).paths)
        directory: Path = tmp_path / "Series"
        directory.mkdir()
        nested: Path = directory / "episode.mkv"
        nested.write_bytes(b"nested")
        observed.clear()
        while nested not in observed:
            observed.update(changes.get(timeout=2.0).paths)
        nested.unlink()
        observed.clear()
        while nested not in observed:
            observed.update(changes.get(timeout=2.0).paths)
    finally:
        watch.close()
    watch.close()
