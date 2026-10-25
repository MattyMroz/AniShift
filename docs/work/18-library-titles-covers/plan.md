---
kind: plan
status: draft
baseline: main @ 4365a51
created: 2026-10-25
---

# Plan: Biblioteka jako widok tytułów, potem okładki w panelu

Plan nie startuje przed akceptacją decyzji z [specification.md](specification.md), sekcja „Nierozstrzygnięte”.
Przyjęto rekomendacje O-1…O-11; odpowiedź właściciela inna niż rekomendacja zmienia wskazane fazy (kolumna „Blokuje”).

Dwie części to dwa PR-y z jednym kontraktem danych (`anilist_id` tytułu), ale z różnymi podsystemami i różnym ryzykiem:

- **Część I (b):** tytuły, odcinki, zaznaczanie, usuwanie, Ctrl+Z. Rezultat akceptowalny samodzielnie.
- **Część II (a):** okładki. Zależy od części I tylko pozycją slotu i źródłem `anilist_id`; zależy od decyzji O-2.

Test granicy (planning §Granica): wynik części I może zmienić design części II (miejsce w układzie listy, wysokość
widoku), więc część II planuje się szczegółowo dopiero po checkpoint H2, a tu daje jej kontrakt i fazy.

## Warunki końcowe

- [ ] Część I: Biblioteka pokazuje tytuły → odcinki; zaznaczanie i usuwanie wielu; Kosz i Ctrl+Z zgodnie z O-6.
- [ ] Część II: okładka w slocie, gdy SIXEL i miejsce; w pozostałych przypadkach ekran bez zmian.
- [ ] Bramki repo przechodzą; scoped `AGENTS.md` zaktualizowane.
- [ ] H1…H4 wykonane przez właściciela.

## Nie-cel

Zmiany Anime/Przetwarzania/Historii, odcinki jeszcze niepobrane w Bibliotece, półbloki, Linux, synchronizacja MAL/AniList,
foldery serii na dysku, nowe pliki konfiguracyjne.

## Authority i baseline

| Źródło | Rola |
|---|---|
| `specification.md` tego katalogu | wymagania i decyzje |
| `current-state.md` | stan kodu z liniami |
| `research-covers.md` | dowody o terminalu i AniList |
| `AGENTS.md`, `anishift/AGENTS.md`, `anishift/cli/AGENTS.md`, `anishift/application/AGENTS.md`, `tests/AGENTS.md` | reguły repo |
| `.agents/skills/simple`, `coding` (+ `references/python.md`, `comments-docstrings.md`, `testing.md`) | standard pracy |

**Baseline:** `main` @ `4365a51`, drzewo czyste. **Znane wcześniejsze failures:** nie zmierzono (zakaz uruchamiania w zleceniu planisty);
faza 0 zapisuje wynik `uv run pytest` przed zmianami.

## Reuse (obowiązek `AGENTS.md`)

| Potrzeba | Istniejące | Ograniczenie |
|---|---|---|
| Układ „lista → Enter → okruszki” | `AnimeScreen`, `_table_body`, `mark_crumbs`, `CRUMB_SEPARATOR` (`anime_view.py`, `pointer.py:63`, `state.py:1397`) | Biblioteka używa `AnimeScreen.LIBRARY`; ekran odcinków reużyje `_spec` z kolumnami `Nr, Tytuł, Emisja, Stan` (`anime_view.py:371-376`) |
| Etykieta z pliku | `library_label`, `LibraryLabel.episode_text` (`library.py:109`, `:95`) | zostaje źródłem dla zestawów bez klucza (I-3) |
| Nazwa serii | `series_title`, `name_series`, `downloaded_episodes` (`library.py:185-250`) | rozszerzyć, nie dublować |
| Normalizacja klucza grupy | `normalize_series` (`application/acquisition.py:590`) | sprawdzić eksport; importować z istniejącego modułu |
| Wyszukiwarka w liście | `_history_input`, `TextInput`, `_history_input_key` (`state.py:258`, `:819-845`) | ten sam wzorzec, bez nowego edytora tekstu |
| Pytanie przed działaniem | `_question`, `_question_key` (`state.py:390`) | użyć do usuwania > 1 zestawu |
| Usuwanie | `preview_deletion`, `delete_set`, `_delete_hidden`, `undo_deletion` (`resident.py:145-175`) | bez równoległych sesji (F-13) |
| Dane odcinków (tytuł, emisja) | `ListedEpisode`, ani.zip (`episode_selection.py:267`, `anizip.py`), `AnimeController._load_episodes` | symbol serwisu do potwierdzenia w fazie 4 |
| Obraz natywny | `encode_sixel`, `native_mascot_cell`, kotwica ``, `_draw_native_mascot` (`mascot_native.py`, `prompts.py:325-389`) | jedno miejsce na obraz; uogólnić, nie powielać |
| Zaznaczanie w liście | `AnimeViewState.toggle/select_all`, `AnimeSnapshot.selected` (`anime_state.py`) | wiersze Biblioteki mają `AnimeRow.key` = `set_id` |
| Okruszki, klik, hover | `pointer.py` (`mark_row`, `mark_crumbs`) | testy `test_interactive_mouse.py`, `test_interactive_hover.py` |

