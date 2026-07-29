from __future__ import annotations

import importlib
import subprocess
import sys
from types import ModuleType
from typing import cast, get_args

import pytest

from anishift.errors import ErrorCode
from anishift.services.tts import (
    TtsConfig,
    TtsConfigError,
    TtsEngine,
    TtsEngineId,
    available_engine_ids,
    create_engine,
)

EXPECTED_ENGINE_IDS = ("edge", "elevenbytes", "elevenlabs", "sapi")


class FakeEngine:
    engine_id = "edge"
    is_available = True


def _build_config(*, engine_id: str) -> TtsConfig:
    return TtsConfig(
        engine_id=engine_id,
        provider_model_id="test-model",
        voice_id="test-voice",
        max_concurrency=1,
        queue_capacity=2,
    )


def test_available_engine_ids_returns_exact_stable_order() -> None:
    assert available_engine_ids() == EXPECTED_ENGINE_IDS
    assert get_args(TtsEngineId) == EXPECTED_ENGINE_IDS


def test_unknown_engine_raises_structured_config_error() -> None:
    config = _build_config(engine_id="unknown")

    with pytest.raises(TtsConfigError) as exc_info:
        create_engine(config)

    assert exc_info.value.context.code is ErrorCode.TTS_CONFIG_INVALID
    assert "unknown" in str(exc_info.value)
    assert ", ".join(EXPECTED_ENGINE_IDS) in str(exc_info.value)


def test_create_engine_imports_only_selected_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    imported_modules: list[str] = []
    fake_module = ModuleType("anishift.services.tts.engines.edge")

    def fake_factory(config: TtsConfig) -> TtsEngine:
        assert config.engine_id == "edge"
        return cast("TtsEngine", FakeEngine())

    def fake_import_module(module_path: str) -> ModuleType:
        imported_modules.append(module_path)
        return fake_module

    fake_module.__dict__["EdgeTtsEngine"] = fake_factory
    registry = importlib.import_module("anishift.services.tts.engines")
    monkeypatch.setattr(registry.importlib, "import_module", fake_import_module)

    engine = create_engine(_build_config(engine_id="edge"))

    assert engine.engine_id == "edge"
    assert imported_modules == ["anishift.services.tts.engines.edge"]


def test_domain_import_does_not_load_provider_implementations() -> None:
    forbidden_modules = (
        "edge_tts",
        "elevenlabs",
        "anishift.services.tts.engines.edge",
        "anishift.services.tts.engines.elevenbytes",
        "anishift.services.tts.engines.elevenlabs",
        "anishift.services.tts.engines.sapi",
    )
    module_names = repr(forbidden_modules)
    script = (
        "import sys\n"
        "import anishift.services.tts\n"
        f"forbidden = {module_names}\n"
        "loaded = [name for name in forbidden if name in sys.modules]\n"
        "if loaded:\n"
        "    raise SystemExit(','.join(loaded))\n"
    )

    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
