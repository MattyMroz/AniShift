"""TranslationService - sync facade over one engine with a fallback chain.

Deduplicates lines, delegates a whole file's unique set to the engine, and on a
hard engine failure retranslates the whole file with the next available engine in
the chain. Accepts an injected engine for tests / the LLM engine.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.constants import TARGET_LANG
from anishift.services.translation.dedup import deduplicate, redistribute, redistribute_flags
from anishift.services.translation.errors import (
    TranslationAuthError,
    TranslationEngineError,
    TranslationError,
    TranslationQuotaError,
    TranslationRateLimitError,
)
from anishift.services.translation.types import BatchedLine, FileTranslation, TranslatedLine

if TYPE_CHECKING:
    from anishift.services.subtitles.types import SpokenLine
    from anishift.services.translation.protocols import TranslationEngine


class TranslationService:
    """Sync translation facade over one engine with a fallback chain."""

    __slots__ = ("_injected", "config", "fallback_chain")

    def __init__(
        self,
        config: TranslationConfig,
        *,
        engine: TranslationEngine | None = None,
        fallback_chain: tuple[str, ...] = (),
    ) -> None:
        """Create the facade; optionally inject an engine (tests / LLM DI)."""
        self.config = config
        self._injected = engine
        self.fallback_chain = fallback_chain

    def translate_file(
        self,
        spoken: list[SpokenLine],
        displayed: list[str],
        *,
        source_lang: str = "auto",
        target_lang: str = TARGET_LANG,
        cancel: threading.Event | None = None,
    ) -> FileTranslation:
        """Translate one file's spoken + displayed streams with dedup + fallback.

        Args:
            spoken: Narrator lines carrying source timings and styles.
            displayed: Visible-texts of displayed events, in event order.
            source_lang: Source language code (``auto`` to auto-detect).
            target_lang: Target language code.
            cancel: Cooperative cancellation event checked before each engine.

        Returns:
            A :class:`FileTranslation`; ``error`` is set only when the whole
            fallback chain failed.
        """
        if not spoken and not displayed:
            return FileTranslation(target_lang=target_lang)

        chain = self._resolve_chain()
        last_error: str | None = None
        for engine_id in chain:
            if cancel is not None and cancel.is_set():
                context = ErrorContext(code=ErrorCode.CANCELLED, message="translation cancelled")
                raise TranslationError(context=context)
            engine = self._build_engine(engine_id)
            if not engine.is_available:
                last_error = f"engine {engine_id} unavailable"
                continue
            try:
                return self._run(engine, spoken, displayed, source_lang=source_lang, target_lang=target_lang)
            except TranslationQuotaError as exc:
                last_error = str(exc)
            except TranslationRateLimitError as exc:
                last_error = str(exc)
            except TranslationAuthError as exc:
                last_error = str(exc)
            except TranslationEngineError as exc:
                last_error = str(exc)
            finally:
                engine.close()
        return FileTranslation(target_lang=target_lang, error=last_error or "no available translation engine")

    def _resolve_chain(self) -> tuple[str, ...]:
        """Return the ordered engine chain (injected engine wins, no fallback)."""
        if self._injected is not None:
            return (self._injected.engine_id,)
        return tuple(dict.fromkeys((self.config.engine, *self.fallback_chain)))

    def _build_engine(self, engine_id: str) -> TranslationEngine:
        """Return the injected engine or build one from the registry."""
        if self._injected is not None:
            return self._injected
        from anishift.services.translation.engines import create_engine  # noqa: PLC0415 - lazy engine import

        engine_config = TranslationConfig(
            engine=engine_id,
            source_lang=self.config.source_lang,
            batch_size=self.config.batch_size,
            max_chars_per_request=self.config.max_chars_per_request,
            max_retries=self.config.max_retries,
            concurrency=self.config.concurrency,
            api_key=self.config.api_key,
        )
        return create_engine(engine_config)

    def _run(
        self,
        engine: TranslationEngine,
        spoken: list[SpokenLine],
        displayed: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> FileTranslation:
        """Translate both streams with one engine and assemble the result."""
        spoken_lines, spoken_calls, spoken_unique, spoken_failed = self._translate_spoken(
            engine, spoken, source_lang=source_lang, target_lang=target_lang
        )
        displayed_out, displayed_calls, displayed_unique = self._translate_displayed(
            engine, displayed, source_lang=source_lang, target_lang=target_lang
        )
        return FileTranslation(
            spoken=spoken_lines,
            displayed=displayed_out,
            engine_id=engine.engine_id,
            target_lang=target_lang,
            unique_lines=spoken_unique + displayed_unique,
            total_lines=len(spoken) + len(displayed),
            api_calls=spoken_calls + displayed_calls,
            failed_lines=spoken_failed,
        )

    def _translate_spoken(
        self,
        engine: TranslationEngine,
        spoken: list[SpokenLine],
        *,
        source_lang: str,
        target_lang: str,
    ) -> tuple[tuple[TranslatedLine, ...], int, int, int]:
        """Translate the spoken stream into TranslatedLine objects."""
        spoken_texts = [line.text for line in spoken]
        dedup = deduplicate(spoken_texts)
        batched = self._call_engine(engine, list(dedup.unique), source_lang=source_lang, target_lang=target_lang)
        calls = 1 if dedup.unique else 0
        full_text = redistribute([line.text for line in batched], dedup, spoken_texts)
        full_ok = redistribute_flags([line.ok for line in batched], dedup)
        lines = tuple(
            TranslatedLine(
                start=source.start,
                end=source.end,
                source_text=source.text,
                text=text,
                lines=(text,),
                style=source.style,
                ok=ok,
            )
            for source, text, ok in zip(spoken, full_text, full_ok, strict=True)
        )
        failed = sum(1 for ok in full_ok if not ok)
        return lines, calls, len(dedup.unique), failed

    def _translate_displayed(
        self,
        engine: TranslationEngine,
        displayed: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> tuple[tuple[str, ...], int, int]:
        """Translate the displayed stream into plain strings."""
        dedup = deduplicate(displayed)
        batched = self._call_engine(engine, list(dedup.unique), source_lang=source_lang, target_lang=target_lang)
        calls = 1 if dedup.unique else 0
        out = tuple(redistribute([line.text for line in batched], dedup, displayed))
        return out, calls, len(dedup.unique)

    @staticmethod
    def _call_engine(
        engine: TranslationEngine,
        unique: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> list[BatchedLine]:
        """Translate a unique set, or return an empty list when there is none."""
        if not unique:
            return []
        return engine.translate_batch(unique, source_lang=source_lang, target_lang=target_lang)


__all__ = ["TranslationService"]
