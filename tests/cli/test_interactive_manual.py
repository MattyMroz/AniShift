from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import pytest

from anishift.application import (
    AppService,
    AutoPreset,
    ExecutionPlan,
    InspectedSourceGroup,
    PlanPreview,
    PlanTask,
    ProductIntent,
    ProductKind,
    RefusalReason,
    TaskKind,
)
from anishift.application.inspection import WorkspaceInspector
from anishift.application.intents import (
    AUDIOBOOK_PRODUCTS,
    COVER_PRODUCTS,
    TRANSLATE_PRODUCTS,
    VIDEO_PRODUCTS,
)
from anishift.application.scheduler_contracts import TaskHandler
from anishift.cli.interactive.manual import (
    _PRODUCT_LABELS,
    ManualController,
    ManualResult,
    ManualRun,
    _first_product,
    _Screen,
)
from anishift.cli.interactive.state import refusal_text
from anishift.cli.resident import ResidentSession
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.platform.local_control import ControlError, ControlErrorCode
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


class _RefusingSession(ResidentSession):
    def __init__(self, problem: ControlError) -> None:
        self._problem: ControlError = problem

    def reserve(self, group_ids: Sequence[str]) -> None:
        del group_ids
        raise self._problem


def test_a_refusal_reaching_manual_is_stated_in_polish_like_every_other_screen(tmp_path: Path) -> None:
    controller: ManualController = _controller(tmp_path)
    english: str = "Another client holds one of the requested groups"
    controller._service = _RefusingSession(
        ControlError(
            english,
            code=ControlErrorCode.CONFLICT,
            reason=RefusalReason.GROUP_RESERVED.value,
            answered=True,
        )
    )

    assert controller.handle_key("space") is ManualResult.STAY
    frame: str = controller.render(120, 40).plain

    assert refusal_text(ControlError(english, reason=RefusalReason.GROUP_RESERVED.value)) in frame
    assert english not in frame
    assert "Check whether the resident runs" not in frame


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


def test_a_typed_a_selects_every_episode_for_the_preview(tmp_path: Path) -> None:
    controller: ManualController = _controller(tmp_path)
    for key in ("text:a", "end", "enter"):
        assert controller.handle_key(key) is ManualResult.STAY

    assert "8 odcinków" in controller.render(120, 40).plain


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


def test_every_place_can_name_the_first_product_it_offers() -> None:
    offered: tuple[frozenset[ProductKind], ...] = (
        TRANSLATE_PRODUCTS,
        AUDIOBOOK_PRODUCTS,
        COVER_PRODUCTS,
        VIDEO_PRODUCTS,
    )
    named: frozenset[ProductKind] = frozenset(product for product, _label in _PRODUCT_LABELS)

    for allowed in offered:
        assert _first_product(allowed) <= allowed
        assert _first_product(allowed) <= named


_CUSTOM: Final[tuple[str, ...]] = ("space", "end", "down", "enter", "down", "enter")

_ROUTES: Final[dict[_Screen, tuple[str, ...]]] = {
    _Screen.GROUPS: (),
    _Screen.PREVIEW: ("space", "end", "enter"),
    _Screen.GROUP_ACTION: _CUSTOM[:4],
    _Screen.CUSTOM: _CUSTOM,
    _Screen.PRODUCTS: (*_CUSTOM, "enter"),
    _Screen.SUBTITLES: (*_CUSTOM, "down", "enter"),
    _Screen.AUDIO: (*_CUSTOM, "down", "down", "enter"),
    _Screen.TIMELINE: (*_CUSTOM, "down", "down", "down", "enter"),
    _Screen.INPUT: (*_CUSTOM, "down", "enter", "down", "enter"),
    _Screen.BUSY: _CUSTOM,
}


def _manual_at(tmp_path: Path, screen: _Screen) -> ManualController:
    tmp_path.mkdir()
    controller: ManualController = (_audiobook_controller if screen is _Screen.TIMELINE else _controller)(tmp_path)
    for key in _ROUTES[screen]:
        controller.handle_key(key)
    if screen is _Screen.BUSY:
        controller._screen = _Screen.BUSY
    assert controller._screen is screen
    return controller


@pytest.mark.parametrize("screen", sorted(set(_ROUTES) - {_Screen.INPUT}))
def test_backspace_goes_back_like_escape_on_every_manual_screen_without_a_field(
    tmp_path: Path, screen: _Screen
) -> None:
    outcomes: list[tuple[object, ...]] = []
    for key in ("escape", "backspace"):
        controller: ManualController = _manual_at(tmp_path / key, screen)
        result: ManualResult = controller.handle_key(key)
        outcomes.append((result, controller._screen, controller._selected, controller._edit_index))
    assert outcomes[0] == outcomes[1]
    assert outcomes[1][0] is ManualResult.BACK_HOME or outcomes[1][1] is not screen


def test_backspace_edits_the_external_file_path(tmp_path: Path) -> None:
    controller: ManualController = _manual_at(tmp_path / "manual", _Screen.INPUT)
    for key in ("text:ab", "backspace"):
        assert controller.handle_key(key) is ManualResult.STAY
    assert controller._screen is _Screen.INPUT
    assert controller._input.text == "a"
