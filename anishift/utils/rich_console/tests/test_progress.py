"""Tests for rich_console.progress module."""

from __future__ import annotations

import threading
from typing import Literal
from unittest.mock import MagicMock

import pytest
from rich.text import Text

from ..progress.manager import (
    ColoredBytesColumn,
    ColoredElapsedColumn,
    ColoredETAColumn,
    ColoredPercentageColumn,
    ColoredSpeedColumn,
    DynamicSpinnerColumn,
    ProgressBarBuilder,
    ProgressBarManager,
)
from ..progress.multi import MultiProgressManager

# ── ProgressBarBuilder ────────────────────────────────────────────────────────


class TestProgressBarBuilder:
    """Test static bar-building methods."""

    def test_blocks_zero_progress(self):
        result = ProgressBarBuilder.blocks(10, 0.0, "green")
        assert "░" in result
        assert "[green]" not in result or "█" not in result

    def test_blocks_full_progress(self):
        result = ProgressBarBuilder.blocks(10, 1.0, "green")
        assert "[green]" in result
        assert "░" not in result
        assert "▌" not in result
        assert "█" * 10 in result.replace("[green]", "").split("[/green]")[0]

    def test_blocks_full_no_half_block(self):
        result = ProgressBarBuilder.blocks(8, 1.0, "blue")
        assert "▌" not in result

    def test_blocks_half_progress(self):
        result = ProgressBarBuilder.blocks(10, 0.5, "green")
        assert "[green]" in result
        assert "░" in result

    def test_blocks_clamps_over_one(self):
        result = ProgressBarBuilder.blocks(10, 1.5, "green")
        assert "░" not in result

    def test_blocks_clamps_negative(self):
        result = ProgressBarBuilder.blocks(10, -0.5, "green")
        assert "[green]" in result

    def test_custom_chars(self):
        result = ProgressBarBuilder.custom(10, 0.5, "red", "gray", "#", "-")
        assert "#" in result
        assert "-" in result
        assert "[red]" in result
        assert "[gray]" in result

    def test_custom_full(self):
        result = ProgressBarBuilder.custom(5, 1.0, "blue", "gray", "X", ".")
        assert "X" in result
        assert "." not in result

    def test_custom_empty(self):
        result = ProgressBarBuilder.custom(5, 0.0, "blue", "gray", "X", ".")
        assert "X" not in result
        assert "." in result


# ── ProgressBarManager._truncate_description ──────────────────────────────────


class TestTruncateDescription:
    """Test description truncation modes."""

    def _truncate(
        self,
        text: str,
        max_length: int = 10,
        mode: Literal["start", "middle", "end"] = "end",
    ) -> str:
        return ProgressBarManager._truncate_description(
            ProgressBarManager.__new__(ProgressBarManager),
            text,
            max_length,
            mode,
        )

    def test_short_text_unchanged(self):
        assert self._truncate("abc", 10) == "abc"

    def test_empty_text(self):
        assert self._truncate("", 10) == ""

    def test_exact_length(self):
        assert self._truncate("1234567890", 10) == "1234567890"

    def test_end_mode(self):
        result = self._truncate("very_long_name.zip", 10, "end")
        assert result.endswith("...")
        assert len(result) == 10

    def test_start_mode(self):
        result = self._truncate("very_long_name.zip", 10, "start")
        assert result.startswith("...")
        assert len(result) == 10

    def test_middle_mode(self):
        result = self._truncate("very_long_name.zip", 10, "middle")
        assert "..." in result
        assert len(result) == 10

    def test_min_length_enforced(self):
        result = self._truncate("abcdefghij", 3)
        assert len(result) == 5  # min is 5


# ── ProgressBarManager context manager ────────────────────────────────────────


