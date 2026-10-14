# Etap 0: wzorzec i pomiar bazowy

Status: projekt do akceptacji właściciela (2026-10-15). [Masterplan](../masterplan.md).

## Rezultat

- Trzy odcinki wzorca z zamrożonym wejściem.
- Arkusz ocen właściciela.
- Narzędzie pomiaru, które z wyniku jednego przebiegu liczy metryki z masterplanu.
- Zapisany pomiar bazowy dla obecnego kodu (`main` @ `f9b0dd9`).

## Wybór odcinków (decyzja właściciela)

Trzy odcinki z biblioteki właściciela, każdy z innym głównym problemem:
1. **Dużo postaci i dialogów:** sprawdza imiona i rodzaj gramatyczny.
2. **Fansub ASS z dużą liczbą szyldów i typesettingu:** sprawdza szyldy w lektorze i dopasowanie do ramki.
3. **Odcinek z napisami do OP/ED** (karaoke albo osobny styl piosenki): sprawdza piosenki w lektorze.

Najlepiej, żeby były to tytuły, które właściciel ogląda, a wydania pochodziły z automatu.

Propozycja z pomiaru źródłowych napisów w `workspace/ready/` (2026-10-15):
1. `Sasaki.and.Peeps.S02E01` — 660 linii, wiele postaci obu płci, `Actor` wypełnione, brak polskiej ścieżki.
2. `[Erai-raws] Seihantai na Kimi to Boku 2nd Season - 08` — najwięcej szyldów: 128 linii z `\pos`, znaczniki `SIGN` (86) i `SFX` (49); ma polską ścieżkę, więc wzorzec tłumaczy z angielskiej.
3. `[SubsPlus+] I'm Dating a Dark Summoner - S01E01v2` — jedyny plik ze stylami piosenek (40 linii), bez `Actor`, więc sprawdza też zachowanie bez mówcy.

## Arkusz ocen

Dla każdego odcinka skala 1–5 i krótka uwaga z przykładowym czasem, np. `12:40`, w sześciu kryteriach:
- imiona;
- rodzaj gramatyczny;
- co czyta lektor;
- tempo i nadążanie lektora;
- głośność względem oryginału;
- czytelność szyldów.

Plik: `outcomes/01-baseline.md`. Oceny właściciel podaje w rozmowie, a zapisuje je orkiestrator.

## Kroki

1. **Sprawdzić, jak uruchamiać przebieg wzorca** bez ruszania żywej biblioteki i rezydenta.
   - Hipoteza: `ANISHIFT_WORKSPACE_ROOT` wskazany na `workspace/.quality/` plus `anishift run --preset <preset>`. Katalog od kropki jest pomijany przez skaner żywego workspace.
   - Dowód: przebieg na jednym krótkim pliku, z kontrolą, że żywy `workspace/ready/` i `config/watch/` się nie zmieniły.
   - Jeśli `run` wymaga rezydenta albo koliduje z jego blokadą: zatrzymać się i zapytać właściciela. Możliwe drogi: przebieg przy zamkniętym rezydencie albo osobny katalog `config/`.
2. **Zamrozić wejście.** Do `workspace/.quality/<odcinek>/` trafia źródłowy MKV (hardlink na tym samym dysku, bez kopiowania 1,5 GB) i wybrane źródłowe napisy. Nic w `workspace/ready/` się nie zmienia.
3. **Narzędzie pomiaru:** `scripts/quality/measure.py`.
   - Czyta wynik przebiegu: źródłowe i polskie ASS, `spoken`/`displayed` oraz oś czasu lektora.
   - Wypisuje JSON z metrykami masterplanu.
   - Używa istniejących modułów (`anishift.services.subtitles`, `pysubs2`, klient AniList z `anishift.services.catalog`) zamiast własnych parserów.
   - Ma test na małym, syntetycznym ASS w `tests/scripts/`.
4. **Pomiar bazowy:**
   - pełny przebieg obecnego kodu na 3 odcinkach;
   - metryki zapisane w `outcomes/01-baseline.md`;
   - surowe JSON-y w `workspace/.quality/`, poza gitem.
5. **Ocena właściciela.**
   - Właściciel ogląda 3 odcinki (wystarczy kilka minut z każdego, w miejscach wskazanych przez metryki) i wypełnia arkusz.
   - Orkiestrator zapisuje oceny i decyzję w outcome.

## Zakazy

- Nie zmieniać kodu produkcyjnego w tym etapie.
- Nie ruszać `workspace/ready/` ani `config/`.
- Nie przetwarzać odcinków spoza wzorca.

## Weryfikacja

- Test narzędzia pomiaru przechodzi.
- Bramki repo przechodzą.
- Dwa przebiegi pomiaru na tym samym wyniku dają identyczny JSON.

## Checkpoint właściciela

- Przed krokiem 2: wybór 3 odcinków.
- Po kroku 5: arkusz ocen.

Bez tego etap 1 nie startuje.
