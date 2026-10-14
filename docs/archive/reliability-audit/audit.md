---
kind: review
status: fail
reviewed-state: c2e89964a4dd7d0a8efcdefacf2a7db609ec81e8
date: 2026-09-04
---

# AniShift — audyt niezawodności i jakości

## Werdykt

**Ocena ogólna: 6/10.** To ocena inżynierska względem celu niezawodnej aplikacji
do regularnego używania, nie procent pokrycia testami. Repozytorium ma sensowny
podział odpowiedzialności, dużo skutecznych testów i działające mechanizmy
ochrony wyników. Nie jest jeszcze gotowe do bezobsługowej automatyzacji:
możliwy jest fałszywy sukces tłumaczenia, utrata powtarzanej kwestii w lektorze
oraz porażka poprawnego renderu na granicy audio i kontenera.

`FAIL` oznacza niespełnienie tego kontraktu niezawodności. Nie oznacza, że wszystkie
przebiegi są zepsute lub że potrzebne jest przepisanie projektu.

| Obszar | Ocena | Powód |
| --- | ---: | --- |
| Architektura i katalogi | 7/10 | Dobry podział produktu i domen; dublowane adaptery legacy i duże kontrolery |
| Typowanie i automatyczne bramki | 8/10 | Ruff, oba targety mypy, rozbudowany pytest; lokalne adnotacje niepełne |
| Integralność wyniku | 5/10 | Niekompletne tłumaczenia i niektóre poprawne media źle klasyfikowane |
| Anulowanie i procesy | 5/10 | Dobre tokeny i bramki zapisu; niejednolite deadline i lifecycle |
| Postęp i diagnoza w UI | 4/10 | Część pomiarów znika między usługą i rendererem; wynik błędu zbyt ubogi |
| Wydajność | 6/10 | Bounded concurrency i cache; zmierzony koszt startu, blokowanie koordynatora |
| Dowody integracyjne | 7/10 | Prawdziwe testy narzędzi istnieją, ale znalezione kombinacje nie są pokryte |
| Dokumentacja i prostota opisów | 5/10 | Liczne historyczne kontrakty i wielowierszowe opisy powtarzające kod |

Nie wyliczam średniej z pozorną dokładnością. Ważniejsze od końcowej liczby są
konkretne usterki, ich skutki i dowody poniżej.

## Zakres i baseline

- Commit: `c2e89964a4dd7d0a8efcdefacf2a7db609ec81e8`.
- Branch: `work/interactive-cli/04-mascot-polish`; przed audytem brak zmian
  śledzonego kodu.
- Zachowane nieśledzone materiały: `prompt_helper.txt`, `prompt_helperSS.txt`,
  `prompt_main.txt` w `anishift/services/translation/engines/llm/prompts/`.
- Badano wejście CLI, application, konfigurację, domeny, utils, testy, CI,
  instrukcje i historię najważniejszych zmian. Niezależne części review objęły
  translation/LLM/text, media/TTS/setup oraz fundamenty/utils.
- Dowody: odczyt kodu i wywołań, bezsieciowe reprodukcje, kompletne bramki,
  dwa krótkie eksperymenty FFmpeg oraz ograniczony pomiar prezentacji.
- Nie wykonano przeglądu każdego możliwego stanu programu ani dowodu braku
  wszystkich błędów. Nie wykonywano pełnego odcinka przez rzeczywiste API.

Pełne ścieżki kodu są względne względem root repo; skróty `translation/`, `llm/`,
`audio/`, `subtitles/`, `composition/` i `extraction/` oznaczają odpowiednie katalogi
w `anishift/services/`. Skróty `application/`, `cli/`, `config/`, `setup/` i `utils/`
oznaczają katalogi w `anishift/`. Numery linii dotyczą baseline.
Symbol jest trwalszym odnośnikiem niż numer. Status napraw znajduje się wyłącznie
na [tablicy](tasks.md), żeby raport baseline nie zmieniał się w konkurencyjny tracker.

## Czym dziś jest repozytorium

