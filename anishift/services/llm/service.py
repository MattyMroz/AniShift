"""Synchronous lifecycle facade for provider-neutral LLM completions."""

from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType
from typing import Self

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm._retry import retry_transient
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines import create_engine
from anishift.services.llm.errors import LlmAuthError, LlmCancelledError, LlmConfigError
from anishift.services.llm.protocols import LlmAttemptObserver, LlmEngine, StreamingLlmEngine
from anishift.services.llm.types import LlmRequest, LlmResponse
from anishift.utils.logger import get_logger

__all__ = ["LlmService"]

logger = get_logger(__name__)


class LlmService:
    """Manage one lazy provider engine and its synchronous retry lifecycle."""

    __slots__ = ("_closed", "_engine", "_observer", "config")

    def __init__(
        self,
        config: LlmConfig,
        *,
        observer: LlmAttemptObserver | None = None,
    ) -> None:
        """Create a facade without constructing the selected provider engine."""
        self.config: LlmConfig = config
        self._observer: LlmAttemptObserver | None = observer
        self._engine: LlmEngine | None = None
        self._closed: bool = False

    @property
    def is_available(self) -> bool:
        """Return whether required local configuration is present."""
        if self._closed:
            return False
        if self.config.engine_id == "openai_compatible":
            return bool(self.config.base_url and self.config.base_url.strip())
        return bool(self.config.api_key.strip())

    def complete(
        self,
        request: LlmRequest,
        *,
        cancel: threading.Event | None = None,
        on_text: Callable[[str], None] | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> LlmResponse:
        """Complete one request using the lazy engine and central retry policy."""
        self._ensure_open()
        self._ensure_available()
        logger.debug(
            "LLM completion started",
            provider=self.config.engine_id,
            model=self.config.provider_model_id,
            message_count=len(request.messages),
            max_retries=self.config.max_retries,
        )

        def attempt() -> LlmResponse:
            if on_start is not None:
                on_start()
            return self._complete_once(request, receive)

        def receive(delta: str) -> None:
            if cancel is not None and cancel.is_set():
                msg = "LLM operation was cancelled"
                raise LlmCancelledError(msg)
            if on_text is not None:
                on_text(delta)

        response = retry_transient(
            attempt,
            max_retries=self.config.max_retries,
            observer=self._observer,
            cancel=cancel,
        )
        logger.info(
            "LLM completion completed",
            provider=response.engine_id,
            model=response.provider_model_id,
            finish_reason=response.finish_reason,
            latency_ms=response.latency_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
        )
        return response

    def _complete_once(self, request: LlmRequest, on_text: Callable[[str], None] | None) -> LlmResponse:
        engine: LlmEngine = self._get_or_create_engine()
        if isinstance(engine, StreamingLlmEngine):
            return engine.complete_stream(request, on_text=on_text)
        return engine.complete(request)

    def close(self) -> None:
        """Close the provider engine once and permanently close the facade."""
        if self._closed:
            return
        self._closed = True
        engine: LlmEngine | None = self._engine
        self._engine = None
        if engine is not None:
            engine.close()
        logger.debug("LLM service closed", provider=self.config.engine_id)

    def __enter__(self) -> Self:
        """Enter the facade context without constructing an engine."""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the provider engine when leaving the facade context."""
        self.close()

    def _get_or_create_engine(self) -> LlmEngine:
        if self._engine is None:
            self._engine = create_engine(self.config)
            logger.debug(
                "LLM provider engine created",
                provider=self.config.engine_id,
                model=self.config.provider_model_id,
            )
        return self._engine

    def _ensure_open(self) -> None:
        if not self._closed:
            return
        message: str = "LLM service is already closed"
        context: ErrorContext = ErrorContext(
            code=ErrorCode.LLM_CONFIG_INVALID,
            message=message,
            suggestion="Create a new LLM service for another completion.",
        )
        raise LlmConfigError(context=context)

    def _ensure_available(self) -> None:
        if self.is_available:
            return
        if self.config.engine_id == "openai_compatible":
            message: str = "OpenAI-compatible LLM provider requires a base URL"
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_CONFIG_INVALID,
                message=message,
                suggestion="Configure ANISHIFT_OPENAI_COMPATIBLE_BASE_URL before retrying.",
            )
            raise LlmConfigError(context=context)
        message = f"LLM provider {self.config.engine_id!r} requires an API key"
        context = ErrorContext(
            code=ErrorCode.LLM_AUTH_FAILED,
            message=message,
            suggestion="Configure the provider API key in the AniShift environment.",
        )
        raise LlmAuthError(context=context)
