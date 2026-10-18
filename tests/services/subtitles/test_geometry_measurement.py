from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from pysubs2 import Alignment, Color, SSAEvent, SSAFile, SSAStyle

from anishift.services.fonts import FontIndex, system_font_paths
from anishift.services.subtitles.geometry import (
    Rect,
    RenderProfile,
    TextBox,
    available_width,
    measure_text,
    screen_rects,
    wrap_text,
)
from anishift.services.subtitles.text import visible_text, visible_verses

_QUALITY: Final[Path] = Path(__file__).resolve().parents[3] / "workspace" / ".quality"
_ICEBLADE_FONTS: Final[Path] = (
    _QUALITY
    / "library"
    / "The.Iceblade.Sorcerer.Shall.Rule.the.World.S02E01.1080p.CR.WEB-DL.AAC2.0.H.264-VARYG"
    / "fonts"
)
_HEADER: Final[dict[str, str]] = {"PlayResX": "1920", "PlayResY": "1080", "ScaledBorderAndShadow": "yes"}
_LIBASS_TOLERANCE_PX: Final[float] = 2.0
_LONG_LINE: Final[str] = "This sentence is far too long to fit on one line of a narrow screen at all"
_LIBASS_BOXES: Final[dict[str, tuple[str, str, tuple[int, int, int, int]]]] = {
    "kern-AV": ("Arial", "AVAVAVAVAVAVAVAVAV", (422, 507, 1498, 571)),
    "plain-arial": ("Arial", "Zażółć gęślą jaźń", (616, 506, 1300, 590)),
    "plain-trebuchet": ("Trebuchet MS", "Zażółć gęślą jaźń", (634, 502, 1285, 589)),
    "plain-georgia": ("Georgia", "Zażółć gęślą jaźń", (638, 504, 1281, 590)),
    "plain-times": ("Times New Roman", "Zażółć gęślą jaźń", (647, 507, 1274, 590)),
    "plain-impact": ("Impact", "Zażółć gęślą jaźń", (680, 505, 1238, 586)),
    "plain-comic": ("Comic Sans MS", "Zażółć gęślą jaźń", (675, 510, 1246, 590)),
    "plain-tahoma": ("Tahoma", "Zażółć gęślą jaźń", (651, 505, 1267, 590)),
    "bord3": ("Arial", r"{\bord3}Hello World", (733, 503, 1188, 576)),
    "bord8": ("Arial", r"{\bord8}Hello World", (728, 498, 1193, 581)),
    "bord8-invisible": ("Arial", r"{\bord8\3a&HFF&}Hello World", (736, 506, 1185, 573)),
    "shad6": ("Arial", r"{\shad6}Hello World", (736, 506, 1191, 579)),
    "shad6-invisible": ("Arial", r"{\shad6\4a&HFF&}Hello World", (736, 506, 1185, 573)),
    "bord4-shad6": ("Arial", r"{\bord4\shad6}Hello World", (732, 502, 1195, 583)),
    "bord4-blur1": ("Arial", r"{\bord4\blur1}Hello World", (731, 502, 1190, 577)),
    "blur3": ("Arial", r"{\blur3}Hello World", (730, 500, 1191, 579)),
    "fscx50": ("Arial", r"{\fscx50}Hello World", (848, 506, 1073, 573)),
    "fscx150": ("Arial", r"{\fscx150}Hello World", (624, 506, 1297, 573)),
    "fsp10": ("Arial", r"{\fsp10}Hello World", (681, 506, 1230, 573)),
    "fsp10-fscx150": ("Arial", r"{\fsp10\fscx150}Hello World", (541, 506, 1365, 573)),
    "bold-arial": ("Arial", r"{\b1}Hello World", (717, 506, 1203, 573)),
    "italic-synthetic-impact": ("Impact", r"{\i1}Hello World", (767, 507, 1176, 574)),
    "italic-arial": ("Arial", r"{\i1}Hello World", (736, 506, 1207, 573)),
    "mixed-fonts": ("Arial", r"Hello {\fnGeorgia}World {\fnImpact\fs140}BIG", (640, 493, 1283, 588)),
    "lines3": ("Arial", r"Line one\Nsecond line here\Nthree", (634, 407, 1285, 672)),
    "lines2-mixed-size": ("Arial", r"{\fs60}small line\N{\fs120}Big line", (791, 460, 1132, 630)),
    "trailing-space": ("Arial", "Hello World   ", (736, 506, 1185, 573)),
    "hard-space": ("Arial", r"Hello\hWorld", (736, 506, 1185, 573)),
}
_LIBASS_BOX_STYLE_BOXES: Final[dict[str, tuple[str, tuple[int, int, int, int]]]] = {
    "box": ("Hello World", (725, 485, 1195, 595)),
    "box-shadow": (r"{\shad6}Hello World", (725, 485, 1201, 600)),
    "box-without-border": (r"{\bord0}Hello World", (736, 506, 1185, 573)),
    "box-two-lines": (r"Hello World\Nsecond", (725, 435, 1195, 645)),
}


