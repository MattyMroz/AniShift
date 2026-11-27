from __future__ import annotations

import asyncio
import base64
import json
import math
import re
from array import array
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest
from engine_host import make_engine, make_request

from anishift.services.tts.engines.elevenreader import Redo, redo, service
from anishift.services.tts.engines.elevenreader.host import (
    Cancellation,
    TtsCancelledError,
    TtsProviderUnavailableError,
    frames_duration_ms,
    iter_frames,
)
from anishift.services.tts.engines.elevenreader.types import LibraryState, PlayerState, UploadedRead

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from engine_host import DocumentResult

    from anishift.services.tts.engines.elevenreader.browser import ChromeSession
    from anishift.services.tts.engines.elevenreader.recorder import StreamRecorder
    from anishift.services.tts.engines.elevenreader.types import AccountCleanup

pytestmark = pytest.mark.unit

PARTS = (
    "Pierwsza kwestia jest krótka.",
    "Druga kwestia mówi o lesie.",
    "Trzecia kwestia ma trzy zdania. Drugie zdanie. Trzecie zdanie.",
    "Czwarta kwestia stoi przed końcem.",
    "Piąta kwestia kończy tekst.",
)
GLUE = "\n\n…\n\n"
BREAK = '<break time="0.6s"/>'
FINAL_BREAK = '<break time="2s"/>'
HEADER = bytes((0xFF, 0xFB, 0x90, 0x64))
FRAME_BYTES = 417
FRAME_MS = 1152 * 1000 / 44_100
LEAD_FRAMES = 10
PAUSE_FRAMES = 20
MS_PER_CHAR = 20.0
LOUD_SAMPLE = 3000
PAUSE_NOISE = 200
SAMPLES_PER_FRAME = 160
VOICE_ID = "T5l58N8RNz5DKoClpKIJ"
TOKEN = "token-redo"  # noqa: S105

type Script = Callable[[int, list[str]], list[str]]


def frames(count: int, fill: int) -> bytes:
    return (HEADER + bytes([fill]) * (FRAME_BYTES - len(HEADER))) * count


def frame_json(
    audio: bytes, chars: str = "", starts: list[float] | None = None, lengths: list[float] | None = None
) -> str:
    payload: dict[str, object] = {"audio": base64.b64encode(audio).decode("ascii")}
    if chars:
        payload["alignment"] = {"chars": list(chars), "charStartTimesMs": starts, "charDurationsMs": lengths}
    return json.dumps(payload)


def stream_of(take: int, paragraphs: list[str], *, pause_fill: int = 0) -> list[str]:
    sent: list[str] = [frame_json(frames(LEAD_FRAMES, 0))]
    for index, text in enumerate(paragraphs):
        gap: str = f" {FINAL_BREAK}" if index == len(paragraphs) - 1 else f" {BREAK} … {BREAK} "
        speech_frames: int = math.ceil(len(text) * MS_PER_CHAR / FRAME_MS) + 1
        speech_ms: float = speech_frames * FRAME_MS
        pause_ms: float = PAUSE_FRAMES * FRAME_MS
        starts: list[float] = [position * speech_ms / len(text) for position in range(len(text))]
        starts += [speech_ms + position * pause_ms / len(gap) for position in range(len(gap))]
        lengths: list[float] = [speech_ms / len(text)] * len(text) + [pause_ms / len(gap)] * len(gap)
        audio: bytes = frames(speech_frames, fill_of(take, index)) + frames(PAUSE_FRAMES, pause_fill)
        sent.append(frame_json(audio, text + gap, starts, lengths))
    return sent


def fill_of(take: int, paragraph: int) -> int:
    return 10 * take + paragraph + 1


