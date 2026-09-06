# application

Czysta warstwa produktu i use case'ów współdzielona przez CLI i testy.

## Kierunek zależności

- `artifacts.py`, `intents.py`, `planning.py`, `selection.py` i `planner.py` nie importują I/O,
  `anishift.services`, `anishift.config` ani CLI.
- Kontrolowane I/O należy do `discovery.py`, `inspection.py`, `publisher.py`,
  `sessions.py`, `acquisition.py` (katalog wydań, katalog tytułów i wysyłka do klienta torrent
  przez wstrzyknięte protokoły `TorrentSource`/`TitleCatalog`/`TorrentClient`; typy z
  `services.torrents` i `services.catalog` tylko pod `TYPE_CHECKING`, jedyny import runtime to
  czyste `season_hint`/`strip_season` z `services.torrents.names`), handlerów oraz fasady
  `service.py`; koordynator publikuje zwalidowany staging przez `scheduler_runtime.py`.
  Decyzje produktowe pozostają w plannerze.
- CLI używa publicznej fasady `anishift.application`; nie importuje
  wewnętrznych helperów I/O ani schedulera.
- Oczekiwany konflikt wejścia jest `PlanProblem`. `PlanningError` oznacza uszkodzony
  kontrakt albo graf, nie zwykłą decyzję użytkownika.

## Inwarianty

- Discovery skanuje root workspace rekurencyjnie: pomija `temp/` bezpośrednio pod rootem,
  katalogi i pliki od kropki oraz nie wchodzi w dowiązania symboliczne. ID grupy liczy się
  z katalogu względem roota i stemu, więc `A/01.mkv` i `B/01.mkv` to dwie grupy, a plik
  w root zachowuje dotychczasowe ID. `discovery.py`
- `watch.py` to czyste reguły czuwania (stabilność pliku, `needs_work`, `WatchLedger`);
  `open("r+b")` wykrywa writer bez współdzielenia (Explorer, qBittorrent), nie drugi
  pythonowy uchwyt. Eksport przez fasadę: `SCAN_INTERVAL_S`, `WatchLedger`. `watch.py`
- Numer odcinka widziany przez aplikację to `choice.episode`, nigdy `choice.name.episode`:
  `read_episode` interpretuje nazwę w `SeasonContext` (indeks sezonu, offset odcinków, liczba
  odcinków). Nazwa ze znacznikiem sezonu (`name.season` albo `season_hint(series)`) zachowuje
  numer i dostaje `other_season`, gdy znacznik wskazuje inny sezon; nazwa bez znacznika i z
  numerem powyżej offsetu jest numeracją absolutną (`absolute`), a poniżej offsetu to inny
  sezon. `acquisition.py`
- `catalog_releases` ukrywa wydania poniżej `min_resolution`, dubbingowane oraz te, którym
  indeks nie podał języka napisów; `filtered` liczy odrzucone filtrem odcinków (paczki i numery
  spoza zakresu). Klucz grupy powstaje z serii złożonej do liter, cyfr i spacji, więc
  `Mushoku Tensei: Jobless Reincarnation` i wersja bez dwukropka to jedna grupa — etykietą
  zostaje pierwszy napotkany zapis. `acquisition.py`
- `matches_title` porównuje zbiory `title_forms`: zapis wprost, bez znacznika sezonu i `base_title`
  (bez sezonu i bez podtytułu po `" - "`, `" -"`, `":"` albo `" –"`). Dzięki temu `Solo Leveling`
  Tsundere-Raws trafia w alias `Solo Leveling Season 2 -Arise from the Shadow-`. `acquisition.py`
- `search_title` odpytuje indeks tytułem romaji i angielskim; przy zakresie najwyżej
  `MAX_EPISODE_SPAN` odcinków dokłada zapytania po numerze (`"{base} - 01"`, a przy sezonie > 1
  także `"{base} S02E01"` i numer absolutny), bo RSS oddaje tylko 75 najnowszych trafień i stary
  odcinek inaczej nie wypłynie. Potem `"{seria} {grupa}"` dla maks. `MAX_GROUP_QUERIES` pasujących
  grup wybranych po sumie seedów odcinków wybranego sezonu — nie po dacie, żeby wieloletni
  uploader nie wypadł za nowszymi. Cała operacja mieści się w `MAX_QUERIES` zapytaniach; scalanie
  idzie po `info_hash` casefold, pierwszy wpis wygrywa. `acquisition.py`
- `season_context` liczy sezony, nie wpisy: `PrequelEntry.cour` (tytuł z `Part N`/`Cour N`) podnosi
  offset, ale nie indeks, a kandydat będący cour zostaje w sezonie swojego poprzednika. Bez tego
  Mushoku Tensei III wychodziło jako sezon 5. `acquisition.py`, `services/catalog/anilist.py`
