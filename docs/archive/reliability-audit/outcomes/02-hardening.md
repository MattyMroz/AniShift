---
kind: outcome
status: partial
created: 2026-09-04
baseline: c2e89964a4dd7d0a8efcdefacf2a7db609ec81e8
---

# Wynik programu napraw

Istniejący pipeline został poprawiony, połączony i sprawdzony automatycznie.
Nie oznacza to zakończenia całego masterplanu. Odsłuch, fizyczny terminal,
pełny odcinek i brakujące scenariusze M08 przechodzą do
[Planu 03](../plans/03-product-acceptance.md). Statusy zadań są wyłącznie
na [tablicy](../tasks.md); [audyt](../audit.md) zachowuje historyczny baseline 6/10.

Ocena techniczna po zmianach: **8/10, warunkowo**. Uzasadnia ją zamknięcie
odtworzonych usterek i rozszerzenie testów, nie gwarancja braku innych błędów.
Brak pełnej akceptacji produktu wyklucza ocenę 10/10.

## Co działa inaczej

| Obszar | Rezultat |
| --- | --- |
| Tłumaczenie | Partial i decoded blank nie przechodzą do polskiego produktu; SSE wymaga poprawnego zakończenia; xAI limit zachowuje split |
| Postęp modelu | Zamknięte numerowane linie liczone w granicach requestu, retry i split; walidacja poprzedza sukces |
| Napisy | Osobne powtórzenia SRT zachowane; jawny pusty spoken respektowany; writer chroni kolejność; reflow nie przenosi słów |
| Media | Osobne długości video i kontenera chronią ogon narracji; render ma dłuższy deadline; apostrof w ścieżce działa |
| Procesy | Cichy stdout i EOF nie omijają cancel/deadline; exit 1 MKVToolNix wymaga poprawnego wyniku; późne cancel usuwa tylko własny wynik |
| Publikacja | Oczekiwanie na zablokowany plik nie zatrzymuje innych grup; generation i cancel nadal chronią replace |
| Setup | Narzędzia przygotowane przed probe; staging i atomowa wymiana; pliki 0 B nie udają gotowych binarek |
| UI | Jeden renderer, gradient istniejącej palety, rzeczywisty procent albo aktywność, przewijany wynik z przyczynami i produktami |
| Utils | Rzeczywiste JSONL czytane i filtrowane; UTC chroni względne okna DST; oba sinki redagują ścieżki, sekrety i kod SyntaxError |
| Utrzymanie | Krótkie opisy aplikacji bez zmian wykonywalnego AST; separatory zachowane; rozszerzony zatwierdzony strażnik testów |

Użycie `simple` ograniczyło zmiany do istniejących granic i helperów: nie powstał
nowy renderer, system workerów ani kopia loggera. Nie reorganizowano katalogów
bez potwierdzonego problemu odpowiedzialności. Współdzielone utils naprawiono,
lecz nie poddano ich masowemu skracaniu dokumentacji.

## Automatyczny dowód na połączonym drzewie

Windows, Python 3.14.2, 2026-09-04:

| Komenda | Wynik |
| --- | --- |
| `uv run ruff check anishift/ tests/` | PASS |
| `uv run ruff format --check anishift/ tests/` | 440 plików, PASS |
| `uv run mypy anishift/ tests/` | 442 plików, PASS |
| `uv run mypy --platform linux anishift/ tests/` | 442 plików, PASS; to analiza typów, nie runtime Linux |
| `uv run pytest` | 2872 passed, 9 skipped, 17,57 s w końcowej próbie integracyjnej |
| `check_test_comments.py` na wszystkich Python tests/support | PASS, włącznie z nowymi plikami i bundled utils |
| `check_const_docstrings.py` na `anishift/` | PASS |
| `uv run anishift --help` | PASS |

Siedem skipów dotyczy opt-in network, dwa niedostępnych directory symlinks Windows.
Ostrzeżenia pochodzą z deprecacji `_UnionGenericAlias` w Google GenAI/Python 3.14;
nie zostały globalnie wyciszone. Pełny suite przechodzi bez usuwania `NO_COLOR`
ze środowiska użytkownika. Przed commitami kontrole są ponawiane; czas może się różnić.

