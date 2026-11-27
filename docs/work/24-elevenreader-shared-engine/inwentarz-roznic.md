# Inwentarz różnic dwóch kopii silnika ElevenReader

Stan wyjściowy: kopia E (`ElevenDownloaderPro`, `src/edp/engine/`, `main` b922bc9) i kopia A (AniShift,
`anishift/services/tts/engines/elevenreader/`, `main` 9fd468a). Te same moduły, ok. 1000 z 2800 linii różnych.
Wynik: jeden silnik o identycznych plikach w obu repozytoriach; wszystko, co zależy od programu, jest w `host.py`
(jeden plik na repozytorium). `diff -r` obu katalogów pokazuje tylko `host.py`.

## Zasada wyboru

- Różnica wynikająca z programu (teksty dla użytkownika, błędy, platforma, typy dokumentu, nazwa programu) → `host.py`.
- Różnica funkcji, której druga kopia nie ma, a jest potrzebna jednemu programowi → zostaje w silniku (suma funkcji).
- Różnica tej samej funkcji → wersja lepsza albo połączenie obu.

## Różnice i decyzje

| Plik | Różnica | E | A | Decyzja i powód |
| --- | --- | --- | --- | --- |
| wszystkie | importy błędów, loggera, anulowania, platformy | `edp.*` | `anishift.*` | `host.py`; pozostałe pliki importują tylko `.host` |
| `__init__.py` | eksporty | typy dokumentu, `sign_in` | `sign_out`, `SignOutOutcome`, `PROVIDER_MODEL_ID` | suma; typy dokumentu z `host.py`, nowe `Redo`, `await_sign_in` |
| `config.py` | `find_chrome` | własna pętla po `CHROME_LOCATIONS` | `platform.installed.find_installed` | `find_installed` z `host.py` (ta sama pętla w E przeniesiona do hosta) |
| `config.py` | `resolve_voice` | przyjmuje dowolne 20-znakowe id biblioteki głosów | tylko dwa głosy | wersja E (nadzbiór, potrzebna `edp --voice <id>`); podpowiedź z `host.py` |
| `config.py` | `lock_file` | brak (ścieżka w `browser.py`) | jest | wersja A (jedno źródło ścieżki) |
| `config.py` | `from_tts_config` | brak | jest | do `host.engine_config` A, bo zależy od `TtsConfig` |
| `config.py` | tryb dogrywania | brak | brak | nowe pole `redo: Redo` bez domyślnej; E `PARAGRAPH`, A `LINE` |
| `constants.py` | `DOCUMENT_NAME` | `edp.txt` | `anishift.txt` | z `host.NAME` (`<NAME>.txt`) |
| `constants.py` | zmienne strony JS | `__edp*` | `__anishift*` | neutralne `__reader*` w obu (nazwy wewnątrz strony) |
| `constants.py` | `SITE_ORIGIN`, `SITE_COOKIE_DOMAIN`, `PROVIDER_MODEL_ID` | brak | są | wersja A (potrzebne wylogowaniu i A) |
| `constants.py` | `SIGN_IN_TIMEOUT_S` | jest | brak | zostaje (sterowane logowanie E) |
| `types.py` | `DocumentPart`, `DocumentSynthesisRequest`, `PartTiming`, `DocumentResult` | w silniku | we wspólnych typach TTS | `host.py` (E definiuje, A importuje swoje) |
| `types.py` | `SignInOutcome` | `SIGNED_IN`, `SIGNED_OUT`, … | `OPENED`, … | suma wartości (dwa sposoby logowania) |
| `types.py` | `SignOutOutcome` | brak | jest | wersja A |
| `recorder.py` | `start_position` | jest | brak | wersja E (pobieranie istniejącego dokumentu) |
| `recorder.py` | prędkość po dźwięku | brak | brak | nowe `off_speed_after_speech`: po dźwięku rejestrator przestaje zapisywać |
| `hub.py` | `CLEANUP_WARNING`, nazwa wątku | teksty E | teksty A | `host.CLEANUP_WARNING`, wątek `<NAME>-elevenreader` |
| `hub.py` | typ anulowania | `Cancellation` | `CancellationToken` + `TtsCancellation` | `host.CancellationToken` (parametry) i `host.Cancellation` (tworzone) |
| `browser.py` | `ChromeSession(root, headless=…)` | okno albo headless | zawsze headless | wersja E (E nagrywa w widocznym oknie); A podaje `headless=True` |
| `browser.py` | `Browser.close` z limitem 10 s | jest | brak | wersja E (Chrome bez odpowiedzi nie wiesza zamknięcia) |
| `browser.py` | `claim_profile` (+ `lockfile` Chrome) | tylko `ProcessLock` | jest | wersja A (wykrywa też ręcznie otwarte okno na profilu) |
| `browser.py` | `open_window`, `forget_site`, `_prepared_profile` | brak | są | wersja A; `independent_child_flags` z `host.py` (E: 0, bez Job Object) |
| `browser.py` | `ChromeBusyError` | trwały (`FatalError`) | przejściowy z `retry_after_s` | w `host.py`: zachowanie każdego programu bez zmian (`busy_error()`) |
| `api_backend.py` | teksty podpowiedzi (`SIGN_IN_HINT`, App Check, głos, konto, kredyty) | angielskie, `edp login` | polskie, panel | `host.py` |
| `api_backend.py` | `sign_in` | sterowane okno, czeka na zalogowanie, sprząta | zwykłe okno bez sterowania | oba: A `sign_in`, E `await_sign_in` |
| `api_backend.py` | `sign_out` | brak | jest | wersja A |
| `api_backend.py` | `prepare_account` z głosem `None` | jest | tylko głos |  wersja E (pobieranie z głosem konta) |
| `api_backend.py` | `is_closed`, `library_ready` publiczne | tak | `_library_ready` | wersja E (potrzebne sterowanemu logowaniu) |
| `api_backend.py` | zapis `session.json` | własny `_atomic_json_snapshot` | `tts.artifacts.atomic_json_snapshot` | `host.atomic_json_snapshot` (E: dotychczasowy kod w hoście) |
| `service.py` | powierzchnia `TtsEngine` (capabilities, dostępność, profil, głosy, `synthesize`) | brak | jest | `host.EngineSurface` (A), klasa bazowa silnika; E pusta |
| `service.py` | walidacja modelu i opcji | brak | jest | `host.check_request` |
| `service.py` | `tags` | jest | brak | `host.keeps_tags` (A zawsze `False`) |
| `service.py` | `download_document` | jest | brak | zostaje (E `edp download`) |
| `service.py` | sprawdzanie tekstu | znak w znak; różnica = `TtsClipValidationError` (przejściowy, całość od nowa) | po słowach na linię; inne słowo = `TtsUnsupportedError` (całość przepada), inna liczba linii = całość od nowa | nowe: porównanie słów całego dokumentu naraz i dogrywanie (`redo.py`) |
| `service.py` | `chars < char_count` | błąd (całość od nowa) | błąd (całość od nowa) | tylko ostrzeżenie; brakujące słowa idą do dogrania |
| `service.py` | zastój, odmowa App Check, v2 po dźwięku | błąd próby | błąd próby | po dźwięku koniec próby z tym, co przyszło, dogranie reszty |
| `service.py` | wynik | `DocumentResult` z `chunks` | `EngineDocumentResult` | `host.document_result`; nowe pola `ranges` (E) i `incomplete` (oba) |
| `service.py` | `part_spans`, `part_bounds`, `stream_timeline` | w `service.py` | `part_spans` w `service.py` | `redo.py` (`timings`, `read_parts`, `stream_timeline`); `part_bounds` i `part_spans` usunięte |
| docstringi | wielolinijkowe (Args/Returns) | kilka | brak | jednolinijkowe w całym silniku |

