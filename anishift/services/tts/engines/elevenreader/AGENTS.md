# Silnik ElevenReader

Silnik dokumentowy: wgrywa dokument do ElevenReadera, nagrywa strumień w Chrome, sprawdza po słowach, czy serwer
przeczytał każdą część, dogrywa części z brakującymi słowami i zwraca jedno nagranie MP3 z czasami części. Wszystko,
co zależy od programu (błędy, teksty dla użytkownika, platforma, dekodowanie MP3, typy dokumentu, nazwa programu,
powierzchnia silnika wobec reszty programu), jest wyłącznie w `host.py`. Pozostałe pliki tego katalogu nie importują
niczego spoza katalogu poza biblioteką standardową i Playwright; zmiana w nich jest zmianą silnika, nie programu.

## Moduły

- `host.py`: jedyne miejsce zależne od programu. Daje błędy i `ErrorContext`, teksty podpowiedzi (`*_HINT`,
  `CLEANUP_WARNING`), `NAME` (nazwa pliku dokumentu, katalogów tymczasowych i wątku), anulowanie, `ProcessLock`,
  `restrict_directory`, `find_installed`, zapis `session.json`, cięcie ramek MP3, `mono_pcm` (MP3 → mono PCM 16 kHz),
  typy dokumentu (`DocumentPart`, `DocumentSynthesisRequest`, `PartTiming`, `DocumentResult` i `document_result`),
  `engine_config` (z czego powstaje `ElevenReaderConfig`), `check_request`, `keeps_tags` oraz `EngineSurface`, klasę
  bazową silnika z tym, czego program wymaga od silnika poza wspólnymi metodami.
- `config.py`, `constants.py`, `types.py`, `service.py` (silnik, `document_text`) i `api_backend.py` (karta
  Playwright: `ReaderPage`, konto, sesja, logowanie, wylogowanie, mapowanie błędów dostawcy).
- `redo.py`: porównanie słów (`read_parts`), czasy części (`timings`, `part_spans`), bloki dogrywania
  (`redo_blocks`) i sklejanie (`splice`). `pauses.py`: poziomy ramek 10 ms i najlepsza pauza między dwoma odcinkami
  mowy (te same stałe co reguła cięcia klipów).
- `browser.py` (proces Chrome i CDP: `ChromeSession(root, headless=…)`, `open_window`), `hub.py` (`ReaderHub`: jedna
  przeglądarka profilu w procesie, karta na nagranie, wspólne sprzątanie konta), `recorder.py` (czyste ramki WebSocket
  → MP3 i czasy znaków, testowane bez przeglądarki).

## Wykrywanie i dogrywanie

- Tekst ze strumienia to metadane do podświetlania i nie jest deterministyczny; celem jest dźwięk. `read_parts`
  porównuje naraz wszystkie słowa dokumentu (`[^\W_]+`, małe litery; interpunkcja, odstępy i wielkość liter się nie
  liczą) ze słowami strumienia (bez znaczników `<break>`) przez `difflib.SequenceMatcher` bez `autojunk`. Połączenie
  lub rozdzielenie linii przez serwer nie jest różnicą. Słowo brakujące albo inne oznacza część jako brakującą
  (`missing`); słowo dodane przez serwer trafia tylko do logu. Każda różnica idzie do logu (`ElevenReader streamed other words than the parts`) z numerem części i słowami obu wersji; to jedyny wyjątek od zakazu tekstu w logach.
- Zakres części w tekście strumienia biegnie od jej pierwszego do ostatniego słowa wraz z interpunkcją do najbliższej
  pauzy albo spacji; część bez słów dostaje akapit bez słów między sąsiadami. Część poza zakresem, z odwróconym czasem
  albo dotykająca cichej porcji dostaje pusty `PartTiming`. Inna liczba znaków niż `char_count` tylko ostrzega.
- `ElevenReaderConfig.redo` (`Redo`, bez wartości domyślnej): `LINE` nagrywa złą część samą, `PARAGRAPH` razem z
  częścią przed i po niej jako jeden dokument, który zastępuje wszystkie trzy. Bloki stykające się lub nachodzące
  łączą się w jeden. Każdy blok nagrywa się raz; dogranie z brakującym słowem albo błędem nie jest wklejane i nie ma
  kolejnych ponowień, a jego części są w wyniku jako `incomplete`. Nigdy nie nagrywa się całego dokumentu od nowa po
  odebraniu dźwięku.
