from __future__ import annotations

from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from anishift.application.sign_narration import (
    SignSelection,
    free_intervals,
    load_sign_candidates,
    reachable_signs,
    select_signs,
    write_sign_candidates,
)
from anishift.services.audio.timeline import plan_timeline
from anishift.services.audio.types import AudioFormat, NormalizedClip, TimedClip, TimelinePlan
from anishift.services.subtitles import SignCandidate
from anishift.services.subtitles.signs import static_weights

_SMALL: tuple[float, float] = (0.5408, 0.3)

_TITLE: tuple[float, float] = (0.84208, 0.0)

_STRONGEST: tuple[float, float] = (0.8824, 0.0)

_PLATES: tuple[SignCandidate, ...] = (
    SignCandidate(47, 221_740, 223_950, "Destra, Dar: Bliźniaczy Szermierz (S)", "destra", 0.6762, 0.1111),
    SignCandidate(49, 223_990, 226_450, "Sinistra, Dar: Bliźniaczy Szermierz (S)", "sinistra", 0.6868, 0.1111),
    SignCandidate(51, 226_490, 228_830, "Rory, Dar: Zwiadowca Superwysokiego Poziomu (A)", "rory", 0.6655, 0.1111),
    SignCandidate(53, 228_870, 231_460, "Celica, Dar: Uzdrowicielka Wysokiego Poziomu (B)", "celica", 0.6767, 0.1111),
    SignCandidate(55, 231_500, 233_960, "Shannon, Dar: Mag Superwysokiego Poziomu (A)", "shannon", 0.6709, 0.1111),
)


def _clip(request_id: str, start_ms: int, frames: int, order: int, sample_rate: int = 1000) -> NormalizedClip:
    duration_ms: int = frames * 1000 // sample_rate
    timed: TimedClip = TimedClip(
        request_id,
        start_ms,
        start_ms + duration_ms,
        order,
        Path(f"{request_id}.mp3"),
        AudioFormat.MP3,
        sample_rate,
        1,
        duration_ms,
    )
    return NormalizedClip(timed, Path(f"{request_id}.pcm"), sample_rate, 2, 1, frames)


def _sign(group: int, start: int, end: int, weights: tuple[float, float] = _SMALL, key: str = "gate") -> SignCandidate:
    return SignCandidate(group, start, end, "Brama", key, *weights)


def _recordings(*groups: int, frames: int = 1000, sample_rate: int = 1000) -> dict[int, NormalizedClip]:
    return {group: _clip(f"sign-{group}", 0, frames, group, sample_rate) for group in groups}


def _decision(selection: SignSelection, group: int) -> str:
    return dict(selection.decisions)[group]


def _margin(selection: SignSelection, group: int) -> float:
    return dict(selection.margins)[group]


def test_a_sign_is_read_in_the_pause_before_the_line_inside_its_window() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 5000, 1000, 10),)

    selection: SignSelection = select_signs((_sign(3, 1000, 4000),), _recordings(3), lines, "smart")

    assert _decision(selection, 3) == "read"
    assert [(item.group, item.start_ms, item.end_ms) for item in selection.placements] == [(3, 1000, 2000)]


def test_a_sign_is_read_after_the_line_when_only_that_pause_is_free() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 3000, 0),)

    selection: SignSelection = select_signs((_sign(3, 1000, 2500, (0.9, 0.0)),), _recordings(3), lines, "smart")

    assert _decision(selection, 3) == "read"
    assert selection.placements[0].start_ms == 3200


def test_a_sign_without_a_pause_is_not_read_and_lines_keep_their_places() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 3000, 0), _clip("line-2", 3000, 3000, 1))

    selection: SignSelection = select_signs((_sign(3, 1000, 2000, (0.9, 0.0)),), _recordings(3), lines, "smart")

    assert _decision(selection, 3) == "no_pause"
    assert selection.placements == ()


