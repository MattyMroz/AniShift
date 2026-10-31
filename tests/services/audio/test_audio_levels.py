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


@pytest.mark.unit
def test_speech_bounds_tone_between_silence_returns_tone_frames() -> None:
    pcm = array("h", [0] * 480) + _tone(8_000, 800, 16_000) + array("h", [0] * 320)

    assert speech_bounds(frame_levels(pcm, 16_000), -45.0) == (3, 7)


@pytest.mark.unit
def test_speech_bounds_silence_returns_none() -> None:
    assert speech_bounds(frame_levels(array("h", [3] * 1_600), 16_000), -45.0) is None
