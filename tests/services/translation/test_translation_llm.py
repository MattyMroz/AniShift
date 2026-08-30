from __future__ import annotations

import json
from collections.abc import Iterable
from typing import cast

import pytest

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.json_contract import (
    JsonContractError,
    parse_translation_response,
    serialize_translation_request,
)
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


def _translations(*texts: str) -> str:
    return json.dumps(
        {"translations": [{"id": index, "translated": text} for index, text in enumerate(texts)]},
        ensure_ascii=False,
    )


def _context_error() -> TranslationContextLengthError:
    return TranslationContextLengthError(
        context=ErrorContext(
            code=ErrorCode.LLM_CONTEXT_EXCEEDED,
            message="context exceeded",
        )
    )


def test_serialize_translation_request_uses_exact_contract() -> None:
    serialized = serialize_translation_request(["same", "same", "first\nsecond"])

    assert serialized == (
        '{"subtitles":[{"id":0,"text":"same"},{"id":1,"text":"same"},{"id":2,"text":"first\\nsecond"}]}'
    )


def test_serialize_translation_request_preserves_unicode_and_quotes() -> None:
    serialized = serialize_translation_request(['Zażółć "gęślą"'])

    assert "Zażółć" in serialized
    assert "\\u" not in serialized
    assert json.loads(serialized) == {"subtitles": [{"id": 0, "text": 'Zażółć "gęślą"'}]}


def test_parse_translation_response_preserves_internal_newlines() -> None:
    result = parse_translation_response(
        '  {"translations":[{"id":0,"translated":"  pierwszy\\ndrugi  "}]}  ',
        1,
    )

    assert result == ["pierwszy\ndrugi"]


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        '```json\n{"translations":[]}\n```',
        '{"translations":[],"extra":true}',
        '{"translations":{}}',
        '{"translations":[{"id":0,"translated":"a","extra":true}]}',
        '{"translations":[{"id":true,"translated":"a"}]}',
        '{"translations":[{"id":0,"translated":1}]}',
        '{"translations":[{"id":0,"translated":"  "}]}',
        '{"translations":[{"id":1,"translated":"a"}]}',
        '{"translations":[{"id":0,"translated":"a"},{"id":0,"translated":"b"}]}',
        '{"translations":[{"id":0,"translated":"a"}],"translations":[]}',
        '{"translations":[{"id":0,"translated":"a"}],"number":NaN}',
    ],
)
def test_parse_translation_response_rejects_contract_violations(response: str) -> None:
    with pytest.raises(JsonContractError):
        parse_translation_response(response, 1)


def test_parse_translation_response_rejects_wrong_count_and_order() -> None:
    response = _translations("zero", "one")
    payload = json.loads(response)
    payload["translations"].reverse()

    with pytest.raises(JsonContractError, match="kolejno"):
        parse_translation_response(json.dumps(payload), 2)
    with pytest.raises(JsonContractError, match="dokładnie 1"):
        parse_translation_response(response, 1)


def test_translate_batch_builds_ordered_prompt_parts_and_json_input() -> None:
    completer = _FakeCompleter([_result(_translations("jeden", "dwa"))])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    result = engine.translate_batch(["one", "two"], source_lang="auto", target_lang="pl")

    request = completer.requests[0]
    assert [line.text for line in result] == ["jeden", "dwa"]
    assert len(request.user_parts) == 3
    assert "polski" in request.system
    assert "Przetłumacz" in request.user_parts[0]
    assert "neutralny" in request.user_parts[1]
    assert json.loads(request.user_parts[2]) == {"subtitles": [{"id": 0, "text": "one"}, {"id": 1, "text": "two"}]}


def test_translate_empty_batch_does_not_call_completer() -> None:
    completer = _FakeCompleter([])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)

    assert engine.translate_batch([], source_lang="auto", target_lang="pl") == []
    assert completer.requests == []


def test_translate_batch_retries_with_only_latest_safe_diagnosis() -> None:
    completer = _FakeCompleter(
        [
            _result("raw invalid response"),
            _result('{"wrong":[]}'),
            _result(_translations("dobrze")),
        ]
    )
    engine = LlmTranslateService(
        LlmTranslateConfig(max_contract_retries=2),
        completer=completer,
    )

    result = engine.translate_batch(["source"], source_lang="auto", target_lang="pl")

    first_retry = completer.requests[1].user_parts
    second_retry = completer.requests[2].user_parts
    assert [line.text for line in result] == ["dobrze"]
    assert len(first_retry) == 4
    assert len(second_retry) == 4
    assert "poprawnym dokumentem JSON" in first_retry[-1]
    assert "klucze: translations" in second_retry[-1]
    assert "raw invalid response" not in first_retry[-1]
    assert first_retry[:3] == second_retry[:3]


def test_translate_batch_does_not_split_invalid_json_after_retries() -> None:
    completer = _FakeCompleter([_result("bad"), _result("still bad")])
    engine = LlmTranslateService(
        LlmTranslateConfig(max_contract_retries=1),
        completer=completer,
    )

    with pytest.raises(TranslationEngineError, match="valid translation JSON"):
        engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")

    assert len(completer.requests) == 2


def test_exhausted_contract_error_reports_only_latest_safe_diagnosis() -> None:
    completer = _FakeCompleter([_result("raw response"), _result('{"wrong":[]}')])
    engine = LlmTranslateService(
        LlmTranslateConfig(max_contract_retries=1),
        completer=completer,
    )

    with pytest.raises(TranslationEngineError) as error:
        engine.translate_batch(["a"], source_lang="auto", target_lang="pl")

    assert "klucze: translations" in str(error.value)
    assert "raw response" not in str(error.value)


def test_translate_batch_output_limit_splits_without_contract_retry() -> None:
    completer = _FakeCompleter(
        [
            _result("discarded", finish_reason="length"),
            _result(_translations("jeden")),
            _result(_translations("dwa")),
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
            _result(_translations("jeden")),
            _result(_translations("dwa")),
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


def test_translate_batch_splits_input_above_one_thousand_lines() -> None:
    first = _translations(*(f"translated {index}" for index in range(1000)))
    completer = _FakeCompleter([_result(first), _result(_translations("translated 1000"))])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    texts = [f"source {index}" for index in range(1001)]

    result = engine.translate_batch(texts, source_lang="auto", target_lang="pl")

    assert len(result) == 1001
    assert len(completer.requests) == 2


def test_translate_batch_reports_completed_line_batches() -> None:
    completer = _FakeCompleter(
        [
            _result(_translations("one", "two")),
            _result(_translations("three", "four")),
            _result(_translations("five")),
        ]
    )
    observer = _Observer()
    engine = LlmTranslateService(LlmTranslateConfig(max_batch_lines=2), completer=completer)

    engine.translate_batch(["1", "2", "3", "4", "5"], source_lang="auto", target_lang="pl", observer=observer)

    assert observer.progress_updates == [("llm", 2, 5), ("llm", 4, 5), ("llm", 5, 5)]


def test_is_available_true_with_completer() -> None:
    engine = LlmTranslateService(
        LlmTranslateConfig(),
        completer=_FakeCompleter([_result(_translations("a"))]),
    )

    assert engine.is_available


def test_llm_service_rejects_generic_translation_config() -> None:
    config = cast("LlmTranslateConfig", TranslationConfig(engine="llm"))

    with pytest.raises(TypeError, match="requires LlmTranslateConfig"):
        LlmTranslateService(config, completer=_FakeCompleter([]))


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
