# Etap 3 — ekstrakcja + refaktor napisów — WYMAGANIA

> Ten dokument to **wymagania**, nie plan i nie kod. Plan powstanie dopiero po zaakceptowaniu wymagań.
> Status: **DRAFT — do przeglądu przez usera.** Sekcja USTALONE = potwierdzone. `???` = wymaga decyzji.
> Referencje: kod `../mm_avh_working_space/` (materiał źródłowy, **nie wzorzec**), `external/docs/mkvtoolnix/`, zbiór testowy `../mm_avh_working_space/temp/{dataset_ass,ground_truth}/` (183 pliki ASS + ręczny ground truth), pliki z bugami `../mm_avh_working_space/working_space/bugs/`.

## Cel

Enter w shellu zaczyna realnie pracować: MKV z `workspace/` → wyciągnięte ścieżki → napisy podzielone na to, co **lektor przeczyta** (`spoken`) i to, co **widz zobaczy** (`displayed`).

## Zasada nadrzędna

**mm_avh to materiał źródłowy, nie wzorzec.** Kod działa, ale jego kształt wynikał z ograniczeń, których już nie mamy. Każde nieoczywiste rozwiązanie sprawdzamy pomiarem albo w `external/docs/`, zanim je przepiszemy.

Dowody z tej sesji (wszystkie zmierzone, nie założone):
- `--gui-mode` czyni zbędnym 30 linii obejścia (`read(1)`) — wynik bit-w-bit identyczny,
- klasyfikator ma **95.86%**, nie deklarowane 99% (182 pliki, 1014 stylów),
- audyt 03 **zmyślił** buga main/alt — w kodzie go nie ma,
- `ASS→SRT→ASS` gubi **wszystko** (style 8→1, tagi 2169→0, eventy 2483→2181),
- `ASS→ASS` z podmianą samego tekstu **nie gubi nic** (2483→2483, 8→8, 2169→2169).

> ⚠️ **Audyty w `docs/reference/audyt-mm-avh/` bywają błędne.** Przy wątpliwości: czytaj kod, nie audyt.

---

## 1. MODEL DANYCH — najważniejsza zmiana względem mm_avh

### Jak było i dlaczego to był przypadek

mm_avh: `ASS → SRT → tłumacz → SRT → ASS`. SRT był **etapem pośrednim**, bo stare funkcje tłumaczenia i lektora umiały czytać wyłącznie pliki SRT. To ograniczenie narzędzi, nie decyzja projektowa.

### Jak jest

**ASS jest formatem roboczym przez cały pipeline.** Tłumaczenie i TTS żyją *wewnątrz* programu, więc nie potrzebują pliku pośredniego.

```
MKV
 └─ ASS (lub SRT — patrz R2)          ← źródło prawdy, NIGDY nie ginie
     │
     ├─ oznacz każdą linię:  spoken | displayed
     │
     ├─ spoken   → tekst do tłumaczenia → tekst do lektora   (stan w pamięci)
     └─ displayed → <nazwa>.displayed.ass                     (JEDYNY produkt)
```

**Trzy konsekwencje, każda kasuje byt z mm_avh:**

- **`main` przestaje istnieć jako plik.** Był stanem pośrednim w drodze do lektora i na końcu i tak był kasowany. Znika `tmp/main_subs/`, `_move_subs_to_main`, `_save_subs`, `_copy_metadata_and_styles`.
- **`srt_to_ass` jako „scalanie z powrotem" znika** — nic się nie rozłączyło, więc nie ma czego scalać. (Etap 7 dostaje gotowy `displayed.ass`.)
- **Decyzja `spoken`/`displayed` zapada na LINIĘ, nie na styl.** To rozwiązuje przypadek, którego na poziomie stylu rozwiązać się nie da (§5).

### Nazewnictwo

| pojęcie | nazwa | czym jest |
|---|---|---|
| linia idzie do lektora | **`spoken`** | stan w pamięci, nie plik |
| linia zostaje na ekranie | **`displayed`** | trafia do `<nazwa>.displayed.ass` |

**Świadomie NIE `signs`/`narration`** — te nazwy przemycają założenie, że o losie linii decyduje jej rodzaj albo styl ASS. Właśnie to obaliliśmy (§5). `spoken`/`displayed` opisują **co się z linią dzieje**, nie czym rzekomo jest.

