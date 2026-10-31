---
kind: plan
status: draft
baseline: AniShift 9c5a418 (work/cli/05-processing-delete; silnik ElevenReader jest w main od ec90f18); ElevenDownloaderPro 7e3fd94 + niezacommitowane src/auto.py (mtime 2026-10-26)
created: 2026-10-31
parent: ../plan.md
---

# Plan: kilka odcinków naraz w ElevenReaderze

Plan dla świeżego wykonawcy. Skróty: **EDP** = `../ElevenDownloaderPro` (tylko do odczytu), **ER** = silnik
`anishift/services/tts/engines/elevenreader/`. Ścieżki bez prefiksu liczą się od roota AniShift. Numery linii
dotyczą baseline'u; po przesunięciu kodu szukaj po symbolu.

## Cel

Lektor ElevenReader nagrywa jednocześnie kilka odcinków (domyślnie 3) zamiast jednego. Liczbę ustawia właściciel w
istniejącym wierszu ustawień lektora. Konto po każdej pracy zostaje czyste: bez wgranych dokumentów, z głosem i
tempem sprzed pracy.

## Rezultat użytkownika

- W Ustawienia → Lektor dla ElevenReadera widać „Syntez jednocześnie” (1–5, domyślnie 3).
- Trzy odcinki gotowe do lektora nagrywają się razem w jednym ukrytym Chrome, każdy w swojej karcie. Jedno
  nagranie trwa jak dziś (ok. 5–6 min na odcinek), więc trzy kończą się mniej więcej w czasie jednego.
- Błąd, anulowanie lub przekroczenie terminu jednego odcinka nie przerywa pozostałych.

## Warunki końcowe

- [ ] N odcinków z różnych runów (Auto: jeden run na odcinek) nagrywa się naraz w jednym procesie Chrome, N = wartość
      ustawienia aktywnego głosu ElevenReadera.
- [ ] Sprzątanie jednego nagrania nigdy nie usuwa dokumentu, który nagrywa inna karta, i nie przywraca ustawień konta,
      dopóki trwa inne nagranie.
- [ ] Anulowanie, timeout lub błąd jednego nagrania zamyka tylko jego kartę.
- [ ] `session.json` ma jednego autora w procesie; żaden zapis nie gubi wpisu innego nagrania.
- [ ] Test na koncie dla 2, 3 i 5 naraz przeszedł albo dał jawny wynik, na podstawie którego ustalono maksimum.
- [ ] Bramki jakości z `AGENTS.md` przechodzą; specyfikacja i pliki `AGENTS.md` opisują nowy stan bez śladu „jeden
      dokument naraz”.

## Nie-cel

- Równoległość innych silników TTS (`_TTS_GROUP_JOBS` dla nich zostaje 1).
- Podnoszenie limitów kompozycji i miksu, nawet jeśli staną się wąskim gardłem (patrz Ryzyka R8).
- Kilka profili Chrome albo kont, żeby dostać osobne identyfikatory urządzenia. To obchodzenie ograniczeń urządzenia,
  zakazane w `intent.md:89`.

## Stan obecny z dowodami

### Silnik ER: dziś zakłada jeden dokument w procesie

- `config.py:42-43` odrzuca `max_concurrency != 1`; `service.py:133` deklaruje `supports_concurrency=False`.
- Każda instancja silnika ma własną przeglądarkę (`service.py:275` `_open_browser` → `_headless_session`) i własną
  kopię zaległego sprzątania wczytaną z `session.json` w konstruktorze (`service.py:156` `load_cleanup`).
- `ChromeSession.start` bierze `ProcessLock` na `chrome.lock` (`browser.py:93-94`). Blokada działa na uchwyt pliku
  (`anishift/platform/process_lock.py:45-55`), więc druga instancja silnika **w tym samym procesie** dostaje
  `ChromeBusyError` (przejściowy, `retry_after_s=UNAVAILABLE_RETRY_S` = 60 s).
- Kilka kart w jednej przeglądarce jest technicznie gotowe: `ChromeSession.new_page` otwiera kartę w kontekście
  profilu (`browser.py:101-107`), skrypt przyspieszenia jest wstrzykiwany do całego kontekstu (`browser.py:161-164`),
  nasłuch strumienia jest per karta (`api_backend.py` `ReaderPage.watch_stream`, `page.on("websocket")`).
- Głos i tempo są ustawieniem konta, nie karty: `prepare_account` zapisuje `default_voice_id` i
  `playback_speed_rate` w `user_config` (`api_backend.py:506-522`); wpis przywrócenia powstaje tylko, gdy go nie ma
  (`:515`).