## Impact scan

| Kontrakt | Ryzyko | Obowiązek regresyjny |
|---|---|---|
| `LibrarySet` i jego `encode_view/decode_view` (`control_views.py:93`) | nowe pola z domyślnymi wartościami; rezydent starej wersji nie zna pól | pola opcjonalne na końcu; test dekodowania starego słownika; restart rezydenta po zmianie (reguła repo) |
| Snapshot `library` (`automation.py:1817`) | rozszerzenie klucza | test kontraktowy snapshotu |
| IPC: lista komend (`automation.py:559`, `:588`) | nowa komenda tylko-do-odczytu (faza 4, 7) | dopisać do właściwej listy, test odmowy bez sesji |
| `_latest_deletion` (`automation.py:2344`) | zmiana semantyki Ctrl+Z (O-6) | testy `restore_nothing`, `restore_already_completed`, kolejność wielu cofnięć, restart w trakcie |
| `test_panel_keys.py` | `ScreenActions` i `_DESCRIPTIONS` muszą pokrywać nowe klawisze | zaktualizować `_DESCRIPTIONS` i testy w tym samym commicie |
| `_hidden` i `unsettled_deletions` (`state_library.py:67-76`) | wiersz tytułu składa się z wielu zestawów; ukrywanie per zestaw | grupowanie liczy się po odfiltrowaniu `_hidden` |
| `_library_context` i `_view_generation` (`state.py:346`) | spóźnione wyniki z poziomu odcinków | kontekst obejmuje klucz tytułu |
| Renderer: jeden slot obrazu (`prompts.py:253`) | uogólnienie dotyka maskotki | testy maskotki i Home bez zmian (`test_interactive_*`) |
| Maskotka i Home/Auto | zmiana wyglądu zabroniona | porównanie klatek przed/po w teście |
| Sieć ownera | dodatkowe zapytania katalogu | wspólna bramka, licznik zapytań w teście |

## Target design

### Odpowiedzialności

| Element | Odpowiada za | Owner danych | Nie odpowiada za |
|---|---|---|---|
| `application/library.py` | tożsamość tytułu zestawu: `anilist_id`, `title_source` | owner | grupowanie na ekran |
| `state_library.py` | czysta projekcja zestawów w tytuły i wiersze; zbiór kolumn | panel (stan lokalny: kursor, zaznaczenia) | usuwanie plików |
| `StateController` | nawigacja tytuł ↔ odcinki, klawisze, workery | panel | źródło prawdy zestawów |
| owner `library_episode_info` | tytuł odcinka, emisja | owner | render |
| `services/catalog/posters.py` | pobranie i zapis pliku okładki | owner (katalog `config/watch/posters/`) | wybór, które tytuły |
| `TerminalRenderer` | rysowanie obrazu w slocie | renderer | pobieranie, kodowanie |
| `cover_native.py` | plik → ładunek SIXEL w komórkach | panel (worker) | I/O w renderze |

### Model danych (część I)

```text
LibrarySet (owner, rozszerzenie; pola opcjonalne na końcu):
  anilist_id: int | None          # z DownloadedEpisode, None dla plików ręcznych
  title_source: str               # "key" | "name"   (+ "recognized" po fazie 3)
  (series, season, episode pozostają jak dziś)

LibraryTitle (panel, niezmienny, nietrwały):
  key: str          # normalize_series(tytuł etykiety)
  title: str
  sets: tuple[mapping, ...]       # wiersze snapshotu, posortowane jak _order
  cover_id: int | None            # anilist_id pierwszego zestawu z kluczem
  source: str                     # "key" jeśli którykolwiek zestaw z kluczem, "name", albo "none"
  problems: int                   # liczba zestawów z library_problems
```

