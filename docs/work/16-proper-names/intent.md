---
kind: intent
status: propozycja do akceptacji właściciela
updated: 2026-10-25
---

# Intencja: nazwy własne i prompty tłumaczenia

## Problem i potrzeba

Właściciel ogląda anime z polskimi napisami i lektorem, które AniShift tłumaczy z angielskich napisów przez LLM (dziś najlepiej wypada `google/gemini-3.8-flash` przez OpenRouter, styl `funny`). Pozycja „Nazwy własne i prompty” w [`docs/ideas.md`](../../ideas.md) §1.1 ma status `teraz`.

Dowody z `workspace/ready/` ([evidence.md](evidence.md)) pokazują, że problem nie polega na tym, że model tłumaczy imiona. Prawie wszystkie zostawia. Psują się cztery rzeczy:

1. **Pisownia**: model gubi lub przestawia litery imienia (`Onsou` → `Onso`, `Gyokuyou` → `Gyokuyo`, `Hasegawa` → `Hagasegawa`) albo spolszcza je w jednym odcinku i zostawia w drugim (`Rebeki` obok `Rebeccę`).
2. **Spójność między odcinkami**: każdy odcinek tłumaczy się w osobnym żądaniu, bez pamięci serii. Ten sam tytuł serii dostaje w trzech kolejnych odcinkach trzy różne wersje, a ten sam zwrot grzecznościowy raz zostaje, raz staje się „panem”, raz znika.
3. **Zwroty grzecznościowe i zwracanie się do postaci**: prompt nie ma o nich żadnej reguły. Gdy fabuła dotyczy samej zmiany sufiksu („Nishi-san” → „Natsumi-chan”), polska wersja traci sens.
4. **Odmiana i płeć**: wołacz zmienia imię na inne japońskie imię (`Shizuka` → `Shizuko`) albo jest użyty przy nazwisku (`Saikawo`), a męskie nazwisko dostaje odmianę żeńską (`Hino` → `Hinę`), bo model nie zna płci postaci.

Potrzeba: polskie napisy, w których imiona, tytuły i sposób zwracania się są poprawne i takie same w całej serii, bez ręcznej korekty każdego odcinka.

## Kierunek

Rekomendacja: **glosariusz serii plus kilka reguł promptu**.

- Glosariusz jest jeden dla serii, powstaje sam z postaci AniList przy pierwszym tłumaczeniu odcinka i leży w pliku, który właściciel może poprawić ręcznie. Do żądania trafiają tylko pozycje, których imię występuje w tłumaczonym tekście.
- Prompt dostaje krótką sekcję o nazwach własnych: pisownia jak w źródle, jedna reguła zwrotów grzecznościowych, jedna reguła wołacza, zachowanie różnic w zwracaniu się, gdy kwestia o nich mówi.
- Poprawę mierzymy przed i po na tych samych odcinkach, tym samym modelem i stylem, skryptem porównującym źródło z wynikiem, a przypadki jakościowe ocenia właściciel.

Dlaczego tak: glosariusz (w branży KNP, „key names and phrases”) to standardowe narzędzie spójności między odcinkami u profesjonalnych tłumaczy ([research.md](research.md) §2), a AniShift już zna AniList i ma w promptach miejsce na „jawny glosariusz” (`prompts/system.md:11`, `prompts/translation.md:20-33`), którego aplikacja nigdy nie dostarcza.

## Granice

- Glosariusz obejmuje postacie z AniList i ręczne wpisy właściciela. Automatyczne zapamiętywanie terminów spoza AniList (techniki, miejsca, tytuły rang) z poprzednich odcinków to osobny, późniejszy etap. Jego wartość ocenimy dopiero po pomiarze pierwszego.
- Tylko silnik LLM. Google i DeepL nie dostają glosariusza.
- Bez interfejsu do edycji glosariusza w panelu; plik JSON w `config/`.
- Bez zmiany stylów (`funny`, `neutral` i innych) i bez przebudowy całego `translation.md`.

## Odrzucone drogi

- **Kontekst z poprzedniego odcinka (pełne pary EN/PL) w każdym żądaniu**: koszt rzędu całego odcinka na każde żądanie (mediana 13 KB źródła), a spójności nazw nie daje lepiej niż lista nazw.
- **Klucz glosariusza z nazwy pliku**: ta sama seria ma w `ready/` dwie nazwy (`The.Apothecary.Diaries.S03E01…` i `[Erai-raws] Kusuriya no Hitorigoto 3rd Season - 02…`), więc klucz z tytułu pliku rozdzieliłby jedną serię. Kluczem musi być identyfikator AniList.
- **Pełna lista postaci AniList w każdym żądaniu**: w serii bywa ponad 25 postaci, a w odcinku występuje ich kilka. Lista pełna kosztuje więcej i ujawnia postacie, które jeszcze się nie pojawiły.
- **Generowanie wszystkich form przypadków przez Morfeusza**: Morfeusz w repo (`anishift/text/morphology.py`) zwraca dla `Hino`, `Gyokuyou`, `Rebecca`, `Nagisa`, `Yamada` i `Hinę` tylko znacznik `ign`, czyli wyraz nieznany (sprawdzone 2026-10-25). Formy dobiera LLM, a glosariusz podaje mu płeć i regułę odmiany.

## Nierozstrzygnięte

Decyzje właściciela, z rekomendacjami, są w [specification.md](specification.md) w sekcji „Decyzje właściciela”. Najważniejsze: czy zachowywać japońskie sufiksy, czy w wołaczu używać mianownika i czy glosariusz ma działać także dla plików spoza subskrypcji.

## Stan uzgodnienia

Propozycja. Właściciel 2026-10-17 odłożył glosariusz postaci z warunkiem „jeśli wróci, to jeden na całą serię, powiązany z subskrypcją” ([masterplan 10-quality](../10-quality/masterplan.md), „Poza tym planem”). `ideas.md` przywraca go jako `teraz`. Kierunek wymaga akceptacji przed realizacją [plan.md](plan.md).
