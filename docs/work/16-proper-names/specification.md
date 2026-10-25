---
kind: specification
status: draft, czeka na decyzje właściciela
updated: 2026-10-25
---

# Specyfikacja: glosariusz serii i reguły nazw własnych

## Cel

Polskie tłumaczenie LLM zachowuje pisownię imion ze źródła, stosuje jedną regułę zwrotów grzecznościowych i wołacza, odmienia imiona zgodnie z płcią postaci i trzyma te same formy we wszystkich odcinkach serii.

## Użytkownik i intencja

Właściciel ogląda odcinki z napisami i lektorem AniShift. Chce, żeby nazwy i sposób zwracania się były poprawne i spójne bez ręcznej korekty każdego odcinka, a gdy coś jest źle, żeby wystarczyło raz poprawić wpis dla całej serii. Uzasadnienie i odrzucone drogi: [intent.md](intent.md).

## Stan wyjściowy

- Model dostaje cały plik napisów w jednym żądaniu, bez tytułu, postaci i poprzednich odcinków ([evidence.md](evidence.md) §1).
- `translation.md:20-33` i `system.md:11` obiecują glosariusz „dostarczony przez aplikację”, którego aplikacja nie dostarcza.
- Prompt nie ma reguły zwrotów grzecznościowych ani wołacza.
- `services/catalog/anilist.py` nie pobiera postaci.
- 17 udokumentowanych błędów w czterech klasach: pisownia, spójność między odcinkami, sufiksy, odmiana i płeć ([evidence.md](evidence.md) §3).

## Ustalenia

- Glosariusz jest jeden na całą serię i jest powiązany z tytułem z AniList (właściciel, 2026-10-17, [masterplan 10-quality](../10-quality/masterplan.md)). Skutek: kluczem jest identyfikator AniList, nie nazwa pliku.
- Cel tłumaczenia pozostaje polski, a `translation` nadal nie importuje `services.llm` ani `services.catalog` (`services/translation/AGENTS.md`, „Decyzje”). Skutek: glosariusz przechodzi do silnika jako wartość domenowa translation, a AniList i pliki obsługuje warstwa aplikacji.
- Prompty pozostają zasobami pakietu ładowanymi przez `PromptLoader`, bez treści zapasowej w stałych (`engines/llm/AGENTS.md`, „Prompty”).

## Wymagania funkcjonalne

### Glosariusz: zawartość i format

- G1. Glosariusz serii to plik JSON `config/glossaries/<anilist_id>.json`, gdzie `anilist_id` to identyfikator klucza serii (D6).
- G2. Plik zawiera tytuły serii z AniList (romaji, angielski), listę identyfikatorów wpisów AniList, z których pobrano postacie, listę tytułów z nazw plików, które już do tej serii przypisano (`file_titles`), oraz listę wpisów.
- G3. Wpis ma pola: `source` (forma w napisach źródłowych), `aliases` (inne formy tej samej postaci: imię, nazwisko, alias), `pl` (forma polska, domyślnie równa `source`), `gender` (`m`, `f` albo pusty), `inflect` (`true`, `false` albo brak = reguła ogólna), `note` (opcjonalny tekst dla modelu), `origin` (`anilist` albo `owner`), `skip` (`true` wyłącza wpis bez usuwania).
- G4. Z AniList trafiają wyłącznie: imiona z `full`, `first`, `last`, `alternative`, płeć i rola. Nigdy `alternativeSpoiler`, opis, wiek ani obrazy.
- G5. Płeć `Male` → `m`, `Female` → `f`, każda inna wartość lub brak → pusty.

### Glosariusz: powstawanie i spójność

