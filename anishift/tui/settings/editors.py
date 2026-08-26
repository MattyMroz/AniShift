"""The one editor dispatch every setting is changed through, keyed by value type."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.reorder import ReorderDialog
from anishift.tui.dialogs.select import SelectAction, SelectDialog, SelectOption, SelectOutcomeKind
from anishift.tui.dialogs.value import ConfirmDialog, NumberDialog, NumberKind, PromptDialog, toggle_boolean
from anishift.tui.state import FeedbackLevel, UiFeedback
from anishift.tui.strings import (
    OBJECT_ADD_LABEL,
    OBJECT_REMOVE_LABEL,
    OBJECT_REMOVE_QUESTION,
    OBJECT_REMOVE_TITLE,
    SETTING_EMPTY_VALUE,
    SETTING_INVALID_VALUE,
    SETTING_LIST_SEPARATOR,
    SETTING_UNSET,
    SETTINGS_OFF,
    SETTINGS_ON,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import App

    from anishift.application import AppService
    from anishift.config.field_catalog import SettingSpec, SettingValue
    from anishift.tui.dialogs.select import SelectOutcome
    from anishift.tui.dialogs.value import Validator
    from anishift.tui.state import SessionState

__all__ = ["EditorKind", "editor_for", "open_field_editor", "value_summary"]

# ── Constants ──────────────────────────────────────────────────────────────

_OBJECT_ADD: Final[str] = "add_item"
"""Action name of the key that adds one item to an object list."""

_OBJECT_REMOVE: Final[str] = "remove_item"
"""Action name of the key that removes the highlighted object-list item."""

_OBJECT_ADD_KEY: Final[str] = "ctrl+a"
"""Key that adds one item, kept off the letters the filter box consumes."""

_OBJECT_REMOVE_KEY: Final[str] = "ctrl+d"
"""Key that removes one item, kept off the letters the filter box consumes."""


class EditorKind(StrEnum):
    """The editor one setting opens, chosen only from its value type."""

    SELECT = "select"
    TEXT = "text"
    NUMBER = "number"
    TOGGLE = "toggle"
    MULTI_SELECT = "multi_select"
    REORDER = "reorder"
    OBJECT_WIZARD = "object_wizard"


def editor_for(spec: SettingSpec) -> EditorKind:
    """Return the editor *spec* opens, total over every setting value type."""
    from anishift.config.field_catalog import SettingValueType  # noqa: PLC0415

    value_type = spec.value_type
    if value_type in {SettingValueType.STRING, SettingValueType.OPTIONAL_STRING}:
        return EditorKind.SELECT if spec.allowed_values else EditorKind.TEXT
    if value_type in {
        SettingValueType.INTEGER,
        SettingValueType.OPTIONAL_INTEGER,
        SettingValueType.FLOAT,
        SettingValueType.OPTIONAL_FLOAT,
    }:
        return EditorKind.NUMBER
    if value_type is SettingValueType.BOOLEAN:
        return EditorKind.TOGGLE
    if value_type is SettingValueType.STRING_LIST:
        return EditorKind.REORDER
    if value_type is SettingValueType.STRING_SET:
        return EditorKind.MULTI_SELECT
    if value_type is SettingValueType.OBJECT_LIST:
        return EditorKind.OBJECT_WIZARD
    msg = f"No editor for setting value type: {value_type!r}"
    raise ValueError(msg)


def value_summary(value: SettingValue) -> str:
    """Return the text one settings row shows for the value it holds."""
    if isinstance(value, bool):
        return SETTINGS_ON if value else SETTINGS_OFF
    if value is None:
        return SETTING_UNSET
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    if isinstance(value, str):
        return value or SETTING_UNSET
    if isinstance(value, frozenset):
        return SETTING_LIST_SEPARATOR.join(sorted(value)) or SETTING_EMPTY_VALUE
    parts: list[str] = [item if isinstance(item, str) else str(getattr(item, "alias", item)) for item in value]
    return SETTING_LIST_SEPARATOR.join(parts) or SETTING_EMPTY_VALUE


def open_field_editor(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    current: SettingValue,
    on_committed: Callable[[], None],
) -> None:
    """Open the editor *spec* asks for, committing a confirmed value only."""
    kind: EditorKind = editor_for(spec)
    if kind is EditorKind.TOGGLE:
        _commit(state, service, spec, toggle_boolean(bool(current)))
        on_committed()
        return
    if kind is EditorKind.SELECT:
        _open_select(app, state, service, spec, current, on_committed)
        return
    if kind is EditorKind.TEXT:
        _open_text(app, state, service, spec, current, on_committed)
        return
    if kind is EditorKind.NUMBER:
        _open_number(app, state, service, spec, current, on_committed)
        return
    if kind is EditorKind.MULTI_SELECT:
        _open_multi(app, state, service, spec, current, on_committed)
        return
    if kind is EditorKind.REORDER:
        _open_reorder(app, state, service, spec, current, on_committed)
        return
    _open_object_wizard(app, state, service, spec, current, on_committed)


def _open_select(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    current: SettingValue,
    on_committed: Callable[[], None],
) -> None:
    """Offer the allowed values of *spec*, marking the one it currently holds."""
    options: tuple[SelectOption[SettingValue], ...] = tuple(
        SelectOption(value=value, title=str(value)) for value in spec.allowed_values
    )

    def chosen(outcome: SelectOutcome[SettingValue] | None) -> None:
        """Commit the picked value, then return to the list either way."""
        if outcome is not None and outcome.kind is SelectOutcomeKind.SINGLE and outcome.value is not None:
            _commit(state, service, spec, outcome.value)
        on_committed()

    open_dialog(app, state, SelectDialog(title=spec.label, options=options, current=current), chosen)


def _open_text(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    current: SettingValue,
    on_committed: Callable[[], None],
) -> None:
    """Edit one text value, keeping the row unchanged on an empty result."""
    from anishift.config.field_catalog import SettingValueType  # noqa: PLC0415

    optional: bool = spec.value_type is SettingValueType.OPTIONAL_STRING
    text: str = current if isinstance(current, str) else ""

    def keep(value: str | None) -> None:
        """Commit a typed value, then return to the list either way."""
        if value is not None:
            _commit(state, service, spec, value)
        on_committed()

    open_dialog(
        app,
        state,
        PromptDialog(title=spec.label, value=text, optional=optional, validate=_text_validator(spec)),
        keep,
    )


def _open_number(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    current: SettingValue,
    on_committed: Callable[[], None],
) -> None:
    """Edit one number inside its declared range, keeping empty as no change."""
    from anishift.config.field_catalog import SettingValueType  # noqa: PLC0415

    whole: bool = spec.value_type in {SettingValueType.INTEGER, SettingValueType.OPTIONAL_INTEGER}
    optional: bool = spec.value_type in {SettingValueType.OPTIONAL_INTEGER, SettingValueType.OPTIONAL_FLOAT}
    number: int | float | None = (
        current if isinstance(current, (int, float)) and not isinstance(current, bool) else None
    )

    def keep(value: int | float | None) -> None:
        """Commit a typed number, then return to the list either way."""
        if value is not None:
            _commit(state, service, spec, value)
        on_committed()

    open_dialog(
        app,
        state,
        NumberDialog(
            title=spec.label,
            value=number,
            kind=NumberKind.WHOLE if whole else NumberKind.DECIMAL,
            minimum=spec.minimum,
            maximum=spec.maximum,
            optional=optional,
        ),
        keep,
    )


def _open_multi(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    current: SettingValue,
    on_committed: Callable[[], None],
) -> None:
    """Toggle the members of one string set, committing the whole selection."""
    chosen_set: frozenset[str] = current if isinstance(current, frozenset) else frozenset()
    options: tuple[SelectOption[SettingValue], ...] = tuple(
        SelectOption(value=value, title=str(value)) for value in spec.allowed_values
    )
    selected: tuple[int, ...] = tuple(index for index, value in enumerate(spec.allowed_values) if value in chosen_set)

    def chosen(outcome: SelectOutcome[SettingValue] | None) -> None:
        """Commit the whole selection, then return to the list either way."""
        if outcome is not None and outcome.kind is SelectOutcomeKind.MULTI:
            _commit(state, service, spec, frozenset(str(value) for value in outcome.values))
        on_committed()

    open_dialog(app, state, SelectDialog(title=spec.label, options=options, multi=True, selected=selected), chosen)


def _open_reorder(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    current: SettingValue,
    on_committed: Callable[[], None],
) -> None:
    """Rearrange one ordered list, committing or rolling it back as a whole."""
    items: tuple[str, ...] = tuple(str(item) for item in current) if isinstance(current, tuple) else ()
    candidates: tuple[str, ...] = tuple(str(value) for value in spec.allowed_values)

    def keep(result: tuple[str, ...] | None) -> None:
        """Commit the new order, then return to the list either way."""
        if result is not None:
            _commit(state, service, spec, tuple(result))
        on_committed()

    open_dialog(app, state, ReorderDialog(title=spec.label, items=items, candidates=candidates), keep)


def _open_object_wizard(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    current: SettingValue,
    on_committed: Callable[[], None],
) -> None:
    """List the object items, offering add, edit and remove over the whole list."""
    voices: tuple[Any, ...] = current if isinstance(current, tuple) else ()
    options: tuple[SelectOption[int], ...] = tuple(
        SelectOption(
            value=index,
            title=str(getattr(voice, "alias", voice)),
            description=str(getattr(voice, "label", "")),
        )
        for index, voice in enumerate(voices)
    )
    actions: tuple[SelectAction, ...] = (
        SelectAction(_OBJECT_ADD, _OBJECT_ADD_KEY, OBJECT_ADD_LABEL),
        SelectAction(_OBJECT_REMOVE, _OBJECT_REMOVE_KEY, OBJECT_REMOVE_LABEL),
    )

    def chosen(outcome: SelectOutcome[int] | None) -> None:
        """Route the wizard decision to add, edit, remove or back to the list."""
        _react_wizard(app, state, service, spec, voices, outcome, on_committed)

    open_dialog(app, state, SelectDialog(title=spec.label, options=options, actions=actions), chosen)


def _react_wizard(  # noqa: PLR0913 - the wizard decision needs the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    voices: tuple[Any, ...],
    outcome: SelectOutcome[int] | None,
    on_committed: Callable[[], None],
) -> None:
    """Open the add, edit or remove flow for one wizard outcome."""
    if outcome is None or outcome.kind is SelectOutcomeKind.CANCELLED:
        on_committed()
        return
    if outcome.kind is SelectOutcomeKind.ACTION and outcome.action == _OBJECT_ADD:
        app.call_next(_voice_form, app, state, service, spec, voices, None, on_committed)
        return
    if outcome.kind is SelectOutcomeKind.ACTION and outcome.action == _OBJECT_REMOVE:
        _remove_voice(app, state, service, spec, voices, outcome.value, on_committed)
        return
    if outcome.kind is SelectOutcomeKind.SINGLE and outcome.value is not None:
        app.call_next(_voice_form, app, state, service, spec, voices, outcome.value, on_committed)
        return
    on_committed()


def _voice_form(  # noqa: PLR0913 - one object item is built from its full context
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    voices: tuple[Any, ...],
    index: int | None,
    on_committed: Callable[[], None],
) -> None:
    """Prompt for every object field in turn, committing the finished item."""
    fields = spec.object_fields
    existing: Any | None = voices[index] if index is not None and 0 <= index < len(voices) else None

    def collect(values: list[str], position: int) -> None:
        """Gather one field, then move on or commit the whole list."""
        if position == len(fields):
            _commit_voices(app, state, service, spec, voices, index, values, on_committed)
            return
        field = fields[position]
        initial: str = "" if existing is None else str(getattr(existing, field.field_id, ""))

        def keep(text: str | None) -> None:
            """Keep the typed field, or abandon the whole form on cancel."""
            if text is None:
                on_committed()
                return
            app.call_next(collect, [*values, text], position + 1)

        open_dialog(app, state, PromptDialog(title=field.label, value=initial, hint=field.description), keep)

    collect([], 0)


def _commit_voices(  # noqa: PLR0913 - the whole edited list is committed at once
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    voices: tuple[Any, ...],
    index: int | None,
    values: list[str],
    on_committed: Callable[[], None],
) -> None:
    """Build the finished object item and commit the whole updated list."""
    from anishift.config.user_settings import CustomVoiceSetting  # noqa: PLC0415

    voice = CustomVoiceSetting(alias=values[0], label=values[1], voice_id=values[2])
    updated: list[Any] = list(voices)
    if index is None or not (0 <= index < len(updated)):
        updated.append(voice)
    else:
        updated[index] = voice
    _commit(state, service, spec, tuple(updated))
    on_committed()


def _remove_voice(  # noqa: PLR0913 - the whole edited list is committed at once
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    voices: tuple[Any, ...],
    index: int | None,
    on_committed: Callable[[], None],
) -> None:
    """Confirm and then drop one object item from the list."""
    if index is None or not (0 <= index < len(voices)):
        on_committed()
        return
    alias: str = str(getattr(voices[index], "alias", ""))

    def answered(confirmed: bool | None) -> None:
        """Drop the item on a yes, then return to the list either way."""
        if confirmed:
            updated: tuple[Any, ...] = tuple(item for position, item in enumerate(voices) if position != index)
            _commit(state, service, spec, updated)
        on_committed()

    open_dialog(
        app,
        state,
        ConfirmDialog(title=OBJECT_REMOVE_TITLE, question=OBJECT_REMOVE_QUESTION.format(alias=alias)),
        answered,
    )


def _commit(state: SessionState, service: AppService, spec: SettingSpec, value: SettingValue) -> None:
    """Persist one setting, surfacing a rejected value instead of crashing."""
    from anishift.errors import ConfigError  # noqa: PLC0415

    try:
        service.update_setting(spec.setting_id, value)
    except (ConfigError, ValueError, TypeError) as error:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=_error_text(error))


def _text_validator(spec: SettingSpec) -> Validator:
    """Return a check that rejects text the spec's own format refuses."""

    def check(text: str) -> str | None:
        """Report the invalid-value reason, or nothing when the text passes."""
        try:
            spec.validate_value(text)
        except ValueError, TypeError:
            return SETTING_INVALID_VALUE
        return None

    return check


def _error_text(error: Exception) -> str:
    """Return the redacted message an application error carries."""
    context = getattr(error, "context", None)
    return context.message if context is not None else str(error)
