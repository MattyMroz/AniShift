from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

from anishift.application.tts_clips import FfmpegClipService
from anishift.paths import elevenreader_dir
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import SubprocessRunner
from anishift.services.tts import (
    AudioFormat,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchStatus,
    SpeechRequest,
    SpeechRequestProgress,
    SpeechRetryProgress,
    TtsConfig,
    TtsService,
)
from anishift.services.tts.engines.elevenreader import MAX_PARALLEL_DOCUMENTS, VOICES
from anishift.services.tts.engines.elevenreader.api_backend import (
    ReaderPage,
    _in_window,
    _titled,
    clean_account,
    load_cleanup,
    require_signed_in,
    save_cleanup,
)
from anishift.services.tts.engines.elevenreader.browser import ChromeSession
from anishift.services.tts.engines.elevenreader.constants import DOCUMENT_NAME, READS_URL, USER_CONFIG_URL
from anishift.services.tts.engines.elevenreader.types import AccountCleanup, DocumentTrace, UploadedRead

pytestmark = [
    pytest.mark.integration,
    pytest.mark.network,
    pytest.mark.skipif(os.environ.get("ANISHIFT_ELEVENREADER_LIVE") != "1", reason="set ANISHIFT_ELEVENREADER_LIVE=1"),
]

TEXTS = ("Dzień dobry.", "To jest krótki test lektora.", "Do zobaczenia!")
_EPISODE_CHARS = 8_000
_LOG_KEYS = frozenset({"message", "chars", "parts", "elapsed_ms", "active", "received_chars", "code", "step"})
_VOCABULARY = (
    "dom rzeka zielony szybko kot miasto wieczorem przyjaciel drzewo słońce pociąg książka spokojnie jutro las okno "
    "deszcz mały stary wiatr droga morze góra chleb muzyka światło ciepły cichy nagle razem most ogród list pies lato "
    "zima noc dzień rano długi jasny ptak kamień woda obłok stół lampa brat"
)


class _Progress:
    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        del state

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        del update

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        del update


def _clips() -> FfmpegClipService:
    ffmpeg: Path | None = resolve_binary(Binary.FFMPEG)
    ffprobe: Path | None = resolve_binary(Binary.FFPROBE)
    if ffmpeg is None or ffprobe is None:
        pytest.skip("FFmpeg is not available")
    return FfmpegClipService(
        cancel=threading.Event(),
        runner=SubprocessRunner(),
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        timeout_s=120.0,
        recording_timeout_s=600.0,
    )


def _wav(path: Path) -> tuple[int, int, int]:
    with wave.open(str(path), "rb") as stream:
        return stream.getframerate(), stream.getnchannels(), stream.getnframes()


@pytest.mark.parametrize("voice", list(VOICES))
def test_tts_service_live_document_commits_three_validated_clips(tmp_path: Path, voice: str) -> None:
    clips: FfmpegClipService = _clips()
    config = TtsConfig(
        engine_id="elevenreader",
        provider_model_id="eleven_v4",
        voice_id=voice,
        max_concurrency=1,
        queue_capacity=2,
        max_retries=0,
        request_timeout_s=600.0,
        scheduler_timeout_enabled=False,
        shutdown_deadline_s=15.0,
        elevenreader_profile_root=elevenreader_dir(),
    )
    batch = SpeechBatch(
        scope_id="live",
        batch_rank=0,
        requests=tuple(SpeechRequest(f"line-{index}", text, index) for index, text in enumerate(TEXTS)),
    )

    with TtsService(config, resume_root=tmp_path / "tts", validator=clips, splitter=clips) as service:
        result = service.synthesize(batch, callbacks=_Progress())

    assert result.status is SpeechBatchStatus.COMPLETED, result.failure
    committed = [item.speech_clip for item in result.requests]
    assert [clip.request_id for clip in committed if clip is not None] == ["line-0", "line-1", "line-2"]
    assert all(clip is not None and clip.format is AudioFormat.WAV for clip in committed)
    wavs: list[tuple[int, int, int]] = [_wav(clip.path) for clip in committed if clip is not None]
    assert [(rate, channels) for rate, channels, _ in wavs] == [(48_000, 1)] * len(TEXTS)
    assert all(frames > 0 for _, _, frames in wavs)


