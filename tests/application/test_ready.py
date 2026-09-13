from __future__ import annotations

import errno
from collections.abc import Callable
from pathlib import Path

import pytest

from anishift.application.artifacts import SourceGroup
from anishift.application.discovery import discover_groups
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.errors import ExecutionError


def _group(root: Path) -> SourceGroup:
    (root / "Episode.mkv").write_bytes(b"video bytes")
    (root / "Episode.pl.srt").write_text("Polish subtitles", encoding="utf-8")
    return discover_groups(root).groups[0]


def test_ready_preserves_file_identity_and_renames_the_whole_colliding_group(tmp_path: Path) -> None:
    group: SourceGroup = _group(tmp_path)
    identities: dict[str, int] = {path.name: path.stat().st_ino for path in tmp_path.iterdir()}
    ready: Path = tmp_path / "ready"
    ready.mkdir()
    (ready / "Episode.mkv").write_bytes(b"another episode")
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    move: ReadyMove | None = store.prepare(group, ())
    assert move is not None
    store.execute(move)
    assert (ready / "Episode.mkv").read_bytes() == b"another episode"
    assert (ready / "Episode [2].mkv").stat().st_ino == identities["Episode.mkv"]
    assert (ready / "Episode [2].pl.srt").stat().st_ino == identities["Episode.pl.srt"]
    assert not (tmp_path / "Episode.mkv").exists()
    assert store.pending() == (move,)
    store.acknowledge(move)
    assert store.pending() == ()
    moved: SourceGroup = next(
        item for item in discover_groups(tmp_path).groups if item.group_id == move.destination_group_id
    )
    assert store.prepare(moved, ()) is None


def test_ready_recovers_after_linking_before_removing_the_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    group: SourceGroup = _group(tmp_path)
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    move: ReadyMove | None = store.prepare(group, ())
    assert move is not None
    unlink: Callable[..., None] = Path.unlink

    def interrupted(path: Path, *, missing_ok: bool = False) -> None:
        if path == tmp_path / "Episode.mkv":
            raise OSError(errno.EIO, "Interrupted after linking")
        unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "unlink", interrupted)
        with pytest.raises(OSError, match="Interrupted after linking"):
            store.execute(move)
    assert (tmp_path / "Episode.mkv").samefile(tmp_path / "ready/Episode.mkv")
    restored: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    restored.execute(restored.pending()[0])
    assert not (tmp_path / "Episode.mkv").exists()
    assert (tmp_path / "ready/Episode.mkv").read_bytes() == b"video bytes"
    assert (tmp_path / "ready/Episode.pl.srt").read_text(encoding="utf-8") == "Polish subtitles"


def test_ready_rejects_a_destination_created_after_preparation_without_overwriting(tmp_path: Path) -> None:
    group: SourceGroup = _group(tmp_path)
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    move: ReadyMove | None = store.prepare(group, ())
    assert move is not None
    destination: Path = tmp_path / "ready/Episode.mkv"
    destination.write_bytes(b"someone else's file")
    with pytest.raises(ExecutionError, match="changed"):
        store.execute(move)
    assert destination.read_bytes() == b"someone else's file"
    assert (tmp_path / "Episode.mkv").read_bytes() == b"video bytes"
