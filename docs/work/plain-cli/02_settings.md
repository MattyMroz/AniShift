# PLAN 02 — ustawienia Interactive CLI: Tłumaczenie, Lektor, Wynik i Połączenia

## 0. Status dokumentu

```text
STATUS: READY
MODE: UPDATE / REPLAN
SPEC AUTHORITY: spec.md
PREDECESSOR: PLAN 01 — Interactive CLI + Home + prawdziwy Auto
BASELINE BRANCH: work/interactive-cli/01-home-auto
BASELINE COMMIT: cd020dc4e0fabed54ff3e3d24d73d84253e1cd74
TARGET BRANCH: work/interactive-cli/02-settings
FINAL COMMIT: feat(cli): add interactive product settings
```

Plan odświeżono po wykonaniu PLANU 01 i potwierdzeniu finalnego SHA.

Plan przeszedł z `PREPARED` do `READY`, ponieważ:

```text
PLAN 01 IMPLEMENTED / COMMITTED
```

i wykonawca potwierdzi dokładny finalny commit PLANU 01.

Jeżeli wykonany PLAN 01 różni się materialnie od założeń opisanych niżej, wykonawca
nie naprawia architektury według własnego uznania. Wykonuje baseline refresh,
klasyfikuje drift i zatrzymuje się przy zmianie ownershipu, publicznego API,
persistencji albo zachowania produktu.

PLAN 02 jest jednym pionowym wycinkiem wykonywanym sekwencyjnie:

```text
fundament ustawień
→ Tłumaczenie
→ Lektor
→ Wynik
→ Połączenia
→ HITL
```

Nie dzielimy tego na cztery osobne plany.

Nie tworzymy dla PLANU 02:

- `tasks.json`;
- osobnego frameworka formularzy;
- managera presetów;
- advanced settings;
- Textual;
- command palette;
- slash commands;
- web UI;
- własnego systemu konfiguracji poza istniejącymi backendowymi źródłami prawdy.

---

## 1. Authority

Przed zmianą wykonawca czyta w całości:

```text
spec.md
01-plain-cli.md
AGENTS.md
anishift/AGENTS.md
anishift/cli/AGENTS.md
anishift/application/AGENTS.md
anishift/config/AGENTS.md
tests/AGENTS.md
```

Następnie czyta rzeczywisty kod po PLANIE 01, co najmniej:

```text
anishift/cli/interactive/app.py
anishift/cli/interactive/prompts.py
anishift/cli/interactive/home.py
anishift/cli/interactive/progress.py
anishift/cli/run.py
anishift/application/service.py
anishift/config/field_catalog.py
anishift/config/field_access.py
anishift/config/user_settings.py
anishift/config/presets.py
anishift/config/env_file.py
anishift/config/model_catalog.py
anishift/config/settings.py
config/anishift.models.example.jsonc
anishift/application/runtime.py
anishift/application/intents.py
```

`spec.md` jest authority dla WHAT.

Ten PLAN jest authority dla HOW PLANU 02.

Jeżeli lokalne nazwy z PLANU 01 są inne, ale kontrakt jest ten sam:

```text
adaptuj lokalnie
zachowaj ownership
raportuj istotną deviation
```

Jeżeli zmieniła się semantyka:

```text
STOP
REPLAN
```

---

## 2. Obowiązkowy baseline refresh

### 2.1. Finalny SHA poprzednika

Przed utworzeniem brancha agent musi znać:

```text
cd020dc4e0fabed54ff3e3d24d73d84253e1cd74
```

Nie wolno wpisać go z pamięci.

Nie wolno uznać nazwy brancha za stabilny baseline.

### 2.2. Kontrola Git

Uruchomić:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
```

Wymagane:

```text
working tree: clean
branch: work/interactive-cli/01-home-auto
HEAD: cd020dc4e0fabed54ff3e3d24d73d84253e1cd74
```

Jeżeli użytkownik po PLANIE 01 dodał zaakceptowany drobny commit, aktualnym baselinem
jest dokładny zaakceptowany HEAD, a nie wcześniejszy planowany commit.

### 2.3. Sprawdzenie rzeczywistego diffu PLANU 01

Przejrzeć:

```bash
git diff bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32..cd020dc4e0fabed54ff3e3d24d73d84253e1cd74 --stat
git diff bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32..cd020dc4e0fabed54ff3e3d24d73d84253e1cd74 --name-only
```

W szczególności ustalić rzeczywiste symbole odpowiedzialne za:

```text
Home dispatch
single-owner Prompt Toolkit renderer
Rich progress
Auto flow
result/error rendering
```

### 2.4. Oczekiwane odpowiedzialności po PLANIE 01

PLAN 02 zakłada logicznie:

```text
interactive/app.py
    pętla Home i dispatch Auto / Ręczny / Ustawienia / Wyjście

interactive/prompts.py
    jedyny właściciel aplikacji Prompt Toolkit, klawiszy i alternate screen

interactive/home.py
    rendering Home

interactive/progress.py
    rendering przebiegu, wyniku i błędu

cli/run.py
    UI-neutralny realny Auto flow
```

Dokładne prywatne nazwy funkcji nie są kontraktem.

### 2.5. Drift dozwolony bez replanu

Dozwolone:

- inna prywatna nazwa helpera;
- jeden dodatkowy plik test helper;
- drobna korekta layoutu zaakceptowana podczas `HOME PASS`;
- lokalne rozbicie jednej funkcji dla czytelności;
- dodanie parametru adaptera promptów bez zmiany semantyki.

### 2.6. Drift wymagający replanu

Zatrzymać się, jeżeli PLAN 01:

- zrezygnował z pojedynczego ownera aplikacji Prompt Toolkit;
- przeniósł Interactive CLI do innej warstwy niż `anishift/cli`;
- pozwolił Interactive importować konkretne `services`;
- wprowadził globalny UI store;
- zmienił `AppService` jako granicę produktu;
- zmienił persistencję `settings.json`, `presets.json` lub `.env`;
- zmienił cztery akcje Home;
- usunął wspólną ścieżkę wykonania potrzebną później Manualowi.

---

## 3. Potwierdzony current state backendu

Ta sekcja opisuje current state zweryfikowany na `feature/plain-cli` przed PLANEM 01.
PLAN 02 ma sprawdzić, że PLAN 01 nie naruszył tych kontraktów.

### 3.1. UserSettings

`anishift/config/user_settings.py` zapisuje trwałe preferencje do:

```text
config/settings.json
```

Obecny model posiada między innymi:

```text
translation_engine
translation_fallback_chain
translation_batch_size
translation_concurrency
translation_max_retries

llm_provider
llm_provider_model_id
llm_temperature
llm_top_p
llm_max_output_tokens
llm_prompt_id
llm_style_id
llm_module_ids
llm_max_concurrency

primary_model_alias
palantir_enrollment_base_url

tts_engine
tts_provider_model_id
tts_voice_id
tts_max_retries
tts_output_profile
tts_output_bitrate
tts_timeline_policy
narrator_mix_base_gain_db
original_gain_db
tts_voice_profiles

