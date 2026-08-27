"""The automatic route: the preset surface and the one default run it resolves."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from textual.widgets import Static

from anishift.application import ready_group_ids
from anishift.application.intents import (
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductKind,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.select import SelectAction, SelectDialog, SelectOption, SelectOutcomeKind
from anishift.tui.dialogs.value import PromptDialog
from anishift.tui.settings.editors import EditorKind, editor_for, value_summary
from anishift.tui.state import FeedbackLevel, UiFeedback
from anishift.tui.strings import (
    AUTO_DEFAULT_MARKER,
    AUTO_DEFAULT_REFUSED,
    AUTO_DEFAULT_SAVED,
    AUTO_EDIT_LABEL,
    AUTO_FIELD_REFUSED,
    AUTO_FIELDS_TITLE,
    AUTO_GROUPS_LABEL,
    AUTO_LABEL_GAP,
    AUTO_NO_CHANGES,
    AUTO_NO_GROUPS,
    AUTO_NO_PRESET,
    AUTO_NO_WORKSPACE,
    AUTO_PRESET_LABEL,
    AUTO_PRESET_SAVED,
    AUTO_PROBLEMS_LABEL,
    AUTO_PRODUCTS_LABEL,
    AUTO_READY_GROUPS,
    AUTO_RESET_LABEL,
    AUTO_SAVE_LABEL,
    AUTO_UNSAVED_MARKER,
    COMMAND_AUTO_TITLE,
    SETTING_UNSET,
)
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from textual.app import App

    from anishift.application import AppService, AutoPreset, AutoPresetDraft, InspectedWorkspace
    from anishift.config.field_catalog import SettingCondition, SettingSpec, SettingValue
    from anishift.tui.auto_trigger import AutoVerdict
    from anishift.tui.dialogs.select import SelectOutcome
    from anishift.tui.state import SessionState

__all__ = [
    "AUTO_ID",
    "AutoRequest",
    "AutoSession",
    "AutoView",
    "auto_body",
    "open_auto_presets",
    "resolve_request",
]

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

AUTO_ID: Final[str] = "auto-view"
"""Id of the one surface the work area shows the automatic route on."""

EDIT_ACTION: Final[str] = "edit_fields"
"""Action name of the key that opens the fields of the highlighted preset."""

SAVE_ACTION: Final[str] = "save_preset"
"""Action name of the key that stores the draft of the highlighted preset."""

RESET_ACTION: Final[str] = "reset_preset"
"""Action name of the key that drops the draft of the highlighted preset."""

EDIT_KEY: Final[str] = "ctrl+e"
"""Key opening the field list, kept off the letters the filter box consumes."""

SAVE_KEY: Final[str] = "ctrl+s"
"""Key storing the draft, kept off the letters the filter box consumes."""

RESET_KEY: Final[str] = "ctrl+r"
"""Key dropping the draft, kept off the letters the filter box consumes."""

_PROBLEM_LIMIT: Final[int] = 4
"""Problems of the last plan the route lists before it stops."""

_FIELD_READERS: Final[Mapping[str, Callable[[AutoPresetDraft], SettingValue]]] = MappingProxyType(
    {
        "requested_products": lambda draft: frozenset(kind.value for kind in draft.products.requested_products),
        "burn_subtitle_product": lambda draft: draft.products.burn_subtitle_product.value,
        "mkv_tracks": lambda draft: frozenset(track.value for track in draft.products.mkv_tracks),
        "mp4_audio_source": lambda draft: draft.products.mp4_audio_source.value,
        "subtitle_source_policy": lambda draft: draft.subtitle_source_policy.value,
        "translation_action": lambda draft: draft.translation_action.value,
        "source_subtitle_language": lambda draft: draft.source_subtitle_language,
        "subtitle_output_format": lambda draft: draft.subtitle_output_format.value,
    },
)
"""The value every automatic-preset field holds, keyed by its setting id."""

_FIELD_WRITERS: Final[Mapping[str, Callable[[AutoPresetDraft, SettingValue], AutoPresetDraft]]] = MappingProxyType(
    {
        "requested_products": lambda draft, value: replace(
            draft,
            products=replace(
                draft.products,
                requested_products=frozenset(ProductKind(item) for item in _as_set(value)),
            ),
        ),
        "burn_subtitle_product": lambda draft, value: replace(
            draft,
            products=replace(draft.products, burn_subtitle_product=BurnSubtitleProduct(_as_text(value))),
        ),
        "mkv_tracks": lambda draft, value: replace(
            draft,
            products=replace(draft.products, mkv_tracks=frozenset(MkvTrackProduct(item) for item in _as_set(value))),
        ),
        "mp4_audio_source": lambda draft, value: replace(
            draft,
            products=replace(draft.products, mp4_audio_source=Mp4AudioSource(_as_text(value))),
        ),
        "subtitle_source_policy": lambda draft, value: replace(
            draft,
            subtitle_source_policy=SubtitleSourcePolicy(_as_text(value)),
        ),
        "translation_action": lambda draft, value: replace(
            draft,
            translation_action=TranslationAction(_as_text(value)),
        ),
        "source_subtitle_language": lambda draft, value: replace(
            draft,
            source_subtitle_language=_as_optional_text(value),
        ),
        "subtitle_output_format": lambda draft, value: replace(
            draft,
            subtitle_output_format=SubtitleOutputFormat(_as_text(value)),
        ),
    },
)
"""The draft one changed automatic-preset field produces, keyed by its setting id."""


@dataclass(slots=True)
class AutoSession:
    """What the shell holds about the automatic route between two renders."""

    presets: tuple[AutoPreset, ...] = ()
    verdict: AutoVerdict | None = None
    generation: int | None = None
    accepted_artifact_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class AutoRequest:
    """One resolved default Auto run, or the reason the session cannot start one."""

    group_ids: tuple[str, ...] = ()
    preset: AutoPreset | None = None
    refusal: str = ""


def resolve_request(state: SessionState, service: AppService, session: AutoSession) -> AutoRequest:
    """Resolve the groups and the stored preset one empty Enter runs, or its refusal."""
    if state.workspace is None:
        return AutoRequest(refusal=AUTO_NO_WORKSPACE)
    group_ids: tuple[str, ...] = run_group_ids(state)
    if not group_ids:
        return AutoRequest(refusal=AUTO_NO_GROUPS)
    refresh_presets(state, service, session)
    preset: AutoPreset | None = default_preset(state, session)
    if preset is None:
        return AutoRequest(refusal=AUTO_NO_PRESET)
    logger.info("Auto request resolved", groups=len(group_ids))
    return AutoRequest(group_ids=group_ids, preset=preset)


def run_group_ids(state: SessionState) -> tuple[str, ...]:
    """Return the selected groups, or every ready group when nothing is selected."""
    workspace: InspectedWorkspace | None = state.workspace
    if workspace is None:
        return ()
    selected: tuple[str, ...] = tuple(
        group.group_id for group in workspace.groups if group.group_id in state.selected_group_ids
    )
    if selected:
        return selected
    return ready_group_ids(workspace.groups)


def refresh_presets(state: SessionState, service: AppService, session: AutoSession) -> None:
    """Read every stored preset and the default the preset file names."""
    session.presets = service.list_presets()
    state.default_preset_id = _stored_default_id(session, state.default_preset_id)


def default_preset(state: SessionState, session: AutoSession) -> AutoPreset | None:
    """Return the preset an empty Enter would run, or ``None`` while none is stored."""
    for preset in session.presets:
        if preset.preset_id == state.default_preset_id:
            return preset
    return session.presets[0] if session.presets else None


def choose_default(state: SessionState, preset_id: str) -> bool:
    """Store *preset_id* as the default of the preset file, atomically and durably."""
    from anishift.config.presets import load_presets, save_presets  # noqa: PLC0415 - lazy configuration boundary

    stored = load_presets()
    if preset_id not in {preset.preset_id for preset in stored.presets}:
        logger.warning("Default preset refused, the preset file does not hold it")
        return False
    try:
        save_presets(replace(stored, default_preset_id=preset_id))
    except OSError:
        logger.warning("Default preset could not be stored")
        return False
    state.default_preset_id = preset_id
    logger.info("Default preset stored")
    return True


def auto_body(state: SessionState, session: AutoSession) -> str:
    """Return the summary of the preset, the groups and the last plan of this route."""
    preset: AutoPreset | None = default_preset(state, session)
    draft: AutoPresetDraft | None = _draft_of(state, preset)
    rows: list[tuple[str, str]] = [
        (AUTO_PRESET_LABEL, _preset_text(state, preset, draft)),
        (AUTO_PRODUCTS_LABEL, _products_text(preset, draft)),
        (AUTO_GROUPS_LABEL, _groups_text(state)),
    ]
    verdict: AutoVerdict | None = session.verdict
    problems: tuple[str, ...] = () if verdict is None else verdict.problems[:_PROBLEM_LIMIT]
    rows.extend((AUTO_PROBLEMS_LABEL if index == 0 else "", problem) for index, problem in enumerate(problems))
    width: int = max(len(label) for label, _ in rows)
    return "\n".join(f"{label.ljust(width)}{AUTO_LABEL_GAP}{value}" for label, value in rows)


class AutoView(Static):
    """Show the preset one default run would use and what the last plan reported."""

    def __init__(self) -> None:
        """Build the one surface the work area shows the automatic route on."""
        super().__init__(id=AUTO_ID)

    def show(self, state: SessionState, session: AutoSession) -> None:
        """Redraw the automatic summary from the state and the held route facts."""
        self.update(auto_body(state, session))


def open_auto_presets(
    app: App[Any],
    state: SessionState,
    service: AppService,
    session: AutoSession,
    *,
    highlight_id: str | None = None,
) -> None:
    """Offer every stored preset, its default marker and the keys that edit and store it."""
    refresh_presets(state, service, session)
    options: tuple[SelectOption[str], ...] = tuple(
        SelectOption(
            value=preset.preset_id,
            title=preset.name,
            description=_products_text(preset, _draft_of(state, preset)),
            footer=_preset_footer(state, preset),
        )
        for preset in session.presets
    )
    actions: tuple[SelectAction, ...] = (
        SelectAction(EDIT_ACTION, EDIT_KEY, AUTO_EDIT_LABEL),
        SelectAction(SAVE_ACTION, SAVE_KEY, AUTO_SAVE_LABEL),
        SelectAction(RESET_ACTION, RESET_KEY, AUTO_RESET_LABEL),
    )
    highlight: int | None = next(
        (index for index, preset in enumerate(session.presets) if preset.preset_id == highlight_id),
        None,
    )

    def chosen(outcome: SelectOutcome[str] | None) -> None:
        """Route the picked row or the pressed key once the list left the stack."""
        _react_preset(app, state, service, session, outcome)

    open_dialog(
        app,
        state,
        SelectDialog(
            title=COMMAND_AUTO_TITLE,
            options=options,
            current=state.default_preset_id,
            actions=actions,
            initial_highlight=highlight,
        ),
        chosen,
    )


def _react_preset(
    app: App[Any],
    state: SessionState,
    service: AppService,
    session: AutoSession,
    outcome: SelectOutcome[str] | None,
) -> None:
    """Set the default, edit, save or reset one preset, never starting anything."""
    if outcome is None or outcome.kind is SelectOutcomeKind.CANCELLED or outcome.value is None:
        return
    preset_id: str = outcome.value
    if outcome.kind is SelectOutcomeKind.ACTION:
        _act_on_preset(app, state, service, session, outcome.action, preset_id)
        return
    if outcome.kind is SelectOutcomeKind.SINGLE:
        _set_default(state, preset_id)
        _reopen(app, state, service, session, preset_id)


def _act_on_preset(  # noqa: PLR0913 - one router threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    session: AutoSession,
    action: str,
    preset_id: str,
) -> None:
    """Open the fields of one preset, store its draft or drop every unsaved change."""
    if action == EDIT_ACTION:
        app.call_next(open_preset_fields, app, state, service, session, preset_id)
        return
    if action == SAVE_ACTION:
        _save_draft(state, service, preset_id)
    elif action == RESET_ACTION:
        _reset_draft(state, preset_id)
    _reopen(app, state, service, session, preset_id)


def _set_default(state: SessionState, preset_id: str) -> None:
    """Store one chosen default preset, or report that the file refused it."""
    if not choose_default(state, preset_id):
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=AUTO_DEFAULT_REFUSED)
        return
    state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=AUTO_DEFAULT_SAVED.format(name=preset_id))


def _save_draft(state: SessionState, service: AppService, preset_id: str) -> None:
    """Validate and persist the draft of *preset_id* through the one facade."""
    from anishift.errors import ConfigError, PlanningError  # noqa: PLC0415 - lazy configuration boundary

    draft: AutoPresetDraft | None = state.auto_draft
    if draft is None or draft.preset_id != preset_id:
        state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=AUTO_NO_CHANGES)
        return
    try:
        stored = service.save_preset(draft)
    except ConfigError, PlanningError, ValueError, TypeError:
        logger.warning("Preset draft refused")
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=AUTO_FIELD_REFUSED)
        return
    state.auto_draft = None
    state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=AUTO_PRESET_SAVED.format(name=stored.name))


def _reset_draft(state: SessionState, preset_id: str) -> None:
    """Drop every unsaved change the draft of *preset_id* holds."""
    draft: AutoPresetDraft | None = state.auto_draft
    if draft is None or draft.preset_id != preset_id:
        state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=AUTO_NO_CHANGES)
        return
    state.auto_draft = None


def open_preset_fields(  # noqa: PLR0913 - one field list threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    session: AutoSession,
    preset_id: str,
    *,
    highlight_id: str | None = None,
) -> None:
    """Offer every active field of one preset draft, each with the value it holds."""
    draft: AutoPresetDraft | None = _editable_draft(state, session, preset_id)
    if draft is None:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=AUTO_NO_PRESET)
        return
    specs: tuple[SettingSpec, ...] = preset_specs(service, draft)
    options: tuple[SelectOption[str], ...] = tuple(
        SelectOption(
            value=spec.setting_id,
            title=spec.label,
            description=spec.description,
            footer=value_summary(_field_value(draft, spec.setting_id)),
        )
        for spec in specs
    )
    highlight: int | None = next(
        (index for index, spec in enumerate(specs) if spec.setting_id == highlight_id),
        None,
    )

    def chosen(outcome: SelectOutcome[str] | None) -> None:
        """Open the editor of the picked field, or go back to the preset list."""
        _react_field(app, state, service, session, specs, preset_id, outcome)

    open_dialog(
        app,
        state,
        SelectDialog(title=AUTO_FIELDS_TITLE, options=options, initial_highlight=highlight),
        chosen,
    )


def preset_specs(service: AppService, draft: AutoPresetDraft) -> tuple[SettingSpec, ...]:
    """Return every automatic-preset field the draft's own choices keep active."""
    from anishift.config.field_catalog import SettingScope  # noqa: PLC0415 - lazy configuration boundary

    return tuple(
        spec
        for spec in service.settings_catalog(service.settings_snapshot())
        if spec.scope is SettingScope.AUTO_PRESET and _spec_is_active(draft, spec)
    )


