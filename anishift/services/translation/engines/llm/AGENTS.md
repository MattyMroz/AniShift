# LLM engine

Silnik tłumaczenia przez wstrzyknięty `LlmCompleter` (provider-agnostic). Rejestrowany pod `engine_id = "llm"`.

## Pułapki

- Świadomie NIE importuje `anishift.services.llm` — completer dostaje przez wstrzyknięcie (`__init__` wymaga go), a realny podłącza runtime boundary. `service.py:1-8,53-61`
- Konstruktor przyjmuje wyłącznie `LlmTranslateConfig`; zwykły `TranslationConfig` jest błędem zamiast cichego użycia ustawień domyślnych. Jawny config LLM buduje `application/runtime.py`. `service.py`, `anishift/application/runtime.py:442`
- `_parse_numbered` zwraca `None` (odrzuca CAŁĄ partię) przy jakimkolwiek zdublowanym, brakującym lub spoza zakresu indeksie — nie tylko przy złej liczbie linii. `service.py:40-45`
- Porażka pojedynczej linii rzuca `TranslationEngineError`; źródło nigdy nie jest zwracane jako udane tłumaczenie. `service.py`
- `TranslationContextLengthError`, output limit i błędny format uruchamiają stabilny podział na połowy; inne błędy transportu propagują bez shrink. `service.py`

## Konwencje

- Protokół to numerowane linie `[N] text`, NIE JSON — parser trzyma tylko linie pasujące do `LINE_PATTERN`, resztę (intro/markdown/outro) ignoruje. `service.py:3-4`, `constants.py:1,17-18`
- Drabina ma stałą kolejność: pełna partia → jedna naprawa formatu → stabilne połowienie → błąd pojedynczej linii. `service.py`
- Engine łapie wyłącznie typed context-length error; pozostałe błędy completera propagują do fasady i schedulera. `service.py`
- `close()` no-op — completer należy do composition root. `service.py:73-74`
- `LINE_PATTERN` toleruje wiodące spacje i co najwyżej jedną po `]` (`\s?`); tekst grupy jest `.strip()`-owany. `constants.py:17`, `service.py:42`
- `prompts/` składa task, style, moduły i obowiązkowy contract; dane runtime są escapowane i nie wchodzą do fingerprintu. Custom `.txt` pochodzą z `config/prompts/`. `prompts/`
