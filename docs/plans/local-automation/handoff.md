---
kind: implementation-handoff
status: proposed
updated: 2026-09-05
baseline: bc74425b487fb9110da76911c26dca4194b2aad9
implementation: not-executed
language: pl
---

# AniShift | przekazanie planu agentowi implementującemu

## Polecenie wykonania

Zrealizuj pełny zakres lokalnej automatyzacji opisany w tym katalogu. Nie ograniczaj pracy do wklejenia magnetu lub samej wyszukiwarki. Nie wdrażaj VPS, chmury, pełnego MAL live sync, nowego UI ani drugiego pipeline. Zachowaj dotychczasowe Auto.

Ten plik jest instrukcją przyszłego wykonawcy. Samo przekazanie pakietu nie oznacza, że wykonano implementację lub że wolno zmieniać konta/system bez wymaganej zgody użytkownika.

## Czytanie

Najpierw spec.md, następnie brief.md i research.md. Potem masterplan.md: kontrakty 1–14, mapa faz i aktualna karta. Wczytaj AGENTS repo oraz obszarów przed edycją. Nie próbuj wczytać całego masterplanu na raz; otwieraj kontrakt i aktualną fazę po kotwicy.

Status zadania jest zapisywany wyłącznie w karcie masterplanu. Nie ma osobnego trackera ani eksportu do odtwarzania.

## Umieszczenie dokumentów

Skopiuj cały katalog pakietu do `docs/work/local-automation/`, zachowując nazwy plików i linki względne. Nie twórz osobnej spec-final ani drugiego masterplan-v2.

`baseline.md`, pliki `proofs/` oraz końcowy `outcomes/local-automation.md` powstają dopiero z rzeczywistego rozpoznania, prób i implementacji. Nie wypełniaj ich wcześniej zdaniami PASS lub gotowe.

## Początek

Zacznij od T001. Sprawdź HEAD względem `bc74425b487fb9110da76911c26dca4194b2aad9` oraz working tree. Zapisz istotne różnice. Nie resetuj/stashuj cudzych zmian i nie zakładaj, że gałąź o tej samej nazwie nadal ma ten sam kod.

Jedna gałąź i jeden PR na fazę: `feature/local-automation-p00`, `feature/local-automation-p01` i dalej, każda z aktualnego `main` po merge poprzedniej. Nie prowadź jednej gałęzi przez wszystkie fazy; bramki repo i review mają działać na porcji, którą da się przeczytać. Jeden integrator modyfikuje schemat, stany, mostek i UI. Czytające review może być delegowane, ale nie kilka równoległych writerów tej samej granicy.

T002–T005 to wczesne próby integracyjne, nie kosmetyka. Brak lokalnego Windows/klienta oznacz jako brak dowodu. Nie zastępuj go wynikiem Linux lub stubem. Nie uruchamiaj prywatnych odcinków ani istniejących aktywnych procesów właściciela.

## Pętla wykonania zadania

1. Otwórz kartę oraz wskazane pliki i instrukcje obszaru.
2. Potwierdź publiczne sygnatury i aktualny schemat, na których opiera się zmiana.
3. Dodaj właściwe scenariusze deterministyczne albo przygotuj konkretną próbę integracyjną.
4. Implementuj osiem kroków karty w opisanej kolejności, korzystając z istniejących modułów.
5. Uruchom targeted checks; odnotuj prawdziwe wyniki i ograniczenia środowiska.
6. Przed commitem wykonaj bramki root z instrukcji repo.
7. Zaktualizuj status karty i dowód; nie zmieniaj historycznego rezultatu bez wyjaśnienia.
8. Przejdź do kolejnego numeru albo zapisz konkretną blokadę i zależny zakres.

Karty mogą współdzielić jeden mały moduł. Nie twórz osobnego modułu produkcyjnego, frameworka lub publicznej klasy dla każdego numeru zadania. Symbole w kartach określają odpowiedzialność i kontrakt, nie nakaz sztucznego mnożenia obiektów.

