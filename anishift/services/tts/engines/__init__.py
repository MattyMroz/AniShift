"""Lazy registry for TTS engines."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Final, Literal, cast

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsConfigError

if TYPE_CHECKING:
    from anishift.services.tts.config import TtsConfig
    from anishift.services.tts.protocols import TtsEngine

__all__ = ["TtsEngineId", "available_engine_ids", "create_engine"]

TtsEngineId = Literal["edge", "elevenbytes", "elevenlabs", "sapi"]
"""Stable registry identifiers for supported TTS engines."""

type _EngineFactory = Callable[[TtsConfig], TtsEngine]
"""Callable constructing one configured TTS engine."""

type _RegistryEntry = tuple[str, str]
"""Engine module and service class."""

_REGISTRY: Final[dict[TtsEngineId, _RegistryEntry]] = {
    "edge": ("anishift.services.tts.engines.edge", "EdgeTtsEngine"),
    "elevenbytes": (
        "anishift.services.tts.engines.elevenbytes",
        "ElevenBytesTtsEngine",
    ),
    "elevenlabs": (
        "anishift.services.tts.engines.elevenlabs",
        "ElevenLabsTtsEngine",
    ),
    "sapi": ("anishift.services.tts.engines.sapi", "SapiTtsEngine"),
}
"""Engine module and class by stable engine id."""


def available_engine_ids() -> tuple[TtsEngineId, ...]:
    """Return all registered TTS engine ids in stable order."""
    return tuple(_REGISTRY)


def create_engine(config: TtsConfig) -> TtsEngine:
    """Create only the TTS engine selected by the caller.

    Args:
        config: Validated synthesis configuration.

    Returns:
        The selected TTS engine.

    Raises:
        TtsConfigError: The engine id is not registered.
    """
    module_path, class_name = _get_registry_entry(config.engine_id)
    module = importlib.import_module(module_path)
    factory = cast("_EngineFactory", getattr(module, class_name))
    engine: TtsEngine = factory(config)
    return engine


def _get_registry_entry(engine_id: str) -> _RegistryEntry:
    if engine_id in _REGISTRY:
        return _REGISTRY[engine_id]
    available: str = ", ".join(_REGISTRY)
    message: str = f"Unknown TTS engine: {engine_id!r}. Available: {available}"
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Select one of the registered TTS engines in settings.",
        details={"engine_id": engine_id},
    )
    raise TtsConfigError(context=context)
