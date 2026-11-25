---
kind: plan
status: accepted-decisions
baseline: main @ 1f76e30
created: 2026-11-26
---

# Plan: Biblioteka jako widok tytułów z okładkami

Plan wykonuje całą [specyfikację](specification.md): tożsamość serii, widok tytułów i odcinków, usuwanie wielu, rozpoznanie
plików ręcznych, okładki w Bibliotece i na liście Subskrypcji. Decyzje właściciela są zamknięte; wykonawca nie wybiera między
architekturami. Fakty o kodzie: [current-state.md](current-state.md); pomiary: [research-covers.md](research-covers.md).

## Warunki końcowe

- [ ] Biblioteka pokazuje tytuły serii, Enter otwiera odcinki z `Nr`, `Tytuł`, `Emisja`, `Stan`; filtr `/`; zasobnik trafia
  w odcinek.
- [ ] Zaznaczanie i usuwanie wielu z pytaniem; Kosz i Ctrl+Z po jednym.
- [ ] Pliki ręczne: `z nazwy`, „Nie rozpoznano” albo rozpoznane według F-6.
- [ ] Okładki w `config/covers/` i w slocie SIXEL Biblioteki i Subskrypcji; bez SIXEL ekran jak dziś.
- [ ] Bramki repo zielone; `AGENTS.md` obszarów i `config/README.md` aktualne; checkpointy H1–H5 przyjęte przez właściciela.

## Nie-cel

Inne ekrany panelu, odcinki niepobrane w Bibliotece, półbloki, Linux, zmiana nazw plików (workstream 23), trwały zapis serii w
`WatchState`, synchronizacja MAL/AniList.

## Authority i baseline

- Wymagania: [specification.md](specification.md). Reguły: `AGENTS.md`, `anishift/AGENTS.md`, `anishift/cli/AGENTS.md`,
  `anishift/application/AGENTS.md`, `anishift/services/catalog/AGENTS.md`, `tests/AGENTS.md`.
- Standard pracy: skille `simple`, `coding` (z `references/python.md`, `comments-docstrings.md`, `testing.md`,
  `markdown.md`), `commit`.
- Baseline: `main` @ `1f76e30`, worktree `.worktrees/library-titles-covers`, gałąź `feat/library-titles-covers`, `.venv`
  zsynchronizowane (`uv sync` wykonane 2026-11-26). Znane wcześniejsze failures: nie mierzono; faza 0 je zapisuje.

## Zasady wykonania

- Zero legacy: stara nazwa, ścieżka i mechanizm znikają w tym samym commicie (`_series_titles`, `untitled_series`,
  `_series_title`, kolumny `Nazwa`/`Odcinek`, `NativeMascotImage`, `NATIVE_MASCOT_ANCHOR`, cichy alias `X` w Bibliotece).
  Żadnych aliasów ani podwójnych ścieżek.
- Reuse przed nowym kodem: tabela niżej. Nowy moduł tylko tam, gdzie plan go wymienia.
- Nie uruchamiaj `uv ... --active`; w worktree `uv run --no-sync`. Testy najwyżej `-n 6`.
- Commit tematyczny po każdej fazie według skilla `commit`; nic nie wychodzi z komputera przed zgodą właściciela po H5.

## Reuse

| Potrzeba | Istniejące | Jak użyć |
|---|---|---|
| Graf franczyzy wielu wpisów | `_franchise_query()`, `_collect_franchise`, `franchise_traversal` | zapytanie zbiorcze serii; bez zmiany `franchise()` pojedynczego wpisu |
| Tytuł bez sezonu | `series_title`, `season_hint`, `strip_season` | tytuł serii i kryterium F-6 |
| Klucz grupy z tekstu | `normalize_series` (`acquisition.py:582`) | wyeksportować w fasadzie `anishift.application`, nie kopiować |
| Etykieta pliku | `library_label`, `LibraryLabel.episode_text` | zestawy bez klucza (I-3) |
| Wyszukiwanie tytułu | owner `find_titles` → `AniListCatalog.search`, `TitleCandidate.aliases()` | rozpoznanie F-5 |
| Odcinki wpisu | `ResidentSession.episodes(anilist_id)` → `ListedEpisode` | `Tytuł` i `Emisja` w widoku odcinków; bez nowej komendy ownera |
| Format daty odcinka | `anime_rows.episode_row` (`%d.%m.%Y`) | wydzielić jedną funkcję daty i użyć w obu miejscach |
| Tabela, okruszki, pola zaznaczenia | `render_anime`, `_spec`, `AnimeScreen.EPISODES`, `AnimeSnapshot.selected`, `mark_crumbs` | widok odcinków Biblioteki to prezentacja `EPISODES` |
| Pole tekstowe | `TextInput`, wzorzec `_history_input` | filtr `/` |
| Usuwanie | `preview_deletion`, `delete_set`, `_hidden`, `unsettled_deletions`, `undo_deletion` | pętla w jednym wątku |
| Praca ownera w tle | `_pool`, `_active_io`, `_queue.put`, `_publish_state` (wzorzec `_request_series_titles`) | seria, rozpoznanie i okładki |
| Obraz w terminalu | sonda `native_mascot_cell`, `_encode_sixel`, kotwica, `_draw_native_mascot`, `_erase_native_mascot` | uogólnić na jeden slot obrazu |
| Zapis atomowy | wzorzec `WatchStateStore` (plik tymczasowy obok + `os.replace`) | zapis okładki |

