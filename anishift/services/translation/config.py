"""Translation service configuration."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from anishift.services.translation.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_SOURCE_LANG,
)
from anishift.services.translation.errors import TranslationConfigError
from anishift.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True, init=False)
class TranslationConfig:
    """Translation facade configuration."""

    engine: str
    source_lang: str = DEFAULT_SOURCE_LANG
    batch_size: int = DEFAULT_BATCH_SIZE
    max_retries: int = DEFAULT_MAX_RETRIES
    api_key: str = ""

    def __init__(self, **kwargs: Any) -> None:
        """Assign known fields from kwargs; warn on unknown keys."""
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
