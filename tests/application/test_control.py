from __future__ import annotations

from dataclasses import replace

import pytest

from anishift.application.control import (
    AutomationPolicy,
    CommandReceipt,
    ManualHandledMarker,
    ProcessingRequest,
    RequestState,
    Reservation,
    SourceFingerprint,
    SourceSelection,
    WatchState,
    auto_admissible,
    mark_manual_handled,
    record_command,
    record_request,
    release,
    reserve,
)
from anishift.application.intents import ProductKind, RequestOrigin

_TIMESTAMP: str = "2026-09-08T12:00:00+00:00"

_FINGERPRINT: SourceFingerprint = (("episode-01.mkv", 1024, 111),)

_OTHER_FINGERPRINT: SourceFingerprint = (("episode-01.mkv", 2048, 222),)

_PRODUCTS: frozenset[ProductKind] = frozenset({ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO})


def _reservation(client_id: str = "panel", group_id: str = "episode-01") -> Reservation:
    return Reservation(
        group_id=group_id,
        fingerprint=_FINGERPRINT,
        client_id=client_id,
        reserved_at=_TIMESTAMP,
    )


def _request(
    *,
    request_id: str = "request-1",
    group_id: str = "episode-01",
    state: RequestState = RequestState.ACCEPTED,
    attempts: int = 0,
    fingerprint: SourceFingerprint = _FINGERPRINT,
) -> ProcessingRequest:
    return ProcessingRequest(
        request_id=request_id,
        generation=1,
        group_ids=(group_id,),
        fingerprints={group_id: fingerprint},
        origin=RequestOrigin.USER,
        source_selection=SourceSelection.AUTO,
        rebuild=None,
        settings={"llm_max_concurrency": 4},
        state=state,
        attempts=attempts,
        accepted_at=_TIMESTAMP,
    )


def _marker(products: frozenset[ProductKind], fingerprint: SourceFingerprint = _FINGERPRINT) -> ManualHandledMarker:
    return ManualHandledMarker(
        group_id="episode-01",
        fingerprint=fingerprint,
        products=products,
        request_id="request-1",
        recorded_at=_TIMESTAMP,
    )


def _admissible(state: WatchState, *, directory: str = "", products: frozenset[ProductKind] = _PRODUCTS) -> bool:
    return auto_admissible(state, state.policy, "episode-01", directory, _FINGERPRINT, products)


@pytest.mark.parametrize("auto_enabled", [True, False])
def test_automatic_admission_asks_the_switch_alone_and_never_a_subscription(auto_enabled: bool) -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=auto_enabled)
    state: WatchState = WatchState(policy=policy)

    assert policy.effective_auto("") is auto_enabled
    assert _admissible(state) is auto_enabled


def test_a_directory_without_an_exception_inherits_the_library_setting() -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=True, directory_exceptions={"A": False})

    assert policy.effective_auto("A/B") is False
    assert policy.effective_auto("C") is True


def test_the_nearest_exception_wins_over_the_one_above_it() -> None:
    policy: AutomationPolicy = AutomationPolicy(
        auto_enabled=True,
        directory_exceptions={"A": False, "A/B": True},
    )

    assert policy.effective_auto("A/B") is True
    assert policy.effective_auto("A/B/C") is True
    assert policy.effective_auto("A/D") is False


def test_the_global_switch_blocks_a_directory_that_allows_automatic_work() -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=False, directory_exceptions={"A": True})

    assert policy.effective_auto("A") is False
    assert _admissible(WatchState(policy=policy), directory="A") is False


def test_a_root_exception_applies_to_the_library_root() -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=True, directory_exceptions={"": False})

    assert policy.effective_auto("") is False
    assert policy.effective_auto("A") is False


def test_a_reservation_of_another_client_refuses_the_reservation_and_automatic_work() -> None:
    state: WatchState = WatchState(policy=AutomationPolicy(auto_enabled=True), reservations=(_reservation(),))

    assert reserve(state, _reservation(client_id="cli")) is None
    assert _admissible(state) is False


