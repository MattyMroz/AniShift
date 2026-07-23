from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from .._time_helpers import (
    _in_range,
    _parse_timestamp,
    filter_logs_by_time,
    resolve_time_window,
)


class TestResolveTimeWindow:
    def test_passthrough_when_no_shortcuts(self) -> None:
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)
        s, e = resolve_time_window(start=start, end=end)
        assert s == start
        assert e == end

    def test_none_passthrough(self) -> None:
        s, e = resolve_time_window()
        assert s is None
        assert e is None

    def test_minutes_shortcut(self) -> None:
        before = datetime.now()
        s, e = resolve_time_window(minutes=10)
        after = datetime.now()
        assert s is not None and e is not None
        assert before - timedelta(minutes=10, seconds=1) <= s
        assert e <= after

    def test_hours_shortcut(self) -> None:
        before = datetime.now()
        s, e = resolve_time_window(hours=2)
        after = datetime.now()
        assert s is not None and e is not None
        assert before - timedelta(hours=2, seconds=1) <= s
        assert e <= after

    def test_days_shortcut(self) -> None:
        before = datetime.now()
        s, e = resolve_time_window(days=7)
        after = datetime.now()
        assert s is not None and e is not None
        assert before - timedelta(days=7, seconds=1) <= s
        assert e <= after

    def test_minutes_beats_hours(self) -> None:
        s, _e = resolve_time_window(minutes=5, hours=2)
        assert s is not None
        assert (datetime.now() - s) < timedelta(minutes=6)

    def test_hours_beats_days(self) -> None:
        s, _e = resolve_time_window(hours=1, days=30)
        assert s is not None
        assert (datetime.now() - s) < timedelta(hours=2)


class TestParseTimestamp:
    def test_iso_format(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        result = _parse_timestamp(log)
        assert result == datetime(2024, 6, 15, 12, 0, 0)

    def test_missing_timestamp(self) -> None:
        assert _parse_timestamp({}) is None

    def test_none_timestamp(self) -> None:
        assert _parse_timestamp({"timestamp": None}) is None

    def test_invalid_timestamp(self) -> None:
        assert _parse_timestamp({"timestamp": "not-a-date"}) is None

    def test_non_string_timestamp(self) -> None:
        assert _parse_timestamp({"timestamp": 12345}) is None


class TestInRange:
    def test_within_range(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        start = datetime(2024, 6, 15, 11, 0, 0)
        end = datetime(2024, 6, 15, 13, 0, 0)
        assert _in_range(log, start, end) is True

    def test_before_range(self) -> None:
        log = {"timestamp": "2024-06-15T10:00:00"}
        start = datetime(2024, 6, 15, 11, 0, 0)
        end = datetime(2024, 6, 15, 13, 0, 0)
        assert _in_range(log, start, end) is False

    def test_after_range(self) -> None:
        log = {"timestamp": "2024-06-15T14:00:00"}
        start = datetime(2024, 6, 15, 11, 0, 0)
        end = datetime(2024, 6, 15, 13, 0, 0)
        assert _in_range(log, start, end) is False

    def test_start_only(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        assert _in_range(log, datetime(2024, 6, 15, 11, 0, 0), None) is True
        assert _in_range(log, datetime(2024, 6, 15, 13, 0, 0), None) is False

    def test_end_only(self) -> None:
        log = {"timestamp": "2024-06-15T12:00:00"}
        assert _in_range(log, None, datetime(2024, 6, 15, 13, 0, 0)) is True
        assert _in_range(log, None, datetime(2024, 6, 15, 11, 0, 0)) is False

    def test_no_timestamp_returns_false(self) -> None:
        assert _in_range({}, datetime(2024, 1, 1), datetime(2024, 1, 2)) is False


class TestFilterLogsByTime:
    @pytest.fixture
    def logs(self) -> list[dict[str, str]]:
        return [
            {"timestamp": "2024-06-15T10:00:00", "message": "early"},
            {"timestamp": "2024-06-15T12:00:00", "message": "noon"},
            {"timestamp": "2024-06-15T14:00:00", "message": "late"},
        ]

    def test_no_filter_returns_all(self, logs: list[dict[str, str]]) -> None:
        assert filter_logs_by_time(logs, None, None) == logs

    def test_start_filter(self, logs: list[dict[str, str]]) -> None:
        result = filter_logs_by_time(logs, datetime(2024, 6, 15, 11, 0, 0), None)
        assert len(result) == 2
        assert result[0]["message"] == "noon"

    def test_end_filter(self, logs: list[dict[str, str]]) -> None:
        result = filter_logs_by_time(logs, None, datetime(2024, 6, 15, 13, 0, 0))
        assert len(result) == 2
        assert result[-1]["message"] == "noon"

    def test_both_filters(self, logs: list[dict[str, str]]) -> None:
        result = filter_logs_by_time(
            logs,
            datetime(2024, 6, 15, 11, 0, 0),
            datetime(2024, 6, 15, 13, 0, 0),
        )
        assert len(result) == 1
        assert result[0]["message"] == "noon"

    def test_empty_list(self) -> None:
        assert filter_logs_by_time([], datetime(2024, 1, 1), datetime(2024, 1, 2)) == []