class TestProgressBarManagerContextManager:
    """Test ProgressBarManager enter/exit lifecycle."""

    def test_enter_returns_self(self):
        with ProgressBarManager("Test", total=10) as pb:
            assert isinstance(pb, ProgressBarManager)

    def test_advance_increments(self):
        with ProgressBarManager("Test", total=10) as pb:
            pb.advance(5)
            assert pb.last_successful_progress == 5

    def test_advance_multiple(self):
        with ProgressBarManager("Test", total=10) as pb:
            pb.advance(3)
            pb.advance(4)
            assert pb.last_successful_progress == 7

    def test_exit_without_error(self):
        with ProgressBarManager("Test", total=5) as pb:
            for _ in range(5):
                pb.advance(1)
        assert pb.last_successful_progress == 5

    def test_exit_with_error_preserves_state(self):
        pb: ProgressBarManager | None = None
        try:
            with ProgressBarManager("Test", total=10) as pb:
                pb.advance(3)
                msg = "test error"
                raise RuntimeError(msg)
        except RuntimeError:
            pass
        assert pb is not None
        assert pb.last_successful_progress == 3

    def test_advance_zero_no_change(self):
        with ProgressBarManager("Test", total=10) as pb:
            pb.advance(5)
            pb.advance(0)
            assert pb.last_successful_progress == 5


# ── ProgressBarManager configuration ──────────────────────────────────────────


class TestProgressBarManagerConfig:
    """Test ProgressBarManager initialization options."""

    def test_default_colors(self):
        assert ProgressBarManager.DEFAULT_COLORS == {
            25: ("red_bold", "red_bold"),
            50: ("orange_bold", "orange_bold"),
            75: ("yellow_bold", "yellow_bold"),
            100: ("green_bold", "green_bold"),
        }

    def test_custom_colors(self):
        custom = {50: ("blue", "blue"), 100: ("green", "green")}
        with ProgressBarManager("Test", total=10, colors=custom) as pb:
            assert pb.colors == custom

    def test_unknown_total_uses_rich_bar(self):
        with ProgressBarManager("Test", total=None) as pb:
            assert pb.bar_style == "rich"

    def test_blocks_bar_type(self):
        with ProgressBarManager("Test", total=10, bar="blocks") as pb:
            assert pb.bar_type == "blocks"

    def test_custom_bar_type(self):
        with ProgressBarManager("Test", total=10, bar="custom", custom_chars=("█", "░")) as pb:
            assert pb.bar_type == "custom"
            assert pb.custom_chars == ("█", "░")

    def test_show_flags_default(self):
        with ProgressBarManager("Test", total=10) as pb:
            assert pb.show_bar is True
            assert pb.show_percentage is True
            assert pb.show_elapsed is True
            assert pb.show_spinner is False
            assert pb.show_eta is False
            assert pb.show_download is False

    def test_show_flags_custom(self):
        with ProgressBarManager(
            "Test",
            total=10,
            show_bar=False,
            show_percentage=False,
            show_spinner=True,
            show_eta=True,
        ) as pb:
            assert pb.show_bar is False
            assert pb.show_percentage is False
            assert pb.show_spinner is True
            assert pb.show_eta is True


# ── ProgressBarManager._update_colors ─────────────────────────────────────────


class TestProgressBarManagerColors:
    """Test color transition logic."""

    def test_initial_color_is_first_threshold(self):
        with ProgressBarManager("Test", total=100) as pb:
            assert pb.current_style == "red_bold"

    def test_color_changes_at_threshold(self):
        with ProgressBarManager("Test", total=100) as pb:
            pb.advance(50)
            assert pb.current_style in ("orange_bold", "yellow_bold")

    def test_color_at_completion(self):
        with ProgressBarManager("Test", total=100) as pb:
            for _ in range(100):
                pb.advance(1)
            assert pb.current_style == "green_bold"

    def test_indeterminate_uses_unknown_style(self):
        with ProgressBarManager("Test", total=None, unknown_style="purple_bold") as pb:
            assert pb.current_style == "purple_bold"


# ── Width Validation ──────────────────────────────────────────────────────────


