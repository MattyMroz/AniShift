---
kind: current-state
status: verified-by-reading
baseline: main @ 1f76e30
created: 2026-11-26
---

# Stan dziś: panel, Biblioteka, okładki

Wszystko poniżej pochodzi z odczytu kodu na `main` @ `1f76e30` (gałąź `feat/library-titles-covers`). Panelu ani rezydenta
nie uruchamiano; pomiary danych i AniList są w [research-covers.md](research-covers.md).

## 1. Co zmieniło się od planu z 2026-10-25 (`4365a51`)

- Ctrl+Z jest wielopoziomowe i obejmuje jedno uruchomienie rezydenta (`65a7d2d`, `3002b3c`; `latest_deletion`,
  `control.py:1023`). Poprzednia decyzja O-6 jest więc wdrożona.
- Ctrl+Z od razu pokazuje wiersz „Przywracam…” (`fba473a`; `_restoring`, `undo_target`, `settled_restores`).
- Przetwarzanie usuwa nieudany odcinek przez Del tą samą drogą co Biblioteka i odróżnia go przestrzenią `unrecorded:`
  (`bd13442`, `f9de08a`).
- Przetwarzanie straciło klawisz X i pytanie Enter/Esc przed anulowaniem: Del działa od razu (`b00fe9b`, 2026-11-09).
  Wzorzec `_question`, na którym stary plan opierał pytanie przed usunięciem wielu zestawów, już nie istnieje.
- Zestaw usuwa się i przywraca w mniej niż sekundę (`d0a69d0`).
- Maskotka, renderer, `state_library.py`, `anime_view.py` (poza kolumnami wydań), `library.py` (poza stagingiem) i
  `anilist.py` mają ten sam kształt co w starym planie. Nowe workstreamy 19–22 nie dotykają Biblioteki ani obrazu;
  `21-playshift` nie ma kodu w AniShift.

## 2. Struktura panelu

| Fakt | Źródło |
|---|---|
| Zakładki Anime, Subskrypcje, Przetwarzanie, Biblioteka; Biblioteka to `_Tab.FILES` | `state.py:127`, `:200` |
| `StateController` (1726 linii) prowadzi klawisze, workery i zdarzenia ownera; treść zakładek w czystych `state_subscriptions.py`, `state_processing.py`, `state_library.py`, liść `state_texts.py` | `anishift/cli/AGENTS.md` |
| Subskrypcje i Biblioteka renderują się wspólnym `_table_body` przez `render_anime` | `state.py:1464`, `:1476`, `:1487` |
| Jeden słownik klawiszy z opisami `?`, stopka z `ScreenActions`; strażnik `test_panel_keys.py` | `actions.py:44` |
| Opisy klawiszy, które Biblioteka może przejąć: `("Enter", "odcinki")`, `("Enter", "obejrzyj")`, `("Space", "zaznacz")` (dziś „żeby D pobrało kilka naraz”), `("A", "wszystkie")`, `("/", "szukaj")` | `actions.py:44-88` |
| Pole tekstowe jednym modelem `TextInput`; wzorzec wyszukiwania w Historii | `text_input.py`, `_history_input` (`state.py:267`, `:817-845`) |
| Mysz z jednego źródła `pointer.py`; okruszki `mark_crumbs`, `CRUMB_SEPARATOR` | `pointer.py` |

## 3. Biblioteka dziś

### Dane

- Panel dostaje zestawy w snapshotcie `library`: `group_id`, `set_id`, `name`, `main_result`, `target`, `series`, `season`,
  `episode`; tylko dostępne zestawy. Zestawy z problemem idą jako `library_problems` (pełne `encode_view(LibrarySet)`),
  usuwania jako `deletions` (`automation.py:1944-1990`).
- `LibrarySet` to widok, nie stan trwały (`control_views.py:93`); nowe pola nie zmieniają `WatchState`.
- `name_series` (`library.py:222`) wypełnia `series/season/episode` tylko dla zestawów pobranych przez AniShift
  (`downloaded_episodes`, `:187`). Tytuł bierze z subskrypcji, a gdy jej nie ma, z `_series_titles` ownera
  (`automation.py:963`), które `_request_series_titles` (`:8521`) dociąga osobnym `franchise()` na każdy wpis spoza subskrypcji
  (`_series_title`, `:9533`, do 4 zapytań na wpis). Tytuł to `series_title(english or romaji)` pojedynczego wpisu.
- `anilist_id` nie trafia do snapshotu; panel nie wie, które zestawy należą do jednej serii, poza równością tekstu `series`.
- Zestaw ręczny nie ma pól serii; etykietę daje `library_label(name)` (`library.py:111`), a nierozpoznana nazwa zostaje w
  całości jako `LibraryLabel(stem, None, None)`.
