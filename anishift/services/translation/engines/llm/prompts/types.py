"""Typed values used by the LLM translation prompt subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from anishift.services.translation.protocols import PromptIdentity

PromptAssetKind = Literal["task", "style", "module", "contract"]
"""Supported static prompt asset categories."""


@dataclass(frozen=True, slots=True)
class PromptAsset:
    """One validated static prompt asset."""

    asset_id: str
    version: int
    kind: PromptAssetKind
    text: str
    source: str


@dataclass(frozen=True, slots=True)
class ComposedPrompt:
    """A complete provider request plus its static prompt identity."""

    system: str
    user: str
    identity: PromptIdentity
    omitted_context_items: int


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    """One caller-supplied source-to-target terminology hint."""

    source: str
    target: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class PromptContext:
    """Bounded dynamic context supplied for one translated file."""

    title: str = ""
    summary: str = ""
    glossary: tuple[GlossaryEntry, ...] = ()


__all__ = [
    "ComposedPrompt",
    "GlossaryEntry",
    "PromptAsset",
    "PromptAssetKind",
    "PromptContext",
]
