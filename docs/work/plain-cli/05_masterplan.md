# 05 — Masterplan

Mapa etapu 05. Wymagania: `05_settings_and_progress.md`.

Dokument opisuje stany, przez które przechodzimy, i który budujemy teraz. Nie
zawiera szczegółów implementacji przyszłych etapów — te powstają dopiero na
aktualnym baseline.

## Cel końcowy

Panel ustawień czyta widoczność, etykiety, grupy i zakresy z katalogu pól,
udostępnia pięć brakujących pokręteł jakości, obsługuje się strzałkami i
przewija. Widok Auto pokazuje maskotkę i całą kolejkę, z przyklejonym nagłówkiem
i stopką. Wszystko w jednym rendererze, bez viewportu.

## Stan wyjściowy

Zweryfikowany na `4b03ce2`. Panel ma trzy poziomy i działa, ale widoczność pól
jest zduplikowana w hard-coded krotkach, liczby edytuje się tylko wpisywaniem,
okno listy jest funkcją kursora i kosztuje `O(n³)` na klatkę, maskotka jest w
Auto wyłączona na sztywno, a nadmiar wierszy kolejki jest cicho ucinany.

Baseline testów: 47 nieprzechodzących i 2 błędy zbierania, stan zastany,
niezwiązany z tym etapem.

---

## E1 — Układ panelu wiązany z katalogiem

- **cel:** jedna struktura układu w warstwie CLI opisuje kategorię, sekcję,
  kolejność i polski tekst każdego pola; test kompletności gwarantuje, że każde
  pole edytowalne w katalogu występuje w układzie dokładnie raz
- **powód:** dziś widoczność jest zduplikowana bez żadnego sygnału o rozjeździe,
  co już raz spowodowało trwałą lukę — `elevenbytes_custom_voices` ma pełny
  kontrakt w katalogu i nie istnieje w panelu
- **wejście:** obecny `settings.py`, `field_catalog.py`, `field_access.py`
- **rezultat:** test wiążący układ z katalogiem, z jawną i opisaną listą pól
  świadomie obsługiwanych inną drogą; udokumentowana jedna realna luka
- **warunek wyjścia:** dodanie pola do katalogu bez dopisania go do układu albo do
  listy wyjątków wywala test, zamiast zniknąć po cichu
- **zależności:** brak, to fundament
- **ryzyko:** niskie po pomiarze; pierwotne założenie, że układ jest zepsuty, było
  fałszywe — zmierzono 55 pól w katalogu, 35 w układzie, 9 poprawnie nieaktywnych,
  5 celowo obsługiwanych inaczej i 1 realną lukę, więc etap sprowadza się do
  postawienia strażnika, nie do przebudowy
- **status:** current

Uwaga do zakresu: pierwotnie ten etap miał zastąpić trzy krotki jedną strukturą i
przenieść polskie teksty do katalogu. Pomiar i weryfikacja `SettingSpec` unieważniły
oba pomysły — struktura układu już istnieje w dobrym kształcie
(`_SettingField = (setting_id, etykieta, sekcja)`), a `label`/`description` w
katalogu są celowo UI-neutralne po angielsku. Etap zmniejszył się do strażnika.

## E2 — Interakcja: strzałki, przewijanie, Cofnij

- **cel:** `←→` zmieniają liczby i przechodzą po wyborach, `PageUp`/`PageDown`/
  `Home`/`End` działają, lista ma stan przewijania niezależny od kursora, wiersz
  `Cofnij` jest zawsze widoczny, kółko myszy przewija
- **powód:** to jest sedno prośby o ergonomię; bez tego panel pozostaje
  formularzem do wpisywania
- **wejście:** E1 zaakceptowane, bo krok i zakres pochodzą z `SettingSpec`
- **rezultat:** nawigacja po długiej liście bez opuszczania kursora z widoku,
  regulacja liczb bez wpisywania, wyznaczanie okna liniowe
- **warunek wyjścia:** lista 22 pól obsługuje się bez wpisywania i bez gubienia
  kursora przy każdej wysokości terminala; `Cofnij` widoczny w każdej pozycji
  przewinięcia
- **zależności:** E1
- **ryzyko:** rozszerzenie kontraktu klawiszy dotyka jedynego właściciela
  interakcji, więc może wpłynąć na Home i Ręczny; klawisze specjalne na Windowsie
  przychodzą z pustym `data`, co wymaga bindingów per klawisz, nie przez `Any`
- **status:** planned