- `clean_account` (`api_backend.py:525-544`) przywraca ustawienia konta i usuwa **wszystkie** dokumenty z
  `cleanup.documents`. Silnik woła go na starcie próby, gdy coś zalega (`service.py:298`), i po każdej próbie
  (`_end_page`, `service.py:419`). Przy dwóch nagraniach naraz koniec pierwszego usunąłby dokument, który nagrywa
  drugie, i przywróciłby poprzedni głos w trakcie jego pracy.
- Po anulowaniu, timeoucie i niedostępności silnik zamyka całą przeglądarkę (`_KEEP_BROWSER_ERRORS`,
  `service.py:115`; `keep_browser`, `:237-240`). We wspólnej przeglądarce zabiłoby to pozostałe nagrania.
- `upload`, `prepare_account`, `write_session` i `save_cleanup` robią odczyt–zmianę–zapis `session.json`
  (`api_backend.py:302-313`, `:694-710`) bez blokady między wątkami.

### Warstwa aplikacji: dziś TTS jednego pliku naraz w całym rezydencie

- Auto startuje osobny run dla każdego odcinka (`application/automation.py:1479-1483`, `plan_auto((group.group_id,))`).
- Każdy run buduje własny `TtsService` (`application/runtime.py:237`), a ten ma własny wątek `anishift-tts` z własną
  pętlą asyncio (`services/tts/service.py:600-619`) i leniwie tworzy własny silnik (`:634`). Silniki różnych runów
  żyją więc na różnych wątkach i pętlach. Obiekty async Playwright są związane z pętlą, która je utworzyła, więc
  jednej przeglądarki Playwright nie da się po prostu przekazać między nimi.
- Koordynator grafu jest wspólny dla runów i limituje taski per zasób (`application/AGENTS.md`, sekcja
  „Workspace, planowanie i wykonanie”). Dla `tts:*` limit to `tts_group_jobs` (`scheduler_contracts.py:147`), a ten
  jest stałą `_TTS_GROUP_JOBS = 1` (`application/service.py:121`, `:1081`). Klucz zasobu taska TTS to
  `tts:<silnik>` (`planner.py:836`).
- Dla silnika dokumentowego `_tts_config` wymusza `max_concurrency=1`, `queue_capacity=2`
  (`application/runtime.py:670-677`); scheduler TTS ma tyle workerów, ile `max_concurrency`
  (`services/tts/scheduler.py:116`). W jednym batchu dokumenty i tak idą po kolei (`services/tts/service.py:1056-1072`).
- Token anulowania TTS jest niezależny od pętli (`services/tts/cancellation.py:35-36`), więc można na niego czekać
  z innej pętli. Callback postępu dokumentu (`request.progress`) żyje na pętli `TtsService`
  (`services/tts/service.py:255-261`) i z innej pętli trzeba go wywoływać przez `run_coroutine_threadsafe`.
- Wniosek z kodu (nie zmierzony): run trzyma Chrome otwarty do swojego końca (zamknięcie przy `close` handlera,
  `application/tts_handler.py:373-375`), więc TTS następnego runu, wpuszczony w czasie miksu lub kompozycji
  poprzedniego, dostaje dziś `ChromeBusyError` i czeka w backoffie `60/120/300 s` (`application/runtime.py:134-137`).
  Wspólna przeglądarka z tego planu usuwa też to czekanie.

### Ustawienia

- Profil głosu ma już pole `concurrency` (`config/user_settings.py:195-204`); dla obu głosów ER domyślnie 1
  (`:249-252`). W panelu to wiersz „Syntez jednocześnie” w grupie WYDAJNOŚĆ (`cli/interactive/settings.py:254`),
  ukryty dla `elevenreader` i `sapi` (`config/field_catalog.py:1017`). Maksimum per silnik liczy
  `_tts_concurrency_max` (`field_catalog.py:1364-1367`), wzorem `VPN_MAX_CONCURRENCY` z `elevenbytes/vpn.py`.
- Snapshot runu bierze `profile.concurrency` jako `tts_request_concurrency` (`application/service.py:1072`).
- `config/settings.json` właściciela (odczyt 2026-10-31) ma zapisane `concurrency: 1` dla obu profili ER, więc zmiana
  wartości domyślnej w kodzie go nie obejmie.
- Specyfikacja zakazuje dziś równoległości: `specification.md:79` (U9), `:201` (O3); U14 (`:86`) wymaga sprzątania po
  każdej próbie.

## Jak robi to ElevenDownloaderPro

- **Jedna przeglądarka, jeden kontekst, karta na dokument.** `auto.py:339` bierze `connect(pw).contexts[0]` (profil),
  `auto.py:264` otwiera dla każdego dokumentu nową kartę `main_page.context.new_page()`. Skrypt przyspieszenia idzie na
  cały kontekst (`auto.py:340`).
