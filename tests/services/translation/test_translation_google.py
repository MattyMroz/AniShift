import httpx
import pytest

from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines.google._batching import translate_lines
from anishift.services.translation.engines.google.api_backend import (
    MobileTranslateClient,
    _extract_translation,
)
from anishift.services.translation.engines.google.constants import LINE_SEPARATOR, MAX_CHARS_PER_REQUEST, USER_AGENT
from anishift.services.translation.engines.google.service import GoogleService
from anishift.services.translation.errors import TranslationEngineError, TranslationRateLimitError
from anishift.services.translation.protocols import TranslationObserver


class _Observer:
    def __init__(self) -> None:
        self.retries: list[tuple[str, int, int]] = []

    def progress(self, engine_id: str, completed: int, total: int) -> None:
        del engine_id, completed, total

    def retry(
        self,
        engine_id: str,
        attempt: int,
        max_attempts: int,
        reason: str | None = None,
    ) -> None:
        del reason
        self.retries.append((engine_id, attempt, max_attempts))

    def fallback(self, failed_engine_id: str, next_engine_id: str) -> None:
        del failed_engine_id, next_engine_id


def _page(text: str) -> str:
    return f'<html><body><div class="result-container">{text}</div></body></html>'


def test_separator_join_maps_lines_in_order() -> None:
    texts = ["hello", "world", "cat"]

    def fake(joined: str) -> str:
        parts = joined.split(LINE_SEPARATOR)
        return LINE_SEPARATOR.join(f"PL-{p}" for p in parts)

    result = translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake)
    assert [line.text for line in result] == ["PL-hello", "PL-world", "PL-cat"]
    assert all(line.ok for line in result)


def test_falls_back_to_per_line_on_segment_mismatch() -> None:
    texts = ["a", "b", "c"]

    def fake(joined: str) -> str:
        if LINE_SEPARATOR in joined or "\n" in joined:
            return "wrong-merge"
        return f"PL-{joined}"

    result = translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake)
    assert [line.text for line in result] == ["PL-a", "PL-b", "PL-c"]


def test_empty_input_returns_empty() -> None:
    def fake(joined: str) -> str:
        return joined

    assert translate_lines([], batch_size=50, max_chars=15000, translate_joined=fake) == []


def test_per_line_failure_pads_source() -> None:
    texts = ["x", "y"]

    def fake(joined: str) -> str:
        if LINE_SEPARATOR in joined or "\n" in joined:
            return "merged"
        raise RuntimeError("boom")

    result = translate_lines(texts, batch_size=50, max_chars=15000, translate_joined=fake)
    assert [line.text for line in result] == ["x", "y"]
    assert all(not line.ok for line in result)


def test_empty_per_line_response_is_not_successful() -> None:
    def fake(joined: str) -> str:
        return "merged" if LINE_SEPARATOR in joined or "\n" in joined else " \t "

    result = translate_lines(["first", "second"], batch_size=50, max_chars=15000, translate_joined=fake)

    assert [line.text for line in result] == ["first", "second"]
    assert all(not line.ok for line in result)


def test_facade_built_google_uses_engine_char_limit_not_domain_default() -> None:
    engine = GoogleService(TranslationConfig(engine="google"))
    assert engine._config.max_chars_per_request == MAX_CHARS_PER_REQUEST
    assert engine._config.max_chars_per_request == 15000


def test_extract_reads_the_result_container_and_unescapes_it() -> None:
    assert _extract_translation(_page("Dzie&#324; dobry")) == "Dzień dobry"


def test_extract_rejects_a_page_without_a_result() -> None:
    with pytest.raises(TranslationEngineError):
        _extract_translation("<html><body>Sorry...</body></html>")


def test_client_sends_a_browser_user_agent() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["User-Agent"]
        seen["url"] = str(request.url)
        return httpx.Response(200, text=_page("PL"))

    client = MobileTranslateClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    try:
        assert client.translate("hi", source_lang="en", target_lang="pl") == "PL"
    finally:
        client.close()

    assert seen["ua"] == USER_AGENT
    assert "tl=pl" in seen["url"]
    assert "sl=en" in seen["url"]


@pytest.mark.parametrize("status", [429, 503])
def test_client_maps_throttling_to_a_retryable_error(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status, text="Sorry...")

    client = MobileTranslateClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TranslationRateLimitError):
            client.translate("hi", source_lang="en", target_lang="pl")
    finally:
        client.close()


def test_retry_repeats_throttled_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.services.translation.engines.google.service.RETRY_BACKOFF_BASE_S", 0.0)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, text="Sorry...")
        return httpx.Response(200, text=_page("PL-hi"))

    engine = GoogleService(TranslationConfig(engine="google", max_retries=2))
    engine._client = MobileTranslateClient()
    engine._client._client = httpx.Client(transport=httpx.MockTransport(handler))
    observer: TranslationObserver = _Observer()
    try:
        result = engine.translate_batch(["hi"], source_lang="en", target_lang="pl", observer=observer)
    finally:
        engine.close()

    assert [line.text for line in result] == ["PL-hi"]
    assert len(calls) == 2
    assert isinstance(observer, _Observer)
    assert observer.retries == [("google", 2, 3)]


def test_a_page_without_a_result_is_not_reported_as_a_translation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text="<html><body>Sorry...</body></html>")

    engine = GoogleService(TranslationConfig(engine="google", max_retries=0))
    engine._client = MobileTranslateClient()
    engine._client._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = engine.translate_batch(["hi"], source_lang="en", target_lang="pl")
    finally:
        engine.close()

    assert [line.ok for line in result] == [False]
    assert [line.text for line in result] == ["hi"]


def test_close_is_idempotent() -> None:
    engine = GoogleService(TranslationConfig(engine="google"))
    engine.close()
    engine.close()

    assert engine._client is None
