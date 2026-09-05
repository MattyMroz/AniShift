from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from anishift.services.tts import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    CancellationToken,
    EngineAvailability,
    EngineCapabilities,
    EngineClipResult,
    EngineLocality,
    SpeechBatch,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechRequest,
    SynthesisProfile,
    SynthesisRequest,
    TtsEngine,
    VoiceInfo,
)

FORBIDDEN_IMPORT_PREFIXES = (
    "pysubs2",
    "anishift.services.audio",
    "anishift.services.subtitles",
    "anishift.services.translation",
)


class FakeEngine:
    engine_id = "edge"
    is_available = True
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3,),
        supports_concurrency=True,
        supports_native_rate=True,
        supports_native_volume=True,
        supports_pitch=True,
        supports_voice_settings=False,
        requires_api_key=False,
        min_text_chars=1,
        max_text_chars=None,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.REMOTE,
    )
    synthesis_profile = SynthesisProfile(
        engine_id="edge",
        endpoint_id="edge-consumer-v1",
        provider_model_id="edge-default",
        resolved_voice_id="pl-PL-ZofiaNeural",
        provider_output_id="audio-24khz-mp3",
        provider_source_format=AudioFormat.MP3,
        adapter_version="edge:v1",
    )

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        source = AvailabilitySource.LIVE if live else AvailabilitySource.CACHED
        return EngineAvailability(
            status=AvailabilityStatus.READY,
            message="ready",
            checked_at=datetime.now(UTC),
            source=source,
        )

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        return ()

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        raise NotImplementedError

    async def close(self) -> None:
        return None


def test_neutral_request_and_batch_have_exact_fields() -> None:
    assert tuple(item.name for item in fields(SpeechRequest)) == (
        "request_id",
        "text",
        "request_rank",
    )
    assert tuple(item.name for item in fields(SpeechBatch)) == (
        "scope_id",
        "batch_rank",
        "requests",
    )
    assert tuple(item.name for item in fields(SpeechBatchResult)) == (
        "scope_id",
        "status",
        "requests",
        "stats",
        "failure",
    )


def test_neutral_contract_preserves_polish_text_and_opaque_ids() -> None:
    request = SpeechRequest(
        request_id="opaque:req:01",
        text="Zażółć gęślą jaźń",
        request_rank=0,
    )
    batch = SpeechBatch(
        scope_id="opaque:scope",
        batch_rank=3,
        requests=(request,),
    )

    assert batch.requests[0] is request
    assert batch.requests[0].text == "Zażółć gęślą jaźń"
    assert batch.scope_id == "opaque:scope"


def test_neutral_contract_is_frozen_and_slotted() -> None:
    request = SpeechRequest(request_id="request", text="Tekst", request_rank=0)
    batch = SpeechBatch(scope_id="scope", batch_rank=0, requests=(request,))

    assert not hasattr(request, "__dict__")
    assert not hasattr(batch, "__dict__")
    attribute_name = "text"
    with pytest.raises(FrozenInstanceError):
        setattr(request, attribute_name, "Zmieniony")


def test_batch_result_cannot_contain_timing_or_audio_pipeline_state() -> None:
    stats = SpeechBatchStats(
        total_requests=0,
        synthesized=0,
        resume_hits=0,
        skipped=0,
        failed=0,
        provider_calls=0,
        retries=0,
        synthesis_time_ms=0.0,
        engine_id="edge",
        provider_model_id="edge-default",
        voice_id="pl-PL-MarekNeural",
    )
    result = SpeechBatchResult(
        scope_id="opaque:scope",
        status=SpeechBatchStatus.COMPLETED,
        requests=(),
        stats=stats,
        failure=None,
    )
    forbidden_fields = (
        "audio_source",
        "end_ms",
        "mixed_audio_path",
        "narrator_path",
        "source_path",
        "start_ms",
        "subtitle_path",
        "timeline",
    )

    assert not hasattr(result, "__dict__")
    for field_name in forbidden_fields:
        assert not hasattr(result, field_name)


def test_engine_result_does_not_claim_scheduler_or_resume_state() -> None:
    engine_result_fields = tuple(item.name for item in fields(EngineClipResult))

    assert "attempts" not in engine_result_fields
    assert "from_resume" not in engine_result_fields


def test_engine_protocol_extends_shared_identity_contract() -> None:
    engine: TtsEngine = FakeEngine()

    assert isinstance(engine, TtsEngine)
    assert engine.engine_id == "edge"
    assert engine.is_available


def test_tts_domain_does_not_import_pipeline_or_other_domains() -> None:
    package_root = Path(__file__).parents[3] / "anishift" / "services" / "tts"
    violations: list[str] = []

    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module_names: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                module_names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                module_names = (node.module,)
            violations.extend(
                f"{path.relative_to(package_root)}: {module_name}"
                for module_name in module_names
                if module_name.startswith(FORBIDDEN_IMPORT_PREFIXES)
            )

    assert violations == []
