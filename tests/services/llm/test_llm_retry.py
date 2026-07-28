from __future__ import annotations

import threading
from collections.abc import Callable

import pytest

from anishift.errors import AniShiftError, TransientError
from anishift.services.llm import (
    LlmAuthError,
    LlmCancelledError,
    LlmMessage,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRequest,
    LlmResponse,
    LlmRole,
    LlmTimeoutError,
    LlmUsage,
    TextPart,
)
from anishift.services.llm._retry import retry_transient


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[str] = []

    def before_attempt(self) -> None:
        self.events.append("before")

    def on_transient_failure(self, error: TransientError) -> None:
        self.events.append(f"transient:{type(error).__name__}")

    def on_success(self) -> None:
        self.events.append("success")

    def on_fatal_failure(self, error: AniShiftError) -> None:
        self.events.append(f"fatal:{type(error).__name__}")


def test_retry_transient_succeeds_after_exact_retries() -> None:
    response: LlmResponse = _response("translated")
    outcomes: list[LlmResponse | TransientError] = [
        LlmTimeoutError("first"),
        LlmProviderUnavailableError("second"),
        response,
    ]
    calls: int = 0
    delays: list[float] = []
    observer = RecordingObserver()

    def operation() -> LlmResponse:
        nonlocal calls
        calls += 1
        outcome: LlmResponse | TransientError = outcomes.pop(0)
        if isinstance(outcome, TransientError):
            raise outcome
        return outcome

    result: LlmResponse = retry_transient(
        operation,
        max_retries=2,
        observer=observer,
        sleep=delays.append,
    )

    assert result is response
    assert calls == 3
    assert delays == [1.0, 2.0]
    assert observer.events == [
        "before",
        "transient:LlmTimeoutError",
        "before",
        "transient:LlmProviderUnavailableError",
        "before",
        "success",
    ]


def test_retry_transient_raises_exhausted_error_without_extra_sleep() -> None:
    calls: int = 0
    delays: list[float] = []
    observer = RecordingObserver()

    def operation() -> LlmResponse:
        nonlocal calls
        calls += 1
        raise LlmTimeoutError(f"attempt {calls}")

    with pytest.raises(LlmTimeoutError, match="attempt 4"):
        retry_transient(
            operation,
            max_retries=3,
            observer=observer,
            sleep=delays.append,
        )

    assert calls == 4
    assert delays == [1.0, 2.0, 4.0]
    assert observer.events.count("before") == 4
    assert observer.events.count("transient:LlmTimeoutError") == 4
    assert "success" not in observer.events


def test_retry_transient_does_not_retry_fatal_error() -> None:
    calls: int = 0
    delays: list[float] = []
    observer = RecordingObserver()

    def operation() -> LlmResponse:
        nonlocal calls
        calls += 1
        raise ValueError("fatal")

    with pytest.raises(ValueError, match="fatal"):
        retry_transient(
            operation,
            max_retries=5,
            observer=observer,
            sleep=delays.append,
        )

    assert calls == 1
    assert delays == []
    assert observer.events == ["before"]


def test_retry_observer_sees_typed_fatal_failure() -> None:
    observer = RecordingObserver()

    def operation() -> LlmResponse:
        raise LlmAuthError("auth")

    with pytest.raises(LlmAuthError):
        retry_transient(
            operation,
            max_retries=5,
            observer=observer,
        )

    assert observer.events == ["before", "fatal:LlmAuthError"]


@pytest.mark.parametrize(
    "build_error",
    [
        pytest.param(
            lambda: LlmRateLimitError("limited", retry_after_s=7.5),
            id="rate-limit",
        ),
        pytest.param(
            lambda: LlmProviderUnavailableError("offline", retry_after_s=3.25),
            id="unavailable",
        ),
    ],
)
def test_retry_transient_respects_retry_after(
    build_error: Callable[[], LlmRateLimitError | LlmProviderUnavailableError],
) -> None:
    response: LlmResponse = _response("done")
    error: LlmRateLimitError | LlmProviderUnavailableError = build_error()
    outcomes: list[LlmResponse | TransientError] = [error, response]
    delays: list[float] = []

    def operation() -> LlmResponse:
        outcome: LlmResponse | TransientError = outcomes.pop(0)
        if isinstance(outcome, TransientError):
            raise outcome
        return outcome

    assert retry_transient(operation, max_retries=1, sleep=delays.append) is response
    assert delays == [error.retry_after_s]


@pytest.mark.parametrize("retry_after_s", [-1.0, float("nan"), float("inf")])
def test_retry_transient_ignores_invalid_retry_after(retry_after_s: float) -> None:
    response: LlmResponse = _response("done")
    outcomes: list[LlmResponse | TransientError] = [
        LlmRateLimitError("limited", retry_after_s=retry_after_s),
        response,
    ]
    delays: list[float] = []

    def operation() -> LlmResponse:
        outcome: LlmResponse | TransientError = outcomes.pop(0)
        if isinstance(outcome, TransientError):
            raise outcome
        return outcome

    assert retry_transient(operation, max_retries=1, sleep=delays.append) is response
    assert delays == [1.0]


def test_retry_transient_caps_backoff() -> None:
    response: LlmResponse = _response("done")
    outcomes: list[LlmResponse | TransientError] = [LlmTimeoutError(str(index)) for index in range(5)]
    outcomes.append(response)
    delays: list[float] = []

    def operation() -> LlmResponse:
        outcome: LlmResponse | TransientError = outcomes.pop(0)
        if isinstance(outcome, TransientError):
            raise outcome
        return outcome

    assert retry_transient(operation, max_retries=5, sleep=delays.append) is response
    assert delays == [1.0, 2.0, 4.0, 4.0, 4.0]


def test_retry_transient_cancels_before_first_attempt() -> None:
    cancel = threading.Event()
    cancel.set()
    calls: int = 0

    def operation() -> LlmResponse:
        nonlocal calls
        calls += 1
        return _response("unused")

    with pytest.raises(LlmCancelledError):
        retry_transient(operation, max_retries=2, cancel=cancel)

    assert calls == 0


def test_retry_transient_cancels_during_backoff() -> None:
    cancel = threading.Event()
    calls: int = 0

    class CancellingObserver:
        def before_attempt(self) -> None:
            return None

        def on_transient_failure(self, error: TransientError) -> None:
            cancel.set()

        def on_success(self) -> None:
            return None

        def on_fatal_failure(self, error: AniShiftError) -> None:
            del error

    def operation() -> LlmResponse:
        nonlocal calls
        calls += 1
        raise LlmTimeoutError("timeout")

    with pytest.raises(LlmCancelledError):
        retry_transient(
            operation,
            max_retries=2,
            observer=CancellingObserver(),
            cancel=cancel,
        )

    assert calls == 1


def test_retry_transient_discards_success_completed_after_cancellation() -> None:
    cancel = threading.Event()

    def operation() -> LlmResponse:
        cancel.set()
        return _response("discarded")

    with pytest.raises(LlmCancelledError):
        retry_transient(operation, max_retries=0, cancel=cancel)


def _response(text: str) -> LlmResponse:
    request = LlmRequest(
        messages=(LlmMessage(role=LlmRole.USER, parts=(TextPart(text),)),),
    )
    return LlmResponse(
        text=request.messages[0].parts[0].text,
        engine_id="fake",
        provider_model_id="fake-model",
        finish_reason="stop",
        latency_ms=1.0,
        usage=LlmUsage(),
    )
