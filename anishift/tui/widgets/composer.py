"""The one always-present input line of the application, box and suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from anishift.tui.commands.palette import slash_options
from anishift.tui.strings import (
    COMPOSER_ACCENT_GLYPH,
    COMPOSER_PLACEHOLDER,
    COMPOSER_PLAIN_TEXT,
    COMPOSER_PROMPT_GLYPH,
    COMPOSER_UNKNOWN_COMMAND,
    COMPOSER_UNKNOWN_COMMAND_SUGGESTION,
    CONTEXT_MODE_AUTO,
    CONTEXT_MODEL_SEPARATOR,
    CONTEXT_MODEL_UNSET,
    CONTEXT_PROVIDER,
    CONTEXT_SEPARATOR,
    SUGGESTION_COMPLETE_LABEL,
    SUGGESTION_DISMISS_LABEL,
    SUGGESTION_NEXT_LABEL,
    SUGGESTION_PREVIOUS_LABEL,
    SUGGESTION_ROW_GAP,
)

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import BindingType

    from anishift.tui.commands.palette import CommandOption
    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandSpec

__all__ = [
    "ACCENT_ID",
    "BODY_ID",
    "BOX_ID",
    "BOX_ROWS",
    "COMPOSER_ID",
    "CONTEXT_ID",
    "FIELD_ID",
    "HINT_ID",
    "INPUT_ID",
    "PROMPT_ID",
    "SUGGESTIONS_ID",
    "Composer",
    "ComposerSubmission",
    "ComposerSubmissionKind",
    "classify",
    "context_text",
]

# ── Constants ──────────────────────────────────────────────────────────────

COMPOSER_ID: Final[str] = "composer"
"""Id of the composer itself, inside the fixed slot of the frame."""

BOX_ID: Final[str] = "composer-box"
"""Id of the raised box holding the accent, the field and the context line."""

BODY_ID: Final[str] = "composer-body"
"""Id of the column the box keeps beside its accent."""

FIELD_ID: Final[str] = "composer-field"
"""Id of the one row holding the prompt glyph and the text field."""

INPUT_ID: Final[str] = "composer-input"
"""Id of the one text field a submitted line can come from."""

SUGGESTIONS_ID: Final[str] = "composer-suggestions"
"""Id of the suggestion list shown above the text field."""

HINT_ID: Final[str] = "composer-hint"
"""Id of the one row the composer answers a line it refused in."""

PROMPT_ID: Final[str] = "composer-prompt"
"""Id of the prompt glyph in front of the text field."""

ACCENT_ID: Final[str] = "composer-accent"
"""Id of the accent column drawn on the left edge of the box."""

CONTEXT_ID: Final[str] = "composer-context"
"""Id of the faded context line one row below the text field."""

BOX_ROWS: Final[int] = 3
"""Rows the box always has: the field, one blank row and the context line."""

SLASH_PREFIX: Final[str] = "/"
"""Character that turns a submitted line into a command name."""

_ACCENT_COLUMN: Final[str] = "\n".join([COMPOSER_ACCENT_GLYPH] * BOX_ROWS)
"""Accent column of the box: the edge glyph once per row of the box."""

_SUGGESTION_ACTIONS: Final[frozenset[str]] = frozenset(
    {"previous_suggestion", "next_suggestion", "complete_suggestion", "dismiss_suggestions"},
)
"""Actions that exist only while the suggestion list is on screen."""


class ComposerSubmissionKind(StrEnum):
    """The three readings one submitted line can have."""

    EMPTY_AUTO = "empty_auto"
    SLASH = "slash"
    PLAIN_TEXT = "plain_text"


@dataclass(frozen=True, slots=True)
class ComposerSubmission:
    """What one submitted line asks for.

    Attributes:
        kind: Reading of the line the composer decided on.
        command: Slash name the line carries, without the slash and in one word;
            empty for every other reading and for a line that names nothing.
    """

    kind: ComposerSubmissionKind
    command: str = ""


def classify(text: str) -> ComposerSubmission:
    """Classify *text* as empty-auto, slash command, or plain text."""
    stripped: str = text.strip()
    if not stripped:
        return ComposerSubmission(kind=ComposerSubmissionKind.EMPTY_AUTO)
    if not stripped.startswith(SLASH_PREFIX):
        return ComposerSubmission(kind=ComposerSubmissionKind.PLAIN_TEXT)
    return ComposerSubmission(kind=ComposerSubmissionKind.SLASH, command=_slash_name(stripped))


def context_text(*, mode: str, provider: str, model: str) -> str:
    """Render the context line: which mode, provider and model the next run uses."""
    return f"{mode}{CONTEXT_SEPARATOR}{provider}{CONTEXT_MODEL_SEPARATOR}{model}"


def _slash_name(stripped: str) -> str:
    """Name one slash line asks for: the first word after the slash, folded."""
    body: str = stripped.removeprefix(SLASH_PREFIX).strip()
    if not body:
        return ""
    return body.split(maxsplit=1)[0].casefold()


class _Suggestions(OptionList):
    """Suggestion list that never takes the focus away from the text field."""

    can_focus = False


class Composer(Vertical):
    """The one always-present input line of the application.

    ``Enter`` is deliberately absent: a line arrives as ``Input.Submitted``.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "previous_suggestion", SUGGESTION_PREVIOUS_LABEL, show=False),
        Binding("down", "next_suggestion", SUGGESTION_NEXT_LABEL, show=False),
        Binding("tab", "complete_suggestion", SUGGESTION_COMPLETE_LABEL, show=False),
        Binding("escape", "dismiss_suggestions", SUGGESTION_DISMISS_LABEL, show=False),
    ]

    class EmptySubmitted(Message):
        """One finished line holding nothing but blanks left the composer."""

    def __init__(self, registry: CommandRegistry) -> None:
        """Offer the commands *registry* currently holds, and no other list."""
        super().__init__(id=COMPOSER_ID)
        self._registry: CommandRegistry = registry
        self._offered: tuple[CommandOption, ...] = ()
        self._suggestions: _Suggestions = _Suggestions(id=SUGGESTIONS_ID, markup=False)
        self._accent: Static = Static(_ACCENT_COLUMN, id=ACCENT_ID)
        self._prompt: Static = Static(COMPOSER_PROMPT_GLYPH, id=PROMPT_ID)
        self._input: Input = Input(placeholder=COMPOSER_PLACEHOLDER, id=INPUT_ID)
        self._context_line: Static = Static(
            context_text(mode=CONTEXT_MODE_AUTO, provider=CONTEXT_PROVIDER, model=CONTEXT_MODEL_UNSET),
            id=CONTEXT_ID,
        )
        self._hint: Static = Static(id=HINT_ID)

    def compose(self) -> ComposeResult:
        """Draw the suggestions above the box, then the box, then the answer row."""
        yield self._suggestions
        with Horizontal(id=BOX_ID):
            yield self._accent
            with Vertical(id=BODY_ID):
                with Horizontal(id=FIELD_ID):
                    yield self._prompt
                    yield self._input
                yield self._context_line
        yield self._hint

    def show_context(self, *, mode: str, provider: str, model: str) -> None:
        """Say which mode, provider and model the next run would use."""
        self._context_line.update(context_text(mode=mode, provider=provider, model=model))

    def on_mount(self) -> None:
        """Start as a plain field: no suggestions and nothing to answer."""
        self._hide_suggestions()
        self._clear_hint()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Claim the suggestion keys only while the suggestion list is on screen."""
        del parameters
        if action in _SUGGESTION_ACTIONS:
            return self._suggestions.display
        return True

    def clear(self) -> None:
        """Empty the field and drop the suggestions, keeping the focus."""
        self._input.value = ""
        self._hide_suggestions()

    @on(Input.Changed, f"#{INPUT_ID}")
    def _on_input_changed(self, event: Input.Changed) -> None:
        """Offer the commands the typed line could mean, and drop the last answer."""
        event.stop()
        self._clear_hint()
        self._offer(event.value)

    @on(Input.Submitted, f"#{INPUT_ID}")
    def _on_input_submitted(self, event: Input.Submitted) -> None:
        """Act on one finished line, and never on the text of another widget."""
        event.stop()
        highlighted: CommandOption | None = self._highlighted()
        if highlighted is not None:
            self._run(highlighted.name)
            return
        submission: ComposerSubmission = classify(event.value)
        if submission.kind is ComposerSubmissionKind.EMPTY_AUTO:
            self.post_message(self.EmptySubmitted())
            return
        if submission.kind is ComposerSubmissionKind.PLAIN_TEXT:
            self._show_hint(COMPOSER_PLAIN_TEXT)
            return
        self._run_slash(submission.command)

    def action_previous_suggestion(self) -> None:
        """Highlight the suggestion above the current one."""
        self._move(-1)

    def action_next_suggestion(self) -> None:
        """Highlight the suggestion below the current one."""
        self._move(1)

    def action_complete_suggestion(self) -> None:
        """Write the highlighted name into the field, and run nothing."""
        highlighted: CommandOption | None = self._highlighted()
        if highlighted is None:
            return
        self._input.value = highlighted.label
        self._input.cursor_position = len(self._input.value)

    def action_dismiss_suggestions(self) -> None:
        """Drop the suggestions, leaving the typed line exactly as it is."""
        self._hide_suggestions()

    def _offer(self, value: str) -> None:
        """Show the ranked commands *value* could mean, or no list at all."""
        query: str = value.strip()
        if not query.startswith(SLASH_PREFIX):
            self._hide_suggestions()
            return
        self._offered = slash_options(self._registry, query)
        if not self._offered:
            self._hide_suggestions()
            return
        self._suggestions.set_options([Option(self._suggestion_row(option)) for option in self._offered])
        self._suggestions.display = True
        self._suggestions.highlighted = 0

    def _suggestion_row(self, option: CommandOption) -> str:
        """Text one suggested command shows: its slash name and its sentence."""
        return f"{option.label}{SUGGESTION_ROW_GAP}{option.description}"

    def _move(self, delta: int) -> None:
        """Move the highlight *delta* suggestions, wrapping at either end."""
        count: int = len(self._offered)
        if count == 0:
            return
        current: int = self._suggestions.highlighted or 0
        self._suggestions.highlighted = (current + delta) % count

    def _highlighted(self) -> CommandOption | None:
        """Suggestion the list rests on, or ``None`` while there is no list."""
        if not self._suggestions.display:
            return None
        index: int | None = self._suggestions.highlighted
        if index is None or not 0 <= index < len(self._offered):
            return None
        return self._offered[index]

    def _run_slash(self, command: str) -> None:
        """Run the command one slash line named, or say why nothing happened.

        A line that names nothing after the slash never reaches the registry.
        """
        if not command:
            self._show_hint(COMPOSER_UNKNOWN_COMMAND)
            return
        resolved: CommandSpec | None = self._resolved(command)
        if resolved is None:
            self._show_hint(self._unknown_hint(command))
            return
        self._run(resolved.name)

    def _resolved(self, command: str) -> CommandSpec | None:
        """Command whose slash name is *command*; aliases resolve nothing here."""
        return next((spec for spec in self._registry.available() if spec.slash_name == command), None)

    def _unknown_hint(self, command: str) -> str:
        """Answer for *command*, naming the closest known command if there is one."""
        nearest: tuple[CommandOption, ...] = slash_options(self._registry, command)
        if not nearest:
            return COMPOSER_UNKNOWN_COMMAND
        return COMPOSER_UNKNOWN_COMMAND_SUGGESTION.format(command=nearest[0].label)

    def _run(self, name: str) -> None:
        """Run the command called *name* through the one dispatch point."""
        self._hide_suggestions()
        if self._registry.dispatch(name):
            self.clear()

    def _hide_suggestions(self) -> None:
        """Take the suggestion list off the screen and forget what it offered."""
        self._offered = ()
        self._suggestions.clear_options()
        self._suggestions.display = False

    def _show_hint(self, text: str) -> None:
        """Answer the last line with *text*, leaving that line in the field."""
        self._hint.update(text)
        self._hint.display = True

    def _clear_hint(self) -> None:
        """Take the last answer off the screen."""
        self._hint.update("")
        self._hint.display = False
