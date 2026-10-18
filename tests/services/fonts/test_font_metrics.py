from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from font_test_helpers import ADVANCE, INK_BOX, build_font, write_font

from anishift.services.fonts.index import read_faces
from anishift.services.fonts.metrics import font_scale, glyph_metrics

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.services.fonts.types import FontFace

pytestmark = pytest.mark.integration

_LIBASS_GLYPH_SIZE = 256


def _rounded_face(path: Path, win: tuple[int, int]) -> FontFace:
    font = build_font("Box", win=win)
    font["head"].flags |= 1 << 3
    font.save(path)
    return read_faces(path)[0]


def test_glyph_metrics_round_the_advance_at_the_libass_glyph_size_and_measure_ink_at_reference_size(
    tmp_path: Path,
) -> None:
    face = read_faces(write_font(tmp_path / "box.ttf", "Box"))[0]

    metrics = glyph_metrics(face, "H")

    left, bottom, right, top = INK_BOX
    assert metrics.advance == pytest.approx(round(ADVANCE * _LIBASS_GLYPH_SIZE / 1000) * 1000 / _LIBASS_GLYPH_SIZE)
    assert metrics.ink_left == pytest.approx(left, abs=1)
    assert metrics.ink_right == pytest.approx(right, abs=1)
    assert metrics.ink_ascent == pytest.approx(top, abs=1)
    assert metrics.ink_descent == pytest.approx(-bottom, abs=1)
    assert (metrics.outline_left, metrics.outline_right) == pytest.approx((left, right), abs=1)
    assert metrics.has_ink


def test_glyph_metrics_blank_glyph_has_advance_without_ink(tmp_path: Path) -> None:
    face = read_faces(write_font(tmp_path / "box.ttf", "Box"))[0]

    metrics = glyph_metrics(face, " ")

    assert metrics.advance == pytest.approx(round(ADVANCE * _LIBASS_GLYPH_SIZE / 1000) * 1000 / _LIBASS_GLYPH_SIZE)
    assert not metrics.has_ink
    assert (metrics.outline_left, metrics.outline_right) == (0.0, 0.0)


def test_glyph_metrics_slant_the_ink_and_outline_box_by_height_like_synthetic_italic(tmp_path: Path) -> None:
    face = read_faces(write_font(tmp_path / "box.ttf", "Box"))[0]

    upright = glyph_metrics(face, "H")
    slanted = glyph_metrics(face, "H", slant=0.25)

    left, bottom, right, top = INK_BOX
    assert (slanted.ink_left, slanted.ink_right) == pytest.approx((left + 0.25 * bottom, right + 0.25 * top))
    assert (slanted.outline_left, slanted.outline_right) == pytest.approx((left + 0.25 * bottom, right + 0.25 * top))
    assert (slanted.advance, slanted.ink_ascent) == (upright.advance, upright.ink_ascent)


@pytest.mark.parametrize(("win", "expected"), [((800, 200), 0.05), ((1000, 250), 0.04)])
def test_font_scale_maps_font_size_to_ascent_plus_descent(
    tmp_path: Path, win: tuple[int, int], expected: float
) -> None:
    face = read_faces(write_font(tmp_path / "box.ttf", "Box", win=win))[0]

    assert font_scale(face, 50) == pytest.approx(expected)


def test_font_scale_rounds_the_libass_glyph_ppem_of_a_truetype_face_flagged_for_integer_ppem(tmp_path: Path) -> None:
    plain = read_faces(write_font(tmp_path / "plain.ttf", "Box", win=(900, 230)))[0]
    rounded = _rounded_face(tmp_path / "rounded.ttf", (900, 230))

    assert font_scale(plain, 50) == pytest.approx(50 / 1130)
    assert font_scale(rounded, 50) == pytest.approx(50 / _LIBASS_GLYPH_SIZE * 227 / 1000)
