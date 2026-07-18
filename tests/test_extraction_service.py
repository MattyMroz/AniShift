import json
import subprocess
import threading
from pathlib import Path

import pytest

from anishift.errors import ErrorCode
from anishift.services.extraction import service
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import MediaInfo, TrackSelection

DATA_DIR = Path(__file__).parent / "data"


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
        self.stdout = iter(output)
        self.returncode = returncode
        self.terminated = False

    def wait(self) -> int:
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


class _BlockingProcess(_FakeProcess):
    def __init__(self) -> None:
        self._released = threading.Event()
        super().__init__([])
        self.stdout = _BlockingOutput(self._released)

    def terminate(self) -> None:
        super().terminate()
        self._released.set()


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
    process: _FakeProcess | None = None

    def fake_popen(command: list[str], **_: object) -> _FakeProcess:
        nonlocal process
        Path(command[-2].split(":", 1)[1]).write_bytes(b"partial")
        process = _FakeProcess(["ordinary output\n"])
        return process

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    cancel = threading.Event()
    cancel.set()
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
    Path(tmp_path / "source.aac").write_bytes(b"partial")
    cancel = threading.Event()
    result: list[ExtractionError] = []

    def fake_popen(*_: object, **__: object) -> _BlockingProcess:
        return process

    def run_extraction() -> None:
        try:
            service.extract_tracks(_info(), TrackSelection(1, 2, False), tmp_path, cancel=cancel)
        except ExtractionError as exc:
            result.append(exc)

    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    worker = threading.Thread(target=run_extraction)
    worker.start()
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
