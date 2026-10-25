---
kind: plan
status: draft, wykonanie po decyzjach D1–D8
baseline: main @ 4365a51
created: 2026-10-25
---

# Plan: glosariusz serii i reguły nazw własnych

## Cel

Wdrożyć [specification.md](specification.md): glosariusz serii z AniList, wstrzyknięcie go do promptu LLM, reguły nazw własnych w `translation.md` i pomiar przed i po na tych samych odcinkach.

## Rezultat użytkownika

Kolejne odcinki tej samej serii mają te same imiona, tę samą regułę sufiksów i wołacza oraz poprawną płeć w odmianie. Właściciel poprawia błędną formę raz, w `config/glossaries/<id>.json`, i poprawka obowiązuje w każdym następnym odcinku.

## Warunki końcowe

- [ ] S1–S6 ze specyfikacji spełnione i zapisane w `outcomes/01-glossary-bench.md`.
- [ ] Właściciel ocenił listę M5.
- [ ] Bramki repo zielone na gałęzi.

## Nie-cel

Pamięć terminów spoza AniList z poprzednich odcinków (specyfikacja, „Odłożone”).

## Authority i baseline

| Źródło | Rola |
|---|---|
| [specification.md](specification.md) z decyzjami D1–D8 | wymaganie |
| [evidence.md](evidence.md) | stan aktualny i przypadki kontrolne |
| `AGENTS.md` (root), `anishift/AGENTS.md`, `services/translation/AGENTS.md`, `engines/llm/AGENTS.md`, `services/catalog/AGENTS.md`, `application/AGENTS.md`, `tests/AGENTS.md` | reguły repo |
| `.agents/skills/simple`, `coding` (z `references/python.md`, `comments-docstrings.md`, `testing.md`) | standard wykonania |

**Baseline:** `main` @ `4365a51`, drzewo czyste 2026-10-25. **Znane wcześniejsze failures:** nieznane; faza 0 je zapisuje.

## Stan aktualny

### Obecne zachowanie i gap

Skrót z [evidence.md](evidence.md) §1:

- `LlmTranslateService._complete` składa trzy części użytkownika bez glosariusza (`engines/llm/service.py:247-258`).
- `TranslationService.translate_file` woła `engine_factory(engine_id, config)`; fabryka nie dostaje nic per plik (`services/translation/service.py:110`).
- `TranslationTaskHandler._translate_subtitles` nie zna serii (`application/translation_handler.py:282-315`).
- `AniListCatalog` nie ma zapytania o postacie (`services/catalog/anilist.py`).

### Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
|---|---|---|---|
| Transport GraphQL | `AniListCatalog._post` | wysyłka zapytania, mapowanie błędów na `TitleCatalogError` | 429 jest błędem bez retry; tak zostaje |
| Graf franczyzy | `AniListCatalog.franchise`, `graph_prequels` | korzeń serii dla D6 (b) | do 4 zapytań; wołać raz na serię |
| Wyszukiwanie tytułu | `AniListCatalog.search` | D5 (b) | zwraca kandydatów; trzeba wybrać pierwszego z dopasowaniem sezonu |
| Tytuł z nazwy pliku | `application/library.py:library_label` | D5 (b) | dla nierozpoznanej nazwy zwraca cały stem |
| Seria pobranego zestawu | `application/library.py:downloaded_episodes` | D5 (a) | klucz to `set_id`; powiązanie z `PlanTask.group_id` sprawdza faza 0 |
| Katalog konfiguracji | `anishift/paths.py:config_dir` | `config_dir() / "glossaries"` | `ANISHIFT_CONFIG_DIR` przestawia go w benchu |
| Parowanie zdarzeń | `scripts/subtitle_quality/metrics.py:pair_events`, `dialogue` | M1–M5 | paruje po czasie i stylu |
| Ładowanie promptów | `engines/llm/prompts/loader.py:PromptLoader` | nowy zasób `glossary.md` | walidacja tokenu jak `retry.md` |
| Granice słów | `anishift/text/` | dopasowanie aliasów w P1, jeśli istnieje pasujący prymityw | nie dublować skanu Unicode |

