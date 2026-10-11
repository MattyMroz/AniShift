"""Release list rows and identity explanations of one episode offer."""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Final

from anishift.application import (
    CandidateNumbering,
    EpisodeOffer,
    EpisodeOfferView,
    IdentityVerdict,
    PolishClass,
    RankedCandidate,
    confidence_text,
    conflict_label,
    quality_text,
)
from anishift.cli.interactive.anime_state import AnimeRow
from anishift.cli.interactive.anime_texts import safe
from anishift.utils.rich_console import format_bytes

__all__ = ["UNKNOWN_PREVIOUS_WARNING", "candidate_reason", "release_rows", "repeat_warning", "suggested_position"]

# ── Constants ─────────────────────────────────────────────────────────────────

UNKNOWN_PREVIOUS_WARNING: Final[str] = "Nie wiem, które wydanie pobrano poprzednio — może to być to samo"
"""Warning shown when the previous order of the episode recorded no release hash."""

_VERDICT_LABELS: Final[dict[IdentityVerdict, str]] = {
    IdentityVerdict.MATCH: "zgodny",
    IdentityVerdict.INSUFFICIENT: "niepewny",
    IdentityVerdict.MISMATCH: "niezgodny",
}
"""Polish identity labels, without confidence percentages."""

_VERDICT_FALLBACKS: Final[dict[IdentityVerdict, str]] = {
    IdentityVerdict.MATCH: "Nazwa wskazuje wybrany odcinek.",
    IdentityVerdict.INSUFFICIENT: "Nie można jednoznacznie ustalić tożsamości odcinka.",
    IdentityVerdict.MISMATCH: "Nazwa wskazuje inny materiał.",
}
"""Explanation of each verdict whose H1 reason has no Polish text."""

