"""Check the layout measurement against libass on static events of the quality pairs, with wrap controls."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from anishift.services.fonts import FontIndex
from anishift.services.subtitles.classifier import Category
from anishift.services.subtitles.geometry import (
    Rect,
    RenderProfile,
    TextBox,
    available_width,
    measure_text,
    screen_rects,
    wrap_text,
)
from anishift.services.subtitles.service import load_subtitles
from anishift.services.subtitles.text import is_drawing, visible_text, visible_verses
from anishift.utils.logger import LoggerMode, setup_mode
from anishift.utils.logger.config import FileConfig
from scripts.subtitle_quality import metrics
from scripts.subtitle_quality.episode import FONTS_NAME, OUTPUT_NAME, SOURCE_NAME, pair_fonts, work_dir
from scripts.subtitle_quality.render import PAD_FRACTION, measure_boxes, prepare_fonts, wrap_breaks
from scripts.subtitle_quality.replay import REPLAY_ROOTS, pair_dirs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.subtitles.types import FontSources
    from scripts.subtitle_quality.metrics import Box, Size

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_SIGNS: Final[int] = 120
"""Static sign events sampled per pair, spread evenly over the episode."""

MAX_DIALOGUE: Final[int] = 40
"""Static dialogue events sampled per pair, spread evenly over the episode."""

MAX_DURATION_MS: Final[int] = 20000
"""Longest event sampled; longer ones are usually karaoke or screen-long notes."""

MIN_BOX: Final[tuple[int, int]] = (8, 4)
"""Smallest libass box, width and height in script pixels, compared at all."""

GATE_MIN_WIDTH: Final[int] = 100
"""Narrowest libass box in script pixels that counts toward the width gate."""

WIDTH_P90_LIMIT: Final[float] = 1.5
"""Largest allowed 90th percentile of the width error in percent."""

WIDTH_P99_LIMIT: Final[float] = 4.0
"""Largest allowed 99th percentile of the width error in percent."""

HEIGHT_P90_LIMIT: Final[float] = 5.0
"""Largest allowed 90th percentile of the height error in percent."""

CONTROL_MARGIN: Final[float] = 0.25
"""Share of the script width given to each side margin of a margin control."""

MAX_MARGIN_CONTROLS: Final[int] = 10
"""Dialogue events per pair and language turned into margin controls that wrap only under the narrower margins."""

DEFAULT_JOBS: Final[int] = 4
"""Pair languages rendered by libass at once."""

ROWS_NAME: Final[str] = "calibrate.json"
"""File with every measured sample of a calibration run."""

SUMMARY_NAME: Final[str] = "summary.txt"
"""File with the calibration groups, percentiles and gate verdicts."""

PERCENTILES: Final[tuple[float, ...]] = (0.5, 0.9, 0.99)
"""Error percentiles reported for every group."""

VERDICTS: Final[tuple[str, ...]] = ("agree", "disagree", "unresolved")
"""Outcomes of comparing the automatic line breaks of a sample with the ones libass logged."""

KNOWN_WRAPS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("corpus-pairs/grand-blue-s2-01", "pl", "Disclaimer", "Niniejsze dzieło jest fikcją"),
    ("corpus-pairs/grand-blue-s2-02", "pl", "Disclaimer", "Niniejszy utwór jest fikcją"),
    ("corpus-pairs/grand-blue-s2-04", "pl", "Disclaimer", "Niniejsze dzieło jest fikcją"),
    ("corpus-pairs/grand-blue-s2-05", "pl", "Disclaimer", "Niniejszy utwór jest fikcją"),
    ("corpus-pairs/grand-blue-s2-06", "pl", "Disclaimer", "Niniejszy utwór jest fikcją"),
    ("corpus-pairs/grand-blue-s2-07", "pl", "Disclaimer", "Niniejsze dzieło jest fikcją"),
    ("corpus-pairs/grand-blue-s2-08", "pl", "Disclaimer", "Niniejsze dzieło jest fikcją"),
    ("corpus-pairs/grand-blue-s2-09", "pl", "Disclaimer", "Niniejsze dzieło jest fikcją"),
    ("corpus-pairs/grand-blue-s2-10", "pl", "boxed", "Metodologia powiększania biustu"),
    ("corpus-pairs/grand-blue-s2-11", "pl", "Disclaimer", "Niniejsze dzieło jest fikcją"),
    ("corpus-pairs/grand-blue-s2-12", "en", "handwritten", "As our smart viewers have probably figured"),
    ("corpus-pairs/grand-blue-s2-12", "pl", "Disclaimer", "Niniejsze dzieło jest fikcją"),
)
"""The twelve automatic wraps libass drew in the measurement research: pair, language, style and text start."""

_NO_WRAP: Final[str] = r"{\q2}"
"""Override block prepended to a no-wrap control."""

_RE_DYNAMIC: Final[re.Pattern[str]] = re.compile(
    r"\\(?:move|t\(|org|frz?-?[0-9.]|frx|fry|fax|fay|p[1-9]|k[fo]?[0-9]|K[0-9]|fade\(|fs[+-]|fn@|q[13]|fe)"
)
"""Tags that move, rotate, animate, draw, time or re-encode an event, so it is not static."""

_RE_FADE: Final[re.Pattern[str]] = re.compile(r"\\fad\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)")
"""Simple fade whose in or out time may keep the event translucent at its midpoint."""

type Case = str
"""Sample case: ``static`` for corpus events, ``no-wrap`` and ``margins`` for the controls."""

type Verdict = str
"""Line break outcome, one of ``VERDICTS``."""


@dataclass(frozen=True, slots=True)
class Sample:
    """One event to render and measure, with where it comes from."""

    pair: str
    lang: str
    kind: str
    case: Case
    event: SSAEvent


@dataclass(frozen=True, slots=True)
class Row:
    """Measured and libass-rendered extent and automatic line breaks of one sample."""

    pair: str
    lang: str
    kind: str
    case: Case
    style: str
    text: str
    status: str
    breaks: int
    libass_breaks: int | None
    wrap_slack: float
    estimate: tuple[float, float, float, float] | None
    libass: Box | None
    clipped: bool

    @property
    def comparable(self) -> bool:
        """Tell whether both extents exist and libass drew a whole, large enough box."""
        if self.estimate is None or self.libass is None or self.clipped:
            return False
        return self.libass[2] - self.libass[0] >= MIN_BOX[0] and self.libass[3] - self.libass[1] >= MIN_BOX[1]

    @property
    def libass_width(self) -> int:
        """Return the libass box width, zero without a box."""
        return 0 if self.libass is None else self.libass[2] - self.libass[0]

    @property
    def width_error(self) -> float:
        """Return the width error relative to libass in percent."""
        return _error(self.estimate, self.libass, horizontal=True)

    @property
    def height_error(self) -> float:
        """Return the height error relative to libass in percent."""
        return _error(self.estimate, self.libass, horizontal=False)

    @property
    def verdict(self) -> Verdict:
        """Compare the automatic line breaks the layout predicts with the ones libass logged."""
        if self.libass_breaks is None:
            return "unresolved"
        return "agree" if self.libass_breaks == self.breaks else "disagree"


@dataclass(frozen=True, slots=True)
class Job:
    """Samples of one pair language rendered by libass."""

    directory: Path
    lang: str
    subs: SSAFile
    profile: RenderProfile
    samples: tuple[Sample, ...]


@dataclass(frozen=True, slots=True)
class Gate:
    """One calibration requirement with what was measured."""

    name: str
    passed: bool


# ── Sampling ──────────────────────────────────────────────────────────────────


def is_static(event: SSAEvent, subs: SSAFile) -> bool:
    """Tell whether an event is visible text drawn the same way for its whole lifetime."""
    if is_drawing(event.text) or not visible_text(event.text) or event.style not in subs.styles:
        return False
    duration: int = event.end - event.start
    if not 0 < duration <= MAX_DURATION_MS or _RE_DYNAMIC.search(event.text):
        return False
    if any(int(fade) > duration / 2 for match in _RE_FADE.finditer(event.text) for fade in match.groups()):
        return False
    verses: tuple[str, ...] = visible_verses(event.text)
    return len(verses) == 1 or all(verses)


def spaced[T](items: Sequence[T], limit: int) -> list[T]:
    """Return at most ``limit`` items spread evenly over the sequence."""
    if len(items) <= limit:
        return list(items)
    step: float = len(items) / limit
    return [items[int(number * step)] for number in range(limit)]


def is_known_wrap(pair: str, lang: str, style: str, text: str) -> bool:
    """Tell whether an event is one of the automatic wraps in ``KNOWN_WRAPS``."""
    return any(
        (pair, lang, style) == (known_pair, known_lang, known_style) and text.startswith(prefix)
        for known_pair, known_lang, known_style, prefix in KNOWN_WRAPS
    )


def sample_pair(
    pair: str, source: SSAFile, output: SSAFile, profiles: tuple[RenderProfile, RenderProfile]
) -> list[Sample]:
    """Pick static paired events like the measurement research, plus every predicted or known automatic wrap."""
    originals: list[SSAEvent] = metrics.dialogue(source)
    targets: list[SSAEvent] = metrics.dialogue(output)
    verdicts: dict[str, Category] = metrics.style_verdicts(source)
    seen: set[tuple[str, str]] = set()
    chosen: dict[str, list[tuple[SSAEvent, SSAEvent]]] = {"sign": [], "dialogue": []}
    for left, right in metrics.pair_events(originals, targets):
        original, target = originals[left], targets[right]
        key: tuple[str, str] = (original.style, original.text)
        if key in seen:
            continue
        seen.add(key)
        if is_static(original, source) and is_static(target, output):
            chosen["dialogue" if verdicts.get(original.style) is Category.DIALOG else "sign"].append((original, target))
    picked: list[tuple[str, tuple[SSAEvent, SSAEvent]]] = [
        *(("sign", events) for events in spaced(chosen["sign"], MAX_SIGNS)),
        *(("dialogue", events) for events in spaced(chosen["dialogue"], MAX_DIALOGUE)),
    ]
    taken: set[int] = {id(events) for _, events in picked}
    picked.extend(
        (kind, events)
        for kind, candidates in chosen.items()
        for events in candidates
        if id(events) not in taken and _wanted(pair, events, profiles)
    )
    return [
        Sample(pair, lang, kind, "static", event)
        for kind, events in picked
        for lang, event in zip(("en", "pl"), events, strict=True)
    ]


def controls(samples: Sequence[Sample], profile: RenderProfile) -> list[Sample]:
    """Return a no-wrap and a narrow-margin copy of every wrapped sample and margin copies of long dialogue."""
    wrapped: list[Sample] = [sample for sample in samples if _wrapped(sample.event, profile)]
    margin: int = round(profile.play_res_x * CONTROL_MARGIN)
    longest: list[Sample] = sorted(
        (sample for sample in samples if sample.kind == "dialogue" and not _wrapped(sample.event, profile)),
        key=lambda sample: -measure_text(sample.event, sample.event.text, profile).width,
    )
    narrowed: list[Sample] = [sample for sample in longest if _wrapped(_with_margins(sample.event, margin), profile)][
        :MAX_MARGIN_CONTROLS
    ]
    no_wrap: list[Sample] = [_control(sample, "no-wrap", _without_wrap(sample.event)) for sample in wrapped]
    margins: list[Sample] = [
        _control(sample, "margins", _with_margins(sample.event, margin)) for sample in (*wrapped, *narrowed)
    ]
    return [*no_wrap, *margins]


def _wanted(pair: str, events: tuple[SSAEvent, SSAEvent], profiles: tuple[RenderProfile, RenderProfile]) -> bool:
    return any(
        _wrapped(event, profile) or is_known_wrap(pair, lang, event.style, visible_text(event.text))
        for lang, event, profile in zip(("en", "pl"), events, profiles, strict=True)
    )


def _wrapped(event: SSAEvent, profile: RenderProfile) -> bool:
    return wrap_text(event, event.text, profile) != event.text


def _control(sample: Sample, case: Case, event: SSAEvent) -> Sample:
    return Sample(sample.pair, sample.lang, sample.kind, case, event)


def _without_wrap(event: SSAEvent) -> SSAEvent:
    copy: SSAEvent = event.copy()
    copy.text = _NO_WRAP + event.text
    return copy


def _with_margins(event: SSAEvent, margin: int) -> SSAEvent:
    copy: SSAEvent = event.copy()
    copy.marginl = copy.marginr = margin
    return copy


# ── Measurement ───────────────────────────────────────────────────────────────


def pair_jobs(pair: str, directory: Path) -> list[Job]:
    """Build the English and Polish render jobs of one pair."""
    source: SSAFile = load_subtitles(directory / SOURCE_NAME)
    output: SSAFile = load_subtitles(directory / OUTPUT_NAME)
    fonts: FontSources = pair_fonts(directory)
    index: FontIndex = FontIndex.build(fonts.episode, fonts.system)
    profiles: tuple[RenderProfile, RenderProfile] = (
        RenderProfile.from_subs(source, index),
        RenderProfile.from_subs(output, index),
    )
    samples: list[Sample] = sample_pair(pair, source, output, profiles)
    jobs: list[Job] = []
    for lang, subs, profile in (("en", source, profiles[0]), ("pl", output, profiles[1])):
        own: list[Sample] = [sample for sample in samples if sample.lang == lang]
        jobs.append(Job(directory, lang, subs, profile, (*own, *controls(own, profile))))
    return jobs


def run_job(job: Job, work_root: Path) -> list[Row]:
    """Render every sample of a job with libass, count its logged line breaks and measure it with the geometry."""
    work: Path = work_dir(work_root, job.directory) / job.lang
    work.mkdir(parents=True, exist_ok=True)
    prepare_fonts(job.directory, None, work)
    size: Size = metrics.play_size(job.subs)
    events: list[SSAEvent] = [sample.event for sample in job.samples]
    boxes, _ = measure_boxes(job.subs, events, size, work, "calibrate")
    breaks: list[int | None] = wrap_breaks(job.subs, events, size, work, "wraps")
    return [
        _row(sample, (box, libass_breaks), job.profile, size)
        for sample, box, libass_breaks in zip(job.samples, boxes, breaks, strict=True)
    ]


def _row(sample: Sample, rendered: tuple[Box | None, int | None], profile: RenderProfile, size: Size) -> Row:
    event: SSAEvent = sample.event
    box, libass_breaks = rendered
    wrapped: TextBox = measure_text(event, wrap_text(event, event.text, profile), profile)
    unwrapped: TextBox = measure_text(event, event.text, profile)
    limit: float = available_width(event, profile)
    rects: tuple[Rect, ...] = screen_rects(event, event.text, profile)
    return Row(
        pair=sample.pair,
        lang=sample.lang,
        kind=sample.kind,
        case=sample.case,
        style=event.style,
        text=visible_text(event.text)[:80],
        status=wrapped.status,
        breaks=len(wrapped.line_widths) - len(unwrapped.line_widths),
        libass_breaks=libass_breaks,
        wrap_slack=min(
            (abs(width - unwrapped.edge - limit) / limit * 100 for width in unwrapped.line_widths if width),
            default=float("inf"),
        ),
        estimate=(rects[0].left, rects[0].top, rects[0].right, rects[0].bottom) if rects else None,
        libass=box,
        clipped=box is not None and _clipped(box, size),
    )


def _clipped(box: Box, size: Size) -> bool:
    dx, dy = round(size[0] * PAD_FRACTION), round(size[1] * PAD_FRACTION)
    return box[0] <= -dx or box[1] <= -dy or box[2] >= size[0] + dx or box[3] >= size[1] + dy


def _error(estimate: tuple[float, float, float, float] | None, box: Box | None, *, horizontal: bool) -> float:
    if estimate is None or box is None:
        return float("inf")
    axis: int = 0 if horizontal else 1
    actual: int = box[axis + 2] - box[axis]
    return abs(estimate[axis + 2] - estimate[axis] - actual) / actual * 100


# ── Summary ───────────────────────────────────────────────────────────────────


def gates(rows: Sequence[Row]) -> list[Gate]:
    """Return every calibration requirement: errors of static samples, libass line breaks and required cases."""
    static: list[Row] = [row for row in rows if row.case == "static" and row.comparable]
    wide: list[float] = [row.width_error for row in static if row.libass_width >= GATE_MIN_WIDTH]
    heights: list[float] = [row.height_error for row in static]
    counts: Counter[Verdict] = Counter(row.verdict for row in rows)
    missing: list[str] = missing_known_wraps(rows)
    present: Counter[Case] = Counter(row.case for row in rows)
    return [
        _percentile_gate(f"width p90, static samples >= {GATE_MIN_WIDTH} px", wide, 0.9, WIDTH_P90_LIMIT),
        _percentile_gate(f"width p99, static samples >= {GATE_MIN_WIDTH} px", wide, 0.99, WIDTH_P99_LIMIT),
        _percentile_gate("height p90, static samples", heights, 0.9, HEIGHT_P90_LIMIT),
        Gate(
            f"line breaks equal to libass on every sample: agree {counts['agree']} of {len(rows)}, "
            f"disagree {counts['disagree']}, unresolved {counts['unresolved']}",
            bool(rows) and counts["agree"] == len(rows),
        ),
        Gate(f"known automatic wraps covered and agreeing, missing or failing: {missing or 'none'}", not missing),
        Gate(
            f"wrap controls present: no-wrap {present['no-wrap']}, margins {present['margins']}",
            present["no-wrap"] > 0 and present["margins"] > 0,
        ),
    ]


def missing_known_wraps(rows: Sequence[Row]) -> list[str]:
    """Return the known wraps of the calibrated pairs that are absent, not wrapped by libass or not agreeing."""
    pairs: set[str] = {row.pair for row in rows}
    missing: list[str] = []
    for pair, lang, style, prefix in KNOWN_WRAPS:
        found: list[Row] = [
            row
            for row in rows
            if row.case == "static"
            and (row.pair, row.lang, row.style) == (pair, lang, style)
            and row.text.startswith(prefix)
        ]
        if pair in pairs and not any(row.verdict == "agree" and row.libass_breaks for row in found):
            missing.append(f"{pair} {lang} {style}")
    return missing


def summary(rows: Sequence[Row], elapsed: dict[str, float]) -> str:
    """Return the calibration report: groups, percentiles, gates, line breaks and timing."""
    comparable: list[Row] = [row for row in rows if row.comparable]
    static: list[Row] = [row for row in comparable if row.case == "static"]
    groups: dict[str, list[Row]] = {
        "static (gate)": static,
        f"static >= {GATE_MIN_WIDTH} px (gate)": [row for row in static if row.libass_width >= GATE_MIN_WIDTH],
        "diagnostic: static exact, unwrapped": [row for row in static if row.status == "exact" and not row.breaks],
        "diagnostic: static approximate": [row for row in static if row.status != "exact"],
        "diagnostic: static wrapped": [row for row in static if row.breaks or row.libass_breaks],
        "diagnostic: control no-wrap": [row for row in comparable if row.case == "no-wrap"],
        "diagnostic: control margins": [row for row in comparable if row.case == "margins"],
    }
    lines: list[str] = [
        f"samples {len(rows)}  comparable {len(comparable)}  "
        f"pairs {len({row.pair for row in rows})}  clipped {sum(row.clipped for row in rows)}",
        "",
        "group | n | width p50/p90/p99 % | height p50/p90/p99 %",
        *(_group_line(name, group) for name, group in groups.items()),
        "",
        "gates:",
        *(f"  {'OK  ' if gate.passed else 'FAIL'} {gate.name}" for gate in gates(rows)),
        "",
        "line breaks against the libass log, by case:",
    ]
    for case in ("static", "no-wrap", "margins"):
        counts: Counter[Verdict] = Counter(row.verdict for row in rows if row.case == case)
        lines.append(f"  {case}: " + ", ".join(f"{verdict} {counts[verdict]}" for verdict in VERDICTS))
    lines.extend(["", "samples whose line breaks differ from libass or could not be read:"])
    lines.extend(_wrap_line(row) for row in rows if row.verdict != "agree")
    lines.extend(["", "known automatic wraps:"])
    lines.extend(_wrap_line(row) for row in rows if row.case == "static" and _known(row))
    lines.extend(["", "automatic wraps in the corpus samples:"])
    lines.extend(_wrap_line(row) for row in rows if row.case == "static" and (row.breaks or row.libass_breaks))
    lines.extend(["", "timing: " + ", ".join(f"{name} {seconds:.1f} s" for name, seconds in elapsed.items())])
    return "\n".join(lines)


def _known(row: Row) -> bool:
    return is_known_wrap(row.pair, row.lang, row.style, row.text)


def _percentile_gate(name: str, errors: Sequence[float], share: float, limit: float) -> Gate:
    value: float = metrics.percentile(errors, share)
    return Gate(f"{name}: {value:.2f}% <= {limit}% (n={len(errors)})", bool(errors) and value <= limit)


def _wrap_line(row: Row) -> str:
    return (
        f"  {row.verdict:10} {row.case:8} {row.pair[:48]} {row.lang} {row.style}: breaks {row.breaks} vs libass "
        f"{row.libass_breaks}, width {row.width_error:.1f}%, slack {row.wrap_slack:.2f}%  {row.text[:40]}"
    )


def _group_line(name: str, rows: Sequence[Row]) -> str:
    widths: list[float] = [row.width_error for row in rows]
    heights: list[float] = [row.height_error for row in rows]
    width: str = "/".join(f"{metrics.percentile(widths, share):.2f}" for share in PERCENTILES)
    height: str = "/".join(f"{metrics.percentile(heights, share):.2f}" for share in PERCENTILES)
    return f"{name} | {len(rows)} | {width} | {height}"


# ── Command line ──────────────────────────────────────────────────────────────


def calibrate(roots: Sequence[Path], out: Path, jobs: int) -> tuple[list[Row], str]:
    """Sample, render and measure every pair under the roots; write the rows and the summary into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    started: float = time.perf_counter()
    work: list[Job] = [
        job
        for pair, directory in pair_dirs(roots)
        if (directory / OUTPUT_NAME).is_file() and (directory / FONTS_NAME).is_dir()
        for job in pair_jobs(pair, directory)
    ]
    sampled: float = time.perf_counter()
    with ThreadPoolExecutor(max(1, jobs)) as pool:
        rows: list[Row] = [
            row for job_rows in pool.map(lambda job: run_job(job, out / "work"), work) for row in job_rows
        ]
    elapsed: dict[str, float] = {"sampling": sampled - started, "render and measure": time.perf_counter() - sampled}
    report: str = summary(rows, elapsed)
    (out / ROWS_NAME).write_text(json.dumps([asdict(row) for row in rows], ensure_ascii=False), encoding="utf-8")
    (out / SUMMARY_NAME).write_text(report + "\n", encoding="utf-8")
    return rows, report


def main(argv: Sequence[str], quality_root: Path) -> int:
    """Run the calibration and print its summary; return 1 when any gate fails."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality calibrate",
        description=(
            "Render static paired events of every pair folder with libass and compare their boxes with the layout "
            "measurement, and compare the automatic line breaks libass logs for every sample, the no-wrap and "
            "margin controls and the known wraps of the research with the ones the layout predicts."
        ),
    )
    parser.add_argument("roots", nargs="*", type=Path, help="pair folders or roots searched recursively")
    parser.add_argument("--out", type=Path, default=quality_root / "experiments" / "calibrate", help="report folder")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="libass renders at once")
    args: argparse.Namespace = parser.parse_args(argv)
    setup_mode(LoggerMode.SILENT, file=FileConfig(enable=False))
    roots: list[Path] = list(args.roots) or [quality_root / folder for folder in REPLAY_ROOTS]
    rows, report = calibrate(roots, args.out, args.jobs)
    print(report)
    print(f"report {args.out / SUMMARY_NAME}", file=sys.stderr)
    return 0 if all(gate.passed for gate in gates(rows)) else 1
