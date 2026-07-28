"""LLM translation engine runtime config."""

from __future__ import annotations

from dataclasses import dataclass, field

from anishift.services.translation.engines.llm.prompts.types import PromptContext


@dataclass(frozen=True, slots=True)
class LlmTranslateConfig:
    """Runtime config for the LLM translation engine.

    Attributes:
        max_batch_lines: Maximum non-empty lines sent in one completion.
        prompt_id: Selected translation task prompt.
        prompt_version: Version of the selected task prompt.
        style_id: Selected translation style prompt.
        module_ids: Optional reusable prompt module identifiers.
        context: Bounded dynamic metadata and glossary for one file.
    """

    max_batch_lines: int = 1000
    prompt_id: str = "anime_translation_v1"
    prompt_version: int = 1
    style_id: str = "natural_polish_v1"
    module_ids: tuple[str, ...] = ()
    context: PromptContext = field(default_factory=PromptContext)

    def __post_init__(self) -> None:
        """Validate limits and prompt identity."""
        if self.max_batch_lines <= 0:
            msg = "max_batch_lines must be greater than zero"
            raise ValueError(msg)
        if not self.prompt_id.strip():
            msg = "prompt_id must not be empty"
            raise ValueError(msg)
        if self.prompt_version <= 0:
            msg = "prompt_version must be greater than zero"
            raise ValueError(msg)
        if not self.style_id.strip():
            msg = "style_id must not be empty"
            raise ValueError(msg)
        if any(not module_id.strip() for module_id in self.module_ids):
            msg = "module_ids must not contain empty identifiers"
            raise ValueError(msg)


__all__ = ["LlmTranslateConfig"]
