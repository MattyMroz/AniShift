from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from io import StringIO
from pathlib import Path
from typing import cast

import pytest
import questionary
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import anishift.cli.interactive.home as home_module
import anishift.cli.interactive.prompts as prompts_module
from anishift.cli.interactive.home import HomeAction, ask_home_action
from anishift.cli.interactive.mascot import mascot_art
from anishift.cli.interactive.prompts import HomeGeometry, PromptChoice, home_footer, resolve_home_geometry


class _Prompts:
    def __init__(self, *, columns: int = 80, rows: int = 24, selected: HomeAction = HomeAction.AUTO) -> None:
        self.columns: int = columns
        self.rows: int = rows
        self.selected: HomeAction = selected
        self.choices: tuple[PromptChoice, ...] = ()
        self.default: str | None = None
        self.footer: str | None = None
        self.geometry: HomeGeometry | None = None
        self.interrupt: bool = False
        self.resize_once: bool = False
        self.select_calls: int = 0
        self.clears: int = 0

    def screen(self) -> AbstractContextManager[None]:
        return nullcontext()

    def clear_screen(self) -> None:
        self.clears += 1

    def terminal_columns(self) -> int:
        return self.columns

    def terminal_rows(self) -> int:
        return self.rows

    def select(
        self,
        choices: Sequence[PromptChoice],
        *,
        default: str | None,
        footer: str,
        geometry: HomeGeometry,
    ) -> str:
        self.select_calls += 1
        if self.interrupt:
            raise KeyboardInterrupt
        if self.resize_once:
            self.resize_once = False
            self.columns = 100
            self.rows = 30
            raise prompts_module._TerminalResizedError
        self.choices = tuple(choices)
        self.default = default
        self.footer = footer
        self.geometry = geometry
        return self.selected

    def pause(self, message: str) -> None:
        del message


class _RecordingOutput(DummyOutput):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enter_alternate_screen(self) -> None:
        self.calls.append("enter")

    def erase_screen(self) -> None:
        self.calls.append("erase")

    def show_cursor(self) -> None:
        self.calls.append("show_cursor")

    def quit_alternate_screen(self) -> None:
        self.calls.append("quit")

    def flush(self) -> None:
        self.calls.append("flush")


def _render_home(monkeypatch: pytest.MonkeyPatch, prompts: _Prompts) -> str:
    stream = StringIO()
    test_console = Console(file=stream, width=prompts.columns, color_system=None)
    monkeypatch.setattr(home_module, "console", test_console)
    ask_home_action(prompts, version="0.1.0")
    return stream.getvalue()


