from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, cast

import pytest
from textual.widgets import Input, OptionList

from anishift.application import AppService, ModelAvailability, ModelProbeResult
from anishift.config import Settings, UserSettings
from anishift.config.field_catalog import SettingCatalogContext, SettingSpec, setting_catalog
from anishift.config.model_catalog import (
    CatalogDefaults,
    CatalogIssue,
    ModelCatalog,
    ModelCatalogError,
    ModelEntry,
    ModelProtocol,
    ProviderEntry,
)
from anishift.errors import ErrorCode, ErrorContext
from anishift.tui import ui_state
from anishift.tui.app import AniShiftApp
from anishift.tui.dialogs.base import DialogScreen
from anishift.tui.models.picker import (
    AVAILABILITY_ATTRIBUTE,
    CATALOG_PROVIDER,
    PRIMARY_MODEL_SETTING_ID,
    availability_text,
)
from anishift.tui.strings import (
    DIALOG_ALREADY_OPEN,
    MODEL_CATALOG_EMPTY,
    MODEL_CATALOG_UNUSABLE,
    MODEL_EXPERIMENTAL,
    MODEL_ISSUES_CATEGORY,
    MODEL_STATE_ERROR,
    MODEL_STATE_UNVERIFIED,
    MODEL_STATE_VERIFIED,
    MODEL_TIME_FORMAT,
    TRANSLATION_MODEL_TITLE,
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SETTLE_PAUSES: Final[int] = 30

_OPENAI_PROVIDER: Final[str] = "foundry-openai"

_ANTHROPIC_PROVIDER: Final[str] = "foundry-anthropic"

_GPT_ALIAS: Final[str] = "gpt-main"

_CLAUDE_ALIAS: Final[str] = "claude-main"

_LAB_ALIAS: Final[str] = "gpt-lab"

_GPT_LABEL: Final[str] = "Foundry main chat"

_TRANSLATION_MODEL_ROW: Final[str] = "LLM model"

_TRANSLATION_PROVIDER_ROW: Final[str] = "LLM provider"

_PROMPT_ROW: Final[str] = "Translation prompt"

_STYLE_ROW: Final[str] = "Translation style"

_MODULES_ROW: Final[str] = "Prompt modules"

_TYPED_TRANSLATION_MODEL: Final[str] = "translation-only-alias"

_TOKEN_VARIABLES: Final[tuple[str, ...]] = ("ANISHIFT_PALANTIR_TOKEN", "FOUNDRY_API_TOKEN")

_FREE_TEXT_PROVIDER: Final[str] = "gemini"

_TRANSLATION_MODEL_SETTING_ID: Final[str] = "llm_provider_model_id"

_FREE_TEXT_DESCRIPTION: Final[str] = "Enter a provider model ID for gemini."


def _providers() -> dict[str, ProviderEntry]:
    return {
        _OPENAI_PROVIDER: ProviderEntry(
            provider_id=_OPENAI_PROVIDER,
            protocol=ModelProtocol.OPENAI_CHAT,
            path="/api/v2/llm/proxy/openai/v1",
        ),
        _ANTHROPIC_PROVIDER: ProviderEntry(
            provider_id=_ANTHROPIC_PROVIDER,
            protocol=ModelProtocol.ANTHROPIC_MESSAGES,
            path="/api/v2/llm/proxy/anthropic/v1",
        ),
    }


def _entries() -> dict[str, ModelEntry]:
    return {
        _GPT_ALIAS: ModelEntry(
            alias=_GPT_ALIAS,
            provider_id=_OPENAI_PROVIDER,
            model_id="openai-model-id",
            label=_GPT_LABEL,
        ),
        _CLAUDE_ALIAS: ModelEntry(
            alias=_CLAUDE_ALIAS,
            provider_id=_ANTHROPIC_PROVIDER,
            model_id="anthropic-model-id",
            label="Foundry long context",
        ),
        _LAB_ALIAS: ModelEntry(
            alias=_LAB_ALIAS,
            provider_id=_OPENAI_PROVIDER,
            model_id="openai-lab-id",
            label="Foundry lab build",
            experimental=True,
        ),
    }


def _catalog(
    *,
    models: dict[str, ModelEntry] | None = None,
    issues: tuple[CatalogIssue, ...] = (),
) -> ModelCatalog:
    return ModelCatalog(
        schema_version=1,
        providers=MappingProxyType(_providers()),
        models=MappingProxyType(_entries() if models is None else models),
        defaults=CatalogDefaults(),
        issues=issues,
    )


def _service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader: Any,
    provider: str = _FREE_TEXT_PROVIDER,
) -> AppService:
    for variable in _TOKEN_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    env_file: Path = tmp_path / ".env"
    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(translation_engine="llm", llm_provider=provider),
        inspector=cast("Any", object()),
        handler_factory=cast("Any", lambda *args, **kwargs: None),
        settings_saver=lambda draft: None,
        catalog_loader=loader,
        env_file=env_file,
    )


