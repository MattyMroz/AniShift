# Subskrypcje AniShift — rzeczywisty przepływ i miejsca zatrzymania

## 1. Konkluzja

**Nie ma dowodu przyczyny awarii u użytkownika. Jest dowód, że subskrypcja może nie wywołać wyszukiwania albo nie znaleźć wydania dostępnego ręcznie, a panel nie rozróżnia dostatecznie tych sytuacji.** Nie można sprowadzić zgłoszenia do rankingu wydań.

- **USERREPORTED:** „subskrypcje w ogóle nie działają”, ręczne **D** działa. Brak przykładu subskrypcji, ustawień, czasu próby i logów.
- **DIRECT:** lokalna reprodukcja wykazała pominięcie numeracji absolutnej w zapytaniach catch-up subskrypcji. Przy atrapie indeksu zwracającej wydanie wyłącznie dla zapytań z numerem absolutnym otrzymano 0 pobrań wobec 1 ręcznego dodania przez tę samą prawdziwą `AcquisitionService`. Nośnym dowodem jest różnica list emitowanych zapytań, nie samo `downloaded=0`; wynik 0 vs 1 zależy od jawnie przyjętego zachowania atrapy.
- **DIRECT:** wcześniej przyszły odcinek bez indywidualnej daty pozostaje bez okna wyszukiwania po przejściu sezonu do `RELEASING`, również po odtworzeniu usługi. Ręczna ścieżka znajduje wydanie. To zachowanie zgodne z obecnym kontraktem kalendarzowym, nie samodzielny dowód błędu implementacji.
- **DIRECT:** terminalne zamówienie może wyglądać na liście jak `● Example [Group] · Brak terminu`, przy stopce `Praca`. Dodanie globalnego `subscriptions_problem` nie zmienia renderowanej klatki. Wynik ręcznego sprawdzenia z `problems=1` trafia do ogólnego „Polecenie przyjęte”.
- **DIRECT:** 140 istniejących testów przeszło, w tym rzeczywisty owner + IPC + lokalne atrapy: przyjęcie zakresu → zaległe odcinki → restart → blokada dostawcy → następny odcinek. Nie jest to system bez działającej ścieżki automatycznej.

Stan: `0e8a6bf9194d2786d426d3f3a58f48272b3eb087`, gałąź `work/local-automation/06-efficiency`, badanie 2026-09-22. Numery linii poniżej sprawdzone w tym stanie. `DIRECT` oznacza kod lub wykonaną reprodukcję; `INFERENCE` — wniosek warunkowy; `UNKNOWN` — brak dowodu runtime. Priorytety oznaczają wpływ i kolejność diagnostyczną, **nie prawdopodobieństwo przyczyny zgłoszenia**.

## 2. Mapa rzeczywistych wywołań

