from __future__ import annotations

import pytest
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.services.subtitles.geometry import (
    RenderProfile,
    TextBox,
    available_width,
    measure_text,
    safe_width,
    screen_rects,
    wrap_text,
)
from anishift.services.subtitles.text import visible_text

_LONG_LINE = "This sentence is far too long to fit on one line of a narrow screen"


def _profile(info: dict[str, str] | None = None, style: SSAStyle | None = None) -> RenderProfile:
    subs: SSAFile = SSAFile()
    subs.info = dict(info or {})
    subs.styles = {"Default": style if style is not None else SSAStyle()}
    return RenderProfile.from_subs(subs, None)


@pytest.mark.unit
def test_render_profile_reads_the_header_and_falls_back_to_the_default_canvas() -> None:
    full: RenderProfile = _profile(
        {"PlayResX": "1920", "PlayResY": "1080", "WrapStyle": "2", "ScaledBorderAndShadow": "yes"}
    )
    bare: RenderProfile = _profile({"PlayResX": "wide"})

    assert (full.play_res_x, full.play_res_y, full.wrap_style, full.scaled_border) == (1920, 1080, 2, True)
    assert (bare.play_res_x, bare.play_res_y, bare.wrap_style, bare.scaled_border) == (384, 288, 0, False)
    assert list(full.styles) == ["Default"]
    assert full.fonts is None


@pytest.mark.unit
def test_measure_text_scales_every_line_by_the_starting_size_and_the_axis_factors() -> None:
    profile: RenderProfile = _profile(style=SSAStyle(fontsize=32))
    event: SSAEvent = SSAEvent(text=r"Hello\Nworld wide")

    box: TextBox = measure_text(event, event.text, profile)
    half: TextBox = measure_text(event, event.text, profile, fx=0.5, fy=0.5)
    bigger: TextBox = measure_text(SSAEvent(text=r"{\fs64}Hello\Nworld wide"), event.text, profile)

    assert len(box.line_widths) == 2
    assert box.width == max(box.line_widths) > 0
    assert box.height == 2 * 32
    assert (box.status, box.edge, box.fallback_glyphs) == ("approximate", 0.0, 0)
    assert (half.width, half.height) == pytest.approx((box.width / 2, box.height / 2))
    assert bigger.width == pytest.approx(2 * box.width)


@pytest.mark.unit
def test_available_width_prefers_event_margins_over_style_margins() -> None:
    profile: RenderProfile = _profile({"PlayResX": "1920"}, SSAStyle(marginl=10, marginr=20))

    assert available_width(SSAEvent(), profile) == 1890
    assert available_width(SSAEvent(marginl=100), profile) == 1800


@pytest.mark.unit
def test_wrap_text_breaks_a_line_wider_than_the_canvas_unless_wrapping_is_off() -> None:
    profile: RenderProfile = _profile({"PlayResX": "640"}, SSAStyle(fontsize=60))
    no_wrap: RenderProfile = _profile({"PlayResX": "640", "WrapStyle": "2"}, SSAStyle(fontsize=60))
    inline: str = r"{\q2}" + _LONG_LINE

    wrapped: str = wrap_text(SSAEvent(text=_LONG_LINE), _LONG_LINE, profile)

    assert r"\N" in wrapped
    assert visible_text(wrapped) == _LONG_LINE
    assert wrap_text(SSAEvent(text="Short"), "Short", profile) == "Short"
    assert wrap_text(SSAEvent(text=inline), inline, profile) == inline
    assert wrap_text(SSAEvent(text=_LONG_LINE), _LONG_LINE, no_wrap) == _LONG_LINE


@pytest.mark.unit
def test_screen_rects_anchor_the_box_at_the_margins_the_position_or_both_ends_of_a_move() -> None:
    profile: RenderProfile = _profile(
        {"PlayResX": "640", "PlayResY": "360"}, SSAStyle(fontsize=40, marginl=10, marginr=10, marginv=20)
    )
    width: float = measure_text(SSAEvent(text="Sign"), "Sign", profile).width
    positioned: str = r"{\an7\pos(100,50)}Sign"
    moving: str = r"{\an5\move(100,100,300,200)}Sign"

    (bottom,) = screen_rects(SSAEvent(text="Sign"), "Sign", profile)
    (corner,) = screen_rects(SSAEvent(text=positioned), positioned, profile)
    start, end = screen_rects(SSAEvent(text=moving), moving, profile)

    assert bottom.bottom == 340
    assert (bottom.left + bottom.right) / 2 == pytest.approx(320)
    assert (corner.left, corner.top, corner.bottom) == (100, 50, 90)
    assert corner.right == pytest.approx(100 + width)
    assert ((start.left + start.right) / 2, (start.top + start.bottom) / 2) == pytest.approx((100, 100))
    assert ((end.left + end.right) / 2, (end.top + end.bottom) / 2) == pytest.approx((300, 200))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "margin", "expected"),
    [
        ("x", 10, 0.9),
        (r"{\an7}x", 10, 0.9),
        (r"{\an4\pos(50,500)}x", 0, 0.9),
        (r"{\an1\pos(1056,1000)}x", 0, 0.4),
        (r"{\pos(960,500)}x", 0, 0.9),
    ],
)
def test_safe_width_stays_inside_the_central_share_of_the_canvas(text: str, margin: int, expected: float) -> None:
    profile: RenderProfile = _profile(
        {"PlayResX": "1920", "PlayResY": "1080"}, SSAStyle(marginl=margin, marginr=margin)
    )

    assert safe_width(SSAEvent(text=text), profile, 0.9) / 1920 == pytest.approx(expected)
