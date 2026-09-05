# Ustawienia AniShift

Jedyne miejsce, w którym każde ustawienie panelu ma pełne wyjaśnienie. Kod
(`anishift/config/field_catalog.py`) trzyma tylko etykiety i jednozdaniowe opisy;
ten dokument opisuje rzeczywiste działanie w runtime, nie zamierzone ani domyślne
limity dostawców. Identyfikator w nawiasie wskazuje pole preferencji, presetu
albo połączenia; miejsce zapisu kluczy API opisuje sekcja Połączenia.

## Słownik

- **Zapytanie** — jedno wywołanie HTTP do dostawcy (tłumaczenie albo synteza).
- **Partia** — grupa linii napisów wysłana w jednym zapytaniu tłumaczenia.
- **Plik** — jedno źródło z workspace (MKV, MP4, napisy albo TXT) przetwarzane
  jako całość; „plików jednocześnie” znaczy: ile źródeł wykonuje dany etap równolegle.
- **Fragment TXT** — kawałek zwykłego tekstu, który staje się jedną linią lektora,
  gdy źródłem jest plik TXT bez wideo.
- **Profil głosu** — wartości zapisane osobno dla pary silnik + głos; zmiana
  głosu przełącza cały profil.

## Jak panel zapisuje

Reguły zapisu opisuje [kontrakt panelu](../work/plain-cli/06_state_persistence.md).
W skrócie:

- Chodzenie po liście (`↑↓`, `PageUp`/`PageDown`, `Home`/`End`, kółko) nic nie zmienia.
  Kulka `●` stoi na wartości zapisanej, nie pod kursorem.
- Zmienia dopiero jawna akcja: `Enter` na opcji, `Space` na przełączniku, `←→` na
  wierszu z liczbą, wpisany znak w edytorze tekstu. Każda zapisuje się sama, bez
  komunikatu sukcesu. Seria strzałek zwija się w jeden zapis po 0,4 s bezczynności.
- Każde wyjście (zejście z wiersza, `Esc`, `Cofnij`, zamknięcie panelu, `Ctrl+C`)
  utrwala oczekującą zmianę natychmiast. Dwa `Ctrl+C` po ostrzeżeniu porzucają
  zmianę, której nie dało się zapisać.
- Dwa wyjątki wymagają `Enter`: klucz API (pół klucza nie może trafić do `.env`)
  i linia własnego głosu (pół linii nie jest głosem).
- Niepoprawna wartość w trakcie pisania milczy; wiersz zachowuje zapisaną wartość.
  Błąd zakresu pokazuje się dopiero w wierszu statusu razem z dozwolonym zakresem.

## Co przywraca „Przywróć domyślne”

Wiersz na ekranach opcji prowadzi do potwierdzenia. Połączenia mają zamiast
resetu osobną akcję usunięcia klucza.

| Ekran | Zakres |
| --- | --- |
| Ogólne, Napisy, Tłumaczenie, Lektor | tylko pola tego ekranu; pomija pola, które po drodze przestały być aktywne (np. opcje LLM po powrocie silnika do Google) |
| Własne głosy | tylko lista własnych głosów ElevenBytes |
| Wynik, Auto | cały domyślny preset Auto (produkty i polityki razem — to jeden plik) |
| Ustawienia (root, „WSZYSTKO”) | `settings.json` w całości oprócz adresu Palantira, plus domyślny preset Auto |

Reset nigdy nie usuwa kluczy z `.env`; służy do tego `Usuń klucz` w Połączeniach.
Adres enrollmentu Palantira zostaje po każdym resecie.
Reset preferencji i presetu to dwa zapisy: jeżeli drugi zawiedzie, panel
informuje o częściowym resecie. Enter pozwala ponowić brakujący zapis.

## Kiedy zmiana zaczyna działać

Start przebiegu (Auto, Ręczny, `anishift run --preset`) kopiuje bieżące
preferencje do niezmiennego planu. Trwający przebieg do końca używa wartości
z chwili startu; zmiana w panelu dotyczy dopiero następnego przebiegu. Drugie
okno AniShift czyta `settings.json` i `.env` przy swoim starcie, więc nie
odświeża automatycznie zmian zapisanych później w innym oknie. Preset Auto
jest odczytywany osobno przy planowaniu; nie należy utożsamiać go ze snapshotem preferencji.

