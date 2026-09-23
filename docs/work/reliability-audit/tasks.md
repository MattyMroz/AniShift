---
kind: task-board
updated: 2026-09-05
---

# AniShift — lokalna tablica zadań

Tablica jest powiązana z [masterplanem](masterplan.md) i
[findingami audytu](audit.md). Otwarte dopracowanie przeniesiono do
[GitHub Issues](../../plans/automation/README.md#odłożone-dopracowanie), które są
właścicielem jego bieżącego statusu. Historyczne ID i dowody pozostają tutaj.
Nie utworzono osobnego GitHub Project.

## Statusy i zasada aktualizacji

Aktualny workstream: [plany automatyzacji i napisów](../../plans/automation/README.md).
Kod poprzedniej iteracji jest na `main` po PR #41; nie zamyka to oczekujących
ocen człowieka. Pełne testy produktu i porównania promptów są decyzją właściciela
odłożone. Nowe funkcje mają na razie wyłącznie zakres planistyczny.

Wynik implementacji i komendy: [outcome](outcomes/02-hardening.md).
Terminal: [wynik Planu 04](outcomes/04-terminal-polish.md).
Aktualny checkpoint: wybór jednej iteracji automatyzacji i szczegółowy plan
z [briefu dla Pro](../../plans/automation/pro-brief.md). Ogólne dopracowanie
i pełne próby produktu są odłożone; nie blokują wszystkiego.

`backlog` → `ready` → `in-progress` → `verified` → `done`.
`pending-human` oznacza oczekującą ocenę właściciela, `blocked` konkretną zależność,
`deferred` świadomie odłożony zakres. `ready` oznacza gotowość planu, nie zgodę
na commit/publikację ani dowód wykonania. Zamykany task musi wskazywać outcome
z konkretną kontrolą i commit, jeśli powstał. Nie kopiować procentowych statusów
do innych dokumentów.

## Naprawy i dowody

| ID | Tytuł | Priorytet | Etap | Zależność | Status | Warunek zakończenia / dowód |
| --- | --- | --- | --- | --- | --- | --- |
| A01 | Reject partial translations before product publication | P1 | M01 | — | verified | ASS/SRT i TXT: partial/blank blokuje writer oraz zależne produkty; 15 regresji FAIL→PASS; [dowód](outcomes/02-hardening.md) |
| A02 | Require successful SSE completion | P1 | M01 | A01 | verified | SSE error/EOF i nieznany finish odrzucone; poprawne odpowiedzi zachowane; [dowód](outcomes/02-hardening.md) |
| A03 | Preserve Responses incomplete reasons | P1 | M01 | A02 | verified | xAI incomplete z limitem zachowuje split, failed nie jest sukcesem; A02/A03: 9 regresji FAIL→PASS; [dowód](outcomes/02-hardening.md) |
| A04 | Reject decoded blank translations | P2 | M01 | A01, wspólny Plan 01 | verified | Niepustość po jednokrotnym decode i ten sam kontrakt per-line Google; [dowód](outcomes/02-hardening.md) |
| A05 | Preserve repeated SRT utterances | P1 | M04 | — | verified | Powtórzone kwestie SRT zachowane; ASS nadal rozpoznaje animację; kolejność writera chroniona; [dowód](outcomes/02-hardening.md) |
| A06 | Honor an explicit empty spoken selection | P2 | M04 | A05 | verified | Jawne spoken_styles=() daje puste spoken, bez cichego fallbacku; [dowód](outcomes/02-hardening.md) |
| A07 | Validate container duration with narration tails | P1 | M04 | — | verified | Realne FFmpeg: osobna długość video/container, dłuższa narracja nie jest obcinana; [dowód](outcomes/02-hardening.md) |
| A08 | Separate long audio work from probe timeouts | P1/P2 | M03 | — | verified | Osobny deadline renderowania/transkodowania; testy timeout, cancel i cleanup; [dowód](outcomes/02-hardening.md) |
| A09 | Accept validated MKVToolNix warning results | P2 | M04 | A11 | verified | Exit 1 tylko z niepustym wynikiem akceptowany jako warning; exit 2 nadal failure; [dowód](outcomes/02-hardening.md) |
| A10 | Support subtitle filters under quoted directories | P2 | M04 | M03 | verified | Rzeczywisty FFmpeg działa pod parent z apostrofem; bezpieczny cwd i basename filtra; [dowód](outcomes/02-hardening.md) |
| A11 | Bound the active MKV extraction lifecycle | P1 | M03 | — | verified | Cichy proces, EOF, deadline, cancel po runner/stat, kill i callback failure objęte regresją; [dowód](outcomes/02-hardening.md) |
| A12 | Cancel active work before shutdown | P1/P2 | M03 | A11 | verified | Token przed shutdown executora; UI sygnalizuje cancel w finally; aktywna sieć ograniczona timeoutem; [dowód](outcomes/02-hardening.md) |
| A13 | Keep the coordinator responsive during publication retries | P2 | M03 | A12 | verified | Publikacja A czeka bez blokowania B; generation/cancel nadal chronią atomowe replace; [dowód](outcomes/02-hardening.md) |
| A14 | Carry measured progress through media stages | P2 | M05 | M03, M04 | pending-human | FFmpeg measured progress dociera do UI; nieznane fazy pokazują aktywność; ocena terminala otwarta; [dowód](outcomes/02-hardening.md) |
| A15 | Count translation progress across attempts correctly | P2 | M05 | A02, A03 | verified | Newline/fences, retry/transport reset, split offset i cap przed walidacją; niezależne review PASS; [dowód](outcomes/02-hardening.md) |
| A16 | Show actionable per-group run outcomes | P2 | M05 | A14 | pending-human | Wynik grup ma przyczyny i produkty, przewijanie z ograniczeniem zakresu; ocena kopiowania/ergonomii otwarta; [dowód](outcomes/02-hardening.md) |
| A17 | Measure and reduce terminal startup overhead | P2 | M06 | M05 | pending-human | Zmierzono encoder/Home, ograniczono polling; brak dowodu szybszego encodera i pełnego startupu; [dowód](outcomes/02-hardening.md) |
| A18 | Validate persisted setting types before use | P2 | M02 | — | verified | Nieprawidłowe typy preferencji izolowane; float/bool nie stają się int; [dowód](outcomes/02-hardening.md) |
| A19 | Isolate malformed and colliding model catalogue entries | P2 | M02 | A18 | verified | Złe URL i kolizje znormalizowanych ID izolowane; dobre wpisy pozostają dostępne; [dowód](outcomes/02-hardening.md) |
| A20 | Prepare required binaries before inspection | P2 | M02 | A21 | pending-human | Przygotowanie przed probe + lokalny ZIP/HTTP sprawdzone; świeży Windows i UX pobierania nadal otwarte; [dowód](outcomes/02-hardening.md) |
| A21 | Replace installed binaries atomically | P2 | M02 | — | verified | Weryfikacja SHA256, staging na volume celu, atomic replace; błąd zachowuje poprzedni plik; [dowód](outcomes/02-hardening.md) |
| A22 | Audit the project dependency set in CI | P2 | M02 | — | verified | Audyt 87 zależności z locka: brak znanych podatności; CI eksportuje lock dla Ubuntu/Windows; [dowód](outcomes/02-hardening.md) |
| A23 | Read and filter production logger records correctly | P2 | osobny utils | Zgoda otrzymana | verified | Rzeczywisty JSONL roundtrip, filtry złożone i DST: godzina ma 3600 s; niezależnie 145 testów loggera PASS; [dowód](outcomes/02-hardening.md) |
| A24 | Redact absolute paths in serialized log metadata | P2 | osobny utils | Zgoda otrzymana | verified | Oba sinki: basename bez ścieżek/sekretów/kodu SyntaxError, także cause/notes/groups; review PASS; [dowód](outcomes/02-hardening.md) |
| A25 | Report font attachment uncertainty accurately | P2 | M08 | Realny attachment Q08 | verified | Basename nie dowodzi rodziny; jawny komunikat niepewności zamiast fałszywego braku; [dowód](outcomes/02-hardening.md) |

## Czytelność, jakość i nowe możliwości

| ID | Tytuł | Etap | Zależność | Status | Warunek zakończenia / dowód |
| --- | --- | --- | --- | --- | --- |
| Q01 | Isolate color rendering tests from environment policy | M02 | — | verified | Test wymuszonego koloru izoluje NO_COLOR; pełny suite przechodzi w niezmienionym środowisku; [dowód](outcomes/02-hardening.md) |
| Q02 | Shorten application docstrings and preserve section dividers | M07 | Stabilne dotknięte kontrakty | verified | Jednozdaniowe docstringi aplikacji, bez masowej zmiany utils; wykonywalny AST skrócenia bez zmian; [dowód](outcomes/02-hardening.md) |
| Q03 | Reconcile operational instructions with current code | M07 | Wyniki M01–M06 | verified | AGENTS i README odpowiadają obecnemu frontendowi, skillom, postępowi i instalacji; CLAUDE odsyła do AGENTS; [dowód](outcomes/02-hardening.md) |
| Q04 | Review the test-prose guard scope | M07 | Zgoda na zmianę strażnika | verified | Zgoda otrzymana; conftest i testowe __init__ objęte hookiem oraz CI, 18 testów strażnika PASS; [dowód](outcomes/02-hardening.md) |
| Q05 | Reduce proven duplication after contract tests | M07 | M03–M05 | deferred | Nie wykazano potrzeby reorganizacji; reuse istniejących helperów bez nowego frameworka; szersze przenosiny pominięte; [dowód](outcomes/02-hardening.md) |
| Q06 | Align progress visuals with the existing brand palette | M06 | A14, A15 | pending-human | Gradient bierze istniejącą paletę; brak osobnego renderera; akceptacja wyglądu otwarta; [dowód](outcomes/02-hardening.md) |
| Q07 | Validate Polish reflow on a representative corpus | M04 | Przykłady językowe | pending-human | Korpus 4 zdań × 5 szerokości i negatywne przypadki; 51 testów PASS; naturalność wymaga oceny; [dowód](outcomes/02-hardening.md) |
| Q08 | Verify restart recovery, fonts and long-duration boundaries | M08 | M03, M04 | in-progress | Świeży proces po cancel, realny font i mały RF64 PASS; hard-kill, metadane rodzin i >4 GiB otwarte; [dowód](outcomes/02-hardening.md) |
| Q09 | Run repeatable media and provider acceptance scenarios | M08 | M01–M05, gotowy setup | pending-human | Krótki produkcyjny MKV→Google→Edge→publikacja PASS bez retry; cały odcinek/odsłuch otwarte; [dowód i próbki](outcomes/02-hardening.md) |
| Q10 | Reconcile shared utility portability and retry contracts | osobny utils | Zgoda otrzymana | verified | Portable utils bez importów aplikacji; wymagania runtime i custom logging level sprawdzone; [dowód](outcomes/02-hardening.md) |
| Q11 | Synchronize the normalization concurrency test deterministically | M08 | — | verified | Bariera zastępuje sleep50ms, pełna asercja czterech workerów zachowana; commit 173fdf9; [dowód](outcomes/02-hardening.md) |
| Q12 | Close delayed extraction output and model native child processes | M08 | A11 | verified | Czytnik domyka własny pipe po opóźnionym EOF; native-process timeout/reap/closed bez osłabienia asercji; [dowód i granice](outcomes/02-hardening.md) |
| P01 | Produce an audiobook from standalone text | M09 | M08, kontrakt TXT | deferred | TXT bez wideo daje audio o naturalnym rytmie; tłumaczenie opcjonalne |
| P02 | Watch completed input files automatically | przyszłość | M08, idempotencja | deferred | Zamknięte kopiowanie, deduplikacja zleceń i restart; osobny plan |
| P03 | Import dropped terminal paths | przyszłość | Polityka copy/move/kolizji | deferred | Materiał trafia do właściwej grupy bez utraty źródła |
| P04 | Discover and download requested episodes | przyszłość | Źródła i zasady dostępu | deferred | Osobny zaakceptowany kontrakt i plan integracji |

## Terminal i ustawienia — feedback 2026-09-05

| ID | Tytuł | Priorytet | Status | Warunek zakończenia / dowód |
| --- | --- | --- | --- | --- |
| U01 | Keep terminal ownership across redraw and exit | P1 | pending-human | Real Renderer i Application.run/exit PASS, brak wychodzenia do primary screen przy przejściu; [wynik](outcomes/04-terminal-polish.md) |
| U02 | Make branding and queue responsive | P2 | pending-human | Po feedbacku: nieruchome duże logo lub sam slime, bez średniego napisu; pełna osiągalność kolejki; [wynik](outcomes/04-terminal-polish.md) |
| U03 | Keep completion and progress in one readable palette | P2 | pending-human | Checkmark, gradient, krótkie etapy, dynamiczne nazwy, Unicode i brak overflow; [wynik](outcomes/04-terminal-polish.md) |
| U04 | Preserve settings edits and all output products | P1 | verified | Siedem produktów, rollback błędnego zapisu, no-op, brak utraty pending, jawne porzucenie; [wynik](outcomes/04-terminal-polish.md) |
| U05 | Recover model selection without weakening run readiness | P1 | verified | Pierwszy własny model, atomowy zapis, usunięty alias nadal blokuje wykonanie, lecz nie picker; [wynik](outcomes/04-terminal-polish.md) |
| U06 | Unify keyboard navigation and masked input | P2 | pending-human | Tab/backtab, lewo/prawo, cursor/delete/paste, powrót do miejsca w menu; [wynik](outcomes/04-terminal-polish.md) |
| U07 | Audit prompts and remove unused scratch copies | P2 | verified | Loader i kontrakt zbadane, trzy TXT usunięte odzyskiwalnie, aktywne prompty bez zmian; [rekomendacje](prompt-recommendations.md) |
| U08 | Expose advanced default Auto preset controls | P2 | pending-human | `4dc99dc` scalone lokalnie do głównej kopii; R1–R5 zamknięte, 3089 testów PASS i 30 smoke PASS; czeka odbiór panelu; [wynik](outcomes/05-auto-preset-controls.md) |
| U09 | Evaluate a shorter faithful translation prompt | P2 | deferred | Usunąć sprzeczności, ślepe A/B, metryki kontraktu i jakości; [plan ewaluacji](prompt-recommendations.md) |
| U10 | Document settings and correct misleading concurrency labels | P2 | transferred | Status i kryteria: [GitHub #42](https://github.com/MattyMroz/AniShift/issues/42) |
| U11 | Keep settings viewport height stable while wheel scrolling | P2 | done | 83150d8; 13 regresji FAIL→PASS, pełny suite 3102 passed / 13 skipped; właściciel potwierdził „Ok działa” |

## Jak dopisywać nowe problemy

Nadaj nowy stały ID. Zapisz scenariusz, oczekiwany i rzeczywisty wynik, źródło
dowodu oraz minimalną reakcję w nowym raporcie review albo outcome. Na tablicy
umieść link, priorytet, zależność i kryterium zakończenia. Nie zamieniaj podejrzenia
w confirmed bug ani preferencji wizualnej w blocker funkcjonalny.

Przy późniejszym przeniesieniu do GitHub zachować lokalne ID w treści issue,
skorzystać z `.github/ISSUE_TEMPLATE/` i aktualnej listy dozwolonych scopes.
Nie utrzymywać dwóch niezależnych statusów: po decyzji o GitHub wskazać jednego
właściciela statusu i używać w drugim miejscu wyłącznie linków.