## Zakres

### In scope

Wymagania G1–G12, P1–P6, R1–R3, M1–M6, Q1–Q4 i inwarianty I1–I4 ze specyfikacji.

### Out of scope

Grok, kontekst z innych języków, panel edycji glosariusza, tabela formalności.

### Forbidden

- Zmiany w `prompts/styles/`, `line_contract.py`, silnikach Google i DeepL (poza zignorowaniem nowego argumentu, jeśli protokół tego wymaga).
- Import `services.catalog` lub `services.llm` w `services/translation/`.
- Nowe zależności.
- Czytanie `.env` i kluczy przez wykonawcę; płatne przebiegi uruchamia właściciel (D7).
- Zmiana plików w `workspace/ready/` i w `config/` właściciela. Bench pracuje na własnych katalogach (faza 1).
- Commit na `main`; worktree (pamięć właściciela: praca w głównym checkoucie).

### Dozwolone decyzje lokalne

- Nazwy prywatnych funkcji, podział na moduły wewnątrz wskazanych plików, limit stron AniList (stała w zakresie 2–4).
- Dokładne brzmienie `glossary.md` i sekcji R1, jeśli realizuje treść R1 i decyzje D1–D4.

### Zatrzymaj się i wróć po decyzję, gdy

- `group_id` zadania nie wiąże się jednoznacznie ze stanem ownera (wpływa na D5).
- Przekazanie glosariusza wymaga zmiany protokołu `TranslationEngine.translate_batch` zamiast fabryki silnika.
- Bench z `ANISHIFT_CONFIG_DIR` dotyka stanu rezydenta właściciela.
- Przebieg bazowy pokazuje, że dzisiejszy model nie popełnia większości błędów z [evidence.md](evidence.md): wtedy zakres reguł R1 trzeba zawęzić do tego, co pomiar potwierdził.

## Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres |
|---|---|---|---|
| 1 | `specification.md`, `evidence.md` | kontrakt i przypadki | całość |
| 2 | `services/translation/AGENTS.md`, `engines/llm/AGENTS.md`, `services/catalog/AGENTS.md`, `application/AGENTS.md` | pułapki | całość |
| 3 | `engines/llm/service.py`, `engines/llm/config.py`, `prompts/loader.py` | wstrzyknięcie | całość |
| 4 | `services/translation/service.py`, `protocols.py`, `types.py` | ścieżka glosariusza | całość |
| 5 | `application/translation_handler.py`, `application/runtime.py:364-506` | wiring | wskazane |
| 6 | `services/catalog/anilist.py`, `types.py` | AniList | całość |
| 7 | `scripts/subtitle_quality/metrics.py`, `__main__.py` | pomiar | `pair_events`, `dialogue`, CLI |

## Impact scan

| Kontrakt / subsystem | Ryzyko | Obowiązek regresyjny |
|---|---|---|
| `TranslationEngineFactory` i jego trzy użycia (runtime, domyślna fabryka, testy) | zmiana sygnatury | `test_translation_service.py`, `test_auto_preset_smoke.py` zielone |
| Części użytkownika w żądaniu LLM | testy indeksują `user_parts[2]` | P3: bez trafień nadal trzy części; testy istniejące bez zmian |
| Cache prefiksu u providera | glosariusz przed stałym tekstem psuje cache | P2: kolejność system → translation → styl → glosariusz → linie |
| AniList (limit 30/min) | nowe zapytania w czasie przetwarzania wielu odcinków | Q3: tylko przy nowym wpisie; test, że znany wpis nie wysyła zapytania |
| Rezydent i równoległe zadania tłumaczenia | dwa odcinki tej samej serii jednocześnie zapisują plik | zapis atomowy (G10); dopisywanie bez nadpisywania istniejących pozycji, więc wygrana któregokolwiek zapisu zostawia poprawny plik |
| Prywatność logów | nazwy postaci w logach | Q4; test logów nie jest wymagany, wystarczy review |

