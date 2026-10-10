---
kind: plan
status: przyjęty do wykonania 2026-10-10 (rundy 5 i 6: AKCEPTUJĘ, 0 B + 0 I; drobne wprowadzone); decyzje delegowane przez właściciela, punkty „Do potwierdzenia” w intent.md
created: 2026-10-10
baseline: work/acquisition/05-h1-season-alias @ 0f6fde8 (stos 04-algorithm → tui/01-mouse-everywhere 973a9eb → 05)
execution branch: work/tui/02-unified-tabs
---

# Plan: cztery zakładki panelu jako jedna moneta

Kierunek i podstawa: [intent.md](intent.md). Spis ekranów: `%TEMP%\opencode\tui\inventory.md` (rendery
`screens\`), burza mózgów `%TEMP%\opencode\tui\brainstorm-{a,b,c}.md`. Wykonawca czyta inwentarz w całości przed F0.

## 1. Rezultat

Po `uv run anishift` → `Enter` panel otwiera się na Subskrypcjach. Cztery zakładki (Anime, Subskrypcje,
Przetwarzanie, Biblioteka) mają:

- jeden słownik klawiszy (§3);
- stopkę i pomoc `?` generowane z jednej funkcji akcji ekranu (§4, §5);
- jeden szkielet z jedną linią statusu automatu (§6);
- jedną zasadę wyjścia (§7).

Wygląd bez zmian: paleta, `brand_accent`, `gray`, kursor `❯`, układ góra/dół, `PANEL`, pasek zakładek.

## 2. Stan obecny (zweryfikowany w dwóch rundach review)

- **Start:** `self._tab: int = _Tab.PROGRESS` (`state.py:289`); tray z `--state` startuje od razu w STATE
  (`app.py:189`).
- **Klawisze:** łańcuchy `if`, bez mapy:
  - `state.py` `_list_key`, `_subscription_key`, `_action_key`, `_anime_key`, `_file_action`, `_details_key`,
    `_history_key`, `_retry_key`;
  - `anime.py:469-475` (szczegóły), `:551-612`, `:1064-1083`, `:1404-1482`, `:1519-1598`;
  - `anime_panel.py` `_command`/`_edit`.
- **Stopki:**
  - `state.py` `_view_footer` `:1282`, `_footer` `:1296`, `_subscription_hint` `:1380`, `_processing_hint` `:1392`;
  - Anime `anime.py:889-923`, `:1134-1168`, `anime_view.py:419`, `:481-505`;
  - `NAVIGATION_KEYS` `anime_view.py:80`, pakowanie `pack_keys(..., optional=...)` (`menu.py:114`).
- **Status:** `_global_status` `state.py:1411` (PROGRESS liczy `len(_processing_rows())`); `_shows_status` `:1406`
  (Biblioteka tylko przy pauzie); Anime bez statusu. `material_counts["processing"]` liczy tylko RUNNING
  (`automation.py:1694`).
- **Rozmiar:** `render_anime` poniżej 50×12 pokazuje „Powiększ terminal” (`anime_view.py:193`). `_list_body`
  (Przetwarzanie, Biblioteka) działa przy każdej szerokości. Treść Anime przy 12 wierszach ma `MIN_ROWS = 9`.
- **Biblioteka:** lista ma pola `name`, `main_result` (może być `None`) i `target` (`automation.py:1788-1803`).
- **Błędy:**
  - `manual.py:588` (`"a"` zamiast `"text:a"`);
  - `_field_title` (`settings.py:1907`) bez `_SUBTITLE_FIELDS`;
  - `/` w U08 (`anime.py:1072`) nie zeruje `_subscription`;
  - `O` na nieaktywnym QUERY przełącza automat (`state.py` `_anime_key`: `text:o and not input_focused`), wbrew
    W-01 (`ux.md:58`).

## 3. Słownik klawiszy (decyzja)

| Klawisz | Znaczenie | Zmiana względem dziś |
|---|---|---|
| `↑↓`, `Home/End`, `PgUp/PgDn` | ruch | `PgUp/PgDn` także na listach `StateController` (rozmiar strony z ostatniego renderu, jak `_visible_count` w Ustawieniach) |
| `←→` | zmiana zakładki | bez zmian; zablokowane tylko, gdy pole tekstowe ma fokus |
| `Tab/Shift+Tab` | zmiana zakładki | bez zmian; zawsze przełącza |
| `Enter` | główna akcja wiersza | Przetwarzanie bez `Enter` (wolny pod U05/U04b) |
| `Space` | zaznacz | Subskrypcje: pauza tylko `W` |
| `W` | wstrzymaj/wznów | — |
| `D` | pobierz | Subskrypcje: dodawanie → `/`; Biblioteka: szczegóły → `?` |
| `S` | subskrybuj (Anime: tytuły, wpisy, odcinki, U08) | Historia: szukanie → `/` |
| `/` | szukaj | Subskrypcje i U08: `/` = `start_subscription_search` (szukaj i dodaj; w U08 zeruje kontekst subskrypcji) |
| `R` | sprawdź teraz | Subskrypcje i U08 (było `F`) |
| `P` | ponów | — |
| `F` | folder | tylko Biblioteka i jej szczegóły |
| `X` / `Delete` | usuń / anuluj | Biblioteka i jej szczegóły: `X` = `Delete` (z `Ctrl+Z`, bez pytania); Przetwarzanie: `X` i `Delete` uzbrajają pytanie (§3.2) |
| `C` | kopiuj (Anime, jak dziś) | — |
| `?` | pomoc i szczegóły (§5) | — |
| `Ctrl+Z` | cofnij usunięcie | Subskrypcje i Biblioteka, jak dziś |
| `M`, `U` | Ręczny, Ustawienia | bez zmian (nie w Anime) |
| `O` | automat wstrzymaj/wznów | bez zmian poza QUERY; na QUERY `O` wpisuje się w pole (F0) |
| `T`, `I`, `Z`, `H`, `A` | akcje lokalne | bez zmian znaczenia |

Zasada potwierdzeń: pytanie tylko tam, gdzie nie ma `Ctrl+Z`.

### 3.1 Ciche aliasy (działają; nie ma ich w stopce ani w pomocy)

| Ekran | Alias | Działa jak |
|---|---|---|
| Subskrypcje | `D`, `Enter` na pustej liście | `/` |
| Subskrypcje, U08 | `F` | `R` |
| Subskrypcje | `Space` | `W` |
| Przetwarzanie | `C` | `X` |
| Biblioteka | `D` | `?` |
| Historia | `S` | `/` |
| wszędzie, gdzie działa `X` | `Delete` | `X` |

Każdy alias ma test.

### 3.2 Pytanie przy anulowaniu w Przetwarzaniu (wzorzec R-04, `ux.md:186`)

- **Uzbrojenie:** `X`, `Delete` lub `C` na wierszu uzbraja pytanie. `X anuluj` jest w akcjach i uzbraja pytanie
  tylko na wierszu z celem: `stage == "download"` z `info_hash` albo przetwarzanie/przyjęte z `run_id` (jak dziś
  w `_processing_action`). Na innych wierszach i na pustej liście `X` nie robi nic i nie ma go w stopce. Pytanie to jawne pole kontrolera z celem
  (`run_id` dla przetwarzania, `info_hash` dla pobierania).
- **Treść** zastępuje stopkę, tak jak przy ponowieniu w `_view_footer`:
  - pobieranie: „Anulować pobieranie? Enter tak · Esc nie”, a gdy ten sam `info_hash` ma kilka wierszy
    (paczka): „Anulować pobieranie (N materiałów)? Enter tak · Esc nie”;
  - przetwarzanie: „Anulować całe zlecenie (N materiałów)? Enter tak · Esc nie”.
- **Klawisze przy aktywnym pytaniu:**
  - `Enter` anuluje cel (istniejąca ścieżka); przy `_busy` jest ignorowany, a pytanie zostaje;
  - `Esc` kasuje pytanie bez przejścia do Home;
  - `Ctrl+C` kasuje pytanie (nie kopiuje i nie wychodzi);
  - każdy inny klawisz, także `Tab` i `←→` (wyjątek od „Tab zawsze przełącza”), kasuje pytanie i jest połykany;
  - każde wciśnięcie przycisku myszy (także początek przeciągnięcia) kasuje pytanie i nie wybiera wiersza;
    obsługa w `StateController.mouse`, bez zmian w `app.py`.
- **Zniknięcie celu:** pytanie znika, gdy cel ze snapshotu zniknie. Zmiana kolejności wierszy w snapshocie nie
  zmienia celu pytania (cel po tożsamości, `_preserve_processing_selection`).
- **Wyniki `_work`** nie nadpisują aktywnego pytania.
- **Opuszczenie Przetwarzania** każdą drogą (klawisz, `show_library`, `_show_subscription_list`, `suspend`,
  wyjście do Home) kasuje pytanie.

## 4. Akcje ekranu i stopki (decyzja)

1. **Funkcja akcji.** Funkcja stanu ekranu zwraca krotkę akcji `(klawisz, etykieta)` w kolejności priorytetu.
   - Akcje zależne od wiersza wynikają ze stanu: `W wstrzymaj/wznów`, `T` tylko przy czekaniu na PL, `P` przy
     problemie przeniesienia, `W` w Przetwarzaniu tylko dla pobierania.
   - Funkcja zasila wyłącznie stopkę i pomoc. Obecne łańcuchy `if` obsługi klawiszy zostają.
   - Duplikaty akcji głównej (`Enter` na pustej liście Subskrypcji = `/`) są cichymi
     aliasami (§3.1). `Enter` w EPISODES zależny od wiersza („Wskaż plik”, „Dodatki”) jest akcją główną tego
     wiersza.
   - `D` i `Space` zostają w stopce niezależnie od wiersza pod kursorem (na wierszu niekwalifikującym się dają
     komunikat odmowy, jak dziś); stopka nie skacze.
   - Zgodność pilnują złote testy (§9, F1).
2. **Stopka:** `Enter …` (jeśli ekran ma akcję główną) + najwyżej 3 akcje + `? więcej` + `Esc wróć`.
   - Ucinanie przy wąskim ekranie przez `pack_keys(..., optional=...)`: akcje od końca, nigdy `?` i `Esc`.
   - Łamanie tylko na granicy ` · `.
3. `NAVIGATION_KEYS` znika ze stopek; nawigacja jest w pomocy (część „Wszędzie”).
4. **Etykiety Esc:** `wróć` wszędzie poza edycją pola (`Esc anuluj`). Znikają „lista”, „bieżące”, „anuluj”
   w DRAFT. Pozostałe etykiety: `usuń`, `ponów`, `szczegóły`, `dodaj`, `szukaj`.
5. **Komunikaty po usunięciu** zostają w slocie komunikatu. Subskrypcje jak dziś (`state.py:526`). Biblioteka
   dostaje trwały komunikat „Usunięto · Ctrl+Z cofnij”. Nazwy z wiersza przeniesienia (`P ponów przenoszenie ·
   {names}`) zostają w slocie komunikatu Biblioteki.
6. **Ekrany bez `?`** (stopka bez `? więcej`): QUERY (stopka `Enter szukaj · Esc wróć`), BUSY, PROBLEM,
   pole zakresu `Z`, pole szukania Historii, propozycja ponowienia, pytanie anulowania.
7. **Szczegóły i bloki pomocy** mają stopkę: własne akcje + `Esc wróć`, bez `? …`; `?` zamyka je po cichu.

Docelowe stopki 80 kolumn (złote stringi w testach):

```text
Anime/tytuły        Enter wybierz · S subskrybuj · ? więcej · Esc wróć
Anime/wpisy         Enter odcinki · S subskrybuj · ? więcej · Esc wróć
Anime/odcinki       Space zaznacz · D pobierz · S subskrybuj · ? więcej · Esc wróć
Anime/wydania       Space zaznacz · D pobierz · ? więcej · Esc wróć
Anime/pliki         Enter wybierz · ? więcej · Esc wróć
Nowa subskrypcja    Enter wybierz · Space zaznacz · ? więcej · Esc wróć
U08                 Space zaznacz · D pobierz · W wstrzymaj · ? więcej · Esc wróć
U08 (czeka na PL)   Space zaznacz · D pobierz · T pobierz teraz · ? więcej · Esc wróć
Subskrypcje         Enter szczegóły · / dodaj · W wstrzymaj · ? więcej · Esc wróć
Subskrypcje pusta   / dodaj pierwszą · ? więcej · Esc wróć      (treść: „Brak subskrypcji”)
Przetwarzanie       W wstrzymaj · X anuluj · H historia · ? więcej · Esc wróć
Historia            Enter otwórz · P ponów · / szukaj · ? więcej · Esc wróć
Biblioteka          Enter otwórz · F folder · X usuń · ? więcej · Esc wróć
Biblioteka/szczeg.  Enter otwórz plik · F folder · X usuń · Esc wróć
Anime, U08/szczeg.  C kopiuj · Esc wróć
Blok pomocy         Esc wróć
```

2026-10-10: ekran oferty usunięty (decyzja właściciela) — `I` i `P` otwierają od razu Anime/wydania; zob. `docs/work/acquisition/ux.md` §6.

Lista „akcji spoza stopki” poniżej jest przykładowa; obowiązuje reguła §4.1 i sonda z F1.

Akcje spoza stopki (pomoc „Ten ekran”):
- Anime/odcinki: `I` wydania, `Z` zakres, `A` wszystkie, `P` ponownie, `/` szukaj;
- U08: `R`, `X`, `I`, `W` (gdy jest `T`);
- Subskrypcje: `R`, `X`, `Ctrl+Z`, `M`, `U`;
- Przetwarzanie: `M`, `U`;
- Biblioteka: `Ctrl+Z`, `M`, `U`, `P` (gdy jest problem przeniesienia).

`W` w Przetwarzaniu tylko dla pobierania. Bez niego stopka zaczyna się od `X anuluj`.

## 5. Pomoc `?` (decyzja)

- **Każda pomoc** kończy się częścią „Wszędzie”: `↑↓ wybierz · ←→ zakładki · Tab zakładki · O automat · Esc wróć`
  (`O` poza QUERY).
- **Anime i U08:** istniejące szczegóły wiersza zostają (opis, powód H1, nota kalibracji). Stałe trzy linie skrótów
  zastępuje wygenerowana część „Ten ekran” (akcje bieżącego stanu, bez aliasów) i „Wszędzie”. DRAFT tak samo.
- **Subskrypcje (lista, także pusta), Przetwarzanie, Historia:** `?` otwiera blok pomocy w miejscu listy (góra
  i dół ekranu zostają): „Ten ekran” + „Wszędzie”. W Historii dodatkowo „Historia z ostatnich 30 dni”.
- **Biblioteka:**
  - z wybranym wierszem i połączeniem `?` otwiera istniejące szczegóły zestawu (dziś `D`);
  - pod listą plików szczegóły rysują pomoc „Ten ekran” i „Wszędzie” jako tekst bez możliwości wyboru, poza
    `_entries` (`_open_detail_file` liczy indeks pliku od końca listy), więc `↑↓` nie wchodzi w tekst pomocy;
    przy niskim ekranie pomoc jest ucinana pierwsza, przed wierszami plików;
  - przy pustej liście, bez połączenia albo przy `_busy` `?` otwiera zwykły blok pomocy;
  - przyjście szczegółów z oczekującego odczytu zamyka otwarty blok pomocy, więc nigdy nie są otwarte
    jednocześnie.
- **Szczegóły Anime, U08 i Biblioteki działają jak dziś** (kontrakt `ux.md:286`, `cli/AGENTS.md:85`, testy
  `test_anime_episodes.py:345-360`, `:1845-1859`):
  - Anime i U08:
    - `↑↓`, `PgUp/PgDn`, `Home/End` i kółko przewijają tekst szczegółów, kursor listy stoi;
    - klik wybiera wiersz szczegółów;
    - `C` kopiuje wiersz, `Ctrl+C` kopiuje zaznaczenie, a bez zaznaczenia zamyka szczegóły;
    - litery akcji (`Enter`, `I`, `P`, `S`, `/`) działają jak dziś na wierszu, którego dotyczą szczegóły;
  - Biblioteka: `↑↓` pliki, `Enter`, `F`, `Delete`, `Ctrl+Z` jak dziś.

  Zmiany w szczegółach, wszystkie nazwane w intencji:
  - treść pomocy: trzy stałe linie skrótów w Anime → wygenerowane „Ten ekran” i „Wszędzie”;
  - `Backspace` zamyka szczegóły (dziś nic nie robi);
  - w szczegółach Biblioteki `X` działa jak `Delete`, `Tab` i `←→` zamykają je i przełączają zakładkę, a `O`,
    `M` i `U` działają jak na liście.
- **Bloki pomocy w `StateController`** (Subskrypcje, Przetwarzanie, Historia, Biblioteka bez wiersza):
  - `↑↓`, `PgUp/PgDn`, `Home/End` i kółko przewijają blok;
  - `?`, `Esc` i `Backspace` zamykają;
  - `Tab` i `←→` zamykają i przełączają zakładkę;
  - `O` działa jak na liście;
  - `Ctrl+C` kopiuje zaznaczenie, a bez zaznaczenia zamyka blok;
  - wszystkie inne klawisze są ignorowane.
- **Mysz w blokach pomocy:**
  - wiersze bez tagów `mark_row`;
  - `select()` nic nie robi;
  - `view_key()` uwzględnia otwartą pomoc.

## 6. Szkielet ekranu (decyzja)

Od góry, identycznie w czterech zakładkach:

1. **`PANEL` i pasek zakładek** bez zmian.
2. **Wiersz okruszka**, zawsze obecny (treść nie skacze). Stoi bezpośrednio nad treścią, a nie przypięty pod
   zakładkami: w Anime i Subskrypcjach jest to dotychczasowy wiersz kontekstu z `render_anime` (wyśrodkowany
   blok z tabelą), w `_list_body` wiersz nad wyśrodkowaną listą.
   - na poziomie listy zakładki pusty: lista Subskrypcji, Przetwarzanie, Biblioteka, Anime/tytuły, Anime/wpisy;
   - głębiej jeden format `Zakładka › Element`: `Anime › Tytuł (rok)` (odcinki, wydania, pliki),
     `Subskrypcje › Tytuł` (U08), `Nowa subskrypcja › Tytuł` (DRAFT, jak dziś), `Przetwarzanie › Historia`,
     `Biblioteka › Zestaw` (szczegóły);
   - tytuł „Subskrypcje” nad listą znika. `ANIME` nad polem zapytania zostaje (kontrakt cli/AGENTS); dawne
     `ANIME › …` → `Anime › …`.
3. **Nagłówki kolumn:**
   - Anime i Subskrypcje bez zmian;
   - Biblioteka zostaje w `_list_body`, bez kolumn (jedna kolumna nazw; kolumna formatu prawie zawsze
     pokazywałaby MKV, a to tylko dokłada słów). Jednolitość daje okruszek, stopka, pomoc i status;
   - Przetwarzanie bez nagłówka.
4. **Treść.**
5. **Slot komunikatu** (jeden).
6. **Stopka** (§4).
7. **Linia statusu automatu:** jedna funkcja, ten sam format w czterech zakładkach:
   - bez połączenia lub przed pierwszym snapshotem: `Automat: brak połączenia`;
   - praca: `Automat: praca · pobiera N · przetwarza N · czeka N`, człony z zerem pomijane, a przy wąskim
     ekranie odrzucane od końca (czeka, przetwarza, pobiera);
   - bez liczników: `Automat: bezczynny`;
   - pauza: `Automat wstrzymany` (bez liczników; `O` jest w pomocy „Wszędzie”);
   - zatrzymywanie i niepełna pauza: `Automat: zatrzymywanie` i `Automat: pauza niepełna`, z licznikami
     jak przy pracy.

   Liczby wyłącznie z `material_counts`; w Przetwarzaniu lista pokazuje wszystkie wiersze, a status tylko liczniki
   automatu (zmiana kontraktu, w intencji). Status jest widoczny także w Anime i Bibliotece. W Anime przy
   wysokości mniejszej niż 13 wierszy status się nie pokazuje (Anime zachowuje `MIN_ROWS`, nic innego nie
   ustępuje). Minimalny rozmiar terminala bez zmian w żadnej zakładce.
8. **Linia katalogu i wersji** bez zmian.

**Pusty stan Subskrypcji** pojawia się dopiero po pierwszej liście od ownera. Wcześniej treść pokazuje
„Łączenie…”. O połączeniu mówią tylko dwa miejsca: treść „Łączenie…” i status `Automat: brak połączenia`.
Znikają komunikat „Łączenie z procesem w tle…” (`state.py:298`) i wiersze „Brak połączenia” (`state.py:1302`,
`:1339`).

## 7. Wyjście i nawigacja (decyzja)

- **`Esc`** = krok wstecz, jak dziś. Na polu zapytania Anime jak dziś: wyłącza edycję, zostawia tekst.
- **`Backspace`** = `Esc` wszędzie poza polami tekstowymi:
  - na QUERY (z fokusem i bez) aktywuje pole i edytuje, tak jak pierwszy znak (W-01);
  - w polu zakresu `Z`, szukaniu Historii, polu ścieżki w Ręcznym i edytorach Ustawień edytuje;
  - reguła obejmuje Anime (wszystkie ekrany poza QUERY, także BUSY i PROBLEM), Ręczny i zakładki (jak dziś).
- **`/` w Subskrypcjach i U08:** `start_subscription_search`; `Esc` z wyszukiwarki wraca do listy subskrypcji
  (`_back_out`).
- **Start panelu:** `_Tab.SUBSCRIPTIONS`, także z tray `--state` bez innej zakładki. Kolejność zakładek, Home
  i `Ctrl+C` bez zmian.

## 8. Mapa plików

```text
MODIFY  anishift/cli/interactive/state.py            start, akcje, stopki, pomoc, status, okruszek, Biblioteka, pytanie, aliasy, PgUp/PgDn
MODIFY  anishift/cli/interactive/anime.py            akcje, stopki, treść pomocy, Backspace, / w U08, O na QUERY, _IN_PROGRESS_HINT
MODIFY  anishift/cli/interactive/anime_view.py       stopka, status w Anime, okruszek
MODIFY  anishift/cli/interactive/settings.py         _field_title + _SUBTITLE_FIELDS (F0)
MODIFY  anishift/cli/interactive/manual.py           "text:a" (F0), Backspace (F3)
MODIFY  anishift/cli/interactive/app.py              tylko start z tray --state, jeśli wybiera zakładkę
CREATE  anishift/cli/interactive/actions.py          typ akcji, budowa stopki i bloku pomocy (albo w menu.py, jeśli to naturalne)
MODIFY  tests/cli/**                                 kontrakty §3–§7, złote stopki
MODIFY  tests/application/test_history.py, test_service.py, test_automation.py   wejście (ustawienie zakładki po konstrukcji, nawigacja) i asercje startu/anulowania
MODIFY  anishift/cli/AGENTS.md                       zasady §3–§7 i zmienione kontrakty
MODIFY  docs/work/acquisition/spec.md, ux.md         start, klawisze, stopki, Backspace (zdania z datą)
READ ONLY anishift/application/**
```

## 9. Wykonanie (każda faza = osobny commit)

**F0. Warunki, baseline i błędy** (`fix(tui)`).
- Start przy czystym drzewie (poza nieśledzonym `session-ses_f20e.md` i `docs/work/tui-unify/`), branch
  `work/tui/02-unified-tabs` od `0f6fde8`.
- Pełne bramki przed zmianami; zapisać znane niestabilne testy.
- Rendery „przed” do `%TEMP%\opencode\tui\before\` skryptami `shots_*.py`.
- Naprawy z testami:
  - `manual.py:588` → `text:a`;
  - `_field_title` + `_SUBTITLE_FIELDS`, z testem: każde edytowalne pole z listy w
    `test_interactive_settings_layout.py:44` ma tytuł różny od ID;
  - `/` w U08 zeruje kontekst subskrypcji (test: U08 → `/` → inny wpis → `X` nie dotyka starej subskrypcji);
  - `O` na QUERY wpisuje się w pole (test: wpisanie „Overlord” na świeżej zakładce Anime nie wywołuje
    `set_auto`).

**F1. Akcje, słownik klawiszy, stopki i pomoc** (`feat(tui)`, jedna faza: złote stopki są możliwe dopiero
z nowym słownikiem).
- §3 (z aliasami §3.1 i pytaniem §3.2), §4 i §5.
- Aktualizacja `_IN_PROGRESS_HINT` (`anime.py:156`) i `_NO_SUBSCRIPTIONS` (`state.py:178`, „Brak subskrypcji”;
  podpowiedź `/ dodaj pierwszą` jest w stopce).
- Testy:
  - **złote zestawy akcji** na każdy ekran i stan z fixture oraz złote stopki z §4 przy 80 kolumnach (dokładne
    stringi); przy 50 kolumnach reguła łamania;
  - **sonda klawiszy:**
    - klawisze: `a–z`, Space, Enter, Delete, `/`, `?`;
    - „zmiana stanu” = wywołanie na atrapie sesji lub ownera, wywołanie schowka, wynik różny od `CONTINUE` albo
      zmiana krotki (ekran, kursor, zaznaczenia, otwarte szczegóły/pomoc, pole zakresu/szukania, pytanie,
      `_retry`, zakładka) z pominięciem slotu komunikatu;
    - **kierunek prosty:** na każdym ekranie poza QUERY, pytaniem anulowania, polami edycji i szczegółami Anime
      i U08 (te mają osobny test „jak dziś”) klawisz zmieniający stan musi być w akcjach ekranu, w §3.1 albo
      w części „Wszędzie” (`O`, `Tab`, `←→`, `Esc`, `Backspace`, `?`);
    - **kierunek odwrotny:** każdy klawisz z akcji ekranu zmienia stan na wierszu, na którym akcja ma
      zastosowanie (wiersz do pobrania, wiersz do anulowania itd.);
    - fixture wierszowe: wiersz „Wskaż plik” i „Dodatki” w EPISODES, cel czekający na PL (U08), zestaw
      z problemem przeniesienia (Biblioteka), pobieranie i przetwarzanie (Przetwarzanie), pusta i niepusta lista
      Subskrypcji;
  - **szczegóły Biblioteki:** po otwarciu przez `?` `Enter` i `F` trafiają we właściwy plik, a `↑↓` nie wchodzi
    w tekst pomocy;
  - **blok pomocy:** każdy klawisz akcji nie woła sesji i nie zmienia kursora, a klik nic nie wybiera; `?`
    otwiera i zamyka na każdym ekranie spoza §4.6 i poza szczegółami (tam `?` zamyka);
  - **szczegóły Anime:** testy `test_anime_episodes.py:345-360` i `:1845-1859` przechodzą bez zmian;
  - **zmiany klawiszy:** każda zmieniona para i każdy alias;
  - **pytanie:**
    - uzbrojenie przez `X`, `Delete` i `C`;
    - opuszczenie Przetwarzania kasuje;
    - `Enter` anuluje, a przy `_busy` nie anuluje;
    - `Esc` kasuje bez Home;
    - `Ctrl+C`, `Tab`, inny klawisz i klik kasują;
    - zniknięcie celu kasuje;
    - zmiana kolejności wierszy w snapshocie nie zmienia celu.

**F2. Szkielet i status** (`feat(tui)`).
- §6.
- Macierz testów renderu:
  - **40×12:** Anime i Subskrypcje pokazują „Powiększ terminal” (jak dziś); Przetwarzanie i Biblioteka rysują
    listę i status;
  - **50×12 i 80×12:** Anime bez statusu i bez „Powiększ terminal” (QUERY, BUSY, szczegóły, DRAFT, EPISODES
    z zaznaczeniami); Subskrypcje ze statusem (cli/AGENTS: „kept at 50×12 by dropping the blank row beneath the table”);
  - **80×24 i 120×30:** status w identycznym formacie w czterech zakładkach, także „brak połączenia”;
  - **każdy rozmiar:** okruszek nie przesuwa treści; brak wiersza szerszego niż ekran;
  - „Łączenie…” przed pierwszą listą Subskrypcji.

**F3. Start i wyjście** (`feat(tui)`).
- §7.
- Testy:
  - start na Subskrypcjach (także tray `--state`);
  - `/` → `Esc` (zdejmuje fokus) → `Esc` wraca do Subskrypcji;
  - `Backspace` = `Esc` na każdym ekranie Anime (także BUSY, PROBLEM) i w Ręcznym;
  - testy negatywne: `Backspace` edytuje QUERY z fokusem i bez (np. tekst bez fokusu po `Esc` z listy
    tytułów: znak znika, panel nie wychodzi), pole zakresu, szukanie Historii, ścieżkę w Ręcznym;
  - przeredagowanie `cli/AGENTS.md:236-237` („Anime … shows no pause notice”).
- `spec.md`, `ux.md`, `cli/AGENTS.md` jednym przebiegiem dla F0–F3.

**F4. Sprzątanie** (`refactor(tui)`).
- Usunięcie martwego kodu: stałe stopek, `NAVIGATION_KEYS`, jeśli nieużywane, zdublowane gałęzie.
- Skill `simple` i `coding`; bez zmiany zachowania.
- Rendery „po” do `%TEMP%\opencode\tui\after\`.

**Polityka testów:**
- **W `tests/application/**` i `tests/cli/**`** wolno:
  - zmieniać wejście testu: ustawić zakładkę po konstrukcji (przez istniejące przełączanie), poprawić nawigację,
    dopisać `Enter` potwierdzający pytanie anulowania;
  - zmieniać asercje startu i anulowania zgodnie z §3.2 i §7;
  - nie wolno osłabiać asercji przepływów D/S/T/U08.
- **W `tests/cli/**`** asercje układu i tekstu (tytuł, okruszek, status, stopki, etykiety Esc, pusty stan) idą za
  §4–§6.
- **Eskalacja:** gdy zmiana łamie zachowanie przepływów D/S/T/U08, partii, odmów, ponowień albo wyboru wydania.

**Pętla każdej fazy:**
1. Autor koduje i testuje.
2. Niezależny recenzent (świeży agent, nie autor).
3. Poprawki.
4. Weryfikacja recenzenta.
5. Pełne bramki.
6. Commit.

Push po F4.

## 10. Weryfikacja

- **Po każdej fazie:**
  - `uv run ruff check anishift/ tests/`;
  - `uv run ruff format --check anishift/ tests/`;
  - `uv run mypy anishift/ tests/` oraz `--platform linux` (cache w `%TEMP%`);
  - `uv run pytest`;
  - hooki `no-test-prose` i `const-docstrings`.
- **Testy:** złote zestawy i sondy z F1, mutacje recenzentów.
- **Rendery** „przed/po” w raporcie nocnym.
- **Rano:** checkpoint właściciela.

## 11. Zakres

- **In scope:** §3–§7 w czterech zakładkach; w Ręcznym `A` i `Backspace`; w Ustawieniach `_field_title`.
- **Deferred (decyzja właściciela):**
  - kategoria „Zaawansowane” w Ustawieniach;
  - usunięcie aliasów;
  - wyszukiwarka wbudowana w listę;
  - widok „Oglądam”;
  - Historia w Bibliotece;
  - wiersze „Cofnij/Anuluj/Wróć”;
  - tłumaczenie komunikatów planera;
  - kliknięcie w zakładki;
  - `Enter` w Przetwarzaniu.
- **Forbidden:**
  - paleta, style, akcent, kursor i układ góra/dół;
  - usunięcie funkcji (czekanie na PL, `T`, ręczny wybór wydania, kolumny Jakość i Pewność, nota kalibracji,
    `D` bez podglądu, U08);
  - zmiany w `anishift/application/**`;
  - zmiany testów poza polityką §9;
  - nowe zależności;
  - zmiana `Esc` w polu zapytania i `Ctrl+C` poza pytaniem anulowania;
  - wzrost minimalnego rozmiaru terminala.
- **Allowed local decisions:**
  - nazwy i położenie typu akcji;
  - priorytety w obrębie §4;
  - brzmienie etykiet w granicach §3–§4;
  - rozmiar strony `PgUp/PgDn`;
  - rozbicie testów.
- **Escalation:** §9 („Eskalacja”); dodatkowo, gdy reguła §4 chowa akcję kluczową dla zadania codziennego albo
  status lub nagłówki wymagają danych od rezydenta.

## 12. Ryzyka

| Ryzyko | Wykrycie | Reakcja |
|---|---|---|
| Właściciel szuka znanego klawisza | aliasy; pełna pomoc | rano decyzja o podpowiedzi |
| Akcje rozjeżdżają się z obsługą | złote zestawy i sonda klawiszy | poprawić akcje albo obsługę |
| Status w Anime przy małej wysokości | testy 50×12 i 80×12 | ukrycie poniżej 13 wierszy |
| Pytanie anulowania a odświeżanie | testy zniknięcia celu, `_busy`, klik | pole celu po tożsamości |
| Fałszywy pusty stan na starcie | test „Łączenie…” | czekanie na pierwszą listę |
