"""Per-clip conversion to the narrator timeline's PCM format."""

from __future__ import annotations

import math
import os
import tempfile
import threading
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.commands import CommandRunner, PcmTarget, normalize_command
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import AudioCancelledError, AudioDecodeError
from anishift.services.audio.levels import FRAME_MS, frame_levels, speech_bounds
from anishift.services.audio.types import NormalizedClip, TimedClip

__all__ = [
    "EDGE_TRIM_DBFS",
    "EDGE_TRIM_MARGIN_MS",
    "NormalizationContext",
    "atempo_chain",
    "normalize_clip",
]

# ── Constants ────────────────────────────────────────────────────────────────

_MIN_ATEMPO: Final[float] = 0.5
"""Smallest factor emitted as one FFmpeg atempo stage."""

_MAX_ATEMPO: Final[float] = 2.0
"""Largest factor emitted as one FFmpeg atempo stage."""

_TEMPO_EPSILON: Final[float] = 1e-9
"""Tolerance for recognizing a neutral tempo."""

_PCM_S16LE_WIDTH: Final[int] = 2
"""Byte width of signed 16-bit PCM samples."""

_MS_PER_SECOND: Final[int] = 1000
"""Milliseconds in one second."""

EDGE_TRIM_DBFS: Final[float] = -45.0
"""Frame level above which a clip edge counts as speech."""

EDGE_TRIM_MARGIN_MS: Final[float] = 30.0
"""Audio kept outside the outermost speech frames to avoid clicks."""


@dataclass(frozen=True, slots=True)
class NormalizationContext:
    """Process dependencies shared by clip normalization calls."""

    config: AudioConfig
    ffmpeg: Path
    runner: CommandRunner
    cancel: threading.Event | None = None
    reuse_existing: bool = False


def atempo_chain(tempo: float) -> tuple[float, ...]:
    """Split a positive tempo into deterministic FFmpeg-safe stages."""
    if not math.isfinite(tempo) or tempo <= 0:
        message: str = "Post-process tempo must be finite and positive"
        raise ValueError(message)
    if math.isclose(tempo, 1.0, abs_tol=_TEMPO_EPSILON):
        return ()

    remaining: float = tempo
    stages: list[float] = []
    while remaining > _MAX_ATEMPO:
        stages.append(_MAX_ATEMPO)
        remaining /= _MAX_ATEMPO
    while remaining < _MIN_ATEMPO:
        stages.append(_MIN_ATEMPO)
        remaining /= _MIN_ATEMPO
    if not math.isclose(remaining, 1.0, abs_tol=_TEMPO_EPSILON):
        stages.append(remaining)
    return tuple(stages)


def normalize_clip(
    clip: TimedClip,
    destination: Path,
    *,
    tempo: float,
    context: NormalizationContext,
) -> NormalizedClip:
    """Convert one source clip to edge-trimmed raw PCM atomically, or reuse the cached artifact."""
    sample_rate: int = context.config.narrator_sample_rate
    sample_width: int = context.config.narrator_sample_width
    channels: int = context.config.narrator_channels
    cancel: threading.Event | None = context.cancel
    _validate_target(sample_rate=sample_rate, sample_width=sample_width, channels=channels)
    if cancel is not None and cancel.is_set():
        _raise_cancelled(clip.request_id)
    cached: NormalizedClip | None = _cached_raw_pcm(
        clip,
        destination,
        context=context,
    )
    if cached is not None:
        return cached

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int
    raw_path: str
    descriptor, raw_path = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}-",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary: Path = Path(raw_path)
    stages: tuple[float, ...] = atempo_chain(tempo)
    tempo_filter: str | None = ",".join(f"atempo={_format_factor(stage)}" for stage in stages) if stages else None
    try:
        context.runner.run(
            normalize_command(
                context.ffmpeg,
                clip.clip_path,
                temporary,
                target=PcmTarget(sample_rate=sample_rate, channels=channels),
                tempo_filter=tempo_filter,
            ),
            operation="normalize_clip",
            timeout_s=context.config.operation_timeout_s,
            cancel=cancel,
        )
        if cancel is not None and cancel.is_set():
            _raise_cancelled(clip.request_id)
        frame_size: int = sample_width * channels
        size: int = temporary.stat().st_size
        if size <= 0 or size % frame_size:
            _raise_invalid_pcm(clip.request_id)
        _trim_edges(temporary, sample_rate)
        temporary.replace(destination)
    except OSError as error:
        error_context: ErrorContext = ErrorContext(
            code=ErrorCode.AUDIO_FAILED,
            message="Normalized PCM artifact could not be committed",
            suggestion="Check workspace permissions and free disk space.",
            details={"operation": "normalize_clip", "request_id": clip.request_id},
        )
        raise AudioDecodeError(context=error_context) from error
    finally:
        temporary.unlink(missing_ok=True)

    frame_count: int = destination.stat().st_size // (sample_width * channels)
    return NormalizedClip(
        timed_clip=clip,
        path=destination,
        sample_rate=sample_rate,
        sample_width=sample_width,
        channels=channels,
        frame_count=frame_count,
    )


def _cached_raw_pcm(
    clip: TimedClip,
    path: Path,
    *,
    context: NormalizationContext,
) -> NormalizedClip | None:
    if not context.reuse_existing or not path.is_file() or path.is_symlink():
        return None
    sample_rate: int = context.config.narrator_sample_rate
    sample_width: int = context.config.narrator_sample_width
    channels: int = context.config.narrator_channels
    frame_size: int = sample_width * channels
    size: int = path.stat().st_size
    if size <= 0 or size % frame_size:
        return None
    return NormalizedClip(
        timed_clip=clip,
        path=path,
        sample_rate=sample_rate,
        sample_width=sample_width,
        channels=channels,
        frame_count=size // frame_size,
    )


def _trim_edges(path: Path, sample_rate: int) -> None:
    samples: array[int] = array("h")
    samples.frombytes(path.read_bytes())
    bounds: tuple[int, int] | None = speech_bounds(frame_levels(samples, sample_rate), EDGE_TRIM_DBFS)
    if bounds is None:
        return
    first, last = bounds
    start_ms: float = first * FRAME_MS - EDGE_TRIM_MARGIN_MS
    end_ms: float = (last + 1) * FRAME_MS + EDGE_TRIM_MARGIN_MS
    start: int = max(0, round(start_ms * sample_rate / _MS_PER_SECOND))
    end: int = min(len(samples), round(end_ms * sample_rate / _MS_PER_SECOND))
    path.write_bytes(samples[start:end].tobytes())


def _validate_target(*, sample_rate: int, sample_width: int, channels: int) -> None:
    whole_frames: bool = sample_rate * FRAME_MS % _MS_PER_SECOND == 0
    if sample_rate <= 0 or not whole_frames or sample_width != _PCM_S16LE_WIDTH or channels != 1:
        message: str = "Narrator target must be mono PCM S16LE at a sample rate split into whole 10 ms frames"
        raise ValueError(message)


def _format_factor(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _raise_invalid_pcm(request_id: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message="FFmpeg produced invalid normalized PCM",
        suggestion="Inspect the source clip and FFmpeg diagnostics.",
        details={"operation": "normalize_clip", "request_id": request_id},
    )
    raise AudioDecodeError(context=context)


def _raise_cancelled(request_id: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message="Audio clip normalization cancelled",
        suggestion="Run the file again to resume from committed artifacts.",
        details={"operation": "normalize_clip", "request_id": request_id},
    )
    raise AudioCancelledError(context=context)
