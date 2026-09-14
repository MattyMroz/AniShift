from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from anishift.application import (
    AppService,
    AutoPreset,
    ExecutionPlan,
    InspectedSourceGroup,
    PlanPreview,
    PlanTask,
    ProductIntent,
    ProductKind,
    TaskKind,
)
from anishift.application.inspection import WorkspaceInspector
from anishift.application.scheduler_contracts import TaskHandler
from anishift.cli.interactive.manual import ManualController, ManualResult, ManualRun
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.services.media import DefaultMediaProbe


def _controller(tmp_path: Path) -> ManualController:
    for number in range(1, 9):
        (tmp_path / f"{number:02d}.txt").write_text("Original text", encoding="utf-8")
    (tmp_path / "03.pl.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nPolski tekst\n", encoding="utf-8")

    def unused(run_root: Path, plan: ExecutionPlan, source_groups: Mapping[str, InspectedSourceGroup]) -> TaskHandler:
        del run_root, plan, source_groups
        raise AssertionError("A preview cannot execute tasks")

    service: AppService = AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=unused,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=lambda value: None,
    )
    preset: AutoPreset = AutoPreset("manual", "Manual", ProductIntent(frozenset({ProductKind.FULL_PL})))
    return ManualController(service, service.discover(), preset, lambda: None)


def test_manual_previews_and_starts_only_episodes_three_and_eight(tmp_path: Path) -> None:
    controller: ManualController = _controller(tmp_path)
    for key in ("down", "down", "space", *("down",) * 5, "space", "end", "enter"):
        assert controller.handle_key(key) is ManualResult.STAY
    assert controller.take_ready_run() is None
    assert "2 odcinków" in controller.render(120, 40).plain

    assert controller.handle_key("enter") is ManualResult.START_RUN
    run: ManualRun | None = controller.take_ready_run()

    assert run is not None
    selected: set[str] = {group.group_id for group in run.plan.groups}
    assert {group.source.stem for group in run.workspace.groups if group.group_id in selected} == {"03", "08"}
    completed_id: str = next(group.group_id for group in run.workspace.groups if group.source.stem == "03")
    assert not [task for task in run.plan.tasks if task.group_id == completed_id]


def test_manual_regeneration_rebuilds_existing_subtitles_without_deleting_them(tmp_path: Path) -> None:
    controller: ManualController = _controller(tmp_path)
    previous: bytes = (tmp_path / "03.pl.srt").read_bytes()
    for key in ("down", "down", "space", "end", "down", "down", "down", "enter"):
        controller.handle_key(key)

    assert controller.handle_key("enter") is ManualResult.START_RUN
    run: ManualRun | None = controller.take_ready_run()

    assert run is not None
    assert len(run.plan.groups) == 1
    assert TaskKind.TRANSLATE_SUBTITLES in {task.kind for task in run.plan.tasks}
    assert (tmp_path / "03.pl.srt").read_bytes() == previous


def _audiobook_controller(tmp_path: Path) -> ManualController:
    book: Path = tmp_path / "audiobook" / "book.srt"
    book.parent.mkdir(parents=True, exist_ok=True)
    book.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nGood morning\n\n2\n00:05:00,000 --> 00:05:02,000\nGood night\n",
        encoding="utf-8",
    )

    def unused(run_root: Path, plan: ExecutionPlan, source_groups: Mapping[str, InspectedSourceGroup]) -> TaskHandler:
        del run_root, plan, source_groups
        raise AssertionError("A preview cannot execute tasks")

    service: AppService = AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=unused,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=lambda value: None,
    )
    preset: AutoPreset = AutoPreset("manual", "Manual", ProductIntent(frozenset({ProductKind.NARRATION_AUDIO})))
    return ManualController(service, service.discover(), preset, lambda: None)


def _reading(run: ManualRun | None) -> str:
    assert run is not None
    plan: ExecutionPlan | PlanPreview = run.plan
    assert isinstance(plan, ExecutionPlan)
    speech: PlanTask = next(task for task in plan.tasks if task.kind is TaskKind.SYNTHESIZE_SPEECH)
    return str(dict(speech.parameters)["narration_timeline"])


def test_a_manual_audiobook_is_read_one_line_after_another_unless_asked_otherwise(tmp_path: Path) -> None:
    controller: ManualController = _audiobook_controller(tmp_path)
    for key in ("space", "end", "down", "enter", "down", "enter", *("down",) * 4, "enter"):
        assert controller.handle_key(key) is ManualResult.STAY

    assert controller.handle_key("enter") is ManualResult.START_RUN
    assert _reading(controller.take_ready_run()) == "continuous"


def test_a_manual_audiobook_can_be_asked_for_the_times_of_its_own_document(tmp_path: Path) -> None:
    controller: ManualController = _audiobook_controller(tmp_path)
    for key in ("space", "end", "down", "enter", "down", "enter", *("down",) * 3, "enter"):
        assert controller.handle_key(key) is ManualResult.STAY
    screen: str = controller.render(120, 40).plain
    assert "W czasach z dokumentu" in screen
    assert "Jedno po drugim, z krótką pauzą" in screen
    for key in ("down", "enter", *("down",) * 4, "enter"):
        assert controller.handle_key(key) is ManualResult.STAY

    assert controller.handle_key("enter") is ManualResult.START_RUN
    assert _reading(controller.take_ready_run()) == "source_times"


def test_a_film_is_never_offered_a_reading_it_cannot_be_recorded_on(tmp_path: Path) -> None:
    controller: ManualController = _controller(tmp_path)
    for key in ("space", "end", "down", "enter", "down", "enter"):
        assert controller.handle_key(key) is ManualResult.STAY

    assert "Czytanie" not in controller.render(120, 40).plain


def _text_audiobook_controller(tmp_path: Path) -> ManualController:
    book: Path = tmp_path / "audiobook" / "book.txt"
    book.parent.mkdir(parents=True, exist_ok=True)
    book.write_text("Good morning. Good night.\n", encoding="utf-8")

    def unused(run_root: Path, plan: ExecutionPlan, source_groups: Mapping[str, InspectedSourceGroup]) -> TaskHandler:
        del run_root, plan, source_groups
        raise AssertionError("A preview cannot execute tasks")

    service: AppService = AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=unused,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=lambda value: None,
    )
    preset: AutoPreset = AutoPreset("manual", "Manual", ProductIntent(frozenset({ProductKind.NARRATION_AUDIO})))
    return ManualController(service, service.discover(), preset, lambda: None)


def test_a_text_is_never_offered_times_its_translation_would_only_invent(tmp_path: Path) -> None:
    controller: ManualController = _text_audiobook_controller(tmp_path)
    for key in ("space", "end", "down", "enter", "down", "enter"):
        assert controller.handle_key(key) is ManualResult.STAY

    screen: str = controller.render(120, 40).plain

    assert "Czytanie" not in screen
    assert "W czasach z dokumentu" not in screen
