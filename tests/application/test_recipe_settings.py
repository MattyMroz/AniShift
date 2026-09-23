from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import FakeMediaProbe, write_image_source, write_media_source
from test_service import _panel_owner

import anishift.config.user_settings as preferences_module
from anishift.application import AppService, AutoPreset, PlanPreview
from anishift.application.cancellation import CancellationToken
from anishift.application.control import AutomationPolicy, ProcessingRequest, RecipePreferences, WatchState
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import (
    NarrationTimeline,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.planning import ExecutionPlan, PlanTask
from anishift.application.recovery import RunJournal
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.scheduler_contracts import TaskHandler, TaskProgressSink
from anishift.application.watch_state import WatchStateStore
from anishift.cli.interactive.settings import SettingsController
from anishift.config.presets import AutoPresetFile, default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, save_user_settings
from anishift.errors import ExecutionError
from anishift.platform.local_control import ControlError


class _HeldBoundary:
    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self.entered: threading.Event = entered
        self.release: threading.Event = release

    def execute(
        self, task: PlanTask, artifacts: ArtifactSnapshot, cancel: CancellationToken, progress: TaskProgressSink
    ) -> TaskResult:
        del task, artifacts, cancel, progress
        self.entered.set()
        assert self.release.wait(5)
        raise ExecutionError("Isolated execution boundary")


def _service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entered: threading.Event, release: threading.Event
) -> AppService:
    monkeypatch.setattr(preferences_module, "config_path", lambda: tmp_path / ".settings.json")
    settings: UserSettings = UserSettings(tts_engine="edge", tts_voice_id="pl-PL-MarekNeural")
    save_user_settings(settings)
    presets: list[AutoPresetFile] = [default_preset_file()]

    def handlers(run_root: Path, plan: ExecutionPlan, source_groups: Mapping[str, InspectedSourceGroup]) -> TaskHandler:
        del run_root, plan, source_groups
        return _HeldBoundary(entered, release)

    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=settings,
        inspector=WorkspaceInspector(FakeMediaProbe()),
        handler_factory=handlers,
        preset_loader=lambda: presets[0],
        preset_saver=lambda value: presets.__setitem__(0, value),
        env_file=tmp_path / ".env",
    )


def _activate(panel: SettingsController, key: str) -> None:
    panel._selected = next(index for index, item in enumerate(panel._items) if item.key == key)
    panel.handle_key("enter")


def test_recipe_editors_use_owner_persistence_and_confirm_only_the_selected_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service: AppService = _service(tmp_path, monkeypatch, threading.Event(), threading.Event())
    preferences: bytes = (tmp_path / ".settings.json").read_bytes()
    preset: AutoPreset = service.get_preset(service.default_preset_id())
    original: WatchState = WatchState(policy=AutomationPolicy(auto_enabled=False))
    WatchStateStore(tmp_path / ".control" / "state.json").save(original)
    with _panel_owner(service, tmp_path) as (session, store):
        panel: SettingsController = SettingsController(service, lambda: None, resident=session)
        _activate(panel, "category:auto")
        assert [item.label for item in panel._items[:3]] == ["Wideo", "Tłumaczenie", "Audiobook"]
        assert "Start" not in panel.render(80, 24).plain
        _activate(panel, "recipe:audiobook")
        assert "cover:" in panel.render(80, 24).plain
        assert all("voice" not in item.key and "model" not in item.key for item in panel._items)
        _activate(panel, "setting:audiobook.timeline")
        panel.handle_key("down")
        assert session.recipes() == RecipePreferences()
        panel.handle_key("enter")
        assert session.recipes().audiobook.timeline is NarrationTimeline.SOURCE_TIMES
        session.update_recipe("translate.text_result", "subtitles")
        _activate(panel, "reset-scope:recipe:audiobook")
        panel.handle_key("enter")
        assert session.recipes().audiobook.timeline is NarrationTimeline.SOURCE_TIMES
        _activate(panel, "reset-scope:recipe:audiobook")
        panel.handle_key("down")
        panel.handle_key("enter")
        assert session.recipes().audiobook == RecipePreferences().audiobook
        assert session.recipes().translate.text_result.value == "subtitles"
        assert store.load().policy == original.policy
        assert (tmp_path / ".settings.json").read_bytes() == preferences
        assert service.get_preset(service.default_preset_id()) == preset
        panel._selected = 0
        panel.handle_key("right")
        assert session.recipes().audiobook.translation_action is TranslationAction.AUTO
        panel.close()
        assert session.recipes().audiobook.translation_action is TranslationAction.TRANSLATE
        fresh: SettingsController = SettingsController(service, lambda: None, resident=session)
        _activate(fresh, "category:auto")
        _activate(fresh, "recipe:audiobook")
        assert "Zawsze tłumacz" in fresh.render(80, 24).plain
        before: WatchState = store.load()
        with pytest.raises(ControlError):
            session.update_recipe("tts_voice_id", "anything")
        assert store.load() == before
    service.close()


