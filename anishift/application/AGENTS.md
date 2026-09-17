# application

Czysta warstwa produktu i use case'ów współdzielona przez CLI i testy.

## Kierunek zależności

- `artifacts.py`, `control.py`, `intents.py`, `planning.py`, `selection.py` i `planner.py`
  nie importują I/O, `anishift.services`, `anishift.config` ani CLI.
- Kontrolowane I/O należy do `discovery.py`, `inspection.py`, `publisher.py`,
  `sessions.py`, `watch_state.py`, `acquisition.py` (katalog wydań, katalog tytułów i wysyłka do klienta torrent
  przez wstrzyknięte protokoły `TorrentSource`/`TitleCatalog`/`TorrentClient`; typy z
  `services.torrents` i `services.catalog` tylko pod `TYPE_CHECKING`, poza czystymi
  `season_hint`/`strip_season`, adapterem zachowanej referencji Nyaa i rekonstrukcją `Release`
  dla jawnego ponowienia), handlerów oraz fasady
  `service.py`; koordynator publikuje zwalidowany staging przez `scheduler_runtime.py`.
  Decyzje produktowe pozostają w plannerze.
- Nazwy trwałych produktów pochodzą wyłącznie z `products.py`; żaden inny moduł nie zapisuje
  literałów `.pl`, `.spoken.pl`, `.displayed.pl`, `.pl.mkv`, `.pl.mp4` ani `.m4a`.
- CLI używa publicznej fasady `anishift.application`; nie importuje
  wewnętrznych helperów I/O ani schedulera.
- Oczekiwany konflikt wejścia jest `PlanProblem`. `PlanningError` oznacza uszkodzony
  kontrakt albo graf, nie zwykłą decyzję użytkownika.

## Inwarianty

- `AutomationOwner` zapisuje przyjęcie pracy i jest jedynym autorem stanu rezydenta.
  `RunJournal` zapisuje pozostały graf i potwierdzenia publikacji; niepewne operacje zdalne
  po przerwaniu procesu wymagają jawnego wznowienia, bez automatycznego powtarzania opłat.
- Result notifications follow saved completion and ready provenance, never `GROUP_FINISHED`
  alone. A ready main result may notify while its torrent source is still held. `notified`
  is the durable at-most-once offer guard; ephemeral IDs bind an attempt, set and exact file
  revision. Callbacks revalidate current confirmations and file identity, never History or
  a latest-result fallback. `automation.py`
  Legacy ready inventory refresh runs on the existing I/O pool; notification clicks reuse
  the owner's Library projection plus current confirmations and file identity, without waiting
  for the service discovery lock on the owner thread.
- `history.py` is an owner-written, non-authoritative JSONL beside `WatchState`; its 30-day
  retention and failures never alter admission, deduplication or recovery. Only torn tails
  are repaired; corrupt middle records preserve bytes and produce a History read refusal.
  Recovered terminal observations label admission-time provenance, not a fabricated finish time.
- Retry classification belongs to `AutomationOwner`: resume keeps the entire recorded scope,
  local rebuild enters Manual, and reacquire persists its correlated intent before sending.
  `AcquisitionConfirmation` retains only a verified numeric Nyaa ID and original release title;
  older or unsupported references remain absent. URL restoration belongs to `services/torrents/nyaa.py`.
- `ReadyStore` przenosi ukończoną grupę do `ready/` przez wyłączne dowiązanie i usunięcie
  starej nazwy na tym samym woluminie. Dziennik pozostaje do zapisania nowych tożsamości
  w stanie właściciela; znany torrent musi wcześniej zwolnić pliki. Blokada relokacji
  chroni oba ID grupy przed Auto. Nie przenoś plików bezpośrednio z renderera.
- Discovery skanuje root workspace rekurencyjnie: pomija `temp/` bezpośrednio pod rootem,
  katalogi i pliki od kropki oraz nie wchodzi w dowiązania symboliczne. ID grupy liczy się
  z katalogu względem roota i stemu, więc `A/01.mkv` i `B/01.mkv` to dwie grupy, a plik
  w root zachowuje dotychczasowe ID. `discovery.py`
