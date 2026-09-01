from __future__ import annotations

import pytest

from anishift.services.translation.engines.llm.line_contract import (
    ViolationKind,
    parse_response,
    serialize_request,
)


def test_serialize_request_uses_exact_contract() -> None:
    serialized = serialize_request([(0, "Ale tu cicho."), (1, "Chyba tylko ja ocalałem.")])
    assert serialized == "[0] Ale tu cicho.\n[1] Chyba tylko ja ocalałem."


def test_serialize_request_keeps_original_numbers_for_a_repair_subset() -> None:
    assert serialize_request([(7, "siedem"), (12, "dwanaście")]) == "[7] siedem\n[12] dwanaście"


def test_serialize_request_of_nothing_is_empty() -> None:
    assert serialize_request([]) == ""


def test_serialize_request_escapes_a_line_break_so_numbering_cannot_shift() -> None:
    serialized = serialize_request([(0, "pierwszy\ndrugi"), (1, "potem")])
    assert serialized == "[0] pierwszy\\ndrugi\n[1] potem"
    assert len(serialized.splitlines()) == 2


def test_serialize_request_escapes_a_carriage_return() -> None:
    serialized = serialize_request([(0, "a\r\nb")])
    assert serialized == "[0] a\\r\\nb"
    assert len(serialized.splitlines()) == 1


def test_serialize_request_escapes_a_backslash_before_the_line_break() -> None:
    assert serialize_request([(0, "a\\nb")]) == "[0] a\\\\nb"


@pytest.mark.parametrize(
    "text",
    [
        "zwykły tekst",
        "pierwszy\ndrugi",
        "a\\nb",
        "back\\slash",
        "wiele\\\\ukośników",
        "karetka\rpowrót",
        "windows\r\nkoniec",
        "ASS \\N przełamanie",
        "nawias [5] w środku",
        "tabulator\tw środku",
        "Zażółć gęślą jaźń",
        "kropki... i myślnik —",
        "[",
        "\\",
    ],
)
def test_escape_round_trip_preserves_text_exactly(text: str) -> None:
    serialized = serialize_request([(0, text)])
    assert len(serialized.splitlines()) == 1
    parsed = parse_response(serialized, [0])
    assert parsed.violation is None
    assert parsed.entries[0] == text


def test_parse_response_accepts_a_complete_answer() -> None:
    parsed = parse_response("[0] Zaczekaj chwilę.\n[1] Chodźmy już.", [0, 1])
    assert parsed.violation is None
    assert parsed.entries == {0: "Zaczekaj chwilę.", 1: "Chodźmy już."}


def test_parse_response_ignores_blank_lines_and_code_fences() -> None:
    parsed = parse_response("```text\n\n[0] jeden\n\n[1] dwa\n```\n", [0, 1])
    assert parsed.violation is None
    assert parsed.entries == {0: "jeden", 1: "dwa"}


def test_parse_response_ignores_a_fence_with_a_language_tag() -> None:
    parsed = parse_response("```json\n[0] jeden\n```", [0])
    assert parsed.violation is None
    assert parsed.entries == {0: "jeden"}


def test_parse_response_accepts_windows_line_endings() -> None:
    parsed = parse_response("[0] jeden\r\n[1] dwa\r\n", [0, 1])
    assert parsed.violation is None
    assert parsed.entries == {0: "jeden", 1: "dwa"}


def test_parse_response_accepts_a_missing_space_after_the_number() -> None:
    parsed = parse_response("[0]jeden", [0])
    assert parsed.violation is None
    assert parsed.entries == {0: "jeden"}


def test_parse_response_accepts_indented_lines() -> None:
    parsed = parse_response("   [0] jeden\n\t[1] dwa", [0, 1])
    assert parsed.violation is None
    assert parsed.entries == {0: "jeden", 1: "dwa"}


def test_parse_response_keeps_brackets_inside_a_translation() -> None:
    parsed = parse_response("[0] tekst [5] w środku", [0])
    assert parsed.violation is None
    assert parsed.entries == {0: "tekst [5] w środku"}


def test_parse_response_accepts_leading_zeros_in_the_number() -> None:
    parsed = parse_response("[007] siedem", [7])
    assert parsed.violation is None
    assert parsed.entries == {7: "siedem"}


def test_parse_response_accepts_large_numbers() -> None:
    parsed = parse_response("[7524] ostatni", [7524])
    assert parsed.violation is None
    assert parsed.entries == {7524: "ostatni"}


def test_parse_response_deduplicates_repeated_expected_numbers() -> None:
    parsed = parse_response("[0] jeden", [0, 0])
    assert parsed.violation is None
    assert parsed.entries == {0: "jeden"}


def test_a_repair_subset_validates_against_its_own_numbers() -> None:
    parsed = parse_response("[7] siedem\n[12] dwanaście", [7, 12])
    assert parsed.violation is None
    assert parsed.entries == {7: "siedem", 12: "dwanaście"}


def test_order_follows_the_request_not_the_numeric_value() -> None:
    parsed = parse_response("[12] dwanaście\n[7] siedem", [12, 7])
    assert parsed.violation is None
    assert parsed.entries == {7: "siedem", 12: "dwanaście"}


@pytest.mark.parametrize("response", ["", "   ", "\n\n", "```\n```"])
def test_a_response_without_numbered_lines_invalidates_the_whole_batch(response: str) -> None:
    parsed = parse_response(response, [0, 1])
    assert parsed.entries == {}
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.EMPTY_RESPONSE
    assert parsed.violation.numbers == ()


