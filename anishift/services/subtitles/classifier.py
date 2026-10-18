"""Classify subtitle styles using the measured mm_avh heuristic."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.fuzzy import fall, rise
from anishift.services.subtitles.text import is_drawing, visible_text
from anishift.text.boundaries import LATIN_SENTENCE_ENDINGS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile, SSAStyle

__all__ = [
    "Category",
    "StyleVerdict",
    "classify_styles",
    "dedup_animation",
    "line_category",
    "main_dialogue_style",
    "never_narrated",
    "screen_edge",
    "title_like",
    "word_count",
    "written_in_capitals",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_BACKSLASH: Final[str] = chr(92)
"""Literal backslash used to build ASS tag expressions."""


# ── ASS tag signatures ──────────────────────────────────────────────────────
_RE_POS: Final[re.Pattern[str]] = re.compile(_BACKSLASH + _BACKSLASH + r"(pos|move|clip|frz|fad|org|t\()")
"""Positioning and animation tags typical of on-screen typesetting."""

_RE_KARA: Final[re.Pattern[str]] = re.compile(_BACKSLASH + _BACKSLASH + r"[kK][fo]?[0-9]")
"""Karaoke timing tags typical of song lines."""

_RE_PUNCT: Final[re.Pattern[str]] = re.compile(r'[.!?…»"]')
"""Sentence punctuation signalling dialogue."""

_RE_MID_ALIGN: Final[re.Pattern[str]] = re.compile(_BACKSLASH + _BACKSLASH + r"an[456]")
"""Inline alignment tags placing a line at mid frame height."""


# ── Style-name signatures (supporting, not decisive on their own) ───────────
_RE_SONG: Final[re.Pattern[str]] = re.compile(
    r"\bop\b|\bed\b|opening|ending|song|lyric|piosenk|karaoke|insert.?song|theme", re.I
)
"""Style names suggesting an opening, ending or insert song."""

_RE_SONG_NAME: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[^a-z])(?:nc)?(?:op|ed|ins|insert|in(?=[0-9]))(?:[0-9]+|up|down|bg)?(?:$|[^a-z])", re.I
)
"""Song style names written as release codes, such as ``EDup``, ``OP_EN_blue``, ``ED1 - ENG`` or ``IN01``."""

_RE_NOTE: Final[re.Pattern[str]] = re.compile(r"disclaimer|\bnote\b|notka|przypis|tln|t/n|credit|copyright", re.I)
"""Style names suggesting a translator note or credit."""

_RE_SIGN: Final[re.Pattern[str]] = re.compile(
    r"sign|znak|kartka|title|next_ep|acquired|chyron|chapter|^ts$|typeset|caption.?box|box$", re.I
)
"""Style names suggesting an on-screen sign, title or chapter card."""

_RE_DLG: Final[re.Pattern[str]] = re.compile(
    r"default|main|dialog|narrat|italic|flashback|tirets|thought|mysli|myśli|alter|overlap|\bsub(title)?\b|\balt\b",
    re.I,
)
"""Style names suggesting dialogue, narration or thoughts."""


# ── Line veto signatures ────────────────────────────────────────────────────
_RE_SENTENCE: Final[re.Pattern[str]] = re.compile("[" + re.escape(LATIN_SENTENCE_ENDINGS) + '"»”]|[—–-]' + r"\s*$")
"""Sentence mark or a trailing dash of an interrupted line, either of which makes a line speech."""

_RE_WORD: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")  # noqa: RUF001 - typographic apostrophe
"""One word of letters, joined across apostrophes and hyphens."""

_RE_SOUND_EFFECT: Final[re.Pattern[str]] = re.compile(r"\*.*\*", re.S)
"""Visible text wholly between asterisks, a sound effect rather than a sign."""

_RE_PLACED: Final[re.Pattern[str]] = re.compile(
    _BACKSLASH + _BACKSLASH + r"(?:pos|move|org)\(|" + _BACKSLASH + _BACKSLASH + r"fr[xyz]?\s*-?(?:0*[1-9]|0*\.0*[1-9])"
)
"""Tags placing a line by position, origin or a nonzero rotation."""

_RE_ALIGN: Final[re.Pattern[str]] = re.compile(_BACKSLASH + _BACKSLASH + r"an([1-9])")
"""Inline numpad alignment tag."""

_RE_ANCHOR_Y: Final[re.Pattern[str]] = re.compile(
    _BACKSLASH + _BACKSLASH + r"(?:pos|move)\(\s*-?[0-9.]+\s*,\s*(-?(?:[0-9]+\.?[0-9]*|\.[0-9]+))"
)
"""Vertical coordinate of the first position or movement start of a line."""

_MID_ROW: Final[frozenset[int]] = frozenset({4, 5, 6})
"""Numpad alignments of the middle screen row, where signs sit and dialogue does not."""

_DEFAULT_ALIGNMENT: Final[int] = 2
"""Numpad alignment of a line whose style is undefined."""

_NUMPAD_COLUMNS: Final[int] = 3
"""Alignment columns in one numpad row: left, centre and right."""

_CAPS_SHARE: Final[tuple[float, float]] = (0.6, 0.85)
"""Share of capital letters over which a line becomes written in capitals."""

_CAPS_MIN_LETTERS: Final[int] = 2
"""Fewest letters a line needs before its capitals count."""

_EDGE_BOTTOM: Final[tuple[float, float]] = (0.7, 0.8)
"""Vertical position, as a share of the script height, over which a placed line reaches the bottom edge."""

_EDGE_TOP: Final[tuple[float, float]] = (0.2, 0.3)
"""Vertical position, as a share of the script height, under which a placed line reaches the top edge."""

_PROTECTED_MAX_WORDS: Final[int] = 3
"""Most words of a short unplaced line at a screen edge that the veto keeps spoken, such as a shout."""

_TITLE_WORD_MIN_LETTERS: Final[int] = 4
"""Letters from which a word must start with a capital in title case."""

_TITLE_MIN_WORDS: Final[int] = 2
"""Fewest words of a title-case line."""

_DEGREE_TRUE: Final[float] = 0.5
"""Fuzzy degree from which a line feature counts as present."""


# ── Actor-name signatures ───────────────────────────────────────────────────
_RE_SIGN_ACTOR: Final[re.Pattern[str]] = re.compile(r"signs?|signtext|signsrtol|signl|titlecard|nexteptitle", re.I)
"""Whole actor names that mark a positioned, unpunctuated or secondary-style line as an on-screen sign."""


# ── Animation deduplication thresholds ──────────────────────────────────────
_DEDUP_MIN_REPEAT: Final[int] = 5
"""Minimum repeated lines required for animation deduplication."""

_DEDUP_WINDOW_MS: Final[int] = 2000
"""Maximum median start gap for animation deduplication."""


# ── Style classification thresholds ─────────────────────────────────────────
_DRAW_SIGN_RATIO: Final[float] = 0.30
"""Vector-drawing line ratio above which a style is a sign (shape)."""

_KARA_SONG_RATIO: Final[float] = 0.30
"""Karaoke line ratio above which a style is an OP/ED song."""

_DLG_MAX_POS_RATIO: Final[float] = 0.50
"""Max positioning ratio for the confident-dialogue-variant shortcut."""

_SCORE_DIALOG: Final[float] = 0.55
"""Score at or above which a style is classified as DIALOG."""

_SCORE_SIGN: Final[float] = 0.25
"""Score at or below which a style is classified as SIGN."""

_FRAC_DIALOG_MIN: Final[float] = 0.20
"""File-share ratio at or above which a style earns the share score."""

_POS_LOW_MAX: Final[float] = 0.40
"""Positioning ratio below which a style earns the low-positioning score."""

_PUNCT_MIN: Final[float] = 0.30
"""Punctuation ratio above which a style earns the punctuation score."""

_AVG_TEXT_MIN: Final[int] = 12
"""Average plain-text length at or above which a style earns the length score."""

_POS_HIGH_MIN: Final[float] = 0.60
"""Positioning ratio above which a style is penalised as typesetting."""


class Category(Enum):
    """Subtitle style category for auto mode."""

    DIALOG = "DIALOG"
    SIGN = "SIGN"
    UNCERTAIN = "UNCERTAIN"


@dataclass(slots=True, frozen=True)
class StyleVerdict:
    """Classification verdict for a single style."""

    style: str
    category: Category
    confidence: float
    line_count: int
    raw_line_count: int


@dataclass(slots=True)
class _StyleMetrics:
    n: int = 0
    raw_n: int = 0
    pos: int = 0
    draw: int = 0
    kara: int = 0
    punct: int = 0
    txt: int = 0


def dedup_animation(events: list[SSAEvent]) -> tuple[list[SSAEvent], int]:
    """Collapse repeated typesetting animation lines into one occurrence."""
    by_key: dict[tuple[str, str], list[SSAEvent]] = defaultdict(list)
    for event in events:
        by_key[(event.style, event.plaintext.strip())].append(event)

    keep: list[SSAEvent] = []
    removed = 0
    for (_style, text), group in by_key.items():
        if len(group) < _DEDUP_MIN_REPEAT or not text:
            keep.extend(group)
            continue
        starts = sorted(event.start for event in group)
        diffs = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
        median_gap = sorted(diffs)[len(diffs) // 2] if diffs else 0
        if median_gap >= _DEDUP_WINDOW_MS:
            keep.extend(group)
            continue
        keep.append(min(group, key=lambda event: event.start))
        removed += len(group) - 1
    return keep, removed


def _classify_metrics(metrics: _StyleMetrics, style: str, total: int) -> tuple[Category, float]:
    n = metrics.n
    pos, draw, kara, punct = metrics.pos / n, metrics.draw / n, metrics.kara / n, metrics.punct / n
    avg, frac = metrics.txt / n, metrics.n / total
    if draw > _DRAW_SIGN_RATIO or kara > _KARA_SONG_RATIO:
        return Category.SIGN, 0.95
    if _RE_SONG.search(style) or _RE_SONG_NAME.search(style) or _RE_NOTE.search(style):
        return Category.SIGN, 0.9
    if _RE_DLG.search(style) and pos < _DLG_MAX_POS_RATIO and draw == 0:
        return Category.DIALOG, 0.85
    score = 0.0
    if frac >= _FRAC_DIALOG_MIN:
        score += 0.35
    if pos < _POS_LOW_MAX:
        score += 0.25
    if punct > _PUNCT_MIN:
        score += 0.20
    if avg >= _AVG_TEXT_MIN:
        score += 0.10
    if _RE_DLG.search(style):
        score += 0.15
    if _RE_SIGN.search(style):
        score -= 0.25
    if pos > _POS_HIGH_MIN:
        score -= 0.30
    if score >= _SCORE_DIALOG:
        return Category.DIALOG, round(min(score, 0.99), 2)
    if score <= _SCORE_SIGN:
        return Category.SIGN, round(min(1 - score, 0.95), 2)
    return Category.UNCERTAIN, 0.5


def classify_styles(subs: SSAFile) -> list[StyleVerdict]:
    """Classify every style used by Dialogue events."""
    events = [event for event in subs.events if event.type == "Dialogue"]
    if not events:
        return []
    deduped, _ = dedup_animation(events)
    total = len(deduped)
    metrics: dict[str, _StyleMetrics] = defaultdict(_StyleMetrics)
    for event in events:
        metrics[event.style].raw_n += 1
    for event in deduped:
        entry = metrics[event.style]
        entry.n += 1
        if _RE_POS.search(event.text):
            entry.pos += 1
        if is_drawing(event.text):
            entry.draw += 1
        if _RE_KARA.search(event.text):
            entry.kara += 1
        plain = event.plaintext
        entry.txt += len(plain)
        if _RE_PUNCT.search(plain):
            entry.punct += 1
    verdicts: list[StyleVerdict] = []
    for style, entry in sorted(metrics.items(), key=lambda kv: -kv[1].n):
        if entry.n == 0:
            continue
        category, confidence = _classify_metrics(entry, style, total)
        verdicts.append(StyleVerdict(style, category, confidence, entry.n, entry.raw_n))
    return verdicts


def main_dialogue_style(verdicts: Sequence[StyleVerdict]) -> str | None:
    """Return the DIALOG style with the most lines, or None when no style is DIALOG."""
    dialogue: list[StyleVerdict] = [verdict for verdict in verdicts if verdict.category is Category.DIALOG]
    return max(dialogue, key=lambda verdict: verdict.line_count).style if dialogue else None


def _sign_actor(event: SSAEvent, *, in_main_style: bool) -> bool:
    if not _RE_SIGN_ACTOR.fullmatch(event.name.strip()):
        return False
    return not in_main_style or bool(_RE_POS.search(event.text)) or not _RE_PUNCT.search(event.plaintext)


def line_category(
    event: SSAEvent, style_category: Category, *, in_main_style: bool, style: SSAStyle | None, play_res_y: int
) -> Category:
    """Return the DIALOG or SIGN category of one event, refining its style verdict by actor, alignment and form."""
    if _sign_actor(event, in_main_style=in_main_style):
        return Category.SIGN
    category: Category = style_category
    if category is Category.UNCERTAIN:
        category = Category.DIALOG if _RE_DLG.search(event.style) else Category.SIGN
    if category is Category.DIALOG and (_RE_MID_ALIGN.search(event.text) or _vetoed(event, style, play_res_y)):
        return Category.SIGN
    return category


def written_in_capitals(text: str) -> bool:
    """Tell whether a visible text is written in capitals, from 72.5% capital letters among at least two."""
    letters: list[str] = [char for char in text if char.isalpha()]
    if len(letters) < _CAPS_MIN_LETTERS:
        return False
    return rise(sum(char.isupper() for char in letters) / len(letters), *_CAPS_SHARE) >= _DEGREE_TRUE


def screen_edge(event: SSAEvent, style: SSAStyle | None, play_res_y: int) -> float:
    """Return the degree, from 0 to 1, to which a line sits at the top or bottom edge of the screen."""
    return _edge(event, _alignment(event, style), play_res_y)


def title_like(text: str) -> bool:
    """Tell whether a visible text is written in capitals or in title case."""
    return written_in_capitals(text) or _title_case(_RE_WORD.findall(text))


def word_count(text: str) -> int:
    """Count the words of letters in a visible text."""
    return len(_RE_WORD.findall(text))


def never_narrated(event: SSAEvent) -> bool:
    """Tell whether an on-screen line is a song, karaoke, drawing or sound effect the narrator never reads."""
    if _RE_SONG.search(event.style) or _RE_SONG_NAME.search(event.style) or _RE_KARA.search(event.text):
        return True
    plain: str = visible_text(event.text)
    return is_drawing(event.text) or not plain or bool(_RE_SOUND_EFFECT.fullmatch(plain))


def _alignment(event: SSAEvent, style: SSAStyle | None) -> int:
    inline: list[str] = _RE_ALIGN.findall(event.text)
    return int(inline[-1]) if inline else _style_alignment(style)


def _style_alignment(style: SSAStyle | None) -> int:
    return int(style.alignment) if style is not None else _DEFAULT_ALIGNMENT


def _vetoed(event: SSAEvent, style: SSAStyle | None, play_res_y: int) -> bool:
    plain: str = visible_text(event.text)
    if _RE_SENTENCE.search(plain) or "," in plain:
        return False
    style_alignment: int = _style_alignment(style)
    alignment: int = _alignment(event, style)
    placed: bool = _placed(event, alignment, style_alignment)
    words: list[str] = _RE_WORD.findall(plain)
    if len(words) <= _PROTECTED_MAX_WORDS and not placed and _edge(event, alignment, play_res_y) >= _DEGREE_TRUE:
        return False
    return written_in_capitals(plain) or (placed and _title_case(words))


def _placed(event: SSAEvent, alignment: int, style_alignment: int) -> bool:
    if _RE_PLACED.search(event.text) or alignment in _MID_ROW:
        return True
    return (alignment - 1) % _NUMPAD_COLUMNS != (style_alignment - 1) % _NUMPAD_COLUMNS


def _edge(event: SSAEvent, alignment: int, play_res_y: int) -> float:
    anchor: re.Match[str] | None = _RE_ANCHOR_Y.search(event.text)
    if anchor is None or play_res_y <= 0:
        return 0.0 if alignment in _MID_ROW else 1.0
    height: float = float(anchor[1]) / play_res_y
    return max(rise(height, *_EDGE_BOTTOM), fall(height, *_EDGE_TOP))


def _title_case(words: list[str]) -> bool:
    long_words: list[str] = [word for word in words if len(word) >= _TITLE_WORD_MIN_LETTERS]
    return len(words) >= _TITLE_MIN_WORDS and bool(long_words) and all(word[0].isupper() for word in long_words)
