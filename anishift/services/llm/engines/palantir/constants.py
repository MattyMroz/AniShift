"""Built-in Palantir models, proxy routes and request options."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from anishift.services.llm.types import Modality
from anishift.services.llm.wire_protocol import ModelProtocol

__all__ = ["PALANTIR_MODELS", "PALANTIR_PROVIDERS", "SUGGESTED_MODEL_IDS", "PalantirModel", "PalantirProvider"]


@dataclass(frozen=True, slots=True)
class PalantirProvider:
    """Describe one Foundry proxy protocol and relative route."""

    provider_id: str
    protocol: ModelProtocol
    path: str


@dataclass(frozen=True, slots=True)
class PalantirModel:
    """Describe one model's identity, capabilities and request options."""

    alias: str
    provider_id: str
    model_id: str
    label: str
    file_modalities: frozenset[Modality]
    options: Mapping[str, object]
    variants: Mapping[str, Mapping[str, object]]


# ── Constants ────────────────────────────────────────────────────────────────

_RESPONSES_OPTIONS: Final[Mapping[str, object]] = {"store": False}
"""Default request options shared by OpenAI and xAI models."""

_CLAUDE_OPTIONS: Final[Mapping[str, object]] = {"thinking": {"type": "adaptive", "display": "summarized"}}
"""Adaptive thinking options for supported Claude models."""

_GEMINI_OPTIONS: Final[Mapping[str, object]] = {
    "generationConfig": {"thinkingConfig": {"includeThoughts": True, "thinkingBudget": -1}},
}
"""Dynamic thinking budget shared by Gemini models."""

_GEMINI_VARIANTS: Final[Mapping[str, Mapping[str, object]]] = {
    level: {"generationConfig": {"thinkingConfig": {"includeThoughts": budget != 0, "thinkingBudget": budget}}}
    for level, budget in (("none", 0), ("low", 2048), ("medium", 8192), ("high", 16384), ("max", 24576))
}
"""Explicit thinking budgets shared by Gemini models."""

_GROK_VARIANTS: Final[Mapping[str, Mapping[str, object]]] = {
    level: {"reasoning": {"effort": level}} for level in ("low", "high")
}
"""Reasoning efforts supported by Grok models."""

_THINKING_LEVELS: Final[tuple[str, ...]] = ("low", "medium", "high", "xhigh", "max")
"""Full thinking effort range for recent GPT and Claude models."""

PALANTIR_PROVIDERS: Final[tuple[PalantirProvider, ...]] = (
    PalantirProvider("foundry-openai", ModelProtocol.OPENAI_RESPONSES, "/api/v2/llm/proxy/openai/v1"),
    PalantirProvider("foundry-anthropic", ModelProtocol.ANTHROPIC_MESSAGES, "/api/v2/llm/proxy/anthropic/v1"),
    PalantirProvider("foundry-google", ModelProtocol.GOOGLE_GENERATE, "/api/v2/llm/proxy/google/v1"),
    PalantirProvider("foundry-xai", ModelProtocol.XAI_RESPONSES, "/api/v2/llm/proxy/xai/v1"),
)
"""Foundry provider routes in model-family order."""


def _gpt(
    model_id: str,
    label: str,
    levels: tuple[str, ...],
    *,
    file_modalities: frozenset[Modality] = frozenset({"image", "pdf"}),
) -> PalantirModel:
    return PalantirModel(
        alias=f"foundry/{model_id}",
        provider_id="foundry-openai",
        model_id=model_id,
        label=label,
        file_modalities=file_modalities,
        options=_RESPONSES_OPTIONS,
        variants={level: {"reasoning": {"effort": level}} for level in levels},
    )


def _claude(model_id: str, label: str, levels: tuple[str, ...]) -> PalantirModel:
    return PalantirModel(
        alias=f"foundry-anthropic/{model_id}",
        provider_id="foundry-anthropic",
        model_id=model_id,
        label=label,
        file_modalities=frozenset({"image", "pdf"}),
        options=_CLAUDE_OPTIONS,
        variants={level: {"output_config": {"effort": level}} for level in levels},
    )