Zmiana ustawień sama niczego nie usuwa obok źródła. O wykorzystaniu istniejących
plików i wykonaniu etapów decyduje plan następnego przebiegu.

## Ogólne

### Kolejność przetwarzania (`processing_order_policy`)

- Co robi: `Najpierw gotowe` wykonuje każde zadanie, gdy tylko jego wejście jest
  gotowe, więc pliki mogą kończyć się w dowolnej kolejności. `Ścisła kolejność plików`
  wstrzymuje wyniki późniejszych plików, dopóki wcześniejsze nie skończą; pliki
  kończą się po kolei kosztem równoległości.
- Wartości · domyślnie: `ready_first`, `strict_natural` · `ready_first`.
- Silnik: wszystkie; działa na cały przebieg.
- Przykład: seria 12 odcinków ma być gotowa od pierwszego — `strict_natural`.

### Priorytet języków audio (`audio_language_priority`)

- Co robi: kolejność kodów języka, według której Auto wybiera osadzoną ścieżkę
  audio w MKV, gdy nie wskazano jej ręcznie.
- Format · domyślnie: kody ISO 639-2 po przecinku · `jpn, eng, zho`.
- Przykład: dubbing angielski przed japońskim — `eng, jpn`.

### Priorytet języków napisów (`subtitle_language_priority`)

- Co robi: kolejność kodów języka dla osadzonej ścieżki napisów. Plik napisów obok
  wideo (ta sama nazwa, ASS przed SRT) ma pierwszeństwo przed ścieżką osadzoną
  przy polityce `auto`.
- Format · domyślnie: kody ISO 639-2 po przecinku · `pol, eng`.
- Przykład: źródło ma napisy angielskie i niemieckie, tłumaczyć z angielskiego — `eng`.

### Jakość obrazu (`composition_quality_preset`)

- Co robi: jakość x264 przy wypalaniu napisów w MP4: `Wysoka` CRF 18, `Zrównoważona`
  CRF 21, `Kompaktowa` CRF 24. Bez wypalania obraz jest kopiowany bez ponownego
  kodowania; MKV nigdy nie koduje obrazu ponownie.
- Wartości · domyślnie: `high`, `balanced`, `compact` · `balanced`.
- Zależność: skutek tylko przy produkcie MP4 z `Napisy wypalone w MP4` innym niż `Brak`.
- Przykład: MP4 na telefon z małą pamięcią — `compact`.

## Napisy

### Znaków w linii (`subtitle_max_chars_per_line`)

- Co robi: docelowa długość jednej linii polskich napisów przy podziale tekstu.
  Dotyczy warstwy ekranowej i podziału linii dialogów. Nie jest gwarancją:
  pojedyncze długie słowo lub wyczerpanie limitu wersów może przekroczyć tę wartość.
- Zakres · domyślnie: 20–120 znaków · 42.
- Silnik: wszystkie silniki tłumaczenia; nie wpływa na napisy źródłowe.
- Przykład: duży telewizor z daleka — 36.

### Linii na napis (`subtitle_max_lines_per_event`)

- Co robi: ile linii może zająć jeden napis na ekranie po złamaniu.
- Zakres · domyślnie: 1–4 · 2.
- Przykład: 3, gdy dopuszczasz trzy wersy tekstu w jednym zdarzeniu napisów.

## Tłumaczenie

### Silnik tłumaczenia (`translation_engine`)

- Co robi: wybiera, kto tłumaczy napisy na polski.
- Wartości · domyślnie: `google` (bez klucza, darmowy endpoint), `deepl` (klucz
  DeepL), `llm` (dostawca i model z wiersza `Model tłumaczenia`) · `google`.
- Zależność: wiersze LLM widać tylko przy `llm`. Widoczne `Plików jednocześnie (Google/DeepL)`
  ma skutek wyłącznie dla Google/DeepL.
