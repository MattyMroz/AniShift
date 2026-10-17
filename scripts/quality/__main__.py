"""Command line: measure subtitle quality and render a gallery of the worst cases."""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final

from anishift.paths import default_workspace_dir
from anishift.utils.logger import LoggerMode, setup_mode
from anishift.utils.logger.config import FileConfig
from scripts.quality import report
from scripts.quality.episode import OUTPUT_NAME, SOURCE_NAME, EpisodeResult, analyse, episode_dirs
from scripts.quality.render import Shot, copy_scripts, render_shot

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.quality import metrics

# ── Constants ─────────────────────────────────────────────────────────────────

QUALITY_ROOT: Final[Path] = default_workspace_dir() / ".quality"
"""Root of the quality corpus, reports, gallery and cache."""

DEFAULT_ROOTS: Final[tuple[Path, ...]] = (QUALITY_ROOT / "library", QUALITY_ROOT / "corpus")
"""Episode roots measured when none are given."""

GALLERY_SIZE: Final[int] = 20
"""Worst cases rendered per gallery metric."""

SIGNS_GALLERY: Final[str] = "signs"
"""Gallery folder of signs that grew, left the screen or overlap."""

BREAKS_GALLERY: Final[str] = "line-breaks"
"""Gallery folder of badly broken Polish dialogue lines."""

type Entry = tuple[str, str, str, str]
"""Gallery index row: episode, time, metric value and image file."""


def main(argv: Sequence[str] | None = None) -> int:
    """Measure every episode folder, write the report and optionally the gallery."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.quality",
        description=(
            "Measure subtitle quality. An episode folder holds source.en.ass and optionally output.pl.ass, "
            "video.txt (video path relative to the repository root) and fonts/."
        ),
    )
    parser.add_argument("roots", nargs="*", type=Path, help="episode folders or roots searched recursively")
    parser.add_argument("--out", type=Path, default=QUALITY_ROOT / "report", help="report folder")
    parser.add_argument("--gallery", type=Path, default=QUALITY_ROOT / "gallery", help="gallery folder")
    parser.add_argument("--gallery-size", type=int, default=GALLERY_SIZE, help="worst cases per metric")
    parser.add_argument("--no-render", action="store_true", help="skip libass rendering and the gallery")
    parser.add_argument("--jobs", type=int, default=os.process_cpu_count() or 1, help="episodes measured at once")
    args: argparse.Namespace = parser.parse_args(argv)
    silence: partial[None] = partial(setup_mode, LoggerMode.SILENT, file=FileConfig(enable=False))
    silence()
    roots: list[Path] = list(args.roots) or [root for root in DEFAULT_ROOTS if root.is_dir()]
    render: bool = not args.no_render
    measure: partial[EpisodeResult] = partial(analyse, cache=QUALITY_ROOT / "cache", render=render)
    results: list[EpisodeResult] = []
    with ProcessPoolExecutor(max(1, args.jobs), initializer=silence) as pool:
        for result in pool.map(measure, episode_dirs(roots)):
            print(f"measured {result.name}", file=sys.stderr)
            results.append(result)
    args.out.mkdir(parents=True, exist_ok=True)
    report.write_json(results, args.out / "metrics.json")
    report.write_split_csv(results, args.out / "split.csv")
    summary: str = report.table(results)
    (args.out / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    if render:
        write_gallery(results, args.gallery, args.gallery_size)
    return 0


def write_gallery(results: Sequence[EpisodeResult], gallery: Path, size: int) -> None:
    """Render the worst sign and line-break cases of current outputs with their Markdown indexes."""
    current: list[EpisodeResult] = [result for result in results if not result.stale]
    signs: list[tuple[EpisodeResult, metrics.SignFinding]] = _worst_signs(current, size)
    breaks: list[tuple[EpisodeResult, metrics.BreakCheck]] = sorted(
        ((result, check) for result in current for check in result.output_breaks if check.badness > 0),
        key=lambda item: -item[1].badness,
    )[:size]
    sign_entries: list[Entry] = []
    _reset(gallery / SIGNS_GALLERY)
    for number, (result, finding) in enumerate(signs, start=1):
        sign: metrics.Sign = finding.sign
        caption: str = (
            f"#{number} width x{finding.width_ratio or 0:.2f}  off-screen {finding.new_offscreen_px}px  "
            f"overlaps {finding.new_overlaps}"
        )
        target: Path = gallery / SIGNS_GALLERY / f"{number:02d}.png"
        shot: Shot = Shot((sign.start + sign.end) // 2, target, caption, sign.source_box, sign.output_box)
        value: str = f"{caption}; „{sign.source_text}” → „{sign.output_text}”"
        sign_entries.append(_shoot(result, shot, value))
    break_entries: list[Entry] = []
    _reset(gallery / BREAKS_GALLERY)
    for number, (result, check) in enumerate(breaks, start=1):
        caption = f"#{number} max {check.max_len} chars  lines {check.lines}  orphans {check.orphans}"
        target = gallery / BREAKS_GALLERY / f"{number:02d}.png"
        value = f"{caption}; „{check.text}”"
        break_entries.append(_shoot(result, Shot((check.start + check.end) // 2, target, caption), value))
    report.write_index(gallery / SIGNS_GALLERY / "index.md", "Szyldy: najgorsze przypadki", sign_entries)
    report.write_index(gallery / BREAKS_GALLERY / "index.md", "Polski podział wierszy: najgorsze", break_entries)


def _worst_signs(results: Sequence[EpisodeResult], size: int) -> list[tuple[EpisodeResult, metrics.SignFinding]]:
    ranked: list[tuple[EpisodeResult, metrics.SignFinding]] = sorted(
        ((result, finding) for result in results for finding in result.signs if finding.badness > 0),
        key=lambda item: -item[1].badness,
    )
    seen: set[tuple[str, str]] = set()
    worst: list[tuple[EpisodeResult, metrics.SignFinding]] = []
    for result, finding in ranked:
        key: tuple[str, str] = (result.name, finding.sign.source_text)
        if key not in seen and len(worst) < size:
            seen.add(key)
            worst.append((result, finding))
    return worst


def _reset(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()


def _shoot(result: EpisodeResult, shot: Shot, value: str) -> Entry:
    print(f"rendering {shot.target.parent.name}/{shot.target.name}", file=sys.stderr)
    output: Path = result.directory / OUTPUT_NAME
    copy_scripts(result.directory / SOURCE_NAME, output if output.is_file() else None, result.work)
    render_shot(shot, result.video, result.size, result.work)
    return result.name, report.format_time(shot.time_ms), value.replace("|", "/"), shot.target.name


if __name__ == "__main__":
    sys.exit(main())
