# etap 6 — tts + tor audio (największy etap, główny zysk przebudowy)

> cel: rozbicie god-files `subtitle_to_speech.py` (1196 linii) + `tts_elevenbytes.py` (617 linii) na rejestr 5 silników + osobny tor audio.
> zależności: etap 4 (etap 5 nie blokuje — tts nie korzysta z llm, oba mogą iść równolegle). logika z `mm_avh/modules/subtitle_to_speech.py` + `modules/tts_elevenbytes.py` + wzorce EchoReader (klucz API, voice_settings) — ale dispatch przez rejestr, nie if/elif.
> DoD: pełny lektor elevenbytes na realnym odcinku brzmi/wygląda jak z obecnego kodu; edge i harpo działają; balcon poprawnie gate'owany; elevenlabs bez klucza znika z panelu; żaden plik serwisu nie przekracza ~300 linii; poza tmp/ nie powstaje żaden folder stanu.

## pliki do stworzenia/zmiany

### `utils/number_in_words.py`, `utils/text_chunker.py` (NOWE — kopie 1:1 z mm_avh)
- **odpowiedzialność:** istniejące narzędzia usera używane przez tor TTS (liczby słownie, dzielenie tekstu).
- **zawartość:** kopie bez zmian — utils nietykalne. (`execution_timer.py` dokopiować przy okazji, jeśli coś go woła.)

### `anishift/services/tts/__init__.py` (NOWY)
- **odpowiedzialność:** publiczny interfejs domeny tts.
- **zawartość:** `__all__` + re-export fasady, configu, typów, błędów.

### `anishift/services/tts/errors.py` (NOWY)
- **odpowiedzialność:** błędy domenowe tts.
- **zawartość:** `TtsError`, `TtsConfigError` (guardy rejestru), `TtsUnavailableError` (wymuszenie niedostępnego silnika), `TtsSynthesisError` (błąd generacji). liść.

### `anishift/services/tts/config.py` (NOWY)
- **odpowiedzialność:** config domeny tts.
- **zawartość:** `@dataclass(slots=True) TtsConfig` — `engine_id: str` WYMAGANY bez defaultu + pola per silnik (sub-configi silników trzymane na TtsConfig jako atrybuty — wzorzec tts MangaShift, trzeci element rejestru = nazwa atrybutu `config_attr`): głos (`voice_id`), tempo, `provider_model_id` (elevenbytes v2/v3, elevenlabs), voice_settings elevenlabs. walidacja `__post_init__`.
- **wzorzec z MangaShift:** `mangashift/services/tts/config.py` (sub-configi na TtsConfig — odstępstwo wymuszone z engine-factory-standard).

### `anishift/services/tts/constants.py` (NOWY)
- **odpowiedzialność:** stałe domeny.
- **zawartość:** `Final`: sample rate 44100, format pośredni (mp3), minimalny rozmiar poprawnego audio, limity współbieżności. bez katalogów modeli (te żyją w `constants.py` silników).

### `anishift/services/tts/protocols.py` (NOWY)
- **odpowiedzialność:** kontrakt silnika tts.
- **zawartość:** `Protocol TtsEngine`: `engine_id: str`, `is_available() -> bool` (ZAŁATWIA cross-platform — zero if-ów OS w fasadzie i pipeline), metoda syntezy (tekst/klip → bytes audio), `close()`. wspólna warstwa (timeline, cisza, czyszczenie tekstu) NIE jest częścią Protocolu — żyje w fasadzie/service.

### `anishift/services/tts/types.py` (NOWY)
- **odpowiedzialność:** typy domeny.
- **zawartość:** dataclassy: klip napisu (tekst + start/end z SRT), zsyntezowany klip (ścieżka/bytes + timing), wynik per linia (sukces/błąd), wynik przebiegu (lista błędów, statystyki, ścieżka WAV).

### `anishift/services/tts/output.py` (NOWY)
- **odpowiedzialność:** nazwy i miejsca plików wav/roboczych.
- **zawartość:** funkcje wyprowadzające ścieżki: klipy robocze i stan wznowienia w `workspace/tmp/`, finalny WAV lektora obok MKV; zero innych folderów stanu.

### `anishift/services/tts/service.py` (NOWY)
- **odpowiedzialność:** fasada — SRT → WAV lektora przez wybrany silnik.
- **zawartość:** `TtsService`: wczytanie klipów z SRT (odrzucanie pustych, czyszczenie tekstu, liczby słownie przez `utils/number_in_words`), `create_engine` z rejestru (cache per engine_id, `is_available()` guard → `TtsUnavailableError`), synteza klipów (współbieżność wewnątrz silnika), składanie timeline: dekodowanie/resampling klipów + cisza wg timingów SRT → jeden WAV (przez ffmpeg, RF64 dla >4GB — `-rf64 auto`), raport błędów per linia. sync na zewnątrz. ZERO `if engine_id == ...`.
- **skąd logika:** wspólna warstwa z `modules/subtitle_to_speech.py` (batch, timeline, cisza, mp3→wav przez pipe ffmpeg, fallback pomiaru długości dużego WAV).

