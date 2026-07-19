from __future__ import annotations

from pathlib import Path

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.pipeline import runner
from anishift.pipeline.types import TranslationSettings
from anishift.services.subtitles.service import split_subtitles
from anishift.services.translation.types import FileTranslation, TranslatedLine


def _ts() -> TranslationSettings:
    return TranslationSettings(
        engine="google",
        fallback_chain=("google",),
        batch_size=0,
        max_retries=3,
        deepl_api_key="",
    )


def _split(events: list[SSAEvent], *, spoken_styles: set[str] | None = None):  # type: ignore[no-untyped-def]
    subs = SSAFile()
    subs.events.extend(events)
    return split_subtitles(subs, kind="ass", spoken_styles=spoken_styles)


def test_should_translate_skips_polish() -> None:
    split = _split([SSAEvent(start=0, end=1000, style="Dialog", text="Hello")], spoken_styles={"Dialog"})
    assert not runner._should_translate(split, already_polish=True)
    assert runner._should_translate(split, already_polish=False)


def test_should_translate_skips_empty_split() -> None:
    subs = SSAFile()
    split = split_subtitles(subs, kind="ass", spoken_styles=set())
    assert not runner._should_translate(split, already_polish=False)


def test_displayed_visible_texts_extracts_displayed_only() -> None:
    events = [
        SSAEvent(start=0, end=1000, style="Dialog", text="Spoken line"),
        SSAEvent(start=1000, end=2000, style="Sign", text="{\\pos(1,2)}On screen"),
    ]
    split = _split(events, spoken_styles={"Dialog"})
    assert runner._displayed_visible_texts(split) == ["On screen"]


def test_process_txt_translates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    txt = tmp_path / "book.txt"
    txt.write_text("Pierwsze zdanie. Drugie zdanie.", encoding="utf-8")

    class _FakeService:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def translate_file(self, spoken, displayed, **__):  # type: ignore[no-untyped-def]
            lines = tuple(
                TranslatedLine(
                    start=s.start,
                    end=s.end,
                    source_text=s.text,
                    text=f"PL:{s.text}",
                    lines=(f"PL:{s.text}",),
                    style=s.style,
                    ok=True,
                )
                for s in spoken
            )
            return FileTranslation(spoken=lines, engine_id="fake", target_lang="pl")

    monkeypatch.setattr("anishift.services.translation.TranslationService", _FakeService)
    outcome = runner._process_txt(txt, _ts())
    assert outcome.status == "done"
    assert outcome.translation_engine == "fake"
    assert outcome.translated_lines == outcome.spoken_lines
    assert outcome.translated_lines > 0
    assert outcome.translated_path is not None
    assert outcome.translated_path.exists()
    assert outcome.translated_path.suffix == ".srt"
    srt = outcome.translated_path.read_text(encoding="utf-8")
    assert "-->" in srt
    assert "PL:" in srt
