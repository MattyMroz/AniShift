---
kind: outcome
status: pending-human
baseline: main 6eef7d1
resulting-state: work/reliability/05-auto-preset-controls
completed: 2026-09-05
---

# Wynik: komplet opcji domyślnego Auto w panelu

## Finalny rezultat

Panel ma siedem dodatkowych ustawień Auto; produkty nadal wybiera się w Wynik.
Dostępne wartości i zależności pochodzą z katalogu ustawień. Edycja zapisuje cały
poprawny preset, zachowując jego tożsamość i pozostałe pola. Reset Auto/Wynik
przywraca cały preset; częściowy błąd resetu root jest jawny i można ponowić zapis.

Naprawiono też crash planera przy zakazie tłumaczenia angielskich napisów na produkt
PL: użytkownik otrzymuje odmowę zamiast niepoprawnego grafu wykonania.
„Nie tłumacz” wymaga polskiego źródła tylko dla produktów PL; angielskie napisy
źródłowe można wypalać bez tłumaczenia.

Status: **pending-human**. Poprawki R1–R5 zamknięte technicznie; wygląd i ergonomia
panelu wymagają odbioru właściciela. Nie oznacza to akceptacji wszystkich przyszłych
funkcji aplikacji. Watcher, pobieranie i heurystyki napisów nie zostały zaimplementowane.

## Zmiany

| Obszar | Rezultat |
| --- | --- |
| `config/field_access.py` | adapter płaskich pól katalogu do presetu i produktów, wspólna ocena zależności |
| `cli/interactive/settings.py` | sekcja Auto, istniejące edytory/klawisze/autozapis, etykiety PL, pełny reset |
| `application/planner.py` | problemy zablokowanego planu nie odwołują się do usuniętych artefaktów |
| testy config/CLI/planner | zapis i reload, brak zmiany, błędy zapisu, retry, reset, zależności, wąski terminal |
| `test_console.py` | prawdziwe doctor/setup w subprocessie, ale pobieranie zablokowane i katalog instalacji tymczasowy |
| `test_auto_preset_smoke.py` | 30 przypadków: 23 poprawne wykonania, 1 oczekiwany błąd wykonania, 5 odmów, 1 test panelu |
| `cli/AGENTS.md` | zgodny z kodem opis resetu całego presetu |

Bez zmian schematu, zależności, providerów ani sposobu zapisu danych runtime.

## Dowody automatyczne

Kontrole wykonano na izolowanym worktree ze wspólną venv **bez synchronizacji**.
Ustawienie PYTHONPATH jest konieczne: zainstalowany entrypoint jest związany
z główną kopią repo.

```powershell
$env:UV_PROJECT_ENVIRONMENT = 'C:/Users/MattyMroz/Desktop/PROJECTS/AniShift/.venv'
$env:UV_NO_SYNC = '1'
$env:PYTHONPATH = 'C:/Users/MattyMroz/Desktop/PROJECTS/AniShift-worktrees/auto-preset-controls'
$env:ANISHIFT_SMOKE_BIN_ROOT = 'C:/Users/MattyMroz/Desktop/PROJECTS/AniShift/external/bin'
Set-Location 'C:/Users/MattyMroz/Desktop/PROJECTS/AniShift-worktrees/auto-preset-controls'
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
uv run pytest tests/application/test_auto_preset_smoke.py -m smoke -n 2 -o addopts=''
uv run anishift --help
```

- Ruff i format: PASS, 443 pliki.
- Mypy native i Linux: PASS, 445 plików. Linux to kontrola typów, nie wykonanie na Linuksie.
- Pełny pytest **bez deselection**: **3089 passed, 13 skipped, 11 warnings, 26.54 s**.
- Dedykowane smoke: **30 passed, 14.35 s**, żaden nie pominięty.
- CLI help: PASS.
- Skipy: 7 sieciowych, 4 zewnętrzne korpusy, 2 symlinki Windows.
- Ostrzeżenia: deprecacja wewnętrznego typu w SDK Google dla przyszłego Pythona 3.17.

## Macierz wykonanych smoke

