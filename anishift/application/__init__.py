"""Public application contracts for callers independent of CLI and TUI."""

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from anishift.application.acquisition import (
        AcquisitionService,
        CatalogOrder,
        ClientStatus,
        DownloadReceipt,
        EpisodeReading,
        ReleaseCatalog,
        ReleaseChoice,
        SeasonContext,
        SeriesGroup,
        read_episode,
    )
    from anishift.application.discovery import (
        PRIMARY_SOURCE_SUFFIXES,
        DiscoveryResult,
        DiscoveryWarning,
    )
    from anishift.application.inspection import (
        InspectedSourceGroup,
        InspectedWorkspace,
        InspectionWarning,
        WorkspaceInspector,
    )
    from anishift.application.service import (
        AppService,
        AutoPresetDraft,
        EnvironmentSettingStatus,
        ExecutionHandlerFactory,
        ModelAvailability,
        ModelProbeResult,
        SettingsDraft,
        TranslationModelOption,
    )
    from anishift.application.subscriptions import CHECK_INTERVAL_S as SUBSCRIPTION_CHECK_INTERVAL_S
    from anishift.application.subscriptions import CheckOutcome, Subscription, SubscriptionService
    from anishift.services.catalog import TitleCandidate, TitleCatalogError, TitleStatus
    from anishift.services.torrents.query import EpisodeRange, SearchQuery, parse_query
    from anishift.setup.doctor import CheckResult
    from anishift.setup.installer import ResourceResult

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    GroupConflict,
    GroupConflictKind,
    SourceGroup,
)
from anishift.application.cancellation import CancellationToken, EventCancellationToken
from anishift.application.events import (
    RunEvent,
    RunEventEmitter,
    RunEventKind,
    RunEventSink,
    WorkerNotification,
    WorkerNotificationKind,
)
from anishift.application.intents import (
    AutoPreset,
    BurnSubtitleProduct,
    ExternalAudioRole,
    GroupIntent,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.planner import plan_auto, plan_manual
from anishift.application.planning import (
    ExecutionPlan,
    GroupPlan,
    PlanProblem,
    PlanTask,
    ProcessingOrderPolicy,
    RunSettingsSnapshot,
    TaskKind,
    TaskState,
)
from anishift.application.results import (
    ArtifactSnapshot,
    GroupResult,
    GroupStatus,
    ProducedArtifact,
    RunResult,
    TaskResult,
)
from anishift.application.selection import group_is_ready, ready_group_ids
from anishift.application.watch import SCAN_INTERVAL_S, WatchLedger

__all__ = [
    "PRIMARY_SOURCE_SUFFIXES",
    "SCAN_INTERVAL_S",
    "SUBSCRIPTION_CHECK_INTERVAL_S",
    "AcquisitionService",
    "AppService",
    "Artifact",
    "ArtifactKind",
    "ArtifactLifetime",
    "ArtifactSnapshot",
    "ArtifactState",
    "AutoPreset",
    "AutoPresetDraft",
    "BurnSubtitleProduct",
    "CancellationToken",
    "CatalogOrder",
    "CheckOutcome",
    "CheckResult",
    "ClientStatus",
    "DiscoveryResult",
    "DiscoveryWarning",
    "DownloadReceipt",
    "EnvironmentSettingStatus",
    "EpisodeRange",
    "EpisodeReading",
    "EventCancellationToken",
    "ExecutionHandlerFactory",
    "ExecutionPlan",
    "ExternalAudioRole",
    "GroupConflict",
    "GroupConflictKind",
    "GroupIntent",
    "GroupPlan",
    "GroupResult",
    "GroupStatus",
    "InspectedSourceGroup",
    "InspectedWorkspace",
    "InspectionWarning",
    "MkvTrackProduct",
    "ModelAvailability",
    "ModelProbeResult",
    "Mp4AudioSource",
    "PlanProblem",
    "PlanTask",
    "ProcessingOrderPolicy",
    "ProducedArtifact",
    "ProductIntent",
    "ProductKind",
    "ReleaseCatalog",
    "ReleaseChoice",
    "ResourceResult",
    "RunEvent",
    "RunEventEmitter",
    "RunEventKind",
    "RunEventSink",
    "RunMode",
    "RunResult",
    "RunSettingsSnapshot",
    "SearchQuery",
    "SeasonContext",
    "SeriesGroup",
    "SettingsDraft",
    "SourceGroup",
    "Subscription",
    "SubscriptionService",
    "SubtitleOutputFormat",
    "SubtitleSourcePolicy",
    "TaskKind",
    "TaskResult",
    "TaskState",
    "TitleCandidate",
    "TitleCatalogError",
    "TitleStatus",
    "TranslationAction",
    "TranslationModelOption",
    "WatchLedger",
    "WorkerNotification",
    "WorkerNotificationKind",
    "WorkspaceInspector",
    "group_is_ready",
    "parse_query",
    "plan_auto",
    "plan_manual",
    "read_episode",
    "ready_group_ids",
]

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "PRIMARY_SOURCE_SUFFIXES": ("anishift.application.discovery", "PRIMARY_SOURCE_SUFFIXES"),
    "AppService": ("anishift.application.service", "AppService"),
    "CheckOutcome": ("anishift.application.subscriptions", "CheckOutcome"),
    "SUBSCRIPTION_CHECK_INTERVAL_S": ("anishift.application.subscriptions", "CHECK_INTERVAL_S"),
    "Subscription": ("anishift.application.subscriptions", "Subscription"),
    "SubscriptionService": ("anishift.application.subscriptions", "SubscriptionService"),
    "AcquisitionService": ("anishift.application.acquisition", "AcquisitionService"),
    "CatalogOrder": ("anishift.application.acquisition", "CatalogOrder"),
    "EpisodeReading": ("anishift.application.acquisition", "EpisodeReading"),
    "SeasonContext": ("anishift.application.acquisition", "SeasonContext"),
    "read_episode": ("anishift.application.acquisition", "read_episode"),
    "EpisodeRange": ("anishift.services.torrents.query", "EpisodeRange"),
    "SearchQuery": ("anishift.services.torrents.query", "SearchQuery"),
    "parse_query": ("anishift.services.torrents.query", "parse_query"),
    "TitleCandidate": ("anishift.services.catalog", "TitleCandidate"),
    "TitleCatalogError": ("anishift.services.catalog", "TitleCatalogError"),
    "TitleStatus": ("anishift.services.catalog", "TitleStatus"),
    "AutoPresetDraft": ("anishift.application.service", "AutoPresetDraft"),
    "ClientStatus": ("anishift.application.acquisition", "ClientStatus"),
    "DownloadReceipt": ("anishift.application.acquisition", "DownloadReceipt"),
    "ReleaseCatalog": ("anishift.application.acquisition", "ReleaseCatalog"),
    "ReleaseChoice": ("anishift.application.acquisition", "ReleaseChoice"),
    "SeriesGroup": ("anishift.application.acquisition", "SeriesGroup"),
    "EnvironmentSettingStatus": ("anishift.application.service", "EnvironmentSettingStatus"),
    "CheckResult": ("anishift.setup.doctor", "CheckResult"),
    "DiscoveryResult": ("anishift.application.discovery", "DiscoveryResult"),
    "DiscoveryWarning": ("anishift.application.discovery", "DiscoveryWarning"),
    "InspectedSourceGroup": ("anishift.application.inspection", "InspectedSourceGroup"),
    "InspectedWorkspace": ("anishift.application.inspection", "InspectedWorkspace"),
    "InspectionWarning": ("anishift.application.inspection", "InspectionWarning"),
    "ExecutionHandlerFactory": ("anishift.application.service", "ExecutionHandlerFactory"),
    "ModelAvailability": ("anishift.application.service", "ModelAvailability"),
    "ModelProbeResult": ("anishift.application.service", "ModelProbeResult"),
    "ResourceResult": ("anishift.setup.installer", "ResourceResult"),
    "SettingsDraft": ("anishift.application.service", "SettingsDraft"),
    "TranslationModelOption": ("anishift.application.service", "TranslationModelOption"),
    "WorkspaceInspector": ("anishift.application.inspection", "WorkspaceInspector"),
}
"""I/O exports loaded only when requested, avoiding eager package import cycles."""


def __getattr__(name: str) -> object:
    """Load controlled-I/O facade objects without making every submodule eager."""
    target: tuple[str, str] | None = _LAZY_EXPORTS.get(name)
    if target is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module_name, attribute_name = target
    value: object = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
