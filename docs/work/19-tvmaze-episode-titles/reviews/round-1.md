---
kind: review
status: pass-with-findings
reviewed-state: docs/work/19-tvmaze-episode-titles/{research,specification,plan}.md @ main 4365a51
date: 2026-10-25
---

# Review: research, specyfikacja i plan tytułów odcinków z TVmaze

## Zakres

- przedmiot: trzy artefakty w tym katalogu.
- baseline: `main` @ `4365a51`, `config/watch/state.json` z 2026-10-25.
- authority: issue #58, `AGENTS.md` (root, `anishift/`, `services/catalog/`), skille `research`, `planning`, `review`.
- ryzyka: błędne twierdzenia o kodzie, zgadywanie, sprzeczność z regułami repo, plan niewykonalny bez decyzji.
- poza review: kod (nie istnieje), niezależność recenzenta.

**Ograniczenie niezależności:** review wykonał ten sam agent, który napisał artefakty (zakaz tworzenia subagentów w zleceniu). Zgodnie z regułą krzyżową `AGENTS.md` trzeba jeszcze przeglądu świeżą instancją innego modelu, najlepiej Sonnet (zasada oszczędności) lub model innej rodziny.

## Werdykt

**Status:** pass-with-findings

**Najważniejszy powód:** twierdzenia o kodzie i o TVmaze sprawdzono ponownie w plikach i w żywych zapytaniach; zostały drobne luki w dokładności, żadnej blokującej.

## Findings

### Krytyczne

Brak.

### Poważne

Brak.

### Mniejsze

#### M1. Twierdzenie o AniList było zbyt mocne (naprawione)

- miejsce: `research.md`, tabela "AniList".
- dowód: `grep streamingEpisodes anishift/` bez trafień; to znaczy, że kod nie czyta tytułów odcinków z AniList, a nie że AniList ich nie ma.
- reakcja: zawężono sformułowanie do "kod nie czyta".

#### M2. Cache kluczowany `anilist_id`, a serial TVmaze bywa wspólny dla sezonów

- miejsce: `plan.md`, "Source of truth" (`_Remembered.titles`).
- dowód: Apothecary Diaries S1-S3 mają ten sam `tvdbShowId` 431162, więc kolejne wpisy franczyzy pobiorą te same dane drugi raz.
- wpływ: kilka dodatkowych żądań na godzinę przy przeglądaniu franczyzy, bez wpływu na poprawność.
- reakcja: akceptowalne (reuse istniejącego LRU i blokady); osobny słownik po `tvdb_show_id` jest opcją, jeśli wykonawca uzna to za prostsze.

#### M3. Test `network` zależy od zmiennej treści

- miejsce: `plan.md`, strategia dowodu ("jakiś odcinek 1 ma niepusty tytuł").
- wpływ: test na żywym TVmaze może się kiedyś zepsuć przy zmianie danych; jest pomijany domyślnie, więc nie blokuje bramek.
- reakcja: asercja tylko na kształt (klucz `(1, 1)` i niepusty `str` dla serialu 93848), co plan sugeruje.

### Sugestie

- S1. Pomiar zysku powtórzyć po tygodniu (te same 20 subskrypcji), zanim zapadnie D1; skrypt z `research.md` jest powtarzalny.
- S2. Wykonawca powinien policzyć, czy `episodes()` jest wołane w pętli UI przy każdym odświeżeniu widoku; plan zakłada, że cache pamięci wystarcza (anime.py:517, 1681).

## Zgodność z kontraktem

| Wymaganie | Stan | Dowód |
| --- | --- | --- |
| Zlecenie: stan dziś ze ścieżkami i liniami | pass | tabela w `research.md`; linie sprawdzone odczytem plików |
| Research TVmaze: endpointy, numeracja, limity, licencja, jakość | pass | dokumentacja (WebFetch) + zapytania curl/httpx 2026-10-25 |
| Próbki dla 2-3 tytułów z subskrypcji | pass | Magical Explorer, Magic Repo Man (= Kashita Maryoku), Overgeared, Student Council |
| Projekt bez nadpisywania, z niepewnością, cache i odświeżaniem | pass | wymagania 1-9 specyfikacji, reuse `numbering_gap` |
| Zgodność z kierunkiem "TVmaze jako jedno ze źródeł" | pass | sekcja zgodności w specyfikacji; adapter obok `anizip/arm/kitsu` |
| Artefakty po polsku w `docs/work/19-...`, tylko tam zapis | pass | pięć plików; `git status` poza katalogiem bez zmian |
| Zakazy: bez kodu, configów, git poza `gh issue view`, bez subagentów | pass | brak zmian w repo poza katalogiem; stan `state.json` tylko odczyt; dane tymczasowe w scratchpadzie sesji |
| Reguły repo: commity `typ(scope)`, markery, testy bez prozy, `uv`, brak AI w commitach | pass | plan, fazy 1-3; scope `services/application/repo` są w `SCOPES` |

## Regresje i integracja

- Zweryfikowano, że `read_listing` (automat) nie zostaje dotknięty, a `merge_listing` zapisuje `read.mapping`, więc wypełnienie na wyjściu `episodes()` nie trafi do `state.json`.
- Wykryto ryzyko testowe: testy z `MockTransport` dopuszczające ograniczony zbiór hostów (`test_automation.py:444`) mogą wymagać poprawki; dodano do mapy plików.

## Wykonane kontrole

```text
gh issue view 58 --json ...            -> treść zgodna ze zleceniem (zwykły widok gh nic nie wypisał)
grep/odczyt plików cytowanych w research.md (anizip, episode_selection, acquisition,
  anime_rows, subscription_targets, http_requests, bootstrap, arm, AGENTS.md) -> twierdzenia zgodne
żywe zapytania TVmaze/ani.zip (lookup, episodes, search) i skrypt zbiorczy na 20 subskrypcjach
  -> 20/20 lookup, 6 wypełnień, 62 placeholdery, 25 braków, 0 przesunięć numeracji
```

## Niewykonane lub nierozstrzygające kontrole

- Niezależny przegląd innym modelem (patrz ograniczenie).
- Zachowanie 429 TVmaze (nie prowokowano), placeholdery inne niż `Episode N`, skuteczność wyszukiwania po tytule.
- Implementacja i testy: nie istnieją; plan nieuruchamiany.

## Wymagana ocena człowieka

```text
Uruchom: przeczytaj specification.md, sekcja "Decyzje otwarte"
Zrób: rozstrzygnij D1 (czy warto przy zysku 6 z 93) oraz D3 i D5
Oczekiwany wynik: plan może ruszyć albo issue zostaje odłożone
Zwróć uwagę na: D1, bo zysk dziś wynika z okna opóźnienia ani.zip
```

## Zalecany następny krok

Decyzje D1-D7 właściciela, potem krótki przegląd Sonnetem lub modelem innej rodziny, potem wykonanie planu na gałęzi `work/services/01-tvmaze-episode-titles`.
