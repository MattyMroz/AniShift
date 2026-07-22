# AniShift

Terminalowy lektor anime po polsku: MKV → napisy → tłumaczenie → TTS → merge. Siostra MangaShift.

Zakres i etapy: `docs/plans/plan-anishift.md`.
Wzorzec do recyklingu struktury i nazewnictwa: `../MangaShift/mangashift/` — bierz dobre, słabe rób lepiej.

## Bramki jakości (przed każdym commitem)

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Zawsze na `anishift/ tests/`, nigdy na podkatalogu — na podkatalogu ruff sypie setkami fałszywych błędów.

## Twarde reguły

- Kod, komentarze, nazwy, commity, issue i PR po angielsku. Rozmowa z userem po polsku.
- Zależności tylko przez `uv add` / `uv remove`. Nigdy nie edytuj `pyproject.toml` ręcznie.
- Commity w formacie `typ(scope): opis` — scope OBOWIĄZKOWY, z listy w `scripts/hooks/check_commit_msg.py` (hook odrzuca commit bez scope lub ze scope spoza listy). Zero śladów AI (`Co-Authored-By`, stopki generatora) — też w treści PR.
- Issue zakładaj wg szablonów z `.github/ISSUE_TEMPLATE/` (bug / feature / task). Tytuł z prefiksem Conventional Commits, jak w szablonie.
- Rób tylko to, o co user prosi. Zero nieproszonych plików, refaktorów, issue.
- Przed większą lub planowaną zmianą potwierdź zakres z userem. Nie ruszaj od razu.
- Nie commituj na `main`. Feature branch → PR → merge.
- KISS/YAGNI — użyj skilla `simple` przy pisaniu i przeglądzie kodu.

## Python

Python 3.14+. Stosuj CAŁY standard ze skilli `python` i `instructions` — w całości, bez wyjątków. Przed pisaniem lub przeglądem kodu przeczytaj pasującą instrukcję. Poniżej tylko rzeczy najczęściej łamane oraz specyfika AniShift.

Najłatwiej przeoczyć (patrz skille):
- Typuj WSZYSTKO: parametry, zwroty, atrybuty i zmienne lokalne, w tym `int`. Puste kolekcje z jawnym typem (`items: list[str] = []`).
- `from __future__ import annotations` w linii 1 każdego modułu. Generyki małą literą (`list`, `dict`), `X | None`, nigdy `Optional`.
- Docstring Google-style dla publicznych modułów, klas, funkcji i dla każdej stałej `Final`. Typów w docstringu nie powtarzaj — są w sygnaturze.
- Docstring stałej `Final` pod nią, nie nad. Stałe grupuj w sekcji `# ── Constants ──`.
- Komentarze mówią WHY, nie WHAT. Guard clauses, early return, max 2 poziomy zagnieżdżeń.

Specyfika AniShift:
- Hierarchia błędów: `AniShiftError` → `{Domain}Error`, plus `TransientError` / `FatalError`. Nigdy `except Exception` (ruff `BLE001`) — łap precyzyjnie. Definicje w `anishift/errors.py`.
- Rejestr silników tylko w domenach z wyborem: `translation` (i docelowo `tts`, `llm`). Reszta to zwykłe moduły.
- Każda stała `Final` i type alias na poziomie modułu ma docstring pod spodem (hook `check_const_docstrings.py` wymusza).

## Mapa katalogów

Każdy obszar poniżej ma własny AGENTS.md z pułapkami i konwencjami — wczytaj go, gdy tam wejdziesz.

- `anishift/` — pakiet aplikacji (composition root, hierarchia błędów); ma własny AGENTS.md
- `tests/` — testy pytest; konwencje i markery w jego AGENTS.md
- `docs/plans/` — plany etapów (`plan-anishift.md` = zakres); `docs/reference/` — audyt mm_avh + wzorzec mangashift
- `external/` — pobrane binarki (gitignored) + docs HTML narzędzi; szczegóły w `external/README.md`
- `config/` — runtime katalog na `settings.json` panelu (gitignored); opis w `config/README.md`
- `scripts/hooks/` — hook `check_commit_msg.py` (Conventional Commits); `scripts/tmp/` — jednorazowe
- `workspace/` — user wrzuca MKV, pliki pośrednie powstają obok (patrz Dane runtime)

## Twarde strażniki

- Pre-commit: ruff `--fix` + ruff-format (blokują commit); commit-msg: `scripts/hooks/check_commit_msg.py` (Conventional Commits). Instalacja: `uv run pre-commit install --hook-type pre-commit --hook-type commit-msg`.
- CI: `.github/workflows/ci.yml`.
- `testpaths` obejmuje też `anishift/utils/{logger,rich_console,timer}/tests` — samo `pytest tests/` je pomija.

## Dane runtime

- `workspace/` — dozwolone tylko podfoldery `tmp/` i `output/`. Zero `input/`, `cache/`, `logs/`, `settings.json`. Override przez `ANISHIFT_WORKSPACE_ROOT`.
- Preferencje panelu: `config/settings.json` (obok kodu, gitignored, poza workspace).
- Settings API/env: pydantic-settings, prefix `ANISHIFT_`, z `.env`, wszystkie opcjonalne.
- Logger domyślnie nic nie zapisuje — żaden zapis bez jawnego włączenia.
