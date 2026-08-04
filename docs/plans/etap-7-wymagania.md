# Etap 7 — wymagania składania i pełnego E2E

> Status: draft 2 — wszystkie decyzje HITL rozstrzygnięte, gotowe do fazy planu.
> Data audytu: 2026-08-02.
> Branch: do założenia (`feature/composition`).
> Ten dokument opisuje **co ma działać**. Nie jest jeszcze planem implementacji ani listą commitów.

## 1. Legenda decyzji

- **USTALONE** — wynika z wcześniejszych decyzji projektu albo zostało już potwierdzone przez usera.
- **REKOMENDACJA** — proponowane rozstrzygnięcie po audycie; wymaga akceptacji usera.
- **HITL** — otwarta decyzja, której nie należy zakodować przed wspólnym rozstrzygnięciem.
- **ODRZUCONE** — pomysł z wcześniejszego planu, którego audyt nie potwierdził.

## 2. Cel etapu

**USTALONE**

Etap 7 zamienia rozsypane produkty pipeline'u w jeden zamierzony plik wynikowy:

```text
źródłowy MKV + wyprodukowane napisy PL + ścieżka lektora
  → wybór trybu wyjścia
  → pliki obok MKV  |  scalony MKV  |  wypalony MP4
  → walidacja wyniku
  → umieszczenie wyniku (obok źródła albo w workspace/output/)
  → sprzątanie wyłącznie po sukcesie
```

Główny efekt użytkowy:

- jeden Enter prowadzi od MKV w `workspace/` do gotowego pliku, bez ręcznego składania;
- napisy w wyniku wyglądają **dokładnie jak w źródłowym ASS** — style, pozycje, tagi i czcionki;
- tryb wypalania działa także **bez lektora i bez tłumaczenia** (np. polskie napisy z MKV → MP4);
- żaden błąd składania nie niszczy źródłowego MKV ani wyników wcześniejszych etapów;
- użytkownik dostaje przewidywalny rozmiar MP4 i czytelny raport, co powstało.

## 3. Źródła audytu

### 3.1. AniShift — stan faktyczny

- `anishift/pipeline/runner.py` — produkty per plik, `FileOutcome`, sprzątanie `tmp/`;
- `anishift/services/subtitles/service.py` — writery `.pl` / `.spoken.pl` / `.displayed.pl`;
- `anishift/services/audio/output.py` — `mixed_audio_path` i profile codeców;
- `anishift/services/extraction/` — `identify`, `TrackInfo`, `TrackSelection`, `already_polish`;
- `anishift/config/user_settings.py` — `output_variant`, `move_results_to_output` (dziś martwe);
- `docs/plans/plan-audit-fixes.md` — inwentaryzacja `/settings` z etapu 6.3.

### 3.2. Stary AniShift / mm_avh

- `mm_avh_working_space/modules/mkv_processing.py` — trzy warianty wyjścia;
- `mm_avh_working_space/start.py` — orkiestracja kroku końcowego.

### 3.3. Narzędzia zewnętrzne (zweryfikowane uruchomieniem)

- `external/bin/mkvtoolnix/mkvmerge.exe` — **v100.0**;
- `external/bin/ffmpeg/ffmpeg.exe` — **N-125628-ga5e6c0175a-20260715**, z `libx264`, `libx265`, `libass`, `libfreetype`, `libharfbuzz`, `fontconfig`, NVENC/AMF/QSV;
- `external/docs/mkvtoolnix/mkvmerge.html`, `external/docs/ffmpeg/ffmpeg-filters.html`, `ffmpeg-codecs.html`, `ffmpeg-utils.html`.

## 4. Najważniejsze wnioski audytu

### 4.1. Składanie jest osobną domeną bez wiedzy o napisach i TTS

**REKOMENDACJA**

`services/composition` dostaje gotowe ścieżki plików i deklaratywny opis wyniku. Nie parsuje ASS,
nie zna `SubtitleSplit`, `FileTranslation`, `SpeechBatch` ani `AudioRenderResult`. Jego wejściem
jest neutralny plan składania, a wyjściem jeden zweryfikowany plik.

Domena composition NIE zna:

- `pysubs2`, `SSAFile`, stylów i tagów ASS;
- `anishift.services.tts`, `anishift.services.translation`;
- decyzji, czy plik był polski, czy tłumaczony — dostaje gotową listę ścieżek do dołożenia.

Wybór **co** dołożyć należy do adaptera w `pipeline`, tak samo jak dziś adapter narracji
buduje `SpeechBatch`. Composition odpowiada wyłącznie za **jak** to złożyć.

### 4.2. Metadane ścieżek źródłowych są dziś tracone

**USTALONE — luka do zamknięcia**

Audyt potwierdził: po ekstrakcji `MediaInfo` i `TrackSelection` nie trafiają do `FileOutcome`.
Przetrwał wyłącznie `already_polish`. Etap 7 potrzebuje przynajmniej: języków wszystkich
ścieżek, ich nazw, flag `default`, identyfikatorów oraz informacji o ścieżce wideo.

**ROZSTRZYGNIĘTE — composition woła `identify(mkv)` tuż przed składaniem.**

Uzasadnienie, w kolejności wagi:

1. **Tryb `compose_only` nie ma etapu ekstrakcji.** Snapshot w `FileOutcome` byłby pusty dla
   przebiegu „weź MKV z polskimi napisami i wypal do MP4" — czyli dokładnie tego, o co prosi §6.4.
   Rozwiązanie oparte na snapshotcie wymagałoby i tak awaryjnego `identify`, więc byłyby dwie
   ścieżki kodu zamiast jednej.
