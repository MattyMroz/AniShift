---
kind: current-state
status: verified-by-reading
baseline: main @ 4365a51
created: 2026-10-25
---

# Stan dziś: kontrola zawartości po pobraniu (E4)

Fakty z odczytu kodu na `main` @ `4365a51` oraz z `ffprobe` uruchomionego tylko do odczytu na 52 plikach MKV z `workspace/ready/` (rekurencyjnie, razem z `Nowy folder/`). Rezydenta nie uruchamiano. `config/watch/state.json` czytano wyłącznie do zliczeń, bez nazw i ścieżek.

## 1. Co AniShift sprawdza po pobraniu

| Fakt | Źródło |
|---|---|
| Kontrola pobrania (H2) działa tylko dla próby subskrypcji: `_check_basis` zwraca `None` dla przyjęcia ręcznego, więc ręczne pobranie trafia do nazwania bez kontroli. | `anishift/application/automation.py:6650-6680` (warunek `:6658-6664`) |
| Kontrola biegnie przed nazwaniem plików, na wideo w stagingu, gdy cały zestaw odcinka jest kompletny. | `automation.py:6579-6597` (`_publish_episode`), `:6682-6697` (`_passed_check`) |
| Wideo identyfikuje `MediaProbe.identify` (MKV: `mkvmerge -J`, MP4: `ffprobe`), limit 30 s, jedna ponowiona próba; brak binarki, nieobsługiwany kontener albo druga awaria dają `skipped` i plik przechodzi dalej. | `automation.py:514`, `:6736-6761` |
| `verify()` porównuje czas trwania z ani.zip i obecność obrazu. Rezydent woła ją w trybie `record_only`: każde odrzucenie poza `no_video_stream` zamienia się w `inconclusive`. Log `Download checked` pochodzi z tego miejsca. | `anishift/application/download_verification.py:134-139`, `automation.py:6723-6724` |
| `MeasuredMedia` liczy tylko ścieżki wideo i audio; napisów nie bada. Docstring `Verification` mówi wprost, że wynik nie dotyczy przydatności napisów. | `download_verification.py:75-100`, `:124-131` |
| Odrzucenie zapisuje `EpisodeAssignment.verification = "reject:<powód>"`; przypisanie `rejected` nie jest nazywane ani publikowane. | `automation.py:6787-6798`, `anishift/application/control.py:89-93`, `:507-510` |
| Inwariant: tylko próba subskrypcji może nieść wynik kontroli (`verification`); przyjęcie ręczne z `verification` to `ValueError`. | `control.py:512-533` (`:520-522`) |
| Powód odrzucenia trafia do szczegółów odcinka jako `TargetNotice` i do `decisions.jsonl` (`kind: "check"`, `source: "h2"`). Polskie słowa dla powodów: `brak obrazu`, `za krótki plik`, `za długi plik`. | `automation.py:4647-4663`, `:6763-6785`, `anishift/application/episode_commands.py:40-47` |
| `traits` w `state.json` (`polish`, `resolution`, `unusable`) to fakty z **nazwy** wydania zapisane przy przyjęciu, nie zawartość pliku. `unusable` zna tylko `dub_only`, `hardsub`, `raw`. | `control.py:357-381`, `anishift/application/watch_state.py:188`, `:879-886` |
| Stan właściciela (zliczenia): 90 przypisań (44 ręczne, 46 subskrypcji); `verification` ma 41 prób subskrypcji (`no_contradiction`), 0 przypisań ręcznych; `traits.polish`: 35 `polish`, 30 `none`, 25 bez `traits`. | odczyt `config/watch/state.json`, schemat 5 |

## 2. Wybór ścieżki napisów i audio