## Impact scan

| Kontrakt | Ryzyko | Obowiązek regresyjny |
|---|---|---|
| `LibrarySet` w IPC (`encode_view`, `library_details`, `library_problems`) | panel i owner muszą mieć tę samą wersję | pola z wartościami domyślnymi; restart rezydenta przed checkpointem |
| Snapshot `library` | nowe klucze | test kontraktowy snapshotu w `test_automation.py` |
| `name_series` i testy `test_library_series.py` | zmiana źródła tytułu (seria zamiast subskrypcji) | przepisać testy na nowy kontrakt; żaden test nie znika bez następcy |
| H1 i `FranchiseGraph` pojedynczego wpisu | zapytanie zbiorcze mogłoby zmienić graf H1 | osobna metoda katalogu; `franchise()` i jej testy bez zmian |
| `_library_context`, `_view_generation`, `_preserve_library_selection` | nowy poziom tytułu | kontekst obejmuje klucz tytułu; test spóźnionego wyniku |
| `show_library` z zasobnika | wybór zestawu na płaskiej liście | otwiera tytuł zestawu; test |
| `_hidden`, `_restoring`, `deleting_sets` | grupa składa się z wielu zestawów | grupowanie po odfiltrowaniu; „Przywracam…” w wierszu odcinka |
| `test_panel_keys.py` | nowe klawisze i opisy | ten sam commit aktualizuje `_DESCRIPTIONS` i test |
| Renderer i maskotka | uogólnienie slotu | testy maskotki bez zmian; nowy test klatek |
| Sieć ownera | nowe zapytania | wspólna bramka, licznik zapytań w testach |
| `.gitignore`, `config/README.md` | nowy katalog | linia `config/covers/` i opis |

## Target design

### Tożsamość serii (owner)

```text
wpisy = anilist_id zestawów pobranych (downloaded_episodes) ∪ subskrypcji ∪ rozpoznanych
  -> AniListCatalog.library_graph(wpisy): _franchise_query() po 50 ID na stronę,
     dociąga brakujące węzły łańcucha, łącznie najwyżej _MAX_FRANCHISE_REQUESTS zapytań
  -> library_series(graf, wpisy) (czysta funkcja w application/library.py):
     łańcuch każdego wpisu z franchise_traversal; łańcuchy o wspólnym węźle łączą się w jedną serię;
     series_id = wpis o formacie sezonowym z najwcześniejszą datą startu (remis: mniejsze ID),
     bez wpisu sezonowego najwcześniejszy dowolny;
     tytuł = series_title(english or romaji wpisu series_id)
  -> owner._series: dict[int, LibrarySeries(series_id, title, entry_title)]
```

- `LibrarySeries` (frozen, slots) w `application/library.py`. `entry_title` (english or romaji wpisu) służy wyłącznie
  sezonowi przez istniejące `_series_season`.
- `_series`, `_series_requested` i jedna metoda `_request_series` zastępują `_series_titles`, `_series_requested`,
  `_request_series_titles`, `_read_series_titles`, `_record_series_titles`, `untitled_series` i `_series_title`.
- Błąd lub 429: wpisy zostają bez serii do końca procesu (jak dziś); log z liczbą wpisów i klasą błędu.
- `AcquisitionService` dostaje odczyt `library_series(ids)`, który woła katalog i czystą funkcję.

### Pola zestawu (owner → panel)

```text
LibrarySet (widok, pola z domyślnymi wartościami):
  anilist_id: int | None       # wpis z downloaded_episodes albo rozpoznania
  series_id: int | None        # z _series; None, gdy seria nieznana
  title_source: str = "name"   # "key" | "recognized" | "name"
  series, season, episode      # jak dziś; series = tytuł serii
```

`name_series(sets, state, series, recognized)` ustawia te pola. Snapshot `library` dodaje `anilist_id`, `series_id`,
`title_source`; dochodzi klucz `covers` (posortowana lista ID z plikiem w cache).

### Rozpoznanie plików ręcznych (owner)

- Wejście: zestawy bez klucza; klucz zapytania = `(normalize_series(label.title), label.season or 1)`; zestawy
  nierozpoznane przez `library_label` pomija.
