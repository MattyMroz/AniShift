import io
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from conftest import DATA_DIR

from anishift.errors import ErrorCode
from anishift.services.extraction import service
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import LegacyExtractionResult, MediaInfo, TrackSelection


def _info() -> MediaInfo:
    payload = (DATA_DIR / "youjo-senki-ii-01.json").read_text(encoding="utf-8")
    return service.parse_media_info(Path("source.mkv"), payload)


def test_parse_media_info_reads_real_identify_payload() -> None:
    info = _info()
    assert [(track.id, track.type, track.codec_id) for track in info.tracks] == [
        (0, "video", "V_MPEG4/ISO/AVC"),
        (1, "audio", "A_AAC"),
        (2, "subtitles", "S_TEXT/ASS"),
    ]
    assert info.tracks[1].language == "jpn"
    assert info.tracks[2].language == "pol"


def test_parse_media_info_reads_attachment_names() -> None:
    payload = json.dumps(
        {
            "container": {"recognized": True, "supported": True},
            "tracks": [],
            "attachments": [
                {"file_name": "OpenSans-Semibold.ttf"},
                {"file_name": "Trebuchet.otf"},
                {"content_type": "image/jpeg"},
            ],
        }
    )

    info = service.parse_media_info(Path("source.mkv"), payload)

    assert info.attachments == ("OpenSans-Semibold.ttf", "Trebuchet.otf")


def test_parse_media_info_without_attachments_reports_none() -> None:
    assert _info().attachments == ()


def test_parse_media_info_rejects_invalid_json() -> None:
    with pytest.raises(ExtractionError, match="identify JSON is invalid"):
        service.parse_media_info(Path("source.mkv"), "not json")


def test_parse_media_info_rejects_unrecognized_container() -> None:
    payload = json.dumps({"container": {"recognized": False, "supported": True}, "tracks": []})
    with pytest.raises(ExtractionError, match="not a supported Matroska file"):
        service.parse_media_info(Path("source.mkv"), payload)


def test_format_extension_maps_known_and_unknown_codecs() -> None:
    assert service.format_extension("S_TEXT/ASS") == "ass"
    assert service.format_extension("A_EAC3") == "ac3"
    assert service.format_extension("unknown") == "mkv"


def test_is_text_subtitle_codec_accepts_only_text_formats() -> None:
    assert service.is_text_subtitle_codec("S_TEXT/ASS") is True
    assert service.is_text_subtitle_codec("S_TEXT/SSA") is True
    assert service.is_text_subtitle_codec("S_TEXT/UTF8") is True
    assert service.is_text_subtitle_codec("S_HDMV/PGS") is False
    assert service.is_text_subtitle_codec("S_VOBSUB") is False


def test_progress_regex_parses_gui_mode_lines() -> None:
    match = service._RE_GUI_PROGRESS.match("#GUI#progress 42%\n")
    assert match is not None
    assert match.group(1) == "42"
    assert service._RE_GUI_PROGRESS.match("ordinary output") is None


class _FakeProcess:
    def __init__(self, output: list[str], returncode: int = 0) -> None:
        self.stdout: io.StringIO | _BlockingOutput = io.StringIO("".join(output))
        self.returncode = returncode
        self.terminated = False

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


class _BlockingOutput:
    def __init__(self, released: threading.Event) -> None:
        self._released = released

    def __iter__(self) -> _BlockingOutput:
        return self

    def __next__(self) -> str:
        self._released.wait()
        raise StopIteration

    def close(self) -> None:
        pass


class _BlockingProcess(_FakeProcess):
    def __init__(self) -> None:
        self._released = threading.Event()
        super().__init__([])
        self.stdout = _BlockingOutput(self._released)

    def terminate(self) -> None:
        super().terminate()
        self._released.set()

    def poll(self) -> int | None:
        return self.returncode if self._released.is_set() else None

    def wait(self, timeout: float | None = None) -> int:
        if not self._released.wait(timeout):
            assert timeout is not None
            raise subprocess.TimeoutExpired("mkvextract", timeout)
        return self.returncode


def test_extract_tracks_validates_missing_and_empty_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: _FakeProcess([]))
    with pytest.raises(ExtractionError, match="wrote no data"):
        service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path)


def test_extract_tracks_reports_progress_and_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_popen(command: list[str], **_: object) -> _FakeProcess:
        Path(command[-2].split(":", 1)[1]).write_bytes(b"audio")
        Path(command[-1].split(":", 1)[1]).write_bytes(b"subs")
        return _FakeProcess(["#GUI#progress 50%\n", "#GUI#progress 100%\n"])

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    progress: list[int] = []
    result = service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path, on_progress=progress.append)
    assert progress == [50, 100, 100]
    assert result.audio_path is not None
    assert result.audio_path.read_bytes() == b"audio"
    assert result.subtitle_path is not None
    assert result.subtitle_path.read_bytes() == b"subs"


def test_extract_tracks_cancel_removes_partial_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process: _BlockingProcess | None = None
    cancel = threading.Event()

    def fake_popen(command: list[str], **_: object) -> _BlockingProcess:
        nonlocal process
        Path(command[-2].split(":", 1)[1]).write_bytes(b"partial")
        process = _BlockingProcess()
        cancel.set()
        return process

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with pytest.raises(ExtractionError) as exc_info:
        service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path, cancel=cancel)
    assert exc_info.value.context.code is ErrorCode.CANCELLED
    assert process is not None
    assert process.terminated
    assert list(tmp_path.iterdir()) == []


