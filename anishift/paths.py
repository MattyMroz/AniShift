"""Location of the panel-preferences file, free of every domain import.

``config_path`` is a trivial path helper that every layer needs, down to the
terminal shell. It sits outside :mod:`anishift.config` on purpose: that package
validates engine ids, so its ``__init__`` and its ``user_settings`` module pull
the audio, translation, LLM and TTS registries into the process. Importing this
module pulls nothing but :mod:`pathlib`, which keeps the presentation layer free
of the backend.

:mod:`anishift.config` re-exports ``config_path``, so callers that want the
configuration facade keep using it.

Public API:
    config_path: Location of ``<repo>/config/settings.json``.
"""

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
