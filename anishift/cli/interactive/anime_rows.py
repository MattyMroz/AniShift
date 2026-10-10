"""Rows of the catalogue, episode, file and subscription draft screens built from plain values."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from rich.console import Console
from rich.text import Text

from anishift.application import (
    EpisodeFiles,
    EpisodeListing,
    EpisodeReason,
    EpisodeStatus,
    Franchise,
    FranchiseEntry,
    ListedEpisode,
    TitleCandidate,
)
from anishift.cli.interactive.anime_state import AnimeRow
from anishift.cli.interactive.anime_texts import EPISODE_REASON_LABELS, IN_PROGRESS_HINT, episode_status_label, safe
from anishift.cli.interactive.subscription_texts import SubscriptionDraft

__all__ = ["draft_rows", "entry_rows", "episode_row", "file_rows", "special_rows", "text_rows", "title_rows"]

# ── Constants ─────────────────────────────────────────────────────────────────

_DRAFT_ADD: Final[str] = "Dodaj subskrypcję"
"""Draft action that sends the subscription to the owner."""

_DRAFT_CANCEL: Final[str] = "Anuluj"
"""Draft action that returns to the screen the draft was opened from."""

_DRAFT_AIRED: Final[str] = "Już wyemitowane · zaznaczone pobiorę od razu"
"""Draft heading of the aired episodes that Dodaj subskrypcję downloads at once."""

_SUBSCRIBED: Final[str] = "Ten sezon jest już subskrybowany · Enter pokaż"
"""Draft line of a season already followed, leading to its details."""

_EXTRA_FORMATS: Final[frozenset[str]] = frozenset({"OVA", "SPECIAL"})
"""AniList formats U08 lists as related extras of the subscribed season."""

_ENTRY_STATUSES: Final[dict[str, str]] = {
    "FINISHED": "zakończone",
    "RELEASING": "w emisji",
    "NOT_YET_RELEASED": "zapowiedź",
    "HIATUS": "przerwa w emisji",
    "CANCELLED": "anulowany",
    "UNKNOWN": "—",
}
"""Airing labels referring only to the displayed entry."""


def title_rows(candidates: Sequence[TitleCandidate]) -> tuple[AnimeRow, ...]:
    """Return one row per title search result."""
    return tuple(
        AnimeRow(
            str(item.anilist_id),
            item.english or item.romaji,
            date=_year_label(item.year),
            kind=_format_label(item.format),
            status=_ENTRY_STATUSES.get(item.status.value, ""),
        )
        for item in candidates
    )


def entry_rows(entries: Sequence[FranchiseEntry]) -> tuple[AnimeRow, ...]:
    """Return one row per franchise entry."""
    return tuple(
        AnimeRow(
            str(item.anilist_id),
            item.english or item.romaji,
            date=_year_label(item.year),
            kind=_format_label(item.format),
            status=_ENTRY_STATUSES.get(item.status, ""),
        )
        for item in entries
    )


def file_rows(files: EpisodeFiles) -> tuple[AnimeRow, ...]:
    """Return one row per file of an unresolved pack."""
    return tuple(AnimeRow(str(item.index), f"{item.path} · {item.size:,} B") for item in files.files)


def text_rows(values: Sequence[str], width: int) -> tuple[AnimeRow, ...]:
    """Wrap the non-empty values into one row per terminal line."""
    console: Console = Console(width=width)
    return tuple(
        AnimeRow(str(index), line.plain)
        for index, line in enumerate(line for value in values if value for line in Text(value).wrap(console, width))
    )


def episode_row(episode: ListedEpisode, status: EpisodeStatus | None, *, film: bool, eligible: bool) -> AnimeRow:
    """Return the row of one listed episode with its owner state."""
    label: str = episode_status_label(status) if status else ""
    if not label:
        label = EPISODE_REASON_LABELS[
            EpisodeReason.RESULT_MISSING if episode.aired else EpisodeReason.EPISODE_NOT_AIRED
        ]
    detail: str = ""
    if status is not None and status.reason == EpisodeReason.EPISODE_FILE_UNRESOLVED:
        detail = "Nie ustalono pliku w paczce · Enter wskaż plik"
    elif episode.airs_at_fallback:
        detail = f"E{episode.number}: termin emisji niepotwierdzony (ani.zip)"
    return AnimeRow(
        str(episode.number),
        episode.title or ("Film" if film else f"Odcinek {episode.number}"),
        number="Film" if film else str(episode.number),
        date=episode.airs_at.astimezone().strftime("%d.%m.%Y") if episode.airs_at else "—",
        status=label,
        eligible=eligible,
        detail=detail,
        refusal_text=f"E{episode.number} jeszcze nie wyemitowano" if not episode.aired else IN_PROGRESS_HINT,
    )


def special_rows(listing: EpisodeListing, franchise: Franchise | None) -> tuple[AnimeRow, ...]:
    """Return the U08 extras: the season's specials and its related OVA or special entries."""
    extras: tuple[FranchiseEntry, ...] = _related_extras(listing.anilist_id, franchise)
    if not listing.specials and not extras:
        return ()
    return (
        AnimeRow(
            "specials", "Dodatki tego sezonu · pobierasz je osobno z listy wpisów", eligible=False, navigable=False
        ),
        *(
            AnimeRow(
                f"special:{item.key}",
                safe(item.title or item.key),
                number=item.key,
                date=item.airs_on.strftime("%d.%m.%Y") if item.airs_on else "—",
                eligible=False,
                navigable=False,
            )
            for item in listing.specials
        ),
        *(
            AnimeRow(
                f"related:{item.anilist_id}",
                safe(item.english or item.romaji),
                number=item.format or "",
                date=str(item.year or "—"),
                status="Enter otwórz",
                eligible=False,
            )
            for item in extras
        ),
    )


