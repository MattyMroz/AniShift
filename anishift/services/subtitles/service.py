"""Load, classify, split and write subtitle files."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Final

import pysubs2
from pysubs2 import SSAEvent, SSAFile

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.subtitles.classifier import Category, StyleVerdict, classify_styles
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.text import is_drawing, replace_visible_text, visible_text
from anishift.services.subtitles.types import (
    Decision,
    SplitStats,
    SpokenLine,
    SubtitleKind,
    SubtitleSplit,
)

__all__ = [
    "collapse_fbf",
    "load_subtitles",
    "preview_styles",
    "split_subtitles",
    "subtitle_kind",
    "write_displayed",
    "write_translated_displayed",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_FBF_MAX_GAP_MS: Final[int] = 500
"""Maximum gap between consecutive identical events merged as one FBF run."""

_SAMPLES_PER_STYLE: Final[int] = 3
"""Number of preview samples collected per style."""

_SAMPLE_MAX_CHARS: Final[int] = 60
"""Maximum preview sample length."""

_SUFFIX_KIND: Final[dict[str, SubtitleKind]] = {".ass": "ass", ".ssa": "ass", ".srt": "srt"}
"""Supported subtitle suffixes and their working formats."""

_ENCODING: Final[str] = "utf-8"
"""Subtitle file encoding."""

_LINE_BREAKS: Final[dict[SubtitleKind, str]] = {"ass": "\\N", "srt": "\n"}
"""Soft line break joining a displayed event's verses, per subtitle format."""


def _fail(code: ErrorCode, message: str) -> SubtitleError:
    return SubtitleError(context=ErrorContext(code=code, message=message))


def subtitle_kind(path: Path) -> SubtitleKind | None:
    """Return the working format for a file suffix, or None when unsupported."""
    return _SUFFIX_KIND.get(path.suffix.lower())


def load_subtitles(path: Path) -> SSAFile:
    """Load a subtitle file in UTF-8.

    Raises:
        SubtitleError: When the file is missing, unreadable or unparsable.
    """
    try:
        return pysubs2.load(str(path), encoding=_ENCODING)
    except FileNotFoundError as exc:
        msg = f"Subtitle file not found: {path}"
        raise _fail(ErrorCode.SUBTITLE_PARSE_FAILED, msg) from exc
    except UnicodeDecodeError as exc:
        msg = f"Subtitle file is not valid UTF-8: {path}"
        raise _fail(ErrorCode.SUBTITLE_PARSE_FAILED, msg) from exc
    except OSError as exc:
        msg = f"Subtitle file could not be read: {path}"
        raise _fail(ErrorCode.SUBTITLE_PARSE_FAILED, msg) from exc
    except pysubs2.exceptions.Pysubs2Error as exc:
        msg = f"Subtitle file could not be parsed: {path}"
        raise _fail(ErrorCode.SUBTITLE_PARSE_FAILED, msg) from exc


def preview_styles(subs: SSAFile) -> tuple[tuple[StyleVerdict, ...], dict[str, tuple[str, ...]]]:
    """Classify styles and collect short, visible-text samples per style."""
    verdicts = tuple(classify_styles(subs))
    samples: dict[str, list[str]] = defaultdict(list)
    for event in subs.events:
        if event.type != "Dialogue" or is_drawing(event.text):
            continue
        text = visible_text(event.text)
        if not text or text in samples[event.style] or len(samples[event.style]) >= _SAMPLES_PER_STYLE:
            continue
        samples[event.style].append(text[: _SAMPLE_MAX_CHARS - 1] + "…" if len(text) > _SAMPLE_MAX_CHARS else text)
    return verdicts, {style: tuple(lines) for style, lines in samples.items()}


def _make_run(events: list[SSAEvent], text: str, style: str) -> SpokenLine:
    return SpokenLine(
        start=min(event.start for event in events),
        end=max(event.end for event in events),
        text=text,
        style=style,
    )


def _collapse_group(events: list[SSAEvent], text: str, style: str) -> tuple[list[SpokenLine], int]:
    ordered = sorted(events, key=lambda event: event.start)
    runs: list[list[SSAEvent]] = []
    for event in ordered:
        if not runs or event.start - max(item.end for item in runs[-1]) > _FBF_MAX_GAP_MS:
            runs.append([event])
            continue
        runs[-1].append(event)
    return [_make_run(run, text, style) for run in runs], len(events) - len(runs)


def collapse_fbf(events: Sequence[SSAEvent]) -> tuple[tuple[SpokenLine, ...], int]:
    """Collapse frame-by-frame runs of identical visible text."""
    groups: dict[tuple[str, str], list[SSAEvent]] = defaultdict(list)
    for event in events:
        if is_drawing(event.text):
            continue
        text = visible_text(event.text)
        if text:
            groups[(event.style, text)].append(event)
    lines: list[SpokenLine] = []
    collapsed_away = 0
    for (style, text), group in groups.items():
        group_lines, removed = _collapse_group(group, text, style)
        lines.extend(group_lines)
        collapsed_away += removed
    lines.sort(key=lambda line: (line.start, line.end, line.style))
    return tuple(lines), collapsed_away


