# Google engine

Darmowy Google Translate przez stronę mobilną `translate.google.com/m`, w pełni synchroniczny. Bez klucza. Rejestrowany pod `engine_id = "google"`.

## Dlaczego strona mobilna, a nie JSON API

Google odpowiada na endpoint `translate_a/single` (którego używała biblioteka `googletrans`) kodem **429 + stroną „Sorry...”**, więc stary klient przestał tłumaczyć — i robił to CICHO, zwracając tekst źródłowy bez wyjątku. Strona `/m` nadal tłumaczy, ale tylko klientom wyglądającym na przeglądarkę: z domyślnym `python-requests`/bez UA wraca HTTP 200 ze stroną BEZ kontenera wyniku. Dlatego `USER_AGENT` jest wymogiem funkcjonalnym, nie kosmetyką. `deep-translator` odpada, bo jego `requests.get` nie przyjmuje nagłówków.

## Pułapki

- Kontener wyniku musi istnieć: jego brak to `TranslationEngineError`, NIGDY zwrot źródła. Cicha degradacja jest dokładnie tym, co ukryło zepsuty silnik na długo. `api_backend.py:97-101`
- Wynik trzeba przepuścić przez `html.unescape` — strona zwraca encje (`&#39;`, `&#324;`), więc bez tego apostrofy i polskie znaki trafiłyby do napisów jako `&#...;`. `api_backend.py:103`
- `429` i `503` mapują się na `TranslationRateLimitError` (transient, retry z backoffem); pozostałe błędy HTTP na `TranslationEngineError` bez ponowień, bo powtórka przyniesie tę samą pustą stronę. `api_backend.py:78-85`
- `translate_batch` NIE odpala event loopa — silnik jest synchroniczny zgodnie z engine-standard („nie odpalaj `asyncio.run()` wewnątrz engine'a”). Poprzednia wersja łamała to świadomie tylko dlatego, że `googletrans` był async; ten powód zniknął razem z zależnością.
- `source_lang` jest przekazywany (`sl`), a pusty cicho staje się `auto`; `target_lang` pusty cicho → `"pl"`. `service.py:78-79`
- Przekazanie `TranslationConfig` do konstruktora GUBI `max_chars_per_request` (bierze tylko `batch_size`, `max_retries`; reszta z defaultów `GoogleConfig`). `service.py:38-42`
- `LINE_SEPARATOR` = `ZERO_WIDTH###ZERO_WIDTH`; sprawdzone, że strona mobilna go zachowuje, więc batch 5 linii wraca jako 5 części. Gdy tłumacz go zeżre, drabina schodzi do newline, a potem do per-line. `constants.py:30`, `_batching.py:67-86`
- Puste wyjście dla niepustego wejścia = porażka: `_map_parts` wstawia źródło z `ok=False`, nie pustą linię. `_batching.py:94-95`
- Kod zakłada, że każda linia wejścia jest jednoliniowa (stage napisów zwija `\n`/`\N` do spacji przed tłumaczeniem) — złamanie tego rozjedzie split. `_batching.py:8-12`
- Klient HTTP jest tworzony leniwie przy pierwszym tłumaczeniu i reużywany na cały plik; `close()` jest idempotentny i zeruje referencję. `service.py:56-60,88-92`

## Konwencje

- Klient zewnętrznego API siedzi w `api_backend.py`, zgodnie z engine-standard; `service.py` trzyma tylko lifecycle i orkiestrację drabiny.
- Requesty ZAWSZE sekwencyjnie, bez `gather` — świadomie, by unikać rate-limitów darmowego endpointu. `_batching.py:6-7`
- Retry przez wspólny synchroniczny `call_with_retry` z `translation._retry` (ten sam co DeepL), `retry_on=TRANSIENT_ERRORS`, `max_attempts = max_retries + 1`. `service.py:113-124`
- `except Exception` w drabinie dozwolony z `noqa: BLE001` — granica providera, strona nie ma stabilnego kształtu awarii. `_batching.py:60,84`
- `is_available` zawsze `True` (endpoint bez klucza). `service.py:52-54`
- Silnik nie ma `model_id` ani `provider_model_id` — Google Translate nie wystawia wyboru modelu, więc pole z engine-standard nie ma tu bytu do reprezentowania (tak samo w DeepL).

## Stałe i odesłania

- `BASE_URL`, `USER_AGENT`, `REQUEST_TIMEOUT_S` — kontrakt transportu strony mobilnej. `constants.py:9-22`
- `MAX_CHARS_PER_REQUEST` (15000) — SSOT twardego limitu Google. `constants.py:24`
- `TRANSIENT_ERRORS` — co wolno ponowić; SSOT dla polityki retry silnika. `api_backend.py:39`
- `batch_size`, `max_retries`, `ZERO_WIDTH` przychodzą z modułów wyżej (`translation.constants`, `translation.chunking`). `config.py:7-11`, `constants.py:7`
