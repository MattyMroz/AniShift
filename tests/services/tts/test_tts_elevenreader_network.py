from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from anishift.services.tts import DocumentPart, DocumentSynthesisRequest, TtsCancellation, TtsConfig
from anishift.services.tts.engines.elevenreader import VOICES, ElevenReaderTtsEngine
from anishift.utils.mp3_frames import frames_duration_ms

pytestmark = [
    pytest.mark.integration,
    pytest.mark.network,
    pytest.mark.skipif(os.environ.get("ANISHIFT_ELEVENREADER_LIVE") != "1", reason="set ANISHIFT_ELEVENREADER_LIVE=1"),
]

PROFILE_ROOT = Path(__file__).resolve().parents[3] / "config" / "elevenreader"
TEXTS = ("Dzień dobry.", "To jest krótki test lektora.", "Do zobaczenia!")


async def _record(voice: str, recording: Path) -> tuple[int, float]:
    engine = ElevenReaderTtsEngine(
        TtsConfig(
            engine_id="elevenreader",
            provider_model_id="eleven_v4",
            voice_id=voice,
            max_concurrency=1,
            queue_capacity=2,
            elevenreader_profile_root=PROFILE_ROOT,
        ),
    )
    request = DocumentSynthesisRequest(
        request_id="live:document:0",
        parts=tuple(DocumentPart(request_id=f"line-{index}", text=text) for index, text in enumerate(TEXTS)),
        voice_id=voice,
        provider_model_id="eleven_v4",
        options={},
        recording=recording,
        deadline_s=600.0,
    )
    try:
        result = await engine.synthesize_document(request, cancel=TtsCancellation())
    finally:
        await engine.close()
    return len(result.parts), result.parts[-1].end_ms


@pytest.mark.parametrize("voice", list(VOICES))
def test_synthesize_document_live_account_records_three_parts(tmp_path: Path, voice: str) -> None:
    recording: Path = tmp_path / "recording.mp3"

    parts, last_end_ms = asyncio.run(_record(voice, recording))

    assert parts == len(TEXTS)
    assert frames_duration_ms(recording.read_bytes()) >= last_end_ms