def _react_field(  # noqa: PLR0913 - one router threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    session: AutoSession,
    specs: tuple[SettingSpec, ...],
    preset_id: str,
    outcome: SelectOutcome[str] | None,
) -> None:
    """Open the editor of one field, or leave the fields for the preset list."""
    if outcome is None or outcome.kind is not SelectOutcomeKind.SINGLE or outcome.value is None:
        _reopen(app, state, service, session, preset_id)
        return
    spec: SettingSpec | None = next((item for item in specs if item.setting_id == outcome.value), None)
    if spec is None:
        _reopen(app, state, service, session, preset_id)
        return
    app.call_next(_open_field_editor, app, state, service, session, spec, preset_id)


def _open_field_editor(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    session: AutoSession,
    spec: SettingSpec,
    preset_id: str,
) -> None:
    """Change one field of the draft through the editor its value type asks for."""
    draft: AutoPresetDraft | None = _editable_draft(state, session, preset_id)
    if draft is None:
        return
    current: SettingValue = _field_value(draft, spec.setting_id)

    def reopen() -> None:
        """Show the field list again on the row that was edited."""
        app.call_next(open_preset_fields, app, state, service, session, preset_id, highlight_id=spec.setting_id)

    def committed(value: SettingValue) -> None:
        """Keep one accepted value in the draft, then return to the field list."""
        _commit_field(state, draft, spec, value)
        reopen()

    kind: EditorKind = editor_for(spec)
    if kind is EditorKind.SELECT:
        _open_choice(app, state, spec, current, committed, reopen)
        return
    if kind is EditorKind.MULTI_SELECT:
        _open_choices(app, state, spec, current, committed, reopen)
        return
    if kind in {EditorKind.TEXT, EditorKind.LONG_TEXT}:
        _open_text(app, state, spec, current, committed, reopen)
        return
    state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=AUTO_FIELD_REFUSED)
    reopen()