| Etap | Wywołanie i dowód w kodzie |
| --- | --- |
| Start panelu | `anishift/cli/main.py:153-174` zawsze tworzy `ResidentSession`; `anishift/cli/interactive/app.py:210-214` tworzy `StateController`, którego obserwator otwiera sesję (`anishift/cli/interactive/state.py:876-910`). `anishift/cli/control.py:28-36` łączy lub startuje rezydenta na żądanie. |
| Start rezydenta | `anishift/cli/watch.py:342-414`: blokada → owner → IPC → obserwator plików → publikacja instancji → `serve`. `anishift/application/automation.py:682-697`: odtworzenie blokad dostawców, receipt, źródeł, globalnej pauzy i harmonogramu. To aktualna droga; stary `run_daemon/check_all` nie jest domyślnym wykonawcą panelu. |
| Zamiar w Anime | **O** na podświetlonym odcinku lub grupie tworzy wyłącznie draft. Na grupie wybiera najwyższy kwalifikujący się numer, nie cały sezon od 1: `anishift/cli/interactive/anime.py:670-699`. Query dla rozpoznanego tytułu to nazwa serii z grupy + grupa (`:701-705`). |
| Zakres | `anishift/cli/interactive/subscriptions.py:28-42`: znane numery + liczba odcinków sezonu; zaznaczone od wybranego N wzwyż. Przy nieznanej liczbie powstaje przyszły ogon. Dopiero Enter → `_apply_draft` → `session.follow`: `anishift/cli/interactive/state.py:583-622`. Esc odrzuca draft. |
| Przyjęcie i zapis | `anishift/cli/resident.py:259-274` → `subscription_add`; `anishift/application/automation.py:3073-3095` wyznacza tożsamość i waliduje zakres → `:4348-4427` zapisuje receipt, `add_order`, `set_range`, kończy receipt i planuje sprawdzenie. `anishift/application/subscriptions.py:417-456` — wersjonowany magazyn atomowo przez plik tymczasowy + replace. |
| Zaplanowanie | `anishift/application/automation.py:3398-3417` → `SubscriptionService.next_check_at` (`anishift/application/subscriptions.py:877-912`). Termin UTC zamieniany na deadline monotoniczny. Pętla ownera czeka do deadline i woła `_poll_subscriptions` (`automation.py:755-791`). |
| Wykonanie poll | `anishift/application/automation.py:3419-3442`: zadanie na puli I/O → `_check_subscriptions` (`:3356-3396`) → **`check_due`**, nie `check_all`. Aktualizacje i admission wracają na wątek ownera. `_finish_io` ponownie planuje (`:1089-1091`). |
| Kalendarz / fallback | `anishift/application/subscriptions.py:928-1034`: aktywność i deadline → powiązanie lub odświeżenie kalendarza → przygotowanie dat → wygaszenie okien → wyznaczenie odcinków due. Brak odcinków due kończy wywołanie przed wyszukaniem. |
| Wyszukanie | `_offered` → `_search` → `AcquisitionService.search`, ewentualnie jeden catch-up po numerze: `anishift/application/subscriptions.py:1106-1134`. `anishift/application/acquisition.py:424-434` → źródło → parsowanie i filtr katalogu. Produkcyjny adapter Nyaa: `anishift/bootstrap.py:107-112`; RSS: `anishift/services/torrents/nyaa.py:125-170`. |
| Dopasowanie i wybór | `anishift/application/subscriptions.py:1654-1685`: seria, konkretna grupa, sezon, numer, zakres i długość sezonu. Dopiero wewnątrz zaakceptowanego numeru `_quality` wybiera wersję i seedy (`:1716-1717`). |
| Grab / admission | `anishift/application/subscriptions.py:789-848`: deduplikacja, odczyt hashy klienta, `admit`. `anishift/application/automation.py:3468-3501` zapisuje `PENDING_SEND` **przed** wywołaniem klienta. `anishift/application/acquisition.py:491-509` dodaje torrent do płaskiego workspace jako `stopped=True`. |
| Potwierdzenie | `anishift/application/subscriptions.py:1136-1152` sprawdza obecność hasha. `anishift/application/automation.py:3527-3566` zapisuje/uzgadnia acquisition; brak potwierdzenia nie oznacza bezpiecznego ponowienia. `ACCEPTED` nie oznacza kompletnego pliku. |
| Start transferu i powrót | `anishift/application/automation.py:3693-3749`: metadane → rezerwacja nazw → późniejszy start zawartości. `:3751-3776`: zapis transferów → projekcja do subskrypcji → zdarzenie stanu / inspekcja kompletnego źródła. |
| Status UI | `anishift/application/automation.py:3106-3145,5331-5357` buduje listę i stany pracy; `anishift/cli/interactive/state.py:899-946` pobiera ją po `state_changed`. Lista używa tylko nazwy, grupy, `enabled` i terminu (`:1256-1263`); szczegóły odcinków mają więcej etykiet (`anishift/cli/interactive/subscriptions.py:101-123`). |

## 3. Warunki startu, poll, grab i to, co widzi użytkownik

Wszystkie poniższe warunki są **DIRECT z kodu**; ich wystąpienie u użytkownika jest **UNKNOWN**.

