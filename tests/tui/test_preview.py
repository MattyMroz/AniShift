from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from tui_fakes import OFFLINE_ROOT, StubService, shell

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.intents import GroupIntent, ProductIntent, ProductKind, RunMode
from anishift.application.planning import (
    ExecutionPlan,
    GroupPlan,
    PlanProblem,
    PlanTask,
    ProcessingOrderPolicy,
    RunSettingsSnapshot,
    TaskKind,
)
from anishift.tui import lifecycle
from anishift.tui.commands.palette import palette_options
from anishift.tui.dialogs.value import ConfirmDialog
from anishift.tui.messages import PlanReady
from anishift.tui.screens.preview import (
    BACK_COMMAND_NAME,
    BACK_KEY,
    START_COMMAND_NAME,
    START_KEY,
    start_available,
)
from anishift.tui.state import GroupIntentDraft, RunUiState, SessionState, UiRoute
from anishift.tui.strings import (
    PLAN_BLOCKED_WORD,
    PLAN_KEPT_WORD,
    PLAN_REPLACES_WORD,
    PLAN_WARNING_WORD,
    PREVIEW_TITLE,
    TOOLS_CHECK_FAIL_GLYPH,
    TOOLS_CHECK_WARN_GLYPH,
)
from anishift.tui.widgets.plan_view import plan_body, plan_lines

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from anishift.tui.app import AniShiftApp
    from anishift.tui.commands.palette import CommandOption

_FULL_SIZE: Final[tuple[int, int]] = (110, 34)

_GROUP_ID: Final[str] = "episode-01"

_OTHER_GROUP_ID: Final[str] = "episode-02"

_SECRET_ROOT: Final[Path] = Path("C:/Users/private/secret-folder")


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


def _settings() -> RunSettingsSnapshot:
    return RunSettingsSnapshot(
        translation_profile_id="deepl",
        translation_fallback_chain=("google",),
        translation_max_retries=3,
        translation_concurrency=4,
        llm_profile_id="foundry/gpt-main",
        llm_max_concurrency=2,
        tts_profile_id="edge",
        tts_max_retries=3,
        tts_group_jobs=2,
        audio_profile_id="eac3",
        composition_profile_id="default",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
    )


def _intent(group_id: str) -> GroupIntent:
    return GroupIntent(
        group_id=group_id,
        mode=RunMode.AUTO,
        products=ProductIntent(requested_products=frozenset({ProductKind.FULL_PL})),
    )


def _source(group_id: str, root: Path) -> Artifact:
    path: Path = root / f"{group_id}.mkv"
    return Artifact(
        artifact_id=f"{group_id}-video",
        group_id=group_id,
        kind=ArtifactKind.VIDEO_MKV,
        path=path,
        state=ArtifactState.READY,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=path,
    )


def _intermediate(group_id: str) -> Artifact:
    return Artifact(
        artifact_id=f"{group_id}-subs",
        group_id=group_id,
        kind=ArtifactKind.SOURCE_SUBTITLES,
        path=None,
        state=ArtifactState.MISSING,
        lifetime=ArtifactLifetime.INTERMEDIATE,
    )


def _product(group_id: str, root: Path, *, preserved: Path | None = None) -> Artifact:
    return Artifact(
        artifact_id=f"{group_id}-full",
        group_id=group_id,
        kind=ArtifactKind.FULL_PL,
        path=None,
        state=ArtifactState.MISSING,
        lifetime=ArtifactLifetime.DURABLE,
        planned_destination=root / f"{group_id}.pl.ass",
        preserved_path=preserved,
    )


def _extract(group_id: str) -> PlanTask:
    return PlanTask(
        task_id=f"{group_id}-extract",
        group_id=group_id,
        kind=TaskKind.EXTRACT_SUBTITLES,
        requires=(f"{group_id}-video",),
        produces=(f"{group_id}-subs",),
        depends_on=(),
        resource_key="extraction:local",
        parameters=(("track_id", "2"), ("target_format", "ass")),
    )