def _open_choice(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    spec: SettingSpec,
    current: SettingValue,
    committed: Callable[[SettingValue], None],
    reopen: Callable[[], None],
) -> None:
    """Offer the allowed values of *spec*, marking the one the draft holds."""
    options: tuple[SelectOption[SettingValue], ...] = tuple(
        SelectOption(value=value, title=str(value)) for value in spec.allowed_values
    )

    def chosen(outcome: SelectOutcome[SettingValue] | None) -> None:
        """Keep the picked value, then return to the field list either way."""
        if outcome is not None and outcome.kind is SelectOutcomeKind.SINGLE and outcome.value is not None:
            committed(outcome.value)
            return
        reopen()

    open_dialog(app, state, SelectDialog(title=spec.label, options=options, current=current), chosen)


def _open_choices(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    spec: SettingSpec,
    current: SettingValue,
    committed: Callable[[SettingValue], None],
    reopen: Callable[[], None],
) -> None:
    """Toggle the members of one set field, committing the whole selection."""
    held: frozenset[str] = _as_set(current)
    options: tuple[SelectOption[SettingValue], ...] = tuple(
        SelectOption(value=value, title=str(value)) for value in spec.allowed_values
    )
    selected: tuple[int, ...] = tuple(index for index, value in enumerate(spec.allowed_values) if value in held)

    def chosen(outcome: SelectOutcome[SettingValue] | None) -> None:
        """Keep the whole selection, then return to the field list either way."""
        if outcome is not None and outcome.kind is SelectOutcomeKind.MULTI:
            committed(frozenset(str(value) for value in outcome.values))
            return
        reopen()

    open_dialog(
        app,
        state,
        SelectDialog(title=spec.label, options=options, multi=True, selected=selected),
        chosen,
    )


