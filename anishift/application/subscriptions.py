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
from secrets import token_hex
from statistics import median
from typing import TYPE_CHECKING, Final

from anishift.application.acquisition import (
    CONFIRM_ATTEMPTS,
    CONFIRM_DELAY_S,
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
    "EpisodeRepeat",
    "EpisodeState",
    "Subscription",
    "SubscriptionAdmission",
    "SubscriptionEnd",
    "SubscriptionService",
    "SubscriptionStore",
    "SubscriptionUpdater",
    "in_range",
    "repeat_of",
    "resolve_subscription_id",
    "selectable_episodes",
    "subscription_id",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUBSCRIPTIONS_FILE_NAME: Final[str] = "subscriptions.json"
"""Filename stored beside user settings, outside the media workspace."""

CHECK_INTERVAL_S: Final[float] = 3600.0
"""Delay between two consecutive checks of every subscription."""

SCHEMA_VERSION: Final[int] = 4
"""Current schema of the persisted subscription file."""

_SUPPORTED_VERSIONS: Final[frozenset[int]] = frozenset({1, 2, 3, SCHEMA_VERSION})
"""Schemas a load still understands, the ones migrated on the way in included."""

_REPEAT_ID_BYTES: Final[int] = 8
"""Random bytes making the identity of one explicit repeat unique."""

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
        "future_from",
        "repeats",
        "calendar_checked_at",
        "calendar_attempts",
        "calendar_status",
        "calendar_problem",
        "calendar_start_at",
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

_OPTIONAL_EPISODE_KEYS: Final[frozenset[str]] = frozenset(
    {"checked_at", "attempts", "problem", "selected", "repeat_id", "requested_at", "awaiting_airing"}
)
"""Check history and range membership that episode records written before schema 4 may omit."""

_REPEAT_KEYS: Final[frozenset[str]] = frozenset({"number", "repeat_id", "requested_at"})
"""Keys a serialized explicit repeat must carry."""

_OPTIONAL_REPEAT_KEYS: Final[frozenset[str]] = frozenset({"previous_acquisition_id", "previous_info_hash"})
"""Links to the replaced operation, absent when the repeat had nothing to replace."""

_INVALID_MESSAGE: Final[str] = "Subscriptions file is invalid"
"""Sentence shown when the stored file cannot be trusted."""

_INVALID_SUGGESTION: Final[str] = "Fix or delete config/subscriptions.json"
"""Only recovery a user can perform on a broken subscription file."""

_INACTIVE_CALENDAR_STATUSES: Final[frozenset[str]] = frozenset({"FINISHED", "CANCELLED"})
"""Catalog states that do not authorize searching for hypothetical future episode numbers."""

_DISTANT_CALENDAR_INTERVAL_S: Final[int] = 86400
"""Daily refresh for hiatus or dates over a day away; nearby and unknown dates use the policy cadence."""


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
class EpisodeRepeat:
    """One explicit re-order of an episode, keeping the identity of the operation it repeats."""

    number: Decimal
    repeat_id: str
    requested_at: str
    previous_acquisition_id: str | None = None
    previous_info_hash: str | None = None


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
    selected: bool = True
    repeat_id: str | None = None
    requested_at: str | None = None
    awaiting_airing: bool = False


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
    future_from: Decimal | None = None
    repeats: tuple[EpisodeRepeat, ...] = ()
    calendar_checked_at: str | None = None
    calendar_attempts: int = 0
    calendar_status: str | None = None
    calendar_problem: str | None = None
    calendar_start_at: str | None = None

    def __post_init__(self) -> None:
        if self.calendar_attempts < 0 or self.calendar_status not in {
            None,
            "FINISHED",
            "RELEASING",
            "NOT_YET_RELEASED",
            "CANCELLED",
            "HIATUS",
            "UNKNOWN",
        }:
            msg = "A subscription calendar must carry a known status and a nonnegative retry count"
            raise ValueError(msg)
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


def in_range(subscription: Subscription, number: Decimal) -> bool:
    """Whether that episode number belongs to the ordered range, by explicit choice or by the future tail."""
    entry: EpisodeOrder | None = next((item for item in subscription.episodes if item.number == number), None)
    if entry is not None:
        return entry.selected
    return subscription.future_from is not None and number >= subscription.future_from


def repeat_of(subscription: Subscription, number: Decimal) -> str | None:
    """Return the repeat identity that episode is currently being ordered under, or nothing."""
    entry: EpisodeOrder | None = next((item for item in subscription.episodes if item.number == number), None)
    if entry is None or entry.state not in {EpisodeState.PENDING, EpisodeState.DUE}:
        return None
    return entry.repeat_id


def selectable_episodes(subscription: Subscription) -> tuple[Decimal, ...]:
    """Return the ordinary known numbers a new order may take, leaving every finished one alone."""
    return tuple(
        item.number
        for item in sorted(subscription.episodes, key=lambda entry: entry.number)
        if _is_whole(item.number) and item.state is not EpisodeState.COMPLETE
    )


def subscription_id(series: str, group: str) -> str:
    """Return the stable identifier of the series and release group pair."""
    seed: str = f"{normalize_series(series)}|{group.casefold()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:_ID_LENGTH]


def resolve_subscription_id(order: SubscriptionOrder, subscriptions: Sequence[Subscription]) -> str | None:
    """Reuse a compatible persisted identity or key a new catalog season, refusing ambiguous raw replacement."""
    matches: tuple[Subscription, ...] = tuple(
        item
        for item in subscriptions
        if normalize_series(item.series) == normalize_series(order.series)
        and item.group.casefold() == order.group.casefold()
    )
    base: str = subscription_id(order.series, order.group)
    if order.anilist_id is not None:
        exact: tuple[Subscription, ...] = tuple(item for item in matches if item.anilist_id == order.anilist_id)
        if len(exact) > 1:
            return None
        if exact:
            return exact[0].subscription_id
        return hashlib.sha256(f"{base}|anilist:{order.anilist_id}".encode()).hexdigest()[:_ID_LENGTH]
    if not matches:
        return base
    return matches[0].subscription_id if len(matches) == 1 and _compatible_raw_order(order, matches[0]) else None


def _compatible_raw_order(order: SubscriptionOrder, existing: Subscription) -> bool:
    context: SeasonContext | None = order.context
    return (
        existing.anilist_id is None
        and order.query.casefold() == existing.query.casefold()
        and (context is None or (context.index == existing.season_index and context.offset == existing.episode_offset))
    )


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
        accepted_id: str | None = None,
    ) -> Subscription:
        """Follow *series* by *group* from *first_episode* on, replacing an earlier order."""
        with self._lock:
            stored: tuple[Subscription, ...] = self._store.load()
            if command_id is not None:
                replay: Subscription | None = next(
                    (item for item in stored if item.added_by_command == command_id), None
                )
                if replay is not None:
                    return replay
            identifier: str | None = resolve_subscription_id(
                SubscriptionOrder(series, group, query, first_episode, directory_name, context, anilist_id), stored
            )
            if identifier is None:
                msg: str = "An ambiguous raw order cannot replace an existing season"
                raise ValueError(msg)
            if accepted_id is not None and accepted_id != identifier:
                if _find(stored, accepted_id) is not None or _find(stored, identifier) is not None:
                    raise _invalid_file()
                identifier = accepted_id
            earlier: Subscription | None = _find(stored, identifier)
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
                season_index=context.index if context is not None else (earlier.season_index if earlier else 1),
                episode_offset=context.offset if context is not None else (earlier.episode_offset if earlier else 0),
                season_episodes=context.episodes
                if context is not None
                else (earlier.season_episodes if earlier else None),
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
                future_from=first_episode,
                repeats=earlier.repeats if earlier is not None else (),
                calendar_checked_at=earlier.calendar_checked_at if earlier is not None else None,
                calendar_attempts=earlier.calendar_attempts if earlier is not None else 0,
                calendar_status=earlier.calendar_status if earlier is not None else None,
                calendar_problem=earlier.calendar_problem if earlier is not None else None,
                calendar_start_at=earlier.calendar_start_at if earlier is not None else None,
            )
            remaining: list[Subscription] = [item for item in stored if item.subscription_id != identifier]
            remaining.append(subscription)
            self._store.save(remaining)
            self._invalidate_check(identifier)
            logger.info("Subscription stored", replaced=earlier is not None, total=len(remaining))
            return subscription

    def add_order(self, order: SubscriptionOrder, command_id: str, *, accepted_id: str | None = None) -> Subscription:
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
            accepted_id=accepted_id,
        )

    def enable(self, subscription_id: str) -> Subscription:
        """Let that standing order look for episodes again, keeping everything it already took."""
        return self._switch(subscription_id, enabled=True)

    def disable(self, subscription_id: str) -> Subscription:
        """Stop the automatic checks of that standing order, keeping its range and history."""
        return self._switch(subscription_id, enabled=False)

    def set_range(
        self,
        subscription_id: str,
        *,
        selected: Sequence[Decimal],
        future_from: Decimal | None,
    ) -> Subscription:
        """Store the whole ordered range at once, touching neither taken releases nor finished episodes."""
        with self._lock:
            current: Subscription = self._required(subscription_id)
            wanted: frozenset[Decimal] = frozenset(selected)
            known: dict[Decimal, EpisodeOrder] = {item.number: item for item in current.episodes}
            fresh: bool = (
                bool(wanted - frozenset(known))
                or any(
                    item.number in wanted
                    and not item.selected
                    and item.state in {EpisodeState.PENDING, EpisodeState.DUE}
                    for item in known.values()
                )
                or (future_from is not None and future_from != current.future_from)
            )
            for number in sorted(wanted - frozenset(known)):
                known[number] = EpisodeOrder(number, requested_at=_timestamp(self._clock()))
            for number in wanted:
                entry: EpisodeOrder = known[number]
                if not entry.selected and entry.state in {EpisodeState.PENDING, EpisodeState.DUE}:
                    known[number] = replace(
                        entry,
                        requested_at=_timestamp(self._clock()),
                        due_at=None,
                        window_until=None,
                        checked_at=None,
                        attempts=0,
                        problem=None,
                    )
            episodes: tuple[EpisodeOrder, ...] = tuple(
                replace(known[number], selected=number in wanted) for number in sorted(known)
            )
            updated: Subscription = _finish_subscription(
                replace(
                    current,
                    episodes=episodes,
                    future_from=future_from,
                    end_state=SubscriptionEnd.ACTIVE,
                    calendar_checked_at=None if fresh else current.calendar_checked_at,
                    calendar_attempts=0 if fresh else current.calendar_attempts,
                    calendar_problem=None if fresh else current.calendar_problem,
                )
            )
            if updated == current:
                return current
            updated = replace(updated, generation=current.generation + 1)
            self._replace(updated)
            self._invalidate_check(subscription_id)
            logger.info(
                "Subscription range stored",
                selected=len(wanted),
                open_ended=future_from is not None,
                generation=updated.generation,
            )
            return updated

    def repeat(
        self,
        subscription_id: str,
        numbers: Sequence[Decimal],
        *,
        command_id: str | None = None,
        requested_at: str | None = None,
    ) -> Subscription:
        """Order the named episodes again, recording which earlier operation each repeat replaces."""
        with self._lock:
            current: Subscription = self._required(subscription_id)
            moment: str = requested_at or _timestamp(self._clock())
            wanted: frozenset[Decimal] = frozenset(numbers)
            known: dict[Decimal, EpisodeOrder] = {item.number: item for item in current.episodes}
            repeats: list[EpisodeRepeat] = list(current.repeats)
            applied: frozenset[str] = frozenset(item.repeat_id for item in repeats)
            for number in sorted(wanted):
                episode: EpisodeOrder = known.get(number, EpisodeOrder(number))
                identity: str = (
                    f"repeat-{hashlib.sha256(f'{command_id}|{number.normalize()}'.encode()).hexdigest()}"
                    if command_id is not None
                    else f"repeat-{token_hex(_REPEAT_ID_BYTES)}"
                )
                if identity in applied:
                    continue
                repeats.append(
                    EpisodeRepeat(
                        number=number,
                        repeat_id=identity,
                        requested_at=moment,
                        previous_acquisition_id=episode.acquisition_id,
                        previous_info_hash=episode.info_hash,
                    )
                )
                known[number] = replace(
                    episode,
                    selected=True,
                    repeat_id=identity,
                    state=EpisodeState.DUE,
                    info_hash=None,
                    acquisition_id=None,
                    checked_at=None,
                    attempts=0,
                    problem=None,
                    requested_at=moment,
                    due_at=None,
                    window_until=None,
                )
            if len(repeats) == len(current.repeats):
                return current
            updated: Subscription = replace(
                current,
                episodes=tuple(known[number] for number in sorted(known)),
                repeats=tuple(repeats),
                end_state=SubscriptionEnd.ACTIVE,
                generation=current.generation + 1,
                calendar_checked_at=None,
                calendar_attempts=0,
                calendar_problem=None,
            )
            self._replace(updated)
            self._invalidate_check(subscription_id)
            logger.info("Subscription repeats ordered", episodes=len(wanted), generation=updated.generation)
            return updated

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
            repeating: frozenset[Decimal] = _repeating(subscription)
            selected: dict[Decimal, ReleaseChoice] = {
                episode: choice
                for episode, choice in offered.items()
                if (
                    episode in repeating
                    or (episode not in taken_episodes and choice.release.info_hash.casefold() not in taken_hashes)
                )
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
            self._acquisition.download((choice,))
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
        deadlines: list[datetime] = [
            max(due, datetime.fromtimestamp(self._acquisition.blocked_until(("nyaa",)), UTC))
            for episode in subscription.episodes
            if episode.window_until is not None and (due := _episode_deadline(episode, policy, now)) is not None
        ]
        calendar: datetime | None = _calendar_deadline(subscription, policy, now)
        if calendar is not None:
            deadlines.append(max(calendar, datetime.fromtimestamp(self._acquisition.blocked_until(("anilist",)), UTC)))
        return min(deadlines) if deadlines else None

    def reconcile_sources(self, confirmations: Sequence[AcquisitionConfirmation]) -> None:
        """Project confirmed transfer states into their linked episode orders."""
        by_subscription: dict[str, list[AcquisitionConfirmation]] = {}
        for item in confirmations:
            if item.subscription_id is not None and item.episode is not None:
                by_subscription.setdefault(item.subscription_id, []).append(item)
        with self._lock:
            stored: tuple[Subscription, ...] = self._store.load()
            updated: tuple[Subscription, ...] = tuple(
                _with_sources(item, by_subscription.get(item.subscription_id, [])) for item in stored
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
                    partial(
                        self._check_due, subscription, policy, save, admit, record, refresh_calendar=refresh_calendar
                    ),
                )
            )
        return tuple(outcomes)

    def _check_due(  # noqa: PLR0913 - schedule mode and owner callbacks share one admission boundary
        self,
        subscription: Subscription,
        policy: AutomationPolicy,
        update: SubscriptionUpdater,
        admit: SubscriptionAdmission | None,
        record: CheckRecorder | None,
        *,
        refresh_calendar: bool = False,
    ) -> CheckOutcome:
        now: datetime = self._clock()
        if subscription.anilist_id is None:
            return self._check_unbound(subscription, policy, update, admit, record)
        prepared: Subscription
        refresh_problem: str
        prepared, refresh_problem = self._refresh_calendar(subscription, policy, now, force=refresh_calendar)
        prepared = _prepare_undated(prepared, policy, now)
        prepared = _finish_subscription(_expire_windows(prepared, now))
        if not update(subscription, prepared):
            return CheckOutcome(subscription, 0, _STALE_PROBLEM)
        numbers: frozenset[Decimal] = _due_episodes(prepared, policy, now)
        if not numbers or self._acquisition.blocked_until(("nyaa",)) > now.timestamp():
            return CheckOutcome(prepared, 0, refresh_problem or prepared.calendar_problem or "")
        outcome: CheckOutcome = self._check(prepared, admit, record or self.record_check, numbers)
        if outcome.problem and self.is_current(prepared):
            failed: Subscription = _failed_check(prepared, policy, now, outcome.problem)
            update(prepared, failed)
            return replace(outcome, subscription=failed)
        return replace(outcome, problem=outcome.problem or refresh_problem or prepared.calendar_problem or "")

    def _refresh_calendar(
        self, subscription: Subscription, policy: AutomationPolicy, now: datetime, *, force: bool
    ) -> tuple[Subscription, str]:
        calendar: datetime | None = _calendar_deadline(subscription, policy, now)
        if subscription.anilist_id is None or (not force and (calendar is None or calendar > now)):
            return subscription, ""
        if self._acquisition.blocked_until(("anilist",)) > now.timestamp():
            return subscription, "calendar_cooldown" if force else ""
        try:
            schedule: SeasonAiring = self._acquisition.airing_schedule(subscription.anilist_id)
        except AniShiftError as problem:
            failed: Subscription = _failed_calendar(subscription, now, str(problem.context.code))
            logger.warning(
                "Subscription calendar failed", attempts=failed.calendar_attempts, code=str(problem.context.code)
            )
            return failed, ""
        logger.debug("Subscription calendar refreshed", episodes=len(schedule.episodes), status=schedule.status.value)
        return _apply_schedule(subscription, schedule, policy, now), ""

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


