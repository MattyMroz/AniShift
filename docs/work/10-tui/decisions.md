# Etap 10 — dziennik decyzji

Zapis rozstrzygnięć podjętych w trakcie realizacji `tasks.json`: co zdecydowano, dlaczego
i co zostało świadomie odłożone. Uzupełniany po każdym zamkniętym zadaniu.

Tryb pracy: jeden model implementuje zadanie, drugi robi niezależne review, dopiero
potem integracja i commit. Bramka (`ruff check`, `ruff format --check`, `mypy`, `pytest`)
musi być zielona przed commitem.

## T-010 — dostęp do pól i atomowy zapis ustawień

Commit: `783c1b7`. Bramka: 2446 passed, 8 skipped.

### Rozstrzygnięcia

- **Trzy funkcje mapujące zamiast klasy.** D-08 podaje wolne funkcje, więc `field_access.py`
  eksponuje `read_setting_value`, `assign_setting_value` i `setting_is_active` bez rejestru
  ani obiektu strategii. Nie ma stanu do trzymania, więc klasa nic by nie wniosła.
- **Wyczerpalność typów pilnowana testem, nie ręczną listą.** Test iteruje `SettingValueType`
  i porównuje pokryty zbiór z pełnym enumem, więc dodanie nowego typu zapala test zamiast
  cicho wpadać w gałąź domyślną.
- **Odczyt zwraca `spec.default`, gdy pole trzyma `None` przy typie nieopcjonalnym.**
  Świadoma strata wierności na poziomie storage: świeży profil głosu trzyma `None`
  w `concurrency` i `native_*`, a surowy odczyt nie przeszedłby `spec.validate_value`.
  Skutek: `native_pitch=None` po odczycie i zapisie staje się `"+0Hz"`. Wartość efektywna
  się nie zmienia, więc zaakceptowane.
- **`STRING_SET` zapisywany posortowany.** Zbiór nie ma porządku, a `list(frozenset)`
  przy każdym uruchomieniu przestawiałby wpisy w `settings.json`. Sortowanie stabilizuje diff.
- **Nowy błąd domenowy `ConfigError`.** Publiczna granica `AppService` nie może rzucać
  gołego `ValueError` — AGENTS.md wymaga hierarchii `AniShiftError -> {Domain}Error`,
  a `get_preset` już zwraca domenowy `PlanningError`. Dla konfiguracji nie istniał żaden
  błąd domenowy, więc dodano jedną klasę, bez podklas, i wykorzystano istniejący
  `ErrorCode.CONFIG_INVALID`. Ekran ustawień potrzebuje kodu, żeby wyjaśnić odmowę.
  Wewnątrz czystego mapowania `field_access.py` zostają `ValueError`/`TypeError`.
- **`setting_is_persisted` jako czwarta funkcja publiczna.** Pierwotnie brak edytowalności
  wnioskowano z przechwyconego `ValueError`, co maskowałoby prawdziwy błąd katalogu jako
  „ustawienie nieaktywne”. Teraz specy workflow i środowiskowe są odrzucane bramką z góry,
  a `setting_is_active` wołane jest bez osłony, więc defekt mapowania wychodzi na wierzch.
- **Wycofanie aktywnego głosu idzie przez helper domenowy.** Generyczny `setattr` na
  `elevenbytes_custom_voices` nie informował `UserSettings`, że usuwany alias jest wybrany;
  `tts_voice_id` zostawał przy aliasie, a `resolved_tts_voice_id` dla elevenbytes zwraca
  `voice_id` bez dopasowania, więc `ensure_active_tts_profile` materializował profil
  `elevenbytes:<usunięty-alias>`. Naprawa w warstwie mapowania, nie w `__post_init__`,
  bo `_normalize_tts_selection` celowo zachowuje nieznane ID głosów providera i pilnuje
  tego istniejący test `test_invalid_fixed_engine_voices_normalize_but_custom_engines_preserve_ids`.

### Odłożone świadomie

- **Zmiana nazwy głosu resetuje wybór na głos wbudowany.** Diff całej listy nie odróżnia
  „zmieniono nazwę” od „usunięto i dodano”. Stan jest bezpieczny i bez zwisów. Śledzenie
  zmiany nazwy wymaga operacji per element, a nie podmiany listy — do rozważenia w T-011.
