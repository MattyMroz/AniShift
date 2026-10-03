"""Persisted subscriptions, their episode targets and the pure rules that move them."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from anishift.application.episode_identity import IdentityVerdict

if TYPE_CHECKING:
    from collections.abc import Iterable

    from anishift.application.acquisition import ListingRead
    from anishift.application.control import LegacyScope
    from anishift.application.episode_selection import AniZipMapping, EpisodeListing, ListedEpisode, RankedCandidate

__all__ = [
    "AIRING_STATUSES",
    "ATTEMPT_ACTIVE",
    "ATTEMPT_SATISFIED",
    "LEGACY_ORDERED",
    "MAX_ATTEMPTS",
    "MAX_SUBSCRIPTIONS",
    "PauseReason",
    "SubscriptionCheck",
    "SubscriptionProblem",
    "SubscriptionRecord",
    "SubscriptionRow",
    "SubscriptionTarget",
    "TargetFacts",
    "TargetState",
    "after_close",
    "anilist_date",
    "candidate_pair",
    "completed",
    "cut_point",
    "display_order",
    "eligible",
    "is_target",
    "late",
    "merge_listing",
    "next_check_at",
    "next_search_at",
    "search_targets",
    "settle_target",
    "subscription_row",
]

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_ATTEMPTS: Final[int] = 3
"""Attempts one target may consume before it is exhausted."""

MAX_SUBSCRIPTIONS: Final[int] = 100
"""Subscriptions the automation state may hold at once."""

_OPEN_STATES: Final[frozenset[str]] = frozenset({"awaiting_airing", "due", "attempting"})
"""Target states still waiting for a download, the ones that carry a deadline."""

AIRING_STATUSES: Final[frozenset[str]] = frozenset({"RELEASING", "NOT_YET_RELEASED", "HIATUS"})
"""Catalogue statuses of an entry that still has future episodes, the only ones a subscription may follow."""

_ANNOUNCED: Final[str] = "NOT_YET_RELEASED"
"""Catalogue status of an announced entry, whose every episode is a target."""

_HIATUS: Final[str] = "HIATUS"
"""Catalogue status of a paused broadcast, refreshed only daily."""

_FINISHED: Final[str] = "FINISHED"
"""Catalogue status of a finished entry, the only one a subscription may close on."""

_FIRST_DAY: Final[timedelta] = timedelta(hours=24)
"""Age of a due target until which it is searched every quarter hour."""

_THIRD_DAY: Final[timedelta] = timedelta(hours=72)
"""Age of a due target until which it is searched hourly, and daily afterwards."""

_QUARTER_HOUR: Final[timedelta] = timedelta(minutes=15)
"""Search step of a target during its first day."""

_HOUR: Final[timedelta] = timedelta(hours=1)
"""Search step of a target until its third day."""

_DAY: Final[timedelta] = timedelta(hours=24)
"""Search step of an older target and the longest wait between two list refreshes."""

_LATE_AFTER: Final[timedelta] = timedelta(days=7)
"""Age of a due target without a release after which the user is told once."""

LEGACY_ORDERED: Final[str] = "legacy_ordered"
"""Reason of a target the former subscription file already ordered."""

ATTEMPT_ACTIVE: Final[str] = "active"
"""Fact of an attempt or manual order whose transfer is still working."""

ATTEMPT_SATISFIED: Final[str] = "satisfied"
"""Fact of an attempt or manual order whose episode set was handed to Auto."""


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
    due_number: int | None = None
    catalog_status: str | None = None
    episode_count: int | None = None
    beyond_count: int | None = None
    ready: int = 0
    checking_number: int | None = None


@dataclass(frozen=True, slots=True)
class TargetFacts:
    """What the transfers of one target episode prove, projected by the owner from its state.

    ``attempt`` is ``ATTEMPT_ACTIVE``, ``ATTEMPT_SATISFIED`` or the reason the attempt closed;
    ``manual`` is ``ATTEMPT_ACTIVE`` or ``ATTEMPT_SATISFIED`` for a retained manual order of the episode.
    """

    attempt: str | None = None
    manual: str | None = None
    legacy_complete: bool = False
    check_skipped: bool = False


def settle_target(target: SubscriptionTarget, facts: TargetFacts, now: datetime) -> SubscriptionTarget:
    """Return *target* after the transfers of its episode moved, never satisfied by an order alone."""
    if target.state is TargetState.SATISFIED:
        return target
    settled: SubscriptionTarget = replace(target, check_skipped=target.check_skipped or facts.check_skipped)
    if facts.manual == ATTEMPT_SATISFIED or (
        target.state is TargetState.ATTEMPTING and facts.manual is None and facts.attempt == ATTEMPT_SATISFIED
    ):
        return replace(settled, state=TargetState.SATISFIED, reason=None)
    if facts.manual == ATTEMPT_ACTIVE:
        reason: str | None = target.reason if target.state is TargetState.MANUAL else None
        return replace(settled, state=TargetState.MANUAL, reason=reason)
    if target.state is TargetState.ATTEMPTING and facts.attempt not in {ATTEMPT_ACTIVE, ATTEMPT_SATISFIED}:
        return replace(after_close(settled, now), reason=facts.attempt)
    return _released_manual(settled, facts, now) if target.state is TargetState.MANUAL else settled


def _released_manual(target: SubscriptionTarget, facts: TargetFacts, now: datetime) -> SubscriptionTarget:
    if target.reason != LEGACY_ORDERED:
        return after_close(replace(target, reason=None), now)
    return replace(target, state=TargetState.SATISFIED, reason=None) if facts.legacy_complete else target


def late(target: SubscriptionTarget, now: datetime) -> bool:
    """Whether *target* still waits for a release a week after it aired and nobody was told yet."""
    due: datetime | None = _moment(target.due_at)
    return target.state is TargetState.DUE and not target.notified_late and due is not None and now - due >= _LATE_AFTER


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
    nearest: SubscriptionTarget | None = _nearest(record)
    return SubscriptionRow(
        subscription_id=record.subscription_id,
        anilist_id=record.anilist_id,
        title=record.title,
        from_number=record.cut + 1 if record.cut is not None else min(numbers, default=None),
        downloaded=sum(1 for item in record.targets if item.state is TargetState.SATISFIED),
        targets_total=None if record.review_pending else len(record.targets),
        due_at=None if nearest is None else nearest.due_at,
        paused=record.paused,
        pause_reason=None if record.pause_reason is None else record.pause_reason.value,
        problem=None if record.problem is None else record.problem.value,
        review_pending=record.review_pending,
        due_number=None if nearest is None else nearest.number,
        catalog_status=record.catalog_status,
        episode_count=record.episode_count,
        beyond_count=max(
            (number for number in numbers if record.episode_count is not None and number > record.episode_count),
            default=None,
        ),
    )


def display_order(records: Iterable[SubscriptionRecord]) -> tuple[SubscriptionRecord, ...]:
    """Order subscriptions as problem, nearest deadline, no deadline, paused, ties by title."""
    return tuple(sorted(records, key=_display_key))


def anilist_date(episode: ListedEpisode) -> datetime | None:
    """Return the AniList airing time of *episode*, never an ani.zip fallback date."""
    return None if episode.airs_at_fallback else episode.airs_at


def cut_point(listing: EpisodeListing, now: datetime) -> int | None:
    """Count the episodes AniList dates show aired by *now*, or nothing when that count is unknowable."""
    if listing.status == _ANNOUNCED:
        return 0
    if listing.status not in AIRING_STATUSES or listing.schedule_warning is not None:
        return None
    dates: list[datetime] = [moment for item in listing.episodes if (moment := anilist_date(item)) is not None]
    if not dates:
        return None
    return sum(1 for moment in dates if moment <= now)


def is_target(episode: ListedEpisode, subscribed_at: datetime, cut: int | None) -> bool:
    """Whether a subscription made at *subscribed_at* with cut point *cut* follows *episode*."""
    moment: datetime | None = anilist_date(episode)
    if moment is not None:
        return moment > subscribed_at
    return cut is not None and episode.number > cut


def merge_listing(
    record: SubscriptionRecord, read: ListingRead, now: datetime, legacy: Iterable[LegacyScope] = ()
) -> SubscriptionRecord:
    """Return *record* after one list read: new targets, moved deadlines, catalogue conflict and migration review."""
    mapping: AniZipMapping = read.mapping
    if read.live and record.kitsu_id is not None and mapping.kitsu_id != record.kitsu_id:
        return replace(record, problem=SubscriptionProblem.CATALOG_CONFLICT)
    reviewing: bool = record.review_pending
    if record.anilist_id is None or (reviewing and not (read.live and read.listing.schedule_warning is None)):
        return record
    scopes: tuple[LegacyScope, ...] = tuple(legacy) if reviewing else ()
    known: dict[int, SubscriptionTarget] = {item.number: item for item in record.targets}
    targets: dict[int, SubscriptionTarget] = dict(known)
    subscribed: datetime = _required(record.subscribed_at)
    for episode in read.listing.episodes:
        current: SubscriptionTarget | None = known.get(episode.number)
        if current is not None:
            targets[episode.number] = _moved(current, episode, now)
        elif is_target(episode, subscribed, record.cut):
            targets[episode.number] = _new_target(record, episode, now, scopes)
    updated: SubscriptionRecord = replace(record, targets=tuple(targets[number] for number in sorted(targets)))
    if read.listing.schedule_warning is None:
        updated = replace(updated, catalog_status=read.listing.status, episode_count=read.listing.episode_count)
    if read.live:
        updated = replace(
            updated,
            kitsu_id=mapping.kitsu_id,
            mapping=replace(mapping, max_age_s=None),
            refreshed_at=now.isoformat(),
            problem=None if record.problem is SubscriptionProblem.CATALOG_CONFLICT else record.problem,
        )
    return _reviewed(updated) if reviewing else updated


def next_search_at(target: SubscriptionTarget, checked_at: datetime | None) -> datetime | None:
    """Return the first search moment of a due *target* after *checked_at* on its 15 min, hour and day grid."""
    due: datetime | None = _moment(target.due_at)
    if target.state is not TargetState.DUE or due is None:
        return None
    if checked_at is None or checked_at < due:
        return due
    age: timedelta = checked_at - due
    start: timedelta
    step: timedelta
    start, step = (
        (timedelta(0), _QUARTER_HOUR)
        if age < _FIRST_DAY
        else (_FIRST_DAY, _HOUR)
        if age < _THIRD_DAY
        else (_THIRD_DAY, _DAY)
    )
    return due + start + ((age - start) // step + 1) * step


def search_targets(record: SubscriptionRecord, now: datetime, *, manual: bool) -> tuple[SubscriptionTarget, ...]:
    """Return the due targets one check searches: every one on a manual check, otherwise those whose time came."""
    checked: datetime | None = _moment(record.checked_at)
    return tuple(
        item
        for item in record.targets
        if (moment := next_search_at(item, checked)) is not None and (manual or moment <= now)
    )


def next_check_at(record: SubscriptionRecord, now: datetime) -> datetime | None:
    """Return when *record* needs its next check, before any retry delay the owner keeps in memory."""
    if record.anilist_id is None or record.problem is SubscriptionProblem.SEASON_UNRECOGNIZED:
        return None
    if record.review_pending:
        return now
    if record.paused:
        return None
    if record.problem is SubscriptionProblem.CATALOG_CONFLICT:
        return now
    checked: datetime | None = _moment(record.checked_at)
    moments: list[datetime] = [now if checked is None else checked + _DAY]
    if record.catalog_status != _HIATUS:
        moments.extend(
            moment
            for item in record.targets
            if item.state is TargetState.AWAITING_AIRING and (moment := _moment(item.due_at)) is not None
        )
    moments.extend(moment for item in record.targets if (moment := next_search_at(item, checked)) is not None)
    return min(moments)


def candidate_pair(candidate: RankedCandidate) -> str:
    """Return the casefolded release file reference a target records when it tries *candidate*."""
    index: int | None = candidate.stream.file_index
    return f"{candidate.stream.info_hash}:{'' if index is None else index}".casefold()


def eligible(candidate: RankedCandidate, target: SubscriptionTarget, taken: frozenset[str]) -> bool:
    """Whether automation may try *candidate* for *target*: a supported match never tried nor taken elsewhere."""
    pair: str = candidate_pair(candidate)
    return (
        candidate.identity.verdict is IdentityVerdict.MATCH
        and candidate.facts.supported is not False
        and pair not in target.tried
        and pair not in taken
    )


def completed(record: SubscriptionRecord) -> bool:
    """Whether a finished season has every target satisfied and, with a known cut, every episode after it."""
    count: int | None = record.episode_count
    if record.catalog_status != _FINISHED or count is None:
        return False
    numbers: set[int] = {item.number for item in record.targets}
    if any(item.state is not TargetState.SATISFIED for item in record.targets):
        return False
    return record.cut is None or set(range(record.cut + 1, count + 1)) <= numbers


def _new_target(
    record: SubscriptionRecord, episode: ListedEpisode, now: datetime, scopes: tuple[LegacyScope, ...]
) -> SubscriptionTarget:
    due: str | None = _due_at(episode, None, now)
    moment: datetime | None = _moment(due)
    migrated: datetime | None = _moment(record.migrated_at)
    if (
        record.anilist_id is not None
        and migrated is not None
        and moment is not None
        and moment < migrated
        and any(scope.covers(record.anilist_id, episode.number) for scope in scopes)
    ):
        return SubscriptionTarget(episode.number, due, TargetState.MANUAL, reason=LEGACY_ORDERED)
    return SubscriptionTarget(episode.number, due, _open_state(moment, now))


def _moved(target: SubscriptionTarget, episode: ListedEpisode, now: datetime) -> SubscriptionTarget:
    if target.state not in {TargetState.AWAITING_AIRING, TargetState.DUE}:
        return target
    due: str | None = _due_at(episode, target.due_at, now)
    return replace(target, due_at=due, state=_open_state(_moment(due), now))


def _due_at(episode: ListedEpisode, current: str | None, now: datetime) -> str | None:
    moment: datetime | None = anilist_date(episode)
    if moment is not None:
        return moment.isoformat()
    if current is not None:
        return current
    return now.isoformat() if episode.aired else None


def _open_state(due: datetime | None, now: datetime) -> TargetState:
    return TargetState.DUE if due is not None and due <= now else TargetState.AWAITING_AIRING


def _reviewed(record: SubscriptionRecord) -> SubscriptionRecord:
    migrated: datetime | None = _moment(record.migrated_at)
    late: bool = migrated is not None and any(
        item.state in {TargetState.AWAITING_AIRING, TargetState.DUE}
        and (moment := _moment(item.due_at)) is not None
        and moment < migrated
        for item in record.targets
    )
    if late and not record.paused:
        return replace(record, review_pending=False, paused=True, pause_reason=PauseReason.MIGRATED_DUE)
    return replace(record, review_pending=False)


def _required(value: str) -> datetime:
    moment: datetime | None = _moment(value)
    if moment is None:
        msg: str = "A subscription time is required"
        raise ValueError(msg)
    return moment


def _display_key(record: SubscriptionRecord) -> tuple[int, float, str, str]:
    nearest: SubscriptionTarget | None = _nearest(record)
    due: datetime | None = None if nearest is None else _moment(nearest.due_at)
    bucket: int = 0 if record.problem is not None else 3 if record.paused else 1 if due is not None else 2
    deadline: float = due.timestamp() if bucket == 1 and due is not None else 0.0
    return bucket, deadline, record.title.casefold(), record.subscription_id


def _nearest(record: SubscriptionRecord) -> SubscriptionTarget | None:
    dated: list[tuple[datetime, int, SubscriptionTarget]] = [
        (moment, item.number, item)
        for item in record.targets
        if item.state in _OPEN_STATES and (moment := _moment(item.due_at)) is not None
    ]
    return min(dated, key=lambda entry: entry[:2])[2] if dated else None


def _moment(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment: datetime = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        msg: str = "A subscription time carries its timezone"
        raise ValueError(msg)
    return moment
