---
kind: review
status: fail
reviewed-state: main..work/tts/01-elevenreader (HEAD f3e6980, 25 commitów)
date: 2026-10-31
---

# Review: gałąź ElevenReader przed merge

## Zakres

- przedmiot: cały diff `main..work/tts/01-elevenreader` (127 plików, +11 735/−3 720): silnik `elevenreader`,
  kontrakt dokumentu w TTS i scheduler, cięcie nagrania, przycinanie brzegów, mierzona głośność z limiterem,
  łączenie kwestii urwanych, szyldy w dokumencie, ustawienia, panel, doctor, `paths.py`, testy i dokumenty.
- baseline: `main`; ocena stanu gałęzi z eksportu `git archive` do katalogu tymczasowego, nie z working tree.
- authority: `specification.md` (F1–F28, N1–N7, I1–I5, Z1–Z9), `plan.md` (§7, §9, §14), `intent.md`, decyzje
  właściciela z briefu, AGENTS.md (root, `anishift/`, `tests/`, `engines/elevenreader/`).
- ryzyka: śmieci na koncie w ścieżkach błędu i anulowania, sierota bez `read_id`, mapowanie błędów, wycieki do
  logów, profil Chrome i proces, cięcie MP3, głośność, integracja z handlerem i harmonogramem, testy, reguły repo,
  prywatność.
- poza review: zachowanie na żywym koncie (testy `-m network` celowo nieuruchamiane), odsłuch, test zgodności cięcia
  na danych Tantei (brak danych i FFmpeg w eksporcie), mypy `--platform linux`, pełny `pytest`.

## Werdykt

**Status:** FAIL

**Najważniejszy powód:** wymaganie F27 („komunikat trwałego błędu w panelu mówi, co zrobić”) nie działa na
złożonym stanie: podpowiedź silnika (zaloguj się / poczekaj na kredyty / przełącz na ElevenBytes) ginie w
`TtsTaskHandler`, a zadanie kończy się ogólnym „TTS batch lacks a required clip”. Do tego brak górnego limitu
czasu próby dokumentu wbrew §7.14 planu oraz niepotwierdzony w K2 kształt `GET reads`, od którego zależy
sprzątanie dokumentu-sieroty. Wszystkie trzy poprawki są małe; poza nimi gałąź jest starannie wykonana.

## Findings

### Krytyczne

Brak.

### Poważne

#### P1. Podpowiedź trwałego błędu silnika nie dociera do właściciela (F27, F23)

- miejsce / scenariusz: `anishift/application/tts_handler.py:417` i `:421` (`build_narration_manifest`):
  kwestia bez klipu → `ValueError("TTS batch lacks a required clip")` → `ExecutionError` z tym tekstem.
  `SpeechBatchResult.failure` (pełny `ErrorContext` z `suggestion`, budowany w `services/tts/service.py`
  `_batch_result`) nie jest nigdzie czytany przez `application/` ani `cli/`. Scheduler loguje przy błędzie
  terminalnym tylko `error_code` (`services/tts/scheduler.py`, `_handle_error`). Scenariusz: sesja wygasła →
  `TtsAuthError` z `SIGN_IN_HINT` → panel pokazuje „TTS batch lacks a required clip”.
- dowód: DIRECT (kod); test `tests/application/test_tts_handler.py:447` utrwala ogólny komunikat
  (`match="lacks a required clip"`). Podpowiedzi sprawdzają wyłącznie testy samego silnika
  (`test_map_http_status_permanent_failure_suggests_elevenbytes`), nie ścieżka zadania. Ten sam ogólny
  komunikat był na `main` dla innych silników, ale F27 jest wymaganiem tego workstreamu, a gałąź przepisała tę
  funkcję.
- wpływ: przy wylogowaniu, braku kredytów lub blokadzie konta właściciel nie dostaje informacji, co zrobić; łamie
  F23, F27 i regułę „każdy błąd widoczny” w sensie użytecznym.