| Granica | Odpowiedzialność i obecny stan |
| --- | --- |
| `cli/main.py`, `cli/interactive/` | Typer plus jedna aplikacja Prompt Toolkit, Rich do renderowania; Home, Auto, Manual, Settings |
| `application/discovery.py`, `inspection.py` | Grupy MKV/MP4/TXT i sidecarów, identyfikacja ścieżek i walidacja wejścia |
| `application/planner.py`, `planning.py` | Niemutowalny plan zadań oraz wymagane produkty i zależności |
| `application/scheduler*.py`, `sessions.py` | Pula zasobów, wykonanie gotowych zadań, cancellation, prywatny run-scope i publikacja |
| `services/subtitles`, `text` | Podział spoken/displayed, formaty, Unicode i heurystyki segmentacji |
| `services/translation`, `services/llm` | Google/DeepL/LLM, format numerowanych linii, retry, naprawa i podział po limicie |
| `services/tts`, `audio` | Klipy głosu, oś czasu, normalizacja i miks; Edge/SAPI/ElevenBytes/ElevenLabs |
| `services/composition` | MKV oraz MP4 z gotowych artefaktów |
| `config`, `setup`, `platform` | Preferencje i sekrety, narzędzia zewnętrzne, granice systemu |
| `utils` | Współdzielone narzędzia, ocenione bez zmian |

Auto i Manual dzielą backend. Usługi wykonują decyzje planera. To właściwy
fundament; przeniesienie wszystkiego do jednej klasy lub nowego layoutu nie
rozwiązałoby znalezionych błędów.

TXT jest rzeczywiście wejściem, ale `_build_text_plan()` dopuszcza tylko `FULL_PL`
i tworzy techniczny SRT. Audiobook, watcher folderu, drag-and-drop/import oraz
pobieranie odcinków nie są ukończonymi możliwościami. Domyślny preset żąda także
lektora, więc sam TXT wymaga dziś odpowiedniego wyboru produktów; nie należy
przedstawiać go jako gotowego Auto audiobooka.

Automatyczna instalacja nie jest jednolita: legacy extraction używa
`ensure_binary`, natomiast wcześniejsze rozpoznawanie MKV/MP4 i większość
pozostałych usług używa `require_binary`. Brak narzędzia może zatrzymać przebieg
przed dotarciem do leniwego instalatora. Pythonowe zależności przygotowuje `uv`;
głosy SAPI są zależnością systemową.

## Wyniki uruchomionych kontroli

| Kontrola | Wynik |
| --- | --- |
| `uv run ruff check anishift/ tests/` | PASS |
| `uv run ruff format --check anishift/ tests/` | PASS, 436 plików |
| `uv run mypy anishift/ tests/` | PASS, 438 plików źródłowych |
| `uv run mypy --platform linux anishift/ tests/` | PASS, 438 plików źródłowych |
| `uv run pytest` w zastanym środowisku | 2593 passed, 7 skipped, 1 failed, 21,46 s |
| Ten sam suite, bez `NO_COLOR` tylko w procesie potomnym | 2594 passed, 7 skipped, 27,71 s |
| `uv run anishift --help` | PASS |
| Oba hooki, na plikach wybieranych przez CI | PASS |
| FFmpeg: krótki obraz + dłuższy lektor | Potwierdzone F07 |
| FFmpeg: apostrof w katalogu napisów | Potwierdzone F10 |

Jedyny pierwotny failure to
`tests/cli/test_interactive_palette.py::test_the_accent_style_paints_the_mascot_azure`:
środowisko miało `NO_COLOR=1`, a test bezwarunkowo oczekiwał ANSI RGB. Nie zmieniano
globalnego środowiska ani kodu, żeby uzyskać PASS. Pozostaje realna luka izolacji testu.
Pominięcia: pięć testów sieciowych i dwa wymagające niedostępnych tutaj symlinków.
DeprecationWarning pochodził z `google.genai` na Pythonie 3.14.2.

Nie zmierzono procentowego pokrycia kodu. Liczba testów nie dowodzi jakości
tłumaczenia, odsłuchu, płynności SIXEL ani poprawności aktualnego zdalnego modelu.

## Findings — integralność tekstu i mediów

### F01 — P1: częściowa porażka Google staje się produktem FULL_PL

`translation/engines/google/_batching.py::_per_line` zachowuje tekst źródłowy
z `ok=False`. `translation/types.py::FileTranslation.is_success` sprawdza tylko
`error`. `application/translation_handler.py::_translate_subtitles`,
`_translate_text` i `execute` traktują taki wynik jako poprawny; `failed_lines`
jest wyłącznie metadanymi.

