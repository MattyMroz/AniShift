"""Titles, episode rows, set details and actions of the panel's Library tab."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Final

from natsort import os_sort_keygen

from anishift.application import LibraryFile, LibraryLabel, LibrarySet, library_label, normalize_series
from anishift.cli.interactive.actions import PANEL_ACTIONS, Action, ScreenActions
from anishift.cli.interactive.anime_rows import air_date
from anishift.cli.interactive.anime_state import AnimeRow
from anishift.cli.interactive.state_texts import (
    LIBRARY_FROM_NAME,
    LIBRARY_PROBLEMS,
    LIBRARY_READY,
    LIBRARY_TO_CHECK,
    LIBRARY_UNRECOGNIZED,
    RESTORING,
    deleted_sets,
    deleting_sets,
    rows,
    safe_text,
)

__all__ = [
    "EMPTY_LIBRARY",
    "LIBRARY_DELETED",
    "NO_MATCHING_TITLES",
    "UNRECOGNIZED_KEY",
    "EpisodeInfo",
    "LibraryTitle",
    "detail_actions",
    "detail_entries",
    "detail_file",
    "details_label",
    "episode_row",
    "episodes_actions",
    "library_row_id",
    "library_rows",
    "library_titles",
    "set_entry",
    "title_entry",
    "title_row",
    "titles_actions",
    "unsettled_deletions",
]

# ── Constants ─────────────────────────────────────────────────────────────────

type EpisodeInfo = Mapping[int, Mapping[int, tuple[str | None, datetime | None]]]
"""Title and air time of each listed episode number, per AniList entry."""

EMPTY_LIBRARY: Final[str] = "Biblioteka jest pusta"
"""Only line of a Library the owner has inventoried and found empty."""

NO_MATCHING_TITLES: Final[str] = "Brak tytułów pasujących do filtra"
"""Only line of a Library whose titles the filter leaves out."""

LIBRARY_DELETED: Final[str] = "Usunięto · Ctrl+Z cofnij"
"""Library notice kept after a deleted set leaves the list, until the next move."""

UNRECOGNIZED_KEY: Final[str] = "none"
"""Key of the one Library title gathering the sets whose names carry no title, season or episode."""

_NO_VALUE: Final[str] = "—"
"""Cell of an episode title or air date the catalogue does not know."""

_PROBLEM: Final[str] = "Problem"
"""State of a set whose owner problem has no Polish explanation."""

_TITLE_KEY: Final[Callable[[str], object]] = os_sort_keygen()
"""Order Library titles the way the system file browser orders names."""

_FILE_ROLES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "source": "źródło",
        "product": "wynik",
        "pending_source": "źródło · czeka na zwolnienie",
    }
)
"""Roles shown beside files without implying ownership of an external manual reference."""


@dataclass(frozen=True, slots=True)
class LibraryTitle:
    """One Library row: the sets of one series, one entry, one title read from names or the unrecognized names."""

    key: str
    title: str
    sets: tuple[Mapping[str, object], ...]
    cover_id: int | None
    from_name: bool
    problems: int


def library_rows(
    snapshot: Mapping[str, object],
    hidden: Collection[str] = (),
    restoring: Collection[Mapping[str, object]] = (),
) -> list[Mapping[str, object]]:
    """Return listed, problem and restoring sets neither hidden nor being deleted, sorted by title and episode."""
    deleting: set[str] = deleting_sets(snapshot, hidden)
    deleted: set[str] = deleted_sets(snapshot, hidden)
    listed: list[Mapping[str, object]] = [
        *(item for item in rows(snapshot.get("library")) if library_row_id(item) not in deleting),
        *(item for item in rows(snapshot.get("library_problems")) if library_row_id(item) not in deleted),
    ]
    present: set[str] = {library_row_id(item) for item in listed}
    return sorted([*listed, *(item for item in restoring if library_row_id(item) not in present)], key=_order)


def library_titles(
    snapshot: Mapping[str, object],
    hidden: Collection[str] = (),
    restoring: Collection[Mapping[str, object]] = (),
    query: str = "",
) -> list[LibraryTitle]:
    """Group the shown sets into titles containing the normalized *query*, the unrecognized names last."""
    groups: dict[str, list[Mapping[str, object]]] = {}
    names: dict[str, str] = {}
    for item in library_rows(snapshot, hidden, restoring):
        key, title = _title_key(item)
        groups.setdefault(key, []).append(item)
        names.setdefault(key, title)
    wanted: str = normalize_series(query)
    titles: list[LibraryTitle] = [
        _grouped(key, names[key], tuple(sets)) for key, sets in groups.items() if wanted in normalize_series(names[key])
    ]
    return sorted(titles, key=lambda item: (item.key == UNRECOGNIZED_KEY, _TITLE_KEY(item.title), item.key))


def unsettled_deletions(snapshot: Mapping[str, object], hidden: Mapping[str, str]) -> dict[str, str]:
    """Keep hidden sets awaiting the owner's answer or a snapshot reporting their accepted deletion."""
    reported: set[str] = {str(item.get("operation_id")) for item in rows(snapshot.get("deletions"))}
    return {set_id: operation for set_id, operation in hidden.items() if not operation or operation not in reported}