@pytest.fixture
def state_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target: Path = tmp_path / "ui_state.json"
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: target)
    return target


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppService:
    return _service(tmp_path, monkeypatch, _catalog)


def test_availability_text_names_each_of_the_three_session_states() -> None:
    moment: datetime = datetime(2026, 8, 26, 21, 15, tzinfo=UTC)
    verified: ModelProbeResult = ModelProbeResult(
        alias=_GPT_ALIAS,
        availability=ModelAvailability.VERIFIED,
        checked_at=moment,
    )
    failed: ModelProbeResult = ModelProbeResult(
        alias=_GPT_ALIAS,
        availability=ModelAvailability.ERROR,
        checked_at=moment,
        error_class="LlmRequestError",
    )
    unverified: ModelProbeResult = ModelProbeResult(
        alias=_GPT_ALIAS,
        availability=ModelAvailability.UNVERIFIED,
        checked_at=moment,
    )
    assert availability_text(None) == MODEL_STATE_UNVERIFIED
    assert availability_text(unverified) == MODEL_STATE_UNVERIFIED
    assert availability_text(verified) == MODEL_STATE_VERIFIED.format(time=moment.strftime(MODEL_TIME_FORMAT))
    assert availability_text(failed) == MODEL_STATE_ERROR.format(error_class="LlmRequestError")


def test_the_model_picker_shows_the_alias_label_provider_protocol_and_session_state(
    service: AppService, state_file: Path
) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            row: str = _row_with(app, _GPT_ALIAS)
            assert _GPT_LABEL in row
            assert _OPENAI_PROVIDER in row
            assert ModelProtocol.OPENAI_CHAT.value in row
            assert MODEL_STATE_UNVERIFIED in row
            assert MODEL_EXPERIMENTAL in _row_with(app, _LAB_ALIAS)
            assert _ANTHROPIC_PROVIDER in "\n".join(_labels(app))

    _run(scenario())


