# 16-proper-names: nazwy własne i prompty tłumaczenia

Pozycja `teraz` z [`docs/ideas.md`](../../ideas.md) §1.1: poprawne nazwy własne (imiona, nazwiska, miejsca, tytuły, zwroty grzecznościowe) w tłumaczeniu LLM i dopracowane prompty.

**Status (2026-10-25):** research i plan gotowe; czekają na decyzje właściciela D1–D8 i na review krzyżowe innym modelem. Kodu nie zmieniano.

## Pliki

| Plik | Co zawiera |
|---|---|
| [intent.md](intent.md) | problem, kierunek, odrzucone drogi, stan uzgodnienia |
| [evidence.md](evidence.md) | stan kodu dziś (prompt, style, chunking, kontekst, AniList) i 17 przykładów błędów z `workspace/ready/` z plikiem i linią |
| [research.md](research.md) | AniList GraphQL (postacie, limity, regulamin), glosariusze w branży i w badaniach nad LLM, polskie normy odmiany, wołacza i praktyka sufiksów; źródła z datami |
| [specification.md](specification.md) | wymagania glosariusza, wstrzyknięcia, reguł promptu i pomiaru; warunki sukcesu; **decyzje właściciela D1–D8 z rekomendacjami** |
| [plan.md](plan.md) | fazy 0–6, mapa plików, testy z markerami, bramki, gałąź `work/translation/01-series-glossary`, commity |
| [reviews/round-1.md](reviews/round-1.md), [reviews/round-2.md](reviews/round-2.md) | dwie rundy sceptycznego review (autor planu, nie review krzyżowe) z poprawkami |

## W skrócie

- Problem: zła pisownia rzadkich imion, różne formy tej samej nazwy w kolejnych odcinkach, brak reguły zwrotów grzecznościowych i wołacza, odmiana bez znajomości płci.
- Kierunek: jeden glosariusz na serię z postaci AniList w `config/glossaries/<id>.json`, poprawiany ręcznie przez właściciela; do promptu trafiają tylko wpisy obecne w tłumaczonym tekście; krótka sekcja reguł nazw własnych w `translation.md`.
- Pomiar: ten sam zestaw 15 odcinków, ten sam model i styl, przebiegi przed i po; skrypt mierzy trafność i spójność nazw oraz zgodność z regułami, a 17 przypadków ocenia właściciel.

## Następny krok

Właściciel wybiera D1–D8 w [specification.md](specification.md). Potem review planu przez świeżą instancję innego modelu i faza 0. Wpis w [`docs/README.md`](../../README.md) i zmiana statusu w `ideas.md` należą do fazy 6 planu.
