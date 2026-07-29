from __future__ import annotations

from pathlib import Path

import pytest

from anishift.config.env_file import update_env_value
from anishift.config.settings import Settings


def test_update_env_value_preserves_comments_newlines_and_unrelated_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    path.write_bytes(
        b"# keys\r\nANISHIFT_GEMINI_API_KEY=gemini\r\nexport ANISHIFT_ELEVENLABS_API_KEY=old\r\n",
    )

    update_env_value(
        "ANISHIFT_ELEVENLABS_API_KEY",
        'new"value',
        path=path,
    )

    assert path.read_bytes() == (
        b'# keys\r\nANISHIFT_GEMINI_API_KEY=gemini\r\nexport ANISHIFT_ELEVENLABS_API_KEY="new\\"value"\r\n'
    )


def test_update_env_value_appends_with_existing_newline_style(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_bytes(b"ANISHIFT_DEEPL_API_KEY=key")

    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", "secret", path=path)

    assert path.read_bytes() == (b'ANISHIFT_DEEPL_API_KEY=key\nANISHIFT_ELEVENLABS_API_KEY="secret"\n')


def test_update_env_value_distinguishes_clear_and_remove(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "ANISHIFT_ELEVENLABS_API_KEY=secret\nANISHIFT_DEEPL_API_KEY=key\n",
        encoding="utf-8",
    )

    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", "", path=path)
    assert "ANISHIFT_ELEVENLABS_API_KEY=\n" in path.read_text(encoding="utf-8")

    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", None, path=path)
    text = path.read_text(encoding="utf-8")
    assert "ANISHIFT_ELEVENLABS_API_KEY" not in text
    assert "ANISHIFT_DEEPL_API_KEY=key" in text


def test_update_env_value_preserves_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_bytes(b"\xef\xbb\xbf# ustawienia\n")

    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", "sekret", path=path)

    assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_update_env_value_rejects_invalid_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="uppercase"):
        update_env_value("bad-key", "value", path=tmp_path / ".env")


def test_update_env_value_roundtrips_literal_interpolation_syntax(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    literal_value = "abc${NOT_DEFINED}xyz"

    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", literal_value, path=path)

    assert Settings(_env_file=path).elevenlabs_api_key == literal_value


def test_process_environment_overrides_updated_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / ".env"
    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", "file-secret", path=path)
    monkeypatch.setenv("ANISHIFT_ELEVENLABS_API_KEY", "process-secret")

    settings = Settings(_env_file=path)

    assert settings.elevenlabs_api_key == "process-secret"
    assert "process-secret" not in repr(settings)
