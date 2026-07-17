"""Tests for the multi-task progress manager (no live display started)."""

from __future__ import annotations

import threading

import pytest

from utils.rich_console import MultiProgressManager, ProgressBarManager


def test_add_task_returns_distinct_ids_and_initial_style() -> None:
    mp = MultiProgressManager()
    first = mp.add_task("first")
    second = mp.add_task("second")

    assert first != second
    assert mp._progress.tasks[0].fields["style"] == "red_bold"


def test_tasks_keep_independent_styles_after_updates() -> None:
    mp = MultiProgressManager()
    first = mp.add_task("first")
    second = mp.add_task("second")

    mp.update(first, 20)
    mp.update(second, 80)

    assert mp._progress.tasks[0].fields["style"] == "red_bold"
    assert mp._progress.tasks[1].fields["style"] == "green_bold"
    assert mp._progress.tasks[0].fields["style"] != mp._progress.tasks[1].fields["style"]


def test_custom_bar_field_reflects_completion() -> None:
    mp = MultiProgressManager()
    task = mp.add_task("task")

    mp.update(task, 50)
    assert "█" in mp._progress.tasks[0].fields["custom_bar"]
    assert "░" in mp._progress.tasks[0].fields["custom_bar"]

    mp.update(task, 100)
    assert "░" not in mp._progress.tasks[0].fields["custom_bar"]


def test_update_clamps_to_total_and_zero() -> None:
    mp = MultiProgressManager()
    task = mp.add_task("task")

    mp.update(task, 150)
    assert mp._progress.tasks[0].completed == 100
    mp.update(task, -5)
    assert mp._progress.tasks[0].completed == 0


def test_advance_accumulates() -> None:
    mp = MultiProgressManager()
    task = mp.add_task("task")

    for _ in range(3):
        mp.advance(task, 10)

    assert mp._progress.tasks[0].completed == 30


def test_parallel_advance_is_thread_safe() -> None:
    mp = MultiProgressManager()
    task = mp.add_task("task")

    def advance_task() -> None:
        for _ in range(25):
            mp.advance(task)

    workers = [threading.Thread(target=advance_task) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert mp._progress.tasks[0].completed == 100


def test_long_description_is_tail_truncated() -> None:
    mp = MultiProgressManager(max_description_length=20)
    task = mp.add_task("a" * 60)

    assert len(mp._states[task].description) == 20
    assert mp._states[task].description.endswith("...")


def test_context_manager_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    with MultiProgressManager() as mp:
        task = mp.add_task("task")
        mp.update(task, 100)
    capsys.readouterr()


def test_single_task_manager_columns_fall_back_without_field() -> None:
    manager = ProgressBarManager("task", total=100)
    task_id = manager.progress.add_task("task", total=100)
    task = manager.progress.tasks[task_id]
    assert manager.percentage_col is not None

    rendered = manager.percentage_col.render(task)

    assert rendered.style == manager.percentage_col.style_name
