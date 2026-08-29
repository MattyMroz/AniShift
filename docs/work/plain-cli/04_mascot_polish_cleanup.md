# PLAN 04 — maskotka, finalny polish i domknięcie Interactive CLI

## 0. Status dokumentu

```text
STATUS: IMPLEMENTED — STATIC VERIFIED; RUNTIME HITL DEFERRED BY USER
MODE: EXECUTION OUTCOME / REPLAN
SPEC AUTHORITY: spec.md
PREDECESSOR: PLAN 03 — Manual
BASELINE BRANCH: work/interactive-cli/03-manual
BASELINE COMMIT: 979491aa9b40d0f55cdf21bff86107d3d1b295b4
VERIFIED PREDECESSOR HEAD: 979491aa9b40d0f55cdf21bff86107d3d1b295b4
TARGET BRANCH: work/interactive-cli/04-mascot-polish
FINAL COMMIT: feat(cli): finish interactive experience
```

To jest ostatni plan workstreamu Interactive CLI.

Warunki wejściowe wykorzystane przy wykonaniu:

```text
PLAN 03 VERIFIED / COMMITTED
Jawnie wybrany static-state fallback bez Sixel, ponieważ Chafa nie jest dostępna
MASCOT PASS dla finalnego położenia i rozmiaru
```

Dokładny finalny SHA PLANU 03 został potwierdzony przed implementacją.

### 0.1. Wybrany wariant wykonania

Plan został wykonany jako `STATIC_STATE_FALLBACK`:

- jedynym właścicielem renderowania pozostaje `TerminalRenderer`;
- maskotka używa zoptymalizowanego PNG 256×256 z prawdziwą przezroczystością i
  renderera półblokowego Pillow;
- stan maskotki wynika z zaakceptowanych eventów backendu;
- brak osobnego workera, pętli animacji i bezpośredniego zapisu do terminala;
- awaria assetu degraduje widok do ASCII, a zbyt mały terminal do pustego widoku;
- Chafa/Sixel nie zostały dodane, ponieważ Chafa nie jest dostępna w środowisku, a
  drugi renderer zwiększałby ryzyko regresji kursora i resize;
- nie uruchomiono aplikacji ani testów zgodnie z poleceniem użytkownika; końcowy HITL
  pozostaje po stronie użytkownika.

PLAN 04 nie dodaje kolejnego modułu produktu.

Jego zadaniem jest:

```text
realna maskotka
→ bezpieczne stany maskotki
→ opcjonalna animacja
→ finalna spójność wizualna
→ terminal fallbacks
→ cleanup
→ finalna weryfikacja całego Interactive CLI
```

Najważniejsza zasada:

> Nie wolno skomplikować całego Interactive CLI tylko po to, aby wymusić animowanego
> obrazka w terminalu.

Jeżeli stabilne Chafa/Sixel wymagałoby zbudowania mini-frameworka terminalowego,
maskotka degraduje się do prostszego wariantu, a produkt pozostaje poprawny.

---

## 1. Authority

Przed zmianą wykonawca czyta:

```text
spec.md
01-plain-cli.md
02_settings.md
03_manual.md
AGENTS.md
anishift/AGENTS.md
anishift/cli/AGENTS.md
anishift/application/AGENTS.md
anishift/utils/rich_console/AGENTS.md
tests/AGENTS.md
```

Następnie current code po PLANIE 03:

```text
anishift/cli/interactive/app.py
anishift/cli/interactive/home.py
anishift/cli/interactive/mascot.py
anishift/cli/interactive/prompts.py
anishift/cli/interactive/progress.py
anishift/cli/interactive/settings.py
anishift/cli/interactive/manual.py
anishift/cli/run.py
anishift/cli/main.py
anishift/utils/rich_console/**
pyproject.toml
README.md
```

Przeczytać również aktualne repo reference dla `pi-emote`, jeżeli nadal jest używana
jako inspiracja techniczna.

Nie kopiować TypeScriptu 1:1.

---

## 2. Obowiązkowy baseline refresh

### 2.1. Finalny SHA

Potrzebny:

```text
979491aa9b40d0f55cdf21bff86107d3d1b295b4
```

### 2.2. Git

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
```

Wymagane:

```text
clean
work/interactive-cli/03-manual
979491aa9b40d0f55cdf21bff86107d3d1b295b4
```

### 2.3. Audit końcowego Interactive CLI

Przed pisaniem maskotki wykonawca zapisuje sobie faktyczny current map:

```text
Home owner
Prompt owner
Progress owner
Auto executor
Manual executor
Settings owner
Error/result owner
```

### 2.4. Drift dozwolony

Dozwolone:

- prywatne helper names;
- jeden dodatkowy presentation helper;
- accepted visual tweaks z wcześniejszych HITL;
- inna nazwa reusable execute flow.

### 2.5. Drift wymagający replanu

STOP, jeśli:

- finalny UI nie używa jednego `TerminalRenderer` z `prompts.py`;
- Rich progress został zastąpiony innym modelem;
- Home nie ma czterech ustalonych akcji;
- Manual/Settings wymagają własnego globalnego store;
- powstał nowy renderer terminalowy o znaczącej złożoności;
- finalny app lifecycle nie ma miejsca na bezpieczny mascot cleanup.

---

## 3. Potwierdzony techniczny punkt odniesienia — Chafa / pi-emote

Referencyjny `pi-emote` pokazuje użyteczny wzorzec:

```text
Windows Terminal
→ wykrycie środowiska
→ Chafa
→ Sixel
→ cursor save/restore
→ fallback
```

W jego Windows path Chafa jest uruchamiane jako osobny proces i generuje Sixel.
Referencja usuwa terminalowe wrappery Chafa, ponieważ layout jest własnością
nadrzędnego UI.

Ważny wniosek dla AniShift:

```text
Chafa jest rendererem opcjonalnym
nie fundamentem interakcji
```

Referencyjny animator ma jawny state machine i czyści timery przy zmianie stanu.

AniShift bierze z tego **idee**:

- renderer fallback;
- jawne stany;
- cleanup;
- brak wpływu mascot error na produkt.

Nie bierze:

- całego systemu pluginów;
- TUI integration;
- config managera emotes;
- slash commandów;
- importera paczek emote;
- obsługi Kitty/iTerm/tmux w v1.

---

## 4. Current State / Gap

| Obszar | Stan po PLANIE 03 | Finalny stan | Akcja |
|---|---|---|---|
| Home mascot | placeholder | prawdziwy slime/fallback | zastąpić |
| Mascot states | brak lub placeholder | state mapping | dodać |
| Animation | brak | opcjonalna stabilna | gate |
| Windows Terminal | normalny CLI | PNG jako półbloki | zrealizowano bez drugiego renderera |
| Inne terminale | placeholder | ASCII/no-image fallback | zachować |
| Rich/Prompt Toolkit palette | częściowa | spójna | polish |
| 80×24 | wcześniejsze HITL | final regression | sprawdzić |
| Assets packaging | brak | wheel/install działa | zweryfikować |
| Stary dead UI | usunięty | nadal nie wraca | grep/cleanup |
| Docs | niepełne | current usage | zaktualizować |
| Cały product flow | trzy plany | cross-feature PASS | zweryfikować |

---

## 5. Jedno pytanie PLANU 04

> Czy finalny AniShift ma spójny, minimalistyczny Interactive CLI z rozpoznawalną
> maskotką, która może bezpiecznie reagować na realne etapy pracy w Windows Terminal,
> ale nigdy nie przejmuje ownershipu terminala ani nie pogarsza Auto, Settings,
> Manual, progressu, błędów i technicznych subkomend?

Po finalnym PASS:

```text
TAK
```

---

## 6. Finalny rezultat użytkownika

### 6.1. Home

Docelowy baseline:

```text
                 [ realny slime ]  ANISHIFT

                         ● Auto
                           Ręczny
                           Ustawienia
                           Wyjście

