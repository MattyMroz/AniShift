"""Evidence for a line break between neighbouring words of Polish text: class, rules, turns and quotations."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.text.boundaries import CJK_SENTENCE_ENDINGS, CLOSING_MARKS, SENTENCE_ENDINGS, is_false_sentence_break

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "CONJUNCTIONS",
    "CONJUNCTIONS_MULTIWORD",
    "PREPOSITIONS",
    "PREPOSITIONS_MULTIWORD",
    "PROTECTED_KINDS",
    "TIERS",
    "Gap",
    "GapKind",
    "gaps",
    "list_markers",
    "quote_spans",
    "word_core",
]


class GapKind(StrEnum):
    """Boundary class of the gap between two words."""

    SENTENCE = "sentence"
    CLAUSE = "clause"
    ELLIPSIS = "ellipsis"
    PARENTHETICAL = "parenthetical"
    DASH = "dash"
    BEFORE_SUBORDINATOR = "before_subordinator"
    BEFORE_COORDINATOR = "before_coordinator"
    BEFORE_PREPOSITION = "before_preposition"
    PHRASE = "phrase"
    AUXILIARY = "auxiliary"
    MODIFIER = "modifier"
    ABBREVIATION = "abbreviation"
    AFTER_OPENER = "after_opener"
    NAME = "name"
    AFTER_PREPOSITION = "after_preposition"
    NEGATION = "negation"
    REFLEXIVE = "reflexive"
    NUMBER = "number"
    IDIOM = "idiom"
    AFTER_SINGLE_LETTER = "after_single_letter"


@dataclass(frozen=True, slots=True)
class Gap:
    """Evidence for a line break between two neighbouring words."""

    kind: GapKind
    banned: bool
    protected: bool
    turn: bool


# ── Constants ─────────────────────────────────────────────────────────────────

TIERS: Final[Mapping[GapKind, int]] = MappingProxyType(
    {
        GapKind.SENTENCE: 0,
        GapKind.CLAUSE: 1, GapKind.ELLIPSIS: 1, GapKind.PARENTHETICAL: 1, GapKind.DASH: 1,
        GapKind.BEFORE_SUBORDINATOR: 2, GapKind.BEFORE_COORDINATOR: 2,
        GapKind.BEFORE_PREPOSITION: 3, GapKind.PHRASE: 3,
        GapKind.AUXILIARY: 4, GapKind.MODIFIER: 4, GapKind.ABBREVIATION: 4, GapKind.AFTER_OPENER: 4,
        GapKind.NAME: 5, GapKind.AFTER_PREPOSITION: 5, GapKind.NEGATION: 5, GapKind.REFLEXIVE: 5,
        GapKind.NUMBER: 5, GapKind.IDIOM: 5,
        GapKind.AFTER_SINGLE_LETTER: 6,
    }
)  # fmt: skip
"""Rank of the harm of a cut in each class, from the sentence end up (text-layout spec §4.2); never cheaper upwards."""

_PROTECTED_TIER: Final[int] = TIERS[GapKind.NAME]
"""Lowest tier of a bound pair: every class from it up is protected."""

PROTECTED_KINDS: Final[frozenset[GapKind]] = frozenset(kind for kind, tier in TIERS.items() if tier >= _PROTECTED_TIER)
"""Classes of a bound pair (text-layout spec §4.2) a line is cut inside only in rescue."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_spójniki
CONJUNCTIONS: Final[frozenset[str]] = frozenset(
    {
        "a", "aby", "aczkolwiek", "albo", "albowiem", "ale", "ani", "aniżeli", "atoli", "aż", "ażeby", "bądź", "bo",
        "bodaj", "bowiem", "by", "byle", "choć", "chociaż", "choćby", "czy", "czyli", "dlatego", "dopóki", "dopóty",
        "dotąd", "gdy", "gdyby", "gdyż", "i", "ile", "ilekroć", "im", "iż", "jak", "jakby", "jakkolwiek", "jako",
        "jakoby", "jednak", "jednakże", "jeśli", "jeżeli", "kiedy", "lecz", "ledwie", "ledwo", "lub", "mianowicie",
        "minus", "natomiast", "niby", "niczym", "niemniej", "nim", "niż", "niżeli", "oraz", "plus", "ponieważ", "póki",
        "póty", "przeto", "skoro", "toteż", "tudzież", "tylko", "więc", "wprawdzie", "wszelako", "zanim", "zarówno",
        "zaś", "zatem", "że", "żeby",
    }
)  # fmt: skip
"""All single-word Polish conjunctions."""

