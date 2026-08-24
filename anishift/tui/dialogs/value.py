"""The editors one value is changed with, text, number and confirmation.

Text and numbers are two editors in one module because they share one contract:
the typed value stays in the box while it is wrong, the reason is shown inline,
and ``Enter`` closes the editor only for a value that passed. A booleans needs no
modal at all — ``toggle_boolean`` gives the settings tree the value a row takes
when it is switched in place.

None of these editors writes anything. Each one returns a value, and the caller
performs the atomic save.

Public API:
    REQUIRED_VALUE_TEXT: Reason shown when a required value was left empty.
    NOT_A_NUMBER_TEXT: Reason shown when the typed text is not a number.
    OPTIONAL_HINT: Hint telling that an empty value is allowed.
    CONFIRM_HINT: Hint of the confirmation dialog.
    NumberKind: Whether a number editor edits whole numbers or decimals.
    Validator: Caller's own check of one typed text.
    range_text: Hint one number editor shows about its range and its step.
    out_of_range_text: Reason shown when a number leaves its range.
    toggle_boolean: Value a boolean row takes when it is switched in place.
    PromptDialog: Editor of one text value, optional or required.
    NumberDialog: Editor of one whole or decimal number.
    ConfirmDialog: The one yes-or-no dialog of the application.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.binding import Binding
from textual.widgets import Input, Static

from anishift.tui.dialogs.base import DialogScreen, DialogSize

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import BindingType

__all__ = [
    "CONFIRM_HINT",
    "NOT_A_NUMBER_TEXT",
    "OPTIONAL_HINT",
    "REQUIRED_VALUE_TEXT",
    "ConfirmDialog",
    "NumberDialog",
    "NumberKind",
    "PromptDialog",
    "Validator",
    "out_of_range_text",
    "range_text",
    "toggle_boolean",
]

# ── Constants ──────────────────────────────────────────────────────────────

REQUIRED_VALUE_TEXT: Final[str] = "Wartość jest wymagana."
"""Reason shown when a required value was left empty."""

NOT_A_NUMBER_TEXT: Final[str] = "Podaj liczbę."
"""Reason shown when the typed text is not a number at all."""

OPTIONAL_HINT: Final[str] = "Puste pole usuwa wartość."
"""Hint telling that an empty value is allowed."""

CONFIRM_HINT: Final[str] = "Enter potwierdza · Esc anuluje"
"""Hint of the confirmation dialog."""

Validator = Callable[[str], str | None]
"""Caller's own check of one typed text: a reason, or ``None`` when it passed."""

_DECIMAL_STEP: Final[float] = 0.5
"""Step a decimal editor uses when the caller's field specification gives none."""

_WHOLE_STEP: Final[float] = 1.0
"""Step a whole-number editor uses when the caller's field specification gives none."""

_INPUT_ID: Final[str] = "value-input"
"""Id of the one box a value editor is typed into."""

_HINT_ID: Final[str] = "value-hint"
"""Id of the row describing what the editor accepts."""

_ERROR_ID: Final[str] = "value-error"
"""Id of the row holding the reason the value was refused."""

_MESSAGE_ID: Final[str] = "confirm-message"
"""Id of the question the confirmation dialog asks."""

_RANGE_DASH: Final[str] = " – "
"""Separator between the two ends of a range."""

_HINT_JOINER: Final[str] = " · "
"""Separator between the parts of one hint row."""


class NumberKind(StrEnum):
    """Whether a number editor edits whole numbers or decimals."""

    WHOLE = "whole"
    DECIMAL = "decimal"


def range_text(*, minimum: float | None, maximum: float | None, step: float) -> str:
    """Hint one number editor shows about its range and its step."""
    parts: list[str] = []
    if minimum is not None or maximum is not None:
        low: str = "…" if minimum is None else _number_text(minimum)
        high: str = "…" if maximum is None else _number_text(maximum)
        parts.append(f"Zakres {low}{_RANGE_DASH}{high}")
    parts.append(f"krok {_number_text(step)}")
    return _HINT_JOINER.join(parts)


