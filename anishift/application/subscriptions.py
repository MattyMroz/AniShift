"""Standing orders that keep pulling new episodes of one series by one release group."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from anishift.errors import ConfigError, ErrorCode, ErrorContext
from anishift.services.torrents.categories import SEARCH_CATEGORIES
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = [
    "MAX_DELAY_SAMPLES",
    "SCHEMA_VERSION",
    "SUBSCRIPTIONS_FILE_NAME",
    "AiringSource",
    "EpisodeOrder",
    "EpisodeRepeat",
    "EpisodeState",
    "Subscription",
    "SubscriptionEnd",
    "SubscriptionStore",
    "decode_subscriptions",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUBSCRIPTIONS_FILE_NAME: Final[str] = "subscriptions.json"
"""Filename stored beside user settings, outside the media workspace."""

SCHEMA_VERSION: Final[int] = 4
"""Current schema of the persisted subscription file."""

_SUPPORTED_VERSIONS: Final[frozenset[int]] = frozenset({1, 2, 3, SCHEMA_VERSION})
"""Schemas a load still understands, the ones migrated on the way in included."""

_BACKUP_SUFFIX_TEMPLATE: Final[str] = ".v{version}.bak"
"""Ending of the original-schema copy retained before a subscription migration."""

MAX_DELAY_SAMPLES: Final[int] = 8
"""Release delays kept per subscription, enough to estimate without storing a history."""

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
        version, subscriptions = _decode_text(text)
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


def decode_subscriptions(text: str) -> tuple[Subscription, ...]:
    """Decode a stored subscription document of any supported schema without writing anything."""
    return _decode_text(text)[1]


def _decode_text(text: str) -> tuple[int, tuple[Subscription, ...]]:
    try:
        return _decode_document(json.loads(text))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, InvalidOperation) as problem:
        raise _invalid_file() from problem


def _moment(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment: datetime = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        msg = "A subscription deadline must include its UTC offset"
        raise ValueError(msg)
    return moment.astimezone(UTC)


def _store_order(subscription: Subscription) -> tuple[str, str]:
    return (subscription.series.casefold(), subscription.group.casefold())


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