2. **Snapshot bywa nieaktualny.** Między ekstrakcją a składaniem mija cały czas tłumaczenia i TTS
   (na realnym przebiegu: kilkadziesiąt minut). Plik na dysku mógł się zmienić.
3. **Koszt jest pomijalny.** `mkvmerge -J` na odcinku 1,4 GB kosztuje ułamek sekundy wobec minut
   wypalania i kilkudziesięciu minut TTS. Twardy limit w kodzie ekstrakcji to i tak 120 s.
4. **Mniejsza powierzchnia zmian.** `FileOutcome` nie rośnie o typy z domeny extraction, więc
   `pipeline/types.py` nie zaczyna zależeć od `MediaInfo` w runtime.

**Dowód do wykonania w implementacji** (nie deklaracja, tylko sprawdzalny warunek):

- pomiar czasu `identify` na najcięższym pliku z `workspace/` zapisany w logu etapu 7;
- test, w którym `compose_only` działa na MKV **bez** wcześniejszego przebiegu pipeline'u —
  przechodzi wyłącznie wtedy, gdy metadane pochodzą z `identify`;
- test, w którym plik źródłowy podmieniono między ekstrakcją a składaniem — wynik ma odpowiadać
  aktualnej zawartości pliku.

`identify` jest już zaimplementowane i przetestowane w `services/extraction/service.py`, więc
composition korzysta z istniejącej funkcji, nie pisze własnego parsera.

### 4.3. Czcionki: MKV niesie je sam, ffmpeg je czyta

**USTALONE — potwierdzone uruchomieniem narzędzi**

- `mkvmerge` **domyślnie kopiuje wszystkie załączniki** ze źródłowego MKV do wyniku. Merge nie
  wymaga żadnej pracy z czcionkami, dopóki tłumaczymy napisy już obecne w pliku — style zostają
  te same, więc te same czcionki wystarczają.
- `ffmpeg` z filtrem `ass=`/`subtitles=` **automatycznie ładuje czcionki załączone w MKV**, o ile
  poda mu się ścieżkę do MKV, a nie do gołego `.ass`. Zweryfikowane: log libass pokazuje próbę
  `Error opening memory font` (czyli sięgnięcie po attachment) przed fallbackiem na czcionki systemu.
- Gdy renderujemy z **zewnętrznego** `.ass` (nasz przetłumaczony plik), attachmenty nie są widoczne
  automatycznie — trzeba je wyekstrahować przez `mkvextract attachments` i wskazać `fontsdir=`.
- Fallback dla brakującej czcionki: libass sięga po DirectWrite/GDI (Windows), więc brak czcionki
  degraduje wygląd, ale nie wywala renderu.

### 4.4. Filtr `ass=` jest właściwy dla wierności 1:1

**REKOMENDACJA**

- `subtitles=` konwertuje dowolny format do ASS i renderuje przez libass — wprowadza warstwę
  reinterpretacji.
- `ass=` przyjmuje wyłącznie ASS/SSA i podaje je libass bez zmian — pełna wierność V4+ styles,
  karaoke, `\pos`, `\move`, `\clip`, rysunków.

Skoro produkty AniShift dla źródeł ASS są zawsze ASS, wypalanie ma używać `ass=`. Dla źródeł SRT
(kind `srt`) pozostaje `subtitles=` z domyślnym stylem libass.

### 4.5. Apostrof w ścieżce łamie filtr napisów

**USTALONE — potwierdzone empirycznie, trzy strategie escapowania zawiodły**

Filtr `ass=`/`subtitles=` na tej wersji ffmpeg **gubi apostrof** w nazwie pliku niezależnie od
sposobu escapowania (`\'`, `'\''`, wariant bez cudzysłowów). Plik `it's.ass` staje się `its.ass`
i render pada. Ponieważ w `workspace/` leżą realne anime z apostrofami w tytułach
(np. `Heroine Saint No, I'm an All-Works Maid...`), to nie jest przypadek teoretyczny.

Wymaganie: przed wypalaniem napisy trafiają do **kontrolowanej ścieżki roboczej** w `workspace/tmp/`
o nazwie bez apostrofów i innych znaków problematycznych; oryginalna nazwa pliku wynikowego
pozostaje nietknięta. Escapowanie pozostałych znaków (dwukropek dysku, backslashe, spacje,
nawiasy kwadratowe) jest wymagane i zweryfikowane jako działające.

### 4.6. Wypalanie zawsze przekodowuje wideo

**USTALONE**

Nie istnieje `-c:v copy` razem z filtrem napisów — libass komponuje na zdekodowanych klatkach.
Wypalenie to z definicji pełne przekodowanie wideo. Stąd:

- czas wypalania jest rzędu minut na odcinek, nie sekund;
- rozmiar wyniku zależy od CRF i presetu, nie od źródła;
- tryb „tylko przemuxowanie do MP4 bez wypalania" (gdy napisy nie są wymagane) **może** kopiować
  wideo bez strat.

### 4.7. MP4 nie uniesie ASS ani czcionek

**USTALONE — potwierdzone uruchomieniem**

- `-c:s copy` z ASS do MP4 kończy się błędem `codec not currently supported in container`.
- `-c:s mov_text` działa, ale kasuje całe stylowanie.
- MP4 nie ma mechanizmu załączników — czcionek nie da się przenieść.
- E-AC-3 **wchodzi do MP4 bez przekodowania** (zweryfikowane). AAC, MP3, Opus, FLAC też są legalne.

Wniosek: w MP4 stylowane napisy istnieją **wyłącznie jako wypalone w obrazie**.

### 4.8. Stary kod ma trzy klasy defektów, których nie wolno przenosić

