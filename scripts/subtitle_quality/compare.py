"""Compare two writer replays and render before/after images of every kind of change for a human to judge."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from PIL import Image, ImageChops, ImageDraw, ImageFont

from anishift.services.subtitles import is_drawing, load_subtitles, visible_text, visible_verses
from anishift.services.subtitles.restyle import clone_source
from anishift.services.subtitles.text import RE_TAG_BLOCK
from anishift.utils.logger import LoggerMode, setup_mode
from anishift.utils.logger.config import FileConfig
from scripts.subtitle_quality import metrics
from scripts.subtitle_quality.episode import FRAMES_NAME, SOURCE_NAME, video_path
from scripts.subtitle_quality.render import (
    Shot,
    copy_scripts,
    measure_boxes,
    nearest_frame,
    prepare_fonts,
    render_shot,
)
from scripts.subtitle_quality.replay import matched_pairs
from scripts.subtitle_quality.report import format_time

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.subtitles import Category
    from scripts.subtitle_quality.metrics import Box, Size

# ── Constants ─────────────────────────────────────────────────────────────────

GALLERY_ROOT: Final[str] = "experiments/gallery"
"""Quality-root folder holding one gallery folder per compared pair of replays."""

CASES_PER_KIND: Final[int] = 10
"""Largest changes of each kind rendered by default; hard cases are always rendered."""

INDEX_NAME: Final[str] = "index.md"
"""Markdown index of a gallery folder."""

KIND_HARD: Final[str] = "przypadek trudny"
"""Case from the hard-case list, rendered whether or not anything changed."""

KIND_WIDTH: Final[str] = "szerokość szyldu"
"""Positioned sign whose rendered width changed."""

KIND_NEW_COLLISION: Final[str] = "nowa kolizja szyldów"
"""Two concurrent signs that overlap only after the change."""

KIND_REMOVED_COLLISION: Final[str] = "usunięta kolizja szyldów"
"""Two concurrent signs that overlapped only before the change."""

KIND_BREAKS: Final[str] = "podział wierszy"
"""Non-sign event whose lines changed."""

KIND_MARKERS: Final[str] = "znaczniki stylu"
"""Event whose style tags moved, appeared or disappeared."""

KIND_DECISION: Final[str] = "decyzja lektora"
"""Event the narrator reads on one side and leaves on screen on the other."""

KINDS: Final[tuple[str, ...]] = (
    KIND_HARD,
    KIND_WIDTH,
    KIND_NEW_COLLISION,
    KIND_REMOVED_COLLISION,
    KIND_BREAKS,
    KIND_MARKERS,
    KIND_DECISION,
)
"""Order of the kinds in the gallery."""

DECISIONS_KEY: Final[str] = "decisions"
"""Optional mapping entry field: the reader decision of every source Dialogue event."""

SPOKEN: Final[str] = "spoken"
"""Reader decision of an event the narrator reads."""

TAG_SPOKEN: Final[str] = "LEKTOR CZYTA"
"""Outline label of an event the narrator reads."""

TAG_SCREEN: Final[str] = "TYLKO NA EKRANIE"
"""Outline label of an event left on screen."""

_WORK_NAME: Final[str] = ".work"
"""Gallery subfolder holding per-pair render work, removed after the run."""

_GAP: Final[int] = 16
"""Gap between the before and after halves in pixels."""

_BEFORE_COLOUR: Final[str] = "#ffb347"
"""Heading and outline colour of the before half."""

_AFTER_COLOUR: Final[str] = "#5ab4ff"
"""Heading and outline colour of the after half."""

_COLOURS: Final[tuple[str, str]] = (_BEFORE_COLOUR, _AFTER_COLOUR)
"""Colours of the before and after halves."""

_TAG_COLOURS: Final[dict[str, str]] = {TAG_SPOKEN: "#40e070", TAG_SCREEN: "#b0b0b0"}
"""Outline colour of each reader label."""

_CANVAS_COLOUR: Final[str] = "#1c1c1c"
"""Background of a gallery image."""

_FONT: Final[str] = "arial.ttf"
"""Caption font file found in the system font folder."""

_BOLD_FONT: Final[str] = "arialbd.ttf"
"""Bold caption font file found in the system font folder."""

_OUTLINE_PAD: Final[int] = 8
"""Space between a changed event and its outline in gallery pixels."""

_TAG_HEIGHT: Final[int] = 34
"""Height of a reader label drawn above or below its outline."""

_ZOOM_MARGIN: Final[int] = 14
"""Space around the changed place in its zoom, in gallery pixels."""

_ZOOM_HEIGHT: Final[int] = 240
"""Tallest zoom of two stacked zooms in pixels; zooms side by side may be twice as tall."""

_ZOOM_INDENT: Final[int] = 170
"""Left edge of stacked zooms, leaving room for their labels."""

_ZOOM_FACTOR: Final[float] = 5.0
"""Largest zoom magnification."""

_HIDDEN_TAG: Final[str] = r"{\alpha&HFF&}"
"""Override block making the rest of an event fully transparent."""

_MASK_THRESHOLD: Final[int] = 40
"""Brightness difference above which a pixel belongs to the hidden events."""

_RE_BRACKETS: Final[re.Pattern[str]] = re.compile(r"\[[^\]]*\]|\([^)]*\)")
"""Release-group, checksum and quality groups in an episode folder name."""

_RE_RELEASE: Final[re.Pattern[str]] = re.compile(r"[ .]\d{3,4}p\b.*")
"""Resolution token and the release details after it."""

_RE_LINE_BREAK: Final[re.Pattern[str]] = re.compile(r"\\[Nn]")
"""Hard or soft ASS line break."""


@dataclass(frozen=True, slots=True)
class HardCase:
    """Moment of a pair to render whatever changed: pair id, time and why it is hard."""

    pair: str
    time_ms: int
    description: str


@dataclass(frozen=True, slots=True)
class Case:
    """One change to show: where and when, its kind, one mechanical sentence and how each side reads."""

    pair: str
    kind: str
    time_ms: int
    indexes: tuple[int, ...]
    description: str
    before: str
    after: str
    rank: float = 0.0
    tags: tuple[str, str] = ("", "")


@dataclass(frozen=True, slots=True)
class PairFiles:
    """Replay outputs before and after the change, the pair folder and its render work folder."""

    directory: Path
    before: Path
    after: Path
    work: Path


@dataclass(frozen=True, slots=True)
class Mismatch:
    """Event left out of the comparison because its timing, layer, style or visible wording differs."""

    pair: str
    index: int
    time_ms: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class Selection:
    """Every case of two replays, the events and pairs left out and the pairs whose reader decisions are unknown."""

    cases: tuple[Case, ...]
    pairs: dict[str, PairFiles]
    skipped: tuple[tuple[str, str], ...]
    undecided: tuple[str, ...]
    mismatches: tuple[Mismatch, ...] = ()


@dataclass(frozen=True, slots=True)
class Panel:
    """Everything one before/after image shows."""

    title: str
    subtitle: str
    labels: tuple[str, str]
    images: tuple[Image.Image, Image.Image]
    notes: tuple[str, str]
    boxes: tuple[Box | None, Box | None]
    tags: tuple[str, str]
    footer: str


# ── Selection ─────────────────────────────────────────────────────────────────


def load_hard_cases(path: Path) -> tuple[HardCase, ...]:
    """Read a JSON list of ``{"pair", "time_ms", "description"}`` hard cases."""
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return tuple(HardCase(str(row["pair"]), int(row["time_ms"]), str(row["description"])) for row in rows)


def find_cases(base: Path, other: Path, pairs_root: Path, work_root: Path, hard: Sequence[HardCase] = ()) -> Selection:
    """Find every case of two replays with equal inputs, leaving out excluded events."""
    matched, skipped = matched_pairs(base, other)
    cases: list[Case] = []
    pairs: dict[str, PairFiles] = {}
    undecided: list[str] = []
    mismatches: list[Mismatch] = []
    for position, (pair_id, first, second) in enumerate(matched):
        if first["inputs"] != second["inputs"]:
            skipped.append((pair_id, "inputs differ"))
            continue
        files: PairFiles = PairFiles(
            pairs_root / pair_id, base / first["output"], other / second["output"], work_root / f"{position:03d}"
        )
        before: SSAFile = load_subtitles(files.before)
        after: SSAFile = load_subtitles(files.after)
        if len(metrics.dialogue(before)) != len(metrics.dialogue(after)):
            skipped.append((pair_id, "event counts differ"))
            continue
        pairs[pair_id] = files
        decisions: tuple[list[str], list[str]] | None = _decisions(first, second)
        if decisions is None:
            undecided.append(pair_id)
        excluded: frozenset[int] = frozenset(first["excluded"]) | frozenset(second["excluded"])
        foreign: list[int] = mismatched_events(before, after, excluded)
        mismatches.extend(_mismatch(pair_id, index, before, after) for index in foreign)
        pair_hard: list[HardCase] = [case for case in hard if case.pair == pair_id]
        left_out: frozenset[int] = excluded | frozenset(foreign)
        cases.extend(pair_cases(pair_id, files, (before, after), left_out, decisions, pair_hard))
    skipped.extend((case.pair, "hard case pair not compared") for case in hard if case.pair not in pairs)
    return Selection(tuple(cases), pairs, tuple(skipped), tuple(undecided), tuple(mismatches))


def mismatched_events(before: SSAFile, after: SSAFile, excluded: frozenset[int]) -> list[int]:
    """Return the events, outside the excluded ones, whose timing, layer, style or visible wording differs."""
    return [
        index
        for index, (left, right) in enumerate(zip(metrics.dialogue(before), metrics.dialogue(after), strict=True))
        if index not in excluded and (_identity(left), _wording(left)) != (_identity(right), _wording(right))
    ]


def _identity(event: SSAEvent) -> tuple[int, int, int, str]:
    return event.start, event.end, event.layer, clone_source(event.style)


def _wording(event: SSAEvent) -> str:
    return "".join(visible_text(event.text).split())


def _mismatch(pair_id: str, index: int, before: SSAFile, after: SSAFile) -> Mismatch:
    left, right = metrics.dialogue(before)[index], metrics.dialogue(after)[index]
    return Mismatch(pair_id, index, left.start, _lines(left.text), _lines(right.text))


def _lines(text: str) -> str:
    return " / ".join(visible_verses(text))


def _decisions(first: dict[str, Any], second: dict[str, Any]) -> tuple[list[str], list[str]] | None:
    if DECISIONS_KEY not in first or DECISIONS_KEY not in second:
        return None
    return list(first[DECISIONS_KEY]), list(second[DECISIONS_KEY])


def pair_cases(  # noqa: PLR0913 - one pair gathers every kind of change
    pair_id: str,
    files: PairFiles,
    subs: tuple[SSAFile, SSAFile],
    excluded: frozenset[int],
    decisions: tuple[list[str], list[str]] | None,
    hard: Sequence[HardCase],
) -> list[Case]:
    """Return every case of one pair: hard cases, sign widths and collisions, lines, style tags and decisions."""
    before, after = subs
    events: tuple[list[SSAEvent], list[SSAEvent]] = (metrics.dialogue(before), metrics.dialogue(after))
    changed: list[int] = changed_events(before, after, excluded)
    cases: list[Case] = [_hard_case(pair_id, case, events, changed, excluded) for case in hard]
    if decisions is not None:
        cases.extend(decision_cases(pair_id, events[0], decisions, excluded))
    if not changed:
        return cases
    verdicts: dict[str, Category] = metrics.style_verdicts(load_subtitles(files.directory / SOURCE_NAME))
    kept: list[tuple[int, int]] = [(index, index) for index in range(len(events[0])) if index not in excluded]
    signs: list[metrics.Sign] = metrics.select_signs(events[0], events[1], kept, verdicts)
    measured: list[metrics.Sign] = _measured_signs(signs, set(changed), files, subs)
    cases.extend(width_cases(pair_id, measured, set(changed)))
    cases.extend(collision_cases(pair_id, measured, set(changed)))
    sign_indexes: set[int] = {sign.source_index for sign in signs}
    cases.extend(break_cases(pair_id, events, [index for index in changed if index not in sign_indexes]))
    cases.extend(marker_cases(pair_id, events, changed))
    return cases


def changed_events(before: SSAFile, after: SSAFile, excluded: frozenset[int]) -> list[int]:
    """Return the Dialogue events, outside the excluded ones, whose fields or style definition differ."""
    changed: list[int] = []
    for index, (left, right) in enumerate(zip(metrics.dialogue(before), metrics.dialogue(after), strict=True)):
        same_style: bool = before.styles.get(left.style) == after.styles.get(right.style)
        if index not in excluded and not (left.equals(right) and same_style):
            changed.append(index)
    return changed


def _measured_signs(
    signs: Sequence[metrics.Sign], changed: set[int], files: PairFiles, subs: tuple[SSAFile, SSAFile]
) -> list[metrics.Sign]:
    touched: set[int] = {number for number, sign in enumerate(signs) if sign.source_index in changed}
    relevant: set[int] = set(touched)
    for first, second in metrics.concurrent_pairs([(sign.start, sign.end) for sign in signs]):
        if first in touched or second in touched:
            relevant.update((first, second))
    picked: list[int] = sorted(relevant)
    if not picked:
        return []
    _prepare(files)
    before, after = subs
    size: Size = metrics.play_size(before)
    events: tuple[list[SSAEvent], list[SSAEvent]] = (metrics.dialogue(before), metrics.dialogue(after))
    moved: list[int] = [number for number in picked if number in touched]
    base_boxes, _ = measure_boxes(
        before, [events[0][signs[number].source_index] for number in picked], size, files.work, "compare-before"
    )
    moved_boxes, _ = measure_boxes(
        after, [events[1][signs[number].output_index] for number in moved], size, files.work, "compare-after"
    )
    after_boxes: dict[int, Box | None] = dict(zip(moved, moved_boxes, strict=True))
    return [
        replace(signs[number], source_box=box, output_box=after_boxes.get(number, box))
        for number, box in zip(picked, base_boxes, strict=True)
    ]


def width_cases(pair_id: str, signs: Sequence[metrics.Sign], changed: set[int]) -> list[Case]:
    """Return a case for every changed sign whose rendered width differs, ranked by relative change."""
    cases: list[Case] = []
    for sign in signs:
        if sign.source_index not in changed or sign.source_box is None or sign.output_box is None:
            continue
        width: int = max(1, sign.source_box[2] - sign.source_box[0])
        new_width: int = sign.output_box[2] - sign.output_box[0]
        if new_width == width:
            continue
        change: float = (new_width - width) / width
        cases.append(
            Case(
                pair_id,
                KIND_WIDTH,
                (sign.start + sign.end) // 2,
                (sign.source_index,),
                f"Szerokość szyldu zmieniła się z {width} na {new_width} px ({round(100 * change):+d}%).",
                f"„{sign.source_text}”, szerokość {width} px",
                f"„{sign.output_text}”, szerokość {new_width} px",
                abs(change),
            )
        )
    return cases


def collision_cases(pair_id: str, signs: Sequence[metrics.Sign], changed: set[int]) -> list[Case]:
    """Return a case for every pair of concurrent static signs that overlaps on one side only."""
    cases: list[Case] = []
    for first, second in metrics.concurrent_pairs([(sign.start, sign.end) for sign in signs]):
        pair: list[metrics.Sign] = [signs[first], signs[second]]
        if not {sign.source_index for sign in pair} & changed:
            continue
        new: bool = metrics.new_overlaps(pair)[0][0] > 0
        removed: bool = metrics.new_overlaps([_swapped(sign) for sign in pair])[0][0] > 0
        if new or removed:
            cases.append(_collision(pair_id, pair, new=new))
    return cases


def _swapped(sign: metrics.Sign) -> metrics.Sign:
    return replace(
        sign,
        source_box=sign.output_box,
        output_box=sign.source_box,
        source_clip=sign.output_clip,
        output_clip=sign.source_clip,
    )


def _collision(pair_id: str, pair: Sequence[metrics.Sign], *, new: bool) -> Case:
    names: str = f"„{pair[0].source_text}” i „{pair[1].source_text}”"
    time_ms: int = (max(sign.start for sign in pair) + min(sign.end for sign in pair)) // 2
    crossing: tuple[str, str] = ("nie przecinają się", "przecinają się")
    description: str = (
        f"Prostokąty obwiedni szyldów {names} przecinają się po zmianie, a przed nią się nie przecinały."
        if new
        else f"Prostokąty obwiedni szyldów {names} przecinały się przed zmianą, a po niej przestały się przecinać."
    )
    return Case(
        pair_id,
        KIND_NEW_COLLISION if new else KIND_REMOVED_COLLISION,
        time_ms,
        tuple(sign.source_index for sign in pair),
        description,
        f"Prostokąty obwiedni szyldów {names} {crossing[not new]}.",
        f"Prostokąty obwiedni szyldów „{pair[0].output_text}” i „{pair[1].output_text}” {crossing[new]}.",
    )


def break_cases(pair_id: str, events: tuple[list[SSAEvent], list[SSAEvent]], indexes: Iterable[int]) -> list[Case]:
    """Return a case for every event whose visible lines differ, ranked by line-count and longest-line change."""
    cases: list[Case] = []
    for index in indexes:
        left, right = events[0][index], events[1][index]
        lines: tuple[tuple[str, ...], tuple[str, ...]] = (visible_verses(left.text), visible_verses(right.text))
        if is_drawing(left.text) or lines[0] == lines[1]:
            continue
        longest: tuple[int, int] = (max(map(len, lines[0]), default=0), max(map(len, lines[1]), default=0))
        rank: float = 100 * abs(len(lines[0]) - len(lines[1])) + abs(longest[0] - longest[1])
        cases.append(
            Case(
                pair_id,
                KIND_BREAKS,
                (left.start + left.end) // 2,
                (index,),
                f"Podział wierszy zmienił się z „{' / '.join(lines[0])}” na „{' / '.join(lines[1])}”.",
                f"„{' / '.join(lines[0])}” (wierszy: {len(lines[0])}, najdłuższy: {longest[0]} znaków)",
                f"„{' / '.join(lines[1])}” (wierszy: {len(lines[1])}, najdłuższy: {longest[1]} znaków)",
                rank,
            )
        )
    return cases


def marker_layout(text: str) -> tuple[tuple[int, tuple[str, ...]], ...]:
    """Return each style-tag block of an event with its tags and the visible non-space characters before it."""
    layout: list[tuple[int, tuple[str, ...]]] = []
    for block in RE_TAG_BLOCK.finditer(text):
        tokens: tuple[str, ...] = metrics.style_tokens(block.group(0))
        if tokens:
            before: str = "".join(" ".join(visible_verses(text[: block.start()])).split())
            layout.append((len(before), tokens))
    return tuple(layout)


def tagged_view(text: str) -> str:
    """Return an event's text keeping only its style tags, lines joined by `` / ``."""

    def style_block(match: re.Match[str]) -> str:
        tokens: tuple[str, ...] = metrics.style_tokens(match.group(0))
        return "{" + "".join(tokens) + "}" if tokens else ""

    kept: str = RE_TAG_BLOCK.sub(style_block, text)
    return " / ".join(" ".join(line.split()) for line in _RE_LINE_BREAK.split(kept))