def _open_text(  # noqa: PLR0913 - one editor threads the full editing context
    app: App[Any],
    state: SessionState,
    spec: SettingSpec,
    current: SettingValue,
    committed: Callable[[SettingValue], None],
    reopen: Callable[[], None],
) -> None:
    """Edit one optional text field, where an empty answer clears the value."""
    text: str = current if isinstance(current, str) else ""

    def keep(value: str | None) -> None:
        """Keep the typed text, then return to the field list either way."""
        if value is not None:
            committed(value)
            return
        reopen()

    open_dialog(app, state, PromptDialog(title=spec.label, value=text, optional=True), keep)


def _commit_field(state: SessionState, draft: AutoPresetDraft, spec: SettingSpec, value: SettingValue) -> None:
    """Keep one changed field in the draft, surfacing a value the preset refuses."""
    writer: Callable[[AutoPresetDraft, SettingValue], AutoPresetDraft] | None = _FIELD_WRITERS.get(spec.setting_id)
    if writer is None:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=AUTO_FIELD_REFUSED)
        return
    try:
        state.auto_draft = writer(draft, value)
    except ValueError, TypeError:
        logger.warning("Preset field value refused", setting=spec.setting_id)
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=AUTO_FIELD_REFUSED)


def _editable_draft(state: SessionState, session: AutoSession, preset_id: str) -> AutoPresetDraft | None:
    """Return the unsaved draft of *preset_id*, or the stored preset as one the caller may edit."""
    from anishift.application import AutoPresetDraft as Draft  # noqa: PLC0415 - lazy configuration boundary

    held: AutoPresetDraft | None = state.auto_draft
    if held is not None and held.preset_id == preset_id:
        return held
    stored: AutoPreset | None = next(
        (preset for preset in session.presets if preset.preset_id == preset_id),
        None,
    )
    if stored is None:
        return None
    return Draft(
        preset_id=stored.preset_id,
        name=stored.name,
        products=stored.products,
        subtitle_source_policy=stored.subtitle_source_policy,
        translation_action=stored.translation_action,
        source_subtitle_language=stored.source_subtitle_language,
        subtitle_output_format=stored.subtitle_output_format,
    )


