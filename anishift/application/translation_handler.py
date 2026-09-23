"""Application adapter from subtitle translation tasks to the domain facade."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Protocol

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.errors import ExecutionError
from anishift.services.subtitles import (
    DisplayedLine,
    SpokenLine,
    SubtitleKind,
    SubtitleSplit,
    is_drawing,
    load_subtitles,
    read_txt,
    split_subtitles,
    spoken_to_srt,
    subtitle_kind,
    visible_text,
    visible_verses,
    write_translated,
)
from anishift.services.translation.errors import TranslationError
from anishift.services.translation.layout_config import LayoutConfig
from anishift.services.translation.linebreak import split_for_layout, split_line
from anishift.services.translation.protocols import TranslationCancellation, TranslationObserver
from anishift.services.translation.types import FileTranslation

__all__ = [
    "TextDocument",
    "TextFragment",
    "TranslationTaskHandler",
    "TranslationVerses",
    "displayed_lines",
    "read_text_document",
    "text_spoken_lines",
    "translate_subtitle_split",
    "translation_verses",
    "write_text_document",
]

# ── Constants ──────────────────────────────────────────────────────────────

_RE_TRAILING_BREAK: Final[re.Pattern[str]] = re.compile(r"(?:\r?\n[^\S\r\n]*)+\Z")
"""The run of line breaks closing one paragraph, kept verbatim so blank lines survive translation."""


class TranslationExecutor(Protocol):
    """Configured synchronous translation facade used by one run."""

    def translate_file(  # noqa: PLR0913 - mirrors the configured domain facade
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        """Translate one subtitle file's spoken and displayed streams."""
        ...


class _CancellationView:
    __slots__ = ("_cancel",)

    def __init__(self, cancel: CancellationToken) -> None:
        self._cancel: CancellationToken = cancel

    def is_set(self) -> bool:
        return self._cancel.is_cancelled()


