---
kind: research
status: completed-for-planning
created: 2026-09-08
baseline: a7d319f334a062d0fe016c774d9a5fb4fccbe9b6
branch: work/local-automation/06-efficiency
---

# Research: prosty model sterowania AniShift

## 1. Pytanie i zakres dowodu

Jak połączyć ręczny wybór odcinków, automatyczne reagowanie na pliki i niezależnie sterowane subskrypcje, wykorzystując istniejący kod, bez drugiego wykonawcy i ciągłego odpytywania?

Podstawa produktowa: ostatnie doprecyzowanie właściciela w rozmowie oraz zgodne z nim wcześniejsze ustalenia. Podstawa techniczna: odczyt plików gałęzi `work/local-automation/06-efficiency`, z przypiętym HEAD `a7d319f334a062d0fe016c774d9a5fb4fccbe9b6`, i dokumentacja producentów wymieniona poniżej. Nowy model jest zapisany w [spec.md](../spec.md), a decyzje implementacyjne w [plan.md](../plan.md).

To analiza statyczna i research kontraktów, nie wykonanie aplikacji. Nie przeprowadzono testów na Windowsie właściciela, nie pobrano odcinków, nie uruchomiono klienta torrent, nie wykonano pełnej suite ani nowych pomiarów CPU/RAM/energii. Liczby z wcześniejszych notatek pomiarowych nie są przedstawiane jako odtworzone wyniki.

Skille simple, specification, research i planning odczytano z dostarczonego `wip.zip`. Starszy materiał `Badanie AniShift TUI.txt` opisuje inny etap interfejsu; nie jest podstawą do przywrócenia slash commands, OpenCode-like prototypu ani odrzuconego Textuala.

## 2. Fakty ustalone w kodzie

Odnośniki K01–K15 prowadzą do dokładnego analizowanego commitu, a nie ruchomej gałęzi. Nazwy proponowanych nowych modułów w planie nie są twierdzeniem o ich obecnym istnieniu.

### F01. Auto i Manual już mają wspólny rdzeń

`planner.py::plan_auto` tworzy automatyczne `GroupIntent`, a `plan_manual` przyjmuje intencje z jawnymi wyborami. Obie funkcje delegują do `_plan` i `_GroupPlanner`. `AppService` udostępnia te dwie drogi, a `execute` tworzy sesję i ten sam `GraphScheduler`. W CLI `prepare_auto_run` i `execute_plan` są już współdzielonymi granicami. [K01, K02, K03]

**Wniosek projektowy:** prosty Manual może korzystać z automatycznego doboru źródeł, zachowując pochodzenie użytkownika. Zaawansowany Manual nie musi zostać usunięty. Regeneracja może rozszerzyć wejście istniejącego Auto, zamiast otrzymać trzeci planner.

### F02. Regeneracja nie jest obecnie gotową funkcją

`RunMode` zawiera AUTO i MANUAL. Gotowe artefakty są ponownie wykorzystywane; wykonawca wymaga, aby produkowane deskryptory wyjść były `MISSING`, a nie oryginalnym `SOURCE`. `ArtifactStore` publikuje zwalidowane wyjścia i nie pozwala workerowi samodzielnie podmieniać wspólnego stanu. Samo wywołanie Auto z innym głosem nie jest wystarczającym dowodem, że gotowy lektor zostanie przebudowany. [K01, K04]

**Wniosek projektowy:** potrzebne jest jawne żądanie odtworzenia i projekcja nieaktualnych produktów w plannerze, bez usuwania poprzednich dobrych plików. R-020 nowej specyfikacji mówi o Auto, nie o „szczególnym Manual”.

### F03. Obecny scheduler nie przyjmuje jeszcze niezależnych planów na żywo

`GraphScheduler.run` pracuje na jednym niezmiennym `ExecutionPlan`, z jednym snapshotem ustawień, handlerem i sesją. Kolejki są per zasób. Admission wysyła do executorów do limitu workerów powiększonego o `max_pending_per_resource`. `NaturalOrderGate` kontroluje możliwość przekazania wyników kolejnych grup. [K04, K05]

**Wniosek projektowy:** samo `appendleft` nie gwarantuje priorytetu, kiedy tło jest już w prywatnym buforze executora. Dołączenie ręcznego planu z innym głosem wymaga też odrębnego kontekstu ustawień. W planie wybrano rozszerzenie tego samego koordynatora, nie nowy scheduler.

