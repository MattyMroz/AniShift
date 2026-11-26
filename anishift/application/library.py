"""Project completed sets and validate their exact workspace file scope."""

from __future__ import annotations

import os
import re
import stat
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from natsort import os_sorted

from anishift.application.acquisition import normalize_series
from anishift.application.artifacts import SourceGroup
from anishift.application.control import (
    AcquisitionConfirmation,
    LegacyScope,
    ProductConfirmation,
    ReadyGroup,
    WatchState,
    require_relative_paths,
)
from anishift.application.control_views import LibraryFile, LibraryFileIdentity, LibrarySet, TitleSource
from anishift.application.discovery import ArtifactName, classify_artifact
from anishift.application.episode_identity import TECHNICAL, VIDEO_EXTENSIONS
from anishift.application.episode_selection import (
    SEASON_FORMATS,
    EpisodeName,
    JsonObject,
    LibraryGraph,
    ListedEpisode,
    entry_title,
    franchise_traversal,
)
from anishift.application.products import episode_stem, main_product
from anishift.application.workflows import WorkflowRoute, WorkflowTarget, WorkspacePlace
from anishift.paths import READY_DIRECTORY
from anishift.services.torrents.names import (
    before_season,
    episode_range,
    parse_release_name,
    season_hint,
    strip_season,
)

if TYPE_CHECKING:
    from anishift.application.subscription_targets import SubscriptionRecord
    from anishift.services.catalog.types import TitleCandidate
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
SERIES_PART: Final[re.Pattern[str]] = re.compile(r"(?i)\s+(?:part|cour)\s*\d+$")
"""Find the trailing part or cour number of a catalogue title, which numbers a broadcast block, not a series."""
_UNRECORDED: Final[str] = "unrecorded:"
"""Prefix keeping set IDs of groups outside every ready record apart from Library set IDs."""

SERIES_YEAR: Final[re.Pattern[str]] = re.compile(r"\s*\((?:19|20)\d{2}\)")
"""Find a parenthesised year of a catalogue title, which tells remakes apart, not seasons."""
_UNKNOWN_DATE_PART: Final[int] = 9999
"""Sort value of a missing start year, month or day, placing an undated entry after every dated one."""


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


def series_title(title: str) -> str:
    """Return a catalogue title without its season, what follows it, its part or its year, shared by every season."""
    base: str = SERIES_PART.sub("", SERIES_YEAR.sub("", before_season(title))).removesuffix(" -").removesuffix(" :")
    return base or " ".join(title.split())


def episode_file_stem(name: EpisodeName) -> str:
    """Return the stem every file of the downloaded episode set *name* describes shares."""
    return episode_stem(
        series_title(name.title),
        episode_numbering(name.episode, name.title, film=name.film),
        None if name.film else name.episode.title,
    )


def episode_numbering(listed: ListedEpisode, title: str, *, film: bool) -> tuple[int, int] | None:
    """Return the season and episode one catalogue episode is named with, or ``None`` for a film."""
    if film:
        return None
    if listed.season is not None and listed.episode is not None:
        return listed.season, listed.episode
    hint: int | None = season_hint(title)
    return 1 if hint is None else hint, listed.number


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


@dataclass(frozen=True, slots=True)
class DownloadedEpisode:
    """AniList entry, and its local episode when known, one completed set was downloaded as."""

    anilist_id: int
    number: int | None


def assigned_files(acquisition: AcquisitionConfirmation) -> frozenset[str]:
    """Return every workspace name one transfer owns, whether reserved up front or observed later."""
    return frozenset(acquisition.required_files) | frozenset(path for _index, path, _size in acquisition.file_layout)


def downloaded_episodes(state: WatchState) -> dict[str, DownloadedEpisode]:
    """Map the set ID of each completed set AniShift downloaded to the episode it was ordered as."""
    groups: dict[str, DownloadedEpisode] = {}
    sources: dict[str, DownloadedEpisode] = {}
    for acquisition in state.acquisitions:
        groups.update(
            (item.group_id, DownloadedEpisode(item.choice.anilist_id, item.choice.number))
            for item in acquisition.assignments
            if item.group_id is not None
        )
        scope: LegacyScope | None = acquisition.legacy_scope
        if scope is not None:
            sources.update(
                ((Path(acquisition.directory) / name).as_posix(), DownloadedEpisode(scope.anilist_id, scope.number))
                for name in assigned_files(acquisition)
            )
    result: dict[str, DownloadedEpisode] = {}
    for record in state.ready_groups:
        episode: DownloadedEpisode | None = groups.get(record.set_id) or groups.get(record.group_id)
        episode = episode or next((sources[name] for name in record.sources if name in sources), None)
        if episode is not None:
            result[record.set_id] = episode
    return result


