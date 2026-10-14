# Jak działa pozyskiwanie anime: wyszukiwanie, subskrypcje i czas

**Stan odczytu: 2026-09-17, robocze P17 na historycznej bazie `HEAD 939e807`.** Raport opisuje aktualne pliki robocze, nie sam commit P16. Podstawą jest odczyt kodu i testów oraz przekazana przez prowadzącego weryfikacja kolejnych części P17. Nie oznacza to pełnego odbioru fazy: końcowy przegląd powiadomień jeszcze trwa, a próby fizyczne należą do P18. Podczas aktualizacji raportu nie uruchamiano testów, usług ani sieci i nie odczytywano konfiguracji ani mediów użytkownika. Odnośniki wskazują plik i symbol, ponieważ numery linii w roboczym P17 się zmieniają.

**Aktualizacja P18, 2026-09-17 około 20:00, `ed03e0c` + zmiany robocze:** wybór wydań, przejście do Przetwarzania i wspólny pełny pasek mają niezależny review PASS oraz rzeczywistą próbę panelu opisaną poniżej. Nie oznacza to zamknięcia całego P18 ani odbioru końcowego lektora. Pozostałe sekcje zachowują wcześniejszy zakres odczytu P17.

**Najważniejsze:** jedna karta sezonu/grupy obsługuje `1` odznaczony, `2–7` zamówione teraz i `8–12` zamówione na przyszłość. Świeży wybór zaległości otrzymuje ograniczone okno pozyskania, a przyszłe numery czekają na własne emisje. Ten podział ma już dowód przez produkcyjne `check_due()` oraz owner/IPC z kontrolowanym kalendarzem i restartem — nie tylko test zapisu karty. Lista i stopka karty odliczają sekundy ze snapshotu. Ponów rozróżnia dokończenie, pracę lokalną i ponowne pobranie. Wybór plików wewnątrz paczki nadal nie jest funkcją karty numerów.

Kontrakt produktu: [specyfikacja, R-006–014, R-027 i R-041](spec.md); zakres integracji i prób fizycznych: [plan, P17–P18](plan.md). Osobny kontekst wygody pozyskania i paczek: [zadanie poboczne](intent-acquisition-ux.md). Ślad odkryć P16 i ich rozstrzygnięcia zachowuje tabela w sekcji 6.

## 1. Główny przepływ

### Gdzie czego szukać

Home ma **Panel / Ręczny / Ustawienia / Wyjście**. Panel ma zakładki **Anime / Subskrypcje / Przetwarzanie / Biblioteka**, ale otwiera się na Przetwarzaniu. Anime znajduje tytuł i wydanie; Subskrypcje przechowują zamówione numery; Przetwarzanie pokazuje pobieranie i dalszą pracę; Biblioteka udostępnia wyniki. **Historia jest pod `H` w Przetwarzaniu**, bez piątej zakładki. Źródła: [app.py][app], menu Home; [state.py][ui], `_Tab`, `StateController.__init__`, `_action_key`.

Są dwie różne decyzje:

- **Pobierz:** jednorazowe zamówienie wskazanych wydań z Anime. Nie tworzy subskrypcji. Pobrane wejście przechodzi do zwykłego przetwarzania; nie jest to osobny tryb „pobierz bez obróbki”.
- **Subskrybuj:** zamówienie sezonu, grupy i numerów do dalszego szukania. Pierwsze `O` przygotowuje tylko szkic; dopiero `Enter` w karcie przekazuje zakres ownerowi, czyli procesowi prowadzącemu wspólną pracę.

### Od hasła do gotowego wyniku

1. **Wpisujesz tytuł, opcjonalnie filtr numerów.** AniList proponuje wpisy; wybierasz konkretny sezon/cour/film/OVA. Nie zamawiasz całej franczyzy.
2. **Program ustala numerację i szuka w Nyaa.** Korzysta z nazw romaji/angielskiej, kontekstu sezonu, ograniczonych zapytań po numerze i doprecyzowań grupy. Wyniki grupuje według serii i grupy wydań, z filtrem jakości.
3. **Zatwierdzasz zamiar.** Enter na grupie otwiera jej wydania, Enter/Space zaznacza odcinek, a jawne Pobierz przyjmuje wskazany zakres i przełącza do Przetwarzania. Początkowo nic nie jest zaznaczone. Zapisany hash ma etykietę i nie trafia do zwykłego nowego zamówienia; drugi wariant numeru zastępuje wybór pierwszego. Przez `O` przechodzisz do karty subskrypcji. Zaznaczenie nie dowodzi dostępności, pobrania ani obejrzenia.
4. **Owner zapisuje przyjęcie przed wykonaniem.** `ResidentSession.follow/set_range` prowadzi do trwałego potwierdzenia polecenia i zakresu. Jednorazowe pobranie zachowuje hashe oraz `PENDING_SEND` przed wysłaniem do klienta. Powtórzenie tego samego polecenia odtwarza receipt zamiast wykonywać je drugi raz.
5. **Harmonogram rozdziela kalendarz i szukanie wydań.** Kalendarz ma własny termin i budżet awarii. Szukanie Nyaa rusza dla kwalifikujących się zamówień; odpowiedź może być szersza, ale do przyjęcia przechodzą tylko właściwe numery. Owner sprawdza też aktualność wpisu, pauzę i wcześniejsze potwierdzenia.
6. **qBittorrent przyjmuje całe wydanie jako zatrzymane.** Nowe pobrania trafiają do płaskiego roota `workspace/`. Po otrzymaniu manifestu owner rezerwuje bezkolizyjne nazwy, zleca zmianę wewnętrznych ścieżek i zachowuje mapowanie. Dopiero potem może wznowić zapis treści. Bez manifestu nie ma jeszcze bezpiecznego układu ani startu treści.
7. **Kompletność jest sprawdzana dla plików.** Hash w kliencie oznacza przyjęcie, nie pobranie. Potrzebne są m.in. postęp pliku `1.0`, właściwy stan klienta, bezpieczna ścieżka, zgodny rozmiar i dostępny lokalny plik. Film i zadeklarowane sidecary o wspólnym rdzeniu tworzą komplet.
8. **Komplet przechodzi do obróbki, wynik do `ready`.** Jeden ukończony odcinek paczki może ruszyć przed resztą. Wynik można otworzyć, choć jego źródło nadal pozostaje przy torrencie jako `pending_sources`; źródło zostanie przeniesione po zwolnieniu. Pobrany oryginał nie jest automatycznie gotowym lektorem.

Źródła: [AnimeController][anime] (`_start_download`, `_start_subscription`, `_search_releases`), [StateController][ui] (`_apply_draft`), [ResidentSession][resident] (`follow`, `set_range`), [AutomationOwner][owner] (`_subscription_add_command`, `_subscription_repeat_command`, `_settle_layout`, `_retry_ready`), [SubscriptionService][sub] (`check_due`, `_check_due`), [AcquisitionService][acq] (`download`, `start_transfer`), [TransferInspector][transfers] (`_inspect`, `_inspect_files`, `_complete_files`, `_ready_file`).

### Co dokładnie oznacza wybór w karcie