def test_home_has_four_choices_in_the_required_order(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _Prompts()

    _render_home(monkeypatch, prompts)

    assert [choice.title for choice in prompts.choices] == ["Auto", "Ręczny", "Ustawienia", "Wyjście"]


def test_home_starts_on_auto_without_persisting_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _Prompts()

    _render_home(monkeypatch, prompts)

    assert prompts.choices[0].value == HomeAction.AUTO
    assert prompts.default is None


@pytest.mark.parametrize("action", list(HomeAction))
def test_home_values_map_to_actions(monkeypatch: pytest.MonkeyPatch, action: HomeAction) -> None:
    prompts = _Prompts(selected=action)

    selected = ask_home_action(prompts, version="0.1.0")

    assert selected is action


def test_wide_footer_places_hint_and_status_at_the_edges() -> None:
    geometry = resolve_home_geometry(80)

    footer = home_footer("0.1.0", r"~\Desktop\PROJECTS\AniShift", geometry)
    lines = footer.splitlines()

    assert lines[0] == "↑↓ · Enter"
    assert lines[-1].startswith(r"~\Desktop\PROJECTS\AniShift")
    assert lines[-1].endswith("v0.1.0")
    assert len(lines[-1]) == geometry.terminal_columns - 1


def test_narrow_footer_truncates_the_directory_from_the_left() -> None:
    geometry = resolve_home_geometry(20, 12)

    footer = home_footer("0.1.0", r"~\Desktop\PROJECTS\AniShift", geometry)
    status: str = footer.splitlines()[-1]

    assert status.startswith("…")
    assert status.endswith("v0.1.0")
    assert len(status) == geometry.terminal_columns - 1


def test_tiny_footer_never_exceeds_the_terminal_width() -> None:
    geometry = resolve_home_geometry(5, 8)

    footer = home_footer("0.1.0", r"~\Desktop\PROJECTS\AniShift", geometry)
    status: str = footer.splitlines()[-1]

    assert status == "…1.0"
    assert len(status) == geometry.terminal_columns - 1


def test_home_uses_the_slime_palette_wordmark_without_a_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = _Prompts()

    output = _render_home(monkeypatch, prompts)
    brand = home_module._home_brand(None, show_full_wordmark=True)

    assert "█████" in output
    assert tuple(brand.plain.splitlines()) == home_module._LOGO_ROWS
    assert home_module._LOGO_FILL_PALETTE[0] in repr(brand)
    assert home_module._LOGO_OUTLINE_PALETTE[0] in repr(brand)
    assert not {"+", "|"} & set(brand.plain)


def test_home_does_not_show_configuration_details(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _render_home(monkeypatch, _Prompts())

    assert not {"model", "voice", "workspace", "preset"} & set(output.lower().split())


def test_wide_home_renders_the_packaged_mascot(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _Prompts()

    output = _render_home(monkeypatch, prompts)

    assert "▀" in output or "▄" in output
    assert cast("HomeGeometry", prompts.geometry).show_mascot


def test_small_home_hides_the_mascot(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _Prompts(columns=24, rows=12)

    output = _render_home(monkeypatch, prompts)

    assert "ANISHIFT" in output
    assert not cast("HomeGeometry", prompts.geometry).show_mascot
    assert not cast("HomeGeometry", prompts.geometry).show_full_wordmark
    assert len(home_module._home_brand(None, show_full_wordmark=False).plain) <= prompts.columns


def test_home_menu_block_is_centered() -> None:
    geometry = resolve_home_geometry(100)

    assert geometry.content_width == len("Ustawienia") + 3
    assert geometry.left_padding == (geometry.terminal_columns - geometry.content_width) // 2


def test_home_content_is_vertically_centered_above_the_bottom_status() -> None:
    geometry = resolve_home_geometry(80, 24)

    assert geometry.top_padding == 1
    assert geometry.footer_padding == 3


def test_mascot_keeps_one_size_across_supported_terminal_sizes() -> None:
    regular = resolve_home_geometry(80, 24)
    large = resolve_home_geometry(120, 32)

    assert large.mascot_columns == regular.mascot_columns == 20
    assert large.mascot_rows == regular.mascot_rows == 14


def test_full_brand_has_a_stable_width_and_combined_center() -> None:
    geometry = resolve_home_geometry(80, 24)
    mascot = mascot_art(geometry.mascot_columns, geometry.mascot_rows)

    brand = home_module._home_brand(mascot, show_full_wordmark=geometry.show_full_wordmark)

    assert mascot is not None
    assert {line.cell_len for line in brand.split("\n")} == {79}
    assert {line.cell_len for line in home_module._centered_brand(brand, 80).split("\n")} == {79}
    assert geometry.show_mascot
    assert geometry.show_full_wordmark


def test_active_styles_use_blue_text_without_a_background() -> None:
    assert prompts_module._QUESTIONARY_STYLE.get_attrs_for_style_str("class:highlighted").color == "5c9cf5"
    assert prompts_module._QUESTIONARY_STYLE.get_attrs_for_style_str("class:highlighted").bgcolor == ""
    assert not prompts_module._QUESTIONARY_STYLE.get_attrs_for_style_str("class:highlighted").reverse
    assert prompts_module._QUESTIONARY_STYLE.get_attrs_for_style_str("class:selected").color == "5c9cf5"
    assert prompts_module._QUESTIONARY_STYLE.get_attrs_for_style_str("class:selected").bgcolor == ""
    assert not prompts_module._QUESTIONARY_STYLE.get_attrs_for_style_str("class:selected").reverse


def test_menu_labels_have_no_embedded_padding(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _Prompts()

    _render_home(monkeypatch, prompts)

    assert all(choice.title == choice.title.lstrip() for choice in prompts.choices)


def test_home_marker_is_inset_from_the_terminal_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _Prompts(columns=80)

    _render_home(monkeypatch, prompts)

    assert cast("HomeGeometry", prompts.geometry).left_padding > 0


def test_keyboard_interrupt_propagates_from_home() -> None:
    prompts = _Prompts()
    prompts.interrupt = True

    with pytest.raises(KeyboardInterrupt):
        ask_home_action(prompts, version="0.1.0")


def test_home_recalculates_its_center_after_a_terminal_resize(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _Prompts()
    prompts.resize_once = True

    _render_home(monkeypatch, prompts)

    assert prompts.select_calls == 2
    assert cast("HomeGeometry", prompts.geometry).terminal_columns == 100


def test_questionary_requests_a_clean_rerender_when_terminal_size_changes() -> None:
    dimensions: dict[str, int] = {"columns": 80, "rows": 24}

    class _RenderEvent:
        def __init__(self) -> None:
            self.callback: Callable[[object], None] | None = None

        def __iadd__(self, callback: Callable[[object], None]) -> _RenderEvent:
            self.callback = callback
            return self

    class _Application:
        def __init__(self) -> None:
            self.after_render: _RenderEvent = _RenderEvent()

        def exit(
            self,
            result: object | None = None,
            exception: BaseException | type[BaseException] | None = None,
            style: str = "",
        ) -> None:
            assert isinstance(exception, BaseException)
            raise exception

    class _Question:
        def __init__(self) -> None:
            self.application: _Application = _Application()

    question = _Question()
    prompts_module._register_resize_rerender(
        cast("questionary.Question", question),
        initial_size=(80, 24),
        size_provider=lambda: (dimensions["columns"], dimensions["rows"]),
    )
    dimensions["columns"] = 100
    callback: Callable[[object], None] | None = question.application.after_render.callback

    assert callback is not None
    with pytest.raises(prompts_module._TerminalResizedError):
        callback(question.application)


def test_questionary_terminal_screen_uses_one_native_output_lifecycle() -> None:
    output: _RecordingOutput = _RecordingOutput()
    prompts: prompts_module.QuestionaryPrompts = prompts_module.QuestionaryPrompts(output=output)

    with prompts.screen():
        prompts.clear_screen()

    assert output.calls == [
        "enter",
        "erase",
        "flush",
        "erase",
        "flush",
        "erase",
        "show_cursor",
        "quit",
        "flush",
    ]


def test_questionary_erases_the_selected_answer_before_auto_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output: _RecordingOutput = _RecordingOutput()
    captured: dict[str, object] = {}
    original_select = questionary.select
    forward_select: Callable[..., questionary.Question] = cast(
        "Callable[..., questionary.Question]",
        original_select,
    )

    def capture_select(*args: object, **kwargs: object) -> questionary.Question:
        captured.update(kwargs)
        return forward_select(*args, **kwargs)

    monkeypatch.setattr(questionary, "select", capture_select)
    monkeypatch.setattr(questionary.Question, "unsafe_ask", lambda self: HomeAction.AUTO.value)
    prompts: prompts_module.QuestionaryPrompts = prompts_module.QuestionaryPrompts(output=output)
    geometry: HomeGeometry = resolve_home_geometry(80, 24)

    selected: str = prompts.select(
        (PromptChoice("Auto", HomeAction.AUTO),),
        default=None,
        footer="footer",
        geometry=geometry,
    )

    assert selected == HomeAction.AUTO
    assert captured["erase_when_done"] is True
    assert captured["output"] is output


def test_working_directory_is_home_relative() -> None:
    label = home_module._working_directory_label(
        Path("/users/tester/Desktop/AniShift"),
        Path("/users/tester"),
    )

    assert label == r"~\Desktop\AniShift"


def test_mascot_asset_renders_to_the_requested_terminal_size() -> None:
    mascot = mascot_art(20, 8)

    assert mascot is not None
    assert len(mascot.split("\n")) == 8
    assert mascot.cell_len > 0
