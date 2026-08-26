from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pytest
from textual.widgets import Input, OptionList
from tui_fakes import inspected_group, inspected_workspace, stub_result

from anishift.application import (
    AppService,
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    AutoPreset,
    AutoPresetDraft,
    ExecutionPlan,
    GroupIntent,
    PlanProblem,
    ProductIntent,
    ProductKind,
    RunMode,
    RunResult,
)
from anishift.application.planning import GroupPlan, ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.config import Settings, UserSettings
from anishift.config import presets as presets_module
from anishift.config.presets import PRESET_SCHEMA_VERSION, AutoPresetFile, load_presets, save_presets
from anishift.tui import auto_trigger, ui_state, workers
from anishift.tui.app import AniShiftApp
from anishift.tui.auto_trigger import AutoVerdictKind
from anishift.tui.dialogs.base import DialogScreen
from anishift.tui.messages import PlanReady, WorkspaceLoaded
from anishift.tui.screens import auto as auto_screen
from anishift.tui.screens.auto import (
    EDIT_KEY,
    RESET_KEY,
    SAVE_KEY,
    AutoSession,
    auto_body,
    preset_specs,
    resolve_request,
    run_group_ids,
)
from anishift.tui.screens.results import WORKSPACE_COMMAND_NAME as RESULTS_WORKSPACE_COMMAND_NAME
from anishift.tui.settings.editors import EditorKind, editor_for
from anishift.tui.state import RunUiState, SessionState, UiRoute
from anishift.tui.strings import (
    AUTO_CANCELLED,
    AUTO_DEFAULT_MARKER,
    AUTO_NO_CHANGES,
    AUTO_NO_GROUPS,
    AUTO_NO_WORKSPACE,
    AUTO_PLAN_BLOCKED,
    AUTO_PRESET_SAVED,
    AUTO_UNSAVED_MARKER,
)

_FULL_SIZE: Final[tuple[int, int]] = (110, 34)

_SETTLE_PAUSES: Final[int] = 30

_WAIT_LIMIT: Final[int] = 400

_GATE_SECONDS: Final[float] = 30.0

_BURST: Final[int] = 6

_ALPHA: Final[str] = "alpha-01"

_BETA: Final[str] = "beta-01"

_GROUP_ID: Final[str] = "group-alpha-01"

_ARTIFACT_ID: Final[str] = "artifact-overwrite"

_OTHER_ARTIFACT_ID: Final[str] = "artifact-other"

_PRODUCT_NAME: Final[str] = "alpha-01.pl.ass"

_OVERWRITE_MESSAGE: Final[str] = f"Existing product will be replaced atomically: {_PRODUCT_NAME}"

_BLOCKER_MESSAGE: Final[str] = "Requested products require a subtitle source"

_FAST_PRESET_ID: Final[str] = "fast"

_FAST_PRESET_NAME: Final[str] = "Subtitles only"

_EDITED_LANGUAGE: Final[str] = "jpn"

_LANGUAGE_FIELD: Final[str] = "source_subtitle_language"

_PRODUCTS_FIELD: Final[str] = "requested_products"

_TRACKS_FIELD: Final[str] = "mkv_tracks"

_PRESET_EDITORS: Final[frozenset[EditorKind]] = frozenset(
    {EditorKind.SELECT, EditorKind.MULTI_SELECT, EditorKind.TEXT},
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    monkeypatch.setattr(presets_module, "presets_path", lambda: tmp_path / "presets.json")
    return tmp_path


@pytest.fixture
def service(tmp_path: Path) -> AppService:
    env_file: Path = tmp_path / ".env"
    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(),
        inspector=cast("Any", object()),
        handler_factory=cast("Any", lambda *args, **kwargs: None),
        settings_saver=lambda draft: None,
        env_file=env_file,
    )


class AutoStub:
    def __init__(self, service: AppService) -> None:
        self._service: AppService = service
        self.calls: list[str] = []
        self.plan: ExecutionPlan = _plan()
        self.result: RunResult = stub_result()
        self.hold: threading.Event | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)

    def plan_auto(self, group_ids: Sequence[str], preset: Any) -> ExecutionPlan:
        self.calls.append("plan_auto")
        if self.hold is not None:
            assert self.hold.wait(_GATE_SECONDS)
        return self.plan

    def execute(self, plan: ExecutionPlan, sink: Any) -> RunResult:
        self.calls.append("execute")
        return self.result

    def as_service(self) -> AppService:
        return cast("AppService", self)


