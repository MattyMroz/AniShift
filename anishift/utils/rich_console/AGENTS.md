# rich_console

Przenośny (współdzielony z mm_avh): preskonfigurowana `console`, motyw `RICH_THEME`, managery pasków postępu, helpery formatujące.

## Mapa katalogów

- `console.py` — instancja `console` z auto-highlightem URL/ścieżek/liczb (spany) i normalizacją przecinka dziesiętnego
- `theme.py` — `RICH_THEME` (150+ styli), klasa `Colors`, introspekcja styli
- `utilities.py` — bezstanowe helpery: ikony statusów, formatowanie bajtów/czasu/procentów, kolor progresu
- `progress/` — managery pasków (`ProgressBarManager`, `MultiProgressManager`, `ProgressBarBuilder`)
- `examples/` — dema palety/progresu/motywu + runner
- `tests/` — testy konsoli, motywu, progresu, `FORCE_COLOR`

## Pułapki

- Import `console.py` MONKEYPATCHUJE `console.print` na poziomie modułu — sam import zmienia zachowanie `print` (normalizacja liczb + highlight spanami), nie tylko udostępnia obiekt. `console.py:315`
- `FORCE_COLOR` czytany raz przy budowie konsoli w czasie importu — ustawienie zmiennej PO imporcie nie zadziała; wymusza sztywne `width=400`, `force_terminal=True`. `console.py:155-167`
- `console.print(..., highlight=False)` nadal opakowuje czyste stringi w `Text`, by nawiasy nie były parsowane jako markup — to nie zwykłe „wyłącz highlight" Richa. `console.py:306-308`
- Highlight to spany na surowym stringu; treść NIE jest re-parsowana jako markup, więc `[` i `\` w ścieżkach przetrwają dosłownie. `console.py:116-118,284-287`
- Kolejność wzorców w `_HIGHLIGHT_STYLES` jest znacząca — wcześniejszy dopasowany zakres blokuje nakładające się (URL > ścieżka > bool > liczba). `console.py:87-88,128-131`
- `get_status_icon` domyślnie zwraca STRING z tagami Rich markup (`[success]✅[/success]`) — trzeba go wypisać przez konsolę parsującą markup, inaczej pokażą się dosłowne nawiasy. `utilities.py:39,71`
- Ikony `warning`/`info`/`running`/`stopped` mają celowo doklejoną spację w emoji (`"⚠️ "` itd.) — string ikony nie jest „goły". `utilities.py:59-64`
- `format_bytes(binary=False)` używa bazy 1000 z jednostkami dziesiętnymi `KB/MB`; baza 1024 przełącza na `KiB/MiB`. `utilities.py:108-109`

## Konwencje

- Styl motywu `black` = „czarny na białym" (`rgb(0,0,0) on white`), nie sam czarny tekst. `theme.py:107-109`
- `logging.level/time/message` zakodowane na sztywno jako `"red"`, nie z palety `Colors`. `theme.py:128-130`
- `Colors.NORMAL` = `"default"` (kolor domyślny terminala), nie konkretny kolor. `theme.py:59`
- `format_bytes/duration/percentage`, `get_progress_color` rzucają `ValueError` na wartościach ujemnych / spoza 0–100, nie zwracają wyniku granicznego. `utilities.py:101-103` i in.

## Uwaga

- Docstringi importują jako `from rich_console import ...` (bez prefiksu `anishift.utils.`) — realna ścieżka to `anishift.utils.rich_console`. `console.py:8`