- Jedno `search` na klucz na uruchomienie rezydenta, sekwencyjnie przez `episode_requests()`, w puli I/O; wynik w
  `_recognized: dict[tuple[str, int], int | None]`.
- Kryterium: F-6 specyfikacji, w czystej funkcji `recognize(candidates, title, season) -> int | None` w
  `application/library.py`.
- Rozpoznane ID dołączają do wejścia tożsamości serii i okładek.

### Projekcja tytułów (panel, czysta)

```text
LibraryTitle (state_library.py, frozen):
  key: str            # "series:<id>" | "entry:<id>" | "name:<normalize_series(tytuł)>" | "none"
  title: str          # series albo label.title; "Nie rozpoznano" dla "none"
  sets: tuple[Mapping, ...]   # posortowane jak dziś _order
  cover_id: int | None        # anilist_id najnowszego zestawu z kluczem lub rozpoznanego
  source: str                 # "name", gdy żaden zestaw nie ma klucza; inaczej "key"
  problems: int
```

- `library_titles(snapshot, hidden, restoring, query)` grupuje wynik dzisiejszego `library_rows` (po odfiltrowaniu ukrytych i
  usuwanych), filtruje po `query`, sortuje `_TITLE_KEY`, „Nie rozpoznano” na końcu.
- Wiersz tytułu: `Tytuł`, `Odcinki`, `Stan` (`Gotowe`, `<n> do sprawdzenia`, `z nazwy`; teksty w `state_texts.py`).
- Wiersz odcinka: `Nr` (`episode_text`), `Tytuł` (tytuł odcinka albo nazwa zestawu dla `name`/`none`), `Emisja`, `Stan`
  (`Gotowe`, tekst problemu, „Przywracam…”); `AnimeRow.key` = `set_id`.

### Nawigacja i stan panelu

```text
TYTUŁY --Enter--> ODCINKI (okruszki: Biblioteka › <tytuł>)
ODCINKI --Esc/Backspace/klik okruszka--> TYTUŁY (kursor na tym samym key)
ODCINKI --D--> SZCZEGÓŁY (okruszki: Biblioteka › <tytuł> › <SxxEyy>) --Esc--> ODCINKI
TYTUŁY --/--> pole filtra --Enter--> TYTUŁY z filtrem; Esc w polu czyści filtr
TYTUŁY --Esc--> Home (jak dziś)
zasobnik(set_id) --> ODCINKI tytułu zestawu, kursor na zestawie
```

- Stan w `StateController`: `_library_title: str | None`, `_library_marks: set[str]`, `_library_query: str`,
  `_library_input: TextInput | None`, `_library_confirm: tuple[str, ...] | None`, `_episode_info: dict[int, dict[int,
  tuple[str | None, datetime | None]]]`. Zmiana zakładki czyści tytuł, zaznaczenia, pole i pytanie; filtr zostaje do
  wyjścia z panelu.
- Klawisze. Tytuły: Enter `odcinki`, Del `usuń`, `/` `szukaj`, Ctrl+Z `cofnij`. Odcinki: Enter `obejrzyj`, Space
  `zaznacz`, `A` `wszystkie`, `D` `szczegóły`, `F` `folder`, Del `usuń`, Ctrl+Z `cofnij`. Opis `("Space", "zaznacz")`
  staje się ogólny dla D i Del. Cichy alias `X` znika.
- `_library_context` zwraca `(tytuł, set_id)`, więc spóźnione wyniki z innego tytułu giną.
- Tytuły i daty odcinków: przy otwarciu tytułu worker (`_work`) woła `session.episodes(id)` dla każdego wpisu z kluczem w
  tytule, którego nie ma w `_episode_info`; błąd zostawia `—`.

### Usuwanie wielu

```text
Del -> cele: zaznaczone | odcinek pod kursorem | wszystkie zestawy tytułu
  1 cel  -> jak dziś (_delete_now)
  >1 cel -> _library_confirm = cele; stopka „Usunąć <n> odcinków? Enter tak · Esc nie”;
            Enter: wszystkie cele do _hidden, jeden wątek „anishift-library-delete”, jedna sesja,
            kolejno preview_deletion -> delete_set; odmowa celu zdejmuje go z _hidden z komunikatem;
            koniec: „Usunięto <n> · Ctrl+Z cofa po jednym”
            inny klawisz: pytanie znika bez skutku
```

Pytanie to prosty stan i stopka w Bibliotece, nie ogólny mechanizm (dawny `_question` nie istnieje).

### Okładki w ownerze

