**ODRZUCAM** (jeden nowy bloker; poprawka mieści się w jednym zdaniu planu)

Runda 2, recenzent `claude`, HEAD `c3cf292`. Sprawdzone: plan v2, `visual-quality.md` v2.1, aneksy v4, `split-and-styles.md`, `model-v32.md` i kod w worktree. Tryb: tylko odczyt, bez pytest.

## Blokery rundy 1

1. Replay — **tak** (plan:317, 319): `pair_events`, tekst bez starych `\N`, adapter baseline jako pierwszy commit, C wyłączone z dowodu replay. Drobne: gate mówi „bajtowo identyczny dla sparowanych par”, a niesparowane zdarzenia leżą w tych samych plikach. Trzeba porównywać po zdarzeniach albo wymagać, żeby niesparowane dawały ten sam wynik w obu ścieżkach.
2. U4↔U5 — **tak**: `split_lines` (plan:269), aneks A.4, U4 dopiero w fali C.
3. Czcionki w writerze — **tak**: D3 (plan:78), `FontSources` i `layout_translated` (plan:215, 229). `task_id` nie zależy od wejść (`planner.py:1799`), więc opcjonalne wejście kontenera nie unieważnia gotowych tłumaczeń. Drobne: F0b powinno wskazać, kto zbiera `FontSources.system` (katalogi czcionek Windows).
4. Sprzeczności z visual-quality — **tak**: aneks LB pkt 3 (07 → 2 wiersze, `model-v32.md:22`) i aneks B pkt 5 (kopie w różnych stylach czytane raz).
5. Wymaganie 2 — **tak**, na podstawie zapisanej decyzji właściciela (plan:20; REPORTED) i aneksów wniesionych przed akceptacją. D12 pokrywa LB §5, E1–E9 i §12.
6. Limit 2 instancji — **tak**, jako wyjątek właściciela (plan:20; REPORTED). `AGENTS.md` się nie zmienia, więc wyjątek warto zapisać w outcome albo w session-logu.
7. `\r` i identyczność bajtowa — **tak**: D7 klonuje styl (plan:82), visual-quality §5.1.

## WAŻNE rundy 1

Zamknięte (**tak**): kontrakty (`Rect`, `LayoutReport`, `RenderProfile.styles`, `fit_signs(source, target, signs)`, dwupoziomowe `FontIndex.build`), D3 bez źródła i skrypty TTS (aneks B pkt 6), D8 (teraz D10), ramka = `\clip`, krój zastępczy Arial (visual-quality §9), `split-and-styles.md`, 05/06 (`model-v32.md:52-53`). **Częściowo:** zakresy fal (nowe uwagi niżej) i cecha „jeden wiersz, gdy się mieści”, która nadal działa tylko przez remis „mniej cięć”. To drugie nie blokuje. Kolejność fal jest zgodna z zależnościami. Minimalne B spełnia §6.1–6.5 z dowodem H2 (120/120, regresja 0,9888). Minimalne C spełnia §7.1–7.3 i 7.6, a 7.4 jest jawnie odłożone (§7.7).

## Nowe w v2

- [BLOKER] Aneks C pkt 2 jest niewykonalny w obecnym kontrakcie. „`\i0`/`\b0` otwiera zakres, gdy styl bazowy ma ten atrybut” wymaga znajomości stylu. `marked_text(text)` i `replace_visible_text(text, new)` odtwarzają granice z samego tekstu (`text.py:132-135`, `:334`). Plan zamraża ich sygnatury (plan:286), a U3 ma w zakresie tylko `text.py` i biegnie równolegle z F0b, który przepisuje wywołania (`translation_handler.py:420, 430`, `layout_translated`). — Poprawka: opcjonalny argument `style: SSAStyle | None = None` w obu funkcjach (domyślnie dzisiejsze zachowanie). F0b przekazuje styl zdarzenia we wszystkich wywołaniach, a U3 tylko z niego korzysta.
- [WAŻNE] U1b ma przenieść budowę `FontIndex` z `FontSources` do `layout_translated` (plan:325), ale `service.py` nie należy do jego zakresu. Jednocześnie U2 edytuje ten plik. — Poprawka: zrobić to połączenie w F0b, bo U1a jest już wtedy scalone i `FontIndex.build` istnieje.
- [WAŻNE] U6 musi przekazać `DialogueFont` do handlerów TRANSLATE i NORMALIZE, ale nie ma w zakresie `translation_handler.py` ani `subtitle_handler.py`. Drugi z tych plików ma w tej samej fali U5 (plan:333-334). — Poprawka: F0b przeprowadza `dialogue_font=None` i `limits` przez konstruktory handlerów z `runtime.py`, a U6 tylko uzupełnia wartość w runtime.
- [WAŻNE] Kontrakt `translations: Mapping[int, str]` (plan:231) nie mówi, kto przenosi przekład serii na kopie. Dziś robi to writer przez `spoken_by_key` (`service.py:396-424`), a U2 dodaje „mapowanie w writerze” dla kopii między stylami (plan:326). — Poprawka: kluczami są pierwsze zdarzenie każdej `SpokenLine` i zdarzenia displayed, a `layout_translated` sam przenosi przekład na kopie.
- [DROBNE] `write_translated_spoken/displayed` mają jedynego konsumenta w `LegacySubtitleAdapter` (`subtitle_handler.py:97-98`), którego usuwa F0a. Lepiej dopisać je do D10, niż utrzymywać z nową sygnaturą (plan:234).
- [DROBNE] `visual-quality.md` 2.1.7 nie ma wyjątku dla klonu, choć ma go plan (plan:126). Warunek końcowy plan:24 obejmuje też odłożone 7.4. — Poprawka: wyłączyć punkty odłożone.

## Ocena

Wersja v2 rzetelnie zamyka wszystkie blokery rundy 1, a kontrakty F0b dają jedną granicę do wymiany wnętrz. Słabszy jest już tylko przydział plików między jednostkami równoległymi (styl w C, połączenia w `service.py` i w handlerach). Wystarczy przenieść te połączenia do F0b.
