# application

Czysta warstwa produktu i use case'ów współdzielona przez CLI i testy.

## Kierunek zależności

- `artifacts.py`, `control.py`, `intents.py`, `planning.py`, `selection.py` i `planner.py` nie importują I/O,
  `anishift.services`, `anishift.config` ani CLI.
- Kontrolowane I/O należy do `discovery.py`, `inspection.py`, `publisher.py`, `sessions.py`, `watch_state.py`,
  handlerów, fasady `service.py` i `acquisition.py`. `acquisition.py` używa wstrzykniętych protokołów
  `TorrentSource`/`TitleCatalog`/`TorrentClient`; typy z `services.torrents`/`services.catalog` importuje tylko pod
  `TYPE_CHECKING`, poza czystymi `season_hint`/`strip_season`, adapterem referencji Nyaa i rekonstrukcją `Release`
  dla jawnego ponowienia. `library.py` importuje tylko czyste funkcje `services.torrents.names` dla `library_label`
  i `series_title`. Decyzje produktowe zostają w plannerze; staging publikuje `scheduler_runtime.py`.
- Nazwy trwałych produktów pochodzą wyłącznie z `products.py`; nikt inny nie zapisuje literałów `.pl`, `.spoken.pl`,
  `.displayed.pl`, `.pl.mkv`, `.pl.mp4` ani `.m4a`.
- CLI używa publicznej fasady `anishift.application`, nie wewnętrznych helperów I/O ani schedulera.
- Oczekiwany konflikt wejścia to `PlanProblem`; `PlanningError` oznacza uszkodzony kontrakt albo graf.

## Owner i stan rezydenta

- `AutomationOwner` (`automation.py`) jest jedynym autorem `WatchState`: wątek `anishift-owner` zdejmuje polecenia z
  kolejki, `preview` idzie na pulę `anishift-owner-io` (`set_auto` nie czeka na skan). Pętla śpi na kolejce bez
  timeoutu — bezczynny rezydent nie pracuje.
- Polecenie mutujące zapisuje stan RAZEM z `CommandReceipt` PRZED pozytywną odpowiedzią; nieudany zapis to `INTERNAL`
  bez skutku, powtórzony `command_id` zwraca zapisany wynik. `start` zapisuje `ProcessingRequest` z receipt przed
  `submit_plan`; późniejsza awaria daje `FAILED`, a ponowienie ten sam `run_id`.
- `RunJournal` zapisuje pozostały graf i potwierdzenia publikacji; niepewne operacje zdalne po przerwaniu (awaria,
  zabicie procesu) wymagają jawnego wznowienia, bez automatycznego powtarzania opłat. Wyjątek: task przerwany przez
  zamknięcie rezydenta kończy się po anulowaniu, więc nie jest niepewny i wznawia się sam (przerwane wywołanie płatne
  idzie od nowa). Gdy zapis `interrupted` zawiedzie, znak `inflight` zostaje i obowiązuje jawne wznowienie.
- Rezerwacje należą do sesji klientów jednej instancji: owner porzuca je przy wczytaniu stanu (także gdy zapis
  sprzątania zawiedzie) i po rozłączeniu panelu, które unieważnia też podglądy.
- Zdarzenia plików scalają się w jednym powiadomieniu; ponad 4096 ścieżek zastępuje pełne uzgodnienie. Inspekcja w
  puli I/O, decyzja o Auto po stabilizacji. Zmiana źródeł lub produktów unieważnia podgląd grupy; aktualność
  sprawdza `source_fingerprint` (kilka `stat`), nie pełny `discover()`.
- Sygnał zakończenia omija zapis receipt i zawsze zaczyna drain, nawet gdy zapis stanu zawodzi. Pętla kończy się
  dopiero przy `_drained` (brak aktywnych runów, nierozliczonych zleceń, dopuszczeń pobrań i wyników z puli I/O);
  samo `active_run_ids()` nie wystarcza, bo run znika z rejestru fasady przed zapisem stanu końcowego.
- `shutdown` zamyka dopuszczanie tasków i przerywa aktywne: `drain` anuluje osobny token każdego wysłanego taska
  (rodzicem jest token runu), handler kończy się jak przy anulowaniu, task dostaje `CANCELLED` „Interrupted by
  shutdown”, a cały run `paused` → `RequestState.PAUSED`, wznawiany sam przy następnym starcie. Przerwanie czyści znak
  `inflight` w `RunJournal` (`interrupted`), więc recovery nie uznaje go za niepewną operację zdalną. Task, który mimo
  przerwania zwrócił wynik, jest zatwierdzany normalnie; gotowy wynik nie przepada. Anulowanie
  użytkownika (X) anuluje token runu i zostaje `CANCELLED` (blokuje Auto); `pause_runs` niczego nie przerywa. Staging
  zatrzymanych runów jest chroniony przed cleanup. `scheduler.py`, `recovery.py`, `service.py`, `sessions.py`
