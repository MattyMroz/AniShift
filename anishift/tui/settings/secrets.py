"""Reading and changing environment secrets without ever showing their value."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.value import ConfirmDialog, PromptDialog
from anishift.tui.state import FeedbackLevel, UiFeedback
from anishift.tui.strings import (
    SECRET_CONFIGURED,
    SECRET_HINT,
    SECRET_MISSING,
    SECRET_OVERRIDDEN,
    SECRET_REMOVE_QUESTION,
    SECRET_REMOVE_TITLE,
    SECRET_REMOVED,
    SECRET_STORED,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import App

    from anishift.application import AppService
    from anishift.config.field_catalog import SettingSpec
    from anishift.tui.state import SessionState

__all__ = ["open_secret_editor", "open_secret_removal", "secret_status"]


def secret_status(*, configured: bool) -> str:
    """Return the status text one secret row shows, never the value itself."""
    return SECRET_CONFIGURED if configured else SECRET_MISSING


def open_secret_editor(
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    on_committed: Callable[[], None],
) -> None:
    """Prompt for a new secret value, storing a non-empty entry in the file."""

    def keep(value: str | None) -> None:
        """Store a typed value, then return to the list either way."""
        if value is not None:
            _store(state, service, spec, value)
        on_committed()

    open_dialog(app, state, PromptDialog(title=spec.label, hint=SECRET_HINT), keep)


def open_secret_removal(
    app: App[Any],
    state: SessionState,
    service: AppService,
    spec: SettingSpec,
    on_committed: Callable[[], None],
) -> None:
    """Confirm and then remove one secret from the environment file."""

    def answered(confirmed: bool | None) -> None:
        """Remove the secret on a yes, then return to the list either way."""
        if confirmed:
            _remove(state, service, spec)
        on_committed()

    open_dialog(
        app,
        state,
        ConfirmDialog(title=SECRET_REMOVE_TITLE, question=SECRET_REMOVE_QUESTION.format(label=spec.label)),
        answered,
    )


def _store(state: SessionState, service: AppService, spec: SettingSpec, value: str) -> None:
    """Store one secret and report the honest post-write status."""
    from anishift.errors import ConfigError  # noqa: PLC0415

    try:
        service.update_secret(spec.setting_id, value)
    except ConfigError as error:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=_error_text(error))
        return
    message: str = SECRET_OVERRIDDEN if _process_override(spec.setting_id) else SECRET_STORED
    state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=message)


def _remove(state: SessionState, service: AppService, spec: SettingSpec) -> None:
    """Remove one secret from the file and report the outcome."""
    from anishift.errors import ConfigError  # noqa: PLC0415

    try:
        service.update_secret(spec.setting_id, None)
    except ConfigError as error:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=_error_text(error))
        return
    message: str = SECRET_OVERRIDDEN if _process_override(spec.setting_id) else SECRET_REMOVED
    state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=message)


def _process_override(setting_id: str) -> bool:
    """Whether a shell variable still shadows the stored secret of *setting_id*."""
    return bool(os.environ.get(f"ANISHIFT_{setting_id.upper()}"))


def _error_text(error: Exception) -> str:
    """Return the redacted message an application error carries."""
    context = getattr(error, "context", None)
    return context.message if context is not None else str(error)