def test_example_a_reads_a_small_sign_in_a_long_pause() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 800, 0), _clip("line-2", 5200, 800, 10))

    selection: SignSelection = select_signs((_sign(3, 1000, 4000),), _recordings(3), lines, "smart")

    assert _decision(selection, 3) == "read"
    assert _margin(selection, 3) == pytest.approx(0.2408)


def test_example_b_skips_a_small_sign_in_a_tight_pause() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 800, 0), _clip("line-2", 2300, 10_000, 10))

    selection: SignSelection = select_signs((_sign(3, 1000, 4000),), _recordings(3), lines, "smart")

    assert _decision(selection, 3) == "weight"
    assert _margin(selection, 3) == pytest.approx(0.5408 - 0.636)


def test_example_c_reads_a_large_title_in_the_same_tight_pause() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 800, 0), _clip("line-2", 2300, 10_000, 10))

    selection: SignSelection = select_signs((_sign(3, 1000, 4000, _TITLE),), _recordings(3), lines, "smart")

    assert _decision(selection, 3) == "read"
    assert _margin(selection, 3) == pytest.approx(0.84208 - 0.48)


def test_a_later_pause_that_passes_the_margin_wins_over_an_earlier_one_that_only_fits() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 800, 0), _clip("line-2", 2300, 800, 10))

    selection: SignSelection = select_signs((_sign(3, 1000, 4000),), _recordings(3), lines, "smart")

    assert _decision(selection, 3) == "read"
    assert selection.placements[0].start_ms == 3300


@pytest.mark.parametrize(
    ("weights", "margin"),
    [(_SMALL, 0.5408 - 0.86), (_TITLE, 0.84208 - 0.8), (_STRONGEST, 0.0824)],
)
def test_a_sign_read_five_seconds_earlier_is_not_read_again(weights: tuple[float, float], margin: float) -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 100_000, 800, 50),)
    candidates: tuple[SignCandidate, ...] = (_sign(3, 1000, 4000, weights), _sign(7, 6000, 9000, weights))

    selection: SignSelection = select_signs(candidates, _recordings(3, 7), lines, "smart")

    assert _decision(selection, 3) == "read"
    assert _decision(selection, 7) == "weight"
    assert _margin(selection, 7) == pytest.approx(margin, abs=1e-4)


def test_the_strongest_sign_is_read_again_fifteen_seconds_later() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 100_000, 800, 50),)
    candidates: tuple[SignCandidate, ...] = (_sign(3, 1000, 4000, _STRONGEST), _sign(7, 16_000, 19_000, _STRONGEST))

    selection: SignSelection = select_signs(candidates, _recordings(3, 7), lines, "smart")

    assert _decision(selection, 7) == "read"
    assert _margin(selection, 7) == pytest.approx(0.1624, abs=1e-4)


def test_a_rejected_sign_does_not_count_as_a_repeat() -> None:
    lines: tuple[NormalizedClip, ...] = (
        _clip("line-1", 0, 800, 0),
        _clip("line-2", 2300, 10_000, 10),
        _clip("line-3", 30_000, 800, 20),
    )
    candidates: tuple[SignCandidate, ...] = (_sign(3, 1000, 4000), _sign(15, 13_000, 16_000))

    selection: SignSelection = select_signs(candidates, _recordings(3, 15), lines, "smart")

    assert _decision(selection, 3) == "weight"
    assert _decision(selection, 15) == "read"
    assert _margin(selection, 15) == pytest.approx(0.2408)


def test_always_reads_a_sign_smart_rejects_for_its_weight() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 800, 0), _clip("line-2", 2300, 10_000, 10))

    selection: SignSelection = select_signs((_sign(3, 1000, 4000),), _recordings(3), lines, "always")

    assert _decision(selection, 3) == "read"
    assert selection.placements[0].start_ms == 1000


