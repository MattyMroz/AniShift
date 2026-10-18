"""Fit translated signs to their authored width without relocating ASS geometry."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.geometry import _reference_width, _wraps
from anishift.services.subtitles.linebreak import split_for_layout
from anishift.services.subtitles.text import (
    RE_TAG_BLOCK,
    is_drawing,
    replace_visible_text,
    visible_text,
    visible_verses,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile, SSAStyle

    from anishift.services.subtitles.geometry import RenderProfile
    from anishift.services.subtitles.types import LayoutReport

__all__ = ["fit_signs"]

# ── Constants ─────────────────────────────────────────────────────────────────

_MIN_SCALE: Final[float] = 0.72
"""Smallest proportional size relative to the authored sign."""

_WIDTH_TOLERANCE: Final[float] = 1.03
"""Estimated width growth allowed before resizing a translated sign."""

_BALANCED_LINES: Final[tuple[str, str]] = ("", "")
"""Two equal-weight verses requesting a balanced two-line layout."""

_RE_SCALING: Final[re.Pattern[str]] = re.compile(
    r"\\(?:(fsc[xy]?)\s*(-?[0-9]+(?:\.[0-9]*)?|-?\.[0-9]+)?(?=\s*[\\})]|$)|r([^\\}()]*))"
)
"""Scale overrides, transform targets, and resets requiring proportional sizes."""


def fit_signs(
    source: SSAFile, target: SSAFile, signs: Sequence[int], profile: RenderProfile, report: LayoutReport
) -> dict[int, str]:
    """Fit the translated signs at event positions ``signs`` of both files and return their new texts."""
    return {index: _fit_sign(source.events[index], target.events[index].text, profile) for index in signs}


def _scales(style: SSAStyle, factor: float) -> str:
    return _scale_tag("fscx", style.scalex * factor) + _scale_tag("fscy", style.scaley * factor)


def _scale_tag(tag: str, value: float) -> str:
    return f"\\{tag}{value:.3f}".rstrip("0").rstrip(".")


def _scale_text(text: str, factor: float, style: SSAStyle, styles: Mapping[str, SSAStyle]) -> str:
    current_style: SSAStyle = style

    def replace_command(match: re.Match[str]) -> str:
        nonlocal current_style
        if match[3] is not None:
            current_style = styles.get(match[3].strip(), style)
            return match[0] + _scales(current_style, factor)
        tag: str = match[1]
        if tag == "fsc":
            return _scales(current_style, factor)
        value: float = float(match[2]) if match[2] else getattr(current_style, "scale" + tag[-1])
        return _scale_tag(tag, value * factor)

    return RE_TAG_BLOCK.sub(lambda block: _RE_SCALING.sub(replace_command, block[0]), text)


def _wraps_only_translation(event: SSAEvent, translated: str, profile: RenderProfile) -> bool:
    return not _wraps(event, event.text, profile) and _wraps(event, translated, profile)


def _reflow(event: SSAEvent, translated: str, profile: RenderProfile) -> str:
    layout: tuple[str, ...] = visible_verses(event.text)
    if len(layout) <= 1 and _wraps_only_translation(event, translated, profile):
        layout = _BALANCED_LINES
    if len(layout) <= 1:
        return translated
    verses: tuple[str, ...] = split_for_layout(visible_text(translated), layout)
    reflowed: str = replace_visible_text(event.text, "\\N".join(verses))
    return reflowed if _reference_width(reflowed) < _reference_width(translated) else translated


def _fit_sign(event: SSAEvent, translated: str, profile: RenderProfile) -> str:
    source: str = event.text
    style: SSAStyle | None = profile.styles.get(event.style)
    if style is None or is_drawing(source) or is_drawing(translated):
        return translated
    if visible_text(source) == visible_text(translated):
        return translated
    source_width: float = _reference_width(source)
    target_width: float = _reference_width(translated)
    if source_width <= 0 or target_width <= source_width * _WIDTH_TOLERANCE:
        return translated
    if source_width / target_width < _MIN_SCALE:
        translated = _reflow(event, translated, profile)
        target_width = _reference_width(translated)
    factor: float = max(_MIN_SCALE, min(1.0, source_width / target_width))
    if factor == 1:
        return translated
    scaled: str = _scale_text(translated, factor, style, profile.styles)
    if scaled.startswith("{"):
        return "{" + _scales(style, factor) + scaled[1:]
    return "{" + _scales(style, factor) + "}" + scaled