- minimalna reakcja: gdy wymaganej kwestii brakuje klipu, handler podnosi `ExecutionError` z treścią i sugestią
  `result.failure` (gdy jest), a nie stałym tekstem; jeden test handlera z `TtsAuthError` sprawdzający, że
  sugestia logowania trafia do błędu zadania.

#### P2. Próba dokumentu nie ma górnego limitu czasu, a część oczekiwań omija anulowanie

- miejsce / scenariusz: `application/runtime.py:676` wyłącza timeout schedulera dla silnika dokumentowego, bo
  według `plan.md` §7.14 (linie 606–608) „silnik sam pilnuje `deadline_s` dokumentu”. Silnik nigdzie nie czyta
  `request.deadline_s` (grep po `anishift/services/tts/engines/elevenreader/`: zero użyć). Dodatkowo
  `engines/elevenreader/service.py:317`, `:318`, `:353`, `:360`, `:376` (`set_page_speed`, `press_play`,
  `check_page_speed`, `player_state`) nie przechodzą przez `_unless_cancelled`; `page.evaluate`/`frame.evaluate`
  w Playwright nie ma domyślnego limitu, `click` czeka do `ACTION_TIMEOUT_S` = 120 s. `engines/elevenreader/AGENTS.md:55`
  twierdzi, że „każde długie oczekiwanie idzie przez `_unless_cancelled`”.
- dowód: DIRECT (kod, grep). Scenariusz zawieszenia (zawieszony renderer karty, `evaluate` bez odpowiedzi): ASSUMED.
- wpływ: w takim stanie zadanie TTS wisi bez końca, a anulowanie z panelu go nie przerywa (dopiero zamknięcie
  `TtsService` zatrzymuje pętlę); sprzeczne z planem i z regułą właściciela „żadnych zawieszonych stanów”.
- minimalna reakcja: owinąć `_read` w `asyncio.timeout(request.deadline_s)` mapowany na `TtsTimeoutError`
  (sprzątanie i tak biegnie w `_finish_shielded` w `finally`) i puścić pozostałe wywołania strony przez
  `_unless_cancelled`; test z fałszywą stroną, której `player_state` nigdy nie wraca.

#### P3. Sprzątanie sieroty opiera się na niepotwierdzonym `GET reads`, a K2 nie jest zamknięte

- miejsce / scenariusz: `engines/elevenreader/api_backend.py:542–554` (`_delete_orphan`) zakłada odpowiedź
  `{"reads": [{"read_id", "title"}]}`; `engines/elevenreader/AGENTS.md:66–69` sam nazywa to (oraz 402 jako brak
  kredytów) „założeniami do potwierdzenia w K2”. `plan.md:46` i `:953` (K2, K3, DoD) mają niezaznaczone pola.
  Spec Z1 (`specification.md:206–208`) dopuszcza tylko endpointy `user_config` i `reads/{id}`; listy `reads` na
  niej nie ma. Ścieżki zależne od listy: anulowanie lub zerwanie w trakcie uploadu, odpowiedź bez `read_id`,
  awaria procesu po uploadzie (`load_cleanup` → `delete_document`).
- dowód: DIRECT (kod, dokumenty); poprawność kształtu: nieznana (REPORTED jako niepotwierdzona).
- wpływ: przy innym kształcie krok `delete_orphan` nigdy się nie rozlicza: dokument może zostać na koncie, a flaga
  w `session.json` wisi na stałe (wiersz w panelu, WARN doctora); akcja „Napraw” uruchamia `sign_in`, który
  zawiedzie tak samo. Właściciel nie ma jak tego wyczyścić poza ręczną edycją `session.json`, co jest
  zawieszonym stanem i łamie „żadnych śmieci na koncie”.
- minimalna reakcja: za zgodą właściciela jedno żywe sprawdzenie listy (K2) i wpis wyniku; dopisać endpoint listy do
  Z1 albo uzasadnić wyjątek. Do tego czasu merge z jawnie zaakceptowanym ryzykiem.