def _translate(group_id: str) -> PlanTask:
    return PlanTask(
        task_id=f"{group_id}-translate",
        group_id=group_id,
        kind=TaskKind.TRANSLATE_SUBTITLES,
        requires=(f"{group_id}-subs",),
        produces=(f"{group_id}-full",),
        depends_on=(f"{group_id}-extract",),
        resource_key="translation:deepl",
        parameters=(("output_format", "ass"),),
        is_network=True,
    )


def _plan(
    *,
    root: Path = OFFLINE_ROOT,
    group_ids: tuple[str, ...] = (_GROUP_ID,),
    problems: tuple[PlanProblem, ...] = (),
    group_problems: tuple[PlanProblem, ...] = (),
    preserved: Path | None = None,
) -> ExecutionPlan:
    groups: tuple[GroupPlan, ...] = tuple(
        GroupPlan(
            group_id=group_id,
            intent=_intent(group_id),
            artifact_ids=(f"{group_id}-video", f"{group_id}-subs", f"{group_id}-full"),
            task_ids=(f"{group_id}-extract", f"{group_id}-translate"),
            problems=tuple(problem for problem in group_problems if problem.group_id == group_id),
        )
        for group_id in group_ids
    )
    artifacts: tuple[Artifact, ...] = tuple(
        artifact
        for group_id in group_ids
        for artifact in (
            _source(group_id, root),
            _intermediate(group_id),
            _product(group_id, root, preserved=preserved),
        )
    )
    tasks: tuple[PlanTask, ...] = tuple(
        task for group_id in group_ids for task in (_extract(group_id), _translate(group_id))
    )
    return ExecutionPlan(
        groups=groups,
        artifacts=artifacts,
        tasks=tasks,
        settings=_settings(),
        problems=problems + group_problems,
    )


def _overwrite_problem() -> PlanProblem:
    return PlanProblem(
        code="product_overwrite",
        message=f"{_GROUP_ID}.pl.ass already exists",
        group_id=None,
        artifact_ids=(f"{_GROUP_ID}-full",),
        is_blocking=False,
    )


def _blocking_problem() -> PlanProblem:
    return PlanProblem(
        code="missing_source",
        message="No readable subtitle source",
        group_id=None,
        artifact_ids=(),
        is_blocking=True,
    )


def _stub(plan: ExecutionPlan) -> StubService:
    service: StubService = StubService()
    service.plan = plan
    return service


def _frame(app: AniShiftApp) -> str:
    return "\n".join(strip.text.rstrip() for strip in app.screen._compositor.render_strips())


def _row(app: AniShiftApp, name: str) -> CommandOption | None:
    return next((option for option in palette_options(app.commands) if option.name == name), None)


async def _preview(app: AniShiftApp, plan: ExecutionPlan, *, pilot: Any, origin: UiRoute = UiRoute.MANUAL) -> None:
    state = app.session_state
    lifecycle.navigate(state, origin)
    generation: int | None = lifecycle.begin_planning(state)
    assert generation is not None
    app.post_message(PlanReady(plan=plan, generation=generation))
    await pilot.pause()
    await pilot.pause()


def test_a_plan_projects_the_sources_the_operations_and_the_products_of_every_group() -> None:
    body: str = plan_body(_plan(group_ids=(_GROUP_ID, _OTHER_GROUP_ID)), root=OFFLINE_ROOT)
    assert _GROUP_ID in body
    assert _OTHER_GROUP_ID in body
    assert f"{_GROUP_ID}.mkv" in body
    assert "Extract subtitles" in body
    assert "Translate subtitles" in body
    assert f"{_GROUP_ID}.pl.ass" in body


def test_the_operations_keep_the_order_the_plan_would_execute_them_in() -> None:
    body: str = plan_body(_plan(), root=OFFLINE_ROOT)
    assert body.index("Extract subtitles") < body.index("Translate subtitles")


def test_no_projected_location_reaches_outside_the_workspace_it_belongs_to() -> None:
    body: str = plan_body(_plan(root=_SECRET_ROOT), root=OFFLINE_ROOT)
    assert "secret-folder" not in body
    assert "C:/Users/private" not in body
    assert str(_SECRET_ROOT) not in body
    assert "outside the workspace" in body


