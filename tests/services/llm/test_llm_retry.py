from __future__ import annotations

import threading

import pytest

from anishift.errors import AniShiftError, ErrorCode
from anishift.services.llm import (
    LlmAuthError,
    LlmCancelledError,
    LlmContextLengthError,
    LlmError,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequestError,
    LlmResponse,
    LlmTimeoutError,
    LlmUsage,
)
from anishift.services.llm._retry import retry_across_keys
from anishift.services.llm.config import DEFAULT_RETRY_WAITS_S

type _Outcome = LlmResponse | LlmError
type _Script = dict[int, list[_Outcome]]


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[str] = []

    def before_attempt(self) -> None:
        self.events.append("before")

    def on_retry(self, error: AniShiftError, *, attempt: int, max_attempts: int) -> None:
        self.events.append(f"retry:{type(error).__name__}:{attempt}/{max_attempts}")

    def on_success(self) -> None:
        self.events.append("success")

    def on_fatal_failure(self, error: AniShiftError) -> None:
        self.events.append(f"fatal:{type(error).__name__}")


class ScriptedKeys:
    def __init__(self, script: _Script) -> None:
        self.script: _Script = script
        self.calls: list[int] = []

    def __call__(self, key_index: int) -> LlmResponse:
        self.calls.append(key_index)
        outcome: _Outcome = self.script[key_index].pop(0)
        if isinstance(outcome, LlmError):
            raise outcome
        return outcome


def _run(
    script: _Script,
    *,
    waits_s: tuple[float, ...] = DEFAULT_RETRY_WAITS_S,
    observer: RecordingObserver | None = None,
) -> tuple[LlmResponse, ScriptedKeys, list[float]]:
    operation = ScriptedKeys(script)
    delays: list[float] = []
    response: LlmResponse = retry_across_keys(
        operation,
        provider="gemini",
        key_count=len(script),
        waits_s=waits_s,
        observer=observer,
        sleep=delays.append,
    )
    return response, operation, delays


@pytest.mark.unit
def test_one_key_gets_five_attempts_with_the_default_waits_then_one_final_error() -> None:
    operation = ScriptedKeys({0: [LlmProviderUnavailableError(f"busy {index}") for index in range(5)]})
    delays: list[float] = []
    observer = RecordingObserver()

    with pytest.raises(LlmProviderUnavailableError) as failure:
        retry_across_keys(
            operation,
            provider="gemini",
            key_count=1,
            waits_s=DEFAULT_RETRY_WAITS_S,
            observer=observer,
            sleep=delays.append,
        )

    assert operation.calls == [0, 0, 0, 0, 0]
    assert delays == [10.0, 30.0, 60.0, 60.0]
    assert failure.value.context.message == "All 1 gemini API key failed after 5 attempts; last error: busy 4"
    assert failure.value.context.code is ErrorCode.LLM_PROVIDER_UNAVAILABLE
    assert isinstance(failure.value.__cause__, LlmProviderUnavailableError)
    assert observer.events.count("before") == 5
    assert observer.events[-1] == "fatal:LlmProviderUnavailableError"
    assert [event for event in observer.events if event.startswith("retry")] == [
        "retry:LlmProviderUnavailableError:2/5",
        "retry:LlmProviderUnavailableError:3/5",
        "retry:LlmProviderUnavailableError:4/5",
        "retry:LlmProviderUnavailableError:5/5",
    ]


@pytest.mark.unit
def test_a_failing_key_hands_the_request_to_the_next_key_without_waiting() -> None:
    response: LlmResponse = _response("translated")

    result, operation, delays = _run({0: [LlmRateLimitError("limited")], 1: [response]})

    assert result is response
    assert operation.calls == [0, 1]
    assert delays == []


@pytest.mark.unit
def test_three_keys_failing_every_round_wait_only_between_rounds() -> None:
    errors: _Script = {key: [LlmTimeoutError(f"key {key} round {index}") for index in range(5)] for key in range(3)}

    with pytest.raises(LlmTimeoutError) as failure:
        _run(errors)

    assert failure.value.context.message == "All 3 gemini API keys failed after 15 attempts; last error: key 2 round 4"


