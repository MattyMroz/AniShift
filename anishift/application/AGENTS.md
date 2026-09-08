# application

Czysta warstwa produktu i use case'ów współdzielona przez CLI i testy.

## Kierunek zależności

- `artifacts.py`, `control.py`, `intents.py`, `planning.py`, `selection.py` i `planner.py`
  nie importują I/O, `anishift.services`, `anishift.config` ani CLI.
- Kontrolowane I/O należy do `discovery.py`, `inspection.py`, `publisher.py`,
  `sessions.py`, `watch_state.py`, `acquisition.py` (katalog wydań, katalog tytułów i wysyłka do klienta torrent
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
- `catalog_releases` rozdziela trzy powody pominięcia: `hidden` to wydania poniżej
  `min_resolution`, `excluded` — dubbingowane oraz te, którym indeks nie podał języka napisów,
  `filtered` — odrzucone filtrem odcinków (paczki i numery spoza zakresu). Klucz grupy powstaje
  z serii złożonej do liter, cyfr i spacji (`normalize_series`), więc
  `Mushoku Tensei: Jobless Reincarnation` i wersja bez dwukropka to jedna grupa — etykietą
  zostaje pierwszy napotkany zapis. Kolejność grup ma jedno źródło, `order_groups`; ekran nie
  powtarza tej reguły u siebie. `acquisition.py`
- `matches_title` porównuje zbiory `title_forms`: zapis wprost, bez znacznika sezonu i `base_title`
  (bez sezonu i bez podtytułu po `" - "`, `" -"`, `":"` albo `" –"`). Dzięki temu `Solo Leveling`
  Tsundere-Raws trafia w alias `Solo Leveling Season 2 -Arise from the Shadow-`. `acquisition.py`
- `search_title` odpytuje indeks tytułem romaji i angielskim; przy zakresie najwyżej
  `MAX_EPISODE_SPAN` odcinków dokłada zapytania po numerze (`"{base} - 01"`, a przy sezonie > 1
  także `"{base} S02E01"` i numer absolutny), bo RSS oddaje tylko 75 najnowszych trafień i stary
  odcinek inaczej nie wypłynie. Potem `"{seria} {grupa}"` dla maks. `MAX_GROUP_QUERIES` pasujących
  grup wybranych po sumie seedów odcinków wybranego sezonu — nie po dacie, żeby wieloletni
  uploader nie wypadł za nowszymi. Zapytania po numerze idą tylko dla jednego zapisu tytułu —
  angielskiego, a bez niego romaji. Budżet liczy się w żądaniach HTTP, nie w zapytaniach:
  `MAX_REQUESTS`, gdzie zapytanie tytułem albo numerem kosztuje dwa (obie kategorie), a
  doprecyzowanie grupy jeden — grupę pyta się wyłącznie w kategorii, w której ją widziano
  (`fr` → `1_3`, reszta → `1_2`). Scalanie idzie po `info_hash` casefold, pierwszy wpis wygrywa.
  `acquisition.py`
- `season_context` liczy sezony, nie wpisy: `PrequelEntry.cour` (tytuł z `Part N`/`Cour N`) podnosi
  offset, ale nie indeks, a kandydat będący cour zostaje w sezonie swojego poprzednika. Bez tego
  Mushoku Tensei III wychodziło jako sezon 5. `acquisition.py`, `services/catalog/anilist.py`
- `Subscription` trzyma `directory` (jeden folder biblioteki niezależny od serii w nazwie
  wydania), trójkę `season_index`/`episode_offset`/`season_episodes` oraz `taken_episodes`
  (numery odcinków jako teksty dziesiętne). Wszystkie pola spoza pierwotnej dziewiątki są
  opcjonalne przy odczycie, więc starsze pliki wczytują się bez ręcznej naprawy; zapis jest
  zawsze pełny. `subscriptions.py`
- `SCHEMA_VERSION` to `2`, a loader przyjmuje 1 i 2. Plik w wersji 1 `load()` migruje raz: zostawia
  kopię `subscriptions.json.v1.bak` i przepisuje plik w wersji 2, więc drugi `load()` nie zmienia
  już bajtów. Każdy numer z `taken_episodes` staje się `EpisodeOrder(..., ORDERED)` bez hasha —
  `taken` dowodzi przekazania wydania klientowi, nigdy kompletnego pliku. `subscriptions.py`
- `enable`/`disable`/`set_anilist_id` są idempotentne: bez zmiany wartości nie zapisują i nie
  podnoszą `generation`; ze zmianą podnoszą je o 1. `check_all` pomija wpisy wyłączone i te z
  `end_state != ACTIVE`, a `check` wyłączonego wpisu zwraca `CheckOutcome` z problemem i nie
  dotyka źródła. `subscriptions.py`
- `AutomationPolicy.effective_auto`: globalne wyłączenie wygrywa zawsze, inaczej decyduje
  najbliższy jawny wyjątek katalogu idąc w górę do roota (`""`), a katalog bez wyjątku dziedziczy
  ustawienie biblioteki. Rezerwacje i marker ręcznej obsługi (R-028) kluczuje para
  `(group_id, source_fingerprint)` z `watch.py`, więc publikacja produktu nie unieważnia decyzji
  użytkownika. `control.py`
- `WatchStateStore` zapisuje atomowo: `state.json.tmp` + `fsync`, kopia czytelnego `state.json`
  do `state.json.bak`, dopiero potem `replace`. Uszkodzony JSON, nieznany klucz i nieznana wersja
  schematu dają `ConfigError`, nigdy pustego stanu; brak pliku to stan domyślny z wyłączonym Auto.
  `watch_state.py`
- `subscription_id` i `_matches` porównują serię po postaci znormalizowanej (`normalize_series`,
  `series_forms`), nie po surowym zapisie wybranego wydania. Etykietą grupy w katalogu jest
  pierwszy napotkany zapis, więc dosłowne porównanie cicho zabijało subskrypcję. `subscriptions.py`
- `next_episode` przesuwa się do PIERWSZEGO całkowitego numeru od siebie w górę, którego nie ma
  w `taken_episodes` ani wśród odcinków widzianych w tym sprawdzeniu — nigdy za lukę. Numer
  ułamkowy (7.5) trafia do `taken_episodes`, ale licznika nie rusza. `subscriptions.py`
- Gdy surowe wyszukanie nie ma odcinka równego `next_episode`, `check` dokłada jedno zapytanie
  `"{query} NN"`; jego awaria jest logowana i nie przerywa sprawdzenia, bo główne wyszukanie już
  się udało. `subscriptions.py`
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