composition_quality_preset
audio_language_priority
subtitle_language_priority
```

PLAN 02 nie wystawia wszystkich tych pól.

### 3.2. Field Catalog

`anishift/config/field_catalog.py` opisuje ustawienia jako dane.

`SettingSpec` jest źródłem między innymi:

```text
setting_id
label
description
value_type
allowed_values
minimum
maximum
validation_pattern
depends_on
scope
is_secret
```

Catalog jest źródłem walidacji i zależności.

Nie jest automatycznym menu użytkownika.

### 3.3. Field Access

`anishift/config/field_access.py` ma publiczne:

```text
read_setting_value
assign_setting_value
setting_is_active
setting_is_persisted
```

To jest jedyna translacja między `SettingSpec` i fizyczną strukturą `UserSettings`,
w tym:

```text
tts_profile.*
tts_profile.engine_options.*
```

Interactive nie implementuje tego mapowania drugi raz.

### 3.4. Presets

`anishift/config/presets.py` utrzymuje:

```text
config/presets.json
```

`AutoPresetFile` zawiera:

```text
presets
default_preset_id
```

Jeden `AutoPreset` zawiera produktowe decyzje workflow:

```text
products
subtitle_source_policy
translation_action
source_subtitle_language
subtitle_output_format
```

`save_presets()` zapisuje atomowo.

PLAN 02 nie buduje UI do tworzenia i nazywania presetów.

### 3.5. Model Catalog

`anishift/config/model_catalog.py` jest właścicielem lokalnego katalogu:

```text
config/anishift.models.jsonc
```

Repo dostarcza:

```text
config/anishift.models.example.jsonc
```

Katalog ma:

```text
ProviderEntry
    provider_id
    protocol
    path

ModelEntry
    alias
    provider_id
    model_id
    label
    experimental
    limits

CatalogDefaults
    primary
    translation
```

Katalog:

- jest read-only dla AniShift;
- akceptuje JSONC i komentarze;
- nie zawiera sekretów;
- nie przechowuje enrollment URL;
- nie przechowuje runtime availability;
- nie robi sieci przy `load_model_catalog()`.

### 3.6. Environment Settings

`anishift/config/settings.py` ładuje sekrety z:

```text
system environment
.env
```

System environment ma pierwszeństwo.

Palantir używa:

```text
ANISHIFT_PALANTIR_TOKEN
```

z kompatybilnym wejściem:

```text
FOUNDRY_API_TOKEN
```

### 3.7. AppService

`AppService` jest synchronizowaną, UI-independent fasadą.

Current code już importuje mechanizmy:

```text
field_access
update_env_value
model catalog
presets
settings saver
```

Przed dopisaniem publicznej metody wykonawca ma przeczytać całą sekcję konfiguracji
`AppService` i wykorzystać istniejącą operację, jeśli już spełnia kontrakt.

Nie tworzyć dodatkowej `SettingsService` tylko dlatego, że frontend potrzebuje helpera.

---

## 4. Current State / Gap

| Obszar | Stan po PLANIE 01 | Stan wymagany po PLANIE 02 | Akcja |
|---|---|---|---|
| Home | realny | `Ustawienia` działa | podłączyć |
| Prompt adapter | select | select/checkbox/text/password/confirm | rozszerzyć tylko brakujące |
| settings.json | działa | edycja wybranych pól | użyć istniejącego contractu |
| Field Catalog | technicznie pełny | product allowlist | jawna mapa |
| Ogólne | brak menu | kolejność, języki, jakość | dodać |
| Tłumaczenie | brak menu | sekcje podstawowe/wydajność/model/prompt | dodać |
| Lektor | brak menu | aktywne pola engine/profile/audio | dodać |
| Wynik | preset backend | 4 products | dodać transakcję |
| Połączenia | env backend | status/set/remove/test | dodać |
| Model Catalog | JSONC | read-only picker | dodać |
| Save | brak | nadal brak | nie dodawać |

---

## 5. Jedno pytanie PLANU 02

PLAN 02 odpowiada tylko na pytanie:

> Czy użytkownik może wejść z Home do małego menu ustawień, zmienić wyłącznie
> produktowe decyzje Tłumaczenia, Lektora, Wyniku i Połączeń, a każda zaakceptowana
> zmiana zostaje zwalidowana i zapisana przez istniejące źródła prawdy bez budowania
> drugiego systemu konfiguracji?

Po wykonaniu odpowiedź musi brzmieć:

```text
TAK
```

---

## 6. Wynik widoczny dla użytkownika

### 6.1. Home

Home pozostaje:

```text
ANISHIFT

[ mascot placeholder ]

● Auto
  Ręczny
  Ustawienia
  Wyjście

↑↓ wybór · Enter zatwierdź                    v0.x.x
```

Na Home nie pojawia się żaden settings status.

### 6.2. Settings root

```text
USTAWIENIA

● Ogólne
  Tłumaczenie
  Lektor
  Wynik
  Połączenia
  Przywróć domyślne
  Wróć
```

### 6.3. Tłumaczenie

```text
TŁUMACZENIE

● Silnik tłumaczenia
  Model tłumaczenia
  Silniki awaryjne
  Linii na zapytanie
  Partii jednocześnie
  Plików LLM jednocześnie
  Temperatura / Top-p / Limit tokenów
  Prompt
  Styl
  Moduły promptu
  Wróć
```

`Model tłumaczenia` jest widoczny tylko, gdy aktywny engine korzysta z LLM.

### 6.4. Lektor

```text
LEKTOR

● Silnik
  Model / endpoint
  Głos
  Syntez jednocześnie
  Ponowienia
  Tempo i ustawienia natywne
  Kodek / bitrate
  Głośność lektora
  Głośność oryginału
  Wróć
```

### 6.5. Wynik

```text
WYNIK

● Polskie napisy
● Polski lektor
● MKV
○ MP4
  Zapisz
  Przywróć domyślne
  Wróć
```

W multi-select marker zawsze znajduje się po lewej.

Nie wolno renderować:

```text
Polskie napisy       [x]
MP4                   [ ]
```

### 6.6. Połączenia

Przykładowo:

```text
POŁĄCZENIA

● Palantir Foundry       skonfigurowane
  Gemini                 brak
  OpenAI                 brak
  Anthropic              brak
  DeepSeek               brak
  OpenRouter             brak
  DeepL                   brak
  ElevenLabs             brak
  Wróć
```

Status jest krótką informacją.

Nie jest checkboxem.

### 6.7. Pojedynczy zapis

Po poprawnej zmianie:

```text
✓ Zapisano
```

Następnie wracamy do bieżącej kategorii.

Nie istnieje:

```text
Save
Save all
Apply
Unsaved changes
```

---

## 7. Świadomie poza zakresem

PLAN 02 nie implementuje:

- trybu Ręcznego;
- finalnej maskotki;
- Chafa;
- Sixel;
- animacji;
- download anime;
- managera presetów;
- tworzenia presetów;
- usuwania presetów;
- edycji JSONC model catalog;
- `Advanced`;
- settings search;
- command palette;
- slash commands;
- globalnego draftu ustawień;
- restartu aplikacji po zmianie;
- automatycznych requestów sieciowych przy otwieraniu pickerów.

Brak tych rzeczy nie jest FAIL.

---

## 8. Mapa workstreamu

```text
01 Interactive Home + Auto
   wymagane: VERIFIED / COMMITTED

02 Settings
   TEN PLAN

