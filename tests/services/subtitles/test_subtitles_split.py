from pathlib import Path

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.services.subtitles.classifier import Category, StyleVerdict
from anishift.services.subtitles.service import inherit_split, split_subtitles, write_displayed
from anishift.services.subtitles.types import SubtitleSplit


def _event(text: str, *, style: str, start: int = 0) -> SSAEvent:
    return SSAEvent(start=start, end=start + 1000, style=style, text=text)


def _subs(events: list[SSAEvent]) -> SSAFile:
    subs = SSAFile()
    subs.events.extend(events)
    return subs


def test_split_subtitles_marks_lines_individually_and_preserves_source() -> None:
    subs = _subs([_event("{\\pos(1,2)}Hello", style="Dialog"), _event("Sign", style="Sign")])
    original = subs.events[0].text

    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})

    assert split.decisions == ("spoken", "displayed")
    assert split.spoken[0].text == "Hello"
    assert subs.events[0].text == original


def test_write_displayed_creates_new_tag_safe_file(tmp_path: Path) -> None:
    subs = _subs(
        [
            _event("{\\pos(1,2)}Sign", style="Sign"),
            _event("Narration", style="Dialog", start=1000),
        ]
    )
    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    dest = tmp_path / "source.displayed.ass"

    result = write_displayed(split, dest)

    assert result == dest
    content = dest.read_text(encoding="utf-8")
    assert "{\\pos(1,2)}Sign" in content


def test_split_subtitles_treats_srt_lines_as_spoken() -> None:
    split = split_subtitles(_subs([_event("<i>Hello</i>", style="Default")]), kind="srt")

    assert split.decisions == ("spoken",)
    assert split.spoken[0].text == "Hello"
    assert split.verdicts == ()


def test_split_srt_preserves_repeated_utterances() -> None:
    subs: SSAFile = _subs(
        [
            SSAEvent(start=0, end=500, text="No!"),
            SSAEvent(start=600, end=1100, text="No!"),
        ]
    )

    split = split_subtitles(subs, kind="srt")

    assert [(line.start, line.end, line.text, line.order) for line in split.spoken] == [
        (0, 500, "No!", 0),
        (600, 1100, "No!", 1),
    ]
    assert split.stats.collapsed_away == 0


def test_split_honors_explicit_empty_spoken_selection() -> None:
    subs: SSAFile = _subs([_event("Sign", style="Signs")])

    split = split_subtitles(subs, kind="ass", spoken_styles=())

    assert split.decisions == ("displayed",)
    assert split.spoken == ()
    assert split.stats.spoken_events == 0


@pytest.mark.unit
def test_split_reads_nothing_when_no_style_is_spoken() -> None:
    subs: SSAFile = _subs([_event("Sign", style="Signs"), _event("{\\k20}La {\\k20}la", style="Song", start=1000)])
    verdicts: tuple[StyleVerdict, ...] = (
        StyleVerdict("Signs", Category.SIGN, 1.0, 1, 1),
        StyleVerdict("Song", Category.SIGN, 0.95, 1, 1),
    )

    split = split_subtitles(subs, kind="ass", verdicts=verdicts)

    assert split.decisions == ("displayed", "displayed")
    assert split.spoken == ()
    assert split.stats.spoken_events == 0


def _named(text: str, *, style: str, actor: str, start: int = 0) -> SSAEvent:
    return SSAEvent(start=start, end=start + 1000, style=style, name=actor, text=text)


def _verdict(style: str, category: Category) -> StyleVerdict:
    return StyleVerdict(style, category, 0.5, 1, 1)


@pytest.mark.parametrize(
    "actor", ["SIGN", "sign", "Signs", "signtext", "SIGNSRtoL", "SIGNL", "TitleCard", "NEXTEPTITLE"]
)
def test_split_routes_sign_actor_on_dialogue_style_to_display(actor: str) -> None:
    subs: SSAFile = _subs(
        [_named("Hello there.", style="boxed", actor="IORI"), _named("Boobology", style="boxed", actor=actor)]
    )

    split: SubtitleSplit = split_subtitles(subs, kind="ass", verdicts=(_verdict("boxed", Category.DIALOG),))

    assert split.decisions == ("spoken", "displayed")
    assert [line.text for line in split.spoken] == ["Hello there."]