- `watch.py` sprawdza stabilność pliku, `needs_work` i `WatchLedger`; dostępność źródła
  deleguje do `platform/directory_watch.py`. Windows otwiera plik do odczytu ze współdzieleniem
  wyłącznie odczytu: blokuje aktywnych writerów, dopuszcza odtwarzacz i pliki tylko do odczytu.
  Eksport przez fasadę: `SCAN_INTERVAL_S`, `WatchLedger`. `watch.py`
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
- `SCHEMA_VERSION` to `4`, a loader przyjmuje 1, 2, 3 i 4. Starszy plik `load()` migruje raz: zostawia
  kopię `subscriptions.json.v<wersja>.bak` i przepisuje plik w wersji 4, więc drugi `load()` nie zmienia
  już bajtów. Każdy numer z `taken_episodes` staje się `EpisodeOrder(..., ORDERED)` bez hasha —
  `taken` dowodzi przekazania wydania klientowi, nigdy kompletnego pliku. Kod sprzed schematu 2
  odrzuca plik w wersji 2 (`ConfigError`), więc cofnięcie wersji wymaga przywrócenia kopii
  `subscriptions.json.v1.bak` na miejsce `subscriptions.json` i restartu czuwania. `resolve_subscription_id`
  współdzielony przez ownera i `add` zachowuje ID rozpoznanego sezonu; nowe sezony AniList dostają
  deterministyczne ID uwzględniające sezon. Niepowiązany wpis nie może nadpisać znanego sezonu.
  Przyjęte receipt i późniejsze powiązanie zachowują pierwotne ID oraz historię. `subscriptions.py`
- Rezydent planuje `check_due` według zapisanych terminów odcinków. Niepowiązane wpisy zachowują
  godzinne szukanie wydań; osobne próby powiązania respektują opóźnienia i budżet retry. Kalendarz
  ma osobny trwały budżet i błąd; jego awaria nie blokuje wydań o potwierdzonym terminie.
  HIATUS i najbliższa znana data odległa o ponad dobę oznaczają dobowe odświeżanie; daty bliskie
  i nieznane używają `recheck_interval_s`. Jawne sprawdzenie pozwala na jedną próbę po wyczerpaniu
  budżetu, respektując blokadę dostawcy. `subscriptions.py`
- `requested_at` zapisuje jawny wybór, a `awaiting_airing` zachowuje oczekiwanie na konkretną emisję:
  początek sezonu ani jego liczba odcinków nie uruchamiają wszystkich okien. Jawnie wybrany numer
  bez daty może mieć ograniczone okno szukania, jeśli brak znanej przeszkody przyszłej emisji.
  HIATUS zachowuje przyszły zamiar; FINISHED/CANCELLED nie otwierają okien nieemitowanych numerów.
  Terminalne okno nie odradza się po restarcie ani powtórzeniu receipt. `subscriptions.py`
- `RequestControl` opakowuje wspólny transport HTTP metadanych i qBittorrenta. Liczy rzeczywiste
  wywołania, współdzieli aktywne odczyty i blokady dostawców; trwałe terminy blokad zapisuje owner.
  Budżet jednej operacji obejmuje zagnieżdżone zapytania, bez retry transportu. `services/http_requests.py`
- `subscription_add` zapisuje receipt przed zmianą drugiego pliku; `added_by_command` pozwala
  dokończyć potwierdzenie bez ponownego podniesienia generacji. Ręczne `download` zapisuje receipt
  i hashe przed wysłaniem. Panel w trybie rezydenta prowadzi także wyszukiwanie przez ownera.
- `enable`/`disable`/`set_anilist_id` są idempotentne: bez zmiany wartości nie zapisują i nie
  podnoszą `generation`; ze zmianą podnoszą je o 1. `check_all` pomija wpisy wyłączone i te z
  `end_state != ACTIVE`, a `check` wyłączonego wpisu zwraca `CheckOutcome` z problemem i nie
  dotyka źródła. `subscriptions.py`
- `AutomationPolicy.effective_auto`: globalne wyłączenie wygrywa zawsze, inaczej decyduje
  najbliższy jawny wyjątek katalogu idąc w górę do roota (`""`), a katalog bez wyjątku dziedziczy
  ustawienie biblioteki. Rezerwację kluczuje `group_id` (jej `fingerprint` służy tylko do
  unieważnienia podglądu), a marker ręcznej obsługi (R-028) para `(group_id, source_fingerprint)`
  z `watch.py`, więc publikacja produktu nie unieważnia decyzji użytkownika. `control.py`