## Target design

### Odpowiedzialności i ownership

| Element | Odpowiada za | Owner danych | Nie odpowiada za |
|---|---|---|---|
| `services/catalog/anilist.py: AniListCatalog.characters` | pobranie postaci jednego wpisu (strony, płeć, rola, bez spoilerów) | — | glosariusz, pliki |
| `services/translation/types.py: GlossaryEntry`, `SeriesGlossary` | wartość domenowa, filtr wpisów po tekstach partii | — | AniList, pliki |
| `engines/llm/service.py` + `prompts/glossary.md` | render przefiltrowanej listy i wstawienie części | — | skąd glosariusz pochodzi |
| `application/glossary.py` (nowy) | rozpoznanie serii, odczyt i zapis `config/glossaries/<id>.json`, dopisywanie z AniList | plik glosariusza | prompt |
| `application/translation_handler.py` | pobranie glosariusza dla zadania i przekazanie do `translate_file` | — | format pliku |
| `scripts/subtitle_quality/names.py` (nowy) | M1–M6 | raport benchu | tłumaczenie |

### Source of truth

- Autorytatywny stan: plik `config/glossaries/<id>.json`.
- Mutacje: tylko `application/glossary.py` (dopisywanie) i ręcznie właściciel.
- Odczyt: raz na zadanie tłumaczenia.

### Przepływ

```text
zadanie TRANSLATE_SUBTITLES
-> application/glossary: seria (stan ownera albo tytuł pliku + AniList search) -> klucz (korzeń franczyzy)
-> plik glosariusza; brak bieżącego wpisu na liście źródeł -> AniListCatalog.characters -> dopisanie -> zapis atomowy
-> SeriesGlossary
-> TranslationService.translate_file(..., glossary=...)
-> engine_factory(engine_id, config, glossary)
-> LlmTranslateService: dla każdej partii filtr wpisów po tekstach -> część użytkownika z glossary.md
-> odpowiedź jak dziś
```

### Model danych

```text
plik: config/glossaries/<anilist_id>.json
{
  "anilist_id": int,            klucz serii (D6)
  "titles": {"romaji": str, "english": str | null},
  "sources": [int, ...],        wpisy AniList, z których pobrano postacie
  "entries": [
    {"source": str, "aliases": [str], "pl": str, "gender": "m" | "f" | "",
     "inflect": bool | null, "note": str, "origin": "anilist" | "owner", "skip": bool}
  ]
}
inwarianty: source unikalne w pliku; wpis istniejący nie jest zmieniany przez automat
serializacja: UTF-8, ensure_ascii=False, wcięcia 2, zapis przez plik tymczasowy i replace
migracja: brak (nowy plik); nieznane klucze ignorowane przy odczycie
```

### Algorytm filtra (P1)

1. Dla wpisu bez `skip` zbierz `source` i `aliases`.
2. Wpis trafia do partii, gdy któraś z tych form występuje w którymś tekście partii jako całe słowo albo fraza, z wielkością liter.
3. W linii wpisu podaj tylko formy, które wystąpiły, oraz `pl`, płeć, regułę odmiany i notę.

### Edge cases i failures

