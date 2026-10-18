"""Read font faces and choose them for ASS font requests the way libass does."""

from __future__ import annotations

import os
import struct
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from fontTools.ttLib import TTCollection, TTFont, TTLibError  # type: ignore[import-untyped]

from anishift.platform.binaries import is_windows
from anishift.services.fonts.types import FontFace, FontMatch
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

__all__ = ["FontIndex", "family_name", "polish_missing", "read_faces", "system_font_paths"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_POLISH_LETTERS: Final[str] = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
"""Polish letters a face must draw itself to avoid mixed glyphs in one word."""

_FALLBACK_FAMILY: Final[str] = "arial"
"""Family libass with DirectWrite draws unknown families and missing glyphs with."""

_REGULAR_WEIGHT: Final[int] = 400
"""Weight of a face without a weight class or bold flag."""

_BOLD_WEIGHT: Final[int] = 700
"""Weight an ASS bold request asks for."""

_FAUX_BOLD_MARGIN: Final[int] = 150
"""Requested weight above the face weight at which libass emboldens the face."""

_FAUX_BOLD_GAIN: Final[int] = 120
"""Weight libass credits a face it will embolden when scoring family variants."""

_WEIGHT_SCORE: Final[tuple[int, int]] = (73, 256)
"""libass weight mismatch score per weight unit as numerator and denominator."""

_MISSING_ITALIC_SCORE: Final[int] = 1
"""libass penalty for an upright face answering an italic request."""

_UNWANTED_ITALIC_SCORE: Final[int] = 4
"""libass penalty for an italic face answering an upright request."""

_LEGACY_WEIGHTS: Final[Mapping[int, int]] = MappingProxyType(
    {1: 100, 2: 200, 3: 300, 4: 350, 5: 400, 6: 600, 7: 700, 8: 800, 9: 900}
)
"""libass weights for one-digit OS/2 ``usWeightClass`` values."""

_SELECTION_ITALIC: Final[int] = 1
"""OS/2 ``fsSelection`` italic bit."""

_SELECTION_BOLD: Final[int] = 1 << 5
"""OS/2 ``fsSelection`` bold bit."""

_MAC_STYLE_BOLD: Final[int] = 1
"""``head.macStyle`` bold bit read when the font has no OS/2 table."""

_MAC_STYLE_ITALIC: Final[int] = 2
"""``head.macStyle`` italic bit read when the font has no OS/2 table."""

_MAC_PLATFORM: Final[int] = 1
"""Name table platform of Macintosh records, read only for a PostScript name missing on Windows."""

_WINDOWS_PLATFORM: Final[int] = 3
"""Name table platform of Windows records, the only one libass reads names from."""

_FAMILY_NAME_ID: Final[int] = 1
"""Name table identifier of the family name."""

_FULL_NAME_ID: Final[int] = 4
"""Name table identifier of the full name."""

_POSTSCRIPT_NAME_ID: Final[int] = 6
"""Name table identifier of the PostScript name."""

_POSTSCRIPT_OUTLINE_TABLES: Final[tuple[str, ...]] = ("CFF ", "CFF2")
"""Outline tables of faces libass matches by PostScript name instead of full name."""

_SIGNED_SHORT: Final[int] = 0x8000
"""First unsigned 16-bit value that libass reads as negative."""

_COLLECTION_TAG: Final[bytes] = b"ttcf"
"""Leading bytes of a TrueType or OpenType collection."""

_FONT_SUFFIXES: Final[frozenset[str]] = frozenset({".ttf", ".otf", ".ttc", ".otc"})
"""Font file suffixes taken from system font folders."""

_WINDOWS_DIR: Final[str] = r"C:\Windows"
"""Windows folder used when ``WINDIR`` is not set."""

FONT_READ_ERRORS: Final[tuple[type[Exception], ...]] = (
    OSError, TTLibError, KeyError, ValueError, AssertionError, IndexError, struct.error,
)  # fmt: skip
"""Failures fontTools raises for missing, damaged or non-font files."""


# ── Faces ─────────────────────────────────────────────────────────────────────


def read_faces(path: Path) -> tuple[FontFace, ...]:
    """Read every usable face of a font file; a missing or unreadable file gives no faces."""
    faces: tuple[FontFace | None, ...] = _read_fonts(path, lambda font, index: _face(font, path, index))
    return tuple(face for face in faces if face is not None)


def polish_missing(face: FontFace) -> str:
    """Return the Polish letters the face cannot draw."""
    return "".join(letter for letter in _POLISH_LETTERS if ord(letter) not in face.codepoints)


def family_name(path: Path) -> str:
    """Return the first Windows family name of the file's first face as written, empty when it has none."""
    families: tuple[list[str], ...] = _read_fonts(
        path,
        lambda font, _: [
            record.toUnicode(errors="ignore")
            for record in font["name"].names
            if record.platformID == _WINDOWS_PLATFORM and record.nameID == _FAMILY_NAME_ID
        ],
    )
    first: list[str] = families[0] if families else []
    return next((name for name in first if name), "")


def system_font_paths() -> tuple[Path, ...]:
    """Return font files installed for all users and for the current user on Windows."""
    if not is_windows():
        return ()
    folders: list[Path] = [Path(os.environ.get("WINDIR", _WINDOWS_DIR)) / "Fonts"]
    local: str | None = os.environ.get("LOCALAPPDATA")
    if local:
        folders.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    files: list[Path] = [path for folder in folders if folder.is_dir() for path in sorted(folder.iterdir())]
    return tuple(path for path in files if path.suffix.casefold() in _FONT_SUFFIXES)


def _read_fonts[T](path: Path, read: Callable[[Any, int], T]) -> tuple[T, ...]:
    try:
        with _open_fonts(path) as fonts:
            return tuple(read(font, index) for index, font in enumerate(fonts))
    except FONT_READ_ERRORS as error:
        logger.debug("Font file skipped", file=path.name, reason=type(error).__name__)
        return ()


@contextmanager
def _open_fonts(path: Path) -> Iterator[Sequence[Any]]:
    with path.open("rb") as handle:
        collection: bool = handle.read(len(_COLLECTION_TAG)) == _COLLECTION_TAG
        handle.seek(0)
        yield TTCollection(handle, lazy=True).fonts if collection else [TTFont(handle, lazy=True)]


def _face(font: Any, path: Path, index: int) -> FontFace | None:
    families, full_names, postscript_name = _names(font)
    ascent, descent = _vertical_metrics(font)
    units_per_em: int = font["head"].unitsPerEm
    if not families or units_per_em <= 0 or ascent + descent <= 0:
        return None
    weight, bold, italic = _style(font)
    cmap: Mapping[int, str] = font.getBestCmap() or {}
    return FontFace(
        path=path,
        face_index=index,
        family_names=families,
        full_names=full_names,
        postscript_name=postscript_name,
        weight=weight,
        bold=bold,
        italic=italic,
        units_per_em=units_per_em,
        ascent=ascent,
        descent=descent,
        postscript_outlines=any(table in font for table in _POSTSCRIPT_OUTLINE_TABLES),
        codepoints=frozenset(cmap),
    )


def _names(font: Any) -> tuple[frozenset[str], frozenset[str], str | None]:
    records: list[Any] = font["name"].names
    windows: list[Any] = [record for record in records if record.platformID == _WINDOWS_PLATFORM]
    mac: list[Any] = [record for record in records if record.platformID == _MAC_PLATFORM]
    postscript: list[str] = _texts(windows, _POSTSCRIPT_NAME_ID) or _texts(mac, _POSTSCRIPT_NAME_ID)
    families: frozenset[str] = frozenset(_texts(windows, _FAMILY_NAME_ID))
    return families, frozenset(_texts(windows, _FULL_NAME_ID)), postscript[0] if postscript else None


def _texts(records: Iterable[Any], name_id: int) -> list[str]:
    texts: list[str] = [record.toUnicode(errors="ignore").casefold() for record in records if record.nameID == name_id]
    return [text for text in texts if text]


def _style(font: Any) -> tuple[int, bool, bool]:
    if "OS/2" not in font:
        mac_style: int = font["head"].macStyle
        mac_bold: bool = bool(mac_style & _MAC_STYLE_BOLD)
        return (_BOLD_WEIGHT if mac_bold else _REGULAR_WEIGHT), mac_bold, bool(mac_style & _MAC_STYLE_ITALIC)
    selection: int = font["OS/2"].fsSelection
    bold: bool = bool(selection & _SELECTION_BOLD)
    weight_class: int = font["OS/2"].usWeightClass
    if weight_class == 0:
        weight_class = _BOLD_WEIGHT if bold else _REGULAR_WEIGHT
    return _LEGACY_WEIGHTS.get(weight_class, weight_class), bold, bool(selection & _SELECTION_ITALIC)


def _vertical_metrics(font: Any) -> tuple[int, int]:
    candidates: list[tuple[int, int]] = []
    if "OS/2" in font:
        candidates.append((_signed(font["OS/2"].usWinAscent), _signed(font["OS/2"].usWinDescent)))
    if "hhea" in font:
        candidates.append((font["hhea"].ascent, -font["hhea"].descent))
    if "OS/2" in font:
        candidates.append((font["OS/2"].sTypoAscender, -font["OS/2"].sTypoDescender))
    candidates.append((font["head"].yMax, -font["head"].yMin))
    return next(((ascent, descent) for ascent, descent in candidates if ascent + descent != 0), (0, 0))


def _signed(value: int) -> int:
    return value - 2 * _SIGNED_SHORT if value >= _SIGNED_SHORT else value


# ── Index ─────────────────────────────────────────────────────────────────────


class FontIndex:
    """Two-level font lookup: episode fonts first, system fonts only for names the episode lacks."""

    def __init__(self, episode: tuple[FontFace, ...], system_files: Mapping[str, tuple[Path, ...]]) -> None:
        self._episode: tuple[FontFace, ...] = episode
        self._system_files: Mapping[str, tuple[Path, ...]] = system_files
        self._system_faces: dict[Path, tuple[FontFace, ...]] = {}

    @classmethod
    def build(cls, episode: Iterable[Path], system: Iterable[Path]) -> FontIndex:
        """Read episode font files and index system font files by name for reading on demand."""
        faces: tuple[FontFace, ...] = tuple(face for path in episode for face in read_faces(path))
        return cls(faces, _files_by_name(system))

    def match(self, name: str, *, weight: int, italic: bool) -> FontMatch | None:
        """Choose the face for an ASS font name, Arial when no face carries the name."""
        face: FontFace | None = self._find(name, weight, italic)
        if face is not None:
            return _matched(face, weight, italic, exact=True)
        fallback: FontFace | None = self._find(_FALLBACK_FAMILY, weight, italic)
        return None if fallback is None else _matched(fallback, weight, italic, exact=False)

    def glyph_match(self, request: FontMatch, codepoint: int) -> FontMatch:
        """Choose the face drawing one character: the request, its family, then Arial for the requested style."""
        if codepoint in request.face.codepoints:
            return request
        weight: int = request.requested_weight
        italic: bool = request.requested_italic
        for family in sorted(request.face.family_names):
            face: FontFace | None = self._find(family, weight, italic, codepoint)
            if face is not None:
                return _matched(face, weight, italic, exact=request.exact)
        fallback: FontFace | None = self._find(_FALLBACK_FAMILY, weight, italic, codepoint)
        if fallback is not None:
            return _matched(fallback, weight, italic, exact=False)
        return replace(request, exact=False)

    def _find(self, name: str, weight: int, italic: bool, codepoint: int | None = None) -> FontFace | None:
        key: str = name.strip().lstrip("@").casefold()
        named: list[FontFace] = _named(self._episode, key) or _named(self._system(key), key)
        usable: list[FontFace] = [face for face in named if codepoint is None or codepoint in face.codepoints]
        return min(usable, key=lambda face: _score(face, key, weight, italic), default=None)

    def _system(self, name: str) -> tuple[FontFace, ...]:
        faces: list[FontFace] = []
        for path in self._system_files.get(name, ()):
            if path not in self._system_faces:
                self._system_faces[path] = read_faces(path)
            faces.extend(self._system_faces[path])
        return tuple(faces)


def _files_by_name(paths: Iterable[Path]) -> dict[str, tuple[Path, ...]]:
    files: dict[str, list[Path]] = {}
    for path in paths:
        for name in _file_names(path):
            files.setdefault(name, []).append(path)
    return {name: tuple(found) for name, found in files.items()}


def _file_names(path: Path) -> set[str]:
    faces: tuple[tuple[frozenset[str], frozenset[str], str | None], ...] = _read_fonts(
        path, lambda font, _: _names(font)
    )
    return {name for families, full, postscript in faces for name in (*families, *full, postscript) if name}


def _named(faces: Iterable[FontFace], key: str) -> list[FontFace]:
    return [face for face in faces if key in face.family_names or _full_or_postscript(face, key)]


def _full_or_postscript(face: FontFace, key: str) -> bool:
    if face.postscript_outlines:
        return key == face.postscript_name
    return key in face.full_names


def _score(face: FontFace, key: str, weight: int, italic: bool) -> int:
    if key not in face.family_names:
        return 0
    slant: int = 0
    if italic and not face.italic:
        slant = _MISSING_ITALIC_SCORE
    elif face.italic and not italic:
        slant = _UNWANTED_ITALIC_SCORE
    effective: int = face.weight + _FAUX_BOLD_GAIN if _emboldens(face, weight) else face.weight
    numerator, denominator = _WEIGHT_SCORE
    return slant + numerator * abs(effective - weight) // denominator


def _matched(face: FontFace, weight: int, italic: bool, *, exact: bool) -> FontMatch:
    return FontMatch(
        face=face,
        exact=exact,
        synthetic_bold=_emboldens(face, weight),
        synthetic_italic=italic and not face.italic,
        requested_weight=weight,
        requested_italic=italic,
    )


def _emboldens(face: FontFace, weight: int) -> bool:
    return not face.bold and weight > face.weight + _FAUX_BOLD_MARGIN