- `Subscription` trzyma `directory` (jeden folder biblioteki niezależny od serii w nazwie
  wydania) i trójkę `season_index`/`episode_offset`/`season_episodes`. Cztery pola są opcjonalne
  przy odczycie, więc pliki sprzed numeracji sezonów wczytują się bez migracji, a
  `SCHEMA_VERSION` zostaje `1`. `subscriptions.py`
- ID grup i odkrytych artefaktów powstają wyłącznie z normalizowanych ścieżek
  względnych. Ręcznie zarejestrowany plik spoza workspace używa znormalizowanej
  ścieżki zewnętrznej wyłącznie jako wejścia stabilnego skrótu; nie używaj `hash()`
  ani losowego UUID.
- `SOURCE` ma `planned_destination == path`, `INTERMEDIATE` nie ma trwałego celu,
  a `DURABLE` otrzymuje `planned_destination` przed wykonaniem.
- `AUTO` nie zawiera ręcznych artifact/track ID. `MANUAL` może wskazać artefakt albo
  embedded track danego rodzaju, nigdy oba jednocześnie.
- `ExecutionPlan.tasks` musi wejść już w porządku zwróconym przez
  `stable_topological_order()`. Porządek jest stabilny względem naturalnie ułożonego
  wejścia, więc niezależne taski grupy `2` nie mogą przeskoczyć za grupę `10` przez
  hash w `task_id`. Każdy produkowany artefakt ma jednego producenta.
- Auto wymagające osadzonego audio i napisów z jednego MKV planuje jeden
  `EXTRACT_TRACKS`. Produkcyjny handler uruchamia jeden istniejący
  `mkvextract --gui-mode`, a każde prawdziwe `#GUI#progress N%` przekazuje bez
  uśredniania. Pula ekstrakcji ma rozmiar
  `min(file_count, round(sqrt(cpu_count)) + 2)`.
- LLM wykonuje gotowe pliki równolegle dokładnie do `llm_max_concurrency` (1-16);
  scheduler nie przycina tej liczby drugi raz. TTS
  syntetyzuje jeden plik naraz, ale `tts_request_concurrency` aktywnego profilu nie
  jest zmniejszane; audio może pracować równolegle z następną syntezą.
- Wykonywalny plan nie zawiera `MISSING` bez producenta. Task produkuje wyłącznie
  `MISSING` o lifetime `INTERMEDIATE` albo `DURABLE`, a parametry odpowiadają jego
  `TaskKind`.
- Worker otrzymuje w `ArtifactSnapshot` gotowe wejścia i niezmienne deskryptory
  planowanych wyjść, po czym zwraca `TaskResult`; mutable store pozostaje prywatny
  dla schedulera.
- `GraphScheduler.run()` anuluje własny token powiązany z tokenem wywołującego
  przed czekaniem na executory, również przy Ctrl+C i błędzie koordynatora.
- Blokada docelowego produktu odkłada ponowienie atomowego `replace` w koordynatorze.
  Nie usypiaj całej koordynacji na czas retry: niezależne grupy nadal przekazują
  postęp i kończą pracę, a każda próba ponownie sprawdza cancellation i generację sesji.
  `scheduler.py`, `scheduler_runtime.py`
- `WorkspaceInspector.inspect()` probuje grupy równolegle (`_MAX_INSPECTION_WORKERS`),
  bo każda grupa to osobny `mkvmerge`. Kolejność grup i ostrzeżeń pozostaje
  kolejnością discovery — nie zbieraj wyników w kolejności ukończenia.
  `inspection.py`
- `AppService.discover()` jest serializowane (`_discover_lock`) i reużywa poprzednią
  inspekcję, gdy odcisk workspace (ścieżka + rozmiar + mtime każdego odkrytego pliku)
  jest identyczny. Dzięki temu wielokrotne `discover()` w jednej sesji nie powtarza
  probowania, a zmiana pliku wymusza pełną inspekcję. Nie omijaj tego przez własny
  cache w UI. `service.py`
- Produkcyjne `discover()` przygotowuje brakujące narzędzia przed probe, przez
  callback z `bootstrap.py` i istniejący instalator. MKV wymaga MKVToolNix i FFmpeg,
  MP4/audio — FFmpeg; sam TXT lub napisy nie uruchamiają instalacji. Przygotowanie
  jest ciche dla terminala; konstruktory i renderer nie pobierają plików.
  Oczekiwanie na `_discover_lock` sprawdza anulowanie, również podczas Home prewarm.

## Testy

```bash
uv run pytest tests/application -v
```
