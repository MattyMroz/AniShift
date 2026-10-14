# Dokumenty AniShift: zacznij tutaj

## Używanie działającej aplikacji

[README projektu](../README.md) opisuje uruchomienie, komendy i konfigurację.
[Ustawienia](reference/settings.md) wyjaśniają ustawienia panelu.
Plany opisują zamawiane zmiany, nie gwarantują obecnego zachowania programu.

## Aktualna praca

Pobieranie anime, subskrypcje i ujednolicony panel z czterema zakładkami leżą na
stosie PR #57 → PR #59 i czekają na merge do `main`:

- [masterplan pozyskiwania](work/acquisition/masterplan.md) ze
  [specyfikacją](work/acquisition/spec.md), [kontraktem algorytmu](work/acquisition/algorithm-spec.md)
  i [ekranami](work/acquisition/ux.md);
- [jeden panel, cztery zakładki](work/tui-unify/plan.md) i jego
  [drugi plan](work/tui-unify/plan-02.md).

Pomysły na później, odłożone etapy i decyzje „nie teraz” zbiera jeden plik:
[ideas.md](ideas.md).

## Dowody dostarczonego kodu

- [Etap 06: Manual, Auto i subskrypcje](work/local-automation/06-efficiency/README.md), scalony w PR #56.
- [Audyt niezawodności i wyniki](work/reliability-audit/masterplan.md).
- [Wyniki etapów pozyskiwania](work/acquisition/outcomes/).

Wyniki odnoszą się do opisanych commitów, nie gwarantują dzisiejszej całości.

## Historia i referencje

- [Etapy 1–10](plans/_index.md): historia przebudowy, nie bieżąca kolejka.
- [Dawny pakiet lokalnej automatyzacji](plans/local-automation/README.md) i
  [wcześniejszy pakiet automatyzacji](plans/automation/README.md): historia ustaleń.
- `work/local-automation-2/`: historyczna specyfikacja folderów zadaniowych, wchłonięta przez etap 06 i pozyskiwanie.
- `plans/future/subtitle-layout-engine.md`: koncepcja silnika układu napisów (issue #22).
- `work/10-tui/`: odrzucony Textual; nie przywracać na podstawie dawnych planów.
- `work/plain-cli/`: geneza obecnego Prompt Toolkit i kontrakty interakcji.
- `work/llm-translation/`: wcześniejszy workstream LLM, wdrożony.
- `reference/` i `reports/`: materiały źródłowe, nie nowe zlecenia.