| Fakt | Źródło |
|---|---|
| Auto wybiera napisy osadzone w `planner._select_embedded_track`: kandydaci to tylko ścieżki `ass`/`srt` (obrazkowe PGS/VobSub odpadają). | `anishift/application/planner.py:1173-1220` (`:1184-1188`) |
| Klucz rangi napisów: najpierw „nie-dialog” na koniec, potem język z `subtitle_language_priority`, pozycja na liście, flaga domyślna, niższe ID. | `planner.py:1984-1999` |
| „Nie-dialog” = flaga `forced` **albo** nazwa ścieżki pasująca do `sign|song|forced`. Liczby zdarzeń planner nie zna. | `planner.py:96`, `:1978-1981` |
| Gdy wszystkie ścieżki tekstowe są „nie-dialog”, plan zostaje wykonalny z nieblokującym ostrzeżeniem `subtitle_dialogue_missing` („narracja idzie za nimi”). | `planner.py:1206-1211`, test `tests/application/test_planner.py:551-567` |
| Brak jakiejkolwiek ścieżki tekstowej daje blokujący problem `subtitle_source_missing`, w panelu „Brak napisów”. | `planner.py:1166-1168`, `anishift/cli/interactive/state_processing.py:49` |
| Domyślne priorytety: napisy `("pol", "eng")`, audio `("jpn", "eng", "zho")`. Audio wybiera ten sam klucz rangi bez degradacji „nie-dialog”. | `anishift/services/extraction/tracks.py:24-28`, `anishift/config/user_settings.py:132-136`, `planner.py:1195-1203` |
| `MediaTrack` (neutralny katalog) nie ma liczby zdarzeń. Adapter MKV czyta `num_index_entries` do `TrackInfo.num_entries`, ale `_map_track` tego nie przenosi. MP4 (`ffprobe`) też nie przenosi `nb_frames`. | `anishift/services/media/types.py:26-49`, `anishift/services/extraction/service.py:128-141`, `anishift/services/media/mkv.py:59-79`, `anishift/services/media/mp4.py:65-89` |
| `services/extraction/tracks.py` to legacy scoring z drugą kopią wzorca `sign|song|forced`; planner go nie używa. | `tracks.py:59`, `:88-90`, `anishift/services/extraction/AGENTS.md` (Pułapki) |

## 3. Co robi `translation_action: auto`

| Fakt | Źródło |
|---|---|
| `AUTO` tłumaczy, gdy język źródła napisów jest różny od `pol` (także nieznany); inaczej robi `NORMALIZE_SUBTITLES` (`polish-bypass`). `TRANSLATE` tłumaczy zawsze, `DO_NOT_TRANSLATE` przy obcym źródle daje problem `false_polish_product`. | `planner.py:1350-1391`, `anishift/application/intents.py:97-102` |
| Język źródła pochodzi z tagu ścieżki (`pl`, `pol`, `pl-pl` → `pol`), chyba że preset deklaruje `source_subtitle_language`. Tytuł ścieżki nie wpływa na język. | `planner.py:1931-1939` |
| Lektor (TTS) powstaje z `.pl` także przy ominięciu tłumaczenia — w `ready/` pliki z polską ścieżką mają `.eac3` lektora (np. Erai Ao no Hako 03). | `workspace/ready/` (listing), `planner.py:1383-1391` |
| Etykiety w Ustawieniach: „Automatycznie · tłumaczy, gdy źródło nie jest polskie”, „Zawsze tłumacz”, „Nie tłumacz”. | `anishift/cli/interactive/settings.py:323-325` |

Wniosek: dwie pierwsze gałęzie E4 (PL → bez tłumaczenia, obce → tłumaczenie) działają już w plannerze przy domyślnych ustawieniach, pod warunkiem że rozpoznanie „nie-dialog” jest trafne.

## 4. Zamiana wydania

