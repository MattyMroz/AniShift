"""Tests for the slash-command completer."""

from __future__ import annotations

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from anishift.cli.completer import SlashCompleter


def _complete(text: str) -> list[str]:
    completer = SlashCompleter()
    doc = Document(text, cursor_position=len(text))
    return [c.text for c in completer.get_completions(doc, CompleteEvent())]


def test_no_completions_without_slash() -> None:
    assert _complete("hello") == []


def test_empty_input_yields_nothing() -> None:
    assert _complete("") == []


def test_slash_lists_all_commands_alphabetically() -> None:
    result = _complete("/")
    assert result == sorted(result)
    assert "/help" in result
    assert "/settings" in result


def test_prefix_filters_commands() -> None:
    assert _complete("/se") == ["/settings"]


def test_unmatched_prefix_yields_nothing() -> None:
    assert _complete("/zzz") == []
