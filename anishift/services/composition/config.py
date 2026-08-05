"""Immutable settings for muxing and hardsub rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.composition.errors import CompositionConfigError
from anishift.services.composition.types import QualityPreset

__all__ = ["CompositionConfig"]

# ── Constants ────────────────────────────────────────────────────────────────

_PRESET_CRF: Final[dict[QualityPreset, int]] = {
    QualityPreset.HIGH: 18,
    QualityPreset.BALANCED: 21,
    QualityPreset.COMPACT: 24,
}
"""Constant-quality value per named preset for the x264 encoder."""

_MIN_SIZE_BUDGET_RATIO: Final[float] = 1.0
"""Lowest meaningful ratio between rendered output and source size."""

_MAX_SIZE_BUDGET_RATIO: Final[float] = 4.0
"""Highest ratio still worth warning about instead of rejecting outright."""

_SUPPORTED_ENCODERS: Final[frozenset[str]] = frozenset({"libx264", "libx265"})
"""Video encoders validated for hardsub rendering."""


@dataclass(frozen=True, slots=True)
class CompositionConfig:
    """Composition behaviour shared by every variant.

    Attributes:
        quality_preset: Named quality target for hardsub rendering.
        video_encoder: FFmpeg encoder used when the picture is re-encoded.
        encoder_preset: FFmpeg speed/compression preset.
        size_budget_ratio: Output-to-source size ratio that triggers a warning.
        operation_timeout_s: Timeout for a single muxing or probing process.
        render_timeout_s: Timeout for one hardsub render.
        shutdown_grace_s: Grace period before a hard kill.
    """

    quality_preset: QualityPreset = QualityPreset.BALANCED
    video_encoder: str = "libx264"
    encoder_preset: str = "medium"
    size_budget_ratio: float = 1.1
    operation_timeout_s: float = 120.0
    render_timeout_s: float = 14_400.0
    shutdown_grace_s: float = 5.0

    def __post_init__(self) -> None:
        """Reject settings that cannot produce a valid result."""
        if type(self.quality_preset) is not QualityPreset:
            _raise_config("quality_preset must use QualityPreset")
        if self.video_encoder not in _SUPPORTED_ENCODERS:
            _raise_config("video_encoder is not supported")
        if not _MIN_SIZE_BUDGET_RATIO <= self.size_budget_ratio <= _MAX_SIZE_BUDGET_RATIO:
            _raise_config("size_budget_ratio must be between 1.0 and 4.0")
        if not math.isfinite(self.operation_timeout_s) or self.operation_timeout_s <= 0:
            _raise_config("operation_timeout_s must be finite and positive")
        if not math.isfinite(self.render_timeout_s) or self.render_timeout_s <= 0:
            _raise_config("render_timeout_s must be finite and positive")
        if not math.isfinite(self.shutdown_grace_s) or self.shutdown_grace_s <= 0:
            _raise_config("shutdown_grace_s must be finite and positive")

    @property
    def crf(self) -> int:
        """Return the constant-quality value for the selected preset."""
        return _PRESET_CRF[self.quality_preset]


def _raise_config(message: str) -> Never:
    """Raise a typed configuration failure with a fixed suggestion."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.COMPOSITION_FAILED,
        message=f"Composition configuration is invalid: {message}",
        suggestion="Choose supported values in the composition settings.",
    )
    raise CompositionConfigError(context=context)
