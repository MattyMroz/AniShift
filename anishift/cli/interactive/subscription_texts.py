"""Polish texts of subscription drafts, list rows and checks, computed without I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from anishift.application import AIRING_STATUSES, EpisodeListing, ListedEpisode, anilist_date, cut_point, is_target
from anishift.application.events import sanitize_event_message

__all__ = [
    "CHECK_SHOWN_S",
    "SubscriptionDraft",
    "SubscriptionState",
    "check_state",
    "check_text",
    "earlier_episodes",
    "row_columns",
    "row_state",
    "row_summary",
    "subscription_draft",
]

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
"""Polish explanation of each reason a subscription waits for the user."""

_ISSUES: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "season_unrecognized": ("Nie rozpoznano sezonu", "Nie rozpoznano sezonu — usuń i dodaj ponownie"),
        "catalog_conflict": ("Inny sezon w katalogu", "Katalog wskazuje inny sezon — sprawdzam ponownie"),
    }
)
"""Short state and full explanation of each problem that stops a whole subscription."""

_FAILED_CHECKS: Final[frozenset[str]] = frozenset({"source_failed", "rate_limited"})
"""Check outcomes in which a source did not answer."""


@dataclass(frozen=True, slots=True)
class SubscriptionDraft:
    """Sentences of one subscription draft and whether it can be added."""

    lines: tuple[str, ...]
    addable: bool


@dataclass(frozen=True, slots=True)
class SubscriptionState:
    """Short state of a subscription row and its full explanation."""

    text: str
    detail: str


def subscription_draft(listing: EpisodeListing, now: datetime, *, paused: bool) -> SubscriptionDraft | None:
    """Describe the subscription *listing* would get at *now*, or nothing for an entry without future episodes."""
    if listing.status not in AIRING_STATUSES:
        return None
    cut: int | None = cut_point(listing, now)
    if cut is None:
        return SubscriptionDraft(("Nie wiadomo, ile odcinków już wyemitowano · spróbuj później",), False)
    targets: list[ListedEpisode] = [item for item in listing.episodes if is_target(item, now, cut)]
    count: int | None = listing.episode_count
    span: str = f"odcinki od E{cut + 1}" if count is None else _span(cut + 1, count)
    closing: str = "Subskrypcja zamknie się po końcu sezonu." if count is None else "Potem subskrypcja się zamknie."
    lines: list[str] = [f"Pobiorę sam {span} po emisji, {_next_airing(targets, cut + 1, now)}. {closing}"]
    if cut:
        lines.append(f"{earlier_episodes(range(1, cut + 1))}.")
    if paused:
        lines.append("Automat jest wstrzymany: zacznę po wznowieniu.")
    return SubscriptionDraft(tuple(lines), True)


def earlier_episodes(numbers: Iterable[int]) -> str:
    """Name aired episodes a subscription never downloads and how to get them, or nothing without any."""
    shown: list[int] = sorted(numbers)
    if not shown:
        return ""
    label: str = (
        _span(shown[0], shown[-1])
        if shown[-1] - shown[0] + 1 == len(shown)
        else ", ".join(f"E{number}" for number in shown)
    )
    if len(shown) == 1:
        return f"{label} wyszedł przed subskrypcją: pobierz go ręcznie (D na liście odcinków)"
    return f"{label} wyszły przed subskrypcją: pobierz je ręcznie (D na liście odcinków)"


def row_columns(row: Mapping[str, object]) -> tuple[str, str, str]:
    """Return the episode range, the downloaded share and the ready count of one subscription row."""
    start: object = row.get("from_number")
    count: object = row.get("episode_count")
    beyond: object = row.get("beyond_count")
    end: object = beyond if isinstance(beyond, int) else count
    episodes: str = "?"
    if isinstance(start, int):
        episodes = _span(start, end) if isinstance(end, int) else f"E{start}–?"
    total: object = row.get("targets_total")
    downloaded: str = f"{_safe(row.get('downloaded', 0))}/{'?' if total is None else _safe(total)}"
    return episodes, downloaded, _safe(row.get("ready", 0))


def row_summary(row: Mapping[str, object]) -> str:
    """Join the range and progress of one subscription row into one caption."""
    episodes, downloaded, ready = row_columns(row)
    return f"{episodes} · pobrano {downloaded} · gotowe {ready}"


def row_state(row: Mapping[str, object], now: datetime) -> SubscriptionState:
    """Return the one state a subscription row shows at *now*."""
    issue: SubscriptionState | None = _issue(row)
    if issue is not None:
        return issue
    if row.get("paused"):
        return SubscriptionState("Wstrzymana", f"{_PAUSES.get(str(row.get('pause_reason')), 'Wstrzymana')} · W wznów")
    if row.get("review_pending"):
        return SubscriptionState("Weryfikuję", "Sprawdzam przeniesioną subskrypcję")
    checking: object = row.get("checking_number")
    if isinstance(checking, int):
        return _plain(f"Kontrola E{checking}")
    due: object = row.get("due_at")
    if not isinstance(due, str):
        return _plain("Przerwa w emisji" if row.get("catalog_status") == "HIATUS" else "Termin nieznany")
    number: object = row.get("due_number")
    episode: str = f" E{number}" if isinstance(number, int) else ""
    return _dated_state(episode, int((datetime.fromisoformat(due) - now).total_seconds()))


def _plain(text: str) -> SubscriptionState:
    return SubscriptionState(text, text)


def _issue(row: Mapping[str, object]) -> SubscriptionState | None:
    problem: object = row.get("problem")
    if problem is not None:
        text, detail = _ISSUES.get(str(problem), ("Wymaga uwagi", "Wymaga uwagi"))
        return SubscriptionState(text, detail)
    count: object = row.get("episode_count")
    beyond: object = row.get("beyond_count")
    if isinstance(count, int) and isinstance(beyond, int):
        return SubscriptionState(
            "Konflikt liczby odcinków",
            f"AniList podaje {count} {_episodes(count)}, a subskrypcja czeka na E{beyond} · pobierz ręcznie albo usuń",
        )
    return None


def _dated_state(episode: str, remaining: int) -> SubscriptionState:
    if remaining > 0:
        days, rest = divmod(remaining, _DAY_S)
        hours, rest = divmod(rest, _HOUR_S)
        clock: str = f"{hours:02d}:{rest // 60:02d}:{rest % 60:02d}"
        return _plain(f"Emisja{episode} za {days}d {clock}" if days else f"Emisja{episode} za {clock}")
    waited: int = -remaining
    if waited >= _DAILY_AFTER_S:
        since: str = f"od {waited // _DAY_S} dni"
        return SubscriptionState(
            f"Czeka na wydanie{episode} ({since})", f"Czeka na wydanie{episode} ({since}; sprawdzam raz dziennie)"
        )
    since = f"{waited // _HOUR_S} h" if waited >= _HOUR_S else f"{waited // 60} min"
    if waited >= _DAY_S:
        since = "1 dzień" if waited < 2 * _DAY_S else f"{waited // _DAY_S} dni"
    return _plain(f"Czeka na wydanie{episode} (od {since})")


def check_state(check: Mapping[str, object]) -> str:
    """Name one finished subscription check in the few words a list row has room for."""
    if check.get("outcome") in _FAILED_CHECKS:
        return "Sprawdzenie nieudane"
    number: object = check.get("number")
    return f"Sprawdzono E{number}" if isinstance(number, int) else "Sprawdzono listę odcinków"


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


def _next_airing(targets: list[ListedEpisode], first: int, now: datetime) -> str:
    for item in targets:
        moment: datetime | None = anilist_date(item)
        if moment is not None:
            label: str = "najbliższy" if item.number == first else f"najbliższy E{item.number}"
            return f"{label} {_when(moment, now)}"
    return "terminy jeszcze nieznane"


def _when(moment: datetime, now: datetime) -> str:
    local: datetime = moment.astimezone()
    days: int = (local.date() - now.astimezone().date()).days
    if days == 0:
        return f"dziś {local:%H:%M}"
    if days == 1:
        return f"jutro {local:%H:%M}"
    return f"{local:%d.%m %H:%M}"


def _span(first: int, last: int) -> str:
    return f"E{first}" if last <= first else f"E{first}–E{last}"


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
