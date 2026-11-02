# 21-playshift

PlayShift: przenośny odtwarzacz na mpv dla Windows, następca `C:\Users\MattyMroz\Videos\mpv`. Gra lokalne pliki i
linki, ma skróty właściciela bez usterek, polski interfejs, upscaling AnimeJaNai i interpolację RIFE dobraną do
prędkości 2× i monitora, instaluje się jednym poleceniem, aktualizuje sam i nie zostawia śladów w Windows. Dokumenty leżą
tymczasowo w AniShift; po założeniu repo PlayShift (etap 02) przechodzą tam i znikają stąd.

## Status

2026-11-02: research (raporty R1–R6), specyfikacja, masterplan i plan etapu 01 są scalone do `main`
([PR #85](https://github.com/MattyMroz/AniShift/pull/85)). Fazy 0–6 planu etapu 01 są wykonane, a pomiary opisuje
roboczy `outcomes/01-engine-and-base.md`. Czeka ocena właściciela (K1), potem werdykty G5 i G6 oraz decyzje D3–D8.
Kodu PlayShift w AniShift nie ma. Zmiana ścieżek eksperymentu na `workspace/tmp`:
[PR #98](https://github.com/MattyMroz/AniShift/pull/98).

## Kolejność czytania

1. [specification.md](specification.md) — cel, ustalenia, wymagania, zakazy, otwarte decyzje D1–D18.
2. [masterplan.md](masterplan.md) — rekomendowana droga, sprzeczności w researchu, etapy 01–06.
3. [plans/01-engine-and-base.md](plans/01-engine-and-base.md) — pomiar AnimeJaNai, punkty kontrolne K1 i K2,
   docelowe drzewo katalogów.
4. `research/` — raporty R1–R6: obecny odtwarzacz, buildy i aktualizacje, upscaling, interpolacja i kolor,
   skrypty i UI, architektura i integracja z AniShift.

Wynik etapu 01 (roboczy, przed K1): `outcomes/01-engine-and-base.md`.
