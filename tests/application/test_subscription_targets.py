from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from anishift.application.subscription_targets import (
    MAX_ATTEMPTS,
    PauseReason,
    SubscriptionProblem,
    SubscriptionRecord,
    SubscriptionRow,
    SubscriptionTarget,
    TargetState,
    after_close,
    display_order,
    subscription_row,
)

_NOW: datetime = datetime(2026, 10, 2, 12, tzinfo=UTC)


def _record(identifier: str = "a", title: str = "Series", **changes: object) -> SubscriptionRecord:
    record: SubscriptionRecord = SubscriptionRecord(
        subscription_id=identifier,
        anilist_id=1,
        title=title,
        subscribed_at=_NOW.isoformat(),
        cut=0,
    )
    return replace(record, **changes)  # type: ignore[arg-type]


def _target(number: int, state: TargetState = TargetState.DUE, due: datetime | None = _NOW) -> SubscriptionTarget:
    return SubscriptionTarget(
        number,
        None if due is None else due.isoformat(),
        state,
        admission_id="admission" if state is TargetState.ATTEMPTING else None,
    )


@pytest.mark.parametrize(
    ("attempts", "due", "state"),
    [
        (MAX_ATTEMPTS, _NOW - timedelta(hours=1), TargetState.EXHAUSTED),
        (1, _NOW + timedelta(hours=1), TargetState.AWAITING_AIRING),
        (1, None, TargetState.AWAITING_AIRING),
        (1, _NOW - timedelta(hours=1), TargetState.DUE),
    ],
)
def test_a_closed_attempt_without_a_download_moves_the_target_by_its_budget_and_deadline(
    attempts: int, due: datetime | None, state: TargetState
) -> None:
    target: SubscriptionTarget = replace(
        _target(4, TargetState.ATTEMPTING, due), attempts=attempts, admission_id="admission-1"
    )

    closed: SubscriptionTarget = after_close(target, _NOW)

    assert closed.state is state
    assert closed.admission_id == "admission-1"
    assert closed.attempts == attempts


def test_a_row_counts_satisfied_targets_and_shows_the_nearest_open_deadline() -> None:
    record: SubscriptionRecord = _record(
        cut=2,
        targets=(
            _target(3, TargetState.SATISFIED, _NOW - timedelta(days=2)),
            _target(4, TargetState.DUE, _NOW + timedelta(days=3)),
            _target(5, TargetState.AWAITING_AIRING, _NOW + timedelta(days=1)),
            _target(6, TargetState.MANUAL, _NOW),
        ),
    )

    assert subscription_row(record) == SubscriptionRow(
        subscription_id="a",
        anilist_id=1,
        title="Series",
        from_number=3,
        downloaded=1,
        targets_total=4,
        due_at=(_NOW + timedelta(days=1)).isoformat(),
        paused=False,
        pause_reason=None,
        problem=None,
        review_pending=False,
    )


def test_a_migrated_row_waiting_for_review_hides_its_target_count() -> None:
    record: SubscriptionRecord = _record(
        cut=None,
        migrated_at=_NOW.isoformat(),
        review_pending=True,
        paused=True,
        pause_reason=PauseReason.MIGRATED_MISSING,
    )

    row: SubscriptionRow = subscription_row(record)

    assert (row.from_number, row.targets_total, row.pause_reason, row.review_pending) == (
        None,
        None,
        "migrated_missing",
        True,
    )


def test_the_list_orders_problem_then_deadline_then_undated_then_paused_with_title_ties() -> None:
    problem: SubscriptionRecord = _record(
        "p",
        "Zeta",
        anilist_id=None,
        problem=SubscriptionProblem.SEASON_UNRECOGNIZED,
        cut=None,
        migrated_at=_NOW.isoformat(),
    )
    later: SubscriptionRecord = _record("l", "Alpha", targets=(_target(1, due=_NOW + timedelta(days=2)),))
    sooner: SubscriptionRecord = _record("s", "Omega", targets=(_target(1, due=_NOW + timedelta(days=1)),))
    undated_b: SubscriptionRecord = _record("ub", "beta")
    undated_a: SubscriptionRecord = _record("ua", "Alpha")
    paused: SubscriptionRecord = _record("x", "Aardvark", paused=True, pause_reason=PauseReason.USER)

    ordered: tuple[SubscriptionRecord, ...] = display_order((paused, undated_b, later, problem, undated_a, sooner))

    assert [item.subscription_id for item in ordered] == ["p", "s", "l", "ua", "ub", "x"]


def test_a_paused_record_with_a_problem_sorts_with_the_problems() -> None:
    troubled: SubscriptionRecord = _record(
        "t",
        "Zeta",
        anilist_id=None,
        problem=SubscriptionProblem.SEASON_UNRECOGNIZED,
        cut=None,
        migrated_at=_NOW.isoformat(),
        paused=True,
        pause_reason=PauseReason.USER,
    )
    dated: SubscriptionRecord = _record("d", "Alpha", targets=(_target(1, due=_NOW + timedelta(days=1)),))

    assert [item.subscription_id for item in display_order((dated, troubled))] == ["t", "d"]


@pytest.mark.parametrize(
    "changes",
    [
        {"anilist_id": None},
        {"cut": None},
        {"review_pending": True},
        {"paused": True},
        {"pause_reason": PauseReason.USER},
        {"targets": (_target(1), _target(1))},
        {"merged_from": ("",)},
        {"subscribed_at": "2026-10-02T12:00:00"},
        {"title": " "},
    ],
)
def test_a_record_refuses_an_inconsistent_shape(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"."):
        replace(_record(), **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"number": 0},
        {"attempts": MAX_ATTEMPTS + 1},
        {"state": TargetState.ATTEMPTING},
        {"state": TargetState.EXHAUSTED, "attempts": 1},
        {"tried": ("Upper",)},
    ],
)
def test_a_target_refuses_an_inconsistent_shape(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"."):
        replace(_target(1), **changes)  # type: ignore[arg-type]
