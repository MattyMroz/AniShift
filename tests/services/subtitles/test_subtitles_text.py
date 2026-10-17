from anishift.services.subtitles.text import (
    is_drawing,
    marked_text,
    replace_visible_text,
    restore_markers,
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


def test_marked_text_wraps_a_mid_line_colour_range() -> None:
    assert marked_text(r"The {\c&H0000FF&}Red{\c&HFFFFFF&} Sword") == "The <s1>Red</s1> Sword"


def test_marked_text_wraps_an_italic_word_without_its_punctuation() -> None:
    source: str = r"Wait a minute! Why are you after {\i1}me{\i0}?!"
    assert marked_text(source) == "Wait a minute! Why are you after <s1>me</s1>?!"


def test_marked_text_leaves_verse_prefixes_and_suffixes_unmarked() -> None:
    source: str = r"{\an8\c&HFFFFFF&}{\i1}but if I did,{\i0}\N{\c&HFFFFFF&}{\i1}it wouldn't be for her.{\i0}"
    assert marked_text(source) == "but if I did, it wouldn't be for her."


def test_marked_text_closes_a_range_running_to_the_line_end() -> None:
    source: str = r"{\fnArial\pos(605,317)}EP 2{\3c&H93CC2E&\c&HFFFFFF&}\h\h\hDeath Games and Demons"
    assert marked_text(source) == "EP 2 <s1>Death Games and Demons</s1>"


def test_marked_text_leaves_in_word_effects_unmarked() -> None:
    assert marked_text(r"T{\3c&H1&}h{\3c&H2&}e {\3c&H3&}Ice") == "The Ice"


def test_marked_text_leaves_more_than_two_ranges_unmarked() -> None:
    source: str = r"{\i1}A{\i0} b {\i1}c{\i0} d {\i1}e{\i0} f"
    assert marked_text(source) == "A b c d e f"


def test_replace_visible_text_places_colour_on_the_marked_translated_word() -> None:
    result: str = replace_visible_text(r"The {\c&H0000FF&}Red{\c&HFFFFFF&} Sword", "Miecz <s1>Czerwieni</s1>")
    assert result == r"Miecz {\c&H0000FF&}Czerwieni{\c&HFFFFFF&}"


def test_replace_visible_text_places_italic_on_the_marked_word_before_punctuation() -> None:
    source: str = r"Wait a minute! Why are you after {\i1}me{\i0}?!"
    result: str = replace_visible_text(source, r"Chwila moment!\NCzemu uwziąłeś się akurat na <s1>mnie</s1>?!")
    assert result == r"Chwila moment!\NCzemu uwziąłeś się akurat na {\i1}mnie{\i0}?!"


def test_replace_visible_text_places_a_range_marked_to_the_line_end() -> None:
    source: str = r"{\pos(605,317)}EP 2{\3c&H93CC2E&}\h\hDeath Games"
    result: str = replace_visible_text(source, "Odcinek 2: <s1>Śmiertelne gry</s1>")
    assert result == r"{\pos(605,317)}Odcinek\h2:\h{\3c&H93CC2E&}Śmiertelne gry"


def test_replace_visible_text_falls_back_to_word_edges_when_a_marker_is_missing() -> None:
    result: str = replace_visible_text(r"The {\c&H0000FF&}Red{\c&HFFFFFF&} Sword", "<s1>Czerwony Miecz")
    assert result == r"{\c&H0000FF&}Czerwony{\c&HFFFFFF&} Miecz"


def test_replace_visible_text_falls_back_when_markers_wrap_nothing() -> None:
    result: str = replace_visible_text(r"The {\c&H0000FF&}Red{\c&HFFFFFF&} Sword", "<s1></s1>Czerwony Miecz")
    assert result == r"{\c&H0000FF&}Czerwony{\c&HFFFFFF&} Miecz"


def test_replace_visible_text_never_splits_a_word_with_a_colour_tag() -> None:
    source: str = r"{\pos(605,317)}EP 2{\3c&H93CC2E&\c&HFFFFFF&}\h\hDeath Games and Demons"
    result: str = replace_visible_text(source, "Odcinek drugi: Śmiertelne gry i demony")
    assert result == r"{\pos(605,317)}Odcinek{\3c&H93CC2E&\c&HFFFFFF&}\hdrugi:\hŚmiertelne gry i demony"


def test_replace_visible_text_keeps_italic_off_trailing_punctuation_without_markers() -> None:
    source: str = r"Wait a minute! Why are you after {\i1}me{\i0}?!"
    result: str = replace_visible_text(source, r"Chwila moment!\NCzemu uwziąłeś się akurat na mnie?!")
    assert result == r"Chwila moment!\NCzemu uwziąłeś się akurat na {\i1}mnie{\i0}?!"


def test_replace_visible_text_spreads_gradient_tags_over_distinct_graphemes() -> None:
    source: str = r"G{\3c&H1&}r{\3c&H2&}a{\3c&H3&}d{\3c&H4&}i{\3c&H5&}e{\3c&H6&}n{\3c&H7&}t{\3c&H8&}word"
    result: str = replace_visible_text(source, "Ostrzenia")
    assert result == r"O{\3c&H1&}s{\3c&H2&}t{\3c&H3&}r{\3c&H4&}z{\3c&H5&}e{\3c&H6&}n{\3c&H7&}i{\3c&H8&}a"


def test_replace_visible_text_keeps_split_verse_prefixes_together_at_a_word_start() -> None:
    source: str = r"{\c&HFFFFFF&}{\i1}I was scared of change,{\i0}\N{\c&HFFFFFF&}{\i1}so I kept thinking.{\i0}"
    result: str = replace_visible_text(source, "Bałam się zmiany, więc wciąż myślałam.")
    assert result == r"{\c&HFFFFFF&}{\i1}Bałam się zmiany, {\i0}{\c&HFFFFFF&}{\i1}więc wciąż myślałam.{\i0}"


def test_restore_markers_follows_new_line_breaks() -> None:
    marked: str = "Czemu uwziąłeś się akurat na <s1>mnie</s1>?!"
    verses: tuple[str, ...] = ("Czemu uwziąłeś się", "akurat na mnie?!")
    assert restore_markers(marked, verses) == ("Czemu uwziąłeś się", "akurat na <s1>mnie</s1>?!")


def test_restore_markers_keeps_a_closing_marker_on_the_word_it_closes() -> None:
    assert restore_markers("<s1>Ja</s1> pukałem", ("Ja", "pukałem")) == ("<s1>Ja</s1>", "pukałem")


def test_restore_markers_returns_verses_of_unmarked_text_unchanged() -> None:
    assert restore_markers("Ja pukałem", ("Ja", "pukałem")) == ("Ja", "pukałem")


def test_replace_visible_text_moves_a_merged_verse_prefix_to_the_nearest_word_start() -> None:
    result: str = replace_visible_text(
        r"{\an8}{\c&HFFFFFF&}CONFUSED\N{\c&HFFFFFF&}GOOD LUCK, AKINE!", "ZDEZORIENTOWANA POWODZENIA, AKINE!"
    )
    assert result == r"{\an8}{\c&HFFFFFF&}ZDEZORIENTOWANA {\c&HFFFFFF&}POWODZENIA, AKINE!"


def test_replace_visible_text_spreads_gradient_tags_evenly_when_graphemes_run_short() -> None:
    source: str = r"{\c&H0&}Abc {\c&H1&}S{\c&H2&}o{\c&H3&}r{\c&H4&}c{\c&H5&}e"
    result: str = replace_visible_text(source, "Abc Ost")
    assert result == r"{\c&H0&}Abc {\c&H1&}O{\c&H2&}{\c&H3&}s{\c&H4&}{\c&H5&}t"


def test_replace_visible_text_ignores_markers_that_leave_no_unstyled_words() -> None:
    source: str = r"{\c&H0600A9&\pos(1,2)}A {\c&HFEFDFE&}Flying, Handsome Man Appeared!"
    result: str = replace_visible_text(source, "<s1>Pojawił się latający przystojniak!</s1>")
    assert result == r"{\c&H0600A9&\pos(1,2)}Pojawił {\c&HFEFDFE&}się latający przystojniak!"


def test_marked_text_leaves_a_range_opened_at_the_verse_start_unmarked() -> None:
    assert marked_text(r"{\i1}Why{\i0} are you here?") == "Why are you here?"


def test_marked_text_leaves_a_word_closed_before_punctuation_unmarked() -> None:
    assert marked_text(r"{\i1}Water{\i0}?") == "Water?"


def test_marked_text_leaves_a_range_opened_at_a_later_verse_start_unmarked() -> None:
    source: str = r"This scene is inspired by\N{\i1}Idiots Are Coming in Tanks{\i0} (1964)."
    assert marked_text(source) == "This scene is inspired by Idiots Are Coming in Tanks (1964)."


def test_replace_visible_text_keeps_a_verse_start_range_on_whole_words_without_markers() -> None:
    result: str = replace_visible_text(r"{\i1}Why{\i0} are you here?", "Czemu tu jesteś?")
    assert result == r"{\i1}Czemu{\i0} tu jesteś?"
