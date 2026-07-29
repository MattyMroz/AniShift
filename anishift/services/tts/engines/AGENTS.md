# services/tts/engines

Leniwy rejestr adapterów providerów TTS.

## Registry

- `_REGISTRY` przechowuje module path i class name jako stringi. Importuj tylko
  provider wybrany przez `TtsConfig`; import registry nie może ładować SDK.
- Stabilna kolejność publiczna to `edge`, `elevenbytes`, `elevenlabs`, `sapi`.
  Panel ustawień i testy korzystają z tej kolejności.
- Nieznany `engine_id` jest mapowany na `TtsConfigError`. `ImportError` wybranego
  modułu i `AttributeError` błędnej nazwy klasy pozostają surowymi błędami
  composition; nie ukrywaj ich jako „engine unavailable”. `__init__.py`

## Adaptery

- `edge/` — Microsoft Edge TTS z kontrolowanym patchem jakości zależności.
- `elevenbytes/` — publiczne proxy ElevenBytes, domyślnie stabilny endpoint run6.
- `elevenlabs/` — oficjalne, potencjalnie płatne API ElevenLabs.
- `sapi/` — lokalny, architekturowo izolowany worker Windows SAPI.
