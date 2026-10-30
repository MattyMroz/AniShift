"""One-attempt ElevenReader boundary in a browser tab: page actions, account requests, session and error mapping."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.artifacts import atomic_json_snapshot
from anishift.services.tts.errors import (
    TtsAuthError,
    TtsError,
    TtsProviderUnavailableError,
    TtsQuotaError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsVoiceError,
)
from anishift.utils.logger import get_logger

from .config import session_file
from .constants import (
    ACTION_TIMEOUT_S,
    ADD_ENDPOINT,
    API_HOST,
    CLEANUP_STEP_TIMEOUT_S,
    LIBRARY_LOAD_S,
    LIBRARY_URL,
    PLAYER_STATE_JS,
    READING_SPEED,
    READS_URL,
    READY_TIMEOUT_S,
    SIGN_IN_TIMEOUT_S,
    SPEED_JS,
    SPEED_STATE_JS,
    SPEED_TOLERANCE,
    STREAM_PATH,
    UNAVAILABLE_RETRY_S,
    USER_CONFIG_URL,
)
from .types import AccountSettings, LibraryState, PlayerState, SessionRecord, SignInOutcome, UploadedRead

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator
    from pathlib import Path

    from playwright.async_api import APIResponse, Locator, Page, Request, Response, WebSocket
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    from .recorder import StreamRecorder
    from .types import AccountCleanup

__all__ = [
    "FALLBACK_HINT",
    "ReaderPage",
    "auth_error",
    "map_http_status",
    "map_playwright_error",
    "prepare_account",
    "read_session",
    "require_signed_in",
    "run_cleanup",
    "sign_in",
    "speed_script",
    "unavailable_error",
    "voice_error",
    "write_session",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

FALLBACK_HINT: Final[str] = "Albo przełącz silnik na ElevenBytes w Ustawienia → Lektor."
"""Closing sentence of every permanent-failure suggestion."""

SIGN_IN_HINT: Final[str] = f"Zaloguj się w Ustawienia → Lektor → Zaloguj / sprawdź sesję. {FALLBACK_HINT}"
"""Suggestion for a signed-out or rejected session."""

_UNAUTHORIZED: Final[int] = 401
"""HTTP status of a missing or expired session."""

_PAYMENT_REQUIRED: Final[int] = 402
"""HTTP status assumed for exhausted credits until a live check confirms it."""

_FORBIDDEN: Final[int] = 403
"""HTTP status of a blocked account."""

_NOT_FOUND: Final[int] = 404
"""HTTP status of a read that is already gone."""

_TOO_MANY_REQUESTS: Final[int] = 429
"""HTTP status of a rate limit."""

_SERVER_ERROR: Final[int] = 500
"""Lowest HTTP status of a server failure."""

_MS_PER_S: Final[float] = 1000.0
"""Milliseconds in one second, for Playwright timeouts."""

_SIGN_IN_NAME: Final[re.Pattern[str]] = re.compile(r"sign in|log in|continue with google", re.IGNORECASE)
"""Accessible names of the controls shown to a signed-out visitor."""

_SIGN_IN_URL: Final[re.Pattern[str]] = re.compile(r"sign-?in|log-?in|auth", re.IGNORECASE)
"""Address fragments of the sign-in pages a signed-out visitor is sent to."""

_SIGN_IN_POLL_S: Final[float] = 1.0
"""Interval between checks of the sign-in window."""


# ── Error mapping ─────────────────────────────────────────────────────────────


def map_http_status(status: int, *, action: str, retry_after: str | None = None) -> TtsError:
    """Return the typed error for a failed ElevenReader API reply."""
    details: dict[str, object] = {"action": action, "status": status}
    if status == _UNAUTHORIZED:
        return auth_error("ElevenReader rejected the session", details=details)
    if status == _FORBIDDEN:
        context: ErrorContext = ErrorContext(
            code=ErrorCode.TTS_AUTH_FAILED,
            message="ElevenReader refused access to the account",
            suggestion=f"Konto ElevenReader mogło zostać zablokowane. {FALLBACK_HINT}",
            details=details,
        )
        return TtsAuthError(context=context)
    if status == _PAYMENT_REQUIRED:
        quota: ErrorContext = ErrorContext(
            code=ErrorCode.TTS_QUOTA_EXHAUSTED,
            message="ElevenReader account has no credits left",
            suggestion=f"Poczekaj na odnowienie kredytów ElevenReader. {FALLBACK_HINT}",
            details=details,
        )
        return TtsQuotaError(context=quota)
    if status == _TOO_MANY_REQUESTS:
        limited: ErrorContext = ErrorContext(
            code=ErrorCode.TTS_RATE_LIMITED,
            message="ElevenReader rate limit reached",
            details=details,
        )
        return TtsRateLimitError(retry_after_s=_retry_after_s(retry_after), context=limited)
    return unavailable_error(f"ElevenReader API failed during {action}", details=details)


def map_playwright_error(error: PlaywrightError, *, action: str) -> TtsError:
    """Return a retryable error for a browser failure; a Playwright timeout becomes a TTS timeout."""
    details: dict[str, object] = {"action": action}
    if isinstance(error, _playwright_timeout()):
        context: ErrorContext = ErrorContext(
            code=ErrorCode.TTS_TIMEOUT,
            message=f"ElevenReader page timed out during {action}",
            details=details,
        )
        return TtsTimeoutError(context=context)
    return unavailable_error(f"ElevenReader browser failed during {action}", details=details)


def auth_error(message: str, *, details: dict[str, object] | None = None) -> TtsAuthError:
    """Return the permanent error asking the owner to sign in again."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_AUTH_FAILED,
        message=message,
        suggestion=SIGN_IN_HINT,
        details=details or {},
    )
    return TtsAuthError(context=context)


