from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import pytest

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.service import LlmTranslateService
from anishift.services.translation.errors import (
    TranslationConfigError,
    TranslationContextLengthError,
    TranslationEngineError,
)
from anishift.services.translation.protocols import LlmCompletionRequest, LlmCompletionResult


class _FakeCompleter:
    def __init__(
        self,
        responses: Iterable[LlmCompletionResult | TranslationEngineError],
    ) -> None:
        self.responses: list[LlmCompletionResult | TranslationEngineError] = list(responses)
        self.requests: list[LlmCompletionRequest] = []

    def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, TranslationEngineError):
            raise response
        return response


class _Observer:
    def __init__(self) -> None:
        self.progress_updates: list[tuple[str, int, int]] = []

    def progress(self, engine_id: str, completed: int, total: int) -> None:
        self.progress_updates.append((engine_id, completed, total))

    def retry(
        self,
        engine_id: str,
        attempt: int,
        max_attempts: int,
        reason: str | None = None,
    ) -> None:
        del engine_id, attempt, max_attempts, reason

    def fallback(self, failed_engine_id: str, next_engine_id: str) -> None:
        del failed_engine_id, next_engine_id


def _result(text: str, finish_reason: str = "stop") -> LlmCompletionResult:
    return LlmCompletionResult(text=text, finish_reason=finish_reason)


def _numbered(*texts: str) -> str:
    return "\n".join(f"[{number}] {text}" for number, text in enumerate(texts))


def _lines(*items: tuple[int, str]) -> str:
    return "\n".join(f"[{number}] {text}" for number, text in items)


def _context_error() -> TranslationContextLengthError:
    return TranslationContextLengthError(
        context=ErrorContext(
            code=ErrorCode.LLM_CONTEXT_EXCEEDED,
            message="context exceeded",
        )
    )


def test_translate_batch_builds_ordered_prompt_parts_and_numbered_input() -> None:
    completer = _FakeCompleter([_result(_numbered("jeden", "dwa"))])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    result = engine.translate_batch(["one", "two"], source_lang="auto", target_lang="pl")

    request = completer.requests[0]
    assert [line.text for line in result] == ["jeden", "dwa"]
    assert len(request.user_parts) == 3
    assert "polski" in request.system
    assert "Przetłumacz" in request.user_parts[0]
    assert "neutralny" in request.user_parts[1]
    assert request.user_parts[2] == "[0] one\n[1] two"


def test_translate_empty_batch_does_not_call_completer() -> None:
    completer = _FakeCompleter([])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    assert engine.translate_batch([], source_lang="auto", target_lang="pl") == []
    assert completer.requests == []


def test_translate_batch_round_trips_a_line_break_inside_a_subtitle() -> None:
    completer = _FakeCompleter([_result("[0] pierwszy\\ndrugi")])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    result = engine.translate_batch(["first\nsecond"], source_lang="auto", target_lang="pl")

    assert completer.requests[0].user_parts[2] == "[0] first\\nsecond"
    assert [line.text for line in result] == ["pierwszy\ndrugi"]


def test_translate_batch_repairs_only_the_missing_number() -> None:
    completer = _FakeCompleter(
        [
            _result(_lines((0, "jeden"), (2, "trzy"))),
            _result(_lines((1, "dwa"))),
        ]
    )
    engine = LlmTranslateService(LlmTranslateConfig(max_contract_retries=1), completer=completer)

    result = engine.translate_batch(["one", "two", "three"], source_lang="auto", target_lang="pl")

    assert [line.text for line in result] == ["jeden", "dwa", "trzy"]
    assert len(completer.requests) == 2
    assert completer.requests[1].user_parts[2] == "[1] two"


def test_translate_batch_repairs_the_number_a_stray_line_invalidated() -> None:
    completer = _FakeCompleter(
        [
            _result("[0] jeden\n[1] dwa\nGotowe, oto tłumaczenie!"),
            _result(_lines((1, "dwa"))),
        ]
    )
    engine = LlmTranslateService(LlmTranslateConfig(max_contract_retries=1), completer=completer)

    result = engine.translate_batch(["one", "two"], source_lang="auto", target_lang="pl")

    assert [line.text for line in result] == ["jeden", "dwa"]
    assert completer.requests[1].user_parts[2] == "[1] two"


def test_translate_batch_retry_part_carries_a_safe_diagnosis() -> None:
    completer = _FakeCompleter(
        [
            _result(_lines((0, "zażółcona"))),
            _result(_lines((1, "gęślą"))),
        ]
    )
    engine = LlmTranslateService(LlmTranslateConfig(max_contract_retries=1), completer=completer)

    engine.translate_batch(["one", "two"], source_lang="auto", target_lang="pl")

    retry_part = completer.requests[1].user_parts[-1]
    assert len(completer.requests[1].user_parts) == 4
    assert "Numery do poprawienia: 1" in retry_part
    assert "zażółcona" not in retry_part


def test_translate_batch_does_not_split_after_contract_retry_budget() -> None:
    completer = _FakeCompleter([_result("bez numeracji"), _result("nadal bez numeracji")])
    engine = LlmTranslateService(LlmTranslateConfig(max_contract_retries=1), completer=completer)

    with pytest.raises(TranslationEngineError, match="numbered translation lines"):
        engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")

    assert len(completer.requests) == 2