def marker_cases(pair_id: str, events: tuple[list[SSAEvent], list[SSAEvent]], indexes: Iterable[int]) -> list[Case]:
    """Return a case for every event whose style tags moved, appeared or disappeared."""
    cases: list[Case] = []
    for index in indexes:
        left, right = events[0][index], events[1][index]
        layouts: tuple[tuple[tuple[int, tuple[str, ...]], ...], ...] = (
            marker_layout(left.text),
            marker_layout(right.text),
        )
        if is_drawing(left.text) or layouts[0] == layouts[1]:
            continue
        views: tuple[str, str] = (tagged_view(left.text), tagged_view(right.text))
        cases.append(
            Case(
                pair_id,
                KIND_MARKERS,
                (left.start + left.end) // 2,
                (index,),
                f"Znaczniki stylu zmieniły się z „{views[0]}” na „{views[1]}”.",
                views[0],
                views[1],
                len(set(layouts[0]) ^ set(layouts[1])),
            )
        )
    return cases


def _reads(decision: str) -> str:
    return "czyta" if decision == SPOKEN else "tylko ekran"


def decision_cases(
    pair_id: str, events: Sequence[SSAEvent], decisions: tuple[list[str], list[str]], excluded: frozenset[int]
) -> list[Case]:
    """Return a case for every event, outside the excluded ones, whose reader decision differs."""
    cases: list[Case] = []
    for index, (event, old, new) in enumerate(zip(events, *decisions, strict=True)):
        if old == new or index in excluded:
            continue
        text: str = _lines(event.text)
        cases.append(
            Case(
                pair_id,
                KIND_DECISION,
                (event.start + event.end) // 2,
                (index,),
                f"Decyzja lektora zmieniła się z „{_reads(old)}” na „{_reads(new)}”.",
                f"Lektor: {_reads(old)}. „{text}” (styl „{event.style}”)",
                f"Lektor: {_reads(new)}. „{text}” (styl „{event.style}”)",
                tags=(_tag(old), _tag(new)),
            )
        )
    return cases


