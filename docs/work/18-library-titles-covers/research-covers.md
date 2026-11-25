---
kind: research
status: done
date: 2026-11-26
question: Jak pokazać okładki w panelu Prompt Toolkit na Windows i skąd wziąć tożsamość tytułu, przy stałym wyglądzie panelu?
---

# Research: okładki w terminalu i tożsamość tytułów

Etykiety dowodu: **P** (źródło pierwotne albo pomiar), **R** (fakt z repo), **W** (źródło wtórne), **N** (nie ustalono).
Pomiary z 2026-11-26 na maszynie właściciela; skrypty jednorazowe leżały poza repo i zostały usunięte.

## 1. Terminal właściciela i SIXEL

| Fakt | Dowód |
|---|---|
| Zainstalowany Windows Terminal 1.25.3131.0 | P: `Get-AppxPackage Microsoft.WindowsTerminal*` |
| SIXEL w Windows Terminal od wydania 1.22 | P: [blog Windows Terminal Preview 1.22](https://devblogs.microsoft.com/commandline/windows-terminal-preview-1-22-release), [PR #17421](https://github.com/microsoft/terminal/pull/17421) |
| AniShift już rysuje natywny SIXEL na Home i w Auto; README zapowiada maskotkę „on terminals with SIXEL support” | R: `mascot_native.py`, `prompts.py`, `README.md:41` |
| Kitty graphics protocol i obrazy iTerm2 nie są dostępne w Windows Terminal | W: [microsoft/terminal#8389](https://github.com/microsoft/terminal/issues/8389) otwarte; brak źródła o OSC 1337 |
| Obraz SIXEL w Windows Terminal jest częścią bufora i przewija się z tekstem | P: opis PR #17421 |

Wniosek: decyzja „SIXEL w stałym slocie” nie przeczy możliwościom terminala właściciela. Panelu nie uruchamiano, więc zachowanie
slotu w runtime ocenia checkpoint w planie.

## 2. Jak dziś rysuje się maskotka (mechanizm do ponownego użycia)

| Element | Źródło |
|---|---|
| Sonda terminala przed pętlą wejścia: `CSI 16t` (komórka), `CSI c` z atrybutem `4` = SIXEL, limit 250 ms, tylko przy `isatty`; brak raportu rozmiaru = komórka 8 × 17 | R: `native_mascot_cell` (`mascot_native.py:206`), `TerminalRenderer.run` (`prompts.py:313`) |
| Własny koder SIXEL na Pillow: kwantyzacja do 255 kolorów (`MEDIANCUT` bez palety źródłowej), pasma po 6 px, RLE, przezroczyste tło (`\x1bP9;1;0q`) | R: `_encode_sixel` (`mascot_native.py:346`) |
| Obraz liczony w wierszach tekstu (`MASCOT_FRAME_ROWS = 10`), zajęte komórki w `NativeMascotImage.cell_columns/cell_rows` | R: `mascot_native.py:52`, `:102` |
| Kotwica `` (`NATIVE_MASCOT_ANCHOR`) w ramce Rich; `_formatted_frame` znajduje ją, zamienia na spację i zapamiętuje pozycję | R: `prompts.py:346`, `_native_anchor` (`:464`) |
| Rysowanie w `after_render`: zapis kursora, nadpisanie komórek spacjami (`_native_erase_sequence`), ładunek, odtworzenie kursora; pomija rysunek, gdy ładunek i pozycja się nie zmieniły | R: `_draw_native_mascot` (`prompts.py:374`) |
| Ruch albo zniknięcie rastra: `reset(leave_alternate_screen=False)` + `\x1b[2J` z następną klatką | R: `_before_render`, `_erase_native_mascot` (`prompts.py:336`, `:393`) |
| Renderer ma jedno miejsce na obraz i zna tylko maskotkę; panel (`STATE`) nie wstawia kotwicy | R: `prompts.py:263-267`, `app.py:968-1001` |

Dwie luki mechanizmu ważne dla okładki:

1. `_native_anchor` liczy kolumnę jako `len()` znaków w linii, nie komórki terminala. Kotwica za tabelą z tytułem CJK
   wylądowałaby za daleko w lewo. Maskotka tego nie ujawnia, bo stoi na początku linii.
2. Prompt Toolkit przy skróceniu linii wysyła `erase_end_of_line` od końca nowego tekstu
   (`prompt_toolkit/renderer.py`, `_output_screen_diff`, odczyt w `.venv`). Okładka po prawej stronie tabeli może więc stracić
   fragment, gdy skróci się linia w jej wierszach (przewinięcie listy, inny komunikat). Maskotka animuje się co około 0,1 s,
   więc przerysowuje się sama; statyczna okładka musi rysować się ponownie po zmianie linii w swoich wierszach. Czy Windows
   Terminal czyści piksele SIXEL przy `erase_end_of_line`: N, rozstrzyga checkpoint właściciela.

## 3. AniList: okładki (prawdziwe zapytania tylko do odczytu)

Zapytanie:

```graphql
query ($ids: [Int]) { Page(perPage: 50) { media(id_in: $ids, type: ANIME) {
  id title { romaji english } coverImage { extraLarge large medium color } } } }
```

z `ids = [21, 16498, 1535, 999999999]` zwróciło HTTP 200, `Content-Type: application/json`, `X-RateLimit-Limit: 30`,
`X-RateLimit-Remaining: 29`. Kształt odpowiedzi (P):

```json
{"data": {"Page": {"media": [
  {"id": 21, "title": {"romaji": "ONE PIECE", "english": "ONE PIECE"},
   "coverImage": {
     "extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx21-ELSYx3yMPcKM.jpg",
     "large": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/medium/bx21-ELSYx3yMPcKM.jpg",
     "medium": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/small/bx21-ELSYx3yMPcKM.jpg",
     "color": "#e49335"}},
  {"id": 1535, "coverImage": {"...": "...", "color": null}}
]}}}
```

| Fakt | Dowód |
|---|---|
| Nieistniejące ID znika z listy bez błędu; kolejność wyników nie odpowiada kolejności `ids` | P: brak `999999999`, kolejność 21, 1535, 16498 |
| `color` bywa `null` | P: ID 1535 |
| Nazwy pól są przesunięte względem ścieżek CDN: `extraLarge` → `/cover/large/`, `large` → `/cover/medium/` | P: odpowiedź |
| Host plików: `s4.anilist.co` (Cloudflare), HTTPS, odpowiedź 200 bez przekierowania | P: nagłówki pobrania |
| `extraLarge`: JPEG 460 × 636 px, 83 333 B; `large`: JPEG 230 × 318 px, 28 423 B (ID 16498) | P: pobranie i odczyt Pillow |
| `Cache-Control: max-age=2678400` (31 dni) | P: nagłówki CDN |
| Pobranie pliku z CDN nie zużywa limitu GraphQL: po dwóch pobraniach i jednym zapytaniu GraphQL `X-RateLimit-Remaining` spadło z 29 do 28 | P: nagłówki |
| Limit GraphQL w dniu pomiaru: 30 na minutę; dokumentacja podaje 90 i tryb „degraded” 30 | P: nagłówek; W: [AniList rate limiting](https://docs.anilist.co/guide/rate-limiting) |
| Regulamin zakazuje używania API jako magazynu danych i masowego zbierania; o cache obrazów milczy | W: [AniList terms of use](https://docs.anilist.co/guide/terms-of-use); N: zgoda na cache (O-10, pytanie właściciela) |

Wybór: `coverImage { extraLarge }`, bo slot 12 wierszy przy komórce 20 px ma 240 px wysokości, a `large` (318 px) przy większych
komórkach skalowałoby się w górę. 33 okładki to około 2,7 MB.

## 4. Koszt SIXEL okładki (pomiar)

`_encode_sixel` na okładce 16498 po przeskalowaniu LANCZOS do wysokości slotu (P):

| Wiersze | Komórka | Piksele | Kolumny | Ładunek | Czas |
|---|---|---|---|---|---|
| 10 | 8 × 17 | 123 × 170 | 16 | 69 KB | 166 ms |
| 12 | 8 × 17 | 148 × 204 | 19 | 92 KB | 245 ms |
| 12 | 10 × 20 | 174 × 240 | 18 | 120 KB | 355 ms |
| 16 | 10 × 20 | 231 × 320 | 24 | 188 KB | 655 ms |

Źródło `extraLarge` i `large` daje te same czasy (koszt zależy od rozmiaru wyjścia). Wniosek: kodowanie zawsze w tle, z
pamięcią gotowych ładunków; slot 12 wierszy ma 18–19 kolumn przy proporcji okładki 0,72.

## 5. Tożsamość tytułu: dane właściciela i koszt

Odczyt tylko do odczytu `config/watch/state.json` głównego checkoutu (P):

| Wielkość | Wartość |
|---|---|
| Zestawy w Bibliotece (`ready_groups`) | 299 |
| Zestawy pobrane przez AniShift (`downloaded_episodes`) | 228 |
| Zestawy ręczne | 71, czyli 28 unikalnych tytułów z `library_label` |
| Subskrypcje | 23, wszystkie wpisy są wśród 33 wpisów pobranych zestawów |
| Unikalne wpisy AniList (subskrypcje ∪ pobrane) | 33 |

Jedno zapytanie zbiorcze istniejącym fragmentem franczyzy (`_franchise_query()`, głębokość 3, `id_in` z 33 ID) zwróciło
HTTP 200 w 1,0 s, 190 KB i 33 wpisy (P). Dziś owner czyta tytuł serii osobnym `franchise()` na każdy wpis spoza subskrypcji
(do 4 zapytań na wpis, `_series_title`, `automation.py:9533`), a tytuł subskrybowanego wpisu bierze z subskrypcji.

Tytuł serii z `series_title(english or romaji)` pojedynczego wpisu nie wystarcza do grupowania: nowy sezon często ma w AniList
tylko romaji, a starszy angielski tytuł, więc wyszłyby dwa wiersze (wniosek z kształtu danych; przykład Slime w
`docs/work/08-acquisition/masterplan.md`, E6). Łańcuch `PREQUEL`/`SEQUEL` z grafu daje jedno ID serii niezależnie od tytułów.
Rozpoznanie 28 tytułów ręcznych kosztuje do 28 wyszukiwań (`search` robi czasem drugą próbę ze skróconymi słowami), czyli
około minuty przy 30 zapytaniach na minutę, raz na uruchomienie rezydenta.

## 6. Format nazw workstreamu 23 a `library_label`

`library_label` na przykładowych nazwach w formacie `<tytuł> - SxxEyy - <tytuł odcinka>` (P):

| Nazwa | Tytuł | Sezon | Odcinek |
|---|---|---|---|
| `Attack on Titan - S01E05 - First Battle.pl.mkv` | `Attack on Titan` | 1 | 5 |
| `That Time I Got Reincarnated as a Slime - S04E03 - The Demon Lord.pl.mkv` | `That Time I Got Reincarnated as a Slime` | 4 | 3 |
| `Kaiju No. 8 - S02E01 - The Man Who Became a Kaiju.mkv` | `Kaiju No. 8` | 2 | 1 |
| `Re ZERO -Starting Life in Another World- - S03E01 - Theater of Malice.pl.mkv` | `Re ZERO -Starting Life in Another World` (bez końcowego `-`) | 3 | 1 |

Wniosek: przyszłe nazwy z 23 czytają się poprawnie; końcowy myślnik tytułu ucina `TITLE_EDGE`, co nie zmienia grupy, bo
`normalize_series` i tak usuwa interpunkcję.

## 7. Warianty i rekomendacja (przyjęta)

| Wariant | Ocena |
|---|---|
| A. SIXEL jednego wybranego tytułu w stałym slocie, uogólnienie kotwicy maskotki | przyjęty (O-2, O-3): prawdziwy obraz, zero zależności, mechanizm działa u właściciela |
| B. Półbloki ANSI | odłożony: druga ścieżka renderu, 2 piksele na komórkę |
| C. Miniatura w każdym wierszu | odrzucony: SIXEL nie da się przyciąć, zmienia wygląd listy |
| D. Otwarcie pliku okładki w przeglądarce | odrzucony: wychodzi z terminala |

## 8. Czego nie ustalono

- Czy `erase_end_of_line` Windows Terminal czyści piksele SIXEL i czy ponowne narysowanie tego samego obrazu migocze:
  checkpoint właściciela w fazie 6 planu.
- Zgoda AniList na cache okładek: pytanie właściciela (O-10), poza tym workstreamem.