- Przy znanej liczbie `12` karta tworzy `1–12`, także niewydane, oraz znane numery specjalne. Można wybrać zbiór z dziurami, np. `3, 7.5, 8, 12`.
- **Domyślny wybór zaczyna się od podświetlonego wydania**, nie od zaznaczeń z Anime. `O` na `7` przygotowuje znane numery od `7` wzwyż; wcześniejsze trzeba dołączyć w karcie. Wyniki grupy są uporządkowane od najnowszego numeru.
- Przy nieznanej liczbie karta pokazuje znane numery i jedną pozycję **Kolejne odcinki**, domyślnie od następnej liczby całkowitej za największym znanym numerem. Nie wymyśla listy do `12` lub `24`.
- `Space` edytuje szkic, `Enter` stosuje zakres, `Esc` odrzuca niezastosowane zmiany. `A` dodaje zwykłe numery, pomijając ukończone produkty i ułamki; nie znaczy „pobierz ponownie wszystko”.
- Ukończony produkt znika z oczekującego zaznaczenia, lecz pamięć pobrania zostaje. Zaznaczenie ukończonego numeru wymaga jawnego `P Ponów`; zwykły `Enter` tego nie wykonuje. `P` może też przygotować ponowienie podświetlonego numeru, np. wygasłego. Przy mieszanej edycji zaakceptowane Ponów nie zatwierdza reszty szkicu — tę nadal stosuje osobne `Enter`.

**Odznaczone znaczy tylko „nie zamawiam”.** Nie trzeba wyjaśniać, czy odcinek był obejrzany lub istnieje na dysku. `complete` zamówienia oznacza pobrane źródło; owner osobno projektuje `downloaded`, `processing`, `processing_failed`, `completed`. Błąd TTS nie zmienia faktu pobrania. Źródła: [SubscriptionDraft][draft] (`from_order`, `from_subscription`, `handle_key`, `refresh_work_states`), [StateController][ui] (`_draft_key`, `_retry_key`), [AutomationOwner][owner] (`_subscription_work_states`).

## 2. Źródła danych — faktyczne pola i parametry API

Poniżej są zapytania używane przez AniShift, a nie lista ogólnych możliwości dostawców.

| Informacja / operacja | Rzeczywiste zapytanie i pola | Wykorzystanie i widoczność |
|---|---|---|
| Tożsamość i nazwy anime | GraphQL POST `https://graphql.anilist.co`, JSON `query` + `variables`. `SEARCH_QUERY`: zmienne `search`, `limit=7`; `Page(perPage: $limit)`, `media(search: $search, type: ANIME, sort: SEARCH_MATCH)`; pola `id`, `title { romaji english native }`, `synonyms` | Kandydat ma wszystkie te nazwy. UI pokazuje romaji i różny tytuł angielski; łacińskie aliasy pomagają dopasować wydania. **Native i lista synonimów nie są wyświetlane w liście/nagłówku Anime.** Nie ma trwałej bazy pełnych kart tytułów. |
| Opis fabuły / odcinka | **Nie jest pobierany:** zapytania AniList nie zamawiają `description`, model kandydata nie ma tego pola; parser RSS nie czyta opisu Nyaa | Obecna karta nie ma opisu do pokazania. Dostępność pola w cudzym API nie oznacza jego użycia w AniShift. |
| Rok, pora roku, format, liczba, status | AniList: `seasonYear`, `season`, `format`, `episodes`, `status` | Lista pokazuje rok, format, liczbę i polski status. `season` pozostaje w kandydacie, lecz nie w tej etykiecie. Liczba zasila kartę i granicę sezonu. Status nie dowodzi istnienia torrenta. |
| Numeracja sezonu | W wyszukaniu `relations { edges { relationType node { id episodes format } } }`; kolejne `RELATIONS_QUERY` ze zmienną `id`, również `title { romaji english }` | Przejście po `PREQUEL`, maks. 8 wpisów, tylko TV/TV_SHORT/ONA. Powstają indeks sezonu, offset i liczba odcinków. Cour/Part zwiększa offset, niekoniecznie indeks. Nazwa wydania jest interpretowana w tym kontekście; UI może pokazać numer sezonowy i absolutny. |
| Kalendarz | `SCHEDULE_QUERY`, zmienne `id`, `page`; `Media(id: $id, type: ANIME) { id status episodes startDate { year month day } airingSchedule(page: $page, perPage: 25) { pageInfo { currentPage hasNextPage } nodes { episode airingAt } } }` | To pełne stronicowane znane daty tego sezonu, także historyczne, **nie samo `nextAiringEpisode`**. Brakujących dat kod nie dopisuje. Daty i pochodzenie trafiają do zamówień; `calendar_*` przechowuje stan odczytu. Projekcja listy wybiera najbliższą przyszłą emisję zamówionego `pending/due`, a przy braku przyszłych — ostatnią minioną z tego zbioru. |
| Wydania | RSS GET `https://nyaa.si/`, parametry `page=rss`, `q=<zapytanie>`, `c=1_2` albo `1_3`, `f=0`; nagłówek `User-Agent: AniShift/0.1` | Czytane: `title`, `link`, `infoHash`, `seeders`, `size`, `pubDate`. Parser nazwy ustala grupę, serię, numer, wersję, rozdzielczość, język i dubbing. UI pokazuje grupę/język/serię, numer, jakość, seedy, rozmiar i datę najnowszego wydania grupy; nie pełny opis ani surowy tytuł każdego release'u. |
| Referencja do ponownego pobrania | Z `Release.torrent_url` rozpoznawany jest **wyłącznie** kanoniczny `https://nyaa.si/download/<dodatnie ID>.torrent` | `AcquisitionConfirmation` zapisuje opcjonalne `nyaa_release_id` i `release_title` obok hasha. Nie zapisuje pełnego URL-a ani pełnego RSS. Adapter Nyaa odtwarza URL z ID przy jawnym Ponów. Brak zgodnego adresu/tytułu oznacza brak referencji. Nie powstaje alternatywny magnet. |
| Przyjęcie i sterowanie torrentem | Web API pod `/api/v2`: POST `/torrents/add` z `urls`, `savepath`, `category=AniShift`, `stopped=true`, `paused=true`; `/torrents/renameFile` z `hash`, `oldPath`, `newPath`; `/torrents/start` lub `/torrents/stop` z `hashes` | Przyjęcie jest zatrzymane do rezerwacji nazw. `/torrents/delete` z `hashes`, `deleteFiles=false` usuwa transfer bez kasowania mediów. To operacje całego torrenta; rename dotyczy jego pliku. |
| Manifest i postęp | GET `/torrents/info?category=AniShift`, GET `/torrents/files?hash=…` | Transfer: nazwa, hash, postęp, stan, ścieżka, bajty pozostałe/ukończone. Plik: indeks, nazwa, rozmiar, postęp, priorytet. `priority=0` oznacza pominięcie przez klienta. **Priorytet jest odczytywany, karta nie ustawia wyboru plików paczki.** |

Źródła tabeli: [anilist.py][anilist] (`SEARCH_QUERY`, `RELATIONS_QUERY`, `SCHEDULE_QUERY`, `AniListCatalog.airing_schedule`, `_candidate`), [typy katalogu][catalog-types] (`TitleCandidate.aliases`), [anime.py][anime] (`_title_header`, `_candidate_label`, `_choice_label`, `_newest_detail`), [nyaa.py][nyaa] (`_search_category`, `_release_from_item`, `retained_release_id`, `retained_torrent_url`), [acquisition.py][acq] (`retained_reference`, `reacquire`), [control.py][control] (`AcquisitionConfirmation`), [qbittorrent.py][qbit] (`add_torrent`, `torrents`, `files`, `rename_file`, `stop`, `resume`, `remove`), [automation.py][owner] (`_subscription_view`).

### Własność danych i pamięć

Kompozycja tworzy jeden `httpx.Client` z `RequestControl` dla AniList, Nyaa i klienta torrentowego. Subskrypcje używają tego samego `AcquisitionService`; Panel pyta przez IPC. Wątek UI nie tworzy drugiej puli HTTP. `RequestControl` współdzieli **trwające identyczne odczyty**, nie cache wyników z TTL. Po zakończeniu usuwa request z mapy aktywnych.