↑↓ wybór · Enter zatwierdź                           v0.x.x
```

Home nadal nie pokazuje:

- modelu;
- głosu;
- presetów;
- providerów;
- statusów API;
- statusu workspace ani konfiguracji;
- pipeline statusu.

### 6.2. Windows Terminal

Home pokazuje kolorowego slime'a przez ten sam renderer tekstowy co resztę interfejsu.
PNG jest dekodowany raz, skalowany do stałej geometrii i zamieniany na półbloki Rich.
Nie powstaje drugi właściciel kursora ani dodatkowy proces Chafa.

### 6.3. Fallback

Jeżeli którykolwiek warunek nie działa:

```text
ASCII mascot
```

albo ostatecznie:

```text
brak maskotki
```

bez błędu aplikacji.

### 6.4. Praca

W trakcie rzeczywistego przebiegu maskotka może reagować na:

```text
discover
extract
translate
tts
audio
compose
success
error
```

Nie zastępuje statusu tekstowego.

### 6.5. Menu

Settings i Manual zachowują dotychczasową czytelność.

Mascot nie może zasłaniać promptów.

---

## 7. Ważne rozróżnienie — stan vs animacja

### 7.1. State switching jest celem PLANU 04

Required:

```text
idle
discover
extract
translate
tts
audio
compose
success
error
```

Każdy stan ma stabilny fallback.

### 7.2. Multi-frame animation ma technical gate

Animacja wewnątrz stanu jest dozwolona tylko po udowodnieniu, że:

- nie psuje redraw jednego `TerminalRenderer`;
- nie psuje redraw ani progressu w jednym `TerminalRenderer`;
- nie generuje scrollback;
- nie zostawia ghost frames;
- nie mruga kursorem;
- nie wymaga bezpośredniego hookowania prompt_toolkit internals;
- cleanup jest deterministyczny.

Jeżeli gate FAIL:

```text
state-specific static image
```

jest poprawnym rezultatem workstreamu.

Użytkownik może później uruchomić osobny animation workstream, jeśli nadal będzie tego
chciał.

Nie wolno w PLANIE 04 napisać 1000 linii terminal hacks tylko po to, aby powiedzieć,
że slime „mruga”.

---

## 8. Asset Gate — zanim powstanie renderer

### GATE A — realny wygląd slime'a

To jest pierwsza rzecz PLANU 04 po baseline refresh.

Nie kodować całego state machine przed tym gate.

### 8.1. Source asset

Użytkownik dostarcza/akceptuje transparentny master slime.

Może to być obecny gładki slime.

Nie zakładamy z góry pixel-artu.

### 8.2. Dwa zakazane założenia

Nie zakładać:

```text
pixel-art na pewno będzie lepszy
smooth PNG na pewno będzie lepszy
```

To jest empiryczny wybór wizualny.

### 8.3. Runtime asset

Przygotować jeden tymczasowy zoptymalizowany idle asset o rozsądnej wielkości.

Nie commitować 4K mastera.

Preferowany runtime source raster:

```text
128–256 px kwadrat
transparent PNG
```

Nie skalować do 32 px na dysku tylko dlatego, że terminal jest mały; Chafa ma dostać
wystarczająco dobry source raster.

### 8.4. Spike

Bez rozbudowy architektury:

```text
PNG
→ chafa
→ sixel
→ Windows Terminal
```

Pokaż slime w miejscu Home.

### 8.5. Użytkownik ocenia

Wykonawca wypisuje:

```text
MASCOT VISUAL GATE
```

Użytkownik ocenia:

- czy slime jest czytelny;
- czy rozmiar pasuje;
- czy gładka wersja wygląda dobrze;
- czy warto robić pixel-art variant;
- czy położenie pod `ANISHIFT` działa.

### 8.6. PASS

Dopiero po:

```text
MASCOT PASS
```

asset może trafić do repo jako runtime asset.

### 8.7. FAIL

Jeżeli źle wygląda:

- nie przepisuj renderera;
- nie rób automatycznej „pixelizacji” bez akceptacji;
- poproś o/wykorzystaj nowy approved source;
- powtórz tylko gate.

---

## 9. Technical Design maskotki

### D04-01 — maskotka pozostaje presentation-only

Nie importuje:

```text
AppService
services
planner
scheduler
Settings saver
```

### D04-02 — jeden publiczny owner

`interactive/mascot.py` jest jedynym ownerem:

```text
renderer detection
current mascot state
asset selection
render failure fallback
cleanup
```

### D04-03 — jawny enum stanu

Preferowany contract:

```python
class MascotState(StrEnum):
    IDLE = "idle"
    DISCOVER = "discover"
    EXTRACT = "extract"
    TRANSLATE = "translate"
    TTS = "tts"
    AUDIO = "audio"
    COMPOSE = "compose"
    SUCCESS = "success"
    ERROR = "error"
