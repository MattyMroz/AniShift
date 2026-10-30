from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from anishift.services.tts import TtsConfig, TtsProviderUnavailableError
from anishift.services.tts.engines.elevenreader import ElevenReaderTtsEngine
from anishift.services.tts.engines.elevenreader.types import LibraryState, PlayerState, UploadedRead

if TYPE_CHECKING:
    from collections.abc import Callable

    from anishift.services.tts.engines.elevenreader.browser import ChromeSession
    from anishift.services.tts.engines.elevenreader.recorder import StreamRecorder

FRONCZEWSKI_ID = "T5l58N8RNz5DKoClpKIJ"
ADAM_ID = "hIssydxXZ1WuDorjx6Ic"
TOKEN = "token-7f3c9e1d5b"  # noqa: S105
READ_ID = "u:readsecret42"
BREAK = '<break time="0.6s"/>'
FRAME_HEADER = bytes((0xFF, 0xFB, 0x90, 0x64))
FRAME_BYTES = 417
FRAME_MS = 1152 * 1000 / 44_100


def mp3_frames(count: int, *, fill: int = 0) -> bytes:
    frame: bytes = FRAME_HEADER + bytes([fill]) * (FRAME_BYTES - len(FRAME_HEADER))
    return frame * count


def audio_frame(
    chars: str,
    *,
    frames: int = 4,
    fill: int = 0,
    step_ms: float = 10.0,
    key: str = "alignment",
) -> str:
    payload: dict[str, object] = {"audio": base64.b64encode(mp3_frames(frames, fill=fill)).decode("ascii")}
    if chars:
        payload[key] = {
            "chars": list(chars),
            "charStartTimesMs": [index * step_ms for index in range(len(chars))],
            "charDurationsMs": [step_ms] * len(chars),
        }
    return json.dumps(payload)


def stream_frames(texts: tuple[str, ...]) -> list[str]:
    frames: list[str] = []
    for index, text in enumerate(texts):
        tail: str = f" {BREAK} … {BREAK} " if index < len(texts) - 1 else ' <break time="2s"/>'
        spoken: str = text.replace("[", "(").replace("]", ")")
        frames.append(audio_frame(spoken + tail, frames=22, fill=index + 1))
    return frames


def streamed_chars(texts: tuple[str, ...]) -> int:
    return sum(len(json.loads(frame)["alignment"]["chars"]) for frame in stream_frames(texts))


def tts_config(root: Path, *, voice_id: str = "fronczewski", model: str = "eleven_v4") -> TtsConfig:
    return TtsConfig(
        engine_id="elevenreader",
        provider_model_id=model,
        voice_id=voice_id,
        max_concurrency=1,
        queue_capacity=2,
        elevenreader_profile_root=root,
    )


@dataclass
class FakeSite:
    texts: tuple[str, ...] = ("Pierwsza kwestia.", "Druga kwestia.")
    library: LibraryState = LibraryState.READY
    account: dict[str, object] = field(
        default_factory=lambda: {"default_voice_id": "previous-voice", "playback_speed_rate": 1.5, "theme": "dark"},
    )
    ignore_voice: bool = False
    voice_in_url: bool = True
    listening_speed: float = 1.0
    frames: list[str] | None = None
    char_count: int | None = None
    send_audio: bool = True
    player_done: bool = False
    hang_on: str = ""
    failing: set[str] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    plays: int = 0
    sessions: list[FakeSession] = field(default_factory=list)
    pages: list[FakePage] = field(default_factory=list)

    def stream(self) -> list[str]:
        return stream_frames(self.texts) if self.frames is None else self.frames

    def count(self) -> int:
        if self.char_count is not None:
            return self.char_count
        return sum(len(json.loads(frame).get("alignment", {}).get("chars", [])) for frame in self.stream())