class _ProgressObserver:
    __slots__ = ("_completed", "_progress", "_task_id")

    def __init__(self, task_id: str, progress: TaskProgressSink) -> None:
        self._task_id: str = task_id
        self._progress: TaskProgressSink = progress
        self._completed: int = 0

    def progress(self, engine_id: str, completed: int, total: int) -> None:
        del engine_id
        percent: int = 99 if total <= 0 else min(99, max(0, completed * 100 // total))
        self._completed = percent
        self._progress.emit(
            WorkerNotification(WorkerNotificationKind.PROGRESS, self._task_id, self._completed),
        )

    def retry(
        self,
        engine_id: str,
        attempt: int,
        max_attempts: int,
        reason: str | None = None,
    ) -> None:
        label: str = reason.replace("_", " ").title() if reason else engine_id.upper()
        message: str = f"{label} - retry {attempt}/{max_attempts}"
        self._progress.emit(WorkerNotification(WorkerNotificationKind.RETRY, self._task_id, message=message))

    def fallback(self, failed_engine_id: str, next_engine_id: str) -> None:
        message: str = f"{failed_engine_id} fallback to {next_engine_id}"
        self._progress.emit(WorkerNotification(WorkerNotificationKind.FALLBACK, self._task_id, message=message))


@dataclass(frozen=True, slots=True)
class TranslationVerses:
    """Layout-aware translated streams used by legacy and graph adapters."""

    displayed: tuple[tuple[str, ...], ...]
    spoken: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class TextFragment:
    """One translator-sized piece of a plain text document, identified by its place in it."""

    paragraph: int
    position: int
    text: str

    @property
    def identity(self) -> str:
        """Place of this fragment in the document, carried across translation as the line style."""
        return f"{self.paragraph}:{self.position}"


@dataclass(frozen=True, slots=True)
class TextDocument:
    """Identified fragments of one plain text document and the break closing every paragraph."""

    fragments: tuple[TextFragment, ...]
    breaks: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(fragment.paragraph >= len(self.breaks) for fragment in self.fragments):
            msg = "Text fragment belongs to a paragraph the document does not have"
            raise ValueError(msg)


class TranslationTaskHandler:
    """Translate one subtitle artifact and write a complete Polish staging file."""

    __slots__ = ("_layout", "_run_root", "_service")

    def __init__(
        self,
        service: TranslationExecutor,
        *,
        run_root: Path,
        layout: LayoutConfig | None = None,
    ) -> None:
        """Bind one configured translation facade to the run scope."""
        self._service: TranslationExecutor = service
        self._run_root: Path = run_root
        self._layout: LayoutConfig = layout if layout is not None else LayoutConfig()

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Translate one source subtitle file without publishing it durably."""
        if task.kind is not TaskKind.TRANSLATE_SUBTITLES:
            msg = "Translation handler received a non-translation task"
            raise ExecutionError(msg)
        if len(task.requires) != 1 or len(task.produces) != 1:
            msg = "Translation task must have exactly one input and output"
            raise ExecutionError(msg)
        source: Artifact = artifacts.require_ready(task.requires[0])
        if source.path is None or source.kind not in {ArtifactKind.SOURCE_SUBTITLES, ArtifactKind.STANDALONE_TEXT}:
            msg = "Translation task requires ready source subtitles or text"
            raise ExecutionError(msg)
        output: Artifact = artifacts.require_output(task.produces[0])
        if output.kind not in {ArtifactKind.FULL_PL, ArtifactKind.TRANSLATED_TEXT}:
            msg = "Translation task must produce complete Polish subtitles or text"
            raise ExecutionError(msg)
        if output.kind is ArtifactKind.TRANSLATED_TEXT and source.kind is not ArtifactKind.STANDALONE_TEXT:
            msg = "A translated text document can be written only from a plain text source"
            raise ExecutionError(msg)
        cancel.raise_if_cancelled()
        observer = _ProgressObserver(task.task_id, progress)
        if output.kind is ArtifactKind.TRANSLATED_TEXT:
            result, written = self._translate_document(task, source, output, cancel, observer)
        elif source.kind is ArtifactKind.STANDALONE_TEXT:
            result, written = self._translate_text(task, source, output, cancel, observer)
        else:
            result, written = self._translate_subtitles(
                task,
                source,
                output,
                _output_kind(task, output),
                cancel,
                observer,
            )
        if not result.is_success:
            if result.error_context is not None:
                raise TranslationError(context=result.error_context)
            raise ExecutionError(result.error or "Subtitle translation failed")
        if written is None:
            msg = "Translated subtitle output is empty"
            raise ExecutionError(msg)
        cancel.raise_if_cancelled()
        progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, 100))
        metadata: dict[str, str | int | bool] = {
            "engine_id": result.engine_id,
            "failed_lines": result.failed_lines,
        }
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, written, metadata),))

    def _translate_document(
        self,
        task: PlanTask,
        source: Artifact,
        output: Artifact,
        cancel: CancellationToken,
        observer: TranslationObserver,
    ) -> tuple[FileTranslation, Path | None]:
        parameters: dict[str, str | int | bool] = dict(task.parameters)
        if parameters.get("source_kind") != "txt" or parameters.get("output_format") != "txt" or source.path is None:
            msg = "Text document translation requires source_kind=txt and a txt output"
            raise ExecutionError(msg)
        document: TextDocument = read_text_document(read_txt(source.path), self._layout)
        spoken: tuple[SpokenLine, ...] = tuple(
            SpokenLine(start=0, end=0, text=fragment.text, style=fragment.identity) for fragment in document.fragments
        )
        result: FileTranslation = self._service.translate_file(
            list(spoken),
            [],
            source_lang="auto",
            cancel=_CancellationView(cancel),
            observer=observer,
        )
        _require_complete_translation(result, spoken, ())
        cancel.raise_if_cancelled()
        destination: Path = task_staging_path(self._run_root, task, output, ".txt")
        translated: tuple[str, ...] = tuple(line.text for line in result.spoken)
        return result, write_text_document(document, translated, destination)

    def _translate_text(
        self,
        task: PlanTask,
        source: Artifact,
        output: Artifact,
        cancel: CancellationToken,
        observer: TranslationObserver,
    ) -> tuple[FileTranslation, Path | None]:
        parameters: dict[str, str | int | bool] = dict(task.parameters)
        if parameters.get("source_kind") != "txt" or output.subtitle_format != "srt" or source.path is None:
            msg = "Text translation requires source_kind=txt and an SRT output"
            raise ExecutionError(msg)
        spoken: tuple[SpokenLine, ...] = text_spoken_lines(read_txt(source.path), self._layout)
        result: FileTranslation = self._service.translate_file(
            list(spoken),
            [],
            source_lang="auto",
            cancel=_CancellationView(cancel),
            observer=observer,
        )
        _require_complete_translation(result, spoken, ())
        cancel.raise_if_cancelled()
        destination: Path = task_staging_path(self._run_root, task, output, ".srt")
        return result, spoken_to_srt(result.spoken, destination) if result.is_success else None

    def _translate_subtitles(  # noqa: PLR0913 - exact task and runtime dependencies stay explicit
        self,
        task: PlanTask,
        source: Artifact,
        output: Artifact,
        output_kind: SubtitleKind,
        cancel: CancellationToken,
        observer: TranslationObserver,
    ) -> tuple[FileTranslation, Path | None]:
        if source.path is None:
            msg = "Translation subtitle source requires a runtime path"
            raise ExecutionError(msg)
        source_kind: SubtitleKind | None = subtitle_kind(source.path)
        if source_kind is None:
            msg = "Translation source must be ASS or SRT"
            raise ExecutionError(msg)
        split: SubtitleSplit = split_subtitles(load_subtitles(source.path), kind=source_kind)
        result: FileTranslation = translate_subtitle_split(self._service, split, cancel, observer=observer)
        if not result.is_success:
            return result, None
        _require_complete_translation(result, split.spoken, displayed_lines(split))
        cancel.raise_if_cancelled()
        verses: TranslationVerses = translation_verses(split, result, self._layout)
        output_split: SubtitleSplit = replace(split, kind=output_kind)
        destination: Path = task_staging_path(self._run_root, task, output, f".{output_kind}")
        written: Path | None = write_translated(output_split, verses.displayed, verses.spoken, destination)
        return result, written


def _require_complete_translation(
    result: FileTranslation,
    spoken: tuple[SpokenLine, ...],
    displayed: tuple[DisplayedLine, ...],
) -> None:
    """Reject incomplete products before any subtitle writer runs."""
    if not result.is_success:
        if result.error_context is not None:
            raise TranslationError(context=result.error_context)
        raise ExecutionError(result.error or "Subtitle translation failed")
    if result.failed_lines or len(result.spoken) != len(spoken) or len(result.displayed) != len(displayed):
        msg = "Subtitle translation is incomplete"
        raise ExecutionError(msg)
    for source, translated in zip(spoken, result.spoken, strict=True):
        expected: tuple[int, int, str, str] = (source.start, source.end, source.style, source.text)
        actual: tuple[int, int, str, str] = (
            translated.start,
            translated.end,
            translated.style,
            translated.source_text,
        )
        if expected != actual or not translated.ok or (source.text.strip() and not translated.text.strip()):
            msg = "Spoken subtitle translation is incomplete"
            raise ExecutionError(msg)
    if any(source.text.strip() and not text.strip() for source, text in zip(displayed, result.displayed, strict=True)):
        msg = "Displayed subtitle translation is incomplete"
        raise ExecutionError(msg)


def translate_subtitle_split(
    service: TranslationExecutor,
    split: SubtitleSplit,
    cancel: CancellationToken,
    *,
    observer: TranslationObserver | None = None,
) -> FileTranslation:
    """Translate the two streams of an existing split through one configured facade."""
    return service.translate_file(
        list(split.spoken),
        list(displayed_lines(split)),
        source_lang="auto",
        cancel=_CancellationView(cancel),
        observer=observer,
    )


def read_text_document(text: str, layout: LayoutConfig | None = None) -> TextDocument:
    """Split one plain text document into identified paragraph fragments, keeping every blank line verbatim."""
    from anishift.services.translation.chunking import chunk_text, split_paragraphs  # noqa: PLC0415 - keep engines lazy

    limits: LayoutConfig = layout if layout is not None else LayoutConfig()
    fragments: list[TextFragment] = []
    breaks: list[str] = []
    for paragraph, raw in enumerate(split_paragraphs(text)):
        match: re.Match[str] | None = _RE_TRAILING_BREAK.search(raw)
        breaks.append("" if match is None else match.group())
        body: str = raw if match is None else raw[: match.start()]
        chunks: list[str] = chunk_text(
            " ".join(body.split()),
            char_limit=limits.chunk_chars,
            chunk_limit=limits.chunk_pieces,
        )
        pieces: tuple[str, ...] = tuple(piece for piece in (chunk.strip() for chunk in chunks) if piece)
        fragments.extend(TextFragment(paragraph, position, piece) for position, piece in enumerate(pieces))
    return TextDocument(tuple(fragments), tuple(breaks))


def write_text_document(document: TextDocument, translated: Sequence[str], destination: Path) -> Path | None:
    """Compose translated fragments by identifier and write the document, or return ``None`` when it is empty."""
    if len(translated) != len(document.fragments):
        msg = "Translated text does not cover every fragment of the source document"
        raise ExecutionError(msg)
    paragraphs: list[list[str]] = [[] for _ in document.breaks]
    ordered: list[tuple[TextFragment, str]] = sorted(
        zip(document.fragments, translated, strict=True),
        key=lambda pair: (pair[0].paragraph, pair[0].position),
    )
    for fragment, text in ordered:
        paragraphs[fragment.paragraph].append(text)
    rendered: str = "".join(
        " ".join(pieces) + closing for pieces, closing in zip(paragraphs, document.breaks, strict=True)
    )
    if not rendered.strip():
        return None
    temporary: Path = destination.with_name(f"{destination.name}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(destination)
    return destination


def text_spoken_lines(text: str, layout: LayoutConfig | None = None) -> tuple[SpokenLine, ...]:
    """Chunk plain text hierarchically and wrap each chunk as a narrator line."""
    from anishift.services.translation.chunking import chunk_text  # noqa: PLC0415 - keep engines lazy

    limits: LayoutConfig = layout if layout is not None else LayoutConfig()
    chunks = chunk_text(text, char_limit=limits.chunk_chars, chunk_limit=limits.chunk_pieces)
    flattened = (" ".join(chunk.split()) for chunk in chunks)
    return tuple(SpokenLine(start=0, end=0, text=chunk, style="") for chunk in flattened if chunk)


def displayed_lines(split: SubtitleSplit) -> tuple[DisplayedLine, ...]:
    """Return translatable displayed events in source-file order."""
    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    return tuple(
        DisplayedLine(
            start=event.start,
            end=event.end,
            text=visible_text(event.text),
            order=order,
        )
        for order, (event, decision) in enumerate(zip(dialogue, split.decisions, strict=True))
        if decision == "displayed" and not is_drawing(event.text)
    )


def translation_verses(
    split: SubtitleSplit,
    result: FileTranslation,
    layout: LayoutConfig | None = None,
) -> TranslationVerses:
    """Build authored displayed layout and readable spoken line breaks."""
    limits: LayoutConfig = layout if layout is not None else LayoutConfig()
    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    displayed_events = [
        event
        for event, decision in zip(dialogue, split.decisions, strict=True)
        if decision == "displayed" and not is_drawing(event.text)
    ]
    displayed: tuple[tuple[str, ...], ...] = tuple(
        split_for_layout(
            text,
            visible_verses(event.text),
            max_chars=limits.max_chars_per_line,
            max_lines=limits.max_lines_per_event,
        )
        for event, text in zip(displayed_events, result.displayed, strict=True)
    )
    spoken: tuple[tuple[str, ...], ...] = tuple(
        split_line(line.text, max_chars=limits.max_chars_per_line, max_lines=limits.max_lines_per_event)
        for line in result.spoken
    )
    return TranslationVerses(displayed, spoken)


def _output_kind(task: PlanTask, output: Artifact) -> SubtitleKind:
    raw_format: str | int | bool | None = dict(task.parameters).get("output_format")
    if raw_format == "ass" and output.subtitle_format == raw_format:
        return "ass"
    if raw_format == "srt" and output.subtitle_format == raw_format:
        return "srt"
    msg = "Translation output format does not match the planned artifact"
    raise ExecutionError(msg)