def _reopen(app: App[Any], state: SessionState, service: AppService, session: AutoSession, preset_id: str) -> None:
    """Show the preset list again on the row that was acted on."""
    app.call_next(open_auto_presets, app, state, service, session, highlight_id=preset_id)


def _stored_default_id(session: AutoSession, current: str) -> str:
    """Return the default the preset file names, kept inside the presets the facade lists."""
    from anishift.config.presets import load_presets  # noqa: PLC0415 - lazy configuration boundary

    known: set[str] = {preset.preset_id for preset in session.presets}
    stored: str = load_presets().default_preset_id
    if stored in known:
        return stored
    if current in known:
        return current
    return session.presets[0].preset_id if session.presets else current


def _field_value(draft: AutoPresetDraft, setting_id: str) -> SettingValue:
    """Return the value one automatic-preset field holds in *draft*."""
    reader: Callable[[AutoPresetDraft], SettingValue] | None = _FIELD_READERS.get(setting_id)
    return None if reader is None else reader(draft)


def _spec_is_active(draft: AutoPresetDraft, spec: SettingSpec) -> bool:
    """Whether every condition *spec* depends on holds in this draft."""
    return all(_condition_holds(draft, condition) for condition in spec.depends_on)


def _condition_holds(draft: AutoPresetDraft, condition: SettingCondition) -> bool:
    """Whether the field one condition names holds a value the condition allows."""
    if condition.setting_id not in _FIELD_READERS:
        return False
    current: SettingValue = _field_value(draft, condition.setting_id)
    if isinstance(current, frozenset):
        return any(item in condition.allowed_values for item in current)
    return current in condition.allowed_values


