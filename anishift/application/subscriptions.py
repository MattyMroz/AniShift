"""Standing orders that keep pulling new episodes of one series by one release group."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from anishift.application.acquisition import SeriesGroup

__all__ = [
    "CHECK_INTERVAL_S",
    "SCHEMA_VERSION",
    "SUBSCRIPTIONS_FILE_NAME",
    "CheckOutcome",
    "Subscription",
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

SCHEMA_VERSION: Final[int] = 1
"""Current schema of the persisted subscription file."""

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
    {"directory", "season_index", "episode_offset", "season_episodes", "taken_episodes"}
)
"""Keys a subscription written before seasons and taken episode numbers may omit."""

_INVALID_MESSAGE: Final[str] = "Subscriptions file is invalid"
"""Sentence shown when the stored file cannot be trusted."""

_INVALID_SUGGESTION: Final[str] = "Fix or delete config/subscriptions.json"
"""Only recovery a user can perform on a broken subscription file."""


@dataclass(frozen=True, slots=True)
class Subscription:
    """One standing order: which series and group to follow, and from which episode on.

    ``taken`` identifies the releases already handed to the client, ``taken_episodes`` the
    numbers they carried, which is what keeps ``next_episode`` from stepping over a gap.
    """

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


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What one check of one subscription produced, or why it could not run."""

    subscription: Subscription
    downloaded: int
    problem: str = ""


def subscription_id(series: str, group: str) -> str:
    """Return the stable identifier of the series and release group pair.

    The series is normalized first, so the spelling a single release happens to use never
    splits one followed series into two orders.
    """
    seed: str = f"{normalize_series(series)}|{group.casefold()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:_ID_LENGTH]


