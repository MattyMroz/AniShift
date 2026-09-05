# Dokumenty AniShift — zacznij tutaj

## Używanie działającej aplikacji

[README projektu](../README.md) opisuje uruchomienie, komendy i konfigurację.
[Ustawienia](reference/settings.md) wyjaśniają każde ustawienie panelu: zakres, wartość
domyślną, silnik, zależności i skutek dla przebiegu.
Plany nie są instrukcją obecnego interfejsu.

## Aktualny kierunek rozwoju

[Automatyzacja: od wyboru anime do oglądania](plans/automation/README.md).
Kolejność: wizja → specyfikacja → masterplan → brief dla Pro → jeden zatwierdzony plan.
Otwarte odłożone zadania mają status w GitHub Issues.

## Dowody dostarczonego kodu

[Audyt i wyniki](work/reliability-audit/masterplan.md),
[Auto](work/reliability-audit/outcomes/05-auto-preset-controls.md),
[terminal](work/reliability-audit/outcomes/04-terminal-polish.md).
Historyczne wyniki dotyczą wskazanego commitu, nie gwarantują dzisiejszej całości.

## Historia i referencje

- [Etapy 1–10](plans/_index.md) — historia przebudowy, nie bieżąca kolejka.
- `plans/future/` — starsze pomysły, w tym odrzucone rozwiązania techniczne.
- `work/10-tui/` — odrzucony Textual; nie przywracać na podstawie tych planów.
- `work/plain-cli/` — geneza obecnego Prompt Toolkit i kontrakty interakcji.
- `work/llm-translation/` — wcześniejszy workstream LLM.
- `reference/` i `reports/` — materiały źródłowe i raporty, nie nowe zlecenia.

Zachowujemy artefakty pod obecnymi ścieżkami. Usuwanie lub masowe przenoszenie
nie daje teraz funkcji użytkowej i łatwo zrywa odnośniki. Aktualne ustalenia
należą do jednego pakietu automatyzacji; Git zachowuje wcześniejsze wersje.