def _with_sources(subscription: Subscription, confirmations: Sequence[AcquisitionConfirmation]) -> Subscription:
    if not confirmations:
        return subscription
    episodes: dict[Decimal, EpisodeOrder] = {item.number: item for item in subscription.episodes}
    grouped: dict[Decimal, list[AcquisitionConfirmation]] = {}
    for item in confirmations:
        grouped.setdefault(Decimal(str(item.episode)), []).append(item)
    for number, candidates in grouped.items():
        episode: EpisodeOrder = episodes.get(number, EpisodeOrder(number))
        confirmation: AcquisitionConfirmation | None = _matching_source(episode, candidates)
        if confirmation is None:
            continue
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


def _matching_source(
    episode: EpisodeOrder, candidates: Sequence[AcquisitionConfirmation]
) -> AcquisitionConfirmation | None:
    if episode.repeat_id is not None:
        return next((item for item in candidates if item.repeat_id == episode.repeat_id), None)
    plain: tuple[AcquisitionConfirmation, ...] = tuple(item for item in candidates if item.repeat_id is None)
    return plain[-1] if plain else None


def _repeating(subscription: Subscription) -> frozenset[Decimal]:
    return frozenset(
        item.number
        for item in subscription.episodes
        if item.repeat_id is not None and item.state in {EpisodeState.PENDING, EpisodeState.DUE}
    )


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
    if not episode.selected or episode.state not in {EpisodeState.PENDING, EpisodeState.DUE}:
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
    calendar: datetime | None = _calendar_deadline(subscription, policy, now)
    if calendar is not None:
        deadlines.append(calendar)
    return min(deadlines) if deadlines else None