```text
po zmianie _series lub _recognized: brakujące = wpisy (subskrypcje ∪ klucze ∪ rozpoznane) − _covers − _covers_requested
  -> pula I/O, episode_requests():
     AniListCatalog.cover_urls(ids) -> dict[int, str]   # coverImage { extraLarge }, 50 ID na zapytanie
     dla każdego ID: AniListCatalog.cover(url) -> bytes # https, host s4.anilist.co, bez przekierowań, ≤ 2 MB, status 200
                     store_cover(bytes, covers_dir() / f"{id}.jpg")  # Pillow verify, RGB, JPEG, tmp + os.replace
  -> _queue.put(_record_covers(ids)) -> _publish_state
start ownera: _covers = ID z istniejących plików <liczba>.jpg w covers_dir() (odczyt w puli I/O)
```

- `paths.covers_dir()` zwraca `config_dir() / "covers"`; tworzy go zapis, nie odczyt ścieżki.
- `services/catalog/covers.py`: `store_cover` (walidacja i zapis). Brak okładki w odpowiedzi albo błąd pliku: ID pomija,
  licznik w logu.
- Log tylko liczby: `requested`, `stored`, `skipped`, `error_class`.

### Obraz natywny w panelu

- Nowy `cli/interactive/native_image.py` przejmuje z `mascot_native.py` sondę (`native_cell`), koder (`encode_sixel`),
  odczyt konsoli i dataclass `NativeImage` (ładunki, czasy klatek, `cell_columns`, `cell_rows`, `layout_rows`) oraz kotwicę
  `NATIVE_IMAGE_ANCHOR`. `mascot_native.py` zostaje z ładowaniem maskotki. Stare nazwy znikają.
- `TerminalRenderer` zapamiętuje komórkę z sondy (`native_cell`, `None` bez SIXEL) i dostaje `image_provider: Callable[[],
  NativeImage | None]`; aplikacja podaje maskotkę w Home, Auto i komunikatach, a w panelu obraz z `StateController.cover()`.
- `_native_anchor` liczy kolumnę w komórkach (`cell_len`).
- Rysowanie w jednym slocie:
  - ta sama pozycja, inny obraz: kasowanie komórek poprzedniego obrazu i nowy ładunek, bez `\x1b[2J`;
  - ta sama pozycja, brak obrazu: kasowanie komórek, bez `\x1b[2J`;
  - ta sama pozycja i obraz, ale zmieniła się któraś linia ramki w wierszach slotu albo rozmiar terminala: ponowny
    ładunek bez kasowania;
  - nowa pozycja albo zniknięcie kotwicy: istniejąca ścieżka `reset` + `\x1b[2J`.
- `cli/interactive/covers.py`: `CoverImages` z jednym wątkiem `anishift-cover`. Żądanie `(anilist_id, komórka)`, nowsze
  wygrywa; wynik w pamięci (do 64 ładunków). Plik czyta z `covers_dir()`, skaluje LANCZOS do pudełka, centruje na
  przezroczystym tle i koduje `encode_sixel`. Render tylko odczytuje gotowy ładunek.
- Pudełko: `COVER_ROWS = 12` wierszy, kolumny `ceil(COVER_ROWS * cell_h * COVER_ASPECT / cell_w)`, `COVER_ASPECT = 0.72`
  (pomiar 460 × 636). Stałe pudełko daje stałe komórki dla każdej okładki.

### Slot w tabeli

- `AnimeSnapshot.cover: tuple[int, int] | None` (kolumny i wiersze pudełka) ustawia `StateController`, gdy jest
  `native_cell` i na liście jest choć jeden wiersz z ID w `covers`.
- `render_anime` wstawia slot, gdy `columns ≥ szerokość tabeli + 2 + kolumny pudełka + _MARGIN` i gdy od wiersza nagłówka
  tabeli do pierwszej linii stopki jest co najmniej `COVER_ROWS` wierszy. Tabela układa się wtedy w szerokości bez slotu, a
  kotwica stoi w wierszu nagłówka, dwie kolumny za tabelą. Inaczej klatka jest identyczna z dzisiejszą (F-23).
- Komórki pudełka w tekście ramki są puste w każdej klatce (test).
- Ekrany ze slotem: lista tytułów i widok odcinków Biblioteki, lista Subskrypcji. Wybór obrazu: F-21.

### Docelowe drzewo

