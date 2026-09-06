# AniShift: wybieram anime, reszta dzieje się sama

## Po co to budujemy

Auto już działa: z przygotowanego pliku otrzymujesz polskie napisy i lektora.
Kosztem są czynności wokół niego: znaleźć wydanie, wybrać odcinek, pobrać,
sprawdzić koniec, uruchomić program i odszukać wynik. Powtarzane codziennie
zabierają uwagę, nawet jeśli każda trwa chwilę.

Docelowo wskazujesz, co chcesz obejrzeć. AniShift sprawdza dostępność, przygotowuje
odcinek i pokazuje „Gotowe — oglądaj”. Jeśli wymaga decyzji, pyta konkretnie.
Nie musisz pilnować obróbki, ale możesz obserwować postęp.

To kierunek, nie lista wdrożonych funkcji. Kontrakt jest w
[specyfikacji](specification.md), kolejność w [masterplanie](masterplan.md).

## Funkcje, które zdejmują pracę z głowy

### Dodaj plik i nie pamiętaj o klikaniu Auto

Upuszczasz albo wklejasz ścieżkę do terminala. AniShift kopiuje plik,
zachowuje oryginał, pokazuje postęp i po zamknięciu kopii sam zaczyna Auto.
Ponowne dodanie tego samego materiału nie powinno tworzyć kolejnej pracy.

Osobnym rozszerzeniem jest obserwowanie folderu, do którego zapisują inne
programy. Tu trzeba odróżnić plik gotowy od częściowego. Własna kopia zna koniec;
obcy zapis nie daje takiej gwarancji przez sam chwilowo stały rozmiar.

### Wybierz odcinki, a pobieranie przejdzie w przygotowanie

Wybierasz odcinek lub podajesz magnet. AniShift korzysta z klienta pobierania
i przekazuje ukończony plik do tej samej kolejki co import. Pierwszy wycinek
może obsługiwać sam magnet; wyszukiwarka nie musi blokować pierwszego rezultatu.

Postęp odróżnia pobieranie, tłumaczenie, lektora i składanie. Niepewne wydanie
nie jest automatycznie pierwszym wynikiem wyszukiwania. Właściciel wybiera
źródła, do których ma prawo dostępu; aplikacja nie omija zabezpieczeń.

### Zapisz serię raz na sezon

Subskrypcja pamięta tytuł, sezon, odcinki i preferencje wydania. Sprawdza
dostępność okresowo — np. co godzinę, jeśli taki interwał wybierzesz.
Po pojawieniu się pasującego materiału przygotowuje go bez codziennego szukania.

Ważny detal: numer **następnego odcinka do zdobycia** jest pokazany wprost.
Nie liczysz ostatniego obejrzanego +1. Pobranie nie oznacza obejrzenia:
nie zapisujemy automatycznie fikcyjnej historii AniList/MyAnimeList.

### Jedna lista Gotowe i akcja Oglądaj

Katalog serii pokazuje rezultat już znany aplikacji: co czeka, co się robi,
co jest gotowe i co wymaga uwagi. To nie kolejny formularz do ręcznej aktualizacji.
„Oglądaj” uruchamia Twój mpv z właściwym produktem, bez budowania odtwarzacza.

Serie mogą być grupami wirtualnymi. Nie trzeba od razu zmieniać płaskiego
workspace ani przenosić torrentów. Fizyczne podfoldery to osobna decyzja.

### Serwer pracuje przy wyłączonym komputerze

Późniejszy worker VPS uruchamia ten sam rdzeń AniShift bez terminala.
Lokalny tryb nadal działa niezależnie. Subskrypcje i odzyskanie kolejki po restarcie
są tu istotne, bo nie ma człowieka patrzącego na każdy krok.

Przed wdrożeniem trzeba sprawdzić OS, dostępność TTS/modeli, CPU/RAM/dysk,
transfer, autoryzację, retencję i awarie. „Serwer bez limitu” jest założeniem
do weryfikacji, nie gwarancją. Nie obiecujemy materiału 4K ani gotowości każdego
anime natychmiast w chwili premiery.

