# application

Czysta warstwa produktu i use case'ów współdzielona przez CLI i testy.

## Kierunek zależności

- `artifacts.py`, `control.py`, `intents.py`, `planning.py`, `selection.py` i `planner.py`
  nie importują I/O, `anishift.services`, `anishift.config` ani CLI.
- Kontrolowane I/O należy do `discovery.py`, `inspection.py`, `publisher.py`, `sessions.py`,
  `watch_state.py`, handlerów, fasady `service.py` i `acquisition.py`. `acquisition.py` (katalog
  wydań, katalog tytułów, wysyłka do klienta) używa wstrzykniętych protokołów
  `TorrentSource`/`TitleCatalog`/`TorrentClient`; typy z `services.torrents` i `services.catalog`
  importuje tylko pod `TYPE_CHECKING`, poza czystymi `season_hint`/`strip_season`, adapterem
  zachowanej referencji Nyaa i rekonstrukcją `Release` dla jawnego ponowienia. Koordynator publikuje
  zwalidowany staging przez `scheduler_runtime.py`. Decyzje produktowe pozostają w plannerze.
- Nazwy trwałych produktów pochodzą wyłącznie z `products.py`; żaden inny moduł nie zapisuje
  literałów `.pl`, `.spoken.pl`, `.displayed.pl`, `.pl.mkv`, `.pl.mp4` ani `.m4a`.
- CLI używa publicznej fasady `anishift.application`; nie importuje wewnętrznych helperów I/O
  ani schedulera.
- Oczekiwany konflikt wejścia jest `PlanProblem`. `PlanningError` oznacza uszkodzony kontrakt
  albo graf, nie zwykłą decyzję użytkownika.

## Owner i stan rezydenta

- `AutomationOwner` (`automation.py`) jest jedynym autorem `WatchState`: wątek `anishift-owner`
  zdejmuje polecenia z kolejki, a `preview` idzie na pulę `anishift-owner-io`,
  więc `set_auto` nie czeka na skan. Pętla śpi na kolejce bez timeoutu — bezczynny
  rezydent nie wykonuje pracy.
- Polecenie mutujące zapisuje stan RAZEM z `CommandReceipt` PRZED pozytywną odpowiedzią; nieudany
  zapis daje `INTERNAL` i zero skutku, a powtórzony `command_id` zwraca zapisany wynik bez drugiego
  wykonania. `start` zapisuje `ProcessingRequest` z receipt przed `submit_plan`; późniejsza awaria
  wykonania ma stan `FAILED`, a ponowienie zwraca ten sam `run_id`.
- `RunJournal` zapisuje pozostały graf i potwierdzenia publikacji; niepewne operacje zdalne po
  przerwaniu procesu wymagają jawnego wznowienia, bez automatycznego powtarzania opłat.
- Rezerwacje należą do sesji klientów jednej instancji: owner porzuca je przy wczytaniu stanu
  (także gdy zapis tego sprzątania zawiedzie) i po rozłączeniu panelu. Rozłączenie unieważnia też
  podglądy, również kończące się po zwolnieniu rezerwacji.
- Zdarzenia plików scalają się w jednym oczekującym powiadomieniu; ponad 4096 ścieżek zastępuje
  pełne uzgodnienie. Inspekcja działa w puli I/O, a owner decyduje o Auto po stabilizacji. Zmiana
  źródeł lub produktów unieważnia podgląd grupy; nowy podgląd klienta zastępuje poprzedni.
  Aktualność podglądu sprawdza ponowny `source_fingerprint` (kilka `stat`), nie pełny `discover()`.
- Sygnał zakończenia procesu omija zapis receipt i zawsze zaczyna drain, także gdy zapis stanu
  zawodzi; polecenia sterowania nadal zapisują stan przed potwierdzeniem. Pętla ownera kończy się dopiero, gdy po `shutdown` nie ma aktywnych runów ani zleceń
  nierozliczonych przez ownera (`_drained`); samo `active_run_ids()` nie wystarcza, bo run bywa
  zdjęty z rejestru fasady przed zapisem stanu końcowego. Drain czeka też na dopuszczenia pobrań
  i inne wyniki wracające z puli I/O.
- `shutdown` zamyka dopuszczanie tasków; aktywne zadania kończą się bez anulowania, reszta grafu
  dostaje `PAUSED`, a staging zatrzymanych runów jest chroniony przed cleanup.
  `scheduler.py`, `service.py`, `sessions.py`
- `ProcessingRequest` zachowuje pełny, niejawny dla UI `RunSettingsSnapshot`, wybrane `GroupIntent`
  i `RebuildRequest`. Zagnieżdżone listy z JSON wracają do krotek; pola z segmentem sekretu są
  odrzucane. Stare zlecenia bez `intents` wczytują się, ale nie odtwarzają niezapisanych wyborów.
  `control.py`, `control_payloads.py`, `watch_state.py`