- **Audio per karta.** Każda praca ma własny `Recorder` i własny nasłuch `page.on("websocket", …)`
  (`auto.py:174`, `:184`). Karty się nie mieszają, bo zdarzenie WebSocket należy do karty.
- **Start po kolei, nagrywanie razem.** Upload i ustawienie tempa 1x idą z głównej karty jeden po drugim
  (`auto.py:256-272`, `begin`); pętla `run_all` dokłada nowe prace, dopóki aktywnych jest mniej niż `parallel`, i co
  1 s robi krok każdej aktywnej (`auto.py:275-307`). Odstęp między startami wynika tylko z czasu uploadu i otwarcia
  dokumentu (zmierzone niżej: ok. 22–24 s).
- **Ustawienia konta.** EDP ustawia tylko `playback_speed_rate = 1` przed każdym dokumentem (`auto.py:146-159`). Głosu
  nie zmienia (czyta domyślnym głosem konta), niczego nie przywraca i nie usuwa dokumentów z biblioteki. Problemu
  sprzątania konta przy kilku nagraniach naraz EDP więc nie rozwiązuje; ten plan musi go rozwiązać sam.
- **Limity i ponowienia.** Niedostępna biblioteka: ponowienie co minutę do 120 min (`auto.py:118-131`). Brak audio po
  Play: do 3 naciśnięć co 60 s (`:80-84`). Brak postępu 5 min: porażka bez ponowienia, plik do `failed/` (`:86`,
  `:228-253`). Żadnego limitu ani opóźnienia specyficznego dla równoległości.
- **Ustawienie.** `--parallel N`, domyślnie 1 (`auto.py:323`).
- **Pomiary i sprzeczność.** README EDP (`README.md:145`) i `docs/report.md:32-33`: jedna karta ok. 4,5–5,5x czasu
  rzeczywistego, 2 karty ≈ 11x, 3 ≈ 17x łącznie (2026-10-17/18). Ten sam zapis mówi, że 2026-10-19 nowy strumień
  zamykał starszy (4 karty → zamknięte 2, 2 karty → zamknięta 1; „wszystkie karty mają ten sam identyfikator
  urządzenia”) i zaleca jeden plik naraz.
- **Późniejszy dowód z plików (wniosek z czasów, log nie przetrwał).** `workspace/output/MS3_006.mp3`, `MS3_007.mp3`,
  `MS3_008.mp3` powstały 2026-10-29 o 23:44:44, 23:45:06 i 23:45:30, a skończyły się 2026-10-30 o 00:09:06, 00:03:35 i
  00:06:39. Wszystkie trzy wejścia są w `workspace/input/done/`, `failed/` jest pusty. To trzy nagrania naraz
  zakończone sukcesem: ok. 112, 96 i 95 min audio (przy 128 kb/s) w 18–24 min, czyli 4,5–5,2x na kartę i ok. 12x
  łącznie. Pięciu naraz nikt nie mierzył.

## Luka

Samo podniesienie limitów (`_TTS_GROUP_JOBS`, `max_concurrency`) nie zadziała i zepsuje konto:

1. drugi run dostanie `ChromeBusyError`, bo każdy silnik startuje własny Chrome na tym samym profilu;
2. gdyby wystartował, `clean_account` jednego runu usunie dokument drugiego i przywróci głos w trakcie jego pracy;
3. kilka kopii `AccountCleanup` nadpisuje sobie `session.json`;
4. timeout jednego nagrania zamknie przeglądarkę wszystkim.

Brakuje jednego właściciela przeglądarki i stanu konta na proces, wspólnego dla silników z różnych runów.

## Projekt zmiany

### Decyzja: wspólny gospodarz przeglądarki w procesie

W pakiecie ER powstaje gospodarz (`hub.py`, nazwa klasy do wyboru wykonawcy, np. `ReaderHub`): jeden na
`profile_root` w procesie, z **własnym wątkiem i własną pętlą asyncio**. Na tej pętli żyją: `ChromeSession`, wszystkie
karty, `AccountCleanup` i każdy zapis `session.json`. Silniki z różnych runów nie dotykają Playwright bezpośrednio;
zlecają gospodarzowi całą próbę nagrania i czekają na wynik.

Dlaczego tak:

- jedna pętla = jeden wątek dla całego stanu konta, więc bez blokad międzywątkowych wokół `session.json` i sprzątania;
- istniejący kod async (`ReaderPage`, `prepare_account`, `clean_account`, `_record`) zostaje prawie bez zmian, tylko
  zmienia pętlę;
- zmiana zostaje w silniku ER plus kilka linii wiązania w aplikacji.

Odrzucone:

- **wspólny `TtsService` dla wszystkich runów** — wymaga przebudowy aplikacji (`resume_root` per run, zamykanie
  serwisu przy końcu runu), duża zmiana poza silnikiem;