- Przykład: aby użyć wybranego modelu językowego, wybierz `llm` i `Model tłumaczenia`.

### Model tłumaczenia (`llm_provider` + `llm_provider_model_id`)

- Co robi: dostawca i identyfikator modelu używane przez silnik `llm`. Lista
  pokazuje modele z `config/anishift.models.jsonc` (aliasy Palantira) i dostawców
  z ustawionym kluczem; `Własny model…` pozwala wpisać identyfikator modelu dostawcy,
  pod warunkiem przejścia walidacji formatu.
  Obie wartości zapisują się razem.
- Domyślnie: `gemini` · `gemini-3.5-flash-lite`.
- Zależność: tylko przy silniku `llm`; dostawca musi mieć klucz w Połączeniach.
- Przykład: `Własny model…` → OpenAI → `gpt-5-mini`.

### Linii na zapytanie (`translation_batch_size`)

- Co robi: ile linii napisów trafia do jednego zapytania. `0` (wyświetlane
  jako `domyślnie`) oznacza wartość silnika: Google i DeepL po 50 linii,
  a LLM cały plik w jednym zapytaniu. Google dodatkowo nie przekracza
  15 000 znaków na zapytanie, DeepL swojego limitu bajtów.
- Zakres · domyślnie: 0–500 linii · 0.
- Silnik: wszystkie.
- Przykład: model LLM gubi numery przy długich odcinkach — 150, żeby ciąć plik na partie.

### Plików jednocześnie (Google/DeepL) (`translation_concurrency`)

- Co robi: ile plików Google albo DeepL tłumaczy równolegle. Zapytania wewnątrz
  jednego pliku idą zawsze po kolei, partia po partii; to ustawienie nie zwiększa
  równoległości w obrębie pliku.
- Zakres · domyślnie: 1–16 plików · 1.
- Silnik: `google`, `deepl`. Przy `llm` wiersz pozostaje widoczny, ale nie ma skutku;
  LLM ma własny limit `Plików jednocześnie (LLM)`.
- Przykład: 6 odcinków z DeepL i wystarczający limit konta — 3.

### Ponowień po błędzie tłumaczenia (`translation_max_retries`)

- Co robi: ile razy ponowić zapytanie po błędzie przejściowym (sieć, limit
  zapytań). Dla LLM ta sama liczba ogranicza też naprawy odpowiedzi łamiącej
  kontrakt numerowanych linii.
- Zakres · domyślnie: 0–10 · 3.
- Silnik: wszystkie.
- Przykład: darmowy Google często odrzuca zapytania — 6.

### Plików jednocześnie (LLM) (`llm_max_concurrency`)

- Co robi: ile plików silnik `llm` tłumaczy równolegle. Partie jednego pliku idą
  po kolei.
- Zakres · domyślnie: 1–16 plików · 4.
- Silnik: tylko `llm`.
- Przykład: dostawca zwraca błędy limitu — 1.

### Temperatura (`llm_temperature`)

- Co robi: losowość próbkowania modelu; puste pole zostawia wartość dostawcy.
- Zakres · domyślnie: 0,0–2,0 · 0,3.
- Silnik: tylko `llm`.
- Przykład: bardziej powtarzalne tłumaczenie — 0,1.

### Top-p (`llm_top_p`)

- Co robi: próbkowanie jądrowe modelu; puste pole zostawia wartość dostawcy.
- Zakres · domyślnie: 0,0–1,0 · 1,0.
- Silnik: tylko `llm`.

### Limit tokenów odpowiedzi (`llm_max_output_tokens`)

- Co robi: maksymalna długość jednej odpowiedzi modelu; puste pole zostawia
  wartość dostawcy. Za mały limit ucina partię i wymusza naprawę.
- Zakres · domyślnie: 1–32 000 · 32 000.
- Silnik: tylko `llm`.

### Styl (`llm_translation_style`)

- Co robi: wybiera plik promptu stylu z `anishift/services/translation/engines/llm/prompts/styles/`.
- Wartości: dostępne pliki stylów; domyślnie `neutral`.
- Silnik: tylko `llm`.

