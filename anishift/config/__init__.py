"""Application configuration package.

Two layers, both simple:

* :class:`Settings` — API keys / env, loaded from ``.env`` (prefix ``ANISHIFT_``).
* :class:`UserSettings` — panel preferences persisted to ``config/settings.json``.

Plus workspace root resolution (:func:`resolve_workspace_root`).
"""

from __future__ import annotations

from anishift.config.env_file import env_path, update_env_value
from anishift.config.field_catalog import (
    USER_SETTING_DISPOSITIONS,
    SettingCatalogContext,
    SettingCondition,
    SettingDisposition,
    SettingObjectFieldSpec,
    SettingScope,
    SettingSpec,
    SettingValueType,
    setting_catalog,
)
from anishift.config.presets import (
    AutoPresetFile,
    default_preset_file,
    load_presets,
    presets_path,
    save_presets,
)
from anishift.config.settings import Settings
from anishift.config.user_settings import (
    CustomVoiceSetting,
    TtsVoiceProfileSettings,
    UserSettings,
    config_path,
    default_tts_voice_profiles,
    load_user_settings,
    save_user_settings,
    tts_profile_key,
)
from anishift.config.workspace import (
    DEFAULT_SUBDIRS,
    ENV_WORKSPACE_ROOT,
    ensure_workspace_dir,
    resolve_workspace_root,
)

__all__ = [
    "DEFAULT_SUBDIRS",
    "ENV_WORKSPACE_ROOT",
    "USER_SETTING_DISPOSITIONS",
    "AutoPresetFile",
    "CustomVoiceSetting",
    "SettingCatalogContext",
    "SettingCondition",
    "SettingDisposition",
    "SettingObjectFieldSpec",
    "SettingScope",
    "SettingSpec",
    "SettingValueType",
    "Settings",
    "TtsVoiceProfileSettings",
    "UserSettings",
    "config_path",
    "default_preset_file",
    "default_tts_voice_profiles",
    "ensure_workspace_dir",
    "env_path",
    "load_presets",
    "load_user_settings",
    "presets_path",
    "resolve_workspace_root",
    "save_presets",
    "save_user_settings",
    "setting_catalog",
    "tts_profile_key",
    "update_env_value",
]
