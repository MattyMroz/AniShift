from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from anishift.services.tts import TtsConfig
from anishift.services.tts.engines.elevenreader import (
    DocumentPart,
    DocumentResult,
    DocumentSynthesisRequest,
    ElevenReaderTtsEngine,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from anishift.services.tts.engines.elevenreader.browser import ChromeSession
    from anishift.services.tts.engines.elevenreader.types import Redo

__all__ = ["DocumentResult", "make_engine", "make_request"]


def make_engine(root: Path, factory: Callable[[Path], ChromeSession], mode: Redo) -> ElevenReaderTtsEngine:
    config: TtsConfig = TtsConfig(
        engine_id="elevenreader",
        provider_model_id="eleven_v4",
        voice_id="fronczewski",
        max_concurrency=1,
        queue_capacity=2,
        elevenreader_profile_root=root,
    )
    engine: ElevenReaderTtsEngine = ElevenReaderTtsEngine(config, browser_factory=factory)
    engine._config = replace(engine._config, redo=mode)
    return engine


def make_request(texts: tuple[str, ...], recording: Path, deadline_s: float) -> DocumentSynthesisRequest:
    return DocumentSynthesisRequest(
        request_id="document-0",
        parts=tuple(DocumentPart(request_id=f"part-{index}", text=text) for index, text in enumerate(texts)),
        voice_id="fronczewski",
        provider_model_id="eleven_v4",
        options={},
        recording=recording,
        deadline_s=deadline_s,
    )