| Fakt | Źródło |
|---|---|
| Subskrypcja: odrzucona próba zamyka się z faktem `rejected`, cel wraca do `DUE` (albo `AWAITING_AIRING`), następna próba pomija wypróbowane hashe (`excluded`). Budżet: `MAX_ATTEMPTS = 3` prób na cel, wspólny dla wszystkich powodów; po wyczerpaniu `EXHAUSTED` i powiadomienie. | `anishift/application/subscription_targets.py:67`, `:402-454`, `:609-611`; `automation.py:4447-4489`, `:8532-8545` |
| Własny transfer zamkniętej próby jest anulowany albo próba wycofana ze wspólnego transferu. | `automation.py:8591-8605` (`_closed_attempt`) |
| Reguła zamiany R-07 istnieje jako czysta funkcja `subscription_choice.replacement`: pierwszy `admissible` według `choice_key`, bez czekania na PL i progu, z wykluczeniem całych hashy; `None` = ręczny wybór. **Nikt jej nie woła.** Docstring opisuje podpięcie: `search_episode` → `replacement` → `_admit_episode(previous=…)`. | `anishift/application/subscription_choice.py:297-307`, plan A1 `docs/work/08-acquisition/plans/12-a1-acquisition-algorithm.md` §5.12 |
| Ścieżka ręczna (D z listy odcinków): `_download_episode` w puli I/O czyta listę i `search_episode`, potem na wątku ownera `_admit_download_offer` → `_admit_episode`. `previous` wskazuje ostatnie przyjęcie klucza; `_replace_episode_scope` oznacza stare jako `replaced`. | `automation.py:5663-5724`, `:5726-5800`, `:8495-8502` |
| `reacquire` (Historia) to powtórzenie tego samego wydania starej drogi Nyaa, nie zamiana na inne. | `automation.py:7979-8043` |
| `usable` odrzuca już z nazwy: paczki, niejednoznaczne, sam dubbing, `raw`, `hardsub`, nieobsługiwany kontener. Wydanie bez napisów rozpoznawalne z nazwy (`raw`) nie jest pobierane. | `subscription_choice.py:164-175` |

## 5. Dane: ścieżki w `workspace/ready/*.mkv`

Komenda: `external\bin\ffmpeg\ffprobe.exe -v error -show_streams -show_format -of json <plik>` dla każdego z 52 MKV. Liczba zdarzeń to tag statystyk `NUMBER_OF_FRAMES` zapisany przez mkvmerge; był obecny dla wszystkich 790 ścieżek napisów. Tempo = zdarzenia / czas kontenera w minutach.

### 5.1 Układy

| Układ (grupa) | Pliki | Ścieżek napisów | Kodeki | Pełny PL | Pełny EN | Tytuły ścieżek pełnych | Ścieżki szyldów (EN/PL) | `forced` na pełnej |
|---|---|---|---|---|---|---|---|---|
| Erai-raws CR/NF/AMZN z PL | 25 | 10–37 | ass | 1 | 1–2 | `CR_English`/`CR_Polish`, `NF_*`, `AMZN`, `CR` | brak | nie |
| Erai-raws CR bez PL | 3 | 9–13 | ass | 0 | 1 | `CR_English` | brak | nie |
| Erai-raws po zmianie nazwy (bez grupy) | 1 | 10 | ass | 1 | 1 | `CR_English`, `CR_Polish` | brak | nie |
| Onalrie (rip CR, AV1) | 1 | 10 | ass | 1 | 1 | `CR_English`, `CR_Polish` | brak | nie |
| Judas | 2 | 36–39 | subrip | 1 | 2–3 | `English`, `English [CC]`, `Polish` | EN `English`, 9 i 19 zdarzeń, `forced=1` | nie |
| SubsPlease | 6 | 1 | ass | 0 | 1 | `English subs`, `English` | brak | **tak**: jedyna ścieżka, 251 zdarzeń, `forced=1` (Dark Summoner 03) |
| ToonsHub CR/ADN z PL | 2 | 8–11 | ass, subrip | 1 | 1–2 | bez tytułu, `iQ` | brak | nie |
| ToonsHub CR bez PL | 2 | 13–15 | ass | 0 | 1 | bez tytułu | brak | nie |
| ToonsHub CR DUAL bez PL | 1 | 17 | ass, subrip | 0 | 2 | bez tytułu, `CC` | EN `Forced`, 36 zdarzeń | nie |
| ToonsHub NF MULTi | 2 | 60–61 | subrip | 1–2 | 3 | bez tytułu, `SDH`, `Dubtitle` | EN `Forced` 12–16; PL `Forced` 10 (Sparks 11) | nie |
| VARYG z PL | 3 | 7–14 | ass, subrip | 1 | 1–2 | bez tytułu, `HIDI`, `BILI` | brak | nie |
| VARYG bez PL | 3 | 9–15 | ass | 0 | 1 | bez tytułu | brak | nie |
| lycoris.cafe | 1 | 2 | ass | 1 (domyślna) | 1 | `CR`, bez tytułu | brak | nie |
| **Razem** | **52** | 1–61 | | **37 plików** | 52 plików | | 32 ścieżki | 1 |

