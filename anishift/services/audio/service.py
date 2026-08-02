"""Synchronous facade for narration assembly and final sidecar rendering."""

from __future__ import annotations

import hashlib
import math
import os
import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final, Never, Protocol

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, BinaryNotFoundError, require_binary
from anishift.services.audio.channels import build_channel_plan
from anishift.services.audio.commands import CommandRunner, SubprocessRunner, narrator_wav_command
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import (
    AudioCancelledError,
    AudioConfigError,
    AudioDecodeError,
    AudioProbeError,
    AudioProcessError,
)
from anishift.services.audio.fingerprint import (
    mix_fingerprint,
    narration_fingerprint,
    normalization_fingerprint,
)
from anishift.services.audio.normalize import NormalizationContext, normalize_clip
from anishift.services.audio.output import (
    RenderInputs,
    mixed_audio_path,
    render_command,
    validate_output_probe,
)
from anishift.services.audio.probe import (
    measure_audio_duration,
    probe_audio,
    validate_decode,
)
from anishift.services.audio.resume import AudioResumeRepository
from anishift.services.audio.timeline import plan_timeline, write_raw_timeline
from anishift.services.audio.types import (
    AudioProbe,
    AudioRenderRequest,
    AudioRenderResult,
    AudioRenderStatus,
    ChannelPlan,
    NormalizedClip,
    TimedClip,
    TimelinePlan,
)
from anishift.utils.logger import get_logger

__all__ = ["AudioProgressSink", "AudioService"]

# ── Constants ────────────────────────────────────────────────────────────────

_NARRATOR_DURATION_TOLERANCE_MS: Final[int] = 2
"""Maximum narrator WAV duration rounding difference."""

_SAFE_SCOPE: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z",
)
"""Safe opaque scope syntax shared at the Audio boundary."""

_WINDOWS_DEVICE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "AUX",
        "CON",
        "NUL",
        "PRN",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    },
)
"""Reserved Windows path segments rejected on every platform."""

logger = get_logger(__name__)


class AudioProgressSink(Protocol):
    """Optional phase callback owned and rendered by the pipeline."""

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        """Report a coarse audio-domain phase without rendering UI."""
        ...


