from __future__ import annotations

import re
from pathlib import Path

import pytest
from PIL import ImageFont
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.services.subtitles.fitting import fit_signs
from anishift.services.subtitles.geometry import RenderProfile
from anishift.services.subtitles.layout import LayoutLimits
from anishift.services.subtitles.service import load_subtitles, split_subtitles, write_translated
from anishift.services.subtitles.text import visible_text, visible_verses
from anishift.services.subtitles.types import LayoutReport

_FULL_HD: dict[str, str] = {"PlayResX": "1920", "PlayResY": "1080", "WrapStyle": "0"}


def _fit(
    source: str,
    target: str,
    style: SSAStyle | None = None,
    styles: dict[str, SSAStyle] | None = None,
    info: dict[str, str] | None = None,
) -> str:
    subs: SSAFile = SSAFile()
    subs.styles = {"Default": style if style is not None else SSAStyle(), **(styles or {})}
    subs.info.update(info or {})
    subs.events = [SSAEvent(text=source)]
    translated: SSAFile = SSAFile()
    translated.events = [SSAEvent(text=target)]
    return fit_signs(subs, translated, [0], RenderProfile.from_subs(subs, None), LayoutReport())[0]


def _scale(text: str) -> float:
    return float(re.findall(r"\\fscx(-?[\d.]+)", text)[0]) / 100


def _arial_ratio(source: str, target: str) -> float:
    font: ImageFont.FreeTypeFont = ImageFont.truetype("arial.ttf", 64)
    return float(font.getlength(source) / font.getlength(target))


@pytest.mark.unit
def test_long_sign_scales_both_axes_inside_the_first_block_and_respects_readability_floor() -> None:
    style: SSAStyle = SSAStyle(scalex=80, scaley=120)
    result: str = _fit(r"{\an7\pos(100,100)}Red", r"{\an7\pos(100,100)}Czerwony", style)
    assert result == r"{\fscx57.6\fscy86.4\an7\pos(100,100)}Czerwony"


@pytest.mark.unit
@pytest.mark.parametrize("target", ["Red", "R", ""])
def test_shorter_or_unchanged_sign_is_byte_identical(target: str) -> None:
    assert _fit("Red", target) == target


@pytest.mark.unit
def test_scaling_preserves_geometry_and_scales_inline_animation_and_reset() -> None:
    style: SSAStyle = SSAStyle(scalex=90, scaley=110)
    other: SSAStyle = SSAStyle(scalex=60, scaley=80)
    tags: str = r"{\an8\move(1,2,3,4)\org(5,6)\clip(1,2,3,4)\fad(80,90)"
    tags += r"\fscx120\fscy150\t(0,500,\fscx180\fscy200)}"
    target: str = tags + r"Czerwony{\rOther}Czerwony"
    result: str = _fit(tags + r"Red{\rOther}Red", target, style, {"Other": other})
    assert r"\an8\move(1,2,3,4)\org(5,6)\clip(1,2,3,4)\fad(80,90)" in result
    assert r"\fscx86.4\fscy108\t(0,500,\fscx129.6\fscy144)" in result
    assert r"\rOther\fscx43.2\fscy57.6" in result
    assert visible_text(result) == visible_text(target)


@pytest.mark.unit
def test_reset_style_name_ignores_surrounding_whitespace() -> None:
    other: SSAStyle = SSAStyle(scalex=60, scaley=80)
    source: str = r"Red{\rOther }Red"
    result: str = _fit(source, source.replace("Red", "Czerwony"), SSAStyle(), {"Other": other})
    assert r"{\rOther \fscx43.2\fscy57.6}" in result


@pytest.mark.unit
def test_mirrored_scale_keeps_its_sign() -> None:
    source: str = r"{\fscx-50}Red"
    result: str = _fit(source, source.replace("Red", "Czerwony"))
    assert result == r"{\fscx72\fscy72\fscx-36}Czerwony"


@pytest.mark.unit
def test_drawing_is_never_scaled() -> None:
    source: str = r"{\p1}m 0 0 l 10 10"
    target: str = source + " 20 20"
    assert _fit(source, target) == target


@pytest.mark.unit
def test_scale_resets_keep_the_fitted_named_style_across_blocks() -> None:
    style: SSAStyle = SSAStyle(scalex=90, scaley=110)
    other: SSAStyle = SSAStyle(scalex=60, scaley=80)
    source: str = r"Red{\rOther}Red{\fsc}Red{\fscx}Red{\fscy}Red"
    result: str = _fit(source, source.replace("Red", "Czerwony"), style, {"Other": other})
    assert r"{\fscx43.2\fscy57.6}" in result
    assert r"{\fscx43.2}" in result
    assert r"{\fscy57.6}" in result