- `ProcessingRequest` zachowuje pełny `RunSettingsSnapshot`, `GroupIntent` i `RebuildRequest`; listy z JSON wracają do
  krotek, pola z segmentem sekretu są odrzucane, stare zlecenia bez `intents` się wczytują. `ACCEPTED` może obejmować
  wykonujące się taski; aktywność dowodzą publiczne zdarzenia postępu, `run_progress` ma też próby terminalne.
- `recipe_update` zmienia tylko zwalidowaną różnicę i zapisuje receipt z `WatchState.recipes`. Video to `AutoPreset`,
  subs dziedziczy po video, cover po audiobook. Podgląd utrwala preferencje receptury z planem; dopuszczenie i
  recovery nie przepisują starszego planu bieżącymi preferencjami.
- `AutomationPolicy.effective_auto`: globalne wyłączenie wygrywa, inaczej najbliższy jawny wyjątek katalogu w górę do
  roota (`""`). Rezerwację kluczuje `group_id` (`fingerprint` tylko unieważnia podgląd), marker ręcznej obsługi —
  `(group_id, source_fingerprint)`, więc publikacja produktu nie unieważnia decyzji użytkownika. `control.py`
- Pauza (`auto_enabled == False`) blokuje powtórki i automatyczne dopuszczenie przez `set_background_admission`, nigdy
  `pause_runs`; pracy użytkownika nie odrzuca (Start, Ręczny, ponowienie, ponowne pobranie, D). Pobranie jest ręczne,
  gdy `AcquisitionConfirmation.manual` dowodzi pochodzenia USER bez subskrypcji albo jawnego ponowienia; ręczne
  transfery, partie, metadane, selekcja i publikacja trwają w pauzie, a ich pliki idą z `explicit=True`,
  `automatic=False`. Sam priorytet USER świeżego pliku nie zwalnia z pauzy. Wznowienie zachowuje deduplikację i
  restartuje tylko automatyczne transfery wstrzymane pauzą.
- Klasyfikacja ponowienia należy do ownera: wznowienie zachowuje cały zakres, lokalna przebudowa idzie do Ręcznego,
  ponowne pobranie zapisuje skorelowany zamiar przed wysłaniem. `AcquisitionConfirmation` zachowuje tylko
  zweryfikowane liczbowe ID Nyaa i oryginalny tytuł; URL odtwarza `services/torrents/nyaa.py`.
- `WatchStateStore` zapisuje atomowo (`state.json.tmp` + `fsync`, kopia czytelnego `state.json` do `.bak`, `replace`).
  Uszkodzony JSON, nieznany klucz i nieobsługiwana wersja dają `ConfigError`, nigdy pusty stan; brak pliku to stan
  domyślny. Migracja starszej wersji idzie raz z kopią `state.json.v<wersja>.bak`; przed pierwszym zapisem schematów
  3/4/5 kopiuje `state.json` i `subscriptions.json` do `*.e2-/e3-/a1-migration.bak` (bez nadpisywania; błąd kopii to
  `ConfigError` `IO_ERROR` bez zapisu). Walidacja jest wersjonowana — pola wymagane w nowej wersji są zakazane w
  starszej, więc nowe pole to podbicie `WATCH_STATE_SCHEMA_VERSION`, walidator i migracja. Trwałe ścieżki przechodzą
  `require_relative_paths`. Nie usuwaj dowodów recovery (downgrade). Testy: `test_watch_state.py`, `test_subscription_migration.py`.
- `config/subscriptions.json` jest zamrożony: owner go nie zapisuje, `subscriptions.py` tylko dekoduje, migracja do
  schematu 4 (`subscription_migration.migrate`) waliduje wynik przed kopiami; uszkodzony plik to `CONFIG_INVALID`.

## Biblioteka, gotowe wyniki i historia

- Powiadomienie o wyniku wynika z zapisanego ukończenia i pochodzenia, nigdy z samego `GROUP_FINISHED`; `notified`
  chroni jednokrotną ofertę. Callbacki sprawdzają bieżące potwierdzenia i tożsamość plików, nigdy Historię; nie
  czekają na blokadę discovery fasady na wątku ownera.
