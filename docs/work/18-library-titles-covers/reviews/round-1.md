---
kind: review
status: pass-with-findings
reviewed-state: docs/work/18-library-titles-covers/ (current-state, research-covers, specification, plan) na main @ 4365a51
date: 2026-10-25
---

# Review rundy 1: planowanie Biblioteki tytułów i okładek

## Zakres

- przedmiot: cztery artefakty planistyczne tego katalogu.
- baseline: `main` @ `4365a51`.
- authority: zlecenie planisty, `AGENTS.md` (reguły twarde), skille `specification`, `planning`, `review`.
- ryzyka: niezgodność z kodem, zgadywanie, złamanie reguły stałego wyglądu, pominięty wpływ na kontrakty.
- poza review: implementacja (nie istnieje).

**Ograniczenie niezależności:** review wykonał autor artefaktów (planista), bo zlecenie zabrania tworzenia subagentów. Zasada krzyżowa
repo wymaga świeżej instancji innego modelu, więc ta runda jest samokontrolą, nie zastępuje przeglądu niezależnego (patrz „Zalecany następny krok”).

## Werdykt

**Status:** pass-with-findings (w zakresie samokontroli).

**Najważniejszy powód:** twierdzenia o kodzie mają ścieżki i linie sprawdzone odczytem; największe luki to rzeczy niemożliwe do
zmierzenia w tym zleceniu (runtime, rozmiary okładek, zachowanie Windows Terminal), jawnie przeniesione do fazy 0 i checkpointów.

## Findings

### Krytyczne

Brak.

### Poważne

#### P-1. Zależność wyniku od niezweryfikowanych źródeł o terminalu i AniList

- miejsce: `research-covers.md`, sekcje 1 i 3.
- dowód: strony AniList (`rate-limiting`, `terms-of-use`, `considerations`) zwróciły 403 przy bezpośrednim pobraniu; treść pochodzi z
  streszczenia wyszukiwarki. Status Kitty w Windows Terminal (eksperymenty, 08.2026) pochodzi z odczytu strony zgłoszenia przez narzędzie
  streszczające, bez drugiego źródła. Wsparcie iTerm2 OSC 1337 w Windows Terminal: brak jakiegokolwiek źródła.
- wpływ: rekomendacja wariantu A opiera się głównie na dowodzie z repo (maskotka SIXEL), który jest mocny, ale nie obserwowany.
  Błąd w źródłach o limitach nie zmienia wyboru, zmienia tempo pobierania.
- minimalna reakcja: oznaczone w dokumencie jako W/N; faza 0 mierzy limity i rozmiary; przed implementacją odświeżyć status Kitty w #8389.

#### P-2. „Jak dziś” dla Ctrl+Z jest sprzeczne z wieloma usunięciami

- miejsce: `specification.md` U-5 i O-6; `current-state.md` sekcja 2.
- dowód: `_latest_deletion` (`automation.py:2344`) nie pomija przywróconych wpisów; gałąź `restore_already_completed` (`:2362`). Odczyt, nie runtime.
- wpływ: bez decyzji O-6 użytkownik, który usunął kilka odcinków, cofnie tylko ostatni.
- minimalna reakcja: zapisane jako decyzja O-6, test w fazie 0 potwierdza zachowanie przed zmianą.

### Mniejsze

#### M-1. Brak szablonu briefu wskazanego w `AGENTS.md`

- miejsce: `plan.md`, „Dodatkowi wykonawcy”.
- dowód: `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md` nie istnieje w tym checkout (katalog `.agents/skills/subagent/` ma tylko `SKILL.md`; `.agents/` jest w `.gitignore`).
- wpływ: orkiestrator nie ma wzorca, o którym mówi `AGENTS.md`.
- minimalna reakcja: poza zakresem tej pracy; zgłoszone właścicielowi.

#### M-2. Niezweryfikowane symbole

- miejsce: `plan.md`, tabela Reuse.
- dowód: nie czytałem `normalize_series` (`acquisition.py:590`) ani symbolu serwisu odcinków dla fazy 4; plan to jawnie zaznacza.
- wpływ: faza 1 i 4 mogą wymagać lokalnej adaptacji.
- minimalna reakcja: pierwszy krok wykonawcy: przeczytać oba symbole; jeśli semantyka nie pasuje, eskalacja.

