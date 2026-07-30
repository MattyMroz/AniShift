from __future__ import annotations

from dataclasses import replace
from typing import cast
from unicodedata import normalize

import pytest

from anishift.services.tts import AudioFormat, TtsConfigError, TtsInputError
from anishift.services.tts.fingerprint import (
    SynthesisIdentity,
    SynthesisProfile,
    artifact_key,
    chunk_fingerprints,
    synthesis_fingerprint,
    text_hash,
)


def _profile() -> SynthesisProfile:
    return SynthesisProfile(
        engine_id="edge",
        endpoint_id="edge-consumer-v1",
        provider_model_id="edge-default",
        resolved_voice_id="pl-PL-ZofiaNeural",
        provider_output_id="audio-24khz-48kbitrate-mono-mp3",
        provider_source_format=AudioFormat.MP3,
        adapter_version="edge:v1",
        native_rate="+40%",
        native_volume="+0%",
        native_pitch="+0Hz",
        voice_settings={"style": "neutral", "stability": 0.5},
    )


def _identity(
    *,
    text: str = "Gotowy polski tekst.",
    chunks: tuple[str, ...] | None = None,
    profile: SynthesisProfile | None = None,
    request_id: str = "spoken-17",
) -> SynthesisIdentity:
    return SynthesisIdentity(
        scope_id="scope-test",
        request_id=request_id,
        text=text,
        chunks=chunks or (text,),
        profile=profile or _profile(),
    )


def test_fingerprint_is_stable_and_mapping_order_independent() -> None:
    first = _identity()
    reordered = _identity(
        profile=replace(
            _profile(),
            voice_settings={"stability": 0.5, "style": "neutral"},
        ),
    )

    assert synthesis_fingerprint(first) == synthesis_fingerprint(reordered)
    assert text_hash(first.text) == text_hash(reordered.text)


def test_exact_unicode_and_chunk_boundaries_change_fingerprint() -> None:
    composed = "ż"
    decomposed = normalize("NFD", composed)
    first = _identity(text="abc", chunks=("ab", "c"))
    second = _identity(text="abc", chunks=("a", "bc"))

    assert synthesis_fingerprint(first) != synthesis_fingerprint(second)
    assert text_hash(composed) != text_hash(decomposed)
    assert chunk_fingerprints(first) != chunk_fingerprints(second)


def test_every_resolved_audio_value_invalidates_fingerprint() -> None:
    baseline = _identity()
    changed_profiles = (
        replace(baseline.profile, engine_id="sapi"),
        replace(baseline.profile, endpoint_id="edge-consumer-v2"),
        replace(baseline.profile, provider_model_id="other"),
        replace(baseline.profile, resolved_voice_id="pl-PL-MarekNeural"),
        replace(baseline.profile, provider_output_id="other-output"),
        replace(baseline.profile, provider_source_format=AudioFormat.WAV),
        replace(baseline.profile, adapter_version="edge:v2"),
        replace(baseline.profile, contract_version=2),
        replace(baseline.profile, native_rate="+20%"),
        replace(baseline.profile, native_volume="-2%"),
        replace(baseline.profile, native_pitch="+2Hz"),
        replace(baseline.profile, voice_settings={"style": "cheerful"}),
    )

    assert all(
        synthesis_fingerprint(replace(baseline, profile=profile)) != synthesis_fingerprint(baseline)
        for profile in changed_profiles
    )
    assert synthesis_fingerprint(replace(baseline, request_id="spoken-18")) != synthesis_fingerprint(
        baseline,
    )
    assert synthesis_fingerprint(replace(baseline, scope_id="scope-other")) != synthesis_fingerprint(
        baseline,
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_fingerprint_values_are_rejected(value: float) -> None:
    with pytest.raises(TtsConfigError):
        replace(_profile(), voice_settings={"stability": value})


def test_identity_rejects_chunks_that_do_not_reproduce_text() -> None:
    with pytest.raises(TtsInputError):
        _identity(text="abc", chunks=("a", "c"))


def test_fingerprint_rejects_secret_bearing_endpoint_and_non_scalar_option() -> None:
    with pytest.raises(TtsConfigError):
        replace(_profile(), endpoint_id="https://provider.test?token=secret")
    with pytest.raises(TtsConfigError):
        replace(_profile(), voice_settings={"api_key": "secret"})
    for credential_key in ("access_key", "subscription_key", "bearer", "headers"):
        with pytest.raises(TtsConfigError):
            replace(_profile(), voice_settings={credential_key: "secret"})
    with pytest.raises(TtsConfigError):
        replace(
            _profile(),
            voice_settings=cast("dict[str, str]", []),
        )
    with pytest.raises(TtsConfigError):
        replace(
            _profile(),
            voice_settings={"nested": cast("str", {"secret": "value"})},
        )


def test_artifact_key_hides_and_bounds_opaque_request_id() -> None:
    request_id = "../CON:非常に長い/" * 100
    key = artifact_key(request_id, synthesis_fingerprint(_identity()))

    assert len(key) == 64
    assert key.isascii()
    assert key.isalnum()
    assert request_id not in key