| Przypadek | Oczekiwane zachowanie | Dowód |
|---|---|---|
| Brak sieci, 429, 403 AniList | tłumaczenie bez nowych wpisów, istniejący plik użyty | unit |
| Uszkodzony JSON | tłumaczenie bez glosariusza, plik nietknięty, ostrzeżenie | integration |
| Seria nierozpoznana | tłumaczenie bez glosariusza, same reguły R1 | unit |
| Jedno nazwisko, dwie płcie (`Azumi`) | dwa wpisy-postacie; model rozstrzyga z kontekstu (R1) | ocena M5 |
| Wpis opisowy (`Suzuki no Haha`) | dopasowanie całą frazą, więc nie trafia przez słowo „no” | unit |
| Pisownia AniList inna niż w napisach (`Mizal`/`Mizar`) | wpis nie pasuje i nie trafia do promptu; pisownię daje źródło (R1) | unit |
| Właściciel ustawił `skip` | wpis nie wraca przy odświeżeniu | unit |
| Dwa zadania tej samej serii naraz | oba dopisują brakujące wpisy do świeżo wczytanej treści; plik zawsze poprawny | unit (G10) + zapis atomowy |
| Właściciel edytuje plik w trakcie pobierania z AniList | edycja zostaje, bo zapis dopisuje do treści wczytanej tuż przed zapisem | unit |
| Szyld wielkimi literami (`MIZAR`) | wpis trafia (P1) | unit |
| Imię będące zwykłym słowem małymi literami (`white`, `hel`) | wpis nie trafia | unit |

## Plan wykonania

### Faza 0: preflight

**Działania:**

1. Gałąź `work/translation/01-series-glossary` z `main` (sprawdź `git branch -a`, czy `work/translation/01-…` nie jest zajęte; jeśli jest, weź kolejny numer).
2. Bramki repo na czystym `main`; zapisz failures jako baseline.
3. Sprawdź powiązanie `PlanTask.group_id` → `acquisition.assignments[].group_id` → `anilist_id` w kodzie planera i `library.py`.
4. Sprawdź, czy `ANISHIFT_CONFIG_DIR` przenosi cały stan rezydenta i presety (`cli/watch.py:watch_state_dir`, `anishift/paths.py`), żeby bench nie dotykał rezydenta właściciela. Bench nie ma stanu ownera, więc rozpoznaje serie tylko przez D5 (b). Jeśli właściciel wybierze D5 (a), przygotuj w benchu minimalny stan z identyfikatorami AniList 6 serii; inaczej przebieg „po” zmierzy same reguły R1 ([reviews/round-2.md](reviews/round-2.md), H8).
5. Sprawdź, czy workspace przyjmuje samodzielny angielski `.ass` do tłumaczenia (`tests/application/test_translate_only.py`). Jeśli nie, bench użyje twardych linków do MKV (ten sam wolumin, bez kopiowania).
6. Zapisz decyzje D1–D8 w `specification.md` (sekcja „Ustalenia”).

**Gate:** decyzje zapisane; każde „nie” z punktów 3–5 to eskalacja.

### Faza 1: narzędzie pomiaru i przebieg bazowy

**Cel:** zmierzyć dzisiejszy model przed jakąkolwiek zmianą kodu tłumaczenia.

**Pliki:**

- `scripts/subtitle_quality/names.py`: NEW, M1–M6; wejście: katalog z parami (źródło EN, wynik PL) pogrupowanymi w serie, katalog glosariuszy referencyjnych, reguła D1; wyjście: JSON i Markdown.
- `scripts/subtitle_quality/__main__.py`: MODIFY, tylko jeśli podkomenda jest prostsza niż `python -m scripts.subtitle_quality.names`.
- `tests/scripts/subtitle_quality/test_quality_names.py`: NEW.

**Zestaw pomiarowy (15 odcinków):** Iceblade Sorcerer S02E01–E03; Apothecary Diaries S03E01 oraz Kusuriya 3rd Season 02–04; Detective Is Already Dead S02E01 oraz Tantei S2 02–03; Sasaki to Pii-chan S2 02 oraz Sasaki and Peeps S02E03; Seihantai 2nd Season 07–08; Koori no Jouheki 2nd Season 03.

**Glosariusze referencyjne:** dla 6 serii z zestawu plik w formacie G1–G3, zbudowany jednorazowym skryptem w `scripts/tmp/` (gitignored, najwyżej 6 zapytań AniList) według G4–G5 i uzupełniony ręcznie, jako `origin: owner`, o:

- imiona z przykładów 1–4 ([evidence.md](evidence.md)), których AniList nie ma (`Gyokuyou`, `Gyokuen`, `Onsou`);
- formy tytułów z przykładu 6 według D1 (`Master Jinshi` → `pan Jinshi`);
- tytuł Iceblade według D4.

Pliki zamrożone w katalogu benchu, nie w repo. Ten sam glosariusz referencyjny służy do pomiaru wszystkich wariantów.

**Bench:** `workspace/.quality/names/` (katalog z kropką, pomijany przez skan workspace; ta sama konwencja co `scripts/subtitle_quality`). Każdy przebieg to osobny katalog `ANISHIFT_WORKSPACE_ROOT` i `ANISHIFT_CONFIG_DIR` z ustawieniami: `llm_model_id: google/gemini-3.8-flash`, styl `funny`, preset tylko z tłumaczeniem.

**Human checkpoint (płatny, D7):**

```text
Uruchom: dwa przebiegi bazowe na gałęzi po commicie 1 (zmienia tylko scripts/, kod tłumaczenia = main); komendy przygotowuje wykonawca w README benchu
Zrób: nic poza uruchomieniem; nie otwieraj plików w trakcie
Oczekiwany rezultat: 15 plików .pl.ass na przebieg, raport names.py dla obu
Zwróć uwagę na: błędy kontraktu, brak plików
Przekaż wynik jako: ścieżka do raportu
```

**Automatyczna kontrola:** testy `test_quality_names.py`; ruff i mypy.

**Gate:** raport bazowy istnieje. Jeśli przypadki 1–17 nie występują w żadnym przebiegu bazowym, eskalacja (zakres R1).

### Faza 2: postacie z AniList

**Pliki:**

- `services/catalog/anilist.py`: MODIFY, zapytanie o postacie, `characters(anilist_id) -> tuple[CatalogCharacter, ...]`, strony do limitu, bez `alternativeSpoiler`.
- `services/catalog/types.py`: MODIFY, `CatalogCharacter` (imiona, płeć, rola).
- `services/catalog/AGENTS.md`: MODIFY, fakt o limicie stron i braku spoilerów.
- `tests/services/catalog/test_anilist.py`: MODIFY.

**Inwarianty:** `httpx.Client` wstrzykiwany; błędy przez `_post`; logi tylko liczby.

**Gate:** testy fazy zielone.

### Faza 3: glosariusz w silniku LLM i reguły promptu

**Pliki:**

- `services/translation/types.py`: MODIFY, `GlossaryEntry`, `SeriesGlossary` z filtrem P1.
- `services/translation/protocols.py`: MODIFY, `TranslationEngineFactory` z trzecim argumentem `SeriesGlossary | None`.
- `services/translation/service.py`: MODIFY, `translate_file(..., glossary=None)` przekazuje glosariusz do fabryki.
- `engines/llm/config.py`: MODIFY, `LlmTranslateConfig.glossary: SeriesGlossary | None = None`.
- `engines/llm/service.py`: MODIFY, część glosariusza (P2–P5).
- `engines/llm/constants.py`, `prompts/loader.py`: MODIFY, zasób `glossary.md` z jednym tokenem.
- `engines/llm/prompts/glossary.md`: NEW.
- `engines/llm/prompts/translation.md`: MODIFY, sekcja R1 według D1–D4.
- `application/runtime.py`: MODIFY, fabryka przekazuje glosariusz do `LlmTranslateConfig` (`dataclasses.replace`).
- `services/translation/AGENTS.md`, `engines/llm/AGENTS.md`: MODIFY, nowe pułapki (kolejność części, filtr).
- testy: `test_translation_glossary.py` (NEW), `test_translation_llm.py`, `test_translation_prompts.py`, `test_translation_service.py` (MODIFY).

