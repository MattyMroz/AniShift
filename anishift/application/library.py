"""Project completed sets and validate their exact workspace file scope."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from natsort import os_sorted

from anishift.application.artifacts import SourceGroup
from anishift.application.control import (
    ProcessingRequest,
    ProductConfirmation,
    ReadyGroup,
    RequestState,
    WatchState,
    require_relative_paths,
)
from anishift.application.control_views import LibraryFile, LibraryFileIdentity, LibrarySet
from anishift.application.discovery import ArtifactName, classify_artifact
from anishift.application.episode_identity import TECHNICAL, VIDEO_EXTENSIONS
from anishift.application.intents import GroupIntent
from anishift.application.products import main_product
from anishift.application.workflows import WorkflowRoute, WorkflowTarget, WorkspacePlace
from anishift.paths import READY_DIRECTORY
from anishift.services.torrents.names import episode_range, parse_release_name, season_hint, strip_season

if TYPE_CHECKING:
    from anishift.services.torrents.types import ReleaseName

# ── Constants ─────────────────────────────────────────────────────────────────

NO_EPISODE: Final[str] = "—"
"""Episode column of a film or a file without an episode number."""
RANGE_DASH: Final[str] = "–"
"""Join the first and last episode of an episode range."""
FILM_TAIL: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<=[\s.])(?:\(?(?:19|20)\d{2}\)?|\d{3,4}[pi]|blu-?ray|bdrip|web-?dl|webrip)(?=[\s.]|$)"
)
"""Open the release tail of a film name: a year, a resolution or a source after a space or a dot."""
EPISODE_MARKER: Final[re.Pattern[str]] = re.compile(
    r"(?i)^(?:ep\.?|e)\s*\d|\b(?:episode|cap[ií]tulo)\s*\d|\bs\d{1,2}[ .]?ep?\d|\d+x\d+"
    r"|\b(?:season|temporada|saison|staffel)\s*\d"
)
"""Find an episode or season marker that keeps a subtitle out of a film title."""
WORD_DOT: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\.|\.(?!\d)")
"""Find a dot standing for a space, leaving the dot of a decimal number such as ``2.22``."""
EPISODE_NUMBER: Final[re.Pattern[str]] = re.compile(r"\d+(?:v\d+)?")
"""Match a bare episode number with an optional version, as in ``01v3``."""
SUBTITLE_DASH: Final[re.Pattern[str]] = re.compile(r"([ .])-\1")
"""Find a dash between two spaces or two dots that opens a subtitle."""
LEADING_PARENTHESES: Final[re.Pattern[str]] = re.compile(r"^\(([^)]*)\)")
"""Find a release group written in parentheses at the very start of a name."""
EMPTY_BRACKETS: Final[re.Pattern[str]] = re.compile(r"\s*[(\[]\s*[)\]]")
"""Find the empty brackets a removed season marker leaves behind."""
TITLE_EDGE: Final[str] = " -–:,"
"""Characters left dangling at the end of a title once its tail is cut off."""
NUMBERED_PARTS: Final[frozenset[str]] = frozenset({"movie", "film", "part", "case", "chapter", "vol", "ova"})
"""Words whose trailing number belongs to the title rather than to an episode."""
LABEL_CACHE_SIZE: Final[int] = 4096
"""Bound the labels kept for Library names read again on every panel frame."""


@dataclass(frozen=True, slots=True)
class LibraryLabel:
    """Series title and episode read from one Library file name."""

    title: str
    season: int | None
    episode: Decimal | None
    last: Decimal | None = None

    @property
    def episode_text(self) -> str:
        """Return the Episode column: ``SxxEyy``, ``SxxEyy–Ezz`` or a dash without an episode."""
        if self.episode is None:
            return NO_EPISODE
        text: str = f"S{self.season:02}E{_number(self.episode)}"
        return text if self.last is None else f"{text}{RANGE_DASH}E{_number(self.last)}"

    @property
    def text(self) -> str:
        """Return the title followed by the episode, or the title alone without an episode."""
        return self.title if self.episode is None else f"{self.title} {self.episode_text}"


@lru_cache(maxsize=LABEL_CACHE_SIZE)
def library_label(name: str) -> LibraryLabel:
    """Read the series title, season and episode from a Library file name, keeping an unrecognized name whole."""
    path: Path = Path(name)
    stem: str = path.stem if path.suffix.removeprefix(".").casefold() in VIDEO_EXTENSIONS else name
    text: str = LEADING_PARENTHESES.sub(r"[\1]", stem.replace("_", " " if " " in stem else "."))
    release: ReleaseName = parse_release_name(text)
    span: tuple[Decimal, Decimal] | None = episode_range(text)
    episode: Decimal | None = span[0] if span is not None else release.episode
    hint: int | None = season_hint(release.series)
    season: int | None = release.season if release.season is not None else hint
    series: str = strip_season(release.series) if hint is not None else release.series
    joined: ReleaseName | None = _subtitled(release, text) if episode is None and release.season is None else None
    if joined is not None:
        release, series = joined, joined.series
    if episode is None and season is None and release.group is None and release.resolution is None:
        return LibraryLabel(stem, None, None)
    title: str = _title(series, film=episode is None)
    return LibraryLabel(
        title or stem,
        (1 if season is None else season) if episode is not None else season,
        episode,
        None if span is None else span[1],
    )


def _subtitled(release: ReleaseName, text: str) -> ReleaseName | None:
    joined: ReleaseName = parse_release_name(SUBTITLE_DASH.sub(r"\1", text))
    subtitle: list[str] = joined.series.removeprefix(release.series).split()
    keep: bool = bool(subtitle) and joined.series.startswith(release.series) and not _episode_subtitle(subtitle)
    return joined if keep and EPISODE_MARKER.search(release.series) is None else None


def _episode_subtitle(words: list[str]) -> bool:
    if len(words) == 1 and any(char.isdigit() for char in words[0]):
        return True
    if EPISODE_MARKER.search(" ".join(words)):
        return True
    previous: list[str] = [word.casefold().rstrip(".") for word in words[-2:-1]]
    return bool(words) and EPISODE_NUMBER.fullmatch(words[-1]) is not None and not set(previous) & NUMBERED_PARTS


def _title(series: str, *, film: bool) -> str:
    text: str = series.strip()
    tail: re.Match[str] | None = FILM_TAIL.search(text) if film else None
    if tail is not None or " " not in text:
        text = WORD_DOT.sub(" ", text[: len(text) if tail is None else tail.start()])
    words: list[str] = text.split()
    while film and len(words) > 1 and TECHNICAL.fullmatch(words[-1].casefold()):
        words.pop()
    return EMPTY_BRACKETS.sub("", " ".join(words)).rstrip(TITLE_EDGE)


def _number(value: Decimal) -> str:
    whole, _, fraction = format(value.normalize(), "f").partition(".")
    return f"{whole:0>2}.{fraction}" if fraction else f"{whole:0>2}"


def file_identity(root: Path, name: str) -> LibraryFileIdentity | None:
    """Read a regular workspace file without accepting a symlink, junction or escaped path."""
    require_relative_paths((name,), "A library file")
    path: Path = root / name
    try:
        if any(part.is_symlink() or part.is_junction() for part in (path, *path.parents) if part.is_relative_to(root)):
            return None
        if not path.resolve().is_relative_to(root.resolve()):
            return None
        status: os.stat_result = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(status.st_mode):
        return None
    return LibraryFileIdentity(name, status.st_size, status.st_mtime_ns, status.st_dev, status.st_ino)


def project_library(state: WatchState, root: Path, groups: Sequence[SourceGroup]) -> tuple[LibrarySet, ...]:
    """Reconcile completed sets from provenance, confirmations and the shared discovery inventory."""
    discovered: dict[str, SourceGroup] = {group.group_id: group for group in groups}
    result: list[LibrarySet] = [
        _recorded_set(item, state, root, discovered.get(item.group_id)) for item in state.ready_groups
    ]
    recorded: frozenset[str] = frozenset(item.group_id for item in state.ready_groups)
    result.extend(
        item
        for group in groups
        if group.group_id not in recorded
        and group.directory.is_relative_to(root / READY_DIRECTORY)
        and (item := _legacy_set(group, state, root)) is not None
    )
    return tuple(os_sorted(result, key=lambda item: (item.name, item.set_id)))


def _recorded_set(record: ReadyGroup, state: WatchState, root: Path, group: SourceGroup | None) -> LibrarySet:
    roles: dict[str, str] = dict.fromkeys(record.sources, "source")
    roles.update(dict.fromkeys(record.products, "product"))
    roles.update(dict.fromkeys(record.pending_sources, "pending_source"))
    if group is not None:
        roles.update(
            {name: role for name, role in _discovered_members(group, root, record.target).items() if name not in roles}
        )
    files: tuple[LibraryFile, ...] = tuple(_library_file(root, name, roles[name]) for name in sorted(roles))
    available: bool = _confirmed_main(record.group_id, record.main_result, files, state.products)
    problem: str | None = None
    if not available:
        problem = (
            "library_result_changed"
            if any(item.path == record.main_result and item.identity is not None for item in files)
            else "library_result_missing"
        )
    return LibrarySet(
        record.set_id,
        record.group_id,
        record.stem,
        record.target,
        record.main_result,
        files,
        available,
        problem,
        record.target is WorkflowTarget.TRANSLATE
        and any(Path(name).suffix.casefold() == ".txt" for name in record.sources)
        and record.main_result is not None
        and Path(record.main_result).suffix.casefold() == ".srt",
    )


def _discovered_members(group: SourceGroup, root: Path, target: WorkflowTarget | None) -> dict[str, str]:
    members: dict[str, str] = {}
    for artifact in group.artifacts:
        path: Path | None = artifact.path
        if path is None or not path.is_relative_to(root) or path.parent != group.directory:
            continue
        candidate: ArtifactName | None = classify_artifact(path, WorkflowRoute(WorkspacePlace.READY, target))
        if candidate is not None and candidate.stem.casefold() == group.stem.casefold():
            members[path.relative_to(root).as_posix()] = "product" if candidate.is_derived else "source"
    return members


def _library_file(root: Path, name: str, role: str) -> LibraryFile:
    return LibraryFile(name, role, Path(name).suffix.removeprefix(".").upper(), file_identity(root, name))


def _confirmed_main(
    group_id: str, name: str | None, files: tuple[LibraryFile, ...], products: tuple[ProductConfirmation, ...]
) -> bool:
    identity: LibraryFileIdentity | None = next((item.identity for item in files if item.path == name), None)
    if identity is None:
        return False
    return any(
        item.group_id == group_id
        and item.path == name
        and (item.size, item.modified_ns) == (identity.size, identity.modified_ns)
        for item in products
    )


def _legacy_set(group: SourceGroup, state: WatchState, root: Path) -> LibrarySet | None:
    latest: ProcessingRequest | None = max(
        (item for item in state.requests if item.state is RequestState.SUCCEEDED and group.group_id in item.group_ids),
        key=lambda item: (item.generation, item.accepted_at),
        default=None,
    )
    if latest is None:
        return None
    intent: GroupIntent | None = next((item for item in latest.intents if item.group_id == group.group_id), None)
    products: tuple[str, ...] = tuple(
        item.path
        for item in state.products
        if item.group_id == group.group_id
        and (
            item.artifact_kind.removeprefix("final_") in intent.products.requested_products
            if intent is not None
            else item.request_id == latest.request_id
        )
    )
    headline: str | None = main_product([Path(name).name for name in products])
    primary: str | None = next((name for name in products if Path(name).name == headline), None)
    if primary is None:
        return None
    files: tuple[LibraryFile, ...] = tuple(
        _library_file(root, name, role) for name, role in _discovered_members(group, root, None).items()
    )
    if not _confirmed_main(group.group_id, primary, files, state.products):
        return None
    target: WorkflowTarget | None = intent.target if intent is not None else None
    return LibrarySet(
        group.group_id, group.group_id, group.stem, target, primary, files, True, "library_ownership_unknown"
    )
