---
kind: plan
status: pending-human
baseline: 8e63629
created: 2026-09-05
---

# Plan: płynny terminal i kompletne ustawienia

## Cel i zakres

Zrealizować uwagi właściciela do UI: stabilny ekran, czytelny postęp, animowana
maskotka podczas pracy, responsywny branding i wygodne ustawienia. Zachować jeden
renderer Prompt Toolkit, istniejące usługi i kontrakt rzeczywistych procentów.
Bez nowego frameworka, zależności, zmian kluczy użytkownika, live API ani push/PR.
Polecenie użytkownika z 2026-09-05 jest zgodą na ten zakres i tematyczne commity.

## Sprawdzone przyczyny

- `prompts.TerminalRenderer._erase_native_mascot` wywołuje `renderer.reset()`;
  zainstalowany Prompt Toolkit domyślnie wychodzi wtedy z alternate screen.
- `_auto_content` nie daje pustej linii pod marką i jawnie wyłącza maskotkę.
- `progress._description` rezerwuje 14 kolumn, `_short_filename` ucina do 20,
  a ukończenie grupy ustawia zielony styl `success`.
- Audyt ustawień porównuje rzeczywiste schema i kontrolery, nie tylko opis AGENTS.

## Kolejność i właściciele

1. Renderer: regresja opuszczania ekranu, następnie naprawa; jedna przygotowana
   klatka na redraw, usunięcie starego rastra przed narysowaniem nowego widoku.
2. Postęp: krótkie etapy, checkmark, gradient również po sukcesie, dynamiczne
   przycinanie Unicode, odstęp nagłówka, przewijanie przy wielu źródłach.
3. Branding: pełny/średni/kompaktowy wordmark, maskotka również w Auto; żadnego
   kodowania obrazków w renderze. Opcjonalna ograniczona próba fali bez nowej warstwy.
4. Ustawienia: naprawić potwierdzone luki wyborów i modeli, ujednolicić nawigację
   i wskazówki; nie wykonywać odkrywania sieciowego w obsłudze klawisza.
5. Prompty: prześledzić loader, odzyskiwalnie usunąć wyłącznie nieużywane luźne
   pliki; zapisać propozycje wraz z planem ewaluacji, bez podmiany aktywnych promptów.
6. Review, pełne bramki, rzeczywiste podglądy layoutów, raport wyników i następne etapy.

Root integruje, odpowiada za renderer/layout i commity. Pomocnicze audyty ustawień
i promptów mają zakres read-only; implementację można delegować wyłącznie z jawnym
ograniczeniem plików. Żaden agent nie zapisuje ustawień runtime ani sekretów.

## Dowody i warunki wyjścia

- Test rzeczywistego renderera potwierdza brak wyjścia z alternate screen przy
  zniknięciu/przeniesieniu maskotki; wyjście z aplikacji nadal przywraca konsolę.
- Testy layoutów: duży, standardowy, wąski i bardzo niski terminal; wiele źródeł,
  dostępny ostatni wiersz kolejki, stopka, odstęp, pełna nazwa gdy jest miejsce.
- Regresje ustawień: komplet produktów, pierwszy własny model, nieaktualny alias,
  klawisze i paste bez ujawniania sekretów.
- Przed każdym commitem: Ruff check i format, mypy Windows i Linux dla całego
  `anishift/ tests/`, pełne `pytest` wraz z testami bibliotek utils.
- Pomiar renderowania dotyczy konkretnych klatek, nie szybkości zewnętrznego LLM.
- Odbiór człowieka pozostaje jawnie pending: Windows Terminal, resize/zoom,
  Home ↔ Ustawienia, Auto i przewijanie, wygląd animacji i czytelność.

## Granice adaptacji

Dostosowanie wymiarów, etykiet i skrótów jest lokalne, jeśli nie ukrywa istniejących
operacji. Usunięcie ustawienia, zmiana schema, nowy dostawca lub przebudowa pipeline
wymaga przeplanowania. Raport nie obiecuje braku wszystkich możliwych błędów.
