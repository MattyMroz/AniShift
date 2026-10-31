---
kind: review
status: fail
reviewed-state: f3e6980..ee12184 na work/tts/01-elevenreader (7 commitów)
date: 2026-10-31
---

# Review: poprawki po recenzji gałęzi ElevenReader

## Zakres

- przedmiot: `git diff f3e6980..ee12184`: `e075f6e` (P1), `6b8db15` (P2, M2), `85d6ce8` (M1), `79c9350` (M3),
  `a08e29e` (M6), `bba4971` (M4, S1), `ee12184` (P3: rozpoznawanie osieroconego uploadu po oknie wgrania i tytule).
- baseline: `f3e6980` i findingi z `reviews/01-final-branch.md`.
- authority: `specification.md` (F19, F23, F24, F27, F28, N1, Z1), `plan.md` §7.10 i §7.14, AGENTS.md (root,
  `anishift/`, `tests/`, `engines/elevenreader/`), fakty z żywego konta podane w briefie (kształt `GET reads`, 645
  dokumentów właściciela, `title` = pierwsze zdanie treści, pola `added_at_unix`, `from_user_import`,
  `original_file_type`, `char_count`).
- ryzyka: usunięcie dokumentu właściciela; nasz dokument zostawiony bez widocznego stanu; stan bez wyjścia po
  limicie czasu lub anulowaniu; legacy; tekst dokumentu i sekrety w logach i plikach.
- poza review: M5 (`.claude/settings.json`), testy `-m network`, żywa strona, panel, Chrome, zawartość `config/`.

## Werdykt

**Status:** FAIL

**Najważniejszy powód:** P1, P2, M1, M2, M4 i M6 są naprawione u przyczyny i mają testy zdolne wykryć regresję.
Nowa reguła P3 dobrze chroni dokumenty właściciela, ale „zero dopasowań po `listed_by`” rozlicza krok jako
posprzątany bez dowodu, że dokument nie istnieje. Pierwsza strona `GET reads` nie musi obejmować okna wgrania, a
`read_id` nie przeżywa końca procesu. Każde niedokończone `delete_read` staje się więc po restarcie wyszukiwaniem
sieroty, które może się rozliczyć po cichu, a dokument zostaje na koncie. Sprawdziłem to na fałszywej stronie:
krok rozliczony, brak `DELETE`, brak ostrzeżenia. Poprawka jest mała, ale wymaga decyzji (niżej).

## Findings

### Krytyczne

Brak.

### Poważne

#### P4. Brak dopasowania traktowany jako dowód, że dokumentu nie ma: nasz dokument zostaje bez widocznego stanu

- miejsce / scenariusz: `api_backend.py` `_delete_orphan`: gdy `found` jest puste i `time.time() >= trace.listed_by`,
  funkcja zwraca `True` (krok rozliczony). Gdy w oknie nie ma żadnego importu, nie zostawia nawet wpisu w logu; gdy
  są importy o innym tytule, zostawia tylko `logger.warning`. Trzy realne drogi do takiego wyniku przy dokumencie,
  który wciąż jest w bibliotece:
  1. **Paginacja.** Kod czyta tylko pierwszą stronę i ignoruje `has_more`. `save_cleanup` usuwa `read_id` przed
     zapisem, więc dokument ze znanym id, którego `DELETE` nie zdążył się wykonać (sieć padła przy końcu przebiegu,
     limit 15 s w `TtsService.close`, zabity rezydent, wyłączony komputer w trakcie nagrywania), po restarcie jest
     szukany jak sierota. Takie wyszukiwanie biegnie przy następnej próbie albo przy logowaniu z panelu, czyli po
     godzinach lub dniach, a `listed_by` dawno minęło. Na koncie z 645 dokumentami i `has_more` wystarczy kilka
     nowych importów albo sortowanie inne niż „od dodania”, a dokumentu nie ma na pierwszej stronie. Uzasadnienie w
     `engines/elevenreader/AGENTS.md` („paginacja nie jest potrzebna, dopóki okno wgrania obejmuje minuty”) myli
     szerokość okna z czasem, jaki minął od wgrania. Ten sam dokument mówi, że czas zegarowy ma zachować okno „po
     restarcie procesu i komputera”, więc sam przewiduje wyszukiwanie po długiej przerwie.
  2. **Tytuł inny niż prefiks.** Dopasowanie wymaga, żeby `title` był prefiksem dokumentu kończącym się na granicy
     słowa, dosłownie, z normalizacją tylko białych znaków. Na żywo sprawdzono jedną próbkę
     („Test listy dokumentów! …”). Pierwsze kwestie odcinków zaczynają się od myślnika dialogowego, „♪”, cudzysłowu
     albo wielokropka; jeśli serwer je usuwa, przycina długie zdanie albo inaczej dzieli zdania, nasz dokument trafia
     do `uploads` bez dopasowania. Krok zostaje wtedy rozliczony z samym wpisem w logu.
  3. **Zegar.** Gdy zegar lokalny różni się od serwera o więcej niż `_CLOCK_SKEW_S` (300 s), dokument wypada z okna.
     Krok zostaje rozliczony po cichu, bez wpisu w logu.