- `ProcessingRequest.state == ACCEPTED` może obejmować wykonujące się taski. Publiczne zdarzenia
  postępu dowodzą aktywności grupy; zachowane `run_progress` obejmują też próby terminalne. Migawka
  `materials` zawiera pobrania i wiersze oczekujące/problemowe; panel wybiera przyjęte pobrania,
  żywe zlecenia czekające na pierwszy task i dowiedzione aktywne taski. Etykiety postępu wybierają
  główne artefakty źródłowe według trasy workflow grupy, także dla samodzielnych napisów i audio.
- `recipe_update` zmienia tylko zwalidowaną różnicę celu i zapisuje receipt razem z
  `WatchState.recipes`. Video pozostaje `AutoPreset`; subs dziedziczy po video, cover po audiobook.
  Podgląd utrwala preferencje receptury razem z planem; dopuszczenie i recovery nie przepisują
  starszego planu bieżącymi preferencjami.
- `AutomationPolicy.effective_auto`: globalne wyłączenie wygrywa zawsze, inaczej decyduje najbliższy
  jawny wyjątek katalogu w górę do roota (`""`), a katalog bez wyjątku dziedziczy ustawienie
  biblioteki. Rezerwację kluczuje `group_id` (`fingerprint` tylko unieważnia podgląd), a marker
  ręcznej obsługi para `(group_id, source_fingerprint)` z `watch.py`, więc publikacja produktu nie
  unieważnia decyzji użytkownika. `control.py`
- Pauza automatyzacji (`auto_enabled == False`) blokuje powtórki i automatyczne dopuszczenie
  workspace przez `set_background_admission`, nigdy
  `pause_runs`. Praca zlecona przez użytkownika nie jest odrzucana: Start, Ręczny, ponowienie i
  ponowne pobranie z panelu oraz D. Pobranie jest ręczne, gdy `AcquisitionConfirmation.manual`
  dowodzi pochodzenia USER bez subskrypcji albo jawnego ponownego pobrania. Recovery przy starcie
  i potwierdzanie add obejmują tylko potwierdzenia przyjmowane przez `_working`, więc transfery
  ręczne wracają mimo pauzy. Partie odcinków, metadane, selekcja, treść i publikacja ręcznych
  pobrań trwają w pauzie; ich pliki przechodzą zwykłe kontrole z `explicit=True` i idą z
  `automatic=False`. Sam priorytet USER świeżego pliku nie zwalnia z pauzy. Wznowienie zachowuje
  deduplikację zleceń/receipt i restartuje tylko automatyczne transfery wstrzymane przez pauzę.
  `control.py`, `automation.py`, `scheduler.py`
- Klasyfikacja ponowienia należy do ownera: wznowienie zachowuje cały zapisany zakres, lokalna
  przebudowa przechodzi do Ręcznego, a ponowne pobranie zapisuje skorelowany zamiar przed wysłaniem.
  `AcquisitionConfirmation` zachowuje tylko zweryfikowane liczbowe ID Nyaa i oryginalny tytuł
  wydania; starsze lub nieobsługiwane referencje pozostają puste. Odtwarzanie URL należy do
  `services/torrents/nyaa.py`.
- `WatchStateStore` zapisuje atomowo: `state.json.tmp` + `fsync`, kopia czytelnego `state.json` do
  `state.json.bak` (bez parsowania po udanym `load()`/`save()` tej instancji; nieznany plik wymaga
  walidacji), potem `replace`. Uszkodzony JSON, nieznany klucz i nieobsługiwana wersja dają
  `ConfigError`, nigdy pustego stanu; brak pliku to stan domyślny z działającą automatyzacją, a
  zapisana pauza pozostaje pauzą. `WATCH_STATE_SCHEMA_VERSION` to `4`; loader przyjmuje 1-4, starszy
  plik migruje raz z kopią `state.json.v<wersja>.bak`, więc drugi `load()` nie zmienia bajtów.
  Przed pierwszym zapisem schematu 3 i schematu 4 (także przy pierwszym `save()` bez `state.json`)
  kopiuje bajt w bajt `state.json` i `subscriptions.json` do `*.e2-migration.bak` i
  `*.e3-migration.bak`: istniejącej kopii nie nadpisuje, brak pliku tylko loguje, a błąd kopii to
  `ConfigError` `IO_ERROR` bez zapisu nowego formatu.
  Walidacja jest wersjonowana: dokument 2+ musi mieć sekcje `recipes`, `ready_groups`,
  `pause_owned_transfers`, `pending_deletions`, `complete_files`, dokument 1 żadnej z nich;
  dokument 4 musi mieć `subscriptions`, `removed_subscription` i `legacy_orders`, starsze nie mogą;
  potwierdzenie wersji 3+ musi mieć `assignments` i `legacy_scope`, starsze nie mogą. Migracja nadaje
  `complete_files` z `required_files` tylko potwierdzeniom `COMPLETE`. Trwałe ścieżki `ReadyGroup` i
  `PendingDeletion` przechodzą przez `require_relative_paths`. Opcjonalne `PendingDeletion.restore`
  jest w schemacie 2; czytniki sprzed Undo odrzucają je po pierwszym Undo. Nie usuwaj dowodów
  recovery, żeby umożliwić downgrade. `watch_state.py`, `control.py`

## Biblioteka, gotowe wyniki i historia

