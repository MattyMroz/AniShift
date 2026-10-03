from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from anishift.application.acquisition import ListingRead
from anishift.application.control import LegacyScope
from anishift.application.episode_identity import IdentityAssessment, IdentityVerdict
from anishift.application.episode_selection import (
    AniZipMapping,
    EpisodeListing,
    ListedEpisode,
    RankedCandidate,
    ReleaseFacts,
    StreamCandidate,
)
from anishift.application.subscription_targets import (
    MAX_ATTEMPTS,
    PauseReason,
    SubscriptionProblem,
    SubscriptionRecord,
    SubscriptionRow,
    SubscriptionTarget,
    TargetState,
    after_close,
    completed,
    cut_point,
    display_order,
    eligible,
    is_target,
    merge_listing,
    next_check_at,
    next_search_at,
    search_targets,
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
        due_number=5,
    )


@pytest.mark.parametrize(("count", "beyond"), [(4, 6), (6, None), (None, None)])
def test_a_row_names_the_last_target_beyond_the_catalogue_episode_count(count: int | None, beyond: int | None) -> None:
    record: SubscriptionRecord = _record(episode_count=count, targets=tuple(_target(number) for number in range(3, 7)))

    row: SubscriptionRow = subscription_row(record)

    assert (row.episode_count, row.beyond_count) == (count, beyond)


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


def _episode(
    number: int, airs: datetime | None = None, *, fallback: bool = False, aired: bool = False
) -> ListedEpisode:
    return ListedEpisode(number, airs_at=airs, aired=aired, airs_at_fallback=fallback)


def _listing(
    *episodes: ListedEpisode, status: str = "RELEASING", warning: str | None = None, count: int | None = None
) -> EpisodeListing:
    return EpisodeListing(1, 10, "TV", status, count, episodes, (), None, warning, None)


def _mapping(kitsu: int | None = 10) -> AniZipMapping:
    return AniZipMapping(kitsu, "TV", None, (), (), 300, {"1": {"episodeNumber": 1}})


def _read(listing: EpisodeListing, *, kitsu: int | None = 10, live: bool = True) -> ListingRead:
    return ListingRead(listing, _mapping(kitsu), live)


def _candidate(
    verdict: IdentityVerdict = IdentityVerdict.MATCH, *, supported: bool | None = True, index: int | None = 0
) -> RankedCandidate:
    return RankedCandidate(
        StreamCandidate("ABC", None, index, "Series - 04.mkv", "Series - 04", None, 5, None, None, (), ()),
        IdentityAssessment(verdict, "reason"),
        ReleaseFacts(1080, False, False, None, False, "mkv", supported),
    )


_DAY: timedelta = timedelta(days=1)


@pytest.mark.parametrize(
    ("listing", "cut"),
    [
        (_listing(_episode(1, _NOW - _DAY), _episode(2, _NOW), _episode(3, _NOW + _DAY)), 2),
        (_listing(_episode(1, _NOW - _DAY), _episode(2, _NOW + _DAY), status="HIATUS"), 1),
        (_listing(_episode(1), _episode(2), status="HIATUS"), None),
        (_listing(_episode(1), status="NOT_YET_RELEASED"), 0),
        (_listing(_episode(1, _NOW - _DAY), warning="TITLE_CATALOG_FAILED"), None),
        (_listing(_episode(1, _NOW - _DAY, fallback=True), _episode(2, _NOW + _DAY, fallback=True)), None),
        (_listing(_episode(1, _NOW - _DAY), status="FINISHED"), None),
    ],
    ids=["releasing", "hiatus-dated", "hiatus-undated", "announced", "schedule-failed", "anizip-dates", "finished"],
)
def test_the_cut_point_counts_only_aired_anilist_dates_of_an_airing_entry(
    listing: EpisodeListing, cut: int | None
) -> None:
    assert cut_point(listing, _NOW) == cut