- dowód: DIRECT, czyli kod i uruchomiona sonda na fałszywkach z testów
  (`scratchpad/rev02/probe.py`, `ReaderPage` + `FakePlaywrightPage`, odpowiedź z `has_more: true`):
  - ślad sprzed 3 dni, pierwsza strona z 5 nowszymi dokumentami: `pending=()`, `deleted=[]`, brak logów;
  - ślad z dokumentu „- Hej! - Co tam? …” i tytuł serwera „Hej!”: `pending=()`, `deleted=[]`, tylko WARNING
    „matched no document imported at that time”.

  Prawdopodobieństwo drogi 1 zależy od nieznanego rozmiaru strony i porządku sortowania: ASSUMED. Ścieżka kodu,
  która rozlicza krok, jest pewna.
- wpływ: dokument z treścią odcinka zostaje w bibliotece właściciela, a wiersz SESJA, ostrzeżenie doctora i
  `CLEANUP_WARNING` znikają. Łamie to F28 („śmieci na koncie nie zostają w żadnej ścieżce”), regułę właściciela
  „żadnych cichych zatrzymań” i własne zdanie AGENTS.md silnika, że krok nigdy nie jest rozliczany po cichu.
- minimalna reakcja (DESIGN FLAW, decyzja właściciela przy wyborze A):
  - A (najprostsza): zgoda właściciela na zapis `read_id` w `config/elevenreader/session.json` (katalog z
    `restrict_directory`, w `.gitignore`; `read_id` nie jest tokenem, `DELETE` i tak wymaga zalogowanej sesji).
    Wtedy restart i przerwane sprzątanie kończą się `DELETE reads/{id}`, a wyszukiwanie po oknie zostaje tylko dla
    anulowania w trakcie uploadu, gdzie założenie „minuty” rzeczywiście obowiązuje. Wymaga zmiany N1 i AGENTS.md.
  - B (bez zmiany N1): rozliczać „zero dopasowań” tylko wtedy, gdy lista dowodnie obejmuje okno, czyli
    `has_more is False` albo na stronie jest import z `added_at_unix < pressed_at − _CLOCK_SKEW_S`. Do tego trzeba
    potwierdzić na żywo porządek sortowania i parametr kursora (`next_cursor`) i przewijać strony z twardym
    limitem. W przeciwnym razie krok zostaje zaległy i widoczny, a bez przewijania może tak zostać na zawsze.
  - W obu wariantach import z okna bez dopasowania tytułu powinien zostawić stan widoczny w panelu, nie tylko w logu.
    Test: zaległy ślad sprzed dni i pierwsza strona z `has_more: true` bez tego dokumentu nie mogą rozliczyć kroku.

### Mniejsze

#### M7. Jeden kandydat może być cudzym dokumentem; `char_count` z listy nie jest wykorzystany

- miejsce / scenariusz: `_delete_orphan` + `_titled`. Nasz upload nie powstał na serwerze (anulowanie przed
  przetworzeniem) albo został już usunięty, a ślad przetrwał (nieudany zapis `session.json`). Właściciel lub inne
  jego narzędzie zaimportował w tym samym oknie (ok. 10–12 min) plik `.txt`, którego pierwsze zdanie jest
  prefiksem naszego dokumentu. Prefiksy obejmują pojedyncze słowa („Hej!”, „Co?”, „Nie.”).
- dowód: DIRECT (sonda): ślad „Hej! Co tam? …”, lista z jednym importem właściciela „Hej!” →
  `DELETE …/reads/u:owner`. Wystąpienie w praktyce: ASSUMED, bardzo rzadkie.
- wpływ: nieodwracalne usunięcie dokumentu właściciela, choć przy wąskim zbiegu warunków.
- minimalna reakcja: zapisać w `DocumentTrace` długość wgranego tekstu (liczbę, nie tekst) i wymagać
  `read["char_count"] == trace.chars`; zgodność `char_count` z listy z długością wgrania sprawdzić raz w teście
  sieciowym. Ten sam warunek rozstrzyga też większość przypadków „kilku kandydatów”.

