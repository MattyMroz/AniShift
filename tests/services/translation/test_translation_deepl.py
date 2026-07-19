import pytest

from anishift.services.translation.engines.deepl._lang_codes import to_deepl_code
from anishift.services.translation.engines.deepl.config import DeeplConfig
from anishift.services.translation.engines.deepl.service import DeeplService
from anishift.services.translation.errors import TranslationAuthError


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeClient:
    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self._raise = raise_exc

    def translate_text(self, texts, *, target_lang, source_lang):  # type: ignore[no-untyped-def]
        if self._raise is not None:
            raise self._raise
        return [_Result(f"PL:{t}") for t in texts]


def test_is_available_reflects_key() -> None:
    assert not DeeplService(DeeplConfig(api_key="")).is_available
    assert DeeplService(DeeplConfig(api_key="key:fx")).is_available


def test_translate_without_key_raises_auth_error() -> None:
    engine = DeeplService(DeeplConfig(api_key=""))
    with pytest.raises(TranslationAuthError):
        engine.translate_batch(["hello"], source_lang="auto", target_lang="pl")


def test_translate_maps_results_in_order() -> None:
    engine = DeeplService(DeeplConfig(api_key="key:fx"))
    engine._client = _FakeClient()
    result = engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")
    assert [line.text for line in result] == ["PL:a", "PL:b"]


def test_to_deepl_code_mapping() -> None:
    assert to_deepl_code("auto") is None
    assert to_deepl_code("en") == "EN-US"
    assert to_deepl_code("pt") == "PT-PT"
    assert to_deepl_code("pl") == "PL"


def test_logical_pl_reaches_deepl_sdk_as_uppercase() -> None:
    captured: dict[str, str] = {}

    class _CapturingClient:
        def translate_text(self, texts, *, target_lang, source_lang):  # type: ignore[no-untyped-def]
            captured["target"] = target_lang
            return [_Result(t) for t in texts]

    engine = DeeplService(DeeplConfig(api_key="key:fx"))
    engine._client = _CapturingClient()
    engine.translate_batch(["hi"], source_lang="auto", target_lang="pl")
    assert captured["target"] == "PL"


def test_empty_batch_returns_empty() -> None:
    engine = DeeplService(DeeplConfig(api_key="key:fx"))
    assert engine.translate_batch([], source_lang="auto", target_lang="pl") == []


def test_batch_size_limits_lines_per_request() -> None:
    seen: list[int] = []

    class _CountingClient:
        def translate_text(self, texts, *, target_lang, source_lang):  # type: ignore[no-untyped-def]
            seen.append(len(texts))
            return [_Result(f"PL:{t}") for t in texts]

    engine = DeeplService(DeeplConfig(api_key="key:fx", batch_size=2))
    engine._client = _CountingClient()
    engine.translate_batch(["a", "b", "c", "d", "e"], source_lang="auto", target_lang="pl")
    assert seen == [2, 2, 1]