### Znaków na fragment TXT (`translation_chunk_chars`)

- Co robi: gdy źródłem jest plik TXT bez wideo, tekst jest cięty na fragmenty
  o tej maksymalnej długości (po akapitach, zdaniach i frazach). Każdy fragment
  staje się jedną linią lektora: jest tłumaczony jak linia napisów i czytany
  jako jeden klip. Przy napisach ASS/SRT nie ma żadnego skutku.
- Zakres · domyślnie: 200–4000 znaków · 750.
- Silnik: wszystkie; skutek tylko dla TXT.
- Przykład: 400 tworzy krótsze porcje tekstu do syntezy; nie ustawia długości pauz.

## Lektor

### Silnik (`tts_engine`)

- Co robi: wybiera dostawcę syntezy polskiego lektora.
- Wartości · domyślnie: `elevenbytes` (publiczne proxy ElevenLabs, bez klucza),
  `edge` (Microsoft Edge, bez klucza), `elevenlabs` (oficjalne API, klucz),
  `sapi` (głosy Windows zainstalowane w systemie) · `elevenbytes`.
- Zależność: zmiana silnika przełącza model, głos i cały profil głosu.

### Model / endpoint (`tts_provider_model_id`)

- Co robi: model albo endpoint aktywnego silnika.
- Wartości · domyślnie: ElevenBytes `run6`, `run7` · `run6`; ElevenLabs
  `eleven_multilingual_v2`, `eleven_flash_v2_5`, `eleven_v3` · `eleven_multilingual_v2`;
  Edge tylko `edge-default`; SAPI tylko `sapi5`.
- Zależność: `run7` odsłania opcje głosu (stabilność, podobieństwo, ekspresja,
  wzmocnienie mówcy).

### Głos (`tts_voice_id`)

- Co robi: głos aktywnego silnika. Profil (tempo, korekta, równoległość, opcje
  natywne) jest zapisany osobno dla każdej pary silnik + głos.
- Wartości · domyślnie: ElevenBytes alias `dallin` i aliasy z `Własne głosy` · `dallin`;
  Edge `pl-PL-MarekNeural`, `pl-PL-ZofiaNeural` · Marek; ElevenLabs wpisany
  identyfikator głosu z konta; SAPI `agnieszka`, `zosia` · `agnieszka`.
- Przykład: ElevenLabs — wklej `voice_id` z panelu ElevenLabs.

### Własne głosy (`elevenbytes_custom_voices`)

- Co robi: lista dodatkowych głosów ElevenBytes; każdy to linia
  `alias | nazwa | ID głosu`. Alias pojawia się na liście `Głos`. Pusta linia
  usuwa głos; usunięcie aktywnego aliasu wraca do `dallin`.
- Domyślnie: lista pusta.
- Silnik: tylko `elevenbytes`.
- Przykład: alias `narrator`, nazwa `Narrator spokojny` i ID skopiowane od dostawcy.

### Syntez jednocześnie (`tts_profile.concurrency`)

- Co robi: ile zapytań syntezy jednego pliku leci równolegle do dostawcy.
  Pliki są syntetyzowane po jednym naraz; miks audio poprzedniego pliku może
  trwać równolegle z syntezą następnego.
- Zakres · domyślnie: 1–100 · `dallin` 85, głosy Edge 16, ElevenLabs i własne
  głosy ElevenBytes 1.
- Silnik: `elevenbytes`, `edge`, `elevenlabs`; SAPI zawsze 1 i wiersz jest ukryty.
- Zależność: wartość należy do profilu aktywnego głosu.
- Przykład: proxy odrzuca zapytania — 20.

### Ponowień po błędzie syntezy głosu (`tts_max_retries`)

- Co robi: ile razy ponowić syntezę jednego klipu po błędzie przejściowym.
- Zakres · domyślnie: 0–10 · 3.
- Silnik: wszystkie.

### VPN ElevenBytes (`elevenbytes_vpn_enabled`)

- Co robi: kieruje zapytania ElevenBytes przez wbudowane darmowe serwery 1VPN
  z automatycznym przełączaniem przy błędzie sieci; wyłącza limit czasu
  pojedynczego zapytania w harmonogramie syntezy.
