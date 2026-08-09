"""Public application contracts for callers independent of CLI and TUI."""

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from anishift.application.discovery import DiscoveryResult, DiscoveryWarning
    from anishift.application.inspection import (
        InspectedSourceGroup,
        InspectedWorkspace,
        InspectionWarning,
        WorkspaceInspector,
    )

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
    EventBuffer,
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

__all__ = [
    "Artifact",
    "ArtifactKind",
    "ArtifactLifetime",
    "ArtifactSnapshot",
    "ArtifactState",
    "AutoPreset",
    "BurnSubtitleProduct",
    "CancellationToken",
    "DiscoveryResult",
    "DiscoveryWarning",
    "EventBuffer",
    "EventCancellationToken",
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
    "Mp4AudioSource",
    "PlanProblem",
    "PlanTask",
    "ProcessingOrderPolicy",
    "ProducedArtifact",
    "ProductIntent",
    "ProductKind",
    "RunEvent",
    "RunEventEmitter",
    "RunEventKind",
    "RunEventSink",
    "RunMode",
    "RunResult",
    "RunSettingsSnapshot",
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
    "plan_auto",
    "plan_manual",
]

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "DiscoveryResult": ("anishift.application.discovery", "DiscoveryResult"),
    "DiscoveryWarning": ("anishift.application.discovery", "DiscoveryWarning"),
    "InspectedSourceGroup": ("anishift.application.inspection", "InspectedSourceGroup"),
    "InspectedWorkspace": ("anishift.application.inspection", "InspectedWorkspace"),
    "InspectionWarning": ("anishift.application.inspection", "InspectionWarning"),
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
