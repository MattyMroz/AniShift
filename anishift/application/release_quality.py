"""Resolve scoped language declarations and rank release quality without I/O."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Final

from anishift.application.episode_identity import FIRST_BRACKET

__all__ = [
    "DUBBED_RE",
    "GROUP_ORDER",
    "AudioClass",
    "LanguageDeclaration",
    "LanguageSource",
    "Origin",
    "PolishClass",
    "ReleaseTraits",
    "ResolutionClass",
    "SeedClass",
    "audio_text",
    "class_key",
    "language_code",
    "low_transcode",
    "name_declaration",
    "order_tail",
    "quality_score",
    "release_traits",
    "resolution",
    "resolution_class",
    "seed_class",
    "seed_points",
    "subtitles_text",
    "tag_declaration",
    "untouched_bluray",
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


class SeedClass(IntEnum):
    """Seeding gate: seeded releases, unknown ones included, before weakly seeded ones."""

    SEEDED = 0
    WEAK = 1


class Origin(StrEnum):
    """Provenance a release name declares: a source file, no marker (also an original), or a transcode."""

    SOURCE = "source"
    UNMARKED = "unmarked"
    TRANSCODE = "transcode"


@dataclass(frozen=True, slots=True)
class ReleaseTraits:
    """Resolved quality and usability facts of the selected release file, with its size standing in the offer."""

    polish: PolishClass
    polish_audio_beside_original: bool
    english_subtitles: bool
    audio: AudioClass
    dub_only: bool
    raw: bool
    hardsub: bool
    resolution: int | None
    bluray: bool
    seeders: int | None
    subtitles_listed: bool
    origin: Origin = Origin.UNMARKED
    audio_languages: tuple[str, ...] = ()
    subtitle_languages: tuple[str, ...] = ()
    group: str | None = None
    small: bool = False
    size_rank: int | None = None
    bluray_preferred: bool = False


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

BLURAY_POINTS: Final[float] = -10.0
"""Penalty for Blu-ray or remux releases, applied once unless the owner prefers them."""

MAX_SEED_POINTS: Final[float] = 10.0
"""Availability points of a release with thirty seeders or more."""

UNKNOWN_SEED_POINTS: Final[float] = 5.0
"""Availability points when no source reports seeders."""

SEEDED_FROM: Final[int] = 20
"""Fewest seeders of a seeded release; fewer make it weakly seeded."""

_SEEDED_POINTS: Final[float] = 5.0
"""Availability points of a release with exactly the seeded threshold."""

_SEEDED_POINTS_PER_SEED: Final[float] = 0.5
"""Availability points each seeder above the seeded threshold adds, up to the maximum."""

_WEAK_POINTS_PER_SEED: Final[float] = 0.25
"""Availability points each seeder of a weakly seeded release earns."""

GROUP_ORDER: Final[tuple[str, ...]] = ("toonshub", "subsplus+", "varyg", "anozu", "subsplease", "erai-raws")
"""Casefolded release groups preferred in this order once bitrate ties; every other group follows equally."""

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

_UNLISTED_AUDIO: Final[str] = "?"
"""Audio language entry for the tracks a dual- or multi-audio name leaves unlisted beside the original."""

_NAMED_AUDIO: Final[tuple[str, ...]] = ("ja", "zh", "ko", "en", "pl")
"""Audio languages the release list names in this order after the original; it only counts the others."""

_NAMED_SUBTITLES: Final[tuple[str, ...]] = ("pl", "en")
"""Subtitle languages the release list names in this order; it only counts the others."""

_SOURCE_RE: Final[re.Pattern[str]] = re.compile(r"(?i)(?<![a-z0-9])WEB[ ._-]?DL(?![a-z0-9])|remux(?![a-z0-9])")
"""Source-file markers: a streaming download or a disc remux."""

_GROUP_ENCODE_RE: Final[re.Pattern[str]] = re.compile(r"(?i)(?<![a-z0-9])x26[45](?![a-z0-9])")
"""Encoder markers of a group's own compression, which a source-file marker cannot outweigh."""

_TRANSCODE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<![a-z0-9])(?:WEB[ ._-]?Rip|BD[ ._-]?Rip|x26[45]|HEVC|H[ ._]?265|AV1|10[ ._-]?bits?|Hi(?:10|444)P?"
    r"|Ma10p|Opus|Encode)(?![a-z0-9])"
)
"""Compression markers of a transcode, read only where no source-file marker applies."""