def out_of_range_text(*, minimum: float | None, maximum: float | None) -> str:
    """Reason shown when a number leaves the range its field allows.

    A field without any bound cannot be out of range, so its reason is empty.
    """
    if minimum is not None and maximum is not None:
        return f"Wartość musi być z zakresu {_number_text(minimum)}{_RANGE_DASH}{_number_text(maximum)}."
    if minimum is not None:
        return f"Wartość nie może być mniejsza niż {_number_text(minimum)}."
    if maximum is not None:
        return f"Wartość nie może być większa niż {_number_text(maximum)}."
    return ""


def toggle_boolean(current: bool) -> bool:
    """Value a boolean row takes when the settings tree switches it in place."""
    return not current


def _number_text(value: float) -> str:
    """Shortest honest text of one number, without a trailing ``.0``."""
    return str(int(value)) if float(value).is_integer() else str(value)


class PromptDialog(DialogScreen[str | None]):
    """Editor of one text value, optional or required.

    A refused value stays in the box with its reason below it, so nothing the
    user typed is ever lost to a failed validation.
    """

    AUTO_FOCUS: ClassVar[str | None] = f"#{_INPUT_ID}"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "confirm", "Zatwierdź", show=False, priority=True),
    ]

    def __init__(  # noqa: PLR0913 - one text editor serves every field, so its whole contract stays explicit
        self,
        *,
        title: str,
        value: str = "",
        placeholder: str = "",
        hint: str = "",
        optional: bool = False,
        validate: Validator | None = None,
        size: DialogSize = DialogSize.MEDIUM,
    ) -> None:
        """Edit *value*, letting the caller check every text through *validate*."""
        super().__init__(title=title, size=size)
        self._optional: bool = optional
        self._validate: Validator | None = validate
        self._input: Input = Input(value=value, placeholder=placeholder, id=_INPUT_ID)
        self._hint: Static = Static(self._hint_text(hint), id=_HINT_ID, classes="dialog-hint")
        self._error: Static = Static(id=_ERROR_ID, classes="dialog-error")

    def compose_dialog(self) -> ComposeResult:
        """Draw the box, what it accepts and the reason it refused a value."""
        yield self._input
        yield self._hint
        yield self._error

    def cancel_result(self) -> str | None:
        """A cancelled text editor changes nothing."""
        return None

    def action_confirm(self) -> None:
        """Close the editor, but only for a text that passed every check."""
        text: str = self._input.value
        reason: str | None = self._reason(text)
        if reason is not None:
            self._error.update(reason)
            return
        self.dismiss(None if self._optional and not text else text)

    @on(Input.Changed)
    def _on_changed(self, event: Input.Changed) -> None:
        """Show the reason a value is wrong while it is being typed."""
        event.stop()
        self._error.update(self._reason(self._input.value) or "")

    def _reason(self, text: str) -> str | None:
        """Why *text* cannot be accepted, or ``None`` when it can."""
        if not text:
            return None if self._optional else REQUIRED_VALUE_TEXT
        return None if self._validate is None else self._validate(text)

    def _hint_text(self, hint: str) -> str:
        """Hint row of this editor, including the empty-value rule."""
        parts: list[str] = [part for part in (hint, OPTIONAL_HINT if self._optional else "") if part]
        return _HINT_JOINER.join(parts)


