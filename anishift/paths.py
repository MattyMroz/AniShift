"""Application directory layout, free of domain imports and filesystem mutations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

__all__ = [
    "AUDIOBOOK_DIRECTORY",
    "COVER_DIRECTORY",
    "ENV_CONFIG_DIR",
    "READY_DIRECTORY",
    "SUBS_DIRECTORY",
    "TASK_DIRECTORIES",
    "TEMP_DIRECTORY",
    "TRANSLATE_DIRECTORY",
    "WATCH_DIRECTORY",
    "WORKSPACE_DIRECTORY",
    "config_dir",
    "config_path",
    "default_workspace_dir",
    "env_path",
    "external_bin_root",
    "external_dir",
    "log_path",
    "logs_dir",
    "ready_dir",
    "relocation_journal_dir",
    "repo_root",
    "run_journal_dir",
    "task_dir",
    "temp_dir",
    "torrent_data_dir",
    "torrent_download_dir",
    "torrent_profile_dir",
    "watch_dir",
]

# ── Constants ──────────────────────────────────────────────────────────────

ENV_CONFIG_DIR: Final[str] = "ANISHIFT_CONFIG_DIR"
"""Env var replacing ``<repo>/config`` as the directory of every runtime file."""

_CONFIG_DIR_NAME: Final[str] = "config"
"""Name of the directory holding panel preferences under the repo root."""

_CONFIG_FILE_NAME: Final[str] = "settings.json"
"""Filename of the panel-preferences JSON file."""

READY_DIRECTORY: Final[str] = "ready"
"""Workspace subdirectory collecting completed sources and their durable products."""

WORKSPACE_DIRECTORY: Final[str] = "workspace"
"""Default library directory under the repository root."""

TEMP_DIRECTORY: Final[str] = "temp"
"""Private run staging directory inside a workspace."""

WATCH_DIRECTORY: Final[str] = "watch"
"""Resident state directory inside runtime configuration."""

SUBS_DIRECTORY: Final[str] = "subs"
"""Workspace task folder pairing one video with the sidecar subtitles it must use."""

TRANSLATE_DIRECTORY: Final[str] = "translate"
"""Workspace task folder translating text or subtitles without any video."""

AUDIOBOOK_DIRECTORY: Final[str] = "audiobook"
"""Workspace task folder turning text or subtitles into standalone narration."""

COVER_DIRECTORY: Final[str] = "cover"
"""Workspace task folder exporting one still image and audio into a single video."""

TASK_DIRECTORIES: Final[tuple[str, ...]] = (
    SUBS_DIRECTORY,
    TRANSLATE_DIRECTORY,
    AUDIOBOOK_DIRECTORY,
    COVER_DIRECTORY,
)
"""The one collection of workspace task folders, beside the data areas ``ready`` and ``temp``."""


def repo_root() -> Path:
    """Return the single repository anchor used by the application layout."""
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    """Return the directory holding every runtime configuration file."""
    override: str | None = os.environ.get(ENV_CONFIG_DIR)
    if override is not None and override.strip():
        return Path(override.strip()).expanduser().resolve()
    return repo_root() / _CONFIG_DIR_NAME


def default_workspace_dir() -> Path:
    """Return the default library location before workspace overrides and validation."""
    return repo_root() / WORKSPACE_DIRECTORY


def config_path() -> Path:
    """Return the absolute path to ``settings.json`` inside :func:`config_dir`."""
    return config_dir() / _CONFIG_FILE_NAME


def watch_dir() -> Path:
    """Return the state and local-control directory of the resident."""
    return config_dir() / WATCH_DIRECTORY


def torrent_profile_dir() -> Path:
    """Return the private torrent client's configuration and resume-data root."""
    return config_dir() / "qbittorrent"


def torrent_data_dir(profile: Path) -> Path:
    """Return the vendor data directory inside a private torrent profile."""
    return profile / "qBittorrent"


def torrent_download_dir(profile: Path) -> Path:
    """Return the private client's fallback destination used to verify its profile."""
    return torrent_data_dir(profile) / "downloads"


def ready_dir(workspace: Path) -> Path:
    """Return the completed-media directory inside the selected workspace."""
    return workspace / READY_DIRECTORY


def relocation_journal_dir(state_dir: Path) -> Path:
    """Return pending file-move journals inside the selected resident state directory."""
    return state_dir / "relocations"


def temp_dir(workspace: Path) -> Path:
    """Return private run staging inside the selected workspace."""
    return workspace / TEMP_DIRECTORY


def task_dir(workspace: Path, task: str) -> Path:
    """Return one of :data:`TASK_DIRECTORIES` inside the selected workspace."""
    if task not in TASK_DIRECTORIES:
        msg = f"Unknown workspace task folder: {task}"
        raise ValueError(msg)
    return workspace / task


def run_journal_dir(state_dir: Path) -> Path:
    """Return processing checkpoints inside the selected resident state directory."""
    return state_dir / "runs"


def external_dir() -> Path:
    """Return the repository's external tools and their manifest directory."""
    return repo_root() / "external"


def external_bin_root() -> Path:
    """Return the directory containing the application's downloaded executables."""
    return external_dir() / "bin"


def logs_dir() -> Path:
    """Return application logs beside the selected runtime configuration directory."""
    return config_dir().parent / "logs"


def log_path() -> Path:
    """Return the structured application log selected by the process boundary."""
    return logs_dir() / "anishift.log.jsonl"


def env_path() -> Path:
    """Return the repository-level environment file."""
    return repo_root() / ".env"
