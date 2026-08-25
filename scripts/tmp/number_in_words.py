"""
NumberInWords — converts numbers into Polish words.

Example:
    number_in_words = NumberInWords()
    print(number_in_words.number_in_words(123))
    # "sto dwadzieścia trzy"
    print(number_in_words.convert_numbers_in_text('Rozdział 69'))
    # "Rozdział sześćdziesiąt dziewięć"
"""

import re
from dataclasses import dataclass, field
from typing import List, Union


@dataclass
class NumberInWords:
    """Converts numbers into Polish words."""

    UNITS: list = field(default_factory=lambda: [
        "", "jeden", "dwa", "trzy",
        "cztery", "pięć", "sześć",
        "siedem", "osiem", "dziewięć"
    ])
    TENS: list = field(default_factory=lambda: [
        "", "dziesięć", "dwadzieścia", "trzydzieści",
        "czterdzieści", "pięćdziesiąt", "sześćdziesiąt",
        "siedemdziesiąt", "osiemdziesiąt", "dziewięćdziesiąt"
    ])
    TEENS: list = field(default_factory=lambda: [
        "dziesięć", "jedenaście", "dwanaście",
        "trzynaście", "czternaście", "piętnaście",
        "szesnaście", "siedemnaście", "osiemnaście",
        "dziewiętnaście"
    ])
    HUNDREDS: list = field(default_factory=lambda: [
        "", "sto", "dwieście", "trzysta",
        "czterysta", "pięćset", "sześćset",
        "siedemset", "osiemset", "dziewięćset"
    ])
    BIG: list = field(default_factory=lambda: [
        ["x", "x", "x"],
        ["tysiąc", "tysiące", "tysięcy"],
        ["milion", "miliony", "milionów"],
        ["miliard", "miliardy", "miliardów"],
        ["bilion", "biliony", "bilionów"],
    ])
    ZLOTYS: list = field(default_factory=lambda: [
        "złoty", "złote", "złotych"
    ])
    GROSZES: list = field(default_factory=lambda: [
        "grosz", "grosze", "groszy"
    ])

    def _number_in_words_3digits(self, number: int) -> str:
        unit: int = number % 10
        ten: int = (number // 10) % 10
        hundred: int = (number // 100) % 10
        words: List[str] = []

        if hundred > 0:
            words.append(self.HUNDREDS[hundred])
        if ten == 1:
            words.append(self.TEENS[unit])
        else:
            if ten > 0:
                words.append(self.TENS[ten])
            if unit > 0:
                words.append(self.UNITS[unit])
        return " ".join(words)

    def _case(self, number: int) -> int:
        if number == 1:
            return 0
        unit: int = number % 10
        return 2 if (number // 10) % 10 == 1 and unit > 1 or not 2 <= unit <= 4 else 1

    def number_in_words(self, number: Union[int, float, str]) -> str:
        if isinstance(number, (int, float)):
            number = str(number)

        if '.' in number:
            parts = number.split('.')
            if all(len(p) == 3 for p in parts[1:]):
                integer_part = int(number.replace('.', ''))
                decimal_part = 0
            else:
                integer_part, decimal_part = int(parts[0].replace(',', '')), int(parts[1])
        elif ',' in number:
            parts = number.split(',')
            if all(len(p) == 3 for p in parts[1:]):
                integer_part = int(number.replace(',', ''))
                decimal_part = 0
            else:
                integer_part, decimal_part = int(parts[0].replace('.', '')), int(parts[1])
        else:
            integer_part = int(number)
            decimal_part = 0

        words: List[str] = []
        if integer_part == 0:
            words.append("zero")
        else:
            triples: List[int] = []
            while integer_part > 0:
                triples.append(integer_part % 1000)
                integer_part //= 1000
            for i, n in enumerate(triples):
                if n > 0:
                    if i > 0 and n == 1:
                        p: int = self._case(n)
                        w: str = self.BIG[i][p]
                        words.append(w)
                    elif i > 0:
                        p: int = self._case(n)
                        w: str = self.BIG[i][p]
                        words.append(
                            self._number_in_words_3digits(n) + " " + w)
                    else:
                        words.append(self._number_in_words_3digits(n))
            words.reverse()

        if decimal_part != 0:
            words.extend(
                ("przecinek", self.number_in_words(str(decimal_part))))
        return " ".join(words)

    def thing_in_words(self, number: int, thing: List[str]) -> str:
        return self.number_in_words(number) + " " + thing[self._case(number)]

    def amount_in_words(self, number: float, fmt: int = 0) -> str:
        lzlotys: int = int(number)
        lgroszes: int = int(number * 100 + 0.5) % 100
        if fmt != 0:
            grosz_in_words: str = self.thing_in_words(lgroszes, self.GROSZES)
        else:
            grosz_in_words: str = "%d/100" % lgroszes
        return self.thing_in_words(lzlotys, self.ZLOTYS) + " " + grosz_in_words

    def convert_numbers_in_text(self, text: str) -> str:
        result: str = ''
        number: str = ''
        special_chars: List[str] = ['!', '@', '#', '$', '%', '^', '&', '*',
                                    '(', ')', '_', '+', '~', '`', '{', '}', '|', '[', ']', '\\', ':', '"', ';', "'", '<', '>', '?', '/', '-']
        for i, char in enumerate(text):
            if char.isdecimal() or (char in ['.', ','] and i > 0 and i < len(text) - 1 and text[i-1].isdecimal() and text[i+1].isdecimal()):
                number += char
            else:
                if number and number not in special_chars:
                    for special_char in special_chars:
                        if number.count(special_char) > 1:
                            for part in number.split(special_char):
                                number_in_words_str: str = self.number_in_words(
                                    part)
                                result += number_in_words_str + special_char
                            result = result[:-1]
                            break
                    else:
                        comma_parts = number.split(',')
                        dot_parts = number.split('.')
                        is_thousands = (
                            (len(comma_parts) > 1 and all(len(p) == 3 for p in comma_parts[1:])) or
                            (len(dot_parts) > 1 and all(len(p) == 3 for p in dot_parts[1:]))
                        )
                        if number.count('.') == 1 or number.count(',') == 1 or is_thousands:
                            number_in_words_str: str = self.number_in_words(
                                number)
                            if (result and not result[-1].isspace() and result[-1] not in special_chars):
                                result += ' '
                            result += number_in_words_str
                        else:
                            parts: List[str] = re.split(r'(\D)', number)
                            for part in parts:
                                if part.isdecimal():
                                    number_in_words_str: str = self.number_in_words(
                                        part)
                                    if (result and not result[-1].isspace() and result[-1] not in special_chars):
                                        result += ' '
                                    result += number_in_words_str
                                else:
                                    result += part
                    if (i < len(text) - 1 and not text[i].isspace() and text[i] not in special_chars):
                        result += ' '
                    number = ''
                result += char
        if number and number not in special_chars:
            number_in_words_str: str = self.number_in_words(number)
            if (result and not result[-1].isspace() and result[-1] not in special_chars):
                result += ' '
            result += number_in_words_str
        return result