**USTALONE — z audytu `mkv_processing.py`**

- **Kasowanie wejść mimo porażki.** Po `mkvmerge` kod nie sprawdza kodu wyjścia ani istnienia
  wyniku, po czym bezwarunkowo usuwa `.srt`, `.ass` i `.eac3`. Nieudany merge = utracona praca TTS.
- **Zmiana nazwy źródłowego MKV bez ochrony.** Wypalanie zmienia nazwę źródła na „bezpieczną",
  renderuje i przywraca nazwę — obie operacje poza `try/except`. Przerwanie między nimi zostawia
  źródło pod obcą nazwą i wypada z pipeline'u.
- **Cichy no-op.** Brak napisów i lektora buduje pustą komendę, która jest wywoływana pod
  `suppress(Exception)` — nic nie powstaje, a sprzątanie i tak kasuje pliki.

Dodatkowo: sanityzacja nazw `[^A-Za-z0-9.]+ → _` niszczy polskie znaki w nazwie wyniku,
a `path[2:]` (obcięcie litery dysku) łamie się na UNC i innych dyskach.

Żadne z tych zachowań nie może powtórzyć się w etapie 7.

## 5. Zakres etapu

### 5.1. W zakresie

**USTALONE**

- domena `services/composition` z trzema trybami wyjścia;
- macierz decyzji: co dołożyć do wyniku w zależności od źródła i wyprodukowanych artefaktów;
- ożywienie `output_variant` (z nowym domyślnym `players`) i usunięcie martwego
  `move_results_to_output`;
- nowa `/komenda` uruchamiająca samo składanie (bez tłumaczenia i TTS);
- nowe ustawienia: preferencje języka ścieżek, preset jakości wypalania;
- ręczny wybór ścieżki audio i napisów per plik;
- ustawienia jakości wypalania i kontrola rozmiaru wyniku;
- obsługa czcionek dla wierności napisów;
- postęp, anulowanie i typowane błędy jak w pozostałych domenach;
- wpięcie w `runner.py` jako krok 5 oraz raport końcowy;
- smoke E2E na realnym odcinku.

### 5.2. Poza zakresem

**REKOMENDACJA**

- **ODRZUCONE**: rejestr silników składania. Tryby to skończony zbiór trzech wariantów bez wyboru
  implementacji — zwykły `Enum` wystarcza (zgodnie z regułą repo: rejestr tylko dla `translation`,
  `tts`, `llm`).
- edycja napisów, restyling, zmiana rozdzielczości napisów pod inny PlayRes;
- wielościeżkowe wyjścia audio (kilka lektorów naraz);
- transkodowanie wideo poza trybem wypalania;
- upload, publikacja, integracja z odtwarzaczami.

## 6. Tryby wyjścia

### 6.1. Tryb `players` — pliki obok źródła

**USTALONE**

**Tryb domyślny aplikacji.** Jest najszybszy (zero muxowania i kodowania), niczego nie nadpisuje
i pozwala obejrzeć wynik od razu w odtwarzaczu — dopiero świadoma decyzja użytkownika przełącza
na `merge` albo `burn`, które kosztują czas i miejsce na dysku.

- niczego nie muxuje ani nie koduje;
- gwarantuje, że wszystkie produkty leżą **w jednym katalogu obok źródłowego MKV** i mają nazwy,
  które odtwarzacz automatycznie sparuje z filmem;
- naprawia znaną rozbieżność: napisy trafiają dziś do `workspace_root`, a sidecar audio obok
  źródła — w trybie `players` wszystko ma wylądować w tym samym miejscu;
- nie usuwa nic ze źródła;
- jest **domyślnym trybem awaryjnym**: gdy merge albo wypalenie zawiodą, produkty pozostają
  na dysku dokładnie jak w tym trybie.

### 6.2. Tryb `merge` — scalony MKV

**USTALONE**

- tworzy nowy MKV zawierający wszystko ze źródła plus dołożone ścieżki;
- zachowuje wszystkie oryginalne ścieżki wideo, audio, napisów, rozdziały, tagi i **załączniki**;
- dokłada ścieżkę lektora i wybrane ścieżki napisów zgodnie z macierzą z §7;
- ustawia poprawne metadane: język, nazwę ścieżki, flagi `default` i `forced`, kolejność;
- nigdy nie nadpisuje pliku wejściowego w miejscu — mkvmerge tego zabrania (zweryfikowane),
  więc zapis idzie do pliku tymczasowego i dopiero po walidacji trafia na miejsce docelowe.

### 6.3. Tryb `burn` — wypalony MP4

**USTALONE**

- renderuje MP4 z napisami wypalonymi w obrazie;
- audio: lektor jeśli istnieje, w przeciwnym razie oryginalna ścieżka;
- kopiuje audio bez przekodowania, gdy codec jest legalny w MP4 (E-AC-3, AAC, MP3, Opus, FLAC);
- jakość i rozmiar sterowane presetami z §9;
- **działa również bez lektora i bez tłumaczenia** (§6.4).

### 6.4. Wypalanie bez lektora i bez tłumaczenia

**USTALONE — wymaganie usera**

Użytkownik musi móc wziąć MKV, który **już ma polskie napisy**, i wypalić je do MP4 bez
uruchamiania tłumaczenia ani TTS. To pociąga:

- pipeline musi umieć pominąć etapy 4-6 na żądanie (tryb pracy, nie osobna aplikacja);
- składanie musi działać na napisach **wyekstrahowanych ze źródła**, nie tylko na naszych produktach;
- to samo dotyczy scalania: „weź ten MKV i tylko przełóż napisy/audio" jest legalnym przebiegiem.

