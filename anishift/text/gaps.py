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
    from collections.abc import Callable, Mapping, Sequence

__all__ = [
    "CONJUNCTIONS",
    "CONJUNCTIONS_MULTIWORD",
    "DASHES",
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
    DEGREE = "degree"
    PARTICLE = "particle"
    PREPOSITIONAL = "prepositional"
    NAME = "name"
    AFTER_PREPOSITION = "after_preposition"
    NEGATION = "negation"
    REFLEXIVE = "reflexive"
    CLITIC = "clitic"
    NUMBER = "number"
    IDIOM = "idiom"
    LABEL = "label"
    REPETITION = "repetition"
    AFTER_SINGLE_LETTER = "after_single_letter"


@dataclass(frozen=True, slots=True)
class Gap:
    """Evidence for a line break between two neighbouring words."""

    kind: GapKind
    banned: bool
    protected: bool
    turn: bool


type Modifies = Callable[[str, str], bool]
"""Whether a word modifies the word after it, such as an adjective agreeing with a noun."""

type Verb = Callable[[str], bool]
"""Whether a word can be read as a verb form."""


# ── Constants ─────────────────────────────────────────────────────────────────

TIERS: Final[Mapping[GapKind, int]] = MappingProxyType(
    {
        GapKind.SENTENCE: 0,
        GapKind.CLAUSE: 1, GapKind.ELLIPSIS: 1, GapKind.PARENTHETICAL: 1, GapKind.DASH: 1,
        GapKind.BEFORE_SUBORDINATOR: 2, GapKind.BEFORE_COORDINATOR: 2,
        GapKind.BEFORE_PREPOSITION: 3, GapKind.PHRASE: 3,
        GapKind.AUXILIARY: 4, GapKind.MODIFIER: 4, GapKind.ABBREVIATION: 4, GapKind.AFTER_OPENER: 4,
        GapKind.DEGREE: 4, GapKind.PARTICLE: 4, GapKind.PREPOSITIONAL: 4,
        GapKind.NAME: 5, GapKind.AFTER_PREPOSITION: 5, GapKind.NEGATION: 5, GapKind.REFLEXIVE: 5, GapKind.CLITIC: 5,
        GapKind.NUMBER: 5, GapKind.IDIOM: 5, GapKind.LABEL: 5, GapKind.REPETITION: 5,
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

# source: https://pl.wikipedia.org/wiki/Spójnik_(część_mowy) (spójniki współrzędne)
_COORDINATORS: Final[frozenset[str]] = frozenset(
    {
        "a", "albo", "ale", "ani", "atoli", "bądź", "czy", "czyli", "dlatego", "i", "jednak", "jednakże", "lecz",
        "lub", "mianowicie", "minus", "natomiast", "niemniej", "oraz", "plus", "przeto", "toteż", "tudzież", "tylko",
        "więc", "wszelako", "zarówno", "zatem", "zaś",
    }
)  # fmt: skip
"""Coordinating conjunctions; ``czy`` counts here, since without a parser an indirect question is not told apart."""

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
        "według", "wśród", "obok", "zza", "spod", "poza", "wobec", "podczas", "około", "ponad", "pomiędzy", "poprzez",
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

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_zaimki_dzierżawcze
_POSSESSIVE_DETERMINERS: Final[frozenset[str]] = frozenset(
    {
        "mój", "moja", "moje", "mojego", "mojej", "moim", "moją", "moich", "twój", "twoja", "twoje", "twojego",
        "twojej", "twoim", "twoją", "twoich", "swój", "swoja", "swoje", "swojego", "swojej", "swoim", "swoją",
        "swoich", "nasz", "nasza", "nasze", "naszego", "naszej", "naszym", "naszą", "naszych", "wasz", "wasza",
        "wasze", "waszego", "waszej", "waszym", "waszą", "waszych",
    }
)  # fmt: skip
"""Inflected possessive determiners of the first and second person and of ``swój``."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_zaimki_wskazujące
_DETERMINERS: Final[frozenset[str]] = _POSSESSIVE_DETERMINERS | frozenset(
    {
        "ten", "ta", "to", "te", "tego", "tej", "temu", "tym", "tych", "tą", "tę", "tamten", "tamta", "tamto",
        "tamte", "tamtego", "tamtej", "tamtym", "tamtych", "tamtą", "tamtę", "taki", "taka", "takie", "takiego",
        "takiej", "takim", "takich", "taką", "każdy", "każda", "każde", "każdego", "każdej", "każdym", "każdą",
        "jakiś", "jakaś", "jakieś", "jakiegoś", "jakiejś", "jakimś", "jakąś", "jakichś", "jakimiś",
    }
)  # fmt: skip
"""Demonstrative, possessive and indefinite determiners with their inflected forms, kept with their noun."""

_PREPOSED_POSSESSIVES: Final[frozenset[str]] = _POSSESSIVE_DETERMINERS | {"jej", "jego", "ich"}
"""Words that are possessive after a preposition, where a personal pronoun takes its ``n-`` form (``do niej``)."""

_MAX_PHRASE_MODIFIERS: Final[int] = 3
"""Most modifiers looked through between a preposition and its noun (``w tej naszej starej / szkole``)."""

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

_REFLEXIVES: Final[frozenset[str]] = frozenset({"się", "sobie", "siebie", "sobą"})
"""Reflexive particle and pronoun forms never starting a line and kept with the words after them until a new phrase."""

# source: https://pl.wikipedia.org/wiki/Klityka (Polish pronominal clitics; się is a reflexive)
_CLITICS: Final[frozenset[str]] = frozenset(
    {"mi", "ci", "mu", "go", "ją", "je", "nas", "was", "nam", "wam", "im", "cię"}
)
"""Short unstressed personal pronouns that lean on the word before them and never open a line."""

_NEGATION: Final[str] = "nie"
"""Negation particle bound to the verb after it."""

DASHES: Final[frozenset[str]] = frozenset({"-", "–", "—"})
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

# source: M. Grochowski, „Gradacja”, IJP PAN, https://gramsem.ijppan.pl/wp-content/uploads/2024/06/Gradacja.pdf
# (gradation and approximation operators, analytic comparison); wyjątkowo, niezwykle, okropnie as intensifiers
_DEGREE_ADVERBS: Final[frozenset[str]] = frozenset(
    {
        "tak", "bardzo", "zbyt", "za", "coraz", "aż", "całkiem", "nieco", "trochę", "dość", "dosyć", "równie", "dużo",
        "mało", "sporo", "znacznie", "nieznacznie", "zupełnie", "całkowicie", "kompletnie", "absolutnie", "zanadto",
        "zbytnio", "nazbyt", "nadmiernie", "wielce", "wysoce", "strasznie", "ogromnie", "okropnie", "wyjątkowo",
        "niezwykle", "odrobinę", "prawie", "niemal", "niemalże", "niespełna", "raczej", "mniej", "bardziej",
        "najmniej", "najbardziej",
    }
)  # fmt: skip
"""Degree, approximation and comparison adverbs kept with the word they grade or count (owner quiz t02)."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_partykuły (focus particles; szczególnie as zwłaszcza)
_PARTICLES: Final[frozenset[str]] = frozenset(
    {"nawet", "jedynie", "właśnie", "już", "jeszcze", "też", "także", "również", "przynajmniej", "zwłaszcza",
     "szczególnie", "akurat"}
)  # fmt: skip
"""Focus particles kept with the word they single out; ``tylko``, ``aż`` and ``chociaż`` count as conjunctions."""

_DEGREE_PHRASES: Final[frozenset[tuple[str, str]]] = frozenset({("tak", "samo")})
"""Two-word degree phrases kept with the word they grade."""

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

# source: https://pl.wikipedia.org/wiki/Liczebnik (liczebniki nieokreślone i zbiorowe, inflected forms)
_QUANTIFIERS: Final[frozenset[str]] = frozenset(
    {
        "kilka", "kilku", "kilkoma", "kilkanaście", "kilkunastu", "kilkunastoma", "kilkadziesiąt", "kilkudziesięciu",
        "kilkudziesięcioma", "kilkaset", "kilkuset", "parę", "paru", "paroma", "parędziesiąt", "wiele", "wielu",
        "wieloma", "niewiele", "niewielu", "ileś", "iluś", "tyle", "tylu", "tyloma", "dwoje", "dwojga", "dwojgu",
        "dwojgiem", "troje", "trojga", "trojgu", "trojgiem", "czworo", "czworga", "pięcioro", "pięciorga",
        "sześcioro", "siedmioro", "ośmioro", "dziewięcioro", "dziesięcioro", "kilkoro", "kilkorga", "oboje",
        "obojga", "obojgu", "obojgiem", "obaj", "obie", "obu", "obydwaj", "obydwie", "obydwu",
    }
)  # fmt: skip
"""Indefinite and collective numerals with their inflected forms, kept with the noun they count."""

_NUMBERED: Final[frozenset[str]] = frozenset(
    {
        "numer", "numeru", "numerowi", "numerem", "numerze", "nr", "rozdział", "rozdziału", "rozdziałowi",
        "rozdziałem", "rozdziale", "odcinek", "odcinka", "odcinkowi", "odcinkiem", "odcinku", "pokój", "pokoju",
        "pokojowi", "pokojem", "strona", "strony", "stronie", "stronę", "stroną",
    }
)  # fmt: skip
"""Nouns naming a numbered item, kept with the number or numeral that follows them (``numer / jeden``)."""

_RE_STUTTER: Final[re.Pattern[str]] = re.compile(r"(\w)-(\1\w+)")
"""Stuttered word (``n-nie``): the repeated letter, a hyphen and the whole word."""

_OPENING_QUOTES: Final[str] = '„“«"'
"""Quotation marks that open a quotation at the start of a word."""

_CLOSING_QUOTES: Final[str] = '”“»"'
"""Quotation marks that close a quotation at the end of a word, before any trailing punctuation."""

_TRAILING_MARKS: Final[str] = ".,;:!?…"
"""Punctuation that may follow a closing quotation mark."""

_LABEL_MARK: Final[str] = ":"
"""Mark ending a label whose value follows (``WYS.: 4,5 KM``, ``Korekta: Michał``)."""

_RE_LIST_MARKER: Final[re.Pattern[str]] = re.compile(r"\(\d+\)")
"""Marker of a numbered list item, such as ``(1)``."""


def gaps(words: Sequence[str], modifies: Modifies | None = None, verb: Verb | None = None) -> tuple[Gap, ...]:
    """Return the evidence for every gap between neighbouring ``words``: entry ``i`` precedes word ``i + 1``."""
    speakers: frozenset[int] = _speaker_marks(words)
    paired: frozenset[int] = _paired_dashes(words, speakers)
    return tuple(_gap(words, index, (speakers, paired), (modifies, verb)) for index in range(1, len(words)))


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


def _gap(
    words: Sequence[str],
    index: int,
    dashes: tuple[frozenset[int], frozenset[int]],
    morphology: tuple[Modifies | None, Verb | None],
) -> Gap:
    speakers, paired = dashes
    previous: str = words[index - 1]
    following: str = words[index]
    turn: bool = index in speakers
    kind: GapKind = _punctuation_kind(words, index, speakers, paired) or _word_kind(words, index, morphology)
    banned: bool = not turn and (
        unicodedata.category(previous[-1]) in _OPENING_CATEGORIES
        or all(character in _LEADING_BANNED for character in following)
        or following[0] in DASHES
        or (previous in DASHES and index - 1 in speakers)
    )
    return Gap(kind=kind, banned=banned, protected=not turn and kind in PROTECTED_KINDS, turn=turn)


def _speaker_marks(words: Sequence[str]) -> frozenset[int]:
    marks: set[int] = set()
    for index, word in enumerate(words):
        if word[:1] not in DASHES or (index > 0 and not _ends_sentence(words[index - 1])):
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
    if previous in DASHES and index - 1 not in speakers:
        return _dash_kind(words, index, paired)
    tail: str = _tail(previous)
    if tail.endswith(_LABEL_MARK) and (words[index][:1].isdigit() or _label(words, index - 1)):
        return GapKind.LABEL
    if tail.endswith(_ELLIPSES):
        return GapKind.ELLIPSIS
    strong: bool = bool(tail[-1:]) and tail[-1] in _STRONG_MARKS
    if strong or (tail.endswith(_FULL_STOP) and not is_false_sentence_break(tail, words[index])):
        return GapKind.SENTENCE
    if tail[-1:] and tail[-1] in _CLAUSE_MARKS:
        return GapKind.CLAUSE
    return None


def _dash_kind(words: Sequence[str], index: int, paired: frozenset[int]) -> GapKind:
    repeated: str = word_core(words[index - 2]) if index > 1 else ""
    if repeated and repeated == word_core(words[index]):
        return GapKind.REPETITION
    return GapKind.PARENTHETICAL if index - 1 in paired else GapKind.DASH


def _word_kind(words: Sequence[str], index: int, morphology: tuple[Modifies | None, Verb | None]) -> GapKind:
    modifies, verb = morphology
    kinds: list[GapKind] = [*_bound_kinds(words, index, modifies, verb), *_weighted_kinds(words, index, modifies)]
    return max(kinds, key=TIERS.__getitem__, default=GapKind.PHRASE)


def _bound_kinds(words: Sequence[str], index: int, modifies: Modifies | None, verb: Verb | None) -> list[GapKind]:
    previous: str = word_core(words[index - 1])
    following: str = word_core(words[index])
    preposition: bool = _follows_preposition(words, index) or _inside(words, index, PREPOSITIONS_MULTIWORD)
    phrase: GapKind | None = _prepositional_phrase(words, index, modifies)
    evidence: tuple[tuple[GapKind, bool], ...] = (
        (GapKind.AFTER_PREPOSITION, preposition or phrase == GapKind.AFTER_PREPOSITION),
        (GapKind.PREPOSITIONAL, phrase == GapKind.PREPOSITIONAL),
        (GapKind.NEGATION, previous == _NEGATION and word_core(_earlier(words, index)) not in PREPOSITIONS),
        (GapKind.REFLEXIVE, _reflexive(words, index)),
        (GapKind.CLITIC, _clitic(words[index - 1], words[index])),
        (GapKind.NUMBER, _counts(previous, following) or _numbered(previous, following)),
        (GapKind.ABBREVIATION, _tail(words[index - 1]).endswith(_FULL_STOP)),
        (GapKind.NAME, _named(words, index)),
        (GapKind.IDIOM, _inside(words, index, _IDIOMS)),
        (GapKind.AFTER_OPENER, previous in CONJUNCTIONS or previous in _RELATIVES),
        (GapKind.PARTICLE, previous in _PARTICLES),
        (GapKind.AFTER_SINGLE_LETTER, len(previous) == 1 and previous.isalpha()),
    )
    return [kind for kind, present in evidence if present]


def _weighted_kinds(words: Sequence[str], index: int, modifies: Modifies | None) -> list[GapKind]:
    previous: str = word_core(words[index - 1])
    following: str = word_core(words[index])
    kinds: list[GapKind] = []
    phrase: bool = following in PREPOSITIONS and not _opens(words, index, _IDIOMS)
    if previous in _AUXILIARIES and following not in CONJUNCTIONS and not phrase:
        kinds.append(GapKind.AUXILIARY)
    ending: bool = previous.endswith(_ADJECTIVE_ENDINGS) or (
        modifies is not None and modifies(words[index - 1], words[index])
    )
    adjective: bool = ending and following not in PREPOSITIONS | CONJUNCTIONS
    if previous in _DETERMINERS or adjective:
        kinds.append(GapKind.MODIFIER)
    conjunction: GapKind | None = _conjunction_kind(words, index)
    if conjunction is not None:
        kinds.append(conjunction)
    if following in PREPOSITIONS or _opens(words, index, PREPOSITIONS_MULTIWORD):
        kinds.append(GapKind.BEFORE_PREPOSITION)
    if _degree(words, index) and following not in CONJUNCTIONS and not _opens(words, index, _IDIOMS):
        kinds.append(GapKind.DEGREE)
    return kinds


def _degree(words: Sequence[str], index: int) -> bool:
    previous: str = word_core(words[index - 1])
    return previous in _DEGREE_ADVERBS or (word_core(_earlier(words, index)), previous) in _DEGREE_PHRASES


def _named(words: Sequence[str], index: int) -> bool:
    if not _capitalised(words[index]) or _next_label(words, index):
        return False
    return _capitalised(words[index - 1]) or word_core(words[index - 1]) in _TITLES


def _label(words: Sequence[str], index: int) -> bool:
    word: str = words[index]
    if not _tail(word).endswith(_LABEL_MARK) or not word[:1].isupper() or index + 2 >= len(words):
        return False
    return _capitalised(words[index + 1]) and _capitalised(words[index + 2])


def _next_label(words: Sequence[str], index: int) -> bool:
    return _label(words, index) and any(_label(words, earlier) for earlier in range(index - 1))


def _counts(previous: str, following: str) -> bool:
    if _RE_THOUSANDS_HEAD.fullmatch(previous) and _RE_THOUSANDS_TAIL.match(following):
        return True
    numeral: bool = bool(_RE_NUMBER.fullmatch(previous)) or previous in _NUMERALS | _QUANTIFIERS
    counted: bool = any(character.isalpha() for character in following)
    return numeral and counted and following not in PREPOSITIONS | CONJUNCTIONS


def _numbered(previous: str, following: str) -> bool:
    return previous in _NUMBERED and (bool(_RE_NUMBER.fullmatch(following)) or following in _NUMERALS)


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
    if word_core(following[0]) in _REFLEXIVES:
        return True
    if word_core(_group_words(words[index - 1])[-1]) not in _REFLEXIVES:
        return False
    if word_core(following[0]) in _PHRASE_OPENERS or _capitalised(following[0]):
        return False
    return not any(_opens(following, 0, phrases) for phrases in (CONJUNCTIONS_MULTIWORD, PREPOSITIONS_MULTIWORD))


def _clitic(previous: str, following: str) -> bool:
    return not unicodedata.category(previous[-1]).startswith("P") and word_core(following) in _CLITICS


def _follows_preposition(words: Sequence[str], index: int) -> bool:
    if word_core(words[index - 1]) in PREPOSITIONS:
        return True
    return any(
        tuple(word_core(word) for word in words[index - length : index]) in PREPOSITIONS_MULTIWORD
        for length in range(2, min(index, _MAX_PHRASE_WORDS) + 1)
    )


def _prepositional_phrase(words: Sequence[str], index: int, modifies: Modifies | None) -> GapKind | None:
    adjectival: bool = False
    for left in range(index - 1, max(0, index - 1 - _MAX_PHRASE_MODIFIERS), -1):
        preposed: bool = _follows_preposition(words, left)
        link: GapKind | None = _modifier(words[left], words[left + 1], modifies, preposed=preposed)
        if link is None:
            return None
        adjectival = adjectival or link == GapKind.PREPOSITIONAL
        if preposed:
            return GapKind.PREPOSITIONAL if adjectival else GapKind.AFTER_PREPOSITION
    return None


def _modifier(word: str, following: str, modifies: Modifies | None, *, preposed: bool) -> GapKind | None:
    if unicodedata.category(word[-1]).startswith("P"):
        return None
    if preposed and word_core(word) in _PREPOSED_POSSESSIVES:
        return GapKind.AFTER_PREPOSITION
    return GapKind.PREPOSITIONAL if modifies is not None and modifies(word, following) else None


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
