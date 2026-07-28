from anishift.services.subtitles.text import (
    is_drawing,
    replace_visible_text,
    visible_text,
    visible_verses,
)


def test_visible_text_strips_override_blocks_and_html() -> None:
    assert visible_text(r"{\pos(1,2)}Hello <i>world</i>") == "Hello world"


def test_visible_text_normalises_breaks_and_whitespace() -> None:
    assert visible_text(r"a\Nb\hc") == "a b c"


def test_is_drawing_requires_p_tag() -> None:
    assert is_drawing(r"{\p1}m 0 0 l 1 1") is True
    assert is_drawing("m 0 0 l 1 1") is False
    assert is_drawing("I'm 5") is False


def test_replace_visible_text_keeps_every_tag_block() -> None:
    source = r"{\i1}first{\c&HFFFFFF&}second{\i0}third"
    result = replace_visible_text(source, "replacement")
    assert result.count("{") == source.count("{")
    assert result.count("}") == source.count("}")
    assert result.index(r"{\i1}") < result.index(r"{\c&HFFFFFF&}") < result.index(r"{\i0}")
    assert visible_text(result) == "replacement"


def test_replace_visible_text_handles_no_tags_and_tag_only() -> None:
    assert replace_visible_text("plain", "new") == "new"
    assert replace_visible_text(r"{\b1}", "new") == r"{\b1}new"


def test_replace_visible_text_returns_exact_source_when_text_is_unchanged() -> None:
    source = r"{\c&H0000FF&}M{\c&H00FF00&}u{\c&HFF0000&}s"
    assert replace_visible_text(source, "Mus") == source


def test_replace_visible_text_keeps_inline_tag_anchors() -> None:
    source = r"{\c&H0000FF&}A{\c&H00FF00&}B"
    assert replace_visible_text(source, "XY") == r"{\c&H0000FF&}X{\c&H00FF00&}Y"


def test_replace_visible_text_keeps_tag_at_start_of_second_verse() -> None:
    source = r"{\an8}First\N{\fs20}Second"
    result = replace_visible_text(source, r"Pierwszy\NDrugi")
    assert result == r"{\an8}Pierwszy\N{\fs20}Drugi"


def test_replace_visible_text_preserves_hard_space_anchor() -> None:
    assert replace_visible_text(r"A\hB", "X Y") == r"X\hY"


def test_replace_visible_text_drops_impossible_hard_space_without_splitting_word() -> None:
    assert replace_visible_text(r"A\hB", "Z") == "Z"


def test_replace_visible_text_does_not_split_combining_grapheme() -> None:
    result = replace_visible_text(r"A{\c&HFFFFFF&}B", "e\u0301x")
    assert result == "e\u0301{\\c&HFFFFFF&}x"


def test_replace_visible_text_does_not_split_joined_emoji() -> None:
    result = replace_visible_text("A👩\u200d💻{\\c&HFFFFFF&}B", "X👩\u200d💻Y")
    assert result == "X👩\u200d💻{\\c&HFFFFFF&}Y"


def test_replace_visible_text_does_not_split_flag_emoji() -> None:
    result = replace_visible_text("A{\\c&HFFFFFF&}B", "X🇵🇱Y")
    assert result == "X🇵🇱{\\c&HFFFFFF&}Y"


def test_replace_visible_text_snaps_emphasis_to_word_boundaries() -> None:
    source = r"It isn't good to have {\i1}too{\i0} many spouses."
    result = replace_visible_text(source, "Niezdrowo jest mieć zbyt wielu małżonków.")
    before, emphasized, after = result.partition(r"{\i1}")
    emphasized, separator, after = after.partition(r"{\i0}")
    assert separator
    assert before.endswith((" ", r"\N", "\n")) or not before
    assert emphasized
    assert not emphasized[0].isspace()
    assert not emphasized[-1].isspace()
    assert not after or after[0].isspace() or not after[0].isalnum()


def test_replace_visible_text_does_not_snap_unpaired_emphasis() -> None:
    assert replace_visible_text(r"ABC{\i1}", "Dwa slowa") == r"Dwa slowa{\i1}"


def test_replace_visible_text_does_not_move_mixed_block_with_emphasis() -> None:
    result = replace_visible_text(r"A{\c&HFF&\i1}B{\i0}C", "abcdefghij klm")
    assert not result.startswith(r"{\c&HFF&\i1}")
    assert result.index(r"{\c&HFF&\i1}") < result.index(r"{\i0}")


def test_replace_visible_text_keeps_sequential_emphasis_order_on_one_word() -> None:
    result = replace_visible_text(r"{\i1}a{\i0} {\b1}b{\b0}", "word")
    assert result == r"{\i1}word{\i0}{\b1}{\b0}"


def test_visible_verses_keeps_ass_break_kinds_separate_from_hard_spaces() -> None:
    assert visible_verses(r"{\an8}First\NSecond\nThird\hpart") == (
        "First",
        "Second",
        "Third part",
    )