@pytest.mark.parametrize("actor", ["Preview", "Signe", "Sign Holder", "Text"])
def test_split_keeps_other_actors_on_dialogue_style_spoken(actor: str) -> None:
    subs: SSAFile = _subs([_named("Next time on the show.", style="Default", actor=actor)])

    split: SubtitleSplit = split_subtitles(subs, kind="ass", verdicts=(_verdict("Default", Category.DIALOG),))

    assert split.decisions == ("spoken",)


def test_split_routes_default_style_sign_actor_to_display_before_uncertain_resolution() -> None:
    subs: SSAFile = _subs(
        [
            _named("Has Azu always been such a worrywart?", style="Default", actor="SATO/ID"),
            _named("Instruction Academy", style="Default", actor="SIGN", start=1000),
        ]
    )

    split: SubtitleSplit = split_subtitles(subs, kind="ass", verdicts=(_verdict("Default", Category.UNCERTAIN),))

    assert split.decisions == ("spoken", "displayed")


@pytest.mark.parametrize(("style", "decision"), [("Default", "spoken"), ("Main", "spoken"), ("Black", "displayed")])
def test_split_resolves_uncertain_style_by_dialogue_name(style: str, decision: str) -> None:
    subs: SSAFile = _subs([_event("Club Activities", style=style), _event("Hi there.", style="Speech", start=1000)])
    verdicts: tuple[StyleVerdict, ...] = (_verdict(style, Category.UNCERTAIN), _verdict("Speech", Category.DIALOG))

    split: SubtitleSplit = split_subtitles(subs, kind="ass", verdicts=verdicts)

    assert split.decisions == (decision, "spoken")


def test_split_reads_second_subtitle_track_style_aloud() -> None:
    main: list[SSAEvent] = [
        _event(f"Main line number {index}.", style="Subtitle", start=index * 2000) for index in range(20)
    ]
    alt: list[SSAEvent] = [
        _event("Oh, you're stiff! So very stiff!", style="Subtitle-Alt", start=1000),
        _event("They're in the alley behind the theater.", style="Subtitle-Alt", start=3000),
    ]

    split: SubtitleSplit = split_subtitles(_subs(main + alt), kind="ass")

    assert split.decisions[-2:] == ("spoken", "spoken")
    assert {line.text for line in split.spoken} >= {
        "Oh, you're stiff! So very stiff!",
        "They're in the alley behind the theater.",
    }


@pytest.mark.parametrize("tag", [r"\an4", r"\an5", r"\an6"])
def test_split_routes_mid_frame_dialogue_line_to_display(tag: str) -> None:
    subs: SSAFile = _subs(
        [_event("Hello there.", style="Default"), _event(f"{{{tag}}}CHRISTMAS CAKE", style="Default")]
    )

    split: SubtitleSplit = split_subtitles(subs, kind="ass", verdicts=(_verdict("Default", Category.DIALOG),))

    assert split.decisions == ("spoken", "displayed")


def test_split_keeps_moving_top_shout_in_dialogue_style_spoken() -> None:
    lines: list[SSAEvent] = [
        _event(f"Line number {index}.", style="GJM_Main", start=index * 3000) for index in range(10)
    ]
    shout: list[SSAEvent] = [
        SSAEvent(
            start=40000 + frame * 42,
            end=40042 + frame * 42,
            style="GJM_Main",
            name="Chi",
            text=rf"{{\an8\move(960,{60 + frame},960,{62 + frame})}}Kaguya!",
        )
        for frame in range(19)
    ]

    split: SubtitleSplit = split_subtitles(_subs(lines + shout), kind="ass")

    assert split.decisions[-19:] == ("spoken",) * 19
    assert [line.text for line in split.spoken].count("Kaguya!") == 1


