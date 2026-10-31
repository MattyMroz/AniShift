from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from elevenreader_fakes import ADAM_ID, FRONCZEWSKI_ID, tts_config

from anishift.errors import ErrorCode
from anishift.services.tts import TtsConfigError, TtsVoiceError
from anishift.services.tts.engines.elevenreader import (
    DEFAULT_VOICE_ALIAS,
    MAX_PARALLEL_DOCUMENTS,
    VOICES,
    ElevenReaderConfig,
    resolve_voice,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [("fronczewski", FRONCZEWSKI_ID), ("ADAM", ADAM_ID), (f" {ADAM_ID} ", ADAM_ID), (FRONCZEWSKI_ID, FRONCZEWSKI_ID)],
)
def test_resolve_voice_alias_or_id_returns_offered_voice(value: str, expected: str) -> None:
    assert resolve_voice(value).voice_id == expected


def test_resolve_voice_unknown_raises_voice_error() -> None:
    with pytest.raises(TtsVoiceError) as error:
        resolve_voice("dallin")

    assert error.value.context.code is ErrorCode.TTS_VOICE_INVALID


def test_voices_offer_two_voices_with_fronczewski_default() -> None:
    assert tuple(VOICES) == ("fronczewski", "adam")
    assert DEFAULT_VOICE_ALIAS == "fronczewski"
    assert VOICES["fronczewski"].label == "Piotr Fronczewski"


@pytest.mark.parametrize("documents", [1, MAX_PARALLEL_DOCUMENTS])
def test_from_tts_config_parallel_documents_within_limit_are_accepted(tmp_path: Path, documents: int) -> None:
    config = replace(tts_config(tmp_path), max_concurrency=documents)

    assert ElevenReaderConfig.from_tts_config(config).profile_root == tmp_path


def test_from_tts_config_resolves_voice_and_profile(tmp_path: Path) -> None:
    config: ElevenReaderConfig = ElevenReaderConfig.from_tts_config(tts_config(tmp_path, voice_id="adam"))

    assert config.voice.voice_id == ADAM_ID
    assert config.profile_root == tmp_path


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("provider_model_id", "eleven_v2"),
        ("max_concurrency", MAX_PARALLEL_DOCUMENTS + 1),
        ("engine_options", {"stability": 0.5}),
        ("elevenreader_profile_root", None),
    ],
)
def test_from_tts_config_unsupported_setting_raises_config_error(tmp_path: Path, field_name: str, value: Any) -> None:
    config = replace(tts_config(tmp_path), **{field_name: value})

    with pytest.raises(TtsConfigError) as error:
        ElevenReaderConfig.from_tts_config(config)

    assert error.value.context.details == {"field": field_name}
