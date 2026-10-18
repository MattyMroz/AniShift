from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

import pytest

from anishift.errors import ErrorCode
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.extraction import service
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import MediaInfo

_SYSTEM_FONT: Final[Path] = Path("C:/Windows/Fonts/arial.ttf")


def _media(*attachments: str) -> MediaInfo:
    return MediaInfo(path=Path("episode.mkv"), tracks=(), attachments=attachments, duration_us=0)


@pytest.mark.unit
def test_extract_attachments_skips_a_container_without_fonts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "identify", lambda _: _media("cover.jpg", "notes.txt"))

    assert service.extract_attachments(Path("episode.mkv"), tmp_path / "fonts") == ()
    assert not (tmp_path / "fonts").exists()


@pytest.mark.unit
def test_extract_attachments_picks_each_attachment_by_its_own_extension(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        requested.append(command[5:])
        for spec in command[5:]:
            (tmp_path / "fonts" / spec.split(":", 1)[1]).write_bytes(b"font")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(service, "identify", lambda _: _media("Font.txt", "Font.ttf", "Cover.jpg", "Second.OTF"))
    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(subprocess, "run", run)

    extracted: tuple[Path, ...] = service.extract_attachments(Path("episode.mkv"), tmp_path / "fonts")

    assert requested == [["2:Font.ttf", "4:Second.OTF"]]
    assert extracted == (tmp_path / "fonts" / "Font.ttf", tmp_path / "fonts" / "Second.OTF")


@pytest.mark.unit
def test_extract_attachments_fails_when_mkvextract_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "identify", lambda _: _media("Font.ttf"))
    monkeypatch.setattr(service, "ensure_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 2, stdout="", stderr="")
    )

    with pytest.raises(ExtractionError) as error:
        service.extract_attachments(Path("episode.mkv"), tmp_path / "fonts")

    assert error.value.context.code is ErrorCode.EXTRACTION_FAILED


@pytest.mark.integration
def test_extract_attachments_writes_only_font_attachments_and_repeats_idempotently(tmp_path: Path) -> None:
    mkvmerge: Path | None = resolve_binary(Binary.MKVMERGE)
    if mkvmerge is None or resolve_binary(Binary.MKVEXTRACT) is None or not _SYSTEM_FONT.is_file():
        pytest.skip("MKVToolNix or the system Arial font is not available")
    subtitles: Path = tmp_path / "episode.srt"
    subtitles.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    notes: Path = tmp_path / "notes.txt"
    notes.write_text("not a font", encoding="utf-8")
    container: Path = tmp_path / "episode.mkv"
    attachments: list[str] = ["--attach-file", str(_SYSTEM_FONT), "--attach-file", str(notes)]
    subprocess.run(  # noqa: S603
        [str(mkvmerge), "-q", "-o", str(container), str(subtitles), *attachments],
        check=True,
        timeout=60,
    )

    first: tuple[Path, ...] = service.extract_attachments(container, tmp_path / "fonts")
    second: tuple[Path, ...] = service.extract_attachments(container, tmp_path / "fonts")

    assert first == second == (tmp_path / "fonts" / "arial.ttf",)
    assert first[0].read_bytes() == _SYSTEM_FONT.read_bytes()
    assert sorted(path.name for path in (tmp_path / "fonts").iterdir()) == ["arial.ttf"]
