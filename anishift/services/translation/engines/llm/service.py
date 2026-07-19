"""LLM translation engine (provider-agnostic via injected LlmCompleter).

Does NOT import ``anishift.services.llm`` (independence; stage 5 wires the real
completer). Uses the numbered ``[N] text`` protocol (not JSON): the parser keeps
only lines matching ``[N] text`` and validates that indices 1..N each appear
once. A fallback ladder recovers from mismatches: parse -> repair retry ->
shrink batch -> per-line -> pad source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.constants import LINE_PATTERN, SYSTEM_PROMPT
from anishift.services.translation.types import BatchedLine

if TYPE_CHECKING:
    from anishift.services.translation.config import TranslationConfig
    from anishift.services.translation.protocols import LlmCompleter


def _parse_numbered(text: str, expected: int) -> list[str] | None:
    """Parse ``[N] text`` lines into ordered texts, or None on a mismatch.

    Args:
        text: Raw model output (may include intro/markdown/outro noise).
        expected: Number of lines that must be present (indices 1..expected).

    Returns:
        The translated texts in index order, or ``None`` when any index is
        missing, duplicated or out of range.
    """
    by_index: dict[int, str] = {}
    for line in text.splitlines():
        match = LINE_PATTERN.match(line)
        if match is None:
            continue
        index = int(match.group(1))
        if index in by_index:
            return None  # a duplicated index means the model repeated a line
        by_index[index] = match.group(2).strip()
    if set(by_index) != set(range(1, expected + 1)):
        return None
    return [by_index[index] for index in range(1, expected + 1)]


class LlmTranslateService:
    """Translation engine prompting an injected LLM for numbered [N] output."""

    __slots__ = ("_completer", "_config")

    def __init__(
        self,
        config: TranslationConfig | LlmTranslateConfig,
        *,
        completer: LlmCompleter,
    ) -> None:
        """Store config and the injected completer."""
        self._config = config if isinstance(config, LlmTranslateConfig) else LlmTranslateConfig()
        self._completer = completer

    @property
    def engine_id(self) -> str:
        """Stable engine identifier (registry key)."""
        return "llm"

    @property
    def is_available(self) -> bool:
        """Whether a completer is wired in."""
        return self._completer is not None

    def close(self) -> None:
        """No-op: the completer is owned by the composition root."""

    def translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> list[BatchedLine]:
        """Translate a batch via the numbered round-trip with a fallback ladder."""
        del source_lang  # the LLM infers the source language from the text
        if not texts:
            return []
        parsed = self._ask(texts, target_lang=target_lang)
        if parsed is not None:
            return [BatchedLine(text=text, ok=True) for text in parsed]
        for _ in range(self._config.max_repair_attempts):
            parsed = self._ask(texts, target_lang=target_lang, repair=True)
            if parsed is not None:
                return [BatchedLine(text=text, ok=True) for text in parsed]
        return self._shrink(texts, target_lang=target_lang)

    def _shrink(self, texts: list[str], *, target_lang: str) -> list[BatchedLine]:
        """Split the batch in half and recurse down to per-line translation."""
        if len(texts) <= self._config.min_batch_size:
            return self._per_line(texts, target_lang=target_lang)
        mid = len(texts) // 2
        left = self.translate_batch(texts[:mid], source_lang="auto", target_lang=target_lang)
        right = self.translate_batch(texts[mid:], source_lang="auto", target_lang=target_lang)
        return left + right

    def _per_line(self, texts: list[str], *, target_lang: str) -> list[BatchedLine]:
        """Translate each line alone; pad source on failure."""
        out: list[BatchedLine] = []
        for text in texts:
            parsed = self._ask([text], target_lang=target_lang)
            if parsed is not None:
                out.append(BatchedLine(text=parsed[0], ok=True))
            else:
                out.append(BatchedLine(text=text, ok=False))
        return out

    def _ask(self, texts: list[str], *, target_lang: str, repair: bool = False) -> list[str] | None:
        """Prompt the completer once and parse the numbered response."""
        user = self._build_user(texts, target_lang=target_lang, repair=repair)
        try:
            response = self._completer.complete(SYSTEM_PROMPT, user)
        except Exception:  # noqa: BLE001 - completer boundary: any failure -> fallback ladder
            return None
        return _parse_numbered(response, len(texts))

    def _build_user(self, texts: list[str], *, target_lang: str, repair: bool) -> str:
        """Build the numbered user prompt, optionally with a repair reminder."""
        numbered = "\n".join(f"[{index}] {text}" for index, text in enumerate(texts, start=1))
        prompt = f"Target language: {target_lang}\n{numbered}"
        if repair:
            prompt += f"\n\nReturn EXACTLY {len(texts)} numbered lines [1]..[{len(texts)}], do not merge lines."
        return prompt


__all__ = ["LlmTranslateService"]