- **osobne połączenie CDP z każdej pętli do jednego Chrome** — stan konta byłby współdzielony między wątkami i
  wymagałby blokad trzymanych przez `await`;
- **osobny profil Chrome na nagranie** — osobne logowanie każdego profilu i obchodzenie ograniczenia urządzenia
  (zakaz z `intent.md:89`).

### Gospodarz: odpowiedzialności i cykl życia

- Rejestr procesowy `{profile_root: gospodarz}` pod `threading.Lock`. Silnik w konstruktorze bierze referencję
  (`acquire`), w `close()` ją oddaje (`release`). Licznik referencji = liczba żywych silników ER w procesie.
- Pierwsza referencja: start wątku i pętli, `load_cleanup` raz. Chrome startuje leniwie przy pierwszym nagraniu (jak
  dziś `_open_browser`).
- Ostatnia referencja: na pętli gospodarza zaległe sprzątanie w nowej karcie, jeśli Chrome żyje (dziś
  `_clean_in_new_tab`), zapis, ostrzeżenie `CLEANUP_WARNING`, jeśli coś zostało, zamknięcie Chrome i zwolnienie
  `chrome.lock`, zatrzymanie pętli i wątku. Silnik czeka na to w granicy `shutdown_deadline_s`, jak dziś.
- Stan gospodarza: `ChromeSession | None`, `AccountCleanup`, blokada startu (`asyncio.Lock`), liczba aktywnych nagrań i
  głos aktywnych nagrań (`asyncio.Condition`), zbiór śladów dokumentów należących do aktywnych nagrań, flaga
  „przeglądarka podejrzana”.
- Playwright nadal ładuje się leniwie: `hub.py` importuje `browser.py` w funkcji, jak dziś `_headless_session`.
  Test importu pakietu z `test_tts_contract.py` musi dalej przechodzić.

### Przebieg jednej próby

Silnik (`synthesize_document`) waliduje żądanie jak dziś, potem zleca próbę gospodarzowi
(`asyncio.run_coroutine_threadsafe` + `asyncio.wrap_future`) i czeka na wynik pod `_unless_cancelled`. Postęp
(`request.progress`) gospodarz wysyła na pętlę silnika przez `run_coroutine_threadsafe`, nie wywołuje go u siebie.

Na pętli gospodarza:

1. **Bramka głosu** (poza terminem dokumentu, pod anulowaniem): wejście, gdy nie ma aktywnych nagrań albo aktywne mają
   ten sam głos. Inny głos czeka na koniec aktywnych i loguje `logger.info` raz przy rozpoczęciu czekania. Po wejściu:
   licznik aktywnych +1.
2. **Przeglądarka:** start, jeśli nie żyje. Jeśli jest podejrzana i aktywnych nie ma poza bieżącym nagraniem, restart
   przed otwarciem karty.
3. **Karta i termin:** nowa karta; od tego miejsca działa `_within_deadline(request.deadline_s)` jak dziś.
4. **Faza startu pod blokadą startu:** `require_signed_in`; zaległe dokumenty z poprzednich runów, z pominięciem
   śladów aktywnych nagrań (przywrócenia ustawień tu nie ma, patrz niżej); `upload` (ślad trafia też do zbioru
   aktywnych); `prepare_account`; `watch_stream`; `open_document`; tempo strony; Play. Blokadę zwalnia pierwszy adres
   strumienia z głosem (serwer wybiera głos i model przy starcie strumienia) albo upływ `START_TIMEOUT_S`. Starty
   idą więc jeden po drugim, jak w EDP, a nagrywanie biegnie równolegle.
5. **Nagrywanie:** istniejące `_record`, `_finished`, `_result` bez zmian semantyki.
6. **Koniec (`finally`, pod `_finish_shielded`):** odpięcie nasłuchu; usunięcie **własnego** dokumentu (`delete_read`
   po `read_id` albo wyszukanie sieroty po własnym śladzie); usunięcie śladu ze zbioru aktywnych; licznik −1; gdy
   licznik = 0: przywrócenie ustawień konta i pozostałe zaległe kroki; zapis `session.json`; zamknięcie karty;
   powiadomienie bramki głosu.

Inwariant: `synthesize_document` kończy się (wynikiem albo błędem) dopiero, gdy krok 6 tej próby się wykonał. Przy
anulowaniu zadania silnika anuluj future gospodarza i poczekaj na jego koniec osłonięty (`asyncio.shield`), jak w
`_finish_shielded`.

### Sprzątanie konta przy kilku nagraniach

