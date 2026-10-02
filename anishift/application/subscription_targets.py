"""Persisted subscriptions, their episode targets and the pure rules that move them."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

    from anishift.application.episode_selection import AniZipMapping

__all__ = [
    "MAX_ATTEMPTS",
    "MAX_SUBSCRIPTIONS",
    "PauseReason",
    "SubscriptionCheck",
    "SubscriptionProblem",
    "SubscriptionRecord",
    "SubscriptionRow",
    "SubscriptionTarget",
    "TargetState",
    "after_close",
    "display_order",
    "subscription_row",
]

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_ATTEMPTS: Final[int] = 3
"""Attempts one target may consume before it is exhausted."""

MAX_SUBSCRIPTIONS: Final[int] = 100
"""Subscriptions the automation state may hold at once."""

_OPEN_STATES: Final[frozenset[str]] = frozenset({"awaiting_airing", "due", "attempting"})
"""Target states still waiting for a download, the ones that carry a deadline."""


class TargetState(StrEnum):
    """Where one subscribed episode stands between airing and a confirmed download."""

    AWAITING_AIRING = "awaiting_airing"
    DUE = "due"
    ATTEMPTING = "attempting"
    SATISFIED = "satisfied"
    EXHAUSTED = "exhausted"
    MANUAL = "manual"


class PauseReason(StrEnum):
    """Why one subscription makes no attempts until the user resumes it."""

    USER = "user"
    MIGRATED_DUE = "migrated_due"
    MIGRATED_MISSING = "migrated_missing"


class SubscriptionProblem(StrEnum):
    """Problem of a whole subscription that stops its attempts."""

    SEASON_UNRECOGNIZED = "season_unrecognized"
    CATALOG_CONFLICT = "catalog_conflict"


@dataclass(frozen=True, slots=True)
class SubscriptionTarget:
    """One regular episode a subscription must obtain, with its deadline and spent attempts."""

    number: int
    due_at: str | None
    state: TargetState
    attempts: int = 0
    tried: tuple[str, ...] = ()
    admission_id: str | None = None
    reason: str | None = None
    notified_late: bool = False
    check_skipped: bool = False

    def __post_init__(self) -> None:
        if type(self.number) is not int or self.number < 1:
            msg: str = "A subscription target is a positive episode number"
            raise ValueError(msg)
        if type(self.attempts) is not int or not 0 <= self.attempts <= MAX_ATTEMPTS:
            msg = "A subscription target spends between zero and MAX_ATTEMPTS attempts"
            raise ValueError(msg)
        if self.state is TargetState.ATTEMPTING and not self.admission_id:
            msg = "An attempting target names its admission"
            raise ValueError(msg)
        if self.state is TargetState.EXHAUSTED and self.attempts != MAX_ATTEMPTS:
            msg = "Only a target that spent every attempt is exhausted"
            raise ValueError(msg)
        if any(not item or item != item.casefold() for item in self.tried):
            msg = "A tried release file is a nonempty casefolded reference"
            raise ValueError(msg)
        _moment(self.due_at)


@dataclass(frozen=True, slots=True)
class SubscriptionCheck:
    """What the last source check of one subscription saw, counted by identity verdict."""

    checked_at: str
    number: int | None
    matching: int
    uncertain: int
    mismatched: int
    outcome: str

    def __post_init__(self) -> None:
        if min(self.matching, self.uncertain, self.mismatched) < 0 or not self.outcome:
            msg: str = "A subscription check carries nonnegative counts and an outcome"
            raise ValueError(msg)
        _moment(self.checked_at)


@dataclass(frozen=True, slots=True)
class SubscriptionRecord:
    """One followed catalogue season, owned and persisted by the automation state."""

    subscription_id: str
    anilist_id: int | None
    title: str
    subscribed_at: str
    cut: int | None
    kitsu_id: int | None = None
    mapping: AniZipMapping | None = None
    paused: bool = False
    pause_reason: PauseReason | None = None
    migrated_at: str | None = None
    review_pending: bool = False
    merged_from: tuple[str, ...] = ()
    problem: SubscriptionProblem | None = None
    catalog_status: str | None = None
    episode_count: int | None = None
    refreshed_at: str | None = None
    checked_at: str | None = None
    last_check: SubscriptionCheck | None = None
    targets: tuple[SubscriptionTarget, ...] = ()
    migrated_from: str | None = None

    def __post_init__(self) -> None:
        if not self.subscription_id or not self.title.strip():
            msg: str = "A subscription requires its identity and a title"
            raise ValueError(msg)
        if self.anilist_id is None and (self.problem is not SubscriptionProblem.SEASON_UNRECOGNIZED or self.targets):
            msg = "Only an unrecognized season subscription has no catalogue entry, and it has no targets"
            raise ValueError(msg)
        if self.anilist_id is not None and (type(self.anilist_id) is not int or self.anilist_id < 1):
            msg = "A subscription follows a positive catalogue entry"
            raise ValueError(msg)
        if (self.review_pending or self.cut is None) and self.migrated_at is None:
            msg = "Only a migrated subscription waits for review or lacks a cut point"
            raise ValueError(msg)
        if self.cut is not None and (type(self.cut) is not int or self.cut < 0):
            msg = "A subscription cut point is a nonnegative episode count"
            raise ValueError(msg)
        if (self.mapping is None) != (self.kitsu_id is None):
            msg = "A subscription keeps an episode mapping exactly when it knows its mapping identity"
            raise ValueError(msg)
        if self.paused != (self.pause_reason is not None):
            msg = "A paused subscription names why it is paused"
            raise ValueError(msg)
        numbers: tuple[int, ...] = tuple(item.number for item in self.targets)
        if len(set(numbers)) != len(numbers):
            msg = "A subscription targets every episode at most once"
            raise ValueError(msg)
        if any(not item for item in self.merged_from):
            msg = "A merged subscription names every identity it absorbed"
            raise ValueError(msg)
        for value in (self.subscribed_at, self.migrated_at, self.refreshed_at, self.checked_at):
            _moment(value)


@dataclass(frozen=True, slots=True)
class SubscriptionRow:
    """Compact list projection of one subscription, never carrying its targets."""

    subscription_id: str
    anilist_id: int | None
    title: str
    from_number: int | None
    downloaded: int
    targets_total: int | None
    due_at: str | None
    paused: bool
    pause_reason: str | None
    problem: str | None
    review_pending: bool


def after_close(target: SubscriptionTarget, now: datetime, n_max: int = MAX_ATTEMPTS) -> SubscriptionTarget:
    """Return *target* after its attempt closed without a download, keeping its admission reference."""
    if target.attempts >= n_max:
        return replace(target, state=TargetState.EXHAUSTED)
    due: datetime | None = _moment(target.due_at)
    if due is None or now < due:
        return replace(target, state=TargetState.AWAITING_AIRING)
    return replace(target, state=TargetState.DUE)


def subscription_row(record: SubscriptionRecord) -> SubscriptionRow:
    """Project *record* into the compact row the subscription list shows."""
    numbers: tuple[int, ...] = tuple(item.number for item in record.targets)
    return SubscriptionRow(
        subscription_id=record.subscription_id,
        anilist_id=record.anilist_id,
        title=record.title,
        from_number=record.cut + 1 if record.cut is not None else min(numbers, default=None),
        downloaded=sum(1 for item in record.targets if item.state is TargetState.SATISFIED),
        targets_total=None if record.review_pending else len(record.targets),
        due_at=_nearest_due(record),
        paused=record.paused,
        pause_reason=None if record.pause_reason is None else record.pause_reason.value,
        problem=None if record.problem is None else record.problem.value,
        review_pending=record.review_pending,
    )


def display_order(records: Iterable[SubscriptionRecord]) -> tuple[SubscriptionRecord, ...]:
    """Order subscriptions as problem, nearest deadline, no deadline, paused, ties by title."""
    return tuple(sorted(records, key=_display_key))


def _display_key(record: SubscriptionRecord) -> tuple[int, float, str, str]:
    due: datetime | None = _moment(_nearest_due(record))
    bucket: int = 0 if record.problem is not None else 3 if record.paused else 1 if due is not None else 2
    deadline: float = due.timestamp() if bucket == 1 and due is not None else 0.0
    return bucket, deadline, record.title.casefold(), record.subscription_id


def _nearest_due(record: SubscriptionRecord) -> str | None:
    dated: list[tuple[datetime, str]] = [
        (moment, item.due_at)
        for item in record.targets
        if item.state in _OPEN_STATES and item.due_at is not None and (moment := _moment(item.due_at)) is not None
    ]
    return min(dated)[1] if dated else None


def _moment(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment: datetime = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        msg: str = "A subscription time carries its timezone"
        raise ValueError(msg)
    return moment
