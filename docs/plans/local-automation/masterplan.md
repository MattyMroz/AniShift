---
kind: masterplan-and-implementation-plan
status: proposed
updated: 2026-09-05
baseline: bc74425b487fb9110da76911c26dca4194b2aad9
implementation: not-executed
language: pl
---

# AniShift: pełna automatyzacja lokalna | masterplan implementacji

**Cel:** od wyboru anime lub wrzucenia pliku do gotowego polskiego odcinka, bez ponawiania codziennych ręcznych czynności.

**Baza:** aktualny kod sprawdzony przez GitHub; **wynik tego pliku:** projekt i kolejność implementacji, nie gotowa implementacja.

[Specyfikacja](spec.md) · [Research i źródła](research.md) · [Brief technologiczny](brief.md) · [Przekazanie agentowi](handoff.md)

## 1. Stan, zakres i sposób wykonania

### 1.1. Cel końcowy

Właściciel wybiera serię oraz regułę wydania raz. AniShift lokalnie znajduje pasujące wydania, pobiera wskazane pliki przez istniejący klient torrent, przygotowuje polskie produkty tym samym rdzeniem i udostępnia każdy gotowy odcinek natychmiast po jego własnym zakończeniu. Ten sam rezultat jest dostępny po wrzuceniu własnego pliku do inbox. Terminal służy do wyboru, obserwacji i decyzji wyjątkowych; nie musi pozostawać otwarty.

Zakres obejmuje cały ten przebieg. Fazy porządkują implementację, ale nie ograniczają zamówienia do samego importu lub wklejenia magnetu. Nie ma zależności od VPS, chmury, nowego odtwarzacza ani przebudowy tłumaczenia/TTS.

### 1.2. Stan zweryfikowany

Kod odniesienia: `MattyMroz/AniShift`, `work/planning/automation-and-subtitles`, commit `bc74425b487fb9110da76911c26dca4194b2aad9`, odczytany przez integrację GitHub. [S01]

`AppService` oferuje discovery, planowanie, wykonanie i anulowanie. `GraphScheduler` oraz istniejące handlery odpowiadają za obróbkę i publikację. Nie są nowymi brakującymi komponentami. [S03, S05, S06, S12]

Obecne discovery skanuje jeden katalog. Włączanie rekursji bez zmiany identyfikacji grup mogłoby połączyć dwa różne źródła o tym samym stem. Zamiast tego każdy job automatyzacji otrzyma własny płaski workspace rewizji. [S04]

Frontend używa Prompt Toolkit i menu Home. Historyczny dokument slash-commandów nie opisuje aktualnego interfejsu. Nie usuwamy obecnej maskotki i nie projektujemy nowego brandingu w tej funkcji. [S07–S09]

Nie uruchomiono AniShift na komputerze właściciela ani nie odczytano jego prywatnych odcinków, konfiguracji, promptów i kluczy. Historyczne liczby testów z załącznika nie są wynikami tego pakietu.

### 1.3. Pierwszeństwo ustaleń

1. Aktualna prośba właściciela: pełna lokalna automatyzacja.
2. Specyfikacja tego pakietu: wynik i granice R01–R30.
3. Ten dokument: przyjęty design oraz kolejność kodowania.
4. Instrukcje repozytorium: sposób pracy i wymagane bramki.
5. Starsze wizje i audyty: źródła historyczne, nie obowiązek ograniczenia do jednej iteracji.

Skille masterplan/planning preferują etapowe uszczegóławianie. W tym zleceniu właściciel jawnie zamawia połączenie ich ról i szczegółowy plan całego zakresu. Zachowujemy kontrolę założeń i aktualizację po dowodzie, ale nie odkładamy rozpisania dalszych faz.

### 1.4. Statusy i źródło wykonania

Każda karta T001–T128 ma status `planned`. Żadna nie została wykonana przez samo wygenerowanie dokumentu. Scenariusze w kartach są zamówionymi testami i próbami odbiorowymi.

Ten masterplan jest jedynym właścicielem statusu wykonania. Pokrycie wymagań jest widoczne w polu **Realizacja** każdego wymagania w [spec.md](spec.md); nie ma osobnego eksportu ani drugiej tablicy.

Numery zadań wyznaczają domyślną kolejność pracy jednego integratora. „Kolejność planowa” zachowuje tę kolejność; „Zależności obowiązkowe” opisują zależności, których nie wolno pominąć. Brak zewnętrznej próby qBit blokuje zależny downloader, ale nie lokalny import. Przy zablokowanej karcie wolno przejść do pierwszej numerycznie kolejnej karty z zakończonymi zależnościami i zapisać przyczynę odchylenia. Nie wprowadzać równoległych writerów do schematu, stanu, mostka i TUI. Graf nie jest deklaracją matematycznie minimalnego podziału pracy.

## 2. Decyzje architektoniczne

| ID | Rozstrzygnięcie | Powód i konsekwencja |
| --- | --- | --- |
| D01 | Czuwanie jako proces bez UI, okno partii na istniejącym Auto | Zastąpione przez [Plan 01](plans/01-watch-mode.md): proces czuwania skanuje bibliotekę i otwiera okno terminala tylko na czas obróbki; brak własnego HTTP, brokera i serwera. |
| D02 | Stan = pliki biblioteki | Dla lokalnego dropu nie ma SQLite ani kolejki: produkty obok źródeł mówią, co jest gotowe. SQLite wraca dopiero wtedy, gdy Plan 02 (pobieranie, subskrypcje) wykaże potrzebę trwałego stanu. |
| D03 | Brak skrzynki komend | Frontend i czuwanie komunikują się kodem wyjścia okna partii i plikiem `stop`; nie ma tabeli `commands`. |
| D04 | qBittorrent WebUI na loopback | Dojrzały silnik torrent; AniShift nie implementuje protokołu ani pobierania kawałków. |
| D05 | Stabilny wrapper `qbittorrent-api` | Zależność zamiast kopiowania cudzej kompletnej aplikacji. |
| D06 | Nyaa RSS i ograniczone wyszukiwanie HTML | RSS do nowych wydań, historia do zakończonych serii i luk po długim offline. |
| D07 | Jeden dodatkowy adapter publicznego RSS | Drugie skonfigurowane źródło bez platformy instalowanych dynamicznie pluginów. |
| D08 | AniList jako katalog i hint emisji | Tytuły, aliasy, formaty i relacje; nie tożsamość wyznaczona samym fuzzy score. |
| D09 | LiveChart pozostaje pomocniczy | Jego feed minionych odcinków nie zastępuje kalendarza przyszłych premier. |
| D10 | Biblioteka = `workspace/` z podfolderami serii | Discovery jest rekurencyjne (bez `temp/` i katalogów od kropki); produkty leżą obok źródła w podfolderze. Nie ma osobnego `media/`. |
| D11 | Kopia źródła, nie hardlink/move | Odłożone do Planu 02: dotyczy plików pobranych przez klienta torrent, nie lokalnego dropu. |
| D12 | Rewizja obejmuje cały pakiet wejść | Inne napisy lub inny wybór tracka muszą zmienić produkt także przy identycznym MKV. |
| D13 | Jeden job na fizyczny plik | Odłożone do Planu 02. W Planie 01 partia to zestaw gotowych grup przetwarzany jednym runem Auto, jak dziś; gotowość pojedynczego odcinka daje istniejący scheduler. |
| D14 | Istniejący `AppService` i scheduler | Nie powstaje drugi translator, TTS, merger ani alternatywny system artefaktów rdzenia. |
| D15 | Precyzyjna intencja może mieć `RunMode.MANUAL` | To wewnętrzny kontrakt wskazania tracka, bez wymuszania ręcznych kroków w UI. |
| D16 | Task Scheduler przy logowaniu | Zwykły użytkownik, nie usługa SYSTEM, bez hasła i uprawnień administratora. |
| D17 | Okno partii jest monitorem | Otwiera się, gdy jest co robić, pokazuje ekran Auto i zamyka się samo po wyniku; zamknięcie okna anuluje tylko tę partię, czuwanie trwa. |
| D18 | Zewnętrzny mpv | Odtwarzanie bez pisania playera; uruchomienie filmu nie oznacza obejrzenia. |
| D19 | Lokalny watched + opcjonalny import MAL XML | Brak automatycznego outbound sync MAL/AniList w tej edycji. |
| D20 | Jawny stan częściowego dowodu | Pusty wynik, awaria, nieznane dopasowanie i brak napisów nie są tym samym. |

D04: odczyt rejestru z 2026-09-05 (pakiet `docs/plans/automation/`) potwierdził zainstalowany qBittorrent 5.2.3 i Stremio 5.0.25; zgoda na sterowanie klientem przez WebUI nadal jest jawną decyzją setupu. Bez klienta działa import i obróbka lokalna; nie udajemy działającego downloadu.

D08 jest wyborem integracyjnym, nie potwierdzeniem zgody AniList na dowolną przyszłą dystrybucję produktu. Nie kopiujemy całego katalogu i nie budujemy konkurencyjnej usługi list. Warunki należy ponownie sprawdzić przed publicznym wydaniem. [S17–S19]

## 3. Procesy i własność stanu

> **Zakres tej sekcji po Planie 01:** opis workera z SQLite, komendami i lockami dotyczy przyszłych planów pobierania i subskrypcji, jeżeli okażą się potrzebne. Lokalny drop działa według [Planu 01](plans/01-watch-mode.md): proces czuwania bez UI, okno partii na istniejącym Auto, stan w plikach biblioteki.

```text
TUI / techniczne CLI
    | INSERT idempotent command; SELECT immutable snapshot
    v
SQLite na lokalnym dysku
    ^
    | krótkie transakcje domeny
AutomationWorker (jeden proces, jeden koordynator)
    |-- terminy + inbox + wyniki I/O + retry + reconciliation
    |-- ograniczona pula I/O -> AniList / RSS / Nyaa / qBittorrent
    |-- jeden wątek wykonania -> AppService -> istniejący GraphScheduler
    |-- publikacja gotowości -> snapshot biblioteki
    `-- opcjonalne otwarcie jednego monitora

qBittorrent -> downloads -> kontrolowana kopia -> library/.../revision
                                                     |
                                                     v
                                               AppService Auto
                                                     |
                                                     v
                                         pliki PL + akcja Oglądaj
```

### 3.1. Właściciele

| Obiekt | Writer | Czytelnik | Granica |
| --- | --- | --- | --- |
| Transfer i pieces | qBittorrent | Adapter download | Klient pozostaje prawdą o transferze. |
| Priorytety własnego transferu | Worker przez adapter | TUI snapshot | Wyłącznie transfer z potwierdzoną własnością. |
| Obcy istniejący torrent | Właściciel/klient | AniShift read-only | Brak zmiany priorytetu, kategorii, limitów lub ścieżki. |
| `commands` | Frontend INSERT; worker claim/finish | Obie strony | Jedyny dopuszczony zapis domenowo-neutralny z frontendu. |
| `jobs`, `episodes`, `artifacts` | Worker | Frontend | Wyniki wątków są komunikatami do koordynatora. |
| Produkt w trakcie wykonania | Istniejący scheduler/publisher | Worker po publikacji | Nie kopiować rendererowi pliku jeszcze zapisywanego. |
| Preset i ustawienia silników | Publiczne metody AppService | Mostek wykonania | Automatyzacja nie tworzy drugiego formatu tych ustawień. |
| Sekrety | Istniejąca granica Settings/.env | Adapter przy wykonaniu | Nie trafiają do DB, task XML i raportów. |
| UI i klawiatura | TerminalRenderer | Kontrolery | Jeden renderer na proces interaktywny. |
| Autostart | Jawny setup użytkownika | Doctor | Wyłącznie własne zadanie Windows. |

### 3.2. Blokady

`worker.lock` jest trzymany przez uchwyt OS przez cały czas życia workera. Plik może pozostać po zakończeniu procesu; jego istnienie nie oznacza, że lock jest zajęty.

`execution.lock` chroni uruchamianie obecnej wersji `AppService.execute`, zarówno z automatyzacji, jak i ręcznego Auto. Identyfikator procesu jest informacją pomocniczą, nie testem wyłączności.

`monitor.lock` ogranicza liczbę monitorów danej instalacji. Dodatkowo `busy_epoch` i `dismissed_epoch` nie pozwalają odtwarzać zamkniętego okna w tej samej partii.

Locki używają jednego kanonicznego `state_root`. Composition root rozwiązuje go z istniejącej konfiguracji bootstrap (`ANISHIFT_AUTOMATION_STATE_ROOT`, domyślnie config/automation), nie z katalogu danego odcinka. Setup utrwala lokalizator przed instalacją taska. Jawny override CLI musi odpowiadać wybranemu profilowi instalacji; różnica wobec profilu jest wykrywana przed startem, zamiast tworzyć niewidocznego drugiego ownera. Izolowane testy wstrzykują własny locator/guard. Dwie różne bazy nie mogą zarządzać tym samym `media_root`; setup zapisuje i sprawdza marker właściciela. Starsza oddzielna instalacja AniShift może nie znać nowego `execution.lock`; doctor musi to nazwać, nie obiecywać wyłączności wobec dowolnego obcego kodu.

Lock DB nie może pozostać otwarty podczas HTTP, kopiowania, TTS ani oczekiwania na lock wykonania. Koordynator nie czeka synchronicznie na koniec odcinka.

### 3.3. Kolejność tick

1. Odbierz stop/cancel/pause i zakończone operacje I/O.
2. Zastosuj wyniki wyłącznie bieżącej generacji.
3. Uzgodnij nierozstrzygnięte add i kopie, jeśli nadszedł ich termin.
4. Odbierz gotowe wybrane pliki klienta oraz obserwacje inbox.
5. Sprawdź terminy subskrypcji zgodnie ze wspólnym budżetem hosta.
6. Dopuść pracę według miejsca, priorytetu i limitu zapasu.
7. Uruchom jeden run Auto dla gotowych grup, tak jak dzisiejsze Auto.
8. Zapisz snapshot/heartbeat i uśpij pętlę do najbliższego zdarzenia.

Odbieranie wyników oraz komend ma pierwszeństwo przed nowym wyszukiwaniem. Żaden niedokończony download nie zajmuje slotu rdzenia. Zakończony torrent seedujący nie zajmuje slotu aktywnego pobierania. Własny backlog może zostać wstrzymany na rzecz jawnego pilnego wyboru, z zachowaniem jego danych; obcych transferów nie modyfikujemy.

## 4. Układ kodu i granice modułów

Poniższe nowe ścieżki są projektem, nie twierdzeniem, że już istnieją w repo.

```text
anishift/
  automation/
    __init__.py                 publiczna fasada automatyzacji
    models.py                   ID, DTO, stany i policy values
    config.py                   preferencje i snapshot profilu treści
    schema.sql                  DDL jednego schematu, bez sekretów
    store.py                    transakcje, zapytania, migracje, backup
    commands.py                 zamknięty katalog komend i klient lokalny
    worker.py                   koordynator, lifecycle, recovery
    paths.py                    układ biblioteki i bezpieczne komponenty
    intake.py                   kopiowanie, obserwacje, sidecary, deduplikacja
    pipeline.py                 jedyny mostek do AppService
    progress.py                 eventy rdzenia -> snapshot automatyzacji
    http.py                     budżety, timeouty, limity body, cache
    catalog.py                  aliasy, ranking, tożsamość i relacje
    releases.py                 cechy wydania, jakość, grupy, numeracja
    download.py                 qBit adapter, manifest, per-file intake
    subscriptions.py            zakres, missing set, terminy, backlog
    library.py                  query, gotowość, rewizje i watched
    providers/
      anilist.py                publiczny katalog GraphQL
      nyaa.py                   RSS oraz ograniczone historyczne HTML
      rss.py                    drugi jawnie skonfigurowany feed
      mal.py                    tylko lokalny XML, nie OAuth klient
  cli/
    automation.py               Typer, raporty i routing nowych poleceń
    automation_entry.py         cienkie python/pythonw -m entry
    interactive/
      anime.py                  wyszukiwanie i wybór wydań
      automation_library.py     biblioteka i akcje odcinka
      automation_progress.py    monitor i lista wymagająca uwagi
      automation_schedule.py    subskrypcje i harmonogram
  platform/
    automation_files.py         Windows stabilny odczyt, bezpieczne uchwyty
    automation_lock.py          msvcrt/fcntl i lifecycle locków
    automation_startup.py       XML, instalacja własnego taska, odczyt statusu
    automation_monitor.py       pojedyncze okno monitora
    automation_player.py        argv mpv i bezpieczne uruchomienie
```

Istniejące pliki wymagające punktowych zmian: `bootstrap.py`, `application/service.py`, `cli/main.py`, `cli/console.py`, `cli/interactive/app.py`, `home.py`, `prompts.py`, `config/settings.py`, `errors.py` oraz właściwe instrukcje i README. Nie zmieniamy `discovery.py` na rekurencyjny i nie przenosimy obecnych usług.

Przed edycją należy przeczytać pełną aktualną treść pliku oraz jego AGENTS. Nie każdy wymieniony plik był w całości audytowany podczas tego badania; zakres odczytu znajduje się w researchu.

`pyproject.toml` i `uv.lock` zmieniane są narzędziem `uv add`, a nie ręcznym przepisywaniem wersji pozostałych zależności. Nowe testy są małe, domenowe i używają istniejącego pytest. Nie budujemy frameworka testowego ani nowego zestawu hooków.

### 4.1. Kierunek importów

`models.py` nie importuje I/O, CLI, Settings, httpx ani qBittorrent. `catalog.py` i `releases.py` trzymają czyste decyzje oddzielone od providerów. `store.py` nie importuje TUI. `pipeline.py` używa publicznego `anishift.application` i composition root, nigdy `cli/run.py`.

Widoki korzystają z `AutomationClient` i niemutowalnych snapshotów. Samo renderowanie nie pobiera niczego, nie skanuje dysku, nie zapisuje preferencji i nie otwiera procesu.

Nie wprowadzać rejestru pluginów dla źródeł. Composition root zna trzy konkretne adaptery: katalog AniList, indeks Nyaa, dodatkowy RSS. Wymiana implementacji w testach odbywa się przez wstrzyknięcie małego kontraktu, nie globalny service locator.

## 5. Układ danych na dysku

```text
<repo>/
  config/
    automation/
      state.sqlite3
      state.sqlite3-wal          plik SQLite, nie kopiować samodzielnie
      state.sqlite3-shm          plik SQLite
      worker.lock
      execution.lock
      monitor.lock
      receipts/<job-id>.json     bez sekretów; wersjonowany kontrakt
      backups/<utc>-schema-N.sqlite3
  logs/                          obecny logger AniShift
  workspace/                     poprzedni workspace: bez migracji
    ...                          dotychczasowe źródła i produkty
    temp/
  media/                         edytowalny root nowej funkcji
    .anishift-media-owner.json   ID stanu, nie sekret i nie substytut locka
    inbox/                       źródła użytkownika
    downloads/<transfer-key>/    katalogi należące do klienta torrent
    library/
      .intake/<operation-id>/    własny staging na wolumenie biblioteki
      <safe-title> [<stable-id>]/
        TV/<episode-label>/<revision-id>/
          <stem>.mkv
          <stem>.srt lub <stem>.ass
          <stem>.pl.srt lub <stem>.pl.ass
          <stem>.spoken.pl.*
          <stem>.displayed.pl.*
          <stem>.<audio-codec>
          <stem>.pl.mkv
          temp/                  wyłącznie istniejący lifecycle rdzenia
        OVA/...                  gdy rzeczywiście przypisano taki materiał
        SPECIAL/...
      _unsorted/<job-id>/<revision-id>/
        ...                      lokalny plik bez zgadniętej serii
```

To przykład struktury, nie lista obowiązkowo generowanych produktów. Rzeczywiste suffixy i formaty pochodzą z obecnego presetu i `GroupResult`. Nie wymuszamy jednoczesnego SRT, ASS, każdego kodeka audio oraz MP4, jeśli użytkownik ich nie wybrał.

`downloads`, `inbox`, `library` są rozłączne. Watcher obserwuje tylko zarejestrowany inbox, nigdy downloads, library, receipts, temp lub logów. Dodatkowy watch root wymaga tej samej walidacji rozdzielenia.

Trwała rewizja jest publikowana dopiero po obliczeniu tożsamości kompletu wejść. Tymczasową inspekcję wejścia można wykonać istniejącym probe w `.intake`; po finalnym rename należy utworzyć świeży kontekst AppService dla docelowej ścieżki. Nie planować na absolutnych ścieżkach stagingu, a potem wykonywać takiego planu po przeniesieniu.

`_unsorted` jest pełnoprawną drogą lokalnego użycia. Brak odpowiedzi katalogu nie zatrzymuje lektora, jeśli plik ma poprawne tekstowe napisy. Późniejsze przypisanie serii jest logiczne; automatyczne przenoszenie otwartego filmu jest zabronione.

## 6. Tożsamość i rewizje

### 6.1. Klucze

`SeriesId` to trwałe lokalne ID konkretnego wpisu/serii-sezonu. AniList ID i MAL ID są odrębnymi opcjonalnymi identyfikatorami zewnętrznymi. Dwie części sezonu z różnymi rekordami katalogu nie są scalane samym podobieństwem nazw.

`EpisodeKey = (series_id, kind, number)`. `kind` należy do TV, OVA, ONA, SPECIAL, MOVIE. `number` jest zwalidowanym, skończonym Decimal zapisanym kanonicznym tekstem, nie float. Sortowanie liczb odbywa się w modelu domeny.

Etykieta nieliczbowa, np. `SP-A`, wymaga potwierdzonego mapowania. Nie przypisujemy jej automatycznie numeru 1. Odcinek 7.5 nie jest z definicji recapem.

`SourceBundleDigest` obejmuje hash pliku wideo, wybrane zewnętrzne napisy wraz z ich rolą/językiem oraz kanoniczny opis wybranego źródła tekstu. Zmiana polskiego sidecara przy niezmienionym MKV musi dać inną rewizję.

`ProcessingProfileDigest` obejmuje treściowo istotny snapshot: wymagane produkty, akcję tłumaczenia, język, model, identyfikator wybranego promptu/rewizji, głos oraz parametry wpływające na wynik. Nie obejmuje credentials, timeoutów, liczby wątków i ścieżki biblioteki.

`RevisionId = digest(schema_version, SourceBundleDigest, ProcessingProfileDigest)`. Format skróconego identyfikatora katalogowego może mieć stałą długość, ale rekord zachowuje pełne digests i sprawdza kolizję. Nie polegamy na wbudowanym `hash()` Pythona.

### 6.2. Deduplikacja

Tani fingerprint źródła służy tylko do unikania powtarzania tej samej obserwacji. Ostateczna równość wymaga kompletnego digestu. Provisional job po ukończeniu kopii dostaje końcowy `idempotency_key` w transakcji.

Jeżeli dwa joby mają ten sam pakiet wejść i profil, mogą zostać scalone, a źródła pochodzenia zostają zapisane. Jeżeli potwierdzone tożsamości epizodów są sprzeczne, powstaje decyzja mapowania, nie ciche scalenie różnych serii.

Ten sam plik pokrywający odcinki 1–2 ma jeden job i dwa wpisy `job_episodes`. Jego rozmiar i artefakt liczymy raz. Nie wycinamy automatycznie dwóch filmów bez wiarygodnych granic.

### 6.3. Rewizja aktywna

Poprzedni gotowy produkt pozostaje odtwarzalny podczas przygotowania v2, innego źródła lub nowego głosu. Nowa rewizja nie przejmuje roli aktywnej przed walidacją produktu odtwarzalnego. Historia watched pozostaje przy epizodzie.

Gdy wybrany preset produkuje wyłącznie napisy/audio, job może mieć `ready` w znaczeniu kompletnego zamówienia, ale nie jest automatycznie odtwarzalnym odcinkiem. W UI rozdzielamy „Produkty gotowe” od dostępności „Oglądaj”. Domyślny profil automatyzacji ma jawnie wybrany finalny MKV z lektorem.

## 7. Kontrakt bazy

### 7.1. Reguły globalne

Daty zapisujemy jako UTC Unix milliseconds typu INTEGER; prezentacja używa świadomej strefy czasowej. Numer epizodu pozostaje TEXT. Bool zapisujemy jako INTEGER z CHECK 0/1. JSON jest kanonicznym tekstem z walidacją aplikacji i numerem wersji kontraktu.

Włączamy `PRAGMA foreign_keys=ON` na każdym połączeniu, `journal_mode=WAL`, `synchronous=FULL` dla stanu kolejki i `busy_timeout=5000` jako ostrożny punkt startowy. Wynik otwarcia WAL jest sprawdzany. Aktywna baza nie może leżeć na dysku sieciowym lub w folderze synchronizowanym. [S33, S34]

Każdy wątek używa własnego połączenia. Nie wyłączamy `check_same_thread` w celu współdzielenia jednego cursor. Migracja uzyskuje wyłączność instancji; normalne polecenia nie wykonują DDL. Pierwszy setup może zapisać początkowe preferencje wyłącznie przy zatrzymanym workerze i pod tym samym lockiem. Po uruchomieniu zmiany domeny przechodzą przez komendy.

Własność domeny zapewnia granica kodu, a nie „uprawnienia tabel” SQLite. Obcy proces tego samego konta Windows posiadający dostęp do pliku może go zmienić; nie obiecujemy ochrony przed przejętym lokalnym kontem.

### 7.2. Tabele

Nazwy i role pól poniżej są wiążącym kontraktem planu. Zmiana typu lub znaczenia wymaga aktualizacji kontraktu i migracji, a nie lokalnego zgadywania w kontrolerze.

#### `meta`

- `key TEXT PRIMARY KEY`: klucz stanu globalnego.
- `value_json TEXT NOT NULL`: mała wartość w znanym formacie.
- `version INTEGER NOT NULL`: licznik optimistic concurrency.
- `updated_at INTEGER NOT NULL`: UTC.
- Klucze: schema_version, installation_id, preferences, worker_heartbeat, busy_epoch, dismissed_epoch.
- Preferencje nie zawierają wartości sekretów.
- Migracja wersji schematu jest atomowa z DDL.
- Heartbeat jest informacją diagnostyczną; lock OS jest dowodem żywego ownera.

#### `series`

- `series_id TEXT PRIMARY KEY`: trwałe lokalne ID.
- `anilist_id INTEGER UNIQUE NULL`: tożsamość zewnętrzna, jeżeli potwierdzona.
- `mal_id INTEGER NULL`: oryginalny identyfikator listy.
- `display_title TEXT NOT NULL`: tytuł prezentacyjny.
- `directory_key TEXT NOT NULL UNIQUE`: niezmienny bezpieczny komponent katalogu.
- `format TEXT NOT NULL`: znany format lub jawne UNKNOWN.
- `aliases_json TEXT NOT NULL`: zatwierdzone aliasy oraz ich pochodzenie.
- `catalog_json TEXT NOT NULL`: ograniczony snapshot wybranego rekordu, nie pełna baza.
- `catalog_fetched_at INTEGER NULL`: wiek danych.
- `mal_snapshot_json TEXT NULL`: opcjonalna lista/historyczne liczniki, odrębne od lokalnego watched.
- `created_at INTEGER NOT NULL`, `updated_at INTEGER NOT NULL`.
- Zmiana tytułu nie zmienia directory_key.

#### `episodes`

- `episode_id TEXT PRIMARY KEY`: stabilne ID wiersza.
- `series_id TEXT NOT NULL REFERENCES series(series_id)`.
- `kind TEXT NOT NULL`: zamknięty enum EpisodeKind.
- `number TEXT NOT NULL`: kanoniczny Decimal.
- `source_label TEXT NULL`: oryginalna etykieta przed mapowaniem.
- `expected_at INTEGER NULL`: hint emisji, nie dowód dostępności.
- `desired INTEGER NOT NULL`: wynik jawnego zakresu lub potwierdzonej reguły subskrypcji.
- `skip_reason TEXT NULL`: świadome wyłączenie konkretnego celu.
- `watched_at INTEGER NULL`: wyłącznie jawne lokalne oznaczenie lub zaakceptowany import historii.
- `preferred_job_id TEXT NULL`: wskazanie wybranej rewizji po zweryfikowaniu relacji coverage.
- `created_at INTEGER NOT NULL`, `updated_at INTEGER NOT NULL`.
- UNIQUE(series_id, kind, number).
- Nie wykonujemy kaskadowego DELETE filmów ani watched przy usunięciu subskrypcji.

#### `subscriptions`

- `subscription_id TEXT PRIMARY KEY`.
- `series_id TEXT NOT NULL UNIQUE REFERENCES series(series_id)`.
- `mode TEXT NOT NULL`: ongoing, backlog, future_collect.
- `enabled INTEGER NOT NULL`, `paused INTEGER NOT NULL`.
- `policy_json TEXT NOT NULL`: zakres, grupy, aliasy, źródła, numeracja, jakość, limit zapasu.
- `profile_json TEXT NOT NULL`: zaakceptowany snapshot treści bez sekretów.
- `profile_digest TEXT NOT NULL`.
- `version INTEGER NOT NULL`: optimistic concurrency ustawień.
- `next_check_at INTEGER NULL`, `last_successful_check_at INTEGER NULL`.
- `last_attempt_at INTEGER NULL`, `last_error_code TEXT NULL`.
- `created_at INTEGER NOT NULL`, `updated_at INTEGER NOT NULL`.
- Indeks `(enabled, paused, next_check_at)` wspiera terminy.
- Jedna subskrypcja serii zawiera ewentualne fallbacki grup, a nie kilka konkurujących timerów.

#### `releases`

- `release_id TEXT PRIMARY KEY`: stabilne ID indeksu lub znormalizowanego locatora.
- `provider TEXT NOT NULL`, `provider_key TEXT NOT NULL`.
- `infohash TEXT NULL`: dopiero po normalizacji obsługiwanego formatu.
- `title TEXT NOT NULL`, `locator TEXT NOT NULL`.
- `published_at INTEGER NULL`, `seen_at INTEGER NOT NULL`.
- `features_json TEXT NOT NULL`: jakość deklarowana, grupa, wersja, zakres i provenance parsera.
- `match_json TEXT NOT NULL`: decyzja dopasowania wraz z przyczynami.
- `series_id TEXT NULL REFERENCES series(series_id)`.
- UNIQUE(provider, provider_key).
- Locator jest danymi wejściowymi do adaptera, nigdy argumentem powłoki.
- Zmiana statystyk seeders nie tworzy nowej tożsamości wydania.

#### `transfers`

- `transfer_id TEXT PRIMARY KEY`.
- `operation_id TEXT NOT NULL UNIQUE`: zapisany przed add.
- `infohash TEXT UNIQUE NULL`: niezgodny/nieznany hash nie staje się losowym substytutem.
- `ownership TEXT NOT NULL`: OWNED albo BORROWED.
- `release_id TEXT NULL REFERENCES releases(release_id)`.
- `client_identity_json TEXT NOT NULL`: zatwierdzony endpoint/capabilities i identyfikacja klienta, bez hasła.
- `locator TEXT NOT NULL`, `save_path TEXT NULL`.
- `intent_json TEXT NOT NULL`: zaakceptowany wybór i hash manifestu.
- `observation_json TEXT NOT NULL`: ostatni odczyt klienta, nie własny silnik transferu.
- `reconcile_state TEXT NOT NULL`: pending, known, unresolved, missing.
- `observed_at INTEGER NULL`, `retry_at INTEGER NULL`, `error_code TEXT NULL`.
- `created_at INTEGER NOT NULL`, `updated_at INTEGER NOT NULL`.
- Własność nie wynika z samej nazwy kategorii ani pojedynczego niepełnego odczytu.

#### `transfer_files`

- `transfer_id TEXT NOT NULL REFERENCES transfers(transfer_id)`.
- `file_index INTEGER NOT NULL`: rzeczywisty index API.
- `relative_path TEXT NOT NULL`: zwalidowana ścieżka klienta.
- `size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0)`.
- `selected INTEGER NOT NULL`, `priority INTEGER NOT NULL`.
- `progress REAL NOT NULL`: obserwacja API, nie numer odcinka.
- `manifest_version INTEGER NOT NULL`.
- `coverage_json TEXT NOT NULL`: potwierdzony zbiór epizodów.
- `job_id TEXT NULL`: przyjęty job, jeżeli istnieje.
- `observed_at INTEGER NOT NULL`.
- PRIMARY KEY(transfer_id, file_index).
- Odczyt zmienionej nazwy/rozmiaru dla indeksu unieważnia poprzedni wybór.

#### `jobs`

- `job_id TEXT PRIMARY KEY`.
- `idempotency_key TEXT NOT NULL UNIQUE`: provisional lub finalny klucz, nigdy NULL/pusty.
- `origin_kind TEXT NOT NULL`: manual, inbox, torrent.
- `origins_json TEXT NOT NULL`: zachowane referencje po deduplikacji.
- `source_bundle_digest TEXT NULL`: brak do ukończenia kontrolowanego intake.
- `profile_digest TEXT NOT NULL`, `profile_json TEXT NOT NULL`.
- `revision_id TEXT NULL`, `revision_root TEXT NULL`.
- `state TEXT NOT NULL`: enum JobState.
- `stage TEXT NULL`: aktualny etap rdzenia/aktywność.
- `priority INTEGER NOT NULL`, `generation INTEGER NOT NULL`.
- `retry_scope TEXT NULL`, `retry_at INTEGER NULL`, `attempts INTEGER NOT NULL`.
- `error_code TEXT NULL`, `safe_message TEXT NULL`.
- `cancel_requested INTEGER NOT NULL`.
- `core_group_id TEXT NULL`, `core_run_id TEXT NULL`.
- `required_products_json TEXT NOT NULL`.
- `created_at INTEGER NOT NULL`, `updated_at INTEGER NOT NULL`.
- Indeksy `(state, retry_at, priority)` oraz `(revision_id)`.
- Zmiana stanu i event muszą być zapisane razem.

#### `job_episodes`

- `job_id TEXT NOT NULL REFERENCES jobs(job_id)`.
- `episode_id TEXT NOT NULL REFERENCES episodes(episode_id)`.
- `mapping_source TEXT NOT NULL`: explicit, confirmed_rule, import.
- `mapping_version INTEGER NOT NULL`.
- PRIMARY KEY(job_id, episode_id).
- Jeden film może pokrywać wiele epizodów bez duplikacji fizycznego produktu.
- Konflikt mapowania nie jest naprawiany przez usunięcie historii oglądania.

#### `artifacts`

- `artifact_id TEXT PRIMARY KEY`: globalne ID automatyzacji, nie samo core artifact_id.
- `job_id TEXT NOT NULL REFERENCES jobs(job_id)`.
- `core_artifact_id TEXT NOT NULL`, `role TEXT NOT NULL`.
- `relative_path TEXT NOT NULL`: względem konkretnej revision_root.
- `size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0)`.
- `sha256 TEXT NOT NULL`.
- `status TEXT NOT NULL`: verified, missing, invalid, superseded.
- `playable INTEGER NOT NULL`: wynik walidacji roli/formatu, nie nazwy rozszerzenia.
- `validated_at INTEGER NOT NULL`, `created_at INTEGER NOT NULL`.
- UNIQUE(job_id, core_artifact_id).
- Plik jest referencją do zakończonego produktu; częściowy staging nie trafia jako verified.

#### `commands`

- `command_id TEXT PRIMARY KEY`: generowany przed pierwszym submit.
- `kind TEXT NOT NULL`: zamknięty enum komend.
- `payload_json TEXT NOT NULL`, `payload_digest TEXT NOT NULL`.
- `state TEXT NOT NULL`: pending, claimed, completed, rejected.
- `generation INTEGER NOT NULL`, `priority INTEGER NOT NULL`.
- `created_at INTEGER NOT NULL`, `claimed_at INTEGER NULL`, `finished_at INTEGER NULL`.
- `result_json TEXT NULL`: bezpieczny receipt lub walidowana odmowa.
- Indeks `(state, priority, created_at)`.
- Ten sam command_id z innym payload_digest jest konfliktem, nie nową próbą.
- Frontend wykonuje INSERT/odczyt; claim i finish należą do workera.

#### `events`

- `sequence INTEGER PRIMARY KEY AUTOINCREMENT`.
- `job_id TEXT NULL`, `command_id TEXT NULL`.
- `kind TEXT NOT NULL`, `generation INTEGER NOT NULL`.
- `occurred_at INTEGER NOT NULL`.
- `payload_json TEXT NOT NULL`: mały bezpieczny opis zmiany.
- Aktualny snapshot, nie pełny replay eventów, jest prawdą po reconnect.
- Event terminalny publikujemy z transakcją stanu.
- Nie zapisujemy każdego tokena tłumaczenia ani każdej klatki UI.

#### `provider_state`

- `provider_key TEXT PRIMARY KEY`: host + rodzaj integracji.
- `status TEXT NOT NULL`: available, backoff, auth_required, blocked, schema_changed, unknown.
- `retry_at INTEGER NULL`, `last_success_at INTEGER NULL`.
- `failure_count INTEGER NOT NULL`, `error_code TEXT NULL`.
- `capabilities_json TEXT NOT NULL`: obserwowane możliwości, wersja i czas probe.
- `budget_json TEXT NOT NULL`: ostatnie limity i odroczenia.
- Stan jednego hosta wpływa na wszystkie korzystające z niego subskrypcje.

#### `http_cache`

- `cache_key TEXT PRIMARY KEY`: host, metoda, kanoniczny query/variables.
- `provider_key TEXT NOT NULL`.
- `etag TEXT NULL`, `last_modified TEXT NULL`.
- `body BLOB NOT NULL`: wyłącznie ograniczone publiczne dane, bez tokenów.
- `content_type TEXT NOT NULL`.
- `fetched_at INTEGER NOT NULL`, `expires_at INTEGER NOT NULL`, `last_used_at INTEGER NOT NULL`.
- `schema_version INTEGER NOT NULL`.
- Cache odczytowego GraphQL nie obejmuje mutacji.
- Retencja usuwa nieużywane odpowiedzi, a nie series/jobs/artifacts. Klucze zakończonych komend oraz digests potrzebne do deduplikacji pozostają; ewentualne odchudzanie payloadów zachowuje minimalny receipt.

### 7.3. Migracja i backup

DDL w `schema.sql` nie jest dowolnym skryptem pobranym z sieci. Migrator uruchamia wyłącznie wersje dostarczone z kodem i sprawdza docelowy numer schematu.

Przed migracją: zatrzymany worker, zamknięte przyjmowanie nowych komend, wspólny lock, spójny backup przez `sqlite3.Connection.backup`, otwarcie i `integrity_check` kopii. Backup obejmuje stan i receipts, nie multimedia i nie credentials.

Migracja ma jedną jawną granicę transakcji. Nie zakładać, że `executescript()` uruchomione wewnątrz wcześniej otwartej transakcji zachowa tę granicę: jego zachowanie trzeba uwzględnić w implementacji. Albo wykonujemy znane instrukcje przez kontrolowany executor, albo skrypt zawiera i egzekwuje własne BEGIN/COMMIT. Test wymusza wyjątek w środku migracji i brak częściowego schematu. [S34]

Nowszy schemat niż obsługiwany przez kod oznacza odmowę startu, nie próbę „naprawy” przez reset bazy. Rollback wymaga zatrzymanych writerów i jawnego wyboru zgodnego backupu. Po restore uzgadniamy stan klienta torrent oraz istniejące produkty.

## 8. Publiczne kontrakty nowych modułów

Poniższe sygnatury są kontraktem projektowym. Istniejące typy importujemy z ich publicznych modułów; nie tworzymy duplikatów.

```python
class AutomationClient:
    def submit_command(self, envelope: CommandEnvelope) -> CommandReceipt: ...
    def read_snapshot(self, query: LibraryQuery) -> LibrarySnapshot: ...
    def read_events(self, after_sequence: int, limit: int = 200) -> tuple[AutomationEvent, ...]: ...

class AutomationStore:
    def transition_job(self, job_id: str, expected: JobState,
                       generation: int, change: JobChange) -> bool: ...
    def claim_command(self, generation: int, now_ms: int) -> CommandEnvelope | None: ...
    def complete_command(self, command_id: str, generation: int,
                         result: CommandResult) -> bool: ...

class PipelineRunner:
    def prepare(self, job: JobSnapshot, cancel: CancellationToken) -> PreparedEpisode: ...
    def execute(self, prepared: PreparedEpisode, sink: RunEventSink) -> RunResult: ...
    def cancel(self, job_id: str, generation: int) -> bool: ...

class QbitAdapter:
    def capabilities(self) -> ClientCapabilities: ...
    def reconcile(self, intent: DownloadIntent) -> TransferObservation: ...
    def read_files(self, transfer_id: str) -> tuple[TransferFile, ...]: ...
    def apply_selection(self, selection: AcceptedManifest) -> TransferObservation: ...

class AniListProvider:
    def search(self, query: str, page: int = 1) -> CatalogPage: ...
    def get_media(self, media_id: int) -> CatalogMedia: ...
    def get_airing(self, media_id: int, after_ms: int) -> tuple[AiringHint, ...]: ...

class NyaaProvider:
    def poll_feed(self, query: ReleaseQuery) -> ReleasePage: ...
    def search_history(self, query: ReleaseQuery, cursor: str | None) -> ReleasePage: ...
```

### 8.1. Komenda

`CommandEnvelope` zawiera `command_id`, `kind`, `schema_version`, `payload` i `created_at`. Każdy kind ma własny walidowany payload. Nie ma pola shell command, python code, SQL lub listy dowolnych endpointów do wykonania.

Dozwolone intencje: import_source, search_catalog, search_releases, start_download, subscribe, update_subscription, pause_subscription, resume_subscription, cancel_job, pause_transfer, resume_transfer, check_now, mark_watched, unmark_watched, bind_unsorted, choose_revision, update_preferences, dismiss_monitor, stop_worker.

Operacje wymagające nieodwracalnej zmiany systemowej, takie jak instalacja autostartu, pozostają jawną lokalną akcją setupu; worker nie uzyskuje dowolnego interfejsu do Task Scheduler.

### 8.2. Wynik wyszukiwania

`CatalogPage`: items, page, has_next, query_generation, fetched_at, stale, problems. Nieobecny tytuł English nie jest błędem. Rok częściowy nie jest zamieniany na 1 stycznia.

`ReleasePage`: items, cursor, complete_for_query, fetched_at, source_state, problems. `complete_for_query=False` przy limitach i niedostępnej historii ma pozostać widoczne; nie twierdzimy, że anime nie istnieje.

`MatchDecision`: verdict accepted/rejected/needs_confirmation, matched_alias, numbering_rule_version, quality_evidence, language_evidence, reasons. Fuzzy score nie zastępuje jawnej tożsamości.

### 8.3. Snapshot biblioteki

Każdy wiersz zawiera series/episode label, stan transferu, stan joba, etap, znany procent lub activity, dostępne produkty, playable, watched, wymagane działanie i wiek danych. Ścieżki mogą być pokazane lokalnie po żądaniu; logi i eksport diagnostyczny są redagowane.

Snapshot ma `sequence` i `generated_at`. Po utracie eventów frontend ponownie odczytuje snapshot, zamiast odtwarzać stan z niepełnego historycznego strumienia.

## 9. Stany, retry i skutki zewnętrzne

| Stan joba | Wejście | Dozwolony kolejny stan | Dowód przejścia |
| --- | --- | --- | --- |
| waiting_source | Wybrany cel bez gotowego źródła | waiting_file, attention, cancelled | Znalezione i przyjęte wydanie lub jawna decyzja. |
| waiting_file | Oczekiwany plik/metadata/producent | copying, attention, cancelled | Konkretne źródło dopuszczone do stabilnego odczytu. |
| copying | Własny staging i operation_id | validating, waiting_file, attention, cancelled | Zamknięta kopia, integralny bundle i zgodna tożsamość źródła. |
| validating | Kompletny pakiet wejść | queued, attention, cancelled | Media/text/quality/disk admission oraz finalna tożsamość rewizji. |
| queued | Poprawne wejścia czekają na slot | processing, attention, cancelled | Execution lock i zaakceptowany plan. |
| processing | Wykonywany plan rdzenia | ready, partial, attention, cancelled | Zweryfikowane GroupResult i produkty. |
| ready | Wymagany zestaw produktów istnieje | attention | Zewnętrzny brak/uszkodzenie; nowy profil tworzy nowy job. |
| partial | Zachowane poprawne produkty, brak reszty | queued, attention, cancelled | Jawne ograniczone retry brakującego zakresu. |
| attention | Potrzebna decyzja lub naprawa | Stan właściwy dla wskazanego retry_scope | Zapisana konkretna korekta, nie dowolny restart całej funkcji. |
| cancelled | Przerwane konkretne zlecenie | waiting_file lub queued po jawnym wznowieniu | Nowa generation i ponowna walidacja, bez używania starego callbacka. |

Tabela wymaga sprawdzenia generation przy każdym wyniku z wątku. Obserwacja qBittorrent `checking`, `moving`, `stalled` nie staje się nowym enumem nadrzędnego pipeline; pozostaje w TransferObservation.

### 9.1. Klasy błędów

| Kod | Skutek | Ponowienie |
| --- | --- | --- |
| provider_timeout | Stare dane pozostają widoczne | Backoff tego hosta. |
| provider_rate_limited | Bez nowych żądań do terminu | Najpóźniejszy z nagłówków i lokalnego budżetu. |
| provider_auth_required | Wymaga uwagi | Po poprawie credentials lub jawnym probe. |
| provider_schema_changed | Adapter niedostępny | Nie zamieniać na pustą listę. |
| source_incomplete | waiting_file | Po nowej obserwacji producenta. |
| source_changed | Odrzucona własna kopia | Nowa bezpieczna próba, bez kasowania źródła. |
| mapping_required | Brak automatycznego wyboru torrenta | Po wyborze tożsamości/numeracji. |
| subtitles_missing | attention przed tłumaczeniem | Inne źródło tekstu lub inne wydanie. |
| subtitles_ambiguous | attention | Jeden jawny wybór zapisany jako reguła. |
| quality_rejected | Niedopuszczone źródło | Inne wydanie; nie automatyczny upscale. |
| disk_budget_exceeded | Nie przyjmuj nowej pracy | Po zwolnieniu miejsca przez użytkownika. |
| execution_busy | queued | Gdy obecny właściciel zwolni lock. |
| product_invalid | partial/attention | Walidacja i ponowienie tylko odpowiedniego etapu. |
| product_missing | Biblioteka zachowuje historię | Uzgodnij zachowane źródła/artefakty. |
| client_unavailable | Transfery czekają | Import lokalny nadal działa. |
| unsupported_capability | Odmowa konkretnej operacji | Wspierana konfiguracja klienta lub jawna droga ręczna. |

### 9.2. Miejsca awarii

| Okno awarii | Stan zachowany | Działanie po restarcie |
| --- | --- | --- |
| Przed INSERT komendy | Brak side effectu | Użytkownik może ponowić. |
| Po INSERT, przed claim | Pending command | Nowy worker przejmuje raz. |
| Po add intent, przed request | Operation ID | Uzgodnij, potem ewentualnie wyślij. |
| Po request add, przed odpowiedzią | Intent + oczekiwany hash | Szukaj istniejącego transferu; nie dodawaj ślepo ponownie. |
| Po pojawieniu się metadata | Manifest niezaakceptowany | Nie uruchamiaj całej paczki. |
| W środku kopii | Własny .intake i job | Nie traktuj stagingu jako źródła gotowego. |
| Po rename, przed commit | Plik/receipt i stara faza | Sprawdź digest oraz pochodzenie, dokończ transakcję. |
| Po zakończeniu tłumaczenia | Zwalidowany trwały produkt, jeżeli opublikowany | Reużyj zgodną rolę przez planner. |
| W trakcie requestu TTS | Nieukończony etap | Może wymagać powtórzenia; brak obietnicy wznowienia chunku. |
| Po finalnym MKV, przed ready | Produkt i plan rewizji | Waliduj, zarejestruj, dopiero pokaż Oglądaj. |
| Po zamknięciu monitora | Worker nadal żyje | Nie anuluj, nie odtwarzaj okna w tym samym epoch. |
| Po restore backupu | Stan może być starszy niż klient/produkty | Reconciliation przed nowymi mutacjami. |

Nie istnieje transakcja SQLite obejmująca klient torrent, plik NTFS i usługę TTS. Mechanizm zapewnia idempotentne przyjęcie i uzgadnianie; nie używać nieudowodnionej obietnicy „exactly once” dla dowolnej zewnętrznej usługi.

## 10. Integracje: dokładne granice

### 10.1. AniList

Endpoint katalogu: `https://graphql.anilist.co`. Publiczny odczyt nie wymaga dodawania logowania właściciela. Zapytania korzystają z variables, nie wklejania tekstu użytkownika w GraphQL. [S17]

Kształt podstawowego zapytania do potwierdzenia w T004:

```graphql
query SearchAnime($search: String!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { currentPage hasNextPage }
    media(type: ANIME, search: $search) {
      id
      idMal
      title { english romaji native }
      synonyms
      format
      status
      episodes
      startDate { year month day }
      nextAiringEpisode { episode airingAt }
    }
  }
}
```

Osobne `Media(id: ...)` pobiera szczegóły wybranego rekordu oraz bezpośrednie relacje. Nie ściągać rekurencyjnie całej franczyzy i wszystkich powiązanych tytułów. `AiringSchedule` jest pobierany dla konkretnego media i ograniczonego okna; brak kolejnego wpisu nie wyłącza RSS.

Dokumentacja API nie jest dowodem odpowiedzi aktualnego endpointu. T004 potwierdza pola oraz nullability małym odczytem. GraphQL może zwrócić `errors` z HTTP 200; parser nie może na tej podstawie ogłosić braku anime.

Normalizacja wyszukiwania: NFKC, casefold, odstępy i wybrane warianty interpunkcji. Zachowujemy cyfry, Part, Season, II i istotne podtytuły. Najpierw exact alias, potem fuzzy ranking. Nie używamy jednego arbitralnego progu podobieństwa jako zezwolenia na automatyczne pobranie.

Gdy pierwotne zapytanie nie daje wyników, dopuszczone są maksymalnie dwa kontrolowane warianty krótszego zapytania po usunięciu wyłącznie dekoracyjnej interpunkcji; UI pokazuje zastosowany wariant. Lokalny cache aliasów pomaga dla wcześniej wybranych serii. Nie obiecujemy odnalezienia dowolnie zniekształconego tytułu z całej bazy.

### 10.2. Nyaa

Pierwsze źródło to skonfigurowany host `nyaa.si`. `page=rss`, `q`, `c`, `f` i paginacja `p` pochodzą z udokumentowanego kodu/istniejącego parsera; ich bieżące działanie trzeba potwierdzić w T004. Kategoria English-translated jest filtrem indeksu, nie gwarancją pełnych dialogów konkretnego MKV. [S23–S25]

RSS: bezpieczny parser XML, namespace nyaa, tytuł, guid, data, infoHash, link magnet/.torrent, cechy i statystyki. Brak elementu opcjonalnego nie wywraca całego feedu. Brak wymaganej tożsamości odrzuca konkretny rekord.

Historia: wyszukiwanie po zatwierdzonych aliasach, ograniczona paginacja HTML, deduplikacja po identyfikacji, wykrywanie powtarzającej się strony oraz jawne „pokaż więcej”. Nie kodować jako prawdy stałych 75 rekordów i nie używać CSS jako niezmiennego API.

Po przekroczeniu budżetu historycznego wynik jest częściowy. Ręczne wybranie zakończonego sezonu nie może dostać zapewnienia „wszystkie odcinki” na podstawie jednego feedu najnowszych publikacji.

Nie instalujemy zdalnych pluginów wyszukiwarki przy każdym starcie. Nie obchodzimy challenge, blokad i limitów przez rotację kont, proxy lub CAPTCHA solver.

### 10.3. Drugi RSS i AnimeTosho

Nowy adapter `RssProvider` obsługuje jawnie skonfigurowany publiczny URL feedu z HTTPS, ograniczonym body i tym samym modelem wydania. Host i przekierowania są walidowane. Prywatne URL z tokenem w query nie są zakresem domyślnego publicznego feedu.

AnimeTosho ma opis API typu Newznab, ale nie został tu dowiedziony aktualny kontrakt `caps` i filtrów. Nie dodajemy fikcyjnego kompletnego adaptera. Feed działający w przyjętym kontrakcie może być skonfigurowany po próbie; osobny pełny Newznab adapter nie jest niezbędny dla końca lokalnego zakresu. [S29]

### 10.4. qBittorrent

Wybrana stabilna biblioteka: `qbittorrent-api==2026.8.1`. Wersja klienta nie jest odgadywana. T003 zapisuje rzeczywiste app/version, webapiVersion i zachowanie potrzebnych operacji. [S20–S22]

Połączenie jest lokalne, uwierzytelnione i ograniczone do loopback. Nie wyłączamy autoryzacji, Host validation ani CSRF w celu uproszczenia kodu. Ręcznie wybrany port jest częścią setupu; nie skanujemy całej sieci.

Dla znanego BTIH najpierw odczyt istniejącego transferu. Obcy istniejący hash jest BORROWED. Przy nierozstrzygniętym pochodzeniu po awarii wybór konserwatywny to BORROWED/attention, nie przejęcie według samej kategorii AniShift.

Tylko potwierdzona ścieżka metadata-only może służyć do automatycznego przyjęcia nieznanej paczki. Samo `is_stopped=True` nie jest zakładane jako gwarancja otrzymania metadata magnetu. Próbę `stop_condition=MetadataReceived` wykonujemy na przypiętej parze klient/wrapper. Brak możliwości zatrzymuje automatyczny wybór plików paczki, zamiast po cichu pobierać wszystko.

Przy nieznanej tożsamości lokalnego `.torrent` albo pure v2, dowód kompatybilności musi uwzględnić rozpoznanie duplikatu bez przejmowania cudzych danych. Jeżeli klient nie pozwala tego zapewnić, ta forma wejścia jest odrzucana z konkretną przyczyną; podstawowy download z Nyaa korzysta z potwierdzonego infoHash/BTIH.

Po metadata: zapis manifestu, jawne zaakceptowanie wyboru, priority=0 dla niewybranych, normalny priorytet dla wybranych według rzeczywistych indeksów. Różnica między rozmiarem wybranych plików a bajtami współdzielonych pieces jest wyjaśniona w podglądzie.

Per-file intake: `progress == 1`, zgodny rozmiar, aktualny path, brak moving/checking i poprawny odczyt. Nie wymagamy końca całego torrenta ani zamknięcia klienta. Nie stosujemy deny-write lock watchera jako warunku ukończenia pliku qBit: klient może utrzymywać uchwyty do kompletnego pliku paczki. Kopia oraz walidacja mają osobny kontrakt.

Brak pobierania EXE, BAT, CMD, PS1, DLL, skryptów, archiwów i próbek. Nie uruchamiamy pobranych plików. Odtwarzacz jest wcześniej wybraną lokalną aplikacją.

### 10.5. Polski/angielski tekst

Preferujemy zatwierdzony pełny polski tekst. Ustawiamy `TranslationAction.DO_NOT_TRANSLATE`. Angielski pełny tekst przechodzi istniejące tłumaczenie. Francuski-only nie jest cichym fallbackiem.

Odrzucamy oczywiste signs-only, songs-only, OP/ED, bitmapy i hardsub jako jedyne źródło dialogów. Nie uruchamiamy nowego OCR/ASR. Brak języka/konflikt kilku ścieżek daje konkretny wybór.

Jedna angielska tekstowa ścieżka z zaufanego profilu wydania może zostać przyjęta bez ręcznej decyzji przy każdym odcinku. To praktyczna polityka, nie dowód semantycznej kompletności. Nazwa grupy, napis Raw i kraj grupy nie zastępują inspekcji ścieżek.

Dokładne wskazanie tracka/artifactu korzysta z `GroupIntent(mode=MANUAL)` i `plan_manual`. `AutoPreset` nie może zawierać ręcznych ID; obchodzenie tej walidacji jest zabronione. Całe wykonanie pozostaje w `AppService.execute`. [S43]

## 11. Wartości startowe i limity

To decyzje projektowe do edycji i kalibracji, nie pomiary na komputerze właściciela ani obietnice dostawców.

| Parametr | Default | Granica / znaczenie |
| --- | --- | --- |
| min_resolution | 1080 | W zwykłym search nie wyświetlać niższych klas. |
| preferred_resolution | 1080 | Wyższe dopuszczone, ale nie wymuszone zamiast sensownego 1080. |
| allow_higher | true | 2160 itp. bez obietnicy dostępności każdego anime. |
| managed_active_transfers | 0 (bez limitu) | AniShift nie dubluje kolejki klienta; limit aktywnych pobrań ustawia się w qBittorrent. Wartość > 0 jest opcjonalnym dodatkowym ograniczeniem. |
| inbox_scan_interval | 5 s | Skan tylko zarejestrowanych rootów. |
| quiet_seconds | 15 s | Heurystyka obcego producenta, nie dowód zakończenia. |
| monitor_mode | on_local_intake | Jedno okno przy nowej lokalnej partii. |
| worker_tick_max_sleep | 1 s | Poll workera, nie obietnica reakcji UI na każdym sprzęcie. |
| active_client_poll | 5 s | Jeden współdzielony odczyt, nie po jednym per odcinek. |
| idle_client_poll | 60 s | Brak aktywnych transferów nie wymaga częstego odczytu. |
| ongoing_without_airing | 60 min | Brak kalendarza nie wyłącza pobierania. |
| first_check_after_airing | 30 min | Hint, nie gwarancja istnienia napisów. |
| post_airing_dense_window | co 15 min przez 6 h | Ograniczone wspólnym budżetem hosta. |
| post_airing_late_window | co 60 min przez następne 24 h | Następnie co 6 h. |
| timing_jitter | do 10% interwału | Nie skraca Retry-After. |
| initial_anilist_budget | 10/min | Aktualne nagłówki mogą narzucić ostrzejszy limit. |
| public_index_budget | 6/min na host | Współdzielony dla UI i harmonogramu. |
| http_connect_timeout | 5 s | Kontrolowany błąd, bez zamrożenia renderera. |
| http_read_timeout | 20 s | Osobny od deadline całego przebiegu. |
| http_write_timeout | 20 s | Nie traktować jako dowodu nieprzyjęcia requestu. |
| http_pool_timeout | 5 s | Ograniczona pula, nie nowe połączenie per widget. |
| max_decoded_body | 8 MiB | Limit także po dekompresji. |
| max_feed_items | 1000 | Przekroczenie oznacza ograniczony wynik, nie pełną historię. |
| search_page_size | 20 | Stronicowanie w TUI. |
| search_debounce | 300 ms | Generacja zabezpiecza spóźnione odpowiedzi. |
| history_pages_per_check | 5 | Kontynuacja cursor w kolejnym dozwolonym oknie. |
| default_backlog_ready_limit | 3 | Wyłącznie default; future_collect może świadomie zbierać sezon. |
| disk_free_floor | 10 GiB | Ponad szacowaną rezerwę aktywnej pracy. |
| unused_http_cache_retention | 30 dni | Nie dotyczy biblioteki, historii i aktywnych zadań. |
| transient_retry_delays | 30 s, 2 min, 10 min, 30 min | Potem ograniczone godzinne próby do zmiany stanu. |
| auth_or_schema_retries | 0 po rozpoznaniu | Wymaga poprawy/probe, nie spamowania endpointu. |
| public_command_payload_limit | 64 KiB | Duże manifesty zapisywane przez worker, komenda niesie ID i wybór. |

Nieznana jakość nie pojawia się jako poprawne 1080p. Może być pokazana w osobnej sekcji „Wymaga weryfikacji”. Deklarowane 1080p jest ponownie sprawdzane po pobraniu. Przy znanym panoramicznym cropie klasa 1920-wide jest odrębną jawną regułą; nie wolno dowolnego małego pliku uznać za 1080p po samej nazwie.

Dla materiału bez deklarowanej klasy wymagamy co najmniej rozmiaru odpowiadającego 1920×1080; wyjątek cropu wymaga potwierdzonej deklaracji wydania i szerokości co najmniej 1920. Przeplot i niejednoznaczne proporcje wymagają uwagi. Nie obiecujemy jakości kodowania na podstawie samej rozdzielczości.

Równoległość pobierania jest ustawieniem użytkownika, nie polityką AniShift: domyślnie transfery nie mają limitu po stronie AniShift, bo qBittorrent ma własną kolejkę i własne limity aktywnych pobrań. Przetwarzanie działa dokładnie tak jak dzisiejsze Auto: jedna partia gotowych grup w jednym runie GraphScheduler z jego obecnymi limitami; nie ma osobnego parametru liczby równoległych jobów.

Zasoby providerów: 429 respektowane wspólnie; brak klucza/quota nie przełącza na płatne konto lub innego dostawcę bez zapisanej polityki. Deklaracja właściciela o bezpłatnym dostępie nie uzasadnia nieograniczonej pętli prób.

## 12. Harmonogram i kompletność

Daty emisji przechowujemy w UTC, wyświetlamy domyślnie w `Europe/Warsaw`. Przeliczanie lokalnego czasu nie może produkować naiwnego datetime. Okna aktywności przechodzą test przejścia DST; monotonic clock służy wyłącznie do długości oczekiwania, nie daty premiery.

Jedno uruchomienie po tygodniu offline wykonuje jedno planowane catch-up na serię zgodnie z budżetem, a nie odtwarza setki nieodbytych ticków. Jeżeli zakres RSS nie pokrywa przerwy, używa ograniczonej historii. Nie ogłasza pełnej kompletności po samym przejrzeniu świeżego feedu.

`desired` jest zbiorem epizodów: zakres wybrany przez użytkownika, potwierdzone emisje i wydania oraz świadomie wybrane dodatki. `missing = desired - ready - active_coverage - explicitly_skipped`. Awaria aktywnego joba pozostaje widoczna i nie prowadzi do drugiego równoległego transferu tego samego celu.

„Następny do zdobycia” to najmniejszy niepokryty regularny epizod w tym zbiorze. „Następny do oglądania” wybieramy spośród gotowych, nieoznaczonych watched. Licznik MAL nie wyznacza żadnej z tych wartości bez zaakceptowanego mapowania i zakresu.

OVA/ONA/specials są widoczne oddzielnie i mogą wskazywać osobny rekord katalogu. Relacja sequel nie upoważnia do pobrania kolejnego sezonu bez zgody. Kalendarz lub katalog może nie wiedzieć o każdym dodatku; UI mówi o znanych pozycjach, nie gwarantuje pełności całej franczyzy.

## 13. Interfejs i obsługa

### 13.1. Home

Kolejność: Auto, Ręczny, Anime, Biblioteka, Harmonogram, Ustawienia, Wyjście. Pierwsze Auto pozostaje domyślnie zaznaczone, więc Enter zachowuje obecny sens. Nowa liczba wierszy wymaga dostosowania geometrii menu, a nie tylko dopisania etykiet.

„Anime” otwiera edytor tytułu. Enter zatwierdza wyszukiwanie/wybór kontekstowo. Strzałki tylko nawigują. Space zaznacza odcinki. Pobranie ma jedno jawne podsumowanie plików, grupy, jakości i miejsca; nie uruchamia się po samym przesunięciu kursora.

Zwykły tekst w Home nie jest powłoką ani ukrytym importem. Wklejenie ścieżki w edytorze ustawień pozostaje edycją tego pola.

### 13.2. Widok serii

Nagłówek: tytuł, alternatywny tytuł, rok, format, identyfikator katalogu. Dalej: „Pobierz wybrane”, „Obserwuj nowe”, „Zbieraj na później”, grupy wydań oraz sekcja dodatków.

Wyniki wydań grupujemy według epizodu i grupy. Grupa oraz uploader to różne pola. W ścisłej polityce brak grupy oznacza oczekiwanie, a nie automatyczne przejście na inną. W polityce fallback kolejność jest jawna.

W paczce wiersz wskazuje rzeczywisty plik i numerację. Jeden wspólny plik 1–2 wymaga pobrania całego pliku; podgląd mówi to przed zgodą. Wybór wykluczonych extras/sampli nie jest domyślny.

### 13.3. Monitor

Jeden wiersz na źródło, etap i rzeczywista aktywność/procent. Brak znanego procentu nie jest uzupełniany liczbą wynikającą z upływu czasu. Gotowy odcinek otrzymuje akcję Oglądaj nawet wtedy, gdy niżej dalej trwają inne zadania.

Zamknięcie okna monitora kończy wyłącznie widok. Anulowanie konkretnego joba, pauza subskrypcji i stop workera są trzema różnymi akcjami z osobnymi payloadami.

### 13.4. Lista Wymaga uwagi

Każdy wpis pokazuje przyczynę i najbliższą sensowną akcję: wskaż serię, potwierdź numerację, wybierz pełne napisy, sprawdź połączenie, zwolnij miejsce, użyj innego wydania lub ponów konkretny etap. Nie otwieramy obowiązkowego formularza wszystkich ustawień dla jednego błędu.

### 13.5. Kanoniczna gramatyka nowych poleceń

Wszystkie poniższe polecenia są projektowane, nie obecnie wdrożone. `--state-root PATH` jest wspólną opcją każdej podkomendy roboczej, umieszczaną po jej nazwie. Dzięki temu argumenty Task Scheduler i ręcznego monitora są identyczne semantycznie.

```text
anishift automation setup [--state-root PATH]
anishift automation worker [--state-root PATH]
anishift automation monitor [--state-root PATH]
anishift automation status [--state-root PATH] [--json]
anishift automation stop [--state-root PATH]
anishift automation check-now [--state-root PATH] [--series ID]
anishift automation pause [--state-root PATH] [--series ID | --intake]
anishift automation resume [--state-root PATH] [--series ID | --intake]
anishift automation import PATH [--state-root PATH] [--series ID] [--episode NUMBER]
anishift automation doctor [--state-root PATH] [--network]
anishift automation autostart enable [--state-root PATH]
anishift automation autostart disable [--state-root PATH]
anishift automation autostart status [--state-root PATH]
```

`pause` bez selektora wstrzymuje nowe automatyczne przyjęcia i sprawdzanie subskrypcji, nie anuluje aktywnego rdzenia ani nie zatrzymuje obcych torrentów. `stop` zatrzymuje worker z kontrolowanym anulowaniem jego pracy, nie zamyka qBittorrent.

Nowe polecenia zwracają 0 po wykonaniu/zaakceptowaniu komendy, 1 przy kontrolowanej odmowie/braku workera, 2 dla błędu składni. Asynchroniczny receipt zawiera job/command ID i nie obiecuje, że film już jest gotowy. Istniejące `run --preset` zachowuje 0/1/3/4 i dotychczasowy kontrakt.

### 13.6. Autostart

Task XML ma LogonTrigger bieżącego SID, InteractiveToken, LeastPrivilege, MultipleInstances IgnoreNew, pełne ścieżki executable/cwd/state_root. `pythonw.exe -m anishift.cli.automation_entry automation worker --state-root ...` nie ma otwierać terminala bez potrzeby.

Task jest instalowany dopiero po jawnym potwierdzeniu. Instalator odczytuje go ponownie i porównuje trigger, executable, arguments i principal. Sam exit code schtasks nie stanowi końcowego dowodu poprawnego logowania. [S35]

Nie ustawiamy wake timers, pracy przed logowaniem, SYSTEM, hasła konta lub podwyższonych uprawnień. Uśpiony lub wyłączony PC nie pobiera; przy następnym działającym uruchomieniu następuje catch-up.

## 14. Weryfikacja i granice gotowości

P00 sprawdza ryzyka zanim duży zakres zostanie zakodowany. Krytyczne próby: Python 3.14 i nowe zależności, qBit metadata-only/per-file, AniList/Nyaa transport oraz użycie publicznego rdzenia w izolowanym katalogu. Niepowodzenie blokuje zależną integrację, nie legalny lokalny import działający bez niej.

P14 dostarcza deterministyczne scenariusze od końca do końca z syntetycznymi mediami i kontrolowanymi providerami. P15 oddzielnie wymaga rzeczywistego Windows, ograniczonych prób sieciowych oraz odbioru właściciela. Nie zamieniamy testów stubów na dowód dostępności zewnętrznych usług.

Warunek końca całego zakresu: wybór anime/paczki/subskrypcji, lokalny drop, niezależna gotowość pliku, restart, działający autostart oraz przegląd gotowego odcinka przez właściciela. Dostępny lokalny import nie pozwala oznaczyć całego downloadu jako ukończonego, gdy nie ma klienta.

Bramki repo przed każdym commitem implementacyjnym:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Nie zastępować pełnego `pytest` przez `pytest tests/`: repo zawiera również testy współdzielonych utils w konfiguracji testpaths. Targeted testy służą do pracy nad zadaniem, nie zastępują wymaganych bramek. [S02, S10]

### 14.1. Akceptacja przez właściciela

Właściciel wybiera jedną bieżącą serię, jeden zakończony sezon/paczkę i jeden własny lokalny plik. Sprawdza wybór klawiaturą, widoczność grup/jakości, brak dodatkowych trzech Enterów, gotowość pierwszego odcinka przed resztą oraz możliwość wyłączenia monitora.

Osobno odsłuchuje lektora i sprawdza obecność dialogów. Ten plan nie ocenia rzeczywistej jakości tłumaczenia grup ani nowych głosów bez materiału i odsłuchu.

Próba skali: 15 subskrypcji × 12 regularnych epizodów jako syntetyczny zestaw 180 rekordów, dodatkowo luki, dodatki, v2 i kilka aktywnych transferów. To dane testowe wynikające z opisanego obciążenia, nie pomiar rzeczywistej biblioteki właściciela.

### 14.2. Punkty zatrzymania i korekta planu

Nie uruchamiać automatycznego batch add bez dowodu metadata-only. Nie dopuszczać nadpisywania źródeł, wykonywania danych z feedu i ręcznego omijania autoryzacji klienta. Nie dopisywać fałszywego PASS, gdy brak Windows, dostępu do klienta lub odsłuchu.

Zmiana jednego pola odpowiedzi providera jest lokalną adaptacją adaptera. Zmiana właściciela stanu, magazynu, modelu tożsamości, polityki ochrony źródeł lub zakresu MAL/VPS wymaga aktualizacji decyzji i zależnych kart przed kodowaniem.

## 15. Etapy i szczegółowe zadania

Każda faza ma obserwowalny wynik. Szczegóły implementacji zaczynają się poniżej; wszystkie pochodzą z tego samego kontraktu, nie z oddzielnych sprzecznych mini-planów.

### Mapa faz

| Faza | Zadania | Stan osiągany |
| --- | --- | --- |
| [P00](#p00) | T001–T008 | Znana baza i sprawdzone ryzyka zewnętrzne |
| [P01](#p01) | T009–T016 | Stabilne kontrakty tożsamości i własności |
| [P02](#p02) | T017–T024 | Zastąpiona przez [Plan 01](plans/01-watch-mode.md) |
| [P03](#p03) | T025–T032 | Zastąpiona przez [Plan 01](plans/01-watch-mode.md) |
| [P04](#p04) | T033–T040 | Zastąpiona przez [Plan 01](plans/01-watch-mode.md) |
| [P05](#p05) | T041–T048 | Tytuł, alias i kalendarz są dostępne jako dane katalogowe |
| [P06](#p06) | T049–T056 | Wydania są filtrowane i dopasowane przed pobraniem |
| [P07](#p07) | T057–T064 | Własne transfery są kontrolowane, obce pozostają nietknięte |
| [P08](#p08) | T065–T072 | Sezon/paczka i nietypowa numeracja są obsługiwane |
| [P09](#p09) | T073–T080 | Wybrana raz seria jest pozyskiwana bez cotygodniowego klikania |
| [P10](#p10) | T081–T088 | Właściciel widzi uporządkowane gotowe odcinki i luki |
| [P11](#p11) | T089–T096 | Pełny workflow jest dostępny w aktualnym terminalu |
| [P12](#p12) | T097–T104 | Zastąpiona przez [Plan 01](plans/01-watch-mode.md) |
| [P13](#p13) | T105–T112 | Lokalny setup i naprawy wyjątków są zrozumiałe |
| [P14](#p14) | T113–T120 | Codzienne scenariusze i awarie mają powtarzalny dowód |
| [P15](#p15) | T121–T128 | Właściciel otrzymuje działające lokalne wdrożenie |

<a id="p00"></a>

## P00. Przypięcie kodu i sprawdzenie ryzyk integracyjnych

**Wynik fazy:** Znana baza i sprawdzone ryzyka zewnętrzne.

**Wejście:** Załączniki, bieżący kod oraz możliwość izolowanych prób.

**Warunek wyjścia:** Zapisane ograniczenia środowiska; biblioteki, qBit i publiczne kontrakty mają osobne dowody lub jawne blokady.

**Status fazy:** planned.

<a id="t001"></a>

### T001. Przypnij bazę i granice zmian

**Status:** planned.

**Cel:** Ustal dokładny kod, na którym agent realizuje cały zakres, bez podmiany aktualnego produktu na historyczne TUI.

**Wymagania:** [R01](spec.md#r01), [R02](spec.md#r02), [R27](spec.md#r27).

**Zależności obowiązkowe:** Początek zakresu; najpierw rozpoznanie bazy.

**Kolejność planowa:** T001; poprzednia karta: brak.

**Kontrakt / symbol:** `BaselineManifest`.

#### Pliki i zakres edycji

- `docs/work/local-automation/baseline.md`
- `AGENTS.md`
- `anishift/application/AGENTS.md`
- `tests/AGENTS.md`

**Istotna granica:** Przeczytane źródła i rzeczywiste wykonanie to różne klasy dowodu.

#### Kolejność implementacji

1. Porównaj HEAD z bc74425b487fb9110da76911c26dca4194b2aad9; zapisz SHA i różnice istotne dla wymienionych modułów.

2. Wykonaj git status --short; nie przenoś, nie resetuj i nie commituj cudzych zmian.

3. Przeczytaj root i obszarowe AGENTS, w tym tests/AGENTS.md, przed edycją tych obszarów.

4. Potwierdź publiczne sygnatury AppContext, create_app_service, AppService.plan_auto oraz execute.

5. Zapisz faktyczny interpreter, system i dostępność uv; wersję Python pobierz z procesu, nie z nazwy folderu.

6. Oznacz stare liczby testów z załącznika jako historyczne; nowy wynik może powstać tylko z rzeczywistego uruchomienia.

7. Utwórz gałąź pierwszej fazy (`feature/local-automation-p00`) z właściwego punktu bazowego, jeśli wykonawca otrzymał zgodę na implementację; każda kolejna faza dostaje własną gałąź i PR z aktualnego `main`.

8. Zapisz manifest bazy i listę rozbieżności; blokuj wyłącznie zadania, których publiczny kontrakt rzeczywiście się zmienił.

#### Scenariusze weryfikacji

<a id="t001-c01"></a>

##### T001-C01

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Czysty checkout przypiętego SHA.

**Działanie:** Zbuduj manifest bazy.

**Oczekiwany rezultat:** SHA, interpreter i istniejące ścieżki są zapisane.

**Niedopuszczalny skutek:** Nie ma deklaracji uruchomienia nieuruchomionych testów.

**Rekord dowodu:** `T001-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t001-c02"></a>

##### T001-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Checkout zawiera cudzy niezacommitowany plik.

**Działanie:** Wykonaj rozpoznanie.

**Oczekiwany rezultat:** Plik pozostaje identyczny; kolizja zakresu jest opisana.

**Niedopuszczalny skutek:** Nie użyto reset --hard ani stash bez zgody.

**Rekord dowodu:** `T001-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t001-c03"></a>

##### T001-C03

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** HEAD zmienił implementację execute.

**Działanie:** Porównaj kontrakt.

**Oczekiwany rezultat:** Zadania mostka wskazują konkretną różnicę do adaptacji.

**Niedopuszczalny skutek:** Nie przepisano planu na podstawie samej nazwy brancha.

**Rekord dowodu:** `T001-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t001-c04"></a>

##### T001-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Manifest istnieje z poprzedniej sesji.

**Działanie:** Wznów rozpoznanie.

**Oczekiwany rezultat:** Nowa data i SHA są porównane z poprzednimi.

**Niedopuszczalny skutek:** Nie zastąpiono poprzednich dowodów fikcyjnym PASS.

**Rekord dowodu:** `T001-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Usuń wyłącznie nowy dokument rozpoznania; nie zmieniaj kodu, konfiguracji ani cudzych commitów.

**Podstawa techniczna:** [S01](research.md#s01), [S02](research.md#s02), [S03](research.md#s03), [S05](research.md#s05), [S12](research.md#s12).

<a id="t002"></a>

### T002. Sprawdź cztery nowe biblioteki na Python 3.14

**Status:** planned.

**Cel:** Potwierdź, że minimalny zestaw zależności działa na docelowym interpreterze i nie wymaga przebudowy aplikacji.

**Wymagania:** [R02](spec.md#r02), [R23](spec.md#r23), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T001](#t001)

**Kolejność planowa:** T002; poprzednia karta: T001.

**Kontrakt / symbol:** `test_runtime_dependencies`.

#### Pliki i zakres edycji

- `pyproject.toml`
- `uv.lock`
- `tests/automation/test_dependencies.py`

**Istotna granica:** Niepowodzenie zgodności biblioteki wymaga konkretnej zamiany i aktualizacji planu, nie fikcyjnego dopisania PASS.

#### Kolejność implementacji

1. W izolowanym środowisku sprawdź qbittorrent-api==2026.8.1, anitopy==2.1.1, rapidfuzz==3.14.6 i defusedxml==0.7.1.

2. Dodaj zaakceptowane wersje przez uv add; nie edytuj ręcznie sekcji zależności.

3. Uruchom import każdej biblioteki oraz minimalne wywołanie parsera i funkcji podobieństwa na Python 3.14.

4. Potwierdź wheel RapidFuzz dla Windows x64; błąd runtime VC++ pokaż jako konkretny brak instalacyjny.

5. Sprawdź błędny XML i DTD przez defusedxml; ograniczenie rozmiaru odpowiedzi pozostaje zadaniem kodu HTTP.

6. Zapisz wersje zależności przechodnich w uv.lock, bez zbiorczego upgrade pozostałych providerów.

7. Zestaw deklarowane licencje z dystrybucją projektu; nie kopiuj całych skryptów GPL tylko dlatego, że repo jest publiczne.

8. Oznacz import testowany na Linux oddzielnie od Windows; nie zastępuj brakującego Windows wynikiem innej platformy.

#### Scenariusze weryfikacji

<a id="t002-c01"></a>

##### T002-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Izolowany Python 3.14 z lockiem.

**Działanie:** Zaimportuj cztery biblioteki.

**Oczekiwany rezultat:** Wszystkie importy i dwa małe wywołania przechodzą.

**Niedopuszczalny skutek:** Nie zainstalowano drugiej aplikacji terminalowej.

**Docelowy test:** `tests/automation/test_dependencies.py::test_dependencies_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t002-c02"></a>

##### T002-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nazwa Unicode i pusty tytuł.

**Działanie:** Wywołaj parser oraz ranking.

**Oczekiwany rezultat:** Wynik ma kontrolowany typ; pusty tekst nie daje trafienia automatycznego.

**Niedopuszczalny skutek:** Nie użyto samodzielnie starego anitopy jako resolvera serii.

**Docelowy test:** `tests/automation/test_dependencies.py::test_dependencies_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t002-c03"></a>

##### T002-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** XML zawiera encję zewnętrzną.

**Działanie:** Wywołaj bezpieczny parser.

**Oczekiwany rezultat:** Dane zostają odrzucone bez odczytu pliku i połączenia.

**Niedopuszczalny skutek:** Nie uruchomiono standardowego parsera w fallbacku.

**Docelowy test:** `tests/automation/test_dependencies.py::test_dependencies_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t002-c04"></a>

##### T002-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Środowisko odbudowane z uv.lock.

**Działanie:** Powtórz smoke importów.

**Oczekiwany rezultat:** Użyte są te same stabilne wersje.

**Niedopuszczalny skutek:** Nie pobrano wersji latest/dev bez aktualizacji dowodu.

**Docelowy test:** `tests/automation/test_dependencies.py::test_dependencies_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_dependencies.py
```

**Wycofanie:** Cofnij tylko wpisy dodanych pakietów przez uv remove i odpowiednią zmianę locka; nie ruszaj istniejących providerów.

**Podstawa techniczna:** [S10](research.md#s10), [S21](research.md#s21), [S30](research.md#s30), [S31](research.md#s31), [S32](research.md#s32).

<a id="t003"></a>

### T003. Zweryfikuj metadata-only i gotowość pojedynczego pliku

**Status:** planned.

**Cel:** Przed napisaniem downloadera udowodnij krytyczny kontrakt paczek na rzeczywistej, jawnie udostępnionej instancji qBittorrent.

**Wymagania:** [R08](spec.md#r08), [R11](spec.md#r11), [R16](spec.md#r16), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T001](#t001), [T002](#t002)

**Kolejność planowa:** T003; poprzednia karta: T002.

**Kontrakt / symbol:** `QbitCapabilityProof`.

#### Pliki i zakres edycji

- `tests/automation/test_qbittorrent_contract.py`
- `docs/work/local-automation/proofs/qbittorrent.md`

**Istotna granica:** Ta próba wymaga uruchomionego klienta i zgody na test. W pakiecie planistycznym pozostaje niewykonana.

#### Kolejność implementacji

1. Zapytaj lokalny WebUI o wersję aplikacji i API; brak klienta ma dać potrzebę konfiguracji, nie automatyczną instalację.

2. Użyj własnego małego legalnego torrenta z dwoma plikami testowymi; nie pobieraj prywatnych odcinków użytkownika.

3. Zweryfikuj na parze klient/wrapper zachowanie stop_condition=MetadataReceived oraz is_stopped zgodnie z negocjowaną wersją.

4. Po odebraniu metadanych ustaw zerowy priorytet wszystkich plików, następnie normalny tylko wybranych indeksów.

5. Odczytaj faktyczne index, name, size, progress i priority; sprawdź, że index nie jest pozycją elementu w odpowiedzi.

6. Ukończ pierwszy wybrany plik, pozostaw drugi niekompletny i potwierdź możliwość bezpiecznego odczytu pierwszego.

7. Przetestuj timeout odpowiedzi add oraz ponowne wyszukanie po infohash bez ponownego pobierania.

8. Zapisz odpowiedzi z usuniętymi sekretami i mapę wspieranych funkcji; niesprawdzony metadata-only blokuje automatyczne batch add, nie import plików.

#### Scenariusze weryfikacji

<a id="t003-c01"></a>

##### T003-C01

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Klient ze znaną wersją i testowym torrentem.

**Działanie:** Pobierz wyłącznie metadane.

**Oczekiwany rezultat:** Lista plików jest dostępna przed świadomym startem danych.

**Niedopuszczalny skutek:** Nie ustawiono automatycznego pobierania całej paczki.

**Rekord dowodu:** `T003-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t003-c02"></a>

##### T003-C02

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Pierwszy plik 100%, drugi 20%.

**Działanie:** Sprawdź pierwszy plik.

**Oczekiwany rezultat:** Pierwszy może wejść do kontrolowanej kopii.

**Niedopuszczalny skutek:** Nie wymagano torrent.progress == 1 dla całej paczki.

**Rekord dowodu:** `T003-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t003-c03"></a>

##### T003-C03

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Serwer przyjął add, odpowiedź zginęła.

**Działanie:** Uzgodnij po infohash.

**Oczekiwany rezultat:** Powstaje jedno przypisanie transferu.

**Niedopuszczalny skutek:** Nie wykonano ślepo drugiego add.

**Rekord dowodu:** `T003-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t003-c04"></a>

##### T003-C04

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Restart testowego klienta.

**Działanie:** Odczytaj listę i stany.

**Oczekiwany rezultat:** Indeksy oraz wybrane priorytety zostają poprawnie odtworzone.

**Niedopuszczalny skutek:** Nie rozpoznano ukończenia wyłącznie z istnienia pliku.

**Rekord dowodu:** `T003-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_qbittorrent_contract.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Usuń wyłącznie własny testowy torrent za osobną zgodą; żadna operacja sprzątania nie może obejmować istniejących torrentów użytkownika.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21), [S22](research.md#s22).

<a id="t004"></a>

### T004. Sprawdź kontrakty katalogu i indeksu bez pobierania anime

**Status:** planned.

**Cel:** Uzyskaj mały, wersjonowany zestaw odpowiedzi transportowych do parserów, nie kopię całej bazy anime.

**Wymagania:** [R03](spec.md#r03), [R18](spec.md#r18), [R23](spec.md#r23), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T001](#t001)

**Kolejność planowa:** T004; poprzednia karta: T003.

**Kontrakt / symbol:** `ProviderContractProof`.

#### Pliki i zakres edycji

- `tests/automation/test_provider_contracts.py`
- `docs/work/local-automation/proofs/providers.md`

**Istotna granica:** Sukces odczytu dokumentacji nie zastępuje tej próby transportowej.

#### Kolejność implementacji

1. Wykonaj po jednym ograniczonym zapytaniu AniList Search, Media i AiringSchedule z budżetem 10 żądań na minutę.

2. Potwierdź dostępność id, idMal, title, synonyms, format, status, episodes i nextAiringEpisode w bieżącym schemacie.

3. Pobierz jeden publiczny wynik RSS Nyaa i jeden HTML wyszukiwania, bez uruchamiania pobierania multimediów.

4. Zweryfikuj parametry q, c, f, p i page=rss na aktualnym wdrożeniu; różnicę względem kodu upstream zapisz jawnie.

5. Zidentyfikuj pustą poprawną odpowiedź, stronę blokady oraz brak wymaganych pól jako trzy różne wyniki.

6. Zapisz minimalne fixture z fikcyjnymi tytułami i zachowaną strukturą; nie utrwalaj tokenów, cookies ani kont użytkownika.

7. Sprawdź warunkowy GET RSS, 429 i timeouts przez lokalny stub, nawet jeśli żywe źródło ich teraz nie zwraca.

8. Udokumentuj granice paginacji jako wynik obserwacji, a nie stałą obietnicę 75 rekordów na każdej stronie.

#### Scenariusze weryfikacji

<a id="t004-c01"></a>

##### T004-C01

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Poprawny JSON GraphQL z jednym anime.

**Działanie:** Zweryfikuj pola.

**Oczekiwany rezultat:** Parser tworzy media i emisję z typowanym UTC.

**Niedopuszczalny skutek:** Nie zakłada się obecności następnego odcinka dla każdego tytułu.

**Rekord dowodu:** `T004-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t004-c02"></a>

##### T004-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Poprawny pusty RSS.

**Działanie:** Zmapuj wynik.

**Oczekiwany rezultat:** Wynik ma status OK i zero wydań.

**Niedopuszczalny skutek:** Nie oznaczono serwisu jako uszkodzonego.

**Docelowy test:** `tests/automation/test_provider_contracts.py::test_provider_probe_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t004-c03"></a>

##### T004-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** HTTP 200 zawiera stronę challenge.

**Działanie:** Zmapuj wynik.

**Oczekiwany rezultat:** Źródło ma stan niedostępne lub zmieniony format.

**Niedopuszczalny skutek:** Nie ogłoszono braku nowych odcinków.

**Docelowy test:** `tests/automation/test_provider_contracts.py::test_provider_probe_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t004-c04"></a>

##### T004-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Serwis był offline przez kilka godzin.

**Działanie:** Ponów z warunkowym pobraniem.

**Oczekiwany rezultat:** Zachowane zostają stare dane wraz z ich wiekiem.

**Niedopuszczalny skutek:** Nie wyzerowano harmonogramu subskrypcji.

**Docelowy test:** `tests/automation/test_provider_contracts.py::test_provider_probe_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_provider_contracts.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Usuń wyłącznie zanonimizowane fixture niepasujące do kontraktu; konfiguracja kont i prywatne dane pozostają nietknięte.

**Podstawa techniczna:** [S15](research.md#s15), [S16](research.md#s16), [S17](research.md#s17), [S18](research.md#s18), [S23](research.md#s23), [S24](research.md#s24), [S25](research.md#s25).

<a id="t005"></a>

### T005. Zabezpiecz regresje aktualnego Auto

**Status:** planned.

**Cel:** Potwierdź publiczną drogę przygotowania jednego odcinka bez uruchamiania nowych płatnych lub prywatnych usług.

**Wymagania:** [R02](spec.md#r02), [R07](spec.md#r07), [R11](spec.md#r11), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T001](#t001)

**Kolejność planowa:** T005; poprzednia karta: T004.

**Kontrakt / symbol:** `test_existing_core_baseline`.

#### Pliki i zakres edycji

- `tests/automation/test_core_baseline.py`
- `docs/work/local-automation/proofs/core.md`

**Istotna granica:** Nie obiecuje się wznowienia pojedynczego nieukończonego requestu TTS.

#### Kolejność implementacji

1. Przygotuj syntetyczny MKV z krótkim audio i tekstowymi napisami, używając istniejących narzędzi testowych repo.

2. Wywołaj create_app_service z izolowanym katalogiem zamiast globalnego workspace użytkownika.

3. Zidentyfikuj grupę przez discover i zaplanuj tylko tę grupę przez plan_auto.

4. Zastubuj granice sieci tłumaczenia i TTS; nie przedstawiaj tego testu jako testu żywych providerów.

5. Sprawdź GroupResult.products i preserved_products oraz suffixy rzeczywiście publikowanych plików.

6. Powtórz próbę z polskimi napisami i jawną polityką pominięcia tłumaczenia.

7. Uruchom istniejące root gates w osobnej fazie weryfikacji, zapisując dokładne polecenia i rzeczywiste wyniki.

8. Zapisz, które wejścia i wyniki można reużyć bez zmiany obecnego GraphScheduler.

#### Scenariusze weryfikacji

<a id="t005-c01"></a>

##### T005-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Krótki MKV z pełnym angielskim tekstem.

**Działanie:** Przejdź przez publiczną fasadę.

**Oczekiwany rezultat:** Powstają wymagane produkty z poprawnymi rolami.

**Niedopuszczalny skutek:** Nie powstał alternatywny pipeline.

**Docelowy test:** `tests/automation/test_core_baseline.py::test_core_baseline_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t005-c02"></a>

##### T005-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Polski sidecar i stub liczący tłumaczenia.

**Działanie:** Uruchom preset PL.

**Oczekiwany rezultat:** Liczba wywołań tłumacza wynosi zero.

**Niedopuszczalny skutek:** Nie przełożono polskiego tekstu ponownie.

**Docelowy test:** `tests/automation/test_core_baseline.py::test_core_baseline_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t005-c03"></a>

##### T005-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Stub TTS zwraca błąd.

**Działanie:** Odczytaj RunResult.

**Oczekiwany rezultat:** Częściowy wynik pozostaje częściowy, z zapisanymi produktami.

**Niedopuszczalny skutek:** Nie ogłoszono pełnej gotowości.

**Docelowy test:** `tests/automation/test_core_baseline.py::test_core_baseline_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t005-c04"></a>

##### T005-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Zwalidowane produkty istnieją po przerwaniu.

**Działanie:** Ponownie zaplanuj tę samą rewizję.

**Oczekiwany rezultat:** Planner wykorzystuje wyłącznie zgodne produkty.

**Niedopuszczalny skutek:** Nie przyjęto obecności pliku za dowód jakości.

**Docelowy test:** `tests/automation/test_core_baseline.py::test_core_baseline_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_core_baseline.py
```

**Wycofanie:** Wycofaj tylko nowe testy porównawcze; nie poprawiaj przy tej okazji historycznego długu terminala.

**Podstawa techniczna:** [S03](research.md#s03), [S05](research.md#s05), [S06](research.md#s06), [S12](research.md#s12), [S13](research.md#s13), [S14](research.md#s14).

<a id="t006"></a>

### T006. Zapisz pierwszeństwo aktualnej specyfikacji

**Status:** planned.

**Cel:** Usuń konflikt dokumentacyjny między starym planem jednego kroku a obecnym pełnym zakresem lokalnym.

**Wymagania:** [R01](spec.md#r01), [R15](spec.md#r15), [R27](spec.md#r27), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T001](#t001)

**Kolejność planowa:** T006; poprzednia karta: T005.

**Kontrakt / symbol:** `LocalAutomationScope`.

#### Pliki i zakres edycji

- `docs/work/local-automation/spec.md`
- `docs/work/local-automation/masterplan.md`
- `AGENTS.md`

**Istotna granica:** Ten pakiet rozstrzyga zakres; konfiguracja kont i autostartu nadal wymaga świadomej zgody przy wdrożeniu.

#### Kolejność implementacji

1. Wskaż najnowsze polecenie właściciela jako źródło zakresu wyszukiwarka + download + watcher + subskrypcje + biblioteka.

2. Oznacz poprzedni brief jednego wycinka i propozycję VPS jako historyczne w tym workstreamie.

3. Zachowaj obecne menu i maskotkę jako baseline; nie wdrażaj ponownie starego projektu slash-commandów.

4. Dopuść osobny automation media root poza legacy workspace; nie rozluźniaj globalnie zasad kasowania temp.

5. Zapisz, że każdy katalog rewizji odcinka jest osobnym płaskim workspace dla rdzenia.

6. Wskaż opcjonalny import XML MAL oraz jawny brak automatycznego zapisu do MAL w tej edycji.

7. Zapisz decyzje właściciela wymagane przy setupie: klient, folder, grupy, autostart, zachowanie monitora.

8. Połącz zadania z wymaganiami R01–R30; oznacz wszystkie implementacje jako planned do czasu rzeczywistego odbioru.

#### Scenariusze weryfikacji

<a id="t006-c01"></a>

##### T006-C01

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Stary brief mówi o jednym kroku.

**Działanie:** Odczytaj nową specyfikację.

**Oczekiwany rezultat:** Aktualny zakres obejmuje pełną automatyzację lokalną.

**Niedopuszczalny skutek:** Nie przywrócono VPS jako zależności.

**Rekord dowodu:** `T006-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t006-c02"></a>

##### T006-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Legacy workspace zawiera prywatne pliki.

**Działanie:** Sprawdź reguły layoutu.

**Oczekiwany rezultat:** Nie jest wymagane ich przeniesienie.

**Niedopuszczalny skutek:** Nie przewidziano masowej migracji na starcie.

**Rekord dowodu:** `T006-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t006-c03"></a>

##### T006-C03

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Brak ustawionych preferowanych grup.

**Działanie:** Oceń gotowość setupu.

**Oczekiwany rezultat:** Wybór grup jest jawną decyzją, z neutralną opcją bez preferencji.

**Niedopuszczalny skutek:** Nie przypisano użytkownikowi odgadniętej grupy.

**Rekord dowodu:** `T006-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t006-c04"></a>

##### T006-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Wykonawca wraca po zmianie specyfikacji.

**Działanie:** Porównaj rewizję decyzji.

**Oczekiwany rezultat:** Powiązane taski zostają ponownie ocenione.

**Niedopuszczalny skutek:** Nie zmieniono historycznie wykonanych wyników bez notatki.

**Rekord dowodu:** `T006-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Przywróć jedynie zmodyfikowane fragmenty dokumentacji tej funkcji; nie zmieniaj dawnych wyników audytu.

**Podstawa techniczna:** [S01](research.md#s01), [S02](research.md#s02), [S07](research.md#s07), [S08](research.md#s08).

<a id="t007"></a>

### T007. Przygotuj małe, legalne i deterministyczne fixture

**Status:** planned.

**Cel:** Dostarcz realistyczne przykłady wejść bez magazynowania cudzych odcinków lub prywatnych danych.

**Wymagania:** [R19](spec.md#r19), [R23](spec.md#r23), [R26](spec.md#r26), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T001](#t001)

**Kolejność planowa:** T007; poprzednia karta: T006.

**Kontrakt / symbol:** `automation_fixture_factory`.

#### Pliki i zakres edycji

- `tests/automation/conftest.py`
- `tests/automation/fixtures/README.md`

**Istotna granica:** Nazwy serii w przykładach są syntetyczne i nie opisują listy użytkownika.

#### Kolejność implementacji

1. Utwórz fikcyjne serie Aster Journey i Aster Journey Second Season z aliasami, różnymi ID i datami.

2. Przygotuj nazwy wydań 1080p, 2160p, 720p, v2, zakres 01–12, 7.5 oraz numerację absolutną 013.

3. Zbuduj minimalne JSON AniList, RSS Nyaa, HTML indeksu i odpowiedzi qBittorrent na podstawie udokumentowanych kształtów.

4. Dodaj warianty pustej listy, brakującego pola, błędnej daty, nieznanej kategorii i strony challenge.

5. Wygeneruj krótkie media lokalnie; znakowane role ścieżek: English Full, Signs & Songs, Polish oraz bitmapa.

6. Wprowadź kontrolowany zegar UTC i deterministyczny generator jitter w testach harmonogramu.

7. Udostępnij lokalny stub HTTP z licznikiem żądań i wymuszaną utratą odpowiedzi po mutacji.

8. Opisz pochodzenie fixture i granice symulacji; testy domyślne nie mogą dotykać sieci.

#### Scenariusze weryfikacji

<a id="t007-c01"></a>

##### T007-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Dwie serie o podobnym tytule.

**Działanie:** Wczytaj katalog testowy.

**Oczekiwany rezultat:** ID sezonów pozostają odrębne.

**Niedopuszczalny skutek:** Nie zastosowano jednego oczekiwanego ID do wszystkich nazw.

**Docelowy test:** `tests/automation/conftest.py::test_test_fixtures_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t007-c02"></a>

##### T007-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nazwa epizodu zawiera 7.5.

**Działanie:** Przetwórz fixture numeracji.

**Oczekiwany rezultat:** Wartość nie przechodzi przez float.

**Niedopuszczalny skutek:** Nie zrównano 7.5 z 7 ani 8.

**Docelowy test:** `tests/automation/conftest.py::test_test_fixtures_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t007-c03"></a>

##### T007-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Test sieciowy nie ma jawnego markera.

**Działanie:** Uruchom suite domyślny.

**Oczekiwany rezultat:** Nie ma żadnego zewnętrznego requestu.

**Niedopuszczalny skutek:** Nie użyto kluczy z .env użytkownika.

**Docelowy test:** `tests/automation/conftest.py::test_test_fixtures_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t007-c04"></a>

##### T007-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Próba jest uruchomiona drugi raz.

**Działanie:** Odtwórz katalog fixture.

**Oczekiwany rezultat:** Treść i oczekiwane wyniki pozostają identyczne.

**Niedopuszczalny skutek:** Nie oparto testu na bieżącej dacie premiery.

**Docelowy test:** `tests/automation/conftest.py::test_test_fixtures_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/
```

**Wycofanie:** Usuń tylko wygenerowane testowe media spod tmp_path; fixture tekstowe pozostają małe i pozbawione danych prywatnych.

**Podstawa techniczna:** [S12](research.md#s12), [S24](research.md#s24), [S25](research.md#s25).

<a id="t008"></a>

### T008. Ustal publiczne granice przed równoległymi zmianami

**Status:** planned.

**Cel:** Zdefiniuj niewielkie wejścia automatyzacji, aby UI nie sterował plikami, providerami ani schedulerem bezpośrednio.

**Wymagania:** [R02](spec.md#r02), [R20](spec.md#r20), [R25](spec.md#r25), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T005](#t005), [T006](#t006)

**Kolejność planowa:** T008; poprzednia karta: T007.

**Kontrakt / symbol:** `AutomationClient.submit_command / read_snapshot`.

#### Pliki i zakres edycji

- `anishift/automation/__init__.py`
- `tests/automation/test_public_api.py`
- `docs/work/local-automation/masterplan.md`

**Istotna granica:** Cały kod implementacyjny tych interfejsów powstaje w późniejszych zadaniach, nie w pakiecie planistycznym.

#### Kolejność implementacji

1. Wyeksportuj AutomationClient dla frontendu oraz AutomationWorker dla procesu właściciela stanu.

2. Zdefiniuj submit_command(command_id, kind, payload) i read_snapshot(since_sequence) jako granice frontendowe.

3. Zdefiniuj use case intake, search, subscribe, cancel_job, retry_job i mark_watched; każda mutacja ma trwały command_id.

4. Zdefiniuj typowane wyniki SearchPage, LibrarySnapshot, AttentionItem i OperationReceipt.

5. Zachowaj providerów jako zwykłe moduły z małymi funkcjami, bez dynamicznego rejestru pluginów.

6. Umieść wspólny kontrakt ReleasePage dla Nyaa i custom RSS, bo to rzeczywiście dwie implementacje.

7. Zabroń importów cli z automation oraz importów downloadera z rendererów.

8. Zapisz architekturę zależności i jeden przykład przejścia command → worker → AppService → snapshot.

#### Scenariusze weryfikacji

<a id="t008-c01"></a>

##### T008-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Frontend chce pobrać odcinek.

**Działanie:** Wywołaj submit_command.

**Oczekiwany rezultat:** Powstaje komenda, a nie transfer wykonany w renderze.

**Niedopuszczalny skutek:** Nie wywołano qBittorrent z render().

**Docelowy test:** `tests/automation/test_public_api.py::test_vertical_contract_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t008-c02"></a>

##### T008-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Dwa źródła RSS zwracają wydania.

**Działanie:** Zmapuj ReleasePage.

**Oczekiwany rezultat:** Oba używają tego samego kontraktu i kluczy.

**Niedopuszczalny skutek:** Nie powstały oddzielne kolejki historii.

**Docelowy test:** `tests/automation/test_public_api.py::test_vertical_contract_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t008-c03"></a>

##### T008-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nieznany rodzaj komendy.

**Działanie:** Zwaliduj granicę.

**Oczekiwany rezultat:** Powstaje odmowa o stabilnym kodzie.

**Niedopuszczalny skutek:** Nie uruchomiono dynamicznego importu lub powłoki.

**Docelowy test:** `tests/automation/test_public_api.py::test_vertical_contract_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t008-c04"></a>

##### T008-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Frontend odtwarza command_id po timeout.

**Działanie:** Wywołaj granicę ponownie.

**Oczekiwany rezultat:** Otrzymuje ten sam rezultat lub stan oczekiwania.

**Niedopuszczalny skutek:** Nie uruchomiono drugiej operacji.

**Docelowy test:** `tests/automation/test_public_api.py::test_vertical_contract_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_public_api.py
```

**Wycofanie:** Wycofaj publiczne eksporty nowych modułów i dokument kontraktów; stary AppService pozostaje nienaruszony.

**Podstawa techniczna:** [S03](research.md#s03), [S05](research.md#s05), [S07](research.md#s07), [S12](research.md#s12).

<a id="p01"></a>

## P01. Kontrakty domeny, konfiguracja i własność plików

**Wynik fazy:** Stabilne kontrakty tożsamości i własności.

**Wejście:** P00: rozpoznane ograniczenia.

**Warunek wyjścia:** Model rozróżnia serie, dodatki, rewizje, źródła, watched i stany; ścieżki nie mogą wyjść poza root.

**Status fazy:** planned.

<a id="t009"></a>

### T009. Zamodeluj serię, epizod i rewizję niezależnie od nazwy pliku

**Status:** planned.

**Cel:** Zapewnij stabilne ID rozróżniające tytuł, sezon, typ treści, numer odcinka i konkretną wersję produktu.

**Wymagania:** [R04](spec.md#r04), [R15](spec.md#r15), [R19](spec.md#r19), [R20](spec.md#r20).

**Zależności obowiązkowe:** [T006](#t006), [T008](#t008)

**Kolejność planowa:** T009; poprzednia karta: T008.

**Kontrakt / symbol:** `SeriesId / EpisodeKey / RevisionId`.

#### Pliki i zakres edycji

- `anishift/automation/models.py`
- `tests/automation/test_models.py`

**Istotna granica:** Zewnętrzny sezon to konkretne media ID, nie automatycznie kolejny numer na podstawie podobieństwa tytułu.

#### Kolejność implementacji

1. Zdefiniuj SeriesId jako trwałe lokalne ID, oddzielne od opcjonalnych AniList ID oraz MAL ID.

2. Wprowadź EpisodeKey(series_id, kind, number) i enum kind: TV, OVA, ONA, SPECIAL, MOVIE.

3. Waliduj number przez Decimal i zapisuj kanoniczny string bez utraty części ułamkowej; zabroń NaN i Infinity.

4. Dla nieopisanych specjalnych materiałów zachowaj surową etykietę i wymagaj ręcznego mapowania, zamiast wymyślać numer.

5. Zdefiniuj RevisionId związany z digestem źródła oraz treściowo istotnym profilem przetwarzania.

6. Nie używaj core group_id jako globalnego ID biblioteki; mapuj parę job_id i group_id.

7. Przechowuj oryginalny tytuł wydania jako opis, nie element decydujący o tożsamości produktu.

8. Zaimplementuj porządek prezentacji numerów w domenie, bez sortowania leksykograficznego 10 przed 2.

#### Scenariusze weryfikacji

<a id="t009-c01"></a>

##### T009-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Seria TV z numerami 2, 10 i 7.5.

**Działanie:** Posortuj EpisodeKey.

**Oczekiwany rezultat:** Kolejność wynosi 2, 7.5, 10.

**Niedopuszczalny skutek:** Nie użyto float ani sortowania stringów.

**Docelowy test:** `tests/automation/test_models.py::test_episode_identity_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t009-c02"></a>

##### T009-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Ten sam numer w TV i OVA.

**Działanie:** Utwórz klucze.

**Oczekiwany rezultat:** Powstają dwa odrębne epizody.

**Niedopuszczalny skutek:** Nie nadpisano odcinka TV przez OVA.

**Docelowy test:** `tests/automation/test_models.py::test_episode_identity_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t009-c03"></a>

##### T009-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Numer NaN lub etykieta SP-A bez mapowania.

**Działanie:** Zwaliduj wejście.

**Oczekiwany rezultat:** NaN jest odrzucony, SP-A trafia do decyzji.

**Niedopuszczalny skutek:** Nie przypisano arbitralnie odcinka 1.

**Docelowy test:** `tests/automation/test_models.py::test_episode_identity_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t009-c04"></a>

##### T009-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zmienia się model lub zawartość źródła.

**Działanie:** Wyznacz rewizję.

**Oczekiwany rezultat:** Nowa rewizja nie nadpisuje starej gotowej.

**Niedopuszczalny skutek:** Nie stracono pliku właśnie odtwarzanego.

**Docelowy test:** `tests/automation/test_models.py::test_episode_identity_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_models.py
```

**Wycofanie:** Wycofaj modele przed wdrożeniem migracji; po powstaniu danych wymagana jest kompatybilna migracja, nie usuwanie rekordów.

**Podstawa techniczna:** [S04](research.md#s04), [S06](research.md#s06), [S12](research.md#s12).

<a id="t010"></a>

### T010. Rozdziel transfer, przetwarzanie i oglądanie

**Status:** planned.

**Cel:** Wprowadź stan zadania, którego znaczenie nie zmienia się zależnie od ekranu.

**Wymagania:** [R11](spec.md#r11), [R17](spec.md#r17), [R20](spec.md#r20), [R21](spec.md#r21), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T009](#t009)

**Kolejność planowa:** T010; poprzednia karta: T009.

**Kontrakt / symbol:** `JobState / transition_allowed`.

#### Pliki i zakres edycji

- `anishift/automation/models.py`
- `tests/automation/test_state_transitions.py`

**Istotna granica:** Przejście ready nie jest wyprowadzane z samego globalnego RunResult.succeeded.

#### Kolejność implementacji

1. Zdefiniuj JobState: waiting_source, waiting_file, copying, validating, queued, processing, ready, partial, attention, cancelled.

2. Trzymaj szczegółowy transfer_status jako obserwację klienta, nie drugą maszynę sterującą pobraniem.

3. Zdefiniuj jawne przejścia i wymagane dowody: progress pliku, zakończenie kopii, walidacja wejścia, GroupResult i walidacja produktów.

4. Przechowuj watched_at jako niezależne pole od state i od istniejącego pliku.

5. Zdefiniuj retry_at, error_code i retry_scope; błąd publish nie może automatycznie wracać do wyszukiwania anime.

6. Odróżnij anulowanie przetwarzania od zatrzymania własnego torrenta i od wyłączenia subskrypcji.

7. Zdefiniuj ready jako spełnienie wymaganego zestawu produktów danej rewizji; optional warning nie jest hard failure.

8. Zablokuj przejścia terminalne wynikające ze starej generacji wykonania.

#### Scenariusze weryfikacji

<a id="t010-c01"></a>

##### T010-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Job processing ma zwalidowane wszystkie wymagane produkty.

**Działanie:** Zastosuj wynik.

**Oczekiwany rezultat:** Stan staje się ready, watched_at pozostaje puste.

**Niedopuszczalny skutek:** Nie zwiększono postępu oglądania.

**Docelowy test:** `tests/automation/test_state_transitions.py::test_states_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t010-c02"></a>

##### T010-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Gotowy MKV i nieudany obowiązkowy SRT.

**Działanie:** Zastosuj wynik.

**Oczekiwany rezultat:** Stan to partial z listą dostępnych produktów.

**Niedopuszczalny skutek:** Nie ukryto błędu za ogólnym komunikatem Gotowe.

**Docelowy test:** `tests/automation/test_state_transitions.py::test_states_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t010-c03"></a>

##### T010-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Stary worker wysyła sukces po anulowaniu.

**Działanie:** Zastosuj event starej generacji.

**Oczekiwany rezultat:** Event nie zmienia aktywnego stanu.

**Niedopuszczalny skutek:** Nie wskrzeszono anulowanego zadania.

**Docelowy test:** `tests/automation/test_state_transitions.py::test_states_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t010-c04"></a>

##### T010-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Błąd tylko atomowej publikacji.

**Działanie:** Wykonaj retry.

**Oczekiwany rezultat:** Ponawiana jest publikacja zgodnego stagingu.

**Niedopuszczalny skutek:** Nie wywołano ponownie tłumaczenia i TTS bez potrzeby.

**Docelowy test:** `tests/automation/test_state_transitions.py::test_states_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_state_transitions.py
```

**Wycofanie:** Nie usuwaj stanów obecnych w bazie; ewentualną zmianę nazewnictwa wykonaj migracją zachowującą znaczenie.

**Podstawa techniczna:** [S06](research.md#s06), [S12](research.md#s12).

<a id="t011"></a>

### T011. Ustal niewielki i kompletny zestaw preferencji

**Status:** planned.

**Cel:** Zdefiniuj ustawienia automatyzacji z bezpiecznymi wartościami początkowymi oraz bez nowych kopii ustawień silników.

**Wymagania:** [R05](spec.md#r05), [R06](spec.md#r06), [R09](spec.md#r09), [R13](spec.md#r13), [R24](spec.md#r24), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T010](#t010)

**Kolejność planowa:** T011; poprzednia karta: T010.

**Kontrakt / symbol:** `AutomationPreferences`.

#### Pliki i zakres edycji

- `anishift/automation/config.py`
- `tests/automation/test_config.py`

**Istotna granica:** Domyślne limity są ostrożne i edytowalne; nie stanowią obietnicy przepustowości.

#### Kolejność implementacji

1. Zdefiniuj media_root, enabled, client_url, client_credential_ref, monitor_mode i preferred_player.

2. Zdefiniuj min_resolution=1080, preferred_resolution=1080, allow_higher=true oraz ordered preferred_groups.

3. Zdefiniuj managed_active_transfers (0 = bez limitu, klient decyduje) jako wartość konfigurowalną; równoległość rdzenia pozostaje taka jak w obecnym Auto, limitów GraphScheduler nie zmieniaj.

4. Zdefiniuj poll_interval, quiet_seconds, min_free_bytes, backlog_limit oraz przedział aktywności jako wartości konfigurowalne.

5. Ustal wartości startowe jako decyzje produktu, nie jako wyniki benchmarku użytkownika.

6. Pozostaw silniki, modele, głosy i klucze w istniejącym Settings/UserSettings; przechowuj tylko referencje do presetów.

7. Zwaliduj liczby, brak nakładających się rootów, lokalny adres klienta i enum trybu monitora.

8. Wprowadź wersjonowane defaulty i jawny reset zakresu automatyzacji, bez resetowania tłumacza.

#### Scenariusze weryfikacji

<a id="t011-c01"></a>

##### T011-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Pierwszy start bez konfiguracji.

**Działanie:** Wczytaj defaulty.

**Oczekiwany rezultat:** Automatyczne mutacje systemu pozostają wyłączone.

**Niedopuszczalny skutek:** Nie włączono autostartu lub pobierania bez setupu.

**Docelowy test:** `tests/automation/test_config.py::test_preferences_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t011-c02"></a>

##### T011-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Ustawiono 2160p jako preferowane i minimum 1080.

**Działanie:** Zwaliduj profil.

**Oczekiwany rezultat:** 1080p pozostaje dopuszczalne zgodnie z allow_higher/polityką.

**Niedopuszczalny skutek:** Nie mylono minimum z wymaganym dokładnym rozmiarem.

**Docelowy test:** `tests/automation/test_config.py::test_preferences_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t011-c03"></a>

##### T011-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Interwał ujemny lub inbox wewnątrz downloads.

**Działanie:** Zapisz konfigurację.

**Oczekiwany rezultat:** Zmiana jest odrzucona z nazwą pola.

**Niedopuszczalny skutek:** Nie zapisano częściowo niespójnych ustawień.

**Docelowy test:** `tests/automation/test_config.py::test_preferences_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t011-c04"></a>

##### T011-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Reset automatyzacji po zmianie głosu TTS.

**Działanie:** Wykonaj reset zakresowy.

**Oczekiwany rezultat:** Automatyzacja wraca do defaultów, głos nie zmienia się.

**Niedopuszczalny skutek:** Nie zresetowano istniejących połączeń API.

**Docelowy test:** `tests/automation/test_config.py::test_preferences_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_config.py
```

**Wycofanie:** Przywróć poprzedni wersjonowany rekord preferencji; nie dotykaj .env ani ustawień TTS.

**Podstawa techniczna:** [S02](research.md#s02), [S03](research.md#s03), [S10](research.md#s10).

<a id="t012"></a>

### T012. Wyznacz fizyczny układ katalogów bez migracji legacy

**Status:** planned.

**Cel:** Zapewnij przewidywalną bibliotekę: seria → typ → odcinek → rewizja, przy zachowaniu płaskiego rdzenia.

**Wymagania:** [R15](spec.md#r15), [R16](spec.md#r16), [R26](spec.md#r26), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T011](#t011)

**Kolejność planowa:** T012; poprzednia karta: T011.

**Kontrakt / symbol:** `LibraryPaths.revision_root`.

#### Pliki i zakres edycji

- `anishift/automation/paths.py`
- `tests/automation/test_paths.py`

**Istotna granica:** Folder rewizji chroni wcześniejsze produkty przy zmianie źródła lub profilu, zamiast wymagać nadpisywania.

#### Kolejność implementacji

1. Przyjmij domyślny media_root jako katalog media obok legacy workspace, chyba że właściciel wybierze inny lokalny dysk.

2. Wyznacz osobne podkatalogi inbox, downloads i library bez wzajemnego zawierania.

3. Wyznacz library/<safe-title> [<stable-id>]/<kind>/<episode-label>/<revision-id> jako płaski workspace rdzenia.

4. Wewnątrz rewizji pozostaw źródło, produkty i istniejący temp; baza i logi nie mogą powstawać obok wideo.

5. Zapisz stabilny directory_key serii w bazie; zmiana wyświetlanego tytułu nie zmienia automatycznie ścieżek.

6. Nowe nazwy źródeł nadawaj przed planowaniem; zachowuj zgodność stem wideo i sidecarów.

7. Przyjmij osobny state_root=config/automation oraz istniejące logs, poza media_root.

8. Nie zastępuj iterdir przez rglob w application/discovery.py; każdy job dostaje dokładnie jedną rewizję.

#### Scenariusze weryfikacji

<a id="t012-c01"></a>

##### T012-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Dwie serie o takim samym wyświetlanym tytule.

**Działanie:** Wyznacz katalogi.

**Oczekiwany rezultat:** Różne stable-id tworzą różne katalogi.

**Niedopuszczalny skutek:** Nie nastąpiło połączenie bibliotek.

**Docelowy test:** `tests/automation/test_paths.py::test_layout_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t012-c02"></a>

##### T012-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zmienił się tytuł angielski w katalogu.

**Działanie:** Odśwież metadane.

**Oczekiwany rezultat:** Ścieżka istniejącej serii pozostaje stała.

**Niedopuszczalny skutek:** Nie przeniesiono plików w trakcie odtwarzania.

**Docelowy test:** `tests/automation/test_paths.py::test_layout_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t012-c03"></a>

##### T012-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wybrany state_root leży w folderze synchronizowanym.

**Działanie:** Wykonaj setup validation.

**Oczekiwany rezultat:** Pojawia się odmowa lub konkretne ostrzeżenie wymagające lokalnej bazy.

**Niedopuszczalny skutek:** Nie uruchomiono aktywnej WAL na udziale sieciowym.

**Docelowy test:** `tests/automation/test_paths.py::test_layout_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t012-c04"></a>

##### T012-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Legacy workspace ma gotowe pliki płasko.

**Działanie:** Włącz nową bibliotekę.

**Oczekiwany rezultat:** Legacy pozostaje nienaruszone i nadal obsługiwane przez Auto.

**Niedopuszczalny skutek:** Nie rozpoczęto masowego skanowania dysku.

**Docelowy test:** `tests/automation/test_paths.py::test_layout_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_paths.py
```

**Wycofanie:** Wyłącz nowe rooty w konfiguracji; zachowaj bibliotekę i wszystkie istniejące ścieżki, nie wykonuj automatycznej migracji wstecz.

**Podstawa techniczna:** [S02](research.md#s02), [S04](research.md#s04), [S05](research.md#s05), [S11](research.md#s11), [S33](research.md#s33).

<a id="t013"></a>

### T013. Zabezpiecz nazwy Windows i granice rootów

**Status:** planned.

**Cel:** Nie pozwól nazwie torrenta, tytułowi lub symlinkowi wyprowadzić operacji poza własne katalogi.

**Wymagania:** [R15](spec.md#r15), [R16](spec.md#r16), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T012](#t012)

**Kolejność planowa:** T013; poprzednia karta: T012.

**Kontrakt / symbol:** `safe_component / contained_path`.

#### Pliki i zakres edycji

- `anishift/automation/paths.py`
- `tests/automation/test_path_safety.py`

**Istotna granica:** Sama sanitizacja tekstu nie jest zabezpieczeniem filesystemu; obowiązuje również containment i brak podążania za linkami.

#### Kolejność implementacji

1. Normalizuj nazwy komponentów, usuwając znaki sterujące i zastępując znaki niedozwolone w Windows.

2. Obsłuż CON, PRN, AUX, NUL, COM1–COM9 i LPT1–LPT9 także z rozszerzeniem; usuń końcowe kropki i spacje.

3. Ogranicz długość czytelnej części tytułu i zachowaj stabilny suffix ID; nie obcinaj ID.

4. Względne ścieżki plików z torrenta sprawdzaj przed join oraz po resolve; odrzuć drive, UNC, .. i null bytes.

5. Nie podążaj za junction/symlink w inbox, downloads lub bibliotece podczas zarządzanych operacji.

6. Przy zmianie położenia lub tożsamości pliku między sprawdzeniem i otwarciem przerwij kopię.

7. Loguj stabilny identyfikator pliku, a pełną ścieżkę pokazuj tylko świadomie w lokalnym panelu, po sanitizacji.

8. Przy kolizji case-insensitive dodaj stabilny suffix zamiast nadpisywać pierwszy plik.

#### Scenariusze weryfikacji

<a id="t013-c01"></a>

##### T013-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Tytuł CON: Aster? z końcową kropką.

**Działanie:** Zbuduj nazwę.

**Oczekiwany rezultat:** Powstaje legalny komponent z zachowanym ID.

**Niedopuszczalny skutek:** Nie użyto oryginalnego tytułu jako surowej ścieżki.

**Docelowy test:** `tests/automation/test_path_safety.py::test_path_safety_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t013-c02"></a>

##### T013-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Torrent zwraca ../outside.mkv lub C:\outside.mkv.

**Działanie:** Zweryfikuj plik.

**Oczekiwany rezultat:** Plik jest odrzucony przed otwarciem.

**Niedopuszczalny skutek:** Nie powstał plik poza downloads.

**Docelowy test:** `tests/automation/test_path_safety.py::test_path_safety_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t013-c03"></a>

##### T013-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Inbox zawiera junction do katalogu prywatnego.

**Działanie:** Wykonaj scan.

**Oczekiwany rezultat:** Junction zostaje pominięty i opisany.

**Niedopuszczalny skutek:** Nie rozpoczęto rekurencyjnego odczytu prywatnych danych.

**Docelowy test:** `tests/automation/test_path_safety.py::test_path_safety_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t013-c04"></a>

##### T013-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Plik podmieniono po wstępnej walidacji.

**Działanie:** Rozpocznij kopiowanie.

**Oczekiwany rezultat:** Zmiana tożsamości unieważnia próbę.

**Niedopuszczalny skutek:** Nie zaakceptowano źródła tylko po starej nazwie.

**Docelowy test:** `tests/automation/test_path_safety.py::test_path_safety_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_path_safety.py
```

**Wycofanie:** Wycofaj wyłącznie nowy resolver przed publikacją danych; wcześniej utworzone bezpieczne nazwy pozostają ważne.

**Podstawa techniczna:** [S36](research.md#s36), [S37](research.md#s37).

<a id="t014"></a>

### T014. Zapisz własność źródeł i uprawnienia do operacji

**Status:** planned.

**Cel:** Każda zmiana pliku lub torrenta musi wynikać z jawnej własności, a nie z podobieństwa nazwy.

**Wymagania:** [R16](spec.md#r16), [R17](spec.md#r17), [R26](spec.md#r26), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T013](#t013)

**Kolejność planowa:** T014; poprzednia karta: T013.

**Kontrakt / symbol:** `SourceOwnership / can_mutate`.

#### Pliki i zakres edycji

- `anishift/automation/models.py`
- `anishift/automation/paths.py`
- `tests/automation/test_ownership.py`

**Istotna granica:** Nie planujemy domyślnego wywołania deleteFiles=true ani operacji na hashes=all.

#### Kolejność implementacji

1. Zdefiniuj transfer ownership OWNED i BORROWED; cudzy istniejący torrent pozostaje read-only.

2. Własność powstaje po uzgodnionym add z trwałym operation_id, kategorią AniShift i potwierdzonym infohash.

3. Przy obcym istniejącym hashu dopuść odczyt ukończonego pliku, ale nie zmieniaj priorytetów lub limitów bez decyzji.

4. Źródła inbox traktuj jako BORROWED; kontrolowana kopia w rewizji jest OWNED przez konkretny job.

5. Wszelkie cleanup ogranicz do listy dokładnych plików lub rozpoznanego stagingu danego operation_id.

6. Usunięcie subskrypcji wyłącza przyszłe pobieranie i nie usuwa biblioteki, torrentów ani historii oglądania.

7. Odmowa miejsca na dysku nigdy nie uruchamia automatycznego kasowania źródeł jako sposobu naprawy.

8. Zapisz własność w trwałym rekordzie, a marker plikowy używaj tylko jako pomoc do bezpiecznego recovery.

#### Scenariusze weryfikacji

<a id="t014-c01"></a>

##### T014-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Ten sam hash już istnieje jako prywatny torrent użytkownika.

**Działanie:** Dodaj wybór w AniShift.

**Oczekiwany rezultat:** Transfer jest powiązany read-only lub wymaga decyzji.

**Niedopuszczalny skutek:** Nie zmieniono kategorii i priorytetów cudzego transferu.

**Docelowy test:** `tests/automation/test_ownership.py::test_ownership_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t014-c02"></a>

##### T014-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik usuwa subskrypcję.

**Działanie:** Wykonaj remove subscription.

**Oczekiwany rezultat:** Przyszłe sprawdzanie zostaje wyłączone.

**Niedopuszczalny skutek:** Nie usunięto żadnego MKV ani danych klienta.

**Docelowy test:** `tests/automation/test_ownership.py::test_ownership_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t014-c03"></a>

##### T014-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Brakuje miejsca na kopię.

**Działanie:** Oceń operację.

**Oczekiwany rezultat:** Job czeka z konkretną przyczyną disk_full.

**Niedopuszczalny skutek:** Nie skasowano najstarszej serii bez zgody.

**Docelowy test:** `tests/automation/test_ownership.py::test_ownership_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t014-c04"></a>

##### T014-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Staging ma marker innego operation_id.

**Działanie:** Uruchom cleanup.

**Oczekiwany rezultat:** Obcy katalog zostaje zachowany.

**Niedopuszczalny skutek:** Nie uznano samej nazwy temp za zgodę na usunięcie.

**Docelowy test:** `tests/automation/test_ownership.py::test_ownership_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_ownership.py
```

**Wycofanie:** Wycofanie funkcji wyłącza jej mutacje i zachowuje rekord własności do późniejszego świadomego sprzątania.

**Podstawa techniczna:** [S11](research.md#s11), [S20](research.md#s20).

<a id="t015"></a>

### T015. Zdefiniuj niezmienny profil treści bez zapisywania sekretów

**Status:** planned.

**Cel:** Wznowienie ma wiedzieć, do jakiego źródła i ustawień należą istniejące produkty, bez kopiowania kluczy API.

**Wymagania:** [R02](spec.md#r02), [R07](spec.md#r07), [R17](spec.md#r17), [R24](spec.md#r24), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T014](#t014)

**Kolejność planowa:** T015; poprzednia karta: T014.

**Kontrakt / symbol:** `ProcessingProfile.content_digest`.

#### Pliki i zakres edycji

- `anishift/automation/config.py`
- `anishift/automation/models.py`
- `tests/automation/test_profile.py`

**Istotna granica:** Wykonawca ma odczytać definicje istniejących modeli, nie wymyślać nazw pól Settings z samego opisu.

#### Kolejność implementacji

1. Wybierz jawną listę treściowo istotnych pól presetu, modelu, języka, głosu i parametrów audio z rzeczywistych modeli repo.

2. Oddziel pola wpływające na treść od limitów wykonawczych, timeoutów, liczby wątków i ścieżek.

3. Zserializuj profile w kanonicznym JSON z numerem schematu i oblicz digest.

4. Nie zapisuj wartości kluczy, tokenów, nagłówków, prywatnych promptów ani tekstu napisów w rekordzie profilu.

5. Dla promptów użyj identyfikatora konfiguracji/rewizji udostępnionego przez istniejącą warstwę; brak wiarygodnej rewizji wymaga nowej rewizji produktu przy zmianie wyboru.

6. Pobieraj aktualne credentials przy wykonaniu; odświeżenie klucza nie musi zmieniać profilu treści.

7. Ustawienia zmienione w UI dotyczą nowych zleceń; aktywne zlecenie używa zaakceptowanego snapshotu.

8. Po zmianie profilu nie reużywaj produktów starej rewizji automatycznie; zachowaj je jako nadal odtwarzalne.

#### Scenariusze weryfikacji

<a id="t015-c01"></a>

##### T015-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Dwa snapshoty różnią się wyłącznie liczbą workerów.

**Działanie:** Policz content_digest.

**Oczekiwany rezultat:** Digest treści jest taki sam.

**Niedopuszczalny skutek:** Nie zaplanowano ponownego TTS z powodu liczby wątków.

**Docelowy test:** `tests/automation/test_profile.py::test_profile_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t015-c02"></a>

##### T015-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zmienił się głos lektora.

**Działanie:** Policz digest i rewizję.

**Oczekiwany rezultat:** Powstaje nowa rewizja produktu.

**Niedopuszczalny skutek:** Nie podmieniono ścieżki odtwarzanego MKV.

**Docelowy test:** `tests/automation/test_profile.py::test_profile_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t015-c03"></a>

##### T015-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Settings zawiera token API.

**Działanie:** Zapisz snapshot.

**Oczekiwany rezultat:** Token nie występuje w JSON, logu ani bazie profilu.

**Niedopuszczalny skutek:** Nie użyto dump całego Settings.

**Docelowy test:** `tests/automation/test_profile.py::test_profile_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t015-c04"></a>

##### T015-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Token wygasł, następnie został odnowiony.

**Działanie:** Wznów job.

**Oczekiwany rezultat:** Używa nowego credential przy tym samym profilu treści.

**Niedopuszczalny skutek:** Nie wymaga ponownego pobrania źródła.

**Docelowy test:** `tests/automation/test_profile.py::test_profile_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_profile.py
```

**Wycofanie:** Zachowaj wcześniejsze profile z wersją schematu; nie próbuj usuwać historii digestów lub ponownie podpisywać starych produktów.

**Podstawa techniczna:** [S03](research.md#s03), [S05](research.md#s05), [S06](research.md#s06).

<a id="t016"></a>

### T016. Ujednolić błędy i akcje naprawcze

**Status:** planned.

**Cel:** Użytkownik dostaje konkretną przyczynę i jedną właściwą akcję zamiast tracebacku lub nieskończonego ponawiania.

**Wymagania:** [R23](spec.md#r23), [R24](spec.md#r24), [R26](spec.md#r26), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T015](#t015)

**Kolejność planowa:** T016; poprzednia karta: T015.

**Kontrakt / symbol:** `AutomationError / ErrorCode`.

#### Pliki i zakres edycji

- `anishift/errors.py`
- `anishift/automation/models.py`
- `tests/automation/test_errors.py`

**Istotna granica:** Nie ma ogólnego except Exception z cichym sukcesem; nieznany błąd jest rejestrowany i izolowany.

#### Kolejność implementacji

1. Dodaj błędy domeny automatyzacji zgodnie z istniejącą hierarchią AniShiftError, bez nowego równoległego systemu wyjątków.

2. Zdefiniuj kody: provider_unavailable, schema_changed, rate_limited, auth_required, disk_full, source_changed, mapping_required, subtitles_missing i destination_locked.

3. Każdemu kodowi przypisz retry_scope i kategorię: automatyczne później, po konfiguracji albo po decyzji użytkownika.

4. Zachowaj exception cause w kodzie, ale nie loguj surowego requestu, pełnego stderr lub ErrorContext.details.

5. Komunikaty UI sanitizuj istniejącym sanitize_event_message; nazwa pliku nie może zawierać terminalowych escape sequences.

6. Przy błędzie jednego providera zatrzymaj wyłącznie jego operacje; lokalne przetwarzanie i inne źródła mają działać.

7. Zapisz attempts, next_retry_at i ostatnią bezpieczną przyczynę zamiast mnożyć identyczne eventy co klatkę.

8. Wymaga uwagi ma przycisk odpowiadający przyczynie: Wybierz serię, Wybierz napisy, Połącz klienta, Ponów albo Pokaż folder.

#### Scenariusze weryfikacji

<a id="t016-c01"></a>

##### T016-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Provider zwraca 429 z Retry-After.

**Działanie:** Zmapuj wyjątek.

**Oczekiwany rezultat:** Powstaje rate_limited z konkretnym retry_at.

**Niedopuszczalny skutek:** Nie pokazano użytkownikowi błędu tłumaczenia.

**Docelowy test:** `tests/automation/test_errors.py::test_error_contract_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t016-c02"></a>

##### T016-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Błąd zawiera token w URL.

**Działanie:** Zapisz event i log.

**Oczekiwany rezultat:** Sekret nie pojawia się w żadnym wyjściu diagnostycznym.

**Niedopuszczalny skutek:** Nie wypisano str(exc) bez filtracji.

**Docelowy test:** `tests/automation/test_errors.py::test_error_contract_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t016-c03"></a>

##### T016-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Tytuł zawiera kod ANSI czyszczenia ekranu.

**Działanie:** Pokaż komunikat.

**Oczekiwany rezultat:** Tekst jest bezpiecznie wyświetlony.

**Niedopuszczalny skutek:** Nie wykonano sekwencji terminalowej.

**Docelowy test:** `tests/automation/test_errors.py::test_error_contract_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t016-c04"></a>

##### T016-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nyaa nie działa, lokalny MKV jest gotowy.

**Działanie:** Wykonaj tick workera.

**Oczekiwany rezultat:** Lokalny job nadal przechodzi do kolejki.

**Niedopuszczalny skutek:** Nie zatrzymano całej aplikacji z powodu indeksu.

**Docelowy test:** `tests/automation/test_errors.py::test_error_contract_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_errors.py
```

**Wycofanie:** Cofnij nowe mapowania błędów tylko razem z ich wywołaniami; historyczne kody w bazie nadal muszą mieć czytelny fallback.

**Podstawa techniczna:** [S02](research.md#s02), [S03](research.md#s03), [S07](research.md#s07).

<a id="p02"></a>

## P02. Trwały stan, komendy i pojedynczy worker

**Status fazy:** superseded-by: [plans/01-watch-mode.md](plans/01-watch-mode.md). Karty poniżej pozostają historią projektu; nie są kolejką wykonania.

Karty T tej fazy usunięto przed pierwszym commitem pakietu, bo zastąpił je Plan 01; nie były kolejką wykonania.

<a id="p03"></a>
## P03. Kontrolowany import i obserwowanie inbox

**Status fazy:** superseded-by: [plans/01-watch-mode.md](plans/01-watch-mode.md). Karty poniżej pozostają historią projektu; nie są kolejką wykonania.

Karty T tej fazy usunięto przed pierwszym commitem pakietu, bo zastąpił je Plan 01; nie były kolejką wykonania.

<a id="p04"></a>
## P04. Podłączenie istniejącego Auto i odzyskiwanie produktów

**Status fazy:** superseded-by: [plans/01-watch-mode.md](plans/01-watch-mode.md). Karty poniżej pozostają historią projektu; nie są kolejką wykonania.

Karty T tej fazy usunięto przed pierwszym commitem pakietu, bo zastąpił je Plan 01; nie były kolejką wykonania.

<a id="p05"></a>
## P05. Katalog tytułów, aliasy i dane o emisji

**Wynik fazy:** Tytuł, alias i kalendarz są dostępne jako dane katalogowe.

**Wejście:** P00 probe i P02 cache/stany.

**Warunek wyjścia:** Literówki porządkują sugestie, nie łączą sezonów; brak katalogu nie blokuje lokalnego pliku.

**Status fazy:** planned.

<a id="t041"></a>

### T041. Zbuduj wspólną granicę HTTP z budżetem i timeoutami

**Status:** planned.

**Cel:** Wszystkie odczyty katalogów i indeksów respektują limity oraz nie wprowadzają sieci do renderera.

**Wymagania:** [R18](spec.md#r18), [R23](spec.md#r23), [R24](spec.md#r24), [R26](spec.md#r26), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T024](#t024)

**Kolejność planowa:** T041; poprzednia karta: T040.

**Kontrakt / symbol:** `ProviderHttpClient.request`.

#### Pliki i zakres edycji

- `anishift/automation/http.py`
- `tests/automation/test_http.py`

**Istotna granica:** Nie ma omijania challenge, rotacji IP ani obchodzenia limitów dostawcy.

#### Kolejność implementacji

1. Użyj istniejącego httpx z jawnymi timeoutami connect/read/write/pool i ograniczeniem połączeń.

2. Zdefiniuj osobny budżet dla każdego hosta; AniList startowo nie przekracza 10 requestów na minutę.

3. Honoruj Retry-After i X-RateLimit-Reset; lokalny budżet może się tylko zaostrzyć wobec odpowiedzi serwera.

4. Ogranicz rozmiar pobranego i zdekompresowanego body przed przekazaniem parserowi.

5. Waliduj schemat URL oraz host; nie podążaj automatycznie za przekierowaniem do localhost lub prywatnej sieci z publicznego feedu.

6. Dla publicznych źródeł wyłącz niezamierzone odziedziczenie proxy/credentials; świadomą konfigurację proxy traktuj oddzielnie.

7. Zapisuj wyłącznie bezpieczne identyfikatory hosta, czas, kod odpowiedzi i typ błędu.

8. Wstrzykuj klienta i zegar do testów; żaden konstruktor widoku nie robi requestu.

#### Scenariusze weryfikacji

<a id="t041-c01"></a>

##### T041-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Serwer zwraca Retry-After=120.

**Działanie:** Zaplanuj kolejną próbę.

**Oczekiwany rezultat:** Nie ma requestu przed upływem 120 sekund.

**Niedopuszczalny skutek:** Nie nadpisano limitu krótszym lokalnym retry.

**Docelowy test:** `tests/automation/test_http.py::test_http_boundary_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t041-c02"></a>

##### T041-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Mały skompresowany body rozwija się ponad limit.

**Działanie:** Odczytaj odpowiedź.

**Oczekiwany rezultat:** Odpowiedź jest przerwana i odrzucona.

**Niedopuszczalny skutek:** Nie zużyto nieograniczonej pamięci.

**Docelowy test:** `tests/automation/test_http.py::test_http_boundary_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t041-c03"></a>

##### T041-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Publiczny feed przekierowuje do 127.0.0.1.

**Działanie:** Obsłuż redirect.

**Oczekiwany rezultat:** Przekierowanie jest odrzucone.

**Niedopuszczalny skutek:** Nie wykonano requestu do lokalnych usług.

**Docelowy test:** `tests/automation/test_http.py::test_http_boundary_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t041-c04"></a>

##### T041-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Host po timeout znów działa.

**Działanie:** Ponów według backoff.

**Oczekiwany rezultat:** Żądanie wraca do normalnego budżetu po sukcesie.

**Niedopuszczalny skutek:** Nie pozostaje permanentnie zablokowany bez akcji.

**Docelowy test:** `tests/automation/test_http.py::test_http_boundary_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_http.py
```

**Wycofanie:** Wyłącz nowe zapytania providerów, zachowując lokalny intake i bibliotekę; nie zmieniaj globalnego klienta HTTP istniejących silników.

**Podstawa techniczna:** [S10](research.md#s10), [S18](research.md#s18), [S19](research.md#s19).

<a id="t042"></a>

### T042. Dodaj mały cache zapytań i conditional GET

**Status:** planned.

**Cel:** Powtarzane odświeżenia nie wysyłają tych samych zapytań i nie udają świeżych danych przy awarii.

**Wymagania:** [R03](spec.md#r03), [R18](spec.md#r18), [R23](spec.md#r23), [R24](spec.md#r24).

**Zależności obowiązkowe:** [T041](#t041)

**Kolejność planowa:** T042; poprzednia karta: T041.

**Kontrakt / symbol:** `HttpCache.get_or_fetch`.

#### Pliki i zakres edycji

- `anishift/automation/http.py`
- `anishift/automation/store.py`
- `tests/automation/test_http_cache.py`

**Istotna granica:** To cache żądań komplementarnej aplikacji, nie masowe pobieranie bazy AniList.

#### Kolejność implementacji

1. Cache key obejmuje host, metodę, znormalizowane parametry i język, bez sekretów.

2. Zapisuj ETag, Last-Modified, fetched_at, expires_at oraz ograniczone body odpowiedzi publicznej.

3. Dla RSS wysyłaj If-None-Match i If-Modified-Since, gdy dostawca je wspiera.

4. HTTP 304 aktualizuje świeżość metadanych bez nadpisywania body pustą odpowiedzią.

5. GraphQL POST odczytowe cache według kanonicznej treści zapytania i variables; nie cache mutacji.

6. Ogranicz cache do zapytań użytkownika i subskrybowanych serii; retencja startowa 30 dni dla nieużywanych rekordów.

7. Przy awarii pozwól wyświetlić stare dane z wyraźnym wiekiem, ale nie uznawaj ich za nową premierę.

8. Współdziel jedno in-flight pobranie tego samego feedu pomiędzy wiele subskrypcji.

#### Scenariusze weryfikacji

<a id="t042-c01"></a>

##### T042-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Dwa widoki proszą o ten sam feed.

**Działanie:** Wykonaj odświeżenie.

**Oczekiwany rezultat:** Wysyłany jest jeden request.

**Niedopuszczalny skutek:** Nie pobrano tego samego RSS osobno dla każdego wiersza.

**Docelowy test:** `tests/automation/test_http_cache.py::test_http_cache_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t042-c02"></a>

##### T042-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Serwer zwrócił 304.

**Działanie:** Zastosuj wynik.

**Oczekiwany rezultat:** Poprzednie body pozostaje dostępne.

**Niedopuszczalny skutek:** Nie zamieniono biblioteki wyników na pustą.

**Docelowy test:** `tests/automation/test_http_cache.py::test_http_cache_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t042-c03"></a>

##### T042-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Cache jest stary, sieć nie działa.

**Działanie:** Pokaż dane.

**Oczekiwany rezultat:** Wiek i stan offline są widoczne.

**Niedopuszczalny skutek:** Nie oznaczono danych jako sprawdzone przed chwilą.

**Docelowy test:** `tests/automation/test_http_cache.py::test_http_cache_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t042-c04"></a>

##### T042-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nieaktywny rekord przekroczył retencję.

**Działanie:** Wykonaj cleanup.

**Oczekiwany rezultat:** Usuwany jest wyłącznie cache, nie tożsamość subskrypcji.

**Niedopuszczalny skutek:** Nie skasowano zapisanej serii.

**Docelowy test:** `tests/automation/test_http_cache.py::test_http_cache_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_http_cache.py
```

**Wycofanie:** Cache można usunąć przy zatrzymanym jego writerze; nie usuwa się razem z nim trwałych ID, jobów i subskrypcji.

**Podstawa techniczna:** [S16](research.md#s16), [S18](research.md#s18), [S19](research.md#s19), [S33](research.md#s33).

<a id="t043"></a>

### T043. Wprowadź typowane wyszukiwanie katalogu AniList

**Status:** planned.

**Cel:** Wpisana nazwa zwraca właściwe media z kontekstem sezonu i formatu, nie jedynie dopasowane pliki torrentów.

**Wymagania:** [R03](spec.md#r03), [R04](spec.md#r04), [R18](spec.md#r18), [R23](spec.md#r23).

**Zależności obowiązkowe:** [T042](#t042), [T004](#t004)

**Kolejność planowa:** T043; poprzednia karta: T042.

**Kontrakt / symbol:** `AniListProvider.search / get_media`.

#### Pliki i zakres edycji

- `anishift/automation/providers/anilist.py`
- `tests/automation/test_anilist.py`

**Istotna granica:** Zapytanie musi przejść T004; przy zmianie schematu zmieniany jest ten adapter, nie cała domena.

#### Kolejność implementacji

1. Zbuduj zapytanie Page/Media type=ANIME z variables search, page i perPage ograniczonym do 20.

2. Pobieraj id, idMal, title english/romaji/native, synonyms, format, status, episodes i startDate.

3. Waliduj null w tytule angielskim, brak znanej liczby odcinków oraz częściową datę.

4. Zmapuj GraphQL errors i partial data; błędny schemat nie staje się pustym trafieniem.

5. Zapisuj provenance provider ID i czas pobrania w każdym rekordzie katalogowym.

6. Nie dodawaj OAuth tylko dla publicznego odczytu metadanych.

7. Przekaż wynik do lokalnego rankingu, który zachowuje wszystkie kandydatury z różnymi media ID.

8. Po wyborze media pobierz szczegóły wyłącznie tego rekordu i jego bezpośrednich relacji.

#### Scenariusze weryfikacji

<a id="t043-c01"></a>

##### T043-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Tytuł angielski jest null, romaji istnieje.

**Działanie:** Zmapuj odpowiedź.

**Oczekiwany rezultat:** UI pokazuje romaji i zachowuje ID.

**Niedopuszczalny skutek:** Nie odrzucono anime z powodu braku English title.

**Docelowy test:** `tests/automation/test_anilist.py::test_anilist_search_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t043-c02"></a>

##### T043-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Liczba odcinków jest nieznana.

**Działanie:** Zmapuj media.

**Oczekiwany rezultat:** episodes pozostaje None i nie kończy subskrypcji.

**Niedopuszczalny skutek:** Nie przyjęto wartości zero jako zakończonej serii.

**Docelowy test:** `tests/automation/test_anilist.py::test_anilist_search_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t043-c03"></a>

##### T043-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** GraphQL errors przy HTTP 200.

**Działanie:** Zmapuj odpowiedź.

**Oczekiwany rezultat:** Błąd jest widoczny, ewentualne partial data oznaczone.

**Niedopuszczalny skutek:** Nie zapisano pustego katalogu jako poprawnego odczytu.

**Docelowy test:** `tests/automation/test_anilist.py::test_anilist_search_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t043-c04"></a>

##### T043-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Kolejna strona po paginacji.

**Działanie:** Scal wyniki.

**Oczekiwany rezultat:** Media deduplikowane są po ID, nie po tytule.

**Niedopuszczalny skutek:** Nie zgubiono dwóch sezonów o podobnej nazwie.

**Docelowy test:** `tests/automation/test_anilist.py::test_anilist_search_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_anilist.py
```

**Wycofanie:** Wyłącz odczyty katalogu, zachowując wcześniej wybrane serie i możliwość ręcznego dodania magnetu/pliku.

**Podstawa techniczna:** [S17](research.md#s17), [S18](research.md#s18), [S19](research.md#s19).

<a id="t044"></a>

### T044. Dodaj normalizację aliasów i ranking fuzzy

**Status:** planned.

**Cel:** Literówki i różne warianty tytułu pomagają znaleźć anime, ale nie umożliwiają cichego pomylenia sezonów.

**Wymagania:** [R03](spec.md#r03), [R04](spec.md#r04), [R19](spec.md#r19), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T043](#t043), [T002](#t002)

**Kolejność planowa:** T044; poprzednia karta: T043.

**Kontrakt / symbol:** `normalize_title / rank_titles`.

#### Pliki i zakres edycji

- `anishift/automation/catalog.py`
- `tests/automation/test_title_matching.py`

**Istotna granica:** Dopasowanie semantyczne tytułu nie wymaga LLM w pętli wyszukiwania.

#### Kolejność implementacji

1. Normalizuj Unicode NFKC, casefold, odstępy i łagodne warianty interpunkcji, zachowując cyfry oraz słowa sezonu.

2. Najpierw oceniaj exact title i exact alias, następnie podobieństwo RapidFuzz.

3. W rankingu utrzymuj osobne cechy dopasowania tytułu, sezonu, roku i formatu.

4. Nie usuwaj globalnie tokenów 2, II, Final Season, Part 2 lub nazw podtytułów.

5. Wyświetlaj krótkie wyjaśnienie: dopasowany alias, inny sezon lub inny format.

6. Fuzzy wynik służy do kolejności propozycji; automatyczne pobranie wymaga zapisanej tożsamości i reguły wydania.

7. Wspieraj zapis własnego aliasu po świadomym wyborze serii.

8. Nie interpretuj token_set_ratio=100 jako dowodu zgodności, gdy jeden tytuł zawiera drugi.

#### Scenariusze weryfikacji

<a id="t044-c01"></a>

##### T044-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik wpisuje Aster Jurney.

**Działanie:** Uszereguj kandydatów.

**Oczekiwany rezultat:** Właściwy tytuł jest wysoko i wskazuje dopasowanie fuzzy.

**Niedopuszczalny skutek:** Nie zaczyna się pobieranie od samego score.

**Docelowy test:** `tests/automation/test_title_matching.py::test_title_matching_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t044-c02"></a>

##### T044-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Aster Journey oraz Aster Journey Second Season.

**Działanie:** Porównaj trafienia.

**Oczekiwany rezultat:** Oba ID są odrębne i widoczny jest sezon.

**Niedopuszczalny skutek:** Nie usunięto słowa Second jako szumu.

**Docelowy test:** `tests/automation/test_title_matching.py::test_title_matching_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t044-c03"></a>

##### T044-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik wkleił puste znaki lub same separatory.

**Działanie:** Wyszukaj.

**Oczekiwany rezultat:** Nie jest wysyłane bezużyteczne zapytanie.

**Niedopuszczalny skutek:** Nie wybrano pierwszego wyniku katalogu.

**Docelowy test:** `tests/automation/test_title_matching.py::test_title_matching_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t044-c04"></a>

##### T044-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Zapisany alias po restarcie.

**Działanie:** Wyszukaj alias.

**Oczekiwany rezultat:** Wskazuje wcześniej potwierdzone media ID.

**Niedopuszczalny skutek:** Nie zależy od tymczasowego cache HTTP.

**Docelowy test:** `tests/automation/test_title_matching.py::test_title_matching_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_title_matching.py
```

**Wycofanie:** Wycofaj błędny alias lub regułę rankingu; zapisane canonical IDs nie są automatycznie przepisywane.

**Podstawa techniczna:** [S30](research.md#s30), [S31](research.md#s31).

<a id="t045"></a>

### T045. Pokaż sezony i materiały powiązane bez automatycznego miksowania

**Status:** planned.

**Cel:** Wybór serialu nie ukrywa OVA i specials, ale też nie pobiera nieproszonej całej franczyzy.

**Wymagania:** [R04](spec.md#r04), [R19](spec.md#r19), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T044](#t044)

**Kolejność planowa:** T045; poprzednia karta: T044.

**Kontrakt / symbol:** `list_related_media`.

#### Pliki i zakres edycji

- `anishift/automation/catalog.py`
- `anishift/automation/providers/anilist.py`
- `tests/automation/test_relations.py`

**Istotna granica:** Airing calendar nie jest pełnym katalogiem wszystkich wersji, dodatków i wydań domowych.

#### Kolejność implementacji

1. Odczytaj bezpośrednie relations z typem powiązania i formatem media.

2. Pokaż sekcje Kontynuacje, Poprzednie części oraz Dodatki na stronie wybranego anime.

3. Nie przechodź rekurencyjnie przez całą franczyzę ani nie pobieraj masowo metadanych wszystkich połączeń.

4. Każdy powiązany media ID pozostaje odrębną serią biblioteczną lub jawnym dodatkiem do wybranego tytułu.

5. Zapisuj ręczne mapowanie odcinka dodatkowego na jego media ID i numer, gdy katalog ma osobny rekord.

6. Dla nieznanych relacji pokaż surową znormalizowaną kategorię bez automatycznej subskrypcji.

7. Zaznaczenie Pobieraj dodatki wymaga wyboru konkretnych powiązań, nie całej listy bez kontroli.

8. Przy braku danych nie twierdź, że właściciel ma całą zawartość franczyzy.

#### Scenariusze weryfikacji

<a id="t045-c01"></a>

##### T045-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** TV ma powiązane OVA i sequel.

**Działanie:** Otwórz szczegóły.

**Oczekiwany rezultat:** Dodatki i kontynuacja są widoczne osobno.

**Niedopuszczalny skutek:** Nie dodano ich automatycznie do pobierania.

**Docelowy test:** `tests/automation/test_relations.py::test_media_relations_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t045-c02"></a>

##### T045-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Relacja tworzy cykl.

**Działanie:** Wczytaj bezpośrednie powiązania.

**Oczekiwany rezultat:** Nie powstaje nieskończone odpytywanie.

**Niedopuszczalny skutek:** Nie skanowano całego grafu franczyzy.

**Docelowy test:** `tests/automation/test_relations.py::test_media_relations_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t045-c03"></a>

##### T045-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Provider nie zwraca relations.

**Działanie:** Pokaż szczegóły.

**Oczekiwany rezultat:** Widoczna jest niepełność danych, podstawowy tytuł nadal działa.

**Niedopuszczalny skutek:** Nie ogłoszono kompletności wszystkich specials.

**Docelowy test:** `tests/automation/test_relations.py::test_media_relations_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t045-c04"></a>

##### T045-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik wybiera jedną OVA.

**Działanie:** Zapisz wybór.

**Oczekiwany rezultat:** Powstaje osobna jawna subskrypcja/mapowanie.

**Niedopuszczalny skutek:** Nie zmieniono numeracji regularnego sezonu.

**Docelowy test:** `tests/automation/test_relations.py::test_media_relations_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_relations.py
```

**Wycofanie:** Wyłącz wyłącznie nowe powiązanie/subskrypcję; materiały już pobrane pozostają w bibliotece.

**Podstawa techniczna:** [S17](research.md#s17), [S19](research.md#s19).

<a id="t046"></a>

### T046. Znormalizuj emisje do UTC i czasu Warszawy

**Status:** planned.

**Cel:** Harmonogram przechowuje konkretny instant i odcinek, nie luźną nazwę dnia tygodnia.

**Wymagania:** [R09](spec.md#r09), [R18](spec.md#r18), [R19](spec.md#r19), [R23](spec.md#r23).

**Zależności obowiązkowe:** [T045](#t045)

**Kolejność planowa:** T046; poprzednia karta: T045.

**Kontrakt / symbol:** `AiringHint / get_airing`.

#### Pliki i zakres edycji

- `anishift/automation/providers/anilist.py`
- `anishift/automation/catalog.py`
- `tests/automation/test_airing.py`

**Istotna granica:** Godzina emisji nie jest zobowiązaniem grupy do opublikowania angielskich napisów godzinę później.

#### Kolejność implementacji

1. Odczytaj nextAiringEpisode i ograniczony AiringSchedule dla wybranych aktywnych serii.

2. Zapisuj airingAt jako UTC i wiąż go z konkretnym media ID oraz numerem odcinka.

3. Wyświetlaj lokalnie przez zoneinfo Europe/Warsaw; zachowaj UTC jako źródło obliczeń.

4. Brak przyszłej emisji nie oznacza końca anime; użyj statusu i okresowego wyszukiwania.

5. Oddziel aired_at od release_seen_at i file_completed_at.

6. Obsłuż korektę daty, opóźnienie, anulowanie wpisu i przesunięcie numeracji jako zmianę metadanych.

7. Odświeżaj aktywne kalendarze nie częściej niż potrzeba; dane tytułów ukończonych mają dłuższy TTL.

8. Zwróć hint do subscriptions, nie komendę bezwarunkowego pobrania w chwili emisji.

#### Scenariusze weryfikacji

<a id="t046-c01"></a>

##### T046-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Premiera ma timestamp UTC podczas zmiany DST.

**Działanie:** Wyświetl Europe/Warsaw.

**Oczekiwany rezultat:** Czas lokalny jest poprawny dla daty.

**Niedopuszczalny skutek:** Nie użyto stałego UTC+2 przez cały rok.

**Docelowy test:** `tests/automation/test_airing.py::test_airing_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t046-c02"></a>

##### T046-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** nextAiringEpisode jest null.

**Działanie:** Odśwież serię.

**Oczekiwany rezultat:** Subskrypcja nadal może sprawdzać indeks okresowo.

**Niedopuszczalny skutek:** Nie oznaczono jej automatycznie jako zakończona.

**Docelowy test:** `tests/automation/test_airing.py::test_airing_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t046-c03"></a>

##### T046-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Data premiery została przesunięta.

**Działanie:** Zastosuj aktualizację.

**Oczekiwany rezultat:** Nowy termin zastępuje hint, historia poprzednich odczytów pozostaje czytelna.

**Niedopuszczalny skutek:** Nie pobrano innego odcinka na podstawie starego czasu.

**Docelowy test:** `tests/automation/test_airing.py::test_airing_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t046-c04"></a>

##### T046-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Komputer wybudzono po premierze.

**Działanie:** Przelicz najbliższy termin.

**Oczekiwany rezultat:** Powstaje jedno ograniczone sprawdzenie dostępności.

**Niedopuszczalny skutek:** Nie zakłada się, że torrent już istnieje.

**Docelowy test:** `tests/automation/test_airing.py::test_airing_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_airing.py
```

**Wycofanie:** Przy awarii katalogu przejdź do zwykłego interwału sprawdzania indeksu; nie zatrzymuj całej subskrypcji.

**Podstawa techniczna:** [S16](research.md#s16), [S17](research.md#s17), [S18](research.md#s18).

<a id="t047"></a>

### T047. Zapewnij tryb bez działającego katalogu

**Status:** planned.

**Cel:** Awaria AniList nie blokuje lokalnego pliku, magnetu lub wcześniej skonfigurowanej subskrypcji.

**Wymagania:** [R03](spec.md#r03), [R04](spec.md#r04), [R08](spec.md#r08), [R23](spec.md#r23), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T046](#t046)

**Kolejność planowa:** T047; poprzednia karta: T046.

**Kontrakt / symbol:** `create_local_series / bind_catalog_id`.

#### Pliki i zakres edycji

- `anishift/automation/catalog.py`
- `anishift/automation/commands.py`
- `tests/automation/test_manual_catalog.py`

**Istotna granica:** Lokalne media i potwierdzone reguły działają niezależnie od dostępności katalogu online.

#### Kolejność implementacji

1. Pozwól utworzyć lokalny SeriesId z nazwą i ręcznie określonym formatem bez udawania AniList ID.

2. Pozwól wybrać magnet lub .torrent niezależnie od katalogu, z jawnym przypisaniem epizodu.

3. Wyszukiwanie indeksu może użyć zapisanych aliasów bez ponownego odczytu katalogu.

4. Pokaż wiek metadata cache oraz status niezweryfikowany, zamiast wymyślać rok lub liczbę odcinków.

5. Po powrocie katalogu zaproponuj powiązanie lokalnego SeriesId z media ID bez przenoszenia katalogów.

6. Wymagaj potwierdzenia konfliktu, gdy lokalny tytuł pasuje do więcej niż jednego sezonu.

7. Zachowaj wszystkie joby, watch history i directory_key podczas późniejszego powiązania.

8. Nie buduj nieoficjalnego scrape LiveChart jako awaryjnego publicznego API.

#### Scenariusze weryfikacji

<a id="t047-c01"></a>

##### T047-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** AniList jest niedostępne.

**Działanie:** Dodaj własny MKV.

**Oczekiwany rezultat:** Lokalny import nadal działa.

**Niedopuszczalny skutek:** Nie wymaga sieci do posiadanych mediów.

**Docelowy test:** `tests/automation/test_manual_catalog.py::test_manual_catalog_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t047-c02"></a>

##### T047-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Istnieje zapisany alias i subskrypcja.

**Działanie:** Sprawdź Nyaa bez katalogu.

**Oczekiwany rezultat:** Możliwe jest znalezienie kolejnego wydania według zapisanej reguły.

**Niedopuszczalny skutek:** Nie blokuje się każde pobranie na odczycie tytułu.

**Docelowy test:** `tests/automation/test_manual_catalog.py::test_manual_catalog_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t047-c03"></a>

##### T047-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Lokalny tytuł pasuje do dwóch sezonów.

**Działanie:** Powiąż z katalogiem.

**Oczekiwany rezultat:** UI wymaga wyboru konkretnego media ID.

**Niedopuszczalny skutek:** Nie przepisało serii według pierwszego wyniku.

**Docelowy test:** `tests/automation/test_manual_catalog.py::test_manual_catalog_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t047-c04"></a>

##### T047-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Powiązano lokalną serię po miesiącu używania.

**Działanie:** Odczytaj bibliotekę.

**Oczekiwany rezultat:** Ścieżki i historia oglądania pozostają stabilne.

**Niedopuszczalny skutek:** Nie utworzono drugiej kopii biblioteki.

**Docelowy test:** `tests/automation/test_manual_catalog.py::test_manual_catalog_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_manual_catalog.py
```

**Wycofanie:** Cofnij zewnętrzne powiązanie zachowując lokalne ID; nie kasuj historii ani źródeł, gdy metadata provider jest błędny.

**Podstawa techniczna:** [S15](research.md#s15), [S17](research.md#s17), [S19](research.md#s19).

<a id="t048"></a>

### T048. Obsłuż szybkie wpisywanie i spóźnione wyniki

**Status:** planned.

**Cel:** Wyszukiwarka odpowiada na aktualny tekst i nie przeskakuje do starego wyniku w chwili naciśnięcia Enter.

**Wymagania:** [R03](spec.md#r03), [R23](spec.md#r23), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T047](#t047)

**Kolejność planowa:** T048; poprzednia karta: T047.

**Kontrakt / symbol:** `SearchSession.apply_result`.

#### Pliki i zakres edycji

- `anishift/automation/catalog.py`
- `tests/automation/test_search_generation.py`

**Istotna granica:** Debounce i generacje są częścią kontrolera, nie logiki renderowania.

#### Kolejność implementacji

1. Każda zmiana zapytania zwiększa search_generation i unieważnia wyświetlany wybór niepasujący do bieżącego tekstu.

2. Użyj debounce 300 ms dla requestu; lokalny ranking zapisanego cache może działać od razu.

3. Wynik zakończonego requestu stosuj tylko do zgodnego generation.

4. Enter na liście wybiera konkretne media ID z aktualnego snapshotu, nie pozycję w nowo podmienionej liście.

5. Zachowaj query i wyniki po błędzie sieci, z możliwością jawnego ponowienia.

6. Obsłuż paste całego tytułu jako jedno wejście, a nie serię requestów po każdym znaku.

7. Brak wyniku pokazuj odrębnie od ładowania, błędu i wyszukiwania niedokończonego przez limit.

8. Po zamknięciu widoku wyniki mogą trafić do cache, ale nie mogą otworzyć samoczynnie innego ekranu.

#### Scenariusze weryfikacji

<a id="t048-c01"></a>

##### T048-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zapytanie Aster zostało zastąpione Aster 2.

**Działanie:** Stary request wraca później.

**Oczekiwany rezultat:** Wyświetlony zostaje wyłącznie aktualny generation.

**Niedopuszczalny skutek:** Nie nadpisano nowej listy starszym wynikiem.

**Docelowy test:** `tests/automation/test_search_generation.py::test_search_generation_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t048-c02"></a>

##### T048-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Wklejono długi tytuł.

**Działanie:** Poczekaj na debounce.

**Oczekiwany rezultat:** Wysyłany jest jeden request dla całego tekstu.

**Niedopuszczalny skutek:** Nie wysłano kilkudziesięciu requestów.

**Docelowy test:** `tests/automation/test_search_generation.py::test_search_generation_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t048-c03"></a>

##### T048-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Limit API w trakcie pisania.

**Działanie:** Odśwież widok.

**Oczekiwany rezultat:** Tekst pozostaje, widoczny jest retry_at.

**Niedopuszczalny skutek:** Nie wyczyszczono pola i wyboru użytkownika.

**Docelowy test:** `tests/automation/test_search_generation.py::test_search_generation_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t048-c04"></a>

##### T048-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik wyszedł z wyszukiwarki.

**Działanie:** Kończy się request.

**Oczekiwany rezultat:** Wynik może odświeżyć cache, lecz nie nawigację.

**Niedopuszczalny skutek:** Nie uruchomiono pobierania w tle od odpowiedzi search.

**Docelowy test:** `tests/automation/test_search_generation.py::test_search_generation_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_search_generation.py
```

**Wycofanie:** Wyłącz odświeżanie sieciowe podczas pisania i pozostaw jawne Szukaj; nie zmieniaj potwierdzonych zapisów serii.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S09](research.md#s09), [S31](research.md#s31).

<a id="p06"></a>

## P06. Wydania, Nyaa, RSS oraz polityka jakości

**Wynik fazy:** Wydania są filtrowane i dopasowane przed pobraniem.

**Wejście:** P05: potwierdzona tożsamość; P01: polityki.

**Warunek wyjścia:** Niższa jakość jest ukryta; grupa/uploader oddzielone; historia i RSS mają uczciwą informację o kompletności.

**Status fazy:** planned.

<a id="t049"></a>

### T049. Wprowadź wspólny rekord wydania i dowodów dopasowania

**Status:** planned.

**Cel:** Wynik indeksu opisuje konkretne wydanie, a nie zastępuje tożsamości anime.

**Wymagania:** [R04](spec.md#r04), [R06](spec.md#r06), [R08](spec.md#r08), [R19](spec.md#r19), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T048](#t048), [T004](#t004)

**Kolejność planowa:** T049; poprzednia karta: T048.

**Kontrakt / symbol:** `ReleaseCandidate / MatchDecision`.

#### Pliki i zakres edycji

- `anishift/automation/models.py`
- `anishift/automation/releases.py`
- `tests/automation/test_release_model.py`

**Istotna granica:** Indeks, uploader i release group to trzy różne pojęcia.

#### Kolejność implementacji

1. Zdefiniuj ReleaseCandidate z provider, external_id, title, infohash, locator, published_at i source_refs.

2. Dodaj oddzielne pola parsed_group, uploader_account, resolution, episode_tokens, release_version i language_hint.

3. Przechowuj raw_title do prezentacji oraz parsed_fields z poziomem pewności, bez nadpisywania oryginału.

4. Zdefiniuj MatchDecision: accepted, rejected, needs_mapping i unknown_quality z listą powodów.

5. Kandydat nie otrzymuje EpisodeKey automatycznie, dopóki nie przejdzie reguł serii i numeracji.

6. Pochodzenie tego samego infohash w kilku indeksach zapisuj jako wiele source_refs, nie kilka pobrań.

7. Statystyki seeders i rozmiar traktuj jako chwilowe wskazówki, nie gwarancję pobrania.

8. Znormalizuj daty i identyfikatory przy wejściu; brak pola obowiązkowego daje kontrolowaną odmowę rekordu.

#### Scenariusze weryfikacji

<a id="t049-c01"></a>

##### T049-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Ten sam hash pochodzi z dwóch indeksów.

**Działanie:** Scal kandydatów.

**Oczekiwany rezultat:** Jedno wydanie ma dwa źródła pochodzenia.

**Niedopuszczalny skutek:** Nie pokazano dwóch niezależnych pobrań tego samego pliku.

**Docelowy test:** `tests/automation/test_release_model.py::test_release_model_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t049-c02"></a>

##### T049-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nazwa grupy różni się od konta uploadera.

**Działanie:** Zmapuj rekord.

**Oczekiwany rezultat:** Oba pola pozostają odrębne.

**Niedopuszczalny skutek:** Nie uznano autora uploadu za grupę napisów.

**Docelowy test:** `tests/automation/test_release_model.py::test_release_model_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t049-c03"></a>

##### T049-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Rekord nie ma ani magnetu, ani torrent locator.

**Działanie:** Zwaliduj.

**Oczekiwany rezultat:** Kandydat nie może uruchomić pobierania.

**Niedopuszczalny skutek:** Nie wykonano pustego URL.

**Docelowy test:** `tests/automation/test_release_model.py::test_release_model_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t049-c04"></a>

##### T049-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Liczba seedów spadła do zera po zapisaniu.

**Działanie:** Odśwież statystyki.

**Oczekiwany rezultat:** Wydanie pozostaje znane z aktualną dostępnością.

**Niedopuszczalny skutek:** Nie skasowano mapowania epizodu.

**Docelowy test:** `tests/automation/test_release_model.py::test_release_model_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_release_model.py
```

**Wycofanie:** Zachowaj surowe bezpieczne metadane umożliwiające ponowne parsowanie; nie usuwaj transferów po zmianie parsera.

**Podstawa techniczna:** [S20](research.md#s20), [S24](research.md#s24), [S25](research.md#s25).

<a id="t050"></a>

### T050. Opakuj Anitopy i zachowaj niejednoznaczności

**Status:** planned.

**Cel:** Nazwy wydań są parsowane istniejącą biblioteką, z cienką warstwą reguł właściwych AniShift.

**Wymagania:** [R03](spec.md#r03), [R04](spec.md#r04), [R06](spec.md#r06), [R19](spec.md#r19).

**Zależności obowiązkowe:** [T049](#t049), [T002](#t002)

**Kolejność planowa:** T050; poprzednia karta: T049.

**Kontrakt / symbol:** `parse_release_title`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `tests/automation/test_release_parser.py`

**Istotna granica:** Nie implementujemy od zera uniwersalnego parsera nazw anime.

#### Kolejność implementacji

1. Wywołaj anitopy.parse na raw_title bez modyfikowania samego pliku.

2. Znormalizuj wynik słownikowy do typowanego ParsedRelease z opcjonalnymi polami.

3. Zachowaj zakresy, ułamkowe numery, v2 i absolutną numerację jako jawne tokeny do późniejszego mapowania.

4. Nie uznawaj 2026 lub 1080 za numer odcinka, gdy parser nie ma jednoznacznego wyniku.

5. Dodaj małe poprawki tylko dla udokumentowanych przykładów fixture, z pozytywnym i negatywnym przypadkiem.

6. Wersję parser_policy zapisuj w provenance, aby zmiana heurystyk nie przepisała samoczynnie przyjętych jobów.

7. Nie wyciągaj języka rzeczywistych napisów wyłącznie z słów Multi, Dual Audio lub Raw.

8. W przypadku pustego lub sprzecznego wyniku zwróć needs_mapping zamiast tworzyć fikcyjny odcinek.

#### Scenariusze weryfikacji

<a id="t050-c01"></a>

##### T050-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** [Group-A] Aster Journey - 07.5 [1080p] [v2].mkv.

**Działanie:** Parsuj.

**Oczekiwany rezultat:** Zachowane są group, 1080, 7.5 i v2.

**Niedopuszczalny skutek:** Nie zamieniono 7.5 na 75.

**Docelowy test:** `tests/automation/test_release_parser.py::test_filename_parser_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t050-c02"></a>

##### T050-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Aster Journey 2026 1080p batch.

**Działanie:** Parsuj.

**Oczekiwany rezultat:** Rok i jakość nie stają się numerami epizodów.

**Niedopuszczalny skutek:** Nie dodano odcinka 2026.

**Docelowy test:** `tests/automation/test_release_parser.py::test_filename_parser_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t050-c03"></a>

##### T050-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nazwa jest zupełnie nieznana parserowi.

**Działanie:** Parsuj.

**Oczekiwany rezultat:** Wynik jest typowany i wymaga mapowania.

**Niedopuszczalny skutek:** Nie zgłoszono nieobsłużonego KeyError.

**Docelowy test:** `tests/automation/test_release_parser.py::test_filename_parser_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t050-c04"></a>

##### T050-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Aktualizacja reguły parser_policy.

**Działanie:** Ponownie przeanalizuj zapisane wydanie.

**Oczekiwany rezultat:** Nowe propozycje nie zmieniają potwierdzonego EpisodeKey.

**Niedopuszczalny skutek:** Nie przemianowano gotowej biblioteki automatycznie.

**Docelowy test:** `tests/automation/test_release_parser.py::test_filename_parser_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_release_parser.py
```

**Wycofanie:** Przywróć poprzednią parser_policy dla nowych analiz; zachowaj stare potwierdzone mapowania.

**Podstawa techniczna:** [S30](research.md#s30), [S31](research.md#s31).

<a id="t051"></a>

### T051. Ukryj wydania poniżej 1080p i uczyń ranking przewidywalnym

**Status:** planned.

**Cel:** W zwykłej wyszukiwarce użytkownik nie musi odfiltrowywać 480p i 720p.

**Wymagania:** [R05](spec.md#r05), [R08](spec.md#r08), [R24](spec.md#r24).

**Zależności obowiązkowe:** [T050](#t050)

**Kolejność planowa:** T051; poprzednia karta: T050.

**Kontrakt / symbol:** `filter_quality`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `tests/automation/test_quality_filter.py`

**Istotna granica:** Wyższa rozdzielczość oznacza potencjalnie większy koszt dysku, a nie automatycznie lepsze tłumaczenie.

#### Kolejność implementacji

1. Po parsowaniu odrzuć rozdzielczości niższe od min_resolution=1080.

2. Wydania o nieznanej klasie przenieś poza zwykłe wyniki do sekcji wymagającej metadanych.

3. Domyślnie preferuj 1080p przed wyższymi klasami, jeżeli użytkownik nie ustawi preferowania 4K.

4. Nie odrzucaj 2160p tylko dlatego, że filtr minimum wynosi 1080.

5. Zachowaj codec, bit depth i source tag jako informacje, nie twarde wymogi bez ustawienia użytkownika.

6. Nie traktuj oznaczenia 1080p jako gwarancji braku upscalingu lub dobrego bitrate.

7. Przed wykonaniem ponów sprawdzenie klasy na rzeczywistym media probe.

8. Wynik pusty po filtracji wyjaśnij liczbą odrzuconych słabszych wydań, bez pokazywania ich jako normalnych opcji.

#### Scenariusze weryfikacji

<a id="t051-c01"></a>

##### T051-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Lista zawiera 480p, 720p, 1080p i 2160p.

**Działanie:** Zastosuj minimum.

**Oczekiwany rezultat:** Zwykłe wyniki zawierają tylko 1080p i 2160p.

**Niedopuszczalny skutek:** Nie pokazano 720p między dopuszczonymi wydaniami.

**Docelowy test:** `tests/automation/test_quality_filter.py::test_quality_filter_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t051-c02"></a>

##### T051-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Wydanie ma nieznaną jakość.

**Działanie:** Filtruj.

**Oczekiwany rezultat:** Trafia do osobnej ścieżki weryfikacji.

**Niedopuszczalny skutek:** Nie uznano unknown za 1080p.

**Docelowy test:** `tests/automation/test_quality_filter.py::test_quality_filter_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t051-c03"></a>

##### T051-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Opis 2160p okazuje się 720p po probe.

**Działanie:** Przeprowadź admission.

**Oczekiwany rezultat:** Źródło jest odrzucone przed tłumaczeniem.

**Niedopuszczalny skutek:** Nie zaakceptowano kłamliwej etykiety.

**Docelowy test:** `tests/automation/test_quality_filter.py::test_quality_filter_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t051-c04"></a>

##### T051-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik zmienia preferencję na 2160p.

**Działanie:** Odśwież ranking.

**Oczekiwany rezultat:** Wyższa klasa jest preferowana bez zmiany minimum.

**Niedopuszczalny skutek:** Nie pobrano na nowo istniejących dobrych odcinków bez decyzji.

**Docelowy test:** `tests/automation/test_quality_filter.py::test_quality_filter_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_quality_filter.py
```

**Wycofanie:** Przywróć wcześniejszy profil jakości; nie usuwaj już pobranych plików po zmianie minimum.

**Podstawa techniczna:** [S30](research.md#s30), [S31](research.md#s31).

<a id="t052"></a>

### T052. Wprowadź wybór grup i jawne fallbacki

**Status:** planned.

**Cel:** Program pamięta preferowaną grupę dla serii i nie zmienia jej po cichu przy opóźnieniu premiery.

**Wymagania:** [R06](spec.md#r06), [R07](spec.md#r07), [R09](spec.md#r09), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T051](#t051)

**Kolejność planowa:** T052; poprzednia karta: T051.

**Kontrakt / symbol:** `GroupPolicy.evaluate`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `tests/automation/test_group_policy.py`

**Istotna granica:** Nie potwierdzono dwóch ulubionych grup właściciela ani globalnego zwycięzcy jakości.

#### Kolejność implementacji

1. Zapisz ordered preferred_groups i opcjonalny verified_uploader dla profilu serii.

2. Zdefiniuj strict_group oraz allowed_fallback_groups z osobnym opóźnieniem przejścia na fallback.

3. Porównuj znormalizowane nazwy grup dokładnie; nie dopasowuj losowo podciągu w całym tytule.

4. Brak preferencji oznacza neutralny wybór według zgodności, kompletności i dostępności, a nie odgadniętą ulubioną grupę.

5. Przed subskrypcją pokaż przykładowe wydanie i zapisz potwierdzoną regułę.

6. Pola trusted/remake z indeksu traktuj jako sygnały indeksu, nie dowód prawdziwego języka lub najwyższej jakości.

7. Zmiana grupy dla już gotowego epizodu tworzy propozycję nowej rewizji, a nie automatyczną zamianę.

8. Zapisz powód każdego automatycznego wyboru i powód odrzucenia konkurencyjnego wydania.

#### Scenariusze weryfikacji

<a id="t052-c01"></a>

##### T052-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Preferencja Group-A, wydania A i B zgodne.

**Działanie:** Wybierz.

**Oczekiwany rezultat:** Wygrywa Group-A według zapisanej reguły.

**Niedopuszczalny skutek:** Nie wybrano B tylko przez większą liczbę seedów.

**Docelowy test:** `tests/automation/test_group_policy.py::test_group_policy_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t052-c02"></a>

##### T052-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Strict Group-A i dostępna tylko Group-B.

**Działanie:** Sprawdź subskrypcję.

**Oczekiwany rezultat:** Seria czeka na preferowaną grupę.

**Niedopuszczalny skutek:** Nie złamano strict_group po jednym ticku.

**Docelowy test:** `tests/automation/test_group_policy.py::test_group_policy_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t052-c03"></a>

##### T052-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Uploader nosi nazwę podobną do grupy.

**Działanie:** Oceń zgodność.

**Oczekiwany rezultat:** Weryfikacja używa oddzielnych pól.

**Niedopuszczalny skutek:** Nie uznano podobnego konta za zweryfikowane.

**Docelowy test:** `tests/automation/test_group_policy.py::test_group_policy_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t052-c04"></a>

##### T052-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Fallback został jawnie włączony i minął jego termin.

**Działanie:** Wybierz wydanie.

**Oczekiwany rezultat:** Możliwy jest Group-B z widocznym powodem.

**Niedopuszczalny skutek:** Nie zmieniono już gotowego odcinka bez zgody.

**Docelowy test:** `tests/automation/test_group_policy.py::test_group_policy_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_group_policy.py
```

**Wycofanie:** Wyłącz regułę automatycznego wyboru dla serii; pozostaw już pobrane materiały i ich provenance.

**Podstawa techniczna:** [S24](research.md#s24), [S25](research.md#s25), [S41](research.md#s41), [S42](research.md#s42).

<a id="t053"></a>

### T053. Zaimplementuj parser RSS Nyaa z kontrolą formatu

**Status:** planned.

**Cel:** Nowe wydania trafiają do jednego wspólnego kontraktu bez polegania na nieistniejącym stabilnym JSON API.

**Wymagania:** [R08](spec.md#r08), [R09](spec.md#r09), [R23](spec.md#r23), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T052](#t052)

**Kolejność planowa:** T053; poprzednia karta: T052.

**Kontrakt / symbol:** `NyaaProvider.poll_feed`.

#### Pliki i zakres edycji

- `anishift/automation/providers/nyaa.py`
- `tests/automation/test_nyaa_rss.py`

**Istotna granica:** Namespace, kształt RSS i realne parametry są sprawdzane na żywym wdrożeniu w pierwszej fazie.

#### Kolejność implementacji

1. Pobieraj RSS przez wspólną granicę HTTP z parametrami zweryfikowanymi w T004.

2. Użyj defusedxml i namespace-aware odczytu lokalnych pól Nyaa; nie polegaj na konkretnym prefiksie XML.

3. Odczytaj title, guid, pubDate, infoHash, categoryId, size i dostępne statystyki.

4. Obsłuż link będący magnetem albo odnośnikiem .torrent; zweryfikuj go przed zapisaniem.

5. Wymagaj poprawnego identyfikatora lub infohash; częściowo uszkodzony pojedynczy item pomiń z ostrzeżeniem.

6. Pusty poprawny channel to poprawny brak wyników; HTML challenge i niepoprawny XML to awaria źródła.

7. Zachowaj nakładające się okno ostatnio widzianych wpisów i deduplikację, zamiast polegać wyłącznie na czasie publikacji.

8. RSS traktuj jako feed najnowszych wyników; nie obiecuj pełnej historii sezonu z jednego pobrania.

#### Scenariusze weryfikacji

<a id="t053-c01"></a>

##### T053-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** RSS używa innego prefiksu dla namespace Nyaa.

**Działanie:** Parsuj.

**Oczekiwany rezultat:** Pola nadal zostają odczytane.

**Niedopuszczalny skutek:** Nie przywiązano parsera do tekstu nyaa: w nazwie tagu.

**Docelowy test:** `tests/automation/test_nyaa_rss.py::test_nyaa_rss_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t053-c02"></a>

##### T053-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Item ma link do .torrent zamiast magnetu.

**Działanie:** Zmapuj rekord.

**Oczekiwany rezultat:** Powstaje poprawny locator i zachowany infohash.

**Niedopuszczalny skutek:** Nie odrzucono poprawnego wydania.

**Docelowy test:** `tests/automation/test_nyaa_rss.py::test_nyaa_rss_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t053-c03"></a>

##### T053-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Jeden item jest uszkodzony, pozostałe poprawne.

**Działanie:** Parsuj feed.

**Oczekiwany rezultat:** Poprawne rekordy pozostają, ostrzeżenie jest policzone.

**Niedopuszczalny skutek:** Nie skasowano całej listy z powodu jednego wpisu.

**Docelowy test:** `tests/automation/test_nyaa_rss.py::test_nyaa_rss_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t053-c04"></a>

##### T053-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Powtórzony feed ma te same wpisy i jeden nowy.

**Działanie:** Uzgodnij wyniki.

**Oczekiwany rezultat:** Przyjęte zostaje wyłącznie nowe wydanie.

**Niedopuszczalny skutek:** Nie zaplanowano ponownie dawnych odcinków.

**Docelowy test:** `tests/automation/test_nyaa_rss.py::test_nyaa_rss_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_nyaa_rss.py
```

**Wycofanie:** Wyłącz adapter Nyaa i pozostaw custom RSS, magnet oraz lokalny import; nie przestawiaj automatycznie na nieznany mirror.

**Podstawa techniczna:** [S23](research.md#s23), [S24](research.md#s24), [S32](research.md#s32).

<a id="t054"></a>

### T054. Dodaj stronicowane wyszukiwanie historyczne Nyaa

**Status:** planned.

**Cel:** Wyszukanie zakończonego sezonu nie ogranicza się do najnowszych wpisów RSS.

**Wymagania:** [R03](spec.md#r03), [R08](spec.md#r08), [R10](spec.md#r10), [R23](spec.md#r23), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T053](#t053)

**Kolejność planowa:** T054; poprzednia karta: T053.

**Kontrakt / symbol:** `NyaaProvider.search_history`.

#### Pliki i zakres edycji

- `anishift/automation/providers/nyaa.py`
- `tests/automation/test_nyaa_search.py`

**Istotna granica:** Z kodu istniejącego pluginu bierzemy rozpoznany format i przykłady, nie całe wykonanie, historię lub warstwę UI.

#### Kolejność implementacji

1. Użyj ograniczonego HTMLParser opartego na strukturze tabeli, linkach /view/ i linkach pobierania, bez wykonywania HTML.

2. Buduj parametry przez httpx params, nie ręczną konkatenację tytułu do URL.

3. Przeszukuj potwierdzone aliasy w ustalonej kolejności, zatrzymując się po pokryciu żądanych odcinków albo limicie sesji.

4. Paginację opieraj na odnośniku next i identyfikatorach nowych wyników, nie na sztywnej regule len==75.

5. Ogranicz pojedynczą porcję do trzech stron i kontynuuj następne porcje z zapisanym cursorem oraz budżetem hosta.

6. Powtarzający się identyczny zestaw ID przy innym p oznacza zatrzymanie paginacji i incomplete result.

7. Pokaż użytkownikowi, że lista jest częściowa, dopóki wyszukiwanie nie zakończyło wszystkich wymaganych porcji.

8. Zmiana struktury strony daje schema_changed; nie zamieniaj jej na zero dostępnych odcinków.

#### Scenariusze weryfikacji

<a id="t054-c01"></a>

##### T054-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Sezon ma stare wydania poza RSS.

**Działanie:** Wykonaj wyszukiwanie HTML.

**Oczekiwany rezultat:** Paginacja znajduje starsze pasujące rekordy.

**Niedopuszczalny skutek:** Nie ogłoszono braków po samym najnowszym feedzie.

**Docelowy test:** `tests/automation/test_nyaa_search.py::test_nyaa_history_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t054-c02"></a>

##### T054-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Serwer ignoruje parametr p.

**Działanie:** Przejdź do kolejnej strony.

**Oczekiwany rezultat:** Powtarzalne ID zatrzymują pętlę z wynikiem częściowym.

**Niedopuszczalny skutek:** Nie trwa nieskończone pobieranie tej samej strony.

**Docelowy test:** `tests/automation/test_nyaa_search.py::test_nyaa_history_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t054-c03"></a>

##### T054-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Tabela zmieniła strukturę.

**Działanie:** Parsuj.

**Oczekiwany rezultat:** Pojawia się schema_changed i zachowany cache.

**Niedopuszczalny skutek:** Nie wyświetlono fałszywego Brak anime.

**Docelowy test:** `tests/automation/test_nyaa_search.py::test_nyaa_history_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t054-c04"></a>

##### T054-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Sesję przerwano po pierwszej porcji.

**Działanie:** Wznów wyszukiwanie.

**Oczekiwany rezultat:** Cursor kontynuuje z deduplikacją.

**Niedopuszczalny skutek:** Nie traci się już wybranych odcinków.

**Docelowy test:** `tests/automation/test_nyaa_search.py::test_nyaa_history_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_nyaa_search.py
```

**Wycofanie:** Wyłącz historyczne HTML wyszukiwanie, pozostawiając ostatnie RSS i ręczne locatory; oznacz brak pełności wyników.

**Podstawa techniczna:** [S23](research.md#s23), [S25](research.md#s25), [S26](research.md#s26).

<a id="t055"></a>

### T055. Udostępnij drugi jawny kanał RSS bez frameworka pluginów

**Status:** planned.

**Cel:** Właściciel może dodać wiarygodny feed grupy lub innego źródła bez pisania nowej aplikacji.

**Wymagania:** [R06](spec.md#r06), [R08](spec.md#r08), [R23](spec.md#r23), [R26](spec.md#r26), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T054](#t054)

**Kolejność planowa:** T055; poprzednia karta: T054.

**Kontrakt / symbol:** `RssProvider.poll_feed`.

#### Pliki i zakres edycji

- `anishift/automation/providers/rss.py`
- `tests/automation/test_custom_rss.py`

**Istotna granica:** AnimeTosho może zostać użyte przez zgodny feed po sprawdzeniu; nie deklarujemy gotowego adaptera Newznab bez caps proof.

#### Kolejność implementacji

1. Przyjmij nazwę źródła, publiczny HTTPS URL i opcjonalną etykietę grupy jako konfigurację, nie kod wykonywalny.

2. Obsłuż standardowe RSS item title, guid, pubDate, link oraz enclosure.

3. Akceptuj magnet albo zatwierdzony .torrent locator; inne pliki nie uruchamiają pobierania.

4. Nie zakładaj pełnej historii, języka lub rozdzielczości, gdy feed ich nie dostarcza.

5. Przekaż tytuł do wspólnego parsera i tych samych filtrów jakości, grup oraz numeracji.

6. Zablokuj XML entities, body ponad limit, prywatne redirecty i automatyczne uruchamianie skryptów pluginów.

7. Przed włączeniem automatycznego pobierania pokaż podgląd kilku odczytanych rekordów i wynik filtracji.

8. Usuń źródło przez wyłączenie przyszłych odczytów; już zaakceptowane joby zachowują swoje source_refs.

#### Scenariusze weryfikacji

<a id="t055-c01"></a>

##### T055-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Feed grupy ma poprawne magnety 1080p.

**Działanie:** Przetwórz rekordy.

**Oczekiwany rezultat:** Przechodzą przez te same reguły co Nyaa.

**Niedopuszczalny skutek:** Nie powstała osobna kolejka dla custom RSS.

**Docelowy test:** `tests/automation/test_custom_rss.py::test_custom_rss_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t055-c02"></a>

##### T055-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Feed nie ma jakości w tytułach.

**Działanie:** Oceń wyniki.

**Oczekiwany rezultat:** Wydania trafiają do weryfikacji metadanych.

**Niedopuszczalny skutek:** Nie oznaczono ich domyślnie 1080p.

**Docelowy test:** `tests/automation/test_custom_rss.py::test_custom_rss_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t055-c03"></a>

##### T055-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Enclosure wskazuje exe lub stronę logowania.

**Działanie:** Zwaliduj locator.

**Oczekiwany rezultat:** Pobieranie nie zostaje uruchomione.

**Niedopuszczalny skutek:** Nie wykonano pliku z feedu.

**Docelowy test:** `tests/automation/test_custom_rss.py::test_custom_rss_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t055-c04"></a>

##### T055-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Właściciel wyłączył źródło.

**Działanie:** Wykonaj następny tick.

**Oczekiwany rezultat:** Nie ma dalszych requestów, gotowe materiały pozostają.

**Niedopuszczalny skutek:** Nie usunięto biblioteki związanej ze źródłem.

**Docelowy test:** `tests/automation/test_custom_rss.py::test_custom_rss_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_custom_rss.py
```

**Wycofanie:** Wyłącz konkretny feed bez zmiany pozostałych providerów; zachowaj jego już przyjęte rekordy i dowody wyboru.

**Podstawa techniczna:** [S16](research.md#s16), [S24](research.md#s24), [S29](research.md#s29), [S32](research.md#s32).

<a id="t056"></a>

### T056. Utwórz deterministyczny wybór wydania

**Status:** planned.

**Cel:** Automatyczny wybór jest odtwarzalną regułą, którą można wyjaśnić użytkownikowi.

**Wymagania:** [R04](spec.md#r04), [R05](spec.md#r05), [R06](spec.md#r06), [R08](spec.md#r08), [R09](spec.md#r09), [R19](spec.md#r19).

**Zależności obowiązkowe:** [T055](#t055)

**Kolejność planowa:** T056; poprzednia karta: T055.

**Kontrakt / symbol:** `select_release`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `tests/automation/test_release_decision.py`

**Istotna granica:** Nie istnieje jedna globalna najlepsza grupa dla wszystkich sezonów i wydań.

#### Kolejność implementacji

1. Najpierw zastosuj twarde odrzucenia: zła seria/sezon, zły epizod, zbyt niska jakość, niedozwolona grupa i zły typ pliku.

2. Potem oceniaj preferencję grupy, klasę jakości, poprawną numerację, dostępność i stabilny identyfikator rozstrzygający remis.

3. Nie mieszaj wymagań twardych w jeden wynik punktowy, który da się nadrobić liczbą seedów.

4. Przy remisie niejasnej tożsamości zwróć needs_mapping, zamiast przyjmować pierwszy element listy.

5. Zapisz reasons i odczyt preferencji użyty do decyzji, aby późniejsze zmiany ustawień nie zmieniały historii.

6. Już gotowy odcinek nie jest pobierany ponownie tylko z powodu pojawienia się wydania v2.

7. Dla ręcznego wyboru pokaż finalny podgląd serii, numerów, grupy, jakości, rozmiaru i miejsca docelowego.

8. Zatwierdzenie podglądu tworzy idempotentny intent download, nie bezpośredni efekt w rendererze.

#### Scenariusze weryfikacji

<a id="t056-c01"></a>

##### T056-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** 720p ma milion seedów, 1080p ma kilka.

**Działanie:** Wybierz zgodnie z minimum.

**Oczekiwany rezultat:** Wygrywa dopuszczone 1080p.

**Niedopuszczalny skutek:** Nie nadrobiono złej jakości punktami za dostępność.

**Docelowy test:** `tests/automation/test_release_decision.py::test_release_decision_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t056-c02"></a>

##### T056-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Dwie serie są równie podobne.

**Działanie:** Oceń automatyczny wybór.

**Oczekiwany rezultat:** Wynik wymaga konkretnego mapowania.

**Niedopuszczalny skutek:** Nie pobrano pierwszej alfabetycznie.

**Docelowy test:** `tests/automation/test_release_decision.py::test_release_decision_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t056-c03"></a>

##### T056-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Pojawiło się v2 dla gotowego odcinka.

**Działanie:** Sprawdź subskrypcję.

**Oczekiwany rezultat:** Powstaje co najwyżej propozycja aktualizacji.

**Niedopuszczalny skutek:** Nie nadpisano gotowego pliku bez zgody.

**Docelowy test:** `tests/automation/test_release_decision.py::test_release_decision_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t056-c04"></a>

##### T056-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Preferencje zmieniono po zatwierdzeniu podglądu.

**Działanie:** Wykonaj zapisany intent.

**Oczekiwany rezultat:** Używa zaakceptowanej decyzji albo wymaga nowego zatwierdzenia przy konflikcie.

**Niedopuszczalny skutek:** Nie podmieniono ukradkiem grupy wydania.

**Docelowy test:** `tests/automation/test_release_decision.py::test_release_decision_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_release_decision.py
```

**Wycofanie:** Anuluj nierozpoczęty intent; gotowe wyniki historycznych decyzji zachowaj wraz z reasons.

**Podstawa techniczna:** [S20](research.md#s20), [S24](research.md#s24), [S30](research.md#s30), [S31](research.md#s31).

<a id="p07"></a>

## P07. qBittorrent: uzgadnianie transferów i izolacja własności

**Wynik fazy:** Własne transfery są kontrolowane, obce pozostają nietknięte.

**Wejście:** P00 qBit proof oraz P06 wybór wydania.

**Warunek wyjścia:** Timeout add nie dubluje transferu; per-file gotowość nie czeka na całą paczkę.

**Status fazy:** planned.

<a id="t057"></a>

### T057. Połącz się z istniejącym klientem bez zmiany jego zabezpieczeń

**Status:** planned.

**Cel:** Wybierz qBittorrent jako wspierany backend, nie udając, że użytkownik już go posiada lub skonfigurował.

**Wymagania:** [R08](spec.md#r08), [R23](spec.md#r23), [R26](spec.md#r26), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T003](#t003), [T056](#t056), [T032](#t032)

**Kolejność planowa:** T057; poprzednia karta: T056.

**Kontrakt / symbol:** `QbitAdapter.connect / capabilities`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `tests/automation/test_qbit_connection.py`

**Istotna granica:** Akceptacja qBittorrent lub potwierdzenie zgodnego posiadanego klienta jest decyzją instalacyjną właściciela.

#### Kolejność implementacji

1. Wczytaj jawny loopback URL i referencję credentials; pokaż instrukcję włączenia WebUI na localhost po zgodzie właściciela.

2. Nie wyłączaj uwierzytelniania, CSRF, sprawdzania Host ani nie włączaj nasłuchiwania na publicznych interfejsach.

3. Pobierz app_version i web_api_version przed uznaniem połączenia za gotowe.

4. Zastosuj macierz capability wynikającą z T003 i wersji wrappera, a nie dokumentacji latest/dev.

5. Na brak klienta pokaż Połącz qBittorrent; używany przez właściciela BitTorrent nie jest automatycznie zgodny z tym API.

6. Utwórz sesję wrappera z timeoutem i zamknij ją przy końcu workera.

7. 401/403 mapuj na auth_required bez zapisywania loginu/hasła w logach.

8. Nie instaluj, nie uruchamiaj i nie aktualizuj klienta bez jawnej akcji setupu.

#### Scenariusze weryfikacji

<a id="t057-c01"></a>

##### T057-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Poprawny qBittorrent na loopback.

**Działanie:** Sprawdź połączenie.

**Oczekiwany rezultat:** Widoczne są realne wersje i wspierane funkcje.

**Niedopuszczalny skutek:** Nie podano wersji domyślnej jako wykrytej.

**Docelowy test:** `tests/automation/test_qbit_connection.py::test_qbit_connection_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t057-c02"></a>

##### T057-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Port wskazuje inną aplikację.

**Działanie:** Wykonaj probe.

**Oczekiwany rezultat:** Połączenie jest odrzucone jako niewłaściwy kontrakt.

**Niedopuszczalny skutek:** Nie uznano HTTP 200 za gotowego klienta.

**Docelowy test:** `tests/automation/test_qbit_connection.py::test_qbit_connection_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t057-c03"></a>

##### T057-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Błędne hasło.

**Działanie:** Spróbuj połączenia.

**Oczekiwany rezultat:** Stan auth_required z bezpieczną wskazówką.

**Niedopuszczalny skutek:** Nie powtarza się login bez końca.

**Docelowy test:** `tests/automation/test_qbit_connection.py::test_qbit_connection_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t057-c04"></a>

##### T057-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Klient został uruchomiony po wcześniejszym błędzie.

**Działanie:** Ponów probe.

**Oczekiwany rezultat:** Można wznowić istniejące intenty.

**Niedopuszczalny skutek:** Nie trzeba ponownie wyszukiwać anime.

**Docelowy test:** `tests/automation/test_qbit_connection.py::test_qbit_connection_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_qbit_connection.py
```

**Wycofanie:** Odłącz AniShift i usuń jedynie jego lokalną referencję połączenia po potwierdzeniu; nie zmieniaj ustawień bezpieczeństwa klienta.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21), [S22](research.md#s22).

<a id="t058"></a>

### T058. Zapisz zamiar pobrania przed wywołaniem add

**Status:** planned.

**Cel:** Utrata odpowiedzi sieciowej nie może skutkować utratą śladu transferu lub powtarzanym dodawaniem.

**Wymagania:** [R08](spec.md#r08), [R16](spec.md#r16), [R17](spec.md#r17), [R20](spec.md#r20).

**Zależności obowiązkowe:** [T057](#t057)

**Kolejność planowa:** T058; poprzednia karta: T057.

**Kontrakt / symbol:** `prepare_download_intent / add_transfer`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `anishift/automation/store.py`
- `tests/automation/test_download_intent.py`

**Istotna granica:** Dokładnie-jeden skuteczny transfer wynika z idempotencji i reconciliation, nie z transakcji obejmującej dwie aplikacje.

#### Kolejność implementacji

1. Zapisz operation_id, source_refs, oczekiwany infohash, docelowy katalog downloads i wybrane epizody przed requestem.

2. Jeśli infohash jest znany, najpierw sprawdź, czy klient już go posiada.

3. Jeśli hash jest nieznany przy lokalnym .torrent, użyj unikalnego tagu operation_id i zatrzymanego dodania, potem odczytaj tożsamość klienta.

4. Dla magnetu uruchom wyłącznie udowodnioną ścieżkę metadata-only; bez niej nie startuj automatycznie nieznanej paczki.

5. Ustaw osobną kategorię AniShift oraz konkretny save_path; wyłącz automatic torrent management dla tych transferów, jeżeli zmieniałoby ścieżkę.

6. Nie używaj skip_checking, aby udawać ukończenie już istniejących danych.

7. Po odpowiedzi add odczytaj faktyczny rekord transferu i zapisz jego identity; samo Ok. nie wystarcza.

8. Przy timeout przejdź do reconciling, a nie natychmiastowego drugiego add.

#### Scenariusze weryfikacji

<a id="t058-c01"></a>

##### T058-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nowy znany magnet.

**Działanie:** Zapisz intent i wykonaj add.

**Oczekiwany rezultat:** W bazie istnieje operation_id przed skutkiem zewnętrznym.

**Niedopuszczalny skutek:** Nie wykonano requestu przed trwałym zapisem zamiaru.

**Docelowy test:** `tests/automation/test_download_intent.py::test_download_intent_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t058-c02"></a>

##### T058-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Lokalny .torrent bez znanego hasha.

**Działanie:** Dodaj stopped z tagiem operacji.

**Oczekiwany rezultat:** Tożsamość jest odczytana z klienta przed startem danych.

**Niedopuszczalny skutek:** Nie implementowano pełnego własnego silnika BitTorrent.

**Docelowy test:** `tests/automation/test_download_intent.py::test_download_intent_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t058-c03"></a>

##### T058-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Add zwrócił sukces, ale brak transferu w odczycie.

**Działanie:** Uzgodnij.

**Oczekiwany rezultat:** Stan pozostaje nierozstrzygnięty i wymaga ograniczonego retry.

**Niedopuszczalny skutek:** Nie ogłoszono rozpoczętego pobierania.

**Docelowy test:** `tests/automation/test_download_intent.py::test_download_intent_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t058-c04"></a>

##### T058-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Odpowiedź add została utracona.

**Działanie:** Ponów uzgodnienie.

**Oczekiwany rezultat:** Zostaje znaleziony jeden transfer po hash/tagu.

**Niedopuszczalny skutek:** Nie dodano automatycznie drugiego.

**Docelowy test:** `tests/automation/test_download_intent.py::test_download_intent_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_download_intent.py
```

**Wycofanie:** Zatrzymaj nierozstrzygnięty intent i uzgodnij stan klienta; nie usuwaj transferu wyłącznie dlatego, że brak odpowiedzi add.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21), [S22](research.md#s22).

<a id="t059"></a>

### T059. Uzgadniaj własne transfery po hashu i trwałym identyfikatorze

**Status:** planned.

**Cel:** Klient torrent pozostaje właścicielem transferu, a AniShift rozpoznaje jego faktyczny stan.

**Wymagania:** [R16](spec.md#r16), [R17](spec.md#r17), [R20](spec.md#r20), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T058](#t058)

**Kolejność planowa:** T059; poprzednia karta: T058.

**Kontrakt / symbol:** `reconcile_transfer`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `tests/automation/test_qbit_reconcile.py`

**Istotna granica:** Obsługa v2 wymaga proof klienta; nie dopisujemy deklaracji wsparcia wyłącznie na podstawie długości hasha.

#### Kolejność implementacji

1. Normalizuj obsługiwane BTIH hex/base32 do jednego klucza i zachowuj oryginalny locator.

2. Pure v2 lub nierozpoznany locator obsłuż przez metadane klienta i tag intentu tylko po potwierdzeniu wsparcia; inaczej jawna odmowa.

3. Po reconnect odczytaj dokładnie zapisane hashy oraz kategorię/tagi potrzebne do nierozstrzygniętych add.

4. Brak transferu w jednej niepełnej odpowiedzi nie oznacza, że został usunięty; potwierdź pełnym odczytem.

5. Istniejący obcy hash powiąż jako BORROWED i nie zmieniaj jego ustawień.

6. Po usunięciu własnego torrenta z klienta zachowaj historię oraz gotowe produkty; zaproponuj ponowne pobranie brakującego źródła.

7. Nie utożsamiaj dwóch transferów według tytułu, nazwy folderu lub rozmiaru.

8. Każde przejście między known, missing i unresolved zapisuj z czasem ostatniego potwierdzenia.

#### Scenariusze weryfikacji

<a id="t059-c01"></a>

##### T059-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** BTIH zapisano raz hex, raz base32.

**Działanie:** Znormalizuj locatory.

**Oczekiwany rezultat:** Obie postacie wskazują jedną tożsamość.

**Niedopuszczalny skutek:** Nie powstały dwa transfery tego samego v1 hasha.

**Docelowy test:** `tests/automation/test_qbit_reconcile.py::test_qbit_reconcile_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t059-c02"></a>

##### T059-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Klient zwraca częściową odpowiedź bez jednego hasha.

**Działanie:** Uzgodnij.

**Oczekiwany rezultat:** Rekord nie znika przed potwierdzeniem pełnym odczytem.

**Niedopuszczalny skutek:** Nie uruchomiono ponownie pobierania na podstawie luki.

**Docelowy test:** `tests/automation/test_qbit_reconcile.py::test_qbit_reconcile_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t059-c03"></a>

##### T059-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik usunął torrent, ale finalny MKV istnieje.

**Działanie:** Odśwież stan.

**Oczekiwany rezultat:** Film pozostaje gotowy, transfer oznaczony jako missing.

**Niedopuszczalny skutek:** Nie usunięto produktu biblioteki.

**Docelowy test:** `tests/automation/test_qbit_reconcile.py::test_qbit_reconcile_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t059-c04"></a>

##### T059-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Worker wrócił po awarii add nieznanego hasha.

**Działanie:** Znajdź unikalny tag intentu.

**Oczekiwany rezultat:** Operacja zostaje powiązana albo jawnie nierozstrzygnięta.

**Niedopuszczalny skutek:** Nie zgadnięto transferu według nazwy anime.

**Docelowy test:** `tests/automation/test_qbit_reconcile.py::test_qbit_reconcile_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_qbit_reconcile.py
```

**Wycofanie:** Zatrzymaj automatyczne mutacje nierozpoznanego transferu; zachowaj rekord do ręcznego powiązania bez kasowania danych.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21).

<a id="t060"></a>

### T060. Odczytaj pliki i priorytety przez rzeczywiste indeksy API

**Status:** planned.

**Cel:** Selekcja odcinków w paczce działa na prawdziwych file_index, nie na kolejności listy w odpowiedzi.

**Wymagania:** [R08](spec.md#r08), [R11](spec.md#r11), [R19](spec.md#r19), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T059](#t059)

**Kolejność planowa:** T060; poprzednia karta: T059.

**Kontrakt / symbol:** `read_transfer_files / apply_selection`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `tests/automation/test_qbit_files.py`

**Istotna granica:** Index z API jest częścią kontraktu, a nie numerem wiersza TUI.

#### Kolejność implementacji

1. Po dostępności metadanych pobierz index, name, size, progress i priority każdego pliku.

2. Zapisz mapowanie transfer_id + file_index → bezpieczna ścieżka względna i opcjonalny EpisodeKey.

3. Zwaliduj ścieżki przez wspólny resolver przed jakimkolwiek dostępem do filesystemu.

4. Ustaw priorytet zero plikom niezaakceptowanym i normalny zaakceptowanym, zachowując własność transferu.

5. Dla BORROWED nie modyfikuj priorytetów; pozwól tylko wskazać już dostępny plik.

6. 409 metadata unavailable oznacza oczekiwanie na metadane, nie brak odcinków.

7. Jeśli metadane zmieniły się lub indeks wskazuje inną nazwę, unieważnij poprzedni wybór i wymagaj ponownej walidacji.

8. Nie pobieraj plików wykonywalnych, próbek, instrukcji instalacji i archiwów tylko dlatego, że są w paczce.

#### Scenariusze weryfikacji

<a id="t060-c01"></a>

##### T060-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Odpowiedź zawiera index 2 i 7 w dwóch elementach.

**Działanie:** Zaznacz drugi plik.

**Oczekiwany rezultat:** API dostaje index 7, nie pozycję 1.

**Niedopuszczalny skutek:** Nie pobrano złego odcinka.

**Docelowy test:** `tests/automation/test_qbit_files.py::test_qbit_files_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t060-c02"></a>

##### T060-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Metadane nie są jeszcze gotowe.

**Działanie:** Pobierz files.

**Oczekiwany rezultat:** Stan czeka z ograniczonym retry.

**Niedopuszczalny skutek:** Nie uznano pustej listy za zakończenie paczki.

**Docelowy test:** `tests/automation/test_qbit_files.py::test_qbit_files_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t060-c03"></a>

##### T060-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Ścieżka pliku próbuje wyjść poza downloads.

**Działanie:** Zwaliduj.

**Oczekiwany rezultat:** Plik jest odrzucony przed nadaniem priorytetu.

**Niedopuszczalny skutek:** Nie utworzono pliku poza rootem.

**Docelowy test:** `tests/automation/test_qbit_files.py::test_qbit_files_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t060-c04"></a>

##### T060-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Po restarcie lista ma inną kolejność.

**Działanie:** Odtwórz wybór.

**Oczekiwany rezultat:** Wybór jest stabilny według index i tożsamości.

**Niedopuszczalny skutek:** Nie zresetowano wybranych epizodów.

**Docelowy test:** `tests/automation/test_qbit_files.py::test_qbit_files_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_qbit_files.py
```

**Wycofanie:** Nie zmieniaj priorytetów obcych transferów; własne ustawienia można przywrócić z zapisanego zaakceptowanego manifestu.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21).

<a id="t061"></a>

### T061. Potwierdzaj ukończenie każdego wybranego pliku

**Status:** planned.

**Cel:** Pierwszy odcinek z paczki może zostać przetworzony, gdy inne pliki nadal się pobierają.

**Wymagania:** [R11](spec.md#r11), [R12](spec.md#r12), [R16](spec.md#r16), [R17](spec.md#r17).

**Zależności obowiązkowe:** [T060](#t060)

**Kolejność planowa:** T061; poprzednia karta: T060.

**Kontrakt / symbol:** `completed_selected_files`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `anishift/automation/intake.py`
- `tests/automation/test_qbit_completion.py`

**Istotna granica:** Możliwość odczytu pojedynczego kompletnego pliku paczki jest obowiązkowo testowana na wybranej wersji klienta.

#### Kolejność implementacji

1. Gotowość oceń dla konkretnego selected file: progress=1 oraz zgodność rozmiaru i dostępność bezpiecznej ścieżki.

2. Uwzględnij stan klienta moving/checking i nie rozpoczynaj kopii w trakcie przenosin lub weryfikacji tego źródła.

3. Odczytaj rzeczywisty save/content path z klienta, nie rekonstruuj go wyłącznie z nazwy torrenta.

4. Wymagaj stabilnego odczytu i przeprowadź kontrolowaną kopię przez intake, niezależnie od filesystem watchera.

5. Zapisz transfer/file_index jako origin i ustaw idempotency key, aby każdy ukończony plik został przyjęty raz.

6. Nie zatrzymuj całego torrenta ani seedowania po przyjęciu jednego pliku.

7. Po błędzie odczytu ponownie uzgodnij ścieżkę klienta; nie przyjmuj starej .part kopii.

8. Nie wprowadzaj streamingu niepełnego pliku jako skrótu do wcześniejszego TTS.

#### Scenariusze weryfikacji

<a id="t061-c01"></a>

##### T061-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Plik 1 ma progress=1, plik 2=0.3.

**Działanie:** Wykonaj tick.

**Oczekiwany rezultat:** Plik 1 trafia do intake i może rozpocząć Auto.

**Niedopuszczalny skutek:** Nie czeka na torrent.progress=1.

**Docelowy test:** `tests/automation/test_qbit_completion.py::test_qbit_completion_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t061-c02"></a>

##### T061-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Klient przenosi ukończony plik.

**Działanie:** Sprawdź gotowość.

**Oczekiwany rezultat:** Kopia czeka na zakończenie moving.

**Niedopuszczalny skutek:** Nie odczytuje nieaktualnej ścieżki.

**Docelowy test:** `tests/automation/test_qbit_completion.py::test_qbit_completion_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t061-c03"></a>

##### T061-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Progress=1, lecz plik nie istnieje pod raportowaną ścieżką.

**Działanie:** Przyjmij.

**Oczekiwany rezultat:** Stan jest oczekujący/błąd lokalizacji, nie ready.

**Niedopuszczalny skutek:** Nie oznaczono odcinka jako gotowy.

**Docelowy test:** `tests/automation/test_qbit_completion.py::test_qbit_completion_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t061-c04"></a>

##### T061-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Ta sama informacja completion wraca w kolejnych tickach.

**Działanie:** Przetwórz zdarzenia.

**Oczekiwany rezultat:** Istnieje jeden job dla transfer/file_index/profilu.

**Niedopuszczalny skutek:** Nie powtarza się TTS.

**Docelowy test:** `tests/automation/test_qbit_completion.py::test_qbit_completion_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_qbit_completion.py
```

**Wycofanie:** Wyłącz automatyczne przekazywanie pliku i pozostaw transfer klientowi; źródło nie jest ruszane ani usuwane.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21), [S24](research.md#s24).

<a id="t062"></a>

### T062. Steruj priorytetami pobierania i opcjonalnym limitem transferów

**Status:** planned.

**Cel:** Najbliższy odcinek do oglądania ma pierwszeństwo; liczbę równoległych transferów ogranicza klient albo opcjonalny limit użytkownika, a zapas i miejsce na dysku ogranicza polityka backlogu (T077, T085).

**Wymagania:** [R08](spec.md#r08), [R10](spec.md#r10), [R11](spec.md#r11), [R24](spec.md#r24).

**Zależności obowiązkowe:** [T061](#t061)

**Kolejność planowa:** T062; poprzednia karta: T061.

**Kontrakt / symbol:** `dispatch_download_slots`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `anishift/automation/worker.py`
- `tests/automation/test_download_priority.py`

**Istotna granica:** Wyższy priorytet to wskazówka klienta, nie obietnica szybszego transferu przy braku seedów.

#### Kolejność implementacji

1. Przy managed_active_transfers = 0 nie ograniczaj liczby aktywnych transferów; przy wartości > 0 nie przekraczaj jej. Kolejka i limity klienta pozostają nadrzędne.

2. Jawny wybór Oglądaj następny podnosi priorytet odcinka ponad zwykły backlog.

3. W obrębie własnej paczki przyznaj wyższy priorytet najbliższemu brakującemu epizodowi, jeżeli wspiera to klient.

4. Nie zakładaj, że tryb sequential gwarantuje ukończenie odcinków w wybranej kolejności; progres oceniaj per plik.

5. Nie zmieniaj globalnych limitów połączeń, seedowania i prędkości użytkownika.

6. Przed startem kolejnego transferu uwzględnij rezerwacje miejsca aktywnych kopii i wyników.

7. Stalled torrent zachowuje stan i może zwolnić slot zgodnie z jawną polityką, bez automatycznego kasowania.

8. Odtwarzanie już gotowego odcinka nie zależy od slotu pobierania.

#### Scenariusze weryfikacji

<a id="t062-c01"></a>

##### T062-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Trzy transfery gotowe do startu; raz z managed_active_transfers = 0, raz z wartością 2.

**Działanie:** Wykonaj dispatch w obu konfiguracjach.

**Oczekiwany rezultat:** Przy 0 startują wszystkie trzy; przy 2 trzeci czeka w kolejce AniShift.

**Niedopuszczalny skutek:** Nie przekroczono jawnie ustawionego limitu ani nie wprowadzono ukrytego limitu przy 0.

**Docelowy test:** `tests/automation/test_download_priority.py::test_download_priority_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t062-c02"></a>

##### T062-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik wybiera priorytet dla odcinka 4.

**Działanie:** Przelicz kolejkę.

**Oczekiwany rezultat:** Odcinek 4 ma pierwszeństwo wśród gotowych do startu.

**Niedopuszczalny skutek:** Nie zmieniono obcych torrentów.

**Docelowy test:** `tests/automation/test_download_priority.py::test_download_priority_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t062-c03"></a>

##### T062-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Transfer nie ma seedów.

**Działanie:** Oceń stalled.

**Oczekiwany rezultat:** Widoczny jest brak dostępności i przyszły retry.

**Niedopuszczalny skutek:** Nie ogłoszono pobrania ani nie usunięto plików.

**Docelowy test:** `tests/automation/test_download_priority.py::test_download_priority_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t062-c04"></a>

##### T062-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Pierwszy transfer kończy wybrane pliki.

**Działanie:** Wybierz kolejny.

**Oczekiwany rezultat:** Zwalnia się odpowiedni slot, a ukończone pliki nadal mogą seedować.

**Niedopuszczalny skutek:** Nie wymuszono usunięcia transferu dla zwolnienia kolejki.

**Docelowy test:** `tests/automation/test_download_priority.py::test_download_priority_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_download_priority.py
```

**Wycofanie:** Przywróć ustawienia priorytetów tylko własnych transferów; globalne preferencje klienta pozostają nietknięte.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21).

<a id="t063"></a>

### T063. Dodaj bezpieczne pauzowanie i anulowanie transferów

**Status:** planned.

**Cel:** Akcje pobierania działają wyłącznie na dokładnie wybranych własnych transferach i mają odrębną semantykę od jobów.

**Wymagania:** [R08](spec.md#r08), [R16](spec.md#r16), [R17](spec.md#r17), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T062](#t062)

**Kolejność planowa:** T063; poprzednia karta: T062.

**Kontrakt / symbol:** `pause_transfer / resume_transfer`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `anishift/automation/commands.py`
- `tests/automation/test_download_controls.py`

**Istotna granica:** Podstawowy plan nie zawiera automatycznego usuwania torrentów i ich danych.

#### Kolejność implementacji

1. Zmapuj pause/resume na wersjonowane metody stop/start lub wrappera zgodne z wykrytą wersją.

2. Każda mutacja wymaga konkretnego infohash i OWNED; nie stosuj hashes=all.

3. Cancel acquisition odznacza przyszły zamiar przygotowania; nie kasuje automatycznie danych klienta.

4. Dla paczki anulowanie jednego epizodu nie zatrzymuje innych wybranych epizodów.

5. Jawnie rozróżnij Zatrzymaj pobieranie, Anuluj przetwarzanie i Wyłącz subskrypcję.

6. Nie wywołuj deleteFiles=true w podstawowym workflow; usuwanie danych jest poza automatyczną retencją.

7. Po timeout mutacji odczytaj faktyczny stan i dopiero zdecyduj o ponowieniu.

8. Własny zatrzymany przez użytkownika torrent nie jest wznawiany co tick bez jawnej reguły resume.

#### Scenariusze weryfikacji

<a id="t063-c01"></a>

##### T063-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik pauzuje własny transfer.

**Działanie:** Zastosuj komendę.

**Oczekiwany rezultat:** Transfer pozostaje zatrzymany mimo kolejnych ticków.

**Niedopuszczalny skutek:** Nie odwrócono decyzji użytkownika automatycznie.

**Docelowy test:** `tests/automation/test_download_controls.py::test_download_controls_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t063-c02"></a>

##### T063-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Próba zatrzymania BORROWED.

**Działanie:** Zwaliduj ownership.

**Oczekiwany rezultat:** Operacja jest odrzucona lub kieruje do klienta.

**Niedopuszczalny skutek:** Nie zatrzymano prywatnego transferu.

**Docelowy test:** `tests/automation/test_download_controls.py::test_download_controls_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t063-c03"></a>

##### T063-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Anulowano epizod 3 z paczki 1–12.

**Działanie:** Przelicz wybór.

**Oczekiwany rezultat:** Pozostałe zaakceptowane epizody zachowują pracę.

**Niedopuszczalny skutek:** Nie zatrzymano całej paczki bez potrzeby.

**Docelowy test:** `tests/automation/test_download_controls.py::test_download_controls_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t063-c04"></a>

##### T063-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Odpowiedź pause została utracona.

**Działanie:** Uzgodnij stan.

**Oczekiwany rezultat:** UI odzwierciedla realny stop/start klienta.

**Niedopuszczalny skutek:** Nie przedstawiono samego requestu jako dowodu pauzy.

**Docelowy test:** `tests/automation/test_download_controls.py::test_download_controls_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_download_controls.py
```

**Wycofanie:** Wyłącz automatyczne mutacje; stan klienta zostaw do ręcznej kontroli zamiast odwracać wszystkie pauzy.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21).

<a id="t064"></a>

### T064. Odróżnij awarię klienta od niedostępnego wydania

**Status:** planned.

**Cel:** Kolejka pokazuje, czy czeka na seedów, sieć, uruchomienie klienta czy poprawną konfigurację.

**Wymagania:** [R14](spec.md#r14), [R23](spec.md#r23), [R24](spec.md#r24), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T063](#t063)

**Kolejność planowa:** T064; poprzednia karta: T063.

**Kontrakt / symbol:** `TransferHealthSnapshot`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `anishift/automation/progress.py`
- `tests/automation/test_download_health.py`

**Istotna granica:** Stan klienta jest źródłem prawdy dla transferu, filesystem watcher nie pełni funkcji jego zamiennika.

#### Kolejność implementacji

1. Mapuj missingFiles, error, stalled, checking, moving i disconnected na bezpieczne stany prezentacyjne.

2. Zapisuj last_successful_poll i nie zmieniaj ostatniego potwierdzonego transferu na gotowy po błędzie odczytu.

3. Po utracie klienta utrzymaj już przyjęte lokalne joby i gotową bibliotekę.

4. Stosuj backoff przy kolejnych connection refused; nie odpytuj martwego portu co klatkę.

5. Po restarcie klienta ponownie negocjuj wersję i capabilities przed mutacjami.

6. Zmiana ścieżki w klientcie wymaga ponownej weryfikacji containment i stabilności źródła.

7. Pokaż jedną grupową uwagę o połączeniu, zamiast identycznego alertu dla 200 odcinków.

8. Udostępnij akcję Sprawdź połączenie, która nie pobiera ani nie kasuje żadnego pliku.

#### Scenariusze weryfikacji

<a id="t064-c01"></a>

##### T064-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** qBittorrent został zamknięty.

**Działanie:** Wykonaj polling.

**Oczekiwany rezultat:** UI pokazuje klient niedostępny z wiekiem danych.

**Niedopuszczalny skutek:** Nie oznaczono wszystkich epizodów jako nieistniejące.

**Docelowy test:** `tests/automation/test_download_health.py::test_download_health_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t064-c02"></a>

##### T064-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Transfer stalled z zerową prędkością.

**Działanie:** Pokaż postęp.

**Oczekiwany rezultat:** Widać oczekiwanie na źródła, nie błąd tłumacza.

**Niedopuszczalny skutek:** Nie wyliczono fałszywego czasu zakończenia.

**Docelowy test:** `tests/automation/test_download_health.py::test_download_health_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t064-c03"></a>

##### T064-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Klient wskazuje nową ścieżkę poza dozwoloną własnością.

**Działanie:** Uzgodnij plik.

**Oczekiwany rezultat:** Kopia jest wstrzymana do walidacji.

**Niedopuszczalny skutek:** Nie odczytano dowolnej ścieżki zwróconej przez sieć.

**Docelowy test:** `tests/automation/test_download_health.py::test_download_health_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t064-c04"></a>

##### T064-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Klient wrócił po aktualizacji.

**Działanie:** Ponów połączenie.

**Oczekiwany rezultat:** Capabilities są sprawdzone ponownie.

**Niedopuszczalny skutek:** Nie użyto bezwarunkowo starych metod API.

**Docelowy test:** `tests/automation/test_download_health.py::test_download_health_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_download_health.py
```

**Wycofanie:** Przejdź do trybu wyłącznie lokalnego przetwarzania; zachowaj transfer records do późniejszego uzgodnienia.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21), [S22](research.md#s22).

<a id="p08"></a>

## P08. Paczki sezonów, pliki i nieoczywista numeracja

**Wynik fazy:** Sezon/paczka i nietypowa numeracja są obsługiwane.

**Wejście:** P07: manifest i priorytety; P04: pojedynczy job.

**Warunek wyjścia:** Pierwszy kompletny plik jest odtwarzalny przed końcem paczki; 7.5/v2/OVA nie giną w mapowaniu.

**Status fazy:** planned.

<a id="t065"></a>

### T065. Zbuduj manifest paczki przed startem danych

**Status:** planned.

**Cel:** Paczka sezonu jest listą konkretnych plików i epizodów, a nie pojedynczym nieprzejrzystym przyciskiem Pobierz wszystko.

**Wymagania:** [R08](spec.md#r08), [R11](spec.md#r11), [R19](spec.md#r19), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T064](#t064), [T040](#t040)

**Kolejność planowa:** T065; poprzednia karta: T064.

**Kontrakt / symbol:** `BatchManifest`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `anishift/automation/download.py`
- `tests/automation/test_batch_manifest.py`

**Istotna granica:** Rozmiar zaznaczonych plików nie jest ścisłą gwarancją liczby bajtów transmisji BitTorrent.

#### Kolejność implementacji

1. Po metadata-only utwórz BatchManifest z file_index, ścieżką, rozmiarem, typem i proponowanym EpisodeKey każdego pliku.

2. Oddziel filmy główne, sidecary, dodatki, próbki i nieobsługiwane pliki.

3. Odziedzicz jakość z tytułu paczki tylko jako deklarację; oznacz jej pochodzenie i późniejszą potrzebę probe.

4. Zachowaj oryginalną strukturę klienta, a docelową bibliotekę oblicz oddzielnie dla każdego epizodu.

5. Zapisz wersję manifestu i digest listy plików, aby wybór z UI nie odnosił się do zmienionej listy.

6. Wynik częściowego parsera nie może domyślnie zaznaczać nieznanych plików.

7. Pokazuj sumę rozmiarów wybranych plików i ostrzeżenie, że protokół może pobrać dodatkowe bajty współdzielonych pieces.

8. Zapis zaakceptowanego manifestu jest atomowy przed zmianą priorytetów w kliencie.

#### Scenariusze weryfikacji

<a id="t065-c01"></a>

##### T065-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Paczka ma 12 MKV i 3 próbki.

**Działanie:** Zbuduj manifest.

**Oczekiwany rezultat:** Główne filmy i próbki są odrębnie oznaczone.

**Niedopuszczalny skutek:** Nie zaznaczono wszystkiego po samym rozszerzeniu.

**Docelowy test:** `tests/automation/test_batch_manifest.py::test_batch_manifest_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t065-c02"></a>

##### T065-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nazwy plików są ubogie, paczka deklaruje 1080p.

**Działanie:** Oceń jakość.

**Oczekiwany rezultat:** Widoczna jest deklaracja z paczki i późniejsza walidacja.

**Niedopuszczalny skutek:** Nie udawano odczytu rozdzielczości z mediów przed pobraniem.

**Docelowy test:** `tests/automation/test_batch_manifest.py::test_batch_manifest_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t065-c03"></a>

##### T065-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Manifest zmienił się po otwarciu podglądu.

**Działanie:** Zatwierdź stary wybór.

**Oczekiwany rezultat:** Wymagane jest odświeżenie wyboru.

**Niedopuszczalny skutek:** Nie użyto dawnych indeksów do nowej listy.

**Docelowy test:** `tests/automation/test_batch_manifest.py::test_batch_manifest_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t065-c04"></a>

##### T065-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Proces ginie po zapisie manifestu.

**Działanie:** Wznów.

**Oczekiwany rezultat:** Wybór jest odtworzony przed wznowieniem danych.

**Niedopuszczalny skutek:** Nie włączono całej paczki domyślnie.

**Docelowy test:** `tests/automation/test_batch_manifest.py::test_batch_manifest_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_batch_manifest.py
```

**Wycofanie:** Pozostaw torrent zatrzymany i zachowaj manifest do ponownej oceny; nie kasuj jego metadanych lub źródeł.

**Podstawa techniczna:** [S20](research.md#s20), [S21](research.md#s21), [S30](research.md#s30).

<a id="t066"></a>

### T066. Zapisz jawne mapowanie numeracji sezonowej i absolutnej

**Status:** planned.

**Cel:** Odcinek 13 w nazwie wydania nie staje się automatycznie odcinkiem 13 nowego dwunastoodcinkowego sezonu.

**Wymagania:** [R04](spec.md#r04), [R09](spec.md#r09), [R19](spec.md#r19), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T065](#t065)

**Kolejność planowa:** T066; poprzednia karta: T065.

**Kontrakt / symbol:** `NumberingRule.map`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `anishift/automation/models.py`
- `tests/automation/test_number_mapping.py`

**Istotna granica:** Numeracja jest własnością profilu serii/grupy, nie globalnego parsera.

#### Kolejność implementacji

1. Zdefiniuj NumberingRule: seasonal, absolute_offset oraz explicit_map.

2. Przy absolute_offset zapisuj sprawdzony offset jako różnicę numeru wydania i numeru lokalnego epizodu.

3. Przed zatwierdzeniem pokaż co najmniej dwa przykłady mapowania z realnych nazw wybranej serii.

4. Nigdy nie wyznaczaj offsetu tylko z liczby odcinków poprzedniego sezonu lub daty premiery.

5. Odrzuć mapowanie dające numery niedodatnie albo kolizje, których nie opisano jako multi-episode file.

6. Zmiana numbering rule dotyczy nowych decyzji; istniejące potwierdzone joby wymagają osobnej operacji naprawy.

7. W release decision stosuj tę samą regułę dla pojedynczego odcinka i pliku w paczce.

8. Pokaż użytkownikowi oba numery: numer z wydania oraz numer w bibliotece.

#### Scenariusze weryfikacji

<a id="t066-c01"></a>

##### T066-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nowy sezon jest wydawany jako 13–24, offset=12.

**Działanie:** Mapuj 13 i 24.

**Oczekiwany rezultat:** Powstają lokalne odcinki 1 i 12.

**Niedopuszczalny skutek:** Nie zachowano przypadkowo numeru 24 jako epizodu dwunastoodcinkowej serii.

**Docelowy test:** `tests/automation/test_number_mapping.py::test_number_mapping_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t066-c02"></a>

##### T066-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nie ma potwierdzonego offsetu.

**Działanie:** Znajdź wydanie 13.

**Oczekiwany rezultat:** Wynik wymaga mapowania.

**Niedopuszczalny skutek:** Nie obliczono offsetu z niepełnego katalogu.

**Docelowy test:** `tests/automation/test_number_mapping.py::test_number_mapping_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t066-c03"></a>

##### T066-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Dwa pliki mapują się na ten sam epizod.

**Działanie:** Zwaliduj manifest.

**Oczekiwany rezultat:** Pojawia się konflikt wersji/wyboru.

**Niedopuszczalny skutek:** Nie nadpisano pierwszego źródła drugim.

**Docelowy test:** `tests/automation/test_number_mapping.py::test_number_mapping_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t066-c04"></a>

##### T066-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Regułę poprawiono po błędnej propozycji.

**Działanie:** Przeanalizuj nowe wydania.

**Oczekiwany rezultat:** Nowe decyzje używają poprawnej wersji reguły.

**Niedopuszczalny skutek:** Nie przepisywano historii gotowych jobów bez potwierdzenia.

**Docelowy test:** `tests/automation/test_number_mapping.py::test_number_mapping_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_number_mapping.py
```

**Wycofanie:** Przywróć poprzednią regułę dla przyszłych wydań; błędne przypisania naprawiaj oddzielnym, odwracalnym mapowaniem.

**Podstawa techniczna:** [S17](research.md#s17), [S30](research.md#s30).

<a id="t067"></a>

### T067. Obsłuż numery ułamkowe i materiały dodatkowe

**Status:** planned.

**Cel:** Odcinek 7.5, OVA i SPECIAL nie znikają pomiędzy zwykłymi epizodami ani nie zawyżają postępu MAL.

**Wymagania:** [R04](spec.md#r04), [R19](spec.md#r19), [R21](spec.md#r21), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T066](#t066)

**Kolejność planowa:** T067; poprzednia karta: T066.

**Kontrakt / symbol:** `map_special_episode`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `tests/automation/test_special_numbers.py`

**Istotna granica:** Celem jest niegubienie znanych dodatków, nie niemożliwa gwarancja katalogowania całej franczyzy.

#### Kolejność implementacji

1. Zachowaj Decimal number dla 7.5 i innych jawnie liczbowych etykiet.

2. Nie wnioskuj automatycznie, że każdy odcinek ułamkowy jest recapem lub materiałem nieistotnym.

3. Dla etykiet OVA/ONA/SPECIAL przypisz właściwy kind dopiero po zgodności z wybranym media lub ręcznym mapowaniu.

4. Pozwól użytkownikowi wyłączyć recapy/dodatki jawnie, z zapisem przyczyny pominięcia.

5. Pokaż dodatki w oddzielnej sekcji harmonogramu i biblioteki, nadal powiązanej z serią.

6. Zachowaj stan watched każdego dodatku niezależnie od licznika regularnych odcinków.

7. Nie dodawaj brakującego 7.5 tylko dlatego, że istnieją 7 i 8; oczekiwane epizody wynikają z danych lub wyboru.

8. Brak informacji o dodatkach opisuj jako niepełną wiedzę, nie jako zapewnienie kompletności.

#### Scenariusze weryfikacji

<a id="t067-c01"></a>

##### T067-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Wydanie nosi numer 7.5.

**Działanie:** Zapisz epizod.

**Oczekiwany rezultat:** Wartość i pozycja sortowania są zachowane.

**Niedopuszczalny skutek:** Nie zaokrąglono do 8.

**Docelowy test:** `tests/automation/test_special_numbers.py::test_special_numbers_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t067-c02"></a>

##### T067-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Paczka zawiera OVA 01 i TV 01.

**Działanie:** Zbuduj bibliotekę.

**Oczekiwany rezultat:** To dwa różne epizody i katalogi typu.

**Niedopuszczalny skutek:** Nie połączono ich pod jednym numerem.

**Docelowy test:** `tests/automation/test_special_numbers.py::test_special_numbers_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t067-c03"></a>

##### T067-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Katalog nie wymienia specials.

**Działanie:** Pokaż kompletność.

**Oczekiwany rezultat:** UI nie gwarantuje posiadania wszystkich dodatków.

**Niedopuszczalny skutek:** Nie wymyślono brakujących epizodów.

**Docelowy test:** `tests/automation/test_special_numbers.py::test_special_numbers_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t067-c04"></a>

##### T067-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik oznacza 7.5 jako obejrzany.

**Działanie:** Zapisz postęp.

**Oczekiwany rezultat:** Zmienia się tylko ten epizod.

**Niedopuszczalny skutek:** Nie zwiększono automatycznie licznika regularnych odcinków.

**Docelowy test:** `tests/automation/test_special_numbers.py::test_special_numbers_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_special_numbers.py
```

**Wycofanie:** Cofnij świadome mapowanie dodatku, zachowując sam plik i jego stan oglądania jako nieprzypisany.

**Podstawa techniczna:** [S17](research.md#s17), [S30](research.md#s30).

<a id="t068"></a>

### T068. Obsłuż jeden plik zawierający kilka odcinków

**Status:** planned.

**Cel:** Zakres 01–02 w jednym MKV nie może powodować dwukrotnego TTS tego samego pliku ani udawanego cięcia filmu.

**Wymagania:** [R08](spec.md#r08), [R11](spec.md#r11), [R19](spec.md#r19), [R21](spec.md#r21).

**Zależności obowiązkowe:** [T067](#t067)

**Kolejność planowa:** T068; poprzednia karta: T067.

**Kontrakt / symbol:** `EpisodeCoverage / job_episodes`.

#### Pliki i zakres edycji

- `anishift/automation/models.py`
- `anishift/automation/releases.py`
- `tests/automation/test_multi_episode.py`

**Istotna granica:** Wspólne fizyczne źródło nie wymaga uniwersalnego edytora wideo.

#### Kolejność implementacji

1. Dodaj coverage jako zbiór EpisodeKey przypisany do jednego source joba, zapisany przez job_episodes.

2. Rozróżnij pack z wieloma plikami od pojedynczego multi-episode file.

3. Pokaż w podglądzie, że wybór jednego numeru wymaga pobrania całego wspólnego pliku.

4. Przetwarzaj fizyczny plik raz i przypisz ten sam playable artifact do wszystkich epizodów coverage.

5. Nie dziel automatycznie wideo lub napisów bez wiarygodnych granic rozdziałów; cięcie jest poza zakresem.

6. Oznaczenie obejrzenia wymaga jawnego wyboru jednego numeru lub całego zakresu, nie samego końca procesu playera.

7. Unikaj podwójnego liczenia zajętego miejsca tego samego artifact w bibliotece.

8. Przy niejednoznacznym zakresie nazw pokaż needs_mapping przed uruchomieniem.

#### Scenariusze weryfikacji

<a id="t068-c01"></a>

##### T068-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Jeden MKV obejmuje 01–02.

**Działanie:** Przetwórz źródło.

**Oczekiwany rezultat:** Powstaje jeden job i wspólny produkt dla dwóch EpisodeKey.

**Niedopuszczalny skutek:** Nie wykonano TTS dwa razy.

**Docelowy test:** `tests/automation/test_multi_episode.py::test_multi_episode_file_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t068-c02"></a>

##### T068-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik zaznaczył tylko epizod 1.

**Działanie:** Pokaż podgląd.

**Oczekiwany rezultat:** Widoczne jest pobranie wspólnego pliku 1–2.

**Niedopuszczalny skutek:** Nie obiecano pobrania połowy MKV.

**Docelowy test:** `tests/automation/test_multi_episode.py::test_multi_episode_file_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t068-c03"></a>

##### T068-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zakres jest nieczytelny lub sprzeczny.

**Działanie:** Zwaliduj.

**Oczekiwany rezultat:** Potrzebny jest wybór coverage.

**Niedopuszczalny skutek:** Nie zgadnięto liczby epizodów z rozmiaru pliku.

**Docelowy test:** `tests/automation/test_multi_episode.py::test_multi_episode_file_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t068-c04"></a>

##### T068-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Epizod 1 oznaczono jako obejrzany, 2 nie.

**Działanie:** Odczytaj historię.

**Oczekiwany rezultat:** Stan oglądania pozostaje różny mimo wspólnego pliku.

**Niedopuszczalny skutek:** Nie scalono watch state przez wspólne artifact_id.

**Docelowy test:** `tests/automation/test_multi_episode.py::test_multi_episode_file_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_multi_episode.py
```

**Wycofanie:** Zachowaj fizyczny plik i produkt; zmień wyłącznie mapowanie coverage po jawnym potwierdzeniu.

**Podstawa techniczna:** [S06](research.md#s06), [S20](research.md#s20), [S30](research.md#s30).

<a id="t069"></a>

### T069. Wyklucz próbki i nieobsługiwane pliki bez gubienia dodatków

**Status:** planned.

**Cel:** Domysły parsera nie mogą pobrać programu instalacyjnego ani usunąć prawdziwego odcinka specjalnego.

**Wymagania:** [R08](spec.md#r08), [R19](spec.md#r19), [R24](spec.md#r24), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T068](#t068)

**Kolejność planowa:** T069; poprzednia karta: T068.

**Kontrakt / symbol:** `classify_batch_file`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `tests/automation/test_batch_exclusions.py`

**Istotna granica:** Dodatki mają być widoczne, nie automatycznie pobrane i nie bezpowrotnie odrzucone.

#### Kolejność implementacji

1. Akceptuj główne źródła .mkv i .mp4 oraz jawnie związane .srt/.ass; pozostałe wymagają osobnej świadomej decyzji lub są odrzucane.

2. Oznacz sample, trailer, NCOP, NCED, OP i ED jako dodatki niewybrane domyślnie, z możliwością obejrzenia listy.

3. Nie uznawaj samego krótkiego czasu lub małego rozmiaru za dowód, że materiał jest próbką.

4. Pliki exe, bat, cmd, ps1, js, skróty i archiwa nie są wykonywane ani automatycznie rozpakowywane.

5. Przy kilku kodowaniach tego samego odcinka wybierz jedno zgodnie z jakością i preferencjami, resztę pokaż jako alternatywy.

6. Pliki sidecar łącz po stem i języku, nigdy po przypadkowej kolejności w katalogu.

7. Zapisz exclusion_reason w manifeście dla każdego wyłączonego pliku.

8. Podgląd umożliwia świadome włączenie prawdziwej OVA/SPECIAL, ale nie omija ochrony przed wykonywalnym plikiem.

#### Scenariusze weryfikacji

<a id="t069-c01"></a>

##### T069-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Paczka ma sample.mkv i OVA-01.mkv.

**Działanie:** Zbuduj wybór.

**Oczekiwany rezultat:** Sample jest odznaczone, OVA pokazana jako świadomy dodatek.

**Niedopuszczalny skutek:** Nie ukryto OVA jako próbki na podstawie długości.

**Docelowy test:** `tests/automation/test_batch_exclusions.py::test_batch_exclusions_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t069-c02"></a>

##### T069-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Plik MKV ma nazwę zawierającą słowo Opening w tytule serii.

**Działanie:** Parsuj.

**Oczekiwany rezultat:** Nie jest wykluczony przez luźne dopasowanie podciągu.

**Niedopuszczalny skutek:** Nie zastosowano nieograniczonego regex OP.

**Docelowy test:** `tests/automation/test_batch_exclusions.py::test_batch_exclusions_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t069-c03"></a>

##### T069-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Paczka zawiera install.cmd.

**Działanie:** Przygotuj priorytety.

**Oczekiwany rezultat:** Plik nie jest pobierany/uruchamiany przez workflow.

**Niedopuszczalny skutek:** Nie wywołano powłoki po pobraniu.

**Docelowy test:** `tests/automation/test_batch_exclusions.py::test_batch_exclusions_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t069-c04"></a>

##### T069-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik włącza konkretny SPECIAL.

**Działanie:** Zapisz manifest.

**Oczekiwany rezultat:** Wybrany jest dokładny file_index i EpisodeKey.

**Niedopuszczalny skutek:** Nie włączono wszystkich odznaczonych dodatków.

**Docelowy test:** `tests/automation/test_batch_exclusions.py::test_batch_exclusions_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_batch_exclusions.py
```

**Wycofanie:** Zmiana wykluczeń dotyczy przyszłego pobierania; niczego nie kasuje z już posiadanej biblioteki.

**Podstawa techniczna:** [S20](research.md#s20), [S25](research.md#s25), [S30](research.md#s30).

<a id="t070"></a>

### T070. Przekazuj ukończone pliki paczki niezależnie

**Status:** planned.

**Cel:** Paczka nie jest barierą synchronizacji dla tłumaczenia i oglądania pierwszego odcinka.

**Wymagania:** [R08](spec.md#r08), [R11](spec.md#r11), [R17](spec.md#r17), [R24](spec.md#r24).

**Zależności obowiązkowe:** [T069](#t069)

**Kolejność planowa:** T070; poprzednia karta: T069.

**Kontrakt / symbol:** `dispatch_completed_files`.

#### Pliki i zakres edycji

- `anishift/automation/download.py`
- `anishift/automation/worker.py`
- `tests/automation/test_batch_dispatch.py`

**Istotna granica:** Jednostką przetwarzania jest kompletny fizyczny plik, nie całe wydanie batch.

#### Kolejność implementacji

1. W każdym poll przejrzyj tylko wybrane file_index i znajdź nowe kompletne pliki.

2. Dla każdego pliku wywołaj wspólny intake z własnym idempotency key i coverage.

3. Nie twórz jednego wielkiego AppService run obejmującego cały katalog pobierania.

4. Gotowe pliki ustawiaj w kolejności epizodów lub zgodnie z jawnym priorytetem oglądania.

5. Jeśli epizod 2 jest kompletny, a 1 nie, możesz przetworzyć 2, ale UI nadal pokazuje brak 1.

6. Nie blokuj kolejki lokalnej na pliku, który nadal się pobiera i nie zajmuje jeszcze zasobów rdzenia.

7. Po ready każdego joba odśwież bibliotekę natychmiast; licznik całej paczki jest tylko dodatkowym podsumowaniem.

8. Ponowne poll i restart nie mogą tworzyć drugiego przyjęcia tego samego pliku.

#### Scenariusze weryfikacji

<a id="t070-c01"></a>

##### T070-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Paczka 12 plików: tylko pierwszy gotowy.

**Działanie:** Wykonaj dispatch.

**Oczekiwany rezultat:** Pierwszy trafia do Auto, reszta pozostaje w download.

**Niedopuszczalny skutek:** Nie czekano na komplet paczki.

**Docelowy test:** `tests/automation/test_batch_dispatch.py::test_batch_dispatch_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t070-c02"></a>

##### T070-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Epizod 2 gotowy przed 1.

**Działanie:** Wykonaj dispatch.

**Oczekiwany rezultat:** Może powstać gotowa 2 z widoczną luką 1.

**Niedopuszczalny skutek:** Nie oznaczono następnego do zdobycia jako 3.

**Docelowy test:** `tests/automation/test_batch_dispatch.py::test_batch_dispatch_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t070-c03"></a>

##### T070-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Jeden plik jest uszkodzony po pobraniu.

**Działanie:** Przetwórz pozostałe.

**Oczekiwany rezultat:** Niezależne epizody nadal przechodzą.

**Niedopuszczalny skutek:** Nie odrzucono całego sezonu.

**Docelowy test:** `tests/automation/test_batch_dispatch.py::test_batch_dispatch_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t070-c04"></a>

##### T070-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Restart między copy a queued jednego pliku.

**Działanie:** Uzgodnij manifest.

**Oczekiwany rezultat:** Ten plik jest odzyskany raz, pozostałe zachowują stany.

**Niedopuszczalny skutek:** Nie kopiowano całej paczki od początku.

**Docelowy test:** `tests/automation/test_batch_dispatch.py::test_batch_dispatch_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_batch_dispatch.py
```

**Wycofanie:** Zatrzymaj przyjmowanie nowych plików paczki, pozostawiając już wykonywane joby i klienta torrent bez destrukcyjnych operacji.

**Podstawa techniczna:** [S03](research.md#s03), [S06](research.md#s06), [S20](research.md#s20).

<a id="t071"></a>

### T071. Obsłuż v2 i lepsze wydanie jako nową rewizję

**Status:** planned.

**Cel:** Późniejsze poprawione napisy lub lepsza grupa nie nadpisują po cichu gotowego odcinka.

**Wymagania:** [R06](spec.md#r06), [R16](spec.md#r16), [R17](spec.md#r17), [R19](spec.md#r19), [R21](spec.md#r21).

**Zależności obowiązkowe:** [T070](#t070)

**Kolejność planowa:** T071; poprzednia karta: T070.

**Kontrakt / symbol:** `propose_revision / activate_revision`.

#### Pliki i zakres edycji

- `anishift/automation/releases.py`
- `anishift/automation/library.py`
- `tests/automation/test_release_versions.py`

**Istotna granica:** v2 to wersja wydania, nie epizod 2.

#### Kolejność implementacji

1. Zapisz release_version i source_digest jako cechy konkretnego źródła, nie numer odcinka.

2. Dla epizodu ready nowe wydanie pokaż jako opcjonalną aktualizację.

3. Dla epizodu failed/attention pozwól zaproponować nowsze zgodne wydanie, bez kasowania starego źródła.

4. Nowa wersja tworzy nowy RevisionId i osobny katalog docelowy.

5. Aktywną rewizję przełącz dopiero po walidacji nowego playable produktu albo jawnej decyzji użytkownika.

6. Historia watched pozostaje przypisana do EpisodeKey, nie jest zerowana zmianą kodowania.

7. Nie przenoś gotowego pliku aktualnie otwartego przez mpv; nowa rewizja ma odrębną ścieżkę.

8. Usunięcie starych rewizji jest osobną świadomą operacją, poza automatycznym pipeline.

#### Scenariusze weryfikacji

<a id="t071-c01"></a>

##### T071-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Epizod ready ma dostępne v2.

**Działanie:** Odśwież wydania.

**Oczekiwany rezultat:** UI pokazuje aktualizację bez automatycznego download.

**Niedopuszczalny skutek:** Nie nadpisano v1.

**Docelowy test:** `tests/automation/test_release_versions.py::test_release_versions_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t071-c02"></a>

##### T071-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** v1 nie miało pełnych napisów, v2 je deklaruje.

**Działanie:** Zaproponuj retry ze źródłem.

**Oczekiwany rezultat:** Powstaje nowa rewizja po akceptacji.

**Niedopuszczalny skutek:** Nie zamieniono starego source_digest w miejscu.

**Docelowy test:** `tests/automation/test_release_versions.py::test_release_versions_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t071-c03"></a>

##### T071-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nowa rewizja kończy się błędem.

**Działanie:** Odczytaj bibliotekę.

**Oczekiwany rezultat:** Poprzednia gotowa rewizja nadal jest odtwarzalna.

**Niedopuszczalny skutek:** Nie stracono jedynego dobrego produktu.

**Docelowy test:** `tests/automation/test_release_versions.py::test_release_versions_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t071-c04"></a>

##### T071-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Obejrzany epizod dostaje lepszy encode.

**Działanie:** Przełącz aktywną rewizję.

**Oczekiwany rezultat:** Watched state zostaje zachowany.

**Niedopuszczalny skutek:** Nie zwiększono ani nie wyzerowano licznika oglądania.

**Docelowy test:** `tests/automation/test_release_versions.py::test_release_versions_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_release_versions.py
```

**Wycofanie:** Wróć do poprzedniego active_revision_id; nie usuwaj żadnego pliku podczas samego przełączania.

**Podstawa techniczna:** [S06](research.md#s06), [S30](research.md#s30).

<a id="t072"></a>

### T072. Pokaż kompletność sezonu bez fałszywych zapewnień

**Status:** planned.

**Cel:** Właściciel widzi, które odcinki ma, które są gotowe i które mogą nadal brakować.

**Wymagania:** [R10](spec.md#r10), [R11](spec.md#r11), [R19](spec.md#r19), [R21](spec.md#r21), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T071](#t071)

**Kolejność planowa:** T072; poprzednia karta: T071.

**Kontrakt / symbol:** `SeasonCompleteness`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `tests/automation/test_batch_summary.py`

**Istotna granica:** Nie zakładamy, że każdy sezon ma 12 odcinków albo że wszystkie dodatki występują w jednej paczce.

#### Kolejność implementacji

1. Porównuj znany oczekiwany zbiór epizodów z dostępnymi źródłami i gotowymi produktami.

2. Wyświetl osobno znalezione, pobrane, gotowe, obejrzane oraz wymagające mapowania.

3. Nie licz plików jako odcinków przy multi-episode coverage lub wielu rewizjach.

4. Dla nieznanej liczby odcinków użyj komunikatu Kompletny względem znanych wydań, a nie Cały sezon na pewno gotowy.

5. Znane specials pokaż oddzielnie od regularnego licznika sezonu.

6. Braki liczbowe w środku zakresu pozostają widoczne nawet przy obecności odcinka o najwyższym numerze.

7. Przy partial search zaznacz, że wyszukiwanie historyczne jeszcze nie potwierdziło całego zakresu.

8. Podsumowanie sezonu nie może blokować Oglądaj dla niezależnie gotowych epizodów.

#### Scenariusze weryfikacji

<a id="t072-c01"></a>

##### T072-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Gotowe są 1, 2, 4 i 12.

**Działanie:** Podsumuj serię.

**Oczekiwany rezultat:** Widoczne są luki 3 i dalsze znane brakujące numery.

**Niedopuszczalny skutek:** Nie uznano last=12 za komplet sezonu.

**Docelowy test:** `tests/automation/test_batch_summary.py::test_batch_summary_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t072-c02"></a>

##### T072-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Jeden plik pokrywa 1–2 i istnieje druga rewizja.

**Działanie:** Policz epizody.

**Oczekiwany rezultat:** Liczba odcinków to dwa, nie liczba plików/revizji.

**Niedopuszczalny skutek:** Nie podwojono postępu.

**Docelowy test:** `tests/automation/test_batch_summary.py::test_batch_summary_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t072-c03"></a>

##### T072-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Liczba odcinków w katalogu jest nieznana.

**Działanie:** Pokaż stan.

**Oczekiwany rezultat:** Nie pada gwarancja kompletności sezonu.

**Niedopuszczalny skutek:** Nie przyjęto arbitralnego 12 jako całości.

**Docelowy test:** `tests/automation/test_batch_summary.py::test_batch_summary_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t072-c04"></a>

##### T072-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Historyczne wyszukiwanie zostało wznowione.

**Działanie:** Aktualizuj podsumowanie.

**Oczekiwany rezultat:** Nowe dowody uzupełniają braki bez resetowania ready.

**Niedopuszczalny skutek:** Nie zablokowano odtwarzania podczas szukania.

**Docelowy test:** `tests/automation/test_batch_summary.py::test_batch_summary_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_batch_summary.py
```

**Wycofanie:** Wyłącz tylko nowe podsumowanie, pozostawiając szczegółowe rekordy odcinków dostępne do odczytu.

**Podstawa techniczna:** [S17](research.md#s17), [S20](research.md#s20), [S24](research.md#s24).

<a id="p09"></a>

## P09. Subskrypcje, harmonogram i nadrabianie zaległości

**Wynik fazy:** Wybrana raz seria jest pozyskiwana bez cotygodniowego klikania.

**Wejście:** P05–P08: katalog, wydania i download.

**Warunek wyjścia:** Terminy, missing set, catch-up, backlog i limit dysku tworzą jedną spójną politykę.

**Status fazy:** planned.

<a id="t073"></a>

### T073. Zapisz subskrypcję z pełną regułą przyjęcia

**Status:** planned.

**Cel:** Jednorazowy wybór serii wystarcza do dalszego lokalnego nadzoru nad nowymi odcinkami.

**Wymagania:** [R04](spec.md#r04), [R06](spec.md#r06), [R09](spec.md#r09), [R10](spec.md#r10), [R18](spec.md#r18).

**Zależności obowiązkowe:** [T072](#t072), [T048](#t048), [T024](#t024)

**Kolejność planowa:** T073; poprzednia karta: T072.

**Kontrakt / symbol:** `SubscriptionService.subscribe`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `anishift/automation/commands.py`
- `tests/automation/test_subscribe.py`

**Istotna granica:** Przyszłe automatyczne czynności są ograniczone zapisaną zgodą i regułą, nie dowolnym wynikiem search.

#### Kolejność implementacji

1. Zapisz SeriesId, aliasy wyszukiwania, profile_id, numbering_rule, group_policy oraz minimum jakości.

2. Wybierz tryb ongoing, backlog albo future_collect; każdy ma jawny zakres epizodów i priorytet.

3. Zapisz start episode jako następny do zdobycia, a nie automatycznie ostatni obejrzany plus jeden.

4. Przed włączeniem pokaż przykład pasującego wydania i skutki zapisanej reguły.

5. Wprowadź enabled, paused, next_check_at oraz last_successful_check_at jako niezależne pola.

6. Powtórne potwierdzenie tej samej subskrypcji aktualizuje istniejący rekord, nie tworzy drugiego schedulera.

7. Nie subskrybuj całej listy MAL ani wszystkich tytułów sezonu bez świadomego zaznaczenia.

8. Pierwsze sprawdzenie może ruszyć od razu po commit; nie wymaga ponownego wejścia do Auto.

#### Scenariusze weryfikacji

<a id="t073-c01"></a>

##### T073-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wybrano ongoing i potwierdzono regułę.

**Działanie:** Zapisz subskrypcję.

**Oczekiwany rezultat:** Powstaje jeden aktywny rekord z terminem pierwszego sprawdzenia.

**Niedopuszczalny skutek:** Nie wymaga ręcznego uruchomienia Auto co tydzień.

**Docelowy test:** `tests/automation/test_subscribe.py::test_subscribe_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t073-c02"></a>

##### T073-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Ten sam wybór zatwierdzono dwa razy.

**Działanie:** Zapisz komendę.

**Oczekiwany rezultat:** Subskrypcja nie dubluje się.

**Niedopuszczalny skutek:** Nie powstały dwa harmonogramy tej samej serii.

**Docelowy test:** `tests/automation/test_subscribe.py::test_subscribe_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t073-c03"></a>

##### T073-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Brak jasnej numbering_rule.

**Działanie:** Włącz automatyczne pobieranie.

**Oczekiwany rezultat:** Potrzebne jest konkretne mapowanie.

**Niedopuszczalny skutek:** Nie zgadnięto numeru kolejnego sezonu.

**Docelowy test:** `tests/automation/test_subscribe.py::test_subscribe_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t073-c04"></a>

##### T073-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Worker uruchomiono ponownie.

**Działanie:** Wczytaj subskrypcję.

**Oczekiwany rezultat:** Zachowuje zakres, grupy i następny termin.

**Niedopuszczalny skutek:** Nie wraca do domyślnego pobierania całej serii.

**Docelowy test:** `tests/automation/test_subscribe.py::test_subscribe_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_subscribe.py
```

**Wycofanie:** Wyłącz subskrypcję przez enabled=false; nie usuwa to już pobranych plików ani historii.

**Podstawa techniczna:** [S17](research.md#s17), [S18](research.md#s18), [S20](research.md#s20).

<a id="t074"></a>

### T074. Wyznacz adaptacyjne terminy sprawdzania

**Status:** planned.

**Cel:** Harmonogram sprawdza intensywniej po emisji, a nie bez końca co minutę przez cały tydzień.

**Wymagania:** [R09](spec.md#r09), [R18](spec.md#r18), [R23](spec.md#r23), [R24](spec.md#r24).

**Zależności obowiązkowe:** [T073](#t073)

**Kolejność planowa:** T074; poprzednia karta: T073.

**Kontrakt / symbol:** `next_check_time`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `tests/automation/test_schedule_windows.py`

**Istotna granica:** Program nie zakłada, że angielskie wydanie zawsze pojawia się godzinę po japońskiej emisji.

#### Kolejność implementacji

1. Użyj kalendarza wyłącznie jako hint; brak kalendarza daje domyślny interwał co 60 minut dla ongoing.

2. Po znanej emisji zaproponuj pierwszy check po 30 minutach, następnie co 15 minut przez 6 godzin.

3. Jeśli nadal brak wydania, przejdź na godzinę przez dobę, następnie co 6 godzin do nowych danych.

4. Wszystkie wartości oznacz jako edytowalne defaulty projektu, nie gwarancje czasu publikacji.

5. Dodaj ograniczony jitter, wyliczany przez wstrzykiwany generator w testach.

6. Wspólny budżet hosta ma pierwszeństwo przed indywidualnym terminem serii.

7. Po znalezieniu oczekiwanego wydania przesuń cel na następny znany epizod, zachowując sprawdzanie luk.

8. Nie generuj osobnej biblioteki timerów; zapisz next_check_at w tej samej bazie.

#### Scenariusze weryfikacji

<a id="t074-c01"></a>

##### T074-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Emisja ma znany czas, pliku jeszcze nie ma.

**Działanie:** Wyznacz terminy.

**Oczekiwany rezultat:** Działa określone okno checks i późniejsze spowolnienie.

**Niedopuszczalny skutek:** Nie uruchomiono pobierania od samej daty.

**Docelowy test:** `tests/automation/test_schedule_windows.py::test_schedule_windows_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t074-c02"></a>

##### T074-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Kalendarz jest niedostępny.

**Działanie:** Oblicz następny check.

**Oczekiwany rezultat:** Użyty zostaje fallback interwał.

**Niedopuszczalny skutek:** Nie zatrzymano subskrypcji na stałe.

**Docelowy test:** `tests/automation/test_schedule_windows.py::test_schedule_windows_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t074-c03"></a>

##### T074-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** 15 serii ma identyczną godzinę.

**Działanie:** Zastosuj jitter i budżet.

**Oczekiwany rezultat:** Requesty nie wychodzą jednocześnie ponad limit.

**Niedopuszczalny skutek:** Nie odpytano hosta 15 razy w jednej klatce.

**Docelowy test:** `tests/automation/test_schedule_windows.py::test_schedule_windows_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t074-c04"></a>

##### T074-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wydanie pojawiło się dopiero następnego dnia.

**Działanie:** Wykonaj check.

**Oczekiwany rezultat:** Może zostać przyjęte bez nowej deklaracji użytkownika.

**Niedopuszczalny skutek:** Nie porzucono odcinka po arbitralnej godzinie.

**Docelowy test:** `tests/automation/test_schedule_windows.py::test_schedule_windows_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_schedule_windows.py
```

**Wycofanie:** Przywróć stały, ostrożny interwał sprawdzania; zapisana subskrypcja i kolejka pozostają ważne.

**Podstawa techniczna:** [S16](research.md#s16), [S18](research.md#s18), [S24](research.md#s24).

<a id="t075"></a>

### T075. Licz brakujące odcinki jako zbiór, nie last+1

**Status:** planned.

**Cel:** Pojawienie się odcinka 12 nie może ukryć brakującego odcinka 3.

**Wymagania:** [R09](spec.md#r09), [R10](spec.md#r10), [R19](spec.md#r19), [R21](spec.md#r21).

**Zależności obowiązkowe:** [T074](#t074)

**Kolejność planowa:** T075; poprzednia karta: T074.

**Kontrakt / symbol:** `compute_missing_episodes`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `tests/automation/test_missing_set.py`

**Istotna granica:** Znane luki i następny numer do zdobycia nie są licznikiem obejrzanych odcinków.

#### Kolejność implementacji

1. Wyznacz desired episodes z jawnego zakresu użytkownika, znanych emisji i potwierdzonych wydań.

2. Usuń z desired epizody gotowe, aktywnie pobierane lub świadomie pominięte.

3. Nie usuwaj epizodu wyłącznie dlatego, że został obejrzany z innego źródła; polityka zdobywania jest oddzielna.

4. Najmniejszy niepokryty EpisodeKey regularny pokazuj jako Następny do zdobycia, a dodatki osobno.

5. Dla nieznanej liczby epizodów nie generuj nieskończonego zakresu; rozszerzaj na podstawie konkretnych dowodów.

6. Uwzględnij multi-episode coverage i potwierdzone reguły numeracji.

7. Failed/attention może pozostać brakującym celem wymagającym interwencji, bez ślepego powtarzania download.

8. Każdy znany gap ma własny termin poszukiwania i może korzystać z historycznego search.

#### Scenariusze weryfikacji

<a id="t075-c01"></a>

##### T075-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Posiadane 1,2,4, desired 1–5.

**Działanie:** Policz missing.

**Oczekiwany rezultat:** Brakujące to 3 i 5, następny to 3.

**Niedopuszczalny skutek:** Nie przyjęto 5 jako jedynego braku.

**Docelowy test:** `tests/automation/test_missing_set.py::test_missing_set_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t075-c02"></a>

##### T075-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Epizod 3 jest aktualnie pobierany.

**Działanie:** Policz missing i status.

**Oczekiwany rezultat:** Nie tworzony jest drugi download 3.

**Niedopuszczalny skutek:** Nie myli się pobieranego z gotowym.

**Docelowy test:** `tests/automation/test_missing_set.py::test_missing_set_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t075-c03"></a>

##### T075-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Brak znanej liczby odcinków.

**Działanie:** Rozszerz desired.

**Oczekiwany rezultat:** Uwzględnione są tylko udokumentowane numery.

**Niedopuszczalny skutek:** Nie wygenerowano arbitralnie 1000 oczekiwań.

**Docelowy test:** `tests/automation/test_missing_set.py::test_missing_set_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t075-c04"></a>

##### T075-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Paczka pokrywa odcinki 1 i 2 wspólnym plikiem.

**Działanie:** Zastosuj coverage.

**Oczekiwany rezultat:** Oba cele są pokryte jednym jobem.

**Niedopuszczalny skutek:** Nie dodano drugiego pobrania dla epizodu 2.

**Docelowy test:** `tests/automation/test_missing_set.py::test_missing_set_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_missing_set.py
```

**Wycofanie:** Przywróć poprzednią regułę desired, zachowując fakty posiadania i oglądania; nie nadpisuj ich obliczonym licznikiem.

**Podstawa techniczna:** [S17](research.md#s17), [S20](research.md#s20), [S30](research.md#s30).

<a id="t076"></a>

### T076. Nadrabiaj zaległości po wyłączeniu i uśpieniu

**Status:** planned.

**Cel:** Po powrocie komputera program znajduje brakujące wydania bez lawiny requestów i bez utraty dawnych luk.

**Wymagania:** [R09](spec.md#r09), [R13](spec.md#r13), [R17](spec.md#r17), [R18](spec.md#r18), [R23](spec.md#r23).

**Zależności obowiązkowe:** [T075](#t075)

**Kolejność planowa:** T076; poprzednia karta: T075.

**Kontrakt / symbol:** `plan_catchup`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `anishift/automation/worker.py`
- `tests/automation/test_catchup.py`

**Istotna granica:** Praca lokalna odbywa się wyłącznie przy działającym komputerze i procesie użytkownika.

#### Kolejność implementacji

1. Po starcie porównaj aktualny UTC z next_check_at i last_successful_check_at każdej aktywnej serii.

2. Uruchom co najwyżej jedno zaległe sprawdzenie na serię w pierwszej kolejce catch-up.

3. Współdziel odczyty tych samych feedów oraz rozkładaj zapytania według budżetu hosta.

4. Jeżeli nieobecność przekracza pokrycie RSS, uruchom ograniczone historyczne wyszukiwanie brakujących numerów.

5. Zapisuj cursor długiego catch-up, aby ponowny restart nie zaczynał całego skanu od zera.

6. Skok zegara systemowego nie odtwarza wszystkich pominiętych ticków; monotonic clock obsługuje czekanie, UTC trwałe terminy.

7. Nie wybudzaj komputera automatycznie i nie zmieniaj planu zasilania w tym zakresie.

8. Pokaż stan Nadrabianie i liczbę serii do sprawdzenia, zachowując działającą bibliotekę.

#### Scenariusze weryfikacji

<a id="t076-c01"></a>

##### T076-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Komputer był wyłączony 7 dni.

**Działanie:** Uruchom catch-up.

**Oczekiwany rezultat:** Znane braki są sprawdzane z ograniczonym budżetem.

**Niedopuszczalny skutek:** Nie wykonano jednego requestu na każdy pominięty interwał.

**Docelowy test:** `tests/automation/test_catchup.py::test_catchup_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t076-c02"></a>

##### T076-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nowe wydanie zniknęło już z krótkiego feedu.

**Działanie:** Sprawdź historię.

**Oczekiwany rezultat:** Możliwe jest znalezienie starszego rekordu przez HTML search.

**Niedopuszczalny skutek:** Nie uznano nieobecności w RSS za brak odcinka.

**Docelowy test:** `tests/automation/test_catchup.py::test_catchup_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t076-c03"></a>

##### T076-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zegar przesunięto o kilka godzin.

**Działanie:** Przelicz terminy.

**Oczekiwany rezultat:** Nie powstaje gorąca pętla ani wielodniowy deadlock.

**Niedopuszczalny skutek:** Nie oparto wszystkich opóźnień na wall clock bez walidacji.

**Docelowy test:** `tests/automation/test_catchup.py::test_catchup_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t076-c04"></a>

##### T076-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Restart podczas catch-up.

**Działanie:** Wznów cursor.

**Oczekiwany rezultat:** Nie tracą się potwierdzone wydania ani wybrane epizody.

**Niedopuszczalny skutek:** Nie resetuje się historyczne wyszukiwanie bez potrzeby.

**Docelowy test:** `tests/automation/test_catchup.py::test_catchup_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_catchup.py
```

**Wycofanie:** Wstrzymaj catch-up dla źródła i zachowaj cursor; zwykłe lokalne przetwarzanie pozostaje dostępne.

**Podstawa techniczna:** [S16](research.md#s16), [S18](research.md#s18), [S24](research.md#s24).

<a id="t077"></a>

### T077. Ogranicz zapas do oglądania i uprzywilejuj bieżące serie

**Status:** planned.

**Cel:** Tytuły na później mogą przygotowywać się same, ale nie zapełniają dysku kosztem odcinka, który użytkownik chce teraz.

**Wymagania:** [R09](spec.md#r09), [R10](spec.md#r10), [R21](spec.md#r21), [R24](spec.md#r24).

**Zależności obowiązkowe:** [T076](#t076)

**Kolejność planowa:** T077; poprzednia karta: T076.

**Kontrakt / symbol:** `BacklogPolicy.admit`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `anishift/automation/worker.py`
- `tests/automation/test_backlog.py`

**Istotna granica:** Limity zapasu są preferencjami użytkownika, nie automatyczną retencją kasującą multimedia.

#### Kolejność implementacji

1. Wprowadź limit gotowych nieobejrzanych epizodów na serię oraz limit aktywnie pobieranych danych.

2. Dla backlog domyślnie wybieraj niższy priorytet od bieżącego sezonu i ręcznej akcji.

3. Future_collect może zbierać cały znany sezon po świadomym wybraniu, z kontrolą miejsca i maksymalną liczbą aktywnych zadań.

4. Nie traktuj samego wpisu plan-to-watch z MAL jako zgody na pobranie.

5. Oznaczenie epizodu jako obejrzany może zwolnić logiczny slot zapasu, ale nie kasuje jego pliku.

6. Jeśli limit zapasu jest osiągnięty, subskrypcja nadal może aktualizować informacje o wydaniach rzadziej, bez download.

7. Ręczny priorytet może ominąć limit zapasu dla konkretnego epizodu po pokazaniu skutku, ale nie limit wolnego dysku.

8. Zapisuj przyczynę paused_by_policy, aby nie mylić jej z błędem sieci.

#### Scenariusze weryfikacji

<a id="t077-c01"></a>

##### T077-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Backlog osiągnął limit nieobejrzanych.

**Działanie:** Sprawdź serię.

**Oczekiwany rezultat:** Nie rusza następne automatyczne pobieranie.

**Niedopuszczalny skutek:** Nie rośnie bez końca biblioteka tylko dlatego, że API jest darmowe.

**Docelowy test:** `tests/automation/test_backlog.py::test_backlog_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t077-c02"></a>

##### T077-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik oznaczył odcinek jako obejrzany.

**Działanie:** Przelicz zapas.

**Oczekiwany rezultat:** Może wystartować kolejny brakujący epizod.

**Niedopuszczalny skutek:** Nie usunięto pliku obejrzanego odcinka.

**Docelowy test:** `tests/automation/test_backlog.py::test_backlog_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t077-c03"></a>

##### T077-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Na liście MAL jest 100 plan-to-watch.

**Działanie:** Zaimportuj listę.

**Oczekiwany rezultat:** Żaden tytuł nie zaczyna się pobierać bez wyboru.

**Niedopuszczalny skutek:** Nie subskrybowano wszystkiego domyślnie.

**Docelowy test:** `tests/automation/test_backlog.py::test_backlog_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t077-c04"></a>

##### T077-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Bieżący odcinek pojawia się podczas backlogu.

**Działanie:** Wybierz następny job.

**Oczekiwany rezultat:** Otrzymuje wyższy priorytet dla wolnych zasobów.

**Niedopuszczalny skutek:** Nie przerywa niebezpiecznie publikacji aktywnego produktu.

**Docelowy test:** `tests/automation/test_backlog.py::test_backlog_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_backlog.py
```

**Wycofanie:** Wyłącz kolekcjonowanie przyszłych odcinków dla serii; zachowaj już przygotowany zapas i historię.

**Podstawa techniczna:** [S18](research.md#s18), [S20](research.md#s20).

<a id="t078"></a>

### T078. Połącz retry, opóźnienia premier i limity źródeł

**Status:** planned.

**Cel:** Brak wydania, awaria źródła i limit zapytań mają różne następne kroki.

**Wymagania:** [R09](spec.md#r09), [R18](spec.md#r18), [R23](spec.md#r23), [R24](spec.md#r24).

**Zależności obowiązkowe:** [T077](#t077)

**Kolejność planowa:** T078; poprzednia karta: T077.

**Kontrakt / symbol:** `ProviderRetryPolicy`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `anishift/automation/http.py`
- `tests/automation/test_subscription_retry.py`

**Istotna granica:** Zmiana API to lokalna awaria adaptera, nie powód do przebudowy całego programu.

#### Kolejność implementacji

1. Poprawny pusty wynik przesuwa check zgodnie z oknem dostępności, bez zwiększania licznika awarii providera.

2. HTTP timeout/5xx stosuje backoff z jitter i zachowaniem ostatniego poprawnego wyniku.

3. 429 honoruje najpóźniejszy z Retry-After, reset header oraz lokalnego budżetu.

4. Auth/challenge/schema_changed blokuje automatyczne próby danego źródła po małej liczbie porażek i pokazuje akcję naprawczą.

5. Inny dostępny feed może być użyty tylko jeśli jest wcześniej jawnie skonfigurowany w polityce źródeł.

6. Nie przełączaj na przypadkowe mirrory, proxy, captcha solvery i rotację kont.

7. Po ręcznym Sprawdź teraz nadal respektuj serwerowy Retry-After.

8. Udane pobranie resetuje licznik przejściowych awarii, ale nie usuwa historii ważnych błędów.

#### Scenariusze weryfikacji

<a id="t078-c01"></a>

##### T078-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Poprawny feed nie ma nowego epizodu.

**Działanie:** Przelicz retry.

**Oczekiwany rezultat:** Następuje zwykły kolejny check.

**Niedopuszczalny skutek:** Nie oznaczono indeksu jako uszkodzonego.

**Docelowy test:** `tests/automation/test_subscription_retry.py::test_retry_policy_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t078-c02"></a>

##### T078-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Host zwrócił 429 na 300 sekund.

**Działanie:** Naciśnij Sprawdź teraz.

**Oczekiwany rezultat:** Akcja czeka do dozwolonego terminu.

**Niedopuszczalny skutek:** Nie obchodzono limitu na życzenie UI.

**Docelowy test:** `tests/automation/test_subscription_retry.py::test_retry_policy_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t078-c03"></a>

##### T078-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Schemat HTML uległ zmianie.

**Działanie:** Wykonaj ograniczone próby.

**Oczekiwany rezultat:** Źródło ma attention i nie spamuje requestami.

**Niedopuszczalny skutek:** Nie oznaczono sezonu jako zakończony.

**Docelowy test:** `tests/automation/test_subscription_retry.py::test_retry_policy_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t078-c04"></a>

##### T078-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Po poprawce adaptera źródło działa.

**Działanie:** Ponów świadomie.

**Oczekiwany rezultat:** Subskrypcje wracają do pracy z zachowaną historią.

**Niedopuszczalny skutek:** Nie wymagano ponownego dodania wszystkich serii.

**Docelowy test:** `tests/automation/test_subscription_retry.py::test_retry_policy_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_subscription_retry.py
```

**Wycofanie:** Wymuś pauzę konkretnego źródła; inne źródła i lokalny pipeline pozostają aktywne.

**Podstawa techniczna:** [S18](research.md#s18), [S23](research.md#s23), [S24](research.md#s24).

<a id="t079"></a>

### T079. Dodaj pauzę serii, zmianę zakresu i ręczne sprawdzenie

**Status:** planned.

**Cel:** Właściciel kontroluje subskrypcję bez ukrytych zmian już wykonywanych odcinków.

**Wymagania:** [R09](spec.md#r09), [R10](spec.md#r10), [R16](spec.md#r16), [R25](spec.md#r25), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T078](#t078)

**Kolejność planowa:** T079; poprzednia karta: T078.

**Kontrakt / symbol:** `pause_subscription / update_subscription`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `anishift/automation/commands.py`
- `tests/automation/test_schedule_controls.py`

**Istotna granica:** Wyłączenie subskrypcji jest odwracalne i niezależne od danych już przygotowanych.

#### Kolejność implementacji

1. Pause series zatrzymuje nowe sprawdzania/dobór źródeł, lecz nie usuwa kolejki ani produktu.

2. Zdefiniuj osobną akcję Wstrzymaj nowe pobrania i opcjonalne anulowanie konkretnych aktywnych jobów.

3. Zmiana grupy, zakresu albo profilu jest wersjonowaną aktualizacją przyszłych decyzji.

4. Sprawdź teraz tworzy komendę z deduplikacją i respektuje aktywny in-flight oraz rate limit.

5. Usunięcie subskrypcji domyślnie archiwizuje regułę, zachowując bibliotekę.

6. Wznowienie przelicza missing set i catch-up, nie zakłada, że wszystkie dawne intenty nadal są aktualne.

7. Zmiana start episode pokazuje podgląd odcinków dodawanych lub pomijanych.

8. Każda akcja ma krótki receipt i aktualizuje ten sam snapshot widoczny w CLI i TUI.

#### Scenariusze weryfikacji

<a id="t079-c01"></a>

##### T079-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Seria została zatrzymana.

**Działanie:** Wykonaj kolejny tick.

**Oczekiwany rezultat:** Nie powstają nowe download intenty.

**Niedopuszczalny skutek:** Nie skasowano ukończonych produktów.

**Docelowy test:** `tests/automation/test_schedule_controls.py::test_schedule_controls_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t079-c02"></a>

##### T079-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Sprawdź teraz kliknięto kilka razy.

**Działanie:** Obsłuż komendy.

**Oczekiwany rezultat:** Działa jedno sprawdzenie tego zakresu.

**Niedopuszczalny skutek:** Nie pomnożono requestów providerów.

**Docelowy test:** `tests/automation/test_schedule_controls.py::test_schedule_controls_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t079-c03"></a>

##### T079-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zmiana grupy podczas aktywnego TTS.

**Działanie:** Zapisz preferencję.

**Oczekiwany rezultat:** Aktywny job zachowuje wcześniejszy snapshot.

**Niedopuszczalny skutek:** Nie podmieniono wejścia w trakcie wykonania.

**Docelowy test:** `tests/automation/test_schedule_controls.py::test_schedule_controls_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t079-c04"></a>

##### T079-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wznowienie po miesiącu.

**Działanie:** Policz missing i catch-up.

**Oczekiwany rezultat:** Powstaje aktualny plan zdobywania braków.

**Niedopuszczalny skutek:** Nie uruchomiono ślepo starych anulowanych zadań.

**Docelowy test:** `tests/automation/test_schedule_controls.py::test_schedule_controls_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_schedule_controls.py
```

**Wycofanie:** Przywróć poprzednią wersję reguły subskrypcji; nie cofa to wykonanych transferów ani nie kasuje mediów.

**Podstawa techniczna:** [S17](research.md#s17), [S20](research.md#s20), [S34](research.md#s34).

<a id="t080"></a>

### T080. Pokaż następne działanie i rzeczywistą przyczynę oczekiwania

**Status:** planned.

**Cel:** Harmonogram odpowiada na pytanie co program zrobi dalej i dlaczego jeszcze nie pobrał odcinka.

**Wymagania:** [R09](spec.md#r09), [R14](spec.md#r14), [R18](spec.md#r18), [R21](spec.md#r21), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T079](#t079)

**Kolejność planowa:** T080; poprzednia karta: T079.

**Kontrakt / symbol:** `SubscriptionSnapshot`.

#### Pliki i zakres edycji

- `anishift/automation/subscriptions.py`
- `anishift/automation/progress.py`
- `tests/automation/test_schedule_snapshot.py`

**Istotna granica:** Pobranie i obejrzenie mają osobne wskaźniki; harmonogram pokazuje cel zdobywania, nie fikcyjny postęp MAL.

#### Kolejność implementacji

1. W wierszu serii pokaż następny do zdobycia, znaną emisję, następny check i ostatni udany odczyt.

2. Oddziel Czeka na emisję, Czeka na wydanie, Limit źródła, Pauza, Brak klienta i Osiągnięty zapas.

3. Czas prezentuj w Europe/Warsaw, a w szczegółach udostępnij także jednoznaczny UTC.

4. Nie zastępuj nieznanej daty wymyślonym dniem tygodnia.

5. Jeżeli preferowana grupa ma opóźnienie, pokaż ją i termin ewentualnego jawnego fallbacku.

6. Season completed z katalogu nie oznacza automatycznie, że wszystkie pliki zostały zdobyte.

7. Dodaj filtr Aktywne, Wstrzymane i Wymaga uwagi bez tworzenia drugiego właściciela stanu.

8. Otworzenie szczegółów nie wykonuje check ani download bez jawnej akcji.

#### Scenariusze weryfikacji

<a id="t080-c01"></a>

##### T080-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Seria czeka na Group-A po emisji.

**Działanie:** Pokaż wiersz.

**Oczekiwany rezultat:** Widać konkretny brak wydania i termin check.

**Niedopuszczalny skutek:** Nie wyświetlono ogólnego nieczytelnego Waiting.

**Docelowy test:** `tests/automation/test_schedule_snapshot.py::test_schedule_snapshot_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t080-c02"></a>

##### T080-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Limit hosta blokuje sprawdzenie.

**Działanie:** Pokaż stan.

**Oczekiwany rezultat:** Widoczny jest Retry-After jako czas oczekiwania.

**Niedopuszczalny skutek:** Nie obwiniono braku seedów.

**Docelowy test:** `tests/automation/test_schedule_snapshot.py::test_schedule_snapshot_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t080-c03"></a>

##### T080-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Kalendarz ma completed, ale brak epizodu 3.

**Działanie:** Pokaż podsumowanie.

**Oczekiwany rezultat:** Brak 3 nadal jest celem subskrypcji.

**Niedopuszczalny skutek:** Nie zamknięto automatycznie niekompletnej serii.

**Docelowy test:** `tests/automation/test_schedule_snapshot.py::test_schedule_snapshot_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t080-c04"></a>

##### T080-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik otworzył i zamknął szczegóły.

**Działanie:** Sprawdź requesty.

**Oczekiwany rezultat:** Nie ma nowych mutacji i requestów wynikających z renderu.

**Niedopuszczalny skutek:** Nie pobrano odcinka przez nawigację.

**Docelowy test:** `tests/automation/test_schedule_snapshot.py::test_schedule_snapshot_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_schedule_snapshot.py
```

**Wycofanie:** Wycofaj tylko nowy widok harmonogramu; zapisane terminy i reguły pozostają odczytywalne przez CLI.

**Podstawa techniczna:** [S07](research.md#s07), [S16](research.md#s16), [S18](research.md#s18).

<a id="p10"></a>

## P10. Biblioteka, odtwarzanie i własny postęp oglądania

**Wynik fazy:** Właściciel widzi uporządkowane gotowe odcinki i luki.

**Wejście:** P04/P08/P09: produkty, coverage i subskrypcje.

**Warunek wyjścia:** Player otwiera poprawny finalny produkt; watched jest jawne; brak pliku nie kasuje historii.

**Status fazy:** planned.

<a id="t081"></a>

### T081. Zbuduj bibliotekę jako widok istniejących faktów

**Status:** planned.

**Cel:** Biblioteka nie wymaga ręcznego przepisywania stanu pobierania i obróbki.

**Wymagania:** [R11](spec.md#r11), [R15](spec.md#r15), [R20](spec.md#r20), [R21](spec.md#r21).

**Zależności obowiązkowe:** [T040](#t040), [T080](#t080)

**Kolejność planowa:** T081; poprzednia karta: T080.

**Kontrakt / symbol:** `LibraryService.query`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `tests/automation/test_library_query.py`

**Istotna granica:** Biblioteka jest projekcją jednej historii, nie dodatkowym ręcznie prowadzonym trackerem.

#### Kolejność implementacji

1. Zbuduj zapytanie series → episodes → job_episodes → jobs → artifacts z wyborem aktywnej rewizji.

2. Pokaż tytuł, format, numer, źródło, stan przygotowania i odrębny watched_at.

3. Wskaż jedną aktywną gotową rewizję, a starsze pokaż w szczegółach.

4. Nie licz wielokrotnie wspólnego pliku multi-episode ani identycznego artifact.

5. Zachowaj _unsorted jako pełnoprawną sekcję dla własnych plików bez rozpoznanej serii.

6. Dodaj filtry Gotowe, W trakcie, Wymaga uwagi i Obejrzane oparte na jednym stanie w bazie.

7. Czytaj bibliotekę bez połączenia z AniList i qBittorrent.

8. Dane przeznaczone dla renderera zwracaj w niemutowalnym snapshot, bez cursor i opóźnionego I/O.

#### Scenariusze weryfikacji

<a id="t081-c01"></a>

##### T081-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Seria ma gotową i nieudaną rewizję tego samego epizodu.

**Działanie:** Odczytaj bibliotekę.

**Oczekiwany rezultat:** Domyślnie widoczny jest dobry produkt i informacja o nowej nieudanej próbie.

**Niedopuszczalny skutek:** Nie znika działający film.

**Docelowy test:** `tests/automation/test_library_query.py::test_library_query_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t081-c02"></a>

##### T081-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Brak sieci i klienta torrent.

**Działanie:** Otwórz Gotowe.

**Oczekiwany rezultat:** Biblioteka pozostaje dostępna.

**Niedopuszczalny skutek:** Nie czeka na odświeżenie katalogu online.

**Docelowy test:** `tests/automation/test_library_query.py::test_library_query_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t081-c03"></a>

##### T081-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Jeden produkt jest współdzielony przez dwa epizody.

**Działanie:** Podsumuj dysk.

**Oczekiwany rezultat:** Bajty liczone są raz.

**Niedopuszczalny skutek:** Nie podwojono zajętości.

**Docelowy test:** `tests/automation/test_library_query.py::test_library_query_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t081-c04"></a>

##### T081-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nieznany lokalny film został przetworzony.

**Działanie:** Otwórz _unsorted.

**Oczekiwany rezultat:** Można go odtworzyć i później przypisać.

**Niedopuszczalny skutek:** Nie utracono wyniku z powodu braku media ID.

**Docelowy test:** `tests/automation/test_library_query.py::test_library_query_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_library_query.py
```

**Wycofanie:** Wyłącz nowy widok odczytowy bez usuwania tabel i produktów; historia wykonania pozostaje dostępna w bazie.

**Podstawa techniczna:** [S06](research.md#s06), [S33](research.md#s33), [S34](research.md#s34).

<a id="t082"></a>

### T082. Uruchom mpv z właściwym gotowym produktem

**Status:** planned.

**Cel:** Akcja Oglądaj otwiera zwalidowany film z lektorem bez szukania ścieżki w Explorerze.

**Wymagania:** [R11](spec.md#r11), [R16](spec.md#r16), [R21](spec.md#r21), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T081](#t081)

**Kolejność planowa:** T082; poprzednia karta: T081.

**Kontrakt / symbol:** `PlayerLauncher.open`.

#### Pliki i zakres edycji

- `anishift/platform/automation_player.py`
- `anishift/automation/library.py`
- `tests/automation/test_player.py`

**Istotna granica:** Nie budujemy własnego odtwarzacza ani integracji streamingowej z niepełnym plikiem.

#### Kolejność implementacji

1. Wczytaj jawnie skonfigurowaną ścieżkę mpv lub sprawdź executable w PATH bez instalacji.

2. Wybierz playable_product_id aktywnej rewizji, nie pierwszy plik o rozszerzeniu .mkv.

3. Potwierdź istnienie produktu i jego powiązanie z jobem przed uruchomieniem.

4. Użyj listy argumentów [mpv, --, path] z shell=False i stdin=DEVNULL.

5. Nie przekazuj playerowi wartości credentials AniShift; środowisko dziecka ogranicz do potrzebnych zmiennych systemowych.

6. Nie blokuj workera podczas odtwarzania; proces playera ma niezależny lifecycle.

7. Brak mpv pokazuje wybór ścieżki albo jawną opcję otwarcia bezpiecznego pliku skojarzonym odtwarzaczem.

8. Otwarcie i zamknięcie playera zapisuj najwyżej jako playback action, nie jako watched.

#### Scenariusze weryfikacji

<a id="t082-c01"></a>

##### T082-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Ścieżka zawiera spacje, polskie znaki i apostrof.

**Działanie:** Uruchom Oglądaj.

**Oczekiwany rezultat:** Player dostaje dokładnie jeden argument pliku.

**Niedopuszczalny skutek:** Nie użyto shell=True ani ręcznego sklejania polecenia.

**Docelowy test:** `tests/automation/test_player.py::test_player_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t082-c02"></a>

##### T082-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Obok finalnego filmu leży oryginał.

**Działanie:** Wybierz produkt.

**Oczekiwany rezultat:** Otwarty zostaje finalny polski kontener.

**Niedopuszczalny skutek:** Nie wybrano oryginału alfabetycznie.

**Docelowy test:** `tests/automation/test_player.py::test_player_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t082-c03"></a>

##### T082-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** mpv nie jest zainstalowane.

**Działanie:** Wywołaj akcję.

**Oczekiwany rezultat:** Pokazana jest konkretna konfiguracja playera.

**Niedopuszczalny skutek:** Nie rozpoczęto nieuzgodnionej instalacji.

**Docelowy test:** `tests/automation/test_player.py::test_player_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t082-c04"></a>

##### T082-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik zamknął film po sekundzie.

**Działanie:** Odczytaj watch state.

**Oczekiwany rezultat:** Epizod nadal nie jest automatycznie obejrzany.

**Niedopuszczalny skutek:** Nie zrównano kodu wyjścia 0 z obejrzeniem.

**Docelowy test:** `tests/automation/test_player.py::test_player_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_player.py
```

**Wycofanie:** Wyłącz launcher i pokaż ścieżkę produktu; nie zmieniaj systemowych skojarzeń rozszerzeń.

**Podstawa techniczna:** [S37](research.md#s37), [S38](research.md#s38).

<a id="t083"></a>

### T083. Dodaj jawne oznaczanie obejrzenia

**Status:** planned.

**Cel:** Postęp oglądania jest prawdziwą decyzją właściciela, niezależną od pobierania i generowania lektora.

**Wymagania:** [R10](spec.md#r10), [R19](spec.md#r19), [R21](spec.md#r21), [R22](spec.md#r22).

**Zależności obowiązkowe:** [T082](#t082)

**Kolejność planowa:** T083; poprzednia karta: T082.

**Kontrakt / symbol:** `mark_watched / unmark_watched`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `anishift/automation/commands.py`
- `tests/automation/test_watch_state.py`

**Istotna granica:** Ten zakres nie posiada automatycznego outbound sync do kont MAL/AniList.

#### Kolejność implementacji

1. Zapisuj watched_at w episodes, nie w transferze i nie w pojedynczej rewizji.

2. Akcja Obejrzane przyjmuje dokładny EpisodeKey lub jawny zbiór zaznaczonych epizodów.

3. Powtórzenie tej samej komendy nie zmienia daty pierwszego oznaczenia bez osobnej akcji korekty.

4. Cofnięcie oznaczenia jest jawną operacją i nie usuwa produktów.

5. Dla wspólnego pliku 1–2 pokaż wybór jednego numeru albo całego zakresu.

6. Nie wysyłaj zapisów do MAL i AniList przy żadnym lokalnym przejściu ready.

7. Po zmianie watched przelicz backlog limit i następny odcinek do oglądania.

8. Przechowuj osobno informację pochodzącą z eksportu MAL, aby nie udawać synchronizacji online.

#### Scenariusze weryfikacji

<a id="t083-c01"></a>

##### T083-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Epizod przeszedł do ready.

**Działanie:** Odczytaj watched_at.

**Oczekiwany rezultat:** Pole pozostaje puste.

**Niedopuszczalny skutek:** Nie zwiększono licznika oglądania.

**Docelowy test:** `tests/automation/test_watch_state.py::test_watch_state_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t083-c02"></a>

##### T083-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik oznaczył 1 i 2 ze wspólnego pliku.

**Działanie:** Zapisz komendę.

**Oczekiwany rezultat:** Zmieniają się dwa jawnie wybrane epizody.

**Niedopuszczalny skutek:** Nie zmieniono pozostałych epizodów serii.

**Docelowy test:** `tests/automation/test_watch_state.py::test_watch_state_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t083-c03"></a>

##### T083-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Cofnięto Obejrzane.

**Działanie:** Zastosuj.

**Oczekiwany rezultat:** Film i jego gotowość pozostają bez zmian.

**Niedopuszczalny skutek:** Nie skasowano źródła ani produktu.

**Docelowy test:** `tests/automation/test_watch_state.py::test_watch_state_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t083-c04"></a>

##### T083-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wykonano ponownie command_id oznaczenia.

**Działanie:** Zastosuj.

**Oczekiwany rezultat:** Wynik jest idempotentny.

**Niedopuszczalny skutek:** Nie przesunięto daty oglądania przy każdym reconnect.

**Docelowy test:** `tests/automation/test_watch_state.py::test_watch_state_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_watch_state.py
```

**Wycofanie:** Przywróć poprzedni watch record przez jawną korektę; nie odtwarzaj go automatycznie z liczby pobranych plików.

**Podstawa techniczna:** [S06](research.md#s06), [S28](research.md#s28), [S39](research.md#s39), [S40](research.md#s40).

<a id="t084"></a>

### T084. Wskaż następny odcinek bez ukrywania luk

**Status:** planned.

**Cel:** Biblioteka rozróżnia następny do zdobycia od następnego do obejrzenia.

**Wymagania:** [R09](spec.md#r09), [R11](spec.md#r11), [R19](spec.md#r19), [R21](spec.md#r21).

**Zależności obowiązkowe:** [T083](#t083)

**Kolejność planowa:** T084; poprzednia karta: T083.

**Kontrakt / symbol:** `next_to_watch / next_to_acquire`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `tests/automation/test_next_episode.py`

**Istotna granica:** Chronologia fabularna całej franczyzy nie jest automatycznie wyprowadzana z numerów plików.

#### Kolejność implementacji

1. Wyznacz next_to_watch z porządku znanych regularnych epizodów i lokalnego watched state.

2. Jeśli następny epizod nie jest gotowy, pokaż Przygotuj/Czeka zamiast przeskakiwać bez wyjaśnienia do późniejszego.

3. Pozwól ręcznie otworzyć późniejszy gotowy odcinek po świadomym wyborze.

4. Dodatki pokaż oddzielnie i nie wstawiaj ich arbitralnie między regularne odcinki bez znanego porządku.

5. Akcja Przygotuj następny podnosi priorytet istniejącego joba albo tworzy idempotentne wyszukiwanie brakującego.

6. Nie uzależniaj odtwarzania gotowego odcinka od aktywności subskrypcji.

7. Uwzględnij wspólne coverage i warianty rewizji przy wyborze playable produktu.

8. Pokaż oba liczniki next_to_acquire i next_to_watch, gdy są różne.

#### Scenariusze weryfikacji

<a id="t084-c01"></a>

##### T084-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Obejrzane 1, gotowe 3, brak 2.

**Działanie:** Wyznacz następny.

**Oczekiwany rezultat:** Następny do obejrzenia to 2 z akcją przygotowania.

**Niedopuszczalny skutek:** Nie przeskoczono cicho do 3.

**Docelowy test:** `tests/automation/test_next_episode.py::test_next_episode_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t084-c02"></a>

##### T084-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Subskrypcja jest wyłączona, epizod 2 gotowy.

**Działanie:** Otwórz 2.

**Oczekiwany rezultat:** Player działa normalnie.

**Niedopuszczalny skutek:** Nie wymaga ponownego włączenia pobierania.

**Docelowy test:** `tests/automation/test_next_episode.py::test_next_episode_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t084-c03"></a>

##### T084-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Obejrzano 7, istnieje nieobejrzane SPECIAL.

**Działanie:** Pokaż następny.

**Oczekiwany rezultat:** Dodatek jest widoczny osobno.

**Niedopuszczalny skutek:** Nie narzucono niepotwierdzonej kolejności fabularnej.

**Docelowy test:** `tests/automation/test_next_episode.py::test_next_episode_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t084-c04"></a>

##### T084-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Przygotuj następny kliknięto ponownie.

**Działanie:** Obsłuż komendę.

**Oczekiwany rezultat:** Podniesiony jest priorytet istniejącej pracy.

**Niedopuszczalny skutek:** Nie dodano drugiego torrenta.

**Docelowy test:** `tests/automation/test_next_episode.py::test_next_episode_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_next_episode.py
```

**Wycofanie:** Wycofaj sugestię następnego epizodu; lista wszystkich gotowych produktów nadal pozwala na ręczne odtwarzanie.

**Podstawa techniczna:** [S06](research.md#s06), [S17](research.md#s17).

<a id="t085"></a>

### T085. Kontroluj wolne miejsce i rezerwacje aktywnej pracy

**Status:** planned.

**Cel:** 15 serii nie może niepostrzeżenie zapełnić dysku przez podwójne kopie i finalne kontenery.

**Wymagania:** [R10](spec.md#r10), [R16](spec.md#r16), [R24](spec.md#r24), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T084](#t084)

**Kolejność planowa:** T085; poprzednia karta: T084.

**Kontrakt / symbol:** `DiskBudget.reserve`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `anishift/automation/worker.py`
- `tests/automation/test_disk_budget.py`

**Istotna granica:** Próg 10 GiB jest decyzją startową do kalibracji, nie pomiarem zapotrzebowania komputera właściciela.

#### Kolejność implementacji

1. Odczytuj wolne miejsce osobno dla downloads, library i temp, uwzględniając gdy leżą na tym samym wolumenie.

2. Zarezerwuj budżet dla aktywnych transferów, kopii, audio oraz planowanych finalnych produktów.

3. Dla wspólnego wolumenu licz rezerwacje raz; dla różnych dysków oceniaj niezależne braki.

4. Użyj minimum wolnej przestrzeni 10 GiB jako edytowalnego startowego progu, dodatkowo ponad szacowaną pracę.

5. Nie traktuj rozmiaru torrenta jako całkowitego końcowego zajęcia biblioteki.

6. Wstrzymuj nowe przyjęcia/download przy braku budżetu, zachowując możliwość oglądania gotowego materiału.

7. Pokazuj źródła, wyniki i staging jako osobne kategorie zajętości.

8. Usuwanie starych źródeł lub rewizji pozostaw jawnej akcji z podglądem, poza automatycznym minimum.

#### Scenariusze weryfikacji

<a id="t085-c01"></a>

##### T085-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Downloads i library są na jednym dysku.

**Działanie:** Policz budżet.

**Oczekiwany rezultat:** Suma uwzględnia rzeczywiste kopie bez podwójnego liczenia rezerwacji.

**Niedopuszczalny skutek:** Nie założono jednego pliku zamiast źródła plus produktu.

**Docelowy test:** `tests/automation/test_disk_budget.py::test_disk_budget_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t085-c02"></a>

##### T085-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wolne miejsce jest poniżej progu.

**Działanie:** Uruchom następny backlog.

**Oczekiwany rezultat:** Nowa praca czeka z disk_full.

**Niedopuszczalny skutek:** Nie kasuje się automatycznie najstarszych odcinków.

**Docelowy test:** `tests/automation/test_disk_budget.py::test_disk_budget_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t085-c03"></a>

##### T085-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Finalny film jest wspólny dla dwóch epizodów.

**Działanie:** Policz zajętość.

**Oczekiwany rezultat:** Plik liczony jest raz.

**Niedopuszczalny skutek:** Nie podwojono rozmiaru przez coverage.

**Docelowy test:** `tests/automation/test_disk_budget.py::test_disk_budget_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t085-c04"></a>

##### T085-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik zwolnił miejsce.

**Działanie:** Przelicz budżet.

**Oczekiwany rezultat:** Zachowany job może wrócić do kolejki.

**Niedopuszczalny skutek:** Nie wymaga ponownego wyszukania źródła.

**Docelowy test:** `tests/automation/test_disk_budget.py::test_disk_budget_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_disk_budget.py
```

**Wycofanie:** Wyłącz nowe pobierania do czasu ręcznego odzyskania miejsca; nigdy nie odzyskuj go przez niejawne usuwanie mediów.

**Podstawa techniczna:** [S20](research.md#s20), [S33](research.md#s33), [S36](research.md#s36).

<a id="t086"></a>

### T086. Wykryj zewnętrzne zmiany i brakujące produkty

**Status:** planned.

**Cel:** Ręczne przeniesienie lub usunięcie pliku nie może pozostawić fałszywego przycisku Oglądaj.

**Wymagania:** [R15](spec.md#r15), [R16](spec.md#r16), [R17](spec.md#r17), [R21](spec.md#r21), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T085](#t085)

**Kolejność planowa:** T086; poprzednia karta: T085.

**Kontrakt / symbol:** `reconcile_library_artifact`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `tests/automation/test_library_reconcile.py`

**Istotna granica:** Istnienie produktu jest sprawdzane przy użyciu; jego kompletna walidacja należy do przyjęcia i recovery.

#### Kolejność implementacji

1. Przy akcji odtwarzania zawsze sprawdź istnienie wybranego artifact, a okresowo kontroluj małe porcje biblioteki.

2. Nie wykonuj kosztownego pełnego hash każdego MKV co tick; pełny digest sprawdzaj przy podejrzeniu zmiany lub recovery.

3. Zewnętrznie usunięty plik oznacz jako missing artifact z zachowaniem joba i watched history.

4. Jeżeli użytkownik wskaże nową lokalizację, zweryfikuj zawartość i własność przed przypisaniem.

5. Nie skanuj całych dysków, aby automatycznie odnaleźć zgubiony tytuł.

6. Nowy obcy plik w library nie staje się automatycznie gotowym produktem bez provenance.

7. Naprawę ścieżki wykonaj atomowo dla konkretnego artifact, bez przemianowania całej serii.

8. Brak produktu nie uruchamia automatycznie nowego TTS bez sprawdzenia zachowanych źródeł i zgody polityki retry.

#### Scenariusze weryfikacji

<a id="t086-c01"></a>

##### T086-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Finalny MKV został usunięty.

**Działanie:** Naciśnij Oglądaj.

**Oczekiwany rezultat:** UI pokazuje brak pliku i naprawę.

**Niedopuszczalny skutek:** Nie uruchamia playera z nieistniejącą ścieżką.

**Docelowy test:** `tests/automation/test_library_reconcile.py::test_library_reconcile_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t086-c02"></a>

##### T086-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Plik został przeniesiony i wskazany przez właściciela.

**Działanie:** Zweryfikuj nową lokalizację.

**Oczekiwany rezultat:** Tożsamość zostaje potwierdzona przed zmianą path.

**Niedopuszczalny skutek:** Nie przypisano pliku wyłącznie po nazwie.

**Docelowy test:** `tests/automation/test_library_reconcile.py::test_library_reconcile_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t086-c03"></a>

##### T086-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** W library pojawił się obcy source.mkv.

**Działanie:** Skanuj.

**Oczekiwany rezultat:** Nie dostaje statusu gotowego lektora.

**Niedopuszczalny skutek:** Nie uruchomiono watchera na produktach.

**Docelowy test:** `tests/automation/test_library_reconcile.py::test_library_reconcile_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t086-c04"></a>

##### T086-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Baza i ścieżki odzyskane po restore.

**Działanie:** Przeprowadź porcjowany reconcile.

**Oczekiwany rezultat:** Gotowość odpowiada rzeczywistym plikom.

**Niedopuszczalny skutek:** Nie odczytano wszystkich gigabajtów w jednej blokującej operacji.

**Docelowy test:** `tests/automation/test_library_reconcile.py::test_library_reconcile_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_library_reconcile.py
```

**Wycofanie:** Przywróć poprzednią referencję ścieżki, zachowując obie lokalizacje do ręcznej decyzji; nie przenoś plików automatycznie.

**Podstawa techniczna:** [S06](research.md#s06), [S11](research.md#s11), [S33](research.md#s33).

<a id="t087"></a>

### T087. Pozwól uporządkować nierozpoznane własne pliki

**Status:** planned.

**Cel:** Plik wrzucony bez poprawnej nazwy może zostać przetworzony od razu i przypisany do anime później.

**Wymagania:** [R04](spec.md#r04), [R12](spec.md#r12), [R15](spec.md#r15), [R19](spec.md#r19), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T086](#t086)

**Kolejność planowa:** T087; poprzednia karta: T086.

**Kontrakt / symbol:** `bind_unsorted_job`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `anishift/automation/commands.py`
- `tests/automation/test_unsorted.py`

**Istotna granica:** Porządek katalogów dotyczy nowych rozpoznanych importów; nie wymusza ryzykownej migracji pliku w trakcie odtwarzania.

#### Kolejność implementacji

1. W sekcji _unsorted pokaż nazwę źródła, gotowy produkt i stan bez wymyślonego tytułu katalogowego.

2. Akcja Przypisz serię korzysta z tego samego wyszukiwania canonical ID i wyboru epizodu.

3. Zapisz powiązanie logiczne z EpisodeKey bez automatycznego przenoszenia aktywnego katalogu rewizji.

4. Późniejsze porządkowanie fizyczne jest oddzielną operacją przy zatrzymanym odtwarzaniu/wykonaniu i z podglądem.

5. Jeżeli seria ma już ten epizod, pokaż konflikt źródeł lub wybór aktywnej rewizji.

6. Przenoś watch history wyłącznie zgodnie z jawnym przypisaniem, nie na podstawie podobieństwa pliku.

7. Cofnięcie przypisania przywraca widoczność w _unsorted bez usuwania rezultatu.

8. Nie uzależniaj prostego drop→Auto od odpowiedzi katalogu online.

#### Scenariusze weryfikacji

<a id="t087-c01"></a>

##### T087-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nieznany plik jest już gotowy w _unsorted.

**Działanie:** Przypisz do serii i epizodu.

**Oczekiwany rezultat:** Produkt pojawia się logicznie w tej serii.

**Niedopuszczalny skutek:** Nie jest ponownie tłumaczony tylko z powodu mapowania.

**Docelowy test:** `tests/automation/test_unsorted.py::test_unsorted_mapping_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t087-c02"></a>

##### T087-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Docelowy epizod ma już gotową rewizję.

**Działanie:** Zapisz przypisanie.

**Oczekiwany rezultat:** Pojawia się wybór aktywnego wydania.

**Niedopuszczalny skutek:** Nie nadpisano istniejącego pliku.

**Docelowy test:** `tests/automation/test_unsorted.py::test_unsorted_mapping_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t087-c03"></a>

##### T087-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Plik jest odtwarzany podczas przypisania.

**Działanie:** Zapisz powiązanie logiczne.

**Oczekiwany rezultat:** Odtwarzanie trwa, ścieżka pozostaje stała.

**Niedopuszczalny skutek:** Nie wykonano rename otwartego produktu.

**Docelowy test:** `tests/automation/test_unsorted.py::test_unsorted_mapping_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t087-c04"></a>

##### T087-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Cofnięto błędne przypisanie.

**Działanie:** Zastosuj korektę.

**Oczekiwany rezultat:** Film wraca do _unsorted bez utraty danych.

**Niedopuszczalny skutek:** Nie usunięto jego watch record bez informacji.

**Docelowy test:** `tests/automation/test_unsorted.py::test_unsorted_mapping_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_unsorted.py
```

**Wycofanie:** Cofnij wyłącznie powiązanie logiczne; fizyczne produkty pozostają w swojej znanej lokalizacji.

**Podstawa techniczna:** [S04](research.md#s04), [S06](research.md#s06), [S17](research.md#s17).

<a id="t088"></a>

### T088. Zapewnij czytelność setek odcinków

**Status:** planned.

**Cel:** Biblioteka pozostaje użyteczna przy kilkunastu seriach i setkach plików, bez skanowania mediów w renderze.

**Wymagania:** [R10](spec.md#r10), [R14](spec.md#r14), [R15](spec.md#r15), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T087](#t087)

**Kolejność planowa:** T088; poprzednia karta: T087.

**Kontrakt / symbol:** `LibraryPage`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `tests/automation/test_library_paging.py`

**Istotna granica:** Liczba 180 wynika z przykładu 15 serii × 12 odcinków, nie z deklarowanej wielkości biblioteki użytkownika.

#### Kolejność implementacji

1. Zastosuj stabilne sortowanie seria, kind, Decimal number, active revision.

2. Udostępnij paginację rekordów i filtrowanie po zapisanych tytułach/aliasach bez requestu sieciowego.

3. Zachowuj wybór po EpisodeKey/ID, nie po pozycji wiersza zmienianej odświeżeniem.

4. Przy dodaniu nowego gotowego odcinka nie przenoś kursora użytkownika bez jego decyzji.

5. Widok podaje licznik ukrytych rekordów i wyraźne puste stany.

6. Odczytaj statystyki zbiorcze jednym kontrolowanym zapytaniem zamiast N+1 zapytań na każdy wiersz.

7. Oddziel pomiar czasu zapytania od pomiaru renderowania terminala.

8. Nie dodawaj indeksu SQL bez odpowiadającego zapytania i powtarzalnego problemu w pomiarze.

#### Scenariusze weryfikacji

<a id="t088-c01"></a>

##### T088-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Biblioteka zawiera 180 epizodów i wiele rewizji.

**Działanie:** Odczytaj stronę.

**Oczekiwany rezultat:** Zwraca ograniczoną liczbę stabilnie posortowanych rekordów.

**Niedopuszczalny skutek:** Nie skanuje zawartości MKV.

**Docelowy test:** `tests/automation/test_library_paging.py::test_library_paging_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t088-c02"></a>

##### T088-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nowy odcinek staje się ready nad wybranym wierszem.

**Działanie:** Odśwież listę.

**Oczekiwany rezultat:** Wybór nadal wskazuje ten sam EpisodeKey.

**Niedopuszczalny skutek:** Nie otwiera przypadkiem sąsiedniego odcinka.

**Docelowy test:** `tests/automation/test_library_paging.py::test_library_paging_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t088-c03"></a>

##### T088-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Filtr nie zwraca żadnych wyników.

**Działanie:** Pokaż widok.

**Oczekiwany rezultat:** Widoczny jest pusty stan i zachowany tekst filtra.

**Niedopuszczalny skutek:** Nie zgłoszono wyjątku indeksu.

**Docelowy test:** `tests/automation/test_library_paging.py::test_library_paging_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t088-c04"></a>

##### T088-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Widok został zamknięty i przywrócony.

**Działanie:** Odtwórz kontekst.

**Oczekiwany rezultat:** Powraca filtr i bezpieczny wybór istniejącego ID.

**Niedopuszczalny skutek:** Nie przechowuje otwartego cursor bazy.

**Docelowy test:** `tests/automation/test_library_paging.py::test_library_paging_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_library_paging.py
```

**Wycofanie:** W razie regresji wróć do prostego stronicowania bez zaawansowanego filtrowania; dane i gotowość nie zmieniają się.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S33](research.md#s33), [S34](research.md#s34).

<a id="p11"></a>

## P11. Wyszukiwanie i automatyzacja w obecnym terminalu

**Wynik fazy:** Pełny workflow jest dostępny w aktualnym terminalu.

**Wejście:** P05–P10 i istniejący TerminalRenderer.

**Warunek wyjścia:** Strzałki, Enter, Space, Esc, paste i resize nie wykonują ukrytych działań; monitor nie jest właścicielem pracy.

**Status fazy:** planned.

<a id="t089"></a>

### T089. Dodaj nowe wejścia do aktualnego Home

**Status:** planned.

**Cel:** Nowe możliwości są dostępne w obecnym terminalu, bez wymiany frameworka, logo i działających ustawień.

**Wymagania:** [R02](spec.md#r02), [R14](spec.md#r14), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T088](#t088), [T008](#t008)

**Kolejność planowa:** T089; poprzednia karta: T088.

**Kontrakt / symbol:** `HomeAction / _HOME_CHOICES / HomeGeometry`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/app.py`
- `anishift/cli/interactive/home.py`
- `anishift/cli/interactive/prompts.py`
- `anishift/cli/AGENTS.md`
- `tests/automation/test_home_routes.py`

**Istotna granica:** To rozszerzenie aktualnego TUI, a nie powrót do historycznego projektu interfejsu z sierpnia.

#### Kolejność implementacji

1. Rozszerz HomeAction i menu do Auto, Ręczny, Anime, Biblioteka, Harmonogram, Ustawienia, Wyjście.

2. Zachowaj domyślny wybór Auto, więc Enter po zwykłym uruchomieniu nadal wykonuje dotychczasową akcję.

3. Zastąp stałe budżety wysokości Home zależnością od liczby realnych opcji, bez ukrywania Wyjścia.

4. Dodaj tryby widoków i routing w istniejącym _InteractiveApplication, używając tego samego TerminalRenderer.

5. Nie wprowadzaj slash-commandów ani nowego Textual/curses interfejsu.

6. Nowe kontrolery otrzymują AutomationClient, nie bezpośrednio qBittorrent lub połączenie sieciowe.

7. Zaktualizuj wąską sekcję cli/AGENTS opisującą Home; pozostałe reguły UI zostają ważne.

8. Sprawdź geometrię niskiego terminala i zachowanie istniejącej maskotki bez pracy nad redesignem.

#### Scenariusze weryfikacji

<a id="t089-c01"></a>

##### T089-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik uruchamia gołe anishift i wciska Enter.

**Działanie:** Obsłuż Home.

**Oczekiwany rezultat:** Uruchamia się istniejące Auto.

**Niedopuszczalny skutek:** Nie zamieniono Enter w wyszukiwanie lub bezczynność.

**Docelowy test:** `tests/automation/test_home_routes.py::test_home_routes_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t089-c02"></a>

##### T089-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Terminal jest niski.

**Działanie:** Renderuj siedem opcji.

**Oczekiwany rezultat:** Dostępne są wszystkie akcje przez przewijanie/kompaktową geometrię.

**Niedopuszczalny skutek:** Nie ukryto Wyjścia pod stopką.

**Docelowy test:** `tests/automation/test_home_routes.py::test_home_routes_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t089-c03"></a>

##### T089-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik wybiera Biblioteka.

**Działanie:** Przejdź do widoku.

**Oczekiwany rezultat:** Powstaje kontroler w tym samym rendererze.

**Niedopuszczalny skutek:** Nie otwiera się drugi alternate screen.

**Docelowy test:** `tests/automation/test_home_routes.py::test_home_routes_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t089-c04"></a>

##### T089-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Powrót z nowego widoku.

**Działanie:** Otwórz Ręczny i Ustawienia.

**Oczekiwany rezultat:** Stare akcje zachowują działanie.

**Niedopuszczalny skutek:** Nie zmieniono indeksów zamiast HomeAction bez aktualizacji routingu.

**Docelowy test:** `tests/automation/test_home_routes.py::test_home_routes_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_home_routes.py
```

**Wycofanie:** Usuń nowe routing entries i przywróć budżet poprzedniego menu; pozostaw bazę automatyzacji do odczytu CLI.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S09](research.md#s09).

<a id="t090"></a>

### T090. Zbuduj ekran wpisywania i wyboru anime

**Status:** planned.

**Cel:** Użytkownik wpisuje nazwę, wybiera konkretny sezon i nie musi otwierać przeglądarki z torrentami.

**Wymagania:** [R03](spec.md#r03), [R04](spec.md#r04), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T089](#t089)

**Kolejność planowa:** T090; poprzednia karta: T089.

**Kontrakt / symbol:** `AnimeController`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/anime.py`
- `tests/automation/test_anime_search_ui.py`

**Istotna granica:** Zwykły tekst w tym dedykowanym polu jest zapytaniem, nie globalną instrukcją dla agenta.

#### Kolejność implementacji

1. Utwórz AnimeController z buforem zapytania, generation, listą wyników i wybranym media ID.

2. Obsłuż tekst, Backspace, Delete, pozycję kursora i BracketedPaste zgodnie z istniejącą tabelą klawiszy.

3. Zastosuj lokalny ranking i debounce backendu bez I/O w render().

4. W wierszu pokaż tytuł, rok, format, status i alias odpowiadający zapytaniu.

5. Enter wybiera media z aktualnego snapshotu; Esc wraca, nie uruchamia pobierania.

6. Po wyborze pokaż dwie główne drogi: Wybierz odcinki i Obserwuj serię.

7. Błąd providerów zachowuje tekst i umożliwia ponowienie albo ręczny magnet.

8. Pokaż sekcję dodatków i kontynuacji bez automatycznego zaznaczania wszystkich.

#### Scenariusze weryfikacji

<a id="t090-c01"></a>

##### T090-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Wpisano literówkę w tytule.

**Działanie:** Odśwież wyniki.

**Oczekiwany rezultat:** Można wybrać właściwy sezon z kontekstem.

**Niedopuszczalny skutek:** Nie pobiera się pierwszy wynik automatycznie.

**Docelowy test:** `tests/automation/test_anime_search_ui.py::test_anime_search_ui_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t090-c02"></a>

##### T090-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Wklejono pełen tytuł ze znakami Unicode.

**Działanie:** Obsłuż paste.

**Oczekiwany rezultat:** Tekst jest zachowany jako jedno wejście.

**Niedopuszczalny skutek:** Nie uruchomiono polecenia powłoki.

**Docelowy test:** `tests/automation/test_anime_search_ui.py::test_anime_search_ui_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t090-c03"></a>

##### T090-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Provider zwraca błąd.

**Działanie:** Pokaż ekran.

**Oczekiwany rezultat:** Tekst i poprzedni bezpieczny kontekst pozostają.

**Niedopuszczalny skutek:** Nie znika cała praca użytkownika.

**Docelowy test:** `tests/automation/test_anime_search_ui.py::test_anime_search_ui_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t090-c04"></a>

##### T090-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Stary request wraca po wybraniu innej serii.

**Działanie:** Zastosuj wynik.

**Oczekiwany rezultat:** Nie zmienia aktywnego media ID.

**Niedopuszczalny skutek:** Nie przekierowuje do złego sezonu.

**Docelowy test:** `tests/automation/test_anime_search_ui.py::test_anime_search_ui_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_anime_search_ui.py
```

**Wycofanie:** Wycofaj nowy kontroler wyszukiwania; ręczny import i istniejące Home nadal działają.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S09](research.md#s09), [S17](research.md#s17), [S31](research.md#s31).

<a id="t091"></a>

### T091. Dodaj wybór grup i odcinków z jednym podglądem

**Status:** planned.

**Cel:** Klawiaturą można wybrać kilka odcinków i rozpocząć jeden kontrolowany proces pobrania.

**Wymagania:** [R05](spec.md#r05), [R06](spec.md#r06), [R08](spec.md#r08), [R19](spec.md#r19), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T090](#t090)

**Kolejność planowa:** T091; poprzednia karta: T090.

**Kontrakt / symbol:** `ReleasePickerController`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/anime.py`
- `tests/automation/test_release_picker_ui.py`

**Istotna granica:** Metadata-only może być wcześniej potrzebne do listy plików; UI rozróżnia je od pobierania treści.

#### Kolejność implementacji

1. Pokaż wydania pogrupowane według epizodu, z grupą, jakością, rozmiarem i dostępnością.

2. Space zaznacza rekord lub plik; strzałki tylko poruszają wybór.

3. Enter przy zaznaczonych rekordach otwiera podgląd, a jawne Pobierz zatwierdza intent.

4. Dla pojedynczego wiersza Enter może otworzyć jego szczegóły; nie dubluj różnych skutków na tym samym stanie ekranu.

5. Wskaż ukryte zbyt niskie jakości oraz odrębną sekcję nieznanej jakości wymagającej metadanych.

6. W wyborze paczki pokazuj realne file_index poprzez stabilne ID widoku, nie numery wierszy.

7. Po zaakceptowaniu pokaż receipt i przejście do postępu bez dodatkowego klikania Auto.

8. Anulowanie podglądu nie pozostawia aktywnego pobierania danych.

#### Scenariusze weryfikacji

<a id="t091-c01"></a>

##### T091-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Zaznaczono 1, 3 i 4.

**Działanie:** Zatwierdź podgląd.

**Oczekiwany rezultat:** Intent obejmuje dokładnie te epizody.

**Niedopuszczalny skutek:** Nie pobrano 2 przez automatyczny zakres 1–4.

**Docelowy test:** `tests/automation/test_release_picker_ui.py::test_release_picker_ui_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t091-c02"></a>

##### T091-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik przesuwa kursor strzałkami.

**Działanie:** Sprawdź mutacje.

**Oczekiwany rezultat:** Nie powstaje download intent.

**Niedopuszczalny skutek:** Nie użyto nawigacji jako zatwierdzenia.

**Docelowy test:** `tests/automation/test_release_picker_ui.py::test_release_picker_ui_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t091-c03"></a>

##### T091-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Lista odświeżyła się przed zatwierdzeniem.

**Działanie:** Wykonaj Enter.

**Oczekiwany rezultat:** Wybrane ID są ponownie zweryfikowane.

**Niedopuszczalny skutek:** Nie użyto nowej zawartości starego numeru wiersza.

**Docelowy test:** `tests/automation/test_release_picker_ui.py::test_release_picker_ui_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t091-c04"></a>

##### T091-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik naciska Esc w podglądzie.

**Działanie:** Wróć do listy.

**Oczekiwany rezultat:** Nie uruchomiono danych torrenta.

**Niedopuszczalny skutek:** Nie trzeba anulować ukrytego transferu po wyjściu.

**Docelowy test:** `tests/automation/test_release_picker_ui.py::test_release_picker_ui_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_release_picker_ui.py
```

**Wycofanie:** Wyłącz jedynie nową akcję startu; zapisany wybór może pozostać jako draft bez skutków zewnętrznych.

**Podstawa techniczna:** [S07](research.md#s07), [S09](research.md#s09), [S20](research.md#s20).

<a id="t092"></a>

### T092. Dodaj prosty ekran obserwowania serii

**Status:** planned.

**Cel:** Zapis subskrypcji wymaga jednego zrozumiałego podsumowania, a nie formularza z dziesiątkami przypadkowych ustawień.

**Wymagania:** [R06](spec.md#r06), [R09](spec.md#r09), [R10](spec.md#r10), [R18](spec.md#r18), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T091](#t091)

**Kolejność planowa:** T092; poprzednia karta: T091.

**Kontrakt / symbol:** `SubscriptionController`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/automation_schedule.py`
- `tests/automation/test_subscription_ui.py`

**Istotna granica:** Domyślne ustawienia ograniczają pytania, ale nie zastępują decyzji o niewiadomej numeracji.

#### Kolejność implementacji

1. Pokaż tytuł/sezon, następny do zdobycia, grupę, minimum jakości i wybrany preset.

2. Główne tryby to Na bieżąco oraz Zbierz do późniejszego oglądania; szczegóły limitów są na drugim poziomie.

3. Nie pytaj ponownie o dane już wybrane w ekranie serii lub paczki.

4. Gdy numeracja jest niejednoznaczna, pokaż dwa konkretne przykłady i jedną decyzję mapowania.

5. Enter na Obserwuj zapisuje command z podsumowanym zakresem; Esc odrzuca draft.

6. Po zapisie od razu pokaż następny check i status worker/client.

7. Pauza i zmiana grup są akcjami wiersza z jasnym wpływem na przyszłą pracę.

8. Nie rób z dostępności kalendarza warunku otwarcia lub zapisania serii.

#### Scenariusze weryfikacji

<a id="t092-c01"></a>

##### T092-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Seria i grupa zostały wcześniej wybrane.

**Działanie:** Otwórz subskrypcję.

**Oczekiwany rezultat:** Są już wypełnione.

**Niedopuszczalny skutek:** Nie zadano ponownie tych samych pytań.

**Docelowy test:** `tests/automation/test_subscription_ui.py::test_subscription_ui_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t092-c02"></a>

##### T092-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Nieznany offset numeracji.

**Działanie:** Otwórz potwierdzenie.

**Oczekiwany rezultat:** Widać konkretne przykłady do zatwierdzenia.

**Niedopuszczalny skutek:** Nie pokazano enigmatycznego błędu mapowania.

**Docelowy test:** `tests/automation/test_subscription_ui.py::test_subscription_ui_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t092-c03"></a>

##### T092-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Worker nie jest uruchomiony.

**Działanie:** Zapisz subskrypcję.

**Oczekiwany rezultat:** Reguła jest trwała, UI wyjaśnia brak bieżącej pracy.

**Niedopuszczalny skutek:** Nie udaje natychmiastowo aktywnego nadzoru.

**Docelowy test:** `tests/automation/test_subscription_ui.py::test_subscription_ui_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t092-c04"></a>

##### T092-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Anulowano draft.

**Działanie:** Wróć do wyszukiwania.

**Oczekiwany rezultat:** Nie powstała aktywna subskrypcja.

**Niedopuszczalny skutek:** Nie zapisano połowy formularza jako zgody na pobieranie.

**Docelowy test:** `tests/automation/test_subscription_ui.py::test_subscription_ui_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_subscription_ui.py
```

**Wycofanie:** Wycofaj kontroler subskrypcji; zapisane reguły pozostają widoczne przez CLI i bibliotekę.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S18](research.md#s18).

<a id="t093"></a>

### T093. Pokaż Gotowe i Oglądaj w jednym widoku

**Status:** planned.

**Cel:** Gotowy odcinek można znaleźć i uruchomić bez przeglądania dziesiątek plików pośrednich.

**Wymagania:** [R11](spec.md#r11), [R14](spec.md#r14), [R15](spec.md#r15), [R21](spec.md#r21), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T092](#t092)

**Kolejność planowa:** T093; poprzednia karta: T092.

**Kontrakt / symbol:** `AutomationLibraryController`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/automation_library.py`
- `tests/automation/test_library_ui.py`

**Istotna granica:** Cały widok działa na lokalnym snapshot, bez requestów podczas renderowania.

#### Kolejność implementacji

1. Utwórz kontroler listy serii/epizodów z filtrami Gotowe, Wszystkie i Wymaga uwagi.

2. Wiersz epizodu pokazuje numer, status lektora, obejrzenie i aktywną rewizję.

3. Enter na gotowym produkcie otwiera jawne Oglądaj lub bezpośrednio odtwarzanie zgodnie z jednym opisanym stanem.

4. Akcję Obejrzane pokaż jako osobną od Oglądaj, z zachowaniem jawnego wyboru.

5. W szczegółach udostępnij oryginał, polskie napisy, audio i finalny kontener jako różne role.

6. Zachowaj cursor/scroll po aktualizacji snapshotu; End przywraca śledzenie tylko zgodnie z opisem danego widoku.

7. Pokaż _unsorted i akcję Przypisz serię bez blokowania odtwarzania.

8. Brak playera i brak produktu mają różne komunikaty oraz działania naprawcze.

#### Scenariusze weryfikacji

<a id="t093-c01"></a>

##### T093-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Epizod kończy się podczas oglądania listy.

**Działanie:** Odśwież snapshot.

**Oczekiwany rezultat:** Pojawia się Oglądaj bez powrotu do Home.

**Niedopuszczalny skutek:** Nie czeka na koniec reszty sezonu.

**Docelowy test:** `tests/automation/test_library_ui.py::test_library_ui_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t093-c02"></a>

##### T093-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik otwiera film.

**Działanie:** Odczytaj watch state.

**Oczekiwany rezultat:** Nie zmienia się automatycznie.

**Niedopuszczalny skutek:** Nie utożsamiono dwóch akcji.

**Docelowy test:** `tests/automation/test_library_ui.py::test_library_ui_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t093-c03"></a>

##### T093-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Wiersz jest partial z gotowym SRT.

**Działanie:** Otwórz szczegóły.

**Oczekiwany rezultat:** SRT jest dostępny, film nie udaje gotowego.

**Niedopuszczalny skutek:** Nie ukryto zachowanych produktów.

**Docelowy test:** `tests/automation/test_library_ui.py::test_library_ui_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t093-c04"></a>

##### T093-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nowe wpisy pojawiają się nad kursorem.

**Działanie:** Odśwież.

**Oczekiwany rezultat:** Wybór pozostaje na tym samym EpisodeKey.

**Niedopuszczalny skutek:** Nie uruchomiono innego odcinka po Enter.

**Docelowy test:** `tests/automation/test_library_ui.py::test_library_ui_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_library_ui.py
```

**Wycofanie:** Wycofaj nowe widoki biblioteki, pozostawiając same pliki i techniczne komendy read-only.

**Podstawa techniczna:** [S06](research.md#s06), [S07](research.md#s07), [S08](research.md#s08).

<a id="t094"></a>

### T094. Dołącz terminal do pracy workera bez przejmowania jej lifecycle

**Status:** planned.

**Cel:** Monitor pokazuje lokalną pracę, lecz jego zamknięcie nie jest anulowaniem pobierania i tłumaczenia.

**Wymagania:** [R11](spec.md#r11), [R14](spec.md#r14), [R17](spec.md#r17), [R25](spec.md#r25).

**Zależności obowiązkowe:** [T093](#t093)

**Kolejność planowa:** T094; poprzednia karta: T093.

**Kontrakt / symbol:** `AutomationProgressController`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/automation_progress.py`
- `anishift/cli/interactive/app.py`
- `tests/automation/test_progress_ui.py`

**Istotna granica:** Właścicielem wykonania jest worker; monitor jest tylko klientem poleceń i odczytu.

#### Kolejność implementacji

1. Utwórz widok monitorujący snapshot/events AutomationClient zamiast przechowywać właściciela RunSession.

2. Zachowaj jeden renderer i istniejący styl progress rows.

3. Wyświetl osobno źródła oczekujące, transfer, kopiowanie i aktualny etap rdzenia.

4. Jawny przycisk Anuluj zapisuje cancel_job; Esc lub zamknięcie monitor view wyłącznie odłącza widok.

5. Przy zamknięciu całego terminala odróżnij własny ręczny run od zewnętrznego workera.

6. Oznacz brak heartbeat jako rozłączony monitor, nie jako zakończenie wszystkich jobów.

7. Po reconnect wczytaj pełny snapshot i dopiero kolejne eventy.

8. Brak procentu pokazuj jako aktywność, a zakres pracy wielu odcinków jako liczniki, nie sztuczną średnią.

#### Scenariusze weryfikacji

<a id="t094-c01"></a>

##### T094-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Monitor jest zamykany podczas TTS.

**Działanie:** Odłącz UI.

**Oczekiwany rezultat:** Worker nadal wykonuje job.

**Niedopuszczalny skutek:** Nie wywołano AppService.cancel w procesie workera.

**Docelowy test:** `tests/automation/test_progress_ui.py::test_progress_ui_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t094-c02"></a>

##### T094-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Użytkownik wybiera Anuluj epizod.

**Działanie:** Wyślij command.

**Oczekiwany rezultat:** Anulowany jest dokładny job.

**Niedopuszczalny skutek:** Nie anulowano wszystkich odcinków.

**Docelowy test:** `tests/automation/test_progress_ui.py::test_progress_ui_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t094-c03"></a>

##### T094-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Heartbeat przestał się zmieniać.

**Działanie:** Renderuj.

**Oczekiwany rezultat:** Widać stan rozłączenia i ostatnią aktualizację.

**Niedopuszczalny skutek:** Nie pokazano fałszywie aktualnego czasu postępu.

**Docelowy test:** `tests/automation/test_progress_ui.py::test_progress_ui_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t094-c04"></a>

##### T094-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nowy monitor dołącza do trwającego transferu.

**Działanie:** Odczytaj snapshot.

**Oczekiwany rezultat:** Widok startuje z prawdziwego stanu.

**Niedopuszczalny skutek:** Nie dodaje ponownie tego samego torrenta.

**Docelowy test:** `tests/automation/test_progress_ui.py::test_progress_ui_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_progress_ui.py
```

**Wycofanie:** Wyłącz automatyczne otwieranie monitora, pozostawiając worker i ręczne dołączanie CLI.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S09](research.md#s09).

<a id="t095"></a>

### T095. Zamień niejasne błędy na pojedyncze działania naprawcze

**Status:** planned.

**Cel:** Lista Wymaga uwagi pomaga doprowadzić odcinek do gotowości bez ręcznego grzebania w bazie.

**Wymagania:** [R07](spec.md#r07), [R19](spec.md#r19), [R23](spec.md#r23), [R25](spec.md#r25), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T094](#t094)

**Kolejność planowa:** T095; poprzednia karta: T094.

**Kontrakt / symbol:** `AttentionController`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/automation_library.py`
- `anishift/cli/interactive/automation_schedule.py`
- `tests/automation/test_attention_ui.py`

**Istotna granica:** Akcja naprawcza nie daje dostępu do dowolnej powłoki ani edycji arbitralnego kodu aplikacji.

#### Kolejność implementacji

1. Zmapuj każdy znany error_code na konkretny panel lub akcję naprawy.

2. Brak napisów prowadzi do wyboru istniejącego tracka, sidecara albo innego wydania.

3. Mapping required pokazuje tytuł, numer z pliku i proponowane EpisodeKey do świadomego zatwierdzenia.

4. Disk full pokazuje wolne miejsce, szacunek i własne foldery, bez przycisku automatycznego kasowania wszystkiego.

5. Auth required otwiera istniejący mechanizm konfiguracji połączenia, nie pole echo hasła w logach.

6. Retry ponawia właściwy etap i zachowuje zaakceptowane produkty.

7. Wiele identycznych awarii jednego providera zgrupuj pod jednym powodem.

8. Nieznany kod ma bezpieczny opis i identyfikator diagnostyczny, bez tracebacku w głównym ekranie.

#### Scenariusze weryfikacji

<a id="t095-c01"></a>

##### T095-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Jedyny tekst to Signs & Songs.

**Działanie:** Otwórz uwagę.

**Oczekiwany rezultat:** Dostępny jest wybór poprawnego tekstu/innego źródła.

**Niedopuszczalny skutek:** Nie ma bezwarunkowego Ponów uruchamiającego ten sam błąd.

**Docelowy test:** `tests/automation/test_attention_ui.py::test_attention_ui_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t095-c02"></a>

##### T095-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** 15 jobów ma błąd połączenia klienta.

**Działanie:** Pokaż listę.

**Oczekiwany rezultat:** Widoczna jest jedna grupowa przyczyna z dotkniętymi jobami.

**Niedopuszczalny skutek:** Nie zasypano użytkownika 15 identycznymi alertami.

**Docelowy test:** `tests/automation/test_attention_ui.py::test_attention_ui_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t095-c03"></a>

##### T095-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Brak miejsca na dysku.

**Działanie:** Otwórz szczegóły.

**Oczekiwany rezultat:** Pokazane są konkretne bajty i foldery.

**Niedopuszczalny skutek:** Nie ma ukrytej destrukcyjnej autoretencji.

**Docelowy test:** `tests/automation/test_attention_ui.py::test_attention_ui_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t095-c04"></a>

##### T095-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Naprawiono mapowanie jednego epizodu.

**Działanie:** Ponów job.

**Oczekiwany rezultat:** Tylko ta operacja wraca do kolejki.

**Niedopuszczalny skutek:** Nie zresetowano wszystkich subskrypcji.

**Docelowy test:** `tests/automation/test_attention_ui.py::test_attention_ui_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_attention_ui.py
```

**Wycofanie:** Wycofaj nowy panel naprawczy, pozostawiając bezpieczne kody błędów i read-only szczegóły.

**Podstawa techniczna:** [S07](research.md#s07), [S14](research.md#s14), [S20](research.md#s20).

<a id="t096"></a>

### T096. Sprawdź klawiaturę, resize i brak I/O w renderze

**Status:** planned.

**Cel:** Nowe panele nie psują przewijania, wklejania i dotychczasowej responsywności terminala Windows.

**Wymagania:** [R02](spec.md#r02), [R14](spec.md#r14), [R25](spec.md#r25), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T095](#t095)

**Kolejność planowa:** T096; poprzednia karta: T095.

**Kontrakt / symbol:** `_NORMALISED_KEYS / TerminalRenderer`.

#### Pliki i zakres edycji

- `anishift/cli/interactive/prompts.py`
- `tests/automation/test_terminal_contracts.py`

**Istotna granica:** Pomiar Windows i akceptacja człowieka pozostają odrębne od testów modelu widoku.

#### Kolejność implementacji

1. Użyj istniejącej _NORMALISED_KEYS, dopisując nowe klawisze wyłącznie tam, jeśli są potrzebne.

2. Przetestuj strzałki, Enter, Space, Esc, PageUp/PageDown, Home/End oraz BracketedPaste.

3. Zmiana rozmiaru terminala koryguje okno widoku i nie zmienia wybranego rekordu.

4. Każdy wiersz jest obcinany do szerokości komórek terminala, z zachowaniem Unicode.

5. W renderze zablokuj wywołania sieci, DB write i subprocess przez testowe boundary spies.

6. Opóźnione wyniki trafiają do kontrolerów przez kolejkę bez uruchamiania drugiego event loop renderer.

7. Przeprowadź manualny Windows Terminal check z niskim oknem i dużą biblioteką.

8. Porównaj zmierzony czas reakcji i bezczynność z baseline przed wpisaniem budżetu wydajności do wyniku.

#### Scenariusze weryfikacji

<a id="t096-c01"></a>

##### T096-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Biblioteka przewinięta, potem resize do niskiego okna.

**Działanie:** Renderuj ponownie.

**Oczekiwany rezultat:** Wybór pozostaje ten sam i mieści się poprawne okno listy.

**Niedopuszczalny skutek:** Nie zmienił się zaznaczony odcinek.

**Docelowy test:** `tests/automation/test_terminal_contracts.py::test_keyboard_geometry_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t096-c02"></a>

##### T096-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** W renderze wykonano testowy hook HTTP.

**Działanie:** Uruchom test kontraktu.

**Oczekiwany rezultat:** Test wykrywa naruszenie boundary.

**Niedopuszczalny skutek:** Nie uznano blokującego renderu za poprawny.

**Docelowy test:** `tests/automation/test_terminal_contracts.py::test_keyboard_geometry_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t096-c03"></a>

##### T096-C03

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** Windows wysyła klawisz specjalny z pustym data.

**Działanie:** Obsłuż binding.

**Oczekiwany rezultat:** Klawisz ma własną poprawną nazwę.

**Niedopuszczalny skutek:** Nie został zlepiony z Keys.Any.

**Rekord dowodu:** `T096-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t096-c04"></a>

##### T096-C04

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** Terminal wrócił po reconnect monitora.

**Działanie:** Sprawdź ekran i klawisze.

**Oczekiwany rezultat:** Jest jeden właściciel alternate screen.

**Niedopuszczalny skutek:** Nie pozostawiono drugiego Live lub ukrytego renderera.

**Rekord dowodu:** `T096-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_terminal_contracts.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Przywróć ostatni działający routing/geometry nowego panelu; nie przebudowuj równocześnie maskotki i całego stylu UI.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S09](research.md#s09).

<a id="p12"></a>

## P12. Windows: start przy logowaniu i monitor postępu

**Status fazy:** superseded-by: [plans/01-watch-mode.md](plans/01-watch-mode.md). Karty poniżej pozostają historią projektu; nie są kolejką wykonania.

Karty T tej fazy usunięto przed pierwszym commitem pakietu, bo zastąpił je Plan 01; nie były kolejką wykonania.

<a id="p13"></a>
## P13. Preferencje, import MAL, diagnostyka i obsługa wyjątków

**Wynik fazy:** Lokalny setup i naprawy wyjątków są zrozumiałe.

**Wejście:** P11/P12: kompletne ścieżki użytkowe.

**Warunek wyjścia:** Sekrety nie wyciekają; MAL XML ma podgląd; doctor niczego sam nie instaluje ani nie kasuje.

**Status fazy:** planned.

<a id="t105"></a>

### T105. Przygotuj jednorazowy lokalny setup

**Status:** planned.

**Cel:** Właściciel wybiera kilka rzeczy raz, a nie uzupełnia konfigurację co odcinek.

**Wymagania:** [R01](spec.md#r01), [R08](spec.md#r08), [R13](spec.md#r13), [R24](spec.md#r24), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T104](#t104)

**Kolejność planowa:** T105; poprzednia karta: T104.

**Kontrakt / symbol:** `AutomationSetupController`.

#### Pliki i zakres edycji

- `anishift/cli/automation.py`
- `anishift/cli/interactive/automation_schedule.py`
- `tests/automation/test_setup_flow.py`

**Istotna granica:** Konfiguracja kont i systemu następuje dopiero podczas wdrożenia, nie w trakcie tworzenia tego pakietu.

#### Kolejność implementacji

1. Pokaż aktualnie wykryty interpreter, stan rdzenia i wybrany media_root.

2. Zapytaj tylko o brakujące: folder, połączenie klienta, player, autostart i tryb monitora.

3. Preferowane grupy mogą zostać neutralne do pierwszego wyboru serii; nie wymagaj ich globalnie.

4. Wykonaj walidację lokalnych rootów i budżetu miejsca przed zapisaniem.

5. Zapisz konfigurację atomowo, a mutacje systemowe wykonaj dopiero po osobnym podsumowaniu zgody.

6. Nie czytaj ani nie pokazuj istniejących prywatnych promptów i kluczy jako części setupu.

7. Pozwól zakończyć setup w trybie tylko lokalnego importu przy braku qBittorrent.

8. Na końcu pokaż dwie próby użytkowe: wrzuć testowy plik i wyszukaj serię, z rzeczywistym stanem dostępnych integracji.

#### Scenariusze weryfikacji

<a id="t105-c01"></a>

##### T105-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Wszystkie dane są już zapisane.

**Działanie:** Otwórz setup.

**Oczekiwany rezultat:** Nie pyta ponownie o te same pola.

**Niedopuszczalny skutek:** Nie resetuje preferencji.

**Docelowy test:** `tests/automation/test_setup_flow.py::test_setup_flow_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t105-c02"></a>

##### T105-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Brak klienta torrent.

**Działanie:** Zakończ tryb importu.

**Oczekiwany rezultat:** Watcher i lokalny Auto mogą działać.

**Niedopuszczalny skutek:** Nie blokuje całego programu przez brak download backendu.

**Docelowy test:** `tests/automation/test_setup_flow.py::test_setup_flow_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t105-c03"></a>

##### T105-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Właściciel nie zgadza się na autostart.

**Działanie:** Zapisz wybór.

**Oczekiwany rezultat:** Nie powstaje zadanie Windows.

**Niedopuszczalny skutek:** Nie traktuje samego uruchomienia setupu jako zgody.

**Docelowy test:** `tests/automation/test_setup_flow.py::test_setup_flow_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t105-c04"></a>

##### T105-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Setup przerwano przed potwierdzeniem.

**Działanie:** Uruchom ponownie.

**Oczekiwany rezultat:** Nie ma częściowej mutacji systemowej.

**Niedopuszczalny skutek:** Nie pozostaje zadanie z błędną ścieżką.

**Docelowy test:** `tests/automation/test_setup_flow.py::test_setup_flow_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_setup_flow.py
```

**Wycofanie:** Przywróć poprzedni rekord ustawień i usuń tylko własne nowo utworzone zadanie autostartu po sprawdzeniu ownership.

**Podstawa techniczna:** [S02](research.md#s02), [S20](research.md#s20), [S35](research.md#s35).

<a id="t106"></a>

### T106. Rozszerz istniejącą konfigurację połączenia bez wycieku sekretów

**Status:** planned.

**Cel:** Login klienta torrent nie trafia do SQLite, receiptów, logów ani eksportu diagnostycznego.

**Wymagania:** [R23](spec.md#r23), [R26](spec.md#r26), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T105](#t105)

**Kolejność planowa:** T106; poprzednia karta: T105.

**Kontrakt / symbol:** `Settings.qbittorrent_credentials`.

#### Pliki i zakres edycji

- `anishift/config/settings.py`
- `anishift/automation/config.py`
- `anishift/cli/interactive/automation_schedule.py`
- `tests/automation/test_connection_secrets.py`

**Istotna granica:** Plan nie odczytuje ani nie zmienia rzeczywistych credentials użytkownika.

#### Kolejność implementacji

1. Dodaj ANISHIFT_QBITTORRENT_USERNAME, ANISHIFT_QBITTORRENT_PASSWORD oraz niesekretny lokalizator ANISHIFT_AUTOMATION_STATE_ROOT w istniejącym mechanizmie Settings; root jest lokalizatorem bazy, nie wartością odkrywaną dopiero z niej.

2. W automation preferences przechowuj wyłącznie URL oraz credential reference, nie wartości poświadczeń.

3. Użyj istniejącej fasady do zapisu .env i maskowanego edytora, po odczytaniu jej aktualnego kontraktu.

4. Nie pokazuj sekretu przy ponownym otwieraniu panelu; pokaż jedynie skonfigurowane/nieustawione.

5. Zmiana hasła odświeża sesję adaptera przy kolejnej bezpiecznej próbie, bez resetu biblioteki.

6. Connection probe loguje tylko host, wersję i bezpieczny kod odpowiedzi.

7. Sprawdź testem negatywnym wszystkie serializacje profilu, task XML, snapshot i diagnostic export.

8. Nie dodawaj nowego własnego szyfrowania lub magazynu kont do funkcji, która może użyć istniejących ustawień.

#### Scenariusze weryfikacji

<a id="t106-c01"></a>

##### T106-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Skonfigurowano hasło klienta.

**Działanie:** Zapisz preferencje i receipt.

**Oczekiwany rezultat:** Hasło występuje wyłącznie w wybranym istniejącym magazynie konfiguracji.

**Niedopuszczalny skutek:** Nie znalazło się w state.sqlite3.

**Docelowy test:** `tests/automation/test_connection_secrets.py::test_connection_secrets_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t106-c02"></a>

##### T106-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Probe zgłasza błąd uwierzytelnienia.

**Działanie:** Wyeksportuj diagnostykę.

**Oczekiwany rezultat:** Nie ma hasła ani surowych headers.

**Niedopuszczalny skutek:** Nie zapisano całego wyjątku SDK.

**Docelowy test:** `tests/automation/test_connection_secrets.py::test_connection_secrets_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t106-c03"></a>

##### T106-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Hasło zostało zmienione.

**Działanie:** Wznów adapter.

**Oczekiwany rezultat:** Powstaje nowa sesja z poprawnym credential.

**Niedopuszczalny skutek:** Nie wymaga ponownego dodania serii.

**Docelowy test:** `tests/automation/test_connection_secrets.py::test_connection_secrets_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t106-c04"></a>

##### T106-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Otworzono panel ponownie.

**Działanie:** Renderuj pole.

**Oczekiwany rezultat:** Sekret jest zamaskowany i nie jest automatycznie kopiowany do clipboard.

**Niedopuszczalny skutek:** Nie wyświetla wartości w TUI.

**Docelowy test:** `tests/automation/test_connection_secrets.py::test_connection_secrets_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_connection_secrets.py
```

**Wycofanie:** Usuń wyłącznie nowe pola po jawnej decyzji użytkownika; nie naruszaj istniejących kluczy LLM/TTS.

**Podstawa techniczna:** [S02](research.md#s02), [S03](research.md#s03), [S07](research.md#s07).

<a id="t107"></a>

### T107. Dodaj bezpieczny import eksportu XML MyAnimeList

**Status:** planned.

**Cel:** Własna lista może zasilić wybór tytułów bez niezweryfikowanego OAuth i bez automatycznego zapisywania historii na koncie.

**Wymagania:** [R03](spec.md#r03), [R21](spec.md#r21), [R22](spec.md#r22), [R26](spec.md#r26).

**Zależności obowiązkowe:** [T106](#t106)

**Kolejność planowa:** T107; poprzednia karta: T106.

**Kontrakt / symbol:** `MalXmlImporter.parse`.

#### Pliki i zakres edycji

- `anishift/automation/providers/mal.py`
- `tests/automation/test_mal_xml.py`

**Istotna granica:** Format eksportu wymaga fixture z rzeczywistego eksportu właściciela podczas wdrożenia; konto i lista nie zostały odczytane w tym badaniu.

#### Kolejność implementacji

1. Przyjmij lokalny plik eksportu MAL wybrany przez użytkownika; nie pobieraj prywatnej listy bez dostępu.

2. Użyj defusedxml, ograniczenia rozmiaru i liczby rekordów oraz walidacji wymaganych pól.

3. Odczytaj series_animedb_id, series_title, my_status i my_watched_episodes jako osobne dane źródłowe.

4. Nie wymagaj pełnego bieżącego API MAL, którego dokumentacji nie udało się zweryfikować w badaniu.

5. Pokaż podgląd Watching i Plan to Watch z możliwością zaznaczenia konkretnych pozycji do dalszego mapowania.

6. Nie zapisuj wyników do MAL i nie twórz subskrypcji dla wszystkich rekordów z eksportu.

7. Zachowaj datę eksportu/odczytu i oznacz te informacje jako snapshot, nie live sync.

8. Ponowny import scala po MAL ID i pokazuje różnice, zamiast mnożyć wpisy tytułów.

#### Scenariusze weryfikacji

<a id="t107-c01"></a>

##### T107-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Poprawny eksport z Watching i Plan to Watch.

**Działanie:** Wczytaj.

**Oczekiwany rezultat:** Tytuły i licznik obejrzenia są widoczne jako snapshot.

**Niedopuszczalny skutek:** Nie zaczyna się automatyczne pobieranie wszystkich pozycji.

**Docelowy test:** `tests/automation/test_mal_xml.py::test_mal_xml_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t107-c02"></a>

##### T107-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** XML zawiera DTD lub za dużo danych.

**Działanie:** Parsuj.

**Oczekiwany rezultat:** Import jest odrzucony bez odczytu plików zewnętrznych.

**Niedopuszczalny skutek:** Nie użyto niebezpiecznego fallbacku parsera.

**Docelowy test:** `tests/automation/test_mal_xml.py::test_mal_xml_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t107-c03"></a>

##### T107-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Rekord nie ma prawidłowego MAL ID.

**Działanie:** Wczytaj listę.

**Oczekiwany rezultat:** Wadliwy wpis jest oznaczony/pominięty z powodem.

**Niedopuszczalny skutek:** Nie dopisano fikcyjnego ID na podstawie tytułu.

**Docelowy test:** `tests/automation/test_mal_xml.py::test_mal_xml_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t107-c04"></a>

##### T107-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Ten sam eksport zaimportowano ponownie.

**Działanie:** Scal.

**Oczekiwany rezultat:** Nie powstają duplikaty tytułów ani subskrypcji.

**Niedopuszczalny skutek:** Nie zmieniono lokalnych stanów watched bez decyzji.

**Docelowy test:** `tests/automation/test_mal_xml.py::test_mal_xml_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_mal_xml.py
```

**Wycofanie:** Usuń wyłącznie niezaakceptowany import snapshot; nie zmieniaj konta MAL ani istniejącej biblioteki.

**Podstawa techniczna:** [S28](research.md#s28), [S32](research.md#s32), [S39](research.md#s39), [S40](research.md#s40).

<a id="t108"></a>

### T108. Powiąż wybór z MAL z canonical ID i lokalnym zakresem

**Status:** planned.

**Cel:** Import listy może skrócić wybór anime, ale nie ma zgody na zgadywanie sezonu lub falsyfikowanie obejrzanych odcinków.

**Wymagania:** [R03](spec.md#r03), [R04](spec.md#r04), [R09](spec.md#r09), [R21](spec.md#r21), [R22](spec.md#r22).

**Zależności obowiązkowe:** [T107](#t107)

**Kolejność planowa:** T108; poprzednia karta: T107.

**Kontrakt / symbol:** `map_mal_snapshot`.

#### Pliki i zakres edycji

- `anishift/automation/providers/mal.py`
- `anishift/automation/catalog.py`
- `tests/automation/test_mal_mapping.py`

**Istotna granica:** Automatyczny zapis do MAL jest świadomie poza tym zakresem; nie jest ukrytym brakującym krokiem krytycznej automatyzacji.

#### Kolejność implementacji

1. Powiąż MAL ID z AniList idMal przez sprawdzony endpoint katalogu albo zaproponuj lokalny rekord przy braku sieci.

2. Przy konflikcie kilku kandydatów wymagaj konkretnego wyboru, zachowując źródłowy MAL ID.

3. Pokaż osobno Licznik z eksportu MAL i Lokalnie oznaczone obejrzane.

4. Jednorazowy import historii oglądania wymaga jawnego zatwierdzenia oraz poprawnego mapowania regularnych epizodów.

5. Nie traktuj my_watched_episodes jako następnego epizodu do pobrania; użytkownik może chcieć zebrać wcześniejsze odcinki.

6. Przycisk Obserwuj otwiera normalne podsumowanie subskrypcji z grupą, jakością i zakresem.

7. Brak pełnego aktualnego kontraktu OAuth oznacza brak outbound sync w tym wdrożeniu; nie kopiuj client_id/password grant z anipy.

8. Dodaj bezpieczne Otwórz MAL dla konkretnego ID jako opcjonalną jawną akcję użytkownika.

#### Scenariusze weryfikacji

<a id="t108-c01"></a>

##### T108-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Eksport mówi watched=8, użytkownik chce pobrać od 1.

**Działanie:** Zbuduj zakres.

**Oczekiwany rezultat:** Subskrypcja może zaczynać się od 1.

**Niedopuszczalny skutek:** Nie narzucono automatycznie odcinka 9.

**Docelowy test:** `tests/automation/test_mal_mapping.py::test_mal_mapping_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t108-c02"></a>

##### T108-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** MAL ID pasuje do jednego media idMal.

**Działanie:** Powiąż.

**Oczekiwany rezultat:** Tożsamość jest zgodna i zachowana.

**Niedopuszczalny skutek:** Nie oparto mapowania tylko na tytule.

**Docelowy test:** `tests/automation/test_mal_mapping.py::test_mal_mapping_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t108-c03"></a>

##### T108-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Dane tytułu są niejednoznaczne.

**Działanie:** Zaakceptuj import.

**Oczekiwany rezultat:** Potrzebny jest wybór sezonu.

**Niedopuszczalny skutek:** Nie skopiowano cudzych danych konta lub client_id.

**Docelowy test:** `tests/automation/test_mal_mapping.py::test_mal_mapping_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t108-c04"></a>

##### T108-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Zatwierdzono jednorazowy import watch history.

**Działanie:** Zastosuj.

**Oczekiwany rezultat:** Lokalny stan ma jawne pochodzenie snapshotu.

**Niedopuszczalny skutek:** Nie wykonano żadnej mutacji sieciowej na koncie MAL.

**Docelowy test:** `tests/automation/test_mal_mapping.py::test_mal_mapping_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_mal_mapping.py
```

**Wycofanie:** Cofnij lokalne powiązanie/import history przez jawną korektę; nie wymaga to zmiany czegokolwiek na koncie MAL.

**Podstawa techniczna:** [S17](research.md#s17), [S28](research.md#s28), [S39](research.md#s39), [S40](research.md#s40).

<a id="t109"></a>

### T109. Rozszerz doctor o lokalną automatyzację

**Status:** planned.

**Cel:** Diagnostyka wskazuje konkretną niesprawną część bez wykonywania pobrania, TTS lub naprawy na ślepo.

**Wymagania:** [R13](spec.md#r13), [R23](spec.md#r23), [R24](spec.md#r24), [R28](spec.md#r28), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T108](#t108)

**Kolejność planowa:** T109; poprzednia karta: T108.

**Kontrakt / symbol:** `AutomationDoctor.run`.

#### Pliki i zakres edycji

- `anishift/cli/automation.py`
- `anishift/automation/worker.py`
- `tests/automation/test_doctor.py`

**Istotna granica:** Doctor opisuje i sprawdza, a nie automatycznie naprawia dowolny problem.

#### Kolejność implementacji

1. Sprawdź wersję schematu, integralność odczytu DB, worker.lock i świeżość heartbeat.

2. Zweryfikuj rozdzielenie rootów, dostęp zapisu i wolne miejsce bez tworzenia mediów użytkownika.

3. Pokaż konfigurację client URL i capabilities bez poświadczeń.

4. Probe sieciowy wykonuj tylko po jawnej akcji; zwykłe otwarcie ekranu nie może wywoływać providerów.

5. Sprawdź task Windows, executable, arguments i state_root, nie tylko istnienie nazwy zadania.

6. Sprawdź lokalizację mpv i istniejących narzędzi rdzenia przez ich istniejące mechanizmy.

7. Wynik każdego testu opisuj PASS/FAIL/UNKNOWN/SKIPPED z konkretnym dowodem i podpowiedzią.

8. Nie wywołuj automatycznej instalacji, usuwania cache, zmiany kont lub kill procesu jako części samego doctor.

#### Scenariusze weryfikacji

<a id="t109-c01"></a>

##### T109-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Worker heartbeat jest stary, baza czytelna.

**Działanie:** Uruchom doctor.

**Oczekiwany rezultat:** Rozróżnia sprawną bazę od nieaktywnego workera.

**Niedopuszczalny skutek:** Nie daje globalnego PASS.

**Docelowy test:** `tests/automation/test_doctor.py::test_doctor_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t109-c02"></a>

##### T109-C02

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** Task ma błędny cwd.

**Działanie:** Sprawdź autostart.

**Oczekiwany rezultat:** Wskazuje dokładną niezgodność.

**Niedopuszczalny skutek:** Nie uznaje samej nazwy taska za dowód działania.

**Rekord dowodu:** `T109-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t109-c03"></a>

##### T109-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Probe sieci nie został wybrany.

**Działanie:** Otwórz diagnostykę.

**Oczekiwany rezultat:** Status sieci jest UNKNOWN/SKIPPED bez requestów.

**Niedopuszczalny skutek:** Nie uruchamia testu API bez akcji.

**Docelowy test:** `tests/automation/test_doctor.py::test_doctor_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t109-c04"></a>

##### T109-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Błąd jest naprawiony przez użytkownika.

**Działanie:** Ponów pojedynczy test.

**Oczekiwany rezultat:** Aktualizuje się tylko odpowiedni wynik.

**Niedopuszczalny skutek:** Nie wykonuje całego długiego pipeline.

**Docelowy test:** `tests/automation/test_doctor.py::test_doctor_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_doctor.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Wycofaj nowe kontrole doctor; istniejąca diagnostyka rdzenia nadal działa i nie zmienia danych.

**Podstawa techniczna:** [S02](research.md#s02), [S07](research.md#s07), [S20](research.md#s20), [S35](research.md#s35).

<a id="t110"></a>

### T110. Wyeksportuj bezpieczny pakiet diagnostyczny

**Status:** planned.

**Cel:** Błąd da się zgłosić z wersjami i stanami bez ujawniania kluczy, prywatnych promptów lub treści anime.

**Wymagania:** [R23](spec.md#r23), [R26](spec.md#r26), [R27](spec.md#r27), [R30](spec.md#r30).

**Zależności obowiązkowe:** [T109](#t109)

**Kolejność planowa:** T110; poprzednia karta: T109.

**Kontrakt / symbol:** `build_diagnostic_export`.

#### Pliki i zakres edycji

- `anishift/automation/library.py`
- `anishift/cli/automation.py`
- `tests/automation/test_diagnostic_export.py`

**Istotna granica:** Żadne dane nie są wysyłane do chmury w obecnym zakresie.

#### Kolejność implementacji

1. Wybierz jawnie zakres diagnostyki: wersje, capabilities, error codes, stany i zanonimizowane ścieżki.

2. Nie dołączaj całej bazy, .env, prywatnych promptów, plików audio, napisów i pełnych logów jako domyślnego eksportu.

3. Użyj stabilnych pseudonimów ścieżek i tytułów w zewnętrznym raporcie, z opcją lokalnego podglądu.

4. Zachowaj daty, operation IDs i kolejność eventów potrzebną do analizy race.

5. Usuń query tokeny, cookies, headers, userinfo URL i stringi przypominające credentials.

6. Pokaż podgląd plików do eksportu i miejsce docelowe przed zapisaniem.

7. Zapisz wersję schematu raportu, aby późniejszy czytelnik znał kształt danych.

8. Nie wysyłaj raportu do żadnej usługi bez osobnej jawnej prośby.

#### Scenariusze weryfikacji

<a id="t110-c01"></a>

##### T110-C01

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Błąd SDK zawiera credential w URL.

**Działanie:** Zbuduj raport.

**Oczekiwany rezultat:** Credential jest usunięty.

**Niedopuszczalny skutek:** Nie wyeksportowano str(exc) bez filtracji.

**Docelowy test:** `tests/automation/test_diagnostic_export.py::test_diagnostic_export_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t110-c02"></a>

##### T110-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Baza ma prywatne tytuły i ścieżki.

**Działanie:** Eksportuj domyślnie.

**Oczekiwany rezultat:** Raport używa pseudonimów i nie zawiera pełnej bazy.

**Niedopuszczalny skutek:** Nie spakowano state.sqlite3 automatycznie.

**Docelowy test:** `tests/automation/test_diagnostic_export.py::test_diagnostic_export_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t110-c03"></a>

##### T110-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik anuluje podgląd eksportu.

**Działanie:** Zamknij panel.

**Oczekiwany rezultat:** Nie powstaje ani nie jest wysyłany raport.

**Niedopuszczalny skutek:** Nie wykonano niejawnego uploadu.

**Docelowy test:** `tests/automation/test_diagnostic_export.py::test_diagnostic_export_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t110-c04"></a>

##### T110-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Raport otwiera się po aktualizacji aplikacji.

**Działanie:** Odczytaj schema_version.

**Oczekiwany rezultat:** Kształt jest jednoznacznie rozpoznany.

**Niedopuszczalny skutek:** Nie pomylono starego raportu z bieżącym stanem.

**Docelowy test:** `tests/automation/test_diagnostic_export.py::test_diagnostic_export_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_diagnostic_export.py
```

**Wycofanie:** Usuń wyłącznie własny eksport po potwierdzeniu; nie kasuj źródłowych logów potrzebnych użytkownikowi.

**Podstawa techniczna:** [S02](research.md#s02), [S07](research.md#s07), [S34](research.md#s34).

<a id="t111"></a>

### T111. Utrwal zasady integracji i przypięte zależności

**Status:** planned.

**Cel:** Projekt korzysta z istniejących bibliotek, lecz nie opiera stabilności na automatycznym pobieraniu obcego kodu.

**Wymagania:** [R23](spec.md#r23), [R26](spec.md#r26), [R27](spec.md#r27), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T110](#t110)

**Kolejność planowa:** T111; poprzednia karta: T110.

**Kontrakt / symbol:** `IntegrationManifest`.

#### Pliki i zakres edycji

- `docs/work/local-automation/brief.md`
- `pyproject.toml`
- `uv.lock`
- `tests/automation/test_integration_configuration.py`

**Istotna granica:** Publiczne repozytorium nie oznacza braku warunków licencyjnych ani gwarancji utrzymania.

#### Kolejność implementacji

1. Zapisz wybrane wersje i linki do ich oficjalnych źródeł oraz status testu Windows.

2. Wydziel dokumentacyjnie: użyta biblioteka, referencja kodu oraz odrzucona większa aplikacja.

3. Nie pobieraj i nie wykonuj aktualizowanych pluginów qBittorrent z Internetu przy każdym starcie.

4. Zachowaj wymagane informacje licencyjne, jeśli wykonawca rzeczywiście przenosi fragment kodu; preferuj zależność albo własny cienki adapter kontraktu.

5. Dla AniList ogranicz pobieranie do zapytań użytkownika i subskrypcji; przed publiczną dystrybucją ponownie oceń warunki komplementarnego użycia.

6. Nie obiecuj nieprzerwanego działania RSS/HTML bez zmian adaptera.

7. Źródła pobierania konfiguruje użytkownik do materiałów, do których ma odpowiednie prawa; aplikacja nie omija zabezpieczeń.

8. Zmiana dostawcy lub zależności wymaga małego testu kontraktowego i aktualizacji locka, nie szerokiego upgrade całej aplikacji.

#### Scenariusze weryfikacji

<a id="t111-c01"></a>

##### T111-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Nowa wersja pluginu jest dostępna online.

**Działanie:** Uruchom aplikację.

**Oczekiwany rezultat:** Nie jest automatycznie pobrana i wykonana.

**Niedopuszczalny skutek:** Nie uruchomiono zdalnego kodu z indeksu.

**Docelowy test:** `tests/automation/test_integration_configuration.py::test_source_terms_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t111-c02"></a>

##### T111-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Aktualizacja dotyczy tylko parsera.

**Działanie:** Zmień zależność kontrolowanie.

**Oczekiwany rezultat:** Lock i test kontraktu odnoszą się do konkretnej wersji.

**Niedopuszczalny skutek:** Nie zaktualizowano wszystkich providerów LLM przy okazji.

**Rekord dowodu:** `T111-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t111-c03"></a>

##### T111-C03

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Cache katalogu próbuje pobrać całą bazę.

**Działanie:** Sprawdź granicę.

**Oczekiwany rezultat:** Operacja masowa nie należy do dostępnych use case.

**Niedopuszczalny skutek:** Nie utworzono konkurencyjnego mirroru danych.

**Docelowy test:** `tests/automation/test_integration_configuration.py::test_source_terms_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t111-c04"></a>

##### T111-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Adapter zmienił się po API drift.

**Działanie:** Odnów proof.

**Oczekiwany rezultat:** Udokumentowano nowy kontrakt i rzeczywisty test.

**Niedopuszczalny skutek:** Nie pozostawiono starego PASS jako dowodu nowej wersji.

**Rekord dowodu:** `T111-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_integration_configuration.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Przywróć lock i wyłącz niezgodny adapter; nie zmieniaj stanu użytkownika, aby wymusić zgodność nowego źródła.

**Podstawa techniczna:** [S18](research.md#s18), [S19](research.md#s19), [S21](research.md#s21), [S25](research.md#s25), [S27](research.md#s27), [S30](research.md#s30), [S31](research.md#s31).

<a id="t112"></a>

### T112. Domknij ustawienia bez mnożenia konfiguracji

**Status:** planned.

**Cel:** Każde ustawienie ma jednego właściciela zapisu, a zmiana preferencji nie rozjeżdża się między terminalem i workerem.

**Wymagania:** [R06](spec.md#r06), [R09](spec.md#r09), [R13](spec.md#r13), [R24](spec.md#r24), [R25](spec.md#r25), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T111](#t111)

**Kolejność planowa:** T112; poprzednia karta: T111.

**Kontrakt / symbol:** `update_preferences_if_version`.

#### Pliki i zakres edycji

- `anishift/automation/config.py`
- `anishift/cli/interactive/automation_schedule.py`
- `tests/automation/test_settings_scope.py`

**Istotna granica:** SQLite przechowuje trwały stan automatyzacji; nie zastępuje wszystkich istniejących ustawień aplikacji.

#### Kolejność implementacji

1. Preferencje automatyzacji utrzymuj w wersjonowanym rekordzie meta/preferences tej samej bazy.

2. Media root i state root zmieniaj wyłącznie w kontrolowanym setupie przy zatrzymanej pracy, nie podczas renderowania.

3. Preferencje grupy/jakości/zakresu przechowuj w konkretnej subskrypcji jako snapshot reguły.

4. Preset i ustawienia silników nadal zapisuje AppService, nie AutomationStore.

5. Zmiany z UI wysyłaj komendą z oczekiwaną wersją, wykrywając równoległą edycję z innego terminala.

6. Pokaż zakres resetu oraz zachowaj istniejące zasady ustawień: nawigacja nie zapisuje wartości.

7. Nie dodawaj drugiego settings.json w media_root ani kopii kluczy w bazie.

8. Domyślne wartości i granice liczb dokumentuj w jednym kontrakcie, a UI odczytuje je z modelu.

#### Scenariusze weryfikacji

<a id="t112-c01"></a>

##### T112-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Dwa terminale edytują tę samą regułę.

**Działanie:** Zapisz drugą starą wersję.

**Oczekiwany rezultat:** Powstaje konflikt do odświeżenia.

**Niedopuszczalny skutek:** Nie nadpisano nowszej decyzji ostatnim ślepym zapisem.

**Docelowy test:** `tests/automation/test_settings_scope.py::test_settings_scope_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t112-c02"></a>

##### T112-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Użytkownik przewija listę ustawień.

**Działanie:** Sprawdź stan.

**Oczekiwany rezultat:** Nie następuje żadna mutacja.

**Niedopuszczalny skutek:** Nie zmieniono wartości od samej nawigacji.

**Docelowy test:** `tests/automation/test_settings_scope.py::test_settings_scope_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t112-c03"></a>

##### T112-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Próba zmiany media_root podczas aktywnego copy.

**Działanie:** Zatwierdź.

**Oczekiwany rezultat:** Wymagana jest kontrolowana pauza/migracja.

**Niedopuszczalny skutek:** Nie przeniesiono katalogu w trakcie zapisu.

**Docelowy test:** `tests/automation/test_settings_scope.py::test_settings_scope_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t112-c04"></a>

##### T112-C04

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** Reset automatyzacji.

**Działanie:** Zastosuj podsumowany zakres.

**Oczekiwany rezultat:** Nie zmienia kluczy, głosów i prywatnych promptów rdzenia.

**Niedopuszczalny skutek:** Nie zresetowano całej aplikacji.

**Docelowy test:** `tests/automation/test_settings_scope.py::test_settings_scope_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_settings_scope.py
```

**Wycofanie:** Przywróć wcześniejszą wersję rekordów preferencji; nie cofaj niezależnych ustawień rdzenia ani klientów.

**Podstawa techniczna:** [S02](research.md#s02), [S03](research.md#s03), [S07](research.md#s07), [S34](research.md#s34).

<a id="p14"></a>

## P14. Integracyjne scenariusze awarii i codzienna praca

**Wynik fazy:** Codzienne scenariusze i awarie mają powtarzalny dowód.

**Wejście:** P03–P13: wszystkie funkcje połączone.

**Warunek wyjścia:** E2E z mediami syntetycznymi, 15 seriami, restartami i awariami przechodzi; stubs są jawnie oznaczone.

**Status fazy:** planned.

<a id="t113"></a>

### T113. Sprawdź pełny przepływ wyszukania jednego odcinka

**Status:** planned.

**Cel:** Pierwszy end-to-end potwierdza cały rezultat, nie tylko to, że wyszukiwarka zwróciła wiersz.

**Wymagania:** [R03](spec.md#r03), [R04](spec.md#r04), [R05](spec.md#r05), [R06](spec.md#r06), [R07](spec.md#r07), [R08](spec.md#r08), [R11](spec.md#r11), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T112](#t112), [T040](#t040), [T064](#t064)

**Kolejność planowa:** T113; poprzednia karta: T112.

**Kontrakt / symbol:** `test_end_to_end_single`.

#### Pliki i zakres edycji

- `tests/automation/test_e2e_single.py`
- `docs/work/local-automation/proofs/e2e.md`

**Istotna granica:** Ten E2E ze stubami nie jest dowodem działania żywego Nyaa, AniList ani TTS.

#### Kolejność implementacji

1. Użyj syntetycznej serii, indeksu fixture i legalnego krótkiego MKV z pełnym tekstem.

2. Przejdź przez kontroler search, wybór serii, regułę wydania i zatwierdzenie download intent.

3. Stub klienta odwzorowuje add, metadane, postęp, completion i rzeczywistą ścieżkę lokalnego pliku.

4. Przekaż ukończone źródło przez kontrolowaną kopię do prawdziwego AppService z zastubowanymi providerami sieciowymi.

5. Sprawdź fizyczne polskie produkty i poprawną projekcję ready w bibliotece.

6. Uruchom bezpieczny stub playera z dokładnym finalnym produktem.

7. Porównaj watched_at przed i po odtwarzaniu; ma się zmienić dopiero po osobnej akcji.

8. Zapisz, które granice były prawdziwe, a które symulowane, oraz użyty SHA.

#### Scenariusze weryfikacji

<a id="t113-c01"></a>

##### T113-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Kompletna syntetyczna ścieżka single episode.

**Działanie:** Wykonaj całe use case.

**Oczekiwany rezultat:** Powstaje gotowy polski film i jedno przyjęcie.

**Niedopuszczalny skutek:** Nie zakończono dowodu na samym wyniku search.

**Docelowy test:** `tests/automation/test_e2e_single.py::test_e2e_single_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t113-c02"></a>

##### T113-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Dwa identyczne zatwierdzenia download.

**Działanie:** Przejdź cały proces.

**Oczekiwany rezultat:** Powstaje jeden transfer i jedno wykonanie.

**Niedopuszczalny skutek:** Nie dublują się koszty TTS.

**Docelowy test:** `tests/automation/test_e2e_single.py::test_e2e_single_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t113-c03"></a>

##### T113-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wybrane wydanie ma tylko słabą jakość.

**Działanie:** Przejdź workflow.

**Oczekiwany rezultat:** Odmowa następuje przed tłumaczeniem.

**Niedopuszczalny skutek:** Nie przeszło niespełniające minimum źródło.

**Docelowy test:** `tests/automation/test_e2e_single.py::test_e2e_single_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t113-c04"></a>

##### T113-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** UI zostało odłączone po zatwierdzeniu.

**Działanie:** Dokończ workerem.

**Oczekiwany rezultat:** Produkt nadal powstaje i jest widoczny po reconnect.

**Niedopuszczalny skutek:** Nie zależy od żyjącego terminala.

**Docelowy test:** `tests/automation/test_e2e_single.py::test_e2e_single_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_e2e_single.py
```

**Wycofanie:** Usuń tylko syntetyczny katalog testowy; nie czyść workspace użytkownika ani jego klienta torrent.

**Podstawa techniczna:** [S03](research.md#s03), [S06](research.md#s06), [S20](research.md#s20), [S43](research.md#s43).

<a id="t114"></a>

### T114. Sprawdź sezon i natychmiastową dostępność pierwszego wyniku

**Status:** planned.

**Cel:** Pierwszy film jest gotowy do oglądania, gdy reszta sezonu dopiero się pobiera lub przetwarza.

**Wymagania:** [R08](spec.md#r08), [R10](spec.md#r10), [R11](spec.md#r11), [R15](spec.md#r15), [R19](spec.md#r19), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T113](#t113)

**Kolejność planowa:** T114; poprzednia karta: T113.

**Kontrakt / symbol:** `test_end_to_end_batch`.

#### Pliki i zakres edycji

- `tests/automation/test_e2e_batch.py`
- `docs/work/local-automation/proofs/e2e.md`

**Istotna granica:** Próba rzeczywistego klienta z T003 uzupełnia ten test domenowy, a nie jest przez niego zastąpiona.

#### Kolejność implementacji

1. Zbuduj paczkę z kilkoma małymi plikami o różnych ukończeniach, w tym jednym SPECIAL i próbką.

2. Przejdź przez manifest, wybór konkretnych file_index i przypisanie EpisodeKey.

3. Ukończ pierwszy plik, pozostaw drugi częściowy i sprawdź rozpoczęcie pierwszego AppService run.

4. Po publikacji pierwszego sprawdź Oglądaj przed ukończeniem drugiego.

5. Potwierdź osobne katalogi rewizji oraz nienaruszoną strukturę downloads.

6. Dodaj multi-episode file i upewnij się, że wykonywany jest jeden job dla coverage.

7. Wstrzymaj jeden uszkodzony plik, zachowując niezależny postęp pozostałych.

8. Zapisz zdarzenia czasu logicznego pokazujące brak bariery całej paczki.

#### Scenariusze weryfikacji

<a id="t114-c01"></a>

##### T114-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Pierwszy plik pełny, drugi niepełny.

**Działanie:** Przeprowadź E2E.

**Oczekiwany rezultat:** Pierwszy jest playable zanim drugi się zakończy.

**Niedopuszczalny skutek:** Nie użyto warunku kompletnego torrenta dla całego workflow.

**Docelowy test:** `tests/automation/test_e2e_batch.py::test_e2e_batch_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t114-c02"></a>

##### T114-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Paczkę wybrano z luką w numerach.

**Działanie:** Przygotuj wyniki.

**Oczekiwany rezultat:** Luka jest widoczna, nie pobrana domyślnie.

**Niedopuszczalny skutek:** Nie rozszerzono wyboru na pełny zakres.

**Docelowy test:** `tests/automation/test_e2e_batch.py::test_e2e_batch_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t114-c03"></a>

##### T114-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Jeden MKV jest uszkodzony.

**Działanie:** Dokończ pozostałe.

**Oczekiwany rezultat:** Pozostałe produkty powstają niezależnie.

**Niedopuszczalny skutek:** Nie anulowano całego sezonu.

**Docelowy test:** `tests/automation/test_e2e_batch.py::test_e2e_batch_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t114-c04"></a>

##### T114-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Restart między ukończeniem kolejnych plików.

**Działanie:** Wznów.

**Oczekiwany rezultat:** Każdy plik ma dokładnie jedno przyjęcie.

**Niedopuszczalny skutek:** Nie powtórzono TTS dla gotowej części.

**Docelowy test:** `tests/automation/test_e2e_batch.py::test_e2e_batch_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_e2e_batch.py
```

**Wycofanie:** Zakończ wyłącznie testowe operacje i zachowaj raport; nie zatrzymuj prywatnych transferów.

**Podstawa techniczna:** [S06](research.md#s06), [S20](research.md#s20), [S21](research.md#s21).

<a id="t115"></a>

### T115. Sprawdź drop-folder bez otwartego AniShift TUI

**Status:** planned.

**Cel:** Wrzucenie pliku naprawdę uruchamia całą pracę i wymagany postęp, bez trzech kolejnych Enter.

**Wymagania:** [R07](spec.md#r07), [R12](spec.md#r12), [R13](spec.md#r13), [R14](spec.md#r14), [R16](spec.md#r16), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T114](#t114)

**Kolejność planowa:** T115; poprzednia karta: T114.

**Kontrakt / symbol:** `test_end_to_end_drop`.

#### Pliki i zakres edycji

- `tests/automation/test_e2e_watch.py`
- `docs/work/local-automation/proofs/windows.md`

**Istotna granica:** Test best-effort musi opisać ograniczenie dotyczące przyszłego ponownego otwarcia pliku przez zewnętrznego producenta.

#### Kolejność implementacji

1. Uruchom worker w testowej konfiguracji i zamknij monitor.

2. Dodaj plik najpierw jako .part, później atomowo zmień nazwę na .mkv.

3. Dołącz polski sidecar w oknie gotowości i sprawdź pominięcie tłumaczenia.

4. Wykonaj oddzielną próbę zwykłego kopiowania Explorerem z aktywnym writerem.

5. Sprawdź, że pojawia się najwyżej jedno okno postępu zgodne z monitor_mode.

6. Zamknij to okno i sprawdź dalsze wykonanie oraz brak natychmiastowego ponownego otwarcia.

7. Zapisz gotowe produkty oraz nietknięty oryginał inbox.

8. Powtórz z tym samym źródłem, aby udowodnić deduplikację watch/manual intake.

#### Scenariusze weryfikacji

<a id="t115-c01"></a>

##### T115-C01

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** TUI zamknięte, worker aktywny, plik atomowo ukończony.

**Działanie:** Wykonaj drop.

**Oczekiwany rezultat:** Job uruchamia się bez ręcznego Auto.

**Niedopuszczalny skutek:** Nie wymaga otwartego Home.

**Rekord dowodu:** `T115-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t115-c02"></a>

##### T115-C02

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** Explorer nadal kopiuje duży testowy plik.

**Działanie:** Obserwuj.

**Oczekiwany rezultat:** Nie rozpoczyna się TTS z niepełnego pliku.

**Niedopuszczalny skutek:** Nie oparto startu wyłącznie na chwilowym rozmiarze.

**Rekord dowodu:** `T115-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t115-c03"></a>

##### T115-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Polski sidecar przychodzi razem z MKV.

**Działanie:** Wykonaj pipeline.

**Oczekiwany rezultat:** Tłumacz nie jest wywołany.

**Niedopuszczalny skutek:** Nie pominięto dobrych polskich napisów.

**Docelowy test:** `tests/automation/test_e2e_watch.py::test_e2e_watch_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t115-c04"></a>

##### T115-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Ten sam plik zostaje dodany ponownie.

**Działanie:** Obserwuj kolejkę.

**Oczekiwany rezultat:** Zwracany jest istniejący produkt.

**Niedopuszczalny skutek:** Nie powstaje drugie okno i drugi TTS bez nowego profilu.

**Docelowy test:** `tests/automation/test_e2e_watch.py::test_e2e_watch_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_e2e_watch.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Wyłącz watcher i zamknij własny worker testowy; oryginalne pliki użytkownika nie biorą udziału w próbie.

**Podstawa techniczna:** [S03](research.md#s03), [S11](research.md#s11), [S35](research.md#s35), [S37](research.md#s37).

<a id="t116"></a>

### T116. Sprawdź 15 subskrypcji i długi okres offline

**Status:** planned.

**Cel:** Przykładowy tydzień użytkownika da się odtworzyć deterministycznie, bez zużywania setek realnych requestów AI.

**Wymagania:** [R09](spec.md#r09), [R10](spec.md#r10), [R17](spec.md#r17), [R18](spec.md#r18), [R24](spec.md#r24), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T115](#t115)

**Kolejność planowa:** T116; poprzednia karta: T115.

**Kontrakt / symbol:** `test_fifteen_subscriptions`.

#### Pliki i zakres edycji

- `tests/automation/test_e2e_season.py`
- `docs/work/local-automation/proofs/scale.md`

**Istotna granica:** To test skali modelu pracy, nie dowód szybkości renderowania 180 prawdziwych filmów.

#### Kolejność implementacji

1. Utwórz 15 syntetycznych serii, po 12 znanych epizodów, z różnymi godzinami i regułami grup.

2. Użyj kontrolowanego zegara zamiast rzeczywistego czekania tygodnia.

3. Zasymuluj bieżące wydania, opóźnienie preferowanej grupy, serię zakończoną i brak kalendarza.

4. Wyłącz worker logicznie na siedem dni, następnie uruchom catch-up z krótkim feedem i historią.

5. Policz requesty hostów, liczbę aktywnych transferów i zewnętrznych wykonań rdzenia.

6. Sprawdź backlog limit oraz priorytet ręcznie wskazanego następnego odcinka.

7. Media większości scenariusza mogą być stubowane; rzeczywiste małe media sprawdza oddzielny E2E.

8. Raportuj rzeczywistą liczbę duplikatów, zgubionych celów i ręcznych interwencji, nie ocenę 10/10.

#### Scenariusze weryfikacji

<a id="t116-c01"></a>

##### T116-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** 15 serii z cotygodniowymi wydaniami.

**Działanie:** Przesuń zegar o tydzień.

**Oczekiwany rezultat:** Każdy znany pasujący epizod jest rozpatrzony raz.

**Niedopuszczalny skutek:** Nie pomnożono feed requestów przez wszystkie wiersze.

**Docelowy test:** `tests/automation/test_e2e_season.py::test_e2e_season_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t116-c02"></a>

##### T116-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Jedna seria nie ma kalendarza.

**Działanie:** Przeprowadź tydzień.

**Oczekiwany rezultat:** Działa fallback sprawdzania indeksu.

**Niedopuszczalny skutek:** Nie przestaje być obserwowana.

**Docelowy test:** `tests/automation/test_e2e_season.py::test_e2e_season_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t116-c03"></a>

##### T116-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Komputer offline przez 7 dni.

**Działanie:** Wykonaj catch-up.

**Oczekiwany rezultat:** Zachowany jest budżet i historyczne wyszukiwanie luk.

**Niedopuszczalny skutek:** Nie giną wydania tylko dlatego, że wypadły z RSS.

**Docelowy test:** `tests/automation/test_e2e_season.py::test_e2e_season_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t116-c04"></a>

##### T116-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Dysk osiąga limit przy backlogu.

**Działanie:** Kontynuuj symulację.

**Oczekiwany rezultat:** Nowy backlog czeka, gotowe odcinki można oglądać.

**Niedopuszczalny skutek:** Nie kasuje się nic automatycznie.

**Docelowy test:** `tests/automation/test_e2e_season.py::test_e2e_season_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_e2e_season.py
```

**Wycofanie:** Usuń tylko syntetyczną bazę scenariusza; pomiar nie może wykorzystywać prywatnej listy lub rzeczywistych 180 odcinków.

**Podstawa techniczna:** [S16](research.md#s16), [S18](research.md#s18), [S20](research.md#s20), [S33](research.md#s33).

<a id="t117"></a>

### T117. Przetestuj awarie w granicach commit i skutków zewnętrznych

**Status:** planned.

**Cel:** Każda ważna luka między bazą a filesystemem lub klientem ma konkretny scenariusz recovery.

**Wymagania:** [R16](spec.md#r16), [R17](spec.md#r17), [R20](spec.md#r20), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T116](#t116)

**Kolejność planowa:** T117; poprzednia karta: T116.

**Kontrakt / symbol:** `test_crash_recovery_matrix`.

#### Pliki i zakres edycji

- `tests/automation/test_crash_matrix.py`
- `docs/work/local-automation/proofs/recovery.md`

**Istotna granica:** Test crash jest odrębny od kontrolowanego cancel i musi obejmować granice atomowości.

#### Kolejność implementacji

1. Wstrzyknij przerwanie po zapisie intentu przed add oraz po add przed zapisem odpowiedzi.

2. Wstrzyknij przerwanie w środku kopii i po atomic rename przed commitem jobs.

3. Wstrzyknij przerwanie po publikacji polskiego tekstu oraz po finalnym MKV przed aktualizacją ready.

4. Wstrzyknij utratę procesu podczas zmiany priorytetów manifestu paczki.

5. Uruchom nowego testowego workera na tej samej bazie i katalogach.

6. Sprawdź brak duplikatów, zachowanie oryginałów, zgodność produktów i generacji eventów.

7. Nie zabijaj procesów użytkownika; fault injection obejmuje wyłącznie utworzony testowy PID.

8. Zapisz macierz oczekiwanych i rzeczywistych stanów dla każdej granicy awarii.

#### Scenariusze weryfikacji

<a id="t117-c01"></a>

##### T117-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Crash po add przed zapisem hasha.

**Działanie:** Wznów.

**Oczekiwany rezultat:** Transfer zostaje odnaleziony, nie dodany ponownie.

**Niedopuszczalny skutek:** Nie powstaje drugi efekt zewnętrzny.

**Docelowy test:** `tests/automation/test_crash_matrix.py::test_crash_matrix_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t117-c02"></a>

##### T117-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Crash po rename kopii.

**Działanie:** Wznów.

**Oczekiwany rezultat:** Kopia jest rozpoznana albo bezpiecznie zweryfikowana.

**Niedopuszczalny skutek:** Nie użyto niepełnego stagingu jako filmu.

**Docelowy test:** `tests/automation/test_crash_matrix.py::test_crash_matrix_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t117-c03"></a>

##### T117-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Crash po publikacji finalnego produktu.

**Działanie:** Wznów.

**Oczekiwany rezultat:** Produkt przechodzi walidację przed odzyskanym ready.

**Niedopuszczalny skutek:** Nie uruchamia się bez potrzeby ponownie cały pipeline.

**Docelowy test:** `tests/automation/test_crash_matrix.py::test_crash_matrix_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t117-c04"></a>

##### T117-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Crash podczas wyboru plików paczki.

**Działanie:** Wznów.

**Oczekiwany rezultat:** Manifest zostaje uzgodniony przed startem danych.

**Niedopuszczalny skutek:** Nie włączono domyślnie wszystkich plików.

**Docelowy test:** `tests/automation/test_crash_matrix.py::test_crash_matrix_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_crash_matrix.py
```

**Wycofanie:** Przy niespełnionym inwariancie zatrzymaj wdrożenie danej ścieżki i zachowaj testową bazę jako dowód; nie naprawiaj przez jej usunięcie.

**Podstawa techniczna:** [S06](research.md#s06), [S11](research.md#s11), [S20](research.md#s20), [S33](research.md#s33), [S34](research.md#s34).

<a id="t118"></a>

### T118. Przetestuj awarie i zmiany odpowiedzi providerów

**Status:** planned.

**Cel:** Automatyzacja nie myli problemu sieciowego z faktem, że epizod nie istnieje.

**Wymagania:** [R18](spec.md#r18), [R23](spec.md#r23), [R24](spec.md#r24), [R27](spec.md#r27), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T117](#t117)

**Kolejność planowa:** T118; poprzednia karta: T117.

**Kontrakt / symbol:** `test_network_failure_matrix`.

#### Pliki i zakres edycji

- `tests/automation/test_network_matrix.py`
- `docs/work/local-automation/proofs/providers.md`

**Istotna granica:** Fail-closed dotyczy niepewnego pobrania, nie blokowania całej aplikacji.

#### Kolejność implementacji

1. Przygotuj odpowiedzi 401, 403, 404, 429, 500, timeout, connection refused oraz HTTP 200 z challenge HTML.

2. Dodaj GraphQL partial data, błędny JSON, uszkodzony RSS i niekompletną listę plików klienta.

3. Wymuś Retry-After w sekundach i dacie HTTP oraz reset timestamp.

4. Sprawdź budżety, maksymalną liczbę prób i poprawny retry_scope.

5. Potwierdź, że lokalny intake i odtwarzanie działają podczas awarii każdego zewnętrznego źródła.

6. Po naprawie źródła sprawdź powrót z zachowanym cursorem i deduplikacją.

7. Sprawdź brak sekretów i surowych payloadów w komunikatach.

8. Żaden test nie może wymagać obchodzenia blokady hosta lub używania innych kont.

#### Scenariusze weryfikacji

<a id="t118-c01"></a>

##### T118-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** RSS zwraca challenge przy HTTP 200.

**Działanie:** Obsłuż.

**Oczekiwany rezultat:** Źródło jest niedostępne, nie puste.

**Niedopuszczalny skutek:** Nie ogłoszono braku nowych odcinków.

**Docelowy test:** `tests/automation/test_network_matrix.py::test_network_matrix_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t118-c02"></a>

##### T118-C02

**Rodzaj:** Test jednostkowy.

**Dane wejściowe:** 429 ma datę Retry-After w przyszłości.

**Działanie:** Wyznacz retry.

**Oczekiwany rezultat:** Nie ma wcześniejszego requestu.

**Niedopuszczalny skutek:** Nie ograniczono wsparcia wyłącznie do liczby sekund.

**Docelowy test:** `tests/automation/test_network_matrix.py::test_network_matrix_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t118-c03"></a>

##### T118-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Jedno źródło wraca po awarii.

**Działanie:** Wznów.

**Oczekiwany rezultat:** Nie gubi poprzednich wydań i nie dubluje jobów.

**Niedopuszczalny skutek:** Nie resetuje całej biblioteki.

**Docelowy test:** `tests/automation/test_network_matrix.py::test_network_matrix_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t118-c04"></a>

##### T118-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wszystkie źródła online niedostępne.

**Działanie:** Otwórz lokalny gotowy film.

**Oczekiwany rezultat:** Działa odtwarzanie i dostęp do plików.

**Niedopuszczalny skutek:** Nie blokuje głównego lokalnego rezultatu na sieci.

**Docelowy test:** `tests/automation/test_network_matrix.py::test_network_matrix_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_network_matrix.py
```

**Wycofanie:** Wyłącz niesprawny adapter i zachowaj zanonimizowane dowody; lokalny tryb pozostaje użyteczny.

**Podstawa techniczna:** [S16](research.md#s16), [S18](research.md#s18), [S20](research.md#s20), [S24](research.md#s24), [S32](research.md#s32).

<a id="t119"></a>

### T119. Przetestuj ochronę ścieżek, źródeł i sekretów

**Status:** planned.

**Cel:** Złośliwa nazwa pliku lub błędny endpoint nie może przejąć sterowania komputerem lub skasować biblioteki.

**Wymagania:** [R16](spec.md#r16), [R17](spec.md#r17), [R26](spec.md#r26), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T118](#t118)

**Kolejność planowa:** T119; poprzednia karta: T118.

**Kontrakt / symbol:** `test_safety_boundaries`.

#### Pliki i zakres edycji

- `tests/automation/test_safety_matrix.py`
- `docs/work/local-automation/proofs/safety.md`

**Istotna granica:** Kontrole chronią codzienny workflow; nie są deklaracją formalnego audytu bezpieczeństwa całego produktu.

#### Kolejność implementacji

1. Dodaj przypadki ../, absolute drive, UNC, reserved Windows names, junction i symlink.

2. Dodaj tytuły z ANSI escape, null bytes i bardzo długim Unicode.

3. Przygotuj XML entity expansion, przekierowanie do prywatnego hosta i odpowiedź przekraczającą limit.

4. Wymuś operacje na BORROWED torrent i cudzym staging markerze.

5. Sprawdź argv playera i startupu pod kątem shell injection oraz wycieku credentials.

6. Zablokuj przypadkowe hashes=all i deleteFiles=true na granicy adaptera.

7. Po testach porównaj digest oryginalnych źródeł i istnienie plików poza testowym rootem.

8. Raportuj realne sprawdzone przypadki; testy nie oznaczają gwarancji braku wszystkich podatności.

#### Scenariusze weryfikacji

<a id="t119-c01"></a>

##### T119-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Torrent próbuje utworzyć plik poza downloads.

**Działanie:** Zastosuj manifest.

**Oczekiwany rezultat:** Operacja jest odrzucona i plik poza rootem nie powstaje.

**Niedopuszczalny skutek:** Nie ograniczono ochrony do zamiany znaków tytułu.

**Docelowy test:** `tests/automation/test_safety_matrix.py::test_safety_matrix_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t119-c02"></a>

##### T119-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Cleanup widzi marker innego ownera.

**Działanie:** Wykonaj.

**Oczekiwany rezultat:** Obcy plik zostaje zachowany.

**Niedopuszczalny skutek:** Nie usuwa po samym prefiksie nazwy.

**Docelowy test:** `tests/automation/test_safety_matrix.py::test_safety_matrix_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t119-c03"></a>

##### T119-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Tytuł zawiera fragment polecenia shell.

**Działanie:** Uruchom player stub.

**Oczekiwany rezultat:** Jest traktowany wyłącznie jako dane ścieżki.

**Niedopuszczalny skutek:** Nie uruchomiono drugiego programu.

**Docelowy test:** `tests/automation/test_safety_matrix.py::test_safety_matrix_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t119-c04"></a>

##### T119-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Po pełnym scenariuszu porównano źródła.

**Działanie:** Oblicz digest.

**Oczekiwany rezultat:** Oryginały są identyczne.

**Niedopuszczalny skutek:** Nie nadpisano torrentowego pliku podczas tworzenia lektora.

**Docelowy test:** `tests/automation/test_safety_matrix.py::test_safety_matrix_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_safety_matrix.py
```

**Wycofanie:** W razie naruszenia zatrzymaj automatyczne mutacje i napraw konkretną granicę przed wdrożeniem; zachowaj dowód testowy.

**Podstawa techniczna:** [S02](research.md#s02), [S20](research.md#s20), [S32](research.md#s32), [S36](research.md#s36), [S37](research.md#s37).

<a id="t120"></a>

### T120. Zmierz rzeczywisty koszt nowych funkcji

**Status:** planned.

**Cel:** Nowe możliwości nie powinny degradować reakcji klawiatury ani zużywać stale CPU w bezczynności.

**Wymagania:** [R14](spec.md#r14), [R24](spec.md#r24), [R25](spec.md#r25), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T119](#t119)

**Kolejność planowa:** T120; poprzednia karta: T119.

**Kontrakt / symbol:** `measure_automation_overhead`.

#### Pliki i zakres edycji

- `tests/automation/test_performance_smoke.py`
- `docs/work/local-automation/proofs/performance.md`

**Istotna granica:** Progi czasowe w harmonogramie są ustawieniami, a wyniki wydajności powstają dopiero z pomiaru.

#### Kolejność implementacji

1. Zmierz baseline startup, idle CPU/RSS, reakcję klawiatury i odczyt biblioteki na tej samej maszynie.

2. Powtórz pomiar po zmianach z pustą bazą oraz 180 syntetycznymi epizodami.

3. Rozdziel koszt terminala, skanu inbox, poll klienta, hash kopii i realnego renderowania wideo.

4. Zapisz liczbę requestów w bezczynności i przy 15 subskrypcjach.

5. Zweryfikuj, że kopiowanie jest strumieniowe, eventy koalescowane, a zapytania biblioteki nie są N+1.

6. Nie uruchamiaj ciężkich rzeczywistych TTS dla wszystkich rekordów tylko w celu testu listy.

7. Przy regresji wskaż zmierzony wąski problem i popraw go bez zmiany architektury całego programu.

8. Budżet UX zaakceptuj na podstawie wyników i oceny właściciela; nie wpisuj zmyślonych osiągniętych milisekund.

#### Scenariusze weryfikacji

<a id="t120-c01"></a>

##### T120-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Biblioteka 180 rekordów, worker bezczynny.

**Działanie:** Zmierz odczyt i CPU.

**Oczekiwany rezultat:** Powstaje rzeczywisty raport i porównanie do baseline.

**Niedopuszczalny skutek:** Nie deklarowano wymyślonego czasu reakcji.

**Docelowy test:** `tests/automation/test_performance_smoke.py::test_performance_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t120-c02"></a>

##### T120-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Trwa kopiowanie większego pliku.

**Działanie:** Odczytaj snapshot i klawiaturę.

**Oczekiwany rezultat:** Nie blokują się na kopiowaniu.

**Niedopuszczalny skutek:** Nie użyto jednego wątku do wszystkich operacji.

**Docelowy test:** `tests/automation/test_performance_smoke.py::test_performance_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t120-c03"></a>

##### T120-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** 15 subskrypcji nic nowego nie znajduje.

**Działanie:** Policz requesty.

**Oczekiwany rezultat:** Wspólne cache i budżety ograniczają odczyty.

**Niedopuszczalny skutek:** Nie pobierano każdego feedu co klatkę.

**Docelowy test:** `tests/automation/test_performance_smoke.py::test_performance_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t120-c04"></a>

##### T120-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Po poprawce wąskiego gardła.

**Działanie:** Powtórz ten sam pomiar.

**Oczekiwany rezultat:** Wynik jest porównywalny i zapisany.

**Niedopuszczalny skutek:** Nie porównano różnych maszyn lub innych danych bez oznaczenia.

**Rekord dowodu:** `T120-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_performance_smoke.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Cofnij wyłącznie nieudane optymalizacje; nie zmieniaj modeli i jakości tłumaczenia, aby sztucznie poprawić metrykę.

**Podstawa techniczna:** [S07](research.md#s07), [S08](research.md#s08), [S12](research.md#s12), [S33](research.md#s33).

<a id="p15"></a>

## P15. Odbiór, dokumentacja, aktualizacja i przekazanie

**Wynik fazy:** Właściciel otrzymuje działające lokalne wdrożenie.

**Wejście:** P14 plus rzeczywisty Windows, klient i odsłuch.

**Warunek wyjścia:** Root gates, rzeczywiste kontrakty oraz odbiór człowieka są zapisane oddzielnie; dokumentacja wyłączenia i rollback działa.

**Status fazy:** planned.

<a id="t121"></a>

### T121. Uruchom pełne bramki repozytorium

**Status:** planned.

**Cel:** Pełny zakres nie jest uznany za dostarczony na podstawie samych nowych unit testów.

**Wymagania:** [R02](spec.md#r02), [R23](spec.md#r23), [R27](spec.md#r27), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T120](#t120)

**Kolejność planowa:** T121; poprzednia karta: T120.

**Kontrakt / symbol:** `RootGateReport`.

#### Pliki i zakres edycji

- `docs/work/local-automation/proofs/gates.md`
- `tests/automation/`

**Istotna granica:** Historyczne 3102 PASS i 30 smoke z załącznika nie są wynikiem tego wdrożenia.

#### Kolejność implementacji

1. Wykonaj uv run ruff check anishift/ tests/ z root repozytorium.

2. Wykonaj uv run ruff format --check anishift/ tests/ z root.

3. Wykonaj uv run mypy anishift/ tests/ bez dodatkowych lokalnych wyciszeń ukrywających błędy nowych granic.

4. Wykonaj uv run pytest, a nie tylko pytest tests/, aby objąć wymagane testy utils.

5. Zapisz dokładne polecenia, SHA, interpreter, platformę i rzeczywiste pass/fail/skip.

6. Uruchom oznaczone Windows/live testy oddzielnie zgodnie z dostępnym środowiskiem i zgodą.

7. Każdy skip opisz przyczyną oraz wpływem na funkcje; brak testu klienta nie oznacza gotowego downloadera.

8. Napraw regresje zakresu przed oznaczeniem technicznego zakończenia, nie zmieniając cudzych obszarów bez uzasadnienia.

#### Scenariusze weryfikacji

<a id="t121-c01"></a>

##### T121-C01

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Nowe testy przechodzą, lecz root pytest wykrywa regresję.

**Działanie:** Oceń status.

**Oczekiwany rezultat:** Całość nie jest oznaczona jako technicznie gotowa.

**Niedopuszczalny skutek:** Nie pominięto testów utils.

**Rekord dowodu:** `T121-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t121-c02"></a>

##### T121-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Windows testy nie były uruchomione.

**Działanie:** Zapisz wynik.

**Oczekiwany rezultat:** Są jawnie niewykonane, nie PASS.

**Niedopuszczalny skutek:** Nie zastąpiono ich Linux smoke.

**Rekord dowodu:** `T121-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t121-c03"></a>

##### T121-C03

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Mypy wykrywa błąd nowego DTO.

**Działanie:** Zamknij bramkę.

**Oczekiwany rezultat:** Błąd jest naprawiony zamiast globalnego ignore.

**Niedopuszczalny skutek:** Nie osłabiono strict konfiguracji projektu.

**Rekord dowodu:** `T121-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t121-c04"></a>

##### T121-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Po poprawce wykonano suite ponownie.

**Działanie:** Zaktualizuj proof.

**Oczekiwany rezultat:** Najnowszy wynik wskazuje właściwy SHA.

**Niedopuszczalny skutek:** Nie pozostawiono starego dowodu jako aktualnego.

**Rekord dowodu:** `T121-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Nie oznaczaj zadania done przy niezamkniętej bramce; wycofaj konkretną regresję lub pozostaw ją jawnie blokującą odbiór.

**Podstawa techniczna:** [S02](research.md#s02), [S10](research.md#s10), [S12](research.md#s12).

<a id="t122"></a>

### T122. Sprawdź czyste środowisko i brak ukrytych zależności

**Status:** planned.

**Cel:** Kolejny start po instalacji ma działać według instrukcji, a nie tylko na maszynie wykonawcy.

**Wymagania:** [R01](spec.md#r01), [R13](spec.md#r13), [R24](spec.md#r24), [R27](spec.md#r27), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T121](#t121)

**Kolejność planowa:** T122; poprzednia karta: T121.

**Kontrakt / symbol:** `CleanInstallProof`.

#### Pliki i zakres edycji

- `docs/work/local-automation/proofs/installation.md`
- `tests/automation/test_clean_install.py`

**Istotna granica:** Czysty Windows start jest bramką wdrożenia, nie deklaracją możliwą do potwierdzenia samą dokumentacją.

#### Kolejność implementacji

1. Odtwórz środowisko z uv.lock na obsługiwanym Windows i Python 3.14.

2. Uruchom istniejący mechanizm przygotowania binarek po wymaganej zgodzie, bez nieudokumentowanych ręcznych kroków.

3. Przejdź setup z nowym state_root i legalnym testowym media_root.

4. Potwierdź import czterech nowych bibliotek i wheel RapidFuzz dla tej platformy.

5. Sprawdź tryb lokalnego importu bez qBittorrent oraz pełny tryb z zatwierdzonym klientem.

6. Zapisz rzeczywiste kroki przygotowania credentials bez ich wartości.

7. Przetestuj uruchomienie z terminala oraz z własnego taska logowania.

8. Każdą dodatkową ręczną czynność, której wymagało środowisko, dopisz do instrukcji zamiast pomijać.

#### Scenariusze weryfikacji

<a id="t122-c01"></a>

##### T122-C01

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** Czyste środowisko z locka.

**Działanie:** Uruchom program.

**Oczekiwany rezultat:** Wszystkie zależności są odtwarzalne.

**Niedopuszczalny skutek:** Nie użyto globalnego przypadkowego pakietu.

**Rekord dowodu:** `T122-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t122-c02"></a>

##### T122-C02

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** Brak qBittorrent na maszynie.

**Działanie:** Uruchom lokalny import.

**Oczekiwany rezultat:** Działa podstawowa automatyzacja plików.

**Niedopuszczalny skutek:** Nie kończy się import error modułu downloadera.

**Rekord dowodu:** `T122-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t122-c03"></a>

##### T122-C03

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** RapidFuzz wheel ma brak runtime systemowego.

**Działanie:** Uruchom smoke.

**Oczekiwany rezultat:** Instrukcja wskazuje konkretny brak i rezultat naprawy.

**Niedopuszczalny skutek:** Nie twierdzi się, że instalacja jest kompletna.

**Rekord dowodu:** `T122-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t122-c04"></a>

##### T122-C04

**Rodzaj:** Próba na rzeczywistym Windows.

**Dane wejściowe:** Instalację odtworzono w innej ścieżce.

**Działanie:** Przejdź setup.

**Oczekiwany rezultat:** Task i baza wskazują nową instalację.

**Niedopuszczalny skutek:** Nie użyto zaszytej ścieżki wykonawcy.

**Rekord dowodu:** `T122-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_clean_install.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Usuń wyłącznie testowe środowisko i własne zadanie autostartu; nie zmieniaj prywatnej instalacji właściciela.

**Podstawa techniczna:** [S02](research.md#s02), [S10](research.md#s10), [S21](research.md#s21), [S30](research.md#s30), [S31](research.md#s31), [S35](research.md#s35).

<a id="t123"></a>

### T123. Powtórz małe próby rzeczywistych integracji

**Status:** planned.

**Cel:** Potwierdź, że realne kontrakty nie rozeszły się z fixture podczas implementacji.

**Wymagania:** [R07](spec.md#r07), [R08](spec.md#r08), [R11](spec.md#r11), [R18](spec.md#r18), [R23](spec.md#r23), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T122](#t122)

**Kolejność planowa:** T123; poprzednia karta: T122.

**Kontrakt / symbol:** `LiveIntegrationProof`.

#### Pliki i zakres edycji

- `docs/work/local-automation/proofs/live.md`
- `tests/automation/test_live_contracts.py`

**Istotna granica:** Testy żywych providerów nie zostały wykonane podczas tworzenia niniejszego pakietu dokumentów.

#### Kolejność implementacji

1. Po jawnej zgodzie wykonaj ograniczone odczyty AniList i Nyaa z bieżącymi adapterami.

2. Zweryfikuj rzeczywiste wersje qBittorrent i wrappera oraz metadata-only i selekcję plików.

3. Użyj własnego legalnego dwupilkowego torrenta lub przygotowanego kontrolowanego testu, nie prywatnego anime.

4. Przeprowadź jedno krótkie wywołanie skonfigurowanych istniejących providerów tłumaczenia/TTS tylko za zgodą właściciela.

5. Nie zapisuj request payloadów z tekstem prywatnych napisów ani wartości kluczy.

6. Porównaj wynik mediów z wymaganym produktem, a nie sam HTTP 200 providera.

7. Zapisz datę, wersje, ilość kontrolowanych prób i faktyczny rezultat; porażka nie jest ukrywana jako transient success.

8. W razie braku zgody lub dostępności pozostaw konkretną integrację unverified i nie nazywaj całego systemu bezawaryjnym.

#### Scenariusze weryfikacji

<a id="t123-c01"></a>

##### T123-C01

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Żywe RSS i GraphQL odpowiadają zgodnie ze schematem.

**Działanie:** Uruchom mały proof.

**Oczekiwany rezultat:** Adaptery tworzą poprawne DTO z realnych odpowiedzi.

**Niedopuszczalny skutek:** Nie uznano samych dokumentów za runtime proof.

**Rekord dowodu:** `T123-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t123-c02"></a>

##### T123-C02

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Wybrana para qBittorrent/API różni się od badanej.

**Działanie:** Sprawdź capability.

**Oczekiwany rezultat:** Wymagane funkcje są ponownie sprawdzone.

**Niedopuszczalny skutek:** Nie przyjęto zgodności z nazwy aplikacji.

**Rekord dowodu:** `T123-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t123-c03"></a>

##### T123-C03

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Dostawca TTS odmawia autoryzacji.

**Działanie:** Zapisz wynik.

**Oczekiwany rezultat:** Status jest unverified/failed i wskazuje konfigurację.

**Niedopuszczalny skutek:** Nie zastąpiono wyniku stubem podpisanym jako live.

**Rekord dowodu:** `T123-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t123-c04"></a>

##### T123-C04

**Rodzaj:** Ograniczona próba z rzeczywistą integracją.

**Dane wejściowe:** Po naprawie kontraktu ponowiono próbę.

**Działanie:** Porównaj proof.

**Oczekiwany rezultat:** Nowy dowód ma aktualny SHA i datę.

**Niedopuszczalny skutek:** Nie usunięto poprzedniego niepowodzenia z historii.

**Rekord dowodu:** `T123-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_live_contracts.py
```

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Wyłącz niesprawną integrację i pozostaw działające lokalne ścieżki; nie przełączaj na płatną usługę bez zgody.

**Podstawa techniczna:** [S16](research.md#s16), [S18](research.md#s18), [S20](research.md#s20), [S21](research.md#s21), [S24](research.md#s24).

<a id="t124"></a>

### T124. Przeprowadź odbiór według codziennego workflow właściciela

**Status:** planned.

**Cel:** Odbiór potwierdza, że program usuwa codzienne ręczne czynności, nie tylko spełnia testy jednostkowe.

**Wymagania:** [R01](spec.md#r01), [R08](spec.md#r08), [R09](spec.md#r09), [R11](spec.md#r11), [R12](spec.md#r12), [R13](spec.md#r13), [R14](spec.md#r14), [R15](spec.md#r15), [R21](spec.md#r21), [R27](spec.md#r27).

**Zależności obowiązkowe:** [T123](#t123)

**Kolejność planowa:** T124; poprzednia karta: T123.

**Kontrakt / symbol:** `OwnerAcceptance`.

#### Pliki i zakres edycji

- `docs/work/local-automation/proofs/acceptance.md`

**Istotna granica:** Odbiór służy realnej wygodzie; nie ma automatycznej oceny 10/10.

#### Kolejność implementacji

1. Właściciel wyszukuje wybraną serię i wybiera pojedynczy legalnie dostępny testowy odcinek bez strony torrentów.

2. Właściciel wybiera kilka plików paczki i otwiera pierwszy gotowy film przed zakończeniem pozostałych.

3. Przy zamkniętym TUI wrzuca gotowy plik do inbox i obserwuje jedno okno postępu.

4. Zamyka monitor podczas pracy i potwierdza później gotowy produkt.

5. Zapisuje subskrypcję oraz sprawdza jej następny termin i grupę bez kolejnych codziennych Enter.

6. Po ponownym logowaniu potwierdza worker, catch-up i zachowane dane.

7. Sprawdza odsłuchem oraz wzrokowo reprezentatywny krótki rezultat PL/EN, synchronizację i wybór ścieżki.

8. Zapisz uwagi właściciela i rozróżnij accepted, pending-human oraz rejected dla konkretnych zachowań.

#### Scenariusze weryfikacji

<a id="t124-c01"></a>

##### T124-C01

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Właściciel potwierdził wszystkie kluczowe scenariusze.

**Działanie:** Zapisz odbiór.

**Oczekiwany rezultat:** Status accepted ma faktyczny opis i datę.

**Niedopuszczalny skutek:** Nie wpisano zgody człowieka za niego.

**Rekord dowodu:** `T124-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t124-c02"></a>

##### T124-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Testy techniczne przechodzą, odsłuchu nie było.

**Działanie:** Zapisz status.

**Oczekiwany rezultat:** Pozostaje pending-human dla jakości.

**Niedopuszczalny skutek:** Nie ogłoszono pełnego odbioru audio.

**Rekord dowodu:** `T124-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t124-c03"></a>

##### T124-C03

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Monitor otwiera się ponownie mimo zamknięcia.

**Działanie:** Oceń zachowanie.

**Oczekiwany rezultat:** Odbiór tej funkcji jest odrzucony do naprawy.

**Niedopuszczalny skutek:** Nie zignorowano istotnego bólu użytkownika.

**Rekord dowodu:** `T124-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t124-c04"></a>

##### T124-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Po poprawce konkretnego problemu.

**Działanie:** Powtórz tylko odpowiedni scenariusz i potrzebne regresje.

**Oczekiwany rezultat:** Wynik jest zaktualizowany z dowodem.

**Niedopuszczalny skutek:** Nie żądano ponownie całego sezonu bez potrzeby.

**Rekord dowodu:** `T124-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Wyłącz konkretną niezaakceptowaną automatyczną funkcję bez usuwania plików; istniejące ręczne Auto pozostaje dostępne.

**Podstawa techniczna:** [S03](research.md#s03), [S06](research.md#s06), [S07](research.md#s07), [S35](research.md#s35).

<a id="t125"></a>

### T125. Napisz instrukcję użytkowania bez historii rozmowy

**Status:** planned.

**Cel:** Nowy użytkownik i następny agent mogą uruchomić, diagnozować oraz wyłączyć automatyzację bez tej rozmowy.

**Wymagania:** [R01](spec.md#r01), [R09](spec.md#r09), [R12](spec.md#r12), [R13](spec.md#r13), [R23](spec.md#r23), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T124](#t124)

**Kolejność planowa:** T125; poprzednia karta: T124.

**Kontrakt / symbol:** `OperatorGuide`.

#### Pliki i zakres edycji

- `docs/work/local-automation/README.md`
- `README.md`
- `anishift/cli/AGENTS.md`

**Istotna granica:** Dokumentacja jest po polsku; identyfikatory kodu i polecenia pozostają w języku projektu.

#### Kolejność implementacji

1. Opisz jednorazowy wybór qBittorrent, folderów, grup, playera, autostartu i trybu monitora.

2. Pokaż trzy główne drogi: znajdź i pobierz, obserwuj serię, wrzuć plik do inbox.

3. Wyjaśnij fizyczny layout biblioteki i różnicę między downloads, źródłem kopii i finalnym produktem.

4. Opisz ograniczenia: komputer musi działać, data emisji nie jest dostępnością wydania, best-effort watcher nie zna przyszłych zapisów.

5. Wyjaśnij local watched oraz import XML MAL bez deklarowania nieistniejącego live sync.

6. Podaj komendy status, monitor, check-now, pause, resume, stop oraz diagnostykę zgodną z implementacją.

7. Dokumentuj only verified capability i wersje; znane nieobsługiwane warianty pokaż wprost.

8. Nie przenoś wszystkich kontraktów do root README; linkuj krótki start do kanonicznych dokumentów tego workstreamu.

#### Scenariusze weryfikacji

<a id="t125-c01"></a>

##### T125-C01

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Czytelnik nie zna tej rozmowy.

**Działanie:** Wykonaj instrukcję startową.

**Oczekiwany rezultat:** Zna wszystkie potrzebne decyzje i polecenia.

**Niedopuszczalny skutek:** Nie ma odwołań typu zrób jak wcześniej.

**Rekord dowodu:** `T125-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t125-c02"></a>

##### T125-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Użytkownik chce tylko pliki lokalne.

**Działanie:** Czytaj odpowiednią ścieżkę.

**Oczekiwany rezultat:** Nie musi instalować klienta torrent ani łączyć MAL.

**Niedopuszczalny skutek:** Nie narzucono całego opcjonalnego setupu.

**Rekord dowodu:** `T125-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t125-c03"></a>

##### T125-C03

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Opis komendy różni się od Typer.

**Działanie:** Porównaj help.

**Oczekiwany rezultat:** Dokumentacja zostaje poprawiona.

**Niedopuszczalny skutek:** Nie pozostawiono fikcyjnego polecenia.

**Rekord dowodu:** `T125-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t125-c04"></a>

##### T125-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Aktualizacja zmieniła capabilities.

**Działanie:** Odnów dokument.

**Oczekiwany rezultat:** Wersja i ograniczenia odpowiadają najnowszemu proof.

**Niedopuszczalny skutek:** Nie zachowano starej obietnicy wsparcia.

**Rekord dowodu:** `T125-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Wycofaj tylko niezgodny opis nowej funkcji; historyczne dowody i instrukcje starego Auto zachowaj.

**Podstawa techniczna:** [S02](research.md#s02), [S07](research.md#s07), [S20](research.md#s20), [S35](research.md#s35).

<a id="t126"></a>

### T126. Sprawdź aktualizację, backup i wyłączenie całej funkcji

**Status:** planned.

**Cel:** Wdrożenie jest odwracalne bez utraty oryginałów, gotowych lektorów i stanu oglądania.

**Wymagania:** [R16](spec.md#r16), [R17](spec.md#r17), [R26](spec.md#r26), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T125](#t125)

**Kolejność planowa:** T126; poprzednia karta: T125.

**Kontrakt / symbol:** `UpgradeRollbackProof`.

#### Pliki i zakres edycji

- `docs/work/local-automation/proofs/rollback.md`
- `tests/automation/test_upgrade_rollback.py`

**Istotna granica:** Odwrócenie funkcji nie oznacza automatycznego usuwania danych użytkownika.

#### Kolejność implementacji

1. Przygotuj testową starszą bazę i bibliotekę z ready, pending, partial oraz paused subscription.

2. Wykonaj zweryfikowany backup i migrację z kontrolowanym zatrzymaniem writerów.

3. Porównaj counts i tożsamości epizodów, artifacts, commands oraz watched records.

4. Przetestuj wyłączenie autostartu, zatrzymanie workera i dalsze korzystanie z ręcznego Auto.

5. Przetestuj restore kopii przy zamkniętych writerach i późniejsze uzgodnienie klienta.

6. Nie wymagaj usuwania downloads/library podczas downgrade funkcji.

7. W razie niezgodnego schematu starsza aplikacja ma odmówić mutacji, a nie próbować naprawiać bazę.

8. Opisz w raporcie dokładne warunki powrotu oraz elementy świadomie zachowywane.

#### Scenariusze weryfikacji

<a id="t126-c01"></a>

##### T126-C01

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Baza zawiera aktywne i gotowe prace.

**Działanie:** Wykonaj upgrade.

**Oczekiwany rezultat:** Tożsamość oraz historyczne wyniki są zachowane.

**Niedopuszczalny skutek:** Nie wyzerowano watch state.

**Docelowy test:** `tests/automation/test_upgrade_rollback.py::test_upgrade_rollback_01`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t126-c02"></a>

##### T126-C02

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Starszy kod otwiera nowszy schemat.

**Działanie:** Uruchom.

**Oczekiwany rezultat:** Odmawia bezpiecznie mutacji.

**Niedopuszczalny skutek:** Nie wykonano destrukcyjnego downgrade.

**Docelowy test:** `tests/automation/test_upgrade_rollback.py::test_upgrade_rollback_02`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t126-c03"></a>

##### T126-C03

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Wyłączono automatyzację.

**Działanie:** Uruchom stare ręczne Auto.

**Oczekiwany rezultat:** Może nadal działać na legacy workspace.

**Niedopuszczalny skutek:** Nie zależy od aktywnego Task Scheduler.

**Docelowy test:** `tests/automation/test_upgrade_rollback.py::test_upgrade_rollback_03`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t126-c04"></a>

##### T126-C04

**Rodzaj:** Test integracyjny z kontrolowanymi komponentami.

**Dane wejściowe:** Restore sprzed części transferów.

**Działanie:** Uzgodnij.

**Oczekiwany rezultat:** Nowsze nieznane transfery pozostają nietknięte.

**Niedopuszczalny skutek:** Nie skasowano ich tylko dlatego, że nie ma ich w backupie.

**Docelowy test:** `tests/automation/test_upgrade_rollback.py::test_upgrade_rollback_04`.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Testy właściwe dla zmienionej granicy:

```bash
uv run pytest tests/automation/test_upgrade_rollback.py
```

**Wycofanie:** Przywróć wcześniej zweryfikowany backup wraz z kompatybilnym kodem i wyłącz autostart do zakończenia reconciliation.

**Podstawa techniczna:** [S02](research.md#s02), [S11](research.md#s11), [S20](research.md#s20), [S33](research.md#s33), [S34](research.md#s34), [S35](research.md#s35).

<a id="t127"></a>

### T127. Porównaj finalną implementację ze specyfikacją i decyzjami

**Status:** planned.

**Cel:** Pełny zakres lokalny nie może zakończyć się samym downloaderem, wyszukiwarką lub watcherem.

**Wymagania:** [R01](spec.md#r01), [R02](spec.md#r02), [R08](spec.md#r08), [R09](spec.md#r09), [R11](spec.md#r11), [R12](spec.md#r12), [R13](spec.md#r13), [R15](spec.md#r15), [R22](spec.md#r22), [R27](spec.md#r27), [R29](spec.md#r29).

**Zależności obowiązkowe:** [T126](#t126)

**Kolejność planowa:** T127; poprzednia karta: T126.

**Kontrakt / symbol:** `ScopeReview`.

#### Pliki i zakres edycji

- `docs/work/local-automation/proofs/review.md`
- `docs/work/local-automation/spec.md`

**Istotna granica:** Recenzja może być read-only; nie udawaj niezależnego audytu, jeśli przeprowadza ją ten sam wykonawca.

#### Kolejność implementacji

1. Przejdź po wymaganiach R01–R30 i wskaż konkretne zadania, testy oraz wynik odbioru.

2. Sprawdź wspólną historię wszystkich wejść oraz brak duplikatu schedulera rdzenia.

3. Sprawdź całe ścieżki single, batch, ongoing, backlog i local drop, a nie tylko obecność przycisków.

4. Potwierdź brak VPS, chmurowego uploadu, nowego GUI, autonomicznego agenta i nieuzgodnionego rewrite tłumacza.

5. Potwierdź jawny zakres MAL: import snapshotu i lokalny watch state, bez ukrytej obietnicy zapisu online.

6. Porównaj wykorzystane biblioteki i adaptery z technology brief, wyjaśniając każdą zmianę wersji lub wyboru.

7. Przejrzyj krytyczne awarie: częściowy plik, klient offline, quota, disk full, crash i konflikt numeracji.

8. Zapisz realne findings według istotności; brak live/Windows proof pozostaje widoczną luką odbioru.

#### Scenariusze weryfikacji

<a id="t127-c01"></a>

##### T127-C01

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Istnieje search i magnet add, ale brak subskrypcji.

**Działanie:** Oceń zakres.

**Oczekiwany rezultat:** Nie jest oznaczony jako pełne wdrożenie.

**Niedopuszczalny skutek:** Nie zamknięto celu po jednym pionowym wycinku.

**Rekord dowodu:** `T127-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t127-c02"></a>

##### T127-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Program czeka na cały batch przed TTS.

**Działanie:** Sprawdź R11.

**Oczekiwany rezultat:** Wymaganie jest odrzucone do naprawy.

**Niedopuszczalny skutek:** Nie zaakceptowano sprzecznego przepływu.

**Rekord dowodu:** `T127-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t127-c03"></a>

##### T127-C03

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Dokument obiecuje automatyczny MAL sync bez implementacji.

**Działanie:** Porównaj zakres.

**Oczekiwany rezultat:** Opis jest skorygowany i brak ujawniony.

**Niedopuszczalny skutek:** Nie ukryto fikcyjnej funkcji w README.

**Rekord dowodu:** `T127-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t127-c04"></a>

##### T127-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Wszystkie wymagania mają dowody lub jawne braki.

**Działanie:** Zapisz review.

**Oczekiwany rezultat:** Właściciel zna realny stan produktu.

**Niedopuszczalny skutek:** Nie zastąpiono oceny listą plików bez testów.

**Rekord dowodu:** `T127-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Nie zmieniaj statusów bez dowodów; niezaliczone zachowanie wraca do właściwego taska, nie do bezterminowej ogólnej polerki.

**Podstawa techniczna:** [S01](research.md#s01), [S02](research.md#s02), [S03](research.md#s03), [S06](research.md#s06), [S20](research.md#s20).

<a id="t128"></a>

### T128. Zapisz wynik i przekaż gotowy lokalny workflow

**Status:** planned.

**Cel:** Końcowe przekazanie opisuje faktycznie działający produkt, jego konfigurację i pozostające ograniczenia.

**Wymagania:** [R01](spec.md#r01), [R11](spec.md#r11), [R13](spec.md#r13), [R23](spec.md#r23), [R27](spec.md#r27), [R28](spec.md#r28).

**Zależności obowiązkowe:** [T127](#t127)

**Kolejność planowa:** T128; poprzednia karta: T127.

**Kontrakt / symbol:** `ImplementationOutcome`.

#### Pliki i zakres edycji

- `docs/work/local-automation/outcomes/local-automation.md`
- `docs/work/local-automation/README.md`

**Istotna granica:** W tym zadaniu planistycznym nie powstaje fikcyjny outcome implementacji.

#### Kolejność implementacji

1. Zapisz SHA wykonanej implementacji i zwięzłe zestawienie dostarczonych ścieżek użytkowych.

2. Dołącz rzeczywiste wyniki root gates, Windows, live oraz human acceptance jako oddzielne kategorie.

3. Zapisz wybrany klient i jego wersję, bez wartości credentials oraz prywatnych ścieżek w publicznym raporcie.

4. Wskaż miejsce konfiguracji, sposób otwarcia biblioteki, monitorowania, pauzy i wyłączenia autostartu.

5. Każdy nierozstrzygnięty element ma opis wpływu i konkretną akcję, nie ogólnik działa prawie wszystko.

6. Nie zapisuj outcomes przed rzeczywistą implementacją i testami; niniejszy pakiet jest planem, nie takim wynikiem.

7. Przekaż jedną spójną gałąź/PR zgodnie z instrukcjami repo, bez commitowania cudzych zmian.

8. Po zaakceptowaniu lokalnego rezultatu zakończ ten zakres; przyszły VPS/MAL live sync wymagają osobnej decyzji, nie ukrytego dopisywania.

#### Scenariusze weryfikacji

<a id="t128-c01"></a>

##### T128-C01

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Implementacja i testy są wykonane.

**Działanie:** Zbuduj outcome.

**Oczekiwany rezultat:** Zawiera rzeczywiste SHA i wyniki.

**Niedopuszczalny skutek:** Nie przepisano planned jako PASS.

**Rekord dowodu:** `T128-C01` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t128-c02"></a>

##### T128-C02

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Brakuje odsłuchu lub Windows logon proof.

**Działanie:** Zapisz końcowy status.

**Oczekiwany rezultat:** Odpowiednie funkcje pozostają pending-human/unverified.

**Niedopuszczalny skutek:** Nie ogłoszono bezawaryjnego pełnego odbioru.

**Rekord dowodu:** `T128-C02` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t128-c03"></a>

##### T128-C03

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** W repo są cudze zmiany.

**Działanie:** Przygotuj PR.

**Oczekiwany rezultat:** W PR znajdują się wyłącznie uzgodnione zmiany zakresu.

**Niedopuszczalny skutek:** Nie zacommitowano cudzej pracy.

**Rekord dowodu:** `T128-C03` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

<a id="t128-c04"></a>

##### T128-C04

**Rodzaj:** Przegląd lub próba odbiorowa człowieka.

**Dane wejściowe:** Właściciel chce zatrzymać czuwanie.

**Działanie:** Wykonaj instrukcję.

**Oczekiwany rezultat:** Może wyłączyć task i worker bez utraty biblioteki.

**Niedopuszczalny skutek:** Nie wymaga usunięcia aplikacji i mediów.

**Rekord dowodu:** `T128-C04` w raporcie odpowiedniej próby, po jej rzeczywistym wykonaniu.

**Stan dowodu:** niewykonany; opis stanowi kryterium odbioru.

#### Zakończenie zadania

Przypadki oznaczone live/Windows/manual wymagają własnego dowodu; samo uruchomienie pytest nie zamyka tych pozycji.

**Wycofanie:** Zatrzymaj wdrożenie i wyłącz nowe automatyczne uruchomienia, zachowując bibliotekę oraz dotychczasowe ręczne Auto.

**Podstawa techniczna:** [S01](research.md#s01), [S02](research.md#s02), [S06](research.md#s06), [S35](research.md#s35).

## 16. Zamknięcie całego zakresu

Zadanie T128 zamyka implementację dopiero po spełnieniu odbioru opisanych funkcji. Nie oznacza, że sam pakiet planistyczny dostarczył działający download lub autostart.

Nie przenosić VPS, pełnego live sync MAL, automatycznego OCR/ASR, nowego TUI ani drugiego schedulera do aktualnego zakresu pod nazwą „niezbędne przygotowanie”.

## Źródła kontraktu

[S01]: research.md#s01 "AniShift: przypięty commit"
[S02]: research.md#s02 "AniShift: instrukcje repozytorium"
[S03]: research.md#s03 "AniShift: fasada AppService"
[S04]: research.md#s04 "AniShift: discovery"
[S05]: research.md#s05 "AniShift: composition root"
[S06]: research.md#s06 "AniShift: wyniki produktów"
[S07]: research.md#s07 "AniShift: granica CLI"
[S08]: research.md#s08 "AniShift: obecny terminal"
[S09]: research.md#s09 "AniShift: klawisze i geometria"
[S10]: research.md#s10 "AniShift: zależności"
[S11]: research.md#s11 "AniShift: workspace"
[S12]: research.md#s12 "AniShift: zasady application"
[S13]: research.md#s13 "AniShift: wspólny Auto w CLI"
[S14]: research.md#s14 "AniShift: wybór źródeł"
[S15]: research.md#s15 "LiveChart FAQ"
[S16]: research.md#s16 "LiveChart RSS"
[S17]: research.md#s17 "AniList API: dokumentacja"
[S18]: research.md#s18 "AniList: limity"
[S19]: research.md#s19 "AniList: warunki użycia"
[S20]: research.md#s20 "qBittorrent WebUI API 5.0"
[S21]: research.md#s21 "qbittorrent-api 2026.8.1"
[S22]: research.md#s22 "qbittorrent-api: torrenty"
[S23]: research.md#s23 "Nyaa: kod serwisu"
[S24]: research.md#s24 "Nyaa: szablon RSS"
[S25]: research.md#s25 "Nyaa: istniejący parser klienta"
[S26]: research.md#s26 "nyaa-cli"
[S27]: research.md#s27 "anipy-cli"
[S28]: research.md#s28 "anipy-api: moduł MAL"
[S29]: research.md#s29 "AnimeTosho: informacje o API"
[S30]: research.md#s30 "Anitopy"
[S31]: research.md#s31 "RapidFuzz"
[S32]: research.md#s32 "defusedxml"
[S33]: research.md#s33 "SQLite WAL"
[S34]: research.md#s34 "Python 3.14 sqlite3"
[S35]: research.md#s35 "Windows Task Scheduler: schtasks create"
[S36]: research.md#s36 "Windows: nazwy i ścieżki"
[S37]: research.md#s37 "Python subprocess"
[S38]: research.md#s38 "mpv manual"
[S39]: research.md#s39 "MAL API v2"
[S40]: research.md#s40 "MAL authorization"
[S41]: research.md#s41 "SubsPlease"
[S42]: research.md#s42 "Erai-raws"
[S43]: research.md#s43 "AniShift: intencje produktu"
