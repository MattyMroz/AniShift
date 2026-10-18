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
from scripts.subtitle_quality.render import PAD_FRACTION, measure_boxes, prepare_fonts
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

WRAP_BORDERLINE: Final[float] = 1.0
"""Distance in percent between a line's ink and the wrap limit within which the measurement cannot decide."""

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

_NO_WRAP: Final[str] = r"{\q2}"
"""Override block prepended to a no-wrap control."""

_RE_DYNAMIC: Final[re.Pattern[str]] = re.compile(
    r"\\(?:move|t\(|org|frz?-?[0-9.]|frx|fry|fax|fay|p[1-9]|k[fo]?[0-9]|K[0-9]|fade\(|fs[+-]|fn@|q[13]|fe)"
)
"""Tags that move, rotate, animate, draw, time or re-encode an event, so it is not static."""

_RE_FADE: Final[re.Pattern[str]] = re.compile(r"\\fad\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)")
"""Simple fade whose in or out time may keep the event translucent at its midpoint."""

VERDICTS: Final[tuple[str, ...]] = ("agree", "borderline", "disagree")
"""Outcomes of comparing a line count after wrapping with libass."""

type Case = str
"""Sample case: ``static`` for corpus events, ``no-wrap`` and ``margins`` for the controls."""

type Verdict = str
"""Line count outcome, one of ``VERDICTS``."""


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
    """Measured and libass-rendered extent of one sample in script pixels."""

    pair: str
    lang: str
    kind: str
    case: Case
    style: str
    text: str
    status: str
    lines: int
    wrapped: bool
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
    def libass_lines(self) -> int:
        """Return the line count libass drew, read from how far its height differs from the estimate's."""
        if self.estimate is None or self.libass is None or self.estimate[3] <= self.estimate[1]:
            return self.lines
        height: float = self.estimate[3] - self.estimate[1]
        return self.lines + round((self.libass[3] - self.libass[1] - height) / (height / self.lines))


@dataclass(frozen=True, slots=True)
class Job:
    """Samples of one pair language rendered by one libass run."""

    directory: Path
    lang: str
    subs: SSAFile
    profile: RenderProfile
    samples: tuple[Sample, ...]


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


def sample_pair(
    pair: str, source: SSAFile, output: SSAFile, profiles: tuple[RenderProfile, RenderProfile]
) -> list[Sample]:
    """Pick static paired events like the measurement research, plus every pair the layout wraps automatically."""
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
        if id(events) not in taken and _wraps(events, profiles)
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


def _wraps(events: tuple[SSAEvent, SSAEvent], profiles: tuple[RenderProfile, RenderProfile]) -> bool:
    return any(_wrapped(event, profile) for event, profile in zip(events, profiles, strict=True))


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
    """Render every sample of a job with libass and measure it with the layout geometry."""
    work: Path = work_dir(work_root, job.directory) / job.lang
    work.mkdir(parents=True, exist_ok=True)
    prepare_fonts(job.directory, None, work)
    size: Size = metrics.play_size(job.subs)
    boxes, _ = measure_boxes(job.subs, [sample.event for sample in job.samples], size, work, "calibrate")
    return [_row(sample, box, job.profile, size) for sample, box in zip(job.samples, boxes, strict=True)]


