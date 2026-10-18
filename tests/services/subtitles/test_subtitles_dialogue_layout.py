from __future__ import annotations

import pytest
from pysubs2 import SSAEvent

from anishift.services.subtitles.layout import LayoutLimits
from anishift.services.subtitles.linebreak import DialogueLayout, layout_dialogue, split_lines

_TRANSLATION = "Wczoraj widziałem ogromnego smoka daleko stąd."


@pytest.mark.unit
def test_layout_dialogue_breaks_a_new_translation_and_keeps_the_event_tags() -> None:
    event: SSAEvent = SSAEvent(text=r"{\an8}Yesterday I saw a dragon")

    layout: DialogueLayout = layout_dialogue(event, _TRANSLATION, None, LayoutLimits(max_chars=24))

    assert layout == DialogueLayout(r"{\an8}Wczoraj widziałem\Nogromnego smoka daleko stąd.", frozenset())


@pytest.mark.unit
def test_layout_dialogue_reflows_unchanged_text_without_moving_tags() -> None:
    event: SSAEvent = SSAEvent(text=r"Wczoraj {\i1}widziałem{\i0} ogromnego smoka daleko stąd.")

    layout: DialogueLayout = layout_dialogue(event, _TRANSLATION, None, LayoutLimits(max_chars=24))

    assert layout.text == r"Wczoraj {\i1}widziałem{\i0}\Nogromnego smoka daleko stąd."


@pytest.mark.unit
def test_layout_dialogue_restores_span_markers_into_the_new_lines() -> None:
    event: SSAEvent = SSAEvent(text=r"Why are you after {\i1}me{\i0}?!")

    layout: DialogueLayout = layout_dialogue(
        event, "Czemu uwziąłeś się akurat na <s1>mnie</s1>?!", None, LayoutLimits(max_chars=20)
    )

    assert layout.text == r"Czemu uwziąłeś się\Nakurat na {\i1}mnie{\i0}?!"


@pytest.mark.unit
def test_split_lines_follows_the_event_lines_and_returns_none_without_enough_words() -> None:
    two: SSAEvent = SSAEvent(text=r"Public\Nschool")
    one: SSAEvent = SSAEvent(text="One line")

    assert split_lines(two, "Publiczna szkoła", 2, None) == ("Publiczna", "szkoła")
    assert split_lines(two, "Dom", 2, None) is None
    assert split_lines(two, "  Publiczna   szkoła ", 1, None) == ("Publiczna szkoła",)
    assert split_lines(two, "Publiczna szkoła", 0, None) is None
    assert len(split_lines(one, "Jedna dwie trzy cztery", 2, None) or ()) == 2
