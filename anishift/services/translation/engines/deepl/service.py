"""DeepL engine (official SDK, synchronous).

``translate_text`` accepts a list and returns results in order, so this engine
uses the SDK's native batch. The key comes from the config (injected from
Settings). Rate-limit errors retry with backoff; other SDK errors map onto the
translation error hierarchy so the facade can react (quota -> fallback).
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from anishift.services.translation._retry import call_with_retry
from anishift.services.translation.engines.deepl._lang_codes import to_deepl_code
from anishift.services.translation.engines.deepl.config import DeeplConfig
from anishift.services.translation.engines.deepl.constants import (
    MAX_PAYLOAD_BYTES,
    RATE_LIMIT_BASE_DELAY_S,
    RATE_LIMIT_MAX_ATTEMPTS,
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


def _map_sdk_error(exc: Exception) -> Exception:
    """Map a DeepL SDK exception onto the translation error hierarchy.

    ``deepl`` is imported lazily so the module stays importable without the SDK.
    """
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


def _normalize_lang(code: str | None) -> str | None:
    """Lowercase the provider's detected code (DeepL returns ``JA``/``EN``)."""
    return code.lower() if code else None


def _chunk_by_bytes(texts: list[str], max_bytes: int) -> list[list[str]]:
    """Split lines into sub-batches whose UTF-8 size stays under ``max_bytes``."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_bytes = 0
    for text in texts:
        size = len(text.encode("utf-8")) + 1
        if current and current_bytes + size > max_bytes:
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
            self._config = DeeplConfig(api_key=config.api_key, max_retries=config.max_retries)
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

    def _ensure_client(self) -> None:
        """Create the DeepL client from the configured key (idempotent).

        Raises:
            TranslationAuthError: When no API key is configured.
        """
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
    ) -> list[BatchedLine]:
        """Translate one batch via the SDK; retry transient rate-limits."""
        if not texts:
            return []
        self._ensure_client()
        target = to_deepl_code(target_lang) or "EN-US"
        source = to_deepl_code(source_lang)
        out: list[BatchedLine] = []
        for chunk in _chunk_by_bytes(texts, MAX_PAYLOAD_BYTES):
            out.extend(
                call_with_retry(
                    partial(self._translate_once, chunk, target, source),
                    max_attempts=RATE_LIMIT_MAX_ATTEMPTS,
                    retry_on=TranslationRateLimitError,
                    base_s=RATE_LIMIT_BASE_DELAY_S,
                )
            )
        return out

    def _translate_once(self, texts: list[str], target: str, source: str | None) -> list[BatchedLine]:
        """Single SDK call; SDK errors surface mapped onto the hierarchy."""
        try:
            results = self._client.translate_text(texts, target_lang=target, source_lang=source)
        except Exception as exc:
            raise _map_sdk_error(exc) from exc
        return [
            BatchedLine(text=result.text, detected_lang=_normalize_lang(getattr(result, "detected_source_lang", None)))
            for result in results
        ]


__all__ = ["DeeplService"]