```text
anishift/
├── paths.py                                  # MODIFY covers_dir()
├── application/
│   ├── __init__.py                           # MODIFY eksport normalize_series
│   ├── control_views.py                      # MODIFY LibrarySet: anilist_id, series_id, title_source
│   ├── library.py                            # MODIFY LibrarySeries, library_series, recognize, name_series
│   ├── acquisition.py                        # MODIFY library_series(ids), cover_urls, cover
│   └── automation.py                         # MODIFY _series, _recognized, _covers, snapshot
├── services/catalog/
│   ├── anilist.py                            # MODIFY library_graph, cover_urls, cover
│   └── covers.py                             # CREATE store_cover
└── cli/interactive/
    ├── native_image.py                       # CREATE sonda, koder, NativeImage, kotwica
    ├── mascot_native.py                      # MODIFY tylko maskotka
    ├── covers.py                             # CREATE CoverImages
    ├── prompts.py                            # MODIFY image_provider, native_cell, reguły slotu
    ├── app.py                                # MODIFY dostawca obrazu
    ├── home.py                               # MODIFY nowa nazwa kotwicy
    ├── anime_state.py                        # MODIFY AnimeSnapshot.cover
    ├── anime_view.py                         # MODIFY kolumny tytułów, slot
    ├── anime_rows.py                         # MODIFY wspólny format daty
    ├── actions.py                            # MODIFY opisy klawiszy
    ├── state_library.py                      # MODIFY LibraryTitle, wiersze, akcje
    ├── state_texts.py                        # MODIFY teksty Biblioteki
    └── state.py                              # MODIFY poziom tytułu, filtr, zaznaczenia, usuwanie wielu, okładka
config/README.md                              # MODIFY opis covers/
.gitignore                                    # MODIFY config/covers/
```

Mapa jest sygnałem zasięgu, nie nakazem; wykonawca może przenieść funkcję do sąsiedniego istniejącego modułu bez zmiany
kontraktu.

## Plan wykonania

### Faza 0: preflight

1. `git status --short`, `git branch --show-current` (oczekiwane: czysto, `feat/library-titles-covers`).
2. Baseline wąski: `uv run --no-sync pytest -n 6 tests/cli/test_library_actions.py tests/cli/test_library_columns.py
   tests/cli/test_panel_keys.py tests/cli/test_interactive_mascot_native.py tests/application/test_library_series.py
   tests/application/test_library_label.py tests/services/catalog/test_anilist.py`; wynik do raportu fazy.
3. Przeczytaj w całości `state_library.py`, `state.py` (sekcje Biblioteki), `anime_view.py`, `prompts.py`,
   `mascot_native.py`, `library.py` (linie 170–250) i powyższe testy.

**Gate:** baseline zapisany; czerwony test baseline'u zgłoś przed zmianą.

### Faza 1: tożsamość serii w ownerze

**Cel:** F-1, F-2; zestawy z kluczem mają `anilist_id`, `series_id`, `title_source="key"` i tytuł serii.

**Działania:** `AniListCatalog.library_graph`; `LibrarySeries`, `library_series`; `AcquisitionService.library_series`;
owner `_series` zamiast `_series_titles` (usunąć stare symbole); pola `LibrarySet`; `name_series`; snapshot `library`;
eksport `normalize_series`.

**Testy (`unit`):**

- `tests/application/test_library_series.py`: `test_seasons_of_one_chain_share_one_series_whatever_their_titles`,
  `test_series_title_comes_from_the_earliest_season_entry`, `test_chains_joined_by_a_shared_node_form_one_series`,
  `test_a_film_in_the_chain_joins_its_series`, `test_downloaded_set_carries_its_entry_series_and_key_source`,
  `test_set_of_an_unknown_series_keeps_its_entry_and_file_label`, `test_hand_added_set_stays_with_name_source`;
  dotychczasowe testy `name_series` przepisane na nowe źródło tytułu.
- `tests/services/catalog/test_anilist.py`: `test_library_graph_reads_fifty_ids_per_request`,
  `test_library_graph_expands_missing_chain_nodes_within_the_request_bound` (na zapisanych grafach
  `tests/fixtures/search/anilist__franchise__*.json`).
- `tests/application/test_automation.py`: `test_owner_reads_every_library_series_in_one_batch_once`,
  `test_snapshot_library_rows_carry_entry_series_and_source`.

**Kontrola:** bramki z `AGENTS.md` (ruff, format, mypy na `anishift/ tests/`, pytest `-n 6`).

**Commit:** `feat(repo): group Library sets by their AniList series`.

### Faza 2: widok tytułów i odcinków

**Cel:** F-3, F-4, F-7–F-13.

**Działania:** `LibraryTitle`, `library_titles` i wiersze w `state_library.py`; kolumny `Tytuł`, `Odcinki`, `Stan` w
`_spec(AnimeScreen.LIBRARY)`; widok odcinków jako prezentacja `EPISODES` z okruszkami; poziom tytułu, filtr, zasobnik i
`_episode_info` w `state.py`; opisy klawiszy w `actions.py`; teksty w `state_texts.py`; wspólny format daty w
`anime_rows.py`.

**Testy (`unit`):**

- `tests/cli/test_library_titles.py` (nowy): `test_sets_of_one_series_form_one_title`,
  `test_unknown_series_groups_by_entry_until_the_series_arrives`, `test_hand_added_spellings_of_one_title_join_by_name`,
  `test_hand_added_title_shows_from_name`, `test_unparsed_names_go_to_the_unrecognized_row_last`,
  `test_hidden_and_deleting_sets_leave_their_title`, `test_problem_sets_are_counted_in_the_state_column`,
  `test_filter_keeps_titles_containing_the_normalized_text`, `test_enter_opens_the_title_and_escape_returns_to_it`,
  `test_crumb_click_returns_to_the_titles`, `test_tray_target_opens_the_title_of_its_set`,
  `test_tab_switch_closes_the_title_and_its_marks`, `test_late_episode_titles_of_another_title_are_dropped`.