- G6. Przy tłumaczeniu pliku, którego seria jest rozpoznana (D5), aplikacja wczytuje glosariusz. Gdy plik nie istnieje albo bieżący wpis AniList nie jest na liście źródeł, pobiera postacie tego wpisu i dopisuje brakujące pozycje.
- G7. Dopisywanie nigdy nie zmienia ani nie usuwa istniejącego wpisu. Skutek: ręczna poprawka właściciela i wpis z `skip: true` przetrwają każde odświeżenie.
- G8. Pobranie postaci jest ograniczone do stałej liczby stron na wpis (25 postaci na stronę).
- G9. Błąd AniList, brak sieci albo uszkodzony plik nie przerywa tłumaczenia: plik tłumaczy się bez glosariusza (ewentualnie z dotychczasowym plikiem), a log zawiera kod błędu bez nazw i treści.
- G10. Zapis pliku jest atomowy (zapis do pliku tymczasowego i podmiana), w UTF-8. Tuż przed zapisem aplikacja wczytuje plik ponownie i dopisuje brakujące wpisy do świeżej treści. Skutek: ręczna edycja właściciela zrobiona w trakcie pobierania z AniList nie ginie.
- G11. Rozpoznanie serii pliku spoza stanu ownera (D5 b) najpierw szuka tytułu z nazwy pliku w `file_titles` istniejących glosariuszy. Dopiero brak trafienia wywołuje wyszukiwanie AniList. Skutek: kolejne odcinki znanej serii nie wysyłają zapytań.
- G12. Wyszukiwanie dla sezonu wyższego niż 1 używa najpierw tytułu z dopiskiem sezonu („<tytuł> Season <n>”), potem samego tytułu, żeby trafić we wpis sezonu, a nie pierwszej serii.

### Wstrzyknięcie do promptu

- P1. Do żądania trafiają tylko wpisy bez `skip`, których `source` albo któryś alias występuje w tekstach tej partii jako całe słowo lub fraza, w zapisie dokładnym albo wielkimi literami (szyldy typu `MIZAR`). Inne warianty wielkości liter się nie liczą, żeby imiona będące zwykłymi słowami (`White`, `Gray`, `Hel`, `Luna`) nie trafiały przez małe litery.
- P2. Lista trafia jako osobna część użytkownika po stylu, a przed numerowanymi liniami. Treść instrukcji leży w nowym zasobie `prompts/glossary.md` z jednym tokenem miejsca na listę.
- P3. Bez pasujących wpisów żądanie ma dokładnie dzisiejsze trzy części (zgodność z istniejącymi testami i zachowaniem).
- P4. Partia podzielona na połowy (limit kontekstu lub wyjścia) i żądanie naprawy kontraktu dostają glosariusz przefiltrowany według własnych tekstów.
- P5. Jedna linia wpisu w prompcie zawiera formę polską, aliasy występujące w partii, płeć, regułę odmiany i notę. Dokładny zapis ustala `prompts/glossary.md`.
- P6. Google i DeepL ignorują glosariusz.

### Reguły promptu (nazwy własne)

- R1. `translation.md` dostaje sekcję o nazwach własnych w napisach anime, która mówi:
  - pisownię imion i nazw przepisuj ze źródła litera w literę, także długie samogłoski (`ou`, `uu`), chyba że glosariusz podaje inną formę `pl`;
  - zwroty grzecznościowe według decyzji D1, jednakowo w całej partii;
  - wołacz według decyzji D2; wołacza nazwisk nie używaj;
  - imiona odmieniaj według płci z glosariusza i reguł z D3; gdy płeć jest nieznana, nie zgaduj jej z imienia;
  - gdy kwestia mówi o samym imieniu, sufiksie albo sposobie zwracania się, zachowaj tę różnicę w tłumaczeniu;
  - nie zastępuj imienia opisem ani innym imieniem.
- R2. Istniejące przykłady w `translation.md:20-33` zostają. Zdanie o „profilu tytułu” zostaje, bo aplikacja zaczyna dostarczać część tej informacji.
- R3. Plansza tytułowa i wzmianki o tytule serii według D4.

### Pomiar