`main`/`alt` porzucone: nic nie znaczyły i sugerowały, że `alt` to śmieci. `displayed` to **produkt końcowy** — widz musi zobaczyć, co jest na szyldzie, skoro lektor tego nie czyta.

---

## 2. Wymagania funkcjonalne

- **R1 — Enter uruchamia pipeline.** Discovery w `workspace/` (natsorted) → per plik: identify → wybór ścieżek → ekstrakcja → podział napisów. Tryb z ustawień; **auto jest domyślne i docelowe**.
- **R2 — ASS i SRT równorzędnie na wejściu.** MKV bywa z ASS (anime) albo z SRT (Netflix, Rick and Morty). Oba obsługiwane. **Innych formatów nie ma** — `.sup`/`.vtt`/`.sub` mm_avh skanuje, ale nie ma dla nich handlera (martwy kod, nie portujemy).
- **R3 — Identyfikacja ścieżek.** `mkvmerge -J <plik>` → typowana lista.
- **R4 — Auto-wybór ścieżek.** `track_selector.py` **1:1** (test regresji na 206 plikach).
- **R5 — Ekstrakcja z paskiem postępu.** `mkvextract --gui-mode tracks` → `#GUI#progress N%`, linia po linii. NIE portujemy `read(1)`.
- **R6 — Odsiew przed klasyfikacją** (kolejność ma znaczenie — §5):
  - **R6a** — linie rysunkowe (`\p1`-`\p9`) odsiane; TTS przeczytałby współrzędne na głos,
  - **R6b** — **collapse FBF**: N linii o identycznym `plaintext` i ciągłych timingach → jedna (`start=min`, `end=max`),
  - dopiero potem klasyfikacja. Zmierzone: `1381 → 18` linii.
- **R7 — Podział `spoken`/`displayed` na linię.** Heurystyka (port `style_classifier.py` **bez strojenia**) + odsiew R6.
- **R8 — Produkt: `<nazwa>.displayed.ass`.** Tagi, style, timingi **nietknięte** (zmierzone: podmiana tekstu z zachowaniem tagów = 2169→2169).
- **R9 — Tryb manual jako wyjście awaryjne**, nie główna droga. ??? D5 — o co pyta.
- **R10 — Równoległość skalowana do maszyny.** `max(1, min(n_plików, cpu_count(), cap))`. **Sufit z pomiaru** — ekstrakcja to I/O, nie CPU.
- **R11 — Multi-pasek postępu.** Wiele plików = wiele pasków. **Wymaga etapu 3.1** (§4).
- **R12 — TXT → SRT zostaje** (side quest: szybkie audiobooki). W mm_avh ta ścieżka jest zepsuta end-to-end — portujemy naprawioną.
- **R13 — Błąd jednego pliku nie przerywa reszty.** **Jasny komunikat: co i gdzie poszło nie tak** (wymaganie usera).

## 3. Wymagania niefunkcjonalne

- **N1 — Odwracalność przez zachowanie oryginału.** Oryginalny ASS zostaje nietknięty. Pomyłka heurystyki **nie niszczy pliku** — da się cofnąć. To główne kryterium usera i jedyny działający mechanizm (round-trip go nie daje — §5).
- **N2 — Determinizm.** Dwa przebiegi na tym samym pliku → identyczny wynik bajt w bajt. (Zmierzone: pysubs2 jest deterministyczny.) **pysubs2 przypięty do wersji.**
- **N3 — Zero `sys.exit()` / `input()` w serwisie.**
- **N4 — Walidacja wyniku, nie tylko exit code.** mkvextract potrafi zwrócić 0 i nie zapisać pliku (zweryfikowane).
- **N5 — Domeny bez rejestru.** `extraction`/`subtitles` nie mają `engines/`.
- **N6 — Binarki przez `ensure_binary()`** (etap 2.5).
- **N7 — Testowalność bez MKV.** Klasyfikacja i podział testowalne na 183 plikach ASS ze zbioru.
- **N8 — Progress nie koliduje z promptem.**
- **N9 — Foldery odtwarzalne.** User może skasować `workspace/` — ma się odbudować.
- **N10 — Bez stanu wznowienia.** ElevenBytes jest **darmowy**, tłumaczenie+TTS to ~1 min/odcinek, tryb auto i tak dobiera ścieżki od nowa. Wznowienie = YAGNI.