## Rzeczy świadomie różne (tylko `host.py`)

- Teksty dla użytkownika: E po angielsku z komendami `edp`, A po polsku z drogą w panelu i `FALLBACK_HINT`.
- `ChromeBusyError`: E trwały (drugi `edp` na tym samym katalogu domowym), A przejściowy (panel, okno logowania).
- Dekodowanie MP3 do PCM: E przez `edp.speech.mp3_pcm`, A przez FFmpeg z `platform.binaries`, bo domena TTS AniShift
  nie może importować `services.audio` (test `test_tts_domain_does_not_import_pipeline_or_other_domains`).
- Reguła pauzy (poziomy ramek, czasy ramek na osi serwera, `best_pause`, `silent_cut`) leży w przenośnym
  `anishift/utils/pauses.py`, kopiowanym 1:1 do `edp/utils/`; korzystają z niej klipy AniShift, `edp/speech.py` i silnik
  (przez `host.py`). `services/audio/segmentation.py` i `frame_levels` z `levels.py` zniknęły.
- Konfiguracja: E buduje `ElevenReaderConfig` sam (`Redo.PARAGRAPH`), A z `TtsConfig` (`Redo.LINE`).

## Po recenzji

- Gdy wgrany dokument dał już dźwięk, każdy błąd próby poza anulowaniem (Playwright, zapis, App Check, v2 po dźwięku,
  zastój, termin próby takt przed końcem) kończy ją z tym, co przyszło; błąd dekodowania lub brak pauzy przy
  sklejaniu zostawia nagranie bez wklejenia, a części trafiają do `incomplete`. Silnik nie rzuca wtedy błędu, więc
  ani `_retrying` edp, ani scheduler AniShift nie nagrywają całości od nowa.
- AniShift: linia `incomplete` jest w `spans` przy cięciu (oddziela ją od sąsiadów), ale nie dostaje klipu.
- Pliki prób mają nazwę `<nazwa>.take<n>.mp3` w obu programach.

## Recenzja AniShift i zmiany do przeniesienia

Zasada nadrzędna po recenzji: po odebraniu dźwięku dokument nigdy nie jest nagrywany od nowa; pierwsze nagranie
zostaje wynikiem.