def _gemini(model_id: str, label: str) -> PalantirModel:
    return PalantirModel(
        alias=f"foundry-google/{model_id}",
        provider_id="foundry-google",
        model_id=model_id,
        label=label,
        file_modalities=frozenset({"image", "pdf", "audio", "video"}),
        options=_GEMINI_OPTIONS,
        variants=_GEMINI_VARIANTS,
    )


def _grok(model_id: str, label: str) -> PalantirModel:
    return PalantirModel(
        alias=f"foundry-xai/{model_id}",
        provider_id="foundry-xai",
        model_id=model_id,
        label=label,
        file_modalities=frozenset({"image"}),
        options=_RESPONSES_OPTIONS,
        variants=_GROK_VARIANTS,
    )


# ── Constants ────────────────────────────────────────────────────────────────

PALANTIR_MODELS: Final[tuple[PalantirModel, ...]] = (
    _gpt("gpt-6-astra", "Foundry: GPT-6 Astra", _THINKING_LEVELS),
    _gpt("gpt-6-sol", "Foundry: GPT-6 Sol", ("none", *_THINKING_LEVELS), file_modalities=frozenset({"image"})),
    _gpt("gpt-6-luna", "Foundry: GPT-6 Luna", ("none", *_THINKING_LEVELS), file_modalities=frozenset({"image"})),
    _gpt("gpt-5.6-sol", "Foundry: GPT-5.6 Sol", ("none", *_THINKING_LEVELS)),
    _gpt("gpt-5.6-terra", "Foundry: GPT-5.6 Terra", ("none", *_THINKING_LEVELS)),
    _gpt("gpt-5.6-luna", "Foundry: GPT-5.6 Luna", ("none", *_THINKING_LEVELS)),
    _gpt("gpt-5.5", "Foundry: GPT-5.5", ("none", "low", "medium", "high", "xhigh")),
    _claude("claude-opus-5", "Foundry: Claude Opus 5", _THINKING_LEVELS),
    _claude("claude-opus-4-8", "Foundry: Claude Opus 4.8", _THINKING_LEVELS),
    _claude("claude-opus-4-7", "Foundry: Claude Opus 4.7", _THINKING_LEVELS),
    _claude("claude-opus-4-6", "Foundry: Claude Opus 4.6", ("low", "medium", "high", "max")),
    PalantirModel(
        alias="foundry-anthropic/claude-opus-4-5",
        provider_id="foundry-anthropic",
        model_id="claude-opus-4-5",
        label="Foundry: Claude Opus 4.5",
        file_modalities=frozenset({"image", "pdf"}),
        options={},
        variants={},
    ),
    _claude("claude-sonnet-5", "Foundry: Claude Sonnet 5", _THINKING_LEVELS),
    _claude("claude-sonnet-4-6", "Foundry: Claude Sonnet 4.6", ("low", "medium", "high", "max")),
    _gemini("gemini-3.1-pro-preview", "Foundry: Gemini 3.1 Pro Preview"),
    _gemini("gemini-3.8-flash", "Foundry: Gemini 3.8 Flash"),
    _gemini("gemini-3.7-flash", "Foundry: Gemini 3.7 Flash"),
    _gemini("gemini-3.6-flash", "Foundry: Gemini 3.6 Flash"),
    _gemini("gemini-3.5-flash", "Foundry: Gemini 3.5 Flash"),
    _gemini("gemini-3.5-flash-lite", "Foundry: Gemini 3.5 Flash-Lite"),
    _grok("grok-4.6", "Foundry: Grok 4.6"),
    _grok("grok-4.5", "Foundry: Grok 4.5"),
)
"""Supported models in the order of the verified Foundry configuration."""

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = tuple(model.alias for model in PALANTIR_MODELS)
"""Model aliases exposed by the lazy engine registry."""
