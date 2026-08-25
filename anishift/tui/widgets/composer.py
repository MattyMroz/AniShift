"""The one always-present input line of the application, box and suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.events import MouseMove
from textual.message import Message
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from anishift.tui.commands.palette import slash_options
from anishift.tui.strings import (
    COMPOSER_PLACEHOLDER,
    COMPOSER_PLAIN_TEXT,
    COMPOSER_TAIL_EDGE_GLYPH,
    COMPOSER_TAIL_GLYPH,
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
    from collections.abc import Callable

    from textual.app import ComposeResult
    from textual.binding import BindingType
    from textual.geometry import Region

    from anishift.tui.commands.palette import CommandOption
    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandSpec

__all__ = [
    "BOX_ID",
    "BOX_ROWS",
    "COMPOSER_ID",
    "CONTEXT_ID",
    "HINT_ID",
    "INPUT_ID",
    "SUGGESTIONS_ID",
    "SUGGESTION_MAX_ROWS",
    "TAIL_ID",
    "Composer",
    "ComposerSubmission",
    "ComposerSubmissionKind",
    "classify",
    "context_content",
    "context_text",
]

# ── Constants ──────────────────────────────────────────────────────────────

COMPOSER_ID: Final[str] = "composer"
"""Id of the composer itself, inside the fixed slot of the frame."""

BOX_ID: Final[str] = "composer-box"
"""Id of the raised box holding the field and the context line."""

INPUT_ID: Final[str] = "composer-input"
"""Id of the one text field a submitted line can come from."""

SUGGESTIONS_ID: Final[str] = "composer-suggestions"
"""Id of the suggestion list shown above the text field."""

HINT_ID: Final[str] = "composer-hint"
"""Id of the one row the composer answers a line it refused in."""

CONTEXT_ID: Final[str] = "composer-context"
"""Id of the faded context line one row below the text field."""

TAIL_ID: Final[str] = "composer-tail"
"""Id of the half row closing the box below its context line."""

BOX_ROWS: Final[int] = 4
"""Rows the box always has: a blank edge, the field, a blank row, the context line."""

TAIL_ROWS: Final[int] = 1
"""Rows the closing half row takes under the box."""

SUGGESTION_MAX_ROWS: Final[int] = 10
"""Rows the suggestion overlay grows to before it starts scrolling instead."""

SLASH_PREFIX: Final[str] = "/"
"""Character that turns a submitted line into a command name."""

_MODE_STYLE: Final[str] = "bold $secondary"
"""Style of the mode word, matching the accent edge of the box."""

_ACCENT_STYLE: Final[str] = "$secondary"
"""Style of the accent edge, carried through the upper half of the closing row."""

_TAIL_STYLE: Final[str] = "$background-element"
"""Style painting the closing half row in the raised colour of the box."""

_PROVIDER_STYLE: Final[str] = "bold $text"
"""Style of the provider the context line names."""

_MODEL_STYLE: Final[str] = "$text"
"""Style of the model the context line names once one is chosen."""

_NAME_STYLE: Final[str] = "$text"
"""Style of the name of a suggestion the highlight does not rest on."""

_SENTENCE_STYLE: Final[str] = "$text-muted"
"""Style of the sentence of a suggestion the highlight does not rest on."""

_SELECTED_NAME_STYLE: Final[str] = "bold $on-primary"
"""Style of the name of the highlighted suggestion."""

_SELECTED_SENTENCE_STYLE: Final[str] = "$on-primary"
"""Style of the sentence of the highlighted suggestion."""

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
    """What one submitted line asks for."""

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


def context_content(*, mode: str, provider: str, model: str) -> Content:
    """Render the context line with the mode carrying the structural accent."""
    return Content.assemble(
        (mode, _MODE_STYLE),
        CONTEXT_SEPARATOR,
        (f"{provider}{CONTEXT_MODEL_SEPARATOR}", _PROVIDER_STYLE),
        (model, _SENTENCE_STYLE if model == CONTEXT_MODEL_UNSET else _MODEL_STYLE),
    )


def _slash_name(stripped: str) -> str:
    """Name one slash line asks for: the first word after the slash, folded."""
    body: str = stripped.removeprefix(SLASH_PREFIX).strip()
    if not body:
        return ""
    return body.split(maxsplit=1)[0].casefold()


class _Suggestions(OptionList):
    """Suggestion overlay that never takes the focus away from the text field.

    It hangs on the screen layer, so a click cannot bubble to the composer on its own.
    """

    can_focus = False

    def __init__(self, pick: Callable[[int], None], hover: Callable[[int], None], *, widget_id: str) -> None:
        """Offer rows reporting the picked position through *pick* and the pointed one through *hover*."""
        super().__init__(id=widget_id, markup=False)
        self._pick: Callable[[int], None] = pick
        self._hover: Callable[[int], None] = hover

    @on(OptionList.OptionSelected)
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Report the clicked row, and let nothing else act on that click."""
        event.stop()
        self._pick(event.option_index)

    def _on_mouse_move(self, event: MouseMove) -> None:
        """Report the row the pointer rests on, so it carries the one highlight."""
        super()._on_mouse_move(event)
        pointed: object = event.style.meta.get("option")
        if isinstance(pointed, int):
            self._hover(pointed)


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
        self._suggestions: _Suggestions = _Suggestions(
            self._pick_suggestion,
            self._highlight,
            widget_id=SUGGESTIONS_ID,
        )
        self._box: Vertical = Vertical(id=BOX_ID)
        self._input: Input = Input(placeholder=COMPOSER_PLACEHOLDER, id=INPUT_ID)
        self._input.cursor_blink = False
        self._written: str = ""
        self._context_line: Static = Static(
            context_content(mode=CONTEXT_MODE_AUTO, provider=CONTEXT_PROVIDER, model=CONTEXT_MODEL_UNSET),
            id=CONTEXT_ID,
        )
        self._tail: Static = Static(id=TAIL_ID)
        self._hint: Static = Static(id=HINT_ID)

    def compose(self) -> ComposeResult:
        """Draw the box and its closing half row, then the answer row.

        The suggestions live on their own layer, mounted on the screen.
        """
        with self._box:
            yield self._input
            yield self._context_line
        yield self._tail
        yield self._hint

    def show_context(self, *, mode: str, provider: str, model: str) -> None:
        """Say which mode, provider and model the next run would use."""
        self._context_line.update(context_content(mode=mode, provider=provider, model=model))

    def on_mount(self) -> None:
        """Hang the suggestion overlay on the screen, then start as a plain field."""
        self.screen.mount(self._suggestions)
        self._hide_suggestions()
        self._clear_hint()
        self._paint_tail()

    def on_resize(self) -> None:
        """Redraw the closing half row across the width the box just took."""
        self._paint_tail()

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
        if event.value == self._written:
            self._written = ""
            return
        self._offer(event.value)

    @on(Input.Submitted, f"#{INPUT_ID}")
    def _on_input_submitted(self, event: Input.Submitted) -> None:
        """Act on one finished line, and never on the text of another widget."""
        event.stop()
        highlighted: CommandOption | None = self._highlighted()
        if highlighted is not None:
            self._write(highlighted)
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
        self._write(highlighted)

    def _write(self, option: CommandOption) -> None:
        """Write the name of *option* into the field, ready for one more Enter to run it."""
        text: str = f"{option.label} "
        self._written = text
        self._input.value = text
        self._input.cursor_position = len(text)
        self._hide_suggestions()

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
        self._suggestions.display = True
        self._paint(0)
        self._place()

    def _pick_suggestion(self, index: int) -> None:
        """Run the command a click picked out of the overlay."""
        if 0 <= index < len(self._offered):
            self._run(self._offered[index].name)

    def _paint_tail(self) -> None:
        """Close the box with one half row, the accent edge ending flush with it."""
        width: int = self._box.region.width
        if width < 1:
            return
        self._tail.update(
            Content.assemble(
                (COMPOSER_TAIL_EDGE_GLYPH, _ACCENT_STYLE),
                (COMPOSER_TAIL_GLYPH * (width - 1), _TAIL_STYLE),
            )
        )

    def _place(self) -> None:
        """Pin the overlay to the rows directly above the box, drawing over the work area."""
        box: Region = self._box.region
        rows: int = min(len(self._offered), SUGGESTION_MAX_ROWS, box.y)
        self._suggestions.styles.width = box.width
        self._suggestions.styles.height = rows
        self._suggestions.styles.offset = (box.x, box.y - rows)

    def _name_width(self) -> int:
        """Columns the name column takes: the widest offered name, so sentences line up."""
        return max((len(option.label) for option in self._offered), default=0)

    def _paint(self, highlighted: int) -> None:
        """Re-render the offered rows so the highlighted one carries the contrast colour."""
        width: int = self._name_width()
        self._suggestions.set_options(
            [
                Option(self._suggestion_content(option, width=width, selected=index == highlighted))
                for index, option in enumerate(self._offered)
            ]
        )
        self._suggestions.highlighted = highlighted

    def _suggestion_row(self, option: CommandOption) -> str:
        """Text one suggested command shows: its slash name and its sentence."""
        return f"{option.label.ljust(self._name_width())}{SUGGESTION_ROW_GAP}{option.description}"

    def _suggestion_content(self, option: CommandOption, *, width: int, selected: bool) -> Content:
        """Render one suggested command in two columns, weighting its name over its sentence."""
        return Content.assemble(
            (option.label.ljust(width), _SELECTED_NAME_STYLE if selected else _NAME_STYLE),
            SUGGESTION_ROW_GAP,
            (option.description, _SELECTED_SENTENCE_STYLE if selected else _SENTENCE_STYLE),
        )

    def _move(self, delta: int) -> None:
        """Move the highlight *delta* suggestions, wrapping at either end."""
        count: int = len(self._offered)
        if count == 0:
            return
        current: int = self._suggestions.highlighted or 0
        self._highlight((current + delta) % count)

    def _highlight(self, index: int) -> None:
        """Rest the one highlight on *index*, repainting only the two rows that change."""
        if not 0 <= index < len(self._offered):
            return
        current: int | None = self._suggestions.highlighted
        if current == index:
            return
        width: int = self._name_width()
        if current is not None and 0 <= current < len(self._offered):
            self._suggestions.replace_option_prompt_at_index(
                current,
                self._suggestion_content(self._offered[current], width=width, selected=False),
            )
        self._suggestions.replace_option_prompt_at_index(
            index,
            self._suggestion_content(self._offered[index], width=width, selected=True),
        )
        self._suggestions.highlighted = index

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