def draft_rows(draft: SubscriptionDraft | None, episodes: Sequence[ListedEpisode], width: int) -> tuple[AnimeRow, ...]:
    """Return the subscription draft: its wrapped lines, the aired episodes to order and its buttons."""
    if draft is None:
        return (AnimeRow("show", _SUBSCRIBED),)
    lines: tuple[AnimeRow, ...] = tuple(
        row
        for index, value in enumerate(draft.lines)
        for row in (
            *((AnimeRow(f"gap{index}", "", navigable=False),) if index else ()),
            *(
                AnimeRow(f"line{index}.{piece}", wrapped.plain)
                for piece, wrapped in enumerate(Text(value).wrap(Console(width=width), width))
            ),
        )
    )
    aired: tuple[AnimeRow, ...] = (
        (
            AnimeRow("gap.aired", "", navigable=False),
            AnimeRow("aired", _DRAFT_AIRED, navigable=False),
            *(
                AnimeRow(
                    f"ep:{item.number}",
                    f"E{item.number}  {item.title or f'Odcinek {item.number}'}",
                    number=str(item.number),
                )
                for item in episodes
            ),
        )
        if episodes
        else ()
    )
    buttons: tuple[AnimeRow, ...] = (
        (AnimeRow("add", _DRAFT_ADD), AnimeRow("cancel", _DRAFT_CANCEL))
        if draft.addable
        else (AnimeRow("cancel", _DRAFT_CANCEL),)
    )
    return (*lines, *aired, AnimeRow("gap", "", navigable=False), *buttons)


def _related_extras(anilist_id: int, franchise: Franchise | None) -> tuple[FranchiseEntry, ...]:
    if franchise is None:
        return ()
    related: set[int] = {
        item.target_id if item.source_id == anilist_id else item.source_id
        for item in franchise.relations
        if anilist_id in {item.source_id, item.target_id}
    }
    return tuple(item for item in franchise.entries if item.anilist_id in related and item.format in _EXTRA_FORMATS)


def _year_label(year: int | None) -> str:
    return str(year) if year else "—"


def _format_label(value: str | None) -> str:
    return "Film" if value == "MOVIE" else value or "—"
