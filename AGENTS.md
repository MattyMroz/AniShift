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

Python 3.14+. Stosuj CAŁY standard ze skilli `python` i `instructions` — w całości, bez wyjątków. Przed pisaniem lub przeglądem kodu przeczytaj pasującą instrukcję. Poniżej tylko rzeczy, których lint NIE wymusza (resztę łapie ruff/mypy — patrz Twarde strażniki).

Reguły bez lintera (agent je łamie, nic ich nie łapie):
- Typuj też zmienne lokalne i atrybuty, nie tylko parametry/zwroty (te wymusza mypy). Puste kolekcje z jawnym typem (`items: list[str] = []`).
- Docstring stałej `Final` pod nią, nie nad (hook sprawdza że JEST, nie czy pod). Stałe grupuj w sekcji `# ── Constants ──`.
- Docstring/komentarz mówi CO kod robi, nigdy historii zmian ani planu. Komentarze WHY, nie WHAT. Guard clauses, early return, max 2 poziomy zagnieżdżeń.

Specyfika AniShift:
- Hierarchia błędów: `AniShiftError` → `{Domain}Error`, plus `TransientError` / `FatalError`; definicje w `anishift/errors.py`. Łap precyzyjnie (`except Exception` blokuje ruff `BLE001`).
- Rejestr silników tylko w domenach z wyborem: `translation` (i docelowo `tts`, `llm`). Reszta to zwykłe moduły.

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

Instalacja: `uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.

- **pre-commit:** ruff `--fix` + ruff-format; `check_test_comments.py` (zero docstringów/komentarzy w testach, dyrektywy `# noqa`/`# type:` OK); `check_const_docstrings.py` (docstring pod każdą stałą `Final`/aliasem).
- **commit-msg:** `check_commit_msg.py` — `typ(scope): opis`, scope obowiązkowy z listy.
- **pre-push:** mypy + pytest (łapią błędy lokalnie zanim pójdą do CI).
- **ruff select** wymusza m.in.: typy param/zwrot (`ANN`), `from __future__` (`FA`), `X | None` zamiast `Optional` (`UP`), docstringi modułów/klas/funkcji (`D`), zakaz `except Exception` (`BLE`).
- **CI:** `.github/workflows/ci.yml` — powtarza wszystkie powyższe na całym repo.
- `testpaths` obejmuje też `anishift/utils/{logger,rich_console,timer}/tests` — samo `pytest tests/` je pomija.

## Dane runtime

- `workspace/` — dozwolone tylko podfoldery `tmp/` i `output/`. Zero `input/`, `cache/`, `logs/`, `settings.json`. Override przez `ANISHIFT_WORKSPACE_ROOT`.
- Preferencje panelu: `config/settings.json` (obok kodu, gitignored, poza workspace).
- Settings API/env: pydantic-settings, prefix `ANISHIFT_`, z `.env`, wszystkie opcjonalne.
- Logger domyślnie nic nie zapisuje — żaden zapis bez jawnego włączenia.