- `normalize_series` (`acquisition.py:582`) normalizuje tytuły do klucza grupy, ale nie jest eksportowane w fasadzie
  `anishift.application`.

### Widok i klawisze

- Lista zestawów, wiersz = zestaw, kolumny `Nazwa`, `Odcinek` (`anime_view.py:375`, `state_library.library_row`).
- Enter = otwórz wynik (`_file_action("open")`, `state.py:880`), `D` = szczegóły zestawu, `F` = folder, Del = usuń
  (`X` jako cichy alias), Ctrl+Z = cofnij.
- Szczegóły to osobny poziom `_details` (`state.py:260`, `_details_key` `:558`); okruszek
  `("Biblioteka", details_label(...).text)`.
- Zasobnik otwiera Bibliotekę i wybiera zestaw po `set_id` (`show_library`, `state.py:307`).
- Brak zaznaczania, filtra i poziomu tytułu.

### Usuwanie i Ctrl+Z

- Del ukrywa wiersz (`_hidden`) i usuwa go na osobnym wątku z osobną sesją (`_delete_now`, `_delete_hidden`,
  `state.py:904`, `:912`): `preview_deletion` → `delete_set`. Bez pytania; komunikat `LIBRARY_DELETED`
  („Usunięto · Ctrl+Z cofnij”).
- Ctrl+Z: `_undo_now` → `undo_deletion()` → owner cofa najnowsze nieprzywrócone usunięcie (`state.py:980`).

## 4. Okładki i obraz w terminalu

- Kod nie czyta `coverImage`; `TitleCandidate` i zapytania AniList nie mają pola obrazu (`anilist.py:58-112`).
- Jedyny obraz w terminalu to maskotka Home i Auto. Opis mechanizmu, jego dwie luki (kolumna kotwicy w znakach, kasowanie
  końca linii przez Prompt Toolkit) i pomiary: [research-covers.md](research-covers.md), sekcje 2 i 4.
- `TerminalRenderer` sprawdza SIXEL raz w `run()` i trzyma wynik tylko jako `NativeMascotImage`; rozmiar komórki nie jest
  dostępny dla innych obrazów (`prompts.py:313-321`).
- Ścieżki: `paths.py` ma `config_dir()`, `watch_dir()`, `elevenreader_dir()`, `torrent_profile_dir()`; nie ma katalogu
  cache. `.gitignore` wymienia podkatalogi `config/` z osobna (`config/watch/`, `config/qbittorrent/`, `config/elevenreader/`).
  `COVER_DIRECTORY = "cover"` to zadaniowy folder filmu okładkowego w `workspace/`, inna rzecz.

## 5. Katalog i sieć

- Owner czyta AniList przez `AcquisitionService` i wspólną bramkę `acquisition.episode_requests()`; graf franczyzy pamięta
  w procesie na wpis (`_franchise_graph`, `acquisition.py:853`).
- `AniListCatalog.franchise` używa `_franchise_query()` z `id_in` i `perPage: 50` (`anilist.py:108`, `:157`);
  `parse_franchise_page` składa węzły (`:255`), `franchise_traversal` daje łańcuch `PREQUEL`/`SEQUEL`
  (`episode_selection.py:429`).
- Tytuły i daty odcinków jednego wpisu daje `ResidentSession.episodes(anilist_id)` → `EpisodeListing.episodes`
  (`ListedEpisode.title`, `airs_at`; `resident.py:214`, `episode_selection.py:286`). Ekran odcinków Anime formatuje datę
  w `anime_rows.episode_row` (`anime_rows.py:103`).
- Wiersze Subskrypcji niosą `anilist_id` (`SubscriptionRow`, `subscription_targets.py:363`).

## 6. Testy dotykające obszaru

`tests/cli/test_library_actions.py`, `test_library_columns.py`, `test_panel_keys.py`, `test_panel_frame.py`,
`test_anime_view.py`, `test_interactive_mouse.py`, `test_interactive_hover.py`, `test_interactive_state.py`,
`test_interactive_mascot_native.py`, `test_subscriptions_panel.py`; `tests/application/test_library_series.py`,
`test_library_label.py`, `test_library_undo.py`, `test_automation.py`; `tests/services/catalog/test_anilist.py`; zapisane
grafy `tests/fixtures/search/anilist__franchise__*.json`. Markery: `unit`, `integration`, `e2e`, `network`, `slow`, `smoke`.

## 7. Czego nie sprawdzono

- Zachowania panelu i rezydenta w runtime.
- Wyniku pełnych bramek na tym baseline (faza 0 planu zapisuje wąski baseline).
