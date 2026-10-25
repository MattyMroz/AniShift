# 17 — kontrola zawartości po pobraniu (E4)

Status: **F1 i F2 zrobione (PR #74)**: reguła roli ścieżki i odrzucanie wydania bez napisów dialogowych w subskrypcji. F3 (zamiana przy pobraniu ręcznym) odłożona; decyzje D1–D8 przyjęte według rekomendacji, D6 bez migracji w produkcie.

Po pobraniu odcinka AniShift sprawdza napisy w pliku: polskie dialogi → bez tłumaczenia, tylko obce → tłumaczenie, brak napisów dialogowych → jedno inne wydanie (subskrypcja: w budżecie 3 prób), lektor zawsze. Źródło pozycji: `docs/ideas.md` §2 „Kontrola zawartości po pobraniu”, etap E4 w `docs/work/08-acquisition/masterplan.md`.

## Pliki

| Plik | Treść |
|---|---|
| [current-state.md](current-state.md) | co działa dziś (kontrola H2, planner, `translation_action: auto`, zamiana wydania) i dane `ffprobe` z 52 MKV |
| [specification.md](specification.md) | wymagania, inwarianty, zakres i decyzje właściciela D1–D8 z rekomendacjami |
| [plan.md](plan.md) | fazy F0–F4, pliki, testy z markerami, bramki, branch i commity |
| [reviews/round-1.md](reviews/round-1.md) | sceptyczne review autora z poprawkami |

## Najważniejsze ustalenia

- Rozpoznanie szyldów: tempo zdarzeń rozdziela 758 pełnych ścieżek (≥ 7,98/min) od 32 szyldów (≤ 1,52/min) bez pomyłki; flaga `forced` myli się raz, tytuł pomija 2 szyldy.
- PL → bez tłumaczenia i obce → tłumaczenie już działają w plannerze; brakuje wspólnej, trafniejszej reguły szyldów i reakcji na brak napisów.
- Zamiana dla subskrypcji to istniejąca kolejna próba; dla pobrania ręcznego trzeba podpiąć gotowe `replacement()`.

## Kolejny krok

Przegląd krzyżowy innym modelem → decyzje D1–D8 → F0 (porównanie pola `mkvmerge -J` z pomiarem `ffprobe`).
