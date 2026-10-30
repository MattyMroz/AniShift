from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from anishift.services.tts import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    CancellationToken,
    ClipSpan,
    DocumentPart,
    DocumentSynthesisRequest,
    EngineAvailability,
    EngineCapabilities,
    EngineClipResult,
    EngineDocumentResult,
    EngineLocality,
    PartTiming,
    SpeechBatch,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechRequest,
    SplitResult,
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


def test_document_contract_types_have_exact_fields() -> None:
    assert tuple(item.name for item in fields(DocumentPart)) == ("request_id", "text")
    assert tuple(item.name for item in fields(DocumentSynthesisRequest)) == (
        "request_id",
        "parts",
        "voice_id",
        "provider_model_id",
        "options",
        "recording",
        "deadline_s",
        "progress",
    )
    assert tuple(item.name for item in fields(PartTiming)) == ("request_id", "start_ms", "end_ms")
    assert tuple(item.name for item in fields(EngineDocumentResult)) == (
        "request_id",
        "recording",
        "format",
        "engine_id",
        "provider_model_id",
        "voice_id",
        "request_time_ms",
        "parts",
    )
    assert tuple(item.name for item in fields(ClipSpan)) == (
        "request_id",
        "start_ms",
        "end_ms",
        "open_end",
        "destination",
    )
    assert tuple(item.name for item in fields(SplitResult)) == ("written", "uncertain_boundaries")


def test_document_contract_types_are_frozen_and_slotted(tmp_path: Path) -> None:
    values: tuple[object, ...] = (
        DocumentPart(request_id="line-1", text="Tekst."),
        DocumentSynthesisRequest(
            request_id="scope:document:0",
            parts=(DocumentPart(request_id="line-1", text="Tekst."),),
            voice_id="voice",
            provider_model_id="model",
            options={},
            recording=tmp_path / "recording.mp3",
            deadline_s=1.0,
        ),
        PartTiming(request_id="line-1", start_ms=0.0, end_ms=1.0),
        ClipSpan(request_id="line-1", start_ms=0.0, end_ms=1.0, open_end=False, destination=tmp_path / "a.wav"),
        SplitResult(written=("line-1",), uncertain_boundaries=0),
    )
    attribute_name = "request_id"

    for value in values:
        assert not hasattr(value, "__dict__")
        if hasattr(value, attribute_name):
            with pytest.raises(FrozenInstanceError):
                setattr(value, attribute_name, "changed")


def test_document_request_progress_is_ignored_by_equality(tmp_path: Path) -> None:
    async def observe(received: int, total: int) -> None:
        del received, total

    plain = DocumentSynthesisRequest(
        request_id="scope:document:0",
        parts=(DocumentPart(request_id="line-1", text="Tekst."),),
        voice_id="voice",
        provider_model_id="model",
        options={},
        recording=tmp_path / "recording.mp3",
        deadline_s=1.0,
    )

    assert plain == replace(plain, progress=observe)


def test_document_request_without_parts_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one part"):
        DocumentSynthesisRequest(
            request_id="scope:document:0",
            parts=(),
            voice_id="voice",
            provider_model_id="model",
            options={},
            recording=tmp_path / "recording.mp3",
            deadline_s=1.0,
        )


@pytest.mark.parametrize("end_ms", [10.0, 5.0])
def test_part_timing_without_positive_length_is_rejected(end_ms: float) -> None:
    with pytest.raises(ValueError, match="end after it starts"):
        PartTiming(request_id="line-1", start_ms=10.0, end_ms=end_ms)


def test_engine_capabilities_default_to_line_engine() -> None:
    assert FakeEngine.capabilities.max_document_chars is None
