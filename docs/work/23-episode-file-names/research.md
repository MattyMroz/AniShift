---
kind: research
status: done
baseline: 1f76e30 (origin/main)
created: 2026-11-26
---

# Research: skąd biorą się nazwy plików w `ready/`

Pytanie: gdzie powstaje nazwa zestawu odcinka, co ją trzyma w stanie rezydenta i co trzeba zmienić, żeby każdy pobrany odcinek miał nazwę `<seria> - SxxEyy - <tytuł odcinka>`. Specyfikacja: `specification.md`. Plan: `plan.md`.

Ścieżki względem korzenia repo, linie wg `1f76e30`. Liczby z danych właściciela odczytane 2026-11-26 tylko do odczytu (`config/watch/state.json`, `workspace/ready/` w głównym checkoucie).

## 1. Wniosek

- Nazwę zestawu wybiera jedno miejsce: rezerwacja nazw przy publikacji zestawu ze stagingu do korzenia workspace. Rdzeń to dziś stem pliku wideo z torrenta (`automation.py:7008` `_reserve_publication` → `automation.py:9176` `_published_files` → `transfers.py:472` `flat_names`).
- Wszystko dalej dziedziczy ten rdzeń: Auto liczy `group_id` ze stemu, produkty (`.pl.ass`, `.eac3` …) dostają stem źródła (`products.py:113` `product_path`), przeniesienie do `ready/` zachowuje stem (`ready.py:179` `ReadyStore.prepare`), regeneracja w `ready/` pisze obok źródła.
- Zmiana rdzenia w tym jednym miejscu daje nową nazwę całemu zestawowi bez dotykania produktów, Auto, relokacji i Biblioteki.
- Tożsamość zestawu w Bibliotece (`ReadyGroup.set_id`) i wiązanie z odcinkiem (`EpisodeAssignment.group_id`) nie zależą od nazwy w `ready/`. Od nazwy zależy tylko `ReadyGroup.group_id` i ślady przebiegu (potwierdzenia produktów, markery, zlecenia, `notified`, dzienniki runów). Produkt już umie je przepisać przy zmianie nazwy (`ReadyMove.apply`, `RunJournal.relocate`), więc jednorazowy skrypt ma gotowy, sprawdzony mechanizm. Warunek stopu z briefu nie zachodzi.

## 2. Przepływ nazwy pobranego odcinka

```text
EpisodeAssignment.files (ścieżki z torrenta, indeksy)
-> _publish_episode (wątek puli transferów, automation.py:6968)
   -> _passed_check: kontrola pobrania subskrypcji (media probe)
   -> _reserve_publication (wątek ownera, automation.py:7008)
      -> _reserved_names (automation.py:6305): stemy w korzeniu + rezerwacje transferów + ready_groups + pending_deletions
      -> _published_files -> flat_names: rdzeń = stem wideo, sidecar o tym samym stemie dzieli rdzeń, kolizja -> " [2]" (_free_core, transfers.py:496)
      -> EpisodePublication zapisane w stanie (log "Episode set names reserved", automation.py:7036)
   -> kopie prywatne, publish_set (acquisition_staging.py:144): dowiązania do korzenia
   -> _settle_publication: handed_off (log "Episode set published and handed to Auto", automation.py:7254)
-> discovery: group_id = create_group_id(".", stem) (artifacts.py:187); _published_group (automation.py:9130) zapisuje go w EpisodeAssignment.group_id
-> Auto: produkty product_path(katalog, stem, kind) (products.py:113)
-> _prepare_ready -> ReadyStore.prepare: destination_stem = stem grupy (+ " [n]" przy kolizji), ReadyMove w config/watch/relocations/
-> _relocated_state (automation.py:7715): ReadyMove.apply + RunJournal.relocate + ReadyGroup(set_id = group_id z korzenia, group_id = create_group_id("ready", stem))
```

Fakty:

- `_publish_episode` biegnie na wątku puli transferów (`automation.py:6355-6387`), tam gdzie już działa sonda mediów. Odczyt katalogu w tym miejscu nie blokuje ownera.
- `video_sidecars` (`transfers.py:443`) wiąże z wideo tylko pliki z tego samego katalogu i o identycznym stemie, więc wszystkie pliki przypisania mają jeden stem i jeden rdzeń.
- Po sprzątnięciu transferu `_retained_episode` (`automation.py:9152`) zostawia w przypisaniu tylko `group_id` i `video_path` (ścieżkę w stagingu); `EpisodePublication` i `choice.target` znikają (w stanie `target: {}`).

## 3. Miejsca, które trzymają nazwy lub ścieżki

| Miejsce | Co trzyma | Plik:linia | Zależy od nazwy w `ready/` |
| --- | --- | --- | --- |
| `EpisodePublication.files[].name` | zarezerwowane płaskie nazwy | `control.py:392`, `:413` | nie (tylko przed sprzątnięciem, w korzeniu) |
| `EpisodeAssignment.group_id`, `video_path` | `group_id` w korzeniu = `ReadyGroup.set_id`; ścieżka w stagingu | `control.py:436` | nie |
| `ReadyGroup` | `set_id`, `group_id`, `stem`, `source_stem`, `sources`, `products`, `main_result`, `pending_sources` | `control.py:734` | `group_id`, `stem`, `sources`, `products`, `main_result` tak; `set_id`, `source_*` nie |
| `ProductConfirmation` (`state.products`) | `group_id`, `path` | `control.py:720` | tak |
| `markers` | `group_id`, `fingerprint` (nazwy) | `control.py:289` | tak |
| `requests` | `group_ids`, `fingerprints` (nazwy), `intents[].group_id` | `control.py:300` | tak |
| `notified` | `(group_id, run, wynik)` | `control.py:939` (`WatchState`) | tak |
| `pending_deletions` | ścieżki plików w Koszu, `set_id` | `control.py:845` | nie dla nazw w `ready/` (pliki już w Koszu) |
| `AcquisitionConfirmation.required_files`, `file_layout` | ścieżki transferu starego typu | `control.py:574` | tylko dla transferu starego typu, który trzyma pliki w `ready/` |
| `config/watch/relocations/*.json` | `ReadyMove` w toku | `ready.py:50` | tak (dziś katalog pusty) |
| `config/watch/runs/*.json` | plan, artefakty, dowody plików | `recovery.py:170` | tak dla zakończonych runów grupy |
| `config/watch/history.jsonl` | `material_id` (= `set_id`), `name` | `history.py` | tylko tekst `name`; Historia jest nieautorytatywna |
| `decisions.jsonl` | bez nazw i ścieżek | AGENTS.md | nie |
| Biblioteka | `set_id`, pliki z `ReadyGroup` i discovery | `library.py:270` `project_library` | przez `ReadyGroup` |
| Odtwarzanie, F, Historia Enter | `library_open` po `set_id` | `cli/resident.py:132`, `cli/interactive/state.py:1724`, `automation.py:2335-2378` | nie |
| Kosz / Ctrl+Z | `PendingDeletion.files`, przywracanie do starych ścieżek | `control.py:845` | nie dla zestawów obecnych na dysku |

Mechanizm zmiany nazwy, który już istnieje:

- `ReadyMove.apply` (`ready.py:89`) przepisuje `markers`, `products`, `requests` (zakończone sukcesem albo wskazane), `acquisitions` (ścieżki transferu starego typu) i `notified` na nowe nazwy i nowy `group_id`.
- `RunJournal.relocate` (`recovery.py:170`) przepisuje dziennik zakończonego runu (grupy, intencje, artefakty, dowody plików) i odmawia przy innej wersji dziennika.
- `ReadyStore.execute` (`ready.py:239`) zmienia nazwę wyłącznym dowiązaniem i usunięciem starej nazwy, sprawdza tożsamość pliku i dokańcza przerwaną operację (`_move_file`, `ready.py:283`).
- `_ready_group` (`automation.py:7733`) buduje `ReadyGroup` z `set_id = move.group_id`. To pasuje do przeniesienia z korzenia, ale nie do zmiany nazwy w `ready/`: dałoby `set_id` równy staremu `group_id` w `ready/` i zdublowało rekord. Skrypt musi więc sam podmienić rekord, zachowując `set_id`. Podobnie `ReadyStore.prepare` odmawia grupy już leżącej w `ready/` (`in_ready`), a zapis `ReadyMove` do `config/watch/relocations/` uruchomiłby `_ready_group` przy starcie rezydenta.

