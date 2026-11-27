from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from anishift.services.catalog.covers import cover_path, prune_covers, store_cover, stored_covers
from anishift.services.catalog.errors import TitleCatalogError

pytestmark = pytest.mark.unit


def _png() -> bytes:
    buffer: BytesIO = BytesIO()
    Image.new("RGBA", (46, 64), (200, 40, 40, 128)).save(buffer, "PNG")
    return buffer.getvalue()


def test_store_writes_a_jpeg_atomically(tmp_path: Path) -> None:
    directory: Path = tmp_path / "covers"

    path: Path = store_cover(_png(), directory, 21)

    assert path == directory / "21.jpg"
    with Image.open(path) as stored:
        assert (stored.format, stored.mode, stored.size) == ("JPEG", "RGB", (46, 64))
    assert [item.name for item in directory.iterdir()] == ["21.jpg"]


def test_store_refuses_a_broken_image(tmp_path: Path) -> None:
    directory: Path = tmp_path / "covers"

    with pytest.raises(TitleCatalogError):
        store_cover(b"<html>not an image</html>", directory, 21)

    assert not directory.exists()


def test_store_names_the_file_only_after_the_id(tmp_path: Path) -> None:
    store_cover(_png(), tmp_path, 1535)
    for name in ("21.jpg.tmp", "notes.jpg", "0.jpg", "21.png", "021.jpg"):
        (tmp_path / name).write_bytes(b"x")

    assert cover_path(tmp_path, 1535) == tmp_path / "1535.jpg"
    assert stored_covers(tmp_path) == frozenset({1535})
    assert stored_covers(tmp_path / "missing") == frozenset()


def _files(directory: Path) -> list[str]:
    return sorted(item.relative_to(directory).as_posix() for item in directory.rglob("*") if item.is_file())


def test_prune_deletes_only_covers_outside_the_kept_entries(tmp_path: Path) -> None:
    for name in ("1.jpg", "2.jpg", "2.jpg.tmp", "1.jpg.tmp", "notes.txt", "021.jpg", "3.png"):
        (tmp_path / name).write_bytes(b"x")

    pruned: tuple[frozenset[int], int] = prune_covers(tmp_path, frozenset({1}))

    assert pruned == (frozenset({2}), 0)
    assert _files(tmp_path) == ["021.jpg", "1.jpg", "1.jpg.tmp", "3.png", "notes.txt"]


def test_prune_deletes_payloads_without_a_cover_or_of_another_encoding(tmp_path: Path) -> None:
    (tmp_path / "1.jpg").write_bytes(b"x")
    payloads: Path = tmp_path / "sixel"
    payloads.mkdir()
    for name in (
        "1-10x20-v1.six",
        "1-8x16-v1.six",
        "1-10x20-v0.six",
        "1-10x20-v1.six.42.tmp",
        "2-10x20-v1.six",
        "2-10x20-v1.six.42.tmp",
        "readme.txt",
    ):
        (payloads / name).write_bytes(b"x")

    pruned: tuple[frozenset[int], int] = prune_covers(tmp_path, frozenset({1}))

    assert pruned == (frozenset(), 0)
    assert _files(tmp_path) == [
        "1.jpg",
        "sixel/1-10x20-v1.six",
        "sixel/1-10x20-v1.six.42.tmp",
        "sixel/1-8x16-v1.six",
        "sixel/readme.txt",
    ]


def test_prune_reports_the_id_of_a_deleted_temporary_cover(tmp_path: Path) -> None:
    (tmp_path / "3.jpg.tmp").write_bytes(b"x")

    pruned: tuple[frozenset[int], int] = prune_covers(tmp_path, frozenset())

    assert pruned == (frozenset({3}), 0)
    assert _files(tmp_path) == []


def test_prune_counts_a_cover_it_cannot_delete_and_goes_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("2.jpg", "3.jpg"):
        (tmp_path / name).write_bytes(b"x")
    unlink: Callable[..., None] = Path.unlink

    def held(path: Path, *, missing_ok: bool = False) -> None:
        if path.name == "2.jpg":
            raise PermissionError(path.name)
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", held)

    pruned: tuple[frozenset[int], int] = prune_covers(tmp_path, frozenset())

    assert pruned == (frozenset({3}), 1)
    assert _files(tmp_path) == ["2.jpg"]