def test_a_stray_line_invalidates_only_the_number_it_follows() -> None:
    parsed = parse_response("[0] jeden\n[1] pierwsza połowa\nurwana druga połowa\n[2] trzy", [0, 1, 2])
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.MALFORMED_LINE
    assert parsed.violation.numbers == (1,)
    assert parsed.entries == {0: "jeden", 2: "trzy"}


def test_a_stray_line_before_any_number_invalidates_the_whole_batch() -> None:
    parsed = parse_response("Oto tłumaczenia:\n[0] jeden\n[1] dwa", [0, 1])
    assert parsed.entries == {}
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.MALFORMED_LINE
    assert parsed.violation.numbers == ()


def test_a_trailing_comment_invalidates_only_the_last_number() -> None:
    parsed = parse_response("[0] jeden\n[1] dwa\nMam nadzieję, że pomogłem!", [0, 1])
    assert parsed.violation is not None
    assert parsed.violation.numbers == (1,)
    assert parsed.entries == {0: "jeden"}


@pytest.mark.parametrize("line", ["[-1] minus", "(0) nawias", "0. kropka", "[a] litera", "[] puste"])
def test_a_line_outside_the_pattern_is_malformed(line: str) -> None:
    parsed = parse_response(f"[0] jeden\n{line}", [0])
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.MALFORMED_LINE


def test_a_number_outside_the_request_invalidates_the_number_it_follows() -> None:
    parsed = parse_response("[0] jeden\n[1] dwa\n[2] nadmiarowe", [0, 1])
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.UNKNOWN_NUMBER
    assert parsed.violation.numbers == (1,)
    assert parsed.entries == {0: "jeden"}


def test_a_repeated_number_drops_both_copies() -> None:
    parsed = parse_response("[0] jeden\n[0] inaczej\n[1] dwa", [0, 1])
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.DUPLICATE_NUMBER
    assert parsed.violation.numbers == (0,)
    assert parsed.entries == {1: "dwa"}


def test_a_number_repeated_three_times_stays_rejected() -> None:
    parsed = parse_response("[0] raz\n[0] dwa\n[0] trzy", [0])
    assert parsed.violation is not None
    assert parsed.entries == {}


@pytest.mark.parametrize("body", ["", " ", "   ", "\t"])
def test_an_empty_translation_invalidates_its_own_number(body: str) -> None:
    parsed = parse_response(f"[0] jeden\n[1] {body}\n[2] trzy", [0, 1, 2])
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.EMPTY_TRANSLATION
    assert parsed.violation.numbers == (1,)
    assert parsed.entries == {0: "jeden", 2: "trzy"}


def test_reordered_numbers_invalidate_the_whole_batch() -> None:
    parsed = parse_response("[0] jeden\n[2] trzy\n[1] dwa", [0, 1, 2])
    assert parsed.entries == {}
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.WRONG_ORDER
    assert parsed.violation.numbers == ()


def test_a_missing_number_is_reported_without_any_other_violation() -> None:
    parsed = parse_response("[0] jeden\n[2] trzy", [0, 1, 2])
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.MISSING_NUMBER
    assert parsed.violation.numbers == (1,)
    assert parsed.entries == {0: "jeden", 2: "trzy"}


def test_numbering_from_one_instead_of_zero_loses_every_number() -> None:
    parsed = parse_response("[1] jeden\n[2] dwa", [0, 1])
    assert parsed.entries == {}
    assert parsed.violation is not None
    assert parsed.violation.numbers == (0, 1)


def test_the_first_detected_violation_names_the_kind() -> None:
    parsed = parse_response("[0] jeden\nurwane\n[0] jeszcze raz", [0])
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.MALFORMED_LINE
    assert parsed.entries == {}


def test_an_unrequested_number_before_any_valid_one_invalidates_the_whole_batch() -> None:
    parsed = parse_response("[9] obce\n[0] jeden", [0])
    assert parsed.entries == {}
    assert parsed.violation is not None
    assert parsed.violation.kind is ViolationKind.UNKNOWN_NUMBER
    assert parsed.violation.numbers == ()


def test_diagnosis_names_the_numbers_to_repair() -> None:
    parsed = parse_response("[0] jeden", [0, 1, 2])
    assert parsed.violation is not None
    assert "1, 2" in parsed.violation.message


def test_diagnosis_falls_back_to_a_count_for_many_numbers() -> None:
    parsed = parse_response("[0] jeden", range(40))
    assert parsed.violation is not None
    assert "39" in parsed.violation.message
    assert "1, 2, 3" not in parsed.violation.message


def test_diagnosis_never_leaks_subtitle_text() -> None:
    dialogue = "TAJNA KWESTIA BOHATERA"
    parsed = parse_response(f"[0] {dialogue}\nurwana linia", [0, 1])
    assert parsed.violation is not None
    assert dialogue not in parsed.violation.message


@pytest.mark.parametrize(
    "response",
    [
        "",
        "[0] jeden\nurwane",
        "[0] jeden\n[9] obce",
        "[0] jeden\n[0] znowu",
        "[0]   ",
        "[1] dwa\n[0] jeden",
        "[0] jeden",
    ],
)
def test_every_violation_carries_a_polish_diagnosis(response: str) -> None:
    parsed = parse_response(response, [0, 1])
    assert parsed.violation is not None
    assert parsed.violation.message.strip()
    assert parsed.violation.message.endswith(".")
