"""Rows, set details and actions of the panel's Library tab."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from types import MappingProxyType
from typing import Final

from natsort import os_sort_keygen

from anishift.application import LibraryFile, LibraryLabel, LibrarySet, library_label
from anishift.cli.interactive.actions import PANEL_ACTIONS, ScreenActions
from anishift.cli.interactive.anime_state import AnimeRow
from anishift.cli.interactive.state_texts import LIBRARY_PROBLEMS, rows, safe_text

__all__ = [
    "DETAIL_ACTIONS",
    "EMPTY_LIBRARY",
    "LIBRARY_DELETED",
    "detail_entries",
    "detail_file",
    "library_actions",
    "library_row",
    "library_row_id",
    "library_rows",
    "library_title",
    "unsettled_deletions",
]

# ── Constants ─────────────────────────────────────────────────────────────────

EMPTY_LIBRARY: Final[str] = "Biblioteka jest pusta"
"""Only line of a Library the owner has inventoried and found empty."""

LIBRARY_DELETED: Final[str] = "Usunięto · Ctrl+Z cofnij"
"""Library notice kept after a deleted set leaves the list, until the next move."""

DETAIL_ACTIONS: Final[ScreenActions] = ScreenActions(
    (("Enter", "otwórz plik"), ("F", "folder"), ("Del", "usuń")), (("Ctrl+Z", "cofnij"), *PANEL_ACTIONS)
)
"""Actions of the files of one set."""

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


def library_rows(snapshot: Mapping[str, object], hidden: Collection[str] = ()) -> list[Mapping[str, object]]:
    """Return the sets and problem sets neither hidden nor being deleted, naturally sorted by title and episode."""
    deletions: list[Mapping[str, object]] = [
        item for item in rows(snapshot.get("deletions")) if not item.get("restored")
    ]
    deleting: set[str] = {*hidden, *(str(item["set_id"]) for item in deletions if item.get("active"))}
    deleted: set[str] = deleting | {
        str(item["set_id"]) for item in deletions if item.get("total") and item.get("recycled") == item.get("total")
    }
    return sorted(
        [
            *(item for item in rows(snapshot.get("library")) if library_row_id(item) not in deleting),
            *(item for item in rows(snapshot.get("library_problems")) if library_row_id(item) not in deleted),
        ],
        key=_order,
    )


def unsettled_deletions(snapshot: Mapping[str, object], hidden: Mapping[str, str]) -> dict[str, str]:
    """Keep hidden sets awaiting the owner's answer or a snapshot reporting their accepted deletion."""
    listed: set[str] = {library_row_id(item) for item in library_rows(snapshot)}
    reported: set[str] = {str(item.get("operation_id")) for item in rows(snapshot.get("deletions"))}
    return {
        set_id: operation
        for set_id, operation in hidden.items()
        if not operation or (set_id in listed and operation not in reported)
    }


def library_row(item: Mapping[str, object]) -> AnimeRow:
    """Return the `Nazwa · Odcinek` table row of one set."""
    label: LibraryLabel = _label(item)
    return AnimeRow(library_row_id(item), safe_text(label.title), number=label.episode_text)


def library_title(item: Mapping[str, object]) -> str:
    """Return the full label of one set for the narrow list."""
    return safe_text(_label(item).text)


def library_row_id(item: Mapping[str, object]) -> str:
    """Return the set ID identifying a Library row."""
    return str(item.get("set_id", ""))


def library_actions(*, listed: bool) -> ScreenActions:
    """Return the actions of the Library list, file actions only on a listed set."""
    return ScreenActions(
        (("Enter", "otwórz"), ("F", "folder"), ("Del", "usuń")) if listed else (),
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


def _label(item: Mapping[str, object]) -> LibraryLabel:
    return library_label(str(item.get("name", "")))


def _order(item: Mapping[str, object]) -> tuple[object, ...]:
    label: LibraryLabel = _label(item)
    numbers: tuple[object, ...] = (label.season or 0, label.episode or 0, label.last or 0)
    return (_TITLE_KEY(label.title), label.episode is None, *numbers, library_row_id(item))
