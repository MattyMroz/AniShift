"""Pure migration of the former subscription file into the schema 4 automation state."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from itertools import groupby
from typing import TYPE_CHECKING, Final

from anishift.application.control import (
    WATCH_STATE_SCHEMA_VERSION,
    AcquisitionConfirmation,
    CommandReceipt,
    LegacyOrder,
    WatchState,
    legacy_number,
)
from anishift.application.control_views import encode_view
from anishift.application.subscription_targets import PauseReason, SubscriptionProblem, SubscriptionRecord
from anishift.application.subscriptions import SUBSCRIPTIONS_FILE_NAME, EpisodeState, Subscription, SubscriptionEnd
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["legacy_reference", "migrate"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_ORDERED_STATES: Final[frozenset[EpisodeState]] = frozenset({EpisodeState.ORDERED, EpisodeState.COMPLETE})
"""Episode states of the former file proving an order was handed to the client."""

_MISSING_ENDS: Final[frozenset[SubscriptionEnd]] = frozenset({SubscriptionEnd.MISSING, SubscriptionEnd.UNCERTAIN})
"""Former season ends that closed a subscription while episodes were still missing."""

_ENABLING_KINDS: Final[dict[str, bool]] = {"subscription_enable": True, "subscription_disable": False}
"""Pending former commands that still decide whether a migrated subscription is paused."""


def legacy_reference(item: AcquisitionConfirmation) -> str:
    """Return the conflict reference one unkeyed legacy acquisition is confirmed under."""
    identity: str = json.dumps(
        [item.info_hash, item.episode, item.release_title, item.required_files, encode_view(item.legacy_scope)],
        sort_keys=True,
    )
    return f"acquisition:{item.operation_id}:{sha256(identity.encode('utf-8')).hexdigest()}"


def migrate(state: WatchState, legacy: Sequence[Subscription], now: datetime) -> WatchState:
    """Return *state* as schema 4, carrying *legacy* subscriptions, their orders and no pending command."""
    removed: set[str] = set()
    enabled: dict[str, bool] = {}
    receipts: list[CommandReceipt] = []
    settled: int = 0
    for receipt in state.command_receipts:
        if receipt.pending is None or not receipt.pending.startswith("subscription_"):
            receipts.append(receipt)
            continue
        identifier: str = str(receipt.outcome["subscription_id"])
        if receipt.pending == "subscription_remove":
            removed.add(identifier)
        elif receipt.pending in _ENABLING_KINDS:
            enabled[identifier] = _ENABLING_KINDS[receipt.pending]
        receipts.append(replace(receipt, pending=None))
        settled += 1
    if settled:
        logger.info("Pending subscription commands settled by the migration", total=settled)
    kept: tuple[Subscription, ...] = tuple(
        replace(item, enabled=enabled.get(item.subscription_id, item.enabled))
        for item in legacy
        if item.subscription_id not in removed
    )
    moment: str = now.astimezone(UTC).isoformat()
    return replace(
        state,
        schema_version=WATCH_STATE_SCHEMA_VERSION,
        command_receipts=tuple(receipts),
        legacy_orders=_legacy_orders(legacy, state.acquisitions),
        subscriptions=_records(kept, moment),
        removed_subscription=None,
    )


def _legacy_orders(
    legacy: Sequence[Subscription], acquisitions: Sequence[AcquisitionConfirmation]
) -> tuple[LegacyOrder, ...]:
    linked: dict[str, int] = {item.subscription_id: item.anilist_id for item in legacy if item.anilist_id is not None}
    orders: dict[str, LegacyOrder] = {}
    for item in legacy:
        if item.anilist_id is None:
            continue
        numbers: set[str] = set(item.taken_episodes)
        numbers.update(str(order.number) for order in item.episodes if order.state in _ORDERED_STATES)
        complete: set[str] = {str(order.number) for order in item.episodes if order.state is EpisodeState.COMPLETE}
        for number in sorted(numbers):
            reference: str = f"subscription:{item.subscription_id}:{number}"
            orders.setdefault(
                reference, LegacyOrder(item.anilist_id, legacy_number(number), reference, None, number in complete)
            )
        for order in item.episodes:
            if str(order.number) not in numbers:
                continue
            reference = (
                f"subscription:{item.subscription_id}:{order.number}:"
                f"{order.info_hash}:{order.acquisition_id}:{order.repeat_id}"
            )
            orders.setdefault(
                reference,
                LegacyOrder(
                    item.anilist_id,
                    legacy_number(order.number),
                    reference,
                    None,
                    order.state is EpisodeState.COMPLETE,
                ),
            )
    for acquisition in acquisitions:
        if acquisition.legacy_scope is not None or acquisition.subscription_id not in linked:
            continue
        reference = legacy_reference(acquisition)
        orders.setdefault(
            reference,
            LegacyOrder(
                linked[acquisition.subscription_id],
                legacy_number(acquisition.episode),
                reference,
                acquisition.operation_id,
                complete=False,
            ),
        )
    return tuple(orders.values())


def _records(legacy: Sequence[Subscription], moment: str) -> tuple[SubscriptionRecord, ...]:
    pending: list[Subscription] = sorted(
        (item for item in legacy if item.end_state is not SubscriptionEnd.COMPLETE), key=_age
    )
    records: list[SubscriptionRecord] = [
        _record((item,), moment, SubscriptionProblem.SEASON_UNRECOGNIZED) for item in pending if item.anilist_id is None
    ]
    linked: list[Subscription] = sorted((item for item in pending if item.anilist_id is not None), key=_entry)
    records.extend(_record(tuple(group), moment, None) for _entry_id, group in groupby(linked, key=_entry))
    return tuple(records)


def _record(group: tuple[Subscription, ...], moment: str, problem: SubscriptionProblem | None) -> SubscriptionRecord:
    ordered: tuple[Subscription, ...] = tuple(sorted(group, key=_age))
    first: Subscription = ordered[0]
    reason: PauseReason | None = None
    if not any(item.enabled for item in ordered):
        reason = PauseReason.USER
    elif all(item.end_state in _MISSING_ENDS for item in ordered):
        reason = PauseReason.MIGRATED_MISSING
    return SubscriptionRecord(
        subscription_id=first.subscription_id,
        anilist_id=first.anilist_id,
        title=first.series,
        subscribed_at=_utc(first.added_at),
        cut=None,
        paused=reason is not None,
        pause_reason=reason,
        migrated_at=moment,
        review_pending=problem is None,
        merged_from=tuple(item.subscription_id for item in ordered),
        problem=problem,
        migrated_from=SUBSCRIPTIONS_FILE_NAME,
    )


def _age(item: Subscription) -> tuple[datetime, str]:
    return datetime.fromisoformat(_utc(item.added_at)), item.subscription_id


def _entry(item: Subscription) -> int:
    return item.anilist_id or 0


def _utc(value: str) -> str:
    moment: datetime = datetime.fromisoformat(value)
    return (moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)).astimezone(UTC).isoformat()