- Sklejanie (`splice`) tnie w ciszy wykrytej w dźwięku (`pauses.best_pause` między częścią przed i po szwie, środek
  pauzy), a nie według czasów serwera. Dogranie zaczyna się tyle przed pierwszą głośną ramką (`NOISE_DBFS`), ile pauzy
  ucięto po stronie nagrania głównego, i kończy tyle po ostatniej; blok na początku albo końcu dokumentu bierze
  dogranie od jego początku albo do końca. Brak pauzy przy szwie: blok nie jest wklejany. Tekst i czasy znaków
  wynikowego nagrania powstają z odcinków obu nagrań przesuniętych na nową oś.

## Pliki nagrań

- Każda próba ma własny plik `<stem>.take<n><suffix>` obok `request.recording` (`open("xb")`), także pobranie
  (`download_document`); silnik niczego nie kasuje. Wynik trafia do `request.recording`, który nie może zawierać
  danych (pusty plik zastępczy jest dozwolony), więc żadne nagranie nie jest nadpisywane.
- Obok każdej próby i wyniku zawsze leży `<stem>.stream.txt` z tekstem, który przysłał serwer.
- Strumień urwany po dźwięku (zastój `STALL_S`, odmowa App Check, prośba strony o inną prędkość) kończy próbę z tym,
  co przyszło; brakujące części idą do dogrania. Bez dźwięku te same zdarzenia są błędem próby. Rejestrator przestaje
  zapisywać, gdy strona poprosi o inną prędkość po dźwięku (`off_speed_after_speech`).

## Gospodarz (`hub.py`)

- `ReaderHub.acquire(profile_root, …)` w konstruktorze silnika, `release()` w `close()`; rejestr procesu pod
  `threading.Lock`, licznik referencji = żywe silniki. Gospodarz ma własny wątek `<NAME>-elevenreader` (daemon) i
  pętlę asyncio; na niej żyją `ChromeSession`, karty, `AccountCleanup` i każdy zapis `session.json`. Silniki z różnych
  pętli zlecają całą próbę przez `record` i nie dotykają Playwright.
- Nowy gospodarz profilu, którego poprzedni jeszcze się zamyka, czeka w swoim wątku na koniec poprzedniego i dopiero
  wtedy wczytuje `load_cleanup`; ostatni `release` sprząta konto w nowej karcie, zapisuje, ostrzega
  (`CLEANUP_WARNING`), zamyka Chrome i kończy wątek.
- Próba: bramka głosu (poza terminem, pod anulowaniem; inny głos czeka na koniec aktywnych, kolejka po bilecie bez
  głodzenia) → termin `deadline_s` → blokada startu: Chrome (start albo restart podejrzanego, gdy nikt inny nie
  nagrywa), karta, `require_signed_in`, zaległe dokumenty, upload, `prepare_account`, Play; blokadę zwalnia
  `attempt.started()` po pierwszym adresie strumienia albo po `START_TIMEOUT_S` → nagrywanie równolegle → `_leave`.
  Każde dogranie to osobna próba.
- Anulowanie wywołującego i anulowanie zadania silnika przechodzą przez osobne anulowanie próby (`_until_done`);
  silnik wraca dopiero po końcu `_leave` tej próby. Postęp dokumentu wraca na pętlę silnika (`_reported_here`).

## Granice

- Na poziomie modułu Playwright importuje tylko `browser.py`. `api_backend.py` ładuje go leniwie, a `hub.py` w
  `headless_session`.
- `find_chrome`, `profile_dir`, `session_file` i `lock_file` leżą w `config.py`, żeby diagnostyka nie ładowała
  Playwright.
- `ChromeSession` startuje Chrome z `--user-data-dir=<root>/chrome-profile` (Chrome 136+ ignoruje CDP dla domyślnego
  profilu) na wolnym porcie i dołącza `connect_over_cdp`; skrypt prędkości strony tylko przy `headless=True`.
  `close` najpierw prosi Chrome o wyjście przez CDP (sama prośba ma limit 10 s) i czeka do 10 s; `terminate` i `kill`
  są zapasem. Chrome zapisuje ciasteczka z opóźnieniem do ok. 30 s, więc twarde zabicie zaraz po zalogowaniu gubi
  sesję.
- `claim_profile` to jedyna droga zajęcia profilu (`ChromeSession.start`, `sign_in`): `ProcessLock` na `chrome.lock`
  i `chrome-profile/lockfile`, który Chrome na Windows trzyma otwarty; nieusuwalny `lockfile` = zajęty. Zajęty →
  `busy_error()` z `host.py`; w `sign_in` i `await_sign_in` → `SignInOutcome.BUSY`, w `sign_out` →
  `SignOutOutcome.BUSY`.
