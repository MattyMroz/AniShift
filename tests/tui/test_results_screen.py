from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from tui_fakes import (
    OFFLINE_ROOT,
    StubService,
    group_result,
    inspected_group,
    inspected_workspace,
    mixed_result,
    produced_artifact,
    shell,
    stub_plan,
)

from anishift.application import GroupStatus
from anishift.application.intents import ProductKind
from anishift.tui.commands.palette import palette_options
from anishift.tui.lifecycle import begin_planning
from anishift.tui.messages import RunFinished, WorkspaceLoaded
from anishift.tui.screens.manual import ManualView
from anishift.tui.screens.results import (
    MANUAL_COMMAND_NAME,
    MANUAL_KEY,
    RESULTS_COMMAND_NAME,
    WORKSPACE_COMMAND_NAME,
    ResultsView,
    recoverable_groups,
    recovery_available,
    recovery_draft,
    results_available,
    results_body,
    results_lines,
    status_text,
)
from anishift.tui.state import GroupIntentDraft, RunUiState, SessionState, UiRoute
from anishift.tui.strings import (
    EXECUTION_CANCELLED_GLYPH,
    EXECUTION_DONE_GLYPH,
    EXECUTION_FAILED_GLYPH,
    EXECUTION_STATE_CANCELLED,
    EXECUTION_STATE_FAILED,
    GROUP_COLUMN_GAP,
    PLAN_NONE,
    PLAN_OUTSIDE_WORKSPACE,
    PLAN_PRODUCTS_LABEL,
    RESULTS_EMPTY,
    RESULTS_ERROR_LABEL,
    RESULTS_PARTIAL_GLYPH,
    RESULTS_PRESERVED_LABEL,
    RESULTS_RECOVERY_HINT,
    RESULTS_STATUS_PARTIAL,
    RESULTS_STATUS_SUCCEEDED,
    RESULTS_SUMMARY,
    RESULTS_TITLE,
    RESULTS_WARNINGS_LABEL,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from anishift.application import GroupResult, RunResult
    from anishift.tui.app import AniShiftApp

_FULL_SIZE: Final[tuple[int, int]] = (110, 34)

_PAUSE_LIMIT: Final[int] = 400

_SETTLE_PAUSES: Final[int] = 8

_RUN_ID: Final[str] = "run-results"

_OTHER_RUN_ID: Final[str] = "run-older"

_ALPHA_STEM: Final[str] = "alpha"

_BETA_STEM: Final[str] = "beta"

_GAMMA_STEM: Final[str] = "gamma"

_ALPHA: Final[str] = f"group-{_ALPHA_STEM}"

_BETA: Final[str] = f"group-{_BETA_STEM}"

_GAMMA: Final[str] = f"group-{_GAMMA_STEM}"

_DELTA: Final[str] = "group-delta"

_PRODUCT_NAME: Final[str] = "alpha.pl.ass"

_KEPT_NAME: Final[str] = "beta.pl.ass"

_PRESERVED_NAME: Final[str] = "gamma.src.ass"

_OUTSIDE_PATH: Final[Path] = Path("C:/Users/private/secret-folder/delta.pl.ass")

_LOCATED_ERROR: Final[str] = "the engine stopped at C:\\secret\\episode.mkv"

_PLAIN_ERROR: Final[str] = "no subtitle source was usable"

_WARNING: Final[str] = "one voice profile was missing"

_CATALOG_COMMANDS: Final[int] = 14

_HEADING_ROW: Final[int] = 2


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("anishift.tui.ui_state.config_path", lambda: tmp_path / "settings.json")
    return tmp_path


@pytest.fixture
def stub() -> StubService:
    service: StubService = StubService()
    service.result = _mixed()
    return service


def test_a_session_without_a_finished_run_renders_the_base_state() -> None:
    assert results_lines(None) == (RESULTS_EMPTY,)
    assert RESULTS_EMPTY in results_body(SessionState())
    assert results_body(SessionState()).startswith(RESULTS_TITLE)


def test_every_group_outcome_carries_its_own_glyph_and_its_own_word() -> None:
    body: str = results_body(_session(_mixed()), root=OFFLINE_ROOT)
    for glyph in (EXECUTION_DONE_GLYPH, RESULTS_PARTIAL_GLYPH, EXECUTION_FAILED_GLYPH, EXECUTION_CANCELLED_GLYPH):
        assert glyph in body
    for word in (RESULTS_STATUS_SUCCEEDED, RESULTS_STATUS_PARTIAL, EXECUTION_STATE_FAILED, EXECUTION_STATE_CANCELLED):
        assert word in body
    assert status_text(GroupStatus.PARTIAL) == f"{RESULTS_PARTIAL_GLYPH} {RESULTS_STATUS_PARTIAL}"


def test_a_partial_group_is_never_flattened_into_a_failure() -> None:
    lines: tuple[str, ...] = results_lines(mixed_result(_partial(), run_id=_RUN_ID), root=OFFLINE_ROOT)
    heading: str = lines[_HEADING_ROW]
    assert RESULTS_STATUS_PARTIAL in heading
    assert RESULTS_PARTIAL_GLYPH in heading
    assert EXECUTION_STATE_FAILED not in heading
    assert _KEPT_NAME in "\n".join(lines)


def test_every_group_lists_the_products_it_made_and_the_ones_it_preserved() -> None:
    body: str = results_body(_session(mixed_result(_failed(), run_id=_RUN_ID)), root=OFFLINE_ROOT)
    assert f"{PLAN_PRODUCTS_LABEL}{GROUP_COLUMN_GAP}{PLAN_NONE}" in body
    assert RESULTS_PRESERVED_LABEL in body
    assert _PRESERVED_NAME in body


def test_a_group_that_produced_nothing_at_all_still_renders_every_label() -> None:
    body: str = results_body(_session(mixed_result(group_result(_ALPHA, GroupStatus.SUCCEEDED), run_id=_RUN_ID)))
    assert f"{PLAN_PRODUCTS_LABEL}{GROUP_COLUMN_GAP}{PLAN_NONE}" in body
    assert f"{RESULTS_PRESERVED_LABEL}{GROUP_COLUMN_GAP}{PLAN_NONE}" in body
    assert f"{RESULTS_ERROR_LABEL}{GROUP_COLUMN_GAP}{PLAN_NONE}" in body


def test_a_failed_group_shows_a_redacted_error_and_never_the_location_it_stopped_at() -> None:
    body: str = results_body(_session(mixed_result(_partial(), run_id=_RUN_ID)), root=OFFLINE_ROOT)
    assert RESULTS_ERROR_LABEL in body
    assert "secret" not in body
    assert "<path>" in body


def test_the_cancelled_group_of_a_run_keeps_the_products_it_had_already_made() -> None:
    body: str = results_body(_session(mixed_result(_cancelled(), run_id=_RUN_ID)), root=OFFLINE_ROOT)
    assert EXECUTION_STATE_CANCELLED in body
    assert PLAN_OUTSIDE_WORKSPACE in body


def test_no_rendered_location_ever_leaves_the_workspace_root() -> None:
    body: str = results_body(_session(_mixed()), root=OFFLINE_ROOT)
    assert _PRODUCT_NAME in body
    assert PLAN_OUTSIDE_WORKSPACE in body
    assert str(OFFLINE_ROOT) not in body
    assert str(_OUTSIDE_PATH) not in body


def test_the_warnings_of_a_run_are_listed_once_under_a_label_of_their_own() -> None:
    body: str = results_body(_session(_mixed()), root=OFFLINE_ROOT)
    assert RESULTS_WARNINGS_LABEL in body
    assert body.count(_WARNING) == 1
    quiet: str = results_body(_session(mixed_result(_succeeded(), run_id=_RUN_ID)), root=OFFLINE_ROOT)
    assert RESULTS_WARNINGS_LABEL not in quiet


def test_the_summary_counts_only_the_groups_that_succeeded() -> None:
    body: str = results_body(_session(_mixed()), root=OFFLINE_ROOT)
    assert RESULTS_SUMMARY.format(succeeded=1, total=4) in body


def test_the_note_promising_no_resume_shows_only_while_a_group_could_be_planned_again() -> None:
    assert RESULTS_RECOVERY_HINT in results_body(_session(_mixed()), root=OFFLINE_ROOT)
    finished: str = results_body(_session(mixed_result(_succeeded(), run_id=_RUN_ID)), root=OFFLINE_ROOT)
    assert RESULTS_RECOVERY_HINT not in finished


def test_only_a_failed_or_a_partial_group_can_be_planned_again() -> None:
    assert [group.group_id for group in recoverable_groups(_mixed())] == [_BETA, _GAMMA]
    assert recoverable_groups(None) == ()
    assert recoverable_groups(mixed_result(_succeeded(), _cancelled(), run_id=_RUN_ID)) == ()


def test_the_results_are_available_only_to_a_session_that_holds_one() -> None:
    assert results_available(SessionState()) is False
    assert results_available(_session(_mixed())) is True


def test_no_recovery_is_offered_while_a_dialog_covers_the_results() -> None:
    state: SessionState = _session(_mixed())
    assert recovery_available(state) is True
    state.modal_focus_stack.append(None)
    assert recovery_available(state) is False


def test_no_recovery_is_offered_while_every_group_of_a_run_finished() -> None:
    assert recovery_available(_session(mixed_result(_succeeded(), run_id=_RUN_ID))) is False


def test_a_recovery_draft_keeps_mutable_state_of_its_own() -> None:
    state: SessionState = _session(_mixed())
    fresh: GroupIntentDraft = recovery_draft(state, _GAMMA)
    assert fresh.group_id == _GAMMA
    assert fresh.products == {ProductKind.FULL_PL}
    state.manual_drafts[_GAMMA] = GroupIntentDraft(group_id=_GAMMA, products={ProductKind.MKV})
    cloned: GroupIntentDraft = recovery_draft(state, _GAMMA)
    cloned.products.add(ProductKind.MP4)
    assert state.manual_drafts[_GAMMA].products == {ProductKind.MKV}


def test_a_recovery_draft_never_carries_a_source_the_finished_run_had_chosen() -> None:
    state: SessionState = _session(_mixed())
    state.manual_drafts[_GAMMA] = GroupIntentDraft(
        group_id=_GAMMA,
        products={ProductKind.MKV},
        preferred_video_artifact_id="artifact-video",
        selected_subtitle_artifact_id="artifact-subtitle",
        selected_audio_artifact_id="artifact-audio",
        selected_audio_track_id=2,
        selected_subtitle_track_id=3,
    )
    draft: GroupIntentDraft = recovery_draft(state, _GAMMA)
    assert draft.products == {ProductKind.MKV}
    assert draft.preferred_video_artifact_id is None
    assert draft.selected_subtitle_artifact_id is None
    assert draft.selected_audio_artifact_id is None
    assert draft.selected_audio_track_id is None
    assert draft.selected_subtitle_track_id is None


def test_a_finished_run_lands_on_the_results_of_that_run(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _finish(app, pilot)
            assert app.session_state.route is UiRoute.RESULTS
            assert app.session_state.result is stub.result
            assert _view(app).display is True
            frame: str = _rendered(app)
            assert RESULTS_TITLE in frame
            assert _PRODUCT_NAME in frame
            assert RESULTS_STATUS_PARTIAL in frame

    asyncio.run(scenario())


def test_a_run_that_ended_without_a_result_never_opens_the_results(stub: StubService) -> None:
    stub.error = _refusal()

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _finish(app, pilot)
            assert app.session_state.result is None
            assert app.session_state.route is not UiRoute.RESULTS
            assert _view(app).display is False
            assert app.commands.dispatch(RESULTS_COMMAND_NAME) is False

    asyncio.run(scenario())


def test_the_results_never_render_again_once_a_new_planning_cleared_them(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _finish(app, pilot)
            assert begin_planning(app.session_state) is not None
            app.open_results()
            await _settle(pilot)
            assert app.session_state.route is UiRoute.RESULTS
            assert _view(app).display is False
            assert app.commands.dispatch(RESULTS_COMMAND_NAME) is False
            assert app.commands.command(MANUAL_COMMAND_NAME) is None

    asyncio.run(scenario())


def test_the_results_action_is_offered_only_once_the_session_holds_a_result(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.commands.command(RESULTS_COMMAND_NAME) is not None
            assert _labels(app).count(RESULTS_TITLE) == 0
            assert app.commands.dispatch(RESULTS_COMMAND_NAME) is False
            await _finish(app, pilot)
            assert _labels(app).count(RESULTS_TITLE) == 1
            assert app.commands.dispatch(RESULTS_COMMAND_NAME) is True

    asyncio.run(scenario())


def test_the_results_screen_offers_its_actions_only_while_it_is_on_screen(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.commands.command(MANUAL_COMMAND_NAME) is None
            await _finish(app, pilot)
            assert app.commands.command(MANUAL_COMMAND_NAME) is not None
            assert app.commands.command(WORKSPACE_COMMAND_NAME) is not None
            assert app.commands.dispatch(WORKSPACE_COMMAND_NAME) is True
            await _settle(pilot)
            assert app.session_state.route is UiRoute.WORKSPACE
            assert app.commands.command(MANUAL_COMMAND_NAME) is None
            assert app.commands.command(WORKSPACE_COMMAND_NAME) is None
            assert app.session_state.result is stub.result

    asyncio.run(scenario())


def test_the_slash_catalogue_stays_at_fourteen_commands_on_the_results_screen(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert len(app.commands.slash_names()) == _CATALOG_COMMANDS
            await _finish(app, pilot)
            assert len(app.commands.slash_names()) == _CATALOG_COMMANDS

    asyncio.run(scenario())


def test_opening_the_one_group_that_failed_in_manual_selects_it_alone(stub: StubService) -> None:
    stub.result = mixed_result(_succeeded(), _failed(), run_id=_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _finish(app, pilot)
            await pilot.press(MANUAL_KEY)
            await _until(pilot, lambda: app.session_state.route is UiRoute.MANUAL)
            await _settle(pilot)
            assert app.session_state.selected_group_ids == {_GAMMA}
            assert set(app.session_state.manual_drafts) == {_GAMMA}
            assert app.session_state.run_state is RunUiState.TERMINAL
            assert stub.calls == ["execute"]
            assert _GAMMA_STEM in str(app.query_one(ManualView).content)

    asyncio.run(scenario())


def test_opening_one_of_many_unfinished_groups_in_manual_asks_which_one(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _finish(app, pilot)
            await pilot.press(MANUAL_KEY)
            await _until(pilot, lambda: _top_screen(app) == "SelectDialog")
            assert app.session_state.route is UiRoute.RESULTS
            assert app.session_state.manual_drafts == {}
            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.route is UiRoute.MANUAL)
            assert app.session_state.selected_group_ids == {_BETA}

    asyncio.run(scenario())


def test_a_recovery_that_was_cancelled_leaves_the_results_untouched(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _finish(app, pilot)
            selected: set[str] = set(app.session_state.selected_group_ids)
            await pilot.press(MANUAL_KEY)
            await _until(pilot, lambda: _top_screen(app) == "SelectDialog")
            await pilot.press("escape")
            await _settle(pilot)
            assert app.session_state.route is UiRoute.RESULTS
            assert app.session_state.manual_drafts == {}
            assert app.session_state.selected_group_ids == selected

    asyncio.run(scenario())


def test_a_finished_run_of_an_older_generation_never_replaces_the_current_result(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _finish(app, pilot)
            kept: RunResult | None = app.session_state.result
            generation: int = app.session_state.generation
            older: RunResult = mixed_result(_succeeded(), run_id=_OTHER_RUN_ID)
            app.post_message(RunFinished(result=older, run_id=_OTHER_RUN_ID, generation=generation - 1))
            app.post_message(RunFinished(result=older, run_id=_OTHER_RUN_ID, generation=generation + 1))
            app.post_message(RunFinished(result=older, run_id=_RUN_ID, generation=generation))
            await _settle(pilot)
            assert app.session_state.result is kept
            assert app.session_state.route is UiRoute.RESULTS
            assert _OTHER_RUN_ID not in _rendered(app)

    asyncio.run(scenario())


def _succeeded(group_id: str = _ALPHA) -> GroupResult:
    return group_result(
        group_id,
        GroupStatus.SUCCEEDED,
        products=(produced_artifact("alpha-full", OFFLINE_ROOT / _PRODUCT_NAME),),
    )


def _partial(group_id: str = _BETA) -> GroupResult:
    return group_result(
        group_id,
        GroupStatus.PARTIAL,
        products=(produced_artifact("beta-full", OFFLINE_ROOT / _KEPT_NAME),),
        errors=(_LOCATED_ERROR,),
    )


def _failed(group_id: str = _GAMMA) -> GroupResult:
    return group_result(
        group_id,
        GroupStatus.FAILED,
        preserved=(produced_artifact("gamma-source", OFFLINE_ROOT / _PRESERVED_NAME),),
        errors=(_PLAIN_ERROR,),
    )


def _cancelled(group_id: str = _DELTA) -> GroupResult:
    return group_result(
        group_id,
        GroupStatus.CANCELLED,
        products=(produced_artifact("delta-full", _OUTSIDE_PATH),),
    )


def _mixed() -> RunResult:
    return mixed_result(_succeeded(), _partial(), _failed(), _cancelled(), run_id=_RUN_ID, warnings=(_WARNING,))


def _session(result: RunResult | None) -> SessionState:
    state: SessionState = SessionState()
    state.route = UiRoute.RESULTS
    state.run_state = RunUiState.TERMINAL
    state.result = result
    return state


def _refusal() -> Exception:
    from anishift.errors import ExecutionError  # noqa: PLC0415 - only this test needs the domain failure

    return ExecutionError("the run stopped at C:\\secret\\episode.mkv")


async def _finish(app: AniShiftApp, pilot: Any) -> None:
    await pilot.pause()
    app.post_message(
        WorkspaceLoaded(
            workspace=inspected_workspace(
                inspected_group(_ALPHA_STEM, sidecar="ass"),
                inspected_group(_BETA_STEM, sidecar="ass"),
                inspected_group(_GAMMA_STEM, sidecar="ass"),
            ),
            generation=app.session_state.generation,
        ),
    )
    await _settle(pilot)
    assert begin_planning(app.session_state) is not None
    assert app.start_execution(stub_plan()) is True
    await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
    await _settle(pilot)


def _view(app: AniShiftApp) -> ResultsView:
    return app.query_one(ResultsView)


def _rendered(app: AniShiftApp) -> str:
    return "\n".join(strip.text.rstrip() for strip in app.screen._compositor.render_strips())


def _labels(app: AniShiftApp) -> list[str]:
    return [option.label for option in palette_options(app.commands)]


def _top_screen(app: AniShiftApp) -> str:
    return type(app.screen).__name__


async def _until(pilot: Any, ready: Callable[[], bool]) -> None:
    for _ in range(_PAUSE_LIMIT):
        if ready():
            return
        await pilot.pause()


async def _settle(pilot: Any) -> None:
    for _ in range(_SETTLE_PAUSES):
        await pilot.pause()