def test_exhausted_contract_error_reports_only_a_safe_diagnosis() -> None:
    completer = _FakeCompleter([_result("[0] jeden\n[0] jeden"), _result("[0] jeden\n[0] jeden")])
    engine = LlmTranslateService(LlmTranslateConfig(max_contract_retries=1), completer=completer)

    with pytest.raises(TranslationEngineError) as error:
        engine.translate_batch(["a"], source_lang="auto", target_lang="pl")

    assert "powtarza ten sam numer" in str(error.value)
    assert "jeden" not in str(error.value)


def test_translate_batch_output_limit_splits_without_contract_retry() -> None:
    completer = _FakeCompleter(
        [
            _result("discarded", finish_reason="length"),
            _result(_numbered("jeden")),
            _result(_numbered("dwa")),
        ]
    )
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    result = engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")

    assert [line.text for line in result] == ["jeden", "dwa"]
    assert all(len(request.user_parts) == 3 for request in completer.requests)


def test_translate_batch_context_limit_splits_without_contract_retry() -> None:
    completer = _FakeCompleter(
        [
            _context_error(),
            _result(_numbered("jeden")),
            _result(_numbered("dwa")),
        ]
    )
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    result = engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")

    assert [line.text for line in result] == ["jeden", "dwa"]


def test_translate_batch_single_line_size_failure_raises() -> None:
    completer = _FakeCompleter([_result("discarded", finish_reason="max_tokens")])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    with pytest.raises(TranslationEngineError, match="single-line"):
        engine.translate_batch(["source"], source_lang="auto", target_lang="pl")


def test_translate_batch_transport_error_propagates() -> None:
    error = TranslationEngineError(context=ErrorContext(code=ErrorCode.TRANSLATION_FAILED, message="provider failed"))
    engine = LlmTranslateService(LlmTranslateConfig(), completer=_FakeCompleter([error]))

    with pytest.raises(TranslationEngineError, match="provider failed"):
        engine.translate_batch(["source"], source_lang="auto", target_lang="pl")


def test_translate_batch_rejects_non_polish_target_before_completion() -> None:
    completer = _FakeCompleter([])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    with pytest.raises(TranslationConfigError, match="Polish output only"):
        engine.translate_batch(["source"], source_lang="auto", target_lang="en")

    assert completer.requests == []


def test_translate_batch_rejects_blank_text_before_completion() -> None:
    completer = _FakeCompleter([])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    with pytest.raises(TranslationEngineError, match="blank text"):
        engine.translate_batch(["source", "  "], source_lang="auto", target_lang="pl")

    assert completer.requests == []


def test_translate_batch_sends_every_line_in_one_request_without_a_limit() -> None:
    completer = _FakeCompleter([_result(_numbered(*(f"translated {index}" for index in range(300))))])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    texts = [f"source {index}" for index in range(300)]

    result = engine.translate_batch(texts, source_lang="auto", target_lang="pl")

    assert [line.text for line in result] == [f"translated {index}" for index in range(300)]
    assert len(completer.requests) == 1


def test_translate_batch_honours_an_explicit_line_limit() -> None:
    completer = _FakeCompleter(
        [
            _result(_numbered("one", "two")),
            _result(_numbered("three", "four")),
            _result(_numbered("five")),
        ]
    )
    observer = _Observer()
    engine = LlmTranslateService(LlmTranslateConfig(max_batch_lines=2), completer=completer)

    engine.translate_batch(["1", "2", "3", "4", "5"], source_lang="auto", target_lang="pl", observer=observer)

    assert observer.progress_updates == [("llm", 2, 5), ("llm", 4, 5), ("llm", 5, 5)]
    assert [request.user_parts[2] for request in completer.requests] == ["[0] 1\n[1] 2", "[0] 3\n[1] 4", "[0] 5"]


def test_is_available_true_with_completer() -> None:
    engine = LlmTranslateService(
        LlmTranslateConfig(),
        completer=_FakeCompleter([_result(_numbered("a"))]),
    )

    assert engine.is_available


def test_llm_service_rejects_generic_translation_config() -> None:
    config = cast("LlmTranslateConfig", TranslationConfig(engine="llm"))

    with pytest.raises(TypeError, match="requires LlmTranslateConfig"):
        LlmTranslateService(config, completer=_FakeCompleter([]))


def test_llm_config_leaves_the_line_limit_absent_by_default() -> None:
    assert LlmTranslateConfig().max_batch_lines is None


def test_llm_config_rejects_a_non_positive_line_limit() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        LlmTranslateConfig(max_batch_lines=0)


@pytest.mark.parametrize("retries", [-1, 11])
def test_llm_config_rejects_contract_retry_count_outside_range(retries: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 10"):
        LlmTranslateConfig(max_contract_retries=retries)


def test_llm_config_rejects_untrimmed_style_name() -> None:
    with pytest.raises(ValueError, match="trimmed name"):
        LlmTranslateConfig(style_name=" neutral ")


@pytest.mark.parametrize("style_name", ["../neutral", "styles/neutral", "styles\\neutral"])
def test_llm_config_rejects_style_path(style_name: str) -> None:
    with pytest.raises(ValueError, match="not a path"):
        LlmTranslateConfig(style_name=style_name)
