from __future__ import annotations

import threading
from pathlib import Path

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline import runner
from anishift.pipeline.narration import NarrationBatch, scope_id_for_source
from anishift.pipeline.types import FileOutcome, TranslationSettings
from anishift.services.subtitles.service import load_subtitles, split_subtitles
from anishift.services.subtitles.text import visible_text
from anishift.services.translation import chunking
from anishift.services.translation.errors import TranslationError
from anishift.services.translation.types import FileTranslation, TranslatedLine
from anishift.services.tts import SpeechBatch


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


def test_displayed_lines_extracts_text_and_source_order() -> None:
    events = [
        SSAEvent(start=0, end=1000, style="Dialog", text="Spoken line"),
        SSAEvent(start=1000, end=2000, style="Sign", text="{\\pos(1,2)}On screen"),
    ]
    split = _split(events, spoken_styles={"Dialog"})
    displayed = runner._displayed_lines(split)
    assert [line.text for line in displayed] == ["On screen"]
    assert [line.order for line in displayed] == [1]


def test_displayed_lines_do_not_send_vector_drawings_to_translator() -> None:
    events = [
        SSAEvent(start=0, end=1000, style="Sign", text=r"{\p1}m 0 0 l 10 10"),
        SSAEvent(start=1000, end=2000, style="Sign", text="Translate me"),
        SSAEvent(start=2000, end=3000, style="Dialog", text="Spoken"),
    ]
    split = _split(events, spoken_styles={"Dialog"})
    assert [line.text for line in runner._displayed_lines(split)] == ["Translate me"]


def test_translation_writer_creates_full_spoken_and_displayed_products(tmp_path: Path) -> None:
    events = [
        SSAEvent(start=0, end=1000, style="Dialog", text="We are home"),
        SSAEvent(start=1000, end=2000, style="Sign", text=r"{\an8}Episode 3\NLife Back at Home"),
    ]
    split = _split(events, spoken_styles={"Dialog"})
    result = FileTranslation(
        spoken=(
            TranslatedLine(
                start=0,
                end=1000,
                source_text="We are home",
                text="Jesteśmy w domu",
                lines=("Jesteśmy w domu",),
                style="Dialog",
            ),
        ),
        displayed=("Odcinek 3: Życie z powrotem w domu",),
    )
    outcome = FileOutcome(tmp_path / "show.mkv", "done")
    state = runner._MkvState(outcome, split, "ass")

    runner._write_translation_products(tmp_path / "show.mkv", state, result, tmp_path)

    assert outcome.translated_path == tmp_path / "show.pl.ass"
    assert outcome.spoken_path == tmp_path / "show.spoken.pl.ass"
    assert outcome.displayed_path == tmp_path / "show.displayed.pl.ass"
    full_events = [event for event in load_subtitles(outcome.translated_path).events if event.type == "Dialogue"]
    spoken_events = [event for event in load_subtitles(outcome.spoken_path).events if event.type == "Dialogue"]
    displayed_events = [event for event in load_subtitles(outcome.displayed_path).events if event.type == "Dialogue"]
    assert [visible_text(event.text) for event in full_events] == [
        "Jesteśmy w domu",
        "Odcinek 3: Życie z powrotem w domu",
    ]
    assert r"Odcinek 3:\NŻycie z powrotem w domu" in full_events[1].text
    assert [visible_text(event.text) for event in spoken_events] == ["Jesteśmy w domu"]
    assert len(displayed_events) == 1
    assert r"Odcinek 3:\NŻycie z powrotem w domu" in displayed_events[0].text


def test_polish_source_writer_creates_final_products_without_translation(tmp_path: Path) -> None:
    events = [
        SSAEvent(start=0, end=1000, style="Dialog", text="Jesteśmy w domu"),
        SSAEvent(start=1000, end=2000, style="Sign", text=r"{\an8}Tytuł odcinka"),
    ]
    split = _split(events, spoken_styles={"Dialog"})
    outcome = FileOutcome(tmp_path / "show.mkv", "done", already_polish=True)

    runner._write_polish_products(tmp_path / "show.mkv", outcome, split, tmp_path, "ass")

    assert outcome.translated_path == tmp_path / "show.pl.ass"
    assert outcome.spoken_path == tmp_path / "show.spoken.pl.ass"
    assert outcome.displayed_path == tmp_path / "show.displayed.pl.ass"
    assert not (tmp_path / "show.displayed.ass").exists()


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


def test_process_txt_translates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    txt = tmp_path / "book.txt"
    txt.write_text("Pierwsze zdanie. Drugie zdanie.", encoding="utf-8")

    monkeypatch.setattr("anishift.services.translation.TranslationService", _FakeService)
    outcome = runner._process_txt(txt, _ts(), cancel=threading.Event())
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