---

## 4. Etap 3.1 — multi-pasek (BLOKER dla R11)

**Osobny etap PRZED etapem 3.** Wymaga własnych wymagań + planu.

**Problem:** `ProgressBarManager` obsługuje jeden task (`self.task: TaskID | None`).

**Zweryfikowane w kodzie:**
- `rich.Progress` **natywnie umie multi-task**. **Problem jest w naszym wrapperze, nie w rich.**
- Najgłębszy bloker: kolumny trzymają styl na sobie (`self.style_name`), nie na tasku → każdy pasek dostałby kolor ostatnio zaktualizowanego. Fix: styl do `task.fields`.
- `advance()` ma niezabezpieczony `+=` — dziś maskowane zewnętrznym lockiem w `installer.py`.
- `_BLOCK_BAR_COLORS` **nie istnieje** (nazwa z notatek 2.5 była zmyślona). Realnie: `DEFAULT_COLORS` + `ProgressBarBuilder.blocks()` (`█▌░`).

**Beneficjenci:** ekstrakcja (3), pobieracz (2.5 — dziś jeden zsumowany pasek), TTS (6).

**??? D6 — kształt:** (a) `ProgressBarManager` dostaje `add_task()` (breaking change dla 2 call-site'ów), czy (b) nowy `MultiProgressManager`, a obecny zostaje wrapperem 1-taskowym.

---

## 5. GŁÓWNE RYZYKO — co lektor przeczyta

### Pomiar bazowy (182 pliki, 1014 stylów, ręczny ground truth)

```
klasyfikator mm_avh:  95.86%  (972/1014)
  przeczytał znak:      40    (szum, nic nie ginie)
  ZGUBIŁ DIALOG:         2    (groźne)
```

### Hipoteza pozycyjna usera — zmierzona, odrzucona jako samodzielna reguła

User: *„jeśli styl jest inny niż główny i nie jest na górze/dole — to napis do wyświetlania"*. Sprawdzone na tym samym zbiorze:

```
reguła pozycyjna (\pos):  78.66%   przeczytał znak: 212   ZGUBIŁ DIALOG: 2
klasyfikator mm_avh:      95.86%   przeczytał znak:  40   ZGUBIŁ DIALOG: 2
```

**Intuicja trafna co do mechaniki** (potwierdzone na Fuji: `Furry` 251 linii dialogu — **zero `\pos`**; dialogi płyną z alignmentu stylu, typesetting jest przyklejany ręcznie). **Ale sama pozycja to za mało** — 5× więcej szumu. mm_avh już używa tego sygnału (`_RE_POS`, `_DLG_MAX_POS_RATIO`), tylko łączy go z innymi. **Wniosek: heurystyka nie jest zła, nie rozwalamy jej.**

### Dlaczego decyzja musi zapadać na linię

Plik `Fuji__Kimi_to_Koete_Koi_ni_Naru` odc. 3, styl `[Znaki]` — 1381 linii. Po odsianiu rysunków i collapse FBF zostaje **18**:

```
01:39   60x  'ZJEDZMY JUTRO RAZEM OBIAD'      ← SMS = dialog  → spoken
01:39   29x  'OKEJ'                           ← SMS = dialog  → spoken
02:12   54x  'JUTRO ZNOWU SOBIE POGADAMY.'    ← SMS = dialog  → spoken
─────────────────────────────────────────────────────────────────────
08:22   90x  'WYNIKI EGZAMINU Z 1 SEMESTRU'   ← tablica       → displayed
08:22   91x  'TSUNAGU HIDAKA'                 ← lista nazwisk → displayed
14:25   66x  'SALA PLASTYCZNA'                ← szyld         → displayed
08:22   90x  'ttttttttttttttttttt'            ← śmieć TS      → displayed
```

**W jednym stylu są obie rzeczy.** Ground truth mówi „Znaki = DIALOG" (chce SMS-ów), klasyfikator mówi „SIGN" (widzi 1381 animacji). **Żaden nie może mieć racji — pytanie jest źle postawione.** To nie błąd progów, to **błąd granulacji**. Te same 2 groźne pudła mają obie reguły (mm_avh i pozycyjna) — bo obie sądzą styl.

### Skala FBF

`[Znaki]` 1381 linii → 23 unikalne. `[TS]` 734 → **5** (`'FUJISUBS PRZEDSTAWIA'` ×364). Bez collapse lektor powtórzyłby to 364 razy.

Ustalenia z badania: **gotowca nie ma** (fansuberzy pliki *tworzą*, nie *konsumują*); **`pysubs2 --clean` nie zadziała** (keyuje na identycznym `(start,end)`, a FBF ma z definicji różne).

### Odwracalność — zmierzone, wynik przesądza model

```
                      eventy         style      linie z tagami
ASS→SRT→ASS:     2483 → 2181       8 → 1       2169 → 0      ✗
ASS→ASS (tekst): 2483 → 2483       8 → 8       2169 → 2169   ✓
```

SRT **nie ma pojęcia stylu** — 8 stylów Fuji staje się jednym `Default`, i tej informacji nie ma gdzie zapisać. **Dlatego SRT nie może być etapem pośrednim.** Nie jest to wada pysubs2 — to fizyka formatu.

⚠️ **Pułapka implementacyjna:** zapis przez `event.plaintext = ...` **kasuje tagi** (2169→297). Podmieniać trzeba tylko tekst *pomiędzy* blokami `{...}`.

---

## 6. Edge case'y

| # | Sytuacja | Zachowanie |
|---|----------|-----------|
| E1 | `workspace/` puste | Komunikat „wrzuć MKV", powrót do promptu. |
| E2 | MKV bez napisów | Ekstrakcja audio, ostrzeżenie, plik pominięty dalej. |
| E3 | MKV bez audio | Same napisy (audio potrzebne dopiero w 6/7). |
| E4 | Napisy już po polsku | Flaga `already_polish` → etap 4 pomija tłumaczenie. |
| E5 | MKV z SRT zamiast ASS | Obsługiwane (R2). `displayed` też jako SRT? ??? D4 |
| E6 | Brak `mkvextract.exe` | `ensure_binary` pobiera; brak sieci → błąd domenowy. |
| E7 | mkvextract exit != 0 | Błąd domenowy + **jasny komunikat co i gdzie** (R13). |
| E8 | exit == 0, brak pliku | Wykryte (N4) → jak E7. |
| E9 | Plik już wyekstrahowany | ??? D2 |
| E10 | Dwie ścieżki napisów tego samego kodeka | Kolizja nazw — ??? D2 |
| E11 | ASS bez eventów `Dialogue` | Wszystko → `spoken` (lepiej przeczytać za dużo niż zgubić). |
| E12 | Klasyfikator: zero `spoken` | Jak E11. |
| E13 | Uszkodzony ASS | Błąd domenowy, plik pominięty. |
| E14 | Ctrl+C | Przerywa czysto, częściowy plik kasowany. |
| E15 | Nazwa ze spacjami / PL znakami | Działa (oba MKV testowe). |
| E16 | 2+ MKV | Wszystkie (natsorted), błąd jednego nie ubija reszty. |
| E17 | Brak miejsca na dysku | `OSError` → błąd domenowy, nie crash. |
| E18 | Skasowany `workspace/` | Odtwarzany (N9). |
| E19 | Obok siebie `film.ass` i `film.srt` | ??? D2 — **wymaga reguły pierwszeństwa**, inaczej nadpiszemy ręczne poprawki usera. |
| E20 | Wiele napisów w tym samym czasie | **Znany problem, etap 6** — lektor musi je przeczytać po kolei. Etap 3 zachowuje timingi bez zmian. |

---

## 7. DECYZJE (`???`)

### D1 — Gdzie lądują pliki pośrednie i produkt?
mm_avh: `working_space/temp/`. Plan strategiczny mówi „obok MKV, **jak dziś**" — **to nieprawda**.
- **(a)** obok MKV w `workspace/`
- **(b)** pośrednie w `workspace/tmp/`, produkt (`displayed.ass`) obok MKV

**Rekomendacja: (b).** 1.4 GB audio nie ma zaśmiecać folderu wrzutowego, ale produkt ma być tam, gdzie user go szuka. Struktura folderów do dopracowania przez Fabla — nie trzymać się kurczowo nazw mm_avh.

### D2 — Cache ekstrakcji + zewnętrzne napisy (JEDNO pytanie)
Scenariusze usera: grupa wydała tylko ASS; MKV z torrenta bez napisów + własne napisy; podmiana napisów na lepsze; `film.ass` i `film.srt` obok siebie (E19).

mm_avh: plik >1 KB → skip. **Ślepy** — nie wie z której ścieżki; dwie ścieżki tego samego kodeka nadpisują się.
- **(a)** port 1:1 (znany problem)
- **(b)** cache + track id w nazwie
- **(c)** bez cache — ekstrakcja to sekundy, tłumaczenie i tak trwa dłużej
- **(d)** cache + „zewnętrzne wygrywają": plik obok MKV, którego mkvextract nie stworzył → źródło prawdy

**Rekomendacja: (c) + issue na (d).** Skoro cały odcinek to ~1 min, cache oszczędza sekundy i wprowadza ryzyko cichego użycia złego pliku. (d) to realny use-case, ale „skąd wiemy, że plik jest zewnętrzny" wymaga własnych wymagań.

### D3 — `UNCERTAIN`: czytać czy wyświetlać?
Dziś: `DIALOG + UNCERTAIN` → czytane („lepiej za dużo niż zgubić"). User proponuje odwrotnie.
- **(a)** jak dziś — czytaj przy niepewności
- **(b)** wyświetlaj przy niepewności — widz i tak zobaczy, nic nie ginie

**Brak rekomendacji — trzeba policzyć.** Jeśli `UNCERTAIN` to 2 linie/plik, (b) jest tanie. Jeśli 200 — (b) wycisza pół odcinka. **Do zmierzenia przed decyzją.**

### D4 — Format `displayed` gdy wejściem był SRT?
- **(a)** zawsze ASS (jednolity produkt)
- **(b)** taki jak wejście (SRT→SRT, ASS→ASS)

**Rekomendacja: (b)** — SRT nie ma czego stracić, konwersja na ASS niczego nie dodaje.

### D5 — O co pyta tryb manual?
Dziś pyta o style (8 pozycji). Po zmianie granulacji: o 18 linii? o 418? **Nie skaluje się.**
- **(a)** manual dalej pyta o style (zgrubny filtr), linie doprecyzowuje heurystyka
- **(b)** manual pyta o style, ale pokazuje ile linii i próbki
- **(c)** półautomat: pyta tylko o `UNCERTAIN`

**Rekomendacja: (b) teraz, (c) jako issue.** User: *„jak heurystyka będzie dobra, to nie ma sensu pytać"* — manual to wyjście awaryjne.

### D6 — Kształt multi-paska (3.1). Patrz §4.

### D7 — Preferencje językowe w `/settings`?
Dziś zaszyte (audio JP>EN>CH, napisy PL>EN).
**Rekomendacja: issue.** `track_selector` idzie 1:1 z testem regresji; konfiguracja od razu psuje parytet. User: „nieistotne czy teraz czy issue".

---

## 8. Definition of Done

- [ ] Enter przetwarza oba MKV testowe bez pytań (auto)
- [ ] **Oryginalny ASS nietknięty po całym przebiegu** (N1 — główne kryterium usera)
- [ ] **`displayed.ass`: tagi/style/timingi identyczne z oryginałem** (tylko tekst podmieniony)
- [ ] **Parytet: te same ID ścieżek co `track_selector`** (regresja)
- [ ] **Klasyfikator na 182 plikach: ≥95.86%** — automatyczny test regresji
- [ ] **Zero nowych `zgubił dialog`** poza 2 znanymi (Fuji 3-4)
- [ ] Rysunki (`\p1`) nie trafiają do lektora
- [ ] Collapse FBF: 1381 → 18 na pliku Fuji
- [ ] Determinizm: dwa przebiegi → identyczny bajt (N2)
- [ ] Pasek live przez `--gui-mode`; wiele plików = wiele pasków (wymaga 3.1)
- [ ] SRT na wejściu działa tak samo jak ASS (R2)
- [ ] Błąd = jasny komunikat co i gdzie (R13); nie przerywa reszty
- [ ] Żaden serwis nie woła `input()` ani `sys.exit()`
- [ ] pysubs2 przypięty
- [ ] Równoległość: sufit zmierzony
- [ ] Bramki: ruff + format + mypy + pytest zielone
- [ ] Smoke: oba MKV testowe + 3 pliki z `working_space/bugs/`

---

## USTALONE

**Model danych:**
- ✅ **ASS formatem roboczym, SRT tylko wejście/wyjście.** SRT był etapem pośrednim wyłącznie dlatego, że stare funkcje umiały tylko SRT.
- ✅ **`main` nie istnieje jako plik** — był stanem pośrednim, i tak kasowanym. Tłumaczenie i TTS są wewnątrz programu.
- ✅ **Jeden produkt: `displayed.ass`** — to co widz zobaczy, bo lektor tego nie czyta.
- ✅ **Nazwy: `spoken` / `displayed`** — opisują los linii, nie jej rodzaj. NIE `signs`/`narration` (przemycają styl).
- ✅ **Decyzja na LINIĘ, nie na styl** — inaczej przypadek Fuji jest nierozstrzygalny.
- ✅ **ASS→SRT→ASS nieodwracalny** (zmierzone). Odwracalność przez **zachowanie oryginału**.
- ✅ **`event.plaintext = ...` kasuje tagi** — podmieniać tekst między `{...}`.
- ✅ **Bez wznowienia po crashu** — ElevenBytes darmowy, ~1 min/odcinek. YAGNI.

**Heurystyka:**
- ✅ **Cel docelowy: 100% dokładności.** Nie teraz — etap 3 portuje as-is i dostarcza **pomiar** (regresja na 182 plikach). Wszystkie tropy zebrane niżej (§9), żeby nie przepadły. Iteracja z userem: issue #16.
- ✅ **95.86%, nie 99%** (zmierzone).
- ✅ **Reguła pozycyjna sama nie wystarcza** — 78.66%, 5× więcej szumu. Ale intuicja trafna: dialogi nie mają `\pos`.
- ✅ **2 groźne pudła to błąd granulacji, nie progów.**
- ✅ **Collapse FBF PRZED klasyfikacją** — klasyfikator dostaje 18 linii zamiast 1381.
- ⛔ **LLM do klasyfikacji: NIE jako bramkarz** — niedeterministyczny (koniec z N2), kosztuje, wolny. Ewentualna nisza: tylko `UNCERTAIN`, z kontekstem sąsiednich linii, default OFF, serwis llm i tak wchodzi w etapie 5. → issue #16, nie etap 3.

**Narzędzia i fakty:**
- ✅ **`--gui-mode` zamiast `read(1)`** (zweryfikowane na 2 MKV).
- ✅ **pysubs2 zostaje** — jedyna biblioteka ASS+SRT naraz, aktywna. Przypiąć wersję.
- ✅ **FBF: gotowca nie ma**, `--clean` nie pomoże. Filtr piszemy sami.
- ✅ **Multi-pasek = etap 3.1.** Problem w naszym wrapperze, nie w rich.
- ✅ **Chunker: nie ma nowszej wersji** — `scripts/tmp/` i `geminicli2api` identyczne (md5). Ma 2 bugi → issue.
- ✅ **Składanie w etapie 7** — wspólna binarka, zero wspólnego kodu. W planie zapisać wprost, gdzie leży plik odpowiedzialny za fazę 7.
- ✅ **Manual sekwencyjnie** — równoległość w mm_avh to wyścig o stdin.
- ✅ **Auto jest domyślne i docelowe** — manual to wyjście awaryjne.
- ✅ **Źródło prawdy = kod**, nie audyty.

---

## 9. TROPY DO 100% — bank pomysłów (NIE etap 3, patrz issue #16)

Cel: **100% dokładności podziału `spoken`/`displayed`.** Nie robimy tego teraz — ale wszystko, co dziś wyszło, jest tu zapisane, żeby nie odkrywać tego drugi raz. Kolejność = moja ocena stosunku zysku do kosztu.

**Baza wyjściowa:** 95.86% (972/1014), 40× przeczytał znak, 2× zgubił dialog.

### Trop 1 — decyzja na linię (JUŻ w etapie 3, R7)
Największy pojedynczy zysk i jedyny, który jest w zakresie etapu 3. Przypadek Fuji (SMS-y + szyldy w jednym stylu) jest **nierozstrzygalny** na poziomie stylu — oba znane groźne pudła stąd pochodzą. Po zmianie granulacji przestają istnieć jako klasa błędu.

### Trop 2 — czystsze wejście (JUŻ w etapie 3, R6)
Collapse FBF + odsiew rysunków: `1381 → 18` linii. Heurystyka dostaje uczciwy materiał **bez dotykania progów**. Nie wiadomo, ile z 40 „przeczytał znak" zniknie samo — **do zmierzenia po etapie 3**.

### Trop 3 — `\pos` jako sygnał, nie reguła (zmierzone)
Sama pozycja: **78.66%**, 212× szum. Ale mechanika jest prawdziwa: **dialogi nie mają `\pos`** (Fuji: `Furry` 251 linii dialogu, zero `\pos`) — płyną z alignmentu stylu; typesetting jest przyklejany ręcznie. mm_avh już to ma (`_RE_POS`, `_DLG_MAX_POS_RATIO`), pytanie brzmi czy waga jest dobra. **Tanie do przetestowania: przestroić próg, zmierzyć na 182 plikach.**

### Trop 4 — `UNCERTAIN` jako brama, nie kategoria (D3)
Dziś `UNCERTAIN` → czytane. Nie policzone, ile tego jest. Jeśli mało — to naturalne miejsce na drogie rozstrzyganie (człowiek albo LLM) bez kosztu na resztę. **Najpierw policzyć.**

### Trop 5 — progi jako nazwane stałe
`_classify_metrics` ma literały wpisane w ciele (`0.20`, `0.40`, `12`, `0.15`, `-0.25`, `-0.30`) obok nazwanych `Final`. Bez wyciągnięcia ich nie da się sensownie stroić. **Warunek wstępny dla każdego strojenia.**

### Trop 6 — LLM tylko na `UNCERTAIN` (⛔ NIE jako bramkarz)
Jako główny klasyfikator: **nie** — niedeterministyczny (zabija N2), kosztuje, wolny.
Jako rozjemca dla kilku niepewnych linii z kontekstem sąsiednich kwestii: **może**. Serwis llm i tak wchodzi w etapie 5, więc to nowy konsument istniejącej fasady, nie nowa maszyneria. Default OFF. **Zależy od Tropu 4** — bez pomiaru nie wiadomo, czy to 2 linie czy 200.

### Trop 7 — sygnały jeszcze niezbadane
- **alignment stylu** (`\an`/`Alignment` z `[V4+ Styles]`) — dialog to zwykle 2 (dół); nie sprawdzone jako osobny sygnał
- **czcionka** — typesetting często ma własny font (Fuji: `FOT-Matisse Pro Toaru EB PL`); dialog trzyma jeden font w całym pliku
- **kolor** (`\1c`) — j.w.
- **czas trwania linii** — szyld wisi sekundy, kwestia leci w tempie mowy
- **interpunkcja** — mm_avh ma `_RE_PUNCT`, ale to słaby sygnał dla PL/EN wielkich liter (`SALA PLASTYCZNA` vs `Chodźmy.`)
- **wielkość liter** — szyldy bywają CAPS-em (widoczne w danych: `WYNIKI EGZAMINU`, `SALA PLASTYCZNA`), dialog nie
- **layer** — typesetting bywa na wyższej warstwie

### Trop 8 — więcej danych
Zbiór ma 183 pliki / 20 packów ground truth. User zbiera bugi (`working_space/bugs/` — 3 pliki z nazwami wskazującymi sekundę). **Każdy nowy przypadek → do zbioru, nie do głowy.**

### Czego NIE robić
- ⛔ Nie stroić progów bez pomiaru na 182 plikach — „poprawka" bez regresji to zgadywanie.
- ⛔ Nie ufać nazwie stylu jako rozstrzygnięciu — Fuji dowodzi, że kłamie (`Znaki` = SMS-y = dialog, `TS` = prawdziwy typesetting).
- ⛔ Nie zastępować heurystyki LLM-em (Trop 6).

---

## Zasady usera (na cały projekt)

- **100% albo wcale** — zero kompromisów/półśrodków.
- Ja (agent) oceniam sensowność wymagań, nie user. User reaguje na moją ocenę.
