"""Application composition root.

``bootstrap()`` is the single place that resolves settings and the workspace
and returns an :class:`AppContext`.

Usage:
    from anishift.bootstrap import bootstrap

    app = bootstrap()                 # production defaults
    app = bootstrap(create_dirs=False)  # skip workspace creation (tests)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anishift.config.env_file import env_path
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, load_user_settings
from anishift.config.workspace import ensure_workspace_dir, resolve_workspace_root
from anishift.utils.logger import get_logger

__all__ = ["AppContext", "bootstrap"]

logger = get_logger(__name__)


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
        settings: Pre-built :class:`Settings` (skips constructing a new one;
            environment and ``.env`` resolution are already complete).
        create_dirs: When ``True`` create the workspace root and its
            default subdirectories on disk.

    Returns:
        Fully wired :class:`AppContext`.
    """
    resolved = settings if settings is not None else Settings(_env_file=env_path())
    user_settings = load_user_settings()
    workspace_root = resolve_workspace_root(
        override=resolved.workspace_root or None,
    )
    if create_dirs:
        ensure_workspace_dir(workspace_root)

    logger.debug(
        "Application context composed",
        create_dirs=create_dirs,
        workspace_name=workspace_root.name,
        translation_engine=user_settings.translation_engine,
        tts_engine=user_settings.tts_engine,
    )

    return AppContext(
        settings=resolved,
        user_settings=user_settings,
        workspace_root=workspace_root,
    )