- Jeden `AccountCleanup` na proces, w gospodarzu. Silnik nie ma już własnego (`service.py:156` znika).
- `clean_account` dostaje dwie jawne granice: zbiór śladów do pominięcia (aktywne nagrania) i to, czy wolno przywrócić
  ustawienia (tylko przy zerze aktywnych). Wykonawca może zamiast tego rozdzielić funkcję na „usuń dokumenty” i
  „przywróć ustawienia”; jedna wersja, bez starej obok.
- Przywrócenie przy zerze aktywnych jest poprawne także po awarii: zaległy wpis `restore` z poprzedniego procesu
  zostaje do końca ostatniego nagrania, a `prepare_account` go nie nadpisuje (`api_backend.py:515`), więc wraca głos
  właściciela, nie nasz.
- Szukanie sieroty (`_delete_orphan`) zostaje bez zmian: rozróżnia uploady po oknie czasu i skrócie tytułu, a tytuły
  odcinków są różne. Dwa jednakowe tytuły w oknie dają dziś ostrzeżenie i krok zaległy; to zachowanie zostaje.

### Błędy, anulowanie, termin

- Każdy błąd jednej próby zamyka tylko jej kartę. `_KEEP_BROWSER_ERRORS` i logika `keep_browser` znikają.
- Timeout, niedostępność i anulowanie oznaczają przeglądarkę jako podejrzaną (zachowanie dzisiejszego restartu po tych
  błędach); restart następuje w kroku 2, gdy żadne inne nagranie nie trwa. Martwy Chrome (`alive == False`) kończy
  błędem wszystkie aktywne nagrania i startuje od nowa przy następnej próbie.
- Termin dokumentu (`request.deadline_s`, 3600 s) nie obejmuje czekania w bramce głosu; scheduler ma dla tego silnika
  wyłączony własny timeout (`application/runtime.py:676`), więc jedynym ograniczeniem czekania jest anulowanie.
- Ponowienia zostają w schedulerze TTS (backoff `60/120/300/600 s`); gospodarz niczego sam nie ponawia.

### Ustawienie

- Wykorzystać istniejące `tts_profile.concurrency` profilu głosu. Dla ER znaczy „dokumentów (odcinków) naraz”; każdy
  dokument to jedna synteza, więc etykieta „Syntez jednocześnie” pasuje bez zmian.
- `field_catalog.py:1017`: warunek ukrywania tylko dla `sapi`. Opis specyfikacji dla ER: liczba odcinków nagrywanych
  naraz. `_tts_concurrency_max`: dla ER stała `MAX_PARALLEL_DOCUMENTS` z `elevenreader/constants.py` (5 przed
  pomiarem; po K1 = największe N, które przeszło).
- `default_tts_voice_profiles`: `concurrency=3` dla Fronczewskiego i Adama.
- Wartość właściciela: w `config/settings.json` jest 1. Właściciel ustawia 3 w panelu po wdrożeniu (wiersz staje się
  widoczny). Format się nie zmienia, więc bez skryptu migracji.

### Wiązanie w aplikacji

- `application/service.py` `_run_settings_snapshot`: dla silnika dokumentowego (`is_document_engine`)
  `tts_group_jobs = request_concurrency`; dla pozostałych `_TTS_GROUP_JOBS` (1) bez zmian. Koordynator czyta limity z
  bieżących preferencji (`service.py:604-605`), więc zmiana w panelu działa od następnego wpuszczenia taska.
- `application/runtime.py` `_tts_config`: z gałęzi silnika dokumentowego znika wymuszenie `max_concurrency=1` i
  `queue_capacity=2`; zostaje `scheduler_timeout_enabled=False` i `shutdown_deadline_s`. Run z kilkoma odcinkami
  (Ręczny) też nagrywa je naraz.
- `ElevenReaderConfig.from_tts_config`: przyjmuje `1 ≤ max_concurrency ≤ MAX_PARALLEL_DOCUMENTS`, poza zakresem
  `TtsConfigError` z poprawioną sugestią. `capabilities.supports_concurrency=True`.
- `scheduler_contracts.py` bez zmian (`tts:*` → `tts_group_jobs`).

## Mapa plików