### `anishift/services/tts/engines/__init__.py` (NOWY)
- **odpowiedzialność:** rejestr 5 silników tts — SSOT.
- **zawartość:** wg engine-factory-standard: `TtsEngineId = Literal["balcon", "edge", "elevenbytes", "elevenlabs", "harpo"]`, `_REGISTRY` (trzeci element = `config_attr`, wzorzec tts), `available_engine_ids()`, `create_engine()` z guardami i lazy importem (edge-tts/pyttsx3/elevenlabs SDK nie importowane na starcie apki).
- **wzorzec z MangaShift:** kanoniczny szablon engine-factory-standard, wariant tts.

### `anishift/services/tts/engines/elevenbytes/__init__.py`, `config.py`, `constants.py`, `service.py`, `api_backend.py`, `types.py` (NOWE)
- **odpowiedzialność:** silnik `elevenbytes` — ElevenLabs PROXY przez teamsp.org, klucz proxy WBUDOWANY w kod (user nie podaje własnego).
- **zawartość:**
  - `constants.py` — katalog modeli v2/v3 jako `provider_model_id` (`DEFAULT_PROVIDER_MODEL_ID`, `SUPPORTED_PROVIDER_MODEL_IDS`), endpoint proxy, limity rund, 5h timeout, sample rate.
  - `config.py` — dataclass: `provider_model_id` (wybór v2/v3 — JEDEN silnik, nie dwa), głos, batch size, retry.
  - `api_backend.py` — klient HTTP proxy (async batch, request per linia); nie zna engine_id domeny.
  - `service.py` — implementacja Protocolu: batch async wewnątrz (jeden event loop na batch, nie wycieka), retry/backoff, RUNDY dosyłania nieudanych requestów, WZNOWIENIE po crashu — stan per linia w `workspace/tmp/` (opłacone requesty nie idą drugi raz; stan sprzątany razem z tmp; przeniesienie ścieżki stanu z dzisiejszego osobnego cache do tmp/ to część migracji, nie detal), stan/cache zostaje po błędzie.
  - `types.py` — typy stanu wznowienia i odpowiedzi proxy.
- **skąd logika:** `modules/tts_elevenbytes.py` + tor elevenbytes z `subtitle_to_speech.py` — przenosić BLOKAMI z testem porównawczym na tym samym SRT (największe ryzyko parytetu całej przebudowy).

### `anishift/services/tts/engines/elevenlabs/__init__.py`, `config.py`, `constants.py`, `service.py` (NOWE)
- **odpowiedzialność:** silnik `elevenlabs` — OFICJALNE API ElevenLabs przez SDK `elevenlabs`, klucz usera. NIE mylić z elevenbytes (proxy z wbudowanym kluczem) — dwa osobne silniki w rejestrze.
- **zawartość:**
  - `config.py` — klucz z `Settings` (`ANISHIFT_ELEVENLABS_API_KEY`), `voice_id`, `provider_model_id`, voice_settings (stability, similarity_boost, style, use_speaker_boost), parametry retry/backoff.
  - `constants.py` — katalog `provider_model_id`, `RETRY_STATUS_CODES = {429, 5xx}`, minimalny rozmiar audio.
  - `service.py` — SDK `elevenlabs` (import lazy), retry/backoff wykładniczy z jitterem TYLKO na 429/przejściowe 5xx/timeout/connection (400/401/403 = natychmiastowy błąd), walidacja niepustego audio; `is_available()` = fałsz bez klucza (znika z panelu).
- **skąd logika:** wzorce EchoReader (audyt 08): klucz API, voice_settings, retry/backoff.

### `anishift/services/tts/engines/edge/__init__.py`, `config.py`, `constants.py`, `service.py` (NOWE)
- **odpowiedzialność:** silnik `edge` — edge-tts; głosy Zofia/Marek to OPCJA GŁOSU (`voice_id`), nie osobne silniki.
- **zawartość:** `constants.py` — lista głosów PL (Zofia, Marek); `service.py` — async edge-tts wewnątrz z jednym event loopem na batch; tempo/pitch przez parametry edge-tts.
- **skąd logika:** tor edge z `subtitle_to_speech.py`.

### `anishift/services/tts/engines/harpo/__init__.py`, `config.py`, `constants.py`, `service.py` (NOWE)
- **odpowiedzialność:** silnik `harpo` — pyttsx3/SAPI, głos Zosia.
- **zawartość:** `service.py` — pyttsx3 `save_to_file` z ISTNIEJĄCYM obejściem zawieszek w pętli (przenieść 1:1 z toru Harpo); `is_available()` = SAPI obecne + głos Zosia zainstalowany (sprawdzenie konkretnego głosu, nie tylko biblioteki — bez głosu silnik znika z panelu, nie wybucha).
- **skąd logika:** tor harpo z `subtitle_to_speech.py`.

