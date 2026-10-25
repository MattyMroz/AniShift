---
kind: research
status: zebrane
updated: 2026-10-25
---

# Research: glosariusz nazw własnych dla tłumaczenia LLM

## Odpowiedź

1. AniList GraphQL daje postacie wpisu (`Media.characters`) z imieniem i nazwiskiem, pełną nazwą, zapisem natywnym, aliasami, osobno aliasami-spoilerami, płcią i rolą. Strona ma najwyżej 25 postaci. Limit to 90 zapytań na minutę, a w stanie obniżonym 30. Zakaz masowego zbierania i używania API jako magazynu danych. Na glosariusz jednej serii wystarczy 1–4 zapytań raz na sezon.
2. Branża rozwiązuje spójność nazw między odcinkami listą KNP („key names and phrases”): jeden glosariusz tytułu z zatwierdzonymi formami i notami, używany przez każdego tłumacza każdego odcinka. Badania nad LLM pokazują, że wskazówki słownikowe w prompcie i pamięć nazw własnych poprawiają trafność terminów i spójność dokumentu. Pomiar w WMT 2023 używa dwóch miar: trafności terminów i spójności.
3. Polska norma odmienia obce imiona, także japońskie, z wyjątkami (zakończenia `-u`, nazwiska kobiet na spółgłoskę). Mianownik w funkcji wołacza jest dopuszczalny potocznie, a wołacza nazwisk się nie używa. Co do japońskich sufiksów polska praktyka jest podzielona i nie znalazłem normy. To decyzja właściciela.

Zakres: stan na 2026-10-25. Źródła otwierałem bezpośrednio, poza dwoma wynikami wyszukiwarki oznaczonymi niżej.

## 1. AniList GraphQL: postacie i limity