### Mniejsze

#### M1. Zaległe sprzątanie znika z widoku po przełączeniu silnika

- miejsce / scenariusz: `cli/interactive/settings.py:1174–1179` pokazuje sekcję SESJA (w tym wiersz zaległego
  sprzątania) tylko przy `tts_engine == "elevenreader"`; `setup/doctor.py:274` daje SKIP przy innym silniku.
  Każdy trwały błąd silnika radzi „przełącz silnik na ElevenBytes”.
- dowód: DIRECT.
- wpływ: po przełączeniu dokument i zmieniony głos na koncie pozostają niewidoczne; zostaje tylko dawny wpis w logu
  (F28 mówi o komunikacie w panelu).
- minimalna reakcja: wiersz zaległego sprzątania i WARN doctora zależne od `session.json`, nie od wybranego silnika.

#### M2. Surowe błędy Playwright z `ChromeSession._launch` zawieszają akcję logowania w panelu

- miejsce / scenariusz: `engines/elevenreader/browser.py:149–158` (`async_playwright().start()`,
  `add_init_script`, zamykanie pustych kart) nie mapuje `PlaywrightError`. `sign_in` łapie tylko `TtsError`
  (`api_backend.py:697–703`), a `SettingsController._run_sign_in` (`cli/interactive/settings.py:1733–1737`) tylko
  `AniShiftError, OSError`; wątek kończy się wyjątkiem i `_busy` zostaje `True` z komunikatem „Zaloguj się w
  oknie Chrome albo je zamknij…”. W silniku scheduler zamienia taki błąd na ogólny przejściowy.
- dowód: DIRECT (kod); wystąpienie błędu w tych wywołaniach: ASSUMED (rzadkie).
- wpływ: zawieszony stan panelu bez komunikatu.
- minimalna reakcja: mapować `PlaywrightError` w `_launch` na `unavailable_error`.

#### M3. F19 niepełne dla ElevenLabs

- miejsce / scenariusz: `config/user_settings.py:463–500` resetuje głos ElevenReadera przy przejściu na
  `elevenbytes`, `edge`, `sapi`, ale nie na `elevenlabs`.
- dowód: DIRECT, uruchomione: `UserSettings(tts_engine="elevenreader", tts_voice_id="fronczewski")` →
  `tts_engine="elevenlabs"` → `tts_voice_id == "fronczewski"`. Test
  `tests/config/test_user_settings.py:665` parametryzuje tylko `edge` i `sapi`. Ten sam wzorzec istniał dla SAPI.
- wpływ: alias ElevenReadera trafia do ElevenLabs jako ID głosu i daje błąd głosu dopiero przy syntezie.
- minimalna reakcja: reset aliasu ElevenReadera przy `elevenlabs` i przypadek w teście.

#### M4. Dokumenty rozjechane z kodem i decyzjami

- miejsce / scenariusz: `specification.md:132–133` (F15) podaje Fronczewski 0 dB i Adam +2 dB, a kod, `plan.md`
  §7.9 i `docs/reference/settings.md:314` mają +0,5 i +2,5; U7, I1 i D1 (`specification.md:76–77`, `:183–184`,
  `:259–261`) wciąż traktują przycinanie brzegów dla wszystkich silników jako otwartą decyzję, choć właściciel ją
  podjął. README EN/PL nie zmienione, choć zakres specyfikacji je obejmuje (w wymaganiach brak Google Chrome).
- dowód: DIRECT.
- wpływ: następny wykonawca dostaje sprzeczne źródła prawdy.
- minimalna reakcja: aktualizacja spec (F15, U7, I1, D1) i wymagań w README EN/PL.

#### M5. Zmiany spoza zakresu w gałęzi funkcji

- miejsce / scenariusz: commit `24ef1e0` zastępuje `.claude/settings.json` (usuwa m.in. `deny: Read(./.env)`,
  hook SessionStart i listę `allow`, dodaje `disableClaudeAiConnectors`); `f2a3ded` zmienia `.vscode/settings.json`.