- `history.py` to nieautorytatywny JSONL ownera (30 dni); awarie nie zmieniają dopuszczenia, deduplikacji ani
  recovery. Naprawiany jest tylko urwany ogon; uszkodzony środek daje odmowę odczytu Historii.
- `ReadyStore` przenosi grupę do `ready/` wyłącznym dowiązaniem i usunięciem starej nazwy na tym samym woluminie; znany
  torrent musi wcześniej zwolnić pliki, blokada relokacji chroni oba ID grupy przed Auto. Nie przenoś plików z renderera.
- Odcinek wiąże z pobranym zestawem `downloaded_episodes` (`EpisodeAssignment.group_id` = `ReadyGroup.set_id`).
  `LibrarySet.series/season/episode` dokłada `name_series` przy emisji, nigdy w zapisanym stanie; zestaw ręczny ich nie ma.
- Usuwanie z Biblioteki pomija pobranie tylko w `COMPLETE` z receipt managera dowodzącym zwolnienia (odczyt w puli
  I/O, ponowne sprawdzenie przed przyjęciem). Undo zapisuje przyjęcie `PendingDeletion.restore` i start każdego
  pliku przed skutkami natywnymi; `DeletionRestore.unsettled` chroni nierozstrzygnięte skutki po restarcie.
  `recycler`/`restorer` to fabryki sesji: jeden proces pomocniczy na zestaw, zapis per plik bez zmian.

## Pobieranie odcinków

- Kontrola po pobraniu subskrypcji (`_check_episode`) odrzuca wydanie z werdyktem napisów `none` (brak ścieżek tekstowych
  albo same szyldy, także niepewnie) przed nazwaniem pliku, również w trybie `record_only`; subskrypcja bierze następne
  wydanie w budżecie prób, właściciel dostaje toast. Rolę ścieżki liczy jedna reguła `selection.subtitle_role`;
  pominięta kontrola (brak sondy lub binarki) nigdy nie odrzuca.
- `episode_identity.py` posiada zamrożoną klasyfikację tożsamości; `episode_selection.py` jej czysty builder wejścia,
  projekcje, fakty wydań i ranking. Produkcja przekazuje tylko `target` i `candidate`; cel buduj z pełnego
  `FranchiseGraph` i surowych odcinków ani.zip, nigdy z wyświetlanej franczyzy. Zmiana klasyfikacji: minimalny
  przypadek w `tests/fixtures/acquisition/identity-regressions.json` i procedura
  `docs/work/08-acquisition/plans/07-episode-identity-integration.md` §10.6; zmiana golden wymaga niezależnego review. Nigdy nie zamieniaj
  wyjątku programistycznego w niepewny werdykt.
- `AcquisitionService.franchise/episodes/offer` to odczyty katalogu przez IPC ownera, bez przyjęcia i receipt; awaria
  harmonogramu zachowuje mapowanie z ostrzeżeniem. Reguły sugestii: `test_episode_selection.py`, `test_acquisition.py`.
- `admit_episode` to synchroniczna bramka: jeden zapis `ADMITTED` z receipt, bez skutków w qB; wysyłkę przejmuje
  cykl transferów. Nowy klucz dołącza do jedynego aktywnego transferu selektywnego swojego hasha, po
  `COMPLETE`/`FAILED` dostaje nową operację. Przed ponownym dodaniem hasha zwolnij poprzedni wpis klienta.
- Konflikt liczy `control.episode_conflict`. `download` nie ma klucza odcinka (brak nazwy pliku przed przyjęciem),
  dostaje `LegacyScope(ID, numer lokalny)`; offset odejmuje się tylko od surowego numeru bez sezonu.
- `episode_download` zapisuje receipt partii przed odczytem źródeł, każde przyjęcie ma własny receipt; restart
  oznacza niedokończone partie jako przerwane. Autorytatywne są trwałe receipt, nie zdarzenie `episode_batch`. Pola
  `reason` zostają `str`, bo historyczne receipt mogą mieć dowolną wartość. `episode_commands.py`
- Oferta: jedna na sesję katalogu, praca w `_active_io`, rewizje trzyma owner. `episode_choose` wybiera przez
  `offer_id/revision/info_hash/path`; zmiana reprezentanta, oceny, konfliktu lub potwierdzeń daje `offer_changed`,
  same seedy i jakość nie. Jawny wybór niepewnego/niezgodnego wymaga osobnego potwierdzenia.
