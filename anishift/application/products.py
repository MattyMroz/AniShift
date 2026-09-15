"""Single source of truth for the file names of durable AniShift products."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from anishift.application.artifacts import ArtifactKind

__all__ = [
    "AUDIO_PRODUCT_PROFILES",
    "MAIN_PRODUCT_PRIORITY",
    "PRODUCT_SUFFIXES",
    "SUBTITLE_FORMATS",
    "ProductName",
    "ProductSuffix",
    "classify_product",
    "main_product",
    "product_path",
    "product_suffix",
]


@dataclass(frozen=True, slots=True)
class ProductSuffix:
    """One filename ending and the product it names."""

    suffix: str
    kind: ArtifactKind
    subtitle_format: str | None = None
    audio_profile: str | None = None


@dataclass(frozen=True, slots=True)
class ProductName:
    """One durable product filename split into its stem and naming parts."""

    stem: str
    kind: ArtifactKind
    subtitle_format: str | None = None
    audio_codec: str | None = None


# ── Constants ────────────────────────────────────────────────────────────────

PRODUCT_SUFFIXES: Final[tuple[ProductSuffix, ...]] = (
    ProductSuffix(".spoken.pl.ass", ArtifactKind.SPOKEN_PL, subtitle_format="ass"),
    ProductSuffix(".spoken.pl.srt", ArtifactKind.SPOKEN_PL, subtitle_format="srt"),
    ProductSuffix(".displayed.pl.ass", ArtifactKind.DISPLAYED_PL, subtitle_format="ass"),
    ProductSuffix(".displayed.pl.srt", ArtifactKind.DISPLAYED_PL, subtitle_format="srt"),
    ProductSuffix(".pl.ass", ArtifactKind.FULL_PL, subtitle_format="ass"),
    ProductSuffix(".pl.srt", ArtifactKind.FULL_PL, subtitle_format="srt"),
    ProductSuffix(".pl.txt", ArtifactKind.TRANSLATED_TEXT),
    ProductSuffix(".pl.mkv", ArtifactKind.FINAL_MKV),
    ProductSuffix(".pl.mp4", ArtifactKind.FINAL_MP4),
    ProductSuffix(".cover.mp4", ArtifactKind.COVER_MP4),
    ProductSuffix(".m4a", ArtifactKind.NARRATION_AUDIO, audio_profile="aac"),
    ProductSuffix(".eac3", ArtifactKind.NARRATION_AUDIO, audio_profile="eac3"),
    ProductSuffix(".mp3", ArtifactKind.NARRATION_AUDIO, audio_profile="mp3"),
    ProductSuffix(".opus", ArtifactKind.NARRATION_AUDIO, audio_profile="opus"),
    ProductSuffix(".flac", ArtifactKind.NARRATION_AUDIO, audio_profile="flac"),
    ProductSuffix(".wav", ArtifactKind.NARRATION_AUDIO, audio_profile="wav"),
)
"""Every durable product ending, longer endings before the shorter ones they contain."""

SUBTITLE_FORMATS: Final[frozenset[str]] = frozenset(
    entry.subtitle_format for entry in PRODUCT_SUFFIXES if entry.subtitle_format is not None
)
"""Formats a subtitle product can be written in."""

AUDIO_PRODUCT_PROFILES: Final[frozenset[str]] = frozenset(
    entry.audio_profile for entry in PRODUCT_SUFFIXES if entry.audio_profile is not None
)
"""Narration audio profiles a product can be encoded with."""

MAIN_PRODUCT_PRIORITY: Final[tuple[ArtifactKind, ...]] = (
    ArtifactKind.FINAL_MKV,
    ArtifactKind.FINAL_MP4,
    ArtifactKind.COVER_MP4,
    ArtifactKind.NARRATION_AUDIO,
    ArtifactKind.TRANSLATED_TEXT,
    ArtifactKind.FULL_PL,
    ArtifactKind.SPOKEN_PL,
    ArtifactKind.DISPLAYED_PL,
)
"""Order in which a finished set names its headline result, playable containers before the documents beside them."""


def main_product(file_names: Sequence[str]) -> str | None:
    """Return the one finished file a completed set should open, or ``None`` when it produced no known product."""
    ranked: list[tuple[int, str]] = []
    for name in file_names:
        product: ProductName | None = classify_product(name)
        if product is None or product.kind not in MAIN_PRODUCT_PRIORITY:
            continue
        ranked.append((MAIN_PRODUCT_PRIORITY.index(product.kind), name))
    return min(ranked, default=(0, None))[1] if ranked else None


def product_suffix(kind: ArtifactKind, *, subtitle_format: str | None = None, audio_profile: str | None = None) -> str:
    """Return the ending written after the stem of the product *kind*."""
    wanted_format: str | None = None if subtitle_format is None else subtitle_format.casefold()
    wanted_profile: str | None = None if audio_profile is None else audio_profile.casefold()
    for entry in PRODUCT_SUFFIXES:
        if entry.kind is kind and entry.subtitle_format == wanted_format and entry.audio_profile == wanted_profile:
            return entry.suffix
    msg = f"No product ending for {kind.value!r} with format {subtitle_format!r} and profile {audio_profile!r}"
    raise ValueError(msg)


def product_path(
    directory: Path,
    stem: str,
    kind: ArtifactKind,
    *,
    subtitle_format: str | None = None,
    audio_profile: str | None = None,
) -> Path:
    """Return the path of the product *kind* written for *stem* inside *directory*."""
    normalized_stem: str = stem.strip()
    if not normalized_stem:
        msg = "Product stem cannot be empty"
        raise ValueError(msg)
    suffix: str = product_suffix(kind, subtitle_format=subtitle_format, audio_profile=audio_profile)
    return directory / f"{normalized_stem}{suffix}"


def classify_product(file_name: str) -> ProductName | None:
    """Return the product *file_name* names, or ``None`` for any other file."""
    lowered: str = file_name.casefold()
    for entry in PRODUCT_SUFFIXES:
        if not lowered.endswith(entry.suffix):
            continue
        stem: str = file_name[: -len(entry.suffix)].strip()
        if not stem:
            return None
        return ProductName(stem, entry.kind, entry.subtitle_format, entry.suffix[1:] if entry.audio_profile else None)
    return None
