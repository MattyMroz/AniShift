from __future__ import annotations

import io
import json

import pytest
from elevenreader_fakes import FRAME_BYTES, FRAME_MS, audio_frame, mp3_frames

from anishift.services.tts.engines.elevenreader.recorder import StreamRecorder

pytestmark = pytest.mark.unit

FIRST = "The quick brown fox jumps over"
CONFIG = json.dumps({"type": "config"})


def _recorder() -> tuple[StreamRecorder, io.BytesIO]:
    output: io.BytesIO = io.BytesIO()
    return StreamRecorder(output), output


def test_on_frame_audio_with_alignment_writes_audio_and_timings() -> None:
    recorder, output = _recorder()

    recorder.on_frame(audio_frame("Ab", frames=3))

    assert output.getvalue() == mp3_frames(3)
    assert recorder.audio_bytes == 3 * FRAME_BYTES
    assert recorder.chars == 2
    assert recorder.chunks[0].chars == ("A", "b")
    assert recorder.chunks[0].starts_ms == (0.0, 10.0)
    assert recorder.chunks[0].offset_ms == 0.0


def test_on_frame_second_chunk_offset_is_first_chunk_duration() -> None:
    recorder, _ = _recorder()

    recorder.on_frame(audio_frame("Ab", frames=3, fill=1))
    recorder.on_frame(audio_frame("Cd", frames=2, fill=2))

    assert recorder.chunks[1].offset_ms == pytest.approx(3 * FRAME_MS)


def test_on_frame_large_duplicate_chunk_is_skipped() -> None:
    recorder, _ = _recorder()
    frame: str = audio_frame("Ab", frames=20)

    recorder.on_frame(frame)
    recorder.on_frame(frame)

    assert recorder.audio_bytes == 20 * FRAME_BYTES
    assert recorder.chars == 2


def test_on_frame_small_duplicate_chunk_is_kept() -> None:
    recorder, _ = _recorder()
    frame: str = audio_frame("", frames=2)

    recorder.on_frame(frame)
    recorder.on_frame(frame)

    assert recorder.audio_bytes == 4 * FRAME_BYTES


def test_on_frame_without_alignment_keeps_audio_and_advances_offset() -> None:
    recorder, _ = _recorder()

    recorder.on_frame(audio_frame("", frames=2))
    recorder.on_frame(audio_frame("Xy", frames=1))

    assert recorder.chars == 2
    assert len(recorder.chunks) == 1
    assert recorder.chunks[0].offset_ms == pytest.approx(2 * FRAME_MS)


def test_on_frame_normalized_alignment_is_used_when_alignment_missing() -> None:
    recorder, _ = _recorder()

    recorder.on_frame(audio_frame("Ab", frames=1, key="normalizedAlignment"))

    assert recorder.chars == 2


def test_on_frame_partial_repeat_after_reconnect_is_trimmed_with_audio() -> None:
    recorder, _ = _recorder()
    recorder.on_frame(audio_frame(FIRST, frames=12, fill=1))

    recorder.on_frame(CONFIG)
    recorder.on_frame(audio_frame("brown fox jumps over the lazy dog", frames=12, fill=2))

    assert recorder.chars == len(FIRST) + len(" the lazy dog")
    assert "".join(recorder.chunks[-1].chars) == " the lazy dog"
    assert recorder.chunks[-1].starts_ms[0] == pytest.approx(0.0)
    assert recorder.audio_bytes == 12 * FRAME_BYTES + 4 * FRAME_BYTES


def test_on_frame_full_repeat_after_reconnect_is_skipped() -> None:
    recorder, _ = _recorder()
    recorder.on_frame(audio_frame(FIRST, frames=12, fill=1))

    recorder.on_frame(CONFIG)
    recorder.on_frame(audio_frame("fox jumps over", frames=5, fill=2))

    assert recorder.chars == len(FIRST)
    assert recorder.audio_bytes == 12 * FRAME_BYTES


def test_on_frame_text_without_reconnect_is_never_trimmed() -> None:
    recorder, _ = _recorder()
    recorder.on_frame(audio_frame(FIRST, frames=12, fill=1))

    recorder.on_frame(audio_frame("brown fox jumps over", frames=5, fill=2))

    assert recorder.chars == len(FIRST) + len("brown fox jumps over")


@pytest.mark.parametrize("payload", [b"binary", "not json", "[1, 2]", json.dumps({"audio": "!!!"}), json.dumps({})])
def test_on_frame_unusable_payload_writes_nothing(payload: str | bytes) -> None:
    recorder, output = _recorder()

    recorder.on_frame(payload)

    assert output.getvalue() == b""
    assert recorder.chars == 0


@pytest.mark.parametrize(("payload", "expected"), [({"listening_speed": 1}, 1.0), ({"listening_speed": 3.0}, 3.0)])
def test_on_sent_listening_speed_is_tracked(payload: dict[str, object], expected: float) -> None:
    recorder, _ = _recorder()

    recorder.on_sent(json.dumps(payload))

    assert recorder.listening_speed == expected


@pytest.mark.parametrize("payload", ["{}", json.dumps({"listening_speed": True}), "nope", b"\x00"])
def test_on_sent_without_speed_keeps_none(payload: str | bytes) -> None:
    recorder, _ = _recorder()

    recorder.on_sent(payload)

    assert recorder.listening_speed is None


def test_stop_later_frames_are_ignored() -> None:
    recorder, output = _recorder()

    recorder.stop()
    recorder.on_frame(audio_frame("Ab", frames=1))
    recorder.on_sent(json.dumps({"listening_speed": 3.0}))

    assert output.getvalue() == b""
    assert recorder.listening_speed is None