def test_a_projected_location_stays_relative_to_the_workspace() -> None:
    body: str = plan_body(_plan(root=OFFLINE_ROOT), root=OFFLINE_ROOT)
    assert str(OFFLINE_ROOT) not in body
    assert f"{_GROUP_ID}.mkv" in body


def test_a_plan_problem_carries_a_glyph_and_a_word_never_a_colour_alone() -> None:
    blocked: str = plan_body(_plan(problems=(_blocking_problem(),)), root=OFFLINE_ROOT)
    assert f"{TOOLS_CHECK_FAIL_GLYPH} {PLAN_BLOCKED_WORD}" in blocked
    warned: str = plan_body(_plan(problems=(_overwrite_problem(),)), root=OFFLINE_ROOT)
    assert f"{TOOLS_CHECK_WARN_GLYPH} {PLAN_WARNING_WORD}" in warned


def test_a_plan_names_the_engines_and_the_model_it_would_run() -> None:
    body: str = plan_body(_plan(), root=OFFLINE_ROOT)
    assert "deepl" in body
    assert "foundry/gpt-main" in body
    assert "edge" in body


def test_a_product_that_would_take_the_place_of_another_says_so() -> None:
    body: str = plan_body(_plan(preserved=OFFLINE_ROOT / "kept.ass"), root=OFFLINE_ROOT)
    assert PLAN_REPLACES_WORD in body
    assert PLAN_KEPT_WORD not in body


def test_a_plan_without_a_group_projects_one_line_instead_of_failing() -> None:
    assert plan_lines(None) == ("There is no plan to preview yet",)


def test_a_group_problem_is_projected_under_the_group_that_owns_it() -> None:
    problem: PlanProblem = PlanProblem(
        code="track_missing",
        message="The chosen track is gone",
        group_id=_GROUP_ID,
        is_blocking=True,
    )
    body: str = plan_body(_plan(group_ids=(_GROUP_ID, _OTHER_GROUP_ID), group_problems=(problem,)), root=OFFLINE_ROOT)
    assert body.index("The chosen track is gone") > body.index(_GROUP_ID)
    assert body.index("The chosen track is gone") < body.index(_OTHER_GROUP_ID)


def test_a_ready_plan_lets_the_session_start_it() -> None:
    state: SessionState = SessionState()
    state.plan = _plan()
    state.run_state = RunUiState.PLANNING
    assert start_available(state) is True


def test_no_session_starts_a_plan_a_problem_blocks() -> None:
    state: SessionState = SessionState()
    state.plan = _plan(problems=(_blocking_problem(),))
    state.run_state = RunUiState.PLANNING
    assert start_available(state) is False


def test_no_session_starts_a_plan_while_a_dialog_covers_it() -> None:
    state: SessionState = SessionState()
    state.plan = _plan()
    state.run_state = RunUiState.PLANNING
    state.modal_focus_stack.append(None)
    assert start_available(state) is False


def test_no_session_starts_a_plan_outside_planning() -> None:
    state: SessionState = SessionState()
    state.plan = _plan()
    for run_state in (RunUiState.IDLE, RunUiState.RUNNING, RunUiState.CANCELLING, RunUiState.TERMINAL):
        state.run_state = run_state
        assert start_available(state) is False


def test_a_ready_plan_opens_the_preview_and_renders_it() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        app: AniShiftApp = shell(_stub(plan).as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot)
            assert app.session_state.route is UiRoute.PREVIEW
            body: str = _frame(app)
            assert PREVIEW_TITLE in body
            assert _GROUP_ID in body

    _run(scenario())


