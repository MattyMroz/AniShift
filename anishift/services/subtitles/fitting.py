"""Fit translated signs to their authored width without relocating ASS geometry."""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Final

from PIL import ImageFont
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.services.subtitles.text import (
    RE_TAG_BLOCK,
    is_drawing,
    replace_visible_text,
    visible_text,
    visible_verses,
)
from anishift.services.translation.linebreak import split_for_layout

# ── Constants ─────────────────────────────────────────────────────────────────

_MIN_SCALE: Final[float] = 0.72
"""Smallest proportional size relative to the authored sign."""

_WIDTH_TOLERANCE: Final[float] = 1.03
"""Estimated width growth allowed before resizing a translated sign."""

_FONT_SIZE: Final[int] = 64
"""Reference font size for language-independent advance-width ratios."""

_DEFAULT_PLAY_RES_X: Final[int] = 384
"""ASS script width assumed when the header omits ``PlayResX``."""

_NO_WRAP_STYLE: Final[str] = "2"
"""ASS ``WrapStyle`` value that disables automatic line wrapping."""

_BALANCED_LINES: Final[tuple[str, str]] = ("", "")
"""Two equal-weight verses requesting a balanced two-line layout."""

_RE_SCALING: Final[re.Pattern[str]] = re.compile(
    r"\\(?:(fsc[xy]?)\s*(-?[0-9]+(?:\.[0-9]*)?|-?\.[0-9]+)?(?=\s*[\\})]|$)|r([^\\}()]*))"
)
"""Scale overrides, transform targets, and resets requiring proportional sizes."""

_RE_PREFIX: Final[re.Pattern[str]] = re.compile(r"^(?:\{[^}]*\})*")
"""Leading override blocks setting the initial font size and horizontal scale."""

_RE_SIZE: Final[re.Pattern[str]] = re.compile(r"\\fs(cx)?\s*(-?[0-9]+(?:\.[0-9]*)?)")
"""Font size or horizontal scale override with an explicit value."""

_RE_NO_WRAP: Final[re.Pattern[str]] = re.compile(r"\\q\s*2")
"""Inline override disabling automatic line wrapping."""


@lru_cache(maxsize=1)
def _font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", _FONT_SIZE)
    except OSError:
        return ImageFont.load_default(size=_FONT_SIZE)


@lru_cache(maxsize=4096)
def _width(text: str) -> float:
    return max((float(_font().getlength(verse)) for verse in visible_verses(text)), default=0.0)


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


def _pixel_scale(text: str, style: SSAStyle) -> float:
    size: float = style.fontsize
    scale: float = style.scalex
    prefix: re.Match[str] | None = _RE_PREFIX.match(text)
    for match in _RE_SIZE.finditer(prefix[0] if prefix else ""):
        if match[1]:
            scale = abs(float(match[2]))
        else:
            size = float(match[2])
    return size * scale / 100 / _FONT_SIZE


def _play_width(subs: SSAFile) -> float:
    try:
        return float(subs.info.get("PlayResX") or _DEFAULT_PLAY_RES_X)
    except ValueError:
        return _DEFAULT_PLAY_RES_X


def _wraps_only_translation(event: SSAEvent, translated: str, subs: SSAFile) -> bool:
    style: SSAStyle = subs.styles[event.style]
    if subs.info.get("WrapStyle", "0").strip() == _NO_WRAP_STYLE or _RE_NO_WRAP.search(event.text):
        return False
    wrap_width: float = _play_width(subs) - (event.marginl or style.marginl) - (event.marginr or style.marginr)
    pixels: float = _pixel_scale(event.text, style)
    return _width(event.text) * pixels <= wrap_width < _width(translated) * pixels


def _reflow(event: SSAEvent, translated: str, subs: SSAFile) -> str:
    layout: tuple[str, ...] = visible_verses(event.text)
    if len(layout) <= 1 and _wraps_only_translation(event, translated, subs):
        layout = _BALANCED_LINES
    if len(layout) <= 1:
        return translated
    verses: tuple[str, ...] = split_for_layout(visible_text(translated), layout)
    reflowed: str = replace_visible_text(event.text, "\\N".join(verses))
    return reflowed if _width(reflowed) < _width(translated) else translated


def fit_sign_text(event: SSAEvent, translated: str, subs: SSAFile) -> str:
    """Fit an already classified sign, preserving geometry and a 72% size floor."""
    source: str = event.text
    style: SSAStyle | None = subs.styles.get(event.style)
    if style is None or is_drawing(source) or is_drawing(translated):
        return translated
    if visible_text(source) == visible_text(translated):
        return translated
    source_width: float = _width(source)
    target_width: float = _width(translated)
    if source_width <= 0 or target_width <= source_width * _WIDTH_TOLERANCE:
        return translated
    if source_width / target_width < _MIN_SCALE:
        translated = _reflow(event, translated, subs)
        target_width = _width(translated)
    factor: float = max(_MIN_SCALE, min(1.0, source_width / target_width))
    if factor == 1:
        return translated
    scaled: str = _scale_text(translated, factor, style, subs.styles)
    if scaled.startswith("{"):
        return "{" + _scales(style, factor) + scaled[1:]
    return "{" + _scales(style, factor) + "}" + scaled
