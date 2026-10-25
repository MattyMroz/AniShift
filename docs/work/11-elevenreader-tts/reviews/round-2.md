---
kind: review
status: fail
reviewed-state: docs/work/11-elevenreader-tts/{plan,specification,file-map}.md po poprawkach rundy 1
date: 2026-10-25
---

# Review: plan i specyfikacja silnika ElevenReader — runda 2

## Zakres

- przedmiot: pliki po poprawkach rundy 1;
- authority: jak w rundzie 1;
- ryzyka szczególne tej rundy: cykl życia próby dokumentu w schedulerze i fasadzie, anulowanie i zamykanie,
  bramki typów na dwóch platformach, wykonalność testów;
- poza review: wykonanie kodu.

Metoda: prześledzenie ścieżki `TtsTaskHandler → TtsService → TtsScheduler → silnik → splitter → resume` w kodzie
(`anishift/services/tts/service.py:248-377`, `:778-786`, `anishift/services/tts/scheduler.py:154-260`,
`anishift/application/tts_handler.py:270-285`, `:399-444`) i zderzenie z §13.6, §13.9 i §18 planu; sprawdzenie
konfiguracji mypy i CI (`pyproject.toml:122-130`, `.github/workflows/ci.yml:58-66`).

## Werdykt

**Status:** FAIL

**Najważniejszy powód:** anulowanie i zamknięcie przebiegu nie przerywały długich oczekiwań Playwright, a przerwane
zamknięcie mogło zostawić proces Chrome z zajętą blokadą profilu do restartu rezydenta.

## Findings

### Krytyczne

Brak.

### Poważne

#### P4. `creationflags=CREATE_NO_WINDOW` łamie `mypy --platform linux`

- miejsce: plan §13.8 `browser.py`;
- dowód: hook pre-push i CI uruchamiają mypy także dla Linuksa (`AGENTS.md`, „Twarde strażniki”); istniejący kod
  używa `getattr(subprocess, "CREATE_NO_WINDOW", 0)` (`anishift/platform/qbittorrent_process.py:649`,
  `anishift/platform/local_control.py:967`), bo atrybut istnieje w typeshed tylko dla win32;
- wpływ: czerwone CI i zablokowany push;
- minimalna reakcja: ten sam wzorzec `getattr`.

#### P5. Anulowanie nie przerywa długich oczekiwań Playwright

- miejsce: plan §13.9 (czekanie na „Play” do 600 s, upload, akcje do 120 s); wymaganie N4;
- dowód: `TtsService.cancel()` woła tylko `scheduler.cancel_pending()` (`service.py:290-297`), które obsługuje kolejkę,
  nie aktywną próbę (`scheduler.py:169-188`); pętla silnika sprawdza `cancel.is_cancelled` dopiero między krokami;
- wpływ: anulowanie w trakcie oczekiwania na gotowość dokumentu trwałoby do 10 minut; N4 niespełnione;
- minimalna reakcja: każde długie oczekiwanie ścigane z `cancel.wait()` (`protocols.py:76-78`); testy przerwania
  czekania.

#### P6. Przerwane zamknięcie przebiegu zostawia Chrome i blokadę profilu

- miejsce: plan §13.8 `browser.close`, §13.9 `finally`;
- dowód: `TtsService.close()` czeka na `_shutdown_async` najwyżej `shutdown_deadline_s` (domyślnie 5 s,
  `config.py:36`), potem anuluje i zatrzymuje pętlę (`service.py:316-326`); `scheduler.close()` czeka na aktywne
  workery (`scheduler.py:162`), więc `engine.close()` może się nie wykonać; blokada `ProcessLock` jest per proces
  (`process_lock.py:32-37`), a rezydent żyje dalej;
- wpływ: kolejny przebieg dostaje „profil zajęty” aż do restartu rezydenta; osierocony headless Chrome z sesją;
- minimalna reakcja: zamknięcie przeglądarki w `finally` próby przy anulowaniu i awarii; `close()` idempotentne z
  krótkimi oczekiwaniami; `shutdown_deadline_s=15` dla silnika; test zwolnienia blokady.

### Mniejsze

#### M6. Jeden limit 30 s dla FFmpeg także przy nagraniu dokumentu

- miejsce: plan §13.7; `anishift/application/runtime.py:216-226` (`timeout_s=_AUDIO_TIMEOUT_S`, 30 s);
- wpływ: na wolnym dysku dekodowanie nagrania bliskiego limitowi 50 000 znaków (około 54 minut) może przekroczyć
  limit i zamienić się w ponowienie całego dokumentu;
