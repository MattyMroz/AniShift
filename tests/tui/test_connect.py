from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, cast

import pytest
from textual.widgets import Input, OptionList, Static

from anishift.application import AppService, ModelAvailability
from anishift.config import Settings, UserSettings
from anishift.config.model_catalog import (
    CatalogDefaults,
    ModelCatalog,
    ModelEntry,
    ModelProtocol,
    ProviderEntry,
)
from anishift.services.llm import LlmRequestError
from anishift.tui import ui_state
from anishift.tui.app import AniShiftApp
from anishift.tui.dialogs.base import DialogScreen
from anishift.tui.strings import (
    CONNECT_ADDRESS_CONFIGURED,
    CONNECT_TEST_TITLE,
    CONNECT_TEST_WARNING,
    MODEL_STATE_UNVERIFIED,
    MODEL_STATE_VERIFIED,
    MODEL_TIME_FORMAT,
    SECRET_CONFIGURED,
    SECRET_HINT,
    SECRET_MISSING,
    SETTING_UNSET,
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SETTLE_PAUSES: Final[int] = 30

_OPENAI_PROVIDER: Final[str] = "foundry-openai"

_GPT_ALIAS: Final[str] = "gpt-main"

_CLAUDE_ALIAS: Final[str] = "claude-main"

_ADDRESS: Final[str] = "https://enrollment.example.com"

_OTHER_ADDRESS: Final[str] = "https://second.example.com"

_BAD_ADDRESS: Final[str] = "ftp://enrollment.example.com"

_TOKEN: Final[str] = "unit-test-token"  # noqa: S105

_TOKEN_VARIABLES: Final[tuple[str, ...]] = ("ANISHIFT_PALANTIR_TOKEN", "FOUNDRY_API_TOKEN")

_ADDRESS_LABEL: Final[str] = "Palantir enrollment address"

_TOKEN_LABEL: Final[str] = "Palantir token"  # noqa: S105

_RESPONSE_BODY: Final[str] = "provider said no in a body nobody may see"

_ERROR_CLASS: Final[str] = "LlmRequestError"


class _Prober:
    def __init__(self, failure: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._failure: Exception | None = failure

    def __call__(self, config: Any) -> None:
        self.calls.append(str(config.alias))
        if self._failure is not None:
            raise self._failure


def _catalog() -> ModelCatalog:
    providers: dict[str, ProviderEntry] = {
        _OPENAI_PROVIDER: ProviderEntry(
            provider_id=_OPENAI_PROVIDER,
            protocol=ModelProtocol.OPENAI_CHAT,
            path="/api/v2/llm/proxy/openai/v1",
        )
    }
    models: dict[str, ModelEntry] = {
        _GPT_ALIAS: ModelEntry(
            alias=_GPT_ALIAS,
            provider_id=_OPENAI_PROVIDER,
            model_id="openai-model-id",
            label="Foundry main chat",
        ),
        _CLAUDE_ALIAS: ModelEntry(
            alias=_CLAUDE_ALIAS,
            provider_id=_OPENAI_PROVIDER,
            model_id="openai-other-id",
            label="Foundry long context",
        ),
    }
    return ModelCatalog(
        schema_version=1,
        providers=MappingProxyType(providers),
        models=MappingProxyType(models),
        defaults=CatalogDefaults(),
        issues=(),
    )


def _service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prober: _Prober) -> AppService:
    for variable in _TOKEN_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    env_file: Path = tmp_path / ".env"
    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(),
        inspector=cast("Any", object()),
        handler_factory=cast("Any", lambda *args, **kwargs: None),
        settings_saver=lambda draft: None,
        catalog_loader=_catalog,
        model_prober=prober,
        env_file=env_file,
    )


def _connected(service: AppService) -> None:
    service.update_setting("palantir_enrollment_base_url", _ADDRESS)
    service.update_secret("palantir_token", _TOKEN)


@pytest.fixture
def state_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target: Path = tmp_path / "ui_state.json"
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: target)
    return target


