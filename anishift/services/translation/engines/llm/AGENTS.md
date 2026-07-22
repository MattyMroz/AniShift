# LLM engine

Silnik tłumaczenia przez wstrzyknięty `LlmCompleter` (provider-agnostic). Rejestrowany pod `engine_id = "llm"`.

## Pułapki

- Świadomie NIE importuje `anishift.services.llm` — completer dostaje przez wstrzyknięcie (`__init__` wymaga go), realny podłącza dopiero etap 5. `service.py:1-8,53-61`
- Konstruktor po cichu odrzuca przekazany `TranslationConfig`: jeśli config nie jest `LlmTranslateConfig`, tworzy świeży domyślny, gubiąc ustawienia. `service.py:60`
- `_parse_numbered` zwraca `None` (odrzuca CAŁĄ partię) przy jakimkolwiek zdublowanym, brakującym lub spoza zakresu indeksie — nie tylko przy złej liczbie linii. `service.py:40-45`
- `source_lang` ignorowany (`del source_lang`); rekurencja w `_shrink` przekazuje na sztywno `"auto"`. `service.py:84,101-102`
- Ostatni szczebel drabiny (per-line) przy porażce wkłada ORYGINALNY tekst źródłowy z `ok=False`, nie przekład. `service.py:112-113`
- `min_batch_size` domyślnie `1`, więc `_shrink` schodzi do pojedynczych linii; ustawienie wyżej przerywa połowienie wcześniej. `config.py:19`, `service.py:98-99`

## Konwencje

- Protokół to numerowane linie `[N] text`, NIE JSON — parser trzyma tylko linie pasujące do `LINE_PATTERN`, resztę (intro/markdown/outro) ignoruje. `service.py:3-4`, `constants.py:1,17-18`
- Drabina fallbacku, stała kolejność: pełna partia → `max_repair_attempts` prób naprawczych → połowienie rekurencyjne → linia po linii → pad źródłem. `service.py:87-94`
- Szeroki `except Exception` na granicy completera jest celowy (`noqa: BLE001`) — każdy błąd degraduje do fallbacku. `service.py:121`
- `close()` no-op — completer należy do composition root. `service.py:73-74`
- `LINE_PATTERN` toleruje wiodące spacje i co najwyżej jedną po `]` (`\s?`); tekst grupy jest `.strip()`-owany. `constants.py:17`, `service.py:42`
- `_ask(repair=True)` dokleja przypomnienie o liczbie linii do promptu użytkownika, nie systemowego. `service.py:125-131`