@dataclass(frozen=True, slots=True)
class LibrarySeries:
    """Catalogue series one AniList entry belongs to, with the entry's own title for its season."""

    series_id: int
    title: str
    entry_title: str


@dataclass(frozen=True, slots=True)
class EpisodeEntry:
    """AniList entry of one downloaded episode, with its series, entry title and numbering once the series is known."""

    anilist_id: int
    series: str | None = None
    entry_title: str | None = None
    season: int | None = None
    episode: int | None = None


def library_entries(state: WatchState) -> frozenset[int]:
    """Return the AniList entries of subscriptions and of every ordered download."""
    followed: frozenset[int] = frozenset(item.anilist_id for item in state.subscriptions if item.anilist_id is not None)
    ordered: frozenset[int] = frozenset(
        item.choice.anilist_id for acquisition in state.acquisitions for item in acquisition.assignments
    ) | frozenset(item.legacy_scope.anilist_id for item in state.acquisitions if item.legacy_scope is not None)
    return followed | ordered


def episode_entry(
    episode: DownloadedEpisode, series: Mapping[int, LibrarySeries], record: SubscriptionRecord | None
) -> EpisodeEntry:
    """Name one downloaded episode after its series and entry, keeping only the entry while the series is unknown."""
    known: LibrarySeries | None = series.get(episode.anilist_id)
    if known is None:
        return EpisodeEntry(episode.anilist_id)
    numbering: tuple[int, int] | None = (
        None
        if episode.number is None
        else _numbering(known.entry_title, record, episode.number, first=known.series_id == episode.anilist_id)
    )
    return EpisodeEntry(
        episode.anilist_id,
        known.title,
        known.entry_title,
        None if numbering is None else numbering[0],
        None if numbering is None else numbering[1],
    )


def library_series(graph: LibraryGraph, entries: Iterable[int]) -> dict[int, LibrarySeries]:
    """Join the PREQUEL/SEQUEL chains of *entries* sharing a node into series named after their first season."""
    known: tuple[int, ...] = tuple(entry for entry in dict.fromkeys(entries) if entry in graph.nodes)
    chains: list[frozenset[int]] = []
    for entry in known:
        chain: frozenset[int] = franchise_traversal(entry, graph.nodes, graph.queried)[0] | {entry}
        joined: list[frozenset[int]] = [item for item in chains if item & chain]
        chains = [item for item in chains if not item & chain]
        chains.append(chain.union(*joined))
    result: dict[int, LibrarySeries] = {}
    for chain in chains:
        first: JsonObject = min((graph.nodes[item] for item in chain if item in graph.nodes), key=_series_order)
        title: str = series_title(_node_title(first))
        if title:
            result.update(
                (entry, LibrarySeries(first["id"], title, _node_title(graph.nodes[entry])))
                for entry in known
                if entry in chain
            )
    return result


def _series_order(node: JsonObject) -> tuple[bool, int, int, int, int]:
    start: JsonObject = node.get("startDate") or {}
    return (
        node.get("format") not in SEASON_FORMATS,
        start.get("year") or _UNKNOWN_DATE_PART,
        start.get("month") or _UNKNOWN_DATE_PART,
        start.get("day") or _UNKNOWN_DATE_PART,
        node["id"],
    )


def _node_title(node: JsonObject) -> str:
    title: JsonObject = node.get("title") or {}
    return entry_title(title.get("english"), str(title.get("romaji") or ""))


def hand_key(item: LibrarySet) -> tuple[str, int] | None:
    """Return the normalized title and season a hand-added set is searched by, or None for an unreadable name."""
    label: LibraryLabel = library_label(item.name)
    title: str = normalize_series(label.title)
    if not title or (label.season is None and label.episode is None and label.title == item.name):
        return None
    return title, label.season or 1


def hand_titles(sets: Sequence[LibrarySet], state: WatchState) -> dict[tuple[str, int], tuple[str, int | None]]:
    """Map the search key of each hand-added set to the title from its file name and the highest episode."""
    keyed: dict[str, DownloadedEpisode] = downloaded_episodes(state)
    titles: dict[tuple[str, int], tuple[str, int | None]] = {}
    for item in sets:
        key: tuple[str, int] | None = None if item.set_id in keyed else hand_key(item)
        if key is None:
            continue
        label: LibraryLabel = library_label(item.name)
        episode: int | None = None if label.episode is None else int(label.last or label.episode)
        title, highest = titles.get(key, (label.title, None))
        titles[key] = title, max((value for value in (highest, episode) if value is not None), default=None)
    return titles


