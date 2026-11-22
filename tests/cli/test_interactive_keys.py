from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Final, cast

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.input import DummyInput, create_pipe_input
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput
from rich.text import Text

from anishift.cli.interactive.prompts import TerminalRenderer, _ctrl_backspace_data

if sys.platform == "win32":
    from prompt_toolkit.input.win32 import ConsoleInputReader, Vt100ConsoleInputReader, Win32Input

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent

_DEFAULT_KEY_PREFIX_S: Final[float] = 1.0

_HANG_GUARD_S: Final[float] = 30.0

_EXPECTED_KEYS = [
    (Keys.Up, "up"),
    (Keys.Down, "down"),
    (Keys.Left, "left"),
    (Keys.Right, "right"),
    (Keys.PageUp, "pageup"),
    (Keys.PageDown, "pagedown"),
    (Keys.Home, "home"),
    (Keys.End, "end"),
    (Keys.Enter, "enter"),
    (Keys.Delete, "delete"),
    (Keys.Tab, "tab"),
    (Keys.BackTab, "backtab"),
    (Keys.Escape, "escape"),
    (Keys.ControlC, "interrupt"),
    (Keys.ControlLeft, "ctrl-left"),
    (Keys.ControlRight, "ctrl-right"),
    (Keys.ControlDelete, "ctrl-delete"),
    (Keys.ControlW, "ctrl-backspace"),
    (Keys.ShiftLeft, "shift-left"),
    (Keys.ShiftEnd, "shift-end"),
    (Keys.ControlShiftLeft, "ctrl-shift-left"),
    (Keys.ControlA, "select-all"),
    (Keys.ControlX, "cut"),
    (Keys.ControlV, "paste"),
    (Keys.ControlZ, "undo"),
    (Keys.ControlY, "redo"),
]


def _press(renderer: TerminalRenderer, key: Keys | str) -> None:
    bindings = renderer._application.key_bindings
    assert bindings is not None
    matches = bindings.get_bindings_for_keys((key,))
    assert matches, f"no binding for {key}"
    matches[-1].handler(cast("KeyPressEvent", object()))


@pytest.fixture
def seen() -> list[str]:
    return []


@pytest.fixture
def renderer(seen: list[str]) -> TerminalRenderer:
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        return TerminalRenderer(lambda _columns, _rows: Text(), seen.append)


@pytest.mark.parametrize(("key", "expected"), _EXPECTED_KEYS)
def test_each_key_arrives_as_its_own_name(
    renderer: TerminalRenderer,
    seen: list[str],
    key: Keys,
    expected: str,
) -> None:
    _press(renderer, key)
    assert seen == [expected]


def test_normalised_names_are_all_distinct() -> None:
    names = [name for _key, name in _EXPECTED_KEYS]
    assert len(names) == len(set(names))


def test_space_is_reported_separately_from_printable_text(renderer: TerminalRenderer, seen: list[str]) -> None:
    _press(renderer, " ")
    assert seen == ["space"]


@pytest.mark.parametrize(
    ("sequence", "expected"), [((Keys.Escape, "d"), "ctrl-delete"), ((Keys.Escape, Keys.Backspace), "ctrl-backspace")]
)
def test_terminal_word_deletion_sequences_use_the_shared_editor_action(
    renderer: TerminalRenderer, seen: list[str], sequence: tuple[Keys | str, ...], expected: str
) -> None:
    bindings = renderer._application.key_bindings
    assert bindings is not None
    matches = bindings.get_bindings_for_keys(sequence)
    assert matches
    matches[-1].handler(cast("KeyPressEvent", object()))
    assert seen == [expected]


@pytest.mark.parametrize(
    ("ctrl_backspace", "data", "expected"),
    [
        ("\x08", "\x7f", "backspace"),
        ("\x08", "\x08", "ctrl-backspace"),
        ("\x7f", "\x08", "backspace"),
        ("\x7f", "\x7f", "ctrl-backspace"),
    ],
)
def test_backspace_data_tells_ctrl_backspace_apart_for_the_active_reader(
    renderer: TerminalRenderer, seen: list[str], ctrl_backspace: str, data: str, expected: str
) -> None:
    renderer._ctrl_backspace = ctrl_backspace
    bindings = renderer._application.key_bindings
    assert bindings is not None
    bindings.get_bindings_for_keys((Keys.Backspace,))[-1].handler(cast("KeyPressEvent", SimpleNamespace(data=data)))

    assert seen == [expected]


def test_vt_input_sends_ctrl_backspace_as_backspace_control_character(renderer: TerminalRenderer) -> None:
    assert renderer._ctrl_backspace == "\x08"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console readers")
def test_windows_console_reader_decides_which_backspace_data_means_ctrl() -> None:
    if sys.platform == "win32":
        console_input: Win32Input = object.__new__(Win32Input)
        console_input.console_input_reader = object.__new__(ConsoleInputReader)
        vt_input: Win32Input = object.__new__(Win32Input)
        vt_input.console_input_reader = object.__new__(Vt100ConsoleInputReader)

        assert _ctrl_backspace_data(console_input) == "\x7f"
        assert _ctrl_backspace_data(vt_input) == "\x08"


def test_vt_parser_delivers_backspace_and_ctrl_backspace_separately() -> None:
    seen: list[str] = []

    async def run() -> None:
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):

            def key_received(key: str) -> None:
                seen.append(key)
                if len(seen) == 2:
                    vt_renderer.exit()

            vt_renderer: TerminalRenderer = TerminalRenderer(lambda _columns, _rows: Text(), key_received)
            await asyncio.wait_for(
                vt_renderer._application.run_async(pre_run=lambda: pipe.send_text("\x7f\x08")), _HANG_GUARD_S
            )

    asyncio.run(run())
    assert seen == ["backspace", "ctrl-backspace"]


def test_bracketed_paste_arrives_as_one_literal_edit(renderer: TerminalRenderer, seen: list[str]) -> None:
    bindings = renderer._application.key_bindings
    assert bindings is not None
    binding = bindings.get_bindings_for_keys((Keys.BracketedPaste,))[-1]
    binding.handler(cast("KeyPressEvent", SimpleNamespace(data="local/model\nsecond line")))

    assert seen == ["paste:local/model\nsecond line"]


def test_escape_is_delivered_without_waiting_for_a_one_second_key_prefix() -> None:
    seen: list[str] = []
    moments: list[float] = []

    async def run() -> None:
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):

            def send() -> None:
                moments.append(time.monotonic())
                pipe.send_text("\x1b")

            def key_received(key: str) -> None:
                moments.append(time.monotonic())
                seen.append(key)
                escape_renderer.exit()

            escape_renderer: TerminalRenderer = TerminalRenderer(lambda _columns, _rows: Text(), key_received)
            await asyncio.wait_for(escape_renderer._application.run_async(pre_run=send), _HANG_GUARD_S)

    asyncio.run(run())
    assert seen == ["escape"]
    assert moments[1] - moments[0] < _DEFAULT_KEY_PREFIX_S
