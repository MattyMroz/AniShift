---
kind: evidence
status: zebrane
updated: 2026-10-25
baseline: main @ 4365a51 (kod), workspace/ready na 2026-10-25 (dane)
---

# Dowody: nazwy własne w tłumaczeniu

## 1. Stan dziś (kod)

### Jak powstaje prompt

| Element | Gdzie | Co robi |
|---|---|---|
| Wiadomość systemowa | `anishift/services/translation/engines/llm/prompts/system.md` | rola, hierarchia instrukcji (pkt 3: „jawny glosariusz oraz informacje o tytule dostarczone przez aplikację”, linia 11), format `[N]` |
| Części użytkownika | `engines/llm/service.py:247-258` (`_complete`) | dokładnie trzy części: `translation.md`, wybrany styl, numerowane linie; przy naprawie kontraktu czwarta: `retry.md` |
| Zasady nazw | `prompts/translation.md:20-33` | „Jeżeli aplikacja dostarcza glosariusz, profil tytułu lub informacje o postaciach…” plus przykłady odmiany z powieści *Shadow Slave* (Sunny, Nephis, Cassie) |
| Zwroty grzecznościowe | brak | ani `system.md`, ani `translation.md`, ani żaden styl nie mówi nic o `-san`, `-kun`, `-senpai` (grep po `honor`, `-san`, `senpai`) |
| Wybór stylu | `application/runtime.py:504` | `style_name=snapshot.llm_translation_style`; jeden styl globalnie, nie per seria |

Aplikacja nigdy nie dostarcza glosariusza ani informacji o tytule: `LlmTranslateConfig` ma tylko `max_batch_lines`, `style_name`, `max_contract_retries` (`engines/llm/config.py:16-22`), a `TranslationTaskHandler._translate_subtitles` przekazuje do tłumaczenia wyłącznie linie (`application/translation_handler.py:282-315`, `354-360`).

### Style

Pakietowe pliki w `engines/llm/prompts/styles/`: `neutral.md` (domyślny, `engines/llm/constants.py:21`), `funny.md`, `adult-extreme.md`, `shadow-slave.md`. Ten ostatni to ręczny glosariusz jednej powieści zapisany jako styl (np. linia 413: „Imiona postaci, nazwy miejsc i klanów NIE TŁUMACZ (Sunny, Nephis…)”). To jedyny w repo precedens wiedzy o tytule.

### Chunking

`translation_chunk_chars: 750` (`application/planning.py:167`) trafia do `ChunkConfig` (`application/runtime.py:685-686`) i jest używane tylko dla wejścia TXT: `read_text_document` i `text_spoken_lines` (`application/translation_handler.py:237`, `266`, `412`). **Napisów ASS/SRT nie dotyczy.** Dla napisów rozmiar żądania wyznacza `translation_batch_size` (domyślnie `0`, `planning.py:168`), które `runtime.py:503` zamienia na `max_batch_lines=None`, czyli cały plik w jednym żądaniu (`engines/llm/service.py:171`). Przy limicie kontekstu lub wyjścia partia dzieli się na połowy (`service.py:225-237`).

### Jaki kontekst dostaje model

- Wszystkie linie jednego pliku naraz, chronologicznie: dialogi (`spoken`, bez deduplikacji) przeplatane z tekstem ekranowym (`displayed`, z deduplikacją) (`services/translation/service.py:204-237`).
- Bez tytułu serii, bez numeru odcinka, bez listy postaci, bez płci, bez poprzednich odcinków. Przy `translation_batch_size > 0` kolejne partie nie widzą nawet poprzednich linii tego samego pliku.
- Ustawień właściciela (`config/settings.json`) nie czytałem: zakaz briefu. Wartości `llm_model_id`, stylu i `translation_chunk_chars` pochodzą z briefu; `translation_batch_size` zakładam domyślne.

### Co AniShift wie o serii

- `services/catalog/anilist.py`: wyszukiwanie tytułów (`search`, zapytanie z `title {romaji english native} synonyms`, linie 60-61), łańcuch prequeli, harmonogram emisji i graf franczyzy (`franchise`, do 4 zapytań). **Nie pobiera postaci.**
- `TitleCandidate` (`services/catalog/types.py:62-77`): `anilist_id`, tytuły romaji/angielski/natywny, synonimy, sezon, format.
- Stan ownera (`config/watch/state.json`) wiąże subskrypcje i pobrania z `anilist_id`; `application/library.py:185-207` (`downloaded_episodes`) mapuje zestaw w `ready/` na `anilist_id` i numer odcinka, ale tylko dla plików pobranych przez AniShift.
- Ścieżka tłumaczenia nie korzysta z żadnej z tych informacji.

