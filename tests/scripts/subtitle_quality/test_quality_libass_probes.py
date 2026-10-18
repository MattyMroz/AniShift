from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from pysubs2 import Alignment, Color, SSAEvent, SSAFile, SSAStyle

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.fonts import FontIndex, system_font_paths
from anishift.services.subtitles.geometry import RenderProfile, screen_rects, wrap_text
from scripts.subtitle_quality import render

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

_TOLERANCE_PX: Final[float] = 2.0
_THRESHOLD_TEXT: Final[str] = "Regarding the other day's incident."


def _needs(*names: str) -> FontIndex:
    if resolve_binary(Binary.FFMPEG) is None:
        pytest.skip("ffmpeg is not installed")
    paths = system_font_paths()
    present = {path.name.casefold() for path in paths}
    if not all(name in present for name in names):
        pytest.skip("system fonts for the probe are not available")
    return FontIndex.build((), paths)


def _subs(style: SSAStyle, size: tuple[int, int]) -> SSAFile:
    subs = SSAFile()
    subs.info = {"PlayResX": str(size[0]), "PlayResY": str(size[1]), "ScaledBorderAndShadow": "yes"}
    subs.styles = {"Default": style}
    return subs


@pytest.mark.parametrize("scales", [r"\fscx200\fscy50", r"\fscx50\fscy200", r"\fscx130\fscy130"])
def test_screen_rects_match_libass_for_synthetic_italic_with_independent_axis_scales(
    tmp_path: Path, scales: str
) -> None:
    fonts = _needs("impact.ttf")
    style = SSAStyle(fontname="Impact", fontsize=80, primarycolor=Color(255, 255, 255), outline=0, shadow=0)
    subs = _subs(style, (1920, 1080))
    event = SSAEvent(start=0, end=2000, style="Default", text=rf"{{\an5\pos(960,540)\i1{scales}}}Hello World")

    (box,), _ = render.measure_boxes(subs, [event], (1920, 1080), tmp_path, "italic")
    (rect,) = screen_rects(event, event.text, RenderProfile.from_subs(subs, fonts))

    assert box is not None
    assert (rect.left, rect.top, rect.right, rect.bottom) == pytest.approx(box, abs=_TOLERANCE_PX)


def test_wrap_text_breaks_exactly_where_libass_does_at_the_wrap_limit(tmp_path: Path) -> None:
    fonts = _needs("trebuc.ttf")
    style = SSAStyle(fontname="Trebuchet MS", fontsize=24, outline=2, alignment=Alignment.BOTTOM_CENTER)
    subs = _subs(style, (640, 360))
    profile = RenderProfile.from_subs(subs, fonts)
    events = [
        SSAEvent(start=0, end=2000, style="Default", text=_THRESHOLD_TEXT, marginl=margin, marginr=margin + odd)
        for margin in range(157, 163)
        for odd in (0, 1)
    ]

    libass = render.wrap_breaks(subs, events, (640, 360), tmp_path, "threshold")
    ours = [wrap_text(event, event.text, profile).count(r"\N") for event in events]

    assert libass == ours
    assert 0 in ours
    assert 1 in ours
