from __future__ import annotations

import json
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from anishift.services.audio.commands import CommandResult

type RunnerHandler = Callable[[tuple[str, ...], str], CommandResult]


@dataclass(slots=True)
class RecordingRunner:
    handler: RunnerHandler
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: object | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        self.calls.append((command, operation))
        return self.handler(command, operation)


def command_result(
    command: tuple[str, ...],
    *,
    stdout: str = "",
    stderr: str = "",
) -> CommandResult:
    return CommandResult(command=command, stdout=stdout, stderr=stderr, returncode=0)


def probe_payload(  # noqa: PLR0913
    *,
    codec: str = "pcm_s16le",
    sample_rate: int = 48_000,
    channels: int = 1,
    layout: str = "mono",
    duration: str | None = "1.25",
    format_name: str = "wav",
    bit_rate: str | None = "768000",
) -> str:
    stream: dict[str, object] = {
        "codec_type": "audio",
        "codec_name": codec,
        "sample_rate": str(sample_rate),
        "channels": channels,
        "channel_layout": layout,
    }
    if duration is not None:
        stream["duration"] = duration
    if bit_rate is not None:
        stream["bit_rate"] = bit_rate
    return json.dumps(
        {
            "streams": [stream],
            "format": {"format_name": format_name, "duration": duration},
        },
    )


def write_wav(  # noqa: PLR0913
    path: Path,
    *,
    frames: int,
    sample_rate: int = 48_000,
    channels: int = 1,
    sample_width: int = 2,
    sample: bytes = b"\x01\x00",
) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(sample_width)
        stream.setframerate(sample_rate)
        stream.writeframes(sample * frames * channels)