- reakcja: osobny `recording_timeout_s` (300 s) dla obwiedni.

#### M7. Typowanie fałszywych obiektów Playwright w testach niejasne

- miejsce: plan §18 F4, testy silnika;
- wpływ: mypy strict na `tests/` odrzuci fałszywe strony przekazywane tam, gdzie oczekiwany jest `Page`; kusi
  dodanie produkcyjnych `Protocol` tylko dla testów (wbrew `python.md`: `Protocol` tylko przy realnej
  wymienności);
- reakcja: `cast("Page", fake)` w testach.

#### M8. Nieopisana konsekwencja nieznalezionego szyldu

- miejsce: plan §13.15;
- dowód: `build_narration_manifest` wymaga `COMPLETED` także dla szyldów (`tts_handler.py:408-409`);
- wpływ: wykonawca mógłby „naprawiać” to w handlerze, co jest poza zakresem;
- reakcja: wpis w edge cases: zachowanie jak dziś dla każdego silnika, ponowienie czyta tylko brakujący szyld.

#### M9. Brak testu mapowania błędów w mapie plików

- miejsce: `file-map.md` §2 „Testy”;
- reakcja: dopisać `tests/services/tts/test_tts_elevenreader_errors.py`.

### Sugestie

#### S2. Osobna walidacja całego nagrania jest zbędna

Dekodowanie obwiedni w `split_clip` jest już pełnym dekodowaniem nagrania; osobne `validate_clip(recording)`
podwaja pracę FFmpeg na najdłuższym pliku. Wystarczy walidacja każdego wyciętego klipu (potrzebna i tak do receipt
resume).

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
|---|---|---|
| N4 anulowanie w sekundach | fail → poprawione | P5 |
| N5 Chrome kończy się z przebiegiem/rezydentem | fail → poprawione | P6 |
| S1 bramki (mypy linux) | fail → poprawione | P4 |
| F2–F4 | pass | §13.6 bez zmian w tej rundzie |
| I3 brak retry w transporcie | pass | ponowne „Play” opisane jako czynność odtwarzacza, `_unless_cancelled` nie ponawia |

## Regresje i integracja

- Sprawdzono, że ścieżka dokumentu nie nakłada prób: `_run_document_batch` czeka na wynik `submit` przed kolejnym
  dokumentem, a `max_concurrency=1`; akceptacja (cięcie) biegnie w osobnym zadaniu schedulera
  (`scheduler.py:255-260`), ale kolejna próba tego samego batcha nie jest jeszcze w kolejce. Bez findingu.
- Sprawdzono, że `commit_clip` z receipt nie dekoduje klipu drugi raz (`resume.py:205-232`). Bez findingu.

## Wykonane kontrole

```text
odczyt: anishift/services/tts/service.py:290-326, :778-786; anishift/services/tts/scheduler.py:154-260;
        anishift/services/tts/config.py:30-40; anishift/platform/qbittorrent_process.py:633-653;
        anishift/platform/process_lock.py:32-60; anishift/application/runtime.py:208-242;
        anishift/application/tts_handler.py:399-444; pyproject.toml:122-130
wynik: opisane findingi
```

## Niewykonane kontrole

- Bramki i testy — zakaz uruchamiania kodu; zaplanowane w fazach.

## Poprawki naniesione po rundzie

| Finding | Poprawka | Miejsce |
|---|---|---|
| P4 | `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` z uzasadnieniem | `plan.md` §13.8 |
| P5 | helper `_unless_cancelled` dla każdego długiego oczekiwania; test `test_engine_cancel_interrupts_long_wait_for_play` | `plan.md` §13.9, §18 F4 |
| P6 | zamknięcie przeglądarki w `finally` przy anulowaniu i awarii; `close()` idempotentne, 2 s na `terminate`; `shutdown_deadline_s=15`; test zwolnienia blokady | `plan.md` §13.8, §13.9, §13.12, §18 F4, F5 |
| M6 | `recording_timeout_s=300` w `FfmpegClipService` | `plan.md` §13.7 |
| M7 | `cast("Page", fake)` w testach | `plan.md` §18 F4 |
| M8 | wiersz „szyld nieznaleziony” | `plan.md` §13.15 |
| M9 | wiersz testu błędów | `file-map.md` |
| S2 | usunięta walidacja całego nagrania; kontrakt `split_clip` mówi, że dekodowanie obwiedni jest walidacją | `plan.md` §13.3, §13.4, §13.6, §9 |

## Zalecany następny krok

Runda 3: spójność całości po dwóch rundach poprawek (numeracja, odwołania, kolejność commitów wobec faz,
kompletność checkpointów i warunków stopu).
