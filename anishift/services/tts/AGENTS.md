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
- `anishift.pipeline`
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

## Podkatalogi

- `engines/` — leniwy rejestr i różnice kontraktów providerów.
