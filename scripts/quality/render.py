"""Render subtitle events with FFmpeg and libass to measure and show them."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

from PIL import Image, ImageChops, ImageDraw, ImageFont
from pysubs2 import SSAFile

from anishift.platform.binaries import Binary, require_binary
from anishift.services.composition.fonts import attachment_font_names
from anishift.services.extraction.service import identify
from scripts.quality.metrics import NUMBER

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    from pysubs2 import SSAEvent, SSAStyle

    from scripts.quality.metrics import Box, Size

# ── Constants ─────────────────────────────────────────────────────────────────

PAD_FRACTION: Final[float] = 0.5
"""Canvas margin around the screen, as a share of the script size, to see off-screen text."""

GALLERY_WIDTH: Final[int] = 1280
"""Width of each half of a gallery image in pixels."""

_CAPTION_SIZE: Final[int] = 20
"""Gallery caption font size in pixels."""

_BACKGROUND: Final[tuple[int, int, int]] = (1, 2, 3)
"""Measurement canvas colour unlikely to appear in rendered text."""

_BACKGROUND_PIXEL: Final[bytes] = bytes(_BACKGROUND)
"""Measurement canvas colour as one raw RGB pixel."""

_GALLERY_BACKGROUND: Final[tuple[int, int, int]] = (64, 64, 64)
"""Neutral gallery background when no video is available."""

_SOURCE_COLOUR: Final[str] = "#33ff66"
"""Outline colour of the source sign box."""

_OUTPUT_COLOUR: Final[str] = "#ff3355"
"""Outline colour of the translated sign box."""

_FFMPEG_TIMEOUT_S: Final[int] = 600
"""Upper bound of one FFmpeg run."""

_MKVEXTRACT_OK: Final[frozenset[int]] = frozenset((0, 1))
"""mkvextract exit codes meaning success or success with warnings."""

_NO_WINDOW: Final[int] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
"""Windows flag keeping console children from opening a window."""

_RE_POS: Final[re.Pattern[str]] = re.compile(rf"\\(pos|org)\({NUMBER},{NUMBER}\)")
"""Position or rotation-origin tag with its coordinates."""

_RE_MOVE: Final[re.Pattern[str]] = re.compile(rf"\\move\({NUMBER},{NUMBER},{NUMBER},{NUMBER}")
"""Movement tag with its start and end coordinates."""

_RE_CLIP: Final[re.Pattern[str]] = re.compile(r"\\i?clip\([^)]*\)")
"""Rectangular or vector clip tag, removed to measure the unclipped text."""

_RE_FONTSELECT: Final[re.Pattern[str]] = re.compile(r"fontselect: \((.+?), \d+, \d+\) -> (.+?), \d+, ")
"""libass font selection result: requested family and selected font."""

_RE_MISSING_GLYPH: Final[re.Pattern[str]] = re.compile(r"Glyph 0x([0-9A-Fa-f]+) not found.*?\((.+?), \d+, \d+\)")
"""libass report of a glyph absent from the requested font."""

_RE_INLINE_FONT: Final[re.Pattern[str]] = re.compile(r"\\fn([^\\}]+)")
"""Inline font override."""

_RE_NON_ALNUM: Final[re.Pattern[str]] = re.compile(r"[^0-9a-z]")
"""Characters ignored when comparing font names."""


@dataclass(frozen=True, slots=True)
class FontReport:
    """Fonts libass replaced or could not cover while rendering one file."""

    fallbacks: tuple[str, ...]
    missing_glyphs: dict[str, str]

    def affects(self, fonts: frozenset[str]) -> bool:
        """Tell whether any of the given font families fell back or missed glyphs."""
        replaced: set[str] = {name.split(" -> ")[0].casefold() for name in self.fallbacks}
        replaced.update(name.casefold() for name in self.missing_glyphs)
        return any(font.casefold() in replaced for font in fonts)


# ── Fonts ─────────────────────────────────────────────────────────────────────


def prepare_fonts(episode_dir: Path, video: Path | None, work: Path) -> int:
    """Fill ``work/fonts`` from the episode font folder or the video attachments; return font count."""
    target: Path = work / "fonts"
    if target.is_dir() and any(target.iterdir()):
        return len(list(target.iterdir()))
    local: Path = episode_dir / "fonts"
    if local.is_dir():
        shutil.copytree(local, target, dirs_exist_ok=True)
        return len(list(target.iterdir()))
    if video is None or not video.is_file():
        return 0
    return _extract_attachments(video, work)


def _extract_attachments(video: Path, work: Path) -> int:
    names: tuple[str, ...] = identify(video).attachments
    stems: frozenset[str] = attachment_font_names(names)
    specs: list[str] = [f"{number}:fonts/{name}" for number, name in enumerate(names, start=1) if _stem(name) in stems]
    if not specs:
        return 0
    (work / "fonts").mkdir(parents=True, exist_ok=True)
    completed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - argv built here
        [str(require_binary(Binary.MKVEXTRACT)), "--ui-language", "en", str(video), "attachments", *specs],
        cwd=work,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_FFMPEG_TIMEOUT_S,
        check=False,
        creationflags=_NO_WINDOW,
    )
    if completed.returncode not in _MKVEXTRACT_OK:
        return 0
    return len(specs)


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0].casefold()


def event_fonts(subs: SSAFile, event: SSAEvent) -> frozenset[str]:
    """Return the style font and inline font overrides of one event."""
    names: set[str] = {match.group(1).strip().lstrip("@") for match in _RE_INLINE_FONT.finditer(event.text)}
    if event.style in subs.styles:
        names.add(subs.styles[event.style].fontname.lstrip("@"))
    return frozenset(names)


def parse_font_log(log: str) -> FontReport:
    """Read libass font fallbacks and missing glyphs from a verbose FFmpeg log."""
    fallbacks: set[str] = set()
    for requested, selected in _RE_FONTSELECT.findall(log):
        if not _same_font(requested, selected):
            fallbacks.add(f"{requested} -> {selected}")
    missing: dict[str, set[str]] = {}
    for code, font in _RE_MISSING_GLYPH.findall(log):
        missing.setdefault(font, set()).add(chr(int(code, 16)))
    return FontReport(tuple(sorted(fallbacks)), {font: "".join(sorted(chars)) for font, chars in missing.items()})


def _same_font(requested: str, selected: str) -> bool:
    words: list[str] = requested.split()
    first: str = _RE_NON_ALNUM.sub("", words[0].casefold()) if words else ""
    return bool(first) and first in _RE_NON_ALNUM.sub("", selected.casefold())


# ── Measurement ───────────────────────────────────────────────────────────────


def _padding(size: Size) -> tuple[int, int]:
    return round(size[0] * PAD_FRACTION), round(size[1] * PAD_FRACTION)


def _shift_text(text: str, dx: int, dy: int) -> str:
    def shift_point(match: re.Match[str]) -> str:
        return f"\\{match.group(1)}({float(match.group(2)) + dx:g},{float(match.group(3)) + dy:g})"

    def shift_move(match: re.Match[str]) -> str:
        x1, y1, x2, y2 = (float(match.group(index)) for index in range(1, 5))
        return f"\\move({x1 + dx:g},{y1 + dy:g},{x2 + dx:g},{y2 + dy:g}"

    unclipped: str = _RE_CLIP.sub("", text)
    return _RE_MOVE.sub(shift_move, _RE_POS.sub(shift_point, unclipped))


def measurement_file(subs: SSAFile, events: Sequence[SSAEvent], size: Size) -> tuple[SSAFile, int]:
    """Lay events into isolated time slots on a padded canvas; return the file and slot length in seconds."""
    dx, dy = _padding(size)
    canvas: SSAFile = SSAFile()
    canvas.info = dict(subs.info)
    canvas.info.update(
        {
            "PlayResX": str(size[0] + 2 * dx),
            "PlayResY": str(size[1] + 2 * dy),
            "LayoutResX": str(size[0] + 2 * dx),
            "LayoutResY": str(size[1] + 2 * dy),
        }
    )
    canvas.styles = {name: style.copy() for name, style in subs.styles.items()}
    slot_s: int = max((event.end - event.start for event in events), default=0) // 1000 + 2
    for number, event in enumerate(events, start=1):
        canvas.events.append(_slotted(event, subs, number * slot_s * 1000, dx, dy))
    return canvas, slot_s


def _slotted(event: SSAEvent, subs: SSAFile, sample_ms: int, dx: int, dy: int) -> SSAEvent:
    duration: int = event.end - event.start
    style: SSAStyle | None = subs.styles.get(event.style)
    margin_l: int = event.marginl or (int(style.marginl) if style else 0)
    margin_r: int = event.marginr or (int(style.marginr) if style else 0)
    margin_v: int = event.marginv or (int(style.marginv) if style else 0)
    slotted: SSAEvent = event.copy()
    slotted.start = sample_ms - duration // 2
    slotted.end = slotted.start + duration
    slotted.text = _shift_text(event.text, dx, dy)
    slotted.marginl = margin_l + dx
    slotted.marginr = margin_r + dx
    slotted.marginv = margin_v + dy
    return slotted


def measure_boxes(
    subs: SSAFile,
    events: Sequence[SSAEvent],
    size: Size,
    work: Path,
    name: str,
) -> tuple[list[Box | None], FontReport]:
    """Render each event alone at its midpoint and return its box in script pixels."""
    if not events:
        return [], FontReport((), {})
    canvas, slot_s = measurement_file(subs, events, size)
    canvas.save(str(work / f"{name}.ass"), encoding="utf-8")
    width: int = int(canvas.info["PlayResX"])
    height: int = int(canvas.info["PlayResY"])
    source: str = (
        f"color=c=0x{_BACKGROUND[0]:02x}{_BACKGROUND[1]:02x}{_BACKGROUND[2]:02x}:s={width}x{height}"
        f":r=1/{slot_s}:d={(len(events) + 1) * slot_s},format=rgb24"
    )
    arguments: list[str] = ["-v", "verbose", "-f", "lavfi", "-i", source, "-vf", _ass_filter(f"{name}.ass", work)]
    raw: list[str] = [*arguments, "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    log: Path = work / f"{name}.log"
    frames: Iterator[bytes] = _ffmpeg_frames(raw, work, log, 3 * width * height)
    boxes: list[Box | None] = [_frame_box(frame, width, size) for frame in frames][1 : len(events) + 1]
    boxes.extend([None] * (len(events) - len(boxes)))
    return boxes, parse_font_log(log.read_text(encoding="utf-8", errors="replace"))


def _frame_box(frame: bytes, width: int, size: Size) -> Box | None:
    stride: int = 3 * width
    blank: bytes = _BACKGROUND_PIXEL * width
    changed: list[int] = [
        row for row in range(len(frame) // stride) if frame[row * stride : (row + 1) * stride] != blank
    ]
    if not changed:
        return None
    top, bottom = changed[0], changed[-1] + 1
    band: Image.Image = Image.frombytes("RGB", (width, bottom - top), frame[top * stride : bottom * stride])
    box: tuple[int, int, int, int] | None = ImageChops.difference(
        band, Image.new("RGB", band.size, _BACKGROUND)
    ).getbbox()
    if box is None:
        return None
    dx, dy = _padding(size)
    return box[0] - dx, top + box[1] - dy, box[2] - dx, top + box[3] - dy


def _ass_filter(filename: str, work: Path) -> str:
    fonts: str = ":fontsdir=fonts" if (work / "fonts").is_dir() else ""
    return f"ass={filename}{fonts}"


def _ffmpeg(arguments: list[str], work: Path) -> str:
    completed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - argv built here
        [str(require_binary(Binary.FFMPEG)), "-hide_banner", "-nostdin", "-y", *arguments],
        cwd=work,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_FFMPEG_TIMEOUT_S,
        check=False,
        creationflags=_NO_WINDOW,
    )
    _check(completed.returncode, completed.stderr)
    return completed.stderr


def _ffmpeg_frames(arguments: list[str], work: Path, log: Path, frame_bytes: int) -> Iterator[bytes]:
    """Yield the complete raw frames FFmpeg writes to stdout, keeping its log in a file."""
    with (
        log.open("wb") as log_file,
        subprocess.Popen(  # noqa: S603 - argv built here
            [str(require_binary(Binary.FFMPEG)), "-hide_banner", "-nostdin", "-y", *arguments],
            cwd=work,
            stdout=subprocess.PIPE,
            stderr=log_file,
            creationflags=_NO_WINDOW,
        ) as process,
    ):
        if process.stdout is not None:
            chunks: Iterator[bytes] = iter(partial(process.stdout.read, frame_bytes), b"")
            yield from (frame for frame in chunks if len(frame) == frame_bytes)
        returncode: int = process.wait(timeout=_FFMPEG_TIMEOUT_S)
    _check(returncode, log.read_text(encoding="utf-8", errors="replace"))


def _check(returncode: int, log: str) -> None:
    if returncode != 0:
        tail: str = "\n".join(log.strip().splitlines()[-5:])
        message: str = f"ffmpeg failed with {returncode}: {tail}"
        raise RuntimeError(message)


# ── Gallery ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Shot:
    """One gallery image request: a moment with optional boxes to outline."""

    time_ms: int
    target: Path
    caption: str
    source_box: Box | None = None
    output_box: Box | None = None


def render_shot(shot: Shot, video: Path | None, size: Size, work: Path) -> None:
    """Render the full source above the full output at one moment, on a video frame when available."""
    height: int = round(GALLERY_WIDTH * size[1] / size[0] / 2) * 2
    base: Path = work / "shot-base.png"
    if video is not None and video.is_file():
        seek: list[str] = ["-ss", f"{shot.time_ms / 1000:.3f}", "-i", str(video), "-frames:v", "1"]
        _ffmpeg([*seek, "-vf", f"scale={GALLERY_WIDTH}:{height}", base.name], work)
    else:
        Image.new("RGB", (GALLERY_WIDTH, height), _GALLERY_BACKGROUND).save(base)
    graph: str = (
        f"[0:v]setpts=PTS+{shot.time_ms / 1000:.3f}/TB,split[a][b];"
        f"[a]{_ass_filter('source.ass', work)}[x];[b]{_ass_filter('output.ass', work)}[y];[x][y]vstack"
    )
    _ffmpeg(["-i", base.name, "-filter_complex", graph, "-frames:v", "1", "shot.png"], work)
    shot.target.parent.mkdir(parents=True, exist_ok=True)
    _annotate(work / "shot.png", shot, GALLERY_WIDTH / size[0], height).save(shot.target)


def _annotate(path: Path, shot: Shot, scale: float, height: int) -> Image.Image:
    with Image.open(path) as rendered:
        image: Image.Image = rendered.convert("RGB")
    draw: ImageDraw.ImageDraw = ImageDraw.Draw(image)
    for box, offset, colour in ((shot.source_box, 0, _SOURCE_COLOUR), (shot.output_box, height, _OUTPUT_COLOUR)):
        if box is not None:
            draw.rectangle(_scaled(box, scale, offset), outline=colour, width=2)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.load_default(_CAPTION_SIZE)
    draw.text((8, 8), f"EN  {shot.caption}", font=font, fill="#ffffff", stroke_width=2, stroke_fill="#000000")
    draw.text((8, height + 8), "PL", font=font, fill="#ffffff", stroke_width=2, stroke_fill="#000000")
    return image


def _scaled(box: Box, scale: float, offset: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return round(left * scale), round(top * scale) + offset, round(right * scale), round(bottom * scale) + offset


def copy_scripts(source: Path, output: Path | None, work: Path) -> None:
    """Copy both subtitle files to filter-safe names in the work folder."""
    shutil.copyfile(source, work / "source.ass")
    shutil.copyfile(output if output is not None else source, work / "output.ass")