_COORDINATORS: Final[frozenset[str]] = frozenset(
    {
        "a", "albo", "ale", "ani", "atoli", "bądź", "czy", "czyli", "dlatego", "i", "jednak", "jednakże", "lecz",
        "lub", "mianowicie", "minus", "natomiast", "niemniej", "oraz", "plus", "przeto", "toteż", "tudzież", "tylko",
        "więc", "wszelako", "zarówno", "zatem", "zaś",
    }
)  # fmt: skip
"""Coordinating conjunctions, which join words or clauses of equal rank.

Source: https://pl.wikipedia.org/wiki/Spójnik_(część_mowy) (copulative, disjunctive, adversative, consecutive and
explanatory); ``czy`` counts as coordinating, since without a parser an indirect question is not told apart.
"""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_spójniki
CONJUNCTIONS_MULTIWORD: Final[frozenset[tuple[str, ...]]] = frozenset(
    {
        ("a", "co", "więcej"), ("a", "również"), ("a", "także"), ("a", "w", "szczególności"), ("a", "zwłaszcza"),
        ("ale", "również"), ("ale", "też"), ("chyba", "że"), ("co", "gorsza"), ("dlatego", "że"), ("gdy", "tylko"),
        ("jak", "gdyby"), ("jak", "i"), ("jako", "że"), ("mimo", "to"), ("mimo", "że"), ("niemniej", "jednak"),
        ("o", "ile"), ("oprócz", "tego"), ("po", "czym"), ("podczas", "gdy"), ("poza", "tym"), ("przy", "czym"),
        ("przy", "tym"), ("to", "jest"), ("to", "znaczy"), ("w", "przeciwnym", "razie"), ("w", "sensie"),
        ("w", "takim", "razie"), ("w", "związku", "z", "czym"), ("wobec", "tego"), ("z", "tego", "powodu"),
        ("z", "tym", "że"), ("za", "to"), ("żeby", "tylko"),
    }
)  # fmt: skip
"""Multi-word Polish conjunctions."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_przyimki
PREPOSITIONS: Final[frozenset[str]] = frozenset(
    {
        "bez", "beze", "dla", "do", "ku", "między", "na", "nad", "nade", "o", "od", "ode",
        "po", "pod", "pode", "przed", "przede", "przez", "przeze", "przy", "u", "w", "we", "z", "za", "ze",
        "według", "wśród", "obok", "zza", "spod", "poza", "wobec", "podczas", "około", "ponad", "pomiędzy",
    }
)  # fmt: skip
"""Simple prepositions (with phonetic variants) never detached from their noun."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_przyimki
PREPOSITIONS_MULTIWORD: Final[frozenset[tuple[str, ...]]] = frozenset(
    {
        ("aż", "do"), ("bez", "względu", "na"), ("na", "czele"), ("na", "korzyść"), ("na", "podstawie"),
        ("na", "przekór"), ("na", "rzecz"), ("na", "skutek"), ("na", "temat"), ("na", "tle"), ("na", "wzór"),
        ("na", "zewnątrz"), ("o", "włos", "od"), ("odnośnie", "do"), ("począwszy", "od"), ("pod", "kątem"),
        ("pod", "względem"), ("przy", "pomocy"), ("przy", "użyciu"), ("w", "celu"), ("w", "ciągu"), ("w", "czasie"),
        ("w", "imieniu"), ("w", "imię"), ("w", "miarę"), ("w", "obliczu"), ("w", "obrębie"),
        ("w", "odniesieniu", "do"), ("w", "oparciu", "o"), ("w", "porównaniu", "z"), ("w", "przeciwieństwie", "do"),
        ("w", "ramach"), ("w", "razie"), ("w", "sprawie"), ("w", "stosunku", "do"), ("w", "wyniku"),
        ("w", "zależności", "od"), ("w", "związku", "z"), ("w", "ślad", "za"), ("z", "okazji"), ("z", "powodu"),
        ("z", "punktu", "widzenia"), ("z", "uwagi", "na"), ("z", "wyjątkiem"), ("z", "wyłączeniem"),
        ("za", "pomocą"), ("za", "pośrednictwem"), ("za", "sprawą"), ("ze", "strony"), ("ze", "względu", "na"),
    }
)  # fmt: skip
"""Multi-word Polish prepositions."""

