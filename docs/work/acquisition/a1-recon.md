# A1 K0 — rekonesans źródeł i zestaw wzorcowy

Raport kroku K0 planu `plans/a1-algorytm-pozyskiwania.md` (§9, §10.2). Bez kodu produkcyjnego.
Oczekiwania w `expectations.json` potwierdził właściciel 2026-10-06 (`confirmed_by_owner: true`
we wszystkich przypadkach). Wersja po review K0 („DO POPRAWY”) i decyzjach właściciela oraz
orkiestratora.

## 1. Artefakty

Fixtury w `tests/fixtures/acquisition/reference/` (stan źródeł z 2026-10-06, pole `captured_at`;
odpowiedzi mostów numeracji §3.5 dograne 2026-10-07, `notes.appended`, §2):

| Plik | Rozmiar [B] | Plik | Rozmiar [B] |
|---|---:|---|---:|
| `101972-1.json` | 270 519 | `189123-1.json` | 1 083 014 |
| `130003-1.json` | 363 897 | `194884-1.json` | 198 889 |
| `130003-12.json` | 276 507 | `195516-1.json` | 733 350 |
| `140960-1.json` | 1 100 764 | `204389-1.json` | 282 009 |
| `140960-12.json` | 1 174 461 | `204389-2.json` | 273 163 |
| `152677-1.json` | 109 625 | `210031-1.json` | 1 333 188 |
| `154587-1.json` | 1 185 940 | `210031-13.json` | 503 720 |
| `154587-28.json` | 1 028 230 | `213805-1.json` | 1 302 386 |
| `159042-1.json` | 532 175 | `21519-1.json` | 1 606 064 |
| `172192-1.json` | 66 528 | `coverage-baseline.json` | 2 598 685 |
| `185756-1.json` | 377 098 | `expectations.json` | 105 154 |
| `185756-2.json` | 762 181 | `recording-log.json` | 43 |
| | | `probes/n2.json` | 55 394 |

Razem 17,3 MB; największy plik 2,6 MB (`coverage-baseline.json`), największa fixtura 1,6 MB.
Suma przekracza 10 MB z planu; **decyzja właściciela: fixtury zostają w całości**. Rozmiary
dotyczą surowego JSON; w repozytorium każdy plik leży jako `.json.gz` (gzip, `mtime=0`, największy
338 KB), bo hook `check-added-large-files` odrzuca pliki powyżej 500 KB.

Skrypty jednorazowe w `scripts/tmp/`: `a1_record_reference.py` (nagrywanie), `a1_rank.py`
(przybliżenie spec A §3.3–§6.3), `a1_expectations.py` (odtworzenie offline per tryb i propozycja),
`a1_coverage.py` (pokrycie i ponowne zapytania), `a1_probe_n2.py` (N-2), `a1_n6_settings.py` (N-6),
`a1_probe_shapes.py`, `a1_probe_titles.py`, `a1_probe_dual.py` (reszta nazwy po DUAL), `a1_strip_ws.py`
(webseedy), `a1_renote.py` (notatki uzupełniania z replay) oraz pomocnicze `a1_check.py`, `a1_diff.py`, `a1_inspect.py`,
`a1_losses.py`, `a1_reasons.py`, `a1_table.py`, `a1_table_md.py`, `a1_visits.py`,
`a1_fill_report.py`.

Format fixtury:

```text
{case, kinds, anilist{id,format,country}, number, pre_airing, captured_at, notes,
 modes{manual:[i], subscription:[i]}, evidence:[i],
 responses[{method,url,request_body?,status,body} | {method,url,error}]}
```

- `responses` — każde zapytanie raz (klucz metoda + URL + treść POST); powtórzenia obsłużono z pamięci.
- `modes.manual` / `modes.subscription` — indeksy odpowiedzi dozwolonych w danym trybie (część
  wspólna AniList/ani.zip + zapytania trybu). Replay trybu odrzuca każde zapytanie spoza swojego zbioru.
- `evidence` — zapytania AniList wykonane tylko przez `season_context` (dowód do N-5), poza trybami.
- `notes.modes[tryb]` — frazy, liczba zapytań per host, podsumowanie źródeł i przebieg uzupełniania.

## 2. Nagranie

- 21 przypadków nagranych, 0 nieudanych, 0 odpowiedzi 429 (`recording-log.json`).
- 15 przypadków badawczych; subskrypcje: 159042-1, 189123-1, 185756-2, 195516-1, 204389-2
  (wspólne z badawczymi), 213805-1 (nowy), 152677-1 i 172192-1 (przed emisją, `pre_airing: true`);
  dodatkowo film 21519-1, OVA/SPECIAL 194884-1 i donghua 101972-1.
- Każdy przypadek nagrano jako dwa osobne wyszukiwania: **ręczne** (frazy subskrypcji + frazy
  z numerem absolutnym, kolejka §6.1) i **subskrypcja** (tylko frazy subskrypcji, lista poprzedniego
  odcinka TsukiHime, kolejka §6.2). Każdy tryb ma własny budżet 10 odczytów uzupełniania.
- Odtworzenie offline per tryb (`httpx.BaseTransport` po kluczu metoda + URL + treść POST,
  ograniczone do `modes[tryb]`): 21 × 2 tryby, 0 brakujących odpowiedzi, wizyty uzupełniania
  identyczne z nagraniem.
- Nagłówki odpowiedzi nie są zapisywane. Replay musi sam podać `content-type` (XML dla Nyaa
  i nekoBT — adapter Nyaa odrzuca odpowiedź bez `xml`; JSON dla reszty).
- **Sanityzacja:** w treściach JSON z `api.tsukihime.org` pola `links` i `links_audio` zastąpiono
  pustymi listami przy zapisie; pozostałe pola bez zmian. W fixturach jest 0 linków mirrorów
  TsukiHime. W treściach z `nekobt.to` parametry `ws=` (webseedy) usunięto z magnetów (decyzja
  właściciela; `strip_webseeds` w nagrywaniu, `a1_strip_ws.py` dla istniejących fixtur): 729 usuniętych
  w 13 fixturach, 0 pozostałych; liczby `xt=`, `dn=`, `tr=` bez zmian.
- Dryf danych: ani.zip nie zwraca dziś `kitsu_id` dla 210031. Kitsu ID 50634 daje teraz krok 3
  §3.5 (Kitsu mappings z kontrolą zwrotną), więc 210031-1 i 210031-13 znów mają zapytanie Torrentio.
- **Dogranie mostów numeracji (spec A §3.5 D1, plan K9b):** `a1_record_reference.py --append`
  odtwarza każdy przypadek z jego `captured_at` i odpowiada z zapisanych odpowiedzi, a z sieci
  pobiera tylko brakujące, z tą samą sanityzacją i tymi samymi odstępami. Kolejność w fazie wspólnej:
  ani.zip po AniList → arm-server (`/api/v2/ids?source=anilist&id=`) → ani.zip po `anidb_id`, gdy
  `episodes` są puste → Kitsu mappings (`/mappings?filter[externalSite]=anilist/anime&filter[externalId]=…&include=item`,
  potem `/anime/{id}/mappings?page[limit]=20`), gdy brak `kitsu_id`. `page[limit]=20` dodano, bo
  domyślna strona Kitsu ma 10 wpisów. Wynik: 21/21 ok, 0 nieudanych, 0 × 429, dograne 40 odpowiedzi:
  arm 21, ani.zip po AniDB 1, Kitsu 4, Torrentio 2, btih TsukiHime 4 (204389-1/2, 210031-1/13 — inna
  kolejka uzupełnień przy nowym celu) oraz w 213805-1 frazy ręczne z numerem absolutnym `- 15`
  (Nyaa 4, Knaben 2, nekoBT 2).
  Indeksy dogranych odpowiedzi: `notes.appended.responses`. Starsze odpowiedzi zostają w fixturze,
  także te, których po zmianie celu nie używa już żaden tryb.
- **Przeliczenie po regule numeracji celu (plan v17, `numbering_gap`):** ponowne `--append` dla
  21 przypadków dograło 0 odpowiedzi (21/21 ok, 0 × 429); odświeżyło tylko `modes` i `notes.modes`
  pod nowy cel. `notes.appended.responses` łączy indeksy obu dograń (razem 40).
- **Dogranie K16 (2026-10-09):** spisy TsukiHime (`/torrents/btih/*`, `/torrents/{id}`) dla wizyt
  kolejki produkcyjnej i `Page` franczyzy 101972 z `countryOfOrigin` nagrano 2026-10-09
  (`notes.appended_k16`, log `k16_appended`), a odpowiedź `404` jest monotoniczna: hash nieznany
  TsukiHime 2026-10-09 nie był znany także w chwili `captured_at`. Ryzyko jest odwrotne dla `200`:
  spis po hashu nagrany 2026-10-09 mógł 2026-10-06 jeszcze nie istnieć (wtedy `404` albo `202`).

### Frazy (spec §3.1 po decyzjach)

| Rodzaj | Frazy subskrypcji | Dodatkowo w ręcznym |
|---|---|---|
| TV, sezon 1 | `{tytuł} - {NN}`, `{tytuł} S01E{NN}` | — |
| TV, sezon > 1 | `{tytuł} - {NN}`, `{tytuł} S{ss}E{NN}` | `{tytuł} - {absolutny}` |
| OVA/SPECIAL | `{pełny tytuł} - {NN}` | — |
| MOVIE | `{tytuł}` | — |
| ONA (donghua) | `{tytuł} - {NN}` | — |

`{tytuł}` = `base_title` romaji i angielskiego (bez duplikatów), dla OVA/SPECIAL pełny tytuł
z podtytułem; najwyżej 4 frazy. `{ss}` z grafu franczyzy (N-5). Przykład 194884-1:
`Kaguya-sama wa Kokurasetai: Otona e no Kaidan - 01`, `Kaguya-sama: Love Is War -Stairway to Adulthood- - 01`.

### Zapytania na tryb (zakres w zestawie)

| Host | Subskrypcja | Ręczne |
|---|---:|---:|
| Nyaa (fraza × 2 kategorie) | 4–8 | 4–12 |
| Knaben (≤2 strony × 300 na frazę) | 2–4 | 2–6 |
| nekoBT (≤2 strony × 100 na frazę) | 2–5 | 2–7 |
| TsukiHime (tytuł + lista + poprzedni odcinek + ≤10 uzupełnień) | 1–13 | 1–12 |
| Torrentio | 1 | 1 |
| ani.zip (AniList; AniDB przy pustych `episodes`) | 1–2 | 1–2 |
| arm-server | 1 | 1 |
| Kitsu mappings (tylko bez `kitsu_id`) | 0–2 | 0–2 |