def _tag(decision: str) -> str:
    return TAG_SPOKEN if decision == SPOKEN else TAG_SCREEN


def _hard_case(
    pair_id: str,
    case: HardCase,
    events: tuple[list[SSAEvent], list[SSAEvent]],
    changed: list[int],
    excluded: frozenset[int],
) -> Case:
    visible: list[int] = [
        index
        for index, event in enumerate(events[0])
        if event.start <= case.time_ms < event.end
        and index not in excluded
        and visible_text(event.text)
        and not is_drawing(event.text)
    ]
    active: tuple[int, ...] = tuple(index for index in visible if index in changed)
    shown: tuple[int, ...] = active or tuple(visible)
    return Case(
        pair_id,
        KIND_HARD,
        case.time_ms,
        shown,
        f"{case.description} (zmienione zdarzenia w tej chwili: {len(active)} z {len(visible)}).",
        "; ".join(f"„{_lines(events[0][index].text)}”" for index in shown),
        "; ".join(f"„{_lines(events[1][index].text)}”" for index in shown),
    )


def chosen(cases: Sequence[Case], size: int) -> list[Case]:
    """Return every hard case and the ``size`` highest-ranked cases of each other kind, in gallery order."""
    shown: list[Case] = []
    for kind in KINDS:
        ranked: list[Case] = sorted((case for case in cases if case.kind == kind), key=lambda case: -case.rank)
        shown.extend(ranked if kind == KIND_HARD else ranked[:size])
    return shown