- **Ta sama pułapka istnieje na ścieżce wczytywania.** Ręczne usunięcie głosu z
  `config/settings.json`, gdy `tts_voice_id` nadal go nazywa, daje ten sam pozorny profil
  przez `load_user_settings`. Odrębny, wcześniejszy kontrakt; naprawa kolidowałaby
  z zachowaniem ID providera. Kandydat na osobne issue.

### Obserwacje

- Jednorazowy, niereprodukowalny failure testu współbieżności audio przy jednym z uruchomień
  pełnego zestawu. Kolejne przebiegi czyste. Do obserwacji — jeśli wróci, to wyścig, nie szum.

### Korekta zakresu

`update_secret` i `reload_environment` z D-08 zostały wyłączone z T-010, żeby zadanie
zamknęło się na jednym polu preferencji. Zakres T-011 obejmuje jednak edytor sekretów,
a nie wymienia `application/service.py`, więc te dwie metody powstały jako osobna jednostka
przed T-011 — luka w zakresowaniu, nie zmiana projektu.

## T-012 — katalog modeli JSONC

Commit: `4120a70`. Bramka: 2517 passed, 8 skipped.

### Rozstrzygnięcia

- **Parser tylko `json5`, dodany przez `uv add`.** Plan wprost zakazywał własnego strippera
  komentarzy i kazał zatrzymać zadanie, gdyby resolver nie wspierał Pythona 3.14.
  Sprawdzone przed zleceniem: `json5==0.15.0` rozwiązuje się czysto. Duplikaty kluczy łapie
  sam parser (`allow_duplicate_keys=False`), więc nie ma na to osobnego kodu.
- **Dwa poziomy walidacji, nie jeden.** Nieobsługiwany protokół, nieznany provider, puste ID
  i zła ścieżka wykluczają wpis i zgłaszają zaadresowany `CatalogIssue`, ale zwracają
  użyteczny katalog. Odrzucenie całego pliku sprawiłoby, że wpis znika — a R-054 wymaga
  dokładnie odwrotnie: ma zostać widoczny jako błąd konfiguracji. Cały plik odrzuca tylko
  niejednoznaczność, której nie da się bezpiecznie rozstrzygnąć: powtórzony alias, zły
  `schema_version`, pole wyglądające na sekret.
- **Reguła sekretów patrzy wyłącznie na nazwy pól schematu.** Pierwsza wersja przeszukiwała
  każdy klucz, więc provider nazwany `foundry-oauth` albo alias `nova-key` wysadzał cały
  katalog komunikatem o sekrecie. Review to zreprodukowało; naprawione przed commitem, mimo
  że recenzent dopuszczał wypuszczenie tego jako follow-up — plik pisze użytkownik ręcznie,
  a `foundry-oauth` to naturalna nazwa. Teraz klucze sekcji `providers` i `models` są
  pomijane, a ich wartości nadal przeszukiwane na dowolnej głębokości.
- **Dopasowanie po końcówce nazwy, nie po fragmencie.** `apiKey` i `access_token` są łapane,
  a `max_tokens` zostaje legalne. Znany martwy punkt: sekret z dalszym przyrostkiem
  (`authorization_header`, `token_id`) przechodzi. Zapisane w docstringu reguły jako
  ograniczenie, nie zamiecione pod dywan.
- **Zero pola dostępności w katalogu.** Obecność modelu w pliku to twierdzenie, nie obietnica;
  czy alias odpowiada, należy do sesji, która o to zapytała.
- **Klasa błędu zostaje przy module.** `errors.py` trzyma wyłącznie bazy i miksy, a każda
  domena definiuje swoje liście lokalnie — w samym `config/` jest już precedens
  (`workspace.py`). Sprawdzone policzalnie w review, nie przyjęte na słowo.

### Odłożone świadomie

- **Brak atomowego writera katalogu**, mimo że krok 7 planu go wymienia. Role modeli zapisują
  się do `UserSettings` (D-12), więc nic w T-013–T-015 nie zapisuje katalogu z powrotem,
  a `json5` i tak nie zachowa komentarzy użytkownika przy round-tripie. Konsekwencja do
  rozstrzygnięcia najpóźniej przy T-015: albo writer powstaje, albo `save_model_catalog`
  wypada z D-12. Nie może przejść niezauważone.
- **`CatalogIssue` są dziś tylko logowane na debug.** T-015 musi je pokazać w interfejsie,
  inaczej „wykluczony z błędem" będzie nieodróżnialny od „nie istnieje".
