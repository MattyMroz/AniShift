---
kind: review
status: fail, poprawki naniesione
reviewed-state: specification.md i plan.md, pierwsza wersja z 2026-10-25
date: 2026-10-25
---

# Review: plan i specyfikacja, runda 1

## Zakres

- Przedmiot: `specification.md`, `plan.md`; tło: `evidence.md`, `research.md`.
- Authority: brief zadania, root `AGENTS.md`, `services/translation/AGENTS.md`, `engines/llm/AGENTS.md`, skille `planning` i `review`.
- Ryzyka: miara, która nie wykrywa błędów z dowodów; utrata ręcznych poprawek; ukryty koszt zapytań; brak możliwości przypisania poprawy.
- **Ograniczenie niezależności**: review napisał autor planu w tej samej sesji (brief zakazał subagentów). To nie jest review krzyżowe w rozumieniu root `AGENTS.md`. Przed wykonaniem planu potrzebna jest świeża instancja innego modelu.

## Werdykt

**Status:** FAIL. **Najważniejszy powód:** miara M2 w pierwszej wersji uznawała za poprawne trzy z pięciu błędów pisowni, które miała wykrywać (F1).

## Findings

### Poważne

#### F1. M2 przepuszcza błędy, które ma mierzyć

- Miejsce: `specification.md`, M2, pierwotnie „`pl` bez końcowej samogłoski”.
- Dowód: sprawdziłem regułę na przypadkach z `evidence.md`. `Gyokuyou`→`Gyokuyo`, `Onsou`→`Onso` i `Hino`→`Hinę` dają przy tej regule wynik „zgodne”, bo temat `Gyokuyo`, `Onso`, `Hin` jest prefiksem złej formy.
- Wpływ: S1 mógłby przejść bez żadnej poprawy pisowni.
- Poprawka (naniesiona): reguła zależna od zakończenia (`-a` → temat bez `-a`; nieodmienne według D3 → forma dokładna; reszta → cały `pl` jako prefiks). Sprawdzona skryptem na 12 przypadkach: wszystkie błędy odrzucone, poprawne formy (`Rebeccę`, `Taniego`, `Saikawie`) przyjęte. Dwa testy w planie (`…rejects_a_dropped_long_vowel`, `…rejects_a_feminine_form_of_an_indeclinable_male_name`).

#### F2. Nie da się przypisać poprawy glosariuszowi

- Miejsce: plan, fazy 1 i 5. Przebieg „po” zmienia naraz reguły promptu i glosariusz.
- Wpływ: jeśli poprawa pochodzi z samych reguł R1, glosariusz (nowa struktura, pliki, AniList) może być zbędną złożonością. Tego nie wiemy.
- Poprawka (naniesiona): opcjonalny wariant „R1 bez glosariusza” w D7. Uruchamia się go na stanie gałęzi po fazie 3 i przed fazą 4, bez dodatkowego przełącznika w kodzie, bo do tego momentu nic nie dostarcza glosariusza.

#### F3. Ręczna poprawka może zginąć w trakcie odświeżania

- Miejsce: G10, impact scan, wiersz o równoległych zadaniach.
- Scenariusz: zadanie wczytuje plik, pobiera postacie z AniList (sekundy), w tym czasie właściciel zapisuje poprawkę, zadanie podmienia plik swoją wersją.
- Wpływ: łamie I3 („ręczne wpisy nigdy nie są nadpisywane”).
- Poprawka (naniesiona): G10 wymaga ponownego wczytania tuż przed zapisem i dopisania do świeżej treści; test `test_refresh_merges_into_a_file_edited_during_the_fetch`.

#### F4. Wyszukiwanie AniList przy każdym odcinku

- Miejsce: D5 (b), Q3.
- Dowód: przy rozpoznaniu po nazwie pliku nic nie zapamiętywało dopasowania, więc każdy odcinek ręcznie wrzuconej serii wysyłałby wyszukiwanie. Q3 mówiło tylko o stronach postaci, a pomijało wyszukiwanie i graf franczyzy.
- Poprawka (naniesiona): pole `file_titles` (G2), wyszukiwanie dopiero po braku trafienia (G11), pełny rachunek zapytań w Q3; test `test_known_file_title_sends_no_search`.

#### F5. Wyszukiwanie trafia w pierwszy sezon

- Miejsce: D5 (b).
- Dowód: `library_label` odcina sezon z tytułu (`The Apothecary Diaries` + sezon 3). Wyszukiwanie samego tytułu wskaże raczej pierwszą serię, więc postacie sezonu 3 nie trafią do glosariusza.
- Poprawka (naniesiona): G12, najpierw „<tytuł> Season <n>”; test `test_season_search_tries_the_season_title_first`.

### Mniejsze

#### F6. Szyldy wielkimi literami

- P1 wymagało dokładnej wielkości liter, a imiona na szyldach są pisane wersalikami (`MIZAR`, `NISHI I YAMADĄ`).
- Poprawka (naniesiona): P1 dopuszcza wariant wersalikowy, ale nie małe litery (`White`, `Hel` jako zwykłe słowa); dwa testy.

#### F7. Glosariusz referencyjny bez tytułów i wpisów spoza AniList

- Pomiar M2 dla przykładów 1–2 i 6 wymaga wpisów, których AniList nie ma.
- Poprawka (naniesiona): faza 1 dopisuje je jako `origin: owner`; M2 raportowane osobno dla wpisów z AniList i ręcznych; S1 dotyczy tylko wpisów z AniList.

#### F8. Stan ownera

- Plan nie mówił wprost, że glosariusz tylko czyta `config/watch/state.json`.
- Poprawka (naniesiona): inwariant I4.

### Sugestie

- Wpis tytułu serii (D4) i tytułów rang (`Master Jinshi`) to w praktyce pierwsze pozycje przyszłej „pamięci terminów”. Warto po pomiarze sprawdzić, ile takich wpisów właściciel dopisał ręcznie; to najlepszy sygnał, czy etap odłożony jest potrzebny.

## Zgodność z kontraktem briefu

| Wymaganie briefu | Stan | Dowód |
|---|---|---|
| Stan dziś ze ścieżkami i liniami | pass | `evidence.md` §1 |
| 10–20 przykładów z plikiem i linią | pass | 17 przykładów, `evidence.md` §3 |
| Research ze źródłami | pass | `research.md`, daty dostępu |
| Projekt: źródło, format, miejsce, odmiana, wstrzyknięcie, spójność, korekta, koszt, pomiar | pass po poprawkach | `specification.md` G, P, R, M, Q |
| Plan: fazy, pliki, testy z markerami, bramki, branch, commity ze scope | pass | `plan.md` |
| Zapis tylko w `docs/work/16-proper-names/` | pass | brak zmian poza katalogiem |

## Wykonane kontrole

```text
reguła M2 (stara i nowa) na 12 parach z evidence.md: stara 3 fałszywe „zgodne”, nowa 0
grep po stałych kodu przywołanych w planie (ścieżki, symbole, linie): zgodne z main @ 4365a51
```

## Zalecany następny krok

Runda 2 na wersji z poprawkami; potem review krzyżowe innym modelem przed fazą 0.