- Powiadomienia o wyniku wynikają z zapisanego ukończenia i pochodzenia gotowego wyniku, nigdy z
  samego `GROUP_FINISHED`. Gotowy wynik główny może powiadomić, gdy źródło torrent jest jeszcze
  trzymane. `notified` to trwała ochrona jednokrotnej oferty; ulotne ID wiążą próbę, zestaw i
  dokładną rewizję plików. Callbacki sprawdzają ponownie bieżące potwierdzenia i tożsamość plików,
  nigdy Historii ani „ostatniego wyniku”.
- Odświeżanie starego inwentarza `ready/` działa w istniejącej puli I/O; kliknięcia powiadomień
  używają projekcji Biblioteki ownera z bieżącymi potwierdzeniami i tożsamością plików, bez
  czekania na blokadę discovery fasady na wątku ownera.
- `history.py` to pisany przez ownera, nieautorytatywny JSONL obok `WatchState`; retencja 30 dni i
  awarie nie zmieniają dopuszczenia, deduplikacji ani recovery. Naprawiany jest tylko urwany ogon;
  uszkodzony rekord w środku zachowuje bajty i daje odmowę odczytu Historii. Odzyskane obserwacje
  terminalne opisują pochodzenie z chwili przyjęcia, nie zmyślony czas zakończenia.
- `ReadyStore` przenosi ukończoną grupę do `ready/` przez wyłączne dowiązanie i usunięcie starej
  nazwy na tym samym woluminie. Dziennik zostaje do zapisu nowych tożsamości w stanie ownera; znany
  torrent musi wcześniej zwolnić pliki. Blokada relokacji chroni oba ID grupy przed Auto. Nie
  przenoś plików z renderera.
- Usuwanie z Biblioteki pomija pasujące pobranie tylko w stanie `COMPLETE` z receipt managera
  dowodzącym zwolnienia. Dowód zwolnienia czytaj w puli I/O i sprawdź stan ownera ponownie przed
  przyjęciem; same historyczne ścieżki relokacji nie dowodzą aktywnego posiadania.
- Undo zapisuje przyjęcie `PendingDeletion.restore` i start każdego pliku przed skutkami natywnymi.
  Cel to ostatnie usunięcie ze skutkami w kolejności dopisania; udane Undo go konsumuje.
  `DeletionRestore.unsettled` chroni nierozstrzygnięte rozpoczęte skutki po restarcie, nie
  nieszkodliwą odmowę wstępną. Zachowuj oryginalne receipt, dowody produktów i rekordy deduplikacji.

## Pobieranie odcinków

- `episode_identity.py` posiada zamrożoną klasyfikację H1; `episode_selection.py` jej czysty
  builder wejścia, projekcje franczyzy i odcinków, fakty wydań i ranking. Produkcja przekazuje tylko
  `target` i `candidate`, bez dowodów, dodatków roku, etykiet i hashy. Cel buduj z pełnego
  `FranchiseGraph` i surowych odcinków ani.zip, nigdy z wyświetlanej franczyzy.
- Zmiana H1 wymaga minimalnego przypadku padającego w
  `tests/fixtures/acquisition/identity-regressions.json`, poprawki konkretnej przyczyny, tłumaczeń
  powodów, testów tożsamości/golden i raportu porównania; procedura w
  `docs/work/acquisition/plans/e1-integracja.md` §10.6, a zmiana golden wymaga niezależnego review.
  Nigdy nie zamieniaj wyjątku programistycznego w niepewny werdykt.
- `AcquisitionService.franchise/episodes/offer` to operacje katalogu tylko do odczytu wystawione
  przez IPC ownera. Grafy, mapowania i harmonogramy zostają w pamięci usługi; nie powstaje przyjęcie
  ani receipt. Awaria harmonogramu zachowuje mapowanie z ostrzeżeniem i terminem ponowienia. `offer`
  używa zapamiętanego grafu bez rozwijania niepełnego liścia; filmy wołają `movie_streams` z
  `EpisodeKey(id, 1)`. Sugestie pomijają niezgodne wydania i znane nieobsługiwane kontenery.
- `AutomationOwner.admit_episode` to synchroniczna bramka przyjęcia: jeden zapis `ADMITTED`
  (selektywne `AcquisitionConfirmation` z `EpisodeAssignment`) razem z receipt, bez skutków w qB.
  Wysyłkę przejmuje cykl transferów (niżej); komenda `transfer` na hash w stanie `ADMITTED` dostaje
  `transfer_not_started`. Nowy klucz odcinka dołącza do jedynego aktywnego transferu selektywnego
  swojego hasha; po `COMPLETE` albo `FAILED` dostaje nową operację i staging. Przed ponownym dodaniem
  tego samego hasha zwolnij poprzedni wpis klienta; stare klucze pozostają chronione. Hashe legacy
  i kilka niedokończonych transferów odmawiają z `transfer_recorded`.
