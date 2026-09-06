"""Standing orders that keep pulling new episodes of one series by one release group."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final

from anishift.application.acquisition import MIN_RESOLUTION, AcquisitionService, ReleaseChoice
from anishift.errors import AniShiftError, ConfigError, ErrorCode, ErrorContext
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from anishift.application.acquisition import ReleaseCatalog, SeriesGroup
    from anishift.services.torrents import ReleaseName

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
"""Only keys accepted for one serialized subscription."""

_INVALID_MESSAGE: Final[str] = "Subscriptions file is invalid"
"""Sentence shown when the stored file cannot be trusted."""

_INVALID_SUGGESTION: Final[str] = "Fix or delete config/subscriptions.json"
"""Only recovery a user can perform on a broken subscription file."""


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


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What one check of one subscription produced, or why it could not run."""

    subscription: Subscription
    downloaded: int
    problem: str = ""


def subscription_id(series: str, group: str) -> str:
    """Return the stable identifier of the series and release group pair."""
    seed: str = f"{series.casefold()}|{group.casefold()}"
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

    def subscribe(self, query: str, choice: ReleaseChoice) -> Subscription:
        """Follow the series and group of *choice* from its episode on, replacing an earlier order.

        Raises:
            ValueError: The chosen release is a batch or carries no episode number.
        """
        episode: Decimal | None = choice.name.episode
        if choice.name.batch or episode is None:
            msg = "A subscription needs a numbered episode"
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
            added_at=earlier.added_at if earlier is not None else _timestamp(self._clock()),
            checked_at=None,
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
            catalog: ReleaseCatalog = self._acquisition.search(subscription.query)
            selected: dict[Decimal, ReleaseChoice] = _new_episodes(catalog, subscription)
            queued: frozenset[str] = self._acquisition.queued_hashes() if selected else frozenset()
            chosen: tuple[ReleaseChoice, ...] = tuple(
                selected[episode]
                for episode in sorted(selected)
                if selected[episode].release.info_hash.casefold() not in queued
            )
            if chosen:
                self._acquisition.download(chosen)
            updated: Subscription = self._advance(subscription, selected)
            self._replace(updated)
        except AniShiftError as problem:
            logger.warning("Subscription check failed", error_class=type(problem).__name__)
            return CheckOutcome(subscription, 0, problem=str(problem))
        logger.info("Subscription checked", downloaded=len(chosen), taken=len(updated.taken))
        return CheckOutcome(updated, len(chosen))

    def check_all(self) -> tuple[CheckOutcome, ...]:
        """Check every subscription in stored order; a failing one does not stop the rest."""
        return tuple(self.check(subscription) for subscription in self.list())

    def _advance(self, subscription: Subscription, selected: dict[Decimal, ReleaseChoice]) -> Subscription:
        checked_at: str = _timestamp(self._clock())
        if not selected:
            return replace(subscription, checked_at=checked_at)
        taken: frozenset[str] = subscription.taken | {choice.release.info_hash for choice in selected.values()}
        return replace(
            subscription,
            next_episode=max(selected) + 1,
            taken=taken,
            checked_at=checked_at,
        )

    def _replace(self, subscription: Subscription) -> None:
        stored: tuple[Subscription, ...] = self._store.load()
        self._store.save(
            [subscription if item.subscription_id == subscription.subscription_id else item for item in stored]
        )


def _new_episodes(catalog: ReleaseCatalog, subscription: Subscription) -> dict[Decimal, ReleaseChoice]:
    series: str = subscription.series.casefold()
    group: str = subscription.group.casefold()
    best: dict[Decimal, ReleaseChoice] = {}
    for series_group in catalog.groups:
        if not _matches(series_group, series, group):
            continue
        for choice in series_group.choices:
            name: ReleaseName = choice.name
            episode: Decimal | None = name.episode
            if episode is None or name.batch or episode < subscription.next_episode:
                continue
            if choice.release.info_hash in subscription.taken:
                continue
            current: ReleaseChoice | None = best.get(episode)
            if current is None or _quality(choice) > _quality(current):
                best[episode] = choice
    return best


def _matches(series_group: SeriesGroup, series: str, group: str) -> bool:
    return series_group.series.casefold() == series and series_group.group.casefold() == group


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
    document: dict[str, object] = _strict_object(raw, _ENTRY_KEYS, "subscription")
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
    )


def _strict_object(raw: object, expected_keys: frozenset[str], label: str) -> dict[str, object]:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        msg = f"Serialized {label} must be an object with text keys"
        raise TypeError(msg)
    document: dict[str, object] = raw
    if frozenset(document) != expected_keys:
        msg = f"Serialized {label} has missing or unknown fields"
        raise ValueError(msg)
    return document


def _required_string(document: dict[str, object], key: str) -> str:
    value: object = document[key]
    if not isinstance(value, str):
        msg = f"Subscription field {key!r} must be text"
        raise TypeError(msg)
    return value


def _list_string(value: object) -> str:
    if not isinstance(value, str):
        msg = "Subscription collection values must be text"
        raise TypeError(msg)
    return value
