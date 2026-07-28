from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import pytest

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.prompts import GlossaryEntry, PromptContext
from anishift.services.translation.engines.llm.service import LlmTranslateService, _parse_numbered
from anishift.services.translation.errors import TranslationEngineError
from anishift.services.translation.protocols import (
    LlmCompletionRequest,
    LlmCompletionResult,
)


class _FakeCompleter:
    def __init__(
        self,
        responses: Iterable[LlmCompletionResult],
        *,
        error: TranslationEngineError | None = None,
    ) -> None:
        self.responses: list[LlmCompletionResult] = list(responses)
        self.error = error
        self.requests: list[LlmCompletionRequest] = []

    def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


def _result(text: str, finish_reason: str = "stop") -> LlmCompletionResult:
    return LlmCompletionResult(text=text, finish_reason=finish_reason)


def test_parse_numbered_clean() -> None:
    assert _parse_numbered("[1] a\n[2] b\n[3] c", 3) == ["a", "b", "c"]


def test_parse_numbered_ignores_noise() -> None:
    text = "Oto tłumaczenie:\n```\n[1] a\n[2] b\n```\nMam nadzieję że pomogłem"
    assert _parse_numbered(text, 2) == ["a", "b"]


def test_parse_numbered_detects_missing_index() -> None:
    assert _parse_numbered("[1] a\n[3] c", 3) is None


def test_parse_numbered_detects_duplicate() -> None:
    assert _parse_numbered("[1] a\n[1] b\n[2] c", 2) is None


def test_parse_numbered_detects_empty_translation() -> None:
    assert _parse_numbered("[1]   \n[2] b", 2) is None


def test_translate_batch_happy_path() -> None:
    completer = _FakeCompleter([_result("[1] jeden\n[2] dwa")])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    result = engine.translate_batch(["one", "two"], source_lang="auto", target_lang="pl")
    assert [line.text for line in result] == ["jeden", "dwa"]
    assert all(line.ok for line in result)
    assert [request.identity.purpose for request in completer.requests] == ["translation"]


def test_translate_batch_runs_one_repair_before_split() -> None:
    completer = _FakeCompleter([_result("[1] only"), _result("[1] jeden\n[2] dwa")])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    result = engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")
    assert [line.text for line in result] == ["jeden", "dwa"]
    assert [request.identity.purpose for request in completer.requests] == [
        "translation",
        "translation_repair",
    ]


def test_translate_batch_splits_after_failed_repair() -> None:
    completer = _FakeCompleter(
        [
            _result("[1] only"),
            _result("[1] still only"),
            _result("[1] jeden"),
            _result("[1] dwa"),
        ]
    )
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    result = engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")
    assert [line.text for line in result] == ["jeden", "dwa"]
    assert len(completer.requests) == 4


def test_translate_batch_output_limit_splits_without_repair() -> None:
    completer = _FakeCompleter(
        [
            _result("[1] partial", finish_reason="length"),
            _result("[1] jeden"),
            _result("[1] dwa"),
        ]
    )
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    result = engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")
    assert [line.text for line in result] == ["jeden", "dwa"]
    assert all(request.identity.purpose == "translation" for request in completer.requests)


def test_translate_batch_single_line_failure_raises() -> None:
    completer = _FakeCompleter([_result("bad"), _result("still bad")])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    with pytest.raises(TranslationEngineError, match="numbered output"):
        engine.translate_batch(["source"], source_lang="auto", target_lang="pl")


def test_translate_batch_transport_error_propagates() -> None:
    error = TranslationEngineError(context=ErrorContext(code=ErrorCode.TRANSLATION_FAILED, message="provider failed"))
    engine = LlmTranslateService(LlmTranslateConfig(), completer=_FakeCompleter([], error=error))
    with pytest.raises(TranslationEngineError, match="provider failed"):
        engine.translate_batch(["source"], source_lang="auto", target_lang="pl")


def test_translate_batch_splits_input_above_one_thousand_lines() -> None:
    first = "\n".join(f"[{index}] translated {index}" for index in range(1, 1001))
    completer = _FakeCompleter([_result(first), _result("[1] translated 1001")])
    engine = LlmTranslateService(LlmTranslateConfig(), completer=completer)
    texts = [f"source {index}" for index in range(1, 1002)]
    result = engine.translate_batch(texts, source_lang="auto", target_lang="pl")
    assert len(result) == 1001
    assert len(completer.requests) == 2


def test_is_available_true_with_completer() -> None:
    engine = LlmTranslateService(LlmTranslateConfig(), completer=_FakeCompleter([_result("[1] a")]))
    assert engine.is_available


def test_llm_service_rejects_generic_translation_config() -> None:
    config = cast("LlmTranslateConfig", TranslationConfig(engine="llm"))

    with pytest.raises(TypeError, match="requires LlmTranslateConfig"):
        LlmTranslateService(config, completer=_FakeCompleter([]))


def test_translate_request_reports_omitted_glossary_entries() -> None:
    completer = _FakeCompleter([_result("[1] translated")])
    context = PromptContext(
        glossary=tuple(GlossaryEntry(source=str(index), target="x") for index in range(201)),
    )
    engine = LlmTranslateService(
        LlmTranslateConfig(context=context),
        completer=completer,
    )

    engine.translate_batch(["source"], source_lang="auto", target_lang="pl")

    assert completer.requests[0].omitted_context_items == 1
