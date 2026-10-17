from pathlib import Path

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.services.subtitles.classifier import Category, StyleVerdict
from anishift.services.subtitles.service import split_subtitles, write_displayed
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


def test_split_retains_automatic_fallback_when_styles_are_not_selected() -> None:
    subs: SSAFile = _subs([_event("Sign", style="Signs")])
    verdicts: tuple[StyleVerdict, ...] = (StyleVerdict("Signs", Category.SIGN, 1.0, 1, 1),)

    split = split_subtitles(subs, kind="ass", verdicts=verdicts)

    assert split.decisions == ("spoken",)


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
