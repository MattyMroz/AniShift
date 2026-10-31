# services/tts/engines/elevenreader

Silnik dokumentowy: jedna próba wgrywa dokument odcinka do ElevenReadera, nagrywa strumień w Chrome i zwraca
nagranie MP3 z czasami części (`PartTiming`). Cięcie na klipy robi wstrzyknięty `ClipSplitter`, nie silnik.

## Moduły

- Standard sióstr: `config.py`, `constants.py`, `types.py`, `service.py` (silnik, `document_text`, `part_spans`)
  i `api_backend.py` (karta Playwright: `ReaderPage`, konto, sesja, mapowanie błędów dostawcy).
- Specyficzne: `browser.py` (proces Chrome i CDP, jak `sapi/worker.py`; tu też `ChromeMissingError` i
  `ChromeBusyError`, jak `VpnError` w `elevenbytes/vpn.py`) oraz `recorder.py` (czyste ramki WebSocket → MP3 i
  czasy znaków, testowane bez przeglądarki).

## Granice

- Na poziomie modułu Playwright importuje tylko `browser.py`. `api_backend.py` ładuje go leniwie
  (`_playwright_error`, `_playwright_timeout`, import `browser` w `sign_in`), a `service.py` ładuje `browser.py`
  w `_headless_session`. Pilnuje tego test w `test_tts_contract.py` i test importu pakietu w procesie potomnym.
- `find_chrome`, `profile_dir` i `session_file` leżą w `config.py`, żeby doctor i panel nie ładowały Playwright.
- `ChromeSession` startuje Chrome z `--user-data-dir=config/elevenreader/chrome-profile` (Chrome 136+ ignoruje
  CDP dla domyślnego profilu) na wolnym porcie i dołącza `connect_over_cdp`. Proces jest zwykłym dzieckiem
  rezydenta (bez breakaway), więc Job Object kończy go razem z rezydentem.
- `ChromeSession.close` najpierw prosi Chrome o wyjście przez CDP (`Browser.close`) i czeka do 10 s; `terminate`
  i `kill` są tylko zapasem. Chrome zapisuje ciasteczka na dysk z opóźnieniem do ok. 30 s, więc twarde zabicie
  zaraz po zalogowaniu gubi sesję (K2: `signed_in: true` w `session.json`, a profil wylogowany).
- Nagrywanie, sprzątanie i sprawdzanie sesji przez silnik działają tylko z `headless=True` (`_headless_session`);
  okno widać wyłącznie w `sign_in`. Skrypty diagnostyczne też nie otwierają okna.
- `ProcessLock` na `chrome.lock` wyklucza drugą przeglądarkę na profilu: zajęty → `ChromeBusyError`
  (przejściowy); w `sign_in` → `SignInOutcome.BUSY`. `restrict_directory` przy każdym starcie.
- `ReaderPage` jest jedynym miejscem z selektorami i wywołaniami Playwright. Każdy błąd Playwright idzie przez
  `map_playwright_error` z `from None`, bo komunikat Playwright potrafi zawierać adres z `read_id`.

## Konto i sprzątanie

- Głos i tempo 1x ustawia `user_config` konta tokenem strony (`prepare_account`), przed otwarciem dokumentu:
  serwer wybiera model przy starcie strumienia. Wpis przywrócenia powstaje przed zapisem i nie jest
  nadpisywany, dopóki poprzedni nie wykona się, inaczej „poprzednim” głosem zostałby nasz.
- `AccountCleanup` (przywrócenie ustawień, `DELETE reads/{id}`, sierota po oknie wgrania i tytule) biegnie przez
  `clean_account` w `finally` każdej próby pod `_finish_shielded`, także po `asyncio.CancelledError`; każdy krok ma
  własny limit i `_cleanup_step` łapie każdy wyjątek, a karta i Chrome zamykają się w `finally`. Nieudany krok zostaje
  i wykonuje się po `require_signed_in` następnej próby (przed uploadem), w `close()`, jeśli przeglądarka żyje, oraz w
  `sign_in` panelu. Trwała porażka: `logger.warning(CLEANUP_WARNING, steps=…)`, wiersz w SESJA i ostrzeżenie doctora.
- `upload` dopisuje `DocumentTrace` każdego wgrania (`pressed_at` i `listed_by` jako czas zegarowy `time.time()`,
  skróty SHA-256 możliwych tytułów z `document_titles`) i zapisuje go przed „Upload”, a `read_id` z odpowiedzi
  wpisuje do śladu przed walidacją `char_count`/tokenu. Dokument ze znanym `read_id` znika przez `DELETE reads/{id}`,
  także po restarcie, bo `read_id` jest zapisany w `session.json`.