### Gdzie leżą tłumaczenia

`workspace/ready/*.pl.ass` (pełny plik polski) i `*.displayed.pl.ass` (wariant z warstwą wyświetlania), obok `.mkv` ze źródłowymi napisami angielskimi. Osobnych angielskich `*.ass` w `ready/` nie ma: źródło wyciągnąłem z MKV (§2).

## 2. Metoda

1. Dla każdego `*.pl.ass` w `ready/` (bez `.displayed`/`.spoken`) wyciągnąłem pierwszą angielską ścieżkę ASS z MKV obok (`ffmpeg -map 0:<idx> -c copy`) do katalogu tymczasowego poza repo. Tylko odczyt `ready/`.
2. Zdarzenia źródła i wyniku sparowałem po identycznym `start`/`end`, w kolejności. Z 33 plików z angielską ścieżką ASS 27 sparowało się w co najmniej 77% zdarzeń źródła (25 w ponad 90%). Sześć ma przesunięte czasy i praktycznie nie wnosi par: `Kikansha… - 03`, `Seihantai… - 09` i `- 12`, `Tsuihou…` (Onalrie) i `Exiled Heavy Knight` S01E17, `Reincarnated as a Sword` S02E04. Poza próbką zostały pliki `.pl.srt`, `Even the Student Council…` (brak angielskiego ASS w MKV) i `Katainaka no Ossan II` (nazwa nie przeszła mojego filtra plików).
3. Postacie z AniList: dwa zapytania publiczne bez klucza (2026-10-25, 11 serii, `characters(perPage: 25, sort: [ROLE, RELEVANCE, ID])`).
4. Wyszukiwanie: wystąpienia imion (z AniList i z wielkiej litery w środku zdania) oraz sufiksów (`-san`, `-kun`, `-chan`, `-sama`, `-senpai`, `-dono`) w źródle i forma w sparowanej linii polskiej. Każdy przykład poniżej sprawdziłem ręcznie w kontekście.

**Numer linii** w tabelach to fizyczna linia w pliku `*.pl.ass` (licząc od 1, z nagłówkiem), obok znacznik czasu startu. Nazwy plików skracam do serii i odcinka; pełne nazwy są w `workspace/ready/`.

**Ograniczenie**: daty modyfikacji plików mieszczą się między 2026-10-04 a 2026-10-25 (data może oznaczać regenerację układu, nie tłumaczenie), a model i wersja promptu dla konkretnego pliku nie są zapisane w ASS. Część mogła powstać innym modelem niż Gemini 3.8 Flash. Dlatego przykłady dowodzą, **jakie błędy występują**, a nie jak często popełnia je dzisiejszy model. Częstość zmierzy dopiero przebieg bazowy z `plan.md` (faza 1).

## 3. Przykłady

### A. Zmieniona pisownia imienia

| # | Plik (seria, odcinek) | Linia | Czas | Źródło (EN) | Wynik (PL) | Problem |
|---|---|---|---|---|---|---|
| 1 | Apothecary Diaries S03E01 (VARYG) | 72 | 0:04:08 | `You Gyokuen, Concubine Gyokuyou's father` | `ojciec Gyokuyo, Yo Gyokuen` | dwa imiona skrócone; ta sama postać ma w linii 65 pisownię `Gyokuyou` |
| 2 | Apothecary Diaries S03E01 | 88, 93, 96 | 0:05:15 | `Master Onsou went to get him` | `Onso już po niego poszedł.` | `Onsou` → `Onso` we wszystkich trzech wystąpieniach; tytuł `Master` zgubiony |
| 3 | Seihantai na Kimi to Boku S2 - 07 | 417 | 0:18:28 | `Taira-kun, Saotome-kun, and Hasegawa-kun...` | `Tani... i Taira, Saotome, Hagasegawa...` | literówka w nazwisku: `Hasegawa` → `Hagasegawa` |
| 4 | Iceblade Sorcerer S02E02 / S02E03 | 381 / 345 | 0:17:49 / 0:17:34 | `This is for Rebecca.` / `where did Rebecca and Maria walk off to?` | `Robię to dla Rebeki!` / `gdzie znowu wcięło Rebeccę i Marię?` | w E02 imię spolszczone do `Rebeka`, w E01 (`Rebecco.`, linia 355) i E03 zostaje `Rebecca` |

### B. Ta sama nazwa różnie w kolejnych odcinkach