| Warunek | Skutek | Widoczność / istotne ograniczenie |
| --- | --- | --- |
| Brak pracującego rezydenta | Brak automatycznego poll. Panel próbuje połączyć/startować. | Błąd połączenia i „Brak połączenia”, nie dowód błędu rankingu (`state.py:876-897,1180-1181`). `resident_status` nie uruchamia procesu (`cli/control.py:39-51`). |
| Globalne `auto_enabled=False` | Brak schedule; ręczne `subscriptions_check` i D również odmówione. Zapis zamiaru jest dozwolony. | Stopka „Wstrzymano”; zapis pauzy przeżywa restart. Uwaga: sam `AutomationPolicy()` ma False, ale **brak pliku stanu daje True** przez `_fresh_state` (`application/control.py:183`; `application/watch_state.py:235-262`). To zamierzona globalna pauza, nie błąd. D działające w tym samym ownerze i momencie przemawiałoby przeciw tej przyczynie. |
| `enabled=False` lub `end_state != ACTIVE` | `check_due` pomija wpis także po F; samo enable nie resetuje końca ani okien. | Kropka oznacza wyłącznie `enabled`, nie skuteczne monitorowanie (`subscriptions.py:943-946,1074-1083`; `state.py:1256-1263`). |
| Niezakończony receipt / globalny problem subskrypcji / trwa inne sprawdzenie | Automatyczny schedule nie jest uzbrojony. Admission także odmawia przy pending receipt. | `status` niesie pending i problem, ale panel nie renderuje globalnego `subscriptions_problem` (`automation.py:1298-1321,3398-3409,3477-3480`). |
| Błąd obliczenia `next_check_at` | Deadline ustawiony na None, warning „Subscription schedule is unavailable”. | Ta gałąź nie ustawia `_subscriptions_problem`; nie ma okresowego retry wyłącznie z niej (`automation.py:3410-3417`). Późniejsze zdarzenie może ponowić planowanie. |
| Niepowiązany wpis | Oddzielny budżet prób powiązania; nadal wyszukiwanie wydań wg `recheck_interval_s`. | Jednoznaczny alias i zgodność sezonu/offsetu wymagane przed związaniem (`subscriptions.py:1006-1055,1355-1371`). Niepowodzenie wiązania nie blokuje fallbacku. |
| Powiązany sezon | Terminy indywidualne + opóźnienie; domyślnie 3 h, kontrola co 1 h, okno 72 h. | „Czeka na wydanie” odnosi się do emisji, nie do faktycznego deadline szukania. Polityka siedzi w `WatchState`, nie jest bieżącą preferencją TTS/tłumaczenia (`control.py:93-109,183-190`; `subscriptions.py:1404-1485`). |
| Nowy jawny backlog od N | Dla dat historycznych `due=max(emisja+delay, requested_at)`; świeży wybór dostaje nowe ograniczone okno. Wybrane wcześniejsze numery poza N nie są wymagane. | Istniejący test i owner/IPC potwierdzają 2–7 teraz, 8 dopiero po terminie; nie można twierdzić, że cały catch-up jest zepsuty (`tests/application/test_subscriptions.py:1621-1640`; `test_automation.py:4847-4922`). |
| Przyszły sezon / HIATUS | Dzienny refresh przy HIATUS lub odległej znanej dacie; brak otwarcia wszystkich okien przez sam start sezonu. | Brak daty konkretnego odcinka może utrzymać `awaiting_airing`. F odświeża kalendarz, nie omija tej blokady (`subscriptions.py:1303-1352,1458-1534`). |
| Wygasłe okno / wyczerpane retry | Expiry następuje przed wyszukiwaniem. 3 błędy wydań mogą zakończyć odcinek jako MISSING; błędy kalendarza mają osobny budżet. | Okna nie odżywają po restarcie. F nie wznawia terminalnego wpisu; potrzebna istniejąca ścieżka jawnego powtórzenia. Zwykłe zaznaczenie nie resetuje terminalnego odcinka (`subscriptions.py:601-662,664-727,1537-1608`). |
| Blokada dostawcy | Deadline respektuje trwały cooldown; dla powiązanego sezonu Nyaa może nie zostać wywołane nawet przy F. | Kalendarz może pokazać błąd; terminy dostawców są w technicznym statusie (`automation.py:1327-1330,3448-3465`; `subscriptions.py:889-912,978-994`). |
| Seria / grupa / sezon nie pasują | Wydanie odrzucone przed rankingiem. Grupa porównywana dokładnie po casefold; nie ma „dowolnej grupy” ani automatycznego fallbacku grupy. | Brak osobnych liczników przyczyn odrzucenia subskrypcji (`subscriptions.py:1654-1685`). |
| Jakość, język, paczka, zakres | Katalog ukrywa brak rozdzielczości/<1080p, dub i brak języka; subskrypcja odrzuca paczki, brak numeru, inny sezon i numery poza zakresem/liczbą sezonu. | `min_resolution` jest zapisane, ale `_search` nie przekazuje go do katalogu: faktycznie działa globalne 1080p. Nowe wpisy i tak zapisują 1080p; brak dowodu różnicy ustawienia u użytkownika (`subscriptions.py:542,1129-1134`; `acquisition.py:323-359,424-427,740-747`). |
| Wydanie już przyjęte / niepewne | Nie dodaje ponownie hasha ani innego wariantu tego samego numeru w tej samej operacji. | Ochrona przed duplikacją, zgodna z kontraktem; `taken` oznacza przekazanie, nie pobrany plik (`automation.py:3481-3494`; `subscriptions.py:1201-1232`). |

F w panelu → `refresh_calendar=True`. To **nie** polecenie „ignoruj okna i szukaj wszystkich numerów”: `_due_episodes` nadal respektuje daty, odstęp od ostatniej kontroli i stany terminalne (`subscriptions.py:928-985,1267-1280,1374-1381`).

**Startup po logowaniu:** produkcyjny `run_resident(enable_tray=True)` wywołuje `_ensure_autostart`; jeśli zadanie jest `MISSING`, rejestruje je, a błąd jedynie loguje (`cli/watch.py:348-350,504-518`). Nie sprawdzano rzeczywistego zadania użytkownika. `README.md:20-23` opisuje start Auto off i ręcznie opcjonalny autostart; szczegółowa ścieżka kodu jest inna. Nie wolno wywnioskować „nowa instalacja ma wyłączone Auto” z domyślnej wartości samej dataclass.

### Przyszły sezon bez dostępnych grup — korekta wcześniejszego ustalenia

`anishift/cli/interactive/anime.py:415-445` ma działającą drogę przy pustych wynikach i wybranym kandydacie AniList: **O → wpisanie grupy → draft od 1 → wybór zakresu → Enter**. Potwierdził ją wykonany test `tests/cli/test_interactive_anime.py:663-688`.