| Przypadek | Liczba | Sprawdzony rezultat |
| --- | ---: | --- |
| Domyślny preset EN | 1 | pełne PL + audio, treść napisów i wywołania syntezy |
| Wszystkie siedem produktów | 1 | treść warstw, ścieżki MKV, audio i wypalenie w MP4 |
| Tylko źródłowe napisy | 1 | oryginalny tekst, bez tłumaczenia/TTS |
| AUTO i SIDECAR z plikiem obok | 2 | sidecar EN wybrany przed osadzonym PL, pełne wykonanie |
| EMBEDDED przy sidecarze | 1 | wybrane osadzone PL, bez tłumaczenia, prawidłowy tekst TTS |
| Brak sidecara / NONE z napisami | 2 | odmowa przed wykonaniem |
| AUTO PL / zakaz tłumaczenia PL / wymuszenie PL | 3 | odpowiednio brak/brak/obecność tłumaczenia i właściwa treść |
| Zakaz tłumaczenia EN dla produktu PL | 1 | odmowa, bez crasha |
| Dwa override języka | 2 | normalizacja albo tłumaczenie zgodne z override, produkty i tekst TTS |
| Preserve / ASS / SRT | 3 | właściwe rozszerzenie i treść produktu |
| Ścieżki MKV displayed+source+audio / puste | 2 | prawdziwe ścieżki; pusty wybór zachowuje oryginalne wideo/audio/napisy |
| MP4 original + displayed | 1 | brak TTS, oryginalny ton i widoczne wypalone napisy |
| MP4 narration bez produktu audio | 1 | synteza/miks, brak osobnego produktu audio, właściwy ton |
| Wypalone SOURCE + do_not_translate EN | 1 | sukces bez tłumaczenia/TTS, źródłowe audio i wypalone napisy |
| MP4 AUTO bez/z produktem narration | 2 | odpowiednio oryginalne audio albo miks lektora |
| Displayed z czystego SRT | 1 | oczekiwany FAILED, brak publikacji pustego produktu |
| Pusty workspace / uszkodzony MKV | 2 | odmowa przed przetwarzaniem |
| Priorytet EN / PL przy dwóch ścieżkach | 2 | wykonany właściwy wybór, poprawne teksty produktu i TTS |
| Nawigacja bez edycji | 1 | nie powstaje plik presetu |

Wszystkie wykonania porównują SHA256 plików wejściowych przed i po procesie.
MP4 jest w całości dekodowane przez FFmpeg; próbka PCM rozróżnia ton źródła 440 Hz
i deterministyczny lektor 330 Hz. Porównanie klatki z niebieskim źródłem sprawdza
obecność wypalenia; przypadki bez wypalenia są kontrolą negatywną.

Realne są generowanie mediów, probe, ekstrakcja, miks, mux i burn.
Google HTTP zwraca deterministyczne `PL <tekst>`, a Edge generowany klip MP3:
to stuby granic sieciowych, **nie dowód jakości tłumaczenia ani głosu**.
Nie użyto prywatnego materiału, live API ani pełnych odcinków.

## Review i ograniczenia

[Review](../reviews/05-auto-preset-controls.md) rozdziela kontrolę kodu Fable od
późniejszej autokontroli poprawek prowadzącego. Limit Fable nie jest już blokadą:
właściciel zlecił prowadzącemu dokończenie.

Zastany klasyfikator SRT nie tworzy warstwy displayed: ten brak jest wykrywany
dopiero podczas wykonania. Smoke utrwala bezpieczny błąd bez publikacji.
To odchylenie od ogólnego warunku odmowy przed wykonaniem; wymaga osobnego
etapu heurystyk, nie zostało ukryte ani naprawione przez zmianę semantyki.

MKV zachowuje oryginalne ścieżki i dokłada żądane; wybór source może więc
duplikować osadzone napisy. Pozostawiono obowiązujący kontrakt.

Wcześniejszy test setup pobrał narzędzie do izolowanego worktree. Poprawiony test
nie pobiera niczego; ignorowane binarki pozostają lokalne. Główna venv i narzędzia
nie były aktualizowane, a tłumaczenie w tle nie było zatrzymywane.

## Odbiór człowieka

Po lokalnym scaleniu uruchomić AniShift w **nowym terminalu**, bez restartowania
bieżącego tłumaczenia. Wejść w Ustawienia → Auto. Sprawdzić nazwy, Enter/Esc,
lewo/prawo, język źródła, multiselect oraz okno 44×14.
Zaznaczenie MKV/MP4 w Wynik powinno odsłonić zależne opcje Auto.
Reset jest celowo resetem całego presetu — używać go tylko chcąc przywrócić
domyślne wartości. Cofnij pozostaje na dole, zapis nie pokazuje komunikatu sukcesu.

Plan 05 i tablica zadań należą również do niezacommitowanego pakietu planowania
w głównej kopii. Nie publikować go przypadkiem razem z kodem.