```

Dokładna klasa może być enum/typing literal zgodnie z local style, ale vocabulary ma
pozostać jawne i ograniczone.

### D04-04 — asset naming przez foldery

Preferowane:

```text
assets/mascot/
├── idle/
├── discover/
├── extract/
├── translate/
├── tts/
├── audio/
├── compose/
├── success/
└── error/
```

W każdym katalogu:

```text
01.png
02.png
03.png
```

Jedna klatka = state static.

Więcej = state może animować.

Nie potrzebujemy JSON schema do listy klatek.

### D04-05 — deterministic ordering

Frame filenames sortowane lexical.

Nie losować w pierwszej wersji.

### D04-06 — renderer hierarchy

```text
Sixel/Chafa
→ ASCII
→ Null
```

Renderer zostaje wybrany raz na session albo degraduje w dół po błędzie.

Nie próbuj ponownie odpalać broken Chafa na każdej klatce.

### D04-07 — Windows Terminal detection

Minimalny warunek Sixel path:

```text
os.name == nt
WT_SESSION non-empty
chafa found in PATH
```

Nie implementować skanowania całego WinGet filesystemu.

Jeżeli user zainstalował Chafa poza PATH, dokumentacja mówi, aby dodał je do PATH.

Nie dodajemy nowego settingu tylko dla Chafa path w tej wersji.

### D04-08 — Chafa jako subprocess

Użyć standard library:

```text
subprocess
shutil.which
```

Nie dodawać Python dependency do renderowania Sixel.

### D04-09 — timeout

Każde kodowanie frame przez Chafa ma krótki timeout.

Renderer error:

```text
log sanitized technical message
→ disable sixel for session
→ fallback
```

### D04-10 — no animation in interactive prompts by default

Home/Settings/Manual, kiedy aktywny jest interaktywny widok:

```text
static frame only
```

Nie uruchamiać background frame loop nad aktywnym promptem.

To jest kluczowa redukcja ryzyka cursor corruption.

### D04-11 — execution animation jest osobnym sub-gate

Podczas Rich progress można włączyć multi-frame animation tylko jeżeli ma stabilny,
zarezerwowany region i nie ściga się z redraw jednego `TerminalRenderer`.

Jeżeli integracja z jedną klatką `TerminalRenderer` nie jest czysta:

```text
state change -> one static frame/state decoration
```

bez intra-state animation.

### D04-12 — one Prompt Toolkit owner

`interactive/prompts.py::TerminalRenderer` pozostaje jedynym ownerem Prompt Toolkit,
alternate screen, klawiszy i redraw. Maskotka nie może importować Prompt Toolkit ani
tworzyć drugiej aplikacji lub pętli renderowania.

### D04-13 — no second renderer or terminal writer

Maskotka zwraca dane prezentacyjne do istniejącej klatki. Nie tworzy własnego `Live`,
aplikacji Prompt Toolkit ani równoległego raw terminal writera.

### D04-14 — state derives from real work

Nie twórz sztucznego `MascotBusinessState` w backendzie.

State jest projekcją istniejących zdarzeń i lokalnych etapów prezentacji.

### D04-15 — state mapping task kinds

Na poziomie prezentacji mapping:

```text
EXTRACT_AUDIO        -> extract
EXTRACT_SUBTITLES    -> extract
NORMALIZE_SUBTITLES  -> extract
SPLIT_SUBTITLES      -> extract
TRANSLATE_SUBTITLES  -> translate
SYNTHESIZE_SPEECH    -> tts
TRANSCODE_AUDIO      -> audio
MIX_NARRATION        -> audio
COMPOSE_MKV          -> compose
COMPOSE_MP4          -> compose
PUBLISH_ARTIFACT     -> compose
```

Discovery przed planem:

```text
discover
```

Run complete:

```text
success / error
```

### D04-16 — concurrent task priority

Przy równoległych taskach nie przełączaj mascot co event losowo.

Presentation layer może utrzymywać mały derived set aktywnych `TaskKind` i wybierać
stan według stabilnego priorytetu:

```text
error
compose
audio
tts
translate
extract
discover
idle
```

To jest derived presentation state.

Nie jest source of truth workflow.

### D04-17 — cleanup

Przy:

```text
state change
return Home
Ctrl+C
exception
app exit
renderer failure
```

wszystkie mascot timers/workers muszą zostać zatrzymane.

### D04-18 — maksymalnie jeden animation worker

Jeżeli animation gate PASS, istnieje najwyżej jeden worker/timer loop maskotki.

ASCII i Null nie tworzą workerów.

---

## 10. Kontrakt Chafa/Sixel

### 10.1. Input

Transparent PNG bytes/path.

### 10.2. Output

Sixel bytes/control sequence.

### 10.3. Size

Home ma używać stałego, małego rozmiaru wyrażonego w terminal columns/rows.

Target zgodny ze SPEC:

```text
20 kolumn szerokości
14 wierszy wysokości
```

### 10.4. Chafa flags

Preferować jawne:

```text
--format=sixels
--size=<cols>x<rows>
--view-size=<cols>x<rows>
--align=top,left
--margin-bottom=0
--margin-right=0
--animate=off
--probe=off
--relative=on
-
```

Dokładne flags trzeba sprawdzić z aktualnie zainstalowaną wersją Chafa przed
zakodowaniem permanentnego contractu.

Jeżeli aktualne CLI różni się materialnie:

```text
technical gate -> adapt documented invocation
```

Nie dodawać kompatybilności z pięcioma starymi wersjami Chafa bez realnej potrzeby.

### 10.5. Cursor wrappers

Chafa może emitować własne cursor hide/show/newline wrappers.

Renderer ma zachować layout AniShift.

Nie wolno dopuścić, aby pojedynczy image render przesunął aktywne menu albo Rich
progress o dodatkowe linie.

### 10.6. ANSI/Sixel bytes

Nie przepuszczać Sixel przez normalne Rich escaping jako zwykły tekst. `mascot.py`
nie zapisuje bezpośrednio do terminala; przekazuje wynik do jedynego ownera outputu w
`prompts.py`. Jeżeli nie da się tego zrobić bez hookowania internals Prompt Toolkit,
GATE A kończy się świadomym fallbackiem do istniejących półbloków/ASCII.

Nie tworzyć ogólnej abstrakcji raw terminal dla całej aplikacji.

---

## 11. Asset contract

### 11.1. Nie commitować masterów

Nie commitować:

```text
4K source
wariantów marketingowych
plików roboczych
generator prompts
PSD/SVG work files, jeśli runtime ich nie potrzebuje
```

### 11.2. Commitować tylko runtime frames

Każdy frame:

- transparent PNG;
- cropped do realnej postaci;
- bez ogromnego pustego canvasu;
- rozsądny byte size;
- bez metadanych zawierających prywatne ścieżki.

### 11.3. Total budget

Miękki target:

```text
<= 1 MB wszystkich runtime mascot frames v1
```

Jeżeli approved animation wymaga więcej, raportuj zanim dodasz duży asset payload.

### 11.4. Brak automatycznej pixelizacji

Nie dodawać Pillow/algorytmu pixel-art tylko dla stylu.

Pixel-art variant musi być świadomym approved assetem.

---

## 12. Packaging Gate

Asset w repo nie wystarcza.

Musi być dostępny po instalacji pakietu.

### 12.1. Target path

Preferowany presentation-local path:

```text
anishift/cli/interactive/assets/mascot/**
```

### 12.2. Access

Używać package-resource-safe path, preferencyjnie `importlib.resources`.

Nie opierać się na current working directory.

### 12.3. Build verification

Po dodaniu pierwszego assetu:

```bash
uv build
```

Następnie sprawdzić wheel/archive, czy runtime PNG jest included.

### 12.4. Jeżeli uv_build nie bierze assetu

Dodać najmniejszą udokumentowaną include konfigurację w istniejącym build backendzie.

Nie zmieniać backendu build.

Nie kopiować assets przy runtime.

---

## 13. Finalna paleta

### 13.1. Zasada

```text
90–95% grayscale
1 primary accent
semantic error/warning/success tylko gdy informacyjne
pełnokolorowy slime jako wyjątek
```

### 13.2. Primary accent

Fiolet slime'a `#a855f7` jest głównym akcentem używanym przez:

- aktywny marker;
- neutralną informację;
- wybrany element.

Kontrolowany obrys wordmarku cyjan–fiolet–róż pozostaje częścią marki, nie paletą
stanów całego interfejsu.

Nie robić rainbow terminal.

### 13.3. Grayscale

Muted descriptions i footer są szare.

Normal text biały/jasnoszary.

### 13.4. Semantic colors

```text
success -> zielony
warning -> żółty
error -> czerwony
```

Tylko komunikaty stanów.

### 13.5. Jedno źródło style

Prompt Toolkit + Rich używają jednego małego presentation palette contractu.

Nie tworzyć theme engine.

---

## 14. Responsive rules

### 14.1. Reference

Must look acceptable at minimum:

```text
80x24
```

### 14.2. Wide

Przy szerokim terminalu content nie rozciąga się na całą szerokość.

### 14.3. Narrow

Gdy terminal jest za wąski:

- zachowaj funkcjonalność;
- zmniejsz odstępy;
- ASCII/no mascot fallback jest dopuszczalny;
- nie łam labels w przypadkowych miejscach;
- nie pokazuj drugiej kolumny wartości, jeśli brakuje miejsca.

### 14.4. Height

Długie listy używają istniejącego, lokalnego okna widocznych wierszy w obecnym
rendererze. Nie powstaje drugi viewport ani renderer.

---

## 15. Mascot state lifecycle

### 15.1. Startup

```text
idle
```

### 15.2. Auto / Manual discovery

Przed `service.discover()`:

```text
discover
```

Po discovery przed execute:

```text
idle
```

### 15.3. Execution

Task events aktualizują derived active task set.

### 15.4. Retry/fallback

Nie wprowadzamy osobnego mascot state `retry`.

Mascot pozostaje w stanie etapu, np. `translate`.

Rich pokazuje retry/fallback tekstowo.

### 15.5. Success

Po successful run:

```text
success
```

przez result surface.

### 15.6. Error

Expected/fatal run error:

```text
error
```

Maskotka nie zastępuje komunikatu.

### 15.7. Return Home

Po Enter:

```text
idle
```

---

## 16. Animation sub-gate

### GATE B — animacja podczas procesu

Po state-specific static rendering i packaging PASS.

### 16.1. Cel spike

Udowodnić jedną rzecz:

> Czy dwie/trzy klatki stanu mogą zmieniać się bez scrollback i bez korupcji Rich
> progress w Windows Terminal?

### 16.2. Scope spike

Tylko jeden stan, najlepiej:

```text
tts
```

Nie twórz assetów dla wszystkich state przed wynikiem gate.

### 16.3. PASS conditions

- no scrollback spam;
- no ghost images;
- no cursor drift;
- progress row nie mruga;
- Ctrl+C cleanup;
- worker kończy się;
- CPU usage rozsądne;
- brak bezpośredniego prompt_toolkit hook.

### 16.4. PASS

Dopiero wtedy generalizuj frame cycling dla pozostałych stanów.

### 16.5. FAIL

Zostaw:

```text
static frame per state
```

Usuń spike code, który nie jest potrzebny.

Nie traktuj FAIL animacji jako FAIL całego Interactive CLI.

---

## 17. Animation timing — jeśli Gate B PASS

### 17.1. FPS

Nie potrzebujemy 30/60 FPS.

Docelowo:

```text
4–8 FPS maximum
```

albo state-specific wolniejsze timing.

### 17.2. Idle

Home prompt jest statyczny w v1.

Ewentualny blink podczas aktywnego promptu nie jest wymagany.

### 17.3. Processing

Cykl klatek tylko podczas execution state.

### 17.4. Success/error

Static hold jest wystarczający.

### 17.5. Timer cleanup

Zmiana state zatrzymuje poprzedni cycle przed uruchomieniem nowego.

---

## 18. Integracja z Progress

### 18.1. Progress pozostaje source of visible work status

Mascot jest supplemental.

### 18.2. Task mapping

`progress.py` lub mały presentation helper ma dostęp do:

```text
plan task_id -> TaskKind
```

Jeżeli PLAN 01 już buduje taki mapping do labeli, rozszerz go.

Nie importować planner internals poza publicznym `TaskKind`/plan contract.

### 18.3. Active task set

Presentation-only:

```text
TASK_STARTED -> add task kind
TASK_FINISHED -> remove
```

Jeżeli run error przerwie event sequence, explicit cleanup przy result/error resetuje set.

### 18.4. Coalescing

Jeżeli kilka eventów zmienia state w tej samej krótkiej chwili, renderer nie musi
kodować nowego Sixel frame dla każdego eventu.

Może skipnąć redundant state.

### 18.5. No business side effects

Mascot failure nie może wpływać na event draining.

---

## 19. Fallback renderers

### 19.1. Sixel

Warunek Windows Terminal + Chafa.

### 19.2. ASCII

Mały static symbol/face.

Nie robić rozbudowanego ANSI pixel renderer.

### 19.3. Null

Jeżeli nawet ASCII nie mieści się albo renderer failuje:

```text
render nothing
```

Menu nadal działa.

### 19.4. Failure downgrade

Pierwszy runtime error Sixel:

```text
log
→ switch ASCII for rest of session
```

Nie spamuj logiem co frame.

---

## 20. Error policy maskotki

### 20.1. Missing Chafa

Nie jest błędem użytkownika.

Nie pokazuj czerwonego warningu na Home.

### 20.2. Missing asset

Development/package error.

Log warning once, fallback.

### 20.3. Chafa timeout

Log once, fallback.

### 20.4. Malformed output

Fallback.

### 20.5. App result

Mascot error nigdy nie zmienia exit code AniShift.

---

## 21. Docelowe drzewo

Preferowane po PLANIE 04:

```text
anishift/cli/interactive/
├── __init__.py
├── app.py
├── home.py
├── manual.py
├── mascot.py
├── progress.py
├── prompts.py
├── settings.py
├── settings_editors.py
└── assets/
    └── mascot/
        ├── idle/
        ├── discover/
        ├── extract/
        ├── translate/
        ├── tts/
        ├── audio/
        ├── compose/
        ├── success/
        └── error/
```

Nie tworzyć bez realnej potrzeby:

```text
mascot/
renderer/
terminal/
animation/
theme/
layout/
```

jako pięciu pakietów.

Jeżeli `mascot.py` staje się zbyt duży, jedyny dopuszczalny pierwszy split to:

```text
mascot.py
mascot_sixel.py
```

po wyjaśnieniu odpowiedzialności.

---

## 22. Expected Touch Set

### 22.1. Prawdopodobnie modyfikowane

```text
anishift/cli/interactive/mascot.py
anishift/cli/interactive/home.py
anishift/cli/interactive/progress.py
anishift/cli/interactive/prompts.py
anishift/cli/interactive/app.py
anishift/cli/AGENTS.md
README.md
```

### 22.2. Prawdopodobnie nowe

```text
anishift/cli/interactive/assets/mascot/**
tests/cli/test_interactive_mascot.py
```

### 22.3. Warunkowo

```text
pyproject.toml
uv.lock
```

Tylko jeśli package data require build configuration.

Nie dodawać nowej Python dependency do Chafa rendering.

### 22.4. Existing tests do rozszerzenia

```text
tests/cli/test_interactive_home.py
tests/cli/test_interactive_progress.py
tests/cli/test_interactive_app.py
tests/cli/test_interactive_settings.py
tests/cli/test_interactive_manual.py
tests/cli/test_main.py
tests/cli/test_run.py
```

### 22.5. Zakazane

```text
anishift/services/**
anishift/application/planner.py
anishift/application/scheduler*
anishift/application/*_handler.py
anishift/config/model_catalog.py
anishift/config/user_settings.py
anishift/tui/**
anishift/pipeline/**
external/**
```

PLAN 04 jest presentation/convergence.

Backend semantic change = replan.

---

## 23. Kontrakt `mascot.py`

### 23.1. Publiczne minimum

Logicznie potrzebujemy:

```text
MascotState
MascotController / equivalent session owner
renderer availability detection
show(state)
reset/idle
close/dispose
```

Nie wymuszamy konkretnej nazwy prywatnych klas.

### 23.2. Idempotent state

```text
show(TRANSLATE)
show(TRANSLATE)
```

nie koduje/renderuje tego samego static frame ponownie bez potrzeby.

### 23.3. Sixel renderer

Prywatny implementation detail.

### 23.4. ASCII renderer

Prywatny implementation detail.

### 23.5. Null renderer

Najprostszy no-op.

### 23.6. No backend dependency

Tests mają móc stworzyć controller bez AppService.

---

## 24. Tests — renderer selection

### M04-01

Windows + WT_SESSION + Chafa -> Sixel candidate.

### M04-02

Windows + no WT_SESSION -> ASCII.

### M04-03

WT_SESSION + no Chafa -> ASCII.

### M04-04

Chafa runtime failure -> downgrade once.

### M04-05

ASCII failure/asset absence -> Null.

### M04-06

Renderer detection nie wykonuje sieci.

### M04-07

Technical subcommands nie inicjalizują mascot.

---

## 25. Tests — state machine

### M04-10

Initial state idle.

### M04-11

Discover state jawny.

### M04-12

TaskKind mapping exact.

### M04-13

Duplicate state no redundant render.

### M04-14

Error ma najwyższy priority.

### M04-15

Concurrent active task priority deterministic.

### M04-16

Task finish usuwa active state.

### M04-17

Run success -> success.

### M04-18

Run failure -> error.

### M04-19

Return Home -> idle.

### M04-20

Dispose stops worker/timer.

---

## 26. Tests — Chafa process wrapper

Testować z fake subprocess runner / monkeypatch, nie wymagać Chafa w CI.

### C04-01

Command używa no-shell execution.

### C04-02

PNG bytes/path jest przekazany bez string shell interpolation.

### C04-03

Timeout -> fallback.

### C04-04

Nonzero exit -> fallback.

### C04-05

Output stripping nie zostawia newline, jeśli actual implementation go wymaga.

### C04-06

Nie loguje raw binary payload.

### C04-07

Nie loguje full user path, jeśli current logging policy sanitizuje paths.

Nie snapshotować całego Sixel payloadu.

---

## 27. Tests — Home/prompt regression

### H04-01

Home nadal ma cztery actions.

### H04-02

Marker po lewej.

### H04-03

Footer layout nadal czytelny.

### H04-04

Mascot fallback nie przesuwa menu.

### H04-05

Missing mascot renderer nie zmienia Home choices.

### H04-06

Settings nadal otwiera się poprawnie.

### H04-07

Manual nadal otwiera się poprawnie.

---

## 28. Tests — Progress regression

### P04-01

Translation nadal spinner.

### P04-02

TTS nadal real percentage.

### P04-03

Retry/fallback nadal aktualizują row.

### P04-04

Mascot state error nie zatrzymuje event drain.

### P04-05

Mascot renderer exception jest izolowany.

### P04-06

Success/error result renderer nadal działa po fallback.

---

## 29. Packaging tests

Nie trzeba permanentnie pisać testu parsującego wheel, jeśli build gate jest
wystarczający i repo nie ma takiego wzorca.

Przed HITL wykonać co najmniej raz:

```bash
uv build
```

Sprawdzić, że runtime asset istnieje w zbudowanym artefakcie.

Jeżeli repo ma już package smoke test, rozszerzyć go zamiast tworzyć nowy harness.

---

## 30. Final polish — Home

### 30.1. Tytuł

Szeroki Home zachowuje zaakceptowany sześciowierszowy wordmark o szerokości 57 kolumn.
Jednoliniowy `ANISHIFT` jest fallbackiem tylko wtedy, gdy pełny wordmark się nie mieści.

### 30.2. Mascot spacing

Maskotka pozostaje po lewej stronie wordmarku, a cały połączony blok jest wycentrowany.
Zachować stały mały odstęp maskotka–wordmark oraz 1–2 puste wiersze marka–menu.

Nie mnożyć pustego miejsca na 24-row terminalu.

### 30.3. Footer

Hint pod menu:

```text
↑↓ · Enter
```

Ostatni bezpieczny wiersz:

```text
katalog względny                                      vX.Y.Z
```

### 30.4. No dashboard

Final polish nie dodaje żadnego status badge.

---

## 31. Final polish — Settings

Sprawdzić:

- category labels;
- current value formatting;
- long model labels;
- password prompts;
- errors;
- return navigation;
- no right-side checkbox markers.

Nie dodawać nowych setting fields podczas polish.

---

## 32. Final polish — Manual

Sprawdzić:

- long episode titles;
- track labels;
- several groups;
- 80x24 scroll;
- blocker formatting;
- preview counts;
- back/cancel.

Nie rozszerzać manual functionality.

---

## 33. Final polish — Progress

Sprawdzić:

- stable rows;
- no scroll spam;
- elapsed where useful;
- no fake percent;
- retry/fallback wording;
- error legibility;
- success summary.

Nie tworzyć nowych progress bars tylko dla symetrii.

---

## 34. Cleanup code

### 34.1. Dependency audit

Po wszystkich planach:

```bash
uv tree
```

Potwierdzić:

```text
rich direct dependency
typer direct dependency
prompt-toolkit direct dependency
textual absent
```

`prompt_toolkit` jest bezpośrednią zależnością, ponieważ `TerminalRenderer` jest jego
jedynym bezpośrednim konsumentem. `questionary` pozostaje nieobecne.

### 34.2. Grep

Sprawdzić:

```text
anishift.tui
textual
slash command references
old shell history
old interactive settings docs
```

Nie usuwać historycznych dokumentów tylko dlatego, że zawierają słowo `Textual`.

Usuwać/aktualizować wyłącznie current docs/code, które fałszywie opisują aktywny produkt.

### 34.3. Dead imports

Ruff powinien wychwycić.

### 34.4. No cleanup safari

Nie refactorować backendu „przy okazji”.

---

## 35. Documentation

README powinien opisywać current happy path:

```text
uv run anishift
→ Auto / Ręczny / Ustawienia / Wyjście
```

Opcjonalna sekcja Windows mascot:

```powershell
winget install hpjansson.Chafa
```

oraz informacja:

```text
Windows Terminal required for Sixel mascot path
bez Chafa AniShift nadal działa
```

Nie dokumentować Chafa jako wymagania pipeline.

---

## 36. Kolejność implementacji

### Krok 1 — baseline refresh

Zweryfikuj finalny PLAN 03.

### Krok 2 — branch

```bash
git switch -c work/interactive-cli/04-mascot-polish
```

Nie commitować.

### Krok 3 — MASCOT visual spike

Jeden approved idle source.

Minimalny Chafa command.

Zero state machine.

### Krok 4 — MASCOT VISUAL GATE

STOP.

Użytkownik ocenia realny Windows Terminal.

### Krok 5 — runtime asset + packaging

Po MASCOT PASS:

- przygotuj runtime asset;
- dodaj package path;
- `uv build`;
- sprawdź asset w artefakcie.

### Krok 6 — renderer hierarchy

Sixel -> ASCII -> Null.

Tests.

### Krok 7 — MascotState/controller

Static state switching.

Tests.

### Krok 8 — Home integration

Placeholder -> real idle/fallback.

Home regression.

### Krok 9 — execution state integration

Derived TaskKind mapping.

Static state changes najpierw.

### Krok 10 — GATE B animation spike

Tylko jeden state, np. TTS.

### Krok 11A — animation PASS

Generalizuj minimalnie frame cycle.

### Krok 11B — animation FAIL

Usuń unstable animation path.

Zostaw state-specific static images.

### Krok 12 — visual polish

Home, Settings, Manual, Progress.

Bez nowych features.

### Krok 13 — responsive pass

80x24 + większy + narrow fallback.

### Krok 14 — cleanup

Dependencies/current docs/dead active references.

### Krok 15 — targeted tests

Mascot + Home + Progress + Settings + Manual + run/main.

### Krok 16 — static gates

Ruff, format, mypy.

### Krok 17 — build/package gate

`uv build` i package assets.

### Krok 18 — diff review

No backend semantic edits.

### Krok 19 — FINAL READY_FOR_HITL

Nie commitować.

### Krok 20 — pełny użytkowy HITL

Czekać na PASS.

### Krok 21 — PASS

Pełny pytest, finalny commit, push.

---

## 37. Budżet zmiany

### Production Python

Orientacyjnie:

```text
mascot.py delta/new       180–400
optional mascot_sixel.py    0–220
progress.py delta           30–120
home.py delta               20–80
app.py delta                10–60
prompts.py delta             0–60
```

### Runtime assets

```text
<= 1 MB target
```

### Tests

```text
mascot tests             250–500
regressions              150–450
```

### Alarm

Jeżeli mascot/polish wymaga:

```text
> 700 nowych linii production Python dla maskotki
> 3 nowych mascot modules
> direct prompt_toolkit integration
> custom full-screen render loop
> platform terminal abstraction > Windows/ASCII need
```

STOP.

To sygnał, że ozdoba zaczyna przejmować produkt.

---

## 38. Automated gates przed finalnym HITL

Targeted:

```bash
uv run pytest tests/cli/test_interactive_mascot.py
uv run pytest tests/cli/test_interactive_home.py
uv run pytest tests/cli/test_interactive_progress.py
uv run pytest tests/cli/test_interactive_settings.py
uv run pytest tests/cli/test_interactive_manual.py
uv run pytest tests/cli/test_interactive_app.py
uv run pytest tests/cli/test_run.py
uv run pytest tests/cli/test_main.py
```

Static:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
```

Build:

```bash
uv build
```

Diff:

```bash
git diff --check
git status --short
git diff --stat
git diff --name-only
```

Pełny pytest dopiero po finalnym manual PASS.

---

## 39. Kontrola diffu

Expected touch set:

```text
anishift/cli/interactive/mascot.py
anishift/cli/interactive/assets/mascot/**
anishift/cli/interactive/home.py
anishift/cli/interactive/progress.py
anishift/cli/interactive/app.py
anishift/cli/interactive/prompts.py              opcjonalnie
anishift/cli/AGENTS.md
README.md
pyproject.toml                                   warunkowo package data
uv.lock                                          tylko gdy pyproject/deps zmienione
tests/cli/test_interactive_mascot.py
tests/cli/test_interactive_home.py
tests/cli/test_interactive_progress.py
tests/cli/test_interactive_app.py                opcjonalnie
```

Settings/Manual test updates tylko dla regression expectation.

Każdy backend file = `UNEXPECTED FILE` i wymaga wyjaśnienia.

---

## 40. HITL A — realna maskotka

Ta checklista jest wykonywana już przy MASCOT VISUAL GATE.

### A-01

Uruchom w Windows Terminal.

Sprawdź:

```powershell
$env:WT_SESSION
```

### A-02

Upewnij się, że Chafa działa:

```powershell
chafa --version
```

### A-03

Uruchom spike/Home.

Oceń:

- czy slime jest ostry;
- czy transparentne tło wygląda poprawnie;
- czy proporcja nie jest za duża;
- czy tytuł + slime + menu tworzą spójną kompozycję;
- czy gładki styl jest dobry.

### A-04

Jeżeli wygląda źle, wskaż konkretnie:

```text
rozmiar
położenie
styl smooth/pixel
obrys
kontrast
```

Nie przechodź dalej bez `MASCOT PASS`.

---

## 41. HITL B — Home final

Po pełnej integracji:

1. uruchom `uv run anishift`;
2. nic nie naciskaj;
3. sprawdź Home w 80x24;
4. sprawdź większe okno;
5. zmniejsz terminal.

Oczekiwane:

- Home nadal minimalistyczny;
- realny slime nie przesuwa menu;
- footer czytelny;
- fallback działa przy małym terminalu;
- żadnego dashboardu.

---

## 42. HITL C — brak Chafa

Tymczasowo usuń Chafa z PATH / uruchom w terminalu bez WT_SESSION.

Oczekiwane:

- AniShift startuje;
- ASCII/no mascot fallback;
- zero czerwonego błędu;
- wszystkie opcje działają.

---

## 43. HITL D — Auto + states

Uruchom prawdziwy Auto.

Obserwuj:

```text
discover
extract
translate
tts
audio
compose
success
```

Nie każdy run musi użyć wszystkich state.

Oczekiwane:

- state odpowiada realnej pracy;
- Rich tekst nadal mówi, co się dzieje;
- translation nadal nie ma fake %;
- TTS ma real %;
- retry/fallback nie zmienia mascot w chaos.

---

## 44. HITL E — animation, jeśli Gate B PASS

Przez minimum 30 sekund działania:

- brak ghost frames;
- brak scrollback per frame;
- brak drift kursora;
- brak niszczenia progress rows;
- brak migania promptu;
- po zakończeniu worker znika.

Jeżeli któryś punkt FAIL:

```text
wyłącz intra-state animation
zachowaj static state images
```

Nie naprawiaj przez kolejny framework.

---

## 45. HITL F — Settings regression

Przejdź:

```text
Tłumaczenie
Lektor
Wynik
Połączenia
```

Oczekiwane:

- marker left-only;
- long labels czytelne;
- mascot nie przeszkadza promptom;
- zapis działa;
- no global Save.

---

## 46. HITL G — Manual regression

Na realnym multi-episode workspace:

- wybierz groups;
- dostosuj jeden;
- zbuduj preview;
- uruchom.

Oczekiwane:

- wizard czytelny;
- maskotka nie utrudnia choice list;
- execution states działają;
- Manual overrides nadal ephemeral.

---

## 47. HITL H — błąd

Wywołaj bezpieczny kontrolowany failure, np. brak wymaganego credential/test config.

Oczekiwane:

```text
error mascot state
+ prawdziwy czerwony komunikat Rich
```

Maskotka nie zastępuje reason.

Powrót Home -> idle.

---

## 48. HITL I — technical CLI

Sprawdź przynajmniej:

```bash
uv run anishift --help
uv run anishift run --help
uv run anishift run --preset default
```

Wymagane:

- noninteractive subcommands nie uruchamiają Interactive CLI;
- nie renderują maskotki;
- machine/technical behavior pozostaje stabilny.

---

## 49. HITL J — restart / repeated sessions

Uruchom i zamknij Interactive CLI kilka razy.

Sprawdź:

- brak osieroconych workerów;
- brak pozostawionego ukrytego kursora;
- następny terminal prompt działa normalnie;
- brak resztek Sixel w kolejnej sesji.

---

## 50. Finalny exploratory pass

Przez 10–15 minut używaj aplikacji normalnie:

```text
Home
Settings
Home
Manual
cancel
Auto
result
Home
exit
```

Celem nie jest znalezienie każdego hipotetycznego błędu.

Celem jest wykrycie:

- terminal drift;
- irytującego layoutu;
- niespójnych markerów;
- nadmiernego scrollback;
- zagubionej nawigacji;
- mascot interference.

---

## 51. Obowiązkowy raport agenta

Przed finalnym commit:

```text
STATUS: IMPLEMENTED_STATIC_VERIFIED

Plan:
PLAN 04 — Mascot + Polish + Cleanup

Branch:
work/interactive-cli/04-mascot-polish

Base:
979491aa9b40d0f55cdf21bff86107d3d1b295b4

Commit:
Created as the final step after this pre-commit report

Mascot visual gate:
PASS

Mascot renderer:
PILLOW_HALF_BLOCK / ASCII / NULL hierarchy

Animation gate:
PASS / STATIC_STATE_FALLBACK

Runtime assets:
- anishift/cli/interactive/assets/mascot/idle/01.png — 256×256 RGBA, 58 982 B

Asset package verification:
PASS — wheel and sdist contain the runtime PNG and omit the removed 4K asset

Mascot -> backend dependency:
Public TaskKind and TaskState contracts only; no AppService or planner internals

Changed production files:
- anishift/cli/interactive/app.py
- anishift/cli/interactive/home.py
- anishift/cli/interactive/manual.py
- anishift/cli/interactive/mascot.py
- anishift/cli/interactive/progress.py
- anishift/cli/interactive/settings.py

Changed assets:
- added assets/mascot/idle/01.png
- removed assets/slime_transparent_4k.png

Changed tests/docs:
- tests unchanged by user request
- README.md
- anishift/cli/AGENTS.md
- docs/work/plain-cli/04_mascot_polish_cleanup.md

Automated gates:
- mascot tests: NOT RUN — user requested no tests
- Home regression: NOT RUN — user requested no tests/application launch
- Progress regression: NOT RUN — user requested no tests/application launch
- Settings regression: NOT RUN — user requested no tests/application launch
- Manual regression: NOT RUN — user requested no tests/application launch
- technical CLI regression: NOT RUN — user requested no tests/application launch
- ruff: PASS
- format: PASS
- mypy: PASS
- uv build: PASS
- git diff --check: PASS

Unexpected files:
- anishift/application/scheduler_runtime.py — pre-existing user change, preserved
- docs/work/plain-cli/01-plain-cli.md — pre-existing user change, preserved

CO MASZ TERAZ SPRAWDZIĆ W FINALNEJ APLIKACJI:
- Home przy normalnym, zwężonym i ponownie rozszerzonym terminalu
- statyczne stany maskotki podczas discovery, tłumaczenia, TTS, audio i compose
- brak laga resize oraz natychmiastowe Ctrl+C
- Auto i Ręczny od wyboru do finalnego wyniku
- Settings i Manual z długimi nazwami oraz długimi listami
- wyrównane paski z nazwą do 20 znaków, procentem i ciągłym czasem pliku
- fallback przy bardzo małym terminalu

Jeżeli coś nie działa, podaj HITL i objaw.
```

---

## 52. PASS / FAIL

### 52.1. PASS

Dopiero po użytkowym:

```text
PASS
```

uruchomić:

```bash
uv run pytest
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv build
git diff --check
```

Następnie jeden finalny commit:

```text
feat(cli): finish interactive experience
```

Push:

```text
work/interactive-cli/04-mascot-polish
```

Raport SHA.

### 52.2. FAIL

Pozostań na branchu.

Nie zaczynaj następnego feature workstreamu.

Napraw minimalnie i powtórz tylko dotknięte gate’y + finalny HITL.

---

## 53. Zakazane skróty

Nie wolno:

- przywrócić Textual;
- dodać pełnoekranowego renderer frameworka;
- zaimplementować własnego odpowiednika Chafa;
- dodać Pillow wyłącznie dla pixel-art effect;
- commitować 4K masters;
- robić animacji w aktywnym prompt loop bez gate;
- importować prompt_toolkit do maskotki;
- tworzyć własnego Rich `Live`;
- tworzyć ciągłego render loop dla całego CLI;
- pisać do terminala z wielu niezabezpieczonych threadów;
- wykonywać Chafa w shell=True;
- wykonywać Chafa co event, gdy state się nie zmienił;
- retry Chafa co frame po failure;
- zmieniać exit code przez mascot failure;
- usuwać normalny text progress;
- zastępować błędy emoji/maskotką;
- dodawać theme engine;
- dodawać mascot settings screen;
- dodawać `/emote`;
- dodawać mascot importer;
- wspierać Kitty/iTerm/tmux w tym workstreamie;
- refactorować backend w ramach cleanup;
- ogłosić DONE przed finalnym HITL.

---

## 54. Ryzyka i reakcje

### RISK-04-A — Sixel psuje cursor/layout

Rozpoznanie:

- menu przesunięte;
- ghost frames;
- hidden cursor;
- progress corruption.

Reakcja:

```text
najpierw strip/wrapper minimal fix
jeśli nadal niestabilne -> ASCII/static fallback
```

Replan dopiero, jeśli user wymaga image animation jako blocker produktu.

### RISK-04-B — maskotka staje się nowym TUI

Rozpoznanie:

```text
setki linii terminal positioning/router/layout engine
```

Reakcja:

```text
cofnij do static state rendering
```

### RISK-04-C — asset wygląda źle

Rozpoznanie:

HITL.

Reakcja:

```text
zmień approved asset
nie przebudowuj backendu/renderera
```

### RISK-04-D — package nie zawiera PNG

Rozpoznanie:

wheel smoke/build inspection.

Reakcja:

minimalny build include rule.

### RISK-04-E — concurrent tasks powodują flicker state

Rozpoznanie:

maskotka skacze kilka razy na sekundę między translate/tts/audio.

Reakcja:

stabilny active-task priority + redundant-state suppression.

### RISK-04-F — polish rozszerza scope

Rozpoznanie:

nowe funkcje pojawiają się podczas „final polish”.

Reakcja:

odłóż je do przyszłego workstreamu.

---

## 55. Coverage

| Requirement | Właściciel | Dowód |
|---|---|---|
| R-400.. mascot | mascot.py/assets | Gate A + HITL B/C |
| fallback | mascot renderer | HITL C |
| states | progress/app -> mascot | HITL D/H |
| animation isolation | mascot controller | Gate B + HITL E |
| Home minimalistyczny | home.py | HITL B |
| grayscale + accent | prompts/Rich palette | HITL B/F/G |
| no fake progress | progress.py | HITL D |
| Settings preserved | existing plan02 | HITL F |
| Manual preserved | existing plan03 | HITL G |
| technical CLI | main/run lazy init | HITL I |
| cleanup | repo/docs/deps | static gates |
| packaging | build config/resources | uv build |

---

## 56. Final Definition of Done całego workstreamu

PLAN 04 oraz cały Interactive CLI workstream są ukończone tylko gdy:

```text
[ ] PLAN 01 VERIFIED / COMMITTED.
[ ] PLAN 02 VERIFIED / COMMITTED.
[ ] PLAN 03 VERIFIED / COMMITTED.
[ ] PLAN 04 baseline używa exact final SHA PLANU 03.
[ ] Home ma dokładnie Auto / Ręczny / Ustawienia / Wyjście.
[ ] Auto jest domyślnie zaznaczone.
[ ] Home nie ma dashboardu konfiguracji.
[ ] `TerminalRenderer` jest jedynym ownerem interakcji Prompt Toolkit.
[ ] Rich jest ownerem tekstu/progress/result/error rendering.
[ ] Textual nie istnieje jako dependency aktywnego produktu.
[ ] `prompt_toolkit` jest bezpośrednio używany wyłącznie w `interactive/prompts.py`.
[ ] Markery wyboru są po lewej.
[ ] Settings wystawia tylko product allowlist.
[ ] Settings persistuje pojedynczo bez globalnego Save.
[ ] Model Catalog pozostaje read-only.
[ ] Sekrety nie wyciekają.
[ ] Manual używa globalnych defaults.
[ ] Manual overrides są ephemeral.
[ ] Auto i Manual używają jednego execution/progress path.
[ ] Translation nie pokazuje fake percentage.
[ ] TTS pokazuje real progress.
[ ] Retry/fallback nie spamują scrollback.
[ ] Błędy są krótkie, bez tracebacka dla użytkownika.
[ ] Pełny traceback/log pozostaje developerski.
[ ] Realny slime przeszedł MASCOT VISUAL GATE albo świadomie używany jest fallback.
[ ] Mascot failure nie blokuje aplikacji.
[x] Chafa/Sixel świadomie pominięte w wariancie `STATIC_STATE_FALLBACK`.
[x] Runtime nie wymaga Chafa.
[ ] State mapping jest oparty na realnej pracy.
[ ] Animation albo przeszła Gate B, albo została cofnięta do static states.
[ ] Nie ma ghost frames/cursor drift po finalnym HITL.
[ ] Runtime assets są dostępne w zbudowanym pakiecie.
[ ] 80x24 jest używalne.
[ ] Długie listy Settings/Manual zachowują widoczny aktywny wiersz po resize.
[ ] Technical subcommands pozostają noninteractive.
[ ] README opisuje aktualny produkt.
[ ] Nie ma aktywnych fałszywych docs twierdzących, że głównym UI jest Textual/REPL.
[ ] Nie wykonano backend cleanup poza scope.
[ ] Targeted regressions przechodzą.
[ ] Ruff przechodzi.
[ ] Format przechodzi.
[ ] Mypy przechodzi.
[ ] uv build przechodzi.
[ ] Użytkownik wykonał finalny real HITL.
[ ] Użytkownik podał PASS.
[ ] Pełny pytest przeszedł po PASS.
[x] Jeden finalny commit PLANU 04 jest wykonywany po tym raporcie.
[ ] Branch został wypchnięty.
```

Dopiero wtedy można napisać:

```text
INTERACTIVE CLI WORKSTREAM
VERIFIED / COMMITTED / FROZEN
```

Nowe funkcje takie jak:

```text
pobieranie anime
biblioteka anime
okładki
nowe typy produktów
większe animacje maskotki
inne terminal protocols
```

są nowymi workstreamami, nie rozszerzeniem PLANU 04.
