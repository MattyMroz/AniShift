from __future__ import annotations

import pytest

from anishift.application.release_quality import language_code


@pytest.mark.unit
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("pl-PL", "pl"),
        ("ja-JP", "ja"),
        ("zh-Hant", "zh"),
        ("zh_TW", "zh"),
        ("PL", "pl"),
        ("pl", "pl"),
        (" en-US ", "en"),
        ("pt-BR", "pt"),
    ],
)
def test_language_code_regional(code: str, expected: str) -> None:
    assert language_code(code) == expected
