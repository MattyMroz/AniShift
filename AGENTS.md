# AniShift

Terminalowy lektor anime po polsku: MKV → napisy → tłumaczenie → TTS → merge. Siostra MangaShift.

Zakres i etapy: `docs/plan-anishift.md`.
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
- Commity w formacie Conventional Commits (hook wymusza). Zero śladów AI (`Co-Authored-By`, stopki generatora) — też w treści PR.
- Issue zakładaj wg szablonów z `.github/ISSUE_TEMPLATE/` (bug / feature / task). Tytuł z prefiksem Conventional Commits, jak w szablonie.
- Rób tylko to, o co user prosi. Zero nieproszonych plików, refaktorów, issue.
- Przed większą lub planowaną zmianą potwierdź zakres z userem. Nie ruszaj od razu.
- Nie commituj na `main`. Feature branch → PR → merge.
- KISS/YAGNI — użyj skilla `simple` przy pisaniu i przeglądzie kodu.

## Python

Stosuj CAŁY standard ze skilli `python` i `instructions` — w całości, bez wyjątków. Przed pisaniem lub przeglądem kodu Pythona przeczytaj pasującą instrukcję. Poniżej tylko rzeczy najczęściej łamane oraz specyfika AniShift.

Najłatwiej przeoczyć (patrz skille):
- Typuj WSZYSTKO: parametry, zwroty, atrybuty i zmienne lokalne, w tym `int`. Puste kolekcje z jawnym typem (`items: list[str] = []`).
- `from __future__ import annotations` w linii 1 każdego modułu. Generyki małą literą (`list`, `dict`), `X | None`, nigdy `Optional`.
- Docstring Google-style dla publicznych modułów, klas, funkcji i dla każdej stałej `Final`. Typów w docstringu nie powtarzaj — są w sygnaturze.
- Docstring stałej `Final` pod nią, nie nad. Stałe grupuj w sekcji `# ── Constants ──`.
- Komentarze mówią WHY, nie WHAT. Guard clauses, early return, max 2 poziomy zagnieżdżeń.

Specyfika AniShift:
- Hierarchia błędów: `AniShiftError` → `{Domain}Error`, plus `TransientError` / `FatalError`. Nigdy `except Exception` (ruff `BLE001`) — łap precyzyjnie.
- Rejestr silników tylko w domenach z wyborem: `tts`, `translation`, `llm`. Reszta to zwykłe moduły.
- ruff 0.15.21 psuje `except (A, B):` na `except A, B:`. Rozbijaj na osobne `except`, nie łącz typów.

## Moduły (`anishift/`)

- `cli/` — REPL, komendy `/`, panel `/settings`, banner.
- `pipeline/` — orkiestracja etapów i paski postępu.
- `services/` — domeny (extraction, subtitles, translation, tts, audio, composition); wybór silnika przez rejestr w `engines/`.
- `setup/` — pobieranie i instalacja zewnętrznych binarek (mkvtoolnix, ffmpeg).
- `platform/` — kod zależny od systemu.
- `config/` — ustawienia i `Settings` (pydantic-settings, prefix `ANISHIFT_`, z `.env`, wszystkie opcjonalne).
- `utils/` — logger, rich_console, timer. Przenośne (współdzielone z mm_avh): zero zależności od AniShift. Podlega standardowi `python`.

## Workspace

- `workspace/` — user wrzuca tam MKV, pliki pośrednie powstają obok. Dozwolone tylko podfoldery `tmp/` i `output/`. Zero `input/`, `cache/`, `logs/`, `settings.json`.
- Preferencje panelu: `config/settings.json` (obok kodu, gitignored, poza workspace).
- Logger domyślnie nic nie zapisuje — żaden zapis bez jawnego włączenia.
