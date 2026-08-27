"""Public application contracts for callers independent of CLI and TUI."""

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
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
        ExecutionHandlerFactory,
        ModelAvailability,
        ModelProbeResult,
        SettingsDraft,
    )
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

__all__ = [
    "PRIMARY_SOURCE_SUFFIXES",
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
    "CheckResult",
    "DiscoveryResult",
    "DiscoveryWarning",
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
    "ResourceResult",
    "RunEvent",
    "RunEventEmitter",
    "RunEventKind",
    "RunEventSink",
    "RunMode",
    "RunResult",
    "RunSettingsSnapshot",
    "SettingsDraft",
    "SourceGroup",
    "SubtitleOutputFormat",
    "SubtitleSourcePolicy",
    "TaskKind",
    "TaskResult",
    "TaskState",
    "TranslationAction",
    "WorkerNotification",
    "WorkerNotificationKind",
    "WorkspaceInspector",
    "group_is_ready",
    "plan_auto",
    "plan_manual",
    "ready_group_ids",
]

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "PRIMARY_SOURCE_SUFFIXES": ("anishift.application.discovery", "PRIMARY_SOURCE_SUFFIXES"),
    "AppService": ("anishift.application.service", "AppService"),
    "AutoPresetDraft": ("anishift.application.service", "AutoPresetDraft"),
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
