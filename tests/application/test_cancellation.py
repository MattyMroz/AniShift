from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from anishift.application.cancellation import CancellationToken, EventCancellationToken
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
