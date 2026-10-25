---
kind: review
status: fail
reviewed-state: plan.md i specification.md, pierwsza wersja, 2026-10-25, baseline main @ 4365a51
date: 2026-10-25
---

# Review: plan i specyfikacja, runda 1

Samokontrola autora planu według skilla `review`, z otwarciem kodu od nowa. Nie zastępuje niezależnego review innego
modelu (plan.md, §12).

## Zakres

- przedmiot: `plan.md`, `specification.md`, z odniesieniem do `dependency-map.md` i `research.md`;
- authority: polecenie zadania, root `AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/services/catalog/AGENTS.md`;
- ryzyka: zmiana wejścia H1, utrwalenie w stanie decyzji podjętej na kopii, łamanie istniejących kontraktów testów,
  koszt wydajności, zgodność z regułą rejestru silników;
- poza review: implementacja (nie istnieje), ocena prawna regulaminu AniList.

## Werdykt

**Status:** FAIL — dwa poważne problemy wymagały zmiany designu przed oddaniem.

**Najważniejszy powód:** odtwarzanie grafu przez ponowne scalanie mogło zmienić kolejność węzłów i krawędzi, a przegląd
po migracji mógł zakończyć się trwale na danych z kopii.

## Findings

### Poważne

#### P1. Odtworzenie grafu z płaskiej listy węzłów zmienia kolejność

- miejsce: plan.md §8.3, pierwsza wersja („odczyt grafu przechodzi przez `parse_franchise_page`”).
- dowód: `_collect_franchise` (`anilist.py:276-307`) wstawia węzły w porządku DFS po zagnieżdżonych krawędziach i
  scala krawędzie istniejących węzłów. Na żywo strony 2–4 są przetwarzane w kolejności odpowiedzi AniList
  (`anilist.py:163-171`). Płaska lista węzłów odtworzona tym samym kodem odwiedza węzły z granicy w innej kolejności,
  więc ich dzieci trafiają do słownika w innym porządku. `AGENTS.md` katalogu i aplikacji wymagają zachowania
  kolejności („Merge one GraphQL data page without reordering nodes, titles or relation edges”, `anilist.py:261`).
  `franchise_view` bierze kolejność wpisów z `_walk`, a `identity_target` buduje `other_series` z `nodes.items()`
  (`episode_selection.py:456-461`).
- wpływ: kopia mogłaby dać inny widok franczyzy albo inny cel H1 niż ten sam graf na żywo. H1 część wejść traktuje
  jako zbiory (`episode_identity.py:463-488`), ale nie wszystkie, a regresja H1 wymaga osobnej procedury.
- reakcja (naniesiona): zapis par `[id, węzeł]` w kolejności `graph.nodes`, walidacja każdego węzła istniejącym
  walidatorem, słownik budowany wprost z pliku. Dodany test równoważności grafu z pliku i z replayu (plan.md §8.3,
  §8.7, faza 1).

#### P2. Przegląd po migracji kończy się na danych z kopii

- miejsce: plan.md §8.5 — „`schedule_warning` tylko gdy brak harmonogramu ani na żywo, ani w kopii”.
- dowód: `merge_listing` przepuszcza rekord z `review_pending` tylko przy `read.live` i braku `schedule_warning`
  (`subscription_targets.py:520`); `_reviewed` zdejmuje przegląd i może wstrzymać subskrypcję z powodem
  `MIGRATED_DUE` (`:692-702`). Kopia czyści ostrzeżenie, więc przegląd zamknąłby się na starych datach, a wynik
  zostaje w `state.json`.
- wpływ: trwała zmiana stanu subskrypcji na podstawie danych sprzed awarii.
- reakcja (naniesiona): przegląd wymaga także `catalog_as_of is None` (plan.md §8.6, faza 2; nowe W13 w
  specification.md).

### Mniejsze

#### M1. Jeden globalny znacznik kopii „miga” przy mieszanych odczytach

- miejsce: plan.md §8.6, pierwsza wersja (`_catalog_as_of: datetime | None` nadpisywany przez każde sprawdzenie).
- dowód: subskrypcje sprawdzane są pojedynczo w puli I/O (`automation.py:3879-3898`); jedna z pamięci na żywo i
  jedna z kopii nadpisywałyby sobie wynik.
- reakcja (naniesiona): słownik per `subscription_id`, publikowana najstarsza data; W9 doprecyzowane.

#### M2. Koszt przeszukania kopii nieznany

- miejsce: §8.2 `candidates()` i `graph(id)` dla wpisu spoza korzeni czytają wszystkie pliki.
- dowód: nagrania mają do 171 KB (`tests/fixtures/search/anilist__franchise__106509.json`); limit 256 plików.
- reakcja (naniesiona): pomiar w fazie 1 i zgłoszenie przed optymalizacją; bez indeksu na zapas.

#### M3. Brak nagrań harmonogramu dla testu integracyjnego

- dowód: `tests/fixtures/search/` zawiera tylko `franchise`, `media` (`RELATIONS_QUERY`) i `search`.
- reakcja (naniesiona): mała odpowiedź harmonogramu zapisana w teście.

#### M4. Checkpoint z plikiem hosts bez warunków

- reakcja (naniesiona): ścieżka pliku, uprawnienia administratora, `ipconfig /flushdns`, oznaczenie jako opcjonalne.

### Sugestie

#### S1. Znacznik kopii w rejestrze decyzji

Wpis `check` w `decisions.jsonl` nie powie, że decyzja zapadła na kopii. Nie wprowadzono: rejestr jest poza zakresem
(plan.md §7), a log `Saved catalog used` daje ślad. Do rozważenia przez właściciela przy następnej pracy nad rejestrem.

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
|---|---|---|
| Rejestr silników tylko w `translation`, `tts`, `llm` | pass | plan.md §7 Forbidden; `SavedCatalog` to zwykła klasa w `services/catalog` |
| Klucze `anilist_id` bez zmian | pass | §8.4 tylko nowe pola z domyślnymi; brak zmian schematu |
| Cooldown nie woła katalogu | pass | §8.5 zachowuje skrót `acquisition.py:1292-1293`; testy `test_acquisition.py:1366-1380`, `:1438-1452` bez zmian |
| Brak nowej zależności | pass | §8.3: `tempfile`, `json`, `pathlib` |
| Logi bez ścieżek i haseł | pass | §8.2, §8.5 |
| H1 bez zmian | pass po P1 | §8.3 równoważność |
| Decyzja w stanie na kopii | pass po P2 | §8.6 |

## Wykonane kontrole

```text
odczyt anilist.py:131-307, acquisition.py:850-1340, subscription_targets.py:480-545 i :692-702,
episode_selection.py:410-465, episode_identity.py:460-490, automation.py:3739-3759, 3879-3992, 9077-9099
grep nagrań w tests/fixtures/search/ → brak SCHEDULE_QUERY
test_acquisition.py:1366-1452 → kontrakt cooldownu
```

## Niewykonane kontrole

- Brak implementacji, więc brak testów i pomiarów.
- Ocena prawna regulaminu AniList — decyzja D1 właściciela.

## Zalecany następny krok

Runda 2 na poprawionym planie.
