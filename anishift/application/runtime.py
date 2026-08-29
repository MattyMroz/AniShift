"""Production construction of run-scoped task handlers."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from anishift.application.handlers import (
    AudioTaskHandler,
    CompositionTaskHandler,
    ExecutionHandlers,
    ExtractionTaskHandler,
    LegacyExtractionAdapter,
    PublishTaskHandler,
    SubtitleTaskHandler,
    TranslationTaskHandler,
    TtsTaskHandler,
)
from anishift.application.inspection import InspectedSourceGroup
from anishift.application.planning import ExecutionPlan, RunSettingsSnapshot, TaskKind
from anishift.application.tts_clips import FfmpegClipService
from anishift.application.tts_handler import TtsProgressObserver
from anishift.config.model_catalog import ModelCatalog, ModelEntry, ProviderEntry, load_model_catalog
from anishift.config.user_settings import (
    PALANTIR_ENROLLMENT_URL_PATTERN,
    UserSettings,
    config_path,
    load_user_settings,
)
from anishift.errors import AniShiftError, ConfigError, ErrorCode, ErrorContext, TransientError
from anishift.platform.binaries import Binary, require_binary
from anishift.services.audio import (
    AudioConfig,
    AudioRenderRequest,
    AudioRenderResult,
    AudioService,
    AudioTranscodeService,
)
from anishift.services.audio.commands import SubprocessRunner
from anishift.services.audio.service import AudioProgressSink
from anishift.services.audio.types import AudioCodecProfile, TimelinePolicy
from anishift.services.composition import CompositionConfig, CompositionService, QualityPreset
from anishift.services.extraction import ExtractionService, extract_tracks, identify
from anishift.services.llm import (
    LlmAuthError,
    LlmCancelledError,
    LlmConfig,
    LlmConfigError,
    LlmContextLengthError,
    LlmError,
    LlmMessage,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequest,
    LlmRequestError,
    LlmRole,
    LlmService,
    LlmTimeoutError,
    TextPart,
)
from anishift.services.llm.engines.palantir import PALANTIR_ENGINE_ID, PalantirModelConfig, palantir_model_config
from anishift.services.translation import TranslationConfig, TranslationService
from anishift.services.translation.constants import DEFAULT_BATCH_SIZE
from anishift.services.translation.engines import create_engine
from anishift.services.translation.engines.llm import LlmTranslateConfig, LlmTranslateService
from anishift.services.translation.engines.llm.prompts import PromptRegistry
from anishift.services.translation.engines.llm.prompts.types import PromptContext
from anishift.services.translation.errors import (
    TranslationAuthError,
    TranslationContextLengthError,
    TranslationEngineError,
    TranslationError,
    TranslationQuotaError,
    TranslationRateLimitError,
)
from anishift.services.translation.protocols import (
    LlmCompletionRequest,
    LlmCompletionResult,
    TranslationCancellation,
    TranslationEngine,
    TranslationInputPolicy,
    TranslationObserver,
    TranslationStream,
)
from anishift.services.translation.types import BatchedLine, FileTranslation
from anishift.services.tts import SpeechBatch, SpeechBatchResult, TtsConfig, TtsService
from anishift.services.tts.config import DEFAULT_RETRY_BACKOFF_SECONDS

if TYPE_CHECKING:
    from anishift.config.settings import Settings
    from anishift.services.subtitles import DisplayedLine, SpokenLine

__all__ = ["ProductionHandlerFactory", "palantir_llm_config", "probe_palantir_model"]

# ── Constants ────────────────────────────────────────────────────────────────

_EXTRACTION_TIMEOUT_S: Final[float] = 120.0
"""Maximum time allowed for one neutral track extraction."""

_PROBE_PROMPT: Final[str] = "ping"
"""Shortest prompt of the single request one explicit connection test sends."""

_PROBE_MAX_OUTPUT_TOKENS: Final[int] = 16
"""Output cap of that request, small enough to stay a negligible cost."""

_ENROLLMENT_SETTING_ID: Final[str] = "palantir_enrollment_base_url"
"""Preference naming the enrollment address in a configuration failure."""

_ENROLLMENT_URL_RE: Final[re.Pattern[str]] = re.compile(PALANTIR_ENROLLMENT_URL_PATTERN)
"""Compiled form of the enrollment-address rule owned by ``user_settings``."""

_AUDIO_TIMEOUT_S: Final[float] = 30.0
"""Maximum time allowed for one audio validation or conversion process."""

_TTS_REQUEST_TIMEOUT_S: Final[dict[str, float]] = {"elevenbytes": 45.0, "sapi": 10.0}
"""Provider request deadlines that differ from the neutral default."""

_TTS_RETRY_BACKOFF_S: Final[dict[str, tuple[float, ...]]] = {
    "elevenbytes": (5.0, 10.0, 15.0, 30.0),
}
"""Provider retry delays retained from the validated legacy runtime."""


class _TranslationExecutor(Protocol):
    def translate_file(  # noqa: PLR0913
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation: ...


class ProductionHandlerFactory:
    """Build only the concrete services required by one accepted plan."""

    __slots__ = ("_settings_provider",)

    def __init__(self, settings_provider: Callable[[], Settings]) -> None:
        self._settings_provider: Callable[[], Settings] = settings_provider

    def __call__(
        self,
        run_root: Path,
        plan: ExecutionPlan,
        source_groups: Mapping[str, InspectedSourceGroup],
    ) -> ExecutionHandlers:
        """Construct a run-owned dispatcher from immutable execution choices."""
        settings: Settings = self._settings_provider()
        kinds: frozenset[TaskKind] = frozenset(task.kind for task in plan.tasks)
        tts_handler: TtsTaskHandler | None = self._tts_handler(settings, run_root, plan, kinds)
        audio_handler: AudioTaskHandler | None = self._audio_handler(run_root, plan, kinds)
        composition_handler: CompositionTaskHandler | None = self._composition_handler(
            run_root,
            plan,
            kinds,
        )
        publish_handler: PublishTaskHandler | None = None
        if TaskKind.PUBLISH_ARTIFACT in kinds:
            publish_handler = PublishTaskHandler(
                run_root=run_root,
                source_groups={group_id: group.source for group_id, group in source_groups.items()},
            )
        return ExecutionHandlers(
            ExtractionTaskHandler(
                ExtractionService(),
                run_root=run_root,
                timeout_s=_EXTRACTION_TIMEOUT_S,
                legacy=LegacyExtractionAdapter(identify, extract_tracks),
            ),
            SubtitleTaskHandler(run_root=run_root),
            TranslationTaskHandler(
                _translation_service(settings, plan),
                run_root=run_root,
            ),
            tts=tts_handler,
            audio=audio_handler,
            composition=composition_handler,
            publish=publish_handler,
        )

    @staticmethod
    def _tts_handler(
        settings: Settings,
        run_root: Path,
        plan: ExecutionPlan,
        kinds: frozenset[TaskKind],
    ) -> TtsTaskHandler | None:
        if TaskKind.SYNTHESIZE_SPEECH not in kinds:
            return None
        ffmpeg: Path = require_binary(Binary.FFMPEG)
        ffprobe: Path = require_binary(Binary.FFPROBE)
        runner = SubprocessRunner()
        clip_cancel = threading.Event()
        clips = FfmpegClipService(
            cancel=clip_cancel,
            runner=runner,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            timeout_s=_AUDIO_TIMEOUT_S,
        )
        service = TtsService(
            _tts_config(settings, plan),
            resume_root=run_root / "tts",
            validator=clips,
            assembler=clips,
        )
        ranks: dict[str, int] = {group.group_id: rank for rank, group in enumerate(plan.groups)}
        return TtsTaskHandler(_RunTtsService(service, clip_cancel), run_root=run_root, group_ranks=ranks)

    @staticmethod
    def _audio_handler(
        run_root: Path,
        plan: ExecutionPlan,
        kinds: frozenset[TaskKind],
    ) -> AudioTaskHandler | None:
        if not kinds.intersection({TaskKind.MIX_NARRATION, TaskKind.TRANSCODE_AUDIO}):
            return None
        config: AudioConfig = _audio_config(plan)
        return AudioTaskHandler(
            _ConfiguredAudioService(AudioService(config), plan.settings.tts_postprocess_tempo),
            AudioTranscodeService(config),
            run_root=run_root,
        )

    @staticmethod
    def _composition_handler(
        run_root: Path,
        plan: ExecutionPlan,
        kinds: frozenset[TaskKind],
    ) -> CompositionTaskHandler | None:
        if not kinds.intersection({TaskKind.COMPOSE_MKV, TaskKind.COMPOSE_MP4}):
            return None
        service = CompositionService(
            CompositionConfig(quality_preset=QualityPreset(plan.settings.composition_profile_id)),
        )
        return CompositionTaskHandler(service, run_root=run_root)


class _RunTtsService:
    __slots__ = ("_clip_cancel", "_service")

    def __init__(self, service: TtsService, clip_cancel: threading.Event) -> None:
        self._service: TtsService = service
        self._clip_cancel: threading.Event = clip_cancel

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        return self._service.synthesize(batch, callbacks=callbacks)

    def cancel(self) -> None:
        self._clip_cancel.set()
        self._service.cancel()

    def close(self) -> None:
        self._clip_cancel.set()
        self._service.close()


class _ConfiguredAudioService:
    __slots__ = ("_post_process_tempo", "_service")

    def __init__(self, service: AudioService, post_process_tempo: float) -> None:
        self._service: AudioService = service
        self._post_process_tempo: float = post_process_tempo

    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        configured: AudioRenderRequest = replace(request, post_process_tempo=self._post_process_tempo)
        return self._service.render(configured, callbacks=callbacks, cancel=cancel)


class _TranslationRuntime:
    __slots__ = ("_llm_cancel", "_service")

    def __init__(self, service: TranslationService, llm_cancel: threading.Event) -> None:
        self._service: TranslationService = service
        self._llm_cancel: threading.Event = llm_cancel

    def translate_file(  # noqa: PLR0913
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        stop = threading.Event()
        watcher: threading.Thread | None = None
        if cancel is not None:
            watcher = threading.Thread(target=_mirror_translation_cancel, args=(cancel, self._llm_cancel, stop))
            watcher.start()
        try:
            return self._service.translate_file(
                spoken,
                displayed,
                source_lang=source_lang,
                target_lang=target_lang,
                cancel=cancel,
                observer=observer,
            )
        finally:
            stop.set()
            if watcher is not None:
                watcher.join()


class _LlmTranslationEngine:
    __slots__ = ("_cancel", "_config", "_engine", "_llm_config", "_service")

    def __init__(
        self,
        config: LlmConfig,
        translation_config: LlmTranslateConfig,
        *,
        cancel: threading.Event,
    ) -> None:
        self._config: LlmConfig = config
        self._llm_config: LlmTranslateConfig = translation_config
        self._cancel: threading.Event = cancel
        self._service: LlmService | None = None
        self._engine: LlmTranslateService | None = None

    @property
    def engine_id(self) -> str:
        return "llm"

    @property
    def is_available(self) -> bool:
        if self._config.engine_id == "openai_compatible":
            return bool(self._config.base_url and self._config.base_url.strip())
        return bool(self._config.api_key.strip())

    def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy:
        return "preserve" if stream == "spoken" else "deduplicate"

    def translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
        observer: TranslationObserver | None = None,
    ) -> list[BatchedLine]:
        service = LlmService(
            self._config,
            observer=_LlmRetryObserver(observer, max_retries=self._config.max_retries),
        )
        engine = LlmTranslateService(
            self._llm_config,
            completer=_LlmCompleter(service, self._cancel),
            prompt_registry=PromptRegistry(custom_root=config_path().parent / "prompts"),
        )
        self._service = service
        self._engine = engine
        return engine.translate_batch(texts, source_lang=source_lang, target_lang=target_lang, observer=observer)

    def close(self) -> None:
        if self._service is not None:
            self._service.close()
            self._service = None
        self._engine = None


class _LlmCompleter:
    __slots__ = ("_cancel", "_service")

    def __init__(self, service: LlmService, cancel: threading.Event) -> None:
        self._service: LlmService = service
        self._cancel: threading.Event = cancel

    def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        llm_request = LlmRequest(
            messages=(
                LlmMessage(role=LlmRole.SYSTEM, parts=(TextPart(request.system),)),
                LlmMessage(role=LlmRole.USER, parts=(TextPart(request.user),)),
            ),
        )
        try:
            response = self._service.complete(llm_request, cancel=self._cancel)
        except LlmError as error:
            _raise_translation_error(error)
        return LlmCompletionResult(response.text, response.finish_reason)


class _LlmRetryObserver:
    __slots__ = ("_attempt", "_delegate", "_max_retries")

    def __init__(self, delegate: TranslationObserver | None, *, max_retries: int) -> None:
        self._delegate: TranslationObserver | None = delegate
        self._max_retries: int = max_retries
        self._attempt: int = 0

    def before_attempt(self) -> None:
        self._attempt += 1

    def on_transient_failure(self, error: TransientError) -> None:
        del error
        if self._delegate is not None:
            self._delegate.retry("llm", self._attempt, self._max_retries + 1)

    def on_success(self) -> None: ...

    def on_fatal_failure(self, error: AniShiftError) -> None:
        del error


def _translation_service(settings: Settings, plan: ExecutionPlan) -> _TranslationExecutor:
    snapshot = plan.settings
    llm_cancel = threading.Event()
    config = TranslationConfig(
        engine=snapshot.translation_profile_id,
        source_lang="auto",
        batch_size=snapshot.translation_batch_size or DEFAULT_BATCH_SIZE,
        max_retries=snapshot.translation_max_retries,
        api_key=settings.deepl_api_key,
    )

    def engine_factory(engine_id: str, engine_config: TranslationConfig) -> TranslationEngine:
        if engine_id != "llm":
            translated = TranslationConfig(
                engine=engine_id,
                source_lang=engine_config.source_lang,
                batch_size=engine_config.batch_size,
                max_retries=engine_config.max_retries,
                api_key=engine_config.api_key,
            )
            return create_engine(translated)
        return _LlmTranslationEngine(
            _llm_config(settings, plan),
            LlmTranslateConfig(
                prompt_id=snapshot.llm_prompt_id,
                style_id=snapshot.llm_style_id,
                module_ids=snapshot.llm_module_ids,
                context=PromptContext(),
            ),
            cancel=llm_cancel,
        )

    service = TranslationService(
        config,
        engine_factory=engine_factory,
        fallback_chain=snapshot.translation_fallback_chain,
    )
    return _TranslationRuntime(service, llm_cancel)


def palantir_llm_config(
    catalog: ModelCatalog,
    alias: str,
    *,
    enrollment_base_url: str,
    token: str,
    max_retries: int = 0,
) -> LlmConfig:
    """Resolve one catalog alias into a complete Palantir configuration.

    The alias becomes a provider, a wire protocol, the endpoint joining the
    enrollment address with that provider route, and the exact provider model
    identifier — everything the engine needs before it may open a connection.

    Args:
        catalog: Validated local catalog; nothing here writes it.
        alias: Catalog alias the user selected.
        enrollment_base_url: ``UserSettings.palantir_enrollment_base_url``.
        token: ``Settings.palantir_token``, already folded from the environment,
            the ``.env`` file and the compatibility variable.
        max_retries: Retries the LLM service may spend on transient failures.

    Returns:
        The neutral configuration carrying the alias, provider, protocol,
        endpoint, provider model identifier and the token.

    Raises:
        ConfigError: The alias is unknown to the catalog, its provider is
            unusable, or the enrollment address is unset or malformed.
        LlmAuthError: The token is absent or cannot be sent in a header.
    """
    entry: ModelEntry | None = catalog.models.get(alias.strip())
    if entry is None:
        raise _alias_error(alias)
    provider: ProviderEntry | None = catalog.providers.get(entry.provider_id)
    if provider is None:
        raise _alias_error(alias)
    model: PalantirModelConfig = palantir_model_config(
        alias=entry.alias,
        provider_id=provider.provider_id,
        protocol=provider.protocol,
        enrollment_base_url=_required_enrollment_url(enrollment_base_url),
        provider_path=provider.path,
        provider_model_id=entry.model_id,
        token=token,
    )
    return LlmConfig(
        engine_id=PALANTIR_ENGINE_ID,
        provider_model_id=model.provider_model_id,
        api_key=model.token,
        base_url=model.base_url,
        max_retries=max_retries,
        alias=model.alias,
        provider_id=model.provider_id,
        protocol=model.protocol,
    )


def probe_palantir_model(config: LlmConfig) -> None:
    """Send exactly one minimal completion to prove *config* can really run.

    Args:
        config: Configuration already resolved from a catalog alias.

    Raises:
        LlmError: The single attempt failed; the caller keeps only a safe error
            class, never the response body.
    """
    service: LlmService = LlmService(replace(config, max_retries=0, max_output_tokens=_PROBE_MAX_OUTPUT_TOKENS))
    try:
        service.complete(
            LlmRequest(messages=(LlmMessage(role=LlmRole.USER, parts=(TextPart(_PROBE_PROMPT),)),)),
        )
    finally:
        service.close()


def _alias_error(alias: str) -> ConfigError:
    """Build the failure of an alias no usable catalog entry serves."""
    return ConfigError(
        context=ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=f"Model alias is not served by the local catalog: {alias}",
            suggestion="Select one of the aliases the model catalog defines with a usable provider",
        ),
    )


def _required_enrollment_url(enrollment_base_url: str) -> str:
    """Return the configured enrollment address or fail before any request.

    Raises:
        ConfigError: The address is unset or is not a plain https address. The
            value itself never reaches the failure, so no company hostname can
            leak into a message or a log.
    """
    candidate: str = enrollment_base_url.strip()
    if candidate and _ENROLLMENT_URL_RE.fullmatch(candidate) is not None:
        return candidate
    code: ErrorCode = ErrorCode.CONFIG_MISSING if not candidate else ErrorCode.CONFIG_INVALID
    raise ConfigError(
        context=ErrorContext(
            code=code,
            message=f"Palantir enrollment address is not usable: {_ENROLLMENT_SETTING_ID}",
            suggestion="Set the enrollment address to the https origin of your enrollment in /connect",
        ),
    )


def _llm_config(settings: Settings, plan: ExecutionPlan) -> LlmConfig:
    snapshot = plan.settings
    if snapshot.llm_profile_id == PALANTIR_ENGINE_ID:
        return _palantir_translation_config(settings, snapshot)
    keys: dict[str, str] = {
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "deepseek": settings.deepseek_api_key,
        "openrouter": settings.openrouter_api_key,
        "openai_compatible": settings.openai_compatible_api_key,
    }
    # Only the OpenAI-compatible provider is addressed by that base URL; every
    # other engine, Palantir included, resolves its own endpoint.
    compatible: bool = snapshot.llm_profile_id == "openai_compatible"
    return LlmConfig(
        engine_id=snapshot.llm_profile_id,
        provider_model_id=snapshot.llm_model_id,
        api_key=keys.get(snapshot.llm_profile_id, ""),
        base_url=(settings.openai_compatible_base_url or None) if compatible else None,
        temperature=snapshot.llm_temperature,
        top_p=snapshot.llm_top_p,
        max_output_tokens=snapshot.llm_max_output_tokens,
        max_retries=snapshot.translation_max_retries,
    )


def _palantir_translation_config(settings: Settings, snapshot: RunSettingsSnapshot) -> LlmConfig:
    """Resolve the translation alias, reading the enrollment address it needs.

    The address is a panel preference rather than a run-snapshot value, so it is
    read here, once per constructed engine and always before any request.
    """
    preferences: UserSettings = load_user_settings()
    config: LlmConfig = palantir_llm_config(
        load_model_catalog(),
        snapshot.llm_model_id,
        enrollment_base_url=preferences.palantir_enrollment_base_url,
        token=settings.palantir_token,
        max_retries=snapshot.translation_max_retries,
    )
    return replace(
        config,
        temperature=snapshot.llm_temperature,
        top_p=snapshot.llm_top_p,
        max_output_tokens=snapshot.llm_max_output_tokens,
    )


def _tts_config(settings: Settings, plan: ExecutionPlan) -> TtsConfig:
    snapshot = plan.settings
    concurrency: int = snapshot.tts_request_concurrency
    return TtsConfig(
        engine_id=snapshot.tts_profile_id,
        provider_model_id=snapshot.tts_model_id,
        voice_id=snapshot.tts_voice_id,
        max_concurrency=concurrency,
        queue_capacity=max(2, 2 * concurrency),
        max_retries=snapshot.tts_max_retries,
        retry_backoff_seconds=_TTS_RETRY_BACKOFF_S.get(
            snapshot.tts_profile_id,
            DEFAULT_RETRY_BACKOFF_SECONDS,
        ),
        request_timeout_s=_TTS_REQUEST_TIMEOUT_S.get(snapshot.tts_profile_id, _AUDIO_TIMEOUT_S),
        scheduler_timeout_enabled=not (snapshot.tts_profile_id == "elevenbytes" and snapshot.tts_vpn_enabled),
        native_rate=snapshot.tts_native_rate,
        native_volume=snapshot.tts_native_volume,
        native_pitch=snapshot.tts_native_pitch,
        engine_options=dict(snapshot.tts_engine_options),
        elevenbytes_vpn_enabled=snapshot.tts_vpn_enabled,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        metadata_cache_root=config_path().parent,
    )


def _audio_config(plan: ExecutionPlan) -> AudioConfig:
    snapshot = plan.settings
    return AudioConfig(
        codec_profile=AudioCodecProfile(snapshot.audio_output_profile),
        bitrate=snapshot.audio_bitrate,
        narrator_mix_base_gain_db=snapshot.narrator_mix_base_gain_db,
        voice_mix_offset_db=snapshot.voice_mix_offset_db,
        original_gain_db=snapshot.original_gain_db,
        timeline_policy=TimelinePolicy(snapshot.tts_timeline_policy),
    )


def _mirror_translation_cancel(
    source: TranslationCancellation,
    destination: threading.Event,
    stop: threading.Event,
) -> None:
    while not stop.wait(0.05):
        if source.is_set():
            destination.set()
            return


def _raise_translation_error(error: LlmError) -> None:
    context = error.context
    if isinstance(error, LlmCancelledError):
        raise TranslationError(context=context) from error
    if isinstance(error, LlmContextLengthError):
        raise TranslationContextLengthError(context=context) from error
    if isinstance(error, LlmAuthError):
        raise TranslationAuthError(context=context) from error
    if isinstance(error, LlmRateLimitError):
        raise TranslationRateLimitError(context=context) from error
    if isinstance(error, (LlmQuotaError, LlmPaymentError)):
        raise TranslationQuotaError(context=context) from error
    if isinstance(
        error,
        (
            LlmTimeoutError,
            LlmProviderUnavailableError,
            LlmConfigError,
            LlmModelError,
            LlmOutputBlockedError,
            LlmRequestError,
        ),
    ):
        raise TranslationEngineError(context=context) from error
    raise TranslationEngineError(context=context) from error