@pytest.mark.parametrize(
    ("episode", "cut", "expected"),
    [
        (_episode(1, _NOW + timedelta(seconds=1)), 5, True),
        (_episode(9, _NOW), 0, False),
        (_episode(9, _NOW - _DAY), 0, False),
        (_episode(3), 2, True),
        (_episode(2), 2, False),
        (_episode(2, _NOW + _DAY, fallback=True), 2, False),
        (_episode(3), None, False),
    ],
    ids=["dated-after", "dated-at", "dated-before", "undated-after-cut", "undated-at-cut", "anizip-date", "no-cut"],
)
def test_membership_follows_the_anilist_date_and_otherwise_the_cut(
    episode: ListedEpisode, cut: int | None, expected: bool
) -> None:
    assert is_target(episode, _NOW, cut) is expected


def test_an_announced_entry_targets_every_episode_and_waits_for_unknown_dates() -> None:
    merged: SubscriptionRecord = merge_listing(
        _record(), _read(_listing(_episode(1), _episode(2), status="NOT_YET_RELEASED")), _NOW
    )
    assert [(item.number, item.due_at, item.state) for item in merged.targets] == [
        (1, None, TargetState.AWAITING_AIRING),
        (2, None, TargetState.AWAITING_AIRING),
    ]


def test_an_undated_target_is_due_from_its_first_observation_as_aired_and_never_moves_later() -> None:
    first: SubscriptionRecord = merge_listing(_record(), _read(_listing(_episode(1, aired=True))), _NOW)
    later: SubscriptionRecord = merge_listing(first, _read(_listing(_episode(1, aired=True))), _NOW + _DAY)
    assert (first.targets[0].due_at, first.targets[0].state) == (_NOW.isoformat(), TargetState.DUE)
    assert later.targets == first.targets


def test_a_moved_date_moves_an_open_target_but_never_an_attempted_one_nor_its_membership() -> None:
    record: SubscriptionRecord = _record(
        targets=(_target(1, TargetState.DUE, _NOW - _DAY), _target(2, TargetState.ATTEMPTING, _NOW - _DAY))
    )
    moved: SubscriptionRecord = merge_listing(
        record, _read(_listing(_episode(1, _NOW + _DAY), _episode(2, _NOW + _DAY))), _NOW
    )
    back: SubscriptionRecord = merge_listing(moved, _read(_listing(_episode(1, _NOW - _DAY))), _NOW)
    assert [(item.due_at, item.state) for item in moved.targets] == [
        ((_NOW + _DAY).isoformat(), TargetState.AWAITING_AIRING),
        ((_NOW - _DAY).isoformat(), TargetState.ATTEMPTING),
    ]
    assert [item.number for item in back.targets] == [1, 2]
    assert back.targets[0].state is TargetState.DUE


def test_a_live_read_records_its_mapping_and_a_snapshot_read_changes_only_the_targets() -> None:
    listing: EpisodeListing = _listing(_episode(1, _NOW + _DAY))
    live: SubscriptionRecord = merge_listing(_record(), _read(listing), _NOW)
    snapshot: SubscriptionRecord = merge_listing(
        live, _read(_listing(_episode(1, _NOW + _DAY), _episode(2, _NOW + 2 * _DAY)), live=False), _NOW + _DAY
    )
    assert (live.kitsu_id, live.mapping, live.refreshed_at) == (
        10,
        replace(_mapping(), max_age_s=None),
        _NOW.isoformat(),
    )
    assert (snapshot.mapping, snapshot.refreshed_at) == (live.mapping, live.refreshed_at)
    assert [item.number for item in snapshot.targets] == [1, 2]


def test_a_live_read_of_another_kitsu_entry_is_a_conflict_until_a_consistent_live_read() -> None:
    record: SubscriptionRecord = merge_listing(_record(), _read(_listing(_episode(1, _NOW + _DAY))), _NOW)
    conflict: SubscriptionRecord = merge_listing(record, _read(_listing(_episode(2, _NOW + _DAY)), kitsu=11), _NOW)
    unchanged: SubscriptionRecord = merge_listing(conflict, _read(_listing(_episode(2, _NOW + _DAY)), live=False), _NOW)
    repaired: SubscriptionRecord = merge_listing(conflict, _read(_listing(_episode(1, _NOW + _DAY))), _NOW)
    assert conflict == replace(record, problem=SubscriptionProblem.CATALOG_CONFLICT)
    assert unchanged.problem is SubscriptionProblem.CATALOG_CONFLICT
    assert repaired.problem is None


_MIGRATED: datetime = _NOW - 2 * _DAY