def test_process_txt_chunks_via_chunk_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    txt = tmp_path / "book.txt"
    txt.write_text("Dr. Kowalski przyszedł wcześnie. " * 60, encoding="utf-8")

    calls: list[str] = []
    real_chunk_text = chunking.chunk_text

    def spy(text: str, **kwargs: object):  # type: ignore[no-untyped-def]
        calls.append(text)
        return real_chunk_text(text, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("anishift.services.translation.chunking.chunk_text", spy)
    monkeypatch.setattr("anishift.services.translation.TranslationService", _FakeService)
    outcome = runner._process_txt(txt, _ts(), cancel=threading.Event())

    assert calls, "chunk_text was not used for the txt path"
    assert outcome.status == "done"
    assert outcome.spoken_lines > 1
    assert outcome.translated_path is not None
    srt = outcome.translated_path.read_text(encoding="utf-8")
    assert srt.count("PL:") == outcome.spoken_lines


def test_txt_spoken_lines_flatten_chunks_to_single_lines() -> None:
    lines = runner._txt_spoken_lines("Pierwszy akapit.\n\nDrugi akapit.\nDalszy ciąg.")
    assert lines
    for line in lines:
        assert "\n" not in line.text
        assert line.text == line.text.strip()


def test_process_txt_marks_unsuccessful_translation_as_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    txt = tmp_path / "book.txt"
    txt.write_text("Source", encoding="utf-8")
    context = ErrorContext(
        code=ErrorCode.LLM_AUTH_FAILED,
        message="missing key",
        suggestion="configure key",
    )

    class _FailingService:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def translate_file(self, *_: object, **__: object) -> FileTranslation:
            return FileTranslation(error="missing key", error_context=context)

    monkeypatch.setattr("anishift.services.translation.TranslationService", _FailingService)
    outcome = runner._process_txt(txt, _ts(), cancel=threading.Event())
    assert outcome.status == "failed"
    assert outcome.failure is not None
    assert outcome.failure.code == ErrorCode.LLM_AUTH_FAILED.value
    assert outcome.translated_path is None


def test_successful_mkv_translation_publishes_timed_narration_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "show.mkv"
    source.touch()
    split = _split(
        [SSAEvent(start=1000, end=2000, style="Dialog", text="Good evening")],
        spoken_styles={"Dialog"},
    )
    state = runner._MkvState(
        FileOutcome(source, "done"),
        split,
        "ass",
        source_rank=2,
        scope_id=scope_id_for_source(source, workspace_root=tmp_path),
    )
    published: list[tuple[Path, NarrationBatch]] = []
    monkeypatch.setattr("anishift.services.translation.TranslationService", _FakeService)

    runner._translate_one(
        source,
        state,
        tmp_path,
        _ts(),
        threading.Event(),
        progress=None,
        task_id=None,
        on_spoken_ready=lambda path, batch: published.append((path, batch)),
    )

    assert len(published) == 1
    assert published[0][0] == source
    assert published[0][1].speech.batch_rank == 2
    assert published[0][1].speech.requests[0].text == "PL:Good evening"
    assert state.enqueue_generation == 1


def test_translate_phase_uses_source_rank_not_extraction_completion_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = tmp_path / "Episode 1.mkv"
    second = tmp_path / "Episode 2.mkv"
    split = _split(
        [SSAEvent(start=0, end=1000, style="Dialog", text="Hello")],
        spoken_styles={"Dialog"},
    )
    states = {
        second: runner._MkvState(FileOutcome(second, "done"), split, source_rank=1),
        first: runner._MkvState(FileOutcome(first, "done"), split, source_rank=0),
    }
    observed: list[Path] = []

    def translate_one(path: Path, *_: object, **__: object) -> None:
        observed.append(path)

    monkeypatch.setattr(runner, "_translate_one", translate_one)

    runner._translate_phase(
        states,
        tmp_path,
        _ts(),
        None,
        threading.Event(),
    )

    assert observed == [first, second]


def test_failed_spoken_ready_publish_remains_retryable(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    state = runner._MkvState(
        FileOutcome(source, "done"),
        None,
        narration=NarrationBatch(
            speech=SpeechBatch(
                scope_id="scope",
                batch_rank=0,
                requests=(),
            ),
            items=(),
        ),
    )

    def reject(_path: Path, _batch: NarrationBatch) -> None:
        raise RuntimeError("queue closed")

    with pytest.raises(RuntimeError, match="queue closed"):
        runner._notify_spoken_ready(source, state, reject)

    assert state.enqueue_generation == 0


def test_failed_mkv_translation_never_publishes_narration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _FailedService:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def translate_file(self, *_: object, **__: object) -> FileTranslation:
            return FileTranslation(error="failed")

    source = tmp_path / "show.mkv"
    source.touch()
    split = _split(
        [SSAEvent(start=1000, end=2000, style="Dialog", text="Good evening")],
        spoken_styles={"Dialog"},
    )
    state = runner._MkvState(
        FileOutcome(source, "done"),
        split,
        "ass",
        source_rank=0,
        scope_id=scope_id_for_source(source, workspace_root=tmp_path),
    )
    published: list[NarrationBatch] = []
    monkeypatch.setattr(
        "anishift.services.translation.TranslationService",
        _FailedService,
    )

    runner._translate_one(
        source,
        state,
        tmp_path,
        _ts(),
        threading.Event(),
        progress=None,
        task_id=None,
        on_spoken_ready=lambda _path, batch: published.append(batch),
    )

    assert published == []
    assert state.narration is None
    assert state.outcome.status == "failed"


def test_process_txt_maps_raised_cancellation_to_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    txt = tmp_path / "book.txt"
    txt.write_text("Source", encoding="utf-8")
    context = ErrorContext(code=ErrorCode.CANCELLED, message="cancelled")

    class _CancelledService:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def translate_file(self, *_: object, **__: object) -> FileTranslation:
            raise TranslationError(context=context)

    monkeypatch.setattr("anishift.services.translation.TranslationService", _CancelledService)
    outcome = runner._process_txt(txt, _ts(), cancel=threading.Event())
    assert outcome.status == "cancelled"
    assert outcome.failure is not None
    assert outcome.failure.code == ErrorCode.CANCELLED.value