Reprodukcja reviewera: wszystkie żądania Google kończą się
`TranslationEngineError`; fasada oddaje `is_success=True`, `failed_lines=1`
i `English source`. Bezpośredni odczyt handlera potwierdza możliwość zapisania
tego jako polskiego produktu i dalszego TTS.

Reakcja: zablokować niepełny wynik przed zapisem produktu i zależnymi etapami.
Historyczny rekord domenowy świadomie dopuszcza partial result; nie zmieniać
potajemnie jego znaczenia dla wszystkich konsumentów. Nie przywracać cichego
fallbacku dostawcy.

### F02 — P1: urwany SSE lub zdarzenie błędu mogą dać sukces LLM

`llm/engines/palantir/http.py::stream_palantir_request` kończy na EOF i wymaga
jedynie niepustej listy eventów. `_decode_sse_data` odrzuca `[DONE]` bez
zapamiętania zakończenia. `normalize.py::merge_google_stream` i
`merge_openai_stream` pomijają eventy błędu i dopuszczają brak finish reason.
Normalizer zwraca `unknown`; translator odrzuca tylko znane limity wyjścia.

Bezsieciowe reprodukcje: Google urwany po `[0] Truncated transla` oraz Chat
z deltą i późniejszym `{"error": ...}` kończą jako `BatchedLine(..., ok=True)`.
Prowadzący powtórzył przypadek Chat i potwierdził `finish_reason='unknown'`.

Reakcja: sprawdzić zakończenie i błąd zgodnie z konkretnym protokołem. Brak
terminalnego sukcesu nie może być sukcesem tłumaczenia. Zachować pojedynczego
właściciela retry i bezpieczne, typowane błędy.

### F03 — P1: xAI incomplete gubi powód limitu

`llm/engines/palantir/normalize.py::_extract_xai_responses` bierze wyłącznie
`status`, pomijając `incomplete_details.reason`. `status='incomplete'` z
`reason='max_output_tokens'` przechodzi jako tekst; `_hit_output_limit` nie
rozpoznaje takiej wartości. Reprodukcja reviewera przez mock HTTP potwierdziła
sukces urwanej numerowanej linii bez podziału.

Reakcja: znany limit mapować na istniejący sygnał podziału; inne niekompletne lub
nieudane odpowiedzi odrzucać. Nie traktować każdego incomplete jako limitu.

### F04 — P2: puste tłumaczenie przechodzi dwiema drogami

`translation/engines/llm/line_contract.py::_consume_numbered` sprawdza tekst przed
`_unescape`. Linia z literalnym `\n` daje `{0: '\n'}`, `violation=None`.
`translation/engines/google/_batching.py::_per_line` akceptuje pusty `_restore`,
choć `_map_parts` tę samą sytuację oznacza jako porażkę. Oba przypadki odtworzono
bez sieci; przypadek parsera również przez prowadzącego.

Reakcja: walidować niepustość po dekodowaniu; współdzielić regułę mapowania Google.
Istniejąca naprawa numeru obsłuży błąd parsera. Nie zgadywać języka po samej
równości źródła i tłumaczenia — nazwy własne mogą pozostać identyczne.

### F05 — P1: zwijanie animacji usuwa powtórzoną wypowiedź SRT

`subtitles/service.py::split_subtitles` bezwarunkowo używa `_collapse_fbf_indexed`.
`_collapse_group` skleja identyczny tekst i styl z przerwą do 500 ms. Dwa osobne
SRT `No!` w `0–500 ms` i `600–1100 ms` dają jeden spoken `0–1100 ms`.

Reakcja: zachować wystąpienia SRT; deduplikację animacji ograniczyć do rzeczywistych
przypadków ASS. Zachować regresje animacji i sprawdzić sprzężenie z writerem.

### F06 — P2: pusty jawny wybór spoken jest ignorowany

`subtitles/service.py::_dialogue_decisions` przy zerowej liczbie spoken ustawia
wszystkie nierysunkowe eventy jako spoken. `split_subtitles(...spoken_styles=())`
dla ASS `Signs` zwraca `('spoken',)`. Reprodukcja w pamięci.