@pytest.fixture
def prober() -> _Prober:
    return _Prober()


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prober: _Prober) -> AppService:
    return _service(tmp_path, monkeypatch, prober)


def test_entering_the_connection_surface_sends_no_request(
    service: AppService, prober: _Prober, state_file: Path
) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("connect")
            await _settle(pilot)
            listed: str = "\n".join(_labels(app))
            assert _ADDRESS_LABEL in listed
            assert _TOKEN_LABEL in listed
            assert CONNECT_TEST_TITLE in listed
            assert prober.calls == []
            assert app.model_availability == {}

    _run(scenario())


def test_the_surface_summarises_the_address_and_the_token_without_showing_them(
    service: AppService, state_file: Path
) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("connect")
            await _settle(pilot)
            listed: str = "\n".join(_labels(app))
            assert CONNECT_ADDRESS_CONFIGURED in listed
            assert SECRET_CONFIGURED in listed
            assert _ADDRESS not in listed
            assert _TOKEN not in listed
            assert CONNECT_TEST_WARNING in listed

    _run(scenario())


def test_an_unconfigured_connection_reports_both_rows_as_unset(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("connect")
            await _settle(pilot)
            listed: str = "\n".join(_labels(app))
            assert SETTING_UNSET in listed
            assert SECRET_MISSING in listed

    _run(scenario())


def test_the_confirmation_carries_the_warning_before_any_request(
    service: AppService, prober: _Prober, state_file: Path
) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            assert _top_dialog(app) == "ConfirmDialog"
            question: str = str(app.screen.query_one("#confirm-message", Static).content)
            assert _GPT_ALIAS in question
            assert CONNECT_TEST_WARNING in question
            assert prober.calls == []

    _run(scenario())


def test_declining_the_confirmation_sends_no_request(service: AppService, prober: _Prober, state_file: Path) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            await pilot.press("escape")
            await _settle(pilot)
            assert prober.calls == []
            assert app.model_availability == {}

    _run(scenario())


def test_confirming_the_warning_sends_exactly_one_request(
    service: AppService, prober: _Prober, state_file: Path
) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            await pilot.press("enter")
            await _settle(pilot)
            assert prober.calls == [_GPT_ALIAS]
            result = app.model_availability[_GPT_ALIAS]
            assert result.availability is ModelAvailability.VERIFIED
            assert result.error_class == ""
            assert result.checked_at is not None

    _run(scenario())


def test_confirming_twice_in_a_row_sends_one_request_for_one_confirmation(
    service: AppService, prober: _Prober, state_file: Path
) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            await pilot.press("enter")
            await pilot.press("enter")
            await _settle(pilot)
            assert prober.calls == [_GPT_ALIAS]

    _run(scenario())


def test_a_failed_test_keeps_only_a_safe_error_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    failing: _Prober = _Prober(LlmRequestError(_RESPONSE_BODY))
    service: AppService = _service(tmp_path, monkeypatch, failing)
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            await pilot.press("enter")
            await _settle(pilot)
            assert failing.calls == [_GPT_ALIAS]
            result = app.model_availability[_GPT_ALIAS]
            assert result.availability is ModelAvailability.ERROR
            assert result.error_class == _ERROR_CLASS
            feedback = app.session_state.feedback
            assert feedback is not None
            assert _ERROR_CLASS in feedback.message
            assert _RESPONSE_BODY not in feedback.message
            assert _TOKEN not in feedback.message
            assert _ADDRESS not in feedback.message

    _run(scenario())


def test_a_verified_alias_carries_its_session_state_into_the_model_picker(
    service: AppService, state_file: Path
) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            await pilot.press("enter")
            await _settle(pilot)
            checked: str = app.model_availability[_GPT_ALIAS].checked_at.strftime(MODEL_TIME_FORMAT)
            await _close_dialogs(pilot, app)
            app.commands.dispatch("model")
            await _settle(pilot)
            assert MODEL_STATE_VERIFIED.format(time=checked) in _row_with(app, _GPT_ALIAS)
            assert MODEL_STATE_UNVERIFIED in _row_with(app, _CLAUDE_ALIAS)

    _run(scenario())


def test_a_fresh_app_starts_with_every_alias_unverified(service: AppService, state_file: Path) -> None:
    _ = state_file
    _connected(service)

    async def first() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            await pilot.press("enter")
            await _settle(pilot)
            assert app.model_availability[_GPT_ALIAS].availability is ModelAvailability.VERIFIED

    async def second() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.model_availability == {}
            app.commands.dispatch("model")
            await _settle(pilot)
            assert MODEL_STATE_UNVERIFIED in _row_with(app, _GPT_ALIAS)

    _run(first())
    _run(second())


def test_the_session_answer_is_never_written_to_disk(service: AppService, state_file: Path, tmp_path: Path) -> None:
    _connected(service)
    before: dict[str, bytes] = _tree(tmp_path)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _reach_confirmation(pilot, app, _GPT_ALIAS)
            await pilot.press("enter")
            await _settle(pilot)
            assert app.model_availability[_GPT_ALIAS].availability is ModelAvailability.VERIFIED

    _run(scenario())
    assert _tree(tmp_path) == before
    assert state_file.exists() is False


def test_the_address_editor_opens_empty_and_stores_a_typed_https_origin(service: AppService, state_file: Path) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, _ADDRESS_LABEL)
            box: Input = app.screen.query_one("#value-input", Input)
            assert box.value == ""
            box.value = _OTHER_ADDRESS
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().palantir_enrollment_base_url == _OTHER_ADDRESS

    _run(scenario())