- M1. Skrypt pomiarowy porównuje angielskie napisy źródłowe z polskim wynikiem dla zestawu odcinków i glosariusza referencyjnego, bez wywołań sieciowych.
- M2. Miara trafności nazw (odpowiednik Term Success Rate z WMT 2023): odsetek wystąpień wpisów glosariusza referencyjnego w linii źródła, dla których sparowana linia polska zawiera formę tego wpisu. Forma jest zgodna, gdy wyraz polski:
  - dla `pl` zakończonego na `-a` zaczyna się od `pl` bez tego `-a` (`Rebecca` → `Rebeccę`, `Rebeccą`); przy `-ka`, `-ga`, `-ta`, `-da` dopuszcza też polskie oboczności celownika i miejscownika: `-ce`, `-dze`, `-cie`, `-dzie` (`Yumeka` → `Yumece`, `Momoka` → `Momoce`, `Nishida` → `Nishidzie`);
  - wyrazy z łącznikiem (`Shindo-senpaia`) dzieli na części; część z sufiksem ocenia M4, nie M2;
  - dla `pl` nieodmiennego (wpis `inflect: false` albo zakończenie objęte nieodmiennością w D3) równa się `pl`;
  - w pozostałych przypadkach zaczyna się od całego `pl` (`Tani` → `Taniego`).
  Ta reguła odrzuca `Gyokuyo`, `Onso`, `Hinę`, `Rebeki` i `Hagasegawa` z [evidence.md](evidence.md). Wersja „`pl` bez dowolnej końcowej samogłoski” przepuszczała trzy pierwsze, więc jest zakazana ([reviews/round-1.md](reviews/round-1.md), F1). Wynik M2 podaje się osobno dla wpisów z AniList i dla wpisów dopisanych ręcznie do glosariusza referencyjnego: te drugie produkt w tym etapie zna tylko przez reguły R1.
- M3. Miara spójności (odpowiednik Term Consistency): dla każdego wpisu i serii liczba różnych form polskich (po regule z M2) użytych w całej serii; cel wynosi 1.
- M4. Miara zgodności z regułami: odsetek wystąpień sufiksów w źródle, potraktowanych zgodnie z D1, oraz liczba wołaczy niezgodnych z D2 (dla D2 a: forma `pl` bez `-a` plus `-o` przy imionach na `-a`, np. `Nagiso`, `Amelio`, `Shizuko`; zawsze: wołacz nazwiska, np. `Saikawo`).
- M5. Lista kontrolna: 17 przypadków z [evidence.md](evidence.md) §3 wypisana jako para linii przed i po, do oceny człowieka. Przypadek jest wskazany odcinkiem, czasem startu i tekstem źródła, nie numerem linii w starym pliku `ready/`, bo nowe przebiegi mają inne pliki.
- M6. Raport zawiera też liczbę naprawionych kontraktów (`response_contract` retry), liczbę nieprzetłumaczonych linii i rozmiar wejścia w znakach przed i po.

## Wymagania jakościowe

- Q1. Przyrost wejścia na żądanie wynosi nie więcej niż rozmiar przefiltrowanej listy plus zasób `glossary.md`. Szacunek: 10–25 wpisów po 60–90 znaków, około 1 KB instrukcji, łącznie 2–3,5 KB, czyli 4–7% obecnego żądania (stałe prompty 39 KB plus mediana odcinka 13 KB). Wyjście bez zmian.
- Q2. Stała część promptu (system, `translation.md`, styl) jest identyczna między żądaniami, więc glosariusz nie psuje cache prefiksu ([research.md](research.md) §2).
- Q3. Zapytania AniList tylko dla nowego tytułu z nazwy pliku albo nowego wpisu sezonu: wyszukiwanie (najwyżej 2, G12), graf franczyzy (najwyżej 4, D6 b) i postacie (najwyżej limit stron). Znana seria i znany sezon: zero zapytań.
- Q4. Logi zawierają liczby (wpisy, trafienia, strony), nigdy nazw postaci, treści napisów ani ścieżek absolutnych.

## Inwarianty

- I1. Kontrakt numerowanych linii (`line_contract.py`) bez zmian.
- I2. Bez glosariusza i z regułami R1 zachowanie silnika różni się tylko treścią `translation.md`.
- I3. Ręczne wpisy właściciela nigdy nie są nadpisywane przez automat.
- I4. Stan ownera (`config/watch/state.json`) jest dla glosariusza tylko do odczytu, przez istniejące API wczytania stanu.

## Ograniczenia

- AniList: 30 zapytań na minutę w stanie obniżonym, zakaz masowego zbierania ([research.md](research.md) §1).
- Windows-only, Python 3.14, zależności tylko istniejące (`httpx`, stdlib `json`).
- Pomiar przed i po wymaga płatnych wywołań OpenRouter: decyzja D7.