## 4. Skąd wziąć tytuł serii, sezon, odcinek i tytuł odcinka

| Fakt | Źródło dziś | Plik:linia | Uwagi |
| --- | --- | --- | --- |
| Tytuł serii | `FranchiseEntry.english or romaji` z `AcquisitionService.franchise` (pamięć serwisu) | `automation.py:9533` `_series_title`, `acquisition.py:849` | ta sama reguła daje `SubscriptionRecord.title` (`automation.py:9553`); Biblioteka obcina sezon, część i rok przez `series_title` (`library.py:136`) |
| Sezon i odcinek TVDB | `ListedEpisode.season`, `.episode` z ani.zip | `episode_selection.py:286`, `acquisition.py:868` `episodes` | cel H1 (`choice.target["season"/"episode"]`, `episode_selection.py:455`) ma kopię z chwili przyjęcia, do sprzątnięcia |
| Tytuł odcinka | `ListedEpisode.title`: ani.zip `en`, potem `x-jat` | `services/catalog/anizip.py:127` | druga kopia tej reguły: `episode_selection.py:808` `_episode_title` (zamienia też `` ` `` na `'`) |
| Sezon w Bibliotece | `season_hint(tytuł)`, potem sezon z zapisanego mapowania subskrypcji; odcinek = numer lokalny | `library.py:245` `_series_season`, `:222` `name_series` | inna reguła niż TVDB z ani.zip; dziś 0 rozjazdów na 60 zestawach z mapowaniem, ale rozjedzie się przy split-cour |

Workstream 19 (`.worktrees/tvmaze-episode-titles`, `docs/work/19-tvmaze-episode-titles/`, baseline `4365a51`, plan sprzed decyzji z 2026-11-25) dziś:

- uzupełnia tylko `ListedEpisode.title == None` i nie zastępuje romaji (`x-jat`) angielskim tytułem TVmaze (D3);
- kieruje TVmaze tylko przez `AcquisitionService.episodes()` (wymaganie 8), z cache w pamięci rezydenta (wymaganie 7, 9).

Decyzja właściciela z 2026-11-25 (angielski ani.zip → TVmaze → romaji → brak) wymaga więc zmiany 19: rozdzielenia `en` i `x-jat` oraz jednej reguły tytułu zamiast dwóch kopii. Ten workstream tylko czyta wynik: `ListedEpisode.title` zwracany przez `AcquisitionService.episodes(anilist_id)`. Wymaganie 8 workstreamu 19 to dopuszcza, bo publikacja woła tę samą funkcję co panel, raz na opublikowany odcinek.

## 5. Ścieżki bez klucza odcinka

- Pliki wrzucone ręcznie do workspace nie mają `EpisodeKey`; ich nazwa to nazwa użytkownika.
- Pobranie całego wydania (`download`, `automation.py:5001`, i `reacquire` zlecenia starego typu, `automation.py:8395`) nazywa pliki w kliencie (`_reserve_names`, `automation.py:6483`, przez `flat_layout`, `transfers.py:467`). Ma tylko `LegacyScope` (wpis AniList i numer z kontekstu wydania), nie klucz odcinka. `ResidentSession.download` (`cli/resident.py:225`) nie ma wywołania w `anishift/cli` (sprawdzone `grep`); w stanie jest jedno takie zlecenie (Overgeared S01E01, pliki już usunięte).

## 6. Pułapki znalezione przy researchu

- Znaki: `series_directory_name` (`acquisition.py:589`) usuwa `<>:"/\|?*` i znaki sterujące, obcina kropki i spacje na końcu i omija nazwy urządzeń (`_RESERVED_NAMES`, `acquisition.py:162`). Usunięcie `:` skleja wyrazy (`Re:Zero` → `ReZero`). Tytuły ani.zip mają `` ` `` zamiast apostrofu (`Fire Rat`s Cloak`).
- Klasyfikacja po sufiksie: rdzeń kończący się np. `.cover` przed `.mp4` dałby produkt `COVER_MP4` zamiast źródła (`products.py:130` `classify_product`, `discovery.classify_artifact`). Nazwa musi przechodzić test: `classify_artifact(rdzeń + sufiks wideo)` daje źródło główne o stemie równym rdzeniowi.
- Rezerwacja: `_reserved_names` liczy stemy wszystkich rekordów `ready_groups`, także tych, których pliki dawno usunięto (224 z 299 rekordów nie ma plików). Przy nazwach z wydania kolizje były rzadkie; przy nazwie kanonicznej każde ponowne pobranie usuniętego odcinka dostanie ` [2]`. W stanie 9 z 224 kluczy odcinków przekazano do Auto więcej niż raz.
- `reserved_stem` (`transfers.py:361`) bierze `Path.stem`, więc dla produktu `X.pl.ass` rezerwuje `x.pl`, nie `x`. Nie szkodzi nazwie źródła (rezerwuje też `x` z wideo), ale reguła rdzenia nie jest jedna.
- Długość: ścieżka `workspace/ready` właściciela ma 60 znaków, najdłuższy sufiks produktu `.displayed.pl.ass` 17, ordinal ` [n]` 4. Dzisiejsze nazwy mają do 154 znaków i działają.
- Testy kontraktu nazwy: `tests/application/test_selective_publication.py:353` (`Neko to Ryuu - 03 [2]`) i sąsiednie zakładają nazwę z torrenta; zmienią się razem z kontraktem.
- Workstream 18 (`.worktrees/library-titles-covers`) zmienia `name_series` w `library.py`; nazwy kanoniczne ułatwiają mu etykiety „z nazwy”, ale oba diffy dotkną tego samego pliku.

