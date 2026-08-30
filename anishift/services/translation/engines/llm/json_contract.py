"""Strict JSON contract for LLM translation requests and responses."""

from __future__ import annotations

import json
from typing import Never


class JsonContractError(ValueError):
    """A safe description of an invalid translation response."""


def serialize_translation_request(texts: list[str]) -> str:
    """Serialize subtitle texts to the exact model input contract."""
    subtitles: list[dict[str, int | str]] = [{"id": index, "text": text} for index, text in enumerate(texts)]
    return json.dumps({"subtitles": subtitles}, ensure_ascii=False, separators=(",", ":"))


def parse_translation_response(text: str, expected_count: int) -> list[str]:
    """Validate and parse the exact model output contract."""
    try:
        payload: object = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite_number,
        )
    except json.JSONDecodeError as error:
        msg = "Odpowiedź nie jest jednym poprawnym dokumentem JSON."
        raise JsonContractError(msg) from error

    root = _require_exact_object(payload, {"translations"}, "Obiekt główny")
    translations = root["translations"]
    if not isinstance(translations, list):
        msg = "Pole 'translations' musi być tablicą."
        raise JsonContractError(msg)
    if len(translations) != expected_count:
        msg = f"Tablica 'translations' musi zawierać dokładnie {expected_count} elementów."
        raise JsonContractError(msg)

    parsed: list[str] = []
    identifiers: list[int] = []
    for index, item in enumerate(translations):
        item_object = _require_exact_object(item, {"id", "translated"}, f"Element {index}")
        identifier = item_object["id"]
        translated = item_object["translated"]
        if type(identifier) is not int:
            msg = f"Pole 'id' elementu {index} musi być liczbą całkowitą."
            raise JsonContractError(msg)
        if not isinstance(translated, str):
            msg = f"Pole 'translated' elementu {index} musi być tekstem."
            raise JsonContractError(msg)
        normalized = translated.strip()
        if not normalized:
            msg = f"Pole 'translated' elementu {index} nie może być puste."
            raise JsonContractError(msg)
        identifiers.append(identifier)
        parsed.append(normalized)

    expected_ids = list(range(expected_count))
    if len(set(identifiers)) != len(identifiers):
        msg = "Każde pole 'id' w tablicy 'translations' musi być unikalne."
        raise JsonContractError(msg)
    if identifiers != expected_ids:
        msg = "Pola 'id' muszą występować kolejno od 0, zgodnie z wejściem."
        raise JsonContractError(msg)
    return parsed


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object while rejecting duplicate keys."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            msg = "Obiekt JSON nie może zawierać powtórzonych kluczy."
            raise JsonContractError(msg)
        result[key] = value
    return result


def _reject_non_finite_number(value: str) -> Never:
    """Reject JSON extensions such as NaN and Infinity."""
    msg = f"Wartość '{value}' nie jest dozwolona w JSON."
    raise JsonContractError(msg)


def _require_exact_object(
    value: object,
    expected_keys: set[str],
    location: str,
) -> dict[str, object]:
    """Require one object with exactly the allowed keys."""
    if not isinstance(value, dict):
        msg = f"{location} musi być obiektem JSON."
        raise JsonContractError(msg)
    actual_keys = set(value)
    if actual_keys != expected_keys:
        expected = ", ".join(sorted(expected_keys))
        msg = f"{location} musi zawierać wyłącznie klucze: {expected}."
        raise JsonContractError(msg)
    return value


__all__ = [
    "JsonContractError",
    "parse_translation_response",
    "serialize_translation_request",
]
