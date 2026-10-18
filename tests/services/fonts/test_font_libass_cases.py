from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from anishift.services.fonts.index import FontIndex, polish_missing, system_font_paths

pytestmark = pytest.mark.integration

_QUALITY: Final[Path] = Path(__file__).resolve().parents[3] / "workspace" / ".quality"
_GRAND_BLUE: Final[Path] = _QUALITY / "corpus-pairs" / "grand-blue-s2-01" / "fonts"
_KAGUYA: Final[Path] = _QUALITY / "corpus-pairs" / "kaguya-s1-01" / "fonts"
_ICEBLADE: Final[Path] = (
    _QUALITY
    / "library"
    / "The.Iceblade.Sorcerer.Shall.Rule.the.World.S02E01.1080p.CR.WEB-DL.AAC2.0.H.264-VARYG"
    / "fonts"
)
_MPV_FONTS: Final[Path] = Path.home() / "Videos" / "mpv" / "portable_config" / "fonts"
_OFFICINA_FAMILY: Final[str] = "ITC Officina Sans Std PL Book"


def _index(folder: Path) -> FontIndex:
    if not folder.is_dir():
        pytest.skip(f"font folder {folder.name} is not available")
    system = system_font_paths()
    if not any(path.name.casefold() == "arialbi.ttf" for path in system):
        pytest.skip("system Arial is not available")
    return FontIndex.build(sorted(path for path in folder.iterdir() if path.is_file()), system)


@pytest.mark.parametrize(
    ("folder", "italic", "expected"),
    [
        (_GRAND_BLUE, False, ("arial-boldmt", True, False, False)),
        (_GRAND_BLUE, True, ("arial-boldmt", True, False, True)),
        (_KAGUYA, False, ("arial-boldmt", False, False, False)),
        (_KAGUYA, True, ("arial-bolditalicmt", False, False, False)),
    ],
)
def test_gandhi_sans_missing_polish_glyph_uses_arial_of_the_same_style(
    folder: Path, italic: bool, expected: tuple[str, bool, bool, bool]
) -> None:
    index = _index(folder)
    request = index.match("Gandhi Sans", weight=700, italic=italic)

    assert request is not None
    assert request.exact
    assert {"ż", "ź"} <= set(polish_missing(request.face))
    found = index.glyph_match(request, ord("ż"))

    postscript, in_episode, synthetic_bold, synthetic_italic = expected
    assert found.face.postscript_name == postscript
    assert (found.face.path.parent == folder, found.synthetic_bold, found.synthetic_italic) == (
        in_episode,
        synthetic_bold,
        synthetic_italic,
    )
    assert not found.exact


def test_comic_sans_missing_polish_glyph_uses_bold_variant_of_the_family() -> None:
    index = _index(_ICEBLADE)
    request = index.match("Comic Sans MS", weight=400, italic=False)

    assert request is not None
    assert request.face.postscript_name == "comicsansms"
    found = index.glyph_match(request, ord("ż"))

    assert found.face.postscript_name == "comicsansms-bold"
    assert (found.exact, found.synthetic_bold) == (True, False)


def test_arial_italic_request_with_episode_regular_and_bold_synthesizes_italic() -> None:
    index = _index(_ICEBLADE)

    match = index.match("Arial", weight=400, italic=True)

    assert match is not None
    assert (match.face.path.parent, match.face.weight, match.face.italic) == (_ICEBLADE, 400, False)
    assert match.synthetic_italic


@pytest.mark.parametrize(
    ("weight", "italic", "expected"),
    [
        (400, False, "officinasansstdpl-bold"),
        (700, False, "officinasansstdpl-bold"),
        (400, True, "officinasansstdpl-bolditalic"),
    ],
)
def test_officina_book_family_request_draws_with_bold_file(weight: int, italic: bool, expected: str) -> None:
    index = _index(_MPV_FONTS)

    match = index.match(_OFFICINA_FAMILY, weight=weight, italic=italic)

    assert match is not None
    assert (match.face.postscript_name, match.exact, match.synthetic_bold, match.synthetic_italic) == (
        expected,
        True,
        False,
        False,
    )
    assert polish_missing(match.face) == ""


def test_officina_book_request_draws_missing_glyph_with_regular_arial() -> None:
    index = _index(_MPV_FONTS)
    request = index.match(_OFFICINA_FAMILY, weight=400, italic=False)

    assert request is not None
    assert request.face.weight == 700
    found = index.glyph_match(request, ord("Ж"))

    assert (found.face.postscript_name, found.exact, found.synthetic_bold) == ("arialmt", False, False)


def test_officina_typographic_family_does_not_match() -> None:
    index = _index(_MPV_FONTS)

    match = index.match("ITC Officina Sans Std", weight=400, italic=False)

    assert match is not None
    assert _OFFICINA_FAMILY.casefold() not in match.face.family_names
    assert not match.exact


def test_officina_postscript_name_matches_bold_file() -> None:
    index = _index(_MPV_FONTS)

    match = index.match("OfficinaSansStdPL-Bold", weight=400, italic=False)

    assert match is not None
    assert (_OFFICINA_FAMILY.casefold() in match.face.family_names, match.face.italic, match.exact) == (
        True,
        False,
        True,
    )
