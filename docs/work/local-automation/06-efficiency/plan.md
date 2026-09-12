---
kind: implementation-plan
status: IN_PROGRESS
created: 2026-09-08
updated: 2026-09-12
baseline: a7d319f334a062d0fe016c774d9a5fb4fccbe9b6
branch: work/local-automation/06-efficiency
specification: spec.md
---

# Plan 06: sterowanie lokalną automatyzacją

## 1. Kontrakt wykonawcy

Zaimplementować [spec.md](spec.md): Manual wybiera odcinki, Auto reaguje na gotowe pliki, subskrypcje niezależnie dostarczają odcinki. Regeneracja wywołuje Auto z żądaniem odtworzenia. Jeden istniejący rdzeń wykonuje wszystkie zlecenia.

**Najpierw przeczytaj specyfikację. Ten plan opisuje HOW, nie zastępuje WHAT.** Kolejność prac: P01–P08. Nie zaczynaj od przebudowy wyszukiwarki, wyglądu terminala ani nowego modelu mediów. Nie realizuj starego wielkiego masterplanu lokalnej automatyzacji; jest historią wcześniejszych decyzji. Kontekst kodu i ograniczenia źródeł: [research](research/2026-09-08-control-model-research.md).

Plan jest gotowy do rozpoczęcia implementacji; decyzje domykające luki z przeglądu wykonawcy są w sekcji 15. Nie dowodzi działania API na komputerze właściciela. Bramki G1–G3 weryfikują wąskie granice platformowe; wynik negatywny blokuje tylko zależny etap i wymaga korekty tej decyzji, a nie cichego zastąpienia wymagań gorszym zachowaniem.

### Reguły pracy

- Pracuj na wskazanej gałęzi funkcjonalnej, nie na `main`; nie nadpisuj zmian właściciela. Sprawdź `git status`, HEAD i różnicę względem baseline. Jeżeli zmienił się kod dotykany przez plan, najpierw zaktualizuj mapę wpływu.
- Czytaj `AGENTS.md` w root oraz obszarach `anishift`, `application`, `cli`, `platform`, `services` i `tests`, kiedy je zmieniasz. Kod, komentarze i komunikaty gita po angielsku; dokumenty produktu i rozmowa po polsku. Używaj skilli simple, specification, research i planning dostępnych w środowisku agenta. Nie kopiuj całej paczki skilli do projektu.
- Kolejny etap musi zostawić działającą dotychczasową ścieżkę. Nie włączaj domyślnie niedokończonego nowego watchera. W P08 nowa droga zastępuje starą, bez dwóch konkurujących mechanizmów w produkcji.
- Nazwy nowych modułów i kontraktów podane niżej są nazwami planowanymi. Metody zastane oznaczono jako istniejące. Nie twórz pustych interfejsów ani modułów wyłącznie dla odhaczenia tabeli.
- Dokumentacja wdrożenia opisuje wyniki rzeczywistych komend i testów. SKIP, brak Windowsa lub brak danych nie oznacza PASS. Nie dodawaj nowego frameworka, brokera, bazy ani zależności runtime.

## 2. Co rozszerzamy, a czego nie budujemy drugi raz

| Obszar | Zastany punkt wejścia | Zmiana w tym planie |
| --- | --- | --- |
| Intencje i planowanie | `application/intents.py`, `planner.py`, `planning.py`; `plan_auto`, `plan_manual`, wspólne `_plan` | Jednorazowe ustawienia, odtworzenie produktów, kontrola aktualności podglądu. |
| Wykonanie | `application/service.py::execute`, `GraphScheduler`, `scheduler_runtime.py`, `scheduler_contracts.py`, `sessions.py` | Jeden koordynator przyjmujący niezależne konteksty planów, wspólne limity i pierwszeństwo. |
| Rozpoznawanie biblioteki | `discovery.py`, `inspection.py`, `service.py::discover`, `application/watch.py::WatchLedger` | Aktualizacja zmienionych grup, trwała wiedza o obsłużonych wejściach, zdarzenia plikowe. |
| Rezydent | `cli/watch.py::run_daemon`, `ProcessLock`, `platform/autostart.py` | Właściciel pracy i stanu zamiast uruchamiania okien partii. |
| Pozyskanie | `application/acquisition.py`, `subscriptions.py`, `services/catalog/anilist.py`, `services/torrents/nyaa.py`, `qbittorrent.py` | Kontrola subskrypcji, terminy emisji, potwierdzone transfery i wspólna kontrola żądań. |
| UI i CLI | `cli/run.py`, `interactive/app.py`, `manual.py`, `anime.py`, `progress.py`, `prompts.py`, `settings.py`, `cli/main.py` | Cienki klient rezydenta, prosty wybór odcinków i ekran Stan w obecnym rendererze. |
| Publikacja | `publisher.py`, `publish_handler.py`, `ArtifactStore`, `RunSession` | Zachowanie poprzedniego wyniku, zgodność generacji i recovery częściowej publikacji. |

Obecny `GraphScheduler` dostaje jeden niezmienny `ExecutionPlan`, jeden snapshot ustawień, handler i sesję. Obecne `AppService._run_lock` chroni tylko konkretną instancję procesu. Nie wystarczy dopisać priorytetu do listy albo założyć, że panel i watcher już mają wspólną blokadę. Ponadto `ThreadPoolExecutor` dostaje dziś nadmiarowe oczekujące future, a `NaturalOrderGate` może zatrzymać gotowe wyniki. Te trzy miejsca trzeba zmienić razem, zachowując istniejące handlery.

Nowe niewielkie granice, kiedy będą potrzebne: `application/control.py` na polecenia i stan sterowania, `application/watch_state.py` na trwały ledger, `platform/local_control.py` na lokalne IPC, `platform/directory_watch.py` na powiadomienia o plikach, `platform/tray.py` na ikonę oraz `platform/qbittorrent_process.py` na własność procesu. To nie sześć usług ani osobnych wykonawców. Logika subskrypcji pozostaje przy `subscriptions.py`, a przydział zasobów przy istniejącym schedulerze.

## 3. Jeden właściciel, panel jako klient

### 3.1. Proces i kierunek zależności

Rozszerzyć obecny proces czuwania. Tylko on przyjmuje do wykonania, rezerwuje grupy i zapisuje stan automatyzacji. Ma jeden skład aplikacji oraz jeden koordynator wykonania. GUI systemowe to jedynie ikona; interfejsem pracy pozostaje Prompt Toolkit.

Panel/CLI -> publiczna fasada aplikacji -> lokalny kanał sterowania -> właściciel stanu -> obecne planowanie i wykonanie. Reguły domenowe nie importują transportu, renderera ani Win32. `cli/watch.py` pozostaje granicą procesu, nie miejscem całej logiki produktu.

Jeżeli właściciel już działa, następny klient się podłącza. Jeżeli nie działa, klient może uruchomić go z zapisanymi ustawieniami pod istniejącym `ProcessLock`; samo uruchomienie nie włącza Auto ani subskrypcji. Wyścig dwóch uruchomień kończy się jednym właścicielem i ponowną próbą połączenia drugiego klienta. PID i obecność pliku nie są dowodem zajętej blokady.

Wolne I/O jest zlecane poza wątkiem sterowania i wraca jako wynik z identyfikatorem żądania oraz generacją. Nie blokuje przycisku Wyłącz, nowych plików ani postępu schedulera. Liczba prac I/O jest ograniczona; nie uruchamia się wątku na każdą subskrypcję w nieskończoność. Nie dopuszczać operacji zależnych od pliku stanu, którego nie udało się bezpiecznie zapisać.

### 3.2. Minimalny lokalny protokół

Użyć standardowej biblioteki: `multiprocessing.connection` z lokalnym `AF_PIPE` na Windows i `AF_UNIX` w testach/obsługiwanym środowisku Unix. To kanał sterowania, nie kolejka zadań. Nie wystawiać portu TCP ani zdalnego API.

Przesyłać wyłącznie jawnie walidowany JSON przez `send_bytes`/`recv_bytes` z limitem wielkości ramki. Nie używać `send`/`recv` z pickle, deserializacji obiektów Pythona, `eval` ani dowolnych nazw wywoływanych metod. Schemat ma wersję, `command_id`, `instance_id`, rodzaj polecenia i ograniczony payload. Górny rozmiar ramki jest stałą bezpieczeństwa uzasadnioną największym obsługiwanym komunikatem; większe listy stanu są stronicowane, nie przesyłane bez końca.

Wymagane grupy poleceń: odczyt stanu; Auto on/off i wyjątki katalogów; rezerwacja/zwolnienie; podgląd i zatwierdzenie; kontrola subskrypcji; jawne sprawdzenie/ponowienie; sterowanie istniejącym transferem; anulowanie własnego zlecenia; zakończenie procesu. Zamiana listy wierszy na polecenia odbywa się w kontrolerze, nigdy w rendererze.

Autoryzacja to losowy klucz instancji i mechanizm `authkey`; metadane połączenia/klucz chronić uprawnieniami bieżącego użytkownika, nie logować. Na Windows endpoint jest lokalny `\\.\pipe\...`; nie akceptować nazwy innego komputera. Chronione uprawnienia pliku z kluczem i transportu trzeba zweryfikować w G1; sam prefiks ścieżki nie jest pełnym zabezpieczeniem. Nie zapisywać kluczy LLM/TTS ani pełnych `Settings` w komunikatach stanu.

Właściciel zapisuje przyjęcie polecenia przed pozytywnym potwierdzeniem. Powtórzenie `command_id` daje wcześniejszy wynik, nie nową pracę. Brak odpowiedzi po zerwaniu połączenia nie uprawnia UI do wysłania nowego ID i zdublowania skutku. Nieaktualny `instance_id` albo fingerprint podglądu zwraca żądanie odświeżenia. Zaakceptowane zlecenie żyje po zamknięciu klienta.