Tytuły/wyniki pozostają w kontrolerze na czas nawigacji; zakres, daty, `requested_at`, oczekiwanie i budżety w zapisie subskrypcji; blokady dostawców oraz potwierdzenia przyjęć u ownera; manifesty i pomiary transferów w inspectorze. Historia jest osobnym, nieautorytatywnym dziennikiem. Ta wspólna granica dotyczy **pozyskania**, nie obietnicy wspólnego klienta HTTP również dla tłumaczenia/TTS. Źródła: [bootstrap.py][bootstrap] (`_acquisition_service`, `_subscription_service`), [http_requests.py][http] (`RequestControl.handle_request`, `restore`), [Subscription][sub], [HistoryJournal][history].

## 3. Harmonogram i znaczenie czasu

### Cztery różne fakty

| Czas / stan | Znaczenie |
|---|---|
| **Emisja `airing_at`** | Data według AniList. Unix `airingAt` przechodzi do świadomego UTC, trwały zapis ma ISO z offsetem. Nie jest datą wydania konkretnej grupy. |
| **Publikacja `published`** | `pubDate` z Nyaa, parsowane do UTC; brak/zła wartość daje `None`. Służy sortowaniu i próbkom opóźnienia grupy. |
| **Szukanie `due_at` / następne sprawdzenie** | Termin kwalifikacji do szukania, skorygowany m.in. o świeże zamówienie. Faktyczny request zależy też od ostatniej próby, okna i blokady API. Odczyt kalendarza ma osobny termin. |
| **Ukończenie AniShift** | Potwierdzony wynik obróbki i publikacji. Kalendarz i procent torrenta nie wyznaczają godziny gotowego lektora. |

Lista subskrypcji i **stopka karty** pokazują np. `Odc. 8 · Emisja za 02d 04:18:09`. Licznik korzysta wyłącznie ze snapshotu i bieżącego zegara UI. Nowy termin zastępuje poprzedni; po emisji widnieje „Czeka na wydanie”, bez wartości ujemnej; bez daty „Brak terminu”. Odznaczone, przyjęte i ukończone numery nie są celem zegara. Błąd katalogu pozostaje widoczny obok zachowanego terminu.

**Strefa czasu:** odliczanie porównuje chwile z offsetem, więc lokalny czas, np. `+02:00`, i UTC dają tę samą różnicę. Nie należy mylić tego z lokalizacją wszystkich dat w UI: obecny licznik jest względny, etykieta daty Nyaa nadal formatuje UTC bez `astimezone()`, a historia wyświetla zapisany timestamp bez przeliczenia strefy. Same wiersze numerów w karcie nadal używają krótkich etykiet enumu (`pending` → „czeka na emisję”); zegar i przejście „Czeka na wydanie” są w stopce. To granica obecnej prezentacji, nie gwarancja lokalnej daty/godziny w każdym widoku.

Źródła: [state.py][ui] (`_subscription_term`, `_view_footer`, `_entries`), [subscriptions.py UI][draft] (`entries`), [anime.py][anime] (`_newest_detail`), [automation.py][owner] (`_subscription_view`). Testy: [test_interactive_state.py][test-ui] — `test_subscription_countdown_compares_instants_across_timezones`, `test_visible_subscription_list_and_card_tick_from_snapshot_and_accept_rescheduled_dates_without_io`, `test_subscription_projection_prefers_the_nearest_future_selected_unfulfilled_episode`.

### Rytm pracy zapisany w kodzie

- **Termin wydania:** emisja + jawne `release_delay_s`, a bez korekty mediana maksymalnie 8 próbek opóźnienia grupy; bez próbek **+3 h**. Próbka pochodzi z potwierdzonego wydania, pomija paczki i rewizje inne niż pierwotne. To obserwacja, nie SLA grupy.
- **Świeżo zamówione zaległości:** `requested_at` oznacza nowy jawny zamiar. Dla znanej daty początek okna to co najmniej `max(emisja + opóźnienie, requested_at)`. Stara emisja nie wygasza więc od razu nowego zamówienia. Dla dopuszczonego jawnego numeru bez daty okno zaczyna się przy przygotowaniu szukania, bez tworzenia fikcyjnego `airing_at`.
- **Brak wydania:** domyślnie kolejne szukanie co **1 h**, okno **72 h** od jego początku. Po końcu numer jest `expired`; późniejszy odcinek ma własne okno. Restart, render i odtworzenie receipt nie otwierają nowego okna.
- **Przyszłe numery:** znana data ustala przyszły termin szukania. Przy braku własnej daty `awaiting_airing` zachowuje zamiar, gdy wiadomo, że numer jest przyszły, sezon jeszcze nie ruszył lub ma HIATUS. Sama liczba odcinków albo nadejście `startDate` nie uruchamia wszystkich okien. Kolejne numery czekają na własną emisję, zamiast wygasać po 72 h przed premierą.
- **Odczyt kalendarza:** niezależny od szukania Nyaa. Domyślnie **1 h** dla terminów bliskich i nieznanych; **24 h** dla HIATUS oraz gdy najbliższa istotna znana data jest dalej niż dobę i nie ma jawnego nieznanego numeru wymagającego bliższej kontroli. To okresowe sprawdzanie może wykryć zmianę daty, ale nie natychmiast po zmianie u dostawcy.
- **Awaria kalendarza:** własne trwałe `calendar_attempts`, `calendar_checked_at`, `calendar_problem`; domyślnie **3 próby łącznie**, odstępy **60 s, 300 s**, potem brak dalszych automatycznych prób tego odczytu. Nie zużywa prób wydań i nie blokuje szukania zaległości z potwierdzonym terminem.
- **Awaria szukania wydań:** osobny budżet odcinka — domyślnie **3 próby**, **60 s, 300 s**, potem `missing`. Pusty wynik nie jest awarią: działa godzinne sprawdzanie do końca okna. Próby i problemy przeżywają restart.
- **Ręczne `F` w Subskrypcjach:** wymusza jedną próbę odświeżenia kalendarza aktywnych wpisów także po wyczerpaniu jego budżetu. Nie resetuje terminalnych odcinków i nie oznacza Ponów. Nadal respektuje limiter: aktywny cooldown daje przejściowe `calendar_cooldown`, bez requestu, zużycia próby lub nadpisania wcześniejszego trwałego błędu. Nieudana ręczna próba nie rozpoczyna nowej serii automatycznych retry.
- **Brak powiązania AniList:** ograniczone próby dopasowania jednego zgodnego kandydata i indeksu/offsetu sezonu oraz godzinny fallback Nyaa. Wyczerpanie prób powiązania nie wyłącza tego fallbacku.
- **HTTP:** co najmniej **1 s** między faktycznymi requestami do danego zdalnego dostawcy; budżet operacji po **16 requestów Nyaa i AniList**, również dla zagnieżdżeń. Wyszukanie tytułu, numeracja i wydania są osobnymi operacjami IPC — nie jednym limitem całej sesji. `Retry-After` i nagłówki limitu/resetu mogą wydłużyć oczekiwanie; awaryjny cooldown wynosi **60 s**. Transport ma `retries=0`. Odstęp 1 s nie jest obietnicą zgodności z każdym chwilowym limitem serwera.
- **Zakres wyszukania:** do 7 kandydatów AniList; pusty wynik dopuszcza jedną próbę skróconymi słowami. W Anime Nyaa dostaje do 5 doprecyzowań grupy; dodatkowe zapytania po każdym numerze tylko dla zamkniętego całkowitego zakresu do 3 odcinków. Subskrypcja szuka własnym hasłem z grupą i może dołożyć jedno zapytanie o najwcześniejszy brakujący kwalifikujący się numer całkowity. RSS i budżet nie gwarantują odnalezienia wszystkich dawnych wydań.
- **Transfery:** bazowy odczyt co **10 s**, backoff błędów całej rundy do **300 s**. Manifest jest odświeżany po istotnych zmianach transferu, nie co render. Zastój oznacza domyślnie **30 min aktywnego pobierania bez postępu**; pauza/wznowienie zeruje pomiar nieaktywnego przedziału. Brak przyjętych transferów i zaległych działań oznacza brak ich cyklicznego odczytu.