def test_the_address_editor_refuses_an_address_that_is_not_an_https_origin(
    service: AppService, state_file: Path
) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, _ADDRESS_LABEL)
            app.screen.query_one("#value-input", Input).value = _BAD_ADDRESS
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().palantir_enrollment_base_url == _ADDRESS

    _run(scenario())


def test_the_token_editor_never_shows_the_stored_value(service: AppService, state_file: Path) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, _TOKEN_LABEL)
            box: Input = app.screen.query_one("#value-input", Input)
            assert box.value == ""
            assert SECRET_HINT in str(app.screen.query_one("#value-hint", Static).content)
            box.value = "second-token"
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.environment_statuses()["palantir_token"] is True

    _run(scenario())


def test_clearing_the_token_removes_it_after_a_confirmation(service: AppService, state_file: Path) -> None:
    _ = state_file
    _connected(service)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("connect")
            await _settle(pilot)
            _filter(app, _TOKEN_LABEL)
            await pilot.pause()
            await pilot.press("ctrl+d")
            await _settle(pilot)
            assert _top_dialog(app) == "ConfirmDialog"
            await pilot.press("enter")
            await _settle(pilot)
            assert service.environment_statuses()["palantir_token"] is False

    _run(scenario())


def _tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


async def _settle(pilot: Any) -> None:
    for _ in range(_SETTLE_PAUSES):
        await pilot.pause()


def _filter(app: AniShiftApp, query: str) -> None:
    app.screen.query_one("#select-filter", Input).value = query


def _labels(app: AniShiftApp) -> list[str]:
    listing: OptionList = app.screen.query_one("#select-list", OptionList)
    return [str(option.prompt) for option in listing.options]


def _row_with(app: AniShiftApp, needle: str) -> str:
    return next(label for label in _labels(app) if needle in label)


async def _open_row(pilot: Any, app: AniShiftApp, row: str) -> None:
    app.commands.dispatch("connect")
    await _settle(pilot)
    _filter(app, row)
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)


async def _reach_confirmation(pilot: Any, app: AniShiftApp, alias: str) -> None:
    await _open_row(pilot, app, CONNECT_TEST_TITLE)
    _filter(app, alias)
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)


async def _close_dialogs(pilot: Any, app: AniShiftApp) -> None:
    while _top_dialog(app) != "":
        await pilot.press("escape")
        await _settle(pilot)


def _top_dialog(app: AniShiftApp) -> str:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, DialogScreen):
            return type(screen).__name__
    return ""