@pytest.mark.parametrize("target", ["audiobook", "cover"])
def test_accepted_video_and_audio_keep_their_settings_while_new_orders_receive_shared_voice_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    service: AppService = _service(tmp_path, monkeypatch, entered, release)
    write_media_source(tmp_path / "Video.mkv")
    directory: Path = tmp_path / target
    directory.mkdir()
    for name in ("Before", "After"):
        (directory / f"{name}.srt").write_text("1\n00:01:00,000 --> 00:01:01,000\nHello\n", encoding="utf-8")
        if target == "cover":
            write_image_source(directory / f"{name}.png")
    with _panel_owner(service, tmp_path) as (session, store):
        try:
            groups: dict[str, str] = {group.source.stem: group.group_id for group in session.discover().groups}
            preset: AutoPreset = service.get_preset(service.default_preset_id())
            video: PlanPreview = session.plan_auto((groups["Video"],), preset)
            assert video.can_execute
            session.command("start", {"preview_id": video.preview_id})
            assert entered.wait(5)
            before: PlanPreview = session.plan_auto((groups["Before"],), preset)
            assert before.can_execute
            session.command("start", {"preview_id": before.preview_id})
            session.update_recipe("audiobook.timeline", "source_times")
            panel: SettingsController = SettingsController(service, lambda: None, resident=session)
            _activate(panel, "category:tts")
            _activate(panel, "setting:tts_voice_id")
            assert panel._editor is not None
            panel._editor.selected = next(
                index for index, option in enumerate(panel._editor.options) if option.value == "pl-PL-ZofiaNeural"
            )
            panel.handle_key("enter")
            assert panel._feedback is None
            after: PlanPreview = session.plan_auto((groups["After"],), preset)
            assert after.can_execute
            session.command("start", {"preview_id": after.preview_id})
            requests: dict[str, ProcessingRequest] = {item.group_ids[0]: item for item in store.load().requests}
            assert len(requests) == 3
            assert requests[groups["Video"]].settings["tts_voice_id"] == "pl-PL-MarekNeural"
            assert requests[groups["Before"]].settings["tts_voice_id"] == "pl-PL-MarekNeural"
            assert requests[groups["After"]].settings["tts_voice_id"] == "pl-PL-ZofiaNeural"
            assert requests[groups["Before"]].intents[0].narration_timeline is NarrationTimeline.CONTINUOUS
            assert requests[groups["After"]].intents[0].narration_timeline is NarrationTimeline.SOURCE_TIMES
            expected: ProductKind = ProductKind.COVER_MP4 if target == "cover" else ProductKind.NARRATION_AUDIO
            assert requests[groups["After"]].intents[0].products.requested_products == frozenset({expected})
            for request in requests.values():
                plan: ExecutionPlan = RunJournal.load(store.run_path(request.request_id)).plan
                assert plan.settings.tts_voice_id == request.settings["tts_voice_id"]
            assert not release.is_set()
        finally:
            release.set()
    service.close()


def test_recipe_inheritance_and_manual_overrides_do_not_copy_video_policy_into_other_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service: AppService = _service(tmp_path, monkeypatch, threading.Event(), threading.Event())
    for target in ("subs", "translate", "audiobook"):
        directory: Path = tmp_path / target
        directory.mkdir()
        (directory / f"{target}.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    write_media_source(tmp_path / "subs" / "subs.mkv")
    with _panel_owner(service, tmp_path) as (session, _store):
        groups: dict[str, str] = {group.source.stem: group.group_id for group in session.discover().groups}
        preset: AutoPreset = replace(
            service.get_preset(service.default_preset_id()),
            subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
            subtitle_output_format=SubtitleOutputFormat.ASS,
            source_subtitle_language="pol",
        )
        paired: PlanPreview = session.plan_auto((groups["subs"],), preset)
        assert paired.can_execute
        assert paired.groups[0].intent.subtitle_source_policy is SubtitleSourcePolicy.SIDECAR
        translated: PlanPreview = session.plan_auto((groups["translate"],), preset)
        assert translated.can_execute
        assert translated.groups[0].intent.subtitle_output_format is SubtitleOutputFormat.PRESERVE
        assert translated.groups[0].intent.source_subtitle_language is None
        session.update_recipe("audiobook.timeline", "source_times")
        automatic: PlanPreview = session.plan_auto((groups["audiobook"],), preset)
        manual: PlanPreview = session.plan_manual(
            (
                replace(
                    automatic.groups[0].intent,
                    mode=RunMode.MANUAL,
                    narration_timeline=NarrationTimeline.CONTINUOUS,
                    translation_action=TranslationAction.DO_NOT_TRANSLATE,
                ),
            )
        )
        assert manual.can_execute
        assert manual.groups[0].intent.narration_timeline is NarrationTimeline.CONTINUOUS
        assert session.recipes().audiobook.timeline is NarrationTimeline.SOURCE_TIMES
        assert service.get_preset(service.default_preset_id()) != preset
    service.close()


def test_recipe_changed_after_preview_does_not_relabel_the_accepted_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release: threading.Event = threading.Event()
    service: AppService = _service(tmp_path, monkeypatch, threading.Event(), release)
    directory: Path = tmp_path / "translate"
    directory.mkdir()
    (directory / "Text.txt").write_text("Hello", encoding="utf-8")
    with _panel_owner(service, tmp_path) as (session, store):
        try:
            group_id: str = session.discover().groups[0].group_id
            preset: AutoPreset = service.get_preset(service.default_preset_id())
            preview: PlanPreview = session.plan_auto((group_id,), preset)
            session.update_recipe("translate.text_result", "subtitles")
            session.command("start", {"preview_id": preview.preview_id})
            accepted: ProcessingRequest = store.load().requests[0]
            assert accepted.recipe == RecipePreferences()
            assert accepted.intents[0].products.requested_products == frozenset({ProductKind.TRANSLATED_TEXT})
            assert store.load().recipes != accepted.recipe
        finally:
            release.set()
    service.close()