Postęp jest współdzielonym snapshotem i ograniczonym strumieniem zdarzeń, z łączeniem zastąpionych aktualizacji. Wolny panel nie może powiększać kolejki powiadomień bez limitu. Bez podłączonego panelu nie wysyłać heartbeatów i nie zapisywać tego samego procentu na dysk co klatkę.

### 3.3. Rezerwacje Manual

Rezerwacja dotyczy wybranych grup, nie całej biblioteki. Atomowa operacja właściciela sprawdza, czy grupa nie jest aktywna lub zarezerwowana przez innego klienta. Samo przeglądanie listy nie rezerwuje. Rozłączenie kanału edycji, Esc i odznaczenie zwalniają rezerwację. Zmiana źródła unieważnia podgląd; po restarcie właściciela stary panel musi uzyskać nową rezerwację i podgląd.

Zatwierdzenie zamienia rezerwację w zlecenie bez luki, w której watcher przejąłby odcinek. Wyjście z już zaakceptowanej pracy nie jest anulowaniem. Jawne Anuluj dotyczy wskazanego zlecenia i wykorzystuje istniejący mechanizm cancellation, nie zabija całego rezydenta.

## 4. Stan i migracja bez drugiej kolejki

### 4.1. Miejsce i własność danych

Zachować `config/subscriptions.json` jako rejestr subskrypcji i ich zakresu pozyskania. Rozszerzyć jego schemat z jawną migracją. Dodać `config/watch/state.json` dla trwałego ledgera sterowania/przetwarzania i potwierdzeń operacji. To zapis zamiarów i rezultatów, nie drugi scheduler: nie zawiera własnej alternatywnej kolejki gotowych tasków, pul workerów ani grafów obok `GraphScheduler`.

`settings.json`, `.env` i presety nadal przechodzą przez istniejącą fasadę i zachowują publiczny format. Istniejące API zapisujące te dane musi być serializowane przez właściciela, gdy działa rezydent. Preferencje Auto, harmonogramu i wyjątków można przechowywać w ledg­erze automatyzacji, nie dopisywać ich ukradkiem do formatu presetu. Nie dodawać SQLite, katalogu inbox ani kopii źródeł.

| Zapis | Minimalne dane do utrwalenia |
| --- | --- |
| Polityka automatyzacji | Globalne Auto, wyjątki katalogów, ustawienia harmonogramu i retry, wersja schematu. |
| Subskrypcja | Stabilne ID sezonu/grupy, etykiety/fraza/kategoria, numeracja, zamówiony zakres, katalog, enabled, generacja konfiguracji, stan końca emisji. |
| Odcinek w zakresie | Termin emisji i jego pochodzenie, termin szukania, okno/stan braku, znalezione wydanie, powiązanie z potwierdzeniem pozyskania. |
| Potwierdzenie pozyskania | ID operacji, info hash, katalog i wymagane pliki, stan przed wysłaniem/niepewny/przyjęty/kompletny, pochodzenie użytkownik/tło. |
| Zlecenie przetwarzania | ID/generacja, grupa i fingerprint wejścia, pochodzenie, tryb doboru źródeł, snapshot ustawień bez sekretów, zakres wymuszenia, stan i próby. |
| Rezultaty | Potwierdzenia poprawnych produktów/checkpointów, ich generacja i pochodzenie; marker świadomie obsłużonego ręcznie wejścia; zgłoszone problemy/powiadomienia. |
| Wspólne ograniczenia | Termin blokady dostawcy, niepewne efekty operacji i zaakceptowane ID poleceń potrzebne do idempotentnego recovery. |

Nie powielać pola kompletności w kilku rejestrach jako niezależnie zapisywanej prawdy. Subskrypcja odsyła do potwierdzenia pozyskania, Stan składa widok z potwierdzeń źródeł i produktów. Każda atomowa zmiana ma jednego autora. Operacje między plikami odtwarza się po stabilnym ID: brak drugiego zapisu nie jest sukcesem i nie powoduje nowego transferu.

Zapisy: serializacja, plik tymczasowy w tym samym katalogu, flush i trwałość wymagana przez wybrany punkt potwierdzenia, następnie `replace`. Zachować poprzedni poprawny stan do odzyskania, a błąd zapisu jawnie zatrzymuje zależne operacje. Testować uszkodzony/truncated JSON i awarię między etapami zapisu. Log to diagnostyka, nie rejestr wykonawczy.

### 4.2. Identyfikatory i generacje

Grupy i artefakty korzystają z istniejących identyfikatorów względnych ścieżek. Przynależność do sezonu korzysta z zapisanego ID AniList i kontekstu sezonu; sama znormalizowana nazwa z grupą nie wystarcza do rozróżnienia sezonów. W numerach odcinków zachować reprezentację dziesiętną i istniejące reguły `SeasonContext`/`read_episode`.

Zlecenie posiada oddzielnie pochodzenie, sposób doboru źródeł i żądanie przebudowy. Nie kodować wszystkich trzech w `RunMode`. Przyjęte ustawienia są niezmienne dla tego zlecenia. Referencję do sekretu rozwiązuje istniejący handler podczas wykonania; sam sekret nie jest snapshotem w ledg­erze.

Ten sam aktywny `group_id` nie dostaje drugiego wykonania. Retry należy do tej samej generacji zlecenia. Jawna regeneracja z identycznymi ustawieniami ma nową generację i dlatego naprawdę odtwarza wynik. Fingerprint uwzględnia istotne wejścia grupy, nie mtime całego katalogu i nie chwilowe pliki z `temp/`.

Marker ręcznie obsłużonego wejścia jest konieczny dla R-028. Bez niego watcher po Manual z samymi napisami od razu dorobi domyślnego lektora, a po regeneracji innym głosem może cofnąć wybór. Marker wiąże się z wersją źródła oraz zaakceptowanym zakresem, nie z całą serią na zawsze. Jawne Auto jednorazowo i nowy rzeczywisty input przechodzą przez nowe rozstrzygnięcie planera; zmiana globalnego głosu sama go nie kasuje.

### 4.3. Migracja

Migrację wykonać raz przed uruchomieniem nowych automatów, po kopii poprzedniego poprawnego zapisu. Dotychczas działające czuwanie zachowuje aktywne Auto; nowa instalacja i samo otwarcie panelu go nie włączają. Obecne subskrypcje stają się enabled z zachowaniem katalogu, zakresu, dat i numeracji.

Dawne `taken`/`taken_episodes` są dowodem przekazania, nie kompletności. Przygotować stan do uzgodnienia z dyskiem i klientem; nie oznaczać go od razu jako komplet ani nie pobierać wszystkich numerów ponownie. Brak pewnego ID sezonu pozostawia wpis wymagający powiązania, bez losowego przypisania. Nie startować qBittorrenta wyłącznie po to, by odświeżyć stare nieaktywne wpisy bez zamówionej pracy.

Uszkodzony plik nie może dać pustej listy subskrypcji. Nie usuwać danych przy rollbacku. Stary kod nie powinien zapisywać nowego schematu; po migracji tylko jedna wersja rezydenta jest właścicielem. Cofnięcie wersji wymaga jawnej kopii sprzed migracji, nie zgadywanego downgrade'u.

## 5. Rozszerzenie istniejącego GraphScheduler

### 5.1. Niezależne konteksty, wspólne zasoby

Zachować niezmienny plan dla pojedynczego zlecenia. Rozszerzyć koordynator tak, aby przyjmował nowe konteksty planów w trakcie działania. Kontekst ma swój plan, `RunSettingsSnapshot`, sesję/temp, handler, cancellation, emitter i wynik. Gotowe taski wszystkich kontekstów trafiają do tego samego mechanizmu przydziału zasobów istniejącego schedulera.

Nie sklejać ręcznego planu z innym głosem do jednego starego `ExecutionPlan.settings`. Nie tworzyć po jednym niezależnym `GraphScheduler` dla każdego zlecenia; pomnożyłoby to limity. Istniejące `run(plan, ...)` zachować jako adapter jednego zamkniętego zbioru wejść do tej samej logiki, aby testy i jednorazowe wywołania nie miały drugiego algorytmu.

Wspólne mapy identyfikują task przez `(request_id, task_id)`, a artefakty i zależności pozostają w kontekście planu. Właściciel zakazuje jednoczesnych generacji jednej grupy. `ArtifactStore` pozostaje prywatny dla koordynatora, worker otrzymuje niezmienny snapshot.

Limity zasobów pochodzą z istniejących ustawień, nie sumują się po zleceniach i nie mnożą przez otwarte panele. Parametry treści są snapshotem zlecenia; preferencje dostępnej współbieżności stanowią wspólny limit przyjmowania nowych tasków. Zmniejszenie limitu nie zabija trwających tasków, tylko czeka z następnymi. Zachować wymaganą seryjność SAPI i istniejące obliczanie limitu ekstrakcji. Klucze z aliasami tego samego dostawcy nie tworzą niezależnych pul obchodzących wspólny limit.

### 5.2. Kolejność i brak ukrytego bufora

Dwie klasy pierwszeństwa: jawna/przyspieszona praca użytkownika oraz tło. W klasie zachować kolejność przyjęcia i istniejący porządek naturalny potrzebny wewnątrz zakresu. Ręcznie zamówiony sezon jest nadal jawną pracą użytkownika; nie przypisywać mu niskiego priorytetu tylko dlatego, że ma wiele odcinków.

