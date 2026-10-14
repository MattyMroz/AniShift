---
kind: plan
status: aktywny
updated: 2026-09-28
parent: plans/e1-wybor-odcinka.md
---

# Plan: heurystyka E1 jako wyszukiwarka i weryfikator

Plan zapisuje decyzje właściciela z 2026-09-28 i koryguje kierunek fazy 2 planu
`e1-wybor-odcinka.md`. Tam, gdzie oba plany się różnią, obowiązuje ten.

## 1. Decyzje właściciela (2026-09-28)

| Nr | Decyzja |
| --- | --- |
| H-1 | System ma dwie części: **wyszukiwarkę** (szybkie znalezienie i uszeregowanie kandydatów) oraz **weryfikator** (sprawdzenie, że pobrany plik to właściwy odcinek). Heurystyka nie działa sama. |
| H-2 | Tryb ręczny: heurystyka tylko **sugeruje i sortuje**, właściciel wybiera. Musi być szybka. |
| H-3 | Tryb subskrypcji: dotyczy **nowych tytułów** (w emisji, praktycznie 2021+) i tylko odcinków niewyemitowanych w chwili dodania. Pobiera automatycznie `zgodne`; `niepewne` tylko według dopuszczalności `e1-przeplyw-subskrypcji.md` §3.3. |
| H-4 | Do właściciela trafia wyłącznie to, czego system nie rozstrzygnął po wszystkich krokach (eskalacje: `e1-przeplyw-subskrypcji.md` §5.6). Skoro coś trafia do właściciela, to jest ważne. Brak powiadomienia oznacza, że wszystko przeszło. |
| H-5 | Weryfikacja po pobraniu (H2) dotyczy tylko automatycznych pobrań subskrypcji; czy zostaje, wypada, czy działa w trybie „tylko zapis”, rozstrzyga `e1-przeplyw-subskrypcji.md` §5.4. Gdy plik okaże się zły: zatrzymaj transfer, usuń plik tylko przy warunkach K-09, wyklucz parę (hash, plik), spróbuj następnego kandydata w limicie prób celu (tamże §3.3). Po wyczerpaniu limitu zgłoś właścicielowi. |
| H-6 | Żadna warstwa nie daje 100%. Bezpieczeństwo wynika z nakładania warstw (heurystyka → weryfikacja po pobraniu → pętla ponowienia → eskalacja), a nie z jednej doskonałej reguły. |
| H-7 | Bez nowych zależności, jeśli nie dają wyraźnego zysku. Najpierw sprawdzić istniejące otwarte parsery i rozwiązania; nie pisać od zera tego, co już istnieje. Zależność tylko po pomiarze szybkości, stabilności i licencji, przez `uv add`. |
| H-8 | Kod heurystyki ma jakość produkcyjną i dobrą dokumentację, ale na tym etapie **nie jest jeszcze wpięty** w aplikację. |
| H-9 | Priorytet jakości: najnowsze odcinki. Starsze tytuły mają gorszą standaryzację nazw i trafiają do trybu ręcznego. |

## 2. Stan na 2026-09-28