- Grupowanie: `key` z `_label(item).title`. Zestaw bez tytułu i odcinka (`LibraryLabel(stem, None, None)` i brak
  `series`) trafia do grupy `none` o stałym kluczu, wyświetlanej jako „Nie rozpoznano” na końcu listy (O-9).
- Kolejność tytułów: `_TITLE_KEY` (naturalna), „Nie rozpoznano” ostatni.
- Ukryte i usuwane zestawy (`_hidden`, `deletions`) są odfiltrowywane przed grupowaniem (`library_rows`).
- Tytuł `z nazwy` ma oznaczenie w kolumnie `Stan` (np. `z nazwy`), tekst do ustalenia w H1; tekst tylko z `state_texts.py`.

### Nawigacja (część I)

```text
LIST (tytuły) --Enter--> TITLE (odcinki)
TITLE --Esc/Backspace/klik okruszka--> LIST (kursor zachowany po key tytułu)
TITLE --D--> DETAILS (pliki zestawu, jak dziś) --Esc--> TITLE
LIST --Esc--> Home (jak dziś)
```

Stan: `_library_title: str | None` (klucz otwartego tytułu), `_marks: set[str]` (set_id zaznaczonych), reset przy zmianie zakładki,
wyjściu z tytułu i zmianie tytułu. Klawisze: `Space` zaznacz, `A` wszystkie, `Del`, `/` filtr (tylko LIST), `F`, `D`, `Enter`, `Ctrl+Z`.
Odtwarzanie przy Enter na odcinku: ścieżka `_file_action("open")` bez zmian.

### Usuwanie wielu (część I)

```text
Del -> zbiór set_id (zaznaczone | kursor | wszystkie zestawy tytułu)
  > 1 zestaw -> _question "Enter tak · Esc nie" (O-7)
  -> jeden wątek roboczy, zestawy kolejno: preview_deletion -> delete_set
  -> _hidden[set_id] per zestaw; odmowa zestawu: wraca wiersz + komunikat, pozostałe idą dalej
  -> komunikat "Usunięto N · Ctrl+Z cofa po jednym" (O-6)
```

Owner (O-6): `_latest_deletion` pomija wpisy z `restore.completed`, więc kolejne `deletion_undo` cofają kolejne usunięcia w
odwrotnej kolejności. Bez zmiany schematu trwałego stanu.

### Dane odcinka (część I)

Komenda ownera tylko do odczytu `library_episode_info {anilist_id}` zwraca `[{number, title|null, airs_at|null}]` z istniejącego
źródła odcinków (ani.zip, ten sam cache co ekran odcinków). Panel woła ją workerem przy otwarciu tytułu i wstawia wynik do
wierszy; render czyta tylko stan. Brak odpowiedzi = `—` w obu kolumnach. Odmowa katalogu nie blokuje widoku.

### Rozpoznawanie plików ręcznych (faza 3, warunkowa)

Dla znormalizowanego tytułu `z nazwy` owner wywołuje `AniListCatalog.search` przez bramkę sieci. Kryterium (O-5): dokładnie jeden
kandydat, którego `aliases()` zawiera tytuł z nazwy (casefold), i zgodny sezon (`season_hint`). Wynik tylko w pamięci ownera
(`dict[str, int | None]`, jak `_series_titles`), jedno zapytanie na unikalny tytuł, raz na proces. Przy 429 lub błędzie: `z nazwy`.
Faza startuje dopiero po pomiarze z fazy 0 (czas przy ~100 plikach z ≤ 30 tytułami) i po H2.

### Okładki (część II)

```text
owner: ids = anilist_id(subskrypcje ∪ pobrane serie ∪ rozpoznane) − ids w cache
  -> AniListCatalog.covers(ids)  (jedno zapytanie id_in ≤ 50, coverImage { large })
  -> PosterStore.fetch(id, url): https + host z odpowiedzi AniList, limit rozmiaru, Pillow verify, zapis atomowy
     config/watch/posters/<id>.jpg   (nazwa wyłącznie z liczby)
panel: worker (debounce ~150 ms po zmianie wyboru) -> cover_native.load(path, cell, rows) -> ładunek SIXEL w pamięci (LRU)
render: slot z gotowym ładunkiem, inaczej pusto; po zmianie ładunku w tym samym miejscu bez czyszczenia ekranu
```