def title_row(title: LibraryTitle) -> AnimeRow:
    """Return the `Tytuł · Odcinki · Stan` table row of one Library title."""
    state: str = LIBRARY_READY
    if title.problems:
        state = f"{title.problems} {LIBRARY_TO_CHECK}"
    elif title.from_name and title.key != UNRECOGNIZED_KEY:
        state = LIBRARY_FROM_NAME
    return AnimeRow(title.key, safe_text(title.title), number=str(len(title.sets)), status=state)


def episode_row(item: Mapping[str, object], info: EpisodeInfo) -> AnimeRow:
    """Return the `Nr · Tytuł · Emisja · Stan` row of one set, its title and date from the catalogue when keyed."""
    anilist_id: int | None = _number(item.get("anilist_id"))
    episode: int | None = _number(item.get("episode"))
    known: tuple[str | None, datetime | None] | None = (
        None if anilist_id is None or episode is None else info.get(anilist_id, {}).get(episode)
    )
    title: str = safe_text(item.get("name", "")) if anilist_id is None else _NO_VALUE
    if known is not None and known[0]:
        title = safe_text(known[0])
    problem: str = LIBRARY_PROBLEMS.get(str(item.get("problem")), _PROBLEM) if item.get("available") is False else ""
    return AnimeRow(
        library_row_id(item),
        title,
        number=_label(item).episode_text,
        date=air_date(None if known is None else known[1]),
        status=f"{RESTORING}…" if item.get("restoring") else problem or LIBRARY_READY,
        detail=problem,
    )


def title_entry(title: LibraryTitle) -> str:
    """Return a Library title with its number of sets for the narrow list."""
    return f"{safe_text(title.title)} · {len(title.sets)}"


def set_entry(item: Mapping[str, object]) -> str:
    """Return the full label of one set for the narrow list."""
    label: str = safe_text(_label(item).text)
    return f"{label} · {RESTORING}" if item.get("restoring") else label


def library_row_id(item: Mapping[str, object]) -> str:
    """Return the set ID identifying a Library row."""
    return str(item.get("set_id", ""))


def detail_actions(*, openable: bool) -> ScreenActions:
    """Return the actions of the files of one set, opening only on an available file row."""
    files: tuple[Action, ...] = (("Enter", "otwórz plik"), ("F", "folder")) if openable else ()
    return ScreenActions((*files, ("Del", "usuń")), (("Ctrl+Z", "cofnij"), *PANEL_ACTIONS))


def titles_actions(*, listed: bool) -> ScreenActions:
    """Return the actions of the Library titles, opening only on a listed title."""
    opening: tuple[Action, ...] = (("Enter", "odcinki"),) if listed else ()
    return ScreenActions((*opening, ("/", "szukaj")), (("Ctrl+Z", "cofnij"), *PANEL_ACTIONS))


