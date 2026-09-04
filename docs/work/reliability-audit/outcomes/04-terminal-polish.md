---
kind: outcome
status: pending-human
baseline: 8e63629
resulting-state: work/reliability/02-terminal-polish
completed: 2026-09-05
---

# Wynik: terminal i ustawienia

## Co zmieniło się dla użytkownika

- Zmiana widoku i rozmiaru nie opuszcza już alternate screen. Czyszczenie starego
  rastra odbywa się przed nową klatką, z zachowaniem historii konsoli.
- Końcowy redraw nie maluje maskotki po powrocie do konsoli.
- Home i Auto mają animowaną maskotkę, pełny/średni/kompaktowy napis oraz wariant
  z samym slime'em. Zbyt niski terminal zachowuje sterowanie zamiast dekoracji.
- Fala napisu po lądowaniu i tekstowy podskok mieszczą się w stałej rezerwacji;
  nie przesuwają pasków. To próba wizualna do oceny właściciela.
- Pod całą marką, również dodatkowym wierszem natywnego rastra, zostaje odstęp.
- Krótkie etapy nie mają sztywnej 14-kolumnowej przerwy. Nazwa źródła korzysta
  z szerokości okna, Unicode jest liczone w komórkach, rozszerzenie zostaje.
- `✓ Done` zachowuje gradient; procent nadal pochodzi z backendu. Nieznany postęp
  ma poruszający się znacznik. W bardzo wąskim oknie procent ma pierwszeństwo
  przed paskiem i zegarem.
- Strzałki, PageUp/PageDown i Home przeglądają całą kolejkę. End jawnie wraca do
  śledzenia aktywnego pliku; dojście na dół nie zabiera ostatniego wiersza.
- Podpowiedzi i stopka są jaśniejsze; tekst akcentu to rozjaśniony azure tej samej palety.

## Ustawienia

Naprawiono utratę produktów niewidocznych wcześniej w panelu (były tylko 4/7),
zapis bez zmiany i podwójny zapis po Enter. Błąd zapisu zachowuje edycję i widoczną
diagnozę, nie ponawia się co klatkę. Dwa kolejne Ctrl+C po jawnym ostrzeżeniu
pozwalają porzucić wyłącznie niezapisaną zmianę i wrócić do Home.

Tab/Shift+Tab uzupełniają strzałki. Right/Enter otwiera lub wybiera; Left/Esc cofa,
a powrót zachowuje miejsce w nadrzędnym menu. Edytor ma kursor, Home/End, Delete
i atomowe wklejenie jednej linii. Sekrety pozostają maskowane i wymagają Enter.
Wynik z siedmioma produktami przewija się również w małym oknie.

Własny model wybiera się jako dostawca → identyfikator → Enter. Działa pierwszy
model skonfigurowanego OpenAI-compatible, a zapis provider/model jest atomowy.
Usunięty alias Palantira można zastąpić poprawnym z katalogu; gotowość wykonania
nadal wymaga poprawnego wybranego aliasu. Katalog JSONC pozostaje read-only.

### Kompletność — co jest, czego nadal nie ma

| Obszar | Wynik audytu |
| --- | --- |
| Katalog wszystkich kontekstów | 66 unikalnych speców: GLOBAL 29, ENGINE_PROFILE 14, SECRET 9, AUTO_PRESET 8, MANUAL_RUN 6 |
| Preferencje globalne i silników | 38 bezpośrednich pól; provider/model jako jeden atomowy wybór; adresy połączeń w osobnym ekranie; stary `primary_model_alias` świadomie ukryty |
| Klucze | Wszystkie 9 ustawień SECRET w Połączeniach |
| Produkty | Wszystkie 7 `ProductKind`, bez utraty wcześniej zapisanych wyborów |
| Zaawansowane Auto | Nadal 7 pól poza panelem — osobny Plan 05 poniżej |
| MANUAL_RUN | Identyfikatory konkretnej grupy i rola zewnętrznego audio, nie globalne preferencje |
| Środowisko | Workspace root i kompatybilne źródło tokenu nie są dodatkowymi globalnymi polami formularza |

Nie ogłaszamy pełnej kompletności panelu. `subtitle_source_policy`,
`translation_action`, `source_subtitle_language`, `subtitle_output_format`,
`burn_subtitle_product`, `mkv_tracks`, `mp4_audio_source` pozostają dostępne przez
konfigurację presetu, ale nie mają jeszcze edycji w Ustawieniach.

## Dowody wizualne i pomiary

Statyczne obrazy powstały z faktycznych widoków Rich i syntetycznych zdarzeń, nie
z ręcznej makiety. Pokazują fallback tekstowy, nie przechwycony ekran SIXEL.
Przeglądarka testowa nie była dostępna; obrazy obejrzano lokalnie po renderowaniu.

- [Home](../proof/terminal-home.png)
- [Auto: sukces, procent i aktywność](../proof/terminal-auto.png)
- [Węższy terminal i próba fali](../proof/terminal-narrow.png)
- [Ustawienia](../proof/terminal-settings.png)
- [Dodanie własnego modelu](../proof/terminal-models.png)

Odtworzenie na Windows z Consolas: `uv run --no-active python docs/work/reliability-audit/proof/render_terminal.py`.
Skrypt używa izolowanych fixture'ów i nie odczytuje kluczy użytkownika.