@pytest.mark.unit
def test_intermediate_scale_tracks_measured_width_instead_of_using_the_floor() -> None:
    expected: float = _arial_ratio("Public school", "Publiczna szkoła")
    result: str = _fit("Public school", "Publiczna szkoła")
    assert 0.72 < expected < 0.97
    assert _scale(result) == pytest.approx(expected, abs=0.00001)


@pytest.mark.unit
def test_small_width_growth_is_tolerated() -> None:
    source: str = "M" * 100
    assert _fit(source, source + "M") == source + "M"


@pytest.mark.unit
def test_scale_values_accept_ass_whitespace() -> None:
    source: str = r"{\fscx 120 \fscy150 }Red"
    result: str = _fit(source, source.replace("Red", "Czerwony"))
    assert result == r"{\fscx72\fscy72\fscx86.4 \fscy108 }Czerwony"


@pytest.mark.unit
def test_multiline_source_can_restore_line_break_without_moving_tags() -> None:
    result: str = _fit(r"{\pos(20,20)}Public\Nschool", r"{\pos(20,20)}Publiczna szkoła")
    assert r"Publiczna\Nszkoła" in result
    assert r"\pos(20,20)" in result


@pytest.mark.unit
def test_sign_that_libass_would_wrap_gets_a_balanced_break_and_per_line_fit() -> None:
    style: SSAStyle = SSAStyle(fontsize=75, marginl=18, marginr=15)
    source: str = r"{\pos(900,1)\fs120}Stu{\c&HF7FCFE&}dent Council Pre{\c&H8DD4F4&}sident"
    target: str = r"{\pos(900,1)\fs120}Przewodni{\c&HF7FCFE&}czący Samorządu Ucznio{\c&H8DD4F4&}wskiego"
    result: str = _fit(source, target, style, info=_FULL_HD)
    expected: float = _arial_ratio("Student Council President", "Samorządu Uczniowskiego")
    assert visible_verses(result) == ("Przewodniczący", "Samorządu Uczniowskiego")
    assert result.startswith(r"{\fscx")
    assert r"\pos(900,1)\fs120}" in result
    assert result.count("{") == target.count("{")
    assert _scale(result) == pytest.approx(expected, abs=0.00001)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tags", "info"),
    [
        (r"\fs40", _FULL_HD),
        (r"\fs200", _FULL_HD),
        (r"\fs120", {**_FULL_HD, "WrapStyle": "2"}),
        (r"\fs120\q2", _FULL_HD),
        (r"\fs10", {**_FULL_HD, "PlayResX": "wide"}),
    ],
    ids=["fits-screen", "source-already-wrapped", "wrap-style-none", "inline-no-wrap", "malformed-width"],
)
def test_floor_keeps_one_line_unless_libass_would_wrap_only_the_translation(tags: str, info: dict[str, str]) -> None:
    style: SSAStyle = SSAStyle(fontsize=75, marginl=18, marginr=15)
    target: str = "{" + tags + "}Przewodniczący Samorządu Uczniowskiego"
    result: str = _fit("{" + tags + "}Student Council President", target, style, info=info)
    assert result == "{" + r"\fscx72\fscy72" + tags + "}Przewodniczący Samorządu Uczniowskiego"


@pytest.mark.integration
def test_translated_writer_fits_signs_but_does_not_resize_dialogue(tmp_path: Path) -> None:
    subs: SSAFile = SSAFile()
    subs.styles["Default"] = SSAStyle()
    subs.styles["Sign"] = SSAStyle()
    subs.events = [
        SSAEvent(style="Default", text="Red", start=0, end=2000),
        SSAEvent(style="Sign", text=r"{\pos(10,10)}Red", start=0, end=2000),
    ]
    split = split_subtitles(subs, kind="ass", spoken_styles={"Default"})
    path: Path = tmp_path / "output.pl.ass"
    write_translated(split, {0: "Czerwony", 1: "Czerwony"}, path, fonts=None, limits=LayoutLimits(), dialogue_font=None)
    result: SSAFile = load_subtitles(path)
    assert result.events[0].text == "Czerwony"
    assert result.events[1].text == r"{\fscx72\fscy72\pos(10,10)}Czerwony"


@pytest.mark.unit
def test_fit_signs_returns_texts_only_for_the_requested_events() -> None:
    subs: SSAFile = SSAFile()
    subs.styles = {"Default": SSAStyle()}
    subs.events = [SSAEvent(text="Red"), SSAEvent(text=r"{\pos(10,10)}Red")]
    translated: SSAFile = SSAFile()
    translated.events = [SSAEvent(text="Czerwony"), SSAEvent(text=r"{\pos(10,10)}Czerwony")]
    fitted: dict[int, str] = fit_signs(subs, translated, [1], RenderProfile.from_subs(subs, None), LayoutReport())
    assert fitted == {1: r"{\fscx72\fscy72\pos(10,10)}Czerwony"}
