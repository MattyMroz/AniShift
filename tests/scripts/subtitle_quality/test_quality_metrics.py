from __future__ import annotations

from itertools import combinations

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.services.subtitles.classifier import Category
from scripts.subtitle_quality import metrics

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,26,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: Sign,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_VERDICTS = {"Default": Category.DIALOG, "Sign": Category.SIGN}


def _subs(*lines: str) -> SSAFile:
    return SSAFile.from_string(_HEADER + "\n".join(lines) + "\n")


def _line(start: str, end: str, style: str, text: str, actor: str = "") -> str:
    return f"Dialogue: 0,0:00:{start},0:00:{end},{style},{actor},0,0,0,,{text}"


def _event(text: str, start: int = 0, end: int = 2000) -> SSAEvent:
    return SSAEvent(start=start, end=end, text=text)


def _sign(
    span: tuple[int, int],
    source_box: metrics.Box,
    output_box: metrics.Box,
    *,
    animated: bool = False,
    clip: metrics.Box | None = None,
) -> metrics.Sign:
    return metrics.Sign(
        0,
        0,
        *span,
        "Sign",
        "Exit",
        "Wyjście",
        has_clip=clip is not None,
        animated=animated,
        source_clip=clip,
        output_clip=clip,
        source_box=source_box,
        output_box=output_box,
    )


def test_pair_events_matches_timing_and_style_in_order() -> None:
    source = metrics.dialogue(
        _subs(
            _line("01.00", "02.00", "Default", "One"),
            _line("02.00", "03.00", "Default", "Two"),
            _line("03.00", "04.00", "Sign", "Three"),
        )
    )
    output = metrics.dialogue(
        _subs(
            _line("01.00", "02.00", "Default", "Jeden"),
            _line("02.00", "03.50", "Default", "Dwa"),
            _line("03.00", "04.00", "Sign", "Trzy"),
        )
    )
    assert metrics.pair_events(source, output) == [(0, 0), (2, 2)]


def test_select_signs_keeps_typeset_sign_text_only() -> None:
    source = metrics.dialogue(
        _subs(
            _line("01.00", "02.00", "Sign", r"{\pos(10,10)}Exit"),
            _line("01.00", "02.00", "Sign", "Plain sign"),
            _line("01.00", "02.00", "Sign", r"{\pos(10,10)\p1}m 0 0 l 10 10"),
            _line("01.00", "02.00", "Default", r"{\pos(10,10)}Hello"),
            _line("01.00", "02.00", "Sign", r"{\clip(0,0,5,5)}Clipped"),
        )
    )
    output = metrics.dialogue(
        _subs(
            _line("01.00", "02.00", "Sign", r"{\pos(10,10)}Wyjście"),
            _line("01.00", "02.00", "Sign", "Zwykły szyld"),
            _line("01.00", "02.00", "Sign", r"{\pos(10,10)\p1}m 0 0 l 10 10"),
            _line("01.00", "02.00", "Default", r"{\pos(10,10)}Cześć"),
            _line("01.00", "02.00", "Sign", r"{\clip(0,0,5,5)}Przycięty"),
        )
    )
    signs = metrics.select_signs(source, output, metrics.pair_events(source, output), _VERDICTS)
    assert [(sign.source_text, sign.output_text, sign.has_clip) for sign in signs] == [
        ("Exit", "Wyjście", False),
        ("Clipped", "Przycięty", True),
    ]


def test_offscreen_px_sums_overflow_on_every_side() -> None:
    assert metrics.offscreen_px((-5, -2, 650, 370), (640, 360)) == 5 + 2 + 10 + 10
    assert metrics.offscreen_px((0, 0, 640, 360), (640, 360)) == 0


def test_concurrent_pairs_find_every_overlapping_pair_including_empty_and_reversed_spans() -> None:
    spans = [((index * 350) % 5000, (index * 350) % 5000 + (index * 530) % 1100 - 200) for index in range(300)]
    expected = {
        (first, second)
        for first, second in combinations(range(len(spans)), 2)
        if spans[first][0] < spans[second][1] and spans[second][0] < spans[first][1]
    }
    pairs = metrics.concurrent_pairs(spans)
    assert len(pairs) == len(expected)
    assert {(min(pair), max(pair)) for pair in pairs} == expected


def test_new_overlaps_ignore_overlaps_already_in_source() -> None:
    layered = _sign((0, 1000), (0, 0, 50, 20), (0, 0, 60, 20))
    border = _sign((0, 1000), (0, 0, 50, 20), (0, 0, 60, 20))
    neighbour = _sign((0, 1000), (55, 0, 90, 20), (55, 0, 90, 20))
    later = _sign((2000, 3000), (0, 0, 50, 20), (0, 0, 60, 20))
    assert metrics.new_overlaps([layered, border, neighbour, later]) == [(1, True), (1, True), (2, True), (0, True)]