- Konflikt liczy `control.episode_conflict`: klucz → `episode_admitted`, `LegacyScope` zapisany w
  potwierdzeniu albo w `WatchState.legacy_orders` → `episode_possibly_admitted`.
  Polecenie `download` (stare wydania wg grup) nie ma klucza odcinka, bo przed
  przyjęciem brak nazwy pliku dla H1; dostaje `LegacyScope(ID, numer lokalny)` i odmawia wobec
  przyjęć kluczowych (`legacy_conflict`), także przy powtórzeniu. Wywołujący `download` podaje ID
  tytułu i offset sezonu; nieznany offset daje zakres całego ID. Zapisane numery są lokalne — offset
  odejmuje się tylko od surowego numeru wydania bez odczytu sezonu. `automation.py`, `control.py`
- `episode_download` zapisuje receipt partii przed odczytem źródeł; każde przyjęcie ma receipt
  kluczowany ID partii i numerem odcinka. Rozłączenie zachowuje partię, restart oznacza niedokończone
  partie jako przerwane bez wznawiania pozostałych kluczy. Wynik przyjęć odzyskuj z pojedynczych
  receipt, gdy zapis wyniku partii został przerwany. Koniec partii emituje `episode_batch` nawet przy
  nieudanym końcowym zapisie; zdarzenie opisuje bieżącą próbę, autorytatywne są trwałe receipt.
  Lokalne powody odmów i stanów ownera to `EpisodeReason`; pola `reason` zostają `str`, bo historyczne
  receipt mogą zawierać dowolną wartość. `episode_commands.py`, `automation.py`
- `episode_offer` trzyma jedną interakcję na połączenie; nowszy odczyt i rozłączenie ją unieważniają.
  `episode_choose` konsumuje dokładnie zapisanego kandydata bez ponownego odczytu źródła. Niepewne
  automatyczne sugestie są dozwolone, ale jawny wybór niepewnego/niezgodnego wymaga osobnego
  potwierdzenia. Zgoda na powtórkę wiąże bieżące tożsamości zamówień legacy i ostatnie przyjęcie.
  Nieznane transfery legacy zostają nietknięte; znane zastąpione przypisania zachowują pliki i tracą
  tylko aktywny zakres. Nowa treść czeka na zastosowaną rewizję poprzedniego zakresu.
- Projekcja `episode_states` nie mutuje stanu: nierozliczony lub problemowy poprzednik daje
  `waiting_previous_transfer`; gotowy odcinek bez `ReadyGroup.main_result` (lub źródłowego wideo,
  gdy wyniku brak) daje `not_ordered` + `result_missing`, a D powtarza go bez wykluczania
  poprzedniego wydania. Gdy niedokończony transfer tego wydania trzyma poprzednie przypisanie,
  D odmawia z `pack_in_progress`. `automation.py`
- `episode_file_choose` czyta świeżą mapę plików, sprawdza rewizję oraz dokładne index/path/size i
  zapisuje wideo z napisami/audio o tym samym stemie razem z receipt przed selekcją. Po odczycie
  sprawdź receipt ponownie na wątku ownera, żeby równoległe ponowienia rozliczyły się idempotentnie.
  Nie używaj wideo ze starszego przypisania. Sprawdzaj rewizję selekcji i przypisanie, nie całe
  potwierdzenie: zmiana samego znacznika czasu nie unieważnia wyboru pliku.
- Pomocnicze funkcje metadanych w `transfers.py` wybierają unikalną dokładną nazwę wideo przed H1
  na oryginalnych pełnych ścieżkach; `fileIdx` źródła nigdy nie wybiera pliku. Brak unikalnego
  dopasowania daje pustą selekcję (ręczny wybór pliku). Pliki towarzyszące wymagają tego samego
  katalogu i stemu. `file_map_revision` pomija postęp i priorytety oraz waliduje unikalne ścieżki
  Windows i indeksy. Zbiór wybranych plików to `AcquisitionConfirmation.wanted_files` (indeksy
  aktywnych przypisań); przed `select_files` `_apply_selection` odrzuca mapę, której rewizja różni
  się od `file_map` któregokolwiek aktywnego przypisania. `automation.py`
- Cykl selektywny prowadzi istniejący poller, tylko gdy `AcquisitionService.selective`: `ADMITTED` →
  trwałe `PENDING_SEND` → `add_metadata` → `ACCEPTED` (wyjątek add → `UNCERTAIN`). Po mapie plików
  owner zapisuje przypisania z podniesionym `selection_revision` PRZED `select_files`; potwierdzenie
  zapisuje `applied_revision` tylko dla niezmienionej rewizji i zeruje `content_started`. Start
  wymaga potwierdzonej selekcji, niepustego zestawu, stanu stop i braku żądanego stop/cancel.
  Działający transfer przed nową selekcją dostaje stop i czeka na kolejną rundę. Wynik workera
  scala się tylko przy niezmienionym `_selection_basis`, a `_may_settle` odrzuca go po stop/cancel
  zleconym w trakcie rundy.
