"""Presentation preferences of the TUI persisted next to ``settings.json``.

Only presentation state lives here — never product preferences, which belong to
``anishift.config.user_settings``. The file sits in ``<repo>/config/`` beside
``settings.json`` so the workspace the user drops MKV files into stays clean.

Public API:
    UiState: Dataclass holding presentation preferences.
    ui_state_path: Location of ``ui_state.json``.
    load_ui_state: Read the file (safe defaults when absent / unreadable).
    save_ui_state: Write the file atomically (creates ``config/`` if needed).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Final

from anishift.paths import config_path
from anishift.tui.theme import DEFAULT_THEME_ID, THEME_IDS
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "UiState",
    "load_ui_state",
    "save_ui_state",
    "ui_state_path",
]

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

_UI_STATE_FILE_NAME: Final[str] = "ui_state.json"
"""Filename of the presentation-state JSON file."""


@dataclass(slots=True)
class UiState:
    """Presentation preferences of the TUI.

    Attributes:
        theme: Selected theme id, always one of ``THEME_IDS``.
    """

    theme: str = DEFAULT_THEME_ID


def ui_state_path() -> Path:
    """Return the absolute path to ``<repo>/config/ui_state.json``."""
    return config_path().with_name(_UI_STATE_FILE_NAME)


def load_ui_state() -> UiState:
    """Load presentation preferences, falling back to safe defaults.

    A missing, unreadable, malformed or unknown-theme file never raises: the
    dark theme is selected instead.
    """
    path: Path = ui_state_path()
    if not path.is_file():
        return UiState()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        logger.warning("UI state unreadable; defaults selected")
        return UiState()
    if not isinstance(raw, dict):
        logger.warning("UI state is not an object; defaults selected")
        return UiState()
    theme: object = raw.get("theme")
    if theme not in THEME_IDS:
        logger.warning("UI state theme unknown; defaults selected")
        return UiState()
    return UiState(theme=str(theme))


def save_ui_state(state: UiState) -> None:
    """Persist presentation preferences atomically to ``config/ui_state.json``."""
    path: Path = ui_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: str = json.dumps(asdict(state), indent=2, ensure_ascii=False) + "\n"
    tmp: Path = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    logger.info("UI state saved", theme=state.theme)
