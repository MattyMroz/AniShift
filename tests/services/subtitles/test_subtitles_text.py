import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final

import pysubs2
import pytest
from pysubs2 import SSAStyle

from anishift.services.subtitles.text import (
    is_drawing,
    marked_text,
    reflow_visible_text,
    replace_visible_text,
    restore_markers,
    visible_text,
    visible_verses,
)

_STYLE_EXPERIMENT: Final[Path] = (
    Path(__file__).resolve().parents[3] / "workspace" / ".quality" / "experiments" / "styles"
)


@dataclass(frozen=True, slots=True)
class _SavedRun:
    examples: tuple[tuple[str, str], ...]
    events: tuple[tuple[str, SSAStyle | None], ...]


@cache
def _load_saved_runs() -> tuple[_SavedRun, ...]:
    runs: list[_SavedRun] = []
    for path in sorted((_STYLE_EXPERIMENT / "runs").glob("*.json")):
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        source: Path = _STYLE_EXPERIMENT / "pairs" / data["episode"] / "source.en.ass"
        subs: pysubs2.SSAFile = pysubs2.load(str(source), encoding="utf-8")
        examples: list[list[str]] = data["marked_examples"]
        events: tuple[tuple[str, SSAStyle | None], ...] = tuple(
            (event.text, subs.styles.get(event.style)) for event in subs.events if event.type == "Dialogue"
        )
        runs.append(_SavedRun(tuple(dict.fromkeys((english, polish) for english, polish in examples)), events))
    return tuple(runs)


def _saved_runs() -> tuple[_SavedRun, ...]:
    runs: tuple[_SavedRun, ...] = _load_saved_runs()
    if not runs:
        pytest.skip("saved LLM style runs are not available")
    return runs


def _saved_sources(english: str) -> list[tuple[str, SSAStyle | None, str]]:
    return [
        (raw, style, polish)
        for run in _saved_runs()
        for marked, polish in run.examples
        if marked == english
        for raw, style in run.events
        if marked_text(raw, style) == english
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"{\i1}Pierwszy\Ndrugi{\i0} trzeci czwarty", r"{\i1}Pierwszy drugi{\i0}\Ntrzeci czwarty"),
        (r"Pierwszy {\b1}drugi{\b0} trzeci czwarty", r"Pierwszy {\b1}drugi{\b0}\Ntrzeci czwarty"),
        (r"Pierwszy\hdrugi trzeci czwarty", r"Pierwszy\hdrugi\Ntrzeci czwarty"),
        (r"Pierwszy drugi\h\Ntrzeci czwarty", r"Pierwszy drugi\h\Ntrzeci czwarty"),
        (r"Pierwszy drugi\h trzeci czwarty", r"Pierwszy drugi\h\Ntrzeci czwarty"),
    ],
)
def test_reflow_moves_only_breaks_and_keeps_exact_style_spans(source: str, expected: str) -> None:
    assert reflow_visible_text(source, ("Pierwszy drugi", "trzeci czwarty")) == expected


@pytest.mark.unit
def test_reflow_keeps_a_drawing_unchanged() -> None:
    source: str = r"{\p1}m 0 0 l 10 10"
    assert reflow_visible_text(source, ("m 0 0", "l 10 10")) == source


@pytest.mark.unit
def test_visible_text_can_preserve_nonbreaking_spaces_for_reflow() -> None:
    assert visible_text(r"{\i1}Jan\hKowalski\Nwrócił.", preserve_hard_spaces=True) == "Jan\u00a0Kowalski wrócił."


@pytest.mark.unit
@pytest.mark.parametrize("space", ["\u00a0", "\u202f"])
def test_reflow_preserves_literal_nonbreaking_space(space: str) -> None:
    text: str = f"Jan{space}Kowalski wrócił do domu."
    assert (
        reflow_visible_text(text, (f"Jan{space}Kowalski", "wrócił do domu.")) == f"Jan{space}Kowalski\\Nwrócił do domu."
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "style", "expected"),
    [
        (r"For {\i0}you{\i1} to call them,", SSAStyle(italic=True), "For <s1>you</s1> to call them,"),
        (r"How {\i0}weak{\i1}.", SSAStyle(italic=True), "How <s1>weak</s1>."),
        (r"Not {\b0}this{\b1} one", SSAStyle(bold=True), "Not <s1>this</s1> one"),
    ],
)
def test_marked_text_wraps_a_word_negating_the_style_emphasis(source: str, style: SSAStyle, expected: str) -> None:
    assert marked_text(source, style) == expected


