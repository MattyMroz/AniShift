from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import cast

import pytest
import questionary
from prompt_toolkit.output import DummyOutput

import anishift.cli.interactive.home as home_module
import anishift.cli.interactive.prompts as prompts_module
from anishift.cli.interactive.home import HomeAction, ask_home_action
from anishift.cli.interactive.mascot import mascot_art
from anishift.cli.interactive.prompts import (
    HomeGeometry,
    PromptChoice,
    QuestionaryPrompts,
    _TerminalResizedError,
    home_footer,
    resolve_auto_geometry,
    resolve_home_geometry,
    status_line,
)


class _Prompts:
    def __init__(self, *, columns: int = 80, rows: int = 24, selected: HomeAction = HomeAction.AUTO) -> None:
        self.columns: int = columns
        self.rows: int = rows
        self.selected: HomeAction = selected
        self.choices: tuple[PromptChoice, ...] = ()
        self.default: str | None = None
        self.footer: str | None = None
        self.geometry: HomeGeometry | None = None
        self.resize_once: bool = False
        self.select_calls: int = 0
        self.clears: int = 0
        self.rendered_footers: list[tuple[str, str]] = []
        self.cursor_positions: list[tuple[int, int]] = []
        self.resize_callbacks: list[Callable[[], None]] = []

    def screen(self) -> AbstractContextManager[None]:
        return nullcontext()

    def clear_screen(self) -> None:
        self.clears += 1

    def terminal_columns(self) -> int:
        return self.columns

    def terminal_rows(self) -> int:
        return self.rows

    def render_footer(self, version: str, directory: str) -> None:
        self.rendered_footers.append((version, directory))

    def position_cursor(self, row: int, column: int = 0) -> None:
        self.cursor_positions.append((row, column))

    def watch_resize(self, callback: Callable[[], None]) -> AbstractContextManager[None]:
        self.resize_callbacks.append(callback)
        return nullcontext()

    def select(
        self,
        choices: Sequence[PromptChoice],
        *,
        default: str | None,
        footer: str,
        geometry: HomeGeometry,
    ) -> str:
        self.select_calls += 1
        if self.resize_once:
            self.resize_once = False
            self.columns = 100
            self.rows = 30
            raise _TerminalResizedError
        self.choices = tuple(choices)
        self.default = default
        self.footer = footer
        self.geometry = geometry
        return self.selected

    def pause(self, message: str) -> None:
        del message

    def wait_for_key(self) -> None:
        pass


class _RecordingOutput(DummyOutput):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enter_alternate_screen(self) -> None:
        self.calls.append("enter")

    def erase_screen(self) -> None:
        self.calls.append("erase")

    def erase_end_of_line(self) -> None:
        self.calls.append("erase_line")

    def show_cursor(self) -> None:
        self.calls.append("show_cursor")

    def quit_alternate_screen(self) -> None:
        self.calls.append("quit")

    def flush(self) -> None:
        self.calls.append("flush")

    def cursor_goto(self, row: int = 0, column: int = 0) -> None:
        self.calls.append(f"cursor:{row}:{column}")

    def write(self, data: str) -> None:
        self.calls.append(f"write:{data}")


def test_home_has_four_choices_in_required_order() -> None:
    prompts: _Prompts = _Prompts()

    ask_home_action(prompts, version="0.1.0")

    assert [choice.title for choice in prompts.choices] == ["Auto", "Ręczny", "Ustawienia", "Wyjście"]
    assert prompts.default is None


@pytest.mark.parametrize("action", list(HomeAction))
def test_home_values_map_to_actions(action: HomeAction) -> None:
    prompts: _Prompts = _Prompts(selected=action)

    selected: HomeAction = ask_home_action(prompts, version="0.1.0")

    assert selected is action


def test_home_footer_keeps_directory_and_version_at_edges() -> None:
    geometry: HomeGeometry = resolve_home_geometry(80)

    footer: str = home_footer("0.1.0", r"~\Desktop\PROJECTS\AniShift", geometry)
    lines: list[str] = footer.splitlines()

    assert lines[0] == "↑↓ · Enter"
    assert lines[-1].startswith(r"~\Desktop\PROJECTS\AniShift")
    assert lines[-1].endswith("v0.1.0")
    assert len(lines[-1]) == geometry.terminal_columns - 1


def test_narrow_footer_truncates_directory_before_version() -> None:
    status: str = status_line("0.1.0", r"~\Desktop\PROJECTS\AniShift", 20)

    assert status.startswith("…")
    assert status.endswith("v0.1.0")
    assert len(status) == 19


def test_home_resize_triggers_one_clean_rerender() -> None:
    prompts: _Prompts = _Prompts(columns=80, rows=24)
    prompts.resize_once = True

    ask_home_action(prompts, version="0.1.0")

    assert prompts.select_calls == 2
    assert prompts.clears == 2
    assert prompts.geometry == resolve_home_geometry(100, 30)


def test_resize_watcher_coalesces_rapid_dimension_changes() -> None:
    size: list[tuple[int, int]] = [(80, 24)]
    rendered: threading.Event = threading.Event()
    callbacks: list[tuple[int, int]] = []

    def redraw() -> None:
        callbacks.append(size[0])
        rendered.set()

    with prompts_module._ResizeWatcher(lambda: size[0], redraw, initial_size=size[0]):
        size[0] = (90, 26)
        time.sleep(0.005)
        size[0] = (100, 30)
        assert rendered.wait(timeout=1.0)
        time.sleep(0.05)

    assert callbacks == [(100, 30)]