- `tests/cli/test_library_columns.py`: `test_titles_fit_at_50_80_and_120_columns`,
  `test_episode_view_has_number_title_air_and_state_columns`, `test_missing_episode_data_shows_a_dash`.
- `tests/cli/test_library_actions.py`: dotychczasowe testy przeniesione na widok odcinków (Enter odtwarza, `F`, `D`, Del
  pojedynczy, Ctrl+Z, odmowy).
- `tests/cli/test_panel_keys.py`: nowe zestawy klawiszy obu poziomów, brak aliasu `X`.
- `tests/application/test_library_label.py`: `test_label_reads_the_shared_ready_name_format` (tabela z
  [research-covers.md](research-covers.md), sekcja 6).

**Human checkpoint H1:**

```text
Uruchom: zamknij rezydenta i panel z głównego checkoutu; w PowerShell 7 w folderze worktree:
  $env:ANISHIFT_CONFIG_DIR = "C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\config"
  $env:ANISHIFT_WORKSPACE_ROOT = "C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\workspace"
  uv run --no-sync anishift
  Panel → O (automat wyłączony na czas próby: worktree nie ma .env z kluczami usług) → Biblioteka
Zrób: otwórz kilka tytułów, wróć Esc, filtruj /, kliknij okruszek, kliknij wynik w zasobniku, przejdź na Subskrypcje i wróć
Oczekiwany rezultat: sezony jednej serii w jednym wierszu; odcinki SxxEyy z tytułami i datami; kursor wraca na tytuł
Zwróć uwagę na: nazwy tytułów, wiersze „z nazwy” i „Nie rozpoznano”, styl zgodny z resztą panelu
Przekaż wynik jako: lista uwag co do słów i układu
```

Po checkpoincie właściciel zamyka panel i rezydenta z worktree, uruchamia zwykłe `anishift` z głównego checkoutu i włącza
automat z powrotem (O). Kod gałęzi nie zmienia schematu `WatchState`, więc stan zostaje czytelny dla `main`.

**Commit:** `feat(tui): show the Library as titles with an episode view`.

### Faza 3: zaznaczanie i usuwanie wielu

**Cel:** F-14–F-19.

**Działania:** Space, `A`, cele Del, `_library_confirm`, pętla usuwania w jednym wątku, komunikaty.

**Testy (`unit`, `tests/cli/test_library_actions.py`):** `test_space_marks_and_a_marks_every_episode`,
`test_delete_acts_on_marks_else_on_the_cursor`, `test_title_delete_covers_every_set_of_the_title`,
`test_deleting_several_asks_first_and_any_other_key_cancels`, `test_deleting_one_asks_nothing`,
`test_several_deletes_run_in_one_worker_and_one_session`, `test_refused_set_returns_while_the_rest_go_on`,
`test_several_deleted_notice_says_undo_goes_one_by_one`.

**Human checkpoint H2:**

```text
Uruchom: jak H1, na kopiach kilku plików wrzuconych do workspace (nie na jedynych kopiach)
Zrób: zaznacz 3 odcinki, Del, Enter; potem Ctrl+Z trzy razy; Del na tytule z 2 kopiami, Esc
Oczekiwany rezultat: pytanie przy więcej niż jednym; pliki w Koszu; Ctrl+Z przywraca po jednym; Esc nic nie usuwa
Zwróć uwagę na: zrozumiałość pytania i komunikatu, skok kursora
Przekaż wynik jako: lista uwag
```

**Commit:** `feat(tui): mark and delete several Library episodes at once`.

### Faza 4: rozpoznanie plików ręcznych

**Cel:** F-5, F-6. Koszt zmierzony: 28 unikalnych tytułów, czyli do 28 wyszukiwań na start rezydenta (research, sekcja 5).

**Działania:** `recognize` w `application/library.py`; `_recognized` i praca w puli w ownerze; `title_source="recognized"`;
rozpoznane ID w wejściu serii.

**Testy (`unit`):** `tests/application/test_library_series.py`:
`test_one_alias_with_matching_title_and_season_is_recognized`, `test_two_matching_candidates_stay_from_name`,
`test_matching_title_with_another_season_stays_from_name`, `test_seasonless_name_matches_only_a_first_season`;
`tests/application/test_automation.py`: `test_owner_searches_each_hand_added_title_once_per_run`,
`test_rate_limited_search_leaves_the_title_from_name`, `test_recognized_set_joins_its_series`.

**Human checkpoint H3:**

