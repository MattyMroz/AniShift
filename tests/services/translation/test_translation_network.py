from pathlib import Path

import pytest

from anishift.config.settings import Settings
from anishift.services.subtitles import (
    load_subtitles,
    split_subtitles,
    subtitle_kind,
    visible_text,
    write_translated_displayed,
)
from anishift.services.subtitles.types import SpokenLine
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.linebreak import split_line
from anishift.services.translation.service import TranslationService

pytestmark = pytest.mark.network

_DATASET_ASS = Path("../mm_avh_working_space/temp/dataset_ass")


def _spoken(*texts: str) -> list[SpokenLine]:
    return [SpokenLine(start=i * 1000, end=i * 1000 + 500, text=t, style="Default") for i, t in enumerate(texts)]


def _first_real_ass() -> Path | None:
    if not _DATASET_ASS.is_dir():
        return None
    return next(iter(sorted(_DATASET_ASS.glob("*.ass"))), None)


def _first_ass_with_displayed() -> Path | None:
    if not _DATASET_ASS.is_dir():
        return None
    for ass in sorted(_DATASET_ASS.glob("*.ass")):
        try:
            split = split_subtitles(load_subtitles(ass), kind="ass")
        except Exception:  # noqa: BLE001, S112 - skip unparsable dataset entries while scanning
            continue
        if split.stats.displayed_events > 0:
            return ass
    return None


def test_google_translates_english_to_polish() -> None:
    service = TranslationService(TranslationConfig(engine="google"))
    result = service.translate_file(_spoken("Hello", "How are you?"), [], target_lang="pl")
    assert result.is_success
    assert len(result.spoken) == 2
    assert result.spoken[0].start == 0
    assert result.spoken[1].start == 1000
    assert all(line.text and line.text != line.source_text for line in result.spoken)


def test_google_preserves_line_count_and_timings() -> None:
    service = TranslationService(TranslationConfig(engine="google"))
    lines = _spoken("I don't know", "if I can do it", "but I will try")
    result = service.translate_file(lines, [], target_lang="pl")
    assert len(result.spoken) == 3
    assert [line.start for line in result.spoken] == [0, 1000, 2000]


def test_google_translates_real_ass_file() -> None:
    ass = _first_real_ass()
    if ass is None:
        pytest.skip("dataset_ass corpus not available")
    kind = subtitle_kind(ass)
    assert kind == "ass"
    split = split_subtitles(load_subtitles(ass), kind=kind)
    spoken = list(split.spoken[:15])
    if not spoken:
        pytest.skip("real ASS produced no spoken lines")

    service = TranslationService(TranslationConfig(engine="google"))
    result = service.translate_file(spoken, [], target_lang="pl")

    assert result.is_success
    assert len(result.spoken) == len(spoken)
    for source, translated in zip(spoken, result.spoken, strict=True):
        assert translated.start == source.start
        assert translated.end == source.end
        assert translated.style == source.style
        assert translated.source_text == source.text
    changed = sum(1 for line in result.spoken if line.text and line.text != line.source_text)
    assert changed >= len(result.spoken) // 2


def test_google_real_ass_displayed_round_trip_to_disk(tmp_path: Path) -> None:
    ass = _first_ass_with_displayed()
    if ass is None:
        pytest.skip("no dataset ASS with displayed events")
    kind = subtitle_kind(ass)
    assert kind == "ass"
    split = split_subtitles(load_subtitles(ass), kind=kind)

    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    displayed_source = [
        (event, visible_text(event.text))
        for event, decision in zip(dialogue, split.decisions, strict=True)
        if decision == "displayed"
    ]
    displayed_texts = [text for _, text in displayed_source]

    service = TranslationService(TranslationConfig(engine="google"))
    result = service.translate_file([], displayed_texts, target_lang="pl")
    assert result.is_success
    assert len(result.displayed) == split.stats.displayed_events

    verses = [split_line(text) for text in result.displayed]
    dest = write_translated_displayed(split, verses, tmp_path / "out.pl.ass")
    assert dest is not None

    written = load_subtitles(dest)
    written_displayed = [event for event in written.events if event.type == "Dialogue"]
    assert len(written_displayed) == split.stats.displayed_events
    assert written.styles.keys() == split.subs.styles.keys()
    for (source_event, _), written_event in zip(displayed_source, written_displayed, strict=True):
        assert written_event.start == source_event.start
        assert written_event.end == source_event.end
        assert written_event.style == source_event.style


def test_deepl_translates_with_user_key() -> None:
    key = Settings().deepl_api_key
    if not key:
        pytest.skip("no DeepL key configured")
    service = TranslationService(TranslationConfig(engine="deepl", api_key=key))
    result = service.translate_file(_spoken("Hello", "How are you?"), [], target_lang="pl")
    assert result.is_success
    assert result.engine_id == "deepl"
    assert len(result.spoken) == 2
    assert all(line.text and line.text != line.source_text for line in result.spoken)
