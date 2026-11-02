# Translation engines

Fabryka silników tłumaczenia oparta na rejestrze. `create_engine(config)` buduje konkretny `TranslationEngine`, `available_engine_ids()` zwraca zarejestrowane id.

## Silniki (każdy ma własny AGENTS.md)

- `deepl/` — silnik DeepL (oficjalny SDK, batch natywny)
- `google/` — silnik darmowego Google Translate (strona mobilna `/m`, synchroniczny)
- `llm/` — silnik przez wstrzyknięty `LlmCompleter` (provider-agnostic)

## Rejestr (`__init__.py`)

- `create_engine` celowo ODRZUCA silnik `llm` mimo obecności w rejestrze — pipeline buduje `LlmTranslateService` przez `TranslationService(engine_factory=...)`. `__init__.py`
- Kolejność guardów jest znacząca: pusty → nieznany → `llm`. `__init__.py`
- Silniki ładowane leniwie przez `importlib.import_module` (ciężkie SDK poza ścieżką importu domeny) — błąd importu SDK wypływa dopiero przy `create_engine`. `__init__.py`
- `TranslationEngineId` (`Literal["google","deepl","llm"]`) jest źródłem prawdy — wyższe warstwy importują go, nie przepisują własnym stringiem. `__init__.py`
- `_REGISTRY` mapuje id na krotkę `(module_path, service_class)` jako stringi (nie obiekt klasy) — to mechanizm leniwego ładowania. `__init__.py`
- `available_engine_ids()` = `tuple(_REGISTRY)`, jedyne źródło prawdy o dostępnych silnikach. `__init__.py`
