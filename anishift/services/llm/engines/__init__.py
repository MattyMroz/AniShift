"""Lazy registry for LLM provider engines."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Final, Literal, cast

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.errors import LlmConfigError

if TYPE_CHECKING:
    from anishift.services.llm.config import LlmConfig
    from anishift.services.llm.protocols import LlmEngine

__all__ = [
    "LlmEngineId",
    "available_engine_ids",
    "create_engine",
    "suggested_model_ids",
]

LlmEngineId = Literal[
    "anthropic",
    "deepseek",
    "gemini",
    "openai",
    "openai_compatible",
    "openrouter",
    "palantir",
]
"""Stable registry identifiers for supported LLM providers."""

type _EngineFactory = Callable[[LlmConfig], LlmEngine]
"""Callable constructing one configured provider engine."""

type _RegistryEntry = tuple[str, str, str | None]
"""Provider module, service class, and optional suggestions module."""

_REGISTRY: Final[dict[LlmEngineId, _RegistryEntry]] = {
    "anthropic": (
        "anishift.services.llm.engines.anthropic",
        "AnthropicService",
        "anishift.services.llm.engines.anthropic.constants",
    ),
    "deepseek": (
        "anishift.services.llm.engines.deepseek",
        "DeepseekService",
        "anishift.services.llm.engines.deepseek.constants",
    ),
    "gemini": (
        "anishift.services.llm.engines.gemini",
        "GeminiService",
        "anishift.services.llm.engines.gemini.constants",
    ),
    "openai": (
        "anishift.services.llm.engines.openai",
        "OpenaiService",
        "anishift.services.llm.engines.openai.constants",
    ),
    "openai_compatible": (
        "anishift.services.llm.engines.openai_compatible",
        "OpenaiCompatibleService",
        None,
    ),
    "openrouter": (
        "anishift.services.llm.engines.openrouter",
        "OpenrouterService",
        "anishift.services.llm.engines.openrouter.constants",
    ),
    "palantir": (
        "anishift.services.llm.engines.palantir.service",
        "PalantirService",
        None,
    ),
}
"""Provider module, service class, and optional suggestions module by engine id."""


def available_engine_ids() -> tuple[LlmEngineId, ...]:
    """Return all registered LLM engine ids in stable order."""
    return tuple(_REGISTRY)


def create_engine(config: LlmConfig) -> LlmEngine:
    """Create only the provider engine selected by the caller."""
    module_path, class_name, _ = _get_registry_entry(config.engine_id)
    module = importlib.import_module(module_path)
    factory = cast("_EngineFactory", getattr(module, class_name))
    engine: LlmEngine = factory(config)
    return engine


def suggested_model_ids(engine_id: str) -> tuple[str, ...]:
    """Return lightweight UI suggestions without importing a provider SDK."""
    _, _, constants_path = _get_registry_entry(engine_id)
    if constants_path is None:
        return ()
    constants_module = importlib.import_module(constants_path)
    return cast("tuple[str, ...]", constants_module.SUGGESTED_MODEL_IDS)


def _get_registry_entry(engine_id: str) -> _RegistryEntry:
    if engine_id in _REGISTRY:
        return _REGISTRY[engine_id]
    available: str = ", ".join(_REGISTRY)
    message: str = f"Unknown LLM engine: {engine_id!r}. Available: {available}"
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_CONFIG_INVALID,
        message=message,
        suggestion="Select one of the registered LLM providers.",
        details={"engine_id": engine_id},
    )
    raise LlmConfigError(context=context)