def test_extract_tracks_cancel_terminates_process_during_blocked_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _BlockingProcess()
    cancel = threading.Event()
    result: list[ExtractionError] = []

    def fake_popen(*_: object, **__: object) -> _BlockingProcess:
        (tmp_path / "source.aac").write_bytes(b"partial")
        started.set()
        return process

    def run_extraction() -> None:
        try:
            service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path, cancel=cancel)
        except ExtractionError as exc:
            result.append(exc)

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    started = threading.Event()
    worker = threading.Thread(target=run_extraction)
    worker.start()
    assert started.wait(timeout=1)
    cancel.set()
    worker.join(timeout=2)

    assert worker.is_alive() is False
    assert process.terminated
    assert result
    assert result[0].context.code is ErrorCode.CANCELLED


def test_extract_tracks_with_no_selection_runs_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def never(*_: object, **__: object) -> _FakeProcess:
        raise AssertionError("Popen must not be called")

    monkeypatch.setattr(subprocess, "Popen", never)
    assert service.extract_tracks(_info(), TrackSelection(None, None, False), tmp_path).audio_path is None


class _StubbornProcess(_BlockingProcess):
    def __init__(self, *, output_finished: bool = False) -> None:
        super().__init__()
        self.killed: bool = False
        self.wait_timeouts: list[float | None] = []
        if output_finished:
            self.stdout = io.StringIO("")

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self._released.set()

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        return super().wait(timeout)


@pytest.mark.parametrize("output_finished", [False, True])
def test_extraction_deadline_kills_stubborn_child_and_cleans_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    output_finished: bool,
) -> None:
    process: _StubbornProcess = _StubbornProcess(output_finished=output_finished)

    def fake_popen(command: list[str], **_: object) -> _StubbornProcess:
        Path(command[-1].split(":", 1)[1]).write_bytes(b"partial")
        return process

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(service, "_SHUTDOWN_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with pytest.raises(ExtractionError) as captured:
        service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path, timeout_s=0.02)

    assert captured.value.context.code is ErrorCode.TIMEOUT
    assert process.terminated
    assert process.killed
    assert all(timeout is not None and timeout <= 0.02 for timeout in process.wait_timeouts)
    assert list(tmp_path.iterdir()) == []


def test_extraction_cancel_escalates_to_kill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process: _StubbornProcess = _StubbornProcess()
    cancel: threading.Event = threading.Event()

    def fake_popen(command: list[str], **_: object) -> _StubbornProcess:
        Path(command[-1].split(":", 1)[1]).write_bytes(b"partial")
        cancel.set()
        return process

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(service, "_SHUTDOWN_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with pytest.raises(ExtractionError) as captured:
        service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path, cancel=cancel)

    assert captured.value.context.code is ErrorCode.CANCELLED
    assert process.terminated
    assert process.killed
    assert list(tmp_path.iterdir()) == []


def test_extraction_observer_failure_stops_child_and_removes_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process: _StubbornProcess = _StubbornProcess()
    process.stdout = io.StringIO("#GUI#progress 12%\n")

    def fake_popen(command: list[str], **_: object) -> _StubbornProcess:
        Path(command[-1].split(":", 1)[1]).write_bytes(b"partial")
        return process

    def fail_progress(_: int) -> None:
        raise RuntimeError("observer failed")

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(service, "_SHUTDOWN_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with pytest.raises(RuntimeError, match="observer failed"):
        service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path, on_progress=fail_progress)

    assert process.terminated
    assert process.killed
    assert process.stdout.closed
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("returncode", "payload", "success"), [(1, b"valid", True), (1, b"", False), (2, b"valid", False)]
)
def test_extraction_accepts_only_valid_warning_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
    payload: bytes,
    success: bool,
) -> None:
    def fake_popen(command: list[str], **_: object) -> _FakeProcess:
        Path(command[-1].split(":", 1)[1]).write_bytes(payload)
        return _FakeProcess([], returncode=returncode)

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    if success:
        result: LegacyExtractionResult = service.extract_tracks(_info(), TrackSelection(None, 2, False), tmp_path)
        assert result.subtitle_path is not None
        assert result.subtitle_path.read_bytes() == payload
    else:
        with pytest.raises(ExtractionError):
            service.extract_tracks(_info(), TrackSelection(None, 2, False), tmp_path)
        assert list(tmp_path.iterdir()) == []


def test_extraction_preserves_existing_target(tmp_path: Path) -> None:
    target: Path = tmp_path / "source.ass"
    target.write_bytes(b"existing")

    with pytest.raises(ExtractionError, match="target already exists"):
        service.extract_tracks(_info(), TrackSelection(None, 2, False), tmp_path)

    assert target.read_bytes() == b"existing"


@pytest.mark.parametrize("close_stdout", [False, True])
def test_extraction_deadline_reaps_real_silent_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    close_stdout: bool,
) -> None:
    original_popen: type[subprocess.Popen[str]] = subprocess.Popen
    processes: list[subprocess.Popen[str]] = []
    script: str = "import time; time.sleep(10)"
    if close_stdout:
        script = "import os, time; os.close(1); time.sleep(10)"

    def start_child(command: list[str], **kwargs: Any) -> subprocess.Popen[str]:
        process: subprocess.Popen[str] = original_popen([sys.executable, "-c", script], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", start_child)

    with pytest.raises(ExtractionError) as captured:
        service.extract_tracks(_info(), TrackSelection(None, 2, False), tmp_path, timeout_s=0.2)

    assert captured.value.context.code is ErrorCode.TIMEOUT
    assert len(processes) == 1
    assert processes[0].poll() is not None
    assert processes[0].stdout is not None
    assert processes[0].stdout.closed