def test_always_reads_in_the_same_span_after_the_sign_window_as_smart() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 3000, 0),)

    selection: SignSelection = select_signs((_sign(3, 1000, 2500, (0.9, 0.0)),), _recordings(3), lines, "always")

    assert _decision(selection, 3) == "read"
    assert selection.placements[0].start_ms == 3200


def test_always_never_reads_past_three_seconds_after_the_sign_window() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 3000, 0),)

    selection: SignSelection = select_signs((_sign(3, 0, 500, (0.9, 0.0)),), _recordings(3), lines, "always")

    assert _decision(selection, 3) == "no_pause"


@pytest.mark.parametrize(("mode", "decision"), [("smart", "weight"), ("always", "read")])
def test_a_sound_written_as_a_repeated_word_is_read_only_in_always(mode: str, decision: str) -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 100_000, 800, 50),)
    weights: tuple[float, float] = static_weights(
        height=0.12, centre=1.0, on_screen_ms=2000, words=2, alone=True, edge=0.0, echo=False, sound=True
    )

    selection: SignSelection = select_signs((_sign(3, 1000, 3000, weights, "tup tup"),), _recordings(3), lines, mode)

    assert _decision(selection, 3) == decision


@pytest.mark.parametrize("mode", ["smart", "always"])
def test_a_run_of_plates_longer_to_read_than_to_show_is_read_plate_after_plate(mode: str) -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 217_560, 3880, 0), _clip("line-2", 238_000, 2000, 60))

    selection: SignSelection = select_signs(_PLATES, _recordings(47, 49, 51, 53, 55, frames=2600), lines, mode)

    assert selection.decisions == ((47, "read"), (49, "read"), (51, "read"), (53, "read"), (55, "read"))
    assert [(item.start_ms, item.end_ms) for item in selection.placements] == [
        (221_740, 224_340),
        (224_540, 227_140),
        (227_340, 229_940),
        (230_140, 232_740),
        (232_940, 235_540),
    ]


@pytest.mark.parametrize("mode", ["smart", "always"])
def test_a_run_of_plates_cut_short_by_a_line_is_read_from_its_first_plate_without_gaps(mode: str) -> None:
    lines: tuple[NormalizedClip, ...] = (
        _clip("line-1", 217_560, 3880, 0),
        _clip("line-2", 234_170, 2780, 60),
        _clip("line-3", 236_950, 3890, 61),
    )

    selection: SignSelection = select_signs(_PLATES, _recordings(47, 49, 51, 53, 55, frames=3000), lines, mode)

    assert selection.decisions == ((47, "read"), (49, "read"), (51, "read"), (53, "no_pause"), (55, "run"))
    assert [(item.start_ms, item.end_ms) for item in selection.placements] == [
        (221_740, 224_740),
        (224_940, 227_940),
        (228_140, 231_140),
    ]


def test_a_plate_without_a_recording_leaves_the_rest_of_its_run_to_be_read() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 217_560, 3880, 0), _clip("line-2", 238_000, 2000, 60))

    selection: SignSelection = select_signs(_PLATES, _recordings(47, 51, 53, 55, frames=2600), lines, "smart")

    assert selection.decisions == ((47, "read"), (49, "missing"), (51, "read"), (53, "read"), (55, "read"))


def test_a_plate_hidden_by_a_line_is_reachable_while_its_run_lasts() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 5200, 0),)
    candidates: tuple[SignCandidate, ...] = (_sign(3, 1000, 2000, key="a"), _sign(4, 2040, 3000, key="b"))
    baseline: TimelinePlan | None = plan_timeline(lines)

    assert baseline is not None
    assert reachable_signs(candidates, free_intervals(baseline), baseline.sample_rate) == candidates


def test_a_sign_without_a_recording_is_missing() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 5000, 1000, 10),)

    selection: SignSelection = select_signs((_sign(3, 1000, 4000),), {}, lines, "smart")

    assert _decision(selection, 3) == "missing"


