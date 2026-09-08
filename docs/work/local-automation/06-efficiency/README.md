---
kind: handoff
status: ready-for-implementation
updated: 2026-09-08
baseline: a7d319f334a062d0fe016c774d9a5fb4fccbe9b6
branch: work/local-automation/06-efficiency
---

# AniShift 06: zacznij tutaj

**Manual wybiera odcinki. Auto reaguje na gotowe pliki. Subskrypcje niezależnie pobierają i mają Dodaj / Włącz / Wyłącz / Usuń. Regeneracja to ponowne Auto z żądaniem odtworzenia, nie trzeci tryb.**

## Dokumenty obowiązujące w tej zmianie

| Kolejność | Dokument | Rola |
| --- | --- | --- |
| 1 | [spec.md](spec.md) | Zamawiane zachowanie, granice, 28 wymagań, 5 niezmienników i 42 kryteria akceptacji. |
| 2 | [plan.md](plan.md) | Decyzje techniczne, dotykane pliki, kolejność P01–P08, migracja, testy, bramki Windows i mapa pokrycia. |
| Pomocniczo | [research](research/2026-09-08-control-model-research.md) | Ustalenia z konkretnego commitu i oficjalnych źródeł, z ograniczeniami dowodu. |

Specyfikacja i plan są gotowe do implementacji. **Kod nie został w tym pakiecie zaimplementowany.** Status READY nie oznacza pozytywnego wyniku prób Windows, integracji z klientem ani pomiarów. Wynik etapów dopisuj w sekcji 14 planu.

## Instrukcja dla agenta kodującego

Przeczytaj root/scoped AGENTS, następnie spec.md i plan.md. Porównaj aktualny kod z baseline wskazanym powyżej. Nie zakładaj czystego drzewa i nie odrzucaj cudzych zmian. Realizuj kolejno P01–P08, zaczynając od kontraktów, ledgera i migracji, a nie od wyglądu interfejsu. Testuj rzeczywiste granice i zapisuj dowody przy etapach. Zatrzymaj zależną część pracy, gdy bramka platformowa obali metodę; nie zastępuj wymagań ukrytym pollingiem lub zamykaniem dowolnego procesu.

Najważniejsze ograniczenia: istniejące AppService, planner, GraphScheduler, handlery i renderer Prompt Toolkit; jedna własność wykonania i stanu; wspólne limity; brak konkurencyjnych schedulerów. Nie dodawaj RunMode.REGENERATE, SQLite, brokera, nowego inboxa, webowego panelu, nowych zależności runtime ani nowych formatów presetów/mediów. Źródła i produkty nadal są obok siebie w bibliotece.

Wyłączenie subskrypcji nie wyłącza Auto, nie usuwa plików i nie anuluje wcześniej przyjętego pobrania. Wyłączenie Auto nie wyłącza subskrypcji ani Manual. Manual nie wymaga ręcznego konstruowania grafu; domyślny preset wystarcza do zwykłego wyboru zakresu, a obecne zaawansowane źródła pozostają dostępne. Regeneracja i ręczne wyniki nie mogą być zaraz cofane przez tło.

Przygotowanie lokalnej gałęzi, po sprawdzeniu i zabezpieczeniu istniejących zmian:

```bash
git fetch origin
git switch work/local-automation/06-efficiency
git pull --ff-only
```

Jeżeli gałąź istnieje tylko zdalnie, użyj `git switch --track origin/work/local-automation/06-efficiency`. Nie używaj reset --hard ani force push jako sposobu przygotowania. Kodowe commity przechodzą obecne pełne bramki repo i nie trafiają bezpośrednio do main.

## Co zostało zastąpione

Ten katalog jest jedyną bieżącą kolejką pracy dla etapu 06. Poprzedni załączony pakiet specyfikacji oraz [dawny plan 06](../../../plans/local-automation/plans/06-queue-and-control.md) nie są równoległym kontraktem. [Starszy pakiet automatyzacji](../../../plans/local-automation/README.md) i jego spec/brief/masterplan/handoff służą wyłącznie jako historia i dowody wcześniejszych zmian. Nie realizuj na ich podstawie odrzuconej architektury SQLite/inbox/rewizji. Wersja sprzed tej aktualizacji pozostaje w historii Git pod baseline.
