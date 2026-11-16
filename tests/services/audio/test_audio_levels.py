from __future__ import annotations

import math
from array import array

import pytest

from anishift.services.audio.levels import frame_levels, speech_bounds


def _tone(amplitude: int, count: int, sample_rate: int) -> array[int]:
    return array("h", (round(amplitude * math.sin(2 * math.pi * 1000 * n / sample_rate)) for n in range(count)))


@pytest.mark.unit
def test_frame_levels_sine_reports_rms_dbfs() -> None:
    levels = frame_levels(_tone(16_384, 1_600, 16_000), 16_000)

    assert len(levels) == 10
    assert all(level == pytest.approx(20 * math.log10(0.5 / math.sqrt(2)), abs=0.1) for level in levels)


@pytest.mark.unit
def test_frame_levels_partial_trailing_frame_is_dropped() -> None:
    assert len(frame_levels(array("h", [0] * 1_200), 48_000)) == 2


@pytest.mark.unit
def test_frame_levels_digital_silence_stays_finite() -> None:
    assert frame_levels(array("h", [0] * 160), 16_000) == [pytest.approx(-120.0)]


@pytest.mark.unit
def test_frame_levels_rate_without_whole_frames_raises() -> None:
    with pytest.raises(ValueError, match="10 ms"):
        frame_levels(array("h", [0] * 441), 22_050)


def _bounds(levels: list[float]) -> tuple[int, int] | None:
    return speech_bounds(levels, -45.0, click_ms=50.0, pause_ms=80.0)


def _frames(*sounds: tuple[int, int]) -> list[float]:
    return [-10.0 if any(start <= index < end for start, end in sounds) else -90.0 for index in range(100)]


@pytest.mark.unit
def test_speech_bounds_tone_between_silence_returns_tone_frames() -> None:
    pcm = array("h", [0] * 480) + _tone(8_000, 800, 16_000) + array("h", [0] * 320)

    assert _bounds(frame_levels(pcm, 16_000)) == (3, 7)


@pytest.mark.unit
def test_speech_bounds_silence_returns_none() -> None:
    assert _bounds(frame_levels(array("h", [3] * 1_600), 16_000)) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sounds", "expected"),
    [
        (((10, 13), (30, 90)), (30, 89)),
        (((10, 20), (30, 90)), (10, 89)),
        (((10, 13), (17, 90)), (10, 89)),
        (((30, 80), (90, 93)), (30, 92)),
    ],
    ids=["click-before-pause-dropped", "word-before-pause-kept", "click-before-short-gap-kept", "stop-release-kept"],
)
def test_speech_bounds_start_past_a_click_before_a_pause(
    sounds: tuple[tuple[int, int], ...], expected: tuple[int, int]
) -> None:
    assert _bounds(_frames(*sounds)) == expected
