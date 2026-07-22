# tests

Testy pytest. Konwencje testowe całego drzewa; komenda bramki jakości i markery w `pyproject.toml`.

## Pułapki

- Testy importują wprost `from conftest import ...` (bez `pythonpath` w configu) — działają tylko dzięki domyślnemu prepend-mode pytesta wstawiającemu `tests/` do sys.path. Dodanie `__init__.py` do dowolnego podkatalogu testowego to zepsuje. `services/extraction/test_regression_tracks.py:7`
- Istnieje dokładnie JEDEN `__init__.py` (`services/translation/`), reszta katalogów go nie ma — niespójność, którą łatwo nieświadomie „naprawić" i rozwalić importy conftest. `services/translation/__init__.py:1`
- Progi dokładności są zaszyte w asercjach (`>= 0.95`, `>= 0.9586`, `>= 0.9`) — to bramki regresji, nie luźne sanity. `services/extraction/test_regression_tracks.py:63`
- Regresja klasyfikatora ma allowlistę znanych pudeł (`_KNOWN_MISSED_DIALOG`) i faila na KAŻDE nowe pudło, nie tylko na spadek dokładności. `services/subtitles/test_regression_classifier.py:10`
- `test_translation_network.py` liczy ścieżkę datasetu względną `../mm_avh_working_space/...` — działa tylko gdy CWD = katalog repo. `services/translation/test_translation_network.py:20`

## Konwencje

- Testy `network` domyślnie SKIPowane; uruchamiają się tylko z `-m network` (logika w `pytest_collection_modifyitems`, nie w addopts). `conftest.py:26`
- Testy zależne od datasetu spoza repo gate'ują się przez `skipif(not PATH.is_file())` / `pytest.skip()` — brak pliku = zielono, nie czerwono. `services/extraction/test_regression_tracks.py:12`
- Dataset selekcji ścieżek (`TRACKS_DATASET`) i korpus ASS (`MM_AVH_TEMP`) leżą POZA repo, w siostrzanym `../mm_avh_working_space/temp/`. `conftest.py:19`
- Izolacja stanu przez `monkeypatch.setattr` (config_path/resolve_binary/is_windows/Popen), brak globalnego autouse fixture — każdy test patchuje sam. `config/test_user_settings.py:19`, `platform/test_binaries.py:18`
- Testy zależne od systemu wymuszają zachowanie przez `monkeypatch.setattr(..., "is_windows", ...)` zamiast realnego OS. `platform/test_binaries.py:19`

## Komendy i konfiguracja (`pyproject.toml`)

- `testpaths` obejmuje nie tylko `tests/`, ale też `anishift/utils/{logger,rich_console,timer}/tests` — czyste `uv run pytest tests/` je pomija. `pyproject.toml:120`
- Testy biegną równolegle (xdist `-n auto --dist=worksteal`) — muszą być bezstanowe/niezależne od kolejności. `pyproject.toml:141`
- `--strict-markers` + `--strict-config`: niezadeklarowany marker = błąd; wszystkie markery muszą być w `[tool.pytest.ini_options].markers`. `pyproject.toml:138`
- Zadeklarowanych 6 markerów (`unit`/`integration`/`e2e`/`network`/`slow`/`smoke`), ale w kodzie realnie używany tylko `network`. `pyproject.toml:129`

## Dane testowe

- `data/youjo-senki-ii-01.json` — surowy output mkvmerge, używany w `test_extraction_service.py`
- `data/mushoku-tensei-s3-03.json` — surowy output mkvmerge, do żadnego testu nie podpięty
- `test_regression_tracks.py` sam mapuje kodeki datasetu na codec_id (`SubStationAlpha`→`S_TEXT/ASS`) — dataset trzyma nazwy ludzkie. `services/extraction/test_regression_tracks.py:15`
