"""The connection surface: the enrollment address, the token and one confirmed test."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from anishift.tui.dialogs.base import open_dialog, refuse_second_dialog
from anishift.tui.dialogs.select import SelectAction, SelectDialog, SelectOption, SelectOutcomeKind
from anishift.tui.dialogs.value import ConfirmDialog
from anishift.tui.models.picker import load_catalog, model_options
from anishift.tui.settings.editors import open_field_editor
from anishift.tui.settings.secrets import open_secret_editor, open_secret_removal, secret_status
from anishift.tui.state import FeedbackLevel, UiFeedback
from anishift.tui.strings import (
    COMMAND_CONNECT_TITLE,
    CONNECT_ADDRESS_CONFIGURED,
    CONNECT_TEST_FAILED,
    CONNECT_TEST_QUESTION,
    CONNECT_TEST_TITLE,
    CONNECT_TEST_VERIFIED,
    CONNECT_TEST_WARNING,
    MISSING_SURFACE,
    MODEL_TEST_TITLE,
    SECRET_REMOVE_LABEL,
    SETTING_UNSET,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, MutableMapping

    from textual.app import App

    from anishift.application import AppService, ModelProbeResult, SettingsDraft
    from anishift.config.field_catalog import SettingSpec
    from anishift.config.model_catalog import ModelCatalog
    from anishift.tui.dialogs.select import SelectOutcome
    from anishift.tui.state import SessionState

__all__ = ["ADDRESS_SETTING_ID", "TOKEN_SETTING_ID", "open_connect_surface"]

# ── Constants ──────────────────────────────────────────────────────────────

ADDRESS_SETTING_ID: Final[str] = "palantir_enrollment_base_url"
"""Preference holding the enrollment address, which is edited but never shown."""

TOKEN_SETTING_ID: Final[str] = "palantir_token"  # noqa: S105
"""Environment secret holding the token, which is written but never read back."""

_ADDRESS_ROW: Final[str] = "address"
"""Value of the row that edits the enrollment address."""

_TOKEN_ROW: Final[str] = "token"  # noqa: S105
"""Value of the row that stores or clears the token."""

_TEST_ROW: Final[str] = "test"
"""Value of the row that runs one confirmed connection test."""

_TOKEN_CLEAR_ACTION: Final[str] = "clear_token"  # noqa: S105
"""Action name of the key that clears the stored token."""

_TOKEN_CLEAR_KEY: Final[str] = "ctrl+d"  # noqa: S105
"""Key that clears the stored token, kept off the filter box letters."""


def open_connect_surface(
    app: App[Any],
    state: SessionState,
    service: AppService,
    availability: MutableMapping[str, ModelProbeResult],
) -> None:
    """Summarise the connection without any secret and offer the confirmed test."""
    if refuse_second_dialog(app, state):
        return
    draft: SettingsDraft = service.settings_snapshot()
    address: SettingSpec | None = _spec(service, draft, ADDRESS_SETTING_ID)
    token: SettingSpec | None = _spec(service, draft, TOKEN_SETTING_ID)
    if address is None or token is None:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=MISSING_SURFACE)
        return
    statuses: Mapping[str, bool] = service.environment_statuses()
    options: tuple[SelectOption[str], ...] = (
        SelectOption(
            value=_ADDRESS_ROW,
            title=address.label,
            description=address.description,
            footer=CONNECT_ADDRESS_CONFIGURED if draft.palantir_enrollment_base_url.strip() else SETTING_UNSET,
        ),
        SelectOption(
            value=_TOKEN_ROW,
            title=token.label,
            description=token.description,
            footer=secret_status(configured=bool(statuses.get(TOKEN_SETTING_ID, False))),
        ),
        SelectOption(value=_TEST_ROW, title=CONNECT_TEST_TITLE, description=CONNECT_TEST_WARNING),
    )

    def chosen(outcome: SelectOutcome[str] | None) -> None:
        """Route the picked row to its editor, or to the confirmed test."""
        _react(app, state, service, availability, (address, token), outcome)

    open_dialog(
        app,
        state,
        SelectDialog(
            title=COMMAND_CONNECT_TITLE,
            options=options,
            actions=(SelectAction(_TOKEN_CLEAR_ACTION, _TOKEN_CLEAR_KEY, SECRET_REMOVE_LABEL),),
        ),
        chosen,
    )


def _react(  # noqa: PLR0913 - one surface routes its outcome with the full context
    app: App[Any],
    state: SessionState,
    service: AppService,
    availability: MutableMapping[str, ModelProbeResult],
    specs: tuple[SettingSpec, SettingSpec],
    outcome: SelectOutcome[str] | None,
) -> None:
    """Open the address editor, the token editor or the confirmation gate."""
    address: SettingSpec = specs[0]
    token: SettingSpec = specs[1]

    def reopen() -> None:
        """Show the connection surface again once the opened editor closed."""
        app.call_next(open_connect_surface, app, state, service, availability)

    if outcome is None or outcome.kind is SelectOutcomeKind.CANCELLED:
        return
    if outcome.kind is SelectOutcomeKind.ACTION:
        _clear_token(app, state, service, token, outcome.value, reopen)
        return
    if outcome.kind is not SelectOutcomeKind.SINGLE:
        return
    if outcome.value == _ADDRESS_ROW:
        app.call_next(open_field_editor, app, state, service, address, "", reopen)
        return
    if outcome.value == _TOKEN_ROW:
        app.call_next(open_secret_editor, app, state, service, token, reopen)
        return
    if outcome.value == _TEST_ROW:
        app.call_next(_open_test_picker, app, state, service, availability, reopen)


def _clear_token(  # noqa: PLR0913 - one removal needs the full editing context
    app: App[Any],
    state: SessionState,
    service: AppService,
    token: SettingSpec,
    row: str | None,
    reopen: Callable[[], None],
) -> None:
    """Confirm and clear the stored token, but only from its own row."""
    if row != _TOKEN_ROW:
        reopen()
        return
    app.call_next(open_secret_removal, app, state, service, token, reopen)


def _open_test_picker(
    app: App[Any],
    state: SessionState,
    service: AppService,
    availability: MutableMapping[str, ModelProbeResult],
    reopen: Callable[[], None],
) -> None:
    """Pick exactly one alias for the test, sending nothing while browsing."""
    catalog: ModelCatalog | None = load_catalog(state, service)

    def chosen(outcome: SelectOutcome[str] | None) -> None:
        """Ask for the confirmation before anything may be sent."""
        if outcome is None or outcome.kind is not SelectOutcomeKind.SINGLE or not outcome.value:
            reopen()
            return
        app.call_next(_confirm_test, app, state, service, availability, outcome.value, reopen)

    open_dialog(
        app,
        state,
        SelectDialog(title=MODEL_TEST_TITLE, options=model_options(catalog, availability)),
        chosen,
    )


def _confirm_test(  # noqa: PLR0913 - the confirmation gate needs the full context
    app: App[Any],
    state: SessionState,
    service: AppService,
    availability: MutableMapping[str, ModelProbeResult],
    alias: str,
    reopen: Callable[[], None],
) -> None:
    """Show the warning and let only one confirmed request through."""

    def answered(confirmed: bool | None) -> None:
        """Run exactly one test on a yes, then return to the surface."""
        if confirmed:
            _run_test(state, service, availability, alias)
        reopen()

    open_dialog(
        app,
        state,
        ConfirmDialog(
            title=CONNECT_TEST_TITLE,
            question=CONNECT_TEST_QUESTION.format(alias=alias, warning=CONNECT_TEST_WARNING),
        ),
        answered,
    )


def _run_test(
    state: SessionState,
    service: AppService,
    availability: MutableMapping[str, ModelProbeResult],
    alias: str,
) -> None:
    """Send the one confirmed request and keep its answer in this session only."""
    from anishift.application import ModelAvailability  # noqa: PLC0415

    result: ModelProbeResult = service.probe_model(alias)
    availability[alias] = result
    verified: bool = result.availability is ModelAvailability.VERIFIED
    state.feedback = UiFeedback(
        level=FeedbackLevel.INFO if verified else FeedbackLevel.WARNING,
        message=(
            CONNECT_TEST_VERIFIED.format(alias=alias)
            if verified
            else CONNECT_TEST_FAILED.format(alias=alias, error_class=result.error_class)
        ),
    )


def _spec(service: AppService, draft: SettingsDraft, setting_id: str) -> SettingSpec | None:
    """Return the catalog spec of *setting_id*, or ``None`` when it is absent."""
    return next((spec for spec in service.settings_catalog(draft) if spec.setting_id == setting_id), None)