## Co wolno dopasować lokalnie

Nazwy prywatnych helperów, dokładny podział małych funkcji, asercje i struktura fixture mogą zostać dostosowane do repo, jeżeli zachowują publiczny kontrakt oraz wszystkie scenariusze. Nie zmieniaj znaczenia persisted fields, źródła prawdy, polityki źródeł, identity/revision i scope bez aktualizacji masterplanu.

Różnica nazwy parametru wrappera wymaga aktualizacji adaptera oraz testu kontraktowego. Nie jest pretekstem do dodania drugiego klienta lub zignorowania metadata-only. Biblioteka niekompatybilna z Python 3.14 wymaga uzasadnionej konkretnej zamiany oraz odświeżenia locka i źródeł, nie twierdzenia, że „powinna działać”.

## Konfiguracja i zgody

Nie instaluj qBittorrent, nie włączaj WebUI, nie zmieniaj hasła, autostartu lub skojarzeń plików bez świadomej zgody przy wdrożeniu. Własny setup pokazuje podsumowanie zmian. Nie obiecuj obsługi dowolnego klienta o nazwie BitTorrent.

Nie czytaj prywatnych promptów, runtime logs z mediami, .env lub odcinków tylko do napisania testu. Korzystaj z syntetycznych materiałów oraz jawnie udostępnionej konfiguracji próbnej. Nie zabijaj działającego TTS/translatora użytkownika.

## Dowody

Test jednostkowy sprawdza czystą regułę. Test integracyjny sprawdza przejście przez DB, plik lub proces i może stubować sieć. Próba live sprawdza konkretną usługę/klienta. Próba Windows sprawdza platformę i logowanie. Odbiór manualny sprawdza ergonomię i odsłuch.

Każdy przypadek ma ID Txxx-Cyy. Nazwy testów w kartach są docelowe; można je połączyć w parametryzację i w jeden moduł na obszar, zachowując identyfikowalne przypadki. Cztery scenariusze na kartę to szablon generatora, nie wymóg: jeżeli scenariusz nie wnosi nowego ryzyka, połącz go z sąsiednim albo pomiń z adnotacją w karcie. Nie pomijamy negatywnego skutku wymienionego w karcie.

## Warunki zatrzymania

Brak dowodu bezpieczeństwa batch add, próba naruszenia własności źródeł, sekret w diagnostyce lub możliwość wykonania danych z sieci zatrzymują zależny kod. Nie wolno „naprawić” testu przez wyłączenie autoryzacji klienta albo globalne usuwanie plików.

Jeżeli nie ma możliwości wykonania próby platformowej, zakończ właściwą część z oznaczeniem unverified/pending-human i opisem brakującego dowodu. Nie ogłaszaj całego lokalnego wdrożenia ukończonym, gdy download lub autostart wciąż są wyłącznie zaprojektowane.

## Root gates

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Nie zmniejszaj zakresu pytest do samego `tests/`, jeśli konfiguracja repo obejmuje utils. Nie uruchamiaj pełnego suite po każdej kosmetycznej zmianie opisu; wymagane momenty wynikają z instrukcji repo i commitów implementacji.

## Gotowy wynik

T128 tworzy rzeczywisty outcome: SHA implementacji, spełnione przepływy, dokładne wyniki testów, zweryfikowana para klient/wrapper, zachowanie Windows, wynik odsłuchu oraz jawne ograniczenia. Publiczny raport nie zawiera credentials i prywatnych ścieżek właściciela.

Końcowa instrukcja użytkownika ma mówić, jak wyszukać, obserwować, wrzucić plik, otworzyć Bibliotekę i wyłączyć czuwanie. Nie przekazuj użytkownikowi obowiązku poznania całej wewnętrznej architektury, żeby obejrzeć odcinek.
