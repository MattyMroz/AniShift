from __future__ import annotations

import ast
import asyncio
import json
import subprocess
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from textual.containers import Container
from textual.geometry import Region
from textual.widgets import Static
from tui_fakes import shell

import anishift.tui
from anishift.application import InspectedWorkspace, RunEvent, RunEventKind
from anishift.tui.app import (
    COMPOSER_SLOT_ID,
    CONTENT_ID,
    FOOTER_ID,
    FULL_LAYOUT_MIN_HEIGHT,
    FULL_LAYOUT_MIN_WIDTH,
    SPACER_ID,
    AniShiftApp,
    is_compact,
)
from anishift.tui.brand import full_logo_lines
from anishift.tui.lifecycle import begin_planning, begin_run
from anishift.tui.messages import (
    NavigationRequested,
    PlanFailed,
    RunFailed,
    RunProgressed,
    WorkspaceFailed,
    WorkspaceLoaded,
)
from anishift.tui.screens.workspace import WorkspaceView, workspace_body
from anishift.tui.state import GroupIntentDraft, RunUiState, SessionState, UiFeedback, UiRoute
from anishift.tui.strings import (
    COMPOSER_ACCENT_GLYPH,
    COMPOSER_PLACEHOLDER,
    CONTEXT_MODE_AUTO,
    LOCATION_SEPARATOR,
    PATH_ELLIPSIS,
    WORKSPACE_EMPTY,
)
from anishift.tui.widgets.composer import BOX_ID, BOX_ROWS
from anishift.tui.widgets.footer import (
    LOCATION_ID,
    VERSION_ID,
    BottomBar,
    app_version,
    git_branch,
    location_text,
    shortened_path,
)
from anishift.tui.widgets.hints import KEYS_ID, TIP_ID, action_hints, hints_row, tip_row

_FRAME_IDS: Final[tuple[str, ...]] = (
    "#app-body",
    "#app-brand",
    "#app-content",
    "#app-composer",
    "#app-hints",
    "#app-spacer",
    "#app-footer",
)

