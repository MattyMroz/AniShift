from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from anishift.application import (
    AppService,
    AutoPreset,
    ExecutionPlan,
    InspectedSourceGroup,
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