- `episode_states` nie mutuje stanu. `episode_file_choose` czyta świeżą mapę plików, sprawdza rewizję i dokładne
  index/path/size, zapisuje wybór z receipt przed selekcją i po odczycie sprawdza receipt znów na wątku ownera.
  Sprawdzaj rewizję selekcji i przypisanie, nie całe potwierdzenie (sam znacznik czasu nie unieważnia).
- Wybór pliku w `transfers.py`: najpierw liczba plików zgodnych na pełnych ścieżkach (więcej niż jeden = pusta
  selekcja), potem dokładna nazwa, potem jedyny zgodny; `fileIdx` źródła nigdy nie wybiera. Wideo odcinków liczy
  jedno `episode_identity.episode_video_count`, dodatki rozpoznaje `is_extra_path`; towarzyszące wymagają tego
  samego katalogu i stemu. Próba subskrypcji odrzucona przez `metadata_check` zapisuje `EpisodeAssignment.stopped`.
- Cykl selektywny (`AcquisitionService.selective`): `ADMITTED` → trwałe `PENDING_SEND` → `add_metadata` → `ACCEPTED`
  (wyjątek add → `UNCERTAIN`). Przypisania z podniesionym `selection_revision` zapisuj PRZED `select_files`;
  `_apply_selection` odrzuca mapę o innej rewizji. Start wymaga potwierdzonej selekcji, niepustego zestawu, stanu
  stop i braku żądanego stop/cancel; wynik workera scala się tylko przy niezmienionym `_selection_basis`, a
  `_may_settle` odrzuca go po stop/cancel z rundy.
- Przed KAŻDYM startem i resume selektywnym owner czyta klienta na świeżo (`_mismatched`: `save_path`, mapa
  index/path/size, priorytety vs `wanted_files`) — cache inspektora nie wystarcza; niezgodność daje
  `_SELECTION_MISMATCH`. Tuż przed startem znów `_may_start_selection`; resume chroni `_mark_sent`.
- qBittorrent gubi priorytety przy wyłączeniu: start ownera i pierwsza udana runda po nieudanej
  (`_recheck_selections`) oznaczają potwierdzone `ACCEPTED` jako `_unverified` i naprawiają przez
  `_apply_selection(restoring=True)` + zwykły start (pauza nadal blokuje nieręczne).
- Rekord selektywny nie przechodzi w `COMPLETE`, dopóki selekcja nie jest zastosowana i każde przypisanie nie ma
  `handed_off`. Timeout metadanych liczy się w pamięci na próbę; jawne resume zaczyna nową (`restart_idle`). Resume
  bez potwierdzonej selekcji nie wysyła `resume`. `PENDING_SEND` uzgadnia się bez ponownego add (`_SEND_CHECKS`, potem
  `UNCERTAIN`). Pauza zatrzymuje tylko nieręczne z `applied_revision > 0`. Testy: `test_selective_lifecycle.py`.
- Potwierdzony transfer nieobecny w udanym odczycie klienta → `FAILED` `removed_from_client`; `TransferInspector`
  wymaga trzech kolejnych udanych odczytów bez hasha. `protected_assignments` współdzielą konflikty i status;
  usunięcie zwalnia tylko przyjęcia bez publikacji. Obecność hasha w kliencie znaczy `ACCEPTED`, nie kompletność.
- `AcquisitionConfirmation` zapisuje się przed add; niepewne przekazanie blokuje ponowne dodanie hasha i innej wersji
  numeru, zwykłe dopuszczenie chroni każdy zapisany hash. Usunięcie subskrypcji nie usuwa potwierdzenia.
- `acquisition_staging.py` wylicza `tmp/.acquisition/<operation_id>/data` i sprawdza dowiązania przed I/O; nie
  przyjmuje pracy ani nie startuje treści — publikację i cleanup rozstrzyga owner.
- Publikacja selektywna zapisuje zweryfikowane prywatne kopie przed wyłącznymi dowiązaniami do roota. Cleanup wymaga
  zwolnienia przez managera i zgodnej tożsamości oraz skrótu; niedowiedzione oryginały zostają w stagingu, dowody
  kompaktuj dopiero po potwierdzonym braku katalogu operacji, usuwaj tylko pliki manifestu i puste katalogi.
  Ponowienie relokacji ma osobny termin `_ready_retry_at`, nie `_transfers_at`. Testy: `test_selective_publication.py`.

## Katalog wydań i subskrypcje

