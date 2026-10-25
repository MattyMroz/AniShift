---
kind: current-state
status: verified-by-reading
baseline: main @ 4365a51
created: 2026-10-25
---

# Stan dziś: panel, Biblioteka, okładki

Wszystko poniżej pochodzi z odczytu kodu na `main` @ `4365a51`. Panelu ani rezydenta nie uruchamiano
(zakaz zlecenia), więc zachowania runtime oznaczone „z odczytu” nie były obserwowane.

## 1. Struktura panelu

| Fakt | Źródło |
|---|---|
| Cztery zakładki: Anime, Subskrypcje, Przetwarzanie, Biblioteka | `anishift/cli/interactive/state.py:116` (`_TABS`), `:192-196` (`_Tab`; Biblioteka to `_Tab.FILES`) |
| Home: Panel, Ręczny, Ustawienia, Wyjście; Panel = `StateController` | `anishift/cli/AGENTS.md` („Auto, postęp i maskotka”), `app.py:961-1000` (tryby renderu) |
| `StateController` to szkielet panelu: klawisze, workery, zdarzenia ownera | `state.py` (1618 linii); treść zakładek w `state_subscriptions.py`, `state_processing.py`, `state_library.py`, liść `state_texts.py` |
| Anime ma osobny `AnimeController` i ekrany `AnimeScreen` (QUERY, TITLES, ENTRIES, EPISODES, RELEASES, DETAILS, FILES, …, SUBSCRIPTIONS, LIBRARY) | `anime.py:168`, `anime_state.py:36-49` |
| Jeden słownik klawiszy zakładek, stopka i `?` z `ScreenActions` | `actions.py:72-145`, strażnik `tests/cli/test_panel_keys.py` |
| Jeden renderer Prompt Toolkit, `mouse_support=True`, redraw 30 fps | `prompts.py` (`TerminalRenderer`), `cli/AGENTS.md` („Renderer i wejście”) |
| Mysz: jedno źródło `pointer.py` (`mark_row`, `mark_target`, `mark_crumbs`, `CRUMB_SEPARATOR = " › "`) | `pointer.py:63`, `:322` |
| Paleta: jedno źródło `palette.py`, `brand_accent` | `cli/AGENTS.md` („Paleta”) |

## 2. Biblioteka dziś

### Dane

- Źródłem prawdy jest owner (rezydent). Panel dostaje listę w snapshotcie (`automation.py:1817-1830`):
  pola `group_id`, `set_id`, `name`, `main_result`, `target`, `series`, `season`, `episode`; tylko zestawy
  `available`. Zestawy z problemem idą osobno jako `library_problems` (`automation.py:1831`).
- Jednostką jest **zestaw** (`LibrarySet`, `control_views.py:93-108`): plik źródłowy i produkty jednego
  odcinka. To nie jest tytuł ani sezon.
- Pola `series/season/episode` wypełnia `name_series()` (`application/library.py:220`):
  tylko dla zestawów, które AniShift pobrał, z klucza AniList (`downloaded_episodes()` → `DownloadedEpisode(anilist_id, number)`, `:185`).
  Tytuł bierze z subskrypcji albo z `_series_titles` ownera (`automation.py:896`, `:8105-8130`), który dociąga go
  franczyzą (`_series_title`, `automation.py:9077`). Reszta zestawów zostaje bez tych pól.
- Dla zestawów bez klucza etykietę daje `library_label(name)` (`library.py:109`): parsowanie nazwy pliku
  (`parse_release_name`, `season_hint`, `episode_range`); nierozpoznana nazwa zostaje w całości jako tytuł
  (`LibraryLabel(stem, None, None)`).
- Panel łączy oba źródła w `state_library._series_label` (`state_library.py:154`) i sortuje naturalnie po
  tytule, sezonie, odcinku (`_order`, `:163`).
- Brak w danych: `anilist_id` w snapshotcie, tytuł odcinka, data emisji, okładka.

### Widok i klawisze

