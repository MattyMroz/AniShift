# Etap 6 — TTS i tor audio — plan implementacji

Kompletny plan budowy neutralnego API TTS, czterech silników syntezy, trwałego resume,
adaptera pipeline oraz osobnego toru audio FFmpeg. Dokument przekłada zaakceptowane
wymagania produktu na kolejność zmian, granice modułów, kontrakty, testy i bramki.

> **Stan źródeł:** 2026-07-28, branch `feature/tts-audio`.
>
> **Źródło prawdy o zachowaniu:** [`etap-6-wymagania.md`](etap-6-wymagania.md).
>
> **Stan realizacji:** `NOT IMPLEMENTED`.
>
> **Ważne:** ten plik nie zastępuje wymagań i nie skraca ich. Jeżeli plan
> różni się od wymagania R1–R64 albo decyzji D1–D22, wygrywa dokument wymagań.
>
> **Ważne:** techniczne wartości pozostawione do pomiaru w §23 wymagań
> są bramkami Fali 0. Nie wolno zamienić ich w przypadkowe stałe produkcyjne.

## 1. Wynik końcowy

Po zakończeniu etapu 6:

- pipeline mapuje polskie spoken events na neutralne `SpeechRequest` bez ponownego
  parsowania zapisanego ASS lub SRT;
- źródło już polskie i źródło przetłumaczone trafiają przez adapter pipeline do tego
  samego publicznego API TTS;
- cztery engine IDs są dostępne przez lazy registry:
  - `elevenbytes`;
  - `elevenlabs`;
  - `edge`;
  - `sapi`;
- domyślny engine to ElevenBytes;
- domyślny wariant ElevenBytes to stabilny `run6`;
- domyślny głos ElevenBytes to `Dallin — Storyteller`;
- `run7` pozostaje widocznym wariantem eksperymentalnym;
- oficjalne ElevenLabs jest osobnym silnikiem wymagającym klucza usera;
- Edge automatycznie używa zweryfikowanego profilu 24 kHz / 96 kb/s;
- jeden engine `sapi` obsługuje:
  - Zosię przez trwały worker x64;
  - Agnieszkę przez trwały worker x86;
- Balcon i pyttsx3 nie uczestniczą w produkcyjnym torze;
- każdy `SpeechRequest` jest osobnym zadaniem syntezy;
- identyczne teksty w różnych requestach nie są deduplikowane;
- poprawny klip tego samego `request_id` może zostać użyty po resume;
- synteza wielu requestów używa globalnego limitu wybranego engine;
- retry błędnego requestu ma pierwszeństwo przed nową pracą;
- scheduler jest jedynym właścicielem retry;
- `Retry-After` ma pierwszeństwo przed lokalnym backoffem;
- provider-wide failure zatrzymuje nowe requesty;
- poprawne klipy innych requestów i batchy zostają zachowane;
- jedno `Ctrl+C` rozpoczyna anulowanie całego przebiegu;
- spóźniony worker nie może zatwierdzić klipu po anulowaniu;
- resume state przeżywa restart aplikacji;
- zmiana tempa, gainu albo codeca nie powtarza płatnej syntezy;
- surowe klipy TTS powstają w `workspace/tmp/<scope-id>/tts/`;
- narrator WAV powstaje w `workspace/tmp/<scope-id>/audio/`;
- narrator jest roboczym artefaktem, a nie drugim finalnym sidecarem;
- klipy są układane chronologicznie na osi czasu;
- heurystyka v1 nigdy nie ucina wypowiedzi;
- konflikt czasowy przesuwa następny klip i raportuje drift;
- naturalna późniejsza przerwa może wyzerować wcześniejszy drift;
- post-process tempo działa per klip, nie na całym narratorze;
- narrator WAV ma PCM S16LE, mono i jawny sample rate;
- montaż obsługuje RF64 dla wyniku przekraczającego RIFF 4 GiB;
- tor audio miksuje narrator z oryginalną ścieżką;
- mixed audio trwa `max(original, narrator)`;
- narrator nie zostaje ucięty do długości obrazu ani oryginalnego audio;
- baseline miksu zachowuje:
  - bazowe `+7 dB` podczas miksowania;
  - offset profilu wybranego głosu;
  - `amix normalize=true`;
  - `dropout_transition=2`;
  - `duration=longest`;
- sam narrator pozostaje na `0 dB`;
- bez oryginalnego audio nie stosuje się mix gainu;
- wynik zachowuje przestrzenność źródła w granicach wybranego codeca;
- narrator pozostaje centralny;
- downmix jest jawny, testowany i raportowany;
- format sidecaru wybiera user:
  - MP3;
  - WAV;
  - E-AC-3;
  - Opus;
  - FLAC;
  - AAC w kontenerze M4A;
- domyślny format to E-AC-3;
- gotowy produkt ma nazwę `{stem}.<codec>`;
- wcześniejszy sidecar innego formatu nie jest usuwany;
- obcy plik o tej samej nazwie nie jest nadpisywany bez decyzji usera;
- każdy plik ma jeden wiersz progress od ekstrakcji do końca audio;
- raport pokazuje syntezę, resume, retry, drift, czas i wynik;
- etap 7 otrzymuje jednoznaczne `mixed_audio_path`;
- finalny MKV ani MP4 nie powstaje jeszcze w etapie 6.

## 2. Źródła prawdy i pierwszeństwo

### 2.1. Źródła repozytorium

Kolejność pierwszeństwa:

1. [`etap-6-wymagania.md`](etap-6-wymagania.md).
2. Aktualny kod i testy AniShift.
3. [`plan-anishift.md`](plan-anishift.md).
4. Ten plan implementacji.
5. [`etap-6-tts-audio.md`](etap-6-tts-audio.md) jako starszy kierunek.
6. Audyt starego mm_avh.
7. Faktyczne źródła starego mm_avh.
8. Faktyczne źródła MangaShift.
9. Faktyczne źródła EchoReader.
10. Oficjalna dokumentacja zależności i usług.

Aktualny kod jest źródłem faktów o stanie wejściowym.

Aktualny kod nie może unieważnić zaakceptowanego wymagania.

### 2.2. Pliki wymagane podczas implementacji

- `docs/plans/etap-6-wymagania.md`;
- `docs/plans/plan-anishift.md`;
- `docs/reference/audyt-mm-avh/04-modules-tts.md`;
- `docs/reference/audyt-mm-avh/08-wzorzec-echoreader-tts.md`;
- `../mm_avh_working_space/modules/subtitle_to_speech.py`;
- `../mm_avh_working_space/modules/tts_elevenbytes.py`;
- `../MangaShift/mangashift/services/tts/`;
- `../EchoReader/echoreader/services/tts/`;
- `anishift/pipeline/runner.py`;
- `anishift/pipeline/types.py`;
- `anishift/config/user_settings.py`;
- `anishift/config/settings.py`;
- `anishift/cli/settings_panel.py`;
- `anishift/cli/pipeline_ui.py`;
- `anishift/services/subtitles/types.py`;
- `anishift/services/subtitles/text.py`;
- `anishift/services/subtitles/srt.py`;
- `anishift/services/translation/types.py`;
- `anishift/errors.py`.

### 2.3. Źródła zewnętrzne

Bezpośrednio przed implementacją engine trzeba ponownie sprawdzić:

- publiczne API bieżącej wersji `edge-tts`;
- strukturę pliku odpowiedzialnego za output format Edge;
- bieżące API oficjalnego SDK ElevenLabs;
- tokeny `output_format` ElevenLabs;
- błędy SDK ElevenLabs i ich statusy HTTP;
- bieżący kontrakt proxy ElevenBytes `run6`;
- bieżący kontrakt proxy ElevenBytes `run7`;
- FFmpeg `atempo`;
- FFmpeg `amix`;
- FFmpeg `pan`;
- FFmpeg E-AC-3 channel layout;
- FFmpeg MP3 channel layout;
- FFmpeg Opus channel layout;
- FFmpeg AAC channel layout;
- FFmpeg FLAC channel layout;
- FFmpeg `-rf64 auto`;
- SAPI `SpVoice`;
- SAPI `SpFileStream`.

Snapshot dokumentacji nie może być traktowany jako wieczna gwarancja działania usługi.

### 2.4. Reguła konfliktu

Jeżeli źródła się różnią:

1. decyzja usera wygrywa z rekomendacją;
2. ustalone wymaganie wygrywa z planem;
3. aktualny kod wygrywa ze starym opisem stanu;
4. oficjalna dokumentacja wygrywa z kopią kodu z innego projektu;
5. potwierdzony lokalny spike wygrywa z założeniem architektonicznym;
6. architektura AniShift wygrywa z bazodanową architekturą MangaShift;
7. bezpieczeństwo płatnych requestów wygrywa z agresywną optymalizacją;
8. jawny błąd wygrywa z cichym fallbackiem.

## 3. Granice etapu

### 3.1. W zakresie

- domena `services/tts`;
- domena `services/audio`;
- lazy registry TTS;
- cztery silniki;
- capabilities;
- availability;
- dynamiczne listy głosów;
- profile per engine i voice;
- custom voice ElevenBytes;
- retry;
- circuit breaker;
- engine-specific concurrency;
- kolejka gotowych batchy w pipeline;
- anulowanie;
- late-result commit gate;
- resume manifest;
- fingerprinty;
- atomowy zapis;
- normalizacja klipów;
- oś czasu;
- drift;
- narrator WAV;
- miks;
- kodeki sidecaru;
- layout kanałów;
- progress;
- recovery;
- raport;
- settings;
- zmienna środowiskowa ElevenLabs;
- testy offline;
- testy FFmpeg;
- testy SAPI;
- testy network;
- testy dwóch realnych odcinków.

### 3.2. Poza zakresem

- ponowna klasyfikacja spoken/displayed;
- dual-role eventów;
- poprawa stylów ASS;
- nowy line breaking;
- typesetting;
- automatyczny scheduler przenoszący spoken do displayed;
- ducking;
- adaptive gain;
- loudness normalization;
- true-peak limiter jako produkcyjny default;
- diarization;
- głos osobno dla każdej postaci;
- klonowanie głosu;
- Supertonic;
- TTS dla TXT bez osi czasu;
- finalny MKV;
- burn MP4;
- integracja graficznego UI;
- automatyczny cleanup resume przed etapem 7;
- automatyczne usuwanie starszego sidecaru;
- automatyczny fallback na drugi płatny engine;
- pobieranie Balcona;
- adapter Balcon;
- adapter pyttsx3.

### 3.3. Zasada przeciw scope creep

Nowy przypadek znaleziony podczas implementacji:

1. jest porównywany z R1–R64;
2. jeżeli mieści się w wymaganiu, dostaje test i poprawkę;
3. jeżeli zmienia zachowanie produktu, wraca do HITL;
4. jeżeli należy do etapu 7 lub przyszłego schedulera, jest notowany bez implementacji;
5. nie może zostać ukryty jako „mały refactor”.

## 4. Rozstrzygnięcia wykonawcze D1–D22

### 4.1. D1 — moment uruchomienia TTS

Pipeline wywołuje API TTS natychmiast po przygotowaniu spoken danego pliku.

Konsekwencje:

- pipeline przekazuje kolejne neutralne `SpeechBatch` do wspólnego runtime TTS;
- nie wolno czekać na zakończenie tłumaczenia całego folderu;
- źródło polskie może trafić do TTS po ekstrakcji;
- źródło obce trafia po poprawnym tłumaczeniu;
- pipeline potrzebuje własnego callbacku „spoken ready”, który buduje `SpeechBatch`;
- TTS działa równolegle z ekstrakcją lub tłumaczeniem innych plików.

### 4.2. D2 — klip dłuższy niż okno

V1 używa polityki `serialize`.

Konsekwencje:

- klip nie jest ucinany;
- klip nie jest automatycznie przyspieszany do okna;
- kolejny klip nie może rozpocząć się przed końcem poprzedniego;
- przesunięcie jest mierzone jako drift;
- późniejsza naturalna przerwa może usunąć drift;
- każdy spoken event pozostaje przeczytany.

### 4.3. D3 — cleanup resume

Resume state zostaje do zweryfikowanego wyniku etapu 7.

Konsekwencje:

- etap 6 może oznaczyć manifest jako complete;
- etap 6 nie usuwa poprawnych klipów po mixed audio;
- obecny cleanup `workspace/tmp/<stem>` musi zostać naprawiony;
- etap 7 przejmie odpowiedzialność za finalne sprzątanie.

### 4.4. D4 — brak deduplikacji audio

Identyczny tekst w dwóch eventach generuje dwa klipy.

Konsekwencje:

- cache key zawiera `request_id`;
- nie ma cross-request content cache;
- resume dotyczy wyłącznie tego samego `request_id`;
- naturalna różnorodność syntezy zostaje zachowana.

### 4.5. D5 — produkt etapu

Finalnym produktem jest mixed audio.

Konsekwencje:

- narrator WAV pozostaje w `tmp`;
- narrator nie jest raportowany jako drugi finalny sidecar;
- brak mixed audio oznacza brak ukończenia etapu dla pliku;
- niepełny narrator nie dostaje finalnej nazwy.

### 4.6. D6 — nazwa produktu

Nazwa to `{stem}.<codec>`.

Konsekwencje:

- nie dodajemy `voiceover`;
- nie dodajemy `lector`;
- nie dodajemy `narration`;
- nie dodajemy języka w nazwie;
- język i tytuł ścieżki doda etap 7 jako metadane.

### 4.7. D7 — widoczność engine

Każdy engine jest widoczny także wtedy, gdy nie jest gotowy.

Panel pokazuje:

- `ready`;
- `missing key`;
- `missing voice`;
- `missing binary`;
- `offline`;
- `service unavailable`;
- `unsupported platform`.

### 4.8. D8 — ElevenBytes bez klucza usera

Nie istnieje `ANISHIFT_ELEVENBYTES_API_KEY`.

Konsekwencje:

- kontrakt proxy jest częścią kodu engine;
- brak działania oznacza `service unavailable`;
- settings nie pokazuje pola klucza;
- token requestu nie jest przedstawiany jako sekret usera.

### 4.9. D9 — jeden engine SAPI

Jeden engine `sapi` wybiera architekturę na podstawie profilu voice.

Konsekwencje:

- registry nie zawiera `harpo`;
- registry nie zawiera `ivona`;
- registry nie zawiera `balcon`;
- registry nie zawiera `pyttsx3`;
- worker x86 i x64 używa tego samego protokołu;
- różni się tylko host i voice profile.

### 4.10. D10 — miks v1

V1 implementuje wyłącznie `fixed_gain`.

Konsekwencje:

- brak duckingu;
- brak loudness normalization;
- brak adaptacyjnego gainu;
- brak automatycznej analizy scen;
- prosty filtr jest deterministyczny;
- przyszłe V1–V5 nie komplikują pierwszej implementacji.

### 4.11. D11 — domyślny codec

Default to E-AC-3.

Default nie jest hardcoded w audio service.

Default pochodzi z `UserSettings`.

### 4.12. D12 — domyślny engine/model

Default:

```text
engine = elevenbytes
provider_model_id = run6
```

`run7` jest oznaczony `experimental`.

### 4.13. D13 — głos ElevenBytes

Wbudowany jest tylko:

```text
alias = dallin
label = Dallin — Storyteller
voice_id = alFofuDn3cOwyoz1i44T
```

Custom voices są preferencją usera.

### 4.14. D14 — długość wyniku

Mixed audio ma długość:

```text
max(original_audio_duration, narrator_duration)
```

Etap 7 nie używa `-shortest`.

### 4.15. D15 — recovery po zmianie engine

Zmiana engine, wariantu albo voice:

- tworzy nowy synthesis fingerprint;
- nie miesza klipów z poprzedniego fingerprintu;
- regeneruje cały nieukończony odcinek;
- nie dotyka ukończonych odcinków;
- zachowuje stary resume state diagnostycznie.

### 4.16. D16 — retry

Default:

```text
first attempt + 3 retries
```

Retry dotyczy tylko błędów transient.

### 4.17. D17 — brak partial sidecar

Nieukończony plik:

- zachowuje klipy;
- zachowuje manifest;
- może zachować narrator diagnostycznie;
- nie tworzy `{stem}.<codec>`;
- nie jest raportowany jako done.

### 4.18. D18 — normalizacja amix

Filtr jawnie zapisuje:

```text
normalize=true
dropout_transition=2
duration=longest
```

Nie polegamy na domyślnych wartościach FFmpeg.

### 4.19. D19 — ustawienia per voice

Każdy profil `engine_id + resolved_voice_id` przechowuje:

- post-process tempo;
- voice mix offset;
- engine-native rate;
- engine-native volume;
- engine-native pitch;
- voice settings wspierane przez engine.

Placeholdery Stage 2 nie są migrowane.

### 4.20. D20 — zachowanie sidecarów

Zmiana codeca nie usuwa starego formatu.

Przykład:

```text
Anime.eac3
Anime.flac
Anime.m4a
```

Wszystkie mogą istnieć równocześnie.

### 4.21. D21 — dwie warstwy gainu

Podczas miksowania:

```text
effective_narrator_gain_db =
    narrator_mix_base_gain_db
    + voice_mix_offset_db
```

Default base:

```text
+7 dB
```

Dallin:

```text
+7 dB - 2 dB = +5 dB
```

Agnieszka:

```text
+7 dB + 2 dB = +9 dB
```

Sam narrator:

```text
0 dB
```

### 4.22. D22 — przestrzenność

Zasady:

- narrator mono jest logicznym centrum;
- mono pozostaje mono;
- stereo dostaje jawny equal-power center;
- surround używa fizycznego kanału center;
- layout źródła zostaje zachowany, jeżeli codec go wspiera;
- downmix występuje tylko z powodu limitu codeca;
- downmix emituje warning;
- automatyczne remapowanie FFmpeg jest zakazane.

## 5. Audyt recyklingu

### 5.1. Co bierzemy z MangaShift

- ogólny kształt domeny `services/tts`;
- lazy registry;
- caller-owned `engine_id`;
- typed `VoiceInfo`;
- typed `AudioResult`;
- typed capabilities;
- config per engine;
- listowanie głosów;
- walidację opcji przed requestem;
- oddzielenie oficjalnego ElevenLabs od ElevenBytes;
- lazy import SDK;
- narrow provider boundary;
- mapowanie SDK errors na domenowe errors;
- jawny lifecycle klienta;
- mechanizm custom voice ID;
- podstawowy Edge engine;
- podstawowy ElevenLabs engine;
- podstawowy ElevenBytes engine.

### 5.2. Co poprawiamy względem MangaShift

- publiczna fasada pozostaje synchroniczna;
- jeden run ma jednego właściciela event loopa;
- concurrency jest globalne dla engine, nie per plik;
- nie ma podwójnych semaphore;
- retry ma jednego właściciela;
- SDK retry jest wyłączone;
- cancellation jest częścią kontraktu;
- late-result commit gate blokuje wynik po anulowaniu;
- engine nie zakłada MP3;
- source format jest metadanym wyniku;
- availability nie jest samym `bool`;
- import SDK nie jest dowodem działania sieci;
- voice cache nie trafia do workspace;
- batch nie zapisuje przypadkowych `0001.mp3` jako publicznego API;
- brak bazy i repository;
- brak globalnego cache TTS;
- brak VRAM/model runtime;
- brak async API wyciekającego do pipeline;
- brak szerokiego `except Exception`;
- brak automatycznego source fallback;
- brak nieograniczonego concurrency 50–100.

### 5.3. Co bierzemy ze starego mm_avh

- sprawdzony kontrakt ElevenBytes;
- `run6`;
- `run7`;
- Dallin voice ID;
- retry wyłącznie nieudanych elementów;
- resume poprawnych requestów;
- per-event audio;
- zachowanie kolejności;
- post-process `atempo`;
- brak zmiany pitch przy `atempo`;
- harmonogram bez ucinania;
- drift odzyskiwany naturalną ciszą;
- `duration=longest`;
- baseline gain;
- `amix normalize=true`;
- `dropout_transition=2`;
- E-AC-3 jako default;
- ochrona końcówki narratora;
- RF64 jako wymaganie długiego WAV.

### 5.4. Co poprawiamy względem starego mm_avh

