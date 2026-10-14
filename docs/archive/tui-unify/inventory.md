# Inwentarz ekranów interaktywnych AniShift

Stan badania: 2026-10-11, branch `work/tui/02-unified-tabs`, commit `49dd9ec`. Badanie statyczne kodu; bez uruchamiania panelu/rezydenta i bez dostępu do danych `config/` lub `workspace/`. Śledzone pliki repozytorium były czyste. Nieśledzony `.opencode/` pochodził ze stanu zastanego.

Raport opisuje kod, nie docelowy projekt. Napisy w backtickach są literalnymi tekstami UI; `{…}` oznacza część wyliczaną. Nazwy ekranów obejmują także modalne stany, które zmieniają klawisze lub stopkę. Polskie napisy pochodzące z dowolnego wyjątku, nazwy pliku, tytułu katalogowego, opisu modelu lub odpowiedzi procesu nie tworzą zamkniętego słownika: podano ich miejsce włączenia i sanitizacji zamiast zgadywać wartości runtime. „Nie stwierdzono” w naruszeniach oznacza brak potwierdzonego przypadku w przeanalizowanej ścieżce, nie uniwersalny dowód bezbłędności. R1 odnosi się do faktycznego wykonania nazwanej akcji, nie samego wyświetlenia odmowy po naciśnięciu skrótu.

**Konwencja źródeł:** skrót `ui/` oznacza `anishift/cli/interactive/`; `app/` oznacza `anishift/application/`. Wszystkie `file:line` odnoszą się do powyższego commita. Wspólne słowniki i zachowania poniżej są częścią każdego ekranu, który się do nich odwołuje — nie trzeba powtarzać kilkudziesięciu identycznych odmów przy każdym ekranie.

**Identyfikatory:** S01–S14 opisują wspólny panel, U01–U23 poziomy Ustawień, E01–E16 warianty edytorów, M01–M13 Ręczny, A01–A07 Home i wykonanie, B01–B13 Anime. Produktowa nazwa „U08” oznacza szczegóły subskrypcji (B05); nie jest odwołaniem do sekcji U08 raportu, która opisuje Ustawienia → Auto → Wideo.

## Wspólne zasady odczytu

Zakres słowa „ekran”: osobny stan z własnymi regułami wejścia/stopką, a nie każda konfiguracja danych. Wszystkie poziomy menu mają osobne pozycje. Współdzielone edytory mają osobne opisy zachowania oraz tabelę każdej instancji pola. Wynik i błąd to dwa warianty tego samego trybu `MESSAGE`; probe jest stanem BUSY menu Ustawień, nie nowym typem `_EditorKind`. Takie rozróżnienie służy spisowi zachowania i nie sugeruje istnienia dodatkowych klas lub trybów w kodzie.

### K — klawiatura i mysz

- **K-panel:** `↑/↓` przesuwa kursor z zawijaniem, `Home/End` skraj listy, `PgUp/PgDn` o ostatnio wyrenderowaną stronę bez zawijania (`ui/state.py:443-445,1579-1584`). `←/→`, `Tab/Shift+Tab` przełączają zakładki; `Esc`, `Backspace`, niezaznaczony `Ctrl+C` wracają z listy do Home (`ui/state.py:432-455`). Wyjątki dla pól, pomocy, pytań i propozycji są opisane osobno. Litery działań są normalizowane przez `casefold` (`ui/state.py:454-455`). `O` wysyła `set_auto` z negacją `auto_enabled`; `M/U` otwierają Ręczny/Ustawienia (`ui/state.py:727-741`).
- **K-mysz:** klik w otagowany wiersz ustawia kursor. Drugi klik w ten sam *wiersz ekranu* w ciągu 0,4 s generuje Enter na kursorze ustawionym pierwszym klikiem; nie wybiera ponownie elementu, który mógł się w międzyczasie przesunąć (`ui/pointer.py:50,169-184`). Wiersz typu `LINE` nie uruchamia Enter (`ui/pointer.py:250-253`). PPM na wciśnięciu to Esc (`ui/pointer.py:145-150`). Przeciągnięcie zaznacza malowany tekst, kółko rozłącza podwójny klik. Kółko w listach State przewija widok o 3 wiersze bez zmiany wybranego elementu; klawiatura znów dociąga widok do kursora (`ui/state.py:669-700`). Klik innej zakładki działa jak jej wybór klawiaturą, klik wcześniejszego okruszka jak powroty; wyjątek bieżącej zakładki opisano w F (`ui/state.py:1292-1307`; `ui/pointer.py:267-272`).
- **K-kopiowanie:** `Ctrl+C`/`Ctrl+Insert` najpierw kopiują zaznaczenie ramki; bez zaznaczenia Ctrl+C trafia do danego ekranu jako przerwanie/powrót. Wynik: `Skopiowano zaznaczenie` albo `Nie udało się skopiować` (`FrameSelection.copy`, `ui/pointer.py:229-241`). Anime ma też własne `C` opisane przy jego ekranach.
- **K-pole:** każdy `TextInput`: pisanie/wklejanie drukowalnych znaków, Space, ←/→, Home/End, Ctrl+←/→ skoki słów, Ctrl+Home/End, warianty z Shift zaznaczające, Backspace/Delete, Ctrl+W i Alt+Backspace kasują wstecz słowo; Ctrl+Delete/Alt+D kasują naprzód, Ctrl+A zaznacza wszystko, Ctrl+X/Shift+Delete wycina, Ctrl+C przy zaznaczeniu i Ctrl+Insert kopiuje, Ctrl+V/Shift+Insert wkleja, Ctrl+Z/Y undo/redo (`ui/prompts.py:97-138`; `ui/text_input.py:20-49,98-119,155-229`). `Ctrl+Backspace` to nazwa znormalizowanej operacji, nie dodatkowy osobny binding w `_NORMALISED_KEYS`. Klik dowolnego miejsca linii pola ustawia kursor, poza tekstem na jego skraju (`ui/pointer.py:275-294`; `ui/text_input.py:149-153`).

### F — stopki, klikalność i szerokość

Panel składa akcje `ScreenActions.footer`, następnie `? więcej` i `Esc wróć`; początkowe `Enter wróć` scala do `Enter/Esc wróć` (`ui/actions.py:25,45-51`). Pakowanie mieści najwyżej dwie linie, odrzucając akcje od końca, zachowując `?` i Esc tak długo, jak pozwala szerokość; pojedynczy zbyt długi segment może zostać skrócony wielokropkiem (`ui/actions.py:54-59`; `ui/menu.py:116-138`). Podane niżej pełne stopki dotyczą szerokości, przy której wszystkie segmenty mieszczą się. Nie każdy ekran używa tego samego pakowania.

**Żadna podpowiedź klawisza w stopce nie jest przyciskiem myszy.** Dla State `_keys` tworzy tylko `mark_inert(Text(...))` bez `mark_target` (`ui/state.py:1569-1570`), a `click_at` bez celu zwraca pusty `Click` (`ui/pointer.py:275-294`). To brak tagu celu, a nie samo `inert`, dowodzi nieklikalności: `mark_inert` celowo zachowuje istniejące cele (`ui/pointer.py:256-259`), czego przykładem są zakładki. Wspólne stopki Manual tworzy analogicznie `with_footer` (`ui/menu.py:141-161`). Pola edycyjne umieszczone na dole ekranu są klikalne jako **pola**, nie jako podpowiedzi; PPM na stopce nadal uruchamia globalne Esc. Szczegółowe miejsca renderowania Anime/Ustawień/Home/Auto podano w ich sekcjach.

Pomoc generuje nagłówki `Ten ekran` i `Wszędzie`; druga część to dokładnie `↑↓ wybierz · ←→ zakładki · Tab zakładki · O automat · Esc wróć` (`ui/actions.py:16-22,62-70`). Są to opisy skrótów, nie cele myszy.

Stopki **tabel** Subskrypcji i Biblioteki idą inną drogą niż `_keys`: `AnimeSnapshot.controls` (`ui/state.py:1405`) → `anime_view._key_lines` (`ui/anime_view.py:559-561`). Także nie otrzymują tagów celu; tagowanie wierszy i pól wyboru jest odrębne (`ui/anime_view.py:178-188`).

Nad treścią panelu: `PANEL` (znika poniżej 12 wierszy, `ui/state.py:1206-1207`), pasek `Anime · Subskrypcje · Przetwarzanie · Biblioteka` (`ui/state.py:102,1296-1299`), a przy małej szerokości `← {zakładka} ({n}/4) →` z klikalnymi strzałkami (:1303-1307). Klik innej zakładki przełącza ją. Klik nazwy **bieżącej** zakładki w widoku zagnieżdżonym jest celem okruszka i wraca do jej poziomu listy, nie przełącza ponownie tej samej zakładki (`_TOP`, `ui/state.py:145,1300`; `ui/app.py:419-429`).

### G — dół panelu i globalne komunikaty

Pod stopką czterech zakładek stoi status automatu, poniżej ramka aplikacji pokazuje bieżący katalog i `v{version}` (`ui/state.py:1247,1442-1446`; `ui/prompts.py:536-553`). Przy bardzo małej szerokości katalog znika, wersja także może być skracana z lewej. Status Anime zostaje pominięty, jeśli jego obszar nie ma więcej niż `MIN_ROWS` (`ui/state.py:1228-1231`).

| Tekst | Źródło i rzeczywisty warunek |
|---|---|
| `Automat: brak połączenia` | `_NO_CONNECTION`, `ui/state.py:129,1477-1479`: brak połączenia lub pierwszego snapshotu. |
| `Automat wstrzymany` | `_PAUSED`, `ui/state.py:114,1468-1475`: znany stan, `auto_enabled` fałszywe, bez wyższego priorytetu zatrzymywania/niepełnej pauzy; liczniki znikają. |
| `Automat: pauza niepełna` | `_pause_state`, `ui/state.py:1471-1472`: `pause_incomplete`. |
| `Automat: zatrzymywanie` | `_pause_state`, `ui/state.py:1473-1474`: `pausing`, o ile nie ma niepełnej pauzy. |
| `Automat: praca` / `Automat: bezczynny` | `_global_status`, `ui/state.py:1480-1484`: istnieje/nie istnieje niezerowy (`truthy`) licznik z trzech pól `downloading/processing/waiting`; nie jest to liczba widocznych wierszy panelu. |
| `pobiera {N}` / `przetwarza {N}` / `czeka {N}` | `_STATUS_COUNTS`, `ui/state.py:132-136,1480-1487`: odpowiednio `material_counts.downloading/processing/waiting`, człony zerowe pomijane. Przy braku miejsca znikają od końca. |
| `O włącz` / `O wyłącz` | `_ENABLE_HINT`, `_DISABLE_HINT`, `ui/state.py:117-120,1485-1487`: pierwszy przy którymkolwiek stanie pauzy, drugi w pracy/bezczynności; mogą zniknąć z braku miejsca. |
| `Łączenie…` | `_CONNECTING`, `ui/state.py:126,1426-1428`: pusta lista przed pierwszym snapshotem. |
| `Wczytuję…` | `_LOADING`, `ui/state.py:123,1431-1437`: pusta Biblioteka podczas `library_loading` lub pusta Historia przy `_busy`. |
| `Wykonywanie polecenia…` | `_work`, `ui/state.py:939-940`: rozpoczęcie workera poza Biblioteką. |
| `Polecenie przyjęte` | `_work/_perform`, `ui/state.py:932,952,972`: domyślny sukces workera, jeżeli kontekst nadal aktualny; niektóre akcje jawnie przekazują pusty sukces. Biblioteka go nie pokazuje. |
| `Poprzednia czynność jeszcze trwa; możesz przejść do ustawień` | `_work`, `ui/state.py:935-938`: ponowne wywołanie podczas zajętości poza Biblioteką. Biblioteka milczy. |
| `Widok nieaktualny: odpowiedź przekracza limit` | `_receive`, `ui/state.py:1024-1028`: `control_problem`. Literał ma końcową kropkę, lecz `_notify` zawsze usuwa ją przed wyświetleniem (`ui/state.py:324`). |

Przekazane przez właściciela i błędy są sanitizowane przez `safe_text`/`refusal_text` (`ui/state_texts.py:128-151`); pełny zamknięty słownik odmów w dodatku A. Spóźniony wynik `_work` nie przechodzi do innej zakładki: `_perform` wymaga zgodnej generacji i kontekstu, a przełączenie zwiększa generację (`ui/state.py:619,967-978`). Niezależne błędy obserwatora `_watch` ustawiają notice w bieżącej zakładce (`ui/state.py:998-1000`). Już ustawiony `_notice` może przetrwać niektóre przejścia z Anime (`ui/state.py:706-709`), podczas gdy zwykły `_list_key` go czyści (:440).

Dokładne znaczenie liczników pochodzi z `AutomationOwner._status`, `app/automation.py:1711-1736`: `pobiera` liczy `stage=download` i `active=True`; `przetwarza` — `stage=processing` i `state=running`; `czeka` — każdy `stage=waiting` oraz przetwarzanie w `accepted/paused`. W tym wyliczeniu **nie ma filtra po `automatic`**. Status jest nazwany „Automat”, lecz nie należy z tego wywodzić, że liczy wyłącznie automatycznie zamówione materiały.

## S01 — Subskrypcje: lista z wierszami

### Klawisze i mysz

K-panel i K-mysz. `Enter` otwiera U08 wybranej subskrypcji; jeżeli `replay_list_batch()` wymaga odzyskania wyniku nieznanej partii szkicu, ten Enter **tylko odtwarza wynik** i kończy obsługę — szczegóły wymagają kolejnego Enter po rozliczeniu. `D` lub `/` otwiera wyszukiwarkę dodawania. `W` wstrzymuje/wznawia **subskrypcję**, `R` sprawdza teraz, `X/Delete` usuwa, `Ctrl+Z` przywraca ostatnio usuniętą; ciche aliasy `Space=W`, `F=R`. `?` pomoc. `Enter` na starym wpisie bez liczbowego AniList ID daje odmowę zamiast U08 (`ui/state.py:459-501`; `ui/state_subscriptions.py:45-50,98-100`). Klik wybiera, dwuklik wykonuje Enter, kółko przesuwa listę, PPM wraca. Usunięcie nie ma pytania.

### Stopka

`Enter szczegóły · D lub / dodaj · W wstrzymaj · ? więcej · Esc wróć`; przy `row.paused` zamiana na `W wznów`. Dalsze akcje tylko w pomocy: `R sprawdź teraz`, `X usuń`, `Ctrl+Z cofnij`, `M ręczny`, `U ustawienia` (`subscription_actions`, `ui/state_subscriptions.py:80-88`; test złoty `tests/cli/test_panel_keys.py:575`). Zasada F; wszystkie podpowiedzi nieklikalne.

### Dół ekranu poza stopką

Tabela wspólnego renderera: pełny stan, jeśli różni się od krótkiego, schowane kolumny, pełny ucięty tytuł; notatka o obejrzanych oraz świeże sprawdzenie pochodzi z `AnimeRow.detail/note` (`ui/state_subscriptions.py:54-76`; `ui/state.py:1365-1373,1386-1424`). Slot powiadomienia zawiera `_notice.rstrip(".")`. Nad tabelą może stać ostrzeżenie monitoringu/cienia. Status G zawsze na dole, według budżetu renderera.

### Komunikaty

- Stan/kolumny/podsumowanie subskrypcji: słownik Subskrypcji/U08 w części Anime raportu, źródło `ui/subscription_texts.py`; nie są niezależnymi tekstami listy.
- `Sprawdzam…` (`_CHECKING`, `ui/state_subscriptions.py:36,103-108`): wysłano żądanie R/F, jeszcze brak wyniku. Wynik sprawdzenia zastępuje Stan i opis na czas `CHECK_SHOWN_S`.
- `Monitoring nie działa: nie można zapisać stanu` (`subscription_warning`, `ui/state_subscriptions.py:91-95`): niepusty problem subskrypcji.
- `Tryb cienia — subskrypcje tylko zapisują propozycje` (`_SHADOW_WARNING`, `ui/state_subscriptions.py:39,95`): tryb shadow bez wyższego priorytetu problemu.
- `Sprawdzam wynik…` (`_subscription_key`, `ui/state.py:463-465`): odtwarzanie nieznanego wyniku partii.
- `Ta subskrypcja nie ma wpisu AniList · usuń ją i dodaj ponownie` (`_subscription_key`, `ui/state.py:475-477`): stary/nieprawidłowy wpis nie może otworzyć U08.
- `Usunięto {title} · Ctrl+Z cofnij` (`_subscription_command`, `ui/state.py:495-497`): potwierdzone usunięcie; tytuł sanitizowany, komunikat trwa do zmiany kontekstu/nawigacji.
- G, A-kontrola i A-subskrypcje, a przy spóźnionym wyniku partii także odmowy Anime.

### Naruszenia

R2-S: `D lub /` jawnie dubluje skrót dodawania. R1-BUSY: W/R/usuwanie opisane w stopce/pomocy nadal widoczne, gdy `_work` nie przyjmuje kolejnego polecenia. R1-S-ID: `Enter szczegóły` także na wpisie bez AniList ID. R3-MORE, R3-WAIT i R3-SHADOW: patrz tabela końcowa.

## S02 — Subskrypcje: pusta lista / pierwsze połączenie

### Klawisze i mysz

K-panel; D i `/` otwierają dodawanie, a `Enter` jest cichym aliasem na pustej liście. `Ctrl+Z` może przywrócić usuniętą; W/R/X/Space bez wiersza nic nie robią (`ui/state.py:459-474`). Klik pustego komunikatu nie wybiera; nie ma wiersza do dwukliku. PPM wraca, kółko bez elementów nie zmienia wyboru.

### Stopka

Po snapshotcie: `D lub / dodaj pierwszą · ? więcej · Esc wróć`; przed snapshotem tylko `? więcej · Esc wróć`. Pomoc ma `Ctrl+Z cofnij`, `M ręczny`, `U ustawienia` (`ui/state_subscriptions.py:80-84`). Zasada F.

### Dół ekranu poza stopką

Powiadomienie i G jak S01. Pusty komunikat jest wyszarzony, wyśrodkowany i nie ma tagu klikalnego wiersza (`ui/state.py:1400-1402,1420-1421,1439-1440`).

### Komunikaty

`Brak subskrypcji` (`NO_SUBSCRIPTIONS`, `ui/state_subscriptions.py:33`; wybór `ui/state.py:1426-1430`) dopiero po snapshotcie; wcześniej `Łączenie…`. G, A-subskrypcje i A-kontrola; po usunięciu także komunikat S01.

### Naruszenia

R2-S i R3-MORE/R3-WAIT. Brak R1 dla nieistniejącego wiersza: akcje wymagające wiersza są w tej stopce pominięte.

## S03 — Przetwarzanie: aktywna lista / pusta lista

### Klawisze i mysz

K-panel i K-mysz; `H` Historia; `?` pomoc. `W` steruje transferem, wyłącznie gdy `pause_toggle` ma wynik: pobieranie z hashem, bez fazy `pending_send`, `metaDL/forcedMetaDL`, `error/missingFiles`; stan zatrzymany daje wznowienie, pozostałe wstrzymanie. `X/Delete`, cichy `C`, uzbrajają pytanie anulowania tylko gdy jest hash pobierania albo run przetwarzania/przygotowania. `Enter` i dwuklik zwykłego wiersza niczego tu nie otwierają; `P` na bieżącej liście nie ma działania (`ui/state.py:761-774`; `ui/state_processing.py:188-207,248-258`).

### Stopka

Pobieranie z dostępnym W: `W wstrzymaj` lub `W wznów`, następnie `X anuluj · H historia · ? więcej · Esc wróć`. Run możliwy do anulowania albo pobranie z hashem, lecz bez W (`pending_send`, `metaDL/forcedMetaDL`, `error/missingFiles`): `X anuluj · H historia · ? więcej · Esc wróć`. Brak celu/pusta lista: `H historia · ? więcej · Esc wróć`. Pomoc dodatkowo `M ręczny · U ustawienia` (`processing_actions`, `ui/state_processing.py:188-200,220-229,248-255`). Zasada F, nieklikalne.

### Dół ekranu poza stopką

Slot `_notice`, stopka, G. Brak osobnego pełnego tytułu/ukrytych kolumn i brak zaznaczeń. Lista renderuje nazwy i paski, których procent/czas może zachowywać ostatni pomiar; przed pierwszym pomiarem zero. Dane listy to pobrania, przyjęte przygotowanie i potwierdzone wykonywanie, nie wszystkie materiały liczone statusem (`ui/state_processing.py:89-130`; `ui/state.py:1502-1530`).

### Komunikaty

`Brak aktywnego przetwarzania` (`NO_PROCESSING`, `ui/state_processing.py:63`; `ui/state.py:1433-1434`) przy pustej liście po snapshotcie, wcześniej G `Łączenie…`.

| Tekst etapu | Źródło / kiedy |
|---|---|
| `Materiał` | `material_name`, `ui/state_processing.py:149-154`: brak nazwy lub zamiast niej wyłącznie identyfikator. |
| `Finalizacja` | `download_progress`, `ui/state_processing.py:163-164`: `FINALIZATION_FAILED`; etykieta nie mówi wprost o błędzie. |
| `Wstrzymano` / `Przygotowanie` | `ui/state_processing.py:165-166`: oczekujący materiał, zależnie od pauzy automatu dla pracy automatycznej. |
| `Wymaga uwagi` | `ui/state_processing.py:167-168`: niepusty problem materiału. |
| etykieta `WAITING_PREVIOUS_TRANSFER` | `ui/state_processing.py:169-170`: wspólny słownik powodów Anime. |
| `Brak odczytu` | `ui/state_processing.py:171-172,183`: brak połączenia/problem odczytu transferów lub brak pomiaru pobierania. Także run bez połączenia `ui/state.py:1513-1514`. |
| `Wstrzymano` | `ui/state_processing.py:174-175`: klient raportuje zatrzymanie; run automatyczny także przy globalnej pauzie `ui/state.py:1513-1514`. |
| `Metadane` | `ui/state_processing.py:176-177`: klient pobiera metadane lub polecenie jeszcze `pending_send`. |
| `Brak transferu` | `ui/state_processing.py:178-179`: brak stanu klienta. |
| `Błąd transferu` | `ui/state_processing.py:180-181`: `error`/`missingFiles`. |
| `Brak źródeł` / `Pobieranie` | `ui/state_processing.py:182-184`: odpowiednio `stalledDL` lub czynne pobieranie z pomiarem. |
| `W kolejce` / `Pobrane` / `Przenoszenie` | `_TRANSFER_LABELS`, `ui/state_processing.py:78-85`: `queuedDL`, stany uploadu, `moving`. |
| `Sprawdzanie` | `ui/state_processing.py:185`: każdy pozostały stan klienta. |

Pozostałe etapy syntezy/przetwarzania są dokładnie wspólnymi etykietami `RichRunProgress` z sekcji Auto, nie osobnym słownikiem. G i A-kontrola.

### Naruszenia

R1-BUSY: dostępne W i status O nie uwzględniają workera. X nadal może uzbroić pytanie; blokada jego późniejszego zatwierdzenia należy do S04. R3-MORE, R3-WAIT, R3-FINALIZATION, R3-ATTENTION, R3-METADATA.

## S04 — Przetwarzanie: pytanie o anulowanie

### Klawisze i mysz

Enter wysyła anulowanie zapamiętanego celu; przy `_busy` nie wykonuje go i pozostawia pytanie. **Każdy inny klawisz**, także Tab/strzałki/Ctrl+C, tylko kasuje pytanie i jest połykany (`ui/state.py:370-379`). Każde wciśnięcie przycisku myszy kasuje pytanie bez wybrania wiersza (`ui/state.py:633-640`). Kółko samo nie jest potwierdzeniem. Zniknięcie celu ze snapshotu kasuje pytanie (`ui/state.py:381-386`).

### Stopka

Zastępuje zwykłą stopkę: `Anulować pobieranie? Enter tak · Esc nie`, przy paczce `Anulować pobieranie ({N} materiałów)? Enter tak · Esc nie`; dla runu `Anulować całe zlecenie ({N} materiałów)? Enter tak · Esc nie`. Gdy nie mieści się, pytanie i odpowiedzi zajmują osobne linie (`question_text`, `ui/state_processing.py:210-217`; `_ANSWERS`, `ui/state.py:148`; `_view_footer`, `ui/state.py:1310-1314`). Nie ma `?`. Nieklikalne.

### Dół ekranu poza stopką

Lista pozostaje, pytanie zastępuje normalne powiadomienia/akcje; pod nim G. N dla pobrania to liczba wierszy o wspólnym hashu, dla runu długość listy `group_ids`; brak klucza daje pustą listę i **0**, a wartość istniejąca, lecz niebędąca listą daje **1** (`ui/state_processing.py:216-217`). To nie liczba zaznaczonych wierszy.

### Komunikaty

Trzy pytania powyżej; po wykonaniu G `Wykonywanie polecenia…`, `Polecenie przyjęte` lub A-kontrola. W czasie pytania normalny `_notice` nie jest rysowany (`ui/state.py:1310-1321`).

### Naruszenia

R1-CANCEL: `Enter tak` pozostaje przy `_busy`, choć Enter wtedy nic nie wysyła. R1-O-MODAL: status może pokazywać O, ale klawisz tylko zamyka pytanie. R3-WAIT.

## S05 — Przetwarzanie: Historia (H)

### Klawisze i mysz

K-panel/K-mysz; Enter otwiera wynik wybranego materiału po walidacji ownera; `P` pobiera propozycję ponowienia. `/` otwiera pole szukania, cichy `S` to alias. `H`, Esc, Backspace lub niezaznaczony Ctrl+C zamykają Historię i wracają do aktywnej listy. `?` pomoc Historii. `M/U/O` jak lista. Brak działania F folder w handlerze Historii (`ui/state.py:418-430,727-751,805-814`). Pusta lista nie ma celu dla Enter/P; klik/dwuklik zgodnie K-mysz.

Zmiana zakładki przez Tab/←→ zachowuje `_history_open`: po powrocie do Przetwarzania nadal pokazuje Historię (`ui/state.py:615-626`); jawne `show_processing` ją zamyka (:308-315). H podczas `_busy` otwiera Historię, lecz jej odczyt zostaje odrzucony przez `_work`; zostają poprzednie `_history_items` bez automatycznego ponowienia (`ui/state.py:735-739,776-803,935-938`).

### Stopka

Zawsze `Enter otwórz · P ponów · / szukaj · ? więcej · Esc wróć`, również pusta/niedostępna Historia. Pomoc dodaje `H zamknij · M ręczny · U ustawienia` (`HISTORY_ACTIONS`, `ui/state_processing.py:58-60`; `ui/state.py:1359-1360`). Zasada F.

### Dół ekranu poza stopką

Po klawiszach stoją `_history_problem`, `_notice`, następnie G — inaczej niż w zwykłej liście, gdzie powiadomienie poprzedza klawisze (`ui/state.py:1317-1320`). Okruszek `Przetwarzanie › Historia` (`ui/state.py:142,1453-1454`).

### Komunikaty

- `Brak pozycji` (`NO_HISTORY`, `ui/state_processing.py:66`), `Historia niedostępna` (`HISTORY_UNAVAILABLE`, `ui/state_processing.py:69`) lub G `Wczytuję…/Łączenie…`; wybór `ui/state.py:1426-1437`.
- `Historia niedostępna · uszkodzony zapis; przetwarzanie działa dalej` oraz `Historia niedostępna · błąd odczytu lub zapisu; przetwarzanie działa dalej` (`HISTORY_PROBLEMS`, `ui/state_processing.py:49-52`): trwałe ostrzeżenia odczytu Historii.
- Wiersz `{data i czas} · {nazwa} · {zdarzenie}`, opcjonalnie ` · odtworzony zapis · czas przyjęcia` (`history_entry`, `ui/state_processing.py:232-238`): ostatni człon oznacza rekord odtworzony z przyjęcia, nie pomiar rzeczywistego czasu zakończenia.
- Zdarzenia `_HISTORY_LABELS`: `przyjęto zamówienie` (:38), `pobrano źródło` (:39), `przyjęto regenerację` (:40), `ukończono` (:41), `błąd` (:42), `przerwano` (:43), `usuwanie` (:44), `subskrypcja zakończona` (:45), wszystkie `ui/state_processing.py`; nieznany rodzaj pokazuje surowe `item.kind` (:236).
- `Historia z ostatnich 30 dni` w pomocy (`HISTORY_SPAN`, `ui/state_processing.py:55`; `ui/state.py:1334`). G, A-retry, A-kontrola, A-biblioteka przy otwarciu wyniku.

### Naruszenia

R1-H-EMPTY: Enter/P widoczne bez żadnego materiału. R1-BUSY dla akcji wymagających workera. R3-MORE/R3-WAIT. Rozbieżność F folder z opisem AGENTS odnotowana na końcu.

## S06 — Historia: pole wyszukiwania

### Klawisze i mysz

K-pole. Enter zapisuje query i ładuje wyniki, chyba że `_busy`; Esc lub niezaznaczony Ctrl+C zamyka pole. Backspace kasuje, nie wraca. Wszystkie aplikacyjne skróty literowe wpisują tekst. Tab nie zmienia zakładki, bo `_history_input_key` przechwytuje wejście wcześniej (`ui/state.py:351-353,816-833`). Klik ustawia kursor; PPM to Esc; lista w tle pozostaje dostępna dla przewijania.

### Stopka

`Enter szukaj · Esc anuluj`, bez `?`, pod polem (`ui/state.py:1318-1319`). Nieklikalna; samo pole klikalne.

### Dół ekranu poza stopką

Pole z zapytaniem, klawisze, `_history_problem`, G. `_notice` nie jest tutaj dołączony do listy renderowanych wierszy (`ui/state.py:1319`).

### Komunikaty

Historia i G nadal widoczne. `Poprzednia czynność jeszcze trwa; zatwierdź wyszukiwanie po jej zakończeniu` jest ustawiane przez `_history_input_key` (`ui/state.py:823-827`), **ale podczas aktywnego pola `_view_footer` nie renderuje `_notice`**; nie należy uznawać go za zawsze widoczny. Może zostać pokazany po opuszczeniu pola, zanim nadpisze go kolejny wynik.

### Naruszenia

R1-H-SEARCH: Enter szukaj przy `_busy` nie wykonuje wyszukiwania. R1-O-MODAL: O w statusie wpisuje literę zamiast sterować automatem. R3-WAIT. Dodatkowa obserwacja poza R1–R3: niewidoczny w polu komunikat zajętości opisany wyżej.

## S07 — Historia: propozycja ponowienia (P)

### Klawisze i mysz

Enter na `manual/resume` przekazuje propozycję do Ręcznego, na innej trasie zleca jawne ponowne pobranie. Esc/Backspace/niezaznaczony Ctrl+C kasują propozycję. Inne klawisze, w tym Tab/O, ignorowane (`ui/state.py:847-861`). `select()` odmawia wyboru przy `_retry`; nie ma nawigacji po opcjach. PPM zamyka. Renderowany jeden wiersz pochodzi ze wspólnej listy; akcją potwierdzającą jest Enter.

### Stopka

`Enter przygotuj · Esc wróć`, bez `?` (`ui/state.py:1315-1316`). Nieklikalna.

### Dół ekranu poza stopką

Za stopką `_notice`, G; jedna linia propozycji zamiast listy Historii (`ui/state.py:1489-1493`).

### Komunikaty

- `Popraw wybrany lokalny materiał w Ręcznym · wybór zakresu przebudowy` (`_RETRY_LABELS`, `ui/state_processing.py:73`): trasa manual.
- `Pobierz ponownie zachowane wydanie · nowe jawne zamówienie` (`ui/state_processing.py:74`): trasa reacquire.
- `Dokończ całe zapisane zlecenie · {N} materiałów · podgląd` (`retry_entry`, `ui/state_processing.py:241-245`): resume obejmuje całe zlecenie.
- `Nieznana droga ponowienia` (`ui/state_processing.py:245`): nieobsługiwana trasa.
- `Nieaktualne ponowienie; wybierz materiał jeszcze raz` (`_execute_repeat`, `ui/state.py:1592-1597`): brak poprawnej trasy reacquire/operation_id.
- G, A-retry i A-kontrola.

### Naruszenia

R1-O-MODAL: O z linii statusu ignorowane. R3-WAIT. Nieznana trasa jest obsługą nieoczekiwanego payloadu, a nie udowodnionym normalnie osiągalnym ekranem.

## S08 — Biblioteka: lista (także pusta)

### Klawisze i mysz

K-panel/K-mysz. Enter otwiera zweryfikowany główny wynik, F wskazuje go w folderze; Del usuwa cały zestaw bez pytania, cichy X to alias. `?` otwiera szczegóły przy wybranym wierszu, połączeniu i bez `_busy`, w pozostałych przypadkach pomoc; cichy D to alias. Ctrl+Z przywraca ostatnie usunięcie (`ui/state.py:360-365,742-759,863-875`). **P nie ma akcji.** Klik wybiera, dwuklik Enter; usuwanie natychmiast chowa wiersz i działa osobnym wątkiem, niezależnie od `_busy` (`ui/state.py:880-912`).

### Stopka

Z wierszem `Enter otwórz · F folder · Del usuń · ? więcej · Esc wróć`; bez wiersza `? więcej · Esc wróć`. Pomoc dodaje `Ctrl+Z cofnij · M ręczny · U ustawienia` (`library_actions`, `ui/state_library.py:104-109`). Zasada F.

### Dół ekranu poza stopką

Tabela `Nazwa · Odcinek`; tekst utracony przez zwężenie pokazywany przez wspólny renderer, przy zbyt małym terminalu fallback do listy pełnych etykiet (`ui/state.py:1375-1424`; `ui/state_library.py:88-96`). Pod nią wyłącznie trwały `_notice` i `_library_notice`, bez rutynowego komunikatu workera ani wiersza przeniesień (`ui/state.py:1323-1329,1375-1383`). G. Okruszek listy pusty.

### Komunikaty

`Biblioteka jest pusta` (`EMPTY_LIBRARY`, `ui/state_library.py:35`), G `Łączenie…/Wczytuję…`, A-biblioteka i A-kontrola. Sukcesy otwarcia/folderu/szczegółów są ciche w Bibliotece (`ui/state.py:972`). `_library_notice` przechowuje sanitizowane `navigation.notification_problem` (`ui/state.py:280-290`); aplikacja nadaje mu `Wynik powiadomienia jest niedostępny lub zmieniony w Bibliotece` (`_UNAVAILABLE_NOTIFICATION`, `app/automation.py:318,1050,8349`), gdy wynik wskazany powiadomieniem nie daje się potwierdzić. Stan po usunięciu osobno S10.

Ten `_library_notice` nie znika przy ruchu, zmianie zakładki ani wejściu w szczegóły; zmienia go dopiero następne `show_library` (`ui/state.py:209,290,1327-1328,1382`).

### Naruszenia

R1-BUSY: Enter/F pozostają widoczne, gdy `_work` milcząco pomija akcję. R3-MORE/R3-WAIT. Samo istnienie ownerowej walidacji lub możliwy błąd I/O nie jest automatycznie liczone jako R1.

## S09 — Biblioteka: szczegóły zestawu (`?`, alias D)

### Klawisze i mysz

