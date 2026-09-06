---
kind: masterplan
status: active
updated: 2026-09-06
---

# Masterplan: AniShift zdalnie

## Cel końcowy

Serwer (Oracle A1, Ubuntu ARM64) czuwa bez terminala: pobiera nowe odcinki obserwowanych serii przez VPN,
robi lektora tym samym rdzeniem, wysyła MP4 na Google Drive, sprząta po sobie. Właściciel ogląda na telefonie
z Drive i ma te same pliki na komputerze po synchronizacji. Lokalny tryb Windows działa dalej niezależnie.

## Źródła celu i ograniczeń

[spec.md](spec.md), [research.md](research.md), ustalenia właściciela U15–U16 w
[../automation/specification.md](../automation/specification.md), wykonane plany 01–04 w
[../local-automation/](../local-automation/README.md).

## Aktualny zaakceptowany stan

- działa i zostało zaakceptowane: lokalne czuwanie, wyszukiwanie, pobieranie, subskrypcje (plany 01–04, PR #51/#52,
  odbiór klawiaturą właściciela w toku);
- pozostaje niepewne: tenancja właściciela (Always Free czy PAYG), zgoda na VPN, czas enkodowania MP4 na A1,
  dostępność edge-tts/ElevenLabs z adresów Oracle;
- blokery: brak instancji Oracle i poświadczeń w sesji agenta; etapy 02–05 wymagają dostępu SSH do serwera
  albo wykonania kroków przez właściciela według instrukcji.

## Etapy

| Nr | Etap | Rezultat | Zależności | Warunek wyjścia | Status |
| --- | --- | --- | --- | --- | --- |
| 01 | Tryb bez okna | `watch --headless` wykonuje partie w procesie, loguje wynik, działa bez TTY; jednostka systemd i doctor dla Linuksa w repo | plany 01–04 | test integracyjny headless zielony na Windows; `mypy --platform linux`; smoke `anishift watch --headless` z syntetycznym plikiem | current |
| 02 | Proof na instancji | AniShift zainstalowany na jednej instancji Oracle z `apt` binariami, `uv`, `.env`; `doctor` zielony; jeden ręcznie wrzucony MKV przechodzi Auto do MP4 | 01, instancja od właściciela | log `Batch finished exit 0`, MP4 odtwarzalny; pomiar czasu enkodowania i RAM | planned |
| 03 | Dostawa na Drive | preset `remote`, rclone, ledger `delivered.json`, weryfikacja hash, `delivery list/retry`, retencja | 02, remote rclone od właściciela | odcinek pojawia się w `AniShift/<Seria>/`, odtwarza się na telefonie, źródło znika po progu | planned |
| 04 | Pobieranie na serwerze | qbittorrent-nox za WireGuard z kill-switchem, subskrypcje na serwerze, progi dysku | 02, decyzja VPN | nowy odcinek obserwowanej serii ląduje na Drive bez ingerencji; test kill-switch: bez tunelu klient nie ma sieci | blocked (VPN) |
| 05 | Operacje | skrypt aktualizacji, logrotate, alert budżetu, ochrona przed reclaim, dokument „jak odtworzyć serwer” | 03, 04 | tydzień bez ingerencji, doctor zielony, dysk poniżej progu | planned |
| 06 | Strona domowa | Drive → komputer, lokalny watch nie dubluje pracy, lista dostarczonych w Home | 03 | właściciel widzi te same pliki na komputerze bez ręcznego kopiowania | planned |

## Aktualny etap

**Etap:** 01 Tryb bez okna — [plans/01-headless-worker.md](plans/01-headless-worker.md).

**Dlaczego teraz:** to jedyny etap bez serwera, usuwa fundamentalną zależność od Prompt Toolkit w czuwaniu
i daje kod, który na instancji trzeba tylko uruchomić.

**Największa niewiadoma:** czy wykonanie partii w procesie czuwania nie psuje reguły „jedno okno naraz”
i anulowania; rozstrzyga test z fałszywą partią i z sygnałem stop w trakcie.

**Następny artefakt lub decyzja:** po odbiorze 01 właściciel podaje adres instancji lub wykonuje
`docs/plans/remote-automation/deploy.md` krok po kroku; decyzja VPN przed etapem 04.

## Późniejsze etapy

Etap 02 mierzy, nie projektuje: czas MP4, RAM, czy API odpowiadają. Etap 03 dodaje jeden moduł
`application/delivery.py` i komendę `delivery`; rclone jest wywoływany jak inne binaria. Etap 04 to głównie
konfiguracja systemu (WireGuard, policy routing, systemd `After=`), w AniShift tylko doctor i progi dysku.
Etapy 05–06 to skrypty i dokumentacja; kod AniShift zmienia się minimalnie.

## Ryzyka kierunku

| Ryzyko | Jak je rozpoznać | Reakcja |
| --- | --- | --- |
| Oracle reclaimuje bezczynną instancję | instancja znika po tygodniu; `doctor` niedostępny | PAYG z alertem 0 USD; skrypt odtworzenia instancji (etap 05) |
| Ban za torrent | e-mail DMCA, instancja zablokowana | VPN z kill-switchem przed etapem 04; bez VPN etap 04 nie startuje |
| ARM za wolny na enkod MP4 | etap 02: > 30 min na odcinek | `composition_quality_preset` szybszy, remux zamiast enkodu gdy źródło to H.264 |
| API TTS/LLM blokują adresy chmury | błędy 403/429 w logu etapu 02 | zmiana silnika (edge → ElevenLabs lub odwrotnie); ostatecznie TTS lokalnie, upload tylko z serwera |
| 200 GB pełne | `doctor` dysk poniżej progu, pobrania wstrzymane | retencja z etapu 03; niższy próg seedowania |
| Drive nie odtwarza MP4 na telefonie | test w etapie 03 | profil H.264 High/AAC stereo w presecie `remote`; sprawdzić poziom H.264 |

## Historia materialnych zmian kierunku

| Data | Zmiana | Dowód / powód | Wpływ |
| --- | --- | --- | --- |
| 2026-09-06 | Powrót do VPS po lokalnym pakiecie, który VPS wykluczał | polecenie właściciela: „automatyzacja na VPS Oracle, produkt na Google Drive” | nowy pakiet; lokalny pozostaje bez zmian |
| 2026-09-06 | Pierwszy etap bez serwera (headless) zamiast instalacji instancji | brak dostępu do Oracle w sesji; headless testowalny lokalnie | etap 02 czeka na właściciela |

## Nierozstrzygnięte decyzje

- VPN: dostawca i zgoda na koszt (blokuje etap 04).
- Tenancja: Always Free czy PAYG (wpływa na etap 05).
- Cel dostawy: Mój dysk czy dysk współdzielony (konfiguracja rclone w etapie 03).