- Brak `schema_version` jest czytany jako `1` dla zgodności ze starym plikiem. Przy wersji 2
  brak tego pola musi stać się błędem, inaczej v2 dostanie po cichu semantykę v1.

## T-011 — rozstrzygnięcia przed implementacją

Pierwsze podejście do T-011 zatrzymało się na preflighcie, bez zapisanych plików. Nie było to
zmarnowane: wyszły z niego cztery blokery, z których dwa wymagały decyzji użytkownika.

- **Bramka importów TUI nie blokuje tego zadania.** `tests/tui/test_app_shell.py:260-273` skanuje
  AST całego drzewa `anishift/tui/**`, więc łapie importy również wewnątrz funkcji, ale lista
  zakazanych prefiksów to wyłącznie `anishift.services`, `anishift.pipeline`,
  `anishift.application.service` i `anishift.application.runtime`. Fasada `anishift.application`
  oraz `anishift.config.*` są dozwolone. Import odłożony (pod `TYPE_CHECKING` albo w ciele
  funkcji) nie ładuje backendu do `sys.modules`, więc przechodzi też sondę runtime.
- **`/auto` wypada z T-011.** Jego pola mają scope `AUTO_PRESET`/`MANUAL_RUN`, żyją w
  `AutoPreset`/`GroupIntent` i zapisują się przez `save_preset()`, a nie `update_setting()` —
  `read_setting_value` na nich rzuca. Jedno zadanie zostaje przy jednym mechanizmie zapisu;
  `/auto` dostaje własne zadanie jako edytor presetu. Te same względy dotyczą czterech
  globalnych preferencji bez przydziału domeny w D-09 (`processing_order_policy`,
  `audio_language_priority`, `subtitle_language_priority`, `composition_quality_preset`) —
  idą razem z `/auto`. `editor_for(spec)` pozostaje funkcją totalną nad `SettingValueType`
  niezależnie od routingu domen, więc kryterium pełnego pokrycia nadal jest dowodzone testem.
- **`openai_compatible_base_url` zostaje na razie bez edytora.** Jest polem środowiskowym
  `Settings` o scope GLOBAL, nie jest sekretem ani polem `UserSettings`, więc odrzuci je
  i `update_setting`, i `update_secret` — luka w D-08. Teraz wiersz tylko do odczytu,
  z adnotacją o pochodzeniu ze środowiska. Zapis warto dodać dopiero, gdy okaże się potrzebny.
- **Prototyp nie jest podtrzymywany.** `anishift/tui/prototype.py` sam deklaruje się jako
  tymczasowy, usuwany w T-016, a `cli/main.py` na nim stoi. Pierwotny pomysł, żeby `open_tts`
  rozgałęział się na „serwis wstrzyknięty albo stara ścieżka prototypu", został odrzucony:
  utrzymywanie legacy równolegle z nową ścieżką kosztuje więcej niż jest warte. T-011 zastępuje
  prototypowe pola ustawień prawdziwym panelem i usuwa razem z nimi ich testy; resztą prototypu
  zajmuje się T-016 zgodnie z planem.
- **Podsesje nie pytają użytkownika.** Pierwsze podejście stanęło, bo worker użył narzędzia
  `question`, które w kontekście podagenta zostało odrzucone. Worker ma raportować `BLOCKED`
  i wracać z pytaniem do orkiestratora, nigdy nie zatrzymywać się na pytaniu.

### Wynik

Commit: `81fbfbf`. Bramka: 2465 passed, 8 skipped (2455 − 4 usunięte prototypowe + 14 nowych).

- **Jeden dispatch klasyfikuje spec po typie wartości**, a nie po nazwie pola. Test iteruje
  `SettingValueType` i katalog, więc nowy typ pola zapala test zamiast wpaść w gałąź domyślną.
- **Kryterium „zmiana silnika zachowuje profile per głos" było najpierw dowodzone złym testem.**
  Round-trip silnika `elevenbytes → edge → elevenbytes` nie przywraca głosu:
  `_normalize_tts_selection` twardo ustawia `tts_voice_id` na Marka przy wejściu na `edge`
  i nie cofa tego przy powrocie, więc klucz profilu się zmienia. To zachowanie zastane,
  nie regresja. Test przepisano na oś głosu, ale to zostawiało oś silnika bez dowodu, więc
  dołożono osobny test: po round-tripie i jawnym przywróceniu głosu zapisany profil nadal
  trzyma ustawione tempo. Kryterium jest teraz dowiedzione na obu osiach, bez osłabiania go.
