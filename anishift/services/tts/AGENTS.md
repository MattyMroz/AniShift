# services/tts

Samodzielna domena syntezy mowy. Publiczna granica przyjmuje neutralny tekst i opaque
identyfikatory; nie zna formatu ani cyklu życia plików źródłowych.

## Granica

- Wejście publiczne: `SpeechBatch` z `SpeechRequest`.
- Wyjście publiczne: `SpeechBatchResult` z technicznymi metadanymi klipów.
- TTS posiada engine, voice/model settings, provider request scheduling, retry, circuit,
  cancellation oraz resume surowych klipów.
- Pipeline posiada kolejkę plików, stan napisów, timing, mapowanie wyników i recovery
  całego przebiegu.
- Audio posiada timeline, normalizację, narrator, miksowanie, kanały i codec produktu.
- Composition wybiera jawny profil engine/model/voice/concurrency/queue; wspólny config
  nie zgaduje defaultów innego silnika.

## Zakazane zależności

- `pysubs2`
- `anishift.services.audio`
- `anishift.services.subtitles`
- `anishift.services.translation`

TTS nie parsuje ASS/SRT, nie przyjmuje timestampów, MKV ani source audio i nie buduje
narratora ani finalnego sidecara.

## Silniki

- Registry (`engines/__init__.py`) jest jedynym źródłem prawdy o ID silników.
- Import domeny i registry nie może importować SDK ani implementacji providerów.
- Caller jawnie wybiera silnik; nie ma cichego fallbacku.
- `is_available` jest wyłącznie tanim, cache'owanym skrótem. Szczegółowy wynik
  `availability()` jest źródłem prawdy dla doctor/settings.
- Transport providera wykonuje pojedynczą próbę. Wspólna warstwa TTS jest jedynym
  właścicielem retry, limitów współbieżności i circuit state.

## Kontrakty i resume

- `validation.py` wymaga już oczyszczonego tekstu i świadomie odrzuca składnię
  napisów. Nie „naprawiaj” ASS/SRT wewnątrz TTS.
- `chunking.py` dzieli wyłącznie według limitów capability silnika; wspólne
  granice i grafemy bierze z `anishift/text/`, ale wymowność i backtracking
  pozostają własnością TTS.
- Provider zapisuje do prywatnej ścieżki klipu przygotowanej przez TTS. Dopiero
  wspólna warstwa waliduje wynik i commit manifestu.
- Fingerprint obejmuje profil silnika oraz tekst requestu. Zmiana parametru
  wpływającego na dźwięk musi unieważniać resume.
- Callback postępu jest observerem. Jego błąd nie może przejąć syntezy.
- `TtsScheduler.submit(call, …)` wykonuje dowolną próbę (`call(attempt)`); wynik leży w
  `ScheduledSynthesis.result`. Ścieżka per kwestia i ścieżka dokumentu dzielą ten sam
  retry, circuit i timeout. Ostrzeżenie o ponowieniu i błąd końcowy logują kod, komunikat
  i wyłącznie liczbowe wartości `details` (`_numeric_details`), bez tekstów i ścieżek.
- Ponowienie powstaje tylko dla nieanulowanego tokenu i otwartego schedulera; warunek jest sprawdzany też pod
  blokadą przy wstawianiu do kolejki opóźnionych, więc anulowanie w trakcie planowania ponowienia kończy próbę od
  razu (`_retry_allowed`).

## Ścieżka dokumentu

- Silnik z `capabilities.reads_documents` czyta wszystkie brakujące kwestie batcha jednym
  dokumentem przez `DocumentTtsEngine.synthesize_document`, bez limitu długości;
  wymaga wstrzykniętego `ClipSplitter`, inaczej każda kwestia mowy dostaje
  `TtsUnsupportedError`.
- Kwestia, która nie mieści się w jednej części albo której nie przyjmuje
  `DocumentTtsEngine.validate_part`, dostaje `TtsInputError` przed odczytem; reszta
  batcha idzie dalej. Resume, tożsamość i commit są per kwestia jak w ścieżce zwykłej.
- `accept_result` sprawdza własność nagrania i kolejność `PartTiming`, tnie nagranie
  (`open_end = not ends_sentence(text)`) i waliduje każdy klip; błąd splittera albo
  niezgodne czasy to `TtsClipValidationError`, więc dokument jest ponawiany w całości.
  Pusty `PartTiming` (`spoken is False`) to część, której silnik nie wypowiedział: reszta
  nagrania jest cięta i zatwierdzana od razu.
- Niewypowiedziane kwestie dokumentu `_read_lines` czyta od razu jeszcze raz: najpierw razem jako mniejszy dokument
  (tylko gdy jest ich więcej niż jedna i mniej niż w dokumencie), potem każdą wciąż cichą osobno (tylko gdy ostatni
  dokument miał więcej niż jedną kwestię). Dokument identyczny z już przeczytanym się nie powtarza, więc kwestia ma
  najwyżej dwa ponowne odczyty. Dopiero kwestia cicha także sama dostaje `TtsInputError`. `provider_calls`, `retries`
  i czas wcześniejszych odczytów doliczają się do jej końcowego wyniku (`_with_earlier_reads`).
- Ponowne odczyty jednego batcha idą po kolei; kilka dokumentów naraz to kilka batchy (`max_concurrency` workerów
  schedulera, w aplikacji też kilka `TtsService` różnych runów). Zasób wspólny dla nich (jedna przeglądarka i konto
  ElevenReadera) trzyma silnik, nie wspólna warstwa TTS.
- Identyfikator dokumentu `{scope_id}:document:{n}` bierze `n` z licznika `TtsService`, więc jest unikalny w
  całym przebiegu, także między batchami tego samego scope.
- Nagranie i niezatwierdzone klipy są usuwane przed każdą kolejną próbą i po każdym
  dokumencie. `provider_calls` i `retries` dokumentu liczą się na jego pierwszej kwestii.
- `TtsScheduler` dostaje od silnika tylko `locality` (silnik `SYSTEM` ponawia bez
  opóźnienia); nie trzyma instancji silnika.

## Podkatalogi

- `engines/` — leniwy rejestr i różnice kontraktów providerów.
