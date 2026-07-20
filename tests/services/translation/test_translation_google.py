import asyncio
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines.google._batching import translate_lines
from anishift.services.translation.engines.google.constants import LINE_SEPARATOR, MAX_CHARS_PER_REQUEST
from anishift.services.translation.engines.google.service import GoogleService
from anishift.services.translation.types import BatchedLine


def _run(coro: Coroutine[Any, Any, list[BatchedLine]]) -> list[BatchedLine]:
    return asyncio.run(coro)


def test_separator_join_maps_lines_in_order() -> None:
    texts = ["hello", "world", "cat"]

    async def fake(joined: str) -> str:
        parts = joined.split(LINE_SEPARATOR)
        return LINE_SEPARATOR.join(f"PL-{p}" for p in parts)

    result = _run(translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake))
    assert [line.text for line in result] == ["PL-hello", "PL-world", "PL-cat"]
    assert all(line.ok for line in result)


def test_falls_back_to_per_line_on_segment_mismatch() -> None:
    texts = ["a", "b", "c"]
    calls: list[str] = []

    async def fake(joined: str) -> str:
        calls.append(joined)
        if LINE_SEPARATOR in joined or "\n" in joined:
            return "wrong-merge"
        return f"PL-{joined}"

    result = _run(translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake))
    assert [line.text for line in result] == ["PL-a", "PL-b", "PL-c"]


def test_empty_input_returns_empty() -> None:
    async def fake(joined: str) -> str:
        return joined

    assert _run(translate_lines([], batch_size=50, max_chars=15000, translate_joined=fake)) == []


def test_per_line_failure_pads_source() -> None:
    texts = ["x", "y"]

    async def fake(joined: str) -> str:
        if LINE_SEPARATOR in joined or "\n" in joined:
            return "merged"
        raise RuntimeError("boom")

    result = _run(translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake))
    assert [line.text for line in result] == ["x", "y"]
    assert all(not line.ok for line in result)


def test_facade_built_google_uses_engine_char_limit_not_domain_default() -> None:
    engine = GoogleService(TranslationConfig(engine="google"))
    assert engine._config.max_chars_per_request == MAX_CHARS_PER_REQUEST
    assert engine._config.max_chars_per_request == 15000


def test_retry_retries_transient_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.services.translation.engines.google.service.RETRY_BACKOFF_BASE_S", 0.0)

    class _FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        async def translate(self, text: str, dest: str) -> SimpleNamespace:
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("boom")
            return SimpleNamespace(text=f"PL-{text}")

    engine = GoogleService(TranslationConfig(engine="google", max_retries=2))
    client = _FlakyClient()
    assert asyncio.run(engine._call_with_retry(client, "hi", dest="pl")) == "PL-hi"
    assert client.calls == 2


def test_retry_raises_non_transient_immediately() -> None:
    class _BrokenClient:
        def __init__(self) -> None:
            self.calls = 0

        async def translate(self, text: str, dest: str) -> SimpleNamespace:
            self.calls += 1
            raise ValueError("parse failure")

    engine = GoogleService(TranslationConfig(engine="google", max_retries=3))
    client = _BrokenClient()
    with pytest.raises(ValueError, match="parse failure"):
        asyncio.run(engine._call_with_retry(client, "hi", dest="pl"))
    assert client.calls == 1


def test_retry_exhausts_attempts_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.services.translation.engines.google.service.RETRY_BACKOFF_BASE_S", 0.0)

    class _DownClient:
        def __init__(self) -> None:
            self.calls = 0

        async def translate(self, text: str, dest: str) -> SimpleNamespace:
            self.calls += 1
            raise httpx.ConnectTimeout("down")

    engine = GoogleService(TranslationConfig(engine="google", max_retries=2))
    client = _DownClient()
    with pytest.raises(httpx.ConnectTimeout):
        asyncio.run(engine._call_with_retry(client, "hi", dest="pl"))
    assert client.calls == 3