- dowód: DIRECT.
- wpływ: niezwiązane z ElevenReaderem; usunięcie zakazu czytania `.env` osłabia ochronę sekretów przed agentami.
- minimalna reakcja: potwierdzić u właściciela, że to zamówione; w przeciwnym razie osobny PR.

#### M6. Test sieciowy z własną ścieżką profilu i węższy niż S3

- miejsce / scenariusz: `tests/services/tts/test_tts_elevenreader_network.py:19` buduje
  `parents[3] / "config" / "elevenreader"` zamiast `anishift.paths.elevenreader_dir()`; test sprawdza trzy czasy
  części, a S3 wymaga „trzech zwalidowanych klipów” (bez cięcia).
- dowód: DIRECT.
- wpływ: druga kopia wiedzy o ścieżce; S3 sprawdzone tylko częściowo.
- minimalna reakcja: `elevenreader_dir()`; opcjonalnie cięcie przez `FfmpegClipService` w tym teście.

### Sugestie

- S1. `specification.md:25` i `plan.md:16–17` zawierają ścieżki absolutne z nazwą konta i katalogiem tymczasowym
  sesji; repo jest publiczne. Wystarczy opis bez ścieżki.
- S2. `recorder.chars` liczy też znaki tagów `<break…>` z wyrównania, więc ostrzeżenie „received more text than
  uploaded” może pojawiać się przy każdym dokumencie (ASSUMED; sprawdzić w logu K2). Integralność i tak chroni
  `part_spans`.
- S3. `api_backend.py:277`: lokalna `response` bez adnotacji typu (reguła AGENTS.md o typowanych zmiennych).
- S4. `_delete_orphan` usuwa każdy dokument zatytułowany `anishift`/`anishift.txt`, także własny dokument
  właściciela o tej nazwie; wystarczy zdanie w AGENTS.md silnika.

## Zgodność z kontraktem

- Kod nagrywania w AniShift, bez importu EDP; cięcie heurystyką ciszy bez modelu: pass; DIRECT (grep `whisper`,
  `ElevenDownloaderPro` w `anishift/ tests/ scripts/` = 0; `segmentation.py` czysta reguła poziomów).
- Separator „…” w osobnym akapicie (`LINE_SEPARATOR`), dokument `"\n\n…\n\n".join + "\n"`: pass; DIRECT
  (`service.py:104`, `:473–475`).
- Szyldy w tym samym dokumencie; szyld bez nagrania pominięty z ostrzeżeniem; dialog bez nagrania = błąd zadania:
  pass; DIRECT (`tts_handler.py` `_sign_batch`, `_split_signs`, `_sign_clips`, ostrzeżenie „Signs left out
  without a recording”, `signs_unrecorded`). Treść błędu zadania: patrz P1.
- Łączenie urwanych kwestii tylko dla `reads_document`: pass; DIRECT (`_narration_batch(join_open_lines=…)`,
  `runtime.py` `is_document_engine`).
- Lektor 7,5 LU nad oryginałem po downmiksie stereo, limiter −1 dBFS z `level=0`, narrator-only bez gainu i
  limitera: pass; DIRECT (`commands.loudness_command`, `output.MIX_LIMITER`, `AudioService._narrator_gain_db`).
  Słyszalny wynik w stereo i 5.1: unknown (K3, ucho właściciela).
- Przycinanie brzegów klipów dla wszystkich silników: pass; DIRECT (`normalize.py`, `EDGE_TRIM_*`, wersja
  fingerprintu 2).
- Tempo i korekta: Fronczewski 1,45/+0,5, Adam 1,35/+2,5, Dallin 1,25/0: pass w kodzie; DIRECT
  (`default_tts_voice_profiles`). Spec F15 nieaktualna (M4).
