"""The picker of the main model role, built from the local catalog alone."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from anishift.tui.dialogs.base import open_dialog, refuse_second_dialog
from anishift.tui.dialogs.select import SelectAction, SelectDialog, SelectOption, SelectOutcomeKind
from anishift.tui.state import FeedbackLevel, UiFeedback
from anishift.tui.strings import (
    MODEL_CATALOG_EMPTY,
    MODEL_CATALOG_UNUSABLE,
    MODEL_EXPERIMENTAL,
    MODEL_ISSUES_CATEGORY,
    MODEL_PICKER_TITLE,
    MODEL_REFRESH_LABEL,
    MODEL_ROW_SEPARATOR,
    MODEL_SAVED,
    MODEL_STATE_ERROR,
    MODEL_STATE_UNVERIFIED,
    MODEL_STATE_VERIFIED,
    MODEL_TIME_FORMAT,
    TRANSLATION_MODEL_SAVED,
    TRANSLATION_MODEL_TITLE,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from textual.app import App

    from anishift.application import AppService, ModelProbeResult
    from anishift.config.field_catalog import SettingSpec
    from anishift.config.model_catalog import CatalogIssue, ModelCatalog, ModelEntry, ProviderEntry
    from anishift.tui.dialogs.select import SelectOutcome
    from anishift.tui.state import SessionState

__all__ = [
    "AVAILABILITY_ATTRIBUTE",
    "CATALOG_PROVIDER",
    "NO_MODEL_VALUE",
    "PRIMARY_MODEL_SETTING_ID",
    "TRANSLATION_MODEL_SETTING_ID",
    "availability_text",
    "load_catalog",
    "model_options",
    "open_alias_selection",
    "open_model_picker",
]

# ── Constants ──────────────────────────────────────────────────────────────

PRIMARY_MODEL_SETTING_ID: Final[str] = "primary_model_alias"
"""The one setting this picker writes; no other model role is ever touched."""

TRANSLATION_MODEL_SETTING_ID: Final[str] = "llm_provider_model_id"
"""The translation model role, offered as a selection only for the catalog provider."""

CATALOG_PROVIDER: Final[str] = "palantir"
"""The one LLM provider whose model IDs come from the local catalog."""

NO_MODEL_VALUE: Final[str] = ""
"""Value of a row that reports a catalog state instead of offering a model."""

AVAILABILITY_ATTRIBUTE: Final[str] = "model_availability"
"""Name of the shell attribute holding the session availability answers."""

_REFRESH_ACTION: Final[str] = "reload_catalog"
"""Action name of the key that reads the catalog file again."""

_REFRESH_KEY: Final[str] = "ctrl+r"
"""Key that reads the catalog file again, kept off the filter box letters."""


def availability_text(result: ModelProbeResult | None) -> str:
    """Return the session availability of one alias as text, never as a colour."""
    from anishift.application import ModelAvailability  # noqa: PLC0415

    if result is None or result.availability is ModelAvailability.UNVERIFIED:
        return MODEL_STATE_UNVERIFIED
    if result.availability is ModelAvailability.VERIFIED:
        return MODEL_STATE_VERIFIED.format(time=result.checked_at.strftime(MODEL_TIME_FORMAT))
    return MODEL_STATE_ERROR.format(error_class=result.error_class)


def load_catalog(state: SessionState, service: AppService) -> ModelCatalog | None:
    """Read the catalog file again, reporting an unusable file instead of failing."""
    from anishift.config.model_catalog import ModelCatalogError  # noqa: PLC0415

    try:
        return service.model_catalog()
    except ModelCatalogError as error:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=_error_text(error))
        return None


def model_options(
    catalog: ModelCatalog | None,
    availability: Mapping[str, ModelProbeResult],
) -> tuple[SelectOption[str], ...]:
    """Return one row per configured alias, grouped by provider, warnings last."""
    if catalog is None:
        return (SelectOption(value=NO_MODEL_VALUE, title=MODEL_CATALOG_UNUSABLE, disabled=True),)
    entries: tuple[ModelEntry, ...] = tuple(sorted(catalog.models.values(), key=_by_provider))
    rows: list[SelectOption[str]] = [
        SelectOption(
            value=entry.alias,
            title=entry.alias,
            description=entry.label,
            footer=_row_footer(entry, catalog, availability.get(entry.alias)),
            category=entry.provider_id,
        )
        for entry in entries
    ]
    if not rows:
        rows.append(SelectOption(value=NO_MODEL_VALUE, title=MODEL_CATALOG_EMPTY, disabled=True))
    rows.extend(_issue_rows(catalog.issues))
    return tuple(rows)


def open_model_picker(
    app: App[Any],
    state: SessionState,
    service: AppService,
    availability: Mapping[str, ModelProbeResult],
) -> None:
    """Offer every configured alias and change the main model role alone."""
    if refuse_second_dialog(app, state):
        return
    catalog: ModelCatalog | None = load_catalog(state, service)
    current: str = service.settings_snapshot().primary_model_alias

    def chosen(outcome: SelectOutcome[str] | None) -> None:
        """Save a confirmed alias, or read the catalog file again."""
        _react(app, state, service, availability, outcome)

    open_dialog(
        app,
        state,
        SelectDialog(
            title=MODEL_PICKER_TITLE,
            options=model_options(catalog, availability),
            current=current or None,
            actions=(SelectAction(_REFRESH_ACTION, _REFRESH_KEY, MODEL_REFRESH_LABEL),),
        ),
        chosen,
    )


def open_alias_selection(
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    reopen: Callable[[], None],
) -> bool:
    """Offer the catalog aliases for the translation model role, or refuse the row."""
    draft: Any = service.settings_snapshot()
    if spec.setting_id != TRANSLATION_MODEL_SETTING_ID or draft.llm_provider != CATALOG_PROVIDER:
        return False
    if refuse_second_dialog(app, state):
        return True
    catalog: ModelCatalog | None = load_catalog(state, service)
    current: str = str(draft.llm_provider_model_id)

    def chosen(outcome: SelectOutcome[str] | None) -> None:
        """Save a confirmed alias, then show the translation panel again."""
        if outcome is not None and outcome.kind is SelectOutcomeKind.SINGLE and outcome.value:
            _save(state, service, TRANSLATION_MODEL_SETTING_ID, outcome.value, TRANSLATION_MODEL_SAVED)
        reopen()

    open_dialog(
        app,
        state,
        SelectDialog(
            title=TRANSLATION_MODEL_TITLE,
            options=model_options(catalog, _availability_of(app)),
            current=current or None,
        ),
        chosen,
    )
    return True


def _availability_of(app: App[Any]) -> Mapping[str, ModelProbeResult]:
    """Return the session availability the shell owns, empty for any other host."""
    answers: Any = getattr(app, AVAILABILITY_ATTRIBUTE, None)
    return answers if isinstance(answers, dict) else {}


def _react(
    app: App[Any],
    state: SessionState,
    service: AppService,
    availability: Mapping[str, ModelProbeResult],
    outcome: SelectOutcome[str] | None,
) -> None:
    """Route one picker outcome to a save, to a reload, or to nothing at all."""
    if outcome is None or outcome.kind is SelectOutcomeKind.CANCELLED:
        return
    if outcome.kind is SelectOutcomeKind.ACTION and outcome.action == _REFRESH_ACTION:
        app.call_next(open_model_picker, app, state, service, availability)
        return
    if outcome.kind is SelectOutcomeKind.SINGLE and outcome.value:
        _save(state, service, PRIMARY_MODEL_SETTING_ID, outcome.value, MODEL_SAVED)


def _save(state: SessionState, service: AppService, setting_id: str, alias: str, saved: str) -> None:
    """Persist one model role, surfacing a refused alias as feedback."""
    from anishift.errors import ConfigError  # noqa: PLC0415

    try:
        service.update_setting(setting_id, alias)
    except (ConfigError, ValueError, TypeError) as error:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=_error_text(error))
        return
    state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=saved.format(alias=alias))


def _by_provider(entry: ModelEntry) -> tuple[str, str]:
    """Sort key keeping the aliases of one provider together and in order."""
    return (entry.provider_id, entry.alias)


def _row_footer(entry: ModelEntry, catalog: ModelCatalog, result: ModelProbeResult | None) -> str:
    """Return the provider, the protocol and the session state of one row."""
    provider: ProviderEntry | None = catalog.providers.get(entry.provider_id)
    parts: list[str] = [entry.provider_id]
    if provider is not None:
        parts.append(str(provider.protocol))
    parts.append(availability_text(result))
    if entry.experimental:
        parts.append(MODEL_EXPERIMENTAL)
    return MODEL_ROW_SEPARATOR.join(parts)


def _issue_rows(issues: tuple[CatalogIssue, ...]) -> tuple[SelectOption[str], ...]:
    """Return one unselectable row per rejected entry, so none of them vanishes."""
    return tuple(
        SelectOption(
            value=NO_MODEL_VALUE,
            title=issue.key or issue.section,
            description=issue.message,
            category=MODEL_ISSUES_CATEGORY,
            disabled=True,
        )
        for issue in issues
    )


def _error_text(error: Exception) -> str:
    """Return the redacted message an application error carries."""
    context: Any = getattr(error, "context", None)
    return str(context.message) if context is not None else str(error)