def test_new_overlaps_leave_pairs_with_animated_signs_unmeasured() -> None:
    moving = _sign((0, 1000), (0, 0, 50, 20), (0, 0, 60, 20), animated=True)
    still = _sign((500, 1500), (55, 0, 90, 20), (55, 0, 90, 20))
    alone = _sign((5000, 6000), (0, 0, 50, 20), (0, 0, 60, 20), animated=True)
    assert metrics.new_overlaps([moving, still, alone]) == [(0, False), (0, False), (0, True)]


def test_new_overlaps_use_the_visible_part_of_rectangular_clips() -> None:
    clipped = _sign((0, 1000), (0, 0, 50, 20), (0, 0, 80, 20), clip=(0, 0, 50, 20))
    neighbour = _sign((0, 1000), (55, 0, 90, 20), (55, 0, 90, 20))
    assert metrics.new_overlaps([clipped, neighbour]) == [(0, True), (0, True)]


def test_sign_findings_measure_offscreen_on_visible_box_and_growth_on_full_box() -> None:
    clipped = _sign((0, 1000), (600, 0, 630, 20), (590, 0, 660, 20), clip=(0, 0, 640, 360))
    finding = metrics.sign_findings([clipped], (640, 360))[0]
    assert finding.width_ratio == pytest.approx(70 / 30)
    assert finding.new_offscreen_px == 0
    assert finding.offscreen_measured


def test_sign_findings_leave_vector_and_inverse_clips_unmeasured() -> None:
    vector = metrics.clip_rect(r"{\clip(m 0 0 l 10 0 10 10)}Text")
    inverse = metrics.clip_rect(r"{\iclip(0,0,10,10)}Text")
    sign = metrics.Sign(
        0,
        0,
        0,
        1000,
        "Sign",
        "Exit",
        "Wyjście",
        has_clip=True,
        source_box=(600, 0, 630, 20),
        output_box=(590, 0, 700, 20),
    )
    finding = metrics.sign_findings([sign], (640, 360))[0]
    assert (vector, inverse) == (None, None)
    assert finding.new_offscreen_px == 0
    assert not finding.offscreen_measured


def test_unrendered_signs_count_as_unmeasured_offscreen() -> None:
    sign = metrics.Sign(0, 0, 0, 1000, "Sign", "Exit", "Wyjście")
    finding = metrics.sign_findings([sign], (640, 360))[0]
    summary = metrics.summarise_signs([finding])
    assert not finding.offscreen_measured
    assert summary["rendered"] == 0
    assert summary["offscreen_unmeasured"] == 1


def test_clip_rect_reads_the_last_rectangular_clip() -> None:
    assert metrics.clip_rect(r"{\clip(0,0,5,5)\pos(1,1)\clip(30, 40, 10, 20)}Text") == (10, 20, 30, 40)
    assert metrics.clip_rect(r"{\pos(1,1)}Text") is None


def test_select_signs_mark_animation_and_clip_rectangles() -> None:
    source = metrics.dialogue(
        _subs(
            _line("01.00", "02.00", "Sign", r"{\move(0,0,10,10)}Moving"),
            _line("01.00", "02.00", "Sign", r"{\pos(10,10)\t(\fscx120)}Growing"),
            _line("01.00", "02.00", "Sign", r"{\fad(100,100)\pos(10,10)\clip(0,0,50,60)}Fading"),
        )
    )
    output = metrics.dialogue(
        _subs(
            _line("01.00", "02.00", "Sign", r"{\move(0,0,10,10)}Ruch"),
            _line("01.00", "02.00", "Sign", r"{\pos(10,10)\t(\fscx120)}Rośnie"),
            _line("01.00", "02.00", "Sign", r"{\fad(100,100)\pos(10,10)\clip(0,0,50,60)}Znika"),
        )
    )
    signs = metrics.select_signs(source, output, metrics.pair_events(source, output), _VERDICTS)
    assert [(sign.animated, sign.source_clip, sign.output_clip) for sign in signs] == [
        (True, None, None),
        (True, None, None),
        (False, (0, 0, 50, 60), (0, 0, 50, 60)),
    ]


def test_sign_findings_measure_growth_and_new_offscreen_extent() -> None:
    grown = _sign((0, 1000), (600, 0, 630, 20), (590, 0, 660, 20))
    finding = metrics.sign_findings([grown], (640, 360))[0]
    assert finding.width_ratio == pytest.approx(70 / 30)
    assert finding.overflow_px == 40
    assert finding.new_offscreen_px == 20
    assert finding.badness == pytest.approx(60 / 30)


def test_sign_findings_without_render_keep_length_ratio_only() -> None:
    unrendered = metrics.Sign(0, 0, 0, 1000, "Sign", "Exit", "Wyjście", False)
    finding = metrics.sign_findings([unrendered], (640, 360))[0]
    assert finding.width_ratio is None
    assert finding.length_ratio == pytest.approx(7 / 4)
    assert finding.badness == 0


def test_style_tokens_normalise_colours_and_skip_layout_tags() -> None:
    text = r"{\1c&Hffffff&\bord2\i1}a{\b1\blur3\rAlt}b{\fnArial\c&H00FF00&}c"
    assert metrics.style_tokens(text) == (r"\c&HFFFFFF", r"\i1", r"\b1", r"\rAlt", r"\fnArial", r"\c&H00FF00")