_SCENE_GROUP_RE: Final[re.Pattern[str]] = re.compile(r"-([A-Za-z0-9][A-Za-z0-9+]*)(?:\.(?:mkv|mp4))?\s*$")
"""Group a scene release name ends with, as in ``H.264-VARYG``."""

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


def seed_class(seeders: int | None) -> SeedClass:
    """Return weakly seeded below the seeded threshold; unknown seeders count as seeded."""
    return SeedClass.WEAK if seeders is not None and seeders < SEEDED_FROM else SeedClass.SEEDED


def class_key(traits: ReleaseTraits) -> tuple[int, ...]:
    """Order resolution, an original before a transcode, seeding, a preferred Blu-ray, Polish subtitles, then audio."""
    return (
        *resolution_class(traits.resolution),
        traits.origin is Origin.TRANSCODE,
        seed_class(traits.seeders),
        not traits.bluray_preferred,
        traits.polish,
        traits.audio,
    )


def order_tail(traits: ReleaseTraits, quality: float) -> tuple[int, ...]:
    """Order a small file last, quality then bitrate (reversed for a preferred Blu-ray), group, then seeds."""
    seeders: int = -1 if traits.seeders is None else traits.seeders
    group: int = GROUP_ORDER.index(traits.group) if traits.group in GROUP_ORDER else len(GROUP_ORDER)
    points: tuple[int, ...] = (-round(quality),)
    bitrate: tuple[int, ...] = (traits.size_rank is None, traits.size_rank or 0)
    measures: tuple[int, ...] = (*bitrate, *points) if traits.bluray_preferred else (*points, *bitrate)
    return (traits.small, *measures, group, -seeders)


def untouched_bluray(traits: ReleaseTraits) -> bool:
    """Whether the release is a Blu-ray or remux that its name does not mark as a transcode."""
    return traits.bluray and traits.origin is not Origin.TRANSCODE


def low_transcode(traits: ReleaseTraits) -> bool:
    """Whether the release is a transcode below 1080 lines, which is never shown, suggested or admitted."""
    return traits.origin is Origin.TRANSCODE and traits.resolution is not None and traits.resolution < _REFERENCE_HEIGHT


def seed_points(seeders: int | None) -> float:
    """Award availability points: a quarter per seeder below twenty, then five rising to ten at thirty."""
    if seeders is None:
        return UNKNOWN_SEED_POINTS
    count: int = max(0, seeders)
    if count < SEEDED_FROM:
        return count * _WEAK_POINTS_PER_SEED
    return min(MAX_SEED_POINTS, _SEEDED_POINTS + _SEEDED_POINTS_PER_SEED * (count - SEEDED_FROM))


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
        + BLURAY_POINTS * (traits.bluray and not traits.bluray_preferred),
    )


def audio_text(traits: ReleaseTraits) -> str:
    """Return the audio languages as the release list shows them, such as ``JA+EN+PL+11``, ``JA+?`` or ``?``."""
    languages: tuple[str, ...] = traits.audio_languages
    if not languages:
        return "?"
    first: tuple[str, ...] = languages[:1] if languages[0] in _NAMED_AUDIO else ()
    named: tuple[str, ...] = (*first, *(code for code in _NAMED_AUDIO if code in languages and code not in first))
    return _languages_text(named, tuple(code for code in languages if code not in named))


def subtitles_text(traits: ReleaseTraits) -> str:
    """Return the subtitle languages as the release list shows them, such as ``PL+EN+15``, ``+5`` or ``—``."""
    present: dict[str, bool] = {"pl": traits.polish is not PolishClass.NONE, "en": traits.english_subtitles}
    named: tuple[str, ...] = tuple(code for code in _NAMED_SUBTITLES if present[code])
    return _languages_text(named, tuple(code for code in traits.subtitle_languages if code not in named)) or "—"


def _languages_text(named: tuple[str, ...], others: tuple[str, ...]) -> str:
    shown: str = "+".join(code.upper() for code in named)
    if not others:
        return shown
    return f"{shown}+{_UNLISTED_AUDIO if _UNLISTED_AUDIO in others else len(others)}"


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
        listed: bool = declaration.complete_audio if audio else not declaration.partial_subtitles
        if languages and (not complete or listed):
            return frozenset(language_code(code) for code in languages)
    return frozenset()