def voice_error(message: str) -> TtsVoiceError:
    """Return the permanent error for a voice the account or stream did not take."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_VOICE_INVALID,
        message=message,
        suggestion=f"Wybierz głos Piotr Fronczewski albo Adam w Ustawienia → Lektor. {FALLBACK_HINT}",
    )
    return TtsVoiceError(context=context)


def unavailable_error(message: str, *, details: dict[str, object] | None = None) -> TtsProviderUnavailableError:
    """Return the retryable error for an unavailable site, stream or browser."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_ENGINE_UNAVAILABLE,
        message=message,
        details=details or {},
    )
    return TtsProviderUnavailableError(retry_after_s=UNAVAILABLE_RETRY_S, context=context)


def _retry_after_s(header: str | None) -> float | None:
    if header is None:
        return None
    try:
        seconds: float = float(header)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _playwright_error() -> type[PlaywrightError]:
    from playwright.async_api import Error  # noqa: PLC0415 - Playwright loads only once a browser tab exists

    return Error


def _playwright_timeout() -> type[PlaywrightTimeoutError]:
    from playwright.async_api import TimeoutError as PlaywrightTimeout  # noqa: PLC0415 - as above

    return PlaywrightTimeout


@contextmanager
def _browser_action(action: str) -> Iterator[None]:
    try:
        yield
    except _playwright_error() as error:
        raise map_playwright_error(error, action=action) from None


# ── Page ──────────────────────────────────────────────────────────────────────


def speed_script(initial: float) -> str:
    """Return the init script that starts every page at *initial* playback speed."""
    return SPEED_JS.replace("__INITIAL_SPEED__", repr(float(initial)))


