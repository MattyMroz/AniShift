from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from font_test_helpers import build_font, write_collection, write_font

from anishift.services.fonts import index as font_index
from anishift.services.fonts.index import FontIndex, polish_missing, read_faces, system_font_paths

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def _arial(folder: Path) -> list[Path]:
    folder.mkdir(exist_ok=True)
    return [
        write_font(folder / "arial.ttf", "Arial", chars="Hab żą"),
        write_font(folder / "arialbd.ttf", "Arial", weight=700, bold_flag=True, chars="Hab żą"),
        write_font(folder / "ariali.ttf", "Arial", italic=True, chars="Hab żą"),
        write_font(folder / "arialbi.ttf", "Arial", weight=700, italic=True, bold_flag=True, chars="Hab żą"),
    ]


def test_read_faces_windows_family_and_full_names_are_casefolded_keys(tmp_path: Path) -> None:
    path = write_font(
        tmp_path / "officina.ttf",
        "Officina Sans PL Book",
        weight=700,
        full="OfficinaSansPL-Bold",
        postscript="OfficinaSansPL-Bold",
        typographic="Officina Sans",
        mac_family="Officina Sans",
    )

    (face,) = read_faces(path)

    assert face.family_names == frozenset({"officina sans pl book"})
    assert face.full_names == frozenset({"officinasanspl-bold"})
    assert (face.path, face.face_index, face.weight, face.italic) == (path, 0, 700, False)


def test_read_faces_without_windows_family_uses_other_platform_family(tmp_path: Path) -> None:
    path = write_font(tmp_path / "mac.ttf", "Unused", windows_family=False, mac_family="Mac Only")

    (face,) = read_faces(path)

    assert face.family_names == frozenset({"mac only"})


@pytest.mark.parametrize(
    ("weight_class", "bold_flag", "expected"),
    [(0, True, 700), (0, False, 400), (4, False, 350), (7, False, 700), (650, False, 650)],
)
def test_read_faces_weight_follows_libass_table(
    tmp_path: Path, weight_class: int, bold_flag: bool, expected: int
) -> None:
    path = write_font(tmp_path / "font.ttf", "Weighted", weight=weight_class, bold_flag=bold_flag)

    assert read_faces(path)[0].weight == expected


@pytest.mark.parametrize(
    ("win", "hhea", "typo", "expected"),
    [
        ((900, 300), (800, 200), (700, 100), (900, 300)),
        ((0, 0), (800, 200), (700, 100), (800, 200)),
        ((0, 0), (0, 0), (700, 100), (700, 100)),
        ((0, 0), (0, 0), (0, 0), (700, 0)),
    ],
)
def test_read_faces_vertical_metrics_fall_back_like_libass(
    tmp_path: Path,
    win: tuple[int, int],
    hhea: tuple[int, int],
    typo: tuple[int, int],
    expected: tuple[int, int],
) -> None:
    path = write_font(tmp_path / "font.ttf", "Metrics", win=win, hhea=hhea, typo=typo)

    face = read_faces(path)[0]

    assert (face.ascent, face.descent, face.units_per_em) == (*expected, 1000)


def test_read_faces_collection_keeps_face_indexes(tmp_path: Path) -> None:
    path = write_collection(tmp_path / "pair.ttc", [build_font("First"), build_font("Second", italic=True)])

    faces = read_faces(path)

    assert [(face.face_index, sorted(face.family_names), face.italic) for face in faces] == [
        (0, ["first"], False),
        (1, ["second"], True),
    ]


def test_read_faces_unreadable_or_missing_file_gives_no_faces(tmp_path: Path) -> None:
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font at all")

    assert read_faces(broken) == ()
    assert read_faces(tmp_path / "missing.ttf") == ()


def test_polish_missing_lists_letters_absent_from_cmap(tmp_path: Path) -> None:
    face = read_faces(write_font(tmp_path / "font.ttf", "Partial", chars="abłóŁÓ"))[0]

    assert polish_missing(face) == "ąćęńśźżĄĆĘŃŚŹŻ"


def test_match_full_or_postscript_name_selects_that_face(tmp_path: Path) -> None:
    files = [
        write_font(tmp_path / "regular.ttf", "Family", full="Family Regular", postscript="Family-Regular"),
        write_font(tmp_path / "bold.ttf", "Family", weight=700, full="Family Bold", postscript="Family-Bold"),
    ]
    index = FontIndex.build(files, ())

    by_full = index.match("FAMILY BOLD", weight=400, italic=False)
    by_postscript = index.match("family-bold", weight=400, italic=False)

    assert by_full is not None
    assert by_postscript is not None
    assert by_full.face.path == by_postscript.face.path == files[1]
    assert by_full.exact


def test_match_typographic_family_is_not_a_key(tmp_path: Path) -> None:
    files = [write_font(tmp_path / "pl.ttf", "Sans PL Book", weight=700, typographic="Sans", mac_family="Sans")]
    index = FontIndex.build(files, ())

    assert index.match("Sans", weight=400, italic=False) is None
    assert index.match("sans pl book", weight=400, italic=False) is not None


