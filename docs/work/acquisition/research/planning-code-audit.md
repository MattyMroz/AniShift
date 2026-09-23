# Audyt kodu do planowania uproszczenia pozyskiwania

## 1. Wniosek i granica dowodu

**Należy zastąpić grupocentryczne wyszukiwanie wspólnym wyborem sezonu i odcinków, zachowując istniejącego właściciela przyjęć, kontrolę gotowości plików i pipeline.** Sama wymiana Nyaa na Torrentio nie zapewni selekcji E1+E3, poprawnego monitorowania ani czytelnego UI.

- Stan sprawdzony 2026-09-23: HEAD `0e8a6bf9194d2786d426d3f3a58f48272b3eb087`, gałąź `work/local-automation/06-efficiency`.
- Wynik to materiał do specyfikacji/masterplanu, drzewa i ASCII UI, nie zaakceptowany projekt implementacji.
- **CURRENT** oznacza kod tego HEAD; **WYMAGANIA** — ustalenia z `summary.md`; **TOUCH** — propozycje zmian; **OPEN** — decyzje nadal potrzebne.
- Wykonano inspekcję kodu, instrukcji, konfiguracji kontroli jakości i wcześniejszych raportów. Nie uruchomiono aplikacji, testów, sieci, qBittorrenta ani modeli. Nie badano danych produkcyjnych.
- Inwentaryzacja obejmuje całe `anishift/`; lektura kodu była kierunkowa, a nie linia po linii wszystkich modułów. Duże moduły czytano w zakresach związanych z kontraktami. Uciętych wyników narzędzi nie uznano za pełną lekturę.
- Zastane zmiany: `AGENTS.md`, nieśledzone katalogi tego workstreamu i `docs/work/local-automation-2/`, `session-ses_f3f3.md`. Jedynym artefaktem tego audytu jest niniejszy plik.

## 2. WYMAGANIA i konflikty z CURRENT

1. Jedna droga tytuł → sezon/część → odcinki, z akcją Download lub Subscribe; ręczne pobranie z subskrypcji używa tej samej selekcji i admission.
2. Główne Subskrypcje pokazują aktywne wpisy, zamówiony zakres, numery i stany, liczniki oraz następną emisję; zapewniają zarządzanie, usunięcie i wejście do wyszukiwarki.
3. Countdown dotyczy emisji. Po niej można nadal czekać na wydanie; nieznana data nie jest obietnicą ani dowodem braku pliku. Pobrano ≠ przetwarzanie ≠ gotowy produkt.
4. Kierunek integracji: AniList — katalog/relacje; ani.zip — mapowania/odcinki; Torrentio — kandydaci; heurystyka — tożsamość z wynikiem `match`, `mismatch`, `insufficient_evidence` i powodem.
5. Pełne polskie dialogi w napisach **lub** polskie audio mają pierwszeństwo przed typesettingiem; MultiSub jest wskazówką/fallbackiem, nie potwierdzeniem PL. NF/CR nie są wymagane.
6. Preferowane 1080p, inne wysokości dopuszczalne. Rozmiar/quality hints najwyżej słabe sygnały; bez minimum 1,4 GB, whitelisty grup ani reguły „największy wygrywa”.
7. E1+E3 z paczki wymagają jawnych, uzgodnionych indeksów qB. Deduplikacja zamiaru, elementu plikowego i zadania torrentowego to trzy różne kontrakty.
8. Wspólna droga lokalnego pliku i pobrania: watch → pipeline → biblioteka. Zachować płaski workspace, `ready/`, staging i recovery, o ile późniejsza specyfikacja jawnie tego nie zmieni.
9. Sonarr i Laya są odłożone. Stare wymaganie konkretnej grupy i ograniczone okno kalendarzowe nie stają się automatycznie nowymi wymaganiami.

CURRENT przeczy pkt 5–7: `_is_hidden` odrzuca brak rozdzielczości/<1080, `_is_excluded` odrzuca dub/brak deklaracji napisów; zakres pomija paczki. `_accept_download` deduplikuje po hashu, a `TorrentClient` nie oferuje zmiany priorytetów plików [E02–E05].
CURRENT już posiada Subskrypcje wewnątrz Panelu i odliczanie do emisji. Problemem jest także odkrywalność i niepełna projekcja, a nie całkowity brak ekranu [E10–E11].

## 3. Mapa całego pakietu i rzeczywiste pokrycie

`git ls-files -- 'anishift/*.py'` daje **350 śledzonych plików Python**, łącznie z `__init__.py`, przykładami i testami osadzonymi. Liczby poniżej są bezpośrednie dla wskazanego katalogu, bez ponownego doliczania dzieci.
Poziomy: **P** — prześledzony przepływ i kluczowe zakresy; **K** — kontrakty/reuse, wybrane typy lub granice; **I** — inwentaryzacja i instrukcje, bez audytu implementacji.

