from __future__ import annotations

import json
import subprocess
from array import array
from typing import TYPE_CHECKING

import pytest

from anishift.paths import quality_dir
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.levels import frame_levels
from anishift.services.audio.segmentation import (
    ENVELOPE_RATE,
    CutDecision,
    LineSpan,
    clip_ranges,
    cut_points,
    server_frame_times,
)
from anishift.services.tts import DocumentPart
from anishift.services.tts.engines.elevenreader.service import part_spans
from anishift.services.tts.engines.elevenreader.types import AlignmentChunk
from anishift.text.boundaries import ends_sentence
from anishift.utils.mp3_frames import iter_frames, splice_times

if TYPE_CHECKING:
    from pathlib import Path

DATA: Path = quality_dir() / "elevenreader"
FFMPEG: Path | None = resolve_binary(Binary.FFMPEG)
QUIET: float = -60.0
SPEECH: float = -20.0
LINE: LineSpan = LineSpan(start_ms=0.0, end_ms=1000.0, open_end=False)
NEXT: LineSpan = LineSpan(start_ms=1400.0, end_ms=3000.0, open_end=False)


def _levels(total_ms: int, *pauses: tuple[int, int]) -> list[float]:
    return [QUIET if any(start <= ms < end for start, end in pauses) else SPEECH for ms in range(0, total_ms, 10)]


def _cut(levels: list[float], line: LineSpan = LINE, following: LineSpan = NEXT) -> CutDecision:
    (decision,) = cut_points(levels, server_frame_times(len(levels), (), 26.0), (line, following))
    return decision


def _chunk(row: dict[str, object]) -> AlignmentChunk:
    chars, starts, durations = row["chars"], row["start_ms"], row["dur_ms"]
    assert isinstance(chars, list)
    assert isinstance(starts, list)
    assert isinstance(durations, list)
    return AlignmentChunk(
        offset_ms=float(str(row["offset_ms"])),
        chars=tuple(str(char) for char in chars),
        starts_ms=tuple(float(str(value)) for value in starts),
        durations_ms=tuple(float(str(value)) for value in durations),
    )


def _spans(work: Path, voice: str) -> list[LineSpan]:
    rows: list[dict[str, object]] = json.loads((work / "lines.json").read_text(encoding="utf-8"))
    parts: tuple[DocumentPart, ...] = tuple(
        DocumentPart(request_id=str(index), text=str(row["text"])) for index, row in enumerate(rows)
    )
    alignment: list[str] = (work / f"anishift-test-{voice}.align.jsonl").read_text(encoding="utf-8").splitlines()
    chunks: tuple[AlignmentChunk, ...] = tuple(_chunk(json.loads(line)) for line in alignment if line)
    return [
        LineSpan(start_ms=timing.start_ms, end_ms=timing.end_ms, open_end=not ends_sentence(part.text))
        for timing, part in zip(part_spans(chunks, parts), parts, strict=True)
    ]


def _recording_cuts(work: Path, voice: str) -> list[CutDecision]:
    recording: Path = work / f"anishift-test-{voice}.mp3"
    if FFMPEG is None or not recording.is_file() or not (work / f"cuts-{voice}.json").is_file():
        pytest.skip("ElevenReader prototype data or FFmpeg is not available")
    command: list[str] = [str(FFMPEG), "-v", "error", "-f", "mp3", "-i", str(recording)]
    command += ["-ac", "1", "-ar", str(ENVELOPE_RATE), "-f", "s16le", "-"]
    pcm: array[int] = array("h", subprocess.run(command, capture_output=True, check=True).stdout)  # noqa: S603
    levels: list[float] = frame_levels(pcm, ENVELOPE_RATE)
    data: bytes = recording.read_bytes()
    times: list[float] = server_frame_times(len(levels), splice_times(data), next(iter_frames(data)).duration_ms)
    return cut_points(levels, times, _spans(work, voice))


def _prototype_cuts(work: Path, voice: str) -> list[dict[str, object]]:
    payload: dict[str, list[dict[str, object]]] = json.loads((work / f"cuts-{voice}.json").read_text(encoding="utf-8"))
    return payload["cuts"]


@pytest.mark.unit
def test_server_frame_times_splices_shift_later_frames_by_frame_duration() -> None:
    assert server_frame_times(5, (15.0, 30.0), 26.0) == [0.0, 10.0, 46.0, 82.0, 92.0]


