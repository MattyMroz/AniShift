import threading

import pytest

from anishift.services.subtitles.types import DisplayedLine, SpokenLine
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.service import LlmTranslateService
from anishift.services.translation.errors import TranslationError, TranslationQuotaError
from anishift.services.translation.protocols import (
    LlmCompletionRequest,
    LlmCompletionResult,
    TranslationEngine,
    TranslationEngineFactory,
    TranslationInputPolicy,
    TranslationObserver,
    TranslationStream,
)
from anishift.services.translation.service import TranslationService
from anishift.services.translation.types import BatchedLine


class _FakeEngine:
    def __init__(
        self,
        *,
        engine_id: str = "fake",
        fail_with: Exception | None = None,
        prefix: str = "PL:",
        spoken_policy: TranslationInputPolicy = "deduplicate",
        displayed_policy: TranslationInputPolicy = "deduplicate",
    ) -> None:
        self._engine_id = engine_id
        self._fail = fail_with
        self._prefix = prefix
        self._spoken_policy = spoken_policy
        self._displayed_policy = displayed_policy
        self.calls: list[list[str]] = []
        self.target_langs: list[str] = []

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def is_available(self) -> bool:
        return True

    def translate_batch(self, texts, *, source_lang, target_lang, observer=None):  # type: ignore[no-untyped-def]
        del observer
        self.calls.append(list(texts))
        self.target_langs.append(target_lang)
        if self._fail is not None:
            raise self._fail
        return [BatchedLine(text=f"{self._prefix}{t}", ok=True) for t in texts]

    def close(self) -> None:
        pass

    def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy:
        return self._spoken_policy if stream == "spoken" else self._displayed_policy


class _Observer:
    def __init__(self) -> None:
        self.fallbacks: list[tuple[str, str]] = []

    def progress(self, engine_id: str, completed: int, total: int) -> None:
        del engine_id, completed, total

    def retry(
        self,
        engine_id: str,
        attempt: int,
        max_attempts: int,
        reason: str | None = None,
    ) -> None:
        del engine_id, attempt, max_attempts, reason

    def fallback(self, failed_engine_id: str, next_engine_id: str) -> None:
        self.fallbacks.append((failed_engine_id, next_engine_id))


class _InvalidLlmCompleter:
    def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        del request
        return LlmCompletionResult(text="invalid response", finish_reason="stop")


def _spoken(*texts: str) -> list[SpokenLine]:
    return [
        SpokenLine(start=i * 1000, end=i * 1000 + 500, text=t, style="Default", order=i * 2)
        for i, t in enumerate(texts)
    ]


def _displayed(*items: tuple[int, str]) -> list[DisplayedLine]:
    return [DisplayedLine(start=order * 1000, end=order * 1000 + 500, text=text, order=order) for order, text in items]


def _config() -> TranslationConfig:
    return TranslationConfig(engine="google")


def _single_engine_factory(engine: _FakeEngine) -> TranslationEngineFactory:
    def build(_engine_id: str, _config: TranslationConfig) -> _FakeEngine:
        return engine

    return build


def test_translate_file_builds_translated_lines_with_timings() -> None:
    engine = _FakeEngine()
    service = TranslationService(_config(), engine_factory=_single_engine_factory(engine))
    result = service.translate_file(_spoken("hi", "bye"), [], target_lang="pl")
    assert [line.text for line in result.spoken] == ["PL:hi", "PL:bye"]
    assert result.spoken[0].start == 0
    assert result.spoken[1].start == 1000
    assert result.spoken[0].lines == ("PL:hi",)
    assert result.engine_id == "fake"


def test_facade_defaults_target_to_polish_when_no_target_passed() -> None:
    engine = _FakeEngine()
    service = TranslationService(_config(), engine_factory=_single_engine_factory(engine))
    service.translate_file(_spoken("hi"), [])
    assert engine.target_langs == ["pl"]


def test_dedup_collapses_repeated_lines() -> None:
    engine = _FakeEngine()
    service = TranslationService(_config(), engine_factory=_single_engine_factory(engine))
    result = service.translate_file(_spoken("same", "same", "same"), [], target_lang="pl")
    assert engine.calls == [["same"]]
    assert [line.text for line in result.spoken] == ["PL:same", "PL:same", "PL:same"]
    assert result.unique_lines == 1
    assert result.total_lines == 3


def test_stream_policies_preserve_spoken_and_deduplicate_displayed() -> None:
    engine = _FakeEngine(spoken_policy="preserve")
    service = TranslationService(_config(), engine_factory=_single_engine_factory(engine))
    result = service.translate_file(
        _spoken("same", "same"),
        _displayed((1, "Sign"), (3, "Sign")),
        target_lang="pl",
    )
    assert engine.calls == [["same", "Sign", "same"]]
    assert [line.text for line in result.spoken] == ["PL:same", "PL:same"]
    assert result.displayed == ("PL:Sign", "PL:Sign")
    assert result.api_calls == 1


