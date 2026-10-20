from __future__ import annotations

import re
from pathlib import Path

import pytest
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.services.subtitles.fitting import fit_signs
from anishift.services.subtitles.geometry import Rect, RenderProfile, screen_rects
from anishift.services.subtitles.linebreak import NO_WRAP
from anishift.services.subtitles.service import load_subtitles, split_subtitles, write_translated
from anishift.services.subtitles.text import visible_text, visible_verses
from anishift.services.subtitles.types import LayoutReport

_FULL_HD: dict[str, str] = {"PlayResX": "1920", "PlayResY": "1080", "WrapStyle": "0"}


def _files(
    sources: list[SSAEvent],
    targets: list[str],
    styles: dict[str, SSAStyle] | None = None,
    info: dict[str, str] | None = None,
) -> tuple[SSAFile, SSAFile, RenderProfile]:
    subs: SSAFile = SSAFile()
    subs.styles = {"Default": SSAStyle(), **(styles or {})}
    subs.info.update(info or {})
    subs.events = sources
    translated: SSAFile = SSAFile()
    translated.styles = subs.styles
    translated.events = [event.copy() for event in sources]
    for event, text in zip(translated.events, targets, strict=True):
        event.text = text
    return subs, translated, RenderProfile.from_subs(subs, None)


def _fit(
    source: str,
    target: str,
    style: SSAStyle | None = None,
    styles: dict[str, SSAStyle] | None = None,
    info: dict[str, str] | None = None,
) -> str:
    subs, translated, profile = _files(
        [SSAEvent(text=source, end=1000)], [target], {"Default": style or SSAStyle(), **(styles or {})}, info
    )
    return fit_signs(subs, translated, [0], profile, LayoutReport())[0]


def _scales(text: str) -> list[tuple[str, float]]:
    return [(tag, float(value)) for tag, value in re.findall(r"\\(fsc[xy])(-?[\d.]+)", text)]


def _overflow(rects: tuple[Rect, ...], width: float, height: float) -> float:
    return max(
        (
            max(0.0, -rect.left) + max(0.0, rect.right - width) + max(0.0, -rect.top) + max(0.0, rect.bottom - height)
            for rect in rects
        ),
        default=0.0,
    )


def _area(rects: tuple[Rect, ...], others: tuple[Rect, ...]) -> float:
    return sum(
        max(0.0, min(a.right, b.right) - max(a.left, b.left)) * max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))
        for a in rects
        for b in others
    )


@pytest.mark.unit
def test_one_word_sign_much_wider_than_its_original_shrinks_both_axes_in_proportion() -> None:
    style: SSAStyle = SSAStyle(fontsize=80, scalex=80, scaley=120)
    result: str = _fit(r"{\an7\pos(10,100)}Red", r"{\an7\pos(10,100)}Czerwony", style)
    (_, x), (_, y) = _scales(result)[:2]
    assert result.startswith(r"{\fscx")
    assert r"\an7\pos(10,100)}" in result
    assert x / 80 == pytest.approx(y / 120, abs=0.001)
    assert x / 80 < 1
    assert visible_text(result) == "Czerwony"


@pytest.mark.unit
@pytest.mark.parametrize("target", ["Red", "R", ""])
def test_shorter_or_unchanged_sign_is_byte_identical(target: str) -> None:
    assert _fit("Red", target) == target


@pytest.mark.unit
def test_slightly_wider_small_sign_keeps_its_size() -> None:
    assert _fit(r"{\pos(100,100)}Red", r"{\pos(100,100)}Czerwony") == r"{\pos(100,100)}Czerwony"


