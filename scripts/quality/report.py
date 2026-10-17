"""Write quality metrics as JSON, CSV, a text table and gallery indexes."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Final

from scripts.quality import metrics
from scripts.quality.episode import PAIRING_MIN

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from scripts.quality.episode import EpisodeResult

# ── Constants ─────────────────────────────────────────────────────────────────

NAME_WIDTH: Final[int] = 40
"""Episode name width in the text table."""

CSV_FIELDS: Final[tuple[str, ...]] = (
    "episode",
    "index",
    "start",
    "end",
    "duration_ms",
    "style",
    "actor",
    "verdict",
    "positioned",
    "alignment",
    "top",
    "chars",
    "overlaps",
    "flags",
    "label",
)
"""Columns of the dialogue and sign split sheet; ``label`` is left for the owner."""

STALE_NOTE: Final[str] = f"pairing below {PAIRING_MIN:.0%}"
"""Legend explaining when an output counts as stale."""


def summarise(results: Sequence[EpisodeResult]) -> dict[str, object]:
    """Summarise every metric over the given episodes pooled together, skipping stale outputs."""
    with_output: list[EpisodeResult] = [result for result in results if result.has_output]
    compared: list[EpisodeResult] = [result for result in with_output if not result.stale]
    return {
        "episodes": len(results),
        "compared": len(compared),
        "stale": [result.name for result in with_output if result.stale],
        "pairing": {
            "source_events": sum(result.source_events for result in with_output),
            "output_events": sum(result.output_events for result in with_output),
            "paired": sum(result.paired for result in with_output),
        },
        "signs": metrics.summarise_signs([finding for result in compared for finding in result.signs]),
        "split": metrics.summarise_flags([row for result in results for row in result.rows]),
        "styles": metrics.summarise_styles([check for result in compared for check in result.styles]),
        "comparison": _comparison(compared),
        "source_only": {
            "episodes": len(results),
            "breaks": metrics.summarise_breaks([check for result in results for check in result.source_breaks]),
            "timing": metrics.summarise_cps([value for result in results for value in result.source_cps]),
        },
    }


def _comparison(compared: Sequence[EpisodeResult]) -> dict[str, object]:
    return {
        "episodes": len(compared),
        "events": sum(len(result.common_source_breaks) for result in compared),
        "empty_output": sum(result.empty_output for result in compared),
        "breaks": {
            "source": metrics.summarise_breaks([check for result in compared for check in result.common_source_breaks]),
            "output": metrics.summarise_breaks([check for result in compared for check in result.common_output_breaks]),
        },
        "timing": {
            "source": metrics.summarise_cps([value for result in compared for value in result.common_source_cps]),
            "output": metrics.summarise_cps([value for result in compared for value in result.common_output_cps]),
            "length_ratio": metrics.distribution([value for result in compared for value in result.length_ratios]),
        },
    }


def episode_payload(result: EpisodeResult) -> dict[str, object]:
    """Return the JSON payload of one episode, including per-sign findings."""
    return {
        "play_res": list(result.size),
        "video": result.video is not None,
        "fonts": result.fonts,
        "summary": summarise([result]),
        "font_reports": {name: asdict(report) for name, report in result.font_reports.items()},
        "signs": [_sign_payload(finding) for finding in result.signs],
    }


def _sign_payload(finding: metrics.SignFinding) -> dict[str, object]:
    payload: dict[str, object] = asdict(finding.sign)
    payload.update(
        length_ratio=round(finding.length_ratio, 2),
        width_ratio=None if finding.width_ratio is None else round(finding.width_ratio, 2),
        overflow_px=finding.overflow_px,
        new_offscreen_px=finding.new_offscreen_px,
        new_overlaps=finding.new_overlaps,
        offscreen_measured=finding.offscreen_measured,
        overlap_measured=finding.overlap_measured,
        source_visible=finding.sign.source_visible,
        output_visible=finding.sign.output_visible,
        badness=round(finding.badness, 3),
    )
    return payload


def write_json(results: Sequence[EpisodeResult], path: Path) -> None:
    """Write pooled and per-episode metrics to one JSON file."""
    payload: dict[str, object] = {
        "thresholds": {
            "max_line_chars": metrics.MAX_LINE_CHARS,
            "max_lines": metrics.MAX_LINES,
            "orphan_words": sorted(metrics.ORPHAN_WORDS),
            "cps_limits": list(metrics.CPS_LIMITS),
            "width_tolerance": metrics.WIDTH_TOLERANCE,
        },
        "overall": summarise(results),
        "episodes": {result.name: episode_payload(result) for result in results},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_split_csv(results: Sequence[EpisodeResult], path: Path) -> None:
    """Write one feature row per source line for manual dialogue and sign labelling."""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer: csv.DictWriter[str] = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for result in results:
            writer.writerows(_csv_row(result.name, row) for row in result.rows)


def _csv_row(episode: str, row: metrics.ClassificationRow) -> dict[str, object]:
    return {
        "episode": episode,
        "index": row.index,
        "start": format_time(row.start),
        "end": format_time(row.end),
        "duration_ms": row.end - row.start,
        "style": row.style,
        "actor": row.actor,
        "verdict": row.verdict,
        "positioned": int(row.positioned),
        "alignment": row.alignment,
        "top": int(row.top),
        "chars": row.chars,
        "overlaps": row.overlaps,
        "flags": "|".join(row.flags),
        "label": "",
    }


def format_time(milliseconds: int) -> str:
    """Format milliseconds as ``H:MM:SS.cc``."""
    seconds, millis = divmod(max(0, milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis // 10:02d}"


def table(results: Sequence[EpisodeResult]) -> str:
    """Return a short fixed-width table of the main metrics per episode and overall."""
    header: str = (
        f"{'episode':<{NAME_WIDTH}} {'pair%':>5} {'signs':>5} {'wide':>4} {'off':>4} {'ovl':>4} {'ovl?':>4} "
        f"{'tags':>4} {'empt':>4} {'wspl':>4} {'add':>4} {'>42':>4} {'orph':>4} {'>2L':>4} "
        f"{'cps90':>11} {'>17cps':>11} {'flags':>5}"
    )
    lines: list[str] = [header, "-" * len(header)]
    lines.extend(_table_row(result.name, summarise([result])) for result in results)
    lines.append("-" * len(header))
    lines.append(_table_row("OVERALL", summarise(results)))
    lines.append(f"* stale output made from another source release; output metrics skipped ({STALE_NOTE})")
    lines.append(
        "cps90, >17cps: EN/PL on the same paired dialogue lines of non-stale outputs; "
        ">42, orph, >2L: PL on those lines; ovl: new overlaps of static signs; ovl?: signs with unmeasured overlaps; "
        "empt: emptied tag spans; wspl: style tag split inside a word; add: style tags added to an untagged line"
    )
    return "\n".join(lines)


def _value(summary: dict[str, object], *keys: str) -> object:
    current: object = summary
    for key in keys:
        if not isinstance(current, dict):
            return "-"
        current = current.get(key, "-")
    return current


def _table_row(name: str, summary: dict[str, object]) -> str:
    source_events: object = _value(summary, "pairing", "source_events")
    paired: object = _value(summary, "pairing", "paired")
    pair_share: str = "-"
    if isinstance(source_events, int) and isinstance(paired, int) and source_events:
        pair_share = f"{100 * paired / source_events:.0f}"
    if _value(summary, "stale") and _value(summary, "episodes") == 1:
        pair_share += "*"
    timing: tuple[str, ...] = ("comparison", "timing")
    cps: str = f"{_value(summary, *timing, 'source', 'p90')}/{_value(summary, *timing, 'output', 'p90')}"
    over: str = f"{_value(summary, *timing, 'source', 'over_17')}/{_value(summary, *timing, 'output', 'over_17')}"
    if not _value(summary, "comparison", "events"):
        cps = over = "-"
    cells: tuple[object, ...] = (
        _value(summary, "signs", "signs"),
        _value(summary, "signs", "wider_than_source"),
        _value(summary, "signs", "new_offscreen"),
        _value(summary, "signs", "new_overlaps"),
        _value(summary, "signs", "overlap_unmeasured"),
        _value(summary, "styles", "tag_sequence_changed"),
        _value(summary, "styles", "emptied_span_events"),
        _value(summary, "styles", "split_word_events"),
        _value(summary, "styles", "added_style_events"),
        _value(summary, "comparison", "breaks", "output", "long_line_events"),
        _value(summary, "comparison", "breaks", "output", "orphan_events"),
        _value(summary, "comparison", "breaks", "output", "over_max_lines"),
    )
    counts: str = f"{cells[0]!s:>5} " + " ".join(f"{cell!s:>4}" for cell in cells[1:])
    flagged: object = _value(summary, "split", "flagged")
    return f"{name[:NAME_WIDTH]:<{NAME_WIDTH}} {pair_share:>5} {counts} {cps:>11} {over:>11} {flagged!s:>5}"


def write_index(path: Path, title: str, entries: Sequence[tuple[str, str, str, str]]) -> None:
    """Write a Markdown gallery index of ``(episode, time, value, file)`` entries."""
    lines: list[str] = [f"# {title}", "", "| # | Odcinek | Czas | Wartość | Plik |", "| --- | --- | --- | --- | --- |"]
    lines.extend(
        f"| {number} | {episode} | {time} | {value} | [{file}]({file}) |"
        for number, (episode, time, value, file) in enumerate(entries, start=1)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