def test_empty_streams_return_empty_result() -> None:
    service = TranslationService(_config(), engine_factory=_single_engine_factory(_FakeEngine()))
    result = service.translate_file([], [], target_lang="pl")
    assert result.spoken == ()
    assert result.displayed == ()
    assert result.is_success


def test_displayed_translated_as_strings() -> None:
    service = TranslationService(_config(), engine_factory=_single_engine_factory(_FakeEngine()))
    result = service.translate_file([], _displayed((0, "Sign one"), (1, "Sign two")), target_lang="pl")
    assert result.displayed == ("PL:Sign one", "PL:Sign two")


def test_translate_file_preserves_chronological_context_across_streams() -> None:
    engine = _FakeEngine(spoken_policy="preserve")
    service = TranslationService(_config(), engine_factory=_single_engine_factory(engine))
    result = service.translate_file(
        [
            SpokenLine(start=1000, end=1500, text="Before", style="Default", order=0),
            SpokenLine(start=3000, end=3500, text="After", style="Default", order=2),
        ],
        _displayed((1, "Episode title")),
        target_lang="pl",
    )
    assert engine.calls == [["Before", "Episode title", "After"]]
    assert [line.text for line in result.spoken] == ["PL:Before", "PL:After"]
    assert result.displayed == ("PL:Episode title",)


def test_displayed_animation_duplicates_use_one_provider_item() -> None:
    engine = _FakeEngine(spoken_policy="preserve")
    service = TranslationService(_config(), engine_factory=_single_engine_factory(engine))
    displayed = _displayed(*((index, "Town name") for index in range(100)))
    result = service.translate_file([], displayed, target_lang="pl")
    assert engine.calls == [["Town name"]]
    assert result.displayed == ("PL:Town name",) * 100
    assert result.unique_lines == 1
    assert result.total_lines == 100


def test_displayed_partial_failure_counts_every_redistributed_occurrence() -> None:
    class _PartialFailureEngine(_FakeEngine):
        def translate_batch(self, texts, *, source_lang, target_lang, observer=None):  # type: ignore[no-untyped-def]
            del observer
            del source_lang, target_lang
            self.calls.append(list(texts))
            return [BatchedLine(text=text, ok=text != "Broken") for text in texts]

    engine = _PartialFailureEngine()
    service = TranslationService(_config(), engine_factory=_single_engine_factory(engine))
    result = service.translate_file([], _displayed((0, "Broken"), (1, "Broken")), target_lang="pl")
    assert result.displayed == ("Broken", "Broken")
    assert result.failed_lines == 2


def test_fallback_chain_uses_next_engine_on_quota() -> None:
    failing = _FakeEngine(engine_id="deepl", fail_with=TranslationQuotaError("quota"))
    working = _FakeEngine(engine_id="google", prefix="G:")
    engines = {"deepl": failing, "google": working}
    config = TranslationConfig(engine="deepl")

    def build(engine_id: str, _config: TranslationConfig) -> _FakeEngine:
        return engines[engine_id]

    service = TranslationService(config, fallback_chain=("google",), engine_factory=build)
    observer: TranslationObserver = _Observer()
    result = service.translate_file(_spoken("x"), [], target_lang="pl", observer=observer)
    assert result.engine_id == "google"
    assert [line.text for line in result.spoken] == ["G:x"]
    assert isinstance(observer, _Observer)
    assert observer.fallbacks == [("deepl", "google")]


def test_invalid_llm_json_falls_back_for_the_whole_file() -> None:
    failing = LlmTranslateService(
        LlmTranslateConfig(max_contract_retries=0),
        completer=_InvalidLlmCompleter(),
    )
    working = _FakeEngine(engine_id="google", prefix="G:")

    def build(engine_id: str, _config: TranslationConfig) -> TranslationEngine:
        return failing if engine_id == "llm" else working

    service = TranslationService(
        TranslationConfig(engine="llm"),
        fallback_chain=("google",),
        engine_factory=build,
    )
    observer = _Observer()

    result = service.translate_file(_spoken("one", "two"), [], target_lang="pl", observer=observer)

    assert result.engine_id == "google"
    assert [line.text for line in result.spoken] == ["G:one", "G:two"]
    assert working.calls == [["one", "two"]]
    assert observer.fallbacks == [("llm", "google")]


def test_exhausted_chain_sets_error() -> None:
    failing = _FakeEngine(fail_with=TranslationQuotaError("quota"))
    service = TranslationService(_config(), engine_factory=_single_engine_factory(failing))
    result = service.translate_file(_spoken("x"), [], target_lang="pl")
    assert not result.is_success
    assert result.error is not None
    assert result.error_context is not None


def test_cancel_raises_translation_error() -> None:
    cancel = threading.Event()
    cancel.set()
    service = TranslationService(_config(), engine_factory=_single_engine_factory(_FakeEngine()))
    with pytest.raises(TranslationError):
        service.translate_file(_spoken("x"), [], target_lang="pl", cancel=cancel)
