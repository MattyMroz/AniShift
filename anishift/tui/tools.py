"""Safe projections behind ``/init``, ``/status``, ``/debug``, ``/doctor``, ``/help`` and Setup."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Protocol

from anishift.application.events import sanitize_event_message
from anishift.tui.commands.palette import format_keys
from anishift.tui.commands.spec import CommandCategory, CommandSpec, key_display
from anishift.tui.models.connect import TOKEN_SETTING_ID
from anishift.tui.models.picker import availability_text
from anishift.tui.state import RunUiState
from anishift.tui.strings import (
    COMMAND_DEBUG_TITLE,
    COMMAND_DOCTOR_TITLE,
    COMMAND_HELP_TITLE,
    COMMAND_INIT_TITLE,
    COMMAND_STATUS_TITLE,
    CONTEXT_MODEL_SEPARATOR,
    GLYPH_GAP,
    MODEL_CATALOG_UNUSABLE,
    MODEL_ROW_SEPARATOR,
    SELECTION_SUMMARY,
    SETTING_LIST_SEPARATOR,
    SETTING_UNSET,
    SETUP_ACTION_DESCRIPTION,
    SETUP_ACTION_TITLE,
    TOOLS_CATALOG_LABEL,
    TOOLS_CATALOG_SUMMARY,
    TOOLS_CHECK_FAIL_GLYPH,
    TOOLS_CHECK_FAIL_WORD,
    TOOLS_CHECK_OK_GLYPH,
    TOOLS_CHECK_OK_WORD,
    TOOLS_CHECK_SKIP_GLYPH,
    TOOLS_CHECK_SKIP_WORD,
    TOOLS_CHECK_WARN_GLYPH,
    TOOLS_CHECK_WARN_WORD,
    TOOLS_ENCODING_LABEL,
    TOOLS_ENGINE_COUNT,
    TOOLS_ENGINES_LABEL,
    TOOLS_ERRORS_LABEL,
    TOOLS_EVENTS_LABEL,
    TOOLS_FILES_LABEL,
    TOOLS_HELP_ACTIONS_HEADING,
    TOOLS_HELP_COMMANDS_HEADING,
    TOOLS_HELP_KEYS_HEADING,
    TOOLS_INIT_CONNECT_STEP,
    TOOLS_INIT_MODEL_STEP,
    TOOLS_INIT_READY,
    TOOLS_INIT_SETUP_STEP,
    TOOLS_LABEL_GAP,
    TOOLS_MAIN_MODEL_LABEL,
    TOOLS_NONE,
    TOOLS_PENDING,
    TOOLS_PLATFORM_LABEL,
    TOOLS_PRESET_LABEL,
    TOOLS_PYTHON_LABEL,
    TOOLS_RESULT_COUNT,
    TOOLS_RESULT_LABEL,
    TOOLS_RUN_CANCELLING,
    TOOLS_RUN_IDLE,
    TOOLS_RUN_LABEL,
    TOOLS_RUN_PLANNING,
    TOOLS_RUN_RUNNING,
    TOOLS_RUN_TERMINAL,
    TOOLS_SELECTION_LABEL,
    TOOLS_SUGGESTION_GLYPH,
    TOOLS_TRANSLATION_LABEL,
    TOOLS_UNKNOWN,
    TOOLS_VERSION_LABEL,
    TOOLS_WORKERS_DRAINING,
    TOOLS_WORKERS_IDLE,
    TOOLS_WORKERS_LABEL,
    TOOLS_WORKSPACE_GROUPS,
    TOOLS_WORKSPACE_LABEL,
    TOOLS_WORKSPACE_UNREAD,
)
from anishift.tui.widgets.footer import app_version
from anishift.tui.widgets.hints import action_hints, hints_row

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from anishift.application import (
        AppService,
        CheckResult,
        ModelProbeResult,
        ResourceResult,
        RunResult,
        SettingsDraft,
    )
    from anishift.config.model_catalog import ModelCatalog
    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandRun
    from anishift.tui.state import SessionState, UiFeedback

__all__ = [
    "CHECK_MARKS",
    "OK_CHECK_STATUS",
    "SETUP_ACTION_NAME",
    "SETUP_MARKS",
    "EngineStatus",
    "ReportLine",
    "RuntimeFacts",
    "SessionFacts",
    "ToolsIntent",
    "ToolsReport",
    "config_names",
    "console_encoding",
    "debug_report",
    "doctor_report",
    "help_report",
    "init_report",
    "pending_report",
    "report_body",
    "runtime_facts",
    "session_facts",
    "setup_action",
    "setup_report",
    "status_lines",
    "status_report",
]

# ── Constants ──────────────────────────────────────────────────────────────

SETUP_ACTION_NAME: Final[str] = "setup"
"""Name the registry holds the contextual Setup action under, never a slash command."""

OK_CHECK_STATUS: Final[str] = "ok"
"""Value of the one diagnostic status ``/init`` treats as a finished step."""

CHECK_MARKS: Final[Mapping[str, str]] = MappingProxyType(
    {
        OK_CHECK_STATUS: f"{TOOLS_CHECK_OK_GLYPH}{GLYPH_GAP}{TOOLS_CHECK_OK_WORD}",
        "warn": f"{TOOLS_CHECK_WARN_GLYPH}{GLYPH_GAP}{TOOLS_CHECK_WARN_WORD}",
        "fail": f"{TOOLS_CHECK_FAIL_GLYPH}{GLYPH_GAP}{TOOLS_CHECK_FAIL_WORD}",
        "skip": f"{TOOLS_CHECK_SKIP_GLYPH}{GLYPH_GAP}{TOOLS_CHECK_SKIP_WORD}",
    },
)
"""Glyph and word every diagnostic status is shown as, so colour carries nothing."""

SETUP_MARKS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "installed": TOOLS_CHECK_OK_GLYPH,
        "skipped": TOOLS_CHECK_OK_GLYPH,
        "failed": TOOLS_CHECK_FAIL_GLYPH,
        "unavailable": TOOLS_CHECK_WARN_GLYPH,
        "cancelled": TOOLS_CHECK_WARN_GLYPH,
    },
)
"""Glyph every installation outcome is marked with, ahead of its own word."""

_RUN_WORDS: Final[Mapping[RunUiState, str]] = MappingProxyType(
    {
        RunUiState.IDLE: TOOLS_RUN_IDLE,
        RunUiState.PLANNING: TOOLS_RUN_PLANNING,
        RunUiState.RUNNING: TOOLS_RUN_RUNNING,
        RunUiState.CANCELLING: TOOLS_RUN_CANCELLING,
        RunUiState.TERMINAL: TOOLS_RUN_TERMINAL,
    },
)
"""Word every run state of one session is named by."""

_SLASH_PREFIX: Final[str] = "/"
"""Character in front of the name of every listed slash command."""

_PALETTE_HINT_KEY: Final[str] = "ctrl+p"
"""Key the setup step of ``/init`` names as the way into the palette."""


class ToolsIntent(StrEnum):
    """The tools answer one launched worker is expected to fill in."""

    INIT = "init"
    DOCTOR = "doctor"
    SETUP = "setup"


class EngineStatus(Protocol):
    """The two fields the engine summary reads from one availability answer."""

    @property
    def domain(self) -> str:
        """Domain the answered engine belongs to."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether the configuration alone already makes that engine usable."""
        ...