def _calendar_deadline(subscription: Subscription, policy: AutomationPolicy, now: datetime) -> datetime | None:
    if subscription.calendar_attempts >= policy.external_retry_budget:
        return None
    pending: bool = any(
        item.selected and item.state in {EpisodeState.PENDING, EpisodeState.DUE} for item in subscription.episodes
    )
    tail: bool = (
        subscription.future_from is not None and subscription.calendar_status not in _INACTIVE_CALENDAR_STATUSES
    )
    if tail and subscription.season_episodes is not None:
        known: set[Decimal] = {item.number for item in subscription.episodes}
        tail = any(
            Decimal(number) not in known and in_range(subscription, Decimal(number))
            for number in range(1, subscription.season_episodes + 1)
        )
    if not pending and not tail:
        return None
    checked: datetime | None = _moment(subscription.calendar_checked_at)
    if checked is None:
        return now
    delay: int = _calendar_interval(subscription, policy, now)
    if subscription.calendar_attempts and policy.retry_delays_s:
        delay = policy.retry_delays_s[min(subscription.calendar_attempts - 1, len(policy.retry_delays_s) - 1)]
    return checked + timedelta(seconds=delay)


def _calendar_interval(subscription: Subscription, policy: AutomationPolicy, now: datetime) -> int:
    if subscription.calendar_status == "HIATUS":
        return _DISTANT_CALENDAR_INTERVAL_S
    dates: list[datetime] = [
        airing
        for item in subscription.episodes
        if item.selected
        and item.state in {EpisodeState.PENDING, EpisodeState.DUE}
        and (airing := _moment(item.airing_at)) is not None
    ]
    start: datetime | None = _moment(subscription.calendar_start_at)
    if start is not None:
        dates.append(start)
    unknown: bool = any(
        item.selected
        and item.state in {EpisodeState.PENDING, EpisodeState.DUE}
        and item.requested_at is not None
        and item.airing_at is None
        and not item.awaiting_airing
        for item in subscription.episodes
    )
    if not unknown and dates and min(dates) > now + timedelta(seconds=_DISTANT_CALENDAR_INTERVAL_S):
        return _DISTANT_CALENDAR_INTERVAL_S
    return policy.recheck_interval_s


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
        if episode.window_until is not None
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
    tail: Decimal | None = subscription.future_from
    if schedule.status in _INACTIVE_CALENDAR_STATUSES and count is None:
        tail = None
    numbers: set[Decimal] = set(known) | {number for number in dates if in_range(subscription, number)}
    if not numbers and count is None and tail is None and subscription.future_from is not None:
        numbers.add(subscription.future_from)
    if count is not None and tail is not None:
        numbers.update(Decimal(number) for number in range(math.ceil(tail), count + 1))
    elif tail is not None and tail not in numbers:
        numbers.add(tail)
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
        _scheduled_episode(
            _calendar_episode(known.get(number, EpisodeOrder(number)), dates, subscription),
            dates,
            schedule,
            delay,
            policy,
            now,
        )
        for number in sorted(numbers)
    )
    end: SubscriptionEnd = subscription.end_state
    if count is not None and tail is not None and tail > count and not episodes:
        end = SubscriptionEnd.COMPLETE
    return replace(
        subscription,
        season_episodes=count,
        episodes=episodes,
        end_state=end,
        calendar_checked_at=_timestamp(now),
        calendar_attempts=0,
        calendar_status=schedule.status.value,
        calendar_problem=None,
        calendar_start_at=(
            _timestamp(datetime.combine(schedule.start_date, datetime.min.time(), tzinfo=UTC))
            if schedule.start_date is not None
            else None
        ),
    )


