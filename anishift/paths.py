"""Location of the panel-preferences file, free of every domain import."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

__all__ = ["ENV_CONFIG_DIR", "config_dir", "config_path"]

# ── Constants ──────────────────────────────────────────────────────────────

ENV_CONFIG_DIR: Final[str] = "ANISHIFT_CONFIG_DIR"
"""Env var replacing ``<repo>/config`` as the directory of every runtime file."""

_CONFIG_DIR_NAME: Final[str] = "config"
"""Name of the directory holding panel preferences under the repo root."""

_CONFIG_FILE_NAME: Final[str] = "settings.json"
"""Filename of the panel-preferences JSON file."""


def _repo_root() -> Path:
    """Return the repository root (ancestor holding ``pyproject.toml``)."""
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    """Return the directory holding every runtime configuration file.

    ``ANISHIFT_CONFIG_DIR`` replaces ``<repo>/config`` entirely, so a test or a second
    machine account can keep its own preferences, watch state and subscriptions.
    """
    override: str | None = os.environ.get(ENV_CONFIG_DIR)
    if override is not None and override.strip():
        return Path(override.strip()).expanduser().resolve()
    return _repo_root() / _CONFIG_DIR_NAME


def config_path() -> Path:
    """Return the absolute path to ``settings.json`` inside :func:`config_dir`."""
    return config_dir() / _CONFIG_FILE_NAME
