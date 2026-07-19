from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.service import LlmTranslateService, _parse_numbered


class _FakeCompleter:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append(user)
        return self.response


def test_parse_numbered_clean() -> None:
    assert _parse_numbered("[1] a\n[2] b\n[3] c", 3) == ["a", "b", "c"]


def test_parse_numbered_ignores_noise() -> None:
    text = "Oto tłumaczenie:\n```\n[1] a\n[2] b\n```\nMam nadzieję że pomogłem"
    assert _parse_numbered(text, 2) == ["a", "b"]


def test_parse_numbered_detects_missing_index() -> None:
    assert _parse_numbered("[1] a\n[3] c", 3) is None


def test_parse_numbered_detects_duplicate() -> None:
    assert _parse_numbered("[1] a\n[1] b\n[2] c", 2) is None


def test_translate_batch_happy_path() -> None:
    engine = LlmTranslateService(LlmTranslateConfig(), completer=_FakeCompleter("[1] jeden\n[2] dwa"))
    result = engine.translate_batch(["one", "two"], source_lang="auto", target_lang="pl")
    assert [line.text for line in result] == ["jeden", "dwa"]
    assert all(line.ok for line in result)


def test_translate_batch_shrinks_to_per_line_on_persistent_mismatch() -> None:
    # Completer always returns a single '[1] x' regardless of batch size, so the
    # multi-line parse fails, repair fails, shrink recurses to per-line (which
    # parses because expected == 1).
    engine = LlmTranslateService(
        LlmTranslateConfig(max_repair_attempts=1, min_batch_size=1),
        completer=_FakeCompleter("[1] x"),
    )
    result = engine.translate_batch(["a", "b"], source_lang="auto", target_lang="pl")
    assert [line.text for line in result] == ["x", "x"]
    assert all(line.ok for line in result)


def test_is_available_true_with_completer() -> None:
    engine = LlmTranslateService(LlmTranslateConfig(), completer=_FakeCompleter("[1] a"))
    assert engine.is_available