- Dataset: `%USERPROFILE%\acquisition-labels\label-fixes-v1\dataset.json`
  (SHA `2cc60928…`), 52 577 rekordów: 45 452 poprawny, 6507 błędny, 618 nie da się ustalić.
  Weryfikacja 9 serii z rozjazdem numeracji (`label-fixes-v2\`): 44 zmiany potwierdzone,
  35 spornych — do rozstrzygnięcia przed egzaminem.
- Podział zamrożony: `split-v1-labels-fix1\` — robocza 36 862, egzamin 15 715, bez przecieków.
- Heurystyka v5 (`scripts/tmp/e1_heuristic.py`) na części roboczej, metryka per odcinek:

| Lata emisji | Pokrycie odcinków | Odcinki z błędną akceptacją |
| --- | ---: | ---: |
| przed 2010 | 69% | 0 |
| 2010–2015 | 76% | 1 |
| 2016–2020 | 79% | 3 |
| 2021+ | 87% | 1 |

  Wszystkie błędne akceptacje pochodzą z serii, w których katalog i wydawcy liczą odcinki inaczej
  (fragmenty, kompilacje, pary odcinków). Z samej nazwy pliku nie da się tego rozpoznać; łapie to
  dopiero weryfikacja po pobraniu (H-5).
- Parsery: `anitopy` (MPL-2.0, ~20 KB, bez zależności, nieutrzymywany od 2022) zawiesił się na
  danych korpusu; `guessit` (LGPL, ~330 KB + 3 zależności) niezmierzony. Żadnego nie dodano.

## 3. Architektura docelowa

```text
katalog odcinka ─► WYSZUKIWARKA ─► lista kandydatów z oceną zgodny / niepewny / niezgodny
                    (heurystyka nazw)          │
                                               ├─ ręcznie: pokaż uszeregowaną listę
                                               └─ subskrypcja: pierwszy dopuszczalny wg rankingu
                                                          │
                                         pobranie ─► WERYFIKATOR PO POBRANIU (o ile H2 zostaje)
                                                          │
                                  przyjęta ◄──────────────┤
                                                          └─ odrzucona: wyklucz parę,
                                                             następny dopuszczalny w limicie prób
                                                             → po wyczerpaniu eskalacja
```

Dopuszczalność, limit prób celu, bramka przyjęcia i przejścia: `e1-przeplyw-subskrypcji.md`
§3.3–§3.6 (diagram jest skrótem, nie kopią reguł).

Weryfikator po pobraniu (pierwsza wersja, bez nowych zależności):

- długość wideo z `ffprobe` względem długości odcinka z katalogu; wykrywa fragmenty,
  kompilacje, pary odcinków, recapy i dodatki;
- liczba i typ strumieni (wideo jest; plik nie jest samym audio ani napisami);
- opcjonalnie w kolejnych wersjach: tytuł odcinka lub numer w metadanych kontenera, rozdziały MKV.

## 4. Kroki

| Nr | Krok | Wykonawca | Warunek ukończenia |
| --- | --- | --- | --- |
| K-1 | Rozstrzygnąć 35 spornych etykiet 9 serii (trzeci, niezależny głos) i opublikować `label-fixes-v2` | `sol6` + `opus55` | dataset v2 z weryfikacją, podział bez zmian |
| K-2 | Badanie istniejących parserów i rozwiązań (anitomy, guessit, Sonarr/TheXEM, Shoko, SeaDex, Anime-Lists); pomiar z limitem czasu na nazwę | `sol6` | raport w `research/` z rekomendacją: użyć / nie używać |
| K-3 | Heurystyka v6 jako kod produkcyjny: moduł wyszukiwarki (ranking + ocena), pełne docstringi kontraktu, testy adversarialne, metryka per odcinek i per lata | `astra` | 0 błędnych akceptacji rozpoznawalnych z nazwy/metadanych w pierwszym zamrożonym przejściu (W1 poniżej, D6 w `e1-wybor-odcinka.md`); pokrycie odcinków 2021+ ≥ 87% |
| K-4 | Przegląd v6 | `opus55` | PASS albo lista poprawek do K-3 |
| K-5 | Jednorazowy egzamin na części odłożonej, wynik osobno dla 2021+ i całości; bramka: 0 błędnych `zgodnych` rozpoznawalnych z nazwy/metadanych, pozostałe z adnotacją „domena heurystyki 2” według kryteriów zamrożonych przed egzaminem (D6) | orkiestrator | raport w `outcomes/e1.md` |
| K-6 | Weryfikator po pobraniu H2 (długość/strumienie) jako kod produkcyjny niewpięty w aplikację; twarde odrzucenie długości tylko przy `anizip.length` konkretnego odcinka i braku sygnału sprzecznych granic odcinka (K-04). Pętla ponowienia należy do maszyny stanów przepływu (`e1-przeplyw-subskrypcji.md` §3.3–§3.6) | `astra`, przegląd `opus55` | testy na syntetykach i realnych plikach; decyzja zostaje / wypada / tylko zapis według `e1-przeplyw-subskrypcji.md` §5.4 |
| K-7 | Przy porażce K-5: poprawka oceniana tylko na świeżych tytułach rezerwy | wszyscy | nowy egzamin zdany |

### Decyzja orkiestratora 2026-09-28: bramka K-3 na poziomie systemu

Przegląd v7 wykazał, że żadnej z 19 błędnych akceptacji na części roboczej nie da się
uczciwie odrzucić ogólną regułą nazwy pliku. 16 wynika z rozjazdu numeracji katalog
vs wydawca (NEET Kunoichi, Saiki K., Owarimonogatari), 2 z remake'u o identycznym
tytule (Kanon). Dlatego:

- **W1 (heurystyka):** zero błędnych akceptacji rozpoznawalnych z nazwy, ścieżki lub
  metadanych runtime; każda pozostała błędna akceptacja musi mieć udokumentowaną
  przyczynę spoza nazwy.
- **System (W1 + W3):** zero błędnych akceptacji w 2021+ po zastosowaniu weryfikatora
  po pobraniu na danych z oczekiwaną długością odcinka — tylko jeśli H2 zostaje
  (`e1-przeplyw-subskrypcji.md` §5.4); nie jest bramką egzaminu heurystyki.
- Reguły ogólne, które usuwają pojedynczy błędny odcinek kosztem dziesiątek dobrych
  (np. „TV_SHORT → niepewny”: −1 błąd, −26 odcinków), są odrzucone.

## 5. Zasady egzaminu (bez zmian)

- Egzamin jest jednorazowy; autor heurystyki nie widzi części odłożonej.
- Twardy błąd: `zgodny` przy etykiecie `błędny`. Akceptacja `nie da się ustalić` to osobna kategoria ryzyka.
- Pomiar główny: pokrycie odcinków i odcinki z błędną akceptacją, osobno dla 2021+.
