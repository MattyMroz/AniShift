---
kind: review
status: fail
reviewed-state: docs/work/11-elevenreader-tts/{plan,specification,file-map}.md, pierwsza wersja z 2026-10-25
date: 2026-10-25
---

# Review: plan i specyfikacja silnika ElevenReader — runda 1

## Zakres

- przedmiot: `plan.md`, `specification.md`, `file-map.md` w pierwszej wersji;
- baseline: AniShift `4365a51`; EDP stan roboczy z dysku;
- authority: `intent.md`, `AGENTS.md` repo i obszarów, skille `planning`, `review`, kod obu repozytoriów;
- ryzyka: wyciek sekretów, regresja istniejących silników, błędny design granic, luki dowodowe, zgadywanie
  wykonawcy;
- poza review: wykonanie kodu (zakaz), sieć ElevenReadera.

Metoda: ponowny odczyt finalnych plików planu, potem kodu, na który plan się powołuje (scheduler, serwis, ustawienia,
architektura warstw, EDP `auto.py`, `capabilities.md`), i próba obalenia każdej decyzji scenariuszem awarii.
Recenzentem jest ten sam autor w nowej, sceptycznej rundzie — subagenci byli zakazani; zgodnie z regułą krzyżową
repo pełne review innym modelem pozostaje obowiązkiem fazy 7 planu.

## Werdykt

**Status:** FAIL

**Najważniejszy powód:** plan tworzył profil Chrome z cookies sesji w fazie 0, a dopisanie `config/elevenreader/` do
`.gitignore` odkładał do fazy 5 — w publicznym repozytorium.

## Findings

### Krytyczne

#### K1. Profil z cookies powstaje przed wpisem w `.gitignore`

- miejsce: plan §18 F0 krok 4 (spike tworzy `config/elevenreader/chrome-profile/`), F5 krok 2 (`.gitignore`);
- dowód: `.gitignore:292-296` ignoruje dziś tylko `settings.json`, `presets.json`, `watch/`, `qbittorrent/`,
  `subscriptions.json`; `config/elevenreader/` nie jest ignorowany; repozytorium jest publiczne (pamięć właściciela,
  decyzje 2026-10-14);
- wpływ: między F0 a F5 każde `git add` szerszego zakresu mogło dodać profil z cookies do historii publicznego
  repozytorium — nieodwracalne ujawnienie sesji konta;
- minimalna reakcja: wpis w `.gitignore` i weryfikacja `git check-ignore` przed pierwszym uruchomieniem Chrome,
  osobny commit od razu w F0.

### Poważne

#### P1. Ponowne użycie `read_id` przy ponowieniu startowałoby od środka dokumentu

- miejsce: plan §13.9 krok 3 (mapa `_uploaded`), §13.12 (niekompletne nagranie → ten sam `read_id`), §13.13;
- dowód: `EDP:README.md:79` — nowy dokument „always starts at the beginning”; `EDP:docs/research/capabilities.md:49`
  — `last_listened_char_offset` to „pozycja wznowienia w znakach”; plan nie miał kroku przewinięcia na początek;
- wpływ: próba po przerwanym nagraniu otwiera dokument na ostatniej pozycji, nagrywa tylko końcówkę, kontrola
  kompletności odrzuca wynik — każde ponowienie kończy się tak samo, cały dokument przepada mimo retry;
- minimalna reakcja: każda próba wgrywa nowy dokument; ponowne użycie odłożone do czasu poznania mechanizmu
  przewinięcia.

#### P2. Panel importowałby typy silnika z warstwy usług

- miejsce: plan §18 F5 krok 5 (`AppService.elevenreader_session() -> SessionState`, `-> SignInOutcome`), krok 9
  (panel);
- dowód: `tests/application/test_architecture.py:126-143` — warstwy UI importują tylko publiczną powierzchnię
  aplikacji; DTO panelu żyją w `anishift/application/service.py:137-190` i są eksportowane przez
  `anishift.application` (`anishift/cli/interactive/settings.py:15-25`);
- wpływ: test architektury czerwony albo obejście granicy warstw;
- minimalna reakcja: DTO `ElevenReaderSession` i `ElevenReaderSignIn` w aplikacji, mapowanie w fasadzie, eksport w
  `anishift/application/__init__.py`.

#### P3. Przełączenie z `elevenreader` na `elevenlabs` zostawiłoby model `eleven_v4` i alias głosu

- miejsce: spec F11, plan §18 F5 krok 6;
- dowód: gałąź `elevenlabs` w `_normalize_tts_selection` resetuje model tylko, gdy jest pusty, jest endpointem
  ElevenBytes albo modelem Edge/SAPI (`anishift/config/user_settings.py:465-474`), a głosu nie dotyka;
  `eleven_v4` nie jest na liście modeli API (`DEFAULT_MODEL_ID = "eleven_multilingual_v2"`,
  `anishift/services/tts/engines/elevenlabs/constants.py:39`);
- wpływ: płatny silnik `elevenlabs` dostaje nieistniejący model i alias `fronczewski` jako ID głosu — błąd przy
  syntezie albo nieoczekiwane zachowanie;