- brak god-file;
- brak dispatchu `if/elif` po nazwie engine;
- brak whole-SRT engine;
- brak ponownego parsowania SRT;
- brak Balcona;
- brak pyttsx3;
- jeden manifest zamiast luźnych plików cache;
- trzy warstwy fingerprintu;
- atomowy zapis;
- walidacja dekodowalności;
- typed errors;
- typed availability;
- globalna kolejka;
- bounded concurrency;
- jedno `Ctrl+C`;
- brak `call()` bez kontroli return code;
- brak cichego `pass`;
- brak losowego cleanup;
- brak hardcoded E-AC-3;
- brak niejawnego channel mapping;
- brak zależności od kolejności wejść FFmpeg;
- brak volume `0–100` mieszanej z dB;
- brak gainu narratora bez oryginalnego audio;
- brak finalnego sidecaru przy partial result.

### 5.5. Czego nie kopiujemy z EchoReader

- warstw nieużywanych przez AniShift;
- store sekretów;
- frontendowych schema;
- automatycznego fallback chain;
- provider-specific logiki poza narrow adapterem;
- retry, jeżeli dubluje scheduler;
- globalnych klientów SDK.

### 5.6. Co zachowujemy z obecnego AniShift

- `AppContext`;
- `UserSettings`;
- env `Settings`;
- `ErrorContext`;
- hierarchię `AniShiftError`;
- `natsort`;
- `FileOutcome`;
- `PipelineReport`;
- jeden input snapshot;
- izolację plików;
- istniejący LLM circuit breaker;
- istniejącą semantykę recovery;
- istniejące produkty napisów;
- `SpokenLine`;
- `TranslatedLine`;
- widoczny tekst bez tagów;
- jeden wiersz progress na plik;
- domyślnie wyłączony zapis loggera;
- `workspace/tmp`;
- `workspace/output`;
- centralny `bootstrap`.

## 6. Docelowa architektura

### 6.1. Trzy odpowiedzialności

Etap dzieli się na:

1. **TTS API — generowanie głosu**
   - neutralny `SpeechRequest`;
   - tekst;
   - engine;
   - voice;
   - request;
   - retry;
   - surowy clip;
   - resume syntezy;
   - zero wiedzy o napisach i timeline.
2. **Audio API — narration**
   - neutralny `TimedClip`;
   - tempo per clip;
   - normalizacja PCM;
   - kolejność;
   - cisza;
   - overlap;
   - drift;
   - narrator WAV.
3. **Audio API — mix/output**
   - oryginalne audio;
   - gain;
   - channel mapping;
   - codec;
   - finalny sidecar;
   - walidacja.

Pipeline jest jedynym miejscem, które zna jednocześnie wynik napisów, TTS i audio.
Żaden serwis nie może odtwarzać całego pipeline wewnątrz własnej domeny.

### 6.2. Kierunek przepływu

```text
MKV/TXT discovery
        |
        v
extraction + subtitle classification
        |
        +---------------- already Polish ----------------+
        |                                                |
        v                                                |
translation                                             |
        |                                                |
        +---------------- spoken ready <-----------------+
                             |
                             v
                  pipeline narration adapter
                             |
             clean one-line text + opaque request_id
                             |
                             v
                    pipeline/tts_runtime.py
                             |
                             v
                     TtsService.synthesize
                             |
            +----------------+----------------+
            |                                 |
            v                                 v
     engine scheduler                  resume repository
            |
            v
     lazy engine registry
            |
    +-------+----------+----------+---------+
    |                  |          |         |
    v                  v          v         v
elevenbytes       elevenlabs     edge      sapi
    |                  |          |         |
    +------------------+----------+---------+
                             |
                             v
                    SpeechBatchResult
                             |
                             v
             pipeline joins request_id with timings
                             |
                             v
                       tuple[TimedClip]
                             |
                             v
                    per-clip normalization
                             |
                             v
                       timeline planner
                             |
                             v
                    narrator PCM / WAV
                             |
                             v
                      AudioService.mix
                             |
                             v
                 validated {stem}.<codec>
                             |
                             v
                       FileOutcome
```

### 6.3. Kierunek zależności

```text
cli
 |
 v
pipeline ---------> services/tts
 |                       |
 |                       v
 |                  tts engines
 |
 +-----------------> services/audio
 |
 +-----------------> services/subtitles
 |
 +-----------------> services/translation
```

`services/tts` może importować:

- wspólne errors;
- swoje typy;
- engine packages;
- neutralne request/result types z własnej domeny;
- protocol audio validator wstrzyknięty przez composition.

`services/tts` nie importuje:

- CLI;
- pipeline;
- `pysubs2`;
- subtitles;
- translation;
- `SSAEvent`, `SubtitleSplit`, `SpokenLine`, `TranslatedLine` ani `FileTranslation`;
- `UserSettings`;
- `AppContext`;
- konkretnego translatora;
- Rich;
- prompt_toolkit.

`services/audio` może importować:

- platform resolver binarek;
- wspólne errors;
- własne typy;
- standard library.

`services/audio` nie importuje:

- TTS engine;
- pipeline;
- CLI;
- translation;
- subtitles.

### 6.4. Dozwolone importy

- pipeline zna TTS i audio;
- pipeline mapuje `AppContext` na domain config;
- pipeline mapuje wynik TTS na `FileOutcome`;
- pipeline przekazuje callbacki progress;
- TTS registry importuje engine dopiero w factory;
- engine importuje wspólne TTS types;
- SAPI controller importuje subprocess helpers;
- audio service importuje `resolve_binary`;
- testy mogą importować moduły prywatne tylko do contract tests, gdy publiczny dowód nie wystarcza.

### 6.5. Zakazane importy

```text
services/tts       -X-> pipeline
services/tts       -X-> cli
services/audio     -X-> services/tts/engines
engine A           -X-> engine B
engine             -X-> UserSettings
engine             -X-> FileOutcome
resume             -X-> Rich
timeline           -X-> provider SDK
config             -X-> edge_tts
config             -X-> elevenlabs
registry import    -X-> provider SDK import
```

### 6.6. Właściciel współbieżności

`PipelineTtsRuntime` posiada kolejkę gotowych batchy, mapowanie do plików, agregację
wyników i recovery całego przebiegu.

Jedna run-scoped instancja `TtsService` posiada wyłącznie zasoby wykonania syntezy:

- dedykowany Runner/thread dla async engine;
- selected engine;
- globalny semaphore engine;
- bounded priority queue requestów providera;
- retry schedule;
- circuit state;
- cancel event;
- late-result commit gate;
- worker lifecycle;
- provider counters.

Nie istnieje:

- kolejka plików w `services/tts`;
- producer extraction/translation w `services/tts`;
- semaphore w pipeline i drugi w engine;
- retry w schedulerze i drugi w SDK;
- osobny event loop per request;
- `asyncio.run()` per request;
- executor per clip.

### 6.7. Publiczny sync boundary

Pipeline uruchamia dwa niezależne synchroniczne API:

```python
with TtsService(config, dependencies) as service:
    speech = service.synthesize(batch, callbacks=callbacks)

audio = audio_service.render(audio_requests, callbacks=callbacks)
```

`TtsService.synthesize`:

1. synchroniczne, thread-safe wywołanie przekazuje requesty jednego batcha do jednego
   współdzielonego Runnera;
2. requesty trafiają do współdzielonego schedulera engine;
3. async engine generuje klipy;
4. sync SDK działa w kontrolowanym executorze;
5. zwraca `SpeechBatchResult` bez narratora i miksu;
6. zamknięcie czeka do deadline;
7. pozostałe late results tracą prawo commitu.

`AudioService.render`:

1. dostaje źródłowe audio i `TimedClip`;
2. normalizuje klipy;
3. buduje timeline i narrator;
4. miksuje i koduje;
5. zwraca `AudioRenderResult`.

Pipeline nie otrzymuje coroutine.
Równoległe wywołania `synthesize(batch)` nie tworzą nowych event loopów ani osobnych
limitów; współdzielą jedną instancję service.

## 7. Docelowe drzewo plików

Legenda:

- `ADD` — nowy plik;
- `MOD` — zmiana istniejącego pliku;
- `DEL` — usunięcie;
- `KEEP` — świadomie bez zmiany.

```text
.env.example                                                   MOD
pyproject.toml                                                 MOD przez uv add/uv remove
uv.lock                                                        MOD przez uv
anishift/
├── errors.py                                                  MOD
├── bootstrap.py                                               KEEP
├── config/
│   ├── settings.py                                            MOD
│   ├── user_settings.py                                       MOD
│   └── workspace.py                                           KEEP
├── cli/
│   ├── AGENTS.md                                              MOD przez skill agents-md
│   ├── CLAUDE.md                                              MOD przez skill agents-md
│   ├── settings_panel.py                                      MOD
│   └── pipeline_ui.py                                         MOD
├── pipeline/
│   ├── AGENTS.md                                              MOD przez skill agents-md
│   ├── CLAUDE.md                                              MOD przez skill agents-md
│   ├── types.py                                               MOD
│   ├── runner.py                                              MOD
│   ├── narration.py                                           ADD — jedyny adapter napisów do voice requests
│   ├── recovery.py                                            ADD
│   ├── tts_runtime.py                                         ADD
│   ├── tts_queue.py                                           ADD
│   └── audio_runtime.py                                       ADD
└── services/
    ├── subtitles/
    │   ├── types.py                                           KEEP
    │   ├── text.py                                            KEEP
    │   ├── service.py                                         KEEP
    │   └── srt.py                                             KEEP
    ├── translation/
    │   └── types.py                                           KEEP
    ├── tts/
    │   ├── AGENTS.md                                          ADD
    │   ├── CLAUDE.md                                          ADD
    │   ├── __init__.py                                        ADD
    │   ├── config.py                                          ADD
    │   ├── constants.py                                       ADD
    │   ├── errors.py                                          ADD
    │   ├── protocols.py                                       ADD
    │   ├── types.py                                           ADD
    │   ├── validation.py                                      ADD — tylko kontrakt czystego tekstu
    │   ├── chunking.py                                        ADD — limity engine, zero składni napisów
    │   ├── fingerprint.py                                     ADD
    │   ├── artifacts.py                                       ADD — prywatne ścieżki klipów
    │   ├── resume.py                                          ADD
    │   ├── scheduler.py                                       ADD
    │   ├── service.py                                         ADD
    │   └── engines/
    │       ├── AGENTS.md                                      ADD
    │       ├── CLAUDE.md                                      ADD
    │       ├── __init__.py                                    ADD
    │       ├── elevenbytes/
    │       │   ├── AGENTS.md                                  ADD
    │       │   ├── CLAUDE.md                                  ADD
    │       │   ├── __init__.py                                ADD
    │       │   ├── config.py                                  ADD
    │       │   ├── constants.py                               ADD
    │       │   ├── types.py                                   ADD
    │       │   ├── api_backend.py                             ADD
    │       │   └── service.py                                 ADD
    │       ├── elevenlabs/
    │       │   ├── AGENTS.md                                  ADD
    │       │   ├── CLAUDE.md                                  ADD
    │       │   ├── __init__.py                                ADD
    │       │   ├── config.py                                  ADD
    │       │   ├── constants.py                               ADD
    │       │   ├── options.py                                 ADD
    │       │   └── service.py                                 ADD
    │       ├── edge/
    │       │   ├── AGENTS.md                                  ADD
    │       │   ├── CLAUDE.md                                  ADD
    │       │   ├── __init__.py                                ADD
    │       │   ├── config.py                                  ADD
    │       │   ├── constants.py                               ADD
    │       │   ├── patch.py                                   ADD
    │       │   └── service.py                                 ADD
    │       └── sapi/
    │           ├── AGENTS.md                                  ADD
    │           ├── CLAUDE.md                                  ADD
    │           ├── __init__.py                                ADD
    │           ├── config.py                                  ADD
    │           ├── constants.py                               ADD
    │           ├── protocol.py                                ADD
    │           ├── worker.py                                  ADD
    │           ├── sapi_worker.ps1                            ADD
    │           └── service.py                                 ADD
    └── audio/
        ├── AGENTS.md                                          ADD
        ├── CLAUDE.md                                          ADD
        ├── __init__.py                                        ADD
        ├── config.py                                          ADD
        ├── constants.py                                       ADD
        ├── errors.py                                          ADD
        ├── types.py                                           ADD
        ├── probe.py                                           ADD
        ├── commands.py                                        ADD
        ├── channels.py                                        ADD
        ├── normalize.py                                       ADD
        ├── timeline.py                                        ADD
        ├── fingerprint.py                                     ADD
        ├── resume.py                                          ADD
        ├── output.py                                          ADD
        └── service.py                                         ADD
tests/
├── config/
│   └── test_user_settings.py                                  MOD
├── cli/
│   ├── test_settings_panel.py                                 MOD
│   └── test_pipeline_ui.py                                    MOD
├── pipeline/
│   ├── test_pipeline_runner.py                                MOD
│   ├── test_narration.py                                      ADD
│   ├── test_recovery.py                                       ADD
│   ├── test_tts_queue.py                                      ADD
│   ├── test_tts_runtime.py                                    ADD
│   └── test_audio_runtime.py                                  ADD
├── services/
│   ├── tts/
│   │   ├── conftest.py                                        ADD
│   │   ├── test_tts_config.py                                 ADD
│   │   ├── test_tts_registry.py                               ADD
│   │   ├── test_tts_contract.py                               ADD
│   │   ├── test_tts_validation.py                             ADD
│   │   ├── test_tts_chunking.py                               ADD
│   │   ├── test_tts_fingerprint.py                            ADD
│   │   ├── test_tts_resume.py                                 ADD
│   │   ├── test_tts_scheduler.py                              ADD
│   │   ├── test_tts_service.py                                ADD
│   │   ├── test_tts_elevenbytes.py                            ADD
│   │   ├── test_tts_elevenlabs.py                             ADD
│   │   ├── test_tts_edge.py                                   ADD
│   │   ├── test_tts_sapi.py                                   ADD
│   │   └── test_tts_network.py                                ADD
│   └── audio/
│       ├── conftest.py                                        ADD
│       ├── test_audio_config.py                               ADD
│       ├── test_audio_probe.py                                ADD
│       ├── test_audio_commands.py                             ADD
│       ├── test_audio_channels.py                             ADD
│       ├── test_audio_normalize.py                            ADD
│       ├── test_audio_timeline.py                             ADD
│       ├── test_audio_fingerprint.py                          ADD
│       ├── test_audio_resume.py                               ADD
│       ├── test_audio_output.py                               ADD
│       └── test_audio_integration.py                          ADD
└── data/
    └── audio/
        ├── README.md                                          ADD
        ├── mono.wav                                           ADD lub generowany w fixture
        ├── stereo.wav                                         ADD lub generowany w fixture
        ├── surround-5.1.wav                                   ADD lub generowany w fixture
        └── surround-7.1.wav                                   ADD lub generowany w fixture
```

### 7.1. Granica drzewa

W `services/tts/` **nie powstają**:

- parser napisów;
- `text.py` rozumiejący ASS/SRT;
- adapter `SpokenLine`/`TranslatedLine`;
- typ pliku wejściowego zawierający MKV, source audio albo timing;
- timeline, narrator WAV lub mixer;
- drugi odpowiednik `_MkvState`, `FileOutcome` albo pipeline.

Jedynym miejscem mapującym istniejący stan napisów na API głosu jest
`pipeline/narration.py`. TTS przyjmuje wynik tego adaptera i może być testowany bez
utworzenia `SSAFile`.

### 7.2. Pliki świadomie usuwane

Po potwierdzeniu braku innych importów:

- zależność `pyttsx3`;
- zależność `pydub`, jeżeli nowy ani obecny kod jej nie używa;
- każdy nowy artefakt Balcon, jeżeli pojawi się poza już usuniętym spike;
- żaden plik usera w workspace.

Usunięcie zależności wyłącznie przez:

```bash
uv remove pyttsx3
uv remove pydub
```

### 7.3. Pliki świadomie bez zmian

- klasyfikator spoken/displayed;
- mapowanie tagów ASS;
- line breaking;
- prompt LLM;
- providerzy LLM;
- Google translation;
- DeepL translation;
- format produktów `.pl.ass`;
- format produktów `.spoken.pl.ass`;
- format produktów `.displayed.pl.ass`;
- składanie finalnego MKV.

### 7.4. Miękka granica wielkości pliku

Około 300 linii kodu jest sygnałem review odpowiedzialności.

Nie jest:

- limitem;
- testem;
- hookiem;
- powodem sztucznego dzielenia spójnego modułu;
- zakazem docstringów.

Jeżeli plik przekracza ten sygnał, reviewer pyta:

1. czy zawiera więcej niż jedną odpowiedzialność;
2. czy miesza provider, retry, cache i montaż;
3. czy zawiera kod możliwy do testowania osobno;
4. czy podział poprawi nazwy i kierunek zależności;
5. czy podział nie stworzy abstrakcji bez konsumenta.

## 8. Typy domenowe TTS

### 8.1. `SpeechRequest`

Publiczny, neutralny kontrakt:

```python
@dataclass(frozen=True, slots=True)
class SpeechRequest:
    request_id: str
    text: str
    request_rank: int
```

Własności:

- `request_id` jest opaque dla TTS;
- `text` jest już gotowym, jednoliniowym tekstem do przeczytania;
- `request_rank` zachowuje kolejność przekazaną przez caller;
- nie zawiera timingu, stylu, layoutu ani source text;
- nie przechowuje obiektu subtitles, translation, pipeline ani audio;
- pozostaje immutable;
- jest walidowany na publicznej granicy TTS.

### 8.2. `SpeechBatch`

```python
@dataclass(frozen=True, slots=True)
class SpeechBatch:
    scope_id: str
    batch_rank: int
    requests: tuple[SpeechRequest, ...]
```

`scope_id`:

- jest nadawany przez caller;
- grupuje resume i raport jednego zadania;
- nie jest interpretowany jako ścieżka, nazwa MKV ani track ID;
- nie daje TTS dostępu do stanu pipeline.

`batch_rank` pochodzi z jednego snapshotu `natsorted`, ale TTS zna wyłącznie liczbę,
nie regułę jej wyznaczenia.

### 8.3. `PreparedSpeechRequest`

```python
@dataclass(frozen=True, slots=True)
class PreparedSpeechRequest:
    request: SpeechRequest
    chunks: tuple[SpeechChunk, ...]
    status: SpeechPreparationStatus
```

Status:

- `ready`;
- `skipped_non_speech`;
- `unsupported_input`;
- `invalid_contract`.

`translation_incomplete` nie jest statusem TTS. Pipeline nie tworzy requestu dla
nieukończonego tłumaczenia.

### 8.4. `SpeechChunk`

```python
@dataclass(frozen=True, slots=True)
class SpeechChunk:
    part_index: int
    text: str
    fingerprint: str
```

Chunk istnieje tylko dla limitu pojedynczego requestu.

Nie jest translation batchingiem i nie interpretuje składni napisów.

### 8.5. `EngineCapabilities`

```python
@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    locality: EngineLocality
    source_formats: tuple[AudioFormat, ...]
    supports_concurrency: bool
    supports_native_rate: bool
    supports_native_volume: bool
    supports_pitch: bool
    supports_voice_settings: bool
    requires_api_key: bool
    min_text_chars: int
    max_text_chars: int | None
    max_text_bytes: int | None
    availability_probe: AvailabilityProbeKind
```

Capabilities są statycznym opisem implementacji.

Availability jest dynamicznym wynikiem środowiska.

### 8.6. `EngineAvailability`

```python
@dataclass(frozen=True, slots=True)
class EngineAvailability:
    status: AvailabilityStatus
    message: str
    checked_at: datetime
    source: AvailabilitySource
    voices: tuple[VoiceInfo, ...] = ()
```

Status:

```python
class AvailabilityStatus(StrEnum):
    READY = "ready"
    MISSING_KEY = "missing_key"
    MISSING_VOICE = "missing_voice"
    MISSING_BINARY = "missing_binary"
    OFFLINE = "offline"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
```

### 8.7. `VoiceInfo`

```python
@dataclass(frozen=True, slots=True)
class VoiceInfo:
    id: str
    label: str
    engine_id: str
    language: str
    gender: str = ""
    architecture: ProcessArchitecture | None = None
    experimental: bool = False
```

### 8.8. `RawClip`

```python
@dataclass(frozen=True, slots=True)
class RawClip:
    request_id: str
    path: Path
    format: AudioFormat
    sample_rate: int
    channels: int
    duration_ms: int
    engine_id: str
    provider_model_id: str
    voice_id: str
    attempts: int
    request_time_ms: float
    from_resume: bool
```

Bytes nie muszą pozostawać w pamięci po atomowym zapisie.

### 8.9. `SynthesizedRequest`