- Numer odcinka aplikacji to `choice.episode`, nigdy `choice.name.episode`: `read_episode` interpretuje nazwę w
  `SeasonContext`. `season_context` liczy sezony, nie wpisy (`PrequelEntry.cour` podnosi offset, nie indeks).
- `catalog_releases` rozdziela `hidden`, `excluded` i `filtered`; klucz grupy daje `normalize_series`, kolejność grup
  jedno źródło `order_groups` — ekran jej nie powtarza. `matches_title` porównuje zbiory `title_forms`.
- `search_title` ma budżet `MAX_REQUESTS` w żądaniach HTTP (`MAX_GROUP_QUERIES`, `MAX_EPISODE_SPAN`); scalanie po
  `info_hash` casefold, pierwszy wygrywa. Testy: `test_acquisition.py`, `tests/integration/test_search_pipeline.py`.
- Samodzielny 1. sezon bez S/E w ani.zip (`_first_season`) dostaje `first_season_numbering`; sugestią może być tylko
  wydanie zgodne (`EpisodeOffer.derived_numbering`).
- Subskrypcje żyją w `WatchState.subscriptions`; wiersze, limit `MAX_SUBSCRIPTIONS`, kolejność, cele i terminy mają
  jedno źródło `subscription_targets.py`. Nieobsługiwany rodzaj `subscription*` to `UNKNOWN_COMMAND`; mutacja zapisuje
  receipt ze stanem. Sprawdzenie biegnie w puli I/O, jedno na subskrypcję, z izolacją wyjątków; pamięci źródeł są w
  procesie (restart je czyści). Wybór robi czysty `subscription_choice.choose`.
- `checked_at` zmienia tylko udane sprawdzenie; niedostępność źródeł lub wyjątek jednego celu nie przerywa rundy.
  „Pobierz teraz” (`PolishSkip`) rozlicza tylko snapshot rundy — zegar ani `checked_at` nie dowodzą obsługi prośby.
  Tryb cienia (`subscription_shadow`) tylko proponuje. Każdy `_save` rozlicza cele (`settle_target`); cel spełnia
  dopiero `handed_off`. Próba zatrzymana po metadanych nie wyczerpuje celu; próg podnosi tylko martwa próba. Kontrola
  pobrania (`download_verification.py`) biegnie przed nazwaniem plików, `media_probe` daje `AppService.media_probe`
  (CLI nie importuje `services`). Testy: `test_subscription_owner.py`, `test_subscription_scenarios.py`.
- Powiadomienia subskrypcji mają jeden kanał: trwały `WatchState.notified`, wpis `escalation` w `decisions.jsonl` i
  `_publish_notification`. Klucz trafia do `notified` w tym samym zapisie, publikacja po udanym zapisie. Polskie
  zdania składa jedno `episode_commands.notice_text`. Rejestr decyzji nie zawiera nazw ani URL-i.
- Stara subskrypcja nie ma zdalnego ponowienia z Historii (`legacy_subscription_retry`). Ręczne `download` zapisuje
  receipt i hashe przed wysłaniem.
- `RequestControl` opakowuje wspólny transport HTTP: liczy wywołania, współdzieli odczyty i blokady dostawców; trwałe
  terminy zapisuje owner, callback cooldownu tylko kolejkuje zapis (cooldown po końcu pętli zostaje w pamięci).
  Transport zamyka `cli/watch.py`. `services/http_requests.py`

## Workspace, planowanie i wykonanie

- Discovery skanuje rekurencyjnie, pomija `tmp/` pod rootem, pliki/katalogi od kropki i dowiązania. ID grup i
  artefaktów tylko z normalizowanych ścieżek względnych (katalog + stem; plik w roocie ma płaskie ID); nie używaj
  `hash()` ani losowego UUID. `watch.py` deleguje dostępność źródła do `platform/directory_watch.py`.
- `AppService.discover()` jest serializowane (`_discover_lock`), oczekiwanie sprawdza anulowanie. `WorkspaceInspector`
  trzyma cache niezmienionych grup — nie dodawaj cache w UI; równoległa inspekcja zachowuje kolejność discovery.
  Produkcyjne `discover()` cicho instaluje brakujące narzędzia przez callback z `bootstrap.py` (MKV: MKVToolNix i
  FFmpeg; MP4/audio: FFmpeg; TXT i napisy: nic); konstruktory i renderer nie pobierają plików.
- `SOURCE` ma `planned_destination == path`, `INTERMEDIATE` nie ma trwałego celu, `DURABLE` dostaje cel przed
  wykonaniem. `AUTO` nie zawiera ręcznych ID; `MANUAL` wskazuje artefakt albo osadzoną ścieżkę, nigdy oba.
