from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from anishift.application.cancellation import (
    CancellationToken,
    EventCancellationToken,
    ThreadEventCancellationToken,
)
from anishift.errors import ErrorCode, ExecutionError


def test_event_cancellation_token_satisfies_protocol_and_is_idempotent() -> None:
    token = EventCancellationToken()
    contract: CancellationToken = token

    assert contract.is_cancelled() is False
    with ThreadPoolExecutor(max_workers=4) as executor:
        tuple(executor.map(lambda _: token.cancel(), range(20)))
    assert contract.is_cancelled() is True
    token.cancel()


def test_cancelled_token_raises_structured_execution_error() -> None:
    token = EventCancellationToken()
    token.raise_if_cancelled()
    token.cancel()

    with pytest.raises(ExecutionError) as captured:
        token.raise_if_cancelled()

    assert captured.value.context.code is ErrorCode.CANCELLED
    assert captured.value.context.details == {}


def test_final_commit_is_serialized_with_concurrent_cancellation() -> None:
    token = EventCancellationToken()
    entered = threading.Event()
    release = threading.Event()
    committed: list[bool] = []

    def action() -> None:
        entered.set()
        assert release.wait(timeout=1.0)

    commit_thread = threading.Thread(target=lambda: committed.append(token.commit_if_active(action)))
    commit_thread.start()
    assert entered.wait(timeout=1.0)
    cancel_thread = threading.Thread(target=token.cancel)
    cancel_thread.start()
    cancel_thread.join(timeout=0.01)
    assert cancel_thread.is_alive() is True
    release.set()
    commit_thread.join(timeout=1.0)
    cancel_thread.join(timeout=1.0)

    assert committed == [True]
    assert token.is_cancelled() is True
    assert token.commit_if_active(lambda: pytest.fail("late commit")) is False


def test_thread_event_adapter_preserves_legacy_cancellation_signal() -> None:
    event = threading.Event()
    token = ThreadEventCancellationToken(event)

    assert token.is_cancelled() is False
    event.set()

    with pytest.raises(ExecutionError) as captured:
        token.raise_if_cancelled()

    assert captured.value.context.code is ErrorCode.CANCELLED