@dataclass(frozen=True, slots=True)
class ReportLine:
    """One row of a report: its label, and the value the label names."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class ToolsReport:
    """One rendered tools answer: its heading and its rows, in reading order."""

    title: str
    lines: tuple[ReportLine, ...]


@dataclass(frozen=True, slots=True)
class SessionFacts:
    """Every safe fact of one session, collected once from its owning object."""

    workspace_read: bool
    group_count: int
    warning_count: int
    selected_count: int
    preset_id: str
    primary_alias: str
    primary_state: str
    translation_provider: str
    translation_alias: str
    token_configured: bool
    engines: tuple[tuple[str, int, int], ...]
    run_state: RunUiState
    result_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class RuntimeFacts:
    """Every safe diagnostic ``/debug`` adds on top of the session facts."""

    version: str
    python: str
    platform: str
    encoding: str
    files: tuple[str, ...]
    catalog: str
    event_count: int
    draining: bool
    error_classes: tuple[str, ...]
    last_error: str


def setup_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that installs the external tools on request."""
    return CommandSpec(
        name=SETUP_ACTION_NAME,
        title=SETUP_ACTION_TITLE,
        description=SETUP_ACTION_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
    )


def console_encoding() -> str:
    """Return the encoding of the stream this session writes its frame to."""
    encoding: str | None = getattr(sys.stdout, "encoding", None)
    return encoding or TOOLS_UNKNOWN