#### M-3. Opis E6 zakłada zaznaczanie, którego Biblioteka nie ma

- miejsce: `current-state.md`, sekcja 2; `masterplan.md` E6.
- wpływ: zakres faz 2–3 jest większy, niż sugeruje „zaznaczanie zostaje”; plan traktuje zaznaczanie jako nową funkcję.
- minimalna reakcja: uwzględnione w planie; zgłoszone właścicielowi.

#### M-4. Uogólnienie slotu obrazu może dotknąć maskotki

- miejsce: `plan.md`, faza 8.
- dowód: renderer ma jeden zestaw pól `_native_*` (`prompts.py:253-257`); `_native_anchor` i kasowanie są wspólne.
- wpływ: ryzyko regresji Home/Auto.
- minimalna reakcja: test `test_mascot_frames_unchanged` i obowiązkowe istniejące testy interaktywne; przeplanowanie, jeśli potrzebny drugi slot.

### Sugestie

- S-1. Rozważyć, czy część II ma sens bez części I, jeśli O-2 padnie na „nie”: Subskrypcje mają ten sam problem 30 tytułów, a okładki w nich nie zależą od widoku tytułów. Plan zachowuje kolejność I → II, bo slot ma być dostrojony do listy tytułów.
- S-2. Faza 5 (rozpoznawanie) mogłaby być osobnym planem po H2; tu zostawiona jako warunkowa, żeby O-5 nie ginęło.

## Zgodność z kontraktem

| Wymaganie zlecenia | Stan | Dowód |
|---|---|---|
| Wygląd panelu zostaje | pass (z jawnym konfliktem O-2) | `specification.md` U-1, O-2; `research-covers.md` sekcja 5 |
| Stan dziś ze ścieżkami i liniami | pass | `current-state.md`, linie zweryfikowane `grep -n` |
| Okładki: badanie z źródłami | pass-with-findings | P-1 |
| Projekt (b): model, nawigacja, usuwanie, Kosz, Ctrl+Z, płaski dysk | pass | `plan.md` Target design |
| Artefakty po polsku w wskazanym katalogu | pass | zapis tylko w `docs/work/18-library-titles-covers/` |
| Brak zmian kodu, gitu, uruchomień panelu | pass | niewykonywane |
| Brak subagentów | pass | |

## Wykonane kontrole

```text
grep -n symboli i linii cytowanych w current-state.md i plan.md na main @ 4365a51  -> poprawiono 11 przesuniętych odwołań
skrypt: wszystkie ścieżki w backtickach istnieją albo są jawnie plikami NEW  -> jedyny brak realny: SUBAGENT-BRIEF.template.md (M-1)
odczyt: anishift/application/library.py, automation.py (fragmenty), state.py, state_library.py, prompts.py, mascot_native.py, anilist.py, anime_view.py
```

## Niewykonane lub nierozstrzygające kontrole

- Uruchomienie panelu, rezydenta, pytest, ruff, mypy (zakaz zlecenia). Baseline testów nieznany.
- Pomiary okładek i czasu kodowania SIXEL (faza 0).
- Weryfikacja AniList i Windows Terminal z drugiego źródła (P-1).

## Wymagana ocena człowieka

```text
Uruchom: nic; to decyzje dokumentowe
Zrób: odpowiedz na O-1…O-11 w specification.md, w szczególności O-1, O-2, O-6
Oczekiwany wynik: akceptacja lub korekta rekomendacji
Zwróć uwagę na: konflikt O-2 (nowy element układu a reguła wyglądu)
```

## Ograniczenia review

Samokontrola autora, bez niezależnej instancji; brak runtime.

## Zalecany następny krok

1. Właściciel rozstrzyga O-1…O-11.
2. Niezależny przegląd planu świeżą instancją innego modelu niż autor planu (preferencja właściciela: Sonnet do ocen), zakres: `plan.md` i `specification.md`, zgodnie z skillem `review` §6.
3. Dopiero potem brief dla autora części I.