| Katalog względem `anishift/` | Pliki `.py` | Pokrycie i rola |
| --- | ---: | --- |
| root | 4 | P: `bootstrap`, `paths`; K: błędy i publiczne wejście |
| `application/` | 43 | P: acquisition/subscriptions/transfers/owner, stan, planner, service, discovery/watch, ready/recovery/library; pozostałe handlery K/I |
| `cli/` | 8 | P: resident/watch/main/control; K: run/console/exit codes |
| `cli/interactive/` | 16 | P: app/state/anime/subscriptions/prompts; K: settings/manual/progress/text input; branding I |
| `cli/interactive/assets/` | 1 | I: pakiet zasobów |
| `config/` | 9 | P: settings/user_settings/workspace; K: field catalog/access, presets, katalog modeli |
| `platform/` | 13 | P: local_control/qbittorrent_process/directory_watch; K: locks/child processes/recycle/restore; reszta I |
| `services/` | 3 | P: `http_requests`; K: wspólna granica silników |
| `services/catalog/` | 4 | P: AniList i typy katalogu |
| `services/torrents/` | 8 | P: Nyaa, nazwy/query, typy, qB; granice transportu i referencji |
| `services/media/` | 7 | K: katalog ścieżek i probe, bez pełnego audytu parserów |
| `services/extraction/` | 8 | K: protokół ekstrakcji/wyboru ścieżek, języki i oznaczenia signs |
| `services/subtitles/` | 8 | K: klasyfikacja/split/writers, nie nowe rozpoznawanie dialogów |
| `services/audio/` | 15 | K: kontrakty timeline/miksu; implementacje poza głębokim audytem |
| `services/composition/` | 9 | K: request/result i zachowanie produktów |
| `services/llm/` | 9 | K: protocol/reuse; bez porównania providerów |
| `services/llm/engines/` | 3 | I: istniejący rejestr |
| `services/llm/engines/{anthropic,deepseek,gemini,openai,openai_compatible,openrouter}/` | po 3 | I: sześć katalogów providerów |
| `services/llm/engines/palantir/` | 8 | I: poza zmianą pozyskiwania |
| `services/translation/` | 11 | K: protokół i integracja pipeline |
| `services/translation/engines/` | 1 | I: rejestr |
| `services/translation/engines/{deepl,google,llm}/` | 5 / 6 / 5 | I: bez audytu silników |
| `services/translation/engines/llm/prompts/` | 2 | I: zasoby promptów pozostają istniejące |
| `services/tts/` | 13 | K: protokół syntezy/resume, bez audytu providerów |
| `services/tts/engines/` | 1 | I: rejestr |
| `services/tts/engines/{edge,elevenbytes,elevenlabs,sapi}/` | 7 / 7 / 6 / 7 | I: cztery katalogi providerów |
| `setup/` | 4 | K: granica instalacji/doctor; bez uruchomienia |
| `text/` | 3 | K: istniejąca obsługa tekstu; bez nowego parsera UI |
| `utils/` | 8 | K: `safe_path` i helpery, nie nowa domena |
| `utils/logger/` | 13 | K: publiczna granica loggera; wnętrze I |
| `utils/logger/{examples,formatters,handlers,readers,tests}/` | 7 / 2 / 4 / 3 / 16 | I: pięć katalogów zinwentaryzowanych |
| `utils/rich_console/` | 4 | K: publiczna granica renderowania |
| `utils/rich_console/{examples,progress,tests}/` | 7 / 3 / 7 | I: trzy katalogi zinwentaryzowane |
| `utils/timer/`, `utils/timer/tests/` | 2 / 2 | I: reużycie bez zmiany |

Katalogi zasobów bez Pythona: `cli/interactive/assets/mascot/` i `mascot/idle/` (ICO/GIF/PNG), `services/translation/engines/llm/prompts/styles/` (Markdown). Dodatkowo prompty Markdown, JSON przykładów loggera i `sapi_worker.ps1` w zinwentaryzowanych katalogach. Nie analizowano binarnych obrazów ani zawartości wszystkich zasobów.
Mapa obejmuje wszystkie katalogi ze śledzonym kodem/zasobami; nie obejmuje jako kodu runtime `__pycache__`, pobranych binarek ani danych użytkownika. Liczba modułów nie jest liczbą modułów przeczytanych w całości.

## 4. CURRENT — rejestr dowodów i właścicieli

Ścieżki w tabeli są względem `anishift/`; format kotwicy: `path:symbol:lines`. Zakresy odnoszą się do zamrożonego HEAD, nie do przyszłego drzewa.

