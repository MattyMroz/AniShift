"""The representative speech settings and the one dialog flow that edits them."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.select import SelectDialog, SelectOption, SelectOutcome, SelectOutcomeKind
from anishift.tui.dialogs.value import NumberDialog, NumberKind, toggle_boolean
from anishift.tui.strings import (
    COMMAND_TTS_TITLE,
    SETTING_BOOST_DESCRIPTION,
    SETTING_BOOST_TITLE,
    SETTING_CONCURRENCY_DESCRIPTION,
    SETTING_CONCURRENCY_TITLE,
    SETTING_ENGINE_DESCRIPTION,
    SETTING_ENGINE_TITLE,
    SETTING_GAIN_DESCRIPTION,
    SETTING_GAIN_TITLE,
    SETTING_RETRIES_DESCRIPTION,
    SETTING_RETRIES_TITLE,
    SETTING_TEMPO_DESCRIPTION,
    SETTING_TEMPO_TITLE,
    SETTINGS_OFF,
    SETTINGS_ON,
    TTS_ENGINE_EDGE,
    TTS_ENGINE_ELEVENBYTES,
    TTS_ENGINE_ELEVENLABS,
    TTS_ENGINE_SAPI,
)

if TYPE_CHECKING:
    from textual.app import App

    from anishift.tui.state import SessionState

__all__ = [
    "FieldKind",
    "SettingField",
    "open_speech_panel",
    "speech_fields",
    "speech_values",
    "value_text",
]


class FieldKind(StrEnum):
    """Editor one setting field is changed through."""

    CHOICE = "choice"
    NUMBER = "number"
    TOGGLE = "toggle"


@dataclass(frozen=True, slots=True)
class SettingField:
    """One editable setting, the value it starts on and the editor it opens."""

    name: str
    title: str
    description: str
    kind: FieldKind
    default: object
    choices: tuple[str, ...] = ()
    number_kind: NumberKind = NumberKind.DECIMAL
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


def value_text(value: object) -> str:
    """Return the text one row shows for the value it currently holds."""
    if isinstance(value, bool):
        return SETTINGS_ON if value else SETTINGS_OFF
    if isinstance(value, int | float):
        return str(int(value)) if float(value).is_integer() else str(value)
    return str(value)


def speech_fields() -> tuple[SettingField, ...]:
    """Return the representative speech fields the speech surface offers."""
    return (
        SettingField(
            name="tts_engine",
            title=SETTING_ENGINE_TITLE,
            description=SETTING_ENGINE_DESCRIPTION,
            kind=FieldKind.CHOICE,
            default=TTS_ENGINE_ELEVENBYTES,
            choices=(TTS_ENGINE_EDGE, TTS_ENGINE_ELEVENBYTES, TTS_ENGINE_ELEVENLABS, TTS_ENGINE_SAPI),
        ),
        SettingField(
            name="tts_profile.postprocess_tempo",
            title=SETTING_TEMPO_TITLE,
            description=SETTING_TEMPO_DESCRIPTION,
            kind=FieldKind.NUMBER,
            default=1.0,
            minimum=0.5,
            maximum=2.0,
            step=0.05,
        ),
        SettingField(
            name="tts_profile.voice_mix_offset_db",
            title=SETTING_GAIN_TITLE,
            description=SETTING_GAIN_DESCRIPTION,
            kind=FieldKind.NUMBER,
            default=0.0,
            step=0.5,
        ),
        SettingField(
            name="tts_profile.concurrency",
            title=SETTING_CONCURRENCY_TITLE,
            description=SETTING_CONCURRENCY_DESCRIPTION,
            kind=FieldKind.NUMBER,
            default=4,
            number_kind=NumberKind.WHOLE,
            minimum=1,
            maximum=100,
            step=1,
        ),
        SettingField(
            name="tts_max_retries",
            title=SETTING_RETRIES_TITLE,
            description=SETTING_RETRIES_DESCRIPTION,
            kind=FieldKind.NUMBER,
            default=3,
            number_kind=NumberKind.WHOLE,
            minimum=0,
            maximum=10,
            step=1,
        ),
        SettingField(
            name="tts_profile.engine_options.use_speaker_boost",
            title=SETTING_BOOST_TITLE,
            description=SETTING_BOOST_DESCRIPTION,
            kind=FieldKind.TOGGLE,
            default=True,
        ),
    )


def speech_values() -> dict[str, object]:
    """Return the value every speech field starts on."""
    return {field.name: field.default for field in speech_fields()}


def open_speech_panel(
    app: App[Any],
    state: SessionState,
    values: dict[str, object],
    *,
    highlight: int | None = None,
) -> None:
    """Offer every speech field, and show the list again on the one that was edited."""
    fields: tuple[SettingField, ...] = speech_fields()

    def edit(outcome: SelectOutcome[str] | None) -> None:
        """Open the editor of the picked field, once the list left the stack."""
        if outcome is None or outcome.kind is not SelectOutcomeKind.SINGLE or outcome.value is None:
            return
        index: int = next(position for position, field in enumerate(fields) if field.name == outcome.value)
        app.call_next(_edit_field, app, state, fields, values, index)

    options: tuple[SelectOption[str], ...] = tuple(
        SelectOption(
            value=field.name,
            title=field.title,
            description=field.description,
            footer=value_text(values[field.name]),
        )
        for field in fields
    )
    panel: SelectDialog[str] = SelectDialog(
        title=COMMAND_TTS_TITLE,
        options=options,
        initial_highlight=highlight,
    )
    open_dialog(app, state, panel, edit)


def _edit_field(
    app: App[Any],
    state: SessionState,
    fields: tuple[SettingField, ...],
    values: dict[str, object],
    index: int,
) -> None:
    """Change the field at *index* through the editor its kind asks for."""
    field: SettingField = fields[index]
    current: object = values[field.name]

    def keep(value: object | None) -> None:
        """Write a confirmed value, then show the field list again on this field."""
        if value is not None:
            values[field.name] = value
        app.call_next(open_speech_panel, app, state, values, highlight=index)

    if field.kind is FieldKind.TOGGLE:
        values[field.name] = toggle_boolean(bool(current))
        keep(None)
        return
    if field.kind is FieldKind.CHOICE:
        choices: tuple[SelectOption[str], ...] = tuple(
            SelectOption(value=choice, title=choice) for choice in field.choices
        )
        dialog: SelectDialog[str] = SelectDialog(
            title=field.title,
            options=choices,
            current=str(current),
        )
        open_dialog(app, state, dialog, lambda outcome: keep(_picked(outcome)))
        return
    number: int | float | None = current if isinstance(current, int | float) else None
    open_dialog(
        app,
        state,
        NumberDialog(
            title=field.title,
            value=number,
            kind=field.number_kind,
            minimum=field.minimum,
            maximum=field.maximum,
            step=field.step,
        ),
        keep,
    )


def _picked(outcome: SelectOutcome[str] | None) -> str | None:
    """Return the one confirmed value of *outcome*, or ``None`` without one."""
    if outcome is None or outcome.kind is not SelectOutcomeKind.SINGLE:
        return None
    return outcome.value
