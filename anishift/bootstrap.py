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
    from collections.abc import Sequence

    from anishift.application.acquisition import AcquisitionService
    from anishift.application.cancellation import CancellationToken
    from anishift.application.discovery import DiscoveryResult
    from anishift.application.service import AppService
    from anishift.application.subscriptions import SubscriptionService
    from anishift.services.torrents import Release

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

    acquisition: AcquisitionService = _acquisition_service(context)
    service: AppService = AppService(
        workspace_root=context.workspace_root,
        settings=context.settings,
        user_settings=context.user_settings,
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        prepare_workspace=_prepare_workspace_binaries,
        handler_factory=ProductionHandlerFactory(
            lambda: service.current_settings(),  # noqa: PLW0108 - defers the lookup until the service exists
        ),
        acquisition=acquisition,
        subscriptions=_subscription_service(acquisition),
    )
    return service


def _acquisition_service(context: AppContext) -> AcquisitionService:
    """Wire the public release index and the local torrent client from the environment settings."""
    import httpx  # noqa: PLC0415

    from anishift.application.acquisition import AcquisitionService  # noqa: PLC0415
    from anishift.services.catalog import AniListCatalog  # noqa: PLC0415
    from anishift.services.http_requests import RequestControl  # noqa: PLC0415
    from anishift.services.torrents import QBittorrentClient, parse_release_name, search_releases  # noqa: PLC0415
    from anishift.services.torrents.categories import SEARCH_CATEGORIES  # noqa: PLC0415

    request_control: RequestControl = RequestControl(httpx.HTTPTransport(retries=0))
    http: httpx.Client = httpx.Client(transport=request_control, follow_redirects=True)

    class NyaaSource:
        """Public nyaa.si index queried through the shared HTTP client."""

        def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
            """Return the anime releases matching *query* in *categories*."""
            return search_releases(query, http=http, categories=categories)

    client: QBittorrentClient = QBittorrentClient(
        context.settings.qbittorrent_url,
        username=context.settings.qbittorrent_username,
        password=context.settings.qbittorrent_password,
        http=http,
    )
    return AcquisitionService(
        source=NyaaSource(),
        client=client,
        workspace_root=context.workspace_root,
        parse_name=parse_release_name,
        title_catalog=AniListCatalog(http),
        request_control=request_control,
    )


def _subscription_service(acquisition: AcquisitionService) -> SubscriptionService:
    """Wire the followed-series store beside the panel preferences onto the acquisition boundary."""
    from anishift.application.subscriptions import (  # noqa: PLC0415
        SUBSCRIPTIONS_FILE_NAME,
        SubscriptionService,
        SubscriptionStore,
    )
    from anishift.paths import config_path  # noqa: PLC0415

    store: SubscriptionStore = SubscriptionStore(config_path().parent / SUBSCRIPTIONS_FILE_NAME)
    return SubscriptionService(store=store, acquisition=acquisition)


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