```text
anishift/services/tts/engines/elevenreader/
├── hub.py           # CREATE  gospodarz: wątek+pętla, rejestr per profil, Chrome, AccountCleanup, bramka głosu, blokada startu
├── service.py       # MODIFY  silnik zleca próbę gospodarzowi; bez własnego Chrome i AccountCleanup; bez _KEEP_BROWSER_ERRORS
├── api_backend.py   # MODIFY  clean_account z pominięciem aktywnych śladów i warunkiem przywrócenia
├── config.py        # MODIFY  zakres max_concurrency 1..MAX_PARALLEL_DOCUMENTS
├── constants.py     # MODIFY  MAX_PARALLEL_DOCUMENTS
├── browser.py       # KEEP    (ewentualnie tylko to, czego wymaga restart z gospodarza)
└── AGENTS.md        # MODIFY  granice: gospodarz, sprzątanie przy wielu nagraniach, zamykanie tylko karty
anishift/application/
├── service.py       # MODIFY  tts_group_jobs z profilu dla silnika dokumentowego
├── runtime.py       # MODIFY  _tts_config bez wymuszenia 1 dla silnika dokumentowego
└── AGENTS.md        # MODIFY  „TTS jeden plik naraz” → wyjątek silnika dokumentowego
anishift/config/
├── user_settings.py # MODIFY  concurrency=3 dla profili ER
└── field_catalog.py # MODIFY  wiersz widoczny dla ER, maksimum MAX_PARALLEL_DOCUMENTS
docs/work/11-elevenreader-tts/
└── specification.md # MODIFY  U9, O3, U14 (+ F28, jeśli opisuje kolejność sprzątania)
tests/services/tts/  # MODIFY/CREATE testy silnika i gospodarza (elevenreader_fakes.py, test_tts_elevenreader_*.py)
tests/application/   # MODIFY  test_runtime_config.py (:189-229), testy snapshotu
tests/config/        # MODIFY  test_field_catalog.py (:355), test_user_settings.py
```

Bez nowych zależności. Bez zmian w `scheduler_contracts.py`, plannerze i panelu poza wierszem ustawień.

## Kolejność wykonania

### Faza 0: preflight

1. Przeczytaj `../plan.md` §7, `../specification.md` (U9–U14, F28), `anishift/services/tts/engines/elevenreader/AGENTS.md`,
   `anishift/services/tts/AGENTS.md`, `anishift/application/AGENTS.md`, ten plan.
2. Bramki z `AGENTS.md` na baseline; zapisz istniejące porażki.
3. Rezydent działa z tego checkoutu: przed zmianą plików, które czyta, i przed testem na koncie właściciel go
   zamyka.

Gate: zielony baseline albo spisane wcześniejsze porażki.

### Faza 1: gospodarz i silnik (pakiet ER)

`hub.py`, zmiany w `service.py`, `api_backend.py`, `config.py`, `constants.py`; testy jednostkowe z listy niżej na
fałszywej stronie (`tests/services/tts/elevenreader_fakes.py`: `FakeSite`, `FakeSession`, `fake_engine` z
`browser_factory`).

Inwarianty: Playwright tylko w `browser.py` na poziomie modułu; token, `read_id`, adres strumienia i tekst nie trafiają do
logów; `session.json` pisze tylko pętla gospodarza.

Gate: testy pakietu ER i `test_tts_contract.py` zielone.

### Faza 2: aplikacja, ustawienia, dokumenty

`application/service.py`, `application/runtime.py`, `config/user_settings.py`, `config/field_catalog.py`; aktualizacja
`specification.md` (U9: „Jedna przeglądarka, do N dokumentów naraz w osobnych kartach”; O3; U14: dokument usuwany po
każdej próbie, ustawienia konta przywracane po ostatnim aktywnym nagraniu) i trzech `AGENTS.md`. Stare zdania znikają
w tym samym diffie.

Gate: pełne bramki z `AGENTS.md`.

### Faza 3: test na koncie (K1, agent)

Opis w sekcji „Test na koncie”. Wynik ustala `MAX_PARALLEL_DOCUMENTS` i potwierdza domyślne 3.

### Faza 4: odbiór właściciela (K2)

Opis niżej. Po K2 właściciel decyduje o merge'u.

## Test na koncie

Koszt: znaki dokumentów. Plan zakłada ok. 8 000 znaków na dokument, czyli ok. 0,8 kredytu (1 kredyt = 10 000 znaków,
`EDP docs/report.md:35`); 2 + 3 + 5 = 10 dokumentów ≈ 8 kredytów. Wymaga zgody właściciela (P1).

### K1: pomiar 2, 3 i 5 naraz (agent, rezydent zamknięty)

- Nowy test sieciowy obok `tests/services/tts/test_tts_elevenreader_network.py` (te same markery i
  `ANISHIFT_ELEVENREADER_LIVE=1`), parametryzowany N ∈ {2, 3, 5}. Każdy dokument przez **osobny `TtsService` w
  osobnym wątku**, żeby sprawdzić gospodarza tak jak w rezydencie (różne pętle).
- Dokumenty muszą być różne w każdej rundzie i między rundami: ten sam tekst wraca z pamięci serwera ok. 58x szybciej i
  bez kredytów (`EDP docs/report.md:38`), co sfałszowałoby pomiar. ~8 000 znaków daje ok. 8–9 min audio i ok. 2 min
  nagrywania na kartę; przy starcie co ok. 20–25 s pięć kart nagrywa razem przez większość czasu.