- Przed KAŻDYM startem i KAŻDYM resume selektywnym (także po restarcie i końcu pauzy) owner czyta
  klienta na świeżo (`_mismatched`) i porównuje `save_path` ze stagingiem, mapę index/path/size z
  przypisaniami i priorytety z `wanted_files`; niezgodność albo brak transferu zatrzymuje go z
  `_SELECTION_MISMATCH` — cache inspektora tu nie wystarcza. Tuż przed startem owner ponownie
  sprawdza `_may_start_selection` (polityka, action ID, `_selection_basis`); resume chroni
  `_mark_sent`, który odrzuca akcję zastąpioną w trakcie odczytu.
- Rekord selektywny nie przechodzi w `COMPLETE`/release, dopóki selekcja nie jest zastosowana i
  każde aktywne przypisanie nie ma przekazanego zestawu (`handed_off`); inspektor zachowuje listę
  plików ukończonego transferu (`stale`). Timeout metadanych (`METADATA_TIMEOUT_S`) liczy się w
  pamięci na próbę; jawne resume zaczyna nową (`restart_idle`). Resume bez potwierdzonej selekcji
  nie wysyła `resume`: w `metaDL` metadane nadal się pobierają, a zatrzymany transfer bez metadanych
  dostaje `_METADATA_STOPPED` (bez ponownego add). Pauza automatyzacji zatrzymuje tylko nieręczne
  transfery z `applied_revision > 0`. Selektywne `PENDING_SEND` uzgadnia się z klientem bez
  ponownego add: niewidoczny hash dostaje do `_SEND_CHECKS` odczytów, potem `UNCERTAIN` z
  `_SEND_UNCONFIRMED`, a resume sprawdza go od nowa. `automation.py`, `transfers.py`
- Potwierdzony transfer selektywny nieobecny w udanym odczycie klienta przechodzi w `FAILED` z
  `removed_from_client`; start uzgadnia stare `UNCERTAIN` tylko przy trwałym potwierdzeniu
  (`content_started` albo `applied_revision > 0`). Niepotwierdzone wysyłki zachowują ochronę.
  `protected_assignments` współdzielą konflikty i status: usunięcie lub potwierdzone anulowanie
  zwalnia tylko przyjęcia bez publikacji; dowody publikacji, pliki i rekordy historyczne zostają.
- `TransferInspector` czyta zbiorczą listę aktywnych transferów; metadane plików odświeża po ich
  uzyskaniu i przy przejściu do kompletności. Do Auto dopuszcza wybrane pliki po dowodzie klienta,
  zgodności rozmiaru i lokalnej dostępności. Nieznane nazwy przyjętego transferu blokują Auto w jego
  katalogu do odczytu metadanych. Przejście w uncertain/removed wymaga trzech kolejnych udanych
  odczytów listy bez hasha; licznik w pamięci zeruje obecność albo zdjęcie z inspekcji. Po
  `COMPLETE` owner zleca zwykłą inspekcję plików; bez `ACCEPTED` nie odpytuje klienta.
- `AcquisitionConfirmation` zapisuje się przed add; niepewne przekazanie blokuje ponowne dodanie
  hasha i innej wersji tego samego numeru. Zwykłe dopuszczenie chroni każdy zapisany hash, także
  nieudanych pobrań; jawne ponowne pobranie zachowuje stare potwierdzenie i koreluje nową próbę.
  Usunięcie subskrypcji nie usuwa potwierdzenia. Obecność hasha w kliencie oznacza `ACCEPTED`,
  nigdy kompletność pliku. `automation.py`
- `acquisition_staging.py` wylicza `temp/.acquisition/<operation_id>/data` z podanego workspace i
  nie tworzy markera runu. Ścieżki Windows i przodków od podanego katalogu w dół sprawdzaj pod kątem
  dowiązań przed I/O; junction powyżej workspace jest poza tą granicą. Helpery nie przyjmują pracy
  ani nie startują treści; każdą publikację i cleanup rozstrzyga owner.
- Publikacja selektywna zapisuje płaskie nazwy i zweryfikowane prywatne kopie przed wyłącznymi
  dowiązaniami do roota. Auto wymaga kompletnego przekazanego zestawu; istniejące zlecenia
  deduplikują przyjęcie po restarcie. Scalanie wyników workera zachowuje publikacje i manifesty
  zapisane przez ownera. Cleanup wymaga zwolnienia przez managera oraz zgodnej tożsamości pliku i
  skrótu w roocie albo w dowiedzionym miejscu `ReadyStore`; niedowiedzione oryginały zostają w
  stagingu. Udany cleanup zapisuje się także, gdy chronione pliki zostały, więc polling ich nie
  hashuje ponownie. Dowody kompaktuj dopiero, gdy cleanup potwierdzi brak katalogu operacji;
  chronione oryginały zachowują manifest i dowody publikacji. Usuwane są tylko pliki manifestu i
  puste katalogi; prawdziwe błędy I/O ponawiają się w procesie w ograniczonym budżecie, potem po
  restarcie. Oczekiwanie na zwolnienie lub odroczoną relokację nie jest błędem; ponowienia stoją,
  gdy klient nie może postępować (zewnętrzny, przejęty, zamknięty), i wracają przy pollingu,
  `ready_retry` albo restarcie. Przekazany zestaw nie potrzebuje oryginałów ze stagingu do
  ukończenia transferu; brak opublikowanych plików przed przetwarzaniem daje `publication_missing`
  bez blokowania zwolnienia pozostałych odcinków. Rekordy schematu 3 sprzed `manifest`, `cleaned` i
  `publication` pozostają czytelne. `automation.py`, `acquisition_staging.py`, `watch_state.py`

