"""Owner's dialogue font and the dialogue styles drawn with it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.fonts import FontFace, polish_missing, read_faces
from anishift.services.subtitles.errors import SubtitleError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from pysubs2 import SSAFile

    from anishift.services.subtitles.types import Decision, LayoutReport

__all__ = ["DialogueFont", "restyle_dialogue"]


@dataclass(frozen=True, slots=True)
class DialogueFont:
    """Family of the owner's dialogue font and every file of that family drawing all Polish letters."""

    family: str
    files: tuple[Path, ...]

    @classmethod
    def from_file(cls, path: Path) -> DialogueFont:
        """Read the chosen font file and its sibling variants; raise SubtitleError when the file is unusable."""
        if not path.is_file():
            raise _unusable(ErrorCode.FILE_NOT_FOUND, f"Dialogue font file is missing: {path.name}")
        faces: tuple[FontFace, ...] = read_faces(path)
        if not faces:
            raise _unusable(ErrorCode.CONFIG_INVALID, f"Dialogue font has no readable face with a family: {path.name}")
        family: str = min(faces[0].family_names)
        if any(polish_missing(face) for face in faces):
            raise _unusable(ErrorCode.CONFIG_INVALID, f"Dialogue font lacks Polish letters: {path.name}")
        variants: list[Path] = [
            sibling for sibling in sorted(path.parent.iterdir()) if sibling != path and _is_variant(sibling, family)
        ]
        return cls(family, (path, *variants))


def restyle_dialogue(subs: SSAFile, decisions: Sequence[Decision], font: DialogueFont, report: LayoutReport) -> SSAFile:
    """Return the subtitle file to lay out with the dialogue font; its styles stay unchanged."""
    return subs


def _is_variant(path: Path, family: str) -> bool:
    if not path.is_file():
        return False
    faces: tuple[FontFace, ...] = read_faces(path)
    return bool(faces) and all(family in face.family_names and not polish_missing(face) for face in faces)


def _unusable(code: ErrorCode, message: str) -> SubtitleError:
    return SubtitleError(context=ErrorContext(code=code, message=message))