- Zapisz dla każdego N: czas ściany, czas audio i przepustowość na kartę oraz łącznie; liczbę zamknięć strumienia,
  utknięć (`stalled`) i ponowień; `chars` vs `char_count`; pik RAM i CPU procesów `chrome` (próbkowanie co 5 s);
  stan konta po teście: brak naszych dokumentów na pierwszej stronie `GET reads`, `default_voice_id` i
  `playback_speed_rate` jak przed testem.
- Wynik do `docs/work/11-elevenreader-tts/outcomes/02-parallel-documents.md` (po polsku).

PASS dla danego N: wszystkie dokumenty kompletne bez ponowień, brak zamkniętych strumieni, łączna przepustowość
wyraźnie rośnie z N, konto czyste. Maksimum = największe N, które przeszło. Jeśli nie przechodzi już N = 2 (powtórka
zjawiska z 2026-10-19), zatrzymaj pracę i wróć do właściciela: równoległość na jednym urządzeniu nie działa, a jej
obejście jest zakazane.

### K2: odbiór na prawdziwych odcinkach (właściciel)

```text
Uruchom:    anishift; Ustawienia → Lektor (ElevenReader) → „Syntez jednocześnie” = 3.
Zrób:       wrzuć do workspace 3 odcinki gotowe do lektora (albo poczekaj na 3 z subskrypcji) i zostaw Auto.
Oczekiwane: trzy nagrania startują w odstępie kilkudziesięciu sekund i kończą się razem w ok. 6–7 min;
            w bibliotece ElevenReadera nie zostaje żaden dokument; głos konta jak przed startem.
Uwaga na:   powtórzone lub ucięte zdania w lektorze, błędy „stalled” w Przetwarzaniu, obciążenie komputera.
Przekaż:    czasy z logu (`ElevenReader document recorded`, elapsed_ms), zrzut Przetwarzania, ocenę odsłuchu
            jednego odcinka. Potem to samo dla 5, jeśli K1 przeszło dla 5.
```

## Testy jednostkowe

Na fałszywej stronie i fałszywej sesji, bez sieci i bez Chrome:

1. `ElevenReaderConfig`: przyjmuje 1 i `MAX_PARALLEL_DOCUMENTS`, odrzuca 0 i maksimum + 1.
2. Dwa silniki na dwóch pętlach w dwóch wątkach nagrywają naraz: fabryka przeglądarki wywołana raz, dwie karty, oba
   wyniki poprawne.
3. Faza startu jest szeregowana: upload drugiej próby zaczyna się po pierwszym adresie strumienia pierwszej.
4. Koniec próby A przy trwającej B usuwa tylko dokument A, nie przywraca ustawień; koniec B przywraca ustawienia;
   `session.json` po każdym kroku zgadza się ze stanem.
5. Zaległy dokument z poprzedniego procesu znika na starcie próby, a ślad aktywnej próby nie.
6. Bramka głosu: próba z innym głosem czeka, aż aktywne skończą; `prepare_account` dla niej biegnie po przywróceniu
   lub zakończeniu poprzednich.
7. Anulowanie A zamyka tylko kartę A; B kończy się sukcesem; dokument A usunięty.
8. Timeout A przy trwającej B nie zamyka Chrome; następna próba po końcu B dostaje świeży Chrome.
9. Zamknięcie pierwszego silnika nie zamyka Chrome; zamknięcie ostatniego robi zaległe sprzątanie, zamyka Chrome,
   zwalnia `chrome.lock` i kończy wątek gospodarza.
10. Postęp dokumentu trafia na pętlę silnika (callback sprawdza `asyncio.get_running_loop()`).
11. Aplikacja: `_run_settings_snapshot` dla ER daje `tts_group_jobs` = `concurrency` profilu, dla `elevenbytes` 1;
    `_tts_config` dla ER ma `max_concurrency = N`, `queue_capacity = max(2, 2N)`, wyłączony timeout schedulera;
    `worker_limit("tts:elevenreader")` = N.
12. Ustawienia: katalog pokazuje wiersz dla ER z maksimum `MAX_PARALLEL_DOCUMENTS` i domyślnym 3; `sapi` nadal ukryte;
    domyślne profile ER mają 3.

Istniejące testy, które kodują stary kontrakt „jeden dokument” (`test_runtime_config.py:189-229`,
`test_field_catalog.py:355`, testy `max_concurrency` w `test_tts_elevenreader_config.py`), przechodzą na nowy
kontrakt w tym samym diffie.

## Ryzyka