@dataclass(frozen=True, slots=True)
class _Recorded:
    status: SpeechBatchStatus
    started: float
    finished: float
    retries: int
    speech_s: float
    failure: str


class _RetryCount(_Progress):
    def __init__(self) -> None:
        self.retries: list[str] = []

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        self.retries.append(update.error_code)


def _episode(rng: random.Random, chars: int) -> tuple[str, ...]:
    words_in: list[str] = _VOCABULARY.split()
    lines: list[str] = []
    while sum(len(line) + len("\n\n…\n\n") for line in lines) < chars:
        words: list[str] = [rng.choice(words_in) for _ in range(rng.randint(8, 14))]
        lines.append(" ".join(words).capitalize() + ".")
    return tuple(lines)


def _record_episode(
    index: int, texts: tuple[str, ...], documents: int, root: Path, clips: FfmpegClipService
) -> _Recorded:
    config = TtsConfig(
        engine_id="elevenreader",
        provider_model_id="eleven_v4",
        voice_id="fronczewski",
        max_concurrency=documents,
        queue_capacity=2 * documents,
        max_retries=0,
        request_timeout_s=3600.0,
        scheduler_timeout_enabled=False,
        shutdown_deadline_s=15.0,
        elevenreader_profile_root=elevenreader_dir(),
    )
    batch = SpeechBatch(
        scope_id=f"parallel-{index}",
        batch_rank=0,
        requests=tuple(SpeechRequest(f"line-{line}", text, line) for line, text in enumerate(texts)),
    )
    progress = _RetryCount()
    started: float = time.monotonic()
    with TtsService(config, resume_root=root / f"episode-{index}", validator=clips, splitter=clips) as service:
        result = service.synthesize(batch, callbacks=progress)
    finished: float = time.monotonic()
    clips_s: list[float] = [
        frames / rate
        for item in result.requests
        if item.speech_clip is not None
        for rate, _, frames in (_wav(item.speech_clip.path),)
    ]
    failure: str = "" if result.failure is None else f"{result.failure.code.value}: {result.failure.message}"
    return _Recorded(result.status, started, finished, len(progress.retries), sum(clips_s), failure)


async def _account(root: Path) -> tuple[object, object, frozenset[str]]:
    session = ChromeSession(root, headless=True)
    await session.start()
    try:
        page: ReaderPage = await session.new_page()
        await require_signed_in(page, root)
        token: str | None = page.token
        assert token
        config: dict[str, object] = await page.get_json(USER_CONFIG_URL, token, action="read_account")
        listing: dict[str, object] = await page.get_json(READS_URL, token, action="list_reads")
        reads: object = listing.get("reads")
        assert isinstance(reads, list)
        imports: frozenset[str] = frozenset(
            str(read.get("read_id"))
            for read in reads
            if isinstance(read, dict)
            and read.get("from_user_import") is True
            and read.get("original_file_type") == "text/plain"
        )
        await page.close()
        return config.get("default_voice_id"), config.get("playback_speed_rate"), imports
    finally:
        await session.close()


