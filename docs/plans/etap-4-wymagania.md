# Etap 4 — tłumaczenie (pierwszy rejestr silników) — WYMAGANIA

> Ten dokument to **wymagania** — definiuje kryteria sukcesu etapu 4. Nie plan, nie kod, nie historia decyzji. Plan i decyzje architektoniczne pisze Fable po zaakceptowaniu wymagań.
> Status: **DRAFT — do przeglądu przez usera.** ✅ USTALONE. 🏗️ = propozycja architektoniczna dla Fabla (user nie rozstrzyga).
> Referencje (przeczytane w kodzie): `../mm_avh_working_space/modules/translator.py` (dedup, markery, fallback — materiał, nie wzorzec); `../MangaShift/mangashift/services/translation/` (wzorzec rejestru — przepisujemy + ulepszamy); `../../geminicli2api/apps/gemini_translator/src/` (punkt wyjścia dla systemu agentowego LLM); `anishift/services/subtitles/`, `anishift/pipeline/runner.py`, `anishift/config/` (realny stan etapu 3 — źródło prawdy).

## Zasada nadrzędna

**Przepisujemy MangaShift + dodajemy nowości + ulepszamy o rzeczy z mm_avh/geminicli2api.** Rejestr silników wg wzorca MangaShift, ale **sync** (AniShift nie ma REST). **100% albo wcale** — zero półśrodków.

---

## Cel

Linie z etapu 3 (`spoken` + `displayed`) → przetłumaczone na polski przez **rejestr silników** (pierwszy w projekcie). AniShift to lektor ORAZ tłumaczarka napisów → produkuje całościowy przetłumaczony ASS. Silniki: **Google + DeepL** (oficjalne API) + **LLM** (rejestr od projektu, realizacja/test w etapie 5).

---

## 0. Fakty z kodu (fundament wymagań)

- **Etap 3 daje `SpokenLine(start, end, text, style)` w PAMIĘCI** (spoken) — tekst już oczyszczony z tagów (`visible_text()`), już po collapse FBF. Tłumaczenie NIE czyści tekstu (zrobione wcześniej), NIE czyta pliku SRT. `displayed` etap 3 pisze jako `<stem>.displayed.<kind>` (oryginalny język) — etap 4 też go tłumaczy (patrz §1).
- **Ani `spoken`, ani przetłumaczony `displayed` nie wypływają dziś z runnera** — `_process_mkv` liczy statystyki i pisze oryginalny displayed. Etap 4 wpina krok `translate` w `_process_mkv`.
- **Klucze API i szkielet `/settings` istnieją** — `Settings.deepl_api_key` (user MA klucz Free `:fx`), `UserSettings.translation_engine`. Etap 4 konsumuje, nie tworzy.
- **Wzorzec: runner woła serwis, serwis nie zna runnera** (jak `extraction`).
- **`extraction` = zwykły moduł; `translation` = rejestr + fasada** (bo ma wybór silnika).
- **AniShift działa też jako tłumaczarka napisów** (opcja lektor/napisy w `/settings`) — produkuje przetłumaczone napisy. Format wyjścia (ASS/SRT) = sprawa eksportu (§10, granica z etapem 7): opcja formatu pojawia się TYLKO w trybie eksportu `player` (gołe pliki napisów na dysk); domyślnie jak wejście (ASS→ASS, SRT→SRT — źródło z Netflixa bywa SRT), można wybrać SRT (upraszcza, bez stylów ASS). Tłumaczenie dotyczy zarówno `spoken` (lektor), jak i `displayed` (napisy które widz ogląda). Układ wersów ma znaczenie dla czytelności napisów na ekranie — nie tylko dla lektora.
- **`text_chunker.py`** (z geminicli2api: `LatinPunctuator` + `CharBreaker`/`WordBreaker`) dzieli tekst na granicach zdań/fraz/słów — nadaje się i do txt (chunking), i do re-podziału przetłumaczonych linii. Do przepisania wg standardu `python instructions`.

---

## 1. Model danych i przepływ

- ✅ **Tłumaczymy `spoken` ORAZ `displayed`** — nie tylko lektora. AniShift to też tłumaczarka napisów → całościowy przetłumaczony ASS. `spoken` (do TTS) żyje w pamięci; `displayed` (napisy dla widza) → przetłumaczony plik.
- ✅ **Runner woła tłumaczenie w łańcuchu** — krok `translate` w `_process_mkv` (po `split`, przed TTS). `spoken` (do lektora) nie ląduje na dysk jako osobny artefakt.
- ✅ **Trzy możliwe warianty napisów** (co eksportować — zależy od trybu w `/settings`):
  - **całościowy** — cały przetłumaczony ASS (spoken + displayed po polsku),
  - **lektorski** — tylko `displayed` po polsku (dialogi czyta lektor głosem, na ekranie tylko szyldy/znaki),
  - **spoken** — tylko przetłumaczone dialogi (opcja).
