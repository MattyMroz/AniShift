---
kind: package-index
status: proposed
updated: 2026-09-06
---

# AniShift zdalnie | pakiet planistyczny (VPS Oracle + Google Drive)

| Dokument | Zawartość |
| --- | --- |
| [research.md](research.md) | limity Oracle po cięciu z czerwca 2026, reclaim, ryzyko DMCA, formaty Drive, rclone, gotowość kodu na Linux |
| [spec.md](spec.md) | cel, ustalenia, wymagania W01–W09, zakazy, warunki sukcesu, nierozstrzygnięte (VPN, tenancja, cel dostawy) |
| [masterplan.md](masterplan.md) | sześć etapów: headless → proof → dostawa → pobieranie za VPN → operacje → strona domowa |
| [plans/01-headless-worker.md](plans/01-headless-worker.md) | bieżący etap, wykonalny i testowalny bez serwera |

Relacja do [local-automation](../local-automation/README.md): tamten pakiet wykluczał VPS decyzją właściciela z 2026-09-05;
2026-09-06 właściciel zamówił automatyzację na Oracle z dostawą na Drive. Lokalny tryb pozostaje w całości.

## Przepływ pracy dnia codziennego (stan docelowy po etapie 04)

1. Właściciel raz: Anime → seria → `O` (lokalnie albo `anishift subs` przez SSH na serwerze; subskrypcje serwera
   są osobnym plikiem, bo serwer i komputer mają własne `config/`).
2. Serwer co godzinę sprawdza nyaa, qbittorrent-nox za VPN pobiera do `/srv/anishift/workspace/<Seria>/`.
3. Czuwanie headless po 10 s ciszy uruchamia partię: napisy → tłumaczenie → lektor → MP4 (H.264 + AAC lektor)
   oraz `.pl.ass` i `.eac3` obok źródła.
4. Dostawa: rclone kopiuje MP4 do `AniShift/<Seria>/` na Drive, weryfikuje hash, wpis w `config/delivered.json`.
5. Telefon: aplikacja Drive odtwarza MP4. Komputer: klient Drive synchronizuje folder `AniShift/` do lokalnego
   `workspace/` (albo osobnego katalogu), lokalny watch nic nie robi, bo produkt już jest.
6. Retencja na serwerze: po weryfikacji dostawy i progu seedowania źródło i produkty znikają; przy dysku poniżej
   progu nowe pobrania czekają.

## Struktura folderów

Serwer (Ubuntu 24.04 ARM64, użytkownik `anishift`):

```text
/srv/anishift/
  app/                 # klon repozytorium, .venv przez uv; aktualizacja = git pull + uv sync --frozen
  app/config/          # settings.json, presets.json (preset remote), subscriptions.json, delivered.json, watch/
  app/.env             # klucze API, 0600; jedyne miejsce sekretów AniShift
  workspace/           # ANISHIFT_WORKSPACE_ROOT; <Seria>/ jak lokalnie; temp/ zarządzany
  logs/                # anishift.log.jsonl (logrotate), qbittorrent, rclone
/etc/systemd/system/anishift-watch.service, qbittorrent-nox.service, wg-quick@vpn.service
/home/anishift/.config/rclone/rclone.conf   # 0600, remote "drive" (Mój dysk lub team_drive)
/etc/wireguard/vpn.conf                     # 0600
```

Google Drive (Mój dysk albo dysk współdzielony, do decyzji):

```text
AniShift/
  <Seria po angielsku>/
    [Grupa] Seria - 01 (1080p) [CRC].pl.mp4     # produkt do telefonu
    [Grupa] Seria - 01 (1080p) [CRC].pl.ass     # napisy PL (opcjonalnie, dla komputera)
    [Grupa] Seria - 01 (1080p) [CRC].eac3       # lektor (opcjonalnie, dla komputera)
```

Komputer właściciela: bez zmian (`workspace/<Seria>/`); klient Drive dostarcza `AniShift/` jako osobny katalog
lub bezpośrednio do `workspace/` (decyzja w etapie 06).

## Przepływ pracy nad kodem

- Gałęzie `work/remote-automation/<nn>-<slug>`, jedna na plan; PR do `main` (CI: ruff, mypy w obu targetach,
  pytest na Ubuntu i Windows), merge po odbiorze właściciela.
- Wdrożenie na serwer to skrypt z etapu 05; do tego czasu ręcznie według `deploy.md` (powstaje w planie 01).
- Każdy etap kończy się sekcją „Wynik wykonania” w swoim planie i aktualizacją tabeli w masterplanie.

## Stan pakietu

Dokumenty planistyczne z 2026-09-06 po researchu (limity Oracle, AUP, Drive, rclone, odczyt kodu). Nie uruchomiono
instancji Oracle, nie wysłano nic na Drive (konektor Drive tej sesji potwierdził tylko dostęp do Mojego dysku
i dysków współdzielonych właściciela; nie ma jeszcze folderu `AniShift`). Plan 01 czeka na akceptację właściciela;
etapy 02–06 wymagają instancji i decyzji o VPN.
