from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput
from rich.text import Text

from anishift.cli.interactive.prompts import TerminalRenderer

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent

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
    (Keys.Backspace, "backspace"),
    (Keys.Escape, "escape"),
    (Keys.ControlC, "interrupt"),
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
