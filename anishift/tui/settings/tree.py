"""The settings panels every domain command opens over the shared editor dispatch."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.select import SelectAction, SelectDialog, SelectOption, SelectOutcomeKind
from anishift.tui.models.picker import open_alias_selection
from anishift.tui.settings.editors import open_field_editor, value_summary
from anishift.tui.settings.secrets import open_secret_editor, open_secret_removal, secret_status
from anishift.tui.strings import (
    COMMAND_PROMPTS_TITLE,
    COMMAND_TRANSLATION_TITLE,
    COMMAND_TTS_TITLE,
    SECRET_REMOVE_LABEL,
    SETTING_ENV_READONLY,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from textual.app import App

    from anishift.application import AppService
    from anishift.config.field_catalog import SettingSpec
    from anishift.tui.dialogs.select import SelectOutcome
    from anishift.tui.state import SessionState

__all__ = ["SettingDomain", "domain_of", "open_settings_panel"]

# ── Constants ──────────────────────────────────────────────────────────────

_PROMPT_SETTING_IDS: Final[frozenset[str]] = frozenset({"llm_prompt_id", "llm_style_id", "llm_module_ids"})
"""Prompt preferences the ``/prompts`` panel owns, taken out of the LLM group."""

_TRANSLATION_SECRET_IDS: Final[frozenset[str]] = frozenset(
    {
        "deepl_api_key",
        "anthropic_api_key",
        "gemini_api_key",
        "openai_api_key",
        "deepseek_api_key",
        "openrouter_api_key",
        "openai_compatible_api_key",
    }
)
"""Provider secrets the ``/translation`` panel offers next to the engine choice."""

_TTS_SETTING_IDS: Final[frozenset[str]] = frozenset(
    {"elevenlabs_api_key", "narrator_mix_base_gain_db", "original_gain_db"}
)
"""Speech-domain settings that do not share the ``tts_`` prefix."""

_SECRET_REMOVE_ACTION: Final[str] = "clear_secret"  # noqa: S105
"""Action name of the key that clears the highlighted secret."""

_SECRET_REMOVE_KEY: Final[str] = "ctrl+d"  # noqa: S105
"""Key that clears one secret, kept off the letters the filter box consumes."""


class SettingDomain(StrEnum):
    """The setting domains the shell edits over one shared dispatch."""

    TRANSLATION = "translation"
    PROMPTS = "prompts"
    TTS = "tts"


_DOMAIN_TITLES: Final[dict[SettingDomain, str]] = {
    SettingDomain.TRANSLATION: COMMAND_TRANSLATION_TITLE,
    SettingDomain.PROMPTS: COMMAND_PROMPTS_TITLE,
    SettingDomain.TTS: COMMAND_TTS_TITLE,
}
"""Heading each domain panel shows, reusing the command titles."""


def domain_of(setting_id: str) -> SettingDomain | None:
    """Return the domain that owns *setting_id*, or ``None`` when no panel shows it."""
    if setting_id in _PROMPT_SETTING_IDS:
        return SettingDomain.PROMPTS
    if (
        setting_id.startswith(("translation_", "llm_"))
        or setting_id in _TRANSLATION_SECRET_IDS
        or setting_id == "openai_compatible_base_url"
    ):
        return SettingDomain.TRANSLATION
    if setting_id.startswith(("tts_", "elevenbytes_")) or setting_id in _TTS_SETTING_IDS:
        return SettingDomain.TTS
    return None


def open_settings_panel(
    app: App[Any],
    state: SessionState,
    service: AppService,
    domain: SettingDomain,
    *,
    highlight_id: str | None = None,
) -> None:
    """Offer every active setting of *domain*, reopening on the edited row."""
    from anishift.config.field_access import setting_is_active, setting_is_persisted  # noqa: PLC0415

    draft = service.settings_snapshot()
    statuses: Mapping[str, bool] = service.environment_statuses()
    specs: tuple[SettingSpec, ...] = tuple(
        spec
        for spec in service.settings_catalog(draft)
        if domain_of(spec.setting_id) is domain
        and setting_is_active(spec, draft)
        and (spec.is_secret or setting_is_persisted(spec) or spec.setting_id in statuses)
    )
    options: tuple[SelectOption[str], ...] = tuple(
        SelectOption(
            value=spec.setting_id,
            title=spec.label,
            description=spec.description,
            footer=_footer(spec, draft, statuses),
        )
        for spec in specs
    )
    actions: tuple[SelectAction, ...] = (
        (SelectAction(_SECRET_REMOVE_ACTION, _SECRET_REMOVE_KEY, SECRET_REMOVE_LABEL),)
        if any(spec.is_secret for spec in specs)
        else ()
    )
    highlight: int | None = next(
        (index for index, spec in enumerate(specs) if spec.setting_id == highlight_id),
        None,
    )

    def chosen(outcome: SelectOutcome[str] | None) -> None:
        """Route the picked row to its editor once the list left the stack."""
        _react(app, state, service, domain, specs, outcome)

    open_dialog(
        app,
        state,
        SelectDialog(title=_DOMAIN_TITLES[domain], options=options, actions=actions, initial_highlight=highlight),
        chosen,
    )


def _footer(spec: SettingSpec, draft: Any, statuses: Mapping[str, bool]) -> str:
    """Return the value or status text one settings row shows."""
    from anishift.config.field_access import read_setting_value, setting_is_persisted  # noqa: PLC0415

    if spec.is_secret:
        return secret_status(configured=bool(statuses.get(spec.setting_id, False)))
    if not setting_is_persisted(spec):
        return SETTING_ENV_READONLY
    return value_summary(read_setting_value(draft, spec))


def _react(  # noqa: PLR0913 - the panel routes one outcome with its full context
    app: App[Any],
    state: SessionState,
    service: AppService,
    domain: SettingDomain,
    specs: tuple[SettingSpec, ...],
    outcome: SelectOutcome[str] | None,
) -> None:
    """Open the editor, secret removal or nothing for one panel outcome."""
    if outcome is None or outcome.kind is SelectOutcomeKind.CANCELLED:
        return
    if outcome.kind is SelectOutcomeKind.ACTION and outcome.action == _SECRET_REMOVE_ACTION:
        _remove_secret(app, state, service, domain, specs, outcome.value)
        return
    if outcome.kind is SelectOutcomeKind.SINGLE and outcome.value is not None:
        spec: SettingSpec | None = _spec_by_id(specs, outcome.value)
        if spec is not None:
            app.call_next(_edit, app, state, service, domain, spec)


def _edit(
    app: App[Any],
    state: SessionState,
    service: AppService,
    domain: SettingDomain,
    spec: SettingSpec,
) -> None:
    """Change one setting through the editor its kind or scope asks for."""
    from anishift.config.field_access import read_setting_value, setting_is_persisted  # noqa: PLC0415

    def reopen() -> None:
        """Show the domain panel again on the row that was edited."""
        app.call_next(open_settings_panel, app, state, service, domain, highlight_id=spec.setting_id)

    if spec.is_secret:
        open_secret_editor(app, state, service, spec, reopen)
        return
    if not setting_is_persisted(spec):
        reopen()
        return
    if open_alias_selection(app, state, service, spec, reopen):
        return
    draft = service.settings_snapshot()
    open_field_editor(app, state, service, spec, read_setting_value(draft, spec), reopen)


def _remove_secret(  # noqa: PLR0913 - the panel routes one outcome with its full context
    app: App[Any],
    state: SessionState,
    service: AppService,
    domain: SettingDomain,
    specs: tuple[SettingSpec, ...],
    setting_id: str | None,
) -> None:
    """Clear the highlighted secret, then reopen the panel on that row."""
    spec: SettingSpec | None = None if setting_id is None else _spec_by_id(specs, setting_id)

    def reopen() -> None:
        """Show the domain panel again on the row that was cleared."""
        app.call_next(open_settings_panel, app, state, service, domain, highlight_id=setting_id)

    if spec is None or not spec.is_secret:
        reopen()
        return
    open_secret_removal(app, state, service, spec, reopen)


def _spec_by_id(specs: tuple[SettingSpec, ...], setting_id: str) -> SettingSpec | None:
    """Return the spec in *specs* with *setting_id*, or ``None`` when absent."""
    return next((spec for spec in specs if spec.setting_id == setting_id), None)