_ON_SCREEN_IDS: Final[tuple[str, ...]] = (
    "#app-body",
    "#app-content",
    "#app-composer",
    "#app-footer",
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SMALL_SIZE: Final[tuple[int, int]] = (80, 24)

_TALL_SURFACE_ROWS: Final[int] = 120

_BRAND_GAP: Final[int] = 2

_TIP_GAP: Final[int] = 3

_WORDMARK_LESS_HEIGHT: Final[int] = 18

_TIP_LESS_HEIGHT: Final[int] = 11

_FORBIDDEN_IMPORTS: Final[tuple[str, ...]] = (
    "anishift.services",
    "anishift.application.service",
    "anishift.application.runtime",
)

_SHELL_MODULES: Final[tuple[str, ...]] = (
    "anishift.tui.app",
    "anishift.tui.brand",
    "anishift.tui.lifecycle",
    "anishift.tui.messages",
    "anishift.tui.state",
    "anishift.tui.theme",
    "anishift.tui.ui_state",
    "anishift.tui.screens.workspace",
    "anishift.tui.widgets.footer",
)

_IMPORT_PROBE: Final[str] = """
import importlib
import json
import pkgutil
import sys

import anishift.tui

prefixes = tuple(json.loads(sys.argv[1]))
imported = sorted(module.name for module in pkgutil.walk_packages(anishift.tui.__path__, "anishift.tui."))
for name in imported:
    importlib.import_module(name)
loaded = sorted(name for name in sys.modules if name.startswith(prefixes))
print(json.dumps({"imported": imported, "loaded": loaded}))
"""

_PROBE_TIMEOUT: Final[int] = 120


def _import_graph() -> dict[str, list[str]]:
    probe: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - fixed probe on this interpreter
        [sys.executable, "-c", _IMPORT_PROBE, json.dumps(_FORBIDDEN_IMPORTS)],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    graph: dict[str, list[str]] = json.loads(probe.stdout)
    return graph


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


def _event(sequence: int) -> RunEvent:
    return RunEvent(run_id="run-1", sequence=sequence, kind=RunEventKind.TASK_QUEUED)


def _empty_workspace() -> InspectedWorkspace:
    return InspectedWorkspace(groups=(), warnings=())


def _gaps(lines: list[str], first: int, last: int) -> list[int]:
    runs: list[int] = []
    blanks: int = 0
    for line in lines[first : last + 1]:
        if line.strip():
            if blanks:
                runs.append(blanks)
            blanks = 0
            continue
        blanks += 1
    return runs


def _imported_modules(source: str) -> list[str]:
    tree: ast.Module = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def _shell_sources() -> list[Path]:
    root: Path = Path(anishift.tui.__file__).parent
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _rendered(app: AniShiftApp) -> list[str]:
    return [strip.text.rstrip() for strip in app.screen._compositor.render_strips()]


def _row_of(lines: list[str], needle: str) -> int:
    return next(index for index, line in enumerate(lines) if needle in line)


def _fits(app: AniShiftApp, frame_id: str, height: int) -> bool:
    region: Region = app.query_one(frame_id).region
    return region.height > 0 and region.y >= 0 and region.y + region.height <= height


def test_layout_threshold_matches_the_full_terminal_size() -> None:
    assert (FULL_LAYOUT_MIN_WIDTH, FULL_LAYOUT_MIN_HEIGHT) == _FULL_SIZE
    assert is_compact(width=100, height=30) is False
    assert is_compact(width=99, height=30) is True
    assert is_compact(width=100, height=29) is True


def test_the_bottom_bar_joins_the_working_path_with_the_branch() -> None:
    assert location_text(path="~/work", branch="main", width=40) == f"~/work{LOCATION_SEPARATOR}main"


def test_the_bottom_bar_leaves_an_empty_segment_without_a_branch() -> None:
    assert location_text(path="~/work", branch="", width=40) == "~/work"


def test_the_bottom_bar_shortens_the_path_from_the_left() -> None:
    shortened: str = location_text(path="~/a/very/long/working/path", branch="main", width=16)
    assert len(shortened) == 16
    assert shortened.startswith(PATH_ELLIPSIS)
    assert shortened.endswith(f"{LOCATION_SEPARATOR}main")


def test_the_bottom_bar_folds_the_home_directory_to_a_mark() -> None:
    home: Path = Path("/home/anishift")
    assert shortened_path(home / "work" / "repo", home) == str(Path("~/work/repo"))
    assert shortened_path(Path("/elsewhere/repo"), home) == str(Path("/elsewhere/repo"))


def test_the_bottom_bar_reads_the_branch_of_this_repository() -> None:
    assert git_branch(Path(anishift.tui.__file__).parent) != ""


def test_the_bottom_bar_answers_a_missing_repository_with_an_empty_branch(tmp_path: Path) -> None:
    assert git_branch(tmp_path) == ""


def test_the_bottom_bar_answers_a_detached_head_with_an_empty_branch(tmp_path: Path) -> None:
    git_dir: Path = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_bytes(b"9f1b2c3d4e5f60718293a4b5c6d7e8f901234567\n")
    assert git_branch(tmp_path) == ""


def test_the_bottom_bar_follows_the_pointer_of_a_worktree(tmp_path: Path) -> None:
    real: Path = tmp_path / "real"
    real.mkdir()
    (real / "HEAD").write_bytes(b"ref: refs/heads/feature/one\n")
    worktree: Path = tmp_path / "tree"
    worktree.mkdir()
    (worktree / ".git").write_bytes(f"gitdir: {real}\n".encode())
    assert git_branch(worktree) == "feature/one"


def test_the_bottom_bar_reads_the_version_from_the_package_metadata() -> None:
    assert app_version() != ""


def test_workspace_body_shows_the_base_state_without_sources() -> None:
    assert workspace_body(None) == WORKSPACE_EMPTY


def test_the_shell_import_graph_loads_no_backend_module() -> None:
    graph: dict[str, list[str]] = _import_graph()
    assert set(_SHELL_MODULES) <= set(graph["imported"])
    assert graph["loaded"] == []


def test_shell_modules_import_no_backend_module() -> None:
    offenders: list[str] = [
        f"{path.name}:{module}"
        for path in _shell_sources()
        for module in _imported_modules(path.read_text(encoding="utf-8"))
        if module.startswith(_FORBIDDEN_IMPORTS)
    ]
    assert offenders == []


def test_the_import_guard_flags_a_backend_import() -> None:
    assert [
        module
        for module in _imported_modules("from anishift.application.service import AppService\n")
        if module.startswith(_FORBIDDEN_IMPORTS)
    ] == ["anishift.application.service"]


def test_shell_mounts_the_fixed_frame_without_a_backend() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            for frame_id in _FRAME_IDS:
                assert app.query_one(frame_id) is not None
            assert app.session_state.route is UiRoute.WORKSPACE
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_the_start_screen_keeps_the_work_area_empty() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.query_one(WorkspaceView).display is False
            assert [line for line in _rendered(app) if WORKSPACE_EMPTY in line] == []

    _run(scenario())


def test_an_inspection_without_sources_shows_the_base_state_in_the_work_area() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.post_message(WorkspaceLoaded(workspace=_empty_workspace(), generation=app.session_state.generation))
            await pilot.pause()
            view: WorkspaceView = app.query_one(WorkspaceView)
            assert view.content == WORKSPACE_EMPTY
            assert view.display is True
            assert app.query_one(f"#{SPACER_ID}").display is False
            assert app.query_one("#app-brand", Static).display is False

    _run(scenario())


def test_a_work_area_with_a_surface_outranks_the_start_block() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.post_message(WorkspaceLoaded(workspace=_empty_workspace(), generation=app.session_state.generation))
            await pilot.pause()
            work_area: Region = app.query_one(f"#{CONTENT_ID}").region
            composer: Region = app.query_one(f"#{COMPOSER_SLOT_ID}").region
            assert work_area.height > _FULL_SIZE[1] // 2
            assert composer.y + composer.height + app.query_one(f"#{FOOTER_ID}").region.height <= _FULL_SIZE[1]

    _run(scenario())


def test_shell_shows_the_full_wordmark_and_no_header_bar() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.screen.has_class("compact") is False
            assert app.query_one("#app-brand", Static).display is True
            assert app.query("#app-header").nodes == []

    _run(scenario())


@pytest.mark.parametrize("size", [_FULL_SIZE, _SMALL_SIZE])
def test_every_fixed_region_stays_inside_the_visible_screen(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            height: int = size[1]
            assert [frame_id for frame_id in _ON_SCREEN_IDS if not _fits(app, frame_id, height)] == []
            work_area: Region = app.query_one("#app-body").region
            composer: Region = app.query_one("#app-composer").region
            bar: Region = app.query_one("#app-footer").region
            assert work_area.height > composer.height
            assert composer.height >= BOX_ROWS
            assert bar.y + bar.height == height

    _run(scenario())


@pytest.mark.parametrize("size", [_FULL_SIZE, _SMALL_SIZE])
def test_a_work_surface_taller_than_the_terminal_keeps_the_composer_on_screen(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            host: Container = app.query_one(f"#{CONTENT_ID}", Container)
            await host.mount(Static("\n".join(f"row {index}" for index in range(_TALL_SURFACE_ROWS))))
            await pilot.pause()
            assert [frame_id for frame_id in _ON_SCREEN_IDS if not _fits(app, frame_id, size[1])] == []
            work_area: Region = app.query_one(f"#{CONTENT_ID}").region
            composer: Region = app.query_one(f"#{COMPOSER_SLOT_ID}").region
            bar: Region = app.query_one(f"#{FOOTER_ID}").region
            assert work_area.height > 0
            assert composer.height >= BOX_ROWS
            assert bar.y + bar.height == size[1]

    _run(scenario())


def test_a_work_surface_taller_than_the_terminal_scrolls_inside_the_work_area() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            host: Container = app.query_one(f"#{CONTENT_ID}", Container)
            await host.mount(Static("\n".join(f"row {index}" for index in range(_TALL_SURFACE_ROWS))))
            await pilot.pause()
            assert host.is_vertical_scrollbar_grabbed is False
            assert host.max_scroll_y > 0

    _run(scenario())


def test_shrinking_the_terminal_keeps_every_fixed_region_on_screen() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            regions: dict[str, object] = {frame_id: app.query_one(frame_id) for frame_id in _FRAME_IDS}
            state: SessionState = app.session_state
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            assert app.screen.has_class("compact") is True
            assert all(app.query_one(frame_id) is regions[frame_id] for frame_id in _FRAME_IDS)
            assert app.session_state is state
            assert [frame_id for frame_id in _ON_SCREEN_IDS if not _fits(app, frame_id, _SMALL_SIZE[1])] == []
            assert app.query_one("#app-body").region.height > app.query_one("#app-composer").region.height

    _run(scenario())


def test_the_start_screen_renders_the_canonical_block_in_order() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            lines: list[str] = _rendered(app)
            logo: int = _row_of(lines, full_logo_lines()[0])
            field: int = _row_of(lines, COMPOSER_PLACEHOLDER)
            keys: int = _row_of(lines, hints_row(action_hints(app.commands)))
            tip: int = _row_of(lines, tip_row())
            bar: int = _row_of(lines, app_version())
            assert logo < field < keys < tip < bar
            assert lines[field].lstrip().startswith(COMPOSER_ACCENT_GLYPH)
            assert COMPOSER_ACCENT_GLYPH in lines[field + 2]
            assert CONTEXT_MODE_AUTO in lines[field + 2]
            assert bar == len(lines) - 1

    _run(scenario())


@pytest.mark.parametrize("size", [_FULL_SIZE, _SMALL_SIZE])
def test_the_start_block_keeps_the_gaps_of_the_specification(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            lines: list[str] = _rendered(app)
            first: int = app.query_one("#app-brand").region.y
            last: int = _row_of(lines, hints_row(action_hints(app.commands)))
            tip: Static = app.query_one(f"#{TIP_ID}", Static)
            if tip.display:
                last = _row_of(lines, tip_row())
            dense: bool = app.screen.has_class("compact")
            expected: list[int] = [] if dense else [_BRAND_GAP, _TIP_GAP]
            assert sorted(gap for gap in _gaps(lines, first, last) if gap > 1) == expected

    _run(scenario())


def test_the_box_is_the_last_row_the_composer_paints() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            box: Region = app.query_one(f"#{BOX_ID}").region
            keys: Region = app.query_one(f"#{KEYS_ID}").region
            lines: list[str] = _rendered(app)
            assert keys.y == box.y + box.height
            assert COMPOSER_ACCENT_GLYPH not in lines[keys.y]

    _run(scenario())


@pytest.mark.parametrize("size", [_FULL_SIZE, _SMALL_SIZE])
def test_the_key_hints_hang_on_the_left_edge_of_the_composer_box(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            box: Region = app.query_one(f"#{BOX_ID}").region
            keys: Region = app.query_one(f"#{KEYS_ID}").region
            assert keys.x == box.x
            assert keys.width == box.width
            lines: list[str] = _rendered(app)
            field: int = _row_of(lines, COMPOSER_PLACEHOLDER)
            hints: int = _row_of(lines, hints_row(action_hints(app.commands)))
            assert lines[field].index(COMPOSER_ACCENT_GLYPH) == box.x
            assert len(lines[hints]) - len(lines[hints].lstrip()) == box.x

    _run(scenario())


def test_the_start_block_sits_vertically_centred_between_the_free_rows() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            above: int = app.query_one(f"#{CONTENT_ID}").region.height
            below: int = app.query_one(f"#{SPACER_ID}").region.height
            assert above > 0
            assert abs(above - below) <= 1

    _run(scenario())


def test_only_the_composer_edge_owns_a_border_on_the_start_screen() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            bordered: list[str] = [
                str(widget.id or type(widget).__name__) for widget in app.screen.query("*") if widget.styles.border
            ]
            assert bordered == [BOX_ID]

    _run(scenario())


def test_the_bottom_bar_shows_the_location_and_the_version() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            bar: BottomBar = app.query_one(BottomBar)
            assert str(app.query_one(f"#{VERSION_ID}", Static).content) == app_version()
            location: str = str(app.query_one(f"#{LOCATION_ID}", Static).content)
            assert location.endswith(f"{LOCATION_SEPARATOR}{git_branch(Path.cwd())}")
            assert bar.region.width == _FULL_SIZE[0]

    _run(scenario())


def test_the_tip_outlives_the_wordmark_as_the_terminal_shrinks() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.query_one(f"#{TIP_ID}", Static).display is True
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            assert app.query_one(f"#{TIP_ID}", Static).display is True
            await pilot.resize_terminal(_SMALL_SIZE[0], _WORDMARK_LESS_HEIGHT)
            await pilot.pause()
            assert app.query_one("#app-brand").display is False
            assert app.query_one(f"#{TIP_ID}", Static).display is True
            await pilot.resize_terminal(_SMALL_SIZE[0], _TIP_LESS_HEIGHT)
            await pilot.pause()
            assert app.query_one(f"#{TIP_ID}", Static).display is False
            assert app.query_one("#app-composer").region.height >= BOX_ROWS

    _run(scenario())


def test_shrinking_the_terminal_never_shrinks_the_wordmark() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            brand: Static = app.query_one("#app-brand", Static)
            full: str = str(brand.content)
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            assert str(brand.content) == full
            assert brand.region.height == len(full_logo_lines())

    _run(scenario())


def test_growing_the_terminal_restores_the_full_layout() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_SMALL_SIZE) as pilot:
            await pilot.pause()
            assert app.screen.has_class("compact") is True
            await pilot.resize_terminal(*_FULL_SIZE)
            await pilot.pause()
            assert app.screen.has_class("compact") is False

    _run(scenario())


def test_navigation_moves_the_route_and_hides_the_workspace_view() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.post_message(NavigationRequested(UiRoute.AUTO))
            await pilot.pause()
            assert app.session_state.route is UiRoute.AUTO
            assert app.query_one(WorkspaceView).display is False

    _run(scenario())


def test_navigation_keeps_the_drafts_of_the_session() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            draft: GroupIntentDraft = GroupIntentDraft(group_id="ep01", products=set())
            app.session_state.manual_drafts["ep01"] = draft
            app.post_message(NavigationRequested(UiRoute.MANUAL))
            await pilot.pause()
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            assert app.session_state.manual_drafts["ep01"] is draft

    _run(scenario())


def test_a_late_run_event_of_an_old_generation_changes_nothing() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int | None = begin_planning(app.session_state)
            assert generation is not None
            assert begin_run(app.session_state, "run-1") is True
            app.post_message(RunProgressed(events=(_event(1),), run_id="run-1", generation=generation - 1))
            await pilot.pause()
            assert app.session_state.events == []
            app.post_message(RunProgressed(events=(_event(2),), run_id="run-1", generation=generation))
            await pilot.pause()
            assert [event.sequence for event in app.session_state.events] == [2]

    _run(scenario())


def test_a_run_event_of_another_run_changes_nothing() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int | None = begin_planning(app.session_state)
            assert generation is not None
            assert begin_run(app.session_state, "run-1") is True
            app.post_message(RunProgressed(events=(_event(1),), run_id="run-2", generation=generation))
            await pilot.pause()
            assert app.session_state.events == []

    _run(scenario())


def test_a_late_failure_of_an_old_generation_never_reaches_the_state() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.post_message(WorkspaceFailed(reason="Skanowanie nie powiodło się", generation=-1))
            app.post_message(PlanFailed(reason="Nie ukończono", generation=-1))
            app.post_message(RunFailed(reason="Nie ukończono", run_id="run-1", generation=-1))
            await pilot.pause()
            assert app.session_state.feedback is None
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_a_failure_of_the_current_generation_reaches_the_state() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int = app.session_state.generation
            app.post_message(WorkspaceFailed(reason="Skanowanie nie powiodło się", generation=generation))
            await pilot.pause()
            assert app.session_state.feedback == UiFeedback.error("Skanowanie nie powiodło się")

    _run(scenario())


@pytest.mark.parametrize("size", [_FULL_SIZE, _SMALL_SIZE])
def test_shell_mounts_at_both_canonical_sizes(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one("#app-composer") is not None
            assert app.query_one(BottomBar) is not None

    _run(scenario())
