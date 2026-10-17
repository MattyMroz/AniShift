from __future__ import annotations

from anishift.text.markers import span_marker, strip_span_markers


def test_span_marker_numbers_opening_and_closing_markers() -> None:
    assert (span_marker(2), span_marker(2, closing=True)) == ("<s2>", "</s2>")


def test_strip_span_markers_removes_markers_and_spare_spaces() -> None:
    assert strip_span_markers("Why are you after <s1>me</s1> <s2> now</s2>?!") == "Why are you after me now?!"


def test_strip_span_markers_leaves_unmarked_text_untouched() -> None:
    assert strip_span_markers("  a <b> c\n") == "  a <b> c\n"
