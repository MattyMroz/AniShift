# ficzer: integracja z odtwarzaczem / lektor w MKV

> status: POMYSŁ (poza obecną przebudową)
> priorytet: średni — wygoda oglądania; wariant (b) to w dużej mierze polerka tego, co już jest
> cel: user ogląda anime z lektorem AniShift bez ręcznego przełączania ścieżek — odtwarzacz sam wie, co załadować.

## problem / motywacja

Pipeline kończy się plikiem (merge mkv / burn mp4) albo kompletem "napisy + audio obok MKV" (wariant players). Trzy pomysły na pójście dalej: (a) wtyczka do odtwarzacza, która sama podpina lektora, (b) lepsze osadzenie lektora jako ścieżki audio w MKV, (c) generowanie lektora "w locie" podczas oglądania. Poniżej każdy wariant z oceną realności.

## technologie i repozytoria

| technologia | po co | dojrzałość | plusy | minusy |
|---|---|---|---|---|
| mpv Lua scripting (wbudowane w mpv) | skrypt `.lua` w folderze `scripts/` mpv — hak na `file-loaded`, auto-`audio-add` pliku lektora leżącego obok MKV | bardzo wysoka — oficjalny mechanizm mpv, API stabilne od lat | zero zależności Pythona; instalacja = wrzucenie 1 pliku; działa z każdym mpv | osobny język (Lua) — ale skrypt ma ~30 linii; tylko mpv |
| mpv JSON IPC + `python-mpv` (pip) | sterowanie działającym mpv z Pythona (przez libmpv lub socket IPC) | wysoka — python-mpv aktywnie utrzymywany | pełna kontrola z AniShift (np. komenda `/play`) | wymaga libmpv/mpv w PATH; więcej ruchomych części niż skrypt Lua |
| `python-vlc` (pip) | bindingi libVLC — odtwarzanie/sterowanie VLC z Pythona | wysoka (oficjalne bindingi VideoLAN) | VLC jest wszędzie | VLC extensions do auto-ładowania audio pisze się w Lua VLC (inne, uboższe API niż mpv); doklejanie zewnętrznego audio w VLC to `--input-slave` — toporne |
| mkvtoolnix: `mkvmerge` (już w `external/bin/`) | wariant (b): lektor jako pełnoprawna ścieżka audio w MKV z flagami default/forced i nazwą | już w projekcie | zero nowych zależności — composition już to robi, brakuje tylko metadanych ścieżki | brak |
| mkvtoolnix: `mkvpropedit` | zmiana flag/nazw ścieżek w istniejącym MKV **bez remuxu** (sekundy zamiast minut) | wysoka, część mkvtoolnix | naprawa flag po fakcie bez przepisywania pliku | +1 binarka do manifestu (plan świadomie ją wyciął — wraca tylko, jeśli wariant b tego potrzebuje) |

## architektura modułu

Wariant (a) i (b) razem to nie jest osobna domena serwisowa — to mały folder integracji + drobne rozszerzenie `composition/`:

```
integrations/                      # NOWY folder top-level (obok utils/) — artefakty dla apek zewnętrznych
└── mpv/
    ├── README.md                  # jak zainstalować (skopiuj .lua do %APPDATA%/mpv/scripts/)
    └── anishift-lektor.lua        # hak file-loaded: jeśli obok pliku leży <nazwa>_lektor.eac3/.mp3
                                   #   -> audio-add + przełącz na tę ścieżkę + OSD "Lektor AniShift"

anishift/services/composition/
└── service.py                     # ZMIANA (wariant b): przy merge mkv ścieżka lektora dostaje
                                   #   name="Lektor PL (AniShift)", language=pol, flagę default;
                                   #   oryginalne audio zostaje, traci default

anishift/cli/
└── commands.py                    # OPCJONALNIE: /play — odpala mpv na wskazanym pliku
                                   #   (subprocess na mpv z --audio-file=..., bez python-mpv)
```

### opis plików

- **`integrations/mpv/anishift-lektor.lua`** — cały wariant (a): skrypt rejestruje handler `file-loaded`, składa oczekiwaną nazwę pliku lektora z nazwy odtwarzanego wideo (ta sama konwencja nazw co wariant players pipeline'u), jeśli plik istnieje → `mp.commandv("audio-add", ...)` i komunikat OSD. Konwencja nazw plików lektora to jedyny "kontrakt" między AniShift a skryptem — musi być udokumentowana w README obok.
- **`integrations/mpv/README.md`** — instalacja (1 plik do folderu skryptów mpv), wymagany wariant wyjścia players, konwencja nazw.
- **`composition/service.py` (zmiana)** — wariant (b): przy wyjściu merge mkv dopisać do wywołania `mkvmerge` opcje nazwy ścieżki, języka `pol` i flag default (lektor default=tak, oryginał default=nie). Efekt: każdy odtwarzacz (mpv, VLC, TV, Jellyfin) sam startuje z lektorem, a oryginał zostaje do przełączenia. To ~kilka opcji CLI więcej, nie nowy moduł.
- **`/play` (opcjonalnie)** — komenda odpalająca mpv subprocessem z `--audio-file=<lektor>` na pliku z workspace. Bez python-mpv — zwykły subprocess wystarcza, bo nie sterujemy odtwarzaniem po starcie.

## przepływ

- **wariant (a)**: user raz kopiuje `.lua` do mpv → od tej pory otwarcie dowolnego MKV, obok którego pipeline zostawił audio lektora, automatycznie gra z lektorem. AniShift nic nie robi w runtime.
- **wariant (b)**: pipeline (merge mkv) → plik ma ścieżkę "Lektor PL (AniShift)" z flagą default → każdy odtwarzacz startuje z lektorem bez żadnej wtyczki.
- **wariant (c) — ocena realności**: generowanie w locie wymaga, by tłumaczenie+TTS wyprzedzały głowicę odtwarzania. Sam TTS odcinka trwa minuty (elevenbytes: requesty + rundy retry), tłumaczenie kolejne minuty — bufor nie do utrzymania przy starcie zimnym; do tego koszt API płacony za coś, co user może przerwać po 3 minutach. Streaming-TTS (ElevenLabs websocket) skraca latencję pojedynczej linii, ale nie usuwa tłumaczenia ani miksu audio. **Werdykt: nierealne dziś, nie planować.** Praktyczny substytut: `/download` + auto-pipeline (watch mode) — odcinek jest gotowy zanim user siada do oglądania.

## ryzyka / uwagi

- konwencja nazw plików lektora staje się publicznym kontraktem (skrypt Lua na niej polega) — zmiana nazewnictwa w pipeline łamie wtyczkę; jedna stała, jedno miejsce.
- wariant (b) z flagą default: niektóre odtwarzacze ignorują default przy zapamiętanych preferencjach języka — to ograniczenie odtwarzaczy, nie nasze.
- VLC świadomie pominięty w (a): auto-ładowanie zewnętrznego audio w VLC jest znacząco toporniejsze (input-slave / uboższe Lua API), a mpv pokrywa grupę docelową; python-vlc odnotowany, nieużyty.
- (c) odrzucone — patrz przepływ; wracać tylko, gdyby cały pipeline zszedł poniżej ~realtime.

## rekomendacja

Zacząć od **(b)** — to niemal darmowe (kilka opcji mkvmerge w istniejącym composition) i daje największy efekt: każdy odtwarzacz gra lektora od razu. Potem **(a)** jako bonus dla wariantu players (jeden plik Lua, ~30 linii, zero zależności). **(c)** skreślić. Całość może wejść tuż po etapie 7/8 — dotyka jednego serwisu i nie wymaga nowej domeny.
