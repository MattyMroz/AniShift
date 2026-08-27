# application

Czysta warstwa produktu i use case'ów współdzielona przez TUI, CLI i testy.

## Kierunek zależności

- `artifacts.py`, `intents.py`, `planning.py`, `selection.py` i `planner.py` nie importują I/O,
  `anishift.services`, `anishift.config`, CLI ani TUI.
- Kontrolowane I/O należy wyłącznie do `discovery.py`, `inspection.py`,
  `publisher.py`, `sessions.py` i handlerów; decyzje produktowe pozostają w plannerze.
- TUI i CLI używają publicznej fasady `anishift.application`; nie importują
  wewnętrznych helperów I/O ani schedulera.
- Oczekiwany konflikt wejścia jest `PlanProblem`. `PlanningError` oznacza uszkodzony
  kontrakt albo graf, nie zwykłą decyzję użytkownika.

## Inwarianty

- ID grup i odkrytych artefaktów powstają wyłącznie z normalizowanych ścieżek
  względnych. Ręcznie zarejestrowany plik spoza workspace używa znormalizowanej
  ścieżki zewnętrznej wyłącznie jako wejścia stabilnego skrótu; nie używaj `hash()`
  ani losowego UUID.
- `SOURCE` ma `planned_destination == path`, `INTERMEDIATE` nie ma trwałego celu,
  a `DURABLE` otrzymuje `planned_destination` przed wykonaniem.
- `AUTO` nie zawiera ręcznych artifact/track ID. `MANUAL` może wskazać artefakt albo
  embedded track danego rodzaju, nigdy oba jednocześnie.
- `ExecutionPlan.tasks` musi wejść już w porządku zwróconym przez
  `stable_topological_order()`; każdy produkowany artefakt ma jednego producenta.
- Wykonywalny plan nie zawiera `MISSING` bez producenta. Task produkuje wyłącznie
  `MISSING` o lifetime `INTERMEDIATE` albo `DURABLE`, a parametry odpowiadają jego
  `TaskKind`.
- Worker otrzymuje w `ArtifactSnapshot` gotowe wejścia i niezmienne deskryptory
  planowanych wyjść, po czym zwraca `TaskResult`; mutable store pozostaje prywatny
  dla schedulera.

## Testy

```bash
uv run pytest tests/application -v
```
