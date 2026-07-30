"""Application configuration package.

Two layers, both simple:

* :class:`Settings` — API keys / env, loaded from ``.env`` (prefix ``ANISHIFT_``).
* :class:`UserSettings` — panel preferences persisted to ``config/settings.json``.

Plus workspace root resolution (:func:`resolve_workspace_root`).
"""

from __future__ import annotations

from anishift.config.env_file import env_path, update_env_value
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
    "CustomVoiceSetting",
    "Settings",
    "TtsVoiceProfileSettings",
    "UserSettings",
    "config_path",
    "default_tts_voice_profiles",
    "ensure_workspace_dir",
    "env_path",
    "load_user_settings",
    "resolve_workspace_root",
    "save_user_settings",
    "tts_profile_key",
    "update_env_value",
]
