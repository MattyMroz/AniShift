from anishift.services.subtitles.text import is_drawing, replace_visible_text, visible_text


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
    assert result.count("replacement") == 1


def test_replace_visible_text_handles_no_tags_and_tag_only() -> None:
    assert replace_visible_text("plain", "new") == "new"
    assert replace_visible_text(r"{\b1}", "new") == r"{\b1}new"