1. Jeden zły klip kończył cały odcinek (`TtsRecordingSplitError` dla wszystkich linii). Teraz zły klip to błąd tylko
   jego linii (`TTS_CLIP_INVALID`), reszta linii zostaje z klipami. Nieudane cięcie FFmpeg jest ponawiane raz (samo
   cięcie, nie nagranie); anulowanie dekodera to anulowanie. `8091a340`, `ec7a336e`.
2. Trwały błąd w dogrywaniu (logowanie, App Check, kredyty, głos) nie przerywał pętli, a linie dostawały „rewrite the
   line”. Teraz `FatalError` kończy dogrywanie, nagranie zostaje, a `incomplete_cause` niesie kod i podpowiedź błędu
   na niepełne linie. `a34e228e`.
3. `_joined` łapał `ValueError`/`IndexError`/`TtsError` wokół całego `splice` jako „redo is not joined”. Teraz
   `OSError` (odczyt, dekodowanie) to „not joined”, a `ValueError`/`IndexError` to błąd w kodzie z tracebackiem w
   logu; w obu przypadkach wynikiem jest pierwsze nagranie (wyjątek z silnika scheduler AniShift ponawiałby jako
   przejściowy, czyli nagrywał od nowa). `ab4658f9`, `b7982e37`.
4. Pliki `*.take<n>.mp3` i `*.stream.txt` prób zostawały na dysku, a każde ponowienie nieudanego przebiegu dokładało
   nagranie wielkości odcinka. Teraz silnik usuwa dogranie niewklejane od razu, a próbę główną i wklejone dogrania po
   zapisie wyniku; zostaje wynik i jego `stream.txt`. Błąd przed wynikiem zostawia próby wywołującemu; `TtsService`
   AniShift usuwa po każdej próbie dokumentu wszystkie pliki pod nazwą nagrania. `a5f65d07`.
5. Martwy kod: `redo.part_spans` (tylko testy) i lista `left_out` z `splice` usunięte; testy czasów części używają
   pomocnika `part_timings` w `tests/conftest.py` (`read_parts` + `timings`). `e6e3c2c3`.
6. Test „przekroczenie czasu przed dźwiękiem → przeglądarka podejrzana” wrócił w nowej postaci (brak dźwięku po Play,
   drugie nagranie trwa, przeglądarka restartuje dopiero po nim). `8c99cf08`.

Poza listą: `host.mono_pcm` uruchamia FFmpeg z `CREATE_NO_WINDOW`, jak reszta wywołań w AniShift (`207c3a7b`, tylko
`host.py` AniShift).

### Do przeniesienia do ElevenDownloaderPro (`src/edp/engine/`)

Pliki wspólne, skopiować 1:1 z AniShift (`anishift/services/tts/engines/elevenreader/`):

- `service.py`: `FatalError` z `.host`; `_redo` zwraca `(redone, cause)` i kończy się na `FatalError`;
  `document_result(..., incomplete_cause=...)` w `synthesize_document` i `download_document`; `_take(recording=...)`;
  `_discard` i `_stream_file`; usuwanie prób po zapisie wyniku i dograń niewklejanych od razu; `_joined` łapie
  `OSError` i osobno `ValueError`/`IndexError` (`logger.exception`), `splice` zwraca same chunki.
- `redo.py`: bez `part_spans` (także w `__all__`), `splice` zwraca `tuple[AlignmentChunk, ...]`, bez `left_out`.

`host.py` ElevenDownloaderPro (własny, nie kopiować z AniShift):

- eksport `FatalError` z `edp.errors`;
- `DocumentResult` z polem `incomplete_cause: ErrorContext | None` i `document_result(..., incomplete_cause)`.

Reszta ElevenDownloaderPro:

- `reading.py`: `_TAKES` i warunek „read more than once” (`len(list(work.glob(_TAKES))) > ...`) nie mają już sensu,
  bo po wyniku prób nie ma; do usunięcia razem z testem `tests/test_reading.py` (ok. linii 813, oczekuje
  `download.take1.mp3`); `edp record`/`download` może pokazać `incomplete_cause` przy częściach `incomplete`.
- `tests/engine/test_engine_redo.py`: te same zmiany co w AniShift (`tests/services/tts/test_engine_redo.py`):
  test bez plików prób po wyniku, test usunięcia niewklejanego dogrania, test odmowy App Check w dogrywaniu
  (`incomplete_cause`), test błędu w kodzie przy sklejaniu (pierwsze nagranie zostaje), porównania z
  `doc.take1.mp3` zamienione na `fills(...)`.
- `AGENTS.md` silnika: sekcje „Wykrywanie i dogrywanie” i „Pliki nagrań” jak w AniShift.

## Sprawy otwarte

- AniShift: wynik dokumentu niezgodny z kontraktem (`_unowned_clip_error`, `_document_timing_error`, oba
  przejściowe) dalej każe schedulerowi nagrać dokument od nowa; to błąd silnika, nie cięcia, więc zostało bez zmian.
