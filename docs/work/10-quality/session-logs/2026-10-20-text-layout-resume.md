# 2026-10-20 — układ tekstu v4: punkt wznowienia

## Stan

- Gałąź `work/quality/21-text-layout` (worktree `AniShift-wt/q-tl`) scalona do `work/quality/08-fuzzy-quality`. Nic na `main`, bez push. Specyfikacja: `docs/work/10-quality/text-layout.md`; plan: `plans/02-text-layout.md`; kalibracja: `research/text-layout-calibration.md`.
- Gotowe: rdzeń `anishift/services/subtitles/layout.py`, klasy przerw `anishift/text/gaps.py` (+ Morfeusz 2, `anishift/text/morphology.py`), kalibracja `scripts/subtitle_quality/layout_calibrate.py`, dialog i napisy poboczne podpięte (warstwa sceny w `fitting.py`), usunięte ustawienia „Znaków w linii” i „Linii na napis”. Katalog + ankiety 87/87; test produkcyjny `tests/services/subtitles/test_text_layout_production.py` (wymaga junction `workspace\.quality` → główny checkout; nie commitować).
- Ślepe oceny (dwóch sędziów): odłożone NF+AMZN — rdzeń 1,2–2,5% złych cięć, zawodowcy 1,9–2,5%; świeże CR (501) przed poprawką klityk — rdzeń 3,4–5,8%, zawodowcy CR 10,8–11,6%.
- Replay `workspace/.quality/experiments/replay/v4`: szyldy poza ekranem bardziej niż oryginał 819 → 93, kolizje 2097 → 496. Galerie: `experiments/gallery/hard-baseline-vs-v4` (60 trudnych scen z programu), `baseline-vs-v4`.
- Zbiór holdout (8 nieużywanych odcinków z `ready`): `workspace/.quality/holdout/` — zbudowany, jeszcze nie oceniony.

## Otwarte

1. s13 (podpis z pustymi wierszami, obraz 50 galerii trudnej): WIP w `git stash` na gałęzi 21 („s13 blank-line spacing WIP”); replay padał na `MemoryError` — wybór granic bloków trzeba zrobić programowaniem dynamicznym po blokach albo brać granice z układu tłumacza.
2. Strojenie pod przypadki: progi 0,6 skali, 16 px, 50% sieroty szyldu bez danych; LOO 74/87. Proponowany audyt reguł szyldów i ślepa ocena szyldów na holdout (oceny na Sonnecie).
3. Tekst wypalony w obrazie (s13, s29) — niewidoczny dla programu.
4. Pomysły właściciela do decyzji: Officina dla szyldów bez pracy typesettera („kolorowy Arial”), ustawienie „Wielkość dialogów” jako % wysokości ekranu.

## Następny krok

Akceptacja właściciela na obrazach (`hard-baseline-vs-v4`), potem scalenie `08` → `main`. Nigdy `uv run --active`; po pracy agentów sprawdzić `AniShift\.venv\Lib\site-packages\anishift.pth`.
