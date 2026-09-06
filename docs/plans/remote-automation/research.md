---
kind: research
status: current
updated: 2026-09-06
---

# Research: AniShift jako worker na VPS Oracle z dostawą na Google Drive

Pytanie: czy i jak ten sam rdzeń AniShift może pracować bez terminala na darmowym VPS Oracle, pobierać i przetwarzać
odcinki przy wyłączonym komputerze właściciela oraz dostarczać gotowy produkt tam, gdzie właściciel ogląda
(telefon, komputer). Poziom dowodu: decyzje architektoniczne i limity kosztowe, nie parametry runtime (tych
dostarczy dopiero proof na instancji).

## Fakty ze źródeł zewnętrznych

| Twierdzenie | Źródło | Data |
| --- | --- | --- |
| Always Free Ampere A1: 1 500 OCPU-h i 9 000 GB-h miesięcznie = **2 OCPU / 12 GB** ciągle (od 15.06.2026; wcześniej 4/24) | [docs.oracle.com resourceref](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm), [InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/) | 2026-09-06 |
| Konta PAYG (karta, bez opłat w limicie) wg wsparcia Oracle nadal 4 OCPU / 24 GB; brak oficjalnego potwierdzenia | [InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/) | 2026-07 |
| Storage: **200 GB** łącznie boot + block, 5 backupów; egress **10 TB/mies.**; 2× micro AMD 1/8 OCPU 1 GB | docs.oracle.com resourceref | 2026-09-06 |
| Reclaim bezczynnej instancji Always Free: w oknie 7 dni CPU p95 < 20 % **i** sieć < 20 % **i** pamięć < 20 % (A1) | docs.oracle.com resourceref | 2026-09-06 |
| Torrent na Oracle: treść naruszająca prawa autorskie → skarga DMCA → ban instancji/konta | [dev.to](https://dev.to/damith/top-methods-to-download-torrents-on-the-cloud-for-free-2l2c), AUP dostawców | 2026 |
| Google Drive odtwarza natywnie MP4/MOV/WebM/AVI/3GP; MKV i EAC3 bez gwarancji; zalecany H.264 + AAC w MP4 | [videoconverterfactory](https://www.videoconverterfactory.com/tips/google-drive-video-formats.html), [winxdvd](https://www.winxdvd.com/video-transcoder/google-drive-video-format.htm) | 2026 |
| Drive: limit **750 GiB/dzień** uploadu na użytkownika lub konto serwisowe; rclone ma `--drive-stop-on-upload-limit`; dyski współdzielone przez `team_drive` | [rclone.org/drive](https://rclone.org/drive/), forum rclone | 2026 |

## Fakty z repozytorium (odczyt kodu 2026-09-06, gałąź `work/local-automation/05-polish`)

- `mypy --platform linux` przechodzi na całym pakiecie; kod jest importowalny na Linuksie.
- Ścieżki tylko-Windows: `platform/autostart.py` (`schtasks`), `cli/watch.py::spawn_window` (`CREATE_NEW_CONSOLE`,
  na innych systemach zwykły `Popen` tego samego argv: okno partii to Prompt Toolkit, bez TTY nie wystartuje),
  `platform/process_lock.py` ma gałąź `fcntl`, `setup/installer.py` pobiera binaria tylko na Windows
  (`platform/binaries.py` na Linuksie szuka `ffmpeg`, `mkvmerge`, `mkvextract` w PATH), `platform/qbittorrent_config.py`
  odmawia poza Windows, `mascot_native.py` używa `msvcrt` (tylko interaktywny terminal), `CREATE_NO_WINDOW`
  wszędzie przez `getattr(..., 0)`.
- Silniki TTS: `edge`, `elevenbytes`, `elevenlabs` (HTTP, działają na Linuksie), `sapi` (tylko Windows).
  Właściciel używa dziś silników i modeli z `config/settings.json`; `doctor` pokazuje klucze DeepL, ElevenLabs,
  Gemini, OpenRouter.
- Produkty: `ProductKind.MP4` z `mp4_audio_source=narration` istnieje (`services/composition/service.py`
  `_compose_container_mp4`), więc produkt „do telefonu” nie wymaga nowego kodu kompozycji.
- Wejścia do pracy bez terminala: `prepare_auto_run(service, preset_id, group_ids=...)` i `execute_plan(service,
  plan, sink)` w `cli/run.py`; `run_daemon` w `cli/watch.py` przyjmuje `spawner`, więc tryb bez okna to inny spawner
  lub wywołanie w procesie.
- Klient qBittorrent rozmawia z Web UI przez HTTP; `qbittorrent-nox` na Linuksie udostępnia to samo API.
- Google Drive: konektor tej sesji czyta Mój dysk, „udostępnione dla mnie” i foldery na dyskach współdzielonych
  (np. `Shadow Slave AudioBook PL`); nie ma folderu `AniShift`. Konektor nie jest mechanizmem dostawy z VPS;
  dostawa idzie przez rclone z własną autoryzacją.

## Wnioski

1. **Zasoby wystarczą na jeden strumień pracy.** 2 OCPU / 12 GB starczy na tłumaczenie (API), TTS (API) i
   remux/enkod MP4 (ffmpeg, kilka minut na odcinek na ARM). 200 GB dysku to około 60 odcinków źródłowych po 1,4 GB,
   więc źródła muszą znikać po dostawie; biblioteka nie żyje na VPS, żyje na Drive i na komputerze.
2. **Reclaim jest realnym ryzykiem dla czuwania.** Worker przez większość tygodnia jest bezczynny. Reakcja:
   upgrade tenancji do PAYG z alertem budżetowym 0 USD (usuwa reclaim i wg wsparcia przywraca 4/24) albo
   zaakceptowanie reclaimu i odtwarzanie instancji skryptem. Rekomendacja: PAYG.
3. **Torrent bez VPN na Oracle to ryzyko utraty konta.** Pobieranie na VPS wymaga tunelu WireGuard do dostawcy VPN
   z kill-switchem (ruch qbittorrent-nox tylko przez interfejs VPN), albo pobieranie zostaje na komputerze i VPS
   przetwarza tylko to, co dostanie. Rekomendacja: VPN (koszt rzędu 5 EUR/mies.), bo tylko ta droga daje
   „komputer wyłączony”. Decyzja właściciela zapisana jako nierozstrzygnięta w spec.
4. **Produkt do telefonu = MP4 H.264 + AAC z lektorem.** Drive odtwarza go w aplikacji i w przeglądarce; MKV z EAC3
   nie. Komputer nadal dostaje `.pl.ass` i `.eac3` obok źródła, jak dziś.
5. **Dostawa przez rclone.** Jedno konto (OAuth właściciela) lub konto serwisowe z uprawnieniem do folderu;
   750 GiB/dzień to ponad 500 odcinków, bez znaczenia. Weryfikacja po uploadzie: rozmiar i hash (rclone `check`).
6. **Najtańszy pierwszy etap nie potrzebuje VPS.** Tryb bez okna (`watch --headless`) i jednostka systemd da się
   napisać i przetestować lokalnie (Windows uruchamia partię w procesie zamiast okna). Dopiero potem instancja.

## Czego nie sprawdzono

Nie uruchomiono nic na Oracle (brak instancji i poświadczeń w tej sesji). Nie zmierzono czasu enkodowania MP4 na
Ampere A1 ani transferu z nyaa przez VPN. Nie zweryfikowano, czy tenancja właściciela jest Always Free czy PAYG.
Nie potwierdzono, że edge-tts i ElevenLabs odpowiadają z adresów Oracle bez blokad.