@pytest.mark.unit
def test_scaling_preserves_geometry_and_scales_inline_animation_and_reset() -> None:
    style: SSAStyle = SSAStyle(fontsize=80, scalex=90, scaley=110)
    other: SSAStyle = SSAStyle(scalex=60, scaley=80)
    tags: str = r"{\an7\move(1,2,3,4)\org(5,6)\fad(80,90)"
    tags += r"\fscx120\fscy150\t(0,500,\fscx180\fscy200)}"
    target: str = tags + r"Czerwony{\rOther}Czerwony"
    result: str = _fit(tags + r"Red{\rOther}Red", target, style, {"Other": other})
    factor: float = _scales(result)[0][1] / 90
    assert factor < 1
    assert r"\an7\move(1,2,3,4)\org(5,6)\fad(80,90)" in result
    assert [value for _, value in _scales(result)] == pytest.approx(
        [90 * factor, 110 * factor, 120 * factor, 150 * factor, 180 * factor, 200 * factor, 60 * factor, 80 * factor],
        abs=0.001,
    )
    assert visible_text(result) == visible_text(target)


@pytest.mark.unit
def test_mirrored_scale_keeps_its_sign() -> None:
    result: str = _fit(r"{\an7\fscx-50}Red", r"{\an7\fscx-50}Czerwony", SSAStyle(fontsize=160))
    assert [value < 0 for tag, value in _scales(result) if tag == "fscx"] == [False, True]


@pytest.mark.unit
def test_drawing_is_never_scaled() -> None:
    source: str = r"{\p1}m 0 0 l 10 10"
    assert _fit(source, source + " 20 20") == source + " 20 20"


@pytest.mark.unit
def test_two_line_original_keeps_two_lines_for_a_two_word_translation() -> None:
    result: str = _fit(r"{\pos(200,40)}Public\Nschool", r"{\pos(200,40)}Publiczna szkoła")
    assert visible_verses(result) == ("Publiczna", "szkoła")
    assert r"\pos(200,40)" in result


@pytest.mark.unit
def test_short_translation_of_a_two_line_original_may_take_one_line() -> None:
    result: str = _fit(r"{\pos(200,40)}Come back\Nhome", r"{\pos(200,40)}Wróć")
    assert visible_verses(result) == ("Wróć",)


@pytest.mark.unit
def test_list_of_single_words_keeps_one_item_per_line_and_its_empty_lines() -> None:
    result: str = _fit(r"{\an8\pos(192,10)}1st\N\N2nd\N\N3rd", r"{\an8\pos(192,10)}1. 2. 3.")
    assert result == r"{\an8\pos(192,10)}1.\N\N2.\N\N3."


@pytest.mark.unit
def test_spaced_list_with_as_many_translated_words_keeps_its_items_on_their_lines() -> None:
    result: str = _fit(r"{\an8\pos(192,10)}500 p\N\N497 p\N\N489 p", r"{\an8\pos(192,10)}500 pkt 497 pkt 489 pkt")
    assert re.sub(r"\{[^}]*\}", "", result) == r"500 pkt\N\N497 pkt\N\N489 pkt"
    assert r"\an8\pos(192,10)}" in result


@pytest.mark.unit
def test_empty_authored_lines_stay_between_the_text_lines() -> None:
    result: str = _fit(
        r"{\an7\pos(10,10)}Has a tea ceremony license\N\N\N\NKnowledgeable",
        r"{\an7\pos(10,10)}Ma licencję na ceremonię herbacianą i ogromną wiedzę",
    )
    assert re.sub(r"\{[^}]*\}", "", result).count(r"\N\N\N\N") == 1
    assert len([verse for verse in visible_verses(result) if verse]) == 2


@pytest.mark.unit
def test_signature_dash_of_the_original_starts_its_line() -> None:
    result: str = _fit(
        r"{\an5\pos(192,144)}Come to the roof\N- Peek-a-Boo Seniors",
        r"{\an5\pos(192,144)}Zbiórka na dachu – Starsi z Peek-a-Boo",
    )
    assert [verse for verse in visible_verses(result) if verse] == ["Zbiórka na dachu", "– Starsi z Peek-a-Boo"]