| # | Plik | Linia | Czas | Źródło | Wynik | Problem |
|---|---|---|---|---|---|---|
| 5 | Iceblade Sorcerer S02E01 / E02 / E03 | 77 / 71 / 77 | 0:03:49 / 0:03:15 / 0:02:54 | plansza tytułowa `The Iceblade Sorcerer Shall Rule the World` | `Magik Lodowego Ostrza zapanuje nad światem` / `Mag Lodowego Ostrza zawładnie światem` / bez tłumaczenia | trzy wersje tytułu w trzech odcinkach; w E01 zapowiedź (linia 493) zostawia tytuł po angielsku w cudzysłowie |
| 6 | Apothecary S03E01 / Kusuriya S3 - 02 | 394 / 38 | 0:22:03 / 0:01:53 | `Master Jinshi, it's time.` / `Master Jinshi.` | `Jinshi, już czas.` / `Panie Jinshi.` | E01 gubi tytuł i rejestr, E02–E04 konsekwentnie mają „pan Jinshi” |
| 7 | Sasaki and Peeps S2 - 02 / S02E03 | 341 / 74 | 0:19:24 / 0:04:02 | `…when you were made a baron, Sasaki-dono.` / `Sasaki-dono's world?` | `…panie Sasaki.` / `W świecie Sasaki-dono?` | ten sam sufiks raz staje się „panem”, raz zostaje |
| 8 | Tantei wa Mou Shindeiru S2 - 02 / - 03 | 313 / 50 | — / 0:02:53 | `Kimizuka-san...` / `Kimizuka-san, have you finally become a man?` | `Kimizuka-san...` / `Kimizuka, czyżbyś w końcu…` | E02 zostawia `-san`, E03 usuwa go we wszystkich 8 liniach z `Kimizuka-san` |
| 9 | Detective Is Already Dead S02E01 / Tantei S2 - 02 | 174 / 210 | 0:10:47 / 0:14:38 | `Nagisa.` / `Nagisa!` | `Nagiso.` / `Nagisa!` | wołacz w E01 (4 razy), mianownik w E02–E03 |

### C. Zwroty grzecznościowe, które niosą treść

| # | Plik | Linia | Czas | Źródło | Wynik | Problem |
|---|---|---|---|---|---|---|
| 10 | Seihantai S2 - 07 | 139 | 0:07:26 | `But, I mean, calling you "Nishi-san" was kinda... you know?` | `…nazwanie cię „Nishi” było...no wiesz?` | kwestia mówi o sufiksie, a wynik go usuwa; zdanie traci sens |
| 11 | Seihantai S2 - 07 | 135, 140, 142, 143 | 0:07:08–0:07:40 | `Natsumi-chan` → `Natsumi-chan...` → `Natsumi...` → `Nacchan!` | `Natsumi` → `Natsumi...` → `Natsumi...` → `Nat!` | stopniowe skracanie dystansu (sufiks, samo imię, zdrobnienie) zlewa się w dwie identyczne linie |
| 12 | Sasaki and Peeps S02E03 | 265 / 338 | — | `How can I help you, Shindo-senpai?` / `Hoshizaki-senpai...` | `…Shindo-senpai?` / `Panno Hoshizaki...` | w jednym odcinku dwie strategie dla tego samego sufiksu |
| 13 | Iceblade S02E01 / Sasaki S02E03 | 175, 297 / 320 | 0:09:03 / — | `Lydia-senpai.`, `Good morning, Rebecca-senpai.` / `You rejected Shindo-senpai?` | `Lydio-senpai.`, `Rebecco-senpai.` / `Spławiłaś Shindo-senpaia?` | hybryda: polski wołacz imienia z japońskim sufiksem; w innej serii odmieniony sam sufiks |

### D. Odmiana, wołacz i płeć

| # | Plik | Linia | Czas | Źródło | Wynik | Problem |
|---|---|---|---|---|---|---|
| 14 | Sasaki to Pii-chan S2 - 02 | 58 / 236 | 0:02:09 / 0:14:25 | `…be quiet for a minute, Futari Shizuka-san?` / `Futari Shizuka-san!` | `…panno Futari Shizuka?` / `Pani Futari Shizuko!` | w jednym odcinku „panna” i „pani”; wołacz `Shizuko` to inne japońskie imię; to samo w S02E03, linia 160 |
| 15 | Tantei S2 - 03 | 349 | 0:21:18 | `So Saikawa Yui...` | `Zatem, Saikawo Yui...` | wołacz nazwiska; polska norma nie używa wołacza nazwisk ([research.md](research.md) §3.2) |
| 16 | Koori no Jouheki S2 - 03 | 278 | 0:16:11 | `Let's invite Hino and Azumi too!` | `Zwerbujmy Hinę i Azumi!` | `Hino` to mężczyzna (AniList: Youta Hino, Male); biernik żeński zmienia go w „Hinę” |
| 17 | Yasei no Last Boss S2 - 05 / - 04 | 52 / 369 | 0:01:06 / 0:14:52 | `Twelve Heavenly Star Scorpius` / `one of the Twelve Heavenly Stars?` | `Dwanaście Niebiańskich Gwiazd Scorpius` / `jedną z Dwunastu Niebiańskich Gwiazd?` | nazwa grupy jako przydomek postaci bez składni („Scorpius z Dwunastu…”) |

