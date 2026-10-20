"""Owner's dialogue font and the dialogue and plain sign styles drawn with it."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.fonts import FontFace, polish_missing, read_faces
from anishift.services.fonts.index import family_name
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.text import RE_TAG_BLOCK, is_drawing, is_karaoke, visible_text

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

    from pysubs2 import SSAEvent, SSAFile, SSAStyle

    from anishift.services.subtitles.types import Decision, LayoutReport

__all__ = ["DialogueFont", "attached_names", "clone_source", "restyle_dialogue", "restyle_signs", "with_family"]

# ── Constants ─────────────────────────────────────────────────────────────────

_CLONE_LABEL: Final[str] = "dialog"
"""Word in the parenthesized suffix of a style cloned for the dialogue font, numbered from 2 when a name is taken."""

_RE_CLONE: Final[re.Pattern[str]] = re.compile(rf"(?P<source>.+) \({_CLONE_LABEL}(?: (?:[2-9]|[1-9][0-9]+))?\)")
"""Whole name of a dialogue clone, capturing the style it was made from."""

_RE_NAMED_RESET: Final[re.Pattern[str]] = re.compile(r"\\r([^\\}]+)")
"""ASS ``\\r<style>`` reset naming the style it restores, inside one override block."""

_RE_FONT_NAME: Final[re.Pattern[str]] = re.compile(r"\\fn([^\\}]*)")
"""ASS ``\\fn<name>`` font override; an empty name restores the style font."""

_RE_FITTED: Final[re.Pattern[str]] = re.compile(r"\\(?:i?clip|fr[xy]|fa[xy]|t\s*\(|move\s*\()")
"""Overrides fitting a sign to the picture: masks, perspective, shear, animation and motion."""

_RE_SOFTENED: Final[re.Pattern[str]] = re.compile(r"\\(?:blur|be)\s*([0-9]*\.?[0-9]+)")
"""Edge blur override with its strength."""

_RE_WORD_COLOUR: Final[re.Pattern[str]] = re.compile(r"[^\s}]\{[^}]*\\1?c\s*&H[^}]*\}(?=[^\s{])")
"""Primary colour change between two letters of one word, the mark of a gradient."""

_SYSTEM_FAMILIES: Final[frozenset[str]] = frozenset(
    {
        "arial", "arial black", "arial narrow", "times new roman", "verdana", "georgia", "trebuchet ms",
        "comic sans ms", "tahoma", "segoe ui", "calibri", "cambria", "garamond", "courier new", "impact", "roboto",
        "open sans", "noto sans", "noto serif", "liberation sans", "liberation serif", "dejavu sans",
    }
)  # fmt: skip
"""Casefolded common system font families that mark no typesetting work even when a release attaches them."""


@dataclass(frozen=True, slots=True)
class DialogueFont:
    """Family of the owner's dialogue font as written and every file of that family drawing all Polish letters."""

    family: str
    files: tuple[Path, ...]

    @classmethod
    def from_file(cls, path: Path) -> DialogueFont:
        """Read the chosen font file and its sibling variants; raise SubtitleError when the file is unusable."""
        if not path.is_file():
            raise _unusable(ErrorCode.FILE_NOT_FOUND, f"Dialogue font file is missing: {path.name}")
        family: str = family_name(path)
        faces: tuple[FontFace, ...] = read_faces(path)
        if not family or not faces:
            raise _unusable(ErrorCode.CONFIG_INVALID, f"Dialogue font has no readable face with a family: {path.name}")
        if any(polish_missing(face) for face in faces):
            raise _unusable(ErrorCode.CONFIG_INVALID, f"Dialogue font lacks Polish letters: {path.name}")
        variants: list[Path] = [
            sibling for sibling in sorted(path.parent.iterdir()) if sibling != path and _is_variant(sibling, family)
        ]
        return cls(family, (path, *variants))


def restyle_dialogue(subs: SSAFile, decisions: Sequence[Decision], font: DialogueFont, report: LayoutReport) -> SSAFile:
    """Return a copy whose spoken lines of every mostly spoken style use that style's clone drawn with the font."""
    clones: dict[str, str] = _clone_names(subs, decisions)
    if not clones:
        return subs
    out: SSAFile = copy(subs)
    out.styles = _with_clones(subs.styles, clones, font.family)
    out.events = _restyled_events(subs.events, decisions, clones)
    report.restyled_styles += len(clones)
    return out


def attached_names(paths: Sequence[Path]) -> frozenset[str]:
    """Return the casefolded family, full and PostScript names of the font files attached to an episode."""
    return frozenset(
        name
        for path in paths
        for face in read_faces(path)
        for name in (*face.family_names, *face.full_names, face.postscript_name)
        if name
    )