- `AutomationOwner` (`automation.py`) jest jedynym właścicielem `WatchState`: jeden wątek
  `anishift-owner` zdejmuje polecenia z kolejki, a `preview` i `subscriptions_check` idą na pulę
  `anishift-owner-io`, więc `set_auto` nie czeka na skan biblioteki ani na sieć. Pętla śpi na
  kolejce bez timeoutu — bezczynny rezydent nie wykonuje pracy. `automation.py`
- Polecenie mutujące zapisuje stan RAZEM z `CommandReceipt` PRZED pozytywną odpowiedzią; nieudany
  zapis daje `INTERNAL` i zero skutku, a powtórzony `command_id` zwraca zapisany wynik bez
  drugiego wykonania (AC-042). `start` zapisuje `ProcessingRequest` razem z receipt przed
  `submit_plan`: odpowiedź potwierdza przyjęcie zamiaru; późniejsza awaria wykonania ma stan
  `FAILED`, a ponowienie polecenia zwraca ten sam `run_id`. `automation.py`
- `ProcessingRequest.state == ACCEPTED` can include executing tasks. Public progress events
  prove per-group activity; retained `run_progress` views also include terminal attempts.
  The technical `materials` snapshot includes downloads and waiting/problem rows; the panel
  selects admitted downloads, live requests awaiting their first task and proven active tasks. Ordinary download
  admission protects every recorded hash, including failed acquisitions; explicit reacquire
  retains the old confirmation and correlates the new attempt. Progress labels select primary source artifacts
  using the group's workflow route, including standalone subtitles and audio. `automation.py`
- Rezerwacje są własnością sesji klientów jednej instancji: `AutomationOwner` porzuca je przy
  wczytaniu stanu i po rozłączeniu panelu. Rozłączenie unieważnia także podglądy, również
  kończące się po zwolnieniu rezerwacji.
  `automation.py`
- Startup discards previous-session reservations in memory even when persisting that cleanup
  fails; the failed write must not revive dead clients' ownership. `automation.py`
- Zdarzenia plików są scalane w jednym oczekującym powiadomieniu; ponad 4096 ścieżek zastępuje
  pełne uzgodnienie. Inspekcja działa w puli I/O, a właściciel decyduje o Auto po stabilizacji.
  Zmiana źródeł lub produktów unieważnia podgląd właściwej grupy; nowy podgląd klienta zastępuje
  poprzedni. `automation.py`
- Sygnał zakończenia procesu omija zapis receipt i zawsze rozpoczyna drain, także gdy zapis
  stanu zawodzi. Polecenia sterowania nadal zachowują trwałość przed potwierdzeniem.
  `automation.py`
- `shutdown` zamyka dopuszczanie tasków; aktywne zadania kończą się bez anulowania, pozostały
  graf otrzymuje `PAUSED`. Staging zatrzymanych runów pozostaje chroniony przed cleanup.
  `scheduler.py`, `service.py`, `sessions.py`
- Pętla właściciela kończy się dopiero, gdy po `shutdown` nie ma ani aktywnych runów, ani
  zleceń nierozliczonych przez samego właściciela (`_drained`). Sam `active_run_ids()` nie
  wystarcza: run bywa zdjęty z rejestru fasady, zanim właściciel zapisze jego stan końcowy.
  `automation.py`
- Dopuszczenie pobrania i zapis wyniku subskrypcji wracają z puli I/O do właściciela;
  drain czeka także na te komendy. `AcquisitionConfirmation` jest zapisywane przed add,
  a niepewne przekazanie blokuje ponowne dodanie hasha i innej wersji tego samego numeru.
  Usunięcie subskrypcji nie usuwa potwierdzenia. Obecność hasha w kliencie oznacza
  `ACCEPTED`, nigdy kompletność pliku. `automation.py`, `subscriptions.py`