## Katalog wydań i subskrypcje

- Numer odcinka widziany przez aplikację to `choice.episode`, nigdy `choice.name.episode`:
  `read_episode` interpretuje nazwę w `SeasonContext` (indeks sezonu, offset, liczba odcinków).
  Nazwa ze znacznikiem sezonu (`name.season` albo `season_hint(series)`) zachowuje numer i dostaje
  `other_season`, gdy znacznik wskazuje inny sezon; bez znacznika numer powyżej offsetu to numeracja
  absolutna (`absolute`), a poniżej offsetu — inny sezon. `acquisition.py`
- `catalog_releases` rozdziela powody pominięcia: `hidden` (poniżej `min_resolution`), `excluded`
  (dubbing i brak języka napisów w indeksie), `filtered` (paczki i numery spoza zakresu). Klucz
  grupy to seria złożona do liter, cyfr i spacji (`normalize_series`), więc wersje z dwukropkiem i
  bez są jedną grupą z etykietą pierwszego zapisu. Kolejność grup ma jedno źródło, `order_groups`;
  ekran nie powtarza tej reguły.
- `matches_title` porównuje zbiory `title_forms`: zapis wprost, bez znacznika sezonu i `base_title`
  (bez sezonu i podtytułu po `" - "`, `" -"`, `":"` albo `" –"`), więc `Solo Leveling` trafia w alias
  `Solo Leveling Season 2 -Arise from the Shadow-`. `acquisition.py`
- `search_title` pyta tytułem romaji i angielskim; przy zakresie do `MAX_EPISODE_SPAN` odcinków
  dokłada zapytania po numerze (`"{base} - 01"`, przy sezonie > 1 także `"{base} S02E01"` i numer
  absolutny) tylko dla jednego zapisu tytułu (angielski, bez niego romaji), bo RSS oddaje 75
  najnowszych trafień. Potem `"{seria} {grupa}"` dla najwyżej `MAX_GROUP_QUERIES` grup wybranych po
  sumie seedów odcinków sezonu, nie po dacie (wieloletni uploader nie wypada za nowszymi). Budżet `MAX_REQUESTS` liczy żądania HTTP: zapytanie
  tytułem lub numerem kosztuje dwa (obie kategorie), grupa jeden — tylko w kategorii, w której ją
  widziano (`fr` → `1_3`, reszta → `1_2`). Scalanie po `info_hash` casefold, pierwszy wpis wygrywa.
- `season_context` liczy sezony, nie wpisy: `PrequelEntry.cour` (`Part N`/`Cour N`) podnosi offset,
  nie indeks, a kandydat będący cour zostaje w sezonie poprzednika. `acquisition.py`,
  `services/catalog/anilist.py`
- Subskrypcje żyją w `WatchState.subscriptions` jako `SubscriptionRecord`; wiersze, limit
  `MAX_SUBSCRIPTIONS` (100) i kolejność listy (`display_order`: problem, termin, bez terminu,
  pauza) mają jedno źródło w `subscription_targets.py`; tam też są reguły celów (`cut_point`,
  `is_target`, `merge_listing`) i terminów (`next_search_at`, `next_check_at`). Owner obsługuje
  `subscriptions_list`, `subscription_get`, `subscription_add`, `subscription_check` i
  `subscription_pause/resume/remove/restore`; każdy inny rodzaj `subscription*` to
  `UNKNOWN_COMMAND`. Mutacja zapisuje receipt razem ze stanem. Sprawdzenie biegnie w puli I/O,
  jedno na subskrypcję, z izolacją wyjątków; jeden `read_listing` (ze zapisanym mapowaniem jako
  fallback) zasila `prepare_episode(mapping=…)` każdego celu. Wynik trafia do `last_check` i
  `decisions.jsonl`; `checked_at` zmienia tylko udane sprawdzenie. Bez `ANISHIFT_SUBSCRIPTION_SHADOW`
  owner przyjmuje próbę przez `_admit_episode` z receipt `sub:{id}:{numer}:{próba}`, zapisując cel
  `attempting` w tym samym zapisie; tryb cienia tylko proponuje. Każdy `_save` rozlicza cele
  (`settle_target`) na przypisaniach, zamyka skończone próby (anulowanie własnego transferu albo
  wycofanie zakresu współdzielonego), a ostatni spełniony cel sezonu zakończonego przenosi rekord do
  Historii. Cel spełnia dopiero przekazany zestaw (`handed_off`), ręczne zamówienie wygrywa (`manual`).
  Kontrola H2 (`download_verification.py`) biegnie przed nazwaniem plików na wideo ze stagingu;
  `media_probe` dostarcza `AppService.media_probe` (bez importu `services` w CLI), a sprawdzony
  `verified_stamp` trafia do `copy_staged(expected=)`. Odrzucenie zamyka próbę, brak sondy lub
  błąd po jednym ponowieniu daje `verification_skipped`. `removed_subscription` trzyma jedną
  usuniętą subskrypcję dla Ctrl+Z; przywrócenie odmawia `subscription_exists` albo
  `subscription_limit` i zachowuje ją. Wznowienie czyści `pause_reason`. `automation.py`
