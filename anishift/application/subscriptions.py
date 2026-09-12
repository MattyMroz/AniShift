"""Standing orders that keep pulling new episodes of one series by one release group."""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
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
from anishift.errors import AniShiftError, ConfigError, ErrorCode, ErrorContext
from anishift.services.torrents.names import season_hint
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from anishift.application.acquisition import SeriesGroup

__all__ = [
    "CHECK_INTERVAL_S",
    "MAX_DELAY_SAMPLES",
    "SCHEMA_VERSION",
    "SUBSCRIPTIONS_FILE_NAME",
    "AiringSource",
    "CheckOutcome",
    "EpisodeOrder",
    "EpisodeState",
    "Subscription",
    "SubscriptionEnd",
    "SubscriptionService",
    "SubscriptionStore",
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

SCHEMA_VERSION: Final[int] = 2
"""Current schema of the persisted subscription file."""

_SUPPORTED_VERSIONS: Final[frozenset[int]] = frozenset({1, SCHEMA_VERSION})
"""Schemas a load still understands, the one migrated on the way in included."""

_V1_BACKUP_SUFFIX: Final[str] = ".v1.bak"
"""Ending of the one copy a schema 1 file leaves behind before it is rewritten."""

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

    def __post_init__(self) -> None:
        if len(self.delay_samples_s) > MAX_DELAY_SAMPLES:
            msg = "A subscription keeps at most MAX_DELAY_SAMPLES release delays"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What one check of one subscription produced, or why it could not run."""

    subscription: Subscription
    downloaded: int
    problem: str = ""


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
            self._upgrade(text, subscriptions)
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

    def _upgrade(self, text: str, subscriptions: Sequence[Subscription]) -> None:
        backup: Path = self._path.with_name(f"{self._path.name}{_V1_BACKUP_SUFFIX}")
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
    ) -> Subscription:
        """Follow *series* by *group* from *first_episode* on, replacing an earlier order."""
        with self._lock:
            identifier: str = subscription_id(series, group)
            stored: tuple[Subscription, ...] = self._store.load()
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
            )
            remaining: list[Subscription] = [item for item in stored if item.subscription_id != identifier]
            remaining.append(subscription)
            self._store.save(remaining)
            self._invalidate_check(identifier)
            logger.info("Subscription stored", replaced=earlier is not None, total=len(remaining))
            return subscription

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

    def check(self, subscription: Subscription) -> CheckOutcome:
        """Download every episode *subscription* still misses and record what was taken."""
        if not subscription.enabled:
            return CheckOutcome(subscription, 0, problem=_DISABLED_PROBLEM)
        with self._lock:
            if subscription.subscription_id in self._checking:
                return CheckOutcome(subscription, 0, problem=_CHECKING_PROBLEM)
            if not self._current(subscription):
                return CheckOutcome(subscription, 0, problem=_STALE_PROBLEM)
            self._checking[subscription.subscription_id] = True
        try:
            return self._check(subscription)
        finally:
            with self._lock:
                self._checking.pop(subscription.subscription_id)

    def _check(self, subscription: Subscription) -> CheckOutcome:
        try:
            offered: dict[Decimal, ReleaseChoice] = self._offered(subscription)
            taken_hashes: frozenset[str] = frozenset(info_hash.casefold() for info_hash in subscription.taken)
            taken_episodes: frozenset[Decimal] = frozenset(Decimal(number) for number in subscription.taken_episodes)
            selected: dict[Decimal, ReleaseChoice] = {
                episode: choice
                for episode, choice in offered.items()
                if episode not in taken_episodes and choice.release.info_hash.casefold() not in taken_hashes
            }
            queued: frozenset[str] = self._acquisition.queued_hashes() if selected else frozenset()
            chosen: tuple[ReleaseChoice, ...] = self._download(subscription, selected, queued)
            admitted: dict[Decimal, ReleaseChoice] = {
                episode: choice
                for episode, choice in selected.items()
                if choice in chosen or choice.release.info_hash.casefold() in queued
            }
            confirmed: dict[Decimal, ReleaseChoice] = self._confirmed(admitted, queued) if admitted else {}
            sent: int = sum(1 for choice in chosen if choice in confirmed.values())
            with self._lock:
                current: Subscription | None = _find(self._store.load(), subscription.subscription_id)
                if not self._current(subscription):
                    return CheckOutcome(current or subscription, sent, problem=_STALE_PROBLEM)
                updated: Subscription = self._advance(subscription, confirmed, offered)
                self._replace(updated)
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
            self._acquisition.download((choice,), directory_name=subscription.directory)
            chosen.append(choice)
        return tuple(chosen)

    def check_all(self) -> tuple[CheckOutcome, ...]:
        """Check every active subscription in stored order; a failing one does not stop the rest."""
        return tuple(
            self.check(subscription)
            for subscription in self.list()
            if subscription.enabled and subscription.end_state is SubscriptionEnd.ACTIVE
        )

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
            and current.generation == subscription.generation
            and self._checking.get(subscription.subscription_id, True)
        )

    def _invalidate_check(self, subscription_id: str) -> None:
        if subscription_id in self._checking:
            self._checking[subscription_id] = False

    def _offered(self, subscription: Subscription) -> dict[Decimal, ReleaseChoice]:
        context: SeasonContext | None = _context(subscription)
        catalog: ReleaseCatalog = self._acquisition.search(subscription.query)
        with self._lock:
            if not self._current(subscription):
                return {}
        offered: dict[Decimal, ReleaseChoice] = _new_episodes(catalog, subscription, context)
        if subscription.next_episode in offered or not _is_whole(subscription.next_episode):
            return offered
        _keep_best(offered, _new_episodes(self._catch_up(subscription), subscription, context))
        return offered

    def _catch_up(self, subscription: Subscription) -> ReleaseCatalog:
        query: str = f"{subscription.query} {int(subscription.next_episode):02d}"
        try:
            return self._acquisition.search(query)
        except AniShiftError as problem:
            logger.warning("Subscription catch-up search failed", error_class=type(problem).__name__)
            return ReleaseCatalog((), 0)

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
    ) -> Subscription:
        checked_at: str = _timestamp(self._clock())
        taken_episodes: frozenset[Decimal] = frozenset(Decimal(number) for number in subscription.taken_episodes)
        taken_hashes: frozenset[str] = frozenset(info_hash.casefold() for info_hash in subscription.taken)
        known: dict[Decimal, ReleaseChoice] = {
            episode: choice
            for episode, choice in offered.items()
            if episode in selected or episode in taken_episodes or choice.release.info_hash.casefold() in taken_hashes
        }
        if not known:
            return replace(subscription, checked_at=checked_at)
        taken: frozenset[str] = subscription.taken | {choice.release.info_hash for choice in selected.values()}
        episodes: tuple[str, ...] = _recorded_episodes(subscription.taken_episodes, known)
        return replace(
            subscription,
            next_episode=_next_episode(subscription.next_episode, episodes),
            taken=taken,
            taken_episodes=episodes,
            checked_at=checked_at,
        )

    def _replace(self, subscription: Subscription) -> None:
        stored: tuple[Subscription, ...] = self._store.load()
        self._store.save(
            [subscription if item.subscription_id == subscription.subscription_id else item for item in stored]
        )


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
    )
    return _migrate_v1(subscription) if version == 1 else subscription


def _migrate_v1(subscription: Subscription) -> Subscription:
    episodes: tuple[EpisodeOrder, ...] = tuple(
        EpisodeOrder(number=Decimal(number), state=EpisodeState.ORDERED) for number in subscription.taken_episodes
    )
    return replace(subscription, episodes=episodes)


def _decode_episode(raw: object) -> EpisodeOrder:
    document: dict[str, object] = _strict_object(raw, _EPISODE_KEYS, "episode")
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