**USTALONE — `/komenda`, nie ustawienie**

Rozważane były obie drogi; komenda wygrywa z konkretnych powodów:

- **to czynność, nie preferencja.** „Złóż mi ten plik" robi się raz dla konkretnego materiału.
  Ustawienie utrzymuje stan między sesjami, więc trzeba pamiętać, żeby je cofnąć — inaczej
  następnym razem Enter po cichu pomija tłumaczenie i TTS, a użytkownik dowiaduje się o tym
  po fakcie. To dokładnie ta klasa pułapek, których §11.2b zabrania;
- **zero ryzyka zapomnianego trybu.** Komenda działa raz i nie zostawia śladu w konfiguracji;
- **panel `/settings` i tak czeka refaktor**, a dokładanie tam pozycji zmieniającej cały przebieg
  zwiększa dług, zamiast go zmniejszać;
- **spójność z shellem**: rejestr `/komend` już istnieje i jest jedynym źródłem prawdy dla
  completera i `/help`, więc dodanie pozycji jest tanie.

Kontrakt komendy:

- uruchamia składanie dla plików z `workspace/` **bez** tłumaczenia i TTS;
- używa tego, co jest w pliku źródłowym i obok niego (nasze produkty z wcześniejszych przebiegów
  albo napisy wyekstrahowane ze źródła);
- honoruje `output_variant` z ustawień, bo to nadal decyzja „co chcę dostać";
- pomija plik z jawnym powodem, gdy nie ma z czego składać;
- **nie zmienia żadnego ustawienia** — po jej wykonaniu Enter działa jak wcześniej.

Zwykły Enter pozostaje **pełnym pipeline'em**, bez nowej gałęzi zachowania i bez dodatkowego
ustawienia do pomylenia.

### 6.5. Wybór ścieżek źródłowych

**USTALONE — wymaganie usera**

Automatyczny scoring wybiera dziś ścieżkę audio (preferuje japońską) i napisów. Użytkownik musi
móc ten wybór **nadpisać**: czasem lektor ma powstać z wersji angielskiej, nie japońskiej, a
napisy pochodzić z konkretnej ścieżki spośród kilkunastu w pliku.

- wybór dotyczy **ścieżki audio** (baza miksu i ewentualne źródło dla MP4) oraz **ścieżki napisów**
  (materiał do tłumaczenia i składania);
- domyślnie działa dotychczasowy scoring — brak decyzji użytkownika niczego nie zmienia;
- nadpisanie musi być możliwe **per plik**, bo w jednej paczce odcinki bywają różne;
- **REKOMENDACJA**: realizacja przez istniejący mechanizm interakcji pipeline'u
  (`PipelineInteraction`), analogicznie do ręcznego wyboru stylów napisów — a nie przez globalne
  ustawienie, które nie zna zawartości konkretnego pliku;
- w trybie auto pytanie nie pada; obowiązuje scoring.

**USTALONE — dwa mechanizmy, każdy dla swojego trybu**

- **tryb ręczny**: użytkownik wybiera ścieżki **przy każdym pliku z osobna**, tak jak dziś wybiera
  style napisów. Odcinki w jednej paczce bywają różne, więc jednorazowa odpowiedź nie wystarcza;
- **tryb auto**: żadnego pytania — obowiązują **priorytety języków z `/settings`**, które sterują
  scoringiem wyboru ścieżek.

Z tego wynika nowe ustawienie: **preferencje języka** dla audio i dla napisów (np. kolejność
`jpn, eng` dla audio). Dziś wagi są zaszyte w `tracks.py`; etap 7 wystawia je jako ustawienie,
zachowując obecne wartości jako domyślne.

## 7. Macierz składania — co trafia do wyniku

### 7.1. Osie decyzyjne

**USTALONE**

| Oś | Warianty |
|---|---|
| Tryb wyjścia | `players` · `merge` · `burn` |
| Źródło napisów | już polskie w MKV · obce (tłumaczone przez nas) · TXT · brak napisów |
| Lektor | jest · brak (pominięty, wyłączony albo nieudany) |
| Napisy do dołożenia | pełne PL · spoken PL · displayed PL · żadne |
| Oryginalne ścieżki | zachowane (zawsze w `merge`) |

### 7.2. Reguła braku duplikatu

**USTALONE — wymaganie usera**

- Gdy źródłowy MKV **ma już polską ścieżkę napisów** (`already_polish`), nie dokładamy jej kopii
  jako „pełne PL" — byłby to ten sam tekst dwa razy.
- Lektor jest dokładany **niezależnie** od tego, czy napisy były już polskie.
- Warianty `spoken` i `displayed` **nie są duplikatem** — to inne cięcie tego samego tekstu i mają
  wartość użytkową (lektor + tylko napisy poboczne na ekranie). Wolno je dołożyć nawet przy
  polskim źródle.
- Gdy dokładamy `spoken`/`displayed`, oryginalna polska ścieżka zostaje w pliku (jest częścią
  źródła), ale nie tworzymy z niej trzeciej kopii.

### 7.3. Tabela prawdy dla `merge`

**REKOMENDACJA — do zatwierdzenia w całości**

Legenda: `+` dokładamy, `–` nie dokładamy, `(src)` zostaje ze źródła.

**USTALONE**: dokładamy **pełne PL + displayed PL**. Wariant `spoken` nie trafia do kontenera —
osobno rzadko przydatny, a mnoży ścieżki w odtwarzaczu. Pozostaje produktem na dysku.

