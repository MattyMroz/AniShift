# 11-elevenreader-tts

Nowy silnik lektora AniShift: ElevenReader (Eleven v4, głosy Piotr Fronczewski i Adam) przez prawdziwy Chrome z
zalogowaną sesją. Cały odcinek jest nagrywany jednym dokumentem i cięty na klipy kwestii w ciszy. W tym samym
workstreamie: głośność lektora mierzona względem oryginału z limiterem, przycinanie ciszy na brzegach klipów i
tempo na głos. `elevenbytes` zostaje zapasem.

## Status

Plan zaktualizowany 2026-10-30 po prototypie (nagranie, cięcie, głośność, tempo na Tantei S2E03). Kod nie powstał;
review tej wersji planu jeszcze się nie odbyło. Następny krok: potwierdzenie D1 (`specification.md`) i faza E0
planu (w tym pilne skopiowanie danych prototypu poza katalog tymczasowy). Edgerunners 02 i 03 są nagrane, a walidacja cięcia na
nich trwa; jej wynik zamyka punkt kontrolny K1.

## Kolejność czytania

1. [intent.md](intent.md) — problem, kierunek, ryzyko regulaminu, odrzucone drogi.
2. [specification.md](specification.md) — ustalenia, wymagania, zakazy, kryteria sukcesu, otwarta decyzja D1.
3. [plan.md](plan.md) — stan z dowodami, decyzja „port czy EDP”, design, etapy E0–E10 z zależnościami i pasami
   zapisu, punkty kontrolne K1–K3.
4. [file-map.md](file-map.md) — pliki źródłowe i dotknięte, z przypisaniem do etapów.

Artefakty powstające w trakcie wykonania: `outcomes/01-elevenreader-engine.md` (E10).