# ── Rendering ─────────────────────────────────────────────────────────────────


def _prepare(files: PairFiles) -> None:
    files.work.mkdir(parents=True, exist_ok=True)
    prepare_fonts(files.directory, video_path(files.directory), files.work)


def episode_title(pair_id: str) -> str:
    """Return a readable episode title from a pair id, without release groups, checksums and release details."""
    name: str = pair_id.rsplit("/", 1)[-1]
    title: str = _RE_RELEASE.sub("", _RE_BRACKETS.sub(" ", name))
    if " " not in title.strip():
        title = title.replace(".", " ")
    return " ".join(title.split()) or name


def _frame_note(files: PairFiles, time_ms: int) -> str:
    frame: Path | None = nearest_frame(files.directory / FRAMES_NAME, time_ms)
    if frame is not None:
        return f"zapisana klatka {int(frame.stem) - time_ms:+d} ms od chwili napisów"
    if video_path(files.directory) is not None:
        return f"klatka z wideo w {format_time(time_ms)}"
    return "brak wideo i klatek: szare tło"


def render_case(case: Case, number: int, files: PairFiles, labels: tuple[str, str], target: Path) -> None:
    """Render one case: both replays on one frame, outlines and a zoom of the change, with Polish captions."""
    _prepare(files)
    size: Size = metrics.play_size(load_subtitles(files.before))
    halves: tuple[Image.Image, Image.Image] = render_halves(files, (files.before, files.after), case.time_ms, size)
    boxes: tuple[Box | None, Box | None] = placed_boxes(files, case, halves, size)
    panel: Panel = Panel(
        title=f"{number:02d}. {case.kind[:1].upper()}{case.kind[1:]}",
        subtitle=f"{episode_title(case.pair)} — {format_time(case.time_ms)} ({_frame_note(files, case.time_ms)}). "
        f"{case.description}",
        labels=labels,
        images=halves,
        notes=(case.before, case.after),
        boxes=boxes,
        tags=case.tags,
        footer=(
            "Te same wejścia replay po obu stronach; różnicę robi wyłącznie kod. Ta sama chwila i ta sama klatka. "
            "Ramka: miejsce zdarzeń przypadku na tym obrazie (różnica renderu libass z tymi zdarzeniami i bez nich)."
        ),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    compose(panel).save(target)


def render_halves(
    files: PairFiles, scripts: tuple[Path, Path], time_ms: int, size: Size
) -> tuple[Image.Image, Image.Image]:
    """Render two whole scripts at one moment on the pair's frame and return the two gallery-sized images."""
    copy_scripts(scripts[0], scripts[1], files.work)
    shot: Shot = Shot(time_ms, files.work / "annotated.png", "")
    render_shot(shot, video_path(files.directory), files.directory / FRAMES_NAME, size, files.work)
    with Image.open(files.work / "shot.png") as raw:
        image: Image.Image = raw.convert("RGB")
    half: int = image.height // 2
    return image.crop((0, 0, image.width, half)), image.crop((0, half, image.width, image.height))


def placed_boxes(
    files: PairFiles, case: Case, shown: tuple[Image.Image, Image.Image], size: Size
) -> tuple[Box | None, Box | None]:
    """Return where the case events are drawn on each rendered half, from a second render with them invisible."""
    if not case.indexes:
        return None, None
    hidden: list[Path] = []
    for number, script in enumerate((files.before, files.after)):
        subs: SSAFile = load_subtitles(script)
        events: list[SSAEvent] = metrics.dialogue(subs)
        for index in case.indexes:
            events[index].text = hidden_text(events[index].text)
        path: Path = files.work / f"hidden-{number}.ass"
        subs.save(str(path), encoding="utf-8")
        hidden.append(path)
    without: tuple[Image.Image, Image.Image] = render_halves(files, (hidden[0], hidden[1]), case.time_ms, size)
    return _difference_box(shown[0], without[0]), _difference_box(shown[1], without[1])


def hidden_text(text: str) -> str:
    """Return an event's text made fully transparent, keeping its layout and the space it takes."""
    return _HIDDEN_TAG + RE_TAG_BLOCK.sub(lambda block: block.group(0)[:-1] + _HIDDEN_TAG[1:], text)


def _difference_box(shown: Image.Image, without: Image.Image) -> Box | None:
    mask: Image.Image = ImageChops.difference(shown, without).convert("L").point(_mask_level)
    return mask.getbbox()


def _mask_level(value: int) -> int:
    return 255 if value > _MASK_THRESHOLD else 0


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_BOLD_FONT if bold else _FONT, size)