- `config/subscriptions.json` jest zamrożonym plikiem poprzedniej wersji: owner go nigdy nie
  zapisuje, a `subscriptions.py` służy tylko do jego dekodowania (schemat 1-4). Migracja stanu do
  schematu 4 przenosi go czystym `subscription_migration.migrate` do rekordów i `legacy_orders`
  (referencje konfliktów starych zamówień) i rozlicza oczekujące receipt dawnych poleceń
  subskrypcji. Wynik powstaje i przechodzi walidację przed kopiami; uszkodzony lub nieczytelny plik
  daje `ConfigError` `CONFIG_INVALID` z podpowiedzią przywrócenia kopii, bez zmiany obu plików.
  `watch_state.py`, `subscription_migration.py`
- Pobranie starej subskrypcji nie ma zdalnego ponowienia z Historii (`legacy_subscription_retry`);
  lokalne wznowienie i przebudowa działają. Ręczne `download` zapisuje receipt i hashe przed
  wysłaniem. Panel prowadzi wyszukiwanie i odczyty katalogu przez ownera. `automation.py`
- `RequestControl` opakowuje wspólny transport HTTP metadanych i qBittorrenta: liczy rzeczywiste
  wywołania, współdzieli aktywne odczyty i blokady dostawców; trwałe terminy blokad zapisuje owner.
  Budżet operacji obejmuje zagnieżdżone zapytania, bez retry transportu. `services/http_requests.py`

## Workspace, planowanie i wykonanie

- Discovery skanuje root rekurencyjnie: pomija `temp/` bezpośrednio pod rootem, pliki i katalogi od
  kropki i nie wchodzi w dowiązania. ID grupy liczy się z katalogu względem roota i stemu, więc
  `A/01.mkv` i `B/01.mkv` to dwie grupy, a plik w roocie zachowuje dotychczasowe płaskie ID.
  `discovery.py`
- ID grup i artefaktów powstają wyłącznie z normalizowanych ścieżek względnych; plik spoza
  workspace używa znormalizowanej ścieżki zewnętrznej tylko jako wejścia stabilnego skrótu. Nie
  używaj `hash()` ani losowego UUID.
- `watch.py` sprawdza stabilność pliku, `needs_work` i `WatchLedger`; dostępność źródła deleguje do
  `platform/directory_watch.py`, który otwiera plik ze współdzieleniem wyłącznie odczytu: blokuje
  aktywnych writerów, dopuszcza odtwarzacz i pliki tylko do odczytu. Fasada eksportuje
  `SCAN_INTERVAL_S` i `WatchLedger`.
- `AppService.discover()` jest serializowane (`_discover_lock`); oczekiwanie sprawdza anulowanie,
  także w prewarmie Home. Bez `changed_paths` uzgadnia pełną listę plików, z listą zdarzeń
  aktualizuje `DiscoveryIndex` bez przechodzenia reszty. `WorkspaceInspector` zachowuje inspekcję
  niezmienionych grup i katalogi ścieżek niezmienionych mediów, także po dodaniu napisów; usunięte
  grupy wypadają z cache. Nie dodawaj osobnego cache w UI. `service.py`, `discovery.py`,
  `inspection.py`
- Produkcyjne `discover()` przygotowuje brakujące narzędzia przed probe przez callback z
  `bootstrap.py` i istniejący instalator: MKV wymaga MKVToolNix i FFmpeg, MP4/audio FFmpeg, sam TXT
  lub napisy nic nie instalują. Przygotowanie jest ciche dla terminala; konstruktory i renderer nie
  pobierają plików.
- `WorkspaceInspector.inspect()` sonduje grupy równolegle (`_MAX_INSPECTION_WORKERS`), bo każda to
  osobny `mkvmerge`. Kolejność grup i ostrzeżeń pozostaje kolejnością discovery.
- `SOURCE` ma `planned_destination == path`, `INTERMEDIATE` nie ma trwałego celu, a `DURABLE`
  dostaje `planned_destination` przed wykonaniem.
- `AUTO` nie zawiera ręcznych artifact/track ID. `MANUAL` wskazuje artefakt albo osadzoną ścieżkę
  danego rodzaju, nigdy oba.
- `ExecutionPlan.tasks` musi wejść w porządku `stable_topological_order()`, stabilnym względem
  naturalnie ułożonego wejścia, więc taski grupy `2` nie przeskoczą za grupę `10` przez hash w
  `task_id`. Każdy produkowany artefakt ma jednego producenta.
- Wykonywalny plan nie zawiera `MISSING` bez producenta. Task produkuje wyłącznie `MISSING` o
  lifetime `INTERMEDIATE` albo `DURABLE`, a parametry odpowiadają jego `TaskKind`.