def _reviewing() -> SubscriptionRecord:
    return _record(
        cut=None,
        subscribed_at=(_NOW - 10 * _DAY).isoformat(),
        migrated_at=_MIGRATED.isoformat(),
        review_pending=True,
    )


@pytest.mark.parametrize(
    "read",
    [
        _read(_listing(_episode(1, _NOW - 3 * _DAY)), live=False),
        _read(_listing(_episode(1, _NOW - 3 * _DAY)), kitsu=None, live=False),
        _read(_listing(_episode(1, _NOW - 3 * _DAY), warning="TITLE_CATALOG_FAILED")),
    ],
    ids=["snapshot", "empty-404", "schedule-failed"],
)
def test_a_migration_review_finishes_only_on_complete_live_data(read: ListingRead) -> None:
    record: SubscriptionRecord = _reviewing()
    assert merge_listing(record, read, _NOW) == record


def test_a_finished_review_pauses_for_a_target_due_before_migration_that_no_old_order_covers() -> None:
    read: ListingRead = _read(_listing(_episode(1, _MIGRATED - _DAY), _episode(2, _NOW + _DAY)))
    paused: SubscriptionRecord = merge_listing(_reviewing(), read, _NOW)
    covered: SubscriptionRecord = merge_listing(_reviewing(), read, _NOW, (LegacyScope(1, 1),))
    assert (paused.review_pending, paused.paused, paused.pause_reason) == (False, True, PauseReason.MIGRATED_DUE)
    assert (covered.review_pending, covered.paused) == (False, False)
    assert (covered.targets[0].state, covered.targets[0].reason) == (TargetState.MANUAL, "legacy_ordered")


def test_a_late_review_keeps_a_target_aired_after_migration_as_a_normal_due_target() -> None:
    reviewed: SubscriptionRecord = merge_listing(_reviewing(), _read(_listing(_episode(1, _MIGRATED + _DAY))), _NOW)
    assert (reviewed.review_pending, reviewed.paused) == (False, False)
    assert reviewed.targets[0].state is TargetState.DUE


_DUE: datetime = datetime(2026, 10, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("checked", "expected"),
    [
        (None, timedelta(0)),
        (-timedelta(minutes=1), timedelta(0)),
        (timedelta(0), timedelta(minutes=15)),
        (timedelta(minutes=20), timedelta(minutes=30)),
        (timedelta(hours=23, minutes=59), timedelta(hours=24)),
        (timedelta(hours=24), timedelta(hours=25)),
        (timedelta(hours=71, minutes=30), timedelta(hours=72)),
        (timedelta(hours=72), timedelta(hours=96)),
        (timedelta(hours=100), timedelta(hours=120)),
    ],
)
def test_a_due_target_is_searched_on_a_grid_of_15_min_then_hours_then_days_from_its_deadline(
    checked: timedelta | None, expected: timedelta
) -> None:
    target: SubscriptionTarget = _target(1, TargetState.DUE, _DUE)
    assert next_search_at(target, None if checked is None else _DUE + checked) == _DUE + expected


@pytest.mark.parametrize("state", [TargetState.AWAITING_AIRING, TargetState.ATTEMPTING, TargetState.SATISFIED])
def test_only_a_due_target_has_a_search_moment(state: TargetState) -> None:
    assert next_search_at(_target(1, state, _DUE), _DUE) is None