- **R1. Serwer zamyka starszy strumień przy nowym (EDP, 2026-10-19).** Objaw: koniec audio w jednej karcie, `stalled`
  po 300 s, ponowienie dokumentu. Reakcja: K1 to wykrywa; maksimum = największe N bez tego zjawiska; przy N = 2
  stop i decyzja właściciela. Dowód przeciwny: udane trzy naraz 2026-10-29 (pliki MS3_006–008).
- **R2. Limit urządzenia lub blokada konta.** Konto ma włączone `device_rate_limit_enabled` i `ip_ban_check_enabled`
  (`EDP docs/research/capabilities.md:64`, `:152`). Więcej strumieni naraz to większy ślad automatu. Ryzyko regulaminu
  jest już przyjęte w `intent.md:38`; równoległość go zwiększa, nie zmienia jego natury. Nie obchodzimy żadnego
  limitu.
- **R3. Różne głosy w kolejce.** Głos jest ustawieniem konta. Bramka głosu nie pozwala nagrywać dwoma głosami naraz;
  run z innym głosem czeka (log), nie psuje cudzego nagrania.
- **R4. Sprzątanie po przerwaniu kilku nagrań.** Każda próba usuwa swój dokument w `finally`; ustawienia wracają po
  ostatniej. Zabicie procesu w trakcie zostawia ślady w `session.json`; następne uruchomienie sprząta je jak dziś
  (dokumenty po `read_id`, sieroty po oknie i tytule, `restore` przed pierwszym `prepare_account`).
- **R5. Ponowienie dokumentu kosztuje znaki.** Przy R1 ponowione dokumenty mogą zużyć kredyty drugi raz, jeśli serwer
  nie poda ich z pamięci. Reakcja: K1 mierzy saldo przed i po (opcjonalnie `GET customer`).
- **R6. Obciążenie komputera.** Każda karta dekoduje audio przy 64x. Liczb nie mamy; K1 mierzy pik RAM i CPU, K2 ocenia
  właściciel. Za duże obciążenie obniża domyślną wartość, nie zmienia projektu.
- **R7. Ukryte karty w tle.** Nie wiadomo, czy headless Chrome dławi timery kart w tle przy kilku kartach. Objaw:
  wolniejsze nagrania albo zawieszony odtwarzacz w K1. Reakcja: flagi Chrome przeciw dławieniu tła w `browser.py`
  (decyzja lokalna wykonawcy, z testem argumentów).
- **R8. Nowe wąskie gardło.** Kompozycja ma limit 1, miks 2 (`scheduler_contracts.py` `from_settings`). Trzy odcinki
  po TTS mogą czekać na kompozycję. Poza zakresem; K2 pokaże, czy to odczuwalne.
- **R9. Wątek gospodarza nie kończy się.** Ostatnie `release` musi zatrzymać pętlę i wątek; test 9. Właściciel nie
  chce procesów w tle po zamknięciu aplikacji.

## Zakres wykonania

- **Forbidden:** wiele profili Chrome, kont lub sztuczne identyfikatory urządzenia; zmiana limitów innych silników;
  stara ścieżka „jeden Chrome na silnik” obok nowej; aliasy starych nazw; ręczna edycja `pyproject.toml`; uruchamianie
  rezydenta albo testu na koncie bez zamknięcia rezydenta i zgody na koszt (P1).
- **Dozwolone decyzje lokalne:** nazwy modułu i klas gospodarza, podział `clean_account`, dokładny moment zwolnienia
  blokady startu w granicach opisanych wyżej, flagi Chrome z R7, opis pozycji w katalogu ustawień.
- **Zatrzymaj się i wróć, gdy:** K1 nie przechodzi dla N = 2; okaże się, że strumień nie niesie głosu w adresie (bramka
  głosu nie może się na nim oprzeć); test 2 pokaże, że Playwright nie działa z pętli w osobnym wątku; zmiana zaczyna
  wymagać przebudowy `TtsService` albo koordynatora grafu.

## Pytania do właściciela

- **P1.** Zgoda na koszt K1: ok. 8 kredytów (10 dokumentów po ok. 8 000 znaków). Inne pytania nie blokują planu;
  domyślną i maksymalną liczbę ustala pomiar K1 i odbiór K2.

## Definition of Done

- [ ] warunki końcowe spełnione;
- [ ] bramki z `AGENTS.md` przeszły (`ruff check`, `ruff format --check`, `mypy`, `pytest` na `anishift/ tests/`);
- [ ] K1 zapisany w `outcomes/02-parallel-documents.md`, `MAX_PARALLEL_DOCUMENTS` zgodne z wynikiem;
- [ ] K2 przyjęty przez właściciela;
- [ ] review innego modelu niż autor kodu (zasada krzyżowa z `AGENTS.md`);
- [ ] w produkcie, testach i dokumentach nie zostało zdanie ani kod „jeden dokument naraz”.