def _iceblade_fonts() -> FontIndex:
    if not _ICEBLADE_FONTS.is_dir():
        pytest.skip("Iceblade quality pair fonts are not available")
    return FontIndex.build(sorted(path for path in _ICEBLADE_FONTS.iterdir() if path.is_file()), system_font_paths())


@pytest.fixture(scope="module")
def system_fonts() -> FontIndex:
    paths: tuple[Path, ...] = system_font_paths()
    if not any(path.name.casefold() == "arial.ttf" for path in paths):
        pytest.skip("system Arial is not available")
    return FontIndex.build((), paths)


def _style(font: str = "Arial", **options: object) -> SSAStyle:
    style: SSAStyle = SSAStyle(
        fontname=font,
        fontsize=100,
        primarycolor=Color(255, 255, 255),
        outlinecolor=Color(0, 0, 0),
        backcolor=Color(0, 0, 0, 0),
        outline=0,
        shadow=0,
        alignment=Alignment.MIDDLE_CENTER,
        borderstyle=1,
    )
    for name, value in options.items():
        setattr(style, name, value)
    return style


def _profile(fonts: FontIndex | None, style: SSAStyle, header: dict[str, str] | None = None) -> RenderProfile:
    subs: SSAFile = SSAFile()
    subs.info = {**_HEADER, **(header or {})}
    subs.styles = {"Default": style}
    return RenderProfile.from_subs(subs, fonts)


def _rect(box: tuple[int, int, int, int]) -> Rect:
    return Rect(*(float(value) for value in box))


def _assert_near(actual: Rect, expected: Rect, tolerance: float) -> None:
    assert actual.left == pytest.approx(expected.left, abs=tolerance)
    assert actual.top == pytest.approx(expected.top, abs=tolerance)
    assert actual.right == pytest.approx(expected.right, abs=tolerance)
    assert actual.bottom == pytest.approx(expected.bottom, abs=tolerance)


@pytest.mark.integration
@pytest.mark.parametrize("label", sorted(_LIBASS_BOXES))
def test_screen_rects_match_the_libass_boxes_of_the_control_probes(label: str) -> None:
    font, text, box = _LIBASS_BOXES[label]
    profile: RenderProfile = _profile(_iceblade_fonts(), _style(font), {"WrapStyle": "2"})
    event: SSAEvent = SSAEvent(text=r"{\pos(960,540)}" + text)

    (rect,) = screen_rects(event, event.text, profile)

    _assert_near(rect, _rect(box), _LIBASS_TOLERANCE_PX)


@pytest.mark.integration
@pytest.mark.parametrize("label", sorted(_LIBASS_BOX_STYLE_BOXES))
def test_screen_rects_match_the_libass_boxes_of_opaque_box_probes(label: str) -> None:
    text, box = _LIBASS_BOX_STYLE_BOXES[label]
    style: SSAStyle = _style(borderstyle=3, outline=4, outlinecolor=Color(30, 60, 200, 0))
    profile: RenderProfile = _profile(_iceblade_fonts(), style, {"WrapStyle": "2"})
    event: SSAEvent = SSAEvent(text=r"{\pos(960,540)}" + text)

    (rect,) = screen_rects(event, event.text, profile)

    _assert_near(rect, _rect(box), _LIBASS_TOLERANCE_PX)