Źródła: [control.py][control] (`AutomationPolicy`, `_DEFAULT_*`), [subscriptions.py][sub] (`_scheduled_episode`, `_undated_episode`, `_calendar_deadline`, `_calendar_interval`, `_failed_calendar`, `_failed_check`, `_refresh_calendar`, `_bind_calendar`, `_release_delays`, `_offered`, `_catch_up`), [http_requests.py][http] (`request_scope`, `RequestControl._admit`, `_retry_deadline`), [acquisition.py][acq] (`requests`, `search_title`, `_search_queries`), [automation.py][owner] (`_poll_transfers`, `_inspect_transfers`), [transfers.py][transfers] (`_record_progress`).

Adapter kalendarza dopuszcza do **200 stron po 25 wpisów**, lecz produkcyjny budżet operacji nadal wynosi 16 requestów. Obsługa paginacji nie dowodzi obsługi dowolnie długiego sezonu w jednej operacji. Timeout pojedynczego requestu: AniList/Nyaa **20 s**, qBittorrent **10 s** — nie jest to czas całej interakcji.

### Pauza, restart i błędne dane

Globalna pauza blokuje harmonogram, nowe pobrania i start obróbki; własne transfery dochodzą do zatrzymania. Katalog, Historia i zweryfikowane otwarcie istniejącego wyniku pozostają odczytami, ale Pobierz, `F` subskrypcji i Ponów są blokowane. Wyłączenie/usunięcie pojedynczej subskrypcji zatrzymuje jej przyszłe zamawianie, nie usuwa wcześniej przyjętych mediów ani potwierdzeń.

Restart zachowuje zakres, daty, oczekiwanie, potwierdzenia i cooldown. Nie odtwarza każdej przegapionej godziny i nie zamienia wygasłego zamówienia w świeże. Brak `airingAt` pozostaje brakiem daty; zły typ, niedodatni timestamp, sprzeczne duplikaty i niepoprawna paginacja są błędem katalogu. Niepełne `startDate` daje brak daty, a błędna pełna data — błąd. GraphQL `errors` jest odrzucane także przy HTTP 200. Trwałe terminy wymagają offsetu. Źródła: [anilist.py][anilist] (`_post`, `_schedule_page`, `_episode_airing`, `_start_date`), [subscriptions.py][sub] (`_moment`, `check_due`), [AutomationOwner][owner] (`_subscriptions_check_command`, `_retry_proposal`, `_reacquire_refusal`).

## 4. Przykłady użytkowe i niejednoznaczności

### A. Potrzebuję istniejących odcinków 3 i 8

W Anime wybierz sezon i grupę, zaznacz `Space` wydania `3` i `8`, następnie `Enter`. Bez zaznaczeń `Enter` zamawia podświetlone wydanie. `A/Z` wybierają **wiersze wydań**, nie jedną najlepszą wersję każdego numeru; różne hashe mogą oznaczać kilka zamówionych wersji. Subskrypcja sama wybiera najwyższą rewizję, potem seedy, w ramach wymaganej jakości. Źródła: [AnimeController][anime] (`_mark_group`, `_start_download`), [subscriptions.py][sub] (`_new_episodes`, `_quality`).

### B. Sezon ma 12 odcinków, wyszły 1–7: chcę 2–7 teraz i 8–12 później

W jednej karcie pozostaw `1` odznaczony, zaznacz `2–12`, zatwierdź `Enter`. Przy znanej liczbie 12 nie potrzebujesz ogona. Jeżeli `O` użyto na najnowszym `7`, do początkowego `7–12` dołącz `2–6`.

1. Owner zapisuje `selected={2,…,12}`, `future_from=None` i świeży zamiar zamówienia. `1` pozostaje poza zakresem.
2. `check_due → _refresh_calendar → _apply_schedule` przypina daty. Dla starych `2–7` uwzględnia `requested_at`, więc dawne okno emisji nie odrzuca świeżego zamówienia. `8–12` zachowują przyszłe terminy albo oczekiwanie na własne daty.
3. `_due_episodes` dopuszcza teraz `2–7`, `_check/_new_episodes` odrzuca `1` i przyszłe numery nawet wtedy, gdy indeks oferuje wszystkie.
4. Restart nie powtarza przyjętych `2–7`. Gdy nadejdzie właściwy termin `8`, kwalifikuje się tylko ten numer; cooldown może jeszcze odroczyć request. `9–12` nadal czekają.

**Poziom dowodu jest szerszy niż w P16:** [test_subscriptions.py][test-sub], `test_fresh_selected_backlog_downloads_before_future_episodes`, wywołuje rzeczywiste `check_due()` z dawnymi datami, wybranym `2–12`, restartem i późniejszym `8`. [test_automation.py][test-owner], `test_one_resident_order_downloads_backlog_then_only_due_eight_across_restart_and_cooldown`, przechodzi przez `ResidentSession.follow`, ownera, adapter AniList z podstawionym HTTP, trwałą blokadę i restart. Sprawdza wysyłkę `2–7`, potem wyłącznie `8`. To kontrolowany dowód harmonogramu i przyjęcia, **nie pobranie sezonu z żywych usług ani gotowy TTS**.

### C. Nie znamy liczby odcinków albo wybieram 7.5

Włączone „Kolejne odcinki” obejmuje później poznane numery, zachowując jawne wykluczenia. Wyłączony ogon nie dopisuje `8` po przyjęciu `7`, także przy nieznanej długości. `FINISHED/CANCELLED` nie prowadzi do nieskończonego szukania hipotetycznej kontynuacji: jawne zaległości mają ograniczone okno, nieemitowane oczekiwania zostają oznaczone jako brak. HIATUS zachowuje przyszły zamiar i wolniejszy odczyt kalendarza. Nie ma automatycznego przejścia do sequela.

`7.5` pozostaje `Decimal`, nie przesuwa licznika za `8` i wymaga jawnego wyboru. Kalendarz AniList przyjmuje całkowite numery, lecz jawnie wybrane `7.5` bez daty może teraz przejść ograniczoną ścieżkę `check_due()`, gdy nie ma znanej przeszkody przyszłej emisji. Nie przypisuje mu się wymyślonej daty ani obcych OVA. Dowody: [test_subscriptions.py][test-sub], `test_a_closed_range_never_creates_the_next_episode`, `test_an_open_tail_accepts_new_calendar_rows_but_keeps_an_explicit_exclusion`, `test_explicit_fractional_release_without_airing_is_discovered_by_check_due`, `test_an_upcoming_full_card_waits_for_individual_airings_before_opening_windows`, `test_hiatus_keeps_future_intent_and_observes_resumption_without_reviving_expired_work`.

### D. Wynik wyszukania jest paczką 1–12

`Space/Enter` zaznacza wydanie oznaczone **cała paczka**; dopiero jawne Pobierz zamawia cały torrent. `O` na nienumerowanej paczce odmawia subskrypcji; `A/Z` pomija paczki. Manifest i postęp per-file służą bezpiecznemu przetwarzaniu po przyjęciu, ale nie tworzą interfejsu selekcji plików. **„Pobierz 2–7 z paczki” nadal pozostaje osobnym zadaniem**, opisanym w [intencji UX](intent-acquisition-ux.md). Obecny widok Przetwarzania udostępnia globalne O oraz C dla ujawnionego zlecenia obróbki, nie skróty sterujące pojedynczym torrentem. Źródła: [anime.py][anime] (`_start_subscription`, `_is_markable`), [state.py][ui] (`_processing_action`), [qbittorrent.py][qbit] (`files`, `stop`, `resume`, `remove`).