class TestWidthValidation:
    """Test ValueError on invalid bar widths."""

    def test_blocks_zero_width_raises(self):
        with pytest.raises(ValueError, match="width must be >= 1"):
            ProgressBarBuilder.blocks(0, 0.5, "green")

    def test_blocks_negative_width_raises(self):
        with pytest.raises(ValueError, match="width must be >= 1"):
            ProgressBarBuilder.blocks(-1, 0.5, "green")

    def test_custom_zero_width_raises(self):
        with pytest.raises(ValueError, match="width must be >= 1"):
            ProgressBarBuilder.custom(0, 0.5, "red", "gray", "#", "-")

    def test_custom_negative_width_raises(self):
        with pytest.raises(ValueError, match="width must be >= 1"):
            ProgressBarBuilder.custom(-3, 0.5, "red", "gray", "#", "-")

    def test_blocks_width_one_ok(self):
        result = ProgressBarBuilder.blocks(1, 0.5, "green")
        assert isinstance(result, str)

    def test_custom_width_one_ok(self):
        result = ProgressBarBuilder.custom(1, 1.0, "blue", "gray", "X", ".")
        assert isinstance(result, str)


# ── Column Render Methods ─────────────────────────────────────────────────────


def _mock_task(
    *,
    total: float | None = 100,
    completed: float = 50,
    elapsed: float | None = 10.5,
    time_remaining: float | None = 30.0,
    speed: float | None = 1_000_000.0,
    finished_speed: float | None = None,
    finished: bool = False,
) -> MagicMock:
    """Create a mock Rich Task with common defaults."""
    task = MagicMock()
    task.total = total
    task.completed = completed
    task.percentage = (completed / total * 100) if total else 0
    task.elapsed = elapsed
    task.time_remaining = time_remaining
    task.speed = speed
    task.finished_speed = finished_speed
    task.finished = finished
    task.get_time.return_value = 0.0
    return task


class TestColoredPercentageColumn:
    """Test ColoredPercentageColumn render."""

    def test_render_determinate(self):
        col = ColoredPercentageColumn("green")
        result = col.render(_mock_task(completed=75))
        assert isinstance(result, Text)
        assert "75%" in result.plain

    def test_render_indeterminate(self):
        col = ColoredPercentageColumn("green")
        result = col.render(_mock_task(total=None))
        assert isinstance(result, Text)
        assert result.plain == ""

    def test_render_hundred_percent(self):
        col = ColoredPercentageColumn("green")
        result = col.render(_mock_task(completed=100))
        assert "100%" in result.plain


class TestColoredElapsedColumn:
    """Test ColoredElapsedColumn render."""

    def test_render_with_elapsed(self):
        col = ColoredElapsedColumn("blue")
        result = col.render(_mock_task(elapsed=3661.123))
        assert isinstance(result, Text)
        assert "01:01:01" in result.plain

    def test_render_zero_elapsed(self):
        col = ColoredElapsedColumn("blue")
        result = col.render(_mock_task(elapsed=0))
        assert "00:00:00" in result.plain

    def test_render_none_elapsed(self):
        col = ColoredElapsedColumn("blue")
        result = col.render(_mock_task(elapsed=None))
        assert "00:00:00" in result.plain


class TestColoredETAColumn:
    """Test ColoredETAColumn render."""

    def test_render_with_remaining(self):
        col = ColoredETAColumn("yellow")
        result = col.render(_mock_task(time_remaining=90.0))
        assert isinstance(result, Text)
        assert "01:30" in result.plain

    def test_render_no_remaining(self):
        col = ColoredETAColumn("yellow")
        result = col.render(_mock_task(time_remaining=None))
        assert "00:00:00" in result.plain

    def test_render_indeterminate(self):
        col = ColoredETAColumn("yellow")
        result = col.render(_mock_task(total=None))
        assert result.plain == ""


class TestColoredBytesColumn:
    """Test ColoredBytesColumn render."""

    def test_render_with_total(self):
        col = ColoredBytesColumn("green")
        result = col.render(_mock_task(completed=5_000_000, total=10_000_000))
        assert isinstance(result, Text)
        assert "5.0 MB" in result.plain
        assert "10.0 MB" in result.plain

    def test_render_zero_total(self):
        col = ColoredBytesColumn("green")
        result = col.render(_mock_task(completed=0, total=0))
        assert "0 B" in result.plain