### Gotowy odcinek dociera tam, gdzie oglądasz

Serwer może wysłać ukończony produkt np. do Google Drive. Następnie komputer
go synchronizuje albo oglądasz inną uzgodnioną drogą. Dostawca i sposób dostępu
pozostają do wyboru po sprawdzeniu ograniczeń.

Przerwany upload oznacza ponowienie transferu, nie tłumaczenia i lektora.
„Gotowe na serwerze” i „dostępne na komputerze” są różnymi stanami.
Nie kasujemy jedynej dobrej kopii ani nie wysyłamy konfiguracji z sekretami.

### Powiedz „chcę obejrzeć…”

Gdy operacje będą stabilne, rozmowa może przekładać prośbę na te same zlecenia
co terminal. Wyjaśnia dopasowanie, prosi o wybór i informuje o wyniku.
Nie dostaje dowolnej powłoki, kasowania plików ani prawa do naprawiania kodu
na działającym serwerze. AI ma uprościć obsługę, nie zastąpić reguły bezpieczeństwa.

## Jeden system, nie kilka trackerów

Import, watcher i downloader prowadzą do jednej historii zleceń:

```text
wybrany → oczekuje na dostępność → pobiera/kopiuje → przetwarza
        → gotowy lokalnie → opcjonalnie wysłany → dostępny do oglądania
```

Błąd jest stanem konkretnego kroku. „Obejrzany” nie wynika z żadnej strzałki.
Klient torrent nadal jest właścicielem transferu, a AniShift uzgadnia jego stan.
JSON/SQLite nie wybrano: potrzebujemy spójności i restartu, nie modnej nazwy bazy.

## Co odkładamy i czy to się opłaca

[Zaległości na GitHubie](README.md#odłożone-dopracowanie) nie są bramką wszystkich
nowych funkcji. Ustawienia, uproszczenie testów, pomiary, szerokie próby awarii,
trudny ASS i README wrócą, gdy będzie czas albo konkretny problem użytkowy.
Każda nowa funkcja nadal chroni źródła i ma proporcjonalne testy.

PyAV, nowy GUI, multi-voice, licznik kosztów i MAL/AniList nie są priorytetami.
TXT → audiobook pozostaje osobnym kierunkiem. Już działającego batch processing
i klasyfikatora nie traktujemy jako brakujących nowych funkcji.

Kontrolowany import ma mały koszt integracji i daje niewielką natychmiastową ulgę.
Subskrypcje są droższe, lecz usuwają najwięcej codziennej pracy. VPS/chmura zwiększają
niezależność od PC, dodając utrzymanie i rachunki. Rozmowa ma sens na gotowej podstawie.

Przed serwerem policzyć storage, transfer, CPU, API i czas utrzymania.
Nie podajemy fikcyjnej ceny ani terminu bez wybrania usług. Sukces mierzymy
liczbą ręcznych interwencji potrzebnych do obejrzenia odcinka, nie oceną „10/10”.

## Opinia Fable i ocena prowadzącego

Fable 5.1 przeczytał wcześniejszy pakiet i zalecił kontrolowaną kopię z historią
jako pierwszy krok. Trafnie rozdzielił watcher od potwierdzenia klienta pobierania.
Subiektywna opłacalność według niego: wspólna historia 9/10, import 8/10,
magnet 7/10, katalog/mpv 6/10, VPS/Drive 5/10, MAL/AniList 2/10.
To opinia o korzyści i koszcie, nie benchmark.

Przyjmuję wspólne intake i brak drugiego trackera. Nie przesądzam JSON ani nie
odkładam ochrony przed dwoma writerami: minimalny zapis/blokada należą do pierwszego
planu. Subskrypcje są docelowo kluczowe dla właściciela; ich większy koszt wejścia
nie powinien spychać ich za kolejne miesiące polerowania.
