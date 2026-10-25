---
kind: review
status: pass-with-findings
reviewed-state: docs/work/17-content-check (current-state.md, specification.md, plan.md) na main @ 4365a51
date: 2026-10-25
---

# Review: plan kontroli zawartości po pobraniu (E4), runda 1

## Zakres

- przedmiot: `current-state.md`, `specification.md`, `plan.md` w tym katalogu;
- baseline: `main` @ `4365a51`;
- authority: `docs/work/08-acquisition/specification.md` (U-07, U-08, R-07, I-08), decyzje K-09/K-10, plan A1 §5.12, plan przepływu §3.3, `AGENTS.md` (root i scoped);
- ryzyka: fałszywe odrzucenie dobrego wydania, regresja plannera, zła trwałość stanu, praca sieciowa na wątku ownera, scope creep;
- poza review: wykonanie kodu (nie istnieje), H4.

**Ograniczenie niezależności:** review pisał autor planu w osobnym przebiegu, bez subagentów (zakaz zlecenia). Reguła krzyżowa z `AGENTS.md` wymaga jeszcze przeglądu innym modelem przed akceptacją właściciela.

## Werdykt

**Status:** PASS WITH FINDINGS — poważne findingi poprawiono w artefaktach; zostają decyzje właściciela D1–D8 i jedna luka dowodowa (F0).

**Najważniejszy powód:** projekt opiera się na zmierzonym rozdzieleniu tempa zdarzeń (790 ścieżek), ale pole, które aplikacja widzi w `mkvmerge -J`, nie zostało porównane z tym pomiarem. Plan stawia to jako bramkę F0 z warunkiem stopu.

## Findings

### Poważne (poprawione)

#### P1. Fake sondy w testach zwracają katalog bez napisów

