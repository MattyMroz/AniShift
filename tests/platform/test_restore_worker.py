from __future__ import annotations

import ctypes
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from anishift.platform import restore_worker as worker
from anishift.platform.qbittorrent_process import ManagedQBittorrent
from anishift.platform.recycle import RecycleResult
from anishift.platform.recycle_worker import _identity


@pytest.mark.skipif(sys.platform != "win32", reason="Windows handle rename")
@pytest.mark.parametrize("occupied", [False, True])
def test_native_restore_publication_uses_exact_terminated_name_without_overwrite(
    tmp_path: Path, occupied: bool
) -> None:
    staging: Path = tmp_path / "staged-source"
    destination: Path = tmp_path / "01.txt"
    staging.write_bytes(b"synthetic source")
    identity: tuple[int, int, int, int] | None = _identity(staging)
    assert identity is not None
    if occupied:
        destination.write_bytes(b"foreign")
        with pytest.raises(FileExistsError):
            worker._publish_file(staging, destination, identity)
        assert destination.read_bytes() == b"foreign"
        assert _identity(staging) == identity
        assert set(tmp_path.iterdir()) == {staging, destination}
        return
    worker._publish_file(staging, destination, identity)
    assert list(tmp_path.iterdir()) == [destination]
    assert _identity(destination) == identity
    assert destination.read_bytes() == b"synthetic source"


def test_rename_handle_buffer_has_terminating_wchar_outside_length(tmp_path: Path) -> None:
    destination: Path = tmp_path / "01.txt"

    class Kernel:
        def SetFileInformationByHandle(self, handle: int, kind: int, pointer: Any, size: int) -> bool:  # noqa: N802
            del handle, kind
            request: Any = pointer._obj
            expected: bytes = str(destination).encode("utf-16-le")
            assert request.length == len(expected)
            assert bytes(request.name) == expected + b"\x00\x00"
            assert size >= type(request).name.offset + len(expected) + 2
            assert request.replace == 0
            return True

    worker._rename_handle(cast("ctypes.CDLL", Kernel()), 1, destination)


@pytest.mark.parametrize("place", ["bin", "staging", "destination", "external", "collision", "missing", "hardlink"])
def test_restore_reconciles_only_exact_recorded_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, place: str
) -> None:
    monkeypatch.setattr(worker, "_watch_parent", lambda pid: None)
    monkeypatch.setattr(worker, "_private_desktop", lambda: None)
    monkeypatch.setattr(worker, "_supported_path", lambda path: True)
    monkeypatch.setattr(worker, "_locked_source", lambda *args: nullcontext())
    monkeypatch.setattr(worker, "_held_parents", lambda *args: nullcontext())
    monkeypatch.setattr(worker, "_publish_file", lambda source, destination, identity: source.rename(destination))
    path: Path = tmp_path / "ready" / "01.txt"
    path.parent.mkdir()
    receipt: Path = tmp_path / "synthetic-receipt"
    receipt.write_bytes(b"synthetic")
    identity = _identity(receipt)
    assert identity is not None
    staging: Path = tmp_path / "temp/.restore-one/file"
    staging.parent.mkdir(parents=True)
    moves: list[Path] = []

    class Bin:
        def __init__(self, value: Path) -> None:
            assert value == receipt

        def close(self) -> None:
            pass

    def move(item: Any, old: Path, new: Path, expected: tuple[int, int, int, int]) -> bool:
        del item
        assert expected == identity
        moves.append(old)
        old.rename(new)
        return True

    monkeypatch.setattr(worker, "_BinItem", Bin)
    monkeypatch.setattr(worker, "_move", move)
    if place in {"staging", "destination", "external"}:
        receipt.rename(staging if place == "staging" else path)
    elif place == "hardlink":
        path.hardlink_to(receipt)
    elif place == "collision":
        path.write_bytes(b"foreign")
    elif place == "missing":
        receipt.rename(tmp_path / "unavailable-item")
    payload: dict[str, object] = {
        "parent_pid": os.getpid(),
        "workspace": str(tmp_path),
        "path": "ready/01.txt",
        "staging": "temp/.restore-one/file",
        "identity": list(identity),
        "receipt": str(receipt),
        "started": place in {"staging", "destination"},
        "check_only": True,
    }
    preflight: RecycleResult = worker.restore_request(payload)
    assert moves == []
    if place in {"collision", "missing", "hardlink"}:
        assert preflight.outcome == "refused"
        if place == "collision":
            assert path.read_bytes() == b"foreign"
        return
    assert preflight.outcome in {"ready", "restored"}
    result: RecycleResult = worker.restore_request({**payload, "check_only": False})
    assert result.outcome == "restored"
    assert _identity(path) == identity
    assert path.read_bytes() == b"synthetic"
    assert len(moves) == int(place == "bin")


def test_release_proof_reader_never_initializes_profile(tmp_path: Path) -> None:
    profile: Path = tmp_path / "absent"
    with httpx.Client() as client:
        manager: ManagedQBittorrent = ManagedQBittorrent(profile, http=client)
        assert manager.released_hashes(frozenset({"hash"})) == frozenset()
        assert not profile.exists()
        profile.mkdir()
        document: Path = profile / "process.json"
        document.write_text('{"released":["hash"]}', encoding="utf-8")
        before: bytes = document.read_bytes()
        assert manager.released_hashes(frozenset({"hash", "other"})) == frozenset({"hash"})
        assert document.read_bytes() == before
        assert list(profile.iterdir()) == [document]