Limity subskrypcji ze spec §3.1 (Nyaa ≤8, TsukiHime ≤14, numeracja i ID ≤5) są dotrzymane
w każdym przypadku; numeracja i ID to najwyżej 4 żądania (213805-1: 3, 210031: 4).

## 3. Niewiadome

### N-1 — `/torrents/btih/{btih}` TsukiHime

- Hash bez względu na wielkość liter.
- Brak: `404` z `{"detail": "...does not exist."}`.
- `200` przy stanie gotowym; treść to pełny opis torrenta z polem `id` **i z `files`**.
- `202` przy stanie niegotowym (`state: "error"`); treść ma `id`, `filecount` 28 i niepełne `files`
  (11–16 z 28) — 4 odpowiedzi w Frieren i Spy×Family. Zgodnie z decyzją `202` = `pending`;
  `files` z `202` nie są listą.
- Poprzednia runda: w 78 parach btih `200` + `/torrents/{id}` lista plików (nazwa, `sublangs`,
  `audiolangs`) była identyczna w 78/78; w 6 przypadkach lista nie została odczytana.
  Oszczędność w tamtym przebiegu: **90 uniknionych GET-ów listy i 6 wizyt** bez drugiego odczytu.

Reguła spisu (decyzja): btih `200` jest spisem tylko, gdy `len(files) == filecount`. W przeciwnym razie
(także bez `filecount`) drugi odczyt `/torrents/{id}`; jeśli i on ma mniej plików niż `filecount`, wynik
to `incomplete` — spis niekompletny, pliki TsukiHime nie są używane, wydanie oceniane jest jak bez
spisu (plik z Torrentio, jeśli jest, inaczej po nazwie). Recorder (`complete()`) i replay stosują tę
samą funkcję. Przypadki z zestawu:

- `3753beaf…` (154587-1 i 154587-28, subskrypcja): btih 34/44 → `/torrents/{id}` 34/44 → `incomplete`;
  werdykt `match` pochodzi z pliku Torrentio `[DB]Sousou no Frieren_-_28_…mkv`;
- `c66cb8d4…` (21519-1, subskrypcja): btih 3/58 → `/torrents/{id}` 3/58 → `incomplete`.

Poprzednio oba trafiały jako `listed` z listingu. Poprawka zmieniła tylko te 3 wizyty; notatki
`notes.modes[*].completion` przeliczono z replay (`a1_renote.py`), bez nowych zapytań.

| Miara | Ręczne | Subskrypcja |
|---|---:|---:|
| wizyty / odczyty | 179 / 190 | 180 / 186 |
| btih 200 / 202 / 404 | 82 / 2 / 12 | 70 / 2 / 19 |
| spis z btih (1 odczyt) | 68 | 62 |
| drugi odczyt `/torrents/{id}` | 92 | 93 |
| `listed` / `empty` / `incomplete` / `no_hash` / `pending` / `budget_cut_after_lookup` | 149 / 11 / 0 / 12 / 4 / 3 | 149 / 3 / 3 / 19 / 4 / 2 |

Poprzednio 275 wizyt na 380 odczytów w obu kolejkach razem; teraz 359 wizyt na 376 odczytów.

### N-2 — stronicowanie `/animes/{id}/episodes/{n}` (sonda `a1_probe_n2.py`)

Dowód: `tests/fixtures/acquisition/reference/probes/n2.json` — 5 surowych odpowiedzi (metoda, URL,
status, treść; bez nagłówków; TsukiHime zsanityzowane), warianty zapytań i wynik sprawdzeń
(`checks`), sonda z 2026-10-06, 0 odpowiedzi 429.

Odpowiedź `{total, start, limit, results}`. Na liście z `total` 29 (`/animes/9779/episodes/1`):

- `limit=15` + `offset=15` zwraca `start: 15` i 14 wierszy; obie połowy razem są identyczne z `limit=100`;
- parametr `start=15` jest ignorowany (wynik jak bez przesunięcia) — `start` to tylko echo w odpowiedzi;
- `limit=101` → `422` (`less_than_equal`, „Input should be less than or equal to 100”).

Potwierdzone. W zestawie żadna lista odcinka TsukiHime nie przekroczyła 100 wierszy, więc druga
strona w nagraniu nie wystąpiła. Starsze tytuły (Bocchi, Spy×Family, Frieren, Kimi no Na wa, OVA
Kaguya, Mo Dao Zu Shi) mają w TsukiHime tytuł, ale 0–1 wydań na odcinek.

### N-3 — Knaben v2

Wyszukiwanie przez **GET** (decyzja): `q`, `s` (300), `f` (przesunięcie), `o=date`, `dead`. Pola:
`hash` (WIELKIE litery — normalizacja), `title`, `seeders`, `magnetUrl`, `total.value`. Druga strona
potrzebna tylko w filmie (`Kimi no Na wa.`).

### N-4 — nekoBT torznab

Tagi językowe w sufiksie tytułu: `{Tags:...;A=ja;F=pl;S=...}`; flagi bez `=` (np. `HS`). Kody bywają
złączone (`es419`, `frfr`, `ptbr`, `zhhans`). `seeders` i `infohash` w `torznab:attr`. Tytuły czasem
kończą się `.mkv`. Stronicowanie `limit=100` + `offset`. Magnety zawierają `ws=` (webseed).

### N-5 — `{ss}` z `season_context`

| Przypadek | `season_context` index/offset | zapytania AniList | indeks z grafu |
|---|---|---:|---:|
| 101972-1, 130003-*, 140960-*, 154587-*, 21519-1 | 1 / 0 | 0 | 1 |
| 152677-1, 159042-1, 172192-1, 204389-*, 210031-* | 2 / 12 | 1 | 2 |
| 189123-1 | 2 / 25 | 1 | 2 |
| 213805-1 | 2 / 14 | 1 | 2 |
| 185756-*, 195516-1 | 3 / 24, 3 / 48 | 2 | 3 |
| 194884-1 (SPECIAL) | 5 / 41 | 4 | 5 |

Zgodność 21/21. `season_context` wymaga 19 dodatkowych zapytań AniList łącznie (0–4 na przypadek;
zapisane osobno w `evidence`); graf daje indeks bez zapytań. Decyzja: `{ss}` z grafu. Dla SPECIAL
indeks nie jest używany (brak frazy `S{ss}E{NN}`).

### N-6 — `load_user_settings`

Sprawdzone w runtime (`a1_n6_settings.py`, plik tymczasowy, podmieniony `config_path`):
`SETTINGS_SCHEMA_VERSION = 3`, 36 pól.

- Częściowy plik v3: wczytany jako schemat 3; brakujące pola dostają wartości domyślne.
- Plik v2: migrowany do 3.
- Nieznane klucze (`polish_wait_h`, `source_knaben`) są po cichu pomijane.
- Plik ze schematem 4: ostrzeżenie i **pełne wartości domyślne** (cały plik odrzucony).
- Wczytanie nie zmienia pliku na dysku.

Wniosek: nowe ustawienia A1 wymagają pól dataclass i walidacji, bez podnoszenia schematu.

### N-8 — `countryOfOrigin`

Pole wraca w zapytaniu AniList (`anilist.country`, `notes.country`). 101972 (Mo Dao Zu Shi, ONA) = `CN`;
pozostałe = `JP`.

## 4. Pokrycie względem 640

`coverage-baseline.json` w formacie planu §9.3: dla każdego przypadku `union` i lista hashy każdego
źródła badania (`tsukihime`, `nekobt`, `knaben`, `torrentio`, `nyaa`), dalej `covered` per tryb,
`missing` (status każdej brakującej pary) i `requery` (zapytania, kompletność, indeksy surowych
odpowiedzi). Surowe odpowiedzi ponownych zapytań leżą w `_requery_responses` (TsukiHime
zsanityzowane), podsumowanie w `_summary`. Licznik: hashe obecne na scalonej liście trybu
odtworzonej z fixtury; mianownik zawsze 640.

| Miara | Ręczne | Subskrypcja |
|---|---:|---:|
| pokryte | 637 | 637 |
| `gone` | 0 | 0 |
| `unverified` | 0 | 0 |
| `loss` | 3 | 3 |
| pokrycie (bramka ≥95%) | 99,53% | 99,53% |
| spadek | 0,47 pp | 0,47 pp |

Poprzednio 629/640 (98,28%), 11 strat: **8 z braku frazy `S01E01`** (140960-1: EMBER, AnimokuSubs,
Anime Chap, SKYANiME DUBBED, ABdex S01E01-E12; 154587-1: EMBER, dwa Yameii) **i 3 inne**. Fraza
`S01E{NN}` odzyskała wszystkie 8. Zostały 3 inne, wszystkie tylko z Knaben (badanie pytało o sam
tytuł bez numeru) i potwierdzone ponownym zapytaniem jako nadal obecne:

- 154587-28: `[AsukaRaws] Sousou no Frieren S1+S2 - 01-38 (BD 1280x720 …)` — paczka;
- 130003-1: `Bocchi the Rock! - 001 [FlyH] vostfr 720p` — numer trzycyfrowy;
- 210031-1: `Ты и я - полные противоположности (S2) / …` — tytuł cyrylicą na początku.

## 5. Uzupełnianie TsukiHime i pominięte hashe

Budżet według spec §3.4: 10 odczytów na sprawdzenie, osobno w każdym trybie. Wizyta = odczyt btih;
`200` z `len(files) == filecount` kończy wizytę, w przeciwnym razie drugi odczyt `/torrents/{id}`
(krótszy niż `filecount` = `incomplete`, §3 N-1); `202` = `pending`; `404` = `no_hash`. Odczyty zwolnione przez btih idą na kolejne pozycje kolejki.
Kolejka ręczna według §6.1, kolejka subskrypcji według §6.2 po odfiltrowaniu konfliktu na nazwie,
nieużytecznych i wykluczonych. Liczby — §3 N-1.

- Długość kolejek: subskrypcja 6–109, ręczne 15–677 (film); odwiedzono 6–10 wydań.
- 152677-1 i 172192-1 nie mają tytułu w TsukiHime (0 wizyt).

