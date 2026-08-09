"""Composition domain: assemble pipeline products into one finished file."""

from __future__ import annotations

from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import (
    CompositionCancelledError,
    CompositionConfigError,
    CompositionError,
    CompositionProcessError,
    CompositionValidationError,
)
from anishift.services.composition.service import CompositionProgressSink, CompositionService
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    ContainerCompositionRequest,
    ContainerCompositionResult,
    ContainerTarget,
    OutputVariant,
    QualityPreset,
    SubtitleRole,
)

__all__ = [
    "AttachedSubtitle",
    "CompositionCancelledError",
    "CompositionConfig",
    "CompositionConfigError",
    "CompositionError",
    "CompositionPlan",
    "CompositionProcessError",
    "CompositionProgressSink",
    "CompositionResult",
    "CompositionService",
    "CompositionStatus",
    "CompositionValidationError",
    "ContainerCompositionRequest",
    "ContainerCompositionResult",
    "ContainerTarget",
    "OutputVariant",
    "QualityPreset",
    "SubtitleRole",
]