@pytest.mark.unit
def test_style_change_at_an_authored_line_end_stays_a_line_end() -> None:
    result: str = _fit(
        r"{\an8\pos(960,100)\fs60}Episode 01\N{\fs40}The Boy Who Is the World's Strongest Sorcerer",
        r"{\an8\pos(960,100)\fs60}Odcinek pierwszy: {\fs40}Chłopiec, który jest najsilniejszym magikiem na świecie",
        info=_FULL_HD,
    )
    assert visible_verses(result)[0] == "Odcinek pierwszy:"


@pytest.mark.unit
def test_leading_label_with_a_colon_heads_the_sign_without_a_style_change() -> None:
    result: str = _fit(
        r"{\an8\pos(960,100)\fs50}Episode 02\NThe Boy Who Is the\NWorld's Strongest Sorcerer Dons a Mask",
        r"{\an8\pos(960,100)\fs50}Odcinek drugi: Chłopiec, który jest najsilniejszym magiem, przywdziewa maskę",
        info=_FULL_HD,
    )
    assert visible_verses(result)[0] == "Odcinek drugi:"


@pytest.mark.unit
def test_sign_at_the_screen_edge_does_not_leave_the_screen_more_than_its_original() -> None:
    subs, translated, profile = _files(
        [SSAEvent(text=r"{\an5\pos(40,540)\fs60}Safety Hazard", end=1000)],
        [r"{\an5\pos(40,540)\fs60}Zagrożenie dla bezpieczeństwa"],
        info=_FULL_HD,
    )
    result: str = fit_signs(subs, translated, [0], profile, LayoutReport())[0]
    before: float = _overflow(screen_rects(subs[0], subs[0].text, profile), 1920, 1080)
    after: float = _overflow(screen_rects(translated[0], result, profile), 1920, 1080)
    assert after <= before + 1 + 0.07 * 400
    assert visible_text(result) == "Zagrożenie dla bezpieczeństwa"


@pytest.mark.unit
def test_sign_does_not_grow_into_a_sign_shown_beside_it() -> None:
    sources: list[SSAEvent] = [
        SSAEvent(text=r"{\an5\pos(700,540)\fs60}Sale", end=1000),
        SSAEvent(text=r"{\an4\pos(820,540)\fs60}Japanese", end=1000),
    ]
    subs, translated, profile = _files(
        sources, [r"{\an5\pos(700,540)\fs60}Wielka wyprzedaż sezonowa", sources[1].text], info=_FULL_HD
    )
    result: str = fit_signs(subs, translated, [0], profile, LayoutReport())[0]
    neighbour: tuple[Rect, ...] = screen_rects(subs[1], subs[1].text, profile)
    before: float = _area(screen_rects(subs[0], subs[0].text, profile), neighbour)
    assert _area(screen_rects(translated[0], result, profile), neighbour) <= before + 1
    assert visible_text(result) == "Wielka wyprzedaż sezonowa"


@pytest.mark.unit
def test_sign_inside_a_clip_frame_stays_inside_it() -> None:
    clip: str = r"\clip(600,500,1320,580)"
    subs, translated, profile = _files(
        [SSAEvent(text=r"{\an5\pos(960,540)\fs50" + clip + "}Note: can't swim", end=1000)],
        [r"{\an5\pos(960,540)\fs50" + clip + "}Przypis: nie potrafi pływać ani trochę w ogóle"],
        info=_FULL_HD,
    )
    result: str = fit_signs(subs, translated, [0], profile, LayoutReport())[0]
    (rect,) = screen_rects(translated[0], result, profile)
    assert rect.left >= 600 - 0.07 * 720
    assert rect.right <= 1320 + 0.07 * 720


@pytest.mark.unit
def test_rotated_sign_is_boxed_by_its_turned_corners() -> None:
    subs, _, profile = _files([SSAEvent(text=r"{\an5\pos(960,540)\fs60}Wide sign text", end=1000)], ["x"])
    (flat,) = screen_rects(subs[0], subs[0].text, profile)
    (turned,) = screen_rects(subs[0], r"{\an5\pos(960,540)\fs60\frz90}Wide sign text", profile)
    assert turned.right - turned.left == pytest.approx(flat.bottom - flat.top, abs=0.01)
    assert turned.bottom - turned.top == pytest.approx(flat.right - flat.left, abs=0.01)