- Chrome przy nagrywaniu headless + `--mute-audio`, okno tylko w `sign_in`, zamykanie przez CDP `Browser.close` z
  10 s na zapis: pass; DIRECT (`browser.py` `_HEADLESS_ARGS`, `_request_exit`, `_stop_process`).
- Sprzątanie konta zawsze (sukces, błąd, anulowanie, `CancelledError`), zaległe kroki trwałe i ponawiane: pass dla
  ścieżek ze znanym `read_id`; DIRECT (kod i testy `test_synthesize_document_*cancel*`, `*cleans*`). Sierota bez
  `read_id`: unknown (P3). Widoczność po zmianie silnika: fail (M1).
- Żadnych cichych zatrzymań: fail częściowo (P1, P2, M2).
- Mapowanie 401/403 → `TtsAuthError`, 402 → `TtsQuotaError`, 429 → `TtsRateLimitError(Retry-After)`, 5xx i
  Playwright → przejściowe, circuit dla auth/quota/voice/config: pass; DIRECT (`map_http_status`,
  `_opens_circuit`). 402 jako brak kredytów: unknown (P3).
- Dane testowe tylko przez `quality_dir()`, bez `mm_avh_working_space` i `temp`: pass; DIRECT (grep w diffie i
  testach; `MM_AVH_TEMP` usunięte z `tests/conftest.py`).
- Zero legacy, `narrator_mix_base_gain_db` zniknął z kodu i dokumentów referencyjnych: pass; DIRECT (git grep na
  gałęzi poza historią workstreamu = 0). Jednorazowy skrypt migracji: REPORTED (poza repo, nieweryfikowalny).
- `anishift/utils/` bez usunięć, `mp3_frames.py` dopisany do manifestu przenośnych modułów: pass; DIRECT.
- Prywatność: brak nagrań, profilu i sesji w drzewie gałęzi; `config/elevenreader/` w `.gitignore`: pass; DIRECT
  (`git ls-tree -r` bez plików audio poza wcześniejszym `edge-polish.mp3`, `git check-ignore`).
- N1 (bez tokenu, `read_id`, adresu WS, tekstu, ścieżek w logach): pass w przeczytanym kodzie; DIRECT (wywołania
  loggera w silniku, `split_clip`, `_narrator_gain_db`; mapowanie Playwright `from None`) plus test
  `test_logs_never_contain_token_read_id_or_stream_address`.
- Reguły AGENTS.md: docstringi jednolinijkowe, stałe `Final` z docstringiem pod spodem, brak komentarzy opisowych:
  pass; DIRECT (skan dodanych linii). Drobna luka w typowaniu lokalnej (S3).
- F1 (rejestr i import bez Playwright): pass; DIRECT (`engines/__init__.py`, leniwe importy, test importu).
- Commity: format `typ(scope): opis`, brak stopek AI: pass; DIRECT (`git log`).

## Regresje i integracja

- `build_narration_manifest` straciło globalny warunek „batch COMPLETED”; teraz wymagana jest obecność klipu każdej
  kwestii. Dla silników „kwestia po kwestii” wynik jest równoważny (kwestia bez klipu nadal kończy zadanie
  błędem), ale komunikat pozostał ogólny (P1).
- Cięcie: granice monotoniczne z konstrukcji (`high_i ≤ mid_{i+1} ≤ low_{i+1}`), a `part_spans` odrzuca część o
  zerowym czasie, więc pusty klip nie powstanie; DIRECT (analiza `segmentation._cut`).
- Mierzony gain liczony przed `amix normalize=true`, która skaluje oba wejścia jednakowo, więc odstęp LU jest
  zachowany; `original_gain_db` działa po pomiarze, zgodnie z §7.8.
- Silnik żyje tyle co `TtsService` przebiegu; Chrome zostaje otwarty między dokumentami jednego przebiegu, więc
  w tym czasie „Zaloguj” w panelu zwraca BUSY („Lektor właśnie nagrywa”) także w krótkich przerwach. Akceptowalne.
