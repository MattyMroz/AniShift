from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Final, cast

from anishift.application import ExecutionPlan, RunEvent, RunResult
from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    SourceGroup,
)
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
from anishift.application.intents import (
    BurnSubtitleProduct,
    ExternalAudioRole,
    GroupIntent,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.tui.lifecycle import (
    ALLOWED_RUN_TRANSITIONS,
    abandon_planning,
    accepts_message,
    begin_planning,
    begin_run,
    close_modal,
    fail_run,
    finish_run,
    navigate,
    open_modal,
    plan_ready,
    record_run_events,
    request_cancel,
    run_transition_allowed,
    set_workspace,
)
from anishift.tui.state import GroupIntentDraft, RunUiState, SessionState, UiRoute

_ROUTES: Final[tuple[str, ...]] = (
    "workspace",
    "auto",
    "manual",
    "preview",
    "execution",
    "results",
    "tools",
)

_RUN_STATES: Final[tuple[str, ...]] = ("idle", "planning", "running", "cancelling", "terminal")

_TRANSITIONS: Final[frozenset[tuple[RunUiState, RunUiState]]] = frozenset(
    {
        (RunUiState.IDLE, RunUiState.PLANNING),
        (RunUiState.PLANNING, RunUiState.IDLE),
        (RunUiState.PLANNING, RunUiState.RUNNING),
        (RunUiState.RUNNING, RunUiState.CANCELLING),
        (RunUiState.RUNNING, RunUiState.TERMINAL),
        (RunUiState.CANCELLING, RunUiState.TERMINAL),
        (RunUiState.TERMINAL, RunUiState.PLANNING),
    },
)


def _workspace(*stems: str) -> InspectedWorkspace:
    groups: list[InspectedSourceGroup] = []
    for stem in stems:
        path: Path = Path(f"{stem}.mkv")
        artifact: Artifact = Artifact(
            artifact_id=f"{stem}-video",
            group_id=stem,
            kind=ArtifactKind.VIDEO_MKV,
            path=path,
            state=ArtifactState.READY,
            lifetime=ArtifactLifetime.SOURCE,
            planned_destination=path,
        )
        source: SourceGroup = SourceGroup(
            group_id=stem,
            stem=stem,
            directory=Path(),
            artifacts=(artifact,),
        )
        groups.append(
            InspectedSourceGroup(source=source, artifacts=(artifact,), media_catalogs={}, conflicts=()),
        )
    return InspectedWorkspace(groups=tuple(groups), warnings=())


def _manual_intent() -> GroupIntent:
    return GroupIntent(
        group_id="ep01",
        mode=RunMode.MANUAL,
        products=ProductIntent(
            frozenset({ProductKind.MKV, ProductKind.NARRATION_AUDIO}),
            mkv_tracks=frozenset({MkvTrackProduct.NARRATION_AUDIO}),
            burn_subtitle_product=BurnSubtitleProduct.NONE,
            mp4_audio_source=Mp4AudioSource.AUTO,
        ),
        subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
        translation_action=TranslationAction.TRANSLATE,
        preferred_video_artifact_id="ep01-video",
        selected_subtitle_track_id=3,
        selected_audio_artifact_id="ep01-audio",
        source_subtitle_language="eng",
        external_audio_role=ExternalAudioRole.SOURCE_AUDIO,
        subtitle_output_format=SubtitleOutputFormat.ASS,
    )


def test_routes_are_exactly_the_seven_allowed_screens() -> None:
    assert tuple(route.value for route in UiRoute) == _ROUTES


def test_settings_is_a_dialog_and_never_a_route() -> None:
    assert "settings" not in {route.value for route in UiRoute}


def test_run_states_are_exactly_the_five_explicit_states() -> None:
    assert tuple(run_state.value for run_state in RunUiState) == _RUN_STATES


def test_allowed_run_transitions_are_exactly_the_declared_edges() -> None:
    declared: set[tuple[RunUiState, RunUiState]] = {
        (current, target) for current, targets in ALLOWED_RUN_TRANSITIONS.items() for target in targets
    }
    assert declared == set(_TRANSITIONS)
    assert set(ALLOWED_RUN_TRANSITIONS) == set(RunUiState)


def test_every_run_state_pair_outside_the_contract_is_refused() -> None:
    for current in RunUiState:
        for target in RunUiState:
            assert run_transition_allowed(current, target) is ((current, target) in _TRANSITIONS)


def test_an_illegal_transition_leaves_the_run_state_untouched() -> None:
    state: SessionState = SessionState()
    assert begin_run(state, "run-1") is False
    assert state.run_state is RunUiState.IDLE
    assert state.active_run_id is None


def test_run_lifecycle_walks_from_idle_to_terminal() -> None:
    state: SessionState = SessionState()
    walk: list[RunUiState] = []
    assert begin_planning(state) == 1
    walk.append(state.run_state)
    assert begin_run(state, "run-1") is True
    walk.append(state.run_state)
    assert request_cancel(state) is True
    walk.append(state.run_state)
    assert fail_run(state, "Anulowano") is True
    walk.append(state.run_state)
    assert walk == [
        RunUiState.PLANNING,
        RunUiState.RUNNING,
        RunUiState.CANCELLING,
        RunUiState.TERMINAL,
    ]
    assert state.active_run_id is None


def test_planning_can_be_abandoned_without_a_run() -> None:
    state: SessionState = SessionState()
    begin_planning(state)
    assert abandon_planning(state, "Nie ukończono") is True
    assert state.run_state is RunUiState.IDLE
    assert state.plan is None
    assert state.error_message == "Nie ukończono"


def test_a_new_generation_is_reserved_for_every_planning_attempt() -> None:
    state: SessionState = SessionState()
    assert begin_planning(state) == 1
    abandon_planning(state, "Nie ukończono")
    assert begin_planning(state) == 2
    assert state.generation == 2


def test_planning_clears_the_previous_attempt() -> None:
    state: SessionState = SessionState()
    state.error_message = "Nie ukończono"
    state.run_events.append(cast("RunEvent", object()))
    begin_planning(state)
    assert state.error_message is None
    assert state.run_events == []
    assert state.plan is None
    assert state.result is None


def test_a_message_of_the_current_generation_is_accepted() -> None:
    state: SessionState = SessionState(generation=4)
    assert accepts_message(state, generation=4) is True


def test_a_message_of_a_lower_generation_is_ignored() -> None:
    state: SessionState = SessionState(generation=4)
    assert accepts_message(state, generation=3) is False


def test_a_message_of_a_higher_generation_is_ignored() -> None:
    state: SessionState = SessionState(generation=4)
    assert accepts_message(state, generation=5) is False


def test_a_message_of_another_run_is_ignored() -> None:
    state: SessionState = SessionState(generation=1, active_run_id="run-1")
    assert accepts_message(state, generation=1, run_id="run-2") is False
    assert accepts_message(state, generation=1, run_id="run-1") is True


def test_a_run_message_is_ignored_when_no_run_is_tracked() -> None:
    state: SessionState = SessionState(generation=1)
    assert accepts_message(state, generation=1, run_id="run-1") is False


def test_navigation_keeps_the_active_run_the_plan_and_every_draft() -> None:
    state: SessionState = SessionState()
    draft: GroupIntentDraft = GroupIntentDraft(group_id="ep01", products={ProductKind.MKV})
    state.manual_drafts["ep01"] = draft
    begin_planning(state)
    begin_run(state, "run-1")
    record_run_events(state, ())
    assert navigate(state, UiRoute.EXECUTION) is True
    assert state.route is UiRoute.EXECUTION
    assert state.run_state is RunUiState.RUNNING
    assert state.active_run_id == "run-1"
    assert state.manual_drafts["ep01"] is draft


def test_navigation_to_the_current_route_changes_nothing() -> None:
    state: SessionState = SessionState()
    assert navigate(state, UiRoute.WORKSPACE) is False


def test_a_reloaded_workspace_keeps_only_selection_that_still_exists() -> None:
    state: SessionState = SessionState()
    state.selected_group_ids = {"ep01", "ep02"}
    state.manual_drafts = {
        "ep01": GroupIntentDraft(group_id="ep01", products={ProductKind.MKV}),
        "ep02": GroupIntentDraft(group_id="ep02", products={ProductKind.MKV}),
    }
    set_workspace(state, _workspace("ep01"))
    assert state.selected_group_ids == {"ep01"}
    assert set(state.manual_drafts) == {"ep01"}
    assert state.group_count == 1


def test_a_session_without_a_workspace_counts_no_group() -> None:
    assert SessionState().group_count == 0


def test_closing_a_modal_layer_restores_the_focus_that_opened_it() -> None:
    state: SessionState = SessionState()
    open_modal(state, "workspace-table")
    open_modal(state, "settings-tree")
    assert close_modal(state) == "settings-tree"
    assert close_modal(state) == "workspace-table"
    assert state.focus_id == "workspace-table"


def test_closing_a_modal_layer_that_was_never_opened_restores_nothing() -> None:
    state: SessionState = SessionState()
    assert close_modal(state) is None
    assert state.modal_focus_stack == []


def test_draft_covers_every_decision_of_the_current_group_intent() -> None:
    intent_names: set[str] = {field.name for field in fields(GroupIntent)} - {"mode", "products"}
    product_names: set[str] = {field.name for field in fields(ProductIntent)} - {"requested_products"}
    draft_names: set[str] = {field.name for field in fields(GroupIntentDraft)} - {"products"}
    assert draft_names == intent_names | product_names


def test_a_draft_round_trips_a_manual_group_intent() -> None:
    intent: GroupIntent = _manual_intent()
    assert GroupIntentDraft.from_intent(intent).to_intent() == intent


def test_a_draft_always_materializes_a_manual_intent() -> None:
    draft: GroupIntentDraft = GroupIntentDraft(group_id="ep01", products={ProductKind.FULL_PL})
    assert draft.to_intent().mode is RunMode.MANUAL


def test_a_cloned_draft_owns_its_mutable_collections() -> None:
    draft: GroupIntentDraft = GroupIntentDraft.from_intent(_manual_intent())
    clone: GroupIntentDraft = draft.clone_for("ep02")
    clone.products.add(ProductKind.MP4)
    clone.mkv_tracks.clear()
    assert clone.group_id == "ep02"
    assert draft.group_id == "ep01"
    assert draft.products == {ProductKind.MKV, ProductKind.NARRATION_AUDIO}
    assert draft.mkv_tracks == {MkvTrackProduct.NARRATION_AUDIO}


def test_a_draft_restored_from_an_intent_owns_its_collections() -> None:
    intent: GroupIntent = _manual_intent()
    draft: GroupIntentDraft = GroupIntentDraft.from_intent(intent)
    draft.products.clear()
    draft.mkv_tracks.clear()
    assert intent.products.requested_products == {ProductKind.MKV, ProductKind.NARRATION_AUDIO}
    assert intent.products.mkv_tracks == {MkvTrackProduct.NARRATION_AUDIO}


def test_a_stored_plan_survives_navigation() -> None:
    state: SessionState = SessionState()
    plan: ExecutionPlan = cast("ExecutionPlan", object())
    begin_planning(state)
    plan_ready(state, plan)
    navigate(state, UiRoute.PREVIEW)
    assert state.plan is plan
    assert state.run_state is RunUiState.PLANNING


def test_a_finished_run_keeps_its_result_and_releases_the_run_id() -> None:
    state: SessionState = SessionState()
    result: RunResult = cast("RunResult", object())
    begin_planning(state)
    begin_run(state, "run-1")
    assert finish_run(state, result) is True
    assert state.run_state is RunUiState.TERMINAL
    assert state.result is result
    assert state.active_run_id is None
