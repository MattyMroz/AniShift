from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.errors import ErrorCode, UnsupportedMediaError
from anishift.services.media import probe
from anishift.services.media._process import (
    ProcessExecutionError,
    ProcessFailureReason,
    SubprocessRunner,
)
from anishift.services.media.mkv import parse_mkv_catalog
from anishift.services.media.mp4 import parse_mp4_catalog
from anishift.services.media.probe import DefaultMediaProbe
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind


def _mkv_payload() -> str:
    return json.dumps(
        {
            "container": {
                "recognized": True,
                "supported": True,
                "properties": {"duration": 2_000_000_000},
            },
            "tracks": [
                {
                    "id": 0,
                    "type": "video",
                    "properties": {"codec_id": "V_MPEG4/ISO/AVC", "language": "und"},
                },
                {
                    "id": 1,
                    "type": "audio",
                    "properties": {
                        "codec_id": "A_AAC",
                        "language": "jpn",
                        "track_name": "Main",
                        "default_track": True,
                    },
                },
                {
                    "id": 2,
                    "type": "subtitles",
                    "properties": {
                        "codec_id": "S_TEXT/UTF8",
                        "language": "pol",
                        "forced_track": True,
                    },
                },
            ],
            "attachments": [{"file_name": "font.ttf"}],
        }
    )


def _mp4_payload() -> str:
    return json.dumps(
        {
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264", "tags": {}},
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "tags": {"language": "jpn", "title": "Main"},
                    "disposition": {"default": 1},
                },
                {
                    "index": 2,
                    "codec_type": "subtitles",
                    "codec_name": "mov_text",
                    "codec_tag_string": "tx3g",
                    "tags": {"language": "pol"},
                    "disposition": {"forced": 1},
                },
            ],
            "format": {"duration": "2.000000"},
        }
    )


def _neutral_tracks(catalog: MediaCatalog) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            track.track_id,
            track.kind,
            track.language,
            track.name,
            track.is_default,
            track.is_forced,
            track.subtitle_format,
        )
        for track in catalog.tracks
    )


def test_mkv_and_mp4_map_the_same_material_to_neutral_tracks() -> None:
    mkv = parse_mkv_catalog(Path("episode.mkv"), _mkv_payload())
    mp4 = parse_mp4_catalog(Path("episode.mp4"), _mp4_payload())
    assert mkv.container is ContainerKind.MKV
    assert mp4.container is ContainerKind.MP4
    assert mkv.duration_us == mp4.duration_us == 2_000_000
    assert _neutral_tracks(mkv) == _neutral_tracks(mp4)
    assert mkv.attachments == ("font.ttf",)
    assert mp4.attachments == ()


def test_missing_or_und_language_maps_to_none() -> None:
    mkv = parse_mkv_catalog(Path("episode.mkv"), _mkv_payload())
    mp4 = parse_mp4_catalog(Path("episode.mp4"), _mp4_payload())
    assert mkv.tracks[0].language is None
    assert mp4.tracks[0].language is None


def test_default_probe_forwards_cancel_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, CancellationToken, float]] = []
    expected = MediaCatalog(Path("episode.mkv"), ContainerKind.MKV, 0, ())

    def fake_identify(
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
        runner: object,
    ) -> MediaCatalog:
        calls.append((path, cancel, timeout_s))
        return expected

    monkeypatch.setattr(probe, "identify_mkv", fake_identify)
    token = NeverCancelledToken()
    result = DefaultMediaProbe().identify(Path("episode.mkv"), cancel=token, timeout_s=12.5)
    assert result is expected
    assert calls == [(Path("episode.mkv"), token, 12.5)]


def test_default_probe_rejects_unsupported_suffix() -> None:
    with pytest.raises(UnsupportedMediaError) as raised:
        DefaultMediaProbe().identify(
            Path("episode.avi"),
            cancel=NeverCancelledToken(),
            timeout_s=1.0,
        )
    assert raised.value.context.code is ErrorCode.MEDIA_UNSUPPORTED


class _CancelsAfterFirstPoll:
    def __init__(self) -> None:
        self.checks: int = 0

    def is_cancelled(self) -> bool:
        self.checks += 1
        return self.checks > 1

    def raise_if_cancelled(self) -> None:
        return None


def test_subprocess_runner_terminates_on_cancel() -> None:
    command = (sys.executable, "-c", "import time; time.sleep(5)")
    with pytest.raises(ProcessExecutionError) as raised:
        SubprocessRunner().run(command, cancel=_CancelsAfterFirstPoll(), timeout_s=2.0)
    assert raised.value.reason is ProcessFailureReason.CANCELLED


def test_subprocess_runner_terminates_on_timeout() -> None:
    command = (sys.executable, "-c", "import time; time.sleep(5)")
    with pytest.raises(ProcessExecutionError) as raised:
        SubprocessRunner().run(command, cancel=NeverCancelledToken(), timeout_s=0.01)
    assert raised.value.reason is ProcessFailureReason.TIMED_OUT


def test_media_track_rejects_subtitle_format_on_audio() -> None:
    with pytest.raises(ValueError, match="Only subtitle"):
        MediaTrack(
            track_id=1,
            kind=MediaTrackKind.AUDIO,
            codec_id="aac",
            language=None,
            name=None,
            is_default=False,
            is_forced=False,
            subtitle_format="srt",
        )
