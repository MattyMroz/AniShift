"""Unit tests for sensitive data scrubber."""

from __future__ import annotations

import pytest

from ..scrubber import scrub_message


class TestScrubMessage:
    """Tests for scrub_message pattern matching."""

    # ── API Keys ──────────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("api_key=sk-1234567890abcdef", id="api_key_eq"),
            pytest.param("api-key: sk-1234567890abcdef", id="api-key_colon"),
            pytest.param("apikey=secret123", id="apikey_eq"),
            pytest.param("secret_key=mykey", id="secret_key"),
            pytest.param("access_key=awskey", id="access_key"),
            pytest.param("access-key: val", id="access-key_colon"),
        ],
    )
    def test_api_key_patterns_masked(self, raw: str) -> None:
        result = scrub_message(raw)
        assert "***" in result
        # Original value should be gone
        for secret in ("sk-1234567890abcdef", "secret123", "mykey", "awskey", "val"):
            if secret in raw:
                assert secret not in result

    # ── Bearer Tokens ─────────────────────────────────────────────────────────

    def test_bearer_token_masked(self) -> None:
        result = scrub_message("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload")
        assert "Bearer ***" in result
        assert "eyJhbGciOiJIUzI1NiJ9" not in result

    def test_bearer_case_insensitive(self) -> None:
        result = scrub_message("bearer MyToken123")
        assert "***" in result
        assert "MyToken123" not in result

    # ── OpenAI Keys ───────────────────────────────────────────────────────────

    def test_openai_key_masked(self) -> None:
        key = "sk-" + "a" * 48
        result = scrub_message(f"Using key {key}")
        assert "sk-***" in result
        assert key not in result

    def test_short_sk_not_masked(self) -> None:
        result = scrub_message("sk-short")
        # Too short for OpenAI pattern — should NOT be masked
        assert "sk-short" in result

    # ── Google API Keys ───────────────────────────────────────────────────────

    def test_google_api_key_masked(self) -> None:
        key = "AIza" + "B" * 35
        result = scrub_message(f"key={key}")
        assert "AIza***" in result
        assert key not in result

    # ── Password Fields ───────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("password=secret123", id="password"),
            pytest.param("passwd: s3cret!", id="passwd"),
            pytest.param("pwd=hunter2", id="pwd"),
        ],
    )
    def test_password_masked(self, raw: str) -> None:
        result = scrub_message(raw)
        assert "***" in result

    # ── Token / Auth Fields ───────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("token=abc123def", id="token"),
            pytest.param("auth: myauth", id="auth"),
        ],
    )
    def test_token_auth_masked(self, raw: str) -> None:
        result = scrub_message(raw)
        assert "***" in result

    # ── 32-char Hex (ElevenLabs-style) ────────────────────────────────────────

    def test_hex_key_masked(self) -> None:
        key = "a1b2c3d4e5f67890a1b2c3d4e5f67890"
        result = scrub_message(f"elevenlabs key: {key}")
        assert "***" in result
        assert key not in result

    def test_pure_digit_hex_not_masked(self) -> None:
        # All digits — should NOT match (requires mixed digits+letters)
        key = "1" * 32
        result = scrub_message(f"hash: {key}")
        assert key in result

    def test_pure_letter_hex_not_masked(self) -> None:
        # All letters — should NOT match (requires mixed digits+letters)
        key = "a" * 32
        result = scrub_message(f"hash: {key}")
        assert key in result

    # ── Safe Messages ─────────────────────────────────────────────────────────

    def test_safe_message_unchanged(self) -> None:
        msg = "Processing image manga_001.jpg with 3 panels"
        assert scrub_message(msg) == msg

    def test_empty_string(self) -> None:
        assert scrub_message("") == ""

    # ── Multiple Patterns ─────────────────────────────────────────────────────

    def test_multiple_secrets_in_one_message(self) -> None:
        msg = "api_key=secret123 password=hunter2"
        result = scrub_message(msg)
        assert "secret123" not in result
        assert "hunter2" not in result
        assert result.count("***") >= 2


class TestScrubPatcher:
    """Tests for scrub_patcher loguru integration."""

    def test_patches_record_message(self) -> None:
        from ..scrubber import scrub_patcher

        record: dict = {"message": "token=secret123"}  # type: ignore[type-arg]
        scrub_patcher(record)  # type: ignore[arg-type]
        assert "secret123" not in record["message"]
        assert "***" in record["message"]

    def test_safe_message_unchanged(self) -> None:
        from ..scrubber import scrub_patcher

        record: dict = {"message": "Hello world"}  # type: ignore[type-arg]
        scrub_patcher(record)  # type: ignore[arg-type]
        assert record["message"] == "Hello world"
