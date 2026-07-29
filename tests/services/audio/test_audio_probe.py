from __future__ import annotations

import json
from pathlib import Path

import pytest
from audio_test_helpers import RecordingRunner, command_result, probe_payload

from anishift.services.audio.commands import CommandResult
from anishift.services.audio.errors import AudioProbeError
from anishift.services.audio.probe import parse_probe_json, probe_audio


def test_parse_probe_json_selects_first_audio_and_rounds_duration() -> None:
    payload = json.dumps(
        {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                    "duration": "1.2345",
                    "bit_rate": "256000",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "opus",
                    "sample_rate": "48000",
                    "channels": 1,
                    "channel_layout": "mono",
                    "duration": "9",
                },
            ],
            "format": {"format_name": "mov,mp4,m4a", "duration": "10"},
        },
    )

    probe = parse_probe_json(Path("track.m4a"), payload)

    assert probe.codec_name == "aac"
    assert probe.format_name == "mov,mp4,m4a"
    assert probe.duration_ms == 1235
    assert probe.bit_rate == 256000
    assert probe.channel_layout == "stereo"


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"streams":[],"format":{"format_name":"wav","duration":"1"}}',
        probe_payload(duration=None),
        "not json",
    ],
)
def test_parse_probe_json_rejects_missing_audio_or_duration(payload: str) -> None:
    with pytest.raises(AudioProbeError):
        parse_probe_json(Path("bad.audio"), payload)


def test_probe_audio_rejects_zero_byte_before_process(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    path.touch()
    runner = RecordingRunner(lambda command, operation: command_result(command))

    with pytest.raises(AudioProbeError):
        probe_audio(
            path,
            ffprobe=Path("ffprobe"),
            runner=runner,
            timeout_s=1,
        )

    assert runner.calls == []


def test_probe_audio_uses_json_argument_list(tmp_path: Path) -> None:
    path = tmp_path / "voice clip.wav"
    path.write_bytes(b"audio")

    def handler(command: tuple[str, ...], operation: str) -> CommandResult:
        return command_result(command, stdout=probe_payload())

    runner = RecordingRunner(handler)

    probe_audio(
        path,
        ffprobe=Path("ffprobe.exe"),
        runner=runner,
        timeout_s=1,
    )

    command, operation = runner.calls[0]
    assert operation == "probe"
    assert command[:7] == (
        "ffprobe.exe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
    )
    assert command[-1] == str(path)