def test_the_model_picker_groups_every_alias_under_its_provider(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            labels: list[str] = _labels(app)
            assert labels[0] == _ANTHROPIC_PROVIDER
            assert _OPENAI_PROVIDER in labels
            assert labels.index(_ANTHROPIC_PROVIDER) < _row_index(app, _CLAUDE_ALIAS)
            assert _row_index(app, _CLAUDE_ALIAS) < labels.index(_OPENAI_PROVIDER)
            assert labels.index(_OPENAI_PROVIDER) < _row_index(app, _GPT_ALIAS)

    _run(scenario())


def test_confirming_a_model_writes_only_the_main_model_alias(service: AppService, state_file: Path) -> None:
    _ = state_file
    before: str = service.settings_snapshot().llm_provider_model_id

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _pick_model(pilot, app, _CLAUDE_ALIAS)
            assert service.settings_snapshot().primary_model_alias == _CLAUDE_ALIAS
            assert service.settings_snapshot().llm_provider_model_id == before

    _run(scenario())


def test_leaving_the_model_picker_keeps_the_stored_alias(service: AppService, state_file: Path) -> None:
    _ = state_file
    service.update_setting(PRIMARY_MODEL_SETTING_ID, _GPT_ALIAS)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            _filter(app, _CLAUDE_ALIAS)
            await pilot.pause()
            await pilot.press("escape")
            await _settle(pilot)
            assert service.settings_snapshot().primary_model_alias == _GPT_ALIAS

    _run(scenario())


def test_the_translation_model_row_never_changes_the_main_model(service: AppService, state_file: Path) -> None:
    _ = state_file
    service.update_setting(PRIMARY_MODEL_SETTING_ID, _GPT_ALIAS)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            app.screen.query_one("#value-input", Input).value = _TYPED_TRANSLATION_MODEL
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().llm_provider_model_id == _TYPED_TRANSLATION_MODEL
            assert service.settings_snapshot().primary_model_alias == _GPT_ALIAS

    _run(scenario())


def test_the_main_model_row_never_changes_the_translation_model(service: AppService, state_file: Path) -> None:
    _ = state_file
    service.update_setting("llm_provider_model_id", _TYPED_TRANSLATION_MODEL)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _pick_model(pilot, app, _GPT_ALIAS)
            assert service.settings_snapshot().primary_model_alias == _GPT_ALIAS
            assert service.settings_snapshot().llm_provider_model_id == _TYPED_TRANSLATION_MODEL

    _run(scenario())


def test_the_translation_surface_offers_the_provider_and_the_model_apart(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("translation")
            await _settle(pilot)
            listed: str = "\n".join(_labels(app))
            assert _TRANSLATION_PROVIDER_ROW in listed
            assert _TRANSLATION_MODEL_ROW in listed

    _run(scenario())


def test_the_prompt_surface_lists_the_task_style_and_module_fields(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("prompts")
            await _settle(pilot)
            listed: str = "\n".join(_labels(app))
            assert _PROMPT_ROW in listed
            assert _STYLE_ROW in listed
            assert _MODULES_ROW in listed

    _run(scenario())


@pytest.mark.parametrize(
    ("row", "setting_id"),
    [(_PROMPT_ROW, "llm_prompt_id"), (_STYLE_ROW, "llm_style_id"), (_MODULES_ROW, "llm_module_ids")],
)
def test_the_prompt_surface_commits_each_field_through_the_shared_dialog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path, row: str, setting_id: str
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _catalog)
    commits: list[str] = []
    original: Any = service.update_setting

    def recorder(field: str, value: Any) -> Any:
        commits.append(field)
        return original(field, value)

    monkeypatch.setattr(service, "update_setting", recorder)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "prompts", row)
            assert _top_dialog(app) == "SelectDialog"
            await pilot.press("enter")
            await _settle(pilot)
            assert commits == [setting_id]

    _run(scenario())


def test_browsing_and_filtering_the_picker_sends_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    probes: list[str] = []
    service: AppService = _service(tmp_path, monkeypatch, _catalog)

    def spy(alias: str) -> None:
        probes.append(alias)

    monkeypatch.setattr(service, "probe_model", spy)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            _filter(app, "gpt")
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("up")
            _filter(app, "claude")
            await _settle(pilot)
            assert probes == []
            assert app.model_availability == {}

    _run(scenario())


def test_a_catalog_entry_stays_unverified_until_a_test_in_this_session(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            states: list[str] = [label for label in _labels(app) if MODEL_STATE_UNVERIFIED in label]
            assert len(states) == len(_entries())
            assert [label for label in _labels(app) if "Verified " in label] == []

    _run(scenario())


def test_the_picker_reports_an_unusable_catalog_without_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _broken_catalog)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            assert _labels(app) == [MODEL_CATALOG_UNUSABLE]
            assert _top_dialog(app) == "SelectDialog"
            feedback = app.session_state.feedback
            assert feedback is not None
            assert feedback.message

    _run(scenario())


def test_the_picker_reports_an_empty_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, lambda: _catalog(models={}))

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            assert _labels(app) == [MODEL_CATALOG_EMPTY]

    _run(scenario())


def test_the_picker_surfaces_a_catalog_issue_instead_of_hiding_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    issue: CatalogIssue = CatalogIssue(
        section="models",
        key="broken-alias",
        message="Model broken-alias references an unknown provider",
    )
    service: AppService = _service(tmp_path, monkeypatch, lambda: _catalog(issues=(issue,)))

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            labels: list[str] = _labels(app)
            assert MODEL_ISSUES_CATEGORY in labels
            assert any(issue.key in label and issue.message in label for label in labels)
            assert any(_GPT_ALIAS in label for label in labels)

    _run(scenario())