Regresje odtworzono przed poprawkami, m.in. 15 przypadków integralności
tłumaczenia, 9 zakończenia modeli, 9 prywatności loggera, DST i 8 późnego cancel /
pustych binarek. Pierwsze skrócenie opisów objęło 226 bloków w 76 plikach;
po integracji ponownie skrócono 32 przywrócone bloki w 7 plikach. Oba porównania
wykonywalnego AST przed/po samym skróceniu nie wykazały różnic.

## Niezależne review i poprawki po nim

Recenzenci sprawdzali inne obszary niż te, które implementowali. Review wykryło
i doprowadziło do naprawy: mieszanie prób w postępie, zasłanianie aktywnego TTS
publikacją, nieograniczone przewijanie wyniku, wycieki paths/notes/SyntaxError,
błąd godziny przy DST, późne cancel i puste binarki. Poprawiono też glob CI
pomijający bezpośrednie dzieci katalogów testów oraz nieścisły opis procentu.

Końcowe niezależne kontrole: tłumaczenie 634 PASS / 5 network skip;
logger 145 PASS oraz rzeczywisty zapis do obu sinków; lifecycle 64 PASS.
Oryginalne wyjątki pozostają niezmienione; redakcja zachowuje basename, typ,
errno, cause, context, notes i groups. Nie jest to dowód rozpoznawania każdego
możliwego formatu sekretu — domeny nadal nie mogą logować treści ani kluczy.

Dodatkowy rzeczywisty zapis wykrył pominięte `Path`/`PurePath` w zagnieżdżonych
wartościach oraz kluczach metadata. Trzy regresje FAIL→PASS rozszerzyły redakcję
o te typy; kolejna regresja chroni rozpoznany sekret także jako klucz mapowania.
Cały logger: 314 PASS, potwierdzone niezależnie na obu sinkach. Rooted path zachowuje basename, względna ścieżka
pozostaje względna. Kontrakt nie obejmuje automatycznego wykrywania sekretów
w dowolnym własnym `repr` obiektu — źródło logowania nadal odpowiada za dane.

Powtarzane bramki ujawniły niestabilny test równoległej normalizacji: założenie,
że wszystkie wątki wystartują w 50 ms, dawało fałszywy failure pod obciążeniem.
Zastąpiono sleep barierą czterech wątków z timeoutem. Asercja wymaganej równoległości
pozostaje bez osłabienia. Kolejne pełne suite przeszły.

W teście timeoutu Windows wykryto osobny race venv redirectora: przerwanie
launchera podczas startu mogło pozostawić zawieszony interpreter potomny
(7 z 24 równoległych prób). Test zastępujący jednoprocowe `mkvextract` używa teraz
bezpośredniego interpretera; 24 z 24 prób zamknęły proces, stdout i czytnik.
Nie usunięto asercji i nie zwiększono grace. W produkcyjnym `_read_output`
naprawiono ownership: sam czytnik zamyka stdout także po EOF późniejszym niż join.
Deterministyczny delayed-EOF test najpierw FAIL, potem PASS; regresja 73 PASS / 1 skip.
Siedem własnych procesów probe zamknięto po sprawdzeniu ich pochodzenia.
Nie dodano gwarancji zamykania dowolnych drzew procesów tworzonych przez wrappery.

## Dodatkowe domknięcie techniczne M08

Po poleceniu kontynuacji dodano cztery przypadki recovery w nowym interpreterze:
TTS po kontrolowanym cancel reużywa poprawny klip, regeneruje ucięty lub po zmianie
tekstu; publisher odrzuca niepełny SRT, zachowuje poprzedni produkt, a poprawny
publikuje atomowo. PID procesu jest sprawdzany, cache/manifest/pliki są rzeczywiste;
provider i walidator TTS pozostają atrapami. Niezależne review: 4 PASS. Nie jest to
test wymuszonego zabicia procesu ani rzeczywistego dekodowania audio.

Prawdziwy font `segoeui.ttf` przetrwał merge byte-for-byte, źródło pozostało bez
zmian. Ujawniono fałszywe ostrzeżenie: basename fontu nie określa jego rodziny.
Naprawa raportuje `font embedding not verified`, gdy są załączniki fontów,
zamiast nieuzasadnionego `font not embedded`. To jawne ograniczenie diagnostyki,
nie pełna walidacja metadanych rodziny. Żaden font nie został dodany do repozytorium.