| ID | Kotwica | Fakt i właściciel |
| --- | --- | --- |
| E01 | `bootstrap.py:_acquisition_service:92–132` | Jeden composition root: Nyaa + AniList + wspólny HTTP + qB z opcjonalnym private managerem; transport retries=0. |
| E02 | `application/acquisition.py:TorrentClient:139–172; download:491–509` | Add stopped do roota, files/rename/resume; brak operacji priorytetów. Źródło i klient są wstrzykniętymi protokołami. |
| E03 | `application/acquisition.py:_merge/_is_hidden/_is_excluded:734–747` | Merge po hashu, twarde minimum/unknown resolution, wykluczenie dub i nieznanego języka napisów. |
| E04 | `application/automation.py:_accept_download:3311–3354` | Owner zapisuje receipt i `PENDING_SEND` przed efektem; `unique` i istniejące przyjęcia są kluczowane samym hashem. |
| E05 | `application/automation.py:_admit_subscription:3468–3501; _reconcile_acquisitions:3552–3566` | Ochrona hash oraz subscription/episode/repeat; obecność w qB potwierdza `ACCEPTED`, nie plik. |
| E06 | `application/control.py:AcquisitionConfirmation:275–324` | Jedno pole episode/subscription, required/complete files, layout `(index,path,size)`, repeat i Nyaa reference; brak modelu wielu intencji do jednego transferu. |
| E07 | `application/transfers.py:_inspect:211–237; _complete_files/_ready_file:309–343` | Wybrane priority>0; kontrola ścieżki/layoutu, stanów checking/moving, progress pliku, dostępności i rozmiaru. |
| E08 | `application/subscriptions.py:SubscriptionStore:417–457; _new_episodes/_matches:1654–1685` | Własny plik subskrypcji; dokładna grupa, zakres, sezon, brak paczek; zapis temp+replace bez jawnego fsync. |
| E09 | `application/automation.py:_schedule_subscriptions:3398–3446; _dispatch:1056–1081` | Deadline/pending/problem/pauza kontrolowane przez ownera; I/O na puli; admission wraca do ownera. |
| E10 | `application/automation.py:_subscription_work_states:3116–3145; _subscription_view:5331–5357` | Projekcja łączy odcinki, acquisition i request; API już niesie end_state, calendar_problem, episodes, airing. |
| E11 | `cli/interactive/state.py:_entries:1256–1264; _subscription_term:1401–1430` | Lista pokazuje serię/grupę/enabled/termin; countdown już bazuje na airing, lecz brak pełnego stanu wpisu/liczników na liście. |
| E12 | `cli/interactive/subscriptions.py:SubscriptionDraft:12–83; entries:101–124` | Draft nie jest trwałym zamówieniem; szczegóły rozróżniają downloaded/processing/completed, inaczej niż uboga lista. |
| E13 | `application/automation.py:_file_origin:1043–1054; _start_automatic:1015–1041` | Handoff wykorzystuje `complete_files`, potem wspólne plan_auto/admission; źródła lokalne także trafiają do tej drogi. |
| E14 | `application/watch_state.py:WatchStateStore:257–297` | Stan ownera: temp, flush/fsync, backup, replace; migracja z zachowaniem wcześniejszej kopii. |
| E15 | `services/http_requests.py:RequestControl:61–196` | Współdzielone aktywne odczyty, budżety, cooldown i liczniki; rozpoznaje AniList/Nyaa/qB, inne hosty jako `other`. |
| E16 | `application/planner.py:_select_subtitle_input/_select_embedded_track:1013–1137` | Manual zachowuje wybór, Auto preferuje sidecar przed embedded, ranking embedded bierze języki ze snapshotu. |
| E17 | `services/extraction/tracks.py:DEFAULT_AUDIO_PRIORITY/DEFAULT_SUBTITLE_PRIORITY:24–28; config/user_settings.py:UserSettings:280–281` | Domyślne audio jpn/eng/zho, napisy pol/eng; preferencje pipeline nie realizują same priorytetu PL audio w acquisition. |
| E18 | `platform/local_control.py:constants:67–92; _prove_key:722–735; _decode_frame:785–793` | Protokół 1, JSON, uwierzytelnienie, 1 MiB ramki, ograniczona kolejka; odrzucenie innej wersji. |
| E19 | `platform/qbittorrent_process.py:download_scope:101–115; release_completed:248; released_hashes:275` | Osobny właściciel procesu/hashów i dowodów zwolnienia; nie utożsamiać ze stanem requestu. |
| E20 | `application/library.py:file_identity:29–43; application/discovery.py:_iter_source_paths/_iter_entry_sources:260–283; paths.py:config_dir/watch_dir/ready_dir:89–152` | Tożsamość i bezpieczne ścieżki, pomijanie temp/ukrytych/dowiązań, jedno źródło katalogów runtime. |
| E21 | `application/acquisition.py:retained_reference/reacquire:511–528` | Jawne ponowienie zachowuje numeryczne Nyaa ID i tytuł; usunięcie Nyaa dotyka recovery, nie tylko wyszukiwarki. |
| E22 | `application/ready.py:ReadyMove.apply:89; recovery.py:CHECKPOINT_VERSION:23; history.py:constants:24–28` | Relokacja, recovery grafu i obserwacyjna historia mają odrębne odpowiedzialności. Historia: 30 dni/50 domyślnych wpisów. |

### Stan i protokół — nie scalać odmiennych automatów