| Twierdzenie | Źródło | Status |
|---|---|---|
| `Media.characters(sort, role, page, perPage)` zwraca `CharacterConnection`; `perPage` „max 25” | [Media](https://docs.anilist.co/reference/object/media) | potwierdzone (dokumentacja) |
| `CharacterEdge` ma `role` (MAIN/SUPPORTING/BACKGROUND), `name` (nazwa specyficzna dla wpisu), `node` | [CharacterEdge](https://docs.anilist.co/reference/object/characteredge) | potwierdzone |
| `CharacterName`: `first`, `middle`, `last`, `full`, `native`, `alternative`, `alternativeSpoiler`, `userPreferred` (bez logowania romaji) | [CharacterName](https://docs.anilist.co/reference/object/charactername) | potwierdzone |
| `Character.gender` to dowolny napis („Usually Male, Female, or Non-binary”), bywa `null` | [Character](https://docs.anilist.co/reference/object/character) | potwierdzone; w próbce 2026-10-25 trzy `null` |
| Sortowanie `ROLE`, `RELEVANCE` („order manually decided by moderators”), `ID` | [CharacterSort](https://docs.anilist.co/reference/enum/charactersort) | potwierdzone |
| Limit 90/min, „currently in a degraded state and is limited to 30 requests per minute”, po przekroczeniu minuta blokady, nagłówki `X-RateLimit-*`, `Retry-After`; osobny limiter impulsowy | [Rate Limiting](https://docs.anilist.co/guide/rate-limiting) | potwierdzone; nagłówek odpowiedzi 2026-10-25: `X-RateLimit-Limit: 30` |
| W `PageInfo` wiarygodne jest tylko `hasNextPage` | [Pagination](https://docs.anilist.co/guide/graphql/pagination) | potwierdzone |
| Zakaz „hoarding or mass collection” i używania API „as a backup or data storage service”; darmowe użycie niekomercyjne | [Terms of Use](https://docs.anilist.co/guide/terms-of-use) | potwierdzone |
| Awaria API daje 403 z komunikatem GraphQL | [Considerations](https://docs.anilist.co/guide/considerations) | potwierdzone |

Obserwacje z próbki (2 zapytania, 11 serii, [evidence.md](evidence.md) §4):

- Wpis sezonu bywa ubogi: `Kikansha no Mahou wa Tokubetsu desu 2nd Season` ma 5 postaci, a 3 serie mają więcej niż 25 (`hasNextPage: true`).
- Kolejność `full` jest zachodnia (imię, nazwisko), napisy CR używają tego, czym postacie się nazywają (`Tani`, `Nishi`, `Natsumi`), więc dopasowanie musi działać na `first`, `last`, `full` i `alternative` osobno.
- Pisownia AniList różni się czasem od napisów (`Mizal`/`Mizar`, `Rain`/`Rein`). Pisownię musi wyznaczać źródło napisów, nie AniList.
- Wpisy opisowe (`Suzuki no Haha`, alias `Miyu's Mother`) nie są imionami; dopasowanie całych fraz, nie pojedynczych słów, eliminuje fałszywe trafienia typu „no”.

Wniosek dla projektu: zapytanie o postacie wpisu (1 zapytanie na 25 postaci, limit stron), wynik zapisany jako glosariusz serii i odświeżany tylko przy nowym sezonie. To pojedyncze, celowe zapytania, nie masowe zbieranie. Mieści się w regulaminie, ale plik glosariusza nie może stać się kopią bazy AniList (tylko nazwy, płeć i rola).

## 2. Glosariusze w tłumaczeniu (branża i LLM)

### Praktyka zawodowa: KNP

- Netflix, *Timed Text Style Guide: General Requirements*, §6 Consistency: „KNPs/formality tables must be created and used for translation to ensure consistency across episodes and seasons.” ([Netflix Partner Help](https://backlothelp.netflix.com/hc/en-us/articles/215758617)). Tabela formalności (kto do kogo per ty/pan) jest osobnym elementem obok nazw.
- Netflix, tłumaczenie tytułów: „Do not translate the main title from scratch: always use the approved title provided.” ([Main title and episode title translation](https://backlothelp.netflix.com/hc/en-us/articles/360000586227-Episode-Main-Title-Translation-in-Subs-and-Dubs)).
- Netflix, *Polish Timed Text Style Guide*, §4 Character Names: „Do not translate proper names (e.g. Peter, Suzanne), unless Netflix provides approved translations. Nicknames should only be translated if they convey a specific meaning.” Diakrytyki w nazwach własnych zachować ([Polish TTSG](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide)). Przewodnik nie wspomina o honoryfikatorach (przeszukałem tekst strony 2026-10-25).
- M. Campbell, *What Makes a Great KNP?* (ATA Audiovisual Division, 2022-12-21): kategorie wpisów (Person, Location, Organization, Term or Phrase), wpisy „NTBT” (not to be translated) z tą samą formą po obu stronach, noty o postaci („Jon — Kate's husband…”), uwaga, że glosariusz warto prowadzić nawet przy pracy w pojedynkę ([ATA AVD](https://www.ata-divisions.org/AVD/what-makes-a-great-knp/)).

### LLM: wskazówki w prompcie i pamięć nazw

- Ghazvininejad i in., *Dictionary-based Phrase-level Prompting of LLMs for MT* (arXiv 2302.07856, 2023): podanie w prompcie możliwych tłumaczeń wybranych słów (DiPMT) poprawia tłumaczenie rzadkich słów i domen spoza treningu ([arXiv](https://arxiv.org/abs/2302.07856)).
- Wang i in., *DelTA: An Online Document-Level Translation Agent Based on Multi-Level Memory* (arXiv 2410.08143, 2024): pamięć „Proper Noun Records” obok streszczenia i pamięci krótkiej i długiej podnosi spójność o 4,58 pp. i COMET o 3,16 pkt średnio na czterech LLM ([arXiv](https://arxiv.org/abs/2410.08143)). To bezpośredni odpowiednik „pamięci nazw między odcinkami”, z tym że DelTA aktualizuje rekordy osobnymi wywołaniami LLM, co kosztuje.
- Bogoychev i Chen, *Terminology-Aware Translation with Constrained Decoding and LLM Prompting* (WMT 2023, arXiv 2310.05824): poprawka LLM z ograniczeniami terminologicznymi zwiększa trafność terminów ([arXiv](https://arxiv.org/abs/2310.05824)).
- Semenov i in., *Findings of the WMT 2023 Shared Task on MT with Terminologies* ([ACL Anthology 2023.wmt-1.54](https://aclanthology.org/2023.wmt-1.54)):
  - **Term Success Rate**: porównanie terminów w wyniku ze słownikiem przez wyszukiwanie rozmyte z progiem 90%, wynik od 0 do 1 (§5, s. 666);
  - **Term Consistency**: czy ten sam termin źródłowy ma wszędzie to samo tłumaczenie, F1 względem pierwszego wystąpienia (§5, metoda Semenov i Bojar 2022);
  - główny wniosek: słownik poprawia jakość, ale podobny zysk daje tyle samo losowej informacji z referencji. Ogólne metryki mogą nie wyłapać różnicy. Wniosek dla nas: mierzyć terminy wprost, nie ogólną jakością.

### Pamięć podręczna promptu

OpenRouter, *Prompt Caching*: Gemini 2.5 i nowsze mają niejawny cache. Odczyt z cache kosztuje 0,25 ceny wejścia, TTL wynosi średnio 3–5 minut, a próg minimalny zależy od modelu (1024 tokeny dla Gemini 2.5 Flash). Trafienia daje stały początek promptu ([OpenRouter](https://openrouter.ai/docs/guides/best-practices/prompt-caching)). Dla Gemini 3.8 Flash progu nie znalazłem (założenie: działa podobnie). Wniosek: glosariusz wstawiać **po** stałych częściach (`system.md`, `translation.md`, styl), żeby nie psuć wspólnego prefiksu.

## 3. Polskie konwencje

### 3.1 Odmiana japońskich imion i nazwisk

- Poradnia PWN, *odmiana imion japońskich* (dr Jan Grzenia): „Imiona obce, również japońskie, odmieniamy w polszczyźnie tak jak imiona europejskie”, np. „o Akirze, dla Shina, z Kenjim”. Wyjątki: imion na `-u` nie odmieniamy; imiona na `-o` „odmieniać należałoby, ale ze świadomością ewentualnych komplikacji praktycznych”, zalecane co najmniej jedno użycie w mianowniku; na `-e` można odmieniać, „w razie wątpliwości lepiej od tego odstąpić” ([PWN](https://sjp.pwn.pl/poradnia/haslo/odmiana-imion-japonskich;9377.html)).
- Poradnia PWN, *odmiana nazwisk zakończonych na samogłoskę*: męskie na `-u` nieodmienne; na `-i`, `-e` odmiana przymiotnikowa (Verdi, Verdiego); na `-a` „odmieniają się zawsze” (Santana, Santany); obce na `-o` rzeczownikowo męsko (Caruso, Carusa) ([PWN](https://sjp.pwn.pl/poradnia/haslo/odmiana-nazwisk-zakonczonych-na-samogloske;5738.html)).
- Dobry Słownik, reguła 241: nazwiska kobiet zakończone na `-o` są zawsze nieodmienne („o pani Depo”) ([dobryslownik.pl](https://dobryslownik.pl/kompendium-regul-jezykowych/regula/123/); pełna treść reguły japońskiej jest płatna, odczytałem tylko część jawną).
- Wniosek dla przykładów z [evidence.md](evidence.md): `Hino` (mężczyzna) w bierniku według PWN to „Hina”, nie „Hinę”. Forma poprawna wygląda jednak jak imię żeńskie `Hina`, czyli to dokładnie ta „komplikacja praktyczna”. Dlatego reguła odmiany imion na `-o` jest decyzją właściciela.

### 3.2 Wołacz

- Narodowe Centrum Kultury, *Ojczysty – dodaj do ulubionych*, hasło „Wołacz”: odrębne formy wołacza są „zdecydowanie staranniejsze, ale w potocznej polszczyźnie można posługiwać się mianownikiem w funkcji wołacza”; pełne imiona częściej mają wołacz równy mianownikowi. „Wołacza nazwisk nie używamy.” ([NCK](https://nck.pl/projekty-kulturalne/projekty/ojczysty-dodaj-do-ulubionych/ciekawostki-jezykowe/wolacz))
- Wniosek: `Saikawo Yui` (wołacz nazwiska) narusza normę. `Nagiso` i `Nagisa!` są oba dopuszczalne, ale ich mieszanie między odcinkami nie. `Shizuko` jest regularnym wołaczem, który zmienia rozpoznawalne imię.

### 3.3 Zwroty grzecznościowe (`-san`, `-kun`, `-senpai`)

- Brak normy językowej. Netflix PL nie reguluje sufiksów (§2).
- Fansub: wątek *Sufiksy - jak wy podchodzicie do nich?* na forum AnimeSub.info (2005) pokazuje podział. Część tłumaczy zostawia sufiksy, część spolszcza („Niektóre można po prostu wyczyścić, inne trzeba spolszczyć dodając jakiś zwrot”), a jedna osoba zauważa, że sufiksy „stają się absurdalne przy naszych Kowalskich” ([AnimeSub.info](http://animesub.info/forum/viewtopic.php?pid=15442)). Źródło stare i opiniotwórcze, nie statystyka.
- Rascal.pl, *Jakość polskich wydań mangi…*: krytyka wycinania sufiksów, bo „ktoś przestaje dodawać sufiks do imienia, co jednocześnie jest punktem zwrotnym danej historii” ([Rascal.pl](https://rascal.pl/anime-manga-japonia/jakosc-polskich-wydan-mangi/)). To opinia jednego autora, ale dokładnie ten mechanizm widać w przykładzie 10–11 z [evidence.md](evidence.md).
- Źródła angielskie same się różnią: CR zostawia `-san`/`-kun` w napisach, NF w *Ao no Hako* pisze `Chinatsu Senpai` osobnym słowem, a w innych miejscach zamienia sufiksy na `Master`/`Lady` (*Kusuriya*). Polski wynik dziedziczy tę różnorodność, jeśli reguła nie mówi inaczej.
- Wynik wyszukiwarki bez otwarcia oryginału: wzmianki o zachowywaniu sufiksów w części wydań Waneko i JPF. Nie potwierdziłem ich i nie opieram na nich wniosków.

### 3.4 Zapis imion

- Netflix PL: nie tłumaczyć imion; transliterować tylko nietypowe znaki z alfabetu łacińskiego, jeśli mylą. Japońskie imiona w napisach angielskich są już w transkrypcji Hepburna z długimi samogłoskami pisanymi `ou`/`uu` (CR: `Kentarou`, `Yuusuke`, `Gyokuyou`). Polski zapis powinien je przepisać bez zmian. Zmiana `Gyokuyou` → `Gyokuyo` i `Onsou` → `Onso` jest odstępstwem od źródła, nie normalizacją do żadnej normy.

## Sprzeczności i niewiadome

- Brak normy dla sufiksów: decyzja stylistyczna, nie fakt.
- Próg cache dla Gemini 3.8 Flash na OpenRouter: nieznany. Wpływ na koszt glosariusza jest mały w każdym wariancie (§ koszt w [specification.md](specification.md)).
- Czy gender w AniList może ujawnić spoiler (postać ukrywająca płeć): możliwe, nie znalazłem przypadku w próbce. Ryzyko odnotowane w specyfikacji.

## Źródła (dostęp 2026-10-25)

- AniList API Docs: [Media](https://docs.anilist.co/reference/object/media), [Character](https://docs.anilist.co/reference/object/character), [CharacterName](https://docs.anilist.co/reference/object/charactername), [CharacterEdge](https://docs.anilist.co/reference/object/characteredge), [CharacterSort](https://docs.anilist.co/reference/enum/charactersort), [Rate Limiting](https://docs.anilist.co/guide/rate-limiting), [Pagination](https://docs.anilist.co/guide/graphql/pagination), [Terms of Use](https://docs.anilist.co/guide/terms-of-use), [Considerations](https://docs.anilist.co/guide/considerations)
- Netflix: [General Requirements](https://backlothelp.netflix.com/hc/en-us/articles/215758617), [Main/episode titles](https://backlothelp.netflix.com/hc/en-us/articles/360000586227-Episode-Main-Title-Translation-in-Subs-and-Dubs), [Polish TTSG](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide)
- [ATA AVD: What Makes a Great KNP?](https://www.ata-divisions.org/AVD/what-makes-a-great-knp/)
- [arXiv 2302.07856](https://arxiv.org/abs/2302.07856), [arXiv 2410.08143](https://arxiv.org/abs/2410.08143), [arXiv 2310.05824](https://arxiv.org/abs/2310.05824), [WMT 2023 Terminology Findings](https://aclanthology.org/2023.wmt-1.54)
- [OpenRouter: Prompt Caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
- PWN: [odmiana imion japońskich](https://sjp.pwn.pl/poradnia/haslo/odmiana-imion-japonskich;9377.html), [odmiana nazwisk zakończonych na samogłoskę](https://sjp.pwn.pl/poradnia/haslo/odmiana-nazwisk-zakonczonych-na-samogloske;5738.html); [Dobry Słownik, reguła 241](https://dobryslownik.pl/kompendium-regul-jezykowych/regula/123/); [NCK: Wołacz](https://nck.pl/projekty-kulturalne/projekty/ojczysty-dodaj-do-ulubionych/ciekawostki-jezykowe/wolacz)
- [AnimeSub.info: Sufiksy](http://animesub.info/forum/viewtopic.php?pid=15442), [Rascal.pl](https://rascal.pl/anime-manga-japonia/jakosc-polskich-wydan-mangi/)
