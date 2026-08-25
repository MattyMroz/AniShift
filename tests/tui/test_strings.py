from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import pytest

import anishift.tui
from anishift.tui import strings
from anishift.tui.strings import (
    COMMAND_AUTO_DESCRIPTION,
    COMMAND_EXIT_TITLE,
    COMMAND_PALETTE_TITLE,
    COMPOSER_PLACEHOLDER,
    WORKSPACE_EMPTY,
)

_POLISH_LETTERS: Final[re.Pattern[str]] = re.compile(
    r"[\u0104-\u0107\u0118\u0119\u0141\u0142\u0143\u0144"
    r"\u00d3\u00f3\u015a\u015b\u0179-\u017c]"
)

_STRINGS_MODULE: Final[str] = "strings.py"

_MAX_TITLE_WORDS: Final[int] = 2

_MAX_DESCRIPTION_WORDS: Final[int] = 8

_TITLE_SUFFIX: Final[str] = "_TITLE"

_DESCRIPTION_SUFFIX: Final[str] = "_DESCRIPTION"


def _shell_sources() -> list[Path]:
    root: Path = Path(anishift.tui.__file__).parent
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _polish_lines(source: str) -> list[int]:
    return [number for number, line in enumerate(source.splitlines(), 1) if _POLISH_LETTERS.search(line)]


def _string_literals(source: str) -> list[str]:
    tree: ast.Module = ast.parse(source)
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _constants(suffix: str) -> dict[str, str]:
    return {
        name: value
        for name, value in vars(strings).items()
        if name.endswith(suffix) and isinstance(value, str) and not name.startswith("_")
    }


def test_no_shell_module_holds_a_polish_letter() -> None:
    offenders: list[str] = [
        f"{path.name}:{number}"
        for path in _shell_sources()
        for number in _polish_lines(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_language_guard_covers_the_dialog_primitives() -> None:
    root: Path = Path(anishift.tui.__file__).parent
    assert (root / "dialogs" / "select.py") in _shell_sources()


@pytest.mark.parametrize("source", ['PLACEHOLDER = "Wpisz komendę"\n', "# uruchamia przetwarzanie plików\n"])
def test_the_language_guard_flags_polish_in_any_line(source: str) -> None:
    assert _polish_lines(source) == [1]


def test_the_language_guard_leaves_plain_english_alone() -> None:
    assert _polish_lines('PLACEHOLDER = "Ask anything"\n') == []


def test_the_string_module_is_the_only_owner_of_the_specified_texts() -> None:
    fixed: tuple[str, ...] = (COMPOSER_PLACEHOLDER, WORKSPACE_EMPTY)
    offenders: list[str] = [
        f"{path.name}:{text}"
        for path in _shell_sources()
        if path.name != _STRINGS_MODULE
        for text in fixed
        if text in _string_literals(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_placeholder_and_the_base_state_match_the_specification() -> None:
    assert COMPOSER_PLACEHOLDER == "Ask anything or press enter to dub"
    assert WORKSPACE_EMPTY == "No supported files in workspace"


def test_every_action_title_stays_within_two_words() -> None:
    titles: dict[str, str] = _constants(_TITLE_SUFFIX)
    assert titles
    assert {name: value for name, value in titles.items() if len(value.split()) > _MAX_TITLE_WORDS} == {}
    assert COMMAND_EXIT_TITLE in titles.values()
    assert COMMAND_PALETTE_TITLE in titles.values()


def test_every_command_description_is_short_and_carries_no_full_stop() -> None:
    descriptions: dict[str, str] = _constants(_DESCRIPTION_SUFFIX)
    assert descriptions
    too_long: dict[str, str] = {
        name: value for name, value in descriptions.items() if len(value.split()) > _MAX_DESCRIPTION_WORDS
    }
    assert too_long == {}
    assert [name for name, value in descriptions.items() if value.endswith(".")] == []
    assert COMMAND_AUTO_DESCRIPTION in descriptions.values()