class ReaderPage:
    """Owner of one Playwright tab working on ElevenReader."""

    def __init__(self, page: Page) -> None:
        """Wrap *page* and remember the newest API token its requests carry."""
        self._page: Page = page
        self._token: str | None = None
        self._stream_listener: Callable[[WebSocket], None] | None = None
        page.set_default_timeout(ACTION_TIMEOUT_S * _MS_PER_S)
        page.on("request", self._remember_token)

    @property
    def token(self) -> str | None:
        """Return the newest authorization token seen on an API request of this tab."""
        return self._token

    @property
    def is_closed(self) -> bool:
        """Whether the tab or its window is gone."""
        return self._page.is_closed()

    async def open_library(self) -> LibraryState:
        """Load the library and report whether it is usable, signed out or unavailable."""
        try:
            response = await self._page.goto(LIBRARY_URL)
        except _playwright_error():
            return LibraryState.UNAVAILABLE
        if response is not None and response.status >= _SERVER_ERROR:
            return LibraryState.UNAVAILABLE
        marker: Locator = self._button("Import").or_(self._page.get_by_role("button", name=_SIGN_IN_NAME))
        try:
            await marker.first.wait_for(state="visible", timeout=LIBRARY_LOAD_S * _MS_PER_S)
        except _playwright_timeout():
            return LibraryState.SIGNED_OUT if _SIGN_IN_URL.search(self._page.url) else LibraryState.UNAVAILABLE
        except _playwright_error():
            return LibraryState.UNAVAILABLE
        return LibraryState.READY if await self.library_ready() else LibraryState.SIGNED_OUT

    async def library_ready(self) -> bool:
        """Whether the library Import button is visible now, without navigating."""
        try:
            return await self._button("Import").count() > 0
        except _playwright_error():
            return False

    async def upload(self, document: Path) -> UploadedRead:
        """Import *document* through the library dialog and return the new read."""
        with _browser_action("upload"):
            await self._button("Import").click()
            async with self._page.expect_response(_is_add_response) as reply:
                await self._page.locator("input[type=file]").set_input_files(document)
                await self._button("Upload").click()
            response = await reply.value
            if not response.ok:
                raise map_http_status(response.status, action="upload", retry_after=response.headers.get("retry-after"))
            body: object = await response.json()
            headers: dict[str, str] = await response.request.all_headers()
        read_id: object = body.get("read_id") if isinstance(body, dict) else None
        char_count: object = body.get("char_count") if isinstance(body, dict) else None
        token: str = headers.get("authorization", "")
        if not isinstance(char_count, int) or isinstance(char_count, bool) or char_count <= 0:
            reason: str = "ElevenReader upload reply lacked the document length"
            raise unavailable_error(reason)
        if not isinstance(read_id, str | int) or not str(read_id) or not token:
            reason = "ElevenReader upload reply lacked the read or the token"
            raise unavailable_error(reason)
        return UploadedRead(read_id=str(read_id), char_count=char_count, token=token)

    async def get_json(self, url: str, token: str, *, action: str) -> dict[str, object]:
        """Return the JSON object of an authorized GET."""
        with _browser_action(action):
            response: APIResponse = await self._page.request.get(url, headers={"authorization": token})
            _require_ok(response, action=action)
            body: object = await response.json()
        if not isinstance(body, dict):
            reason: str = f"ElevenReader returned no object during {action}"
            raise unavailable_error(reason)
        return body

    async def post_json(self, url: str, token: str, data: dict[str, object], *, action: str) -> None:
        """Send an authorized JSON POST."""
        with _browser_action(action):
            response: APIResponse = await self._page.request.post(url, headers={"authorization": token}, data=data)
            _require_ok(response, action=action)

    async def delete(self, url: str, token: str, *, action: str) -> None:
        """Send an authorized DELETE; a resource that is already gone counts as deleted."""
        with _browser_action(action):
            response: APIResponse = await self._page.request.delete(url, headers={"authorization": token})
            if response.status != _NOT_FOUND:
                _require_ok(response, action=action)

    async def open_document(self, read_id: str) -> None:
        """Open one uploaded read and wait until its Play button appears."""
        with _browser_action("open_document"):
            await self._page.goto(f"{LIBRARY_URL}/{read_id}")
            await self._button("Play").wait_for(timeout=READY_TIMEOUT_S * _MS_PER_S)

    async def press_play(self) -> None:
        """Press Play when the player shows it."""
        with _browser_action("press_play"):
            play: Locator = self._button("Play")
            if await play.count():
                await play.click()

    async def player_state(self) -> PlayerState:
        """Return the player position and document length in characters."""
        with _browser_action("player_state"):
            state: object = await self._page.evaluate(PLAYER_STATE_JS)
        if not isinstance(state, dict):
            return PlayerState(value=0.0, length=0.0)
        return PlayerState(value=_number(state.get("value")), length=_number(state.get("max")))

    async def set_page_speed(self, speed: float) -> None:
        """Retune every frame of the tab, including buffers already playing, to *speed*."""
        for frame in self._page.frames:
            try:
                await frame.evaluate(f"window.__anishiftSetSpeed && window.__anishiftSetSpeed({speed!r})")
            except _playwright_error():
                continue

    async def check_page_speed(self, speed: float) -> None:
        """Inject the speed script into frames without it and retune frames playing off *speed*."""
        fixed: int = 0
        for frame in self._page.frames:
            try:
                state: object = await frame.evaluate(SPEED_STATE_JS)
                if not isinstance(state, dict):
                    await frame.evaluate(speed_script(speed))
                    fixed += 1
                elif _off_speed(state, speed):
                    await frame.evaluate(f"window.__anishiftSetSpeed({speed!r})")
                    fixed += 1
            except _playwright_error():
                continue
        if fixed:
            logger.debug("ElevenReader page speed restored", frames=fixed)

    def watch_stream(self, recorder: StreamRecorder, on_url: Callable[[str], None]) -> None:
        """Feed the read stream's frames to *recorder* and its address to *on_url*."""

        def on_websocket(socket: WebSocket) -> None:
            if STREAM_PATH not in socket.url:
                return
            on_url(socket.url)
            socket.on("framesent", recorder.on_sent)
            socket.on("framereceived", recorder.on_frame)

        self._stream_listener = on_websocket
        self._page.on("websocket", on_websocket)

    def unwatch_stream(self) -> None:
        """Stop feeding new stream sockets to the recorder."""
        listener: Callable[[WebSocket], None] | None = self._stream_listener
        self._stream_listener = None
        if listener is None or self._page.is_closed():
            return
        self._page.remove_listener("websocket", listener)

    async def close(self) -> None:
        """Close the tab, tolerating a tab or browser that is already gone."""
        if self._page.is_closed():
            return
        try:
            await self._page.close()
        except _playwright_error():
            logger.debug("ElevenReader tab was already closed")

    def _button(self, name: str) -> Locator:
        return self._page.get_by_role("button", name=name, exact=True).filter(visible=True)

    def _remember_token(self, request: Request) -> None:
        if API_HOST not in request.url:
            return
        token: str | None = request.headers.get("authorization")
        if token:
            self._token = token