↑↓/Home/End/PgUp/PgDn po **wszystkich** wierszach szczegółów, także informacyjnych; Enter otwiera wybrany plik, F jego folder, tylko jeśli istnieje `LibraryFileIdentity`. Del/X usuwa **cały zestaw**, niezależnie od wskazanego pliku. Ctrl+Z cofa ostatnie usunięcie; O/M/U pozostają dostępne. Esc/Backspace/Ctrl+C/`?` zamykają, Tab/←→ zamykają i zmieniają zakładkę (`ui/state.py:553-597`). Klik wybiera, dwuklik Enter; kółko przewija pliki, PPM wraca.

### Stopka

Zawsze `Enter otwórz plik · F folder · Del usuń · Esc wróć`, bez `? więcej` (`DETAIL_ACTIONS`, `ui/state_library.py:41-43`; `ui/state.py:1329`). Nie zależy od rodzaju wybranego wiersza ani tożsamości pliku. Wszystkie podpowiedzi nieklikalne.

### Dół ekranu poza stopką

Pod plikami, jeśli pozostały przynajmniej 3 wiersze, tekst pomocy `Ten ekran`/`Wszędzie`, bez możliwości wybrania; ucina się przed plikami. Trwałe powiadomienia, G. Okruszek `Biblioteka › {etykieta zestawu}` (`ui/state.py:1273-1275,1455-1456`). Pierwsza pozycja to nazwa zestawu, nie plik.

### Komunikaty

- `Cel nierozstrzygnięty · regeneracja wymaga wyboru` (`detail_entries`, `ui/state_library.py:115-116`): brak celu zestawu.
- `Pochodzenie zestawu wymaga rozstrzygnięcia przed usunięciem` (`ui/state_texts.py:98`, włączane przez `ui/state_library.py:117-118`): nieznane pochodzenie.
- `Czasy robocze · skrypt lektora bez synchronizacji z nagraniem` (`ui/state_library.py:119-120`): provisional timing.
- Wiersz `{path} · {format} · {rola} · {size:,} B`, albo `brak` zamiast rozmiaru, dodatkowo ` · główny` (`ui/state_library.py:121-125`). Role `_FILE_ROLES`: `źródło` (:51), `wynik` (:52), `źródło · czeka na zwolnienie` (:53).
- `Wybierz wiersz pliku` (`_open_detail_file`, `ui/state.py:579-582`): Enter/F na informacji.
- `Wybrany plik jest niedostępny` (`ui/state.py:583-587`): plik bez identity.
- G, A-biblioteka, A-kontrola.

### Naruszenia

R1-L-INFO: Enter/F reklamowane również na nazwie/opisie; R1-L-MISSING: to samo dla pliku bez identity. R1-BUSY; R3-WAIT. Opis nierozstrzygniętej regeneracji nie oznacza istnienia skrótu P na tym ekranie.

## S10 — Biblioteka: stan po usunięciu / Ctrl+Z

### Klawisze i mysz

Jak S08; Ctrl+Z wysyła `undo_deletion()` także na pustej liście, **o ile `_busy` nie blokuje `_work`** — przy zajętości jest po cichu pomijane. Nie jest przywiązane do wiersza, który teraz jest pod kursorem (`ui/state.py:360-363,935-938`). PPM/klik/dwuklik/kółko według S08. Kolejne usunięcia nie czekają na zakończenie poprzedniego workera (`ui/state.py:880-911`).

### Stopka

Jak S08, zależna od tego, czy pozostał wiersz. `Ctrl+Z cofnij` jest w powiadomieniu i pomocy, a nie dodatkowym przyciskiem stopki (`ui/state_library.py:38,104-109`). Nieklikalne.

### Dół ekranu poza stopką

`Usunięto · Ctrl+Z cofnij` jest trwałym `_notice` do następnego ruchu/zmiany widoku; wiersz usunięty znika, po odmowie wraca z tekstem odmowy (`ui/state.py:888-911,337-348`). G pozostaje.

### Komunikaty

`Usunięto · Ctrl+Z cofnij` (`LIBRARY_DELETED`, `ui/state_library.py:38`); po Ctrl+Z brak obowiązkowego komunikatu sukcesu, przy odmowie A-biblioteka `restore_*`; przy usunięciu A-biblioteka `recycle_*` i inne odmowy. Jeśli brak wierszy — `Biblioteka jest pusta` jak S08.

### Naruszenia

R1-BUSY dla Enter/F i reklamowanego w notice Ctrl+Z, które też przechodzi przez `_work`; R3-MORE/R3-WAIT. Powtórzenie Ctrl+Z w pomocy i powiadomieniu nie jest liczone jako R2 stopki.

## S11 — Pomoc listy Subskrypcji

### Klawisze i mysz

↑↓, PgUp/PgDn, Home/End oraz kółko przewijają blok. Esc/Backspace/`?`/niezaznaczony Ctrl+C zamykają; Tab/←→ zamykają i przełączają zakładkę; O działa. Pozostałe klawisze, **także M/U i akcje wypisane w „Ten ekran”**, są ignorowane (`ui/state.py:392-412`). Klik nic nie wybiera, brak wierszy do dwukliku (`ui/state.py:669-675,1332-1351`); PPM zamyka, tekst można zaznaczyć i skopiować.

### Stopka

`Esc wróć` (`ui/state.py:1336`), nieklikalna.

### Dół ekranu poza stopką

G; powiadomienia listy ustępują blokowi pomocy.

### Komunikaty

`Ten ekran`, `Wszędzie` i dokładne akcje S01/S02 + część wspólna F (`ui/actions.py:62-70`; `ui/state.py:1334-1335`). Nie pojawia się nowy słownik odmów, dopóki nie zostanie wywołane O.

### Naruszenia

R3-WAIT. Jeśli R1 obejmuje również treść pomocy, akcje „Ten ekran” są opisem ekranu pod spodem, nie działają z samej pomocy; odnotowano tę różnicę bez doliczania jej do R1 stopki.

## S12 — Pomoc listy Przetwarzania

### Klawisze i mysz

Dokładnie S11 (`ui/state.py:392-412,669-700`).

### Stopka

`Esc wróć`, nieklikalna (`ui/state.py:1336`).

### Dół ekranu poza stopką

G, bez slotu powiadomienia listy.

### Komunikaty

`Ten ekran`, `Wszędzie`, akcje aktualnego wiersza S03 oraz F (`ui/state.py:1335,1361-1362`; `ui/state_processing.py:220-229`).

### Naruszenia

R3-WAIT; uwaga o działaniach opisanych, lecz niedostępnych w pomocy jak S11.

## S13 — Pomoc Historii

### Klawisze i mysz

Dokładnie S11; H z otwartej pomocy jest ignorowane (`ui/state.py:358-359,392-412`).

### Stopka

`Esc wróć`, nieklikalna (`ui/state.py:1336`).

### Dół ekranu poza stopką

G; zachowany okruszek Historii, brak `_history_problem` w tym rendererze.

### Komunikaty

`Historia z ostatnich 30 dni`, `Ten ekran`, `Wszędzie`, akcje S05 i F (`ui/state.py:1334-1335`; `ui/state_processing.py:55-60`).

### Naruszenia

R3-WAIT; uwaga o opisach akcji jak S11.

## S14 — Pomoc Biblioteki bez otwierania szczegółów

### Klawisze i mysz

Dokładnie S11. Otwierana `?`/D, gdy lista pusta, niepołączona lub `_busy`; przyjście wcześniej zamówionych szczegółów zamyka pomoc (`ui/state.py:755-759,914-923`).

### Stopka

`Esc wróć`, nieklikalna (`ui/state.py:1336`).

### Dół ekranu poza stopką

G, bez powiadomienia Biblioteki.

### Komunikaty

`Ten ekran`, `Wszędzie`, akcje S08 zgodne z istnieniem wybranego wiersza, F (`ui/state.py:1335,1363`; `ui/state_library.py:104-109`).

### Naruszenia

R3-WAIT; uwaga o opisach akcji jak S11.

## Dodatek A — wspólny słownik odmów State/wywołań aplikacji

Wszystkie poniższe teksty pochodzą z `ui/state_texts.py`. Klucz identyfikuje rzeczywisty powód od ownera; zdanie jest tłumaczeniem tego powodu. `refusal_text` najpierw wybiera retry/subskrypcje, potem odmowy i Bibliotekę, następnie kod IPC/fallback (`:128-145`). To słownik możliwych odpowiedzi, nie twierdzenie, że każdy ekran normalnie emituje każdy powód.

### A-retry

| Powód → dokładny tekst | Źródło |
|---|---|
| `retry_source_missing` → `Brak lokalnego źródła; usuniętej treści nie można odtworzyć` | `_RETRY_PROBLEMS`, `ui/state_texts.py:18` |
| `retry_reference_missing` → `Brak zachowanej referencji wydania; wybierz wydanie ponownie w Anime` | `ui/state_texts.py:19` |
| `retry_choose_one` → `Zakres zawiera lokalne materiały; wybierz jeden numer, aby zobaczyć właściwe dokończenie lub poprawkę` | `ui/state_texts.py:20-22` |
| `retry_source_available` → `Źródło jest już lokalnie; ponownie wybierz Ponów, aby przygotować Ręczny` | `ui/state_texts.py:23` |
| `retry_acquisition_pending` → `Wcześniejsze przekazanie nadal wymaga uzgodnienia; nie dodano drugiego pobrania` | `ui/state_texts.py:24` |
| `legacy_subscription_retry` → `Pobierz ten odcinek ponownie z Anime (P)` | `ui/state_texts.py:25` |

### A-kontrola

| Powód/kod → dokładny tekst | Źródło |
|---|---|
| GROUP_RESERVED → `Inny panel zajął ten odcinek` | `_REFUSAL_TEXTS`, `ui/state_texts.py:45` |
| GROUP_PROCESSING / ALREADY_PROCESSING → `Ten odcinek jest już przetwarzany` | `ui/state_texts.py:46,72` |
| GROUP_RELOCATING → `Gotowy odcinek jest przenoszony do biblioteki` | `ui/state_texts.py:47` |
| SESSION_CLOSED → `Połączenie z procesem w tle wygasło` | `ui/state_texts.py:48` |
| CLIENT_BOUND → `Ten panel jest już połączony w innej sesji` | `ui/state_texts.py:49` |
| NOT_RESERVED → `Najpierw zajmij odcinek, potem dodaj do niego plik` | `ui/state_texts.py:50` |
| FOREIGN_PREVIEW → `Ten wybór należy do innego panelu` | `ui/state_texts.py:51` |
| NOT_RESUMABLE → `Tej pracy nie da się wznowić` | `ui/state_texts.py:52` |
| PAUSED → `AniShift jest wstrzymany · wybierz Wznów, aby podjąć pracę` | `ui/state_texts.py:53` |
| SHUTTING_DOWN → `AniShift się kończy · nie przyjmuje już nowej pracy` | `ui/state_texts.py:54` |
| TRANSFER_METADATA_PENDING → `Trwa przygotowanie pobrania · poczekaj na potwierdzenie wyboru plików` | `ui/state_texts.py:55-57` |
| brak znanego powodu/REFUSED → `Proces w tle odrzucił polecenie` | `_UNKNOWN_REFUSAL`, `ui/state_texts.py:62,73` |
| STALE_INSTANCE → `Proces w tle został uruchomiony ponownie · otwórz panel ponownie` | `_CONTROL_PROBLEMS`, `ui/state_texts.py:67` |
| UNKNOWN_COMMAND → `Proces w tle nie obsługuje tego polecenia` | `ui/state_texts.py:68` |
| INVALID_PAYLOAD → `Proces w tle odrzucił niepoprawne dane polecenia` | `ui/state_texts.py:69` |
| STALE_PREVIEW → `Podgląd jest nieaktualny · przygotuj go ponownie` | `ui/state_texts.py:70` |
| CONFLICT → `Polecenie koliduje z bieżącą pracą` | `ui/state_texts.py:71` |
| INTERNAL → `Wewnętrzny błąd procesu w tle · sprawdź log` | `ui/state_texts.py:74` |
| brak potwierdzonej odpowiedzi IPC → `Brak potwierdzonej odpowiedzi procesu w tle · sprawdź, czy proces działa, oraz Historię i log przed ponowieniem` | `refusal_text`, `ui/state_texts.py:141-142` |

`safe_text` zastępuje także cztery angielskie komunikaty klienta torrent (`_CLIENT_PROBLEMS`, :29-40): `qBittorrent wyłączony · zlecenia czekają na wznowienie` (:31; zamknięte prywatne okno), `qBittorrent sterowany ręcznie` (:33; przejęty klient), `Otwarto qBittorrenta · sterowanie automatyczne wstrzymane` (:35; uruchomienie ręczne), `Nie udało się uruchomić qBittorrenta · usuń przyczynę i wybierz Wznów` (:38; błąd startu). Inny wyjątek pokazuje sanitizowane `str(problem)` (:135,145), inny tekst właściciela sanitizowany tekst bez tłumaczenia (:148-151).

### A-subskrypcje

| Powód → dokładny tekst | Źródło `_SUBSCRIPTION_PROBLEMS` |
|---|---|
| subscription_missing → `Tej subskrypcji już nie ma` | `ui/state_texts.py:81` |
| nothing_to_restore → `Brak usuniętej subskrypcji do przywrócenia` | `ui/state_texts.py:82` |
| subscription_exists → `Ten sezon jest już subskrybowany` | `ui/state_texts.py:83` |
| subscription_limit → `Osiągnięto limit subskrypcji; usuń jedną, aby dodać lub przywrócić` | `ui/state_texts.py:84` |
| subscription_not_airing → `Ten wpis nie ma przyszłych odcinków` | `ui/state_texts.py:85` |
| subscription_cut_unknown → `Nie wiadomo, ile odcinków już wyemitowano · spróbuj później` | `ui/state_texts.py:86` |
| source_failed → `Nie udało się odczytać katalogu · spróbuj ponownie` | `ui/state_texts.py:87` |
| target_not_waiting → `Ten odcinek już nie czeka na polskie napisy` | `ui/state_texts.py:88` |

### A-biblioteka

| Powód → dokładny tekst | Źródło `LIBRARY_PROBLEMS` |
|---|---|
| library_set_missing → `Tego zestawu nie ma już w bibliotece` | `ui/state_texts.py:95` |
| library_result_missing → `Brakuje potwierdzonego głównego wyniku` | `ui/state_texts.py:96` |
| library_result_changed → `Główny wynik istnieje, ale jest zmieniony lub niepotwierdzony` | `ui/state_texts.py:97` |
| library_ownership_unknown → `Pochodzenie zestawu wymaga rozstrzygnięcia przed usunięciem` | `ui/state_texts.py:98` |
| library_source_held → `Źródło czeka na zwolnienie przez torrent` | `ui/state_texts.py:99` |
| library_source_missing → `Brakuje źródłowego pliku wideo tego zestawu` | `ui/state_texts.py:100` |
| library_scope_changed → `Zestaw zmienił się · przygotuj nowe potwierdzenie` | `ui/state_texts.py:101` |
| library_source_busy → `Plik jest nadal zapisywany lub niedostępny` | `ui/state_texts.py:102` |
| library_deleting → `Zestaw jest chroniony przez operację Kosza lub przywracania` | `ui/state_texts.py:103` |
| recycle_unsupported → `Kosz jest niedostępny dla tego środowiska` | `ui/state_texts.py:104` |
| recycle_unavailable → `Nie udało się potwierdzić dostępności operacji Kosza` | `ui/state_texts.py:105` |
| recycle_refused → `System odmówił przeniesienia pliku do Kosza` | `ui/state_texts.py:106` |
| recycle_timeout → `Upłynął limit operacji · jej wynik pozostaje niepewny` | `ui/state_texts.py:107` |
| recycle_cleanup_timeout → `Upłynął limit zamykania operacji · jej wynik pozostaje niepewny` | `ui/state_texts.py:108` |
| recycle_interrupted → `Operacja została przerwana · jej wynik pozostaje niepewny` | `ui/state_texts.py:109` |
| recycle_invalid_evidence → `Brak poprawnego potwierdzenia operacji Kosza` | `ui/state_texts.py:110` |
| recycle_incomplete → `System nie potwierdził pełnego wyniku operacji` | `ui/state_texts.py:111` |
| library_release_unavailable → `Nie można odczytać potwierdzenia zwolnienia torrenta` | `ui/state_texts.py:112` |
| restore_nothing → `Brak usuniętego zestawu do przywrócenia` | `ui/state_texts.py:113` |
| restore_already_completed → `Ostatnie usunięcie zostało już cofnięte` | `ui/state_texts.py:114` |
| restore_destination_occupied → `Miejsce przywracania jest zajęte · istniejący plik pozostawiono bez zmian` | `ui/state_texts.py:115` |
| restore_receipt_missing → `Brak dokładnego elementu w Koszu · mógł zostać opróżniony` | `ui/state_texts.py:116` |
| restore_unsupported_destination → `Przywracanie wymaga dostępnego miejsca na tym samym woluminie NTFS` | `ui/state_texts.py:117` |
| restore_unsafe_path → `Ścieżka przywracania jest niedostępna lub prowadzi przez dowiązanie` | `ui/state_texts.py:118` |
| restore_scope_changed → `Pliki przywracania zmieniły się · nie wykonano kolejnej operacji` | `ui/state_texts.py:119` |
| restore_interrupted → `Przywracanie przerwane · Ctrl+Z sprawdzi zapisany stan przed ponowieniem` | `ui/state_texts.py:120` |
| restore_incomplete → `System nie potwierdził pełnego przywrócenia` | `ui/state_texts.py:121` |
| restore_inflight → `Przywracanie wymaga rozliczenia zapisanej operacji` | `ui/state_texts.py:122` |

## Rozbieżności dokumentacji z kodem — część wspólnego panelu

Dowody testowe były **czytane, nie uruchamiane**: złote stringi i pakowanie 80/50 kolumn (`tests/cli/test_panel_keys.py:565-586,699-722`), pytanie tylko z celem i brak jego potwierdzenia podczas `_busy` (`:1044-1095`), połykanie innych klawiszy/myszy (`:1098-1122`), pomoc ignorująca akcje i kliknięcia (`:794-846`). Sonda „every listed action” używa `_APPLIES`, tj. podstawia stan, w którym dana akcja ma zastosowanie (`:551-563,739-743`); dlatego zgodność z tym testem nie dowodzi R1 dla każdego możliwego wiersza/stanu.

1. Plan §3.1 i przykładowa stopka przewidują ciche D oraz `/ dodaj`; kod i testy jawnie pokazują `D lub / dodaj` / `dodaj pierwszą` (`docs/archive/tui-unify/plan.md:78-87,151-152`; `ui/state_subscriptions.py:42,80-88`; `tests/cli/test_panel_keys.py:575-576`).
2. Plan pokazuje `X usuń` w Bibliotece, kod pokazuje `Del usuń`, X pozostaje aliasem (`docs/archive/tui-unify/plan.md:155-156`; `ui/state_library.py:41-43,104-109`; `tests/cli/test_panel_keys.py:580-581`).
3. Plan opisuje Bibliotekę jako pojedynczą listę bez kolumn; kod używa tabeli `AnimeScreen.LIBRARY` i etykiet Nazwa/Odcinek, z listą jako fallback (`docs/archive/tui-unify/plan.md:233-235`; `ui/state.py:1375-1424`; `ui/state_library.py:88-96`).
4. Plan nie przewiduje podpowiedzi O w linii statusu; kod dodaje `O włącz` / `O wyłącz` (`docs/archive/tui-unify/plan.md:240-247`; `ui/state.py:117-120,1485-1487`). AGENTS mówi miejscami o `O wznów` nad treścią, lecz `_subscription_body` przekazuje wyłącznie problem/cień, a bieżący status automatu jest przypięty na dole (`anishift/cli/AGENTS.md:107-109`; `ui/state.py:1365-1373,1442-1446`).
5. Opis Historii w AGENTS wspomina F do folderu; ścieżki klawiszy Historii nie obsługują F. `_open_episode(..., show_folder=True)` jest wywoływane z Biblioteki (`anishift/cli/AGENTS.md:164-171`; `ui/state.py:418-430,727-751,805-814,863-875`).
6. Fragment planu nadal wymienia P przy problemie relokacji Biblioteki, choć jego aktualizacja wyżej i kod usuwają tę akcję (`docs/archive/tui-unify/plan.md:133-135,172`; `ui/state_library.py:104-109`; `ui/state.py:863-875`).
7. „Tab zawsze przełącza” ma poza pytaniem anulowania również wyjątki: pole Historii i propozycja ponowienia pochłaniają Tab (`docs/archive/tui-unify/plan.md:58,106`; `ui/state.py:349-355,816-861`).
8. Dokumentacja mówi o jednym slocie powiadomienia; renderer Historii może mieć po klawiszach osobno problem i notice, szczegóły Biblioteki dodatkowo pomoc. Opis w raporcie zachowuje faktyczną kolejność (`docs/archive/tui-unify/plan.md:238`; `ui/state.py:1273-1275,1317-1320`).
9. Plan nazywa `material_counts` „licznikami automatu”, ale owner sumuje materiały po fazie/stanie bez sprawdzania `automatic`. Panel poprawnie korzysta z tego jednego źródła, lecz nazwa statusu nie określa pochodzenia zleceń (`docs/archive/tui-unify/plan.md:249-250`; `app/automation.py:1724-1736`).

## Tabela zbiorcza naruszeń — wspólny panel

Liczenie: jeden wiersz = jeden odrębny mechanizm/komunikat, także gdy występuje na kilku ekranach. Nie liczę powtórzeń tego samego `? więcej` na kilkunastu ekranach jako kilkunastu usterek. R3 poza przykładami właściciela jest oceną zrozumiałości opartą na rozbieżności między tekstem a faktycznym stanem; nie wynikiem badania użytkowników. Odmowa właściciela po rzeczywistej próbie działania sama w sobie nie dowodzi R1; poniżej są przypadki znanych już UI blokad lub braku celu.

| ID | Ekran / tekst | Reguła | Obserwacja i dowód |
|---|---|---|---|
| R1-BUSY | S01, S03, S05, S08–S10; W / Enter / F / P, O w statusie i Ctrl+Z w notice podczas `_busy` | R1 | Funkcje akcji nie dostają `_busy`, `_work` przy nim wraca bez wykonania. Biblioteka milczy; pozostałe zakładki dają komunikat zajętości. `ui/state.py:360-361,928-940,1354-1363`; `ui/state_subscriptions.py:80-88`; `ui/state_library.py:41-43,104-109`; `ui/state_processing.py:58-60,220-229`. H otwiera Historię, ale nie ładuje jej przy `_busy` (`ui/state.py:735-739,803`). Del/X Biblioteki ma osobny worker, X Przetwarzania nadal uzbraja pytanie — oba wyłączone z tej obserwacji. |
| R1-S-ID | S01 `Enter szczegóły` | R1 | Stopka zależy od istnienia wiersza, nie od AniList ID; handler odmawia otwarcia, gdy ID nie jest int. `ui/state_subscriptions.py:80-88`; `ui/state.py:475-477`. |
| R1-CANCEL | S04 `Enter tak` | R1 | Przy `_busy` Enter zachowuje pytanie, nic nie wysyła; stopka nie ma tego warunku. `ui/state.py:370-377,1310-1314`. |
| R1-H-EMPTY | S05 `Enter otwórz · P ponów` | R1 | Stałe `HISTORY_ACTIONS` także przy pustej/niedostępnej Historii; handler robi coś tylko przy indeksie istniejącego zdarzenia. `ui/state_processing.py:58-60`; `ui/state.py:805-813,1359-1360`. |
| R1-H-SEARCH | S06 `Enter szukaj` | R1 | Przy `_busy` handler zachowuje pole i nie wyszukuje, stopka nadal poleca Enter. `ui/state.py:823-830,1318-1319`. |
| R1-L-INFO | S09 `Enter otwórz plik · F folder` na nazwie/opisie | R1 | Akcje stałe; pierwszy wybrany wiersz po otwarciu to nazwa. Handler zwraca `Wybierz wiersz pliku`. `ui/state_library.py:41-43,112-133`; `ui/state.py:579-582,919-922`. |
| R1-L-MISSING | S09 `Enter otwórz plik · F folder` na brakującym pliku | R1 | `identity is None` jest już znane, lecz stopka nie zmienia się; handler tylko pokazuje niedostępność. `ui/state.py:583-587`; `ui/state_library.py:41-43,121-125`. |
| R1-O-MODAL | S04, S06, S07; `O włącz` / `O wyłącz` | R1 | Status pozostaje, lecz w pytaniu O jedynie kasuje pytanie, w polu Historii wpisuje literę, w propozycji jest ignorowane. `ui/state.py:349-355,370-379,816-833,847-861,1485-1487`. To podpowiedź w statusie, nie segment zwykłej stopki. |
| R2-S | S01–S02 `D lub / dodaj` / `dodaj pierwszą` | R2 | Dwa jawne skróty do tej samej wyszukiwarki; jeden segment stopki. `ui/state_subscriptions.py:42,80-88`; `ui/state.py:468-471`. |
| R3-MORE | wszystkie listy panelu z `? więcej` | R3 | Potwierdzony przykład właściciela: nie nazywa pomocy/szczegółów, a działanie zależy od zakładki. Literal `ui/actions.py:25`; dispatch `ui/state.py:742-745,755-759`. |
| R3-WAIT | G `czeka {N}` | R3 | Potwierdzony przykład właściciela: liczba materiałów `material_counts.waiting`, bez przyczyny/obiektu oczekiwania w samym członie. `ui/state.py:132-136,1480-1487`. |
| R3-SHADOW | S01/S02 `Tryb cienia — subskrypcje tylko zapisują propozycje` | R3 | Termin „tryb cienia” pozostaje techniczny; zdanie nie wskazuje, gdzie zobaczyć zapisane propozycje. `ui/state_subscriptions.py:39,91-95`. |
| R3-FINALIZATION | S03 `Finalizacja` | R3 | Etykieta pojawia się właśnie dla `FINALIZATION_FAILED`, więc brzmi jak trwający normalnie etap zamiast jego niepowodzenia. `ui/state_processing.py:163-164`. |
| R3-ATTENTION | S03 `Wymaga uwagi` | R3 | Wiersz mówi jedynie, że `item.problem` jest niepuste; nie podaje w tej etykiecie konkretnej przyczyny ani czynności. `ui/state_processing.py:167-168`. |
| R3-METADATA | S03 `Metadane` | R3 | Techniczna nazwa obejmuje zarówno faktyczne pobieranie metadanych, jak i `pending_send` przed potwierdzeniem wysyłki. `ui/state_processing.py:176-177`. |

## Ustawienia, Ręczny, Home i wykonanie — inwentarz

### Wspólne mechanizmy myszy i kopiowania

Źródła: `ui/app.py:289–327`, `ui/app.py:367–465`, `ui/pointer.py:145–184`, `ui/pointer.py:216–240`.

- Klik w oznaczony wiersz ustawia kursor, nie uruchamia akcji.
- Drugi szybki klik w ten sam wiersz ekranu, ponownie rozpoznany jako wiersz listy, wysyła Enter. Nie wykonuje ponownego wyboru wiersza.
- Prawy przycisk na `MOUSE_DOWN` wysyła Esc.
- Przeciągnięcie zaznacza dostępny tekst ramki.
- Ctrl+C lub Ctrl+Insert przy zaznaczeniu tekstu ramki kopiuje je przed obsługą klawisza przez ekran.
- Klik pola tekstowego ustawia pozycję kursora. Nie zatwierdza wartości.
- Potwierdzenia Ustawień mają `mark_row(..., opens=False)`: podwójny klik nie zatwierdza — `ui/settings.py:1815`.
- Zwykłe listy Ustawień: kółko przesuwa widok o trzy pozycje bez zmiany kursora — `ui/settings.py:564–576`.
- Listowe edytory Ustawień: kółko zmienia kursor opcji o trzy pozycje — `ui/settings.py:566–570`.
- Home i Ręczny nie obsługują kółka jako przewijania. `_handle_scroll` obsługuje State, Message, Auto oraz Settings, ale nie Home/Manual — `ui/app.py:446–465`.
- Auto i Message: kółko przesuwa widok o trzy wiersze — `ui/app.py:455–460`.

Podpowiedzi stopki nie są klikalnymi przyciskami. `with_footer` buduje tekst podpowiedzi przez `mark_inert`, bez tagów akcji — `ui/menu.py:141–150`. To dotyczy wszystkich tekstowych stopek opisanych poniżej. Klikalny wiersz `Cofnij`, `Wróć`, `Zapisz` lub `Anuluj` w treści jest innym elementem niż podpowiedź stopki. Samo `mark_inert` zachowuje istniejące cele; tutaj o nieklikalności świadczy brak nadanych tagów akcji.

### Wspólny najniższy wiersz aplikacji

Źródła: `ui/app.py:990–994`, `ui/app.py:1172–1180`, `ui/prompts.py:536–545`, `ui/home.py:214–225`.

Na każdym ekranie aplikacja dodaje ostatni wiersz:

- z lewej: etykieta bieżącego katalogu procesu, zwykle `~\…`;
- z prawej: `v{version}`;
- przy małej szerokości tekst jest skracany od lewej;
- po kopiowaniu etykietę katalogu zastępuje `Skopiowano zaznaczenie` albo `Nie udało się skopiować` — `FrameSelection.copy`, `ui/pointer.py:240`;
- gdy uruchomiono odliczanie końca partii, wygrywa `Okno zamknie się za {seconds} s · dowolny klawisz zamyka` — `_BATCH_CLOSING`, `ui/app.py:98`; `_closing_label`, `ui/app.py:1012–1014`.

Nie jest to linia statusu automatu. Status automatu należy do `StateController`.

### U — słownik stopek Ustawień

| ID | Dokładny tekst | Źródło |
|---|---|---|
| U-menu | `↑↓/Tab · ←→ · Enter · Esc` | `_MENU_HINT`, `ui/settings.py:52` |
| U-output | `↑↓ · Enter/Space zmień · Esc wróć` | `_MULTI_HINT`, `ui/settings.py:55` |
| U-multi | `↑↓ · Space zmień · Esc wróć` | `_MULTI_SELECT_HINT`, `ui/settings.py:58` |
| U-select | `↑↓/Tab · Enter/→ wybierz · Esc/← cofnij` | `_SELECT_HINT`, `ui/settings.py:61` |
| U-secret | `Enter zatwierdź · Esc anuluj` | `_SECRET_HINT`, `ui/settings.py:64` |
| U-input | `←→ kursor · Enter/Esc wróć · zapis automatyczny` | `_INPUT_HINT`, `ui/settings.py:67` |
| U-voice | `alias \| nazwa \| ID głosu · Enter zatwierdź · puste usuwa · Esc wróć` | `_VOICE_HINT`, `ui/settings.py:70` |
| U-model-id | `ID modelu · Enter zatwierdź · Esc anuluj` | `_render_editor`, `ui/settings.py:1831–1832` |

Wybór stopki: `ui/settings.py:1824–1833`. Stopka menu recepty może mieć dodatkową linię opisową — ekrany U08–U10.

### U-NAV — wspólna nawigacja Ustawień

- ↑ / Shift+Tab: poprzedni wiersz, z zawijaniem;
- ↓ / Tab: następny wiersz, z zawijaniem;
- PgUp/PgDn: skok o `max(visible_count−1, 1)`, bez zawijania;
- Home/End: pierwszy/ostatni wiersz;
- Enter: aktywacja wiersza;
- →: aktywacja wiersza, chyba że pole obsługuje bezpośrednią zmianę wartości;
- ←: krok wstecz, chyba że pole obsługuje bezpośrednią zmianę wartości;
- Esc, Backspace, niezaznaczony Ctrl+C: krok wstecz;
- klik/podwójny klik/prawy przycisk: wspólny mechanizm myszy opisany wyżej;
- kółko: przewijanie widoku bez zmiany kursora.

Źródła: `ui/settings.py:532–562`, `ui/settings.py:798–825`, `ui/settings.py:913–926`, `ui/settings.py:1010–1046`.

Bezpośrednia zmiana ←→:

- bool: odwrócenie wartości;
- wybór skalarny: poprzednia/następna dopuszczalna wartość, bez zawijania;
- liczba: zmiana krokiem z katalogu i geometrii zakresu;
- kolekcja lub dowolny tekst: brak takiej zmiany; → otwiera edytor, ← cofa.

Źródła: `ui/settings.py:729–760`, `ui/settings.py:2067–2146`.

Zmiana czeka zwykle 0,4 s na zapis; inny niedeferrujący klawisz może wymusić zapis wcześniej. Błąd zapisu może zatrzymać nawigację — `ui/settings.py:125`, `ui/settings.py:542–551`, `ui/settings.py:637–668`.

### U-BOTTOM — wspólny dół Ustawień

1. Wiersze `Przywróć domyślne` i `Cofnij`, jeśli dany poziom je ma.
2. `Cofnij` jest wydzielone poza przewijane pozycje menu — `ui/settings.py:1655–1656`, `ui/settings.py:1708–1718`.
3. Zawsze rezerwowany wiersz informacji/błędu, również pusty.
4. Podpowiedź klawiszy.
5. Najniższa linia katalogu/wersji opisana wyżej.

Źródła: `_STATUS_ROWS`, `ui/settings.py:86`; `_finish`, `ui/settings.py:1835–1839`; `_append_feedback`, `ui/settings.py:1841–1856`.

Nie ma osobnego wiersza pełnej nazwy ani odkrywania uciętej wartości. Menu skraca etykietę i wartość — `ui/settings.py:1691–1702`.

Znaczniki przewijania:

- `↑ więcej` — są pozycje ponad oknem;
- `↓ więcej` — są pozycje pod oknem.

Źródła: `ui/settings.py:1680–1682`, `ui/settings.py:1705–1707`; odpowiedniki w Wyniku `ui/settings.py:1750–1763` i edytorach `ui/settings.py:1797–1819`.

### U-MSG — pełny słownik komunikatów Ustawień

Nie każdy tekst występuje na każdym ekranie; warunek jest podany w tabeli.

