"""Owner's dialogue font and the dialogue styles drawn with it."""

from __future__ import annotations

import re
from collections import Counter
from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.fonts import FontFace, polish_missing, read_faces
from anishift.services.fonts.index import family_name
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.text import RE_TAG_BLOCK

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

    from pysubs2 import SSAEvent, SSAFile, SSAStyle

    from anishift.services.subtitles.types import Decision, LayoutReport

__all__ = ["DIALOGUE_CLONE_SUFFIX", "DialogueFont", "restyle_dialogue"]

# ── Constants ─────────────────────────────────────────────────────────────────

DIALOGUE_CLONE_SUFFIX: Final[str] = " (dialog)"
"""Suffix of the style cloned for the dialogue font, ignored when matching a translation to its source."""

_RE_NAMED_RESET: Final[re.Pattern[str]] = re.compile(r"\\r([^\\}]+)")
"""ASS ``\\r<style>`` reset naming the style it restores, inside one override block."""


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
        name: str = style + DIALOGUE_CLONE_SUFFIX
        while name in taken:
            name += DIALOGUE_CLONE_SUFFIX
        taken.add(name)
        clones[style] = name
    return clones


def _with_clones(styles: Mapping[str, SSAStyle], clones: Mapping[str, str], family: str) -> dict[str, SSAStyle]:
    result: dict[str, SSAStyle] = {}
    for name, style in styles.items():
        result[name] = style
        if name in clones:
            clone: SSAStyle = style.copy()
            clone.fontname = family
            result[clones[name]] = clone
    return result


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
