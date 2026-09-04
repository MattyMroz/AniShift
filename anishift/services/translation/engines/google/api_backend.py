"""HTTP client for the free Google Translate mobile page."""

from __future__ import annotations

import html
import re
from typing import Final

import httpx

from anishift.services.translation.engines.google.constants import (
    BASE_URL,
    REQUEST_TIMEOUT_S,
    USER_AGENT,
)
from anishift.services.translation.errors import (
    TranslationEngineError,
    TranslationRateLimitError,
)

_RESULT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r'<div[^>]*class="result-container"[^>]*>(.*?)</div>',
    re.DOTALL,
)
"""Captures the translated text the mobile page puts in its result container."""

_RATE_LIMIT_STATUSES: Final[frozenset[int]] = frozenset({429, 503})
"""Statuses meaning "come back later" rather than "this request is wrong"."""

TRANSIENT_ERRORS: Final[tuple[type[Exception], ...]] = (TranslationRateLimitError, httpx.HTTPError)
"""Errors from this backend that another attempt can still resolve."""


class MobileTranslateClient:
    """Translate one already-joined string through the mobile page."""

    __slots__ = ("_client",)

    def __init__(self, timeout_s: float = REQUEST_TIMEOUT_S) -> None:
        """Create the reusable HTTP client with the browser User-Agent."""
        self._client: httpx.Client = httpx.Client(
            timeout=timeout_s,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        """Translate one string and return the page's translated text."""
        response: httpx.Response = self._client.get(
            BASE_URL,
            params={"sl": source_lang, "tl": target_lang, "q": text},
        )
        if response.status_code in _RATE_LIMIT_STATUSES:
            msg = f"Google Translate refused the request ({response.status_code})"
            raise TranslationRateLimitError(msg)
        if response.is_error:
            msg = f"Google Translate request failed ({response.status_code})"
            raise TranslationEngineError(msg)
        return _extract_translation(response.text)

    def close(self) -> None:
        """Release the HTTP client; safe to call more than once."""
        self._client.close()


def _extract_translation(page: str) -> str:
    """Return the translated text held by the page's result container."""
    match: re.Match[str] | None = _RESULT_PATTERN.search(page)
    if match is None:
        msg = "Google Translate returned a page without a result container"
        raise TranslationEngineError(msg)
    return html.unescape(match.group(1)).strip()


__all__ = ["TRANSIENT_ERRORS", "MobileTranslateClient"]
