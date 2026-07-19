import pytest

from anishift.services.subtitles.types import SpokenLine
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.service import TranslationService

pytestmark = pytest.mark.network


def _spoken(*texts: str) -> list[SpokenLine]:
    return [SpokenLine(start=i * 1000, end=i * 1000 + 500, text=t, style="Default") for i, t in enumerate(texts)]


def test_google_translates_english_to_polish() -> None:
    service = TranslationService(TranslationConfig(engine="google"))
    result = service.translate_file(_spoken("Hello", "How are you?"), [], target_lang="pl")
    assert result.is_success
    assert len(result.spoken) == 2
    assert result.spoken[0].start == 0
    assert result.spoken[1].start == 1000
    # translations are non-empty and differ from the source
    assert all(line.text and line.text != line.source_text for line in result.spoken)


def test_google_preserves_line_count_and_timings() -> None:
    service = TranslationService(TranslationConfig(engine="google"))
    lines = _spoken("I don't know", "if I can do it", "but I will try")
    result = service.translate_file(lines, [], target_lang="pl")
    assert len(result.spoken) == 3
    assert [line.start for line in result.spoken] == [0, 1000, 2000]
