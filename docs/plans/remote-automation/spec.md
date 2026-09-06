---
kind: specification
status: draft
updated: 2026-09-06
---

# Specyfikacja: AniShift zdalnie — worker na VPS, produkt na Google Drive

## Cel

Nowy odcinek obserwowanej serii ma trafić do właściciela jako polski lektor bez włączania komputera: pobranie,
tłumaczenie, lektor i złożenie odbywają się na serwerze, a gotowy plik czeka na Google Drive, gdzie da się go
obejrzeć na telefonie i zsynchronizować na komputer. Lokalny tryb (plany 01–04 w
[local-automation](../local-automation/README.md)) pozostaje w całości i nie zależy od serwera.

## Użytkownik i intencja

Jeden właściciel, Windows w domu, telefon w drodze. Chce raz powiedzieć „obserwuj tę serię” i potem tylko oglądać.
Nie chce administrować serwerem częściej niż przy aktualizacji AniShift.

## Stan wyjściowy

- Rdzeń AniShift (discovery, plan, wykonanie, subskrypcje, klient qBittorrent, katalog AniList) działa na Windows;
  import na Linuksie przechodzi (`mypy --platform linux`), ale okno partii to Prompt Toolkit, autostart to `schtasks`,
  instalator binariów działa tylko na Windows, TTS `sapi` tylko na Windows.
- Produkty dziś: `.pl.ass` i `.eac3` obok źródła (preset `default`); MP4 z lektorem jest dostępny jako produkt.
- Oracle Always Free: 2 OCPU / 12 GB ARM, 200 GB dysku, 10 TB egress, reclaim bezczynnych instancji
  ([research](research.md)). Torrent w chmurze bez VPN grozi banem.
- Właściciel deklaruje ~10 TB miejsca na Google Drive (U16 w starszym pakiecie) i ma dostęp do dysku współdzielonego.

## Ustalenia

- Serwer uruchamia ten sam kod AniShift z tego samego repozytorium, bez osobnej aplikacji. Skutek: każda funkcja
  zdalna musi mieć tryb bez terminala w istniejących modułach, nie w forku.
- Docelowy system: Ubuntu 24.04 LTS ARM64 na Oracle Ampere A1. Skutek: binaria z `apt` (`ffmpeg`, `mkvtoolnix`),
  `qbittorrent-nox`, `rclone`, `wireguard`; brak instalatora AniShift dla Linuksa w tej edycji.
- Produkt zdalny to MP4 H.264 + AAC z lektorem (`mp4_audio_source=narration`), a obok niego `.pl.ass` i `.eac3`.
  Skutek: preset `remote` w `config/presets.json` serwera; telefon odtwarza MP4 z aplikacji Drive.
- Dostawa przez rclone do folderu `AniShift/<Seria>/` na Drive właściciela (Mój dysk albo dysk współdzielony,
  do wyboru w konfiguracji rclone). Skutek: AniShift nie implementuje Drive API; wywołuje rclone i sprawdza wynik.
- Biblioteka nie mieszka na serwerze. Skutek: po potwierdzonej dostawie i spełnieniu warunku seedowania źródło
  i produkty są usuwane z serwera; historia dostaw jest w `config/delivered.json`.
- Pobieranie na serwerze idzie przez tunel VPN z kill-switchem (ruch klienta torrent tylko przez interfejs VPN).
  Skutek: koszt abonamentu VPN po stronie właściciela; bez VPN pobieranie zostaje wyłączone, a serwer przetwarza
  tylko pliki dostarczone inną drogą. Wybór dostawcy VPN: nierozstrzygnięte.
- Tryb bez okna (`headless`) jest pierwszym etapem i jest testowalny lokalnie na Windows. Skutek: serwer nie jest
  warunkiem rozpoczęcia pracy.
- Sekrety (`.env`, konfiguracja rclone, klucz WireGuard) żyją tylko na serwerze w plikach `0600` użytkownika
  `anishift`; repozytorium nie zawiera ich ani ich szablonów z wartościami.

## Wymagania funkcjonalne

- W01: `anishift watch --headless` czuwa bez okna: partia jest wykonywana w tym samym procesie, postęp i wynik idą
  do logu, kody wyjścia partii są zapisywane w ledgerze jak dziś.
- W02: czuwanie w trybie headless obsługuje subskrypcje co godzinę identycznie jak lokalnie.
- W03: `anishift doctor` na Linuksie raportuje binaria z PATH, klucze, workspace, klienta torrent, tunel VPN
  (interfejs obecny i trasa domyślna dla klienta) i rclone (remote skonfigurowany, folder osiągalny).
- W04: po zakończeniu partii z kodem 0 każdy produkt MP4 grupy jest wysyłany do `AniShift/<Seria>/` na Drive;
  sukces to zgodny rozmiar i hash po stronie Drive; niepowodzenie uploadu jest ponawiane w kolejnych skanach,
  nigdy nie powtarza tłumaczenia ani lektora.
- W05: `config/delivered.json` trzyma dla każdego produktu: ścieżkę względną, hash, czas dostawy, stan
  (`uploaded`, `verified`, `retired`); `anishift delivery list|retry` pokazuje i ponawia.
