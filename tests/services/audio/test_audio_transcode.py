from __future__ import annotations

import json
import threading
from pathlib import Path

from anishift.services.audio import AudioCodecProfile, AudioConfig, AudioTranscodeService
from anishift.services.audio.commands import CommandResult


class _Runner:
    def __init__(self, source: Path, destination: Path) -> None:
        self.source: Path = source
        self.destination: Path = destination
        self.operations: list[str] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
    ) -> CommandResult:
        assert timeout_s == 30.0
        assert cancel is not None
        self.operations.append(operation)
        if operation == "transcode_audio":
            Path(command[-1]).write_bytes(b"encoded")
            return CommandResult(command, "", "", 0)
        is_output: bool = Path(command[-1]) != self.source
        payload = _probe_payload(codec="eac3" if is_output else "aac", format_="eac3" if is_output else "mp4")
        return CommandResult(command, payload, "", 0)


def _probe_payload(*, codec: str, format_: str) -> str:
    return json.dumps(
        {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": codec,
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                    "duration": "10.000",
                }
            ],
            "format": {"format_name": format_, "duration": "10.000"},
        }
    )


def test_transcode_service_validates_and_commits_configured_profile(tmp_path: Path) -> None:
    source = tmp_path / "source.m4a"
    source.write_bytes(b"source")
    destination = tmp_path / "result.eac3"
    runner = _Runner(source, destination)
    service = AudioTranscodeService(
        AudioConfig(codec_profile=AudioCodecProfile.EAC3),
        runner=runner,
        ffmpeg=Path("ffmpeg"),
        ffprobe=Path("ffprobe"),
    )

    result: Path = service.transcode(source, destination, cancel=threading.Event())

    assert result == destination
    assert result.read_bytes() == b"encoded"
    assert runner.operations == ["probe", "transcode_audio", "probe"]
