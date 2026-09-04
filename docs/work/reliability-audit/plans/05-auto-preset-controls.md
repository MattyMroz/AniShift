---
kind: plan
status: ready
baseline: work/reliability/02-terminal-polish
created: 2026-09-05
---

# Plan: komplet opcji domyślnego Auto w panelu

## Rezultat

Użytkownik ustawia istniejące polityki Auto bez ręcznej edycji `presets.json`.
Każda zmiana zachowuje pozostałe pola presetu, a dozwolone wartości pochodzą
z istniejącego katalogu `SettingSpec`, nie z drugiej ręcznej listy.

## Stan i granice

Iteracja terminala udostępnia wszystkie siedem produktów. Pozostałe siedem
`AUTO_PRESET` opisuje `anishift/config/field_catalog.py:_workflow_specs`, lecz
`SettingsController` nie renderuje ich jako ustawień domyślnego przebiegu.
Nie są polami `UserSettings`; nie wolno zapisywać ich przez `update_setting()`.
Osiągalność `GLOBAL` i `ENGINE_PROFILE` nie dowodzi kompletności Auto.

Zakres: aktualny domyślny preset. Poza nim: zarządzanie wieloma presetami, zmiana
schema, wybór konkretnych ścieżek grupy, nowe silniki, watcher i audiobook.
Ten plan jest gotowy do następnej iteracji po ocenie terminala, nie opisuje
zrealizowanych opcji.

## Pola i zależności

| Pole | Odbiorca | Warunek |
| --- | --- | --- |
| `subtitle_source_policy` | Wybór źródła napisów | Tylko wartości katalogu dla `RunMode.AUTO` |
| `translation_action` | Automatyczne język / wymuszenie / zachowanie źródła | Nie ukrywać skutku dla polskich produktów |
| `source_subtitle_language` | Korekta języka źródła | Pusta wartość usuwa override, nie jest pustym kodem |
| `subtitle_output_format` | Preserve / ASS / SRT | Zachować obecną walidację formatu |
| `burn_subtitle_product` | MP4 | Pokazywać tylko dla żądanego MP4 |
| `mkv_tracks` | MKV | Wielokrotny wybór z katalogu; obecna semantyka pustego zbioru |
| `mp4_audio_source` | MP4 | Pokazywać tylko dla żądanego MP4 |

## Kolejność

1. Przeczytać root, `anishift/cli`, `application`, `config` i `tests` AGENTS,
   wynik Planu 04 oraz `field_catalog`, `AutoPreset`, `AutoPresetDraft`,
   `AppService.save_preset`, `SettingsController._save_output`.
2. Utrwalić red tests: read→edit→save→fresh load każdego pola; zmiana jednego
   nie narusza pozostałych siedmiu ani wybranego modelu/globalnych preferencji.
3. Dodać sekcję domyślnego Auto w istniejącym kontrolerze. Użyć obecnych edytorów
   select/multiselect/text i `save_preset`, bez nowego uniwersalnego routera.
4. Oprzeć odczyt/walidację na kontekście AUTO. Pokazywać tylko aktywne zależności
   produktów, zachować jawne resetowanie całego właściwego zakresu.
5. Testy błędnego zapisu: poprzedni plik i stan pozostają spójne; ponowienie oraz
   świadome anulowanie nie wymagają restartu. Brak sekretów w podglądzie/diagnostyce.
6. Sprawdzić keyboard, narrow window, scroll i działający plan Auto z każdym
   wyborem przez fasadę. Bez live API do sprawdzania samego formularza.
7. Pełne bramki repo, niezależne review, tematyczny commit i odbiór człowieka.

## Warunki wyjścia

- Wszystkie osiem opcji `AUTO_PRESET` ma prawdziwą edycję w panelu lub zależne
  ukrycie zgodne z katalogiem; nie tylko etykietę z aktualną wartością.
- Reset, anulowanie, brak zmiany, błąd dysku i reload mają regresje.
- Nie naruszono tożsamości presetu, pozostałych preferencji ani materiałów źródłowych.
- Użytkownik wybiera format/źródło i otrzymuje zgodny plan; niemożliwa kombinacja
  pokazuje konkretną odmowę zamiast awarii w trakcie przetwarzania.
- Wygląd i nazwy potwierdzono w scenariuszu ręcznym; testy nie zastępują tego odbioru.

Materialny brak backendu, konieczność migracji albo zmiana semantyki istniejącego
pola oznacza przeplanowanie przed implementacją, nie ciche rozszerzenie zakresu.