### F04. Aktualne blokady nie rozwiązują współpracy panelu z tłem

`AppService._run_lock` i aktywny run należą do instancji obiektu. `ProcessLock` w czuwaniu chroni proces watchera, nie każdą możliwą niezależną instancję AppService. `execute` wywołuje cleanup z listą obejmującą aktualny run; rozszerzenie do wielu kontekstów musi uwzględnić wszystkie aktywne sesje. [K02, K06]

**Wniosek projektowy:** potrzebny jeden właściciel wykonania i stanu oraz cienki lokalny kanał sterowania. Oddzielne procesy wykonujące Manual i Auto z osobnymi blokadami nie dają wymaganej wyłączności ani wspólnych limitów.

### F05. Watcher pomija skanowanie podczas partii

W `cli/watch.py::_watch_loop` żywe okno partii powoduje sleep i `continue`, przed skanem biblioteki i sprawdzeniem subskrypcji. `check_all` jest synchroniczne. `application/watch.py` ma interwał skanu 5 s i stabilizację 10 s. `WatchLedger` przechowuje stan w pamięci, a zamknięcie okna wiąże grupy z zakończeniem obserwacji danej wersji wejścia. [K06, K07]

**Wniosek projektowy:** samo schowanie okna nie naprawi reakcji na ręczny plik, restartu i zużycia zasobów. Trzeba oddzielić oczekiwanie na zdarzenia od wykonywania planów i utrwalić potrzebny zamiar.

### F06. Istnieje cache inspekcji, lecz jego unieważnienie jest zbyt szerokie

`AppService.discover` serializuje discovery i ponownie używa poprzedniej inspekcji przy identycznym odcisku całego workspace. Zmiana odcisku uruchamia inspekcję discovery. `discovery.py` już rozpoznaje źródła i produkty, grupuje ścieżki oraz pomija zarządzane temp, ukryte wpisy i niebezpieczne przejścia po symlinkach. [K02, K08]

**Wniosek projektowy:** rozwinąć istniejącą granicę do cache grup, a nie budować własny inventory w UI. Oszczędne czuwanie ma korzystać z istniejących klasyfikatorów, ale nie ze stałego pełnego probe.

### F07. Subskrypcja śledzi przekazanie torrenta, nie ukończenie źródła

`SubscriptionService.check` szuka wydań, zleca `download`, następnie `_confirmed` sprawdza ich hashe w kliencie. `_advance` aktualizuje `taken` i numery. `check_all` obejmuje wszystkie zapisane subskrypcje. Stworzenie wpisu wymaga obecnie numerowanego `ReleaseChoice`; w modelu nie ma pełnego niezależnego enabled/disabled i harmonogramu emisji. Store stosuje JSON i atomową podmianę pliku. [K09]

**Wniosek projektowy:** zachować ten store i reguły numeracji, lecz rozdzielić zamiar, przyjęcie transferu i kompletny plik. Migracja nie może nazwać `taken` sukcesem pobrania. Dodanie nadchodzącego sezonu wymaga nowej drogi wejścia, nie tylko nowego przycisku.

### F08. Katalog już zna sezon, ale nie pobiera potrzebnych terminów

Adapter AniList ma zapytania wyszukania i relacji/prequeli. Analizowane zapytania nie pobierają harmonogramu emisji. Model pozyskania ma `SeasonContext` i reguły `read_episode`, które rozróżniają numer lokalny, absolutny i inny sezon. [K10, K11]

**Wniosek projektowy:** korzystać z tych samych tożsamości i numeracji. Dodać potrzebne odczyty harmonogramu, a nie traktować znajomości dat jako już zaimplementowanej cechy aplikacji.

### F09. Nyaa ma przydatne dane do oszczędnego dopasowania

Istniejący adapter RSS wysyła oddzielne żądanie na każdą kategorię, scala po info hash i odczytuje `pubDate` do `Release.published`. Wyszukiwanie interaktywne może rozszerzać tytuły i numery oraz ma budżet faktycznych requestów. RSS oddaje najnowsze trafienia, nie dowód kompletnej historii sezonu. [K11, K12]

