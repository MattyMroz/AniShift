# DeepL engine

Silnik tłumaczenia przez oficjalny SDK `deepl` (synchroniczny, batch natywny). Rejestrowany pod `engine_id = "deepl"`.

## Pułapki

- SDK `deepl` importowany leniwie (`_map_sdk_error`, `_ensure_client`) — moduł importuje się bez SDK, brak paczki wybucha dopiero przy tłumaczeniu. `service.py:38,113`
- Klient tworzony leniwie przy pierwszym `translate_batch`, nie w `__init__`; `_ensure_client` idempotentny, rzuca `TranslationAuthError` gdy brak klucza. `service.py:102-115`
- Pusty `texts` → `[]` przed utworzeniem klienta, więc klucz NIE jest wtedy walidowany. `service.py:125-126`
- Kody języków: `en`→`EN-US`, `pt`→`PT-PT`, `auto`→`None` (bare `EN`/`PT` nie są wysyłane; `None` = DeepL pomija `source_lang`). `_lang_codes.py:12-15,30-31`
- `target_lang` mapowany na `None` cicho fallbackuje do `"EN-US"` — cel `auto` da angielski, nie błąd. `service.py:128`
- `_chunk_batches` liczy linię jako `len(utf-8)+1`; limit bajtów sprawdzany tylko gdy `current` niepuste — pojedyncza linia > `MAX_PAYLOAD_BYTES` i tak trafia do jednego chunku. `service.py:57-64`

## Konwencje

- Jedyne `except Exception` (w `_translate_once`) natychmiast mapuje przez `_map_sdk_error`, który dla nie-DeepL błędów zwraca oryginał. `service.py:147-148`
- `_map_sdk_error` sprawdza podtypy od najszczegółowszego do `DeepLException` — kolejność `isinstance` jest istotna. `service.py:40-47`
- `__init__` przyjmuje `TranslationConfig` lub `DeeplConfig`; ten pierwszy jest ręcznie przepakowywany. `service.py:76-85`

## Stałe i odesłania

- `MAX_PAYLOAD_BYTES` (128 KiB) — SSOT limitu payloadu DeepL. `constants.py:7`
- `DeeplConfig.batch_size`/`max_retries` domyślnie z `translation.constants`. `config.py:23-24`
- Retry rate-limitów przez `call_with_retry` z `translation._retry` (`retry_on=TranslationRateLimitError`, `max_attempts = max_retries + 1`). `service.py:130,134-139`