| Dokładny tekst | Symbol i źródło | Kiedy i co oznacza |
|---|---|---|
| `✗ Nie udało się zapisać ustawienia` | `_commit_pending`, `ui/settings.py:658`; `_submit_editor`, `ui/settings.py:1491` | Błąd aplikacji/I/O podczas zapisu. Przy opóźnionej zmianie zachowuje zmianę do ponowienia. |
| `✗ Nieprawidłowa wartość` | `_validation_message`, `ui/settings.py:1549–1556` | Odrzucono typ/format albo nie można odczytać specyfikacji; nie podaje szczegółowej przyczyny. |
| `✗ Nieprawidłowa wartość · Zakres: {min}–{max}` | `_validation_message`, `ui/settings.py:1554–1555` | Walidacja pola mającego obie granice. |
| `✗ Wpisz jedną linię bez znaków sterujących` | `_handle_text_key`, `ui/settings.py:877–883` | Wpisany/wklejony pakiet tekstu zawiera znak niedrukowalny. |
| `✗ Nie można wczytać ustawień` | `_refresh_menu`, `ui/settings.py:1060–1064` | Budowa menu zawiodła; zostaje tylko `Cofnij`. |
| `✗ Nie można wczytać recepty właściciela` | `_enter_recipe`, `ui/settings.py:998–1004` | Nie udał się odczyt recepty Tłumaczenie/Audiobook albo nie ma sesji rezydenta. |
| `✗ Nie można wczytać ustawień wyniku` | `_load_output`, `ui/settings.py:1558–1564` | Nie udał się odczyt presetu; zbiór wyświetlanych produktów staje się pusty. |
| `✗ Nie udało się zapisać ustawień wyniku` | `_save_output`, `ui/settings.py:1567–1573` | Zapis zaznaczeń Wyniku zawiódł; przywracane są wcześniejsze zaznaczenia. |
| `✗ Wybierz co najmniej jeden wynik` | `_toggle_output_product`, `ui/settings.py:855–858` | Próba wyłączenia ostatniego produktu w kategorii Wynik. |
| `Palantir · katalog niedostępny` | `_palantir_model_label`, `ui/settings.py:1225–1229` | Nie udało się odczytać katalogu do prezentacji bieżącego modelu. |
| `✗ Nie można wczytać modeli · Sprawdź Połączenia i katalog Palantir` | `_open_model_editor`, `ui/settings.py:1310–1316` | Pobranie listy modeli z fasady zakończyło się błędem aplikacji. |
| `✗ Brak modeli · Najpierw skonfiguruj dostawcę w Połączeniach` | `_open_model_editor`, `ui/settings.py:1327–1331` | Nie ma żadnych opcji modelu ani dostępnej ścieżki własnego modelu. |
| `✗ Najpierw skonfiguruj dostawcę w Połączeniach` | `_open_custom_model_provider_editor`, `ui/settings.py:1350–1354` | Lista dostępnych dostawców własnego modelu jest pusta. |
| `✗ Preferencje przywrócone; recepty: błąd · Enter ponawia` | `_ROOT_RESET_PARTIAL`, `ui/settings.py:119`; `_reset_scope`, `ui/settings.py:1397–1404` | Reset preferencji już się wykonał, ale dalszy reset presetu/recept zawiódł. |
| `Zapisano · nie przeładowano · Enter ponawia` | `_reload_owner_settings`, `ui/settings.py:1591–1599` | Zapis lokalny się udał, przeładowanie ustawień w rezydencie nie. |
| `Zapisano. Ctrl+C ponownie: wróć bez przeładowania` | `handle_key`, `ui/settings.py:546–547` | Pierwszy Ctrl+C po nieudanym przeładowaniu uzbraja wyjście bez niego. |
| `Nie zapisano zmiany. Ctrl+C ponownie: porzuć i wróć; inny klawisz: zostań` | `handle_key`, `ui/settings.py:548` | Pierwszy Ctrl+C po błędzie zapisu uzbraja porzucenie oczekującej zmiany. |
| `Ctrl+C: porzuć · inny klawisz: zostań` | `_append_feedback`, `ui/settings.py:1850` | Skrót powyższego ostrzeżenia, gdy pełny tekst nie mieści się. |
| `Ctrl+C: porzuć zmianę` | `_append_feedback`, `ui/settings.py:1851` | Jeszcze krótszy wariant ostrzeżenia. |
| `Zapisano · Ctrl+C: wróć` | `_append_feedback`, `ui/settings.py:1852–1853` | Krótki wariant ostrzeżenia o nieprzeładowanym, ale zapisanym ustawieniu. |
| `✗ Nie można wczytać katalogu modeli` | `_start_probe`, `ui/settings.py:1613–1618` | Nie można przygotować testu Palantira. |
| `✗ Najpierw wybierz model tłumaczenia` | `_start_probe`, `ui/settings.py:1619–1621` | Bieżący identyfikator modelu nie występuje w katalogu testowanym przez Palantira. |
| `Testowanie połączenia…` | `_start_probe`, `ui/settings.py:1625–1626` | Trwa jawnie uruchomiony probe. |
| `✓ Połączenie działa` | `_run_probe`, `ui/settings.py:1645–1647` | Probe zwrócił `VERIFIED`. |
| `✗ Test połączenia nie powiódł się` | `_run_probe`, `ui/settings.py:1635–1647` | Probe nie potwierdził działania albo zakończył się obsługiwanym wyjątkiem. |
| `Anulowano` | `_handle_busy_key`, `ui/settings.py:789–796` | Odrzucono oczekiwanie na wynik testu; późny wynik tej generacji jest ignorowany. |

Sukces zwykłego zapisu i resetu jest cichy. `_submit_editor` zamyka edytor i czyści feedback — `ui/settings.py:1496–1499`.

### U — wspólne wartości i etykiety

| Tekst | Źródło | Znaczenie |
|---|---|---|
| `Cofnij` | `_BACK_LABEL`, `ui/settings.py:101` | Przejście o poziom wyżej. |
| `Przywróć domyślne` | `_RESET_LABEL`, `ui/settings.py:104` | Otwarcie potwierdzenia resetu. |
| `domyślnie` | `_format_value`, `ui/settings.py:1957–1960` | `None`, a dla `translation_batch_size` także zero. |
| `tak`, `nie` | `_format_value`, `ui/settings.py:1961–1962` | Bieżąca wartość logiczna. |
| `Tak`, `Nie` | `_open_setting_editor`, `ui/settings.py:1241`; potwierdzenia `ui/settings.py:1382,1468` | Opcje boola albo potwierdzenia. |
| `brak` | `_format_collection`, `ui/settings.py:1981–1984`; `_connection_address`, `ui/settings.py:1204–1208`; `_connection_status`, `ui/settings.py:2017–2020` | Pusta kolekcja, pusty adres albo nieskonfigurowany sekret — zależnie od miejsca. |
| `skonfigurowane` | `_connection_status`, `ui/settings.py:2020` | Sekret istnieje, bez potwierdzenia działania połączenia. |
| `skonfigurowane · system` | `_connection_status`, `ui/settings.py:2020` | Sekret jest nadpisywany konfiguracją środowiska systemowego. |

## U01 — Ustawienia: poziom główny

### Klawisze i mysz

U-NAV. Enter/→ otwiera kategorię, reset lub powrót. Esc/Backspace/Ctrl+C/← opuszcza Ustawienia do kontekstu wejścia: Home albo Panel — `ui/settings.py:1046`, `ui/app.py:500–509`, `ui/app.py:887–903`.

### Stopka

U-menu: `↑↓/Tab · ←→ · Enter · Esc` — `ui/settings.py:52`, `ui/settings.py:1720–1723`. Nieklikalna.

### Dół poza stopką

U-BOTTOM: przewijany reset, przypięte `Cofnij`, stały slot feedbacku, katalog/wersja.

### Komunikaty

Nagłówek `USTAWIENIA` — `_menu_title`, `ui/settings.py:2027`. Pozycje `_ROOT_ITEMS`, `ui/settings.py:151–162`: `Ogólne`, `Napisy`, `Tłumaczenie`, `Lektor`, `Wynik`, `Auto`, `Pobieranie`, `Połączenia`, `Przywróć domyślne`, `Cofnij`. U-MSG dla nieudanego zapisu/resetu.

### Naruszenia

N01/R2: `↑↓/Tab` pokazuje alternatywne klawisze tej samej nawigacji. N02/R3: `←→`, `Enter`, `Esc` nie mają opisu znaczenia; `←→` w różnych wierszach może oznaczać zmianę wartości albo wejście/powrót.

## U02 — Ustawienia → Ogólne

### Klawisze i mysz

U-NAV; ←→ zmienia kolejność przetwarzania i jakość obrazu. Na listach języków → otwiera edytor tekstowej listy, ← cofa — `ui/settings.py:729–760`.

### Stopka

U-menu — `ui/settings.py:52`, `ui/settings.py:1720`.

### Dół poza stopką

U-BOTTOM, reset zakresu `general`.

### Komunikaty

`OGÓLNE` — `ui/settings.py:2028`. `_GENERAL_FIELDS`, `ui/settings.py:168–173`:

- `PRZETWARZANIE`: `Kolejność przetwarzania`;
- `JĘZYKI`: `Priorytet języków audio`, `Priorytet języków napisów`;
- `WYNIK`: `Jakość obrazu`.

Opcje kolejności: `Najpierw gotowe`, `Ścisła kolejność plików` — `ui/settings.py:301–302`. Jakość: `Wysoka`, `Zrównoważona`, `Kompaktowa` — `ui/settings.py:303–305`. Edytory wymieniono w wykazie instancji poniżej. Pozostałe komunikaty U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U03 — Ustawienia → Napisy

### Klawisze i mysz

U-NAV; ←→ zmienia liczbę, Enter otwiera jej edytor tekstowy.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

U-BOTTOM, reset `subtitles`.

### Komunikaty

`NAPISY` — `ui/settings.py:2030`; `UKŁAD TEKSTU`, `Znaków w linii`, `Linii na napis` — `_SUBTITLE_FIELDS`, `ui/settings.py:176–179`. Walidacja liczby: U-MSG. Zakresy: 20–120 i 1–4 — `anishift/config/user_settings.py:96–100`.

### Naruszenia

N01/R2 i N02/R3.

## U04 — Ustawienia → Tłumaczenie

### Klawisze i mysz

U-NAV. Enter na `Model tłumaczenia` otwiera osobny picker; wiersz istnieje tylko dla silnika `llm` — `ui/settings.py:1101–1113`.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

U-BOTTOM, reset `translation`.

### Komunikaty

`TŁUMACZENIE` — `ui/settings.py:2031`. Pełne sekcje i etykiety — `_TRANSLATION_FIELDS`, `ui/settings.py:192–203`:

- `PODSTAWOWE`: `Silnik tłumaczenia`, warunkowo `Model tłumaczenia`;
- `WYDAJNOŚĆ`: `Znaków na fragment TXT`, `Linii na zapytanie`, `Plików jednocześnie (Google/DeepL)`, `Plików jednocześnie (LLM)`, `Ponowień po błędzie tłumaczenia`;
- `MODEL LLM`: `Temperatura`, `Top-p`, `Limit tokenów odpowiedzi`;
- `PROMPT`: `Styl`.

`Model tłumaczenia`, temperatura, top-p, tokeny, styl i współbieżność LLM są warunkowane `translation_engine == "llm"` — `anishift/config/field_catalog.py:710,788–865`. Pole `Plików jednocześnie (Google/DeepL)` nie ma warunku ukrywającego dla LLM — `anishift/config/field_catalog.py:766–775`.

Etykiety silników: `Google`, `DeepL`, `LLM` — `_ENGINE_LABELS`, `ui/settings.py:330–345`. Bieżący model: `{dostawca} · {model_id}` albo `Palantir · {label/alias}` — `ui/settings.py:1215–1233`. U-MSG obejmuje błędy modeli.

### Naruszenia

N01/R2, N02/R3. N03/R3: `Top-p`, `Temperatura`, `PROMPT`, `Limit tokenów odpowiedzi` nie mają na tym ekranie wyjaśnienia wpływu na wynik; renderer pokazuje etykietę i wartość, nie `SettingSpec.description` — `ui/settings.py:1691–1702`.

## U05 — Ustawienia → Lektor

### Klawisze i mysz

U-NAV. `Własne głosy` otwiera oddzielny poziom listy. Pozostałe pola: wybór, bool, liczba lub tekst zgodnie z wykazem instancji.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

U-BOTTOM, reset `tts`.

### Komunikaty

`LEKTOR` — `ui/settings.py:2032`. Wszystkie etykiety `_TTS_FIELDS`, `ui/settings.py:212–235`:

- `PODSTAWOWE`: `Silnik`, `Model / endpoint`, `Głos`, `Własne głosy`;
- `WYDAJNOŚĆ`: `Syntez jednocześnie`, `Ponowień po błędzie syntezy głosu`, `VPN ElevenBytes`;
- `GŁOS`: `Tempo końcowe`, `Korekta głośności głosu`, `Tempo natywne`, `Głośność natywna`, `Wysokość głosu`, `Stabilność`, `Podobieństwo`, `Ekspresja`, `Wzmocnienie mówcy`, `Prędkość natywna`;
- `DŹWIĘK`: `Format natywny`, `Kodek lektora`, `Bitrate lektora`, `Głośność lektora`, `Głośność oryginału`.

Warunki:

- własne głosy i VPN: ElevenBytes;
- współbieżność syntez: poza SAPI;
- natywne tempo/głośność: Edge albo SAPI; wysokość: Edge;
- stabilność/podobieństwo/ekspresja/wzmocnienie: ElevenBytes `run7` lub ElevenLabs;
- natywna prędkość i format: ElevenLabs;
- bitrate: kodek `aac`, `eac3`, `mp3` albo `opus`.

Źródła: `anishift/config/field_catalog.py:903–989,1019–1050,1053–1230,1246–1254`.

### Naruszenia

N01/R2, N02/R3. N04/R3: ekran nie wyjaśnia różnicy `Tempo końcowe`/`Tempo natywne`/`Prędkość natywna` ani trzech korekt głośności; pokazuje tylko etykiety i wartości — `ui/settings.py:220–234,1691–1702`.

## U06 — Ustawienia → Wynik

### Klawisze i mysz

Nawigacja jak U-NAV, lecz:

- Enter lub Space na produkcie przełącza zaznaczenie;
- ostatniego produktu nie wolno wyłączyć;
- Enter na resecie otwiera potwierdzenie, na `Cofnij` wraca;
- Space na resecie/`Cofnij` nic nie robi;
- ← wraca; → nic nie robi.

Źródło: `ui/settings.py:827–861`. Klik wskazuje produkt; podwójny klik działa jak Enter. Kółko przewija.

### Stopka

U-output: `↑↓ · Enter/Space zmień · Esc wróć` — `ui/settings.py:55,1777`.

### Dół poza stopką

U-BOTTOM; zaznaczenia `●/○`. Reset i `Cofnij` są odrębnymi wierszami — `ui/settings.py:1725–1777`.

### Komunikaty

`WYNIK` — `ui/settings.py:1748`. Produkty `_PRODUCTS`, `ui/settings.py:288–296`: `Polskie napisy`, `Polski lektor`, `MKV`, `MP4`, `Napisy źródłowe`, `Polskie dialogi`, `Polskie napisy ekranowe`.

Błędy odczytu/zapisu i `✗ Wybierz co najmniej jeden wynik`: U-MSG.

### Naruszenia

N05/R1: `Enter/Space zmień` pozostaje na resecie i `Cofnij`, gdzie Space nie działa, oraz na jedynym zaznaczonym produkcie, którego nie można odznaczyć. N06/R2: `Enter/Space` dubluje zmianę produktu. N07/R3: reset opisany zakresem `WYNIK` przywraca cały preset, również polityki Auto, nie tylko widoczne produkty — `ui/settings.py:1409–1413,1423–1432`.

## U07 — Ustawienia → Auto: lista recept

### Klawisze i mysz

U-NAV. Enter/→ otwiera `Wideo`, `Tłumaczenie`, `Audiobook`, reset albo powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

U-BOTTOM; na tym poziomie brak opisu dziedziczenia pod listą.

### Komunikaty

`AUTO` — `ui/settings.py:2035`. `Wideo`, `Tłumaczenie`, `Audiobook` — `_RECIPE_LABELS`, `ui/settings.py:263`. Lista i reset: `ui/settings.py:1085–1093`. Błąd `✗ Nie można wczytać recepty właściciela`: U-MSG.

### Naruszenia

N01/R2 i N02/R3. N08/R3: komunikat `recepty właściciela` opisuje wewnętrzny podział odpowiedzialności, bez wskazania zwykłemu użytkownikowi, gdzie leży problem — `ui/settings.py:1003`.

## U08 — Ustawienia → Auto → Wideo

### Klawisze i mysz

U-NAV; pola otwierają edytory z wykazu instancji. Pola MKV/MP4 pojawiają się dopiero przy odpowiednim produkcie.

### Stopka

U-menu; przy wysokości co najmniej 12 wierszy poprzedza go `subs: wideo + obowiązkowe napisy obok` — `_RECIPE_DESCRIPTIONS`, `ui/settings.py:267`; `_render_menu`, `ui/settings.py:1721–1723`.

### Dół poza stopką

U-BOTTOM; opis `subs` jest elementem przekazanego bloku stopki, a nie komunikatem operacji.

### Komunikaty

`AUTO · WIDEO` — `ui/settings.py:1653–1654`. `_AUTO_FIELDS`, `ui/settings.py:238–247`:

- `WYNIK`: `Produkty wideo`;
- `ŹRÓDŁO NAPISÓW`: `Źródło napisów`, `Język źródła`;
- `TŁUMACZENIE I FORMAT`: `Tłumaczenie`, `Format napisów`;
- `KONTENERY`: `Ścieżki MKV`, `Dźwięk MP4`, `Napisy wypalone w MP4`.

Opcje:

- źródło: `Automatycznie`, `Plik obok źródła`, `Osadzone w MKV`, `Bez napisów` — `ui/settings.py:306–309`;
- tłumaczenie: `Automatycznie · tłumaczy, gdy źródło nie jest polskie`, `Zawsze tłumacz · także polskie źródło`, `Nie tłumacz · produkty PL wymagają polskiego źródła` — `ui/settings.py:310–312`;
- format: `Jak źródło`, `ASS`, `SRT` — `ui/settings.py:313–315`;
- wypalanie: `Brak`, `Napisy źródłowe`, `Polskie napisy`, `Polskie napisy ekranowe` — `ui/settings.py:316–319`;
- MKV: `Napisy źródłowe`, `Polskie napisy`, `Polskie napisy ekranowe`, `Polski lektor` — `ui/settings.py:320–323`;
- MP4 audio: `Automatycznie`, `Oryginalne audio`, `Polski lektor` — `ui/settings.py:324–326`.

### Naruszenia

N01/R2 i N02/R3. N09/R3: `subs:` nie objaśnia, że chodzi o nazwę katalogu/dziedziczenie trasy; analogicznie `cover:` w U10 — `ui/settings.py:266–270`.

## U09 — Ustawienia → Auto → Tłumaczenie

### Klawisze i mysz

U-NAV; dwa pola wyboru: wynik TXT i sposób tłumaczenia.

### Stopka

U-menu; od 12 wierszy dodatkowo `TXT/SRT/ASS/SSA → bez głosu` — `ui/settings.py:268,1721–1723`.

### Dół poza stopką

U-BOTTOM; reset tylko recepty `translate`.

### Komunikaty

`AUTO · TŁUMACZENIE` — `ui/settings.py:1654`. `TEKST I NAPISY`, `Wynik TXT`, `Tłumaczenie` — `ui/settings.py:252–255`.

- `TXT · zachowaj akapity`;
- `SRT · czasy robocze, bez synchronizacji`;
- `Automatycznie`, `Zawsze tłumacz`, `Nie tłumacz`.

Źródło: `_choice_label`, `ui/settings.py:1935–1938`. U-MSG.

### Naruszenia

N01/R2, N02/R3, ewentualny komunikat N08/R3. Nie stwierdzono odrębnego R1.

## U10 — Ustawienia → Auto → Audiobook

### Klawisze i mysz

U-NAV; pola `Tłumaczenie` i `Czytanie SRT`.

### Stopka

U-menu; od 12 wierszy dodatkowo `cover: audiobook + obraz → MP4` — `ui/settings.py:269,1721–1723`.

### Dół poza stopką

U-BOTTOM; reset recepty `audiobook`.

### Komunikaty

`AUTO · AUDIOBOOK` — `ui/settings.py:1654`. `SAMODZIELNE AUDIO`, `Tłumaczenie`, `Czytanie SRT` — `ui/settings.py:256–259`.

- `Automatycznie`, `Zawsze tłumacz`, `Nie tłumacz`;
- `Ciągłe · przerwy 0,3 s`;
- `Zachowaj czasy SRT`.

Źródło: `_choice_label`, `ui/settings.py:1935–1940`. U-MSG.

### Naruszenia

N01/R2, N02/R3, N09/R3; przy błędzie odczytu także N08/R3.

## U11 — Ustawienia → Pobieranie

### Klawisze i mysz

U-NAV. Strzałki poziome przełączają źródło albo zmieniają godziny czekania; Enter otwiera bool/listę albo edytor liczby.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

U-BOTTOM; reset `download`.

### Komunikaty

`POBIERANIE` — `ui/settings.py:2029`. `_DOWNLOAD_FIELDS`, `ui/settings.py:182–189`:

- `ŹRÓDŁA WYDAŃ`: `TsukiHime`, `Torrentio`, `Nyaa`, `Knaben`, `nekoBT`;
- `SUBSKRYPCJE`: `Czekanie na polskie napisy (h)`.

Zakres czekania: 0–48 — `anishift/config/field_catalog.py:413–421`. Bool `tak/nie`, opcje `Tak/Nie`, U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U12 — Ustawienia → Połączenia: lista dostawców

### Klawisze i mysz

U-NAV; Enter/→ otwiera konkretnego dostawcę.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

Przypięte `Cofnij` i slot feedbacku. Nie ma resetu — `ui/settings.py:1182–1192`.

### Komunikaty

`POŁĄCZENIA` — `ui/settings.py:2033`. Dziesięć pozycji `_CONNECTIONS`, `ui/settings.py:475–496`, opisanych osobno U13–U22. Każda pokazuje `brak`, `skonfigurowane` albo `skonfigurowane · system` — wspólny słownik wartości U. Stan nie jest wynikiem testu połączenia.

### Naruszenia

N01/R2 i N02/R3. N10/R3: `skonfigurowane · system` nie wyjaśnia na ekranie, że chodzi o nadpisanie przez zmienną środowiskową — `ui/settings.py:2017–2020`.

## U13 — Połączenia → Palantir Foundry

### Klawisze i mysz

U-NAV. Osobne akcje sekretu, adresu, usunięcia i probe. Test używa bieżącego aliasu modelu tłumaczenia — `ui/settings.py:1612–1621`.

### Stopka

U-menu, także podczas probe — `ui/settings.py:1720`.

### Dół poza stopką

`Cofnij`, slot feedbacku; brak resetu.

### Komunikaty

Nagłówek `PALANTIR FOUNDRY` — `_menu_title`, `ui/settings.py:2024–2025`. `Ustaw / zmień klucz`, `Adres`, `Usuń klucz`, `Testuj połączenie`, `Cofnij` — `ui/settings.py:1194–1202`. Adres jest wartością `palantir_enrollment_base_url`; sekret `palantir_token` — `ui/settings.py:476`. Wszystkie komunikaty probe z U-MSG.

### Naruszenia

N01/R2, N02/R3; podczas testu N11/R1 opisane w E16.

## U14 — Połączenia → Palantir Foundry · konto 2

### Klawisze i mysz

U-NAV. Ustawienie sekretu, adresu i usunięcie sekretu. Brak akcji testu.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak resetu.

### Komunikaty

`PALANTIR FOUNDRY · KONTO 2`; `Ustaw / zmień klucz`, `Adres`, `Usuń klucz`, `Cofnij` — `ui/settings.py:477–482,1194–1202,2024–2025`. Sekret `palantir_secondary_token`, adres `palantir_fallback_enrollment_base_url`. U-MSG.

### Naruszenia

N01/R2 i N02/R3. Nie stwierdzono osobnego R1.

## U15 — Połączenia → Gemini

### Klawisze i mysz

U-NAV; edycja `gemini_api_key`, usunięcie przez CONFIRM, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak adresu, resetu i probe.

### Komunikaty

`GEMINI`; `Ustaw / zmień klucz`, `Usuń klucz`, `Cofnij` — `ui/settings.py:483,1194–1202,2024–2025`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U16 — Połączenia → OpenAI

### Klawisze i mysz

U-NAV; edycja `openai_api_key`, usunięcie przez CONFIRM, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak adresu, resetu i probe.

### Komunikaty

`OPENAI`; `Ustaw / zmień klucz`, `Usuń klucz`, `Cofnij` — `ui/settings.py:484,1194–1202,2024–2025`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U17 — Połączenia → Anthropic

### Klawisze i mysz

U-NAV; edycja `anthropic_api_key`, usunięcie przez CONFIRM, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak adresu, resetu i probe.

### Komunikaty

`ANTHROPIC`; `Ustaw / zmień klucz`, `Usuń klucz`, `Cofnij` — `ui/settings.py:485,1194–1202,2024–2025`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U18 — Połączenia → DeepSeek

### Klawisze i mysz

U-NAV; edycja `deepseek_api_key`, usunięcie przez CONFIRM, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak adresu, resetu i probe.

### Komunikaty

`DEEPSEEK`; `Ustaw / zmień klucz`, `Usuń klucz`, `Cofnij` — `ui/settings.py:486,1194–1202,2024–2025`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U19 — Połączenia → OpenRouter

### Klawisze i mysz

U-NAV; edycja `openrouter_api_key`, usunięcie przez CONFIRM, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak adresu, resetu i probe.

### Komunikaty

`OPENROUTER`; `Ustaw / zmień klucz`, `Usuń klucz`, `Cofnij` — `ui/settings.py:487,1194–1202,2024–2025`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U20 — Połączenia → OpenAI-compatible

### Klawisze i mysz

U-NAV; edycja sekretu, edycja adresu, usunięcie sekretu, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak resetu i probe.

### Komunikaty

`OPENAI-COMPATIBLE`; `Ustaw / zmień klucz`, `Adres`, `Usuń klucz`, `Cofnij` — `ui/settings.py:488–493,1194–1202,2024–2025`. Sekret `openai_compatible_api_key`; adres `openai_compatible_base_url`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U21 — Połączenia → DeepL

### Klawisze i mysz

U-NAV; edycja `deepl_api_key`, usunięcie przez CONFIRM, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak adresu, resetu i probe.

### Komunikaty

`DEEPL`; `Ustaw / zmień klucz`, `Usuń klucz`, `Cofnij` — `ui/settings.py:494,1194–1202,2024–2025`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U22 — Połączenia → ElevenLabs

### Klawisze i mysz

