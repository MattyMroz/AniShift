# 20 — granice stylów po tłumaczeniu

Issue: [#34](https://github.com/MattyMroz/AniShift/issues/34). Pozycja „Granice stylów po tłumaczeniu” z `docs/ideas.md` §1.2, etap 3 masterplanu [10-quality](../10-quality/masterplan.md).

**Status:** specyfikacja i plan czekają na przegląd innej rodziny modeli i akceptację właściciela. Kodu jeszcze nie ma.

## W skrócie

- **Działa:** zakres w środku wersu idzie do LLM jako `<sN>` i trafia na właściwe polskie słowa także po zmianie szyku (7/7 w gotowych plikach, LLM zwraca znaczniki w 56/56 linii). Tagi nie rozcinają słów.
- **Nie działa:**
  - styl mówcy w osobnym wersie przechodzi na drugiego mówcę (dokładnie #34);
  - zakres otwarty na początku linii ląduje na zgadniętym słowie;
  - zamknięcie stylu tuż przed `\N` rozciąga zakres do końca linii.
- **Projekt:** granicą znacznika staje się też styk wersów ze zmianą stylu oraz zakres od początku linii. Tagi tych granic stają na znacznikach, a z bloku początku linii przechodzi tylko kursywa albo pogrubienie. Znaczniki są czytane na tym samym stylu, na którym powstały. Ścieżka bez znaczników zostaje bez zmian.

## Pliki

- [evidence.md](evidence.md): przepływ znaczników z liniami, realne przypadki z danych, spis przyczyn, prototyp reguł.
- [specification.md](specification.md): wymagania W1–W8, inwarianty, zakazy, katalog przypadków K1–K28, decyzje D1–D5 z rekomendacjami.
- [plan.md](plan.md): pliki, testy, fazy, bramki, branch `work/subtitles/04-style-boundaries` i commity.
- [reviews/round-1.md](reviews/round-1.md): kontrola autorska z findings.

## Decyzje właściciela

D1 (szyldy tą samą regułą), D2 (kolory od początku linii — nie teraz), D3 (wyróżnienie bez odpowiednika — jak dziś), D4 (zakres na cały przekład — jak dziś), D5 (zmiana oczekiwań pięciu testów). Szczegóły i rekomendacje: [specification.md](specification.md#nierozstrzygnięte-do-decyzji-właściciela).