def _is_add_response(response: Response) -> bool:
    return ADD_ENDPOINT in response.url and response.request.method == "POST"


def _require_ok(response: APIResponse, *, action: str) -> None:
    if response.ok:
        return
    raise map_http_status(response.status, action=action, retry_after=response.headers.get("retry-after"))


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _off_speed(state: dict[str, object], speed: float) -> bool:
    rates: object = state.get("rates")
    playing: list[object] = rates if isinstance(rates, list) else []
    if abs(_number(state.get("target")) - speed) > SPEED_TOLERANCE:
        return True
    return any(abs(_number(rate) - speed) > SPEED_TOLERANCE for rate in playing)


# ── Account ───────────────────────────────────────────────────────────────────


async def prepare_account(page: ReaderPage, token: str, voice_id: str, cleanup: AccountCleanup) -> None:
    """Set the account voice and reading speed 1x, registering the restore first; refuse a voice that did not take."""
    current: dict[str, object] = await page.get_json(USER_CONFIG_URL, token, action="read_account")
    if cleanup.restore is None:
        cleanup.restore = _settings(current)
    await page.post_json(USER_CONFIG_URL, token, _with_settings(current, voice_id, READING_SPEED), action="set_account")
    check: AccountSettings = _settings(await page.get_json(USER_CONFIG_URL, token, action="check_account"))
    if check.voice_id != voice_id or check.speed != READING_SPEED:
        message: str = "ElevenReader account did not take the voice or reading speed"
        raise voice_error(message)


async def run_cleanup(page: ReaderPage, token: str, cleanup: AccountCleanup) -> None:
    """Run every pending step under its own deadline; a step that succeeds leaves *cleanup*, a failed one stays."""
    restore: AccountSettings | None = cleanup.restore
    if restore is not None and await _cleanup_step("restore_settings", lambda: _restore(page, token, restore)):
        cleanup.restore = None
    read_id: str | None = cleanup.read_id
    if read_id is not None and await _cleanup_step(
        "delete_read",
        lambda: page.delete(f"{READS_URL}/{read_id}", token, action="delete_read"),
    ):
        cleanup.read_id = None


async def _restore(page: ReaderPage, token: str, settings: AccountSettings) -> None:
    current: dict[str, object] = await page.get_json(USER_CONFIG_URL, token, action="read_account")
    await page.post_json(
        USER_CONFIG_URL,
        token,
        _with_settings(current, settings.voice_id, settings.speed),
        action="restore_account",
    )


