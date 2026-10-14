from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from anishift.application.acquisition_staging import (
    SetPublication,
    clean_staging,
    copy_staged,
    file_stamp,
    publication_path,
    publish_set,
    staging_path,
)
from anishift.application.control import FileStamp, PublishedFile

_OPERATION: str = "operation-1"


def _proven(root: Path, index: int, name: str, content: bytes) -> PublishedFile:
    source: Path = root / f"source-{index}"
    source.write_bytes(content)
    digest, stamp = copy_staged(source, publication_path(root, _OPERATION) / str(index), len(content))
    return PublishedFile(index, f"Pack/{name}", name, len(content), digest, stamp)


def test_a_copy_carries_the_digest_and_stamp_of_the_private_file(tmp_path: Path) -> None:
    source: Path = tmp_path / "source.mkv"
    source.write_bytes(b"video")
    copy: Path = publication_path(tmp_path, _OPERATION) / "0"

    digest, stamp = copy_staged(source, copy, 5)

    assert copy.read_bytes() == b"video"
    assert digest == hashlib.sha256(b"video").hexdigest()
    assert stamp == file_stamp(copy)


def test_a_source_whose_size_differs_from_the_declared_one_leaves_no_copy(tmp_path: Path) -> None:
    source: Path = tmp_path / "source.mkv"
    source.write_bytes(b"video")
    copy: Path = publication_path(tmp_path, _OPERATION) / "0"

    with pytest.raises(OSError, match="changed while it was copied"):
        copy_staged(source, copy, 6)

    assert not copy.exists()


def test_a_whole_set_is_linked_once_and_a_repeated_call_only_confirms_it(tmp_path: Path) -> None:
    files: tuple[PublishedFile, ...] = (_proven(tmp_path, 0, "a.mkv", b"v"), _proven(tmp_path, 1, "a.ass", b"s"))
    private: Path = publication_path(tmp_path, _OPERATION)

    first: SetPublication = publish_set(tmp_path, private, files)
    second: SetPublication = publish_set(tmp_path, private, files)

    assert first == SetPublication()
    assert second == SetPublication()
    assert (tmp_path / "a.mkv").read_bytes() == b"v"
    assert (tmp_path / "a.ass").read_bytes() == b"s"
    assert sorted(path.name for path in private.iterdir()) == ["0", "1"]


def test_an_occupied_name_publishes_nothing_of_the_set_and_keeps_the_occupant(tmp_path: Path) -> None:
    files: tuple[PublishedFile, ...] = (_proven(tmp_path, 0, "a.mkv", b"v"), _proven(tmp_path, 1, "a.ass", b"s"))
    (tmp_path / "a.ass").write_bytes(b"foreign")

    outcome: SetPublication = publish_set(tmp_path, publication_path(tmp_path, _OPERATION), files)

    assert outcome == SetPublication(occupied=(1,))
    assert not (tmp_path / "a.mkv").exists()
    assert (tmp_path / "a.ass").read_bytes() == b"foreign"


def test_a_lost_private_copy_publishes_nothing_and_is_reported(tmp_path: Path) -> None:
    files: tuple[PublishedFile, ...] = (_proven(tmp_path, 0, "a.mkv", b"v"), _proven(tmp_path, 1, "a.ass", b"s"))
    (publication_path(tmp_path, _OPERATION) / "1").unlink()

    outcome: SetPublication = publish_set(tmp_path, publication_path(tmp_path, _OPERATION), files)

    assert outcome == SetPublication(lost=(1,))
    assert not (tmp_path / "a.mkv").exists()


def test_a_published_file_changed_by_someone_else_is_not_claimed(tmp_path: Path) -> None:
    file: PublishedFile = _proven(tmp_path, 0, "a.mkv", b"v")
    stamp: FileStamp | None = file.stamp
    assert stamp is not None
    publish_set(tmp_path, publication_path(tmp_path, _OPERATION), (file,))
    (tmp_path / "a.mkv").write_bytes(b"other")

    outcome: SetPublication = publish_set(tmp_path, publication_path(tmp_path, _OPERATION), (file,))

    assert outcome == SetPublication(occupied=(0,))