def config_names() -> tuple[str, ...]:
    """Return the file name of every local configuration file, never a directory."""
    from anishift.config.env_file import env_path  # noqa: PLC0415 - a shell module never loads configuration on import
    from anishift.config.model_catalog import model_catalog_path  # noqa: PLC0415 - same lazy configuration boundary
    from anishift.paths import config_path  # noqa: PLC0415 - same lazy configuration boundary

    return (env_path().name, config_path().name, model_catalog_path().name)


def session_facts(
    state: SessionState,
    service: AppService,
    availability: Mapping[str, ModelProbeResult],
) -> SessionFacts:
    """Collect every fact ``/status`` shows, each one from the object that owns it."""
    draft: SettingsDraft = service.settings_snapshot()
    secrets: Mapping[str, bool] = service.environment_statuses()
    return SessionFacts(
        workspace_read=state.workspace is not None,
        group_count=state.group_count,
        warning_count=0 if state.workspace is None else len(state.workspace.warnings),
        selected_count=len(state.selected_group_ids),
        preset_id=state.default_preset_id,
        primary_alias=draft.primary_model_alias,
        primary_state=availability_text(availability.get(draft.primary_model_alias)),
        translation_provider=draft.llm_provider,
        translation_alias=draft.llm_provider_model_id,
        token_configured=bool(secrets.get(TOKEN_SETTING_ID, False)),
        engines=engine_counts(service.engine_availability()),
        run_state=state.run_state,
        result_counts=result_counts(state.result),
    )


def runtime_facts(
    state: SessionState,
    availability: Mapping[str, ModelProbeResult],
    catalog: ModelCatalog | None,
    *,
    draining: bool,
) -> RuntimeFacts:
    """Collect every diagnostic ``/debug`` adds, none of which reads a private object."""
    return RuntimeFacts(
        version=app_version(),
        python=platform.python_version(),
        platform=f"{platform.system()}{GLYPH_GAP}{platform.release()}".strip(),
        encoding=console_encoding(),
        files=config_names(),
        catalog=catalog_text(catalog),
        event_count=len(state.events),
        draining=draining,
        error_classes=error_classes(availability),
        last_error=feedback_text(state.feedback),
    )


def engine_counts(statuses: Sequence[EngineStatus]) -> tuple[tuple[str, int, int], ...]:
    """Count the ready engines of every domain, in the order the facade answers."""
    domains: list[str] = []
    ready: dict[str, int] = {}
    total: dict[str, int] = {}
    for status in statuses:
        if status.domain not in total:
            domains.append(status.domain)
        total[status.domain] = total.get(status.domain, 0) + 1
        ready[status.domain] = ready.get(status.domain, 0) + int(status.is_available)
    return tuple((domain, ready[domain], total[domain]) for domain in domains)


def result_counts(result: RunResult | None) -> tuple[tuple[str, int], ...]:
    """Count the groups of the last run per status, without naming any of them."""
    if result is None:
        return ()
    counted: dict[str, int] = {}
    for group in result.groups:
        key: str = str(group.status)
        counted[key] = counted.get(key, 0) + 1
    return tuple(sorted(counted.items()))


def error_classes(availability: Mapping[str, ModelProbeResult]) -> tuple[str, ...]:
    """Return the safe error class of every failed connection test of this session."""
    return tuple(sorted({result.error_class for result in availability.values() if result.error_class}))


def catalog_text(catalog: ModelCatalog | None) -> str:
    """Return what the local catalog holds, or the reason it cannot be used."""
    if catalog is None:
        return MODEL_CATALOG_UNUSABLE
    return TOOLS_CATALOG_SUMMARY.format(
        providers=len(catalog.providers),
        models=len(catalog.models),
        issues=len(catalog.issues),
    )


def feedback_text(feedback: UiFeedback | None) -> str:
    """Return the redacted message of the last operation, or nothing at all."""
    return TOOLS_NONE if feedback is None else safe_text(feedback.message)


def safe_text(text: str) -> str:
    """Return *text* through the one sanitization rule the application already owns."""
    return sanitize_event_message(text) or ""