def _calendar_episode(
    episode: EpisodeOrder, dates: dict[Decimal, datetime | None], subscription: Subscription
) -> EpisodeOrder:
    if (
        episode.state in {EpisodeState.PENDING, EpisodeState.DUE}
        and dates.get(episode.number) is not None
        and episode.airing_at is None
        and episode.window_until is None
        and episode.requested_at is None
    ):
        return replace(episode, requested_at=subscription.added_at)
    return episode


def _scheduled_episode(  # noqa: PLR0913
    episode: EpisodeOrder,
    dates: dict[Decimal, datetime | None],
    schedule: SeasonAiring,
    delay: int,
    policy: AutomationPolicy,
    now: datetime,
) -> EpisodeOrder:
    if not episode.selected or episode.state not in {EpisodeState.PENDING, EpisodeState.DUE}:
        return episode
    airing: datetime | None = _moment(episode.airing_at)
    if episode.airing_source is not AiringSource.USER and episode.number in dates:
        airing = dates[episode.number]
    if airing is not None:
        if airing == _moment(episode.airing_at) and episode.due_at is not None:
            return episode
        due: datetime = airing + timedelta(seconds=delay)
        requested: datetime | None = _moment(episode.requested_at)
        if requested is not None:
            due = max(due, requested)
        if episode.awaiting_airing:
            due = max(due, now)
        return replace(
            episode,
            airing_at=_timestamp(airing),
            airing_source=episode.airing_source if episode.airing_source is AiringSource.USER else AiringSource.ANILIST,
            due_at=_timestamp(due),
            window_until=_timestamp(due + timedelta(seconds=policy.search_window_s)),
            awaiting_airing=False,
        )
    start: datetime | None = (
        datetime.combine(schedule.start_date, datetime.min.time(), tzinfo=UTC)
        if schedule.start_date is not None
        else None
    )
    status: str = schedule.status.value
    if any(number <= episode.number and date is not None and date > now for number, date in dates.items()):
        status = "NOT_YET_RELEASED"
    return _undated_episode(episode, status, start, policy, now)