- **Brak podwójnej ścieżki dla prototypu.** Gdy serwisu nie ma, panel zgłasza ten sam
  `MISSING_SURFACE`, co każda inna niezbudowana powierzchnia — to istniejący wzorzec,
  nie reanimacja prototypu.

### Odłożone świadomie

- **Opcjonalnych pól liczbowych i tekstowych nie da się wyczyścić z powrotem do `None`.**
  `PromptDialog`/`NumberDialog` przy pustym zatwierdzeniu robią `dismiss(None)`, czego nie
  da się odróżnić od anulowania, więc oba są traktowane jako „bez zmiany". Dotyczy
  `llm_max_output_tokens`, `llm_temperature`, `llm_top_p` i `tts_output_bitrate`: raz nadaną
  wartość można zmienić, ale nie przywrócić domyślnego braku. Domknięcie wymaga zmiany
  kontraktu dialogów (osobny wynik „wyczyszczono" obok „anulowano"), co jest poza T-011.

## Sekrety i świeże ustawienia dla kolejnego runa

Commit: `b99807e`. Bramka: 2455 passed, 8 skipped.

### Rozstrzygnięcia

- **Nazwa zmiennej środowiskowej wyprowadzana, nie tabelaryzowana.** Katalog nie nosi nazw
  zmiennych — `SettingSpec` ma tylko `setting_id` i `is_secret`. Obowiązuje niezmiennik
  „ID sekretu == nazwa pola `Settings`", pilnowany istniejącym testem katalogu, więc nazwa
  powstaje z prefiksu pydantic. Druga tabela mapowań byłaby drugim źródłem prawdy.
  Dodatkowa bramka wymaga, by ID było polem `Settings` — nie da się zapisać klucza,
  którego aplikacja nie czyta.
- **Allowlist sekretów niezależna od `depends_on`.** Klucz DeepL da się wpisać, gdy silnikiem
  jest Google. Inaczej nie dałoby się skonfigurować silnika przed przełączeniem się na niego.
- **Semantyka czyszczenia wzięta z istniejącego `update_env_value`, nie wymyślona.**
  `None` usuwa linię z pliku, `""` zostawia puste przypisanie. Oba dają status „brak".
- **Bez drugiego loggera.** `update_env_value` już loguje klucz i akcję bez wartości.
- **Fabryka handlerów pyta o aktualne ustawienia, zamiast trzymać instancję z kompozycji.**
  To był realny defekt wykryty w review: status środowiska pokazywałby klucz jako
  skonfigurowany, a kolejny run leciałby starym. Kryterium T-011 dopuszczało też komunikat
  „wymagany restart", ale rozbieżność między tym, co panel pokazuje, a tym, czego używa run,
  jest pułapką na użytkownika, nie niedogodnością. Zmiana wyszła mała: fabryka dostaje
  `Callable[[], Settings]`, jedno miejsce konstrukcji w `bootstrap.py`, handlery i tak
  powstają per run. Żaden plik testowy nie wymagał zmiany, bo protokół wywołania fabryki
  został nietknięty.
- **`AppContext.settings` zostaje snapshotem z chwili startu.** To rekord composition roota,
  a nie źródło prawdy dla runów; po zmianie nikt nie czyta z niego sekretów w ścieżce
  wykonania.

### Odłożone świadomie

- **Zmienna wyeksportowana w środowisku procesu wygrywa nad `.env`.** Zachowanie istniejące
  i przetestowane. `update_secret` poprawnie zapisze plik, ale status pokaże wartość z shella.
  Docstring mówi to wprost; TUI powinno to komunikować, gdy wystąpi.

## T-013 — konfiguracja, token i router protokołów Foundry

Commit `0e41585`. Warstwa poprzedzająca żądanie: konfiguracja modelu, odczyt tokenu
i router builderów. Sam silnik oraz normalizacja odpowiedzi należą do T-014.

### Rozstrzygnięcia

- **Jeden algorytm precedencji tokenu, nie dwa.** Pierwsza wersja miała `AliasChoices`
  w `Settings` i osobną pętlę w `resolve_palantir_token`. Review pokazało realną
  rozbieżność: przy `ANISHIFT_PALANTIR_TOKEN="   "` i ustawionym `FOUNDRY_API_TOKEN`
  `Settings` zwracało `"   "`, a adapter `"compat-value"` — `AliasChoices` bierze pierwszą
  obecną wartość, nawet pustą, adapter trymuje i schodzi dalej. Testem pilnującym była
  tylko równość krotki nazw, więc semantyka mogła się rozjechać bez alarmu. Teraz
  `Settings` deleguje wybór do adaptera, a test porównuje wynik rozwiązania dla tego
  samego środowiska. Kierunek `config` → `services` jest tu zgodny z już istniejącym
  (`user_settings` woła rejestr silników tłumaczenia).