Nie ma jednak subskrypcji **bez wskazania grupy**: pusty tekst jest ignorowany przez UI, a `SubscriptionOrder` odrzuca brak grupy (`subscriptions.py:334-340`). Wpisana nazwa staje się filtrem, nie sugestią. Stwierdzenie w `reports/current-system.md:66,93`, że nie wykazano drogi UI bez istniejącego wydania, jest zatem niepełne dla badanego HEAD; tutaj zostało zweryfikowane. Poprzedniego raportu nie zmieniano.

### Trwałość i tożsamość

`resolve_subscription_id` rozdziela sezony AniList nawet przy tym samym aliasie/grupie; surowe niejednoznaczne zastąpienie jest odrzucane (`subscriptions.py:387-414`). Model przechowuje sezon, offset, liczbę odcinków, wybrane numery, przyszły ogon, `requested_at`, stan okien i historię powtórzeń. Loader przyjmuje schematy 1–4 i migruje z kopią (`:84-87,423-456`). Receipt przed drugim plikiem i `added_by_command` chronią replay (`:519-524`; `automation.py:4348-4427`). Wykonane testy obejmują przerwę między zapisem zamiaru a potwierdzeniem oraz odtworzenie utraconej odpowiedzi add bez drugiego add.

Subskrypcja nie przechowuje całego zestawu aliasów AniList do ponownego wyszukania: dopasowuje `series_forms` zapisanej serii. Po pierwszym niepustym `offered` przypina również `search_category` (FR → `1_3`, pozostałe → `1_2`), nawet bez potwierdzonego add (`subscriptions.py:1129-1134,1162-1171`). Ręczne wyszukiwanie tytułu ma szersze wejście. Brak danych, czy nazwa/grupa/kategoria realnego wydania użytkownika się zmieniła.

**Granica dowodu:** restart obiektów ownera/usługi i lokalnego IPC, nie restart systemu ani utrata zasilania. `SubscriptionStore.save` nie wykonuje jawnego fsync, który ma `WatchStateStore.save` (`watch_state.py:270-280`). Nie stwierdzono utraty danych użytkownika.

## 4. Potwierdzone findingi i reprodukcje

### F-01 — wysoki: panel zaciera różnicę między aktywnym zamiarem, zakończonym oknem i zatrzymaniem sprawdzania

**DIRECT, R3 + kod.** Rzeczywista usługa utworzyła okno, dostała pusty katalog, po 72 h zapisała `EXPIRED` / `end_state=MISSING`. `next_check_at=None`, ręczne `check_due(refresh_calendar=True)` zwróciło zero wyników. Prawdziwy renderer pokazał nadal aktywną kropkę, „Brak terminu” i „Praca”.

`SubscriptionService` nie używa `policy.auto_enabled` jako bramki; pauzę egzekwuje owner przy planowaniu i admission (`anishift/application/automation.py:3402,3477`). Dlatego domyślne `AutomationPolicy(auto_enabled=False)` w końcowych odczytach R3 **nie jest przyczyną** `next_check_at=None` ani pustego wyniku sprawdzenia. Przyczyną jest terminalność wpisu (`anishift/application/subscriptions.py:943-946,1283-1285`). R3 bada bezpośrednio usługę i renderer, nie wykonanie pod pauzą ownera.

Trzy konkretne ubytki informacji:

1. Lista ignoruje `end_state`, terminy okna i błędy odcinków. Wejście Enter daje etykietę „wymaga ponowienia” / „brak wydania”, więc informacja **nie jest całkowicie nieobecna**, lecz nie wynika z listy (`state.py:1256-1263`; `interactive/subscriptions.py:101-123`).
2. Globalny `_subscriptions_problem` blokuje automatyczne sprawdzanie (`automation.py:3405`), trafia do statusu (`:1321`), ale nie do renderowania panelu. R3: identyczna klatka z/bez `subscriptions_problem="OSError"`. Tray ma osobny wskaźnik problemu (`cli/watch.py:375-381`); nie wolno twierdzić, że błąd nie ma żadnego kanału sygnalizacji.
3. `_subscriptions_check_command` zwraca poprawną odpowiedź IPC również dla `CheckOutcome.problem`, podając `problems/outcomes` (`automation.py:3147-3157`). Panel ignoruje zwróconą treść akcji (`state.py:829-863`). R3 z atrapą odpowiedzi `problems=1` daje „Polecenie przyjęte”, bez pokazania problemu wyszukania. Automatyczny poll także nie agreguje zwróconych problemów do `_subscriptions_problem` (`automation.py:3427-3440`).

**INFERENCE:** „subskrypcje nie działają” może oznaczać poprawnie zapisany zamiar, dla którego nie ma już zaplanowanej pracy, lub niewidoczny na liście błąd — niekoniecznie brak znalezionego torrenta. R3 nie wywoływał realnej awarii dysku; potwierdza projekcję i renderer, a warunek zatrzymania harmonogramu wynika z kodu.

