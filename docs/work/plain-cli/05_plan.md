# 05 — Plan wykonania

Plan bieżących etapów. Wymagania: `05_settings_and_progress.md`. Mapa etapów:
`05_masterplan.md`.

Dokument jest żywy: zawiera szczegóły etapu budowanego teraz i następnego.
Dalsze etapy pozostają w masterplanie na poziomie stanów, bo ich szczegóły
zależą od wyniku tych dwóch.

## Baseline

- branch `work/interactive-cli/04-mascot-polish`, HEAD `4b03ce2`, drzewo czyste
- baseline testów: 47 nieprzechodzących, 2 błędy zbierania — stan zastany,
  niezwiązany z tym etapem, nie wolno go „naprawiać" po drodze
- bramki: `ruff check`, `ruff format --check`, `mypy` dla win32 i `--platform linux`,
  `pytest` — zawsze na `anishift/ tests/`, nigdy na podkatalogu

---

# E1 — Strażnik kompletności układu

## Różnica

```text
STAN OBECNY
    układ panelu = trzy krotki _GENERAL_FIELDS, _TRANSLATION_FIELDS, _TTS_FIELDS
    katalog      = 55 pól dla konfiguracji elevenbytes/run6
    związek      = brak
        ↓
PRZYCZYNA
    pole dodane do katalogu nie musi pojawić się w panelu i nic tego nie zgłasza
    dowód: elevenbytes_custom_voices ma pełny kontrakt i nie istnieje w UI
        ↓
STAN DOCELOWY
    test wiąże obie listy; pole pominięte bez wpisu na listę wyjątków wywala test
```

## Projekt

Jedna nowa struktura w `settings.py` — jawna, opisana lista pól świadomie
nieobecnych w układzie, z powodem przy każdym wpisie:

```text
_FIELDS_COVERED_ELSEWHERE: mapa setting_id -> powód
    llm_provider                 wybierany atomowo razem z modelem
    llm_provider_model_id        wybierany atomowo razem z providerem
    palantir_enrollment_base_url kategoria Połączenia
    openai_compatible_base_url   kategoria Połączenia
    primary_model_alias          świadomie ukryty
```

`elevenbytes_custom_voices` **nie** trafia na tę listę. Jest realną luką, więc test
ma na nią wskazywać aż do E3, gdy powstanie edytor `OBJECT_LIST`. Do tego czasu
figuruje na osobnej liście znanych braków, żeby test był zielony, ale brak był
policzony i widoczny.

## Zakres

- **w zakresie:** test kompletności, dwie listy w `settings.py`, zmiana etykiety
  `Wróć` na `Cofnij`
- **poza zakresem:** przenoszenie układu do katalogu, przenoszenie polskich
  tekstów do `anishift/config/`, nowe pola, nowe edytory
- **zabronione:** dodawanie pól prezentacyjnych do `SettingSpec`, usuwanie
  którejkolwiek z dwóch list, obchodzenie testu przez rozszerzanie listy wyjątków
  bez powodu
- **dozwolone lokalnie:** nazwy stałych i helperów, dokładny kształt asercji

## Mapa plików

```text
MODIFY  anishift/cli/interactive/settings.py     dwie listy + etykieta Cofnij
CREATE  tests/cli/test_interactive_settings_layout.py   test kompletności
READ    anishift/config/field_catalog.py         źródło pól i dyspozycji
READ    anishift/config/field_access.py          setting_is_active
```

## Kroki

1. **Listy i etykieta.** Dodać `_FIELDS_COVERED_ELSEWHERE` i `_KNOWN_LAYOUT_GAPS`
   z powodem przy każdym wpisie. Zmienić `Wróć` na `Cofnij` w `_ROOT_ITEMS` i we
   wszystkich miejscach dopinających wiersz powrotu.
   Sprawdzenie: `ruff`, `mypy`, panel nadal się otwiera.
2. **Test kompletności.** Dla kilku reprezentatywnych konfiguracji silników
   zbudować katalog i sprawdzić, że każde pole edytowalne jest albo w układzie,
   albo na jednej z dwóch list; oraz że żadne pole układu nie jest zdublowane.
   Konfiguracje: `elevenbytes/run6`, `elevenbytes/run7`, `edge`, `sapi`,
   `elevenlabs` — bo `depends_on` odsłania różne pola.
   Sprawdzenie: test przechodzi; ręczne dopisanie atrapy pola do katalogu wywala go.
3. **Bramki.** Pełny zestaw na `anishift/ tests/`; baseline bez zmian.

## Weryfikacja

| twierdzenie | dowód |
|---|---|
| układ pokrywa wszystkie pola edytowalne | test kompletności na 5 konfiguracjach |
| brak zdublowanych pól | asercja w tym samym teście |
| przyszłe pole nie zniknie po cichu | test wywala się po dodaniu atrapy |
| panel działa jak przed zmianą | ręczne otwarcie każdej kategorii |

## Warunek przejścia do E2

