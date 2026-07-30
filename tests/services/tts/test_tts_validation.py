from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from anishift.services.tts import SpeechBatch, SpeechRequest, TtsInputError
from anishift.services.tts.validation import is_speech_text, validate_speech_batch

VALID_REQUEST = SpeechRequest(
    request_id="spoken-0",
    text="Zażółć gęślą jaźń.",
    request_rank=0,
)
VALID_BATCH = SpeechBatch(
    scope_id="episode-a1b2c3",
    batch_rank=0,
    requests=(VALID_REQUEST,),
)


def test_valid_batch_preserves_neutral_values() -> None:
    assert validate_speech_batch(VALID_BATCH) is VALID_BATCH


@pytest.mark.parametrize(
    "scope_id",
    [
        "",
        ".",
        "..",
        "episode.name",
        "episode/name",
        "episode\\name",
        "episode:name",
        " trailing",
        "CON",
        "lpt9",
        "a" * 65,
    ],
)
def test_batch_rejects_unsafe_scope_id(scope_id: str) -> None:
    with pytest.raises(TtsInputError):
        validate_speech_batch(replace(VALID_BATCH, scope_id=scope_id))


def test_batch_rejects_invalid_runtime_contract_types() -> None:
    with pytest.raises(TtsInputError):
        validate_speech_batch(cast("SpeechBatch", object()))
    with pytest.raises(TtsInputError):
        validate_speech_batch(replace(VALID_BATCH, scope_id=cast("str", 1)))
    with pytest.raises(TtsInputError):
        validate_speech_batch(replace(VALID_BATCH, batch_rank=True))
    with pytest.raises(TtsInputError):
        validate_speech_batch(
            replace(VALID_BATCH, requests=cast("tuple[SpeechRequest, ...]", [])),
        )
    with pytest.raises(TtsInputError):
        validate_speech_batch(
            replace(
                VALID_BATCH,
                requests=(cast("SpeechRequest", object()),),
            ),
        )


def test_batch_rejects_invalid_request_runtime_types() -> None:
    invalid_requests = (
        replace(VALID_REQUEST, request_id=cast("str", 1)),
        replace(VALID_REQUEST, text=cast("str", 1)),
        replace(VALID_REQUEST, request_rank=True),
    )

    for request in invalid_requests:
        with pytest.raises(TtsInputError):
            validate_speech_batch(replace(VALID_BATCH, requests=(request,)))


def test_batch_rejects_negative_batch_rank() -> None:
    with pytest.raises(TtsInputError):
        validate_speech_batch(replace(VALID_BATCH, batch_rank=-1))


def test_batch_rejects_duplicate_request_ids() -> None:
    duplicate = replace(VALID_REQUEST, request_rank=1)
    batch = replace(VALID_BATCH, requests=(VALID_REQUEST, duplicate))

    with pytest.raises(TtsInputError):
        validate_speech_batch(batch)


def test_batch_rejects_empty_request_id_and_negative_rank() -> None:
    with pytest.raises(TtsInputError):
        validate_speech_batch(
            replace(VALID_BATCH, requests=(replace(VALID_REQUEST, request_id=""),)),
        )
    with pytest.raises(TtsInputError):
        validate_speech_batch(
            replace(VALID_BATCH, requests=(replace(VALID_REQUEST, request_rank=-1),)),
        )


@pytest.mark.parametrize(
    "text",
    [
        r"{\i1}Tekst",
        r"Pierwsza\Ndruga",
        r"Pierwsza\ndruga",
        r"Pierwsza\hDruga",
        "<i>Tekst</i>",
        "Pierwsza\nDruga",
        "Pierwsza\rDruga",
        "Pierwsza\vDruga",
        "Pierwsza\fDruga",
        "Pierwsza\u0085Druga",
        "Pierwsza\u2028Druga",
        "Pierwsza\u2029Druga",
        "Pierwsza\tDruga",
        "Pierwsza\x00Druga",
        "m 0 0 l 10 10",
        "m 0 0 l 10 10 20 20",
        "m 0 0 b 1 2 3 4 5 6",
        "m 0 0 l 10 10 c",
        "m -0.5 0 s 10 10 20 20 30 30 p 40 40 c",
    ],
)
def test_batch_rejects_subtitle_artifacts_instead_of_cleaning_them(text: str) -> None:
    request = replace(VALID_REQUEST, text=text)

    with pytest.raises(TtsInputError) as exc_info:
        validate_speech_batch(replace(VALID_BATCH, requests=(request,)))

    assert exc_info.value.context.details["request_id"] == request.request_id


@pytest.mark.parametrize(
    "text",
    [
        "{tekst}",
        "2 < 3 > 1",
        "Naciśnij M 0 0.",
        "Emoji 👨‍👩‍👧‍👦 zostaje.",
    ],
)
def test_batch_accepts_plain_text_that_resembles_markup(text: str) -> None:
    request = replace(VALID_REQUEST, text=text)

    assert validate_speech_batch(replace(VALID_BATCH, requests=(request,))).requests == (request,)


@pytest.mark.parametrize("text", ["", "   ", "...", "!", "?!", "—"])
def test_punctuation_only_text_is_not_speech(text: str) -> None:
    assert not is_speech_text(text)


@pytest.mark.parametrize("text", ["A", "7", "O!", "Ja...", "Ł"])
def test_letters_and_numbers_are_speech(text: str) -> None:
    assert is_speech_text(text)