- Slot: `COVER_FRAME_ROWS = 12` wierszy, szerokość `ceil(0.667 · rows · cell_h / cell_w)` komórek (okładka 2:3), zakotwiczony
  po prawej stronie tabeli. Pokazywany, gdy `columns ≥ szerokość_tabeli + 2 + szerokość_slotu + margines` i `rows ≥ COVER_FRAME_ROWS + chrome`;
  inaczej układ identyczny z dzisiejszym (F-18).
- Renderer: ta sama kotwica `` i ten sam slot; źródło obrazu (maskotka albo okładka) wskazuje wywołujący. Home/Auto
  i panel nigdy nie rysują obu naraz (`app.py:961-1000`).
- Bezpieczeństwo pobierania: tylko `https`, host z odpowiedzi AniList (lista dozwolonych hostów z fazy 0), brak
  przekierowań poza listę, limit 2 MB, `Image.verify`, nazwa pliku z `int`, brak logowania URL.
- Cache: bez wygaszania (tylko tytuły z biblioteki i subskrypcji, rząd dziesiątek plików); ponowne pobranie przy zmianie URL.

## Mapa plików (oczekiwany zasięg, nie nakaz)

| Ścieżka | Operacja | Rola | Uwagi |
|---|---|---|---|
| `anishift/application/control_views.py` | MODIFY | `LibrarySet`: `anilist_id`, `title_source` | pola opcjonalne |
| `anishift/application/library.py` | MODIFY | `name_series` ustawia nowe pola | |
| `anishift/application/automation.py` | MODIFY | snapshot `library`, `_latest_deletion`, komendy `library_episode_info`, (II) ścieżka okładek | blisko `:1817`, `:2344`, `:8105` |
| `anishift/cli/resident.py` | MODIFY | `library_episode_info()` w sesji | |
| `anishift/cli/interactive/state_library.py` | MODIFY | `LibraryTitle`, `library_titles`, wiersze tytułów i odcinków, akcje | czysty moduł |
| `anishift/cli/interactive/state_texts.py` | MODIFY | teksty: „Nie rozpoznano”, `z nazwy`, pytanie usunięcia | jedyne miejsce polskich tekstów list |
| `anishift/cli/interactive/state.py` | MODIFY | nawigacja tytuł ↔ odcinki, zaznaczenia, `/`, usuwanie wielu | |
| `anishift/cli/interactive/actions.py` | MODIFY | `_DESCRIPTIONS` nowych klawiszy | |
| `anishift/cli/interactive/anime_view.py` | MODIFY | kolumny listy tytułów Biblioteki; widok odcinków z `Nr, Tytuł, Emisja, Stan` | bez zmiany palety |
| `anishift/cli/interactive/anime_state.py` | READ ONLY / MODIFY | `AnimeRow`/`AnimeSnapshot` wystarczają; dodać pole tylko, jeśli test tego wymaga | |
| `anishift/paths.py` | MODIFY (II) | `poster_dir()` | |
| `anishift/services/catalog/anilist.py` | MODIFY (II) | `covers(ids)` | |
| `anishift/services/catalog/posters.py` | CREATE (II) | `PosterStore` | |
| `anishift/cli/interactive/cover_native.py` | CREATE (II) | plik → ładunek SIXEL | używa `encode_sixel` |
| `anishift/cli/interactive/mascot_native.py` | MODIFY (II) | uwidocznić `encode_sixel` | bez zmiany zachowania maskotki |
| `anishift/cli/interactive/prompts.py` | MODIFY (II) | źródło obrazu w slocie | |
| `anishift/cli/interactive/app.py` | MODIFY (II) | przekazanie okładki do renderera | |
| `anishift/cli/AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/services/catalog/AGENTS.md` | MODIFY | opis Biblioteki tytułów, usuwania wielu, okładek | w commicie danej funkcji |
| `tests/cli/test_library_titles.py` | CREATE | grupowanie i widok tytułów | |
| `tests/cli/test_library_actions.py`, `test_library_columns.py` | MODIFY | nowe wiersze i akcje | |
| `tests/application/test_library_titles.py` | CREATE | tożsamość tytułu i `_latest_deletion` |
| `tests/services/catalog/test_posters.py` | CREATE (II) | pobranie, walidacja, atomowość | |
| `tests/cli/test_library_covers.py` | CREATE (II) | slot, degradacja, brak I/O w renderze | |
| `docs/README.md`, `docs/ideas.md` | MODIFY | wiersz workstreamu 18; przeniesienie pozycji do „Zrealizowane” po scaleniu | `docs(repo)` |

