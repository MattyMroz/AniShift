"""Translation service configuration.

Forward-compatible dataclass: unknown keys are warned and ignored rather than
raising. The DeepL key is injected from :class:`anishift.config.settings.Settings`
at the composition root into ``api_key`` (google needs none).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from anishift.services.translation.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_CHARS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_SOURCE_LANG,
)
from anishift.services.translation.errors import TranslationConfigError
from anishift.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True, init=False)
class TranslationConfig:
    """Translation facade configuration.

    The caller decides which engine to use - this config carries no default for
    ``engine``, so the service never picks one on its own.

    The translation target is always Polish, so this config carries no target
    language (see ``constants.TARGET_LANG``).

    Attributes:
        engine: Engine id from the lazy registry (``google``/``deepl``/``llm``).
        source_lang: Source language; ``auto`` lets the provider detect it.
        batch_size: Lines joined per provider request.
        max_chars_per_request: Character budget per request before chunking.
        max_retries: Retry attempts on transient errors.
        concurrency: Concurrent batches per file (semaphore).
        api_key: Provider key (used by deepl; empty for the free google engine).
    """

    engine: str
    source_lang: str = DEFAULT_SOURCE_LANG
    batch_size: int = DEFAULT_BATCH_SIZE
    max_chars_per_request: int = DEFAULT_MAX_CHARS
    max_retries: int = DEFAULT_MAX_RETRIES
    concurrency: int = DEFAULT_CONCURRENCY
    api_key: str = ""

    def __init__(self, **kwargs: Any) -> None:
        """Assign known fields from kwargs; warn on unknown keys.

        Raises:
            TranslationConfigError: ``engine`` is missing or empty.
        """
        known = {dc_field.name for dc_field in dataclasses.fields(self)}
        unknown = kwargs.keys() - known
        if unknown:
            logger.warning("Unknown TranslationConfig keys ignored: {keys}", keys=sorted(unknown))

        if not kwargs.get("engine"):
            msg = "translation.engine is required - the service does not pick an engine"
            raise TranslationConfigError(msg)

        for dc_field in dataclasses.fields(self):
            default = None if dc_field.default is dataclasses.MISSING else dc_field.default
            setattr(self, dc_field.name, kwargs.get(dc_field.name, default))


__all__ = ["TranslationConfig"]