Reakcja: odróżnić brak automatycznej diagnozy od jawnego pustego wyboru.
Automatyczny fallback jest historycznie opisany; jego całościowa zmiana wymaga
świadomej decyzji, nie tylko usunięcia gałęzi.

### F07 — P1: dłuższy lektor powoduje odrzucenie poprawnego MP4

`composition/service.py::_compose_container_mp4` i legacy `_compose_burn`
przekazują czas źródłowego wideo do `probe.py::validate_burned`. Walidator porównuje
czas całego kontenera z tolerancją 2 s. Audio zgodnie ze swoim kontraktem zachowuje
ogon przez `duration=longest`.

Reviewer wygenerował rzeczywistym FFmpeg wideo 1 s i AAC 4 s. Produkcyjna komenda
utworzyła poprawny MP4 4 s; walidacja odrzuciła go jako
`Rendered duration does not match the source`.

Reakcja: walidować właściwe czasy wideo i produktu, z uwzględnieniem narracji.
Nie obcinać wypowiedzi, żeby dopasować wynik do złego warunku walidacji.

### F08 — P1/P2: pełna operacja audio ma ten sam limit 30 s co krótka operacja

`audio/config.py` ustawia `operation_timeout_s=30.0`;
`application/runtime.py::_audio_config` go nie zmienia. Limit trafia także do
pełnego miksu w `audio/service.py` i transkodowania w `audio/transcode.py`.

Potwierdzona semantyka: nadal postępująca operacja >30 s zostanie przerwana.
Nie ustalono długości realnego odcinka powodującej przekroczenie na tej maszynie.
Reakcja: osobny budżet długiej pracy i wykrywanie braku aktywności, zweryfikowane
krótkim testem sterowanego czasu oraz późniejszym pomiarem rzeczywistego materiału.

### F09 — P2: ostrzeżenie mkvextract jest porażką

`extraction/service.py::extract_tracks` odrzuca każdy niezerowy exit code.
Neutralny runner też uznaje go za błąd. Lokalna dokumentacja
`external/docs/mkvtoolnix/mkvextract.html` w sekcji exit codes mówi: 1 oznacza
ostrzeżenie, 2 błąd. Composition już rozróżnia te stany dla MKVToolNix.

Reakcja: przy code 1 sprawdzić wyniki i zgłosić ostrzeżenie; code 2 pozostawić
błędem. Nie rozszerzać tej reguły na FFmpeg.

### F10 — P2: apostrof w katalogu nadal psuje wypalanie napisów

`composition/paths.py::filter_safe_copy` oczyszcza nazwę pliku, ale pozostawia
`work_dir`. W aktywnym torze katalog powstaje pod destination. Reviewer wykonał
rzeczywisty render jednej klatki z napisami w katalogu o prefiksie
`anishift's-audit-`; produkcyjny filtr nie otworzył pliku. Testy trudnej nazwy
pliku nie pokrywają apostrofu w nazwie rodzica.

Reakcja: bezpieczna musi być cała ścieżka widziana przez gramatykę filtra, np.
kontrolowany `cwd` i względna nazwa kopii. Dodać test na rzeczywistym FFmpeg.

## Findings — cykl życia, postęp i terminal

### F11 — P1: aktywny legacy MKV nie ma kontrolowanego deadline

`application/extraction_handler.py` kieruje MKV do legacy `extract_tracks`.
Ta funkcja nie przyjmuje timeoutu handlera; iteruje po stdout i wykonuje
`process.wait()` bez limitu. Cancel używa terminate bez gwarantowanego bounded
kill/wait. Wyjątek obserwatora nie gwarantuje zamknięcia procesu.

Dowód: aktywny przepływ i kod; nie symulowano zawieszenia prawdziwego mkvextract.
Na POSIX proces ignorujący SIGTERM dodatkowo utrudnia cancel; Windows zwykle
kończy proces po terminate, ale nadal nie ma deadline. Reakcja: zachować jeden
bulk mkvextract i jego prawdziwe GUI progress, uzupełnić lifecycle i cleanup.

### F12 — P1/P2: Ctrl+C technicznego CLI może czekać na całą pracę

`application/scheduler.py::run` po przerwaniu `_coordinate` wykonuje
`executor.shutdown(wait=True, cancel_futures=True)` bez ustawienia tokenu.
`cli/main.py::_executed_run` łapie KeyboardInterrupt dopiero po wyjściu z tego
stosowego wywołania. Już uruchomione zadania nie dostają prośby o cancel.