def test_reloading_the_catalog_shows_an_entry_added_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    reads: list[int] = []

    def loader() -> ModelCatalog:
        reads.append(1)
        if len(reads) == 1:
            return _catalog(models={_GPT_ALIAS: _entries()[_GPT_ALIAS]})
        return _catalog()

    service: AppService = _service(tmp_path, monkeypatch, loader)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            assert not any(_CLAUDE_ALIAS in label for label in _labels(app))
            await pilot.press("ctrl+r")
            await _settle(pilot)
            assert any(_CLAUDE_ALIAS in label for label in _labels(app))

    _run(scenario())


def test_the_translation_model_row_selects_a_catalog_alias_for_the_catalog_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _catalog, CATALOG_PROVIDER)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            assert _top_dialog(app) == "SelectDialog"
            listed: list[str] = _labels(app)
            assert TRANSLATION_MODEL_TITLE in str(app.screen.query_one("#dialog-title").render())
            assert any(_GPT_ALIAS in label for label in listed)
            assert any(_CLAUDE_ALIAS in label for label in listed)
            assert _OPENAI_PROVIDER in listed
            _filter(app, _CLAUDE_ALIAS)
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().llm_provider_model_id == _CLAUDE_ALIAS

    _run(scenario())


def test_the_translation_model_row_stays_free_text_for_any_other_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _catalog)
    before: str = service.settings_snapshot().llm_provider_model_id

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("translation")
            await _settle(pilot)
            row: str = _row_with(app, _TRANSLATION_MODEL_ROW)
            assert before in row
            assert _FREE_TEXT_DESCRIPTION in row
            _filter(app, _TRANSLATION_MODEL_ROW)
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert _top_dialog(app) == "PromptDialog"
            box: Input = app.screen.query_one("#value-input", Input)
            assert box.value == before
            box.value = _TYPED_TRANSLATION_MODEL
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().llm_provider_model_id == _TYPED_TRANSLATION_MODEL

    _run(scenario())


def test_selecting_a_translation_alias_leaves_the_main_model_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _catalog, CATALOG_PROVIDER)
    service.update_setting(PRIMARY_MODEL_SETTING_ID, _GPT_ALIAS)
    commits: list[str] = []
    original: Any = service.update_setting

    def recorder(field: str, value: Any) -> Any:
        commits.append(field)
        return original(field, value)

    monkeypatch.setattr(service, "update_setting", recorder)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            _filter(app, _CLAUDE_ALIAS)
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert commits == [_TRANSLATION_MODEL_SETTING_ID]
            assert service.settings_snapshot().llm_provider_model_id == _CLAUDE_ALIAS
            assert service.settings_snapshot().primary_model_alias == _GPT_ALIAS

    _run(scenario())


def test_leaving_the_translation_selection_keeps_the_stored_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _catalog, CATALOG_PROVIDER)
    service.update_setting(_TRANSLATION_MODEL_SETTING_ID, _GPT_ALIAS)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            _filter(app, _CLAUDE_ALIAS)
            await pilot.pause()
            await pilot.press("escape")
            await _settle(pilot)
            assert service.settings_snapshot().llm_provider_model_id == _GPT_ALIAS

    _run(scenario())


def test_the_translation_selection_reports_an_unusable_catalog_without_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _broken_catalog, CATALOG_PROVIDER)
    before: str = service.settings_snapshot().llm_provider_model_id

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            assert _top_dialog(app) == "SelectDialog"
            assert MODEL_CATALOG_UNUSABLE in "\n".join(_labels(app))
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().llm_provider_model_id == before

    _run(scenario())


def test_the_translation_selection_reports_an_empty_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file

    def loader() -> ModelCatalog:
        return _catalog(models={})

    service: AppService = _service(tmp_path, monkeypatch, loader, CATALOG_PROVIDER)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            assert MODEL_CATALOG_EMPTY in "\n".join(_labels(app))

    _run(scenario())


