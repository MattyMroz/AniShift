# services

Domeny usług. Każda domena z wyborem silnika ma rejestr w `engines/`; reszta to zwykłe moduły.

## Domeny (każda ma własny AGENTS.md)

- `audio/` — timeline, normalizacja, kanały, miks, codec i resume sidecara
- `extraction/` — neutralna ekstrakcja pojedynczych ścieżek z MKV/MP4 oraz legacy ekstrakcja MKV
- `llm/` — providerzy modeli językowych z leniwym rejestrem
- `media/` — neutralne rozpoznawanie kontenerów i ścieżek MKV/MP4
- `subtitles/` — klasyfikacja stylów ASS, split spoken/displayed, zapis ASS/SRT
- `translation/` — tłumaczenie z rejestrem silników (deepl/google/llm)
- `tts/` — neutralna synteza mowy z rejestrem providerów i resume klipów

## Fakty

- `anishift/services/__init__.py` jest pusty (bez `__all__`, bez importów podmodułów) — dostęp do domen tylko przez pełne ścieżki `anishift.services.<domena>`, nie przez `anishift.services`.
- Wspólny kontrakt każdego silnika (dowolnej domeny) to tylko dwie właściwości `engine_id` i `is_available` (Protocol `EngineInfo`); reszta w protokołach domenowych, które ten bazowy rozszerzają. `_base.py:19-27`
- `EngineInfo` jest `@runtime_checkable` — `isinstance()` sprawdza wyłącznie obecność atrybutów `engine_id`/`is_available`, nie typy ani sygnatury. `_base.py:12`