#### M8. Skróty tytułów w `session.json` da się odwrócić słownikiem, słowo po słowie

- miejsce / scenariusz: `document_titles` zapisuje SHA-256 każdego prefiksu na granicy słowa (do 200 znaków), bez
  soli. Znając prefiks z k słów, następne słowo odgadnie się, haszując prefiks z każdym słowem ze słownika. Tak da
  się odtworzyć do 200 znaków tekstu.
- dowód: DIRECT (`sha256("Hej!")` jest w `trace.titles`); test
  `test_save_cleanup_owed_steps_are_saved_without_read_id_or_text` sprawdza tylko jawny tekst.
- wpływ: mały, bo plik jest lokalny, z ograniczonym ACL, a tekst to napisy właściciela. Twierdzenie „bez tekstu
  dokumentu w plikach” (AGENTS.md silnika, plan §7.10, N1) jest jednak nieprawdziwe.
- minimalna reakcja: poprawić opis (skróty prefiksów, odwracalne słownikowo) albo zmienić sposób zapisu, np. przy
  wariancie A z P4 skróty mogą zniknąć.

#### M9. Błąd zadania bierze pierwszą porażkę całego batcha, nie porażkę brakującej kwestii

- miejsce / scenariusz: `tts_handler._raise_missing_clip(result.failure)`. `failure` to pierwsza porażka w
  `executions` (`services/tts/service.py` `_batch_result`), a `_split_signs` przenosi ją do obu połówek. Przy
  silniku „kwestia po kwestii” z szyldami w tym samym batchu panel może pokazać błąd i podpowiedź szyldu, choć
  zadanie pada z powodu kwestii dialogu. W ElevenReaderze cały dokument ma jedną porażkę, więc F27 działa.
- dowód: DIRECT (kod); scenariusz z różnymi błędami szyldu i dialogu: ASSUMED.
- wpływ: mylący komunikat w rzadkim przypadku.
- minimalna reakcja: nic przed merge albo osobny drobny follow-up (porażka per kwestia).

#### M10. Ścisły odczyt `session.json` gubi zaległy `restore` z poprzedniego formatu

- miejsce / scenariusz: `read_session` zwraca `None` przy braku `documents` (stary format z `delete_document`) albo
  przy jednym wadliwym wpisie. `load_cleanup` daje wtedy pusty `AccountCleanup`, a zaległe przywrócenie głosu konta
  ginie bez śladu. Panel do pierwszej kontroli pokazuje brak sesji. Zgodne z regułą „zero legacy” (bez migracji w
  produkcie), ale stary plik istnieje tylko u właściciela.
- dowód: DIRECT (kod, test `test_read_session_corrupt_file_returns_none` ze starym formatem). Stan pliku właściciela:
  niesprawdzony (zakaz dotykania `config/`).
- wpływ: jednorazowy. Jeśli stary plik miał `restore` różne od `null`, głos konta zostaje zmieniony bez komunikatu.
- minimalna reakcja: przed merge raz zajrzeć do `config/elevenreader/session.json` u właściciela. Jeśli ma stary
  format z `restore`, ustawić głos ręcznie albo jednorazowym skryptem w `scripts/tmp/`. Po teście sieciowym z
  `ee12184` plik ma już nowy format.

### Sugestie

- S5. M3: przy przejściu na `elevenlabs` alias ElevenReadera zamienia się na `dallin`, ale ElevenLabs też go nie zna
  (`resolved_tts_voice_id` rozwija `dallin` tylko dla `elevenbytes`; katalog ma dla ElevenLabs pustą listę i domyślne
  `""`). Zgodne z poprawionym F19 i z dotychczasowym przejściem z ElevenBytes, a skutek (błąd głosu przy syntezie)
  pozostaje. Jedno źródło prawdy: domyślna wartość z `field_catalog._tts_voice_values`.
- S6. `CLEANUP_WARNING` mówi „usuń … ostatni dokument”, a przy „kilku kandydatach” trzeba usunąć wszystkie
  pasujące.
- S7. Brak testu granicy okna (`added_at = pressed_at − 301` albo `listed_by + 301`); test z `u:old` sprawdza
  tylko odległość godziny.
- S8. Anulowanie w trakcie uploadu zostawia krok zaległy do `listed_by` (do 120 s), więc `close()` od razu loguje
  `CLEANUP_WARNING` „nie udało się posprzątać”, choć sprzątanie dokona się przy następnej próbie.

## Zgodność z kontraktem