03 Manual
   PREPARED / BLOCKED DO PASS PLANU 02

04 Mascot + Polish + Cleanup
   PREPARED / BLOCKED DO PASS PLANU 03
```

---

## 9. Technical Design

### D02-01 — Interactive nie zapisuje config files bezpośrednio

Kod:

```text
anishift/cli/interactive/**
```

nie wywołuje bezpośrednio:

```text
save_user_settings()
save_presets()
update_env_value()
Path.write_text()
```

Mutacje przechodzą przez `AppService`.

### D02-02 — jawna product allowlist

Nie implementować:

```python
for spec in service.settings_catalog():
    render(spec)
```

jako publicznego Settings.

Interactive ma jawnie wybrać tylko pola dozwolone przez `spec.md`.

### D02-03 — SettingSpec nadal jest źródłem walidacji

Product allowlist określa **co pokazać**.

`SettingSpec` określa:

```text
typ
allowed values
minimum / maximum
pattern
depends_on
```

Nie duplikować tych reguł w frontendzie.

### D02-04 — jedna zmiana = jedna transakcja

Flow:

```text
wybierz pole
→ świeży snapshot
→ pokaż current value
→ edit
→ validate
→ persist
→ swap in-memory state
→ return
```

Nie trzymać wielkiego `SettingsDraft` przez całą wizytę w menu.

### D02-05 — mały zestaw editor primitives

Do PLANU 02 potrzebne są najwyżej:

```text
select one
select many
text
number
password
confirm
```

Nie tworzyć frameworka rendererów wszystkich `SettingValueType`.

### D02-06 — Model Catalog jest read-only

Model picker:

```text
AppService / ModelCatalog
→ usable ModelEntry
→ label
→ select alias
```

Nigdy:

```text
rewrite JSONC
append model
persist availability
```

### D02-07 — model tłumaczenia jest atomową domenową decyzją

Jeżeli wybrany alias wymaga zsynchronizowania:

```text
llm_provider
llm_provider_model_id
```

lub Palantir-specific mapping, robi to application/config boundary.

Interactive nie zna:

```text
ProviderEntry.path
ModelProtocol
RID mapping
proxy routes
```

Jeżeli `AppService` ma już gotową operację wyboru modelu, użyć jej.

Jeżeli nie ma, dodać jedną minimalną operację domenową.

### D02-08 — PromptRegistry jest źródłem promptów

Nie hard-code listy prompt IDs w Interactive.

To samo dotyczy style IDs.

### D02-09 — TTS provider model pozostaje techniczny

Użytkownik wybiera:

```text
engine
voice
tempo
narrator gain
original gain
```

Nie wybiera `tts_provider_model_id` w tym workstreamie.

### D02-10 — Output aktualizuje default preset

`Wynik` zmienia wyłącznie `ProductIntent` aktywnego domyślnego Auto preset.

Nie tworzy nowego presetu.

### D02-11 — product transaction jest atomowa

Cztery checkboxy są zatwierdzane jako jeden nowy `ProductIntent`.

Nie zapisuj po każdym Space.

### D02-12 — co najmniej jeden product

Pusty wybór:

```text
✗ Wybierz co najmniej jeden wynik.
```

Bez zapisu.

### D02-13 — secrets mają oddzielną ścieżkę

Sekret nie jest `UserSettings`.

Flow:

```text
password prompt
→ AppService secret operation
→ existing atomic .env mechanism
→ Settings reload
```

### D02-14 — blank secret nie znaczy delete

Pusty password:

```text
cancel / no change
```

Delete jest osobną, potwierdzoną akcją.

### D02-15 — environment precedence pozostaje prawdziwe

Jeżeli system environment przesłania `.env`, UI nie może twierdzić, że usunięcie wpisu
z `.env` wyłączyło provider.

Pokazujemy safe informację o source override, bez wartości.

### D02-16 — probe jest jawny

Sieć może zostać wykonana tylko po akcji:

```text
Testuj połączenie
```

Nie przy otwarciu:

```text
Settings
Połączenia
Model picker
```

### D02-17 — zmiana Settings dotyczy następnego runu

Bieżący `ExecutionPlan.settings` jest immutable.

PLAN 02 nie próbuje zmieniać aktywnego runu.

---

## 10. Ownership po PLANIE 02

### 10.1. Prompt Toolkit interaction

Owner:

```text
anishift/cli/interactive/prompts.py
```

Odpowiada za high-level:

```text
select
checkbox
text
password
confirm
cancel semantics
```

Nie zna `UserSettings`.

### 10.2. Settings navigation

Owner:

```text
anishift/cli/interactive/settings.py
```

Odpowiada za:

- kategorie;
- kolejność pól;
- product allowlist;
- format label/value;
- dispatch editorów;
- powrót.

Nie zapisuje plików.

### 10.3. Typed editor adapter

Owner:

```text
anishift/cli/interactive/settings_editors.py
```

Odpowiada za:

```text
SettingSpec + current value
→ prompt
→ typed candidate / cancel
```

Nie posiada AppService.

### 10.4. Persisted preferences

Owner:

```text
anishift/config/user_settings.py
anishift/config/field_access.py
anishift/application/service.py
```

### 10.5. Workflow products

Owner:

```text
anishift/config/presets.py
anishift/application/intents.py
anishift/application/service.py
```

### 10.6. Model metadata

Owner:

```text
anishift/config/model_catalog.py
config/anishift.models.jsonc
```

### 10.7. Secrets

Owner:

```text
anishift/config/settings.py
anishift/config/env_file.py
anishift/application/service.py
```

### 10.8. Home dispatch

Owner pozostaje:

```text
anishift/cli/interactive/app.py
```

`app.py` nie implementuje formularzy.

---

## 11. Twarde inwarianty

### I02-001

Nie dodawać Textual.

### I02-002

Nie tworzyć `anishift/tui`.

### I02-003

Home nadal ma dokładnie cztery akcje.

### I02-004

Home nie dostaje wartości ustawień.

### I02-005

Nie ma globalnego Save.

### I02-006

Successful field edit od razu persistuje.

### I02-007

Validation failure nie zapisuje nic.

### I02-008

Persistence failure nie zmienia in-memory current state.

### I02-009

Interactive nie zapisuje `.env` bezpośrednio.

### I02-010

Interactive nie zapisuje `settings.json` bezpośrednio.

### I02-011

Interactive nie zapisuje `presets.json` bezpośrednio.

### I02-012

AniShift nie zapisuje `anishift.models.jsonc`.

### I02-013

Sekrety nie są echo’owane.

### I02-014

Sekrety nie trafiają do logów.

### I02-015

Model picker nie robi sieci.

### I02-016

Nie renderować token suffixów.

### I02-017

Technical fields pozostają ukryte nawet jeśli dawny katalog oznacza je jako `VISIBLE`.

### I02-018

Nie tworzyć `Advanced`.

### I02-019

Nie tworzyć managera presetów.

### I02-020

Nie modyfikować schedulerów ani handlerów.

### I02-021

Nie zmieniać retry/fallback semantics z PLANU 01.

### I02-022

`TerminalRenderer` pozostaje jedynym ownerem aplikacji Prompt Toolkit i interakcji
klawiaturowej.

---

## 12. Dokładna product allowlist

Zakres został rozszerzony po ręcznej ocenie produktu: panel ma udostępniać realne
ustawienia pracy, nie tylko pięć pól demonstracyjnych. Długie listy pozostają
responsywne dzięki sekcjom i pionowemu oknu wokół kursora.

### 12.0. Ogólne — widoczne

```text
processing_order_policy
audio_language_priority
subtitle_language_priority
composition_quality_preset
```

### 12.1. Tłumaczenie — widoczne

```text
translation_engine
translation model selection
translation_fallback_chain
translation_batch_size
translation_concurrency
translation_max_retries
llm_temperature
llm_top_p
llm_max_output_tokens
llm_prompt_id
llm_style_id
llm_module_ids
llm_max_concurrency
```

### 12.2. Tłumaczenie — ukryte

```text
primary_model_alias
```

### 12.3. Lektor — widoczne

```text
tts_engine
tts_provider_model_id
tts_voice_id
tts_max_retries
tts_profile.postprocess_tempo
tts_profile.voice_mix_offset_db
tts_profile.concurrency
tts_profile.native_rate
tts_profile.native_volume
tts_profile.native_pitch
tts_profile.engine_options.*
elevenbytes_vpn_enabled
tts_output_profile
tts_output_bitrate
narrator_mix_base_gain_db
original_gain_db
```

### 12.4. Lektor — ukryte

```text
tts_timeline_policy
elevenbytes_custom_voices
```

### 12.5. Wynik — widoczne

Mapowanie:

```text
Polskie napisy  -> ProductKind.FULL_PL
Polski lektor   -> ProductKind.NARRATION_AUDIO
MKV             -> ProductKind.MKV
MP4             -> ProductKind.MP4
```

### 12.6. Wynik — ukryte

```text
SOURCE_SUBTITLES
SPOKEN_PL
DISPLAYED_PL
mkv_tracks
burn_subtitle_product
mp4_audio_source
```

### 12.7. Połączenia — możliwe do zarządzania

Tylko backendowo istniejące:

```text
palantir_token
palantir_enrollment_base_url
gemini_api_key
openai_api_key
anthropic_api_key
deepseek_api_key
openrouter_api_key
openai_compatible_api_key
openai_compatible_base_url
deepl_api_key
elevenlabs_api_key
```

Nie dodawać nieistniejącego providera jako placeholder.

---

## 13. Kontrakt menu Settings

### 13.1. Brak fullscreen panelu

Każdy poziom jest prostym promptem.

### 13.2. Header

Rich może wyrenderować:

```text
USTAWIENIA
```

bez ciężkiej ramki.

### 13.3. Current value

W kategorii wolno pokazać current value jako informację:

```text
Silnik tłumaczenia        LLM
Model tłumaczenia         Claude Sonnet
```

To nie jest status checkboxa.

### 13.4. Wąski terminal

Jeżeli dwukolumnowy zapis nie jest czytelny:

```text
Tempo · 1.25×
```

albo:

```text
Tempo
1.25×
```

### 13.5. Powrót

Każdy submenu ma:

```text
Wróć
```

`Esc` korzysta ze wspólnego bindingu `TerminalRenderer` z PLANU 01.

Nie dodawać niskopoziomowych bindingów wyłącznie dla estetyki.

### 13.6. Reset

Root ma `Przywróć domyślne` bezpośrednio przed `Wróć`. Akcja wymaga confirm,
przywraca `UserSettings()` i nie dotyka `.env` ani presetów. Wynik ma osobny lokalny
reset wyboru produktów obok `Wróć`.

---

## 14. Kontrakt editorów

### 14.1. `select one`

Źródło options:

```text
SettingSpec.allowed_values
```

albo jawna domenowa lista udostępniona przez AppService.

Kursor startuje na current value.

Cancel = no write.

### 14.2. `number`

Potrzebny dla:

```text
postprocess_tempo
narrator_mix_base_gain_db
original_gain_db
```

Current value jest default inputu.

Walidacja zakresu pochodzi z `SettingSpec`.

Invalid input:

```text
krótki błąd
→ reprompt
```

### 14.3. `text`

Używać tylko, gdy domena naprawdę wymaga swobodnego tekstu.

Nie zamieniać selectów z allowed values na text input.

### 14.4. `password`

- input masked;
- pusty = cancel/no change;
- value nigdy nie wraca do rendererów po zapisie.

### 14.5. `confirm`

Tylko dla destrukcyjnych/sieciowych działań wymagających jawności:

```text
remove secret
test paid/network connection, jeśli wymagane
```

---

## 15. Kontrakt Tłumaczenia

### 15.1. Silnik

Lista pochodzi z application/config boundary.

Interactive nie importuje concrete translation registry z `services`.

### 15.2. LLM condition

Jeżeli:

```text
translation_engine != llm
```

ukryj:

```text
Model tłumaczenia
Prompt
Styl
```

Jeżeli obecny produkt nadal używa prompt/style wyłącznie dla LLM, trzymaj tę zależność.

### 15.3. Model picker

Dla każdego skonfigurowanego providera pokazuj osobną sekcję i dokładny model ID:

```text
GOOGLE GEMINI
  gemini-...

OPENROUTER
  provider/model-...
```

Sugestie providerów pochodzą z lekkiego `suggested_model_ids()`. Picker nie wykonuje
requestu sieciowego.

### 15.4. Provider i model

Wybór direct providera zapisuje jedną transakcją `llm_provider` oraz dokładny
`llm_provider_model_id`.

Dla Palantir wybór UI operuje aliasem katalogu.

Rozwiązanie aliasu do protocol/provider/model ID pozostaje poza frontendem.

Wpisy przykładowe `replace-with-*` nigdy nie są opcją. Palantir pojawia się dopiero,
gdy istnieją token, enrollment URL oraz przynajmniej jeden prawdziwy lokalny alias/RID.
Sekcje Palantir są dodatkowo dzielone według protokołu OpenAI, Anthropic, Google lub
xAI, ponieważ Foundry proxy zachowuje natywny format każdego providera.

### 15.5. Catalog issues

Entry-level issue:

- valid entries nadal działają;
- pokaż krótki warning z liczbą problemów;
- nie pokazuj raw parser input;
- nie hard-code fallback listy.

### 15.6. File-level catalog error

Pokaż:

```text
✗ Nie można wczytać katalogu modeli.
Napraw config/anishift.models.jsonc.
```

Potem wróć.

### 15.7. Prompt

Lista pochodzi z istniejącego `PromptRegistry` przez właściwą boundary.

### 15.8. Styl

Analogicznie.

### 15.9. No network

Otwarcie model picker jest całkowicie lokalne.

---

## 16. Kontrakt Lektora

### 16.1. Engine

Lista z backendowego catalog/availability contract.

### 16.2. Voice

Lista zależy od active engine.

Jeżeli active `SettingSpec` ma `allowed_values`, to jest źródło listy.

Jeżeli backend jawnie dopuszcza swobodny provider voice ID, text input jest dozwolony
tylko dla tej ścieżki.

### 16.3. Engine switch

`UserSettings` może normalizować:

```text
tts_provider_model_id
tts_voice_id
active voice profile
```

Frontend nie powiela tej logiki.

### 16.4. Tempo

Mapuje dokładnie:

```text
tts_profile.postprocess_tempo
```

### 16.5. Głośność lektora

Mapuje:

```text
narrator_mix_base_gain_db
```

### 16.6. Głośność oryginału

Mapuje:

```text
original_gain_db
```

### 16.7. Provider tuning

Pokazuj wyłącznie aktywne pola z `SettingSpec`: stability, similarity, style, speaker
boost, native pitch/rate/volume, speed, concurrency i format, zależnie od silnika.

---

## 17. Kontrakt Wyniku

### 17.1. Odczyt

Pobierz:

```text
default_preset_id()
get_preset(default_id)
```

### 17.2. Initial selection

Preselectuj cztery publiczne produkty z current `ProductIntent`.

### 17.3. Commit

Enter lub Space na produkcie przełącza marker. Po Enter na osobnym `Zapisz`:

1. upewnij się, że wybór nie jest pusty;
2. zbuduj nowy `ProductIntent`;
3. zachowaj pozostałe pola `AutoPreset`;
4. zapisz jedną operacją `save_preset`;
5. wróć do menu.

### 17.4. Derived defaults

Polityka v1:

```text
burn_subtitle_product = NONE
mp4_audio_source = AUTO
mkv_tracks = empty, chyba że current default preset ma backendowo bezpieczne track defaults,
             które planner już interpretuje poprawnie
```

Nie dodawać pytań o te wartości.

Jeżeli zachowanie existing planner wymaga konkretnych MKV track defaults do osiągnięcia
produktowego wyniku, wykonawca ma odczytać planner/testy i zachować istniejący bezpieczny
preset behavior zamiast wymyślać nowe UI.

---

## 18. Kontrakt Połączeń

### 18.1. Status

Dozwolone publiczne wartości:

```text
skonfigurowane
brak
```

Jeżeli wartość jest przesłaniana przez system environment:

```text
skonfigurowane · system
```

bez wartości sekretu.

### 18.2. Menu połączenia

Minimalnie:

```text
● Ustaw / zmień
  Usuń
  Testuj
  Wróć
```

`Testuj` tylko tam, gdzie backend posiada rzeczywisty probe.

### 18.3. Brak fikcyjnych probe

Jeżeli current backend ma jawny model probe wyłącznie dla Palantir:

- `Testuj` istnieje dla Palantir;
- nie implementować własnych requestów testowych dla OpenAI/Gemini/etc.

### 18.4. Palantir enrollment URL

To persisted user setting.

Nie zapisuje się do `.env`.

### 18.5. OpenAI-compatible URL

To regular setting powiązane z istniejącym providerem.

Nie mieszać z Palantir.

### 18.6. Secret write

Po successful atomic write `AppService.current_settings()` musi widzieć nową wartość.

### 18.7. Remove

Wymaga confirm.

Jeżeli system env nadal dostarcza wartość, status po usunięciu `.env` nadal jest
`skonfigurowane · system`.

---

## 19. Error semantics

### 19.1. Validation

```text
✗ Nieprawidłowa wartość.
```

plus jedna konkretna podpowiedź.

### 19.2. Persistence

```text
✗ Nie udało się zapisać ustawienia.
```

Previous state pozostaje aktywny.

### 19.3. Model catalog

Safe, bez raw parser dumpu.

### 19.4. Sekrety

Nie wyświetlać `repr(error)` jeśli może zawierać user input.

### 19.5. Ctrl+C

Nie zostawia tmp files.

Powrót/cancel zgodny z adapterem PLANU 01.

---

## 20. Docelowe drzewo

```text
anishift/cli/
├── main.py
├── run.py
└── interactive/
    ├── __init__.py
    ├── app.py
    ├── home.py
    ├── mascot.py
    ├── progress.py
    ├── prompts.py
    ├── settings.py
    └── settings_editors.py

tests/cli/
├── test_main.py
├── test_run.py
├── test_interactive_app.py
├── test_interactive_home.py
├── test_interactive_progress.py
├── test_interactive_settings.py
└── test_interactive_settings_editors.py
```

Nie tworzyć:

```text
settings/
forms/
screens/
widgets/
settings_store.py
settings_router.py
settings_context.py
settings_repository.py
settings_framework.py
```

---

## 21. Expected Touch Set

### 21.1. Prawdopodobnie nowe

```text
anishift/cli/interactive/settings.py
anishift/cli/interactive/settings_editors.py
tests/cli/test_interactive_settings.py
tests/cli/test_interactive_settings_editors.py
```

### 21.2. Prawdopodobnie modyfikowane

```text
anishift/cli/interactive/app.py
anishift/cli/interactive/prompts.py
anishift/cli/AGENTS.md
pyproject.toml
uv.lock
```

### 21.3. Warunkowo modyfikowane tylko przy realnej luce

```text
anishift/application/service.py
tests/application/test_service.py
```

### 21.4. Read-only domyślnie

```text
anishift/config/field_catalog.py
anishift/config/field_access.py
anishift/config/user_settings.py
anishift/config/presets.py
anishift/config/env_file.py
anishift/config/model_catalog.py
anishift/config/settings.py
anishift/application/intents.py
anishift/application/runtime.py
config/anishift.models.example.jsonc
```

### 21.5. Zakazane

```text
anishift/services/**
anishift/application/scheduler*
anishift/application/*_handler.py
anishift/tui/**
anishift/pipeline/**
workspace/**
external/**
.github/**
```

Jeżeli realna luka wymaga config schema change, zatrzymaj się przed zmianą i raportuj:

```text
CURRENT CONTRACT
MISSING CAPABILITY
MINIMAL REQUIRED CHANGE
WHY EXISTING APP SERVICE CANNOT SOLVE IT
```

---

## 22. Plik — `settings_editors.py`

### 22.1. Rola

Jeden mały typed adapter.

Wejście:

```text
SettingSpec
current SettingValue
prompt facade
```

Wyjście:

```text
typed candidate
albo cancel sentinel
```

### 22.2. Zakaz I/O

Nie importować:

```text
AppService
Path
save_user_settings
save_presets
update_env_value
```

### 22.3. Publiczne minimum

Plan nie wymusza nazw prywatnych helperów.

Potrzebna jest jedna publiczna odpowiedzialność logiczna:

```python
edit_setting(spec, current, prompts) -> SettingValue | Cancelled
```

### 22.4. Typed conversion

```text
INTEGER -> int
OPTIONAL_INTEGER -> int | None
FLOAT   -> float
OPTIONAL_FLOAT -> float | None
STRING  -> str
OPTIONAL_STRING -> str | None
BOOLEAN -> bool
STRING_LIST -> tuple[str, ...]
STRING_SET -> frozenset[str]
```

Kolekcje z `allowed_values` używają multi-select; wolne listy tekstowe używają
wartości rozdzielonych przecinkami.

### 22.5. Validation loop

Candidate przechodzi przez `spec.validate_value`.

Błąd:

```text
show concise error
reprompt
```

Cancel nie jest wyjątkiem błędu.

---

## 23. Plik — `settings.py`

### 23.1. Rola

Jedyny owner nawigacji Settings.

### 23.2. Categories

Jawna kolejność:

```text
translation
tts
output
connections
back
```

### 23.3. Field lists

Trzyma tylko product field IDs i user-facing labels/order.

Nie kopiuje walidacji.

### 23.4. Spec lookup

Każdorazowo:

```text
fresh settings snapshot
→ service.settings_catalog(snapshot)
→ find required spec
→ active?
```

Jeżeli wymagany product field nie istnieje:

```text
developer/config error
```

Nie tworzyć synthetic spec.

### 23.5. Fresh state

Po każdym successful save menu jest przebudowane z fresh state.

Nie cache’ować starego `SettingCatalogContext`.

---

## 24. Plik — `prompts.py`

Rozszerzyć wyłącznie znormalizowane klawisze potrzebne PLANOWI 02:

```text
up/down/enter/escape
space
backspace
printable text
```

Nie tworzyć drugiej aplikacji Prompt Toolkit, osobnego renderera ani pętli promptów.

Jedna wspólna style palette.

Questionary nie jest już używane. `prompt-toolkit` pozostaje bezpośrednią zależnością
core CLI, zamiast przypadkowej zależności tranzytywnej.

---

## 25. AppService technical gate

### 25.1. Najpierw audit

Przed edycją `service.py` wypisać wszystkie istniejące metody związane z:

```text
settings snapshot
settings mutation
secret mutation
model catalog
model probe
presets
```

### 25.2. Potrzebne capability — persisted setting

Jeżeli nie istnieje atomowa operacja pojedynczego settingu, dodać jedną metodę o
semantyce:

```text
clone current UserSettings
→ locate active persisted SettingSpec
→ validate candidate
→ assign through field_access
→ validate resulting UserSettings
→ persist
→ only after persist swap _user_settings
→ return detached fresh snapshot
```

### 25.3. Persistence failure

Jeżeli saver rzuci:

```text
_disk may be unchanged/failed
_in-memory MUST remain old
```

### 25.4. Secret update

Jeżeli current method już istnieje, użyć.

Jeżeli trzeba ją uzupełnić:

```text
validate secret ID against SECRET specs
→ atomic env update
→ rebuild Settings
→ swap only after success
```

### 25.5. Secret remove

Nie implementować ręcznego parsera `.env`.

Użyć istniejącego env mechanism lub minimalnie rozszerzyć go w config layer dopiero po
technical gate.

### 25.6. Model selection

Jeżeli current backend nie ma role-aware selection, minimalna nowa operacja musi być w
application/config layer.

Nie w Interactive.

---

## 26. Testy `settings_editors.py`

Wymagane co najmniej:

### E02-01 — current select

Picker startuje na current allowed value.

### E02-02 — cancel

Cancel nie zwraca candidate do persistencji.

### E02-03 — valid float

Tekst `1.25` daje typed float.

### E02-04 — invalid float

Tekst nienumeryczny nie wychodzi z editora.

### E02-05 — below minimum

Odrzucone + reprompt.

### E02-06 — above maximum

Odrzucone + reprompt.

### E02-07 — allowed values

Select nie może zwrócić wartości spoza source options.

### E02-08 — password abstraction

Fake prompt potwierdza, że value nie jest przekazywane do normalnego Rich renderera.

Nie testować internals Prompt Toolkit.

---

## 27. Testy Settings navigation

Wymagane:

### S02-01

Home dispatch `Ustawienia` otwiera Settings root.

### S02-02

Category order jest dokładna.

### S02-03

Wróć wraca Home.

### S02-04

Translation non-LLM ukrywa model.

### S02-05

Translation LLM pokazuje model.

### S02-06

Model picker używa dokładnych ID z `AppService.translation_model_options()` i grupuje
je według skonfigurowanego providera/protokołu.

### S02-07

Valid models pozostają przy entry-level catalog issue.

### S02-08

File-level catalog error jest safe.

### S02-09

Model picker nie wywołuje probe.

### S02-10

Prompt list pochodzi z backend contractu.

### S02-11

Style list pochodzi z backend contractu.

### S02-12

TTS engine switch odświeża voice choices.

### S02-13

Tempo zapisuje postprocess tempo.

### S02-14

Narrator gain zapisuje global gain.

### S02-15

Original gain zapisuje global gain.

### S02-16

Output preselectuje current default preset products.

### S02-17

Empty output nie zapisuje.

### S02-18

Output save jest jedną transakcją.

### S02-19

Connection status nie zawiera sekretu.

### S02-20

Blank password = no change.

### S02-21

Remove wymaga confirm.

### S02-22

System-env override jest pokazany bez value.

### S02-23

Probe powstaje tylko po explicit action.

### S02-24

Po restarcie persisted values wracają.

---

## 28. Testy AppService — tylko jeśli service.py się zmieni

### A02-01

Successful single-setting update persistuje i swapuje current state.

### A02-02

Validation error nie woła saver.

### A02-03

Saver failure nie swapuje state.

### A02-04

Inactive dependent spec nie jest zapisywany.

### A02-05

Secret write reloaduje Settings.

### A02-06

Secret write failure zachowuje poprzedni Settings.

### A02-07

Secret removal nie może usunąć system environment.

### A02-08

Unknown model alias jest odrzucony.

### A02-09

Model listing nie robi network.

### A02-10

Probe result nie jest persisted.

---

## 29. Data flow — persisted field

```text
Settings menu
→ product field ID
→ AppService settings snapshot
→ active SettingSpec
→ settings editor
→ candidate
→ SettingSpec validation
→ AppService atomic mutation
→ field_access assignment
→ settings.json atomic persistence
→ new in-memory settings
→ refresh menu
```

---

## 30. Data flow — translation model

```text
Tłumaczenie
→ Model tłumaczenia
→ AppService loads local ModelCatalog
→ valid ModelEntry list
→ local model select(label)
→ alias
→ AppService resolves alias to runtime contract
→ persisted selection
→ refresh
```

Network:

```text
NONE
```

---

## 31. Data flow — TTS voice

```text
Lektor
→ current settings
→ current SettingCatalogContext
→ active tts_voice_id spec
→ allowed values
→ select
→ validate
→ assign through field_access
→ persist
→ rebuild context
```

---

## 32. Data flow — Output

```text
Wynik
→ default preset
→ four product checkbox
→ non-empty validation
→ ProductIntent
→ AutoPresetDraft / preserved preset fields
→ AppService.save_preset
→ return
```

---

## 33. Data flow — Secret

```text
Połączenia
→ provider
→ Ustaw / zmień
→ password prompt
→ non-empty candidate
→ AppService secret operation
→ atomic .env update
→ Settings reload
→ environment status refresh
```

---

## 34. Data flow — Probe

```text
Połączenia
→ Palantir
→ Testuj
→ optional confirm
→ one AppService probe
→ session-only result
→ safe Rich message
```

Nie persistuje availability.

---

## 35. Kolejność implementacji

Agent wykonuje tę kolejność dokładnie.

### Krok 1 — baseline refresh

Potwierdź finalny PLAN 01 SHA i rzeczywiste kontrakty.

### Krok 2 — branch

```bash
git switch -c work/interactive-cli/02-settings
```

Nie commitować.

### Krok 3 — AppService audit

Przeczytaj publiczne config capabilities.

Wynik audytu ma rozstrzygnąć, czy `service.py` w ogóle wymaga edycji.

### Krok 4 — prompt primitives

Rozszerz `interactive/prompts.py` tylko o brakujące operacje.

Uruchom targeted tests adaptera.

### Krok 5 — typed editors

Utwórz:

```text
settings_editors.py
```

Najpierw scalar select + numeric.

### Krok 6 — Settings shell

Utwórz:

```text
settings.py
```

Podłącz pięć root entries.

### Krok 7 — Tłumaczenie

W kolejności:

```text
Silnik
Model
Prompt
Styl
```

Po każdej podsekcji targeted tests.

### Krok 8 — Lektor

W kolejności:

```text
Silnik
Głos
Tempo
Głośność lektora
Głośność oryginału
```

### Krok 9 — Wynik

Podłącz jedną product transaction default preset.

### Krok 10 — Połączenia

Najpierw status.

Następnie set/remove.

Probe tylko jeśli current application contract rzeczywiście go ma.

### Krok 11 — error paths

Sprawdź:

- validation failure;
- saver failure;
- malformed catalog;
- blank secret;
- cancel;
- environment override.

### Krok 12 — targeted tests

Uruchom nowe testy Settings i wszystkie zmienione regression tests.

### Krok 13 — static gates

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
```

### Krok 14 — diff review

```bash
git status --short
git diff --stat
git diff --check
git diff --name-only
```

### Krok 15 — READY_FOR_HITL

Nie commitować.

### Krok 16 — HITL

Czekać na użytkownika.

### Krok 17 — PASS

Po PASS:

```bash
uv run pytest
git diff --check
```

Następnie jeden commit i push.

---

## 36. Budżet zmiany

### 36.1. Produkcja

Orientacyjnie:

```text
settings.py              250–500
settings_editors.py      120–260
prompts.py delta          30–100
app.py delta              20–60
service.py delta           0–180
```

### 36.2. Testy

```text
settings tests           300–600
editor tests             120–250
service delta              0–250
```

### 36.3. Alarm

Jeżeli implementacja potrzebuje:

```text
> 1100 nowych linii produkcyjnych
> 1200 nowych linii testów
> 10 nowych modułów
```

zatrzymać się i wyjaśnić.

Nie jest to automatyczny FAIL, ale sygnał, że cienki Interactive CLI zaczyna zmieniać
się w kolejne TUI.

---

## 37. Targeted verification

Minimalnie:

```bash
uv run pytest tests/cli/test_interactive_settings.py
uv run pytest tests/cli/test_interactive_settings_editors.py
uv run pytest tests/cli/test_interactive_app.py
```

Jeżeli zmieniono `AppService`:

```bash
uv run pytest tests/application/test_service.py
```

Następnie:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
```

Pełny pytest po manualnym PASS.

---

## 38. Kontrola diffu

Expected final diff powinien mieścić się głównie w:

```text
anishift/cli/interactive/settings.py
anishift/cli/interactive/settings_editors.py
anishift/cli/interactive/prompts.py
anishift/cli/interactive/app.py
anishift/cli/AGENTS.md
tests/cli/test_interactive_settings.py
tests/cli/test_interactive_settings_editors.py
tests/cli/test_interactive_app.py
```

Warunkowo:

```text
anishift/application/service.py
tests/application/test_service.py
```

Każdy dodatkowy production file wypisać jako:

```text
UNEXPECTED FILE
```

Zmiana `services`, schedulera, handlerów albo schema modeli bez technical gate = STOP.

---

## 39. HITL — przygotowanie

Agent przed testem wypisuje dokładną sekcję:

```text
CO MASZ TERAZ SPRAWDZIĆ W USTAWIENIACH
```

Użytkownik uruchamia:

```bash
uv run anishift
```

w Windows Terminal.

---

## 40. HITL-01 — root i nawigacja

1. wybierz `Ustawienia`;
2. przejdź wszystkie kategorie;
3. użyj `Wróć`;
4. wróć Home.

Oczekiwane:

- layout pozostaje minimalistyczny;
- marker jest po lewej;
- brak `[x]` po prawej;
- Home nie pokazuje ustawień;
- brak osobnego dashboardu.

---

## 41. HITL-02 — Tłumaczenie

Sprawdź kolejno:

```text
Silnik
Model
Prompt
Styl
```

Po każdej zmianie:

1. wróć poziom wyżej;
2. wejdź ponownie;
3. sprawdź persistence;
4. nie używaj globalnego Save.

Dla non-LLM:

- model znika;
- prompt/style zachowują kontrakt wynikający z backendu;
- UI nie pokazuje temperature/retry/batch.

---

## 42. HITL-03 — katalog modeli

1. otwórz model picker;
2. sprawdź czytelne labels;
3. anuluj;
4. upewnij się, że samo otwarcie nie czeka na sieć.

Jeżeli masz bezpieczny runtime JSONC z jednym błędnym entry:

- valid models pozostają;
- warning jest krótki;
- komentarze w pliku pozostają 1:1 po pracy AniShift.

---

## 43. HITL-04 — Lektor

Zmień:

```text
Silnik
Głos
Tempo
Głośność lektora
Głośność oryginału
```

Sprawdź:

- current values;
- invalid tempo nie zapisuje się;
- engine switch daje odpowiednie głosy;
- nie pojawiają się advanced provider fields.

---

## 44. HITL-05 — Wynik

1. otwórz `Wynik`;
2. zmień product set;
3. zatwierdź;
4. otwórz ponownie;
5. sprawdź preselection;
6. spróbuj odznaczyć wszystko.

Oczekiwane:

- markery po lewej;
- empty selection rejected;
- brak pytań o bitrate/MKV tracks;
- zapis jest jedną transakcją.

---

## 45. HITL-06 — Połączenia

Na bezpiecznym testowym providerze:

1. sprawdź `brak`;
2. `Ustaw / zmień`;
3. wpisz secret;
4. wróć;
5. status `skonfigurowane`;
6. ponownie wejdź;
7. value nie jest pokazane;
8. pusty password nie usuwa;
9. remove pyta o confirm.

Nie kopiować sekretu do raportu.

---

## 46. HITL-07 — Palantir probe

Jeżeli środowisko jest gotowe:

1. ustaw enrollment URL;
2. upewnij się, że token jest skonfigurowany;
3. wybierz jawnie `Testuj`;
4. wykonaj jeden minimalny test;
5. sprawdź safe wynik.

Oczekiwane:

- menu samo nie robi sieci;
- probe robi się tylko jawnie;
- availability nie trafia do JSONC/settings;
- error nie pokazuje tokenu/header/body.

---

## 47. HITL-08 — restart

1. zmień po jednej wartości Tłumaczenia, Lektora i Wyniku;
2. wyjdź;
3. uruchom `uv run anishift` ponownie;
4. wejdź do Settings.

Wszystkie wartości mają wrócić.

---

## 48. HITL-09 — regresja Auto

Po zmianie bezpiecznej konfiguracji:

1. wróć Home;
2. uruchom Auto;
3. użyj prawdziwego materiału.

Oczekiwane:

- Auto bierze nowe ustawienia;
- Rich progress z PLANU 01 działa;
- nie powstała druga ścieżka wykonania;
- błędy zachowują politykę PLANU 01.

---

## 49. Obowiązkowy raport agenta przed HITL

```text
STATUS: READY_FOR_HITL

Plan:
PLAN 02 — Settings

Branch:
work/interactive-cli/02-settings

Base:
cd020dc4e0fabed54ff3e3d24d73d84253e1cd74

Commit:
NONE — awaiting HITL

Settings navigation owner:
...

Setting editor owner:
...

Persisted setting path:
Interactive -> AppService -> ...

Preset path:
Interactive -> AppService -> ...

Secret path:
Interactive -> AppService -> ...

Model catalog:
READ ONLY

Changed production files:
- ...

Changed test files:
- ...

Automated gates:
- targeted settings: PASS/FAIL
- app regression: PASS/FAIL
- service tests if applicable: PASS/FAIL
- ruff: PASS/FAIL
- format: PASS/FAIL
- mypy: PASS/FAIL
- git diff --check: PASS/FAIL

Unexpected files:
NONE / pełna lista

CO MASZ TERAZ SPRAWDZIĆ W USTAWIENIACH:
[pełna praktyczna checklista dostosowana do rzeczywistego diffu]

CELOWO JESZCZE NIE DZIAŁA:
- Manual
- finalna maskotka
- animacja
- Chafa/Sixel
- pobieranie anime

Jeżeli coś nie działa, podaj HITL-XX i objaw.
```

Agent nie może odesłać użytkownika do samego pliku planu.

---

## 50. PASS / FAIL

### 50.1. PASS

Użytkownik odpowiada:

```text
PASS
```

Dopiero wtedy:

```bash
uv run pytest
git diff --check
```

Następnie jeden finalny commit:

```text
feat(cli): add interactive product settings
```

Push:

```text
work/interactive-cli/02-settings
```

Raport SHA.

### 50.2. FAIL

Użytkownik podaje:

```text
HITL-XX
objaw
```

Agent:

- pozostaje na tym branchu;
- nie tworzy finalnego commita;
- lokalizuje problem;
- poprawia minimalnie;
- uruchamia targeted tests;
- ponownie daje `READY_FOR_HITL`.

---

## 51. Zakazane skróty implementacyjne

Nie wolno:

- wyrenderować wszystkich `SettingSpec`;
- dodać `Advanced`;
- dodać globalnego Save;
- utrzymywać wielkiego settings draft;
- zapisywać `settings.json` z Interactive;
- zapisywać `presets.json` z Interactive;
- zapisywać `.env` z Interactive;
- przepisywać model JSONC;
- hard-code listy modeli;
- robić request przy otwarciu model picker;
- pokazywać fragment tokenu;
- dodać keyring;
- dodać DB;
- dodać settings repository layer;
- importować concrete services w Interactive;
- zmienić scheduler;
- zmienić retry/fallback semantics;
- dodać manager presetów;
- używać markerów po prawej;
- przywrócić Textual;
- utworzyć `anishift/tui`;
- ogłosić DONE przed HITL.

---

## 52. Ryzyka i reakcje

### RISK-02-A — katalog techniczny zacznie dyktować UI

Sygnał:

```text
Settings pokazuje dziesiątki pól
```

Reakcja:

```text
wróć do product allowlist
```

Nie dodawaj filtrów po fakcie.

### RISK-02-B — frontend zaczyna mapować modele/providery

Sygnał:

```text
interactive/settings.py importuje protocol/provider config
```

Reakcja:

```text
przenieś decyzję do AppService/config boundary
```

### RISK-02-C — zapis pół-konfiguracji

Sygnał:

```text
plik zapisany, in-memory state nie
albo odwrotnie
```

Reakcja:

```text
transaction ordering: validate -> persist -> swap
```

### RISK-02-D — secret leaks

Sygnał:

```text
wartość w Rich output/log/test assertion
```

Reakcja:

```text
stop
redact
add regression test
```

### RISK-02-E — Settings rośnie w framework

Sygnał:

```text
router/store/forms/widgets abstractions
```

Reakcja:

```text
cofnij do dwóch małych modułów
```

---

## 53. Coverage

| Requirement area | Właściciel techniczny | Główny dowód |
|---|---|---|
| R-800 root | settings.py | HITL-01 |
| R-801..R-806 zapis | AppService + editors | tests + restart |
| R-820 translation | settings.py | HITL-02/03 |
| R-840 TTS | settings.py | HITL-04 |
| R-860 output | preset contract | HITL-05 |
| R-880 connections | AppService env contract | HITL-06/07 |
| R-900 persistence | config owners | HITL-08 |
| R-920 model catalog | ModelCatalog | HITL-03 |
| left markers | prompts.py | HITL-01/05 |
| Home purity | app/home | HITL-01 |
| Auto regression | run/progress unchanged | HITL-09 |

---

## 54. Definition of Done

PLAN 02 jest ukończony tylko gdy:

```text
[ ] PLAN 01 ma VERIFIED / COMMITTED.
[ ] Baseline jest dokładnym finalnym SHA.
[ ] Powstał work/interactive-cli/02-settings.
[ ] Ustawienia są dostępne z Home.
[ ] Root ma Ogólne / Tłumaczenie / Lektor / Wynik / Połączenia / reset / Wróć.
[ ] Home nadal ma tylko cztery akcje.
[ ] Nie ma globalnego Save.
[ ] Tłumaczenie ma sekcje podstawowe / wydajność / model LLM / prompt.
[ ] Model jest warunkowy dla LLM.
[ ] Model picker grupuje dokładne ID dla skonfigurowanych providerów.
[ ] Przykładowe Palantir `replace-with-*` nie są opcjami.
[ ] Model picker nie robi sieci.
[ ] Prompt nie jest hard-coded.
[ ] Styl nie jest hard-coded.
[ ] Lektor pokazuje aktywne pola engine / profilu / wydajności / dźwięku.
[ ] Provider-native tuning jest warunkowy i pochodzi z SettingSpec.
[ ] Wynik ma cztery publiczne produkty.
[ ] Enter i Space przełączają produkt, a zapis ma osobny wiersz.
[ ] Reset preferencji nie usuwa sekretów ani presetów.
[ ] Markery multi-select są po lewej.
[ ] Empty product set jest odrzucony.
[ ] Output aktualizuje default preset atomowo.
[ ] Połączenia nie pokazują secret values.
[ ] Blank password niczego nie usuwa.
[ ] Remove wymaga confirm.
[ ] Secret write korzysta z existing env mechanism przez AppService.
[ ] AppService reloaduje Settings po secret change.
[ ] Palantir enrollment URL jest regular preference.
[ ] Model catalog pozostaje read-only.
[ ] Probe jest jawny i session-only.
[ ] Nie dodano Textual.
[ ] Nie utworzono anishift/tui.
[ ] Auto PLANU 01 nie ma regresji.
[ ] Targeted tests przechodzą.
[ ] Ruff przechodzi.
[ ] Format check przechodzi.
[ ] Mypy przechodzi.
[ ] Diff check przechodzi.
[ ] Agent wypisał pełne CO MASZ TERAZ SPRAWDZIĆ.
[ ] Użytkownik podał PASS.
[ ] Pełny pytest przeszedł po PASS.
[ ] Powstał jeden finalny commit.
[ ] Branch został wypchnięty.
```

Dopiero wtedy:

```text
PLAN 02 VERIFIED / COMMITTED
READY FOR PLAN 03 — MANUAL
```
