"""LLM translation engine runtime config."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LlmTranslateConfig:
    """Runtime config for the LLM translation engine.

    Attributes:
        max_repair_attempts: Times to re-ask on a line-count mismatch before
            shrinking the batch.
        min_batch_size: Batch-size floor for the shrink-to-1 cascade.
    """

    max_repair_attempts: int = 2
    min_batch_size: int = 1


__all__ = ["LlmTranslateConfig"]