Każdy gotowy task niesie pochodzenie swojego zlecenia. Wybór najwyższego priorytetu odbywa się dopiero, gdy istnieje rzeczywisty wolny slot. W rezydencie nie wysyłać zapasu niższego priorytetu do prywatnej kolejki `ThreadPoolExecutor`. Dopuszczalna liczba submitted odpowiada faktycznej pojemności workerów; czekające taski pozostają w koordynatorze, gdzie można zmienić kolejność. To usuwa przeszkodę obecnego `max_pending_per_resource` bez anulowania rozpoczętych wywołań.

`NaturalOrderGate` nie może stanąć pomiędzy niezależnym pilnym zleceniem a gotowym wynikiem tła. Ograniczyć go do odpowiedniego kontekstu zlecenia i respektowanej przez użytkownika polityki kolejności. Nie wprowadzać globalnej kolejności publikacji całej biblioteki. Dopiero zależność lub brak danego zasobu może opóźnić pilny task.

### 5.3. Pauza, zasoby, sesje i publikacja

Wyłączenie Auto zatrzymuje admission nowych automatycznych tasków; trwające kończą się normalnie. Gotowe wyniki zapisuje się i zachowuje sesję oczekującą, nie wyrzuca jej stagingu. Manual/jawne Auto/regeneracja pozostają dopuszczone. Oczekiwanie na premierę, retry i transfer nie tworzy future zajmującego pulę multimedialną.

Koordynator czeka na przyjęcie planu, zakończenie taska, zmianę sterowania albo najbliższy termin publikacji. Nie utrzymuje pętli 50 ms podczas pustego czuwania. Zakończenie pracy zamyka niepotrzebne executory i klientów/handlery, nie pozostawia aktywnych procesów narzędzi ani zasobów modeli dla samego oczekiwania na przyszły plik.

Rozszerzenie sesji musi uwzględnić `cleanup_orphaned_temp`: lista aktywnych runów to wszystkie aktywne i zachowane oczekujące konteksty, nie tylko właśnie otwierany run. Sprzątanie nie dotyka źródeł ani temp innych zleceń. Nie porzucać existing generation/cancellation guards.

Przed publikacją sprawdzić aktualność generacji i wejść grupy. Task publikuje zwalidowany staging do docelowego produktu istniejącą atomową operacją per plik. Stary plik pozostaje do tej chwili. Potwierdzenie generacji produktu zapisać tak, aby recovery po `replace`, ale przed potwierdzeniem, umiało ustalić, co naprawdę zostało opublikowane. Zachować w pending publication metadane potrzebne do uzgodnienia. Nie obiecywać transakcji obejmującej wszystkie pliki odcinka.

Po restarcie zweryfikować zachowane poprawne checkpointy i produkty, a brakującą pracę wyznaczyć ponownie dla tego samego zamiaru. Nie ma gwarancji exactly-once dla obcego requestu, gdy proces umarł po jego wykonaniu, lecz przed odbiorem odpowiedzi. Taki stan jest niepewny, z ograniczonym retry; nie można ukrywać go jako dowodu niewykonania ani bezkarnie mnożyć płatnych żądań.

## 6. Wejście Auto, Manual i regeneracja

### 6.1. Jeden wybór zakresu, dwie ścieżki doboru źródeł

Prosty Manual: zaznaczenia grup -> preset domyślny -> podgląd -> Start. Przy domyślnym automatycznym doborze źródeł można wykorzystać `plan_auto` z pochodzeniem użytkownika. Oryginalny zaawansowany Manual nadal tworzy `GroupIntent.MANUAL` i używa `plan_manual`. To istniejące dwie drogi do wspólnego `_plan`, nie dwa silniki. Pochodzenie nie wynika z `RunMode`.

Zachować zgodność `ManualController`, `ManualDraft`, domyślnych produktów, wyboru plików zewnętrznych i ścieżek. Dopisać wygodny wybór wielu grup oraz jeden zbiorczy podgląd. Grupa z blokującym problemem nie może zablokować całej automatycznej biblioteki: walidować i przyjmować niezależne grupy, a problem pokazać przy danej grupie. Nie przerabiać w ciemno obecnej semantyki blokującego, jednorazowego `ExecutionPlan`.

Warunek automatycznego przyjęcia: globalne Auto i skuteczny wyjątek katalogu pozwalają; znane wejście jest gotowe; są potrzebne produkty; nie ma rezerwacji/aktywnej generacji; nie obowiązuje marker świadomej ręcznej obsługi tego wejścia; nie wyczerpano retry tego zamiaru. Zmiana własnego produktu nie jest nowym wejściem spełniającym te warunki.

### 6.2. Odtworzenie przez istniejący planner

Rozszerzyć wejście automatycznego planowania o żądanie odtworzenia wskazanych produktów oraz run-only overrides. Nie zmieniać formatu `AutoPreset`, nie dodawać `RunMode.REGENERATE`. W UI Regeneruj jest wygodnym utworzeniem tego żądania, a nie osobnym kontrolerem całego procesu wykonania.

Planner buduje projekcję artefaktów dla nowej generacji: wskazane generowane produkty i nieaktualne zależne wyniki nie mogą zostać ponownie użyte tylko dlatego, że mają `READY`. Ich nowe deskryptory są planowanymi wyjściami `MISSING`, jak wymaga obecny `ArtifactStore`. Nie kasować plików, nie zmieniać trwałego inventory na „brak” przed powodzeniem, nie oznaczać oryginalnego `SOURCE` jako produkowalnego.

Zakres unieważnienia wynika z zależności produktu i zmienianego parametru. Głos/tempo unieważnia TTS oraz zależne audio i zamówione eksporty, ale nie poprawne tłumaczenie. Zmiana tekstu unieważnia jego rzeczywistych konsumentów. Eksport bez zmiany treści korzysta z gotowego lektora/napisów. Nie unieważniać wszystkich przodków tylko dlatego, że wynik trzeba odtworzyć.

Jeżeli potrzebne surowe audio, klipy lub inny poprzednik nie istnieją, planner planuje ich rzeczywiste odtworzenie i pokazuje je w podglądzie. Gotowy miks nie jest suchym głosem. Zmiana głośności po usunięciu pośrednich danych może więc wymagać TTS; nie maskować kosztu fałszywym „tylko audio”. Nie dodawać bez zgody wiecznego cache wszystkich klipów.

Podgląd pokazuje produkty zachowane, odtwarzane i zależne, oraz rzeczywiście brakujące poprzedniki. Wymuszenie bez zmiany ustawień musi dać taski; zwykłe Auto tej samej kompletnej grupy nie daje tasków. Udane ręczne wykonanie aktualizuje marker R-028. Częściowo opublikowane wyniki oznaczyć generacją i stanem częściowym, aby zwykła inspekcja nie uznała mieszanego zestawu za sukces nowego zlecenia.

## 7. Czuwanie bez stałego pełnego skanu

Dodać platformową granicę `ReadDirectoryChangesW` przez `ctypes`, z asynchronicznym oczekiwaniem i kontrolowanym zamknięciem uchwytów. Obserwacja obejmuje poddrzewo biblioteki. Najpierw uzbroić watcher, potem wykonać początkowe discovery i nałożyć zebrane w tym czasie zdarzenia, żeby plik dodany podczas rozruchu nie zginął.

Powiadomienie oznacza „sprawdź zmianę”, nie „plik gotowy”. Scalić zdarzenia do zestawu zmienionych grup/katalogów; wykorzystać istniejące `classify_artifact`, `group_candidates`, reguły `temp/`, ukrytych plików i symlinków. Nie tworzyć drugiego parsera nazw w adapterze Win32.

Zmienić cache z jednego odcisku całej biblioteki na cache inspekcji grup i istotnych plików. `AppService.discover()` nadal jest fasadą i źródłem inventory; UI nie buduje alternatywnej inspekcji. Niezmienione grupy są ponownie używane, a zmiana jednej grupy nie wywołuje `mkvmerge`/FFmpeg dla pozostałych. Trwała część cache ma wersję walidatora, względne ścieżki i fingerprinty; nie serializuje bezpośrednio obiektów bibliotek.

Dla zmienionego własnego pliku zaplanować tylko potrzebny termin stabilizacji, z dotychczasowym QUIET jako ustawieniem pomocniczym. Znany transfer jest blokowany do jego potwierdzenia. Pojawienie się napisów odblokowuje tę samą grupę. Zdarzenia publikacji wyników aktualizują stan, ale nie generują nowego odcinka. Nie hashować dużych mediów przy każdym powiadomieniu.

Przepełnienie bufora/utrata zdarzeń, `ERROR_NOTIFY_ENUM_DIR`, wynik zero bytes, powrót z uśpienia i utrata/zmiana korzenia uruchamiają uzgodnienie biblioteki. Po uzgodnieniu wrócić do oczekiwania. Dla niewspieranego nośnika ujawnić tryb awaryjny i stosować tylko lekkie kontrole metadanych z istniejącym interwałem jako początkowym fallbackiem; pełne dekodowanie w pętli jest niedozwolone. G1 sprawdza realny nośnik właściciela i zerowe okresowe skany w normalnym idle.

## 8. Subskrypcje, terminy i kontrola HTTP

### 8.1. Mutacje i konkurencja

Rozszerzyć `SubscriptionService` o idempotentne enabled/disabled, usunięcie i dodanie przed pierwszym wydaniem. Wyłączyć zależność tworzenia subskrypcji od obowiązkowego istniejącego `ReleaseChoice`: przyjmować rozstrzygnięty tytuł/sezon, grupę i zakres. Obecna akcja O nadal może wypełnić te dane z wydania. Nie usuwać istniejącego rozumienia numeracji i filtrów jakości/języka.

Zmiana wpisu podnosi jego generację. Wynik szukania wraca z generacją, dla której został rozpoczęty. Przed dopuszczeniem dodania torrenta właściciel ponownie sprawdza istnienie, enabled i generację. Wyłączenie/usunięcie zatwierdza stan i blokuje jeszcze niedopuszczone dodania. Żądanie add już przekazane do klienta jest operacją wcześniej zamówioną, może mieć niepewny wynik i musi pozostać widoczne; nie obiecywać cofnięcia pakietu HTTP.

