# Etap 9.5 — wymagania: TUI w gramatyce wizualnej OpenCode

> Status: READY.
> Data: 2026-08-23.
> Baseline stanu repo: `6849f32d4b197aff3507266e55f3d7fbb5c674d4`, branch `feature/stage-9-product-tui`.
> Nadrzędne kontrakty produktu: [etap-9-wymagania.md](etap-9-wymagania.md) i
> [etap-9-interfejs-wymagania.md](etap-9-interfejs-wymagania.md) — obowiązują wszędzie tam,
> gdzie ten dokument jawnie ich nie zmienia (§3.3 wylicza wszystkie zmiany).
> Plan implementacji: [etap-9.5-tui-opencode-plan.md](etap-9.5-tui-opencode-plan.md).
> Wzornik: OpenCode 1.18.21, commit `3a31c4ea801915c0b050df4b3842997ea62b6e93`, licencja MIT,
> klon lokalny w scratchpadzie sesji researchu (ścieżki cytowane względem `packages/tui/src/`).

## 1. Cel etapu i granica wobec Etapu 9

### 1.1. Cel

Etap 9.5 zastępuje odrzuconą warstwę prezentacji `anishift/tui/` (2555 linii) nowym TUI,
które przenosi do Textual **gramatykę wizualną i wzorce interakcji OpenCode**: system
tokenów semantycznych, jeden uniwersalny dialog wyboru, rejestr komend z paletą i slashem,
markery stanu i stopkę ze skrótami z żywej keymapy. Backend Etapu 9 — `anishift/application/`
(28 plików, 7771 linii), planner, scheduler, `AppService`, `field_catalog.py` — pozostaje
bez zmian kontraktu i jest jedynym źródłem danych dla nowego TUI.

Etap 9.5 kończy się tym, czego Etap 9 nie dowiózł po stronie interfejsu: `anishift` bez
argumentów otwiera nowe TUI, `run --preset` wraca do CLI, a stary REPL i `anishift/pipeline/`
znikają po przejściu bramki parytetu.

### 1.2. Diagnoza — dlaczego poprzednie TUI odpada (fakty zweryfikowane w repo)

Odrzucone TUI nie użyło **żadnego** mechanizmu wyglądowego Textual:

- zero `register_theme` / `App.theme`; zero zmiennych designu `$primary`/`$surface`/`$panel`
  (grep po `anishift/tui/` — brak trafień);
- `anishift/tui/theme.tcss` to 156 linii layoutu z 17 hardkodowanymi hexami, bez warstwy
  semantycznej (`theme.tcss:88-94` rozróżnia stan sekretu wyłącznie kolorem — wprost łamiąc
  §3 `etap-9-interfejs-wymagania.md`);
- **ani jednego `BINDINGS`** w całym `anishift/tui/` — aplikacja nie ma skrótów klawiszowych;
- zero `Header`, `Footer`, `TabbedContent`, `Collapsible`, `ProgressBar`, `Tooltip`;
  1 typ obramowania z 19 dostępnych;
