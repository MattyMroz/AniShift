"""Explicit source and narrator channel matrices for final audio profiles."""

from __future__ import annotations

from typing import Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.errors import AudioLayoutError
from anishift.services.audio.types import AudioCodecProfile, ChannelPlan

__all__ = ["build_channel_plan"]


def build_channel_plan(
    profile: AudioCodecProfile,
    source_layout: str,
) -> ChannelPlan:
    """Resolve a supported layout without relying on FFmpeg's implicit remap."""
    normalized_layout: str = source_layout.casefold()
    if normalized_layout == "mono":
        return ChannelPlan(
            output_layout="mono",
            output_channels=1,
            source_filter=None,
            narrator_filter="pan=mono|c0=c0",
            warning=None,
        )
    if normalized_layout == "stereo":
        return ChannelPlan(
            output_layout="stereo",
            output_channels=2,
            source_filter=None,
            narrator_filter="pan=stereo|FL=0.70710678*c0|FR=0.70710678*c0",
            warning=None,
        )
    if normalized_layout not in {"5.1", "5.1(side)", "7.1"}:
        _raise_layout(profile, source_layout)
    if profile is AudioCodecProfile.MP3:
        return ChannelPlan(
            output_layout="stereo",
            output_channels=2,
            source_filter=("pan=stereo|FL<FL+0.5*FC+0.6*BL+0.6*SL|FR<FR+0.5*FC+0.6*BR+0.6*SR"),
            narrator_filter="pan=stereo|FL=0.70710678*c0|FR=0.70710678*c0",
            warning=f"{source_layout} audio is explicitly downmixed to stereo for MP3",
        )
    if profile is AudioCodecProfile.EAC3 and normalized_layout == "7.1":
        return ChannelPlan(
            output_layout="5.1(side)",
            output_channels=6,
            source_filter=(
                "pan=5.1(side)|FL=FL|FR=FR|FC=FC|LFE=LFE|SL=0.70710678*SL+0.70710678*BL|SR=0.70710678*SR+0.70710678*BR"
            ),
            narrator_filter=_center_narrator("5.1(side)"),
            warning="7.1 audio is explicitly downmixed to 5.1(side) for E-AC-3",
        )
    if normalized_layout in {"5.1", "5.1(side)"}:
        return ChannelPlan(
            output_layout=normalized_layout,
            output_channels=6,
            source_filter=None,
            narrator_filter=_center_narrator(normalized_layout),
            warning=None,
        )
    return ChannelPlan(
        output_layout="7.1",
        output_channels=8,
        source_filter=None,
        narrator_filter=_center_narrator("7.1"),
        warning=None,
    )


def _center_narrator(layout: str) -> str:
    if layout == "5.1":
        return "pan=5.1|FL=0*c0|FR=0*c0|FC=c0|LFE=0*c0|BL=0*c0|BR=0*c0"
    if layout == "5.1(side)":
        return "pan=5.1(side)|FL=0*c0|FR=0*c0|FC=c0|LFE=0*c0|SL=0*c0|SR=0*c0"
    return "pan=7.1|FL=0*c0|FR=0*c0|FC=c0|LFE=0*c0|BL=0*c0|BR=0*c0|SL=0*c0|SR=0*c0"


def _raise_layout(profile: AudioCodecProfile, layout: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=f"Unsupported explicit channel layout: {layout}",
        suggestion="Choose a supported source track or output profile.",
        details={"profile": profile.value, "channel_layout": layout},
    )
    raise AudioLayoutError(context=context)
