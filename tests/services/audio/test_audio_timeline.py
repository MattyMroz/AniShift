from __future__ import annotations

from pathlib import Path

from anishift.services.audio.timeline import plan_timeline, write_raw_timeline
from anishift.services.audio.types import (
    AudioFormat,
    NormalizedClip,
    PcmStorage,
    PlacementReason,
    TimedClip,
)


def test_timeline_serializes_overlap_and_recovers_at_natural_gap(tmp_path: Path) -> None:
    first = _clip(tmp_path, "first", start_ms=100, source_order=1, frames=100)
    same_start = _clip(tmp_path, "same", start_ms=100, source_order=0, frames=100)
    recovered = _clip(tmp_path, "recovered", start_ms=500, source_order=2, frames=50)

    plan = plan_timeline((first, recovered, same_start))

    assert plan is not None
    assert [item.timed_clip.request_id for item in plan.clips] == [
        "same",
        "first",
        "recovered",
    ]
    assert [item.start_frame for item in plan.placements] == [100, 200, 500]
    assert plan.placements[1].reason is PlacementReason.SERIALIZED_OVERLAP
    assert plan.placements[1].drift_ms == 100
    assert plan.placements[2].reason is PlacementReason.ON_TIME
    assert plan.placements[2].drift_ms == 0
    assert plan.placements[0].overlap_group_id == 1
    assert plan.placements[1].overlap_group_id == 1


def test_raw_timeline_streams_initial_silence_and_exact_frames(tmp_path: Path) -> None:
    first = _clip(tmp_path, "first", start_ms=10, source_order=0, frames=20, byte=b"\x01\x00")
    second = _clip(tmp_path, "second", start_ms=40, source_order=1, frames=10, byte=b"\x02\x00")
    plan = plan_timeline((first, second))
    assert plan is not None
    output = tmp_path / "narrator.pcm"

    written = write_raw_timeline(plan, output)

    assert written == 50
    assert output.stat().st_size == 100
    payload = output.read_bytes()
    assert payload[:20] == bytes(20)
    assert payload[20:60] == b"\x01\x00" * 20
    assert payload[60:80] == bytes(20)
    assert payload[80:] == b"\x02\x00" * 10


def test_timeline_empty_returns_none() -> None:
    assert plan_timeline(()) is None


def _clip(  # noqa: PLR0913
    root: Path,
    request_id: str,
    *,
    start_ms: int,
    source_order: int,
    frames: int,
    byte: bytes = b"\x01\x00",
) -> NormalizedClip:
    path = root / f"{request_id}.pcm"
    path.write_bytes(byte * frames)
    timed = TimedClip(
        request_id=request_id,
        start_ms=start_ms,
        end_ms=start_ms + 100,
        source_order=source_order,
        clip_path=path,
        clip_format=AudioFormat.WAV,
        sample_rate=1000,
        channels=1,
        duration_ms=frames,
    )
    return NormalizedClip(
        timed_clip=timed,
        path=path,
        sample_rate=1000,
        sample_width=2,
        channels=1,
        frame_count=frames,
        storage=PcmStorage.RAW,
        from_fast_path=False,
    )


def test_a_reading_of_paragraphs_pauses_between_each_pair_and_never_at_its_ends(tmp_path: Path) -> None:
    first = _clip(tmp_path, "first", start_ms=0, source_order=0, frames=400)
    second = _clip(tmp_path, "second", start_ms=0, source_order=1, frames=1500)
    third = _clip(tmp_path, "third", start_ms=0, source_order=2, frames=250)

    plan = plan_timeline((first, second, third), paragraph_pauses=True)

    assert plan is not None
    assert [item.start_frame for item in plan.placements] == [0, 700, 2500]
    assert [item.end_frame for item in plan.placements] == [400, 2200, 2750]
    gaps = [
        later.start_frame - earlier.end_frame
        for earlier, later in zip(plan.placements, plan.placements[1:], strict=False)
    ]
    assert gaps == [300, 300]
    assert plan.total_frames == 400 + 1500 + 250 + len(gaps) * 300


def test_a_single_paragraph_is_read_with_no_pause_at_all(tmp_path: Path) -> None:
    only = _clip(tmp_path, "only", start_ms=0, source_order=0, frames=400)

    plan = plan_timeline((only,), paragraph_pauses=True)

    assert plan is not None
    assert plan.placements[0].start_frame == 0
    assert plan.total_frames == 400


def test_a_reading_that_keeps_its_own_times_is_never_given_a_pause_it_did_not_ask_for(tmp_path: Path) -> None:
    first = _clip(tmp_path, "first", start_ms=100, source_order=0, frames=100)
    overlapping = _clip(tmp_path, "overlapping", start_ms=150, source_order=1, frames=50)

    plan = plan_timeline((first, overlapping))

    assert plan is not None
    assert [item.start_frame for item in plan.placements] == [100, 200]
    assert plan.total_frames == 250
