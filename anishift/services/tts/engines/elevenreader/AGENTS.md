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
- `ProcessLock` na `chrome.lock` wyklucza drugą przeglądarkę na profilu: zajęty → `ChromeBusyError`
  (przejściowy); w `sign_in` → `SignInOutcome.BUSY`. `restrict_directory` przy każdym starcie.
- `ReaderPage` jest jedynym miejscem z selektorami i wywołaniami Playwright. Każdy błąd Playwright idzie przez
  `map_playwright_error` z `from None`, bo komunikat Playwright potrafi zawierać adres z `read_id`.

## Konto i sprzątanie

- Głos i tempo 1x ustawia `user_config` konta tokenem strony (`prepare_account`), przed otwarciem dokumentu:
  serwer wybiera model przy starcie strumienia. Wpis przywrócenia powstaje przed zapisem i nie jest
  nadpisywany, dopóki poprzedni nie wykona się, inaczej „poprzednim” głosem zostałby nasz.
- `AccountCleanup` (przywrócenie ustawień, `DELETE reads/{id}`, sierota po tytule) biegnie przez `clean_account` w
  `finally` każdej próby pod `_finish_shielded`, także po `asyncio.CancelledError`; każdy krok ma własny limit i
  `_cleanup_step` łapie każdy wyjątek, a karta i Chrome zamykają się w `finally`. Nieudany krok zostaje i wykonuje
  się po `require_signed_in` następnej próby (przed uploadem), w `close()`, jeśli przeglądarka żyje, oraz w
  `sign_in` panelu. Trwała porażka: `logger.warning(CLEANUP_WARNING, steps=…)`, wiersz w SESJA i ostrzeżenie doctora.
- `upload` rejestruje możliwy dokument (`orphan_visible_at`) i zapisuje go przed „Upload”, a `read_id` z odpowiedzi
  przed walidacją `char_count`/tokenu. Dokument bez znanego id (anulowanie w trakcie uploadu, odpowiedź bez id,
  poprzedni proces) szuka się w `GET reads` po tytule `anishift`/`anishift.txt`; pusty wynik rozlicza krok dopiero
  po `ACTION_TIMEOUT_S` od kliknięcia.
- Zaległe sprzątanie jest trwałe w `session.json` (`restore`, `delete_document`, bez `read_id`): `prepare_account` i
  `upload` zapisują je przed zmianą konta, silnik po każdym sprzątaniu, `load_cleanup` wczytuje je przy starcie.
- Przeglądarka zostaje otwarta po sukcesie i po błędach, które jej nie dotyczą (`_KEEP_BROWSER_ERRORS`); po
  anulowaniu, timeoucie i niedostępności zamyka się dopiero po sprzątaniu.

## Pułapki

- Brak retry w transporcie (Z6). Ponowne „Play” (do 3) i pętla dołączania do CDP to czynności jednej próby.
- Każde długie oczekiwanie idzie przez `_unless_cancelled`, więc anulowanie nie czeka na limit Playwright.
- Token, `read_id`, adres WebSocketu i tekst dokumentu nie trafiają do logów, wyjątków ani plików;
  `session.json` ma tylko `signed_in`, `checked_at`, `restore` (głos i tempo konta) i `delete_document`. Adres
  strumienia jest sprawdzany w pamięci (F8).
- Część pusta po neutralizacji, równa `LINE_SEPARATOR` albo z `<break` to `TtsInputError` z `validate_part`;
  `TtsService` woła ją dla każdej kwestii przed grupowaniem, a `synthesize_document` dla każdej części przed
  przeglądarką.
- Błąd zapisu nagrania (`OSError`) zatrzymuje `StreamRecorder`; `_record` w następnym takcie rzuca
  `TtsClipValidationError` z `error_class` i `errno`, bez ścieżki.
- Pierwsza ramka wysyłana z `listening_speed` ≠ 1 oznacza model v2 → błąd przejściowy.
- Rozpoznanie wylogowania w `ReaderPage.open_library` (przyciski „Sign in/Log in/Continue with Google” albo
  adres strony logowania), status 402 jako brak kredytów oraz lista `GET reads` w kształcie
  `{"reads": [{"read_id", "title"}]}` są założeniami do potwierdzenia w K2. Inny kształt listy zostawia krok
  `delete_orphan` zaległym (widocznym w panelu), nigdy nie rozlicza go po cichu.
- `char_count` z odpowiedzi uploadu jest obowiązkowy; bez niego próba kończy się błędem przejściowym.
