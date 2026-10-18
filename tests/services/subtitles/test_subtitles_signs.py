from __future__ import annotations

import pytest
from pysubs2 import SSAFile

from anishift.services.subtitles import (
    SignCandidate,
    SignWeight,
    SubtitleSplit,
    inherit_split,
    sign_candidates,
    split_subtitles,
)
from anishift.services.subtitles.signs import place_weight_against, static_weights

_HEADER = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n\n"
    "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment, MarginV, Encoding\n"
    "Style: Default,Arial,32,&H00FFFFFF,0,2,20,1\n"
    "Style: Sign,Arial,28,&H0000FFFF,0,8,10,1\n"
    "Style: SignAlt,Arial,28,&H0000FFFF,0,8,10,1\n"
    "Style: OP,Arial,28,&H0000FFFF,0,8,10,1\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)

_EVENTS = (
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Good morning, everyone.\n"
    "Dialogue: 0,0:00:03.00,0:00:03.10,Sign,,0,0,0,,{\\pos(320,40)}SCHOOL GATE\n"
    "Dialogue: 0,0:00:03.10,0:00:03.20,Sign,,0,0,0,,{\\pos(321,40)}SCHOOL GATE\n"
    "Dialogue: 0,0:00:03.20,0:00:05.00,Sign,,0,0,0,,{\\pos(322,40)}SCHOOL GATE\n"
    "Dialogue: 0,0:00:03.10,0:00:05.00,SignAlt,,0,0,0,,{\\pos(320,60)}School gate\n"
    "Dialogue: 0,0:00:06.00,0:00:08.00,OP,,0,0,0,,{\\pos(320,300)}Fly away\n"
    "Dialogue: 0,0:00:06.00,0:00:08.00,Sign,,0,0,0,,{\\pos(320,300)\\k20}La la\n"
    "Dialogue: 0,0:00:09.00,0:00:10.00,Sign,,0,0,0,,{\\pos(320,300)}*sigh*\n"
    "Dialogue: 0,0:00:11.00,0:00:12.00,Default,,0,0,0,,Thank you, teacher.\n"
)


def _split() -> SubtitleSplit:
    return split_subtitles(SSAFile.from_string(_HEADER + _EVENTS), kind="ass")


def test_small_edge_sign_and_large_title_have_the_specified_static_weights() -> None:
    small: tuple[float, float] = static_weights(
        height=0.035, centre=0.0, on_screen_ms=3000, words=2, alone=True, edge=1.0, echo=False
    )
    title: tuple[float, float] = static_weights(
        height=0.12, centre=1.0, on_screen_ms=2000, words=3, alone=True, edge=0.0, echo=False
    )
    strongest: tuple[float, float] = static_weights(
        height=0.2, centre=1.0, on_screen_ms=5000, words=1, alone=True, edge=0.0, echo=False
    )

    assert small == pytest.approx((0.5408, 0.3))
    assert title == pytest.approx((0.84208, 0.0))
    assert strongest == pytest.approx((0.8824, 0.0))


@pytest.mark.parametrize(
    ("static_against", "slack", "overrun_ms", "repeat_gap_ms", "expected"),
    [
        (0.3, 3.0, -2000.0, None, 0.3),
        (0.3, 0.1, -2000.0, None, 0.636),
        (0.0, 0.1, -2000.0, None, 0.48),
        (0.0, 0.0, -2000.0, None, 0.6),
        (0.3, 3.0, 500.0, None, 0.44),
        (0.0, 3.0, 500.0, None, 0.2),
        (0.3, 3.0, -2000.0, 5000.0, 0.86),
        (0.0, 3.0, -2000.0, 5000.0, 0.8),
        (0.0, 3.0, -2000.0, 15_000.0, 0.72),
    ],
)
def test_place_weight_against_matches_the_specified_examples(
    static_against: float, slack: float, overrun_ms: float, repeat_gap_ms: float | None, expected: float
) -> None:
    assert place_weight_against(
        static_against, slack=slack, overrun_ms=overrun_ms, repeat_gap_ms=repeat_gap_ms
    ) == pytest.approx(expected)


def test_frame_by_frame_series_and_copies_in_other_styles_form_one_sign_group() -> None:
    split: SubtitleSplit = _split()
    weights: tuple[SignWeight | None, ...] = split.sign_weights

    assert len(weights) == len(split.decisions)
    assert weights[0] is None
    assert weights[8] is None
    group: SignWeight | None = weights[1]
    assert group is not None
    assert group.group == 1
    assert weights[1] == weights[2] == weights[3] == weights[4]


def test_songs_karaoke_and_sound_effects_are_never_sign_candidates() -> None:
    split: SubtitleSplit = _split()

    assert split.decisions[5:8] == ("displayed", "displayed", "displayed")
    assert split.sign_weights[5:8] == (None, None, None)


def test_sign_candidates_give_one_window_and_the_first_event_text_per_group() -> None:
    candidates: tuple[SignCandidate, ...] = sign_candidates(_split())

    assert [(candidate.group, candidate.start, candidate.end, candidate.text) for candidate in candidates] == [
        (1, 3000, 5000, "SCHOOL GATE")
    ]
    assert candidates[0].key == "school gate"


def test_translation_inherits_the_sign_weights_and_groups_of_its_source() -> None:
    source: SubtitleSplit = _split()
    polish: SSAFile = SSAFile.from_string(
        _HEADER + _EVENTS.replace("SCHOOL GATE", "BRAMA SZKOŁY").replace("School gate", "Brama szkoły")
    )

    inherited: SubtitleSplit | None = inherit_split(source, polish)

    assert inherited is not None
    assert inherited.sign_weights == source.sign_weights
    assert [candidate.text for candidate in sign_candidates(inherited)] == ["BRAMA SZKOŁY"]