| # | Źródło napisów | Lektor | Pełne PL | Spoken PL | Displayed PL | Audio lektora |
|---|---|---|---|---|---|---|
| 1 | obce | jest | `+` | `–` | `+` | `+` |
| 2 | obce | brak | `+` | `–` | `+` | `–` |
| 3 | polskie | jest | `–` (src) | `–` | `+` | `+` |
| 4 | polskie | brak | `–` (src) | `–` | `–` | `–` (no-op, patrz §7.5) |
| 5 | TXT (brak wideo) | — | — | — | — | — (nie dotyczy) |
| 6 | brak napisów | brak | `–` | `–` | `–` | `–` (no-op) |
| 7 | brak napisów, jest audio | brak | `–` | `–` | `–` | `–` (no-op) |

Wiersz 4 i 6-7 to przypadki, w których scalanie nie ma czego dołożyć — patrz §7.5.

### 7.4. Tabela prawdy dla `burn`

**USTALONE**

Wypalić można **dokładnie jedną** ścieżkę napisów — obraz ma jedną warstwę. Wybór zależy od tego,
czy powstał lektor: z lektorem dialogi słychać, więc wypalamy tylko napisy poboczne; bez lektora
wypalamy komplet.

| # | Źródło | Lektor | Wypalane napisy | Audio w MP4 |
|---|---|---|---|---|
| 1 | obce | jest | **displayed PL** | lektor |
| 2 | obce | brak | pełne PL | oryginał |
| 3 | polskie | jest | **displayed PL** (nasz split źródła) | lektor |
| 4 | polskie | brak | źródłowe polskie | oryginał |
| 5 | brak napisów | jest | — (samo przemuxowanie + lektor) | lektor |
| 6 | brak napisów | brak | — | — (no-op) |

Wiersz 3 wymaga uwagi: przy polskim źródle i lektorze potrzebujemy `displayed` jako osobnego
pliku — pipeline produkuje go także dla źródeł polskich (`write_displayed`), więc jest dostępny.
Gdy `displayed` nie powstał (brak eventów pobocznych), nie wypalamy nic — sam lektor wystarcza.

### 7.5. Przypadki „nie ma czego złożyć"

**REKOMENDACJA**

Gdy dla danego pliku nie ma ani lektora, ani żadnych napisów do dołożenia:

- tryb `merge` nie tworzy kopii MKV bez zmian — zwraca status `skipped_nothing_to_add`
  z czytelnym powodem;
- tryb `burn` również nie renderuje (przekodowanie bez zysku to strata czasu i jakości), chyba że
  użytkownik jawnie chce konwersji kontenera;
- tryb `players` nadal porządkuje to, co powstało;
- raport końcowy wprost mówi, dlaczego plik został pominięty.

To bezpośrednia naprawa cichego no-opu ze starego kodu.

## 8. Metadane ścieżek w scalonym MKV

### 8.1. Ścieżka lektora

**USTALONE**

- język: `pol`;
- nazwa ścieżki: `Lektor PL` (stary kod używał tej nazwy — zachowujemy rozpoznawalność);
- `default`: `no` — lektor jest **ścieżką dodatkową**, dokładaną na końcu listy. Oryginalne
  ścieżki zachowują swoje flagi, w szczególności japoński oryginał pozostaje domyślny;
- `forced`: `no`;
- pozycja: **na końcu** ścieżek audio, po wszystkich oryginalnych.

### 8.2. Ścieżki napisów

**USTALONE**

| Wariant | Język | Nazwa ścieżki | Default | Forced |
|---|---|---|---|---|
| pełne PL | `pol` | `Napisy PL` | `no` | `no` |
| displayed PL | `pol` | `Napisy poboczne PL` | `no` | `no` |

Wszystkie dokładane ścieżki są **dodatkowe**: `default` i `forced` pozostają `no`, a ścieżki lądują
na końcu listy w kolejności `pełne PL`, `displayed PL`. Oryginalne flagi źródła nie są modyfikowane
— plik po scaleniu zachowuje się przy otwarciu tak jak przed nim, dopóki widz nie wybierze
polskiej ścieżki.

### 8.3. Załączniki i rozdziały

**USTALONE**

- wszystkie załączniki źródła (czcionki) przechodzą do wyniku — domyślne zachowanie mkvmerge;
- rozdziały i tagi źródła przechodzą do wyniku;
- gdy nasz `.ass` używa czcionki, której nie ma w załącznikach źródła, obowiązuje §10.

## 9. Jakość i rozmiar wypalonego MP4

### 9.1. Presety jakości

**USTALONE — wybór usera**

Zamiast surowego CRF użytkownik wybiera nazwany preset. Mapowanie na parametry kodera jest
szczegółem implementacji, nie decyzją użytkownika.

**REKOMENDACJA** dla mapowania startowego (x264, `-preset medium`):

| Preset | CRF | Zastosowanie |
|---|---|---|
| `high` | 18 | wizualnie bezstratny, wynik może przekroczyć źródło |
| `balanced` | 21 | domyślny — bardzo dobry obraz, rozmiar zwykle poniżej źródła |
| `compact` | 24 | wyraźnie mniejszy plik, akceptowalna jakość |

- koder domyślny: `libx264` (najszersza zgodność odtwarzaczy);
- `-pix_fmt yuv420p` wymuszony dla zgodności;
- `-movflags +faststart` zawsze;
- audio kopiowane bez przekodowania, gdy codec legalny w MP4.

### 9.2. Miękki budżet rozmiaru

**USTALONE — wybór usera**

- po renderze porównujemy rozmiar wyniku z rozmiarem źródła;
- przekroczenie progu (**REKOMENDACJA**: 110% rozmiaru źródła) trafia jako **ostrzeżenie**
  do raportu, nie jako błąd;