**Wniosek projektowy:** zapisać ustalone dane grupy/kategorii i używać ich w należnym sprawdzeniu. Datę publikacji można zestawić z zachowaną wiarygodną datą emisji; czasu pobrania i mtime nie używać jako zastępstwa. Budżet liczy transport, nie tylko wywołania metody search.

### F10. qBittorrent jest już zależnością, ale nie ma pełnego zarządzania cyklem życia

Obecny klient WebUI obsługuje version, preferences, add i listę torrentów oraz jedno leniwe logowanie. Platforma wykrywa binarkę i przygotowuje ustawienia. Konfigurator chroni INI przed edycją podczas działania klienta i robi kopię. Kod oraz AGENTS opisują konfigurację qBittorrent 5, w tym hasło WebUI. To nie jest dowód istnienia bezpiecznego trybu uruchom/zakończ własną instancję na żądanie. [K13, K14]

**Wniosek projektowy:** osobna wąska granica własności procesu jest potrzebna. Sam hash torrenta, kategoria `anishift`, PID lub odpowiadający localhost nie upoważniają do zamknięcia osobistego klienta właściciela.

### F11. UI i testy dają punkty rozbudowy

Obecny interfejs to Home z Auto, Ręczny, Anime, Ustawienia i Wyjście w jednym rendererze Prompt Toolkit. Manual ma draft wypełniany z presetu i jawny podgląd/Start. Anime prowadzi I/O poza renderem, z generacją do odrzucania nieaktualnych wyników. Test schedulerów ma fake handler z licznikami i barierami; testy subskrypcji modelują queued hashes, a nie pełną kompletność transferu. [K03, K15]

**Wniosek projektowy:** zachować obecny frontend i rozwinąć testy prawdziwych granic. Do testu „pobrane” nie wystarczy ten sam mock, który potwierdza tylko „dodane”.

### F12. Stare pakiety są niespójne z aktualnym zakresem

Stary indeks lokalnej automatyzacji opisuje między innymi SQLite, inbox i katalogi rewizji. Aktualne reguły repo i działający kod trzymają źródła/produkty obok siebie, stan w `config/`, a plany 01–05 mają własne wyniki. Plan 06 w baseline jest notatką z odrzuconą specyfikacją w załączniku, nie obowiązującym kompletnym kontraktem nowego modelu.

**Wniosek projektowy:** nowy workstream musi mieć jedno wskazane wejście, a dawne indeksy i plan 06 prowadzić do niego. Historia pozostaje w Git i starszych plikach, bez realizacji kilku sprzecznych masterplanów.

## 3. Sprawdzone kontrakty zewnętrzne

### E01. Zdarzenia katalogowe Windows

Microsoft dokumentuje `ReadDirectoryChangesW`, obserwację poddrzewa i asynchroniczne użycie. Przepełnienie bufora może utracić zdarzenia; przypadki wskazujące utratę wymagają odtworzenia zawartości katalogu. Nie wszystkie środowiska systemu plików muszą obsługiwać tę metodę. [W01]

**Decyzja:** watcher zdarzeniowy z uzgodnieniem na start, resume i utratę zdarzeń. Nie obiecywać bezwarunkowej kompletności strumienia, ani używać każdego eventu jako dowodu ukończenia kopiowania. W G1 trzeba sprawdzić rzeczywisty nośnik.

### E02. Ikona nie wymaga nowego frameworka UI

Windows Shell udostępnia `Shell_NotifyIcon` i callbacki do okna aplikacji. Widoczność w obszarze powiadomień/overflow zależy od systemu i użytkownika. Po utworzeniu taskbara ponownie rozsyłany jest `TaskbarCreated` do okien top-level, a aplikacja odtwarza ikonę. [W02, W03]

**Decyzja:** wąski adapter Win32 przez standardowe `ctypes`, ukryte okno top-level i pompa komunikatów. Samo message-only window nie wystarczy do opisanego scenariusza broadcastu. Restart powłoki nie jest restartem planów.

### E03. Lokalny transport jest dostępny w standardowej bibliotece

Python opisuje `multiprocessing.connection.Listener` i `Client`, rodziny adresów, uwierzytelnianie `authkey` oraz ramki `send_bytes`/`recv_bytes`. `recv()` deserializuje pickle; nie jest odpowiednim parserem jawnego bezpiecznego protokołu z niezweryfikowanym payloadem. Mechanizmy Event/Condition pozwalają czekać na zmianę zamiast aktywnie sprawdzać stan. [W04, W05]