@pytest.mark.parametrize(
    ("style", "actor", "text", "decision"),
    [
        ("Furry", "SIGN", "Złamałbym ci serce, Asaka.", "spoken"),
        ("Furry", "sign", "Thanks.", "spoken"),
        ("Furry", "Sign", "How did we get into another dangerous situation again?", "spoken"),
        ("Furry", "sign", "Fresh Bread Angel", "displayed"),
        ("Furry", "Sign", r"{\pos(640,360)}What an awful name.", "displayed"),
        ("boxed", "SIGN", "Completely wrong! Re-submit!", "displayed"),
    ],
)
def test_split_sign_actor_keeps_plain_sentences_of_main_dialogue_style_spoken(
    style: str, actor: str, text: str, decision: str
) -> None:
    subs: SSAFile = _subs([_named("Hello there.", style="Furry", actor="MARI"), _named(text, style=style, actor=actor)])
    verdicts: tuple[StyleVerdict, ...] = (
        StyleVerdict("Furry", Category.DIALOG, 0.9, 200, 200),
        StyleVerdict("boxed", Category.DIALOG, 0.6, 12, 12),
    )

    split: SubtitleSplit = split_subtitles(subs, kind="ass", verdicts=verdicts)

    assert split.decisions == ("spoken", decision)


@pytest.mark.unit
def test_split_reads_short_lines_of_an_alt_style_aloud() -> None:
    main: list[SSAEvent] = [
        _event(f"Main line number {index}.", style="Default", start=index * 2000) for index in range(20)
    ]
    alt: list[SSAEvent] = [_event("Nooo!", style="Alt", start=1000), _event("Yo!", style="Alt", start=3000)]

    split: SubtitleSplit = split_subtitles(_subs(main + alt), kind="ass")

    assert split.decisions[-2:] == ("spoken", "spoken")


def _dialogue_file(line: str) -> SSAFile:
    subs: SSAFile = _subs([_event("Hello there.", style="Default"), _event(line, style="Default", start=2000)])
    subs.info["PlayResX"] = "1280"
    subs.info["PlayResY"] = "720"
    return subs


@pytest.mark.unit
@pytest.mark.parametrize(
    ("line", "decision"),
    [
        (r"{\an7}IRRITATED", "displayed"),
        (r"{\pos(640,360)}KAGUYA", "displayed"),
        (r"{\pos(640,690)}NO WAY", "displayed"),
        ("TWO GENIUSES' WAR OF LOVE", "displayed"),
        (r"{\an8}WATER-BASED - ALL PURPOSE PAINT", "displayed"),
        (r"{\pos(640,360)}Fresh Bread Angel", "displayed"),
        (r"{\an8}EEK", "spoken"),
        (r"{\an8}IRRITATED", "spoken"),
        ("Club Activities", "spoken"),
        (r"{\an9}THAT CAN'T POSSIBLY BE SEX!!", "spoken"),
        ("WAIT, NO", "spoken"),
        ("I DON'T THINK—", "spoken"),
        (r"{\frz0\pos(640,690)}Hey you", "spoken"),
    ],
)
def test_split_vetoes_capital_or_placed_title_labels_in_a_dialogue_style(line: str, decision: str) -> None:
    split: SubtitleSplit = split_subtitles(
        _dialogue_file(line), kind="ass", verdicts=(_verdict("Default", Category.DIALOG),)
    )

    assert split.decisions == ("spoken", decision)


@pytest.mark.unit
def test_split_reads_a_copy_of_a_line_in_another_style_once() -> None:
    subs: SSAFile = _subs(
        [
            _event("Right away!", style="Main"),
            _event(r"{\an8}Right away!", style="Overlap", start=200),
            _event("Next line.", style="Main", start=3000),
        ]
    )

    split: SubtitleSplit = split_subtitles(subs, kind="ass", spoken_styles={"Main", "Overlap"})

    assert split.decisions == ("spoken", "spoken", "spoken")
    assert [(line.order, line.start, line.end, line.text) for line in split.spoken] == [
        (0, 0, 1200, "Right away!"),
        (2, 3000, 4000, "Next line."),
    ]
    assert split.stats.collapsed_away == 1


