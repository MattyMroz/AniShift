from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from font_test_helpers import ADVANCE, INK_BOX, write_font

from anishift.services.fonts.index import read_faces
from anishift.services.fonts.metrics import font_scale, glyph_metrics

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def test_glyph_metrics_measure_advance_and_ink_at_reference_size(tmp_path: Path) -> None:
    face = read_faces(write_font(tmp_path / "box.ttf", "Box"))[0]

    metrics = glyph_metrics(face, "H")

    left, bottom, right, top = INK_BOX
    assert metrics.advance == pytest.approx(ADVANCE)
    assert metrics.ink_left == pytest.approx(left, abs=1)
    assert metrics.ink_right == pytest.approx(right, abs=1)
    assert metrics.ink_ascent == pytest.approx(top, abs=1)
    assert metrics.ink_descent == pytest.approx(-bottom, abs=1)
    assert metrics.has_ink


def test_glyph_metrics_blank_glyph_has_advance_without_ink(tmp_path: Path) -> None:
    face = read_faces(write_font(tmp_path / "box.ttf", "Box"))[0]

    metrics = glyph_metrics(face, " ")

    assert metrics.advance == pytest.approx(ADVANCE)
    assert not metrics.has_ink


@pytest.mark.parametrize(("win", "expected"), [((800, 200), 0.05), ((1000, 250), 0.04)])
def test_font_scale_maps_font_size_to_ascent_plus_descent(
    tmp_path: Path, win: tuple[int, int], expected: float
) -> None:
    face = read_faces(write_font(tmp_path / "box.ttf", "Box", win=win))[0]

    assert font_scale(face, 50) == pytest.approx(expected)
