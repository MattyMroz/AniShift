"""Typed task-family dispatcher for graph-scheduled application work."""

from __future__ import annotations

from dataclasses import dataclass

from anishift.application.audio_handler import AudioTaskHandler
from anishift.application.cancellation import CancellationToken
from anishift.application.composition_handler import CompositionTaskHandler, build_composition_request
from anishift.application.extraction_handler import ExtractionTaskHandler, LegacyExtractionAdapter
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.publish_handler import PublishTaskHandler
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.scheduler_contracts import TaskHandler, TaskProgressSink
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


@dataclass(frozen=True, slots=True)
class ExecutionHandlers:
    """Explicit task-family dispatcher shared by the graph scheduler."""

    media: ExtractionTaskHandler
    subtitles: SubtitleTaskHandler
    translation: TranslationTaskHandler
    tts: TtsTaskHandler | None = None
    audio: AudioTaskHandler | None = None
    composition: CompositionTaskHandler | None = None
    publish: PublishTaskHandler | None = None

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Dispatch a task by its closed operation kind without a plugin registry."""
        handler: TaskHandler | None
        match task.kind:
            case TaskKind.EXTRACT_AUDIO | TaskKind.EXTRACT_SUBTITLES | TaskKind.EXTRACT_TRACKS:
                handler = self.media
            case TaskKind.NORMALIZE_SUBTITLES | TaskKind.SPLIT_SUBTITLES:
                handler = self.subtitles
            case TaskKind.TRANSLATE_SUBTITLES:
                handler = self.translation
            case TaskKind.SYNTHESIZE_SPEECH:
                handler = self.tts
            case TaskKind.TRANSCODE_AUDIO | TaskKind.MIX_NARRATION:
                handler = self.audio
            case TaskKind.COMPOSE_MKV | TaskKind.COMPOSE_MP4:
                handler = self.composition
            case TaskKind.PUBLISH_ARTIFACT:
                handler = self.publish
        if handler is None:
            msg = f"Task handler is unavailable for operation: {task.kind.value}"
            raise ExecutionError(msg)
        return handler.execute(task, artifacts, cancel, progress)

    def cancel(self) -> None:
        """Cancel run-scoped provider work without closing shared runtimes."""
        if self.tts is not None:
            self.tts.cancel()

    def close(self) -> None:
        """Close run-scoped provider runtimes exactly once at the application boundary."""
        if self.tts is not None:
            self.tts.close()