def recognize(candidates: Sequence[TitleCandidate], title: str, season: int, episode: int | None) -> int | None:
    """Return the only candidate named *title* in *season* holding *episode*, or None when another or a remake fits."""
    wanted: str = normalize_series(title)
    exact: set[int] = set()
    rivals: set[int] = set()
    for candidate in candidates:
        if episode is not None and candidate.episodes is not None and candidate.episodes < episode:
            continue
        for alias in candidate.aliases():
            if (season_hint(alias) or 1) != season:
                continue
            base: str = strip_season(alias)
            if normalize_series(base) == wanted:
                exact.add(candidate.anilist_id)
                rivals.add(candidate.anilist_id)
            if normalize_series(SERIES_YEAR.sub("", base)) == wanted:
                rivals.add(candidate.anilist_id)
    return next(iter(exact)) if len(exact) == 1 and rivals == exact else None


def name_series(
    sets: Sequence[LibrarySet],
    state: WatchState,
    series: Mapping[int, LibrarySeries],
    recognized: Mapping[tuple[str, int], int | None],
) -> tuple[LibrarySet, ...]:
    """Give each downloaded or recognized set its entry, series and title source, leaving others to their names."""
    episodes: dict[str, DownloadedEpisode] = downloaded_episodes(state)
    followed: dict[int, SubscriptionRecord] = {
        item.anilist_id: item for item in state.subscriptions if item.anilist_id is not None
    }
    named: list[LibrarySet] = []
    for item in sets:
        episode: DownloadedEpisode | None = episodes.get(item.set_id)
        if episode is None:
            named.append(_recognized_set(item, series, recognized))
            continue
        entry: EpisodeEntry = episode_entry(episode, series, followed.get(episode.anilist_id))
        named.append(
            replace(
                item,
                anilist_id=entry.anilist_id,
                title_source=TitleSource.KEY,
                series=entry.series,
                entry_title=entry.entry_title,
                season=entry.season,
                episode=entry.episode,
            )
        )
    return tuple(named)


def _numbering(title: str, record: SubscriptionRecord | None, number: int, *, first: bool) -> tuple[int, int] | None:
    mapped: tuple[ListedEpisode, ...] = () if record is None or record.mapping is None else record.mapping.episodes
    listed: ListedEpisode = next((item for item in mapped if item.number == number), ListedEpisode(number))
    if listed.season is None and season_hint(title) is None and not first:
        return None
    return episode_numbering(listed, title, film=False)


def _recognized_set(
    item: LibrarySet, series: Mapping[int, LibrarySeries], recognized: Mapping[tuple[str, int], int | None]
) -> LibrarySet:
    key: tuple[str, int] | None = hand_key(item)
    anilist_id: int | None = None if key is None else recognized.get(key)
    if anilist_id is None:
        return item
    found: LibrarySet = replace(item, anilist_id=anilist_id, title_source=TitleSource.RECOGNIZED)
    known: LibrarySeries | None = series.get(anilist_id)
    if known is None:
        return found
    label: LibraryLabel = library_label(item.name)
    whole: bool = label.episode is not None and label.last is None and label.episode == int(label.episode)
    return replace(
        found,
        series=known.title,
        entry_title=known.entry_title,
        season=(label.season or 1) if whole else None,
        episode=int(label.episode) if whole and label.episode is not None else None,
    )


def file_identity(root: Path, name: str) -> LibraryFileIdentity | None:
    """Read a regular workspace file without accepting a symlink, junction or escaped path."""
    require_relative_paths((name,), "A library file")
    if ":" in name:
        return None
    parts: tuple[str, ...] = Path(name).parts
    chain: tuple[Path, ...] = tuple(root.joinpath(*parts[:index]) for index in range(len(parts) + 1))
    try:
        if any(part.is_symlink() or part.is_junction() for part in chain):
            return None
        status: os.stat_result = chain[-1].lstat()
    except OSError:
        return None
    if not stat.S_ISREG(status.st_mode):
        return None
    return LibraryFileIdentity(name, status.st_size, status.st_mtime_ns, status.st_dev, status.st_ino)