Nie wystąpiły: plik bez napisów, plik z samymi szyldami, napisy obrazkowe, ścieżka bez tagu języka, tytuły `Signs`/`Songs`/`Signs & Songs`. Trzy pliki Erai mają w nazwie `[MultiSub]`, ale nie mają polskiej ścieżki (Tantei S2 02 i 03, Tensei Kizoku S3 04) — deklaracja z nazwy nie dowodzi PL (U-07).

### 5.2 Sygnały rozpoznania szyldów (790 ścieżek)

| Sygnał | Wynik na danych | Wniosek |
|---|---|---|
| Tempo zdarzeń | Pełne ścieżki: 758, tempo 7,98–41,18/min (najniższa: tajski AMZN, 188 zdarzeń w 23,6 min). Szyldy: 32, tempo 0,19–1,52/min, najwyżej 36 zdarzeń. Rozdzielenie pełne, przerwa 1,52 → 7,98. | Najmocniejszy sygnał; jedyny bez pomyłki na próbce. |
| Flaga `forced` | 33 ścieżki z flagą: 32 szyldy + 1 pełna (SubsPlease Dark Summoner 03). Wszystkie 32 szyldy mają flagę. | Pełny recall, ale jedna pomyłka odrzuciłaby dobre wydanie. Sama flaga nie wystarcza. |
| Tytuł `sign\|song\|forced` | 30 trafień, wszystkie to szyldy; 2 szyldy bez słowa kluczowego (Judas: tytuł `English`). Żadna pełna ścieżka nie pasuje. | Wysoka precyzja, niepełny recall. |
| Styl ASS | Nie mierzono: `ffprobe -show_streams` nie pokazuje użycia stylów, a odczyt wymaga ekstrakcji ścieżki. | Niepotrzebny przy obecnym rozdzieleniu tempem. |

### 5.3 Jak planner potraktowałby te pliki dziś

- Dark Summoner 03: jedyna ścieżka ma `forced=1`, więc planner uznaje ją za „nie-dialog” i wydaje fałszywe ostrzeżenie `subtitle_dialogue_missing`; wynik powstał, bo nie było innej ścieżki.
- Judas: ścieżka `forced=1` z tytułem `English` jest degradowana flagą — poprawnie.
- Sparks 11: PL `Forced` (10 zdarzeń) degradowana; wybrana PL bez tytułu (ID 55) przed PL `Dubtitle` (ID 57), bo niższe ID.

## 6. Luki względem E4

1. Plik bez napisów kończy jako blokujący Problem „Brak napisów” w Przetwarzaniu; nikt nie bierze innego wydania (ryzyko przyjęte w `docs/work/08-acquisition/masterplan.md:179`).
2. Plik z samymi szyldami przechodzi z ostrzeżeniem i lektor czyta szyldy zamiast dialogów.
3. Rozpoznanie szyldów używa flagi `forced` jako dowodu rozstrzygającego; na próbce daje to jedną pomyłkę (Dark Summoner).
4. Kontrola po pobraniu nie istnieje dla pobrań ręcznych, a `replacement()` nie ma wyzwalacza.
5. Liczba zdarzeń jest czytana przez adapter MKV, ale nie trafia do neutralnego katalogu.

## 7. Czego nie zweryfikowano

- Czy pole widoczne dla aplikacji (`num_index_entries` z `mkvmerge -J` albo tag statystyk w tym samym JSON) jest równe `NUMBER_OF_FRAMES` z `ffprobe`. Zakaz zlecenia dopuszczał tylko `ffprobe`; sprawdzenie jest bramką F0 planu.
- Zachowanie plików zmuksowanych innym narzędziem niż mkvmerge (brak tagów statystyk, brak cue dla napisów).
- Wydania fansubowe z osobną ścieżką `Signs & Songs` — nie ma ich w próbce.