| Trwały kontrakt / projekcja | CURRENT | Właściciel i konsekwencja TOUCH |
| --- | --- | --- |
| WatchState | schema **2**, reader 1/2 | `AutomationOwner` + `WatchStateStore`; nowy model powiązań wymaga wersjonowanej migracji, nie dopisywania nieznanych pól staremu readerowi. |
| Subscriptions | schema **4**, reader 1–4 | `SubscriptionService`/`SubscriptionStore`, mutacje rezydenta koordynuje owner; numery z `taken_episodes` migrują do ORDERED, nie COMPLETE; `taken` zachowuje hashe. |
| Settings / presets / model catalog | **3** (reader 1/2/3) / **1** / **1** | AppService i config; nowe preferencje przez istniejący field catalog oraz UI, nie dodatkowy settings store. |
| RunJournal | checkpoint **1** | Pozostały graf, publication proofs i niepewna praca zdalna; nie wykonywać automatycznie drugi raz płatnego kroku. |
| IPC | protocol **1** | ControlRequest/Response, `control_views` strict TypeAdapter; zmiana payloadu wymaga świadomej kompatybilności/version bump. |
| EpisodeState / SubscriptionEnd | pending/due/ordered/complete/expired/missing; active/complete/missing/uncertain | Fakty pozyskiwania i monitorowania, nie stan tasków ani historia oglądania. |
| AcquisitionState | pending_send/uncertain/accepted/complete/failed | Pewność przekazania i plików; błąd/niepewność nie upoważnia do nowego add. |
| RequestState | accepted/running/paused/succeeded/partial/failed/cancelled | ACCEPTED request może już wykonywać taski; UI potrzebuje także zdarzeń aktywności. |
| TaskState | blocked/ready/queued/running/succeeded/failed/cancelled (`planning.py:44–53`) | Scheduler prowadzi taski; sukces pojedynczego taska nie oznacza gotowego zestawu w Library. |
| Projekcje / events | status, subscriptions/work_states, materials, Library; `state_changed`, RunEventKind/WorkerNotificationKind | Snapshot odtwarza stan po reconnect; `GROUP_FINISHED` nie jest samodzielnym dowodem publikacji/ready. |

Droga IPC: `ResidentSession` → `acquisition` (search/season_context/search_title), `download`, `subscription_add`, `subscriptions_check`, enable/disable/remove/range → dispatch ownera → I/O → admission/commit → projekcja/event → renderer. Zachować session/instance/command IDs, replay receipt i odrzucanie spóźnionych odpowiedzi.

## 5. CURRENT — najważniejsze ryzyka i korekty wcześniejszych opisów

- **Paczki:** zmiana samego rankingu nie wystarczy. Model E06 mieści jedną korelację odcinka, E04 usuwa kolejne wybory tego samego hasha. Potrzebne rozdzielenie jednego transferu i wielu elementów/intencji; nie usuwać dedupe add.
- **Selekcja plików:** `TransferInspector` obsługuje już częściową kompletność, ale obserwuje wybór qB, zamiast wyznaczać żądany zakres. Zachować E07 i uzupełnić kontrakt selekcji przed `resume`.
- **Tożsamość:** nazwa, grupa, seed count i format nie dowodzą sezonu/odcinka. Walidację docelowej tożsamości wykonać także przy admission, nie wyłącznie podczas renderowania listy.
- **Subskrypcje:** `_schedule_subscriptions` zatrzymuje globalny problem/pending receipt; `check_due` może zakończyć się przed wyszukiwaniem. Zmiana źródła nie usuwa tych warunków.
- **Widoczność:** enabled to nie „skutecznie monitorowana”. Wcześniejszy raport odtworzył identyczny ekran z/bez `subscriptions_problem` i ignorowanie `problems` z F; to cudza reprodukcja, nie run tego audytu.
- **Korekta źródeł:** `subscriptions-current-state.md:59–63` uzupełnia `current-system.md:66,93`: istnieje UI O → ręczna grupa → draft przed pierwszym wydaniem. Brakuje drogi bez obowiązkowej grupy, nie każdej drogi przed premierą.
- **PL:** acquisition odrzuca dub, a domyślne audio nie preferuje PL. Z kolei planner już demotuje signs/forced w automatycznym wyborze napisów. Nie mylić legacy scoringu `tracks.py` z całym aktualnym plannerem.
- **Sidecar:** Auto wybiera dopasowany sidecar przed embedded [E16]; samo przestawienie języków embedded nie zapewni globalnego „PL dialogowe najpierw” między różnymi rodzajami źródeł.
- **Trwałość:** SubscriptionStore ma słabszą granicę zapisu niż WatchStateStore. Nie wyprowadzamy gwarancji odporności na utratę zasilania z samego `replace` ani z testu restartu obiektów.
- **Drift dokumentacji:** wcześniejsze raporty wskazują nieaktualne Enter/folder serii i Auto/autostart w README; implementację przyszłego przepływu oprzeć na kodzie, potem świadomie zaktualizować dokumentację.

## 6. TOUCH — mapa chirurgicznych zmian

KEEP nie oznacza pełnego certyfikatu poprawności. REMOVE jest warunkowe: dopiero po przepięciu konsumentów, migracji danych i odpowiednim teście. Proponowane nazwy plików nie istnieją w zinwentaryzowanym drzewie.