- Tylko upload bez odpowiedzi z `read_id` (anulowanie w trakcie uploadu, odpowiedź bez id) szuka się w pierwszej
  stronie `GET reads`: `from_user_import is True`, `original_file_type == "text/plain"`, `added_at_unix` w
  `[pressed_at − 300 s, listed_by + 300 s]` i skrót znormalizowanego `title` wśród skrótów śladu. Serwer bierze tytuł
  z pierwszego zdania treści, nie z nazwy pliku, więc ślad trzyma skróty każdego prefiksu dokumentu na granicy słów
  do 200 znaków. Jeden kandydat → `DELETE`; kilku → nic nie usuwa, ostrzeżenie, krok zostaje zaległy; zero przed
  `listed_by` → krok zostaje; zero po `listed_by` → krok rozliczony z `logger.warning`, że upload mógł zostać na
  koncie (z liczbą importów w oknie, bez tytułu i tekstu).
- Zaległe sprzątanie jest trwałe w prywatnym `session.json` (`restore`, `documents`: `pressed_at`, `listed_by`,
  `titles`, `read_id`): `prepare_account` i `upload` zapisują je przed zmianą konta, silnik po każdym sprzątaniu,
  `load_cleanup` wczytuje je przy starcie. Czas zegarowy zachowuje okno wgrania po restarcie procesu i komputera.
- Przeglądarka zostaje otwarta po sukcesie i po błędach, które jej nie dotyczą (`_KEEP_BROWSER_ERRORS`); po
  anulowaniu, timeoucie i niedostępności zamyka się dopiero po sprzątaniu.

## Pułapki

- Brak retry w transporcie (Z6). Ponowne „Play” (do 3) i pętla dołączania do CDP to czynności jednej próby.
- Błąd Playwright przy starcie sterownika, dołączaniu i przygotowaniu kontekstu (`ChromeSession._attach`) staje się
  `unavailable_error`, więc `sign_in` kończy się `FAILED`, a panel nie zostaje w stanie „zajęty”.
- Każde wywołanie strony w próbie (także `set_page_speed`, `press_play`, `check_page_speed`, `player_state`) idzie
  przez `_unless_cancelled`, więc anulowanie nie czeka na limit Playwright; `evaluate` nie ma własnego limitu.
- Kartę i nagrywanie próby ogranicza `request.deadline_s` (`_within_deadline`): po jego upływie próba kończy się
  `TtsTimeoutError` (przejściowy), a sprzątanie konta i zamknięcie Chrome biegną w `finally` jak po każdym błędzie.
  Scheduler ma wyłączony `asyncio.timeout` dla tego silnika, więc ten termin jest jedynym górnym limitem próby;
  poza nim są start Chrome (`_open_browser`, ograniczony próbami `CONNECT_ATTEMPTS`) i końcowe sprzątanie (każdy
  krok `CLEANUP_STEP_TIMEOUT_S`).
- Token, `read_id`, adres WebSocketu i tekst dokumentu nie trafiają do logów ani wyjątków. Token i adres
  WebSocketu nie trafiają też do plików. Prywatny `session.json` (katalog z `restrict_directory`, gitignored) ma tylko
  `signed_in`, `checked_at`, `restore` (głos i tempo konta) i `documents` (czasy, `read_id` wyłącznie do sprzątania
  oraz skróty SHA-256 prefiksów tytułu). Skróty nie są jawnym tekstem, ale słownikiem da się je odwrócić słowo po
  słowie. Adres strumienia jest sprawdzany w pamięci (F8).
- Część pusta po neutralizacji, równa `LINE_SEPARATOR` albo z `<break` to `TtsInputError` z `validate_part`;
  `TtsService` woła ją dla każdej kwestii przed grupowaniem, a `synthesize_document` dla każdej części przed
  przeglądarką.
- Błąd zapisu nagrania (`OSError`) zatrzymuje `StreamRecorder`; `_record` w następnym takcie rzuca
  `TtsClipValidationError` z `error_class` i `errno`, bez ścieżki.
- Pierwsza ramka wysyłana z `listening_speed` ≠ 1 oznacza model v2 → błąd przejściowy.
- Wylogowanego gościa biblioteka przekierowuje na `/reader/sign-up` (przyciski „Sign up with Google/Apple/email”,
  „Sign in” nie jako przycisk; K2); `open_library` rozpoznaje to po adresie i przyciskach „Sign up”. Status 402 jako brak
  kredytów jest założeniem do potwierdzenia w K2.
- `GET reads` (zmierzone 2026-10-31) zwraca `{"reads": [...], "has_more", "next_cursor", "last_sort_id"}`; nowy
  upload był na pierwszej stronie. Kod czyta tylko ją, bez paginacji. Założenie: kolejność od najnowszych, a upload
  bez `read_id` szuka się zwykle w tym samym przebiegu, minuty po wgraniu (sprzątanie po anulowaniu, następna próba,
  `close()`). Po dłuższej przerwie dokument może być poza pierwszą stroną; wtedy krok rozlicza się z ostrzeżeniem,
  a nie po cichu. Brak listy `reads` zostawia krok `delete_orphan` zaległym
  (widocznym w panelu), nigdy nie rozlicza go po cichu. Rozpoznanie sprawdza test sieciowy
  `test_reads_listing_live_account_finds_and_deletes_document_without_known_id`.
- `char_count` z odpowiedzi uploadu jest obowiązkowy; bez niego próba kończy się błędem przejściowym.
