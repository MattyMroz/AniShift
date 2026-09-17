from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AudiobookRecipe,
    AutomationPolicy,
    CommandReceipt,
    ManualHandledMarker,
    NarrationTimeline,
    PendingDeletion,
    PreflightFindingKind,
    ProcessingRequest,
    ReadyGroup,
    RecipePreferences,
    RequestState,
    Reservation,
    SourceFingerprint,
    SourceSelection,
    TextResultFormat,
    TranslateRecipe,
    WatchState,
    auto_admissible,
    mark_manual_handled,
    preflight,
    record_command,
    record_request,
    release,
    reserve,
)
from anishift.application.intents import (
    GroupIntent,
    ProductIntent,
    ProductKind,
    RebuildRequest,
    RequestOrigin,
    RunMode,
    TranslationAction,
)
from anishift.application.workflows import WorkflowTarget
from anishift.config.workspace import ensure_workspace_dir, occupied_task_dirs

_TIMESTAMP: str = "2026-09-08T12:00:00+00:00"

_WINDOWS_PATH_ESCAPES: tuple[str, ...] = ("C:/outside.mkv", "C:outside.mkv") if sys.platform == "win32" else ()

_PATH_ESCAPES: tuple[str, ...] = (
    "../../outside.mkv",
    "ready/../../outside.mkv",
    "/outside.mkv",
    "//server/share/outside.mkv",
    " ",
    *_WINDOWS_PATH_ESCAPES,
)

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
def test_automatic_admission_follows_the_global_switch(auto_enabled: bool) -> None:
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


def test_a_running_request_refuses_a_reservation_and_automatic_work() -> None:
    state: WatchState = record_request(
        WatchState(policy=AutomationPolicy(auto_enabled=True)), _request(state=RequestState.RUNNING)
    )

    assert reserve(state, _reservation()) is None
    assert _admissible(state) is False


@pytest.mark.parametrize("terminal", [RequestState.SUCCEEDED, RequestState.CANCELLED])
def test_a_finished_request_without_failure_leaves_the_group_free_again(terminal: RequestState) -> None:
    accepted: WatchState = record_request(WatchState(policy=AutomationPolicy(auto_enabled=True)), _request())

    finished: WatchState = record_request(accepted, _request(state=terminal))

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


@pytest.mark.parametrize("terminal", [RequestState.FAILED, RequestState.PARTIAL])
@pytest.mark.parametrize("attempts", [1, 2, 3])
def test_a_terminal_failure_blocks_automatic_work_regardless_of_retry_budget(
    terminal: RequestState, attempts: int
) -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=True)
    state: WatchState = record_request(
        WatchState(policy=policy),
        _request(state=terminal, attempts=attempts),
    )

    assert _admissible(state) is False


@pytest.mark.parametrize("problem", [None, "Automatic recovery attempts are exhausted"])
def test_a_later_success_supersedes_only_an_old_failure_without_an_unresolved_problem(problem: str | None) -> None:
    failed: ProcessingRequest = replace(_request(state=RequestState.FAILED, attempts=3), problem=problem)
    succeeded: ProcessingRequest = replace(
        _request(request_id="retry", state=RequestState.SUCCEEDED), accepted_at="2026-09-08T13:00:00+00:00"
    )
    state: WatchState = WatchState(policy=AutomationPolicy(auto_enabled=True), requests=(succeeded, failed))

    assert _admissible(state) is (problem is None)
    assert _admissible(mark_manual_handled(state, _marker(frozenset({ProductKind.FULL_PL})))) is False


def test_a_narrow_rebuild_keeps_the_unresolved_remote_request_and_its_receipt_protected() -> None:
    failed: ProcessingRequest = replace(
        _request(state=RequestState.FAILED),
        problem="A remote operation was interrupted without confirmation",
    )
    receipt: CommandReceipt = CommandReceipt("original-start", _TIMESTAMP, {"run_id": failed.request_id})
    state: WatchState = WatchState(
        policy=AutomationPolicy(auto_enabled=True), requests=(failed,), command_receipts=(receipt,)
    )
    products: frozenset[ProductKind] = frozenset({ProductKind.FULL_PL})
    succeeded: ProcessingRequest = replace(
        _request(request_id="narrow-rebuild", state=RequestState.SUCCEEDED),
        accepted_at="2026-09-08T13:00:00+00:00",
        source_selection=SourceSelection.MANUAL,
        rebuild=RebuildRequest(products),
        intents=(GroupIntent("episode-01", RunMode.MANUAL, ProductIntent(products)),),
    )
    rebuilt: WatchState = record_request(state, succeeded)

    assert _admissible(rebuilt) is False
    assert rebuilt.requests == (failed, succeeded)
    assert rebuilt.command_receipts == (receipt,)
    assert (
        auto_admissible(
            rebuilt,
            rebuilt.policy,
            "episode-01",
            "",
            _FINGERPRINT,
            _PRODUCTS,
            succeeded_groups={failed.request_id: frozenset(failed.group_ids)},
        )
        is False
    )

    resumed: WatchState = record_request(
        rebuilt, replace(failed, state=RequestState.SUCCEEDED, generation=2, problem=None)
    )

    assert _admissible(resumed) is True
    assert resumed.command_receipts == (receipt,)
    assert resumed.requests[-1].request_id == failed.request_id