- Wartości · domyślnie: tak / nie · nie.
- Silnik: tylko `elevenbytes`.
- Przykład: proxy odpowiada błędem z Twojego adresu — tak.

### Tempo końcowe (`tts_profile.postprocess_tempo`)

- Co robi: mnożnik tempa nałożony przez FFmpeg na gotowe klipy, po syntezie.
- Zakres · domyślnie: 0,5–2,0 × · 1,0; `dallin` 1,25.
- Silnik: wszystkie; wartość należy do profilu głosu.
- Przykład: lektor nie nadąża za szybkimi dialogami — 1,3.

### Korekta głośności głosu (`tts_profile.voice_mix_offset_db`)

- Co robi: poprawka w dB dodawana do `Głośność lektora` dla tego głosu.
- Domyślnie: 0 dB; `dallin` −2 dB, SAPI Agnieszka +2 dB.
- Silnik: wszystkie; wartość należy do profilu głosu.

### Tempo natywne (`tts_profile.native_rate`)

- Co robi: tempo mowy ustawiane u dostawcy, przed `Tempo końcowe`.
- Format · domyślnie: Edge `+40%` (od `-100%` do `+100%`); SAPI Agnieszka liczba
  całkowita −10…10 · 5; SAPI Zosia słowa na minutę ≥ 1 · 200.
- Silnik: `edge`, `sapi`.

### Głośność natywna (`tts_profile.native_volume`)

- Co robi: głośność ustawiana u dostawcy.
- Format · domyślnie: Edge `+0%` (od `-100%` do `+100%`); SAPI Agnieszka 0–100 · 65;
  SAPI Zosia 0,0–1,0 · 0,7.
- Silnik: `edge`, `sapi`.

### Wysokość głosu (`tts_profile.native_pitch`)

- Co robi: przesunięcie wysokości głosu Edge.
- Format · domyślnie: od `-100Hz` do `+100Hz` · `+0Hz`.
- Silnik: tylko `edge`.

### Stabilność, Podobieństwo, Ekspresja, Wzmocnienie mówcy (`tts_profile.engine_options.stability`, `tts_profile.engine_options.similarity_boost`, `tts_profile.engine_options.style`, `tts_profile.engine_options.use_speaker_boost`)

- Co robi: parametry głosu ElevenLabs przekazywane wprost do dostawcy.
- Zakres · domyślnie: 0,0–1,0 · 0,5; 0,0–1,0 · 0,75; 0,0–1,0 · 0,0; tak / nie · tak.
- Silnik: `elevenlabs` oraz `elevenbytes` z endpointem `run7`.
- Przykład: głos „pływa” między klipami — stabilność 0,7, ekspresja 0,0.

### Prędkość natywna (`tts_profile.engine_options.speed`)

- Co robi: prędkość mowy ElevenLabs po stronie dostawcy, przed `Tempo końcowe`.
- Zakres · domyślnie: 0,7–1,2 · 1,0.
- Silnik: tylko `elevenlabs`.

### Format natywny (`tts_profile.engine_options.output_format`)

- Co robi: format pobierany z ElevenLabs (oficjalne tokeny MP3, Opus, WAV);
  końcowy kodek lektora i tak wynika z `Kodek lektora`.
- Domyślnie: `mp3_44100_128`.
- Silnik: tylko `elevenlabs`.

### Kodek lektora (`tts_output_profile`)

- Co robi: kodek pliku lektora zapisywanego obok źródła i ścieżki lektora w MKV.
- Wartości · domyślnie: `aac`, `eac3`, `flac`, `mp3`, `opus`, `wav` · `eac3`.
- Zależność: `Bitrate lektora` widać tylko dla kodeków stratnych.

### Bitrate lektora (`tts_output_bitrate`)

- Co robi: bitrate FFmpeg dla kodeka stratnego. Puste pole oznacza wartość
  zależną od kodeka i liczby kanałów, np. stereo: EAC3 `384k`, AAC `256k`,
  MP3 `320k`, Opus `192k`.