```python
@dataclass(frozen=True, slots=True)
class SynthesizedRequest:
    request: SpeechRequest
    status: SynthesisStatus
    raw_clip: RawClip | None
    error_code: str
    retries: int
```

### 8.10. `SpeechBatchResult`

```python
@dataclass(frozen=True, slots=True)
class SpeechBatchResult:
    scope_id: str
    status: SpeechBatchStatus
    requests: tuple[SynthesizedRequest, ...]
    stats: SpeechBatchStats
    failure: TtsFailure | None
```

Nie zawiera:

- `source_path`;
- `narrator_path`;
- `mixed_audio_path`;
- source audio;
- timeline ani channel layout.

### 8.11. `SpeechBatchStats`

Statystyki:

- total requests;
- synthesized;
- resume hits;
- skipped;
- failed;
- provider calls;
- retries;
- raw synthesis time;
- engine;
- model;
- voice.

### 8.12. `TimedClip` — typ domeny audio

Po otrzymaniu `SpeechBatchResult` pipeline łączy klip z przechowanym timingiem:

```python
@dataclass(frozen=True, slots=True)
class TimedClip:
    request_id: str
    start_ms: int
    end_ms: int
    source_order: int
    clip_path: Path
    clip_format: AudioFormat
    sample_rate: int
    channels: int
    duration_ms: int
```

`TimedClip` należy do `services/audio/types.py`. TTS nigdy go nie przyjmuje ani nie
tworzy. Pipeline kopiuje wymagane metadata z `RawClip`, więc `services/audio` nie importuje
typów TTS. Informacje o pozycji wizualnej napisów pozostają w subtitles/pipeline i nie są
częścią etapu generowania głosu ani podstawowego timeline audio.

## 9. Kontrakty protokołów

### 9.1. Engine protocol

```python
class TtsEngine(Protocol):
    @property
    def engine_id(self) -> str: ...

    @property
    def capabilities(self) -> EngineCapabilities: ...

    async def availability(
        self,
        *,
        live: bool = False,
    ) -> EngineAvailability: ...

    async def list_voices(self) -> tuple[VoiceInfo, ...]: ...

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult: ...

    async def close(self) -> None: ...
```

### 9.2. `SynthesisRequest`

```python
@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    request_id: str
    text: str
    voice_id: str
    provider_model_id: str
    native_rate: str | float | None
    native_volume: str | float | None
    native_pitch: str | float | None
    options: EngineOptions
    destination: Path
    deadline_s: float
```

### 9.3. Brak output-format fiction

Engine zwraca rzeczywisty format providera.

Przykłady:

- Edge zwraca MP3;
- SAPI zwraca WAV PCM;
- ElevenBytes zwraca format zgodny z rzeczywistym endpointem;
- ElevenLabs zwraca format zgodny z wybranym tokenem API.

Wspólny audio normalizer dopiero potem tworzy PCM montażowe.

### 9.4. `CancellationToken`

Token zapewnia:

- `is_cancelled`;
- oczekiwanie na cancel;
- run generation;
- commit permission;
- close deadline.

Cancel token nie udaje, że przerwał nieanulowalne SDK.

### 9.5. `ClipValidator`

```python
class ClipValidator(Protocol):
    def validate_clip(
        self,
        path: Path,
        expected: ClipExpectation,
    ) -> AudioProbe: ...
```

TTS używa protokołu.

Implementację dostarcza `services/audio`.

TTS nie importuje FFmpeg command builder bezpośrednio.

### 9.6. `ProgressSink`

```python
class TtsProgressSink(Protocol):
    def on_batch_state(self, state: SpeechBatchProgress) -> None: ...
    def on_request_committed(self, update: SpeechRequestProgress) -> None: ...
```

Callback:

- nie może blokować schedulera długo;
- nie może zatwierdzać domenowego stanu;
- nie dostaje sekretów;
- zostaje zamknięty przed shutdown UI.

## 10. Walidacja i przygotowanie requestu TTS

### 10.1. Publiczna granica

`services/tts` zakłada, że caller przekazuje gotowy tekst. Nie naprawia ani nie
interpretuje reprezentacji napisów.

Walidacja wykonuje wyłącznie:

1. niepusty i bezpieczny `scope_id`;
2. unikalny `request_id` w batchu;
3. nieujemny `request_rank`;
4. `text` typu `str`;
5. brak znanych tokenów świadczących o złamaniu kontraktu;
6. klasyfikację speech/non-speech;
7. sprawdzenie limitów engine;
8. podział zbyt długiego requestu.

### 10.2. Zanieczyszczony request

Jeżeli publiczne API dostanie tekst zawierający np. `{\i1}`, `\N`, `\h`, HTML tag albo
wektor drawing, zwraca `TtsInputContractError`.

Nie:

- importuje parsera ASS/SRT;
- próbuje odtwarzać widocznego tekstu;
- usuwa tagów „na wszelki wypadek”;
- skleja fragmentów rysunku z tekstem;
- modyfikuje requestu przed zgłoszeniem błędu.

Poprawna transformacja `dobry\Nwieczór -> dobry wieczór` należy do adaptera pipeline,
który pracuje na istniejącym wewnętrznym stanie napisów.

### 10.3. Non-speech

Pominięte:

```text
""
"   "
"..."
"!"
"?!"
```

Niepominięte:

```text
"A"
"7"
"O!"
"Ja..."
```

### 10.4. Pojedynczy znak

Adapter pojedynczego znaku jest engine-specific.

Plan Fali 0 porównuje:

- bezpośredni request;
- bezpieczny trailing punctuation;
- bezpieczny trailing whitespace;
- SSML wyłącznie tam, gdzie publiczne API wspiera;
- jawny `unsupported_input`.

Adapter nie może zmienić słyszalnej treści.

### 10.5. Zbyt długi request

Algorytm:

1. policzyć limit znaków;
2. policzyć limit UTF-8 bytes;
3. jeżeli mieści się — jeden chunk;
4. próbować podziału na granicy zdania;
5. następnie na granicy frazy;
6. następnie na granicy słowa;
7. nigdy nie ciąć grapheme cluster;
8. nie wysyłać pustych części;
9. nadać stabilne `part_index`;
10. fingerprintować każdą część;
11. zsyntetyzować części;
12. skleić bez sztucznej pauzy;
13. zwalidować połączony klip.

### 10.6. Brak globalnego number normalizer

V1 nie zamienia:

- dat;
- numerów;
- liczb;
- skrótów;
- nazw odcinków;
- cyfr rzymskich.

Zmiana wymaga osobnego modułu i testów wymowy.

## 11. Lazy registry

### 11.1. Registry table

```python
_REGISTRY: Final[dict[str, EngineFactory]] = {
    "edge": _create_edge,
    "elevenbytes": _create_elevenbytes,
    "elevenlabs": _create_elevenlabs,
    "sapi": _create_sapi,
}
```

### 11.2. Kolejność IDs

Publiczna lista jest stabilna i posortowana:

```text
edge
elevenbytes
elevenlabs
sapi
```

Default produktu nie wynika z kolejności registry.

### 11.3. Lazy imports

Import:

```python
import anishift.services.tts
```

nie może importować:

- `edge_tts`;
- `elevenlabs`;
- `httpx` backendu provider-specific;
- SAPI worker;
- PowerShell;
- COM.

### 11.4. Unknown engine

Błąd zawiera:

- błędny ID;
- poprawne IDs;
- suggestion otwarcia settings;
- error code;
- zero tracebacku w normalnym CLI.

### 11.5. Registry jako SSOT

Registry zasila:

- config validation;
- settings picker;
- test registry;
- availability listing;
- engine factory;
- doctor summary.

Nie powstaje druga lista w panelu.

## 12. Config domeny TTS

### 12.1. `TtsConfig`

```python
@dataclass(frozen=True, slots=True)
class TtsConfig:
    engine_id: str
    provider_model_id: str
    voice_id: str
    max_concurrency: int
    max_retries: int
    request_timeout_s: float
    shutdown_deadline_s: float
    queue_capacity: int
    native_rate: str | float | None
    native_volume: str | float | None
    native_pitch: str | float | None
    engine_options: EngineOptions
```

`TtsConfig` opisuje wyłącznie syntezę. Post-process tempo, gain, codec, channel policy,
źródłowe audio i katalog produktu należą do `AudioConfig` albo do zależności
wstrzykiwanych przez composition root.

Defaulty Fali 0:

- ElevenBytes concurrency `12`;
- Edge concurrency `8`;
- SAPI concurrency `1`;
- ElevenLabs concurrency `4` jako konserwatywny default przed płatnym smoke;
- request timeout `30 s`;
- shutdown deadline `5 s`, następnie hard kill;
- queue capacity `max(2, 2 * max_concurrency)`;
- cooldown `15/30/60/120 s`, z limitem `120 s`;
- `Retry-After` ma pierwszeństwo.

### 12.2. `AudioConfig` — osobna domena

```python
@dataclass(frozen=True, slots=True)
class AudioConfig:
    codec_profile: AudioCodecProfile
    bitrate: str | None
    narrator_sample_rate: int
    narrator_sample_width: int
    narrator_channels: int
    narrator_mix_base_gain_db: float
    voice_mix_offset_db: float
    original_gain_db: float
    timeline_policy: TimelinePolicy
```

### 12.3. Walidacja

Przed pierwszym requestem TTS walidujemy:

- engine ID;
- model/endpoint;
- voice ID;
- concurrency;
- retry;
- timeout;
- queue capacity;
- native options;
- voice settings;

Przed pierwszym renderem Audio osobno walidujemy:

- post-process tempo;
- codec profile;
- bitrate;
- channel policy;
- writable tmp path;
- ffmpeg/ffprobe availability.

### 12.4. Sekrety

`TtsConfig` nie przechowuje klucza w zwykłym repr.

Klucz ElevenLabs:

```python
elevenlabs_api_key: str = field(default="", repr=False)
```

Lepszy wariant, jeżeli spójny z Pydantic Settings:

```python
SecretStr
```

## 13. Error model

### 13.1. Hierarchia

Planowane klasy:

```text
AniShiftError
└── TtsError
    ├── TtsConfigError + FatalError
    ├── TtsAuthError + FatalError
    ├── TtsVoiceError + FatalError
    ├── TtsInputError + FatalError
    ├── TtsUnsupportedError + FatalError
    ├── TtsCancelledError + FatalError
    ├── TtsRateLimitError + TransientError
    ├── TtsTimeoutError + TransientError
    ├── TtsNetworkError + TransientError
    └── TtsProviderUnavailableError + TransientError

AniShiftError
└── AudioError
    ├── AudioConfigError + FatalError
    ├── AudioProbeError + FatalError
    ├── AudioDecodeError + FatalError
    ├── AudioLayoutError + FatalError
    ├── AudioOutputCollisionError + FatalError
    ├── AudioProcessError + FatalError
    └── AudioCancelledError + FatalError
```

### 13.2. Retry classification

| Błąd | Retry |
|---|---:|
| timeout | tak |
| connection reset | tak |
| 429 | tak |
| provider 5xx | tak |
| ElevenBytes 403 | ograniczony transient |
| ElevenLabs 403 | nie |
| 400 | nie |
| 401 | nie |
| missing voice | nie |
| invalid model | nie |
| invalid output format | nie |
| empty audio | zależnie od provider contract, maksymalnie transient |
| cancelled | nie |
| FFmpeg command error | nie jako provider retry |

### 13.3. `Retry-After`

`TtsRateLimitError` przechowuje:

```python
retry_after_s: float | None
```

Scheduler wybiera:

```text
max(retry_after_s, local_backoff_s)
```

Nie skraca wartości providera.

### 13.4. Error context

Każdy error zawiera:

- code;
- message;
- suggestion;
- safe details;
- engine;
- `request_id`, jeżeli dotyczy;
- bezpieczny status HTTP;
- retry-after, jeżeli dotyczy;
- bez request body;
- bez response audio;
- bez API key;
- bez pełnego signed URL.

## 14. TtsService

### 14.1. Odpowiedzialność

`TtsService`:

- waliduje config;
- lazy tworzy engine;
- utrzymuje jedną sesję wybranego engine;
- planuje wyłącznie requesty syntezy przekazane przez wywołania API;
- koordynuje resume klipów TTS;
- zwraca typed result per batch;
- zamyka engine;
- nie montuje kanałów samodzielnie;
- nie renderuje progressu;
- nie zna CLI;
- nie wybiera defaultów usera.

### 14.2. Lifecycle

Stan:

```text
created -> running -> closing -> closed
```

Zasady:

- constructor nie tworzy klienta;
- `__enter__` nie wykonuje requestu;
- pierwszy rzeczywisty request tworzy engine;
- `close()` jest idempotentne;
- call po close daje config error;
- wyjątek wewnątrz context managera nadal zamyka engine;
- SAPI worker zostaje zakończony;
- klient HTTP zostaje zamknięty;
- executor zostaje zamknięty do deadline.

### 14.3. Publiczne wejście

Sygnatura publiczna:

```python
def synthesize(
    self,
    batch: SpeechBatch,
    *,
    callbacks: TtsProgressSink,
) -> SpeechBatchResult: ...
```

Pipeline jest właścicielem kolejki batchy i wywołuje tę metodę dla każdego gotowego
batcha. Jedna run-scoped instancja `TtsService` może przyjmować równoległe wywołania;
wszystkie korzystają z tego samego limitera, circuit state i engine lifecycle.

TTS nie posiada kolejki plików, producenta ekstrakcji ani agregatu całego pipeline.

Runtime może utrzymywać jedną instancję serwisu i wywoływać ją dla batchy pojawiających
się podczas pracy pipeline, ale to pipeline:

- wykrywa moment gotowości spoken;
- tworzy batch;
- zamyka własnego producera;
- przekazuje wspólny sygnał cancel.

TTS nie obserwuje ekstrakcji, tłumaczenia ani listy plików. Jego wewnętrzna kolejka
requestów jest bounded, więc caller nie może bez końca zapełniać pamięci.

### 14.4. Wynik

`synthesize` zwraca jeden `SpeechBatchResult`, który zawiera:

- wynik każdego requestu przekazanego batcha;
- statystyki requestów i providera dla batcha;
- typowany failure, jeżeli batch nie został ukończony;
- status anulowania należący do tego wywołania.

Agregacja wielu batchy, lista plików `done/failed/not processed` i decyzja recovery
należą do pipeline.

## 15. Scheduler requestów

### 15.1. Jedna kolejka priorytetowa

Klucz:

```python
(
    priority_class,
    retry_ready_at,
    batch_rank,
    request_rank,
    enqueue_sequence,
)
```

Priority class:

```text
0 = retry gotowy do wykonania
1 = nowy request
```

### 15.2. Natsorted

`batch_rank` nadaje caller.

Wśród gotowych batchy niższy `batch_rank` ma pierwszeństwo.

TTS nie wie, dlaczego dany batch jest gotowy. Brak wcześniejszego batcha nie blokuje
requestów już przekazanych przez caller.

### 15.3. Retry bez bariery rund

Nie implementujemy:

```text
wykonaj wszystkie
czekaj
zbierz błędy
wykonaj całą nową rundę
```

Implementujemy:

```text
request fails
schedule retry_at
release concurrency slot
other ready work may run
when retry_at arrives, failed request receives priority
```

### 15.4. Slot concurrency

Backoff nie zajmuje slotu.

Walidacja wyniku po request może należeć do tego samego tasku.

Praca Audio nie zajmuje slotu provider request.

### 15.5. Globalny limit

Przy trzech batchach i concurrency `4`:

```text
łączna liczba aktywnych requestów <= 4
```

Nie:

```text
4 requesty na każdy batch
```

### 15.6. Provider-wide failure

Circuit otwiera się dla:

- wyczerpanej serii rate limit;
- proxy-wide 403 ElevenBytes;
- auth error;
- quota/payment;
- service unavailable;
- powtarzalnego 5xx wskazującego awarię usługi.

Po otwarciu:

- nowe requesty nie startują;
- aktywne mogą zakończyć się;
- poprawne wyniki aktywnych mogą zostać przyjęte, jeżeli run nadal ma commit permission;
- unsent requests pozostają w kolejce;
- caller dostaje typowany stan awarii i listę niezakończonych requestów.

### 15.7. Błąd pojedynczego requestu

Input-specific 400:

- nie otwiera globalnego circuit, jeżeli wiadomo, że dotyczy tekstu;
- kończy request fatalnie;
- `SpeechBatchResult` nie udaje pełnego sukcesu;
- inne batche mogą się zakończyć;
- decyzja o finalnym sidecarze należy do pipeline i Audio, nie do TTS.

### 15.8. Dokładna liczba prób

`max_retries=3` oznacza:

```text
attempt 1
retry 1
retry 2
retry 3
```

Maksymalnie cztery wysłania payloadu.

### 15.9. SDK retry

SDK i transport:

- automatyczny retry wyłączony;
- reconnect bez wysłania payloadu nie zwiększa attempts;
- każde powtórne wysłanie payloadu zwiększa attempts;
- test fake server liczy realne payload submissions.

## 16. Anulowanie

### 16.1. Jedno `Ctrl+C`

Pierwsze `Ctrl+C`:

1. ustawia run cancel;
2. zamyka producer input;
3. blokuje start nowych requestów;
4. anuluje oczekujące async tasks;
5. przerywa backoff;
6. wysyła close do SAPI;
7. kończy FFmpeg;
8. rozpoczyna shutdown deadline;
9. zamyka progress sink;
10. wraca do promptu po kontrolowanym cleanup.

### 16.2. Late-result commit gate

Każdy wynik przed commitem sprawdza:

```python
commit_gate.can_commit(run_generation)
```

Jeżeli false:

- nie wykonuje atomic replace final clip;
- nie aktualizuje manifestu;
- nie zwiększa progress;
- nie zmienia `SpeechBatchResult` ani stanu caller;
- tymczasowy plik zostaje usunięty lub oznaczony orphan do weryfikacji.

### 16.3. Blokujące SDK

Anulowanie coroutine czekającej na `to_thread` nie kończy wywołania SDK.

Plan:

- ograniczony executor;
- deadline;
- odłączenie wyniku;
- zamknięty commit gate;
- brak czekania bez końca;
- brak ponownego użycia uszkodzonego klienta.

### 16.4. SAPI

Timeout:

- zabija cały worker;
- zamyka pipe;
- odrzuca niepełny klip;
- nie usuwa wcześniejszych klipów;
- kolejna próba tworzy nowy worker.

### 16.5. FFmpeg

Każdy FFmpeg process:

- jest rejestrowany w run subprocess registry;
- ma timeout;
- dostaje terminate;
- po grace period dostaje kill;
- jest waitowany;
- nie zostawia procesu potomnego.

## 17. Resume state

### 17.1. Dwa niezależne stany

```text
workspace/tmp/<scope-id>/
├── tts/
│   ├── manifest.json
│   ├── manifest.corrupt.<timestamp>.json
│   └── clips/
│       ├── <request-id>-<fingerprint>.source
│       ├── <request-id>-<fingerprint>.wav
│       └── ...
└── audio/
    ├── manifest.json
    ├── narration/
    │   ├── <narration-fingerprint>.pcm
    │   └── narrator.wav
    └── output/
        └── output-manifest.json
```

Granice:

- `services/tts` posiada wyłącznie `tts/manifest.json` i surowe klipy syntezy;
- `services/audio` posiada `audio/manifest.json`, narrator i metadata finalnego miksu;
- pipeline nadaje oba katalogi jako kontrolowane zależności;
- TTS nie zna ścieżek `audio/`, źródłowego MKV ani produktu finalnego;
- Audio nie interpretuje manifestu TTS — dostaje zweryfikowane `TimedClip`.

### 17.2. `scope-id`

`scope_id` jest:

- nadawany przez caller;
- nieprzezroczysty dla TTS i Audio;
- bezpieczny jako pojedynczy segment ścieżki;
- stabilny w obrębie wznawianego zadania;
- krótki dla Windows path limits;
- odporny na kolizje;
- pozbawiony sekretów.

Pipeline może wyprowadzić `scope_id` ze swojej tożsamości źródła, ale publiczne API TTS
nie zna tego algorytmu ani jego składników. W szczególności TTS nie odczytuje canonical
source path, rozmiaru MKV, mtime ani identyfikatorów tracków.

### 17.3. Manifest TTS

Szkic:

```json
{
  "schema_version": 1,
  "scope_id": "opaque-episode-scope",
  "requests": {
    "spoken-17": {
      "request_id": "spoken-17",
      "text_hash": "sha256:...",
      "synthesis_fingerprint": "sha256:...",
      "clip_path": "clips/spoken-17-....wav",
      "clip_hash": "sha256:...",
      "duration_ms": 1412,
      "status": "complete"
    }
  }
}
```

Manifest TTS nie zawiera:

- source path;
- subtitle/audio stream identity;
- timingów;
- stylów albo source indexów napisów;
- narratora;
- original audio;
- mix gainu;
- codeca finalnego produktu;
- `FileOutcome`.

### 17.4. Synthesis fingerprint

Obejmuje:

- schema version;
- `scope_id`;
- `request_id`;
- gotowy tekst;
- chunk boundaries;
- engine ID;
- endpoint/model;
- resolved voice ID;
- engine-native rate;
- engine-native volume;
- engine-native pitch;
- voice settings;
- provider source format;
- wersję kontraktu syntezy;
- engine adapter version.

Nie obejmuje:

- timingu;
- post-process tempo;
- mix gain;
- output codec;
- original audio identity.

Ten fingerprint jest jedyną warstwą cache/resume należącą do TTS.

### 17.5. Manifest Audio

Audio zapisuje własne pochodne. Jego manifest może zawierać:

- `scope_id`;
- ordered clip fingerprints;
- fingerprint i ścieżkę narratora;
- fingerprint i ownership finalnego outputu;
- bezpieczną tożsamość oryginalnej ścieżki audio;
- config timeline, kanałów, gainu i codeca.

Audio nie zmienia ani nie rozszerza manifestu TTS.

### 17.6. Narration fingerprint

Należy do `services/audio`.

Obejmuje:

- ordered clip fingerprints;
- `TimedClip` timings i source order;
- post-process tempo;
- timeline policy;
- target PCM format;
- timeline algorithm version;
- clip normalization version.

Nie obejmuje:

- mix gain;
- original audio;
- output codec.

### 17.7. Mix fingerprint

Należy do `services/audio`.

Obejmuje:

- narration fingerprint;
- original audio identity;
- base gain;
- voice offset;
- original gain;
- amix settings;
- channel policy;
- output codec;
- container;
- bitrate/profile;
- mix algorithm version.

### 17.8. Invalidation matrix

| Zmiana | TTS synthesis | Audio narrator | Audio mix |
|---|---:|---:|---:|
| tekst | rebuild | rebuild | rebuild |
| engine | rebuild | rebuild | rebuild |
| model | rebuild | rebuild | rebuild |
| voice | rebuild | rebuild | rebuild |
| native rate | rebuild | rebuild | rebuild |
| voice settings | rebuild | rebuild | rebuild |
| post tempo | reuse | rebuild | rebuild |
| timing | reuse | rebuild | rebuild |
| base gain | reuse | reuse | rebuild |
| voice mix offset | reuse | reuse | rebuild |
| original gain | reuse | reuse | rebuild |
| codec | reuse | reuse | rebuild |
| bitrate | reuse | reuse | rebuild |
| original audio stream | reuse | reuse | rebuild |

### 17.9. Atomic commit klipu TTS

Kolejność:

1. provider zwraca dane;
2. dane trafiają do temp path;
3. clip validator wykonuje decode-check;
4. commit gate jest sprawdzany;
5. temp atomowo zastępuje deterministic clip path;
6. hash jest liczony;
7. manifest writer przyjmuje update;
8. manifest snapshot zapisuje się atomowo;
9. progress sink dostaje commit requestu.

Audio ma analogiczną, ale niezależną procedurę dla narratora i finalnego outputu.

### 17.10. Concurrent manifest writer

Każdy manifest ma własnego właściciela. Manifest TTS ma:

- jednego serializowanego writera;
- immutable update messages;
- atomic snapshots;
- brak read-modify-write w wielu workerach;
- test wielu jednoczesnych completions requestów.

### 17.11. Orphan clip

Po crashu pomiędzy clip replace a manifest replace:

1. scanner TTS znajduje deterministic orphan we własnym katalogu `clips/`;
2. sprawdza fingerprint w nazwie;
3. wykonuje decode-check;
4. liczy hash;
5. porównuje oczekiwany `request_id` i synthesis fingerprint;
6. przyjmuje klip do nowego manifestu;
7. nie wykonuje płatnego requestu.

TTS nie skanuje katalogu Audio ani plików obok MKV.

### 17.12. Corrupt manifest

Uszkodzony manifest:

- nie jest częściowo interpretowany;
- zostaje przeniesiony do diagnostycznej nazwy w katalogu jego właściciela;
- orphan clips są sprawdzane niezależnie;
- przypadkowe pliki nie są uznawane za cache;
- user dostaje warning.

### 17.13. Cleanup conflict

Obecny szeroki cleanup:

```text
safe_rmtree(workspace/tmp/<stem>)
```

nie może obejmować TTS ani Audio resume.

Docelowo pipeline rozdziela:

```text
workspace/tmp/<scope-id>/extract-scratch/
workspace/tmp/<scope-id>/tts/
workspace/tmp/<scope-id>/audio/
```

Extraction cleanup usuwa tylko własny scratch. Każdy serwis czyści wyłącznie artefakty,
których ownership potwierdza jego manifest.

## 18. ElevenBytes

### 18.1. Zakres engine

- proxy contract;
- `run6`;
- `run7`;
- Dallin;
- custom voices;
- async HTTP;
- typed mapping errors;
- brak własnego retry;
- rzeczywisty source format;
- availability probe.

### 18.2. Config

```python
@dataclass(frozen=True, slots=True)
class ElevenBytesConfig:
    endpoint_variant: Literal["run6", "run7"]
    voice_id: str
    timeout_s: float
    run7_settings: ElevenBytesV3Settings | None
```

### 18.3. Default

```text
run6
eleven_multilingual_v2
dallin
postprocess tempo 1.25
voice_mix_offset_db -2
```

### 18.4. `run6`

- stable;
- required live smoke;
- no exposed voice settings;
- provider defaults;
- no accidental v3 parameters;
- no fallback to `run7`.

### 18.5. `run7`

- experimental label;
- no default;
- stability;
- similarity boost;
- style;
- speaker boost;
- manual end-of-utterance evaluation;
- failure does not alter `run6`.

### 18.6. Request boundary

`api_backend.py`:

- builds request;
- sends once;
- returns response metadata;
- maps HTTP;
- does not retry;
- does not write resume;
- does not know timeline;
- does not know FileOutcome.

### 18.7. 403

ElevenBytes 403:

- is not `missing key`;
- can be transient proxy block;
- participates in limited retry;
- after exhaustion becomes provider-wide `service_unavailable`;
- opens recovery.

### 18.8. Custom voices

Stored fields:

```json
{
  "alias": "my_voice",
  "label": "My Voice",
  "voice_id": "provider-id"
}
```

Rules:

- alias non-empty;
- case-insensitive uniqueness;
- `dallin` reserved;
- voice ID non-empty;
- edit atomic;
- delete selected voice falls back to Dallin;
- fingerprint uses resolved voice ID.

### 18.9. Porting checklist

Ze starego kodu sprawdzić:

- exact URLs;
- headers;
- public request constants;
- payload field names;
- endpoint differences;
- accepted response;
- content type;
- status handling;
- timeout;
- maximum text;
- current voice ID.

Nie kopiować:

- sync loop thread;
- broad exception swallowing;
- internal retry;
- output directory API;
- arbitrary built-in voices;
- generic converter;
- pydub.

## 19. Oficjalne ElevenLabs

### 19.1. Dependency

Dodanie wyłącznie:

```bash
uv add elevenlabs
```

Przed dodaniem:

- przeczytać dependency workflow skill;
- sprawdzić wersję;
- sprawdzić Python 3.14;
- sprawdzić transitive dependencies;
- sprawdzić import time.

### 19.2. Secret

```text
ANISHIFT_ELEVENLABS_API_KEY
```

`.env.example`:

```dotenv
ANISHIFT_ELEVENLABS_API_KEY=
```

### 19.3. Availability

Bez klucza:

```text
missing_key
```

Z kluczem bez live probe:

```text
configured / network unchecked
```

Z live probe:

- ready;
- auth failed;
- offline;
- service unavailable.

### 19.4. Model

Fala 0 potwierdza:

- jakościowy default;
- szybki kandydat;
- dostępność dla konta;
- obsługę języka polskiego;
- output format compatibility.

Planowany default:

```text
eleven_multilingual_v2
```

Dozwolony custom model ID, jeżeli SDK/API to akceptuje.

### 19.5. Voice list

- pobierana z API;
- cache TTL;
- cache w `config/`, nie workspace;
- ręczny voice ID działa;
- brak voice list nie usuwa ręcznego ID;
- cache nie jest resume.

### 19.6. Voice settings

Walidowane:

- stability;
- similarity boost;
- style;
- speaker boost;
- speed, jeżeli model wspiera;
- API output format.

### 19.7. Output format mapping

Allowlist mapuje token API na:

- codec;
- container;
- sample rate;
- channels;
- expected content type.

Engine nie zakłada MP3.

### 19.8. SDK boundary

Jeżeli SDK jest sync:

- call trafia do kontrolowanego executor;
- scheduler nadal jest async;
- cancellation zamyka commit gate;
- SDK automatic retry jest wyłączony;
- late result nie zapisuje stanu.

### 19.9. Error mapping

| Provider | Domena |
|---|---|
| 400 | `TtsInputError` lub `TtsConfigError` |
| 401 | `TtsAuthError` |
| 403 | `TtsAuthError` lub permission fatal |
| 404 voice/model | `TtsVoiceError` / config fatal |
| 429 | `TtsRateLimitError` |
| timeout | `TtsTimeoutError` |
| connection | `TtsNetworkError` |
| 5xx | `TtsProviderUnavailableError` |
| empty audio | typed provider error |

## 20. Edge

### 20.1. Głosy

Minimum:

- `pl-PL-MarekNeural`;
- `pl-PL-ZofiaNeural`.

Lista pochodzi z usługi.

### 20.2. Parametry

- rate;
- volume;
- pitch;
- voice;
- output format patch.

### 20.3. Patch jakości

Patch:

1. lokalizuje package bez importu `Communicate`;
2. sprawdza wersję;
3. czyta dokładny plik;
4. rozpoznaje dokładny stary format;
5. rozpoznaje dokładny nowy format;
6. rozpoznaje bitrate constant;
7. odmawia nieznanego układu;
8. zapisuje temp;
9. waliduje temp;
10. wykonuje atomic replace;
11. ponownie czyta plik;
12. potwierdza oba pola;
13. dopiero wtedy importuje runtime Edge.

### 20.4. Patch values

Oczekiwane:

```text
audio-24khz-48kbitrate-mono-mp3
    ->
audio-24khz-96kbitrate-mono-mp3
```

Oraz:

```text
MP3_BITRATE_BPS = 48_000
    ->
MP3_BITRATE_BPS = 96_000
```

Dokładne symbole są sprawdzane dla przypiętej wersji.

### 20.5. Nieznana wersja

Nie wykonujemy blind replace.

Wynik:

```text
service_unavailable
```

Komunikat zawiera:

- wykrytą wersję;
- wspieraną wersję;
- instrukcję reinstall/update;
- brak tracebacku.

### 20.6. Read-only environment

- warning;
- brak cichego 48 kb/s fallback;
- engine unavailable;
- instrukcja naprawy;
- inne engine pozostają dostępne.

### 20.7. Live validation

Network smoke:

1. generuje krótki polski tekst;
2. zapisuje odpowiedź;
3. ffprobe sprawdza 24 kHz;
4. ffprobe sprawdza mono;
5. ffprobe sprawdza 96 kb/s;
6. pełny decode-check;
7. usuwa temp.

### 20.8. Czego nie kopiować z MangaShift

Nie kopiować runtime best-effort patchu, który:

- łapie błąd i kontynuuje;
- może zostać wykonany po imporcie;
- nie aktualizuje bitrate constant;
- nie blokuje 48 kb/s;
- nie wykonuje realnego smoke.

## 21. SAPI

### 21.1. Profile

```python
SAPI_PROFILES = {
    "zosia": SapiVoiceProfile(
        voice_name="Vocalizer Expressive Zosia Harpo 22kHz",
        architecture="x64",
    ),
    "agnieszka": SapiVoiceProfile(
        voice_name="IVONA 2 Agnieszka - polski głos żeński [22kHz]",
        architecture="x86",
    ),
}
```

Nazwy są dokładnymi wartościami potwierdzonymi przez probe x64/x86.

### 21.2. Host x64

Używa systemowego 64-bit PowerShell.

Ścieżka jest rozwiązywana jawnie.

### 21.3. Host x86

Używa:

```text
%WINDIR%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
```

Ścieżka:

- jest rozwiązywana bez niezaufanego shell expansion;
- musi istnieć;
- jest częścią availability;
- nie jest pobierana.

### 21.4. Worker asset

`sapi_worker.ps1` jest package assetem.

Test wheel potwierdza obecność.

Worker:

- inicjalizuje COM raz;
- wybiera voice raz;
- czyta JSON Lines z stdin;
- pisze JSON Lines na stdout;
- stderr służy tylko do diagnostyki;
- jeden request daje jedną odpowiedź;
- EOF kończy worker.

### 21.5. Request protocol

```json
{
  "protocol_version": 1,
  "request_id": "scope:request:attempt",
  "operation": "synthesize",
  "voice_name": "IVONA 2 Agnieszka - polski głos żeński [22kHz]",
  "text": "Cześć.",
  "output_path": "C:/workspace/tmp/.../clip.tmp.wav"
}
```

Tekst nie jest interpolowany do komendy.

### 21.6. Response protocol

Success:

```json
{
  "protocol_version": 1,
  "request_id": "scope:request:attempt",
  "ok": true,
  "output_path": "C:/workspace/tmp/.../clip.tmp.wav"
}
```

Failure:

```json
{
  "protocol_version": 1,
  "request_id": "scope:request:attempt",
  "ok": false,
  "error_code": "SAPI_SPEAK_FAILED",
  "message": "Safe message"
}
```

### 21.7. Path validation

Controller przekazuje wyłącznie path:

- pod bieżącym TTS tmp;
- z oczekiwanym suffix;
- bez traversal;
- po resolve pod workspace;
- nieistniejący albo temp-owned.

### 21.8. Worker controller

`worker.py` odpowiada za:

- spawn;
- stdin writer;
- stdout reader;
- stderr drain;
- request correlation;
- timeout;
- process exit;
- restart;
- close;
- kill;
- zero orphan process.

### 21.9. Concurrency

SAPI:

```text
max_concurrency = 1
```

Jeden worker obsługuje requesty sekwencyjnie.

### 21.10. Timeout/restart

Scenariusz:

1. request A kończy się poprawnie;
2. manifest przyjmuje request A;
3. request B blokuje worker;
4. timeout zabija worker;
5. B dostaje transient failure;
6. scheduler planuje retry;
7. nowy worker startuje;
8. A pozostaje resume hit;
9. B wykonuje się ponownie;
10. request C idzie dalej.

### 21.11. Modal licencyjny

Zwykły doctor:

- nie wykonuje Speak;
- nie wywołuje modala;
- tylko listuje voice.

`doctor --live`:

- ma timeout;
- uruchamia osobny worker;
- wymusza kill po timeout;
- zgłasza broken backend;
- nie blokuje głównego CLI.

### 21.12. Voice enumeration

Enumeration osobno:

- x64;
- x86.

Wynik przechowuje architecture.

Ten sam display name w dwóch hostach pozostaje rozróżnialny.

### 21.13. Walidacja WAV

Success wymaga:

- path istnieje;
- size > header-only;
- ffprobe działa;
- pełny decode działa;
- duration > 0;
- channels > 0;
- sample rate > 0.

### 21.14. Odrzucone backendy

Balcon:

- identyczny dźwięk;
- większy narzut;
- dodatkowa binarka;
- brak użycia.

pyttsx3:

- zawiesił test;
- nie daje izolacji;
- brak użycia.

## 22. Audio domain

### 22.1. Odpowiedzialność

Audio domain:

- probe;
- validate;
- normalize;
- per-clip tempo;
- timeline;
- narrator WAV;
- mix;
- encode;
- final decode-check;
- output ownership.

Nie wykonuje:

- TTS request;
- retry providera;
- klasyfikacji napisów;
- translation;
- CLI rendering.

### 22.2. `AudioProbe`

```python
@dataclass(frozen=True, slots=True)
class AudioProbe:
    path: Path
    codec_name: str
    format_name: str
    sample_rate: int
    channels: int
    channel_layout: str
    duration_ms: int
    bit_rate: int | None
```

### 22.3. `AudioCodecProfile`

```python
class AudioCodecProfile(StrEnum):
    MP3 = "mp3"
    WAV = "wav"
    EAC3 = "eac3"
    OPUS = "opus"
    FLAC = "flac"
    AAC = "aac"
```

### 22.4. Mapping produktu

| Profile | Encoder | Container | Extension |
|---|---|---|---|
| MP3 | `libmp3lame` albo dostępny MP3 encoder | MP3 | `.mp3` |
| WAV | `pcm_s16le` | WAV/RF64 | `.wav` |
| E-AC-3 | `eac3` | E-AC-3 | `.eac3` |
| Opus | `libopus` | Ogg Opus | `.opus` |
| FLAC | `flac` | FLAC | `.flac` |
| AAC | `aac` | M4A/MP4 audio | `.m4a` |

Dokładny dostępny encoder potwierdza setup/doctor.

### 22.5. `ffprobe`

Probe command:

```text
ffprobe
-v error
-show_streams
-show_format
-of json
<path>
```

Parser:

- nie polega na human text;
- waliduje JSON;
- wybiera audio stream;
- odrzuca brak audio;
- typuje brak duration;
- nie używa float bez tolerancji.

### 22.6. Full decode-check

```text
ffmpeg
-v error
-i <path>
-map 0:a:0
-f null
-
```

Success wymaga return code 0.

### 22.7. Clip normalization

Target:

```text
PCM S16LE
mono
48 kHz
```

Wyjątek:

- target może zostać jawnie zmieniony po probe źródła/codec;
- wartość trafia do narration fingerprint.

### 22.8. Neutral fast path

Jeżeli klip jest już:

- PCM S16LE;
- mono;
- target sample rate;
- tempo `1.0`;

to:

- nie uruchamiamy zbędnego transcodingu;
- validator metadata jest używany ponownie;
- klip może wejść bezpośrednio do timeline reader.

### 22.9. Tempo per clip

Filtr:

```text
atempo=<resolved>
```

Jeżeli tempo wymaga chain:

```text
atempo=2.0,atempo=1.25
```

Algorytm buduje chain deterministycznie.

### 22.10. Nie tempo całego narratora

Zakazane:

```text
narrator.wav -> atempo
```

Powód:

- kompresuje ciszę;
- przesuwa timing;
- łamie start_ms;
- zmienia drift.

### 22.11. Montaż bez setek procesów

Strategia v1:

1. provider clip zostaje zwalidowany;
2. tylko wymagające klipy są normalizowane;
3. normalizacja jest cache'owana przez narration fingerprint;
4. subprocess concurrency jest bounded;
5. PCM frames są składane streamingowo in-process;
6. nie ładuje się całego odcinka do RAM;
7. jeden końcowy FFmpeg opakowuje raw PCM jako WAV/RF64.

### 22.12. Raw PCM timeline

Timeline writer:

- otwiera raw PCM scratch;
- dopisuje zero frames dla ciszy;
- dopisuje frames klipu;
- nie seekuje po całym pliku bez potrzeby;
- raportuje written frames;
- trzyma stały sample format;
- po zakończeniu zamyka plik;
- FFmpeg tworzy narrator WAV z `-rf64 auto`.

### 22.13. RF64

Command sketch:

```text
ffmpeg
-f s16le
-ar 48000
-ac 1
-i narrator.pcm
-c:a pcm_s16le
-rf64 auto
narrator.tmp.wav
```

Wynik jest atomowo zatwierdzany.

## 23. Timeline

### 23.1. Input order

Eventy sortowane stabilnie:

```python
sorted(events, key=lambda event: (event.start_ms, event.source_index))
```

### 23.2. Planowany start

```text
planned_start = event.start_ms
```

### 23.3. Rzeczywisty start

```text
actual_start = max(planned_start, previous_actual_end)
```

### 23.4. Drift

```text
drift_ms = actual_start - planned_start
```

### 23.5. Rzeczywisty koniec

```text
actual_end = actual_start + normalized_clip_duration
```

### 23.6. Odzyskanie driftu