| Decyzja | Istniejące miejsce lub proponowana ścieżka | Konsumenci i wymagany dowód |
| --- | --- | --- |
| KEEP | `application/{service,watch,discovery,inspection,planner,scheduler,scheduler_runtime,recovery,ready,library}.py` | Lokalny input, Auto/Manual, biblioteka; istniejące testy watch/ready/planner/service, dopięcie end-to-end po zmianie acquisition. |
| KEEP | `platform/{local_control,process_lock,directory_watch,child_processes,recycle,restore_worker}.py` | Rezydent, transfer→watch, usuwanie/Undo; zachować auth/identity/drain i testy platformowe. |
| MODIFY | `services/catalog/{types,anilist}.py`; `bootstrap.py` | Wspólna wyszukiwarka i subskrypcje: relacje sezon/cour/dodatki bez przeliczania całego drzewa tylko z prequeli. `test_anilist.py`. |
| CREATE | `services/catalog/anizip.py` | Wstrzyknięty mapper z jawnie typowanym wynikiem i pochodzeniem; proponowane `tests/services/catalog/test_anizip.py`. |
| CREATE | `services/torrents/torrentio.py` | Kandydaci do wspólnego use case; proponowane `tests/services/torrents/test_torrentio.py`; unknown pola nie stają się verified. |
| CREATE | `application/episode_selection.py` | Czysta tożsamość/ranking dla manual i subscriptions, bez HTTP/config/CLI; proponowane `tests/application/test_episode_selection.py`. |
| MODIFY | `application/acquisition.py`, `services/torrents/types.py` | Jeden search/select/download contract, rozdzielenie candidate/file/transfer; obecne `test_acquisition.py`, nowe kontrakty paczek. |
| MODIFY | `application/{control,control_payloads,control_views,watch_state}.py` | Owner, serializacja, IPC, projekcje; zapisać powiązania wielu intencji z elementami transferu. `test_control.py`, `test_watch_state.py`, `test_local_control.py`. |
| MODIFY | `application/{automation,subscriptions}.py` | Wspólna selekcja i trwała korelacja; usuwać tylko stare wymagania po decyzji produktowej. `test_automation.py`, `test_subscriptions.py`, `test_subscription_pipeline.py`. |
| MODIFY | `services/torrents/qbittorrent.py`, `platform/qbittorrent_process.py`, `application/transfers.py` | Wybór rzeczywistych indeksów, potwierdzenie priorytetów, restart/dodanie E3 do E1; testy qB/process/transfers i izolowana próba runtime. |
| MODIFY | `services/http_requests.py` | Nazwane budżety i cooldown ani.zip/Torrentio; obecnie trafiłyby do `other`. Zachować wspólny transport i pomiar rzeczywistych wywołań. |
| MODIFY | `cli/resident.py`, `cli/interactive/{app,state,anime,subscriptions,prompts}.py` | Jedna wyszukiwarka, główne Subskrypcje i pełne powody; testy interactive state/anime/keys/app/resident. |
| MODIFY warunkowo | `config/{user_settings,field_catalog,field_access}.py`, `interactive/settings.py`, `application/planner.py` | Dopiero po decyzji o PL audio, fallbacku i ustawieniach; snapshoty starszych runów zachować. Testy planner/settings/runtime config. |
| REMOVE warunkowo | Group-first UI, `_group_queries`, twarde `_is_hidden/_is_excluded`, wymaganie grupy subskrypcji | Konsumenci: Anime, SubscriptionOrder/Service, CatalogOrder, lazy exports, IPC i testy; zastąpić zatwierdzoną selekcją, nie samym usunięciem asercji. |
| REMOVE warunkowo | Wyszukiwanie Nyaa/RSS, `categories.py`, zależne query paths | OPEN fallback. `retained_reference/reacquire` i zapisane Nyaa ID nadal mają konsumentów; mogą wymagać małego adaptera legacy po usunięciu aktywnego search. |
| REMOVE warunkowo | `AcquisitionService.series_directory` | Wyszukanie w aplikacji wykazało tylko definicję; przed usunięciem sprawdzić eksporty/testy. Realny download już zapisuje do roota. |

### Proponowany fragment drzewa docelowego, nie stan istniejący

```text
anishift/
  bootstrap.py                         [ISTNIEJE, MODIFY: jawne DI]
  application/
    acquisition.py                     [ISTNIEJE, MODIFY: wspólny use case]
    episode_selection.py               [NOWE, PROPOZYCJA: czyste reguły]
    subscriptions.py                   [ISTNIEJE, MODIFY: intencja/terminy]
    automation.py                      [ISTNIEJE: nadal jeden owner]
    control.py / watch_state.py         [ISTNIEJĄ, MODIFY: wersjonowane fakty]
    transfers.py / planner.py           [ISTNIEJĄ: handoff / plan produktów]
  services/
    catalog/anilist.py / types.py       [ISTNIEJĄ]
    catalog/anizip.py                   [NOWE, PROPOZYCJA]
    torrents/torrentio.py               [NOWE, PROPOZYCJA]
    torrents/qbittorrent.py / types.py  [ISTNIEJĄ, MODIFY]
    torrents/nyaa.py                    [ISTNIEJE, LOS WARUNKOWY]
  cli/interactive/
    anime.py / subscriptions.py        [ISTNIEJĄ, wspólny wybór i drafty]
    state.py / prompts.py / app.py      [ISTNIEJĄ, routing i jeden renderer]
```

Adaptery są zwykłymi modułami jak obecny AniList/qB, z wstrzykniętym HTTP i domenowymi błędami. Nie tworzyć `catalog/engines`, `torrents/engines`, drugiego schedulera ani drugiego ledgeru acquisition. Nie przenosić providerów TTS/LLM/tłumaczeń.

## 7. TOUCH — kolejność małych kroków i granice ownership