Usunięty wpis nie wraca od spóźnionej odpowiedzi. Potwierdzenia przyjętych transferów przeżywają usunięcie subskrypcji. Włącz nie resetuje przerwanych operacji, ukończonych plików, historycznych problemów i wyczerpanych okien. Pełna synchronizacja nie jest efektem renderowania listy.

### 8.2. Czyste wyznaczanie terminów

Zastąpić `check_all` wykonywane co godzinę decyzją dla konkretnego należnego zakresu. Czysta funkcja z zapisanych danych i bieżącego czasu zwraca akcję, jej powód oraz następny termin albo brak automatycznej akcji. Dla liczby subskrypcji właściciela wystarczy minimum z zapisanych terminów; nie dodawać APScheduler ani nowego frameworka harmonogramów.

AniList adapter rozszerzyć o terminy dla konkretnych ID, z walidacją schematu i paginacji w G2. Nie odtwarzać aliasów i całego łańcucha prequeli przy każdej premierze. Zapisać potrzebne przyszłe wpisy, ponieważ historia emisji nie jest gwarantowana przez źródło. Samo `nextAiringEpisode` nie stanowi pełnej historii zaległości.

Pierwszy termin to znane `airingAt` plus ustawione/oszacowane opóźnienie. Proste oszacowanie: mediana dostępnych poprawnych par dat emisji i publikacji tej samej serii/grupy, po odrzuceniu paczek, poprawek/reuploadów i niepewnych dopasowań. Przy braku danych użyć ustawienia, nie wyznaczać historii z mtime. Nie budować systemu ML i nie przechowywać nieograniczonej historii; liczba zachowanych próbek jest ograniczoną preferencją techniczną, a wynik pozostaje oznaczonym szacunkiem.

Kontrola kalendarza: dodanie, potrzebny następny termin, uzasadniona weryfikacja przy należnym sprawdzeniu i akcja użytkownika. Null/nieznana data nie znaczy teraz ani koniec. Przy potwierdzonym przełożeniu zmienić due i nie wysyłać starego zapytania Nyaa. Brak żadnego terminu zostawia stan wymagający uzupełnienia zamiast zapytania co godzinę.

Każdy zamówiony odcinek ma niezależne okno. Jego wygaśnięcie nie blokuje kolejnego odcinka i nie jest odwołane przy najbliższej premierze. Po końcu emisji dokończyć okno finału i już przyjęte transfery; potem subskrypcja jest zakończona z kompletem/brakami/niepewnością, bez okresowej sieci. Wznowienie po długim wyłączeniu robi jedno bieżące uzgodnienie, nie pętlę historycznych godzin. Zapisany terminalny brak nie odzyskuje prób od restartu.

### 8.3. Realne żądania i błędy

W subskrypcji korzystać najpierw z zapamiętanej grupy, frazy i właściwej kategorii. Pełne `search_title` pozostaje wyszukiwaniem interaktywnym, nie operacją każdej godziny. Brak konkretnego numeru może uzasadnić ograniczone dodatkowe zapytanie. Wszystkie rzeczywiste kategorie, catch-up i retry mieszczą się w jawnym budżecie opartym na istniejących ograniczeniach wyszukiwania.

Na istniejących granicach HTTP dodać współdzieloną kontrolę najwcześniejszego żądania, aktywnego identycznego klucza i odpowiedzi limitowania. Klucz uwzględnia dostawcę, metodę, parametry/kategorię i kontekst uprawnień, ale nie loguje sekretów. Współdzielić tylko równoważne bieżące potrzeby; stary wynik z innego okna nie jest bezterminowym dowodem braku wydania.

Odpowiedzi AniList wymagają obsługi błędów GraphQL również przy HTTP 200. 429, `Retry-After` i reset tworzą wspólną blokadę; powtarzane ręczne kliknięcia jej nie obchodzą. Brak sieci nie uruchamia osobnego health-checka bez należnej pracy. Po powrocie ograniczać burst. Warunkowe żądania stosować wyłącznie dla endpointów, które rzeczywiście dostarczają odpowiednie walidatory; nie zakładać cache dla każdego POST GraphQL.

Przy każdym faktycznym wysłaniu policzyć dostawcę, typ operacji, powód i wynik, bez treści napisów/promptów i danych logowania. Liczniki obejmują logowanie, 304 i retry bibliotek. Zweryfikować retry już obecne w adapterach/SDK, żeby nadzór ich nie mnożył. Jednostką budżetu jest konkretna operacja, nie wszystkie klipy jednego odcinka razem. Lokalny retry blokady publikacji pozostaje osobnym istniejącym mechanizmem.

## 9. Transfer i proces qBittorrenta

### 9.1. Potwierdzenie zamiast znacznika taken

Przed wysłaniem add zapisać zamiar i info hash. Po sukcesie/niepewnym wyniku uzgodnić obecność po tym samym hashu; restart nie tworzy nowego zlecenia. Nie podnosić odcinka do kompletnego na podstawie samej obecności torrenta. Rozszerzyć `TorrentInfo` i klienta o dane rzeczywiście potrzebne: stan, postęp, ilość pozostałych danych, ścieżkę oraz kompletność wybranych plików.

Podczas aktywnych zarządzanych transferów wykonywać jeden zbiorczy odczyt stanu, korzystając z istniejącego `torrents/info` dla kategorii. Szczegóły wymaganych plików odczytać przy istotnej zmianie i potwierdzeniu końca. `/sync/maindata?rid` jest możliwą późniejszą optymalizacją, nie warunkiem implementacji i nie push API. Nie tworzyć nowego mechanizmu synchronizacji bez pomiaru, że odczyt zbiorczy jest problemem.

Potwierdzenie ukończenia dotyczy zamówionych plików i lokalnej gotowości. Plik z prealokacją, transfer w recheck lub bez pobranej metadanej nie jest gotowy. Paczka nie czeka na wyłączone pliki. Zdarzenie completed oznacza aktualizację inventory wspólnego watchera, nie bezpośrednie uruchomienie tłumaczenia z subskrypcji.

Zastój wyznaczać na podstawie braku postępu podczas aktywnego pobierania. Pauza, uśpienie, sprawdzanie danych i brak przyjętego transferu nie naliczają tego czasu. Po progu własny transfer można wstrzymać i pokazać działania ze specyfikacji. Cudzą pracą nie sterować samoczynnie. Zero seedów w jednej odpowiedzi nie jest diagnozą terminalną.

### 9.2. Własność i start na żądanie

Wykorzystać istniejące wykrywanie binarki i konfiguracji. Rozdzielić klienta zastanego oraz uruchomionego przez AniShift. Nie wykonywać setup ani modyfikacji globalnych preferencji cudzego klienta przy codziennym starcie. Zachować zabezpieczenie przed edycją INI działającego procesu i istniejącą kopię konfiguracji.

Dla kontrolowanego cyklu życia wymagany jest rozpoznawalny własny proces/profil i lokalny endpoint. Kierunek implementacji: osobny zarządzany profil tej samej zainstalowanej binarki, z prywatnymi danymi w `config/`, bez kopiowania mediów i bez nowej biblioteki torrent. **Dokładne uruchomienie profilu w wersji Windows właściciela musi przejść G3**; dokumentacja opcji z Linuxa nie jest dowodem obsługi Windows. Nie używać niezweryfikowanej flagi jako gotowego kontraktu.

G3 rozstrzyga i dokumentuje rzeczywisty argv/profil/endpoint oraz sposób dowodu własności. Do tego czasu zastana instancja może działać w bezpiecznym trybie zewnętrznym, ale nie wolno ogłosić funkcji automatycznego zarządzania ukończoną. Awaria izolowanego startu nie uprawnia do zamknięcia całego `qbittorrent.exe` po nazwie.

Uruchamiać dopiero dla konkretnego download/resume. Zapisać tożsamość własnego procesu wraz z danymi pozwalającymi odróżnić ponownie użyty PID oraz profil/API. Kategoria nie potwierdza własności. Po restarcie AniShift nie uznaje dowolnego zastanego procesu za własny na podstawie starego PID; niepewność oznacza brak automatycznego zamknięcia. Przejęcie przez użytkownika lub cudza praca wyłącza prawo do zakończenia instancji.

Gdy nie pozostało własnej pracy i własność jest potwierdzona, można użyć shutdown tej instancji. API shutdown dotyczy całego klienta, nie kategorii. Dla zakończonych zarządzanych zleceń stosować brak dalszego seedowania bez wyłączania mechanizmów cudzego profilu. Timeout startu prowadzi do ograniczonego retry/problemu, nie pętli uruchamiania procesów.

## 10. Stan i ikona, bez przebudowy TUI

Dodać do Home ekran Stan we wspólnym rendererze. Przyjęta zmiana: Auto w głównym menu prowadzi do stanu i przełącznika czuwania; jawne Auto jednorazowo jest akcją wybranego zakresu. Ręczny otwiera wybór odcinków, Anime zachowuje wyszukiwanie. Istniejące techniczne CLI i ich kody wyjścia pozostają obsługiwane. Nie przywracać historycznego systemu komend slash ani Textuala.

`StateController` przechowuje tylko aktualny snapshot UI, zaznaczenia i draft. Widoki: podsumowanie automatyzacji, grupy/produkty/queue, transfery oraz subskrypcje/problemy. Mogą być zakładkami jednego ekranu, nie czterema nowymi aplikacjami. Kontrolki są nazywane czynnościami. Wyłącz subskrypcję ma inne wyjaśnienie niż Wyłącz Auto, a Usuń nie obiecuje skasowania mediów.

