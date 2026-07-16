"""Panel preferences persisted to ``config/settings.json`` next to the code.

These are the choices the /settings panel edits (mode, engines, voice, output
placement...). They live in ``<repo>/config/settings.json`` — OUTSIDE the
workspace, so the folder the user drops MKV files into stays clean, while the
file stays visible and hand-editable. The file is created on first save.

Public API:
    UserSettings: Dataclass holding panel preferences.
    Mode: Processing mode literal.
    OutputVariant: Output-assembly variant literal.
    config_path: Location of ``settings.json``.
    load_user_settings: Read the file (defaults when absent / unreadable).
    save_user_settings: Write the file atomically (creates ``config/`` if needed).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final, Literal

__all__ = [
    "Mode",
    "OutputVariant",
    "UserSettings",
    "config_path",
    "load_user_settings",
    "save_user_settings",
]

Mode = Literal["auto", "manual"]
"""Processing mode: ``auto`` (Enter processes everything) or ``manual``."""

OutputVariant = Literal["players", "merge", "burn"]
"""Output assembly: soft players, MKV merge, or burned-in MP4."""

# ── Constants ──────────────────────────────────────────────────────────────

_CONFIG_DIR_NAME: Final[str] = "config"
"""Name of the directory holding panel preferences under the repo root."""

_CONFIG_FILE_NAME: Final[str] = "settings.json"
"""Filename of the panel-preferences JSON file."""

TEMPO_RANGE: Final[tuple[float, float]] = (0.5, 2.0)
"""Allowed inclusive range for the speech tempo multiplier."""

VOLUME_RANGE: Final[tuple[int, int]] = (0, 100)
"""Allowed inclusive range for the output volume percentage."""

_MODES: Final[frozenset[str]] = frozenset(("auto", "manual"))
"""Accepted values for the ``mode`` field."""

_OUTPUT_VARIANTS: Final[frozenset[str]] = frozenset(("players", "merge", "burn"))
"""Accepted values for the ``output_variant`` field."""


@dataclass(slots=True)
class UserSettings:
    """Panel preferences (mode, engines, voice, output placement).

    Attributes:
        mode: ``"auto"`` (Enter processes everything) or ``"manual"``.
        translation_engine: Selected translation engine id.
        tts_engine: Selected text-to-speech engine id.
        voice: Selected TTS voice id.
        tempo: Speech tempo multiplier within :data:`TEMPO_RANGE`.
        volume: Output volume percentage within :data:`VOLUME_RANGE`.
        output_variant: Output assembly variant.
        move_results_to_output: When ``True`` finished files go to
            ``workspace/output/``; when ``False`` they land next to the MKV.
    """

    mode: Mode = "auto"
    translation_engine: str = "google"
    tts_engine: str = "edge"
    voice: str = "pl-PL-MarekNeural"
    tempo: float = 1.0
    volume: int = 100
    output_variant: OutputVariant = "merge"
    move_results_to_output: bool = False


def _repo_root() -> Path:
    """Return the repository root (ancestor holding ``pyproject.toml``)."""
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    """Return the absolute path to ``<repo>/config/settings.json``."""
    return _repo_root() / _CONFIG_DIR_NAME / _CONFIG_FILE_NAME


def _clean_string(raw: dict[str, Any], key: str, allowed: frozenset[str]) -> None:
    """Drop ``key`` from ``raw`` when its value is not in ``allowed``."""
    if raw.get(key) not in allowed:
        raw.pop(key, None)


def _clean_bool(raw: dict[str, Any], key: str) -> None:
    """Drop ``key`` from ``raw`` when its value is not a real boolean."""
    if not isinstance(raw.get(key), bool):
        raw.pop(key, None)


def _clean_number(raw: dict[str, Any], key: str, low: float, high: float) -> None:
    """Drop ``key`` from ``raw`` when it is non-numeric or out of range."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raw.pop(key, None)
        return
    if not low <= value <= high:
        raw.pop(key, None)


def load_user_settings() -> UserSettings:
    """Load panel preferences, falling back to defaults.

    Unknown keys are ignored; missing, unreadable, wrong-typed or out-of-range
    fields fall back to their defaults instead of raising.
    """
    path = config_path()
    if not path.is_file():
        return UserSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return UserSettings()
    except UnicodeDecodeError:
        return UserSettings()
    except json.JSONDecodeError:
        return UserSettings()
    if not isinstance(raw, dict):
        return UserSettings()

    known = set(UserSettings.__dataclass_fields__)
    filtered: dict[str, Any] = {k: v for k, v in raw.items() if k in known}
    _clean_string(filtered, "mode", _MODES)
    _clean_string(filtered, "output_variant", _OUTPUT_VARIANTS)
    _clean_number(filtered, "tempo", *TEMPO_RANGE)
    _clean_number(filtered, "volume", *VOLUME_RANGE)
    _clean_bool(filtered, "move_results_to_output")
    return UserSettings(**filtered)


def save_user_settings(settings: UserSettings) -> None:
    """Persist panel preferences atomically to ``config/settings.json``."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(settings), indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