def _draft_of(state: SessionState, preset: AutoPreset | None) -> AutoPresetDraft | None:
    """Return the draft the session holds for *preset*, or ``None`` when it holds none."""
    draft: AutoPresetDraft | None = state.auto_draft
    if preset is None or draft is None or draft.preset_id != preset.preset_id:
        return None
    return draft


def _preset_footer(state: SessionState, preset: AutoPreset) -> str:
    """Return the words marking one preset as the default and as unsaved."""
    marks: list[str] = []
    if preset.preset_id == state.default_preset_id:
        marks.append(AUTO_DEFAULT_MARKER)
    if _draft_of(state, preset) is not None:
        marks.append(AUTO_UNSAVED_MARKER)
    return AUTO_LABEL_GAP.join(marks)


def _preset_text(state: SessionState, preset: AutoPreset | None, draft: AutoPresetDraft | None) -> str:
    """Return the name of the preset a default run uses, marked when it is unsaved."""
    if preset is None:
        return AUTO_NO_PRESET
    if draft is None:
        return preset.name
    return f"{draft.name}{AUTO_LABEL_GAP}{AUTO_UNSAVED_MARKER}"


def _products_text(preset: AutoPreset | None, draft: AutoPresetDraft | None) -> str:
    """Return the products the preset or its draft asks for."""
    source: AutoPreset | AutoPresetDraft | None = draft if draft is not None else preset
    if source is None:
        return SETTING_UNSET
    return value_summary(frozenset(kind.value for kind in source.products.requested_products))


def _groups_text(state: SessionState) -> str:
    """Return how many inspected groups a default run would take."""
    workspace: InspectedWorkspace | None = state.workspace
    if workspace is None:
        return AUTO_NO_WORKSPACE
    return AUTO_READY_GROUPS.format(ready=len(run_group_ids(state)), total=len(workspace.groups))


def _as_set(value: SettingValue) -> frozenset[str]:
    """Return the string set *value* holds, or an empty one when it holds none."""
    return value if isinstance(value, frozenset) else frozenset()


def _as_text(value: SettingValue) -> str:
    """Return the text *value* holds, or an empty string when it holds none."""
    return value if isinstance(value, str) else ""


def _as_optional_text(value: SettingValue) -> str | None:
    """Return the text *value* holds, or ``None`` when it holds nothing usable."""
    return value if isinstance(value, str) and value else None