```text
Uruchom: jak H1
Zrób: przejrzyj tytuły, które dotąd miały „z nazwy”
Oczekiwany rezultat: rozpoznane pliki ręczne leżą pod właściwą serią; wątpliwe zostają „z nazwy”
Zwróć uwagę na: każdy błędnie przypisany plik (to błąd krytyczny)
Przekaż wynik jako: lista złych przypisań i tytułów, które powinny się rozpoznać
```

**Commit:** `feat(application): recognize hand-added Library files on AniList`.

### Faza 5: okładki w ownerze

**Cel:** F-20; pliki w `config/covers/`.

**Działania:** `covers_dir()`; `cover_urls`, `cover` w `AniListCatalog` i odczyty w `AcquisitionService`;
`services/catalog/covers.py`; `_covers`, `_covers_requested`, praca w puli; klucz snapshotu `covers`; `.gitignore`;
`config/README.md`.

**Testy (`unit`):** `tests/services/catalog/test_anilist.py`: `test_cover_urls_read_extra_large_by_id`,
`test_missing_or_null_cover_is_skipped`, `test_cover_refuses_another_host`, `test_cover_refuses_plain_http`,
`test_cover_refuses_a_redirect`, `test_cover_refuses_more_than_two_megabytes` (atrapy zbudowane na kształcie z research,
sekcja 3); `tests/services/catalog/test_covers.py`: `test_store_writes_a_jpeg_atomically`,
`test_store_refuses_a_broken_image`, `test_store_names_the_file_only_after_the_id`;
`tests/application/test_automation.py`: `test_owner_fetches_only_missing_covers_once`,
`test_owner_reads_existing_covers_at_start`, `test_snapshot_lists_cached_covers`,
`test_cover_fetch_stops_when_shutting_down`.

**Human checkpoint H4 (krótki):**

```text
Uruchom: jak H1, poczekaj minutę po starcie
Zrób: otwórz config\covers w Eksploratorze
Oczekiwany rezultat: około 33 plików <liczba>.jpg z okładkami Twoich tytułów
Przekaż wynik jako: „jest” albo opis braków
```

**Commit:** `feat(repo): cache AniList covers of Library and subscription titles`.

### Faza 6: slot okładki w panelu

**Cel:** F-21–F-24, Q-1.

**Działania:** `native_image.py` (przeniesienie z `mascot_native.py`, nowe nazwy we wszystkich wywołaniach i testach);
`image_provider` i reguły slotu w `prompts.py`; kolumna kotwicy w komórkach; `covers.py` (`CoverImages`);
`AnimeSnapshot.cover` i slot w `anime_view.py`; `StateController.cover()` i ustawienie slotu dla Biblioteki i Subskrypcji;
dostawca w `app.py`.

**Testy (`unit`):** `tests/cli/test_interactive_mascot_native.py` przeniesione na nowe nazwy bez zmiany oczekiwań;
`tests/cli/test_library_covers.py` (nowy): `test_slot_absent_without_sixel`, `test_slot_absent_when_the_terminal_is_small`,
`test_slot_absent_when_no_listed_title_has_a_cover`, `test_frame_without_slot_equals_the_plain_layout`,
`test_slot_cells_stay_blank_in_the_frame`, `test_render_neither_reads_files_nor_encodes`,
`test_title_cover_is_the_newest_set_entry`, `test_subscription_row_shows_its_own_cover`;
`tests/cli/test_interactive_app.py` albo nowy `tests/cli/test_interactive_native_image.py` z atrapą wyjścia:
`test_new_image_in_place_erases_cells_without_clearing_the_screen`,
`test_changed_line_in_slot_rows_redraws_the_same_image`, `test_unchanged_frame_writes_no_image`,
`test_moved_slot_clears_the_screen_once`, `test_anchor_column_counts_wide_characters_as_two_cells`,
`test_mascot_frames_match_the_previous_output`.

**Human checkpoint H5:**

```text
Uruchom: jak H1, w Windows Terminal, w którym widać maskotkę
Zrób: przesuwaj kursor po tytułach Biblioteki i Subskrypcji, przewijaj stronami, otwórz tytuł, zmień rozmiar okna,
      przełącz zakładki, wróć na Home
Oczekiwany rezultat: okładka zmienia się z wierszem, bez mignięcia całego ekranu i bez urwanych fragmentów; przy
      wąskim oknie ekran jak dziś; maskotka na Home jak dawniej
Zwróć uwagę na: ślady rastra po przewinięciu i zmianie zakładki, opóźnienie okładki, czy to nadal ten sam panel
Przekaż wynik jako: lista uwag
```

**Commit:** `feat(tui): draw the title cover beside the Library and Subscriptions lists`.

### Faza 7: dokumentacja i zamknięcie