def _prepare_undated(subscription: Subscription, policy: AutomationPolicy, now: datetime) -> Subscription:
    return replace(
        subscription,
        episodes=tuple(
            _undated_episode(
                episode, subscription.calendar_status, _moment(subscription.calendar_start_at), policy, now
            )
            if episode.airing_at is None
            else episode
            for episode in subscription.episodes
        ),
    )


def _undated_episode(
    episode: EpisodeOrder, status: str | None, start: datetime | None, policy: AutomationPolicy, now: datetime
) -> EpisodeOrder:
    if not episode.selected or episode.state not in {EpisodeState.PENDING, EpisodeState.DUE}:
        return episode
    future: bool = status in {"NOT_YET_RELEASED", "HIATUS"} or (start is not None and start > now)
    if status in _INACTIVE_CALENDAR_STATUSES and (episode.awaiting_airing or episode.requested_at is None):
        return replace(episode, state=EpisodeState.MISSING, problem="schedule_unavailable")
    if future or (episode.awaiting_airing and status not in _INACTIVE_CALENDAR_STATUSES):
        return replace(episode, awaiting_airing=True, due_at=None, window_until=None)
    if episode.requested_at is not None:
        if episode.window_until is not None:
            return episode
        return replace(
            episode,
            airing_at=None,
            airing_source=None,
            awaiting_airing=False,
            due_at=_timestamp(now),
            window_until=_timestamp(now + timedelta(seconds=policy.search_window_s)),
        )
    return replace(episode, due_at=None, window_until=None, awaiting_airing=True)


