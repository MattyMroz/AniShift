from __future__ import annotations

import threading
from pathlib import Path

from anishift.application.cancellation import CancellationToken
from anishift.application.events import RunEvent
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.scheduler_contracts import TaskHandler, TaskProgressSink
from anishift.errors import ExecutionError
from anishift.services.media import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind
from anishift.services.subtitles import DisplayedLine, SpokenLine
from anishift.services.translation.protocols import TranslationCancellation, TranslationObserver
from anishift.services.translation.types import FileTranslation, TranslatedLine


class FakeTranslationService:
    def __init__(self, *, entered: threading.Event | None = None, release: threading.Event | None = None) -> None:
        self.entered: threading.Event | None = entered
        self.release: threading.Event | None = release
        self.calls: list[tuple[str, ...]] = []

    def translate_file(  # noqa: PLR0913
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        del displayed, source_lang, target_lang, observer
        self.calls.append(tuple(line.text for line in spoken))
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(timeout=2.0)
        if cancel is not None and cancel.is_set():
            return FileTranslation(engine_id="fake", error="cancelled")
        translated: tuple[TranslatedLine, ...] = tuple(
            TranslatedLine(
                line.start,
                line.end,
                line.text,
                f"PL {line.text}",
                (f"PL {line.text}",),
                line.style,
            )
            for line in spoken
        )
        return FileTranslation(
            spoken=translated,
            engine_id="fake",
            unique_lines=len(translated),
            total_lines=len(translated),
            api_calls=1,
        )


class FailingGroupHandler:
    def __init__(self, delegate: TaskHandler, *, group_id: str | None = None) -> None:
        self.delegate: TaskHandler = delegate
        self.group_id: str | None = group_id

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        if task.group_id == self.group_id and task.kind is TaskKind.SPLIT_SUBTITLES:
            raise ExecutionError("fake subtitle split failure")
        return self.delegate.execute(task, artifacts, cancel, progress)

    def close(self) -> None:
        close: object = getattr(self.delegate, "close", None)
        if callable(close):
            close()


class CollectingRunSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []
        self.started: threading.Event = threading.Event()

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)
        if event.kind.value == "run_started":
            self.started.set()


class FakeMediaProbe:
    def identify(
        self,
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> MediaCatalog:
        del cancel, timeout_s
        return MediaCatalog(
            path=path,
            container=ContainerKind(path.suffix.casefold().lstrip(".")),
            duration_us=10_000_000,
            tracks=(
                MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
                MediaTrack(1, MediaTrackKind.AUDIO, "aac", "jpn", None, True, False),
            ),
        )


def write_text_source(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_media_source(path: Path) -> None:
    path.write_bytes(b"fake media")
    path.with_suffix(".srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
        encoding="utf-8",
    )