1. **Ustalić kontrakt i dane:** zamknąć OPEN wpływające na model, wskazać keys intent/episode/file/transfer i dowody końca. Zapisać fixtures migracji 1–4/1–2 oraz scenariusze admission przed zmianą modelu.
2. **Czysta selekcja:** wydzielić reguły tożsamości i rankingu do jednego małego modułu; wykorzystać zamrożone przypadki badawcze, ale dodać niezależne przypadki/kontrprzykłady. Nie kopiować instrumentów eksperymentu jako produktu.
3. **Adaptery i wspólne wyszukiwanie:** AniList/ani.zip/Torrentio przez DI i RequestControl; manual i subscriptions wywołują ten sam use case. Błędy/niepełność katalogu muszą być widoczne.
4. **Trwałe admission i wybór plików:** najpierw migracja/persist intencji, następnie stopped add lub reconcile istniejącego hasha, uzgodnienie manifestu, priorytety, trwały layout i dopiero resume. Każdy krok musi dać się uzgodnić po utracie odpowiedzi.
5. **Subskrypcje i projekcja:** usunąć zależność od jednej grupy, zmapować zaakceptowaną politykę dat/retry/końca, zachować historię przyjęć. Wyliczać liczniki i powody z faktów ownera, nie z pamięci UI.
6. **UI/settings/pipeline PL:** przebudować wejście i szczegóły na nowym kontrakcie; decyzję o wykorzystaniu PL audio wdrożyć w plannerze, nie w downloaderze. Sprawdzić lokalny plik, Auto, Manual i reconnect.
7. **Usuwanie starych ścieżek:** dopiero po przełączeniu wszystkich konsumentów i scenariuszach migracja/restart. Nie kończyć z dwoma aktywnymi mechanizmami zamawiającymi ten sam odcinek.

`automation.py` ma 5445 linii, lecz rozmiar nie uzasadnia jednorazowego przepisywania. Najpierw wydzielać czyste DTO/projekcje/predykaty związane z nową selekcją; następnie tylko niezbędne operacje I/O za protokołem. `_commit`, kolejka, receipt, admission i zmiany WatchState pozostają przy ownerze.
Zależne etapy nie mogą równolegle zmieniać tych samych schematów. Dopuszczalne niezależne zakresy przyszłej implementacji: adaptery po ustaleniu DTO, czyste fixtures selekcji, makiety na zatwierdzonej projekcji.

## 8. Runtime, bezpieczeństwo, migracja i rollback

**CURRENT runtime:** `paths.py` wylicza `config/settings.json`, `config/watch/`, `watch/runs/`, `watch/relocations/`, `config/qbittorrent/`; SubscriptionStore używa `config/subscriptions.json`. Workspace ma root, `ready/`, `temp/` i istniejące trasy `subs/translate/audiobook/cover/`; nie dodawać wymaganego input/output/cache/logs do workspace.
`ANISHIFT_CONFIG_DIR` zmienia katalog konfiguracji, `ANISHIFT_WORKSPACE_ROOT` wybór workspace; `.env` pozostaje przy repo. Preferencje i sekrety nie mają trafić do manifestu transferu ani payloadów projekcji.

- **Auth/protocol:** zachować lokalny pipe/socket, challenge/key, session przypisane przez serwer, ścisłe dekodowanie i limity ramek/połączeń. Duże katalogi wymagają ograniczenia/paginacji odpowiedzi; nie zwiększać w ciemno 1 MiB.
- **URL/provenance:** nowy kandydat potrzebuje źródła, identyfikatora katalogu, wyniku identity, zakresu deklaracji języka i referencji transferu. Walidować schemat/host/redirecty w adapterze; nie utrwalać dowolnego signed URL lub credentials jako „provenance”.
- **Ścieżki:** hash nie zatwierdza filename. Uzgodnić manifest z qB; odrzucać escape/drive/UNC/dowiązania i kolizje. `safe_resolve` nie zastępuje tożsamości pliku, rezerwacji i ponownej walidacji przed publication/relocation.
- **Własność qB:** PID/time/binary/profile i własność hashów pozostają warunkiem mutacji/shutdown. Ręczne przejęcie GUI nie może uruchomić automatycznej walki o klienta. Release zachowuje dane (`deleteFiles=false`).
- **Paczki:** indeks dostawcy nie jest qB index; basename+size bywa niejednoznaczny. Przy braku dowodu parkować wybór z powodem. Priority=0 nie gwarantuje zera pobranych bajtów; companion progress=1 nie dowodzi osobnego pliku.
- **Retention:** cache metadanych może wygasać, ale receipt/dedupe/recovery nie dziedziczą 30-dniowej retencji History. Zniknięcie wpisu z aktywnej listy nie usuwa dowodu wcześniejszego zamówienia.
- **Logowanie:** istniejący `get_logger`; kody/powody/liczniki/czas granic operacji. Bez sekretów, pełnych payloadów, promptów, absolutnych ścieżek, pełnych komend/stderr i `ErrorContext.details`.

