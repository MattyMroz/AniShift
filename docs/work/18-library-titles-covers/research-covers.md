---
kind: research
status: done
date: 2026-10-25
question: Jak pokazać okładki w panelu Prompt Toolkit na Windows, przy stałym wyglądzie panelu?
---

# Research: okładki w terminalu na Windows

## Pytanie i kryterium decyzji

Który mechanizm obrazu działa realnie w terminalu właściciela (Windows, panel Prompt Toolkit), ile kosztuje pobranie i
cache okładek z AniList i czy da się to pogodzić z regułą stałego wyglądu panelu.

Etykiety dowodu: **P** (źródło pierwotne), **W** (źródło wtórne), **R** (fakt z repo), **N** (nie ustalono).

## 1. Protokoły obrazów a Windows Terminal

| Wariant | Status w Windows Terminal | Dowód |
|---|---|---|
| Sixel | Działa od Terminal Preview 1.22 (blog z 27.08.2024); implementacja przez społecznego współautora j4james; do kodowania potrzebny enkoder (libsixel, chafa) | P: [blog Windows Terminal Preview 1.22](https://devblogs.microsoft.com/commandline/windows-terminal-preview-1-22-release); P: [PR #17421 „Add support for Sixel images in conhost”, scalony 01.07.2024](https://github.com/microsoft/terminal/pull/17421) |
| Sixel w stabilnej wersji | Neowin opisuje stabilne 1.22 z Sixel, blog wymienia 1.21 jako stabilne w dniu wpisu; wersja, od której stabilny kanał ma Sixel, jest rozbieżna | W: [Neowin](https://www.neowin.net/news/microsoft-updates-windows-terminal-with-new-multi-window-support-console-architecture-more/); N: dokładny numer do sprawdzenia w [notatkach wydania](https://github.com/microsoft/terminal/releases) |
| Kitty graphics protocol | Brak w wydaniu. Zgłoszenie [#8389](https://github.com/microsoft/terminal/issues/8389) jest otwarte w Backlogu; w pliku zgłoszenia maintainer pisze o eksperymentach (08.2026), a rozmowa jest zablokowana dla współpracowników. [#17309](https://github.com/microsoft/terminal/issues/17309) zamknięto jako duplikat | P (odczyt strony przez narzędzie; treść komentarzy nie weryfikowana niezależnie) |
| iTerm2 inline images (OSC 1337) | Nie znalazłem żadnego źródła o wsparciu w Windows Terminal | N: brak dowodu wsparcia; [dokumentacja protokołu iTerm2](https://iterm2.com/documentation-images.html) opisuje tylko iTerm2 |
| Sixel w VS Code | Wymaga `terminal.integrated.enableImages`; wg poradnika trzecich osób obsługiwane są Sixel i iTerm; uwaga o Windows niezweryfikowana | W: [Ultralytics: view results in terminal](https://docs.ultralytics.com/guides/view-results-in-terminal); R: `anishift/cli/AGENTS.md` („VS Code wymaga śledzonego `terminal.integrated.enableImages=true`”) |
| Półbloki ANSI (znak `▄` z kolorem pierwszego planu i tła) | Działa w każdym terminalu z truecolor; rozdzielczość 1 × 2 piksele na komórkę | W: [rich-pixels](https://pypi.org/project/rich-pixels/) (opis techniki: znak U+2584 z dwoma kolorami); R: `mascot.py:210-256` robi to samo dla maskotki bez SIXEL |

### Znane ograniczenia Sixel w Windows Terminal (z PR #17421)

- Obraz przewija się razem z tekstem, jest częścią bufora (P: opis PR).
- Pierwsza implementacja dotyczyła renderera GDI w conhost; Atlas/passthrough opisano jako jeszcze niestabilne (P: opis PR, stan z 2024).
- PR nie zawierał zapytań xterm o rozmiar komórki, na których polegają niektóre biblioteki (P: opis PR). AniShift
  nie zależy od tego, bo wysyła własne `CSI 16t`/`CSI 14t` i ma wartość domyślną 8 × 17 (R: `mascot_native.py:58`, `:206`).
- Autor PR stwierdza, że protokół Kitty jest zasadniczo niezgodny z modelem Sixel i wymagałby osobnej obsługi (P: opis PR).

### Wniosek z repo (najmocniejszy dowód)

AniShift już dziś wysyła natywny SIXEL w Prompt Toolkit na Windows: własny koder na Pillow
(`mascot_native.py:346-405`), sondę wsparcia (`:206`), kotwicę w ramce i rysowanie w `after_render`
(`prompts.py:325-389`), degradację do półbloków (`mascot.py`). Maskotka jest zatwierdzonym przez właściciela elementem
(`README.md:41`). To dowodzi, że ścieżka działa w terminalu właściciela; sam jej nie uruchomiłem (zakaz zlecenia), więc to jest
dowód z kodu i dokumentacji, nie z obserwacji.

## 2. Prompt Toolkit a obrazy

- Wyszukiwanie nie znalazło dokumentacji ani zgłoszeń o natywnym wsparciu obrazów w Prompt Toolkit (N).
  Wniosek ostrożny: nie ma wbudowanego widżetu obrazu.
- AniShift obchodzi to samodzielnie: ramka Rich → `ANSI` → Prompt Toolkit, a obraz zapisywany jest bezpośrednio do wyjścia
  w `after_render` po zapisaniu kursora (`prompts.py:363-380`). Rozmiar rezerwuje się w komórkach, a kasowanie
  nadpisuje komórki, bo `ECH` zostawia raster (R: `prompts.py` stałe `_ERASE_ROW`, `_CLEAR_SCREEN`).
- Konsekwencje dla okładek (R, `cli/AGENTS.md`):
  1. raster nie przycina się do okna listy, więc okładka musi stać w stałym miejscu poza przewijanym obszarem;
  2. zmiana położenia lub zniknięcie rastra wymusza `reset` + `\x1b[2J`, a zmiana samej zawartości w tym samym miejscu nie;
  3. `_fit_frame` obcina każdy wiersz do szerokości terminala, więc kotwica musi mieścić się w szerokości.

## 3. AniList: pola, limity, koszt

- **Pole obrazu.** Zapytanie Media może żądać `coverImage { extraLarge large medium color }` (W: [animedex, szablon zapytania](https://animedex.readthedocs.io/en/latest/api_doc/backends/anilist/_queries.html)).
  Oficjalnej strony ze schematem nie odczytałem (N: potwierdzić w GraphiQL). Rozmiary w pikselach, format pliku i host CDN
  (`s4.anilist.co` wg [opisu wtyczki trzeciej strony](https://noctalia.dev/plugins/community/anilist)) są niepotwierdzone (N); mierzy je faza 0 planu.
- **Limit zapytań API.** Strona dokumentacji AniList podaje 90 zapytań na minutę oraz tymczasowy stan „degraded” z limitem
  30 na minutę; nagłówki `X-RateLimit-Limit` i `X-RateLimit-Remaining`; po przekroczeniu minutowa blokada
  (P: [Rate limiting](https://docs.anilist.co/guide/rate-limiting), odczytane przez wyszukiwarkę; bezpośrednie pobranie strony zwróciło 403).
  Ostrożnie planować na 30/min.
- **Regulamin.** Zakaz używania API jako kopii zapasowej lub magazynu danych oraz masowego zbierania danych; użycie komercyjne
  poniżej 150 USD miesięcznie bez zgody (P przez wyszukiwarkę: [Terms of use](https://docs.anilist.co/guide/terms-of-use); bezpośrednie pobranie 403).
  Nie znalazłem zapisu o cache obrazów ani hotlinkingu (N). Pytanie o to kieruje się do AniList (Discord, contact@anilist.co). Cache
  ograniczony do tytułów obserwowanych i posiadanych (rząd dziesiątek plików) jest daleko od „masowego zbierania”, ale to ocena, nie zgoda.
- **Koszt w zapytaniach.** Dodanie `coverImage { large }` do istniejących fragmentów (`anilist.py:60-112`) nie zwiększa liczby
  zapytań. Dla tytułów, których owner jeszcze nie pyta, jedno zapytanie `media(id_in: [...])` obsługuje do 50 wpisów
  (R: `_franchise_query`, `perPage: 50`), czyli ok. 30 tytułów to 1 zapytanie.
- **Koszt pobrania pliku.** To żądanie do CDN, nie do GraphQL; czy liczy się do limitu API, nie ustalono (N).
  Plan zakłada pobieranie sekwencyjne przez wspólną bramkę sieci ownera z pomiarem w fazie 0.
- **Cache.** Plik na `anilist_id` w katalogu stanu ownera (`config/`, gitignored). Okładki rzadko się zmieniają; unieważnianie przy
  zmianie URL w odpowiedzi. Uwaga na nazwę: `COVER_DIRECTORY` w `paths.py` oznacza zadaniowy folder filmu okładkowego w workspace,
  więc katalog cache nazwać `posters`, a w interfejsie używać słowa „okładka”.

## 4. Warianty dla AniShift

| Wariant | Zalety | Wady | Zgodność z regułą stałego wyglądu |
|---|---|---|---|
| **A. SIXEL jednego wybranego tytułu w stałym miejscu** (uogólnienie kotwicy maskotki) | Prawdziwy obraz, zero nowych zależności, mechanizm już zatwierdzony przez właściciela, degradacja do „jak dziś” | Wymaga SIXEL (nie ma w starszych terminalach); jedno miejsce na obraz; nie da się miniatury w każdym wierszu; zmiana położenia kosztuje czyszczenie ekranu | Styl bez zmian (paleta, nagłówek, stopka). Dodaje nowy element (panel obrazu); układ listy zmienia się tylko, gdy jest miejsce |
| B. Półbloki ANSI (Rich/Pillow) | Działa wszędzie; da się wstawić do ramki Rich i przycinać; reuse `mascot._terminal_blocks` | 2 piksele pionowo na komórkę: okładka 17 × 12 komórek to 17 × 24 px, rozpoznawalna po kolorze, nie po rysunku; potrzebny pion jak w A | j.w.; dodaje element, wygląd „pikselowy” |
| C. Miniatura w każdym wierszu listy | Najlepsze dla „który jest który” przy 30 tytułach | SIXEL niemożliwy (brak przycinania, stałe wiersze); półbloki wymagają ≥ 3 wierszy na tytuł i zmiany gęstości listy | **Konflikt:** zmienia wygląd listy |
| D. Przeglądarka lub zewnętrzny podgląd (otwarcie pliku okładki) | Zero kodu renderera | Wychodzi z terminala | Nie dotyczy |

## 5. Rekomendacja

**Wariant A**, jako pojedynczy „slot okładki” po prawej stronie listy tytułów (Biblioteka, Subskrypcje), pokazujący okładkę
wybranego wiersza. Powody:

1. Mechanizm istnieje i działa u właściciela (maskotka); koszt to uogólnienie jednego slotu w `TerminalRenderer`.
2. Zero nowych zależności; Pillow i httpx są w projekcie.
3. Brak SIXEL lub za mały terminal = układ identyczny jak dziś, więc reguła stałego wyglądu nie jest złamana tam, gdzie obraz niemożliwy.
4. Wariant B zostaje decyzją odłożoną (druga ścieżka renderu to dodatkowa złożoność za pogorszoną jakość).

**Jawny konflikt do decyzji właściciela:** slot okładki jest nowym elementem układu. Nie zmienia stylu, ale zmienia kompozycję
ekranu listy (tabela przesuwa się w lewo, gdy zmieści się obraz). Jeśli właściciel uzna to za zmianę wyglądu, okładki wypadają z
planu (wariant C jest wtedy jedyną drogą do „który jest który” w liście i wprost zmienia wygląd). Decyzja O-2 w specyfikacji.

## 6. Niewiadome, które zamyka faza 0

| Niewiadoma | Jak zmierzyć |
|---|---|
| Czy terminal właściciela ma SIXEL (wersja i kanał Windows Terminal) | maskotka na Home; jeśli się pokazuje, tak |
| Rozmiar pliku i wymiary `large` / `extraLarge` | skrypt jednorazowy w `scripts/tmp/` pobiera 5 okładek |
| Czas kodowania SIXEL dla slotu 12 wierszy (ok. 136 × 204 px) | ten sam skrypt, `_encode_sixel` na 5 plikach |
| Czy pobranie z CDN dławi limit API | nagłówek `X-RateLimit-Remaining` przed i po 10 pobraniach |
| Rozmiar wiersza kasowania w WT przy zmianie zawartości w tym samym miejscu (mignięcie) | test ręczny właściciela (checkpoint H1 planu) |