Każdy wiersz pokazuje osobno źródło/produkty, etap lub powód czekania, termin i możliwą akcję. Procent pochodzi z istniejących eventów, a nie upływu czasu. Pokaż stan zestarzały/rozłączony zamiast zerowania list. Zmiana zakładki, nawigacja i render nie wysyłają HTTP.

Ikona korzysta z `Shell_NotifyIcon` przez `ctypes`, z własnym małym ukrytym oknem top-level i pompą komunikatów. Okno top-level jest potrzebne do broadcastu `TaskbarCreated`; samo message-only window nie odbierze tego scenariusza. Callbacki tylko przekazują polecenia do właściciela, nie wykonują sieci/TTS na wątku Win32.

Otwórz uruchamia/dołącza panel i pokazuje Stan. Menu: Otwórz, Włącz/Wyłącz Auto, Zakończ AniShift. Ikona i tooltip odpowiadają aktualnemu stanowi; overflow to decyzja systemu. Restart Explorera odtwarza wyłącznie ikonę. Nie uruchamia się nowego rezydenta i nie zmienia ledger.

Powiadomienia Windows wysyłać przy nowym gotowym odcinku lub problemie wymagającym decyzji, z trwałym kluczem odcinek/generacja/rodzaj. Nieskuteczne powiadomienie nie ponawia zadania multimedialnego. Przy seryjnym dopływie wyników można scalić komunikat, ale każdy odcinek pozostaje osobno dostępny w Stanie.

Zakończ blokuje nowe admission, zachowuje stan, czeka na bezpieczne granice operacji i zamyka tylko własne zasoby. Nie zrywa cudzego qBittorrenta. Wyjście z samego TUI nie wywołuje tego polecenia.

## 11. Fazy realizacji

### P01. Kontrakty sterowania, ledger i migracja

**Wynik:** automat potrafi odczytać dotychczasową bibliotekę/subskrypcje i zapisać nowy stan bez uruchamiania czegokolwiek za plecami użytkownika.

**Zależności:** brak. Przed kodem porównać baseline i przeczytać scoped AGENTS. Wykonać istniejące testy oraz zapisać ich rzeczywisty wynik jako punkt odniesienia.

**Zmiany:** `application/intents.py`, `subscriptions.py`, planowane `application/control.py`, `application/watch_state.py`; eksporty fasady i testy konfiguracji/aplikacji. Zdefiniować rozdzielone origin/source selection/rebuild, semantykę przełączników, wersje schematów, trwałe command ID, epizodyczne braki i manual-handled marker. Zachować format presetów.

**Odbiór:** round-trip nowego schematu; stare wpisy z/bez pól opcjonalnych; migracja powtórzona nie zmienia wyniku; uszkodzony zapis nie jest pustą biblioteką; `taken` nie oznacza gotowego źródła; wyłączenie/deletion nie usuwa plików; cztery kombinacje ustawień. Dowód: rozszerzone `tests/application/test_subscriptions.py` i nowe testy ledgera z katalogiem tymczasowym.

**Warunek wyjścia:** potwierdzone reguły R-003/007/013/026/027/028 i przejścia stanu, bez zmiany domyślnego runtime. Nie rozpoczynać od przeprojektowania wszystkich settings.

### P02. Jeden rezydent i komunikacja panelu/CLI

**Wynik:** dwie instancje interfejsu nie tworzą dwóch właścicieli pracy. Zapisane polecenie można odczytać po rozłączeniu bez powtórnego skutku.

**Zależności:** P01.

**Zmiany:** `cli/watch.py`, `cli/run.py`, `cli/main.py`, `application/service.py`, `application/control.py`, `platform/local_control.py`, istniejący `process_lock.py` i `autostart.py`. Publiczne adaptery fasady zachowują granicę aplikacji; UI nie importuje prywatnego schedulera. Dotychczasowe wykonanie pojedynczego planu pozostaje adapterem do późniejszego koordynatora.

**Odbiór:** równoczesny start dwóch klientów; nieaktualny PID przy wolnej blokadzie; klient ginie przed/po ACK; ponowne command ID; błędny auth, zbyt duży JSON, niedozwolona komenda; nowy instance ID odrzuca stary podgląd; zamknięcie panelu nie anuluje zatwierdzonego zlecenia. Testy wieloprocesowe nie mogą ograniczać się do mocka tej samej funkcji.

**G1, część sterowania:** na Windows zweryfikować pythonw, AF_PIPE, autoryzację i uprawnienia bieżącego konta, brak publicznego listenera oraz szybkie sterowanie podczas blokującego fake I/O. Jeżeli transport/ACL nie spełnia kontraktu, nie wystawiać go na TCP jako cichego obejścia; poprawić lokalny adapter i powtórzyć dowód.

### P03. Żywy GraphScheduler z prawdziwym priorytetem

**Wynik:** ręczny plan z innymi ustawieniami dołącza podczas tła i dostaje następny właściwy slot, bez przerwania rozpoczętego taska.

**Zależności:** P02; schemat kontekstów z P01.

**Zmiany:** `scheduler.py`, `scheduler_runtime.py`, `scheduler_contracts.py`, `service.py`, `sessions.py`, `results.py`/`events.py` tylko w potrzebnym zakresie. Wspólne executory/admission, osobne immutable konteksty/emitery, brak ukrytego zapasu future, właściwy scope NaturalOrderGate, komplet active_run_ids w cleanup. Zachować `run(plan)` i testy istniejących handlerów.

**Odbiór:** wykorzystać bariery i liczniki z `tests/application/test_scheduler.py`. Blokować task tła, dodać ręczny, zwolnić zasób i sprawdzić rzeczywistą kolejność wejść handlera. Powtórzyć dla tłumaczenia, TTS i publikacji; ręczne z innym głosem nie dziedziczy ustawień tła; globalny max_active nie rośnie z liczbą planów; natural order nie zatrzymuje niezależnego pilnego wyniku. Sprawdzić Auto off/on, cancellation jednego runu, powrót po blokadzie publikacji i cleanup dwóch aktywnych sesji.

**Warunek wyjścia:** fake-clock test pustego koordynatora nie pokazuje aktywnego pollingu. Wszystkie dotychczasowe testy pojedynczego GraphScheduler pozostają zielone albo mają wyjaśnioną zmianę kontraktu bez osłabienia bezpieczeństwa.

### P04. Manual, automatyczne dopuszczenie i regeneracja

**Wynik:** właściciel wybiera tylko odcinki 3 i 8 i uruchamia je; tło nie przejmuje ich podczas edycji i nie cofa rezultatów. Regeneruj rzeczywiście wykorzystuje Auto.

**Zależności:** P03.

**Zmiany:** `application/planner.py`, `planning.py`, `intents.py`, `selection.py`, `service.py`, `application/watch.py`, `publisher.py`/`scheduler_runtime.py`; `interactive/manual.py` i obecne wyświetlanie podglądu. Żądanie odtworzenia jako wejście Auto; planner projekcji wyjść; rezerwacje i marker ręcznej decyzji w kontrolerze właściciela, nie w rendererze.

**Odbiór:** kilka wybranych grup i tylko ich plan; Esc zwalnia; zmiana pliku unieważnia Start; brak napisów jednej grupy nie zatrzymuje innych automatycznych; zaawansowane źródła w Manual bez regresji. Graf dla zmiany głosu nie zawiera ponownego tłumaczenia; identyczne settings+force zawierają przebudowę; zwykły komplet nie ma tasków. Miks bez dostępnego poprzednika pokazuje dodatkową pracę. Awaria przed replace zachowuje stary produkt, a awaria po jednym z kilku replace pozostawia prawdziwy stan częściowy i da się wznowić.

**Warunek wyjścia:** brak enum/mode/planner/executor „regenerate”. Włączone Auto nie uzupełnia celowo pominiętych produktów po ręcznej pracy dla tej samej wersji wejścia.

### P05. Zdarzenia plikowe i inspekcja zmienionych grup

**Wynik:** biblioteka jest obserwowana podczas pracy, a czekanie nie wymaga pełnego skanu co kilka sekund.

**Zależności:** P03–P04.

**Zmiany:** `platform/directory_watch.py`, `application/discovery.py`, `inspection.py`, `watch.py`, `watch_state.py`, `service.py` i pętla `cli/watch.py`. Zastąpić `_watch_loop` blokowaną dzieckiem, nie dopisywać drugiego stale aktywnego watchera obok. Reużyć klasyfikację produktów i istniejące metody probe.

**Odbiór:** plik w czasie rozruchu, kopiowanie z pauzą, `.!qB`, plik tylko do odczytu, późniejsze napisy, rename, usunięcie, podfolder, symlink, produkty własne i podwójne completed/fs-event. Licznik inspekcji pokazuje wyłącznie zmienioną grupę; niezmienione media nie są ponownie dekodowane. Overflow/resume wymusza uzgodnienie i później wraca do czekania.

**G1, część plikowa:** rzeczywisty Windows i nośnik biblioteki, restart/zmiana korzenia, uśpienie/wznowienie, anulowanie oczekiwania oraz bezczynność bez kolejnych pełnych skanów. Fallback niewspieranego nośnika jest podpisany w Stanie, nie sprzedawany jako ten sam profil idle.

### P06. Subskrypcje z terminami i pewnym przekazaniem pliku

**Wynik:** Dodaj/Włącz/Wyłącz/Usuń kontrolują odrębne pobieranie; przyszłe premiery nie generują zbędnych requestów, a zakończony transfer korzysta ze wspólnego Auto.

**Zależności:** P01–P05. Testy czystego wyznaczania terminów można pisać wcześniej, ale podłączenie runtime dopiero do wspólnego właściciela.

