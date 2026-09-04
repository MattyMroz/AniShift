"""DeepL engine (official SDK, synchronous)."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from anishift.services.translation._retry import call_with_retry
from anishift.services.translation.engines.deepl._lang_codes import to_deepl_code, to_deepl_source_code
from anishift.services.translation.engines.deepl.config import DeeplConfig
from anishift.services.translation.engines.deepl.constants import (
    MAX_PAYLOAD_BYTES,
    RATE_LIMIT_BASE_DELAY_S,
)
from anishift.services.translation.errors import (
    TranslationAuthError,
    TranslationEngineError,
    TranslationQuotaError,
    TranslationRateLimitError,
)
from anishift.services.translation.types import BatchedLine

if TYPE_CHECKING:
    from anishift.services.translation.config import TranslationConfig
    from anishift.services.translation.protocols import TranslationInputPolicy, TranslationObserver, TranslationStream


def _map_sdk_error(exc: Exception) -> Exception:
    """Map a DeepL SDK exception onto the translation error hierarchy."""
    import deepl  # noqa: PLC0415 - lazy SDK import

    if isinstance(exc, deepl.TooManyRequestsException):
        return TranslationRateLimitError(str(exc) or "DeepL rate limit (429)")
    if isinstance(exc, deepl.QuotaExceededException):
        return TranslationQuotaError(str(exc) or "DeepL quota exceeded")
    if isinstance(exc, deepl.AuthorizationException):
        return TranslationAuthError(str(exc) or "DeepL authorization failed")
    if isinstance(exc, deepl.DeepLException):
        return TranslationEngineError(str(exc) or "DeepL request failed")
    return exc


def _chunk_batches(texts: list[str], max_lines: int, max_bytes: int) -> list[list[str]]:
    """Split lines into sub-batches bounded by line count and UTF-8 byte size."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_bytes = 0
    for text in texts:
        size = len(text.encode("utf-8")) + 1
        too_many = len(current) >= max_lines
        too_large = bool(current) and current_bytes + size > max_bytes
        if too_many or too_large:
            chunks.append(current)
            current = []
            current_bytes = 0
        current.append(text)
        current_bytes += size
    if current:
        chunks.append(current)
    return chunks


class DeeplService:
    """Translation engine backed by the official DeepL SDK."""

    __slots__ = ("_client", "_config")

    def __init__(self, config: TranslationConfig | DeeplConfig) -> None:
        """Store config; defer client creation to the first translate call."""
        if isinstance(config, DeeplConfig):
            self._config = config
        else:
            self._config = DeeplConfig(
                api_key=config.api_key,
                batch_size=config.batch_size,
                max_retries=config.max_retries,
            )
        self._client: Any = None

    @property
    def engine_id(self) -> str:
        """Stable engine identifier (registry key)."""
        return "deepl"

    @property
    def is_available(self) -> bool:
        """Whether an API key is configured."""
        return bool(self._config.api_key)

    def close(self) -> None:
        """Drop the client reference."""
        self._client = None

    def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy:
        """Deduplicate both subtitle streams before translation."""
        del stream
        return "deduplicate"

    def _ensure_client(self) -> None:
        """Create the DeepL client from the configured key (idempotent)."""
        if self._client is not None:
            return
        if not self._config.api_key:
            msg = "DeepL API key is not set"
            raise TranslationAuthError(msg)
        import deepl  # noqa: PLC0415 - lazy SDK import

        self._client = deepl.Translator(self._config.api_key)

    def translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
        observer: TranslationObserver | None = None,
    ) -> list[BatchedLine]:
        """Translate one batch via the SDK; retry transient rate-limits."""
        if not texts:
            return []
        self._ensure_client()
        target = to_deepl_code(target_lang) or "EN-US"
        source = to_deepl_source_code(source_lang)
        max_attempts = self._config.max_retries + 1
        out: list[BatchedLine] = []
        for chunk in _chunk_batches(texts, self._config.batch_size, MAX_PAYLOAD_BYTES):
            out.extend(
                call_with_retry(
                    partial(self._translate_once, chunk, target, source),
                    max_attempts=max_attempts,
                    retry_on=TranslationRateLimitError,
                    base_s=RATE_LIMIT_BASE_DELAY_S,
                    on_retry=(
                        None
                        if observer is None
                        else lambda attempt, maximum: observer.retry(self.engine_id, attempt, maximum)
                    ),
                )
            )
        return out

    def _translate_once(self, texts: list[str], target: str, source: str | None) -> list[BatchedLine]:
        """Single SDK call; SDK errors surface mapped onto the hierarchy."""
        try:
            results = self._client.translate_text(texts, target_lang=target, source_lang=source)
        except Exception as exc:
            raise _map_sdk_error(exc) from exc
        return [BatchedLine(text=result.text) for result in results]


__all__ = ["DeeplService"]