def test_frequent_checks_of_a_fresh_target_never_starve_an_old_one() -> None:
    old: SubscriptionTarget = _target(1, TargetState.DUE, _NOW - timedelta(hours=96, minutes=10))
    fresh: SubscriptionTarget = _target(2, TargetState.DUE, _NOW - timedelta(hours=1))
    record: SubscriptionRecord = _record(targets=(old, fresh), checked_at=(_NOW - timedelta(minutes=15)).isoformat())
    assert [item.number for item in search_targets(record, _NOW, manual=False)] == [1, 2]
    assert [item.number for item in search_targets(record, _NOW - timedelta(minutes=11), manual=False)] == []
    assert [item.number for item in search_targets(record, _NOW - timedelta(minutes=11), manual=True)] == [1, 2]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"review_pending": True, "cut": None, "migrated_at": _NOW.isoformat()}, _NOW),
        (
            {
                "review_pending": True,
                "cut": None,
                "migrated_at": _NOW.isoformat(),
                "paused": True,
                "pause_reason": PauseReason.USER,
            },
            _NOW,
        ),
        ({"paused": True, "pause_reason": PauseReason.USER}, None),
        ({"problem": SubscriptionProblem.CATALOG_CONFLICT}, _NOW),
        (
            {
                "anilist_id": None,
                "problem": SubscriptionProblem.SEASON_UNRECOGNIZED,
                "cut": None,
                "migrated_at": _NOW.isoformat(),
            },
            None,
        ),
        ({}, _NOW),
        ({"checked_at": _NOW.isoformat()}, _NOW + _DAY),
        (
            {
                "checked_at": _NOW.isoformat(),
                "targets": (_target(1, TargetState.AWAITING_AIRING, _NOW + 3 * _DAY / 4),),
            },
            _NOW + 3 * _DAY / 4,
        ),
        (
            {
                "checked_at": _NOW.isoformat(),
                "catalog_status": "HIATUS",
                "targets": (_target(1, TargetState.AWAITING_AIRING, _NOW + _DAY / 4),),
            },
            _NOW + _DAY,
        ),
        ({"checked_at": _NOW.isoformat(), "targets": (_target(1, TargetState.DUE, _NOW),)}, _NOW + _DAY / 96),
    ],
    ids=[
        "review",
        "review-paused",
        "paused",
        "conflict",
        "unrecognized",
        "never-checked",
        "daily-refresh",
        "airing",
        "hiatus",
        "due",
    ],
)
def test_the_next_check_follows_review_repair_airing_and_search_moments(
    changes: dict[str, object], expected: datetime | None
) -> None:
    assert next_check_at(replace(_record(), **changes), _NOW) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("age", [timedelta(0), timedelta(days=8)])
@pytest.mark.parametrize(
    ("candidate", "tried", "taken", "expected"),
    [
        (_candidate(), (), frozenset(), True),
        (_candidate(IdentityVerdict.INSUFFICIENT), (), frozenset(), False),
        (_candidate(IdentityVerdict.MISMATCH), (), frozenset(), False),
        (_candidate(supported=False), (), frozenset(), False),
        (_candidate(supported=None), (), frozenset(), True),
        (_candidate(), ("abc:0",), frozenset(), False),
        (_candidate(), (), frozenset({"abc:0"}), False),
        (_candidate(index=None), ("abc:0",), frozenset(), True),
    ],
    ids=["match", "uncertain", "mismatch", "unsupported", "unknown-container", "tried", "taken", "other-file"],
)
def test_only_a_supported_untried_match_is_eligible_whatever_the_target_age(
    candidate: RankedCandidate, tried: tuple[str, ...], taken: frozenset[str], expected: bool, age: timedelta
) -> None:
    target: SubscriptionTarget = replace(_target(4, TargetState.DUE, _NOW - age), tried=tried)
    assert eligible(candidate, target, taken) is expected


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, True),
        ({"catalog_status": "RELEASING"}, False),
        ({"episode_count": None}, False),
        ({"episode_count": 3}, False),
        (
            {
                "targets": (
                    _target(1, TargetState.SATISFIED),
                    replace(_target(2, TargetState.DUE), state=TargetState.EXHAUSTED, attempts=MAX_ATTEMPTS),
                )
            },
            False,
        ),
        ({"targets": (_target(1, TargetState.SATISFIED),)}, False),
        ({"targets": (_target(1, TargetState.SATISFIED), _target(3, TargetState.SATISFIED))}, False),
        ({"cut": None, "migrated_at": _NOW.isoformat(), "targets": (_target(2, TargetState.SATISFIED),)}, True),
    ],
    ids=["closed", "airing", "unknown-count", "count-grew", "exhausted", "missing", "beyond-count", "migrated"],
)
def test_a_finished_season_closes_only_with_every_target_satisfied(changes: dict[str, object], expected: bool) -> None:
    record: SubscriptionRecord = _record(
        catalog_status="FINISHED",
        episode_count=2,
        targets=(_target(1, TargetState.SATISFIED), _target(2, TargetState.SATISFIED)),
    )
    assert completed(replace(record, **changes)) is expected  # type: ignore[arg-type]