U-NAV; edycja `elevenlabs_api_key`, usunięcie przez CONFIRM, powrót.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Cofnij`, feedback; brak adresu, resetu i probe.

### Komunikaty

`ELEVENLABS`; `Ustaw / zmień klucz`, `Usuń klucz`, `Cofnij` — `ui/settings.py:495,1194–1202,2024–2025`. U-MSG.

### Naruszenia

N01/R2 i N02/R3.

## U23 — Lektor → Własne głosy: lista

### Klawisze i mysz

U-NAV. Enter/→ na głosie otwiera jego edycję; na `Dodaj głos` otwiera pusty edytor. Dostęp przez Lektor przy ElevenBytes.

### Stopka

U-menu — `ui/settings.py:52`.

### Dół poza stopką

`Przywróć domyślne`, `Cofnij`, slot feedbacku. Reset tej listy usuwa wszystkie własne głosy — `ui/settings.py:1406–1408`.

### Komunikaty

`WŁASNE GŁOSY` — `_VOICES_TITLE`, `ui/settings.py:76`, oraz sekcja `ui/settings.py:1157`. `Dodaj głos` — `_ADD_VOICE_LABEL`, `ui/settings.py:82`. Wiersz głosu: `{voice.label} · {voice.voice_id}` — `ui/settings.py:1155–1163`. Brak osobnego komunikatu pustej listy; pozostają akcje dodania/resetu/powrotu.

### Naruszenia

N01/R2 i N02/R3.

## Ustawienia — wykaz każdej instancji edytora

Nagłówek zwykłego edytora jest nazwą pola pisaną wielkimi literami, a nie identyfikatorem technicznym — `_field_title`, `ui/settings.py:1919–1931`. Poniższa tabela wymienia wszystkie zwykłe instancje; pięć części zachowania każdego rodzaju znajduje się w E01–E06. Własne modele, sekrety, adresy, głosy i potwierdzenia mają osobne ekrany E07–E16.

| Poziom → nazwa edytora/pola | Rodzaj | Warunek / wartości | Źródło nazwy |
|---|---|---|---|
| Ogólne → Kolejność przetwarzania | E01 SELECT | `Najpierw gotowe`, `Ścisła kolejność plików` | `ui/settings.py:169,301–302` |
| Ogólne → Priorytet języków audio | E06 lista tekstowa | Kody języków oddzielone przecinkami | `ui/settings.py:170` |
| Ogólne → Priorytet języków napisów | E06 lista tekstowa | Kody języków oddzielone przecinkami | `ui/settings.py:171` |
| Ogólne → Jakość obrazu | E01 SELECT | `Wysoka`, `Zrównoważona`, `Kompaktowa` | `ui/settings.py:172,303–305` |
| Napisy → Znaków w linii | E05 liczba całkowita | 20–120 | `ui/settings.py:177` |
| Napisy → Linii na napis | E05 liczba całkowita | 1–4 | `ui/settings.py:178` |
| Tłumaczenie → Silnik tłumaczenia | E01 SELECT | Zarejestrowane silniki; etykiety Google/DeepL/LLM | `ui/settings.py:193,330–345` |
| Tłumaczenie → Znaków na fragment TXT | E05 liczba całkowita | 200–4000 | `ui/settings.py:194` |
| Tłumaczenie → Linii na zapytanie | E05 liczba całkowita | 0–500; zero pokazuje się jako `domyślnie` w menu | `ui/settings.py:195,92,1957–1960` |
| Tłumaczenie → Plików jednocześnie (Google/DeepL) | E05 liczba całkowita | 1–16 | `ui/settings.py:196` |
| Tłumaczenie → Plików jednocześnie (LLM) | E05 liczba całkowita | LLM; 1–16 | `ui/settings.py:197` |
| Tłumaczenie → Ponowień po błędzie tłumaczenia | E05 liczba całkowita | 0–10 | `ui/settings.py:198` |
| Tłumaczenie → Temperatura | E05 liczba opcjonalna | LLM; 0–2; puste = domyślnie | `ui/settings.py:199` |
| Tłumaczenie → Top-p | E05 liczba opcjonalna | LLM; 0–1; puste = domyślnie | `ui/settings.py:200` |
| Tłumaczenie → Limit tokenów odpowiedzi | E05 liczba całkowita opcjonalna | LLM; 1–32000; puste = domyślnie | `ui/settings.py:201` |
| Tłumaczenie → Styl | E01 SELECT | LLM; nazwy z `available_style_names()`, formatowane przez `_choice_label` | `ui/settings.py:202`; `anishift/config/field_catalog.py:844–853` |
| Lektor → Silnik | E01 SELECT | Zarejestrowane silniki; Microsoft Edge, ElevenBytes, ElevenLabs, Windows SAPI | `ui/settings.py:213,330–345` |
| Lektor → Model / endpoint | E01 SELECT | Lista zależna od silnika | `ui/settings.py:214`; `anishift/config/field_catalog.py:1352–1362` |
| Lektor → Głos | E01 SELECT / E04 tekst | Lista dla Edge/ElevenBytes/SAPI; dowolny identyfikator dla ElevenLabs | `ui/settings.py:215`; `anishift/config/field_catalog.py:1371–1382` |
| Lektor → Syntez jednocześnie | E05 liczba całkowita | Poza SAPI; 1–100, dla VPN ElevenBytes maksimum ogranicza `VPN_MAX_CONCURRENCY` | `ui/settings.py:217`; `anishift/config/field_catalog.py:1019–1034,1365–1368` |
| Lektor → Ponowień po błędzie syntezy głosu | E05 liczba całkowita | 0–10 | `ui/settings.py:218` |
| Lektor → VPN ElevenBytes | E02 bool | ElevenBytes; `Tak`, `Nie` | `ui/settings.py:219` |
| Lektor → Tempo końcowe | E05 liczba | 0,5–2; menu dodaje `×` | `ui/settings.py:220,1964–1971` |
| Lektor → Korekta głośności głosu | E05 liczba | Wartość dB, bez obu granic w specyfikacji | `ui/settings.py:221`; `anishift/config/field_catalog.py:1008–1016` |
| Lektor → Tempo natywne | E04 tekst / E05 liczba | Edge: format ±procent; SAPI: skala wybranego głosu | `ui/settings.py:222`; `anishift/config/field_catalog.py:1056–1065,1193–1217` |
| Lektor → Głośność natywna | E04 tekst / E05 liczba | Edge: format ±procent; SAPI: 0–1 lub 0–100 według głosu | `ui/settings.py:223`; `anishift/config/field_catalog.py:1067–1076,1202–1229` |
| Lektor → Wysokość głosu | E04 tekst | Edge: ±Hz | `ui/settings.py:224`; `anishift/config/field_catalog.py:1078–1087` |
| Lektor → Stabilność | E05 liczba | ElevenBytes run7 / ElevenLabs; 0–1 | `ui/settings.py:225` |
| Lektor → Podobieństwo | E05 liczba | Jak wyżej; 0–1 | `ui/settings.py:226` |
| Lektor → Ekspresja | E05 liczba | Jak wyżej; 0–1 | `ui/settings.py:227` |
| Lektor → Wzmocnienie mówcy | E02 bool | Jak wyżej; `Tak`, `Nie` | `ui/settings.py:228` |
| Lektor → Prędkość natywna | E05 liczba | ElevenLabs; 0,7–1,2 | `ui/settings.py:229` |
| Lektor → Format natywny | E01 SELECT | ElevenLabs; tokeny `OUTPUT_FORMATS` | `ui/settings.py:230` |
| Lektor → Kodek lektora | E01 SELECT | `AudioCodecProfile`, etykieta przez `_choice_label` | `ui/settings.py:231`; `anishift/config/field_catalog.py:1236–1244` |
| Lektor → Bitrate lektora | E04 tekst opcjonalny | Tylko kodek stratny; puste = domyślnie | `ui/settings.py:232` |
| Lektor → Głośność lektora | E05 liczba | dB | `ui/settings.py:233` |
| Lektor → Głośność oryginału | E05 liczba | dB | `ui/settings.py:234` |
| Auto → Wideo → Produkty wideo | E03 MULTI_SELECT | Siedem produktów z U06; nie wolno wyłączyć ostatniego | `ui/settings.py:239,1258–1259,900–903` |
| Auto → Wideo → Źródło napisów | E01 SELECT | Cztery opcje z U08 | `ui/settings.py:240,306–309` |
| Auto → Wideo → Język źródła | E04 tekst opcjonalny | ISO języka; puste = brak wymuszenia | `ui/settings.py:241`; `anishift/config/field_catalog.py:589–597` |
| Auto → Wideo → Tłumaczenie | E01 SELECT | Trzy opisowe opcje z U08 | `ui/settings.py:242,310–312` |
| Auto → Wideo → Format napisów | E01 SELECT | Jak źródło/ASS/SRT | `ui/settings.py:243,313–315` |
| Auto → Wideo → Ścieżki MKV | E03 MULTI_SELECT | Tylko przy produkcie MKV; cztery rodzaje ścieżek z U08 | `ui/settings.py:244,320–323` |
| Auto → Wideo → Dźwięk MP4 | E01 SELECT | Tylko przy MP4; trzy opcje z U08 | `ui/settings.py:245,324–326` |
| Auto → Wideo → Napisy wypalone w MP4 | E01 SELECT | Tylko przy MP4; cztery opcje z U08 | `ui/settings.py:246,316–319` |
| Auto → Tłumaczenie → Wynik TXT | E01 SELECT | Dwie opcje z U09 | `ui/settings.py:253,1937–1938` |
| Auto → Tłumaczenie → Tłumaczenie | E01 SELECT | Automatycznie/Zawsze tłumacz/Nie tłumacz | `ui/settings.py:254,1935–1936` |
| Auto → Audiobook → Tłumaczenie | E01 SELECT | Automatycznie/Zawsze tłumacz/Nie tłumacz | `ui/settings.py:257,1935–1936` |
| Auto → Audiobook → Czytanie SRT | E01 SELECT | Ciągłe · przerwy 0,3 s / Zachowaj czasy SRT | `ui/settings.py:258,1939–1940` |
| Pobieranie → TsukiHime | E02 bool | Tak/Nie | `ui/settings.py:183` |
| Pobieranie → Torrentio | E02 bool | Tak/Nie | `ui/settings.py:184` |
| Pobieranie → Nyaa | E02 bool | Tak/Nie | `ui/settings.py:185` |
| Pobieranie → Knaben | E02 bool | Tak/Nie | `ui/settings.py:186` |
| Pobieranie → nekoBT | E02 bool | Tak/Nie | `ui/settings.py:187` |
| Pobieranie → Czekanie na polskie napisy (h) | E05 liczba całkowita | 0–48 | `ui/settings.py:188` |

Źródło większości zakresów: `anishift/config/user_settings.py:81–120`. Typy edytorów wybiera `_open_setting_editor`, `ui/settings.py:1235–1296`. Pola nieaktywne lub nieobecne w katalogu są pomijane — `ui/settings.py:1131–1142`.

### E-TEXT — wspólna obsługa pola tekstowego

Profil używany w E04–E06, E09–E13 i M09–M11:

- wpisywanie tekstu i wklejanie;
- ←→, Home/End, również Ctrl+Home/End: ruch kursora;
- Ctrl+←→: ruch po słowach;
- warianty z Shift: zaznaczenie;
- Ctrl+A: zaznacz wszystko;
- Backspace/Delete: usuń znak lub zaznaczenie;
- Ctrl+W oraz sekwencja Esc, Backspace: kasowanie poprzedniego słowa;
- Ctrl+Delete oraz sekwencja Esc, d: kasowanie następnego słowa;
- Ctrl+X / Shift+Delete: wytnij;
- Ctrl+Insert, a przy zaznaczeniu także Ctrl+C: kopiuj;
- Ctrl+V / Shift+Insert: wklej;
- Ctrl+Z/Ctrl+Y: undo/redo;
- klik w polu: ustaw kursor;
- kółko: bez działania w polu.

Źródła: `_NORMALISED_KEYS`, `ui/prompts.py:97–138`; `TextInput.handle`, `ui/text_input.py:98–119`; `_move`, `ui/text_input.py:155–179`; `_delete`, `ui/text_input.py:181–199`; `_command`, `ui/text_input.py:212–229`.

W Ustawieniach istniejąca wartość jest zwykle `pristine=True`: pierwszy wpisany znak zastępuje całość; ruch kursora, zaznaczenie lub kasowanie przełącza na zwykłą edycję — `ui/settings.py:1290–1296`, `ui/text_input.py:201–210`.

## E01 — Edytor pojedynczego wyboru: SELECT

### Klawisze i mysz

↑↓, Tab/Shift+Tab, PgUp/PgDn, Home/End poruszają kursorem. Enter/→ zapisuje wybór i zamyka. Esc/←/Backspace/Ctrl+C zamyka bez wyboru nowej opcji. Space nic nie robi. Kółko przesuwa kursor o trzy; klik wskazuje, podwójny klik wybiera — `ui/settings.py:863–911,2156–2176`.

### Stopka

U-select: `↑↓/Tab · Enter/→ wybierz · Esc/← cofnij` — `ui/settings.py:61,1824`.

### Dół poza stopką

Slot U-MSG; znaczniki `↑ więcej`/`↓ więcej`. Kulka oznacza zapisaną wartość, a strzałka bieżący kursor — `ui/settings.py:2179–2187`. Brak osobnego wiersza `Cofnij`.

### Komunikaty

Nagłówek i opcje dokładnie z wykazu instancji; błędy U-MSG. Przesuwanie kursora nie wyświetla sukcesu ani nie zmienia zapisanej wartości.

### Naruszenia

N12/R2: trzy pary alternatywnych skrótów w jednej stopce: `↑↓/Tab`, `Enter/→`, `Esc/←`.

## E02 — Edytor wartości logicznej: Tak/Nie

### Klawisze i mysz

Jak E01. Początkowy kursor wskazuje bieżącą wartość — `ui/settings.py:1240–1251`.

### Stopka

U-select — `ui/settings.py:61,1824`.

### Dół poza stopką

Jak E01; kulka na zapisanym `Tak` lub `Nie`.

### Komunikaty

`Tak`, `Nie` — `_open_setting_editor`, `ui/settings.py:1241`; nazwy wszystkich pól bool z wykazu instancji. U-MSG.

### Naruszenia

N12/R2.

## E03 — Edytor wielokrotnego wyboru: produkty wideo / ścieżki MKV

### Klawisze i mysz

Nawigacja listowa jak E01. Space przełącza bieżącą opcję i uruchamia opóźniony zapis. Enter/→ zatwierdza aktualny zbiór i zamyka. Esc/←/Backspace/Ctrl+C zamyka; wcześniej zaakceptowane zmiany kolekcji nie są cofane. Na ostatnim produkcie `requested_products` Space jest ignorowany bez komunikatu — `ui/settings.py:900–911`.

### Stopka

U-multi: `↑↓ · Space zmień · Esc wróć` — `ui/settings.py:58`.

### Dół poza stopką

Slot U-MSG, znaczniki przewijania. `●/○` oznacza członkostwo w zbiorze — `ui/settings.py:2183–2184`.

### Komunikaty

`PRODUKTY WIDEO` lub `ŚCIEŻKI MKV` — nazwy z `ui/settings.py:239,244`, transformacja `ui/settings.py:1919–1931`. Pełne opcje U06/U08. U-MSG.

### Naruszenia

N13/R1: `Space zmień` jest pokazane także na jedynym zaznaczonym produkcie, gdzie kod odmawia zmiany bez komunikatu — `ui/settings.py:900–903`.

## E04 — Edytor tekstu / tekstu opcjonalnego

### Klawisze i mysz

E-TEXT. Poprawna zmiana zwykle zapisuje się automatycznie po 0,4 s. Enter waliduje i zatwierdza; Esc/Ctrl+C zamyka, po wcześniejszym wymuszeniu zapisu wartości oczekującej. Błędny niezatwierdzony tekst może zostać porzucony przez Esc — `ui/settings.py:706–727,863–889`.

### Stopka

U-input: `←→ kursor · Enter/Esc wróć · zapis automatyczny` — `ui/settings.py:67`.

### Dół poza stopką

Stały slot informacji/błędu. Nie ma opisu wymaganego formatu pola ani przycisku zapisu.

### Komunikaty

Tytuły pól z wykazu instancji; `✗ Wpisz jedną linię bez znaków sterujących`, komunikaty zapisu i walidacji z U-MSG. Dla typu opcjonalnego pusty tekst daje `None` — `ui/settings_editors.py:34–35`.

### Naruszenia

N14/R2: `Enter/Esc wróć`. N15/R3: ten sam napis sugeruje równoważny powrót, lecz Enter waliduje bieżący tekst, a Esc może porzucić tekst niepoprawny — `ui/settings.py:867–889`.

## E05 — Edytor liczby: całkowitej, dziesiętnej i opcjonalnej

### Klawisze i mysz

E-TEXT, nie spinner. ←→ w otwartym edytorze przesuwa kursor, nie zmienia liczby. Zmianę liczby strzałkami wykonuje menu rodzica. Zapis/Enter/Esc jak E04.

### Stopka

U-input — `ui/settings.py:67`.

### Dół poza stopką

Slot U-MSG. Zakres nie jest stałą podpowiedzią; pojawia się dopiero w komunikacie walidacji, jeżeli katalog ma obie granice — `ui/settings.py:1549–1556`.

### Komunikaty

Każda nazwa liczby i jej zakres w wykazie instancji. `✗ Nieprawidłowa wartość` lub `✗ Nieprawidłowa wartość · Zakres: …`. Parser używa `int`/`float`; pusty tekst jest dozwolony wyłącznie dla wariantu opcjonalnego — `ui/settings_editors.py:24–31`.

### Naruszenia

N14/R2, N15/R3. N16/R3: dla pola z jednostronną granicą lub wymaganym formatem komunikat nie podaje tej granicy/formatu — warunek `minimum is not None and maximum is not None`, `ui/settings.py:1554`.

## E06 — Edytor tekstowej listy języków

### Klawisze i mysz

E-TEXT; zapis jak E04. Kolejne elementy rozdziela przecinek. Spacje wokół elementów są usuwane, puste elementy i duplikaty odpadają — `ui/settings_editors.py:38–41,74–76`.

### Stopka

U-input — `ui/settings.py:67`. Nie ma podpowiedzi o przecinkach.

### Dół poza stopką

Slot U-MSG; brak osobnych wierszy elementów listy.

### Komunikaty

`PRIORYTET JĘZYKÓW AUDIO`, `PRIORYTET JĘZYKÓW NAPISÓW` — `ui/settings.py:170–171,1919–1931`. U-MSG.

### Naruszenia

N14/R2, N15/R3. N17/R3: format listy i oczekiwanie kodów języków nie są objaśnione przez tytuł ani stopkę — `ui/settings.py:67,1824`; parser `ui/settings_editors.py:74–76`.

## E07 — Tłumaczenie → Model tłumaczenia: katalog modeli

### Klawisze i mysz

E01. Wybranie modelu zapisuje dostawcę i identyfikator; `Własny model…` otwiera E08. Zamknięcie wraca do kategorii Tłumaczenie.

### Stopka

U-select — `ui/settings.py:61,1824`.

### Dół poza stopką

Slot U-MSG; nagłówki grup modeli; znaczniki przewijania.

### Komunikaty

`MODEL TŁUMACZENIA` — `ui/settings.py:1334`; `Własny model…`, `WŁASNY IDENTYFIKATOR` — `ui/settings.py:1327–1328`. Grupy `_model_group_label`, `ui/settings.py:2001–2014`: `ANTHROPIC`, `DEEPSEEK`, `GOOGLE GEMINI`, `OPENAI`, `OPENAI-COMPATIBLE`, `OPENROUTER`, `PALANTIR FOUNDRY · OPENAI`, `PALANTIR FOUNDRY · ANTHROPIC`, `PALANTIR FOUNDRY · GOOGLE`, `PALANTIR FOUNDRY · XAI`.

Opcje pochodzą tylko od dostępnych dostawców. Zwykła etykieta to model ID; Palantir: `{entry.label} · {entry.model_id}` — `anishift/application/service.py:657–685,952–965`. Błędy listy modeli: U-MSG.

### Naruszenia

N12/R2. Nie stwierdzono osobnego R1.

## E08 — Własny model → Dostawca

### Klawisze i mysz

E01. Enter/→ otwiera E09 z wybranym dostawcą. Esc zamyka edytor do kategorii, nie odtwarza pickera E07 — `ui/settings.py:867–870,1476–1478`.

### Stopka

U-select — `ui/settings.py:61,1824`.

### Dół poza stopką

Slot U-MSG. Brak osobnego okruszka wcześniejszych pickerów.

### Komunikaty

`WŁASNY MODEL · DOSTAWCA` — `ui/settings.py:1356`. Lista obejmuje dostępnych dostawców LLM poza Palantirem — `ui/settings.py:1343–1348`. `✗ Najpierw skonfiguruj dostawcę w Połączeniach` — U-MSG.

### Naruszenia

N12/R2.

## E09 — Własny model → ID modelu

### Klawisze i mysz

E-TEXT. Bez automatycznego zapisu; Enter wybiera model u dostawcy. Esc/Ctrl+C porzuca edycję. Źródła: `ui/settings.py:706–714,1363–1374,1520–1527`.

### Stopka

U-model-id: `ID modelu · Enter zatwierdź · Esc anuluj` — `ui/settings.py:1831–1832`.

### Dół poza stopką

Slot U-MSG; bez listy sugestii.

### Komunikaty

`{DOSTAWCA} · ID MODELU` — `ui/settings.py:1366`. Nieprawidłowy identyfikator daje ogólną walidację U-MSG.

### Naruszenia

N16/R3 w przypadku ogólnego błędu formatu. Brak potwierdzonego R1/R2.

## E10 — Połączenie → Klucz: edytor sekretu

### Klawisze i mysz

E-TEXT. Bufor zaczyna pusty, nie pokazuje wcześniejszego sekretu. Enter zapisuje niepusty tekst; pusty Enter zamyka bez usunięcia sekretu. Esc/Ctrl+C porzuca. Brak automatycznego zapisu — `ui/settings.py:1434–1441,1479–1484,1528–1529`.

### Stopka

U-secret: `Enter zatwierdź · Esc anuluj` — `ui/settings.py:64`.

### Dół poza stopką

Slot U-MSG. Pole jest maskowane `•` — `ui/settings.py:2149–2153`, `ui/text_input.py:121–123`.

### Komunikaty

Dziesięć tytułów `{NAZWA POŁĄCZENIA} · KLUCZ`, z nazw U13–U22 — `ui/settings.py:1437`. Błędy zapisu/walidacji U-MSG. Nie ma tekstu ujawniającego sekret.

### Naruszenia

Brak potwierdzonego R1/R2/R3 specyficznego dla tego ekranu.

## E11 — Połączenie → Adres

### Klawisze i mysz

E-TEXT i automatyczny zapis jak E04. Trzy instancje:

1. Palantir Foundry → `palantir_enrollment_base_url`;
2. Palantir Foundry · konto 2 → `palantir_fallback_enrollment_base_url`;
3. OpenAI-compatible → `openai_compatible_base_url`.

Pierwsze dwie zapisują preferencję; trzecia ustawienie środowiskowe — `ui/settings.py:1443–1459`.

### Stopka

U-input — `ui/settings.py:67`.

### Dół poza stopką

Slot U-MSG.

### Komunikaty

`PALANTIR FOUNDRY · ADRES`, `PALANTIR FOUNDRY · KONTO 2 · ADRES`, `OPENAI-COMPATIBLE · ADRES` — `ui/settings.py:1454`. Dla Palantira walidowany jest adres HTTPS lub pusty — `anishift/config/field_catalog.py:880–898`; wzorzec `anishift/config/user_settings.py:123–124`.

### Naruszenia

N14/R2, N15/R3, N16/R3: zły format URL daje ogólne `✗ Nieprawidłowa wartość`.

## E12 — Własne głosy → Dodaj głos

### Klawisze i mysz

E-TEXT; pusty bufor. Enter parsuje `alias | nazwa | ID głosu` i zapisuje listę. Esc/Ctrl+C porzuca. Brak automatycznego zapisu — `ui/settings.py:1168–1180,1298–1306,1515–1519`.

### Stopka

U-voice — `ui/settings.py:70`.

### Dół poza stopką

Slot U-MSG.

### Komunikaty

`DODAJ GŁOS` — `ui/settings.py:1174`; format trzech niepustych części — `ui/settings_editors.py:49–56`. Błąd parsera jest zamieniany na `✗ Nieprawidłowa wartość` przez `ui/settings.py:1493–1494`.

### Naruszenia

N18/R1: `puste usuwa` jest pokazane także przy dodawaniu nowego głosu; pusty tekst nie ma tu istniejącego głosu do usunięcia — `ui/settings.py:1301–1305`. N16/R3: ogólny błąd nie wskazuje brakującej części/duplikatu.

## E13 — Własne głosy → Edytuj istniejący głos

### Klawisze i mysz

E-TEXT; początkowo pełna linia `alias | nazwa | ID`. Enter zastępuje ten głos; pusty Enter usuwa go. Esc/Ctrl+C porzuca. Brak automatycznego zapisu — `ui/settings.py:1174–1179,1298–1306`.

### Stopka

U-voice — `ui/settings.py:70`.

### Dół poza stopką

Slot U-MSG.

### Komunikaty

Nagłówek `{ALIAS}` zapisany wielkimi literami — `ui/settings.py:1174`. Format i błędy jak E12.

### Naruszenia

N16/R3 dla ogólnej walidacji. `puste usuwa` ma tu rzeczywiste zastosowanie.

## E14 — Przywróć domyślne: CONFIRM

### Klawisze i mysz

Nawigacja opcji jak E01; początkowo `Nie`. Enter albo → zatwierdza. Esc/←/Backspace/Ctrl+C zamyka. Klik wskazuje, podwójny klik nie zatwierdza — `ui/settings.py:892–911,1376–1383,1815`.

### Stopka

U-select, nie osobna stopka „Enter tak / Esc nie” — `ui/settings.py:61,1824`.

### Dół poza stopką

Slot U-MSG; brak osobnego wiersza cofania.

### Komunikaty

Tytuł `PRZYWRÓCIĆ DOMYŚLNE · {ZAKRES}?`, opcje `Nie`, `Tak` — `ui/settings.py:1376–1383`.

Wszystkie instancje zakresu:

- `WSZYSTKO` — root;
- `OGÓLNE`;
- `NAPISY`;
- `TŁUMACZENIE` — kategoria tłumaczenia;
- `LEKTOR`;
- `WYNIK`;
- `AUTO`;
- `POBIERANIE`;
- `WŁASNE GŁOSY`;
- `WIDEO` — recepta video;
- `TŁUMACZENIE` — recepta translate;
- `AUDIOBOOK` — recepta audiobook.

Źródła: `_scope_title`, `ui/settings.py:2040–2047`; `_SCOPE_FIELDS`, `ui/settings.py:367–375`; `_reset_scope`, `ui/settings.py:1385–1421`.

Nie ma resetu Połączeń. Root może pokazać częściowy reset z U-MSG.

### Naruszenia

N12/R2. N07/R3 dla zakresu Wynik. N19/R3: dwa różne zakresy mają identyczne pytanie `PRZYWRÓCIĆ DOMYŚLNE · TŁUMACZENIE?`: globalne ustawienia tłumaczenia i recepta Auto → Tłumaczenie — `ui/settings.py:2041–2047`.

## E15 — Usuń klucz: CONFIRM

### Klawisze i mysz

Jak E14. `Tak` + Enter/→ usuwa sekret, `Nie` zamyka bez zmiany. Podwójny klik nie zatwierdza.

### Stopka

U-select — `ui/settings.py:61,1824`.

### Dół poza stopką

Slot U-MSG.

### Komunikaty

Dziesięć instancji `USUNĄĆ KLUCZ · {NAZWA POŁĄCZENIA}?`, po jednej dla U13–U22; `Nie`, `Tak` — `ui/settings.py:1461–1469`. Usunięcie: `ui/settings.py:1531–1533`.

### Naruszenia

N12/R2. Nie stwierdzono osobnego R1.

## E16 — Testowanie połączenia: BUSY na menu Palantira

### Klawisze i mysz

Tylko Esc lub niezaznaczony Ctrl+C kończy oczekiwanie. Pozostałe klawisze są ignorowane; Backspace nie jest tu aliasem Esc — `ui/settings.py:552–553,789–796`. Klik nie zmienia kursora, bo `select` odmawia przy `_busy` — `ui/settings.py:584–588`. Prawy przycisk działa jako Esc. Kółko może przewijać menu, bo `scroll` nie sprawdza `_busy` — `ui/settings.py:564–576`.

### Stopka

Nadal U-menu: `↑↓/Tab · ←→ · Enter · Esc` — `ui/settings.py:1720`.

### Dół poza stopką

Slot feedbacku pokazuje testowanie, wynik lub anulowanie.

### Komunikaty

`Testowanie połączenia…`, `✓ Połączenie działa`, `✗ Test połączenia nie powiódł się`, `Anulowano` — U-MSG.

### Naruszenia

N11/R1: widoczne ↑↓/Tab, ←→ i Enter nie działają podczas `_busy`. N01/R2 i N02/R3 pozostają w tej samej stopce.

## Ręczny — wspólne zasady i słowniki

### Rzeczywiste Ctrl+C

W samym `ManualController` `interrupt` bywa traktowane jak powrót, ale normalne wejście przez aplikację przechwytuje Ctrl+C wcześniej:

1. kopiuje zaznaczenie ramki, jeśli istnieje;
2. kopiuje zaznaczenie pola ścieżki, jeśli istnieje;
3. w innym przypadku anuluje sesję Ręcznego i wraca do kontekstu wejścia.

Źródła: `ui/app.py:289–309`, `ui/app.py:529–559`, `ui/manual.py:818–821`. Dlatego Ctrl+C nie jest poniżej zwykłym aliasem Esc.

### Wspólne stopki Ręcznego

| ID | Dokładny tekst | Źródło |
|---|---|---|
| M-menu | `↑↓ · Enter · Esc` | `_MENU_HINT`, `ui/manual.py:74` |
| M-multi | `↑↓ · Enter/Space zmień · Esc wróć` | `_MULTI_HINT`, `ui/manual.py:77` |
| M-input | `Enter zatwierdź · Esc wróć` | `_INPUT_HINT`, `ui/manual.py:90` |
| M-groups | `↑↓ · Space wybierz · A wszystkie · End podgląd · Esc wróć` | `_render_groups`, `ui/manual.py:1113` |
| M-busy | `Esc anuluj` | `_render_busy`, `ui/manual.py:1261` |

Wszystkie nieklikalne. `ManualController._finish` dopisuje feedback do treści, potem przypina stopkę — `ui/manual.py:1272–1275`. W przeciwieństwie do Ustawień nie rezerwuje zawsze pustego slotu feedbacku.

### Komunikaty planera prezentowane przez Ręczny

| Kod → dokładny tekst | Źródło | Znaczenie |
|---|---|---|
| `audio_duration_mismatch` → `Wybrane audio ma inną długość niż wideo` | `_PROBLEM_MESSAGES`, `ui/manual.py:126` | Niezgodna długość wybranego audio. |
| `audio_selection_invalid` → `Wybrane audio jest niedostępne lub nieprawidłowe` | `ui/manual.py:127` | Wybrany artefakt/ścieżka nie nadaje się do użycia. |
| `audio_source_missing` → `Brak zgodnego źródła audio` | `ui/manual.py:128` | Plan nie ma odpowiedniego audio. |
| `source_conflict` → `Grupa zawiera nierozwiązany konflikt źródeł` | `ui/manual.py:129` | Konflikt w grupie wejściowej nadal blokuje plan. |
| `subtitle_selection_invalid` → `Wybrane napisy są niedostępne lub nieprawidłowe` | `ui/manual.py:130` | Wskazane napisy są niepoprawne lub niedostępne. |
| `subtitle_selection_missing` → `Wybrany rodzaj napisów wymaga wskazania źródła` | `ui/manual.py:131` | Polityka napisów wymaga jawnego wskazania pliku/ścieżki. |
| `subtitle_source_missing` → `Brak zgodnego źródła napisów` | `ui/manual.py:132` | Nie ma zgodnych napisów do zaplanowania. |
| `video_missing` → `Brak prawidłowego źródła wideo` | `ui/manual.py:133` | Plan wymagający wideo nie ma poprawnego źródła. |

Inne `PlanProblem.message` są sanitizowane i pokazywane bez tłumaczenia — `ui/manual.py:1225–1242`. To otwarty kanał treści z backendu, nie zamknięty słownik polskich zdań.

### Wspólne odmowy backendu — odwołanie do dodatku A

Ręczny i ekrany błędu aplikacji używają tego samego `refusal_text` co StateController. Pełne literalne słowniki są w dodatku A tego raportu; nie są powielane w tej części.

- wywołania w Ręcznym: `ui/manual.py:603,629,658,967,1021`;
- wywołania w aplikacji: `ui/app.py:670,1204`;
- implementacja: `ui/state_texts.py:128–145`.

| Grupa z dodatku A | Źródło | Znaczenie dla tej części |
|---|---|---|
| `_RETRY_PROBLEMS` | `ui/state_texts.py:17–26` | Odmowy ponowienia przekazywanego do Ręcznego. |
| `_CLIENT_PROBLEMS` | `ui/state_texts.py:29–40` | Tłumaczenia stanów prywatnego klienta torrent. |
| `_REFUSAL_TEXTS` | `ui/state_texts.py:43–59` | Rezerwacje, sesja, zajęte grupy, pauza, wygaszanie procesu. |
| `_UNKNOWN_REFUSAL` | `ui/state_texts.py:62` | Ogólna odmowa bez precyzyjniej rozpoznanej przyczyny. |
| `_CONTROL_PROBLEMS` | `ui/state_texts.py:65–76` | Błędy protokołu/instancji/podglądu. |
| `_SUBSCRIPTION_PROBLEMS` | `ui/state_texts.py:79–90` | Wspólny fallback rozpoznający przyczyny subskrypcji. |
| `LIBRARY_PROBLEMS` | `ui/state_texts.py:93–124` | Wspólny fallback rozpoznający przyczyny biblioteki/źródła. |
| Brak potwierdzonej odpowiedzi | `ui/state_texts.py:140–143` | Odrębny tekst dla niepewnego wyniku polecenia. |

Nie oznacza to, że każdy kod biblioteki/subskrypcji ma udowodnioną drogę emisji podczas zwykłego Ręcznego. Istotne dla jego zwykłych działań są przede wszystkim przyczyny rezerwacji grupy, trwającego przetwarzania/przenoszenia, wygasłej sesji, obcego podglądu, niewznawialnej pracy i odmowy procesu; literalne teksty i ich znaczenia pozostają w dodatku A.

## M01 — Wybierz odcinki: GROUPS

### Klawisze i mysz

- ↑↓: zmiana wiersza z zawijaniem.
- Space lub Enter na odcinku: zmiana zaznaczenia i rezerwacja zakresu.
- A/a: jeśli cokolwiek zaznaczono, odznacza wszystko; jeśli nic — zaznacza wszystkie grupy.
- Home: pierwszy wiersz.
- End: ustawia kursor na pierwszej akcji `Podgląd`, nie uruchamia podglądu.
- Enter na akcji: jej wykonanie, wymagające zaznaczenia poza `Anuluj`.
- Esc/Backspace: wyjście z Ręcznego.
- Ctrl+C: wspólna obsługa Ręcznego opisana wyżej.
- Klik wybiera; podwójny klik na odcinku przełącza jego zaznaczenie. Kółko nie działa.

Źródła: `ui/manual.py:579–631`, `ui/app.py:446–465`.

### Stopka

M-groups: `↑↓ · Space wybierz · A wszystkie · End podgląd · Esc wróć` — `ui/manual.py:1113`.

### Dół poza stopką

Po odcinkach występują wszystkie akcje zakresu. Feedback jest dopisywany po treści; nie ma osobnej linii `Zaznaczone: …` — `ui/manual.py:1101–1113,1272–1275`.

### Komunikaty

`WYBIERZ ODCINKI` — `ui/manual.py:1106`.

Akcje `_GROUP_ACTIONS`, `ui/manual.py:80–87`: `Podgląd`, `Dostosuj źródła i produkty`, `Regeneruj lektora`, `Regeneruj polskie napisy`, `Dokończ poprzednią pracę`, `Anuluj`.

`Dokończ poprzednią pracę` istnieje dla `ResidentSession`; lokalny AppService pomija tę pozycję — `ui/manual.py:439–441`.

Etykiety grup:

- `{nazwa} · konflikt źródeł` — `ui/manual.py:287–288`;
- przy powtarzającym się stemie dopisywany jest katalog;
- fallbacki `inny katalog`, `katalog główny` — `ui/manual.py:293–298`.

Odmowy:

- `✗ Wybierz co najmniej jeden odcinek` — `ui/manual.py:612`;
- `✗ Nie można zarezerwować odcinków · {refusal_text}` — `ui/manual.py:603`, słownik dodatku A.

### Naruszenia

N20/R1: `Space wybierz` nadal jest widoczne na wierszach akcji, gdzie Space nic nie robi — `ui/manual.py:585–589`. N21/R3: `End podgląd` nie mówi, że End tylko wskazuje akcję — `ui/manual.py:594–595`. N22/R3: `A wszystkie` przy częściowym zaznaczeniu usuwa wszystkie zaznaczenia, zamiast dopełnić je do wszystkich — `ui/manual.py:590–591`.

## M02 — Decyzja dla bieżącego odcinka: GROUP_ACTION

### Klawisze i mysz

↑↓, Enter. Pierwszy wiersz resetuje draft odcinka do domyślnego i przechodzi dalej; drugi otwiera CUSTOM; trzeci wraca do poprzedniego odcinka albo listy. Esc/Backspace wykonuje ten sam powrót. Ctrl+C — wspólna obsługa Ręcznego. Klik/podwójny klik zwykłe; kółko nie działa — `ui/manual.py:670–681,1002–1008`.

### Stopka

M-menu: `↑↓ · Enter · Esc` — `ui/manual.py:74`.

### Dół poza stopką

Ewentualny feedback w treści; katalog/wersja.

### Komunikaty

Nagłówek: etykieta bieżącej grupy. Pozycje: `Użyj ustawień domyślnych`, `Dostosuj ten odcinek`, `Wróć` — `_render_group_action`, `ui/manual.py:1115–1118`.

### Naruszenia

N23/R3: M-menu nie nazywa czynności Enter ani celu Esc; konkretna akcja zależy od wiersza. Brak osobnego R1/R2.

## M03 — Dostosuj odcinek: CUSTOM

### Klawisze i mysz

↑↓, Enter otwiera wskazany edytor. `Gotowe` przechodzi do następnego odcinka albo buduje plan. `Wróć`/Esc/Backspace wraca do GROUP_ACTION. Ctrl+C — wspólna obsługa Ręcznego. Kółko nie działa — `ui/manual.py:683–726`.

### Stopka

M-menu — `ui/manual.py:74`.

### Dół poza stopką

Feedback po nieudanym dodaniu pliku jest dopisywany do treści — `ui/manual.py:965–968,1272–1275`.

### Komunikaty

Wiersze `_CustomRow`, `ui/manual.py:160–167`:

- `Wynik`;
- `Napisy źródłowe`;
- `Audio źródłowe`;
- `Wideo źródłowe` — tylko gdy są co najmniej dwa gotowe źródła wideo, `ui/manual.py:1071–1078`;
- `Czytanie` — tylko gdy legalnych osi czasu jest więcej niż jedna, `ui/manual.py:687–688`;
- `Gotowe`;
- `Wróć`.

Błąd dodania: `✗ Nie udało się dodać pliku · {powód}`; fallback `Nieznany błąd` — `ui/manual.py:967–968`. Powód może pochodzić ze słownika dodatku A.

### Naruszenia

N23/R3.

## M04 — Wynik odcinka: PRODUCTS

### Klawisze i mysz

↑↓; Enter/Space przełącza produkt. Enter na `Zapisz` przenosi zbiór do draftu, jeśli niepusty. Enter na `Wróć`, Esc lub Backspace wraca bez zatwierdzenia bieżącej selekcji. Space na `Zapisz/Wróć` nie działa. Ctrl+C — wspólna obsługa Ręcznego. Kółko nie działa — `ui/manual.py:744–769`.

### Stopka

M-multi: `↑↓ · Enter/Space zmień · Esc wróć` — `ui/manual.py:77`.

### Dół poza stopką

Wiersze `Zapisz`, `Wróć`; poniżej ewentualny błąd. Brak automatycznego zapisu.

### Komunikaty

`WYNIK ODCINKA` — `ui/manual.py:1140`. Produkty, filtrowane przez `legal_products`: `Polskie napisy`, `Polski lektor`, `MKV`, `MP4`, `Okładka MP4` — `ui/manual.py:93–99,703–705`. `Zapisz`, `Wróć` — `ui/manual.py:1138`. `✗ Wybierz co najmniej jeden wynik` — `ui/manual.py:760`.

### Naruszenia

N24/R1: `Enter/Space zmień` na `Zapisz/Wróć`, gdzie Space nie działa. N25/R2: Enter i Space opisane jako ta sama zmiana produktu.

## M05 — Czytanie odcinka: TIMELINE

### Klawisze i mysz

↑↓, Enter wybiera oś czasu i wraca do CUSTOM. Wiersz `Wróć`, Esc/Backspace wraca bez zmiany. Ctrl+C — wspólna obsługa Ręcznego. Klik/podwójny klik; kółko nie działa — `ui/manual.py:733–742`.

### Stopka

M-menu — `ui/manual.py:74`.

### Dół poza stopką

`Wróć`, ewentualny feedback; katalog/wersja.

### Komunikaty

`CZYTANIE ODCINKA` — `ui/manual.py:1129`. Opcje `_TIMELINE_LABELS`, `ui/manual.py:102–105`: `Jedno po drugim, z krótką pauzą`, `W czasach z dokumentu`.

Lista jest filtrowana przez `legal_narration_timelines` — `ui/manual.py:692–694`.

### Naruszenia

N23/R3.

## M06 — Napisy źródłowe: SUBTITLES

### Klawisze i mysz

↑↓, Enter wybiera źródło; `Plik zewnętrzny…` otwiera M09. Esc/Backspace wraca do CUSTOM. Ctrl+C — wspólna obsługa Ręcznego. Kółko nie działa — `ui/manual.py:771–801`.

### Stopka

M-menu — `ui/manual.py:74`.

### Dół poza stopką

Brak osobnego `Wróć` w liście źródeł. Feedback w treści; katalog/wersja.

### Komunikaty

`NAPISY ŹRÓDŁOWE` — `ui/manual.py:1153`. `Automatycznie`, gotowe pliki napisów, zgodne osadzone ścieżki ASS/SRT, `Plik zewnętrzny…`, `Brak` — `_subtitle_choices`, `ui/manual.py:301–340`.

Etykieta ścieżki: `#{track_id} · {język} · {kodek} · {nazwa}`; etykieta pliku: nazwa + dostępny język/format/kodek — `ui/manual.py:408–418`.

### Naruszenia

N23/R3. Nazwy plików i ścieżek są danymi, nie zamkniętym słownikiem komunikatów.

## M07 — Audio źródłowe: AUDIO

### Klawisze i mysz

↑↓, Enter wybiera źródło albo otwiera M10/M11. Esc/Backspace wraca do CUSTOM. Ctrl+C — wspólna obsługa Ręcznego. Kółko nie działa — `ui/manual.py:771–801`.

### Stopka

M-menu — `ui/manual.py:74`.

### Dół poza stopką

Jak M06: brak własnego wiersza powrotu.

### Komunikaty

`AUDIO ŹRÓDŁOWE` — `ui/manual.py:1154`. `Automatycznie`, gotowe audio źródłowe/lektora, osadzone ścieżki audio oraz `Plik zewnętrzny jako źródło…`, `Gotowy zewnętrzny lektor lub mix…` — `_audio_choices`, `ui/manual.py:343–389`. Etykiety plików/ścieżek jak M06.

### Naruszenia

N23/R3.

## M08 — Wideo źródłowe: VIDEO

### Klawisze i mysz

↑↓, Enter wybiera wideo i wraca do CUSTOM. Zmiana wideo czyści wskazania osadzonych ścieżek audio i napisów — `ui/manual.py:895–903`. Esc/Backspace wraca; Ctrl+C — wspólna obsługa Ręcznego. Kółko nie działa.

### Stopka

M-menu — `ui/manual.py:74`.

### Dół poza stopką

Jak M06.

### Komunikaty

`WIDEO ŹRÓDŁOWE` — `ui/manual.py:1155`. `Automatycznie` oraz gotowe pliki MKV/MP4 — `_video_choices`, `ui/manual.py:392–405`. Wejście do tego ekranu wymaga więcej niż jednego gotowego wideo — `ui/manual.py:1071–1078`.

### Naruszenia

N23/R3.

## M09 — Zewnętrzne napisy: INPUT/SUBTITLE

### Klawisze i mysz

E-TEXT. Enter usuwa otaczające spacje/cudzysłowy, wymaga niepustej ścieżki i rozpoczyna rejestrację. Esc wraca do CUSTOM. Backspace edytuje tekst. Ctrl+C kopiuje zaznaczenie, a bez niego opuszcza całego Ręcznego. Klik ustawia kursor; kółko nie działa — `ui/manual.py:857–867`, wspólna obsługa Ctrl+C Ręcznego.