def episodes_actions(*, listed: bool) -> ScreenActions:
    """Return the actions of the episodes of one Library title, file actions only on a listed episode."""
    return ScreenActions(
        (("Enter", "obejrzyj"), ("D", "szczegóły"), ("F", "folder"), ("Del", "usuń")) if listed else (),
        (("Ctrl+Z", "cofnij"), *PANEL_ACTIONS),
    )


def detail_entries(details: LibrarySet) -> list[str]:
    """Return the set name, its informational rows and one row per file."""
    entries: list[str] = [safe_text(details.name)]
    if details.target is None:
        entries.append("Cel nierozstrzygnięty · regeneracja wymaga wyboru")
    if details.problem == "library_ownership_unknown":
        entries.append(LIBRARY_PROBLEMS[details.problem])
    if details.provisional_timing:
        entries.append("Czasy robocze · skrypt lektora bez synchronizacji z nagraniem")
    entries.extend(
        f"{safe_text(item.path)} · {item.format} · {_FILE_ROLES[item.role]} · "
        + ("brak" if item.identity is None else f"{item.identity.size:,} B")
        + (" · główny" if item.path == details.main_result else "")
        for item in details.files
    )
    return entries


def detail_file(details: LibrarySet, selected: int) -> LibraryFile | None:
    """Return the file on detail row ``selected``, or None on an informational row."""
    index: int = selected - (len(detail_entries(details)) - len(details.files))
    return details.files[index] if 0 <= index < len(details.files) else None


def details_label(details: LibrarySet) -> LibraryLabel:
    """Return the label of an opened set, named after its series when the owner knows it."""
    return _series_label(details.name, details.series, details.season, details.episode)


def _title_key(item: Mapping[str, object]) -> tuple[str, str]:
    label: LibraryLabel = _label(item)
    series_id: int | None = _number(item.get("series_id"))
    anilist_id: int | None = _number(item.get("anilist_id"))
    if series_id is not None:
        return f"series:{series_id}", label.title
    if anilist_id is not None:
        return f"entry:{anilist_id}", label.title
    if label.season is None and label.episode is None and label.title == str(item.get("name", "")):
        return UNRECOGNIZED_KEY, LIBRARY_UNRECOGNIZED
    return f"name:{normalize_series(label.title)}", label.title


def _grouped(key: str, title: str, sets: tuple[Mapping[str, object], ...]) -> LibraryTitle:
    keyed: list[Mapping[str, object]] = [item for item in sets if _number(item.get("anilist_id")) is not None]
    newest: Mapping[str, object] | None = max(keyed, key=_newest, default=None)
    return LibraryTitle(
        key,
        title,
        sets,
        None if newest is None else _number(newest.get("anilist_id")),
        not keyed,
        sum(item.get("available") is False for item in sets),
    )


def _newest(item: Mapping[str, object]) -> tuple[int, Decimal]:
    label: LibraryLabel = _label(item)
    return label.season or 0, label.episode or Decimal(0)


def _number(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _label(item: Mapping[str, object]) -> LibraryLabel:
    series: object = item.get("series")
    return _series_label(
        str(item.get("name", "")),
        series if isinstance(series, str) and series else None,
        _number(item.get("season")),
        _number(item.get("episode")),
    )


def _series_label(name: str, series: str | None, season: int | None, episode: int | None) -> LibraryLabel:
    label: LibraryLabel = library_label(name)
    if series is None:
        return label
    if season is None or episode is None:
        return replace(label, title=series)
    return LibraryLabel(series, season, Decimal(episode))


def _order(item: Mapping[str, object]) -> tuple[object, ...]:
    label: LibraryLabel = _label(item)
    numbers: tuple[object, ...] = (label.season or 0, label.episode or 0, label.last or 0)
    return (_TITLE_KEY(label.title), label.episode is None, *numbers, library_row_id(item))