@pytest.mark.parametrize("documents", [1, MAX_PARALLEL_DOCUMENTS])
def test_tts_services_on_own_threads_live_record_documents_together(tmp_path: Path, documents: int) -> None:
    clips: list[FfmpegClipService] = [_clips() for _ in range(documents)]
    root: Path = elevenreader_dir()
    before = asyncio.run(_account(root))
    rng = random.Random()  # noqa: S311 - distinct filler text, not a secret
    episodes: list[tuple[str, ...]] = [_episode(rng, _EPISODE_CHARS) for _ in range(documents)]
    captured: list[dict[str, object]] = []
    handler_id: int = loguru_logger.add(
        lambda message: captured.append(
            {"at": message.record["time"].timestamp(), "message": message.record["message"], **message.record["extra"]}
        ),
        level="INFO",
        filter="anishift.services.tts",
    )
    started: float = time.monotonic()
    began: float = time.time()
    try:
        with ThreadPoolExecutor(max_workers=documents) as pool:
            recorded: list[_Recorded] = list(
                pool.map(
                    lambda index: _record_episode(index, episodes[index], documents, tmp_path, clips[index]),
                    range(documents),
                )
            )
    finally:
        loguru_logger.remove(handler_id)
    wall_s: float = time.monotonic() - started
    after = asyncio.run(_account(root))
    report: dict[str, object] = {
        "documents": documents,
        "wall_s": round(wall_s, 1),
        "speech_s": [round(item.speech_s, 1) for item in recorded],
        "episode_s": [round(item.finished - item.started, 1) for item in recorded],
        "speech_per_wall": round(sum(item.speech_s for item in recorded) / wall_s, 2),
        "retries": [item.retries for item in recorded],
        "failures": [item.failure for item in recorded],
        "account_kept": after[:2] == before[:2],
        "new_imports": len(after[2] - before[2]),
        "log": [
            {"at": round(float(str(entry["at"])) - began, 1)}
            | {key: value for key, value in entry.items() if key in _LOG_KEYS}
            for entry in captured
        ],
    }
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")

    assert after[:2] == before[:2]
    assert after[2] <= before[2]
    assert not load_cleanup(root).pending
    assert all(item.status is SpeechBatchStatus.COMPLETED for item in recorded), report
    assert all(item.retries == 0 for item in recorded), report


def _listed(listing: dict[str, object], read_id: str) -> object:
    reads: object = listing.get("reads")
    assert isinstance(reads, list)
    return next((read for read in reads if isinstance(read, dict) and str(read.get("read_id")) == read_id), None)


async def _leave_clean(page: ReaderPage | None, cleanup: AccountCleanup, uploaded: UploadedRead | None) -> None:
    if page is None:
        return
    known: list[str | None] = [trace.read_id for trace in cleanup.documents]
    if uploaded is not None and uploaded.read_id not in known:
        cleanup.documents.append(
            DocumentTrace(pressed_at=0.0, listed_by=0.0, titles=frozenset(), read_id=uploaded.read_id)
        )
    await clean_account(page, cleanup, restore=True)
    await page.close()


async def _orphan_lookup(root: Path, document: Path) -> tuple[object, bool, object, bool]:
    cleanup: AccountCleanup = load_cleanup(root)

    def save() -> None:
        save_cleanup(root, cleanup)

    session = ChromeSession(root, headless=True)
    page: ReaderPage | None = None
    uploaded: UploadedRead | None = None
    await session.start()
    try:
        page = await session.new_page()
        await require_signed_in(page, root)
        uploaded = await page.upload(document, cleanup, save)
        listed: object = _listed(await page.get_json(READS_URL, uploaded.token, action="list_reads"), uploaded.read_id)
        trace: DocumentTrace = cleanup.documents[-1]
        recognised: bool = isinstance(listed, dict) and _in_window(listed, trace) and _titled(listed, trace)
        cleanup.swap(trace, replace(trace, read_id=None))
        await clean_account(page, cleanup, restore=True)
        settled: bool = not cleanup.pending
        left: object = _listed(await page.get_json(READS_URL, uploaded.token, action="list_reads"), uploaded.read_id)
        return listed, recognised, left, settled
    finally:
        await _leave_clean(page, cleanup, uploaded)
        save()
        await session.close()


def test_reads_listing_live_account_finds_and_deletes_document_without_known_id(tmp_path: Path) -> None:
    root: Path = elevenreader_dir()
    document: Path = tmp_path / DOCUMENT_NAME
    document.write_text("Test listy dokumentów! Drugie zdanie.\n\n…\n\nDruga kwestia.\n", encoding="utf-8")

    listed, recognised, left, settled = asyncio.run(_orphan_lookup(root, document))

    assert isinstance(listed, dict)
    assert recognised, {key: listed.get(key) for key in ("title", "added_at_unix", "original_file_type")}
    assert settled
    assert left is None
    assert not load_cleanup(root).pending
