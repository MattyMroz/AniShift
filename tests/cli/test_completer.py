from __future__ import annotations

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import to_plain_text

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
    assert _complete("/se") == ["/settings", "/setup"]


def test_unmatched_prefix_yields_nothing() -> None:
    assert _complete("/zzz") == []


def test_space_after_setup_suggests_its_options() -> None:
    assert _complete("/setup ") == ["force"]


def test_option_prefix_filters_options() -> None:
    assert _complete("/setup f") == ["force"]
    assert _complete("/setup x") == []


def test_option_meta_is_the_option_description() -> None:
    completer = SlashCompleter()
    doc = Document("/setup ", cursor_position=len("/setup "))
    completion = next(iter(completer.get_completions(doc, CompleteEvent())))
    assert "re-download" in to_plain_text(completion.display_meta)


def test_space_after_optionless_command_suggests_nothing() -> None:
    assert _complete("/help ") == []


def test_space_after_unknown_command_suggests_nothing() -> None:
    assert _complete("/zzz ") == []