Rzeczywisty mały RF64: wejście 200 ms przechodzi normalizację, narrator i sidecar
mają RF64 oraz pełne dekodowalne 300 ms, po 28914 B. Test zmienia `-rf64 auto`
na `always` wyłącznie w runnerze testowym. Dowodzi obsługi RF64, nie automatycznego
przekroczenia 4 GiB. Niezależna kontrola font/RF64: 21 testów kontraktowych oraz
2 rzeczywiste PASS. Po integracji 48 testów mediów/TTS/publisher PASS.

### Cały krótki pipeline bez atrap

```powershell
uv run pytest tests/application/test_production_network.py -m network -n0 -o addopts='' -q -s --tb=short
```

**1 PASS w 4,54 s**, scenariusz z generowaniem wejścia i końcową walidacją 3,112 s.
Rzeczywiste `AppService`, discovery,
planner, scheduler i wszystkie backendy wykonały siedem zadań: sześci sekundowy
MKV → ekstrakcja → Google → Edge Zofia → miks → publikacja MKV i FULL_PL.
Google wykonał jeden request dla dwóch autorskich kwestii; retry nie wystąpiło.
Powstały dwa poprawne niepuste polskie napisy, MKV zawiera video, oryginalne audio,
lektora oraz polskie napisy. Pełny decode lektora ma szczyt powyżej −60 dB,
a SHA256 źródła się nie zmienił. Próg odróżnia sygnał od ciszy; nie ocenia odsłuchu.

[Produkt MKV](../proof/pipeline-polish.mkv) ma czarny obraz i dwie ścieżki audio;
w odtwarzaczu wybierz polski lektor. [Napisy](../proof/pipeline-polish.srt) są
dołączone osobno. MKV: 302493 B, SHA256
`e440daf0d2b075fb1262d8d5d8504d2f2f512a049cd01544a48ae00d59754a12`.
To własny syntetyczny materiał, nie przetworzony odcinek anime.

## Prawdziwe usługi i media

```powershell
uv run pytest tests/services/translation/test_translation_network.py -m network -k 'english_to_polish or preserves_line_count or deepl_translates' -n0 -o addopts='' -ra
uv run pytest tests/services/tts/test_tts_edge_network.py -m network -n0 -o addopts='' -ra
uv run pytest tests/services/composition/test_composition_real.py tests/services/audio/test_audio_service_integration.py -n0
```

Google: dwa testy; DeepL: jeden test — razem 3 PASS w 4,42 s. Bez zmiany
preferencji i bez drukowania kluczy. Próbę Edge wykonano raz na identycznym
teście w odizolowanym worktree, następnie test przeniesiono do root.
Edge: **1 PASS, 2,00 s**, jeden provider call, zero retry/resume, głos
`pl-PL-ZofiaNeural`, latencja żądania 911,55 ms. FFmpeg zwalidował pełnym dekodowaniem
[próbkę MP3](../proof/edge-polish.mp3): 3,552 s, 42624 B, 24 kHz mono, 96 kb/s.
SHA256: `6708e26a748aa010596114ef23ae698929b5b8a748c99aff517735bdf5cedbbc`.

Testy rzeczywistego FFmpeg obejmują krótki MKV/MP4, ogon narracji, apostrof,
transkodowanie i render/resume audio. Nie są pełnym przebiegiem dowolnego odcinka.
Live LLM nie wykonano: brak wybranego primary model alias. SAPI nie uruchamiano;
wymaga osobno zainstalowanych/licencjonowanych głosów i może otworzyć okno dostawcy.

Audyt konkretnych zależności projektu:

```powershell
uv export --frozen --all-groups --no-emit-project --format requirements.txt --output-file .pytest_cache/audit-requirements.txt
uvx pip-audit --requirement .pytest_cache/audit-requirements.txt --disable-pip --strict
```

87 pakietów dla lokalnego Windows: **No known vulnerabilities found**.
Lock zaktualizowano przez uv: aiohttp 3.14.3, cryptography 50.0.1.
CI eksportuje ten sam lock i audytuje warianty Ubuntu/Windows; zdalnego CI
jeszcze nie uruchomiono, ponieważ nie wykonano push.

## Wydajność bez nieudowodnionych obietnic

