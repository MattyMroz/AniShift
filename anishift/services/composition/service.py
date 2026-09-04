"""Synchronous facade assembling pipeline products into one finished file."""

from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
from typing import Final, Protocol

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, BinaryNotFoundError, require_binary
from anishift.services.composition.commands import (
    NARRATION_TRACK_NAME,
    CommandOutcome,
    StreamingRunner,
    burn_command,
    container_burn_command,
    container_merge_command,
    merge_command,
    parse_ffmpeg_progress,
    parse_mkvmerge_progress,
    subtitle_filter_argument,
)
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import CompositionConfigError
from anishift.services.composition.fonts import attachment_font_names, missing_fonts
from anishift.services.composition.paths import filter_safe_copy, output_path, temporary_sibling
from anishift.services.composition.probe import (
    audio_codec_name,
    source_duration_us,
    source_tracks,
    validate_burned,
    validate_merged,
)
from anishift.services.composition.types import (
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    ContainerCompositionRequest,
    ContainerCompositionResult,
    ContainerTarget,
    OutputVariant,
)
from anishift.services.media import MediaCatalog
from anishift.services.media._process import ProcessRunner
from anishift.services.media._process import SubprocessRunner as ProbeSubprocessRunner
from anishift.utils.logger import get_logger
from anishift.utils.safe_fs import safe_move
from anishift.utils.timer import Timer

__all__ = ["CompositionProgressSink", "CompositionService"]

# ── Constants ────────────────────────────────────────────────────────────────

_MKVMERGE_WARNING_EXIT: Final[int] = 1
"""mkvmerge exit code meaning the result exists but carries warnings."""

logger = get_logger(__name__)


class CompositionProgressSink(Protocol):
    """Optional phase callback owned and rendered by the pipeline."""

    def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
        """Report one composition phase without rendering UI."""
        ...