# source: anishift/text/idioms.txt (Wikisłownik phrase categories listed in its header)
_IDIOMS: Final[frozenset[tuple[str, ...]]] = (
    frozenset(
        tuple(line.split(" "))
        for line in Path(__file__).with_name("idioms.txt").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    | CONJUNCTIONS_MULTIWORD
)
"""Fixed adverbial and particle phrases and multi-word conjunctions, never broken inside."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_zaimki_względne
_RELATIVES: Final[frozenset[str]] = frozenset(
    {"który", "która", "które", "którzy", "którego", "której", "któremu", "którym", "którą", "których", "którymi"}
)
"""Relative pronouns opening a subordinate clause, never left at the end of a line."""

_SUBORDINATORS: Final[frozenset[str]] = (CONJUNCTIONS - _COORDINATORS) | _RELATIVES | {"gdzie"}
"""Subordinating conjunctions and relative words, which open a dependent clause."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_zaimki_wskazujące, ..._dzierżawcze
_DETERMINERS: Final[frozenset[str]] = frozenset(
    {
        "ten", "ta", "to", "te", "tego", "tej", "temu", "tym", "tych", "tą", "tę", "tamten", "tamta", "tamto",
        "tamte", "tamtego", "tamtej", "tamtym", "tamtych", "tamtą", "tamtę", "taki", "taka", "takie", "takiego",
        "takiej", "takim", "takich", "taką", "mój", "moja", "moje", "mojego", "mojej", "moim", "moją", "moich",
        "twój", "twoja", "twoje", "twojego", "twojej", "twoim", "twoją", "twoich", "swój", "swoja", "swoje",
        "swojego", "swojej", "swoim", "swoją", "swoich", "nasz", "nasza", "nasze", "naszego", "naszej", "naszym",
        "naszą", "naszych", "wasz", "wasza", "wasze", "waszego", "waszej", "waszym", "waszą", "waszych", "każdy",
        "każda", "każde", "każdego", "każdej", "każdym", "każdą", "jakiś", "jakaś", "jakieś", "jakiegoś", "jakiejś",
        "jakimś", "jakąś", "jakichś", "jakimiś",
    }
)  # fmt: skip
"""Demonstrative, possessive and indefinite determiners with their inflected forms, kept with their noun."""

_AUXILIARIES: Final[frozenset[str]] = frozenset(
    {
        "będę", "będziesz", "będzie", "będziemy", "będziecie", "będą", "był", "była", "było", "byli", "były",
        "jestem", "jesteś", "jest", "jesteśmy", "jesteście", "są", "musi", "muszę", "musisz", "musimy", "musicie",
        "muszą", "mogę", "możesz", "może", "możemy", "możecie", "mogą", "mógł", "mogła", "mogli", "powinien",
        "powinna", "powinno", "powinni", "powinny", "chciał", "chciała", "chcę", "chcesz", "chce",
        "byłem", "byłam", "byłeś", "byłaś", "byliśmy", "byłyśmy", "byliście", "byłby", "byłaby", "byłoby", "byłbym",
        "byłabym", "byłbyś", "byłabyś", "byliby", "byłyby", "bym", "byś", "byśmy", "byście", "musiał", "musiała",
        "musiało", "musieli", "musiały", "musiałem", "musiałam", "musiałeś", "musiałaś", "musieliśmy", "musiałby",
        "musiałaby", "musiałbym", "musiałabym", "musiałbyś", "musiałabyś", "mogło", "mogły", "mogłem", "mogłam",
        "mogłeś", "mogłaś", "mogliśmy", "mógłby", "mogłaby", "mogłoby", "mógłbym", "mogłabym", "mógłbyś",
        "mogłabyś", "moglibyśmy", "mogliby", "mogłyby", "powinienem", "powinnam", "powinieneś", "powinnaś",
        "powinniśmy", "powinnyśmy", "powinniście", "chcemy", "chcecie", "chcą", "chciało", "chcieli", "chciały",
        "chciałem", "chciałam", "chciałeś", "chciałaś", "chcieliśmy", "chciałby", "chciałaby", "chciałbym",
        "chciałabym", "chciałbyś", "chciałabyś", "chcieliby",
    }
)  # fmt: skip
"""Forms of the auxiliary ``być`` and of the modal verbs, kept with the predicate they open."""

_TITLES: Final[frozenset[str]] = frozenset(
    {"dr", "mgr", "prof", "pan", "pani", "panie", "panno", "profesor", "doktor", "kapitan", "król"}
)
"""Titles and undotted abbreviations kept with the name that follows."""

_ADJECTIVE_ENDINGS: Final[tuple[str, ...]] = ("ego", "emu", "ych", "ymi", "ym", "ny", "na", "ne", "ry", "ra", "re")
"""Conservative surface hints for an attributive adjective, without a morphological parser."""

_REFLEXIVE: Final[str] = "się"
"""Reflexive particle never starting a line and kept with the words after it until a new phrase."""

_NEGATION: Final[str] = "nie"
"""Negation particle bound to the verb after it."""

_DASHES: Final[frozenset[str]] = frozenset({"-", "–", "—"})
"""Dash characters a speaker turn starts with."""

_ASIDE_DASHES: Final[frozenset[str]] = frozenset({"–", "—"})
"""Dash characters a pair of which encloses an aside; a hyphen never does."""

_ELLIPSES: Final[tuple[str, ...]] = ("…", "...")
"""Ellipsis written as one character or three dots."""

_CLAUSE_MARKS: Final[str] = ",;:"
"""Marks closing a clause inside a sentence."""

_FULL_STOP: Final[str] = "."
"""Dot that ends a sentence unless it closes an abbreviation."""

_STRONG_MARKS: Final[str] = "!?" + CJK_SENTENCE_ENDINGS
"""Marks that always end a sentence."""

_LEADING_BANNED: Final[str] = CLOSING_MARKS + ".,;:!?…"
"""Characters a token made of nothing else never starts a line with."""

_OPENING_CATEGORIES: Final[frozenset[str]] = frozenset({"Ps", "Pi"})
"""Unicode categories of opening brackets and quotes, which never end a line."""

_SUBORDINATING_PHRASES: Final[frozenset[tuple[str, ...]]] = frozenset(
    {
        ("chyba", "że"), ("dlatego", "że"), ("gdy", "tylko"), ("jak", "gdyby"), ("jako", "że"), ("mimo", "że"),
        ("o", "ile"), ("podczas", "gdy"), ("z", "tym", "że"), ("żeby", "tylko"),
    }
)  # fmt: skip
"""Multi-word conjunctions opening a dependent clause; the other ones in ``CONJUNCTIONS_MULTIWORD`` coordinate."""

_PHRASE_OPENERS: Final[frozenset[str]] = _SUBORDINATORS | _COORDINATORS | PREPOSITIONS
"""Words recognised as opening a new phrase, after which a reflexive ``się`` may end a line."""

_MAX_PHRASE_WORDS: Final[int] = 4
"""Longest multi-word phrase looked up (``w związku z czym``)."""

_RE_NUMBER: Final[re.Pattern[str]] = re.compile(r"\d+(?:[.,:–-]\d+)*")
"""Number with optional decimal, time or range separators."""

_RE_THOUSANDS_HEAD: Final[re.Pattern[str]] = re.compile(r"\d{1,3}")
"""Leading group of a number written with a space as the thousands separator (``10`` in ``10 000``)."""

_RE_THOUSANDS_TAIL: Final[re.Pattern[str]] = re.compile(r"\d{3}(?!\d)")
"""Group of three digits continuing a number after a thousands separator."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_liczebniki_główne (inflected forms)
_NUMERALS: Final[frozenset[str]] = frozenset(
    {
        "jeden", "jedna", "jedno", "jednego", "jednej", "jednemu", "jednym", "jedną", "dwa", "dwie", "dwóch", "dwu",
        "dwom", "dwoma", "dwiema", "trzy", "trzech", "trzem", "trzema", "cztery", "czterech", "czterem", "czterema",
        "pięć", "sześć", "siedem", "osiem", "dziewięć", "dziesięć", "pięciu", "sześciu", "siedmiu", "ośmiu",
        "dziewięciu", "dziesięciu", "pięcioma", "sześcioma", "siedmioma", "ośmioma", "dziewięcioma", "dziesięcioma",
        "jedenaście", "dwanaście", "trzynaście", "czternaście", "piętnaście", "szesnaście", "siedemnaście",
        "osiemnaście", "dziewiętnaście", "jedenastu", "dwunastu", "trzynastu", "czternastu", "piętnastu",
        "szesnastu", "siedemnastu", "osiemnastu", "dziewiętnastu", "dwadzieścia", "trzydzieści", "czterdzieści",
        "pięćdziesiąt", "sześćdziesiąt", "siedemdziesiąt", "osiemdziesiąt", "dziewięćdziesiąt", "dwudziestu",
        "trzydziestu", "czterdziestu", "pięćdziesięciu", "sześćdziesięciu", "siedemdziesięciu", "osiemdziesięciu",
        "dziewięćdziesięciu", "sto", "stu", "dwieście", "dwustu", "trzysta", "trzystu", "czterysta", "czterystu",
        "pięćset", "sześćset", "siedemset", "osiemset", "dziewięćset", "pięciuset", "sześciuset", "siedmiuset",
        "ośmiuset", "dziewięciuset", "tysiąc", "tysiąca", "tysiące", "tysięcy", "milion", "miliona", "miliony",
        "milionów", "miliard", "miliarda", "miliardy", "miliardów",
    }
)  # fmt: skip
"""Polish cardinal numerals with their common inflected forms, kept with the word they count."""

_RE_STUTTER: Final[re.Pattern[str]] = re.compile(r"(\w)-(\1\w+)")
"""Stuttered word (``n-nie``): the repeated letter, a hyphen and the whole word."""

_OPENING_QUOTES: Final[str] = '„“«"'
"""Quotation marks that open a quotation at the start of a word."""

_CLOSING_QUOTES: Final[str] = '”“»"'
"""Quotation marks that close a quotation at the end of a word, before any trailing punctuation."""

_TRAILING_MARKS: Final[str] = ".,;:!?…"
"""Punctuation that may follow a closing quotation mark."""

_RE_LIST_MARKER: Final[re.Pattern[str]] = re.compile(r"\(\d+\)")
"""Marker of a numbered list item, such as ``(1)``."""


def gaps(words: Sequence[str]) -> tuple[Gap, ...]:
    """Return the evidence for every gap between neighbouring ``words``: entry ``i`` precedes word ``i + 1``."""
    speakers: frozenset[int] = _speaker_marks(words)
    paired: frozenset[int] = _paired_dashes(words, speakers)
    return tuple(_gap(words, index, speakers, paired) for index in range(1, len(words)))


def quote_spans(words: Sequence[str]) -> tuple[tuple[int, int], ...]:
    """Return the first and last word index of every quotation spanning more than one word."""
    spans: list[tuple[int, int]] = []
    opened: int | None = None
    for index, word in enumerate(words):
        if opened is None and word[:1] in _OPENING_QUOTES:
            opened = index
        if opened is not None and word.rstrip(_TRAILING_MARKS)[-1:] in _CLOSING_QUOTES and len(word) > 1:
            if index > opened:
                spans.append((opened, index))
            opened = None
    return tuple(spans)


def list_markers(words: Sequence[str]) -> tuple[int, ...]:
    """Return the index of every word that marks a numbered list item."""
    return tuple(index for index, word in enumerate(words) if _RE_LIST_MARKER.fullmatch(word))


def word_core(word: str) -> str:
    """Return ``word`` without surrounding punctuation, casefolded, with a stutter reduced to the word it repeats."""
    start: int = 0
    end: int = len(word)
    while start < end and unicodedata.category(word[start]).startswith("P"):
        start += 1
    while end > start and unicodedata.category(word[end - 1]).startswith("P"):
        end -= 1
    core: str = word[start:end].casefold()
    stutter: re.Match[str] | None = _RE_STUTTER.fullmatch(core)
    return core if stutter is None else stutter.group(2)


def _gap(words: Sequence[str], index: int, speakers: frozenset[int], paired: frozenset[int]) -> Gap:
    previous: str = words[index - 1]
    following: str = words[index]
    turn: bool = index in speakers
    kind: GapKind = _punctuation_kind(words, index, speakers, paired) or _word_kind(words, index)
    banned: bool = not turn and (
        unicodedata.category(previous[-1]) in _OPENING_CATEGORIES
        or all(character in _LEADING_BANNED for character in following)
        or following[0] in _DASHES
        or (previous in _DASHES and index - 1 in speakers)
    )
    return Gap(kind=kind, banned=banned, protected=not turn and kind in PROTECTED_KINDS, turn=turn)


def _speaker_marks(words: Sequence[str]) -> frozenset[int]:
    marks: set[int] = set()
    for index, word in enumerate(words):
        if word[:1] not in _DASHES or (index > 0 and not _ends_sentence(words[index - 1])):
            continue
        if (len(word) == 1 and index + 1 < len(words)) or word[1:2].isalpha():
            marks.add(index)
    if 0 not in marks:
        return frozenset(marks)
    opener: str = words[0][0]
    asides: frozenset[int] = _paired_dashes(words, frozenset(marks))
    marks.update(
        index
        for index, word in enumerate(words[1:-1], 1)
        if word == opener and index not in asides and words[index + 1][:1].isupper()
    )
    return frozenset(marks)


def _paired_dashes(words: Sequence[str], speakers: frozenset[int]) -> frozenset[int]:
    paired: set[int] = set()
    opened: int | None = None
    for index, word in enumerate(words):
        if word in _ASIDE_DASHES and index not in speakers:
            if opened is None:
                opened = index
            else:
                paired.update({opened, index})
                opened = None
        elif _ends_sentence(word):
            opened = None
    return frozenset(paired)


def _punctuation_kind(
    words: Sequence[str], index: int, speakers: frozenset[int], paired: frozenset[int]
) -> GapKind | None:
    previous: str = words[index - 1]
    if previous in _DASHES and index - 1 not in speakers:
        return GapKind.PARENTHETICAL if index - 1 in paired else GapKind.DASH
    tail: str = _tail(previous)
    if tail.endswith(_ELLIPSES):
        return GapKind.ELLIPSIS
    if tail[-1:] and tail[-1] in _STRONG_MARKS:
        return GapKind.SENTENCE
    if tail.endswith(_FULL_STOP) and not is_false_sentence_break(tail, words[index]):
        return GapKind.SENTENCE
    if tail[-1:] and tail[-1] in _CLAUSE_MARKS:
        return GapKind.CLAUSE
    return None


def _word_kind(words: Sequence[str], index: int) -> GapKind:
    return _bound_kind(words, index) or _weighted_kind(words, index)


def _bound_kind(words: Sequence[str], index: int) -> GapKind | None:  # noqa: PLR0911 - one return per class
    previous: str = word_core(words[index - 1])
    following: str = word_core(words[index])
    if previous in PREPOSITIONS or _inside(words, index, PREPOSITIONS_MULTIWORD):
        return GapKind.AFTER_PREPOSITION
    if previous == _NEGATION and word_core(_earlier(words, index)) not in PREPOSITIONS:
        return GapKind.NEGATION
    if _reflexive(words, index):
        return GapKind.REFLEXIVE
    if _counts(previous, following):
        return GapKind.NUMBER
    if _tail(words[index - 1]).endswith(_FULL_STOP):
        return GapKind.ABBREVIATION
    if _capitalised(words[index]) and (_capitalised(words[index - 1]) or previous in _TITLES):
        return GapKind.NAME
    if _inside(words, index, _IDIOMS):
        return GapKind.IDIOM
    if previous in CONJUNCTIONS or previous in _RELATIVES:
        return GapKind.AFTER_OPENER
    if len(previous) == 1 and previous.isalpha():
        return GapKind.AFTER_SINGLE_LETTER
    return None


def _weighted_kind(words: Sequence[str], index: int) -> GapKind:
    previous: str = word_core(words[index - 1])
    following: str = word_core(words[index])
    kinds: list[GapKind] = []
    if previous in _AUXILIARIES:
        kinds.append(GapKind.AUXILIARY)
    adjective: bool = previous.endswith(_ADJECTIVE_ENDINGS) and following not in PREPOSITIONS | CONJUNCTIONS
    if previous in _DETERMINERS or adjective:
        kinds.append(GapKind.MODIFIER)
    conjunction: GapKind | None = _conjunction_kind(words, index)
    if conjunction is not None:
        kinds.append(conjunction)
    if following in PREPOSITIONS or _opens(words, index, PREPOSITIONS_MULTIWORD):
        kinds.append(GapKind.BEFORE_PREPOSITION)
    return max(kinds, key=TIERS.__getitem__, default=GapKind.PHRASE)


def _counts(previous: str, following: str) -> bool:
    if _RE_THOUSANDS_HEAD.fullmatch(previous) and _RE_THOUSANDS_TAIL.match(following):
        return True
    numeral: bool = bool(_RE_NUMBER.fullmatch(previous)) or previous in _NUMERALS
    counted: bool = any(character.isalpha() for character in following)
    return numeral and counted and following not in PREPOSITIONS | CONJUNCTIONS


def _conjunction_kind(words: Sequence[str], index: int) -> GapKind | None:
    following: str = word_core(words[index])
    if _opens(words, index, _SUBORDINATING_PHRASES):
        return GapKind.BEFORE_SUBORDINATOR
    if _opens(words, index, CONJUNCTIONS_MULTIWORD):
        return GapKind.BEFORE_COORDINATOR
    if following in _SUBORDINATORS:
        return GapKind.BEFORE_SUBORDINATOR
    if following in _COORDINATORS:
        return GapKind.BEFORE_COORDINATOR
    return None


def _reflexive(words: Sequence[str], index: int) -> bool:
    following: list[str] = [*_group_words(words[index]), *words[index + 1 :]]
    if word_core(following[0]) == _REFLEXIVE:
        return True
    if word_core(_group_words(words[index - 1])[-1]) != _REFLEXIVE:
        return False
    if word_core(following[0]) in _PHRASE_OPENERS or _capitalised(following[0]):
        return False
    return not any(_opens(following, 0, phrases) for phrases in (CONJUNCTIONS_MULTIWORD, PREPOSITIONS_MULTIWORD))


def _group_words(word: str) -> list[str]:
    return word.split() or [word]


def _earlier(words: Sequence[str], index: int) -> str:
    return words[index - 2] if index > 1 else ""


def _inside(words: Sequence[str], index: int, phrases: frozenset[tuple[str, ...]]) -> bool:
    for length in range(2, _MAX_PHRASE_WORDS + 1):
        for start in range(max(0, index - length + 1), index):
            end: int = start + length
            if end <= len(words) and tuple(word_core(word) for word in words[start:end]) in phrases:
                return True
    return False


def _opens(words: Sequence[str], index: int, phrases: frozenset[tuple[str, ...]]) -> bool:
    return any(
        tuple(word_core(word) for word in words[index : index + length]) in phrases
        for length in range(2, _MAX_PHRASE_WORDS + 1)
    )


def _ends_sentence(word: str) -> bool:
    return _tail(word)[-1:] in tuple(SENTENCE_ENDINGS)


def _capitalised(word: str) -> bool:
    letters: str = "".join(character for character in word if character.isalpha())
    return bool(letters) and letters[0].isupper() and not letters.isupper()


def _tail(word: str) -> str:
    return word.rstrip(CLOSING_MARKS + '"')