- ostrzeżenie sugeruje preset o stopień niżej;
- plik nie jest kasowany ani renderowany ponownie automatycznie.

### 9.3. Akceleracja sprzętowa

**REKOMENDACJA — poza zakresem etapu 7**

Bundlowany ffmpeg ma NVENC, AMF i QSV, ale jakość przy porównywalnym rozmiarze jest gorsza niż
x264, sterowanie jakością działa inaczej (`-cq` zamiast `-crf`), a poprawność zależy od sterowników
użytkownika. Do rozważenia po etapie 8, gdy będzie realna potrzeba skrócenia czasu.

## 10. Czcionki i wierność napisów

### 10.1. Wymaganie nadrzędne

**USTALONE — wymaganie usera**

Napisy w wyniku mają wyglądać **1:1 jak w źródłowym ASS**: te same style, czcionki, rozmiary,
pozycje, obramowania, cienie, animacje i rysunki.

### 10.2. Merge

**USTALONE**

Wystarczy domyślne kopiowanie załączników przez mkvmerge — nasz przetłumaczony ASS zachowuje
sekcję `[V4+ Styles]` źródła (potwierdzone w kodzie writerów), więc odwołuje się do tych samych
czcionek, które już są w kontenerze.

### 10.3. Wypalanie

**REKOMENDACJA**

Kolejność pozyskiwania czcionek przy renderze:

1. jeśli wypalamy **napisy źródłowe** — podajemy ffmpeg ścieżkę do **MKV**, a nie do `.ass`;
   libass sam sięgnie po załączniki (zweryfikowane);
2. jeśli wypalamy **nasz przetłumaczony ASS** — wyciągamy załączniki źródła przez
   `mkvextract attachments` do katalogu roboczego i podajemy `fontsdir=`;
3. brakująca czcionka → fallback systemowy libass (DirectWrite) + **ostrzeżenie w raporcie**
   z nazwą czcionki.

**USTALONE — w etapie 7 wykrywamy i ostrzegamy, nie szukamy**

Powód: brakująca czcionka **nie psuje renderu** — libass podstawia czcionkę systemową, więc napisy
są czytelne, tylko wyglądają inaczej niż zamierzył autor. To degradacja wyglądu, nie awaria.

Co robimy w etapie 7:

- czytamy nazwy czcionek z sekcji `[V4+ Styles]` i z tagów `\fn` w naszym ASS;
- porównujemy z listą załączników źródłowego MKV;
- brakująca czcionka → **ostrzeżenie w raporcie z nazwą fontu**, render idzie dalej;
- użytkownik wie, że wynik może wyglądać inaczej, i może zainstalować czcionkę albo odpuścić.

Czego **nie** robimy: wyszukiwania plików czcionek w systemie, dopasowywania wariantów
bold/italic, dołączania znalezionych fontów do MKV. To osobny moduł do rozważenia po etapie 7,
jeśli ostrzeżenia okażą się częste na realnym materiale.

## 11. Zachowanie operacyjne

### 11.1. Nienaruszalność źródła

**USTALONE**

- źródłowy MKV nie jest **nigdy** zmieniany, przenoszony ani przemianowywany;
- zapis wyniku idzie do pliku tymczasowego obok miejsca docelowego i dopiero po walidacji
  zastępuje cel atomowo;
- przerwanie w dowolnym momencie zostawia źródło i produkty wcześniejszych etapów nietknięte.

### 11.2. Sprzątanie wyłącznie po sukcesie

**USTALONE**

- po zweryfikowanym sukcesie kasowany jest **katalog roboczy `workspace/tmp/<scope>/` tego pliku**
  — klipy TTS, narrator WAV, PCM-y, wyekstrahowane ścieżki i manifesty resume;
- kasowanie jest **per plik** i **tylko** po walidacji wyniku;
- nieudane składanie **nie kasuje niczego** — cały stan resume zostaje, żeby ponowny przebieg
  nie płacił drugi raz za TTS;
- produkty użytkowe (scalony MKV, wypalony MP4, pliki dla odtwarzaczy) nigdy nie są kasowane;
- `tmp/` jest **stanem przejściowym**, nie archiwum — po udanym złożeniu nie ma prawa nic po sobie
  zostawiać. Kto chce pracować na plikach pośrednich, używa trybu `players`, który po to istnieje.

### 11.2b. Zasada braku niespodzianek

**USTALONE — wymaganie usera**

Etap 7 dotyka komponentów, które łatwo „po cichu nic nie robią". Każdy taki przypadek musi być
widoczny **zanim** użytkownik zacznie czekać, i policzalny **po** zakończeniu.

- **żadnego cichego pominięcia**: plik pominięty przez composition zawsze ma w raporcie powód
  wyrażony po ludzku („brak lektora i napisów do dołożenia", „napisy już polskie, nic nowego");
- **zapowiedź kosztu przed startem**: przed wypalaniem raport podaje liczbę plików do
  przekodowania i szacowany czas — wypalanie 27 odcinków to godziny, nie minuty (§4.6), więc
  użytkownik ma prawo wiedzieć o tym przed naciśnięciem Enter, nie po godzinie;
- **postęp z sensowną jednostką**: pasek wypalania pokazuje procent i pozostały czas liczony z
  `out_time_us` wobec długości filmu, a nie sam spinner;
- **przerwanie jest bezpieczne i wznawialne**: Ctrl+C w trakcie wypalania kasuje plik częściowy,
  zostawia wszystko inne i wraca do promptu — bez zostawiania śmieci i bez psucia źródła;
- **każdy pominięty krok jest policzony**: raport końcowy podaje liczbę plików złożonych,
  pominiętych i nieudanych, tak jak dziś podaje wyniki TTS.

