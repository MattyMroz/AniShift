"""Application composition root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from anishift.config.env_file import env_path
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, load_user_settings
from anishift.config.workspace import ensure_workspace_dir, resolve_workspace_root
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from anishift.application.cancellation import CancellationToken
    from anishift.application.discovery import DiscoveryResult
    from anishift.application.service import AppService

__all__ = ["AppContext", "bootstrap", "create_app_service", "production_service"]

logger = get_logger(__name__)


@dataclass(slots=True)
class AppContext:
    """Wired application context."""

    settings: Settings
    user_settings: UserSettings
    workspace_root: Path


def bootstrap(
    *,
    settings: Settings | None = None,
    create_dirs: bool = True,
) -> AppContext:
    """Load config, resolve the workspace, and return an :class:`AppContext`."""
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


def create_app_service(context: AppContext) -> AppService:
    """Build the shared application facade while keeping providers lazy."""
    from anishift.application.inspection import WorkspaceInspector  # noqa: PLC0415
    from anishift.application.runtime import ProductionHandlerFactory  # noqa: PLC0415
    from anishift.application.service import AppService  # noqa: PLC0415
    from anishift.services.media import DefaultMediaProbe  # noqa: PLC0415

    service: AppService = AppService(
        workspace_root=context.workspace_root,
        settings=context.settings,
        user_settings=context.user_settings,
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        prepare_workspace=_prepare_workspace_binaries,
        handler_factory=ProductionHandlerFactory(
            lambda: service.current_settings(),  # noqa: PLW0108 - defers the lookup until the service exists
        ),
    )
    return service


def _prepare_workspace_binaries(discovery: DiscoveryResult, cancel: CancellationToken) -> None:
    """Prepare media tools before probing without opening another renderer."""
    from anishift.application.artifacts import ArtifactKind  # noqa: PLC0415
    from anishift.errors import ErrorContext, ExecutionError  # noqa: PLC0415
    from anishift.platform.binaries import Binary, BinaryNotFoundError  # noqa: PLC0415
    from anishift.setup.installer import InstallerError, ensure_binary  # noqa: PLC0415

    kinds: set[ArtifactKind] = {artifact.kind for group in discovery.groups for artifact in group.artifacts}
    binaries: list[Binary] = []
    if ArtifactKind.VIDEO_MKV in kinds:
        binaries.extend((Binary.MKVMERGE, Binary.MKVEXTRACT))
    if kinds.intersection({ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4, ArtifactKind.NARRATION_AUDIO}):
        binaries.extend((Binary.FFMPEG, Binary.FFPROBE))
    for binary in binaries:
        cancel.raise_if_cancelled()
        logger.debug("Preparing workspace media tool", binary=binary.value)
        try:
            ensure_binary(binary, show_progress=False, cancel=cancel.is_cancelled)
        except (InstallerError, BinaryNotFoundError) as error:
            raise ExecutionError(
                context=ErrorContext(
                    code=error.context.code,
                    message=f"External tool preparation failed: {binary.value}",
                    suggestion="Check the connection and disk access, then retry or run `anishift setup`.",
                ),
            ) from error
    cancel.raise_if_cancelled()


def production_service() -> AppService:
    """Compose the one application facade every production entry point runs on."""
    return create_app_service(bootstrap())