1. `anishift/cli/AGENTS.md` (Biblioteka, renderer i obraz natywny), `anishift/application/AGENTS.md` (seria, rozpoznanie,
   okładki), `anishift/services/catalog/AGENTS.md` (pliki i inwarianty), `docs/README.md` (status 18),
   `docs/ideas.md` (pozycje sekcji 2 do „Zrealizowane”).
2. Pełne bramki z `AGENTS.md`.
3. Niezależne review całej gałęzi przez inny model niż autor, skill `review`; poprawki w commitach tematów.
4. Pull request dopiero po zgodzie właściciela, z opisem w pełnej postaci skilla `commit`.

**Commit:** `docs(repo): record the Library titles and covers workstream`.

## Strategia dowodu

- Testy: marker `pytest.mark.unit` na poziomie modułu; zero prozy w testach (hook `no-test-prose`); atrapy AniList tylko z
  kształtem z research, sekcja 3; sieć wyłącznie w testach `network` (żaden nowy test jej nie wymaga).
- Regresje obowiązkowe: całe `tests/cli`, `tests/application/test_library_*.py`, `tests/application/test_automation.py`,
  `tests/services/catalog`.
- Bramki przed każdym commitem: `uv run --no-sync ruff check anishift/ tests/`, `uv run --no-sync ruff format --check
  anishift/ tests/`, `uv run --no-sync mypy anishift/ tests/`, `uv run --no-sync pytest -n 6`.
- Human acceptance: H1–H5; PASS = właściciel przyjmuje wynik bez uwag blokujących.

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Eskalacja |
|---|---|---|---|
| Łańcuch `SEQUEL` łączy spin-off z serią | H1: obcy tytuł pod serią | ograniczyć łączenie do formatów sezonowych i filmów | zmiana definicji serii → właściciel |
| `erase_end_of_line` lub ponowny zapis rastra migocze | H5 | rysować ponownie tylko przy zmianie linii w wierszach slotu (już w planie); wydłużyć próg | brak rozwiązania → decyzja o slocie |
| Kodowanie okładki opóźnia obraz | H5: widoczne opóźnienie | po wybranej okładce kodować w tle sąsiednie wiersze | zmiana pudełka → właściciel |
| Pomyłka rozpoznania pliku ręcznego | H3 | zaostrzyć kryterium F-6; domyślnie `z nazwy` | zmiana F-6 → właściciel |
| 429 przy starcie rezydenta | log liczników | sekwencyjnie, bez ponowień w tym samym procesie | trwały zapis serii (odłożone) |
| Stary rezydent nie zna nowych pól | panel bez tytułów serii | restart rezydenta z kodu gałęzi | — |
| Zmiana kontraktu przez workstream 23 | konflikt w `LibrarySet` lub `name_series` | merge z `main` i ponowne bramki | sprzeczność → orkiestrator |

## Lokalna adaptacja

Nazwy helperów i testów, plik testu renderera, dokładne polskie teksty poza „Nie rozpoznano”, `z nazwy`, pytaniem i
komunikatem usuwania (te ustala H1/H2), miejsce funkcji w istniejących modułach, nowy `AnimeScreen` dla widoku odcinków
Biblioteki, jeśli prezentacja `EPISODES` koliduje z jej semantyką (spinner, wiersz liczby zaznaczeń).

## Materialna zmiana (zatrzymaj się i wróć)

Zmiana `WatchState`, druga ścieżka renderu obrazu, drugi slot w jednej klatce, nowa zależność, zmiana wyglądu poza slotem,
zmiana `franchise()` lub danych H1, pobieranie okładek poza ownerem, komenda IPC zmieniająca stan, rozszerzenie na inne ekrany.

## Wykonawcy

Jeden autor kodu na całość (fazy 0–7, sprzężone: owner, panel i renderer), świeża instancja na fazę 6, jeśli kontekst po
fazie 5 jest duży. Recenzent: inny model niż autor, tylko odczyt, po fazie 4 (dane i usuwanie) i przed pull requestem
(całość). Brief według `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`; zaczyna się od przeczytania skilli
`simple`, `coding` z `references/python.md` i `commit`, zawiera regułę zero legacy i zakaz `--active`.

## Definition of Done

- [ ] F-1–F-24 spełnione.
- [ ] Bramki repo zielone na `anishift/ tests/`.
- [ ] Zakazy specyfikacji zachowane.
- [ ] H1–H5 przyjęte; wyniki w `outcomes/01-library-titles-covers.md`.
- [ ] `AGENTS.md` obszarów, `config/README.md`, `docs/README.md`, `docs/ideas.md` aktualne; niezależne review bez
  otwartych blockerów.

## Kontrakt wyniku wykonania

```text
status
finalny rezultat
zmienione elementy i commity
konkretne dowody (komendy i wyniki)
human feedback H1–H5
lokalne odchylenia
materialne odkrycia
znane ograniczenia
stan repo
rekomendowany następny krok
```
