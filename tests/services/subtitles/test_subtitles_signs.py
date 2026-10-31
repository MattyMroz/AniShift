from __future__ import annotations

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.services.subtitles import (
    SignCandidate,
    SignWeight,
    SubtitleSplit,
    inherit_split,
    sign_candidates,
    split_subtitles,
)
from anishift.services.subtitles.classifier import sung
from anishift.services.subtitles.signs import SIGN_MARGIN, place_weight_against, static_weights

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
        height=0.035, centre=0.0, on_screen_ms=3000, words=2, alone=True, edge=1.0, echo=False, sound=False
    )
    title: tuple[float, float] = static_weights(
        height=0.12, centre=1.0, on_screen_ms=2000, words=3, alone=True, edge=0.0, echo=False, sound=False
    )
    strongest: tuple[float, float] = static_weights(
        height=0.2, centre=1.0, on_screen_ms=5000, words=1, alone=True, edge=0.0, echo=False, sound=False
    )

    assert small == pytest.approx((0.5408, 0.3))
    assert title == pytest.approx((0.84208, 0.0))
    assert strongest == pytest.approx((0.8824, 0.0))


def test_a_sound_written_as_a_repeated_word_keeps_even_the_strongest_sign_below_the_margin() -> None:
    weight_for, weight_against = static_weights(
        height=0.2, centre=1.0, on_screen_ms=5000, words=1, alone=True, edge=0.0, echo=False, sound=True
    )

    assert weight_against == pytest.approx(0.8)
    assert weight_for - weight_against < SIGN_MARGIN


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


_SONG_EVENTS = (
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Good morning, everyone.\n"
    "Dialogue: 0,0:00:15.00,0:00:21.00,Sign,,0,0,0,,{\\pos(320,40)}SCHOOL GATE\n"
    "Dialogue: 0,0:00:20.00,0:00:30.00,OP,,0,0,0,,Fly away\n"
    "Dialogue: 0,0:00:24.00,0:00:26.00,Sign,,0,0,0,,{\\pos(320,40)}DREAM SERIES\n"
    "Dialogue: 0,0:00:40.00,0:00:42.00,Sign,,0,0,0,,{\\pos(320,40)}y\n"
    "Dialogue: 0,0:00:50.00,0:00:52.00,Sign,,0,0,0,,{\\pos(320,40)}TUP TUP\n"
    "Dialogue: 0,0:00:55.00,0:00:57.00,Sign,,0,0,0,,{\\pos(320,40)}pik-pik pik-pik\n"
)


def test_signs_during_a_song_and_single_letters_are_never_sign_candidates() -> None:
    split: SubtitleSplit = split_subtitles(SSAFile.from_string(_HEADER + _SONG_EVENTS), kind="ass")

    assert split.decisions[1:5] == ("displayed", "displayed", "displayed", "displayed")
    assert split.sign_weights[1] is not None
    assert split.sign_weights[2:5] == (None, None, None)


@pytest.mark.parametrize(("second_verse", "candidate"), [("0:00:25.00", False), ("0:00:30.00", True)])
def test_a_sign_in_a_gap_between_verses_belongs_to_the_song_only_up_to_five_seconds(
    second_verse: str, candidate: bool
) -> None:
    events: str = (
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Good morning, everyone.\n"
        "Dialogue: 0,0:00:20.00,0:00:22.00,OP,,0,0,0,,Fly away\n"
        "Dialogue: 0,0:00:22.50,0:00:24.50,Sign,,0,0,0,,{\\pos(320,40)}DREAM SERIES\n"
        f"Dialogue: 0,{second_verse},0:00:40.00,OP,,0,0,0,,Far away\n"
    )

    split: SubtitleSplit = split_subtitles(SSAFile.from_string(_HEADER + events), kind="ass")

    assert split.decisions[2] == "displayed"
    assert (split.sign_weights[2] is not None) is candidate


def test_sounds_written_as_repeated_words_weigh_against_reading_like_a_repeat() -> None:
    split: SubtitleSplit = split_subtitles(SSAFile.from_string(_HEADER + _SONG_EVENTS), kind="ass")
    school, tup, pik = split.sign_weights[1], split.sign_weights[5], split.sign_weights[6]

    assert school is not None
    assert tup is not None
    assert pik is not None
    assert school.weight_against < 0.8
    assert tup.weight_against >= 0.8
    assert pik.weight_against >= 0.8


@pytest.mark.parametrize(
    "style",
    ["East Of Eden - Ghost Sequence [PL]", "MONSTER -  Eir Aoi [PL] 2", "The Akebosi Rockets - Meltdowner [en]"],
)
def test_style_named_artist_and_title_with_language_tag_is_a_song(style: str) -> None:
    assert sung(SSAEvent(style=style, text="W t"))


@pytest.mark.parametrize(
    "style",
    [
        "Toaru - Myśli",
        "Main - Top + Italics",
        "Re: Zero III - Retrospekcja - Myśli",
        "Dr Stone - Zapowiedź",
        "Znaki [PL]",
    ],
)
def test_style_with_a_dash_but_no_language_tag_is_not_a_song(style: str) -> None:
    assert not sung(SSAEvent(style=style, text="W trzewiach"))


def test_fragments_of_a_song_styled_artist_and_title_are_never_sign_candidates() -> None:
    events: str = (
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Good morning, everyone.\n"
        "Dialogue: 0,0:00:50.40,0:00:52.74,East Of Eden - Ghost Sequence [PL],,0,0,0,,{\\an5\\pos(557,340)}W t\n"
        "Dialogue: 0,0:00:50.45,0:00:52.78,East Of Eden - Ghost Sequence [PL],,0,0,0,,{\\an5\\pos(652,340)}rze\n"
        "Dialogue: 0,0:01:10.00,0:01:12.00,Sign,,0,0,0,,{\\pos(320,40)}SCHOOL GATE\n"
    )

    split: SubtitleSplit = split_subtitles(SSAFile.from_string(_HEADER + events), kind="ass")

    assert split.sign_weights[1:3] == (None, None)
    assert [candidate.text for candidate in sign_candidates(split)] == ["SCHOOL GATE"]


def test_sign_fragments_generated_by_kara_effector_are_never_sign_candidates() -> None:
    effect: str = "{Kara Effector 3.6 legacy: Clip Paint I [line origin: 1 - line fx: 1] \\an5\\pos(300,40)}"
    events: str = (
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Good morning, everyone.\n"
        f"Dialogue: 0,0:00:10.00,0:00:12.00,Sign,,0,0,0,,{effect}Jeś\n"
        f"Dialogue: 0,0:00:10.04,0:00:12.04,Sign,,0,0,0,,{effect}j g\n"
        "Dialogue: 0,0:01:10.00,0:01:12.00,Sign,,0,0,0,,{\\pos(320,40)}SCHOOL GATE\n"
    )

    split: SubtitleSplit = split_subtitles(SSAFile.from_string(_HEADER + events), kind="ass")

    assert split.sign_weights[1:3] == (None, None)
    assert [candidate.text for candidate in sign_candidates(split)] == ["SCHOOL GATE"]
