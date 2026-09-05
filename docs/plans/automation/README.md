# AniShift — od wyboru anime do oglądania

Aktualny kierunek po decyzji właściciela z 2026-09-05: działający Auto rozwijamy
o funkcje usuwające codzienną obsługę. Ogólne polerowanie jest odłożone.
Ten pakiet nie jest zgodą na wdrożenie downloadera, watchera ani serwera.

## Kolejność czytania

1. [Wizja po ludzku](vision.md) — co ma robić AniShift i po co.
2. [Specyfikacja](specification.md) — wymagania, zakazy i decyzje otwarte.
3. [Masterplan](masterplan.md) — najbliższy wycinek i dalsze stany produktu.
4. [Brief dla ChatGPT Pro](pro-brief.md) — wejście do szczegółowego planowania.
5. [Research](research.md) i [import/Stremio](import-and-stremio.md) — dowody
   ze wskazanego baseline; ponownie sprawdzić używane API przed implementacją.

Bieżący kod: 4dc99dc (Auto) i 83150d8 (scroll), lokalnie scalone.
Właściciel potwierdził scroll i działanie Auto, nie pełny odbiór wszystkich opcji.
3102 testy PASS, 13 skip; 30 smoke PASS. [Wynik Auto](../../work/reliability-audit/outcomes/05-auto-preset-controls.md).
Status publikacji i dalszych funkcji: [epic #49](https://github.com/MattyMroz/AniShift/issues/49).

## Odłożone dopracowanie

To odnośniki do właściciela statusu, nie druga tablica aktualizowana ręcznie.

| Temat | GitHub |
| --- | --- |
| Proste opisy ustawień i poprawne nazwy limitów | [#42](https://github.com/MattyMroz/AniShift/issues/42) |
| Mniej powtarzalnych testów, te same dowody | [#43](https://github.com/MattyMroz/AniShift/issues/43) |
| Pomiary startu, responsywności i etapów przed optymalizacją | [#44](https://github.com/MattyMroz/AniShift/issues/44) |
| Kwalifikacja awarii/restartów przed serwerem | [#45](https://github.com/MattyMroz/AniShift/issues/45) |
| Realne media, odsłuch, dostawcy i świeża instalacja | [#46](https://github.com/MattyMroz/AniShift/issues/46) |
| Pusty displayed z SRT wykryty przed zbędną pracą | [#47](https://github.com/MattyMroz/AniShift/issues/47) |
| Animacja prawdziwego terminala w README | [#48](https://github.com/MattyMroz/AniShift/issues/48) |
| Polski podział i layout ASS | istniejące [#22](https://github.com/MattyMroz/AniShift/issues/22) |
| Napisy wewnątrz obrazu, nie całego ultrawide | istniejące [#23](https://github.com/MattyMroz/AniShift/issues/23) |
| Granice stylów między fragmentami dialogu | istniejące [#34](https://github.com/MattyMroz/AniShift/issues/34) |

Nie dodano duplikatu klasyfikatora ani batch processing, które już istnieją.
Starsze otwarte #38 (Textual) i #40 (test normalizacji) wymagają osobnego
uzgodnienia statusu; nie są dowodem, że te prace trzeba wykonać od nowa.

## Starsze plany i dowody

[Plan 01](plans/01-folder-watch.md) i [Plan 02](plans/02-acquisition.md) są do
przeplanowania pod wspólne intake i aktualną kolejność. [Plan 03](plans/03-subtitle-layout.md)
jest odłożony. [Dawne review](review.md) i [brief Fable](fable-brief.md) dokumentują
tamten zakres — nie są bieżącym zleceniem.

Nie przenosimy plików: istniejące ścieżki zachowują odnośniki i dowody.
Nowy wykonawca zaczyna od powyższej kolejności, nie od legacy roadmapy.