@pytest.mark.unit
def test_server_frame_times_splice_at_frame_start_shifts_that_frame() -> None:
    assert server_frame_times(3, (10.0,), 26.0) == [0.0, 36.0, 46.0]


@pytest.mark.unit
def test_cut_points_equal_pauses_cut_in_pause_nearer_anchor() -> None:
    assert _cut(_levels(4000, (1000, 1200), (1500, 1700))) == CutDecision(at_ms=1600.0, uncertain=False)


@pytest.mark.unit
def test_cut_points_much_longer_pause_beats_pause_at_anchor() -> None:
    assert _cut(_levels(4000, (1300, 1500), (1700, 2100))) == CutDecision(at_ms=1900.0, uncertain=False)


@pytest.mark.unit
def test_cut_points_short_pause_after_closed_line_is_certain() -> None:
    assert _cut(_levels(4000, (1350, 1450))) == CutDecision(at_ms=1400.0, uncertain=False)


@pytest.mark.unit
def test_cut_points_short_pause_after_open_line_is_uncertain() -> None:
    open_line: LineSpan = LineSpan(start_ms=0.0, end_ms=1000.0, open_end=True)

    assert _cut(_levels(4000, (1350, 1450)), line=open_line).uncertain


@pytest.mark.unit
def test_cut_points_no_pause_cuts_at_anchor_uncertain() -> None:
    assert _cut(_levels(4000)) == CutDecision(at_ms=1400.0, uncertain=True)


@pytest.mark.unit
def test_cut_points_no_pause_anchor_past_window_is_clamped() -> None:
    short_next: LineSpan = LineSpan(start_ms=1010.0, end_ms=1100.0, open_end=False)

    assert _cut(_levels(4000), following=short_next) == CutDecision(at_ms=1055.0, uncertain=True)


@pytest.mark.unit
def test_cut_points_pauses_beyond_line_halves_are_ignored() -> None:
    assert _cut(_levels(4000, (400, 500), (2200, 2400))).uncertain


@pytest.mark.unit
def test_cut_points_level_count_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="server time"):
        cut_points([QUIET, QUIET], [0.0], (LINE, NEXT))


@pytest.mark.unit
def test_clip_ranges_cuts_split_recording_from_zero_to_last_frame_end() -> None:
    cuts: list[CutDecision] = [CutDecision(at_ms=1200.0, uncertain=False), CutDecision(at_ms=2500.0, uncertain=True)]

    assert clip_ranges(cuts, [0.0, 10.0, 2990.0]) == [(0.0, 1200.0), (1200.0, 2500.0), (2500.0, 3000.0)]


@pytest.mark.unit
def test_clip_ranges_no_frames_raises() -> None:
    with pytest.raises(ValueError, match="level frames"):
        clip_ranges([], [])


@pytest.mark.integration
@pytest.mark.parametrize("voice", ["fronczewski", "adam"])
def test_cut_points_tantei_recording_matches_prototype_cuts(voice: str) -> None:
    decisions: list[CutDecision] = _recording_cuts(DATA / "tantei", voice)
    prototype: list[dict[str, object]] = _prototype_cuts(DATA / "tantei", voice)
    cut: list[tuple[CutDecision, object]] = [
        (decision, row["at"]) for decision, row in zip(decisions, prototype, strict=True) if row["at"] is not None
    ]

    assert [index for index, decision in enumerate(decisions) if decision.uncertain] == [
        row["line"] for row in prototype if row["at"] is None
    ]
    assert [decision.at_ms for decision, _ in cut] == pytest.approx([at for _, at in cut], abs=10.0)


@pytest.mark.integration
@pytest.mark.parametrize("voice", ["fronczewski", "adam"])
def test_cut_points_separated_edgerunners_recording_matches_prototype_cuts(voice: str) -> None:
    decisions: list[CutDecision] = _recording_cuts(DATA / "edge02c", voice)
    prototype: list[dict[str, object]] = _prototype_cuts(DATA / "edge02c", voice)

    assert len(decisions) == 388
    assert not any(decision.uncertain for decision in decisions)
    assert [decision.at_ms for decision in decisions] == pytest.approx([row["at"] for row in prototype], abs=10.0)