Dowód kodowy; brak rzeczywistego testu Ctrl+C z aktywnym providerem. Reakcja:
właściciel wykonania ustawia cancel przed dołączeniem workerów; test z kontrolowanym
workerem ma sprawdzić kolejność, nie tylko kod wyjścia atrapowej funkcji.
Interaktywny exit/failure również wymaga testu domknięcia workerów: `app.run`
w finally zamyka ustawienia i maskotkę, nie aktywną pracę.

### F13 — P2: blokada jednego produktu zatrzymuje koordynatora

`scheduler_runtime.py::_publish_durable` ponawia do 240 razy, śpiąc po 0,25 s.
Wywołanie odbywa się synchronicznie z `commit_success` w koordynatorze.
Przez do 60 s nie drenuje on postępu innych workerów ani nie przyjmuje kolejnej
gotowej pracy. Nie trzyma stale locka cancellation — problemem jest zajęty
koordynator, nie deadlock tego locka.

Reakcja: oczekiwanie na ponowną próbę nie może blokować pętli koordynacji;
zachować atomową finalną operację i bramkę cancel/generation. Test: dwa niezależne
pliki, zablokowany cel jednego, postęp i zakończenie drugiego widoczne na czas.

### F14 — P2: postęp narzędzi nie przechodzi przez cały aktywny przepływ

| Faza | Backend | Handler / UI |
| --- | --- | --- |
| MKV extraction | Prawdziwe `#GUI#progress` | Podłączone; zachować |
| MP4 extraction | Runner oddaje wynik po zakończeniu | Tylko końcowe 100 |
| Tłumaczenie | Deltas tylko część protokołów | Osobne błędy F15 |
| TTS | Rzeczywiste callbacks/retry | Najpełniej podłączony etap |
| Audio | Nazwy faz, brak procentu kodowania | `_show_audio_phase` ustawia 0; rysowany determinate bar |
| MKV/MP4 composition | Parser istnieje, `compose_container` nie przyjmuje callbacku | Handler emituje dopiero 100, renderer nie mapuje TaskKind composition |
| Publikacja/walidacja | Brak callbacku postępu | Poprzednia etykieta może pozostać na ekranie |