- W06: retencja: źródło i produkty grupy są usuwane z serwera, gdy dostawa jest `verified` i minął próg seedowania
  (czas lub ratio z ustawień), a wolne miejsce poniżej progu wstrzymuje nowe pobrania zamiast zapełniać dysk.
- W07: jednostka systemd `anishift-watch.service` uruchamia czuwanie po starcie systemu jako użytkownik `anishift`,
  z restartem po awarii; `anishift-qbittorrent.service` i tunel VPN startują przed nią.
- W08: aktualizacja serwera to jeden skrypt: `git pull`, `uv sync --frozen`, restart usługi, `anishift doctor`;
  brak zielonego doctora zatrzymuje restart z czytelnym powodem.
- W09: komputer właściciela widzi dostarczone odcinki przez klienta Drive (Google Drive na komputer albo rclone),
  bez zmian w AniShift; lokalny watch nie przetwarza ich ponownie, bo produkty są już obok źródła lub nie ma źródła.

## Wymagania jakościowe

- Awaria jednego odcinka (brak napisów, błąd API) nie zatrzymuje czuwania ani dostaw innych odcinków.
- Restart serwera w dowolnym momencie nie gubi stanu: subskrypcje, ledger dostaw i klient torrent wznawiają się.
- Żaden log ani plik na Drive nie zawiera kluczy API, haseł ani konfiguracji VPN.
- Zużycie dysku jest obserwowalne (`doctor`) i ograniczone progami; brak miejsca daje zrozumiały komunikat.
- Wszystkie komendy CLI zdalne działają bez TTY (cron/systemd), z kodami wyjścia jak lokalnie.

## Inwarianty

- Lokalny tryb Windows działa bez serwera i bez Drive.
- Ten sam `workspace/<Seria>/` układ na serwerze i na komputerze; produkty obok źródła.
- Historia subskrypcji i dostaw jest źródłem prawdy w plikach JSON w `config/`; nie ma drugiej kopii stanu.

## Ograniczenia

- Oracle Always Free: 2 OCPU / 12 GB, 200 GB, reclaim przy bezczynności; PAYG rekomendowane.
- Drive: 750 GiB/dzień uploadu; MKV/EAC3 bez gwarancji odtwarzania w Drive.
- Prawo i AUP: torrent bez VPN na Oracle grozi utratą konta.
- Brak `sapi` na Linuksie: lektor z `edge` albo ElevenLabs (właściciel dziś: `elevenbytes`).

## Zakazane

- Sekrety w repozytorium, w obrazie, w logach i na Drive.
- Osobny fork lub druga aplikacja dla serwera.
- Własny serwer HTTP/API AniShift, panel www, bot.
- Usuwanie jedynej kopii produktu przed weryfikacją dostawy.
- Automatyczne modyfikowanie kont właściciela (Drive, VPN, Oracle) przez AniShift.

## Zakres

Tryb headless, preset zdalny, dostawa rclone z ledgerem i retencją, jednostki systemd, doctor dla Linuksa,
skrypt aktualizacji, dokumentacja wdrożenia krok po kroku, proof na jednej instancji Oracle.

## Poza zakresem

Panel www, powiadomienia push, streaming z serwera, Stremio, MAL/AniList jako lista obejrzanych, wiele serwerów,
własny tracker, kopiowanie całej istniejącej biblioteki na Drive.

## Odłożone

- Grupa zapasowa i ranking grup w subskrypcji (plan 05 lokalny) — działa jednakowo lokalnie i zdalnie, więc po odbiorze.
- Powiadomienie na telefon o nowym odcinku — po działającej dostawie.

## Odrzucone

- Drive API bezpośrednio w AniShift zamiast rclone: druga implementacja uploadu, OAuth i wznowień bez korzyści.
- Docker jako warunek: jedna instancja, jeden użytkownik systemd; kontener dodałby warstwę bez zysku.
- Serwer jako miejsce biblioteki: 200 GB nie mieści biblioteki, a Drive i komputer już ją mają.

## Warunki sukcesu

- S1 (lokalnie): `anishift watch --headless` na Windows przetwarza wrzucony plik bez okna; test integracyjny.
- S2 (serwer): nowy odcinek obserwowanej serii pojawia się w `AniShift/<Seria>/` na Drive jako MP4 z lektorem,
  odtwarzalny w aplikacji Drive na telefonie, bez działania właściciela; ocena: właściciel na telefonie.
- S3: po tygodniu bez ingerencji serwer nie przekroczył progu dysku, nie został zreclaimowany i `doctor` jest zielony.

## Nierozstrzygnięte

- Dostawca VPN i akceptacja jego kosztu (zmienia etap 03: z VPN pobieranie na serwerze, bez VPN tylko przetwarzanie).
- Tenancja Always Free czy PAYG (zmienia ryzyko reclaim i limit 2/12 vs 4/24).
- Mój dysk czy dysk współdzielony jako cel dostawy (zmienia konfigurację rclone, nie kod).