class TestColoredSpeedColumn:
    """Test ColoredSpeedColumn render."""

    def test_render_with_speed(self):
        col = ColoredSpeedColumn("orange")
        result = col.render(_mock_task(speed=2_500_000.0))
        assert isinstance(result, Text)
        assert "/s" in result.plain
        assert "2.5 MB" in result.plain

    def test_render_no_speed(self):
        col = ColoredSpeedColumn("orange")
        result = col.render(_mock_task(speed=None, finished_speed=None))
        assert "? MB/s" in result.plain

    def test_render_finished_speed(self):
        col = ColoredSpeedColumn("orange")
        result = col.render(_mock_task(speed=100.0, finished_speed=5_000_000.0))
        assert "5.0 MB" in result.plain


class TestDynamicSpinnerColumn:
    """Test DynamicSpinnerColumn render and lifecycle."""

    def test_render_active(self):
        col = DynamicSpinnerColumn("red_bold")
        task = _mock_task(finished=False)
        result = col.render(task)
        assert result is not None

    def test_render_finished(self):
        col = DynamicSpinnerColumn("green_bold")
        col.mark_finished()
        task = _mock_task(finished=True)
        result = col.render(task)
        assert isinstance(result, Text)
        assert "✓" in result.plain

    def test_mark_finished_sets_flag(self):
        col = DynamicSpinnerColumn("blue")
        assert col.is_finished is False
        col.mark_finished()
        assert col.is_finished is True


# ── MultiProgressManager ──────────────────────────────────────────────────────


class TestMultiProgressManager:
    def test_add_task_returns_distinct_ids_and_initial_style(self):
        mp = MultiProgressManager()
        first = mp.add_task("first")
        second = mp.add_task("second")
        assert first != second
        assert mp._progress.tasks[0].fields["style"] == "red_bold"

    def test_tasks_keep_independent_styles_after_updates(self):
        mp = MultiProgressManager()
        mp.add_task("first")
        mp.add_task("second")
        mp.update(mp._progress.tasks[0].id, 20)
        mp.update(mp._progress.tasks[1].id, 80)
        assert mp._progress.tasks[0].fields["style"] == "red_bold"
        assert mp._progress.tasks[1].fields["style"] == "green_bold"
        assert mp._progress.tasks[0].fields["style"] != mp._progress.tasks[1].fields["style"]

    def test_custom_bar_field_reflects_completion(self):
        mp = MultiProgressManager(max_description_length=5)
        task = mp.add_task("task")
        mp.update(task, 50)
        half_bar = mp._progress.tasks[0].fields["custom_bar"]
        assert "█" in half_bar or "▌" in half_bar
        assert "░" in half_bar
        mp.update(task, 100)
        assert "░" not in mp._progress.tasks[0].fields["custom_bar"]

    def test_update_clamps_to_total_and_zero(self):
        mp = MultiProgressManager()
        task = mp.add_task("task")
        mp.update(task, 150)
        assert mp._progress.tasks[0].completed == 100
        mp.update(task, -5)
        assert mp._progress.tasks[0].completed == 0

    def test_advance_accumulates(self):
        mp = MultiProgressManager()
        task = mp.add_task("task")
        for _ in range(3):
            mp.advance(task, 10)
        assert mp._progress.tasks[0].completed == 30

    def test_parallel_advance_is_thread_safe(self):
        mp = MultiProgressManager()
        task = mp.add_task("task")

        def advance_task():
            for _ in range(25):
                mp.advance(task)

        workers = [threading.Thread(target=advance_task) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert mp._progress.tasks[0].completed == 100

    def test_long_description_is_tail_truncated(self):
        mp = MultiProgressManager(max_description_length=20)
        task = mp.add_task("a" * 60)
        assert len(mp._states[task].description) == 20
        assert mp._states[task].description.endswith("...")

    def test_context_manager_smoke(self, capsys):
        with MultiProgressManager() as mp:
            task = mp.add_task("task")
            mp.update(task, 100)
        capsys.readouterr()

    def test_single_task_columns_fall_back_without_field(self):
        col = ColoredPercentageColumn("green_bold")
        task = _mock_task(total=100, completed=50)
        task.fields.get.return_value = None
        rendered = col.render(task)
        assert rendered.style == "green_bold"