class SubscriptionStore:
    """Versioned, atomic persistence of every standing order."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path

    def load(self) -> tuple[Subscription, ...]:
        """Read every stored subscription, or none when the file was never written.

        Raises:
            ConfigError: The file exists but carries an unreadable or unsupported document.
        """
        try:
            text: str = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        except OSError as problem:
            raise _invalid_file() from problem
        try:
            subscriptions: tuple[Subscription, ...] = _decode_document(json.loads(text))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, InvalidOperation) as problem:
            raise _invalid_file() from problem
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


class SubscriptionService:
    """Create standing orders and pull every episode they still miss."""

    def __init__(
        self,
        *,
        store: SubscriptionStore,
        acquisition: AcquisitionService,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store: SubscriptionStore = store
        self._acquisition: AcquisitionService = acquisition
        self._clock: Callable[[], datetime] = clock

    def subscribe(
        self,
        query: str,
        choice: ReleaseChoice,
        *,
        directory_name: str | None = None,
        context: SeasonContext | None = None,
    ) -> Subscription:
        """Follow the series and group of *choice* from its episode on, replacing an earlier order.

        The episode is read in the numbering of *context*, so a check later compares the same
        numbers the user saw, and *directory_name* pins every download to one library folder.

        Raises:
            ValueError: The chosen release is a pack, carries no episode number, or belongs
                to another season than the one being followed.
        """
        episode: Decimal | None = choice.episode
        if choice.name.is_pack or episode is None:
            msg = "A subscription needs a numbered episode"
            raise ValueError(msg)
        if choice.other_season:
            msg = "A subscription needs a release of the season being followed"
            raise ValueError(msg)
        series: str = choice.name.series
        group: str = choice.name.group or "?"
        identifier: str = subscription_id(series, group)
        stored: tuple[Subscription, ...] = self._store.load()
        earlier: Subscription | None = _find(stored, identifier)
        subscription: Subscription = Subscription(
            subscription_id=identifier,
            query=query,
            series=series,
            group=group,
            next_episode=episode,
            min_resolution=MIN_RESOLUTION,
            taken=earlier.taken if earlier is not None else frozenset(),
            taken_episodes=earlier.taken_episodes if earlier is not None else (),
            added_at=earlier.added_at if earlier is not None else _timestamp(self._clock()),
            checked_at=None,
            directory=directory_name,
            season_index=context.index if context is not None else 1,
            episode_offset=context.offset if context is not None else 0,
            season_episodes=context.episodes if context is not None else None,
        )
        remaining: list[Subscription] = [item for item in stored if item.subscription_id != identifier]
        remaining.append(subscription)
        self._store.save(remaining)
        logger.info("Subscription stored", replaced=earlier is not None, total=len(remaining))
        return subscription

    def list(self) -> tuple[Subscription, ...]:
        """Return every stored subscription."""
        return self._store.load()

    def remove(self, subscription_id: str) -> bool:
        """Drop the subscription with that identifier, reporting whether it existed."""
        stored: tuple[Subscription, ...] = self._store.load()
        remaining: tuple[Subscription, ...] = tuple(item for item in stored if item.subscription_id != subscription_id)
        if len(remaining) == len(stored):
            return False
        self._store.save(remaining)
        logger.info("Subscription removed", total=len(remaining))
        return True

    def check(self, subscription: Subscription) -> CheckOutcome:
        """Download every episode *subscription* still misses and record what was taken."""
        try:
            offered: dict[Decimal, ReleaseChoice] = self._offered(subscription)
            selected: dict[Decimal, ReleaseChoice] = {
                episode: choice
                for episode, choice in offered.items()
                if choice.release.info_hash not in subscription.taken
            }
            queued: frozenset[str] = self._acquisition.queued_hashes() if selected else frozenset()
            chosen: tuple[ReleaseChoice, ...] = tuple(
                selected[episode]
                for episode in sorted(selected)
                if selected[episode].release.info_hash.casefold() not in queued
            )
            if chosen:
                self._acquisition.download(chosen, directory_name=subscription.directory)
            updated: Subscription = self._advance(subscription, selected, offered)
            self._replace(updated)
        except AniShiftError as problem:
            logger.warning("Subscription check failed", error_class=type(problem).__name__)
            return CheckOutcome(subscription, 0, problem=str(problem))
        logger.info("Subscription checked", downloaded=len(chosen), taken=len(updated.taken))
        return CheckOutcome(updated, len(chosen))

    def check_all(self) -> tuple[CheckOutcome, ...]:
        """Check every subscription in stored order; a failing one does not stop the rest."""
        return tuple(self.check(subscription) for subscription in self.list())

    def _offered(self, subscription: Subscription) -> dict[Decimal, ReleaseChoice]:
        """Return the best release of every episode the index offers from ``next_episode`` on.

        The index answers a free-text query with its newest entries only, so an episode still
        missing after that query is asked for once more by its own number.
        """
        context: SeasonContext | None = _context(subscription)
        catalog: ReleaseCatalog = self._acquisition.search(subscription.query)
        offered: dict[Decimal, ReleaseChoice] = _new_episodes(catalog, subscription, context)
        if subscription.next_episode in offered or not _is_whole(subscription.next_episode):
            return offered
        _keep_best(offered, _new_episodes(self._catch_up(subscription), subscription, context))
        return offered

    def _catch_up(self, subscription: Subscription) -> ReleaseCatalog:
        """Ask the index for the missing episode by number, answering with nothing when it fails."""
        query: str = f"{subscription.query} {int(subscription.next_episode):02d}"
        try:
            return self._acquisition.search(query)
        except AniShiftError as problem:
            logger.warning("Subscription catch-up search failed", error_class=type(problem).__name__)
            return ReleaseCatalog((), 0)

    def _advance(
        self,
        subscription: Subscription,
        selected: dict[Decimal, ReleaseChoice],
        offered: dict[Decimal, ReleaseChoice],
    ) -> Subscription:
        checked_at: str = _timestamp(self._clock())
        if not selected:
            return replace(subscription, checked_at=checked_at)
        taken: frozenset[str] = subscription.taken | {choice.release.info_hash for choice in selected.values()}
        episodes: tuple[str, ...] = _recorded_episodes(subscription.taken_episodes, offered)
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


def _context(subscription: Subscription) -> SeasonContext | None:
    if subscription.season_index <= 1 and subscription.episode_offset <= 0:
        return None
    return SeasonContext(
        index=subscription.season_index,
        offset=subscription.episode_offset,
        episodes=subscription.season_episodes,
    )


def _new_episodes(
    catalog: ReleaseCatalog,
    subscription: Subscription,
    context: SeasonContext | None,
) -> dict[Decimal, ReleaseChoice]:
    """Return the best release of every episode of the followed group from ``next_episode`` on.

    Releases already taken stay in the answer, because their number still tells the counter
    that the episode is not missing any more.
    """
    series: frozenset[str] = series_forms(subscription.series)
    group: str = subscription.group.casefold()
    best: dict[Decimal, ReleaseChoice] = {}
    for series_group in catalog.groups:
        if not _matches(series_group, series, group):
            continue
        for choice in series_group.choices:
            reading: EpisodeReading = read_episode(choice.name, context)
            episode: Decimal | None = reading.episode
            if episode is None or reading.other_season or choice.name.is_pack:
                continue
            if episode < subscription.next_episode:
                continue
            current: ReleaseChoice | None = best.get(episode)
            if current is None or _quality(choice) > _quality(current):
                best[episode] = choice
    return best


def _matches(series_group: SeriesGroup, series: frozenset[str], group: str) -> bool:
    return bool(series_forms(series_group.series) & series) and series_group.group.casefold() == group


def _keep_best(offered: dict[Decimal, ReleaseChoice], extra: dict[Decimal, ReleaseChoice]) -> None:
    """Add the episodes only the second listing carries, keeping the better release of a shared one."""
    for episode, choice in extra.items():
        current: ReleaseChoice | None = offered.get(episode)
        if current is None or _quality(choice) > _quality(current):
            offered[episode] = choice


def _recorded_episodes(stored: tuple[str, ...], offered: dict[Decimal, ReleaseChoice]) -> tuple[str, ...]:
    """Return every episode number known to be taken, the ones this check saw included."""
    numbers: set[str] = {*stored, *(str(episode) for episode in offered)}
    return tuple(sorted(numbers, key=Decimal))


def _next_episode(current: Decimal, recorded: tuple[str, ...]) -> Decimal:
    """Return the first whole episode from *current* on that no check has taken yet.

    A fractional number such as 7.5 never moves the counter, and a gap left by an episode
    that has not shown up yet keeps the counter waiting for exactly that number.
    """
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
    }


def _decode_document(raw: object) -> tuple[Subscription, ...]:
    document: dict[str, object] = _strict_object(raw, _ROOT_KEYS, "subscription file")
    schema_version: object = document["schema_version"]
    entries: object = document["subscriptions"]
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        msg = "Unsupported subscription schema version"
        raise ValueError(msg)
    if not isinstance(entries, list):
        msg = "Serialized subscriptions must be a list"
        raise TypeError(msg)
    return tuple(_decode_entry(entry) for entry in entries)


def _decode_entry(raw: object) -> Subscription:
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
    return Subscription(
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