- Lista zestawów: wiersze `Nazwa · Odcinek`, jeden wiersz = jeden zestaw (`state_library.library_row`, `:83`;
  tabela `anime_view.py:369-370`, kolumny `("Nazwa", "Odcinek")`). Brak nagłówka kontekstu z tytułem.
- Enter na wierszu = otwórz wynik odcinka (`_list_key` → `_file_action("open")`, `state.py:452`, `:875`);
  `D` = szczegóły zestawu (lista plików, `_show_details`, `:927`); `F` = folder; Del / `X` = usuń.
- Szczegóły zestawu to osobny ekran plików: Enter otwiera plik, `F` folder, Del usuwa cały zestaw
  (`_details_key`, `state.py:573`; `state_library.detail_actions`, `:99`).
- **Brak zaznaczania wielu wierszy i brak wyszukiwarki w Bibliotece.** `space` obsługują tylko Subskrypcje
  (`state.py:466`), wyszukiwarkę ma Anime i Historia (`_history_input`, `state.py:258`, `:819-845`).
  Opis E6 w masterplanie („Zaznaczanie zostaje”) zakłada zaznaczanie, którego dziś w Bibliotece nie ma.

### Usuwanie, Kosz, Ctrl+Z

- Del ukrywa wiersz w tej klatce (`_hidden`) i usuwa na własnym wątku z własną sesją (`_delete_now` /
  `_delete_hidden`, `state.py:893`, `:901`): `preview_deletion` → `delete_set` (`resident.py:145`, `:175`).
  Bez pytania o potwierdzenie; zabezpieczeniem jest Ctrl+Z (`state_library.LIBRARY_DELETED`, `:38`).
  Odmowa przywraca wiersz (`test_library_refused_delete_returns_the_row_with_the_refusal`).
- Dwa szybkie usunięcia różnych zestawów są obsłużone (`test_library_quick_deletes_remove_two_different_sets`).
- Kosz to kosz Windows (`anishift/platform/recycle.py`, `recycle_worker.py`, `restore_worker.py`).
- Ctrl+Z → `session.undo_deletion()` (`state.py:381`) → owner `_start_restore` na `_latest_deletion()`
  (`automation.py:2344-2370`). **Cofnięcie jest jednopoziomowe**: `_latest_deletion` bierze ostatni wpis
  `pending_deletions` bez pomijania już przywróconych, więc po cofnięciu pierwszego zestawu kolejny Ctrl+Z trafia
  w gałąź `restore_already_completed` (z odczytu `automation.py:2362`; nie sprawdzono w runtime).
  Test `test_library_ctrl_z_uses_owner_latest_not_selected_set` potwierdza, że cel to „ostatnie usunięcie ownera”,
  nie zaznaczenie.

### Pliki ręczne

- Zestaw wrzucony do workspace, a nie pobrany przez AniShift, nie ma `DownloadedEpisode`; tytuł wynika wyłącznie z
  nazwy pliku. Masterplan podaje przykład Slime S4: trzy różne tytuły z jednej serii (`docs/work/08-acquisition/masterplan.md`, E6).
- Żaden kod nie rozpoznaje pliku ręcznego przez AniList. `AniListCatalog.search` istnieje
  (`services/catalog/anilist.py:139`), a owner udostępnia go panelowi (`resident.py` `find_titles`), ale nie dla Biblioteki.

## 3. Okładki dziś

- `grep coverImage` w `anishift/` daje zero trafień. Zapytania AniList (`anilist.py:60-112`) nie żądają
  `coverImage`; `TitleCandidate` (`services/catalog/types.py`) nie ma pola obrazu.
- Panel nie pokazuje żadnego obrazu poza maskotką Home/Auto.

### Maskotka jako istniejący mechanizm obrazu