### Stopka

M-input: `Enter zatwierdź · Esc wróć` — `ui/manual.py:90`.

### Dół poza stopką

Pole `> {tekst}` oraz ewentualny błąd w treści — `ui/manual.py:1244–1253`.

### Komunikaty

`ZEWNĘTRZNE NAPISY` — `ui/manual.py:1245`. `✗ Podaj ścieżkę pliku` — `ui/manual.py:865`. Po Enter ekran przechodzi do M12; błędy dodania wracają na CUSTOM.

### Naruszenia

Brak potwierdzonego lokalnego R1/R2/R3.

## M10 — Zewnętrzne audio jako źródło: INPUT/SOURCE_AUDIO

### Klawisze i mysz

Jak M09; rejestracja nadaje rolę `SOURCE_AUDIO` — `ui/manual.py:940–945`.

### Stopka

M-input — `ui/manual.py:90`.

### Dół poza stopką

Jak M09.

### Komunikaty

`ZEWNĘTRZNE AUDIO` — `ui/manual.py:1245`; `✗ Podaj ścieżkę pliku` — `ui/manual.py:865`.

### Naruszenia

N26/R3: tytuł nie przypomina wybranej roli audio; jest taki sam dla źródła i gotowego lektora/miksu — `ui/manual.py:1245`, wobec różnych ról `ui/manual.py:940–945`.

## M11 — Gotowy zewnętrzny lektor/miks: INPUT/NARRATION_MIX

### Klawisze i mysz

Jak M09; rejestracja nadaje rolę `NARRATION_MIX` — `ui/manual.py:940–945`.

### Stopka

M-input — `ui/manual.py:90`.

### Dół poza stopką

Jak M09.

### Komunikaty

`ZEWNĘTRZNE AUDIO`, `✗ Podaj ścieżkę pliku` — `ui/manual.py:1245,865`.

### Naruszenia

N26/R3.

## M12 — Ręczny: BUSY

### Klawisze i mysz

Esc/Backspace przerywa oczekiwanie. Dla `ResidentSession` wychodzi z Ręcznego, dla lokalnego AppService wraca do CUSTOM i anuluje token — `ui/manual.py:472–474,564–577`. Ctrl+C obsługuje aplikacja według wspólnych zasad Ręcznego. Pozostałe klawisze ignorowane; brak wybieralnych wierszy; prawy przycisk = Esc; kółko nie działa.

### Stopka

M-busy: `Esc anuluj` — `ui/manual.py:1261`.

### Dół poza stopką

Brak listy, podsumowania zaznaczeń i informacji o zakresie operacji.

### Komunikaty

`TRYB RĘCZNY`, `{spinner} Sprawdzanie pliku…` — `_render_busy`, `ui/manual.py:1255–1261`.

Ten sam BUSY służy:

- rejestracji zewnętrznego pliku — `ui/manual.py:905–920`;
- rezerwacji/przygotowaniu podglądu, także wielu odcinków — `ui/manual.py:633–668`.

### Naruszenia

N27/R3: `Sprawdzanie pliku…` jest pokazywane również przy przygotowaniu planu lub samej rezerwacji zakresu, nie tylko przy sprawdzaniu pliku.

## M13 — Podgląd planu: PREVIEW

### Klawisze i mysz

↑↓, Enter:

- `Uruchom` istnieje tylko dla `plan.can_execute`;
- `Wróć do zmian` wraca do GROUPS przy automatycznym podglądzie albo GROUP_ACTION przy indywidualnym;
- `Anuluj` wychodzi z Ręcznego.

Esc/Backspace wraca jak „Wróć do zmian”; Ctrl+C — wspólna obsługa Ręcznego. Kółko i PageUp/PageDown nie przewijają podsumowania — `ui/manual.py:803–816,1045–1050`, `ui/app.py:446–465`.

### Stopka

M-menu — `ui/manual.py:74`.

### Dół poza stopką

Akcje pod podsumowaniem; ewentualny feedback po treści. Problemy są limitowane budżetem wysokości; brak osobnego pełnego podglądu ukrytych komunikatów — `ui/manual.py:1172–1196,1278–1295`.

### Komunikaty

- `TRYB RĘCZNY` — `ui/manual.py:1185`;
- `Uruchom`, `Wróć do zmian`, `Anuluj` — `ui/manual.py:1177–1181`;
- `Plan nie jest dostępny` — `ui/manual.py:1200`;
- `{N} odcinków` — `ui/manual.py:1204`;
- `{nazwa produktu}: {N}` — `ui/manual.py:1205`, nazwy z `ui/manual.py:93–99`;
- `Zachowane: …`, `Do wykonania: …` — `ui/manual.py:1207–1215`;
- `Wymagane: …` — `ui/manual.py:1222`, składniki `tłumaczenie`, `synteza mowy`, `miks audio` z `ui/manual.py:108–112`;
- blokery: `✗ {odcinek/Plan} · {powód}` — `ui/manual.py:1229–1232`, słownik komunikatów planera powyżej;
- ostrzeżenia: `! {odcinek/Plan} · {message}` — `ui/manual.py:1239–1241`;
- `… jeszcze {N}` — `_limit_problems`, `ui/manual.py:1292`.

Błędy:

- `✗ Nie można zbudować planu · {refusal_text}` — `ui/manual.py:629,1021`;
- `✗ Nie można przygotować odcinków · {refusal_text}` — `ui/manual.py:658`.

Przy wejściu z ponowienia mogą powstać:

- `Źródło zmieniło się; wróć i ponownie wybierz Ponów` — `ui/manual.py:543`;
- `Źródło lub część zapisanego zlecenia już nie istnieje` — `ui/manual.py:546`.

Te wyjątki trafiają następnie do ekranu MESSAGE aplikacji przez `ui/app.py:665–670`. Wspólne odmowy `refusal_text`: dodatek A.

### Naruszenia

N23/R3. N28/R3: `… jeszcze {N}` informuje o schowanych problemach, ale ekran nie oferuje sposobu ich przewinięcia; dodatkowo oblicza licznik przed zastąpieniem ostatniego widocznego problemu znacznikiem, więc liczba faktycznie niewidocznych problemów jest o jeden większa — `ui/manual.py:1291–1295`.

## Home, przygotowanie, Auto, postęp i wynik — rzeczywiste routowanie

1. Produkcyjne `main._default` zawsze tworzy `ResidentSession` i przekazuje ją do `run_interactive` — `anishift/cli/main.py:166–175`.
2. Bez `show_state` aplikacja zaczyna w Home; `show_state=True` od razu otwiera State — `ui/app.py:192`.
3. Home ma wyłącznie `Panel`, `Ręczny`, `Ustawienia`, `Wyjście` — `ui/app.py:63–68`. Nie ma pozycji Auto.
4. Metoda `run()` wywołuje `_start_auto()` tylko dla nie-`None` argumentu `batch` — `ui/app.py:218–226`.
5. Znalezione produkcyjne wywołanie `run_interactive` w `anishift/cli/main.py:175` nie przekazuje `batch`. W objętym odczytem kodzie `anishift/` nie znaleziono drugiego wywołania.
6. Ręczny po zaakceptowaniu planu z rezydenta pokazuje State → Przetwarzanie z `Przygotowanie` — `ui/app.py:675–696`; wywołuje `backend.start(prepared.plan)`, kończy lokalnego workera i nie przechodzi do `_ViewMode.AUTO` — `ui/app.py:796–807`.
7. Stare `_ViewMode.AUTO`/`AUTO_DONE` i wynik `_result_message` pozostają dla lokalnego wykonania `ExecutionPlan` — `ui/app.py:808–840`.
8. Automatyczna praca rezydenta oraz ręcznie przyjęta praca są obserwowane w StateController. Szczegółowy inwentarz tych ekranów znajduje się w części wspólnego panelu.
9. Odmowa Auto w sesji rezydenta trafia do notice panelu, a przy braku State/rezydenta do MESSAGE — `ui/app.py:751–760`.

Poniżej rozdzielono ekrany istniejące w kodzie od ekranów normalnej ścieżki produkcyjnej.

## A01 — Home

### Klawisze i mysz

↑↓ wybiera z zawijaniem; Enter wykonuje akcję. Ctrl+C bez zaznaczenia kończy panel. Esc, Backspace, Tab, Home/End nie mają akcji menu. Klik wybiera, podwójny klik aktywuje. Prawy przycisk daje Esc, więc nie wychodzi. Kółko nie działa — `ui/app.py:476–498,529–535,431–465`.

### Stopka

`↑↓ · Enter` — `_HOME_HINT`, `ui/app.py:71`. Przy bardzo małej wysokości, najwyżej dwóch wierszy, helper ma wariant bez podpowiedzi — `ui/app.py:1068–1084`.

### Dół poza stopką

Katalog/wersja albo informacja kopiowania, jak we wspólnym najniższym wierszu aplikacji. Nie ma statusu automatu. Branding/maskotka mogą być pominięte w niskim terminalu — `ui/app.py:1027–1028`.

### Komunikaty

`Panel`, `Ręczny`, `Ustawienia`, `Wyjście` — `_HOME_CHOICES`, `ui/app.py:63–68`. Marka `ANISHIFT` — `ui/home.py:165–172`. Brak własnych komunikatów sukcesu/błędu Home.

### Naruszenia

Brak potwierdzonego R1/R2/R3 dla zwykłego, bezczynnego Home.

## A02 — Przygotowanie Ręcznego: MANUAL_PREPARING

### Klawisze i mysz

Ctrl+C przerywa przygotowanie i wraca do wcześniejszego kontekstu. Inne klawisze nie sterują pokazanym menu. Klik nie wybiera pozycji, bo `_select_row` obsługuje menu tylko dla HOME — `ui/app.py:304–326,431–444,537–552`.

### Stopka

Widoczna stopka Home `↑↓ · Enter`, mimo że tryb nie jest HOME — `ui/app.py:958–967`.

### Dół poza stopką

Katalog/wersja. Nie ma spinnera ani tekstu skanowania. Wyświetlana jest klatka Home — `ui/app.py:958–967`.

### Komunikaty

Widoczne teksty Home z A01. Gdy discovery jest puste, późniejszy MESSAGE pokazuje `Nie znaleziono materiału do przetworzenia` — `ui/app.py:640–643`. Inny błąd: `refusal_text(problem)` — `ui/app.py:665–670`, dodatek A.

### Naruszenia

N29/R1: stopka `↑↓ · Enter` sugeruje sterowanie menu, lecz te klawisze są ignorowane w MANUAL_PREPARING.

## A03 — Przygotowanie Auto / startu lokalnego: PREPARING

### Klawisze i mysz

Bez rezydenta: Ctrl+C przerywa przygotowanie; pozostałe klawisze nie aktywują pokazanego Home. W partii Ctrl+C zamyka ją kodem anulowania — `ui/app.py:529–552`. Z rezydentem `_start_auto`/`_start_manual_run` przełącza na State → Przetwarzanie — `ui/app.py:597–599,694–696`.

### Stopka

W wariancie renderowanym jako PREPARING: stopka Home `↑↓ · Enter` — `ui/app.py:958–967`. Po przejściu do State stopkę określa StateController.

### Dół poza stopką

W wariancie Home: katalog/wersja, bez tekstu skanowania.

### Komunikaty

W samym PREPARING tylko teksty Home. Przy przejściu do panelu notice `Przygotowanie` — `ui/app.py:598,695`.

### Naruszenia

N29/R1 w wariancie pozostającym w PREPARING.

## A04 — Auto: aktywny lokalny postęp

### Klawisze i mysz

- ↑↓: przewinięcie o jeden wiersz;
- PgUp/PgDn: o `visible−1`, minimum jeden;
- Home: początek;
- End: włącza śledzenie aktywnej pracy, nie skok na ostatni plik;
- każde inne przewinięcie odłącza śledzenie;
- kółko: trzy wiersze;
- Ctrl+C: anuluje lokalny run i wraca do Home; w partii zamyka kodem anulowania;
- Enter/Esc/Backspace nie kończą aktywnego Auto;
- brak wierszy akcji do kliknięcia/podwójnego kliknięcia.

Źródła: `_QueueView`, `ui/app.py:127–154`; routing `ui/app.py:317–319`; przerwanie `ui/app.py:561–574`; kółko `ui/app.py:459–460`.

### Stopka

Brak tekstowej podpowiedzi klawiszy w `_auto_content` — `ui/app.py:1087–1121`. Pozostaje najniższa linia katalogu/wersji.

### Dół poza stopką

Przewijana kolejka, liczniki ukrytych wierszy: `↑ {N} poza widokiem`, `↓ {N} poza widokiem` — `_queue_marker`, `ui/app.py:1124–1127`. Przy mniej niż ośmiu wierszach: `↑ {N} · ↓ {N}` — `ui/app.py:1097–1102`.

Brak linii statusu automatu.

### Komunikaty

Pełny słownik faz z `ui/progress.py`:

| Tekst | Źródło | Znaczenie |
|---|---|---|
| `Ekstrakcja` | `_ACTIVE_LABEL`, `ui/progress.py:85` | Aktywne wyodrębnianie/normalizowanie wejścia; również początkowa prealokowana etykieta, `ui/progress.py:578–580`. |
| `Tłumaczenie` | `ui/progress.py:86` | Aktywny etap tłumaczenia/podziału. |
| `Synteza mowy` | `ui/progress.py:87` | TTS. |
| `Dźwięk` | `ui/progress.py:88` | Ogólny etap obróbki audio. |
| `Kompozycja` | `ui/progress.py:89` | Budowa kontenera wideo. |
| `Okładka` | `ui/progress.py:90` | Kompozycja filmu z okładką. |
| `Zapis` | `ui/progress.py:91` | Publikacja produktu. |
| `Przetwarzanie` | `_FALLBACK_LABEL`, `ui/progress.py:95` | Faza bez własnej etykiety. |
| `Wyodrębniono` | `_COMPLETE_LABEL`, `ui/progress.py:99` | Wszystkie zadania etapu ekstrakcji ukończone. |
| `Przetłumaczono` | `ui/progress.py:100` | Wszystkie zadania etapu tłumaczenia ukończone. |
| `Normalizacja` | `_AUDIO_LABEL`, `ui/progress.py:105` | Callback audio `normalizing`. |
| `Oś czasu` | `ui/progress.py:106` | Callback `timeline`. |
| `Miksowanie` | `ui/progress.py:107` | Callback `mixing`. |
| `Wznowienie` | `ui/progress.py:108` | Callback `narration_resume`. |
| `Brak mowy` | `ui/progress.py:109` | Callback `skipped_no_spoken`. |
| `Lektor` | `ui/progress.py:110` | Callback `wrapping`. |
| `Przygotowanie` | `_show_active_task`, `ui/progress.py:415` | Aktywne zadanie bez mierzalnej publicznej fazy. |
| `Ponawianie` | `_retry_task`, `ui/progress.py:485` | Retry tłumaczenia lub TTS. |
| `✓ Gotowe` | `_finish_group`, `ui/progress.py:529` | Grupa zakończona sukcesem; 100%. |
| `Anulowano` | `_finish_group`, `ui/progress.py:535`; `_finish_remaining`, `ui/progress.py:552` | Grupa albo reszta runu anulowana. |
| `Błąd` | `_finish_group`, `ui/progress.py:538` | Grupa zakończona niesukcesem innym niż anulowanie. |
| `Nie wykonano` | `_finish_remaining`, `ui/progress.py:555` | Run skończony, ale grupa nie miała końcowego sukcesu/anulowania. |
| `Materiał` | `_initialize`, `ui/progress.py:219` | Brak użytecznej etykiety źródła. |

Nazwa pliku, procent i czas są danymi. Nieznany pomiar wyświetla liczbowy fallback zero lub ostatni znany procent; nie jest komunikatem błędu — `ui/progress.py:645–649`.

### Naruszenia

Nie stwierdzono R1/R2: nie ma podpowiedzi akcji. N30/R3: fazy `Ekstrakcja`, `Kompozycja`, `Oś czasu` nie objaśniają użytkownikowi konkretnych wykonywanych operacji — `ui/progress.py:84–112`; renderer składa wyłącznie fazę i nazwę, `ui/progress.py:755–757`.

## A05 — Auto: zakończenie sukcesem, AUTO_DONE

### Klawisze i mysz

Klawisze przewijania działają jak A04. Każdy pozostały klawisz wraca do kontekstu, a w partii zamyka okno. Wyjątki:

- Ctrl+C jest przechwytywane przez `_interrupt`; w partii ustawia kod anulowania;
- klawisz kopiujący zaznaczenie może zostać zużyty na kopiowanie.

Źródła: `ui/app.py:289–326,529–535`.

### Stopka

Brak zwykłej podpowiedzi. W partii najniższy wiersz: `Okno zamknie się za {seconds} s · dowolny klawisz zamyka` — `ui/app.py:98,990–993`.

### Dół poza stopką

Końcowa kolejka i liczniki ukrytych wierszy jak A04. Po sukcesie bez ostrzeżeń nie powstaje osobny tekst `_result_message` — `ui/app.py:830–840`.

### Komunikaty

Końcowe etykiety postępu z A04, przede wszystkim `✓ Gotowe`. Odliczanie partii rozpoczyna się na 10 s — `ui/app.py:95,852–858`.

### Naruszenia

N31/R1: `dowolny klawisz zamyka` jest nieprawdziwe dla ↑↓, PgUp/PgDn, Home/End, które wcześniej przechwytuje przewijanie — `ui/app.py:317–319`.

## A06 — Wynik przetwarzania: MESSAGE z `_result_message`

### Klawisze i mysz

↑↓, PgUp/PgDn, Home/End przewijają tekst. Pozostałe zwykłe klawisze wracają; w partii zamykają. Ctrl+C i kopiowanie — wyjątki jak A05. Kółko przewija po trzy wiersze. Prawy przycisk wysyła Esc, więc wraca/zamyka — `ui/app.py:320–326,455–457`.

### Stopka

`↑↓ przewijanie · dowolny inny klawisz: powrót` — `_message_content`, `ui/app.py:1151`. W partii dodatkowo najniższe odliczanie ze wspólnego wiersza aplikacji.

### Dół poza stopką

Przewijany blok wyniku. Końcowe `Szczegóły: {_LOG_LOCATION}` jest częścią treści, nie przypiętym wierszem — `ui/app.py:1168`.

### Komunikaty

- `Przetwarzanie anulowane` — jeśli `result.cancelled`;
- `Wynik przetwarzania` — w pozostałych przypadkach;
- `{nazwa grupy}: {group.status.value}` — status jest surową wartością enum, nie polskim słownikiem;
- `{error_message}` — sanitizowany błąd backendu;
- `✓ Zachowano: {nazwa pliku}` — zarówno dla nowych `products`, jak i `preserved_products`;
- `{warning}` — sanitizowane ostrzeżenie backendu;
- `Szczegóły: {_LOG_LOCATION}` — względna lokalizacja logu.

Źródło wszystkich wzorców: `_result_message`, `ui/app.py:1154–1169`; lokalizacja logu `ui/app.py:60`.

### Naruszenia

N32/R3: `dowolny inny klawisz: powrót` pomija PgUp/PgDn/Home/End, które również przewijają, oraz kopiowanie zaznaczenia. N33/R3: `✓ Zachowano` wspólnie opisuje produkty nowo utworzone i wcześniej zachowane — `ui/app.py:1164–1165`. N31/R1 w odliczaniu partii.

## A07 — Ogólny komunikat / odmowa / błąd: MESSAGE

### Klawisze i mysz

Jak A06. Brak menu akcji i klikalnych wierszy wykonawczych.

### Stopka

`↑↓ przewijanie · dowolny inny klawisz: powrót` — `ui/app.py:1151`; w partii odliczanie ze wspólnego najniższego wiersza aplikacji.

### Dół poza stopką

Przewijana treść. Dla `_problem_text` kończy się lokalizacją logu. Najniższy wiersz katalog/wersja albo odliczanie.

### Komunikaty

Odmowy Auto — `_REFUSAL_MESSAGES`, `ui/app.py:101–105`:

- `Workspace nie zawiera materiału do uruchomienia`;
- `Żadna wykryta grupa nie jest gotowa do uruchomienia`;
- `Plan nie może zostać uruchomiony`.

Sugestie — `_REFUSAL_SUGGESTIONS`, `ui/app.py:108–115`:

- `Umieść plik wideo lub napisów w workspace i spróbuj ponownie`;
- `Usuń konflikty i zapewnij każdej grupie użyteczne napisy`.

Odmowy przygotowania przez rezydenta — `_prepare_resident_auto`:

- `Nie znaleziono gotowych odcinków` — `ui/app.py:782`;
- `Nie można przygotować wybranych odcinków` — `ui/app.py:787`;
- `Wszystkie odcinki są już gotowe` — `ui/app.py:789`.

Te trzy w normalnej ścieżce rezydenta trafiają do notice Przetwarzania, nie automatycznie do MESSAGE — `ui/app.py:751–760`.

Pozostałe:

- `Nie znaleziono materiału do przetworzenia` — przygotowanie Ręcznego, `ui/app.py:642`;
- `Błąd · {refusal_text(problem)}` — `_problem_text`, `ui/app.py:1204`;
- `Szczegóły: {_LOG_LOCATION}` — `ui/app.py:1212`;
- `{suggestion}` — sugestia błędu aplikacyjnego, po sanitizacji, `ui/app.py:1205–1211`;
- `{blocker.scope}: {blocker.message}` — dodatkowe blokery odmowy Auto, `ui/app.py:1191–1192`;
- komunikaty `prepare_retry` z M13 oraz wspólne odmowy z dodatku A.

Przed powstaniem panelu może wystąpić tekst konsolowy `Nie udało się połączyć z rezydentem AniShift. Sprawdź stan: anishift watch status.` — `anishift/cli/main.py:173`. Nie jest to ekran interaktywny MESSAGE.

### Naruszenia

N32/R3; N31/R1 w wariancie odliczania. N34/R3: `Workspace`, `grupa` i `użyteczne napisy` są pokazane bez wyjaśnienia wymaganej struktury lub konkretnej przyczyny niegotowości — `ui/app.py:101–115`. Nie tłumaczy się automatycznie nieznanych komunikatów backendu — `ui/app.py:1189–1195`.

## Rozbieżności dokumentacji z kodem — Ustawienia, Ręczny i wykonanie

1. „Potwierdza wyłącznie Enter” nie odpowiada obsłudze CONFIRM Ustawień. `anishift/cli/AGENTS.md:375–376` tak opisuje potwierdzenia. Kod dopuszcza także → — `ui/settings.py:910–911`. Podwójny klik rzeczywiście nie zatwierdza — `ui/settings.py:1815`.
2. Ogólna deklaracja kółka bez zmiany zaznaczenia dotyczy menu, ale nie edytorów listowych. Dokument: `anishift/cli/AGENTS.md:360–364`. Kod edytora zmienia `editor.selected` — `ui/settings.py:566–570`.
3. Opis Auto jako ekranu normalnego uruchomienia jest szerszy niż bieżące wejście produkcyjne. Home nie ma Auto; main zawsze przekazuje rezydenta; zaakceptowany `PlanPreview` jest oddawany przez `backend.start` do panelu Przetwarzanie — `ui/app.py:63–68,675–696,796–807`, `anishift/cli/main.py:175`.
4. Kontrakt „dowolny klawisz zamyka partię” ma wyjątki w routerze. Dokument: `anishift/cli/AGENTS.md:189–191`. Kod najpierw przechwytuje klawisze przewijania i kopiowania — `ui/app.py:289–324`.
5. Backspace podczas testu połączenia nie zachowuje się jak powrót. W zwykłych Ustawieniach jest aliasem powrotu, ale BUSY rozpoznaje tylko Esc i Ctrl+C — `ui/settings.py:552–557,789–796`.
6. Starsza uwaga o ręcznej edycji preferencji nie opisuje istniejącego UI. `anishift/config/AGENTS.md:3,30` mówi o plikach edytowanych ręcznie; `SettingsController` ma działające ścieżki zapisu przez fasadę — `ui/settings.py:690–700,1537–1547`.

## Niepewności i granice dowodów — Ustawienia, Ręczny i wykonanie

- Nie ma obserwacji runtime ani renderów. Warunki, teksty i routing potwierdzono w kodzie, nie przez uruchomienie panelu.
- Dynamiczne dane nie są zamkniętym słownikiem: nazwy plików, głosów, modeli, etykiety katalogowe, wyjątki, `PlanProblem.message`, ostrzeżenia i rezultaty backendu mogą zawierać dowolny sanitizowany tekst. Wskazano miejsca ich wstawiania; nie dopisano hipotetycznych komunikatów.
- Wspólny słownik `ui/state_texts.py` jest w dodatku A. Wskazanie jego użycia w Ręcznym nie przypisuje każdej odmowie biblioteki/subskrypcji nieudowodnionej drogi emisji.
- Lista dostępnych modeli i część opcji silników zależy od rejestrów i konfiguracji. Potwierdzono konstrukcję oraz filtrowanie list, bez odczytu konfiguracji runtime.
- Stare Auto/AUTO_DONE jest osiągalne przez API aplikacji z lokalnym wykonaniem, ale nie znaleziono produkcyjnej drogi Home → Auto ani wywołania `run_interactive(..., batch=...)` w kodzie `anishift/`.
- Ctrl+C w Ręcznym opisano według `ui/app.py`, nie tylko samego kontrolera. To istotna różnica dla faktycznego zachowania panelu.

## Tabela naruszeń N01–N34 — Ustawienia, Ręczny, Home i wykonanie

Tabela zachowuje lokalne identyfikatory obserwacji. Ma 34 wiersze: R1 = 8, R2 = 5, R3 = 21. Przy liczeniu unikalnych wzorców N01/N12 tworzą jedną grupę alternatywnych skrótów nawigacji, a N06/N25 jedną grupę `Enter/Space` zmieniającego produkt. Po scaleniu daje to R1 = 8, R2 = 3, R3 = 21, razem 32 wzorce w tej części. Nie liczy się każdego wystąpienia na kolejnej instancji pola. R3 jest oceną czytelności opartą na wskazanym tekście i braku objaśnienia w danym rendererze, nie wynikiem badania użytkowników.

| ID | Ekran / tekst | Reguła | Dowód |
|---|---|---|---|
| N01 | Menu Ustawień: `↑↓/Tab` | R2 | `ui/settings.py:52`, obsługa `ui/settings.py:798–802` |
| N02 | Menu Ustawień: `←→ · Enter · Esc` bez znaczeń | R3 | `ui/settings.py:52`, różne działania `ui/settings.py:815–825,729–760` |
| N03 | Tłumaczenie: `Top-p`, `Temperatura`, `PROMPT`, tokeny | R3 | `ui/settings.py:199–202`; render tylko etykiety/wartości `ui/settings.py:1691–1702` |
| N04 | Lektor: różne tempa i głośności bez objaśnienia | R3 | `ui/settings.py:220–234,1691–1702` |
| N05 | Wynik: `Enter/Space zmień` na akcjach i ostatnim produkcie | R1 | `ui/settings.py:55,827–858` |
| N06 | Wynik: `Enter/Space` | R2 | `ui/settings.py:55,836–838` |
| N07 | Reset `WYNIK` obejmuje cały preset | R3 | `ui/settings.py:1409–1413,1423–1432` |
| N08 | `recepty właściciela` | R3 | `ui/settings.py:1003` |
| N09 | `subs:` / `cover:` bez nazwania roli katalogu | R3 | `ui/settings.py:266–270,1721–1723` |
| N10 | `skonfigurowane · system` | R3 | `ui/settings.py:2017–2020` |
| N11 | Test połączenia: zwykła stopka przy blokadzie klawiszy | R1 | `ui/settings.py:552–553,789–796,1720` |
| N12 | SELECT/CONFIRM: `↑↓/Tab`, `Enter/→`, `Esc/←` | R2 | `ui/settings.py:61,892–911,2156–2176` |
| N13 | MULTI_SELECT: `Space zmień` na jedynym produkcie | R1 | `ui/settings.py:58,900–903` |
| N14 | Tekst/liczba/lista/adres: `Enter/Esc wróć` | R2 | `ui/settings.py:67` |
| N15 | `Enter/Esc wróć` zaciera walidację i porzucanie błędnego tekstu | R3 | `ui/settings.py:706–727,867–889` |
| N16 | Ogólne `Nieprawidłowa wartość` bez formatu/jednostronnej granicy | R3 | `ui/settings.py:1549–1556`; parser `ui/settings_editors.py:49–56` |
| N17 | Lista języków bez podpowiedzi separatora/kodów | R3 | `ui/settings.py:67,170–171,1824`; `ui/settings_editors.py:74–76` |
| N18 | Dodaj głos: `puste usuwa`, choć nie ma istniejącego głosu | R1 | `ui/settings.py:70,1298–1305` |
| N19 | Dwa różne resety `TŁUMACZENIE` o identycznym pytaniu | R3 | `ui/settings.py:1378,2040–2047` |
| N20 | Ręczny GROUPS: `Space wybierz` na wierszach akcji | R1 | `ui/manual.py:585–589,1113` |
| N21 | `End podgląd` tylko ustawia kursor | R3 | `ui/manual.py:594–595,1113` |
| N22 | `A wszystkie` przy częściowym zaznaczeniu odznacza wszystko | R3 | `ui/manual.py:590–591,1113` |
| N23 | Ręczny: `↑↓ · Enter · Esc` bez opisów | R3 | `ui/manual.py:74`, lokalne handlery ekranów |
| N24 | Ręczny PRODUCTS: `Enter/Space zmień` na `Zapisz/Wróć` | R1 | `ui/manual.py:77,744–769` |
| N25 | Ręczny PRODUCTS: `Enter/Space` | R2 | `ui/manual.py:77,751–756` |
| N26 | Identyczny tytuł wejścia źródła audio i gotowego miksu | R3 | `ui/manual.py:1245`, role `ui/manual.py:940–945` |
| N27 | `Sprawdzanie pliku…` podczas przygotowania planu/rezerwacji | R3 | `ui/manual.py:633–665,1257` |
| N28 | `… jeszcze N`: brak dostępu do ukrytych problemów i licznik zaniżony o jeden | R3 | `ui/manual.py:1278–1295`; klawisze `ui/manual.py:1045–1050` |
| N29 | Home podczas przygotowania: `↑↓ · Enter` bez działania | R1 | `ui/app.py:310–326,958–967` |
| N30 | Postęp: techniczne nazwy faz bez rozwinięcia | R3 | `ui/progress.py:84–112,755–757` |
| N31 | Partia: `dowolny klawisz zamyka`, lecz nawigacyjne przewijają | R1 | `ui/app.py:98,317–324`. Dodatkowa różnica działania: Ctrl+C bez zaznaczenia zamyka z kodem anulowania, zamiast zachować wynik zakończonej partii (`ui/app.py:304–309,335–339,529–532`); nie jest to osobno doliczone R1. |
| N32 | MESSAGE: „dowolny inny” mimo dodatkowych klawiszy przewijania/kopiowania | R3 | `ui/app.py:1151,289–324` |
| N33 | `Zachowano` obejmuje nowe i zachowane produkty | R3 | `ui/app.py:1164–1165` |
| N34 | Odmowy Auto: `Workspace`, `grupa`, `użyteczne napisy` | R3 | `ui/app.py:101–115` |

<!-- Część B: zakładka Anime, drugi przebieg 2026-10-11 -->


Stan badania: 2026-10-11, `work/tui/02-unified-tabs @ 49dd9ec`. Analiza statyczna kodu i testów, bez uruchamiania panelu, rezydenta ani testów. Śledzone pliki czyste; zastany nieśledzony `.opencode/`. Pierwsze `git status --short` zgłosiło odmowę dostępu do kilku katalogów `workspace/temp/pytest-*` podczas skanowania nieśledzonych plików; nie odczytywano ich zawartości. Kolejne sprawdzenie użyło `--untracked-files=no`.

Obowiązują konwencje oraz **K, F, G i Dodatek A** z sąsiedniego `inventory-2.md`. `ui/` = `anishift/cli/interactive/`, `app/` = `anishift/application/`. Każdy zapis `file:line` dotyczy wskazanego commita. `{…}` oznacza część zmienną, nie dosłowne nawiasy UI. Wspólne słowniki poniżej są częścią wszystkich ekranów odwołujących się do nich. Danych katalogowych, nazw plików i dowolnych sanitizowanych wyjątków nie można wyliczyć jako skończonego słownika.

Numeracja: B01 wyszukiwarka, B02 tytuły, B03 wpisy, B04 odcinki, B05 U08, B06 wydania, B07 pliki paczki, B08 zakres, B09 szczegóły/pomoc, B10 BUSY, B11 PROBLEM, B12 potwierdzenie niepewnego wydania, B13 szkic subskrypcji. B12 to osobna interakcja w stanie `PROBLEM`, B08/B09 to nakładki, a B05 to `EPISODES` z subskrypcją (`ui/anime.py:149-158,271-307,411-436,1201-1228`). Nie istnieje dodatkowy ekran pojedynczej oferty: I/P prowadzą do B06 (`ui/anime.py:1643-1657,1923-1931`).

## Wspólne uzupełnienia Anime

### K-Anime — różnice względem K-panel

- `↑↓`, `Home/End`, `PgUp/PgDn` przesuwają po nawigowalnych wierszach; ↑↓ zawijają, strony są ograniczane do krańców, rozmiar strony pochodzi z ostatniej klatki (`ui/anime_panel.py:145-169`). Kółko przesuwa widok o trzy wiersze bez zmiany kursora i kasuje notice; następna nawigacja klawiaturą dociąga do kursora (`ui/anime.py:778-804`).
- `Tab/Shift+Tab` przełączają zakładkę zawsze; ←→ tylko bez fokusu pola. Przy kontekście Subskrypcji przejście usuwa ten kontekst, zakres i zaznaczenia; przy zwykłym Anime `cancel()` rozmywa fokus i unieważnia odczyty, lecz nie kasuje wszystkich zachowanych danych (`ui/state.py:615-626,702-709`; `ui/anime.py:450-459,1090-1108`). `O` steruje automatem tylko gdy `accepts_text=False`; `M/U` nie otwierają Ręcznego/Ustawień w Anime (`ui/state.py:702-725`; `ui/anime.py:1116-1120`).
- `C` i `Ctrl+Insert` kopiują zaznaczony tekst albo pełny bieżący wiersz, nawet ucięty w tabeli; Ctrl+C bez zaznaczenia zachowuje powrót. W QUERY i zakresie C jest literą; Ctrl+Insert bez zaznaczenia pola/tekstu nic nie kopiuje. Pierwszeństwo ma zaznaczenie ramki, potem lokalne zaznaczenie Anime/pola (`inventory-2.md`, K-kopiowanie; `ui/anime.py:271-280`; `ui/anime_panel.py:120-143`). Kopiowanie wiersza to `AnimeRow.copy_text`, nie sam tytuł (`ui/anime_state.py:84-105`).
- Klik i dwuklik według K-mysz; dodatkowo klik `[ ]/[x]` ustawia wiersz i wykonuje Space. Drugie kliknięcie w checkbox to następne przełączenie, nie Enter. W zakresie checkbox staje się zwykłym kliknięciem wiersza (`ui/anime_view.py:174-188`; `ui/anime.py:806-818`; `ui/app.py:395-397`). PPM = Esc. Przeciąganie zaznacza tylko malowany tekst; pomija znaczniki, checkboxy, padding i stopkę. W B09/B11/B12 wiersze mają `opens=False`, więc dwuklik nie potwierdza (`ui/anime_view.py:88-94,270,302-331`).
- Esc/Backspace/Ctrl+C bez zaznaczenia oznaczają powrót, z wyjątkami pola B01/B08. Litery działań są niewrażliwe na wielkość; poza wyszukiwarką brak skrótów Ctrl+Z do cofania subskrypcji (`ui/anime.py:271-307`; `ui/anime_panel.py:78-92,171-186`).

