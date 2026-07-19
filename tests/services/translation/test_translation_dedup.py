from anishift.services.translation.dedup import (
    deduplicate,
    redistribute,
    redistribute_flags,
)


def test_1000_duplicates_collapse_to_one() -> None:
    lines = ["same"] * 1000
    result = deduplicate(lines)
    assert result.unique == ("same",)
    assert all(position == 0 for position in result.index_map)


def test_dedup_is_deterministic() -> None:
    lines = ["a", "b", "a", "c", "b"]
    first = deduplicate(lines)
    second = deduplicate(lines)
    assert first == second
    assert first.unique == ("a", "b", "c")


def test_empty_lines_pass_through() -> None:
    lines = ["a", "", "   ", "b"]
    result = deduplicate(lines)
    assert result.unique == ("a", "b")
    assert result.index_map == (0, -1, -1, 1)


def test_redistribute_restores_full_list() -> None:
    lines = ["a", "b", "a"]
    result = deduplicate(lines)
    out = redistribute(["PL-a", "PL-b"], result, lines)
    assert out == ["PL-a", "PL-b", "PL-a"]


def test_redistribute_passes_empty_lines_unchanged() -> None:
    lines = ["a", "", "b"]
    result = deduplicate(lines)
    out = redistribute(["PL-a", "PL-b"], result, lines)
    assert out == ["PL-a", "", "PL-b"]


def test_redistribute_flags_maps_ok() -> None:
    lines = ["a", "", "a"]
    result = deduplicate(lines)
    flags = redistribute_flags([False], result)
    assert flags == [False, True, False]