- P1 (F23, F27): pass. `build_narration_manifest` → `_raise_missing_clip` buduje `ExecutionError` z kodem, treścią
  i sugestią `result.failure`. Sugestia jest dopisana do `message`, bo panel pokazuje `public_error` (samo
  `context.message`). Bez `failure` zostaje ogólny komunikat. `details` nie są przenoszone, więc nic nie wycieka.
  Test `test_tts_handler_failed_line_fails_task_with_engine_message_and_hint` (oba warianty `reads_document`)
  sprawdza kod, sugestię i dokładny tekst `public_error`. Zastrzeżenie: M9.
- P2: pass. `_within_deadline(request.deadline_s)` (3600 s z `_TTS_REQUEST_TIMEOUT_S`) obejmuje kartę i `_read`;
  wygasły limit daje `TtsTimeoutError`, obcy `TimeoutError` przechodzi dalej (`limit.expired()`).
  `set_page_speed`, `press_play`, `check_page_speed` i `player_state` idą przez `_unless_cancelled`. Sprzątanie
  biegnie w `finally` pod `_finish_shielded`, poza limitem; każdy krok ma 15 s. Wygaśnięcie w trakcie wstępnego
  `clean_account` w `_read` czeka na jego koniec, potem zamienia się w `TtsTimeoutError` (osłona przechwytuje
  anulowanie i rzuca je ponownie, a `asyncio.timeout` je rozpoznaje). Testy: `…_hung_page_times_out_at_deadline…`
  (wisi `player_state`, deadline 0,2 s, zewnętrzny limit 5 s) i parametryzowany `…_cancel_while_page_hangs…`
  dla czterech wywołań. Bez poprawki oba by zawiodły. Stanu bez wyjścia nie znalazłem. Poza limitem zostają
  start Chrome (ograniczony `CONNECT_ATTEMPTS`) i zamknięcie przeglądarki, jak opisuje AGENTS.md.
- M1 (F24, F28): pass. Wiersz `elevenreader-cleanup` przy każdym silniku (`_tts_items`); Enter uruchamia
  `_start_sign_in` bez warunku silnika. Doctor przy innym silniku daje WARN, gdy `cleanup_pending`. Są testy panelu
  i doctora.
- M2: pass. `ChromeSession._attach` w `try/except PlaywrightError` → `unavailable_error(...) from None`;
  `start()` zamyka sesję po każdym `BaseException`. Test dla awarii sterownika i `add_init_script` sprawdza też
  zwolnienie blokady i zakończenie procesu.
- M3 (F19): pass według zalecenia z recenzji 01. Zostaje uwaga S5.
- M4: pass. F15, U7, I1 i D1 zgodne z kodem; README EN/PL wymieniają Chrome; Z1 dopuszcza listę `reads` wyłącznie
  do odszukania własnego uploadu.
- M6: pass w kodzie (`elevenreader_dir()`, klipy przez `FfmpegClipService`, sprawdzenie WAV 48 kHz mono).
  Uruchomienie: REPORTED.
- S1 (ścieżki absolutne w dokumentach): pass; `git grep` w `docs/work/11-elevenreader-tts`, `anishift/` i `tests/`
  nie znajduje `C:\Users`, `MATTYM~1` ani ścieżek tymczasowych (poza historyczną recenzją 01, która ich nie ma).
- P3, kształt `GET reads`: pass. Kod czyta `reads`, brak listy zostawia krok zaległy. Rozpoznanie po oknie i
  tytule: pass dla ochrony cudzych dokumentów w typowym przypadku (wymaga `from_user_import`, `text/plain`, okna i
  tytułu; wielu kandydatów → nic nie usuwa). Fail dla rozliczania przy braku dopasowania (P4). Zostaje rzadkie
  ryzyko M7.
- Zero legacy: pass. `orphan_visible_at`, `read_ids`, `has_document`, `_DOCUMENT_TITLES`, `_LISTED_AT_ONCE` i
  pole `delete_document` w pliku zniknęły z kodu, testów i dokumentów (`git grep` na `ee12184`).
  `SessionRecord.delete_document` jest teraz pochodną właściwością `documents`, nie aliasem. Brak migracji
  starego formatu w produkcie (M10).
- N1 (logi): pass. Nowe wywołania loggera mają tylko liczby i rodzaj kroku, bez `read_id`, tytułu i tekstu.
  N1 (pliki): zastrzeżenie M8.
- Reguły AGENTS.md: pass. Jednolinijkowe docstringi, stałe `Final` z opisem pod spodem (`_UPLOAD_TYPE`,
  `_CLOCK_SKEW_S`, `_TITLE_CHARS`), typowane zmienne lokalne, brak komentarzy opisowych w kodzie i testach.
- Commity: format `typ(scope): opis`, jeden temat na commit, bez stopek AI.

## Regresje i integracja

