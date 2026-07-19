"""Free Google Translate engine (googletrans 4.x, async under a sync facade).

googletrans is async, so the batching ladder stays async and the sync
``translate_batch`` wraps a whole file in one ``asyncio.run`` (one event loop per
file, never per batch).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

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
                max_chars_per_request=config.max_chars_per_request,
                max_retries=config.max_retries,
                concurrency=config.concurrency,
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

        async def _translate_joined(joined: str) -> tuple[str, str | None]:
            return await self._call_with_retry(client, joined, dest=dest)

        return await translate_lines(
            texts,
            batch_size=self._config.batch_size,
            max_chars=self._config.max_chars_per_request,
            translate_joined=_translate_joined,
        )

    async def _call_with_retry(self, client: Any, text: str, *, dest: str) -> tuple[str, str | None]:
        """Call googletrans with capped linear backoff; return (text, src lang)."""
        attempts = self._config.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                result = await client.translate(text, dest=dest)
            except Exception:
                if attempt >= attempts:
                    raise
                await asyncio.sleep(min(RETRY_BACKOFF_BASE_S * attempt, RETRY_MAX_WAIT_S))
                continue
            detected = getattr(result, "src", None)
            return str(result.text), (detected.lower() if detected else None)
        msg = "google retry exhausted without returning"  # unreachable
        raise RuntimeError(msg)


__all__ = ["GoogleService"]
