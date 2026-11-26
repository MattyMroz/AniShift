"""Single source of truth for the file names of durable AniShift products."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from anishift.application.artifacts import ArtifactKind

__all__ = [
    "AUDIO_PRODUCT_PROFILES",
    "EPISODE_STEM_LIMIT",
    "MAIN_PRODUCT_PRIORITY",
    "PRODUCT_SUFFIXES",
    "SUBTITLE_FORMATS",
    "ProductName",
    "ProductSuffix",
    "classify_product",
    "episode_stem",
    "main_product",
    "product_path",
    "product_suffix",
    "safe_name_part",
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

EPISODE_STEM_LIMIT: Final[int] = 150
"""Longest stem of a downloaded episode set, so every product path stays under the Windows path limit."""

EPISODE_SEPARATOR: Final[str] = " - "
"""Join the series, the ``SxxEyy`` code and the episode title of an episode stem."""

_DASHED_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[:/\\|]")
"""Separators Windows refuses inside a file name, written as a dash."""

_QUOTE_CHARACTERS: Final[re.Pattern[str]] = re.compile(r'["`]')
"""Quotes Windows refuses or a catalogue uses for an apostrophe, written as an apostrophe."""

_DROPPED_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[<>?*\x00-\x1f]")
"""Characters Windows refuses inside a file name with no readable stand-in."""

_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
)
"""Device names Windows refuses as a file or directory name regardless of extension."""

_CUT_EDGE: Final[str] = " .-,;"
"""Characters a shortened name part never ends with."""

_PRODUCT_STEM_ENDINGS: Final[tuple[str, ...]] = tuple(
    entry.suffix[: entry.suffix.rindex(".")] for entry in PRODUCT_SUFFIXES if entry.suffix.count(".") > 1
)
"""Stem endings that turn a source name into a product name, such as ``.pl`` before ``.mkv``."""


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


def safe_name_part(text: str) -> str:
    """Return *text* as one part of a file name Windows accepts, empty when nothing usable is left."""
    cleaned: str = _DASHED_CHARACTERS.sub("-", " ".join(text.split()).replace(": ", EPISODE_SEPARATOR))
    cleaned = _DROPPED_CHARACTERS.sub("", _QUOTE_CHARACTERS.sub("'", cleaned))
    cleaned = " ".join(cleaned.split()).rstrip(". ")
    if cleaned.split(".", maxsplit=1)[0].upper() in _RESERVED_NAMES:
        return f"_{cleaned}"
    return cleaned


def episode_stem(series: str, numbering: tuple[int, int] | None, title: str | None = None) -> str:
    """Return the stem every file of one downloaded episode set shares; a film without *numbering* is its series."""
    show: str = safe_name_part(series)
    if not show:
        msg = "An episode stem needs a series title"
        raise ValueError(msg)
    if numbering is None:
        film: str = _shortened(show, EPISODE_STEM_LIMIT)
        return f"{film[: film.rindex('.')]} {film[film.rindex('.') + 1 :]}" if _names_product(film) else film
    season, episode = numbering
    code: str = f"S{season:02d}E{episode:02d}"
    base: str = f"{_shortened(show, EPISODE_STEM_LIMIT - len(EPISODE_SEPARATOR) - len(code))}{EPISODE_SEPARATOR}{code}"
    named: str = _shortened(safe_name_part(title or ""), EPISODE_STEM_LIMIT - len(base) - len(EPISODE_SEPARATOR))
    stem: str = f"{base}{EPISODE_SEPARATOR}{named}" if named else base
    return base if _names_product(stem) else stem


def _shortened(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    head: str = text[: limit + 1]
    words: str = head.rsplit(" ", maxsplit=1)[0] if " " in head else ""
    return (words or text[:limit]).rstrip(_CUT_EDGE)


def _names_product(stem: str) -> bool:
    return stem.casefold().endswith(_PRODUCT_STEM_ENDINGS)
