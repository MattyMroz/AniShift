"""Standing orders that keep pulling new episodes of one series by one release group."""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import partial
from statistics import median
from typing import TYPE_CHECKING, Final

from anishift.application.acquisition import (
    MIN_RESOLUTION,
    AcquisitionService,
    EpisodeReading,
    ReleaseCatalog,
    ReleaseChoice,
    SeasonContext,
    normalize_series,
    read_episode,
    series_forms,
)
from anishift.application.control import AcquisitionState
from anishift.errors import AniShiftError, ConfigError, ErrorCode, ErrorContext
from anishift.services.torrents.categories import (
    CATEGORY_ENGLISH_TRANSLATED,
    CATEGORY_NON_ENGLISH_TRANSLATED,
    SEARCH_CATEGORIES,
)
from anishift.services.torrents.names import season_hint
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from anishift.application.acquisition import SeriesGroup
    from anishift.application.control import AcquisitionConfirmation, AutomationPolicy
    from anishift.services.catalog import SeasonAiring, TitleCandidate

__all__ = [
    "CHECK_INTERVAL_S",
    "MAX_DELAY_SAMPLES",
    "SCHEMA_VERSION",
    "SUBSCRIPTIONS_FILE_NAME",
    "AiringSource",
    "CheckOutcome",
    "CheckRecorder",
    "EpisodeOrder",
    "EpisodeState",
    "Subscription",
    "SubscriptionAdmission",
    "SubscriptionEnd",
    "SubscriptionService",
    "SubscriptionStore",
    "SubscriptionUpdater",
    "subscription_id",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUBSCRIPTIONS_FILE_NAME: Final[str] = "subscriptions.json"
"""Filename stored beside user settings, outside the media workspace."""

CHECK_INTERVAL_S: Final[float] = 3600.0
"""Delay between two consecutive checks of every subscription."""

CONFIRM_ATTEMPTS: Final[int] = 3
"""How many times a check looks for a just-added release in the client before giving up on it."""

CONFIRM_DELAY_S: Final[float] = 1.0
"""Pause between two looks for a just-added release, because the client adds torrents asynchronously."""

SCHEMA_VERSION: Final[int] = 3
"""Current schema of the persisted subscription file."""

_SUPPORTED_VERSIONS: Final[frozenset[int]] = frozenset({1, 2, SCHEMA_VERSION})
"""Schemas a load still understands, the one migrated on the way in included."""

_BACKUP_SUFFIX_TEMPLATE: Final[str] = ".v{version}.bak"
"""Ending of the original-schema copy retained before a subscription migration."""

MAX_DELAY_SAMPLES: Final[int] = 8
"""Release delays kept per subscription, enough to estimate without storing a history."""

_DISABLED_PROBLEM: Final[str] = "Subscription is disabled"
"""Reported instead of a check when the standing order is switched off."""

_STALE_PROBLEM: Final[str] = "Subscription changed during the check"
"""Reported when the checked order no longer admits releases from that search."""

_CHECKING_PROBLEM: Final[str] = "Subscription is already being checked"
"""Reported when another check still owns the same standing order."""

_ID_LENGTH: Final[int] = 12
"""Hexadecimal characters kept from the digest, short enough to retype in a command."""

_ROOT_KEYS: Final[frozenset[str]] = frozenset({"schema_version", "subscriptions"})
"""Only root keys accepted from a persisted subscription document."""

_ENTRY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "subscription_id",
        "query",
        "series",
        "group",
        "next_episode",
        "min_resolution",
        "taken",
        "added_at",
        "checked_at",
    }
)
"""Keys every serialized subscription must carry."""

_OPTIONAL_ENTRY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "directory",
        "season_index",
        "episode_offset",
        "season_episodes",
        "taken_episodes",
        "enabled",
        "generation",
        "anilist_id",
        "end_state",
        "episodes",
        "release_delay_s",
        "delay_samples_s",
        "search_category",
        "added_by_command",
        "binding_checked_at",
        "binding_attempts",
    }
)
"""Keys a subscription written before seasons, episode numbers and control may omit."""

_EPISODE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "number",
        "airing_at",
        "airing_source",
        "due_at",
        "window_until",
        "state",
        "info_hash",
        "acquisition_id",
    }
)
"""Keys a serialized episode of the ordered range must carry."""

_OPTIONAL_EPISODE_KEYS: Final[frozenset[str]] = frozenset({"checked_at", "attempts", "problem"})
"""Check and retry history that episode records written before schema 3 may omit."""

_INVALID_MESSAGE: Final[str] = "Subscriptions file is invalid"
"""Sentence shown when the stored file cannot be trusted."""

_INVALID_SUGGESTION: Final[str] = "Fix or delete config/subscriptions.json"
"""Only recovery a user can perform on a broken subscription file."""


class SubscriptionEnd(StrEnum):
    """How the followed season ended for one standing order."""

    ACTIVE = "active"
    COMPLETE = "complete"
    MISSING = "missing"
    UNCERTAIN = "uncertain"


class AiringSource(StrEnum):
    """Where the airing time of one episode came from."""

    ANILIST = "anilist"
    USER = "user"
    ESTIMATE = "estimate"


class EpisodeState(StrEnum):
    """What is known about one episode of the ordered range."""

    PENDING = "pending"
    DUE = "due"
    ORDERED = "ordered"
    COMPLETE = "complete"
    EXPIRED = "expired"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class EpisodeOrder:
    """One episode of the ordered range, its deadlines and the release it was handed."""

    number: Decimal
    airing_at: str | None = None
    airing_source: AiringSource | None = None
    due_at: str | None = None
    window_until: str | None = None
    state: EpisodeState = EpisodeState.PENDING
    info_hash: str | None = None
    acquisition_id: str | None = None
    checked_at: str | None = None
    attempts: int = 0
    problem: str | None = None


