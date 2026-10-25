---
kind: review
status: pass-with-findings
reviewed-state: specification.md i plan.md po poprawkach rundy 1, 2026-10-25
date: 2026-10-25
---

# Review: plan i specyfikacja, runda 2

## Zakres

- Przedmiot: te same pliki po poprawkach F1–F8 z [round-1.md](round-1.md).
- Cel: sprawdzić, czy poprawki nie otworzyły nowych dziur, i jeszcze raz spróbować obalić miarę oraz kolejność faz.
- **Ograniczenie niezależności**: jak w rundzie 1, ten sam autor i ta sama sesja.

## Werdykt

**Status:** PASS WITH FINDINGS. **Powód:** dwa poważne problemy znalezione w tej rundzie poprawiono i sprawdzono. Zostały decyzje właściciela i brak niezależnego review, które nie blokują akceptacji kierunku, ale blokują wykonanie.

## Findings

### Poważne (poprawione w tej rundzie)

#### H1. Nowa reguła M2 odrzuca poprawne formy z obocznością

- Miejsce: M2 po F1.
- Dowód: polskie imiona na `-ka`, `-da` mają w celowniku i miejscowniku oboczność: `Yumeka` → `Yumece`, `Momoka` → `Momoce`, `Nishida` → `Nishidzie`. Wszystkie trzy formy są w `ready/` (Ao no Hako, Koori) i są poprawne. Reguła „temat bez `-a` jako prefiks” liczyła je jako błąd.
- Wpływ: zaniżone M2 i fałszywa niespójność w M3, kara za poprawną polszczyznę.
- Poprawka (naniesiona): dopuszczone oboczności `-ce`, `-dze`, `-cie`, `-dzie` dla `-ka`, `-ga`, `-ta`, `-da`. Sprawdzone skryptem na 12 przypadkach: `Yumece`, `Momoce`, `Nishidzie`, `Shizuce`, `Saikawie` przyjęte; `Rebeki`, `Hagasegawa`, `Hinę`, `Onso`, `Gyokuyo` nadal odrzucone. Test `…accepts_a_consonant_alternation_in_the_dative`.

#### H2. Lista M5 wskazywała przypadki numerami linii ze starych plików

- Miejsce: M5.
- Dowód: numery z `evidence.md` dotyczą plików w `ready/`; przebiegi benchu tworzą nowe pliki z innym układem linii (inne łamanie, inna liczba zdarzeń przy deduplikacji szyldów).
- Poprawka (naniesiona): przypadek wskazany odcinkiem, czasem startu i tekstem źródła; test `…finds_a_case_by_start_time_and_source_text`.

### Mniejsze (poprawione)

- H3. Wyrazy z łącznikiem (`Shindo-senpaia`) w M2: dopisana reguła podziału, sufiks ocenia M4.
- H4. Przebieg bazowy fazy 1 miał biec „na main”, a narzędzie pomiaru leży na gałęzi. Doprecyzowane: gałąź po commicie 1, który zmienia tylko `scripts/`.
- H5. Teza „Morfeusz nie zna japońskich imion” w `intent.md` była bez dowodu. Sprawdziłem: `morfeusz2` zwraca `ign` dla sześciu imion z próbki. Dopisane z datą.

### Mniejsze (otwarte)

- H6. Reguła D1 (a) zakłada, że angielskie źródło dobrze oddaje sufiksy. W *Kusuriya* CR zamienia je na `Master`/`Lady`, w *Ao no Hako* NF pisze `Senpai` osobnym słowem. Reguła „jak w źródle” dziedziczy te wybory. To świadomy kompromis w D1, ale właściciel powinien go widzieć przy decyzji (opisany w D1 i `research.md` §3.3).
- H7. Szacunek kosztu Q1 (4–7% wejścia) opiera się na założonej długości linii wpisu i zasobu `glossary.md`. Rzeczywisty koszt zmierzy M6; plan tego nie ukrywa.
- H8. Nie wiem, które z 15 odcinków benchu pochodzą z subskrypcji, a które da się rozpoznać tylko przez D5 (b): nie czytałem stanu ownera (zakaz briefu). W benchu z własnym `ANISHIFT_CONFIG_DIR` stanu ownera i tak nie ma, więc każdy odcinek przejdzie ścieżką D5 (b). Ścieżka D5 (a) zostaje sprawdzona tylko testami. Faza 0 powinna to potwierdzić i, jeśli właściciel wybierze D5 (a), przygotować w benchu minimalny stan z identyfikatorami AniList.

### Sugestie

- Jeśli wariant „R1 bez glosariusza” da prawie tę samą poprawę co pełny, rozważyć zatrzymanie się na regułach i ręcznym glosariuszu bez AniList. Mniej kodu, zgodnie ze skillem `simple`. Plan pozwala na tę decyzję po fazie 3.

## Sprawdzenie planu według skilla `planning` §16

| Pytanie | Odpowiedź |
|---|---|
| Jeden rezultat? | tak: glosariusz serii plus reguły, z pomiarem |
| Stan i przyczyna z dowodem? | tak: `evidence.md` §1 i §3 |
| Decyzje materialne rozstrzygnięte? | nie wszystkie: D1–D8 czekają na właściciela, każda z rekomendacją |
| Ownership jednoznaczny? | tak: plik glosariusza należy do `application/glossary.py` i właściciela |
| Kolejność a zależności? | tak: pomiar bazowy przed zmianą, typy translation przed aplikacją |
| Testy wykryją zły wynik? | po H1–H2 tak dla miar; jakość tłumaczenia ocenia człowiek (M5) |
| Prostsza droga? | możliwa (sugestia wyżej); plan mierzy ją wariantem R1 |
| Świeży wykonawca ruszy bez zgadywania? | tak, po zapisaniu decyzji D1–D8 w fazie 0 |

## Wykonane kontrole

```text
reguła M2 z obocznościami na 12 parach: 7 poprawnych przyjętych, 5 błędnych odrzuconych
morfeusz2.analyse: Hino, Gyokuyou, Rebecca, Nagisa, Yamada, Hinę -> ign
ponowny odczyt specification.md i plan.md po poprawkach: numeracja G1–G12, P1–P6, M1–M6 spójna z odwołaniami w plan.md
```

## Niewykonane

- Review krzyżowe innym modelem (zakaz subagentów w briefie). Wymagane przed fazą 0 według root `AGENTS.md`.
- Żadnego przebiegu płatnego; liczby bazowe nie istnieją.

## Zalecany następny krok

Właściciel rozstrzyga D1–D8. Potem review planu przez świeżą instancję innego modelu i faza 0.
