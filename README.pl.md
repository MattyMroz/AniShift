# AniShift

[English](README.md)

Terminalowy lektor anime po polsku.

AniShift wyszukuje i pobiera odcinki anime, a potem robi z plików MKV polskie napisy albo
ścieżkę lektora: wyciąga napisy, tłumaczy je, czyta syntezatorem mowy, obrabia dźwięk
i składa gotowy plik. Źródła i gotowe produkty trafiają do płaskiego katalogu
`workspace/ready/`. Regeneracja działa tam na miejscu, bez przenoszenia plików z powrotem.
Dane robocze leżą w `workspace/temp/`.

AniShift działa obecnie tylko na Windowsie.

## Szybki start

```bash
uv sync                                   # zależności Pythona
uv run anishift setup                     # MKVToolNix i FFmpeg do external/bin/
uv run anishift doctor                    # wszystko na zielono? wtedy:
uv run anishift                           # interfejs interaktywny
```

Klucze API wpisz do `.env` (patrz „Konfiguracja”); `doctor` pokaże, które silniki je mają.
Otwarcie interfejsu uruchamia rezydenta w tle albo łączy się z już działającym. Jeśli
rezydent ma startować po każdym zalogowaniu, uruchom `uv run anishift autostart enable`.

Jeśli w powłoce nadal jest aktywne środowisko wirtualne innego projektu, uruchamiaj
`uv run --no-active anishift`. Wtedy uv wybierze `.venv` AniShift i nie pokaże ostrzeżenia
o niezgodności. Szczegóły:
[dokumentacja środowiska projektu w uv](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).

## Interfejs

`anishift` bez podkomendy otwiera ekran startowy z czterema pozycjami:

- **Panel** — główne okno z czterema zakładkami: Anime, Subskrypcje, Przetwarzanie i Biblioteka.
- **Ręczny** — wybór źródeł, wyniku i ustawień jednorazowego przebiegu.
- **Ustawienia** — preferencje, silniki, modele, źródła pobierania i połączenia.
- **Wyjście** — zamyka interfejs; przyjęta praca trwa dalej w rezydencie.

Na terminalach z obsługą SIXEL ekran startowy pokazuje animowanego glutka w pixel arcie;
pozostałe terminale dostają wersję tekstową. Cały interfejs rysuje jeden renderer
Prompt Toolkit.

W Panelu zakładki przełączasz strzałkami w lewo i w prawo, Tab/Shift+Tab albo kliknięciem.
**O** włącza i wyłącza automat z każdej zakładki, **?** pokazuje klawisze bieżącego ekranu,
a **Esc** cofa. Panel otwiera się na Subskrypcjach.

### Anime: wyszukiwanie i pobieranie

Wpisz tytuł tak, jak go wymawiasz, na przykład `frieren` albo `solo leveling`. AniList
zamienia go na serię, wybierasz wpis (sezon, film, odcinek specjalny) i dostajesz listę
odcinków z tytułami i datami emisji. Dla każdego odcinka AniShift przeszukuje Torrentio,
Nyaa, Knaben, nekoBT i TsukiHime, scala wyniki i układa wydania według kolumn **Jakość**
i **Pewność** (czy wydanie to na pewno ten odcinek).

Na liście odcinków:

- **Spacja** zaznacza odcinek, **A** zaznacza wszystkie, **Z** pyta o zakres;
- **D** pobiera zaznaczone odcinki albo podświetlony;
- **I** (lub Enter) otwiera listę wydań odcinka, gdzie **D** pobiera wybrane wydanie;
- **P** pobiera odcinek ponownie;
- **S** subskrybuje serię;
- Enter na gotowym odcinku go odtwarza.

Wydania z polskimi napisami są na liście wyżej. Subskrypcje czekają na polskie napisy
(domyślnie 2 godziny, do zmiany w Ustawienia › Pobieranie), a potem biorą najlepsze inne
wydanie; ręczne **D** pobiera od razu. W tym samym miejscu wyłączysz każde źródło osobno.

Pobieraniem zajmuje się własny, zweryfikowany qBittorrent AniShift w `external/bin/qbittorrent/`.
Jego profil, dane logowania i historia leżą w `config/qbittorrent/`, osobno od twojej
instalacji, a port Web UI wybiera sam. Pobrania idą równolegle; zakończone przestają
seedować i zwalniają pliki przed przetwarzaniem.

```bash
uv run anishift qbit setup    # opcjonalnie: przygotuj prywatnego klienta przed pierwszym pobraniem
uv run anishift qbit status   # sprawdź gotowość bez uruchamiania klienta
```

### Subskrypcje

**S** na liście odcinków otwiera szkic subskrypcji: wyemitowane odcinki są zaznaczone
i pobierają się od razu, kolejne po emisji. Zakładka **Subskrypcje** pokazuje listę:

- **Enter** otwiera odcinki sezonu, gdzie **T** od razu pobiera czekający odcinek;
- **D** dodaje nową subskrypcję przez wyszukiwarkę Anime;
- **W** wstrzymuje lub wznawia, **R** sprawdza teraz;
- **Del** usuwa, **Ctrl+Z** przywraca ostatnio usuniętą.

Subskrypcja zamyka się sama, gdy sezon się skończył, a wszystkie odcinki są na miejscu.
Subskrypcje są zapisane w stanie rezydenta, `config/watch/state.json`.