def restyle_signs(
    subs: SSAFile, decisions: Sequence[Decision], font: DialogueFont, attached: frozenset[str]
) -> tuple[SSAFile, dict[int, str]]:
    """Return a copy with a clone drawn with the font for each plain sign style, and the clone of each plain sign.

    A plain sign is a displayed event drawn only with common system fonts or fonts not attached to the episode,
    without overrides fitting it to the picture and without a layered copy of its text; its clone is keyed by its
    Dialogue index.
    """
    dialogue: list[SSAEvent] = [event for event in subs.events if event.type == "Dialogue"]
    shown: list[int] = [
        index
        for index, (event, decision) in enumerate(zip(dialogue, decisions, strict=True))
        if decision != "spoken" and _plain(event, subs.styles, attached)
    ]
    by_text: defaultdict[str, list[SSAEvent]] = defaultdict(list)
    for event in dialogue:
        by_text[visible_text(event.text)].append(event)
    plain: list[int] = [
        index for index in shown if not _layered(dialogue[index], by_text[visible_text(dialogue[index].text)])
    ]
    if not plain:
        return subs, {}
    clones: dict[str, str] = {
        clone_source(name): name
        for name, style in subs.styles.items()
        if clone_source(name) != name and style.fontname == font.family
    }
    taken: set[str] = set(subs.styles)
    styles: dict[str, SSAStyle] = dict(subs.styles)
    for name in dict.fromkeys(dialogue[index].style for index in plain):
        if name not in clones:
            clones[name] = _clone_name(name, taken)
            taken.add(clones[name])
            styles[clones[name]] = _family_copy(subs.styles[name], font.family)
    out: SSAFile = copy(subs)
    out.styles = styles
    return out, {index: clones[dialogue[index].style] for index in plain}


def with_family(text: str, family: str) -> str:
    """Return the text with every named font override drawing with the family."""
    return RE_TAG_BLOCK.sub(
        lambda block: _RE_FONT_NAME.sub(lambda name: f"\\fn{family}" if name[1] else name[0], block[0]), text
    )


def clone_source(name: str) -> str:
    """Return the style a dialogue clone name was made from, or the name itself when it names no clone."""
    match: re.Match[str] | None = _RE_CLONE.fullmatch(name)
    return name if match is None else match.group("source")


def _clone_names(subs: SSAFile, decisions: Sequence[Decision]) -> dict[str, str]:
    dialogue: list[SSAEvent] = [event for event in subs.events if event.type == "Dialogue"]
    lines: Counter[str] = Counter(event.style for event in dialogue)
    spoken: Counter[str] = Counter(
        event.style for event, decision in zip(dialogue, decisions, strict=True) if decision == "spoken"
    )
    taken: set[str] = set(subs.styles)
    clones: dict[str, str] = {}
    for style in subs.styles:
        if 2 * spoken[style] <= lines[style]:
            continue
        name: str = _clone_name(style, taken)
        taken.add(name)
        clones[style] = name
    return clones


def _clone_name(style: str, taken: set[str]) -> str:
    name: str = f"{style} ({_CLONE_LABEL})"
    number: int = 1
    while name in taken:
        number += 1
        name = f"{style} ({_CLONE_LABEL} {number})"
    return name


def _with_clones(styles: Mapping[str, SSAStyle], clones: Mapping[str, str], family: str) -> dict[str, SSAStyle]:
    result: dict[str, SSAStyle] = {}
    for name, style in styles.items():
        result[name] = style
        if name in clones:
            result[clones[name]] = _family_copy(style, family)
    return result


def _family_copy(style: SSAStyle, family: str) -> SSAStyle:
    clone: SSAStyle = style.copy()
    clone.fontname = family
    return clone


def _plain(event: SSAEvent, styles: Mapping[str, SSAStyle], attached: frozenset[str]) -> bool:
    style: SSAStyle | None = styles.get(event.style)
    if style is None or is_drawing(event.text) or is_karaoke(event.text):
        return False
    tags: str = "".join(RE_TAG_BLOCK.findall(event.text))
    names: list[str] = [style.fontname, *(name for name in _RE_FONT_NAME.findall(tags) if name)]
    keys: set[str] = {name.strip().lstrip("@").casefold() for name in names}
    if keys & attached - _SYSTEM_FAMILIES:
        return False
    softened: bool = any(float(strength) > 0 for strength in _RE_SOFTENED.findall(tags))
    return not (softened or _RE_FITTED.search(tags) or _RE_WORD_COLOUR.search(event.text))


def _layered(event: SSAEvent, same_text: Sequence[SSAEvent]) -> bool:
    return any(
        other.layer != event.layer and other.start < event.end and event.start < other.end for other in same_text
    )


def _restyled_events(
    events: Sequence[SSAEvent], decisions: Sequence[Decision], clones: Mapping[str, str]
) -> list[SSAEvent]:
    remaining: Iterator[Decision] = iter(decisions)
    result: list[SSAEvent] = []
    for event in events:
        if event.type != "Dialogue":
            result.append(event)
            continue
        moves: bool = next(remaining) == "spoken" and event.style in clones
        result.append(_moved(event, clones) if moves else event)
    return result


def _moved(event: SSAEvent, clones: Mapping[str, str]) -> SSAEvent:
    moved: SSAEvent = event.copy()
    moved.style = clones[event.style]
    moved.text = RE_TAG_BLOCK.sub(
        lambda block: _RE_NAMED_RESET.sub(lambda reset: _reset_to(reset, clones), block.group()), event.text
    )
    return moved


def _reset_to(reset: re.Match[str], clones: Mapping[str, str]) -> str:
    target: str | None = clones.get(reset.group(1))
    return reset.group() if target is None else f"\\r{target}"


def _is_variant(path: Path, family: str) -> bool:
    if not path.is_file() or family_name(path).casefold() != family.casefold():
        return False
    faces: tuple[FontFace, ...] = read_faces(path)
    key: str = family.casefold()
    return bool(faces) and all(key in face.family_names and not polish_missing(face) for face in faces)


def _unusable(code: ErrorCode, message: str) -> SubtitleError:
    return SubtitleError(context=ErrorContext(code=code, message=message))