### F-Anime — stopka i wspólny dół

F z `inventory-2.md` obowiązuje również tutaj. Stopki są nieklikalnym tekstem, nie przyciskami (`ui/anime_view.py:524-525,559-561`). Pełne segmenty poniżej mogą być pakowane w dwie linie i odrzucane od końca; globalnego limitu „najwyżej trzy akcje” sam `ScreenActions` nie wymusza (`ui/actions.py:32-59`).

**Odzyskanie partii:** na każdym ekranie poza QUERY, gdy istnieje `_pending_batch` i `_batch_running=False`, dotychczasowe Enter w stopce jest zastępowane przez `Enter sprawdź wynik`, a jeśli go nie było — dodawane na początku (`ui/anime.py:949-954`). Enter wtedy odtwarza dokładnie tę samą partię, przed zwykłą akcją ekranu (`:290-292`). Wyjątki: szczegóły mają własną stopkę C/Esc i własną wcześniejszą obsługę; zakres ma własną stopkę, ale Enter w aktywnym polu może zostać przechwycony przez odzyskanie. Bez fokusu najpierw go włącza. W czasie aktywnego workera partii zwykła stopka wraca, choć część akcji pozostaje zablokowana. Również aktywne QUERY z zachowaną partią może po Enter odtworzyć wynik zamiast wyszukać, choć jego stopka nadal mówi `Enter szukaj`: warunek handlera (:290) nie wyklucza QUERY, a warunek stopki (:951) wyklucza.

**D-Anime:** nad klawiszami stoi slot notice. Niepusty `snapshot.notice` wygrywa z opisem wiersza. W przeciwnym razie pokazuje pełny ucięty tytuł (o ile nie ma detail; w wydaniach także przy detail) lub `item.detail`; wydania mają dodatkową funkcję ujawniania ukrytych kolumn. Notice zajmuje najwyżej dwie linie, jedną w rozciągniętej tabeli, trzy na wydaniach; reszta kończy się wielokropkiem. Nad nim tylko odcinki mają `Zaznaczone: {N} ({numery/ranges})`; zakres zastępuje to polem `Zakres: {tekst}`. Brak zaznaczeń = pusty tekst podsumowania (`ui/anime_view.py:232-239,495-561`).

G obowiązuje dla statusu automatu i ramki katalog/wersja. **Nie należy automatycznie przenosić wszystkich notice G do Anime:** `_anime_body` rysuje `anime.render` i status, ale nie `StateController._notice` (`ui/state.py:1228-1231`). Dlatego np. rutynowe wyniki O/W/R i ogólne błędy workera State są zapisane, lecz nie wyświetlone w B01–B13; widoczne stają się tylko po odpowiednim przejściu albo jawnym `anime.refused` (odtwarzanie i `target_not_waiting`, `ui/state.py:503-515`).

### C-Anime — komunikaty przekrojowe

| Tekst | Źródło, kiedy i znaczenie |
|---|---|
| `Skopiowano zaznaczenie` / `Skopiowano wiersz` / `Nie udało się skopiować` | `ui/anime_panel.py:136-142`: rezultat próby schowka; ostatni oznacza brak `clip.exe`, timeout lub błąd procesu (`ui/anime_clipboard.py:14-31`). Bez wartości do skopiowania nie ma komunikatu. |
| `Powiększ terminal do 50 x 12` | `ui/anime_view.py:223-261`: szerokość <50 albo brak miejsca na dane według budżetu renderera; zastępuje treść Anime. |
| `Widok nieaktualny: odpowiedź przekracza limit` | `ui/anime.py:1395-1399`: odebrano `control_problem`, ustawia stale i notice, niezależnie od aktualnego ekranu. |
| `Widok nieaktualny · otwórz odcinki ponownie` | `ui/anime.py:293-296`: stale blokuje D/P/Enter; sprawdzenie następuje po polu i szczegółach, więc nie blokuje tych wcześniejszych ścieżek. |
| `Trwa wyszukiwanie wydań` | `ui/anime_panel.py:180-181,188-191`: D/P przy niepustym `view.searching`; obejmuje również oczekującą partię lub wysyłkę wyboru, nie tylko faktyczne wyszukiwanie. |
| `Trwa partia · Enter sprawdź wynik` | `ui/anime.py:598-600,1319-1322`: próba nowego zamówienia odcinków albo dodania szkicu z odcinkami przy istniejącej partii. Zwykły D na EPISODES jest często przechwycony wcześniej przez tekst powyżej. |
| `Wynik nieznany · Enter sprawdź wynik` | `ui/anime.py:1348-1359`: nieotrzymana pewna odmowa/odpowiedź partii; zachowuje ID i payload do odtworzenia. |
| `Partia trwa · Enter sprawdź wynik` | `ui/anime.py:1479-1508`: po maksymalnie 180 s obserwacji partia nadal `accepted`; to nie dowód błędu pobrania. |
| `Nie zlecono · {odmowa}` | `ui/anime.py:1352-1356`: potwierdzona odmowa partii przez ownera; kasuje pending. Odmowa według słownika E i Dodatku A wcześniejszego raportu. |
| `Nie zlecono {E…} · zaznacz je ponownie` | `ui/anime.py:1454-1462`: partia przerwana, wymienia klucze bez potwierdzonego przyjęcia. |
| `Zlecono {numery}`; `Nie zlecono {numery: przyczyny}`; `Zlecono {numery} · nie zlecono {numery: przyczyny} · I wydania` | `ui/anime_panel.py:225-243`, wywołanie `ui/anime.py:1412-1438`: sumowane wyniki odcinków bieżącej partii; przy każdej odmowie końcowy człon `I wydania`, także bez sukcesów. Przyjęcie nie oznacza pobrania ani gotowego lektora. |
| `Nie zlecono {zakres: przyczyna}`; przy braku wyniku przyczyna `przerwano` | `ui/anime.py:1361-1373`: zbiorczy wynik partii szkicu, grupowany według przyczyny; trafia na listę Subskrypcji, nie stanowi nowego ekranu Anime. |

## B01 — Wyszukiwarka (QUERY), również dodawanie z Subskrypcji

### Klawisze i mysz

K-pole i K-Anime. Początkowo w zwykłym Anime pole bez fokusu; znak, Space, wklejenie lub Backspace aktywuje i edytuje, `/` albo Enter tylko aktywuje. Z fokusem Enter wyszukuje niepusty tekst, Esc/Ctrl+C bez zaznaczenia rozmywa pole, kolejny Esc/Ctrl+C wraca do Home albo listy Subskrypcji. Backspace nigdy nie wychodzi. D lub `/` z listy Subskrypcji otwiera QUERY już z fokusem; Enter pustej listy jest cichym aliasem tego wejścia. Tekst zapytania pozostaje. `O`, `?`, `S`, `D`, `C`, `M`, `U` są wpisywanymi znakami, nie akcjami aplikacji (`ui/anime.py:366-374,1122-1161`; `ui/state.py:468-471,702-711`). Klik linii pola ustawia fokus/kursor; dwuklik pola nie wyszukuje; PPM rozmywa lub wraca, kółko nie ma listy do przewinięcia.

### Stopka

`Enter szukaj · Esc wróć` niezależnie od fokusu i pustego tekstu (`ui/anime.py:956-959`; `ui/actions.py:45-51`; test `tests/cli/test_panel_keys.py:566`). Bez `?`. G może pokazać `O włącz`/`O wyłącz` mimo tekstowego znaczenia O.

### Dół ekranu poza stopką

D-Anime: brak tytułu/ukrytych kolumn i podsumowania; możliwe pozostawione notice, kopia lub komunikat stale. Pole w środku pod `ANIME`, bez okruszka (`ui/anime_view.py:292-299`; `ui/anime.py:265-269`). G. Wyszukiwanie z Subskrypcji podświetla zakładkę Subskrypcje (`ui/state.py:1287-1290`).

### Komunikaty

C-Anime i status G. Po zatwierdzeniu przejście B10 (`Szukam tytułu…`, potem `Wczytuję wpisy…`, ewentualnie `Wczytuję odcinki…`); brak wyników to B11 `Nie znaleziono tytułu`, nie pusta tabela (`ui/anime.py:1933-1945,1975-1977,1990,2027-2029`). Same pole i nagłówek nie mają dodatkowej instrukcji po polsku.

### Naruszenia

R1-QUERY: Enter szukaj przy braku fokusu tylko aktywuje, a pustego query nie wyszukuje. R1-O-FIELD: O w statusie wpisuje literę. R3-WAIT (G). R2 nie stwierdzono.

## B02 — Tytuły (TITLES)

### Klawisze i mysz

K-Anime. Enter wczytuje franczyzę/otwiera wpisy; na zapowiedzi tylko notice. S przygotowuje B13, `/` otwiera QUERY z fokusem, `?` B09, C kopiuje. Esc/Backspace/Ctrl+C wraca do QUERY. D/I/P/A/Z nie wykonują tutaj zamówienia ani wyboru. Klik wybiera, dwuklik = Enter, PPM wraca, kółko przewija (`ui/anime.py:489-512,1176-1183,1512-1526`; `ui/anime_panel.py:171-204`). Lista jest pomijana, jeżeli wszystkie trafienia należą do pobranych wpisów franczyzy (`ui/anime.py:2003-2049`).

### Stopka

`Enter wybierz · S subskrybuj · ? więcej · Esc wróć`; w pomocy `/ szukaj · C kopiuj` (`ui/anime.py:125-129,964-966`). F-Anime odzyskanie partii może zastąpić Enter. Ciche aliasy powrotu i kopiowania z K-Anime.

### Dół ekranu poza stopką

D-Anime: notice, a bez niego pełny ucięty tytuł. Brak podsumowania zaznaczeń i oddzielnego ujawniania schowanych kolumn. G; brak okruszka (`ui/anime.py:265-269`; `ui/anime_view.py:495-547`).

### Komunikaty

Kolumny `Premiera`, `Tytuł`, `Typ`, `Status` (`ui/anime_view.py:335-339`). Statusy `zakończone`, `w emisji`, `zapowiedź`, `przerwa w emisji`, `anulowany`, `—` odpowiadają FINISHED/RELEASING/NOT_YET_RELEASED/HIATUS/CANCELLED/UNKNOWN; format MOVIE pokazuje `Film`, inne formaty surowy skrót (`ui/anime_rows.py:44-64,209-210`). `Zapowiedź · odcinków jeszcze nie ma · S subskrybuj` po Enter na NOT_YET_RELEASED (`ui/anime.py:121,1514-1516`). `Ten wpis nie ma przyszłych odcinków` po S i niekwalifikującej się liście (`ui/anime.py:118,531-540`). C-Anime; błędy odczytu przechodzą do B11, operacje do B10.

### Naruszenia

R1-ANNOUNCED i R1-S-FINISHED; R3-MORE/R3-WAIT. R2 nie stwierdzono.

## B03 — Wpisy franczyzy (ENTRIES)

### Klawisze i mysz

K-Anime. Enter otwiera odcinki wybranego wpisu, na zapowiedzi tylko notice; S przygotowuje B13, `/` QUERY, `?` B09, C kopiuje. Esc/Backspace/Ctrl+C wraca do TITLES, jeśli lista tytułów była pokazana, inaczej QUERY. Klik wybiera, dwuklik Enter, PPM wraca, kółko przewija (`ui/anime.py:1230-1279,1563-1579`). Pojedynczy kompletny wpis może ominąć ENTRIES; przy pierwszym wyszukiwaniu tylko wydany (`ui/anime.py:1543-1549,2014-2019`).

### Stopka

`Enter odcinki · S subskrybuj · ? więcej · Esc wróć`; pomoc `/ szukaj · C kopiuj`; F-Anime odzyskanie partii (`ui/anime.py:964-966`). Ciche powroty/kopiowanie jak K-Anime.

### Dół ekranu poza stopką

D-Anime i G. Przy niekompletnej franczyzie notice `Lista niepełna` ma pierwszeństwo nad pełnym uciętym tytułem, dopóki nie ma jawnego notice (`ui/anime.py:927-928`). Bez podsumowania i bez okruszka.

### Komunikaty

Kolumny/statusy/formats jak B02, tym razem `ui/anime_rows.py:69-80`. `Lista niepełna` (`ui/anime.py:928`) oznacza `franchise.complete=False`, nie pustą listę. `Zapowiedź · odcinków jeszcze nie ma · S subskrybuj` (`ui/anime.py:121,1567-1569`), `Ten wpis nie ma przyszłych odcinków` (`:118,537-540`), C-Anime. B10/B11 dla odczytu.

### Naruszenia

R1-ANNOUNCED, R1-S-FINISHED; R3-MORE/R3-WAIT. R2 nie stwierdzono.

## B04 — Odcinki (EPISODES bez subskrypcji)

### Klawisze i mysz

K-Anime. Space zaznacza/odznacza kwalifikujący się wiersz; A przełącza wszystkie kwalifikujące się; Z otwiera B08, jeśli nie ma `view.searching`. D zamawia zaznaczone, a bez zaznaczeń odcinek pod kursorem (maks. 100), pozostając na liście. Gotowe/pobrane/nieudane, lecz nieaktywne odcinki też mogą być zamówione ponownie. Nieemitowane i aktywne bez `attempt` są wykluczone (`ui/anime_state.py:206-226`; `ui/anime_panel.py:171-204`; `ui/anime.py:1319-1337,1464-1469`).

I otwiera B06 dla kursora. P otwiera B06 z `repeat=True` tylko jeśli status istnieje i jest inny niż `not_ordered` albo ma admission ID, odcinek jest wyemitowany i jest resident; przy `searching` tylko notice. Enter odtwarza gotowy wynik z `set_id`, wybiera plik nierozstrzygniętej paczki z admission ID, a na pozostałych odcinkach działa jako **cichy alias I**. S przygotowuje B13, `/` QUERY, `?` B09. Esc/Backspace/Ctrl+C wraca do ENTRIES albo do pominiętego poziomu TITLES/QUERY. Mysz: checkbox=Space, klik wybiera, dwuklik=Enter, kółko przewija, PPM wraca (`ui/anime.py:1262-1317,1643-1645`; `ui/state.py:713-724`). Nie ma akcji usuwania/anulowania odcinka tutaj.

### Stopka

Zwykle `Space zaznacz · D pobierz · S subskrybuj · ? więcej · Esc wróć`. Na gotowym `set_id` początek `Enter obejrzyj · `; na nierozstrzygniętej paczce `Enter wskaż plik · `. Bez tych danych Enter pozostaje cichym I. Pomoc: `I wydania · Z zakres · A wszystkie · P ponownie · / szukaj · C kopiuj`. F-Anime replay może podmienić Enter (`ui/anime.py:977-1003`; test `tests/cli/test_panel_keys.py:495-503,569`).

### Dół ekranu poza stopką

Podsumowanie `Zaznaczone: {N} ({1-3, 5…})` liczy zaznaczone istniejące wiersze i kompresuje sąsiednie numery, a nie wszystkie zadania ownera (`ui/anime_view.py:484-507`). Nad klawiszami D-Anime: notice, a bez niego detail lub pełny tytuł. Nie ma `_unshown` dla EPISODES, więc pełny ucięty Stan nie jest osobno ujawniany. G. Okruszek `Anime › {tytuł} ({rok lub —})` (`ui/anime.py:2122-2126`).

### Komunikaty

- Kolumny `Nr`, `Tytuł`, `Emisja`, `Stan` (`ui/anime_view.py:369-375`); domyślne nazwy `Film` / `Odcinek {n}` (`ui/anime_rows.py:111-113`); Stan to pełny słownik E poniżej, a podczas wysłanej partii `{spinner} szukam` (`ui/anime_view.py:378-382`).
- `Nie znam odcinków tego wpisu` — brak listing/shown, nieznane numery (`ui/anime.py:1029-1033`).
- `Brak terminów emisji (AniList) · ponów za {N} s` / `Brak terminów emisji (AniList) · wróć i otwórz ponownie` — schedule_warning, termin z blokady lub listing; render nie ponawia sieci (`ui/anime.py:1044-1049`).
- `Nie ustalono pliku w paczce · Enter wskaż plik` — reason EPISODE_FILE_UNRESOLVED (`ui/anime_rows.py:105-106`).
- `E{n}: termin emisji niepotwierdzony (ani.zip)` — data zastępcza, o ile wcześniejszy detail paczki nie wygra (`ui/anime_rows.py:107-108`).
- `E{n} jeszcze nie wyemitowano` — odmowa zaznaczenia/pobrania przyszłego odcinka (`ui/anime_rows.py:117`; `ui/anime.py:1333,1636-1638`). `W toku · X anuluj w Przetwarzaniu` — blokada aktywnego odcinka (`ui/anime_texts.py:51`; `ui/anime_rows.py:117`).
- `Limit: 100 odcinków | Z zmień zakres` — panel odrzuca >100 wybranych (`ui/anime_panel.py:196-198`); wariant kontrolera z ` · ` zamiast ` | ` (`ui/anime.py:1324-1326`) istnieje, ale normalny D przechodzi najpierw przez panel.
- `Szukam wydań…` — uruchomienie partii (`ui/anime.py:1335`); C-Anime obejmuje wyniki, odzyskanie i blokady.
- `Zlecono E{n}` — sukces jawnego wyboru wydania (`ui/anime.py:1801,1851-1867`); `Wybrano plik` — sukces wyboru paczki (`:1849`).
- `Brak mapowania` — lokalna ścieżka `_start_offers` bez listing (`ui/anime.py:1633-1635`); zwykłe `_episode_key` bez listing kończy się wcześniej (:1282-1284), więc brak dowodu zwykłej osiągalności tego notice.
- `Pobieranie jest niedostępne w tej sesji` — D bez resident (`ui/anime.py:1307-1309`; `ui/anime_texts.py:78`). Odmowa odtwarzania przez `anime.refused` używa Dodatku A-biblioteka/A-kontrola (`ui/state.py:511-515`). S może zwrócić `Ten wpis nie ma przyszłych odcinków` jak B02.

### Naruszenia

R1-EP-ELIGIBILITY, R1-PENDING, R1-P-NEW, R1-S-FINISHED, R1-STALE, R1-STATE-BUSY (odtwarzanie); R3-MORE/R3-WAIT i techniczne etykiety E. R2 nie stwierdzono.

## B05 — U08: szczegóły subskrypcji, lista odcinków i dodatki

### Klawisze i mysz

Wszystkie akcje B04, dodatkowo W wstrzymuje/wznawia subskrypcję, R sprawdza, X/Delete usuwa bez pytania i wraca na listę Subskrypcji. **Cichy alias F=R**, ale Space nadal zaznacza odcinek, nie jest aliasem W. T działa tylko przy `polish_wait_until` wskazanego odcinka: wysyła `subscription_check` z numerem. S otwiera wariant już subskrybowany B13. `/` czyści starą subskrypcję i zaczyna wyszukiwanie w kontekście Subskrypcji. Esc/Backspace/Ctrl+C bez nakładki wraca na listę. Ctrl+Z działa dopiero na liście Subskrypcji (`ui/anime.py:411-459`; `ui/state.py:489-515`).

Nagłówek dodatków i specials nie są nawigowalne; powiązane OVA/SPECIAL są: Enter/dwuklik otwiera ich odcinki, usuwa kontekst subskrypcji i przechodzi do zwykłego Anime. I/P na dodatku nie otwierają wydań. Checkbox dodatku jest pokazywany, lecz Space nie zaznacza (`ui/anime_rows.py:121-152`; `ui/anime.py:1073-1088,1287-1291`; `ui/anime_view.py:448-451`). Klik/kółko/PPM według B04.

### Stopka

`Space zaznacz · D pobierz · W wstrzymaj · ? więcej · Esc wróć`; gdy `row.paused`, `W wznów`; gdy kursor ma `polish_wait_until`, W w stopce zastępuje `T pobierz teraz`, a W przenosi się do pomocy. Opcjonalny początek: `Enter obejrzyj`, `Enter wskaż plik` lub na powiązanym dodatku `Enter otwórz`. Pomoc: W jeśli ukryte, `R sprawdź teraz · X usuń · I wydania · Z zakres · A wszystkie · P ponownie · S subskrybuj · / szukaj · C kopiuj` (`ui/anime.py:977-1003`). F-Anime replay; złote stringi `tests/cli/test_panel_keys.py:573-574,1962`.

### Dół ekranu poza stopką

Podsumowanie zaznaczeń jak B04. Okruszek `Subskrypcje › {pełny tytuł}` i nad tabelą `{row_state.text} · odcinki {done/count} · gotowe {N}`. Notice bez komunikatu użytkownika składa: ostatnie sprawdzenie, pełny stan jeśli różni się od krótkiego, linię PL, powody `notices`, obejrzane przed subskrypcją; puste człony pomijane. Te fakty wygrywają z fallbackiem tytułu/detail odcinka. PL i notices wybierają **osobno** odcinek kursora spełniający warunek albo najniższy numer spełniający swój warunek, więc mogą dotyczyć różnych odcinków (`ui/anime.py:670-743`). Notice jest ucinane do budżetu D-Anime. G pozostaje odrębną linią automatu.

### Komunikaty

B04 + pełny słownik S poniżej. `Sprawdzam…` po R/F/T (`ui/anime.py:430-432`); `Ostatnie sprawdzenie {HH:MM lub —}: {check_text}` (`:737-743`), bez 10-sekundowego wygaszania w tej funkcji. `E{n} {polish_line}` (`:708-712`), `E{n}: {notice_text…}` (`:714-716`; `ui/subscription_texts.py:257-260`). `Dodatki tego sezonu · pobierasz je osobno z listy wpisów` i stan `Enter otwórz` (`ui/anime_rows.py:128,147`). Numerów może być więcej niż zna katalog: dołączane są brakujące `first_target…last_target` (`ui/anime.py:1052-1067`).

`Ten odcinek już nie czeka na polskie napisy` z Dodatku A-subskrypcje jest jawnie kierowane do Anime, a stany odcinków odczytywane ponownie (`ui/state.py:503-509`; `ui/anime.py:1870-1874`). Błędy odtwarzania analogicznie. Pozostałe odmowy W/R/O zapisane jedynie w State nie są tu renderowane (F-Anime); usunięcie kończy na S01 poprzedniego raportu z jego komunikatami.

### Naruszenia

Jak B04 poza R1-S-FINISHED (S może pokazać istniejącą subskrypcję), dodatkowo R1-EXTRA, R1-STATE-BUSY, R3-CATALOG/R3-CHECK/R3-PROPOSAL ze słownika S. R2 nie stwierdzono.

## B06 — Wydania (CANDIDATES / RELEASES), również puste i doładowywane

### Klawisze i mysz

K-Anime. Space przełącza jedno kwalifikujące się wydanie; nowy wybór usuwa poprzedni. D wybiera zaznaczone, inaczej pod kursorem; `supported=False` nie pobierze. Niezgodność/niepewność wymaga B12. **Enter i dwuklik niczego nie wybierają ani nie pobierają**, poza odzyskaniem partii F-Anime. `?` B09, `/` QUERY, C kopiuje; Esc/Backspace/Ctrl+C wraca do odcinków/U08 i unieważnia ofertę. Klik checkbox=Space, klik tekstu ustawia kursor, kółko przewija, PPM wraca (`ui/anime_state.py:206-219`; `ui/anime.py:1230-1271,1757-1781`). A/Z/I/P/S nie mają normalnej akcji wydań; P podczas blokady `searching` daje tylko notice.

Kursor początkowo śledzi `*` sugerowanego wydania, po ruchu jest zachowywany według hasha. Lista filtruje niezgodne, z zerowymi seedami i część niższych jakości; przy dostępnym MATCH zostają MATCH, zatem brak wiersza nie oznacza braku wyniku surowego (`ui/anime.py:1720-1755`; `app/episode_selection.py:637-649`). Nie ma osobnego ekranu „oferta”.

### Stopka

`Space zaznacz · D pobierz · ? więcej · Esc wróć` zawsze, także przy wierszu `Szukam…` / `Brak wydania`. Pomoc `/ szukaj · C kopiuj` (`ui/anime.py:969-970`). Replay jak F-Anime. Nie ma Enter dla pobrania.

### Dół ekranu poza stopką

Brak `Zaznaczone…` dla wydań. Trzy wiersze notice: jawny komunikat, inaczej ostrzeżenie powtórki; dopiero bez nich `_unshown`: ukryte kolumny jako `obraz`, `rozmiar`, `język`, `seedy`, pełna ucięta `pewność`, ucięta nazwa, `z paczki: …`; gdy nic ukrytego, pełny detail. Notice/ostrzeżenie może zatem zasłonić pełną nazwę (`ui/anime_view.py:528-547`; `ui/anime.py:923-926`). Nad tabelą `offer.status`, ostrzeżenie nieznanego poprzednika albo `szukam jeszcze: …`; ostatnie ma najwyższy priorytet (:931-933,1016-1021). G pod stopką.

### Komunikaty

- `Wydanie`, `Obraz`, `Rozmiar`, `Język`, `Seedy`, `Jakość`, `Pewność` — kolumny (`ui/anime_view.py:340-357`). `*` to sugestia, `!` to werdykt inny niż MATCH (`:452-453`). Jakość jest liczbą zaokrągloną, pewność procentem lub `?`, przy konflikcie krótką etykietą; pełny słownik R poniżej (`ui/anime_releases.py:176-201,287-291`; `app/episode_selection.py:614-621`).
- `Szukam…` / `Brak wydania` — zastępczy wiersz pustej listy zależny od trwającego pierwszego odczytu (`ui/anime_releases.py:201`). Space/D na nim mogą pokazać mylący fallback `Zlecono | P pobierz ponownie` (`ui/anime_state.py:108-114`; panel :199-201).
- `szukam jeszcze: {źródła}` / `szukam jeszcze: uzupełnienia spisów` — istnieje częściowa oferta, trwa jej uzupełnianie (`ui/anime.py:931-933`).
- `brak numeracji` — niepotwierdzona numeracja celu (`app/acquisition.py:1175,1231`). `Wszystkie źródła wyłączone (Ustawienia)` / `Brak wyników — źródła niedostępne` — warunki `offer_status` (`app/episode_search.py:278-288`), włączane jako `offer.status` (`ui/anime.py:1018`).
- `E{n} może być już zlecony · Obecne pliki zostają` / `Obecne pliki zostają` — konflikt lub wcześniejsze przyjęcie; `Nie wiem, które wydanie pobrano poprzednio — może to być to samo` — `unknown_previous` (`ui/anime_releases.py:28,212-221`). Ostatnie może jednocześnie znaleźć się nad tabelą i w notice, ale to nie duplikat **stopki** R2.
- `z paczki · {plik}` / `z paczki · E{n} · {wydanie}` oraz `z paczki: {wydanie}` — nazwa pliku/paczki (`ui/anime_releases.py:183,198,230-234`). `PL`, `EN`, `—` — deklaracje języków (`:242-253`).
- `Wysyłam…` — trwa jawny wybór (`ui/anime.py:112,1780`). `Trwa partia · po jej zakończeniu otwórz wydania ponownie` — kontroler odmawia wyboru przy pending (:1762-1764); panel zwykle blokuje wcześniej. C-Anime, słownik R (reason/detail) i E (odmowy, zwykle już na B11).

### Naruszenia

R1-RELEASE-EMPTY, R1-RELEASE-UNSUPPORTED, R1-PENDING, R1-STALE; R3-MORE/R3-WAIT, R3-FALSE-ORDER, R3-TECH-RELEASE, R3-CALIBRATION. R2 nie stwierdzono w stopce.

## B07 — Wybór pliku nierozstrzygniętej paczki (FILES)

### Klawisze i mysz

K-Anime. Enter wybiera dokładny plik z zachowanej mapy/revizji, uruchamia wysyłkę i po sukcesie wraca na odcinki. `?` B09, `/` QUERY, C kopiuje; Esc/Backspace/Ctrl+C wraca do odcinków/U08. Klik wybiera, dwuklik=Enter, kółko przewija, PPM wraca. Brak zaznaczeń wielokrotnych, D/Space/A/P/I/Z/S bez akcji plikowej (`ui/anime.py:1230-1271,1803-1867`). Ciche powroty i Ctrl+Insert według K-Anime.

### Stopka

`Enter wybierz · ? więcej · Esc wróć`, pomoc `/ szukaj · C kopiuj`; nawet gdy zwrócona lista plików pusta (`ui/anime.py:967-968,1830-1833`). F-Anime replay może podmienić Enter.

### Dół ekranu poza stopką

D-Anime: notice albo pełny ucięty wiersz ścieżki/rozmiaru, bez podsumowania i schowanych kolumn. Okruszek wpisu Anime; G. Lista ma jedną kolumnę bez nagłówka (`ui/anime_rows.py:83-85`; `ui/anime_view.py:302-332`).

### Komunikaty

Wiersz `{ścieżka} · {rozmiar z separatorem tysięcy} B` (`ui/anime_rows.py:85`). `Lista plików zmieniła się · wybierz ponownie` po `file_map_changed`: pobiera nową listę, resetuje kursor i zostaje w FILES (`ui/anime.py:1812-1827,1843-1846`). C-Anime. `Wczytuję pliki…` / `Wysyłam…` w B10, `Wybrano plik` dopiero na B04/B05; inne błędy B11 (`ui/anime.py:1809,1835,1847-1849`). Nie ma dedykowanego polskiego tekstu pustej listy plików.

### Naruszenia

R1-FILES-EMPTY, R1-STALE; R3-MORE/R3-WAIT. R2 nie stwierdzono.

## B08 — Edytor zakresu (Z na B04/B05)

### Klawisze i mysz

K-pole. Z otwiera puste pole tylko przy braku `searching`. Enter stosuje zakres zastępując zaznaczenia; Esc/Ctrl+C bez zaznaczenia zamyka bez zastosowania; Backspace edytuje. Litery działań wpisują tekst. Tab przełącza zakładkę; w zwykłym Anime zachowuje obiekt zakresu, lecz gasi fokus, przy U08 usuwa cały kontekst i zakres. ←→ z fokusem edytuje, bez fokusu przełącza zakładkę. Po powrocie zwykłego Anime Enter może najpierw tylko przywrócić fokus (`ui/anime.py:1090-1095,1122-1147`; `ui/state.py:615-626,706-711`). Klik pola ustawia kursor. Klik checkboxa jest zwykłym wyborem wiersza; dwuklik wiersza generuje Enter, czyli może zastosować zakres, nie otworzyć wydania. PPM anuluje, kółko przewija tabelę (`ui/anime.py:813-814`; `ui/anime_panel.py:94-103`).

Parser przyjmuje `1,3,7.5`, `1-4`, `5-`, białe znaki przy członach; końce muszą istnieć w kolumnie numerów, kolejność nie może być odwrotna, wybór pomija niekwalifikujące się wiersze. Dopuszcza Decimal, ale produkcyjne zwykłe odcinki mają int; Film ma w kolumnie `Film`, więc nie jest numerycznym celem zakresu (`ui/anime_state.py:228-258`; `ui/anime_rows.py:112`).

### Stopka

`Enter zastosuj · Esc anuluj` bez pomocy (`ui/anime_view.py:559-561`). G nadal może pokazywać O. Gdy zachowana pending partia już nie jest obserwowana, globalna obsługa Enter w kontrolerze wyprzedza zastosowanie zakresu (`ui/anime.py:279-292`).

### Dół ekranu poza stopką

W miejscu podsumowania `Zakres: {tekst}` z klikalnym `TextInput`; pod nim notice, potem stopka, G. Tabela i dotychczasowe zaznaczenia pozostają do prawidłowego zatwierdzenia (`ui/anime_view.py:498-525`; `ui/anime_state.py:228-238`).

### Komunikaty

`Zakres: podaj 1,3,7.5 albo 5-` przy błędnej składni, brakującym końcu lub odwrotnej kolejności; pole pozostaje otwarte (`ui/anime_state.py:228-234`). Sukces zamyka pole i czyści notice, bez osobnego potwierdzenia. B04/B05 (stany, harmonogram, fakty U08), C-Anime (kopiowanie i zdarzenia partii) oraz G nadal mogą być widoczne.

### Naruszenia

R1-O-FIELD, R1-RANGE-ENTER i R1-RANGE-FILM; R3-RANGE-FRACTION, R3-WAIT. R2 nie stwierdzono.

## B09 — Szczegóły wiersza i pomoc (`?`)

### Klawisze i mysz

Otwierane z B02–B07 i B13. ↑↓/PgUp/PgDn/Home/End nawigują po zawiniętych wierszach tekstu, nie po źródłowej liście. Kółko przewija bez zmiany wskazanego wiersza. C/Ctrl+Insert kopiuje wskazany wiersz tekstu lub zaznaczenie, Ctrl+C bez zaznaczenia zamyka; Esc/Backspace/`?` zamyka. Klik ustawia tekstowy wiersz, dwuklik tylko wskazuje (bez Enter), PPM zamyka (`ui/anime.py:282-288,934-947`; `ui/anime_panel.py:120-169`; `ui/anime_view.py:93-94,270`). Tab/←→ przełączają zakładkę zgodnie K-Anime; zwykły `cancel()` nie zeruje `_details_open`, więc po powrocie zwykłego Anime szczegóły mogą pozostać.

Obsługa szczegółów nie jest tym samym co blok pomocy State: Enter/I/P/S i `/` idą do `_panel_action`, używając zapamiętanego źródłowego kursora (`_adopt_view_input` wraca od razu przy details). `/` zmienia źródłowy screen na QUERY, S rozpoczyna szkic, Enter wykonuje źródłową główną akcję, I/P działają na źródłowym odcinku z warunkami B04. Flaga szczegółów nie jest tu automatycznie zamykana. D/Space/A/Z są odfiltrowane przez `AnimeScreen.DETAILS`; **W/R/F/X/Delete/T U08 nie trafiają do `_subscription_key`**, bo wcześniejsza gałąź szczegółów wraca z `handle_key` (`ui/anime.py:282-288,748-750,850-869`; `ui/anime_panel.py:171-204`). O przechwytuje State poza polem. To różnica między opisem pomocy a faktyczną dostępnością.

### Stopka

`C kopiuj · Esc wróć`, bez `? więcej` i bez replay Enter (`ui/anime.py:947`; `ui/actions.py:45-51`). Ciche zamknięcie `?`, Backspace, Ctrl+C bez zaznaczenia; Ctrl+Insert jako kopia.

### Dół ekranu poza stopką

Nie ma podsumowania zaznaczeń ani osobnych kolumn. D-Anime: notice, inaczej ewentualny pełny ucięty wiersz szczegółów. G. Fakty subskrypcji są w treści i mogą pozostać również w kontekstowym notice/statusie utworzonym wcześniej w `_sync_view` (`ui/anime.py:923-947`).

### Komunikaty