Test kompletności zielony, bramki zielone, baseline bez zmian, jedna realna luka
policzona i opisana.

---

# E2 — Interakcja: strzałki, przewijanie, Cofnij

## Różnica

```text
STAN OBECNY
    klawisze: up, down, enter, space, backspace, escape, interrupt, any
    liczby:   wyłącznie wpisywanie w modalu
    okno:     funkcja kursora, brute force O(n³) na klatkę, bez stanu
    Cofnij:   zwykły wiersz listy, może wypaść poza okno
    mysz:     zdarzenie dochodzi i ginie, bo treść ma dokładnie tyle wierszy co okno
        ↓
STAN DOCELOWY
    klawisze: dodatkowo left, right, pageup, pagedown, home, end
    liczby:   ←→ zmieniają wartość o krok, wpisywanie zostaje
    okno:     własny offset, wyznaczanie liniowe
    Cofnij:   przyklejony pod listą, zawsze widoczny
    mysz:     kółko przewija listę
```

## Projekt

### Klawisze

Rozszerzenie wyłącznie w `TerminalRenderer._key_bindings()`, bo to jedyny
właściciel interakcji. Nowe znormalizowane stringi: `left`, `right`, `pageup`,
`pagedown`, `home`, `end`.

Powód, dla którego muszą to być osobne bindingi, a nie obsługa `"any"`: na
Windowsie klawisze specjalne przychodzą z pustym `data`, więc `Keys.Any` zamienia
je wszystkie na nierozróżnialne `"any"`. Bez własnego bindingu nie da się ich
odróżnić.

### Krok liczby

Krok jest **pochodną** `SettingSpec`, nie nowym polem konfiguracji:

```text
INTEGER, rozpiętość > 1000   -> 100      (limit tokenów)
INTEGER                      -> 1
FLOAT, rozpiętość <= 2       -> 0.05     (temperatura, top_p, stabilność)
FLOAT, rozpiętość <= 20      -> 0.5      (tempo, gain w dB)
FLOAT, brak zakresu          -> 0.5      (gainy bez min/max)
```

Wartość jest klampowana do `minimum`/`maximum`, gdy istnieją. Pole `OPTIONAL_*`
o wartości `None` przy pierwszym `→` przyjmuje `default` ze spec, a przy `←` z
`minimum` wraca do `None`.

Każda zmiana strzałką jest osobną transakcją, tak jak dziś każda zmiana w modalu.
Świadomy kompromis: dwadzieścia naciśnięć to dwadzieścia atomowych zapisów
`settings.json`. Plik ma kilka kilobajtów, zapis jest atomowy, a alternatywa —
bufor i globalny `Save` — łamie obowiązujące ustalenie o braku globalnego zapisu.

### Pola wyboru

`←` i `→` przechodzą po `allowed_values` bez otwierania modala. Modal pozostaje
dla list wielokrotnego wyboru i dla wpisywania tekstu.

### Przewijanie

Kontroler zyskuje `_offset: int`. Wyznaczanie widocznego zakresu jest liniowe:
od offsetu w dół, licząc wiersze razem z nagłówkami sekcji, aż do wypełnienia
budżetu. `_sectioned_window` i jego `O(n³)` znika.

Reguły:

- ruch kursora klawiaturą koryguje offset minimalnie, żeby kursor pozostał w widoku
- `pageup`/`pagedown` przesuwają kursor o wysokość widoku, offset podąża
- `home`/`end` skaczą na początek i koniec, offset podąża
- kółko myszy zmienia **wyłącznie** offset; kursor zostaje na swoim wierszu, a
  pierwsze naciśnięcie strzałki wraca widok do kursora

### Mysz

`FormattedTextControl` dostaje podklasę nadpisującą `mouse_handler`, która
zamienia `SCROLL_UP` i `SCROLL_DOWN` na wywołanie callbacku przewijania i
zgłasza obsłużenie zdarzenia. Bez tego domyślny scroller okna dostaje zdarzenie i
gubi je, bo treść nigdy nie jest wyższa od okna.

To jedyny sposób bez drugiego renderera: `mouse_support=True` już jest, layout
ma jedno okno, a fragmenty po konwersji Rich → ANSI nie mają własnych handlerów.

### Cofnij

Wiersz powrotu przestaje być elementem przewijanej listy. Kolejność składania:
tytuł, wskaźnik `↑`, przewijana lista, wskaźnik `↓`, `Cofnij`, feedback, hint.
Budżet wierszy listy maleje o jeden.

## Zakres

- **w zakresie:** klawisze, krok liczby, przewijanie z offsetem, mysz w
  Ustawieniach, przyklejony `Cofnij`
- **poza zakresem:** przewijanie w Auto — to E5, mimo wspólnego mechanizmu;
  nowe pola i nowe edytory — to E3; paleta — to E4
