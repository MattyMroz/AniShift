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
from anishift.services.translation.dedup import prepare_lines, redistribute, redistribute_flags
from anishift.services.translation.errors import TranslationEngineError, TranslationError
from anishift.services.translation.types import BatchedLine, FileTranslation, TranslatedLine

if TYPE_CHECKING:
    from anishift.services.subtitles.types import SpokenLine
    from anishift.services.translation.protocols import TranslationEngine, TranslationEngineFactory


def _default_engine_factory(
    engine_id: str,
    config: TranslationConfig,
) -> TranslationEngine:
    """Build one registry engine from the facade's base configuration."""
    from anishift.services.translation.engines import create_engine  # noqa: PLC0415 - lazy engine import

    engine_config = TranslationConfig(
        engine=engine_id,
        source_lang=config.source_lang,
        batch_size=config.batch_size,
        max_retries=config.max_retries,
        api_key=config.api_key,
    )
    return create_engine(engine_config)


class TranslationService:
    """Sync translation facade over one engine with a fallback chain."""

    __slots__ = ("_engine_factory", "config", "fallback_chain")

    def __init__(
        self,
        config: TranslationConfig,
        *,
        engine_factory: TranslationEngineFactory | None = None,
        fallback_chain: tuple[str, ...] = (),
    ) -> None:
        """Create the facade with an optional composition-owned engine factory."""
        self.config = config
        self._engine_factory = engine_factory or _default_engine_factory
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
        last_context: ErrorContext | None = None
        for engine_id in chain:
            if cancel is not None and cancel.is_set():
                context = ErrorContext(code=ErrorCode.CANCELLED, message="translation cancelled")
                raise TranslationError(context=context)
            engine: TranslationEngine | None = None
            try:
                engine = self._engine_factory(engine_id, self.config)
                if not engine.is_available:
                    context = ErrorContext(
                        code=ErrorCode.TRANSLATION_ENGINE_ERROR,
                        message=f"engine {engine_id} unavailable",
                        suggestion="Choose an available translation engine.",
                    )
                    raise TranslationEngineError(context=context)
                return self._run(engine, spoken, displayed, source_lang=source_lang, target_lang=target_lang)
            except TranslationError as exc:
                if exc.context.code is ErrorCode.CANCELLED:
                    raise
                last_error = str(exc)
                last_context = exc.context
            finally:
                if engine is not None:
                    engine.close()
        error = last_error or "no available translation engine"
        context = last_context or ErrorContext(
            code=ErrorCode.TRANSLATION_ENGINE_ERROR,
            message=error,
            suggestion="Check translation settings and try again.",
        )
        return FileTranslation(target_lang=target_lang, error=error, error_context=context)

    def _resolve_chain(self) -> tuple[str, ...]:
        """Return the ordered engine chain without duplicate entries."""
        return tuple(dict.fromkeys((self.config.engine, *self.fallback_chain)))

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
        prepared = prepare_lines(spoken_texts, engine.input_policy("spoken"))
        batched = self._call_engine(
            engine,
            list(prepared.texts),
            source_lang=source_lang,
            target_lang=target_lang,
        )
        calls = 1 if prepared.texts else 0
        full_text = redistribute([line.text for line in batched], prepared, spoken_texts)
        full_ok = redistribute_flags([line.ok for line in batched], prepared)
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
        return lines, calls, len(prepared.texts), failed

    def _translate_displayed(
        self,
        engine: TranslationEngine,
        displayed: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> tuple[tuple[str, ...], int, int]:
        """Translate the displayed stream into single-line strings, in event order.

        The result is one translated single-line string per input event. Re-splitting
        into on-screen verses and joining with the format-specific break happens at
        the write step, where the subtitle format (ASS vs SRT) is known.
        """
        prepared = prepare_lines(displayed, engine.input_policy("displayed"))
        batched = self._call_engine(
            engine,
            list(prepared.texts),
            source_lang=source_lang,
            target_lang=target_lang,
        )
        calls = 1 if prepared.texts else 0
        out = tuple(redistribute([line.text for line in batched], prepared, displayed))
        return out, calls, len(prepared.texts)

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
