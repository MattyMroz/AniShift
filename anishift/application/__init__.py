"""Public application contracts for callers independent of CLI and TUI."""

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    GroupConflict,
    GroupConflictKind,
    SourceGroup,
)
from anishift.application.cancellation import CancellationToken
from anishift.application.discovery import DiscoveryResult, DiscoveryWarning
from anishift.application.inspection import (
    InspectedSourceGroup,
    InspectedWorkspace,
    InspectionWarning,
    WorkspaceInspector,
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
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult

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
    "ExecutionPlan",
    "ExternalAudioRole",
    "GroupConflict",
    "GroupConflictKind",
    "GroupIntent",
    "GroupPlan",
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
    "RunMode",
    "RunSettingsSnapshot",
    "SourceGroup",
    "SubtitleOutputFormat",
    "SubtitleSourcePolicy",
    "TaskKind",
    "TaskResult",
    "TaskState",
    "TranslationAction",
    "WorkspaceInspector",
]