### F-02 — średni: catch-up sezonu z numeracją absolutną pyta niewłaściwy wariant numeru

**DIRECT, R1.** Warunki: sezon 2, offset 12, wybrany E1; broad query nie zawiera starego wydania; deterministyczny indeks udostępnia `[Group] Example - 13 (1080p)` pod zapytaniem absolutnym. Prawdziwe parser, katalog, usługi i magazyn; atrapy tylko źródła, kalendarza i klienta.

- Subskrypcja zapytała `Example Group`, `Example 01 Group`; `downloaded=0`, `problem=""`, brak add.
- Ręczne `search_title(E1, SeasonContext(2,12,12))` zapytało także `Example S02E01` i `Example - 13`, odczytało `episode=1, absolute=13`; ręczne `download` wykonało jeden add.
- Przyczyna: `_catch_up` używa lokalnego numeru bez offsetu (`subscriptions.py:1121-1124`), podczas gdy ręczna ścieżka generuje oba rodzaje numeracji (`acquisition.py:673-689`). Interpretacja **otrzymanego** wydania przez `read_episode` jest poprawna (`:306-320`); luka jest wcześniej, w pozyskaniu kandydatów.

To warunkowa luka pokrycia, nie dowód zachowania rzeczywistego Nyaa dla konkretnego tytułu. Jeśli broad query zawiera wydanie, subskrypcja obsługuje numerację absolutną; istniejący test `tests/application/test_subscriptions.py:962` jest takim kontrprzykładem. R1 nie symuluje rankingu ani nie kopiuje implementacji do oczekiwanego wyniku: sprawdza różnicę w faktycznych zapytaniach i add na granicach.

### F-03 — wysoki wpływ, zamierzony guard: przyszły zamiar może nie dotrzeć do wyszukiwania nawet po rozpoczęciu sezonu

**DIRECT, R2.** Wpis wybrany przed premierą, E1 bez daty, sezon `NOT_YET_RELEASED`. Po dwóch dniach odtworzenie usługi i kalendarz `RELEASING`, nadal bez daty E1. Także wymuszone odświeżenie kalendarza: **0 zapytań do źródła wydań**, `PENDING`, `awaiting_airing=True`, `window_until=None`; kolejny termin to refresh kalendarza. Ręczne wyszukanie i pobranie tego samego syntetycznego wydania: 1 add.

Źródło: `subscriptions.py:1518-1534`, wcześniej `:973-979`. To realizuje obowiązujący zapis `anishift/application/AGENTS.md:114-118`: start sezonu/liczba odcinków nie otwierają wszystkich okien. Nie oznaczamy tego jako błędu wobec obecnego kontraktu. **INFERENCE:** jeśli metadane realnego odcinka pozostają niepełne, monitorowanie kalendarza może działać, ale monitoring publikacji nie ruszy. Nowy jawnie wybrany odcinek bez daty i bez wcześniejszego `awaiting_airing` może dostać okno — nie wszystkie braki kalendarza blokują wyszukiwanie.

Po 72 h istniejącego okna expiry jest trwałe i następuje przed wyszukaniem. Restart/F nie zapewniają „ostatniej próby” ani bezterminowego szukania spóźnionych wydań (`subscriptions.py:974,943-946,1537-1578`; R3). Jest to obecna polityka, nie nowo zatwierdzone wymaganie.

## 5. Dlaczego ręczne D nie jest równoważną próbą subskrypcji

| Ręczne D | Subskrypcja |
| --- | --- |
| Człowiek wybiera konkretne wydania już obecne w wynikach; `_start_download` nie sprawdza kalendarza (`anime.py:656-668`). | Zapisuje zamiar i dopiero harmonogram ustala, czy wolno rozpocząć wyszukiwanie. |
| Wyszukiwanie po romaji i angielskim, dla wąskiego zakresu dodatkowo lokalny/absolutny numer i SxxEyy; doprecyzowanie grup (`acquisition.py:454-489,652-731`). | Utrwalone query + jedna grupa; ewentualnie jeden lokalny numer catch-up (`subscriptions.py:1106-1134`). |
| Wybrany wariant może być inną grupą; indywidualny wybór paczki jest możliwy. | Dokładna grupa, brak paczek, zakres i sezon. |
| Nie zależy od `enabled/end_state`, okien ani budżetu kalendarza konkretnej subskrypcji. | Każdy z tych warunków może zakończyć próbę wcześniej. |
| Odmowa globalnej pauzy jest błędem akcji z drogą wznowienia w Anime (`anime.py:810-829`). | Zapis subskrypcji podczas pauzy może się udać, ale nie uzbraja harmonogramu. |
| `ResidentSession.download` → `_accept_download` → `AcquisitionService.download`. | `admit` → ta sama `AcquisitionService.download`, wspólny prywatny klient i obsługa transferów. |