```bash
uv run anishift subs list        # subskrypcje, następny odcinek, ostatnie sprawdzenie
uv run anishift subs check ID    # sprawdź teraz jedną subskrypcję
uv run anishift subs remove ID   # usuń jedną subskrypcję
```

### Przetwarzanie i Biblioteka

**Przetwarzanie** pokazuje pobrania i obróbkę: **W** wstrzymuje lub wznawia transfer,
**Del** anuluje go po potwierdzeniu, a **H** otwiera historię.

W `workspace/` może być osobny podfolder na każdą serię. Wyszukiwanie plików czyta katalog
główny i wszystkie podfoldery poza zarządzanym `temp/` i katalogami ukrytymi. Przy włączonym
automacie stabilne pliki trafiają do tego samego harmonogramu co w trybie Ręcznym, a gotowe,
potwierdzone produkty są używane ponownie. Po udanej obróbce źródła i produkty przechodzą
do `ready/`, a na tym samym dysku ich zawartość nie jest przepisywana. Przy kolizji nazw
zostają oba odcinki.

W **Bibliotece** Enter otwiera wynik, **F** pokazuje go w Eksploratorze, a **Del** przenosi
cały zestaw do Kosza bez pytania. **Ctrl+Z** przywraca ostatnio usunięty zestaw, także po
restarcie rezydenta. Nigdy nie nadpisuje zajętego miejsca i cofa tylko jedno, ostatnie
usunięcie.

Stan rezydenta w `config/watch/state.json` ma wersję (schemat 5). Nowsza wersja AniShift
czyta i migruje starsze schematy, ale starsza odrzuci stan zapisany przez nowszą, więc nie
uruchamiaj starszego AniShift na stanie zapisanym przez nowszy.

Po przerwie rezydent sprawdza zapisaną pracę i wznawia bezpieczne, niedokończone operacje.
Niepotwierdzona operacja zdalna albo wyczerpany limit ponowień zostaje widoczny do ręcznego
rozwiązania. Istniejące produkty są dostępne, dopóki trwa przygotowanie zamiennika.

## Rezydent i autostart

```bash
uv run anishift autostart enable    # zarejestruj zadanie przy logowaniu i uruchom rezydenta
uv run anishift autostart disable   # usuń zadanie i zatrzymaj rezydenta
uv run anishift autostart status    # enabled | disabled | missing
uv run anishift watch               # uruchom rezydenta w tym terminalu
uv run anishift watch status        # running (pid N) | stopped
uv run anishift watch stop          # zatrzymaj rezydenta
```

Rezydent działa bez okien konsoli i ma ikonę w zasobniku, która otwiera AniShift.

## Komendy techniczne

```bash
uv run anishift run --preset ID   # uruchom zapisany preset bez interakcji
uv run anishift doctor            # sprawdź narzędzia, klucze, workspace, kodowanie, rezydenta i autostart
uv run anishift setup [--force]   # pobierz i zweryfikuj narzędzia w external/bin/
```

Przed odczytem mediów AniShift dociąga brakujące MKVToolNix i FFmpeg ze zweryfikowanego
manifestu (SHA256). Workspace z samymi plikami TXT ich nie pobiera.

Przebiegi bez interakcji idą przez rezydenta i kończą się kodem `0` przy pełnym sukcesie,
`1` przy odmowie przed startem, `3` przy błędzie lub częściowym wyniku i `4` po anulowaniu.
Komunikaty dla użytkownika są krótkie; diagnostyka trafia do logu strukturalnego.

## Konfiguracja

Ustawienia zapisują każdą obsługiwaną wartość od razu. Pliki konfiguracji przydają się
przy pierwszej konfiguracji i zaawansowanych zmianach:

| Plik | Zawartość |
|---|---|
| `config/presets.json` | Presety dla `run --preset` i preset domyślny |
| `config/settings.json` | Preferencje przepływu, silników i pobierania |
| `.env` | Klucze API i tokeny |

Domyślnie tłumaczy Google; tłumaczenie przez LLM wybierasz w Ustawieniach, razem z dostawcą
i modelem (domyślnie Gemini). Każdy dostawca czyta własny klucz z `.env`. Palantir Foundry
jest jednym z dostawców: jego lista modeli jest wbudowana w
`anishift/services/llm/engines/palantir/constants.py`, a token pochodzi z
`ANISHIFT_PALANTIR_TOKEN`, a gdy go brak, z `FOUNDRY_API_TOKEN`. Sekrety nigdy nie są
wyświetlane; diagnostyka mówi tylko, czy są ustawione.

## Wymagania

- Windows i Python 3.14+
- MKVToolNix i FFmpeg w `external/bin/`, pobierane na żądanie albo przez `anishift setup`
- qBittorrent przygotowywany prywatnie na żądanie; własna instalacja nie jest potrzebna
- Klucze API dla wybranych silników tłumaczenia i TTS
- Opcjonalne głosy Windows SAPI trzeba zainstalować osobno, z ważną licencją i w architekturze
  zgodnej z procesem Pythona. AniShift nie instaluje ani nie aktywuje głosów komercyjnych;
  wygasły głos może pokazać własne okno producenta.

## Dokumentacja

[Mapa dokumentów](docs/README.md) prowadzi do bieżącej pracy, pliku pomysłów
i historii wdrożenia.
