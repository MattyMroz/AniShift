---
kind: review
status: pass-with-findings
reviewed-state: plan.md i specification.md po poprawkach rundy 1, 2026-10-25, baseline main @ 4365a51
date: 2026-10-25
---

# Review: plan i specyfikacja, runda 2

Ponowne czytanie całych plików po poprawkach z [round-1.md](round-1.md), z kontrolą spójności planu, specyfikacji i
kodu. Nadal samokontrola autora; niezależne review innego modelu jest wymagane przed wykonaniem (plan.md, §12).

## Zakres

- przedmiot: `plan.md` §5–§11, `specification.md` całość;
- ryzyka: sprzeczności między dokumentami po poprawkach, luki w ścieżkach decyzji właściciela, zgodność z regułami
  logowania;
- poza review: implementacja.

## Werdykt

**Status:** PASS WITH FINDINGS — poprawki rundy 1 są spójne; znalezione problemy były mniejsze i zostały naniesione.

**Najważniejszy powód:** plan rozstrzyga wszystkie materialne decyzje poza D1–D6, które mają rekomendacje i opisany
wpływ odpowiedzi na plan.

## Weryfikacja poprawek rundy 1

| Finding | Stan | Dowód |
|---|---|---|
| P1 kolejność węzłów | naprawione | plan.md §8.3: pary `[id, węzeł]`, walidacja bez scalania, test równoważności |
| P2 przegląd na kopii | naprawione | plan.md §8.6, faza 2 (plik `subscription_targets.py`), specification.md W13 |
| M1 znacznik per subskrypcja | naprawione | plan.md §8.6, specification.md W9, §8.7 |
| M2 koszt przeszukania | naprawione | plan.md faza 1, „Pomiar” |
| M3 nagrania harmonogramu | naprawione | plan.md faza 2, test `integration` |
| M4 checkpoint hosts | naprawione | plan.md faza 3 |

## Findings

### Mniejsze

#### M5. Brak ścieżek planu dla odpowiedzi właściciela innych niż rekomendacja

- miejsce: plan.md faza 0, pkt 3 (było tylko „D1 = nie → zatrzymaj”).
- wpływ: wykonawca musiałby sam zdecydować, co zmienić przy D2, D3 lub D5 innym niż rekomendacja.
- reakcja (naniesiona): dla każdej decyzji opisany skutek w planie.

#### M6. Sprzeczność w nazwach plików

- miejsce: plan.md §8.3 („nazwy plików wyłącznie z liczb”) wobec `graph-<root_id>.json`.
- reakcja (naniesiona): „stały prefiks rodzaju i liczba”.

#### M7. W12 obiecywało więcej, niż daje miejsce logowania

- dowód: `_catalog_error` (`anilist.py:487-496`) jest wołany także w parserach, a `candidate_from_node` łapie jego
  błąd przy niepoprawnej dacie (`anilist.py:369-372`); logowanie w budowniczym błędu dawałoby fałszywe ostrzeżenia.
  `_post` ma pięć miejsc `raise` (`:240`, `:242`, `:246`, `:248`, `:251`).
- reakcja (naniesiona): W12 obejmuje porażki na poziomie żądania; log w `_post`; błędy parsera zostają przy
  istniejących komunikatach `Franchise lookup failed` i `Airing schedule unavailable`.

#### M8. Log fallbacku bez `anilist_id` utrudniałby diagnozę

- dowód: inne logi ownera zawierają `anilist_id` (np. `Subscription next search`, `automation.py:3847-3853`);
  `services/catalog/AGENTS.md` zakazuje tylko tekstu wyszukiwania i treści odpowiedzi.
- reakcja (naniesiona): `anilist_id` w logu, przy wyszukiwaniu tylko `count`.

#### M9. Wątek, na którym owner zmienia `_catalog_as_of`

- dowód: `_finish_subscription_check` wykonuje się przez `_on_owner` (`automation.py:3889-3890`).
- reakcja (naniesiona): plan mówi wprost „wyłącznie na swoim wątku”.

### Sugestie

#### S2. Prostsza alternatywa rozważona i odrzucona

Sprawdzono, czy wystarczy wydłużyć pamięć `_Remembered` (bez plików). Nie wystarcza: awaria z 2026-10-21 zaczęła się
przy starcie rezydenta (dependency-map.md, §7), kiedy pamięć jest pusta. Plik jest najmniejszym mechanizmem, który
przeżywa restart.

#### S3. Kolejność prac z workstreamami 18 i 19

Oba plany zmieniają `acquisition.py`, `bootstrap.py` i `services/catalog/__init__.py`. Plan nakazuje sprawdzenie w
fazie 0 i rebase; kolejność scalania warto ustalić w rozmowie z właścicielem, zanim ruszą trzy branche naraz.

## Zgodność z kontraktem

| Wymaganie | Stan | Dowód |
|---|---|---|
| Mapa zależności ze ścieżkami i liniami | pass | dependency-map.md §2–§6 |
| Research ze źródłami, datami, faktami i wnioskami | pass | research.md §3–§8, oznaczenia DIRECT/REPORTED/INFERENCE/UNKNOWN |
| Najprostszy wariant | pass | specification.md „Ustalenia”, S2 |
| Co działa w trybie awaryjnym, a co nie | pass | specification.md W2–W13, „Poza zakresem”; plan.md §8.7 |
| Klucze `anilist_id` | pass | specification.md „Inwarianty” |
| Sygnalizacja w panelu | pass | W8, W9, D3, D6 |
| Rejestr silników | pass | specification.md „Ustalenia”, plan.md §7 Forbidden |
| Testy: markery, sieć domyślnie pomijana, nagrania bez sekretów | pass | plan.md §10 |
| Branch i commity ze scope z hooka | pass | plan.md §11; scope'y `services`, `application`, `tui`, `repo` w `check_commit_msg.py:37-61` |

## Wykonane kontrole

```text
ponowny odczyt plan.md (całość), specification.md (całość)
anilist.py:231-252, :359-372, :487-496 — miejsca raise i łapania błędu
automation.py:3847-3853, :3879-3898 — logi z anilist_id, wątek ownera
scripts/hooks/check_commit_msg.py:37-61 — scope'y
```

## Ograniczenia review

- Obie rundy wykonał autor planu. Reguła krzyżowa z root `AGENTS.md` wymaga przeglądu innego modelu przed
  wykonaniem; ten przegląd jest oczekujący.

## Zalecany następny krok

Odpowiedzi właściciela na D1–D6, niezależne review planu przez inny model, potem faza 0.
