---
kind: plan
status: draft
baseline: 1f76e30 (origin/main)
created: 2026-11-26
---

# Plan: wspólne nazwy gotowych odcinków

Kontrakt: `specification.md` (wymagania 1-17, rekomendacje O-1…O-12). Dowody: `research.md`. Plan zakłada rekomendacje O-1…O-12; inna decyzja właściciela zmienia wskazane fazy.

## Cel

Zestaw pobrany jako odcinek katalogu dostaje przy publikacji rdzeń `<seria> - SxxEyy[ - <tytuł odcinka>]`, a 68 istniejących zestawów w `ready/` właściciela przechodzi na tę nazwę jednorazowym skryptem.

## Warunki końcowe

- [ ] Nowy odcinek (subskrypcja i ręczne zamówienie) trafia do korzenia i do `ready/` pod rdzeniem z reguły, z kompletem produktów.
- [ ] W kodzie produktu nie ma ścieżki, która nadaje zestawowi z kluczem odcinka nazwę z torrenta.
- [ ] Skrypt przemianował zestawy z kluczem w `ready/`, stan nie zawiera ich starych nazw, Biblioteka, odtwarzanie, Del i Ctrl+Z działają; skrypt usunięty z repo.
- [ ] Bramki z `AGENTS.md` zielone, przegląd krzyżowy bez otwartych znalezisk, odbiór właściciela.

## Nie-cel

Tytuły z TVmaze i rozdzielenie `en`/`x-jat` (workstream 19), widok tytułów w Bibliotece (workstream 18), nazwy plików bez klucza odcinka.

## Zależności i kolejność

- Workstream 19 musi być scalony przed fazą 2: ten plan czyta tylko `ListedEpisode.title` z `AcquisitionService.episodes(anilist_id)` i zakłada, że 19 już daje tam kolejność angielski ani.zip → TVmaze → romaji → brak, z jedną regułą tytułu zamiast dwóch kopii (`anizip._title`, `episode_selection._episode_title`). Plan 19 z 2026-10-25 tego jeszcze nie robi (D3, wymaganie 1); jego aktualizacja należy do 19.
- Migrację (faza 5) robi się po scaleniu tej zmiany i 19 do `main`, z głównego checkoutu, żeby nazwy z skryptu były identyczne z nazwami produktu.
- Workstream 18 zmienia `name_series` (`library.py:222`); faza 3 dotyka tej samej funkcji. Kto scala drugi, ten rebazuje.

## Target design

### Odpowiedzialności

- `anishift/application/products.py`: czysta reguła nazwy. `episode_stem(series, season, episode, title) -> str` i `safe_name_part(text) -> str` (reguła O-3), limit O-4, warunek klasyfikacji (wymaganie 7 przez test i przez sprawdzenie w funkcji publikacji). Bez I/O i bez importu `services`.
- `anishift/application/library.py`: `episode_numbering(listed, title, local, *, film) -> tuple[int, int] | None` (reguła O-5), używana przez nazwę i przez `name_series` (O-7). `series_title` bez zmian.
- `anishift/application/acquisition.py`: `AcquisitionService.episode_name(anilist_id, number) -> EpisodeName` czyta `franchise()` i `episodes()` (pamięć serwisu, ta sama co panel) i zwraca fakty: tytuł serii (`english or romaji`), wpis odcinka, czy film. `series_directory_name` używa `safe_name_part`.
- `anishift/application/automation.py`: `_publish_episode` (pula transferów) bierze fakty z `episode_name` w `acquisition.episode_requests()`, z zapasem O-9, składa rdzeń przez `episode_stem` i przekazuje go do `_reserve_publication`; `_published_files` buduje nazwy z rdzenia zamiast stemu torrenta. `_series_title` (Biblioteka) przechodzi na `episode_name` albo na tę samą regułę `english or romaji`, bez trzeciej kopii.
- Skrypt `scripts/tmp/rename_ready_episodes.py`: jednorazowa migracja, używa `AcquisitionService.episode_name`, `episode_stem`, `ReadyMove.apply`, `RunJournal.relocate`, `ReadyStore.execute`, `WatchStateStore`.

### Przepływ

```text
_publish_episode (pula)
-> _passed_check (bez zmian)
-> fakty: AcquisitionService.episode_name(choice.anilist_id, choice.number)
   błąd katalogu -> seria z subskrypcji przypisania, numeracja z choice.target, bez tytułu odcinka
   brak tytułu serii -> brak publikacji w tej rundzie, logger.warning("Episode name waits for the catalogue")
-> rdzeń = episode_stem(...)
-> _reserve_publication(..., core) na ownerze -> _published_files(files, reserved, core)
   nazwy: core + sufiks każdego pliku -> flat_names (kolizja całego zestawu -> " [n]")
-> dalej bez zmian: kopia, publish_set, handed_off, Auto, relokacja do ready/
```