`cli/interactive/progress.py` nie ma spinnera dla audio mimo deklaracji AGENTS;
`_append_row` zawsze rysuje procent. FFmpeg potrafi raportować `key=value`
przez `-progress`, a częstotliwość reguluje `-stats_period`:
[oficjalna dokumentacja](https://ffmpeg.org/ffmpeg.html#toc-Advanced-options).

Reakcja: przeciągnąć istniejące pomiary przez wszystkie granice; brak pomiaru
przedstawiać jako aktywność. Nie zastępować brakującego backendu animowanym procentem.

### F15 — P2: licznik tłumaczenia liczy newline, nie poprawne numery

`translation/engines/llm/service.py::_StreamProgress.consume` liczy każde `\n`,
łącznie z pustymi liniami i fences. Retry transportu ponownie zasila ten sam
licznik; `_split` używa reportera bez offsetu ukończonej połowy. Naprawy kontraktu
nie emitują własnego retry, a UI `_retry_task` przyjmuje tylko TTS.

Reprodukcje reviewera: retry daje `1/3, 2/3, 3/3, 3/3, 3/3`; podział po limicie
daje `3/4, 2/4, 2/4, 4/4`. Clamp w application ukrywa cofnięcie, utrzymując
zawyżony stan. Nie jest prawdą, że dzisiejszy pasek liczy zwalidowane `[N]`.

Reakcja: stan próby, domknięte rozpoznane numery, offset podziału, osobna faza
walidacji/naprawy. Zakończenie ostatniej linii ustala poprawny terminalny stan,
nie domyślny brak kolejnego newline. Nie parsować całego rosnącego tekstu od nowa
po każdym tokenie.

### F16 — P2: interaktywny wynik traci przyczynę błędu

`cli/interactive/app.py::_execute_run` ignoruje zwrócony `RunResult`.
`RichRunProgress` nie zachowuje komunikatu nieudanego `TASK_FINISHED`; finał
grupy daje tylko `Failed`. Zwykła awaria workera jest wynikiem, a nie wyjątkiem,
więc `_problem_text` nie zapewnia w tym przypadku opisu.

Reakcja: prosty wynik grupy z etapem, bezpieczną przyczyną, zachowanymi produktami
i możliwością skopiowania diagnozy. Zachować jeden renderer, bez dashboardu logów.

### F17 — P2: mierzalny koszt maskotki i niepotwierdzony fallback terminala

`TerminalRenderer.__init__` synchronicznie wywołuje `load_native_mascot`, zanim
uruchomi interfejs. Jeden pomiar na tej maszynie, bez odpowiedzi terminala na
zapytanie o komórki: **1,7069 s**, 46 klatek, 416041 znaków payloadu. To pomiar
enkodowania, nie p95 startu aplikacji. Powtarzane przygotowanie klatki Home
120×40: mediana **0,683 ms** dla 5 serii po 200 wywołań; bez wyświetlania.

Kod poprawnie cache'uje wordmark i payloady w sesji. Ciężki koszt jest przed
pierwszą klatką. Poll rozmiaru to 5 ms, refresh 100 ms; brak jeszcze pomiaru
CPU/latencji rzeczywistego terminala. Sam warunek Windows nie jest detekcją
obsługi SIXEL — fallback na niewspieranym terminalu wymaga osobnego dowodu.

Reakcja: pomiar pełnego startu i CPU, następnie odroczenie lub tańsze przygotowanie
obrazu. Animacja gradientu dopiero po ustaleniu budżetu. Nie usuwać działających cache.

## Findings — konfiguracja, narzędzia i współdzielony kod

### F18 — P2: legalny JSON z błędnym typem może zablokować aplikację

`config/user_settings.py::_clean_string` sprawdza membership bez typu:
`{"mode":[]}` i `{"translation_engine":{}}` rzucają TypeError. `_clean_number`
dopuszcza float do pól int: `translation_max_retries=1.5` przechodzi loader,
a potem `range` w retry rzuca TypeError. Obie reprodukcje wykonano bez odczytu
rzeczywistych ustawień, przez podmianę źródła danych.

Reakcja: rozdzielić ścisły int i float, sprawdzić str przed membership;
zachować zachowanie recovery loadera. Nie dodawać ogólnego `except Exception`.

### F19 — P2: katalog modeli nie izoluje wszystkich błędnych wpisów

`config/model_catalog.py::_relative_route` przepuszcza ValueError z `urlsplit('//[')`;
jeden provider blokuje cały katalog zamiast `CatalogIssue` dla niego.
Identyfikatory `same` i ` same ` po `.strip()` cicho nadpisują się mimo kontroli
duplikatów surowego JSON. Reprodukcje `parse_model_catalog` w pamięci.

Reakcja: mapować błąd URL na wadliwy wpis i wykrywać kolizje po normalizacji;
poprawne pozostałe wpisy pozostają dostępne. Nie przepisywać pliku JSONC.

### F20 — P2: automatyczne przygotowanie binarek jest niepełne

`services/media/mkv.py`, `mp4.py`, application runtime oraz audio/composition
wywołują `require_binary`, podczas gdy lazy `ensure_binary` istnieje w legacy
extraction. Preflight może odmówić pracy przed uruchomieniem instalatora.
Reakcja: jeden etap przygotowania potrzebnych narzędzi przed inspekcją, poza
wątkiem renderera, z postępem i bez dublowania downloadów.

### F21 — P2: instalacja usuwa sprawną binarkę przed zastąpieniem

`setup/installer.py::install_resource` wykonuje `final.unlink()` przed
`shutil.move` ze stagingu w systemowym temp. Błąd move pozostawia brak binarki;
przeniesienie między woluminami nie jest atomowym replace. Kod przeczy opisowi
atomowej instalacji w AGENTS.

Reakcja: zwalidowany staging na woluminie docelowym i replace bez wcześniejszego
unlink. Nie uruchamiano uszkadzającej instalacji na narzędziach użytkownika.

### F22 — P2: CI audytuje nie to środowisko

`.github/workflows/ci.yml` w jobie audit uruchamia samo `uvx pip-audit` bez
zależności projektu. `uvx` używa izolowanego środowiska narzędzia, a pip-audit
bez wskazanego wejścia bada bieżące środowisko. Nie jest to dowód audytu AniShift.
Źródła: [uv — tools](https://docs.astral.sh/uv/guides/tools/),
[pip-audit — usage](https://github.com/pypa/pip-audit#usage).

Reakcja: podać konkretny zestaw zależności wynikający z locka i sprawdzić listę
rzeczywiście audytowanych pakietów. Nie ogłaszać na tej podstawie podatności
konkretnej biblioteki — nie wykonywano zapytań do bazy podatności.

### F23 — P2: czytniki loggera nie współpracują z jego formatem

`utils/logger/core.py` zapisuje Loguru `serialize=True`, czyli `{text, record}`.
Prosty `log_reader.py` używany przez CLI oczekuje płaskich pól. Rzeczywista linia
ERROR zapisana do StringIO daje pusty filtr ERROR i statystyki UNKNOWN.
Chainable `readers/reader.py` rozumie format, ale filtr czasu zestawia timezone-aware
timestamp z naiwnym `datetime.now()` w `_time_helpers.py`, rzucając TypeError.
`cli.py::apply_filters` dodatkowo nadpisuje filtr poziomu filtrem czasu.

Reprodukcje reviewera korzystały z rzeczywistej serializacji, bez ujawniania
payloadów. Reakcja w osobnym zakresie utils: wspólna interpretacja formatu,
spójny czas, składanie filtrów. Test ma zaczynać od prawdziwie zapisanej linii.

### F24 — P2: metadane loggera zawierają bezwzględną ścieżkę

Scrubber chroni treść, extra i wyjątek, lecz `record.file.path` w serializacji
Loguru pozostaje absolutny. Potwierdzono wyłącznie boolean `is_absolute()` na
prawdziwym logu. Jest to rozjazd z regułą repozytorium; nie dowód wycieku klucza.
Reakcja: ustalić dozwolone metadane i sprawdzać wynik serializacji. Utils bez zmian.

## Prostota, struktura i dokumentacja

AST śledzonych plików Python; liczby obejmują również przykłady w utils,
natomiast testy wyłączono z dwóch pierwszych wierszy.

| Zakres | Pliki / linie | Docstringi modułów/klas/funkcji | Pozostałe stringi opisowe | Wielowierszowe opisy łącznie |
| --- | ---: | ---: | ---: | ---: |
| Aplikacja bez utils | 224 / 45912 | 1711 | 717 | 227 |
| Utils bez testów | 53 / 8305 | 364 | 82 | 188 |
| Wszystkie drzewa testów | 161 / 34078 | 5 | 4 | 0 |

Komentarze aplikacji: 89 separatorów, 84 dyrektywy i 81 pozostałych.
Testy: 70 dyrektyw, zero opisowych komentarzy. Dziewięć opisowych bloków pozostaje
w `tests/conftest.py` i `utils/*/tests/__init__.py`; obecne globy hooka/CI je omijają.
Nie jest prawdą, że cały kod testowy jest zalany komentarzami. Sensowne sprzątanie
to skrócenie powtórzeń w docstringach, a nie kasowanie separatorów i wiedzy o kontrakcie.

Duże miejsca odpowiedzialności to `cli/interactive/settings.py`,
`application/planner.py`, `application/service.py` i `config/user_settings.py`.
Nie dzielić ich według arbitralnego limitu linii. Najpierw wskazać niezależne
odpowiedzialności i konkretne zmiany utrudniane przez obecny podział. Wspólnym
długiem są powielone watchery cancellation w handlerach, kilka runnerów subprocess
i równoległe ścieżki legacy/nowe. Ich kontrakty najpierw wymagają testów;
ujednolicenie nazw bez tego może zgubić bulk extraction lub semantykę ostrzeżeń.

Potwierdzony drift instrukcji i dokumentacji:

- Root AGENTS odsyła do nieobecnych skilli `python`/`instructions`; aktualny
  standard znaleziono w `coding/references/python.md`.
- Root wskazuje historyczną roadmapę, której dalszy kierunek mówi o Textual;
  aktualny frontend to Prompt Toolkit. Starsze plany nie są specyfikacją obecnej pracy.
- README mówi o statycznej maskotce, a kod i śledzony asset używają GIF.
- CLI AGENTS mówi o `MultiProgressManager` i spinnerze audio; aktualny kod używa
  `ProgressBarBuilder` i procentu dla każdej fazy.
- Palantir docstringi opisują Google jako jedyny streaming, mimo obsługi Chat.
- W utils manifest przenośności podaje Python 3.10, kod używa składni 3.14;
  stary `_retry.py` importuje `anishift.errors` i przechodnie `tenacity`.
  Nie znaleziono aktywnego wywołania tego helpera; to dług biblioteki, nie dowód
  awarii dzisiejszego pipeline.
- Wiele lokalnych zmiennych nie ma adnotacji wymaganych przez AGENTS, mimo PASS
  mypy. Nie naprawiać tego masowo w diffie funkcjonalnym.

Repo-root jest wyznaczany kilkoma drogami. Obecne uruchamianie z checkoutu jest
świadomym kontraktem; brak niezależnej instalacji wheel nie jest automatycznie
błędem produktu. Przypadkowe katalogi w zastanym workspace nie dowodzą, że obecny
runtime je tworzy, i nie są przeznaczone do usunięcia podczas tego audytu.

## Historia wyjaśniająca ryzyka

| Commit | Znaczenie dla audytu |
| --- | --- |
| `4b31f36`, `1fb996f`, `9a79982` | Przejście od Textual do CLI i ponowne dobudowanie interakcji; stare kontrakty frontendu wymagają selekcji |
| `31a0b1d` | Równoległe probowanie i reuse inspekcji — istniejąca wartościowa optymalizacja |
| `1e21ec2`, `ae806f5` | Recovery publikacji przy Windows file locks; wyjaśnia F13 |
| `2e164fa`, `927a61e` | Numerowany kontrakt; niepustość przed unescape leży w tej implementacji |
| `10dd188`, `39f4c47` | Zmiany postępu/streamingu; najważniejsze przypadki awarii obejmują granice nowych callbacków |
| `db52d44` | Ożywienie testów CLI względem istniejących interfejsów |
| `60bb958`, `c2e8996` | Prompty/style i nowy model; nie zastępują walidacji protokołu |

Historia pokazuje serię lokalnych korekt kontraktów, a nie dowód, że każda z nich
jest błędna. Plan napraw ma chronić odzyskane zachowania testami integrującymi
granice, zamiast odtwarzać odrzucony interfejs.

## Niewiadome i dalsze dowody

- Pełny E2E na rzeczywistym odcinku, odsłuch i ocena polszczyzny pozostają niewykonane.
- Nie sprawdzano dostępności ani kosztu rzeczywistych kont i modeli.
- Nie mierzono CPU w bezczynności, p95 klawisz→ekran, przepustowości odcinków,
  dużego audiobooka, zużycia pamięci ani konkurencji kilku procesów aplikacji.
- Streaming aktywnego requestu LLM nie jest przerywany przez token na poziomie
  transportu; kontrola przed/po wywołaniu chroni zapis, ale nie zapewnia szybkiego cancel.
- `composition/commands.py` ma `wait()` po EOF; próby reviewera nie odtworzyły
  zawieszenia. Pozostaje przypadek do kontrolowanego testu, nie potwierdzony runtime bug.
- Font dostępny wyłącznie jako attachment, `thought` parts modeli, wznowienie po
  restarcie całej aplikacji i nazwy CJK w ciasnym widoku wymagają osobnych prób.
- Obecny reflow już istnieje. Zasada przesuwania każdego „się” nie jest poprawnym
  uniwersalnym algorytmem; potrzebny korpus poprawnych i wadliwych polskich przykładów,
  ocena kontekstu oraz testy niezmienności słów i interpunkcji.
- Logger dla niestandardowego poziomu stdlib 35 rzuca błąd po zamianie na nazwę
  `"35"`; odtworzone, ale bez znalezionego produkcyjnego emitera. Dług utils o niższym priorytecie.

## Zalecenie

Zachować strukturę domen. Najpierw naprawić akceptację produktów i odpowiedzi,
potem granice konfiguracji, lifecycle i integralność mediów; następnie przeciągnąć
postęp przez aktywny tor i zmierzyć UI. Uproszczenia i stylistykę wykonywać
w osobnych, sprawdzalnych iteracjach. Szczegółowy następny krok opisuje
[pierwszy plan](plans/01-translation-integrity.md).
