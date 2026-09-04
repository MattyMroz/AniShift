"""Location of the panel-preferences file, free of every domain import."""

from __future__ import annotations

from pathlib import Path
from typing import Final

__all__ = ["config_path"]

# ── Constants ──────────────────────────────────────────────────────────────

_CONFIG_DIR_NAME: Final[str] = "config"
"""Name of the directory holding panel preferences under the repo root."""

_CONFIG_FILE_NAME: Final[str] = "settings.json"
"""Filename of the panel-preferences JSON file."""


def _repo_root() -> Path:
    """Return the repository root (ancestor holding ``pyproject.toml``)."""
    return Path(__file__).resolve().parents[1]


def config_path() -> Path:
    """Return the absolute path to ``<repo>/config/settings.json``."""
    return _repo_root() / _CONFIG_DIR_NAME / _CONFIG_FILE_NAME
