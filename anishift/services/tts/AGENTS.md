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