def _dialogue_decisions(
    dialogue: Sequence[SSAEvent],
    spoken_styles: Collection[str],
) -> tuple[list[Decision], int, int, int]:
    decisions: list[Decision] = []
    drawing_events = 0
    for event in dialogue:
        if is_drawing(event.text):
            decisions.append("displayed")
            drawing_events += 1
            continue
        decisions.append("spoken" if event.style in spoken_styles else "displayed")
    spoken_events = decisions.count("spoken")
    if spoken_events == 0 and len(dialogue) > drawing_events:
        decisions = ["displayed" if is_drawing(event.text) else "spoken" for event in dialogue]
        spoken_events = len(dialogue) - drawing_events
    return decisions, spoken_events, drawing_events, decisions.count("displayed")


def split_subtitles(
    subs: SSAFile,
    *,
    kind: SubtitleKind,
    spoken_styles: Collection[str] | None = None,
    verdicts: Sequence[StyleVerdict] | None = None,
) -> SubtitleSplit:
    """Mark every Dialogue line spoken or displayed and build the spoken stream."""
    dialogue = [event for event in subs.events if event.type == "Dialogue"]
    if kind == "srt":
        decisions: list[Decision] = ["spoken"] * len(dialogue)
        final_verdicts: tuple[StyleVerdict, ...] = ()
        drawing_events = 0
    else:
        final_verdicts = tuple(verdicts) if verdicts is not None else tuple(classify_styles(subs))
        styles = (
            set(spoken_styles)
            if spoken_styles is not None
            else {verdict.style for verdict in final_verdicts if verdict.category is Category.DIALOG}
        )
        decisions, _, drawing_events, _ = _dialogue_decisions(dialogue, styles)
    spoken_events = decisions.count("spoken")
    spoken_input = [event for event, decision in zip(dialogue, decisions, strict=True) if decision == "spoken"]
    spoken, collapsed_away = collapse_fbf(spoken_input)
    stats = SplitStats(
        total_events=len(dialogue),
        spoken_events=spoken_events,
        spoken_lines=len(spoken),
        displayed_events=decisions.count("displayed"),
        drawing_events=drawing_events,
        collapsed_away=collapsed_away,
    )
    return SubtitleSplit(kind, subs, tuple(decisions), final_verdicts, spoken, stats)


def _displayed_file(split: SubtitleSplit) -> SSAFile:
    out = SSAFile()
    out.info = dict(split.subs.info)
    out.styles = {name: style.copy() for name, style in split.subs.styles.items()}
    dialogue_index = 0
    for event in split.subs.events:
        if event.type != "Dialogue":
            out.events.append(event)
            continue
        if split.decisions[dialogue_index] == "displayed":
            out.events.append(event)
        dialogue_index += 1
    return out


def write_displayed(split: SubtitleSplit, dest: Path) -> Path | None:
    """Write the displayed product atomically, or return None when empty."""
    if split.stats.displayed_events == 0:
        return None
    output = _displayed_file(split)
    temporary = dest.with_name(dest.name + ".tmp")
    try:
        temporary.write_text(output.to_string(format_=split.kind), encoding=_ENCODING)
        temporary.replace(dest)
    except OSError as exc:
        msg = f"Displayed subtitles could not be written: {dest}"
        raise _fail(ErrorCode.IO_ERROR, msg) from exc
    return dest


def _translated_displayed_file(split: SubtitleSplit, verses: Sequence[tuple[str, ...]]) -> SSAFile:
    out = SSAFile()
    out.info = dict(split.subs.info)
    out.styles = {name: style.copy() for name, style in split.subs.styles.items()}
    line_break = _LINE_BREAKS[split.kind]
    dialogue_index = 0
    verse_index = 0
    for event in split.subs.events:
        if event.type != "Dialogue":
            out.events.append(event)
            continue
        if split.decisions[dialogue_index] == "displayed":
            translated = line_break.join(verses[verse_index])
            replaced = event.copy()
            replaced.text = replace_visible_text(event.text, translated)
            out.events.append(replaced)
            verse_index += 1
        dialogue_index += 1
    return out


def write_translated_displayed(
    split: SubtitleSplit,
    verses: Sequence[tuple[str, ...]],
    dest: Path,
) -> Path | None:
    r"""Write the translated displayed subtitles atomically, or None when empty.

    Each displayed Dialogue event keeps its tags, style and timing; only its
    visible text is replaced with the translated verses joined by the format's
    soft break (``\N`` for ASS, ``\n`` for SRT). ``verses`` carries one verse
    tuple per displayed event, in event order.

    Raises:
        SubtitleError: The file could not be written.
    """
    if split.stats.displayed_events == 0:
        return None
    output = _translated_displayed_file(split, verses)
    temporary = dest.with_name(dest.name + ".tmp")
    try:
        temporary.write_text(output.to_string(format_=split.kind), encoding=_ENCODING)
        temporary.replace(dest)
    except OSError as exc:
        msg = f"Translated displayed subtitles could not be written: {dest}"
        raise _fail(ErrorCode.IO_ERROR, msg) from exc
    return dest
