"""Pipeline value objects and callback protocols."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from anishift.services.extraction.types import MediaInfo, TrackSelection
    from anishift.services.subtitles.classifier import StyleVerdict
    from anishift.services.translation.protocols import PromptPurpose
    from anishift.services.translation.types import FileTranslation

__all__ = [
    "FileFailure",
    "FileOutcome",
    "FileStatus",
    "LlmCallRecord",
    "LlmSettings",
    "PipelineInteraction",
    "PipelineReport",
    "ProgressPhase",
    "ProgressReporter",
    "StepName",
    "TranslationSettings",
]

StepName = Literal["identify", "select", "extract", "split", "write", "translate", "txt"]
"""Pipeline step a failure is attributed to."""

FileStatus = Literal["done", "failed", "cancelled", "not_processed"]
"""Final state of one input file."""


@dataclass(frozen=True, slots=True)
class LlmCallRecord:
    """Content-free metadata for one logical LLM completion."""

    purpose: PromptPurpose
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    reported_cost: float | None
    latency_ms: float | None
    finish_reason: str
    prompt_id: str
    prompt_version: int
    style_id: str
    prompt_fingerprint: str
    transport_retries: int = 0
    omitted_context_items: int = 0
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class LlmSettings:
    """Resolved provider, prompt, concurrency, and secret settings for one run."""

    provider: str
    model: str
    prompt_id: str
    style_id: str
    module_ids: tuple[str, ...]
    max_concurrency: int
    max_retries: int
    prompt_root: Path = Path("config/prompts")
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    timeout_s: float = 60.0
    anthropic_api_key: str = field(default="", repr=False)
    gemini_api_key: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    deepseek_api_key: str = field(default="", repr=False)
    openrouter_api_key: str = field(default="", repr=False)
    openai_compatible_api_key: str = field(default="", repr=False)
    openai_compatible_base_url: str = field(default="", repr=False)

    def api_key(self) -> str:
        """Return the secret routed to the selected provider."""
        keys: dict[str, str] = {
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "openrouter": self.openrouter_api_key,
            "openai_compatible": self.openai_compatible_api_key,
        }
        return keys.get(self.provider, "")


@dataclass(frozen=True, slots=True)
class FileFailure:
    """Describe why one input file failed."""

    step: StepName
    code: str
    message: str
    suggestion: str


@dataclass(slots=True)
class FileOutcome:
    """Describe everything produced for one input file."""

    source: Path
    status: FileStatus
    audio_path: Path | None = None
    subtitle_path: Path | None = None
    displayed_path: Path | None = None
    translated_path: Path | None = None
    lektor_path: Path | None = None
    already_polish: bool = False
    spoken_lines: int = 0
    displayed_events: int = 0
    drawing_events: int = 0
    collapsed_away: int = 0
    translation: FileTranslation | None = None
    translated_lines: int = 0
    translation_engine: str = ""
    translation_failed_lines: int = 0
    warnings: tuple[str, ...] = ()
    failure: FileFailure | None = None
    llm_calls: tuple[LlmCallRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class TranslationSettings:
    """Translation parameters resolved once from AppContext for the runner.

    Attributes:
        engine: Selected translation engine id.
        fallback_chain: Ordered fallback engine ids.
        batch_size: Lines per request (0 = engine default).
        max_retries: Retry attempts per batch.
        deepl_api_key: DeepL key (used by the deepl engine, ignored by google).
    """

    engine: str
    fallback_chain: tuple[str, ...]
    batch_size: int
    max_retries: int
    deepl_api_key: str
    llm: LlmSettings | None = None


@dataclass(frozen=True, slots=True)
class PipelineReport:
    """Collect per-file outcomes in discovery order."""

    outcomes: tuple[FileOutcome, ...]


class ProgressReporter(Protocol):
    """Define the progress display operations used by the runner."""

    def add_task(self, description: str, *, total: int = 100) -> int:
        """Register one progress row."""
        ...

    def update(self, task_id: int, completed: int) -> None:
        """Set one progress row's absolute completion."""
        ...


class ProgressPhase(Protocol):
    """A progress display for one pipeline phase, entered per phase.

    Each phase is a fresh transient display: its rows disappear on exit so
    the next phase draws its own rows in the same place.
    """

    def __enter__(self) -> ProgressReporter:
        """Start the phase display and return its reporter."""
        ...

    def __exit__(self, *exc: object) -> None:
        """Stop the phase display, clearing its rows."""
        ...


class PipelineInteraction(Protocol):
    """Define manual-mode decisions supplied by the CLI."""

    def choose_tracks(self, info: MediaInfo, proposal: TrackSelection) -> TrackSelection:
        """Confirm or override the selected tracks."""
        ...

    def choose_spoken_styles(
        self,
        source: Path,
        verdicts: Sequence[StyleVerdict],
        samples: Mapping[str, tuple[str, ...]],
    ) -> set[str] | None:
        """Choose spoken styles, or return None to accept auto selection."""
        ...