### 11.2c. Wykrywanie pułapek wejścia

**USTALONE — wymaganie usera**

Znane cechy dzisiejszego pipeline'u, które mogą po cichu wykluczyć plik z przetwarzania,
mają być naprawione albo zgłoszone:

- filtr `discover_inputs` pomija **każdy** plik zawierający `.displayed` w nazwie — źródło nazwane
  `Show.displayed.S01E01.mkv` znika bez śladu. Poprawka: dopasowanie ma dotyczyć wyłącznie
  **naszych produktów** (infiks przed `.pl.<kind>`), nie dowolnego wystąpienia w nazwie;
- rozjazd miejsca zapisu: napisy trafiają do korzenia `workspace/`, a sidecar audio obok źródła —
  identyczne tylko dla plików leżących płasko w `workspace/`. Tryb `players` (§6.1) ujednolica to
  do katalogu źródła;
- brak produktu, o który użytkownik prosił (np. wybrał `burn`, a napisy się nie wygenerowały),
  kończy się jawnym wpisem w raporcie, nigdy pustym sukcesem.

### 11.3. Walidacja wyniku

**USTALONE**

Wynik jest uznany za poprawny dopiero, gdy:

- proces zakończył się kodem 0 (mkvmerge: 1 = ostrzeżenia, traktowane jako sukces z ostrzeżeniem);
- plik istnieje i ma niezerowy rozmiar;
- `ffprobe`/`mkvmerge -J` potwierdza obecność oczekiwanych ścieżek;
- czas trwania wyniku mieści się w tolerancji względem źródła.

### 11.4. Postęp, anulowanie, błędy

**USTALONE**

- postęp merge z `mkvmerge --gui-mode` (`#GUI#progress N%`);
- postęp wypalania z `ffmpeg -progress pipe:1 -nostats` (`out_time_us` wobec czasu źródła);
- anulowanie kooperatywne przez wspólny `threading.Event`, jak w audio;
- hierarchia błędów `CompositionError` → warianty; brak `except Exception`;
- kod wyjścia i stderr **zawsze** sprawdzane (naprawa defektu ze starego kodu);
- logowanie strukturalne granic operacji, bez pełnych komend, ścieżek absolutnych i stderr.

### 11.5. Umieszczenie wyniku

**USTALONE — miejsce zależy od trybu, nie od przełącznika**

| Tryb | Miejsce wyniku |
|---|---|
| `merge` | `workspace/output/{stem}.pl.mkv` |
| `burn` | `workspace/output/{stem}.pl.mp4` |
| `players` | **obok źródłowego MKV**, czyli w `workspace/` przy pliku wejściowym |

Uzasadnienie: scalony MKV i wypalony MP4 to samodzielne produkty końcowe — trafiają do
`output/`, żeby nie mieszać się z materiałem wejściowym. Tryb `players` z definicji ma produkować
pliki towarzyszące filmowi, więc muszą leżeć **przy nim**, inaczej odtwarzacz ich nie sparuje.

To rozstrzyga rozbieżność z §6.1: w trybie `players` wszystkie produkty (napisy i sidecar audio)
mają wylądować w katalogu źródłowego MKV.

**Skutek dla `move_results_to_output`**: to pole istnieje dziś w `config/settings.json` i w panelu
`/settings`, ale **nic go nie czyta** — przełącznik obiecuje „przenieś wyniki do output/", a
pipeline zawsze zapisuje obok MKV. Po powyższej tabeli miejsce wynika z trybu, więc przełącznik
byłby drugim, sprzecznym źródłem prawdy.

**USTALONE**: pole znika z modelu i z panelu w etapie 7. Nie tracimy funkcji — `merge` i `burn`
i tak trafiają do `output/`, a `players` z definicji obok filmu.

**Kolizja nazw — USTALONE**: istniejący plik w miejscu docelowym jest **nadpisywany**. Powtórny
przebieg tego samego odcinka daje jeden aktualny wynik zamiast rosnącej kolekcji wariantów.
Nadpisanie jest atomowe (§11.1), więc przerwany zapis nie niszczy poprzedniego pliku.

### 11.6. Nazewnictwo wyniku

**REKOMENDACJA**

- `merge`: `{stem}.pl.mkv` — nie nadpisuje źródła, od razu widać, że to wersja z lektorem;
- `burn`: `{stem}.pl.mp4`;
- polskie znaki i spacje w nazwie **zachowane** (naprawa sanityzacji ze starego kodu);
- problematyczne znaki dotyczą wyłącznie ścieżek roboczych dla ffmpeg (§4.5), nie nazwy wyniku.

## 12. Decyzje

Brak otwartych punktów — wszystkie rozstrzygnięte 2026-08-02.

### Rozstrzygnięte 2026-08-02

- warianty napisów w merge → **pełne PL + displayed PL**, bez `spoken` (§7.3);
- co wypalać przy lektorze → **displayed**, bez lektora → pełne (§7.4);
- flagi ścieżek → wszystko dodatkowe, `default`/`forced` = `no`, dokładane na końcu (§8.1, §8.2);
- miejsce wyniku → `merge`/`burn` do `output/`, `players` obok źródła (§11.5);
- kolizja nazw → nadpisanie, atomowe (§11.5);
- sprzątanie → kasujemy `tmp/<scope>/` po sukcesie, nic po porażce (§11.2);
- jakość MP4 → presety + miękki budżet rozmiaru (§9);
- czcionki → attachmenty ze źródła, fallback systemowy + ostrzeżenie z nazwą fontu (§10.3);
- metadane ścieżek → `identify` tuż przed składaniem, z dowodem pomiarowym i testami (§4.2);
- składanie bez tłumaczenia i TTS → **`/komenda`**, nie ustawienie; Enter zostaje pełnym
  pipeline'em (§6.4);
