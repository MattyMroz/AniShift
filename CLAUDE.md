# AniShift — instrukcje projektu

Terminalowy lektor anime po polsku (MKV → napisy → tłumaczenie → TTS → merge). Siostra MangaShift.

## Zasada nadrzędna

**Recykling MangaShift w 100%** — struktura, nazewnictwo, wzorce (`services/<domena>/engines/` z rejestrem, bootstrap, doctor, errors hierarchy, `external/` + `workspace/`). MangaShift to ściąga referencyjna (`../MangaShift/mangashift/`), nie biblia — dobre kawałki bierz, słabe rób lepiej. Druga zasada: **wszystko ma być proste** (KISS/YAGNI, skill `simple`).

Źródło prawdy o zakresie i etapach: `docs/plan-anishift.md`.

## Twarde reguły

- **Kod i komentarze po angielsku.** Rozmowa z userem po polsku.
- **Zależności tylko przez `uv add` / `uv remove`** — nigdy ręczna edycja `pyproject.toml`. AniShift nie ma profili CUDA/Torch — gołe `uv add` dla lekkiego core.
- **Commity: Conventional Commits** (hook wymusza), **bez śladów AI** — zero `Co-Authored-By`, zero stopek generatora. Dotyczy też PR body.
- **Robię tylko to, o co user prosi** — zero inicjatywy, zero nieproszonych plików/refaktorów.

## Standardy Pythona

Pełny standard: skille `python` i `instructions` (w `.claude/skills/`). W skrócie:

- Python ≥3.14, `from __future__ import annotations`, lowercase generics, `X | None`.
- **Docstringi Google-style** dla publicznych modułów/klas/funkcji **i dla każdej stałej `Final`** (`"""..."""` pod stałą).
- Stałe `Final` grupuj w sekcji (`# ── Constants ──`), nie wplataj między klasy/funkcje.
- Guard clauses, early return, max 2 poziomy zagnieżdżeń.
- `dataclass(slots=True[, frozen=True])` dla value objects; `Literal` dla zamkniętych zbiorów.
- Hierarchia błędów: `AniShiftError` → `{Domain}Error`; `TransientError`/`FatalError`. Nie blind `except Exception` (ruff `BLE001`) — łap precyzyjnie.
- Rejestr silników tylko w domenach z wyborem: `tts`, `translation`, `llm`. Reszta (extraction, subtitles, audio, composition) = zwykłe moduły.

## Jakość — bramki przed commitem

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

- ruff select: Tier 1/2 + `D` (pydocstyle google) — patrz `pyproject.toml`.
- **Uwaga: ruff 0.15.21 format ma bug** — psuje `except (A, B):` na niepoprawne `except A, B:`. Nie łącz wielu typów w jednym `except` — rozbij na osobne `except`.
- CI (GitHub Actions) i pre-commit pilnują tego samego. CodeRabbit review na PR (skill `/coderabbit` do przeglądu uwag).

## Workspace i config

- `workspace/` — user wrzuca tam MKV; pliki pośrednie powstają obok. Tylko podfoldery `tmp/` i `output/`. Zero `input/`/`cache/`/`logs/`/`settings.json` w workspace.
- Preferencje panelu: `config/settings.json` (obok kodu, gitignored, poza workspace).
- Klucze API: `.env` + `Settings` (pydantic-settings, prefix `ANISHIFT_`). Wszystkie opcjonalne.
- Logger (`utils/`) domyślnie OFF — nic nie zapisuje bez jawnego włączenia.
- `utils/` jest **nietykalne** (1:1 z mm_avh) — nowe rzeczy tylko jako nowe pliki obok.

## Git flow

Feature branch → PR do `main` → CodeRabbit review → merge. Nie commituj na `main` bezpośrednio.