Hashe spoza budżetu zostają nieodwiedzone i są oceniane po nazwie (`release_name_only`). W subskrypcji
wydanie oczekujące (nieodwiedzone, `pending`, `budget_cut_after_lookup`, bez pliku z Torrentio)
blokuje gorszą klasę rozdzielczości, a w tej samej klasie gorszą klasę PL (§6.2). W zestawie blokada
nie rozstrzygnęła żadnego przypadku.

## 6. Wybór OVA/SPECIAL, filmu i donghua

- **OVA/SPECIAL:** Kaguya-sama wa Kokurasetai: Otona e no Kaidan, AniList 194884, `SPECIAL`, 2 odcinki,
  `FINISHED`, `JP`, odcinek 1. Po zmianie fraz na pełny tytuł: 23 wydania (poprzednio 200, głównie
  seria główna), 0 zgodnych.
- **Film:** Kimi no Na wa., AniList 21519, `MOVIE`.
- **Donghua:** Mo Dao Zu Shi, AniList 101972, `ONA`, `CN`; ścieżka `donghua` (oryginalne audio `zh`).

## 7. Propozycja oczekiwań

Top 3 = pierwsze trzy wiersze listy ręcznej po uzupełnieniu (§6.1, z ukryciem ≤720p przy zgodnym
1080p/2160p). Sugestia = pierwszy wiersz grupy 1 (bez konfliktu i nie tylko dub); brak, gdy odcinek
nie ma numeracji. Numeracja według spec A §3.5 (D1–D3): ani.zip po AniList, przy pustych `episodes`
ani.zip po AniDB z arm-server. Regułą jest `numbering_gap` (plan §5.5) liczone dla numeru celu:
bez numeracji jest odcinek bez klucza w `episodes` albo bez `seasonNumber`/`episodeNumber` (`none`),
z parą S/E, którą ma już niższy odcinek lokalny (`duplicate`; najniższy zachowuje numerację), albo
z sezonem różnym od `thetvdb-season` (`tvdb_season`). Cel bez numeracji nie ma S/E, absolutu ani
tytułu odcinka. Reguła nie dotyczy filmu (`MOVIE`): jego cel zostaje bez zmian (decyzja
orkiestratora 2026-10-07, spec A §3.5). Wybór automatyczny =
pierwsze sprawdzenie subskrypcji w `t_due` (§6.2–§6.4):

- przed emisją → `hash: null`;
- bez numeracji (D2) → wybór jak zwykle, a `zgodny` daje tylko tytuł wpisu ze znacznikiem sezonu
  i numerem lokalnym; samo `SxxExx` to `insufficient` z powodem „Mapped numbering cannot be checked
  without target numbering.” (nakładka „D2 (K2)”), nie konflikt;
- pierwszy dopuszczalny z PL → pobiera od razu;
- historia PL `ABSENT` → pobiera od razu;
- historia `PRESENT` lub `UNKNOWN` → `hash: null` z powodem oczekiwania; kandydat po buforze 2 h
  zapisany osobno jako `after_wait` (bufor = min(2 h, bufor) dla `UNKNOWN`, do końca bufora dla
  `PRESENT`; domyślny bufor 2 h).

Wartości w komórce: źródła; werdykt H1 i pewność; punkty jakości; rozdzielczość; klasa PL; seedy;
znaczniki. **„zależne od K2”** oznacza wynik, który dziś daje nakładka skryptu, a w produkcie da go
dopiero `classify_release_name` (K2) lub poprawka parsera:

- „paczka po znaczniku sezonu (parser)” — `S01` przed `[1080p…]` traktowane jak paczka;
- „konflikt sezonu (K2)” — znacznik sezonu spoza dozwolonych (graf + cel) = konflikt;
- „DUAL (K2)” — token `DUAL` usuwany razem z jednym separatorem przed nim (spacja, `.`, `_`),
  np. `H.264.DUAL-VARYG.mkv` → `H.264-VARYG.mkv`; `DUAL-Audio` zostaje. „DUAL usunięty, reszta nazwy
  nadal nieskonsumowana (K2)”, gdy po usunięciu werdykt dalej blokuje inna reszta nazwy. Opis werdyktu
  w wierszu ma dopisek `[nakładka K2: …]`;
- „ocena nazwy wydania (K2)” — werdykt wyłącznie z nazwy wydania;
- „D2 (K2)” — cel bez S/E, nazwa ze znacznikiem `SxxExx`: powód „Mapped numbering cannot be checked
  without target numbering.” zamiast konfliktu sezonu lub „Unconsumed…” (plan §5.3 „Cel bez
  numeracji”, `_identity_conflict`).