def _expire_windows(subscription: Subscription, now: datetime) -> Subscription:
    episodes: tuple[EpisodeOrder, ...] = tuple(
        replace(episode, state=EpisodeState.EXPIRED)
        if episode.selected
        and episode.state in {EpisodeState.PENDING, EpisodeState.DUE}
        and (end := _moment(episode.window_until)) is not None
        and now >= end
        else episode
        for episode in subscription.episodes
    )
    return replace(subscription, episodes=episodes)


def _finish_subscription(subscription: Subscription) -> Subscription:
    if (
        subscription.season_episodes is None
        and subscription.future_from is not None
        and subscription.calendar_status not in _INACTIVE_CALENDAR_STATUSES
    ):
        return subscription
    states: dict[Decimal, EpisodeOrder] = {
        episode.number: episode for episode in subscription.episodes if episode.selected
    }
    if not states:
        return subscription
    required: set[Decimal] = set(states)
    if subscription.future_from is not None and subscription.season_episodes is not None:
        required.update(
            Decimal(number)
            for number in range(math.ceil(subscription.future_from), subscription.season_episodes + 1)
            if in_range(subscription, Decimal(number))
        )
    if any(number not in states for number in required):
        return subscription
    if any(episode.state in {EpisodeState.PENDING, EpisodeState.DUE} for episode in states.values()):
        return subscription
    end: SubscriptionEnd = SubscriptionEnd.COMPLETE
    if any(episode.state is EpisodeState.ORDERED or episode.problem for episode in states.values()):
        end = SubscriptionEnd.UNCERTAIN
    elif any(episode.state in {EpisodeState.MISSING, EpisodeState.EXPIRED} for episode in states.values()):
        end = SubscriptionEnd.MISSING
    return replace(subscription, end_state=end)


