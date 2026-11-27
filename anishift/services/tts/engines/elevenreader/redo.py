"""Parts whose words the server left out, the blocks read again and their joining into pauses heard in the audio."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from .constants import LINE_SEPARATOR
from .host import (
    PartTiming,
    cut_before_ms,
    frames_duration_ms,
    get_logger,
    iter_frames,
    mono_pcm,
    splice_times,
)
from .pauses import FRAME_MS, NOISE_DBFS, Span, best_pause, frame_levels
from .types import AlignmentChunk, Redo

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path
    from typing import BinaryIO

    from .host import DocumentPart, FrameHeader

__all__ = [
    "Difference",
    "Reading",
    "Redone",
    "Take",
    "new_file",
    "part_spans",
    "read_parts",
    "redo_blocks",
    "splice",
    "stream_timeline",
    "timings",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_WORD: Final[re.Pattern[str]] = re.compile(r"[^\W_]+")
"""One word: a run of letters and digits, the only characters compared; punctuation, spacing and case never count."""

_BREAK_RUN: Final[re.Pattern[str]] = re.compile(r"<break[^>]*(?:>|$)(?:\s*<break[^>]*(?:>|$))*")
"""Adjacent SSML pauses the server puts between parts; the final tag may be cut off at the end of the text."""


@dataclass(frozen=True, slots=True)
class Take:
    """One recorded document: its MP3 file and the stream chunks with the text and times the server sent."""

    recording: Path
    chunks: tuple[AlignmentChunk, ...]

    @property
    def text(self) -> str:
        """Return the text the server streamed."""
        return "".join(char for chunk in self.chunks for char in chunk.chars)


@dataclass(frozen=True, slots=True)
class Difference:
    """Words at one place that the stream left out or changed (*expected*) or sent instead or in addition."""

    part: int
    expected: str
    received: str


@dataclass(frozen=True, slots=True)
class Reading:
    """Where each part lies in the streamed text, as first and last character, and which parts lack a word."""

    ranges: tuple[tuple[int, int] | None, ...]
    missing: tuple[int, ...]
    differences: tuple[Difference, ...]


@dataclass(frozen=True, slots=True)
class Redone:
    """Parts *first* to *last* of the document recorded again as one complete document."""

    first: int
    last: int
    take: Take


@dataclass(frozen=True, slots=True)
class _Audio:
    """A recording with the level and server time of every level frame."""

    data: bytes
    levels: list[float]
    times: list[float]
    duration_ms: float


@dataclass(frozen=True, slots=True)
class _Stream:
    """Streamed text of a recording with every character's times, its words and its pause tags."""

    text: str
    starts: list[float]
    ends: list[float]
    words: list[tuple[str, int, int]]
    breaks: list[tuple[int, int]]

    @classmethod
    def of(cls, chunks: tuple[AlignmentChunk, ...]) -> _Stream:
        """Return the stream of *chunks*."""
        text, starts, ends = stream_timeline(chunks)
        breaks: list[tuple[int, int]] = [(match.start(), match.end()) for match in _BREAK_RUN.finditer(text)]
        return cls(text, starts, ends, _stream_words(text, breaks), breaks)

    def span(self, first: int, last: int) -> Span:
        """Return the server span of characters *first* to *last*."""
        return Span(self.starts[first], self.ends[last])


@dataclass(frozen=True, slots=True)
class _Cut:
    """Where a redone block goes: main audio up to *before_ms*, the redo between its bounds, main from *after_ms*."""

    block: Redone
    before_ms: float | None
    after_ms: float | None
    redo_from_ms: float
    redo_to_ms: float | None


