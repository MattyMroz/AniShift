from __future__ import annotations

import pytest

from anishift.application.episode_releases import info_hash_hex


@pytest.mark.unit
def test_info_hash_hex_keeps_lowercase_hex() -> None:
    assert info_hash_hex("3753beaf00112233445566778899aabbccddeeff") == "3753beaf00112233445566778899aabbccddeeff"


@pytest.mark.unit
def test_info_hash_hex_lowercases_uppercase_hex() -> None:
    assert info_hash_hex("3753BEAF00112233445566778899AABBCCDDEEFF") == "3753beaf00112233445566778899aabbccddeeff"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["G5J35LYACERDGRCVMZ3YRGNKXPGN33X7", "g5j35lyacerdgrcvmz3yrgnkxpgn33x7"])
def test_info_hash_hex_converts_base32(value: str) -> None:
    assert info_hash_hex(value) == "3753beaf00112233445566778899aabbccddeeff"


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        "",
        "3753beaf00112233445566778899aabbccddeef",
        "3753beaf00112233445566778899aabbccddeeff0",
        "3753beaf00112233445566778899aabbccddeefg",
        " 3753beaf00112233445566778899aabbccddeeff",
        "G5J35LYACERDGRCVMZ3YRGNKXPGN33X1",
        "G5J35LYACERDGRCVMZ3YRGNKXPGN33X",
        "magnet:?xt=urn:btih:3753beaf00112233445566778899aabbccddeeff",
    ],
)
def test_info_hash_hex_rejects_other_text(value: str) -> None:
    assert info_hash_hex(value) is None