- `sign_in` otwiera przez `open_window` zwykłe, odłączone Chrome na bibliotece, bez CDP i bez czekania.
  `await_sign_in` otwiera sterowane okno, czeka do `SIGN_IN_TIMEOUT_S` na zalogowanie i sprząta konto. `sign_out`
  usuwa tylko ciasteczka `SITE_COOKIE_DOMAIN` i dane originu `SITE_ORIGIN` (CDP `Storage.clearDataForOrigin` przez
  sesję świeżej karty) i zapisuje `signed_in: false`.
- `ReaderPage` jest jedynym miejscem z selektorami i wywołaniami Playwright. Każdy błąd Playwright idzie przez
  `map_playwright_error` z `from None`, bo komunikat Playwright potrafi zawierać adres z `read_id`.

## Konto i sprzątanie

- `resolve_voice` przyjmuje alias, id głosu z `VOICES` albo 20-znakowe id dowolnego głosu biblioteki ElevenLabs.
- Głos i tempo 1x ustawia `user_config` konta tokenem strony (`prepare_account`) przed otwarciem dokumentu; głos
  `None` (pobieranie z głosem konta) zostawia głos. Wpis przywrócenia powstaje przed zapisem i nie jest nadpisywany,
  dopóki poprzedni nie wykona się.
- Każda próba ma własny `AccountCleanup` wgrań; gospodarz ma wspólny (`restore` i dokumenty zakończonych prób).
  `session.json` zapisuje sumę obu. Próba usuwa w `_leave` swoje dokumenty, a ostatnia otwarta karta przywraca
  ustawienia. Każdy krok ma własny limit i `_cleanup_step` łapie każdy wyjątek. Trwała porażka: ostrzeżenie
  `CLEANUP_WARNING` z krokami.
- `upload` zapisuje `DocumentTrace` (czasy zegarowe, skróty SHA-256 możliwych tytułów) przed „Upload”, a `read_id`
  przed walidacją `char_count`/tokenu. Upload bez `read_id` szuka się w pierwszej stronie `GET reads`
  (`from_user_import`, `text/plain`, okno czasu ±300 s, skrót tytułu); jeden kandydat → `DELETE`, kilku → nic.
- Błąd próby zamyka tylko jej kartę. Anulowanie, timeout i niedostępność oznaczają przeglądarkę jako podejrzaną;
  restart następuje przy otwieraniu karty, gdy żadne inne nagranie nie trwa.

## Pułapki

- Konto trzyma na urządzeniu najwyżej 2 strumienie naraz: przy 3 nowy strumień zamyka starszy. Dlatego
  `MAX_PARALLEL_DOCUMENTS` = 2.
- Brak retry w transporcie. Ponowne otwarcie dokumentu z Play (do `PLAY_ATTEMPTS`, gdy przez `START_TIMEOUT_S` nie
  przyszedł dźwięk) i pętla dołączania do CDP to czynności jednej próby; ponowienia próby robi wywołujący.
- Firebase App Check potrafi odrzucić profil (`APP_CHECK_REFUSAL` w konsoli); `raise_if_refused` kończy próbę trwałym
  `TtsAuthError` przed dźwiękiem, a po dźwięku kończy ją z tym, co przyszło.
- `request.deadline_s` (`within_deadline`) jest jedynym górnym limitem próby; po nim próba kończy się
  `TtsTimeoutError` (przejściowy), także po dźwięku.
- Token, `read_id` i adres WebSocketu nie trafiają do logów, wyjątków ani plików.
- Część pusta po neutralizacji, równa `LINE_SEPARATOR` albo z `<break` to `TtsInputError` z `validate_part`.
- `request.tags` (gdy `keeps_tags`) przepuszcza nawiasy kwadratowe do serwera jako znaczniki v4.
- Błąd zapisu nagrania (`OSError`) zatrzymuje `StreamRecorder`; `_record` rzuca `TtsClipValidationError`.
- Prośba strony o prędkość ≠ 1 przed dźwiękiem oznacza model v2 → błąd przejściowy.
- `download_document` odmawia dokumentu, który strona wznawia od środka (`start_position` > 0 → `TtsInputError`).
- Serwer potrafi oddać porcję z tekstem prawie bez dźwięku (`SILENT_CHUNK_MIN_LETTERS`,
  `SILENT_CHUNK_MS_PER_LETTER`); części na niej dostają pusty `PartTiming`, a ponowny odczyt robi wywołujący.