Jeżeli następny planned start jest późniejszy niż previous actual end:

```text
actual_start = planned_start
drift = 0
```

Naturalna cisza przywraca oryginalną oś.

### 23.7. Timeline record

```python
@dataclass(frozen=True, slots=True)
class TimelinePlacement:
    source_index: int
    planned_start_ms: int
    planned_end_ms: int
    actual_start_ms: int
    actual_end_ms: int
    drift_ms: int
    reason: PlacementReason
```

### 23.8. Overlapping subtitle group

V1:

- zachowuje oba spoken;
- czyta je sekwencyjnie;
- raportuje drift;
- zapisuje overlap group metadata;
- nie przenosi eventu do displayed.

### 23.9. Metryki przyszłego schedulera

Zbieramy:

- overlap group ID;
- layer;
- position;
- style;
- planned start/end;
- actual start/end;
- drift;
- reason;
- clip duration;
- window duration.

Nie podejmujemy jeszcze decyzji displayed fallback.

### 23.10. Empty file

Jeżeli po preparation nie ma eventów:

- `skipped_no_spoken`;
- warning;
- brak narrator WAV;
- brak mixed sidecar;
- progress przechodzi do zakończonego skip;
- nie jest provider failure.

## 24. Channel mapping

### 24.1. Bramka Fali 0

Dokładne współczynniki macierzy są ustalane przed produkcyjnym kodem.

Wymagane fixture:

- mono impulse;
- stereo left impulse;
- stereo right impulse;
- 5.1 per-channel impulses;
- 7.1 per-channel impulses;
- narrator center impulse.

### 24.2. Mono

Source mono + narrator mono:

- output mono;
- oba wejścia jawnie mono;
- brak stereo upmix.

### 24.3. Stereo

Narrator jest phantom center.

Macierz używa equal-power split.

Planowany punkt startowy:

```text
FL = original.FL + narrator * 0.70710678
FR = original.FR + narrator * 0.70710678
```

Współczynnik wymaga fixture i odsłuchu przed zamrożeniem.

### 24.4. 5.1

Narrator trafia do `FC`.

Pozostałe kanały oryginału zachowują mapowanie.

Nie duplikujemy narratora do surround.

### 24.5. 7.1

Jeżeli codec wspiera:

- zachować 7.1;
- narrator do FC.

Jeżeli codec nie wspiera:

- jawny downmix;
- warning;
- raport.

### 24.6. E-AC-3

Maksymalnie:

```text
5.1
```

7.1 wymaga jawnego downmixu do 5.1.

### 24.7. MP3

Maksymalnie:

```text
stereo
```

5.1/7.1 wymaga jawnego downmixu do stereo.

### 24.8. AAC, Opus i FLAC

Nie zakładamy capabilities z pamięci.

Fala 0:

- sprawdza lokalny encoder;
- generuje każdy layout;
- wykonuje ffprobe;
- wykonuje decode-check;
- zapisuje potwierdzoną matrix.

### 24.9. Zakaz niejawnego mappingu

Zakazane:

```text
-ac 2
```

jako jedyne rozstrzygnięcie surround.

Dozwolone:

- jawny `pan`;
- jawny `channelmap`;
- jawne coefficients;
- test per channel.

### 24.10. Zamrożone macierze v1

Narrator:

```text
mono:
FC = narrator

stereo:
FL = 0.70710678 * narrator
FR = 0.70710678 * narrator

5.1 / 5.1(side) / 7.1:
FC = narrator
all other channels = 0
```

E-AC-3 7.1 do 5.1(side):

```text
FL  = FL
FR  = FR
FC  = FC
LFE = LFE
SL  = 0.70710678 * SL + 0.70710678 * BL
SR  = 0.70710678 * SR + 0.70710678 * BR
```

MP3 surround do stereo używa przykładu z dokumentacji FFmpeg:

```text
FL < FL + 0.5*FC + 0.6*BL + 0.6*SL
FR < FR + 0.5*FC + 0.6*BR + 0.6*SR
```

LFE nie trafia do stereo. Narrator jest mapowany po downmixie źródła. Każda macierz ma
fixture impulse per kanał, `ffprobe` layout check i decode-check.

## 25. Miks i output

### 25.1. Dwa wejścia

Input 0:

- oryginalne audio.

Input 1:

- narrator.

Kolejność wejść nie zmienia semantyki.

### 25.2. Gain

Original:

```text
original_gain_db = 0.0
```

Narrator:

```text
narrator_gain_db =
    narrator_mix_base_gain_db
    + voice_mix_offset_db
```

### 25.3. `amix`

Jawne:

```text
amix=inputs=2:
duration=longest:
dropout_transition=2:
normalize=true
```

### 25.4. Bez oryginalnego audio

Nie używamy `amix`.

Nie używamy:

- base +7 dB;
- voice offset;
- original gain.

Narrator jest tylko kodowany do output profile.

### 25.5. Długość

Expected:

```text
abs(output_duration - max(original_duration, narrator_duration))
    <= codec_tolerance
```

Tolerancja jest codec-specific.

### 25.6. Output path

```python
def mixed_audio_path(source: Path, profile: AudioCodecProfile) -> Path:
    ...
```

Mapping:

```text
Episode.mkv -> Episode.eac3
Episode.mkv -> Episode.mp3
Episode.mkv -> Episode.wav
Episode.mkv -> Episode.opus
Episode.mkv -> Episode.flac
Episode.mkv -> Episode.m4a
```

### 25.7. Atomic output

1. command zapisuje do temp;
2. return code jest sprawdzany;
3. file size jest sprawdzany;
4. ffprobe jest wykonywany;
5. full decode-check;
6. codec/layout/rate/duration są porównywane;
7. ownership/collision gate;
8. atomic replace;
9. output manifest commit.

### 25.8. Collision

Jeżeli `{stem}.<codec>` istnieje:

- manifest potwierdza własność i fingerprint — można zastąpić po walidacji nowego;
- manifest potwierdza identyczny poprawny fingerprint — resume output hit;
- manifest nie potwierdza własności — typed collision;
- user wybiera overwrite/finish/settings w przyszłym UI;
- v1 nie usuwa obcego pliku.

### 25.9. Zachowanie innych formatów

Audio service dotyka wyłącznie docelowego output path.

Nie globuje:

```text
{stem}.*
```

Nie usuwa:

- `.eac3` przy generowaniu `.flac`;
- `.mp3` przy generowaniu `.m4a`;
- plików usera.

### 25.10. FFmpeg stderr

Error przechowuje:

- operation;
- return code;
- bezpieczny tail stderr;
- input paths;
- temp output path;
- suggestion.

Nie przechowuje:

- pełnego binary dump;
- env;
- sekretów;
- signed URL.

## 26. Integracja z obecnym pipeline

### 26.1. Stan wejściowy

Obecny runner:

- odkrywa MKV i TXT;
- sortuje wejścia przez `os_sorted`;
- tworzy `_MkvState`;
- ekstrahuje MKV równolegle;
- tłumaczy non-LLM sekwencyjnie;
- tłumaczy LLM przez osobną kolejkę;
- kończy po zapisaniu produktów napisów;
- używa `FileOutcome.audio_path` dla źródłowego audio;
- nie rozróżnia narratora i finalnego miksu;
- używa fazowych progress displays.

Etap 6 nie może dopisać TTS tylko na końcu `run_pipeline`.

Taki wariant złamałby D1.

### 26.2. Nowe znaczenia ścieżek

`FileOutcome` dostaje:

```python
source_audio_path: Path | None
narrator_path: Path | None
mixed_audio_path: Path | None
```

Dotychczasowe `audio_path`:

- jest migrowane do `source_audio_path`;
- nie pozostaje jako niejednoznaczny alias;
- wszystkie testy ekstrakcji są aktualizowane;
- etap 7 użyje `mixed_audio_path`.

### 26.3. Nowe kroki błędów

`StepName` dostaje:

```text
tts
audio
```

Znaczenia:

- `tts` — API contract validation, availability, provider, resume, synthesis;
- `audio` — normalize, timeline, narrator, mix, codec, validation.

### 26.4. `_MkvState`

Stan roboczy musi przechowywać:

- outcome;
- split;
- subtitle kind;
- source audio identity;
- spoken readiness;
- pipeline-owned narration plan (`request_id -> timing/source order`);
- TTS enqueue generation;
- `SpeechBatchResult`;
- `AudioRenderResult`;
- source order rank.

Nie powinien przechowywać:

- provider client;
- event loop;
- SAPI worker;
- manifest writer.

### 26.5. Spoken-ready callback

Nowy callback:

```python
type SpokenReadyHandler = Callable[[Path, NarrationBatch], None]
```

`NarrationBatch` jest typem orkiestracyjnym w `pipeline/narration.py`:

```python
@dataclass(frozen=True, slots=True)
class NarrationItem:
    request: SpeechRequest
    start_ms: int
    end_ms: int
    source_order: int

@dataclass(frozen=True, slots=True)
class NarrationBatch:
    speech: SpeechBatch
    items: tuple[NarrationItem, ...]
```

`NarrationBatch` nie trafia do `services/tts`. Runtime przekazuje TTS wyłącznie
`batch.speech`, a po wyniku łączy klipy z `items` i buduje `TimedClip` dla audio.

Jest wywoływany:

- dla źródła polskiego po udanym split;
- dla źródła obcego po udanym translation i zapisie produktów;
- dokładnie raz per generation;
- nigdy dla TXT bez timeline;
- nigdy dla failed translation.

### 26.6. Źródło polskie

Przepływ:

```text
extract
-> split
-> write Polish products
-> pipeline maps SubtitleSplit.spoken to NarrationBatch
-> pass only SpeechBatch to TTS API
-> enqueue TTS
```

Nie wymaga `FileTranslation`.

### 26.7. Źródło obce

Przepływ:

```text
extract
-> split
-> translate
-> validate translation
-> write translated products
-> pipeline strict-zips source timings with FileTranslation.spoken
-> build NarrationBatch
-> pass only SpeechBatch to TTS API
-> enqueue TTS
```

### 26.8. LLM translation

LLM queue po zakończeniu pliku:

- aktualizuje `FileOutcome`;
- wywołuje spoken-ready callback;
- nie czeka na inne tłumaczenia;
- nie tworzy TTS client;
- nie zmienia TTS circuit state.

### 26.9. Google i DeepL

Po `_translate_one`:

- jeśli success — enqueue;
- jeśli failure — brak enqueue;
- następny plik może być tłumaczony;
- TTS działa równolegle w swoim runtime.

Pełny provider-wide recovery Google/DeepL nie jest dokładany po cichu.

### 26.10. TTS runtime start

Runtime startuje przed rozpoczęciem ekstrakcji.

Powód:

- polski plik może być gotowy szybko;
- kolejka musi istnieć przed callbackiem;
- jeden run ma jeden lifecycle.

Runtime jest adapterem/composition, nie drugim pipeline:

- nie parsuje napisów;
- nie klasyfikuje spoken/displayed;
- nie tłumaczy;
- nie posiada własnego `_MkvState`;
- nie ukrywa `AudioService` wewnątrz `TtsService`.

### 26.11. TTS runtime close

Producer close następuje po:

- zakończeniu ekstrakcji wszystkich MKV;
- zakończeniu translation wszystkich możliwych MKV;
- oznaczeniu TXT jako no-timeline;
- braku dalszych spoken-ready callbacków.

Runtime czeka na:

- aktywne requesty;
- retry;
- albo recovery/cancel.

Po zakończeniu `SpeechBatch` pipeline może od razu uruchomić osobny `AudioService` dla
tego batcha; nie czeka na syntezę wszystkich odcinków.

### 26.12. Wyniki

Po zakończeniu TTS i audio:

- `SpeechBatchResult` jest mapowany po `scope_id` do właściwego `_MkvState`;
- pipeline buduje `TimedClip` z zachowanego `NarrationBatch`;
- `AudioRenderResult` jest mapowany osobno;
- `mixed_audio_path` trafia do outcome;
- narrator path trafia diagnostycznie;
- stats trafiają do outcome;
- TTS failure nie kasuje subtitle outputs;
- audio failure nie kasuje clips/resume.

### 26.13. Status pliku

`done` w etapie 6 wymaga:

- poprawnych produktów napisów;
- jeżeli istnieją spoken events — poprawnego mixed audio;
- jeżeli brak spoken — jawnego skip bez mylącego audio;
- braku failure.

Plik może być:

- done with audio;
- done/skipped_no_spoken;
- failed at translation;
- failed at tts;
- failed at audio;
- cancelled;
- not_processed.

### 26.14. Izolacja ukończonych plików

Po finalnym output commit:

- wynik pliku nie jest cofany;
- provider-wide failure późniejszego pliku nie usuwa go;
- recovery nie regeneruje go bez jawnego rerun;
- raport zachowuje jego stats.

### 26.15. TXT

TXT:

- nadal może przejść translation;
- nadal może utworzyć SRT;
- nie trafia do TTS;
- dostaje `no_media_timeline`;
- nie jest błędem całego pipeline;
- nie tworzy audio.

### 26.16. Cleanup ekstrakcji

Runner nie może używać stemu jako jedynej tożsamości stanu etapu.

Przed ekstrakcją:

- rozwiązuje opaque `scope_id`;
- czyści `extract-scratch`;
- zachowuje osobne katalogi `tts` i `audio`;
- nie globuje całego scope root.

### 26.17. Pipeline pseudocode

```python
def run_pipeline(...) -> PipelineReport:
    files = stable_natural_snapshot(...)
    cancel = CancellationController()
    progress = PipelineProgress(...)

    with PipelineTtsRuntime(...) as tts:
        try:
            states = extract_and_publish_polish(
                files,
                on_spoken_ready=tts.put,
                cancel=cancel,
            )
            translate_and_publish_foreign(
                states,
                on_spoken_ready=tts.put,
                cancel=cancel,
            )
        finally:
            tts.close_input()

        tts_results = tts.wait()
        apply_tts_results(states, tts_results)

    return ordered_report(states)
```

Pseudocode pokazuje ownership.

Nie narzuca dokładnej składni implementacji.

### 26.18. Dlaczego osobny `tts_runtime.py`

`pipeline/tts_runtime.py`:

- mapuje settings/env na configs;
- buduje dependencies;
- otwiera service;
- wywołuje `service.synthesize(batch)` dla batchy pobranych z kolejki pipeline;
- odbiera `SpeechBatchResult`;
- nie implementuje engine;
- nie implementuje timeline;
- nie implementuje FFmpeg filters.

To odpowiednik composition adaptera z etapu 5.

### 26.19. Dlaczego osobny `tts_queue.py`

`pipeline/tts_queue.py`:

- thread-safe stream pipeline `NarrationBatch`;
- close producer;
- przekazany `batch_rank`;
- bridge callbacków;
- not-processed mapping;
- recovery handoff.

Request-level priority pozostaje w domain scheduler.

Pipeline queue nie dubluje retry requestów.

## 27. Wspólne recovery

### 27.1. Problem wejściowy

Obecnie LLM ma:

- provider-wide circuit;
- `settings`;
- `finish`;
- kolejkę;
- natural order;
- zachowanie ukończonych plików.

TTS potrzebuje tej samej semantyki.

Nie powinny powstać dwa różne interfejsy decyzji.

### 27.2. Wspólny kontrakt

```python
class RecoveryAction(StrEnum):
    RETRY = "retry"
    SETTINGS = "settings"
    FINISH = "finish"
```

```python
@dataclass(frozen=True, slots=True)
class RecoveryContext:
    domain: RecoveryDomain
    error: ErrorContext
    completed_files: tuple[Path, ...]
    failed_files: tuple[Path, ...]
    pending_files: tuple[Path, ...]
```

### 27.3. Wspólna semantyka

`retry`:

- nowa seria prób;
- aktualne settings;
- identyczny fingerprint używa resume;
- gotowe pliki pozostają.

`settings`:

- otwiera panel;
- po zamknięciu przebudowuje runtime config;
- porównuje fingerprint;
- nie miesza engine/voice/model w jednym pliku.

`finish`:

- zachowuje completed;
- zachowuje resume;
- pending oznacza `not_processed`;
- wraca do promptu.

### 27.4. Stan domenowy pozostaje osobny

Wspólne:

- action enum;
- interaction protocol;
- render prompt;
- completed/pending semantics.

Osobne:

- LLM provider state;
- TTS provider state;
- translation fingerprint;
- synthesis fingerprint;
- resume manifest.

### 27.5. Retry TTS

Retry bez zmiany settings:

- wykorzystuje clips z manifestu;
- nie wysyła completed requestów;
- retry failed request ma priority;
- po provider success circuit może się zamknąć;
- nie tworzy nowego voice mix.

### 27.6. Zmiana engine

Jeżeli user zmienia:

- engine;
- provider model;
- voice;
- native synthesis settings;

to:

- cały nieukończony plik dostaje nową synthesis generation;
- stare klipy nie są używane;
- stary stan pozostaje;
- completed file nie jest zmieniany.

### 27.7. Zmiana post tempo

Nie powtarza synthesis.

Przebudowuje:

- normalized clips;
- narrator;
- mix.

### 27.8. Zmiana codeca

Nie powtarza:

- synthesis;
- narrator.

Przebudowuje:

- mix/output.

### 27.9. Zmiana key

Po edycji `.env`:

- settings object jest przebudowany;
- availability jest odświeżone;
- nowy runtime dostaje nowy secret;
- secret nie trafia do context repr;
- poprzedni client jest zamknięty.

## 28. User settings

### 28.1. Problem starego schema

Obecne:

```text
tts_engine = edge
voice = pl-PL-MarekNeural
tempo = 1.0
volume = 100
```

Problemy:

- default engine jest nieaktualny;
- jedno voice dla wszystkich engine;
- jedno tempo dla wszystkich voices;
- volume `0–100` nie jest dB;
- brak codec;
- brak model/variant;
- brak concurrency;
- brak retry;
- brak native settings;
- brak mix settings;
- brak per-voice profiles.

### 28.2. Nowe top-level fields

Plan:

```python
tts_engine: str = "elevenbytes"
tts_provider_model_id: str = "run6"
tts_voice_id: str = "dallin"
tts_max_retries: int = 3
tts_output_profile: str = "eac3"
tts_output_bitrate: str | None = None
tts_timeline_policy: str = "serialize"
narrator_mix_base_gain_db: float = 7.0
original_gain_db: float = 0.0
tts_voice_profiles: dict[str, TtsVoiceProfileSettings]
elevenbytes_custom_voices: list[CustomVoiceSetting]
```

### 28.3. `TtsVoiceProfileSettings`

```python
@dataclass(slots=True)
class TtsVoiceProfileSettings:
    postprocess_tempo: float = 1.0
    voice_mix_offset_db: float = 0.0
    concurrency: int | None = None
    native_rate: str | float | None = None
    native_volume: str | float | None = None
    native_pitch: str | float | None = None
    engine_options: dict[str, JsonScalar] = field(default_factory=dict)
```

### 28.4. Stabilny profile key

```text
<engine_id>:<resolved_voice_id>
```

Przykład:

```text
elevenbytes:alFofuDn3cOwyoz1i44T
sapi:IVONA 2 Agnieszka - polski głos żeński [22kHz]@x86
edge:pl-PL-MarekNeural
```

### 28.5. Defaults profili

ElevenBytes Dallin:

```text
postprocess_tempo = 1.25
voice_mix_offset_db = -2.0
```

SAPI Agnieszka:

```text
native_rate = 5
native_volume = 65
postprocess_tempo = 1.0
voice_mix_offset_db = +2.0
```

SAPI Zosia:

```text
native_rate = 200 WPM
native_volume = 0.7
postprocess_tempo = 1.0
voice_mix_offset_db = 0.0
```

Adapter bezpośredniego SAPI zachowuje user-facing skalę starego profilu Zosi:
`200 WPM -> SpVoice.Rate=2`, `0.7 -> SpVoice.Volume=70`. Profil Agnieszki jest już
w natywnej skali SAPI i pozostaje `Rate=5 / Volume=65`.

Edge Marek i Zofia:

```text
native_rate = "+40%"
native_volume = "+0%"
postprocess_tempo = 1.0
voice_mix_offset_db = 0.0
```

Inne profile:

```text
postprocess_tempo = 1.0
voice_mix_offset_db = 0.0
```

### 28.6. Migracja starych pól

Nie migrujemy znaczeniowo:

- `tempo=1.85`;
- `volume=60`;
- dowolnego `volume 0–100` do dB.

Loader:

- ignoruje legacy `tempo` dla TTS profile;
- ignoruje legacy `volume` dla mix;
- zachowuje unrelated settings;
- tworzy nowe default profiles;
- może pozostawić stare keys w pliku do kolejnego save;
- następny save zapisuje nowy schema.

### 28.7. Schema version

`settings.json` dostaje:

```json
{
  "schema_version": 2
}
```

Migracja:

- v1 -> v2;
- unknown future version -> safe defaults + warning;
- corrupt file -> defaults;
- unknown keys -> ignored/preserved zgodnie z obecną polityką;
- test roundtrip.

### 28.8. Codec-specific bitrate

Widoczne dla:

- MP3;
- E-AC-3;
- Opus;
- AAC.

Niewidoczne dla:

- WAV;
- FLAC.

FLAC może mieć compression level.

Nie nazywamy go bitrate.

### 28.9. Engine-specific visible fields

ElevenBytes:

- endpoint variant;
- voice;
- custom voices;
- concurrency;
- run7 voice settings tylko przy run7;
- tempo;
- mix offset.

ElevenLabs:

- API key status;
- model;
- voice;
- custom voice ID;
- voice settings;
- API output format;
- concurrency;
- tempo;
- mix offset.

Edge:

- voice;
- rate;
- pitch;
- volume;
- concurrency;
- tempo;
- mix offset.

SAPI:

- voice;
- architecture read-only;
- native rate;
- native volume;
- tempo;
- mix offset;
- concurrency read-only 1.

### 28.10. Advanced native rate

Rekomendacja planu:

- przechowywać w schema;
- pokazywać w advanced engine options;
- default neutralny;
- nie mieszać z post-process tempo;
- nie promować w podstawowym widoku v1.

Ostateczne odsłonięcie jest bramką HITL po smoke.

## 29. Env settings i edycja klucza

### 29.1. Nowe pole

`Settings`:

```python
elevenlabs_api_key: str = ""
```

Prefix Pydantic:

```text
ANISHIFT_ELEVENLABS_API_KEY
```

### 29.2. Maskowanie

Secret:

- `repr=False` lub `SecretStr`;
- brak panel echo;
- brak terminal print;
- brak error details;
- brak report;
- brak logger.

### 29.3. Edycja `.env`

Wspólny helper powinien:

- odczytać bytes;
- wykryć newline;
- zachować komentarze;
- zachować unrelated lines;
- zastąpić tylko exact key;
- dodać key, jeśli brak;
- usunąć albo wyczyścić key jawnie;
- zapisać temp;
- fsync tam, gdzie praktyczne;
- atomic replace;
- zachować UTF-8.

### 29.4. Precedence

Po zapisie:

- process env ma najwyższe istniejące pierwszeństwo;
- `.env` nie nadpisuje process env przez `override=False`;
- runtime Settings jest jawnie rekonstruowany;
- panel pokazuje configured, nie wartość;
- test rozróżnia process env i file env.

### 29.5. Zakres helpera

Jeżeli istnieje już helper z etapu 5:

- rozszerzyć go;
- nie tworzyć drugiego edytora `.env`.

Jeżeli nie istnieje:

- dodać mały config helper;
- nie umieszczać go w TTS engine;
- objąć testami.

## 30. Settings panel

### 30.1. Engine picker

Lista pochodzi z registry.

Każdy wpis pokazuje availability.

Przykład:

```text
elevenbytes  ready
elevenlabs   missing key
edge         ready
sapi         missing voice
```

### 30.2. Missing key

Na ElevenLabs:

- Enter otwiera masked input;
- save zapisuje `.env`;
- cancel nic nie zmienia;
- pusty input nie wyświetla starego key;
- availability jest odświeżone.

### 30.3. Voice picker

Lista:

- built-in;
- remote cached;
- SAPI x64/x86;
- custom IDs;
- custom ElevenBytes.

Nieznany persisted voice:

- pozostaje widoczny jako custom;
- nie jest resetowany, jeżeli engine dopuszcza custom ID;
- jest resetowany do defaultu, jeżeli engine tego nie dopuszcza.

### 30.4. Per-voice profile

Po zmianie voice:

1. zapisz bieżący profile;
2. rozwiąż nowy profile key;
3. załaduj istniejący profile;
4. albo utwórz neutralny;
5. odśwież visible fields.

### 30.5. Custom ElevenBytes commands

Panel v1 potrzebuje operacji:

- add;
- edit;
- remove.

Dokładny UX:

- może być modalny input;
- może być osobną komendą;
- nie wymaga graficznego UI;
- nie może edytować built-in Dallin.

### 30.6. Output panel

Pola:

- format;
- bitrate/profile;
- original gain;
- narrator base gain;
- timeline policy read-only/default serialize;
- debug artifacts;
- resume behavior read-only.

### 30.7. Jednostki

Etykiety jawnie pokazują:

- `×` dla tempo;
- `dB` dla gain;
- `%` tylko dla engine-native API używającego procentów;
- `kb/s` dla bitrate;
- `s` dla timeout;
- integer dla concurrency/retry.

## 31. Progress UI

### 31.1. Jeden wiersz

Każdy input file dostaje jeden task ID.

Task ID żyje przez:

```text
extracting
translating
already Polish
synthesizing
audio
done
failed
cancelled
not processed
```

### 31.2. Brak dodatkowego wiersza TTS

Zakazane:

```text
Episode.mkv extracting
Translating Episode.mkv
Synthesizing Episode.mkv
```

Wymagane:

```text
Episode.mkv [ten sam task id] synthesizing 63%
```

### 31.3. TTS procent

```text
committed required events / total required events
```

Do committed zaliczamy:

- nową syntezę;
- resume hit.

Nie zaliczamy:

- rozpoczętego requestu;
- retry attempt;
- temp file;
- late result po cancel.

### 31.4. Skipped

`skipped_non_speech`:

- nie wchodzi do mianownika required;
- jest liczone osobno;
- nie blokuje 100%.

### 31.5. Audio phase

Montaż jest zwykle jednym procesem bez naturalnego procentu.

Pokazuje:

- spinner;
- phase `audio`;
- elapsed;
- opcjonalny substatus:
  - normalize;
  - timeline;
  - mix;
  - verify.

### 31.6. Engine/voice label

Zwięzły przykład:

```text
elevenbytes/run6 · Dallin
sapi · Agnieszka
edge · Marek
```

### 31.7. Szerokość nazwy

Używamy istniejącej większej szerokości nazwy.

Nie cofamy poprzedniej poprawki.

### 31.8. `rich_console`

Plan zakłada użycie istniejącego komponentu progress.

Nie modyfikujemy `anishift/utils/rich_console` bez:

1. dowodu, że publiczny kontrakt nie wystarcza;
2. poinformowania usera;
3. osobnego zakresu i testu.

Preferowana zmiana jest w `cli/pipeline_ui.py`.

### 31.9. Thread safety

Progress callback:

- jest serializowany;
- ignoruje callback po close;
- nie renderuje z worker thread bez bridge;
- jedno Ctrl+C nie wywołuje deadlock;
- test używa Event/Barrier.

### 31.10. Summary

Przykład:

```text
Done 5 · Failed 1 · Not processed 0 · Cancelled 0
TTS elevenbytes/run6 · Dallin
Events 1640 · synthesized 1200 · resumed 420 · skipped 20 · failed 0
Requests 1200 · retries 3
Drift max 1840 ms · total 12920 ms
TTS 04:21 · audio 00:18
```

Każdy wynik pokazuje final path.

## 32. Bezpieczeństwo subprocessów

### 32.1. Argument list

FFmpeg/ffprobe:

```python
subprocess.Popen([binary, "-v", "error", ...])
```

Zakazane:

```python
subprocess.Popen(f"{binary} ...", shell=True)
```

### 32.2. PowerShell worker

Command zawiera:

- executable path;
- `-NoLogo`;
- `-NoProfile`;
- `-NonInteractive`;
- execution policy tylko jeśli wymagane i uzasadnione;
- `-File`;
- worker asset path;
- voice profile jako dane inicjalizacyjne, nie tekst eventu.

### 32.3. IPC

JSON serialization:

- UTF-8;
- one line per message;
- maximum message size;
- protocol version;
- request ID;
- exact allowed operations;
- no eval;
- no command interpolation.

### 32.4. Workspace boundaries

Każda output path:

- resolve;
- relative-to workspace;
- under current `scope_id`;
- expected suffix;
- no symlink escape, jeśli środowisko może go utworzyć;
- no overwrite outside owned temp.

### 32.5. Process registry

Run-scoped registry przechowuje:

- PID;
- operation;
- started_at;
- terminate callback;
- kill callback;
- wait callback.

Cancel iteruje po snapshot.

### 32.6. Timeout

Każdy subprocess ma:

- operation timeout;
- shutdown grace;
- hard kill deadline.

Defaulty po benchmarku:

- operation/request timeout `30 s`;
- shutdown grace i deadline `5 s`;
- po deadline hard kill;
- żadne `communicate()` nie jest nieskończone.

Nie ma nieskończonego `communicate()`.

## 33. Fale implementacji

### Fala 0 — bramki techniczne i baseline

Cel:

- zamrozić wartości, których nie wolno zgadywać.

Zadania:

1. uruchomić pełne bramki baseline;
2. zapisać commit SHA;
3. potwierdzić branch;
4. wybrać dwa realne odcinki:
   - jeden already Polish;
   - jeden translated;
5. zapisać checklistę odsłuchu;
6. benchmark SAPI 100–300 eventów:
   - Zosia x64;
   - Agnieszka x86;
7. wymusić timeout SAPI;
8. potwierdzić restart;
9. potwierdzić brak modala;
10. zbudować fixture mono/stereo/5.1/7.1;
11. zamrozić macierze `pan`;
12. potwierdzić capabilities encoderów;
13. zmierzyć default concurrency:
   - ElevenBytes;
   - Edge;
   - SAPI;
14. nie bombardować ElevenLabs bez klucza;
15. wybrać ElevenLabs default model;
16. wybrać codec bitrate defaults;
17. wybrać Agnieszka post tempo;
18. wybrać request timeout;
19. wybrać shutdown deadline;
20. wybrać queue capacity;
21. wybrać cooldown.

Bramka:

- wszystkie otwarte punkty §23 wymagań mają wartość albo jawny bezpieczny default;
- wymagania otrzymują finalny status do implementacji;
- żadna wartość benchmarkowa nie jest wymyślona.

Stan po pierwszym przebiegu Fali 0:

- baseline: 1171 passed, 6 skipped;
- branch: `feature/tts-audio`;
- baseline plan commit: `a6f189c`;
- odcinki referencyjne: Youjo Senki II 01 i Mushoku Tensei S3 03;
- SAPI: 100 eventów per głos, 203/203 decode, timeout i restart potwierdzone;
- ElevenBytes: `12/12` przy concurrency do `12`, default `12`;
- Edge: `8/8` przy concurrency do `8`, default `8`;
- codec capabilities i bitrate defaults potwierdzone lokalnym FFmpeg;
- ElevenLabs model: `eleven_multilingual_v2`;
- ElevenLabs concurrency `4` jest jawnym bezpiecznym defaultem, nie zmyślonym benchmarkiem;
- profile natywne: Zosia `200 WPM / 0.7`, Agnieszka `5 / 65`, Edge Marek i Zofia
  `+40% / +0%`;
- post-process Agnieszki: neutralne `1.0`;
- zaakceptowany smoke ElevenLabs wykonał dokładnie jeden POST bez retry i otrzymał HTTP
  `400`; uwierzytelnione GET-y potwierdziły głos, model TTS i język polski, ale audio
  nie powstało;
- kolejny płatny POST wymaga osobnej zgody;
- pozostałe bramki: końcowy odsłuch macierzy `pan`.

### Fala 1 — typy, errors i registry

Pliki:

- `services/tts/types.py`;
- `services/tts/errors.py`;
- `services/tts/protocols.py`;
- `services/tts/config.py`;
- `services/tts/engines/__init__.py`;
- `errors.py`;
- testy.

Scenariusze:

- exact four IDs;
- lazy imports;
- unknown ID;
- immutable types;
- secret repr;
- config validation;
- capabilities.

Bramka:

```bash
uv run pytest tests/services/tts/test_tts_registry.py tests/services/tts/test_tts_config.py
uv run mypy anishift/ tests/
```

### Fala 2 — neutralny kontrakt requestu

Pliki:

- `services/tts/validation.py`;
- `services/tts/chunking.py`;
- `pipeline/narration.py`;
- testy kontraktu i adaptera.

Scenariusze:

- publiczne TTS API działa bez obiektu napisów;
- adapter pipeline dla Polish source;
- adapter pipeline dla translated source;
- incomplete translation zatrzymane przed TTS;
- tagi, `\N`, `\n`, `\h`, HTML i drawing są obsługiwane/testowane w adapterze pipeline;
- zanieczyszczony `SpeechRequest` jest odrzucany, nie czyszczony;
- punctuation-only;
- single char;
- long request;
- grapheme.

Bramka:

- `services/tts` nie importuje `pysubs2`, subtitles, translation ani pipeline;
- test `TtsService` tworzy `SpeechBatch` ręcznie bez ASS/SRT;
- source i translated dają ten sam `SpeechBatch` przez adapter pipeline;
- timing pozostaje poza `SpeechRequest`.

### Fala 3 — fingerprint i resume repository

Pliki:

- `fingerprint.py`;
- `resume.py`;
- `artifacts.py`;
- testy.

Scenariusze:

- stable hash;
- opaque `scope_id`;
- synthesis-only invalidation;
- atomic clip;
- atomic manifest;
- concurrent updates;
- corrupt manifest;
- orphan recovery;
- bezpieczny segment ścieżki;
- `request_id` collision;
- cleanup isolation.

Bramka:

- tempo/codec nie zmienia synthesis fingerprint;
- voice/model zmienia synthesis fingerprint.
- manifest TTS nie zawiera timingu, source path, narratora ani mix config.

### Fala 4 — scheduler i fake engine

Pliki:

- `scheduler.py`;
- `service.py`;
- fake engine fixtures;
- testy.

Scenariusze:

- global concurrency;
- retry priority;
- backoff without slot;
- exact attempts;
- Retry-After;
- provider-wide circuit;
- batch-local error;
- late commit gate;
- cancel;
- close deadline;
- bounded queue.

Bramka:

- kontrolowane Event/Barrier dowodzą zachowania bez timingowych sleep.

### Fala 5 — audio probe i command boundary

Pliki:

- `audio/types.py`;
- `audio/errors.py`;
- `audio/config.py`;
- `audio/probe.py`;
- `audio/commands.py`;
- testy.

Scenariusze:

- ffprobe JSON;
- no audio;
- missing duration;
- safe stderr;
- timeout;
- kill;
- full decode;
- temp output.

Bramka:

- prawdziwy FFmpeg dekoduje fixture.

### Fala 6 — clip normalization i timeline

Pliki:

- `audio/normalize.py`;
- `audio/timeline.py`;
- testy.

Scenariusze:

- neutral fast path;
- atempo;
- atempo chain;
- sample rate conversion;
- silence;
- overlap;
- drift;
- natural recovery;
- raw PCM streaming;
- RF64 command.

Bramka:

- kilku-eventowy narrator ma sample-accurate placements w tolerancji.

### Fala 7 — channel matrices i output profiles

Pliki:

- `audio/channels.py`;
- `audio/fingerprint.py`;
- `audio/resume.py`;
- `audio/output.py`;
- `audio/service.py`;
- integration fixtures.

Scenariusze:

- mono;
- stereo center;
- 5.1 center;
- 7.1 preserve;
- E-AC-3 7.1 -> 5.1;
- MP3 surround -> stereo;
- AAC;
- Opus;
- FLAC;
- WAV;
- warning;
- duration longest.
- narration/mix fingerprint invalidation;
- Audio manifest nie modyfikuje manifestu TTS;

Bramka:

- impulse fixtures dowodzą każdego kanału;
- nie ma niejawnego remap.

### Fala 8 — ElevenBytes

Pliki:

- package ElevenBytes;
- contract tests;
- mock server tests.

Zadania:

1. przenieść exact request contract;
2. oddzielić `run6` i `run7`;
3. usunąć engine retry;
4. mapować typed errors;
5. Dallin only;
6. custom voice resolver;
7. source format validation;
8. availability.

Bramka:

- fake contract;
- `run6` network smoke;
- no cut ending on sample.

### Fala 9 — Edge

Pliki:

- Edge package;
- version-aware patch;
- tests.

Zadania:

1. pin supported version;
2. patch before import;
3. atomic update;
4. metadata constant update;
5. unknown version failure;
6. Marek;
7. Zofia;
8. native options;
9. network smoke.

Bramka:

- ffprobe potwierdza 24 kHz / 96 kb/s.

### Fala 10 — SAPI

Pliki:

- SAPI package;
- PS worker asset;
- controller;
- tests.

Zadania:

1. protocol;
2. x64 host;
3. x86 host;
4. voice list;
5. persistent lifecycle;
6. timeout;
7. restart;
8. one Ctrl+C;
9. doctor passive;
10. doctor live.

Bramka:

- Zosia live, jeżeli installed;
- Agnieszka live, jeżeli installed;
- forced hang restart;
- no orphan process.

### Fala 11 — oficjalne ElevenLabs

Najpierw dependency workflow.

Następnie:

```bash
uv add elevenlabs
```

Pliki:

- ElevenLabs package;
- env setting;
- tests.

Zadania:

1. lazy SDK;
2. missing key;
3. model;
4. voices;
5. custom ID;
6. voice settings;
7. output tokens;
8. error map;
9. SDK retry off;
10. optional network smoke.

Bramka:

- offline contract jest pełny;
- bez klucza standardowy test jest zielony.

### Fala 12 — pipeline streaming

Pliki:

- pipeline types;
- runner;
- tts runtime;
- tts queue;
- tests.

Zadania:

1. source audio rename;
2. spoken-ready callback;
3. runtime start before extraction;
4. Polish immediate enqueue;
5. Google/DeepL enqueue;
6. LLM enqueue;
7. close producer;
8. map results;
9. isolate files;
10. TXT skip.

Bramka:

- fake TTS zaczyna przed końcem tłumaczenia innych plików;
- natural order jest zachowany.

### Fala 13 — settings i `.env`

Pliki:

- user settings;
- settings;
- settings panel;
- `.env.example`;
- tests.

Zadania:

1. schema version;
2. defaults;
3. profile map;
4. codec;
5. bitrate;
6. native options;
7. custom voices;
8. missing key;
9. atomic `.env`;
10. migration old placeholders.

Bramka:

- save/load roundtrip;
- secret never printed;
- switching voice restores profile.

### Fala 14 — progress i recovery

Pliki:

- `pipeline/recovery.py`;
- `pipeline_ui.py`;
- minimal LLM integration;
- tests.

Zadania:

1. one row;
2. TTS real percentage;
3. audio spinner;
4. engine/voice;
5. elapsed;
6. retry/settings/finish;
7. one Ctrl+C;
8. summary;
9. callback close.

Bramka:

- nie ma dodatkowych rows;
- LLM recovery nie regresuje.

### Fala 15 — dependencies cleanup i docs pairs

Po potwierdzeniu:

```bash
uv remove pyttsx3
uv remove pydub
```

Aktualizacja:

- AGENTS/CLAUDE pairs przez skill `agents-md`;
- żadnego tutoriala bez prośby;
- package assets;
- wheel smoke.

Bramka:

- SAPI worker znajduje się w wheel;
- import nie wymaga usuniętych dependencies.

### Fala 16 — real episode validation

Odcinek A:

- already Polish.

Odcinek B:

- translated.

Oba:

- complete TTS;
- interrupt/resume;
- no repeated paid clips;
- narrator;
- mixed audio;
- decode;
- ffprobe;
- listening checklist.

Bramka:

- wyniki zapisane w raporcie implementacyjnym;
- znane różnice opisane;
- brak ruchomego „brzmi dobrze”.