Zarezerwowana `EpisodePublication` zostaje w stanie, więc restart i ponowienie używają zapisanej nazwy (wymaganie 9); `_reserve_publication` nie liczy rdzenia drugi raz, gdy publikacja istnieje.

### Rezerwacja nazw (O-6)

`_reserved_names` (`automation.py:6305`) rezerwuje `stem` i `source_stem` każdego rekordu `ready_groups`, jego `pending_sources`, pliki obecne w korzeniu i w `ready/`, `pending_deletions` i rezerwacje transferów. Rekord bez plików rezerwuje dalej, bo `set_id` jest deterministyczny (`create_group_id(katalog, stem)`): czysta nazwa ponownego pobrania przejęłaby `set_id` starego rekordu.

### Mapa plików

- `anishift/application/products.py` (MODIFY): `episode_stem`, `safe_name_part`, stałe limitu i separatora.
- `anishift/application/library.py` (MODIFY): `episode_numbering`; `name_series` i `_series_season` na nią (O-7).
- `anishift/application/acquisition.py` (MODIFY): `EpisodeName`, `AcquisitionService.episode_name`; `series_directory_name` na `safe_name_part`.
- `anishift/application/automation.py` (MODIFY): `_publish_episode`, `_reserve_publication`, `_published_files`, `_reserved_names`, `_series_title`.
- `anishift/application/AGENTS.md` (MODIFY): jedna linia: rdzeń zestawu odcinka pochodzi wyłącznie z `products.episode_stem`, fakty z `AcquisitionService.episode_name`.
- `README.md` (MODIFY): akapit o `ready/` (linie 114-115) opisuje nową nazwę.
- `tests/application/test_products.py`, `test_library_series.py`, `test_acquisition.py`, `test_selective_publication.py`, `test_automation.py` (MODIFY).
- `scripts/tmp/rename_ready_episodes.py` (CREATE, potem DELETE).
- `docs/work/23-episode-file-names/outcomes/01-episode-file-names.md` (CREATE po odbiorze), `docs/README.md` (MODIFY status).
- READ ONLY: `ready.py`, `recovery.py`, `transfers.py` (`flat_names` zostaje bez zmian, dostaje gotowe nazwy).

### Edge cases

