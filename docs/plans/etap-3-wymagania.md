# Etap 3 — ekstrakcja + refaktor napisów — WYMAGANIA

> Ten dokument to **wymagania**, nie plan i nie kod. Plan powstanie dopiero po zaakceptowaniu wymagań.
> Status: **DRAFT — do przeglądu przez usera.** Sekcja USTALONE = potwierdzone. `???` = wymaga decyzji.
> Referencje: kod `../mm_avh_working_space/` (ŹRÓDŁO PRAWDY), `external/docs/mkvtoolnix/`, zbiór testowy `../mm_avh_working_space/temp/{dataset_ass,ground_truth}/`.

## Cel

Enter w shellu zaczyna realnie pracować: MKV z `workspace/` → wyciągnięte ścieżki (audio + napisy) → napisy przerobione do SRT gotowego pod tłumaczenie, **z odsianym typesettingiem**, żeby lektor nie czytał szyldów i nie powtarzał 300× tej samej animowanej linii.

## Zasada nadrzędna

**mm_avh to punkt wyjścia, nie wyrocznia.** Kod działa, ale powstał metodą prób. Każde nieoczywiste rozwiązanie sprawdzamy w `external/docs/` albo pomiarem, zanim je przepiszemy. Dowody z tej sesji:
- `--gui-mode` czyni zbędnym 30 linii obejścia (`read(1)`),
- klasyfikator ma **95.86%**, nie deklarowane 99% (zmierzone na 182 plikach),
- audyt 03 **zmyślił** buga main/alt — w kodzie go nie ma.

> ⚠️ **Audyty w `docs/reference/audyt-mm-avh/` bywają błędne.** Przy wątpliwości: czytaj kod, nie audyt.

---

## 1. Wymagania funkcjonalne (co MA robić)

- **R1 — Enter uruchamia pipeline.** Pusta linia w shellu → discovery MKV w `workspace/` (natsorted) → per plik: identify → wybór ścieżek → ekstrakcja → refaktor napisów. Tryb (auto/manual) z ustawień, `/auto` i `/manual` przełączają.
- **R2 — Identyfikacja ścieżek.** `mkvmerge -J <plik>` → typowana lista ścieżek (id, typ, kodek, język, nazwa, flagi).
- **R3 — Auto-wybór ścieżek.** Scoring z `track_selector.py` przenoszony **1:1** (test regresji na 206 plikach). Preferencje językowe (dziś: audio JP > EN > CH, napisy PL > EN) — patrz D7.
- **R4 — Ekstrakcja z paskiem postępu.** `mkvextract --gui-mode tracks` → postęp jako `#GUI#progress N%`, **linia po linii**. NIE portujemy `read(1)`.
- **R5 — Tryb manual.** User wybiera ścieżki i style sam. Pytania w `cli/`, nie w serwisie. **Sekwencyjnie** — równoległość w mm_avh to wyścig o stdin (N wątków woła `input()` naraz).
- **R6 — Podział napisów ASS na main/alt.** Style dialogowe → main (czyta lektor), typesetting/piosenki → alt. Auto przez klasyfikator (port `style_classifier.py`), manual przez wybór stylów.
- **R7 — Odsiew typesettingu przed lektorem** (patrz §5 — to główne ryzyko etapu):
  - **R7a** — linie rysunkowe (`\p1`-`\p9`, komendy `m/n/l`) nigdy nie trafiają do SRT (TTS przeczytałby współrzędne),
  - **R7b** — **collapse FBF**: N linii o identycznym `plaintext` i ciągłych timingach → jedna linia (`start=min`, `end=max`),
  - **R7c** — czyste tagi pozycjonowania (`{\an8}`) usuwane z tekstu.