**Inwarianty:** I1, I2, P3; brak importu `services.catalog` w translation.

**Gate:** testy zielone; `test_translation_llm.py` bez zmian w istniejących asercjach.

**Human checkpoint (płatny, opcjonalny wariant z D7):** po commicie fazy 3, a przed fazą 4, silnik zna już reguły R1, ale nikt jeszcze nie dostarcza glosariusza. Jeden przebieg na tym stanie gałęzi to wariant „R1 bez glosariusza”. Komendy i odbiór jak w fazie 1.

### Faza 4: glosariusz serii w aplikacji

**Pliki:**

- `application/glossary.py`: NEW, rozpoznanie serii (D5) z `file_titles` przed wyszukiwaniem (G11) i tytułem sezonu (G12), klucz (D6), odczyt, dopisywanie, ponowne wczytanie tuż przed zapisem atomowym (G10), odporność G9; stan ownera tylko do odczytu (I4).
- `application/translation_handler.py`: MODIFY, `TranslationExecutor.translate_file(..., glossary=...)`; handler dostaje opcjonalnego dostawcę glosariusza.
- `application/runtime.py`: MODIFY, skład dostawcy (katalog AniList z istniejącym klientem HTTP aplikacji, `config_dir()`).
- `application/AGENTS.md`: MODIFY.
- testy: `tests/application/test_glossary.py` (NEW), `tests/application/test_handlers.py` (MODIFY).

**Gate:** testy zielone; ręczny smoke bez sieci: tłumaczenie pliku z pustym `config/glossaries/` w benchu kończy się sukcesem i ostrzeżeniem.

### Faza 5: przebieg po zmianie i akceptacja

**Human checkpoint (płatny, D7):**

```text
Uruchom: dwa przebiegi na gałęzi, te same katalogi wejściowe i ustawienia co w fazie 1, z pustym config/glossaries/ benchu
Zrób: po przebiegach przejrzyj raport M5 (17 par przed/po) i oceń każdą: lepiej / bez zmian / gorzej
Oczekiwany rezultat: S1–S5 spełnione
Zwróć uwagę na: wołacz, sufiksy, płeć Hino, pisownię Onsou/Gyokuyou/Hasegawa/Rebecca, tytuł Iceblade
Przekaż wynik jako: lista ocen w odpowiedzi lub w outcomes/01-glossary-bench.md
```

**Pliki:** `docs/work/16-proper-names/outcomes/01-glossary-bench.md` (NEW): liczby M2–M6 przed i po, ocena M5, koszt w znakach wejścia.

**Gate:** S1–S6 albo decyzja właściciela.

### Faza 6: dokumentacja

`docs/ideas.md` §1.1 (status pozycji), `docs/README.md` (wiersz 16-proper-names), `README.md` projektu, jeśli opisuje katalog `config/` (sprawdzić `config/README.md`). Treść: gdzie leży glosariusz i jak go poprawić.

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
|---|---|---|
| Postacie bez spoilerów, z limitem stron | unit z `httpx.MockTransport` | deterministyczna granica |
| Filtr i render wpisów | unit | czysta funkcja |
| Kolejność części i P3 | unit z fałszywym completerem | istniejący wzorzec `test_translation_llm.py` |
| Dopisywanie nie nadpisuje | unit + integration na `tmp_path` | inwariant I3 |
| Poprawa jakości | bench fazy 1 i 5 + ocena właściciela | testy nie mierzą jakości tłumaczenia |

### Testy (nazwy i markery)

`tests/scripts/subtitle_quality/test_quality_names.py`