- **zabronione:** druga aplikacja Prompt Toolkit, drugi renderer, `viewport.py`,
  własny `Live`, import `prompt_toolkit` poza `interactive/prompts.py`, globalny
  `Save`, kolorowe tło aktywnego wiersza
- **dozwolone lokalnie:** nazwy helperów, dokładny kształt struktury offsetu
- **warunki eskalacji:** jeśli przechwycenie kółka wymaga zmiany layoutu na
  `HSplit` albo `ScrollablePane`, zatrzymać się i przeplanować, bo to zmiana
  własności renderowania

## Mapa plików

```text
MODIFY  anishift/cli/interactive/prompts.py   nowe bindingi, podklasa kontrolki, callback scrolla
MODIFY  anishift/cli/interactive/settings.py  offset, liniowe okno, krok strzałek, przyklejony Cofnij
MODIFY  anishift/cli/interactive/manual.py    tylko jeśli dzieli mechanizm okna
MODIFY  anishift/cli/interactive/app.py       przekazanie nowych klawiszy do kontrolerów
MODIFY  anishift/cli/AGENTS.md                kontrakt klawiszy i reguła przewijania
CREATE  tests/cli/test_interactive_settings_scroll.py   offset, widoczność kursora, budżet
CREATE  tests/cli/test_interactive_settings_steps.py    krok, klamp, OPTIONAL_*
MODIFY  tests/cli/test_interactive_prompts.py  nowe znormalizowane klawisze
```

## Kroki

1. **Bindingi.** Dodać sześć klawiszy w `_key_bindings()`, przekazać dalej bez
   zmiany istniejących ścieżek. Sprawdzenie: test znormalizowanych klawiszy;
   Home i Ręczny nadal działają.
2. **Liniowe okno z offsetem.** Zastąpić `_sectioned_window` funkcją liniową,
   dodać `_offset` i korektę przy ruchu kursora. Bez nowych klawiszy jeszcze.
   Sprawdzenie: test budżetu i widoczności kursora dla wysokości 10, 24, 60;
   zachowanie identyczne jak przed zmianą przy samych `↑↓`.
3. **Strony i skoki.** `pageup`, `pagedown`, `home`, `end`.
   Sprawdzenie: test skoków na liście 22 pól.
4. **Krok liczby i przechodzenie po wyborach.** Funkcja kroku z `SettingSpec`,
   klamp, obsługa `OPTIONAL_*`.
   Sprawdzenie: test kroku dla `llm_temperature` (0–2), `llm_max_output_tokens`
   (1–32000), `narrator_mix_base_gain_db` (bez zakresu), `tts_output_bitrate`
   (`OPTIONAL_STRING` — nie może reagować na strzałki).
5. **Przyklejony Cofnij.** Wyjęcie wiersza powrotu z przewijanej listy.
   Sprawdzenie: test, że wiersz jest ostatni przy każdej pozycji offsetu.
6. **Mysz.** Podklasa kontrolki, callback scrolla.
   Sprawdzenie: test jednostkowy podklasy na sztucznym `MouseEvent`; ręczne
   potwierdzenie kółkiem w realnym terminalu.
7. **AGENTS.md i bramki.** Zapisać kontrakt klawiszy i regułę przewijania.
   Pełne bramki, baseline bez zmian.

## Weryfikacja

| twierdzenie | dowód |
|---|---|
| sześć nowych klawiszy dochodzi jako osobne stringi | test `prompts` |
| kursor nigdy nie ucieka z widoku przy klawiaturze | test dla trzech wysokości |
| przewinięcie myszą nie zmienia zaznaczenia | test podklasy + ręcznie |
| krok respektuje zakres i typ | test czterech reprezentatywnych pól |
| `Cofnij` jest zawsze widoczny | test przy skrajnych offsetach |
| wyznaczanie okna jest liniowe | brak podwójnej pętli po parach; test wydajności nie jest potrzebny |
| Home i Ręczny bez regresji | istniejące testy CLI |

## Punkt kontrolny człowieka

Po kroku 6:

```text
uruchom      uv run anishift  ->  Ustawienia  ->  Lektor
zrób         przejdź listę strzałkami, zmień tempo ←→, przewiń kółkiem,
             wróć strzałką, zejdź na Cofnij i naciśnij Enter
oczekuj      kursor zawsze widoczny, tempo zmienia się o 0.5,
             kółko przewija bez zmiany zaznaczenia, Cofnij zawsze na dole
zwróć uwagę  czy maskotka nie zostawia rastra przy przewijaniu,
             czy zapis po każdej strzałce nie zacina listy
przekaż      jedno zdanie: co działa, co nie
```

## Sprzężenie zwrotne

```text
błąd lokalny zgodny z projektem        popraw w tej iteracji i sprawdź ponownie
krok liczby nieintuicyjny w praktyce   zmień tabelę kroków, to nie zmienia projektu
kółko wymaga zmiany layoutu            zatrzymaj się, przeplanuj E2
zapis po każdej strzałce zacina        wróć po decyzję: debounce kontra transakcja
```
