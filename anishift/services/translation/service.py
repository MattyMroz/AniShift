"""TranslationService - sync facade over one engine with a fallback chain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.constants import TARGET_LANG
from anishift.services.translation.errors import TranslationEngineError, TranslationError
from anishift.services.translation.types import BatchedLine, FileTranslation, TranslatedLine
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from anishift.services.subtitles.types import DisplayedLine, SpokenLine
from anishift.services.translation.protocols import (
    TranslationCancellation,
    TranslationEngine,
    TranslationEngineFactory,
    TranslationObserver,
    TranslationStream,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _TranslationUnit:
    """One source item placed in whole-file chronological order."""

    stream: TranslationStream
    source_index: int
    order: int
    text: str


@dataclass(frozen=True, slots=True)
class _PreparedFile:
    """Provider texts and maps back onto the two output streams."""

    texts: tuple[str, ...]
    spoken_map: tuple[int, ...]
    displayed_map: tuple[int, ...]


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

    def translate_file(  # noqa: PLR0913 - public facade keeps explicit language and observation controls
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = TARGET_LANG,
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        """Translate one file's spoken + displayed streams with dedup + fallback."""
        if not spoken and not displayed:
            return FileTranslation(target_lang=target_lang)

        chain = self._resolve_chain()
        logger.debug(
            "File translation started",
            spoken_lines=len(spoken),
            displayed_lines=len(displayed),
            engine_chain=chain,
        )
        last_error: str | None = None
        last_context: ErrorContext | None = None
        for index, engine_id in enumerate(chain):
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
                result = self._run(
                    engine,
                    spoken,
                    displayed,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    observer=observer,
                )
                logger.info(
                    "File translation completed",
                    engine=engine_id,
                    total_lines=result.total_lines,
                    unique_lines=result.unique_lines,
                    failed_lines=result.failed_lines,
                    api_calls=result.api_calls,
                )
                return result  # noqa: TRY300 - return must precede engine close in finally
            except TranslationError as exc:
                if exc.context.code is ErrorCode.CANCELLED:
                    raise
                last_error = str(exc)
                last_context = exc.context
                logger.warning(
                    "Translation engine attempt failed",
                    engine=engine_id,
                    error_code=exc.context.code.value,
                    fallback_remaining=engine_id != chain[-1],
                )
                if observer is not None and index + 1 < len(chain):
                    observer.fallback(engine_id, chain[index + 1])
            finally:
                if engine is not None:
                    engine.close()
        error = last_error or "no available translation engine"
        context = last_context or ErrorContext(
            code=ErrorCode.TRANSLATION_ENGINE_ERROR,
            message=error,
            suggestion="Check translation settings and try again.",
        )
        logger.error(
            "Translation engine chain exhausted",
            error_code=context.code.value,
            attempted_engines=chain,
        )
        return FileTranslation(target_lang=target_lang, error=error, error_context=context)

    def _resolve_chain(self) -> tuple[str, ...]:
        """Return the ordered engine chain without duplicate entries."""
        return tuple(dict.fromkeys((self.config.engine, *self.fallback_chain)))

    def _run(  # noqa: PLR0913 - one engine invocation receives the full bounded context
        self,
        engine: TranslationEngine,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str,
        target_lang: str,
        observer: TranslationObserver | None,
    ) -> FileTranslation:
        """Translate one chronological whole-file stream and assemble outputs."""
        prepared = _prepare_file(engine, spoken, displayed)
        batched = (
            engine.translate_batch(
                list(prepared.texts),
                source_lang=source_lang,
                target_lang=target_lang,
                observer=observer,
            )
            if prepared.texts
            else []
        )
        spoken_lines, spoken_failed = _translated_spoken(spoken, prepared.spoken_map, batched)
        displayed_out, displayed_failed = _translated_displayed(displayed, prepared.displayed_map, batched)
        return FileTranslation(
            spoken=spoken_lines,
            displayed=displayed_out,
            engine_id=engine.engine_id,
            target_lang=target_lang,
            unique_lines=len(prepared.texts),
            total_lines=len(spoken) + len(displayed),
            api_calls=1 if prepared.texts else 0,
            failed_lines=spoken_failed + displayed_failed,
        )


def _prepare_file(
    engine: TranslationEngine,
    spoken: list[SpokenLine],
    displayed: list[DisplayedLine],
) -> _PreparedFile:
    """Prepare one chronological input while applying per-stream deduplication."""
    units = [
        *(_TranslationUnit("spoken", index, line.order, line.text) for index, line in enumerate(spoken)),
        *(_TranslationUnit("displayed", index, line.order, line.text) for index, line in enumerate(displayed)),
    ]
    units.sort(key=lambda unit: (unit.order, unit.source_index))
    maps: dict[TranslationStream, list[int]] = {
        "spoken": [-1] * len(spoken),
        "displayed": [-1] * len(displayed),
    }
    policies = {
        "spoken": engine.input_policy("spoken"),
        "displayed": engine.input_policy("displayed"),
    }
    texts: list[str] = []
    seen: dict[tuple[TranslationStream, str], int] = {}
    for unit in units:
        if not unit.text.strip():
            continue
        key = (unit.stream, unit.text)
        if policies[unit.stream] == "deduplicate" and key in seen:
            maps[unit.stream][unit.source_index] = seen[key]
            continue
        position = len(texts)
        texts.append(unit.text)
        maps[unit.stream][unit.source_index] = position
        if policies[unit.stream] == "deduplicate":
            seen[key] = position
    return _PreparedFile(tuple(texts), tuple(maps["spoken"]), tuple(maps["displayed"]))


def _translated_spoken(
    sources: list[SpokenLine],
    positions: tuple[int, ...],
    translations: list[BatchedLine],
) -> tuple[tuple[TranslatedLine, ...], int]:
    """Map provider results back onto narrator lines and count failures."""
    lines: list[TranslatedLine] = []
    failed = 0
    for source, position in zip(sources, positions, strict=True):
        translated = BatchedLine(source.text) if position < 0 else translations[position]
        failed += not translated.ok
        lines.append(
            TranslatedLine(
                start=source.start,
                end=source.end,
                source_text=source.text,
                text=translated.text,
                lines=(translated.text,),
                style=source.style,
                ok=translated.ok,
            )
        )
    return tuple(lines), failed


def _translated_displayed(
    sources: list[DisplayedLine],
    positions: tuple[int, ...],
    translations: list[BatchedLine],
) -> tuple[tuple[str, ...], int]:
    """Map provider results back onto displayed events and count failures."""
    lines: list[str] = []
    failed = 0
    for source, position in zip(sources, positions, strict=True):
        translated = BatchedLine(source.text) if position < 0 else translations[position]
        failed += not translated.ok
        lines.append(translated.text)
    return tuple(lines), failed


__all__ = ["TranslationService"]