def read_parts(text: str, parts: Sequence[str]) -> Reading:
    """Compare the words of all *parts* with the words of the streamed *text* at once and place every part in it."""
    breaks: list[tuple[int, int]] = [(match.start(), match.end()) for match in _BREAK_RUN.finditer(text)]
    words: list[tuple[str, int, int]] = _stream_words(text, breaks)
    ours: list[str] = []
    owners: list[int] = []
    for index, part in enumerate(parts):
        for match in _WORD.finditer(part):
            ours.append(match.group().casefold())
            owners.append(index)
    theirs: list[str] = [word for word, _, _ in words]
    owner: list[int | None] = [None] * len(words)
    missing: set[int] = set()
    differences: list[Difference] = []
    for tag, ours_from, ours_to, theirs_from, theirs_to in SequenceMatcher(
        None, ours, theirs, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            owner[theirs_from:theirs_to] = owners[ours_from:ours_to]
            continue
        missing.update(owners[ours_from:ours_to])
        place: int = owners[ours_from] if ours_from < ours_to else owners[ours_from - 1] if ours_from else 0
        differences.append(
            Difference(place, " ".join(ours[ours_from:ours_to]), " ".join(theirs[theirs_from:theirs_to]))
        )
    ranges: list[tuple[int, int] | None] = _word_ranges(text, words, breaks, owner, len(parts))
    _place_wordless(text, breaks, parts, ranges)
    return Reading(ranges=tuple(ranges), missing=tuple(sorted(missing)), differences=tuple(differences))


def redo_blocks(missing: Sequence[int], count: int, mode: Redo) -> tuple[tuple[int, int], ...]:
    """Return the first and last part of every block to record again; touching or overlapping blocks are one."""
    reach: int = 1 if mode is Redo.PARAGRAPH else 0
    blocks: list[tuple[int, int]] = []
    for index in sorted(missing):
        first, last = max(index - reach, 0), min(index + reach, count - 1)
        if blocks and first <= blocks[-1][1] + 1:
            blocks[-1] = (blocks[-1][0], max(blocks[-1][1], last))
        else:
            blocks.append((first, last))
    return tuple(blocks)


def stream_timeline(chunks: tuple[AlignmentChunk, ...]) -> tuple[str, list[float], list[float]]:
    """Return the streamed text with the start and end of every character on the recording timeline."""
    text: str = "".join(char for chunk in chunks for char in chunk.chars)
    starts: list[float] = [chunk.offset_ms + start for chunk in chunks for start in chunk.starts_ms]
    ends: list[float] = [
        chunk.offset_ms + start + duration
        for chunk in chunks
        for start, duration in zip(chunk.starts_ms, chunk.durations_ms, strict=True)
    ]
    return text, starts, ends


def timings(
    chunks: tuple[AlignmentChunk, ...], parts: tuple[DocumentPart, ...], ranges: Sequence[tuple[int, int] | None]
) -> tuple[PartTiming, ...]:
    """Return the server timing of every part; a part not found, reversed or touching a silent chunk gets none."""
    _, starts, ends = stream_timeline(chunks)
    silent: list[bool] = [chunk.silent for chunk in chunks for _ in chunk.chars]
    spans: list[PartTiming] = []
    cursor: float = 0.0
    for part, bounds in zip(parts, ranges, strict=True):
        if bounds is None:
            spans.append(PartTiming(request_id=part.request_id, start_ms=cursor, end_ms=cursor))
            continue
        first, last = bounds
        start_ms: float = starts[first]
        end_ms: float = ends[last]
        if end_ms < start_ms or any(silent[first : last + 1]):
            end_ms = start_ms
        spans.append(PartTiming(request_id=part.request_id, start_ms=start_ms, end_ms=end_ms))
        cursor = end_ms
    return tuple(spans)


def part_spans(chunks: tuple[AlignmentChunk, ...], parts: tuple[DocumentPart, ...]) -> tuple[PartTiming, ...]:
    """Return the server timing of every part found by its words in the streamed text of *chunks*."""
    text: str = "".join(char for chunk in chunks for char in chunk.chars)
    return timings(chunks, parts, read_parts(text, [part.text for part in parts]).ranges)


def splice(
    main: Take, reading: Reading, redone: Sequence[Redone], output: Path, count: int
) -> tuple[tuple[AlignmentChunk, ...], tuple[Redone, ...]]:
    """Write *main* with the redone blocks cut in at heard pauses to *output*; return its chunks and blocks left out."""
    audio: _Audio = _audio(main.recording)
    stream: _Stream = _Stream.of(main.chunks)
    cuts: list[_Cut] = []
    left_out: list[Redone] = []
    last_after_ms: float = 0.0
    for block in redone:
        cut: _Cut | None = _cut(block, audio, stream, reading, count)
        if cut is None or (cut.before_ms is not None and cut.before_ms < last_after_ms):
            logger.warning("ElevenReader redo is not joined: no pause to cut in", first=block.first, last=block.last)
            left_out.append(block)
            continue
        cuts.append(cut)
        last_after_ms = audio.duration_ms if cut.after_ms is None else cut.after_ms
    joined: _Joined = _Joined()
    main_ms: float = 0.0
    main_char: int = 0
    for cut in cuts:
        block_text: str = cut.block.take.text
        before_char: int = 0 if cut.block.first == 0 else _gap_end(stream, reading.ranges[cut.block.first - 1])
        joined.add(audio.data, main.chunks, (main_ms, cut.before_ms or 0.0), (main_char, before_char))
        redo_from: int = 0 if cut.block.first == 0 else _skip_gap(block_text)
        redo_to: int = len(block_text) if cut.block.last == count - 1 else _trim_gap(block_text)
        joined.add(
            cut.block.take.recording.read_bytes(),
            cut.block.take.chunks,
            (cut.redo_from_ms, cut.redo_to_ms),
            (redo_from, redo_to),
        )
        main_ms = audio.duration_ms if cut.after_ms is None else cut.after_ms
        main_char = (
            len(stream.text) if cut.block.last == count - 1 else _gap_start(stream, reading.ranges[cut.block.last + 1])
        )
    joined.add(audio.data, main.chunks, (main_ms, None), (main_char, len(stream.text)))
    with new_file(output) as file:
        file.write(joined.data)
    return tuple(joined.chunks), tuple(left_out)


def new_file(path: Path) -> BinaryIO:
    """Open *path* for writing only when it is missing or an empty placeholder, so no recording is overwritten."""
    if path.is_file() and not path.stat().st_size:
        return path.open("wb")
    return path.open("xb")


class _Joined:
    """MP3 frames and stream chunks of the joined recording, built piece by piece."""

    def __init__(self) -> None:
        """Start empty."""
        self.data: bytearray = bytearray()
        self.chunks: list[AlignmentChunk] = []
        self._ms: float = 0.0

    def add(
        self,
        data: bytes,
        chunks: tuple[AlignmentChunk, ...],
        span_ms: tuple[float, float | None],
        span_chars: tuple[int, int],
    ) -> None:
        """Append the frames of *data* between the server times of *span_ms* and the characters of *span_chars*."""
        start_ms, end_ms = span_ms
        start, played_from_ms = _frame_at(data, start_ms)
        end: int = len(data) if end_ms is None else _frame_at(data, end_ms)[0]
        if end <= start:
            return
        piece: bytes = data[start:end]
        shift_ms: float = self._ms - played_from_ms
        self.data += piece
        self.chunks.extend(_shifted(chunks, span_chars, shift_ms))
        self._ms += frames_duration_ms(piece)


def _cut(block: Redone, audio: _Audio, stream: _Stream, reading: Reading, count: int) -> _Cut | None:
    """Return where *block* goes, or None when a neighbour has no place in the stream or no pause is heard."""
    before: tuple[float, float, float] | None = None
    after: tuple[float, float, float] | None = None
    if block.first > 0:
        kept: tuple[int, int] | None = reading.ranges[block.first - 1]
        if kept is None:
            return None
        before = _pause(audio, stream.span(*kept), _paragraph_after(stream, kept[1], audio.duration_ms))
        if before is None:
            return None
    if block.last < count - 1:
        kept = reading.ranges[block.last + 1]
        after = None if kept is None else _pause(audio, _paragraph_before(stream, kept[0]), stream.span(*kept))
        if after is None or (before is not None and after[1] < before[1]):
            return None
    redo: _Audio = _audio(block.take.recording)
    heard: list[int] = [index for index, level in enumerate(redo.levels) if level >= NOISE_DBFS]
    if not heard:
        return None
    onset_ms: float = redo.times[heard[0]]
    offset_ms: float = redo.times[heard[-1]] + FRAME_MS
    return _Cut(
        block=block,
        before_ms=None if before is None else before[1],
        after_ms=None if after is None else after[1],
        redo_from_ms=0.0 if before is None else max(0.0, onset_ms - (before[2] - before[1])),
        redo_to_ms=None if after is None else min(redo.duration_ms, offset_ms + (after[1] - after[0])),
    )


def _pause(audio: _Audio, line: Span, following: Span) -> tuple[float, float, float] | None:
    """Return the start, middle and end of the best pause between two lines of speech, or None."""
    pause: tuple[float, float] | None = best_pause(audio.levels, audio.times, line, following)
    if pause is None:
        return None
    start, end = pause
    return start, (start + end) / 2, end


def _paragraph_after(stream: _Stream, after: int, end_ms: float) -> Span:
    """Return the span from the first streamed word after character *after* to the end of its paragraph."""
    following: int = next((index for index, word in enumerate(stream.words) if word[1] > after), len(stream.words))
    if following == len(stream.words):
        return Span(end_ms, end_ms)
    first: int = stream.words[following][1]
    stop: int = next((start for start, _ in stream.breaks if start >= first), len(stream.text))
    last: int = max(end - 1 for _, start, end in stream.words[following:] if start < stop)
    return stream.span(first, last)


def _paragraph_before(stream: _Stream, before: int) -> Span:
    """Return the span from the start of the paragraph of the last streamed word before character *before* to it."""
    previous: list[tuple[str, int, int]] = [word for word in stream.words if word[2] <= before]
    if not previous:
        return Span(0.0, 0.0)
    last: int = previous[-1][2] - 1
    opened: int = max((end for _, end in stream.breaks if end <= last), default=0)
    first: int = min(start for _, start, _ in previous if start >= opened)
    return stream.span(first, last)


def _audio(recording: Path) -> _Audio:
    """Return *recording* with its frame levels placed on the server timeline, one frame later per splice."""
    data: bytes = recording.read_bytes()
    levels: list[float] = frame_levels(mono_pcm(recording))
    first: FrameHeader | None = next(iter_frames(data), None)
    frame_ms: float = 0.0 if first is None else first.duration_ms
    splices: tuple[float, ...] = splice_times(data)
    times: list[float] = [
        index * FRAME_MS + frame_ms * bisect_right(splices, index * FRAME_MS) for index in range(len(levels))
    ]
    return _Audio(data=data, levels=levels, times=times, duration_ms=frames_duration_ms(data))


def _frame_at(data: bytes, at_ms: float) -> tuple[int, float]:
    """Return the byte offset of the first frame starting at or after *at_ms* and its server time."""
    rest, dropped_ms = cut_before_ms(data, at_ms)
    return len(data) - len(rest), dropped_ms


def _shifted(chunks: tuple[AlignmentChunk, ...], span: tuple[int, int], shift_ms: float) -> Iterator[AlignmentChunk]:
    """Yield the characters of *chunks* inside *span*, chunk by chunk, moved by *shift_ms*."""
    low, high = span
    position: int = 0
    for chunk in chunks:
        first: int = max(low - position, 0)
        last: int = min(high - position, len(chunk.chars))
        position += len(chunk.chars)
        if first >= last:
            continue
        yield AlignmentChunk(
            offset_ms=chunk.offset_ms + shift_ms,
            chars=chunk.chars[first:last],
            starts_ms=chunk.starts_ms[first:last],
            durations_ms=chunk.durations_ms[first:last],
            silent=chunk.silent,
        )


def _stream_words(text: str, breaks: Sequence[tuple[int, int]]) -> list[tuple[str, int, int]]:
    """Return every word of *text* outside the pause tags, case-folded, with its start and end."""
    blank: list[str] = list(text)
    for start, end in breaks:
        blank[start:end] = " " * (end - start)
    return [(match.group().casefold(), match.start(), match.end()) for match in _WORD.finditer("".join(blank))]


def _word_ranges(
    text: str,
    words: list[tuple[str, int, int]],
    breaks: list[tuple[int, int]],
    owner: list[int | None],
    count: int,
) -> list[tuple[int, int] | None]:
    """Return each part from its first to its last streamed word, with the punctuation that belongs to it."""
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    for index, part in enumerate(owner):
        if part is not None:
            first.setdefault(part, index)
            last[part] = index
    ranges: list[tuple[int, int] | None] = [None] * count
    for part, index in first.items():
        start: int = _left_edge(text, words, breaks, index)
        end: int = _right_edge(text, words, breaks, last[part])
        ranges[part] = (start, end - 1)
    return ranges


def _left_edge(text: str, words: list[tuple[str, int, int]], breaks: list[tuple[int, int]], index: int) -> int:
    """Return where the text of a part starts: after the last pause or space before its first word."""
    start: int = words[index][1]
    low: int = words[index - 1][2] if index else 0
    paused: list[int] = [end for begin, end in breaks if low <= begin and end <= start]
    if paused:
        return _skip_space(text, paused[-1], start)
    spaces: list[int] = [position for position in range(low, start) if text[position].isspace()]
    if spaces:
        return spaces[-1] + 1
    return low if not index else start


def _right_edge(text: str, words: list[tuple[str, int, int]], breaks: list[tuple[int, int]], index: int) -> int:
    """Return where the text of a part ends: before the first pause or space after its last word."""
    end: int = words[index][2]
    high: int = words[index + 1][1] if index + 1 < len(words) else len(text)
    paused: list[int] = [begin for begin, finish in breaks if end <= begin and finish <= high]
    stop: int = paused[0] if paused else next((p for p in range(end, high) if text[p].isspace()), high)
    while stop > end and text[stop - 1].isspace():
        stop -= 1
    return stop


def _skip_space(text: str, start: int, stop: int) -> int:
    while start < stop and text[start].isspace():
        start += 1
    return start


def _place_wordless(
    text: str, breaks: list[tuple[int, int]], parts: Sequence[str], ranges: list[tuple[int, int] | None]
) -> None:
    """Give each part without a word the next streamed paragraph without a word between its placed neighbours."""
    cursor: int = 0
    for index, part in enumerate(parts):
        bounds: tuple[int, int] | None = ranges[index]
        if bounds is not None:
            cursor = bounds[1] + 1
            continue
        if _WORD.search(part):
            continue
        high: int = next((found[0] for found in ranges[index + 1 :] if found is not None), len(text))
        segment: tuple[int, int] | None = next(_wordless_segments(text, breaks, cursor, high), None)
        if segment is not None:
            ranges[index] = segment
            cursor = segment[1] + 1


def _wordless_segments(text: str, breaks: list[tuple[int, int]], low: int, high: int) -> Iterator[tuple[int, int]]:
    """Yield the paragraphs between pause tags inside *low* to *high* that hold text but no word."""
    edges: list[int] = [low]
    for start, end in breaks:
        if low <= start and end <= high:
            edges.extend((start, end))
    edges.append(high)
    for begin, stop in zip(edges[::2], edges[1::2], strict=True):
        first: int = _skip_space(text, begin, stop)
        last: int = stop - 1
        while last >= first and text[last].isspace():
            last -= 1
        if first > last or text[first : last + 1] == LINE_SEPARATOR or _WORD.search(text, first, last + 1):
            continue
        yield first, last


def _gap_end(stream: _Stream, bounds: tuple[int, int] | None) -> int:
    """Return where the text after a part starts: past its pause and separator, at the next word's own text."""
    if bounds is None:
        return 0
    following: int = next((index for index, word in enumerate(stream.words) if word[1] > bounds[1]), -1)
    if following < 0:
        return len(stream.text)
    return _left_edge(stream.text, stream.words, stream.breaks, following)


def _gap_start(stream: _Stream, bounds: tuple[int, int] | None) -> int:
    """Return where the pause and separator before a part start, right after the text before them."""
    if bounds is None:
        return len(stream.text)
    start: int = bounds[0]
    while start > 0 and _in_gap(stream.text, stream.breaks, start - 1):
        start -= 1
    return start


def _in_gap(text: str, breaks: Sequence[tuple[int, int]], position: int) -> bool:
    if text[position].isspace() or text[position] == LINE_SEPARATOR:
        return True
    return any(start <= position < end for start, end in breaks)


def _skip_gap(text: str) -> int:
    """Return the first character of *text* that is not space, separator or a pause tag."""
    breaks: list[tuple[int, int]] = [(match.start(), match.end()) for match in _BREAK_RUN.finditer(text)]
    position: int = 0
    while position < len(text) and _in_gap(text, breaks, position):
        position += 1
    return position


def _trim_gap(text: str) -> int:
    """Return the end of *text* without the space, separator and pause tags that close it."""
    breaks: list[tuple[int, int]] = [(match.start(), match.end()) for match in _BREAK_RUN.finditer(text)]
    position: int = len(text)
    while position > 0 and _in_gap(text, breaks, position - 1):
        position -= 1
    return position
