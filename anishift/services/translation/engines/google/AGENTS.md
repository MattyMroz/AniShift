# Google engine

Darmowy Google Translate (`googletrans` 4.x, async pod synchroniczną fasadą). Bez klucza. Rejestrowany pod `engine_id = "google"`.

## Pułapki

- `translate_batch` opakowuje CAŁY plik w jeden `asyncio.run` (jeden event loop i klient na plik, nie na batch) — wołanie z aktywnej pętli asyncio wybuchnie. `service.py:66,70-72`
- `source_lang` jawnie ignorowany (`del source_lang`) — googletrans sam wykrywa źródło. `service.py:62`
- `target_lang` pusty/None cicho → `"pl"`. `service.py:65`
- Przekazanie `TranslationConfig` do konstruktora GUBI `max_chars_per_request` (bierze tylko `batch_size`, `max_retries`; reszta z defaultów `GoogleConfig`). `service.py:36-39`
- `LINE_SEPARATOR` = `ZERO_WIDTH###ZERO_WIDTH`; jeśli tłumacz zeżre zero-width, split się nie zgadza i drabina schodzi do wolniejszego per-line. `constants.py:18`, `_batching.py:75-86`
- Puste wyjście dla niepustego wejścia = porażka: `_map_parts` wstawia źródło z `ok=False`, nie pustą linię. `_batching.py:94-95`
- Kod zakłada, że każda linia wejścia jest jednoliniowa (stage napisów zwija `\n`/`\N` do spacji przed tłumaczeniem) — złamanie tego rozjedzie split. `_batching.py:8-12`

## Konwencje

- Requesty ZAWSZE sekwencyjnie, bez `gather` — świadomie, by unikać rate-limitów darmowego endpointu. `_batching.py:6-7,124`
- Tylko `httpx.HTTPError` traktowany jako transient i retry'owany; reszta (błędy parsowania) leci w górę i wtedy drabina łapie per-line. `service.py:87-90,96-102`
- `except Exception` dozwolony z `noqa: BLE001` — googletrans nie ma stabilnej hierarchii wyjątków. `_batching.py:60,84`
- `Translator` i `httpx` importowane leniwie w metodach (`noqa: PLC0415`). `service.py:70,91`
- `is_available` zawsze `True` (endpoint bez klucza); `close()` no-op (brak trwałego klienta). `service.py:47-52`

## Stałe i odesłania

- `MAX_CHARS_PER_REQUEST` (15000) — SSOT twardego limitu Google. `constants.py:9`
- `batch_size`, `max_retries`, `ZERO_WIDTH` przychodzą z modułów wyżej (`translation.constants`, `translation.chunking`). `config.py:7-11`, `constants.py:7`