| Przypadek | Tytuł / odcinek | Top 1 | Top 2 | Top 3 | Wybór automatyczny |
|---|---|---|---|---|---|
| 101972-1 | Modao Zushi (donghua) / 1; wydań 15, widocznych 14; sugestia: `d2794489` | `d2794489` [Erai-raws] Mo Dao Zu Shi - 01 ~ 15 [1080p CR WEB-DL AVC AAC][MultiSub] [BATCH]<br>torrentio; match 0.995; q 41.1; 1080p; brak; seedy 10; znaczniki: paczka; użyteczne: nie | `cb41d4f8` [SubsPlease] Mo Dao Zu Shi (01-15) (1080p) [Batch]<br>torrentio; match 0.995; q 36.9; 1080p; brak; seedy 14; znaczniki: paczka; użyteczne: nie | `fe35f076` [Erai-raws] Mo Dao Zu Shi: Wanjie Pian - 01 ~ 12 [1080p CR WEB-DL AVC AAC][Multi<br>torrentio; insufficient_evidence 0.654; q 39.6; 1080p; brak; seedy 5; znaczniki: paczka; użyteczne: nie | **hash: null** — brak pewnego wydania (15 wydań, 2 zgodnych) |
| 130003-1 | Bocchi the Rock! (study) / 1; wydań 73, widocznych 60; sugestia: `201191b3` | `201191b3` [DKB] Bocchi the Rock! - (Season 01) [1080p][HEVC x265 10bit][Multi-Subs][batch]<br>nyaa+knaben+torrentio; match 0.997; q 38.3; 1080p; brak; seedy 25; znaczniki: paczka; użyteczne: nie | `9e5736db` [ZigZag] Bocchi the Rock! S01 [1080p REPACK CR WEB-DL E-AC3] [Multi-Audio] [Mult<br>torrentio; match 0.998; q 34.1; 1080p; brak; seedy 35; znaczniki: paczka; użyteczne: nie<br>**zależne od K2:** paczka po znaczniku sezonu (parser) | `654f3d15` [amZero] Bocchi the Rock! - 01v2 [1080p AV1 10Bit][WEBRip][AAC][MultiSubs]<br>nyaa; match 0.996; q 34.1; 1080p; brak; seedy 4; znaczniki: —; użyteczne: tak | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `80431b4f` — brak PL po 2 h<br>[SubsPlease] Bocchi the Rock! - 01 (1080p) [E04F4EFB].mkv<br>historia PL: UNKNOWN |
| 130003-12 | Bocchi the Rock! (study) / 12; wydań 64, widocznych 50; sugestia: `201191b3` | `201191b3` [DKB] Bocchi the Rock! - (Season 01) [1080p][HEVC x265 10bit][Multi-Subs][batch]<br>torrentio; match 0.997; q 38.3; 1080p; brak; seedy 25; znaczniki: paczka; użyteczne: nie | `9e5736db` [ZigZag] Bocchi the Rock! S01 [1080p REPACK CR WEB-DL E-AC3] [Multi-Audio] [Mult<br>torrentio; match 0.998; q 34.1; 1080p; brak; seedy 35; znaczniki: paczka; użyteczne: nie<br>**zależne od K2:** paczka po znaczniku sezonu (parser) | `53bd9c92` Bocchi the Rock S01 1080p AMZN WEB-DL DDP2.0 H 264 MULTi-VARYG (Bocchi the Rock!<br>torrentio; insufficient_evidence 0.993; q 32.2; 1080p; brak; seedy 16; znaczniki: paczka; użyteczne: nie | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `df20ed6a` — brak PL po 2 h<br>[SubsPlease] Bocchi the Rock! - 12 (1080p) [CA5333CB].mkv<br>historia PL: UNKNOWN |
| 140960-1 | SPY×FAMILY (study) / 1; wydań 201, widocznych 152; sugestia: `39154a75` | `39154a75` SPY x FAMILY Season 1 S01 1080p CR WEBRip 10bits x265-Rapta<br>torrentio; match 0.999; q 45.0; 1080p; brak; seedy 82; znaczniki: paczka; użyteczne: nie | `4b7fc5bc` [Judas] Spy x Family (Season 1) [1080p][HEVC x265 10bit][Multi-Subs] (Batch)<br>torrentio; match 0.997; q 40.0; 1080p; brak; seedy 80; znaczniki: paczka; użyteczne: nie | `3c5d36ec` [Judas] Spy x Family (Season 1) [1080p][HEVC x265 10bit][Dual-Audio][Multi-Subs]<br>torrentio; match 0.997; q 39.7; 1080p; brak; seedy 45; znaczniki: paczka; użyteczne: nie | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `f9dceb4d` — brak PL po 2 h<br>[SubsPlease] Spy x Family - 01 (1080p) [CE31DC37].mkv<br>historia PL: UNKNOWN |
| 140960-12 | SPY×FAMILY (study) / 12; wydań 214, widocznych 147; sugestia: `39154a75` | `39154a75` SPY x FAMILY Season 1 S01 1080p CR WEBRip 10bits x265-Rapta<br>torrentio; match 0.999; q 45.0; 1080p; brak; seedy 82; znaczniki: paczka; użyteczne: nie | `4b7fc5bc` [Judas] Spy x Family (Season 1) [1080p][HEVC x265 10bit][Multi-Subs] (Batch)<br>torrentio; match 0.997; q 40.0; 1080p; brak; seedy 80; znaczniki: paczka; użyteczne: nie | `c1f76c1f` [SubsPlease] Spy x Family - 12 (1080p) [E131FCA6].mkv<br>nyaa+torrentio; match 0.996; q 40.0; 1080p; brak; seedy 51; znaczniki: —; użyteczne: tak | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `c1f76c1f` — brak PL po 2 h<br>[SubsPlease] Spy x Family - 12 (1080p) [E131FCA6].mkv<br>historia PL: UNKNOWN |
| 152677-1 | Tantei wa mou, Shindeiru. Season 2 (subscription) / 1; wydań 46, widocznych 46; sugestia: `4c8c3714` (niepewna) | `4c8c3714` [Cyan] Tantei wa Mou, Shindeiru. - 01 [1080p][EAC3][861C6C0D].mkv<br>nyaa+nekobt; insufficient_evidence 0.96; q 32.8; 1080p; brak; seedy 2; znaczniki: —; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2) | `5d905ef9` [Anime Time] Tantei wa Mou, Shindeiru. - 01 [1080p][HEVC 10bit x265][AAC][Eng Su<br>nyaa; insufficient_evidence 0.96; q 30.0; 1080p; brak; seedy 0; znaczniki: —; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2) | `6dc67642` [SubsPlease] Tantei wa Mou, Shindeiru. (01-12) (1080p) [Batch]<br>nyaa; insufficient_evidence 0.919; q 26.5; 1080p; brak; seedy 12; znaczniki: paczka; użyteczne: nie<br>**zależne od K2:** ocena nazwy wydania (K2) | **hash: null** — odcinek przed emisją — cel nie jest należny |
| 154587-1 | Sousou no Frieren (study) / 1; wydań 180, widocznych 153; sugestia: `fd41effc` | `fd41effc` Frieren Beyond Journeys End S01 Season 1 1080p CR WEBRip Dual Audio 10bits x265-<br>torrentio; match 0.998; q 45.0; 1080p; brak; seedy 259; znaczniki: paczka; użyteczne: nie | `3e83b169` Frieren Beyond Journeys End S01E01-E04 1080p CR WEB-DL AAC2.0 H 264-VARYG (Souso<br>nyaa; match 0.998; q 41.3; 1080p; brak; seedy 11; znaczniki: paczka; użyteczne: nie | `a794ea68` [ToonsHub] Frieren: Beyond Journey's End - 01 (Multi-Audio 1080p x264 AAC) [Mult<br>nyaa+knaben+torrentio; insufficient_evidence 0.971; q 41.9; 1080p; brak; seedy 14; znaczniki: —; użyteczne: tak | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `374ff33f` — brak PL po 2 h<br>[SubsPlease] Sousou no Frieren - 01 (1080p) [F02B9CEE].mkv<br>historia PL: UNKNOWN |
| 154587-28 | Sousou no Frieren (study) / 28; wydań 133, widocznych 110; sugestia: `fd41effc` | `fd41effc` Frieren Beyond Journeys End S01 Season 1 1080p CR WEBRip Dual Audio 10bits x265-<br>torrentio; match 0.998; q 45.0; 1080p; brak; seedy 259; znaczniki: paczka; użyteczne: nie | `0aace8f3` [ToonsHub] Frieren- Beyond Journey's End S01E28 1080p CR WEB-DL x264 (Multi-Audi<br>nyaa+torrentio; match 0.999; q 42.2; 1080p; brak; seedy 16; znaczniki: —; użyteczne: tak | `6dac8abb` Frieren Beyond Journeys End S01E28 It Would Be Embarrassing When We Met Again 10<br>nyaa+knaben; match 0.993; q 42.4; 1080p; brak; seedy 17; znaczniki: —; użyteczne: tak<br>**zależne od K2:** DUAL (K2) | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `0aace8f3` — brak PL po 2 h<br>[ToonsHub] Frieren- Beyond Journey's End S01E28 1080p CR WEB-DL x264 (<br>historia PL: UNKNOWN |
| 159042-1 | Tensei Shitara Ken Deshita 2nd Season (study, subscription) / 1; wydań 79, widocznych 62; sugestia: `8657013b` | `8657013b` [ToonsHub] Reincarnated as a Sword S02E01 1080p ADN WEB-DL AAC2.0 H.264 (Multi-S<br>tsukihime+nyaa+nekobt+knaben; match 0.997; q 75.0; 1080p; PL; seedy 194; znaczniki: —; użyteczne: tak | `59262402` Reincarnated as a Sword S02E01 The Floating Island 1080p ADN WEB-DL AAC2.0 H.264<br>tsukihime+nyaa+nekobt+knaben; match 0.999; q 74.5; 1080p; PL; seedy 41; znaczniki: —; użyteczne: tak | `0578d2a7` Reincarnated as a Sword S02E01 SUBFRENCH 1080p ADN WEB-DL AAC2.0 x264-Tsundere-R<br>nyaa+nekobt+knaben; insufficient_evidence 0.978; q 75.0; 1080p; PL; seedy 413; znaczniki: —; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2) | `8657013b` — pierwszy dopuszczalny ma PL napisy — pobiera od razu<br>[ToonsHub] Reincarnated as a Sword S02E01 1080p ADN WEB-DL AAC2.0 H.26<br>historia PL: UNKNOWN |
| 172192-1 | Kikansha no Mahou wa Tokubetsu desu 2nd Season (subscription) / 1; wydań 23, widocznych 23; sugestia: brak | `ce86a5a0` [FrixySubs] Kikansha no Mahou wa Tokubetsu desu - S01E01 [1080p BD HEVC-10bit FL<br>nekobt; insufficient_evidence 0.939; q 55.3; 1080p; PL; seedy 7; znaczniki: bluray; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2); D2 (K2) | `1b3341b3` [FrixySubs] Kikansha no Mahou wa Tokubetsu desu - S01E02 [1080p BD HEVC-10bit FL<br>nekobt; insufficient_evidence 0.865; q 56.7; 1080p; PL; seedy 13; znaczniki: bluray; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2); D2 (K2) | `f0d525ee` [SubsPlease] Kikansha no Mahou wa Tokubetsu desu - 01 (1080p) [8A2F9225].mkv<br>nyaa; insufficient_evidence 0.982; q 28.7; 1080p; brak; seedy 30; znaczniki: —; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2) | **hash: null** — odcinek przed emisją — cel nie jest należny |
| 185756-1 | Tensei Kizoku, Kantei Skill de Nariagaru 3rd Season (study) / 1; wydań 47, widocznych 32; sugestia: `2ae5702c` | `2ae5702c` [Erai-raws] As a Reincarnated Aristocrat, I'll Use My Appraisal Skill to Rise in<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.992; q 45.0; 1080p; brak; seedy 530; znaczniki: —; użyteczne: tak | `42a623c7` [Erai-raws] As a Reincarnated Aristocrat, I'll Use My Appraisal Skill to Rise in<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.992; q 45.0; 1080p; brak; seedy 215; znaczniki: —; użyteczne: tak | `a4ebcde6` [ToonsHub] As a Reincarnated Aristocrat Ill Use My Appraisal Skill to Rise in th<br>tsukihime+nyaa; match 0.997; q 43.4; 1080p; brak; seedy 26; znaczniki: —; użyteczne: tak | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `2ae5702c` — brak PL po 2 h<br>[Erai-raws] As a Reincarnated Aristocrat, I'll Use My Appraisal Skill <br>historia PL: UNKNOWN |
| 185756-2 | Tensei Kizoku, Kantei Skill de Nariagaru 3rd Season (study, subscription) / 2; wydań 189, widocznych 148; sugestia: `22fa4b6a` | `22fa4b6a` [Erai-raws] As a Reincarnated Aristocrat, I'll Use My Appraisal Skill to Rise in<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.992; q 45.0; 1080p; brak; seedy 477; znaczniki: —; użyteczne: tak | `68b1c6d1` [Erai-raws] As a Reincarnated Aristocrat, I'll Use My Appraisal Skill to Rise in<br>tsukihime+nyaa+nekobt+knaben; match 0.992; q 45.0; 1080p; brak; seedy 195; znaczniki: —; użyteczne: tak | `e47f755a` [ToonsHub] As a Reincarnated Aristocrat Ill Use My Appraisal Skill to Rise in th<br>tsukihime+nyaa; match 0.997; q 43.8; 1080p; brak; seedy 31; znaczniki: —; użyteczne: tak | `22fa4b6a` — PL: brak w poprzednim odcinku — pobiera od razu<br>[Erai-raws] As a Reincarnated Aristocrat, I'll Use My Appraisal Skill <br>historia PL: ABSENT |
| 189123-1 | Ao no Hako Season 2 (study, subscription) / 1; wydań 268, widocznych 259; sugestia: `b569f710` | `b569f710` [Trix] Blue Box S02E01 1080p NF WEB-DL Opus2.0 AV1 (Multi-Audio / Dual-Audio, Mu<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.997; q 75.0; 1080p; PL; seedy 155; znaczniki: —; użyteczne: tak | `9a735b8c` [Erai-raws] Blue Box S02E01 [1080p NF WEB-DL AVC EAC3][MultiSub][54AB16DB]<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.992; q 75.0; 1080p; PL; seedy 167; znaczniki: —; użyteczne: tak | `cbedf56e` [Erai-raws] Blue Box S02E01 [1080p NF WEBRip HEVC EAC3][MultiSub][C7A0D4EE]<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.992; q 75.0; 1080p; PL; seedy 294; znaczniki: —; użyteczne: tak | `cbedf56e` — pierwszy dopuszczalny ma PL napisy — pobiera od razu<br>[Erai-raws] Blue Box S02E01 [1080p NF WEBRip HEVC EAC3][MultiSub][C7A0<br>historia PL: UNKNOWN |
| 194884-1 | Kaguya-sama wa Kokurasetai: Otona e no Kaidan (ova_special) / 1; wydań 23, widocznych 23; sugestia: `ac3059b1` (niepewna) | `ac3059b1` [Erai-raws] Kaguya-sama wa Kokurasetai: Otona e no Kaidan - 01 [1080p CR WEBRip <br>nyaa; insufficient_evidence 0.974; q 43.3; 1080p; brak; seedy 25; znaczniki: —; użyteczne: tak | `611534fb` [AnoZu] Kaguya-sama: Love Is War S00E15 Chika Fujiwara Wants to Surprise Miyuki <br>torrentio; insufficient_evidence 0.961; q 42.6; 1080p; brak; seedy 19; znaczniki: —; użyteczne: tak | `285f02fe` [Feibanyama] Kaguya-sama Love is War Stairway to Adulthood [CR WebRip 1080p HEVC<br>torrentio; insufficient_evidence 0.974; q 41.9; 1080p; brak; seedy 14; znaczniki: paczka; użyteczne: nie | **hash: null** — brak pewnego wydania (23 wydań, 0 zgodnych) |
| 195516-1 | Kusuriya no Hitorigoto 3rd Season (study, subscription) / 1; wydań 159, widocznych 129; sugestia: `7fb815cd` | `7fb815cd` [ToonsHub] The Apothecary Diaries S03E01 REPACK 1080p CR WEB-DL AAC2.0 H.264 (Mu<br>tsukihime+nyaa+nekobt+knaben; match 0.999; q 75.0; 1080p; PL; seedy 1537; znaczniki: —; użyteczne: tak | `c1ec31c3` [VARYG] The Apothecary Diaries S03E01 Locusts REPACK 1080p CR WEB-DL AAC2.0 H.26<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.999; q 75.0; 1080p; PL; seedy 526; znaczniki: —; użyteczne: tak | `1340325e` [Erai-raws] Kusuriya no Hitorigoto 3rd Season - 01v2 [1080p CR WEB-DL AVC AAC][M<br>tsukihime+nyaa+nekobt+knaben; match 0.992; q 75.0; 1080p; PL; seedy 444; znaczniki: —; użyteczne: tak | `7fb815cd` — pierwszy dopuszczalny ma PL napisy — pobiera od razu<br>[ToonsHub] The Apothecary Diaries S03E01 REPACK 1080p CR WEB-DL AAC2.0<br>historia PL: UNKNOWN |
| 204389-1 | Yasei no Last Boss ga Arawareta! 2nd Season (study) / 1; wydań 42, widocznych 29; sugestia: `4f393367` | `4f393367` [Erai-raws] Yasei no Last Boss ga Arawareta 2nd Season - 01 [1080p CR WEB-DL AVC<br>tsukihime+torrentio; match 0.992; q 45.0; 1080p; brak; seedy 86; znaczniki: —; użyteczne: tak | `9ff06452` [Erai-raws] Yasei no Last Boss ga Arawareta 2nd Season - 01 [1080p CR WEBRip HEV<br>tsukihime+torrentio; match 0.992; q 45.0; 1080p; brak; seedy 110; znaczniki: —; użyteczne: tak | `69ab1c64` [ToonsHub] A Wild Last Boss Appeared S02E01 1080p CR WEB-DL AAC2.0 H.264 (Yasei <br>tsukihime+nyaa+knaben+torrentio; insufficient_evidence 0.961; q 45.0; 1080p; brak; seedy 173; znaczniki: —; użyteczne: tak | **hash: null** — PL: nieznane — czeka do t_due + 2 h<br>po buforze: `9ff06452` — brak PL po 2 h<br>[Erai-raws] Yasei no Last Boss ga Arawareta 2nd Season - 01 [1080p CR <br>historia PL: UNKNOWN |
| 204389-2 | Yasei no Last Boss ga Arawareta! 2nd Season (study, subscription) / 2; wydań 29, widocznych 21; sugestia: brak | `29a8e5b3` [AnoZu] A Wild Last Boss Appeared! S02E02 1080p CR WEB-DL AAC 2.0 H.264<br>tsukihime+nyaa+nekobt+knaben+torrentio; insufficient_evidence 0.98; q 45.0; 1080p; brak; seedy 203; znaczniki: —; użyteczne: tak | `5ad4e8d2` [Erai-raws] Yasei no Last Boss ga Arawareta 2nd Season - 02 [1080p CR WEB-DL AVC<br>tsukihime+torrentio; match 0.997; q 44.2; 1080p; brak; seedy 36; znaczniki: —; użyteczne: tak | `7a643677` [Erai-raws] Yasei no Last Boss ga Arawareta 2nd Season - 02 [1080p CR WEBRip HEV<br>tsukihime+torrentio; match 0.997; q 44.1; 1080p; brak; seedy 35; znaczniki: —; użyteczne: tak | `5ad4e8d2` — PL: brak w poprzednim odcinku — pobiera od razu<br>[Erai-raws] Yasei no Last Boss ga Arawareta 2nd Season - 02 [1080p CR <br>historia PL: ABSENT |
| 210031-1 | Seihantai na Kimi to Boku 2nd Season (study) / 1; wydań 217, widocznych 196; sugestia: `fa26bfbd` | `fa26bfbd` [ToonsHub] You and I Are Polar Opposites S02E01 1080p CR WEB-DL AAC2.0 H.264 (Mu<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.999; q 75.0; 1080p; PL; seedy 50; znaczniki: —; użyteczne: tak | `e61ee62e` [VARYG] You and I Are Polar Opposites S02E01 Christmas Eve 1080p CR WEB-DL DUAL <br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.999; q 75.0; 1080p; PL; seedy 76; znaczniki: —; użyteczne: tak | `942878e9` [VARYG] You and I Are Polar Opposites S02E01 Christmas Eve 1080p CR WEB-DL AAC2.<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.999; q 75.0; 1080p; PL; seedy 288; znaczniki: —; użyteczne: tak | `942878e9` — pierwszy dopuszczalny ma PL napisy — pobiera od razu<br>[VARYG] You and I Are Polar Opposites S02E01 Christmas Eve 1080p CR WE<br>historia PL: UNKNOWN |
| 210031-13 | Seihantai na Kimi to Boku 2nd Season (study) / 13; wydań 52, widocznych 38; sugestia: `940fa9c0` | `940fa9c0` [Erai-raws] Seihantai na Kimi to Boku 2nd Season - 13 [1080p CR WEB-DL AVC AAC][<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.994; q 75.0; 1080p; PL; seedy 762; znaczniki: —; użyteczne: tak | `4f0a0b08` [Erai-raws] Seihantai na Kimi to Boku 2nd Season - 13 [1080p CR WEBRip HEVC AAC]<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.994; q 75.0; 1080p; PL; seedy 666; znaczniki: —; użyteczne: tak | `3c1df91b` You and I Are Polar Opposites S02E13 Christmas Eve 1080p CR WEB-DL AAC2.0 H.264-<br>tsukihime+nyaa+nekobt+knaben+torrentio; insufficient_evidence 0.958; q 75.0; 1080p; PL; seedy 133; znaczniki: —; użyteczne: tak | `940fa9c0` — pierwszy dopuszczalny ma PL napisy — pobiera od razu<br>[Erai-raws] Seihantai na Kimi to Boku 2nd Season - 13 [1080p CR WEB-DL<br>historia PL: PRESENT |
| 213805-1 | Koori no Jouheki 2nd Season (subscription) / 1; wydań 150, widocznych 148; sugestia: `0547543f` | `0547543f` [ToonsHub] The Ramparts of Ice S02E01 1080p NF WEB-DL MULTi AAC2.0 H.264 (Multi-<br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.999; q 90.0; 1080p; PL; seedy 130; znaczniki: —; użyteczne: tak | `f86ca2e0` [VARYG] The Ramparts of Ice S02E01 Clouds and Rain 1080p NF WEB-DL MULTi AAC2.0 <br>tsukihime+nyaa+nekobt+knaben+torrentio; match 0.999; q 90.0; 1080p; PL; seedy 103; znaczniki: —; użyteczne: tak | `bab959ec` [Feibanyama] The Ramparts of Ice S02E01 [NF WebRip 1080p H265 Veryslow AAC Multi<br>tsukihime+nyaa+nekobt+knaben+torrentio; insufficient_evidence 0.958; q 90.0; 1080p; PL; seedy 86; znaczniki: —; użyteczne: tak | `0547543f` — pierwszy dopuszczalny ma PL napisy — pobiera od razu<br>[ToonsHub] The Ramparts of Ice S02E01 1080p NF WEB-DL MULTi AAC2.0 H.2<br>historia PL: UNKNOWN |
| 21519-1 | Kimi no Na wa. (movie) / 1; wydań 677, widocznych 567; sugestia: `956bcde2` (niepewna) | `956bcde2` [Valenciano] Kimi no Na wa (Your Name) (君の名は) [1080p][AV1 10bit][Opus 5.1][Multi<br>nyaa+knaben+torrentio; insufficient_evidence 0.769; q 69.1; 1080p; PL; seedy 35; znaczniki: —; użyteczne: tak | `69d1b053` [Gol] Your Name. 2016 (BD 1080p HEVC 10-bit Opus) Multi-Audio Opus5.1 Multi-Subs<br>nekobt; match 0.902; q 50.0; 1080p; PL; seedy 0; znaczniki: bluray; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2) | `4410e697` [pcela] Kimi no Na wa. / Your Name. / Twoje imię. (2016) - [Bluray 1080p][10bit]<br>nyaa; insufficient_evidence 0.856; q 50.0; 1080p; PL; seedy 0; znaczniki: bluray; użyteczne: tak<br>**zależne od K2:** ocena nazwy wydania (K2) | `69d1b053` — pierwszy dopuszczalny ma PL napisy — pobiera od razu (do weryfikacji po metadanych)<br>[Gol] Your Name. 2016 (BD 1080p HEVC 10-bit Opus) Multi-Audio Opus5.1 <br>**zależne od K2:** ocena nazwy wydania (K2)<br>historia PL: UNKNOWN |

Właściciel potwierdził te oczekiwania 2026-10-06 (`confirmed_by_owner: true` we wszystkich
21 przypadkach `expectations.json`).

Przypadki zostawione jako niepewne: 210031-13 (trzeci wiersz `insufficient`); 204389-2 (`duplicate`:
S02E01 ma już odcinek 1, bez sugestii); 172192-1 (`none`: wpis ani.zip bez S/E, bez sugestii);
152677-1 (sugestia niepewna, przed emisją); 21519-1 (film, sugestia `956bcde2` niepewna).

Przybliżenia użyte do propozycji (do zastąpienia kodem K2–K12):

- `classify_release_name` jeszcze nie istnieje — nazwa wydania z `.mkv` służy jako nazwa pliku;
  nakładki opisane wyżej.
- Pewność: zamrożony model `conf_model.score(...)[1]` (skalibrowany, bez weta).
- Wyrażenia PL/EN/dub/RAW/HardSub/platforma są przybliżone. Blu-ray:
  `blu-?ray | bd(rip|mv|remux)? przed cyfrą lub granicą | remux` (łapie `BD1080p`), −10 pkt.
- Kolejka uzupełniania jest statyczna: nie jest przestawiana po każdej wizycie (spec: dynamiczna).
- Historia PL (§6.3) tylko z wydań poprzedniego odcinka w TsukiHime.
- Przebieg bufora w czasie nie był symulowany; `after_wait` to wynik przy braku nowych wydań.

### Różnice względem poprzedniej propozycji

| Przypadek | Było | Jest | Przyczyna |
|---|---|---|---|
| 130003-1 | auto `9e5736db` ZigZag `S01` | `null` (czeka), `after_wait` `80431b4f` SubsPlease - 01 | ZigZag `S01` = paczka |
| 130003-12 | top 2 `a0846b44` DB neohevc BD1080p; auto ZigZag | BD1080p poza top 3; `null`, `after_wait` `df20ed6a` SubsPlease - 12 | Blu-ray −10; paczka; B2 |
| 140960-1 | top: Rapta, GJM-Kaleido, Judas S01E01; auto `f9dceb4d` | top: Rapta, dwie paczki Judas; `null`, `after_wait` `f9dceb4d` | listy paczek z btih; B2 |
| 140960-12 | top 1 `2b4142ba` VARYG `S02E12` | top: Rapta, Judas, SubsPlease - 12; `null`, `after_wait` `c1f76c1f` | `S02E12` = konflikt sezonu |
| 152677-1 | top 3 Delta `S01 BATCH` | SubsPlease (01-12) Batch | `S01` dla S2 = konflikt |
| 154587-1 | top 1 FrixySubs `S02E01`; auto `bb0026d9` Breeze `S01` | top: paczka S01, VARYG S01E01-E04, ToonsHub; `null`, `after_wait` `374ff33f` SubsPlease - 01 | konflikt sezonu; Breeze = paczka |
| 154587-28 | auto `0aace8f3` | `null`, `after_wait` `0aace8f3`; top 1 paczka `fd41effc` | B2 |
| 172192-1 | top: FrixySubs S01E01/E02, Delta S01 | SubsPlease - 01, Erai 01~12, ASW - 01 | `S01` dla S2 = konflikt |
| 185756-1, 204389-1 | auto `2ae5702c` / `9ff06452` | `null`, `after_wait` ten sam hash; 204389-1 bez Delta `S01 BATCH` w top 3 | B2; konflikt sezonu |
| 194884-1 | 200 wydań, 0 zgodnych | 23 wydania, 0 zgodnych | pełny tytuł w frazach |
| 213805-1 | auto `06e78bb8` | `null`, „brak numeracji (ani.zip)”, bez sugestii | B1 |

Bez zmian decyzji: 101972-1 (zmiana tylko brzmienia powodu), 159042-1, 185756-2, 189123-1, 195516-1,
204389-2, 210031-1, 210031-13, 21519-1.

Po review DUAL i reguły spisu: top 3, wybory automatyczne i `after_wait` bez zmian we wszystkich
21 przypadkach; replay obu trybów bez brakujących odpowiedzi. Jedyna różnica to wiersz `6dac8abb`
(154587-28, top 3 nr 3). Na liście ręcznej ocenia go rzeczywista ścieżka pliku ze spisu TsukiHime
`…H.264.DUAL-VARYG.mkv`; po usunięciu `.DUAL` razem z kropką (`…H.264-VARYG.mkv`) werdykt to `match`
(„Named season, local episode and catalog episode title agree.”), `depends` „DUAL (K2)”. W subskrypcji
wydanie nie zostało odwiedzone i ocenia go tylko nazwa z Nyaa z nawiasem
`(Sousou no Frieren, Dual-Audio, Multi-Subs)`; ten nawias nadal blokuje dopasowanie (`insufficient`,
„DUAL usunięty, reszta nazwy nadal nieskonsumowana (K2)”). To zadanie dla `classify_release_name`
(K2); skrypt nie dodaje na nawias nakładki. Zmiana `incomplete` nie przestawiła żadnego wiersza:
3753beaf ma plik z Torrentio, a c66cb8d4 nie jest w top 3 ani w wyborze.

### Różnice po numeracji §3.5 (K9b, 2026-10-07)

Porównanie z poprzednim `expectations.json` (kopia `%TEMP%\opencode\reference_v3\`). Replay obu
trybów: 21 × 2, 0 brakujących odpowiedzi, wizyty identyczne z nagraniem.

| Przypadek | Numeracja | Było | Jest | Przyczyna |
|---|---|---|---|---|
| 213805-1 | AniDB 20168: S02E01, abs. 15, „Clouds and Rain” | auto `null` „brak numeracji (ani.zip)”, bez sugestii | sugestia i auto `0547543f` ToonsHub `S02E01 MULTi` (PL, 130 seedów, q 90) — pobiera od razu; top 2 VARYG `S02E01 Clouds and Rain` (`match`) | ani.zip po AniDB |
| 159042-1 | sprzeczna: odc. 1 i 2 = S02E01 (ten sam `tvdbId`) | auto `8657013b` ToonsHub `S02E01` (PL) od razu; sugestia `8657013b` | auto `null` (PL nieznane), `after_wait` `82111ec0` `[Isekai] Tensei Shitara Ken Deshita Season 2 - 01`; bez sugestii; ToonsHub/VARYG `S02E01` → `insufficient` (D2) | duplikat S/E |
| 204389-1 | sprzeczna (jak wyżej) | sugestia `4f393367`; top 3 nr 3 ToonsHub `S02E01` | bez sugestii; top 3 nr 3 `bf81390b` AnoZu `S02E01` (`insufficient`, D2); auto bez zmian (`null`, `after_wait` `9ff06452`) | duplikat S/E |
| 204389-2 | sprzeczna (jak wyżej) | sugestia `3c902956` (niepewna); top: ToonsHub, VARYG `S02E02`, Erai | bez sugestii; top: `29a8e5b3` AnoZu `S02E02` (D2), Erai `5ad4e8d2`, Erai `7a643677`; auto bez zmian `5ad4e8d2` | duplikat S/E |
| 152677-1 | sprzeczna (odc. 1 i 2 = S02E01) | sugestia `4c8c3714` (niepewna) | bez sugestii; auto bez zmian (przed emisją) | duplikat S/E |
| 172192-1 | jest, ale odcinki ani.zip bez S/E | top: SubsPlease - 01, Erai 01~12, ASW; sugestia `f0d525ee` (niepewna) | top: FrixySubs `S01E01` `ce86a5a0`, FrixySubs `S01E02`, SubsPlease - 01; sugestia `ce86a5a0` (niepewna); auto bez zmian (przed emisją) | D2: `S01E01` przestaje być konfliktem sezonu |
| 210031-1, 210031-13 | bez zmian | bez Torrentio | Torrentio przez Kitsu 50634; top 3 i auto bez zmian | krok 3 §3.5 |

Pozostałe 13 przypadków: top 3, sugestia i wybór bez zmian. Poza tabelą w 152677-1 i 204389-1/2
zmieniła się tylko pewność wierszy (np. 0,992 → 0,997), bo cel stracił S/E. Pokrycie bez zmian: 637/640 (99,53%) w obu trybach,
0 zniknięć, 0 niezweryfikowanych, te same 3 straty (§4).

### Różnice po regule numeracji celu (plan v17, 2026-10-07)

`numbering_gap(mapping, number, tvdb_season)` zastąpiło `numbering_conflicts` (które odbierało
numerację obu odcinkom pary) i warunek „niepuste `episodes`”. Porównanie z propozycją K9b (kopia
`%TEMP%\opencode\reference_v4\`); bez nowych zapytań (§2). Replay obu trybów: 21 × 2, 0 brakujących
odpowiedzi. Pole propozycji `numbering_conflict` zastąpiło `numbering_gap` (`none` / `duplicate` /
`tvdb_season` / `null`).

| Przypadek | Numeracja (v17) | Było (K9b) | Jest | Przyczyna |
|---|---|---|---|---|
| 159042-1 | jest: S02E01, abs. 13, „The Floating Island” | `duplicate`; auto `null` (PL nieznane), `after_wait` `82111ec0`; bez sugestii | sugestia i auto `8657013b` ToonsHub `S02E01` (PL) — pobiera od razu; top 3: ToonsHub `8657013b`, `59262402` `S02E01 The Floating Island` (oba `match`), `0578d2a7` SUBFRENCH (`insufficient`) | najniższy odcinek pary zachowuje numerację |
| 204389-1 | jest: S02E01, abs. 13 | `duplicate`; bez sugestii; top 3 nr 3 AnoZu `S02E01` (D2) | sugestia `4f393367`; top 3 nr 3 `69ab1c64`; auto bez zmian (`null`, `after_wait` `9ff06452`) | jak wyżej |
| 152677-1 | jest: S02E01, abs. 13 | `duplicate`; bez sugestii | sugestia `4c8c3714` (niepewna); auto bez zmian (przed emisją) | jak wyżej |
| 172192-1 | `none` (wpis bez S/E) | sugestia `ce86a5a0` FrixySubs `S01E01` (niepewna) | bez sugestii; top 3 bez zmian; auto bez zmian (przed emisją) | wpis bez S/E = bez numeracji |

204389-2 bez zmian względem K9b (`duplicate`, bez sugestii, auto `5ad4e8d2`). Film 21519-1 jest
wyłączony z reguły (§8 pkt 7) i ma propozycję identyczną z K9b: cel z tytułem „Complete Movie”,
sugestia `956bcde2` (niepewna), auto `69d1b053`. Pozostałe 15 przypadków: top 3, sugestia i wybór
bez zmian. Poza tabelą zmieniła się tylko pewność wierszy (152677-1, 204389-1). Względem stanu sprzed
K9b (`reference_v3`) różnią się już tylko 172192-1 (bez sugestii, top 3 z D2), 204389-2 (bez
sugestii, top 3 z D2) i 213805-1 (§10). Pokrycie bez zmian: 637/640 (99,53%) w obu trybach, 0 zniknięć, 0 niezweryfikowanych,
te same 3 straty (§4).

## 8. Zmiany planu — stan decyzji

Rozstrzygnięte (właściciel / orkiestrator): Knaben przez GET; btih `200` z `files` bez drugiego
odczytu; `202` = `pending`; `{ss}` z grafu; fraza `S01E{NN}` w sezonie 1 (TV); OVA/SPECIAL bez
`S{ss}E{NN}` i z pełnym tytułem; MOVIE bez numeru; fixtury w całości; kolejność kontroli
w `classify` (zamaskowany konflikt sezonu) i token DUAL w K2; `S01` przed `[1080p…]` = paczka
w późniejszym K (parser).

**O7 — wycofane (orkiestrator, astra, sol61, 2026-10-07):** wczesna sprzeczność przed „Unconsumed
filename text…” nie wchodzi do K2. Każdy sprawdzony wariant dał na pełnym korpusie (`evidence = {}`)
fałszywe konflikty dla rekordów poprawnych; najwęższy (tylko `SxxEyy`, numer = lokalny, cel bez
kontynuacji złożonej) — 17, wszystkie z innego systemu sezonów niż mapowanie celu (BLEACH TYBW `S01`
przy S17, Bungo Stray Dogs `S04` przy S3, Seven Deadly Sins `S05` przy S4, InuYasha `S08` przy S7,
Black Clover `S04` przy S1). 154587-1 (`[FrixySubs] … S02E01`) i 140960-12 (`… S02E12` VARYG) zostają
niepewne — świadoma niekompletność. Z O7 zostaje token `DUAL` przed grupą jako metadana techniczna.

Otwarte do decyzji:

1. **OVA/SPECIAL:** nawet z pełnym tytułem 194884 ma 0 zgodnych z 23 wydań — klasyfikator wymaga
   zmapowanego odcinka lub tytułu odcinka z katalogu; automat nigdy nie wybierze. Na liście jest
   też inny special (`[AnoZu] … S00E15 Chika Fujiwara …`) jako `insufficient`.
2. **Zero seedów:** 21519-1 wybiera `69d1b053` (PL, 0 seedów, tylko po nazwie); reguła §6.2 go
   dopuszcza, bo nie ma innego dopuszczalnego 1080p z PL.
3. **Donghua:** 101972-1 ma w źródłach tylko paczki — automat nie wybiera.
4. **210031:** brak `kitsu_id` w ani.zip — rozwiązane krokiem 3 §3.5 (Kitsu 50634, Torrentio wraca).
5. **Odcinki ani.zip bez S/E (172192-1):** rozwiązane w v17 — wpis bez `seasonNumber`
   i `episodeNumber` = `none`, bez sugestii (§7, „Różnice po regule numeracji celu”).
6. **Duplikat S/E (159042-1):** rozwiązane w v17 — numerację zachowuje najniższy odcinek pary;
   159042-1 znów pobiera od razu ToonsHub `S02E01` z PL.
7. **Film bez S/E (21519-1):** rozwiązane (decyzja orkiestratora 2026-10-07) — `numbering_gap` nie
   dotyczy MOVIE. Wpis ani.zip filmu („Complete Movie”, tylko pola AniDB) nie ma S/E, ale cel filmu
   zostaje bez zmian; wraca niepewna sugestia `956bcde2`, auto `69d1b053` bez zmian.

## 9. Niezweryfikowane

- Wyniki rankingu opierają się na przybliżeniach z §7, nie na kodzie A1.
- Pokrycie mierzone tylko dla 15 przypadków badawczych; subskrypcje spoza badania, film, OVA i donghua
  nie mają bazy porównawczej.
- Semantyka `202` znana z 4 odpowiedzi w dwóch tytułach.
- Druga strona listy odcinka TsukiHime nie wystąpiła w nagraniu (N-2 potwierdzone sondą).
- Fixtury nie były czytane przez docelowe adaptery A1 (K8); użyto istniejących adapterów
  Nyaa/Torrentio/AniList/ani.zip i bezpośrednich zapytań dla TsukiHime, Knaben i nekoBT.
- Przypadki przed emisją (152677-1, 172192-1) nagrano dla kształtu odpowiedzi; cel nie jest należny.

## 10. Numeracja bez ani.zip po AniList

Decyzja właściciela D1–D3 (spec A §3.5, plan K9b) zastępuje cel z grafu franczyzy (cel B, badanie
niżej) numeracją z mostów: ani.zip po AniList → arm-server → ani.zip po `anidb_id` przy pustych
`episodes` → Kitsu mappings z kontrolą zwrotną przy braku `kitsu_id`. Numerację celu rozstrzyga
`numbering_gap` (plan v17 §5.5): `none` (brak klucza albo wpis bez S/E), `duplicate` (tę samą parę
ma niższy odcinek lokalny; najniższy zachowuje numerację), `tvdb_season` (sezon różny od
`thetvdb-season`); film (`MOVIE`) jest z reguły wyłączony. Bez numeracji automat przyjmuje tylko `zgodny` z tytułu wpisu i numeru lokalnego.
Skrypty: `a1_record_reference.py` (`bridged`, `numbering_gap`, `episode_target` — emulacja
`identity_target(..., numbering=False)`), `a1_rank.py` (nakładka „D2 (K2)”), `a1_expectations.py`
(bez skrótu „brak numeracji”). Pomiar 288 tytułów, na który powołuje się spec §3.5 D1: §11.

### Numeracja w zestawie (21 przypadków)

| Wynik mostów | Przypadki |
|---|---|
| ani.zip po AniList, cel z numeracją | 17 (w tym 210031-1/13 z Kitsu 50634 z kroku 3; 152677-1, 159042-1 i 204389-1 jako najniższy odcinek pary S02E01) |
| ani.zip po AniDB (puste `episodes` po AniList), cel z numeracją | 213805-1 (AniDB 20168) |
| `duplicate` (S02E01 ma już odcinek 1, ten sam `tvdbId`) | 204389-2 |
| `tvdb_season` | 0 |
| `none` (wpis bez S/E) | 172192-1 |
| film — reguła nie dotyczy (`MOVIE`; wpis „Complete Movie” bez S/E) | 21519-1 |

arm-server odpowiedział w 21/21 (0 × 404); `thetvdb-season` jest `null` w 204389 i 21519 (film),
a w pozostałych zgadza się z `seasonNumber` ani.zip (w OVA 194884 jest to 0 = S00).

### Dane i cel 213805-1

- ani.zip po AniList: `episodes={}`, `kitsu_id=50827`, `thetvdb_id`/`anidb_id` puste.
- arm-server: `anidb=20168`, `thetvdb=459627`, `thetvdb-season=2`, `kitsu=50827`.
- ani.zip po `anidb_id=20168`: odcinek 1 = S02E01, absolute 15, tytuł „Clouds and Rain”; dalej
  S02E02/16, S02E03/17. `mappings.kitsu_id` = `null`, więc zostaje 50827 z pierwszego odczytu.
- Cel: `season=2`, `episode=1`, `absolute=15`, `episode_title="Clouds and Rain"`, bez sprzeczności.
  Frazy ręczne dostają numer absolutny `- 15` (dograne Nyaa 4, Knaben 2, nekoBT 2).

### Nowa propozycja 213805-1

Werdykty: ręczny 13 × `match`, 21 × `insufficient`, 116 × `conflict`; subskrypcja 13 / 13 / 116
(konflikty to `S01E…`/`S01`). Zgodne w subskrypcji, w kolejności §6.2: `0547543f` ToonsHub `S02E01
MULTi` (PL, q 90, 130 seedów), `f86ca2e0` VARYG `S02E01 Clouds and Rain MULTi` (PL, q 90, 103),
`107ee92a` ToonsHub `DUAL` (617), `06e78bb8` Erai „2nd Season - 01” (418), `2d758926` VARYG `DUAL`,
`f30540d8` Erai HEVC, Trix, Judas, DKB, Onalrie, BiOMA, TBK, Mythicore 720p.

- **Sugestia listy:** `0547543f` (pewna); top 3: `0547543f`, `f86ca2e0`, `bab959ec` Feibanyama
  (`insufficient`).
- **Wybór automatyczny:** `0547543f` `[ToonsHub] The Ramparts of Ice S02E01 1080p NF WEB-DL MULTi
  AAC2.0 H.264 (Multi-Audio, Multi-Subs)` — pierwszy dopuszczalny ma PL, pobiera od razu.
- **Różnice:** wcześniej `null` „brak numeracji (ani.zip)” bez sugestii, a przy celu B
  `06e78bb8` Erai (q 75). Z celem z AniDB ToonsHub `MULTi` i VARYG z tytułem odcinka są zgodne
  (wcześniej `insufficient`), więc wygrywa wyższa jakość (q 90 > 75). Odcinek ten sam.

### Badanie celu z grafu (cel B, 2026-10-06, zastąpione przez D1–D3)

Cel B: `season` = indeks z grafu, `episode` = n, `absolute` z `episodes` prequeli, bez tytułu odcinka
(`scripts/tmp/a1_numbering.py`, `%TEMP%\opencode\a1_numbering.json`). Wynik dla 213805-1: 7 zgodnych,
wybór `06e78bb8` Erai. Na pozostałych 20 przypadkach:

| Miara | Ręczny | Subskrypcja |
| --- | ---: | ---: |
| B `match`, A nie-`match` | 4 (tylko 204389-2) | 4 (tylko 204389-2) |
| A `match`, B nie-`match` | 30 | 28 |
| Zmieniony top 3 (ręczny) / wybór (subskrypcja) | 7 | 3 |

- **204389-2 (4 „nowe” dopasowania):** ani.zip przypisuje odcinkom 1 i 2 ten sam `S02E01`,
  absolute 13 i ten sam `tvdbId` — to błąd danych. Cel A odrzucał więc `S02E02` od Ironclad, DKB,
  Unfucked i Onalrie („Explicit mapped episode differs”) i dopasowywał `[Ironclad] … S02E01` jako
  odcinek 2. Wydania VARYG `S02E02 A Rampant Scorpius` = tytuł z ani.zip „Bousou Suru Scorpius”
  potwierdzają, że B ma rację. Wybór automatyczny bez zmian (Erai „2nd Season - 02”).
- **Utracone dopasowania (30/28):** wszystkie przechodzą w `insufficient` (oprócz jednego
  `conflict`, czyli błędnego `S02E01` z 204389-2). Chodzi o wydania potwierdzane tylko tytułem
  odcinka (VARYG z tytułem, ToonsHub `E28 …`) lub resztą nazwy, którą konsumował kontekst ani.zip
  (ToonsHub `(Multi-Subs)`/`MULTi`, paczki `S01`, AsukaRaws `S3 - 01 (25)` bez absolute). Kierunek
  bezpieczny: mniej dopuszczalnych, nie inny odcinek.
- **Zmienione wybory:** 154587-28 (po buforze SubsPlease `- 28` zamiast `0aace8f3`), 195516-1
  (Erai „3rd Season - 01v2” zamiast `7fb815cd`), 210031-1 (Erai „2nd Season - 01” zamiast
  `942878e9`). Każdy nowy wybór to ten sam odcinek; zmienia się wydanie (gorsza jakość wg §6
  ustępuje temu, co zostało dopuszczalne).
- **Sezony i cour:** Kusuriya S3 (195516) i Tensei Kizoku S3 (185756) dostają `absolute=None`, bo
  krawędzie kandydata znają `episodes` tylko bezpośredniego prequela (24/12), a graf franczyzy
  nie ma `episodes`; nie ma to skutku dla subskrypcji (absolute tylko w trybie ręcznym). Frieren 28
  i Spy×Family to sezon 1 bez offsetu — bez zmian werdyktów poza utratą dopasowań po tytule.
  W zestawie nie ma tytułu-cour, więc gałąź `episode=None` dla cour nie jest sprawdzona.
- **Formaty spoza TV:** 194884 (OVA) dostaje cel S05E01 zamiast S00E15, a 21519 (film) S01E01 —
  zero dopasowań i wybór bez zmian, ale numer jest bez sensu. Zastępstwo powinno działać tylko dla
  `TV`/`TV_SHORT`/`ONA`.

Wniosek badania B (przed decyzją D1–D3): na 21 przypadkach cel B nie dopasował żadnego wydania innego odcinka. Jedyne nowe dopasowania
(204389-2) korygują błąd ani.zip. Kosztem jest utrata dopasowań opartych na tytule odcinka
i kontekście ani.zip, która w 3 przypadkach zmienia wydanie, nie odcinek. Zastępstwo jest bezpieczne
jako fallback, gdy ani.zip nie ma numeracji dla `n`, pod warunkami: format `TV`/`TV_SHORT`/`ONA`;
`episode=None` dla cour; `absolute` tylko przy pełnym łańcuchu znanych `episodes`; brak tytułu
odcinka. Niesprawdzone: tytuł-cour, kolejka liczona od celu B i przypadki, w których indeks
z grafu różni się od sezonu TVDB (w zestawie zgodne wszędzie poza OVA).

## 11. Pomiar numeracji (288 tytułów)

Podstawa decyzji D1 (spec A §3.5). Dwa pomiary z 2026-10-06 na tej samej, zamrożonej populacji;
baseline kodu `456d5a33`. Odcięcie emisji **2026-10-06T20:20:53+00:00**, odpowiedzi ani.zip
zbierane 20:20:53–21:10:11 UTC (przekrój, nie migawka). Raporty źródłowe i surowe dowody:
`%TEMP%\opencode\numbering_measure_report.md` (P1) i `numbering_measure_preport.md` (P2, P3) wraz
z plikami `numbering_measure_*`; poza repozytorium.

### Metoda

- **Populacja:** AniList GraphQL, `type:ANIME`, `format_in:[TV,TV_SHORT,ONA]`, trzy pełne stronicowania:
  RELEASING (192), SUMMER 2026 (87), FALL 2026 (83); suma 288 unikalnych ID (TV 121, TV_SHORT 44,
  ONA 123). Bez filtra kraju i popularności. Wyemitowane = jawne węzły `airingSchedule` przed
  odcięciem; 60/288 tytułów nie ma harmonogramu.
- **Podziały:** pierwszy sezon / kontynuacja z `graph_season_index`; top 100 = najwyższa `popularity`
  w kohorcie (SUMMER i FALL mają < 100 tytułów, więc w całości są w top 100).
- **Luki:** a = brak lub puste `episodes`; b = brak `thetvdb_id`; c = `episodes` niepuste, ale brak
  klucza co najmniej jednego wyemitowanego odcinka; d = brak `kitsu_id`. HTTP 404 ani.zip (30 z 288)
  liczone jako a+b+d.
- **P1:** ani.zip po AniList ID. **P2:** tylko przy pustym P1 — dokładny wpis Fribb (snapshot
  z tego samego dnia) → jednoznaczny AniDB ID → ani.zip po `anidb_id`; częściowych P1 nie naprawia.
  **P3:** przy braku Kitsu — Kitsu mappings po AniList z jednym `item` typu anime i kontrolą zwrotną
  `/anime/{id}/mappings`; bez wyszukiwania po nazwie. P2 i P3 nie odświeżały P1 ani AniList.
- Produkt (D1) bierze AniDB ID z arm-server, nie z Fribb; pomiar P2 używał Fribb jako mostu.

### Luki a / c / d: P1 → P2 → P3

Liczba tytułów (procent N). c nie zmienia się, bo P2 nie dotyka częściowych P1.

| Kohorta / grupa | N | a: P1 → P2 | c | d: P1 → P3 |
|---|---:|---|---:|---|
| UNION / all | 288 | 131 (45,5%) → 108 (37,5%) | 10 (3,5%) | 127 (44,1%) → 67 (23,3%) |
| UNION / top100 | 100 | 12 (12,0%) → 6 (6,0%) | 2 (2,0%) | 24 (24,0%) → 3 (3,0%) |
| UNION / rest | 188 | 119 (63,3%) → 102 (54,3%) | 8 (4,3%) | 103 (54,8%) → 64 (34,0%) |
| UNION / first | 193 | 82 (42,5%) → 68 (35,2%) | 6 (3,1%) | 86 (44,6%) → 46 (23,8%) |
| UNION / continuation | 95 | 49 (51,6%) → 40 (42,1%) | 4 (4,2%) | 41 (43,2%) → 21 (22,1%) |
| RELEASING / all | 192 | 103 (53,6%) → 88 (45,8%) | 10 (5,2%) | 98 (51,0%) → 60 (31,2%) |
| RELEASING / top100 | 100 | 32 (32,0%) → 22 (22,0%) | 8 (8,0%) | 36 (36,0%) → 10 (10,0%) |
| RELEASING / rest | 92 | 71 (77,2%) → 66 (71,7%) | 2 (2,2%) | 62 (67,4%) → 50 (54,3%) |
| SUMMER_2026 / all | 87 | 23 (26,4%) → 19 (21,8%) | 0 | 27 (31,0%) → 10 (11,5%) |
| FALL_2026 / all | 83 | 42 (50,6%) → 27 (32,5%) | 0 | 46 (55,4%) → 13 (15,7%) |

Tylko tytuły z co najmniej jednym wyemitowanym odcinkiem:

| Kohorta / grupa | N | a: P1 → P2 | c | d: P1 → P3 |
|---|---:|---|---:|---|
| UNION / all | 205 | 74 (36,1%) → 59 (28,8%) | 10 (4,9%) | 78 (38,0%) → 30 (14,6%) |
| UNION / top100 | 89 | 6 (6,7%) → 1 (1,1%) | 2 (2,2%) | 23 (25,8%) → 3 (3,4%) |
| RELEASING / all | 134 | 62 (46,3%) → 50 (37,3%) | 10 (7,5%) | 60 (44,8%) → 27 (20,1%) |

Wyemitowane odcinki bez klucza w `episodes` (a+c): UNION 1533 → 1459 z 4276 jawnych emisji
(tytuły 84 → 69 z 205); RELEASING 1416 → 1374 z 3455; SUMMER 167 → 121 z 920; FALL 29 → 19 z 67.
Brak TVDB ID (b) w P1: 167/288 (58,0%), RELEASING 140/192 (72,9%).

### Jakość odzyskanych rekordów P2

P2 odzyskało `episodes` dla 23/131 pustych mapowań (17,6%); P3 potwierdziło 60 z 63 kandydatów
Kitsu (47,2% z 127 braków; w 3 zwrotny odczyt dał 404). Z 23 rekordów P2 tylko 10 ma S/E dla
wszystkich dostępnych odcinków, a 11 nie ma S/E wcale — przy regule v17 te 11 dalej daje `none`.
Rozbieżności w 5 rekordach:

- 198727 Chitose-kun Part 2: sezon Fribb/TVDB 2, ani.zip S1 — przypadek `tvdb_season`;
- 213657 Yozakura-san S2 Part 2: odcinki 1 i 2 = S02E13 i różna data — przypadek `duplicate`;
- 204650 Tougen Anki: AniList 24 odcinki, ani.zip 4 klucze (daty 1–4 zgodne);
- 208367 Duel Masters LOST i 212308 Pan no Akachan: rozjazd dat emisji.

213805 (Koori no Jouheki S2) to rekord P2 bez sprzeczności: AniDB 20168, odcinek 1 = S02E01,
absolute 15, „Clouds and Rain” — zgodne z nagraniem w §10.

### Co zostaje po P3 (131 tytułów z luką a/c/d)

Przyczyny nakładają się.

| Przyczyna | Tytuły |
|---|---:|
| Fribb bez AniDB ID | 66 |
| brak dokładnego mostu Kitsu (pusta lista mapowań po AniList) | 64 |
| ani.zip po AniDB: 404 | 25 |
| częściowe P1 (c), P2 nie uruchamiany | 10 |
| ani.zip po AniDB: puste `episodes` | 9 |
| brak wpisu Fribb | 8 |
| Kitsu: zwrotny odczyt 404, niepotwierdzone | 3 |

Luki c to długie serie (Crayon Shin-chan, Doraemon, Sazae-san, Anpanman i in.) z brakującymi
późniejszymi numerami. Spośród 131 pozostałych tytułów 73 mają emisję; TsukiHime ma wydanie dla co
najmniej jednego odcinka w 32, dla wszystkich w 25.

### Losowa próba numeracji

20 tytułów z 49 pełnych mapowań (seed `20261006`): 19 ma numerację AniList zgodną z ani.zip,
1 różną — BLEACH 185874 (graf S05E01–10, ani.zip S17E41–50; 10/236 odcinków). Stąd w D2 sezon
z grafu nie jest dowodem.

### Ograniczenia

- Jeden przekrój: nie wiadomo, kiedy dane pojawiły się w ani.zip (brak pól dat dodania).
- P2/P3 wykonano po P1 i nie dowodzą dostępności mostów o godzinie odcięcia.
- Fribb i ani.zip mogą mieć wspólne źródło; zgodność nie jest niezależnym audytem.
- Pokrycie pól to nie poprawność numeracji: kontrola dat i sezonów wykryła 5 rozbieżności na 23.
