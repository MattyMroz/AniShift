# services/tts/engines

Leniwy rejestr adapterów providerów TTS.

## Registry

- `_REGISTRY` przechowuje module path i class name jako stringi. Importuj tylko
  provider wybrany przez `TtsConfig`; import registry nie może ładować SDK.
- Stabilna kolejność publiczna to `edge`, `elevenbytes`, `elevenlabs`, `elevenreader`,
  `sapi`. Panel ustawień i testy korzystają z tej kolejności.
- `is_document_engine(engine_id)` to jedyne źródło wiedzy, który silnik czyta cały batch
  dokumentem (`_DOCUMENT_ENGINES`), bez importu silnika. Test pilnuje, że zbiór zgadza się
  z `capabilities.reads_documents`.
- Nieznany `engine_id` jest mapowany na `TtsConfigError`. `ImportError` wybranego
  modułu i `AttributeError` błędnej nazwy klasy pozostają surowymi błędami
  composition; nie ukrywaj ich jako „engine unavailable”. `__init__.py`

## Układ adaptera

- Każdy adapter ma `AGENTS.md`, `__init__.py`, `config.py`, `constants.py` i `service.py` (klasa silnika),
  a `types.py` tylko dla typów danych. Zdalny adapter ma `api_backend.py`: jedna próba u dostawcy razem z
  mapowaniem jego błędów; lokalny `sapi` ma w tej roli `worker.py` i `protocol.py`. Żaden nie ma `errors.py`.
- Moduł spoza standardu tylko z uzasadnieniem: `edge/patch.py`, `elevenbytes/vpn.py`,
  `elevenlabs/options.py`, `elevenreader/{browser,host,hub,recorder,redo}.py`.
- Testy: `tests/services/tts/test_tts_<silnik>[_<moduł>].py`; test `network` w osobnym pliku `_network`.

## Adaptery

- `edge/` — Microsoft Edge TTS z kontrolowanym patchem jakości zależności.
- `elevenbytes/` — publiczne proxy ElevenBytes, domyślnie stabilny endpoint run6.
- `elevenlabs/` — oficjalne, potencjalnie płatne API ElevenLabs.
- `elevenreader/` — ElevenReader (Eleven v4) przez prawdziwy Chrome z zalogowanym profilem;
  silnik dokumentowy. Wszystko, co zależy od AniShift, jest w `elevenreader/host.py`: polskie teksty dla panelu
  (Ustawienia → Lektor, `FALLBACK_HINT`), `EngineSurface` (protokół `TtsEngine`: `engine_id`, `capabilities`,
  dostępność, głosy, odmowa `synthesize`), `engine_config` z `TtsConfig` (zawsze `Redo.LINE`: część to kwestia),
  `check_request` (`eleven_v4`, bez opcji), `mono_pcm` (FFmpeg z `anishift.platform.binaries`, bo domena TTS nie
  importuje `services.audio`) i `ChromeBusyError` jako błąd przejściowy z `retry_after_s`. Panel loguje przez
  `sign_in` (okno bez sterowania) i wylogowuje przez `sign_out`. Linia z `incomplete` w wyniku dokumentu kończy się
  w `TtsService` błędem tej linii bez kolejnego odczytu (z `incomplete_cause`, gdy jest); pozostałe linie zostają.
  `TtsService` po każdej próbie dokumentu usuwa nagranie i każdy plik, który silnik zapisał pod jego nazwą (próby,
  `stream.txt`), bo wynikiem AniShift są przyjęte klipy linii, a nie nagranie. Chrome jest dzieckiem rezydenta
  (Job Object kończy go z rezydentem), okno logowania dostaje `independent_child_flags`. Testy sieciowe silnika:
  `test_tts_elevenreader_network.py` (`-m network`, prawdziwe konto, nie uruchamiaj bez polecenia).
- `sapi/` — lokalny, architekturowo izolowany worker Windows SAPI.
