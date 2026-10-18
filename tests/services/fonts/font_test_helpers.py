from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fontTools.fontBuilder import FontBuilder  # type: ignore[import-untyped]
from fontTools.pens.ttGlyphPen import TTGlyphPen  # type: ignore[import-untyped]
from fontTools.ttLib import TTCollection  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

INK_BOX: tuple[int, int, int, int] = (100, 0, 500, 700)
ADVANCE: int = 600


@dataclass(frozen=True, slots=True)
class FontSpec:
    family: str
    weight: int = 400
    italic: bool = False
    bold_flag: bool = False
    chars: str = "Hab "
    full: str = ""
    postscript: str = ""
    typographic: str = ""
    mac_family: str = ""
    windows_family: bool = True
    win: tuple[int, int] = (800, 200)
    hhea: tuple[int, int] = (800, 200)
    typo: tuple[int, int] = (800, 200)


def build_font(family: str, **options: Any) -> Any:
    spec = FontSpec(family, **options)
    names: list[str] = [".notdef", *(f"uni{ord(char):04X}" for char in spec.chars)]
    builder: Any = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(char): f"uni{ord(char):04X}" for char in spec.chars})
    builder.setupGlyf({name: _glyph(blank=name == "uni0020") for name in names})
    builder.setupHorizontalMetrics(dict.fromkeys(names, (ADVANCE, INK_BOX[0])))
    builder.setupHorizontalHeader(ascent=spec.hhea[0], descent=-spec.hhea[1])
    builder.setupNameTable({}, mac=False)
    _set_names(builder.font["name"], spec)
    builder.setupOS2(
        usWeightClass=spec.weight,
        fsSelection=(1 if spec.italic else 0) | (1 << 5 if spec.bold_flag else 0),
        usWinAscent=spec.win[0],
        usWinDescent=spec.win[1],
        sTypoAscender=spec.typo[0],
        sTypoDescender=-spec.typo[1],
    )
    builder.setupPost()
    return builder.font


def write_font(path: Path, family: str, **options: Any) -> Path:
    build_font(family, **options).save(path)
    return path


def write_collection(path: Path, fonts: Sequence[Any]) -> Path:
    collection: Any = TTCollection()
    collection.fonts = list(fonts)
    collection.save(path)
    return path


def _set_names(table: Any, spec: FontSpec) -> None:
    windows: list[tuple[str, int]] = [(spec.full, 4), (spec.postscript, 6), (spec.typographic, 16)]
    if spec.windows_family:
        windows.append((spec.family, 1))
    for text, name_id in windows:
        if text:
            table.setName(text, name_id, 3, 1, 0x409)
    if spec.mac_family:
        table.setName(spec.mac_family, 1, 1, 0, 0)


def _glyph(*, blank: bool) -> Any:
    pen: Any = TTGlyphPen(None)
    if not blank:
        left, bottom, right, top = INK_BOX
        pen.moveTo((left, bottom))
        pen.lineTo((left, top))
        pen.lineTo((right, top))
        pen.lineTo((right, bottom))
        pen.closePath()
    return pen.glyph()
