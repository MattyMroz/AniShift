from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from anishift.services.catalog.covers import cover_path, store_cover, stored_covers
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
