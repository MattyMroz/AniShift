---
kind: plan
status: pending-human
baseline: main 6eef7d1 (kod jak 369efcd)
created: 2026-09-05
branch: work/reliability/05-auto-preset-controls
---

# Plan: komplet opcji domyślnego Auto w panelu

Implementacja i poprawki review ukończone w `4dc99dc`, scalone lokalnie do
`work/planning/automation-and-subtitles` w głównej kopii AniShift.
Pełny suite: 3089 passed, 13 skipped; smoke: 30 passed. Czeka odbiór panelu.
[Finalny wynik i ograniczenia](../outcomes/05-auto-preset-controls.md).
Nie opublikowano na GitHub; pozostały pakiet planowania zachowano lokalnie.

Właściciel zatwierdził wykonanie przez Fable 5.1 bez dalszych agentów oraz
review prowadzącego. Rozszerzył odbiór o smoke MKV PL/EN: wszystkie opcje Auto,
produkty i istotne interakcje, rzeczywiste narzędzia medialne, deterministyczne
granice tłumaczenia/TTS. Macierz ma rozróżniać wykonane ścieżki, odmowy i skipy;
nie jest deklaracją przetestowania live dostawców ani prywatnych odcinków.

## Rezultat

Użytkownik ustawia wszystkie polityki domyślnego presetu Auto bez ręcznej
edycji `presets.json`. Każda zmiana zachowuje pozostałe pola, dozwolone
wartości pochodzą z katalogu `SettingSpec`, reset root przywraca cały preset.
Ten etap jest A00 masterplanu automatyzacji; Plan 01 (watch) zależy od niego.

## Stan i granice

Panel edytuje tylko `requested_products` przez pełny `AutoPresetDraft`
w `SettingsController._save_output`. Pozostałe siedem speców `AUTO_PRESET`
z `field_catalog.py:_workflow_specs` nie jest renderowane. `setting_is_active`
z `field_access.py` ocenia `depends_on` na `UserSettings` i rzuca `ValueError`
dla identyfikatorów presetu. `_reset_scope` dla root woła `reset_settings()`
i `_restore_default_products()`, czyli po dodaniu pól nie przywracałby
całego presetu. Test osiągalności w `test_interactive_settings_layout.py`
liczy tylko spece persystowane.

Zakres: aktualny domyślny preset. Poza nim: wiele presetów, zmiana schema,
nowe silniki, watcher, audiobook. Dwa znane failing testy (prywatny styl
`shadow-slave`) pozostają nietknięte.

## Pola i zależności

| Pole | Edytor | Warunek |
| --- | --- | --- |
| `subtitle_source_policy` | select z `allowed_values` dla `RunMode.AUTO` | bez `external`/`ready_polish` |
| `translation_action` | select | skutek dla produktów PL widoczny w opisie |
| `source_subtitle_language` | text | pusta wartość = brak override |
| `subtitle_output_format` | select | obecna walidacja formatu |
| `burn_subtitle_product` | select | tylko gdy MP4 w produktach |
| `mkv_tracks` | multiselect | tylko gdy MKV; pusty zbiór zachowuje obecną semantykę |
| `mp4_audio_source` | select | tylko gdy MP4 |

## Design

- Ocena zależności: `field_access.py` dostaje mały evaluator warunku
  z jawnym argumentem warunku i odczytem wartości używane przez istniejące `setting_is_active`
  (preferencje) i nowe `preset_setting_is_active(spec, preset)` (wartości
  z wąskiego adaptera odczytującego pola `AutoPreset` i `preset.products`). Bez drugiej listy pól.
- Zapis: jeden helper `_save_preset_field(setting_id, value)` buduje pełny
  `AutoPresetDraft` z bieżącego presetu i woła `save_preset`; `_save_output`
  używa tego samego helpera. Zmiana produktów nadal zeruje zależne pola.
- Reset root: zachować dotychczasowy kontrakt resetu preferencji; preset przywracać z
  `default_preset_file()` pod bieżącym `preset_id`; reset zakresu „Wynik”
  przywraca cały preset, nie same produkty. Ponieważ preferencje i preset są
  w osobnych plikach, test częściowej awarii resetu ma pokazać rzeczywisty stan
  i możliwość ponowienia; nie obiecywać atomowości dwóch niezależnych zapisów.
- Sekcja „Auto” w istniejącym kontrolerze, obok produktów; bez nowego
  routera i bez nowej akcji Home.

## Kolejność

1. Przeczytać root, `anishift/cli`, `application`, `config` i `tests`
   AGENTS, wynik Planu 04, `field_catalog`, `AutoPreset`, `AutoPresetDraft`,
   `save_preset`, `_save_output`, `_reset_scope`.
2. Red tests: read→edit→save→fresh load każdego pola; zmiana jednego nie
   narusza pozostałych ani preferencji; zależne pola ukryte bez MP4/MKV;
   reset root przywraca cały preset.
3. Ocena zależności na presecie, potem sekcja w kontrolerze z istniejącymi
   edytorami select/multiselect/text.
4. Testy błędnego zapisu: poprzedni plik i stan spójne; ponowienie i
   anulowanie bez restartu; brak sekretów w podglądzie.
5. Aktualizacja testu osiągalności o spece `AUTO_PRESET`; keyboard, narrow
   window, scroll; plan Auto przez fasadę dla każdej kombinacji, bez live API.
6. Pełne bramki repo, review, commit tematyczny ze scope z listy hooka,
   odbiór człowieka.

## Warunki wyjścia

- Osiem opcji `AUTO_PRESET` ma prawdziwą edycję albo zależne ukrycie zgodne
  z katalogiem.
- Reset, anulowanie, brak zmiany, błąd dysku i reload mają regresje.
- Tożsamość presetu, pozostałe preferencje i źródła nienaruszone.
- Niemożliwa kombinacja daje konkretną odmowę przed przetwarzaniem.
- Wygląd i nazwy potwierdzone ręcznie; testy nie zastępują tego odbioru.

Materialny brak backendu, migracja albo zmiana semantyki istniejącego pola
oznacza przeplanowanie, nie ciche rozszerzenie zakresu.

Adapter zależności nie używa bezpośrednio `_encode_preset`: serializer ma
zagnieżdżone `products`, a warunki katalogu używają płaskich identyfikatorów.
Test rozróżnia to jawnie. To rozszerzenie wartości presetu, nie przebudowa
ogólnego systemu ustawień ani publicznego formatu JSON.