def test_emptied_spans_count_gaps_emptied_by_translation() -> None:
    assert metrics.emptied_spans(r"Why {\i1}me{\i0}?!", r"Czemu {\i1}mnie?!{\i0}") == 1
    assert metrics.emptied_spans(r"Why {\i1}me{\i0}?", r"Czemu {\i1}ja{\i0}?") == 0


def test_word_splits_count_style_tags_inside_words() -> None:
    assert metrics.word_splits(r"Czem{\i1}u mnie{\i0}?") == 1
    assert metrics.word_splits(r"Why {\i1}me{\i0}?\N{\b1}Now") == 0
    assert metrics.word_splits(r"a{\pos(1,1)}b{\i1}{\b1}c") == 1


def test_style_checks_flag_changed_tag_sequences() -> None:
    source = [_event(r"{\i1}Yes{\i0}\N{\i1}no{\i0}"), _event("Plain"), _event(r"{\b1}Bold")]
    output = [_event(r"{\i1}Tak, nie{\i0}"), _event("Zwykły"), _event(r"{\b1}Pogrubiony")]
    checks = metrics.style_checks(source, output, [(0, 0), (1, 1), (2, 2)])
    assert [(check.index, check.mismatch, check.emptied) for check in checks] == [(0, True, 0), (2, False, 0)]


def test_style_checks_flag_split_words_and_added_styles() -> None:
    source = [_event(r"Why {\i1}me{\i0}?"), _event("Plain line"), _event(r"Mid{\i1}word{\i0}")]
    output = [_event(r"Czem{\i1}u mnie{\i0}?"), _event(r"Zwykła {\i1}linia"), _event(r"Środ{\i1}ek{\i0}")]
    checks = metrics.style_checks(source, output, [(0, 0), (1, 1), (2, 2)])
    assert [(check.index, check.split_words, check.added) for check in checks] == [
        (0, True, False),
        (1, False, True),
        (2, False, False),
    ]
    assert metrics.summarise_styles(checks) == {
        "events_with_style_tags": 3,
        "tag_sequence_changed": 1,
        "emptied_span_events": 0,
        "split_word_events": 1,
        "added_style_events": 1,
    }


def test_break_check_measures_lines_orphans_and_balance() -> None:
    first = "Poszedłem z"
    second = "kolegą do kina, bo bardzo chciał zobaczyć nowy film"
    check = metrics.break_check(3, _event(first + r"\N" + second))
    assert check.lines == 2
    assert check.max_len == len(second)
    assert check.orphans == 1
    assert check.long_lines == 1
    assert check.balance == pytest.approx(len(first) / len(second))
    assert check.badness == (len(second) - metrics.MAX_LINE_CHARS) + metrics.ORPHAN_BADNESS


def test_break_checks_cover_visible_dialogue_only() -> None:
    events = metrics.dialogue(
        _subs(
            _line("01.00", "02.00", "Default", "Dialog"),
            _line("01.00", "02.00", "Sign", "Szyld"),
            _line("01.00", "02.00", "Default", r"{\i1}{\i0}"),
        )
    )
    assert [check.index for check in metrics.break_checks(events, _VERDICTS)] == [0]


def test_cps_counts_visible_characters_per_second() -> None:
    assert metrics.cps(_event(r"{\i1}Hello\Nthere", 0, 2000)) == pytest.approx(11 / 2)
    assert metrics.cps(_event("Hello", 1000, 1000)) is None
    assert metrics.cps(_event(r"{\i1}", 0, 1000)) is None


def test_summarise_cps_reports_share_above_each_limit() -> None:
    summary = metrics.summarise_cps([10.0, 16.0, 18.0, 25.0])
    assert summary["over_15"] == 0.75
    assert summary["over_17"] == 0.5
    assert summary["over_20"] == 0.25
    assert summary["max"] == 25.0


def test_classification_rows_flag_suspicious_lines() -> None:
    subs = _subs(
        _line("01.00", "03.00", "Default", "Hello there.", "Mika"),
        _line("02.00", "04.00", "Default", "SCHOOL", "Sign"),
        _line("05.00", "06.00", "Default", r"{\an8}Top line."),
        _line("05.00", "06.00", "Default", r"{\pos(320,300)}Placed."),
        _line("07.00", "08.00", "Sign", "Wait, Mika!", "Ren"),
    )
    rows = metrics.classification_rows(subs, _VERDICTS)
    assert [row.flags for row in rows] == [
        (),
        ("sign_actor_on_dialog",),
        ("top_dialog",),
        ("positioned_dialog",),
        ("named_actor_on_sign",),
    ]
    assert [row.overlaps for row in rows] == [1, 1, 1, 1, 0]
    assert rows[2].alignment == 8
    assert rows[3].top is False


def test_percentile_uses_nearest_rank() -> None:
    assert metrics.percentile([5.0, 1.0, 3.0, 2.0, 4.0], 0.9) == 5.0
    assert metrics.percentile([5.0, 1.0, 3.0, 2.0, 4.0], 0.5) == 3.0
    assert metrics.percentile([], 0.5) == 0.0