**INFERENCE:** działające D dowodzi możliwości przyjęcia konkretnego ręcznego wyboru w danej chwili, jeżeli rzeczywiście doszło do dodania/transferu. Nie dowodzi, że subskrypcja wykonała wyszukiwanie, dostała ten sam zestaw kandydatów albo była w aktywnym oknie. Oba tryby współdzielą globalną pauzę i końcowy klient; nie ma podstaw do przypisania problemu samemu qBittorrentowi ani rankingowi.

Dokumentacja ma drift: `README.md:74-79` opisuje Enter jako wysłanie oraz folder serii. Aktualne D / akcja Pobierz wysyła zaznaczenie otwartej grupy, Enter przełącza wiersz, a docelowy układ jest płaski (`anime.py:459-498`; `acquisition.py:491-509`). Mapa powyżej opiera się na kodzie.

## 6. Znaczenie dla przyszłej migracji — bez planu architektury

- Zmiana indeksu/rankingu sama nie usuwa zatrzymania **przed** wywołaniem źródła: globalnego latcha błędu, terminalnego końca, `awaiting_airing`, pauzy ani wymagania konkretnej grupy.
- Nowy mechanizm numeracji musi pokryć także **generowanie zapytań** zaległych odcinków, nie tylko poprawne odczytanie nazwy już znalezionego wydania (R1).
- Trzeba odróżniać zapis zakresu, zaplanowane sprawdzenie, wykonane wyszukanie, odrzucone kandydatury, przyjęcie torrenta i kompletny plik. Obecna kropka `enabled` nie reprezentuje tych etapów.
- Obecne okna, retry i przypięcie grupy są faktami wymagającymi świadomej decyzji przy zmianie zachowania, nie automatycznie wymaganiami przyszłego rozwiązania. Zachowana terminalność nie dowodzi pozyskania całego sezonu.
- Trwałe identity sezonu, zakres, powtórzenia i niepewne przyjęcia już istnieją. Wyniki testów pokazują ich wartość; nie wolno utożsamiać `taken` z kompletnością ani odrzucać tej pamięci przy zmianie źródła.

AniList + ani.zip + Torrentio + heurystyka pozostają kierunkiem wcześniej badanym, niezintegrowanym. Nie prowadzono tu nowych prób sieciowych ani porównania Sonarr/Laya.

## 7. Brakujące dowody runtime i minimalna diagnostyka

**UNKNOWN:** czy użytkownik zatwierdził draft, jaki zakres/grupę/sezon zapisał, czy działał owner, jaka była globalna pauza, `end_state`, stan kalendarza, aktywne blokady dostawców, odpowiedź wyszukania i admission. Testy nie rozstrzygają tych faktów. Nie odczytywano produkcyjnych konfiguracji, `.env`, credentials, ledgerów, logów ani mediów.

### Istniejące kanały diagnostyczne — kontrakt sprawdzony w kodzie, bez uruchamiania

| Kanał | Co rzeczywiście pokazuje i czego nie rozstrzyga |
| --- | --- |
| `anishift doctor` | CLI woła `run_doctor(managed_torrents=True)` i dodaje checks `watch`/`autostart` (`anishift/cli/main.py:178-186,415-443`). `watch` oznacza odpowiedź rezydenta na status; nie dowodzi wykonywania poll konkretnego wpisu. `torrent_client` sprawdza przygotowanie prywatnej binarki; na Windows zwraca OK także dla stanu „zostanie pobrana przy pierwszym zamówieniu”, nie sprawdza uwierzytelnienia WebUI ani pobrania (`anishift/setup/doctor.py:239-253`). To nie pełny test downloadera ani operacja bez I/O: doctor czyta Settings/`.env`, sprawdza pliki i może utworzyć workspace (`:169-185,256-272`), a check rezydenta wykonuje IPC. |
| `anishift autostart status` | Pokazuje stan rejestracji/włączenia zadania logowania (`anishift/cli/main.py:316-325`), nie bieżący poll ani skuteczność pobrania. |
| Stopka panelu `Praca` / `Wstrzymano` | Pokazuje globalną aktywność (`anishift/cli/interactive/state.py:1217-1230`), nie gotowość konkretnej subskrypcji. Rzeczywiste D działające jednocześnie w tym samym ownerze jest argumentem przeciw globalnej pauzie jako przyczynie. |
| Subskrypcje: wpis, termin, Enter | Lista potwierdza obecność wpisu, `enabled` i prezentowany termin; Enter pokazuje etykiety odcinków: „czeka na emisję”, „czeka na wydanie”, „wymaga ponowienia”, „brak wydania” (`state.py:564-578,1256-1263`; `anishift/cli/interactive/subscriptions.py:101-123`). Etykiety wynikają ze stanu odcinka, nie są pełną projekcją `awaiting_airing`/due: samo PENDING może nadal mieć etykietę emisji mimo otwartego okna. |
| Ikona tray | Otrzymuje globalny wskaźnik problemu transferów lub subskrypcji (`anishift/cli/watch.py:375-381`). Sygnalizuje problem zbiorczo, bez wskazania przyczyny pominięcia konkretnego odcinka. |

