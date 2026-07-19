"""Text chunking for the plain-text (txt) translation path.

The txt input may be any language (source subtitles are foreign), so phrase and
word boundaries use full Unicode punctuation via ``unicodedata`` categories.
``LatinPunctuator`` splits on paragraph/sentence/phrase/word boundaries;
``CharBreaker`` and ``WordBreaker`` group the pieces into bounded chunks. Feeds
the txt -> translation -> SRT mini-feature.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Final, Literal

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_SENTENCE_LENGTH: Final[int] = 750
"""Preferred maximum characters when grouping into narrator-sized chunks."""

SENTENCE_ENDINGS: Final[str] = ".!?" + chr(0x2026) + chr(0x3002) + chr(0xFF01) + chr(0xFF1F)
"""Sentence-ending chars; handled by ``get_sentences``, never a phrase cut."""

ZERO_WIDTH: Final[str] = chr(0x200B)
"""Zero-width space some sources place after a sentence mark; SSOT of this char."""

_APOSTROPHES: Final[str] = chr(0x27) + chr(0x2019)
"""Apostrophes; kept inside a word (e.g. ``don't``), never a cut point."""


def _punctuation_chars(categories: frozenset[str], *, exclude: str) -> str:
    """Return every Unicode char in ``categories`` except those in ``exclude``.

    Uses ``unicodedata`` (stdlib) so the full punctuation set of every language
    is covered without a hand-written list or a ``regex`` dependency.
    """
    excluded = set(exclude)
    return "".join(
        char
        for code_point in range(0x110000)
        if (char := chr(code_point)) not in excluded and unicodedata.category(char) in categories
    )


# Cut categories: Pd (dashes), Pe (closing), Pf (final quotes), Po (comma,
# colon, CJK/Arabic marks...). Opening Ps/Pi are excluded - a phrase never
# begins right after an opening bracket or quote.
_PHRASE_CUT_CHARS: Final[str] = _punctuation_chars(
    frozenset({"Pd", "Pe", "Pf", "Po"}),
    exclude=SENTENCE_ENDINGS + _APOSTROPHES,
)
"""All Unicode phrase-cut punctuation, minus sentence endings and apostrophes."""

_RE_PARAGRAPHS: Final[re.Pattern[str]] = re.compile(r"((?:\r?\n\s*){2,})")
"""Blank-line paragraph separator."""

_RE_SENTENCES: Final[re.Pattern[str]] = re.compile("([" + re.escape(SENTENCE_ENDINGS) + r"]+[\s" + ZERO_WIDTH + "]+)")
"""Sentence-ending marks (any language) followed by whitespace."""

_ABBREVIATIONS: Final[re.Pattern[str]] = re.compile(
    r"\b(\w|[A-Z][a-z]|Assn|Ave|Capt|Col|Comdr|Corp|Cpl|Gen|Gov|Hon|Inc|Lieut|Ltd|Rev|Mr|Ms|Mrs|Dr|No|Univ"
    r"|Jan|Feb|Mar|Apr|Aug|Sept|Oct|Nov|Dec|dept|ed|est|vol|vs"
    r"|np|itd|itp|tzn|tj|prof|mgr|inż|ul|godz|str|nr|wg|św|ok|por|zob|red)\.\s+$"
)
"""Trailing abbreviations (English + Polish) whose dot is not a sentence end."""

_RE_PHRASES: Final[re.Pattern[str]] = re.compile("([" + re.escape(_PHRASE_CUT_CHARS) + r"]+\s*)")
"""Phrase separators: every Unicode dash/closing/final-quote/other-punctuation char."""
_RE_WORDS: Final[re.Pattern[str]] = re.compile("([" + re.escape(_PHRASE_CUT_CHARS) + r"]|[\s\-/]+)")
"""Word separators: phrase punctuation plus whitespace, hyphen and slash."""
_RE_WORD_SYMBOL: Final[re.Pattern[str]] = re.compile("^[" + re.escape(_PHRASE_CUT_CHARS) + r"\s]+$")
"""A separator token kept as its own word instead of being reattached."""
ChunkMethod = Literal["char", "word"]


class LatinPunctuator:
    """Split Latin-script and CJK text on sentence, phrase and word boundaries."""

    def get_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs on blank lines."""
        return self._recombine(_RE_PARAGRAPHS.split(text))

    def get_sentences(self, text: str) -> list[str]:
        """Split text into sentences, keeping abbreviations (Mr./Dr./itd.) whole."""
        return self._recombine(_RE_SENTENCES.split(text), _ABBREVIATIONS)

    def get_phrases(self, sentence: str) -> list[str]:
        """Split a sentence into phrases on commas, dashes, quotes and brackets."""
        return self._recombine(_RE_PHRASES.split(sentence))

    def get_words(self, phrase: str) -> list[str]:
        """Split a phrase into words, keeping standalone symbols as their own token."""
        tokens = _RE_WORDS.split(phrase.strip())
        result: list[str] = []
        index = 0
        while index < len(tokens):
            if tokens[index]:
                result.append(tokens[index])
            separator = tokens[index + 1] if index + 1 < len(tokens) else None
            if separator is not None:
                if _RE_WORD_SYMBOL.match(separator):
                    result.append(separator)
                elif result:
                    result[-1] += separator
            index += 2
        return result

    def _recombine(self, tokens: list[str], non_punc: re.Pattern[str] | None = None) -> list[str]:
        """Rejoin split tokens with their separators; keep abbreviation dots attached.

        Args:
            tokens: Alternating content/separator tokens from ``re.split``.
            non_punc: When the previous piece matches this pattern (an
                abbreviation), the current piece is appended to it instead of
                starting a new sentence.
        """
        result: list[str] = []
        for index in range(0, len(tokens), 2):
            part = tokens[index] + tokens[index + 1] if index + 1 < len(tokens) else tokens[index]
            if not part:
                continue
            if non_punc is not None and result and non_punc.search(result[-1]):
                result[-1] += part
            else:
                result.append(part)
        return result


class _Breaker:
    """Shared greedy merge over punctuator pieces with a recursive fallback."""

    def __init__(self, limit: int, punctuator: LatinPunctuator) -> None:
        """Store the size budget and the punctuator used to split text."""
        self.limit = limit
        self.punctuator = punctuator

    def _size(self, part: str) -> int:
        """Return the cost of ``part`` in the breaker's unit."""
        raise NotImplementedError

    def _merge(
        self,
        parts: list[str],
        break_part: Callable[[str], list[str]],
        combine_threshold: int | None = None,
    ) -> list[str]:
        """Greedily group ``parts`` up to the budget, recursing on oversized ones."""
        result: list[str] = []
        group: list[str] = []
        group_size = 0
        threshold = combine_threshold or self.limit

        def flush() -> None:
            nonlocal group, group_size
            if group:
                result.append("".join(group))
                group = []
                group_size = 0

        for part in parts:
            size = self._size(part)
            if size > self.limit:
                flush()
                result.extend(break_part(part))
                continue
            if group_size + size > threshold:
                flush()
            group.append(part)
            group_size += size
        flush()
        return result


class CharBreaker(_Breaker):
    """Group punctuator pieces into chunks bounded by a character budget."""

    def __init__(
        self,
        char_limit: int,
        punctuator: LatinPunctuator,
        paragraph_combine_threshold: int | None = None,
    ) -> None:
        """Store the character budget and optional paragraph combine threshold."""
        super().__init__(char_limit, punctuator)
        self.paragraph_combine_threshold = paragraph_combine_threshold

    def _size(self, part: str) -> int:
        """Return the character length of ``part``."""
        return len(part)

    def break_text(self, text: str) -> list[str]:
        """Break text into chunks no larger than the character budget."""
        return self._merge(self.punctuator.get_paragraphs(text), self.break_paragraph, self.paragraph_combine_threshold)

    def break_paragraph(self, text: str) -> list[str]:
        """Break one paragraph into sentence-bounded chunks."""
        return self._merge(self.punctuator.get_sentences(text), self.break_sentence)

    def break_sentence(self, sentence: str) -> list[str]:
        """Break one sentence into phrase-bounded chunks."""
        return self._merge(self.punctuator.get_phrases(sentence), self.break_phrase)

    def break_phrase(self, phrase: str) -> list[str]:
        """Break one phrase into word-bounded chunks."""
        return self._merge(self.punctuator.get_words(phrase), self.break_word)

    def break_word(self, word: str) -> list[str]:
        """Hard-cut a single over-budget word into character slices."""
        return [word[i : i + self.limit] for i in range(0, len(word), self.limit)] or [word]


class WordBreaker(_Breaker):
    """Group punctuator pieces into chunks bounded by a word-count budget."""

    def _size(self, part: str) -> int:
        """Return the word count of ``part``."""
        return len(self.punctuator.get_words(part))

    def break_text(self, text: str) -> list[str]:
        """Break text into chunks no larger than the word budget."""
        return [phrase for sentence in self.punctuator.get_sentences(text) for phrase in self.break_sentence(sentence)]

    def break_sentence(self, sentence: str) -> list[str]:
        """Break one sentence into phrase-bounded chunks."""
        return self._merge(self.punctuator.get_phrases(sentence), self.break_phrase)

    def break_phrase(self, phrase: str) -> list[str]:
        """Hard-split a single over-budget phrase into word slices."""
        words = self.punctuator.get_words(phrase)
        split_point = max(1, min(len(words) // 2, self.limit))
        result: list[str] = []
        while words:
            result.append("".join(words[:split_point]))
            words = words[split_point:]
        return result


def phrase_cut_chars() -> str:
    """Return every Unicode phrase-cut char (one source of truth for cutting).

    Reused by :mod:`anishift.services.translation.linebreak` so both tools share
    the same punctuation base instead of hand-written lists.
    """
    return _PHRASE_CUT_CHARS


def chunk_text(text: str, *, method: ChunkMethod = "char", limit: int = DEFAULT_SENTENCE_LENGTH) -> list[str]:
    """Split ``text`` into chunks no larger than ``limit`` in the chosen unit.

    Args:
        text: The full text to chunk.
        method: ``char`` bounds chunks by characters, ``word`` by word count.
        limit: Budget per chunk in the chosen unit.

    Returns:
        Non-empty chunks in reading order.
    """
    punctuator = LatinPunctuator()
    if method == "word":
        return WordBreaker(limit, punctuator).break_text(text)
    return CharBreaker(limit, punctuator).break_text(text)


__all__ = [
    "DEFAULT_SENTENCE_LENGTH",
    "SENTENCE_ENDINGS",
    "ZERO_WIDTH",
    "CharBreaker",
    "ChunkMethod",
    "LatinPunctuator",
    "WordBreaker",
    "chunk_text",
    "phrase_cut_chars",
]