## Branch, commity, bramki

- Branche: `work/tui/03-library-titles` (część I) i `work/tui/04-library-covers` (część II, od stanu po scaleniu I). Numer do
  potwierdzenia względem istniejących gałęzi w chwili startu. Praca w głównym checkout, bez worktree (preferencja właściciela).
  Nie commitować na `main`. Feature branch → PR → merge. Rezydent zamknięty przed zmianą plików, które czyta, i restart po zmianie ownera.
- Commity tematyczne (jeden na spójny temat, poprawki z review wchodzą w commit tematu), format `typ(scope): opis`, scope z listy
  hooka, bez śladów AI w treści; stopka zgodna z regułami sesji wykonawcy:
  1. `feat(application): name every Library set after its catalogue series and title source`
  2. `feat(tui): show the Library as a list of titles with an episode view`
  3. `feat(application): undo deletions one after another` oraz `feat(tui): mark and delete several Library episodes at once`
  4. `feat(application): serve episode titles and air dates for a Library title`
  5. (II) `feat(services): read cover URLs from AniList and store posters`
  6. (II) `feat(application): fetch title covers in the background`
  7. (II) `feat(tui): draw a cover beside the Library and Subscriptions lists`
  8. `docs(repo): record the Library titles and covers workstream`
- Bramki przed każdym commitem (zawsze na `anishift/ tests/`):