_REASON_TEXTS: Final[dict[str, str]] = {
    "Mapped absolute number exceeds the local episode range under a specific title.": (
        "Numer absolutny wykracza poza zakres odcinków tego wpisu."
    ),
    "Named season, local episode and catalog episode title agree.": (
        "Sezon, numer lokalny i katalogowy tytuł odcinka są zgodne."
    ),
    "Season marker conflicts with the target numbering system.": (
        "Oznaczenie sezonu jest sprzeczne z numeracją szukanego odcinka."
    ),
    "Part/cour marker conflicts with the target.": "Oznaczenie części jest sprzeczne z wybranym wpisem.",
    "A franchise alias does not identify this installment.": "Nazwa franczyzy nie wskazuje jednoznacznie tego wpisu.",
    "The required part/cour is not established.": "Nie ustalono wymaganej części sezonu.",
    "Explicit mapped episode differs from target.": "Podany numer katalogowy wskazuje inny odcinek.",
    "Catalog episode title belongs to another episode.": "Tytuł w nazwie należy do innego odcinka.",
    "Work anchor and exact mapped season/episode match; residual is technical or catalogued.": (
        "Tytuł oraz katalogowe numery sezonu i odcinka są zgodne; pozostały tekst jest rozpoznany."
    ),
    "Movie segment or numbering requires a more specific identity anchor.": (
        "Część lub numer filmu wymaga dokładniejszego potwierdzenia tożsamości."
    ),
    "Movie title matches with compatible year and no unidentified residual.": (
        "Tytuł filmu jest zgodny, rok nie jest sprzeczny i nie ma nierozpoznanego tekstu."
    ),
    "OVA/special needs a mapped episode or catalog episode title.": (
        "Dodatek wymaga numeru katalogowego lub katalogowego tytułu odcinka."
    ),
    "No unambiguous selected episode number.": "Brak jednoznacznego numeru wybranego odcinka.",
    "Bare number is not the local episode; absolute numbering is not established.": (
        "Numer nie pasuje do odcinka lokalnego; nie potwierdzono numeracji absolutnej."
    ),
    "Local and mapped numbering conflict.": "Numeracja lokalna i katalogowa są sprzeczne.",
    "Mapped numbering cannot be checked without target numbering.": (
        "Bez numeracji szukanego odcinka nie da się sprawdzić numeru katalogowego."
    ),
    "Mapped number equals the target absolute number; numbering is ambiguous.": (
        "Numer w nazwie równa się numerowi absolutnemu odcinka; numeracja jest niejednoznaczna."
    ),
    "Specific work title and local episode match; residual is technical or catalogued.": (
        "Dokładny tytuł i numer lokalny odcinka są zgodne; pozostały tekst jest rozpoznany."
    ),
    "Package directory explicitly identifies Plex extra material.": "Katalog paczki wskazuje materiał dodatkowy Plex.",
    "Package explicitly identifies a neighboring work.": "Paczka wskazuje inny powiązany tytuł.",
    "Package explicitly identifies a different season.": "Paczka wskazuje inny sezon.",
    "Package explicitly identifies a different part/cour.": "Paczka wskazuje inną część sezonu.",
    "Package explicitly identifies a different final season.": "Paczka wskazuje inny sezon finałowy.",
    "Package contains an unresolved sequel qualifier.": "Paczka zawiera niejednoznaczny dopisek sequela.",
    "Package localized season conflicts with the target or is unresolved.": (
        "Obcojęzyczne oznaczenie sezonu w paczce jest sprzeczne lub niejednoznaczne."
    ),
    "Package Roman season/part conflicts with the target or is unresolved.": (
        "Rzymski numer sezonu lub części w paczce jest sprzeczny lub niejednoznaczny."
    ),
    "Package ordinal part/cour conflicts with the target.": "Numer porządkowy części w paczce wskazuje inną część.",
    "Package localized movie format conflicts with the target.": (
        "Obcojęzyczne oznaczenie filmu w paczce nie pasuje do wybranego wpisu."
    ),
    "Package contains an unresolved continuation marker.": "Paczka zawiera niejednoznaczne oznaczenie ciągu dalszego.",
    "Package contains an uncatalogued title suffix.": "Paczka zawiera końcówkę tytułu nieznaną katalogowi.",
    "Package explicitly identifies a different language-specific media format.": (
        "Obcojęzyczne oznaczenie w paczce wskazuje inny rodzaj materiału."
    ),
    "Package season declaration conflicts with the target or is unresolved.": (
        "Deklaracja sezonu w paczce jest sprzeczna lub niejednoznaczna."
    ),
    "Package Russian season declaration is unresolved.": "Rosyjskie oznaczenie sezonu w paczce jest niejednoznaczne.",
    "Package explicitly identifies non-episode material.": "Paczka wskazuje materiał inny niż odcinek.",
    "Package explicitly identifies a different media type.": "Paczka wskazuje inny rodzaj materiału.",
    "Package year conflicts with target metadata.": "Rok paczki jest sprzeczny z metadanymi wybranego wpisu.",
    "Package explicitly identifies a numbered sequel.": "Paczka wskazuje numerowaną kontynuację.",
    "Titleless file lacks an unambiguous nearest work directory or single-work release.": (
        "Plik bez tytułu nie ma jednoznacznego katalogu ani wydania jednego tytułu."
    ),
    "Selected file or work directory identifies a neighboring catalogue work.": (
        "Wybrany plik lub katalog wskazuje inny tytuł katalogowy."
    ),
    "Selected directory has a numbered season conflicting with the target.": (
        "Numer sezonu w wybranym katalogu jest sprzeczny z wybranym odcinkiem."
    ),
    "Selected TV variant conflicts with the target editing variant.": (
        "Wariant telewizyjny pliku jest sprzeczny z wybraną wersją montażową."
    ),
    "Release editing variant is not established for the target episode.": (
        "Nie potwierdzono wersji montażowej wydania dla tego odcinka."
    ),
    "Malformed candidate metadata.": "Metadane wydania mają niepoprawny format.",
    "No selected file.": "Brak wskazanego pliku.",
    "Selected file has no allowed video extension.": "Wybrany plik nie ma dozwolonego rozszerzenia wideo.",
    "Malformed target or archived identity metadata.": "Metadane celu lub tożsamości mają niepoprawny format.",
    "Selected filename has an explicit Plex extra suffix.": "Nazwa pliku oznacza materiał dodatkowy Plex.",
    "Selected residual explicitly identifies non-episode material.": (
        "Dodatkowy tekst nazwy wskazuje materiał inny niż odcinek."
    ),
    "Unresolved leading bracket is the nearest identity context.": (
        "Nierozpoznany początkowy nawias uniemożliwia ustalenie tożsamości."
    ),
    "Selected filename more specifically identifies a neighboring work.": (
        "Dokładniejsza nazwa pliku wskazuje inny powiązany tytuł."
    ),
    "Filename year is missing from or conflicts with runtime target metadata.": (
        "Roku z nazwy pliku nie ma w metadanych celu albo jest z nimi sprzeczny."
    ),
    "Unconsumed filename text is neither technical metadata nor a catalog episode title.": (
        "Pozostały tekst nazwy nie jest metadanymi technicznymi ani katalogowym tytułem odcinka."
    ),
    "Release group numbers this season from 1.": "Ta grupa numeruje odcinki tego sezonu od 1.",
}
"""Translate every frozen H1 explanation and the release group numbering explanation at the UI boundary."""


def release_rows(
    candidates: tuple[RankedCandidate, ...], offer: EpisodeOffer | None, *, searching: bool
) -> tuple[AnimeRow, ...]:
    """Return the release list rows, or the one row saying the list is still searched or empty."""
    suggested: RankedCandidate | None = (
        offer.candidates[offer.suggestion] if offer is not None and offer.suggestion is not None else None
    )
    episode: str = "" if offer is None else f" · E{offer.key.number}"
    return tuple(
        AnimeRow(
            item.stream.info_hash,
            _release_title(item, episode),
            image=f"{item.traits.resolution}p" if item.traits.resolution else "?",
            size=_candidate_size(item),
            language=_language(item),
            seeds=str(item.stream.seeders) if item.stream.seeders is not None else "?",
            quality=quality_text(item),
            confidence=_candidate_confidence(item, suggested=item == suggested),
            detail=candidate_reason(item) + " · " + _candidate_details(item),
            eligible=item.supported is not False,
            uncertain=item.identity.verdict is not IdentityVerdict.MATCH,
            suggested=item == suggested,
            note=f"z paczki: {item.stream.release}" if item.pack and _pack_file(item) else "",
        )
        for item in candidates
    ) or (AnimeRow("empty", "Szukam…" if searching else "Brak wydania", eligible=False),)


