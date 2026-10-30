from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import ClassVar

import pytest
from elevenreader_fakes import FakePage, FakeSite
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from anishift.errors import ErrorCode, FatalError, TransientError
from anishift.services.tts import (
    TtsAuthError,
    TtsError,
    TtsProviderUnavailableError,
    TtsQuotaError,
    TtsRateLimitError,
    TtsTimeoutError,
)
from anishift.services.tts.engines.elevenreader import SignInOutcome, api_backend, read_session, sign_in
from anishift.services.tts.engines.elevenreader import browser as browser_module
from anishift.services.tts.engines.elevenreader.api_backend import map_http_status, map_playwright_error, write_session
from anishift.services.tts.engines.elevenreader.browser import ChromeBusyError, ChromeMissingError
from anishift.services.tts.engines.elevenreader.types import LibraryState

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (401, TtsAuthError, ErrorCode.TTS_AUTH_FAILED),
        (403, TtsAuthError, ErrorCode.TTS_AUTH_FAILED),
        (402, TtsQuotaError, ErrorCode.TTS_QUOTA_EXHAUSTED),
        (429, TtsRateLimitError, ErrorCode.TTS_RATE_LIMITED),
        (500, TtsProviderUnavailableError, ErrorCode.TTS_ENGINE_UNAVAILABLE),
        (503, TtsProviderUnavailableError, ErrorCode.TTS_ENGINE_UNAVAILABLE),
    ],
)
def test_map_http_status_known_status_returns_typed_error(
    status: int,
    error_type: type[TtsError],
    code: ErrorCode,
) -> None:
    error: TtsError = map_http_status(status, action="upload")

    assert type(error) is error_type
    assert error.context.code is code
    assert error.context.details == {"action": "upload", "status": status}


@pytest.mark.parametrize("status", [401, 402, 403])
def test_map_http_status_permanent_failure_suggests_elevenbytes(status: int) -> None:
    error: TtsError = map_http_status(status, action="read_account")

    assert isinstance(error, FatalError)
    assert error.context.suggestion.endswith("Albo przełącz silnik na ElevenBytes w Ustawienia → Lektor.")


def test_map_http_status_forbidden_mentions_blocked_account() -> None:
    assert "zablokowane" in map_http_status(403, action="upload").context.suggestion


@pytest.mark.parametrize(
    ("header", "expected"), [("42", 42.0), ("1.5", 1.5), ("soon", None), ("-3", None), (None, None)]
)
def test_map_http_status_rate_limit_reads_retry_after(header: str | None, expected: float | None) -> None:
    error: TtsError = map_http_status(429, action="upload", retry_after=header)

    assert isinstance(error, TtsRateLimitError)
    assert error.retry_after_s == expected


def test_map_http_status_server_error_is_transient_with_retry_delay() -> None:
    error: TtsError = map_http_status(502, action="delete_read")

    assert isinstance(error, TransientError)
    assert isinstance(error, TtsProviderUnavailableError)
    assert error.retry_after_s == 60.0


def test_map_playwright_error_timeout_returns_tts_timeout() -> None:
    error: TtsError = map_playwright_error(PlaywrightTimeoutError("Timeout 1000ms exceeded"), action="open_document")

    assert isinstance(error, TtsTimeoutError)
    assert error.context.details == {"action": "open_document"}


def test_map_playwright_error_browser_failure_returns_unavailable_without_original_text() -> None:
    error: TtsError = map_playwright_error(PlaywrightError("Target closed wss://secret"), action="upload")

    assert isinstance(error, TtsProviderUnavailableError)
    assert "secret" not in str(error)
    assert error.retry_after_s == 60.0


class _ReadyLaterPage(FakePage):
    async def library_ready(self) -> bool:
        return True


class _SignInSession:
    instances: ClassVar[list[_SignInSession]] = []
    failure: ClassVar[TtsError | None] = None
    site: ClassVar[FakeSite] = FakeSite()
    page_type: ClassVar[type[FakePage]] = FakePage

    def __init__(self, root: Path, *, headless: bool) -> None:
        self.root: Path = root
        self.headless: bool = headless
        self.closed: bool = False
        _SignInSession.instances.append(self)

    async def start(self) -> None:
        if _SignInSession.failure is not None:
            raise _SignInSession.failure

    async def new_page(self) -> FakePage:
        return _SignInSession.page_type(_SignInSession.site)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_chrome(monkeypatch: pytest.MonkeyPatch) -> type[_SignInSession]:
    monkeypatch.setattr(browser_module, "ChromeSession", _SignInSession)
    monkeypatch.setattr(api_backend, "_SIGN_IN_POLL_S", 0.001)
    monkeypatch.setattr(_SignInSession, "instances", [])
    monkeypatch.setattr(_SignInSession, "failure", None)
    monkeypatch.setattr(_SignInSession, "site", FakeSite())
    monkeypatch.setattr(_SignInSession, "page_type", FakePage)
    return _SignInSession


def test_sign_in_ready_library_returns_signed_in_and_records_session(
    tmp_path: Path,
    fake_chrome: type[_SignInSession],
) -> None:
    outcome: SignInOutcome = asyncio.run(sign_in(tmp_path))

    assert outcome is SignInOutcome.SIGNED_IN
    record = read_session(tmp_path)
    assert record is not None
    assert record.signed_in
    assert not fake_chrome.instances[0].headless
    assert fake_chrome.instances[0].closed


def test_sign_in_library_appearing_later_returns_signed_in(tmp_path: Path, fake_chrome: type[_SignInSession]) -> None:
    fake_chrome.site = FakeSite(library=LibraryState.SIGNED_OUT)
    fake_chrome.page_type = _ReadyLaterPage

    assert asyncio.run(sign_in(tmp_path, timeout_s=5.0)) is SignInOutcome.SIGNED_IN


def test_sign_in_without_sign_in_before_deadline_returns_signed_out(
    tmp_path: Path,
    fake_chrome: type[_SignInSession],
) -> None:
    fake_chrome.site = FakeSite(library=LibraryState.SIGNED_OUT)

    outcome: SignInOutcome = asyncio.run(sign_in(tmp_path, timeout_s=0.02))

    assert outcome is SignInOutcome.SIGNED_OUT
    record = read_session(tmp_path)
    assert record is not None
    assert not record.signed_in
    assert fake_chrome.instances[0].closed


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ChromeBusyError("busy"), SignInOutcome.BUSY),
        (ChromeMissingError("missing"), SignInOutcome.NO_CHROME),
        (TtsProviderUnavailableError("down"), SignInOutcome.FAILED),
    ],
)
def test_sign_in_browser_failure_returns_matching_outcome(
    tmp_path: Path,
    fake_chrome: type[_SignInSession],
    failure: TtsError,
    expected: SignInOutcome,
) -> None:
    fake_chrome.failure = failure

    assert asyncio.run(sign_in(tmp_path)) is expected
    assert read_session(tmp_path) is None


def test_session_record_round_trips_without_secrets(tmp_path: Path) -> None:
    write_session(tmp_path, signed_in=True)

    saved: dict[str, object] = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))

    assert set(saved) == {"checked_at", "signed_in"}
    assert saved["signed_in"] is True


def test_read_session_corrupt_file_returns_none(tmp_path: Path) -> None:
    (tmp_path / "session.json").write_text("{broken", encoding="utf-8")

    assert read_session(tmp_path) is None