### Fala 17 — pełne bramki i build

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
uv build
```

Następnie:

- wheel inspect;
- clean install smoke;
- offline CLI smoke;
- conditional network smoke;
- process leak check.

## 34. Macierz testów domeny TTS

### 34.1. Registry

- exact IDs;
- stable order;
- unknown ID;
- lazy SDK imports;
- create one engine;
- other engines remain unloaded;
- registry/panel synchronization;
- default not inferred from sort.

### 34.2. Config

- missing engine;
- unknown engine;
- empty voice;
- invalid model;
- concurrency zero;
- concurrency too large;
- negative retry;
- timeout zero;
- queue zero;
- tempo below range;
- tempo above range;
- invalid native option;
- secret absent repr;
- immutable config.

### 34.3. Publiczny kontrakt requestu

- ręcznie utworzony `SpeechRequest` bez obiektu napisów;
- opaque `request_id`;
- `scope_id`;
- `batch_rank`;
- `request_rank`;
- immutable request;
- clean one-line Polish Unicode;
- wynik zachowuje ten sam `request_id`;
- brak timingu, source path i subtitle types w publicznym API.

### 34.4. Walidacja granicy

- clean Polish text accepted;
- ASS tag rejected;
- HTML tag rejected;
- `\N` rejected;
- literal newline rejected;
- `\h` rejected;
- drawing payload rejected;
- empty ID rejected;
- duplicate ID rejected;
- invalid rank rejected;
- empty text;
- punctuation-only;
- one letter;
- one digit;
- mixed punctuation;
- request nie jest naprawiany ani mutowany;
- brak importu `pysubs2`, subtitles, translation i pipeline.

### 34.5. Long event

- under char limit;
- exact char limit;
- over char limit;
- UTF-8 byte limit;
- sentence split;
- phrase split;
- word split;
- no grapheme split;
- no empty chunk;
- stable part IDs;
- join without artificial pause;
- impossible input error;

### 34.6. Capabilities

- local/network;
- key required;
- formats;
- min length;
- max length;
- native options;
- concurrency;
- probe kind;
- serialization.

### 34.7. Availability

- ready;
- missing key;
- missing voice;
- missing binary;
- offline;
- unavailable;
- unsupported platform;
- cached;
- fresh;
- safe message;
- no paid request for passive check.

### 34.8. Lifecycle

- lazy engine;
- reuse;
- context close;
- double close;
- error close;
- use after close;
- worker close;
- client close;
- executor close;
- deadline.

### 34.9. Scheduler

- single request;
- stable batch order;
- stable request order;
- later ready batch proceeds;
- concurrency exact;
- global limit;
- retry priority;
- backoff releases slot;
- Retry-After;
- fatal no retry;
- transient exact attempts;
- provider circuit;
- batch-local failure;
- active completion after circuit;
- bounded input;
- bounded tasks;
- no round barrier.

### 34.10. Cancellation TTS

- cancel before request;
- cancel during request;
- cancel during backoff;
- cancel during SAPI;
- one signal;
- no new work;
- late result blocked;
- temp file not committed;
- progress not incremented;
- worker killed;
- no task leak.

### 34.11. Resume syntezy TTS

- empty manifest;
- hit;
- text miss;
- engine miss;
- model miss;
- voice miss;
- native option miss;
- post tempo synthesis hit;
- codec synthesis hit;
- corrupt manifest;
- orphan valid;
- orphan corrupt;
- hash mismatch;
- zero-byte clip;
- non-decodable clip;
- concurrent updates;
- schema future version;
- changed opaque scope;
- manifest nie zawiera source path, timingu, narratora ani mix config.

### 34.12. Progress

- total required;
- skipped excluded;
- resume initial progress;
- retry no total change;
- commit increments once;
- late result no increment;
- one task ID;
- phase changes;
- done;
- failed;
- cancelled;
- callback after close ignored.

## 35. Macierz testów engine

### 35.1. ElevenBytes offline

- run6 request;
- run7 request;
- Dallin mapping;
- custom voice;
- exact endpoint;
- exact headers;
- source format;
- empty response;
- malformed response;
- 403;
- 429;
- 500;
- timeout;
- Retry-After;
- no internal retry;
- experimental marker.

### 35.2. ElevenBytes network

- run6 short text;
- run6 last word present;
- run6 Unicode;
- run7 short text;
- run7 manual ending;
- small concurrency;
- no bombardment;
- output decode.

### 35.3. ElevenLabs offline

- missing SDK;
- missing key;
- lazy SDK;
- model mapping;
- voice ID;
- custom ID;
- voice settings;
- output token mapping;
- response iterator;
- empty iterator;
- 400;
- 401;
- 403;
- 404;
- 429;
- 5xx;
- timeout;
- retry off;
- secret safety.

### 35.4. ElevenLabs network

- skip without key;
- user model;
- user voice;
- Polish text;
- output probe;
- decode;
- no key output.

### 35.5. Edge offline

- supported version;
- old value;
- already patched;
- partially patched;
- unknown version;
- read-only;
- atomic replace;
- bitrate constant;
- patch before runtime import;
- package missing;
- voice selection;
- rate;
- pitch;
- volume;
- empty audio.

### 35.6. Edge network

- Marek;
- Zofia;
- 24 kHz;
- 96 kb/s;
- mono;
- full decode;
- small concurrency;
- offline classification.

### 35.7. SAPI passive

- non-Windows;
- x64 host missing;
- x86 host missing;
- Zosia found x64;
- Agnieszka found x86;
- voice missing;
- architecture mismatch;
- no Speak in doctor;
- no temp WAV.

### 35.8. SAPI live

- Zosia non-empty;
- Agnieszka non-empty;
- persistent second request;
- 100+ requests;
- Unicode;
- one char;
- output path spaces;
- output path Unicode;
- timeout;
- restart;
- broken pipe;
- worker exit;
- malformed JSON;
- wrong request ID;
- header-only WAV;
- modal timeout;
- Ctrl+C;
- no orphan process.

## 36. Macierz testów audio

### 36.1. Probe

- WAV;
- MP3;
- E-AC-3;
- Opus;
- FLAC;
- M4A AAC;
- no audio;
- corrupt;
- zero byte;
- multiple streams;
- missing duration;
- fractional duration;
- layout.

### 36.2. Normalization

- PCM fast path;
- compressed decode;
- resample;
- mono conversion;
- tempo 1.0;
- tempo 1.25;
- tempo 0.5;
- tempo >2 chain;
- temp collision;
- atomic result;
- cancellation.

### 36.3. Timeline

- initial silence;
- contiguous clips;
- natural gap;
- overlap;
- accumulated drift;
- recovered drift;
- same start;
- stable source index;
- empty;
- one clip;
- long clip;
- raw PCM size;
- duration frames.

### 36.4. Channel fixture

Mono:

- narrator center;
- output mono.

Stereo:

- left source remains left;
- right source remains right;
- narrator equal-power both;
- no phase inversion.

5.1:

- FL preserved;
- FR preserved;
- FC receives narrator;
- LFE preserved;
- SL preserved;
- SR preserved.

7.1:

- every source channel mapped;
- narrator FC;
- preserve profile;
- explicit 5.1 downmix;
- explicit stereo downmix.

### 36.5. Mix

- original 0 dB;
- base +7;
- Dallin -2;
- Agnieszka +2;
- normalize true;
- dropout 2;
- longest;
- narrator longer;
- original longer;
- no original;
- no mix gain without original;
- result tolerance.

### 36.6. Codecs

MP3:

- extension;
- codec;
- mono/stereo;
- surround warning;
- bitrate.

WAV:

- PCM S16LE;
- extension;
- lossless;
- RF64 path.

E-AC-3:

- extension;
- codec;
- 5.1;
- 7.1 downmix.

Opus:

- extension;
- codec;
- supported layout;
- bitrate.

FLAC:

- extension;
- codec;
- no bitrate field;
- compression level.

AAC:

- `.m4a`;
- AAC-LC;
- container;
- supported layout;
- bitrate.

### 36.7. Output ownership

- no existing file;
- owned same fingerprint;
- owned changed fingerprint;
- unowned collision;
- old codec preserved;
- atomic replace;
- failed temp preserves old;
- manifest path exact;
- hash exact.

### 36.8. Resume Audio

- narration hit dla tych samych `TimedClip`;
- timing miss przebudowuje narrator, nie TTS;
- post tempo miss przebudowuje narrator, nie TTS;
- gain miss przebudowuje tylko mix;
- codec/bitrate miss przebudowuje tylko output;
- original audio identity miss przebudowuje tylko mix;
- corrupt Audio manifest nie zmienia manifestu TTS;
- Audio nie zapisuje do `workspace/tmp/<scope-id>/tts/`.

## 37. Testy pipeline i UI

### 37.1. Immediate enqueue

Kontrolowany scenariusz:

1. file B translation jest zablokowane Event;
2. file A Polish source jest gotowe;
3. TTS A startuje;
4. B nadal jest zablokowane;
5. assertion dowodzi D1.

### 37.2. Natsorted

Input:

```text
Episode 2.mkv
Episode 10.mkv
Episode 1.mkv
```

Order:

```text
Episode 1
Episode 2
Episode 10
```

### 37.3. Translation paths

- already Polish;
- Google;
- DeepL;
- LLM;
- failed translation;
- partial translation;
- no spoken;
- drawings only.
- Polish i translated mapują się na ten sam `SpeechRequest`;
- adapter usuwa składnię/layout przed granicą TTS;
- timing pozostaje w `NarrationBatch`, nie w `SpeechRequest`;
- odpowiedź TTS jest łączona po `request_id`, nie po pozycji na liście;
- zanieczyszczony request nie jest wysyłany do engine.

### 37.4. File isolation

- first done;
- second provider failure;
- third pending;
- first sidecar remains;
- second resume remains;
- third not processed after finish.

### 37.5. Recovery

- retry same;
- settings same;
- settings new engine;
- settings new voice;
- settings new tempo;
- settings new codec;
- finish;
- completed untouched;
- pending statuses.

### 37.6. Ctrl+C

- extraction running;
- translation running;
- TTS running;
- audio running;
- one keyboard interrupt;
- prompt returns;
- no worker;
- no process;
- resume valid.

### 37.7. Progress

- same row extraction -> Polish -> TTS -> audio -> done;
- same row extraction -> translation -> TTS;
- engine label;
- real percentage;
- resume initial percentage;
- audio spinner;
- failure color;
- summary separators.

### 37.8. Settings

- defaults;
- migration;
- engine cycle;
- unavailable visible;
- missing key;
- masked input;
- voice cycle;
- custom voice;
- per-voice restore;
- codec fields;
- bitrate visibility;
- units;
- save/cancel.

## 38. Benchmarki

### 38.1. SAPI durability

Zmierzyć:

- cold start;
- first request;
- steady median;
- p95;
- 100 events;
- 300 events;
- memory;
- process count;
- timeout recovery;
- modal absence.

### 38.2. Engine concurrency

Per network engine:

- 1;
- 2;
- 4;
- ewentualnie 8 tylko jeśli bezpieczne;
- success rate;
- wall time;
- rate limit;
- retry;
- provider rules.

Default wybiera najlepszy bezpieczny punkt.

### 38.3. Queue capacity

Sprawdzić:

- typowy odcinek 300–600 events;
- sześć odcinków;
- memory;
- task count;
- backpressure;
- cancel latency.

### 38.4. Audio montage

Porównać:

- stary mm_avh;
- nowy cold cache;
- nowy warm cache;
- tempo 1.0;
- tempo 1.25;
- 300 clips;
- 600 clips;
- WAV;
- E-AC-3.

### 38.5. Kryterium

Warm-cache montaż:

- nie regresuje rażąco;
- nie uruchamia bez potrzeby setek probe;
- nie dominuje czasu po TTS;
- nie zużywa RAM proporcjonalnego do pełnego PCM odcinka.

### 38.6. Cancel latency

Zmierzyć:

- Edge active;
- ElevenBytes active;
- SAPI active;
- FFmpeg active;
- blocked fake SDK.

Terminal powinien wrócić w bounded deadline.

## 39. Real episode protocol

### 39.1. Fixture A

Already Polish:

- źródło z polskimi spoken;
- minimum 200 events;
- overlaps;
- signs/displayed obecne;
- source audio stereo albo surround;
- znane miejsca odsłuchu.

### 39.2. Fixture B

Translated:

- LLM albo Google/DeepL;
- minimum 200 events;
- polskie znaki;
- liczby;
- szybki dialog;
- różne style.

### 39.3. Punkty odsłuchu

Początek:

- pierwsza wypowiedź;
- initial silence;
- poziom lektora.

Środek:

- szybki dialog;
- overlap;
- drift;
- muzyka/efekty.

Koniec:

- ostatnie słowo;
- narrator dłuższy od audio;
- brak ucięcia.

### 39.4. Checklist jakości

- głos nie urywa słów;
- brak klików na łączeniach;
- brak sztucznej pauzy po chunk split;
- tempo naturalne;
- lektor słyszalny;
- anime nadal słyszalne;
- brak clippingu oczywistego odsłuchowo;
- center poprawny;
- surround nie został spłaszczony bez warning;
- final path poprawny.

### 39.5. Resume test

1. rozpocząć TTS;
2. poczekać na co najmniej 20 clips;
3. jedno Ctrl+C;
4. zapisać request count;
5. uruchomić ponownie;
6. potwierdzić resume hits;
7. potwierdzić brak requestów dla ukończonych `request_id`;
8. ukończyć;
9. decode-check.

### 39.6. Zapis wyników

Raport końcowy implementacji zawiera:

- source names;
- engine/model/voice;
- event counts;
- request counts;
- retries;
- resume hits;
- times;
- drift;
- codec/layout;
- listening observations;
- known limitations.

Nie zapisuje:

- subtitle text;
- API key;
- request body.

## 40. Definition of Done

### 40.1. Domena

- [ ] istnieje `services/tts`;
- [ ] istnieje `services/audio`;
- [ ] importy są jednokierunkowe;
- [ ] cztery exact engine IDs;
- [ ] registry jest lazy;
- [ ] unknown ID jest typed;
- [ ] config jest typed;
- [ ] secrets są maskowane.

### 40.2. Adapter pipeline i granica TTS

- [ ] Polish source działa;
- [ ] translated source działa;
- [ ] oba mapują się na jeden `SpeechRequest`;
- [ ] failed translation blokuje TTS;
- [ ] TXT jest no-timeline;
- [ ] adapter pipeline zachowuje Unicode i zamienia layout na whitespace;
- [ ] TTS odrzuca zanieczyszczony request zamiast parsować lub naprawiać napisy;
- [ ] timing pozostaje poza TTS;
- [ ] single char nie znika;
- [ ] long event nie jest obcinany.

### 40.3. Engine

- [ ] ElevenBytes run6;
- [ ] ElevenBytes run7 experimental;
- [ ] Dallin default;
- [ ] custom ElevenBytes voices;
- [ ] ElevenLabs official;
- [ ] missing ElevenLabs key;
- [ ] Edge Marek;
- [ ] Edge Zofia;
- [ ] Edge 96 kb/s;
- [ ] SAPI Zosia x64;
- [ ] SAPI Agnieszka x86;
- [ ] no Balcon;
- [ ] no pyttsx3 runtime.

### 40.4. Scheduler

- [ ] global concurrency;
- [ ] retry priority;
- [ ] Retry-After;
- [ ] exact attempts;
- [ ] one retry owner;
- [ ] provider circuit;
- [ ] file isolation;
- [ ] bounded queue;
- [ ] one event loop owner.

### 40.5. Cancellation

- [ ] one Ctrl+C;
- [ ] no new request;
- [ ] SAPI killed;
- [ ] FFmpeg killed;
- [ ] late result blocked;
- [ ] no progress after cancel;
- [ ] no manifest after cancel;
- [ ] bounded return;
- [ ] no leaked tasks/processes.

### 40.6. Resume

- [ ] deterministic pipeline `scope_id`;
- [ ] versioned manifest;
- [ ] synthesis fingerprint;
- [ ] narration fingerprint;
- [ ] mix fingerprint;
- [ ] atomic clips;
- [ ] atomic manifest;
- [ ] concurrent writer;
- [ ] orphan recovery;
- [ ] corrupt manifest handling;
- [ ] extraction cleanup preserves state;
- [ ] Stage 6 does not clean completed resume.

### 40.7. Timeline

- [ ] stable order;
- [ ] silence;
- [ ] no truncate;
- [ ] serialize overlap;
- [ ] drift;
- [ ] natural drift recovery;
- [ ] per-clip tempo;
- [ ] narrator PCM;
- [ ] narrator WAV;
- [ ] RF64 path.

### 40.8. Mix

- [ ] original gain;
- [ ] +7 base;
- [ ] voice offset;
- [ ] no gain without original;
- [ ] normalize true;
- [ ] dropout 2;
- [ ] longest;
- [ ] narrator end preserved;
- [ ] codec settings;
- [ ] output validation.

### 40.9. Channels

- [ ] mono fixture;
- [ ] stereo fixture;
- [ ] 5.1 fixture;
- [ ] 7.1 fixture;
- [ ] narrator center;
- [ ] explicit downmix;
- [ ] warning;
- [ ] output layout probe;
- [ ] no implicit mapping.

### 40.10. Output

- [ ] `{stem}.<codec>`;
- [ ] MP3;
- [ ] WAV;
- [ ] E-AC-3;
- [ ] Opus;
- [ ] FLAC;
- [ ] M4A AAC;
- [ ] old formats preserved;
- [ ] foreign collision protected;
- [ ] partial has no final path.

### 40.11. Pipeline/UI

- [ ] immediate enqueue;
- [ ] natsorted;
- [ ] one row;
- [ ] real TTS percent;
- [ ] audio phase;
- [ ] engine/voice label;
- [ ] recovery retry;
- [ ] recovery settings;
- [ ] recovery finish;
- [ ] report.

### 40.12. Verification

- [ ] unit tests;
- [ ] integration FFmpeg;
- [ ] network smoke;
- [ ] SAPI live;
- [ ] two episodes;
- [ ] cancel/resume;
- [ ] full decode;
- [ ] full gates;
- [ ] wheel assets;
- [ ] clean install.

## 41. Ryzyka i zabezpieczenia

| Ryzyko | Skutek | Zabezpieczenie |
|---|---|---|
| podwójny retry | koszt i opóźnienie | scheduler jest jedynym właścicielem |
| zbyt duże concurrency | rate limit | benchmark i globalny limiter |
| late SDK result | stan po cancel | commit gate |
| SAPI modal | zawieszony CLI | worker + timeout + live doctor only |
| x86/x64 voice mismatch | pusty WAV | profile architecture + decode |
| cleanup usuwa resume | ponowne koszty | scope root i osobny scratch |
| corrupt manifest | błędne cache hit | reject whole manifest + orphan scan |
| clip po crashu bez manifestu | ponowny koszt | deterministic orphan recovery |
| output collision | utrata pliku usera | ownership manifest |
| blind Edge patch | uszkodzone venv | version-aware atomic patch |
| Edge wraca do 48 kb/s | spadek jakości | unavailable zamiast cichego fallback |
| format providera źle rozpoznany | decode failure | real metadata + full decode |
| post tempo na narratorze | przesunięte timingi | tempo per clip |
| niejawny downmix | utrata przestrzenności | explicit pan + impulses |
| narrator w surround | nienaturalny głos | physical center only |
| normalizacja amix zmienia gain | inny odsłuch | explicit normalize true baseline |
| duży drift | opóźniona narracja | metrics + report; future scheduler |
| setki FFmpeg processów | wolny montaż | fast path + cache + bounded conversion |
| ogromny WAV | RIFF overflow | raw PCM + RF64 |
| secret w repr | wyciek | repr false/SecretStr tests |
| settings `volume=100` jako dB | katastrofalny gain | no semantic migration |
| mixed audio partial | mylący sukces | final name only after complete |
| long event cut | utrata treści | deterministic chunking |
| one-char rejected | brak wypowiedzi | engine adapter |
| batch order race | chaos | stable batch_rank |
| progress row duplication | regresja UX | one task ID test |
| rich_console refactor | scope creep | reuse public API; notify user |
| MangaShift DB copied | przerost | explicit rejected list |
| TTS zaczyna parsować napisy | sprzężenie domen i utrata metadata | neutralny request + test zakazanych importów |

## 42. Antywzorce zakazane

- god-file łączący engine, retry, timeline i mix;
- `if engine_id ==` w pipeline dispatch;
- import SDK w registry import;
- `asyncio.run()` per request;
- event loop w CLI;
- semaphore per file;
- semaphore w schedulerze i engine jednocześnie;
- retry w SDK i schedulerze;
- broad `except Exception`;
- cichy fallback na source text;
- cichy fallback na drugi engine;
- cichy fallback Edge do 48 kb/s;
- whole-SRT TTS;
- reparsing `.spoken.pl.ass`;
- dedup identycznych spoken;
- cache tylko po source index;
- manifest update przed clip validation;
- non-atomic final output;
- glob delete `{stem}.*`;
- cleanup całego `tmp/<stem>`;
- `shell=True`;
- text interpolated into PowerShell command;
- no timeout subprocess;
- header-only WAV as success;
- ffprobe-only final validation bez decode-check;
- `-ac 2` jako ukryty downmix;
- narrator we wszystkich surround channels;
- `-shortest`;
- tempo na całym narrator WAV;
- mix gain na narrator-only;
- E-AC-3 hardcoded w audio service;
- `.aac` jako default AAC product;
- bitrate UI dla FLAC/WAV;
- volume 0–100 interpretowane jako dB;
- automatic cleanup resume w etapie 6;
- tworzenie final sidecaru z partial result;
- dodatkowy progress row;
- zmiana `rich_console` bez poinformowania usera;
- Balcon;
- pyttsx3;
- Supertonic w tym etapie;
- future scheduler ukryty w engine.

## 43. Kolejność commitów

Każdy commit po pełnych bramkach repo.

Proponowana kolejność:

1. `test(tts): add stage 6 audio baselines`
2. `feat(tts): add domain contracts and lazy registry`
3. `feat(tts): add neutral request validation`
4. `feat(tts): add synthesis resume state`
5. `feat(tts): add concurrent scheduler and cancellation`
6. `feat(audio): add ffmpeg probe and validation`
7. `feat(audio): add clip normalization and timeline`
8. `feat(audio): add channel mapping and output profiles`
9. `feat(tts): add elevenbytes engine`
10. `feat(tts): add edge engine and quality patch`
11. `feat(tts): add persistent sapi worker`
12. `feat(tts): add official elevenlabs engine`
13. `feat(pipeline): adapt ready spoken text to tts`
14. `feat(config): add per-voice tts profiles`
15. `feat(cli): add tts engine voice and audio settings`
16. `feat(pipeline): add shared failure recovery`
17. `feat(cli): show tts and audio progress`
18. `test(tts): add live and real episode coverage`
19. `docs(tts): document stage 6 runtime contracts`

### 43.1. Zasady commitów

- nie commitować na `main`;
- nie łączyć wielu fal w jeden commit;
- nie używać `Co-Authored-By`;
- scope musi przejść hook;
- dependencies zmieniane własnym commitem albo razem z jedynym konsumentem;
- generated runtime audio nie trafia do git;
- test fixture binary tylko jeśli mały i uzasadniony;
- inaczej fixture generowany deterministycznie.

### 43.2. Bramki przed każdym

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

### 43.3. Dodatkowe bramki zakresowe

Po engine:

- jego contract tests;
- lazy import test.

Po audio:

- real FFmpeg integration.

Po worker:

- process leak test.

Po settings:

- migration test.

Po assets:

- wheel test.

## 44. Checklista wykonawcy

### 44.1. Przed kodem

- [ ] requirements status zaakceptowany;
- [ ] branch poprawny;
- [ ] worktree przejrzany;
- [ ] user files nietknięte;
- [ ] baseline gates;
- [ ] reference episodes;
- [ ] SAPI durability;
- [ ] channel matrices;
- [ ] codec capabilities;
- [ ] concurrency defaults;
- [ ] timeout defaults;
- [ ] bitrate defaults;
- [ ] ElevenLabs model.

### 44.2. Domena

- [ ] types;
- [ ] config;
- [ ] errors;
- [ ] protocols;
- [ ] registry;
- [ ] service;
- [ ] scheduler;
- [ ] resume;
- [ ] fingerprint;
- [ ] output ownership.

### 44.3. Engine

- [ ] ElevenBytes;
- [ ] Edge;
- [ ] SAPI;
- [ ] ElevenLabs;
- [ ] capabilities;
- [ ] availability;
- [ ] voices;
- [ ] no hidden retry;
- [ ] close.

### 44.4. Audio

- [ ] probe;
- [ ] decode;
- [ ] normalize;
- [ ] atempo;
- [ ] timeline;
- [ ] RF64;
- [ ] channels;
- [ ] mix;
- [ ] codecs;
- [ ] output validation.

### 44.5. Pipeline

- [ ] source audio rename;
- [ ] spoken adapter;
- [ ] immediate enqueue;
- [ ] runtime;
- [ ] result mapping;
- [ ] recovery;
- [ ] cancel;
- [ ] natsorted;
- [ ] file isolation.

### 44.6. Config/UI

- [ ] schema migration;
- [ ] defaults;
- [ ] profiles;
- [ ] custom voices;
- [ ] env key;
- [ ] missing markers;
- [ ] codec;
- [ ] units;
- [ ] one row;
- [ ] summary.

### 44.7. Verification

- [ ] unit;
- [ ] integration;
- [ ] network;
- [ ] SAPI;
- [ ] episodes;
- [ ] resume;
- [ ] cancel;
- [ ] build;
- [ ] clean install;
- [ ] full gates.

## 45. Najważniejsze pytania review

Reviewer zaczyna od:

1. Czy TTS parsuje zapisany plik napisów?
2. Czy Polish source rzeczywiście trafia do TTS?
3. Czy failed translation może zostać przeczytane po angielsku?
4. Czy registry importuje SDK?
5. Czy dokładnie cztery engine IDs istnieją?
6. Czy Balcon albo pyttsx3 pozostały w runtime?
7. Czy retry ma jednego właściciela?
8. Czy `max_retries=3` daje dokładnie cztery attempts?
9. Czy global concurrency mnoży się przez liczbę plików?
10. Czy backoff zajmuje slot?
11. Czy retry ma pierwszeństwo?
12. Czy provider-wide failure zatrzymuje nowe requesty?
13. Czy jedno Ctrl+C wystarcza?
14. Czy late result może zapisać clip?
15. Czy SAPI worker jest zabijany po timeout?
16. Czy x86 i x64 używają tego samego protokołu?
17. Czy passive doctor wykonuje Speak?
18. Czy Edge patch jest przed importem?
19. Czy Edge patch aktualizuje bitrate constant?
20. Czy unknown Edge version failuje jawnie?
21. Czy resume przetrwa extraction cleanup?
22. Czy manifest jest odporny na lost update?
23. Czy orphan clip jest odzyskiwany?
24. Czy tempo zmienia synthesis fingerprint?
25. Czy codec zmienia synthesis fingerprint?
26. Czy voice zmienia synthesis fingerprint?
27. Czy identyczne spoken są deduplikowane?
28. Czy long event jest obcinany?
29. Czy one-char event znika?
30. Czy timeline ucina klip?
31. Czy tempo jest stosowane per clip?
32. Czy narrator WAV obsługuje RF64?
33. Czy narrator-only dostaje +7 dB?
34. Czy amix jawnie ma normalize true?
35. Czy narrator end jest zachowany?
36. Czy `-shortest` pojawiło się?
37. Czy channel mapping jest jawny?
38. Czy narrator trafia do center?
39. Czy downmix emituje warning?
40. Czy obcy sidecar może zostać nadpisany?
41. Czy zmiana codeca usuwa stary?
42. Czy partial result ma finalną nazwę?
43. Czy pipeline tworzy dodatkowy row?
44. Czy progress liczy retry jako nowy total?
45. Czy secret występuje w repr/log/error?
46. Czy stage 2 volume zostało błędnie zmigrowane do dB?
47. Czy LLM recovery nadal działa?
48. Czy TTS zaczyna przed końcem tłumaczenia folderu?
49. Czy TXT jest pomijany z jasnym powodem?
50. Czy final result przechodzi full decode?

## 46. Świadome odroczenia

Poza etapem 6:

- narration scheduler v2;
- displayed fallback;
- ponowny zapis spoken/displayed po konflikcie;
- fit policy;
- overlap policy;
- adaptive timing;
- speech rate optimization;
- narrator loudness normalization;
- local narrator gain;
- ducking;
- adaptive mix;
- peak guard;
- true-peak measurement;
- cross-voice loudness profiles;
- Supertonic;
- inne lokalne modele;
- voice cloning;
- speaker identification;
- voice per character;
- emotional tags;
- SSML authoring;
- automatic quality scoring;
- waveform visualization;
- final MKV;
- MP4 render;
- final resume cleanup;
- automatic old sidecar cleanup;
- GUI;
- audio preview editor;
- TTS for TXT audiobook mode.

Typy nie powinny udawać pełnej obsługi tych funkcji.

Zostają tylko rozszerzalne miejsca, które mają dzisiejszego konsumenta:

- capabilities;
- engine options;
- timeline policy enum;
- codec profile;
- voice profile.

## 47. Mapa pokrycia R1–R64

### R1 — neutralny request syntezy

Pokrycie:

- §8.1;
- §10.1;
- §10.2;
- Fala 2;
- testy §34.3.

Dowód:

- jeden `SpeechRequest` dla Polish i translated;
- timing pozostaje w adapterze pipeline.

### R2 — kolejność

Pokrycie:

- §15.2;
- §23.1;
- §26;
- testy §37.2.

Dowód:

- `batch_rank` i `request_rank` w TTS;
- stable `(start_ms, source_index)` w Audio.

### R3 — nieudane tłumaczenie

Pokrycie:

- §26.7;
- §37.3.

Dowód:

- brak `SpeechRequest`;
- `translation_incomplete` zatrzymane przez pipeline.

### R4 — TXT

Pokrycie:

- §3.2;
- §26.15;
- §37.3.

Dowód:

- `no_media_timeline`.

### R5 — tekst silnika

Pokrycie:

- §10.1;
- §10.2;
- §26.5–§26.7;
- §34.4.
- §37.3.

Dowód:

- adapter pipeline tworzy czysty Unicode text;
- TTS waliduje kontrakt bez wiedzy o layout.

### R6 — puste i jednoliterowe

Pokrycie:

- §10.3;
- §10.4;
- §23.10;
- §34.4.

Dowód:

- skip status;
- engine adapter.

### R7 — liczby

Pokrycie:

- §10.6.

Dowód:

- brak ukrytego normalizer.

### R8 — registry

Pokrycie:

- §11;
- Fala 1;
- §34.1.

Dowód:

- four lazy IDs.

### R9 — capabilities i long input

Pokrycie:

- §8.5;
- §10.5;
- §34.5;
- §34.6.

Dowód:

- typed capabilities;
- deterministic chunk.

### R10 — wynik syntezy

Pokrycie:

- §8.9;
- §8.10;
- §34.

Dowód:

- typed `RawClip`;
- typed `SynthesizedRequest` zachowujący `request_id`.

### R11 — sync facade i async internals

Pokrycie:

- §6.6;
- §6.7;
- §14;
- §16.

Dowód:

- one Runner;
- sync `TtsService.synthesize`.

### R12 — ElevenBytes endpointy

Pokrycie:

- §18;
- Fala 8;
- §35.1.

Dowód:

- run6/run7;
- Dallin.

### R13 — publiczny token proxy

Pokrycie:

- §4.8;
- §18.6.

Dowód:

- no env key.

### R14 — retry owner

Pokrycie:

- §15;
- §18.6;
- §34.9.

Dowód:

- scheduler only.

### R15 — ElevenLabs SDK/key

Pokrycie:

- §19.1;
- §19.2;
- §29;
- Fala 11.

Dowód:

- `uv add`;
- env key.

### R16 — ElevenLabs models/voices

Pokrycie:

- §19.4;
- §19.5;
- §30.

Dowód:

- model choice;
- TTL voices;
- custom ID.

### R17 — ElevenLabs settings

Pokrycie:

- §19.6;
- §19.7;
- §28.9.

Dowód:

- validation before request.

### R18 — ElevenLabs errors

Pokrycie:

- §19.9;
- §35.3.

Dowód:

- typed map.

### R19 — Edge API

Pokrycie:

- §20;
- Fala 9.

Dowód:

- public params;
- strict patch.

### R20 — Edge availability

Pokrycie:

- §8.7;
- §20.5;
- §35.5.

Dowód:

- package/network/voice distinctions.

### R21 — SAPI voices/architecture

Pokrycie:

- §21.1;
- §21.2;
- §21.3;
- §35.7.

Dowód:

- x64/x86 profiles.

### R22 — isolation

Pokrycie:

- §21.8;
- §21.10;
- §16.4.

Dowód:

- kill/restart worker.

### R23 — persistent worker

Pokrycie:

- §21.4–§21.10.

Dowód:

- JSONL persistent protocol.

### R24 — passive/live availability

Pokrycie:

- §21.11;
- §35.7;
- §35.8.

Dowód:

- no Speak passive;
- timeout live.

### R25 — SAPI adapter

Pokrycie:

- §21.5–§21.13.

Dowód:

- one request -> one validated WAV.

### R26 — engine concurrency

Pokrycie:

- §6.6;
- §15.5;
- §38.2.

Dowód:

- global measured limit.

### R27 — multi-file pipeline

Pokrycie:

- §26;
- Fala 12;
- §37.1.

Dowód:

- immediate enqueue.

### R28 — Ctrl+C

Pokrycie:

- §16;
- §32.5;
- §37.6.

Dowód:

- one cancellation controller.

### R29 — order after failure

Pokrycie:

- §15.1–§15.3.

Dowód:

- priority key.

### R30 — resume location

Pokrycie:

- §17.1;
- §17.2.

Dowód:

- `workspace/tmp/<scope-id>/tts`.

### R31 — cleanup conflict

Pokrycie:

- §17.13;
- §26.16.

Dowód:

- separate scratch.

### R32 — layered fingerprints

Pokrycie:

- §17.4–§17.8.
- §34.11;
- §36.8.

Dowód:

- synthesis/narration/mix.

### R33 — atomic write

Pokrycie:

- §17.9–§17.12;
- §25.7.

Dowód:

- validate -> clip -> manifest.

### R34 — cleanup after Stage 7

Pokrycie:

- §4.3;
- §17.13;
- §46.

Dowód:

- Stage 6 retains.

### R35 — no dedup

Pokrycie:

- §4.4;
- §17.4.

Dowód:

- `request_id` in fingerprint.

### R36 — timeline v1

Pokrycie:

- §23.

Dowód:

- serialize formula.

### R37 — window policy

Pokrycie:

- §4.2;
- §23.8;
- §46.

Dowód:

- serialize only;
- future metadata.

### R38 — tempo

Pokrycie:

- §22.9;
- §22.10;
- §28.

Dowód:

- per-voice, per-clip.

### R39 — narrator WAV

Pokrycie:

- §22.7;
- §22.12;
- §22.13.

Dowód:

- PCM mono 48k;
- RF64.

### R40 — audio scope

Pokrycie:

- §22;
- §25.

Dowód:

- probe through final verification.

### R40a — performance

Pokrycie:

- §22.8;
- §22.11;
- §38.4.

Dowód:

- fast path;
- streaming;
- benchmark.

### R41 — mix

Pokrycie:

- §25;
- §36.5.

Dowód:

- fixed gain baseline.

### R41.1 — heuristic registry

Pokrycie:

- §3.2;
- §46.

Dowód:

- V0 only;
- V1–V5 deferred.

### R41.2 — smoothing

Pokrycie:

- §46.

Dowód:

- no accidental implementation.

### R41.3 — length/channels

Pokrycie:

- §24;
- §25.5;
- §36.4.

Dowód:

- explicit matrices;
- longest.

### R41a — codec mapping

Pokrycie:

- §22.3;
- §22.4;
- §36.6.

Dowód:

- exact extension/container.

### R42 — no original audio

Pokrycie:

- §25.4;
- §36.5.

Dowód:

- no mix gain.

### R43 — FFmpeg error

Pokrycie:

- §25.10;
- §32.

Dowód:

- safe typed process error.

### R44 — artifacts

Pokrycie:

- §17.1;
- §25.6–§25.9.

Dowód:

- temp narrator;
- one sidecar.

### R44a — MPV

Pokrycie:

- §4.6;
- §25.6.

Dowód:

- exact stem naming.

### R45 — narrator temp

Pokrycie:

- §4.5;
- §17.1.

Dowód:

- not public second output.

### R46 — common settings

Pokrycie:

- §28;
- §30.

Dowód:

- typed units.

### R47 — per-engine settings

Pokrycie:

- §28.9;
- §30.

Dowód:

- dynamic visible fields.

### R48 — unavailable engine

Pokrycie:

- §8.7;
- §29;
- §30.1;
- §30.2.

Dowód:

- visible reason;
- masked key.

### R49 — voices/custom IDs

Pokrycie:

- §18.8;
- §19.5;
- §21.12;
- §30.3–§30.5.

Dowód:

- dynamic lists and persistence.

### R50 — one row

Pokrycie:

- §31.1;
- §31.2.

Dowód:

- one task ID.

### R51 — real TTS progress

Pokrycie:

- §31.3;
- §31.4.

Dowód:

- committed/required.

### R52 — visible phase

Pokrycie:

- §31.5;
- §31.6;
- §31.7.

Dowód:

- phase/engine/time.

### R53 — summary

Pokrycie:

- §31.10;
- §39.6.

Dowód:

- counts, drift, time, path.

### R54 — file isolation

Pokrycie:

- §26.14;
- §37.4.

Dowód:

- completed result unchanged.

### R55 — recovery

Pokrycie:

- §27;
- Fala 14;
- §37.5.

Dowód:

- retry/settings/finish.

### R55a — translation compatibility

Pokrycie:

- §27.1–§27.4;
- §26.8;
- §26.9.

Dowód:

- shared semantics;
- domain state separate.

### R56 — partial audio

Pokrycie:

- §4.17;
- §25.7;
- §40.10.

Dowód:

- no final sidecar.

### R57 — secrets

Pokrycie:

- §12.4;
- §29;
- §32.

Dowód:

- masking tests.

### R58 — external text

Pokrycie:

- settings/docs update in Fala 15;
- local/network capabilities.

Dowód:

- UI labels external vs local.

### R59 — subprocess

Pokrycie:

- §16.5;
- §21;
- §32.

Dowód:

- list args, timeout, restricted IPC.

### R60 — unit tests

Pokrycie:

- §34;
- §35;
- §36;
- §37.

Dowód:

- offline suite.

### R61 — integration

Pokrycie:

- §36;
- SAPI tests;
- Fale 5–7.

Dowód:

- real FFmpeg and optional local voices.

### R62 — network

Pokrycie:

- §35;
- Fale 8, 9, 11.

Dowód:

- marked conditional smoke.

### R63 — real episode

Pokrycie:

- §39;
- Fala 16.

Dowód:

- two episodes and checklist.

### R64 — quality gates

Pokrycie:

- §33;
- §43.

Dowód:

- full gates before every commit.

## 48. Mapa decyzji D1–D22

| Decyzja | Implementacja |
|---|---|
| D1 | streaming spoken-ready, §26 |
| D2 | serialize timeline, §23 |
| D3 | resume retained, §17 |
| D4 | no cross-event dedup, §17 |
| D5 | one mixed sidecar, §25 |
| D6 | `{stem}.<codec>`, §25.6 |
| D7 | typed visible availability, §30 |
| D8 | no ElevenBytes env key, §18 |
| D9 | one SAPI engine, §21 |
| D10 | fixed gain only, §25 |
| D11 | E-AC-3 user default, §28 |
| D12 | ElevenBytes run6 default, §18 |
| D13 | Dallin built-in, §18 |
| D14 | duration longest, §25 |
| D15 | new synthesis generation, §27 |
| D16 | first + three retry, §15 |
| D17 | no partial sidecar, §25 |
| D18 | explicit amix normalize, §25 |
| D19 | per-voice profiles, §28 |
| D20 | keep old sidecars, §25 |
| D21 | base + voice offset, §25 |
| D22 | explicit spatial mapping, §24 |

## 49. Ostatnia bramka przed implementacją

Implementacja może zacząć się po:

- akceptacji tego planu;
- finalnym statusie wymagań;
- zamknięciu Fali 0;
- zielonym baseline;
- potwierdzeniu feature branch.

Nie trzeba przed pierwszym kodem znać:

- finalnych heurystyk V1–V5;
- schedulera v2;
- cleanup etapu 7;
- GUI.

Trzeba znać:

- SAPI timeout/restart contract;
- channel matrices;
- default concurrency;
- default codec profiles;
- ElevenLabs default model;
- per-voice native rate/volume i post-process tempo;
- queue/deadline bounds;
- reference episodes.

Plan po zatwierdzeniu jest wykonywany falami.

Każda fala:

1. ma mały zakres;
2. zaczyna od testu zachowania;
3. kończy się pełnymi bramkami;
4. dostaje osobny commit;
5. jest reviewowana przed następną ryzykowną falą;
6. nie usuwa istniejących wymagań;
7. nie dotyka plików usera.
