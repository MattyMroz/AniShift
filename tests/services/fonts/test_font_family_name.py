from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from font_test_helpers import build_font, write_collection, write_font

from anishift.services.fonts.index import family_name

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def test_family_name_is_the_windows_family_as_written(tmp_path: Path) -> None:
    path = write_font(
        tmp_path / "officina.ttf",
        "ITC Officina Sans Std PL Book",
        full="ITC Officina Sans Std PL Bold",
        typographic="ITC Officina Sans Std",
        mac_family="ITC Officina Sans Std",
    )

    assert family_name(path) == "ITC Officina Sans Std PL Book"


def test_family_name_of_a_collection_is_the_family_of_its_first_face(tmp_path: Path) -> None:
    path = write_collection(tmp_path / "pair.ttc", [build_font("First Face"), build_font("Second Face")])

    assert family_name(path) == "First Face"


def test_family_name_is_empty_without_a_windows_family_or_a_readable_file(tmp_path: Path) -> None:
    mac_only = write_font(tmp_path / "mac.ttf", "Ignored", mac_family="Mac Only", windows_family=False)
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font at all")

    assert family_name(mac_only) == ""
    assert family_name(broken) == ""
    assert family_name(tmp_path / "missing.ttf") == ""