```text
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

- Zero nowych issue bez prośby właściciela.

## Plan wykonania

### Faza 0 — preflight i pomiary (bez zmian w repo poza `scripts/tmp/`)

**Cel:** zmierzyć niewiadome i zapisać baseline.

**Działania:**

1. `git status`, branch, `uv run pytest`; zapisać wynik jako baseline failures.
2. Pomiar (część I): czas `library_label` i grupowania dla 300 syntetycznych nazw (jednorazowy skrypt w `scripts/tmp/`).
3. Pomiar (część II): pobrać 5 okładek z AniList (`coverImage.large` i `extraLarge`), zapisać wymiary, bajty, host,
   nagłówki `X-RateLimit-*` przed i po; zmierzyć `encode_sixel` slotu 12 wierszy. Skrypt i pliki usunąć po pomiarze.
4. Zapisać wyniki w `docs/work/18-library-titles-covers/research/measurements.md` (po polsku, liczby i komendy).
5. Zweryfikować w teście ownera, że drugi `deletion_undo` dziś zwraca `restore_already_completed` (potwierdzenie z odczytu).

**Gate:** komplet liczb; brak rozbieżności z założeniami O-5/O-6. Rozbieżność = zatrzymaj i wróć do właściciela.

### Faza 1 — tożsamość tytułu (owner) i projekcja (panel)

**Cel:** każdy zestaw ma `anilist_id`/`title_source`; panel umie zbudować `LibraryTitle`.

**Działania:** rozszerzyć `LibrarySet` i `name_series`; snapshot `library`; `library_titles()` w `state_library.py`; teksty w `state_texts.py`.

**Inwarianty:** I-1…I-4; `library_label` bez zmian; brak I/O.

**Kontrola:** testy `tests/cli/test_library_titles.py`, `tests/application/test_library_titles.py` (lista niżej), bramki.

**Gate:** projekcja przechodzi testy na przypadkach: Slime S4 w trzech zapisach, film bez numeru, plik bez tytułu, zestaw z problemem.

### Faza 2 — widok tytułów i odcinków

**Cel:** F-1…F-9, F-16 (filtr).

**Działania:** stan nawigacji w `StateController`; tabela tytułów i odcinków w `anime_view.py`; okruszki i kliknięcia; stopka z `ScreenActions`;
`/` jak w Historii; zachowanie kursora i `_view_generation`.

**Human checkpoint H1:**

```text
Uruchom: anishift (zamknij wcześniej stary rezydent), Panel → Biblioteka
Zrób: otwórz tytuł, wróć Esc, filtruj /, kliknij okruszek, przejdź na Subskrypcje i wróć
Oczekiwany rezultat: lista tytułów, widok odcinków jak ekran odcinków Anime, kursor wraca na tytuł
Zwróć uwagę na: czytelność kolumn przy 80 i 120 kolumnach, tekst „z nazwy”, wiersz „Nie rozpoznano”, zgodność stylu z resztą panelu
Przekaż wynik jako: lista uwag co do słów i układu (styl panelu bez zmian)
```

**Gate:** testy, bramki, H1.

### Faza 3 — zaznaczanie, usuwanie wielu, Ctrl+Z (O-6, O-7)

**Cel:** F-10…F-15.

**Działania:** `Space`/`A`; zbiór celów; pytanie > 1; jeden wątek roboczy sekwencyjnie; `_latest_deletion` pomija przywrócone; komunikaty.

**Inwarianty:** odmowa jednego zestawu nie cofa reszty; wiersz wraca z odmową; Kosz bez zmian.

**Human checkpoint H2:**

```text
Uruchom: Panel → Biblioteka na kopii kilku plików testowych (nie na jedynych kopiach)
Zrób: zaznacz 3 odcinki, Del, potwierdź; potem Ctrl+Z trzykrotnie
Oczekiwany rezultat: odcinki znikają, trafiają do Kosza Windows, wracają po jednym w odwrotnej kolejności
Zwróć uwagę na: czy komunikat o cofaniu po jednym jest zrozumiały, czy kursor nie skacze
Przekaż wynik jako: lista uwag
```

**Gate:** testy, bramki, H2. Po H2 decyzja o fazie 3b (rozpoznawanie) i o starcie części II.

### Faza 4 — tytuł odcinka i Emisja

**Cel:** F-6. Komenda `library_episode_info`, `ResidentSession.library_episode_info`, worker panelu przy otwarciu tytułu.

**Kontrola:** testy komendy (odmowa bez sesji, brak katalogu, wynik z atrapą źródła), test panelu bez I/O w renderze.

**Gate:** brak nowego zapytania sieciowego poza istniejącą bramką; bramki.

### Faza 5 — rozpoznawanie plików ręcznych (warunkowa, po H2 i pomiarze)

**Cel:** O-5. Wykonać tylko po akceptacji właściciela i gdy pomiar z fazy 0 mieści się w limicie (≤ 30 zapytań przy ok. 30 tytułach).

**Kontrola:** testy kryterium pewności (jednoznaczny, niejednoznaczny, zły sezon, 429), test „nigdy ciche przypisanie”.

### Część II — okładki (po scaleniu części I i decyzji O-2)

#### Faza 6 — katalog i magazyn

`AniListCatalog.covers(ids)`, `PosterStore`, `poster_dir()`. Test kontraktowy na zapisanej odpowiedzi (z `coverImage`, bez
`coverImage`, `null`), testy walidacji (host spoza listy, `http`, za duży plik, uszkodzony obraz, zapis atomowy).

**Gate:** testy, bramki.

#### Faza 7 — owner pobiera w tle

Wzorzec `_request_series_titles` (`automation.py:8105`): zbiór brakujących `anilist_id`, jedno zapytanie, pobieranie sekwencyjne przez bramkę
sieci, log tylko liczników. Test: brak ponownego pobrania, brak pobrania przy braku sieci, zatrzymanie przy `shutting_down`.

**Gate:** testy, bramki, pomiar `X-RateLimit-Remaining` w fazie 0 nie przekroczony.

#### Faza 8 — renderer: źródło obrazu w slocie

Wspólny `encode_sixel`; `cover_native.py`; renderer przyjmuje obraz od wywołującego; maskotka bez zmian.

**Gate:** testy renderera z atrapą wyjścia (kolejność: zapis kursora, kasowanie komórek, ładunek, odtworzenie kursora; brak `\x1b[2J` przy
zmianie zawartości w tym samym miejscu), testy maskotki bez zmian.

#### Faza 9 — slot w listach

Geometria slotu w `anime_view.py`, wiązanie z wyborem w `StateController`, debounce i LRU ładunków, wyłączenia z F-18.

**Human checkpoint H3 (SIXEL):**

```text
Uruchom: Panel → Biblioteka, potem Subskrypcje, w Windows Terminal z SIXEL (ten sam, w którym działa maskotka)
Zrób: przesuwaj kursor po 30 tytułach, zmień rozmiar okna, przełącz zakładki
Oczekiwany rezultat: okładka zmienia się razem z wierszem, bez mignięć całego ekranu; przy wąskim oknie ekran jak dziś
Zwróć uwagę na: położenie bloku (tabela + okładka), mignięcie przy zmianie tytułu, ślady rastra po zmianie zakładki
Przekaż wynik jako: lista uwag; osobno „czy to nadal ten sam wygląd panelu” (O-2)
```

**Gate:** testy, bramki, H3.

#### Faza 10 — dokumentacja i zamknięcie

Aktualizacja `AGENTS.md` (cli, application, catalog), `docs/README.md`, `docs/ideas.md`. Niezależne review (inny model niż autor) przed PR.

## Strategia dowodu i testy

Zasady testów: marker `pytest.mark.unit` na poziomie modułu (wzorzec `test_anime_view.py:30`); sieć tylko z `network`; zero opisowych
komentarzy i docstringów w testach (hook `check_test_comments.py`); opis scenariusza wyłącznie w nazwie testu; kontrakty, nie szczegóły implementacji.

| Plik | Marker | Testy (nazwy) |
|---|---|---|
| `tests/cli/test_library_titles.py` | `unit` | `test_sets_of_one_series_group_into_one_title`, `test_slime_season_four_spellings_stay_separate_without_a_key`, `test_manual_file_is_never_marked_as_key`, `test_unparsed_name_goes_to_the_unrecognized_row`, `test_hidden_and_deleting_sets_leave_the_title`, `test_title_with_problem_sets_counts_them`, `test_titles_sort_naturally_with_unrecognized_last`, `test_filter_narrows_titles_by_normalized_text` |
| `tests/cli/test_library_titles.py` | `unit` | `test_enter_opens_the_title_and_escape_returns_with_the_cursor`, `test_crumb_click_returns_to_the_list`, `test_tab_switch_clears_marks_and_title`, `test_stale_title_result_does_not_overwrite_newer_context` |
| `tests/cli/test_library_columns.py` | `unit` | `test_title_list_fits_at_50_80_120_columns`, `test_episode_view_keeps_number_title_air_and_state_columns`, `test_missing_episode_data_shows_a_dash` |
| `tests/cli/test_library_actions.py` | `unit` | `test_space_marks_and_a_marks_all_episodes`, `test_delete_acts_on_marks_else_on_cursor`, `test_delete_of_several_asks_a_question`, `test_delete_of_one_asks_nothing`, `test_refused_set_returns_while_others_go_on`, `test_several_deletes_use_one_worker_session_at_a_time`, `test_title_delete_covers_every_set_of_the_row` |
| `tests/cli/test_panel_keys.py` | `unit` | rozszerzenie istniejących testów o nowe klawisze (`Space`, `A`, `/`) i `_DESCRIPTIONS` |
| `tests/application/test_library_titles.py` | `unit` | `test_downloaded_set_carries_the_catalogue_id_and_key_source`, `test_manual_set_carries_name_source`, `test_old_snapshot_without_new_fields_decodes`, `test_second_undo_restores_the_previous_deletion`, `test_undo_with_nothing_left_refuses`, `test_episode_info_refuses_without_a_session`, `test_episode_info_returns_dashes_when_the_catalogue_fails` |
| `tests/application/test_library_titles.py` | `unit` | (faza 5) `test_single_exact_alias_with_matching_season_is_recognized`, `test_ambiguous_candidates_stay_by_name`, `test_wrong_season_stays_by_name`, `test_rate_limited_search_stays_by_name`, `test_each_title_is_searched_once` |
| `tests/services/catalog/test_posters.py` | `unit` | `test_cover_query_reads_large_url`, `test_missing_cover_is_skipped`, `test_foreign_host_is_refused`, `test_plain_http_is_refused`, `test_oversized_file_is_refused`, `test_broken_image_is_refused`, `test_write_is_atomic`, `test_file_name_comes_only_from_the_id` |
| `tests/cli/test_library_covers.py` | `unit` | `test_slot_hidden_without_sixel`, `test_slot_hidden_when_terminal_too_small`, `test_screen_equals_the_plain_layout_when_slot_is_hidden`, `test_missing_poster_leaves_slot_empty`, `test_render_does_no_io`, `test_same_position_redraw_skips_screen_clear`, `test_mascot_frames_unchanged` |

### Regresje obowiązkowe

Całe `tests/cli` (w tym `test_interactive_mouse.py`, `test_interactive_hover.py`, `test_panel_frame.py`, `test_anime_view.py`,
`test_subscriptions_panel.py`) oraz testy ownera dotykające `deletion_*`.

### Human acceptance

H1 (wygląd tytułów), H2 (usuwanie i Ctrl+Z na kopiach), H3 (okładki), H4 (R: właściciel ocenia całość na własnej Bibliotece i
potwierdza, że wygląd panelu się nie zmienił; PASS = „to nadal ten sam panel”).

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Eskalacja |
|---|---|---|---|
| Slot obrazu nie mieści się przy typowej szerokości | H3: obraz ucięty lub tabela za wąska | podnieść próg szerokości, zmniejszyć `COVER_FRAME_ROWS` | zmiana układu → decyzja właściciela |
| Mignięcie ekranu przy zmianie okładki | H3 | rysować bez `reset`, tylko nadpisanie komórek (jak `_draw_native_mascot`) | brak rozwiązania → okładki do O-2 „nie” |
| CDN zwraca 429 lub blokuje | faza 0/7: statusy | sekwencyjnie, dłuższy odstęp, mniej tytułów naraz | AniList e-mail (O-10) |
| Źle rozpoznany plik ręczny | test kryterium, H2 | zaostrzyć kryterium; domyślnie `z nazwy` | zmiana definicji pewności → właściciel |
| Wielopoziomowe Ctrl+Z niezgodne z oczekiwaniem | H2 | wariant „paczka” (`batch_id`) | zmiana schematu `PendingDeletion` → przeplanowanie |
| Tytuł odcinka z ani.zip pusty dla starszych serii | faza 4 | `—` | issue #58 (TVmaze) poza zakresem |
| Stary rezydent nie zna nowych pól/komend | panel zgłasza odmowę | restart rezydenta; pola opcjonalne | |

## Lokalna adaptacja

Nazwy helperów i testów, dokładne ścieżki po niesemantycznym przeniesieniu, teksty polskie (poza „Nie rozpoznano” i słownictwem z
`ideas.md`) po H1, stałe geometrii slotu w granicach z planu, miejsce nowych funkcji w istniejących modułach.

## Materialna zmiana (zatrzymaj i przeplanuj)

Zmiana schematu trwałego stanu (`WatchState`, `PendingDeletion`), druga ścieżka renderu obrazu (półbloki), drugi slot obrazu w jednej
ramce, nowa zależność, zmiana wyglądu poza slotem, merge zakładek (O-1 inne niż rekomendacja), przeniesienie pobierania okładek do
panelu, rozszerzenie zakresu na ekran Anime.

## Dodatkowi wykonawcy

| Jednostka | Cel | Write scope | Wynik | Owner integracji |
|---|---|---|---|---|
| Autor części I (jeden, sprzężone: owner + panel) | fazy 0–4 | pliki z mapy części I | commity 1–4, raport z dowodami | orkiestrator |
| Recenzent części I (inny model niż autor, np. Sonnet po poprawce lub inna rodzina) | review wg skilla `review` | brak (read-only) | `reviews/round-N.md` | orkiestrator |
| Autor części II (osobna świeża instancja) | fazy 6–10 | pliki z mapy części II | commity 5–8 | orkiestrator |
| Recenzent części II | j.w. | brak | raport | orkiestrator |

Brief każdego wykonawcy zgodny z `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`, zaczyna się od polecenia przeczytania skilli
`simple` i `coding` oraz `python.md`; dokumenty w `docs/work/` po polsku. Review UI jest lekkie (autor + jeden recenzent); pełna pętla tylko
dla usuwania i danych (zgodnie z preferencją właściciela).

## Definition of Done

- [ ] Wymagania F-1…F-21 spełnione lub świadomie odłożone decyzją właściciela.
- [ ] Bramki repo zielone na `anishift/ tests/`.
- [ ] Zakazy z specyfikacji zachowane (wygląd, dysk płaski, brak cichego przypisania, brak sieci w renderze).
- [ ] H1…H4 wykonane; wyniki w `outcomes/`.
- [ ] `AGENTS.md` i `docs/` zaktualizowane; niezależne review bez otwartych blockerów.

## Kontrakt wyniku wykonania

```text
status
finalny rezultat
zmienione elementy
konkretne dowody (komendy i wyniki)
human feedback (H1-H4)
lokalne odchylenia
materialne odkrycia
znane ograniczenia
stan repo / commity
rekomendowany następny krok
```
