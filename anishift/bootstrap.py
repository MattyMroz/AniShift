"""Application composition root.

``bootstrap()`` is the single place that loads ``.env``, resolves settings and
the workspace, and returns an :class:`AppContext`. Trimmed vs. MangaShift: no
DB engine, no runtime manager, no device detection — AniShift processes one
folder in a terminal.

Usage:
    from anishift.bootstrap import bootstrap

    app = bootstrap()                 # production defaults
    app = bootstrap(create_dirs=False)  # skip workspace creation (tests)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, load_user_settings
from anishift.config.workspace import ensure_workspace_dir, resolve_workspace_root

__all__ = ["AppContext", "bootstrap"]


@dataclass(slots=True)
class AppContext:
    """Wired application context.

    Attributes:
        settings: Resolved API-key / env settings.
        user_settings: Panel preferences from ``config/settings.json``.
        workspace_root: Absolute path to the workspace root.
    """

    settings: Settings
    user_settings: UserSettings
    workspace_root: Path


def bootstrap(
    *,
    settings: Settings | None = None,
    create_dirs: bool = True,
) -> AppContext:
    """Load config, resolve the workspace, and return an :class:`AppContext`.

    Args:
        settings: Pre-built :class:`Settings` (skips ``.env`` loading).
        create_dirs: When ``True`` create the workspace root and its
            default subdirectories on disk.

    Returns:
        Fully wired :class:`AppContext`.
    """
    load_dotenv(override=False)

    resolved = settings if settings is not None else Settings()
    user_settings = load_user_settings()
    workspace_root = resolve_workspace_root()
    if create_dirs:
        ensure_workspace_dir(workspace_root)

    return AppContext(
        settings=resolved,
        user_settings=user_settings,
        workspace_root=workspace_root,
    )