- Format: liczba z `k` albo `M`, np. `192k`.
- Zależność: tylko `aac`, `eac3`, `mp3`, `opus`.

### Głośność lektora (`narrator_mix_base_gain_db`)

- Co robi: wzmocnienie lektora w dB podczas miksu z oryginałem; do niego dodawana
  jest `Korekta głośności głosu`.
- Domyślnie: 7 dB.

### Głośność oryginału (`original_gain_db`)

- Co robi: wzmocnienie oryginalnej ścieżki w dB podczas miksu z lektorem.
- Domyślnie: 0 dB.
- Przykład: muzyka zagłusza lektora — −4.

## Wynik (`requested_products`)

Produkty domyślnego presetu Auto, zapisane w `config/presets.json`. Co najmniej
jeden musi być zaznaczony; wybór zapisuje się przy każdym `Enter`/`Space`.

| Produkt | Identyfikator | Co powstaje obok źródła |
| --- | --- | --- |
| Polskie napisy | `full_pl` | pełne polskie napisy w formacie z `Format napisów` |
| Polski lektor | `narration_audio` | miks lektora z oryginałem w kodeku z `Kodek lektora` |
| MKV | `mkv` | MKV z oryginalnymi ścieżkami plus `Ścieżki MKV` |
| MP4 | `mp4` | MP4 z dźwiękiem z `Dźwięk MP4` i ewentualnie wypalonymi napisami |
| Napisy źródłowe | `source_subtitles` | napisy źródłowe wyodrębnione do pliku |
| Polskie dialogi | `spoken_pl` | tylko linie czytane przez lektora |
| Polskie napisy ekranowe | `displayed_pl` | linie zaklasyfikowane jako ekranowe, np. szyldy |

Domyślnie: `full_pl` i `narration_audio`.

## Auto

Polityki domyślnego presetu Auto; również w `config/presets.json`. Ręczny ma
własne wybory na każdy przebieg (źródło, ścieżki, rola zewnętrznego audio) i ich
nie zapisuje.

### Źródło napisów (`subtitle_source_policy`)

- Co robi: skąd brać napisy do tłumaczenia. `Automatycznie`: plik obok źródła
  o tej samej nazwie (ASS przed SRT), a gdy go nie ma, osadzona ścieżka według
  `Priorytet języków napisów`. `Plik obok źródła`: tylko plik obok; brak to odmowa
  przed startem. `Osadzone w MKV`: tylko ścieżka osadzona. `Bez napisów`: produkty
  wymagające tekstu są odmawiane.
- Wartości · domyślnie: `auto`, `sidecar`, `embedded`, `none` · `auto`.

### Język źródła (`source_subtitle_language`)

- Co robi: zastępuje język z metadanych napisów. Puste pole zostawia metadane
  jako podstawę wyboru; brak oznaczenia nie potwierdza polskiego tekstu.
  `pl`, `pol` i `pl-PL` znaczą polski.
- Domyślnie: puste.
- Przykład: ścieżka bez oznaczenia języka, a wiesz, że jest angielska — `eng`.

### Tłumaczenie (`translation_action`)

- Co robi: `Automatycznie` tłumaczy, gdy źródło nie jest polskie. `Zawsze tłumacz`
  tłumaczy także polskie źródło. `Nie tłumacz` publikuje produkty PL tylko z
  polskiego źródła; niepolskie źródło to odmowa przed startem, a napisy źródłowe
  można nadal wypalić bez tłumaczenia.
- Wartości · domyślnie: `auto`, `translate`, `do_not_translate` · `auto`.

### Format napisów (`subtitle_output_format`)

- Co robi: format polskich produktów napisów: `Jak źródło` zachowuje ASS lub SRT
  źródła, `ASS` i `SRT` wymuszają format.
- Wartości · domyślnie: `preserve`, `ass`, `srt` · `preserve`.

### Ścieżki MKV (`mkv_tracks`)

- Co robi: ścieżki dokładane do MKV obok oryginalnych: napisy źródłowe, polskie
  napisy, polskie napisy ekranowe, polski lektor. Pusty wybór daje MKV z
  oryginalnymi ścieżkami. Dołożenie napisów źródłowych może powielić ścieżkę
  osadzoną.
