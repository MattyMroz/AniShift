"""Interactive command-line loop for AniShift."""

from __future__ import annotations

from typing import Final

from rich.markup import escape

from anishift import __version__
from anishift.application import AppService
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.home import (
    HomeAction,
    ask_home_action,
    brand_for_geometry,
    working_directory_label,
)
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.prompts import (
    AutoGeometry,
    InteractivePrompts,
    QuestionaryPrompts,
    resolve_auto_geometry,
)
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
    """Prepare and execute one automatic run before returning Home."""
    prompts.render_footer(__version__, working_directory_label())
    try:
        preset_id: str = service.default_preset_id()
        preparation: PreparedAutoRun | AutoRunRefusal = prepare_auto_run(service, preset_id)
    except (AniShiftError, OSError) as problem:
        _clear_with_footer(prompts)
        _show_problem(problem)
        prompts.pause(_RETURN_PROMPT)
        return
    if isinstance(preparation, AutoRunRefusal):
        _clear_with_footer(prompts)
        _show_refusal(preparation)
        prompts.pause(_RETURN_PROMPT)
        return

    def render_auto_view() -> None:
        _render_auto_view(prompts, len(preparation.plan.groups))

    try:
        with (
            RichRunProgress(preparation, layout=render_auto_view) as progress,
            prompts.watch_resize(progress.relayout),
        ):
            execute_auto_run(service, preparation, progress)
    except KeyboardInterrupt:
        logger.info("Interactive automatic run interrupted")
        _clear_with_footer(prompts)
        console.print("[warning]Anulowano[/warning]")
        prompts.pause(_RETURN_PROMPT)
        return
    except (AniShiftError, OSError) as problem:
        logger.warning("Interactive automatic run failed", error_class=type(problem).__name__)
        _clear_with_footer(prompts)
        _show_problem(problem)
        prompts.pause(_RETURN_PROMPT)
        return
    prompts.pause("")


def _show_temporary_action(action: HomeAction, prompts: InteractivePrompts) -> None:
    """Show one deliberately deferred Home action and return to the menu."""
    _clear_with_footer(prompts)
    console.print(_TEMPORARY_ACTIONS[action])
    prompts.pause(_RETURN_PROMPT)


def _clear_with_footer(prompts: InteractivePrompts) -> None:
    """Clear the active view and restore the essential terminal footer."""
    prompts.clear_screen()
    prompts.render_footer(__version__, working_directory_label())


def _render_auto_view(prompts: InteractivePrompts, progress_rows: int) -> None:
    """Render responsive Auto chrome around the persistent progress rows."""
    geometry: AutoGeometry = resolve_auto_geometry(
        prompts.terminal_columns(),
        prompts.terminal_rows(),
        progress_rows,
    )
    prompts.clear_screen()
    if geometry.top_padding:
        console.print("\n" * geometry.top_padding, end="")
    console.print(brand_for_geometry(geometry))
    prompts.render_footer(__version__, working_directory_label())
    prompts.position_cursor(geometry.progress_row)


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


def _safe(text: str) -> str:
    """Sanitize text before exposing it in the terminal."""
    return sanitize_event_message(text) or ""