Treść: wszystkie fakty U08, następnie `item.copy_text`, `item.detail`, potem `Ten ekran` z akcjami **źródłowego** ekranu i `Wszędzie` z F wcześniejszego raportu; przy braku item nazwa `Anime` (`ui/anime.py:934-945`; `ui/actions.py:62-70`). Copy-text zawiera etykiety `Rozmiar: {…}`, `Jakość: {…}`, `Pewność: {…}` (`ui/anime_state.py:84-105`). E, S, R i komunikaty źródłowego ekranu są integralną częścią tego widoku. Katalogowe opisy/tytuły to dane, nie stały polski słownik. C-Anime/G.

### Naruszenia

R1-DETAIL-ACTIONS (podpowiedzi w treści pomocy, nie dolnej stopce), R3-TECH-RELEASE/R3-CALIBRATION przy wydaniach, R3-CATALOG/R3-CHECK/R3-PROPOSAL przy U08, R3-WAIT. Stopka C/Esc nie dubluje akcji: R2 nie stwierdzono.

## B10 — BUSY: odczyt katalogu, dodawanie i wysyłka pliku

### Klawisze i mysz

Esc/Backspace/Ctrl+C bez zaznaczenia wraca do `_busy_return`, unieważnia wynik odczytu; dla `sending=True` nie anuluje wysłanej mutacji. Pozostałe lokalne działania ignorowane, poza kopiowaniem przez wcześniejszą obsługę. Gdy widok jest BUSY-listą, C/Ctrl+Insert może skopiować wiersz komunikatu; w wariancie QUERY nie ma kopiowania wiersza. O i zmiana zakładki z K-Anime nadal działają (`ui/anime.py:271-280,1185-1199,1947-1957`). BUSY jest nienawigowalnym wierszem: klik/dwuklik nie otwierają, kółko nie ma kolejnych danych, PPM wraca (`ui/anime.py:1022-1023`; `ui/anime_view.py:311-330`).

### Stopka

`Esc wróć` (`ui/anime.py:960-961`; `ui/actions.py:45-51`). C jest tylko w `actions.more` BUSY spoza QUERY, lecz `?` nie jest obsługiwane, więc nie staje się widoczną pomocą. F-Anime może dodać `Enter sprawdź wynik`, jeśli równolegle istnieje nieobserwowana partia.

### Dół ekranu poza stopką

Brak podsumowania, kolumn i ujawnienia tytułu. D-Anime może zachować wcześniejsze notice, ponieważ `_start_work` nie czyści `_notice` (`ui/anime.py:1947-1957`). Przy powrocie QUERY renderer pokazuje nagłówek ANIME i zdanie w miejscu pola; w pozostałych przypadkach jedną linię BUSY z kontekstem (`ui/anime.py:879,900`; `ui/anime_view.py:292-296,314`). G.

### Komunikaty

| Tekst | Źródło i znaczenie |
|---|---|
| `Szukam tytułu…` | `ui/anime.py:106,1944`: zapytanie katalogu. |
| `Wczytuję wpisy…` | `ui/anime.py:109,1525,1990`: odczyt franczyzy. |
| `Wczytuję odcinki…` | `ui/anime.py:400,500,1578,2028`: odcinki U08, szkicu lub wpisu. |
| `Wczytuję pliki…` | `ui/anime.py:1809`: spis nierozstrzygniętej paczki. |
| `Dodaję subskrypcję…` | `ui/anime.py:115,604`: zapis przez ownera, nie samo lokalne zaznaczenie. |
| `Wysyłam…` | `ui/anime.py:112,1835`: wysyłka wyboru pliku; wybór wydania ma ten notice w B06 zamiast BUSY. |
| `Szukam…` | `ui/anime.py:1639-1641,1653-1657`: przejściowo ustawione przez `_start_work`, lecz zaraz w tej samej obsłudze `_open_candidates` zmienia ekran na B06; nie jest osobnym trwałym ekranem BUSY wydań. |

C-Anime i zachowany notice; błędy kończą B11 lub wracają do B13 z odmową.

### Naruszenia

R3-WAIT; R1-STATE-BUSY może objąć O w statusie, jeśli osobny worker State zajęty. Dla samego Esc nie stwierdzono R1: powrót działa także podczas wysyłki, choć nie cofa przyjętej operacji. R2 nie stwierdzono.

## B11 — PROBLEM: błąd lub brak wyników

### Klawisze i mysz

Enter wraca do `_problem_return`, czyści problem/sugestię; **nie ponawia operacji**. Esc/Backspace/Ctrl+C wraca do listowego `_problem_return`, ale przy QUERY wraca do Home lub listy Subskrypcji, więc nie jest zawsze równoważne Enter. C/Ctrl+Insert kopiuje tekstowy wiersz albo zaznaczenie. ↑↓/Pg/Home/End nie nawigują, ponieważ `_handle_problem` obsługuje tylko powrót; kółko może przewijać tekst, klik ustawia wiersz do C. Dwuklik nie potwierdza, PPM jak Esc. O/Tab/←→ przez K-Anime. `?`, D/I/P/S i `/` ignorowane (poza stale lub odzyskaniem partii we wcześniejszej obsłudze; `ui/anime.py:271-306,1201-1228,778-786`).

### Stopka

`Enter/Esc wróć` — scalone przez `footer_segments` (`ui/anime.py:962-963`; `ui/actions.py:49-50`). C niewidoczne w stopce, ponieważ tylko `more`, a `?` tutaj nie ma. F-Anime pending może zmienić ją na `Enter sprawdź wynik · Esc wróć`.

### Dół ekranu poza stopką

Treścią jest zawinięty problem oraz retry-hint lub sugestia; D-Anime może dodatkowo pokazać pozostawione notice. Brak zaznaczeń i kolumn. G. Tekst ma tag LINE, ale nie akcję dwukliku (`ui/anime.py:1024-1026`; `ui/anime_view.py:88-94,270`).

### Komunikaty

Pełny słownik E-błędy poniżej i Dodatek A wcześniejszego raportu przez `stated`; także `Nie znaleziono tytułu` (`ui/anime.py:1976`) — zero wyników AniList, `Katalog nie zawiera już tego wpisu` (:476) — brak szukanego ID we franczyzie U08, `Pobieranie jest niedostępne w tej sesji` (:221-223,1967). `spróbuj za {N} s` / `Możesz spróbować ponownie` (:2115-2120) zastępuje sugestię, gdy znany deadline dostawcy. Odliczanie nie wykonuje retry. `Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.` — nieobsłużony defekt katalogu lub INTERNAL/command_failed nowej operacji (`ui/anime.py:1913-1921,2071-2076`; `ui/anime_texts.py:94-97`). C-Anime/G.

### Naruszenia

R1-STALE (zwykłe Enter wróć też blokowane), R3-RESIDENT/R3-WAIT. Scalona podpowiedź `Enter/Esc wróć` to R2-BACK, mimo że kod dla powrotu QUERY robi różne rzeczy. Pozostała rozbieżność znaczenia Enter/Esc opisana wyżej, bez propozycji zmian.

## B12 — Potwierdzenie pobrania niepewnego wydania (PROBLEM z `_confirm_choice`)

### Klawisze i mysz

Enter zatwierdza zapamiętanego kandydata i rewizję, wraca do CANDIDATES oraz wykonuje `_choose_release(..., confirmed=True)`. Esc/Backspace/Ctrl+C bez zaznaczenia odrzuca potwierdzenie i wraca do wydań. O/zakładki przez K-Anime; C/Ctrl+Insert kopiuje. Inne lokalne klawisze ignorowane. Klik wskazuje tekst; dwuklik **nigdy nie potwierdza**; PPM odrzuca; kółko przewija treść (`ui/anime.py:1201-1210,1757-1777`; `tests/cli/test_panel_keys.py:1616-1629`). Zmiana oferty może unieważnić wybór u ownera; potwierdzenie nie oznacza bezwarunkowego przyjęcia.

### Stopka

`Enter pobierz mimo to · Esc wróć`, bez `?` (`ui/anime.py:962-963`; `ui/actions.py:45-51`). F-Anime może czasowo zastąpić Enter odzyskaniem wcześniej zachowanej partii.

### Dół ekranu poza stopką

Jak B11. Tekst pytania i wyjaśnienie są treścią, nie przyciskiem. G. Brak podsumowania zaznaczeń; wcześniejszy notice może pozostać, bo ustawienie potwierdzenia nie czyści go (`ui/anime.py:1768-1776`).

### Komunikaty

`Pobrać mimo niepewnej tożsamości?` (`ui/anime.py:1772`), następnie `{pełna nazwa wydania} · E{n} · {werdykt: powód}` (:1773-1775) — nazwa oceniona nie daje MATCH; pełne powody w R. Po Enter B06 `Wysyłam…`, po sukcesie B04/B05 `Zlecono E{n}`, po odmowie B11 (E). C-Anime/G.

### Naruszenia

R1-STALE jeśli `control_problem` przyszedł podczas pytania; R3-IDENTITY/R3-TECH-RELEASE/R3-WAIT. R2 nie stwierdzono.

## B13 — Nowa subskrypcja / już subskrybowany sezon (DRAFT)

### Klawisze i mysz

K-Anime, ale lista zawiera też nawigowalne tekstowe objaśnienia. Enter na `ep:` przełącza zaznaczenie, na `Dodaj subskrypcję` wysyła zapis (resident wymagany), na `Anuluj` wraca, na już subskrybowanym `show` otwiera U08. Enter na objaśnieniu nic nie robi. Space przełącza tylko odcinek; A przełącza wszystkie kwalifikujące się odcinki szkicu. Z nie otwiera zakresu. `/` QUERY, `?` B09, C kopiuje. Esc/Backspace/Ctrl+C wraca do źródła. Klik wybiera, checkbox=Space, dwuklik=Enter, PPM wraca, kółko przewija (`ui/anime.py:531-605`; `ui/anime_rows.py:155-191`).

Początkowo zaznaczone wszystkie wyemitowane, niezlecone odcinki sprzed granicy subskrypcji; kursor na pierwszym z nich, a gdy ich nie ma — na add/cancel/show. Nowe zaznaczenia nie są zapisem. Przyjęcie subskrypcji następnie zamawia zaznaczone zwykłą partią D; odmowa partii nie usuwa subskrypcji. Udany zapis przełącza panel na listę Subskrypcji, wyróżnia nowy wpis (`ui/anime.py:545-559,626-668,670-685`). S w tym ekranie nie dodaje niczego ponownie.

### Stopka

Z odcinkami `Enter wybierz · Space zaznacz · ? więcej · Esc wróć`; bez odcinków `Enter wybierz · ? więcej · Esc wróć`. Pomoc w pierwszym wariancie `A wszystkie · / szukaj · C kopiuj`, w drugim `/ szukaj · C kopiuj` (`ui/anime.py:971-974`). F-Anime może podmienić Enter. W wierszu już subskrybowanym dodatkowo tekst `Enter pokaż` (nie drugi segment stopki).

### Dół ekranu poza stopką

Brak zbiorczego `Zaznaczone…` mimo checkboxów szkicu. D-Anime notice; wybór tekstowego objaśnienia może ujawnić jego uciętą treść. Okruszek `Nowa subskrypcja › {tytuł}` (`ui/anime.py:670-685`). G. Ostrzeżenie o pauzie automatu jest tekstem szkicu zapisanym przy tworzeniu, a G bieżącą linią statusu.

### Komunikaty

- `Dodaj subskrypcję`, `Anuluj`, `Już wyemitowane · zaznaczone pobiorę od razu`, `Ten sezon jest już subskrybowany · Enter pokaż` (`ui/anime_rows.py:29-39,155-191`). Trzeci tekst stoi tylko jeśli lista ma niezlecone wyemitowane odcinki.
- `Kolejne odcinki pobiorę po emisji · {najbliższy E… dziś/jutro/data albo terminy jeszcze nieznane}`, `Automat jest wstrzymany · zacznę po wznowieniu`, `Nie wiadomo, ile odcinków już wyemitowano · spróbuj później` — pełne warianty S poniżej (`ui/subscription_texts.py:100-114,263-278`). Ostatni wariant ma tylko przycisk Anuluj.
- `E{n}  {tytuł lub Odcinek {n}}` — wiersz checkboxa (`ui/anime_rows.py:175-179`).
- `Limit: 100 odcinków · A odznacz wszystkie` — za duży wybór przy add (`ui/anime.py:601-603`); `Trwa partia · Enter sprawdź wynik` — poprzednia partia przy niepustym nowym wyborze (:598-600).
- Odmowa `subscription_add` wraca do szkicu, pokazuje pierwszą część `stated(problem)` (E i Dodatek A-subskrypcje), bez drugiej sugestii (`ui/anime.py:615-623`).
- `Dodano subskrypcję · {odmowa partii}` pojawia się dopiero na **liście** Subskrypcji (:625-638); sukces bez odmowy jest cichy. Późniejsze wyniki/odtworzenie partii trafiają przez `notify_list` (:322-339,644-668), opis S01 wcześniejszego raportu. C-Anime/G.

### Naruszenia

R1-DRAFT-ROW, R1-STATE-BUSY dla O, R3-MORE/R3-WAIT. Powtórzenie Enter w wierszu i stopce nie jest R2 ograniczonym do stopki. R2 nie stwierdzono.

## Słownik E — Stan odcinka i odmowy Anime (`anime_texts.py` w całości)

### E-stan — cały `EPISODE_REASON_LABELS`

Każdy powód poniżej jest kluczem odpowiedzi/stanu ownera, nie obliczeniem samego renderera. Tekst trafia do Stan B04/B05, szczegółów B09 lub zbiorczego wyniku partii. Gdy reason ma wpis w słowniku, wygrywa ze zwykłym state; przed nim wygrywają `polish_skipped` i `polish_wait_until` (`ui/anime_texts.py:156-166`).

| Klucz → dokładny tekst | Źródło | Kiedy i co oznacza |
|---|---|---|
| EpisodeReason.ADMITTED → `Zlecono` | `ui/anime_texts.py:27` | Owner potwierdził przyjęcie żądania; nie ukończenie. |
| NO_SUGGESTION → `Brak wydania` | `ui/anime_texts.py:28` | Nie wybrano sugestii, nawet jeśli surowe wyniki istnieją. |
| EPISODE_NOT_AIRED → `Nie wyemitowano` | `ui/anime_texts.py:29` | Odcinek oznaczony jako jeszcze niewyemitowany. |
| AdmissionConflict.ADMITTED → `Zlecono` | `ui/anime_texts.py:30` | Powtórne polecenie napotkało wcześniejsze przyjęcie. |
| EPISODE_IN_PROGRESS → `W toku` | `ui/anime_texts.py:31` | Istnieje niezakończona praca odcinka. |
| AdmissionConflict.POSSIBLY_ADMITTED → `Już zlecone?` | `ui/anime_texts.py:32` | Starszy zapis może obejmować ten odcinek, ale brak ścisłego potwierdzenia klucza. |
| AdmissionConflict.TRANSFER_RECORDED → `Konflikt hasha` | `ui/anime_texts.py:33` | Istniejący zapis transferu tego identyfikatora blokuje przyjęcie. |
| SOURCE_FAILED → `Błąd źródła` | `ui/anime_texts.py:34` | Źródło wydań nie dostarczyło wyniku. |
| LEGACY_UNREADABLE → `Błąd zleceń` | `ui/anime_texts.py:35` | Nie można wiarygodnie odczytać dawnych zamówień. |
| EPISODE_FILE_UNRESOLVED → `Wskaż plik` | `ui/anime_texts.py:36` | Przyjęcie istnieje, ale brak jednoznacznego pliku w paczce. |
| TRANSFER_FAILED → `Błąd pobierania` | `ui/anime_texts.py:37` | Transfer zakończył się niepowodzeniem. |
| PUBLICATION_FAILED → `Błąd eksportu` | `ui/anime_texts.py:38` | Nie udała się publikacja pobranego materiału. |
| WAITING_PREVIOUS_TRANSFER → `Czeka na stare` | `ui/anime_texts.py:39` | Nowe przypisanie czeka na rozliczenie poprzedniego transferu. |
| PUBLICATION_MISSING → `Brak pliku` | `ui/anime_texts.py:40` | Brakuje opublikowanego źródła. |
| RESULT_MISSING → `Do pobrania` | `ui/anime_texts.py:41` | Brak dostępnego wyniku; także domyślny Stan wyemitowanego bez innej etykiety (`ui/anime_rows.py:99-103`). |
| PACK_IN_PROGRESS → `Czeka na paczkę` | `ui/anime_texts.py:42` | Niedokończony transfer paczki chroni wcześniejsze przypisanie. |
| SUBSCRIPTION_AWAITING_AIRING → `Czeka na emisję` | `ui/anime_texts.py:43` | Cel subskrypcji oczekuje emisji. |
| SUBSCRIPTION_AWAITING_RELEASE → `Czeka na wydanie` | `ui/anime_texts.py:44` | Cel nie ma jeszcze przyjętego wydania. |
| SUBSCRIPTION_CHECKING → `Kontrola` | `ui/anime_texts.py:45` | Owner raportuje kontrolę celu/próby. |
| SUBSCRIPTION_CHECK_SKIPPED → `Bez kontroli` | `ui/anime_texts.py:46` | Kontrola została pominięta. |
| SUBSCRIPTION_EXHAUSTED → `Wyczerpano próby` | `ui/anime_texts.py:47` | Owner wyczerpał automatyczny budżet prób celu. |

### E-state — cały `_EPISODE_STATE_LABELS` i pozostałe etykiety

| Warunek → tekst | Źródło | Znaczenie |
|---|---|---|
| `ordered` → `Zlecono` | `ui/anime_texts.py:68` | Przyjęte zamówienie. |
| `downloading` → `Pobieram` | `ui/anime_texts.py:69` | Pobieranie źródła. |
| `downloaded` → `Pobrano` | `ui/anime_texts.py:70` | Źródło pobrane. |
| `processing` → `Przetwarzam` | `ui/anime_texts.py:71` | Tworzenie produktów. |
| `processing_failed` → `Błąd` | `ui/anime_texts.py:72` | Nieudane przetwarzanie. |
| `ready` → `Gotowe` | `ui/anime_texts.py:73` | Owner raportuje gotowy wynik. |
| `possibly_admitted` → `Już zlecone?` | `ui/anime_texts.py:74` | Niepewne dawne przyjęcie. |
| `polish_skipped` → `Bez czekania PL` | `ui/anime_texts.py:158-159` | Użytkownik pominął oczekiwanie na polskie napisy. |
| `polish_wait_until != None` → `Czeka na PL` | `ui/anime_texts.py:160-161` | Trwa wyznaczony bufor polskich napisów. |
| brak rozpoznanego `state` innego niż `not_ordered` → `Zlecono` | `ui/anime_texts.py:164-166` | Fallback, nie dodatkowy dowód przyjęcia. |
| ACQUISITION_UNAVAILABLE → `Niedostępne` + `Pobieranie jest niedostępne w tej sesji` | `ui/anime_texts.py:145-146,78` | Brak usługi pobierania. |
| nieznany powód → `Nie zlecono` | `ui/anime_texts.py:147-153` | Nieprzyjęty odcinek; notice przez `stated`. Wyjątek TORRENT_SOURCE_FAILED daje `Błąd źródła`. |

`not_ordered` bez reason zwraca pustą etykietę, którą wiersz zamienia na `Do pobrania`/`Nie wyemitowano`; nie wyświetla pustego stanu odcinka (`ui/anime_texts.py:164-165`; `ui/anime_rows.py:99-103`).

### E-odmowy — wskazówki do stanów

| Dokładny tekst | Źródło | Kiedy |
|---|---|---|
| `W toku · X anuluj w Przetwarzaniu` | `ui/anime_texts.py:51,139-140` | EPISODE_IN_PROGRESS: anulowanie wymaga innej zakładki. |
| `Odcinek już zlecony · P pobierz ponownie` | `ui/anime_texts.py:54,57,60-64,141-142` | AdmissionConflict.ADMITTED; jawna powtórka oddzielna od zwykłej odmowy. |
| `Już zlecone? · P pobierz ponownie` | `ui/anime_texts.py:32,57,62,141-142` | POSSIBLY_ADMITTED. |
| `Czeka na paczkę · P pobierz ponownie` | `ui/anime_texts.py:42,57,63,141-142` | PACK_IN_PROGRESS. |

W `stated` trzy ostatnie są rozdzielone na `(zdanie, wskazówka)`, nie zawsze sklejone; np. szkic pokazuje tylko zdanie. Inne znane reason dają identyczne Stan i notice (`ui/anime_texts.py:110-111,136-144`). `AnimeRow.refusal` poza tym słownikiem: własny `refusal_text`, potem detail, na końcu `Nie wyemitowano` albo `Zlecono | P pobierz ponownie` (`ui/anime_state.py:108-114`).

### E-błędy — cały `_PROBLEM_TEXTS` i `stated`

| Warunek | Dokładne zdanie / wskazówka | Źródło i znaczenie |
|---|---|---|
| TORRENT_SOURCE_FAILED | `Źródło wydań nie odpowiada` / `Sprawdź połączenie i spróbuj ponownie` | `ui/anime_texts.py:82`: błąd dostawcy wydań. |
| EPISODE_CATALOG_FAILED | `Lista odcinków niedostępna (ani.zip)` / `Spróbuj ponownie` | `ui/anime_texts.py:83`: błąd katalogu odcinków. |
| TORRENT_CLIENT_UNAVAILABLE | `qBittorrent nie odpowiada` / `Uruchom qBittorrenta z włączonym Web UI` | `ui/anime_texts.py:84`: brak dostępu do klienta; wskazówka lokalnej ścieżki. |
| TORRENT_CLIENT_UNAUTHORIZED | `qBittorrent odrzucił logowanie` / `Sprawdź login i hasło Web UI w pliku .env` | `ui/anime_texts.py:85-88`: odmowa uwierzytelnienia; lokalna wskazówka. |
| TORRENT_CLIENT_REFUSED | `qBittorrent odrzucił żądanie` / `Sprawdź ustawienia Web UI i spróbuj ponownie` | `ui/anime_texts.py:89`: odmowa żądania; lokalna wskazówka. |
| TITLE_CATALOG_FAILED | `AniList nie odpowiada` / `Spróbuj ponownie za chwilę` | `ui/anime_texts.py:90`: błąd katalogu tytułów. |
| trzy błędy klienta powyżej niesione przez ControlError | to samo zdanie / `Sprawdź prywatny klient AniShift i log` | `ui/anime_texts.py:125-132`: produkcyjna ścieżka resident zastępuje wskazówkę lokalną. |
| `response_too_large` | `Odpowiedź rezydenta jest za duża` | `ui/anime_texts.py:106-107`: odpowiedź ponad limit. |
| `offer_expired` | `Oferta wygasła — otwórz ponownie` | `ui/anime_texts.py:108-109`: nieaktualna oferta sesji. |
| STALE_PREVIEW | `Wybór lub konflikt zmienił się` / `Otwórz podgląd ponownie` | `ui/anime_texts.py:112-113`: niezgodny podgląd wyboru. |
| `download_recorded`, brak trzech poprawnych liczników | `Nie można potwierdzić wyniku zamówienia` / `Sprawdź prywatny klient AniShift i log` | `ui/anime_texts.py:114-117,169-174`: brak wiarygodnego zestawienia sent/accepted/uncertain. |
| `download_recorded`, liczniki poprawne | `Przyjęto: {sent} · już przyjęte: {accepted} · wynik przekazania niepotwierdzony: {uncertain}` / `Sprawdź prywatny klient AniShift i log` | `ui/anime_texts.py:118-122`: liczby przekazanych/przyjętych/niepewnych rezultatów. |
| nieznany AniShiftError lokalny | `Nie udało się wykonać operacji` | `ui/anime_texts.py:133`: ogólny fallback bez ujawnienia szczegółów domenowego wyjątku. |
| defekt operacji katalogowej / INTERNAL `command_failed` | `Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.` | `ui/anime_texts.py:94-97`; warunki w B11. |
| pozostały ControlError, OSError lub ValueError | Dodatek A `inventory-2.md`; ewentualnie sanitizowane `str(problem)` | `ui/anime_texts.py:100-105,133`: tekst nie zawsze jest polskim zamkniętym literałem. |

Funkcja `safe` sanitizuje tekst katalogu i usuwa końcowe kropki (`ui/anime_texts.py:187-189`); nie wszystkie zdania błędów przechodzą przez nią — powody R zachowują kropki, podobnie COMMAND_FAILED.

## Słownik S — cały zestaw tekstów `subscription_texts.py`

Wspólny dla S01 poprzedniego raportu, B05/B09 i B13. `_PAUSES` / `_ISSUES` / `_POLISH_HISTORY` i wszystkie polskie szablony:

| Warunek → dokładny tekst | Źródło | Kiedy i znaczenie |
|---|---|---|
| pause `user` → `Wstrzymana` | `ui/subscription_texts.py:55` | Pauza użytkownika. |
| `migrated_due` → `Wstrzymana — przeniesiona; zaległe odcinki` | `ui/subscription_texts.py:56` | Pauza po migracji z zaległościami. |
| `migrated_missing` → `Wstrzymana — zakończona przez starą wersję` | `ui/subscription_texts.py:57` | Pauza po migracji dawnego zakończenia. |
| paused → krótko `Wstrzymana`, pełne `{opis pauzy} · W wznów` | `ui/subscription_texts.py:158-159` | Nieznany powód pauzy wraca do `Wstrzymana`. |
| `season_unrecognized` → `Nie rozpoznano sezonu` / `Nie rozpoznano sezonu — usuń i dodaj ponownie` | `ui/subscription_texts.py:64` | Problem rozpoznania całego sezonu. |
| `catalog_conflict` → `Inny sezon w katalogu` / `Katalog wskazuje inny sezon — sprawdzam ponownie` | `ui/subscription_texts.py:65` | Zmiana/sprzeczność sezonu w katalogu blokuje subskrypcję. |
| nieznany nie-None problem → `Wymaga uwagi` | `ui/subscription_texts.py:177-181` | Fallback problemu całej subskrypcji. |
| beyond_count i episode_count to int → `Konflikt liczby odcinków` / `AniList podaje {N} {odcinek/odcinki/odcinków}, a subskrypcja czeka na E{M} · pobierz ręcznie albo usuń` | `ui/subscription_texts.py:182-188,285-290` | Numer oczekiwany wykracza poza deklarowaną liczbę. |
| review_pending → `Weryfikuję` / `Sprawdzam przeniesioną subskrypcję` | `ui/subscription_texts.py:160-161` | Trwa weryfikacja po migracji. |
| checking_number → `Kontrola E{n}` | `ui/subscription_texts.py:162-164` | Sprawdzany wskazany cel. |
| brak due_at i HIATUS → `Przerwa w emisji` | `ui/subscription_texts.py:165-167` | Katalog deklaruje przerwę. |
| brak due_at, inny status → `Termin nieznany` | `ui/subscription_texts.py:165-167` | Brak znanej następnej daty. |
| przyszły due_at → `Emisja{ E…} za {czas}` | `ui/subscription_texts.py:168-170,192-194` | Czas do emisji; numer pomijany, jeśli nie jest int. |
| due_at osiągnięty → `Czeka{ E…} od {czas}` | `ui/subscription_texts.py:195-198` | Czas od terminu; od 72 h pełny opis dokłada ` · sprawdzam raz dziennie`. |
| licznik → `{done/count}` / `{ready}` | `ui/subscription_texts.py:127-133` | `done` jeśli int, inaczej `on_disk`; nieznana liczba odcinków to `?`. |
| podsumowanie → `odcinki {done/count} · gotowe {ready}` | `ui/subscription_texts.py:147-150` | Łączy powyższe liczniki; nie jest postępem procentowym pobierania. |
| watched jedno/wiele → `{E…} obejrzany przed subskrypcją` / `{E…} obejrzane przed subskrypcją` | `ui/subscription_texts.py:136-144` | Epizody zaliczone przed początkiem subskrypcji. |
| historia PL `present` → `zwykle jest` | `ui/subscription_texts.py:75` | Dane poprzedniego odcinka sugerują polskie napisy. |
| historia PL `absent` → `brak w poprzednim odcinku` | `ui/subscription_texts.py:76` | Poprzedni odcinek bez polskich napisów. |
| historia PL unknown/inny → `nieznane` | `ui/subscription_texts.py:77,249` | Brak rozstrzygnięcia historii. |
| polish_skipped → `PL: {historia} · pobieram bez czekania` | `ui/subscription_texts.py:250-251` | Bufor pominięty przez użytkownika. |
| wait_until → `PL: {historia} · czekam do {HH:MM}` | `ui/subscription_texts.py:252-253` | Koniec czekania na polskie napisy w czasie lokalnym. |
| brak pominięcia/terminu → `PL: {historia} · pobieram od razu` | `ui/subscription_texts.py:254` | Opis polityki bez bufora, nie dowód aktywnego transferu. |
| check source_failed/rate_limited → `Sprawdzenie nieudane` | `ui/subscription_texts.py:70,208-211` | Krótki stan nieudanego sprawdzenia na liście Subskrypcji. |
| check z numerem → `Sprawdzono E{n}` | `ui/subscription_texts.py:212-213` | Krótki wynik listy. |
| check bez numeru → `Sprawdzono listę odcinków` | `ui/subscription_texts.py:213,225-226` | Sprawdzono katalog, nie konkretne wydania odcinka. |
| source_failed → `{E{n}: źródło wydań albo Katalog odcinków} nie odpowiada · ponowię później` | `ui/subscription_texts.py:220-222` | Nieudana odpowiedź źródła. |
| rate_limited → `{E{n}: źródło wydań albo Katalog odcinków} ogranicza zapytania · ponowię później` | `ui/subscription_texts.py:220,223-224` | Ograniczenie częstotliwości zapytań. |
| zero kandydatów → `Sprawdzono E{n}: brak wydań w źródle` | `ui/subscription_texts.py:227-234` | Suma matching/uncertain/mismatched równa zero. |
| kandydaci → `Sprawdzono E{n}: {N} {kandydat/kandydatów}, {M} zgodnych` | `ui/subscription_texts.py:235-236` | Suma trzech klas, zgodne to matching. |
| istnieją inne klasy → dopisek ` ({U} niepewnych, {X} niezgodnych)` | `ui/subscription_texts.py:237-238` | Pokazuje rozkład oceny tożsamości. |
| outcome proposed → dopisek ` · propozycja zapisana` | `ui/subscription_texts.py:239` | Wynik propozycji, nie potwierdzenie pobrania. |
| szkic: cut nieznane → `Nie wiadomo, ile odcinków już wyemitowano · spróbuj później` | `ui/subscription_texts.py:104-106` | Szkic nie może być dodany. |
| szkic możliwy → `Kolejne odcinki pobiorę po emisji · {następna emisja}` | `ui/subscription_texts.py:107-108` | Zapowiedź polityki dla przyszłych celów. |
| szkic przy paused → `Automat jest wstrzymany · zacznę po wznowieniu` | `ui/subscription_texts.py:109-110` | Automatyczna subskrypcja czeka na globalne wznowienie. |
| następna emisja znana → `najbliższy E{n} dziś {HH:MM}` / `najbliższy E{n} jutro {HH:MM}` / `najbliższy E{n} {DD.MM HH:MM}` | `ui/subscription_texts.py:263-278` | Pierwszy cel z datą AniList, lokalne daty. |
| brak dat → `terminy jeszcze nieznane` | `ui/subscription_texts.py:268` | Nie znaleziono daty celu. |
| notices → `E{n}: {polskie powody połączone · }` | `ui/subscription_texts.py:257-260` | Bieżące powody konkretnego odcinka; pełny słownik S-notices poniżej. |

Format czasu to `HH:MM:SS`, a z dniami `{D}d HH:MM:SS` (`ui/subscription_texts.py:201-205`); same znaczniki odcinków to `E{n}`, `E{first}–E{last}` dla ciągłych albo lista `E…` po przecinku (`:117-124,281-282`). Priorytet row_state: problem/liczba → pauza → weryfikacja → checking → termin (`:153-170`). `CHECK_SHOWN_S=10` (:41) dotyczy projekcji listy; B05 `_last_check` nie korzysta z tej stałej.

### S-notices — polskie powody importowane przez fasadę

Każdy jest renderowany przez `notice_line` jako `E{n}: …`; to jedyne źródło tych zdań w B05/B09, a nie tekst do samodzielnego odgadywania przez UI (`ui/subscription_texts.py:257-260`; `app/episode_commands.py:198-204`).

| Powód → tekst | Źródło | Znaczenie |
|---|---|---|
| stalled / metadata_timeout → `wydanie stoi` | `app/episode_commands.py:20-21` | Brak postępu transferu albo timeout metadanych. |
| rejected → `wydanie odrzucone` | `app/episode_commands.py:22` | Odrzucenie kontroli pobranego pliku. |
| pack → `wydanie okazało się paczką` | `app/episode_commands.py:23` | Automatyczna próba ujawniła pakiet odcinków. |
| ambiguous → `wydanie ma niejednoznaczny plik` | `app/episode_commands.py:24` | Więcej niż jeden możliwy plik. |
| no_match → `plik to nie ten odcinek` | `app/episode_commands.py:25` | Brak zgodnej tożsamości pliku. |
| recheck → `plik nie przeszedł ponownej kontroli` | `app/episode_commands.py:26` | Plik nieużyteczny po ponownej ocenie. |
| taken → `plik należy już do innego odcinka` | `app/episode_commands.py:27` | Chronione przypisanie innego odcinka. |
| no_admissible → `brak pewnego wydania` | `app/episode_commands.py:28` | Brak przyjmowalnego kandydata. |
| threshold → `czekam na lepszą rozdzielczość` | `app/episode_commands.py:29` | Próg po nieudanej próbie blokuje wybór. |
| pending → `czekam na sprawdzenie wydań` | `app/episode_commands.py:30` | Czekanie na uzupełnienie oceny. |
| sources_down → `źródła wydań nie odpowiadają` | `app/episode_commands.py:31` | Awaria źródeł. |
| no_polish_after_wait → `brak PL` | `app/episode_commands.py:32` | Pobranie bez PL po buforze. |
| nieznany → `pobieranie nie powiodło się` | `app/episode_commands.py:37,200` | Fallback nieudanej próby. |

Przy poprawnym `cause` powyższe zdania rozszerzają się następująco (`app/episode_commands.py:207-245`):

- rejected: `wydanie odrzucone (brak obrazu)` / `(za krótki plik)` / `(za długi plik)` / `(kontrola pliku)` — odpowiednio no_video_stream, fragment_duration, compilation_or_extended_duration, nieznany kod (`:40-45,210-211`).
- no_admissible: `brak pewnego wydania ({N} {wydanie/wydania/wydań}, {M} zgodne)` z odmianą oraz opcjonalnym `, {T} już próbowane` (również odmiana), na podstawie cause total/fresh/tried (`:212-213,225-228,255-261`).
- threshold: `czekam na 1080p`, `czekam na 1080p lub 2160p`, `czekam na 1080p, 2160p lub 720p`, `czekam na znaną rozdzielczość`, `czekam na dowolną rozdzielczość`, opcjonalnie ` (dostępne {H}p)` — klasy FULL_HD/UHD/HD/OTHER/UNKNOWN (`:49-56,231-234`).
- pending: `czekam na sprawdzenie wydań {H}p` (`:216-217,237-238`).
- sources_down: `źródła wydań nie odpowiadają od {N} h` (`:218-219`).
- no_polish_after_wait: `brak PL po {N} min`, `brak PL po {H} h` lub `brak PL po {H} h {M} min` (`:220-221,241-245`).

