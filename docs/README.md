# Dokumenty AniShift: zacznij tutaj

## Używanie działającej aplikacji

[README projektu](../README.md) opisuje uruchomienie, komendy i konfigurację.
[Ustawienia](reference/settings.md) wyjaśniają ustawienia panelu.
Plany opisują zamawiane zmiany, nie gwarantują obecnego zachowania programu.

## Aktualna praca: lokalna automatyzacja, etap 06

**[Manual, Auto i niezależne subskrypcje: pakiet dla wykonawcy](work/local-automation/06-efficiency/README.md).**

Kolejność: [specyfikacja](work/local-automation/06-efficiency/spec.md), następnie
[plan implementacji P01–P08](work/local-automation/06-efficiency/plan.md).
[Research](work/local-automation/06-efficiency/research/2026-09-08-control-model-research.md)
uzasadnia decyzje kodem i oficjalnymi kontraktami. Pakiet jest gotowy do implementacji;
nie oznacza wdrożenia ani wykonanych testów Windows.

Model: Manual wybiera odcinki; Auto reaguje na pliki; subskrypcje mają osobne
Dodaj/Włącz/Wyłącz/Usuń; Regeneruj korzysta z Auto z żądaniem odtworzenia.
Wszystko rozszerza obecny rdzeń, bez konkurencyjnych wykonawców.

## Dowody dostarczonego kodu

[Audyt i wyniki](work/reliability-audit/masterplan.md),
[Auto](work/reliability-audit/outcomes/05-auto-preset-controls.md),
[terminal](work/reliability-audit/outcomes/04-terminal-polish.md).
[Starsze etapy lokalnej automatyzacji](plans/local-automation/README.md)
pozostają historią implementacji. Wyniki odnoszą się do opisanych commitów,
nie gwarantują dzisiejszej całości ani realizacji nowego planu 06.

## Historia i referencje

- [Etapy 1–10](plans/_index.md): historia przebudowy, nie bieżąca kolejka.
- [Dawny pakiet lokalnej automatyzacji](plans/local-automation/README.md): starsze spec/brief/masterplan/handoff, zastąpione dla obecnej pracy przez pakiet etapu 06.
- [Wcześniejszy pakiet automatyzacji](plans/automation/README.md): historia ustaleń.
- `plans/future/`: odłożone pomysły, nie aktywne polecenia.
- `work/10-tui/`: odrzucony Textual; nie przywracać na podstawie dawnych planów.
- `work/plain-cli/`: geneza obecnego Prompt Toolkit i kontrakty interakcji.
- `work/llm-translation/`: wcześniejszy workstream LLM.
- `reference/` i `reports/`: materiały źródłowe, nie nowe zlecenia.

Nie przenosimy masowo historii ani nie zrywamy jej odnośników. Bieżący kontrakt
etapu 06 ma jedno miejsce w `docs/work/local-automation/06-efficiency/`.