### Rozstrzyganie sezonu, grupy i jakości

- Użytkownik wybiera wpis AniList; relacje i nazwa wydania pomagają ustalić numerację. Przy awarii katalogu/braku wyniku UI może przejść do surowego Nyaa z notką; błąd relacji pozostawia informację o niedostępnej numeracji.
- Różne AniList ID tej samej nazwy/grupy mają odrębne deterministyczne ID subskrypcji. Ponowny wybór rozpoznanego sezonu zachowuje wcześniejsze ID i historię, także starszego wpisu. Nierozstrzygnięte surowe zamówienie nie może nadpisać rozpoznanego sezonu; owner odmawia przed przyjęciem receipt. To ochrona tożsamości, nie bezbłędny parser dowolnego tytułu.
- Grupa pochodzi z podświetlonego wydania. Przy wybranym tytule bez torrentów `O` pozwala wpisać grupę; jest to deklaracja użytkownika, nie obietnica jej przyszłych wydań.
- Wyniki poniżej 1080p lub bez rozpoznanej rozdzielczości są ukrywane; dubbing i nieustalony język napisów wykluczają wydanie. Kategoria angielska daje domyślne EN; brak wyników nie powoduje cichego zejścia na 720p.

Źródła: [anime.py][anime] (`_find_titles`, `_search_title`, `_handle_group_input`), [subscriptions.py][sub] (`resolve_subscription_id`, `_compatible_raw_order`, `_bind_calendar`, `_new_episodes`), [acquisition.py][acq] (`catalog_releases`), [nyaa.py][nyaa] (`search_releases`). Test ownera: [test_automation.py][test-owner], `test_resident_keeps_known_seasons_separate_and_refuses_raw_ambiguity_before_a_receipt`.

### Skróty w bieżącej ścieżce

| Miejsce | Działanie |
|---|---|
| Home | `↑↓`, `Enter` |
| Zakładki Panelu | `←→` poza edycją pola; `Tab/Shift+Tab` także podczas edycji. Anime: Enter włącza edycję, Esc kończy ją bez czyszczenia. Powrót zachowuje tekst i wybór bez automatycznego fokusu |
| Anime | `Enter` otwiera grupę; `Space/Enter` na wydaniu przełącza wybór; `Enter` na Pobierz lub `D` wysyła zaznaczenia; `O` szkic subskrypcji, `A` grupa, `Z` zakres, `S` sortowanie; `F` powtarza wyszukanie bez filtra |
| Lista subskrypcji | `Space` aktywność, `Enter` karta, `D` Dodaj przez Anime, `X` usuń wpis, `F` ręczne sprawdzenie |
| Karta | `↑↓`, `Home/End`, `Space`, `A`, `Enter`, `Esc`; `P` propozycja Ponów |
| Przetwarzanie | `O` globalnie zatrzymaj/wznów; `C` anuluj całe ujawnione przyjęte zlecenie obróbki, także oczekujące; `H` Historia. Pobranie przed przyjęciem obróbki nie ma akcji C |
| Historia | `S` lub `/` szukaj, `Enter` otwórz potwierdzony wynik, `P` propozycja Ponów, `Esc` bieżące |
| Biblioteka | `Enter` otwórz wynik, `F` folder, `D` szczegóły, `Delete` potwierdzenie Kosza |

Źródła: [AnimeController][anime] (`_apply_results_key`, `_results_hint`), [StateController][ui] (`_action_key`, `_processing_action`, `_history_key`, `_view_footer`, `_footer`).

## 5. Ponów, Historia, recepty i gotowy wynik

### Próba rzeczywistego panelu P18

Aktualny model pola Anime został zaakceptowany przez użytkownika po próbie: Enter włącza edycję, Esc lub Ctrl+C bez zaznaczenia kończy ją, strzałki edytują tylko aktywne pole. Ctrl+C z zaznaczeniem kopiuje tekst. Kursor jest blokiem na istniejącym znaku i nie rozsuwa liter; poza edycją znika. Tab zachowuje szkic i odbiera fokus. `anime-focus-cursor.xml`: 972 testy CLI PASS oraz root Ruff/format/mypy obu platform PASS. Skróty terminala i parser wejścia pozostawiono zgodnie z korektą użytkownika; tej prostej poprawki nie kierowano do Opusa. Akceptacja dotyczy fokusu i kursora, nie zamknięcia całego P18.

W nowym procesie panelu otwarto sezon 1 Solo Leveling i grupę ASW. Enter zaznaczył wyłącznie odcinek 03; Pobierz (1) przyjęło jedno nowe zamówienie i automatycznie pokazało Przetwarzanie. Odcinki 01/02 miały etykiety Pobrano. Podczas transferu odczyt ekranu pokazał `Pobieranie`, nazwę MKV, 17% i zegar; niezależny snapshot IPC potwierdził transfer `downloading`. Odczyty nie były jednoczesne, więc nie porównywano ich procentów jako tego samego pomiaru. Powrót do Anime pokazał Zamówiono przy 03; Enter odmówił zaznaczenia, Pobierz pozostało (0). Transfer osiągnął COMPLETE i ten sam materiał przeszedł do Extract bez dodatkowego pobrania.

Pasek pobierania korzysta z pełnego renderera TTS/Extract. Testy i Opus porównały tekst oraz Rich spans przy 80 i 120 kolumnach: różni się tylko etykieta fazy. Nieznany postęp ma `--`, a nie wymyślony procent. Lokalny zegar mierzy zaobserwowaną aktywność i nie dolicza pauzy. Akceptacja wyglądu przez użytkownika po tej poprawce pozostaje otwarta.

Odcinek 03: acquisition `1fec3e3e709b9ff5`, hash `01bf5aeaa16489b7801e312b64741d9d94d81501`, grupa `group-447be466697b0eb6`, run `run-fe3ca9d50564043a`. Końcowy wynik próby to **PARTIAL**: ekstrakcja i tłumaczenie zapisane, błąd `Requested subtitle stream is empty: displayed_pl`. Pełny lektor/Biblioteka nie są jeszcze odebrane. Ten sam wcześniej zdiagnozowany problem dotyczy 01/02.

Pełny izolowany przebieg `download-parent-corrected.xml`: **4905 passed, 18 skipped, 0 failures/errors**. Poprzedni `download-parent-full.xml` zachowuje pojedynczą regresję anulowania oczekującego Ręcznego; poprawiono bramkę akcji i oryginalny test przeszedł bez edycji. Ruff, format i mypy obu platform przeszły. Artefakty leżą w zatwierdzonym katalogu tymczasowym OpenCode. Nie uruchamiano automatycznego testu rzeczywistych prywatnych klientów.

Otwarte ustalenia z próby:

- Po doprecyzowaniu użytkownika niepewne potwierdzenia pobrań zostały wyłączone z Przetwarzania, licznika, nawigacji i timerów. Usuwa to 20 pustych starych wierszy z tej próby. Rzeczywiste przyjęte zlecenia obróbki mają niezależną widoczność; pamięć zamówień pozostaje. Korekta strzałek pozwala przełączać zakładki również podczas wpisywania w Anime. Zestaw obu korekt: `anime-arrow-tabs.xml`, 251 PASS; jest nowszy od opisanego wyżej pełnego przebiegu.
- Po przeładowaniu rzeczywistego panelu potwierdzono Przetwarzanie 0 i brak wszystkich niepewnych wierszy. W Anime z wpisanym tekstem → otworzyło Subskrypcje, ← Bibliotekę; powrót zachował tekst. Nie wysłano wyszukiwania ani zamówienia. Obie korekty mają niezależny review PASS.
- Wyszukiwanie nadal czeka na uzupełnienia grup. Izolowany pomiar istniejącego limitera: 9 GET-ów przy RTT 50 ms trwa około 8.055 s, równoległość 8.056 s; odstęp admission wynosi 1 s. Wcześniejsze pokazanie katalogu wstępnego wymaga integracji istniejącego kanału zdarzeń i zachowania budżetu. Tego nie wdrożono.
- `config/watch/runs/` zawierało 26 checkpointów przed nowym odcinkiem, `relocations/` było puste. Stan ma jedną rotowaną kopię `.bak` oraz jednorazową kopię migracji `.v1.bak`. Retencja 30 dni obejmuje Historię, nie checkpointy potrzebne do recovery; w sprawdzonych ścieżkach nie ma czasowego usuwania runów. Niczego nie czyszczono.
- Ręcznego usunięcia aktywnego torrenta nie wykonano w tej próbie. Istniejący test inspektora potwierdza przejście do UNCERTAIN i zachowanie ID; nie zastępuje to odbioru całego procesu po usunięciu z GUI.