### E. Przypadki sporne, nie liczone jako błąd

- Koori S2 - 03, linie 378 i 380: `Momoka said she had plans.` i `"Momoka."` → `Moja dziewczyna miała już plany.` i `„Moja dziewczyna”.` Żart dotyczy tego, jak chłopak nazywa dziewczynę. Wynik zmienia imię na opis i też jest żartem. To dopuszczalna lokalizacja albo błąd, zależnie od tego, czy imię jest treścią sceny. Pokazuje, że model potrafi zastąpić imię, gdy scena o nim mówi.
- Koori S2 - 03: `Azumi` raz odmienione (`Obecność Azumiego, tego chłopaka`, linia 226), raz nie (`…i Azumi!`, linia 278). AniList ma dwie postacie o tym nazwisku: Yuki (Male) i Miki (Female). Obie formy mogą być poprawne. To przypadek graniczny dla glosariusza: jedno nazwisko, dwie płcie.
- Ao no Hako S2 - 04, linia 221: `Nishida Senpai` → `Nishidzie`. Celownik zgodny z polską normą (-da → -dzie), ale lektor przeczyta imię inaczej niż w mianowniku.

## 4. Liczby pomocnicze

### Zwroty grzecznościowe w sparowanych liniach

Klasyfikacja heurystyczna: sufiks zachowany, zamieniony na pan/pani/panna albo pominięty. Wymaga ręcznej weryfikacji, bo „pan/pani” w linii może nie odpowiadać sufiksowi.

| Seria (źródło) | Wystąpień | Zachowany | pan/pani | Pominięty |
|---|---|---|---|---|
| Seihantai S2 07, 08, 10, 11 i część 09 (CR) | 54 | 0 | 0 | 54 |
| Ao no Hako S2 03–04 (NF, `Senpai` osobnym słowem) | 14 | 0 | 0 | 14 |
| Tantei S2 01–03 (CR) | 48 | 7 | 19 | 22 |
| Sasaki S2 02–03 (SubsPlease/CR) | 28 | 10 | 14 | 4 |
| Iceblade S2 01–03 (CR) | 3 | 3 | 0 | 0 |

Wniosek: strategia zmienia się między seriami i wewnątrz serii. Nie ma jednej reguły, bo prompt jej nie podaje.

### Pokrycie nazw przez AniList

Imiona, które w serii występują co najmniej trzy razy i zostają nieprzetłumaczone: 66 ze 107 (62%) jest w polach `full`/`first`/`last`/`alternative` pierwszej strony postaci (25) wpisu sezonu w AniList. Brakuje głównie miejsc i przedmiotów (`Godheim`, `Blutgang`, `Mizgarz`), których AniList nie modeluje, oraz postaci pobocznych (`Gyokuen`, `Gyokuyou`, `Lihaku`, `Shindo`). AniList zapisuje też część imion inaczej niż napisy: `Mizal` zamiast `Mizar`, `Rain Garland` zamiast `Rein`.

### Kontrprzykłady: co już działa

- Kusuriya S3 01–04: `Verdigris House` → `Grynszpanowy Pawilon` i `Freckles` → `Piegusko` są takie same we wszystkich czterech odcinkach.
- Yasei S2 03–05: `Lady Lufas` → `pani Lufas` (żeńskie imię na spółgłoskę, nieodmienne, zgodnie z normą) i `Seven Luminaries` → `Siedmiu Luminarzy` w trzech odcinkach.
- Wewnątrz jednego pliku model zwykle trzyma jedną formę: cały plik idzie w jednym żądaniu.

Wniosek: najsłabsze ogniwa to spójność **między** odcinkami, pisownia rzadkich imion, płeć i wołacz oraz brak reguły sufiksów. Na nie odpowiada glosariusz i reguły promptu z [specification.md](specification.md).
