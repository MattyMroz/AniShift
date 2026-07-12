"""Panel preferences persisted to ``config/settings.json`` next to the code.

These are the choices the /settings panel edits (mode, engines, voice, output
placement...). They live in ``<repo>/config/settings.json`` — OUTSIDE the
workspace, so the folder the user drops MKV files into stays clean, while the
file stays visible and hand-editable. The file is created on first save.

Stage 1 ships the load/save plumbing and a minimal schema; the /settings panel
(stage 2) grows the field set.

Public API:
    UserSettings: Dataclass holding panel preferences.
    config_path: Location of ``settings.json``.
    load_user_settings: Read the file (defaults when absent / unreadable).
    save_user_settings: Write the file (creates ``config/`` if needed).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Literal

__all__ = [
    "Mode",
    "UserSettings",
    "config_path",
    "load_user_settings",
    "save_user_settings",
]

Mode = Literal["auto", "manual"]
"""Processing mode: ``auto`` (Enter processes everything) or ``manual``."""

_CONFIG_DIR_NAME: Final[str] = "config"
"""Name of the directory holding panel preferences under the repo root."""

_CONFIG_FILE_NAME: Final[str] = "settings.json"
"""Filename of the panel-preferences JSON file."""


@dataclass(slots=True)
class UserSettings:
    """Panel preferences (mode, output placement, engine choices).

    Attributes:
        mode: Processing mode — ``"auto"`` (Enter processes everything) or
            ``"manual"`` (prompt per track).
        move_results_to_output: When ``True`` finished files go to
            ``workspace/output/``; when ``False`` they land next to the MKV.
    """

    mode: Mode = "auto"
    move_results_to_output: bool = False


def _repo_root() -> Path:
    """Return the repository root (ancestor holding ``pyproject.toml``)."""
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    """Return the absolute path to ``<repo>/config/settings.json``."""
    return _repo_root() / _CONFIG_DIR_NAME / _CONFIG_FILE_NAME


def load_user_settings() -> UserSettings:
    """Load panel preferences, falling back to defaults.

    Unknown keys in the file are ignored; a missing or unreadable file yields
    a fresh :class:`UserSettings` with defaults.
    """
    path = config_path()
    if not path.is_file():
        return UserSettings()
    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
    except OSError:
        return UserSettings()
    except json.JSONDecodeError:
        return UserSettings()
    if not isinstance(raw, dict):
        return UserSettings()
    known = set(UserSettings.__dataclass_fields__)
    filtered = {k: v for k, v in raw.items() if k in known}
    if filtered.get("mode") not in ("auto", "manual"):
        filtered.pop("mode", None)
    return UserSettings(**filtered)


def save_user_settings(settings: UserSettings) -> None:
    """Persist panel preferences to ``config/settings.json`` (creating the dir)."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
