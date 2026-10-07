"""Resolve scoped language declarations and rank release quality without I/O."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from math import log1p
from types import MappingProxyType
from typing import Final

__all__ = [
    "DUBBED_RE",
    "AudioClass",
    "LanguageDeclaration",
    "LanguageSource",
    "PolishClass",
    "ReleaseTraits",
    "ResolutionClass",
    "class_key",
    "language_code",
    "name_declaration",
    "quality_score",
    "release_traits",
    "resolution",
    "resolution_class",
    "seed_points",
    "tag_declaration",
]


class LanguageSource(StrEnum):
    """Origin of a language declaration within its file or release scope."""

    TSUKIHIME = "tsukihime"
    NEKOBT = "nekobt"
    FILE_NAME = "file_name"
    RELEASE_NAME = "release_name"
    TORRENTIO_FLAG = "torrentio_flag"


@dataclass(frozen=True, slots=True)
class LanguageDeclaration:
    """Languages advertised for one torrent file or, with no file, the whole release."""

    source: LanguageSource
    file: str | None
    subtitles: frozenset[str] | None
    audio: frozenset[str] | None
    complete_audio: bool
    polish_bare: bool = False
    partial_subtitles: bool = False


class PolishClass(IntEnum):
    """Subtitle preference from confirmed Polish to no Polish declaration."""

    POLISH = 0
    BARE = 1
    NONE = 2


class AudioClass(IntEnum):
    """Preference for original audio over acceptable Korean audio."""

    ORIGINAL = 0
    KOREAN = 1


class ResolutionClass(IntEnum):
    """Owner preference for known resolution heights before unknown resolution."""

    FULL_HD = 0
    UHD = 1
    HD = 2
    OTHER = 3
    UNKNOWN = 4


@dataclass(frozen=True, slots=True)
class ReleaseTraits:
    """Resolved quality and usability facts of the selected release file."""

    polish: PolishClass
    polish_audio_beside_original: bool
    english_subtitles: bool
    audio: AudioClass
    dub_only: bool
    raw: bool
    hardsub: bool
    resolution: int | None
    platform: bool
    bluray: bool
    seeders: int | None


# ── Constants ─────────────────────────────────────────────────────────────────

_SUBTAG_SEPARATOR: Final[re.Pattern[str]] = re.compile(r"[-_]")
"""Separator between the primary language and the region or script subtags of a language tag."""

DECLARATION_PRIORITY: Final[Mapping[LanguageSource, int]] = MappingProxyType(
    {
        LanguageSource.TSUKIHIME: 0,
        LanguageSource.NEKOBT: 1,
        LanguageSource.FILE_NAME: 2,
        LanguageSource.RELEASE_NAME: 3,
        LanguageSource.TORRENTIO_FLAG: 4,
    }
)
"""Source precedence within one scope, with an unqualified Torrentio flag last."""

POLISH_POINTS: Final[float] = 40.0
"""Points for confirmed Polish subtitles."""

POLISH_BARE_POINTS: Final[float] = 20.0
"""Points for Polish without a declared role."""

POLISH_AUDIO_POINTS: Final[float] = 15.0
"""Points for Polish audio alongside original or acceptable Korean audio."""

ENGLISH_POINTS: Final[float] = 10.0
"""Points for English subtitles when Polish subtitles are not confirmed."""

FULL_HD_POINTS: Final[float] = 20.0
"""Points for a declared 1080-line image."""

UHD_POINTS: Final[float] = 5.0
"""Points for a declared 2160-line image."""

PLATFORM_POINTS: Final[float] = 5.0
"""Points for a WEB release naming a supported streaming platform."""

BLURAY_POINTS: Final[float] = -10.0
"""Penalty for Blu-ray or remux releases, applied once."""

MAX_SEED_POINTS: Final[float] = 10.0
"""Maximum logarithmic availability bonus."""

UNKNOWN_SEED_POINTS: Final[float] = 5.0
"""Availability bonus when no source reports seeders."""

SEED_SATURATION: Final[int] = 50
"""Seeder count at which availability points stop growing."""

_REFERENCE_HEIGHT: Final[int] = 1080
"""Height closest to which other known resolutions are preferred."""

_HEIGHT_4K: Final[int] = 2160
"""Height meant by a 4K declaration."""

_PREFERRED_RESOLUTIONS: Final[Mapping[int, ResolutionClass]] = MappingProxyType(
    {1080: ResolutionClass.FULL_HD, 2160: ResolutionClass.UHD, 720: ResolutionClass.HD}
)
"""Owner order of the preferred resolution heights."""

_RESOLUTION_HEIGHT: Final[re.Pattern[str]] = re.compile(r"(?i)(?<!\d)(360|480|576|720|1080|1440|2160)[pi]\b")
"""Declared height written as a progressive or interlaced resolution."""

_RESOLUTION_FRAME: Final[re.Pattern[str]] = re.compile(r"(?i)\b\d{3,4}[x×](360|480|576|720|1080|1440|2160)\b")
"""Declared height written as a frame size."""

_RESOLUTION_4K: Final[re.Pattern[str]] = re.compile(r"(?i)\b4k\b")
"""Declared 4K resolution."""

DUBBED_RE: Final[re.Pattern[str]] = re.compile(r"\[Dub\]|(?<!\w)(?:(?:English|Eng)\s+Dub|Dubbed)(?!\w)", re.IGNORECASE)
"""Legacy dubbed-audio markers shared with the torrent release-name parser."""

DUB_MARKERS: Final[tuple[str, ...]] = ("PL dub", "Polish dub", "Dubbing PL")
"""Polish dubbing markers supplementing the legacy dubbed-audio markers."""

_PL_DUB_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<!\w)(?:" + "|".join(marker.replace(" ", r"[ ._-]+") for marker in DUB_MARKERS) + r")(?!\w)",
    re.IGNORECASE,
)
"""Role-qualified Polish dubbing declarations."""

_PL_SUB_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<!\w)(?:Napisy[ ._-]+PL|PL[ ._-]*sub|Polish[ ._-]+sub)(?:s|titles)?(?!\w)"
)
"""Explicit Polish subtitle tokens."""

_PL_AUDIO_RE: Final[re.Pattern[str]] = re.compile(r"(?i)(?<!\w)(?:Lektor[ ._-]+PL|Polish[ ._-]+audio)(?!\w)")
"""Partial Polish audio declarations that cannot prove original audio absent."""

_PL_BARE_RE: Final[re.Pattern[str]] = re.compile(r"(?i)(?<!\w)(?:PL|POL|Polish)(?!\w)")
"""Unqualified Polish language tokens after role-qualified tokens are removed."""

_EN_SUB_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<!\w)(?:(?:ENG|English)[ ._-]+sub(?:s|titles)?|multi(?:ple)?[ ._-]?sub(?:s|titles?)?)(?!\w)"
)
"""English subtitle declarations, including MultiSub without implying Polish."""

_DUAL_AUDIO: Final[re.Pattern[str]] = re.compile(r"(?i)\b(?:dual|multi)[ ._-]?audio\b")
"""Declaration that original audio accompanies a dub when no complete audio list exists."""

PLATFORMS: Final[tuple[str, ...]] = ("NF", "CR", "ADN", "AMZN", "HIDIVE", "BILI", "DSNP")
"""Streaming platform markers eligible for the WEB bonus."""

_PLATFORM_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\b(?:" + "|".join(PLATFORMS) + r"|Netflix|Crunchyroll)\b")
"""Whole platform tokens and the existing long Netflix and Crunchyroll names."""

_WEB_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bWEB(?:[ ._-]?(?:DL|Rip))?\b")
"""WEB provenance required alongside a platform declaration."""

_BLURAY_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\b(?:Blu[ ._-]?ray|BD(?:Rip)?|BDRemux|Remux)\b")
"""Blu-ray and remux source tokens receiving one penalty."""

_RAW_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bRAW\b")
"""Explicit RAW marker, excluding group names ending in Raws."""

_HARDSUB_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bhard[ ._-]?subs?\b")
"""Hard-coded subtitle markers in names or source tags."""

_NEKOBT_LANGUAGE_RE: Final[re.Pattern[str]] = re.compile(r"(?:^|[;{:])\s*([AFS])=([^;}]+)", re.IGNORECASE)
"""Audio, fansub and official subtitle lists in nekoBT tags."""

_HS_TAG_RE: Final[re.Pattern[str]] = re.compile(r"(?i)(?:^|[;{:])\s*HS\s*(?=[;}]|$)")
"""HardSub flag in an individual tag or a nekoBT Tags block."""


def language_code(code: str) -> str:
    """Return the lowercase primary language of a language tag, so ``pl-PL`` and ``PL`` both become ``pl``."""
    return _SUBTAG_SEPARATOR.split(code.strip(), maxsplit=1)[0].casefold()


def resolution(texts: Sequence[str]) -> int | None:
    """Return the single declared height, leaving conflicting or absent declarations unknown."""
    heights: set[int] = set()
    for text in texts:
        heights.update(int(value) for value in _RESOLUTION_HEIGHT.findall(text))
        heights.update(int(value) for value in _RESOLUTION_FRAME.findall(text))
        if _RESOLUTION_4K.search(text):
            heights.add(_HEIGHT_4K)
    return next(iter(heights)) if len(heights) == 1 else None


def resolution_class(resolution: int | None) -> tuple[ResolutionClass, int]:
    """Return the owner resolution class and distance for other known heights."""
    if resolution is None:
        return ResolutionClass.UNKNOWN, 0
    if resolution in _PREFERRED_RESOLUTIONS:
        return _PREFERRED_RESOLUTIONS[resolution], 0
    return ResolutionClass.OTHER, abs(resolution - _REFERENCE_HEIGHT)


def class_key(traits: ReleaseTraits) -> tuple[int, ...]:
    """Order resolution before Polish subtitles before original audio."""
    return (*resolution_class(traits.resolution), traits.polish, traits.audio)


def seed_points(seeders: int | None) -> float:
    """Award logarithmic availability points, saturating at fifty seeders."""
    if seeders is None:
        return UNKNOWN_SEED_POINTS
    return MAX_SEED_POINTS * min(1.0, log1p(max(0, seeders)) / log1p(SEED_SATURATION))


def quality_score(traits: ReleaseTraits) -> float:
    """Return unrounded quality points independently of episode confidence."""
    polish: float = 0.0
    if traits.polish is PolishClass.POLISH:
        polish = POLISH_POINTS
    elif traits.polish is PolishClass.BARE:
        polish = POLISH_BARE_POINTS
    height: float = FULL_HD_POINTS if traits.resolution == _REFERENCE_HEIGHT else 0.0
    if traits.resolution == _HEIGHT_4K:
        height = UHD_POINTS
    return max(
        0.0,
        polish
        + height
        + seed_points(traits.seeders)
        + POLISH_AUDIO_POINTS * traits.polish_audio_beside_original
        + ENGLISH_POINTS * (traits.english_subtitles and traits.polish is not PolishClass.POLISH)
        + PLATFORM_POINTS * traits.platform
        + BLURAY_POINTS * traits.bluray,
    )


def name_declaration(text: str, source: LanguageSource, file: str | None) -> LanguageDeclaration:
    """Read positive language tokens without treating absent subtitle tokens as an explicit exclusion."""
    text = text.replace("_", " ")
    subtitles: set[str] = set()
    if _PL_SUB_RE.search(text):
        subtitles.add("pl")
    if _EN_SUB_RE.search(text):
        subtitles.add("en")
    polish_audio: bool = bool(_PL_AUDIO_RE.search(text) or _PL_DUB_RE.search(text))
    unqualified: str = _PL_DUB_RE.sub("", _PL_AUDIO_RE.sub("", _PL_SUB_RE.sub("", text)))
    return LanguageDeclaration(
        source,
        file,
        frozenset(subtitles),
        frozenset({"pl"}) if polish_audio else None,
        complete_audio=False,
        polish_bare=bool(_PL_BARE_RE.search(unqualified)),
        partial_subtitles=True,
    )


def tag_declaration(tags: Sequence[str]) -> LanguageDeclaration:
    """Combine nekoBT fansub and official subtitle lists while retaining the complete audio list."""
    subtitles: set[str] = set()
    audio: set[str] = set()
    for role, values in _NEKOBT_LANGUAGE_RE.findall(";".join(tags)):
        languages: set[str] = {language_code(code) for code in values.split(",") if code.strip()}
        (audio if role.casefold() == "a" else subtitles).update(languages)
    return LanguageDeclaration(LanguageSource.NEKOBT, None, frozenset(subtitles), frozenset(audio), complete_audio=True)


def _scoped_declarations(
    names: Sequence[str],
    tags: Sequence[str],
    declarations: Sequence[LanguageDeclaration],
    *,
    file: str | None,
    pack: bool,
) -> list[LanguageDeclaration]:
    combined: list[LanguageDeclaration] = [
        *declarations,
        tag_declaration(tags),
        name_declaration("\n".join(names), LanguageSource.RELEASE_NAME, None),
    ]
    if file is not None:
        combined.append(name_declaration(file.replace("\\", "/").rsplit("/", 1)[-1], LanguageSource.FILE_NAME, file))
    selected: list[LanguageDeclaration] = [
        declaration
        for declaration in combined
        if (declaration.file is not None and declaration.file == file) or (declaration.file is None and not pack)
    ]
    return sorted(
        selected, key=lambda declaration: (declaration.file is None, DECLARATION_PRIORITY[declaration.source])
    )


def _declared(
    declarations: Sequence[LanguageDeclaration],
    *,
    audio: bool = False,
    complete: bool = False,
) -> frozenset[str]:
    for declaration in declarations:
        languages: frozenset[str] | None = declaration.audio if audio else declaration.subtitles
        if languages and (not complete or declaration.complete_audio):
            return frozenset(language_code(code) for code in languages)
    return frozenset()


def _polish_class(declarations: Sequence[LanguageDeclaration]) -> PolishClass:
    bare_allowed: bool = True
    for declaration in declarations:
        if declaration.subtitles and "pl" in _declared((declaration,)):
            return PolishClass.POLISH
        if declaration.subtitles and not declaration.partial_subtitles:
            return PolishClass.BARE if bare_allowed and declaration.polish_bare else PolishClass.NONE
        if bare_allowed and declaration.polish_bare:
            return PolishClass.BARE
        if declaration.audio:
            bare_allowed = False
    return PolishClass.NONE


def release_traits(  # noqa: PLR0913 - explicit pure boundary mirrors the acquisition quality contract
    names: Sequence[str],
    tags: Sequence[str],
    declarations: Sequence[LanguageDeclaration],
    *,
    file: str | None,
    pack: bool,
    donghua: bool,
    seeders: int | None,
) -> ReleaseTraits:
    """Resolve file-scoped languages first and retain exclusion evidence from every source."""
    scoped: list[LanguageDeclaration] = _scoped_declarations(names, tags, declarations, file=file, pack=pack)
    subtitles: frozenset[str] = _declared(scoped)
    audio: frozenset[str] = _declared(scoped, audio=True)
    complete_audio: frozenset[str] = _declared(scoped, audio=True, complete=True)
    original_audio: frozenset[str] = frozenset({"ja", "zh"}) if donghua else frozenset({"ja"})
    acceptable_audio: frozenset[str] = original_audio | {"ko"}
    file_names: tuple[str, ...] = (file.replace("\\", "/").rsplit("/", 1)[-1],) if file is not None else ()
    all_names: tuple[str, ...] = tuple(name.replace("_", " ") for name in (*names, *file_names))
    texts: tuple[str, ...] = (*all_names, *tags)
    language_texts: tuple[str, ...] = tuple(name.replace("_", " ") for name in file_names) if pack else texts
    dual: bool = any(_DUAL_AUDIO.search(text) for text in language_texts)
    dubbed: bool = any(DUBBED_RE.search(text) or _PL_DUB_RE.search(text) for text in language_texts)
    dub_only: bool = not bool(complete_audio & acceptable_audio) if complete_audio else dubbed and not dual
    beside_original: bool = bool(complete_audio & acceptable_audio) if complete_audio else dual
    effective_audio: frozenset[str] = complete_audio or audio
    return ReleaseTraits(
        polish=_polish_class(scoped),
        polish_audio_beside_original="pl" in audio and beside_original,
        english_subtitles="en" in subtitles,
        audio=AudioClass.KOREAN
        if "ko" in effective_audio and not effective_audio & original_audio
        else AudioClass.ORIGINAL,
        dub_only=dub_only,
        raw=any(_RAW_RE.search(text) for text in texts),
        hardsub=any(_HARDSUB_RE.search(text) for text in texts) or any(_HS_TAG_RE.search(tag) for tag in tags),
        resolution=resolution((*names, *((file,) if file is not None else ()))),
        platform=any(_WEB_RE.search(name) and _PLATFORM_RE.search(name) for name in all_names),
        bluray=any(_BLURAY_RE.search(name) for name in all_names),
        seeders=seeders,
    )
