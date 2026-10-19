from anishift.services.subtitles.linebreak import split_for_layout
from anishift.text.gaps import CONJUNCTIONS


def test_complete_conjunction_list_loaded() -> None:
    assert len(CONJUNCTIONS) == 76
    for word in ("aczkolwiek", "aniżeli", "wszelako", "niżeli", "ilekroć"):
        assert word in CONJUNCTIONS


def test_split_for_layout_preserves_authored_displayed_line_count() -> None:
    verses = split_for_layout(
        "Odcinek 3: Życie z powrotem w domu",
        ("Episode 3", "Life Back at Home"),
    )
    assert verses == ("Odcinek 3:", "Życie z powrotem w domu")


def test_split_for_layout_prefers_semantic_boundary_over_source_ratio() -> None:
    verses = split_for_layout(
        "W następnym odcinku: Wodny mag rangi królewskiej",
        ("Next Time", "A King-Class Water Mage"),
    )
    assert verses == ("W następnym odcinku:", "Wodny mag rangi królewskiej")


def test_split_for_layout_keeps_one_source_verse_on_normal_policy() -> None:
    text = "To jest długie polskie zdanie, które powinno zostać czytelnie podzielone na ekranie"
    assert split_for_layout(text, ("One source line",)) == (
        "To jest długie polskie zdanie,",
        "które powinno zostać czytelnie podzielone na ekranie",
    )


def test_split_for_layout_does_not_break_one_target_word_artificially() -> None:
    assert split_for_layout("Dom", ("Home", "again")) == ("Dom",)


def test_split_for_layout_keeps_balanced_paragraph_balanced() -> None:
    source = (
        "This is a work of fiction.",
        "Underage drinking is strongly",
        "prohibited and illegal. We also",
        "do not encourage the forceful or",
        "excessive  consumption of alcohol,",
        "nor do we endorse the litany of",
        "depraved and shameful acts portrayed",
        "in the binge-drinking scenes. We ask",
        "that you view this as a comedy anime",
        "and  nothing more. Furthermore,",
        " all characters drinking in this work",
        "are of legal age. In keeping with",
        "the recent social climate, the black circles",
        "have been increased 5% in size from this season.",
    )
    target = (
        "To jest dzieło fikcyjne. Spożywanie alkoholu przez osoby niepełnoletnie "
        "jest surowo zabronione i nielegalne. Nie zachęcamy również do wymuszonego "
        "ani nadmiernego spożywania alkoholu, ani nie popieramy serii zepsutych i "
        "wstydliwych czynów przedstawionych w scenach opilstwa. Prosimy traktować "
        "to jako anime komediowe i nic więcej. Ponadto wszystkie postacie pijące w "
        "tym dziele są pełnoletnie. Zgodnie z obecnym klimatem społecznym, czarne "
        "kółka zostały powiększone o 5% w porównaniu z poprzednim sezonem."
    )
    verses = split_for_layout(target, source)
    assert len(verses) == len(source)
    assert max(len(verse) for verse in verses) <= 60
    assert all(" " in verse for verse in verses)