| Element | Źródło | Znaczenie dla okładek |
|---|---|---|
| Natywny SIXEL z Pillow, własny koder (kwantyzacja, pasma po 6 px, RLE) | `mascot_native.py:346-405` | `_encode_sixel(image)` bez `palette_source` kwantyzuje dowolny obraz do 255 kolorów (`:349-353`) |
| Sonda terminala: `CSI 16t`, `CSI 14t`, atrybuty `CSI c` z „4” = SIXEL, limit 250 ms | `mascot_native.py:206` | gotowe wykrycie wsparcia i rozmiaru komórki |
| Rozmiar w wierszach tekstu, nie w pikselach | `MASCOT_FRAME_ROWS = 10` (`:52`), `load_native_mascot` (`:132`) | okładka też powinna liczyć się w wierszach |
| Kotwica `` w ramce, pozycja z `_native_anchor`, rysowanie w `after_render` przez `write_raw` | `prompts.py:325-380`, `_native_anchor` (`:441`) | jedno miejsce na obraz w rendererze |
| Zmiana położenia lub zniknięcie rastra = `reset(leave_alternate_screen=False)` + `\x1b[2J` | `prompts.py:382-389`, `cli/AGENTS.md` („Zniknięcie lub ruch rastra”) | kosztowne i widoczne; zmiana samej zawartości w tym samym miejscu rysuje się bez czyszczenia (`_draw_native_mascot`, `:363-380`) |
| „Rastra SIXEL nie da się przyciąć” | `cli/AGENTS.md` („Auto, postęp i maskotka”) | okładka nie może leżeć w przewijanym obszarze |
| Renderer ma **jedno** miejsce na obraz (`_native_mascot`, `_native_position`, `_native_drawn_*`) | `prompts.py:253` | okładka wymaga uogólnienia na „obraz natywny”, nie drugiego mechanizmu |
| `STATE` (panel) nie używa maskotki ani kotwicy | `app.py:961-1000`, `grep NATIVE_MASCOT_ANCHOR` (tylko `home.py`, `app.py:1059`, `prompts.py`) | miejsce w panelu jest wolne |
| Zależności: `pillow>=12.3.0`, `rich>=15.0.0`, `prompt-toolkit>=3.0.53`, `httpx>=0.28.1` | `pyproject.toml:17-30` | nie potrzeba nowej zależności |
| README: Home pokazuje animowaną maskotkę tam, gdzie jest SIXEL; inne terminale — tekst | `README.md:41` | wzorzec degradacji: brak SIXEL = jak dziś |

## 4. Katalog i sieć

- Owner ma wspólną bramkę sieci (`acquisition.episode_requests()`, `acquisition.requests(...)`), limity prób i
  dławienie (`anishift/application/AGENTS.md`, `automation.py:9079`). Panel czyta katalog przez `ResidentSession`.
- `franchise()` rozwija graf w ≤ 4 zapytaniach i trzyma węzły poza wyświetlanymi (`services/catalog/AGENTS.md`).
  Fragment zapytania budowany jest w `_franchise_query` (`anilist.py:108-112`) i obsługuje `id_in` do 50 wpisów.
- Dane odcinka (tytuł, data emisji) dla znanego `anilist_id` daje ani.zip (`anizip.py`, `ListedEpisode.title/airs_at`,
  `episode_selection.py:267-276`). Tak korzysta z nich ekran odcinków Anime/Subskrypcji
  (`AnimeController._load_subscription` → `_load_episodes`, `anime.py:460-486`).
- Dozwolone commity: scope z `scripts/hooks/check_commit_msg.py:37-62` (m.in. `tui`, `cli`, `application`, `services`).

## 5. Testy dotykające obszaru

`tests/cli/test_library_actions.py` (327 linii), `test_library_columns.py`, `test_panel_keys.py`,
`test_panel_frame.py`, `test_anime_view.py`, `test_interactive_mouse.py`, `test_interactive_hover.py`,
`test_subscriptions_panel.py`. Wszystkie `pytestmark = pytest.mark.unit` (np. `test_anime_view.py:30`).
Markery: `unit`, `integration`, `e2e`, `network`, `slow`, `smoke` (`pyproject.toml:146-153`).

## 6. Czego nie sprawdzono

- Zachowania paneli w runtime (zakaz uruchamiania panelu i rezydenta).
- Czy drugi Ctrl+Z naprawdę jest odmawiany (tylko odczyt kodu).
- Rozmiar i czas kodowania SIXEL dla okładki 230 px (brak pomiaru; patrz faza 0 planu).
