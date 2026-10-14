---
kind: superseded-plan-pointer
status: superseded
updated: 2026-09-08
baseline: a7d319f334a062d0fe016c774d9a5fb4fccbe9b6
current_workstream: docs/work/06-local-automation/06-efficiency
---

# Plan 06: aktualna specyfikacja i plan implementacji

**Historyczny następca: [pakiet etapu 06](../06-efficiency/README.md), zakończony w PR #56.**

| Dokument | Do czego służy |
| --- | --- |
| [Nowa specyfikacja](../06-efficiency/specification.md) | Manual, Auto, niezależne subskrypcje i regeneracja; wymagania i odbiór. |
| [Plan implementacji](../06-efficiency/plans/01-implementation.md) | Istniejące pliki i kontrakty, kolejność P01–P08, migracja i testy. |
| [Research](../06-efficiency/research/2026-09-08-control-model-research.md) | Kod analizowanego commitu, źródła i granice dowodu. |

Manual oznacza wybór odcinków i świadomy Start. Auto reaguje na gotowe pliki w bibliotece. Subskrypcje osobno dostarczają odcinki i mają Dodaj/Włącz/Wyłącz/Usuń. Regeneracja to Auto z wymuszeniem wskazanych produktów i opcjonalnymi jednorazowymi ustawieniami. Żadna z tych dróg nie tworzy odrębnego silnika wykonania.

Poprzednie notatki właściciela i odrzucony załącznik zachowano w [wersji historycznej tego pliku](https://github.com/MattyMroz/AniShift/blob/a7d319f334a062d0fe016c774d9a5fb4fccbe9b6/docs/plans/local-automation/plans/06-queue-and-control.md). Nie są już aktywną specyfikacją ani poleceniem czekania na kolejną rozmowę. W razie sprzeczności obowiązuje nowy ../specification.md.

Ta aktualizacja dostarcza dokumenty. Nie zmienia kodu aplikacji i nie oznacza, że nowe sterowanie lub kolejka zostały już wdrożone.