def status_lines(facts: SessionFacts) -> tuple[ReportLine, ...]:
    """Project every session fact into the rows ``/status`` and ``/debug`` share."""
    selection: str = SELECTION_SUMMARY.format(selected=facts.selected_count, total=facts.group_count)
    lines: list[ReportLine] = [
        ReportLine(TOOLS_WORKSPACE_LABEL, _workspace_value(facts)),
        ReportLine(TOOLS_SELECTION_LABEL, selection),
        ReportLine(TOOLS_PRESET_LABEL, facts.preset_id),
        ReportLine(TOOLS_MAIN_MODEL_LABEL, _primary_value(facts)),
        ReportLine(TOOLS_TRANSLATION_LABEL, _translation_value(facts)),
        ReportLine(TOOLS_ENGINES_LABEL, _engines_value(facts)),
        ReportLine(TOOLS_RUN_LABEL, _RUN_WORDS[facts.run_state]),
    ]
    if facts.result_counts:
        lines.append(ReportLine(TOOLS_RESULT_LABEL, _result_value(facts)))
    return tuple(lines)


def runtime_lines(runtime: RuntimeFacts) -> tuple[ReportLine, ...]:
    """Project every diagnostic into the rows only ``/debug`` adds."""
    return (
        ReportLine(TOOLS_VERSION_LABEL, runtime.version),
        ReportLine(TOOLS_PYTHON_LABEL, runtime.python),
        ReportLine(TOOLS_PLATFORM_LABEL, runtime.platform),
        ReportLine(TOOLS_ENCODING_LABEL, runtime.encoding),
        ReportLine(TOOLS_FILES_LABEL, SETTING_LIST_SEPARATOR.join(runtime.files)),
        ReportLine(TOOLS_CATALOG_LABEL, runtime.catalog),
        ReportLine(TOOLS_EVENTS_LABEL, str(runtime.event_count)),
        ReportLine(TOOLS_WORKERS_LABEL, TOOLS_WORKERS_DRAINING if runtime.draining else TOOLS_WORKERS_IDLE),
        ReportLine(TOOLS_ERRORS_LABEL, _errors_value(runtime)),
    )


def status_report(facts: SessionFacts) -> ToolsReport:
    """Build the safe summary of the session, without one secret in it."""
    return ToolsReport(title=COMMAND_STATUS_TITLE, lines=status_lines(facts))


def debug_report(facts: SessionFacts, runtime: RuntimeFacts) -> ToolsReport:
    """Build the wider diagnostics, which extend the status rows instead of redoing them."""
    return ToolsReport(title=COMMAND_DEBUG_TITLE, lines=(*status_lines(facts), *runtime_lines(runtime)))


def doctor_report(checks: Sequence[CheckResult]) -> ToolsReport:
    """Build the full diagnostic report: every status, message and suggestion."""
    lines: list[ReportLine] = []
    for check in checks:
        lines.extend(_check_lines(check))
    return ToolsReport(title=COMMAND_DOCTOR_TITLE, lines=tuple(lines))


def setup_report(resources: Sequence[ResourceResult]) -> ToolsReport:
    """Build the installation report, keeping the answer of every single resource."""
    lines: list[ReportLine] = [
        ReportLine(
            resource.name,
            f"{SETUP_MARKS.get(str(resource.outcome), TOOLS_CHECK_SKIP_GLYPH)}{GLYPH_GAP}"
            f"{resource.outcome}{MODEL_ROW_SEPARATOR}{safe_text(resource.detail)}",
        )
        for resource in resources
    ]
    return ToolsReport(title=SETUP_ACTION_TITLE, lines=tuple(lines))


def init_report(checks: Sequence[CheckResult], facts: SessionFacts, registry: CommandRegistry) -> ToolsReport:
    """Build the shortest sequence of steps that are still missing, and nothing else."""
    steps: list[ReportLine] = []
    for check in checks:
        if str(check.status) != OK_CHECK_STATUS:
            steps.extend(_check_lines(check))
    if not facts.token_configured:
        steps.append(ReportLine("", TOOLS_INIT_CONNECT_STEP))
    if not facts.primary_alias:
        steps.append(ReportLine("", TOOLS_INIT_MODEL_STEP))
    if not steps:
        return ToolsReport(title=COMMAND_INIT_TITLE, lines=(ReportLine("", TOOLS_INIT_READY),))
    steps.extend(_setup_step(registry))
    return ToolsReport(title=COMMAND_INIT_TITLE, lines=tuple(steps))