- Wartości · domyślnie: `source_subtitles`, `full_pl_subtitles`,
  `displayed_pl_subtitles`, `narration_audio` · brak.
- Zależność: tylko gdy w Wynik zaznaczono MKV.

### Dźwięk MP4 (`mp4_audio_source`)

- Co robi: `Automatycznie` daje polski lektor, gdy w Wynik jest `Polski lektor`,
  inaczej oryginalne audio. `Oryginalne audio` i `Polski lektor` wymuszają wybór;
  lektor bez produktu audio i tak uruchamia syntezę i miks.
- Wartości · domyślnie: `auto`, `original`, `narration` · `auto`.
- Zależność: tylko gdy w Wynik zaznaczono MP4.

### Napisy wypalone w MP4 (`burn_subtitle_product`)

- Co robi: które napisy wypalić w obraz MP4. Każda wartość poza `Brak` koduje
  obraz ponownie zgodnie z `Jakość obrazu`.
- Wartości · domyślnie: `none`, `source`, `full_pl`, `displayed_pl` · `none`.
- Zależność: tylko gdy w Wynik zaznaczono MP4.

## Połączenia

Klucze leżą w `.env` obok kodu, nigdy w `settings.json`. Zmienna systemowa o tej
samej nazwie ma pierwszeństwo (wiersz pokazuje `skonfigurowane · system`).
Panel maskuje wartości kluczy. `Usuń klucz` kasuje wpis z `.env`;
reset panelu kluczy nie rusza.

| Połączenie | Identyfikator | Zmienna w `.env` | Używa |
| --- | --- | --- | --- |
| Palantir Foundry | `palantir_token` | `ANISHIFT_PALANTIR_TOKEN` (zapasowo `FOUNDRY_API_TOKEN`) | modele Palantira z katalogu; `Testuj połączenie` sprawdza wybrany model |
| Palantir Foundry · Adres | `palantir_enrollment_base_url` | zapisany w `settings.json`, nie w `.env` | adres `https://` enrollmentu z trasami proxy Foundry; puste pole blokuje modele Palantira |
| Gemini | `gemini_api_key` | `ANISHIFT_GEMINI_API_KEY` | silnik `llm`, dostawca `gemini` |
| OpenAI | `openai_api_key` | `ANISHIFT_OPENAI_API_KEY` | silnik `llm`, dostawca `openai` |
| Anthropic | `anthropic_api_key` | `ANISHIFT_ANTHROPIC_API_KEY` | silnik `llm`, dostawca `anthropic` |
| DeepSeek | `deepseek_api_key` | `ANISHIFT_DEEPSEEK_API_KEY` | silnik `llm`, dostawca `deepseek` |
| OpenRouter | `openrouter_api_key` | `ANISHIFT_OPENROUTER_API_KEY` | silnik `llm`, dostawca `openrouter` |
| OpenAI-compatible | `openai_compatible_api_key` (opcjonalny) | `ANISHIFT_OPENAI_COMPATIBLE_API_KEY` | silnik `llm`, dostawca `openai_compatible` (własny serwer albo brama) |
| OpenAI-compatible · Adres | `openai_compatible_base_url` | `ANISHIFT_OPENAI_COMPATIBLE_BASE_URL` | bazowy URL tego serwera |
| DeepL | `deepl_api_key` | `ANISHIFT_DEEPL_API_KEY` | silnik tłumaczenia `deepl` |
| ElevenLabs | `elevenlabs_api_key` | `ANISHIFT_ELEVENLABS_API_KEY` | silnik lektora `elevenlabs`; ElevenBytes go nie używa |

## Pola poza panelem

`settings.json` trzyma też pola, których panel nie pokazuje:

- `primary_model_alias` — alias modelu głównego z katalogu, celowo ukryty; żaden
  ekran go nie zmienia i nie ma wpływu na tłumaczenie.
- `schema_version` i `tts_timeline_policy` — wewnętrzne; nie służą do ręcznej konfiguracji.
