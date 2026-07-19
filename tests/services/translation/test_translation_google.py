import asyncio
from collections.abc import Coroutine
from typing import Any

from anishift.services.translation.engines.google._batching import translate_lines
from anishift.services.translation.engines.google.constants import LINE_SEPARATOR
from anishift.services.translation.types import BatchedLine


def _run(coro: Coroutine[Any, Any, list[BatchedLine]]) -> list[BatchedLine]:
    return asyncio.run(coro)


def test_separator_join_maps_lines_in_order() -> None:
    texts = ["hello", "world", "cat"]

    async def fake(joined: str) -> tuple[str, str | None]:
        parts = joined.split(LINE_SEPARATOR)
        return LINE_SEPARATOR.join(f"PL-{p}" for p in parts), "en"

    result = _run(translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake))
    assert [line.text for line in result] == ["PL-hello", "PL-world", "PL-cat"]
    assert all(line.ok for line in result)
    assert all(line.detected_lang == "en" for line in result)


def test_falls_back_to_per_line_on_segment_mismatch() -> None:
    texts = ["a", "b", "c"]
    calls: list[str] = []

    async def fake(joined: str) -> tuple[str, str | None]:
        calls.append(joined)
        if LINE_SEPARATOR in joined or "\n" in joined:
            return "wrong-merge", "en"  # collapses -> triggers ladder
        return f"PL-{joined}", "en"

    result = _run(translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake))
    assert [line.text for line in result] == ["PL-a", "PL-b", "PL-c"]


def test_empty_input_returns_empty() -> None:
    async def fake(joined: str) -> tuple[str, str | None]:
        return joined, None

    assert _run(translate_lines([], batch_size=50, max_chars=15000, translate_joined=fake)) == []


def test_per_line_failure_pads_source() -> None:
    texts = ["x", "y"]

    async def fake(joined: str) -> tuple[str, str | None]:
        if LINE_SEPARATOR in joined or "\n" in joined:
            return "merged", None  # force ladder to per-line
        raise RuntimeError("boom")  # per-line call fails -> pad source

    result = _run(translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake))
    assert [line.text for line in result] == ["x", "y"]
    assert all(not line.ok for line in result)