**Zmiany:** `subscriptions.py`, `acquisition.py`, `services/catalog/anilist.py` i typy katalogu; `services/torrents/nyaa.py`, `qbittorrent.py`, `types.py`; `interactive/anime.py` i publiczna fasada. Wprowadzić generacje subskrypcji, epizodyczne terminy, oszczędne query, dane kompletności i współdzieloną kontrolę żądań przy istniejących klientach.

**Odbiór:** fake clock i `httpx.MockTransport`/nagrane odpowiedzi: brak Nyaa przed terminem; przełożenie emisji; null i brak kalendarza; godzinna ponowna próba tylko należnego odcinka; wyczerpane okno; finał/koniec; kolejny sezon nie automatyczny; N/7.5/cour/absolute; start nadchodzącego sezonu bez torrenta; jednorazowy catch-up. Wyłącz/Usuń w trakcie zablokowanej odpowiedzi nie pozwala na nowe add. Niepewne add i restart potwierdzają istniejący hash; selected-file completion i prealokacja nie mylą się. Sprawdzić wspólne 429, login/304/retry w licznikach oraz brak mnożenia budżetów.

**G2:** minimalne live odczyty tylko API potrzebnych do potwierdzenia kształtu harmonogramu i WebUI zainstalowanej wersji. Zapisać wersje, pola, paginację, błędy i faktyczne kody przyjęcia, bez sekretów. Nie pobierać sezonu do testu kontraktu. Niepowodzenie źródła nie uruchamia alternatywnego scrapera bez zmiany planu.

### P07. Stan, ikona i zarządzany klient na żądanie

**Wynik:** całe działanie i kontrola są dostępne z obecnego TUI i ikony; terminal nie otwiera się przy każdej partii.

**Zależności:** P02–P06.

**Zmiany:** `interactive/app.py`, `prompts.py`, `progress.py`, `manual.py`, `anime.py`, planowany kontroler `interactive/state.py`; `platform/tray.py`, `qbittorrent_process.py`, `qbittorrent_config.py`, `autostart.py`, komendy CLI/doctor. Ukryte okno z pompą komunikatów, snapshotowy Stan, wszystkie cztery działania subskrypcji, jawna różnica wyłączenia Auto/subskrypcji/całego procesu.

**G3:** sprawdzić izolowany profil i własność qBittorrent na Windows, uruchomienie i zakończenie tylko własnej instancji, równoległą zewnętrzną instancję, ponowne użycie PID, timeout startu, przejęcie przez użytkownika i restart AniShift. Przetestować stop po końcu pobierania bez zmiany cudzego profilu. Jeśli brak wiarygodnej izolacji/własności, zachować bezpieczny tryb zewnętrzny i oznaczyć R-015/G3 jako niespełnione do korekty, a nie zamykać dowolny proces.

**Odbiór UI:** klawiaturą wybrać 3 i 8, uruchomić, zamknąć panel, otworzyć Stan; przełączyć cztery kombinacje Auto/subskrypcji; dodać, wyłączyć, włączyć i usunąć; wykonać regenerację innym głosem. Zrestartować Explorer, sprawdzić ikonę i niezmieniony stan runu. Wyłączone powiadomienia Windows nie zmieniają sukcesu. Render i nawigacja nie podnoszą liczników HTTP. Autostart odtwarza zapisane ustawienia.

### P08. Recovery, pomiary i zamknięcie zmiany

**Wynik:** wszystkie AC mają wskazany dowód, nowy runtime zastąpił stary, a dokumenty nie mylą planu z dostarczonym kodem.

**Zależności:** P01–P07 i pozytywne G1–G3 dla wymaganej platformy.

**Weryfikacja awarii:** przerwać proces przed/po ACK, przed/po przyjęciu torrenta, podczas LLM/TTS, przed replace, po replace przed potwierdzeniem oraz po części publikacji. Sprawdzić utrzymanie zakresu, settings i prób, brak równoległych generacji, spóźnionych wyników i ponownych transferów. Przetestować brak miejsca, uprawnień, narzędzia, klucza, błąd usług, uszkodzony stan, blokadę odtwarzanego pliku i długie uśpienie.

**Pomiary:** ten sam Windows, biblioteka, ustawienia i scenariusze na baseline oraz zmianie. Zebrać rzeczywiste HTTP według przyczyny/dostawcy, uruchomienia narzędzi, skany/probe grup, czas CPU, pamięć i reakcję na ręczny plik. Zmierzyć start, ustalone idle, pojedynczą i równoczesne premiery, ręczne dołączenie podczas pracy i powrót po uśpieniu. Podać rozmiar biblioteki i czas obserwacji. Warunkiem oszczędności nie jest sam mniej widoczny log, lecz niewykonywanie zbędnej pracy przy zachowaniu kompletu wyników.

**Porządek:** aktualizować README działającej aplikacji, scoped AGENTS, instrukcję doctora/autostartu i dokumentację ustawień do faktycznego zachowania. Usunąć zastąpiony godzinny check-all i automatyczny spawn okien z domyślnej ścieżki. Nie przywracać ich jako drugiego ukrytego fallbacku. Publiczne techniczne komendy, które pozostają potrzebne, delegują do nowego właściciela; usunięte komendy mają czytelny komunikat migracyjny zamiast innego nieopisanego skutku.

Dowody dopisać do tego planu w sekcji 14 i ewentualnie jednego raportu pomiarów; nie generować dodatkowych pustych certyfikatów, manifestów i list zadań.

## 12. Pokrycie wymagań i testy

Tabela przypisuje głównego wykonawcę zmiany; P08 weryfikuje całość. Numery AC odnoszą się wyłącznie do [spec.md](spec.md), nie do podobnych numerów z dawnych dokumentów.

| Wymagania | Fazy | Kryteria do dowiedzenia |
| --- | --- | --- |
| R-001, R-002, I-001 | P02, P03, P08 | AC-001, 002, 020, 033, 042 |
| R-003, R-004, R-005, I-005 | P01, P02, P04, P07 | AC-003, 004, 005, 006, 036, 037, 042 |
| R-006, R-007, R-026 | P01, P06 | AC-007, 008, 032, 033, 034, 035 |
| R-008, R-009, R-010, R-011 | P06, P08 | AC-009, 010, 011, 012, 013, 029, 034 |
| R-012, R-013, R-027 | P01, P06, P07 | AC-014, 015, 035, 036, 038, 039 |
| R-014, R-015, I-002, I-004 | P06, P07, P08 | AC-008, 016, 017, 022, 023 |
| R-016, R-017 | P04, P05 | AC-017, 018, 019, 024, 030, 040 |
| R-018 | P03, P04, P06 | AC-002, 020 |
| R-019 | P03, P06, P07, P08 | AC-013, 021, 022 |
| R-020, R-028, I-003 | P01, P03, P04, P08 | AC-018, 024, 025, 040, 041 |
| R-021, R-022, R-023 | P07 | AC-026, 027, 028, 038 |
| R-024, R-025 | P02, P03, P05, P08 | AC-016, 025, 029, 030, 031, 042 |

Testy czystych decyzji nie czekają rzeczywistych godzin: wstrzyknięty zegar i odpowiedzi źródeł. Testy priorytetu używają barier/Eventów i sprawdzają start tasków, nie kolejność wydrukowanych etykiet. Testy IPC/recovery uruchamiają osobne procesy. Testy platformowe używają realnego Win32 w odpowiednim środowisku; mock API nie potwierdza działania ikony i uprawnień.

Zastane punkty testowe: `tests/application/test_scheduler.py`, `test_subscriptions.py`, testy watch/discovery/planner/service w `tests/application/`, CLI i platformy w odpowiednich katalogach oraz istniejące `tests/integration/`. Fixture potwierdzający wyłącznie queued hashes nie wystarczy do testu pobrania; dodać stany i kompletność wymaganych plików. Nie dodawać nieistniejących markerów ani `__init__.py` do katalogów testowych wbrew AGENTS.

Bramki repozytorium z root, przed commitem kodu:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Sprawdzić również cel Windows w środowisku innym niż Windows zgodnie z obecnym CI. Nie zawężać pełnego pytest do `tests/`, bo repo ma dodatkowe testpaths. Testy `network` są osobną świadomą próbą i domyślny SKIP nie potwierdza integracji. Zachować istniejące hooki i format `docs(repo): ...` / właściwe scope dla kodu. Nie wyłączać strażników po to, by przepchnąć zmianę.

## 13. Ryzyka i granice adaptacji

| Ryzyko | Wymagane zabezpieczenie, nie obejście |
| --- | --- |
| „Priorytet” dotyczy listy, ale nie realnej pracy | Test kolejności startów po zapełnieniu bufora; brak ukrytych future tła i globalnej bramki wyników. |
| Inne settings Manual mieszają się z tłem | Niezależne immutable konteksty planów; wspólne wyłącznie przydzielanie zasobów. |
| Nowy rezydent usuwa temp aktywnego sąsiada | Jeden właściciel i pełny zbiór aktywnych/zatrzymanych sesji w cleanup. |
| Zapis taken lub zmiana kursora gubi brak | Odrębne potwierdzenie źródła i odcinki w zamówionym zakresie. |
| Wyłączenie wpisu przegrywa ze starym HTTP | Generacja, ponowne sprawdzenie przed admission efektu, idempotentne potwierdzenia. |
| Auto cofa świadomą ręczną decyzję | Marker obsłużonej wersji wejścia i osobne żądanie odtworzenia. |
| Fałszywe „tylko miks” | Podgląd wynikający z rzeczywiście dostępnych artefaktów, nie założonego cache. |
| Zużycie zasobów ukryte przez brak okna | Liczniki skanów/probe/requestów i pomiar procesu oraz klienta, nie deklaracja bez wyniku. |
| Zamknięcie osobistego qBittorrenta | Pozytywny dowód własności; niepewność oznacza pozostawienie procesu. |
| Windows API działa tylko w mocku | G1/G3 na docelowym środowisku, brak fałszywego PASS. |
| „Atomowość” kilku produktów jest pozorna | Potwierdzenia generacji per produkt, częściowy stan i recovery; brak obietnicy transakcji całego zestawu. |
| Powrót po awarii ponawia kosztowne efekty | Zapis zamiaru, reconciliation i jawne niepewne wyniki; brak obietnicy exactly-once obcych usług. |