- ✅ **Konflikt nazw = TYLKO w trybie player** (napisy na dysk obok wideo). W trybie MKV merge (etap 7) warianty = osobne ścieżki w kontenerze z tytułami ("Polski pełny"/"Polski lektor") — zero konfliktu. 🏗️ nazewnictwo dla trybu player — patrz §10 (sonda bada konwencję MPV).
- 🏗️ **Typ wyniku:** `SpokenLine` jest `frozen` — tłumaczenie tworzy nowy typ (np. `TranslatedLine`), źródło nietknięte (odwracalność N1). Fable rozstrzyga kształt pod potrzeby etapu 6 (TTS) i produkcji wariantów ASS.
- 🏗️ **Granica etap 4 / etap 7:** etap 4 PRODUKUJE przetłumaczone linie (spoken+displayed). Składanie wariantów w pliki/ścieżki + nazewnictwo/muxowanie = etap 7 (composition). Etap 4 zapewnia dane, etap 7 je układa. Fable: gdzie granica.

---

## 2. Wymagania funkcjonalne

- **R1 — Krok `translate` w pipeline.** Po `split`, przed TTS. Konsumuje `spoken` + `displayed`, produkuje przetłumaczone linie. Nowy `StepName = "translate"`.
- **R2 — Rejestr silników (PIERWSZY w projekcie).** `services/translation/engines/__init__.py` wg kanonicznego wzorca MangaShift: `_REGISTRY`, `available_engine_ids()`, `create_engine()`, guard (pusty engine_id → ConfigError; nieznany → ConfigError z posortowaną listą), lazy `importlib`. `TranslationEngineId = Literal["google", "deepl", "llm"]`.
- **R3 — Fasada sync.** `TranslationService` woła tylko `create_engine`, cache instancji per engine_id, **zero `if engine_id == ...`**.
- **R4 — Dedup unikalnych linii.** Linia powtórzona N razy tłumaczy się 1×, mapowanie z powrotem na wszystkie wystąpienia (`dict.fromkeys`). Wspólne dla wszystkich silników — silnik nigdy nie deduplikuje sam.
- **R5 — Batching napisów po LICZBIE LINII.** Batch per silnik (D3) wg jego optimum: GT ~50, DeepL większy, LLM wg modelu. Konfigurowalny w `/settings`.
  - **R5a — twardy limit znaków per request.** Batch nie przekracza limitu silnika (Google 15 000 znaków/request, DeepL 128 KiB payloadu). Za długie linie → podział. 🏗️ limit jako atrybut silnika.