def test_read_signs_never_move_a_line_even_after_rounding_frames_to_milliseconds() -> None:
    rate: int = 24_000
    lines: tuple[NormalizedClip, ...] = (
        _clip("line-1", 1003, 24_011, 10, rate),
        _clip("line-2", 4001, 36_007, 20, rate),
        _clip("line-3", 4500, 12_001, 30, rate),
        _clip("line-4", 12_007, 24_013, 40, rate),
    )
    candidates: tuple[SignCandidate, ...] = (
        _sign(1, 0, 3000, (0.9, 0.0), "a"),
        _sign(2, 6000, 9000, (0.9, 0.0), "b"),
        _sign(5, 7000, 10_000, (0.9, 0.0), "c"),
    )
    recordings: dict[int, NormalizedClip] = {
        group: _clip(f"sign-{group}", 0, 17_777, group, rate) for group in (1, 2, 5)
    }

    selection: SignSelection = select_signs(candidates, recordings, lines, "always")
    read: tuple[NormalizedClip, ...] = tuple(
        replace(
            recordings[item.group],
            timed_clip=replace(recordings[item.group].timed_clip, start_ms=item.start_ms, end_ms=item.end_ms),
        )
        for item in selection.placements
    )
    alone: TimelinePlan | None = plan_timeline(lines)
    together: TimelinePlan | None = plan_timeline((*lines, *read))

    assert len(read) == 3
    assert alone is not None
    assert together is not None
    by_id = {item.request_id: item for item in together.placements}
    for placement in alone.placements:
        moved = by_id[placement.request_id]
        assert (moved.start_frame, moved.actual_start_ms, moved.drift_ms) == (
            placement.start_frame,
            placement.actual_start_ms,
            placement.drift_ms,
        )
    starts: list[tuple[int, int]] = sorted((item.start_frame, item.end_frame) for item in together.placements)
    assert all(end <= next_start for (_, end), (next_start, _) in pairwise(starts))


@pytest.mark.parametrize(("frames", "decision"), [(14_399, "no_pause"), (14_376, "read")])
def test_a_read_sign_keeps_a_full_breath_after_its_start_is_rounded_to_milliseconds(frames: int, decision: str) -> None:
    rate: int = 24_000
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 24_001, 10, rate), _clip("line-2", 2000, 120_000, 20, rate))
    recordings: dict[int, NormalizedClip] = {3: _clip("sign-3", 0, frames, 3, rate)}

    selection: SignSelection = select_signs((_sign(3, 1000, 1900, (0.9, 0.0)),), recordings, lines, "always")
    read: tuple[NormalizedClip, ...] = tuple(
        replace(recordings[3], timed_clip=replace(recordings[3].timed_clip, start_ms=item.start_ms, end_ms=item.end_ms))
        for item in selection.placements
    )
    together: TimelinePlan | None = plan_timeline((*lines, *read))

    assert _decision(selection, 3) == decision
    assert together is not None
    spans: list[tuple[int, int]] = sorted((item.start_frame, item.end_frame) for item in together.placements)
    assert all(next_start - end >= 4800 for (_, end), (next_start, _) in pairwise(spans))


def test_the_same_inputs_always_give_the_same_selection() -> None:
    lines: tuple[NormalizedClip, ...] = (_clip("line-1", 0, 800, 0), _clip("line-2", 2300, 800, 10))
    candidates: tuple[SignCandidate, ...] = (_sign(3, 1000, 4000), _sign(7, 1200, 4500, _TITLE, "title"))

    first: SignSelection = select_signs(candidates, _recordings(3, 7), lines, "smart")
    second: SignSelection = select_signs(candidates, _recordings(3, 7), lines, "smart")

    assert first == second


def test_sign_candidates_survive_their_private_file(tmp_path: Path) -> None:
    candidates: tuple[SignCandidate, ...] = (_sign(3, 1000, 4000), _sign(7, 1200, 4500, _TITLE, "title"))

    path: Path = write_sign_candidates(candidates, tmp_path / "signs.json")

    assert load_sign_candidates(path) == candidates
