"""LLM translation engine runtime config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from anishift.services.translation.engines.llm.constants import DEFAULT_STYLE_NAME

# ── Constants ────────────────────────────────────────────────────────────────

MAX_CONTRACT_RETRIES: Final[int] = 10
"""Maximum allowed retries after an invalid LLM response."""


@dataclass(frozen=True, slots=True)
class LlmTranslateConfig:
    """Runtime config for the LLM translation engine.

    Attributes:
        max_batch_lines: Maximum non-empty lines sent in one completion.
        style_name: Selected packaged translation style.
        max_contract_retries: Additional attempts after invalid JSON output.
    """

    max_batch_lines: int = 1000
    style_name: str = DEFAULT_STYLE_NAME
    max_contract_retries: int = 3

    def __post_init__(self) -> None:
        """Validate batching, style and retry limits."""
        if self.max_batch_lines <= 0:
            msg = "max_batch_lines must be greater than zero"
            raise ValueError(msg)
        if not self.style_name.strip() or self.style_name != self.style_name.strip():
            msg = "style_name must be a non-empty trimmed name"
            raise ValueError(msg)
        if "/" in self.style_name or "\\" in self.style_name or self.style_name in {".", ".."}:
            msg = "style_name must be a name, not a path"
            raise ValueError(msg)
        if not 0 <= self.max_contract_retries <= MAX_CONTRACT_RETRIES:
            msg = f"max_contract_retries must be between 0 and {MAX_CONTRACT_RETRIES}"
            raise ValueError(msg)


__all__ = ["LlmTranslateConfig"]