### Ponów wybiera drogę na podstawie bieżących faktów

`P` przygotowuje propozycję ownera, a `Enter` potwierdza przejście dalej. Samo wyświetlenie propozycji nie pobiera ani nie przebudowuje plików.

| Bieżąca sytuacja | Droga |
|---|---|
| Niedokończone zlecenie z czytelnym dziennikiem wykonania | **Resume przez Ręczny**: podgląd dokończenia całego zachowanego zakresu i wybór Start. Nie zawęża po cichu wielomateriałowego zlecenia do jednego wiersza. |
| Dostępne lokalne źródło | **Ręczny** dla konkretnego materiału, z wyborem zakresu przebudowy i ponowną walidacją. Błąd TTS nie zamawia ponownie torrenta. |
| Brak źródła, istnieje subskrypcja i jawne numery | **Nowe ponowienie zakresu** z nowym ograniczonym oknem. ID wynika deterministycznie z polecenia i numeru; replay nie zeruje wykorzystanych prób. Dawne `taken`, potwierdzenia i powiązania poprzedniej próby pozostają. |
| Brak źródła, zachowane przyjęcie z ID Nyaa i tytułem, nawet po usunięciu subskrypcji | **Ponowne pobranie zachowanego wydania**. Owner zapisuje nowe skorelowane `AcquisitionConfirmation` z `previous_operation_id` przed wysyłką; adapter odtwarza kanoniczny URL. Stare potwierdzenie zostaje. |
| Stary zapis z `nyaa_release_id=None` albo brak internetowego zamówienia | Uczciwa odmowa: trzeba ponownie wybrać wydanie, a lokalnego usuniętego TXT nie da się odtworzyć z historii. Nie zgaduje się URL-a z nazwy ani nie tworzy magneta. |
| Źródło nadal trzymane przez torrent / niezakończone przyjęcie / konflikt pracy | Ponowienie jest blokowane do rozwiązania rzeczywistego konfliktu. Istniejący poprawny wynik może być dostępny do otwarcia niezależnie od tej blokady. |

Referencja Nyaa jest zachowana w **istniejącym potwierdzeniu pozyskania**, nie w drugiej kopii zamówienia w historii. Przeżywa usunięcie subskrypcji i rotację dziennika. Jej zapis poświadcza pochodzenie adresu, nie bieżącą dostępność wydania na serwerze. Źródła: [AutomationOwner][owner] (`_retry_proposal`, `_subscription_retry_proposal`, `_missing_source_retry`, `_accept_reacquire`, `_reacquire_refusal`), [SubscriptionService.repeat][sub], [AcquisitionService.reacquire][acq], [StateController][ui] (`_prepare_retry`, `_retry_key`, `_execute_repeat`). Testy: [test_history.py][test-history], `test_explicit_reacquire_retains_deleted_subscription_provenance_and_never_resends_receipt`, `test_legacy_acquisition_cannot_be_retried_by_inventing_a_release_reference`; [test_subscriptions.py][test-sub], `test_a_repeat_opens_one_fresh_window_and_replaying_its_command_preserves_consumed_attempts`.

### Historia nie steruje wykonaniem

`H` w Przetwarzaniu otwiera ostatnie **50 materiałów z terminalnymi zdarzeniami** z zachowanych **30 dni**, najnowsze najpierw. `S` lub `/` otwiera wspólny edytor wyszukania; podczas pisania litery nie uruchamiają poleceń aplikacji. Jawne szukanie obejmuje także przyjęcie zamówienia, potwierdzenie pobrania i regenerację, a nie tylko końcowe sukcesy/błędy. Wynik jest grupowany po materiale, bez domyślnego limitu 50 dla wyszukania. `Esc` wraca do bieżącej pracy.

`Enter` asks `ResidentSession.library_result` for the owner's current opening target. For a completed sidecar-only video set, the accepted target is its recorded source MKV/MP4 through the OS association, not the standalone narration file; final video results keep priority. Product confirmations remain required and History is never path authority. `pending_sources` may identify video still outside `ready`; local retry remains blocked while the torrent holds it. F reveals the confirmed main product independently of the playback target.

JSONL zapisuje granice operacji, nie każdy procent. Stabilne ID zdarzenia zapobiega duplikacji przy replay. Retencja i awaria dziennika nie usuwają aktywnych problemów, pamięci pobrania, ochrony przed ponowieniem ani metadanych Biblioteki. **Uszkodzony środkowy rekord pozostawia bajty nietknięte i daje widoczną odmowę odczytu Historii**; urwany ostatni zapis może być naprawiony z zachowaniem wcześniejszych rekordów. Odtworzony ślad terminalny oznacza czas przyjęcia, nie zmyśloną godzinę ukończenia.

Źródła: [history.py][history] (`HistoryEvent.create`, `HistoryJournal.materials`, `_prepare`, `_load`), [AutomationOwner][owner] (`_record_history`, `_record_request_history`, `_record_acquisition_history`), [StateController][ui] (`_load_history`, `_history_key`, `_history_input_key`). Testy: [test_history.py][test-history], `test_explicit_search_groups_nonterminal_boundaries_without_changing_default_history`, `test_corrupt_middle_is_preserved_and_not_reread_or_silently_replaced`, `test_torn_tail_next_append_and_restart_preserve_prior_records_and_receipt_identity`, `test_history_opens_ready_product_while_held_source_keeps_local_retry_scope_locked`.

### Recepta dotyczy dalszej obróbki, nie daty emisji

Ustawienia Auto udostępniają bazowe recepty **Wideo / Tłumaczenie / Audiobook**; `subs` dziedziczy wideo z wymogiem sidecara, `cover` audiobook z obrazem i MP4. Wspólny model/głos nie ma osobnej kopii dla każdego folderu. Zmiana preferencji wpływa na nowe plany/zlecenia; już przyjęte zachowują snapshot, a plan przygotowany przed zmianą nie otrzymuje przy przyjęciu nowej etykiety recepty. Lokalny override Ręcznego nie zmienia wspólnej recepty. Reset jest zakresowy i potwierdzany.

Źródła: [AutomationOwner][owner] (`_update_recipe`, `_accepted_recipe`), [test_recipe_settings.py][test-recipes] — `test_accepted_video_and_audio_keep_their_settings_while_new_orders_receive_shared_voice_changes`, `test_recipe_inheritance_and_manual_overrides_do_not_copy_video_policy_into_other_targets`, `test_recipe_changed_after_preview_does_not_relabel_the_accepted_plan`.

### Result notifications — reviewed implementation, native acceptance pending

The notification offer follows saved success, the confirmed main product and set provenance; `GROUP_FINISHED` alone is insufficient. Durable `notified` limits the offer to one per attempt/set. Clicking opens Library and selects the exact set only after owner validation. Unknown native identity opens Library without guessing a target; an expired identified result adds a concise notice. Ordinary icon activation opens Home. A ready product may notify while the torrent still holds its source, and failed balloon delivery does not undo completion.