def test_the_holding_client_renews_its_own_reservation_without_duplicating_it() -> None:
    state: WatchState = WatchState(reservations=(_reservation(),))

    renewed: WatchState | None = reserve(state, replace(_reservation(), reserved_at="2026-09-08T13:00:00+00:00"))

    assert renewed is not None
    assert len(renewed.reservations) == 1
    assert renewed.reservations[0].reserved_at == "2026-09-08T13:00:00+00:00"


def test_releasing_a_reservation_lets_another_client_take_the_group() -> None:
    state: WatchState = WatchState(reservations=(_reservation(),))

    freed: WatchState = release(state, "episode-01", "panel")
    taken: WatchState | None = reserve(freed, _reservation(client_id="cli"))

    assert freed.reservations == ()
    assert taken is not None
    assert taken.reservations[0].client_id == "cli"


def test_a_release_by_another_client_leaves_the_reservation_alone() -> None:
    state: WatchState = WatchState(reservations=(_reservation(),))

    assert release(state, "episode-01", "cli") is state


def test_an_accepted_request_refuses_a_reservation_and_automatic_work() -> None:
    state: WatchState = record_request(WatchState(policy=AutomationPolicy(auto_enabled=True)), _request())

    assert reserve(state, _reservation()) is None
    assert _admissible(state) is False


def test_a_finished_request_leaves_the_group_free_again() -> None:
    accepted: WatchState = record_request(WatchState(policy=AutomationPolicy(auto_enabled=True)), _request())

    finished: WatchState = record_request(accepted, _request(state=RequestState.SUCCEEDED))

    assert len(finished.requests) == 1
    assert _admissible(finished) is True


def test_a_manual_decision_blocks_products_it_did_not_cover_for_that_version() -> None:
    state: WatchState = mark_manual_handled(
        WatchState(policy=AutomationPolicy(auto_enabled=True)),
        _marker(frozenset({ProductKind.FULL_PL})),
    )

    assert _admissible(state) is False
    assert _admissible(state, products=frozenset({ProductKind.FULL_PL})) is True


def test_a_manual_decision_of_another_version_of_the_sources_lets_automatic_work_through() -> None:
    state: WatchState = mark_manual_handled(
        WatchState(policy=AutomationPolicy(auto_enabled=True)),
        _marker(frozenset({ProductKind.FULL_PL}), fingerprint=_OTHER_FINGERPRINT),
    )

    assert _admissible(state) is True


def test_a_second_manual_decision_of_the_same_version_replaces_the_first() -> None:
    first: WatchState = mark_manual_handled(WatchState(), _marker(frozenset({ProductKind.FULL_PL})))

    second: WatchState = mark_manual_handled(first, _marker(_PRODUCTS))

    assert len(second.markers) == 1
    assert second.markers[0].products == _PRODUCTS


def test_an_exhausted_retry_budget_of_that_version_blocks_automatic_work() -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=True)
    exhausted: WatchState = record_request(
        WatchState(policy=policy),
        _request(state=RequestState.FAILED, attempts=policy.external_retry_budget),
    )
    remaining: WatchState = record_request(
        WatchState(policy=policy),
        _request(state=RequestState.FAILED, attempts=policy.external_retry_budget - 1),
    )

    assert _admissible(exhausted) is False
    assert _admissible(remaining) is True


def test_a_failed_request_of_another_version_does_not_block_the_new_one() -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=True)
    state: WatchState = record_request(
        WatchState(policy=policy),
        _request(
            state=RequestState.FAILED,
            attempts=policy.external_retry_budget,
            fingerprint=_OTHER_FINGERPRINT,
        ),
    )

    assert _admissible(state) is True


def test_an_accepted_command_identifier_is_recorded_once() -> None:
    receipt: CommandReceipt = CommandReceipt("command-1", _TIMESTAMP, {"enabled": True})
    recorded: WatchState = record_command(WatchState(), receipt)

    repeated: WatchState = record_command(recorded, CommandReceipt("command-1", "2026-09-08T13:00:00+00:00", {}))

    assert repeated is recorded
    assert recorded.command_receipts == (receipt,)


def test_a_request_refuses_a_settings_snapshot_carrying_a_secret() -> None:
    with pytest.raises(ValueError, match="secret"):
        replace(_request(), settings={"palantir_token": "abc"})
