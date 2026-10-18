"""Load one quality episode folder and compute all of its metrics."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final

from anishift.paths import repo_root
from anishift.services.subtitles.service import load_subtitles
from scripts.quality import metrics
from scripts.quality.render import FontReport, event_fonts, measure_boxes, prepare_fonts

if TYPE_CHECKING:
    from pathlib import Path

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.subtitles.classifier import Category

# ── Constants ─────────────────────────────────────────────────────────────────

SOURCE_NAME: Final[str] = "source.en.ass"
"""English source subtitle file inside an episode folder."""

OUTPUT_NAME: Final[str] = "output.pl.ass"
"""Optional Polish AniShift output inside an episode folder."""

VIDEO_NAME: Final[str] = "video.txt"
"""Optional file naming the episode video, relative to the repository root."""

FRAMES_NAME: Final[str] = "frames"
"""Optional folder of ``<ms>.jpg`` video frames used as gallery backgrounds instead of the video."""

PAIRING_MIN: Final[float] = 0.9
"""Share of source events that must pair with the output for it to count as made from this source."""

_SLUG_LENGTH: Final[int] = 60
"""Longest readable part of a work-folder name."""

_RE_UNSAFE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")
"""Characters replaced in work-folder names so FFmpeg filters need no escaping."""


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    """Every metric of one episode, kept raw so episodes can be pooled."""

    name: str
    directory: Path
    video: Path | None
    work: Path
    size: metrics.Size
    source_events: int
    output_events: int
    paired: int
    fonts: int
    signs: list[metrics.SignFinding] = field(default_factory=list)
    rows: list[metrics.ClassificationRow] = field(default_factory=list)
    styles: list[metrics.StyleCheck] = field(default_factory=list)
    source_breaks: list[metrics.BreakCheck] = field(default_factory=list)
    source_cps: list[float] = field(default_factory=list)
    output_breaks: list[metrics.BreakCheck] = field(default_factory=list)
    common_source_breaks: list[metrics.BreakCheck] = field(default_factory=list)
    common_output_breaks: list[metrics.BreakCheck] = field(default_factory=list)
    common_source_cps: list[float] = field(default_factory=list)
    common_output_cps: list[float] = field(default_factory=list)
    length_ratios: list[float] = field(default_factory=list)
    empty_output: int = 0
    font_reports: dict[str, FontReport] = field(default_factory=dict)

    @property
    def has_output(self) -> bool:
        """Tell whether the episode has a Polish output to compare."""
        return self.output_events > 0

    @property
    def stale(self) -> bool:
        """Tell whether the output was evidently made from another source release."""
        return self.has_output and self.paired < PAIRING_MIN * self.source_events


def episode_dirs(roots: list[Path]) -> list[Path]:
    """Return every folder holding a source subtitle under the given roots."""
    found: set[Path] = set()
    for root in roots:
        found.update(path.parent for path in root.rglob(SOURCE_NAME))
    return sorted(found)


def work_dir(cache: Path, directory: Path) -> Path:
    """Return a filter-safe cache folder for one episode."""
    digest: str = hashlib.sha1(directory.name.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    slug: str = _RE_UNSAFE.sub("_", directory.name).strip("_")[:_SLUG_LENGTH]
    return cache / f"{slug}-{digest}"


def video_path(directory: Path) -> Path | None:
    """Return the video named by ``video.txt``, or None when absent or missing."""
    pointer: Path = directory / VIDEO_NAME
    if not pointer.is_file():
        return None
    video: Path = repo_root() / pointer.read_text(encoding="utf-8").strip()
    return video if video.is_file() else None


def analyse(directory: Path, cache: Path, *, render: bool) -> EpisodeResult:
    """Compute all metrics for one episode folder, rendering signs when asked."""
    source: SSAFile = load_subtitles(directory / SOURCE_NAME)
    output_path: Path = directory / OUTPUT_NAME
    output: SSAFile | None = load_subtitles(output_path) if output_path.is_file() else None
    work: Path = work_dir(cache, directory)
    work.mkdir(parents=True, exist_ok=True)
    video: Path | None = video_path(directory)
    fonts: int = prepare_fonts(directory, video, work) if render else 0
    source_events: list[SSAEvent] = metrics.dialogue(source)
    source_verdicts: dict[str, Category] = metrics.style_verdicts(source)
    result: EpisodeResult = EpisodeResult(
        name=directory.name,
        directory=directory,
        video=video,
        work=work,
        size=metrics.play_size(source),
        source_events=len(source_events),
        output_events=0,
        paired=0,
        fonts=fonts,
        rows=metrics.classification_rows(source, source_verdicts),
        source_breaks=metrics.break_checks(source_events, source_verdicts),
        source_cps=metrics.cps_values(source_events, source_verdicts),
    )
    if output is None:
        return result
    return _compare(result, source, output, source_verdicts, render=render)


def _compare(
    result: EpisodeResult,
    source: SSAFile,
    output: SSAFile,
    source_verdicts: dict[str, Category],
    *,
    render: bool,
) -> EpisodeResult:
    source_events: list[SSAEvent] = metrics.dialogue(source)
    output_events: list[SSAEvent] = metrics.dialogue(output)
    output_verdicts: dict[str, Category] = metrics.style_verdicts(output)
    pairs: list[tuple[int, int]] = metrics.pair_events(source_events, output_events)
    common, empty_output = metrics.common_dialogue(source_events, output_events, pairs, source_verdicts)
    common_source: list[SSAEvent] = [source_events[source_index] for source_index, _ in common]
    common_output: list[SSAEvent] = [output_events[output_index] for _, output_index in common]
    signs: list[metrics.Sign] = metrics.select_signs(source_events, output_events, pairs, source_verdicts)
    reports: dict[str, FontReport] = {}
    if render:
        signs, reports = _render_signs(signs, source, output, result)
    return replace(
        result,
        output_events=len(output_events),
        paired=len(pairs),
        signs=metrics.sign_findings(signs, result.size),
        styles=metrics.style_checks(source_events, output_events, pairs),
        output_breaks=metrics.break_checks(output_events, output_verdicts),
        common_source_breaks=[metrics.break_check(index, source_events[index]) for index, _ in common],
        common_output_breaks=[metrics.break_check(index, output_events[index]) for _, index in common],
        common_source_cps=metrics.cps_values(common_source, source_verdicts),
        common_output_cps=metrics.cps_values(common_output, source_verdicts),
        length_ratios=metrics.length_ratios(source_events, output_events, common),
        empty_output=empty_output,
        font_reports=reports,
    )


def _render_signs(
    signs: list[metrics.Sign],
    source: SSAFile,
    output: SSAFile,
    result: EpisodeResult,
) -> tuple[list[metrics.Sign], dict[str, FontReport]]:
    source_events: list[SSAEvent] = metrics.dialogue(source)
    output_events: list[SSAEvent] = metrics.dialogue(output)
    chosen_source: list[SSAEvent] = [source_events[sign.source_index] for sign in signs]
    chosen_output: list[SSAEvent] = [output_events[sign.output_index] for sign in signs]
    source_boxes, source_report = measure_boxes(source, chosen_source, result.size, result.work, "measure-source")
    output_boxes, output_report = measure_boxes(output, chosen_output, result.size, result.work, "measure-output")
    measured: list[metrics.Sign] = [
        replace(
            sign,
            source_box=source_box,
            output_box=output_box,
            font_fallback=source_report.affects(event_fonts(source, source_event))
            or output_report.affects(event_fonts(output, output_event)),
        )
        for sign, source_box, output_box, source_event, output_event in zip(
            signs, source_boxes, output_boxes, chosen_source, chosen_output, strict=True
        )
    ]
    return measured, {"source": source_report, "output": output_report}