| Klatka | Mediana po rozgrzaniu | P95 | Najwolniejsza z pierwszych 24 faz |
| --- | --- | --- | --- |
| 120×40 | 2,30 ms | 2,75 ms | 21,71 ms |
| 80×24 | 2,31 ms | 3,24 ms | 16,98 ms |
| 50×20 | 1,04 ms | 1,26 ms | 3,95 ms |

Pomiar: Python 3.14.2, ta maszyna, 120 klatek na wymiar, ostatnie 96 jako rozgrzane;
złożenie Auto, przycięcie i Rich→ANSI. Nie obejmuje transportu/wyświetlania SIXEL,
sieci ani pełnego startu. Nie jest dowodem konkretnego przyspieszenia względem baseline.

Osobny pomiar kontrolera z in-memory granicami: 5×200 operacji, 120×40;
Left/Right 0,417 ms, render 0,039 ms, Up/Down 0,000231 ms mediany. Po wejściu
do ekranu 0 kolejnych odczytów katalogu i 0 zapisów przy powrocie do tej samej wartości.
Zapis na deadline/Enter/wyjściu oraz pierwsze otwarcie lokalnego katalogu są nadal
synchroniczne. Nie twierdzimy, że dowolnie wolny dysk nie może opóźnić obsługi.

## Testy i review

Pełny suite: **2986 passed, 9 skipped**, 15,26 s; 114 dodatkowych przypadków
względem poprzedniego wyniku 2872. Pominięcia: 7 opt-in network i 2 niedostępne
symlinki Windows. Jedno ostrzeżenie pochodzi z upstream Google GenAI i Python 3.14;
nie zostało wyciszone.

`uv run --no-active ruff check anishift/ tests/` — PASS;
`ruff format --check anishift/ tests/` — 441 plików PASS;
`mypy anishift/ tests/` i `mypy --platform linux anishift/ tests/` — po 443 pliki PASS.
Każdy commit ma powtórzone te same pełne bramki; użyto osobnego cache mypy per platforma.

Testy obejmują rzeczywisty Renderer oraz `Application.run()/exit()`, klawisze,
bracketed paste, Unicode, rozmiary okna, osiągalność kolejki, stan zapisu, produkty
i atomowy wybór modeli. Dodatkowe live API, SAPI i media nie były potrzebne do tej zmiany.

Niezależne review wykryło i doprowadziło do naprawienia: raster po wyjściu,
zmienną wysokość fallbacku, niewidoczne akcje niskiego Home, dodatkowy wiersz
natywnego rastra, nieskuteczny powrót z błędu zapisu, podwójne/no-op zapisy i
szerokie znaki w edytorze. Pełny suite dodatkowo wykrył konieczność zachowania
osobnej gotowości wykonania przy nieaktualnym aliasie Palantira.

## Prompty i ostrzeżenie uv

[Raport promptów](../prompt-recommendations.md) wskazuje potwierdzoną sprzeczność
stylu z wiernością znaczeniu oraz kandydatów do krótszych instrukcji i A/B.
Aktywne Markdowny nie zostały zmienione. Usunięto wyłącznie nieużywane
`prompt_main.txt`, `prompt_helper.txt`, `prompt_helperSS.txt`; były nieśledzone,
więc Git nie posiada ich historii. Kopie sprawdzone SHA256 są pod
`%TEMP%/anishift-prompt-backup-63ac49c208c64906826332a0053b7df3/`.
Kopia tymczasowa jest odzyskiwalna do czasu czyszczenia systemowego temp.

Ostrzeżenie `VIRTUAL_ENV` pochodzi z uv przed uruchomieniem aplikacji. Poprawne
polecenie z aktywnym MangaShift: `uv run --no-active anishift`; nie przełącza ono
AniShift do obcej venv. Zachowanie potwierdza
[dokumentacja uv](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path), dostęp 2026-09-05.

## Odbiór i następny krok

Status **pending-human**: uruchomić `uv run --no-active anishift`, przejść kilka razy
Home ↔ Ustawienia, zmienić rozmiar i zoom, przetworzyć materiał, przewinąć kolejkę
do końca i wrócić End. Sprawdzić odstęp, czytelność, podskok i falę; po zamknięciu
poprzednia konsola ma wrócić bez namalowanej na niej maskotki. Testy nie potwierdzają
subiektywnej jakości ani zachowania wszystkich emulatorów terminala.

Potem [Plan 05: komplet opcji Auto](../plans/05-auto-preset-controls.md), porównanie
promptów oraz [Plan 03: pełny odbiór produktu](../plans/03-product-acceptance.md).
Zamknięcie okna lub awaria dysku nie gwarantują utrwalenia niezapisanej edycji.
Nie wykonano świeżego Windows, całego odcinka, hard-kill ani >4 GiB w tej iteracji.

Pozostałe granice: przycisk testu połączenia istnieje tylko dla Palantira. Metryka
komórki SIXEL jest pobierana przed startem; po zmianie czcionki obraz nie jest
ponownie kodowany. Proporcje przy zoomie wymagają odbioru, a restart przelicza
rozmiar obrazu. Naprawa prześwitywania konsoli nie jest dowodem poprawnego
skalowania we wszystkich emulatorach.

Zmiany są lokalne, na feature branch. Nie wykonano push, PR ani merge.

Commity tematyczne:

- `e1bde51` — renderer, responsywny branding, nawigacja kolejki i postęp.
- `47f9125` — komplet produktów, trwałość ustawień, klawiatura i wybór modeli.