- miejsce: `tests/application/test_subscription_attempts.py:80`, `test_subscription_scenarios.py` (`_Probe`, `_Snapshots`), `tests/application/fakes.py:97`;
- dowód: `MediaCatalog(path, MKV, 1_440_000_000, (_VIDEO_TRACK,))` — tylko wideo;
- wpływ: po E4 każda próba w tych testach dostałaby werdykt `brak` i odrzucenie; dziesiątki fałszywie czerwonych testów albo pokusa osłabienia asercji;
- poprawka: wpis w Impact scan, krok F2.4 (domyślny katalog fake'a z tekstową ścieżką dialogową), test negatywny w F2 i zakaz zmiany fake'a ukrywającej regresję.

#### P2. `num_index_entries` może wynosić 0 bez cue dla napisów

- miejsce: `services/extraction/service.py:128-141` czyta `num_index_entries`, który zależy od cue zapisanych przez muxer;
- dowód: fixture `tests/data/mushoku-tensei-s3-03.json` ma 0 dla audio; dla napisów wartość zależy od narzędzia; pomiar progów użył `NUMBER_OF_FRAMES` z `ffprobe`;
- wpływ: zero potraktowane jako liczba dałoby tempo 0 → szyldy → odrzucenie dobrego wydania;
- poprawka: reguła traktuje `0` i brak jak „nieznane” (zapas D1), F0 porównuje pola na 52 plikach i wybiera pole zgodne ze 100% ścieżek albo zatrzymuje pracę.

#### P3. Tryb `record_only` gasi odrzucenia

- miejsce: `download_verification.py:134-139`, `automation.py:6723`;
- wpływ: wpięcie napisów w `verify()` dałoby `inconclusive` zamiast odrzucenia;
- poprawka: osobny powód `NO_DIALOGUE_SUBTITLES` poza `verify()`, odrzucenie niezależne od trybu (wymaganie 8, F2.2); wariant „napisy w `verify()`” przeniesiony do „Odrzucone”.

#### P4. Pobranie ręczne nie może dziś nieść wyniku kontroli

- miejsce: `control.py:520-522`;
- wpływ: bez zmiany inwariantu odrzucenie ręczne nie byłoby trwałe, a sonda biegłaby ponownie w każdej rundzie transferów; problem nie byłby widoczny po restarcie (I-08);
- poprawka: zmiana inwariantu, schemat 6 z migracją i kopią (D6), testy `test_watch_state.py`.

#### P5. Etykieta problemu nie mieściła się w kolumnie Stan

- miejsce: pierwsza wersja planu proponowała „Brak napisów · wybierz inne wydanie”; strażnik `tests/cli/test_anime_episodes.py:2401` (`_EPISODE_STATUS_WIDTH`);
- poprawka: Stan „Brak napisów”, w notce istniejący `_REPEAT_HINT`; testy oparte na istniejących strażnikach zamiast wymyślonego nowego.

#### P6. Pauza globalna nie była rozstrzygnięta dla zamiany ręcznej

- miejsce: reguła pauzy w `anishift/application/AGENTS.md` („pracy użytkownika nie odrzuca”, „sam priorytet USER świeżego pliku nie zwalnia z pauzy”);
- wpływ: wykonawca musiałby sam wybrać, czy automatyczna zamiana to praca użytkownika;
- poprawka: decyzja właściciela D8 z rekomendacją, krok F3.7, test pauzy.

### Mniejsze (poprawione)

- **M1.** Wpis rejestru dla kontroli ręcznej: `_record_check` wychodzi przy braku `subscription_id` (`automation.py:6768`); dodano F3.6 i test.
- **M2.** Typ werdyktu jako `str` → alias `Literal` w `selection.py`, plus osobna flaga niepewności.
- **M3.** Plik testów reguły był podany jako „albo-albo”; ustalono `tests/application/test_subtitle_roles.py`.
- **M4.** Inwariant o plikach wrzucanych ręcznie sugerował brak zmian, choć zmienia się definicja szyldów; doprecyzowano.

### Mniejsze (otwarte, nie blokują)

- **M5.** Progi D1 pochodzą z 52 plików czterech źródeł; brak wydań fansubowych ze ścieżką `Signs & Songs`. Reakcja w planie: wpis niepewności w rejestrze, przypadek regresyjny przy pierwszym zgłoszeniu, zmiana progu tylko decyzją właściciela.
- **M6.** Towarzysz `ass`/`srt` liczony jako dialog bez pomiaru; może to być plik szyldów. Akceptowalne, bo planner i tak użyje sidecara, a odrzucenie byłoby gorszą pomyłką; zapisane w specyfikacji jako „co najmniej obce”.
- **M7.** Druga kopia wzorca `sign|song|forced` zostaje w legacy `services/extraction/tracks.py` — kierunek zależności (services nie importuje application) uniemożliwia reuse; dług E5, zapisany w „Poza zakresem”.

### Sugestie

- **S1.** Masterplan 08 przewidywał „licznik prób per odcinek” dla ścieżki ręcznej. Plan zastępuje go regułą łańcucha `previous_admission_id` (bez nowego trwałego pola). Prostsze i wystarczające dla limitu dwóch pobrań; warto, żeby recenzent krzyżowy potwierdził brak przypadku, którego łańcuch nie odróżnia (D2).

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
|---|---|---|
| U-07 zawartość, nie nazwa | pass | werdykt z katalogu sondy; 3 pliki `[MultiSub]` bez PL w `current-state.md` §5.1 |
| U-08 PL → bez tłumaczenia | pass | istniejący planner (`planner.py:1354-1391`), D4 |
| U-08 obce → tłumaczenie | pass | jw. |
| U-08 brak → jedno kolejne wydanie, potem problem | pass | wymagania 11–16, F2–F3 |
| U-08 lektor zawsze | pass | inwariant; E4 nie zmienia produktów |
| Limit 2 pobrań ręcznych / 3 prób subskrypcji (K-09) | pass | reguła łańcucha, wspólny budżet subskrypcji |
| K-09 błąd sondy ≠ odrzucenie | pass | wymaganie 10, test `unchecked` |
| K-10 kontrola także ręcznie | pass | F3.2 |
| I-02 brak H2 dla ręcznych | pass | `ExpectedEpisode(None)` i brak odrzucenia czasem |
| R-07 reguła zamiany | pass | `replacement` bez zmian |
| I-08 powód widoczny | pass | `_REJECTIONS`, `SUBTITLES_MISSING`, rejestr |
| Reuse przed nowym kodem | pass | jedyny nowy moduł to plik testów; reguła w istniejącym `selection.py` |
| Rozpoznanie szyldów z dowodem (N-05) | pass z luką | tempo zmierzone `ffprobe`; pole aplikacji — F0 |

## Wykonane kontrole

```text
ffprobe -v error -show_streams -show_format -of json na 52 MKV w workspace/ready (rekurencyjnie)
  790 ścieżek napisów, NUMBER_OF_FRAMES obecny dla 790/790
  pełne: 758, tempo 7,98–41,18/min; szyldy: 32, tempo 0,19–1,52/min
  forced: 33 (32 szyldy + 1 pełna); tytuł sign|song|forced: 30 (same szyldy)
odczyt config/watch/state.json (tylko zliczenia): schemat 5, 90 przypisań, verification tylko w subskrypcjach
odczyt kodu: automation.py, control.py, download_verification.py, planner.py, selection.py,
  subscription_choice.py, subscription_targets.py, services/media/*, services/extraction/*, anime_texts.py
wyszukanie użyć: replacement() — brak wywołań; _is_non_dialogue — tylko planner
```

## Niewykonane lub nierozstrzygające kontrole

- `mkvmerge -J` na plikach (zakaz zlecenia dopuszczał tylko `ffprobe`) — bramka F0.
- MP4 z napisami: brak w próbce; mapowanie `nb_frames` sprawdzi tylko test na syntetycznym JSON.
- Bramki repo — plan nie zmienia kodu.

## Wymagana ocena człowieka

H4 według `plan.md` F4 oraz decyzje D1–D8 ze `specification.md`.

## Zalecany następny krok

1. Przegląd krzyżowy innym modelem (najlepiej z innej rodziny) tych trzech plików.
2. Decyzje właściciela D1–D8.
3. Start F0.