- **R8 — Konwersja ASS→SRT** przez pysubs2. **Plik `.ass` zostaje** — etap 7 (`srt_to_ass`) go potrzebuje.
- **R9 — Równoległość skalowana do maszyny.** Wiele plików naraz, liczba wątków z `cpu_count()` (jak mm_avh: `max(1, min(n_plików, cpu_count(), cap))`). **Sufit z pomiaru, nie z sufitu** — ekstrakcja to I/O, nie CPU; 6 wątków czytających z jednego dysku bywa wolniejsze niż 2. Zmierzyć na maszynie usera przed ustaleniem `cap`.
- **R10 — Multi-pasek postępu.** Wiele plików = wiele pasków naraz (jak `uv`), nie chaos i nie jeden zbiorczy. **Wymaga etapu 3.1** — patrz niżej.
- **R11 — Wejście SRT / TXT.** Gotowy SRT → `move_srt` (usuwa `{\anN}`). TXT → `txt_to_srt` (**zostaje** — side quest: szybkie audiobooki, patrz D4).
- **R12 — Błąd jednego pliku nie przerywa reszty.** Raport per plik (sukces/błąd/pominięty).

## 2. Wymagania niefunkcjonalne (jak MA się zachowywać)

- **N1 — Parytet zachowania z mm_avh** tam, gdzie mm_avh jest poprawny. Te same ścieżki wybrane; SRT o tej samej treści. **Wyjątki świadome** (R7 collapse FBF, R4 gui-mode) — to poprawki, nie regresje, i mają być udokumentowane.
- **N2 — pysubl2 przypięty.** `ass_to_srt` w mm_avh woła `to_string(format_='srt')` — całe strippowanie tagów robi biblioteka, nie nasz kod. Wersja pysubs2 = warunek powtarzalności. (Zbadane: pysubs2 1.8.1 zostaje, alternatywy albo martwe (`ass-parser` 2021), albo bez SRT.)
- **N3 — Zero `sys.exit()` / `input()` w serwisie.** Serwis rzuca błąd domenowy, decyzje podejmuje CLI.
- **N4 — Walidacja wyniku, nie tylko exit code.** mkvextract potrafi zwrócić 0 i nie zapisać pliku (zweryfikowane: ścieżka POSIX podana Windowsowemu .exe). Sprawdzać istnienie i rozmiar.
- **N5 — Domeny bez rejestru.** `extraction` i `subtitles` nie mają `engines/` — nie ma czego wybierać.
- **N6 — Ścieżki binarek z `platform/binaries.py`** przez `ensure_binary(Binary.MKVEXTRACT)` (leniwe, etap 2.5).
- **N7 — Testowalność bez MKV.** Wybór ścieżek i klasyfikacja testowalne na zrzutach JSON / plikach ASS ze zbioru testowego. Testy na realnym MKV osobno.
- **N8 — Progress nie koliduje z promptem.** Rich Live startuje po zakończeniu `session.prompt()`.
- **N9 — Foldery odtwarzalne.** Brakujące `workspace/`, `tmp/`, `external/` tworzone automatycznie (user może skasować cały folder — ma się odbudować).

---

## 3. Etap 3.1 — multi-pasek postępu (BLOKER dla R10)

**To osobny etap PRZED etapem 3.** Wymaga własnych wymagań + planu.

**Problem:** `ProgressBarManager` (`utils/rich_console/progress/manager.py`) obsługuje **jeden task** (`self.task: TaskID | None`, `add_task` wołany raz w `__enter__`). Przy wielu plikach nie da się pokazać wielu pasków.

**Ustalenia (zweryfikowane w kodzie):**
- `rich.Progress` **natywnie umie multi-task** (`add_task` → `TaskID`, słownik tasków, thread-safe). **Problem jest w naszym wrapperze, nie w rich.**
- Najgłębszy bloker: kolumny trzymają styl na sobie (`self.style_name`), nie na tasku → przy wielu paskach każdy dostałby kolor ostatnio zaktualizowanego. Fix: styl do `task.fields`.
- `advance()` robi niezabezpieczony `last_successful_progress += amount` — dziś maskowane zewnętrznym lockiem w `installer.py`.
- `_BLOCK_BAR_COLORS` **nie istnieje** (nazwa z notatek 2.5 była zmyślona). Realnie: `DEFAULT_COLORS` (mapa próg→kolory) + `ProgressBarBuilder.blocks()` rysujący `█▌░`.