def _missing_after_retries(episode: EpisodeOrder, attempts: int, policy: AutomationPolicy) -> EpisodeState:
    if attempts < policy.external_retry_budget:
        return episode.state
    if episode.state not in {EpisodeState.PENDING, EpisodeState.DUE}:
        return episode.state
    return EpisodeState.MISSING


def _failed_check(subscription: Subscription, policy: AutomationPolicy, now: datetime, problem: str) -> Subscription:
    pending: tuple[EpisodeOrder, ...] = subscription.episodes or (EpisodeOrder(subscription.next_episode),)
    episodes: list[EpisodeOrder] = []
    for episode in pending:
        deadline: datetime | None = _episode_deadline(episode, policy, now)
        if episode.window_until is None or deadline is None or deadline > now:
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
                state=_missing_after_retries(episode, attempts, policy),
            )
        )
    return _finish_subscription(replace(subscription, episodes=tuple(episodes)))


def _failed_calendar(subscription: Subscription, now: datetime, problem: str) -> Subscription:
    return replace(
        subscription,
        calendar_checked_at=_timestamp(now),
        calendar_attempts=subscription.calendar_attempts + 1,
        calendar_problem=problem,
    )


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
            if not in_range(subscription, episode):
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
        "future_from": None if subscription.future_from is None else str(subscription.future_from),
        "repeats": [_encode_repeat(item) for item in subscription.repeats],
        "calendar_checked_at": subscription.calendar_checked_at,
        "calendar_attempts": subscription.calendar_attempts,
        "calendar_status": subscription.calendar_status,
        "calendar_problem": subscription.calendar_problem,
        "calendar_start_at": subscription.calendar_start_at,
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
        "selected": episode.selected,
        "repeat_id": episode.repeat_id,
        "requested_at": episode.requested_at,
        "awaiting_airing": episode.awaiting_airing,
    }