def test_collision_rollback_recovers_after_unlink_before_the_next_names_are_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files: tuple[PublishedFile, ...] = (_proven(tmp_path, 0, "a.mkv", b"v"), _proven(tmp_path, 1, "a.ass", b"s"))
    private: Path = publication_path(tmp_path, _OPERATION)
    publish_set(tmp_path, private, files)
    (tmp_path / "a.ass").unlink()
    (tmp_path / "a.ass").write_bytes(b"foreign")
    unlink: Callable[..., None] = Path.unlink

    def interrupt(path: Path, *, missing_ok: bool = False) -> None:
        unlink(path, missing_ok=missing_ok)
        if path == tmp_path / "a.mkv":
            raise OSError("interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupt)
        with pytest.raises(OSError, match="interrupted"):
            publish_set(tmp_path, private, files)

    assert publish_set(tmp_path, private, files) == SetPublication(occupied=(1,))
    assert (private / "0").read_bytes() == b"v"
    assert (tmp_path / "a.ass").read_bytes() == b"foreign"
    assert not (tmp_path / "a.mkv").exists()


def test_recopy_replaces_a_private_hardlink_without_truncating_its_other_name(tmp_path: Path) -> None:
    source: Path = tmp_path / "source.mkv"
    source.write_bytes(b"new")
    target: Path = publication_path(tmp_path, _OPERATION) / "0"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    other: Path = tmp_path / "other.mkv"
    os.link(target, other)

    copy_staged(source, target, 3)

    assert other.read_bytes() == b"original"
    assert target.read_bytes() == b"new"


def test_cleanup_removes_only_listed_unkept_files_and_reports_what_remains(tmp_path: Path) -> None:
    data: Path = staging_path(tmp_path, _OPERATION)
    (data / "Pack").mkdir(parents=True)
    for name in ("Pack/03.mkv", "Pack/04.mkv.!qB", "Pack/05.mkv", "Pack/foreign.txt", ".hash.parts"):
        (data / name).write_bytes(b"x")
    private: Path = publication_path(tmp_path, _OPERATION)
    private.mkdir(parents=True)
    (private / "0").write_bytes(b"x")

    clean_staging(
        tmp_path,
        _OPERATION,
        "hash",
        ("Pack/03.mkv", "Pack/04.mkv", "Pack/05.mkv"),
        frozenset({"Pack/05.mkv"}),
        frozenset({0}),
    )

    assert sorted(path.name for path in (data / "Pack").iterdir()) == ["05.mkv", "foreign.txt"]
    assert not (data / ".hash.parts").exists()
    assert not private.exists()


def test_cleanup_of_a_fully_exported_staging_removes_its_operation_directory(tmp_path: Path) -> None:
    data: Path = staging_path(tmp_path, _OPERATION)
    (data / "Pack" / "Deep").mkdir(parents=True)
    (data / "Pack" / "Deep" / "03.mkv").write_bytes(b"x")

    clean_staging(tmp_path, _OPERATION, "hash", ("Pack/Deep/03.mkv",), frozenset(), frozenset())

    assert not data.parent.exists()
    assert (tmp_path / "temp" / ".acquisition").is_dir()


def test_cleanup_refuses_to_remove_a_directory_standing_at_a_listed_file_name(tmp_path: Path) -> None:
    data: Path = staging_path(tmp_path, _OPERATION)
    (data / "Pack" / "03.mkv").mkdir(parents=True)

    with pytest.raises(OSError, match="other than a regular file"):
        clean_staging(tmp_path, _OPERATION, "hash", ("Pack/03.mkv",), frozenset(), frozenset())

    assert (data / "Pack" / "03.mkv").is_dir()