- wybór ścieżek → ręczny tryb pyta przy każdym pliku, auto używa preferencji języka z `/settings` (§6.5);
- domyślny tryb wyjścia → **`players`** zamiast dzisiejszego `merge` (§6.1);
- `move_results_to_output` → usunięte z modelu i panelu jako martwe i sprzeczne z §11.5.

## 13. Kontrakt techniczny narzędzi

Wszystko poniżej zweryfikowano uruchomieniem bundlowanych binarek (mkvmerge v100.0,
ffmpeg N-125628), nie samą lekturą dokumentacji.

### 13.1. Składnia scalania

- opcje per ścieżka poprzedzają plik, którego dotyczą, i odnoszą się do jego ścieżki `0`;
- `--language 0:pol`, `--track-name 0:"Lektor PL"`, `--default-track-flag 0:no`,
  `--forced-display-flag 0:no`;
- **uwaga wersyjna**: w v100 obowiązują `--default-track-flag` i `--forced-display-flag`;
  stare `--default-track` / `--forced-track` z tutoriali i z kodu mm_avh **nie istnieją**;
- `--language` przyjmuje BCP 47 (`pol`, `pl-PL`), ISO 639-2 jest normalizowane;
- `--track-order FileID:TrackID,...` steruje kolejnością; `FileID` to pozycja pliku w komendzie;
- kody wyjścia: `0` sukces, `1` sukces z ostrzeżeniami, `2` błąd;
- `--gui-mode` daje `#GUI#progress N%` oraz `#GUI#error ...` — zawsze po angielsku.

### 13.2. Składnia wypalania

- filtr `ass=` dla źródeł ASS (pełna wierność), `subtitles=` tylko dla SRT;
- postęp: `-progress pipe:1 -nostats`, pole `out_time_us` wobec czasu źródła z `ffprobe`;
- wymuszone: `-pix_fmt yuv420p`, `-movflags +faststart`;
- audio kopiowane (`-c:a copy`), gdy codec legalny w MP4;
- wideo **zawsze** przekodowywane przy wypalaniu — `-c:v copy` z filtrem napisów nie istnieje.

### 13.3. Escapowanie ścieżek w filtrze napisów

Reguła zweryfikowana empirycznie, kolejność ma znaczenie:

1. zamień `\` na `/` w całej ścieżce;
2. zamień `:` na `\:` (dotyczy litery dysku);
3. całość ujmij w apostrofy `'...'` — to obsługuje spacje;
4. nawiasy kwadratowe escapuj jako `\[`, `\]`;
5. polskie znaki nie wymagają escapowania, o ile argument trafia do procesu jako `str`
   przez listę argumentów (bez powłoki).

Przykład działający: `ass='C\:/Users/.../dir with spaces/napisy ąćę.ass'`

**Apostrof w ścieżce jest nieobsługiwalny** — trzy udokumentowane strategie escapowania
zawiodły, filtr gubi znak i nie znajduje pliku. Dlatego napisy do wypalania kopiujemy do
`workspace/tmp/<scope>/` pod nazwą bez apostrofów. Nazwa pliku wynikowego pozostaje pełna.

### 13.4. Zgodność kodeków z MP4

| Codec | MP4 | Uwaga |
|---|---|---|
| E-AC-3 | tak | zweryfikowane, kopiowanie bez przekodowania |
| AAC | tak | domyślny codec audio MP4 |
| MP3 | tak | szeroko odtwarzalny |
| Opus | tak | słabsza zgodność ze starszymi odtwarzaczami |
| FLAC | tak | duży plik, dla archiwum |
| ASS/SSA | **nie** | `-c:s copy` kończy się błędem kontenera |
| załączniki | **nie** | MP4 nie ma mechanizmu attachmentów |

## 14. Definicja ukończenia

**REKOMENDACJA**

- trzy tryby wyjścia działają na realnym odcinku i dają odtwarzalny plik;
- napisy w scalonym MKV renderują się identycznie jak źródłowe (te same czcionki i style);
- wypalony MP4 ma napisy 1:1 ze stylami, a rozmiar mieści się w budżecie z §9.2;
- wypalanie polskich napisów **bez** tłumaczenia i TTS działa jako osobna `/komenda`, która nie
  zmienia ustawień;
- żaden plik nie jest pomijany po cichu — każdy pominięty ma powód w raporcie (§11.2b);
- przed wypalaniem użytkownik zna liczbę plików i szacowany czas;
- Ctrl+C w trakcie wypalania kasuje plik częściowy i nie zostawia śmieci — pokryte testem;
- plik ze `.displayed` w nazwie źródłowej jest poprawnie wykrywany jako wejście (§11.2c);
- użytkownik może nadpisać wybór ścieżki audio i napisów (§6.5);
- macierz z §7 pokryta testami: brak duplikatu polskiej ścieżki, poprawne metadane, poprawne
  pominięcia;
- nieudane składanie nie kasuje niczego i nie rusza źródła — pokryte testem;
- udane składanie kasuje `tmp/<scope>/` tego pliku — pokryte testem;
- ścieżki z apostrofem, spacjami, nawiasami i polskimi znakami przechodzą wypalanie;
- `merge`/`burn` lądują w `output/`, `players` obok źródła — pokryte testem;
- `output_variant` faktycznie steruje zachowaniem;
- brakująca czcionka daje ostrzeżenie z nazwą, nie awarię;
- pełne bramki jakości zielone; smoke E2E na realnym odcinku zielony.