def test_browsing_the_translation_selection_sends_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    probes: list[str] = []
    service: AppService = _service(tmp_path, monkeypatch, _catalog, CATALOG_PROVIDER)

    def spy(alias: str) -> None:
        probes.append(alias)

    monkeypatch.setattr(service, "probe_model", spy)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            _filter(app, "gpt")
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("up")
            await _settle(pilot)
            assert probes == []
            assert app.model_availability == {}

    _run(scenario())


def test_the_translation_selection_shows_the_session_state_of_this_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _catalog, CATALOG_PROVIDER)
    moment: datetime = datetime(2026, 8, 26, 21, 15, tzinfo=UTC)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.model_availability[_GPT_ALIAS] = ModelProbeResult(
                alias=_GPT_ALIAS,
                availability=ModelAvailability.VERIFIED,
                checked_at=moment,
            )
            await _open_row(pilot, app, "translation", _TRANSLATION_MODEL_ROW)
            verified: str = MODEL_STATE_VERIFIED.format(time=moment.strftime(MODEL_TIME_FORMAT))
            assert verified in _row_with(app, _GPT_ALIAS)
            assert MODEL_STATE_UNVERIFIED in _row_with(app, _CLAUDE_ALIAS)

    _run(scenario())


def test_the_catalog_provider_is_still_one_of_the_allowed_llm_providers_after_a_rename() -> None:
    specs: tuple[SettingSpec, ...] = setting_catalog(
        SettingCatalogContext.from_user_settings(UserSettings(translation_engine="llm"))
    )
    provider: SettingSpec = next(spec for spec in specs if spec.setting_id == "llm_provider")
    assert CATALOG_PROVIDER in provider.allowed_values


def test_the_shell_still_exposes_the_availability_attribute_the_selection_reads_by_name() -> None:
    assert hasattr(AniShiftApp, AVAILABILITY_ATTRIBUTE)


def test_a_second_surface_is_refused_while_a_dialog_is_open_and_says_why(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("model")
            await _settle(pilot)
            assert _dialog_count(app) == 1
            app.commands.dispatch("translation")
            await _settle(pilot)
            assert _dialog_count(app) == 1
            assert any(_GPT_ALIAS in label for label in _labels(app))
            feedback = app.session_state.feedback
            assert feedback is not None
            assert feedback.message == DIALOG_ALREADY_OPEN

    _run(scenario())


def test_a_refused_surface_leaves_no_catalog_warning_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_file: Path
) -> None:
    _ = state_file
    service: AppService = _service(tmp_path, monkeypatch, _broken_catalog)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("translation")
            await _settle(pilot)
            assert _dialog_count(app) == 1
            app.commands.dispatch("model")
            await _settle(pilot)
            assert _dialog_count(app) == 1
            assert any(_TRANSLATION_MODEL_ROW in label for label in _labels(app))
            feedback = app.session_state.feedback
            assert feedback is not None
            assert feedback.message == DIALOG_ALREADY_OPEN
            assert MODEL_CATALOG_UNUSABLE not in feedback.message

    _run(scenario())


def _broken_catalog() -> ModelCatalog:
    raise ModelCatalogError(
        context=ErrorContext(
            code=ErrorCode.CONFIG_MISSING,
            message="Model catalog is missing",
            suggestion="Copy the bundled example",
        )
    )


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


def _row_index(app: AniShiftApp, needle: str) -> int:
    return next(index for index, label in enumerate(_labels(app)) if needle in label)


async def _pick_model(pilot: Any, app: AniShiftApp, alias: str) -> None:
    app.commands.dispatch("model")
    await _settle(pilot)
    _filter(app, alias)
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)


async def _open_row(pilot: Any, app: AniShiftApp, command: str, query: str) -> None:
    app.commands.dispatch(command)
    await _settle(pilot)
    _filter(app, query)
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)


def _dialog_count(app: AniShiftApp) -> int:
    return sum(1 for screen in app.screen_stack if isinstance(screen, DialogScreen))


def _top_dialog(app: AniShiftApp) -> str:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, DialogScreen):
            return type(screen).__name__
    return ""