@pytest.mark.integration
def test_measure_text_counts_glyphs_drawn_by_another_face_and_keeps_family_variants_exact() -> None:
    profile: RenderProfile = _profile(_iceblade_fonts(), _style("Comic Sans MS"))
    missing: RenderProfile = _profile(_iceblade_fonts(), _style("No Such Family"))

    comic: TextBox = measure_text(SSAEvent(), "Zażółć gęślą jaźń", profile)
    substituted: TextBox = measure_text(SSAEvent(), "Hello", missing)

    assert (comic.status, comic.fallback_glyphs) == ("exact", 7)
    assert (substituted.status, substituted.fallback_glyphs) == ("approximate", 5)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ({"PlayResX": "1920"}, (1920, 1440)),
        ({"PlayResX": "1280"}, (1280, 1024)),
        ({"PlayResY": "1080"}, (1440, 1080)),
        ({"PlayResY": "1024"}, (1280, 1024)),
        ({"PlayResX": "&H780", "PlayResY": "720.9"}, (1920, 720)),
        ({}, (384, 288)),
    ],
)
def test_render_profile_completes_a_missing_play_res_dimension_like_libass(
    header: dict[str, str], expected: tuple[int, int]
) -> None:
    subs: SSAFile = SSAFile()
    subs.info = header

    profile: RenderProfile = RenderProfile.from_subs(subs, None)

    assert (profile.play_res_x, profile.play_res_y) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"), [("yes", True), ("Yes please", True), ("1", True), ("no", False), ("0", False), ("", False)]
)
def test_render_profile_reads_booleans_like_libass_with_no_as_the_default(value: str, expected: bool) -> None:
    subs: SSAFile = SSAFile()
    subs.info = {"ScaledBorderAndShadow": value, "Kerning": value} if value else {}

    profile: RenderProfile = RenderProfile.from_subs(subs, None)

    assert (profile.scaled_border, profile.kerning) == (expected, expected)


@pytest.mark.integration
def test_measure_text_scales_glyphs_and_spacing_by_the_axis_factors_but_not_the_outline(
    system_fonts: FontIndex,
) -> None:
    profile: RenderProfile = _profile(system_fonts, _style(outline=4))
    event: SSAEvent = SSAEvent(text=r"{\fsp6}Hello World")

    full: TextBox = measure_text(event, event.text, profile)
    half: TextBox = measure_text(event, event.text, profile, fx=0.5, fy=0.5)

    assert full.edge == half.edge == pytest.approx(8)
    assert half.width - half.edge == pytest.approx((full.width - full.edge) / 2, rel=0.01)
    assert half.height - 8 == pytest.approx((full.height - 8) / 2, rel=0.02)


@pytest.mark.integration
def test_measure_text_marks_kerning_moves_transforms_rotation_and_unscaled_outline_approximate(
    system_fonts: FontIndex,
) -> None:
    plain: RenderProfile = _profile(system_fonts, _style(outline=2))
    kerned: RenderProfile = _profile(system_fonts, _style(), {"Kerning": "yes"})
    unscaled: RenderProfile = _profile(system_fonts, _style(outline=2), {"ScaledBorderAndShadow": "no"})

    def status(text: str, profile: RenderProfile = plain) -> str:
        return measure_text(SSAEvent(text=text), text, profile).status

    assert status("Sign") == "exact"
    assert status(r"{\t(0,500,\1c&H0000FF&)}Sign") == "exact"
    assert status(r"{\move(10,10,10,10)}Sign") == "exact"
    assert status("Sign", kerned) == "approximate"
    assert status("Sign", unscaled) == "approximate"
    assert status(r"{\move(10,10,50,10)}Sign") == "approximate"
    assert status(r"{\t(0,500,\fscx150)}Sign") == "approximate"
    assert status(r"{\frz15}Sign") == "approximate"
    assert status(r"{\fnArial\fn@Arial}Sign") == "approximate"


@pytest.mark.integration
def test_measure_text_gives_an_empty_line_half_the_line_height(system_fonts: FontIndex) -> None:
    profile: RenderProfile = _profile(system_fonts, _style())

    two: TextBox = measure_text(SSAEvent(), r"Ha\NHa", profile)
    gap: TextBox = measure_text(SSAEvent(), r"Ha\N\NHa", profile)
    trailing: TextBox = measure_text(SSAEvent(), r"Ha\N", profile)
    single: TextBox = measure_text(SSAEvent(), "Ha", profile)

    assert gap.height - two.height == pytest.approx(50, abs=0.5)
    assert len(gap.line_widths) == 3
    assert trailing.height == single.height