- `_unless_cancelled` przy anulowaniu z zewnątrz (także przy limicie) anuluje pracę wewnętrzną, ale na nią nie
  czeka. `upload` i `_end_page` mogą się więc przeplatać. Przeanalizowałem kolejność: anulowane zadanie uploadu
  dostaje `CancelledError` w najbliższym `await` i nie zmienia już `cleanup`, więc `swap`/`remove` nie trafiają na
  stan zmieniony przez `clean_account`. Przy tym kodzie nie znalazłem problemu.
- `TtsTimeoutError` nie należy do `_KEEP_BROWSER_ERRORS`, więc po limicie Chrome zamyka się dopiero po sprzątaniu,
  zgodnie z AGENTS.md.
- Panel i silnik zapisują `session.json` niezależnie. Gdy silnik nieaktualnym stanem w pamięci nadpisze wynik
  logowania z panelu, ślad wraca i rozlicza się przy następnym wyszukiwaniu. To bezpieczne tylko dopóki
  rozliczanie przy braku dopasowania jest poprawne (P4).

## Wykonane kontrole

```text
git log --oneline f3e6980..ee12184; git diff f3e6980..ee12184 (całość kodu, testów i dokumentów)
HEAD = ee12184, working tree czysty poza docs/work/21-playshift/

uv run pytest -o addopts="" -n 0 -q tests/services/tts/test_tts_elevenreader_{api_backend,browser,service,network}.py
  tests/application/test_tts_handler.py tests/config/test_user_settings.py tests/setup/test_doctor.py
  tests/cli/test_interactive_settings_{voices,render,steps,autosave}.py tests/cli/test_interactive_wheel.py
                                                → 583 passed, 3 skipped (testy sieciowe bez ANISHIFT_ELEVENREADER_LIVE), 13,3 s
uv run ruff check --no-fix anishift/ tests/     → All checks passed!
uv run ruff format --check anishift/ tests/     → 702 files already formatted
uv run mypy anishift/ tests/                    → Success: no issues found in 704 source files

sonda (scratchpad/rev02/probe.py, fałszywki z tests/services/tts/elevenreader_fakes.py, has_more: true):
  paged-off-after-restart:  pending=() deleted=[] logs=[]                                  (P4.1)
  title-mismatch:           pending=() deleted=[] logs=[WARNING matched no document …]     (P4.2)
  owner-same-title:         pending=() deleted=[…/reads/u:owner] logs=[]                   (M7)
  sha256("Hej!") ∈ trace.titles → True                                                     (M8)

git grep na ee12184: stare nazwy (orphan_visible_at, read_ids, has_document, _LISTED_AT_ONCE, „anishift” w
  komunikatach), ścieżki absolutne w docs/work/11, anishift/, tests/
```

## Niewykonane lub nierozstrzygające kontrole

- Testy `-m network` i każde zachowanie żywej strony: rozmiar strony i porządek sortowania `GET reads`, parametr
  kursora, tytuły dla pierwszych kwestii z myślnikiem, „♪” albo cudzysłowem, zgodność `char_count` z listy z
  uploadem. Wyniki z żywego konta z briefu: REPORTED.
- Format `config/elevenreader/session.json` u właściciela (M10): zakaz dotykania `config/`.
- Pełny `uv run pytest`, `mypy --platform linux`, testy cięcia na danych Tantei: nieuruchomione w tym review.
- Panel, doctor na żywym profilu, Chrome: zakazane.

## Wymagana ocena człowieka

```text
Uruchom: decyzja właściciela do P4 — czy `read_id` może leżeć w config/elevenreader/session.json (wariant A).
Zrób: przy wariancie B jedno żywe sprawdzenie: GET reads z kursorem, porządek sortowania, rozmiar strony.
Oczekiwany wynik: wybrany wariant; dla B znany parametr kursora i porządek „od dodania”.
Zwróć uwagę na: 645 dokumentów w bibliotece — czy inne narzędzie (np. EDP) importuje na to samo konto.
```

## Ograniczenia review

- Ocena kodu, testów jednostkowych i sondy na fałszywkach, bez obserwacji żywego serwisu.
- Prawdopodobieństwo P4.1 zależy od nieznanego rozmiaru strony; P4.2 od reguł tytułów serwera, sprawdzonych na
  jednej próbce.

## Zalecany następny krok

- Właściciel wybiera wariant P4 (A albo B). Autor poprawia P4 i M7 (`char_count`) i koryguje opis M8 w AGENTS.md i
  planie; M9 i M10 mogą zostać notatkami. Potem krótka weryfikacja `_delete_orphan` przez recenzenta innego niż autor.