## Zakazane

- Zmiana stylów w `prompts/styles/`.
- Glosariusz dla Google/DeepL.
- Interfejs edycji glosariusza w panelu.
- Automatyczne wyciąganie terminów z poprzednich odcinków osobnym wywołaniem LLM (etap późniejszy).
- Zapis glosariusza w `workspace/` lub w repo.
- Wołanie AniList przy każdym odcinku, gdy wpis jest już na liście źródeł.

## Zakres

- Pobieranie postaci w `services/catalog/anilist.py`.
- Wartość glosariusza w `services/translation/` i jego wstrzyknięcie w silniku LLM.
- Rozpoznanie serii, plik glosariusza i odświeżanie w `application/`.
- Reguły R1 w `translation.md` i nowy `prompts/glossary.md`.
- Skrypt pomiarowy w `scripts/subtitle_quality/` i wynik pomiaru w `docs/work/16-proper-names/outcomes/`.

## Poza zakresem

- Porównanie z Grokiem (`ideas.md` §1.1): osobny pomiar tym samym skryptem.
- Kontekst z innych języków napisów (`ideas.md` §1.1, `do zbadania`).
- Tabela formalności (kto do kogo per ty lub pan) poza tym, co wynika z D1.

## Odłożone

- Pamięć terminów spoza AniList (tytuły rang, techniki, miejsca, plansza tytułowa) zbierana z poprzednich odcinków. Powód: koszt dodatkowego wywołania i niepewny zysk, który ocenimy po pomiarze M2–M3 tego etapu. Do tego czasu właściciel dopisuje takie terminy ręcznie (`origin: owner`).

## Odrzucone

- Klucz z nazwy pliku: ta sama seria ma w `ready/` dwie nazwy ([intent.md](intent.md)).
- Pełna lista postaci w każdym żądaniu: koszt i spoilery.
- Para EN/PL poprzedniego odcinka w kontekście: koszt rzędu całego odcinka.

## Warunki sukcesu

- S1. Na zestawie pomiarowym (plan, faza 1) miara M2 dla wpisów z AniList po zmianie jest wyższa niż przed, w każdym z dwóch przebiegów. M2 dla wpisów ręcznych raportujemy bez progu.
- S2. M3: dla żadnego wpisu glosariusza referencyjnego liczba tematów w serii nie rośnie, a dla wpisów z przykładów 1–9 z [evidence.md](evidence.md) wynosi 1.
- S3. M4 po zmianie jest wyższa niż przed w każdym przebiegu.
- S4. Właściciel ocenia listę M5: żaden przypadek nie jest gorszy niż przed, a ocenę „lepiej” wydaje on, nie skrypt.
- S5. M6: liczba napraw kontraktu i nieprzetłumaczonych linii nie rośnie względem bazowego przebiegu ponad różnicę między dwoma przebiegami bazowymi, a przyrost wejścia mieści się w Q1.
- S6. Bramki repo zielone (`ruff check`, `ruff format --check`, `mypy anishift/ tests/`, `pytest`).

## Decyzje właściciela

Każda z rekomendacją. Wybór zmienia treść R1, M4 albo zakres.