**Beneficjenci:** ekstrakcja (etap 3), pobieracz binarek (2.5 — dziś pokazuje jeden zsumowany pasek z ręcznym lockiem), TTS (6).

**Zasada:** rozszerzamy `utils/rich_console` **świadomie**, zero duplikowania stylu do modułów (odrzucone w 2.5).

**??? D8 — kształt rozszerzenia:** (a) `ProgressBarManager` dostaje `add_task()` i sygnatury per-task (breaking change dla 2 call-site'ów), czy (b) nowy `MultiProgressManager`, a obecny zostaje cienkim wrapperem 1-taskowym (wsteczna kompatybilność).

---

## 4. Skąd bierzemy kod

| Stary plik | Linie | Dokąd | Jak |
|---|---|---|---|
| `modules/track_selector.py` | 248 | `extraction/tracks.py` | **1:1** |
| `modules/style_classifier.py` | 294 | `subtitles/styles.py` | port + R7b (collapse FBF) |
| `modules/mkvtoolnix.py` | 496 | `extraction/service.py` | przepisanie (gui-mode, bez sys.exit) |
| `modules/subtitle.py` | 514 | `subtitles/service.py` + `cleanup.py` | przepisanie |
| `start.py` (orkiestracja) | — | `pipeline/runner.py` | przepisanie |
| `scripts/tmp/text_chunker.py` | 151 | `utils/text_chunker.py` | dla R11 (TXT), patrz D4 |

**Uwaga o chunkerze:** wersja w `scripts/tmp/` i ta w `geminicli2api` są **identyczne** (md5 `9b5dd1c2...`) — nie ma nowszej. Ma dwa realne bugi: nieskończona pętla w `WordBreaker.breakPhrase` przy jednym słowie; detekcja skrótów („Mr.") nigdy nie działa (test podciągu na stringu regexa).

---

## 5. GŁÓWNE RYZYKO — lektor czyta to, czego nie powinien

**Zmierzone na zbiorze testowym** (182 pliki, 1014 stylów, ground truth ręcznie oznaczony):

```
skuteczność klasyfikatora:  95.86%   (972/1014)
pudła:                      42
```

Rozkład pudeł jest **asymetryczny** i to determinuje priorytety:

| Kierunek | Ile | Skutek | Waga |
|---|---|---|---|
| ZNAK/PIOSENKA → czytane | 40 | lektor czyta szyld — szum, nic nie ginie | do poprawy |
| **DIALOG → pominięty** | **2** | **lektor gubi kwestię** | **groźne** |

**Te dwa groźne przypadki** (`Fuji__Kimi_to_Koete_Koi_ni_Naru` odc. 3 i 4) są pouczające — zbadane w pliku:

```
[Znaki]  1381 linii →   23 unikalne teksty   (58x redundancji)
[TS]      734 linie →    5 unikalnych        (147x!)
```

Styl `Znaki` zawiera **dwie różne rzeczy naraz**: FBF typesetting (animacje `\pos` co 40 ms) ORAZ SMS-y (`'ZJEDZMY JUTRO RAZEM OBIAD'`), które fabularnie są dialogiem. Ground truth mówi DIALOG (chce SMS-y), klasyfikator mówi SIGN (widzi 1381 animowanych linii). **Oba mają rację o czym innym.**

**To nie jest błąd progów — to błąd granulacji.** Decyzja zapada na *styl*, a materiał jest mieszany na poziomie *linii*. Strojenie progów tego nie naprawi.

**Konsekwencja projektowa: collapse FBF (R7b) + odsiew rysunków (R7a) muszą działać PRZED klasyfikacją**, nie po. Po usunięciu 1376 z 1381 linii ten styl wygląda zupełnie inaczej i klasyfikator dostaje uczciwe wejście.

Znalezione przy okazji w tym samym stylu (dowód na R7a):
- `'m -401.48 -73.79 l -400.4 -13.37...'` ×100 — komendy rysowania wektorowego. **TTS przeczytałby współrzędne na głos.**
- `'ttttttttttttttttttttttttttttt'` ×90 — artefakt typesettingu, nie znaczy nic.
- `'FUJISUBS PRZEDSTAWIA'` ×364 — bez collapse lektor powtórzyłby to 364 razy.

**Zjawisko „300× ta sama linia" jest realne i ma nazwę: FBF typesetting** (frame-by-frame). Skrypty Aegisuba animują `\pos` klatka po klatce — tekst **musi** być identyczny. Ustalenia z badania:
- **gotowca nie ma** — fansuberzy nie mają klasyfikatora sign-vs-dialog, bo pliki *tworzą*, nie *konsumują*. Filtr piszemy sami.
- **pysubs2 `--clean` NIE zadziała** — jego dedup wymaga identycznego `(start,end)`, a FBF ma z definicji różne timingi. Zero linii usuniętych.
- `dedup_animation` w mm_avh (próg ≥5 powtórzeń + mediana <2000 ms) liczy tylko metrykę do klasyfikacji — **nie czyści SRT**.
- Oba MKV testowe usera **nie mają FBF** (shisha: 418 eventów, zero powtórzeń; SubsPlease: 353, max „Morning." 5× z medianą 75 s = prawdziwy dialog). Zbiór 182 plików jest potrzebny właśnie dlatego.

### Odwracalność — ZMIERZONE, wynik negatywny

User postawił kryterium: *„proces powinien być odwracalny — nawet jeśli heurystyka się pomyli, da się cofnąć"*. Słuszne, ale **nie przez round-trip**. Pomiar (pysubs2 1.8.1, prawdziwe pliki):

```
                  eventy         style        linie z tagami
shisha:      419 →  418        6 → 1         112 → 70
SubsPlease:  353 →  353       14 → 1          10 → 53
Fuji (FBF): 2483 → 2181        8 → 1        2169 → 0      (+297 rysunków)
```

**ASS→SRT→ASS jest nieodwracalny i to fizyka formatu, nie wada pysubs2:**
- **style zawsze → 1** — SRT nie ma pojęcia stylu; 8 stylów Fuji staje się jednym `Default`. Informacji nie da się odtworzyć, bo nie ma jej gdzie zapisać.
- **tagi → 0** — `\pos`, kolory, czcionki znikają; bez nich typesetting to goły tekst na środku.
- **eventy maleją** — SRT nie ma warstw, nakładające się linie się sklejają (2483 → 2181).

**Ale: SRT stabilny po 2. cyklu = TAK we wszystkich trzech.** Konwersja jest deterministyczna → parytet bit-w-bit ze starym kodem jest osiągalny mimo stratności.

**Jak realizujemy odwracalność (kontrakt R8):** oryginalny `.ass` **zostaje na dysku** jako źródło prawdy. SRT to wyłącznie *ekstrakt tekstu* dla lektora i tłumacza, nigdy etap pośredni do rekonstrukcji. Etap 7 bierze **oryginalny ASS** i wstrzykuje przetłumaczone linie mapując po `(start,end)` — mm_avh już tak robi i to jedna z jego dobrych decyzji. To czyni pomyłkę heurystyki odwracalną: zły podział main/alt nie niszczy pliku, bo źródło leży nietknięte.

---

## 6. Edge case'y

| # | Sytuacja | Zachowanie |
|---|----------|-----------|
| E1 | `workspace/` puste | Komunikat „wrzuć MKV", powrót do promptu. Nie błąd. |
| E2 | MKV bez napisów | Ekstrakcja audio, ostrzeżenie, plik pominięty dalej. |
| E3 | MKV bez audio | Ekstrakcja samych napisów (audio potrzebne dopiero w 6/7). |
| E4 | Napisy już po polsku | Flaga `already_polish` → etap 4 pomija tłumaczenie. |
| E5 | Brak `mkvextract.exe` | `ensure_binary` pobiera. Brak sieci → błąd domenowy, nie traceback. |
| E6 | mkvextract exit != 0 | Błąd domenowy, plik pominięty, reszta leci. |
| E7 | exit == 0, ale brak pliku | Wykryte (N4) → jak E6. |
| E8 | Plik już wyekstrahowany | ??? D3 |
| E9 | Dwie ścieżki napisów tego samego kodeka | Kolizja nazw — ??? D3 |
| E10 | ASS bez eventów `Dialogue` | Całość → main (lepiej przeczytać za dużo niż zgubić). |
| E11 | Klasyfikator nie znajduje dialogu | Jak E10. |
| E12 | Uszkodzony ASS | Błąd domenowy, plik pominięty. |
| E13 | Ctrl+C w trakcie | Przerywa czysto, częściowy plik kasowany, powrót do promptu. |
| E14 | Nazwa ze spacjami / PL znakami | Działa (oba MKV testowe mają nawiasy i spacje). |
| E15 | 2+ MKV | Wszystkie (natsorted), błąd jednego nie ubija reszty. |
| E16 | Brak miejsca na dysku | `OSError` → błąd domenowy, nie crash. |
| E17 | Zewnętrzne napisy obok MKV | ??? D3 — to samo pytanie co cache |
| E18 | Skasowany `workspace/` | Odtwarzany automatycznie (N9). |
| E19 | Obok siebie `film.ass` i `film.srt` (user dopisał własny SRT) | ??? D3 — **wymaga jawnej reguły pierwszeństwa**, inaczej etap 7 nadpisze ręczne poprawki usera. Dziś w mm_avh: niezdefiniowane. |

---

## 7. DECYZJE DO PODJĘCIA (`???`)

### D1 — Gdzie lądują wyekstrahowane pliki?
mm_avh: `working_space/temp/`. Plan strategiczny mówi „obok MKV, **jak dziś**" — **to nieprawda**, dziś są w `temp/`.
- **(a)** obok MKV w `workspace/` — user widzi co się dzieje, ale 1.4 GB audio zaśmieca folder wrzutowy
- **(b)** w `workspace/tmp/` — jak mm_avh, workspace czysty

**Rekomendacja: (b).**

### D2 — Podfoldery `main_subs/` + `alt_subs/`?
- **(a)** jak mm_avh — **rekomendacja**, zero powodu do zmiany
- **(b)** płasko z sufiksem (`<nazwa>.main.ass`)

### D3 — Cache ekstrakcji + zewnętrzne napisy (JEDNO pytanie, nie dwa)
Twoje scenariusze: grupa wydała tylko ASS; masz MKV z torrenta bez napisów i dorzucasz własne; chcesz podmienić napisy na lepsze.

mm_avh: plik istnieje i >1 KB → skip. **Ślepy**: nie wie z której ścieżki pochodzi; dwie ścieżki tego samego kodeka nadpisują się (nazwa bez track id).

- **(a)** port 1:1 (parytet, znany problem)
- **(b)** cache + track id w nazwie (poprawne, łamie parytet nazw)
- **(c)** bez cache (zawsze poprawnie, wolno)
- **(d)** cache + jawne „zewnętrzne wygrywają": plik `<nazwa>.ass` obok MKV, którego mkvextract nie stworzył → traktowany jako źródło, ekstrakcja napisów pomijana

**Rekomendacja: (a) na teraz + issue na (d).** Parytet to DoD tego etapu. Ale (d) to realny use-case (Twoje trzy scenariusze) — wymaga własnych wymagań, bo „skąd wiemy, że plik jest zewnętrzny" to nietrywialne pytanie.

### D4 — TXT → SRT
**Zostaje** (Twoja decyzja: szybkie audiobooki). W mm_avh ta ścieżka jest **zepsuta end-to-end**: `txt_to_srt` zapisuje SRT do `temp/`, ale pętla iteruje po snapshocie zrobionym **przed** nią → plik nigdy nie zostaje podniesiony w tym samym przebiegu.
- **(a)** portujemy naprawione, chunker as-is
- **(b)** portujemy naprawione + naprawa 2 bugów chunkera (side quest)

**Rekomendacja: (a) teraz, (b) jako issue** — chunker nie blokuje etapu 3.

### D5 — `srt_to_ass` w etapie 3 czy 7?
- **(a)** etap 3 — domena napisów, jedna domena = jeden port; **plus: round-trip da się przetestować od razu** (Twój argument: „czy umiemy ASS→SRT→ASS bez zmiany bitu")
- **(b)** etap 7

**Rekomendacja: (a).** Sprzężenie z 7 jest przez artefakt na dysku (`.ass` zostawiony w `alt_subs`), więc etap 3 i tak musi o nim wiedzieć. **W planie zapisać wprost, że użycie tej funkcji to faza 7.**

### D6 — Wejście inne niż MKV (mp4 + zewnętrzny SRT)?
Twój scenariusz: „mam mp4 i własny SRT, chcę lektora".
- **(a)** nie teraz — etap 3 to „MKV → napisy", mp4 to osobny use-case
- **(b)** teraz

**Rekomendacja: (a) + issue.** Wymaga rozstrzygnięcia gdzie ląduje wynik (Twoje „nie wiem gdzie upuszczę go XD") — czyli to nie jest gotowe wymaganie.

### D7 — Preferencje językowe w `/settings`?
Dziś zaszyte w `track_selector` (audio JP>EN>CH, napisy PL>EN). Twoje: „u nas PL jest ważny, ale ktoś może chcieć inaczej".
- **(a)** issue — etap 3 portuje 1:1, panel później
- **(b)** teraz w `/settings`

**Rekomendacja: (a).** `track_selector` idzie 1:1 z testem regresji; dokładanie konfiguracji od razu psuje parytet. Twoje słowa: „dla mnie to nieistotne czy to robimy czy dajemy issue".

### D8 — Kształt multi-paska (etap 3.1)
Patrz §3.

---

## 8. Definition of Done

- [ ] Enter przetwarza oba MKV testowe bez pytań (auto)
- [ ] Manual pyta o ścieżki i style, **sekwencyjnie**
- [ ] **Parytet: te same ID ścieżek co stary `track_selector`** (regresja na zrzutach)
- [ ] **Parytet: SRT o tej samej treści co stary kod** (golden-file; różnice tylko tam, gdzie R7 świadomie poprawia)
- [ ] **Klasyfikator na zbiorze 182 plików: ≥95.86%** (nie gorzej niż mm_avh) — automatyczny test regresji
- [ ] **Zero `DIALOG → pominięty`** poza 2 znanymi (Fuji odc. 3-4) — nowa regresja tego typu = czerwony test
- [ ] Linie rysunkowe (`\p1`) nie trafiają do SRT
- [ ] Collapse FBF: N identycznych linii → 1 (test na pliku ze zbioru z realnym FBF)
- [ ] Pasek postępu live przez `--gui-mode`, wiele plików = wiele pasków (wymaga 3.1)
- [ ] **Odwracalność: oryginalny `.ass` nietknięty na dysku po całym przebiegu** — zły podział main/alt nie niszczy pliku, da się cofnąć (główne kryterium usera)
- [ ] `.ass` zostaje w `alt_subs/` (kontrakt z etapem 7)
- [ ] Timingi i kolejność eventów nietknięte (kontrakt `(start,end)` dla 7)
- [ ] SRT deterministyczny: dwa przebiegi na tym samym ASS → identyczny bajt w bajt
- [ ] Napisy `lang=pol` → flaga `already_polish`
- [ ] Błąd jednego pliku nie przerywa drugiego; raport per plik
- [ ] Żaden serwis nie woła `input()` ani `sys.exit()`
- [ ] pysubs2 przypięty
- [ ] Równoległość: sufit zmierzony, nie zgadnięty
- [ ] Bramki: ruff + format + mypy + pytest zielone
- [ ] Smoke na żywo: oba MKV testowe + 3 pliki z `working_space/bugs/`

---

## USTALONE

- ✅ **Bug main/alt NIE ISTNIEJE** — audyt zmyślił, kod zweryfikowany.
- ✅ **`--gui-mode` zamiast `read(1)`** — zweryfikowane na obu MKV: wynik bit-w-bit identyczny, ~30 linii obejścia znika.
- ✅ **Klasyfikator: 95.86%** (zmierzone, 182 pliki). Deklarowane 99% się nie potwierdza.
- ✅ **Heurystyka klasyfikatora NIE jest przedmiotem etapu 3.** Portujemy as-is, bez strojenia. To osobny subtask do iteracji z userem (issue #16) — user ocenia wyniki na własnych danych. Etap 3 dostarcza tylko **pomiar** (test regresji na 182 plikach), żeby było wiadomo, od czego się odbijamy.
- ✅ **Collapse FBF PRZED klasyfikacją, nie po** — styl `Znaki` (Fuji) miesza typesetting z SMS-ami; po odsianiu 1376 z 1381 linii klasyfikator dostaje uczciwe wejście. To zmienia kolejność kroków, nie progi.
- ✅ **2 groźne pudła to błąd granulacji, nie progów** — decyzja na styl, materiał mieszany na poziomie linii.
- ✅ **FBF typesetting to realne zjawisko**, gotowca nie ma, `pysubs2 --clean` nie pomoże. Filtr piszemy sami. Skala zmierzona: Fuji ma 1381 linii `[Znaki]` na 23 unikalne teksty; `'FUJISUBS PRZEDSTAWIA'` ×364.
- ✅ **pysubs2 zostaje** — jedyna biblioteka ASS+SRT naraz, aktywna. Alternatywy martwe lub bez SRT.
- ✅ **ASS→SRT→ASS jest NIEODWRACALNY** (zmierzone: style→1, tagi→0, eventy 2483→2181). To fizyka formatu, nie wada biblioteki. **Odwracalność realizujemy przez zachowanie oryginalnego `.ass`**, nie przez wierność konwersji.
- ✅ **Konwersja jest deterministyczna** (SRT stabilny po 2. cyklu) → parytet bit-w-bit ze starym kodem osiągalny mimo stratności.
- ✅ **Multi-pasek = etap 3.1**, przed etapem 3. Problem w naszym wrapperze, nie w rich.
- ✅ **Chunker: nie ma nowszej wersji** — `scripts/tmp/` i `geminicli2api` identyczne (md5).
- ✅ **Składanie zostaje w etapie 7** — wspólna binarka, zero wspólnego kodu.
- ✅ **Heurystyki portujemy gotowe** — `track_selector` 1:1. Dopracowanie = issue #16.
- ✅ **Manual sekwencyjnie** — równoległość w mm_avh to wyścig o stdin.
- ✅ **Równoległość skalowana do CPU**, sufit z pomiaru.
- ✅ **Źródło prawdy = kod**, nie audyty.
- ✅ **Struktura folderów `external/` / `workspace/`** — do rozstrzygnięcia przez Fabla w planie; nie trzymać się kurczowo starych nazw, ale trzymać konwencję nazewniczą projektu.

## Zasady usera (na cały projekt)

- **100% albo wcale** — zero kompromisów/półśrodków.
- Ja (agent) oceniam sensowność wymagań, nie user. User reaguje na moją ocenę.