**Proponowana migracja:** pod blokadą jednej instancji zatrzymać nowe admission, zachować kopie wersjonowanych plików i zależnych dzienników, zwalidować wejście, przeliczyć deterministycznie identyfikatory oraz zapisać nową wersję atomowo. Nie uruchamiać równolegle starej i nowej binarki na tym samym stanie.
Zachować ID sezonów/subskrypcji, numery ułamkowe, zakres/ogon, repeat IDs, receipts, reservations plików, preferences, complete proofs, relokacje i powiązania requestów. Rezerwacje sesji UI nadal są efemeryczne zgodnie z aktualnym kontraktem startup/disconnect; nie odtwarzać martwego klienta.
`taken` bez hasha/dowodu pliku pozostaje handed-over/unknown. Niejednoznaczne stare wpisy parkować i pokazać powód, bez automatycznego redownloadu. Migracja nie może przemianować FAILED/UNCERTAIN na COMPLETE ani otworzyć nowego retry przez sam restart.
Restart w połowie dwóch magazynów rozliczać zapisanym receipt/migration phase, nie zgadywaniem po istnieniu pliku. Zachować kopię z wcześniejszej próby zamiast ją nadpisywać; brak miejsca/uszkodzony JSON/nieznana wersja mają przerwać przełączenie.
**Rollback:** przed nowymi efektami możliwe przywrócenie spójnego backupu i starej binarki. Po nowych add/plikach/przenosinach sam rollback JSON cofa pamięć efektów — potrzebne uzgodnienie qB i dzienników lub naprawa do przodu. Bez automatycznego downgrade i bez wycinania dowodów, aby stary reader zaakceptował plik.

## 9. Kontrakt do przyszłego ASCII UI i pomiarów

- Makieta ma pokazać wejście do Subskrypcji z głównej nawigacji, Search, sezon/cour/rok, zakres, Download/Subscribe, listę aktywnych i szczegóły odcinka. Nie narzucać obecnych grup jako poziomu obowiązkowego.
- Wiersz subskrypcji: tytuł/sezon, zamówiony zakres, pobrane/razem oraz osobno przetwarzane/gotowe, najbliższy AIR, powód oczekiwania/problem i dostępna akcja. Dla nieznanego total nie wymyślać mianownika.
- Pokazać stany puste, busy, offline, stale data, brak daty, brak kandydata, niepewny add, niejednoznaczny plik i terminalny problem; globalny `subscriptions_problem` nie może zniknąć za kropką enabled.
- Zachować jeden Prompt Toolkit renderer, lokalne drafty, TextInput/focus, blurring przy Tab, Esc/back i generation guard. Render nie wykonuje sieci ani zapisu; resize i mały terminal nadal pozwalają działać.
- Aktualne Home: Panel/Ręczny/Ustawienia/Wyjście; taby: Anime/Subskrypcje/Przetwarzanie/Biblioteka. Zmiana liczby tabów dotyka także hardcoded `/4` w `state.py:1130–1138`, routingu strzałek i `_NORMALISED_KEYS`.
- ASCII ma opisać działania i źródło faktów, nie obiecywać ETA torrenta. Dokładne klawisze i ułożenie nawigacji pozostają do zaakceptowania w projekcie UI.

**CURRENT wydajność:** AniList/Nyaa mają timeouty 20 s, qB 10 s; RequestControl rozdziela AniList/Nyaa o 1 s, buforuje maks. 8 MiB i scala tylko aktywne odczyty. Nie jest cache ukończonych odpowiedzi. Nowi dostawcy wymagają własnych nazw/budżetów; nie dziedziczyć przypadkiem wspólnego `other`.
**TOUCH pomiar:** osobno query→pierwszy użyteczny wynik, wybór sezonu→odcinki, wybór odcinka→kandydat, receipt→qB ack, metadata→ustalony plik, complete file→pipeline start, publikacja→Library; p50/p95 dopiero na określonej próbie, liczba HTTP, cache hits, błędy/timeouty, cold/warm/restart.
Cache ograniczony liczbą/rozmiarem i TTL przy właścicielu metadanych, nie osobna kopia UI; terminy emisji i wyniki transferu wymagają odmiennych zasad aktualności. Cała operacja potrzebuje deadline/cancellation oprócz timeoutu pojedynczego HTTP. Wartości docelowe dopiero po pomiarze — brak zatwierdzonego SLA.

## 10. Macierz weryfikacji do przyszłego planu

Istniejące testy poniżej znaleziono w repo, **nie wykonano ich w tym audycie**. Nowe nazwy oznaczają proponowane scenariusze, nie gotowe pliki lub dowody PASS.