def _line_height(size: int) -> int:
    return round(size * 1.3)


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    line: str = ""
    for word in text.split():
        candidate: str = f"{line} {word}".strip()
        if line and font.getlength(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return [*lines, line]


def _write(draw: ImageDraw.ImageDraw, xy: tuple[int, int], lines: Sequence[str], size: int, fill: str) -> None:
    font: ImageFont.FreeTypeFont = _font(size)
    for number, line in enumerate(lines):
        draw.text((xy[0], xy[1] + number * _line_height(size)), line, font=font, fill=fill)


def _outline(image: Image.Image, box: Box | None, colour: str, tag: str) -> Image.Image:
    framed: Image.Image = image.copy()
    if box is None:
        return framed
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(framed)
    rect: Box = (
        max(2, box[0] - _OUTLINE_PAD),
        max(2, box[1] - _OUTLINE_PAD),
        min(framed.width - 3, box[2] + _OUTLINE_PAD),
        min(framed.height - 3, box[3] + _OUTLINE_PAD),
    )
    draw.rectangle(rect, outline=colour, width=5)
    if not tag:
        return framed
    font: ImageFont.FreeTypeFont = _font(24, bold=True)
    width: float = font.getlength(tag)
    top: int = rect[1] - _TAG_HEIGHT if rect[1] > _TAG_HEIGHT + 6 else rect[3] + 6
    left: float = min(max(4, rect[0]), framed.width - width - 12)
    draw.rectangle((left - 4, top - 2, left + width + 6, top + _TAG_HEIGHT - 4), fill=colour)
    draw.text((left + 1, top), tag, font=font, fill="#000000")
    return framed


def _zooms(images: Sequence[Image.Image], boxes: Sequence[Box | None]) -> tuple[list[Image.Image], bool]:
    found: list[Box] = [box for box in boxes if box is not None]
    if not found:
        return [], False
    width, height = images[0].size
    area: Box = (
        max(0, min(box[0] for box in found) - _ZOOM_MARGIN),
        max(0, min(box[1] for box in found) - _ZOOM_MARGIN),
        min(width, max(box[2] for box in found) + _ZOOM_MARGIN),
        min(height, max(box[3] for box in found) + _ZOOM_MARGIN),
    )
    if area[0] >= area[2] or area[1] >= area[3]:
        return [], False
    crops: list[Image.Image] = [image.crop(area) for image in images]
    size: tuple[int, int] = crops[0].size
    stacked: float = min((2 * width + _GAP - _ZOOM_INDENT - 30) / size[0], _ZOOM_HEIGHT / size[1], _ZOOM_FACTOR)
    beside: float = min((width - 30) / size[0], (2 * _ZOOM_HEIGHT + 16) / size[1], _ZOOM_FACTOR)
    factor: float = max(stacked, beside)
    scaled: tuple[int, int] = (round(size[0] * factor), round(size[1] * factor))
    return [crop.resize(scaled, Image.Resampling.LANCZOS) for crop in crops], beside > stacked


def _zoom_height(zooms: Sequence[Image.Image], *, beside: bool) -> int:
    if not zooms:
        return 0
    return 44 + (50 + zooms[0].height + 16 if beside else 2 * (zooms[0].height + 16))


def _paste_zooms(canvas: Image.Image, zooms: Sequence[Image.Image], top: int, *, beside: bool) -> None:
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(canvas)
    half: int = (canvas.width - _GAP) // 2
    draw.text((20, top + 6), "Powiększenie tego samego miejsca:", font=_font(26, bold=True), fill="#ffffff")
    top += 44
    for number, (zoom, name, colour) in enumerate(zip(zooms, ("PRZED", "PO"), _COLOURS, strict=True)):
        x: int = number * (half + _GAP) if beside else 0
        y: int = top if beside else top + number * (zoom.height + 16)
        draw.rectangle((x + 10, y, x + 150, y + 40), fill=colour)
        draw.text((x + 20, y + 6), name, font=_font(26, bold=True), fill="#000000")
        canvas.paste(zoom, (x + (half - zoom.width) // 2, y + 50) if beside else (_ZOOM_INDENT, y))


def compose(panel: Panel) -> Image.Image:
    """Assemble the captioned before/after image with outlines, notes and a zoom of the changed place."""
    half: int = panel.images[0].width
    width: int = 2 * half + _GAP
    framed: list[Image.Image] = [
        _outline(image, box, _TAG_COLOURS.get(tag, colour), tag)
        for image, box, colour, tag in zip(panel.images, panel.boxes, _COLOURS, panel.tags, strict=True)
    ]
    subtitle: list[str] = _wrap(panel.subtitle, _font(24), width - 40)
    notes: list[list[str]] = [_wrap(note, _font(24), half - 30) for note in panel.notes]
    footer: list[str] = _wrap(panel.footer, _font(22), width - 40)
    zooms, beside = _zooms(panel.images, panel.boxes)
    header: int = 58 + len(subtitle) * _line_height(24) + 12
    notes_height: int = max(map(len, notes)) * _line_height(24) + 20
    zoom_height: int = _zoom_height(zooms, beside=beside)
    height: int = header + 46 + framed[0].height + 10 + notes_height + zoom_height + len(footer) * _line_height(22) + 16
    canvas: Image.Image = Image.new("RGB", (width, height), _CANVAS_COLOUR)
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(canvas)
    draw.text((20, 14), panel.title, font=_font(32, bold=True), fill="#ffffff")
    _write(draw, (20, 58), subtitle, 24, "#d0d0d0")
    top: int = header
    for x, label, colour, image, lines in zip((0, half + _GAP), panel.labels, _COLOURS, framed, notes, strict=True):
        draw.rectangle((x, top, x + half - 1, top + 40), fill=colour)
        draw.text((x + 14, top + 6), label, font=_font(28, bold=True), fill="#000000")
        canvas.paste(image, (x, top + 46))
        _write(draw, (x + 14, top + 46 + image.height + 10), lines, 24, "#ffffff")
    top += 46 + framed[0].height + 10 + notes_height
    if zooms:
        _paste_zooms(canvas, zooms, top, beside=beside)
    _write(draw, (20, top + zoom_height), footer, 22, "#bdbdbd")
    return canvas


# ── Gallery ───────────────────────────────────────────────────────────────────


def write_gallery(selection: Selection, shown: Sequence[Case], out: Path, names: tuple[str, str]) -> None:
    """Render the shown cases into ``out`` and write its Markdown index."""
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    labels: tuple[str, str] = (f"PRZED — {names[0]}", f"PO — {names[1]}")
    for number, case in enumerate(shown, start=1):
        print(f"rendering {number:02d}.png  {case.kind}  {case.pair}", file=sys.stderr)
        render_case(case, number, selection.pairs[case.pair], labels, out / f"{number:02d}.png")
    (out / INDEX_NAME).write_text(index_text(selection, shown, names), encoding="utf-8")


def index_text(selection: Selection, shown: Sequence[Case], names: tuple[str, str]) -> str:
    """Return the Markdown gallery index: counts per kind, one row per image, skipped and undecided pairs."""
    lines: list[str] = [
        f"# Galeria przed/po: {names[0]} → {names[1]}",
        "",
        f"Przed: `{names[0]}`. Po: `{names[1]}`. Porównane pary: {len(selection.pairs)}. Obie strony mają te same "
        "wejścia replay (`mapping.json`), więc różnicę robi wyłącznie kod. Każdy obraz pokazuje tę samą chwilę na tej "
        "samej klatce, z ramką i powiększeniem miejsca zmiany. Opisy są mechaniczne; ocenę „lepiej / bez zmian / "
        "gorzej” wystawia człowiek.",
        "",
        "| Rodzaj zmiany | Wykryto | Pokazano |",
        "| --- | --- | --- |",
    ]
    for kind in KINDS:
        found: int = sum(case.kind == kind for case in selection.cases)
        lines.append(f"| {kind} | {found} | {sum(case.kind == kind for case in shown)} |")
    lines.extend(["", "## Przypadki", ""])
    if not shown:
        lines.append("Brak przypadków: 0 zmian.")
    else:
        lines.extend(["| # | Odcinek | Czas | Rodzaj | Opis | Obraz |", "| --- | --- | --- | --- | --- | --- |"])
        lines.extend(
            f"| {number} | {_cell(episode_title(case.pair))} | {format_time(case.time_ms)} | {case.kind} | "
            f"{_cell(case.description)} | [{number:02d}.png]({number:02d}.png) |"
            for number, case in enumerate(shown, start=1)
        )
    if selection.mismatches:
        lines.extend(_mismatch_lines(selection.mismatches))
    if selection.skipped:
        lines.extend(["", "## Pominięte pary", ""])
        lines.extend(f"- `{pair}`: {reason}" for pair, reason in selection.skipped)
    if selection.undecided:
        lines.extend(
            [
                "",
                "## Decyzje lektora",
                "",
                f"Niesprawdzone w {len(selection.undecided)} z {len(selection.pairs)} par: `mapping.json` co najmniej "
                f"jednego przebiegu nie zapisuje pola `{DECISIONS_KEY}`.",
            ]
        )
    return "\n".join(lines) + "\n"


def _mismatch_lines(mismatches: Sequence[Mismatch]) -> list[str]:
    by_pair: dict[str, list[Mismatch]] = {}
    for mismatch in mismatches:
        by_pair.setdefault(mismatch.pair, []).append(mismatch)
    lines: list[str] = [
        "",
        "## Inny tekst — poza porównaniem",
        "",
        f"Zdarzenia z innym czasem, warstwą, stylem albo widocznym tekstem po obu stronach: {len(mismatches)}. "
        "Nie trafiają do żadnego rodzaju zmiany ani do obrazów.",
        "",
        "| Odcinek | Zdarzeń | Pierwsze: czas | Przed | Po |",
        "| --- | --- | --- | --- | --- |",
    ]
    for pair, rows in by_pair.items():
        first: Mismatch = rows[0]
        lines.append(
            f"| {_cell(episode_title(pair))} | {len(rows)} | {format_time(first.time_ms)} | "
            f"{_cell(first.before)} | {_cell(first.after)} |"
        )
    return lines


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def main(argv: Sequence[str], quality_root: Path) -> int:
    """Compare two replay folders and render the gallery; return 1 when any change or mismatched event is found."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality compare",
        description=(
            "Compare two replay folders with equal inputs and render before/after images of the largest sign width "
            "changes, new and removed sign collisions, changed lines, moved style tags, changed reader decisions "
            f"(when both mappings record '{DECISIONS_KEY}') and every listed hard case, with a Markdown index."
        ),
    )
    parser.add_argument("base", type=Path, help="replay folder before the change")
    parser.add_argument("other", type=Path, help="replay folder after the change")
    parser.add_argument("--out", type=Path, help=f"gallery folder; default {GALLERY_ROOT}/<base>-vs-<other>")
    parser.add_argument("--pairs", type=Path, default=quality_root, help="folder holding the pair folders by pair id")
    parser.add_argument("--hard", type=Path, help='JSON list of hard cases {"pair", "time_ms", "description"}')
    parser.add_argument("--size", type=int, default=CASES_PER_KIND, help="cases rendered per kind of change")
    args: argparse.Namespace = parser.parse_args(argv)
    setup_mode(LoggerMode.SILENT, file=FileConfig(enable=False))
    out: Path = args.out or quality_root / GALLERY_ROOT / f"{args.base.name}-vs-{args.other.name}"
    hard: tuple[HardCase, ...] = load_hard_cases(args.hard) if args.hard else ()
    try:
        selection: Selection = find_cases(args.base, args.other, args.pairs, out / _WORK_NAME, hard)
        shown: list[Case] = chosen(selection.cases, args.size)
        write_gallery(selection, shown, out, (args.base.name, args.other.name))
    finally:
        shutil.rmtree(out / _WORK_NAME, ignore_errors=True)
    changes: int = sum(case.kind != KIND_HARD for case in selection.cases)
    print(
        f"cases {changes}  hard {len(selection.cases) - changes}  shown {len(shown)}  "
        f"mismatched {len(selection.mismatches)}  skipped {len(selection.skipped)}"
    )
    print(f"gallery {out / INDEX_NAME}", file=sys.stderr)
    return 1 if changes or selection.mismatches else 0