def test_another_groups_success_does_not_supersede_a_failure() -> None:
    state: WatchState = WatchState(
        policy=AutomationPolicy(auto_enabled=True),
        requests=(
            _request(state=RequestState.FAILED),
            _request(request_id="other", group_id="other", state=RequestState.SUCCEEDED),
        ),
    )

    assert _admissible(state) is False


@pytest.mark.parametrize("terminal", [RequestState.FAILED, RequestState.PARTIAL])
def test_a_failed_request_of_another_version_does_not_block_the_new_one(terminal: RequestState) -> None:
    policy: AutomationPolicy = AutomationPolicy(auto_enabled=True)
    state: WatchState = record_request(
        WatchState(policy=policy),
        _request(
            state=terminal,
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


@pytest.mark.parametrize("secret", ["palantir_token", "deepl_api_key", "qbittorrent_password", "client_secret"])
def test_a_request_refuses_a_settings_snapshot_carrying_a_secret(secret: str) -> None:
    with pytest.raises(ValueError, match="secret"):
        replace(_request(), settings={secret: "abc"})


def test_a_request_accepts_a_setting_whose_name_only_resembles_a_secret() -> None:
    request: ProcessingRequest = replace(_request(), settings={"llm_max_output_tokens": 32000, "keyframe_gap": 2})

    assert request.settings["llm_max_output_tokens"] == 32000


def test_a_settled_configuration_has_nothing_to_report_before_a_transition() -> None:
    state: WatchState = replace(WatchState(), policy=AutomationPolicy(auto_enabled=True))

    assert preflight(state) == ()


def test_preflight_reports_a_pause_a_directory_exception_and_an_unfinished_request() -> None:
    state: WatchState = WatchState(
        policy=AutomationPolicy(auto_enabled=False, directory_exceptions={"Solo Leveling": False}),
        requests=(_request(state=RequestState.RUNNING), _request(request_id="request-2", state=RequestState.SUCCEEDED)),
    )

    findings = preflight(state, refused_names=("cover",), occupied_names=("subs",))

    assert [(item.kind, item.subject) for item in findings] == [
        (PreflightFindingKind.AUTOMATION_PAUSED, ""),
        (PreflightFindingKind.DIRECTORY_EXCEPTION, "Solo Leveling"),
        (PreflightFindingKind.UNFINISHED_REQUEST, "request-1"),
        (PreflightFindingKind.RESERVED_NAME_REFUSED, "cover"),
        (PreflightFindingKind.RESERVED_NAME_OCCUPIED, "subs"),
    ]


def test_preflight_composes_the_persisted_state_with_the_real_reserved_names(tmp_path: Path) -> None:
    root: Path = tmp_path / "workspace"
    root.mkdir()
    (root / "cover").write_text("mine", encoding="utf-8")
    refused: tuple[str, ...] = tuple(item.name for item in ensure_workspace_dir(root))
    (root / "audiobook" / "01.mkv").write_bytes(b"already here")
    state: WatchState = WatchState(
        policy=AutomationPolicy(auto_enabled=False, directory_exceptions={"Solo Leveling": False}),
        requests=(_request(state=RequestState.RUNNING),),
    )

    findings = preflight(state, refused_names=refused, occupied_names=occupied_task_dirs(root))

    assert [(item.kind, item.subject) for item in findings] == [
        (PreflightFindingKind.AUTOMATION_PAUSED, ""),
        (PreflightFindingKind.DIRECTORY_EXCEPTION, "Solo Leveling"),
        (PreflightFindingKind.UNFINISHED_REQUEST, "request-1"),
        (PreflightFindingKind.RESERVED_NAME_REFUSED, "cover"),
        (PreflightFindingKind.RESERVED_NAME_OCCUPIED, "audiobook"),
    ]
    assert (root / "cover").read_text(encoding="utf-8") == "mine"
    assert (root / "audiobook" / "01.mkv").read_bytes() == b"already here"


def test_preflight_leaves_the_state_exactly_as_it_was() -> None:
    state: WatchState = WatchState(requests=(_request(state=RequestState.PAUSED),))

    assert preflight(state, occupied_names=("cover",))
    assert state == WatchState(requests=(_request(state=RequestState.PAUSED),))


def _ready_group(**changes: object) -> ReadyGroup:
    group: ReadyGroup = ReadyGroup(
        set_id="set-1",
        group_id="ready-episode-01",
        stem="episode-01",
        source_directory="audiobook/Solo Leveling",
        source_stem="episode-01",
        target=WorkflowTarget.AUDIOBOOK,
        sources=("ready/episode-01.mkv",),
        products=("ready/episode-01.m4a",),
        main_result="ready/episode-01.m4a",
    )
    return replace(group, **changes)  # type: ignore[arg-type]


def _deletion() -> PendingDeletion:
    return PendingDeletion(
        operation_id="deletion-1",
        set_id="set-1",
        requested_at=_TIMESTAMP,
        files=(("ready/episode-01.mkv", 1024, 111), ("ready/episode-01.m4a", 2048, 222)),
        recycled=("ready/episode-01.mkv",),
    )


def test_a_completed_set_remembers_where_it_came_from_and_which_target_made_it() -> None:
    group: ReadyGroup = _ready_group()

    assert group.target is WorkflowTarget.AUDIOBOOK
    assert (group.source_directory, group.source_stem) == ("audiobook/Solo Leveling", "episode-01")
    assert group.pending_sources == ()


def test_a_completed_set_remembers_the_recipe_delta_it_was_admitted_with() -> None:
    admitted: RecipePreferences = RecipePreferences(
        translate=TranslateRecipe(TextResultFormat.SUBTITLES, TranslationAction.TRANSLATE),
        audiobook=AudiobookRecipe(TranslationAction.DO_NOT_TRANSLATE, NarrationTimeline.SOURCE_TIMES),
    )

    group: ReadyGroup = _ready_group(recipe=admitted)

    assert group.recipe == admitted
    assert _ready_group().recipe == RecipePreferences()


def test_a_completed_set_refuses_a_main_result_that_is_not_its_own_file() -> None:
    with pytest.raises(ValueError, match="own files"):
        _ready_group(main_result="ready/other.m4a")


@pytest.mark.parametrize("blank", [{"set_id": " "}, {"group_id": ""}, {"stem": "  "}])
def test_a_completed_set_refuses_a_missing_identity(blank: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="identity"):
        _ready_group(**blank)


@pytest.mark.parametrize("escape", _PATH_ESCAPES)
def test_a_completed_set_refuses_a_file_outside_the_library(escape: str) -> None:
    with pytest.raises(ValueError, match="relative path inside the library"):
        _ready_group(sources=(escape,))
    with pytest.raises(ValueError, match="relative path inside the library"):
        _ready_group(products=(escape,))
    with pytest.raises(ValueError, match="relative path inside the library"):
        _ready_group(main_result=escape)
    with pytest.raises(ValueError, match="relative path inside the library"):
        _ready_group(pending_sources=(escape,))


def test_a_pending_deletion_tracks_only_the_files_it_confirmed() -> None:
    deletion: PendingDeletion = _deletion()

    assert deletion.recycled == ("ready/episode-01.mkv",)
    with pytest.raises(ValueError, match="belong"):
        replace(deletion, recycled=("ready/other.mkv",))
    with pytest.raises(ValueError, match="at least one file"):
        replace(deletion, files=(), recycled=())


def test_a_pending_deletion_carries_the_identity_of_every_file_it_covers() -> None:
    deletion: PendingDeletion = _deletion()

    assert deletion.files == (("ready/episode-01.mkv", 1024, 111), ("ready/episode-01.m4a", 2048, 222))


@pytest.mark.parametrize("escape", _PATH_ESCAPES)
def test_a_pending_deletion_refuses_a_file_outside_the_library(escape: str) -> None:
    with pytest.raises(ValueError, match="relative path inside the library"):
        replace(_deletion(), files=((escape, 1024, 111),), recycled=())
    with pytest.raises(ValueError, match="relative path inside the library"):
        replace(_deletion(), recycled=(escape,))


def test_a_transfer_only_reports_complete_files_it_actually_required() -> None:
    confirmation: AcquisitionConfirmation = AcquisitionConfirmation(
        operation_id="operation-1",
        info_hash="AABBCC",
        directory="Solo Leveling",
        required_files=("episode-01.mkv", "episode-02.mkv"),
        state=AcquisitionState.ACCEPTED,
        origin=RequestOrigin.BACKGROUND,
        subscription_id=None,
        episode="1",
        updated_at=_TIMESTAMP,
        complete_files=("episode-01.mkv",),
    )

    assert confirmation.complete_files == ("episode-01.mkv",)
    with pytest.raises(ValueError, match="required from the release"):
        replace(confirmation, complete_files=("episode-03.mkv",))