- minimalna reakcja: F11 obejmuje wszystkie silniki; gałąź `elevenlabs` resetuje `eleven_v4` i aliasy ElevenReadera;
  testy dla `elevenlabs`, `edge`, `sapi`.

### Mniejsze

#### M1. Reguła „TTS nie przyjmuje timestampów” bez doprecyzowania

- miejsce: plan §18 F2 krok 9; `anishift/services/tts/AGENTS.md:25-26`;
- wpływ: kolejny wykonawca może uznać czasy znaków w domenie za złamanie reguły albo przepchnąć je do pipeline;
- reakcja: dopisać do AGENTS.md, że chodzi o czasy napisów, a czasy znaków providera nie wychodzą poza domenę.

#### M2. ACL przy każdym starcie bez uzasadnienia kosztu

- miejsce: plan §13.10;
- reakcja: zapisać, że wywołanie dotyczy jednego katalogu bez rekursji i jest idempotentne.

#### M3. Tożsamość resume z ręcznie zbudowanym `chunks=(text,)`

- miejsce: plan §13.6 krok 2;
- dowód: ścieżka per kwestia liczy części przez `chunk_speech_text` (`anishift/services/tts/service.py:536-540`);
- reakcja: użyć tej samej funkcji i wymagać jednej części.

#### M4. Brak wymuszenia `concurrency=1` przy ręcznej edycji `settings.json`

- miejsce: plan §18 F5 krok 6;
- wpływ: `ElevenReaderConfig` odrzuci konfigurację w runtime zamiast naprawić ją przy wczytaniu;
- reakcja: normalizacja profilu `elevenreader:*` do `concurrency=1`.

#### M5. Nieopisane ryzyko okna konsoli sterownika Playwright pod `pythonw`

- miejsce: plan §22, §23;
- reakcja: wpis w niewiadomych i ryzykach, obserwacja w F6.

### Sugestie

#### S1. `availability(live=True)` uruchamiające przeglądarkę

Nikt w MVP nie potrzebuje żywego probe; uruchamianie Chrome z `availability` byłoby zaskakującym efektem ubocznym.
Wystarczy stan konfiguracji plus `session.json`.

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
|---|---|---|
| F1 rejestr | pass | plan §18 F4 krok 6 |
| F2–F4 dokument i resume | pass | §13.6 |
| F11 przełączanie silników | fail → poprawione | P3 |
| F13 profil gitignorowany | fail → poprawione | K1 |
| F14 akcja logowania w panelu | fail (granica warstw) → poprawione | P2 |
| F21 ponowienia przejściowe | fail (P1) → poprawione | P1 |
| N1 brak sekretów | fail (K1) → poprawione | K1 |
| I2 granice domeny TTS | pass | §13.4, test kontraktu |

## Wykonane kontrole

```text
odczyt: .gitignore:286-296, tests/application/test_architecture.py:100-150, anishift/cli/interactive/settings.py:15-45,
        anishift/application/service.py:130-190, anishift/config/user_settings.py:445-474,
        anishift/services/tts/engines/elevenlabs/constants.py:35-50, EDP:README.md:79, EDP:docs/research/capabilities.md:49
wynik: opisane findingi
```

## Niewykonane kontrole

- Uruchomienie testów i bramek — zakaz uruchamiania kodu w tym zadaniu; kontrole są zaplanowane w fazach.

## Poprawki naniesione po rundzie

| Finding | Poprawka | Miejsce |
|---|---|---|
| K1 | F0 krok 2a: `.gitignore` i `git check-ignore` przed pierwszym plikiem profilu, commit `1a`; F5 krok 2 tylko sprawdza; F13 w spec | `plan.md` §18 F0, F5, §19.2; `specification.md` F13; `file-map.md` |
| P1 | każda próba wgrywa nowy dokument; tabela błędów, idempotencja, test `test_engine_uploads_a_new_document_on_every_attempt`; „Deferred” zmienione | `plan.md` §13.9, §13.12, §13.13, §14.4, §18 F4 |
| P2 | DTO w aplikacji, eksport w `anishift/application/__init__.py`, mapowanie w fasadzie | `plan.md` §18 F5 krok 5, §19.2; `file-map.md` |
| P3 | F11 dla wszystkich silników; gałąź `elevenlabs` i testy | `specification.md` F11; `plan.md` §18 F5 krok 6 i testy |
| M1 | doprecyzowanie AGENTS.md w F2 krok 9 | `plan.md` §18 F2 |
| M2 | uzasadnienie wywołania ACL | `plan.md` §13.10 |
| M3 | `chunk_speech_text` i warunek jednej części | `plan.md` §13.6 |
| M4 | wymuszenie `concurrency=1` | `plan.md` §18 F5 krok 6 |
| M5 | wpis w §22 i §23 | `plan.md` |
| S1 | `availability(live=True)` bez przeglądarki; test `test_engine_availability_never_starts_browser` | `plan.md` §13.8, §18 F4 |

## Zalecany następny krok

Runda 2 na poprawionych plikach, ze szczególnym sprawdzeniem ścieżki dokumentu w `TtsService` względem
istniejącego `_run_batch` i schedulera (czy nie powstaje nakładanie prób).
