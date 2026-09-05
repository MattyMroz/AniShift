"""Free Google Translate engine (mobile page, synchronous)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anishift.services.translation._retry import call_with_retry
from anishift.services.translation.engines.google._batching import translate_lines
from anishift.services.translation.engines.google.api_backend import (
    TRANSIENT_ERRORS,
    MobileTranslateClient,
)
from anishift.services.translation.engines.google.config import GoogleConfig
from anishift.services.translation.engines.google.constants import (
    RETRY_BACKOFF_BASE_S,
    RETRY_MAX_WAIT_S,
)

if TYPE_CHECKING:
    from anishift.services.translation.config import TranslationConfig
    from anishift.services.translation.protocols import TranslationInputPolicy, TranslationObserver, TranslationStream
    from anishift.services.translation.types import BatchedLine


class GoogleService:
    """Translation engine backed by the free Google Translate mobile page."""

    __slots__ = ("_client", "_config")

    def __init__(self, config: TranslationConfig | GoogleConfig) -> None:
        """Store config; the HTTP client is created on first use."""
        if isinstance(config, GoogleConfig):
            self._config = config
        else:
            self._config = GoogleConfig(
                batch_size=config.batch_size,
                max_retries=config.max_retries,
            )
        self._client: MobileTranslateClient | None = None

    @property
    def engine_id(self) -> str:
        """Stable engine identifier (registry key)."""
        return "google"

    @property
    def is_available(self) -> bool:
        """The free endpoint needs no key, so it is always available."""
        return True

    def close(self) -> None:
        """Release the HTTP client; idempotent."""
        if self._client is None:
            return
        self._client.close()
        self._client = None

    def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy:
        """Deduplicate both subtitle streams before translation."""
        del stream
        return "deduplicate"

    def translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
        observer: TranslationObserver | None = None,
    ) -> list[BatchedLine]:
        """Translate one batch, preserving order and length."""
        if not texts:
            return []
        source = (source_lang or "auto").lower()
        target = (target_lang or "pl").lower()

        def translate_joined(joined: str) -> str:
            return self._translate_with_retry(joined, source=source, target=target, observer=observer)

        return translate_lines(
            texts,
            batch_size=self._config.batch_size,
            max_chars=self._config.max_chars_per_request,
            translate_joined=translate_joined,
        )

    def _ensure_client(self) -> MobileTranslateClient:
        """Return the HTTP client, creating it on first use (idempotent)."""
        if self._client is None:
            self._client = MobileTranslateClient()
        return self._client

    def _translate_with_retry(
        self,
        text: str,
        *,
        source: str,
        target: str,
        observer: TranslationObserver | None,
    ) -> str:
        """Translate one string, retrying the failures a retry can fix."""
        client: MobileTranslateClient = self._ensure_client()

        def once() -> str:
            return client.translate(text, source_lang=source, target_lang=target)

        return call_with_retry(
            once,
            max_attempts=self._config.max_retries + 1,
            retry_on=TRANSIENT_ERRORS,
            base_s=RETRY_BACKOFF_BASE_S,
            cap_s=RETRY_MAX_WAIT_S,
            on_retry=(
                None if observer is None else lambda attempt, maximum: observer.retry(self.engine_id, attempt, maximum)
            ),
        )


__all__ = ["GoogleService"]