## E3 — Brakujące pokrętła jakości i trzy naprawy

- **cel:** pięć nowych pól z sekcji 3.5 wymagań oraz trzy naprawy defektów
- **powód:** to jedyny etap zmieniający jakość produktu, nie tylko jego obsługę
- **wejście:** E1 zaakceptowane; dodanie pola musi być zmianą w katalogu, nie w
  widoku
- **rezultat:** zakres czytania napisów, layout linii, rozmiar kontekstu
  tłumaczenia i własne głosy są edytowalne; kategoria `Napisy` powstaje razem z
  pierwszymi polami, które ma pomieścić; `OBJECT_LIST` zyskuje edytor, bo bez
  niego własne głosy pozostają nieosiągalne; cap backoffu, martwy sample rate i
  niespójne progi tolerancji naprawione
- **warunek wyjścia:** zmiana każdego nowego pola daje obserwowalnie inny wynik
  na tym samym pliku źródłowym
- **zależności:** E1
- **ryzyko:** pola INTENCJI wymagają zaprojektowania odwzorowania wybór → liczby;
  złe odwzorowanie jest gorsze niż brak pola, bo daje złudzenie kontroli
- **status:** planned

## E4 — Paleta maskotki w całym panelu

- **cel:** kolory z maskotki jako paleta interfejsu, rozdzielona od kolorów
  semantycznych
- **powód:** spójność wizualna jest celem samodzielnym, ale zależy od
  ostatecznego kształtu widoków z E2 i E3
- **wejście:** E2 i E3 zaakceptowane, bo malowanie widoku, który jeszcze się
  zmienia, to podwójna praca
- **rezultat:** jedna paleta prezentacji, akcent na aktywnym wierszu i markerze,
  stan zawsze czytelny bez koloru
- **warunek wyjścia:** ocena wzrokowa właściciela produktu na realnym terminalu
- **zależności:** E2, E3
- **ryzyko:** ocena estetyczna wymaga iteracji z człowiekiem, więc etap ma
  wbudowany punkt kontrolny, nie warunek automatyczny
- **status:** planned

## E5 — Auto: maskotka i przewijana kolejka

- **cel:** trzy regiony w widoku Auto — przyklejony nagłówek z maskotką,
  przewijana kolejka, przyklejona stopka
- **powód:** dziś przy 19 grupach część kolejki jest niewidoczna bez ostrzeżenia,
  a maskotka jest wyłączona stałą w kodzie
- **wejście:** E2 zaakceptowane, bo przewijanie kolejki używa tych samych
  klawiszy i tego samego mechanizmu offsetu
- **rezultat:** run 46 plików pokazuje markę, maskotkę, dowolny fragment kolejki
  i stopkę jednocześnie
- **warunek wyjścia:** realny run na pełnym workspace, przewijanie w trakcie
  pracy, maskotka nie wędruje i nie zostawia rastra
- **zależności:** E2
- **ryzyko:** największe w całym etapie — raster SIXEL nie da się przyciąć, więc
  maskotka nie może wejść w region przewijany; unieważnia zakaz przewijania
  pilnowany testami regresyjnymi, które trzeba przepisać razem z unieważnieniem
- **status:** planned

---

## Kolejność i jej powód

`E1 → E2 → {E3, E4} → E5`, przy czym E4 czeka na E3.

E1 jest pierwsze, bo jest fundamentem i największą niepewnością projektową: jeśli
katalog nie umie wyrazić grupy i kolejności, zmienia się kontrakt `SettingSpec`,
a to przeplanowuje E2 i E3.

E5 jest ostatnie, mimo że nosi największe ryzyko techniczne, bo jego
niepowodzenie **nie unieważnia** żadnego wcześniejszego etapu. Ryzyko jest
odizolowane na końcu, a nie rozlane na całość.

E3 i E4 są rozdzielone, bo pierwszy zmienia zachowanie produktu, a drugi jego
wygląd; mają osobne warunki akceptacji i osobne punkty kontrolne.

## Punkty kontrolne człowieka

- po E2 — ergonomia nawigacji na realnym terminalu
- po E4 — ocena wizualna palety
- po E5 — realny run na pełnym workspace

## Aktualizacja

Po każdym zaakceptowanym etapie: porównać stan z celem, sprawdzić, czy założenia
nadal obowiązują, zaktualizować status, wybrać następny etap. Materialna zmiana
kierunku zostaje zapisana z powodem. Historia należy do Gita, nie do kopii tego
pliku.
