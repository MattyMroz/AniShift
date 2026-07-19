from pathlib import Path

import pytest

from anishift.services.subtitles import load_subtitles, split_subtitles, subtitle_kind
from anishift.services.subtitles.types import SpokenLine
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.service import TranslationService

pytestmark = pytest.mark.network

_DATASET_ASS = Path("../mm_avh_working_space/temp/dataset_ass")


def _spoken(*texts: str) -> list[SpokenLine]:
    return [SpokenLine(start=i * 1000, end=i * 1000 + 500, text=t, style="Default") for i, t in enumerate(texts)]


def _first_real_ass() -> Path | None:
    if not _DATASET_ASS.is_dir():
        return None
    return next(iter(sorted(_DATASET_ASS.glob("*.ass"))), None)


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