@pytest.mark.parametrize(
    ("weight", "italic", "expected"),
    [
        (400, False, ("regular.ttf", False, False)),
        (700, False, ("bold.ttf", False, False)),
        (400, True, ("italic.ttf", False, False)),
        (700, True, ("bold.ttf", False, True)),
    ],
)
def test_match_family_picks_variant_by_libass_score(
    tmp_path: Path, weight: int, italic: bool, expected: tuple[str, bool, bool]
) -> None:
    files = [
        write_font(tmp_path / "regular.ttf", "Family"),
        write_font(tmp_path / "bold.ttf", "Family", weight=700, bold_flag=True),
        write_font(tmp_path / "italic.ttf", "Family", italic=True),
    ]
    index = FontIndex.build(files, ())

    match = index.match("Family", weight=weight, italic=italic)

    assert match is not None
    assert (match.face.path.name, match.synthetic_bold, match.synthetic_italic) == expected


def test_match_bold_request_prefers_emboldened_regular_over_black(tmp_path: Path) -> None:
    files = [
        write_font(tmp_path / "regular.ttf", "Family"),
        write_font(tmp_path / "black.ttf", "Family", weight=900, bold_flag=True),
    ]
    index = FontIndex.build(files, ())

    match = index.match("Family", weight=700, italic=False)

    assert match is not None
    assert (match.face.path.name, match.synthetic_bold) == ("regular.ttf", True)


def test_match_family_in_episode_ignores_system_variants(tmp_path: Path) -> None:
    episode = [write_font(tmp_path / "episode.ttf", "Arial")]
    index = FontIndex.build(episode, _arial(tmp_path / "system"))

    match = index.match("Arial", weight=400, italic=True)

    assert match is not None
    assert (match.face.path, match.exact, match.synthetic_italic) == (episode[0], True, True)


def test_match_family_missing_from_episode_comes_from_system(tmp_path: Path) -> None:
    episode = [write_font(tmp_path / "other.ttf", "Other")]
    index = FontIndex.build(episode, _arial(tmp_path / "system"))

    match = index.match("arial", weight=700, italic=True)

    assert match is not None
    assert (match.face.path.name, match.exact, match.synthetic_bold, match.synthetic_italic) == (
        "arialbi.ttf",
        True,
        False,
        False,
    )


def test_match_unknown_family_falls_back_to_arial_or_none(tmp_path: Path) -> None:
    with_arial = FontIndex.build((), _arial(tmp_path / "system"))
    without_arial = FontIndex.build((), ())

    fallback = with_arial.match("No Such Font", weight=700, italic=False)

    assert fallback is not None
    assert (fallback.face.path.name, fallback.exact) == ("arialbd.ttf", False)
    assert without_arial.match("No Such Font", weight=700, italic=False) is None


def test_glyph_match_keeps_request_with_the_glyph(tmp_path: Path) -> None:
    index = FontIndex.build([write_font(tmp_path / "font.ttf", "Family")], ())
    request = index.match("Family", weight=400, italic=False)

    assert request is not None
    assert index.glyph_match(request, ord("H")) is request


def test_glyph_match_prefers_family_variant_with_the_glyph(tmp_path: Path) -> None:
    files = [
        write_font(tmp_path / "regular.ttf", "Family", chars="Hab"),
        write_font(tmp_path / "bold.ttf", "Family", weight=700, chars="Habż"),
    ]
    index = FontIndex.build(files, _arial(tmp_path / "system"))
    request = index.match("Family", weight=400, italic=False)

    assert request is not None
    found = index.glyph_match(request, ord("ż"))

    assert (found.face.path.name, found.exact, found.synthetic_bold) == ("bold.ttf", True, False)


def test_glyph_match_without_family_glyph_uses_arial_of_the_same_style(tmp_path: Path) -> None:
    episode = [write_font(tmp_path / "gandhi.ttf", "Gandhi", weight=700, italic=True, chars="Hab")]
    index = FontIndex.build(episode, _arial(tmp_path / "system"))
    request = index.match("Gandhi", weight=700, italic=True)

    assert request is not None
    found = index.glyph_match(request, ord("ż"))

    assert (found.face.path.name, found.exact, found.synthetic_bold, found.synthetic_italic) == (
        "arialbi.ttf",
        False,
        False,
        False,
    )


def test_glyph_match_without_any_glyph_keeps_face_as_approximate(tmp_path: Path) -> None:
    index = FontIndex.build([write_font(tmp_path / "font.ttf", "Family")], _arial(tmp_path / "system"))
    request = index.match("Family", weight=400, italic=False)

    assert request is not None
    found = index.glyph_match(request, ord("漢"))

    assert (found.face, found.exact) == (request.face, False)


def test_system_font_paths_off_windows_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(font_index, "is_windows", lambda: False)

    assert system_font_paths() == ()


def test_system_font_paths_lists_machine_and_user_font_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    machine = tmp_path / "windows" / "Fonts"
    user = tmp_path / "local" / "Microsoft" / "Windows" / "Fonts"
    machine.mkdir(parents=True)
    user.mkdir(parents=True)
    for path in (machine / "b.TTF", machine / "a.ttc", machine / "old.fon", user / "c.otf", user / "notes.txt"):
        path.write_bytes(b"")
    monkeypatch.setattr(font_index, "is_windows", lambda: True)
    monkeypatch.setenv("WINDIR", str(tmp_path / "windows"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert system_font_paths() == (machine / "a.ttc", machine / "b.TTF", user / "c.otf")
