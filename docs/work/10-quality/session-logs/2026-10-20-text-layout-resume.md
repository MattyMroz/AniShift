# 2026-10-21 — układ tekstu v4: punkt wznowienia

## Stan

- Gałąź `work/quality/08-fuzzy-quality` w głównym checkoucie, ostatni commit kodu `6daa9f95`. Nic na `main`, bez push. Worktree usunięte (zmiany bez commita w `git stash`). Specyfikacja: `docs/work/10-quality/text-layout.md`; kalibracja: `research/text-layout-calibration.md`.
- Bramki zielone: ruff, mypy, pełny pytest 9855 testów (niestabilne pod obciążeniem, osobno przechodzą: `tests/platform/test_child_processes.py`, `tests/integration/test_episode_download.py`).
- Galeria stała: 60 przypadków (30 dialogów, 30 napisów pobocznych), stan wejściowy obok kodu, folder podpisany commitem: `workspace/.quality/experiments/gallery/60-6daa9f95/`. Lista przypadków: `experiments/v4-hard/cases.json` (galeria wymaga pola `description`, które składa się z `id` i `difficulty`). Render tylko trudnych przypadków: `compare --size 0`.
- Ocena Sonnet (dwóch sędziów, poprzedni commit `196696cd`): dialogi 28/30, poboczne 26/30, nic gorszego niż wejście poza jednym przypadkiem 55, który był złudzeniem powiększenia (ten sam rozmiar liter).

## Reguły ustalone 20–21.10

- Officina na wszystkich napisach (dialogi i poboczne; rysunki i karaoke bez zmian); klon stylu pogrubiony, gdy czcionka ma tylko krój Bold.
- Szyld nie mniejszy niż 0,8, chyba że nic innego się nie mieści (poziom ratunku); piosenka może zejść niżej i zostaje w jednej linii; komplet szyldów ujednolica skalę najwyżej do 0,8.
- Krótki zaimek (mi, ci, go…) nie zaczyna linii. Łamania tłumacza obowiązują, gdy liczba linii zgadza się ze źródłem, poza chronionymi związkami i piosenkami.
- Twarde tylko: poza ekranem (bez marginesu pomiaru; w ramkach `\clip` z marginesem), za dużo linii, zmniejszenie poniżej 0,8, mieszanie krojów w linii. Reszta dawnych blokad to wagi.
- Nieruchomy prostokąt ASS pod szyldem rośnie do dłuższego przekładu (marginesy źródła), gdy tekst wychodzi poza połowę marginesu (właściciel 21.10).
- Katalog mierzy szyldy tą samą funkcją co program (`fitting.sign_input`, czcionka właściciela); kalibracja sprawdza odporność ±1% i zmiękcza sprzeczne przypadki zamiast odmawiać.

## Otwarte

1. 32: „Chika” wjeżdża animowaną maską, klatka łapie ją w połowie (nie błąd układu). 53: „Odcinek drugi” — cięcie 20/51 zamiast 41/31. 30: dialog leży na rankingu (jak w oryginale).
2. 29 (d28, 53 znaki, szerokość 0,77) i 38 (trzy linie wobec dwóch po ~61): decyzja na progu szerokości, do potwierdzenia przez właściciela.
3. Foldery `workspace/temp/pytest-*` mają zablokowane uprawnienia — do usunięcia ręcznie.

## Następny krok

Sprawdzian na zbiorze kontrolnym `workspace/.quality/holdout/` (8 nowych odcinków, m.in. isekaje z okienkami statusu), akceptacja właściciela na galerii `60-6daa9f95`, potem push i scalenie `08` → `main`. Nigdy `uv run --active`.