@dataclass(frozen=True, slots=True)
class Subscription:
    """One standing order: which series and group to follow, and from which episode on."""

    subscription_id: str
    query: str
    series: str
    group: str
    next_episode: Decimal
    min_resolution: int
    taken: frozenset[str]
    added_at: str
    checked_at: str | None
    directory: str | None = None
    season_index: int = 1
    episode_offset: int = 0
    season_episodes: int | None = None
    taken_episodes: tuple[str, ...] = ()
    enabled: bool = True
    generation: int = 1
    anilist_id: int | None = None
    end_state: SubscriptionEnd = SubscriptionEnd.ACTIVE
    episodes: tuple[EpisodeOrder, ...] = ()
    release_delay_s: int | None = None
    delay_samples_s: tuple[int, ...] = ()
    search_category: str | None = None
    added_by_command: str | None = None
    binding_checked_at: str | None = None
    binding_attempts: int = 0

    def __post_init__(self) -> None:
        if self.search_category is not None and self.search_category not in SEARCH_CATEGORIES:
            msg = "A subscription search category must belong to the release index"
            raise ValueError(msg)
        if len(self.delay_samples_s) > MAX_DELAY_SAMPLES:
            msg = "A subscription keeps at most MAX_DELAY_SAMPLES release delays"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What one check of one subscription produced, or why it could not run."""

    subscription: Subscription
    downloaded: int
    problem: str = ""


@dataclass(frozen=True, slots=True)
class SubscriptionOrder:
    """A standing order accepted before or after the first release exists."""

    series: str
    group: str
    query: str
    first_episode: Decimal
    directory_name: str | None = None
    context: SeasonContext | None = None
    anilist_id: int | None = None

    def __post_init__(self) -> None:
        if not self.series.strip() or not self.group.strip() or not self.query.strip():
            msg = "A standing order requires a title, group and search phrase"
            raise ValueError(msg)
        if not self.first_episode.is_finite() or self.first_episode <= 0:
            msg = "A standing order requires a positive episode number"
            raise ValueError(msg)


type SubscriptionAdmission = Callable[[Subscription, Decimal, ReleaseChoice], bool]
"""Decides whether one current release may be handed to the torrent client."""

type CheckRecorder = Callable[
    [Subscription, dict[Decimal, ReleaseChoice], dict[Decimal, ReleaseChoice], frozenset[Decimal] | None],
    Subscription | None,
]
"""Records confirmed releases without replacing a newer standing order."""

type SubscriptionUpdater = Callable[[Subscription, Subscription], bool]
"""Persists a schedule update only while its original subscription is still current."""


def subscription_id(series: str, group: str) -> str:
    """Return the stable identifier of the series and release group pair."""
    seed: str = f"{normalize_series(series)}|{group.casefold()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:_ID_LENGTH]


class SubscriptionStore:
    """Versioned, atomic persistence of every standing order."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path

    def load(self) -> tuple[Subscription, ...]:
        """Read every stored subscription, or none when the file was never written."""
        try:
            text: str = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        except OSError as problem:
            raise _invalid_file() from problem
        try:
            version, subscriptions = _decode_document(json.loads(text))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, InvalidOperation) as problem:
            raise _invalid_file() from problem
        if version != SCHEMA_VERSION:
            self._upgrade(text, subscriptions, version)
        return subscriptions

    def save(self, subscriptions: Sequence[Subscription]) -> None:
        """Atomically persist every subscription, ordered by series and group."""
        ordered: list[Subscription] = sorted(subscriptions, key=_store_order)
        document: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "subscriptions": [_encode(subscription) for subscription in ordered],
        }
        payload: str = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = self._path.with_name(f"{self._path.name}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self._path)

    def _upgrade(self, text: str, subscriptions: Sequence[Subscription], version: int) -> None:
        backup: Path = self._path.with_name(f"{self._path.name}{_BACKUP_SUFFIX_TEMPLATE.format(version=version)}")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8")
        self.save(subscriptions)
        logger.info("Subscriptions migrated", total=len(subscriptions))


class SubscriptionService:
    """Create standing orders and pull every episode they still miss."""

    def __init__(
        self,
        *,
        store: SubscriptionStore,
        acquisition: AcquisitionService,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store: SubscriptionStore = store
        self._acquisition: AcquisitionService = acquisition
        self._clock: Callable[[], datetime] = clock
        self._sleep: Callable[[float], None] = sleep
        self._lock: threading.RLock = threading.RLock()
        self._checking: dict[str, bool] = {}

    def subscribe(
        self,
        query: str,
        choice: ReleaseChoice,
        *,
        directory_name: str | None = None,
        context: SeasonContext | None = None,
    ) -> Subscription:
        """Follow the series and group of *choice* from its episode on, replacing an earlier order."""
        episode: Decimal | None = choice.episode
        if choice.name.is_pack or episode is None:
            msg = "A subscription needs a numbered episode"
            raise ValueError(msg)
        if choice.other_season:
            msg = "A subscription needs a release of the season being followed"
            raise ValueError(msg)
        return self.add(
            choice.name.series,
            choice.name.group or "?",
            query=query,
            first_episode=episode,
            directory_name=directory_name,
            context=context,
        )

    def add(  # noqa: PLR0913 - one standing order is described by every one of these facts
        self,
        series: str,
        group: str,
        *,
        query: str,
        first_episode: Decimal,
        directory_name: str | None = None,
        context: SeasonContext | None = None,
        anilist_id: int | None = None,
        command_id: str | None = None,
    ) -> Subscription:
        """Follow *series* by *group* from *first_episode* on, replacing an earlier order."""
        with self._lock:
            identifier: str = subscription_id(series, group)
            stored: tuple[Subscription, ...] = self._store.load()
            earlier: Subscription | None = _find(stored, identifier)
            if command_id is not None and earlier is not None and earlier.added_by_command == command_id:
                return earlier
            subscription: Subscription = Subscription(
                subscription_id=identifier,
                query=query,
                series=series,
                group=group,
                next_episode=first_episode,
                min_resolution=MIN_RESOLUTION,
                taken=earlier.taken if earlier is not None else frozenset(),
                taken_episodes=earlier.taken_episodes if earlier is not None else (),
                added_at=earlier.added_at if earlier is not None else _timestamp(self._clock()),
                checked_at=None,
                directory=directory_name,
                season_index=context.index if context is not None else 1,
                episode_offset=context.offset if context is not None else 0,
                season_episodes=context.episodes if context is not None else None,
                generation=earlier.generation + 1 if earlier is not None else 1,
                anilist_id=anilist_id if anilist_id is not None or earlier is None else earlier.anilist_id,
                episodes=earlier.episodes if earlier is not None else (),
                enabled=earlier.enabled if earlier is not None else True,
                end_state=earlier.end_state if earlier is not None else SubscriptionEnd.ACTIVE,
                release_delay_s=earlier.release_delay_s if earlier is not None else None,
                delay_samples_s=earlier.delay_samples_s if earlier is not None else (),
                search_category=earlier.search_category if earlier is not None else None,
                added_by_command=command_id,
                binding_checked_at=earlier.binding_checked_at if earlier is not None else None,
                binding_attempts=earlier.binding_attempts if earlier is not None else 0,
            )
            remaining: list[Subscription] = [item for item in stored if item.subscription_id != identifier]
            remaining.append(subscription)
            self._store.save(remaining)
            self._invalidate_check(identifier)
            logger.info("Subscription stored", replaced=earlier is not None, total=len(remaining))
            return subscription

    def add_order(self, order: SubscriptionOrder, command_id: str) -> Subscription:
        """Apply a durable addition once, including replay after a lost confirmation."""
        return self.add(
            order.series,
            order.group,
            query=order.query,
            first_episode=order.first_episode,
            directory_name=order.directory_name,
            context=order.context,
            anilist_id=order.anilist_id,
            command_id=command_id,
        )

    def enable(self, subscription_id: str) -> Subscription:
        """Let that standing order look for episodes again, keeping everything it already took."""
        return self._switch(subscription_id, enabled=True)

    def disable(self, subscription_id: str) -> Subscription:
        """Stop the automatic checks of that standing order, keeping its range and history."""
        return self._switch(subscription_id, enabled=False)

    def set_anilist_id(self, subscription_id: str, anilist_id: int | None) -> Subscription:
        """Bind that standing order to the catalog entry proving which season it follows."""
        with self._lock:
            current: Subscription = self._required(subscription_id)
            if current.anilist_id == anilist_id:
                return current
            updated: Subscription = replace(current, anilist_id=anilist_id, generation=current.generation + 1)
            self._replace(updated)
            self._invalidate_check(subscription_id)
            logger.info("Subscription bound to a catalog entry", generation=updated.generation)
            return updated

    def list(self) -> tuple[Subscription, ...]:
        """Return every stored subscription."""
        with self._lock:
            return self._store.load()

    def remove(self, subscription_id: str) -> bool:
        """Drop the subscription with that identifier, reporting whether it existed."""
        with self._lock:
            stored: tuple[Subscription, ...] = self._store.load()
            remaining: tuple[Subscription, ...] = tuple(
                item for item in stored if item.subscription_id != subscription_id
            )
            if len(remaining) == len(stored):
                return False
            self._store.save(remaining)
            self._invalidate_check(subscription_id)
            logger.info("Subscription removed", total=len(remaining))
            return True

    def check(
        self,
        subscription: Subscription,
        *,
        admit: SubscriptionAdmission | None = None,
        record: CheckRecorder | None = None,
        episodes: frozenset[Decimal] | None = None,
    ) -> CheckOutcome:
        """Download every episode *subscription* still misses and record what was taken."""
        return self._run_check(
            subscription, lambda: self._check(subscription, admit, record or self.record_check, episodes)
        )

    def _run_check(self, subscription: Subscription, action: Callable[[], CheckOutcome]) -> CheckOutcome:
        if not subscription.enabled:
            return CheckOutcome(subscription, 0, problem=_DISABLED_PROBLEM)
        with self._lock:
            if subscription.subscription_id in self._checking:
                return CheckOutcome(subscription, 0, problem=_CHECKING_PROBLEM)
            if not self._current(subscription):
                return CheckOutcome(subscription, 0, problem=_STALE_PROBLEM)
            self._checking[subscription.subscription_id] = True
        try:
            with self._acquisition.requests("subscription"):
                return action()
        finally:
            with self._lock:
                self._checking.pop(subscription.subscription_id)

    def _check(
        self,
        subscription: Subscription,
        admit: SubscriptionAdmission | None,
        record: CheckRecorder,
        episodes: frozenset[Decimal] | None,
    ) -> CheckOutcome:
        try:
            offered: dict[Decimal, ReleaseChoice] = self._offered(subscription, episodes)
            taken_hashes: frozenset[str] = frozenset(info_hash.casefold() for info_hash in subscription.taken)
            taken_episodes: frozenset[Decimal] = frozenset(Decimal(number) for number in subscription.taken_episodes)
            selected: dict[Decimal, ReleaseChoice] = {
                episode: choice
                for episode, choice in offered.items()
                if episode not in taken_episodes
                and choice.release.info_hash.casefold() not in taken_hashes
                and (episodes is None or episode in episodes)
            }
            queued: frozenset[str] = self._acquisition.queued_hashes() if selected else frozenset()
            chosen: tuple[ReleaseChoice, ...] = self._download(subscription, selected, queued, admit)
            admitted: dict[Decimal, ReleaseChoice] = {
                episode: choice
                for episode, choice in selected.items()
                if choice in chosen or choice.release.info_hash.casefold() in queued
            }
            confirmed: dict[Decimal, ReleaseChoice] = self._confirmed(admitted, queued) if admitted else {}
            sent: int = sum(1 for choice in chosen if choice in confirmed.values())
            updated: Subscription | None = record(subscription, confirmed, offered, episodes)
            if updated is None:
                current: Subscription | None = _find(self.list(), subscription.subscription_id)
                return CheckOutcome(current or subscription, sent, problem=_STALE_PROBLEM)
        except AniShiftError as problem:
            logger.warning("Subscription check failed", error_class=type(problem).__name__)
            return CheckOutcome(subscription, 0, problem=str(problem))
        logger.info("Subscription checked", downloaded=sent, taken=len(updated.taken))
        return CheckOutcome(updated, sent)

    def _download(
        self,
        subscription: Subscription,
        selected: dict[Decimal, ReleaseChoice],
        queued: frozenset[str],
        admit: SubscriptionAdmission | None,
    ) -> tuple[ReleaseChoice, ...]:
        chosen: list[ReleaseChoice] = []
        for episode in sorted(selected):
            choice: ReleaseChoice = selected[episode]
            if choice.release.info_hash.casefold() in queued:
                continue
            with self._lock:
                current: bool = self._current(subscription)
            if not current:
                break
            if admit is not None and not admit(subscription, episode, choice):
                continue
            self._acquisition.download((choice,), directory_name=subscription.directory)
            chosen.append(choice)
        return tuple(chosen)

    def check_all(
        self,
        *,
        admit: SubscriptionAdmission | None = None,
        record: CheckRecorder | None = None,
    ) -> tuple[CheckOutcome, ...]:
        """Check every active subscription in stored order; a failing one does not stop the rest."""
        return tuple(
            self.check(subscription, admit=admit, record=record)
            for subscription in self.list()
            if subscription.enabled and subscription.end_state is SubscriptionEnd.ACTIVE
        )

    def is_current(self, subscription: Subscription) -> bool:
        """Check whether that snapshot still admits releases from its search."""
        with self._lock:
            return self._current(subscription)

    def update(self, original: Subscription, updated: Subscription) -> bool:
        """Persist a current schedule update without replacing another control decision."""
        with self._lock:
            if not self._current(original):
                return False
            self._replace(updated)
            return True

    def next_check_at(self, policy: AutomationPolicy) -> datetime | None:
        """Return the next due subscription action, or no automatic work."""
        now: datetime = self._clock()
        with self._lock:
            deadlines: list[datetime] = [
                deadline
                for subscription in self._store.load()
                if subscription.subscription_id not in self._checking
                and (deadline := self._deadline(subscription, policy, now)) is not None
            ]
        return min(deadlines) if deadlines else None

    def _deadline(self, subscription: Subscription, policy: AutomationPolicy, now: datetime) -> datetime | None:
        deadline: datetime | None = _subscription_deadline(subscription, policy, now)
        if deadline is None:
            return None
        if subscription.anilist_id is None:
            release: datetime = max(
                _release_deadline(subscription, policy, now),
                datetime.fromtimestamp(self._acquisition.blocked_until(("nyaa",)), UTC),
            )
            binding: datetime | None = _binding_deadline(subscription, policy, now)
            if binding is None:
                return release
            return min(
                release, max(binding, datetime.fromtimestamp(self._acquisition.blocked_until(("anilist",)), UTC))
            )
        providers: tuple[str, ...] = ("nyaa", "anilist") if subscription.anilist_id is not None else ("nyaa",)
        until: float = self._acquisition.blocked_until(providers)
        return max(deadline, datetime.fromtimestamp(until, UTC))

    def reconcile_sources(self, confirmations: Sequence[AcquisitionConfirmation]) -> None:
        """Project confirmed transfer states into their linked episode orders."""
        by_subscription: dict[str, dict[Decimal, AcquisitionConfirmation]] = {}
        for item in confirmations:
            if item.subscription_id is not None and item.episode is not None:
                by_subscription.setdefault(item.subscription_id, {})[Decimal(item.episode)] = item
        with self._lock:
            stored: tuple[Subscription, ...] = self._store.load()
            updated: tuple[Subscription, ...] = tuple(
                _with_sources(item, by_subscription.get(item.subscription_id, {})) for item in stored
            )
            if updated != stored:
                self._store.save(updated)

    def check_due(
        self,
        policy: AutomationPolicy,
        *,
        admit: SubscriptionAdmission | None = None,
        record: CheckRecorder | None = None,
        update: SubscriptionUpdater | None = None,
        refresh_calendar: bool = False,
    ) -> tuple[CheckOutcome, ...]:
        """Check due episode windows and leave future or exhausted orders quiet."""
        now: datetime = self._clock()
        save: SubscriptionUpdater = update or self.update
        outcomes: list[CheckOutcome] = []
        for subscription in self.list():
            deadline: datetime | None = self._deadline(subscription, policy, now)
            if not subscription.enabled or subscription.end_state is not SubscriptionEnd.ACTIVE:
                continue
            if not refresh_calendar and (deadline is None or deadline > now):
                continue
            outcomes.append(
                self._run_check(
                    subscription,
                    partial(self._check_due, subscription, policy, save, admit, record),
                )
            )
        return tuple(outcomes)

    def _check_due(
        self,
        subscription: Subscription,
        policy: AutomationPolicy,
        update: SubscriptionUpdater,
        admit: SubscriptionAdmission | None,
        record: CheckRecorder | None,
    ) -> CheckOutcome:
        now: datetime = self._clock()
        if subscription.anilist_id is None:
            return self._check_unbound(subscription, policy, update, admit, record)
        try:
            schedule: SeasonAiring = self._acquisition.airing_schedule(subscription.anilist_id)
        except AniShiftError as problem:
            failed = _failed_check(subscription, policy, now, str(problem.context.code))
            update(subscription, failed)
            return CheckOutcome(failed, 0, str(problem))
        prepared: Subscription = _finish_subscription(
            _expire_windows(_apply_schedule(subscription, schedule, policy, now), now)
        )
        if not update(subscription, prepared):
            return CheckOutcome(subscription, 0, _STALE_PROBLEM)
        numbers: frozenset[Decimal] = _due_episodes(prepared, policy, now)
        if not numbers:
            return CheckOutcome(prepared, 0)
        outcome: CheckOutcome = self._check(prepared, admit, record or self.record_check, numbers)
        if outcome.problem and self.is_current(prepared):
            failed = _failed_check(prepared, policy, now, outcome.problem)
            update(prepared, failed)
            return replace(outcome, subscription=failed)
        return outcome

    def _check_unbound(
        self,
        subscription: Subscription,
        policy: AutomationPolicy,
        update: SubscriptionUpdater,
        admit: SubscriptionAdmission | None,
        record: CheckRecorder | None,
    ) -> CheckOutcome:
        now: datetime = self._clock()
        due: datetime | None = _binding_deadline(subscription, policy, now)
        if due is not None and due <= now and self._acquisition.blocked_until(("anilist",)) <= now.timestamp():
            bound: Subscription = replace(
                self._bind_calendar(subscription),
                binding_checked_at=_timestamp(now),
                binding_attempts=subscription.binding_attempts + 1,
            )
            if not update(subscription, bound):
                return CheckOutcome(subscription, 0, _STALE_PROBLEM)
            subscription = bound
        if subscription.anilist_id is not None:
            return self._check_due(subscription, policy, update, admit, record)
        if _release_deadline(subscription, policy, now) > now:
            return CheckOutcome(subscription, 0)
        outcome: CheckOutcome = self._check(subscription, admit, record or self.record_check, None)
        if outcome.problem and self.is_current(subscription):
            failed: Subscription = replace(subscription, checked_at=_timestamp(self._clock()))
            if update(subscription, failed):
                return replace(outcome, subscription=failed)
        return outcome

    def _bind_calendar(self, subscription: Subscription) -> Subscription:
        if self._acquisition.blocked_until(("anilist",)) > self._clock().timestamp():
            return subscription
        try:
            forms: frozenset[str] = series_forms(subscription.series)
            candidates: tuple[TitleCandidate, ...] = tuple(
                candidate
                for candidate in self._acquisition.find_titles(subscription.series)
                if any(forms & series_forms(alias) for alias in candidate.aliases())
            )
            if len(candidates) != 1:
                return subscription
            candidate: TitleCandidate = candidates[0]
            context: SeasonContext = self._acquisition.season_context(candidate)
            if context.index != _context(subscription).index or context.offset != subscription.episode_offset:
                return subscription
            return replace(subscription, anilist_id=candidate.anilist_id)
        except AniShiftError as problem:
            logger.warning("Subscription calendar binding failed", error_class=type(problem).__name__)
            return subscription

    def record_check(
        self,
        subscription: Subscription,
        confirmed: dict[Decimal, ReleaseChoice],
        offered: dict[Decimal, ReleaseChoice],
        checked: frozenset[Decimal] | None = None,
    ) -> Subscription | None:
        """Record a current check or leave a changed order untouched."""
        with self._lock:
            if not self._current(subscription):
                return None
            updated: Subscription = self._advance(subscription, confirmed, offered, checked)
            if updated.anilist_id is not None:
                updated = _finish_subscription(updated)
            self._replace(updated)
            return updated

    def _switch(self, subscription_id: str, *, enabled: bool) -> Subscription:
        with self._lock:
            current: Subscription = self._required(subscription_id)
            if current.enabled == enabled:
                return current
            updated: Subscription = replace(current, enabled=enabled, generation=current.generation + 1)
            self._replace(updated)
            self._invalidate_check(subscription_id)
            logger.info("Subscription switched", enabled=enabled, generation=updated.generation)
            return updated

    def _required(self, subscription_id: str) -> Subscription:
        current: Subscription | None = _find(self._store.load(), subscription_id)
        if current is None:
            msg = "No subscription carries that identifier"
            raise ValueError(msg)
        return current

    def _current(self, subscription: Subscription) -> bool:
        current: Subscription | None = _find(self._store.load(), subscription.subscription_id)
        return (
            current is not None
            and current.enabled
            and current.end_state is SubscriptionEnd.ACTIVE
            and current == subscription
            and self._checking.get(subscription.subscription_id, True)
        )

    def _invalidate_check(self, subscription_id: str) -> None:
        if subscription_id in self._checking:
            self._checking[subscription_id] = False

    def _offered(
        self, subscription: Subscription, episodes: frozenset[Decimal] | None = None
    ) -> dict[Decimal, ReleaseChoice]:
        context: SeasonContext | None = _context(subscription)
        catalog: ReleaseCatalog = self._search(subscription, subscription.query)
        with self._lock:
            if not self._current(subscription):
                return {}
        offered: dict[Decimal, ReleaseChoice] = _new_episodes(catalog, subscription, context)
        next_episode: Decimal = min(episodes) if episodes else subscription.next_episode
        if next_episode in offered or not _is_whole(next_episode):
            return offered
        _keep_best(offered, _new_episodes(self._catch_up(subscription, next_episode), subscription, context))
        return offered

    def _catch_up(self, subscription: Subscription, episode: Decimal) -> ReleaseCatalog:
        query: str = f"{subscription.query} {int(episode):02d}"
        try:
            return self._search(subscription, query)
        except AniShiftError as problem:
            logger.warning("Subscription catch-up search failed", error_class=type(problem).__name__)
            return ReleaseCatalog((), 0)

    def _search(self, subscription: Subscription, query: str) -> ReleaseCatalog:
        categories: tuple[str, ...] = (
            (subscription.search_category,) if subscription.search_category else SEARCH_CATEGORIES
        )
        phrase: str = query if subscription.group.casefold() in query.casefold() else f"{query} {subscription.group}"
        return self._acquisition.search(phrase, categories=categories)

    def _confirmed(
        self, selected: dict[Decimal, ReleaseChoice], queued: frozenset[str]
    ) -> dict[Decimal, ReleaseChoice]:
        present: frozenset[str] = queued
        for attempt in range(CONFIRM_ATTEMPTS):
            missing: bool = any(choice.release.info_hash.casefold() not in present for choice in selected.values())
            if not missing:
                break
            if attempt:
                self._sleep(CONFIRM_DELAY_S)
            present = self._acquisition.queued_hashes()
        confirmed: dict[Decimal, ReleaseChoice] = {
            episode: choice for episode, choice in selected.items() if choice.release.info_hash.casefold() in present
        }
        if len(confirmed) != len(selected):
            logger.warning("Torrent client did not keep every added release", dropped=len(selected) - len(confirmed))
        return confirmed

    def _advance(
        self,
        subscription: Subscription,
        selected: dict[Decimal, ReleaseChoice],
        offered: dict[Decimal, ReleaseChoice],
        checked: frozenset[Decimal] | None = None,
    ) -> Subscription:
        checked_at: str = _timestamp(self._clock())
        if subscription.search_category is None and offered:
            choice: ReleaseChoice = next(iter(offered.values()))
            subscription = replace(
                subscription,
                search_category=(
                    CATEGORY_NON_ENGLISH_TRANSLATED
                    if choice.release.subtitle_language == "fr"
                    else CATEGORY_ENGLISH_TRANSLATED
                ),
            )
        taken_episodes: frozenset[Decimal] = frozenset(Decimal(number) for number in subscription.taken_episodes)
        taken_hashes: frozenset[str] = frozenset(info_hash.casefold() for info_hash in subscription.taken)
        known: dict[Decimal, ReleaseChoice] = {
            episode: choice
            for episode, choice in offered.items()
            if episode in selected or episode in taken_episodes or choice.release.info_hash.casefold() in taken_hashes
        }
        ordered: tuple[EpisodeOrder, ...] = _record_checked(subscription.episodes, selected, checked, checked_at)
        if selected and subscription.anilist_id is not None:
            ordered = _next_calendar_lookup(ordered, max(selected), subscription.season_episodes)
        if not known:
            return replace(subscription, checked_at=checked_at, episodes=ordered)
        taken: frozenset[str] = subscription.taken | {choice.release.info_hash for choice in selected.values()}
        episodes: tuple[str, ...] = _recorded_episodes(subscription.taken_episodes, known)
        return replace(
            subscription,
            next_episode=_next_episode(subscription.next_episode, episodes),
            taken=taken,
            taken_episodes=episodes,
            checked_at=checked_at,
            episodes=ordered,
            delay_samples_s=_release_delays(subscription, selected),
        )

    def _replace(self, subscription: Subscription) -> None:
        stored: tuple[Subscription, ...] = self._store.load()
        self._store.save(
            [subscription if item.subscription_id == subscription.subscription_id else item for item in stored]
        )


def _next_calendar_lookup(
    episodes: tuple[EpisodeOrder, ...],
    last: Decimal,
    count: int | None,
) -> tuple[EpisodeOrder, ...]:
    number: Decimal | None = next(
        (item.number for item in episodes if item.number > last and item.state is EpisodeState.PENDING), None
    )
    if number is None and count is None:
        return (*episodes, EpisodeOrder(Decimal(math.floor(last) + 1)))
    return tuple(
        replace(item, checked_at=None) if item.number == number and item.due_at is None else item for item in episodes
    )


def _with_sources(subscription: Subscription, confirmations: dict[Decimal, AcquisitionConfirmation]) -> Subscription:
    if not confirmations:
        return subscription
    episodes: dict[Decimal, EpisodeOrder] = {item.number: item for item in subscription.episodes}
    for number, confirmation in confirmations.items():
        episode: EpisodeOrder = episodes.get(number, EpisodeOrder(number))
        state: EpisodeState = (
            EpisodeState.COMPLETE if confirmation.state is AcquisitionState.COMPLETE else EpisodeState.ORDERED
        )
        episodes[number] = replace(
            episode,
            state=state,
            acquisition_id=confirmation.operation_id,
            info_hash=confirmation.info_hash,
            problem=None if state is EpisodeState.COMPLETE else episode.problem,
        )
    return _finish_subscription(replace(subscription, episodes=tuple(episodes[number] for number in sorted(episodes))))


def _release_delays(subscription: Subscription, confirmed: dict[Decimal, ReleaseChoice]) -> tuple[int, ...]:
    samples: list[int] = list(subscription.delay_samples_s)
    for episode in subscription.episodes:
        choice: ReleaseChoice | None = confirmed.get(episode.number)
        if choice is None or choice.name.is_pack or choice.name.version not in {None, 1}:
            continue
        published: datetime | None = choice.release.published
        airing: datetime | None = _moment(episode.airing_at)
        end: datetime | None = _moment(episode.window_until)
        if published is not None and airing is not None and end is not None and airing <= published <= end:
            samples.append(int((published - airing).total_seconds()))
    return tuple(samples[-MAX_DELAY_SAMPLES:])


def _moment(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment: datetime = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        msg = "A subscription deadline must include its UTC offset"
        raise ValueError(msg)
    return moment.astimezone(UTC)


def _episode_deadline(episode: EpisodeOrder, policy: AutomationPolicy, now: datetime) -> datetime | None:
    if episode.state not in {EpisodeState.PENDING, EpisodeState.DUE}:
        return None
    due: datetime | None = _moment(episode.due_at)
    checked: datetime | None = _moment(episode.checked_at)
    if due is None:
        return now if checked is None else None
    if checked is not None:
        delay: int = policy.recheck_interval_s
        if episode.problem and policy.retry_delays_s:
            delay = policy.retry_delays_s[min(max(0, episode.attempts - 1), len(policy.retry_delays_s) - 1)]
        due = max(due, checked + timedelta(seconds=delay))
    end: datetime | None = _moment(episode.window_until)
    return min(due, end) if end is not None else due


def _subscription_deadline(subscription: Subscription, policy: AutomationPolicy, now: datetime) -> datetime | None:
    if not subscription.enabled or subscription.end_state is not SubscriptionEnd.ACTIVE:
        return None
    if subscription.anilist_id is None:
        release: datetime = _release_deadline(subscription, policy, now)
        binding: datetime | None = _binding_deadline(subscription, policy, now)
        return min(release, binding) if binding is not None else release
    if not subscription.episodes:
        return now
    deadlines: list[datetime] = [
        deadline
        for episode in subscription.episodes
        if (deadline := _episode_deadline(episode, policy, now)) is not None
    ]
    return min(deadlines) if deadlines else None


def _release_deadline(subscription: Subscription, policy: AutomationPolicy, now: datetime) -> datetime:
    checked: datetime | None = _moment(subscription.checked_at)
    return checked + timedelta(seconds=policy.recheck_interval_s) if checked is not None else now


def _binding_deadline(subscription: Subscription, policy: AutomationPolicy, now: datetime) -> datetime | None:
    if subscription.binding_attempts >= policy.external_retry_budget:
        return None
    checked: datetime | None = _moment(subscription.binding_checked_at)
    if checked is None:
        return now
    delay: int = (
        policy.retry_delays_s[min(max(0, subscription.binding_attempts - 1), len(policy.retry_delays_s) - 1)]
        if policy.retry_delays_s
        else policy.recheck_interval_s
    )
    return checked + timedelta(seconds=delay)


def _due_episodes(subscription: Subscription, policy: AutomationPolicy, now: datetime) -> frozenset[Decimal]:
    return frozenset(
        episode.number
        for episode in subscription.episodes
        if episode.airing_at is not None
        and (deadline := _episode_deadline(episode, policy, now)) is not None
        and deadline <= now
    )


def _apply_schedule(
    subscription: Subscription, schedule: SeasonAiring, policy: AutomationPolicy, now: datetime
) -> Subscription:
    known: dict[Decimal, EpisodeOrder] = {episode.number: episode for episode in subscription.episodes}
    for number in subscription.taken_episodes:
        known.setdefault(Decimal(number), EpisodeOrder(Decimal(number), state=EpisodeState.ORDERED))
    dates: dict[Decimal, datetime | None] = {
        Decimal(episode.episode): episode.airing_at for episode in schedule.episodes
    }
    count: int | None = schedule.episode_count or subscription.season_episodes
    numbers: set[Decimal] = set(known) | {number for number in dates if number >= subscription.next_episode}
    if count is not None:
        numbers.update(Decimal(number) for number in range(math.ceil(subscription.next_episode), count + 1))
    elif subscription.next_episode not in numbers:
        numbers.add(subscription.next_episode)
    delay: int = (
        subscription.release_delay_s
        if subscription.release_delay_s is not None
        else (
            int(median(subscription.delay_samples_s))
            if subscription.delay_samples_s
            else policy.release_delay_default_s
        )
    )
    episodes: tuple[EpisodeOrder, ...] = tuple(
        _scheduled_episode(known.get(number, EpisodeOrder(number)), dates, schedule, delay, policy, now)
        for number in sorted(numbers)
    )
    end: SubscriptionEnd = subscription.end_state
    if count is not None and subscription.next_episode > count and not episodes:
        end = SubscriptionEnd.COMPLETE
    return replace(subscription, season_episodes=count, episodes=episodes, end_state=end)


def _scheduled_episode(  # noqa: PLR0913
    episode: EpisodeOrder,
    dates: dict[Decimal, datetime | None],
    schedule: SeasonAiring,
    delay: int,
    policy: AutomationPolicy,
    now: datetime,
) -> EpisodeOrder:
    if episode.state not in {EpisodeState.PENDING, EpisodeState.DUE}:
        return episode
    airing: datetime | None = _moment(episode.airing_at)
    if episode.airing_source is not AiringSource.USER and episode.number in dates:
        airing = dates[episode.number]
    if airing is not None:
        if airing == _moment(episode.airing_at) and episode.due_at is not None:
            return episode
        due: datetime = airing + timedelta(seconds=delay)
        return replace(
            episode,
            airing_at=_timestamp(airing),
            airing_source=episode.airing_source if episode.airing_source is AiringSource.USER else AiringSource.ANILIST,
            due_at=_timestamp(due),
            window_until=_timestamp(due + timedelta(seconds=policy.search_window_s)),
        )
    start: datetime | None = (
        datetime.combine(schedule.start_date, datetime.min.time(), tzinfo=UTC)
        if schedule.start_date is not None
        else None
    )
    return replace(
        episode,
        airing_at=None,
        due_at=_timestamp(start) if start is not None and start > now else None,
        window_until=None,
        checked_at=_timestamp(now),
        attempts=0,
        problem=None,
    )


def _expire_windows(subscription: Subscription, now: datetime) -> Subscription:
    episodes: tuple[EpisodeOrder, ...] = tuple(
        replace(episode, state=EpisodeState.EXPIRED)
        if episode.state in {EpisodeState.PENDING, EpisodeState.DUE}
        and (end := _moment(episode.window_until)) is not None
        and now >= end
        else episode
        for episode in subscription.episodes
    )
    return replace(subscription, episodes=episodes)


def _finish_subscription(subscription: Subscription) -> Subscription:
    if subscription.season_episodes is None or not subscription.episodes:
        return subscription
    states: dict[Decimal, EpisodeOrder] = {episode.number: episode for episode in subscription.episodes}
    numbers: range = range(math.ceil(min(states)), subscription.season_episodes + 1)
    if any(Decimal(number) not in states for number in numbers):
        return subscription
    if any(episode.state in {EpisodeState.PENDING, EpisodeState.DUE} for episode in states.values()):
        return subscription
    end: SubscriptionEnd = SubscriptionEnd.COMPLETE
    if any(episode.state is EpisodeState.ORDERED or episode.problem for episode in states.values()):
        end = SubscriptionEnd.UNCERTAIN
    elif any(episode.state in {EpisodeState.MISSING, EpisodeState.EXPIRED} for episode in states.values()):
        end = SubscriptionEnd.MISSING
    return replace(subscription, end_state=end)


def _failed_check(subscription: Subscription, policy: AutomationPolicy, now: datetime, problem: str) -> Subscription:
    pending: tuple[EpisodeOrder, ...] = subscription.episodes or (EpisodeOrder(subscription.next_episode),)
    episodes: list[EpisodeOrder] = []
    for episode in pending:
        deadline: datetime | None = _episode_deadline(episode, policy, now)
        if deadline is None or deadline > now:
            episodes.append(episode)
            continue
        attempts: int = episode.attempts + 1
        episodes.append(
            replace(
                episode,
                checked_at=_timestamp(now),
                attempts=attempts,
                problem=problem,
                due_at=episode.due_at or _timestamp(now),
                state=EpisodeState.MISSING if attempts >= policy.external_retry_budget else episode.state,
            )
        )
    return _finish_subscription(replace(subscription, episodes=tuple(episodes)))


def _record_checked(
    episodes: tuple[EpisodeOrder, ...],
    confirmed: dict[Decimal, ReleaseChoice],
    checked: frozenset[Decimal] | None,
    now: str,
) -> tuple[EpisodeOrder, ...]:
    entries: dict[Decimal, EpisodeOrder] = {episode.number: episode for episode in episodes}
    for number in checked or ():
        episode: EpisodeOrder = entries.get(number, EpisodeOrder(number))
        entries[number] = replace(episode, checked_at=now, attempts=0, problem=None)
    for number, choice in confirmed.items():
        episode = entries.get(number, EpisodeOrder(number))
        entries[number] = replace(
            episode,
            state=EpisodeState.ORDERED,
            info_hash=choice.release.info_hash.casefold(),
            checked_at=now,
            attempts=0,
            problem=None,
        )
    return tuple(entries[number] for number in sorted(entries))


def _context(subscription: Subscription) -> SeasonContext:
    index: int = subscription.season_index
    if index == 1:
        index = season_hint(subscription.series) or index
    return SeasonContext(
        index=index,
        offset=subscription.episode_offset,
        episodes=subscription.season_episodes,
    )


def _new_episodes(
    catalog: ReleaseCatalog,
    subscription: Subscription,
    context: SeasonContext | None,
) -> dict[Decimal, ReleaseChoice]:
    series: frozenset[str] = series_forms(subscription.series)
    group: str = subscription.group.casefold()
    best: dict[Decimal, ReleaseChoice] = {}
    for series_group in catalog.groups:
        if not _matches(series_group, subscription, series, group):
            continue
        for choice in series_group.choices:
            reading: EpisodeReading = read_episode(choice.name, context)
            episode: Decimal | None = reading.episode
            if episode is None or reading.other_season or choice.name.is_pack:
                continue
            if episode < subscription.next_episode:
                continue
            if subscription.season_episodes is not None and episode > subscription.season_episodes:
                continue
            current: ReleaseChoice | None = best.get(episode)
            if current is None or _quality(choice) > _quality(current):
                best[episode] = choice
    return best


def _matches(series_group: SeriesGroup, subscription: Subscription, series: frozenset[str], group: str) -> bool:
    if series_group.group.casefold() != group or not series_forms(series_group.series) & series:
        return False
    wanted: int | None = season_hint(subscription.series)
    offered: int | None = season_hint(series_group.series)
    return wanted is None or offered is None or wanted == offered


def _keep_best(offered: dict[Decimal, ReleaseChoice], extra: dict[Decimal, ReleaseChoice]) -> None:
    for episode, choice in extra.items():
        current: ReleaseChoice | None = offered.get(episode)
        if current is None or _quality(choice) > _quality(current):
            offered[episode] = choice


def _recorded_episodes(stored: tuple[str, ...], offered: dict[Decimal, ReleaseChoice]) -> tuple[str, ...]:
    numbers: set[str] = {*stored, *(str(episode) for episode in offered)}
    return tuple(sorted(numbers, key=Decimal))


def _next_episode(current: Decimal, recorded: tuple[str, ...]) -> Decimal:
    taken: set[int] = set()
    for value in recorded:
        number: Decimal = Decimal(value)
        if _is_whole(number):
            taken.add(int(number))
    candidate: int = math.ceil(current)
    while candidate in taken:
        candidate += 1
    return Decimal(candidate)


def _is_whole(episode: Decimal) -> bool:
    return episode == int(episode)


def _quality(choice: ReleaseChoice) -> tuple[int, int]:
    return (choice.name.version or 0, choice.release.seeders)


def _find(subscriptions: Sequence[Subscription], identifier: str) -> Subscription | None:
    return next((item for item in subscriptions if item.subscription_id == identifier), None)


def _store_order(subscription: Subscription) -> tuple[str, str]:
    return (subscription.series.casefold(), subscription.group.casefold())


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _invalid_file() -> ConfigError:
    return ConfigError(
        context=ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=_INVALID_MESSAGE,
            suggestion=_INVALID_SUGGESTION,
        )
    )


def _encode(subscription: Subscription) -> dict[str, object]:
    return {
        "subscription_id": subscription.subscription_id,
        "query": subscription.query,
        "series": subscription.series,
        "group": subscription.group,
        "next_episode": str(subscription.next_episode),
        "min_resolution": subscription.min_resolution,
        "taken": sorted(subscription.taken),
        "added_at": subscription.added_at,
        "checked_at": subscription.checked_at,
        "directory": subscription.directory,
        "season_index": subscription.season_index,
        "episode_offset": subscription.episode_offset,
        "season_episodes": subscription.season_episodes,
        "taken_episodes": list(subscription.taken_episodes),
        "enabled": subscription.enabled,
        "generation": subscription.generation,
        "anilist_id": subscription.anilist_id,
        "end_state": subscription.end_state.value,
        "episodes": [_encode_episode(episode) for episode in subscription.episodes],
        "release_delay_s": subscription.release_delay_s,
        "delay_samples_s": list(subscription.delay_samples_s),
        "search_category": subscription.search_category,
        "added_by_command": subscription.added_by_command,
        "binding_checked_at": subscription.binding_checked_at,
        "binding_attempts": subscription.binding_attempts,
    }


def _encode_episode(episode: EpisodeOrder) -> dict[str, object]:
    return {
        "number": str(episode.number),
        "airing_at": episode.airing_at,
        "airing_source": None if episode.airing_source is None else episode.airing_source.value,
        "due_at": episode.due_at,
        "window_until": episode.window_until,
        "state": episode.state.value,
        "info_hash": episode.info_hash,
        "acquisition_id": episode.acquisition_id,
        "checked_at": episode.checked_at,
        "attempts": episode.attempts,
        "problem": episode.problem,
    }


def _decode_document(raw: object) -> tuple[int, tuple[Subscription, ...]]:
    document: dict[str, object] = _strict_object(raw, _ROOT_KEYS, "subscription file")
    schema_version: object = document["schema_version"]
    entries: object = document["subscriptions"]
    if type(schema_version) is not int or schema_version not in _SUPPORTED_VERSIONS:
        msg = "Unsupported subscription schema version"
        raise ValueError(msg)
    if not isinstance(entries, list):
        msg = "Serialized subscriptions must be a list"
        raise TypeError(msg)
    return schema_version, tuple(_decode_entry(entry, schema_version) for entry in entries)


def _decode_entry(raw: object, version: int) -> Subscription:
    document: dict[str, object] = _strict_object(raw, _ENTRY_KEYS, "subscription", optional=_OPTIONAL_ENTRY_KEYS)
    min_resolution: object = document["min_resolution"]
    taken: object = document["taken"]
    checked_at: object = document["checked_at"]
    if type(min_resolution) is not int or not isinstance(taken, list):
        msg = "Subscription quality and taken releases carry invalid types"
        raise TypeError(msg)
    if checked_at is not None and not isinstance(checked_at, str):
        msg = "Subscription check time must be text or null"
        raise TypeError(msg)
    subscription: Subscription = Subscription(
        subscription_id=_required_string(document, "subscription_id"),
        query=_required_string(document, "query"),
        series=_required_string(document, "series"),
        group=_required_string(document, "group"),
        next_episode=Decimal(_required_string(document, "next_episode")),
        min_resolution=min_resolution,
        taken=frozenset(_list_string(value) for value in taken),
        added_at=_required_string(document, "added_at"),
        checked_at=checked_at,
        directory=_optional_string(document, "directory"),
        season_index=_optional_count(document, "season_index", 1),
        episode_offset=_optional_count(document, "episode_offset", 0),
        season_episodes=_optional_int(document, "season_episodes"),
        taken_episodes=_optional_strings(document, "taken_episodes"),
        enabled=_optional_flag(document, "enabled", default=True),
        generation=_optional_count(document, "generation", 1),
        anilist_id=_optional_int(document, "anilist_id"),
        end_state=SubscriptionEnd(_optional_string(document, "end_state") or SubscriptionEnd.ACTIVE.value),
        episodes=_optional_episodes(document, "episodes"),
        release_delay_s=_optional_int(document, "release_delay_s"),
        delay_samples_s=_optional_whole_numbers(document, "delay_samples_s"),
        search_category=_optional_string(document, "search_category"),
        added_by_command=_optional_string(document, "added_by_command"),
        binding_checked_at=_optional_string(document, "binding_checked_at"),
        binding_attempts=_optional_count(document, "binding_attempts", 0),
    )
    return _migrate_v1(subscription) if version == 1 else subscription


def _migrate_v1(subscription: Subscription) -> Subscription:
    episodes: tuple[EpisodeOrder, ...] = tuple(
        EpisodeOrder(number=Decimal(number), state=EpisodeState.ORDERED) for number in subscription.taken_episodes
    )
    return replace(subscription, episodes=episodes)


def _decode_episode(raw: object) -> EpisodeOrder:
    document: dict[str, object] = _strict_object(raw, _EPISODE_KEYS, "episode", optional=_OPTIONAL_EPISODE_KEYS)
    airing_source: str | None = _optional_string(document, "airing_source")
    return EpisodeOrder(
        number=Decimal(_required_string(document, "number")),
        airing_at=_optional_string(document, "airing_at"),
        airing_source=None if airing_source is None else AiringSource(airing_source),
        due_at=_optional_string(document, "due_at"),
        window_until=_optional_string(document, "window_until"),
        state=EpisodeState(_required_string(document, "state")),
        info_hash=_optional_string(document, "info_hash"),
        acquisition_id=_optional_string(document, "acquisition_id"),
        checked_at=_optional_string(document, "checked_at"),
        attempts=_optional_count(document, "attempts", 0),
        problem=_optional_string(document, "problem"),
    )


def _strict_object(
    raw: object,
    expected_keys: frozenset[str],
    label: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> dict[str, object]:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        msg = f"Serialized {label} must be an object with text keys"
        raise TypeError(msg)
    document: dict[str, object] = raw
    if frozenset(document) - optional != expected_keys:
        msg = f"Serialized {label} has missing or unknown fields"
        raise ValueError(msg)
    return document


def _required_string(document: dict[str, object], key: str) -> str:
    value: object = document[key]
    if not isinstance(value, str):
        msg = f"Subscription field {key!r} must be text"
        raise TypeError(msg)
    return value


def _optional_string(document: dict[str, object], key: str) -> str | None:
    value: object = document.get(key)
    if value is not None and not isinstance(value, str):
        msg = f"Subscription field {key!r} must be text or null"
        raise TypeError(msg)
    return value


def _optional_int(document: dict[str, object], key: str) -> int | None:
    value: object = document.get(key)
    if value is not None and type(value) is not int:
        msg = f"Subscription field {key!r} must be a whole number or null"
        raise TypeError(msg)
    return value


def _optional_count(document: dict[str, object], key: str, default: int) -> int:
    value: int | None = _optional_int(document, key)
    return default if value is None else value


def _optional_flag(document: dict[str, object], key: str, *, default: bool) -> bool:
    value: object = document.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        msg = f"Subscription field {key!r} must be a flag or null"
        raise TypeError(msg)
    return value


def _optional_episodes(document: dict[str, object], key: str) -> tuple[EpisodeOrder, ...]:
    value: object = document.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = f"Subscription field {key!r} must be a list of episodes or null"
        raise TypeError(msg)
    return tuple(_decode_episode(item) for item in value)


def _optional_whole_numbers(document: dict[str, object], key: str) -> tuple[int, ...]:
    value: object = document.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        msg = f"Subscription field {key!r} must be a list of whole numbers or null"
        raise TypeError(msg)
    return tuple(value)


def _optional_strings(document: dict[str, object], key: str) -> tuple[str, ...]:
    value: object = document.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = f"Subscription field {key!r} must be a list of text or null"
        raise TypeError(msg)
    return tuple(_list_string(item) for item in value)


def _list_string(value: object) -> str:
    if not isinstance(value, str):
        msg = "Subscription collection values must be text"
        raise TypeError(msg)
    return value