def test_the_auto_command_lists_every_preset_and_plans_nothing(service: AppService) -> None:
    _store(_bundled(), _fast())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            app.commands.dispatch("auto")
            await _settle(pilot)
            listed: str = "".join(_labels(app))
            assert _FAST_PRESET_NAME in listed
            assert stub.calls == []
            assert _route(app) is UiRoute.AUTO
            assert _run_state(app) is RunUiState.IDLE
            assert app.session_state.generation == 0
            assert app.is_draining is False

    _run(scenario())


def test_the_auto_surface_marks_the_default_the_preset_file_names(service: AppService) -> None:
    _store(_bundled(), _fast(), default_preset_id=_FAST_PRESET_ID)
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("auto")
            await _settle(pilot)
            assert app.session_state.default_preset_id == _FAST_PRESET_ID
            assert AUTO_DEFAULT_MARKER in "".join(_labels(app))
            assert _FAST_PRESET_NAME in auto_body(app.session_state, _session_of(app))

    _run(scenario())


def test_choosing_a_row_stores_the_default_preset_durably(service: AppService) -> None:
    _store(_bundled(), _fast())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("auto")
            await _settle(pilot)
            _filter(app, _FAST_PRESET_NAME)
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert app.session_state.default_preset_id == _FAST_PRESET_ID
            assert stub.calls == []

    _run(scenario())
    assert load_presets().default_preset_id == _FAST_PRESET_ID
    assert {preset.preset_id for preset in load_presets().presets} == {"default", _FAST_PRESET_ID}
    _assert_restarted_default(service, _FAST_PRESET_ID)


def test_a_default_the_preset_file_refuses_is_reported_and_never_kept(service: AppService) -> None:
    _store(_bundled())
    state: SessionState = SessionState()
    session: AutoSession = AutoSession(presets=(_fast(),))
    assert auto_screen.choose_default(state, _FAST_PRESET_ID) is False
    assert state.default_preset_id == "default"
    assert load_presets().default_preset_id == "default"
    assert resolve_request(state, service, session).refusal == AUTO_NO_WORKSPACE