class FakePage:
    def __init__(self, site: FakeSite) -> None:
        self.site: FakeSite = site
        self.closed: bool = False
        self.watching: bool = False
        self._token: str | None = None
        self._recorder: StreamRecorder | None = None
        self._on_url: Callable[[str], None] | None = None

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def open_library(self) -> LibraryState:
        await self._step("open_library")
        if self.site.library is LibraryState.READY:
            self._token = TOKEN
        return self.site.library

    async def library_ready(self) -> bool:
        return self.site.library is LibraryState.READY

    async def upload(self, document: Path) -> UploadedRead:
        await self._step("upload")
        self.site.uploaded.append(document.read_text(encoding="utf-8"))
        return UploadedRead(read_id=READ_ID, char_count=self.site.count(), token=TOKEN)

    async def get_json(self, url: str, token: str, *, action: str) -> dict[str, object]:
        assert token == TOKEN
        await self._step(action)
        return dict(self.site.account)

    async def post_json(self, url: str, token: str, data: dict[str, object], *, action: str) -> None:
        assert token == TOKEN
        await self._step(action)
        updated: dict[str, object] = dict(data)
        if self.site.ignore_voice and action == "set_account":
            updated["default_voice_id"] = self.site.account["default_voice_id"]
        self.site.account = updated

    async def delete(self, url: str, token: str, *, action: str) -> None:
        assert token == TOKEN
        await self._step(action)
        self.site.deleted.append(url)

    async def open_document(self, read_id: str) -> None:
        assert read_id == READ_ID
        await self._step("open_document")

    async def press_play(self) -> None:
        await self._step("press_play")
        self.site.plays += 1
        if self._recorder is None or self._on_url is None or not self.site.send_audio:
            return
        voice: str = str(self.site.account.get("default_voice_id")) if self.site.voice_in_url else "other"
        self._on_url(f"wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{READ_ID}?voice_id={voice}")
        self._recorder.on_sent(json.dumps({"listening_speed": self.site.listening_speed}))
        for frame in self.site.stream():
            self._recorder.on_frame(frame)

    async def player_state(self) -> PlayerState:
        return PlayerState(value=100.0, length=100.0) if self.site.player_done else PlayerState(value=0.0, length=0.0)

    async def set_page_speed(self, speed: float) -> None:
        self.site.events.append("set_page_speed")

    async def check_page_speed(self, speed: float) -> None:
        self.site.events.append("check_page_speed")

    def watch_stream(self, recorder: StreamRecorder, on_url: Callable[[str], None]) -> None:
        self.watching = True
        self._recorder = recorder
        self._on_url = on_url

    def unwatch_stream(self) -> None:
        self.watching = False

    async def close(self) -> None:
        self.site.events.append("close_page")
        self.closed = True

    async def _step(self, action: str) -> None:
        self.site.events.append(action)
        if action in self.site.failing:
            message: str = f"fake {action} failed"
            raise TtsProviderUnavailableError(message)
        if action == self.site.hang_on:
            future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            await future


class FakeSession:
    def __init__(self, site: FakeSite) -> None:
        self.site: FakeSite = site
        self.started: bool = False
        self.closed: bool = False

    @property
    def alive(self) -> bool:
        return self.started and not self.closed

    async def start(self) -> None:
        self.site.events.append("start_browser")
        self.started = True

    async def new_page(self) -> FakePage:
        page: FakePage = FakePage(self.site)
        self.site.pages.append(page)
        return page

    async def close(self) -> None:
        self.site.events.append("close_browser")
        self.closed = True


def fake_engine(root: Path, site: FakeSite, *, voice_id: str = "fronczewski") -> ElevenReaderTtsEngine:
    def factory(profile_root: Path) -> ChromeSession:
        assert profile_root == root
        session: FakeSession = FakeSession(site)
        site.sessions.append(session)
        return cast("ChromeSession", session)

    return ElevenReaderTtsEngine(tts_config(root, voice_id=voice_id), browser_factory=factory)
