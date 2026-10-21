"""Clone or update the owner's private font repository into external/fonts and choose its dialogue font."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Final

from anishift.config.user_settings import UserSettings, load_user_settings, save_user_settings
from anishift.paths import external_dir
from anishift.setup.installer import ResourceResult
from anishift.utils.logger import get_logger

__all__ = ["DIALOGUE_FONT", "FONTS_REPOSITORY", "install_fonts"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

FONTS_REPOSITORY: Final[str] = "MattyMroz/fonts"
"""Private GitHub repository holding the owner's licensed font files."""

DIALOGUE_FONT: Final[Path] = Path("video") / "ITC Officina Sans Std PL - Bold.ttf"
"""Dialogue font inside the font repository."""

_TIMEOUT_S: Final[float] = 120.0
"""Longest a clone or an update may take."""


def install_fonts() -> ResourceResult:
    """Clone or update the font repository and choose its dialogue font when none is set; never raise."""
    root: Path = external_dir() / "fonts"
    command: list[str] = (
        ["git", "-C", str(root), "pull", "--ff-only", "--quiet"]
        if (root / ".git").is_dir()
        else ["gh", "repo", "clone", FONTS_REPOSITORY, str(root), "--", "--quiet"]
    )
    if shutil.which(command[0]) is None:
        return ResourceResult("fonts", "skipped", f"{command[0]} is not installed")
    try:
        done: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603 - fixed command, no shell
            command,
            capture_output=True,
            check=False,
            timeout=_TIMEOUT_S,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        logger.warning("Font repository timed out", tool=command[0])
        return ResourceResult("fonts", "skipped", "font repository timed out")
    if done.returncode != 0:
        logger.warning("Font repository unavailable", tool=command[0], code=done.returncode)
        return ResourceResult("fonts", "skipped", "font repository not available to this account")
    font: Path = root / DIALOGUE_FONT
    settings: UserSettings = load_user_settings()
    if not settings.dialogue_font_file and font.is_file():
        save_user_settings(replace(settings, dialogue_font_file=str(font)))
    logger.info("Font repository ready", tool=command[0])
    return ResourceResult("fonts", "installed", "font repository ready")
