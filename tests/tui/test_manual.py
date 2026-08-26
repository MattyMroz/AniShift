from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Final

import pytest
from textual.app import App, ComposeResult
from tui_fakes import inspected_group, inspected_workspace, offline_service, shell

from anishift.application import AppService
from anishift.application.intents import (
    ExternalAudioRole,
    ProductKind,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.tui import lifecycle, ui_state, workers
from anishift.tui.commands.registry import CommandRegistry
from anishift.tui.commands.spec import CommandCategory
from anishift.tui.screens import manual as manual_module
from anishift.tui.screens.manual import (
    AUDIO_COMMAND_NAME,
    COPY_COMMAND_NAME,
    CURSOR_MARK,
    PREVIEW_COMMAND_NAME,
    PREVIEW_KEY,
    SUBTITLE_COMMAND_NAME,
    ManualRow,
    ManualView,
    draft_is_valid,
    manual_body,
    manual_copy_available,
    manual_preview_available,
    manual_register_available,
    manual_rows,
    product_summary,
    selected_draft_ids,
)
from anishift.tui.state import GroupIntentDraft, RunUiState, SessionState
from anishift.tui.strings import (
    GLYPH_GAP,
    GROUP_CONFLICT_GLYPH,
    GROUP_READY_GLYPH,
    GROUP_STATE_READY,
    MANUAL_COPIED,
    MANUAL_EMPTY,
    MANUAL_NO_SELECTION,
    MANUAL_PREVIEW_INCOMPLETE,
    MANUAL_PRODUCT_FULL_PL,
    MANUAL_PRODUCT_MKV,
    MANUAL_STATE_INVALID,
    MANUAL_SUMMARY,
    MANUAL_TRANSLATION_AUTO,
    MANUAL_TRANSLATION_TRANSLATE,
    SETTING_EMPTY_VALUE,
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_PAUSE_LIMIT: Final[int] = 400

_ALPHA: Final[str] = "alpha-01"

_BETA: Final[str] = "beta-01"

_GAMMA: Final[str] = "gamma-01"

_CATALOG_COMMANDS: Final[int] = 14


class ManualApp(App[None]):
    def __init__(self, service: AppService) -> None:
        super().__init__()
        self._service = service
        self._state = SessionState()
        self._commands = CommandRegistry(lambda: self._state)
        self._view = ManualView()

    @property
    def service(self) -> AppService:
        return self._service

    @property
    def session_state(self) -> SessionState:
        return self._state

    @property
    def commands(self) -> CommandRegistry:
        return self._commands

    def compose(self) -> ComposeResult:
        yield self._view


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    return tmp_path


def _run(scenario: Any) -> None:
    asyncio.run(scenario)


async def _until(pilot: Any, ready: Any) -> None:
    for _ in range(_PAUSE_LIMIT):
        if ready():
            return
        await pilot.pause()


def _draft(group_id: str, **kwargs: Any) -> GroupIntentDraft:
    params: dict[str, Any] = {"group_id": group_id, "products": {ProductKind.FULL_PL}}
    params.update(kwargs)
    return GroupIntentDraft(**params)


def _state(*stems: str, drafts: dict[str, GroupIntentDraft] | None = None) -> SessionState:
    state = SessionState()
    state.workspace = inspected_workspace(*(inspected_group(stem, sidecar="ass") for stem in stems))
    state.selected_group_ids = {f"group-{stem}" for stem in stems}
    if drafts is not None:
        state.manual_drafts = drafts
    return state


def _harness(*stems: str, drafts: dict[str, GroupIntentDraft] | None = None) -> ManualApp:
    app = ManualApp(offline_service())
    app.session_state.workspace = inspected_workspace(*(inspected_group(stem, sidecar="ass") for stem in stems))
    app.session_state.selected_group_ids = {f"group-{stem}" for stem in stems}
    if drafts is not None:
        app.session_state.manual_drafts = drafts
    return app


def test_selected_draft_ids_are_the_intersection_of_selection_and_drafts() -> None:
    state = _state(_ALPHA, _BETA, drafts={"group-alpha-01": _draft("group-alpha-01")})
    assert selected_draft_ids(state) == ("group-alpha-01",)


def test_product_summary_lists_labels_in_order_or_the_empty_word() -> None:
    assert product_summary(set()) == SETTING_EMPTY_VALUE
    summary = product_summary({ProductKind.MKV, ProductKind.FULL_PL})
    assert summary.index(MANUAL_PRODUCT_FULL_PL) < summary.index(MANUAL_PRODUCT_MKV)


def test_draft_is_valid_rejects_a_subtitle_artifact_and_track_at_once() -> None:
    assert draft_is_valid(_draft("group-alpha-01")) is True
    conflicting = _draft("group-alpha-01", selected_subtitle_artifact_id="sub-1", selected_subtitle_track_id=1)
    assert draft_is_valid(conflicting) is False


def test_manual_body_shows_the_empty_state_without_any_row() -> None:
    assert manual_body(()) == MANUAL_EMPTY


def test_manual_body_marks_the_cursor_and_the_validity_of_every_row() -> None:
    rows = (
        ManualRow(name="a", group_id="group-a", products="P", subtitle="S", translation="T", valid=True),
        ManualRow(name="b", group_id="group-b", products="P", subtitle="S", translation="T", valid=False),
    )
    lines = manual_body(rows, cursor=1).splitlines()
    assert lines[0] == MANUAL_SUMMARY.format(count=2)
    listed = lines[2:]
    assert listed[0].startswith(GLYPH_GAP)
    assert listed[1].startswith(CURSOR_MARK)
    assert GROUP_READY_GLYPH in listed[0]
    assert GROUP_STATE_READY in listed[0]
    assert GROUP_CONFLICT_GLYPH in listed[1]
    assert MANUAL_STATE_INVALID in listed[1]


def test_each_group_keeps_its_own_independent_draft() -> None:
    drafts = {
        "group-alpha-01": _draft("group-alpha-01"),
        "group-beta-01": _draft("group-beta-01", products={ProductKind.FULL_PL, ProductKind.MKV}),
    }
    state = _state(_ALPHA, _BETA, drafts=drafts)
    drafts["group-beta-01"].translation_action = TranslationAction.TRANSLATE
    rows = {row.group_id: row for row in manual_rows(state)}
    assert rows["group-alpha-01"].translation == MANUAL_TRANSLATION_AUTO
    assert rows["group-beta-01"].translation == MANUAL_TRANSLATION_TRANSLATE
    assert MANUAL_PRODUCT_MKV in rows["group-beta-01"].products
    assert MANUAL_PRODUCT_MKV not in rows["group-alpha-01"].products
    assert state.manual_drafts["group-alpha-01"] is not state.manual_drafts["group-beta-01"]


def test_entering_manual_creates_defaults_and_keeps_existing_drafts() -> None:
    async def scenario() -> None:
        existing = _draft("group-alpha-01", products={ProductKind.MKV})
        app = _harness(_ALPHA, _BETA, drafts={"group-alpha-01": existing})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            drafts = app.session_state.manual_drafts
            assert drafts["group-alpha-01"] is existing
            assert drafts["group-alpha-01"].products == {ProductKind.MKV}
            assert "group-beta-01" in drafts
            assert drafts["group-beta-01"].products == {ProductKind.FULL_PL}

    _run(scenario())


def test_copy_to_selected_clones_values_without_sharing_the_mutable_object() -> None:
    async def scenario() -> None:
        source = _draft("group-alpha-01", products={ProductKind.FULL_PL, ProductKind.MKV})
        target = _draft("group-beta-01")
        app = _harness(_ALPHA, _BETA, drafts={"group-alpha-01": source, "group-beta-01": target})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            view.action_copy_selected()
            await pilot.pause()
            copied = app.session_state.manual_drafts["group-beta-01"]
            assert copied.group_id == "group-beta-01"
            assert copied.products == {ProductKind.FULL_PL, ProductKind.MKV}
            assert copied.products is not source.products
            copied.products.add(ProductKind.SPOKEN_PL)
            assert ProductKind.SPOKEN_PL not in source.products
            assert app.session_state.feedback is not None
            assert app.session_state.feedback.message == MANUAL_COPIED

    _run(scenario())


def test_copy_to_selected_drops_source_specific_ids() -> None:
    async def scenario() -> None:
        source = _draft(
            "group-alpha-01",
            selected_subtitle_artifact_id="artifact-group-alpha-01-source_subtitles",
            preferred_video_artifact_id="artifact-group-alpha-01-video_mkv",
        )
        target = _draft("group-beta-01")
        app = _harness(_ALPHA, _BETA, drafts={"group-alpha-01": source, "group-beta-01": target})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.query_one(ManualView).action_copy_selected()
            await pilot.pause()
            copied = app.session_state.manual_drafts["group-beta-01"]
            assert copied.selected_subtitle_artifact_id is None
            assert copied.preferred_video_artifact_id is None

    _run(scenario())


def test_conflicting_ids_are_blocked_before_plan_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[Any] = []
        monkeypatch.setattr(workers, "plan_manual", lambda *args, **kwargs: calls.append(kwargs))
        conflicting = _draft("group-alpha-01", selected_subtitle_artifact_id="sub-1", selected_subtitle_track_id=1)
        app = _harness(_ALPHA, drafts={"group-alpha-01": conflicting})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.query_one(ManualView).action_preview()
            await pilot.pause()
            assert calls == []
            assert app.session_state.run_state is RunUiState.IDLE
            assert app.session_state.plan is None
            assert app.session_state.feedback is not None
            assert app.session_state.feedback.message == MANUAL_PREVIEW_INCOMPLETE

    _run(scenario())


def test_preview_without_any_selection_refuses_and_starts_no_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[Any] = []
        monkeypatch.setattr(workers, "plan_manual", lambda *args, **kwargs: calls.append(kwargs))
        app = _harness()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.query_one(ManualView).action_preview()
            await pilot.pause()
            assert calls == []
            assert app.session_state.run_state is RunUiState.IDLE
            assert app.session_state.feedback is not None
            assert app.session_state.feedback.message == MANUAL_NO_SELECTION

    _run(scenario())


def test_preview_materialises_every_intent_and_calls_plan_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[tuple[int, tuple[Any, ...]]] = []

        def fake(host: Any, service: Any, *, generation: int, intents: Any) -> None:
            calls.append((generation, tuple(intents)))

        monkeypatch.setattr(workers, "plan_manual", fake)
        drafts = {"group-alpha-01": _draft("group-alpha-01"), "group-beta-01": _draft("group-beta-01")}
        app = _harness(_ALPHA, _BETA, drafts=drafts)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            assert not hasattr(view, "start_execution")
            assert not hasattr(view, "action_execute")
            view.action_preview()
            await pilot.pause()
            assert len(calls) == 1
            generation, intents = calls[0]
            assert generation == 1
            assert len(intents) == 2
            assert app.session_state.run_state is RunUiState.PLANNING

    _run(scenario())


def test_registration_applies_when_the_answer_is_current() -> None:
    async def scenario() -> None:
        draft = _draft("group-alpha-01")
        app = _harness(_ALPHA, drafts={"group-alpha-01": draft})
        group = inspected_group(_ALPHA, sidecar="ass")
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            view._pending["group-alpha-01"] = manual_module._Pending(
                generation=app.session_state.generation,
                kind=manual_module._RegistrationKind.SUBTITLE,
                path=Path(f"{_ALPHA}.ass"),
            )
            applied = view._apply_registration(group, app.session_state.generation)
            assert applied is True
            assert draft.selected_subtitle_artifact_id == "artifact-group-alpha-01-source_subtitles"
            assert draft.subtitle_source_policy is SubtitleSourcePolicy.EXTERNAL

    _run(scenario())


def test_a_late_registration_is_dropped_after_the_generation_changed() -> None:
    async def scenario() -> None:
        draft = _draft("group-alpha-01")
        app = _harness(_ALPHA, drafts={"group-alpha-01": draft})
        group = inspected_group(_ALPHA, sidecar="ass")
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            view._pending["group-alpha-01"] = manual_module._Pending(
                generation=0,
                kind=manual_module._RegistrationKind.SUBTITLE,
                path=Path(f"{_ALPHA}.ass"),
            )
            assert lifecycle.begin_planning(app.session_state) == 1
            applied = view._apply_registration(group, 0)
            assert applied is False
            assert draft.selected_subtitle_artifact_id is None

    _run(scenario())


def test_a_late_registration_is_dropped_after_the_group_changed() -> None:
    async def scenario() -> None:
        draft = _draft("group-alpha-01")
        app = _harness(_ALPHA, drafts={"group-alpha-01": draft})
        group = inspected_group(_ALPHA, sidecar="ass")
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            view._pending["group-alpha-01"] = manual_module._Pending(
                generation=0,
                kind=manual_module._RegistrationKind.SUBTITLE,
                path=Path(f"{_ALPHA}.ass"),
            )
            del app.session_state.manual_drafts["group-alpha-01"]
            applied = view._apply_registration(group, 0)
            assert applied is False
            assert draft.selected_subtitle_artifact_id is None

    _run(scenario())


def test_registering_a_subtitle_launches_the_worker_under_the_current_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        calls: list[dict[str, Any]] = []

        def fake(host: Any, service: Any, **kwargs: Any) -> None:
            calls.append({"host": host, **kwargs})

        monkeypatch.setattr(workers, "register_external_subtitle", fake)
        app = _harness(_ALPHA, drafts={"group-alpha-01": _draft("group-alpha-01")})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            view._launch_subtitle("group-alpha-01", Path("outside.ass"))
            assert len(calls) == 1
            assert calls[0]["host"] is view
            assert calls[0]["generation"] == app.session_state.generation
            assert calls[0]["group_id"] == "group-alpha-01"
            assert calls[0]["path"] == Path("outside.ass")
            assert calls[0]["declared_language"] is None
            pending = view._pending["group-alpha-01"]
            assert pending.kind is manual_module._RegistrationKind.SUBTITLE
            assert pending.path == Path("outside.ass")

    _run(scenario())


def test_registering_audio_launches_the_worker_with_the_chosen_role(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[dict[str, Any]] = []

        def fake(host: Any, service: Any, **kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr(workers, "register_external_audio", fake)
        app = _harness(_ALPHA, drafts={"group-alpha-01": _draft("group-alpha-01")})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            view._launch_audio("group-alpha-01", Path("outside.wav"), ExternalAudioRole.NARRATION_MIX)
            assert len(calls) == 1
            assert calls[0]["role"] is ExternalAudioRole.NARRATION_MIX
            assert view._pending["group-alpha-01"].role is ExternalAudioRole.NARRATION_MIX

    _run(scenario())


def test_the_manual_view_owns_its_actions_only_while_on_screen() -> None:
    async def scenario() -> None:
        app = _harness(_ALPHA, _BETA, drafts={})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view = app.query_one(ManualView)
            for name in (PREVIEW_COMMAND_NAME, COPY_COMMAND_NAME, SUBTITLE_COMMAND_NAME, AUDIO_COMMAND_NAME):
                spec = app.commands.command(name)
                assert spec is not None
                assert spec.category is CommandCategory.ACTION
                assert spec.slash_name is None
                assert spec.slash_forms == ()
                assert name not in app.commands.slash_names()
            view.on_hide()
            assert app.commands.command(PREVIEW_COMMAND_NAME) is None

    _run(scenario())


def test_the_preview_key_reaches_the_one_action(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[Any] = []
        monkeypatch.setattr(workers, "plan_manual", lambda *args, **kwargs: calls.append(kwargs))
        app = _harness(_ALPHA, drafts={"group-alpha-01": _draft("group-alpha-01")})
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            action = app.commands.command(PREVIEW_COMMAND_NAME)
            assert action is not None
            assert action.run == app.query_one(ManualView).action_preview
            assert PREVIEW_KEY in action.keys
            assert app.commands.dispatch_key(PREVIEW_KEY) is True
            await pilot.pause()
            assert len(calls) == 1

    _run(scenario())


def test_the_copy_action_needs_two_selected_drafts() -> None:
    single = SessionState()
    single.selected_group_ids = {"group-alpha-01"}
    single.manual_drafts = {"group-alpha-01": _draft("group-alpha-01")}
    assert manual_copy_available(single) is False
    both = _state(
        _ALPHA,
        _BETA,
        drafts={
            "group-alpha-01": _draft("group-alpha-01"),
            "group-beta-01": _draft("group-beta-01"),
        },
    )
    assert manual_copy_available(both) is True
    both.modal_focus_stack.append(None)
    assert manual_copy_available(both) is False


def test_the_preview_action_is_permitted_only_by_a_plannable_session() -> None:
    state = _state(_ALPHA, drafts={"group-alpha-01": _draft("group-alpha-01")})
    for run_state in RunUiState:
        state.run_state = run_state
        assert manual_preview_available(state) is (run_state in {RunUiState.IDLE, RunUiState.TERMINAL})
    state.run_state = RunUiState.IDLE
    assert manual_register_available(state) is True
    state.modal_focus_stack.append(None)
    assert manual_preview_available(state) is False
    assert manual_register_available(state) is False


def test_the_manual_actions_never_grow_the_frozen_slash_catalog() -> None:
    async def scenario() -> None:
        app = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert len(app.commands.slash_names()) == _CATALOG_COMMANDS
            assert PREVIEW_COMMAND_NAME not in app.commands.slash_names()

    _run(scenario())
