"""Stable serialized placement and streaming PCM timeline assembly."""

from __future__ import annotations

import threading
import wave
from pathlib import Path
from typing import BinaryIO, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.errors import AudioCancelledError, AudioDecodeError
from anishift.services.audio.types import (
    NormalizedClip,
    PcmStorage,
    PlacementReason,
    TimelinePlacement,
    TimelinePlan,
)

__all__ = ["plan_timeline", "write_raw_timeline"]

# ── Constants ────────────────────────────────────────────────────────────────

_COPY_BUFFER_BYTES: Final[int] = 1024 * 1024
"""Streaming copy buffer for PCM timeline assembly."""


def plan_timeline(clips: tuple[NormalizedClip, ...]) -> TimelinePlan | None:
    """Place clips stably without truncation and recover drift at natural gaps."""
    if not clips:
        return None
    first: NormalizedClip = clips[0]
    _validate_uniform_pcm(clips, first)
    ordered: tuple[NormalizedClip, ...] = tuple(
        sorted(
            clips,
            key=lambda item: (
                item.timed_clip.start_ms,
                item.timed_clip.source_order,
            ),
        ),
    )
    overlap_groups: tuple[int | None, ...] = _overlap_groups(ordered)
    placements: list[TimelinePlacement] = []
    previous_end_frame: int = 0
    for index, clip in enumerate(ordered):
        planned_start_frame: int = _ms_to_frames(clip.timed_clip.start_ms, first.sample_rate)
        actual_start_frame: int = max(planned_start_frame, previous_end_frame)
        actual_end_frame: int = actual_start_frame + clip.frame_count
        reason: PlacementReason = (
            PlacementReason.ON_TIME if actual_start_frame == planned_start_frame else PlacementReason.SERIALIZED_OVERLAP
        )
        actual_start_ms: int = _frames_to_ms(actual_start_frame, first.sample_rate)
        actual_end_ms: int = _frames_to_ms(actual_end_frame, first.sample_rate)
        placements.append(
            TimelinePlacement(
                request_id=clip.timed_clip.request_id,
                source_order=clip.timed_clip.source_order,
                planned_start_ms=clip.timed_clip.start_ms,
                planned_end_ms=clip.timed_clip.end_ms,
                actual_start_ms=actual_start_ms,
                actual_end_ms=actual_end_ms,
                drift_ms=actual_start_ms - clip.timed_clip.start_ms,
                reason=reason,
                overlap_group_id=overlap_groups[index],
                clip_duration_ms=clip.duration_ms,
                window_duration_ms=clip.timed_clip.end_ms - clip.timed_clip.start_ms,
                start_frame=actual_start_frame,
                end_frame=actual_end_frame,
            ),
        )
        previous_end_frame = actual_end_frame
    return TimelinePlan(
        clips=ordered,
        placements=tuple(placements),
        sample_rate=first.sample_rate,
        sample_width=first.sample_width,
        channels=first.channels,
        total_frames=previous_end_frame,
    )


def write_raw_timeline(
    plan: TimelinePlan,
    destination: Path,
    *,
    cancel: threading.Event | None = None,
) -> int:
    """Stream silence and clip frames into one raw PCM file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame_size: int = plan.sample_width * plan.channels
    written_frames: int = 0
    try:
        with destination.open("wb") as output:
            for clip, placement in zip(plan.clips, plan.placements, strict=True):
                _check_cancel(cancel)
                silence_frames: int = placement.start_frame - written_frames
                _write_silence(output, silence_frames, frame_size)
                written_frames += silence_frames
                copied_frames: int = _copy_clip(output, clip, frame_size, cancel)
                if copied_frames != clip.frame_count:
                    _raise_pcm("Normalized clip frame count changed during assembly")
                written_frames += copied_frames
            output.flush()
    except OSError as error:
        context: ErrorContext = ErrorContext(
            code=ErrorCode.AUDIO_FAILED,
            message="Narrator PCM timeline could not be written",
            suggestion="Check workspace permissions and free disk space.",
            details={"operation": "timeline"},
        )
        raise AudioDecodeError(context=context) from error
    if written_frames != plan.total_frames:
        _raise_pcm("Narrator PCM length does not match its timeline plan")
    return written_frames


def _copy_clip(
    output: BinaryIO,
    clip: NormalizedClip,
    frame_size: int,
    cancel: threading.Event | None,
) -> int:
    if clip.storage is PcmStorage.WAV:
        return _copy_wav(output, clip, cancel)
    copied_bytes: int = 0
    with clip.path.open("rb") as source:
        while block := source.read(_COPY_BUFFER_BYTES):
            _check_cancel(cancel)
            output.write(block)
            copied_bytes += len(block)
    if copied_bytes % frame_size:
        _raise_pcm("Raw normalized clip ends on a partial PCM frame")
    return copied_bytes // frame_size


def _copy_wav(
    output: BinaryIO,
    clip: NormalizedClip,
    cancel: threading.Event | None,
) -> int:
    copied_frames: int = 0
    with wave.open(str(clip.path), "rb") as source:
        while block := source.readframes(_COPY_BUFFER_BYTES):
            _check_cancel(cancel)
            output.write(block)
            copied_frames += len(block) // (clip.sample_width * clip.channels)
    return copied_frames


def _write_silence(output: BinaryIO, frames: int, frame_size: int) -> None:
    remaining_bytes: int = frames * frame_size
    zero_block: bytes = bytes(min(_COPY_BUFFER_BYTES, max(frame_size, remaining_bytes)))
    while remaining_bytes:
        count: int = min(remaining_bytes, len(zero_block))
        output.write(zero_block[:count])
        remaining_bytes -= count


def _overlap_groups(clips: tuple[NormalizedClip, ...]) -> tuple[int | None, ...]:
    groups: list[int | None] = [None] * len(clips)
    group_id: int = 0
    start_index: int = 0
    group_end_ms: int = clips[0].timed_clip.end_ms
    for index in range(1, len(clips)):
        clip = clips[index]
        if clip.timed_clip.start_ms < group_end_ms:
            if groups[start_index] is None:
                group_id += 1
                groups[start_index] = group_id
            groups[index] = group_id
            group_end_ms = max(group_end_ms, clip.timed_clip.end_ms)
            continue
        start_index = index
        group_end_ms = clip.timed_clip.end_ms
    return tuple(groups)


def _validate_uniform_pcm(
    clips: tuple[NormalizedClip, ...],
    expected: NormalizedClip,
) -> None:
    if any(
        (
            clip.sample_rate,
            clip.sample_width,
            clip.channels,
        )
        != (
            expected.sample_rate,
            expected.sample_width,
            expected.channels,
        )
        for clip in clips
    ):
        message: str = "Timeline clips must share one PCM format"
        raise ValueError(message)


def _ms_to_frames(milliseconds: int, sample_rate: int) -> int:
    if milliseconds < 0:
        message: str = "Timeline timestamps cannot be negative"
        raise ValueError(message)
    return (milliseconds * sample_rate + 500) // 1000


def _frames_to_ms(frames: int, sample_rate: int) -> int:
    return (frames * 1000 + sample_rate // 2) // sample_rate


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is None or not cancel.is_set():
        return
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message="Audio timeline assembly cancelled",
        suggestion="Run the file again to resume from committed artifacts.",
        details={"operation": "timeline"},
    )
    raise AudioCancelledError(context=context)


def _raise_pcm(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Regenerate normalized clips before rebuilding the narrator.",
        details={"operation": "timeline"},
    )
    raise AudioDecodeError(context=context)
