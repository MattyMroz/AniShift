"""Free Google Translate engine (googletrans 4.x, async under a sync facade).

googletrans is async, so the batching ladder stays async and the sync
``translate_batch`` wraps a whole file in one ``asyncio.run`` (one event loop per
file, never per batch).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from anishift.services.translation._retry import call_with_retry_async
from anishift.services.translation.engines.google._batching import translate_lines
from anishift.services.translation.engines.google.config import GoogleConfig
from anishift.services.translation.engines.google.constants import (
    RETRY_BACKOFF_BASE_S,
    RETRY_MAX_WAIT_S,
)

if TYPE_CHECKING:
    from anishift.services.translation.config import TranslationConfig
    from anishift.services.translation.types import BatchedLine


class GoogleService:
    """Translation engine backed by the free googletrans client."""

    __slots__ = ("_config",)

    def __init__(self, config: TranslationConfig | GoogleConfig) -> None:
        """Store config; the client is created per call inside the event loop."""
        if isinstance(config, GoogleConfig):
            self._config = config
        else:
            self._config = GoogleConfig(
                batch_size=config.batch_size,
                max_retries=config.max_retries,
            )

    @property
    def engine_id(self) -> str:
        """Stable engine identifier (registry key)."""
        return "google"

    @property
    def is_available(self) -> bool:
        """The free Google endpoint needs no key, so it is always available."""
        return True

    def close(self) -> None:
        """No persistent client to release."""

    def translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> list[BatchedLine]:
        """Translate one batch, preserving order and length (one event loop)."""
        del source_lang  # googletrans auto-detects the source language
        if not texts:
            return []
        dest = (target_lang or "pl").lower()
        return asyncio.run(self._translate_all(texts, dest=dest))

    async def _translate_all(self, texts: list[str], *, dest: str) -> list[BatchedLine]:
        """Build the client and run the batching ladder in this event loop."""
        from googletrans import Translator  # type: ignore[import-untyped]  # noqa: PLC0415 - lazy SDK import

        client: Any = Translator()

        async def _translate_joined(joined: str) -> str:
            return await self._call_with_retry(client, joined, dest=dest)

        return await translate_lines(
            texts,
            batch_size=self._config.batch_size,
            max_chars=self._config.max_chars_per_request,
            translate_joined=_translate_joined,
        )

    async def _call_with_retry(self, client: Any, text: str, *, dest: str) -> str:
        """Call googletrans, retrying transient HTTP errors with shared backoff.

        ``httpx.HTTPError`` is the only stable transient class googletrans
        raises (network/timeout/status); anything else (parse failures) raises
        immediately and the batching ladder falls back per-line.
        """
        import httpx  # noqa: PLC0415 - lazy import: ships with googletrans

        async def _once() -> Any:
            return await client.translate(text, dest=dest)

        result = await call_with_retry_async(
            _once,
            max_attempts=self._config.max_retries + 1,
            retry_on=httpx.HTTPError,
            base_s=RETRY_BACKOFF_BASE_S,
            cap_s=RETRY_MAX_WAIT_S,
        )
        return str(result.text)


__all__ = ["GoogleService"]
