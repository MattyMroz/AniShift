# 21-playshift

PlayShift: przenośny odtwarzacz na mpv dla Windows, następca `C:\Users\MattyMroz\Videos\mpv`. Gra lokalne pliki i
linki, ma skróty właściciela bez usterek, polski interfejs, upscaling AnimeJaNai i interpolację RIFE dobraną do
prędkości 2× i monitora, instaluje się jednym poleceniem, aktualizuje sam i nie zostawia śladów w Windows. Dokumenty leżą
tymczasowo w AniShift; po założeniu repo PlayShift (etap 02) przechodzą tam i znikają stąd.

## Status

2026-10-31: research zakończony (6 raportów), specyfikacja, masterplan i plan etapu 01 w wersji roboczej do
akceptacji właściciela. Kod nie powstał. Następny krok: odpowiedzi na D1 i D2 (`specification.md`), potem etap 01
— pomiar silnika AI na RTX 5090 i decyzja bazy.

## Kolejność czytania

1. [specification.md](specification.md) — cel, ustalenia, wymagania, zakazy, otwarte decyzje D1–D18.
2. [masterplan.md](masterplan.md) — rekomendowana droga, sprzeczności w researchu, etapy 01–06.
3. [plans/01-engine-and-base.md](plans/01-engine-and-base.md) — pomiar AnimeJaNai, punkty kontrolne K1 i K2,
   docelowe drzewo katalogów.
4. `research/` — raporty R1–R6: obecny odtwarzacz, buildy i aktualizacje, upscaling, interpolacja i kolor,
   skrypty i UI, architektura i integracja z AniShift.

Artefakty powstające w trakcie etapu 01: `outcomes/01-engine-and-base.md`.
