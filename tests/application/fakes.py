from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from PIL import Image

from anishift.application.cancellation import CancellationToken
from anishift.application.episode_selection import AniZipMapping, FranchiseGraph, JsonObject, ListedEpisode
from anishift.application.events import RunEvent
from anishift.application.planning import PlanTask, RunSettingsSnapshot, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.scheduler_contracts import TaskHandler, TaskProgressSink
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.services.catalog import PrequelEntry, SeasonAiring, TitleCandidate, TitleCatalogError, TitleStatus
from anishift.services.media import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind
from anishift.services.subtitles import DisplayedLine, SpokenLine
from anishift.services.translation.protocols import TranslationCancellation, TranslationObserver
from anishift.services.translation.types import FileTranslation, TranslatedLine

_HOLD_LIMIT_S: Final[float] = 10.0

_CATALOGUE_EPISODES: Final[int] = 12


class FakeTranslationService:
    def __init__(
        self,
        *,
        entered: threading.Event | None = None,
        release: threading.Event | None = None,
        hold_until_cancelled: bool = False,
    ) -> None:
        self.entered: threading.Event | None = entered
        self.release: threading.Event | None = release
        self.hold_until_cancelled: bool = hold_until_cancelled
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
        deadline: float = time.monotonic() + _HOLD_LIMIT_S
        while self.hold_until_cancelled and cancel is not None and not cancel.is_set():
            assert time.monotonic() < deadline
            time.sleep(0.01)
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
        settings: RunSettingsSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        if task.group_id == self.group_id and task.kind is TaskKind.SPLIT_SUBTITLES:
            raise ExecutionError("fake subtitle split failure")
        return self.delegate.execute(task, artifacts, settings, cancel, progress)

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


class FakeEpisodeCatalogue:
    def __init__(
        self,
        *,
        english: str | None = "Neko to Ryuu",
        romaji: str = "Neko to Ryuu",
        titles: Mapping[int, str] | None = None,
        season: int = 1,
        media_format: str = "TV",
    ) -> None:
        self.english: str | None = english
        self.romaji: str = romaji
        self.titles: dict[int, str] = dict(titles or {})
        self.season: int = season
        self.media_format: str = media_format
        self.down: bool = False
        self.franchised: list[int] = []

    def search(self, text: str, *, limit: int = 7) -> tuple[TitleCandidate, ...]:
        raise AssertionError((text, limit))

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[PrequelEntry, ...]:
        return ()

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        return SeasonAiring(anilist_id, TitleStatus.FINISHED, _CATALOGUE_EPISODES, ())

    def franchise(self, anilist_id: int, *, cancel: CancellationToken | None = None) -> FranchiseGraph:
        self.franchised.append(anilist_id)
        if self.down:
            raise TitleCatalogError(context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message="down"))
        node: dict[str, object] = {
            "id": anilist_id,
            "title": {"romaji": self.romaji, "english": self.english},
            "format": self.media_format,
            "status": "FINISHED",
            "episodes": _CATALOGUE_EPISODES,
            "synonyms": [],
            "relations": {"edges": []},
            "startDate": {"year": 2020, "month": 1, "day": 1},
        }
        return FranchiseGraph(anilist_id, {anilist_id: node}, frozenset({anilist_id}), True)

    def mapping(self, anilist_id: int) -> AniZipMapping:
        if self.down:
            raise TitleCatalogError(context=ErrorContext(code=ErrorCode.EPISODE_CATALOG_FAILED, message="down"))
        numbers: range = range(1, _CATALOGUE_EPISODES + 1)
        raw: dict[str, JsonObject] = {
            str(number): {"episode": str(number), "seasonNumber": self.season, "episodeNumber": number}
            for number in numbers
        }
        episodes: tuple[ListedEpisode, ...] = tuple(
            ListedEpisode(number, title_en=self.titles.get(number), season=self.season, episode=number)
            for number in numbers
        )
        return AniZipMapping(None, self.media_format, _CATALOGUE_EPISODES, episodes, (), None, raw)


def write_image_source(path: Path, *, width: int = 320, height: int = 240) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode: str = "RGBA" if path.suffix.casefold() == ".png" else "RGB"
    Image.new(mode, (width, height), (12, 34, 56, 255)[: len(mode)]).save(path)


def write_text_source(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_media_source(path: Path) -> None:
    path.write_bytes(b"fake media")
    path.with_suffix(".srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
        encoding="utf-8",
    )
