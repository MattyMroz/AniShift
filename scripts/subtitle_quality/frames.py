"""Extract the video frames a quality gallery can show, so an episode pair works without its video."""

from __future__ import annotations

import argparse
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.service import load_subtitles
from anishift.services.subtitles.text import is_drawing, visible_text
from anishift.utils.logger import LoggerMode, setup_mode
from anishift.utils.logger.config import FileConfig
from scripts.subtitle_quality import metrics
from scripts.subtitle_quality.episode import FRAMES_NAME, OUTPUT_NAME, SOURCE_NAME, episode_dirs, video_path
from scripts.subtitle_quality.render import extract_attachments, run_ffmpeg

if TYPE_CHECKING:
    from collections.abc import Sequence

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_GAP_MS: Final[int] = 500
"""Shortest gap between two extracted moments; closer moments share a frame."""

MAX_WIDTH: Final[int] = 1920
"""Widest extracted frame; smaller videos keep their own width."""

JPEG_QUALITY: Final[int] = 3
"""FFmpeg MJPEG quantiser of extracted frames; lower is better."""

DEFAULT_JOBS: Final[int] = 4
"""Episodes decoded at once by default."""

_DECODE_TIMEOUT_S: Final[int] = 3600
"""Upper bound of decoding one whole episode."""

_FILTER_NAME: Final[str] = "frames.vf"
"""Filter script file holding the frame selection, too long for a command line."""


def moments(directory: Path) -> list[int]:
    """Return the midpoints of the visible source and output events, at least ``MIN_GAP_MS`` apart."""
    midpoints: set[int] = set()
    for path in (directory / SOURCE_NAME, directory / OUTPUT_NAME):
        if path.is_file():
            midpoints.update(
                (event.start + event.end) // 2
                for event in metrics.dialogue(load_subtitles(path))
                if visible_text(event.text) and not is_drawing(event.text)
            )
    kept: list[int] = []
    for moment in sorted(midpoints):
        if not kept or moment - kept[-1] >= MIN_GAP_MS:
            kept.append(moment)
    return kept


def frame_filter(times_ms: Sequence[int]) -> str:
    """Return a filter graph keeping the first frame at or after each moment, scaled to at most ``MAX_WIDTH``."""
    seconds: list[str] = [f"{time_ms / 1000:.3f}" for time_ms in times_ms]
    terms: list[str] = [f"gte(t,{second})*not(gte(prev_t,{second}))" for second in seconds]
    return f"select='{_any_of(terms)}',scale='min({MAX_WIDTH},iw)':-2"


def _any_of(terms: Sequence[str]) -> str:
    if len(terms) == 1:
        return terms[0]
    half: int = len(terms) // 2
    return f"({_any_of(terms[:half])}+{_any_of(terms[half:])})"


def extract(directory: Path) -> int:
    """Fill a pair's ``frames/`` from its video, and ``fonts/`` when missing; return the frame count."""
    video: Path | None = video_path(directory)
    target: Path = directory / FRAMES_NAME
    if video is None or target.is_dir():
        return len(list(target.glob("*.jpg")))
    if not (directory / "fonts").is_dir():
        extract_attachments(video, directory)
    times: list[int] = moments(directory)
    if not times:
        return 0
    with TemporaryDirectory() as temp:
        work: Path = Path(temp)
        (work / _FILTER_NAME).write_text(frame_filter(times), encoding="utf-8")
        arguments: list[str] = ["-i", str(video), "-map", "0:v:0", "-/vf", _FILTER_NAME, "-fps_mode", "passthrough"]
        named: list[str] = ["-enc_time_base", "1:1000", "-frame_pts", "1", "-q:v", str(JPEG_QUALITY), "%d.jpg"]
        run_ffmpeg([*arguments, *named], work, timeout_s=_DECODE_TIMEOUT_S)
        target.mkdir()
        frames: list[Path] = list(work.glob("*.jpg"))
        for frame in frames:
            shutil.move(frame, target / frame.name)
    return len(frames)


def main(argv: Sequence[str] | None = None) -> int:
    """Extract gallery frames for every episode pair with a ``video.txt`` under the given roots."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality.frames",
        description=(
            "Save the video frame at every subtitle moment of each episode pair into frames/<ms>.jpg "
            "and its fonts into fonts/, so the gallery and measurement no longer need the video."
        ),
    )
    parser.add_argument("roots", nargs="+", type=Path, help="episode folders or roots searched recursively")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="episodes decoded at once")
    args: argparse.Namespace = parser.parse_args(argv)
    silence: partial[None] = partial(setup_mode, LoggerMode.SILENT, file=FileConfig(enable=False))
    silence()
    directories: list[Path] = episode_dirs(list(args.roots))
    with ThreadPoolExecutor(max(1, args.jobs)) as pool:
        for directory, count in zip(directories, pool.map(extract, directories), strict=True):
            print(f"{count:5d} frames  {directory.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