def test_home_resize_exits_the_active_prompt_only_once() -> None:
    size: list[tuple[int, int]] = [(80, 24)]
    exited: threading.Event = threading.Event()

    class _Hooks:
        def __init__(self) -> None:
            self.callbacks: list[Callable[[object], None]] = []

        def __iadd__(self, callback: Callable[[object], None]) -> _Hooks:
            self.callbacks.append(callback)
            return self

    class _Application:
        def __init__(self) -> None:
            self.after_render: _Hooks = _Hooks()
            self.is_done: bool = False
            self.exits: int = 0

        def invalidate(self) -> None:
            for callback in self.after_render.callbacks:
                callback(self)
                callback(self)

        def exit(
            self,
            result: object | None = None,
            exception: BaseException | type[BaseException] | None = None,
            style: str = "",
        ) -> None:
            del result, exception, style
            self.exits += 1
            self.is_done = True
            exited.set()

    class _Question:
        def __init__(self) -> None:
            self.application: _Application = _Application()

    question: _Question = _Question()
    with prompts_module._register_resize_rerender(
        cast("questionary.Question", question),
        initial_size=size[0],
        size_provider=lambda: size[0],
    ):
        size[0] = (100, 30)
        assert exited.wait(timeout=1.0)

    assert question.application.exits == 1


def test_home_geometry_preserves_fixed_brand_and_compact_fallback() -> None:
    wide: HomeGeometry = resolve_home_geometry(120, 30)
    medium: HomeGeometry = resolve_home_geometry(60, 16)
    narrow: HomeGeometry = resolve_home_geometry(50, 12)

    assert (wide.mascot_columns, wide.mascot_rows) == (18, 10)
    assert wide.show_mascot is True
    assert wide.show_full_wordmark is True
    assert medium.show_mascot is False
    assert medium.show_full_wordmark is True
    assert narrow.show_mascot is False
    assert narrow.show_full_wordmark is False


def test_auto_geometry_reserves_progress_and_footer_below_brand() -> None:
    geometry = resolve_auto_geometry(120, 32, 4)

    assert geometry.show_mascot is True
    assert geometry.show_full_wordmark is True
    assert geometry.progress_row > geometry.top_padding
    assert geometry.progress_row + 4 <= geometry.terminal_rows - 1


def test_questionary_select_uses_plain_pointer_without_selected_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Hooks:
        def __iadd__(self, callback: object) -> _Hooks:
            captured["resize_callback"] = callback
            return self

    class _Application:
        def __init__(self) -> None:
            self.after_render: _Hooks = _Hooks()

    class _Question:
        def __init__(self) -> None:
            self.application: _Application = _Application()

        def unsafe_ask(self) -> str:
            return HomeAction.AUTO

    def fake_select(message: str, **kwargs: object) -> _Question:
        captured["message"] = message
        captured.update(kwargs)
        return _Question()

    monkeypatch.setattr(questionary, "select", fake_select)
    geometry: HomeGeometry = resolve_home_geometry(80, 24)
    prompts: QuestionaryPrompts = QuestionaryPrompts(
        width_provider=lambda: 80,
        height_provider=lambda: 24,
        output=DummyOutput(),
    )

    selected: str = prompts.select(
        (PromptChoice("Auto", HomeAction.AUTO),),
        default=None,
        footer=home_footer("0.1.0", "AniShift", geometry),
        geometry=geometry,
    )

    assert selected == HomeAction.AUTO
    assert captured["pointer"] == f"{' ' * geometry.left_padding}❯"  # noqa: RUF001
    style: questionary.Style = cast("questionary.Style", captured["style"])
    assert ("highlighted", "noinherit fg:#a855f7 bold noreverse") in style.style_rules
    assert captured["show_selected"] is False
    assert captured["use_indicator"] is False
    assert captured["erase_when_done"] is True


def test_footer_renderer_targets_last_safe_row() -> None:
    output: _RecordingOutput = _RecordingOutput()
    prompts: QuestionaryPrompts = QuestionaryPrompts(
        width_provider=lambda: 40,
        height_provider=lambda: 12,
        output=output,
    )

    prompts.render_footer("0.1.0", r"~\AniShift")

    assert "cursor:11:0" in output.calls
    assert any(call.startswith(r"write:~\AniShift") and call.endswith("v0.1.0") for call in output.calls)
    assert output.calls[-2:] == ["cursor:0:0", "flush"]


def test_terminal_screen_restores_cursor_and_buffer() -> None:
    output: _RecordingOutput = _RecordingOutput()
    prompts: QuestionaryPrompts = QuestionaryPrompts(output=output)

    with prompts.screen():
        pass

    assert output.calls[0:3] == ["enter", "erase", "flush"]
    assert output.calls[-4:] == ["erase", "show_cursor", "quit", "flush"]


def test_working_directory_is_home_relative() -> None:
    label: str = home_module.working_directory_label(
        Path("/users/tester/Desktop/AniShift"),
        Path("/users/tester"),
    )

    assert label == r"~\Desktop\AniShift"


def test_mascot_asset_renders_to_requested_terminal_size() -> None:
    mascot = mascot_art(20, 8)

    assert mascot is not None
    assert len(mascot.split("\n")) == 8
    assert mascot.cell_len > 0
