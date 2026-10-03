"""Polish texts of subscription drafts, list rows and checks, computed without I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from anishift.application import AIRING_STATUSES, EpisodeListing, ListedEpisode, anilist_date, cut_point, is_target
from anishift.application.events import sanitize_event_message

__all__ = ["CHECK_SHOWN_S", "SubscriptionDraft", "check_text", "row_state", "subscription_draft"]

# ── Constants ─────────────────────────────────────────────────────────────────

CHECK_SHOWN_S: Final[float] = 10.0
"""Seconds a requested check result stays in its subscription row."""

_DAY_S: Final[int] = 86400
"""Seconds in one day."""

_HOUR_S: Final[int] = 3600
"""Seconds in one hour."""

_DAILY_AFTER_S: Final[int] = 72 * _HOUR_S
"""Wait after which the owner looks for a missing episode only once a day."""

_PAUSES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "user": "Wstrzymana",
        "migrated_due": "Wstrzymana — przeniesiona; zaległe odcinki",
        "migrated_missing": "Wstrzymana — zakończona przez starą wersję",
    }
)
"""Polish state of each reason a subscription waits for the user."""

_ISSUES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "season_unrecognized": "Nie rozpoznano sezonu — usuń i dodaj ponownie",
        "catalog_conflict": "Katalog wskazuje inny sezon — sprawdzam ponownie",
    }
)
"""Polish state of each problem that stops a whole subscription."""


@dataclass(frozen=True, slots=True)
class SubscriptionDraft:
    """Lines of one subscription draft and whether it can be added."""

    lines: tuple[str, ...]
    addable: bool


def subscription_draft(listing: EpisodeListing, title: str, now: datetime, *, paused: bool) -> SubscriptionDraft | None:
    """Describe the subscription *listing* would get at *now*, or nothing for an entry without future episodes."""
    if listing.status not in AIRING_STATUSES:
        return None
    heading: str = f"Tytuł:     {_safe(title)}"
    cut: int | None = cut_point(listing, now)
    if cut is None:
        return SubscriptionDraft((heading, "", "Nie wiadomo, ile odcinków już wyemitowano · spróbuj później"), False)
    targets: list[ListedEpisode] = [item for item in listing.episodes if is_target(item, now, cut)]
    lines: list[str] = [
        heading,
        f"Od odc.:   {cut + 1}",
        f"Później:   {_next_airing(targets, cut)}",
        f"Koniec:    {_end(listing.episode_count)}",
        "Dodatki:   nie; pobierasz je osobno z listy wpisów",
    ]
    if cut:
        aired: str = "E1" if cut == 1 else f"E1–E{cut}"
        lines.extend(("", f"Wyemitowane {aired} nie wchodzą do subskrypcji", "· zaznacz je i D, aby pobrać"))
    if paused:
        lines.extend(("", "AniShift jest wstrzymany — subskrypcja zacznie działać po wznowieniu"))
    return SubscriptionDraft(tuple(lines), True)


def row_state(row: Mapping[str, object], now: datetime) -> str:
    """Return the one state the second line of a subscription row shows at *now*."""
    issue: str | None = _issue(row)
    if issue is not None:
        return issue
    if row.get("paused"):
        return f"{_PAUSES.get(str(row.get('pause_reason')), 'Wstrzymana')} · W wznów"
    if row.get("review_pending"):
        return "Sprawdzam przeniesioną subskrypcję"
    checking: object = row.get("checking_number")
    if isinstance(checking, int):
        return f"Kontrola E{checking}"
    due: object = row.get("due_at")
    if not isinstance(due, str):
        return "Przerwa w emisji" if row.get("catalog_status") == "HIATUS" else "Termin nieznany"
    number: object = row.get("due_number")
    episode: str = f" E{number}" if isinstance(number, int) else ""
    return _dated_state(episode, int((datetime.fromisoformat(due) - now).total_seconds()))


def _issue(row: Mapping[str, object]) -> str | None:
    problem: object = row.get("problem")
    if problem is not None:
        return _ISSUES.get(str(problem), "Wymaga uwagi")
    count: object = row.get("episode_count")
    beyond: object = row.get("beyond_count")
    if isinstance(count, int) and isinstance(beyond, int):
        return (
            f"AniList podaje {count} {_episodes(count)}, a subskrypcja czeka na E{beyond} · pobierz ręcznie albo usuń"
        )
    return None


def _dated_state(episode: str, remaining: int) -> str:
    if remaining > 0:
        days, rest = divmod(remaining, _DAY_S)
        hours, rest = divmod(rest, _HOUR_S)
        clock: str = f"{hours:02d}:{rest // 60:02d}:{rest % 60:02d}"
        return f"Emisja{episode} za {days} d {clock}" if days else f"Emisja{episode} za {clock}"
    waited: int = -remaining
    if waited >= _DAILY_AFTER_S:
        return f"Czeka na wydanie{episode} (od {waited // _DAY_S} dni; sprawdzam raz dziennie)"
    since: str = f"{waited // _HOUR_S} h" if waited >= _HOUR_S else f"{waited // 60} min"
    if waited >= _DAY_S:
        since = "1 dzień" if waited < 2 * _DAY_S else f"{waited // _DAY_S} dni"
    return f"Czeka na wydanie{episode} (od {since})"


def check_text(check: Mapping[str, object]) -> str:
    """Summarize one subscription check the way the list and the details show it."""
    number: object = check.get("number")
    outcome: object = check.get("outcome")
    source: str = f"E{number}: źródło wydań" if isinstance(number, int) else "Katalog odcinków"
    if outcome == "source_failed":
        return f"{source} nie odpowiada · ponowię później"
    if outcome == "rate_limited":
        return f"{source} ogranicza zapytania · ponowię później"
    if not isinstance(number, int):
        return "Sprawdzono listę odcinków"
    counts: tuple[int, int, int] = (
        _count(check.get("matching")),
        _count(check.get("uncertain")),
        _count(check.get("mismatched")),
    )
    total: int = sum(counts)
    if not total:
        return f"Sprawdzono E{number}: brak wydań w źródle"
    noun: str = "kandydat" if total == 1 else "kandydatów"
    text: str = f"Sprawdzono E{number}: {total} {noun}, {counts[0]} zgodnych"
    if counts[1] or counts[2]:
        text += f" ({counts[1]} niepewnych, {counts[2]} niezgodnych)"
    return text + (" · propozycja zapisana" if outcome == "proposed" else "")


def _next_airing(targets: list[ListedEpisode], cut: int) -> str:
    for item in targets:
        moment: datetime | None = anilist_date(item)
        if moment is not None:
            return f"E{item.number} — emisja {moment.astimezone():%d.%m %H:%M}"
    return f"od E{cut + 1} — termin nieznany"


def _end(count: int | None) -> str:
    if count is None:
        return "gdy sezon się zakończy i wszystkie odcinki będą pobrane"
    return f"po pobraniu E{count} (sezon ma {count} {_episodes(count)})"


def _episodes(count: int) -> str:
    if count == 1:
        return "odcinek"
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return "odcinki"
    return "odcinków"


def _count(value: object) -> int:
    return value if isinstance(value, int) else 0


def _safe(value: object) -> str:
    return sanitize_event_message(str(value)) or ""