def _polish_class(declarations: Sequence[LanguageDeclaration]) -> PolishClass:
    """Return the Polish class; a Torrentio flag or bare token counts only when nothing in scope decides it."""
    bare_allowed: bool = True
    flagged: bool = False
    for declaration in declarations:
        if declaration.source is LanguageSource.TORRENTIO_FLAG:
            flagged = flagged or declaration.polish_bare
            continue
        if declaration.subtitles and "pl" in _declared((declaration,)):
            return PolishClass.POLISH
        if declaration.subtitles and not declaration.partial_subtitles:
            return PolishClass.BARE if bare_allowed and declaration.polish_bare else PolishClass.NONE
        if bare_allowed and declaration.polish_bare:
            flagged = True
            continue
        if declaration.audio:
            bare_allowed = False
    return PolishClass.BARE if flagged and bare_allowed else PolishClass.NONE


def release_traits(  # noqa: PLR0913 - explicit pure boundary mirrors the acquisition quality contract
    names: Sequence[str],
    tags: Sequence[str],
    declarations: Sequence[LanguageDeclaration],
    *,
    file: str | None,
    pack: bool,
    donghua: bool,
    seeders: int | None,
    file_names: Sequence[str] | None = None,
) -> ReleaseTraits:
    """Resolve languages scoped to *file* first; *file_names* name it, defaulting to the base name of *file*."""
    if file_names is None:
        file_names = (file.replace("\\", "/").rsplit("/", 1)[-1],) if file is not None else ()
    file_declarations: tuple[LanguageDeclaration, ...] = (
        (name_declaration("\n".join(file_names), LanguageSource.FILE_NAME, file),)
        if file is not None and file_names
        else ()
    )
    scoped: list[LanguageDeclaration] = _scoped_declarations(
        names, tags, (*declarations, *file_declarations), file=file, pack=pack
    )
    subtitles: frozenset[str] = _declared(scoped)
    listed_subtitles: frozenset[str] = _declared(scoped, complete=True)
    audio: frozenset[str] = _declared(scoped, audio=True)
    complete_audio: frozenset[str] = _declared(scoped, audio=True, complete=True)
    original_audio: frozenset[str] = frozenset({"ja", "zh"}) if donghua else frozenset({"ja"})
    acceptable_audio: frozenset[str] = original_audio | {"ko"}
    all_names: tuple[str, ...] = tuple(name.replace("_", " ") for name in (*names, *file_names))
    texts: tuple[str, ...] = (*all_names, *tags)
    language_texts: tuple[str, ...] = tuple(name.replace("_", " ") for name in file_names) if pack else texts
    dual: bool = any(_DUAL_AUDIO.search(text) for text in language_texts)
    dubbed: bool = any(DUBBED_RE.search(text) or _PL_DUB_RE.search(text) for text in language_texts)
    dub_only: bool = not bool(complete_audio & acceptable_audio) if complete_audio else dubbed and not dual
    beside_original: bool = bool(complete_audio & acceptable_audio) if complete_audio else dual
    effective_audio: frozenset[str] = complete_audio or audio
    spoken: str = "zh" if donghua else "ja"
    heard: frozenset[str] = complete_audio
    if not heard and audio:
        heard = audio if dub_only else audio | {spoken}
    elif not heard and dual:
        heard = frozenset({spoken, _UNLISTED_AUDIO})
    found: re.Match[str] | None = (FIRST_BRACKET.match(names[0]) or _SCENE_GROUP_RE.search(names[0])) if names else None
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
        resolution=resolution((*names, *file_names, *((file,) if file is not None else ()))),
        bluray=any(_BLURAY_RE.search(name) for name in all_names),
        seeders=seeders,
        subtitles_listed=bool(listed_subtitles),
        origin=_origin(all_names),
        audio_languages=tuple(sorted(heard, key=lambda code: (code != spoken, code not in acceptable_audio, code))),
        subtitle_languages=tuple(sorted(listed_subtitles)),
        group=found.group(1).strip().casefold() if found else None,
    )


def _origin(names: Sequence[str]) -> Origin:
    source: bool = any(_SOURCE_RE.search(name) for name in names)
    if source and not any(_GROUP_ENCODE_RE.search(name) for name in names):
        return Origin.SOURCE
    return Origin.TRANSCODE if any(_TRANSCODE_RE.search(name) for name in names) else Origin.UNMARKED