class NumberDialog(DialogScreen[int | float | None]):
    """Editor of one whole or decimal number, typed or stepped.

    ``Up`` and ``Down`` step the value by the amount the caller's field
    specification gives, clamped to the range; the range and the step are always
    visible, so no rule is hidden from the user.
    """

    AUTO_FOCUS: ClassVar[str | None] = f"#{_INPUT_ID}"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "confirm", "Zatwierdź", show=False, priority=True),
        Binding("up", "step_up", "Więcej", show=False, priority=True),
        Binding("down", "step_down", "Mniej", show=False, priority=True),
    ]

    def __init__(  # noqa: PLR0913 - range, step and kind of one number field stay explicit
        self,
        *,
        title: str,
        value: int | float | None = None,
        kind: NumberKind = NumberKind.DECIMAL,
        minimum: float | None = None,
        maximum: float | None = None,
        step: float | None = None,
        optional: bool = False,
        size: DialogSize = DialogSize.MEDIUM,
    ) -> None:
        """Edit *value* inside ``minimum..maximum``, stepping it by *step*."""
        super().__init__(title=title, size=size)
        self._kind: NumberKind = kind
        self._minimum: float | None = minimum
        self._maximum: float | None = maximum
        self._step: float = self._default_step() if step is None else step
        self._optional: bool = optional
        self._input: Input = Input(value="" if value is None else _number_text(value), id=_INPUT_ID)
        self._hint: Static = Static(self._hint_text(), id=_HINT_ID, classes="dialog-hint")
        self._error: Static = Static(id=_ERROR_ID, classes="dialog-error")

    def compose_dialog(self) -> ComposeResult:
        """Draw the box, the range with the step and the refusal reason."""
        yield self._input
        yield self._hint
        yield self._error

    def cancel_result(self) -> int | float | None:
        """A cancelled number editor changes nothing."""
        return None

    def action_confirm(self) -> None:
        """Close the editor, but only for a number inside its range."""
        text: str = self._input.value
        reason: str | None = self._reason(text)
        if reason is not None:
            self._error.update(reason)
            return
        if not text:
            self.dismiss(None)
            return
        self.dismiss(self._parsed(text))

    def action_step_up(self) -> None:
        """Raise the value by one step, never above the range."""
        self._step_by(self._step)

    def action_step_down(self) -> None:
        """Lower the value by one step, never below the range."""
        self._step_by(-self._step)

    @on(Input.Changed)
    def _on_changed(self, event: Input.Changed) -> None:
        """Show the reason a number is wrong while it is being typed."""
        event.stop()
        self._error.update(self._reason(self._input.value) or "")

    def _default_step(self) -> float:
        """Step used when the caller's field specification names none."""
        return _WHOLE_STEP if self._kind is NumberKind.WHOLE else _DECIMAL_STEP

    def _hint_text(self) -> str:
        """Hint row of this editor, including the empty-value rule."""
        parts: list[str] = [range_text(minimum=self._minimum, maximum=self._maximum, step=self._step)]
        if self._optional:
            parts.append(OPTIONAL_HINT)
        return _HINT_JOINER.join(parts)

    def _reason(self, text: str) -> str | None:
        """Why *text* cannot be accepted as this field's number."""
        if not text:
            return None if self._optional else REQUIRED_VALUE_TEXT
        number: int | float | None = self._parsed(text)
        if number is None:
            return NOT_A_NUMBER_TEXT
        if self._minimum is not None and number < self._minimum:
            return out_of_range_text(minimum=self._minimum, maximum=self._maximum)
        if self._maximum is not None and number > self._maximum:
            return out_of_range_text(minimum=self._minimum, maximum=self._maximum)
        return None

    def _parsed(self, text: str) -> int | float | None:
        """Number *text* holds for this field's kind, or ``None`` when it holds none."""
        try:
            number: float = float(text.replace(",", "."))
        except ValueError:
            return None
        if self._kind is not NumberKind.WHOLE:
            return number
        return int(number) if number.is_integer() else None

    def _step_by(self, amount: float) -> None:
        """Move the typed value by *amount*, clamped to the range of the field."""
        current: int | float | None = self._parsed(self._input.value)
        fallback: float = 0.0 if self._minimum is None else self._minimum
        base: float = fallback if current is None else float(current)
        moved: float = base + amount
        if self._minimum is not None:
            moved = max(moved, self._minimum)
        if self._maximum is not None:
            moved = min(moved, self._maximum)
        self._input.value = _number_text(int(moved) if self._kind is NumberKind.WHOLE else moved)


class ConfirmDialog(DialogScreen[bool]):
    """The one yes-or-no dialog of the application.

    ``Enter`` confirms and ``Esc`` refuses, so a destructive step always has one
    shape wherever it is asked for.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "confirm", "Potwierdź", show=False, priority=True),
    ]

    def __init__(self, *, title: str, question: str, size: DialogSize = DialogSize.MEDIUM) -> None:
        """Ask *question* under the heading *title*."""
        super().__init__(title=title, size=size)
        self._question: str = question

    def compose_dialog(self) -> ComposeResult:
        """Draw the question and the two keys that answer it."""
        yield Static(self._question, id=_MESSAGE_ID)
        yield Static(CONFIRM_HINT, classes="dialog-hint")

    def cancel_result(self) -> bool:
        """A cancelled confirmation is a refusal."""
        return False

    def action_confirm(self) -> None:
        """Answer the question with a yes."""
        self.dismiss(True)