- Dwa wydania jednego odcinka obecne naraz (BD i WEB, v2): drugie ` [2]`; test.
- Sidecar `.ass`/`.srt` wydania: ten sam rdzeń; test.
- Tytuł z `:`, `/`, `?`, `` ` ``, kropką na końcu, nazwą urządzenia: reguła O-3; test parametryczny.
- Tytuł odcinka kończący się sufiksem produktu (np. `….cover` przed `.mp4`): rdzeń bez tytułu odcinka; test.
- Rdzeń ponad limit: skrócony tytuł odcinka, potem seria; test.
- Film (`EpisodeKey(id, 1)`, format `MOVIE`), sezon 0, brak numeracji TVDB: O-5; test.
- AniList lub ani.zip padają przy publikacji: O-9; test z atrapą rzucającą `TitleCatalogError` (kształt błędu z istniejących testów `test_acquisition.py`, nie wymyślony).
- Restart między rezerwacją a kopią: nazwa z zapisanej publikacji; istniejący parametr `boundary` w `test_selective_publication.py:572` rozszerzony o asercję nazwy.

## Plan wykonania

### Faza 0 - Preflight

1. Właściciel rozstrzyga O-1…O-12; rozbieżność z rekomendacją aktualizuje `specification.md` przed kodem.
2. Workstream 19 scalony; sprawdź w `main`, że `AcquisitionService.episodes()` zwraca tytuł według kolejności z decyzji i że jest jedna reguła tytułu.
3. Gałąź `feat/episode-file-names` od świeżego `origin/main`; `uv sync` raz w worktree, potem `uv run --no-sync`. Nigdy `--active`.
4. Baseline: `uv run --no-sync pytest -n 6 tests/application/test_selective_publication.py tests/application/test_products.py tests/application/test_library_series.py`; zapisz znane porażki.
5. Sprawdzenie historii rezerwacji z sekcji O-6.

Gate: decyzje zapisane, 19 w `main`, baseline znany.

### Faza 1 - Reguła nazwy

1. `safe_name_part` i `episode_stem` w `products.py`; `series_directory_name` przechodzi na `safe_name_part` (ta sama zmiana zachowania dla katalogu serii, test `test_series_directory_name_is_safe_on_windows` aktualizowany).
2. `episode_numbering` w `library.py`.
3. Testy `@pytest.mark.unit`: parametryczne przypadki z sekcji Edge cases; warunek klasyfikacji `classify_artifact(Path(core + ".mkv"), route)` daje źródło główne ze stemem `core` dla każdego przypadku.

Kontrola: `uv run --no-sync pytest -n 6 tests/application/test_products.py tests/application/test_library_series.py tests/application/test_acquisition.py`.

Gate: testy zielone; commit `feat(application): add the shared episode file name rule`.

### Faza 2 - Nazwa przy publikacji

1. `EpisodeName` i `AcquisitionService.episode_name`; test `@pytest.mark.unit` na atrapach katalogu w kształcie z istniejących testów.
2. `_publish_episode` → fakty i rdzeń na puli, zapas O-9, `_reserve_publication(…, core)`, `_published_files(files, reserved, core)`; stem torrenta nie wchodzi już do nazwy zestawu z kluczem.
3. `_reserved_names` według O-6.
4. `_series_title` na tę samą regułę tytułu serii.
5. Testy `@pytest.mark.integration` w `test_selective_publication.py`: nazwa z katalogu z sidecarem; kolizja ` [2]`; katalog niedostępny z subskrypcją (nazwa bez tytułu odcinka); zamówienie ręczne bez katalogu (brak publikacji w rundzie, publikacja po powrocie katalogu); restart po rezerwacji. Istniejące testy, które zakładają nazwę z torrenta (`test_a_name_taken_before_publication_moves_the_whole_set_to_one_free_core` i sąsiednie), przechodzą na nowy kontrakt; każdy taki test dostaje powód w opisie PR (sygnał `test-weakening`).

Kontrola: `uv run --no-sync pytest -n 6 tests/application/test_selective_publication.py tests/application/test_automation.py tests/application/test_acquisition.py`.

Gate: testy zielone; commit `feat(application): name published episode sets after the catalogue`.

### Faza 3 - Numeracja w Bibliotece (O-7)

1. `name_series` liczy sezon i odcinek przez `episode_numbering` z zapisanego mapowania subskrypcji.
2. Test `@pytest.mark.unit` w `test_library_series.py`: split-cour daje ten sam `SxxEyy` co nazwa pliku.

Gate: testy zielone; commit `fix(application): number Library episodes like their file names`. Przy decyzji „nie” w O-7 faza znika.

### Faza 4 - Bramki, przegląd, próba właściciela

1. Bramki z `AGENTS.md`: `uv run --no-sync ruff check anishift/ tests/`, `uv run --no-sync ruff format --check anishift/ tests/`, `uv run --no-sync mypy anishift/ tests/`, `uv run --no-sync pytest -n 6`.
2. Przegląd krzyżowy świeżym modelem innej rodziny niż autor, pytanie: „którą drogą przejdzie zestaw z kluczem, która nie użyje `episode_stem`”. Poprawki w commitach tematu.
3. Dokumentacja: `README.md`, `anishift/application/AGENTS.md`.
4. Punkt kontrolny właściciela (bez push i PR przed jego OK):

```text
Uruchom: rezydent z gałęzi feat/episode-file-names (właściciel zamyka swój rezydent, uruchamia z worktree)
Zrób: poczekaj na odcinek z subskrypcji albo zamów jeden odcinek w zakładce Anime (D)
Oczekiwany rezultat: w korzeniu workspace i potem w ready/ pliki "<seria> - SxxEyy - <tytuł>.mkv", ".pl.ass", ".displayed.pl.ass", ".eac3"; Biblioteka pokazuje odcinek, Enter odtwarza
Zwróć uwagę na: tytuł serii (angielski, bez "Season 2"), numer sezonu, znaki w tytule odcinka
Przekaż wynik jako: OK albo nazwa pliku, która się nie podoba
```

Gate: OK właściciela; dopiero wtedy push, PR i scalenie według `ship` na słowo właściciela.

### Faza 5 - Migracja istniejących plików

1. Skrypt `scripts/tmp/rename_ready_episodes.py` (wzór: usunięty skrypt `temp`→`tmp`, `git show 9366ca8`): blokada `ProcessLock` na `RESIDENT_LOCK_FILE_NAME` dowodzi zamkniętego rezydenta; odmowa przy relokacjach w `config/watch/relocations/`, zleceniach w toku, rezerwacjach, niezgodnej tożsamości pliku z rekordem, zajętej nazwie docelowej i innej wersji stanu albo dziennika.
2. Tryby:
   - `plan` (domyślny): liczy rdzenie przez `AcquisitionService.episode_name` i `episode_stem` (sieć: AniList, ani.zip, TVmaze), zapisuje `config/watch/episode-names.json` (dla każdego zestawu: `set_id`, stary i nowy `group_id`, pary stara i nowa nazwa z rozmiarem, `mtime_ns`, urządzeniem i i-node), wypisuje liczby i nazwy;
   - `apply`: wykonuje dokładnie zapisaną listę: kopia `state.json.episode-names.bak` i kopie dotkniętych dzienników `*.episode-names.bak`, `ReadyStore.execute` dla każdego zestawu, `RunJournal.relocate` dla zleceń zestawu, `ReadyMove.apply` ze zbiorem przepisanych zleceń, podmiana `ReadyGroup` po `set_id` (nowe `group_id`, `stem`, `sources`, `products`, `main_result`; reszta bez zmian), jeden zapis przez `WatchStateStore`; ponowne `apply` po przerwaniu dokańcza (`_move_file` znosi istniejący cel);
   - `undo`: ta sama lista w drugą stronę;
   - `check`: każdy nowy plik istnieje z zapisaną tożsamością, żaden stary nie istnieje, stan nie zawiera starych nazw ani starych `group_id` tych zestawów, `WatchStateStore` czyta stan bez błędu.
3. Commit `build(repo): add a one-off script that renames ready episodes` (scope `repo`, skrypt poza pakietem).
4. Punkt kontrolny właściciela:

```text
Uruchom: w głównym checkoucie po scaleniu: uv run --no-sync python scripts/tmp/rename_ready_episodes.py plan
Zrób: przejrzyj listę (oczekiwane ok. 68 zestawów i 255 plików według stanu z 2026-11-26; Clevatess wymaga AniList)
Potem: zamknij rezydent; ... apply; ... check
Oczekiwany rezultat: check bez zastrzeżeń; po starcie rezydenta Biblioteka ma te same zestawy pod nowymi nazwami, Enter odtwarza, F otwiera folder
Zwróć uwagę na: zestawy bez klucza (7) i plik bez rekordu (1) zostają bez zmian
Przekaż wynik jako: OK albo nazwa zestawu z problemem (wtedy: zamknij rezydent, undo)
```

5. Po OK: commit `build(repo): remove the one-off ready episode rename script after it ran`; właściciel usuwa `config/watch/episode-names.json` i kopie `.episode-names.bak`, gdy uzna.

Gate: OK właściciela po migracji; `outcomes/01-episode-file-names.md` i status w `docs/README.md`.

## Strategia dowodu

- Reguła nazwy (wymagania 1-7): testy unit parametryczne, także warunek klasyfikacji.
- Publikacja (8-12): testy integracyjne ownera na prawdziwym przepływie publikacji z atrapą klienta i katalogu, jak dziś w `test_selective_publication.py`.
- Brak drugiej reguły: przegląd krzyżowy i `git grep` po `Path(…).stem` w ścieżce publikacji.
- Migracja (13-17): tryb `plan` na prawdziwych danych przed `apply`; `check` po; odbiór właściciela w Bibliotece.

## Ryzyka

- Workstream 19 nie dostarczy kolejności z decyzji przed fazą 2: tytuły odcinków będą `en` albo `x-jat` z ani.zip. Reakcja: faza 2 czeka; nie dopisuj reguły tytułu tutaj.
- Katalog niedostępny w chwili publikacji zamówienia ręcznego po restarcie: odcinek czeka (O-9). Rozpoznanie: ostrzeżenie w logu przy każdej rundzie. Eskalacja: gdy właściciel uzna czekanie za zawieszenie, wraca decyzja O-9.
- Zmiana `_reserved_names` (O-6) odsłoni nazwę, którą ktoś jeszcze chroni. Reakcja: faza 0 sprawdza historię; test kolizji z `pending_deletions`.
- Skrypt przerwany między plikami a zapisem stanu: pliki pod nowymi nazwami bez rekordu. Reakcja: ponowne `apply` z tej samej listy albo `undo`; rezydent nie startuje, dopóki `check` nie przejdzie.
- Rezydent właściciela działa z checkoutu: każda zmiana plików i stanu tylko po jego zamknięciu, na jego słowo.

## Zatrzymaj się i wróć po decyzję, gdy

- nazwa musiałaby zależeć od czegoś innego niż cztery fakty z wymagania 1;
- przypisanie nie ma `choice.anilist_id` i numeru albo zestaw ma więcej niż jeden stem;
- `RunJournal.relocate` albo `ReadyMove.apply` nie pokrywa miejsca stanu, które trzyma nazwę;
- workstream 19 zmienia kontrakt `ListedEpisode.title` albo `AcquisitionService.episodes`.

## Kontrakt wyniku

Status, finalne nazwy z próby właściciela, zmienione pliki, wyniki bramek z liczbami, odchylenia od rekomendacji O-x, liczby z `plan` i `check` migracji, SHA commitów, następny krok.