- **R6 — Batching txt po ZNAKACH (chunker).** Mini-ficzer (§8): goły `.txt` → tłumaczenie → SRT. Tekst tnie się po znakach na granicach zdań/fraz/słów. Wzorzec: `text_chunker.py` (LatinPunctuator + CharBreaker), przepisany wg `python instructions`. Domyślne atrybuty trybu txt: `sentence_length = 750`, `chunk_limit = 250`.
- **R6a — Obsługa wieloliniowych napisów — RÓŻNA per silnik (zmierzone testem na żywo).**
  - **Google:** MUSI sklejać `\n` w spację przed tłumaczeniem. Test: rozbite wersy = złe tłumaczenie (`"I don't know\nif I can do it"` → „nie wiem, jeśli mogę to zrobić" ❌), sklejone → „Nie wiem, czy dam radę" ✅. Google gubi/psuje kontekst przy `\n`.
  - **DeepL: NIE musi sklejać — radzi sobie z raw `\n`.** Test (na żywo, klucz usera): to samo zdanie z `\n` → „Nie wiem,\nczy dam radę" ✅ (poprawnie!) + **zachowuje podział `\n`** (Google go psuł). DeepL rozumie kontekst całego napisu mimo podziału. Dodatkowo `<br>` + `tag_handling="html"` przetrwał (kolejny sposób ochrony podziału).
  - **Wniosek:** sklejanie to strategia **per silnik** (atrybut silnika, nie stała domeny). Google sklejaj+re-podziel (R6b); DeepL może dostać oryginalny podział. 🏗️ Fable: jak to wyrazić w Protocolu silnika.
  - **Markery (`\n`→znacznik `◍◍◍◍`) ODRZUCONE dla Google** — test: ~20% gubi/przesuwa; research: najbardziej zawodna droga.
- **R6b — Re-podział przetłumaczonego tekstu na wersy (algorytm hierarchiczny).** Dotyczy zwłaszcza **Google** (po sklejeniu wynik to jedna linia — trzeba re-podzielić). DeepL zachowuje podział sam (R6a), więc re-podział mniej potrzebny — ale przydatny gdy przetłumaczona linia przekracza limit znaków. **NIE odtwarzamy oryginalnego układu** (niemożliwe bez LLM — składnia się zmienia), tworzymy NOWY czytelny podział wg reguł napisowych (Netflix/BBC):
  - hierarchia cięcia: **po interpunkcji** (`. , — ? !`) → **przed spójnikiem/przyimkiem** (`i`, `że`, `bo`, `w`, `na`...) → **awaryjnie najbliżej środka, na granicy słowa**.
  - reguły ochronne: limit ~42 znaki/linia (konfigurowalny), max 2 linie, **bez sierot** (jedno słowo samo), **nie tnij zrostów** (przyimek+rzeczownik, przymiotnik+rzeczownik).
  - dotyczy `displayed` (widz czyta — układ ważny) i `spoken` (spójne linie dla lektora). 🏗️ Fable: czy `spoken` w ogóle potrzebuje podziału, skoro lektor czyta ciągiem.
  - **narzędzie: WŁASNY algorytm** (~30-50 linii, zero zależności) na bazie `text_chunker.py` (LatinPunctuator już tnie po zdaniach/frazach). Zbadane: żadna biblioteka nie robi tego lepiej dla polskiego — `srt_equalizer` tnie tylko na `.,!?` (brak `:;…—` — polska pauza dialogowa i wielokropek pominięte), brak hierarchii spójników, "przewaga nad własnym kodem praktycznie zerowa". ML (wtpsplit/nnsplit/spaCy/torch) ODRZUCONE — łamią lekki core. `srt_equalizer` (MIT) tylko jako **referencja do podejrzenia** — warto podkraść ideę `split_at_half` (rekurencyjne cięcie najbliżej środka + bonus za przecinek = równe linie bez sierot). NIE instalować jako zależność (mamy czysty tekst, nie pliki SRT).
  - hierarchia cięcia dla polskiego: **mocna interpunkcja (`. ! ? … :`) → przecinek/średnik/pauza dialogowa (`, ; —`) → spójnik (`i, oraz, ale, że, więc, bo, aby, lub`) → najbliżej środka** (idea `split_at_half`). Fallback: greedy na spacjach gdy fragment > limit.
- **R7 — Równoległość: pliki sekwencyjnie, batche w pliku równolegle.**
  - Pliki: po kolei (natsorted).
  - Batche w jednym pliku: równolegle (semaphore = limit współbieżności).
  - Współbieżność **konserwatywna i konfigurowalna** — API rate-limituje (Google 429/503 przy zalewaniu). Domyślne do zmierzenia skryptem.
- **R8 — Retry + backoff per silnik (DWA systemy).**
  - **System 1 — proste API (Google, DeepL):** retry z backoff wykładniczym na 429/503/5xx. Bez „dogadywania".
  - **System 2 — LLM/agentowy:** patrz §9 (pełne wymagania). Skrót: numeracja linii + walidacja liczby + retry z dogadywaniem. **Realizacja/test w etapie 5.**
  - **R8a — limit ponowień konfigurowalny** w `/settings` (rozsądny, nie 100). Po wyczerpaniu → fallback.
  - **R8b — priorytet ponowień:** najwcześniejsze batche w najwcześniejszym pliku pierwsze — żeby pliki od początku listy miały największą szansę być kompletne w kolejności.
- **R9 — Fallback = cały plik od nowa następnym silnikiem.** Silnik pada → cały plik od nowa następnym **dostępnym** silnikiem z łańcucha (bez sklejania połówek — uniknięcie zgrzytu jakości). Łańcuch pusty/wyczerpany → plik `failed`, reszta plików leci.
- **R10 — Pomijanie już-polskich.** Flaga `already_polish` (etap 3) → pomiń tłumaczenie pliku.
- **R11 — Silniki: google, deepl (+ llm zarezerwowany).**
  - `google` — googletrans 4.x (async→sync, JEDEN event loop na plik). Darmowy, bez klucza, `is_available` = zawsze.
  - `deepl` — oficjalne API (`deepl` 1.30.0), klucz z `Settings.deepl_api_key`. Batch listą. `is_available` = False bez klucza. `QuotaExceededException` → sygnał fallbacku.
  - `llm` — cienki adapter → fasada `services/llm` (etap 5). W rejestrze od projektu; `create_engine` dla llm wymaga wstrzykniętego completera (wzorzec MangaShift).
- **R12 — Błąd jednego pliku nie przerywa reszty.** Jasny komunikat domenowy, nie traceback.
- **R13 — Progress: pasek per plik (jak ekstrakcja).** Tłumaczenie używa istniejącego `MultiProgressManager` (utils, już działa w etapie 3): jeden pasek na plik, `%` = ukończone batche (10/20 batchy = 50%). Wiele plików = wiele pasków. Błędy/retry/fallback → w **raporcie końcowym** (wzorzec `_render_report` etapu 3), nie osobny live-widget. Spójne z etapem 3, bez nowego UI. **Refaktor UI terminala (logi/historia/podział ekranu) = osobny temat (§Tropy), dotyczy całej apki — nie etap 4.**

---

## 3. Wymagania niefunkcjonalne

- **N1 — Źródło nietknięte.** Tłumaczenie nie mutuje `SpokenLine` (frozen).
- **N2 — Determinizm dedup.** Ten sam wejściowy zestaw linii → ten sam dedup i mapowanie.
- **N3 — Zero `sys.exit()` / `input()` w serwisie.**
- **N4 — Domena z rejestrem.** `translation` MA `engines/`.
- **N5 — Klucze przez `Settings`** (już istnieje).
- **N6 — Lazy import silników.** googletrans/deepl nie importowane na starcie apki.
- **N7 — Testowalność bez sieci.** Dedup, batching, chunker, rejestr — testowalne z mockiem silnika. Realne API tylko w testach `network`.
- **N8 — Nie blind `except Exception`.** Łapać precyzyjnie: `QuotaExceededException`, `TooManyRequestsException`, błędy sieci osobno.

---

## 4. Ustawienia w `/settings`

Panel steruje wszystkim. Parametry, które etap 4 dodaje do `UserSettings`:

- **`translation_engine`** — wybrany silnik (domyślny `google`). Lista = `available_engine_ids()` filtrowana przez `is_available()`.
- **`translation_fallback_chain`** — łańcuch fallbacku (lista engine_id). Domyślnie `["google"]`. Pusty = brak fallbacku (failed przy błędzie).
- **`translation_batch_size` per silnik** — każdy swój default wg limitu.
- **`translation_max_retries`** — limit ponowień per batch (rozsądny, nie 100).
- **`translation_concurrency` per silnik** — limit równoległych batchy (semaphore), konserwatywny.
- **`target_lang`** — język docelowy (domyślnie `pl`).
- **Parametry LLM (etap 5, projektowane teraz):** `temperature`, `top_p`, `max_output_tokens`, wybór modelu (z `supported_models()`).

🏗️ Fable: kształt pól (płaskie vs zagnieżdżone per silnik), wzorzec walidacji jak `_clean_string`/`_clean_number` w `user_settings.py`.

---

## 5. Struktura domeny (🏗️ Fable dopracuje)

```
anishift/services/translation/
├── __init__.py           # re-export fasady, configu, typów, błędów
├── errors.py             # TranslationError, TranslationConfigError, TranslationAuthError
├── config.py             # TranslationConfig (engine_id wymagany, target_lang, batch...)
├── constants.py          # Final: domyślny język, limity znaków per silnik
├── protocols.py          # Protocol TranslationEngine (sync): engine_id, is_available, translate_batch, close
├── types.py              # TranslatedLine, raport wyniku
├── dedup.py              # dedup + mapowanie (wspólne dla wszystkich silników)
├── service.py            # fasada sync: spoken → translate → wynik
└── engines/
    ├── __init__.py       # rejestr: google, deepl, llm
    ├── google/           # async→sync, 1 event loop/plik
    ├── deepl/            # deepl SDK, is_available bez klucza
    └── llm/              # etap 5 — cienki adapter → services/llm
```

🏗️ **Chunker / podział linii (R6/R6a/R6b) — OTWARTE dla Fabla, gdzie umieścić `text_chunker`:**
- `text_chunker.py` (przepisany z geminicli2api wg `python instructions`) służy DWÓM celom: (1) chunking txt po znakach (R6), (2) re-podział przetłumaczonych linii na wersy (R6b). To narzędzie do zarządzania tekstem — pytanie architektoniczne: **utils/ (uniwersalne narzędzie, jak `rich_console`)? osobny serwis? podmoduł `translation`?** User wskazał niepewność wprost. Fable rozstrzyga. Kandydat: `utils/text_chunker.py` (uniwersalne, przenośne) albo `translation/linebreak.py` (blisko konsumenta).
- Domyślne atrybuty txt: `sentence_length = 750`, `chunk_limit = 250`.
- Batching napisów (R5) + dedup — Fable: osobny moduł czy razem.

---

## 6. Edge case'y

| # | Sytuacja | Zachowanie |
|---|----------|-----------|
| E1 | Plik już po polsku (`already_polish`) | Pomiń tłumaczenie (R10). |
| E2 | Zero linii `spoken` | Nic do tłumaczenia, przejdź dalej (nie błąd). |
| E3 | DeepL bez klucza | `is_available`=False, znika z panelu; wymuszenie = `TranslationAuthError`. |
| E4 | DeepL wyczerpał limit (`QuotaExceededException`) | Fallback na następny silnik (R9); brak → failed. |
| E5 | Google 429/503 (rate-limit) | Retry z backoff (R8); po wyczerpaniu → fallback. |
| E6 | Rozjazd liczby linii (API zwróciło inną liczbę) | Retry (R8); LLM: dogadanie do modelu (system 2). Po wyczerpaniu → fallback/failed. |
| E7 | Brak sieci | Błąd domenowy (nie crash), retry, potem fallback/failed. |
| E8 | Linia dłuższa niż limit znaków silnika | Batch respektuje limit (R5a); pojedyncza linia > limit — 🏗️ rzadkie dla napisów. |
| E9 | Ctrl+C w trakcie tłumaczenia | Przerywa czysto, wraca do promptu (wzorzec etapu 3). |
| E10 | 2+ pliki, jeden pada | Reszta leci (R12), padły = failed z komunikatem. |
| E11 | Wszystkie silniki z łańcucha niedostępne | Plik failed, komunikat „brak dostępnego silnika tłumaczenia". |

---

## 7. Definition of Done

- [ ] Krok `translate` wpięty w `_process_mkv`, `spoken` płynie do tłumaczenia (nie na dysk)
- [ ] Wieloliniowe napisy per silnik (R6a): Google sklejane, DeepL raw `\n`; markery NIE użyte
- [ ] Re-podział na wersy wg hierarchii interpunkcja→spójnik→środek, limit znaków, bez sierot (R6b)
- [ ] Tłumaczymy spoken ORAZ displayed; warianty eksportu wg trybu (całościowy/lektorski)
- [ ] `text_chunker` przepisany wg `python instructions`; txt domyślnie sentence_length=750, chunk_limit=250
- [ ] Rejestr smoke: nieznany engine_id = `TranslationConfigError` z posortowaną listą
- [ ] Import rejestru NIE importuje googletrans/deepl (test lazy-importu)
- [ ] Dedup: 1000 identycznych linii = 1 wywołanie API, mapowanie poprawne
- [ ] Batch respektuje limit znaków silnika (Google 15k, DeepL 128 KiB)
- [ ] Google: async→sync z jednym event loopem na plik
- [ ] DeepL: bez klucza `is_available`=False; z kluczem tłumaczy; `QuotaExceededException` → fallback
- [ ] Fallback: silnik pada → cały plik od nowa następnym; łańcuch pusty → failed, reszta leci
- [ ] Retry z backoff na 429/503; limit ponowień konfigurowalny
- [ ] Współbieżność konserwatywna i konfigurowalna
- [ ] `already_polish` → pomija tłumaczenie
- [ ] Ctrl+C przerywa czysto (wzorzec etapu 3)
- [ ] Błąd jednego pliku nie ubija reszty; jasny komunikat co i gdzie
- [ ] Zero `input()`/`sys.exit()` w serwisie; nie blind `except Exception`
- [ ] Parametry w `/settings` przeżywają restart
- [ ] Mini-ficzer txt→SRT działa (chunker po znakach)
- [ ] Re-podział linii przetestowany na realnych polskich zdaniach (sensowne cięcia, nie w środku frazy)
- [ ] Smoke na realnym pliku: MKV/ASS z datasetu (`../mm_avh_working_space/temp/dataset_ass/`) → przetłumaczone spoken+displayed, ta sama liczba linii, timingi nietknięte
- [ ] Bramki: ruff + format + mypy + pytest zielone
- [ ] LLM: wymagania + spójny plan opisane (realizacja/test etap 5)

---

## 8. Mini-ficzer: txt → tłumaczenie → SRT

Program bierze goły `.txt`, tłumaczy i rozbija na SRT. Łączy się z `txt.py` / `txt_to_spoken` z etapu 3 (discovery `.txt` już w runnerze). Chunker po znakach (R6). 🏗️ Fable: jak spiąć z istniejącą ścieżką txt.

---

## 9. System agentowy LLM (wymagania pełne — realizacja/test w etapie 5)

> LLM to silnik `llm` w rejestrze translation (adapter → fasada `services/llm`, etap 5). Wymagania spisane teraz dla spójności (rejestr od projektu obsługuje llm). Punkt wyjścia: geminicli2api (`gemini_translator`) — „coś w tym jest, ale nie optymalne", rozwijamy w niezawodny system.

- **A1 — Numeracja linii ZOSTAJE.** Każda linia w requeście numerowana (`[1]`, `[2]`...). Powód (decyzja usera): (a) pomaga LLM trzymać kontekst i kolejność, (b) **natychmiastowa walidacja** — brak `[5]` w odpowiedzi = LLM zgubił linię, wiadomo od razu. To fundament niezawodności, niezależny od formatu opakowania.
- **A2 — Walidacja liczby linii + odporne parsowanie.** Numeracja WYKRYWA błędy, nie zapobiega im — LLM MOŻE scalić/pominąć linię (to nie eliminowalne). Dlatego:
  - **Walidacja:** odpowiedź MUSI mieć indeksy 1..N, każdy dokładnie raz. Brak `[6]` = wiadomo dokładnie że linia 6 zgubiona (bez numeracji: ciche przesunięcie całej reszty — katastrofa). Rozjazd → retry z komunikatem („zwróciłeś X zamiast Y, zwróć DOKŁADNIE Y, nie pomijaj").
  - **Odporne parsowanie (LLM dodaje śmieci na początku/końcu — realny problem z geminicli2api):** bierz TYLKO linie pasujące do wzorca `[N] tekst`; wszystko inne („Oto tłumaczenie:", markdown ```` ``` ````, „Mam nadzieję że pomogłem") — ignoruj automatycznie (nie ma `[N]` → wypada). To przewaga nad JSON, gdzie tekst przed `{` psuje cały parse.
  - **System prompt anty-gadanie:** „Zwróć TYLKO ponumerowane linie. Bez wstępu, bez podsumowania, bez markdown. Jedna linia wejścia = jedna linia wyjścia, NIE scalaj."
- **A2a — Shrink-do-1 (kaskada fallback).** Gdy retry nie pomaga: podziel batch na mniejszy → aż do 1 linii (jedna linia = LLM nie ma czego scalić). Wzorzec geminicli2api + gemini-srt-translator. Ten sam mechanizm co kaskada google/deepl w dedup.
- **A3 — Format komunikacji: NUMERACJA `[N] tekst`** (zbadane, ROZSTRZYGNIĘTE). NIE JSON/TOON/XML. Uzasadnienie (5 kierunków sondy zbieżnie):
  - **Numeracja najtańsza tokenowo** (bez cudzysłowów/nawiasów/tagów) i najłatwiejsza w walidacji (O(N): sprawdź że indeksy 1..N wystąpiły raz — bez parsera JSON, bez pułapek escapowania; napisy pełne cudzysłowów/apostrofów).
  - **Błąd lokalny** — zgubiona linia = jedna luka; ucięty JSON = cały batch nieważny (failuje cicho).
  - **JSON NIE gwarantuje liczby elementów** (`minItems` w nieobsługiwanym podzbiorze schematu) + wymuszony JSON degraduje jakość generacji ~10-15% (EMNLP 2024) — a tłumaczenie to generacja.
  - **TOON** — token-efficient TYLKO na jednorodnych tabelach; lista stringów = płaska = ~6% GORSZY niż CSV. Marker długości wykrył ucięcie 0/4. Przereklamowany dla tego zadania. Obawa usera trafna.
  - **XML** najdroższy tokenowo (+12-19%).
  - Praktyka (llm-subtrans, gemini-srt-translator): numeracja/tagi + „NIE scalaj linii" + walidacja liczby + shrink-do-1. **Kluczowe: żaden format nie zwalnia z walidacji liczby + retry — to właściwa dźwignia, nie format.**
  - **Zasada: niezawodność (N linii) > oszczędność tokenów.**
- **A4 — Kontekst sąsiednich linii.** LLM tłumaczy lepiej z kontekstem — podawać sąsiednie linie (przewaga LLM nad google/deepl per-batch). 🏗️ jak dużo kontekstu vs koszt tokenów.
- **A5 — Retry z dogadywaniem (system agentowy).** Przy błędzie (zła liczba, zły format, brak JSON) → dopisz do promptu konkretny komunikat błędu i ponów. Backoff wykładniczy na błąd API (429/5xx). Limit ponowień konfigurowalny (R8a).
- **A6 — Podział linii dla LLM.** LLM może re-dzielić na wersy inteligentnie (rozumie sens) — lepiej niż algorytm R6b. 🏗️ czy LLM robi podział sam (w promcie), czy używa wspólnego R6b. UWAGA (research): LLM też bywa niedeterministyczny w liczbie linii — walidacja A2 obowiązkowa.
- **A7 — Parametry LLM w `/settings`:** dostawca + model (z `supported_models()` rejestru), `temperature` (niska dla tłumaczenia, np. 0.3), `top_p`, `max_output_tokens`. Wybór dostawcy z etapu 5 (anthropic/gemini/openai/deepseek/openrouter/openai_compatible).
- **A8 — Priorytet ponowień** (R8b) dotyczy też LLM: najwcześniejsze batche/pliki pierwsze.

---

## 10. Eksport wariantów napisów (granica z etapem 7 — zbadane)

> Etap 4 PRODUKUJE przetłumaczone linie (spoken+displayed). Składanie w pliki/ścieżki = etap 7 (composition). Sekcja zapisuje USTALENIA, żeby nie przepadły — implementacja w etapie 7.

- **Tryb MKV merge (rekomendowany) — muxuj warianty jako ścieżki w jednym MKV.** Rozwiązuje wszystko: brak konfliktu nazw, auto-wczytanie w każdym odtwarzaczu, przełączanie w menu, czytelne tytuły. Komenda: `--track-name "0:Polski (pełny)"` / `"0:Polski (lektor)"`, `--language 0:pol`, `--default-track-flag` na starcie. To standard fansubów (ścieżka „Full" + „Signs/Forced"). Dokłada tylko drugą ścieżkę do planowanej komendy mkvmerge etapu 7.
- **Tryb player (pliki na dysk) — sufiksy wariantu + języka.** `{stem}.pelny.pl.ass`, `{stem}.lektor.pl.ass` — człon wariantu PRZED kodem języka (żeby nie psuć detekcji języka MPV). **Zastrzeżenie (nieobejściowalne po stronie AniShift):** MPV domyślnie `sub-auto=exact` NIE wczyta plików z sufiksami — user musi mieć `sub-auto=fuzzy` w `mpv.conf`. Zewnętrzne ASS NIE niosą czytelnego tytułu ścieżki (tylko język + nazwa pliku). Do debugowania OK; do wygodnego wydania → MKV merge.
- **Warianty (co produkować, zależnie od trybu w `/settings`):** całościowy (`{stem}.pelny`), lektorski (`{stem}.lektor` — tylko displayed), opcjonalnie sam spoken. 🏗️ Fable/etap 7: dokładna schema nazw + który default-track.
- **Format pliku wyjściowego (TYLKO tryb player):** wybór ASS/SRT pojawia się tylko dla trybu eksportu `player` (gołe pliki na dysk). Dla merge/burn nieistotny (napisy → kontener/wypalane). Domyślnie jak wejście (ASS→ASS, SRT→SRT); wybór SRT upraszcza (ASS→SRT gubi style — etap 3 zmierzył 8 stylów→1; SRT→ASS nie ma sensu). To decyzja eksportu (etap 7), nie tłumaczenia.
- ⚠️ **Konflikt nadpisywania = tylko tryb player** — MKV merge go nie ma (ścieżki w kontenerze).

---

## USTALONE (decyzje usera)

- ✅ Tłumaczymy linie w pamięci (spoken + displayed), nie przez plik SRT pośredni.
- ✅ Runner woła tłumaczenie w łańcuchu — krok `translate`, `spoken` nigdy na dysk.
- ✅ Fallback = cały plik od nowa następnym silnikiem (bez sklejania połówek).
- ✅ Fallback konfigurowalny; pusty → failed, reszta leci.
- ✅ Pliki sekwencyjnie (natsorted), batche w pliku równolegle (semaphore).
- ✅ Retry z priorytetem najwcześniejszych batchy/plików.
- ✅ Batch per silnik (napisy po liniach, txt po znakach). Domyślne do zmierzenia.
- ✅ Limit ponowień konfigurowalny (nie 100).
- ✅ Dwa systemy retry: proste API (backoff) + LLM/agentowy (numeracja + walidacja liczby + dogadywanie).
- ✅ **Numeracja linii LLM `[N] tekst` ZOSTAJE** (nie JSON/TOON/XML — zbadane 5 kierunkami). Najtańsza tokenowo, walidacja O(N) bez parsera, błąd lokalny. JSON degraduje jakość ~10-15% + nie gwarantuje liczby; TOON przereklamowany (płaska lista = gorszy niż CSV); XML najdroższy. Niezawodność > tokeny. Walidacja liczby + shrink-do-1 obowiązkowa niezależnie od formatu.
- ✅ LLM: pełne wymagania + spójny plan teraz, realizacja/test w etapie 5.
- ✅ D2 — Google domyślny (bez klucza), DeepL gdy user ma klucz. Fallback domyślnie `["google"]`.
- ✅ D3 — Batch per silnik.
- ✅ D4 — Manual nie dotyczy tłumaczenia (zawsze z ustawień).
- ✅ **AniShift to też tłumaczarka napisów** (opcja w `/settings`) — produkuje całościowy przetłumaczony ASS (displayed + spoken). Układ wersów ma znaczenie.
- ✅ **Tłumaczymy oba: spoken + displayed.** Trzy warianty eksportu (zależnie od trybu): całościowy (wszystko PL), lektorski (tylko displayed PL — lektor czyta dialogi), spoken (same dialogi).
- ✅ **Konflikt 2 plików napisów = tylko tryb player** (na dysk). MKV merge (etap 7) → osobne ścieżki z tytułami (`--track-name`), bez konfliktu (§10). Player: sufiksy `{stem}.pelny.pl.ass`/`{stem}.lektor.pl.ass`, ale MPV wymaga `sub-auto=fuzzy` u usera.
- ✅ **Format wyniku i nazewnictwo — granica z etapem 7** (composition układa, etap 4 produkuje dane). Rekomendacja: MKV merge = główny (wygodny), player = debug (§10).
- ✅ **Format pliku (ASS/SRT) = opcja TYLKO w trybie player** (gołe pliki na dysk); merge/burn go nie dotyczy. Domyślnie jak wejście; wybór SRT upraszcza (bez stylów). Sprawa eksportu (etap 7).
- ✅ **Progress: pasek per plik jak ekstrakcja** (R13, MultiProgressManager już działa), błędy w raporcie końcowym. Refaktor UI (logi/historia/podział terminala) = osobny temat całej apki, NIE etap 4.
- ✅ **Obsługa wieloliniowych napisów RÓŻNA per silnik** (zmierzone na żywo, R6a): **Google MUSI sklejać** (rozbite = złe tłumaczenie), **DeepL radzi sobie z raw `\n`** (tłumaczy dobrze + zachowuje podział — dużo lepszy niż Google). Sklejanie = atrybut silnika, nie stała. Markery ODRZUCONE dla Google.
- ✅ **Re-podział wg reguł napisowych** (R6b) — głównie dla Google (po sklejeniu); DeepL zachowuje podział sam. NIE odtwarzanie oryginału — interpunkcja→spójnik→środek, limit znaków, bez sierot.
- ✅ **DeepL > Google jakościowo** (test na żywo): DeepL tłumaczy poprawnie nawet rozbite wersy i zachowuje `\n`; Google gubi kontekst i psuje podział. Argument by DeepL był preferowany gdy user ma klucz.
- ✅ **`text_chunker.py`** — narzędzie do chunkingu txt i re-podziału linii; przepisać wg `python instructions`; txt: sentence_length=750, chunk_limit=250. Gdzie umieścić — otwarte dla Fabla.
- ✅ **Podział linii = WŁASNY algorytm, nie biblioteka.** Zbadane: srt_equalizer (MIT, ~90 linii) tnie tylko na `.,!?` — gorszy dla polskiego niż własna hierarchia z pauzą `—` i spójnikami. Inne biblioteki: ML (ciężkie, łamią lekki core) albo robią co innego (sentence splitting). Własny ~30-50 linii, srt_equalizer tylko jako referencja (podkraść ideę `split_at_half`).
- ✅ User MA klucz DeepL Free (`:fx`, 500k/mies).

## Fakty z researchu (dla wartości domyślnych)

- **Google (googletrans 4.x):** 15 000 znaków/request; async; rate-limit 429/503 przy nadużyciu, próg = brak danych (zmierzyć).
- **DeepL API:** request ≤128 KiB; batch listą; `QuotaExceededException` przy wyczerpaniu; `deepl` 1.30.0.
- Współbieżność musi być konserwatywna — API rate-limitują przy zalewaniu.

---

## Tropy / odłożone (NIE etap 4)

- **Refaktor UI terminala** — logi/historia przebiegu na górze, paski na dole, live raport błędów, podział ekranu przy odświeżającym się progressie. Dotyczy CAŁEJ apki (ekstrakcja/tłumaczenie/TTS), nie tylko tłumaczenia. User już to planuje (session-log). Wzorzec rich: `Live` + `Group` (statyczna historia + żywe paski). Świadomy temat, nie w pośpiechu w etapie 4.
- **Skrypty obciążeniowe** — zmierzyć optymalne domyślne: batch size, concurrency, retry per silnik (nie zgadywać, wzorzec pomiaru z etapu 3).
- **Równoległość plików** — potencjał, tylko gdy jeden plik nie wysyca API. Ryzyko rate-limitu × liczba plików.
- **DeepLX (darmowy nielimitowany DeepL)** — ODRZUCONY (test na żywo: 429 z IP usera od pierwszego requestu). Metoda zachowana: `OwO-Network/DLX`, oneshot REST, curl_cffi chrome120, limit 1500 znaków. Nie wracać bez rozwiązania rate-limitu IP (rotacja nieopłacalna wobec darmowego DeepL API). Test: `scratchpad/deeplx_test.py`.

---

## Zasady usera (na cały projekt)

- **100% albo wcale** — zero półśrodków. Agent ocenia sensowność wymagań, user reaguje.
- Kod i komentarze po angielsku, rozmowa po polsku.
- Zależności tylko przez `uv add`.
