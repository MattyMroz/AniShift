---
kind: historical-package-index
status: superseded-for-current-work
updated: 2026-09-08
current_workstream: docs/work/local-automation/06-efficiency
---

# Lokalna automatyzacja: historia etapów i dawnego pakietu

**Aktualny wykonawca zaczyna od [nowego pakietu etapu 06](../../work/local-automation/06-efficiency/README.md): [specyfikacja](../../work/local-automation/06-efficiency/spec.md) -> [plan implementacji](../../work/local-automation/06-efficiency/plan.md).**

Ten katalog nie jest równoległą kolejką do wdrożenia. Dawne `spec.md`, `research.md`, `brief.md`, `masterplan.md` i `handoff.md` opisują wcześniejszy projekt i są źródłami historycznymi. W szczególności ich SQLite, osobny inbox, katalogi rewizji i wielki podział zadań nie obowiązują w nowym etapie 06. Aktualny plan rozwija istniejący rdzeń i strukturę biblioteki.

## Zachowane materiały implementacji

| Materiał | Znaczenie historyczne |
| --- | --- |
| [01-watch-mode](plans/01-watch-mode.md) | Pierwsze czuwanie, podfoldery biblioteki, okno partii i autostart. |
| [02-search-and-download](plans/02-search-and-download.md) | Wyszukiwanie i przekazanie pobrań do qBittorrenta. |
| [03-subscriptions](plans/03-subscriptions.md) | Pierwsze subskrypcje i godzinne sprawdzanie. |
| [04-smart-search](plans/04-smart-search.md) | Tożsamość tytułu, AniList, sezon i numeracja odcinków. |
| [Przegląd 2026-09-06](reviews/2026-09-06-local-automation-review.md) | Ustalenia przeglądu wcześniejszej implementacji. |
| [06-queue-and-control](plans/06-queue-and-control.md) | Stały odnośnik przekierowujący do nowego kontraktu etapu 06. |

Sekcje wyników starszych planów dotyczą podanych tam commitów i scenariuszy. Nie są dowodem wykonania nowej specyfikacji, której implementacja ma dopiero nastąpić. Aktualne działanie opisuje [README aplikacji](../../../README.md).

Pełna poprzednia wersja tego indeksu i jej ustalenia pozostają w [historii sprzed aktualizacji](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/docs/plans/local-automation/README.md). Plików źródłowych dawnego pakietu nie usunięto ani masowo nie przeniesiono.