Kanały już istnieją, ale nie wszystkie rozstrzygają przyczynę. Nadal brakuje jawnych powodów pominięcia due per wpis i liczników odrzuconych kandydatów według przyczyny. Powyższe komendy opisano, nie uruchomiono; raport nie wymaga przesyłania pełnych outputów, konfiguracji ani sekretów.

### Minimalny brakujący ślad

Najmniejszy przyszły ślad rozstrzygający, bez pełnych plików i sekretów:

1. Wspólne UTC próby i potwierdzenie odpowiedzi ownera; globalna pauza, rodzaj pending receipt, kod globalnego problemu subskrypcji.
2. Pseudonim ID wpisu + generacja, `enabled/end_state`, obecność AniList ID, sezon/offset/liczba odcinków; wybrane numery i granica ogona. Zgodność grupy jako boolean/licznik, bez konieczności logowania całego zapytania.
3. Dla jednego brakującego numeru: `requested_at`, `awaiting_airing`, data emisji, `due_at/window_until`, ostatnia próba, retry i machine code; następny deadline oraz powód pominięcia.
4. Czy faktycznie wywołano źródło, liczby znalezionych/odrzuconych kandydatów według powodu; admission accepted/refused z kodem, pseudonim correlation ID i stan potwierdzenia klienta.

Obecne logi dają „Subscription stored/checked”, liczby pobrań, ostrzeżenia klas błędów i kalendarz (`subscriptions.py:576,824-826,999-1003`). Nie rejestrują powodów wszystkich guardów ani odrzuceń per subskrypcja. Zatem sam brak linii „Releases searched” nie dowodzi błędu źródła; sam „Subscription checked, downloaded=0” nie odróżnia braku wyniku od niedopasowania. To opis potrzebnego dowodu, **nie zmiana loggera ani prośba o przesyłanie plików teraz**.

## 8. Komendy, dowody i zakres zapisu

### Izolacja

Własny katalog (krótka i długa nazwa Windows wskazują to samo miejsce):

`C:\Users\MattyMroz\AppData\Local\Temp\opencode\subscriptions-research-20260922-7e31c9`

Przed utworzeniem wykonano `Test-Path -LiteralPath "C:\Users\MATTYM~1\AppData\Local\Temp\opencode"` → True oraz sprawdzenie nowej nazwy → False; exit 0. Skrypty utworzono przez `apply_patch`. `TMP`, `TEMP`, basetemp i cache pytest są w tym katalogu; `PYTHONDONTWRITEBYTECODE=1`, `UV_OFFLINE=1`, `uv --offline --no-sync`. Runner usuwa odziedziczone `ANISHIFT_*` ze środowiska procesu testów. Wybrane testy używają `Settings(_env_file=None)` i lokalnych magazynów/atrap, nie produkcyjnego bootstrapu. Nie uruchamiano aplikacji ani daemona z konfiguracją użytkownika.

### Wykonane sprawdzenia

| Dowód | Start UTC | Wynik | Czas pytest / całej komendy |
| --- | --- | --- | --- |
| R1–R3, finalny instrument | `2026-09-22T17:58:40.065530+00:00` | **3 passed**, exit **0** | 5,42 s / 6,420 s |
| B1, istniejące testy | `2026-09-22T17:58:40.065585+00:00` | **140 passed**, exit **0** | 5,47 s / 6,544 s |

R1–R3 i B1 uruchomiono **równolegle**, na wspólnym CPU i z tym samym katalogiem `TMP/TEMP`, ale z odrębnymi katalogami basetemp i cache pytest. Podane wartości są orientacyjnymi czasami wykonania testów przy współdzielonych zasobach, nie benchmarkiem ani pomiarem wydajności subskrypcji.

Runtime: Windows, Python **3.14.2**, pytest **9.1.1**. PASS reprodukcji znaczy „zaobserwowano opisane zachowanie”, nie „naprawiono błąd”. Wstępny przebieg R1–R3 również przeszedł (3 passed, 5,90 s; 17:56:44 UTC); finalny dodał weryfikację ukrycia `problems=1`, usunął startową notkę renderera i jawnie wskazał konfigurację pytest. Wyniki finalne są autorytatywne.

Dokładne komendy wejściowe, osobne wywołania PowerShell z cwd repo:

```powershell
if (Test-Path -LiteralPath "C:\Users\MATTYM~1\AppData\Local\Temp\opencode\subscriptions-research-20260922-7e31c9") { $env:TMP="C:\Users\MATTYM~1\AppData\Local\Temp\opencode\subscriptions-research-20260922-7e31c9"; $env:TEMP=$env:TMP; $env:PYTHONDONTWRITEBYTECODE="1"; $env:PYTHONIOENCODING="utf-8"; uv run --offline --no-sync python "$env:TMP\run_checks.py" repro }
if (Test-Path -LiteralPath "C:\Users\MATTYM~1\AppData\Local\Temp\opencode\subscriptions-research-20260922-7e31c9") { $env:TMP="C:\Users\MATTYM~1\AppData\Local\Temp\opencode\subscriptions-research-20260922-7e31c9"; $env:TEMP=$env:TMP; $env:PYTHONDONTWRITEBYTECODE="1"; $env:PYTHONIOENCODING="utf-8"; uv run --offline --no-sync python "$env:TMP\run_checks.py" baseline }
```

Runner zapisuje pełne argv wewnętrznego `uv run --offline --no-sync pytest -c pyproject.toml -n 0 ...`, exit code, UTC, runtime, baseline i hashe do `repro-evidence.json` / `baseline-evidence.json`; stdout/stderr do `repro.log` / `baseline.log`. Basetemp: `repro-tmp-final`, `baseline-tmp-final`; cache: `repro-cache`, `baseline-cache`. Przy ponowieniu należy użyć nowej własnej nazwy basetemp, bo pytest czyści wskazany katalog.

B1 obejmuje cały `tests/application/test_subscriptions.py` oraz dokładne node ID:

```text
tests/application/test_automation.py::test_one_resident_order_downloads_backlog_then_only_due_eight_across_restart_and_cooldown
tests/application/test_automation.py::test_a_restart_reconciles_a_lost_add_response_without_adding_again
tests/application/test_automation.py::test_a_failed_acquisition_journal_save_prevents_the_add
tests/application/test_automation.py::test_a_stored_pause_is_still_a_pause_after_a_restart
tests/application/test_automation.py::test_a_full_pause_refuses_a_client_resume_and_a_manual_subscription_check
tests/application/test_automation.py::test_subscription_addition_replays_after_its_confirmation_could_not_be_saved
tests/cli/test_interactive_anime.py::test_upcoming_title_group_input_is_local_and_routes_command_letters_as_text
tests/cli/test_interactive_anime.py::test_o_follows_the_highlighted_group_of_the_chosen_title
```

SHA-256 finalnych instrumentów:

```text
run_checks.py    d3efbcfa7c589b3fd68fea139f685eb5d9b9d81465ef6963e4d9a2ae3dc035c0
test_research.py 5f2941e4f73d124805ef70d2aac1327a0f86157e082d658ff562daff31cf8ea7
```

Hashe źródeł w obu plikach evidence są zgodne, m.in.:

```text
anishift/application/subscriptions.py aff24bb7efee29fd1abb036e04151472ec7c02afea33ddfb1488a42d0c19c7cd
anishift/application/automation.py    a4680334ac892bd4020f3f8d5c27f8518200812c008207051c743064715f397f
anishift/application/acquisition.py   8b603e9b768fe64f4467e9587d0e71884d3da165d47dc55bd1beec8d880a5bda
anishift/cli/interactive/state.py     b5719cbd779cf0f702b87e439d37930e4b76a235a7a05af9412bbbc1e37aa95b
anishift/cli/interactive/anime.py     030ef1f97a7213d592702b980530f8e3c497f546fda56e377ee0f2f980ff3afe
```

Preflight Git: oczekiwany HEAD/branch; zastane `M AGENTS.md`, nieśledzone `docs/work/acquisition-simplification/` i `docs/work/local-automation-2/`. Szeroki `git status --short` zgłosił ostrzeżenia uprawnień dla obcych katalogów pytest w workspace; nie otwierano ich. Kontrola po testach: `git diff --name-only` → tylko `AGENTS.md`; `git diff --exit-code -- anishift tests README.md pyproject.toml uv.lock` → brak diffu. HEAD bez zmiany.

Jedyny zapis w repo w tym zadaniu: **ten raport**. Reszta zapisów jest w nowym katalogu Temp powyżej. Bez napraw, nowych zależności, zmian testów repo, AGENTS, manifestu, specyfikacji lub planu; bez commit/push i delegacji.

### Status po niezależnym review

**PASS po korektach dokumentacyjnych.** Reviewer `opus5`, sesja `ses_f35ae064bffeZrv73186z5uuVQ`: pierwszy odbiór **PASS WITH FINDINGS**, bez błędu materialnego; niezależne ponowienie reprodukcji **3 passed**. Jest to osobny wynik review, obok **3 passed + 140 passed autora** udokumentowanych wyżej. Doprecyzowano warunek atrapy R1, odpowiedzialność ownera za pauzę w R3, równoległość pomiarów oraz istniejące kanały diagnostyczne. Końcowy odbiór tych korekt: **PASS**, z potwierdzeniem 10 nowych cytowań w kodzie. Reviewer sprawdził również hashe pięciu plików źródłowych i kolekcję 140 przypadków testowych. Końcowa kontrola dokumentu nie wymagała ponowienia testów ani diagnostyki produkcyjnej.