- Worker dostaje w `ArtifactSnapshot` gotowe wejścia i niezmienne deskryptory planowanych wyjść i
  zwraca `TaskResult`; mutowalny store pozostaje prywatny dla schedulera.
- `ABSENT` jest poprawne tylko dla nieźródłowego `DISPLAYED_PL` bez ścieżki runtime. Udana
  klasyfikacja i pusty writer napisów wyświetlanych ustalają brak; konwersja, publikacja i
  kompozycja go przenoszą, a `require_ready` pozostaje ścisłe. `RunJournal` zachowuje brak bez dowodu
  pliku, także przy jawnym wykonaniu zapisanych podziałów. Auto używa migawek dziennika
  zweryfikowanych w inspekcji tła dla niezmienionych źródeł; o użyciu decydują rewizje dziennika i
  bieżące brakujące produkty. Ostrzeżenia wyniku wyjaśniają pominięcia. Puste przebiegi samych
  napisów wyświetlanych nie tworzą wpisu Biblioteki, a regeneracja zachowuje istniejący dobry wynik.
- Auto wymagające osadzonego audio i napisów z jednego MKV planuje jeden `EXTRACT_TRACKS`; handler
  uruchamia jeden `mkvextract --gui-mode` i przekazuje każde prawdziwe `#GUI#progress N%` bez
  uśredniania. Pula ekstrakcji ma rozmiar `min(file_count, round(sqrt(cpu_count)) + 2)`.
- LLM wykonuje gotowe pliki równolegle dokładnie do `llm_max_concurrency` (1-16); scheduler nie
  przycina tej liczby drugi raz. TTS syntetyzuje jeden plik naraz bez zmniejszania
  `tts_request_concurrency` profilu; audio może pracować równolegle z następną syntezą.
- `GraphCoordinator` przyjmuje wiele niezależnych kontekstów planów (`RunRequest` → `RunHandle`).
  Kontekst ma własny plan, sesję, handler, emitter, `ArtifactStore`, cancellation i
  `NaturalOrderGate`; wspólne są tylko kolejki gotowych tasków per zasób, executory i limity z
  `limits_provider()`. `GraphScheduler.run()` to adapter jednego planu: prywatny koordynator,
  `submit`, czekanie na wynik i zawsze `close()`. Błąd pętli koordynatora
  anuluje tokeny wszystkich kontekstów przed joinem executorów i wraca przez `RunHandle.result()`.
- Element wspólnej kolejki to `(rank, sequence, task_index, run_id, task_id)`, `rank` = 0 dla
  `RequestOrigin.USER` i 1 dla `BACKGROUND`. Wybór następuje przy realnie wolnym slocie, a liczba
  wysłanych tasków per zasób nie przekracza `worker_limit` (bez zapasu `max_pending_per_resource`).
  Limity pochodzą z `ResourceLimits` (`plan.settings` tylko dla domyślnego profilu tłumaczenia), pula
  ekstrakcji z liczby grup ekstrakcyjnych WSZYSTKICH aktywnych kontekstów. `scheduler_contracts.py`
- `RequestOrigin` określa priorytet, a `RunRequest.automatic` podporządkowuje plik wyjątkowi Auto
  jego katalogu: wyłączony katalog zatrzymuje kolejne taski automatycznego zlecenia, ale jawne
  zlecenie tego pliku działa. `BACKGROUND` zawsze podlega temu wyjątkowi. `scheduler_runtime.py`
- Wątek `anishift-coordinator` istnieje tylko, gdy koordynator ma zlecenia: `submit` go startuje,
  pusta runda zamyka executory i kończy wątek, `close()` anuluje resztę i go dołącza. Bezczynny
  koordynator nie budzi się, także gdy czeka na pracujący task — bez pollingu (licznik `wakeups`).
- Blokada docelowego produktu odkłada ponowienie atomowego `replace` w koordynatorze bez usypiania
  całej koordynacji: inne grupy nadal raportują postęp i kończą, a każda próba sprawdza cancellation
  i generację sesji. `scheduler.py`, `scheduler_runtime.py`
- `AppService` prowadzi rejestr aktywnych runów: `submit_plan` nie blokuje, `execute` to
  `submit_plan(...).result()`, a `cancel(run_id)` działa dla każdego aktywnego runu. Druga praca nad
  tą samą grupą dostaje `RunConflictError`, a `cleanup_orphaned_temp` komplet aktywnych `run_id`.
  Sesję zamyka wątek domykający run bez prefiksu `anishift-`, zarezerwowanego dla pul do dołączenia.
- `AppService.execute()` po przerwaniu anuluje run i CZEKA na domknięcie kontekstu, zanim przekaże
  wyjątek — inaczej taski, procesy narzędzi i `temp/` przeżyłyby wywołującego. `_finish_run` zawsze
  zamyka handler i sesję i rozwiązuje `RunHandle`, bo nierozwiązany handle wiesza `execute`.
- `AppService.reload_preferences()` wczytuje ponownie `settings.json` i `.env` pod `_run_lock`;
  trwające zlecenia zachowują snapshot ustawień z planu. `service.py`

## Testy

```bash
uv run pytest tests/application -v
```
