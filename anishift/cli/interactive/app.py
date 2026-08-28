"""Interactive command-line loop for AniShift."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from rich.markup import escape

from anishift import __version__
from anishift.application import AppService, GroupStatus, RunResult
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.home import HomeAction, ask_home_action
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.prompts import InteractivePrompts, QuestionaryPrompts
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun, execute_auto_run, prepare_auto_run
from anishift.errors import AniShiftError
from anishift.utils.logger import get_logger
from anishift.utils.rich_console import console

__all__ = ["run_interactive"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_RETURN_PROMPT: Final[str] = "Naciśnij dowolny klawisz, aby wrócić"
"""Prompt shown before Interactive CLI returns to Home."""

_LOG_LOCATION: Final[str] = "logs/anishift.log.jsonl"
"""Relative location of the process diagnostic log."""

_TEMPORARY_ACTIONS: Final[dict[HomeAction, str]] = {
    HomeAction.MANUAL: "Tryb ręczny pojawi się w następnym etapie.",
    HomeAction.SETTINGS: "Ustawienia pojawią się w następnym etapie.",
}
"""Neutral messages for Home actions intentionally deferred beyond Plan 01."""

_REFUSAL_MESSAGES: Final[dict[str, str]] = {
    "The workspace holds no source group to run.": "Workspace nie zawiera materiału do uruchomienia.",
    "No discovered source group is ready to run.": "Żadna wykryta grupa nie jest gotowa do uruchomienia.",
    "The plan cannot run because of a blocking problem.": "Plan nie może zostać uruchomiony.",
}
"""Polish presentation of stable UI-neutral Auto refusals."""

_REFUSAL_SUGGESTIONS: Final[dict[str, str]] = {
    "Put a video or a subtitle file in the workspace and run the preset again.": (
        "Umieść plik wideo lub napisów w workspace i spróbuj ponownie."
    ),
    "Give every group usable text, resolve its conflict, then run the preset again.": (
        "Usuń konflikty i zapewnij każdej grupie użyteczne napisy."
    ),
}
"""Polish presentation of stable UI-neutral Auto suggestions."""

_GROUP_STATUS_LABELS: Final[dict[GroupStatus, str]] = {
    GroupStatus.SUCCEEDED: "gotowe",
    GroupStatus.PARTIAL: "częściowo",
    GroupStatus.FAILED: "błąd",
    GroupStatus.CANCELLED: "anulowano",
}
"""Polish labels for terminal group outcomes."""


def run_interactive(service: AppService, prompts: InteractivePrompts | None = None) -> None:
    """Run Home and its Plan 01 actions until the user exits."""
    prompt_adapter: InteractivePrompts = prompts or QuestionaryPrompts()
    with prompt_adapter.screen():
        _run_interactive_loop(service, prompt_adapter)


def _run_interactive_loop(service: AppService, prompts: InteractivePrompts) -> None:
    """Keep every interactive view inside one terminal screen lifecycle."""
    while True:
        try:
            action: HomeAction = ask_home_action(prompts, version=__version__)
            if action is HomeAction.EXIT:
                return
            if action is HomeAction.AUTO:
                _run_auto(service, prompts)
            else:
                _show_temporary_action(action, prompts)
        except KeyboardInterrupt:
            logger.info("Interactive session interrupted")
            return


def _run_auto(service: AppService, prompts: InteractivePrompts) -> None:
    """Prepare, execute and report one automatic run before returning Home."""
    prompts.clear_screen()
    try:
        with console.status("[info]Skanowanie workspace[/info]", spinner="dots"):
            preset_id: str = service.default_preset_id()
            preparation: PreparedAutoRun | AutoRunRefusal = prepare_auto_run(service, preset_id)
    except (AniShiftError, OSError) as problem:
        _show_problem(problem)
        prompts.pause(_RETURN_PROMPT)
        return
    if isinstance(preparation, AutoRunRefusal):
        _show_refusal(preparation)
        prompts.pause(_RETURN_PROMPT)
        return
    try:
        with RichRunProgress(preparation) as progress:
            result: RunResult = execute_auto_run(service, preparation, progress)
    except KeyboardInterrupt:
        logger.info("Interactive automatic run interrupted")
        console.print("\n[warning]Anulowano[/warning]")
        prompts.pause(_RETURN_PROMPT)
        return
    except (AniShiftError, OSError) as problem:
        logger.warning("Interactive automatic run failed", error_class=type(problem).__name__)
        _show_problem(problem)
        prompts.pause(_RETURN_PROMPT)
        return
    _show_result(result, preparation, service.workspace_root)
    prompts.pause(_RETURN_PROMPT)


def _show_temporary_action(action: HomeAction, prompts: InteractivePrompts) -> None:
    """Show one deliberately deferred Home action and return to the menu."""
    prompts.clear_screen()
    console.print(_TEMPORARY_ACTIONS[action])
    prompts.pause(_RETURN_PROMPT)


def _show_refusal(refusal: AutoRunRefusal) -> None:
    """Render a shared automatic-run refusal in Polish."""
    console.print(f"[warning]{escape(_REFUSAL_MESSAGES.get(refusal.message, _safe(refusal.message)))}[/warning]")
    for blocker in refusal.blockers:
        console.print(f"  {escape(blocker.scope)}: {escape(_safe(blocker.message))}")
    if refusal.suggestion:
        suggestion: str = _REFUSAL_SUGGESTIONS.get(refusal.suggestion, _safe(refusal.suggestion))
        console.print(f"  [gray]{escape(suggestion)}[/gray]")


def _show_problem(problem: AniShiftError | OSError) -> None:
    """Render one expected failure without a traceback or private location."""
    console.print(f"[error]Błąd[/error] · {escape(_safe(str(problem)))}")
    suggestion: str = problem.context.suggestion if isinstance(problem, AniShiftError) else ""
    if suggestion:
        console.print(f"  [gray]{escape(_safe(suggestion))}[/gray]")
    console.print(f"[gray]Szczegóły: {_LOG_LOCATION}[/gray]")


def _show_result(result: RunResult, prepared: PreparedAutoRun, workspace_root: Path) -> None:
    """Render one safe terminal summary after progress has stopped."""
    labels: dict[str, str] = {group.group_id: group.source.stem for group in prepared.workspace.groups}
    heading: str = _result_heading(result)
    console.print(f"\n{heading}\n")
    has_errors: bool = False
    for group in result.groups:
        label: str = escape(labels.get(group.group_id, group.group_id))
        status: str = _GROUP_STATUS_LABELS[group.status]
        console.print(f"[bold]{label}[/bold] · {status}")
        for product in group.products:
            console.print(f"  produkt: {escape(_located(product.path, workspace_root))}")
        for product in group.preserved_products:
            console.print(f"  zachowano: {escape(_located(product.path, workspace_root))}")
        for message in group.error_messages:
            has_errors = True
            console.print(f"  powód: {escape(_safe(message))}")
    for warning in result.warnings:
        console.print(f"  ostrzeżenie: {escape(_safe(warning))}")
    if has_errors or not result.succeeded:
        console.print(f"\n[gray]Szczegóły: {_LOG_LOCATION}[/gray]")


def _result_heading(result: RunResult) -> str:
    """Return the aggregate heading for one terminal run result."""
    if result.cancelled:
        return "[warning]Anulowano[/warning]"
    if result.succeeded:
        return "[success]✓ Gotowe[/success]"
    if any(group.status is GroupStatus.PARTIAL for group in result.groups):
        return "[warning]! Zakończono częściowo[/warning]"
    return "[error]✗ Zakończono z błędem[/error]"


def _located(path: Path, root: Path) -> str:
    """Return a workspace-relative product location or only its name."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _safe(text: str) -> str:
    """Sanitize text before exposing it in the terminal."""
    return sanitize_event_message(text) or ""
