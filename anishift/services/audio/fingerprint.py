"""Deterministic identities for narration and final audio derivatives."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from anishift.services.audio.config import AudioConfig
from anishift.services.audio.types import ChannelPlan, TimedClip

__all__ = [
    "mix_fingerprint",
    "narration_fingerprint",
    "sha256_file",
]

# ── Constants ────────────────────────────────────────────────────────────────

_NARRATION_ALGORITHM_VERSION: Final[int] = 1
"""Version of normalization and serialized timeline semantics."""

_MIX_ALGORITHM_VERSION: Final[int] = 1
"""Version of gain, channel mapping, and amix semantics."""

_COPY_BUFFER_BYTES: Final[int] = 1024 * 1024
"""Streaming file-hash buffer size."""


def narration_fingerprint(
    *,
    scope_id: str,
    clips: tuple[TimedClip, ...],
    post_process_tempo: float,
    config: AudioConfig,
) -> str:
    """Hash ordered clip content, timing, tempo, and target PCM settings."""
    ordered: tuple[TimedClip, ...] = tuple(
        sorted(clips, key=lambda clip: (clip.start_ms, clip.source_order)),
    )
    payload: dict[str, object] = {
        "algorithm_version": _NARRATION_ALGORITHM_VERSION,
        "scope_id": scope_id,
        "timeline_policy": config.timeline_policy.value,
        "post_process_tempo": _canonical_float(post_process_tempo),
        "target": {
            "sample_rate": config.narrator_sample_rate,
            "sample_width": config.narrator_sample_width,
            "channels": config.narrator_channels,
        },
        "clips": [
            {
                "request_id": clip.request_id,
                "source_order": clip.source_order,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
                "clip_hash": sha256_file(clip.clip_path),
                "clip_format": clip.clip_format.value,
                "sample_rate": clip.sample_rate,
                "channels": clip.channels,
                "duration_ms": clip.duration_ms,
            }
            for clip in ordered
        ],
    }
    return _digest(payload)


def mix_fingerprint(
    *,
    narration_fingerprint_value: str,
    narrator_path: Path,
    original_audio_path: Path | None,
    channel_plan: ChannelPlan,
    config: AudioConfig,
) -> str:
    """Hash only inputs and settings that affect the final sidecar."""
    original_identity: dict[str, object] | None = None
    if original_audio_path is not None:
        original_identity = {
            "hash": sha256_file(original_audio_path),
            "size": original_audio_path.stat().st_size,
        }
    payload: dict[str, object] = {
        "algorithm_version": _MIX_ALGORITHM_VERSION,
        "narration_fingerprint": narration_fingerprint_value,
        "narrator_hash": sha256_file(narrator_path),
        "original_audio": original_identity,
        "gain": {
            "narrator_base_db": _canonical_float(config.narrator_mix_base_gain_db),
            "voice_offset_db": _canonical_float(config.voice_mix_offset_db),
            "original_db": _canonical_float(config.original_gain_db),
        },
        "amix": {
            "duration": "longest",
            "dropout_transition": 2,
            "normalize": True,
        },
        "channel_plan": {
            "output_layout": channel_plan.output_layout,
            "output_channels": channel_plan.output_channels,
            "source_filter": channel_plan.source_filter,
            "narrator_filter": channel_plan.narrator_filter,
        },
        "output": {
            "profile": config.codec_profile.value,
            "bitrate": config.bitrate,
            "flac_compression_level": config.flac_compression_level,
        },
    }
    return _digest(payload)


def sha256_file(path: Path) -> str:
    """Return a prefixed streaming SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(_COPY_BUFFER_BYTES):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _canonical_float(value: float) -> str:
    return format(value, ".17g")


def _digest(payload: dict[str, object]) -> str:
    encoded: bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