def _row(sample: Sample, box: Box | None, profile: RenderProfile, size: Size) -> Row:
    event: SSAEvent = sample.event
    wrapped: str = wrap_text(event, event.text, profile)
    measured: TextBox = measure_text(event, wrapped, profile)
    unwrapped: TextBox = measure_text(event, event.text, profile)
    limit: float = available_width(event, profile)
    rects: tuple[Rect, ...] = screen_rects(event, event.text, profile)
    estimate: tuple[float, float, float, float] | None = None
    if rects:
        estimate = (rects[0].left, rects[0].top, rects[0].right, rects[0].bottom)
    return Row(
        pair=sample.pair,
        lang=sample.lang,
        kind=sample.kind,
        case=sample.case,
        style=event.style,
        text=visible_text(event.text)[:80],
        status=measured.status,
        lines=max(1, len(measured.line_widths)),
        wrapped=wrapped != event.text,
        wrap_slack=min(
            (abs(width - unwrapped.edge - limit) / limit * 100 for width in unwrapped.line_widths if width),
            default=float("inf"),
        ),
        estimate=estimate,
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


@dataclass(frozen=True, slots=True)
class Gate:
    """One calibration threshold with the measured value."""

    name: str
    value: float
    limit: float

    @property
    def passed(self) -> bool:
        """Tell whether the measured value stays within the limit."""
        return self.value <= self.limit


def gates(rows: Sequence[Row]) -> list[Gate]:
    """Return the width and height gates over exact, unwrapped static samples."""
    exact: list[Row] = [row for row in rows if _gated(row)]
    wide: list[float] = [row.width_error for row in exact if row.libass_width >= GATE_MIN_WIDTH]
    heights: list[float] = [row.height_error for row in exact]
    return [
        Gate(
            f"width p90 (static exact >= {GATE_MIN_WIDTH} px, n={len(wide)})",
            metrics.percentile(wide, 0.9),
            WIDTH_P90_LIMIT,
        ),
        Gate(
            f"width p99 (static exact >= {GATE_MIN_WIDTH} px, n={len(wide)})",
            metrics.percentile(wide, 0.99),
            WIDTH_P99_LIMIT,
        ),
        Gate(f"height p90 (static exact, n={len(heights)})", metrics.percentile(heights, 0.9), HEIGHT_P90_LIMIT),
    ]


def wrap_verdicts(rows: Sequence[Row]) -> list[tuple[Row, Verdict]]:
    """Return every comparable wrapped or control sample with how its line count compares with libass."""
    checked: list[Row] = [row for row in rows if row.comparable and (row.wrapped or row.case != "static")]
    return [(row, _verdict(row)) for row in checked]


def wraps_pass(rows: Sequence[Row]) -> bool:
    """Tell whether every line count matches libass or differs only for a line at the wrap limit."""
    return all(verdict != "disagree" for _, verdict in wrap_verdicts(rows))


def _verdict(row: Row) -> Verdict:
    if row.libass_lines == row.lines:
        return "agree"
    return "borderline" if row.wrap_slack <= WRAP_BORDERLINE else "disagree"


def summary(rows: Sequence[Row], elapsed: dict[str, float]) -> str:
    """Return the calibration report: groups, percentiles, gates, wrap agreement and timing."""
    comparable: list[Row] = [row for row in rows if row.comparable]
    groups: dict[str, list[Row]] = {
        "static exact, unwrapped": [row for row in comparable if _gated(row)],
        f"static exact, unwrapped, >= {GATE_MIN_WIDTH} px": [
            row for row in comparable if _gated(row) and row.libass_width >= GATE_MIN_WIDTH
        ],
        "static approximate (substitute face, kerning, outline scale)": [
            row for row in comparable if row.case == "static" and row.status != "exact" and not row.wrapped
        ],
        "static wrapped": [row for row in comparable if row.case == "static" and row.wrapped],
        "control no-wrap": [row for row in comparable if row.case == "no-wrap"],
        "control margins": [row for row in comparable if row.case == "margins"],
    }
    lines: list[str] = [
        f"samples {len(rows)}  comparable {len(comparable)}  "
        f"pairs {len({row.pair for row in rows})}  clipped {sum(row.clipped for row in rows)}",
        "",
        "group | n | width p50/p90/p99 % | height p50/p90/p99 %",
    ]
    lines.extend(_group_line(name, group) for name, group in groups.items())
    lines.extend(["", "gates:"])
    lines.extend(
        f"  {'OK  ' if gate.passed else 'FAIL'} {gate.name}: {gate.value:.2f} <= {gate.limit}" for gate in gates(rows)
    )
    verdicts: list[tuple[Row, Verdict]] = wrap_verdicts(rows)
    lines.extend(["", f"line count after wrapping ({'OK' if wraps_pass(rows) else 'FAIL'}):"])
    for case in ("static", "no-wrap", "margins"):
        counts: Counter[Verdict] = Counter(verdict for row, verdict in verdicts if row.case == case)
        lines.append(f"  {case}: " + ", ".join(f"{verdict} {counts[verdict]}" for verdict in VERDICTS))
    lines.extend(["", f"line counts that differ (borderline: ink within {WRAP_BORDERLINE}% of the wrap limit):"])
    lines.extend(_wrap_line(row, verdict) for row, verdict in verdicts if verdict != "agree")
    lines.extend(["", "automatic wraps in the corpus:"])
    lines.extend(_wrap_line(row, verdict) for row, verdict in verdicts if row.case == "static")
    lines.extend(["", "timing: " + ", ".join(f"{name} {seconds:.1f} s" for name, seconds in elapsed.items())])
    return "\n".join(lines)


def _wrap_line(row: Row, verdict: Verdict) -> str:
    return (
        f"  {verdict:10} {row.case:8} {row.pair[:48]} {row.lang} {row.style}: {row.lines} vs libass "
        f"{row.libass_lines}, width {row.width_error:.1f}%, slack {row.wrap_slack:.2f}%  {row.text[:40]}"
    )


def _gated(row: Row) -> bool:
    return row.comparable and row.case == "static" and row.status == "exact" and not row.wrapped


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
    """Run the calibration and print its summary; return 1 when a gate or a wrap line count fails."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality calibrate",
        description=(
            "Render static paired events of every pair folder with libass and compare their boxes with the layout "
            "measurement: width and height errors, gates, and line counts of automatic wrapping with no-wrap and "
            "margin controls."
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
    failed: bool = any(not gate.passed for gate in gates(rows)) or not wraps_pass(rows)
    print(f"report {args.out / SUMMARY_NAME}", file=sys.stderr)
    return 1 if failed else 0