The implementation and automated navigation checks were reviewed and committed in `8d40761`. This does not constitute acceptance of real Windows balloon clicks. The two-result native tray scenario remains a P18 gate. Sources: [AutomationOwner][owner] (`_notify_ready_results`, `_notify_ready_result`, `_open_notification`, `_notification_current`), [test_notification.py][test-notification] and the CLI notification-navigation tests.

### Library opening live checkpoint — 2026-09-18

Code commit: `c307ca3`, `fix(application): open recorded video for sidecar library sets`. Opus verified the final fixes without blockers; a separate fresh Astra reviewed the complete eight-file diff before commit. Root Ruff, formatting, mypy Windows/Linux and commit hooks passed. The final full test report `library-open-final-corrected.xml` records 5088 tests: 5070 passed, 18 skipped, zero failures/errors. The real private-client integration scenario was explicitly deselected; network and unavailable symlink cases account for the reported skips.

The parent shut down idle resident `47268` through its public IPC command, confirmed process exit, and started the current revision through `open_control`. New owner: PID `44636`, instance `instance-c97c7d84c50d4e19`, started at `2026-09-18T00:27:49.559051+00:00`. A fresh panel loaded the current CLI code.

The existing set `group-8a80362aa298183b` represented `[Erai-raws] Youjo Senki II - 11 [1080p CR WEB-DL AVC AAC][MultiSub][1D51A25F]`:

| Boundary | Direct observation |
| --- | --- |
| Public owner/session API | Available set; default opening returned its recorded `.mkv`, `playback=False` returned its confirmed `.eac3`, and `main_result` remained the EAC3 product |
| Real Library keyboard F | Explorer selected the exact episode's `.eac3`; selection was read through the shell API |
| Real Library keyboard Enter | Windows started mpv PID `49532` at local `02:31:15` with the exact episode's `.mkv` as its sole media argument; the matching mpv window appeared |
| Final resident observation | Automation enabled, no active requests, transfers or pending commands; 31 acquisition records and four Library entries |

Window ownership, process start time, foreground and visible Library selection were checked before sending keys. Failed focus/selection checks sent no file-opening key. The existing unrelated player instance was not controlled. This smoke proves actual Enter/F dispatch and OS association, not audio quality, subtitle loading or synchronization. The user subsequently confirmed that the corrected behavior works, closing acceptance of this narrow Library opening correction. The remaining P18 scenarios retain their separate acceptance requirements.

### Library actions and Undo integration checkpoint — 2026-09-18

The real `deletion_preview` for `group-8a80362aa298183b` exposed a false `library_source_held` refusal: sources were already in `ready`, `pending_sources` was empty and the private client's `released` receipt contained the matching hash. Historical acquisitions retain relocated paths. The correction requires both `COMPLETE` and existing release proof before ignoring such an acquisition, reads that proof off-owner without client initialization, and preserves dedup history. Details now resolves the selected file through owner validation; whole-set Delete and persistent, context-bound refusals share the existing Library actions. Ctrl+Z uses one durable last-deletion target.

Opus finished code review with PASS and no open code findings. Root Ruff/format and mypy Windows/Linux passed. `library-undo-integrated.xml` contains 5122 results: **5104 passed, 18 skipped**, zero failures/errors; the real private-client integration scenario was explicitly deselected. The reviewer's 34 focused tests included the real Windows no-overwrite publication cases, not skipped substitutes.

Native acceptance used synthetic files only:

- The initial integrated attempt found a Win32 publication defect: missing terminating WCHAR produced a source name with extra characters. The corrected buffer includes the terminator outside `FileNameLength`. Real handle-publication and buffer regressions now cover it.
- Workspace `library-native-acceptance-ddcc477b14af4bb391840069bd62637b`: guarded recovery found one source with the exact original size/mtime/device/inode and bytes, restored its intended empty destination, and changed no ledger bytes. Explicit Undo then completed the original `recycle-088d899bd449457e` / `restore-17629618eddde382` ledger with both original receipts and product proofs retained.
- Workspace `library-native-acceptance-afc83d46fe7d43e3ab02298f0c76aa13`: `library_native_acceptance.py` passed actual whole-set recycle → reconstructed owner → Undo, verifying original identities, bytes and Library availability. An occupied destination retained its foreign bytes; explicit retry after clearing that synthetic collision restored the exact set.

Artifacts reside under the host's approved temporary `opencode` directory. These checks prove the real native boundary and persisted-owner reconstruction. The fresh Astra pre-commit review passed; code, README and scoped instructions were committed as `d2c779d`, `fix(application): restore recycled library sets and enable file actions`, with active hooks passing. Schema-2 Undo state is deliberately not readable by pre-Undo builds after admission; downgrade cannot discard recovery evidence or revert only the ledger.

### Library keyboard and process-restart checkpoint — 2026-09-18

The live owner `44636` was idle and shut down through public IPC; its exit was confirmed. Owner `47648`, instance `instance-de7885753b8f4bf1`, started at local `04:10:44` and loaded the committed correction. The old panel was closed through Home → Exit; the new panel `AniShift-23385d6e00cf77f2` uses the current CLI. Live API deletion preview for Youjo now succeeds. Real Delete on that selected episode displayed the whole-set confirmation with four files and **Anuluj** initially selected; Enter cancelled it. Final live status retained 31 acquisitions, four Library entries, Auto enabled and no deletions, transfers, active requests or pending commands.

The destructive/recovery keyboard scenario used only `library-panel-acceptance-d2c779d`, an isolated synthetic workspace and configuration. Its fixture service has no acquisition or subscription service and refuses processing-plan execution; the owner uses production `run_resident` with native IPC, DirectoryWatch, recycler and restorer. The panel uses production `run_interactive` and `ResidentSession`.

| Boundary | Direct observation |
| --- | --- |
| Details heading Enter | Displayed “Wybierz wiersz pliku”; no file action |
| Details F on product | Explorer selected exact `ready/AniShift Undo Smoke.pl.txt` |
| Details Enter on source | OS association launched Notepad with exact `ready/AniShift Undo Smoke.txt`; this proves action dispatch, not editor lifecycle after the subsequent deletion |
| Details Delete | Whole-set confirmation showed two files / 16 bytes and default Cancel; Enter cancelled, leaving both files |
| Explicit confirmation | Right selected the recycle action; Enter recycled both exact files under `recycle-097f053fd813d931` |
| Actual process restart | Owner PID `21428`, instance `instance-c18dd98bf330fb99`, exited after public shutdown. New PID `47000`, instance `instance-e6f474925680e061`, loaded the same ledger; both files remained absent before explicit Undo |
| New panel Ctrl+Z | Restored both files under `restore-9640206373e80ca6`; exact size/mtime/device/inode and SHA-256 matched baseline; the set reappeared in Library |
| Repeated Ctrl+Z | Displayed “Ostatnie usunięcie zostało już cofnięte” without a second restore |
| Cleanup | Synthetic panel exited and synthetic owner shut down through IPC with process exit confirmed; restored files and evidence retained |

Parent checked window identity, start time, visible selection and exact foreground HWND before every key action. The temporary UI instrument initially rejected a tab-header TextPattern before sending keys and was narrowed to the terminal TextPattern. During owner downtime the temporary connector initially raised `RuntimeError` instead of `ControlError`; that harness-only defect was corrected and a fresh panel performed Undo on the same ledger. No product-code change was needed. This is a true process-restart and keyboard acceptance run, not merely reconstructing an owner object. It does not establish uninterrupted old-panel reconnect behavior or human UX acceptance.

Evidence in that temporary directory: `baseline.json`, `shutdown-1789697863026704400.json` (deleted state), `inspect-1789697876934027500.json` (new owner before Undo), `inspect-1789697998084646500.json` (exact restoration) and `shutdown-1789698067668045000.json` (final preserved files). User interaction acceptance and the broader P18 scenarios remain pending.