def project_library(state: WatchState, root: Path, groups: Sequence[SourceGroup]) -> tuple[LibrarySet, ...]:
    """Project every recorded set and every ready set on disk, following a recorded set moved inside ``ready``."""
    discovered: dict[str, SourceGroup] = {group.group_id: group for group in groups}
    result: list[LibrarySet] = [
        _recorded_set(item, state, root, discovered.get(item.group_id)) for item in state.ready_groups
    ]
    recorded: frozenset[str] = frozenset(item.group_id for item in state.ready_groups)
    claimed: frozenset[str] = frozenset(
        name for item in state.ready_groups for name in (*item.sources, *item.products, *item.pending_sources)
    )
    loose: list[LibrarySet] = [
        item
        for group in groups
        if group.group_id not in recorded
        and group.directory.is_relative_to(root / READY_DIRECTORY)
        and (item := _loose_set(group, root)) is not None
        and not any(file.path in claimed for file in item.files)
    ]
    moved: dict[str, LibrarySet] = _moved_sets(state, result, loose)
    taken: frozenset[str] = frozenset(item.group_id for item in moved.values())
    result = [moved.get(item.set_id, item) for item in result]
    result.extend(item for item in loose if item.group_id not in taken)
    return tuple(os_sorted(result, key=lambda item: (item.name, item.set_id)))


def unrecorded_set_id(group_id: str) -> str:
    """Return the set ID naming *group_id* outside every ready record, never equal to a Library set ID."""
    return f"{_UNRECORDED}{group_id}"


def unrecorded_group(set_id: str | None) -> str | None:
    """Return the group an unrecorded set ID names, or None for any other ID."""
    return set_id.removeprefix(_UNRECORDED) if set_id is not None and set_id.startswith(_UNRECORDED) else None


def unrecorded_set(group_id: str, name: str, paths: Iterable[str], root: Path) -> LibrarySet:
    """Project workspace files outside every ready record as one set that only deletion and its undo address."""
    files: tuple[LibraryFile, ...] = tuple(_library_file(root, path, "source") for path in sorted(set(paths)))
    return LibrarySet(unrecorded_set_id(group_id), group_id, name, None, None, files, False)


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
        _provisional(record, record.main_result),
    )


def _provisional(record: ReadyGroup, main_result: str | None) -> bool:
    return (
        record.target is WorkflowTarget.TRANSLATE
        and any(Path(name).suffix.casefold() == ".txt" for name in record.sources)
        and main_result is not None
        and Path(main_result).suffix.casefold() == ".srt"
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


def _loose_set(group: SourceGroup, root: Path) -> LibrarySet | None:
    files: tuple[LibraryFile, ...] = tuple(
        _library_file(root, name, role) for name, role in sorted(_discovered_members(group, root, None).items())
    )
    present: dict[str, str] = {
        Path(item.path).name: item.path for item in files if item.role == "product" and item.identity is not None
    }
    headline: str | None = main_product(tuple(present))
    if headline is None:
        return None
    main: str = present[headline]
    ordered: tuple[LibraryFile, ...] = tuple(sorted(files, key=lambda item: item.path == main))
    return LibrarySet(group.group_id, group.group_id, group.stem, None, main, ordered, True)


def _moved_sets(state: WatchState, sets: Sequence[LibrarySet], loose: Sequence[LibrarySet]) -> dict[str, LibrarySet]:
    lost: dict[tuple[int, int], list[ReadyGroup]] = {}
    for record, item in zip(state.ready_groups, sets, strict=True):
        if item.problem != "library_result_missing":
            continue
        confirmed: ProductConfirmation | None = _main_confirmation(record, state.products)
        if confirmed is not None:
            lost.setdefault((confirmed.size, confirmed.modified_ns), []).append(record)
    found: dict[str, list[tuple[LibrarySet, str]]] = {}
    for candidate in loose:
        for file in candidate.files:
            records: list[ReadyGroup] = (
                [] if file.identity is None else lost.get((file.identity.size, file.identity.modified_ns), [])
            )
            if len(records) == 1:
                found.setdefault(records[0].set_id, []).append((candidate, file.path))
    claims: Counter[str] = Counter(candidate.group_id for matches in found.values() for candidate, _path in matches)
    records_by_id: dict[str, ReadyGroup] = {record.set_id: record for record in state.ready_groups}
    return {
        set_id: _moved_set(records_by_id[set_id], matches[0][0], matches[0][1])
        for set_id, matches in found.items()
        if len(matches) == 1 and claims[matches[0][0].group_id] == 1
    }


def _main_confirmation(record: ReadyGroup, products: Sequence[ProductConfirmation]) -> ProductConfirmation | None:
    return next(
        (
            item
            for item in products
            if item.group_id == record.group_id and item.path == record.main_result and item.size >= 0
        ),
        None,
    )


def _moved_set(record: ReadyGroup, found: LibrarySet, main_result: str) -> LibrarySet:
    return replace(
        found,
        set_id=record.set_id,
        target=record.target,
        main_result=main_result,
        files=tuple(sorted(found.files, key=lambda item: item.path == main_result)),
        provisional_timing=_provisional(record, main_result),
    )
