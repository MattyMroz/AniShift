"""Translation engine factory: registry-based engine construction.

Entry point: ``create_engine(config)`` -> concrete ``TranslationEngine``.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Final, Literal

from anishift.services.translation.errors import TranslationConfigError
from anishift.utils.logger import get_logger

__all__ = ["TranslationEngineId", "available_engine_ids", "create_engine"]

logger = get_logger(__name__)

if TYPE_CHECKING:
    from anishift.services.translation.config import TranslationConfig
    from anishift.services.translation.protocols import TranslationEngine

TranslationEngineId = Literal["google", "deepl", "llm"]
"""Registry keys of translation engines; higher layers import this, never respell it."""

# engine_id -> (module_path, service_class, config_class)
_REGISTRY: Final[dict[TranslationEngineId, tuple[str, str, str]]] = {
    "google": ("anishift.services.translation.engines.google", "GoogleService", "GoogleConfig"),
    "deepl": ("anishift.services.translation.engines.deepl", "DeeplService", "DeeplConfig"),
    "llm": ("anishift.services.translation.engines.llm", "LlmTranslateService", "LlmTranslateConfig"),
}


def available_engine_ids() -> tuple[TranslationEngineId, ...]:
    """Return the registered translation engine ids (single source of truth)."""
    return tuple(_REGISTRY)


def create_engine(config: TranslationConfig) -> TranslationEngine:
    """Create a translation engine for the given config.

    Engines import lazily so heavy SDKs stay off the domain import path.

    Args:
        config: Facade config; ``config.engine`` selects the registry entry.

    Returns:
        A ``TranslationEngine`` implementation ready to translate.

    Raises:
        TranslationConfigError: If ``config.engine`` is empty, unknown, or is
            ``llm`` (needs an injected completer; build LlmTranslateService
            directly and pass it via ``TranslationService(engine=...)``).
    """
    engine_id = config.engine
    if not engine_id:
        msg = "translation.engine is required"
        raise TranslationConfigError(msg)
    if engine_id not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        msg = f"Unknown translation engine: {engine_id!r}. Available: {available}"
        raise TranslationConfigError(msg)
    if engine_id == "llm":
        msg = (
            "The 'llm' engine needs an injected completer; build LlmTranslateService "
            "directly and pass it via TranslationService(engine=...)."
        )
        raise TranslationConfigError(msg)
    module_path, class_name, _config_class = _REGISTRY[engine_id]
    module = importlib.import_module(module_path)
    engine_cls = getattr(module, class_name)
    engine: TranslationEngine = engine_cls(config)
    logger.debug("translation engine created: {engine_id} ({cls})", engine_id=engine_id, cls=class_name)
    return engine