def fill_pcm(recording: Path) -> array[int]:
    data: bytes = recording.read_bytes()
    spans: list[tuple[float, float, int]] = []
    clock: float = 0.0
    for frame in iter_frames(data):
        spans.append((clock, clock + frame.duration_ms, data[frame.offset + len(HEADER)]))
        clock += frame.duration_ms
    pcm: array[int] = array("h")
    for index in range(int(frames_duration_ms(data) // 10)):
        fill: int = next(value for start, end, value in spans if start <= index * 10 < end)
        pcm.extend([LOUD_SAMPLE if fill else 0] * SAMPLES_PER_FRAME)
    return pcm


def fills(recording: Path) -> list[int]:
    data: bytes = recording.read_bytes()
    runs: list[int] = []
    for frame in iter_frames(data):
        fill: int = data[frame.offset + len(HEADER)]
        if fill and (not runs or runs[-1] != fill):
            runs.append(fill)
    return runs


def as_written(_: int, parts: list[str]) -> list[str]:
    return parts


@dataclass
class Site:
    script: Script = as_written
    stalls: set[int] = field(default_factory=set)
    failing: set[int] = field(default_factory=set)
    broken: set[int] = field(default_factory=set)
    hangs: set[int] = field(default_factory=set)
    loud_pauses: set[int] = field(default_factory=set)
    on_upload: Callable[[int], None] | None = None
    uploads: list[list[str]] = field(default_factory=list)
    account: dict[str, object] = field(default_factory=lambda: {"default_voice_id": "other", "playback_speed_rate": 1})


class Page:
    def __init__(self, site: Site) -> None:
        self.site: Site = site
        self.take: int = 0
        self.sent: list[str] = []
        self.recorder: StreamRecorder | None = None
        self.on_url: Callable[[str], None] | None = None

    @property
    def token(self) -> str | None:
        return "token"

    async def open_library(self) -> LibraryState:
        return LibraryState.READY

    async def upload(self, document: Path, cleanup: AccountCleanup, save: Callable[[], None]) -> UploadedRead:
        del cleanup, save
        parts: list[str] = document.read_text(encoding="utf-8").removesuffix("\n").split(GLUE)
        self.take = len(self.site.uploads)
        self.site.uploads.append(parts)
        if self.site.on_upload is not None:
            self.site.on_upload(self.take)
        if self.take in self.site.failing:
            message: str = "fake upload failed"
            raise TtsProviderUnavailableError(message)
        pause_fill: int = PAUSE_NOISE if self.take in self.site.loud_pauses else 0
        self.sent = stream_of(self.take, self.site.script(self.take, parts), pause_fill=pause_fill)
        streamed: int = sum(len(json.loads(frame).get("alignment", {}).get("chars", [])) for frame in self.sent)
        return UploadedRead(
            read_id=f"read-{self.take}", char_count=streamed + 1000 * (self.take in self.site.stalls), token=TOKEN
        )

    async def get_json(self, url: str, token: str, *, action: str) -> dict[str, object]:
        del url, token
        return {"reads": []} if action == "list_reads" else dict(self.site.account)

    async def post_json(self, url: str, token: str, data: dict[str, object], *, action: str) -> None:
        del url, token, action
        self.site.account = dict(data)

    async def delete(self, url: str, token: str, *, action: str) -> None:
        del url, token, action

    def raise_if_refused(self) -> None:
        return

    async def open_document(self, read_id: str) -> None:
        assert read_id == f"read-{self.take}"

    async def press_play(self) -> None:
        assert self.recorder is not None
        assert self.on_url is not None
        self.on_url(f"wss://api.elevenlabs.io/v1/reader/reads/stream/v2/read?voice_id={VOICE_ID}")
        self.recorder.on_sent(json.dumps({"listening_speed": 1}))
        for frame in self.sent:
            self.recorder.on_frame(frame)

    async def player_state(self) -> PlayerState:
        done: bool = self.take not in self.site.stalls
        return PlayerState(value=100.0 if done else 0.0, length=100.0)

    async def set_page_speed(self, speed: float) -> None:
        del speed

    async def check_page_speed(self, speed: float) -> None:
        del speed
        if self.take in self.site.broken:
            message: str = "fake page closed"
            raise TtsProviderUnavailableError(message)
        if self.take in self.site.hangs:
            await asyncio.Event().wait()

    def watch_stream(self, recorder: StreamRecorder, on_url: Callable[[str], None]) -> None:
        self.recorder = recorder
        self.on_url = on_url

    def unwatch_stream(self) -> None:
        self.recorder = None

    async def close(self) -> None:
        return


class Session:
    def __init__(self, site: Site) -> None:
        self.site: Site = site
        self.started: bool = False

    @property
    def alive(self) -> bool:
        return self.started

    async def start(self) -> None:
        self.started = True

    async def new_page(self) -> Page:
        return Page(self.site)

    async def close(self) -> None:
        self.started = False


@pytest.fixture(autouse=True)
def _fast_and_heard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "POLL_S", 0.001)
    monkeypatch.setattr(service, "END_IDLE_S", 0.0)
    monkeypatch.setattr(service, "START_TIMEOUT_S", 0.05)
    monkeypatch.setattr(service, "STALL_S", 0.05)
    monkeypatch.setattr(service, "SPEED_CHECK_S", 0.0)
    monkeypatch.setattr(redo, "mono_pcm", fill_pcm)


def record(
    tmp_path: Path, site: Site, mode: Redo, cancel: Cancellation | None = None, deadline_s: float = 60.0
) -> DocumentResult:
    def factory(root: Path) -> ChromeSession:
        del root
        return cast("ChromeSession", Session(site))

    async def run() -> DocumentResult:
        engine = make_engine(tmp_path / "home", factory, mode)
        try:
            request = make_request(PARTS, tmp_path / "out" / "doc.mp3", deadline_s)
            return await engine.synthesize_document(request, cancel=cancel or Cancellation())
        finally:
            await engine.close()

    return asyncio.run(run())


def drop_words(part: int, pattern: str) -> Script:
    def script(take: int, parts: list[str]) -> list[str]:
        if take:
            return parts
        changed: list[str] = list(parts)
        changed[part] = re.sub(pattern, "", changed[part]).strip()
        return [text for text in changed if text]

    return script


@pytest.mark.parametrize(
    ("pattern", "main_fills"),
    [
        ("trzy ", [1, 2, 3, 4, 5]),
        (r"Drugie zdanie\. ", [1, 2, 3, 4, 5]),
        (r".+", [1, 2, 3, 4]),
    ],
    ids=["word", "sentence", "paragraph"],
)
def test_line_mode_reads_the_bad_part_alone_and_joins_it_in_its_place(
    tmp_path: Path, pattern: str, main_fills: list[int]
) -> None:
    site = Site(script=drop_words(2, pattern))

    result = record(tmp_path, site, Redo.LINE)

    assert site.uploads[1] == [PARTS[2]]
    assert fills(result.recording) == [1, 2, fill_of(1, 0), *main_fills[-2:]]
    assert result.incomplete == ()
    assert all(timing.spoken for timing in result.parts)


@pytest.mark.parametrize(
    ("pattern", "main_fills"),
    [
        ("trzy ", [1, 2, 3, 4, 5]),
        (r"Drugie zdanie\. ", [1, 2, 3, 4, 5]),
        (r".+", [1, 2, 3, 4]),
    ],
    ids=["word", "sentence", "paragraph"],
)
def test_paragraph_mode_reads_the_bad_part_with_its_neighbours_and_replaces_all_three(
    tmp_path: Path, pattern: str, main_fills: list[int]
) -> None:
    site = Site(script=drop_words(2, pattern))

    result = record(tmp_path, site, Redo.PARAGRAPH)

    assert site.uploads[1] == list(PARTS[1:4])
    assert fills(result.recording) == [1, fill_of(1, 0), fill_of(1, 1), fill_of(1, 2), main_fills[-1]]
    assert result.incomplete == ()
    assert all(timing.spoken for timing in result.parts)


def test_paragraph_mode_bad_first_and_last_parts_redo_their_edges(tmp_path: Path) -> None:
    def script(take: int, parts: list[str]) -> list[str]:
        if take:
            return parts
        return [parts[0].replace("krótka", ""), *parts[1:4], parts[4].replace("tekst", "")]

    site = Site(script=script)

    result = record(tmp_path, site, Redo.PARAGRAPH)

    assert site.uploads[1:] == [list(PARTS[0:2]), list(PARTS[3:5])]
    assert fills(result.recording) == [fill_of(1, 0), fill_of(1, 1), 3, fill_of(2, 0), fill_of(2, 1)]
    assert result.incomplete == ()


def test_line_mode_adjacent_bad_parts_are_one_block(tmp_path: Path) -> None:
    def script(take: int, parts: list[str]) -> list[str]:
        return parts if take else [parts[0], "Druga kwestia mówi o.", "Trzecia kwestia.", *parts[3:]]

    site = Site(script=script)

    result = record(tmp_path, site, Redo.LINE)

    assert site.uploads[1] == list(PARTS[1:3])
    assert fills(result.recording) == [1, fill_of(1, 0), fill_of(1, 1), 4, 5]


def test_punctuation_and_case_alone_are_no_difference(tmp_path: Path) -> None:
    def script(_: int, parts: list[str]) -> list[str]:
        return [part.upper().replace(".", "!") + " —" for part in parts]

    site = Site(script=script)

    result = record(tmp_path, site, Redo.PARAGRAPH)

    assert len(site.uploads) == 1
    assert all(timing.spoken for timing in result.parts)
    assert result.incomplete == ()


@pytest.mark.parametrize(
    "script",
    [
        lambda _, parts: [parts[0], f"{parts[1]} {parts[2]}", *parts[3:]],
        lambda _, parts: [parts[0], parts[1], *re.split(r" (?=Drugie)", parts[2]), *parts[3:]],
    ],
    ids=["joined", "split"],
)
def test_lines_joined_or_split_by_the_server_are_no_difference(tmp_path: Path, script: Script) -> None:
    site = Site(script=script)

    result = record(tmp_path, site, Redo.LINE)

    assert len(site.uploads) == 1
    assert all(timing.spoken for timing in result.parts)
    assert result.incomplete == ()


def test_redo_still_missing_words_is_not_joined_listed_and_not_read_again(tmp_path: Path) -> None:
    def script(_: int, parts: list[str]) -> list[str]:
        return [part.replace("lesie", "") for part in parts]

    site = Site(script=script)

    result = record(tmp_path, site, Redo.LINE)

    assert len(site.uploads) == 2
    assert result.incomplete == ("part-1",)
    assert fills(result.recording) == [1, 2, 3, 4, 5]


def test_every_take_keeps_its_own_file_and_streamed_text(tmp_path: Path) -> None:
    site = Site(script=drop_words(1, "lesie"))

    result = record(tmp_path, site, Redo.LINE)

    folder: Path = result.recording.parent
    assert sorted(path.name for path in folder.iterdir()) == [
        "doc.mp3",
        "doc.stream.txt",
        "doc.take1.mp3",
        "doc.take1.stream.txt",
        "doc.take2.mp3",
        "doc.take2.stream.txt",
    ]
    assert fills(folder / "doc.take1.mp3") == [1, 2, 3, 4, 5]
    assert fills(folder / "doc.take2.mp3") == [fill_of(1, 0)]
    assert "lesie" not in (folder / "doc.take1.stream.txt").read_text(encoding="utf-8")
    assert "lesie" in (folder / "doc.stream.txt").read_text(encoding="utf-8")


def test_stream_stalling_after_speech_keeps_it_and_reads_only_the_rest(tmp_path: Path) -> None:
    def script(take: int, parts: list[str]) -> list[str]:
        return parts if take else parts[:3]

    site = Site(script=script, stalls={0})

    result = record(tmp_path, site, Redo.PARAGRAPH)

    assert site.uploads[1] == list(PARTS[2:5])
    assert fills(result.recording) == [1, 2, fill_of(1, 0), fill_of(1, 1), fill_of(1, 2)]
    assert result.incomplete == ()


def test_page_failing_after_speech_keeps_it_and_reads_only_the_rest(tmp_path: Path) -> None:
    def script(take: int, parts: list[str]) -> list[str]:
        return parts if take else parts[:3]

    site = Site(script=script, stalls={0}, broken={0})

    result = record(tmp_path, site, Redo.LINE)

    assert site.uploads[1] == list(PARTS[3:5])
    assert fills(result.recording) == [1, 2, 3, fill_of(1, 0), fill_of(1, 1)]
    assert result.incomplete == ()


def test_redo_ending_in_an_error_leaves_its_parts_incomplete_and_keeps_the_recording(tmp_path: Path) -> None:
    site = Site(script=drop_words(2, "trzy "), failing={1})

    result = record(tmp_path, site, Redo.LINE)

    assert len(site.uploads) == 2
    assert result.incomplete == ("part-2",)
    assert result.recording.read_bytes() == (tmp_path / "out" / "doc.take1.mp3").read_bytes()


def test_redo_without_a_pause_to_cut_in_is_left_out(tmp_path: Path) -> None:
    site = Site(script=drop_words(2, "trzy "), loud_pauses={0})

    result = record(tmp_path, site, Redo.LINE)

    assert len(site.uploads) == 2
    assert result.incomplete == ("part-2",)
    assert result.recording.read_bytes() == (tmp_path / "out" / "doc.take1.mp3").read_bytes()


def test_redo_that_cannot_be_decoded_keeps_the_recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(recording: Path) -> array[int]:
        message: str = f"cannot decode {recording.name}"
        raise OSError(message)

    monkeypatch.setattr(redo, "mono_pcm", broken)
    site = Site(script=drop_words(2, "trzy "))

    result = record(tmp_path, site, Redo.LINE)

    assert result.incomplete == ("part-2",)
    assert result.recording.read_bytes() == (tmp_path / "out" / "doc.take1.mp3").read_bytes()


def test_page_call_hanging_into_the_deadline_keeps_the_speech_and_reads_only_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def script(take: int, parts: list[str]) -> list[str]:
        return parts if take else parts[:3]

    monkeypatch.setattr(service, "POLL_S", 0.1)
    site = Site(script=script, stalls={0}, hangs={0})

    result = record(tmp_path, site, Redo.LINE, deadline_s=1.0)

    assert site.uploads[1] == list(PARTS[3:5])
    assert fills(result.recording) == [1, 2, 3, fill_of(1, 0), fill_of(1, 1)]
    assert result.incomplete == ()


def test_redo_failing_to_join_with_any_error_keeps_the_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(recording: Path) -> array[int]:
        message: str = f"no frames in {recording.name}"
        raise ValueError(message)

    monkeypatch.setattr(redo, "mono_pcm", broken)
    site = Site(script=drop_words(2, "trzy "))

    result = record(tmp_path, site, Redo.LINE)

    assert result.incomplete == ("part-2",)
    assert result.recording.read_bytes() == (tmp_path / "out" / "doc.take1.mp3").read_bytes()


def test_cancel_during_a_redo_stops_and_keeps_every_take(tmp_path: Path) -> None:
    cancel = Cancellation()

    def cancel_redo(take: int) -> None:
        if take:
            cancel.cancel()

    site = Site(script=drop_words(2, "trzy "), on_upload=cancel_redo)

    with pytest.raises(TtsCancelledError):
        record(tmp_path, site, Redo.LINE, cancel)

    assert fills(tmp_path / "out" / "doc.take1.mp3") == [1, 2, 3, 4, 5]
    assert not (tmp_path / "out" / "doc.mp3").exists()