## 7. Liczby z danych właściciela (2026-11-26, tylko odczyt)

| Co | Liczba |
| --- | --- |
| Plików płasko w `ready/` (plus podkatalog `Nowy folder/`, poza zakresem) | 283 |
| Rekordów `ready_groups` / z plikami na dysku | 299 / 75 |
| Zestawów z kluczem odcinka (do zmiany nazwy) / plików w nich | 68 / 255 |
| … z subskrypcji / z ręcznego zamówienia | 56 / 12 |
| … seriali | 11 |
| Zestawów bez klucza (zostają) / plików | 7 / 27 (`Seihantai na Kimi to Boku 2nd Season` 07-12 Erai-raws, `Sparks of Tomorrow` S01E11) |
| Pliki bez rekordu (zostają) | 1 (`Avatar.Seven.Havens.S01E03….srt`) |
| Powtórzony klucz odcinka wśród zestawów na dysku | 0 |
| Zestawy z mapowaniem subskrypcji: tytuł `en` / tylko `x-jat` / brak subskrypcji | 54 / 6 / 8 (Clevatess S2 06-13, tytuł serii wymaga AniList) |
| Najdłuższy rdzeń wg dzisiejszych tytułów | 153 znaki (`The Iceblade Sorcerer Shall Rule the World - S02E01 - The Boy Who Is …`) |
| Rozjazd numeru lokalnego i odcinka TVDB | 0 |
| Do przepisania dla tych 68 zestawów: potwierdzeń produktów / markerów / zleceń (wszystkie `succeeded`) / `notified` / dzienników runów (wersja 2) | 187 / 20 / 68 / 88 / 68 |
| `pending_deletions` (pliki w Koszu, nietknięte) / relokacje w toku / zlecenia w toku | 5 / 0 / 0 |

Przykłady nowych nazw wyliczone z dzisiejszych danych (przed TVmaze):

```text
Blue Box - S02E07 - I Need to Tell You Something.mkv
The Apothecary Diaries - S03E02 - Fire Rat's Cloak.pl.ass
Overgeared - S01E09 - Guild no Nakama-tachi.eac3
```