- **D1. Zwroty grzecznościowe.** (a) przepisywać dokładnie jak w źródle angielskim: gdy źródło ma `Nishi-san`, polski też, gdy źródło go nie ma, polski też nie; imię z sufiksem jest nieodmienne w całości (`z Rebecca-senpai`); (b) zamieniać na polskie formy („pan Jinshi”, „panna Shizuka”) albo pomijać; (c) usuwać zawsze. **Rekomendacja: (a).** Najprostsza reguła, którą da się sprawdzić skryptem; zachowuje sceny, w których zmiana sufiksu jest treścią (przykłady 10–11), i dziedziczy decyzję wydawcy angielskiego, który zna oryginał. Koszt: lektor czyta „san” na głos. Nieodmienność usuwa hybrydy typu `Lydio-senpai` i `Shindo-senpaia`. Tytuły, które źródło już przetłumaczyło (`Master Jinshi`, `Lady Lufas`), tłumaczymy po polsku i konsekwentnie („pan Jinshi”, „pani Lufas”).
- **D2. Wołacz imion obcych.** (a) mianownik w funkcji wołacza (`Nagisa!`, `Amelia, otwórz`); (b) polski wołacz (`Nagiso!`, `Amelio`). W obu wariantach bez wołacza nazwisk. **Rekomendacja: (a).** Norma dopuszcza go w mowie potocznej (NCK), nie tworzy innych imion (`Shizuko`), a lektor czyta formę, którą widz zna. Koszt: mniej staranna polszczyzna w scenach formalnych.
- **D3. Odmiana japońskich imion.** (a) według PWN: odmieniać, bez imion na `-u` i nazwisk kobiet na spółgłoskę lub `-i`, a imiona na `-o` odmieniać rzeczownikowo (`Hino`, `Hina`, `Hinowi`); (b) jak (a), ale imiona i nazwiska na `-o` i `-e` zostawiać nieodmienne. **Rekomendacja: (b).** PWN sam ostrzega przed komplikacją przy `-o`, a forma `Hina` zmienia płeć imienia w odbiorze widza i lektora. Właściciel może wymusić odmianę pojedynczego imienia polem `inflect: true`.
- **D4. Tytuł serii (plansza i wzmianki).** (a) zostawić tytuł źródłowy (oficjalny angielski); (b) jedno polskie tłumaczenie zapisane w glosariuszu jako wpis właściciela. **Rekomendacja: (a)** domyślnie, bo nie ma zatwierdzonego polskiego tytułu i Netflix zabrania tłumaczyć tytuł „from scratch”. Właściciel może wpisać polski tytuł ręcznie i wtedy obowiązuje on wszędzie.
- **D5. Rozpoznanie serii.** (a) tylko pliki pobrane przez AniShift (identyfikator ze stanu ownera); (b) dodatkowo pliki wrzucone ręcznie: tytuł z nazwy pliku (`library_label`) i wyszukiwanie AniList, z dopasowaniem zapisanym w pliku glosariusza, żeby było widać, co wybrano. **Rekomendacja: (b).** W `ready/` są serie bez subskrypcji. Ryzyko złego dopasowania jest widoczne i poprawialne przez usunięcie pliku glosariusza. Decyzja z 2026-10-17 mówi „powiązany z subskrypcją”, więc (b) ją rozszerza i wymaga zgody.
- **D6. Klucz serii.** (a) wpis AniList bieżącego sezonu; (b) pierwszy wpis franczyzy (korzeń łańcucha prequeli, już liczony przez `graph_prequels`), z dopisywaniem postaci każdego kolejnego sezonu. **Rekomendacja: (b)**, bo zgadza się z ustaleniem „jeden na całą serię” i zachowuje poprawki właściciela między sezonami. Koszt: do 4 zapytań grafu raz na serię.
- **D7. Płatny pomiar.** Zestaw 15 odcinków, dwa przebiegi przed i dwa po, czyli 60 żądań OpenRouter `google/gemini-3.8-flash` ze stylem `funny`. Opcjonalnie trzeci wariant „reguły R1 bez glosariusza” (jeden przebieg, 15 żądań), który rozdziela wpływ reguł od wpływu glosariusza i rozstrzyga, czy glosariusz jest wart swojej złożoności. Wariant oszczędny: po jednym przebiegu przed i po (30 żądań), ze słabszym rozróżnieniem szumu od efektu. **Rekomendacja: dwa przebiegi przed i po plus wariant R1 (75 żądań).** Ceny nie podaję, bo jej nie sprawdzałem; właściciel zna swój rachunek.
- **D8. Edycja glosariusza.** Ręcznie w pliku JSON w `config/glossaries/`. **Rekomendacja: tak w tym etapie**; panel później, jeśli ręczna edycja okaże się częsta.

## Nierozstrzygnięte

- Czy `group_id` zadania tłumaczenia da się jednoznacznie powiązać z przypisaniem w stanie ownera (`acquisition.assignments[].group_id`). Sprawdza to faza 0 planu; od wyniku zależy, jak wygląda D5 (a).
- Czy płeć z AniList może zdradzić spoiler w pojedynczych seriach. Nie znaleziono przypadku; wpis `skip` lub poprawiona płeć to obejście.