**Decyzja:** lokalne AF_PIPE/AF_UNIX, ograniczony JSON, kontrola użytkownika i wersji, bez TCP ani arbitralnego RPC. Uwierzytelnienie nie zastępuje kontroli uprawnień pliku z kluczem; G1 obejmuje również tę granicę.

### E04. WebUI udostępnia stan, ale jego odczyt nadal kosztuje request

Dokumentacja qBittorrent 5 opisuje `torrents/info`, dane postępu/stanu, szczegóły plików, synchronizację przyrostową `sync/maindata` z `rid` oraz zakończenie aplikacji. Synchronizacja przez HTTP nie jest powiadomieniem push. Shutdown dotyczy instancji aplikacji, a nie samej kategorii torrentów. [W06]

**Decyzja:** zbiorczy odczyt podczas realnych transferów, szczegóły plików tylko gdy potrzebne do potwierdzenia. Nie pobierać statusu raz na wiersz UI i nie uruchamiać klienta dla pustego szukania. Sprawdzić rzeczywistą wersję WebAPI i kody odpowiedzi w G2, bez odrzucania obsługi już znanych kodów przyjęcia.

### E05. Oddzielny profil na Windows pozostaje granicą do sprawdzenia

Dokumentacja trybu portable rozróżnia platformy i warianty profilowania. Wzmianka o `--profile` w materiale dotyczącym Linuxa nie wystarcza do stwierdzenia, że dowolna zainstalowana wersja Windows zapewni takie samo zachowanie. [W07]

**Decyzja:** G3 sprawdza konkretną binarkę, uruchomienie profilu, endpoint i tożsamość procesu. Bez dowodu używać istniejącej zewnętrznej instancji konserwatywnie i nie zamykać jej automatycznie. To nie jest dowód ukończenia R-015.

### E06. AniList nie daje obietnicy pełnego archiwum emisji

Oficjalny opis `AiringSchedule` zawiera `airingAt`, `episode` i `mediaId`; zastrzega skupienie na poprawności przyszłych danych. Dokument ograniczeń podaje standardowy limit, a jednocześnie ostrzeżenie o okresowym ograniczeniu do 30 requestów/minutę i opisuje nagłówki limitu/resetu oraz burst limiting. [W08, W09]

**Decyzja:** zachowywać potrzebne zaobserwowane daty, nie zakładać nieograniczonej historii i nie wpisywać jednego rzekomo trwałego limitu do logiki. Respektować faktyczne odpowiedzi, ograniczać własne żądania i sprawdzać dokładny kształt zapytania w G2. Badanie dokumentacji nie potwierdza bieżącej przepustowości API na koncie użytkownika.

## 4. Wybór rozwiązań i odrzucone skróty

| Wybór | Uzasadnienie | Odrzucony skrót |
| --- | --- | --- |
| Jeden właściciel i obecny scheduler | Wyłączność, wspólne limity i priorytet bez rywalizacji procesów. | Drugi silnik Manual lub kolejka regeneracji. |
| Regeneracja jako parametry Auto | Ten sam dobór zależności i brak duplikacji przetwarzania. | Kasowanie plików przed startem albo nowy RunMode. |
| Zapis zamiaru/rezultatu w istniejącej strukturze config | Recovery jest potrzebne; rozproszona infrastruktura nie jest. | SQLite/broker jako warunek tego etapu. |
| Terminy konkretnego odcinka i ograniczone okna | Znana przyszłość eliminuje bezużyteczne wyszukiwania. | Cała lista co godzinę, wieczne szukanie zakończonego sezonu. |
| Natywne zdarzenia i inspekcja grup | Zmiana jednego pliku nie uzasadnia probe całej biblioteki. | Schowanie terminala przy zachowaniu kosztownej pętli. |
| Wspólne realne liczniki HTTP | Różne warstwy i retry nie mogą ukrywać ruchu. | Liczenie tylko wywołań logicznego search. |
| Konserwatywna własność qBittorrenta | Priorytetem jest niezakłócanie pracy użytkownika. | Zabijanie po nazwie procesu lub kategorii. |
| Prostota Manual jako wybór zakresu | Właściciel nie chce ręcznie budować grafu wykonania. | Obowiązkowe przechodzenie każdego ustawienia i źródła. |

