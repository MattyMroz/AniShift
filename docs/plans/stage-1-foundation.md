# etap 1 — fundament: pakiet, utils, config, doctor

> status: **ZROBIONE** (zmergowane do main)
> cel: pakiet `anishift` uruchamialny przez `uv run anishift`, z configiem, workspace i doktorem — zanim powstał jakikolwiek pipeline.
> DoD (spełnione): pakiet instaluje się przez uv, doctor działa, workspace tworzy się sam (tylko `tmp/` i `output/`), utils działają, logger niczego nie zapisuje bez jawnego włączenia.

## co powstało

- `pyproject.toml` — pakiet `anishift`, entry point `[project.scripts]`, zależności; `.env.example`; `.gitignore`; `.python-version`; `uv.lock`
- `anishift/__init__.py`, `anishift/errors.py` (bazowa hierarchia wyjątków), `anishift/bootstrap.py` (`bootstrap()` → `AppContext`)
- `anishift/config/` — `settings.py` (pydantic-settings, `.env`, prefix `ANISHIFT_`), `user_settings.py` (load/save `config/settings.json`), `workspace.py` (`resolve_workspace_root()` + subfoldery tmp/output), `__init__.py`
- `anishift/platform/` — `binaries.py` (resolucja `external/bin` per OS, fallback PATH na Linux), `__init__.py`
- `anishift/setup/` — `doctor.py` (checki → `CheckResult`: binarki, klucze, workspace, python), `__init__.py`
- `anishift/cli/` — `main.py` (Typer, subkomenda doctor), `__init__.py`
- `utils/` — przeniesione z MangaShift: `rich_console/`, `logger/` (domyślnie OFF), `timer/`, `device.py`, `safe_fs.py`, `safe_path.py`, `secrets.py`, `timing.py`
- `external/README.md`, `external/bin_hashes.json` (szkielet), `external/bin/` (gitignored, .gitkeep)
- `workspace/` (struktura z .gitkeep), `config/README.md`
- `tests/` — `test_binaries.py`, `test_doctor.py`, `test_user_settings.py`, `test_workspace.py`
- CI: `.github/workflows/ci.yml`, szablony issue, `.pre-commit-config.yaml`, `.coderabbit.yaml`, `CLAUDE.md`, `README.md`

## uwaga dla następnych etapów

W `utils/` NIE MA jeszcze 4 plików z mm_avh (`cool_animation.py`, `execution_timer.py`, `number_in_words.py`, `text_chunker.py`) — dokopiować 1:1 (bez zmian) w etapie, który pierwszy ich potrzebuje: `cool_animation.py` w etapie 2 (banner), `number_in_words.py` + `text_chunker.py` w etapie 6 (tts).