- **Skutek uboczny: zamknięta pułapka nieaktualnej zmiennej.** Skoro nazwa zgodnościowa
  jest czytana dopiero wtedy, gdy kanoniczna jest pusta, świeży token w `.env` wygrywa
  z wyeksportowanym `FOUNDRY_API_TOKEN`. Poprzednia sekcja opisywała to jako odłożone.
- **`AliasChoices` i globalne `populate_by_name` usunięte.** Istniały tylko po to, by
  utrzymać zduplikowaną precedencję. Przy zwykłej nazwie pola prefiks pydantic sam daje
  `ANISHIFT_PALANTIR_TOKEN`, a arytmetyka `_env_variable()` i allowlista `update_secret`
  działają bez zmian.
- **`ModelProtocol` przeniesiony do `services/llm/wire_protocol.py`.** Reużycie enuma
  z katalogu było słuszne — jedno słownictwo nie może się rozjechać — ale zrobiło z tego
  jedyny w repo import `services` → `anishift.config`. Katalog re-eksportuje enum, więc
  jego publiczna powierzchnia i testy T-012 zostały nietknięte. T-027 domyka granice
  architektury; lepiej odwrócić kierunek teraz niż budować na nim T-014 i T-015.
- **Brak importu między silnikami.** Sięgnięcie po jedną stałą do `engines/anthropic/
  constants.py` ciągnęło `anthropic/__init__.py` → `service` → SDK, czyli 25 modułów
  z `httpx` włącznie. To łamie regułę z `services/llm/AGENTS.md` o leniwym ładowaniu
  providerów. Stała jest lokalna, a dowodem jest sonda w podprocesie mierząca `sys.modules`
  — poprzednie `not hasattr(module, "httpx")` sprawdzało tylko brak rebindu.
- **Brak tokenu to błąd auth, nie konfiguracji.** Kryterium mówiło „typowany błąd
  konfiguracji", ale to proza planu, nie nazwa klasy; jej sens to szybkie, typowane
  odrzucenie przed siecią. Cztery istniejące silniki podnoszą `LlmAuthError` przy braku
  klucza, więc reguła brzmi: token (brak, pusty, niewysyłalny) → `LlmAuthError`; URL,
  protokół, alias, provider, model → `LlmConfigError`.
- **Zero nowych klas błędów.** Istniejąca taksonomia 13 klas pokrywa całe R-059. Podział
  429 na `LlmQuotaError` (fatalny) i `LlmRateLimitError` (przejściowy) idzie po markerach
  strukturalnych, nie po prozie komunikatu.

### Odłożone świadomie

- **`palantir_token_compat` jako osobne pole `Settings`.** Utrzymuje nazwę zgodnościową
  także w `.env`, nie tylko w środowisku procesu. Czytanie `os.environ` w walidatorze
  byłoby prostsze, ale cicho przestałoby honorować `.env` — a to główne miejsce, gdzie ten
  projekt trzyma sekrety. Pole jest wykluczone z dumpów, `repr=False` i czyszczone po
  rozwiązaniu. Świadomie odwracalne jedną linią, gdy zgodność przestanie być potrzebna.
- **`anthropic-version: 2023-06-01` niesprawdzone wobec dokumentacji proxy.** Stała pod
  ręką, T-014 zweryfikuje ją pierwszym realnym żądaniem.
- **Zapis tokenu wciąż niemożliwy.** `/connect` potrzebuje `SettingSpec` z `is_secret`
  w `_environment_specs()`; samo pole `Settings` nie wystarcza. Należy do T-015.

### Obserwacje

- **`anishift.config.model_catalog` ładuje `httpx` — defekt wcześniejszy niż ten etap.**
  Łańcuch: `config/__init__.py` → `field_catalog` → `user_settings` → `services/tts/engines/
  elevenbytes/__init__.py` → `.service` → `.api_backend`. Dokładnie ten sam wzorzec, co
  naprawiony wyżej, tylko w domenie TTS. Poza zakresem T-013; kandydat na strażnika
  leniwości w T-027.