@pytest.mark.unit
@pytest.mark.parametrize("style", [None, SSAStyle()])
def test_marked_text_leaves_a_switch_off_unmarked_when_the_style_lacks_the_emphasis(style: SSAStyle | None) -> None:
    assert marked_text(r"How {\i0}weak{\i1}.", style) == "How weak."


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            r"{\i1}I {\i0}may{\i1} consider molding him\N into a man worthy of me.",
            "I <s1>may</s1> consider molding him into a man worthy of me.",
        ),
        (
            r"{\i1}Have I really no choice but to use {\i0}that{\i1}?",
            "Have I really no choice but to use <s1>that</s1>?",
        ),
    ],
)
def test_marked_text_wraps_a_word_negating_emphasis_held_from_the_first_to_the_last_grapheme(
    source: str, expected: str
) -> None:
    assert marked_text(source, SSAStyle(bold=True)) == expected


@pytest.mark.unit
def test_marked_text_leaves_emphasis_opened_at_the_line_start_and_closed_mid_line_unmarked() -> None:
    source: str = r"{\i1}You're{\i0} society's darker side!"
    assert marked_text(source, SSAStyle(bold=True)) == "You're society's darker side!"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"Kaguya{**-san}, let's go home together!", "Kaguya, let's go home together!"),
        (r"{*}Mistress Kaguya{*Kaguya-sama}, please!", "Mistress Kaguya, please!"),
    ],
)
def test_marked_text_ignores_comment_blocks(source: str, expected: str) -> None:
    assert marked_text(source) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            r"It means that you actually {\i1}do{\i0} like him, Kashiwagi{**-san}.",
            "It means that you actually <s1>do</s1> like him, Kashiwagi.",
        ),
        (r"Kashi{*}wagi is {\i1}here{\i0} now", "Kashiwagi is <s1>here</s1> now"),
    ],
)
def test_marked_text_marks_a_range_next_to_a_comment_block(source: str, expected: str) -> None:
    assert marked_text(source) == expected


@pytest.mark.unit
@pytest.mark.parametrize("source", [r"The {*note}{\c&H0000FF&}Red{\c&HFFFFFF&} Sword", "The <i>Red</i> Sword"])
def test_marked_text_keeps_command_blocks_and_srt_tags_as_range_boundaries(source: str) -> None:
    assert marked_text(source) == "The <s1>Red</s1> Sword"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "translation", "style", "expected"),
    [
        (
            r"{\i1}I {\i0}may{\i1} consider it.",
            "Rozważę to, <s1>być może</s1>.",
            SSAStyle(bold=True),
            r"{\i1}Rozważę to, {\i0}być może{\i1}.",
        ),
        (
            r"For {\i0}you{\i1} to call them excellent,",
            "Że nazywasz je wspaniałymi właśnie <s1>ty</s1>,",
            SSAStyle(italic=True),
            r"Że nazywasz je wspaniałymi właśnie {\i0}ty{\i1},",
        ),
        (
            r"It means that you actually {\i1}do{\i0} like him, Kashiwagi{**-san}.",
            "To znaczy, że naprawdę go <s1>lubisz</s1>, Kashiwagi.",
            None,
            r"To znaczy, że naprawdę go {\i1}lubisz{\i0}, Kashiwagi{**-san}.",
        ),
    ],
)
def test_replace_visible_text_places_the_range_on_the_marked_word_after_reordering(
    source: str, translation: str, style: SSAStyle | None, expected: str
) -> None:
    assert replace_visible_text(source, translation, style) == expected


@pytest.mark.integration
def test_marked_text_reproduces_every_marked_line_of_the_saved_llm_runs() -> None:
    runs: tuple[_SavedRun, ...] = _saved_runs()
    missing: list[str] = [
        english
        for run in runs
        for english, _ in run.examples
        if all(marked_text(raw, style) != english for raw, style in run.events)
    ]
    assert sum(len(run.examples) for run in runs) >= 12
    assert missing == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "english",
    [
        "Look at all these people in <s1>yukata</s1>.",
        "Do you ever wear <s1>yukata</s1>, Minato?",
        "Why, why, why, <s1>why</s1>?!",
        "How <s1>weak</s1>.",
        "No, you <s1>didn't</s1>!",
        "Episode <s1>15</s1>",
        "EP 2 <s1>Death Games and Demons</s1>",
        "Fresh Bread <s1>Angel</s1>",
        "Wait a minute! Why are you after <s1>me</s1>?!",
        "So... Why are we here, wearing these, and doing whatever <s1>this</s1> is?",
    ],
)
def test_replace_visible_text_puts_the_range_on_the_words_marked_in_a_saved_llm_run(english: str) -> None:
    sources: list[tuple[str, SSAStyle | None, str]] = _saved_sources(english)
    assert sources
    for raw, style, polish in sources:
        assert marked_text(replace_visible_text(raw, polish, style), style) == polish


@pytest.mark.integration
def test_replace_visible_text_opens_a_saved_llm_range_at_the_translated_line_start() -> None:
    [(raw, style, polish)] = _saved_sources("I <s1>do</s1> want her to regain them!")
    assert replace_visible_text(raw, polish, style) == r"{\i1}Chcę{\i0}, żeby je odzyskała!"
