"""Typed task-family dispatcher for graph-scheduled application work."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from anishift.application.audio_handler import AudioTaskHandler
from anishift.application.cancellation import CancellationToken
from anishift.application.composition_handler import CompositionTaskHandler, build_composition_request
from anishift.application.extraction_handler import ExtractionTaskHandler, LegacyExtractionAdapter
from anishift.application.planning import PlanTask, RunSettingsSnapshot, TaskKind
from anishift.application.publish_handler import PublishTaskHandler
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.subtitle_handler import SubtitleTaskHandler
from anishift.application.translation_handler import TranslationTaskHandler
from anishift.application.tts_handler import TtsTaskHandler
from anishift.errors import ExecutionError

__all__ = [
    "AudioTaskHandler",
    "CompositionTaskHandler",
    "ExecutionHandlers",
    "ExtractionTaskHandler",
    "LegacyExtractionAdapter",
    "PublishTaskHandler",
    "SubtitleTaskHandler",
    "TranslationTaskHandler",
    "TtsTaskHandler",
    "build_composition_request",
]

type HandlerFactory[H] = Callable[[RunSettingsSnapshot], H]
"""Build the handler of one task from the settings read when that task starts."""


class _TaskHandler(Protocol):
    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult: ...


@dataclass(frozen=True, slots=True)
class ExecutionHandlers:
    """Explicit task-family dispatcher; every settings-dependent handler is built when its task starts."""

    media: ExtractionTaskHandler
    subtitles: HandlerFactory[SubtitleTaskHandler]
    translation: HandlerFactory[TranslationTaskHandler]
    tts: HandlerFactory[TtsTaskHandler] | None = None
    audio: HandlerFactory[AudioTaskHandler] | None = None
    composition: HandlerFactory[CompositionTaskHandler] | None = None
    publish: PublishTaskHandler | None = None
    close_services: Callable[[], None] | None = None

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        settings: RunSettingsSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Dispatch a task by its closed operation kind to a handler built from the settings it started with."""
        handler: _TaskHandler | None
        match task.kind:
            case TaskKind.EXTRACT_AUDIO | TaskKind.EXTRACT_SUBTITLES | TaskKind.EXTRACT_TRACKS:
                handler = self.media
            case TaskKind.NORMALIZE_SUBTITLES | TaskKind.SPLIT_SUBTITLES:
                handler = self.subtitles(settings)
            case TaskKind.TRANSLATE_SUBTITLES:
                handler = self.translation(settings)
            case TaskKind.SYNTHESIZE_SPEECH:
                handler = None if self.tts is None else self.tts(settings)
            case TaskKind.TRANSCODE_AUDIO | TaskKind.MIX_NARRATION:
                handler = None if self.audio is None else self.audio(_planned_audio(task, settings))
            case TaskKind.COMPOSE_MKV | TaskKind.COMPOSE_MP4 | TaskKind.COMPOSE_COVER:
                handler = None if self.composition is None else self.composition(settings)
            case TaskKind.PUBLISH_ARTIFACT:
                handler = self.publish
        if handler is None:
            msg = f"Task handler is unavailable for operation: {task.kind.value}"
            raise ExecutionError(msg)
        return handler.execute(task, artifacts, cancel, progress)

    def close(self) -> None:
        """Close the run-scoped provider services exactly once at the application boundary."""
        if self.close_services is not None:
            self.close_services()


def _planned_audio(task: PlanTask, settings: RunSettingsSnapshot) -> RunSettingsSnapshot:
    """Return *settings* with the output profile the task was planned for, because that profile names its file."""
    profile: str | int | bool | None = dict(task.parameters).get("output_profile")
    if not isinstance(profile, str) or profile == settings.audio_output_profile:
        return settings
    return replace(settings, audio_output_profile=profile)
