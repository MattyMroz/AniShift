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

- Registry jest jedynym źródłem prawdy o ID: `edge`, `elevenbytes`, `elevenlabs`,
  `sapi`.
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

## Ścieżka dokumentu

- Silnik z `capabilities.max_document_chars` czyta brakujące kwestie batcha zachłannymi
  dokumentami (`document_chars` silnika ≤ limit) przez `DocumentTtsEngine.synthesize_document`;
  wymaga wstrzykniętego `ClipSplitter`, inaczej każda kwestia mowy dostaje
  `TtsUnsupportedError`.
- Kwestia, która nie mieści się w jednej części albo której nie przyjmuje
  `DocumentTtsEngine.validate_part`, dostaje `TtsInputError` przed grupowaniem; reszta
  batcha idzie dalej. Resume, tożsamość i commit są per kwestia jak w ścieżce zwykłej.
- `accept_result` sprawdza własność nagrania i kolejność `PartTiming`, tnie nagranie
  (`open_end = not ends_sentence(text)`) i waliduje każdy klip; błąd splittera albo
  niezgodne czasy to `TtsClipValidationError`, więc dokument jest ponawiany w całości.
  Pusty `PartTiming` (`spoken is False`) to część, której silnik nie wypowiedział: tylko
  ta kwestia dostaje `TtsInputError`, reszta nagrania jest cięta i zatwierdzana.
- Identyfikator dokumentu `{scope_id}:document:{n}` bierze `n` z licznika `TtsService`, więc jest unikalny w
  całym przebiegu, także między batchami tego samego scope.
- Nagranie i niezatwierdzone klipy są usuwane przed każdą kolejną próbą i po każdym
  dokumencie. `provider_calls` i `retries` dokumentu liczą się na jego pierwszej kwestii.
- `TtsScheduler` dostaje od silnika tylko `locality` (silnik `SYSTEM` ponawia bez
  opóźnienia); nie trzyma instancji silnika.

## Podkatalogi

- `engines/` — leniwy rejestr i różnice kontraktów providerów.