### `anishift/services/tts/engines/balcon/__init__.py`, `config.py`, `constants.py`, `service.py` (NOWE)
- **odpowiedzialność:** silnik `balcon` — balcon.exe/SAPI, głos IVONA 2 Agnieszka, Windows-only.
- **zawartość:** `service.py` — wywołanie `external/bin/balabolka/balcon.exe` subprocessem (ścieżka z `platform/binaries.py`); `is_available()` = Windows AND binarka obecna AND głos Agnieszka zainstalowany — fasada i pipeline nie mają ŻADNEGO if-a na OS.
- **skąd logika:** tor balcon z `subtitle_to_speech.py`.

### `anishift/services/audio/__init__.py`, `service.py`, `types.py`, `errors.py` (NOWE)
- **odpowiedzialność:** tor audio ffmpeg = zwykły moduł (bez engines/) — obróbka WAV lektora i miks z oryginałem.
- **zawartość:**
  - `service.py` — funkcje na subprocess ffmpeg (binarka z `platform/binaries.py`): `atempo` (łańcuch filtrów dla tempa poza zakresem pojedynczego atempo — przenieść istniejący atempo-chain), zmiana głośności, `amix` lektor+oryginalne audio, konwersja do eac3/mp3, probe długości (ffprobe + fallback dla dużych WAV), `-rf64 auto` dla WAV>4GB. pliki pośrednie obok MKV (jak dziś).
  - `types.py` — parametry toru (tempo, głośności, format wyjścia) i wyniki.
  - `errors.py` — `AudioError` (non-zero exit ffmpeg z kontekstem komendy, bez `suppress(Exception)`).
- **skąd logika:** tor audio z `subtitle_to_speech.py` (sprawdzone łańcuchy filtrów — przenosić bez przepisywania).

### `anishift/pipeline/runner.py` (ZMIANA)
- **odpowiedzialność:** krok 4 — tts + tor audio.
- **zawartość:** po tłumaczeniu (i ew. korekcie): `TtsService` (engine_id/głos/tempo z ustawień) → WAV lektora → `audio.service` (atempo/volume/amix/konwersja) → gotowa ścieżka audio obok MKV; progress przez rich_console.

### `anishift/cli/settings_panel.py` (ZMIANA)
- **odpowiedzialność:** wybór silnika TTS / głosu / tempa / głośności derywowany z rejestru.
- **zawartość:** lista silników = `available_engine_ids()` filtrowana `is_available()` (balcon tylko na Windows z głosem, elevenlabs tylko z kluczem); głosy per silnik z `constants.py` silnika; dla elevenbytes wybór modelu v2/v3 (`provider_model_id`).

## kolejność implementacji

1. kopie `utils/number_in_words.py`, `text_chunker.py` → weryfikacja: diff pusty ze źródłem.
2. szkielet domeny tts (`errors`, `config`, `constants`, `protocols`, `types`, `output`) + rejestr → weryfikacja: smoke rejestru (nieznany id = ConfigError z listą; lazy import — import rejestru nie ciągnie edge-tts/pyttsx3/SDK).
3. `audio/service.py` (tor audio osobno, testowalny bez TTS) → weryfikacja: atempo/volume/amix na próbce WAV = ten sam wynik co stary kod (ffprobe: parametry + czas ±100 ms).
4. silniki proste: `edge` → `harpo` → `balcon` → weryfikacja po każdym: SRT polski (10-20 linii) → WAV; `is_available()` poprawnie gate'uje (balcon: fałsz bez binarki/głosu).
5. `elevenlabs` (oficjalne SDK) → weryfikacja: bez klucza is_available=False; z kluczem WAV przez API; retry tylko na 429/5xx/timeout (test z mockiem).
6. `elevenbytes` (największy blok — przenosić etapami: api_backend → retry/rundy → wznowienie w tmp/) → weryfikacja: test porównawczy na tym samym SRT co stary kod; przerwanie w połowie + restart = opłacone linie nie idą drugi raz; v2 i v3 przez provider_model_id.
7. `tts/service.py` fasada (klipy, timeline, cisza, RF64) → weryfikacja: WAV z timingami ±100 ms względem SRT; długi plik (symulacja >4GB lub realny maraton) przechodzi przez RF64.
8. krok 4 w runnerze + panel → weryfikacja: Enter-auto od MKV do gotowej ścieżki audio.

## jak testować

SRT polski → WAV lektora każdym dostępnym silnikiem; elevenbytes: wznowienie po przerwaniu trafia (stan w `workspace/tmp/`, opłacone requesty nie idą drugi raz), retry/rundy działają, v2 i v3 przez provider_model_id; balcon widoczny tylko na Windows z zainstalowanym głosem (`is_available`); elevenlabs bez klucza `ANISHIFT_ELEVENLABS_API_KEY` = `is_available` fałsz (znika z panelu), z kluczem generuje WAV przez oficjalne API; tor audio: atempo/volume/amix daje ten sam wynik co dziś na próbce. dodatkowo odsłuch znaków `ąęłóśćźżń` na Windows.