def suggested_position(offer: EpisodeOffer | None, candidates: tuple[RankedCandidate, ...]) -> int:
    """Return the shown row of the offer's suggestion, else the first row."""
    if offer is None or offer.suggestion is None:
        return 0
    suggested: RankedCandidate = offer.candidates[offer.suggestion]
    return next((index for index, item in enumerate(candidates) if item == suggested), 0)


def repeat_warning(view: EpisodeOfferView | None) -> tuple[str, ...]:
    """Return the warnings of an offer that repeats or may duplicate an earlier order."""
    if view is None or (not view.conflict and view.previous_admission_id is None):
        return ()
    warning: str = (
        f"E{view.offer.key.number} może być już zlecony · Obecne pliki zostają"
        if view.conflict
        else "Obecne pliki zostają"
    )
    return (warning, *((UNKNOWN_PREVIOUS_WARNING,) if view.unknown_previous else ()))


def candidate_reason(item: RankedCandidate) -> str:
    """Return the Polish identity verdict of one release with its explanation."""
    verdict: IdentityVerdict = item.identity.verdict
    return f"{_VERDICT_LABELS[verdict]}: {_REASON_TEXTS.get(item.identity.reason, _VERDICT_FALLBACKS[verdict])}"


def _release_title(item: RankedCandidate, episode: str) -> str:
    if not item.pack:
        return item.stream.release
    file: str | None = _pack_file(item)
    return f"z paczki · {file}" if file else f"z paczki{episode} · {item.stream.release}"


def _pack_file(item: RankedCandidate) -> str | None:
    path: str | None = item.stream.path or item.stream.file_name
    return PureWindowsPath(path).name if path else None


def _language(item: RankedCandidate) -> str:
    return (
        " · ".join(
            label
            for label, present in (
                ("PL", item.traits.polish is not PolishClass.NONE),
                ("EN", item.traits.english_subtitles),
            )
            if present
        )
        or "—"
    )


def _candidate_details(item: RankedCandidate) -> str:
    details: list[str] = []
    if item.stream.path or item.stream.file_name:
        details.append(f"Plik: {safe(item.stream.path or item.stream.file_name or '')}")
    if item.release_name_only:
        details.append("bez nazwy pliku")
    if item.traits.platform:
        details.append("wydanie z platformy")
    if item.supported is False:
        details.append("format nieobsługiwany")
    if item.ambiguous:
        details.append("niejednoznaczny plik")
    if item.traits.dub_only:
        details.append("sam dubbing")
    details.extend(_candidate_numbering(item.numbering))
    details.append(
        "Kalibracja pewności potwierdzona tylko dla korpusu E1. "
        "Dla nowych źródeł i ocen bez nazwy pliku: estymata bez potwierdzonej kalibracji."
    )
    return " · ".join(details)


def _candidate_size(item: RankedCandidate) -> str:
    if item.stream.file_size is not None:
        return format_bytes(item.stream.file_size, precision=1)
    return "?" if item.pack else safe(item.stream.size_text or "?")


def _candidate_confidence(item: RankedCandidate, *, suggested: bool) -> str:
    if item.conflict:
        return conflict_label(item.identity)
    value: str = confidence_text(item) or "?"
    return value + (" · niepewne" if suggested and item.identity.verdict is not IdentityVerdict.MATCH else "")


def _candidate_numbering(evidence: CandidateNumbering | None) -> list[str]:
    if evidence is None:
        return []
    mode: str = {"mapped": "S/E", "plain": "bez znacznika numeracji", "missing": "brak numeru"}[evidence.mode]
    return [
        f"Odczyt H1 ({mode}): sezon {evidence.season if evidence.season is not None else '?'}, "
        f"odcinek {evidence.number if evidence.number is not None else '?'}, "
        f"część {evidence.part if evidence.part is not None else '?'}",
        f"Cel: lokalny {evidence.local if evidence.local is not None else '?'}; "
        f"S/E: sezon {evidence.target_season if evidence.target_season is not None else '?'}, "
        f"odcinek {evidence.episode if evidence.episode is not None else '?'}; "
        f"absolutny {evidence.absolute if evidence.absolute is not None else '?'}; "
        f"sezon w tytule {evidence.named_season if evidence.named_season is not None else '?'}; "
        f"część {evidence.target_part if evidence.target_part is not None else '?'}",
    ]