Wartości 3 h opóźnienia bez historii, 1 h ponownego sprawdzenia, 72 h okna, 30 min aktywnego zastoju oraz początkowy budżet retry są propozycjami ustawień odziedziczonymi z poprzedniego projektu i jawnie oznaczonymi w nowej specyfikacji. Nie pochodzą z pomiaru grup i nie stanowią wyniku tego researchu.

Nie badano automatycznego śledzenia całej franczyzy, dodatkowych indeksów, VPS, Google Drive, nowego renderera ani importerów MAL. Nie są potrzebne do rozstrzygnięcia tej zmiany.

## 5. Rejestr źródeł

### Kod i dokumenty repozytorium

- K01: [intents.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/intents.py), [planner.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/planner.py).
- K02: [service.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/service.py), zwłaszcza discover/plan_auto/plan_manual/execute; [application AGENTS](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/AGENTS.md).
- K03: [CLI AGENTS](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/cli/AGENTS.md), [README aplikacji](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/README.md).
- K04: [scheduler_runtime.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/scheduler_runtime.py), ArtifactStore i publikacja.
- K05: [scheduler.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/scheduler.py), [scheduler_contracts.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/scheduler_contracts.py).
- K06: [cli/watch.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/cli/watch.py), [platform AGENTS](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/platform/AGENTS.md).
- K07: [application/watch.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/watch.py).
- K08: [discovery.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/discovery.py).
- K09: [subscriptions.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/subscriptions.py).
- K10: [anilist.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/services/catalog/anilist.py).
- K11: [acquisition.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/application/acquisition.py) i reguły w K02.
- K12: [nyaa.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/services/torrents/nyaa.py).
- K13: [qbittorrent.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/services/torrents/qbittorrent.py).
- K14: [platform AGENTS](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/platform/AGENTS.md), [pyproject.toml](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/pyproject.toml), [root AGENTS](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/AGENTS.md).
- K15: [manual.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/anishift/cli/interactive/manual.py), [test_scheduler.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/tests/application/test_scheduler.py), [test_subscriptions.py](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/tests/application/test_subscriptions.py), [tests AGENTS](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/tests/AGENTS.md).
- Historia F12: [indeks starego pakietu](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/docs/plans/local-automation/README.md), [plan 06 w baseline](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/docs/plans/local-automation/plans/06-queue-and-control.md).

### Źródła producentów sprawdzone 2026-09-08

- W01: Microsoft, [ReadDirectoryChangesW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-readdirectorychangesw).
- W02: Microsoft, [Notifications and the Notification Area](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area).
- W03: Microsoft, [The Taskbar](https://learn.microsoft.com/en-us/windows/win32/shell/taskbar), sekcja `TaskbarCreated`.
- W04: Python 3.14, [multiprocessing: Listeners and Clients](https://docs.python.org/3.14/library/multiprocessing.html#listeners-and-clients), także Connection i bezpieczeństwo deserializacji.
- W05: Python 3.14, [threading](https://docs.python.org/3.14/library/threading.html), Event/Condition.
- W06: qBittorrent, [WebUI API, qBittorrent 5.0](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29).
- W07: qBittorrent, [How to use portable mode](https://github.com/qbittorrent/qBittorrent/wiki/How-to-use-portable-mode).
- W08: AniList, [oficjalny opis AiringSchedule](https://github.com/AniList/docs/blob/master/docs/reference/object/airingschedule.md), odczytany blob `555fb90796dd7005fdad62c125ae2887715990c1`.
- W09: AniList, [oficjalne Rate Limiting](https://github.com/AniList/docs/blob/master/docs/guide/rate-limiting.md), odczytany blob `6b71f4b79dd09b898d0565790f7177e07facaef4`.

Oficjalne dokumenty opisują mechanizmy i kontrakty, ale nie zastępują prób G1–G3 ani pomiaru konkretnego komputera. Tam, gdzie dokumentacja nie rozstrzygnęła użycia zainstalowanej wersji Windows, granica została nazwana wprost zamiast zastąpiona przypuszczeniem.