@pytest.mark.unit
@pytest.mark.parametrize("echo_start", [300, 1200])
def test_split_reads_a_capital_echo_starting_together_or_right_after_the_line_once(echo_start: int) -> None:
    subs: SSAFile = _subs([_event("Yay!", style="Default"), _event("YAY", style="Default", start=echo_start)])

    split: SubtitleSplit = split_subtitles(subs, kind="ass", spoken_styles={"Default"})

    assert [line.text for line in split.spoken] == ["Yay!"]


@pytest.mark.unit
def test_split_reads_repeats_starting_inside_a_long_copy_again() -> None:
    subs: SSAFile = _subs(
        [
            SSAEvent(start=1600, end=3200, style="Main", text="Wahaha."),
            SSAEvent(start=3200, end=25100, style="Overlap", text=r"{\an8}Wahaha."),
            SSAEvent(start=15300, end=16700, style="Main", text="Wahaha."),
            SSAEvent(start=21600, end=23600, style="Main", text='"Wahaha"?'),
        ]
    )

    split: SubtitleSplit = split_subtitles(subs, kind="ass", spoken_styles={"Main", "Overlap"})

    assert [(line.order, line.text) for line in split.spoken] == [(0, "Wahaha."), (2, "Wahaha."), (3, '"Wahaha"?')]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("first", "second"),
    [
        (_event("Right away!", style="Main"), _event("Right away!", style="Overlap", start=1600)),
        (_event("Wahaha.", style="Main"), _event("Wahaha!", style="Main", start=1200)),
        (_event("Wait!", style="Main"), _event("Hold on!", style="Overlap", start=200)),
        (_event("Number one...", style="Main"), _event("NUMBER ONE", style="Main", start=660)),
    ],
)
def test_split_reads_distant_repeats_and_same_style_variants_twice(first: SSAEvent, second: SSAEvent) -> None:
    split: SubtitleSplit = split_subtitles(_subs([first, second]), kind="ass", spoken_styles={"Main", "Overlap"})

    assert [line.order for line in split.spoken] == [0, 1]


def _polish_copy(source: SSAFile, texts: list[str]) -> SSAFile:
    polish: SSAFile = SSAFile()
    polish.info = dict(source.info)
    for event, text in zip(source.events, texts, strict=True):
        copy: SSAEvent = event.copy()
        copy.text = text
        polish.events.append(copy)
    return polish


@pytest.mark.unit
def test_inherit_split_reads_the_lines_the_source_reads() -> None:
    source: SSAFile = _dialogue_file(r"{\an7}IRRITATED")
    polish: SSAFile = _polish_copy(source, ["Cześć.", r"{\an7}Wkurzony"])
    polish.events[0].style = "Default (dialog)"
    decided: SubtitleSplit = split_subtitles(source, kind="ass")

    inherited: SubtitleSplit | None = inherit_split(decided, polish)

    assert split_subtitles(polish, kind="ass").decisions == ("spoken", "spoken")
    assert inherited is not None
    assert inherited.decisions == decided.decisions == ("spoken", "displayed")
    assert inherited.subs is polish
    assert [line.text for line in inherited.spoken] == ["Cześć."]


@pytest.mark.unit
@pytest.mark.parametrize("change", ["end", "layer", "style", "count"])
def test_inherit_split_refuses_a_translation_whose_events_differ(change: str) -> None:
    source: SSAFile = _dialogue_file("Second line.")
    polish: SSAFile = _polish_copy(source, ["Cześć.", "Druga linia."])
    if change == "end":
        polish.events[1].end += 10
    elif change == "layer":
        polish.events[1].layer = 1
    elif change == "style":
        polish.events[1].style = "Sign"
    else:
        polish.events.pop()

    assert inherit_split(split_subtitles(source, kind="ass"), polish) is None