Nieczytelne cause zachowuje ogólną frazę. Opcja `, szukam następnego` istnieje w fasadzie (`:204`), ale `notice_line` nie przekazuje `searching=True`, więc nie dodaje jej do U08.

## Słownik R — wydania, szczegóły i wszystkie `_REASON_TEXTS`

### R-werdykt i opis techniczny

Każdy powód niżej jest wyświetlany jako `{zgodny/niepewny/niezgodny}: {zdanie}` zależnie od IdentityVerdict, nie od stopnia pewności (`ui/anime_releases.py:31-35,224-227`). Jest częścią detail B06/B09 oraz potwierdzenia B12. MISMATCH zwykle nie trafia do widocznej listy; słownik zawiera także te gałęzie, zgodnie wymaganiem kompletności. Jeśli reason nie występuje w tabeli, fallback to:

| Tekst | Źródło | Warunek |
|---|---|---|
| `Nazwa wskazuje wybrany odcinek.` | `ui/anime_releases.py:39` | MATCH bez znanego tłumaczenia. |
| `Nie można jednoznacznie ustalić tożsamości odcinka.` | `ui/anime_releases.py:40` | INSUFFICIENT bez znanego tłumaczenia. |
| `Nazwa wskazuje inny materiał.` | `ui/anime_releases.py:41` | MISMATCH bez znanego tłumaczenia. |
| `Plik: {ścieżka lub nazwa}` | `ui/anime_releases.py:258-259` | Oferta niesie path/file_name; wartość sanitizowana. |
| `bez nazwy pliku` | `ui/anime_releases.py:260-261` | Ocena tylko nazwy wydania. |
| `wydanie z platformy` | `ui/anime_releases.py:262-263` | traits.platform. |
| `format nieobsługiwany` | `ui/anime_releases.py:264-265` | supported=False. |
| `niejednoznaczny plik` | `ui/anime_releases.py:266-267` | ambiguous=True. |
| `sam dubbing` | `ui/anime_releases.py:268-269` | traits.dub_only. |
| `Kalibracja pewności potwierdzona tylko dla korpusu E1. Dla nowych źródeł i ocen bez nazwy pliku: estymata bez potwierdzonej kalibracji.` | `ui/anime_releases.py:271-274` | Zawsze dopisywana do detail, niezależnie od źródła konkretnego kandydata. |
| ` · niepewne` po procentach/`?` | `ui/anime_releases.py:287-291` | Sugestia inna niż MATCH, bez konfliktu. |
| `Odczyt H1 ({tryb}): sezon {S/?}, odcinek {N/?}, część {P/?}` | `ui/anime_releases.py:294-301` | Istnieje CandidateNumbering; tryb to `S/E`, `bez znacznika numeracji` lub `brak numeru` dla mapped/plain/missing (:297). |
| `Cel: lokalny {N/?}; S/E: sezon {S/?}, odcinek {E/?}; absolutny {A/?}; sezon w tytule {S/?}; część {P/?}` | `ui/anime_releases.py:302-307` | Te same dane; zestawienie numeracji docelowej. |

### R-powody — pełna mapa klucz → polskie zdanie

Warunek każdej pozycji: `item.identity.reason` jest dokładnie kluczem w pierwszej kolumnie; polskie zdanie wyjaśnia faktyczną przesłankę oceny (nazwa/pliki/metadane, **nie obejrzany film**). Kolumna „Znaczenie” doprecyzowuje tę przesłankę jednym zdaniem.

| Klucz reason | Dokładne zdanie | Źródło | Znaczenie |
|---|---|---|---|
| `Mapped absolute number exceeds the local episode range under a specific title.` | `Numer absolutny wykracza poza zakres odcinków tego wpisu.` | `ui/anime_releases.py:46-48` | Numer ciągły nie mieści się w lokalnej liście konkretnego tytułu. |
| `Named season, local episode and catalog episode title agree.` | `Sezon, numer lokalny i katalogowy tytuł odcinka są zgodne.` | `ui/anime_releases.py:49-51` | Trzy niezależne oznaczenia pasują do celu. |
| `Season marker conflicts with the target numbering system.` | `Oznaczenie sezonu jest sprzeczne z numeracją szukanego odcinka.` | `ui/anime_releases.py:52-54` | Znacznik sezonu wskazuje inną numerację. |
| `Part/cour marker conflicts with the target.` | `Oznaczenie części jest sprzeczne z wybranym wpisem.` | `ui/anime_releases.py:55` | Part/cour nazwy nie odpowiada części celu. |
| `A franchise alias does not identify this installment.` | `Nazwa franczyzy nie wskazuje jednoznacznie tego wpisu.` | `ui/anime_releases.py:56` | Nazwa całego cyklu nie identyfikuje jego konkretnej części. |
| `The required part/cour is not established.` | `Nie ustalono wymaganej części sezonu.` | `ui/anime_releases.py:57` | Brakuje dowodu Part/cour. |
| `Explicit mapped episode differs from target.` | `Podany numer katalogowy wskazuje inny odcinek.` | `ui/anime_releases.py:58` | Jawny numer po mapowaniu nie pasuje. |
| `Catalog episode title belongs to another episode.` | `Tytuł w nazwie należy do innego odcinka.` | `ui/anime_releases.py:59` | Tytuł epizodu identyfikuje inny numer. |
| `Work anchor and exact mapped season/episode match; residual is technical or catalogued.` | `Tytuł oraz katalogowe numery sezonu i odcinka są zgodne; pozostały tekst jest rozpoznany.` | `ui/anime_releases.py:60-62` | Tytuł i S/E pasują, a reszta nazwy nie wnosi sprzeczności. |
| `Movie segment or numbering requires a more specific identity anchor.` | `Część lub numer filmu wymaga dokładniejszego potwierdzenia tożsamości.` | `ui/anime_releases.py:63-65` | Oznaczenie części filmu nie wystarcza do wyboru. |
| `Movie title matches with compatible year and no unidentified residual.` | `Tytuł filmu jest zgodny, rok nie jest sprzeczny i nie ma nierozpoznanego tekstu.` | `ui/anime_releases.py:66-68` | Nazwa filmu spełnia wszystkie wymienione warunki. |
| `OVA/special needs a mapped episode or catalog episode title.` | `Dodatek wymaga numeru katalogowego lub katalogowego tytułu odcinka.` | `ui/anime_releases.py:69-71` | Sam tytuł cyklu nie wystarcza do identyfikacji dodatku. |
| `No unambiguous selected episode number.` | `Brak jednoznacznego numeru wybranego odcinka.` | `ui/anime_releases.py:72` | Numer nie został jednoznacznie odczytany. |
| `Bare number is not the local episode; absolute numbering is not established.` | `Numer nie pasuje do odcinka lokalnego; nie potwierdzono numeracji absolutnej.` | `ui/anime_releases.py:73-75` | Nie można uzasadnić różnicy numerem ciągłym serii. |
| `Local and mapped numbering conflict.` | `Numeracja lokalna i katalogowa są sprzeczne.` | `ui/anime_releases.py:76` | Dwa systemy numeracji dają różne cele. |
| `Mapped numbering cannot be checked without target numbering.` | `Bez numeracji szukanego odcinka nie da się sprawdzić numeru katalogowego.` | `ui/anime_releases.py:77-79` | Brak docelowego mapowania uniemożliwia porównanie. |
| `Mapped number equals the target absolute number; numbering is ambiguous.` | `Numer w nazwie równa się numerowi absolutnemu odcinka; numeracja jest niejednoznaczna.` | `ui/anime_releases.py:80-82` | Równość liczb nie rozstrzyga systemu numeracji. |
| `Specific work title and local episode match; residual is technical or catalogued.` | `Dokładny tytuł i numer lokalny odcinka są zgodne; pozostały tekst jest rozpoznany.` | `ui/anime_releases.py:83-85` | Konkretny wpis i numer pasują, reszta nazwy rozpoznana. |
| `Package directory explicitly identifies Plex extra material.` | `Katalog paczki wskazuje materiał dodatkowy Plex.` | `ui/anime_releases.py:86` | Katalog ma oznaczenie dodatku Plex. |
| `Package explicitly identifies a neighboring work.` | `Paczka wskazuje inny powiązany tytuł.` | `ui/anime_releases.py:87` | Nazwa paczki identyfikuje sąsiedni wpis. |
| `Package explicitly identifies a different season.` | `Paczka wskazuje inny sezon.` | `ui/anime_releases.py:88` | Jawnie inny sezon paczki. |
| `Package explicitly identifies a different part/cour.` | `Paczka wskazuje inną część sezonu.` | `ui/anime_releases.py:89` | Jawnie inny Part/cour paczki. |
| `Package explicitly identifies a different final season.` | `Paczka wskazuje inny sezon finałowy.` | `ui/anime_releases.py:90` | Oznaczenie sezonu finałowego nie odpowiada celowi. |
| `Package contains an unresolved sequel qualifier.` | `Paczka zawiera niejednoznaczny dopisek sequela.` | `ui/anime_releases.py:91` | Dopisek kontynuacji nie daje się jednoznacznie przypisać. |
| `Package localized season conflicts with the target or is unresolved.` | `Obcojęzyczne oznaczenie sezonu w paczce jest sprzeczne lub niejednoznaczne.` | `ui/anime_releases.py:92-94` | Lokalizowane oznaczenie sezonu nie potwierdza celu. |
| `Package Roman season/part conflicts with the target or is unresolved.` | `Rzymski numer sezonu lub części w paczce jest sprzeczny lub niejednoznaczny.` | `ui/anime_releases.py:95-97` | Rzymska numeracja nie potwierdza celu. |
| `Package ordinal part/cour conflicts with the target.` | `Numer porządkowy części w paczce wskazuje inną część.` | `ui/anime_releases.py:98` | Jawny numer części jest odmienny. |
| `Package localized movie format conflicts with the target.` | `Obcojęzyczne oznaczenie filmu w paczce nie pasuje do wybranego wpisu.` | `ui/anime_releases.py:99-101` | Nazwa określa format filmu niepasujący do celu. |
| `Package contains an unresolved continuation marker.` | `Paczka zawiera niejednoznaczne oznaczenie ciągu dalszego.` | `ui/anime_releases.py:102` | Nie można przypisać oznaczenia kontynuacji. |
| `Package contains an uncatalogued title suffix.` | `Paczka zawiera końcówkę tytułu nieznaną katalogowi.` | `ui/anime_releases.py:103` | Dodatkowy człon tytułu nie jest znanym aliasem. |
| `Package explicitly identifies a different language-specific media format.` | `Obcojęzyczne oznaczenie w paczce wskazuje inny rodzaj materiału.` | `ui/anime_releases.py:104-106` | Oznaczenie formatu w innym języku przeczy celowi. |
| `Package season declaration conflicts with the target or is unresolved.` | `Deklaracja sezonu w paczce jest sprzeczna lub niejednoznaczna.` | `ui/anime_releases.py:107-109` | Deklaracja sezonu nie rozstrzyga zgodności. |
| `Package Russian season declaration is unresolved.` | `Rosyjskie oznaczenie sezonu w paczce jest niejednoznaczne.` | `ui/anime_releases.py:110` | Rosyjski znacznik nie daje rozstrzygnięcia. |
| `Package explicitly identifies non-episode material.` | `Paczka wskazuje materiał inny niż odcinek.` | `ui/anime_releases.py:111` | Paczka jest oznaczona jako materiał poza odcinkami. |
| `Package explicitly identifies a different media type.` | `Paczka wskazuje inny rodzaj materiału.` | `ui/anime_releases.py:112` | Typ materiału paczki jest inny niż docelowy. |
| `Package year conflicts with target metadata.` | `Rok paczki jest sprzeczny z metadanymi wybranego wpisu.` | `ui/anime_releases.py:113` | Rok identyfikuje inną pozycję. |
| `Package explicitly identifies a numbered sequel.` | `Paczka wskazuje numerowaną kontynuację.` | `ui/anime_releases.py:114` | Jawny numer kontynuacji odróżnia paczkę od celu. |
| `Titleless file lacks an unambiguous nearest work directory or single-work release.` | `Plik bez tytułu nie ma jednoznacznego katalogu ani wydania jednego tytułu.` | `ui/anime_releases.py:115-117` | Brak tytułu nie może być uzupełniony kontekstem katalogu/wydania. |
| `Titleless file names the target episode number and catalog episode title.` | `Plik bez tytułu serii podaje numer i katalogowy tytuł szukanego odcinka.` | `ui/anime_releases.py:118-120` | Numer i tytuł epizodu pozwalają dopasować plik. |
| `Franchise alias carries the target absolute number of a matching release.` | `Nazwa franczyzy ma numer absolutny odcinka, a nazwa wydania wskazuje szukany odcinek.` | `ui/anime_releases.py:121-123` | Numer ciągły i kontekst wydania razem potwierdzają cel. |
| `Selected name numbers a special instead of a TV episode.` | `Nazwa wskazuje odcinek specjalny (S00 albo numer z .5), a nie odcinek serii.` | `ui/anime_releases.py:124-126` | Plik jest dodatkiem zamiast zwykłego odcinka TV. |
| `Selected file or work directory identifies a neighboring catalogue work.` | `Wybrany plik lub katalog wskazuje inny tytuł katalogowy.` | `ui/anime_releases.py:127-129` | Dokładniejszy kontekst wskazuje inny wpis katalogu. |
| `Selected directory has a numbered season conflicting with the target.` | `Numer sezonu w wybranym katalogu jest sprzeczny z wybranym odcinkiem.` | `ui/anime_releases.py:130-132` | Sezon katalogu pliku nie pasuje do celu. |
| `Selected TV variant conflicts with the target editing variant.` | `Wariant telewizyjny pliku jest sprzeczny z wybraną wersją montażową.` | `ui/anime_releases.py:133-135` | Oznaczony wariant TV nie jest docelowym montażem. |
| `Release editing variant is not established for the target episode.` | `Nie potwierdzono wersji montażowej wydania dla tego odcinka.` | `ui/anime_releases.py:136-138` | Brak jednoznacznego dowodu wariantu montażu. |
| `Malformed candidate metadata.` | `Metadane wydania mają niepoprawny format.` | `ui/anime_releases.py:139` | Dane kandydata nie spełniają kontraktu wejścia oceny. |
| `No selected file.` | `Brak wskazanego pliku.` | `ui/anime_releases.py:140` | Ocena nie ma wybranego pliku. |
| `Selected file has no allowed video extension.` | `Wybrany plik nie ma dozwolonego rozszerzenia wideo.` | `ui/anime_releases.py:141` | Nazwa nie kończy się obsługiwanym rozszerzeniem. |
| `Malformed target or archived identity metadata.` | `Metadane celu lub tożsamości mają niepoprawny format.` | `ui/anime_releases.py:142` | Dane docelowe lub archiwalne nie spełniają kontraktu oceny. |
| `Selected filename has an explicit Plex extra suffix.` | `Nazwa pliku oznacza materiał dodatkowy Plex.` | `ui/anime_releases.py:143` | Jawny sufiks dodatku Plex. |
| `Selected residual explicitly identifies non-episode material.` | `Dodatkowy tekst nazwy wskazuje materiał inny niż odcinek.` | `ui/anime_releases.py:144-146` | Pozostała część nazwy wskazuje materiał dodatkowy. |
| `Unresolved leading bracket is the nearest identity context.` | `Nierozpoznany początkowy nawias uniemożliwia ustalenie tożsamości.` | `ui/anime_releases.py:147-149` | Najbliższy kontekst nazwy jest nieznany. |
| `Selected filename more specifically identifies a neighboring work.` | `Dokładniejsza nazwa pliku wskazuje inny powiązany tytuł.` | `ui/anime_releases.py:150-152` | Mocniejsze dopasowanie dotyczy innego dzieła. |
| `Filename year is missing from or conflicts with runtime target metadata.` | `Roku z nazwy pliku nie ma w metadanych celu albo jest z nimi sprzeczny.` | `ui/anime_releases.py:153-155` | Roku nie można potwierdzić w danych celu. |
| `Unconsumed filename text is neither technical metadata nor a catalog episode title.` | `Pozostały tekst nazwy nie jest metadanymi technicznymi ani katalogowym tytułem odcinka.` | `ui/anime_releases.py:156-158` | Nierozpoznana reszta nazwy uniemożliwia pełne dopasowanie. |
| `Published before the target episode aired.` | `Wydanie opublikowano przed emisją szukanego odcinka.` | `ui/anime_releases.py:159` | Data publikacji przeczy szukanemu odcinkowi. |
| `Bare number is the target absolute number; no local episode had that number yet.` | `Numer to numer absolutny szukanego odcinka; odcinek sezonu o tym numerze jeszcze nie istniał.` | `ui/anime_releases.py:160-162` | Chronologia rozstrzyga numer bez znacznika. |
| `Published when the season episode with this number aired.` | `Wydanie opublikowano w dniu emisji odcinka sezonu o tym numerze.` | `ui/anime_releases.py:163-165` | Data popiera lokalną numerację sezonu. |
| `Bare number lies beyond the target season.` | `Numer wykracza poza odcinki szukanego sezonu.` | `ui/anime_releases.py:166` | Liczba bez znacznika nie mieści się w sezonie. |
| `Release group numbers this season from 1.` | `Ta grupa numeruje odcinki tego sezonu od 1.` | `ui/anime_releases.py:167` | Pozostałe wydania grupy dostarczają numeracji lokalnej. |
| `Release group marks the target season elsewhere in the offer.` | `Ta grupa oznacza szukany sezon w innym wydaniu, więc to wydanie bez sezonu dotyczy innego sezonu.` | `ui/anime_releases.py:168-170` | Oznaczenia innych wydań grupy przeczą dopasowaniu tej nazwy. |
| `File checksum equals an assessed release.` | `Suma kontrolna pliku jest taka sama jak w ocenionym wydaniu.` | `ui/anime_releases.py:171` | Suma kontrolna łączy plik z wcześniej ocenionym wydaniem. |

### R-konflikty — napisy w kolumnie Pewność

`_candidate_confidence` wybiera `conflict_label` przed procentami (`ui/anime_releases.py:287-291`). Pełna mapa `CONFLICT_LABELS` (`app/episode_identity.py:207-228`):

| Klucz reason (jak R-powody) | Tekst | Źródło |
|---|---|---|
| Season marker conflicts with the target numbering system. | `inny sezon` | `app/episode_identity.py:209` |
| Part/cour marker conflicts with the target. | `inna część` | `app/episode_identity.py:210` |
| Local and mapped numbering conflict. | `inny numer` | `app/episode_identity.py:211` |
| Package directory explicitly identifies Plex extra material. | `dodatek` | `app/episode_identity.py:212` |
| Package explicitly identifies a neighboring work. | `inne dzieło` | `app/episode_identity.py:213` |
| Package explicitly identifies a different season. | `inny sezon` | `app/episode_identity.py:214` |
| Package explicitly identifies a different part/cour. | `inna część` | `app/episode_identity.py:215` |
| Package explicitly identifies a different final season. | `inny sezon` | `app/episode_identity.py:216` |
| Package ordinal part/cour conflicts with the target. | `inna część` | `app/episode_identity.py:217` |
| Package localized movie format conflicts with the target. | `inny rodzaj (film)` | `app/episode_identity.py:218` |
| Package explicitly identifies a different language-specific media format. | `inny rodzaj materiału` | `app/episode_identity.py:219` |
| Package explicitly identifies non-episode material. | `nie odcinek` | `app/episode_identity.py:220` |
| Package explicitly identifies a different media type. | `inny rodzaj materiału` | `app/episode_identity.py:221` |
| Package year conflicts with target metadata. | `inne dzieło (rok)` | `app/episode_identity.py:222` |
| Package explicitly identifies a numbered sequel. | `kontynuacja` | `app/episode_identity.py:223` |
| Selected file or work directory identifies a neighboring catalogue work. | `inne dzieło` | `app/episode_identity.py:224` |
| Selected directory has a numbered season conflicting with the target. | `inny sezon` | `app/episode_identity.py:225` |
| Selected TV variant conflicts with the target editing variant. | `inny wariant montażu` | `app/episode_identity.py:226` |
| Selected filename more specifically identifies a neighboring work. | `inne dzieło` | `app/episode_identity.py:227` |

MISMATCH_LABELS istnieje, lecz normalna lista odfiltrowuje MISMATCH: `inny odcinek` (Explicit mapped episode differs…, `app/episode_identity.py:233`), `nie wideo` (Selected file has no allowed video extension…, :234), `dodatek` (Selected filename has an explicit Plex extra suffix…, :235), `nie odcinek` (Selected residual explicitly identifies non-episode material…, :236), `tytuł innego odcinka` (Catalog episode title belongs to another episode…, :237), `odcinek specjalny` (Selected name numbers a special instead of a TV episode…, :238). Oznaczają odpowiednie sprzeczności opisane w R-powody, nie ocenę jakości obrazu.

## Rozbieżności i granice dowodu

1. **Dokumentacja U08 mówi o 10 s wyniku i `check_state` w Stan.** Kod B05 używa bieżącego `row_state`, a ostatnie sprawdzenie dopisuje przez `_last_check()` bez limitu czasu. Limit CHECK_SHOWN_S należy do listy Subskrypcji. Źródła: `anishift/cli/AGENTS.md:94-98`; `ui/anime.py:694-743`; `ui/subscription_texts.py:41,208-213`.
2. **„Wszędzie” nie znaczy wszędzie w każdej nakładce.** B09 pokazuje akcje źródła, lecz D/Space/A/Z i subskrypcyjne W/R/X/T nie przechodzą do tych samych handlerów. B11/B12 nie mają klawiaturowego przewijania mimo zawijanych wierszy; kółko działa. Źródła w B09/B11.
3. **Plan opisuje zakresy całkowite, parser przyjmuje Decimal.** To nie dowód, że da się zamówić produkcyjny odcinek 7.5; numery zwykłych odcinków i publiczne komendy wymagają dodatnich int. `ui/anime_state.py:241-258`; `app/episode_commands.py:186-195`.
4. **State notice nie jest Anime notice.** O/W/R i większość ich odmów nie ma widocznego slotu w Anime; jawne odmowy odtwarzania i `target_not_waiting` są przekazywane do dziecka. `ui/state.py:489-515,928-978,1228-1231`. Nie opisuję tych niewidocznych tekstów jako widocznych na U08 tylko dlatego, że są ustawiane.
5. **Szablony w kodzie bez dowodu zwykłej osiągalności:** lokalne `Brak mapowania`, drugi limit kontrolera, lokalne wskazówki Web UI i niektóre MISMATCH. Zostały wyliczone z oznaczeniem warunków; nie są dowodem, że każda produkcyjna sesja je pokaże.
6. **Zależne od danych teksty:** titles/paths/offer.status/wyjątki mogą zawierać dowolny tekst, również angielski. Zamknięte polskie wartości `offer.status` wyliczono w B06. `offer.sources` jest budowane w `app/acquisition.py:1174`, ale `_display_rows`/szczegóły nie renderują tej listy; nie mylić z widocznym `szukam jeszcze: …` (`ui/anime.py:931-943,1016-1021`).
7. **Testy przeczytane, nie uruchomione:** złote akcje i stopki `tests/cli/test_panel_keys.py:492-606,699-750`; szczegóły `:765-783`; U08 `:960-1027`; wyjścia/zakres `:1237-1311`; mysz `:1376-1648,1782-1826,2012-2037`; ready `:1948-2009`. Sonda „działa tam, gdzie ma zastosowanie” korzysta z `_APPLIES` (:551-563), więc celowo nie dowodzi dostępności na każdym wierszu. Żadnych poprawek ani nowych tekstów nie proponowano.

## Tabela zbiorcza naruszeń R1/R2/R3

Jeden wiersz = jeden mechanizm albo rodzina ściśle powiązanych tekstów, nie liczba wystąpień na ekranach. R1 obejmuje zarówno stopkę, status, jak i jawne podpowiedzi pomocy — lokalizacja podana w dowodzie. R2 oznacza dwie jawne podpowiedzi tej samej czynności w stopce, także scalone `Enter/Esc`; powtórzeń między treścią, notice i stopką nie doliczono. R3 poza przykładami właściciela to ocena zrozumiałości na podstawie kodu, nie badanie użytkowników. Sam błąd sieci po prawidłowej próbie nie jest R1.

| ID | Ekran / tekst | Reguła | Obserwacja i dowód |
|---|---|---|---|
| R1-QUERY | B01 `Enter szukaj` | R1 | Bez fokusu Enter tylko go włącza; puste query nie wyszukuje. Przy zachowanej pending partii i `_batch_running=False` Enter aktywnego pola odtwarza wynik zamiast szukać. `ui/anime.py:290-292,949-959,1138-1146,1159-1160`. |
| R1-O-FIELD | B01/B08 `O włącz` / `O wyłącz` w statusie | R1 | `accepts_text=True` kieruje O do pola, a wspólny status nadal je reklamuje. `ui/state.py:710-711,1485-1487`; `ui/anime.py:1116-1120`. |
| R1-ANNOUNCED | B02/B03 `Enter wybierz` / `Enter odcinki` | R1 | Zapowiedź jest już rozpoznana, ale Enter tylko pokazuje `_ANNOUNCED`, nie otwiera. `ui/anime.py:964-966,1514-1516,1567-1569`. |
| R1-S-FINISHED | B02/B03/B04 `S subskrybuj` | R1 | Na już znanym zakończonym wpisie bez istniejącej subskrypcji akcja prowadzi do odmowy, nie szkicu do dodania. Stopka bez warunku statusu. `ui/anime.py:531-540,964-966,982-984`; `ui/subscription_texts.py:102-103`. |
| R1-EP-ELIGIBILITY | B04/B05 `Space zaznacz · D pobierz` | R1 | Na nieemitowanym/aktywnym wierszu bez innych zaznaczeń akcje odmawiają; stopka pozostaje. `ui/anime.py:979,1464-1469`; `ui/anime_state.py:206-213`; `ui/anime_panel.py:194-204`. |
| R1-PENDING | B04/B05/B06 `Space zaznacz · D pobierz`, pomoc `Z zakres · A wszystkie · P ponownie` | R1 | Pending/wysyłka ustawia `view.searching`; Space/A/Z blokowane, D/P tylko notice, bez ukrycia podpowiedzi. `ui/anime.py:916-919,969-980`; `ui/anime_state.py:208,223`; `ui/anime_panel.py:176-191`. |
| R1-P-NEW | B04/B05 `P ponownie` w pomocy | R1 | Nowy odcinek bez statusu/admission nie spełnia warunku P. `ui/anime.py:980,1300-1304`. |
| R1-STALE | B02–B07/B11–B13; Enter/D/P | R1 | Stale zatrzymuje te klawisze przed handlerem, a akcje nie uwzględniają stale. Obejmuje nawet Enter wróć w B11; odzyskanie partii ma pierwszeństwo. `ui/anime.py:290-296,949-989`. |
| R1-STATE-BUSY | B04/B05/B09 `Enter obejrzyj`, B05 W/T/R/X, wszystkie ekrany O w statusie | R1 | Osobny `_busy` State odrzuca następne polecenie; akcje Anime go nie znają. Komunikat zajętości trafia do nierenderowanego tu State notice. `ui/state.py:489-501,702-724,935-940,1228-1231`; `ui/anime.py:977-1003`. X wraca na listę, ale usunięcie może nie zostać wysłane. |
| R1-EXTRA | B05 na dodatku `Space zaznacz · D pobierz`; pomoc I/P | R1 | Powiązany dodatek jest nawigowalny, lecz eligible=False; Enter otwiera, I/P nie mają akcji. `ui/anime_rows.py:142-149`; `ui/anime.py:977-989,1287-1291`. |
| R1-RELEASE-EMPTY | B06 `Space zaznacz · D pobierz` | R1 | Zastępczy wiersz Szukam/Brak wydania ma eligible=False; nie ma celu pobrania. `ui/anime_releases.py:201`; `ui/anime.py:969-970`; `ui/anime_panel.py:199-204`. |
| R1-RELEASE-UNSUPPORTED | B06 te same segmenty na nieobsługiwanym formacie | R1 | supported=False jest znane przy budowie wiersza, stopka pozostaje, wybór odrzucony. `ui/anime_releases.py:195,264-265`; `ui/anime.py:1765-1767`. |
| R1-FILES-EMPTY | B07 `Enter wybierz` | R1 | Jeśli owner zwróci pusty files, stopka nadal poleca wybór, handler natychmiast wraca. Gałąź potwierdzona kodem; brak danych runtime dowodzących częstości. `ui/anime.py:967-968,1812-1827,1830-1833`. |
| R1-RANGE-ENTER | B08 `Enter zastosuj` | R1 | Po utracie fokusu zachowanego zwykłego zakresu Enter tylko włącza fokus; przy zachowanej nieobserwowanej partii może odtwarzać wynik zamiast zastosować zakres. `ui/anime.py:279-292,1090-1095,1138-1146`; `ui/anime_view.py:560`. |
| R1-RANGE-FILM | B04 Film `Z zakres` w pomocy | R1 | Można otworzyć zakres, ale kolumna number=`Film` jest pomijana przez Decimal, więc żadna liczba nie może być zastosowana. `ui/anime.py:980`; `ui/anime_rows.py:112`; `ui/anime_state.py:241-256`. |
| R1-DETAIL-ACTIONS | B09 treść `Space zaznacz`, `D pobierz`, `Z zakres`, `A wszystkie`, W/R/X/T z U08 | R1 | Pomoc opisuje źródło, ale te klawisze z samego DETAILS nie wykonują wymienionej czynności; brak przejścia do `_subscription_key`. `ui/anime.py:282-288,942`; `ui/anime_panel.py:171-204`; `ui/anime_state.py:223-224`. To podpowiedzi **w pomocy**, nie w stopce C/Esc. |
| R1-DRAFT-ROW | B13 `Enter wybierz · Space zaznacz` | R1 | Objaśnienia mają navigable=True, Enter na nich nic nie robi; Space działa tylko na ep:, choć stopka wyświetla je na przyciskach/objaśnieniach, jeśli są jakiekolwiek odcinki. `ui/anime_rows.py:159-167`; `ui/anime.py:572-590,971-974`. |
| R2-BACK | B11 `Enter/Esc wróć` | R2 | Dwa jawne klawisze powrotu w jednym segmencie; na listowym `_problem_return` ten sam ekran docelowy, przy QUERY dodatkowo różne zachowanie. `ui/actions.py:49-50`; `ui/anime.py:1211-1227`. |
| R3-MORE | B02–B07/B13 `? więcej` | R3 | Przykład właściciela: nie nazywa pomocy ani szczegółów. `ui/actions.py:25`; `ui/anime.py:854-857,934-947`. |
| R3-WAIT | G we wszystkich B; `czeka {N}` | R3 | Bez nazwy oczekujących materiałów i powodu; wspólna obserwacja poprzedniego raportu, tutaj liczona raz. `ui/state.py:132-136,1480-1487`. |
| R3-CATALOG | B05/B09 `Inny sezon w katalogu` / `Katalog wskazuje inny sezon — sprawdzam ponownie` | R3 | Przykład właściciela: nie określa, który sezon/katalog i na czym polega rozbieżność; kod wybiera literal po `catalog_conflict`. `ui/subscription_texts.py:65,177-181`. |
| R3-HASH | B04/B05/B09 `Konflikt hasha` | R3 | Termin implementacyjny identyfikatora torrenta zamiast opisu przeszkody. `ui/anime_texts.py:33`. |
| R3-OLD | B04/B05/B09 `Czeka na stare` | R3 | Nie nazywa starego transferu ani warunku zwolnienia. `ui/anime_texts.py:39`. |
| R3-CHECK | B04/B05/B09 `Kontrola`, `Bez kontroli`, `Kontrola E{n}` | R3 | Same etykiety nie mówią, co jest sprawdzane/pominięte. `ui/anime_texts.py:45-46`; `ui/subscription_texts.py:164`. |
| R3-PROPOSAL | B05/B09 `propozycja zapisana` | R3 | Nie określa gdzie ją zobaczyć ani że nie jest pobraniem; tylko outcome=proposed. `ui/subscription_texts.py:239`. |
| R3-FALSE-ORDER | B06 pusty wiersz, B05 dodatek; `Zlecono \| P pobierz ponownie` | R3 | Fallback dla dowolnego nieeligible bez detail, również dla Brak wydania/Szukam/dodatku; sugeruje wcześniejsze zlecenie bez dowodu. `ui/anime_state.py:108-114`; `ui/anime_releases.py:201`; `ui/anime_rows.py:142-149`. |
| R3-TECH-RELEASE | B06/B09/B12 `Odczyt H1`, `Cel: lokalny`, `S/E`, `absolutny`, `Nazwa franczyzy`, `dopisek sequela`, `Seedy` | R3 | Wymaga znajomości algorytmu, systemów numeracji i słownictwa torrent/anime; pełne literalne warianty R. `ui/anime_releases.py:56,91,294-307`; `ui/anime_view.py:342`. |
| R3-CALIBRATION | B06/B09 `Kalibracja pewności potwierdzona tylko dla korpusu E1…` | R3 | Odwołuje się do nieobjaśnionego korpusu i estymaty/kalibracji. `ui/anime_releases.py:271-274`. |
| R3-RESIDENT | B11 `Rezydent nie wykonał polecenia…`, `Odpowiedź rezydenta jest za duża`, `Sprawdź prywatny klient AniShift i log` | R3 | Nazwy technicznego procesu/klienta i logu nie wskazują konkretnego miejsca dla zwykłego użytkownika. `ui/anime_texts.py:94-107,117-132`. |
| R3-IDENTITY | B12 `Pobrać mimo niepewnej tożsamości?` | R3 | „Tożsamość” oznacza zgodność nazw/metadanych odcinka, bez dopowiedzenia w samym pytaniu. `ui/anime.py:1768-1775`. |
| R3-RANGE-FRACTION | B08 `Zakres: podaj 1,3,7.5 albo 5-` | R3 | Przykład 7.5 sugeruje cel, którego zwykła produkcyjna lista int nie ma; specials U08 są nienawigowalne i nieeligible. `ui/anime_state.py:233,241-258`; `ui/anime_rows.py:131-138`; `app/episode_commands.py:191-195`. |
| R3-SEARCHING | B04/B05/B06 `Trwa wyszukiwanie wydań` | R3 | Wyświetlane także przy `_choice_sending` lub pending partii, więc nie musi oznaczać aktualnego wyszukiwania. `ui/anime.py:916-919`; `ui/anime_panel.py:180-191`. |

**Podsumowanie:** 13 ekranów, każdy z pięcioma wymaganymi sekcjami; **17 R1, 1 R2, 14 R3 = 32 obserwacje** według powyższej jednostki liczenia. Nie stwierdzono osobnego dodatkowego ekranu produkcyjnego poza opisanymi stanami/nakładkami; minimalny terminal jest wariantem renderu C-Anime. Niepewności: brak uruchomienia runtime, dynamiczne dane/wyjątki, warunkowa osiągalność części defensywnych gałęzi oraz ocenny charakter R3. Końcowe `git diff --exit-code` i `git status --short --untracked-files=no` nie wykazały zmian repozytorium. Komplet 13 nagłówków i pięciu sekcji każdego ekranu sprawdzono odczytem; próba automatycznego zliczenia przez `rg -c` była niedostępna (brak programu `rg`), więc liczby tabeli sprawdzono bezpośrednio w pliku.