- `ExecutionPlan.tasks` w porządku `stable_topological_order()` (grupa `2` przed `10`); każdy artefakt ma jednego
  producenta, plan nie zawiera `MISSING` bez producenta. Worker dostaje `ArtifactSnapshot` i zwraca `TaskResult`;
  mutowalny store zostaje prywatny. `ABSENT` jest poprawne tylko dla nieźródłowego `DISPLAYED_PL` bez ścieżki runtime.
  Split czytający SRT (źródło SRT albo wyjście SRT) nie ma warstwy ekranowej: planner od razu tworzy `ABSENT` (bez
  splitu i tłumaczenia, ostrzeżenie `displayed_cues_absent`), ASS rozstrzyga split w runtime; ABSENT w planie daje
  notkę w `RunResult`.
- Auto z audio i napisami z jednego MKV planuje jeden `EXTRACT_TRACKS` (jeden `mkvextract --gui-mode`, każdy
  `#GUI#progress` bez uśredniania). LLM równolegle dokładnie do `llm_max_concurrency` — scheduler nie przycina drugi
  raz; TTS jeden plik naraz.
- TTS w `runtime.py`: jeden `FfmpegClipService` jest walidatorem, assemblerem i splitterem `TtsService`. Wiedza
  „silnik czyta dokumentem” pochodzi tylko z `is_document_engine` rejestru TTS: daje `reads_document` handlera
  (łączenie kwestii urwanych i wszystkie kandydaty szyldów w batchu kwestii, czyli jeden dokument na odcinek; silniki
  „kwestia po kwestii” dostają drugi batch tylko z szyldami osiągalnymi po ułożeniu kwestii) i przebieg dokumentu w
  `_tts_config` (współbieżność 1, bez `asyncio.timeout` schedulera, bo silnik sam pilnuje terminu i sprzątania
  konta; dłuższy `shutdown_deadline_s`). `split_clip` dekoduje nagranie z jawnym `-f mp3`
  (obce bajty na początku zmylą rozpoznanie formatu), czasy ramek bierze z `utils.mp3_frames`, regułę cięcia z
  `services/audio/segmentation.py`; granice bez pauzy idą do logu jako ostrzeżenie z liczbą. `tts_clips.py`
- `build_narration_manifest` ocenia każdą kwestię osobno, nie status batcha: kwestia bez klipu kończy zadanie
  `ExecutionError` z kodem, treścią i sugestią `SpeechBatchResult.failure` (panel pokazuje tylko
  `context.message`, więc sugestia jest też w treści), szyld bez klipu (pominięty albo nieudany) wypada z manifestu z ostrzeżeniem z liczbą i grupami w
  metadanych `signs_unrecorded`, w obu ścieżkach. `tts_handler.py`
- Sesję ElevenReadera panel czyta i odświeża przez fasadę (`elevenreader_session`, `elevenreader_sign_in`);
  logowanie blokuje wątek wołający do zamknięcia okna Chrome. `service.py`
- `GraphCoordinator` przyjmuje wiele kontekstów (`RunRequest` → `RunHandle`); wspólne są tylko kolejki gotowych
  tasków per zasób, executory i `limits_provider()`. Błąd pętli anuluje wszystkie konteksty przed joinem. Kolejka
  `(rank, sequence, task_index, run_id, task_id)`, USER przed BACKGROUND, wysłanych per zasób najwyżej `worker_limit`.
  `RunRequest.automatic` podporządkowuje plik wyjątkowi Auto katalogu; `BACKGROUND` zawsze. Wątek
  `anishift-coordinator` żyje tylko przy zleceniach, bez pollingu (licznik `wakeups`). Blokada docelowego produktu
  odkłada ponowienie `replace` bez usypiania całej koordynacji.
- `AppService`: `submit_plan` nie blokuje, `execute` = `submit_plan(...).result()`, druga praca nad grupą to
  `RunConflictError`; sesję zamyka wątek bez prefiksu `anishift-` (zarezerwowanego dla pul). `execute()` po
  przerwaniu anuluje i CZEKA na domknięcie kontekstu; `_finish_run` zawsze zamyka handler i sesję i rozwiązuje
  `RunHandle` (nierozwiązany wiesza `execute`). `reload_preferences()` pod `_run_lock`; trwające zlecenia zachowują
  snapshot ustawień. `service.py`

## Testy

```bash
uv run pytest tests/application -v
```