class CompositionService:
    """Assemble one source container into the requested final artifact."""

    def __init__(  # noqa: PLR0913 - explicit tool and runner injection keeps process ownership testable
        self,
        config: CompositionConfig,
        *,
        runner: StreamingRunner | None = None,
        mkvmerge: Path | None = None,
        ffmpeg: Path | None = None,
        ffprobe: Path | None = None,
        probe_runner: ProcessRunner | None = None,
    ) -> None:
        """Store tool overrides and defer resolution until a variant needs them."""
        self._config: CompositionConfig = config
        self._runner: StreamingRunner = runner or StreamingRunner(
            shutdown_grace_s=config.shutdown_grace_s,
        )
        self._mkvmerge: Path | None = mkvmerge
        self._ffmpeg: Path | None = ffmpeg
        self._ffprobe: Path | None = ffprobe
        self._probe_runner: ProcessRunner = probe_runner or ProbeSubprocessRunner()

    def _resolve_tool(self, binary: Binary, configured: Path | None) -> Path:
        """Return one configured or bundled composition tool."""
        if configured is not None:
            return configured
        try:
            return require_binary(binary)
        except BinaryNotFoundError as error:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.BINARY_NOT_FOUND,
                message="Composition requires MKVToolNix and FFmpeg",
                suggestion="Run `anishift setup` to install the external tools.",
                details={"operation": "composition_config"},
            )
            raise CompositionConfigError(context=context) from error

    @property
    def ffprobe(self) -> Path:
        """Return the resolved FFprobe binary, reused for pre-run estimates."""
        if self._ffprobe is None:
            self._ffprobe = self._resolve_tool(Binary.FFPROBE, None)
        return self._ffprobe

    @property
    def _mkvmerge_path(self) -> Path:
        """Return the resolved MKVmerge binary."""
        if self._mkvmerge is None:
            self._mkvmerge = self._resolve_tool(Binary.MKVMERGE, None)
        return self._mkvmerge

    @property
    def _ffmpeg_path(self) -> Path:
        """Return the resolved FFmpeg binary."""
        if self._ffmpeg is None:
            self._ffmpeg = self._resolve_tool(Binary.FFMPEG, None)
        return self._ffmpeg

    def compose(
        self,
        plan: CompositionPlan,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> CompositionResult:
        """Produce the artifact described by ``plan`` and validate it."""
        timer: Timer = Timer("composition", auto_start=True)
        logger.info(
            "Composition started",
            scope_id=plan.scope_id,
            variant=plan.variant.value,
            has_narration=plan.narration_audio is not None,
            subtitle_count=len(plan.subtitles),
        )
        if plan.variant is OutputVariant.PLAYERS:
            return self._compose_players(plan, timer=timer)
        if not plan.has_material:
            logger.info("Composition skipped", scope_id=plan.scope_id, reason="nothing_to_add")
            return CompositionResult(
                source_path=plan.source_path,
                variant=plan.variant,
                status=CompositionStatus.SKIPPED_NOTHING_TO_ADD,
                duration_ms=timer.duration_ms,
            )
        if plan.variant is OutputVariant.MERGE:
            return self._compose_merge(plan, timer=timer, callbacks=callbacks, cancel=cancel)
        return self._compose_burn(plan, timer=timer, callbacks=callbacks, cancel=cancel)

    def compose_container(
        self,
        request: ContainerCompositionRequest,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> ContainerCompositionResult:
        """Produce exactly one independently addressed MKV or MP4 container."""
        timer: Timer = Timer("composition_container", auto_start=True)
        logger.info(
            "Container composition started",
            target=request.target.value,
            has_narration=request.narration_audio is not None,
            subtitle_count=len(request.attached_subtitles),
        )
        if request.target is ContainerTarget.MKV:
            return self._compose_container_mkv(request, timer=timer, callbacks=callbacks, cancel=cancel)
        return self._compose_container_mp4(request, timer=timer, callbacks=callbacks, cancel=cancel)

    def _compose_container_mkv(
        self,
        request: ContainerCompositionRequest,
        *,
        timer: Timer,
        callbacks: CompositionProgressSink | None,
        cancel: threading.Event | None,
    ) -> ContainerCompositionResult:
        """Mux one MKV while preserving only the source tracks requested by policy."""
        temporary: Path = temporary_sibling(request.destination)
        expected: tuple[str, ...] = tuple(subtitle.track_name for subtitle in request.attached_subtitles)
        if request.narration_audio is not None:
            expected = (*expected, NARRATION_TRACK_NAME)
        warnings: tuple[str, ...] = self._container_font_warnings(request, cancel=cancel)
        source_size: int = request.source_video.stat().st_size
        output_size: int
        try:
            outcome: CommandOutcome = self._runner.run(
                container_merge_command(request, mkvmerge=self._mkvmerge_path, destination=temporary),
                operation="merge_container",
                timeout_s=self._config.operation_timeout_s,
                progress=parse_mkvmerge_progress,
                on_percent=lambda percent: _notify(callbacks, "", "merging", percent),
                cancel=cancel,
                warning_exit_code=_MKVMERGE_WARNING_EXIT,
            )
            validate_merged(
                temporary,
                expected_track_names=expected,
                cancel=cancel,
                runner=self._probe_runner,
            )
            output_size = temporary.stat().st_size
            temporary.replace(request.destination)
        finally:
            temporary.unlink(missing_ok=True)
        timer.stop()
        if outcome.had_warnings:
            warnings = (*warnings, "mkvmerge reported warnings")
        return _container_result(
            request,
            timer=timer,
            output_size=output_size,
            source_size=source_size,
            warnings=warnings,
        )

    def _compose_container_mp4(
        self,
        request: ContainerCompositionRequest,
        *,
        timer: Timer,
        callbacks: CompositionProgressSink | None,
        cancel: threading.Event | None,
    ) -> ContainerCompositionResult:
        """Render or remux one MP4 with independently selected subtitle and audio policy."""
        temporary: Path = temporary_sibling(request.destination)
        ffprobe: Path = self.ffprobe
        video_us: int
        total_us: int
        video_us, total_us = self._render_durations_us(
            request.source_video,
            request.narration_audio,
            keep_original_audio=request.keep_original_audio,
            cancel=cancel,
        )
        warnings: tuple[str, ...] = self._container_font_warnings(request, cancel=cancel)
        source_size: int = request.source_video.stat().st_size
        output_size: int
        work_dir: Path | None = None
        try:
            subtitle_argument: str | None = None
            if request.burn_subtitle is not None:
                work_dir = Path(tempfile.mkdtemp(dir=request.destination.parent, prefix=".anishift-compose-"))
                safe_subtitle: Path = filter_safe_copy(request.burn_subtitle, work_dir)
                subtitle_argument = subtitle_filter_argument(
                    Path(safe_subtitle.name),
                    kind=request.burn_subtitle.suffix.removeprefix(".").casefold(),
                )
            audio_source: Path | None = request.narration_audio
            if audio_source is None and request.keep_original_audio:
                audio_source = request.source_video
            audio_codec: str = (
                audio_codec_name(
                    audio_source,
                    ffprobe=ffprobe,
                    cancel=cancel,
                    runner=self._probe_runner,
                )
                if audio_source is not None
                else ""
            )
            self._runner.run(
                container_burn_command(
                    request,
                    ffmpeg=self._ffmpeg_path,
                    config=self._config,
                    subtitle_argument=subtitle_argument,
                    audio_codec=audio_codec,
                    destination=temporary,
                ),
                operation="render_container",
                timeout_s=self._config.render_timeout_s,
                progress=lambda line: parse_ffmpeg_progress(line, total_us=total_us),
                on_percent=lambda percent: _notify(callbacks, "", "burning", percent),
                cancel=cancel,
                cwd=work_dir,
            )
            validate_burned(
                temporary,
                expected_duration_us=total_us,
                expected_video_duration_us=video_us,
                ffprobe=ffprobe,
                cancel=cancel,
                runner=self._probe_runner,
            )
            output_size = temporary.stat().st_size
            temporary.replace(request.destination)
        finally:
            temporary.unlink(missing_ok=True)
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)
        timer.stop()
        if source_size > 0 and output_size > source_size * self._config.size_budget_ratio:
            warnings = (*warnings, "rendered file is larger than the source; consider a smaller preset")
        return _container_result(
            request,
            timer=timer,
            output_size=output_size,
            source_size=source_size,
            warnings=warnings,
        )

    def _compose_players(self, plan: CompositionPlan, *, timer: Timer) -> CompositionResult:
        """Gather every product next to the source so players pair them."""
        destination: Path = plan.source_path.parent
        moved: list[Path] = []
        sources: list[Path] = [subtitle.path for subtitle in plan.subtitles]
        if plan.narration_audio is not None:
            sources.append(plan.narration_audio)
        for product in sources:
            if product.parent == destination or not product.is_file():
                continue
            moved.append(safe_move(product, destination / product.name))
        timer.stop()
        logger.info("Composition completed", scope_id=plan.scope_id, variant="players", moved=len(moved))
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=destination,
            duration_ms=timer.duration_ms,
            moved_paths=tuple(moved),
        )

    def _compose_merge(
        self,
        plan: CompositionPlan,
        *,
        timer: Timer,
        callbacks: CompositionProgressSink | None,
        cancel: threading.Event | None,
    ) -> CompositionResult:
        """Mux the lector and subtitle tracks into a new container."""
        destination: Path = output_path(plan.source_path, plan.variant, plan.destination_dir)
        temporary: Path = temporary_sibling(destination)
        expected: tuple[str, ...] = _appended_track_names(plan)
        warnings: tuple[str, ...] = self._font_warnings(plan, cancel=cancel)
        try:
            outcome: CommandOutcome = self._runner.run(
                merge_command(plan, mkvmerge=self._mkvmerge_path, destination=temporary),
                operation="merge",
                timeout_s=self._config.operation_timeout_s,
                progress=parse_mkvmerge_progress,
                on_percent=lambda percent: _notify(callbacks, plan.scope_id, "merging", percent),
                cancel=cancel,
                warning_exit_code=_MKVMERGE_WARNING_EXIT,
            )
            validate_merged(
                temporary,
                expected_track_names=expected,
                cancel=cancel,
                runner=self._probe_runner,
            )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        timer.stop()
        if outcome.had_warnings:
            warnings = (*warnings, "mkvmerge reported warnings")
        logger.info(
            "Composition completed",
            scope_id=plan.scope_id,
            variant="merge",
            added_tracks=len(expected),
            duration_ms=round(timer.duration_ms),
        )
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=destination,
            output_size_bytes=destination.stat().st_size,
            source_size_bytes=plan.source_path.stat().st_size,
            duration_ms=timer.duration_ms,
            warnings=warnings,
        )

    def _compose_burn(
        self,
        plan: CompositionPlan,
        *,
        timer: Timer,
        callbacks: CompositionProgressSink | None,
        cancel: threading.Event | None,
    ) -> CompositionResult:
        """Render an MP4 with the subtitles composited into the picture."""
        destination: Path = output_path(plan.source_path, plan.variant, plan.destination_dir)
        temporary: Path = temporary_sibling(destination)
        ffprobe: Path = self.ffprobe
        video_us: int
        total_us: int
        video_us, total_us = self._render_durations_us(
            plan.source_path,
            plan.narration_audio,
            keep_original_audio=plan.narration_audio is None,
            cancel=cancel,
        )
        subtitle_argument: str | None = self._burn_filter(plan)
        warnings: tuple[str, ...] = self._font_warnings(plan, cancel=cancel)
        audio_source: Path = plan.narration_audio or plan.source_path
        try:
            self._runner.run(
                burn_command(
                    plan,
                    ffmpeg=self._ffmpeg_path,
                    config=self._config,
                    subtitle_argument=subtitle_argument,
                    audio_codec=audio_codec_name(
                        audio_source,
                        ffprobe=ffprobe,
                        cancel=cancel,
                        runner=self._probe_runner,
                    ),
                    destination=temporary,
                ),
                operation="burn",
                timeout_s=self._config.render_timeout_s,
                progress=lambda line: parse_ffmpeg_progress(line, total_us=total_us),
                on_percent=lambda percent: _notify(callbacks, plan.scope_id, "burning", percent),
                cancel=cancel,
                cwd=plan.temporary_root / "composition" if subtitle_argument is not None else None,
            )
            validate_burned(
                temporary,
                expected_duration_us=total_us,
                expected_video_duration_us=video_us,
                ffprobe=ffprobe,
                cancel=cancel,
                runner=self._probe_runner,
            )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        timer.stop()
        output_size: int = destination.stat().st_size
        source_size: int = plan.source_path.stat().st_size
        if source_size > 0 and output_size > source_size * self._config.size_budget_ratio:
            warnings = (*warnings, "rendered file is larger than the source; consider a smaller preset")
        logger.info(
            "Composition completed",
            scope_id=plan.scope_id,
            variant="burn",
            duration_ms=round(timer.duration_ms),
            size_ratio=round(output_size / source_size, 2) if source_size else 0,
        )
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=destination,
            output_size_bytes=output_size,
            source_size_bytes=source_size,
            duration_ms=timer.duration_ms,
            warnings=warnings,
        )

    def _burn_filter(self, plan: CompositionPlan) -> str | None:
        """Return the subtitle filter value, copying the file when needed."""
        if plan.burn_subtitle is None:
            return None
        work_dir: Path = plan.temporary_root / "composition"
        safe_subtitle: Path = filter_safe_copy(plan.burn_subtitle, work_dir)
        return subtitle_filter_argument(Path(safe_subtitle.name), kind=plan.source_subtitle_kind)

    def _render_durations_us(
        self,
        source: Path,
        narration: Path | None,
        *,
        keep_original_audio: bool,
        cancel: threading.Event | None,
    ) -> tuple[int, int]:
        """Return video and product durations for the streams actually retained."""
        video_us: int = source_duration_us(
            source,
            video_only=True,
            ffprobe=self.ffprobe,
            cancel=cancel,
            runner=self._probe_runner,
        )
        sources: list[Path] = [source] if keep_original_audio else []
        if narration is not None:
            sources.append(narration)
        durations: list[int] = [video_us]
        durations.extend(
            source_duration_us(path, ffprobe=self.ffprobe, cancel=cancel, runner=self._probe_runner) for path in sources
        )
        return video_us, max(durations)

    def _font_warnings(
        self,
        plan: CompositionPlan,
        *,
        cancel: threading.Event | None,
    ) -> tuple[str, ...]:
        """Return one warning per font referenced but not attached."""
        subtitle: Path | None = plan.burn_subtitle or (plan.subtitles[0].path if plan.subtitles else None)
        if subtitle is None:
            return ()
        info: MediaCatalog = source_tracks(plan.source_path, cancel=cancel, runner=self._probe_runner)
        available: frozenset[str] = attachment_font_names(info.attachments)
        missing: tuple[str, ...] = missing_fonts(subtitle, available)
        if not missing:
            return ()
        logger.warning("Composition font missing", scope_id=plan.scope_id, font_count=len(missing))
        return tuple(f"font not embedded: {name}" for name in missing)

    def _container_font_warnings(
        self,
        request: ContainerCompositionRequest,
        *,
        cancel: threading.Event | None,
    ) -> tuple[str, ...]:
        """Return missing-font warnings for a target-specific request."""
        subtitle: Path | None = request.burn_subtitle
        if subtitle is None and request.attached_subtitles:
            subtitle = request.attached_subtitles[0].path
        if subtitle is None:
            return ()
        info: MediaCatalog = source_tracks(request.source_video, cancel=cancel, runner=self._probe_runner)
        available: frozenset[str] = attachment_font_names(info.attachments)
        missing: tuple[str, ...] = missing_fonts(subtitle, available)
        return tuple(f"font not embedded: {name}" for name in missing)


def _appended_track_names(plan: CompositionPlan) -> tuple[str, ...]:
    """Return the track names this run adds to the merged container."""
    names: list[str] = [subtitle.track_name for subtitle in plan.subtitles]
    if plan.narration_audio is not None:
        names.append(NARRATION_TRACK_NAME)
    return tuple(names)


def _container_result(
    request: ContainerCompositionRequest,
    *,
    timer: Timer,
    output_size: int,
    source_size: int,
    warnings: tuple[str, ...],
) -> ContainerCompositionResult:
    """Build the immutable result after a container was atomically committed."""
    return ContainerCompositionResult(
        source_path=request.source_video,
        target=request.target,
        output_path=request.destination,
        output_size_bytes=output_size,
        source_size_bytes=source_size,
        duration_ms=timer.duration_ms,
        warnings=warnings,
    )


def _notify(callbacks: CompositionProgressSink | None, scope_id: str, phase: str, percent: int) -> None:
    """Report progress without letting an observer break composition."""
    if callbacks is None:
        return
    try:
        callbacks.on_composition_phase(scope_id, phase, percent)
    except Exception:  # noqa: BLE001 - observers never own composition execution
        logger.warning("Composition progress observer failed", scope_id=scope_id, phase=phase)