def help_report(registry: CommandRegistry) -> ToolsReport:
    """Project the commands, the contextual actions and the keys the registry holds now."""
    available: tuple[CommandSpec, ...] = registry.available()
    commands: tuple[CommandSpec, ...] = tuple(spec for spec in available if spec.slash_name is not None)
    actions: tuple[CommandSpec, ...] = tuple(spec for spec in available if spec.slash_name is None)
    lines: list[ReportLine] = [ReportLine("", TOOLS_HELP_COMMANDS_HEADING)]
    lines.extend(ReportLine(f"{_SLASH_PREFIX}{spec.slash_name}", _command_value(spec)) for spec in commands)
    if actions:
        lines.append(ReportLine("", TOOLS_HELP_ACTIONS_HEADING))
        lines.extend(ReportLine(spec.title, _command_value(spec)) for spec in actions)
    lines.append(ReportLine("", TOOLS_HELP_KEYS_HEADING))
    lines.append(ReportLine("", hints_row(action_hints(registry))))
    return ToolsReport(title=COMMAND_HELP_TITLE, lines=tuple(lines))


def pending_report(title: str) -> ToolsReport:
    """Build the answer shown under *title* while its worker is still collecting."""
    return ToolsReport(title=title, lines=(ReportLine("", TOOLS_PENDING),))


def report_body(report: ToolsReport) -> str:
    """Render *report* as its heading, a blank row, then one row per line."""
    width: int = max((len(line.label) for line in report.lines), default=0)
    rows: list[str] = [_row(line, width=width) for line in report.lines]
    return "\n".join([report.title, "", *rows])


def _row(line: ReportLine, *, width: int) -> str:
    """Render one row: a padded label and its value, or the value alone."""
    if not line.label:
        return line.value
    return f"{line.label.ljust(width)}{TOOLS_LABEL_GAP}{line.value}"


def _check_lines(check: CheckResult) -> tuple[ReportLine, ...]:
    """Render one diagnostic: its status and message, then its suggestion."""
    mark: str = CHECK_MARKS.get(str(check.status), str(check.status))
    lines: tuple[ReportLine, ...] = (ReportLine(check.name, f"{mark}{GLYPH_GAP}{safe_text(check.message)}"),)
    if not check.suggestion:
        return lines
    return (*lines, ReportLine("", f"{TOOLS_SUGGESTION_GLYPH}{GLYPH_GAP}{safe_text(check.suggestion)}"))


def _setup_step(registry: CommandRegistry) -> tuple[ReportLine, ...]:
    """Name the Setup action of the registry, or nothing while it holds none."""
    spec: CommandSpec | None = registry.command(SETUP_ACTION_NAME)
    if spec is None:
        return ()
    step: str = TOOLS_INIT_SETUP_STEP.format(action=spec.title, key=key_display(_PALETTE_HINT_KEY))
    return (ReportLine("", step),)


def _command_value(spec: CommandSpec) -> str:
    """Render what one command does, and the keys it also answers to."""
    keys: str = format_keys(spec.keys)
    if not keys:
        return spec.description
    return f"{spec.description}{MODEL_ROW_SEPARATOR}{keys}"


def _workspace_value(facts: SessionFacts) -> str:
    """Render how much the last inspection found, or that none has run."""
    if not facts.workspace_read:
        return TOOLS_WORKSPACE_UNREAD
    return TOOLS_WORKSPACE_GROUPS.format(groups=facts.group_count, warnings=facts.warning_count)


def _primary_value(facts: SessionFacts) -> str:
    """Render the main model alias and what this session knows about it."""
    if not facts.primary_alias:
        return SETTING_UNSET
    return f"{facts.primary_alias}{MODEL_ROW_SEPARATOR}{facts.primary_state}"


def _translation_value(facts: SessionFacts) -> str:
    """Render the translation provider and the model role that belongs to it alone."""
    alias: str = facts.translation_alias or SETTING_UNSET
    return f"{facts.translation_provider}{CONTEXT_MODEL_SEPARATOR}{alias}"


def _engines_value(facts: SessionFacts) -> str:
    """Render how many engines of every domain the configuration already allows."""
    return SETTING_LIST_SEPARATOR.join(
        TOOLS_ENGINE_COUNT.format(domain=domain, ready=ready, total=total) for domain, ready, total in facts.engines
    )


def _result_value(facts: SessionFacts) -> str:
    """Render how many groups of the last run ended in each status."""
    return SETTING_LIST_SEPARATOR.join(
        TOOLS_RESULT_COUNT.format(count=count, status=status) for status, count in facts.result_counts
    )


def _errors_value(runtime: RuntimeFacts) -> str:
    """Render the safe error classes of this session, then the last redacted reason."""
    classes: str = SETTING_LIST_SEPARATOR.join(runtime.error_classes) or TOOLS_NONE
    return f"{classes}{MODEL_ROW_SEPARATOR}{runtime.last_error}"
