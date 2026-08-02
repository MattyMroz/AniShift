# translation

Serwis tłumaczenia: synchroniczna fasada `TranslationService` nad jednym silnikiem z łańcuchem fallbacku. Cel zawsze polski.

## Mapa katalogów

- `service.py` — fasada `TranslationService`, łańcuch fallbacku silników
- `config.py` — `TranslationConfig` (forward-compatible, nieznane klucze ignorowane z warnem)
- `constants.py` — stałe domeny (`TARGET_LANG="pl"`, batch, retries); bez nazw silników i sekretów
- `protocols.py` — kontrakty `TranslationEngine` i `LlmCompleter` (DI z composition root)
- `chunking.py` — domenowe cięcie dokumentu (`chunk_text`); wspólne granice i grafemy są w `anishift/text/`
- `linebreak.py` — polski reflow (`split_line`) i odtwarzanie authored layoutu (`split_for_layout`)
- `_retry.py` — retry z wykładniczym backoffem (sync + async), bez tenacity
- `types.py` — dataclassy wartości (`BatchedLine`, `TranslatedLine`, `FileTranslation`)
- `errors.py` — hierarchia wyjątków domeny
- `engines/` — rejestr i implementacje silników (deepl/google/llm); ma własny AGENTS.md

## Pułapki

- `TranslationConfig` NIE waliduje typów ani nieznanych kluczy błędem — nieznane klucze tylko logują warning i są ignorowane; brak/pusty `engine` to jedyny warunek rzucający `TranslationConfigError`. `config.py:53-66`
- `TranslationConfig` używa `init=False` + ręcznego `__init__` przepisującego pola; `MISSING` default staje się `None` — pominięte pole bez defaultu wyląduje jako `None`, nie rzuci. `config.py:68-70`
- Composition wstrzykuje `engine_factory=`, nie gotowy engine. Factory dostaje każdy wpis fallback chain i bazowy `TranslationConfig`; to jedyne wspierane spięcie silnika LLM. `service.py`
- Silnik jest zawsze zamykany w `finally` po każdej próbie, także po sukcesie — `close()` wykona się przed zwrotem. `service.py:83-94`
- `translate_file` łapie bazowy `TranslationError`, zachowuje `ErrorContext` w wyniku i natychmiast przepuszcza `CANCELLED`; błędy programistyczne nadal przebijają. `service.py`
- Anulowanie sprawdzane tylko na starcie każdej iteracji łańcucha, nie w trakcie tłumaczenia pliku; rzuca `TranslationError` z `ErrorCode.CANCELLED`. `service.py:76-78`
- `_prepare_file` pomija puste/whitespace linie (mapa `-1`); pominięte pozycje przechodzą bez tłumaczenia jako sukces. `service.py:208-241`
- `chunk_text` gwarantuje, że konkatenacja kawałków odtwarza wejście DOKŁADNIE (separatory po lewej stronie) — nie wolno trymować kawałków. `chunking.py:334-346`
- Efektywny limit cięcia to `min(chunk_limit, char_limit)` — sam duży `char_limit` bez zmiany `chunk_limit` nie da większych kawałków. `chunking.py:474`

## Konwencje

- Separatory fraz, domknięcia, skróty EN+PL i grafemy pochodzą z bezdomenowego `anishift/text/`; tutaj zostaje hierarchia i pakowanie requestów translation. `chunking.py`
- Heurystyka „fałszywego końca zdania" jest współdzielona z TTS; adapter translation przekazuje jej całe fragmenty przed i po potencjalnej granicy. `chunking.py`
- `split_line` buduje nowy polski podział, a `split_for_layout` zachowuje authored line count dla złożonych `displayed`, jeśli target ma dość granic słów; nigdy nie rozcina pojedynczego słowa ani nie tworzy pustej linii. `linebreak.py`
- `_retry` świadomie bez tenacity — nie jest zależnością projektu. `_retry.py:1-7`
- `api_calls` w `FileTranslation` liczy logiczne wywołania `translate_batch` (zwykle 1 na wspólny strumień pliku), nie surowe HTTP. `types.py`
- `linebreak` reużywa zbiorów z `chunking` (`SENTENCE_ENDINGS`, `phrase_cut_chars()`) jako SSOT. `linebreak.py:23,33,36`

## Decyzje

- `translation` NIGDY nie importuje `anishift.services.llm` — silnik LLM dostaje protokół `LlmCompleter` przez DI (etap 5). `protocols.py:2-7,43-53`
- Per-request limit znaków NIE jest w `TranslationConfig` — to twardy limit silnika (Google 15000, DeepL 128 KiB), by fasada nie mogła go zaniżyć. `config.py:35-38`
- `TARGET_LANG = "pl"` zawsze — config nie niesie języka docelowego. `constants.py:11`
- `_run` scala `spoken` i tekstowe `displayed` chronologicznie do jednego wywołania. LLM zachowuje każde `spoken` i deduplikuje `displayed`; Google/DeepL deduplikują oba. `service.py`
