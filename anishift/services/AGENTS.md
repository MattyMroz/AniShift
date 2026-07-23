# services

Domeny usług. Każda domena z wyborem silnika ma rejestr w `engines/`; reszta to zwykłe moduły.

## Domeny (każda ma własny AGENTS.md)

- `extraction/` — ekstrakcja ścieżek audio/napisów z MKV
- `subtitles/` — klasyfikacja stylów ASS, split spoken/displayed, zapis ASS/SRT
- `translation/` — tłumaczenie z rejestrem silników (deepl/google/llm)

## Fakty

- `anishift/services/__init__.py` jest pusty (bez `__all__`, bez importów podmodułów) — dostęp do domen tylko przez pełne ścieżki `anishift.services.<domena>`, nie przez `anishift.services`.
- Wspólny kontrakt każdego silnika (dowolnej domeny) to tylko dwie właściwości `engine_id` i `is_available` (Protocol `EngineInfo`); reszta w protokołach domenowych, które ten bazowy rozszerzają. `_base.py:19-27`
- `EngineInfo` jest `@runtime_checkable` — `isinstance()` sprawdza wyłącznie obecność atrybutów `engine_id`/`is_available`, nie typy ani sygnatury. `_base.py:12`