@pytest.mark.unit
def test_rounds_try_keys_in_order_and_wait_once_per_failed_round() -> None:
    response: LlmResponse = _response("done")
    script: _Script = {
        0: [LlmProviderUnavailableError("busy"), LlmProviderUnavailableError("busy"), response],
        1: [LlmTimeoutError("slow"), LlmTimeoutError("slow")],
        2: [LlmRateLimitError("limited"), LlmRateLimitError("limited")],
    }

    result, operation, delays = _run(script)

    assert result is response
    assert operation.calls == [0, 1, 2, 0, 1, 2, 0]
    assert delays == [10.0, 30.0]


@pytest.mark.unit
@pytest.mark.parametrize("rejection", [LlmAuthError, LlmQuotaError, LlmPaymentError])
def test_a_rejected_key_is_skipped_for_the_rest_of_the_request(rejection: type[LlmError]) -> None:
    response: LlmResponse = _response("done")
    script: _Script = {0: [rejection("rejected")], 1: [LlmProviderUnavailableError("busy"), response]}

    result, operation, delays = _run(script)

    assert result is response
    assert operation.calls == [0, 1, 1]
    assert delays == [10.0]


@pytest.mark.unit
def test_every_key_rejected_fails_at_once_naming_the_provider_and_key_count() -> None:
    observer = RecordingObserver()

    with pytest.raises(LlmAuthError) as failure:
        _run({0: [LlmQuotaError("daily")], 1: [LlmAuthError("invalid")]}, observer=observer)

    assert failure.value.context.message == "All 2 gemini API keys failed after 2 attempts; last error: invalid"
    assert observer.events[-1] == "fatal:LlmAuthError"


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [
        LlmContextLengthError("too long"),
        LlmModelError("no model"),
        LlmOutputBlockedError("blocked"),
        LlmRequestError("bad request"),
        LlmCancelledError("cancelled"),
    ],
)
def test_a_request_error_ends_at_once_without_trying_another_key(error: LlmError) -> None:
    observer = RecordingObserver()
    operation = ScriptedKeys({0: [error], 1: [_response("unused")]})

    with pytest.raises(type(error)) as failure:
        retry_across_keys(operation, provider="gemini", key_count=2, waits_s=(10.0,), observer=observer)

    assert failure.value is error
    assert operation.calls == [0]
    assert observer.events == ["before", f"fatal:{type(error).__name__}"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("retry_after_s", "expected"),
    [(3.25, 3.25), (10.0, 10.0), (45.0, 10.0), (-1.0, 10.0), (float("nan"), 10.0), (float("inf"), 10.0)],
)
def test_retry_after_shortens_a_wait_but_never_lengthens_it(retry_after_s: float, expected: float) -> None:
    response: LlmResponse = _response("done")

    _result, _operation, delays = _run({0: [LlmRateLimitError("limited", retry_after_s=retry_after_s), response]})

    assert delays == [expected]


@pytest.mark.unit
def test_cancel_before_the_first_attempt_sends_nothing() -> None:
    cancel = threading.Event()
    cancel.set()
    operation = ScriptedKeys({0: [_response("unused")]})

    with pytest.raises(LlmCancelledError):
        retry_across_keys(operation, provider="gemini", key_count=1, waits_s=(), cancel=cancel)

    assert operation.calls == []


@pytest.mark.unit
def test_cancel_during_a_wait_stops_before_the_next_round() -> None:
    cancel = threading.Event()
    operation = ScriptedKeys({0: [LlmTimeoutError("slow"), _response("unused")]})

    class CancellingObserver(RecordingObserver):
        def on_retry(self, error: AniShiftError, *, attempt: int, max_attempts: int) -> None:
            cancel.set()

    with pytest.raises(LlmCancelledError):
        retry_across_keys(
            operation, provider="gemini", key_count=1, waits_s=(10.0,), observer=CancellingObserver(), cancel=cancel
        )

    assert operation.calls == [0]


@pytest.mark.unit
def test_a_success_finished_after_cancel_is_discarded() -> None:
    cancel = threading.Event()

    def operation(key_index: int) -> LlmResponse:
        cancel.set()
        return _response(f"discarded {key_index}")

    with pytest.raises(LlmCancelledError):
        retry_across_keys(operation, provider="gemini", key_count=1, waits_s=(), cancel=cancel)


def _response(text: str) -> LlmResponse:
    return LlmResponse(
        text=text,
        engine_id="fake",
        provider_model_id="fake-model",
        finish_reason="stop",
        latency_ms=1.0,
        usage=LlmUsage(),
    )