| Granica | Istniejący test / zestaw | Proponowany dowód zmiany |
| --- | --- | --- |
| Nowa polityka języka/jakości | `test_acquisition.py::test_catalog_excludes_a_dubbed_release_and_one_without_a_stated_language`, `::test_catalog_filters_episodes_outside_the_range_and_every_pack` | Zastąpić kontrakt po zatwierdzeniu wymagań; `test_polish_dialogue_precedes_typesetting`, `test_1080_is_preferred_not_required`, unknown PL ≠ verified. |
| PL w pipeline | `test_planner.py::test_polish_signs_track_loses_to_english_dialogue`, `::test_default_priority_prefers_polish_dialogue_over_english_dialogue`, `::test_configured_language_order_outranks_the_default_polish_preference` | PL audio kontra napisy, sidecar kontra embedded, zachowanie ręcznego wyboru i starego settings snapshotu. |
| Paczka i readiness | `test_transfers.py::test_completed_selected_files_are_ready_without_unselected_pack_files`, `::test_a_finished_file_of_an_unfinished_pack_is_complete_on_its_own` | `test_e1_and_e3_share_one_transfer_without_selecting_e2`; raw padding index ≠ qB; kolizja basename; brak materializacji; dodanie E3 po E1. |
| Admission/restart | `tests/application/test_automation.py`, `test_watch_state.py`, `tests/platform/test_qbittorrent_process.py` | Utrata ack/add/filePrio/rename/resume w każdym punkcie; brak drugiego add; zachowanie E1 przy dołączeniu E3 i read-only po przejęciu GUI. |
| Migracja | `test_watch_state.py::test_a_schema_one_state_is_migrated_once_and_keeps_every_recorded_fact`, `::test_migration_never_overwrites_a_backup_left_by_an_earlier_attempt` | Wszystkie wspierane schematy, powtórne load bez zmian, przerwanie między plikami, unknown wersja, backup/rollback po efektach. |
| Stare subskrypcje | `test_subscriptions.py::test_loading_a_schema_one_file_records_its_taken_episodes_as_handed_over`, `::test_old_schema_four_records_do_not_gain_a_fresh_intent_or_reset_their_window` | `test_ambiguous_legacy_order_is_parked_without_redownload`; brak utraty zakresu, repeat, receipts i starego postępu. |
| Katalog/identity | `tests/services/catalog/test_anilist.py`, `tests/integration/test_search_pipeline.py` | AniList→ani.zip→Torrentio na MockTransport; cour/OVA/special/absolute numbering/mismatch, niepełna relacja, provider cooldown i reconnect. |
| UI/projekcje | `tests/cli/test_interactive_{anime,state,keys,app}.py`, `test_text_input.py`, `test_resident.py` | Główne wejście, counts/range/AIR, globalny problem, mały terminal, focus, opóźniony worker po Esc i replay snapshotów bez podwójnego admission. |
| Cały przepływ | `tests/integration/test_subscription_pipeline.py`, `tests/application/test_ready.py`, `test_watch.py`, `test_workflows.py` | Lokalny MKV i wybrany plik paczki przechodzą tę samą granicę; downloaded ≠ ready; release przed move; gotowy wynik widoczny w Library po restarcie. |

Przyszłe pełne bramki: `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`, `uv run pytest`; na Windows dodatkowo mypy `--platform linux`, w CI na Ubuntu również `--platform win32`.
CI (`.github/workflows/ci.yml:16–104`) obejmuje pytest i `anishift --help` na Ubuntu/Windows oraz pip-audit eksportowanego locka na obu platformach. `pytest tests/` nie zastępuje pełnego pytest z embedded utils tests.
Zachować `.pre-commit-config.yaml`: ruff/format, zakaz opisowej prozy w testach, docstringi stałych, kontrolę nazw Windows/sekretów i format commita; pre-push mypy obu targetów i pytest. Nowych strażników nie dodawać bez zgody.
Próby runtime przyszłej selekcji wykonywać na odrębnych config/workspace/profilach i syntetycznych danych; Windows rzeczywiście sprawdza locks/ACL/pipe/rename, Linux osobno ścieżki/socket. Mock HTTP nie zastępuje tego dowodu.

## 11. OPEN i przekazanie do specyfikacji

1. Nyaa: fallback aktywnego wyszukiwania czy wyłącznie obsługa starych referencji/reacquire?
2. Koniec subskrypcji: komplet pozyskanych plików czy gotowych produktów; nieznana liczba odcinków, dodatki, spóźnione wydania; kiedy usunąć z aktywnej listy?
3. Usunięcie ręczne: rekomendacja zatrzymać monitoring, zostawić transfery/pipeline/pliki i dedupe; to nadal propozycja, nie zatwierdzony kontrakt.
4. PL audio vs PL napisy, wynik przy gotowym audio oraz pomijanie TTS; czy niepotwierdzony PL hint może wyprzedzić 1080 bez hintu? Jak ograniczyć próby po braku PL w zawartości?
5. Kolejność fallback 720/2160/inne/unknown oraz rola słabych sygnałów jakości; brak podstaw do narzucenia jej na bazie obecnych testów.
6. Monitoring przed premierą, przy braku indywidualnej daty, HIATUS i po zakończeniu kalendarza; retry/expiry/zamiana zatrzymanego źródła nie mogą zostać odziedziczone przypadkiem.
7. Hosted Torrentio nie dostarcza samo dowodu mapowania fileIdx→qB. Nierozstrzygnięty manifest/plik wymaga jawnego stanu, nie wyboru pierwszego podobnego basename.

Źródła wtórne: `summary.md`, `current-system.md`, `subscriptions-current-state.md`, `bundle-file-selection-validation.md`, `polish-1080-selection-validation.md` (badania 2026-09-22). Wyniki 113/140 testów, pomiary HTTP i próba qB v5.2.3/WebAPI 2.15.1 należą do tych raportów; nie są wynikami wykonania tego audytu.
Raport paczek potwierdza syntetyczne bajty/restart, nie dekodowanie anime ani wszystkie wersje qB; raport PL potwierdza wskazówki w ograniczonej próbie, nie zawartość ścieżek. Nie ustalono przyczyny konkretnej awarii użytkownika.
Materiał wystarcza do określenia kontraktów i zakresów przyszłego planu. Implementacja wymaga rozstrzygnięcia OPEN, dokładnego schematu migracji i odbioru UI; głęboki audyt providerów TTS/translation/LLM pozostaje poza tym wynikiem.