- `@pytest.mark.unit test_name_accuracy_accepts_inflected_forms_of_a_declinable_entry`
- `@pytest.mark.unit test_name_accuracy_requires_the_exact_form_of_an_indeclinable_entry`
- `@pytest.mark.unit test_name_accuracy_misses_a_changed_spelling`
- `@pytest.mark.unit test_name_accuracy_rejects_a_dropped_long_vowel`
- `@pytest.mark.unit test_name_accuracy_accepts_a_consonant_alternation_in_the_dative`
- `@pytest.mark.unit test_name_accuracy_splits_a_hyphenated_suffix`
- `@pytest.mark.unit test_case_list_finds_a_case_by_start_time_and_source_text`
- `@pytest.mark.unit test_name_accuracy_rejects_a_feminine_form_of_an_indeclinable_male_name`
- `@pytest.mark.unit test_name_accuracy_reports_anilist_and_owner_entries_separately`
- `@pytest.mark.unit test_name_consistency_counts_distinct_stems_across_episodes`
- `@pytest.mark.unit test_honorific_conformance_follows_the_source_suffix`
- `@pytest.mark.unit test_vocative_check_flags_a_surname_vocative`
- `@pytest.mark.unit test_vocative_check_flags_a_polish_vocative_of_a_given_name`
- `@pytest.mark.unit test_case_list_pairs_lines_before_and_after`

`tests/services/catalog/test_anilist.py`

- `@pytest.mark.unit test_characters_read_names_gender_and_role`
- `@pytest.mark.unit test_characters_never_return_spoiler_names`
- `@pytest.mark.unit test_characters_stop_at_the_page_limit`
- `@pytest.mark.unit test_characters_stop_without_a_next_page`
- `@pytest.mark.unit test_characters_map_other_gender_to_unknown`
- `@pytest.mark.unit test_characters_raise_catalog_error_on_graphql_errors`

`tests/services/translation/test_translation_glossary.py`

- `@pytest.mark.unit test_entry_matches_a_whole_word_alias`
- `@pytest.mark.unit test_entry_ignores_a_word_inside_a_descriptive_phrase`
- `@pytest.mark.unit test_entry_marked_skip_never_matches`
- `@pytest.mark.unit test_entry_matches_an_uppercase_sign`
- `@pytest.mark.unit test_entry_ignores_a_lowercase_common_word`
- `@pytest.mark.unit test_rendered_line_lists_only_aliases_present_in_the_batch`

`tests/services/translation/test_translation_llm.py`

- `@pytest.mark.unit test_request_without_matching_entries_keeps_three_user_parts`
- `@pytest.mark.unit test_glossary_part_sits_between_style_and_numbered_lines`
- `@pytest.mark.unit test_split_halves_carry_their_own_filtered_glossary`
- `@pytest.mark.unit test_contract_repair_keeps_the_filtered_glossary`

`tests/services/translation/test_translation_prompts.py`

- `@pytest.mark.unit test_packaged_glossary_prompt_has_one_placeholder`
- `@pytest.mark.unit test_loader_rejects_glossary_prompt_without_placeholder`

`tests/services/translation/test_translation_service.py`

- `@pytest.mark.unit test_translate_file_passes_the_glossary_to_the_engine_factory`

`tests/application/test_glossary.py`

- `@pytest.mark.unit test_new_glossary_takes_names_gender_and_titles_from_anilist`
- `@pytest.mark.unit test_refresh_adds_entries_of_a_new_season_only`
- `@pytest.mark.unit test_refresh_keeps_owner_entries_and_skip_marks`
- `@pytest.mark.unit test_known_source_sends_no_catalog_request`
- `@pytest.mark.unit test_catalog_failure_returns_the_stored_glossary`
- `@pytest.mark.unit test_unknown_series_returns_no_glossary`
- `@pytest.mark.unit test_downloaded_series_uses_the_franchise_root`
- `@pytest.mark.unit test_refresh_merges_into_a_file_edited_during_the_fetch`
- `@pytest.mark.unit test_manual_file_resolves_the_series_by_title_search` (tylko przy D5 b)
- `@pytest.mark.unit test_known_file_title_sends_no_search` (tylko przy D5 b)
- `@pytest.mark.unit test_season_search_tries_the_season_title_first` (tylko przy D5 b)
- `@pytest.mark.integration test_glossary_file_round_trips_utf8_through_atomic_replace`
- `@pytest.mark.integration test_corrupt_glossary_file_is_left_untouched`