- `TransferInspector` odczytuje zbiorczą listę aktywnych transferów; metadane plików
  odświeża po ich uzyskaniu i przy przejściu do kompletności. Do Auto dopuszcza wybrane
  pliki po dowodzie klienta, zgodności rozmiaru i lokalnej dostępności. Nieznane nazwy
  przyjętego transferu blokują Auto w jego katalogu do odczytania metadanych. Po `COMPLETE`
  właściciel zleca zwykłą inspekcję plików; gdy brak `ACCEPTED`, nie odpytuje klienta.
  `transfers.py`, `automation.py`
- `ProcessingRequest` zachowuje pełny niejawny dla UI `RunSettingsSnapshot`, wybrane
  `GroupIntent` i `RebuildRequest`. Zagnieżdżone listy ustawień z JSON wracają do krotek;
  nazwy pól zawierające segment sekretu są odrzucane. Stare zlecenia bez `intents` nadal
  się wczytują, ale nie pozwalają odtworzyć wyborów, których dawny zapis nie zachował.
  `automation.py`, `control.py`, `control_payloads.py`, `watch_state.py`
- `recipe_update` changes only a validated target delta and commits its receipt with
  `WatchState.recipes`. Video remains an `AutoPreset`; subs inherits video and cover
  inherits audiobook. Preview captures recipe preferences alongside its plan; admission
  and recovery must not relabel an older plan with current recipe preferences. `automation.py`
- Aktualność podglądu sprawdza się przez ponowny `source_fingerprint` grup podglądu (kilka
  `stat`), nie przez pełny `discover()` na wątku właściciela. `automation.py`
- `AppService.reload_preferences()` wczytuje ponownie `settings.json` i `.env` pod `_run_lock`;
  trwające zlecenia zachowują snapshot ustawień, który mają w planie (D-09). `service.py`
- `AppService.execute()` po przerwaniu anuluje run i CZEKA na domknięcie kontekstu, zanim
  przekaże wyjątek dalej — inaczej taski, procesy narzędzi i katalog `temp/` przeżyłyby
  wywołującego. `_finish_run` zawsze zamyka handler i sesję oraz zawsze rozwiązuje `RunHandle`,
  bo nierozwiązany handle wiesza `execute` na zawsze. `service.py`
- `WatchStateStore` zapisuje atomowo: `state.json.tmp` + `fsync`, kopia czytelnego `state.json`
  do `state.json.bak`, dopiero potem `replace`. Uszkodzony JSON, nieznany klucz i nieobsługiwana
  wersja schematu dają `ConfigError`, nigdy pustego stanu; brak pliku to stan domyślny z pracującą
  automatyzacją, a zapisana pauza pozostaje pauzą. `WATCH_STATE_SCHEMA_VERSION` to `2`, a loader przyjmuje 1 i 2: starszy plik `load()` migruje
  raz, zostawia kopię `state.json.v1.bak` i przepisuje plik, więc drugi `load()` nie zmienia bajtów.
  Walidacja jest wersjonowana — dokument wersji 2 musi zawierać wszystkie sekcje schematu 2
  (`recipes`, `ready_groups`, `pause_owned_transfers`, `pending_deletions`, `complete_files`), a
  dokument wersji 1 nie może zawierać żadnej z nich. Migracja nadaje `complete_files` z
  `required_files` wyłącznie potwierdzeniom w stanie `COMPLETE`. Trwałe ścieżki `ReadyGroup`
  i `PendingDeletion` przechodzą przez `require_relative_paths`. `watch_state.py`, `control.py`
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
- `GraphCoordinator` przyjmuje wiele niezależnych kontekstów planów (`RunRequest` →
  `RunHandle`). Kontekst ma własny plan, sesję, handler, emitter, `ArtifactStore`,
  cancellation i `NaturalOrderGate`; wspólne są wyłącznie kolejki gotowych tasków per
  zasób, executory i limity z `limits_provider()`. `GraphScheduler.run()` to adapter
  jednego planu: prywatny koordynator, `submit`, czekanie na wynik, `close()`. Błąd
  pętli koordynatora anuluje tokeny wszystkich kontekstów przed joinem executorów i
  wraca do wywołującego przez `RunHandle.result()`. `scheduler.py`
