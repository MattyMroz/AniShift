---
kind: review
status: pending
reviewed-state: work/reliability/05-auto-preset-controls, final local changes on 6eef7d1
date: 2026-09-05
---

# Review: Auto preset controls

## Zakres i werdykt

Plan 05 / A00: komplet ustawień domyślnego Auto, zachowanie istniejących produktów,
reset i błędy zapisu, smoke syntetycznych MKV PL/EN. Bez watcherów, pobierania,
prywatnych danych ani nowych heurystyk.

**Technicznie: PASS WITH FINDINGS. Cały odbiór: PENDING HUMAN.**
Prowadzący niezależnie sprawdził kod Fable i wskazał R1–R5. Po limicie wykonawcy,
za zgodą właściciela, sam dokończył poprawki. Kontrola tych ostatnich poprawek
jest autokontrolą, nie drugim niezależnym review.

## Rozliczenie uwag

| ID | Problem | Finalny stan i dowód |
| --- | --- | --- |
| R1 | Pełny test pomijał setup, który pobierał binarki | Zamknięte: izolacja HTTP/katalogu wewnątrz subprocessu, prawdziwe doctor/setup; pełny suite bez deselection |
| R2 | Poprawne smoke kończyły się planem; słabe asercje produktów | Zamknięte: 23 udane wykonania, sprawdzenie treści/ścieżek, SHA256 wejść, decode/audio/burn MP4; 30/30 smoke |
| R3 | Brak jawnych typów nowych zmiennych | Zamknięte: nowe helpery/testy i adapter mają adnotacje; mypy native/Linux oraz Ruff PASS |
| R4 | Zakaz tłumaczenia opisany zbyt szeroko | Zamknięte: etykieta mówi o produktach PL; angielskie source-burn z do_not_translate wykonuje się poprawnie |
| R5 | Raport i polecenia nie odzwierciedlały finalnego stanu | Zamknięte: aktualny outcome, macierz, wspólna venv bez sync i PYTHONPATH worktree; CLI AGENTS zgodny z resetem |

Nie zmieniono formatu presetu ani providerów. Adapter jest jedynym miejscem
mapowania pól. Render korzysta z lokalnego snapshotu; zapis odczytuje świeży
preset i zmienia tylko wskazane pole. Reset dwóch plików nie udaje transakcji.
Poprawka planera usuwa wiszące odwołania po odrzuceniu zadań, zachowując odmowę.

## Pozostałe findings

Zastane SRT daje pustą warstwę displayed: błąd jest podczas wykonania, nie
preflightu. Bez publikacji pustego produktu; regresja wykonana. Poza zakresem
tej poprawki ustawień, do osobnego etapu heurystyk/preflightu.

Długa etykieta tłumaczenia jest przycinana w menu. Testy sprawdzają brak
wyjścia poza terminal, ale czytelność wymaga oceny użytkownika.

## Dowody DIRECT

- Ruff check i format całych anishift/ tests/: PASS (443 pliki).
- Mypy native i --platform linux całych anishift/ tests/: PASS (445 plików).
- Pełny pytest: **3089 passed, 13 skipped, 11 warnings, 26.54 s**.
- Dedykowane smoke z markerem smoke: **30 passed, 14.35 s**.
- anishift --help: PASS.
- Treści, ścieżki, źródłowe hashe oraz dekodowanie/audio/klatki MP4 sprawdzone testami.

Środowisko i polecenia: [outcome](../outcomes/05-auto-preset-controls.md).
Skips: 7 sieci, 4 zewnętrzne korpusy, 2 symlinki Windows.
Nie sprawdzono live Google/Edge, materiału prywatnego ani wykonania na Linuxie.
Dane syntetyczne nie potwierdzają jakości tłumaczenia i segmentacji.

## Następny krok

Lokalny commit/scalenie kodu zgodnie ze zleceniem; zachować niezależny pakiet
planowania i prywatny plik. Użytkownik ocenia nowy panel według scenariusza
z outcome. Publikacja na GitHub nie jest częścią tej zgody.
