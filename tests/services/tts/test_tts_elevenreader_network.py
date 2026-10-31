from __future__ import annotations

import asyncio
import os
import threading
import wave
from pathlib import Path

import pytest

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
from anishift.services.tts.engines.elevenreader import VOICES
from anishift.services.tts.engines.elevenreader.api_backend import (
    _DOCUMENT_TITLES,
    ReaderPage,
    clean_account,
    load_cleanup,
    require_signed_in,
    save_cleanup,
)
from anishift.services.tts.engines.elevenreader.browser import ChromeSession
from anishift.services.tts.engines.elevenreader.constants import DOCUMENT_NAME, READS_URL
from anishift.services.tts.engines.elevenreader.types import AccountCleanup, UploadedRead

pytestmark = [
    pytest.mark.integration,
    pytest.mark.network,
    pytest.mark.skipif(os.environ.get("ANISHIFT_ELEVENREADER_LIVE") != "1", reason="set ANISHIFT_ELEVENREADER_LIVE=1"),
]

TEXTS = ("Dzień dobry.", "To jest krótki test lektora.", "Do zobaczenia!")


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


def _listed(listing: dict[str, object], read_id: str) -> object:
    reads: object = listing.get("reads")
    assert isinstance(reads, list)
    return next((read for read in reads if isinstance(read, dict) and str(read.get("read_id")) == read_id), None)


async def _leave_clean(page: ReaderPage | None, cleanup: AccountCleanup, uploaded: UploadedRead | None) -> None:
    if page is None:
        return
    if uploaded is not None and uploaded.read_id not in cleanup.read_ids:
        cleanup.read_ids.append(uploaded.read_id)
    await clean_account(page, cleanup)
    await page.close()


async def _orphan_lookup(root: Path, document: Path) -> tuple[object, object, bool]:
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
        cleanup.read_ids.remove(uploaded.read_id)
        cleanup.orphan_visible_at = 0.0
        await clean_account(page, cleanup)
        settled: bool = not cleanup.pending
        left: object = _listed(await page.get_json(READS_URL, uploaded.token, action="list_reads"), uploaded.read_id)
        return listed, left, settled
    finally:
        await _leave_clean(page, cleanup, uploaded)
        save()
        await session.close()


def test_reads_listing_live_account_finds_and_deletes_document_without_known_id(tmp_path: Path) -> None:
    root: Path = elevenreader_dir()
    document: Path = tmp_path / DOCUMENT_NAME
    document.write_text("Test listy dokumentów.\n", encoding="utf-8")

    listed, left, settled = asyncio.run(_orphan_lookup(root, document))

    assert isinstance(listed, dict)
    assert listed.get("title") in _DOCUMENT_TITLES
    assert settled
    assert left is None
    assert not load_cleanup(root).pending
