# 11-elevenreader-tts

Nowy silnik lektora AniShift: ElevenReader (Eleven v4, głosy Piotr Fronczewski i Adam) przez prawdziwy Chrome z
zalogowaną sesją, na wzór repozytorium `ElevenDownloaderPro`. Jeden dokument na odcinek, cięty na klipy kwestii
według czasów znaków i ciszy. `elevenbytes` zostaje zapasem.

## Status

Plan gotowy do akceptacji właściciela (2026-10-25). Trzy rundy review planu: runda 3 bez findingów krytycznych i
poważnych. Kod nie powstał. Następny krok: decyzje D1–D11 (`specification.md`) i faza 0 planu (spike na koncie
właściciela).

## Kolejność czytania

1. [intent.md](intent.md) — problem, kierunek, ryzyko regulaminu, odrzucone drogi.
2. [specification.md](specification.md) — wymagania, zakazy, kryteria sukcesu, otwarte decyzje z rekomendacjami.
3. [file-map.md](file-map.md) — pliki obu repozytoriów i drzewo nowego silnika.
4. [plan.md](plan.md) — stan obu systemów z dowodami, design, fazy F0–F7, testy, git, ryzyka, wycofanie.
5. [reviews/](reviews/) — rundy 1–3 z findingami i poprawkami.

Artefakty powstające w trakcie wykonania: `research/spike-results.md` (faza 0), `research/e1-envelope-drift.md`
(faza 1), `outcomes/01-elevenreader-engine.md` (faza 7).
