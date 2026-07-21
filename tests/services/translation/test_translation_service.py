import threading

import pytest

from anishift.services.subtitles.types import SpokenLine
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.errors import TranslationError, TranslationQuotaError
from anishift.services.translation.service import TranslationService
from anishift.services.translation.types import BatchedLine


class _FakeEngine:
    def __init__(self, *, engine_id: str = "fake", fail_with: Exception | None = None, prefix: str = "PL:") -> None:
        self._engine_id = engine_id
        self._fail = fail_with
        self._prefix = prefix
        self.calls: list[list[str]] = []
        self.target_langs: list[str] = []

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def is_available(self) -> bool:
        return True

    def translate_batch(self, texts, *, source_lang, target_lang):  # type: ignore[no-untyped-def]
        self.calls.append(list(texts))
        self.target_langs.append(target_lang)
        if self._fail is not None:
            raise self._fail
        return [BatchedLine(text=f"{self._prefix}{t}", ok=True) for t in texts]

    def close(self) -> None:
        pass


def _spoken(*texts: str) -> list[SpokenLine]:
    return [SpokenLine(start=i * 1000, end=i * 1000 + 500, text=t, style="Default") for i, t in enumerate(texts)]


def _config() -> TranslationConfig:
    return TranslationConfig(engine="google")


def test_translate_file_builds_translated_lines_with_timings() -> None:
    engine = _FakeEngine()
    service = TranslationService(_config(), engine=engine)
    result = service.translate_file(_spoken("hi", "bye"), [], target_lang="pl")
    assert [line.text for line in result.spoken] == ["PL:hi", "PL:bye"]
    assert result.spoken[0].start == 0
    assert result.spoken[1].start == 1000
    assert result.spoken[0].lines == ("PL:hi",)
    assert result.engine_id == "fake"


def test_facade_defaults_target_to_polish_when_no_target_passed() -> None:
    engine = _FakeEngine()
    service = TranslationService(_config(), engine=engine)
    service.translate_file(_spoken("hi"), [])
    assert engine.target_langs == ["pl"]


def test_dedup_collapses_repeated_lines() -> None:
    engine = _FakeEngine()
    service = TranslationService(_config(), engine=engine)
    result = service.translate_file(_spoken("same", "same", "same"), [], target_lang="pl")
    assert engine.calls == [["same"]]
    assert [line.text for line in result.spoken] == ["PL:same", "PL:same", "PL:same"]
    assert result.unique_lines == 1
    assert result.total_lines == 3


def test_empty_streams_return_empty_result() -> None:
    service = TranslationService(_config(), engine=_FakeEngine())
    result = service.translate_file([], [], target_lang="pl")
    assert result.spoken == ()
    assert result.displayed == ()
    assert result.is_success


def test_displayed_translated_as_strings() -> None:
    service = TranslationService(_config(), engine=_FakeEngine())
    result = service.translate_file([], ["Sign one", "Sign two"], target_lang="pl")
    assert result.displayed == ("PL:Sign one", "PL:Sign two")


def test_fallback_chain_uses_next_engine_on_quota() -> None:
    failing = _FakeEngine(engine_id="deepl", fail_with=TranslationQuotaError("quota"))
    working = _FakeEngine(engine_id="google", prefix="G:")
    engines = {"deepl": failing, "google": working}
    config = TranslationConfig(engine="deepl")

    class _Service(TranslationService):
        def _build_engine(self, engine_id):  # type: ignore[no-untyped-def]
            return engines[engine_id]

    service = _Service(config, fallback_chain=("google",))
    result = service.translate_file(_spoken("x"), [], target_lang="pl")
    assert result.engine_id == "google"
    assert [line.text for line in result.spoken] == ["G:x"]


def test_exhausted_chain_sets_error() -> None:
    failing = _FakeEngine(fail_with=TranslationQuotaError("quota"))
    service = TranslationService(_config(), engine=failing)
    result = service.translate_file(_spoken("x"), [], target_lang="pl")
    assert not result.is_success
    assert result.error is not None


def test_cancel_raises_translation_error() -> None:
    cancel = threading.Event()
    cancel.set()
    service = TranslationService(_config(), engine=_FakeEngine())
    with pytest.raises(TranslationError):
        service.translate_file(_spoken("x"), [], target_lang="pl", cancel=cancel)