def test_the_preview_offers_the_start_and_the_back_action_only_while_it_is_on_screen() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        app: AniShiftApp = shell(_stub(plan).as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            assert _row(app, START_COMMAND_NAME) is None
            await _preview(app, plan, pilot=pilot)
            assert _row(app, START_COMMAND_NAME) is not None
            assert _row(app, BACK_COMMAND_NAME) is not None
            app.leave_preview(UiRoute.MANUAL)
            await pilot.pause()
            assert _row(app, START_COMMAND_NAME) is None

    _run(scenario())


def test_no_start_is_offered_while_a_problem_blocks_the_plan() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan(problems=(_blocking_problem(),))
        service: StubService = _stub(plan)
        app: AniShiftApp = shell(service.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot)
            assert _row(app, START_COMMAND_NAME) is None
            assert app.commands.dispatch_key(START_KEY) is False
            assert app.commands.dispatch(START_COMMAND_NAME) is False
            await pilot.pause()
            assert "execute" not in service.calls

    _run(scenario())


def test_the_start_key_runs_the_previewed_plan_once() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        service: StubService = _stub(plan)
        app: AniShiftApp = shell(service.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot)
            await pilot.press(START_KEY)
            await pilot.pause()
            assert service.calls.count("execute") == 1

    _run(scenario())


def test_a_double_start_runs_the_previewed_plan_once() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        service: StubService = _stub(plan)
        app: AniShiftApp = shell(service.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot)
            app.start_previewed_run()
            app.start_previewed_run()
            app.start_previewed_run()
            await pilot.pause()
            await pilot.pause()
            assert service.calls.count("execute") == 1

    _run(scenario())


def test_a_plan_that_would_replace_a_product_asks_before_it_starts() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan(problems=(_overwrite_problem(),))
        service: StubService = _stub(plan)
        app: AniShiftApp = shell(service.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot)
            app.start_previewed_run()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDialog)
            assert "execute" not in service.calls
            assert f"{_GROUP_ID}.pl.ass already exists" in _frame(app)

    _run(scenario())


def test_a_refused_replacement_starts_nothing_and_frees_the_next_plan() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan(problems=(_overwrite_problem(),))
        service: StubService = _stub(plan)
        app: AniShiftApp = shell(service.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot)
            app.start_previewed_run()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert "execute" not in service.calls
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_back_returns_to_the_screen_that_prepared_the_plan() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        app: AniShiftApp = shell(_stub(plan).as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot, origin=UiRoute.AUTO)
            await pilot.press(BACK_KEY)
            await pilot.pause()
            assert app.session_state.route is UiRoute.AUTO

    _run(scenario())


def test_back_from_a_manual_plan_returns_to_manual_preparation() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        app: AniShiftApp = shell(_stub(plan).as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot, origin=UiRoute.MANUAL)
            await pilot.press(BACK_KEY)
            await pilot.pause()
            assert app.session_state.route is UiRoute.MANUAL

    _run(scenario())


def test_back_gives_the_reservation_back_so_the_next_plan_can_be_prepared() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        app: AniShiftApp = shell(_stub(plan).as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _preview(app, plan, pilot=pilot)
            await pilot.press(BACK_KEY)
            await pilot.pause()
            assert app.session_state.run_state is RunUiState.IDLE
            assert lifecycle.begin_planning(app.session_state) is not None

    _run(scenario())


def test_back_keeps_every_manual_draft_the_session_holds() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        app: AniShiftApp = shell(_stub(plan).as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            draft: GroupIntentDraft = GroupIntentDraft(group_id=_GROUP_ID, products={ProductKind.FULL_PL})
            app.session_state.manual_drafts[_GROUP_ID] = draft
            await _preview(app, plan, pilot=pilot)
            await pilot.press(BACK_KEY)
            await pilot.pause()
            assert app.session_state.manual_drafts[_GROUP_ID] is draft

    _run(scenario())


def test_a_late_plan_of_an_old_generation_opens_no_preview() -> None:
    async def scenario() -> None:
        plan: ExecutionPlan = _plan()
        app: AniShiftApp = shell(_stub(plan).as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.post_message(PlanReady(plan=plan, generation=app.session_state.generation - 1))
            await pilot.pause()
            assert app.session_state.route is not UiRoute.PREVIEW
            assert app.session_state.plan is None

    _run(scenario())