| Pomiar bez fizycznego TTY | Wynik po zmianach |
| --- | --- |
| Native encode, 5 prób, założona komórka 8×17 | mediana 2,0544 s; zakres 1,7065–2,2463 s |
| Rozmiar animacji | 46 klatek, 416041 znaków — bez zmiany |
| Home 120×40, 5×200 wywołań, tekst / native | mediany 0,3030 / 0,2332 ms |
| Konstruktor z DummyInput/Output, 5×20 | mediana 1,7671 ms; nie koduje GIF |

Nie wykazano przyspieszenia enkodera względem pojedynczej próby baseline 1,7069 s.
Historyczny benchmark Home nie utrwalił dokładnego wywołania; jego 0,683 ms nie
jest porównywalnym dowodem przyspieszenia. Logika Home nie zmieniła się.
Polling resize ograniczono z 5 do 100 ms, redraw do 30 fps. Przygotowanie obrazu
jest przed pętlą klawiatury, lecz nadal przed pierwszą interaktywną klatką —
zgodnie z odrzuceniem placeholdera. Pełny startup, CPU/RSS i latencja TTY: NOT RUN.

Reprodukcja mikrobenchmarku:

```powershell
@'
from statistics import median
from time import perf_counter
from timeit import repeat
from loguru import logger
from anishift.cli.interactive.mascot_native import load_native_mascot
from anishift.cli.interactive.app import MascotState, _home_content
logger.remove()
times = []
for _ in range(5):
    start = perf_counter()
    image = load_native_mascot(query_terminal=False)
    times.append(perf_counter() - start)
    assert image is not None
print('encode seconds:', times, 'median:', median(times))
print('frames/chars:', len(image.payloads), sum(map(len, image.payloads)))
for name, size in (('text', None), ('native', (22, 10))):
    samples = repeat(lambda: _home_content(120, 40, 0, MascotState.IDLE, native_size=size), number=200, repeat=5)
    print(name, 'median ms:', median(samples) * 5)
'@ | uv run python -
```

## Otwarte ograniczenia i przekazanie

Aktywne żądanie sieciowe nie zawsze daje natychmiastowe anulowanie; obowiązuje
timeout danego providera, a streaming sprawdza cancel przy deltach. Neutralna
ekstrakcja MP4 pokazuje aktywność, nie zmierzony procent. Automatyczne przygotowanie
binarek działa bez drugiego renderera; widoczność długiego downloadu wymaga jeszcze
oceny UX. Recovery po hard-kill, pełne metadane fontów, rzeczywisty próg 4 GiB,
świeża instalacja Windows oraz odsłuch całego odcinka pozostają otwarte.
Runnery nadzorują wskazany proces narzędzia; dowolne potomki niestandardowego
wrappera nie mają gwarantowanego cleanupu.

## Commity implementacji i instrukcji

| Commit | Temat |
| --- | --- |
| `e1dc71d` | test(repo): enforce comment-free test support modules |
| `a78eaa4` | refactor(repo): shorten application docstrings |
| `9c6d1a6` | fix(utils): preserve log privacy and time filtering |
| `7f3abed` | fix(config): validate persisted settings and model entries |
| `81cd25c` | fix(setup): prepare and atomically repair media tools |
| `173fdf9` | fix(pipeline): enforce complete results and bounded media execution |
| `dad1c92` | fix(cli): show accurate progress and actionable run outcomes |
| `4bfe3d0` | fix(deps): update vulnerable packages and audit locked dependencies |
| `1f6596e` | fix(composition): report font uncertainty and verify media boundaries |
| `a8efe94` | fix(extraction): close output pipes after delayed completion |
| `4240b0b` | fix(utils): redact path objects and sensitive mapping keys |
| `ce8394f` | test(pipeline): verify restart recovery and live product execution |
| `ba99f97` | docs(repo): align operational guidance with runtime |

Dokumenty audytu, plany, tablica i próbki są zapisane w kolejnym commicie dokumentacyjnym.

Gałąź: `work/reliability/01-hardening`. Lokalne commity są tematyczne; bez push,
PR i merge. Trzy nieśledzone pliki promptów użytkownika pozostają nietknięte.
Worktree wykonawców zachowano; nie są drugim źródłem aktualnego produktu.
Kontynuować z Planu 03, potem rozstrzygnąć szczegółowy kontrakt TXT→audiobook.
Watcher, drop i pobieranie odcinków nie zostały zaimplementowane.