def _encode_repeat(repeat: EpisodeRepeat) -> dict[str, object]:
    return {
        "number": str(repeat.number),
        "repeat_id": repeat.repeat_id,
        "requested_at": repeat.requested_at,
        "previous_acquisition_id": repeat.previous_acquisition_id,
        "previous_info_hash": repeat.previous_info_hash,
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
        future_from=_optional_decimal(document, "future_from"),
        repeats=_optional_repeats(document, "repeats"),
        calendar_checked_at=_optional_timestamp(document, "calendar_checked_at"),
        calendar_attempts=_optional_count(document, "calendar_attempts", 0),
        calendar_status=_optional_string(document, "calendar_status"),
        calendar_problem=_optional_string(document, "calendar_problem"),
        calendar_start_at=_optional_timestamp(document, "calendar_start_at"),
    )
    if version == 1:
        subscription = _migrate_v1(subscription)
    if "calendar_attempts" not in document and not any(
        item.selected and item.state in {EpisodeState.PENDING, EpisodeState.DUE} for item in subscription.episodes
    ):
        subscription = replace(
            subscription,
            calendar_attempts=max(
                (
                    item.attempts
                    for item in subscription.episodes
                    if item.selected and item.state is EpisodeState.MISSING
                ),
                default=0,
            ),
        )
    return _migrate_v4(subscription) if version < SCHEMA_VERSION else subscription


def _migrate_v1(subscription: Subscription) -> Subscription:
    episodes: tuple[EpisodeOrder, ...] = tuple(
        EpisodeOrder(number=Decimal(number), state=EpisodeState.ORDERED) for number in subscription.taken_episodes
    )
    return replace(subscription, episodes=episodes)


def _migrate_v4(subscription: Subscription) -> Subscription:
    return replace(subscription, future_from=subscription.next_episode)


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
        selected=_optional_flag(document, "selected", default=True),
        repeat_id=_optional_string(document, "repeat_id"),
        requested_at=_optional_timestamp(document, "requested_at"),
        awaiting_airing=_optional_flag(document, "awaiting_airing", default=False),
    )


def _decode_repeat(raw: object) -> EpisodeRepeat:
    document: dict[str, object] = _strict_object(raw, _REPEAT_KEYS, "repeat", optional=_OPTIONAL_REPEAT_KEYS)
    return EpisodeRepeat(
        number=Decimal(_required_string(document, "number")),
        repeat_id=_required_string(document, "repeat_id"),
        requested_at=_required_string(document, "requested_at"),
        previous_acquisition_id=_optional_string(document, "previous_acquisition_id"),
        previous_info_hash=_optional_string(document, "previous_info_hash"),
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


def _optional_timestamp(document: dict[str, object], key: str) -> str | None:
    value: str | None = _optional_string(document, key)
    _moment(value)
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


def _optional_repeats(document: dict[str, object], key: str) -> tuple[EpisodeRepeat, ...]:
    value: object = document.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = f"Subscription field {key!r} must be a list of repeats or null"
        raise TypeError(msg)
    return tuple(_decode_repeat(item) for item in value)


def _optional_decimal(document: dict[str, object], key: str) -> Decimal | None:
    text: str | None = _optional_string(document, key)
    return None if text is None else Decimal(text)


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
