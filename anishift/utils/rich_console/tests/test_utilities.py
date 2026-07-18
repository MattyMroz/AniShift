"""Tests for rich_console.utilities module."""

from __future__ import annotations

import pytest

from ..utilities import (
    format_bytes,
    format_duration,
    format_percentage,
    get_progress_color,
    get_status_icon,
)

# ── get_status_icon ───────────────────────────────────────────────────────────


class TestGetStatusIcon:
    """Test get_status_icon for all status types and options."""

    @pytest.mark.parametrize(
        ("status", "expected_icon"),
        [
            ("success", "✅"),
            ("error", "❌"),
            ("warning", "⚠️ "),
            ("info", "ℹ️ "),
            ("debug", "🔍"),
            ("critical", "💀"),
            ("pending", "⏳"),
            ("running", "⚙️ "),
            ("stopped", "⏹️ "),
        ],
    )
    def test_all_statuses_with_style(self, status, expected_icon):
        result = get_status_icon(status, with_style=True)
        assert expected_icon in result
        assert result.startswith("[")
        assert result.endswith("]")

    @pytest.mark.parametrize(
        ("status", "expected_icon"),
        [
            ("success", "✅"),
            ("error", "❌"),
            ("debug", "🔍"),
        ],
    )
    def test_without_style(self, status, expected_icon):
        result = get_status_icon(status, with_style=False)
        assert result == expected_icon
        assert "[" not in result

    def test_success_markup_format(self):
        result = get_status_icon("success")
        assert result == "[success]✅[/success]"

    def test_error_markup_format(self):
        result = get_status_icon("error")
        assert result == "[error]❌[/error]"


# ── format_bytes ──────────────────────────────────────────────────────────────


class TestFormatBytes:
    """Test format_bytes with binary/decimal units and edge cases."""

    def test_zero_bytes(self):
        assert format_bytes(0) == "0 B"

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="negative"):
            format_bytes(-1)

    def test_small_bytes(self):
        assert format_bytes(512) == "512.00 B"

    def test_one_kb(self):
        assert format_bytes(1000) == "1.00 KB"

    def test_one_mb(self):
        assert format_bytes(1000**2) == "1.00 MB"

    def test_one_gb(self):
        assert format_bytes(1000**3) == "1.00 GB"

    def test_one_tb(self):
        assert format_bytes(1000**4) == "1.00 TB"

    def test_binary_one_kib(self):
        assert format_bytes(1024, binary=True) == "1.00 KiB"

    def test_binary_one_mib(self):
        assert format_bytes(1024**2, binary=True) == "1.00 MiB"

    def test_precision_zero(self):
        assert format_bytes(1000, precision=0) == "1 KB"

    def test_precision_four(self):
        assert format_bytes(1500, precision=4) == "1.5000 KB"

    def test_fractional_gb(self):
        result = format_bytes(int(1000**3 * 2.5))
        assert result == "2.50 GB"

    def test_float_input(self):
        assert format_bytes(1024.5) == "1.02 KB"

    def test_float_large(self):
        assert format_bytes(1000000.0) == "1.00 MB"

    def test_pb_range(self):
        result = format_bytes(1000**5)
        assert result == "1.00 PB"


# ── get_progress_color ────────────────────────────────────────────────────────


class TestGetProgressColor:
    """Test get_progress_color threshold logic."""

    def test_zero_returns_red(self):
        assert get_progress_color(0) == "red"

    def test_below_warning_returns_red(self):
        assert get_progress_color(49.9) == "red"

    def test_at_warning_returns_yellow(self):
        assert get_progress_color(50) == "yellow"

    def test_between_warning_and_good_returns_yellow(self):
        assert get_progress_color(79.9) == "yellow"

    def test_at_good_returns_green(self):
        assert get_progress_color(80) == "green"

    def test_hundred_returns_green(self):
        assert get_progress_color(100) == "green"

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            get_progress_color(-1)

    def test_over_hundred_raises(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            get_progress_color(101)

    def test_custom_thresholds(self):
        assert get_progress_color(60, good_threshold=90, warning_threshold=60) == "yellow"
        assert get_progress_color(90, good_threshold=90, warning_threshold=60) == "green"
        assert get_progress_color(59, good_threshold=90, warning_threshold=60) == "red"


# ── format_duration ───────────────────────────────────────────────────────────


class TestFormatDuration:
    """Test format_duration at second/minute/hour boundaries."""

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="negative"):
            format_duration(-1)

    def test_zero(self):
        assert format_duration(0) == "0.00s"

    def test_subsecond(self):
        assert format_duration(0.5) == "0.50s"

    def test_seconds_only(self):
        assert format_duration(45) == "45.00s"

    def test_one_minute(self):
        assert format_duration(60) == "1m 0.00s"

    def test_minutes_and_seconds(self):
        assert format_duration(90) == "1m 30.00s"

    def test_one_hour(self):
        assert format_duration(3600) == "1h 0m 0.00s"

    def test_hours_minutes_seconds(self):
        assert format_duration(3665) == "1h 1m 5.00s"

    def test_precision_zero(self):
        assert format_duration(45.7, precision=0) == "46s"

    def test_precision_four(self):
        assert format_duration(1.2345, precision=4) == "1.2345s"


# ── format_percentage ─────────────────────────────────────────────────────────


class TestFormatPercentage:
    """Test format_percentage with various value/total combos."""

    def test_basic(self):
        assert format_percentage(75, 100) == "75.0%"

    def test_third(self):
        assert format_percentage(1, 3, precision=2) == "33.33%"

    def test_half(self):
        assert format_percentage(50, 100) == "50.0%"

    def test_full(self):
        assert format_percentage(100, 100) == "100.0%"

    def test_zero_total(self):
        assert format_percentage(0, 0) == "0.0%"

    def test_negative_total_raises(self):
        with pytest.raises(ValueError, match="negative"):
            format_percentage(10, -1)

    def test_without_symbol(self):
        assert format_percentage(75, 100, with_symbol=False) == "75.0"

    def test_zero_total_without_symbol(self):
        assert format_percentage(0, 0, with_symbol=False) == "0.0"

    def test_over_hundred(self):
        result = format_percentage(150, 100)
        assert result == "150.0%"

    def test_precision(self):
        assert format_percentage(1, 3, precision=4) == "33.3333%"

    def test_zero_total_respects_precision(self):
        assert format_percentage(0, 0, precision=3) == "0.000%"
