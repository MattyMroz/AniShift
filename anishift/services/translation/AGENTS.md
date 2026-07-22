# translation

Serwis tłumaczenia: synchroniczna fasada `TranslationService` nad jednym silnikiem z łańcuchem fallbacku. Cel zawsze polski.

## Mapa katalogów

- `service.py` — fasada `TranslationService`, łańcuch fallbacku silników
- `config.py` — `TranslationConfig` (forward-compatible, nieznane klucze ignorowane z warnem)
- `constants.py` — stałe domeny (`TARGET_LANG="pl"`, batch, retries); bez nazw silników i sekretów
- `protocols.py` — kontrakty `TranslationEngine` i `LlmCompleter` (DI z composition root)
- `chunking.py` — wielojęzyczne cięcie tekstu na kawałki (`chunk_text`), ścieżka txt
- `linebreak.py` — dzielenie przetłumaczonej linii na maks. 2 wersy ekranowe (`split_line`)
- `dedup.py` — deduplikacja identycznych linii + mapa redystrybucji
- `_retry.py` — retry z wykładniczym backoffem (sync + async), bez tenacity
- `types.py` — dataclassy wartości (`BatchedLine`, `TranslatedLine`, `FileTranslation`)
- `errors.py` — hierarchia wyjątków domeny
- `engines/` — rejestr i implementacje silników (deepl/google/llm); ma własny AGENTS.md

## Pułapki

- `TranslationConfig` NIE waliduje typów ani nieznanych kluczy błędem — nieznane klucze tylko logują warning i są ignorowane; brak/pusty `engine` to jedyny warunek rzucający `TranslationConfigError`. `config.py:53-66`
- `TranslationConfig` używa `init=False` + ręcznego `__init__` przepisującego pola; `MISSING` default staje się `None` — pominięte pole bez defaultu wyląduje jako `None`, nie rzuci. `config.py:68-70`
- Wstrzyknięty silnik (`engine=`) całkowicie wyłącza łańcuch fallbacku — `_resolve_chain` zwraca tylko jego `engine_id`, ignorując `config.engine` i `fallback_chain`. `service.py:97-101`
- Silnik jest zawsze zamykany w `finally` po każdej próbie, także po sukcesie — `close()` wykona się przed zwrotem. `service.py:83-94`
- `translate_file` łapie tylko cztery błędy (Quota/RateLimit/Auth/Engine); każdy inny wyjątek przebije fallback i wyleci. `service.py:85-92`
- Anulowanie sprawdzane tylko na starcie każdej iteracji łańcucha, nie w trakcie tłumaczenia pliku; rzuca `TranslationError` z `ErrorCode.CANCELLED`. `service.py:76-78`
- `deduplicate` mapuje puste/whitespace linie na `-1` i pomija; puste linie zawsze liczą się jako sukces (`redistribute_flags`→`True`). `dedup.py:38-45,76`
- `chunk_text` gwarantuje, że konkatenacja kawałków odtwarza wejście DOKŁADNIE (separatory po lewej stronie) — nie wolno trymować kawałków. `chunking.py:334-346`
- Efektywny limit cięcia to `min(chunk_limit, char_limit)` — sam duży `char_limit` bez zmiany `chunk_limit` nie da większych kawałków. `chunking.py:474`

## Konwencje

- `_PHRASE_CUT_CHARS`/`_CLOSING_MARKS` budowane przez skan CAŁEGO Unicode (0x0–0x10FFFF) w czasie importu — koszt jednorazowy. `chunking.py:52-54`
- Heurystyka „fałszywego końca zdania" działa językowo-niezależnie; lista skrótów EN+PL rozstrzyga tylko wielką literę po kropce. `chunking.py:380-397`
- `linebreak` celowo NIE odtwarza układu źródła — buduje nowy podział pod polską składnię (maks. 2 wersy). `linebreak.py:1-16`
- `_retry` świadomie bez tenacity — nie jest zależnością projektu. `_retry.py:1-7`
- `api_calls` w `FileTranslation` liczy wywołania `translate_batch` (maks. 2 na plik: spoken + displayed), nie surowe HTTP. `types.py:60-63`
- `linebreak` reużywa zbiorów z `chunking` (`SENTENCE_ENDINGS`, `phrase_cut_chars()`) jako SSOT. `linebreak.py:23,33,36`

## Decyzje

- `translation` NIGDY nie importuje `anishift.services.llm` — silnik LLM dostaje protokół `LlmCompleter` przez DI (etap 5). `protocols.py:2-7,43-53`
- Per-request limit znaków NIE jest w `TranslationConfig` — to twardy limit silnika (Google 15000, DeepL 128 KiB), by fasada nie mogła go zaniżyć. `config.py:35-38`
- `TARGET_LANG = "pl"` zawsze — config nie niesie języka docelowego. `constants.py:11`
- `_run` woła silnik dwa razy (osobno spoken i displayed), z osobną deduplikacją każdego strumienia. `service.py:118-133`