def test_editing_a_field_changes_the_draft_and_never_the_stored_preset(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_field(pilot, app, _LANGUAGE_FIELD)
            app.screen.query_one("#value-input", Input).value = _EDITED_LANGUAGE
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            draft: AutoPresetDraft | None = app.session_state.auto_draft
            assert draft is not None
            assert draft.source_subtitle_language == _EDITED_LANGUAGE
            assert service.get_preset("default").source_subtitle_language is None
            assert AUTO_UNSAVED_MARKER in auto_body(app.session_state, _session_of(app))
            assert stub.calls == []

    _run(scenario())


def test_reading_the_field_list_leaves_the_preset_saved(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("auto")
            await _settle(pilot)
            await pilot.press(EDIT_KEY)
            await _settle(pilot)
            assert len(_labels(app)) == 5
            await pilot.press("escape")
            await _settle(pilot)
            assert app.session_state.auto_draft is None
            assert AUTO_UNSAVED_MARKER not in auto_body(app.session_state, _session_of(app))
            assert AUTO_UNSAVED_MARKER not in "".join(_labels(app))

    _run(scenario())


def test_a_started_auto_run_shows_the_groups_and_no_stale_problem(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    stub.plan = _plan(_blocker())

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            assert _route(app) is UiRoute.AUTO
            stub.plan = _plan(_overwrite())
            await pilot.press("enter")
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.result is not None)
            assert _route(app) is UiRoute.RESULTS
            assert _session_of(app).verdict is None
            assert _BLOCKER_MESSAGE not in "\n".join(_rendered(app))
            assert _OVERWRITE_MESSAGE not in "\n".join(_rendered(app))
            assert app.commands.dispatch(RESULTS_WORKSPACE_COMMAND_NAME) is True
            await _settle(pilot)
            assert _ALPHA in "\n".join(_rendered(app))

    _run(scenario())


def test_saving_the_draft_stores_it_and_resetting_drops_it(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("auto")
            await _settle(pilot)
            await pilot.press(RESET_KEY)
            await _settle(pilot)
            assert _feedback(app) == AUTO_NO_CHANGES
            app.session_state.auto_draft = _draft(source_subtitle_language=_EDITED_LANGUAGE)
            await pilot.press(SAVE_KEY)
            await _settle(pilot)
            assert _feedback(app) == AUTO_PRESET_SAVED.format(name="Polish subtitles")
            assert app.session_state.auto_draft is None
            assert service.get_preset("default").source_subtitle_language == _EDITED_LANGUAGE
            assert load_presets().presets[0].source_subtitle_language == _EDITED_LANGUAGE
            app.session_state.auto_draft = _draft(source_subtitle_language="eng")
            await pilot.press(RESET_KEY)
            await _settle(pilot)
            assert app.session_state.auto_draft is None
            assert service.get_preset("default").source_subtitle_language == _EDITED_LANGUAGE

    _run(scenario())


def test_every_automatic_preset_field_is_read_written_and_editable(service: AppService) -> None:
    _store(_bundled())
    specs = preset_specs(service, _draft(products=ProductIntent(frozenset(ProductKind))))
    assert len(specs) == 8
    assert {editor_for(spec) for spec in specs} <= _PRESET_EDITORS
    for spec in specs:
        assert spec.setting_id in auto_screen._FIELD_READERS
        assert spec.setting_id in auto_screen._FIELD_WRITERS


def test_a_field_the_products_keep_inactive_is_not_listed(service: AppService) -> None:
    _store(_bundled())
    without: tuple[str, ...] = tuple(spec.setting_id for spec in preset_specs(service, _draft()))
    with_mkv: tuple[str, ...] = tuple(
        spec.setting_id for spec in preset_specs(service, _draft(products=ProductIntent(frozenset({ProductKind.MKV}))))
    )
    assert _TRACKS_FIELD not in without
    assert _TRACKS_FIELD in with_mkv
    assert _PRODUCTS_FIELD in without


def test_the_default_run_uses_the_selection_before_the_ready_group_policy() -> None:
    state: SessionState = SessionState()
    state.workspace = inspected_workspace(
        inspected_group(_ALPHA, sidecar="ass"),
        inspected_group(_BETA),
    )
    assert run_group_ids(state) == (_GROUP_ID,)
    state.selected_group_ids = {f"group-{_BETA}"}
    assert run_group_ids(state) == (f"group-{_BETA}",)
    state.selected_group_ids = {"group-gone"}
    assert run_group_ids(state) == (_GROUP_ID,)


def test_an_empty_workspace_releases_the_trigger_with_an_instruction(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert stub.calls == []
            assert _run_state(app) is RunUiState.IDLE
            assert _feedback(app) == AUTO_NO_WORKSPACE
            assert _route(app) is UiRoute.AUTO
            assert AUTO_NO_WORKSPACE in "\n".join(_rendered(app))

    _run(scenario())


def test_a_workspace_without_one_ready_group_releases_the_trigger(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_BETA)))
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            assert stub.calls == []
            assert _run_state(app) is RunUiState.IDLE
            assert _feedback(app) == AUTO_NO_GROUPS

    _run(scenario())


def test_one_empty_enter_reserves_the_trigger_before_the_worker_starts(
    service: AppService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    seen: list[tuple[RunUiState, int, int]] = []
    original: Callable[..., None] = workers.plan_auto

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())

        def spy(host: Any, facade: Any, **kwargs: Any) -> None:
            seen.append((app.session_state.run_state, app.session_state.generation, int(kwargs["generation"])))
            original(host, facade, **kwargs)

        monkeypatch.setattr(workers, "plan_auto", spy)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            assert seen == [(RunUiState.PLANNING, 1, 1)]
            assert stub.calls == ["plan_auto", "execute"]

    _run(scenario())


def test_a_double_enter_starts_no_second_plan_and_no_second_run(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    gate: threading.Event = threading.Event()
    stub.hold = gate

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press(*(["enter"] * _BURST))
            await _until(pilot, lambda: stub.calls == ["plan_auto"])
            assert _run_state(app) is RunUiState.PLANNING
            assert app.session_state.generation == 1
            gate.set()
            await _until(pilot, lambda: app.session_state.result is not None)
            assert stub.calls == ["plan_auto", "execute"]
            assert app.session_state.generation == 1

    _run(scenario())


def test_a_safe_plan_walks_straight_into_execution(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.result is not None)
            assert stub.calls == ["plan_auto", "execute"]
            assert _top_dialog(app) == ""
            assert _run_state(app) is RunUiState.TERMINAL

    _run(scenario())


def test_a_blocking_plan_starts_nothing_and_reports_every_problem(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    stub.plan = _plan(_blocker())

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _settle(pilot)
            assert stub.calls == ["plan_auto"]
            assert _run_state(app) is RunUiState.IDLE
            assert _feedback(app) == AUTO_PLAN_BLOCKED
            assert _route(app) is UiRoute.AUTO
            assert _BLOCKER_MESSAGE in "\n".join(_rendered(app))
            assert _top_dialog(app) == ""

    _run(scenario())


def test_a_new_overwrite_is_named_and_confirmed_before_any_run(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    stub.plan = _plan(_overwrite())

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            assert stub.calls == ["plan_auto"]
            assert _PRODUCT_NAME in "\n".join(_rendered(app))
            assert _run_state(app) is RunUiState.PLANNING
            await pilot.press("escape")
            await _settle(pilot)
            assert stub.calls == ["plan_auto"]
            assert _run_state(app) is RunUiState.IDLE
            assert _feedback(app) == AUTO_CANCELLED

    _run(scenario())


def test_an_accepted_overwrite_starts_the_run_and_is_never_asked_about_again(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    stub.plan = _plan(_overwrite())

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.result is not None)
            assert stub.calls == ["plan_auto", "execute"]
            await pilot.press("enter")
            await _until(pilot, lambda: stub.calls.count("execute") == 2)
            assert stub.calls == ["plan_auto", "execute", "plan_auto", "execute"]
            assert _top_dialog(app) == ""

    _run(scenario())


def test_an_overwrite_of_another_product_is_confirmed_again(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    stub.plan = _plan(_overwrite())

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.result is not None)
            stub.plan = _plan(_overwrite(_OTHER_ARTIFACT_ID))
            await pilot.press("enter")
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            assert stub.calls == ["plan_auto", "execute", "plan_auto"]

    _run(scenario())


def test_a_plan_of_an_old_generation_never_starts_a_run(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)
    gate: threading.Event = threading.Event()
    stub.hold = gate

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _load(app, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            await _settle(pilot)
            await pilot.press("enter")
            await _until(pilot, lambda: stub.calls == ["plan_auto"])
            app.post_message(PlanReady(plan=_plan(), generation=0))
            app.post_message(PlanReady(plan=_plan(), generation=2))
            await _settle(pilot)
            assert stub.calls == ["plan_auto"]
            assert app.session_state.plan is None
            gate.set()
            await _until(pilot, lambda: app.session_state.result is not None)
            assert stub.calls == ["plan_auto", "execute"]

    _run(scenario())


def test_a_plan_no_auto_request_asked_for_is_only_stored(service: AppService) -> None:
    _store(_bundled())
    stub: AutoStub = AutoStub(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int | None = auto_trigger.reserve(app.session_state)
            assert generation == 1
            app.post_message(PlanReady(plan=_plan(_overwrite()), generation=generation))
            await _settle(pilot)
            assert stub.calls == []
            assert app.session_state.plan is not None
            assert _run_state(app) is RunUiState.PLANNING
            assert _top_dialog(app) == ""

    _run(scenario())


def test_the_verdict_answers_start_confirm_and_blocked_from_one_plan() -> None:
    assert auto_trigger.classify(_plan()).kind is AutoVerdictKind.START
    assert auto_trigger.classify(_plan()).may_start is True
    blocked = auto_trigger.classify(_plan(_blocker(), _overwrite()))
    assert blocked.kind is AutoVerdictKind.BLOCKED
    assert blocked.problems == (_BLOCKER_MESSAGE,)
    assert blocked.may_start is False
    confirm = auto_trigger.classify(_plan(_overwrite()))
    assert confirm.kind is AutoVerdictKind.CONFIRM
    assert confirm.problems == (_OVERWRITE_MESSAGE,)
    assert confirm.artifact_ids == frozenset({_ARTIFACT_ID})
    assert auto_trigger.classify(_plan(_overwrite()), accepted={_ARTIFACT_ID}).kind is AutoVerdictKind.START
    assert auto_trigger.classify(_plan(_overwrite()), accepted={_OTHER_ARTIFACT_ID}).kind is AutoVerdictKind.CONFIRM


def _plan(*problems: PlanProblem) -> ExecutionPlan:
    return ExecutionPlan(
        groups=(_group_plan(),),
        artifacts=(_artifact(_ARTIFACT_ID), _artifact(_OTHER_ARTIFACT_ID)),
        tasks=(),
        settings=_snapshot(),
        problems=problems,
    )


def _group_plan() -> GroupPlan:
    return GroupPlan(
        group_id=_GROUP_ID,
        intent=GroupIntent(
            group_id=_GROUP_ID,
            mode=RunMode.AUTO,
            products=ProductIntent(frozenset({ProductKind.FULL_PL})),
        ),
        artifact_ids=(_ARTIFACT_ID, _OTHER_ARTIFACT_ID),
        task_ids=(),
    )


def _artifact(artifact_id: str) -> Artifact:
    return Artifact(
        artifact_id=artifact_id,
        group_id=_GROUP_ID,
        kind=ArtifactKind.FULL_PL,
        path=Path(_PRODUCT_NAME),
        state=ArtifactState.READY,
        lifetime=ArtifactLifetime.DURABLE,
        planned_destination=Path(_PRODUCT_NAME),
    )


def _snapshot() -> RunSettingsSnapshot:
    return RunSettingsSnapshot(
        translation_profile_id="profile",
        translation_fallback_chain=(),
        translation_max_retries=1,
        translation_concurrency=1,
        llm_profile_id="profile",
        llm_max_concurrency=1,
        tts_profile_id="profile",
        tts_max_retries=1,
        tts_group_jobs=1,
        audio_profile_id="profile",
        composition_profile_id="profile",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
    )


def _overwrite(artifact_id: str = _ARTIFACT_ID) -> PlanProblem:
    return PlanProblem(
        code="product_overwrite",
        message=_OVERWRITE_MESSAGE,
        group_id=_GROUP_ID,
        artifact_ids=(artifact_id,),
        is_blocking=False,
    )


def _blocker() -> PlanProblem:
    return PlanProblem(code="subtitle_source_missing", message=_BLOCKER_MESSAGE, group_id=_GROUP_ID)


def _bundled() -> AutoPreset:
    return AutoPreset(
        preset_id="default",
        name="Polish subtitles",
        products=ProductIntent(requested_products=frozenset({ProductKind.FULL_PL})),
    )


def _fast() -> AutoPreset:
    return AutoPreset(
        preset_id=_FAST_PRESET_ID,
        name=_FAST_PRESET_NAME,
        products=ProductIntent(requested_products=frozenset({ProductKind.SOURCE_SUBTITLES})),
    )


def _draft(**changes: Any) -> AutoPresetDraft:
    fields: dict[str, Any] = {
        "preset_id": "default",
        "name": "Polish subtitles",
        "products": ProductIntent(requested_products=frozenset({ProductKind.FULL_PL})),
    }
    return AutoPresetDraft(**{**fields, **changes})


def _store(*presets: AutoPreset, default_preset_id: str = "default") -> None:
    save_presets(AutoPresetFile(PRESET_SCHEMA_VERSION, presets, default_preset_id))


def _assert_restarted_default(service: AppService, preset_id: str) -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("auto")
            await _settle(pilot)
            assert app.session_state.default_preset_id == preset_id

    _run(scenario())


def _load(app: AniShiftApp, workspace: Any) -> None:
    app.post_message(WorkspaceLoaded(workspace=workspace, generation=app.session_state.generation))


def _session_of(app: AniShiftApp) -> AutoSession:
    session: AutoSession = app._auto
    return session


def _route(app: AniShiftApp) -> UiRoute:
    route: UiRoute = app.session_state.route
    return route


def _run_state(app: AniShiftApp) -> RunUiState:
    state: RunUiState = app.session_state.run_state
    return state


def _feedback(app: AniShiftApp) -> str:
    feedback = app.session_state.feedback
    return "" if feedback is None else feedback.message


def _filter(app: AniShiftApp, query: str) -> None:
    app.screen.query_one("#select-filter", Input).value = query


def _labels(app: AniShiftApp) -> list[str]:
    listing: OptionList = app.screen.query_one("#select-list", OptionList)
    return [str(option.prompt) for option in listing.options]


def _top_dialog(app: AniShiftApp) -> str:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, DialogScreen):
            return type(screen).__name__
    return ""


def _rendered(app: AniShiftApp) -> list[str]:
    return [strip.text.rstrip() for strip in app.screen._compositor.render_strips()]


async def _open_field(pilot: Any, app: AniShiftApp, setting_id: str) -> None:
    app.commands.dispatch("auto")
    await _settle(pilot)
    await pilot.press(EDIT_KEY)
    await _settle(pilot)
    _filter(app, setting_id.replace("_", " "))
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)


async def _settle(pilot: Any) -> None:
    for _ in range(_SETTLE_PAUSES):
        await pilot.pause()


async def _until(pilot: Any, ready: Callable[[], bool]) -> None:
    for _ in range(_WAIT_LIMIT):
        if ready():
            return
        await pilot.pause()


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)