Wolno dopasować nazwy prywatnych helperów i podział dużego modułu do istniejących wzorców. Nie wolno bez zmiany specyfikacji wyłączyć niezależności Auto/subskrypcji, usunąć zaawansowanego Manual, dodać kolejnego planera regeneracji, uprościć priorytetu do całych partii ani zastąpić tray terminalami. Gdy bramka platformowa obala wybraną metodę, zapisać wynik i skorygować ograniczoną część planu, zamiast implementować nieprzetestowane założenie.

## 14. Stan wykonania

**Stan 2026-09-12:** P01 i P03 zaimplementowane; P02 zaimplementowany, lecz audyt wykazał opisane niżej błędy integracji. P04 jest w toku: planner regeneracji i prosty wybór zakresu w panelu działają, integracja z właścicielem wymaga dokończenia. P05–P08 nie są wdrożone. Domyślny runtime nadal korzysta ze starego czuwania.

G1 ma wcześniejszy dowód dla sterowania opisany przy P02; część plikowa G1 oraz G2/G3 i pomiary całości pozostają do wykonania. Historyczne wyniki nie zastępują odbioru końcowej integracji.

Po każdym etapie wykonawca dopisuje tutaj: commit, zakres, uruchomione komendy i rzeczywiste wyniki, dowiedzione AC oraz pozostały problem. Końcowe ukończenie oznacza pokrycie wszystkich AC-001–042 i I-001–005 wraz z dowodem Windows, a nie samo skompilowanie nowej struktury.

### P01 — wykonane 2026-09-08

- Commity: `5d8d848` (kontrakty `application/control.py`, ledger `application/watch_state.py`, `RequestOrigin`/`RebuildRequest`, schemat 2 subskrypcji z migracją v1), `8135508` (poprawki po niezależnym przeglądzie: ponowne `add`/`subscribe` zachowuje `enabled`/`end_state`/`anilist_id`/korektę opóźnienia; plik stanu nie do zdekodowania daje `ConfigError`, a `save` nadal działa; migracja tylko z wersji 1; `save` zawsze pisze bieżącą wersję schematu).
- Bramki po `8135508`: `ruff check` czysto, `ruff format --check` czysto, `mypy` win32 i linux czysto, `pytest` exit 0 (3598 testów po `5d8d848`, plus 5 nowych), `pre-commit run --all-files` czysto.
- Przegląd niezależny (świeży kontekst, Opus): PASS WITH FINDINGS; 2 poważne i 2 mniejsze naprawione w `8135508`; sugestie (wyprowadzanie kluczy z `dataclasses.fields`, parametr `policy` w `auto_admissible` obok `state.policy`) odłożone do P02/P04.
- Migracja produkcyjna: `config/subscriptions.json` przeszedł na schemat 2 przy pierwszym `load()` nowego czuwania (09:40), kopia `subscriptions.json.v1.bak`, 25 wpisów, 58 odcinków `ORDERED`; cofnięcie wersji = przywrócenie kopii i restart czuwania (opisane w `application/AGENTS.md`).
- Kolejność etapów: P03 przed P02, żeby rezydent powstał na finalnym API koordynatora.

### P03 — wykonane 2026-09-08

- Commity: `2913de9` (`GraphCoordinator` z niezależnymi kontekstami, wspólne kolejki per zasób z rangą `USER`/`BACKGROUND`, brak zapasu future, pętla na `Condition` bez pollingu, `GraphScheduler.run` jako adapter, `AppService.submit_plan/cancel/set_background_admission/active_run_ids/close`), `119ad71` (poprawki po przeglądzie: obudzenie pętli po awarii snapshotu przy dopuszczeniu, sufit puli równy największemu ustawieniu, filtr sekretów w ledgerze po segmentach nazwy) oraz `_finish_run` w `try/finally` i anulowanie z czekaniem przy Ctrl+C w `execute()` (w commicie P02).
- Przegląd niezależny: FAIL na trzech ścieżkach awaryjnych (zawieszenie przy błędzie snapshotu, brak `finally` w domknięciu runu, Ctrl+C bez anulowania) — wszystkie naprawione i pokryte testami, które bez poprawki padają (sprawdzone ręcznie). Pozytywnie zweryfikowane: pierwszeństwo realne, limity wspólne, handshake `_signal`, księgowość future, sesje.
- Dowiedzione AC: AC-020 (ręczny gotowy task dostaje następny slot przed buforowanym tłem, testy dla tłumaczenia/TTS/publikacji), część AC-002 (sterowanie `set_background_admission` podczas trwającego taska), AC-006 (wyłączenie tła kończy rozpoczęte i nie startuje nowych).
- Otwarte: `max_pending_per_resource` zostaje w API do P08; `RunHandle.resolve/fail` publiczne.

### P02 — wykonane 2026-09-08

- Commit: `feat(cli): add the resident owner with an authenticated local control channel` (po `119ad71`): `platform/local_control.py` (AF_PIPE/AF_UNIX, `authkey`, JSON `send_bytes`/`recv_bytes`, limit ramki 1 MiB, outbox scalający per `task_id`), `application/automation.py` (`AutomationOwner`: jeden wątek właściciela, pula I/O 2, trwałość przed odpowiedzią, `CommandReceipt`, `STALE_INSTANCE`/`STALE_PREVIEW`/`CONFLICT`, marker R-028, `shutdown` czekające na aktywne zlecenia, synchronizacja przełącznika Auto z zapisanym stanem przy starcie), `cli/watch.py::run_resident` pod `resident.lock`, ukryta komenda `anishift watch resident`, `cli/control.py` klient, `ANISHIFT_CONFIG_DIR` w `paths.py`, `watch status` z linią rezydenta. Stara droga (`anishift watch` z oknami partii) pozostaje domyślna (D-12).
- G1 (sterowanie) na tym Windows z katalogami tymczasowymi: rezydent przez `pythonw`, `status`, `set_auto` zapisany przed odpowiedzią, powtórzony `command_id` bez skutku, zły klucz odrzucony (`AuthenticationError`), `icacls control.key` = tylko bieżące konto, brak nasłuchu TCP (`netstat`), `shutdown` → kod 0 i usunięty `instance.json`.
- Bramki po commicie: ruff, format, mypy (win32 i linux), pełny pytest exit 0, pre-commit czysto (po usunięciu pięciu komentarzy w testach, które hook odrzucił).
- Odchylenia: snapshot ustawień zlecenia z jawnej listy 15 pól; `start` sprawdza aktualność przez `stat` źródeł grup podglądu, nie pełny `discover()`; `preview` na razie tylko w wariancie Auto (zaawansowany Manual w P04); `COMMAND_TIMEOUT_S = 300` dobrany, nie zmierzony.

### Audyt i częściowe P04 — 2026-09-12

- `61d743f`: trzy odtworzone błędy pozyskania: ponowne zamówienie nowszej wersji odcinka przy wcześniejszej luce, przepuszczanie jawnego sezonu 2 przez subskrypcję sezonu 1, brak ograniczenia znaną długością sezonu. Trzy nowe testy najpierw FAIL, po poprawkach cały moduł subskrypcji PASS.
- P04: `plan_auto` i fasada przyjmują istniejący `RebuildRequest` oraz nadpisania ustawień ograniczone do zlecenia. Auto wykorzystuje gotowe produkty; force odtwarza wskazane produkty i ich rzeczywistych konsumentów. Stare pliki pozostają do poprawnej publikacji. Gotowy miks nie zastępuje brakującego suchego głosu.
- Ręczny rozpoczyna z pustym zaznaczeniem. Wybrane odcinki przechodzą bezpośrednio do zbiorczego podglądu; dostępne są również dotychczasowa edycja zaawansowana, regeneracja lektora oraz polskich napisów. Test klawiatury wykonuje wybór wyłącznie 3 i 8. Planowanie i wykonanie panelu nadal wymagają przepięcia na rezydenta.
- Korekta testów starego zachowania: gotowe polskie napisy mogą być wejściem zwykłego Auto (R-017), więc dawny bezwarunkowy zakaz ich użycia obowiązuje tylko przy jawnym force. Test własności sprawdza oba warianty i zachowanie oryginalnego deskryptora.
- Kontrole po integracji: `uv run pytest` — 3743 passed, 11 skipped (9 sieciowych, 2 wymagające niedostępnych symlinków), 32,68 s; Ruff check i format PASS; mypy win32 i linux PASS, 498 plików. Po tym przebiegu zmieniono wyłącznie nazwy parametrów pomocniczej fabryki testowej dla zgodności z protokołem i odstępy przy nagłówkach sekcji; obie platformy mypy sprawdzono ponownie.
- Audyt P02 odtworzył gubienie zdarzenia przy ACK subskrypcji, osierocone rezerwacje, brak rozliczenia nieoczekiwanego błędu runu, niepewne przyjęcie przy awarii zapisu receipt, zawieszenie shutdown przy oczekujących taskach tła oraz nadpisanie Wyłącz przez spóźniony wynik wyszukiwania. Poprawki są w toku; nie oznacza to ukończenia P02/P04 ani recovery.
- Poprawki P02: ACK subskrypcji nie gubi równoczesnego zdarzenia; uwierzytelnianie ma termin per klient; rezerwacje i podglądy należą do połączenia i wygasają po rozłączeniu, także podczas wolnego podglądu. Przyjęcie zamiaru i receipt są zapisywane razem przed submit; awaria wykonania zachowuje tę samą tożsamość zlecenia. Nieoczekiwany wyjątek runu wraca do właściciela i nie blokuje shutdown.
- Bezpieczny stop: koordynator kończy aktywne taski bez anulowania i zatrzymuje dopuszczanie pozostałych. Zlecenie otrzymuje `PAUSED`, a staging pozostaje chroniony przed cleanup, także podczas następnego runu po restarcie. Test integracyjny przechodzi przez rzeczywistą fasadę i pliki tymczasowe. Automatyczne odtworzenie tego stagingu nie jest jeszcze zaimplementowane.
- Bramki po poprawkach P02: pełny pytest — 3748 passed, 11 skipped, 52,88 s; Ruff check i format PASS; mypy win32 i linux PASS (498 plików).
- Podgląd rezydenta przyjmuje jednorazowy preset, nadpisania ustawień i istniejący `RebuildRequest`, a w Manual pełne `GroupIntent` wybranego zakresu. Wadliwy lub pusty `group_ids` jest odrzucany, zamiast uruchamiać całą bibliotekę. Walidacja JSON korzysta z już używanego Pydantic. Przyjęty zamiar zachowuje wszystkie ustawienia i produkty per grupa; stare zapisy bez tych danych nadal się wczytują.
- Dowód granicy planowania: rzeczywisty lokalny kanał przyjmuje tylko 3 i 8, zachowuje wybór głosu, tempo, priorytet języków, opcje silnika oraz pełne zamiary po zapisie/odczycie; preferencje globalne pozostają niezależne. Pełne bramki: 3758 passed, 11 skipped, 28,24 s; Ruff i mypy win32/linux PASS (499 plików).
- Otwarte: integracja zdalnego panelu i rejestracja jego zewnętrznych źródeł; rozliczanie wyników subskrypcji przez właściciela z generacją; odtworzenie po awarii; wymagane dowody publikacji częściowej. P05–P08 pozostają niewykonane.
- Organizacja: dalsza praca bez subagentów na życzenie właściciela; spójne poprawki i ukończone części otrzymują osobne commity po bramkach.