### Direct, quiet Library actions — user correction, 2026-09-18

The user rejected confirmation altogether: Delete acts immediately and Ctrl+Z undoes it. The current uncommitted CLI follow-up removes confirmation state and rendering, synthetic recycle/restore rows, routine busy/success notices, missing-result label prose and Library's global processing footer. Partial leftover materials remain plain accessible entries. Owner validation, native recycling and durable Undo remain unchanged. Existing action tests were adapted; 1007 CLI tests, root Ruff/format/mypy and final focused Opus verification passed.

On the retained synthetic fixture, one actual Delete keystroke admitted `recycle-f2757ee77018287d` and recycled both files; the panel then showed an empty Library with action hints only. The Windows Terminal process disappeared before the attempted Ctrl+Z, so foreground guards sent no keys. Parent called the same public `deletion_undo` boundary for that exact deletion; `restore-166013d1f36882d2` restored both original identities and SHA-256 values. Parent confirmed synthetic owner PID12684 exited after public shutdown. Earlier real Ctrl+Z/process-restart acceptance still covers the unchanged Undo path; this attempt proves direct keyboard Delete and quiet rendering, not a new Ctrl+Z keyboard run. Live panels also exited; the next panel launch loads the new UI.

## 6. Ślad odkryć P16 → stan roboczy P17 → ograniczenia

Poniższa tabela zachowuje historię diagnozy. Kolumna P16 nie opisuje już bieżącego zachowania naprawionych ścieżek.

| Historyczne ustalenie P16 | Rozwiązanie w roboczym P17 i dowód | Pozostała granica |
|---|---|---|
| Nowo zamówiony stary odcinek mógł natychmiast wygasnąć według dawnej emisji. | `requested_at` i świeże ograniczone okno; `test_fresh_selected_backlog_downloads_before_future_episodes` oraz test owner/IPC z sekcji 4B. | Dostępność konkretnego starego wydania i żywych usług nie jest gwarantowana. Terminalne stare zamówienie nadal wymaga jawnego Ponów. |
| Przy nieznanej długości helper po przyjęciu `7` mógł dopisać `8` mimo wyłączonego ogona. | Kwalifikacja według aktualnego zakresu; `test_a_closed_range_never_creates_the_next_episode` i test jawnego wykluczenia przy otwartym ogonie. | Karta bez count nadal pokazuje pozycję ogona; nie jest ona dowodem kolejnego sezonu ani jego daty. |
| Brak daty lub odległy termin mógł zatrzymać odświeżanie; awaria katalogu mieszała się z próbami wydań. | Osobne `calendar_*`, adaptacyjne 1 h/24 h, trwały budżet, ręczna pojedyncza próba; `test_calendar_failures_do_not_spend_release_attempts_or_block_verified_backlog`, `test_manual_calendar_recovery_respects_provider_cooldown_without_spending_a_retry`. | Po wyczerpaniu budżetu potrzebne jest jawne działanie. Zmiana daty będzie widoczna dopiero po udanym odczycie. |
| `7.5` dawało się zapisać, ale wymóg daty w kalendarzu blokował automatyczne szukanie. | Ograniczone szukanie jawnego numeru bez fikcyjnej daty; `test_explicit_fractional_release_without_airing_is_discovered_by_check_due`. | Nie obejmuje automatycznie obcych OVA ani nie dowodzi kompletności RSS. |
| Ponów mogło zachować stare wygasłe okno i nie rozróżniało lokalnego źródła od ponownego pobrania. | Nowe ID/okno z zachowaniem historii; propozycja resume/Manual/subskrypcja/reacquire; zachowane Nyaa ID + tytuł pozwala ponowić po usunięciu subskrypcji. | Stare `None` wymaga ponownego wyboru wydania. Źródło trzymane przez torrent blokuje retry. Historyczne rezerwacje nazw mogą nadać ponowieniu dopisek **`[2]`**, nawet gdy pierwotnego pliku już nie ma. |
| Nieznana długość zakończonego sezonu mogła utrzymywać hipotetyczny ogon; nazwa/grupa mogły zderzyć dwa sezony. | Obsługa FINISHED/CANCELLED i HIATUS; odrębne ID AniList, zgodność starych ID, odmowa surowej niejednoznaczności. Testy sezonów i przyszłej pełnej karty w [test_subscriptions.py][test-sub]. | Brak automatycznego sequela; poprawne wybranie wpisu katalogu i ograniczenia parsera nadal mają znaczenie. |
| Brak sekundowego zegara; projekcja mogła wybierać dawną datę zamiast następnej przyszłej. | `_subscription_view` wybiera właściwy przyszły zamówiony numer; `_subscription_term` odlicza w liście/stopce bez I/O i bez ujemnych wartości. | Wiersze numerów nadal mają etykiety enumów; nie wszystkie daty są lokalizowane. Opis fabuły oraz selekcja wnętrza paczki nadal są poza obecną funkcją. |

Źródła mechaniki zastrzeżenia `[2]`: [AutomationOwner][owner] (`_reserved_names`, `_reserved_stems`) uwzględnia wcześniejsze `file_layout` niezależnie od obecności pliku; [transfers.py][transfers] (`flat_layout`, `_free_core`) dobiera wolny rdzeń. Raport nie proponuje kasowania tych rezerwacji ani pamięci pobrania.

### Co pozostaje niezweryfikowane

- **P18:** list opening and the controlled Delete/Details/Undo keyboard/process-restart checkpoints above passed. User acceptance of the new interaction remains pending. Remaining wider acceptance includes audiovisual output quality, complete provider-to-result processing, held-source packs, recovery/relocation and the other live scenarios in the plan.
- **Transfer freshness:** no active transfer was present during this checkpoint, so end-to-end comparison with the qBittorrent GUI remains unmeasured.
- **Notifications:** real Windows clicks with two completed results remain pending. Reviewed at-most-once behavior does not guarantee native balloon delivery.
- **Dostępność i ETA:** zapis kalendarza, przechowana referencja Nyaa, zielone testy i przyjęcie torrenta nie dowodzą aktualnej dostępności API/wydania ani godziny ukończenia TTS.

Earlier targeted counts describe their respective revisions and must not be added together. The final automated evidence and the narrow live smoke are recorded above; the wider P18 outcome remains PARTIAL until its remaining live gates and human acceptance are complete.

[app]: ../../../anishift/cli/interactive/app.py
[ui]: ../../../anishift/cli/interactive/state.py
[anime]: ../../../anishift/cli/interactive/anime.py
[draft]: ../../../anishift/cli/interactive/subscriptions.py
[resident]: ../../../anishift/cli/resident.py
[owner]: ../../../anishift/application/automation.py
[sub]: ../../../anishift/application/subscriptions.py
[acq]: ../../../anishift/application/acquisition.py
[control]: ../../../anishift/application/control.py
[history]: ../../../anishift/application/history.py
[transfers]: ../../../anishift/application/transfers.py
[anilist]: ../../../anishift/services/catalog/anilist.py
[catalog-types]: ../../../anishift/services/catalog/types.py
[nyaa]: ../../../anishift/services/torrents/nyaa.py
[qbit]: ../../../anishift/services/torrents/qbittorrent.py
[http]: ../../../anishift/services/http_requests.py
[bootstrap]: ../../../anishift/bootstrap.py
[test-sub]: ../../../tests/application/test_subscriptions.py
[test-owner]: ../../../tests/application/test_automation.py
[test-ui]: ../../../tests/cli/test_interactive_state.py
[test-history]: ../../../tests/application/test_history.py
[test-recipes]: ../../../tests/application/test_recipe_settings.py
[test-notification]: ../../../tests/application/test_notification.py