async def _cleanup_step(kind: str, run: Callable[[], Awaitable[None]]) -> bool:
    try:
        async with asyncio.timeout(CLEANUP_STEP_TIMEOUT_S):
            await run()
    except TimeoutError:
        logger.warning("ElevenReader cleanup step timed out", step=kind)
        return False
    except TtsError as error:
        logger.warning("ElevenReader cleanup step failed", step=kind, code=error.context.code.value)
        return False
    logger.debug("ElevenReader cleanup step done", step=kind)
    return True


def _settings(config: dict[str, object]) -> AccountSettings:
    voice: object = config.get("default_voice_id")
    speed: object = config.get("playback_speed_rate")
    return AccountSettings(
        voice_id=voice if isinstance(voice, str) else None,
        speed=float(speed) if isinstance(speed, int | float) and not isinstance(speed, bool) else None,
    )


def _with_settings(config: dict[str, object], voice_id: str | None, speed: float | None) -> dict[str, object]:
    updated: dict[str, object] = dict(config)
    if voice_id is not None:
        updated["default_voice_id"] = voice_id
    if speed is not None:
        updated["playback_speed_rate"] = speed
    return updated


# ── Session ───────────────────────────────────────────────────────────────────


def read_session(root: Path) -> SessionRecord | None:
    """Return the saved check result, or None when it is missing or unreadable."""
    try:
        data: object = json.loads(session_file(root).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(data, dict):
        return None
    signed_in: object = data.get("signed_in")
    checked_at: object = data.get("checked_at")
    if not isinstance(signed_in, bool) or not isinstance(checked_at, str):
        return None
    try:
        return SessionRecord(signed_in=signed_in, checked_at=datetime.fromisoformat(checked_at))
    except ValueError:
        return None


def write_session(root: Path, *, signed_in: bool) -> None:
    """Save the check result atomically; a write failure is logged, never raised."""
    payload: dict[str, object] = {"signed_in": signed_in, "checked_at": datetime.now(UTC).isoformat()}
    try:
        atomic_json_snapshot(session_file(root), payload)
    except OSError:
        logger.warning("ElevenReader session state could not be saved")


async def require_signed_in(page: ReaderPage, root: Path) -> None:
    """Open the library and record the session; raise when signed out or the site is unavailable."""
    state: LibraryState = await page.open_library()
    if state is LibraryState.READY:
        write_session(root, signed_in=True)
        return
    if state is LibraryState.SIGNED_OUT:
        write_session(root, signed_in=False)
        message: str = "ElevenReader session is signed out"
        raise auth_error(message)
    reason: str = "ElevenReader library is unavailable"
    raise unavailable_error(reason)


async def sign_in(root: Path, *, timeout_s: float = SIGN_IN_TIMEOUT_S) -> SignInOutcome:
    """Open a visible Chrome on the library and wait until the owner signs in or closes the window."""
    from .browser import ChromeBusyError, ChromeMissingError, ChromeSession  # noqa: PLC0415 - keeps Playwright lazy

    session: ChromeSession = ChromeSession(root, headless=False)
    try:
        await session.start()
        page: ReaderPage = await session.new_page()
        signed_in: bool = await _wait_for_library(page, timeout_s)
    except ChromeMissingError:
        return SignInOutcome.NO_CHROME
    except ChromeBusyError:
        return SignInOutcome.BUSY
    except TtsError as error:
        logger.warning("ElevenReader sign-in failed", code=error.context.code.value)
        return SignInOutcome.FAILED
    finally:
        await session.close()
    write_session(root, signed_in=signed_in)
    logger.info("ElevenReader sign-in checked", signed_in=signed_in)
    return SignInOutcome.SIGNED_IN if signed_in else SignInOutcome.SIGNED_OUT


async def _wait_for_library(page: ReaderPage, timeout_s: float) -> bool:
    if await page.open_library() is LibraryState.READY:
        return True
    deadline: float = time.monotonic() + timeout_s
    while time.monotonic() < deadline and not page.is_closed:
        if await page.library_ready():
            return True
        await asyncio.sleep(_SIGN_IN_POLL_S)
    return False