- Element wspólnej kolejki to `(rank, sequence, task_index, run_id, task_id)`, gdzie
  `rank` = 0 dla `RequestOrigin.USER` i 1 dla `BACKGROUND`. Wybór następuje dopiero przy
  realnie wolnym slocie, a liczba wysłanych tasków per zasób nie przekracza
  `worker_limit` — koordynator nie dokłada zapasu `max_pending_per_resource` do puli
  executora. Limity liczbowe pochodzą z `ResourceLimits` (`plan.settings` tylko dla
  domyślnego profilu tłumaczenia), pula ekstrakcji z liczby grup ekstrakcyjnych
  WSZYSTKICH aktywnych kontekstów. `scheduler.py`, `scheduler_contracts.py`
- `RequestOrigin` określa priorytet, a `RunRequest.automatic` dodatkowo podporządkowuje
  pilny plik wyjątkowi Auto dla katalogu pliku. Wyłączony katalog zatrzymuje kolejne taski
  automatycznego zlecenia, ale jawne zlecenie tego pliku nadal działa. Dotychczasowe
  `BACKGROUND` zawsze podlega temu wyjątkowi.
  `scheduler_runtime.py`, `scheduler.py`
- Globalna pauza (`AutomationPolicy.auto_enabled == False`) jest szersza od wyjątków katalogów:
  `GraphCoordinator.pause()` wstrzymuje dopuszczanie wszystkich zleceń, więc pod pauzą nie
  przechodzi też jawny start ani jawne pobranie. `resume()` zwalnia dopuszczanie, chyba że
  koordynator już się zamyka. `scheduler.py`, `service.py`, `automation.py`
- Wątek `anishift-coordinator` istnieje tylko wtedy, gdy koordynator ma zlecenia:
  `submit` go startuje, pusta runda zamyka executory i kończy wątek, `close()` anuluje
  resztę i dołącza go. Bezczynny koordynator nie budzi się (licznik `wakeups`).
- `AppService` prowadzi rejestr aktywnych runów: `submit_plan` nie blokuje, `execute`
  to `submit_plan(...).result()`, a `cancel(run_id)` działa dla każdego aktywnego runu.
  Druga praca nad tą samą grupą jest odrzucana (`RunConflictError`, I-001), a
  `cleanup_orphaned_temp` dostaje komplet aktywnych `run_id`. Sesję zamyka wątek
  domykający run — bez nazwy `anishift-`, bo ten prefiks jest zarezerwowany dla pul,
  które muszą zostać dołączone. `service.py`
- Blokada docelowego produktu odkłada ponowienie atomowego `replace` w koordynatorze.
  Nie usypiaj całej koordynacji na czas retry: niezależne grupy nadal przekazują
  postęp i kończą pracę, a każda próba ponownie sprawdza cancellation i generację sesji.
  `scheduler.py`, `scheduler_runtime.py`
- `WorkspaceInspector.inspect()` probuje grupy równolegle (`_MAX_INSPECTION_WORKERS`),
  bo każda grupa to osobny `mkvmerge`. Kolejność grup i ostrzeżeń pozostaje
  kolejnością discovery — nie zbieraj wyników w kolejności ukończenia.
  `inspection.py`
- `AppService.discover()` jest serializowane (`_discover_lock`). Bez `changed_paths` uzgadnia
  pełną listę plików; z listą zdarzeń aktualizuje `DiscoveryIndex` bez przechodzenia pozostałych
  katalogów. `WorkspaceInspector` zachowuje inspekcję niezmienionych grup i katalogi ścieżek
  niezmienionych mediów, również po dodaniu napisów. Usunięte grupy wypadają z cache.
  Nie dodawaj osobnego cache w UI. `service.py`, `discovery.py`, `inspection.py`
- Produkcyjne `discover()` przygotowuje brakujące narzędzia przed probe, przez
  callback z `bootstrap.py` i istniejący instalator. MKV wymaga MKVToolNix i FFmpeg,
  MP4/audio — FFmpeg; sam TXT lub napisy nie uruchamiają instalacji. Przygotowanie
  jest ciche dla terminala; konstruktory i renderer nie pobierają plików.
  Oczekiwanie na `_discover_lock` sprawdza anulowanie, również podczas Home prewarm.

## Testy

```bash
uv run pytest tests/application -v
```