`tests/application/test_handlers.py`

- `@pytest.mark.unit test_translation_handler_passes_the_series_glossary`
- `@pytest.mark.unit test_translation_handler_translates_without_glossary_for_unknown_series`

Testy bez opisowej prozy: bez komentarzy i docstringów, scenariusz w nazwie (`tests/AGENTS.md`, hook `check_test_comments.py`).

### Bramki repo (przed każdym commitem)

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

CI uruchamia ruff tylko na `anishift/ tests/` (`.github/workflows/ci.yml:31-32`); hook pre-commit obejmuje pliki ze stage'a, a mypy sprawdza `scripts/subtitle_quality` przez importy z testów. Dla nowego modułu dodatkowo `uv run ruff check scripts/subtitle_quality/` i `uv run ruff format --check scripts/subtitle_quality/`, bez zmiany konfiguracji.

### Commity (jeden na temat, poprawki z review wchodzą do commitu tematu)

1. `feat(repo): measure proper-name accuracy and consistency of translated subtitles` (faza 1; scope dopasuj do wcześniejszych commitów `scripts/subtitle_quality` w `git log`)
2. `feat(services): fetch the characters of an AniList title` (faza 2)
3. `feat(translation): send the matching series glossary and proper-name rules to the LLM` (faza 3)
4. `feat(application): keep one glossary per series and pass it to translation` (faza 4)
5. `docs(repo): record the proper-names glossary measurement` (fazy 5–6)

Bez `Co-Authored-By` i stopek generatora (root `AGENTS.md`). PR z gałęzi do `main` po fazie 6.

## Dodatkowi wykonawcy

| Jednostka | Cel | Write scope | Owner integracji |
|---|---|---|---|
| A (autor) | fazy 1–4 | pliki z map faz | orkiestrator |
| B (inna rodzina modeli) | review każdej fazy przed commitem | read-only | orkiestrator |

Fazy 2 i 1 są niezależne i mogą iść równolegle; 3 zależy od 2 tylko przez typ w aplikacji (faza 4). Review krzyżowe według root `AGENTS.md`.

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
|---|---|---|---|
| Szum LLM większy niż efekt | różnica między dwoma przebiegami bazowymi tego rzędu co zmiana | trzeci przebieg tylko za zgodą właściciela | zawsze, bo płatne |
| Reguła sufiksów pogarsza naturalność (lektor czyta „san”) | ocena M5 | zmiana D1 przez właściciela; kod bez zmian (reguła jest w prompcie) | gdy właściciel oceni „gorzej” |
| AniList w stanie obniżonym lub niedostępny | 429/403 w logach | G9; ponowna próba przy następnym odcinku tej serii | nigdy dla jednego odcinka |
| Złe dopasowanie serii przy D5 (b) | obce postacie w pliku glosariusza | usunięcie pliku; dopasowanie zapisane w `titles` | gdy powtarza się dla wielu serii |
| Model ignoruje glosariusz | M2 bez poprawy przy pasujących wpisach | sprawdzić render i miejsce części; bez tego nie zmieniać modelu | po jednej iteracji |

## Definition of Done

- [ ] S1–S6 spełnione albo decyzja właściciela zapisana w outcome;
- [ ] bramki przeszły;
- [ ] zakres i zakazy zachowane;
- [ ] outcome z liczbami przed i po;
- [ ] checkpointy fazy 1 i 5 wykonane;
- [ ] AGENTS.md zmienionych obszarów zaktualizowane.

## Kontrakt wyniku

Status, zmienione pliki, wyniki bramek, liczby M2–M6 przed i po, oceny M5, odchylenia od planu, stan gałęzi i commitów, rekomendowany następny krok (w tym decyzja o etapie pamięci terminów).