- placeholder na produkcji: `anishift/tui/screens/base.py:34`
  („This workflow arrives in the next implementation step.");
- debug-join zamiast UI: `anishift/tui/screens/settings.py:53-58`.

Wniosek przyjęty jako fakt: **warstwa wizualna została porzucona, nie ograniczona przez
Textual**. §13 `etap-9-interfejs-wymagania.md` odłożył design system „do planu i prototypu
Textual", który nigdy nie powstał. Etap 9.5 czyni design system wymaganiem pierwszej klasy
(§4) i nie dopuszcza jego ponownego odroczenia.

### 1.3. Granica: co 9.5 przejmuje z długu Etapu 9, a co w Etapie 9 zostaje

| Element długu Etapu 9 | Decyzja |
|---|---|
| nowe TUI (wszystkie ekrany, dialogi, komendy, design system) | **9.5** — rdzeń etapu |
| przełączenie entrypointu `anishift` → TUI, powrót `run --preset` | **9.5** (przywrócenie zrewertowanego `ed589c5` po bramce §1.4) |
| test parytetu `test_legacy_parity.py` | **9.5** — warunek usunięcia legacy |
| usunięcie `anishift/cli/{shell,commands,completer,pipeline_ui,settings_panel,banner,tts_settings}.py`, całego `anishift/pipeline/`, `tests/pipeline/`, zależności `prompt-toolkit` | **9.5** — po zielonym parytecie i akceptacji HITL |
| Pilot E2E pełnego przepływu na realnym `AppService` (`tests/tui/test_flow.py`) | **9.5** |
| real-media E2E z FFmpeg/MKVToolNix (`tests/e2e/`), osobny job CI E2E | **zostaje w Etapie 9** — dotyczy backendu, nie TUI |
| test obciążeniowy schedulera 100 grup (`tests/load/`) | **zostaje w Etapie 9** |
| dokumentacja końcowa Etapu 9 i zamknięcie issue [#38](https://github.com/MattyMroz/AniShift/issues/38) | **zostaje w Etapie 9** — 9.5 domyka wyłącznie część TUI #38 |

### 1.4. Niewiadoma reverta

Commit `6849f32` („revert(cli): restore legacy shell entrypoint") cofnął przełączenie
entrypointu bez zapisanego powodu. Wymaganie: przed ponownym przełączeniem entrypointu
obowiązuje **technical gate** (plan §F7): manualny smoke nowego TUI na konsoli Windows
(cmd/cp1250 i Windows Terminal) plus jawna akceptacja użytkownika. Bez akceptacji legacy
nie jest usuwane, a entrypoint nie jest przełączany.

## 2. Decyzje już podjęte — nie otwierać ponownie

Decyzja kierunkowa zapadła po researchu pięciu równoległych agentów i została jawnie
zaakceptowana przez użytkownika:

1. **Zostajemy w Pythonie i Textual 8.2.8.** OpenCode jest wzornikiem języka wizualnego
   i wzorców interakcji — nie zależnością, nie celem migracji.
2. Powody (streszczenie, pełne dowody w raportach researchu):
   - koszt: dopisanie brakującej polerki w Textual to 2–5 dni nauki nieużywanych API
     wobec 6–10 tygodni nauki SolidJS+OpenTUI i ~4–7 tys. linii mostu stdio/HTTP;
   - Windows: OpenTUI ma 29 zgłoszeń „windows", w tym otwarty segfault w `opentui.dll`
     i wyciek uchwytu stdin; Textual ma 10, żadnego segfaulta. AniShift jest Windows-only;
   - dojrzałość: `@opentui/core` to 321 wersji npm w 12 miesięcy na numeracji 0.x, bez
     CHANGELOG-a; sam OpenCode stoi na 0.4.5 wobec HEAD 0.5.7. Textual 8.2.8 ma stabilne API;
   - utrzymanie: drugi toolchain bez strażników repo (hooki, ruff, mypy) i utrata
     29 testów Pilot.
3. Odnotowane ryzyko kontrargumentu: **Textual ma bus factor 1** — Textualize zakończyło
   działalność 2025-05-07, 99 ze 100 ostatnich commitów pochodzi od jednej osoby.
   Reakcja w planie (ryzyka), nie powód zmiany decyzji.
4. Werdykt użytkownika o starym TUI („totalna klapa", „wielkie batony", „teksty nakładają
   się na siebie") jest ostateczny: **TUI piszemy od nowa.** Nie ratujemy ekranów; wolno
   ponownie użyć sprawdzonych wzorców wewnętrznych (drenaż `EventBuffer`, bramka generacji,
   drafty w `SessionState`), ale żaden istniejący plik `anishift/tui/` nie jest chroniony.

## 3. Inwentarz: co znika, co zostaje, co się zmienia

### 3.1. Zostaje bez zmian kontraktu (fundament)

| Obszar | Pliki | Rola w 9.5 |
|---|---|---|
| warstwa aplikacji | `anishift/application/` — 28 plików, 7771 linii (`planner.py` 1198, `runtime.py` 532, `inspection.py` 499, `service.py` 453 itd.) | jedyne źródło danych i use case'ów TUI; `AppService` ma komplet metod potrzebnych 9.5 (`service.py:131-327`) |
| katalog ustawień | `anishift/config/field_catalog.py` — 1267 linii, 58 miejsc definicji `SettingSpec`; `setting_catalog(context)` zwraca 54–60 aktywnych pól zależnie od kontekstu silnika | źródło prawdy ekranu ustawień (§7) |
| zdarzenia i wyniki | `anishift/application/events.py` (`RunEventKind`: run_started…run_finished, `EventBuffer`), `results.py` (`RunResult`, `GroupStatus`) | zasilanie ekranu Execution/Results |
| CLI techniczne | `anishift/cli/main.py` — `doctor`, `setup` | zostają; `_default` przechodzi na TUI w fazie F7 |
| testy backendu | 2034 passed / 8 skipped na baseline (pełne `uv run pytest`, exit 0 — zweryfikowane) | mają pozostać zielone po każdej fazie |

### 3.2. Znika (przepisanie lub kasacja)

| Plik | Los |
|---|---|
| `anishift/tui/app.py` (238), `state.py` (153), `messages.py` (90), `commands.py` (41), `theme.tcss` (156) | przepisane od nowa w nowej strukturze (plan §D-1) |
| `anishift/tui/screens/` — `manual.py` 251, `auto.py` 206, `settings.py` 189, `workspace.py` 129, `results.py` 125, `tools.py` 99, `preview.py` 97, `base.py` 57, `execution.py` 52, `__init__.py` 21 | przepisane; `base.py` (PlaceholderScreen) i `settings.py` (ekran) znikają bez następcy 1:1 — ustawienia stają się dialogiem (§3.3) |
| `anishift/tui/widgets/` — `intent_form.py` 211, `setting_field.py` 124, `group_table.py` 90, `progress_table.py` 79, `plan_view.py` 74, `command_bar.py` 63 | przepisane; czyste helpery `_setting_value`/`_assign_setting`/`_setting_is_active` z `screens/settings.py:148-189` przenoszą się do modułu poza TUI (plan §D-6) |
| `tests/tui/` — 29 testów Pilot w 10 plikach | zastępowane per faza nowymi testami Pilot; liczba testów TUI po 9.5 nie może być mniejsza niż 29 |
| `anishift/cli/shell.py`, `commands.py`, `completer.py`, `pipeline_ui.py`, `settings_panel.py`, `banner.py`, `tts_settings.py` | usuwane w F7 po bramce parytetu |
| `anishift/pipeline/` — 13 plików + `tests/pipeline/` — 10 plików | usuwane w F7 po bramce parytetu |
| zależność `prompt-toolkit` | `uv remove prompt-toolkit` w F7 |

### 3.3. Decyzje ZMIENIONE względem Etapu 9 (jawna lista delty kontraktu)

| # | Etap 9 mówił | Etap 9.5 mówi | Powód |
|---|---|---|---|
| Z-1 | Settings to osobny ekran z polami formularza i przyciskami `Save`/`Cancel` (`etap-9-interfejs-wymagania.md` §5.4) | `/settings` to **drzewo dialogów wyboru** nad bieżącym ekranem, w modelu `/session` z OpenCode; osobny ekran Settings nie istnieje | twarde żądanie użytkownika (§7.1); wzorzec zweryfikowany w OpenCode (`ui/dialog-select.tsx`, 20 z 26 dialogów) |
| Z-2 | „Zmiany trafiają do wersji roboczej. `Save` zapisuje je jawnie, a `Cancel` przywraca stan wejściowy" | **zapis natychmiastowy po każdej zatwierdzonej zmianie pola** (wybór z listy → walidacja → atomowy zapis → powrót do rodzica); brak globalnego `Save`/`Cancel` | model OpenCode „lista → wybór → natychmiastowy efekt"; precedens w repo: legacy panel zapisywał po każdym kroku (`anishift/cli/AGENTS.md`: „Każda zmiana w panelu jest natychmiast zapisywana na dysk"); run w toku chroni niezmienny `RunSettingsSnapshot` (`AppService.execute`), więc zapis nie dotyka aktywnej pracy |
| Z-3 | „Cofnięcie ekranu nie kasuje bez pytania wprowadzonych zmian" (dot. formularzy ustawień) | dla ustawień: `escape` w dialogu-dziecku porzuca **niezatwierdzoną** zmianę bez pytania (nic nie zostało zapisane); wyjątek: dialogi z live preview robią rollback (§5.6). Dla draftów Auto/Manual reguła Etapu 9 obowiązuje bez zmian | konsekwencja Z-2: nie ma „wprowadzonych zmian" poza zatwierdzonymi |
| Z-4 | mapa przepływu zawiera węzeł ekranowy `SETTINGS` | routing ekranów: `workspace, auto, manual, preview, execution, results, tools`; komenda `settings` otwiera dialog, nie ekran | Z-1 |
| Z-5 | „nie projektujemy jeszcze szczegółowego układu ekranów ani skrótów klawiszowych" | 9.5 projektuje układ, skróty i design system **w całości, w tym dokumencie i planie** | to odroczenie zabiło Etap 9 |

Wszystkie pozostałe wymagania Etapu 9 (model produktu, planner, tryby auto/manual, command
bar `❯`, zachowanie preview/execution/results, granica CLI, minimalny rozmiar 100×30)
obowiązują bez zmian.

## 4. Design system — wymaganie, nie obietnica

To jest kontrakt wyglądu. Wykonawca nie podejmuje żadnej decyzji wizualnej poza wartościami
hex w palecie (kolory to gust — użytkownik zaakceptował, że mogą różnić się od OpenCode;
gramatyka nie może).

### 4.1. Tokeny semantyczne

**R-101.** Istnieje dokładnie jeden moduł palety (`anishift/tui/theme.py` — plan §D-2),
który jako **jedyny plik w całym `anishift/tui/`** może zawierać literały kolorów (hex).
Wszystkie pliki `.tcss` i cały kod widgetów używają wyłącznie tokenów `$...`.

**R-102.** Zestaw tokenów składa się z 11 slotów bazowych `textual.theme.Theme`
(`primary`, `secondary`, `accent`, `warning`, `error`, `success`, `foreground`,
`background`, `surface`, `panel`, `boost`) oraz z 8 zmiennych własnych aplikacji
dostarczanych przez `App.get_theme_variable_defaults()` / `Theme.variables`:

| Token własny | Rola (odpowiednik OpenCode `theme/index.ts:35-92`) |
|---|---|
| `$border` | spokojne obramowanie paneli (`border`) |
| `$border-active` | obramowanie/podkreślenie elementu z fokusem (`borderActive`) |
| `$border-subtle` | separatory i linie pomocnicze (`borderSubtle`) |
| `$overlay` | przyciemniona zasłona pod dialogiem (odpowiednik `RGBA(0,0,0,150)` z `ui/dialog.tsx:48`) |
| `$marker-current` | kolor markera `●` aktualnej wartości (u OpenCode `theme.primary`, `ui/dialog-select.tsx:750`) |
| `$footer-key` | klawisz w stopce skrótów |
| `$footer-label` | opis akcji w stopce skrótów |
| `$input-cursor` | kursor pól tekstowych (`cursorColor: theme.primary`, `dialog-select.tsx:581`) |

Tokeny pochodne (`$text-muted`, `$text-primary`, `$primary-darken-1` itd.) generuje
`ColorSystem` Textual — nie definiuje się ich ręcznie.

**R-103.** Semantyka użycia jest wiążąca: `error`/`warning`/`success`/`accent` wyłącznie do
znaczenia stanu, nigdy do dekoracji; `panel` to tło każdego dialogu; `boost` to tło
wyróżnionego wiersza pomocniczego; `primary` to fokus/zaznaczenie/marker.

### 4.2. Motywy jasny/ciemny

**R-104.** Aplikacja rejestruje dokładnie dwa motywy: `anishift-dark` (domyślny)
i `anishift-light`, oba zdefiniowane w module palety, oba pokrywające komplet tokenów
z R-102. Przełączanie: komenda `themes` (paleta i slash) otwierająca dialog wyboru motywu
z live preview i rollbackiem (§5.6). Wybrany motyw jest utrwalany w `config/settings.json`?
— **Nie.** Motyw jest preferencją prezentacji, nie ustawieniem pipeline'u: trafia do
osobnego, płaskiego pliku stanu UI `config/ui_state.json` (wzorzec `kv.json` OpenCode:
zapis atomowy po każdej zmianie, brak schematu domenowego, zła zawartość = ignorowana
z ostrzeżeniem w logu). Plik jest gitignorowany razem z `config/settings.json`.

**R-105.** Auto-detekcji jasny/ciemny z OSC 10/11 **nie implementujemy** (Textual jej nie
ma; OpenCode ma — świadome cięcie zakresu). Domyślny motyw to `anishift-dark`.

### 4.3. Kolor nigdy nie jest jedynym nośnikiem stanu — kompletna tabela nośników

**R-106.** Każdy stan prezentowany w TUI ma dwa niezależne nośniki: glif **i** słowo
(albo glif i pozycję strukturalną). Obowiązujący zestaw znaczników (moduł `icons`,
plan §D-2):

| Stan | Glif | Drugi nośnik | Token koloru |
|---|---|---|---|
| aktualna wartość na liście | `●` | pozycja w kolumnie gutter przed tytułem | `$marker-current` |
| kursor listy | tło wiersza | pełnowierszowe podświetlenie + bold | `$primary` (tło), `$background` (tekst) |
| włączone / sukces | `✓` | słowo (`enabled`, `succeeded`, `ok`) | `$success` |
| wyłączone | `○` | słowo (`disabled`, `off`) | `$text-muted` |
| błąd / porażka | `✗` | słowo (`failed`, `error`) + skrócony komunikat | `$error` |
| ostrzeżenie / częściowy sukces | `⚠` | słowo (`warning`, `partial`) | `$warning` |
| w trakcie | spinner braille (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`, 10 klatek, interwał 100 ms) | słowo (`running`) | `$accent` |
| w kolejce / ładowanie | `⋯` | słowo (`queued`, `loading`) | `$text-muted` |
| anulowane | `○` | słowo (`cancelled`) | `$text-muted` |
| zablokowane | `⚠` | słowo (`blocked`) + powód | `$warning` |
| prompt command bara | `❯` | stała pozycja na dole ekranu | `$primary` |
| nawigacja „wejdź głębiej" | `▸` | pozycja na końcu wiersza | `$text-muted` |

Zakaz: para klas różniących się wyłącznie kolorem (obecny antywzorzec
`theme.tcss:88-94`). Ikony emoji z `utils/rich_console` (`✅`, `❌`…) pozostają w CLI
(`doctor`) i są nietykalne (pamięć projektu); TUI używa wyłącznie zestawu z tej tabeli.

### 4.4. Gramatyka obramowań i gęstość

**R-107.** Obramowania:
- **dialogi nie mają ramki** — wyróżnia je wyłącznie tło `$panel` na zasłonie `$overlay`
  (wiernie za `ui/dialog.tsx:44-60`: „Brak ramki. Panel wyróżnia wyłącznie kolor tła");
- panele treści na ekranach używają co najwyżej `border: round $border`, a przy fokusie
  `$border-active`; żadnych `solid`+`heavy` mieszanek;
- separatory poziome to `Rule`/linia w `$border-subtle`, nie puste `Static`.

**R-108.** Gęstość: wiersz listy ma wysokość 1; opis pod tytułem tylko w wierszu
podświetlonym lub jako `details` (wzorzec `dialog-select.tsx:694-702`); padding paneli
1 znak w pionie, 2 w poziomie; ekrany nie używają pustych wierszy jako layoutu (spacing
przez padding/margin w TCSS).

**R-109.** Wyrównanie kolumn list: nazwy dopełniane do najdłuższej + 2 spacje, opisy
zaczynają się w jednej pionowej linii (wzorzec `padEnd` z `autocomplete.tsx:468-473`).
Wartości/status w wierszu wyrównane do prawej (slot `footer` wiersza).

### 4.5. Siatka szerokości dialogów

**R-110.** Dialogi mają dokładnie trzy szerokości: `medium = 60`, `large = 88`,
`xlarge = 116` kolumn, każda ograniczona do `szerokość_terminala − 2`
(`ui/dialog.tsx:22-26`). Panel jest wyśrodkowany poziomo, a jego górna krawędź leży na
`wysokość_terminala // 4` (`ui/dialog.tsx:45`). Maksymalna wysokość listy w dialogu:
`wysokość_terminala // 2 − 6`, dłuższa zawartość przewija się wewnątrz.

**R-111.** Przypisanie szerokości: paleta komend, wybory pojedyncze, prompty, liczby,
potwierdzenia → `medium`; korzeń ustawień, edytor presetu, formularz intencji manual,
listy z kolumną wartości → `large`; podgląd planu w dialogu (jeśli użyty) → `xlarge`.

### 4.6. Rozpoznawalność względem OpenCode

**R-112.** „Wygląd bardzo podobny do OpenCode" jest sprawdzalny przez listę kontrolną
(AC-HITL-1): przyciemniona zasłona + bezramkowy panel w górnej ćwiartce; filtr z kursorem
od otwarcia; `●` przy aktualnej wartości wizualnie oddzielony od podświetlenia kursora;
stopka dialogu z akcjami `tytuł klawisz`; kolumnowe wyrównanie nazw i opisów; stały
command bar `❯` i pasek statusu na dole. Palety kolorów mogą się różnić.

## 5. Kontrakt dialogu wyboru — jeden widget dla wszystkiego

### 5.1. Zasada

**R-201.** Istnieje dokładnie jeden widget listy wyboru (`SelectDialog`), z którego
zbudowane są: paleta komend, wybór motywu, wszystkie kategorie i pola-listy ustawień,
wybory w edytorze presetu auto i formularzu manual oraz każdy przyszły dialog wyboru.
Te same klawisze działają wszędzie. (OpenCode: `ui/dialog-select.tsx` 791 linii używany
przez 20 z 26 dialogów.)

### 5.2. Anatomia

```
(zasłona: $overlay na całym ekranie; klik w zasłonę zamyka)
        ┌─ panel bez ramki, tło $panel, szer. wg §4.5 ─┐
        │  Tytuł                                  esc  │  ← nagłówek: bold; „esc" $text-muted, klikalne
        │  Search_                                     │  ← filtr, FOKUS OD OTWARCIA
        │  Kategoria                                   │  ← nagłówek grupy: $accent bold
        │ ● opcja-aktualna            wartość/status   │  ← ● w gutterze; footer wiersza z prawej
        │ ▓ opcja-podświetlona ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  ← kursor: tło $primary, bold
        │   opcja-trzecia                              │
        │   (brak wyników: „No results", $text-muted)  │
        │  akcja1 klawisz   akcja2 klawisz             │  ← stopka akcji; etykiety z ŻYWEJ keymapy
        └──────────────────────────────────────────────┘
```

### 5.3. Kontrakt wejścia (parametry)

**R-202.** `SelectDialog` przyjmuje: `title`, `placeholder` (domyślnie „Search"),
`options` (dla każdej: `value`, `title`, `description?`, `footer?` — tekst lub renderowalny
status, `category?`, `disabled?`), `current?` (wartość oznaczana `●`), `actions?`
(lista: etykieta, komenda z przypisanym klawiszem, handler na podświetlonej opcji),
`multi?` (tryb przełączania zbioru — §5.5), `on_move?` (hak live preview — §5.6),
`initial_highlight?` (wartość, na której startuje kursor — §7.4), `size`
(`medium`/`large`/`xlarge`). Opcja `disabled` jest odfiltrowana z listy, nie wyszarzona
(`dialog-select.tsx:152-158`).

### 5.4. Pełna mapa klawiszy

**R-203.** Obowiązuje w każdym wystąpieniu dialogu:

| Klawisz | Efekt |
|---|---|
| dowolny znak drukowalny | filtr inkrementalny (pole filtra ma fokus od otwarcia; strzałki NIE są potrzebne do pisania) |
| `up` / `down` | poprzednia/następna opcja, z zawijaniem na końcach |
| `pageup` / `pagedown` | ±10 opcji |
| `home` / `end` | pierwsza / ostatnia opcja |
| `enter` | zatwierdź podświetloną opcję (albo sfokusowaną akcję stopki) |
| `tab` / `shift+tab` | cykl po akcjach stopki (tylko gdy `actions` niepuste) |
| `escape` | zamknij dialog bez efektu; przywróć fokus elementowi sprzed otwarcia |
| `ctrl+c` | jak `escape` (gdy dialog otwarty) |
| klawisz akcji (np. `space`) | wykonaj akcję na podświetlonej opcji |

**R-204.** Zachowanie kursora przy filtrze: zmiana filtra ustawia kursor na pozycję 0;
wyczyszczenie filtra przywraca kursor na `current` (`dialog-select.tsx:264-278`).
Przy niepustym filtrze nagłówki kategorii znikają (lista płaska, żeby nie rozbijać
rankingu — `dialog-select.tsx:184`).

**R-205.** Filtrowanie dialogu: fuzzy po `title` (waga ×2) i `category` (waga ×1),
bez limitu, bez progu — lista przewijalna (`dialog-select.tsx:154-172`).

**R-206.** Dialogi się **nie stackują**. Jedyne operacje to `replace()` (podmiana całej
zawartości) i `clear()` (zamknięcie z przywróceniem fokusu) — `ui/dialog.tsx:139-176`.
„Wejście głębiej" to podmiana; „powrót" to jawne, ponowne otwarcie rodzica z
`initial_highlight` ustawionym na pozycję, z której zeszliśmy (§7.4). `escape` zawsze
zamyka wierzchni dialog całkowicie — wyjątkiem jest dialog-dziecko drzewa ustawień,
którego `escape` otwiera z powrotem rodzica (§7.4); to zachowanie jest projektowane
lepiej niż w OpenCode, gdzie powrót wymagał ręcznego kodu w każdym kreatorze
(`dialog-provider.tsx:283,334,415`).

### 5.5. Tryb zbioru (multi)

**R-207.** W trybie `multi` (zbiory: `requested_products`, `mkv_tracks`,
`llm_module_ids`): `space` przełącza podświetloną pozycję **bez zamykania dialogu**;
`enter` zamyka dialog zatwierdzając bieżący zbiór; slot `footer` każdego wiersza pokazuje
`✓ on` / `○ off` (wzorzec `dialog-mcp.tsx:10-19,80-82`: „`return` nie robi nic" —
u nas `enter` = zatwierdź-i-wróć, bo dialog jest edytorem pola, a nie trwałym panelem).
Każdy toggle jest walidowany dopiero przy zatwierdzeniu całego zbioru.

### 5.6. Live preview z rollbackiem

**R-208.** Dialog z `on_move` stosuje wartość podświetlonej opcji natychmiast przy ruchu
kursora; `enter` utrwala; `escape` przywraca wartość sprzed otwarcia. Przy niepustym
filtrze podgląd stosuje pierwszy wynik; pusty filtr przywraca wartość wejściową.
(Wiernie za `component/dialog-theme-list.tsx:17-47` — najlepszy pojedynczy wzorzec
OpenCode.) Zakres użycia w 9.5: **wyłącznie wybór motywu**. Podgląd głosu TTS wymagałby
syntezy (płatnej/sieciowej) — zakazany.

### 5.7. Pozostałe prymitywy dialogowe

**R-209.** Obok `SelectDialog` istnieją dokładnie cztery dodatkowe prymitywy, wszystkie
w tej samej ramie wizualnej (§5.2, zasłona + panel bez ramki):

| Prymityw | Kontrakt |
|---|---|
| `PromptDialog` | jedno pole tekstowe z opisem; `enter` = zatwierdź (tylko gdy walidacja przechodzi), `escape` = anuluj; błąd walidacji wyświetlany pod polem w `$error` wraz z regułą, pole nie traci treści |
| `NumberDialog` | pole liczbowe: pokazuje aktualną wartość, dozwolony zakres `[min, max]` i default; `up`/`down` zmienia o krok (int: 1; float: 0.1), wpisywanie dozwolone; walidacja inline na każdą zmianę; `enter` aktywne tylko dla wartości poprawnej; dla typów `OPTIONAL_*` puste pole oznacza „brak wartości (użyj domyślnej silnika)" i jest jawnie podpisane |
| `ConfirmDialog` | dwie opcje Cancel/Confirm; `left`/`right` przełącza, `enter` wykonuje, `escape` = Cancel; wariant destrukcyjny/płatny ma tytuł z `⚠` i wypisuje skutek |
| `ReorderDialog` | uporządkowana lista (priorytety języków, fallback chain): `up`/`down` przesuwa kursor, `shift+up`/`shift+down` przesuwa element, `a` dodaje (child-select z dozwolonych wartości albo prompt), `d`/`delete` usuwa, `enter` zatwierdza całość, `escape` porzuca; stopka akcji dokumentuje wszystkie klawisze |

`NumberDialog` i `ReorderDialog` to obszary, w których OpenCode **nie ma żadnego wzorca**
(zero widgetów numerycznych, zero list porządkowanych — ustalone w researchu). Projektujemy
je sami; powyższy kontrakt jest wiążący.

**R-210.** Stopka akcji każdego dialogu renderuje etykiety klawiszy **z żywej keymapy**
(z definicji `BINDINGS`/komend), nigdy z hardkodowanego napisu — po zmianie bindingu
stopka mówi prawdę (`dialog-select.tsx:120-137`).

## 6. Kontrakt komend

### 6.1. Model danych

**R-301.** Jedna komenda to rekord o polach (wzorzec potwierdzony w
`app.tsx:571-640`, `keymap.tsx:272-289`):

```text
name            str        identyfikator kropkowany, np. "settings.open", "run.cancel"
title           str | () -> str    etykieta w palecie; dla przełączników tytuł opisuje AKCJĘ
                                   („Disable X" / „Enable X" — app.tsx:893-900), nie stan
description     str | None  zdanie pokazywane w slashu i palecie
category        str         nagłówek grupy w palecie: "Workspace", "Run", "Settings", "System", "Help"
hidden          bool        ukrywa w palecie i slashu (np. komenda otwarcia samej palety)
enabled         () -> bool  predykat; komenda wyłączona nie pojawia się nigdzie
suggested       () -> bool  predykat; True wynosi komendę do pseudo-grupy „Suggested"
slash_name      str | None  bez tej wartości komenda nie istnieje w slashu
slash_aliases   tuple[str, ...]  dodatkowe klucze fuzzy, NIE osobne wpisy listy
keys            tuple[str, ...]  skróty klawiszowe (podstawa BINDINGS ekranu i etykiet stopki)
run             wywołanie use case'u / nawigacji — bez argumentów
```

**R-302.** Rejestr komend jest jeden. Ekran rejestruje własne komendy przy montowaniu
i wyrejestrowuje przy odmontowaniu — zbiór dostępnych komend zmienia się wraz z aktywnym
ekranem (wzorzec `useBindings`; w Textual: rejestracja w `on_mount`/`on_unmount` +
`BINDINGS` ekranu). `dispatch(name)` jest **jedynym punktem wykonania** dla palety,
slasha, skrótu klawiszowego i przycisku (`app.tsx:986-989`).

**R-303.** Predykaty stanu są obowiązkowe tam, gdzie stan je definiuje, co najmniej:
`run.cancel` enabled tylko podczas aktywnego runu; `results.open` enabled tylko gdy
istnieje wynik w sesji; `run.start` suggested gdy plan preview jest wykonalny;
`tools.setup` suggested gdy doctor zgłasza brak binarki.

### 6.2. Paleta komend

**R-304.** `ctrl+p` otwiera paletę: `SelectDialog` (medium) z opcjami ze wszystkich
aktualnie zarejestrowanych, niescrytych, enabled komend; grupowanie po `category`;
przy pustym filtrze na górze pseudo-grupa **„Suggested"** (duplikaty opcji z prefiksem
wartości, znikają przy pisaniu — `command-palette.tsx:63-76`); każdy wiersz pokazuje
w slocie `footer` skrót klawiszowy komendy z żywej keymapy; paleta nie pokazuje samej
siebie (`command-palette.tsx:15-17`). Wybór = `clear()` + `dispatch(name)`.
Wbudowana paleta Textual jest wyłączona — `ctrl+p` należy do naszej (uzasadnienie:
R-201 „jeden widget = te same klawisze wszędzie").

### 6.3. Command bar i slash

**R-305.** Command bar z promptem `❯` jest stale widoczny na dole każdego ekranu
(kontrakt Etapu 9, decyzja 23 — bez zmian). Fokus: skrót `/` (gdy żaden input nie ma
fokusu) albo klik. Przyjmuje polecenia w dwóch pisowniach równoważnie: `refresh`
i `/refresh`.

**R-306.** Podczas pisania w command barze nad nim pojawia się popup autouzupełniania
(max 10 wierszy, wysokość `min(10, liczba_opcji)`): lista komend posiadających
`slash_name`, filtrowana fuzzy wg §6.4. `up`/`down` nawiguje, `enter` wykonuje
podświetloną, `tab` dopełnia tekst, `escape` chowa popup. Wybór czyści pole. Pusty
`enter` nie robi nic; nieznane polecenie nie ma efektu ubocznego i pokazuje błąd
z sugestią najbliższej nazwy.

**R-307.** Command bar nie przyjmuje argumentów ani nazw wewnętrznych etapów pipeline'u.
Słownik = komendy z `slash_name`; zawiera co najmniej: `workspace`, `auto`, `manual`,
`settings`, `themes`, `refresh`, `doctor`, `setup`, `results`, `cancel`, `help`, `quit`.

### 6.4. Pięć reguł fuzzy — wszystkie obowiązkowe

**R-308.** Filtrowanie slasha (i każdej listy „nigdy niepustej") implementuje dokładnie
pięć decyzji z `autocomplete.tsx:495-522`:

1. **prefix boost ×2** — wynik dopasowania jest podwajany, gdy kandydat zaczyna się od
   wpisanego tekstu (wpisanie `se` wynosi `settings` ponad wszystko z `se` w środku);
2. **próg 0** — lista nigdy nie jest pusta; zawsze widać najlepsze dopasowania,
   choćby słabe;
3. **twardy limit 10** pozycji;
4. **aliasy jako klucz fuzzy**, nie jako osobne wpisy (alias podbija dopasowanie,
   nie zaśmieca listy);
5. **wyrównanie kolumn** — nazwy dopełnione do najdłuższej + 2, opisy w jednej pionowej
   linii (R-109).

Dodatkowo opis (`description`) jest przeszukiwany — zbiór komend jest mały, dokładnie
reżim, w którym OpenCode to włącza. Silnik dopasowania: `textual.fuzzy.FuzzySearch`
z własnym boostem — bez nowej zależności. Pułapka odnotowana: `frecency.tsx` OpenCode
**nie dotyczy komend** i jego mnożnik jest martwy — nie kopiujemy.

### 6.5. Skróty klawiszowe ekranów

**R-309.** Każdy ekran definiuje `BINDINGS` (Textual) spójne z `keys` swoich komend.
Minimalna mapa globalna i per ekran:

| Zakres | Klawisz | Akcja |
|---|---|---|
| globalnie | `ctrl+p` | paleta komend |
| globalnie | `/` | fokus command bara |
| globalnie | `escape` | zamknij dialog / wróć o ekran (nigdy nie anuluje runu bez potwierdzenia) |
| globalnie | `f1` | pomoc (ekran + skróty) |
| globalnie | `ctrl+q` | wyjście (z potwierdzeniem przy aktywnym runie) |
| workspace | `space` | zaznacz/odznacz grupę |
| workspace | `a` / `m` / `s` / `t` | Auto / Manual / Settings(dialog) / Tools |
| workspace | `r` | refresh |
| auto/manual | `p` | plan preview |
| preview | `enter` na przycisku Start | start (modal potwierdzenia dla operacji płatnych/nadpisujących) |
| execution | `c` | cancel (z potwierdzeniem) |
| execution | `f` | cykl filtra `all → running → failed → done` |
| results | `enter` | szczegóły grupy |

Stopka ekranu pokazuje 4–5 najważniejszych skrótów bieżącego ekranu — renderowanych
z żywych `BINDINGS` (R-210).

## 7. Kontrakt ustawień — 58 pól, zero podzbioru

### 7.1. Wymaganie centralne: `/settings` działa jak `/session` w OpenCode

**R-401.** Komenda `settings` (paleta, slash, klawisz `s` na workspace) otwiera **dialog
korzenia ustawień** (`SelectDialog`, large) nad bieżącym ekranem. Nawigacja: przechodzisz
po pozycjach, wybierasz pozycję → otwiera się dialog-dziecko właściwego typu → wybierasz
wartość → efekt natychmiastowy → **powrót do rodzica z kursorem na pozycji, z której
zszedłeś, i z odświeżonym podsumowaniem wartości**. To jest centralny wymóg UX etapu;
jego mechanika (`replace` + `initial_highlight`) jest opisana w §5 i wiążąca.

**R-402.** Sześć składników intuicyjności — wszystkie obowiązkowe w całym drzewie:
(1) jedno wejście: paleta + slash + klawisz; (2) jeden widget = te same klawisze wszędzie;
(3) filtr sfokusowany od otwarcia — pisanie jest podstawową nawigacją; (4) marker `●`
przy aktualnej wartości, wizualnie oddzielony od podświetlenia kursora; (5) globalny
`escape` z przywróceniem fokusu; (6) skróty akcji w stopce z żywej keymapy.

### 7.2. Struktura korzenia

**R-403.** Korzeń pokazuje pola o zakresach `GLOBAL`, `ENGINE_PROFILE` i `SECRET`
z `setting_catalog(context)` (kontekst z aktualnych ustawień), pogrupowane w kategorie:

| Kategoria | Pola (setting_id) |
|---|---|
| Workflow | `processing_order_policy`, `audio_language_priority`, `subtitle_language_priority` |
| Translation | `translation_engine`, `translation_fallback_chain`, `translation_batch_size`, `translation_concurrency`, `translation_max_retries` |
| LLM | `llm_provider`, `llm_provider_model_id`, `llm_temperature`, `llm_top_p`, `llm_max_output_tokens`, `llm_prompt_id`, `llm_style_id`, `llm_module_ids`, `llm_max_concurrency`, `openai_compatible_base_url` |
| TTS | `tts_engine`, `tts_provider_model_id`, `tts_voice_id`, `tts_max_retries`, `elevenbytes_vpn_enabled`, `elevenbytes_custom_voices`, wszystkie `tts_profile.*` aktywnego silnika/głosu (w tym `engine_options.*`) |
| Audio | `tts_output_profile`, `tts_output_bitrate`, `narrator_mix_base_gain_db`, `original_gain_db` |
| Composition | `composition_quality_preset` |
| Secrets | 8 kluczy API (`deepl_api_key` … `openai_compatible_api_key`) |

Wiersz korzenia = etykieta pola + aktualna wartość (skrócona) wyrównana do prawej +
`▸` dla pól otwierających dziecko. Pola nieaktywne wg `depends_on` **nie są renderowane**
(znikają z aktywnego schematu — kontrakt Etapu 9 §13.4, egzekwowany przez
`_setting_is_active`, dziś w `anishift/tui/screens/settings.py:183-189`).

**R-404.** Pola o zakresie `AUTO_PRESET` (8: `subtitle_source_policy`,
`source_subtitle_language`, `subtitle_output_format`, `translation_action`,
`requested_products`, `burn_subtitle_product`, `mkv_tracks`, `mp4_audio_source`) są
edytowane **tymi samymi dialogami** na ekranie Auto (edytor presetu); pola `MANUAL_RUN`
(6: `preferred_video_artifact_id`, `selected_subtitle_artifact_id`,
`selected_subtitle_track_id`, `selected_audio_artifact_id`, `selected_audio_track_id`,
`external_audio_role`) — na ekranie Manual (formularz intencji grupy). Razem trzy
konteksty pokrywają **komplet katalogu**; test kompletności jest wymagany (AC-407).

### 7.3. Wzorzec interakcji per typ pola — wszystkie 10 typów `SettingValueType`

**R-405.** Obowiązująca tabela (typ → dialog → walidacja → zachowanie przy błędzie).
Tam, gdzie OpenCode nie ma wzorca, projektujemy sami — oznaczone „(własny projekt)":

| Typ z `field_catalog.py:81-93` | Pola przykładowe | Wzorzec | Walidacja | Błąd |
|---|---|---|---|---|
| `STRING` z `allowed_values` | `translation_engine`, `tts_engine`, `composition_quality_preset`, `llm_prompt_id` | `SelectDialog` single: `●` current, `enter` = ustaw + wróć do rodzica | wartość ∈ `allowed_values` (gwarantowane przez listę) + `spec.validate_value()` | niemożliwy przez UI; błąd zapisu → §7.5 |
| `STRING` wolny | `openai_compatible_base_url`, `tts_profile.native_rate/volume/pitch` (formaty tekstowe silnika) | `PromptDialog` z opisem i wzorem formatu (np. `-100%…+100%`) | `spec.validate_value()` + `validation_pattern` inline przy każdej zmianie | komunikat pod polem w `$error` z regułą; `enter` nieaktywne; treść pola zachowana |
| `OPTIONAL_STRING` | `source_subtitle_language`, `tts_output_bitrate` | `PromptDialog`; puste pole = brak wartości (jawny podpis „empty = default") | jak wyżej, pusta wartość legalna | jak wyżej |
| `INTEGER` | `translation_concurrency` (1–16), `translation_max_retries` (0–10), `tts_profile.concurrency` | `NumberDialog` (własny projekt, R-209): zakres widoczny, `up`/`down` krok 1 | zakres `[minimum, maximum]` inline | wartość poza zakresem: komunikat + `enter` nieaktywne |
| `OPTIONAL_INTEGER` | `llm_max_output_tokens`, `selected_*_track_id` | `NumberDialog`, puste = brak | jak wyżej | jak wyżej |
| `FLOAT` | `tts_profile.postprocess_tempo` (0.5–2.0), `narrator_mix_base_gain_db`, `engine_options.stability` (0–1) | `NumberDialog`, krok 0.1 | zakres inline | jak wyżej |
| `OPTIONAL_FLOAT` | `llm_temperature` (0–2), `llm_top_p` (0–1) | `NumberDialog`, puste = brak | jak wyżej | jak wyżej |
| `BOOLEAN` | `elevenbytes_vpn_enabled`, `engine_options.use_speaker_boost` | **toggle w miejscu** w liście rodzica: `enter`/`space` przełącza, wiersz pokazuje `✓ on`/`○ off`; bez dialogu-dziecka (lepsze niż komenda-w-palecie OpenCode dla drzewa ustawień) | brak (dwuwartościowe) | — |
| `STRING_SET` | `requested_products`, `mkv_tracks`, `llm_module_ids` | `SelectDialog multi` (§5.5): `space` toggle, `✓/○` per wiersz, `enter` zatwierdza zbiór | zbiór ⊆ `allowed_values`; walidacja krzyżowa planera dopiero w preview (TUI nie duplikuje reguł planera) | błąd zapisu → §7.5 |
| `STRING_LIST` (uporządkowana) | `audio_language_priority`, `subtitle_language_priority`, `translation_fallback_chain` | `ReorderDialog` (własny projekt, R-209) | fallback chain: elementy ∈ `allowed_values`, bez duplikatów; języki: niepuste kody | komunikat inline; `enter` nieaktywne |
| `OBJECT_LIST` | `elevenbytes_custom_voices` (pola obiektu z `object_fields`) | `SelectDialog` listujący aliasy + akcje stopki: `a` add, `enter` edit, `d` remove (z `ConfirmDialog`); add/edit = sekwencja `PromptDialog` per pole obiektu | per pole `object_fields` + unikalność aliasu | komunikat inline w kroku sekwencji |

**R-406.** Pola zależne od silnika (`depends_on`): zmiana `translation_engine`,
`llm_provider`, `tts_engine`, `tts_provider_model_id`, `tts_voice_id` przebudowuje
korzeń natychmiast po powrocie (nowy `setting_catalog(context)` z zaktualizowanym
kontekstem). Zmiana głosu TTS przywraca zapisany profil tego głosu (kontrakt legacy
panelu — `anishift/cli/AGENTS.md`). Opcje `run7` nie mogą przetrwać jako aktywne
ustawienia `run6` (kontrakt Etapu 9 §13.6) — gwarantuje to katalog, TUI tylko renderuje
jego wynik.

### 7.4. Nawigacja drzewa — mechanika powrotu

**R-407.** Wejście w pole: `replace()` korzenia dialogiem-dzieckiem. Zatwierdzenie
w dziecku: zapis (§7.5) → `replace()` z powrotem na korzeń z `initial_highlight` =
edytowane pole i odświeżoną wartością w wierszu. `escape` w dziecku: bez zapisu →
`replace()` na korzeń z tym samym `initial_highlight`. `escape` w korzeniu: `clear()` —
zamknięcie ustawień i przywrócenie fokusu ekranowi. Kaskada
`tts_engine → tts_provider_model_id → tts_voice_id` to trzy osobne pozycje korzenia,
nie kreator wielokrokowy — po każdej zmianie użytkownik wraca do korzenia i widzi
zaktualizowany zestaw pól.

### 7.5. Zapis natychmiastowy

**R-408.** Zatwierdzona zmiana pola jest zapisywana natychmiast: kandydat = kopia
snapshotu (`AppService.settings_snapshot()`), przypisanie wartości (mapowanie
`setting_id` → atrybut/profil jak w dzisiejszych `_assign_setting`), walidacja
(`spec.validate_value()` + `__post_init__` modelu), `AppService.save_settings(kandydat)`
(zapis atomowy). Błąd walidacji lub zapisu: żadna zmiana nie dotyka dysku, dialog-dziecko
pozostaje otwarty z komunikatem `$error` (skrócony `str(error)` bez ścieżek absolutnych).
Run w toku pozostaje nietknięty — wykonuje niezmienny `RunSettingsSnapshot`
(gwarancja `AppService.execute`, `service.py:226-259`).

### 7.6. Sekrety

**R-409.** Wiersze sekretów są **tylko do odczytu**: `✓ configured` / `○ missing`
(glif + słowo; ikona źródła `.env`). `enter` otwiera dialog informacyjny z nazwą
zmiennej środowiskowej (`ANISHIFT_*` / `.env`) i instrukcją konfiguracji — TUI nie
edytuje sekretów i nigdy nie pokazuje ich wartości (kontrakt Etapu 9 §13.11; parytet
z legacy panelem). Silnik z brakującym sekretem pozostaje widoczny na listach wyboru
z markerem stanu, nie znika (kontrakt `anishift/cli/AGENTS.md`).

### 7.7. Dostępność silników

**R-410.** Debug-join dostępności (`settings.py:53-58`) zostaje zastąpiony: stan
z `AppService.engine_availability()` jest renderowany per silnik w slocie `footer`
wiersza wyboru silnika (`✓ ready` / `⚠ <powód>`), a komenda `doctor` pokazuje pełny
raport w Tools. Budowa katalogu nie wykonuje płatnej syntezy ani live probe (kontrakt
legacy panelu — bez zmian).

## 8. Ekrany główne i wykonanie

### 8.1. Routing i ekrany

**R-501.** Ekrany: `workspace` (start), `auto`, `manual`, `preview`, `execution`,
`results`, `tools`. Ich zachowanie funkcjonalne definiują §5.1–5.3 i §5.5–5.8
`etap-9-interfejs-wymagania.md` (bez zmian). 9.5 dodaje wymagania wyglądu: każdy ekran
ma nagłówek z nazwą i kontekstem, treść w panelach wg §4.4, stały command bar `❯`
i pasek statusu; workspace dodatkowo mały logotyp ASCII AniShift w nagłówku (jedyny
element dekoracyjny; nie przesuwa layoutu i znika poniżej 100×30).

### 8.2. Pasek statusu

**R-502.** Pasek statusu (dół, pod command barem) ma segmenty z ikonami wg §4.3:
`workspace: N grup` · `preset/tryb` · `run: idle|running|done|failed` (z glifem stanu)
· `elapsed` (rośnie tylko podczas runu) — po lewej; 4–5 skrótów aktywnego ekranu
z żywych `BINDINGS` — po prawej. Zero metryk deweloperskich (branch, koszt, model).

### 8.3. Execution

**R-503.** Jeden stabilny wiersz per grupa (prealokowany, `natsorted` — parytet
z legacy): glif+słowo stanu, bieżąca operacja, procent postępu; rozwijane szczegóły
zadań. Retry i fallback są renderowane z `RunEvent` (`TASK_RETRY`, `TASK_FALLBACK` —
`events.py:36-44`) jako tekst w wierszu szczegółów (`retry 2/5 <silnik>`,
`fallback → <silnik>`), nie tylko kolor. Postęp procentowy jest koalescowany do
≤10 renderów/s per task; zdarzenia terminalne renderują się w następnym ticku timera
bez throttle. Filtr `f` cyklicznie: all → running → failed → done (`done` = etykieta
stanów terminalnych, nie stan API — kontrakt Etapu 9 decyzja 26).

**R-504.** `cancel` (klawisz `c`, komenda, przycisk) wymaga `ConfirmDialog` z opisem
skutku, jest idempotentny i pozostaje dostępny podczas shutdownu. Częściowy sukces:
Results rozdziela `succeeded / partial / failed / cancelled` per grupa z glifami §4.3,
utworzonymi produktami i następną sensowną akcją (przejście do Manual dla nieudanej
grupy).

## 9. Wydajność i responsywność — obserwowalnie

**R-601.** Podczas aktywnego runu (fake handlery, 20 grup) Pilot wykonuje nawigację
klawiaturą i wpisywanie do command bara bez utraty zdarzeń wejścia; wątek UI nie
wykonuje żadnej blokującej operacji domenowej (discovery/inspection/execute zawsze
w `Worker(thread=True)`).

**R-602.** Otwarcie każdego dialogu i każda zmiana filtra renderują się w najbliższej
klatce (bez sztucznych opóźnień/animacji wejścia); slash-popup filtruje zbiór ≤50 komend
synchronicznie.

**R-603.** Tabela workspace z 100 grupami: pełne przewinięcie i sort/filtr w teście
Pilot bez timeoutu testu (limit 5 s na operację); zużycie zdarzeń: `EventBuffer.drain()`
w timerze UI 50–100 ms; brak nieograniczonego wzrostu bufora (koalescencja progressów —
kontrakt `events.py`).

**R-604.** W bezczynności TUI nie przerysowuje ekranu w pętli: timery ograniczają się
do drenażu zdarzeń (pauzowany poza runem), odświeżania `elapsed` (≤4/s, tylko podczas
runu) i klatek spinnera (tylko gdy widoczny).

## 10. Unicode i kodowanie na Windows — wymóg twardy

**R-701.** Cały język wizualny (§4.3: `●`, `✓`, `⠋`, `❯`, ramki) wymaga wyjścia UTF-8.
Znany bug: `uv run anishift doctor` na konsoli cp1250 rzuca `UnicodeEncodeError` przy
`✅` (`cli/main.py:40-41` → `utils/rich_console/utilities.py`, ikony statusu).
`run_anishift.bat` maskuje problem przez `chcp 65001`; bezpośrednie `uv run anishift`
nie.

**R-702.** Granica procesu (`anishift/cli/main.py`, przed pierwszym wyjściem na konsolę)
rekonfiguruje strumienie: `sys.stdout`/`sys.stderr` → `encoding="utf-8"`,
`errors="replace"` (guard na obecność `reconfigure`). Skutek wymagany: żadna komenda CLI
ani TUI nie może zakończyć się `UnicodeEncodeError` niezależnie od strony kodowej
konsoli; w najgorszym razie glif degraduje do `?` zamiast wywalać proces.

**R-703.** `doctor` zgłasza check „console encoding": OK dla UTF-8/65001, WARN z sugestią
(`chcp 65001` albo `PYTHONUTF8=1`) dla innej strony kodowej — informacyjnie, bo R-702
i tak chroni przed crashem.

**R-704.** Test-strażnik: wywołanie ścieżki raportu doctor z podstawionym strumieniem
`cp1250` przechodzi bez wyjątku (AC-701).

## 11. Dostępność i degradacja

**R-801.** Wąski terminal: pełny layout od 100×30; poniżej — komunikat o minimalnym
rozmiarze plus nadal działający command bar, pasek statusu i bezpieczne wyjście
(`ctrl+q`, `quit`); przy 80×24 aplikacja pozostaje sterowalna (bez crasha, bez
nakładających się tekstów). Dialogi ograniczają szerokość do `terminal − 2` (R-110).

**R-802.** Brak truecolor: paleta musi pozostać czytelna po automatycznej degradacji
Rich/Textual do 256 kolorów; pozycja HITL na liście akceptacji (AC-HITL-1). Żaden stan
nie ginie, bo kolor nigdy nie jest jedynym nośnikiem (R-106).

**R-803.** Brak obsługi znaków: dzięki R-702 nieobsługiwany glif degraduje do `?`
w CLI; w TUI Textual renderuje przez własny driver — wymagane jest, by każdy glif
z R-106 występował zawsze obok słowa lub pozycji strukturalnej, więc utrata glifu nie
usuwa informacji. Osobnego trybu ASCII nie budujemy (YAGNI; Windows Terminal i conhost
z UTF-8 pokrywają populację docelową — projekt Windows-only).

## 12. Inwarianty

- **I-1.** `anishift/application/`, planner i scheduler nie importują `textual`, `typer`,
  Rich ani modułów `anishift.cli`/`anishift.tui`; TUI woła wyłącznie `AppService`
  (test architektury istnieje — utrzymać zielony).
- **I-2.** Żaden plik `anishift/tui/` poza modułem palety nie zawiera literału koloru;
  żaden `.tcss` nie zawiera hexa.
- **I-3.** Żaden ekran produkcyjny nie renderuje placeholderów typu „arrives in the next
  implementation step"; klasa `PlaceholderScreen` nie istnieje po 9.5.
- **I-4.** Sam `enter` nigdzie nie uruchamia ukrytej płatnej pracy; start runu przechodzi
  zawsze przez preview i jawne potwierdzenie kosztu/nadpisań.
- **I-5.** Podwójny `enter`/klik nie uruchamia dwóch runów; drugi start podczas aktywnego
  runu zwraca typowany konflikt (kontrakt `AppService`).
- **I-6.** Zdarzenie z obcego `run_id` albo starszej generacji sesji nigdy nie zmienia
  widoku (bramka generacji — wzorzec zachowany z obecnego `app.py:93-105`).
- **I-7.** Sekrety, pełne `Settings`, prompty, teksty napisów/TTS i ścieżki absolutne
  nie pojawiają się w komunikatach błędów UI ani w logach (kontrakt logowania repo).
- **I-8.** Stan aktualny (`●`) i kursor listy są zawsze dwoma różnymi, jednocześnie
  widocznymi sygnałami wizualnymi.
- **I-9.** Etykiety skrótów w stopkach pochodzą z żywej keymapy — nigdy z literału.
- **I-10.** Bramki jakości (`ruff check`, `ruff format --check`, `mypy`, `pytest` na
  `anishift/ tests/`) są zielone po każdej fazie planu; baseline 2034 passed / 8 skipped
  nie może zmaleć poza jawnie skasowane testy legacy/TUI zastąpione nowymi.

## 13. Kryteria akceptacji

Automatyczne (Pilot / pytest, bez prawdziwego terminala):

- **AC-101.** Test-strażnik: grep po `anishift/tui/**/*.tcss` i `**/*.py` (poza modułem
  palety) nie znajduje wzorca hex ani `Color(`-literałów; test failuje na naruszenie.
- **AC-102.** `anishift-dark` i `anishift-light` są zarejestrowane; przełączenie motywu
  w dialogu `themes` zmienia `App.theme`; `escape` przywraca motyw sprzed otwarcia,
  `enter` utrwala go w pliku stanu UI.
- **AC-103.** Test ikon: każdy stan z tabeli R-106 ma parę (glif, słowo/pozycja);
  moduł ikon jest jedynym źródłem glifów statusu w TUI (grep-test).
- **AC-201.** Pilot: otwarty `SelectDialog` ma fokus na filtrze; wpisanie tekstu filtruje
  bez dotykania strzałek; `escape` zamyka i przywraca fokus poprzedniemu elementowi.
- **AC-202.** Pilot: opcja `current` pokazuje `●`, a podświetlenie kursora jest od niej
  niezależne (dwa różne wiersze mogą jednocześnie nieść oba stany).
- **AC-203.** Pilot: `tab` cykluje po akcjach stopki; etykieta akcji zawiera klawisz
  pobrany z keymapy; zmiana bindingu w definicji zmienia etykietę bez zmiany w widoku.
- **AC-204.** Pilot: tryb multi — `space` przełącza bez zamykania, `enter` zatwierdza
  zbiór; stan `✓/○` widoczny per wiersz.
- **AC-205.** Pilot: `NumberDialog` odrzuca wartość poza zakresem (komunikat, `enter`
  nieaktywne), przyjmuje wartość poprawną; `up`/`down` zmienia o krok; wariant optional
  przyjmuje puste.
- **AC-206.** Pilot: `ReorderDialog` przesuwa element `shift+down`, dodaje i usuwa
  pozycję, `escape` porzuca całość bez zapisu.
- **AC-301.** Pilot: `ctrl+p` otwiera paletę; przy pustym filtrze widoczna grupa
  „Suggested" wyliczona z predykatów; pisanie usuwa nagłówki grup; wybór wykonuje
  komendę przez `dispatch`.
- **AC-302.** Pilot: komenda z `enabled() == False` nie występuje w palecie ani slashu;
  po zmianie stanu sesji pojawia się.
- **AC-303.** Pilot: slash-popup pokazuje ≤10 pozycji, nigdy zero przy niepustym słowniku;
  dopasowanie prefiksowe wygrywa z śródsłownym (test rankingu: `se` → `settings` przed
  `presets`-podobnymi); alias podbija ranking, nie tworzy wpisu.
- **AC-304.** Pilot: pusty `enter` w command barze nie wywołuje żadnej metody
  `AppService`; nieznane polecenie pokazuje błąd z sugestią i nie ma efektów ubocznych.
- **AC-401.** Pilot (fake `AppService` z przechwyconym `save_settings`): wybór wartości
  w polu-liście zapisuje dokładnie jedną zmianę i wraca do korzenia z kursorem na tym
  polu i nową wartością w wierszu.
- **AC-402.** Pilot: `escape` w dialogu-dziecku wraca do korzenia bez wywołania
  `save_settings`.
- **AC-403.** Pilot: zmiana `tts_engine` przebudowuje pozycje korzenia (pola nieaktywne
  znikają, pola nowego silnika się pojawiają); zmiana głosu przywraca profil głosu.
- **AC-404.** Pilot: pole `BOOLEAN` przełącza się w miejscu i pokazuje `✓ on`/`○ off`.
- **AC-405.** Pilot: wiersz sekretu pokazuje `✓ configured`/`○ missing`; `enter` otwiera
  instrukcję; żadna ścieżka kodu nie renderuje wartości sekretu.
- **AC-406.** Pilot: błędna wartość (np. concurrency 99) nie zapisuje niczego; komunikat
  inline; poprawiona wartość zapisuje się.
- **AC-407.** Test kompletności: dla reprezentatywnych kontekstów katalogu (edge,
  elevenbytes run6 i run7, elevenlabs, oba profile SAPI) **każdy** `SettingSpec`
  zwrócony przez `setting_catalog()` ma przypisany edytor (dispatch po `value_type`
  i zakresie); nieobsłużony spec = czerwony test. To jest strażnik „58 pól, nie
  podzbiór".
- **AC-501.** Pilot: pełny przepływ `workspace → auto → preview → execution → results`
  na realnym `AppService` z fake handlerami; podczas runu wejście działa (R-601);
  cancel z potwierdzeniem kończy run; Results pokazuje partial z glifem i słowem.
- **AC-502.** Pilot: retry i fallback z fake handlera są widoczne tekstowo w wierszu
  szczegółów grupy.
- **AC-503.** Pilot: resize do 100×30 zachowuje pełny layout; poniżej — komunikat
  minimalnego rozmiaru + działający command bar; 80×24 pozwala wykonać `quit`.
- **AC-701.** Test kodowania: raport doctor pisany do strumienia `cp1250` nie rzuca
  wyjątku (R-702/R-704).
- **AC-702.** `doctor` zawiera check „console encoding" z poprawnym statusem OK/WARN.
- **AC-801.** Test parytetu legacy (`tests/application/test_legacy_parity.py`):
  identyczne hermetyczne wejścia przez legacy `run_pipeline`/`compose_only` i przez
  `AppService` dają zgodne statusy per grupa, nazwy/rodzaje produktów i liczbę wywołań
  fake providerów; test istnieje i jest zielony PRZED usunięciem legacy, znika razem
  z legacy w tym samym commicie.
- **AC-802.** Po F7: `anishift` bez argumentów otwiera TUI; `doctor`/`setup`/`run` nie
  startują Textual; `run --preset` zwraca kod 0 przy pełnym sukcesie i niezerowy przy
  partial/failure/cancel; `rg 'prompt_toolkit|anishift\.pipeline' anishift tests` puste;
  katalogi `anishift/pipeline/` i `tests/pipeline/` nie istnieją.

Manualne (HITL — użytkownik):

- **AC-HITL-1** (po fazie F4, bramka kontynuacji): użytkownik akceptuje wygląd na
  własnym terminalu wg listy R-112 + czytelność w 256 kolorach; brak akceptacji =
  poprawki wyglądu przed budową kolejnych ekranów, nie po.
- **AC-HITL-2** (przed usunięciem legacy w F7): użytkownik akceptuje działanie nowego
  TUI jako zamiennika REPL-a (smoke na cmd/cp1250 i Windows Terminal) — domknięcie
  niewiadomej reverta `6849f32`.

## 14. Jawne wykluczenia zakresu

- real-media E2E, load test 100 grup w schedulerze, job CI E2E, zamknięcie issue #38 —
  pozostają w Etapie 9 (§1.3);
- edycja sekretów z TUI (zapis do `.env`) — poza zakresem; TUI pokazuje stan i instrukcję;
- auto-detekcja jasny/ciemny z OSC 10/11; osobny tryb ASCII; animacje pełnoekranowe
  i grafika rastrowa (Sixel/Kitty) — poza zakresem;
- podgląd (odsłuch) głosu TTS w dialogu wyboru — zakaz płatnych/sieciowych prób z UI;
- frecency, akordy leadera, which-key, system pluginów, sloty UI, komendy-jako-szablony,
  skille — jawnie nieprzenoszone z OpenCode (ustalenia researchu);
- agent językowy, MyAnimeList, pobieranie anime — bez zmian poza zakresem (Etap 9);
- migracja/konwersja plików konfiguracji użytkownika — nie jest potrzebna (schemat
  ustawień się nie zmienia).

## 15. Basis

- Audyt kodu `anishift/tui/` i `anishift/config/field_catalog.py` na baseline `6849f32`
  (wszystkie twierdzenia §1.2, §3, §7 zweryfikowane grep/odczytem — cytaty ścieżka:linia
  w treści).
- Pełny `uv run pytest` na baseline: exit 0 (2034 passed / 8 skipped).
- Raporty researchu 01–05 (scratchpad sesji): stack i architektura OpenCode, rendering,
  komendy/skille, ustawienia/UX, wykonalność Python vs TS.
- Kod referencyjny OpenCode 1.18.21 (`3a31c4e`): `ui/dialog.tsx`, `ui/dialog-select.tsx`,
  `component/dialog-theme-list.tsx`, `component/dialog-mcp.tsx`,
  `component/command-palette.tsx`, `component/prompt/autocomplete.tsx:495-522`,
  `theme/index.ts` — wszystkie cytowane fragmenty odczytane bezpośrednio z klonu.
- Textual 8.2.8 (zainstalowany): `theme.py` (dataclass `Theme`, `variables`),
  `app.py:441` (`COMMAND_PALETTE_BINDING = "ctrl+p"`),
  `app.py:1399` (`get_theme_variable_defaults`), `fuzzy.py` (`FuzzySearch`),
  `screen.py:2158` (`ModalScreen`).
- Kontrakty nadrzędne: `etap-9-wymagania.md` (§7, §13, §15, §19),
  `etap-9-interfejs-wymagania.md` (§3, §5, §10–§14), `anishift/tui/AGENTS.md`,
  `anishift/cli/AGENTS.md`, `anishift/application/AGENTS.md`.
