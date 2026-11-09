# tests

Testy pytest. Konwencje testowe całego drzewa; komenda bramki jakości i markery w `pyproject.toml`.

## Pułapki

- Testy importują wprost `from conftest import ...` (bez `pythonpath` w configu) — działają tylko dzięki domyślnemu prepend-mode pytesta wstawiającemu `tests/` do sys.path. Dodanie `__init__.py` do dowolnego podkatalogu testowego to zepsuje. `platform/test_qbittorrent_process.py`
- Istnieje dokładnie JEDEN `__init__.py` (`services/translation/`), reszta katalogów go nie ma — niespójność, którą łatwo nieświadomie „naprawić" i rozwalić importy conftest. `services/translation/__init__.py`
- Progi dokładności są zaszyte w asercjach (`>= 0.9586`) — to bramki regresji, nie luźne sanity. `services/subtitles/test_regression_classifier.py`
- Regresja klasyfikatora ma allowlistę znanych pudeł (`_KNOWN_MISSED_DIALOG`) i faila na KAŻDE nowe pudło, nie tylko na spadek dokładności. `services/subtitles/test_regression_classifier.py`
- Wątek `AnimeController` zeruje `_worker` przed swoimi ostatnimi skutkami (np. przejściem na listę subskrypcji), więc `_worker is None` nie dowodzi końca pracy; czekaj na koniec wątków `_WORKER_NAME` uruchomionych przez klawisz (`test_subscription_draft._keys`). `cli/test_subscription_draft.py`
- Pomocnik oczekiwania ma zwracać sukces przy pierwszej obserwacji warunku, nie oceniać go drugi raz: `run_result` wraca chwilowo do `running` przy ponowieniu odroczonej relokacji. Plik przekazany do Auto bywa otwarty przez sondę `mkvmerge`; test usuwający go na Windows używa `_unlink_when_released`. `application/test_automation.py`

## Konwencje

- Zakaz opisowej prozy obejmuje testy, wszystkie pomocnicze moduły Python w ich
  katalogach oraz `conftest.py`. Hook odrzuca także samodzielne stringi pod stałymi;
  dopuszcza dyrektywy `# noqa`, `# type:` i `# pragma`. Opis scenariusza należy do nazwy testu.
- Testy `network` domyślnie SKIPowane; uruchamiają się tylko z `-m network` (logika w `pytest_collection_modifyitems`, nie w addopts). `conftest.py`
- Testy zależne od datasetu spoza repo gate'ują się przez `skipif(not PATH.is_file())` / `pytest.skip()` — brak pliku = zielono, nie czerwono. `services/subtitles/test_regression_classifier.py`
- Test uruchamiający zewnętrzny program (ffmpeg, qBittorrent, mkvtoolnix, 7zip) bramkuje się wyłącznie przez `requires_binaries(Binary...)` z `conftest.py`; bez programu (np. świeży worktree bez `external/`) jest pomijany. Nie pisz własnego `skipif` na `resolve_binary`.
- Dane testowe spoza gita leżą w gitignorowanym `workspace/.quality/` (`anishift.paths.quality_dir()`, jedyne źródło tej ścieżki): korpus `dataset_ass/`, `ground_truth/`, nagrania `elevenreader/`.
- Izolacja stanu przez `monkeypatch.setattr` (config_path/resolve_binary/is_windows/Popen), brak globalnego autouse fixture — każdy test patchuje sam. `config/test_user_settings.py`, `platform/test_binaries.py`
- Testy zależne od systemu wymuszają zachowanie przez `monkeypatch.setattr(..., "is_windows", ...)` zamiast realnego OS. `platform/test_binaries.py`

## Komendy i konfiguracja (`pyproject.toml`)

- Testy biegną równolegle z jawnym `-n` (xdist, `--dist=worksteal` w `pyproject.toml`; nigdy `-n auto`) — muszą być bezstanowe/niezależne od kolejności. `pyproject.toml`
- `--strict-markers` + `--strict-config`: niezadeklarowany marker = błąd; wszystkie markery muszą być w `[tool.pytest.ini_options].markers`. `pyproject.toml`
- Zadeklarowanych 6 markerów: `unit`/`integration`/`e2e`/`network`/`slow`/`smoke`. `integration` obejmuje m.in. recovery w świeżym interpreterze; nie wyłącza testu domyślnie. `pyproject.toml`

## Dane testowe

- `data/youjo-senki-ii-01.json` — surowy output mkvmerge (`DATA_DIR` z `conftest.py`), używany w `test_extraction_service.py` i `test_probe_contract.py`
- `data/mushoku-tensei-s3-03.json` — surowy output mkvmerge, do żadnego testu nie podpięty