## 15. Korekty po przeglądzie wykonawcy (2026-09-08)

Przegląd planu względem spec.md i kodu `a7d319f` (przeczytane w całości: `scheduler*.py`, `service.py`, `sessions.py`, `intents.py`, wejścia `planner.py`, `cli/watch.py`, `application/watch.py`, `cli/run.py`, `interactive/app.py`, `subscriptions.py`, `acquisition.py`, `qbittorrent.py`, wszystkie scoped AGENTS). Plan jest zgodny ze specyfikacją; poniższe decyzje domykają luki, w których wykonawca musiałby zgadywać. Obowiązują razem z sekcjami 1–13; przy sprzeczności wygrywa ta sekcja.

**D-01. Rezydent planuje, panel wysyła zamiary.** Panel nigdy nie serializuje `ExecutionPlan`. Polecenie podglądu niesie listę `group_id`, identyfikator presetu albo jednorazowe nadpisania (`AutoPresetDraft`, run-only overrides ustawień, żądanie odtworzenia), a dla zaawansowanego Manual pola `GroupIntent` oraz rejestracje plików zewnętrznych (ścieżka, rola, język). Rezydent wykonuje `discover`, `register_external_*`, `plan_auto`/`plan_manual` i odpowiada podglądem: dla każdej grupy produkty zachowane, do wykonania, blokery i ostrzeżenia, plus `preview_id` i fingerprint wejść. Start = `preview_id`; nieaktualny fingerprint odsyła do ponownego podglądu. Jedyna inspekcja i jej cache żyją w rezydencie. Gdy rezydent nie działa, panel uruchamia go (`pythonw`, bez konsoli) i dopiero potem się łączy.

**D-02. Postęp przez kanał.** `RunEvent` jest serializowany polami (`run_id`, `group_id`, `task_id`, rodzaj, stan, procent, komunikat po sanitizacji) i wysyłany do podłączonych paneli; rezydent scala zaległe zdarzenia per `task_id`, więc wolny panel dostaje ostatni stan, nie kolejkę. Przy podłączeniu panel otrzymuje snapshot aktywnych zleceń (grupy, etykiety źródeł, taski z rodzajem i stanem, procenty, wyniki) i odtwarza z niego wiersze `RichRunProgress`. `RichRunProgress` dostaje konstruktor ze snapshotu; obecny konstruktor z `PreparedRun` zostaje adapterem dla testów.

**D-03. Migracja subskrypcji bez identyfikatora AniList.** Obecne 25 wpisów nie ma `anilist_id`. Migracja wykonuje jedno wyszukanie tytułu na wpis i wiąże automatycznie, gdy `series_forms` kandydata pokrywa serię, a sezon zgadza się ze znacznikiem; pozostałe wpisy są widoczne w Stanie jako „wymaga powiązania" z akcją Powiąż. Decyzja właściciela z 2026-09-08: wpis bez powiązania z AniList NIE zatrzymuje się. Sprawdza dalej co godzinę jak dziś (`recheck_interval_s`), jest w Stanie podpisany „bez kalendarza, sprawdzanie co godzinę", a próba powiązania ponawia się w rytmie ustawień retry. Gdy powiązanie się uda (automatycznie albo przez Powiąż), wpis przechodzi na rytm według premier. Spec R-009 („bez terminu wpis czeka") obowiązuje tylko dla wpisu powiązanego, którego kalendarz nie podaje daty.

**D-04. Ikona i powiadomienia.** „Otwórz" uruchamia panel w nowym oknie konsoli (`wt.exe`, gdy jest w PATH, inaczej domyślna konsola) z argumentem otwierającym Stan; gdy panel jest już podłączony, rezydent wysyła mu polecenie pokazania Stanu zamiast otwierać drugie okno. Powiadomienia Windows to balon ikony (`Shell_NotifyIcon`, `NIF_INFO`), bez procesu PowerShell.

**D-05. Home.** Pozycja „Auto" prowadzi do Stanu z przełącznikiem Auto oraz akcjami „Uruchom teraz" (wszystkie gotowe grupy, jak dzisiejsze Auto) i „Auto dla zaznaczonych". Ręczny, Anime, Ustawienia i Wyjście bez zmian pozycji. Wyjście z panelu nie kończy rezydenta.

**D-06. Techniczne komendy.** `anishift watch` = rezydent (to samo zadanie autostartu). `run --preset` i `subs check` przy działającym rezydencie delegują do niego i czekają na wynik przez kanał, drukując dotychczasowy raport; bez rezydenta `run --preset` wykonuje plan w procesie przez adapter `run(plan)` pod tą samą blokadą procesu, więc nigdy nie ma dwóch właścicieli. `watch stop` = „Zakończ AniShift". `watch batch` znika w P08 z komunikatem migracyjnym.

**D-07. Wspólne limity.** Koordynator dostaje dostawcę limitów czytającego bieżące preferencje; `plan.settings` nie wyznacza limitów zasobów. Executor ma `max_workers` równe maksimum dopuszczanemu przez katalog ustawień, a faktyczne dopuszczanie liczy aktywne taski per zasób względem aktualnego limitu. Reguła SAPI = 1 i liczenie ekstrakcji z rdzeni pozostają.

**D-08. Żądanie odtworzenia w plannerze.** `plan_auto` przyjmuje `RebuildRequest` (zbiór `ProductKind` do odtworzenia) i nadpisania run-only. Planner nie reużywa READY dla wskazanych rodzajów i ich zależnych konsumentów; tworzy nowe deskryptory `MISSING`/`DURABLE` z `planned_destination` równym ścieżce istniejącego produktu i `preserved_path` na tę ścieżkę, korzystając z istniejącej semantyki `preserved_path` w `_durable_target`. Identyfikator nowego deskryptora różni się od odkrytego produktu. Publikacja `replace` zastępuje stary plik dopiero po walidacji.

**D-09. Ustawienia z panelu.** Panel zapisuje `settings.json`, `presets.json` i `.env` istniejącą drogą `AppService`, a po zapisie wysyła rezydentowi polecenie przeładowania; rezydent przeładowuje preferencje pod własną blokadą, a trwające zlecenia zachowują swój snapshot.

**D-10. Dowód pod G3.** Zainstalowana binarka (`C:\Program Files\qBittorrent\qbittorrent.exe`) zawiera parametry `--profile=`, `--configuration=` i `--webui-port=` (sprawdzone 2026-09-08). Profil zarządzany: `config/qbittorrent/` z własnym portem Web UI z ustawień, własnym hasłem i kategorią; osobista instancja właściciela na porcie 8080 pozostaje nietknięta. Uzgodnienie migrowanych `taken` sprawdza hash w obu instancjach tylko do odczytu.

**D-11. Testy platformowe.** Testy realnego Win32 i potoków są oznaczone `integration` i pomijane poza Windows przez `sys.platform`; nazwy potoków i kluczy są losowe per test, bo suite biegnie równolegle.

**D-12. Rozwój przy działającym czuwaniu.** Stare czuwanie działa z tego drzewa roboczego i uruchamia okna partii importujące bieżący kod. Każdy commit etapu przechodzi bramki, nowe moduły wchodzą przed przepięciem, a stara droga pozostaje domyślna do P08; wtedy stare czuwanie zostaje zatrzymane i zadanie autostartu uruchamia rezydenta.

**D-13. Rezerwacje i marker ręcznej obsługi.** Rezerwacja i marker R-028 są kluczowane `(group_id, fingerprint źródeł)` z `source_fingerprint` z `application/watch.py`; produkty AniShift nie wchodzą do fingerprintu, więc publikacja nie unieważnia własnej decyzji.
