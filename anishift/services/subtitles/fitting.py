"""Lay out translated displayed text with the layout core, keeping it on screen, in its clip and off other text."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.classifier import sung
from anishift.services.subtitles.geometry import (
    Rect,
    alignment,
    anchor_reach,
    font_size,
    measure_text,
    rotated,
    screen_rects,
    style_changes,
    wrap_text,
)
from anishift.services.subtitles.layout import MIN_SCALE, Flag, Scale, heading_break, ranked, sign_field
from anishift.services.subtitles.linebreak import NO_WRAP, tagged_measure, tagged_words, without_wrap
from anishift.services.subtitles.text import RE_TAG_BLOCK, is_drawing, reflow_visible_text, visible_text, visible_verses
from anishift.text.boundaries import BREAKABLE_SPACES
from anishift.text.gaps import DASHES, gaps
from anishift.text.morphology import modifies, verb

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pysubs2 import SSAEvent, SSAFile, SSAStyle

    from anishift.services.subtitles.geometry import RenderProfile
    from anishift.services.subtitles.layout import Field, Layout, Measure
    from anishift.services.subtitles.types import LayoutReport

__all__ = ["fit_signs", "sign_input"]

# ── Constants ─────────────────────────────────────────────────────────────────

_OBJECT_GAP_MS: Final[int] = 500
"""Largest gap after which an event with the same source and translated text still belongs to one sign object."""

_EXACT_UNCERTAINTY: Final[float] = 0.012
"""Relative width error allowed when every glyph is measured in its real font."""

_APPROXIMATE_UNCERTAINTY: Final[float] = 0.07
"""Relative width error allowed when a font, glyph, rotation or animation is only approximated."""

_PIXEL: Final[float] = 1.0
"""Script pixels any screen or overlap comparison tolerates on top of the measurement error."""

_SCREEN_HEIGHT: Final[float] = 1080.0
"""Screen height in pixels letter heights are expressed in."""

_PROBE: Final[str] = "Xg"
"""Text whose one- and two-line heights give the line pitch of a sign."""

_LIST_ITEMS: Final[int] = 2
"""Fewest source lines that make a list whose items keep their own lines."""

_RECT_COORDINATES: Final[int] = 4
"""Coordinates of a rectangular clip."""

_BUCKET_MS: Final[int] = 10_000
"""Length of the time buckets that find the events shown together with a sign."""

_BREAK: Final[str] = "\\N"
"""ASS hard line break."""

_RE_SCALING: Final[re.Pattern[str]] = re.compile(
    r"\\(?:(fsc[xy]?)\s*(-?[0-9]+(?:\.[0-9]*)?|-?\.[0-9]+)?(?=\s*[\\})]|$)|r([^\\}()]*))"
)
"""Scale overrides, transform targets and resets that the chosen scale multiplies."""

_RE_CLIP: Final[re.Pattern[str]] = re.compile(r"\\clip\(([^)]*)\)")
"""Positive clipping mask restricting where the sign is visible."""

_RE_NUMBER: Final[re.Pattern[str]] = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
"""Coordinate of a rectangular or vector clip."""

_RE_PREFIX: Final[re.Pattern[str]] = re.compile(r"^(?:\{[^}]*\})*")
"""Override blocks before the first visible character."""

_RE_POS: Final[re.Pattern[str]] = re.compile(rf"\\pos\(\s*({_RE_NUMBER.pattern})\s*,\s*({_RE_NUMBER.pattern})\s*\)")
"""Static anchor override of an event."""

_RE_AXIS_SCALE: Final[re.Pattern[str]] = re.compile(rf"\\fsc([xy])\s*({_RE_NUMBER.pattern})")
"""Horizontal or vertical scale override of a drawing."""

_RE_DRAWING_LEVEL: Final[re.Pattern[str]] = re.compile(r"\\p([1-9][0-9]*)")
"""Drawing mode with the coordinate precision level libass divides points by."""

_MAX_DRAWING_LEVEL: Final[int] = 31
"""Highest drawing or clip precision level measured, the widest shift libass applies; a higher one is unmeasured."""

_RE_ANIMATED: Final[re.Pattern[str]] = re.compile(r"\\(?:move|t)\s*\(")
"""Motion or animation that keeps a drawing from being a still panel."""

_RE_POINT: Final[re.Pattern[str]] = re.compile(r"-?[0-9]+(?:\.[0-9]*)?")
"""Coordinate of a drawing command."""

_RE_INK: Final[re.Pattern[str]] = re.compile(
    r"\\(alpha|[134]a|bord|shad|r)(?![a-z])\s*(?:&H([0-9A-Fa-f]{1,2})&?|(\d+(?:\.\d*)?|\.\d+))?"
)
"""Overrides deciding whether a character draws any ink: alphas, border and shadow sizes and resets."""

_TRANSPARENT: Final[int] = 0xFF
"""ASS alpha of a fully transparent part."""

_PANEL_SHARE: Final[float] = 0.8
"""Share of the source text box a drawing must cover to be the panel the sign sits on."""


@dataclass(frozen=True, slots=True)
class _Member:
    """One event of a sign object: its unbroken translation, authored spacing and the geometry it is checked against."""

    index: int
    event: SSAEvent
    text: str
    spacing: tuple[int, ...]
    rects: tuple[Rect, ...]
    region: Rect
    lost: tuple[float, float]
    near: tuple[Rect, ...]
    dialogue: tuple[Rect, ...]
    uncertainty: float


@dataclass(frozen=True, slots=True)
class _Fitted:
    """One fitted sign object: its members, chosen layout and texts, and the set it is shown in."""

    members: tuple[_Member, ...]
    layout: Layout
    texts: dict[int, str]
    kit: tuple[str, float]
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _Prepared:
    """A sign as the layout core sees it: the source as shown, word moves, field and line measure."""

    shown: str
    moves: Mapping[int, int]
    field: Field
    measure: Measure


@dataclass(frozen=True, slots=True)
class _Scene:
    """Events of both files with the fitted texts so far and the rectangles of neighbours already measured."""

    source: SSAFile
    target: SSAFile
    signs: frozenset[int]
    profile: RenderProfile
    buckets: Mapping[int, Sequence[int]]
    fitted: dict[int, str]
    boxes: dict[int, tuple[Rect, ...]]


# ── Public functions ──────────────────────────────────────────────────────────


def fit_signs(
    source: SSAFile, target: SSAFile, signs: Sequence[int], profile: RenderProfile, report: LayoutReport
) -> dict[int, str]:
    """Lay out the one-line translated signs at event positions ``signs`` and return their new texts."""
    scene: _Scene = _Scene(source, target, frozenset(signs), profile, _buckets(target), {}, {})
    objects: list[_Fitted] = []
    for group in _objects(source, target, signs):
        fitted: _Fitted | None = _fit_object(group, scene, report)
        if fitted is not None:
            objects.append(fitted)
            scene.fitted.update(fitted.texts)
    for kit in _kits(objects):
        fx: float = min(max(item.layout.scale.fx, MIN_SCALE) for item in kit)
        fy: float = min(max(item.layout.scale.fy, MIN_SCALE) for item in kit)
        changed: list[_Fitted] = [item for item in kit if item.layout.scale.fx > fx or item.layout.scale.fy > fy]
        report.sign_sets_scaled += bool(changed)
        for item in changed:
            scale: Scale = Scale(min(item.layout.scale.fx, fx), min(item.layout.scale.fy, fy))
            scene.fitted.update(_texts(item.members, replace(item.layout, scale=scale), profile))
    result: dict[int, str] = {index: scene.fitted.get(index, target[index].text) for index in signs}
    return result | _grown_panels(objects, scene, result)


# ── Panels ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Panel:
    """A still drawing under a sign: its canvas box, scale, anchor and alignment."""

    index: int
    rect: Rect
    scale: tuple[float, float]
    anchor: tuple[float, float]
    alignment: int


def _grown_panels(objects: Sequence[_Fitted], scene: _Scene, texts: Mapping[int, str]) -> dict[int, str]:
    """Return the drawings under signs grown to hold the laid-out text with the margins the source text had."""
    panels: list[_Panel] = [
        panel
        for index, event in enumerate(scene.target)
        if event.type == "Dialogue" and (panel := _panel(index, event, scene.profile)) is not None
    ]
    grown: dict[int, str] = {}
    for member in (member for item in objects for member in item.members):
        source: Rect | None = _union(member.rects)
        laid_out: SSAEvent = scene.target[member.index].copy()
        laid_out.text = texts.get(member.index, laid_out.text)
        text: Rect | None = _union(screen_rects(laid_out, laid_out.text, scene.profile))
        if source is None or text is None:
            continue
        for panel in panels:
            drawing: SSAEvent = scene.target[panel.index]
            if panel.index in grown or not (drawing.start < member.event.end and member.event.start < drawing.end):
                continue
            if _area(_intersection(source, panel.rect)) < _PANEL_SHARE * _area(source):
                continue
            margins: Rect = Rect(
                max(0.0, source.left - panel.rect.left),
                max(0.0, source.top - panel.rect.top),
                max(0.0, panel.rect.right - source.right),
                max(0.0, panel.rect.bottom - source.bottom),
            )
            inner: Rect = Rect(
                panel.rect.left + margins.left / 2,
                panel.rect.top + margins.top / 2,
                panel.rect.right - margins.right / 2,
                panel.rect.bottom - margins.bottom / 2,
            )
            if _intersection(text, inner) == text:
                continue
            needed: Rect = Rect(
                text.left - margins.left,
                text.top - margins.top,
                text.right + margins.right,
                text.bottom + margins.bottom,
            )
            box: Rect = Rect(
                min(panel.rect.left, needed.left),
                min(panel.rect.top, needed.top),
                max(panel.rect.right, needed.right),
                max(panel.rect.bottom, needed.bottom),
            )
            if box != panel.rect:
                grown[panel.index] = _resized(drawing.text, panel, box)
    return grown


def _panel(index: int, event: SSAEvent, profile: RenderProfile) -> _Panel | None:
    style: SSAStyle | None = profile.styles.get(event.style)
    tags: str = "".join(RE_TAG_BLOCK.findall(event.text))
    position: re.Match[str] | None = _RE_POS.search(tags)
    level: re.Match[str] | None = _RE_DRAWING_LEVEL.search(tags)
    points: list[float] = [float(point) for point in _RE_POINT.findall(RE_TAG_BLOCK.sub("", event.text))]
    if style is None or position is None or level is None or _RE_ANIMATED.search(tags) or len(points) < 4:  # noqa: PLR2004
        return None
    if int(level[1]) > _MAX_DRAWING_LEVEL:
        return None
    scales: dict[str, float] = {"x": float(style.scalex), "y": float(style.scaley)}
    scales |= {axis: float(value) for axis, value in _RE_AXIS_SCALE.findall(tags)}
    divisor: float = 2 ** (int(level[1]) - 1)
    xs, ys = points[0::2], points[1::2]
    width: float = (max(xs) - min(xs)) * scales["x"] / 100 / divisor
    height: float = (max(ys) - min(ys)) * scales["y"] / 100 / divisor
    if width <= 0 or height <= 0:
        return None
    anchor: tuple[float, float] = (float(position[1]), float(position[2]))
    place: int = alignment(event, profile)
    left: float = anchor[0] - width * ((place - 1) % 3) / 2
    top: float = anchor[1] - height * (2 - (place - 1) // 3) / 2
    return _Panel(index, Rect(left, top, left + width, top + height), (scales["x"], scales["y"]), anchor, place)


def _resized(text: str, panel: _Panel, box: Rect) -> str:
    old_width: float = panel.rect.right - panel.rect.left
    old_height: float = panel.rect.bottom - panel.rect.top
    scale_x: float = panel.scale[0] * (box.right - box.left) / old_width
    scale_y: float = panel.scale[1] * (box.bottom - box.top) / old_height
    column: float = ((panel.alignment - 1) % 3) / 2
    row: float = (2 - (panel.alignment - 1) // 3) / 2
    x: float = box.left + (box.right - box.left) * column
    y: float = box.top + (box.bottom - box.top) * row
    tags: str = f"BBpos({x:.3f},{y:.3f})BBfscx{scale_x:.3f}BBfscy{scale_y:.3f}".replace("BB", chr(92))

    def block(found: re.Match[str]) -> str:
        cleaned: str = _RE_AXIS_SCALE.sub("", _RE_POS.sub("", found[0]))
        return cleaned

    stripped: str = RE_TAG_BLOCK.sub(block, text)
    return "{" + tags + "}" + stripped


def _union(rects: Sequence[Rect]) -> Rect | None:
    if not rects:
        return None
    return Rect(
        min(rect.left for rect in rects),
        min(rect.top for rect in rects),
        max(rect.right for rect in rects),
        max(rect.bottom for rect in rects),
    )


def _intersection(first: Rect, second: Rect) -> Rect:
    return Rect(
        max(first.left, second.left),
        max(first.top, second.top),
        min(first.right, second.right),
        min(first.bottom, second.bottom),
    )


def _area(rect: Rect) -> float:
    return max(0.0, rect.right - rect.left) * max(0.0, rect.bottom - rect.top)


# ── Objects ───────────────────────────────────────────────────────────────────


def sign_input(source: SSAEvent, event: SSAEvent, profile: RenderProfile) -> tuple[str, Field, Measure]:
    """Return the translated words of a sign, the field the layout core places them in and their line measure."""
    words: tuple[str, ...] = _words(event.text)
    prepared: _Prepared = _prepared(source, event, words, profile)
    return " ".join(words), prepared.field, prepared.measure


def _prepared(source: SSAEvent, event: SSAEvent, words: tuple[str, ...], profile: RenderProfile) -> _Prepared:
    shown: str = wrap_text(source, source.text, profile)
    moves, forced = _structure(source, shown, event, words, profile)
    tagged: str = _moved(event.text, words, moves)
    field: Field = _field(source, shown, event, tagged, forced, profile)
    return _Prepared(shown, moves, field, tagged_measure(event, tagged, profile))


def _buckets(target: SSAFile) -> dict[int, list[int]]:
    buckets: defaultdict[int, list[int]] = defaultdict(list)
    for index, event in enumerate(target):
        if event.type != "Dialogue" or is_drawing(event.text):
            continue
        for bucket in range(event.start // _BUCKET_MS, max(event.start, event.end - 1) // _BUCKET_MS + 1):
            buckets[bucket].append(index)
    return buckets


def _objects(source: SSAFile, target: SSAFile, signs: Sequence[int]) -> list[tuple[int, ...]]:
    by_text: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index in sorted(set(signs), key=lambda index: (source[index].start, index)):
        if is_drawing(source[index].text):
            continue
        by_text[(visible_text(source[index].text), visible_text(target[index].text))].append(index)
    groups: list[tuple[int, ...]] = [group for indices in by_text.values() for group in _runs(indices, source)]
    return sorted(groups, key=min)


def _runs(indices: Sequence[int], source: SSAFile) -> list[tuple[int, ...]]:
    groups: list[list[int]] = []
    end: int = 0
    for index in indices:
        if not groups or source[index].start > end + _OBJECT_GAP_MS:
            groups.append([])
            end = source[index].end
        groups[-1].append(index)
        end = max(end, source[index].end)
    return [tuple(group) for group in groups]


def _kits(objects: Sequence[_Fitted]) -> list[list[_Fitted]]:
    """Return the sets of objects of one source style and letter size whose times overlap, two objects or more."""
    by_kit: defaultdict[tuple[str, float], list[_Fitted]] = defaultdict(list)
    for item in sorted(objects, key=lambda item: item.start):
        by_kit[item.kit].append(item)
    kits: list[list[_Fitted]] = []
    for items in by_kit.values():
        kits.append([items[0]])
        end: int = items[0].end
        for item in items[1:]:
            if item.start >= end:
                kits.append([])
            kits[-1].append(item)
            end = max(end, item.end)
    return [kit for kit in kits if len(kit) > 1]


def _fit_object(group: tuple[int, ...], scene: _Scene, report: LayoutReport) -> _Fitted | None:
    first: int = group[0]
    source: SSAEvent = scene.source[first]
    event: SSAEvent = scene.target[first]
    style: SSAStyle | None = scene.profile.styles.get(event.style)
    words: tuple[str, ...] = _words(event.text)
    if style is None or not words or visible_text(source.text) == visible_text(event.text):
        return None
    prepared: _Prepared = _prepared(source, event, words, scene.profile)
    shown, moves = prepared.shown, prepared.moves
    layouts: list[Layout] = ranked(" ".join(words), prepared.field, prepared.measure)
    spacing: tuple[int, ...] = _spacing(visible_verses(shown))
    members: list[_Member] = _on_screen(
        [_member(index, _moved(scene.target[index].text, words, moves), spacing, scene) for index in group],
        scene.profile,
    )
    chosen, screen, collision = _choose(layouts, members, scene.profile)
    report.signs_fallback_screen += screen
    report.signs_fallback_collision += collision
    report.signs_relaxed += bool(chosen.flags - {Flag.SMALL})
    report.signs_small += Flag.SMALL in chosen.flags
    report.signs_fitted += len(chosen.lines) > 1 or chosen.scale != Scale()
    texts: dict[int, str] = _texts(members, chosen, scene.profile)
    report.signs_approximate += measure_text(event, texts[first], scene.profile).status == "approximate"
    report.sign_dialogue_collisions += any(
        _overlap(screen_rects(member.event, NO_WRAP + texts[member.index], scene.profile), member.dialogue, 0.0) > 0
        for member in members
        if member.dialogue
    )
    kit: tuple[str, float] = (source.style, font_size(source, scene.profile))
    start: int = min(scene.source[index].start for index in group)
    end: int = max(scene.source[index].end for index in group)
    return _Fitted(tuple(members), chosen, texts, kit, start, end)


def _texts(members: Sequence[_Member], layout: Layout, profile: RenderProfile) -> dict[int, str]:
    return {member.index: without_wrap(member.event, _render(member, layout, profile), profile) for member in members}


def _words(text: str) -> tuple[str, ...]:
    return tuple(word for word in BREAKABLE_SPACES.split(visible_text(text, preserve_hard_spaces=True)) if word)


# ── Field ─────────────────────────────────────────────────────────────────────


def _field(  # noqa: PLR0913 - the source as shown, the anchored translation and its forced breaks
    source: SSAEvent, shown: str, event: SSAEvent, tagged: str, forced: frozenset[int], profile: RenderProfile
) -> Field:
    verses: tuple[str, ...] = visible_verses(shown)
    widths: tuple[float, ...] = measure_text(source, shown, profile).line_widths
    template: tuple[float, ...] = tuple(
        width / profile.play_res_x for verse, width in zip(verses, widths, strict=False) if verse
    )
    width: float = max(template, default=0.0)
    rects: tuple[Rect, ...] = screen_rects(source, source.text, profile)
    region: Rect = _region(source.text, profile)
    reach: float = anchor_reach(event, profile, region.left, region.right) / profile.play_res_x
    changes: tuple[bool, ...] = style_changes(event, tagged, profile)
    blocks, runs = _blocks(verses)
    field: Field = sign_field(
        source_lines=max(1, len(template)),
        template=() if sung(source) else template,
        letter_height=font_size(event, profile) * _SCREEN_HEIGHT / profile.play_res_y,
        max_width=math.inf if rotated(event, event.text, profile) else max(width, reach),
        height_lines=_height_lines(event, rects, region, profile),
        breaks=forced,
        style_breaks=frozenset(gap for gap, change in enumerate(changes) if change),
    )
    field = replace(field, hidden=_hidden_words(event, tagged, profile))
    if len(blocks) < _LIST_ITEMS or not template:
        return field
    return replace(field, blocks=blocks, runs=runs, anchor_row=(alignment(event, profile) - 1) // 3)


def _hidden_words(event: SSAEvent, tagged: str, profile: RenderProfile) -> frozenset[int]:
    style: SSAStyle | None = profile.styles.get(event.style)
    words: tuple[str, ...] = _words(tagged)
    pieces: tuple[str, ...] | None = tagged_words(tagged, words)
    if style is None or pieces is None:
        return frozenset()
    base: dict[str, float] = {
        "1a": style.primarycolor.a, "3a": style.outlinecolor.a, "4a": style.backcolor.a,
        "bord": float(style.outline), "shad": float(style.shadow),
    }  # fmt: skip
    state: dict[str, float] = dict(base)
    hidden: set[int] = set()
    for index, piece in enumerate(pieces):
        for name, alpha, size in _RE_INK.findall("".join(RE_TAG_BLOCK.findall(piece))):
            if name == "r":
                state = dict(base)
            elif name == "alpha" and alpha:
                state |= dict.fromkeys(("1a", "3a", "4a"), float(int(alpha, 16)))
            elif alpha:
                state[name] = float(int(alpha, 16))
            elif size:
                state[name] = float(size)
        outline: bool = state["bord"] > 0 and state["3a"] < _TRANSPARENT
        shadow: bool = state["shad"] > 0 and state["4a"] < _TRANSPARENT
        if state["1a"] >= _TRANSPARENT and not outline and not shadow:
            hidden.add(index)
    return frozenset(hidden)


def _blocks(verses: Sequence[str]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    blocks: list[int] = []
    runs: list[int] = []
    empty: int = 0
    for verse in verses:
        if not verse:
            empty += 1
            continue
        if blocks and empty:
            runs.append(empty)
            blocks.append(0)
        if not blocks:
            blocks.append(0)
        blocks[-1] += 1
        empty = 0
    return tuple(blocks), tuple(runs)


def _structure(
    source: SSAEvent, shown: str, event: SSAEvent, words: tuple[str, ...], profile: RenderProfile
) -> tuple[dict[int, int], frozenset[int]]:
    """Return where authored size changes at source line ends move in the translation, and its forced breaks."""
    heading: int | None = heading_break(words)
    authored: frozenset[int] = (frozenset() if sung(source) else _translator_breaks(shown, event.text, words)) or (
        _authored_breaks(visible_verses(shown), words)
    )
    structural: list[int] = sorted(authored | ({heading} if heading is not None else set()))
    changes: tuple[bool, ...] = style_changes(event, event.text, profile)
    found: list[int] = [gap for gap, change in enumerate(changes) if change]
    ends: set[int] = _verse_ends(visible_verses(shown))
    at_end: list[bool] = [gap in ends for gap, change in enumerate(style_changes(source, shown, profile)) if change]
    if len(changes) != len(words) - 1 or len(at_end) != len(found):
        return {}, authored
    edges: list[int] = [gap for gap, end in zip(found, at_end, strict=True) if end]
    if structural and len(edges) == len(structural):
        return dict(zip(edges, structural, strict=True)), frozenset(structural)
    return {}, authored | frozenset(edges)


def _translator_breaks(shown: str, translated: str, words: tuple[str, ...]) -> frozenset[int]:
    lines: list[str] = [verse for verse in visible_verses(translated) if verse]
    if len(lines) < _LIST_ITEMS or len(lines) != len([verse for verse in visible_verses(shown) if verse]):
        return frozenset()
    if sum(len([word for word in BREAKABLE_SPACES.split(line) if word]) for line in lines) != len(words):
        return frozenset()
    bound: frozenset[int] = frozenset(index for index, gap in enumerate(gaps(words, modifies, verb)) if gap.protected)
    return frozenset(_verse_ends(lines) - {len(words) - 1}) - bound


def _moved(text: str, words: tuple[str, ...], moves: Mapping[int, int]) -> str:
    pieces: tuple[str, ...] | None = tagged_words(text, words)
    if pieces is None or all(origin == target for origin, target in moves.items()):
        return text
    moved: list[str] = list(pieces)
    for origin, target in moves.items():
        tags: str = _prefix(moved[origin + 1])
        moved[origin + 1] = moved[origin + 1][len(tags) :]
        moved[target + 1] = tags + moved[target + 1]
    return " ".join(moved)


def _height_lines(event: SSAEvent, rects: tuple[Rect, ...], region: Rect, profile: RenderProfile) -> float | None:
    if not _RE_CLIP.search(event.text) or not rects:
        return None
    if any(rect.top < region.top - _PIXEL or rect.bottom > region.bottom + _PIXEL for rect in rects):
        return None
    prefix: str = _prefix(event.text)
    one: float = measure_text(event, prefix + _PROBE, profile).height
    pitch: float = measure_text(event, prefix + _PROBE + _BREAK + _PROBE, profile).height - one
    return (region.bottom - region.top) / pitch if pitch > 0 else None


def _verse_ends(verses: Sequence[str]) -> set[int]:
    ends: set[int] = set()
    count: int = 0
    for verse in verses:
        count += len([word for word in BREAKABLE_SPACES.split(verse) if word])
        ends.add(count - 1)
    return ends


def _authored_breaks(verses: Sequence[str], words: tuple[str, ...]) -> frozenset[int]:
    lines: list[str] = [verse for verse in verses if verse]
    if _listed(verses, words):
        return frozenset(_verse_ends(lines) - {len(words) - 1})
    signed: int = sum(line[:1] in DASHES for line in lines[1:])
    dashes: list[int] = [index for index in range(1, len(words)) if words[index][:1] in DASHES]
    if signed == 0 or signed != len(dashes):
        return frozenset()
    return frozenset(index - 1 for index in dashes)


def _listed(verses: Sequence[str], words: tuple[str, ...]) -> bool:
    lines: list[str] = [verse for verse in verses if verse]
    if len(lines) < _LIST_ITEMS or len(words) != sum(len(line.split()) for line in lines):
        return False
    inner: list[str] = list(verses[verses.index(lines[0]) : len(verses) - verses[::-1].index(lines[-1])])
    spaced: bool = all(not later or not earlier for earlier, later in pairwise(inner))
    return spaced or all(len(line.split()) == 1 for line in lines)


def _region(text: str, profile: RenderProfile) -> Rect:
    screen: Rect = Rect(0, 0, profile.play_res_x, profile.play_res_y)
    clips: list[Rect] = [rect for match in _RE_CLIP.finditer(text) if (rect := _clip(match[1])) is not None]
    if not clips:
        return screen
    return Rect(
        max(screen.left, min(rect.left for rect in clips)),
        max(screen.top, min(rect.top for rect in clips)),
        min(screen.right, max(rect.right for rect in clips)),
        min(screen.bottom, max(rect.bottom for rect in clips)),
    )


def _clip(content: str) -> Rect | None:
    values: list[float] = [float(value) for value in _RE_NUMBER.findall(content)]
    if not re.search("[mlbs]", content):
        return Rect(*values) if len(values) == _RECT_COORDINATES else None
    scale: float = 1.0
    if "," in content:
        if not values or values[0] > _MAX_DRAWING_LEVEL:
            return None
        scale = 2 ** (values.pop(0) - 1)
    if len(values) < _RECT_COORDINATES or len(values) % 2 or scale <= 0:
        return None
    return Rect(
        min(values[::2]) / scale, min(values[1::2]) / scale, max(values[::2]) / scale, max(values[1::2]) / scale
    )


# ── Scene ─────────────────────────────────────────────────────────────────────


def _member(index: int, text: str, spacing: tuple[int, ...], scene: _Scene) -> _Member:
    source: SSAEvent = scene.source[index]
    near: list[int] = _neighbours(index, scene)
    exact: bool = measure_text(source, source.text, scene.profile).status == "exact"
    rects: tuple[Rect, ...] = screen_rects(source, source.text, scene.profile)
    region: Rect = _region(source.text, scene.profile)
    return _Member(
        index=index,
        event=scene.target[index],
        text=text,
        spacing=spacing,
        rects=rects,
        region=region,
        lost=_loss(rects, region),
        near=tuple(rect for other in near for rect in _boxes(other, scene)),
        dialogue=tuple(rect for other in near if other not in scene.signs for rect in _boxes(other, scene)),
        uncertainty=_EXACT_UNCERTAINTY if exact else _APPROXIMATE_UNCERTAINTY,
    )


def _neighbours(index: int, scene: _Scene) -> list[int]:
    event: SSAEvent = scene.source[index]
    text: str = visible_text(event.text)
    found: set[int] = {
        other
        for bucket in range(event.start // _BUCKET_MS, max(event.start, event.end - 1) // _BUCKET_MS + 1)
        for other in scene.buckets.get(bucket, ())
    }
    return sorted(
        other
        for other in found
        if other != index
        and scene.target[other].start < event.end
        and event.start < scene.target[other].end
        and visible_text(scene.source[other].text) != text
    )


def _boxes(index: int, scene: _Scene) -> tuple[Rect, ...]:
    if index not in scene.boxes:
        event, text = _shown(index, scene)
        scene.boxes[index] = screen_rects(event, text, scene.profile)
    return scene.boxes[index]


def _shown(index: int, scene: _Scene) -> tuple[SSAEvent, str]:
    if index in scene.fitted:
        return scene.target[index], scene.fitted[index]
    if index in scene.signs:
        return scene.source[index], scene.source[index].text
    return scene.target[index], scene.target[index].text


def _spacing(verses: Sequence[str]) -> tuple[int, ...]:
    spacing: list[int] = [0]
    for verse in verses:
        if verse:
            spacing.append(0)
        else:
            spacing[-1] += 1
    return tuple(spacing) if len(spacing) > 1 else (0, 0)


def _choose(layouts: Sequence[Layout], members: Sequence[_Member], profile: RenderProfile) -> tuple[Layout, int, int]:
    order: list[int] = list(range(len(members)))
    for layout in layouts:
        failed: int | None = _first_failure(layout, members, order, profile)
        if failed is None:
            return layout, 0, 0
        order.remove(failed)
        order.insert(0, failed)
    best: tuple[float, float] = (math.inf, math.inf)
    chosen: Layout = layouts[0]
    for layout in layouts:
        excess: tuple[float, float] = _excess(layout, members, order, profile, best)
        if excess < best:
            best, chosen = excess, layout
    return chosen, int(best[0] > 0), int(best[0] == 0 and best[1] > 0)


def _first_failure(
    layout: Layout, members: Sequence[_Member], order: Sequence[int], profile: RenderProfile
) -> int | None:
    for position in order:
        if _member_excess(layout, members[position], profile) != (0.0, 0.0):
            return position
    return None


def _excess(
    layout: Layout,
    members: Sequence[_Member],
    order: Sequence[int],
    profile: RenderProfile,
    bound: tuple[float, float],
) -> tuple[float, float]:
    screen: float = 0.0
    collision: float = 0.0
    for position in order:
        member_screen, member_collision = _member_excess(layout, members[position], profile)
        screen, collision = max(screen, member_screen), collision + member_collision
        if (screen, collision) >= bound:
            break
    return screen, collision


def _member_excess(layout: Layout, member: _Member, profile: RenderProfile) -> tuple[float, float]:
    rects: tuple[Rect, ...] = screen_rects(member.event, NO_WRAP + _render(member, layout, profile), profile)
    loss_x, loss_y = _loss(rects, member.region)
    base_x, base_y = member.lost
    framed: bool = member.region != Rect(0, 0, profile.play_res_x, profile.play_res_y)
    slack: float = member.uncertainty if framed else 0.0
    width: float = max((rect.right - rect.left for rect in rects), default=0.0)
    height: float = max((rect.bottom - rect.top for rect in rects), default=0.0)
    screen: float = max(0.0, loss_x - base_x - _PIXEL - slack * width, loss_y - base_y - _PIXEL - slack * height)
    grown: float = _overlap(rects, member.near, member.uncertainty) - _overlap(member.rects, member.near, 0.0)
    return screen, max(0.0, grown - _PIXEL)


def _on_screen(members: Sequence[_Member], profile: RenderProfile) -> list[_Member]:
    """Return the members, owed the full screen width when the object stands still on screen without a clip."""
    screen: Rect = Rect(0, 0, profile.play_res_x, profile.play_res_y)
    if len({member.rects for member in members}) > 1 or len(members[0].rects) > 1 or members[0].region != screen:
        return list(members)
    return [replace(member, lost=(0.0, member.lost[1])) for member in members]


def _loss(rects: Sequence[Rect], region: Rect) -> tuple[float, float]:
    return (
        max((max(0.0, region.left - rect.left) + max(0.0, rect.right - region.right) for rect in rects), default=0.0),
        max((max(0.0, region.top - rect.top) + max(0.0, rect.bottom - region.bottom) for rect in rects), default=0.0),
    )


def _overlap(rects: Sequence[Rect], others: Sequence[Rect], uncertainty: float) -> float:
    return sum(
        max(0.0, min(left.right, right.right) - max(left.left, right.left))
        * max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
        for left in (_inset(rect, uncertainty) for rect in rects)
        for right in others
    )


def _inset(rect: Rect, uncertainty: float) -> Rect:
    across: float = uncertainty * max(0.0, rect.right - rect.left) / 2
    down: float = uncertainty * max(0.0, rect.bottom - rect.top) / 2
    return Rect(rect.left + across, rect.top + down, rect.right - across, rect.bottom - down)


# ── Writing ───────────────────────────────────────────────────────────────────


def _render(member: _Member, layout: Layout, profile: RenderProfile) -> str:
    text: str = _spaced(reflow_visible_text(member.text, layout.lines), member.spacing, layout.spacing)
    style: SSAStyle | None = profile.styles.get(member.event.style)
    if layout.scale == Scale() or style is None:
        return text
    return _scaled(text, layout.scale, style, profile.styles)


def _scaled(text: str, scale: Scale, style: SSAStyle, styles: Mapping[str, SSAStyle]) -> str:
    scaled: str = _scale_text(text, scale, style, styles)
    prefix: str = _scales(style, scale)
    return "{" + prefix + scaled[1:] if scaled.startswith("{") else "{" + prefix + "}" + scaled


def _spaced(text: str, spacing: tuple[int, ...], blocks: tuple[int, ...]) -> str:
    pieces: list[str] = text.split(_BREAK)
    sources: int = len(spacing) - 1
    lines: int = len(pieces)
    after: list[int] = [*blocks[1:-1], 0] if len(blocks) == lines + 1 else [0] * lines
    for line in range(1, sources if not blocks else 1):
        if lines > 1:
            after[min(lines - 1, max(1, round(line * lines / sources))) - 1] += spacing[line]
    joined: str = "".join(piece + _BREAK * (1 + after[index]) for index, piece in enumerate(pieces[:-1])) + pieces[-1]
    prefix: str = _prefix(joined)
    before, behind = (blocks[0], blocks[-1]) if blocks else (0, 0)
    return prefix + _BREAK * (spacing[0] + before) + joined[len(prefix) :] + _BREAK * (spacing[-1] + behind)


def _prefix(text: str) -> str:
    match: re.Match[str] | None = _RE_PREFIX.match(text)
    return match[0] if match else ""


def _scales(style: SSAStyle, scale: Scale) -> str:
    vertical: str = "" if scale.fy == 1 else _scale_tag("fscy", style.scaley * scale.fy)
    return _scale_tag("fscx", style.scalex * scale.fx) + vertical


def _scale_tag(tag: str, value: float) -> str:
    return f"\\{tag}{value:.3f}".rstrip("0").rstrip(".")


def _scale_text(text: str, scale: Scale, style: SSAStyle, styles: Mapping[str, SSAStyle]) -> str:
    current: SSAStyle = style

    def replace_command(match: re.Match[str]) -> str:
        nonlocal current
        if match[3] is not None:
            current = styles.get(match[3].strip(), style)
            return match[0] + _scales(current, scale)
        tag: str = match[1]
        if tag == "fsc":
            return _scale_tag("fscx", current.scalex * scale.fx) + _scale_tag("fscy", current.scaley * scale.fy)
        value: float = float(match[2]) if match[2] else getattr(current, "scale" + tag[-1])
        return _scale_tag(tag, value * (scale.fx if tag == "fscx" else scale.fy))

    return RE_TAG_BLOCK.sub(lambda block: _RE_SCALING.sub(replace_command, block[0]), text)