@pytest.mark.integration
def test_measure_text_draws_nothing_for_invisible_text(system_fonts: FontIndex) -> None:
    profile: RenderProfile = _profile(system_fonts, _style())

    hidden: TextBox = measure_text(SSAEvent(), r"{\alpha&HFF&}Hidden", profile)
    partly: TextBox = measure_text(SSAEvent(), r"Shown{\alpha&HFF&} hidden", profile)
    shown: TextBox = measure_text(SSAEvent(), "Shown", profile)

    assert (hidden.width, hidden.height) == (0.0, 0.0)
    assert partly.width == pytest.approx(shown.width)


@pytest.mark.integration
def test_wrap_text_breaks_greedily_by_words_then_balances_unless_wrap_style_one(system_fonts: FontIndex) -> None:
    style: SSAStyle = _style(fontsize=60, alignment=Alignment.BOTTOM_CENTER)
    balanced: RenderProfile = _profile(system_fonts, style, {"PlayResX": "960", "PlayResY": "540"})
    greedy: RenderProfile = _profile(system_fonts, style, {"PlayResX": "960", "PlayResY": "540", "WrapStyle": "1"})
    event: SSAEvent = SSAEvent(text=_LONG_LINE)

    balanced_lines: tuple[str, ...] = visible_verses(wrap_text(event, event.text, balanced))
    greedy_lines: tuple[str, ...] = visible_verses(wrap_text(event, event.text, greedy))
    widths: list[float] = [measure_text(event, line, balanced).width for line in balanced_lines]

    assert len(balanced_lines) == len(greedy_lines) > 1
    assert visible_text(" ".join(balanced_lines)) == _LONG_LINE
    assert balanced_lines != greedy_lines
    assert len(greedy_lines[-1]) < len(balanced_lines[-1])
    assert max(widths) < available_width(event, balanced)


@pytest.mark.integration
def test_wrap_text_keeps_the_text_without_overflow_or_with_wrapping_off(system_fonts: FontIndex) -> None:
    profile: RenderProfile = _profile(system_fonts, _style(fontsize=60), {"PlayResX": "960", "PlayResY": "540"})
    styled_off: RenderProfile = _profile(
        system_fonts, _style(fontsize=60), {"PlayResX": "960", "PlayResY": "540", "WrapStyle": "2"}
    )
    inline_off: str = r"{\q2}" + _LONG_LINE
    narrow: SSAEvent = SSAEvent(text="Short line", marginl=10, marginr=10)

    assert wrap_text(SSAEvent(text=inline_off), inline_off, profile) == inline_off
    assert wrap_text(SSAEvent(text=_LONG_LINE), _LONG_LINE, styled_off) == _LONG_LINE
    assert wrap_text(narrow, narrow.text, profile) == narrow.text
    assert r"\N" in wrap_text(SSAEvent(text="Short line", marginl=400, marginr=400), "Short line", profile)


@pytest.mark.integration
def test_screen_rects_place_the_wrapped_text_between_the_margins(system_fonts: FontIndex) -> None:
    style: SSAStyle = _style(fontsize=60, alignment=Alignment.BOTTOM_CENTER, marginl=40, marginr=40, marginv=30)
    profile: RenderProfile = _profile(system_fonts, style, {"PlayResX": "960", "PlayResY": "540"})
    event: SSAEvent = SSAEvent(text=_LONG_LINE)

    (rect,) = screen_rects(event, event.text, profile)
    wrapped: TextBox = measure_text(event, wrap_text(event, event.text, profile), profile)

    assert 40 <= rect.left < rect.right <= 920
    assert (rect.left + rect.right) / 2 == pytest.approx(480, abs=6)
    assert rect.bottom == pytest.approx(540 - 30, abs=20)
    assert (rect.right - rect.left, rect.bottom - rect.top) == pytest.approx((wrapped.width, wrapped.height))


@pytest.mark.integration
def test_screen_rects_return_the_start_and_end_of_a_move_and_a_size_transform(system_fonts: FontIndex) -> None:
    profile: RenderProfile = _profile(system_fonts, _style())
    moving: str = r"{\move(400,300,1400,300)}Sign"
    growing: str = r"{\pos(960,540)\t(0,1000,\fscx200)}Sign"

    start, end = screen_rects(SSAEvent(text=moving), moving, profile)
    small, large = screen_rects(SSAEvent(text=growing), growing, profile)

    assert ((start.left + start.right) / 2, (end.left + end.right) / 2) == pytest.approx((400, 1400), abs=2)
    assert end.right - end.left == pytest.approx(start.right - start.left)
    assert large.right - large.left == pytest.approx(2 * (small.right - small.left), rel=0.02)