class AudioService:
    """Render normalized clips through narrator WAV to one validated sidecar."""

    def __init__(
        self,
        config: AudioConfig,
        *,
        runner: CommandRunner | None = None,
        ffmpeg: Path | None = None,
        ffprobe: Path | None = None,
    ) -> None:
        """Resolve process dependencies and retain immutable audio settings."""
        self._config: AudioConfig = config
        self._runner: CommandRunner = runner or SubprocessRunner(
            shutdown_grace_s=config.shutdown_grace_s,
        )
        try:
            self._ffmpeg: Path = ffmpeg or require_binary(Binary.FFMPEG)
            self._ffprobe: Path = ffprobe or require_binary(Binary.FFPROBE)
        except BinaryNotFoundError as error:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.BINARY_NOT_FOUND,
                message="Audio rendering requires FFmpeg and FFprobe",
                suggestion="Run `anishift setup` to install the audio binaries.",
                details={"operation": "audio_config"},
            )
            raise AudioConfigError(context=context) from error
        self._normalization_slots: threading.BoundedSemaphore = threading.BoundedSemaphore(
            config.normalization_concurrency,
        )

    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        """Build and atomically commit one final audio sidecar."""
        _validate_request(request)
        logger.info(
            "Audio render started",
            scope_id=request.scope_id,
            clip_count=len(request.clips),
            codec=self._config.codec_profile.value,
            has_original=request.source_audio_path is not None,
        )
        if not request.clips:
            _notify(callbacks, request.scope_id, "skipped_no_spoken")
            logger.info("Audio render skipped", scope_id=request.scope_id, reason="no_spoken_clips")
            return AudioRenderResult(
                scope_id=request.scope_id,
                status=AudioRenderStatus.SKIPPED_NO_SPOKEN,
                narrator_path=None,
                output_path=None,
                output_probe=None,
                placements=(),
                warnings=(),
                narration_fingerprint=None,
                mix_fingerprint=None,
            )
        repository: AudioResumeRepository = AudioResumeRepository(
            request.temporary_root,
            request.scope_id,
        )
        _check_cancel(cancel)
        narration_id: str = narration_fingerprint(
            scope_id=request.scope_id,
            clips=request.clips,
            post_process_tempo=request.post_process_tempo,
            config=self._config,
        )
        narrator_path, plan, narrator_probe = self._narrator(
            request,
            repository,
            narration_id,
            callbacks=callbacks,
            cancel=cancel,
        )
        original_probe: AudioProbe | None = self._probe_original(request, cancel=cancel)
        original_duration_ms: int = self._measure_original_duration(
            request,
            cancel=cancel,
        )
        channel_plan: ChannelPlan = build_channel_plan(
            self._config.codec_profile,
            original_probe.channel_layout if original_probe is not None else "mono",
        )
        mix_id: str = mix_fingerprint(
            narration_fingerprint_value=narration_id,
            narrator_path=narrator_path,
            original_audio_path=request.source_audio_path,
            channel_plan=channel_plan,
            config=self._config,
        )
        destination: Path = mixed_audio_path(
            request.source_path,
            self._config.codec_profile,
        )
        expected_duration_ms: int = max(
            narrator_probe.duration_ms,
            original_duration_ms,
        )
        hit_probe: AudioProbe | None = self._output_hit(
            repository,
            destination,
            mix_id,
            channel_plan,
            expected_duration_ms,
            cancel=cancel,
        )
        if hit_probe is not None:
            _notify(callbacks, request.scope_id, "done")
            logger.info(
                "Audio render resumed",
                scope_id=request.scope_id,
                duration_ms=hit_probe.duration_ms,
                channel_layout=hit_probe.channel_layout,
            )
            return _result(
                request,
                status=AudioRenderStatus.RESUME_HIT,
                narrator_path=narrator_path,
                output_path=destination,
                output_probe=hit_probe,
                plan=plan,
                channel_plan=channel_plan,
                narration_id=narration_id,
                mix_id=mix_id,
            )
        _notify(callbacks, request.scope_id, "mixing")
        output_probe: AudioProbe = self._render_output(
            request,
            repository,
            narrator_path,
            destination,
            channel_plan,
            expected_duration_ms,
            mix_id,
            cancel=cancel,
        )
        _notify(callbacks, request.scope_id, "done")
        logger.info(
            "Audio render completed",
            scope_id=request.scope_id,
            duration_ms=output_probe.duration_ms,
            channel_layout=output_probe.channel_layout,
        )
        return _result(
            request,
            status=AudioRenderStatus.COMPLETED,
            narrator_path=narrator_path,
            output_path=destination,
            output_probe=output_probe,
            plan=plan,
            channel_plan=channel_plan,
            narration_id=narration_id,
            mix_id=mix_id,
        )

    def _narrator(
        self,
        request: AudioRenderRequest,
        repository: AudioResumeRepository,
        narration_id: str,
        *,
        callbacks: AudioProgressSink | None,
        cancel: threading.Event | None,
    ) -> tuple[Path, TimelinePlan | None, AudioProbe]:
        hit: Path | None = repository.narration_hit(narration_id)
        if hit is not None:
            hit_probe: AudioProbe | None = self._valid_narrator_hit(hit, cancel=cancel)
            if hit_probe is not None:
                _notify(callbacks, request.scope_id, "narration_resume")
                return hit, None, hit_probe
        _notify(callbacks, request.scope_id, "normalizing")
        normalized: tuple[NormalizedClip, ...] = self._normalize_many(
            request,
            cancel=cancel,
        )
        plan: TimelinePlan | None = plan_timeline(normalized)
        if plan is None:
            _raise_decode("Narration timeline unexpectedly contains no clips")
        _notify(callbacks, request.scope_id, "timeline")
        narration_dir: Path = repository.narration_dir
        raw_pcm: Path = narration_dir / f"{_digest_name(narration_id)}.pcm"
        temporary_pcm: Path = raw_pcm.with_name(f".{raw_pcm.name}.tmp")
        try:
            write_raw_timeline(plan, temporary_pcm, cancel=cancel)
            _check_cancel(cancel)
            temporary_pcm.replace(raw_pcm)
        finally:
            temporary_pcm.unlink(missing_ok=True)
        narrator_path: Path = narration_dir / "narrator.wav"
        temporary_wav: Path = _temporary_sibling(narrator_path)
        try:
            self._runner.run(
                narrator_wav_command(
                    self._ffmpeg,
                    raw_pcm,
                    temporary_wav,
                    sample_rate=plan.sample_rate,
                    channels=plan.channels,
                ),
                operation="wrap_narrator",
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            probe: AudioProbe = probe_audio(
                temporary_wav,
                ffprobe=self._ffprobe,
                runner=self._runner,
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            _validate_narrator_probe(probe, plan)
            _check_cancel(cancel)
            temporary_wav.replace(narrator_path)
            repository.commit_narration(narration_id, narrator_path)
        finally:
            temporary_wav.unlink(missing_ok=True)
        return narrator_path, plan, probe

    def _normalize_many(
        self,
        request: AudioRenderRequest,
        *,
        cancel: threading.Event | None,
    ) -> tuple[NormalizedClip, ...]:
        worker_count: int = min(
            len(request.clips),
            self._config.normalization_concurrency,
        )

        def normalize_one(clip: TimedClip) -> NormalizedClip:
            return self.prepare_clip(
                clip,
                temporary_root=request.temporary_root,
                tempo=request.post_process_tempo,
                cancel=cancel,
            )

        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="anishift-audio-normalize",
        ) as executor:
            return tuple(executor.map(normalize_one, request.clips))

    def prepare_clip(
        self,
        clip: TimedClip,
        *,
        temporary_root: Path,
        tempo: float,
        cancel: threading.Event | None,
    ) -> NormalizedClip:
        """Normalize one committed TTS clip into its reusable audio artifact."""
        normalized_dir: Path = temporary_root / "narration" / "normalized"
        key: str = _digest_name(
            normalization_fingerprint(
                clip,
                post_process_tempo=tempo,
                config=self._config,
            ),
        )
        with self._normalization_slots:
            return normalize_clip(
                clip,
                normalized_dir / f"{key}.pcm",
                tempo=tempo,
                context=NormalizationContext(
                    config=self._config,
                    ffmpeg=self._ffmpeg,
                    runner=self._runner,
                    cancel=cancel,
                    reuse_existing=True,
                ),
            )

    def _valid_narrator_hit(
        self,
        path: Path,
        *,
        cancel: threading.Event | None,
    ) -> AudioProbe | None:
        try:
            probe: AudioProbe = probe_audio(
                path,
                ffprobe=self._ffprobe,
                runner=self._runner,
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            validate_decode(
                path,
                ffmpeg=self._ffmpeg,
                runner=self._runner,
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
        except AudioDecodeError, AudioProbeError, AudioProcessError:
            return None
        if (
            probe.codec_name == "pcm_s16le"
            and probe.sample_rate == self._config.narrator_sample_rate
            and probe.channels == self._config.narrator_channels
        ):
            return probe
        return None

    def _probe_original(
        self,
        request: AudioRenderRequest,
        *,
        cancel: threading.Event | None,
    ) -> AudioProbe | None:
        if request.source_audio_path is None:
            return None
        return probe_audio(
            request.source_audio_path,
            ffprobe=self._ffprobe,
            runner=self._runner,
            timeout_s=self._config.operation_timeout_s,
            cancel=cancel,
        )

    def _measure_original_duration(
        self,
        request: AudioRenderRequest,
        *,
        cancel: threading.Event | None,
    ) -> int:
        if request.source_audio_path is None:
            return 0
        return measure_audio_duration(
            request.source_audio_path,
            ffmpeg=self._ffmpeg,
            runner=self._runner,
            timeout_s=self._config.operation_timeout_s,
            cancel=cancel,
        )

    def _output_hit(  # noqa: PLR0913
        self,
        repository: AudioResumeRepository,
        destination: Path,
        mix_id: str,
        channel_plan: ChannelPlan,
        expected_duration_ms: int,
        *,
        cancel: threading.Event | None,
    ) -> AudioProbe | None:
        if not repository.output_hit(destination, mix_id):
            return None
        try:
            probe: AudioProbe = probe_audio(
                destination,
                ffprobe=self._ffprobe,
                runner=self._runner,
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            validate_decode(
                destination,
                ffmpeg=self._ffmpeg,
                runner=self._runner,
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            validate_output_probe(
                probe,
                config=self._config,
                channel_plan=channel_plan,
                expected_duration_ms=expected_duration_ms,
            )
        except AudioDecodeError, AudioProbeError, AudioProcessError:
            return None
        return probe

    def _render_output(  # noqa: PLR0913
        self,
        request: AudioRenderRequest,
        repository: AudioResumeRepository,
        narrator_path: Path,
        destination: Path,
        channel_plan: ChannelPlan,
        expected_duration_ms: int,
        mix_id: str,
        *,
        cancel: threading.Event | None,
    ) -> AudioProbe:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = _temporary_sibling(destination)
        try:
            self._runner.run(
                render_command(
                    self._ffmpeg,
                    temporary,
                    inputs=RenderInputs(
                        narrator=narrator_path,
                        original_audio=request.source_audio_path,
                        config=self._config,
                        channel_plan=channel_plan,
                    ),
                ),
                operation="render_output",
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            probe: AudioProbe = probe_audio(
                temporary,
                ffprobe=self._ffprobe,
                runner=self._runner,
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            validate_output_probe(
                probe,
                config=self._config,
                channel_plan=channel_plan,
                expected_duration_ms=expected_duration_ms,
            )
            _check_cancel(cancel)
            temporary.replace(destination)
            repository.commit_output(mix_id, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return probe


def _result(  # noqa: PLR0913
    request: AudioRenderRequest,
    *,
    status: AudioRenderStatus,
    narrator_path: Path,
    output_path: Path,
    output_probe: AudioProbe,
    plan: TimelinePlan | None,
    channel_plan: ChannelPlan,
    narration_id: str,
    mix_id: str,
) -> AudioRenderResult:
    return AudioRenderResult(
        scope_id=request.scope_id,
        status=status,
        narrator_path=narrator_path,
        output_path=output_path,
        output_probe=output_probe,
        placements=plan.placements if plan is not None else (),
        warnings=(channel_plan.warning,) if channel_plan.warning is not None else (),
        narration_fingerprint=narration_id,
        mix_fingerprint=mix_id,
    )


def _validate_request(request: AudioRenderRequest) -> None:
    if _SAFE_SCOPE.fullmatch(request.scope_id) is None or request.scope_id.upper() in _WINDOWS_DEVICE_NAMES:
        _raise_config("Audio scope_id must be one safe opaque path segment")
    if not math.isfinite(request.post_process_tempo) or request.post_process_tempo <= 0:
        _raise_config("Audio post-process tempo must be finite and positive")
    for clip in request.clips:
        if clip.start_ms < 0 or clip.end_ms <= clip.start_ms:
            _raise_config("TimedClip must have a positive subtitle window")
        if not clip.clip_path.is_file() or clip.clip_path.stat().st_size == 0:
            _raise_config("TimedClip source must be a non-empty file")
    if request.source_audio_path is not None and (
        not request.source_audio_path.is_file() or request.source_audio_path.stat().st_size == 0
    ):
        _raise_config("Original audio source must be a non-empty file")


def _validate_narrator_probe(probe: AudioProbe, plan: TimelinePlan) -> None:
    expected_duration_ms: int = (plan.total_frames * 1000 + plan.sample_rate // 2) // plan.sample_rate
    if (
        probe.codec_name == "pcm_s16le"
        and probe.sample_rate == plan.sample_rate
        and probe.channels == plan.channels
        and abs(probe.duration_ms - expected_duration_ms) <= _NARRATOR_DURATION_TOLERANCE_MS
    ):
        return
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message="Narrator WAV does not match its PCM timeline",
        suggestion="Regenerate normalized clips and inspect FFmpeg diagnostics.",
        details={"operation": "narrator_validation"},
    )
    raise AudioDecodeError(context=context)


def _temporary_sibling(path: Path) -> Path:
    descriptor: int
    raw_path: str
    descriptor, raw_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=f".tmp{path.suffix}",
    )
    os.close(descriptor)
    return Path(raw_path)


def _digest_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is None or not cancel.is_set():
        return
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message="Audio render cancelled",
        suggestion="Run the file again to resume from committed artifacts.",
        details={"operation": "audio_render"},
    )
    raise AudioCancelledError(context=context)


def _notify(
    callbacks: AudioProgressSink | None,
    scope_id: str,
    phase: str,
) -> None:
    if callbacks is None:
        return
    try:
        callbacks.on_audio_phase(scope_id, phase)
    except Exception:  # noqa: BLE001 - observers cannot own audio execution
        return


def _raise_config(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Check the audio render request and its owned input paths.",
        details={"operation": "audio_request"},
    )
    raise AudioConfigError(context=context)


def _raise_decode(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Regenerate the narrator timeline.",
        details={"operation": "timeline"},
    )
    raise AudioDecodeError(context=context)
