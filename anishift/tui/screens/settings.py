"""Typed persistent settings editor."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, Select, Static

from anishift.application.service import SettingsDraft
from anishift.config.field_catalog import SettingScope, SettingSpec, SettingValue
from anishift.config.user_settings import CustomVoiceSetting, TtsVoiceProfileSettings
from anishift.tui.widgets import CommandBar, StatusFooter
from anishift.tui.widgets.setting_field import SettingField

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


class SettingsScreen(Screen[None]):
    """Edit a detached settings snapshot and persist only on Save."""

    def __init__(self) -> None:
        super().__init__()
        self._draft: SettingsDraft | None = None
        self._rebuilding: bool = False

    def compose(self) -> ComposeResult:
        """Compose a catalog-owned field host and explicit actions."""
        with Vertical(classes="route-content"):
            yield Label("Settings", classes="route-title")
            yield Static("", id="engine-availability")
            yield VerticalScroll(id="settings-fields")
            with Horizontal(classes="screen-actions"):
                yield Button("Save", id="settings-save", variant="primary")
                yield Button("Cancel", id="settings-cancel")
                yield Button("Tools", id="settings-tools")
            yield Static("", id="settings-feedback")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    async def on_mount(self) -> None:
        """Open an isolated copy that cannot mutate active or saved settings."""
        self._draft = self._shell.service.settings_snapshot()
        availability = self._shell.service.engine_availability()
        self.query_one("#engine-availability", Static).update(
            " | ".join(
                f"{item.domain}:{item.engine_id}={'ready' if item.is_available else item.reason}"
                for item in availability
            )
        )
        await self._rebuild_fields()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Rebuild provider-dependent fields from the edited draft."""
        if self._rebuilding or not event.select.is_mounted:
            return
        if event.select.id not in {
            "setting-llm_provider",
            "setting-tts_engine",
            "setting-tts_provider_model_id",
            "setting-tts_voice_id",
        }:
            return
        setting_id_by_control: dict[str, str] = {
            "setting-llm_provider": "llm_provider",
            "setting-tts_engine": "tts_engine",
            "setting-tts_provider_model_id": "tts_provider_model_id",
            "setting-tts_voice_id": "tts_voice_id",
        }
        setting_id: str = setting_id_by_control[event.select.id]
        if self._draft is not None and event.value == getattr(self._draft, setting_id):
            return
        if self._apply_fields(include_profile=False):
            await self._rebuild_fields()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Save explicitly, discard the draft, or open technical tools."""
        if event.button.id == "settings-cancel":
            await self._shell.open_route("workspace")
            return
        if event.button.id == "settings-tools":
            await self._shell.open_route("tools")
            return
        if event.button.id == "settings-save" and self._apply_fields(include_profile=True) and self._draft is not None:
            self._shell.service.save_settings(self._draft)
            self.query_one("#settings-feedback", Static).update("Settings saved")

    async def _rebuild_fields(self) -> None:
        draft = self._draft
        if draft is None:
            return
        self._rebuilding = True
        try:
            host = self.query_one("#settings-fields", VerticalScroll)
            await host.remove_children()
            environment = self._shell.service.environment_statuses()
            specs: tuple[SettingSpec, ...] = tuple(
                spec
                for spec in self._shell.service.settings_catalog(draft)
                if spec.scope not in {SettingScope.AUTO_PRESET, SettingScope.MANUAL_RUN}
                and (spec.is_secret or _setting_is_active(spec, draft))
            )
            fields: list[SettingField] = []
            for spec in specs:
                environment_configured: bool | None = (
                    environment.get(spec.setting_id, False) if spec.is_secret else environment.get(spec.setting_id)
                )
                value: SettingValue = (
                    spec.default if environment_configured is not None else _setting_value(draft, spec)
                )
                fields.append(SettingField(spec, value, environment_configured=environment_configured))
            await host.mount(*fields)
        finally:
            self._rebuilding = False

    def _apply_fields(self, *, include_profile: bool) -> bool:
        draft = self._draft
        if draft is None:
            return False
        try:
            values: list[tuple[SettingSpec, SettingValue]] = [
                (field.spec, field.read_value())
                for field in self.query(SettingField)
                if field.environment_configured is None
                and (include_profile or not field.spec.setting_id.startswith("tts_profile."))
            ]
            candidate: SettingsDraft = deepcopy(draft)
            values.sort(key=lambda item: item[0].setting_id.startswith("tts_profile."))
            for spec, value in values:
                _assign_setting(candidate, spec, value)
            candidate.__post_init__()
        except (TypeError, ValueError) as error:
            self.query_one("#settings-feedback", Static).update(str(error))
            return False
        self._draft = candidate
        self.query_one("#settings-feedback", Static).update("")
        return True


def _setting_value(draft: SettingsDraft, spec: SettingSpec) -> SettingValue:
    if spec.setting_id.startswith("tts_profile."):
        profile: TtsVoiceProfileSettings = draft.active_tts_profile
        field_id: str = spec.setting_id.removeprefix("tts_profile.")
        if field_id.startswith("engine_options."):
            option_id: str = field_id.removeprefix("engine_options.")
            return profile.engine_options.get(option_id, spec.default)
        return cast("SettingValue", getattr(profile, field_id))
    value: object = getattr(draft, spec.setting_id)
    if isinstance(value, list):
        if value and isinstance(value[0], CustomVoiceSetting):
            return tuple(value)
        return tuple(cast("list[str]", value))
    return cast("SettingValue", value)


def _assign_setting(draft: SettingsDraft, spec: SettingSpec, value: SettingValue) -> None:
    if spec.setting_id.startswith("tts_profile."):
        profile: TtsVoiceProfileSettings = draft.ensure_active_tts_profile()
        field_id: str = spec.setting_id.removeprefix("tts_profile.")
        if field_id.startswith("engine_options."):
            profile.engine_options[field_id.removeprefix("engine_options.")] = cast("str | int | float | bool", value)
        else:
            setattr(profile, field_id, value)
        return
    if spec.setting_id == "elevenbytes_custom_voices":
        setattr(draft, spec.setting_id, list(cast("tuple[CustomVoiceSetting, ...]", value)))
    elif isinstance(getattr(draft, spec.setting_id), list):
        setattr(draft, spec.setting_id, list(cast("tuple[str, ...] | frozenset[str]", value)))
    else:
        setattr(draft, spec.setting_id, value)


def _setting_is_active(spec: SettingSpec, draft: SettingsDraft) -> bool:
    for condition in spec.depends_on:
        current: object = getattr(draft, condition.setting_id, None)
        if isinstance(current, (list, tuple, set, frozenset)):
            if not any(value in current for value in condition.allowed_values):
                return False
        elif current not in condition.allowed_values:
            return False
    return True
