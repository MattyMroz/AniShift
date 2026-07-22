# Translation engines

Fabryka silników tłumaczenia oparta na rejestrze. `create_engine(config)` buduje konkretny `TranslationEngine`, `available_engine_ids()` zwraca zarejestrowane id.

## Silniki (każdy ma własny AGENTS.md)

- `deepl/` — silnik DeepL (oficjalny SDK, batch natywny)
- `google/` — silnik darmowego Google Translate (googletrans, async pod fasadą)
- `llm/` — silnik przez wstrzyknięty `LlmCompleter` (provider-agnostic)

## Rejestr (`__init__.py`)

- `create_engine` celowo ODRZUCA silnik `llm` mimo obecności w rejestrze — potrzebuje wstrzykniętego completera; `LlmTranslateService` buduje się ręcznie i podaje przez `TranslationService(engine=...)`. `__init__.py:62-67`
- Kolejność guardów jest znacząca: pusty → nieznany → `llm`. `__init__.py:55-67`
- Silniki ładowane leniwie przez `importlib.import_module` (ciężkie SDK poza ścieżką importu domeny) — błąd importu SDK wypływa dopiero przy `create_engine`. `__init__.py:41,68-69`
- `TranslationEngineId` (`Literal["google","deepl","llm"]`) jest źródłem prawdy — wyższe warstwy importują go, nie przepisują własnym stringiem. `__init__.py:22-23`
- `_REGISTRY` mapuje id na krotkę `(module_path, service_class)` jako stringi (nie obiekt klasy) — to mechanizm leniwego ładowania. `__init__.py:25-30`
- `available_engine_ids()` = `tuple(_REGISTRY)`, jedyne źródło prawdy o dostępnych silnikach. `__init__.py:33-35`