@pytest.mark.unit
def test_frames_of_one_sign_share_one_layout() -> None:
    sources: list[SSAEvent] = [
        SSAEvent(start=0, end=40, text=r"{\an5\pos(192,100)}Public\Nschool"),
        SSAEvent(start=40, end=80, text=r"{\an5\pos(193,100)}Public\Nschool"),
    ]
    subs, translated, profile = _files(
        sources, [r"{\an5\pos(192,100)}Publiczna szkoła", r"{\an5\pos(193,100)}Publiczna szkoła"]
    )
    fitted: dict[int, str] = fit_signs(subs, translated, [0, 1], profile, LayoutReport())
    assert fitted[0].replace("192", "193") == fitted[1]


@pytest.mark.integration
def test_translated_writer_fits_signs_but_does_not_resize_dialogue(tmp_path: Path) -> None:
    subs: SSAFile = SSAFile()
    subs.styles["Default"] = SSAStyle(fontsize=80)
    subs.styles["Sign"] = SSAStyle(fontsize=80)
    subs.events = [
        SSAEvent(style="Default", text="Red", start=0, end=2000),
        SSAEvent(style="Sign", text=r"{\an7\pos(10,10)}Red", start=0, end=2000),
    ]
    split = split_subtitles(subs, kind="ass", spoken_styles={"Default"})
    path: Path = tmp_path / "output.pl.ass"
    write_translated(split, {0: "Czerwony", 1: "Czerwony"}, path, fonts=None, dialogue_font=None)
    result: SSAFile = load_subtitles(path)
    assert result.events[0].text == "Czerwony"
    assert result.events[1].text.startswith(r"{\fscx")
    assert visible_text(result.events[1].text) == "Czerwony"


@pytest.mark.integration
def test_translated_writer_keeps_karaoke_untouched(tmp_path: Path) -> None:
    subs: SSAFile = SSAFile()
    subs.styles["Default"] = SSAStyle()
    subs.styles["OP"] = SSAStyle()
    karaoke: str = r"{\k20}Ai {\ko30}no {\kf40}uta"
    subs.events = [
        SSAEvent(style="Default", text="Red", start=0, end=2000),
        SSAEvent(style="OP", text=karaoke, start=0, end=2000),
    ]
    split = split_subtitles(subs, kind="ass", spoken_styles={"Default"})
    path: Path = tmp_path / "output.pl.ass"
    write_translated(split, {0: "Czerwony", 1: "Pieśń miłości"}, path, fonts=None, dialogue_font=None)
    assert load_subtitles(path).events[1].text == karaoke


@pytest.mark.unit
def test_fit_signs_returns_texts_only_for_the_requested_events() -> None:
    subs, translated, profile = _files(
        [SSAEvent(text="Red", end=1000), SSAEvent(text=r"{\pos(10,10)}Red", end=1000)],
        ["Czerwony", r"{\pos(10,10)}Czerwony"],
    )
    fitted: dict[int, str] = fit_signs(subs, translated, [1], profile, LayoutReport())
    assert list(fitted) == [1]
    assert visible_text(fitted[1]) == "Czerwony"


@pytest.mark.unit
def test_sign_that_libass_would_wrap_gets_the_shared_no_wrap_override() -> None:
    subs, translated, profile = _files(
        [SSAEvent(text=r"{\an8\pos(960,10)}Sign text", end=1000)],
        [r"{\an8\pos(960,10)}Napis ekranowy dość długi"],
        {"Default": SSAStyle(fontsize=60, marginl=800, marginr=800)},
        _FULL_HD,
    )
    assert NO_WRAP in fit_signs(subs, translated, [0], profile, LayoutReport())[0]