- `TtsService.close` ma 15 s na sprzątanie i zamknięcie Chrome; przy zaległym sprzątaniu (3 kroki × 15 s) limit
  może je przerwać, a stan zostaje zapisany w `session.json` i wykonany przy następnej próbie. Zgodne z F28.

## Wykonane kontrole

```text
git archive work/tts/01-elevenreader → świeży katalog tymczasowy; uv sync --frozen (osobny .venv, bez --active)

uv run ruff check anishift/ tests/                → All checks passed!
uv run ruff format --check anishift/ tests/       → 702 files already formatted
uv run mypy anishift/ tests/                      → Success: no issues found in 704 source files (exit 0)
uv run pytest -o addopts="" -m "not network" tests/services/tts tests/application/test_tts_handler.py
  tests/application/test_tts_clips.py tests/services/audio tests/utils/test_mp3_frames.py tests/config
  tests/setup/test_doctor.py tests/text/test_boundaries.py tests/platform
                                                  → 1278 passed, 40 skipped, 3 deselected (31 s)
  pominięte m.in.: test zgodności cięcia Tantei (brak danych i FFmpeg w eksporcie), testy FFmpeg, test sieciowy

python: UserSettings elevenreader/fronczewski → elevenlabs → tts_voice_id 'fronczewski' (M3)
git grep na gałęzi: narrator_mix_base_gain_db, mm_avh_working_space, whisper, ElevenDownloaderPro, sekrety
git ls-tree -r: brak nagrań głosu, profilu i session.json; git check-ignore config/elevenreader/session.json → ignorowany
```

## Niewykonane lub nierozstrzygające kontrole

- Test zgodności cięcia N2/S2 na Tantei i Edgerunners: niewykonany (dane w `workspace/.quality` checkoutu,
  binarki w `external/`); wynik autora REPORTED.
- `mypy --platform linux`, pełny `uv run pytest` (~10 363 testów): REPORTED przez autora jako zielone.
- Testy `-m network` i każde zachowanie żywej strony (kształt `GET reads`, 402, wylogowanie w trakcie): zakazane w
  tym review.
- Uruchomienie panelu, Chrome'a i doctora: zakazane.

## Wymagana ocena człowieka

```text
Uruchom: przebieg odcinka z elevenreader (Fronczewski i Adam) na źródle stereo i 5.1.
Zrób: posłuchaj miksu; w trakcie jednego przebiegu anuluj nagrywanie.
Oczekiwany wynik: lektor czytelny nad oryginałem bez przesterów; po anulowaniu Chrome znika w kilka sekund,
  a w bibliotece ElevenReadera nie ma dokumentu „anishift”, głos konta jest jak przed przebiegiem.
Zwróć uwagę na: ucięte początki i końce słów; poziom lektora przy 5.1; wiersz SESJA w Ustawieniach po anulowaniu.
```

## Ograniczenia review

- Ocena kodu i testów jednostkowych; żadnej obserwacji żywego serwisu.
- Ścieżki Playwright zweryfikowane czytaniem i fałszywymi obiektami testów, nie prawdziwą przeglądarką.
- Przy przygotowaniu eksportu recenzent omyłkowo rozpakował drzewo gałęzi także do istniejącego katalogu
  prototypu `SCR` (`scratchpad/er/`); pliki repo (m.in. `pyproject.toml`, `uv.lock`, `README.md`, `anishift/`,
  `tests/`, `docs/`) leżą tam teraz obok plików prototypu. Usunięcie wymagało zgody, której nie było; do ręcznego
  posprzątania.

## Zalecany następny krok

- Naprawić P1 i P2 (małe zmiany w handlerze i silniku, po jednym teście), rozstrzygnąć P3 żywym sprawdzeniem K2
  albo jawną akceptacją ryzyka przez właściciela, poprawić M1–M4; potem krótka weryfikacja tych miejsc przez
  recenzenta innego niż autor poprawek.
