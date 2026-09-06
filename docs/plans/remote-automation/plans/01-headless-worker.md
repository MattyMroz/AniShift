---
kind: plan
status: proposed
baseline: work/local-automation/05-polish (po planach 01–04)
branch: work/remote-automation/01-headless
created: 2026-09-06
---

# Plan 01: Czuwanie bez okna — partia w procesie, systemd, doctor na Linuksie

## Cel

`anishift watch --headless` czuwa i przetwarza partie bez terminala: zamiast otwierać okno Prompt Toolkit,
uruchamia `prepare_auto_run` + `execute_plan` w tym samym procesie, zapisuje wynik do logu i ledgera i wraca do
skanowania. Repozytorium dostaje jednostkę systemd, doctor rozpoznaje Linuksa (binaria z PATH, brak `schtasks`),
a dokument wdrożenia opisuje instalację na Ubuntu ARM64 krok po kroku. Na Windows tryb headless działa tak samo,
więc całość jest testowalna lokalnie.

## Rezultat użytkownika

- `uv run anishift watch --headless` w terminalu lub w usłudze: log `Watch started (headless)`, po pojawieniu się
  pliku `Batch started (headless, groups=N)`, postęp etapów w logu, `Batch finished exit=0`. Zero okien.
- `anishift watch stop` i `watch status` bez zmian; stop w trakcie partii kończy ją przez cancellation i zapisuje
  kod 4 (cancelled), jak zamknięcie okna dziś.
- Na Linuksie `anishift doctor`: `binaries: ffmpeg, mkvextract, mkvmerge from PATH`, `autostart: skipped (systemd)`,
  `watch`, `torrent client` jak dziś.
- `deploy/anishift-watch.service` (systemd, `User=anishift`, `WorkingDirectory=/srv/anishift/app`,
  `ExecStart=/srv/anishift/app/.venv/bin/anishift watch --headless`, `Restart=on-failure`,
  `After=network-online.target qbittorrent-nox.service`) i `docs/plans/remote-automation/deploy.md`.

## Warunki końcowe

- [ ] H01: `run_daemon(..., batch=run_batch_in_process)` — czuwanie przyjmuje strategię partii; domyślna to dzisiejsze
      okno, `--headless` wybiera wykonanie w procesie; ledger, kody wyjścia, jedna partia naraz i sprawdzanie
      subskrypcji między partiami bez zmian.
- [ ] H02: partia w procesie używa `prepare_auto_run(service, preset, group_ids=..., cancel=token)` i
      `execute_plan(service, plan, sink)`, gdzie sink loguje `Stage started/finished` i błędy grup; kod wyjścia z
      `run_exit_code(result)`; flaga stop w trakcie → `cancel.cancel()` → kod 4.
- [ ] H03: wyjątek w partii (AniShiftError/OSError) nie zabija czuwania: log warning, kod 1 w ledgerze, następny skan.
- [ ] H04: `anishift watch --headless` działa bez TTY (test: `subprocess.run` z `stdin=DEVNULL`, `stdout=PIPE`,
      syntetyczny `workspace/Test/probe.txt`, stop po pierwszej partii).
- [ ] H05: doctor na Linuksie: `check_binaries` mówi „from PATH”, `autostart` → SKIP z powodem, bez importu
      `msvcrt`; `mypy --platform linux` i testy z `sys.platform` monkeypatchowanym na `linux`.
- [ ] H06: `deploy/anishift-watch.service`, `deploy/README.md` (co skopiować, jakie uprawnienia) i
      `docs/plans/remote-automation/deploy.md` (Ubuntu 24.04 ARM64: użytkownik, `apt` binaria, `uv`, klon, `.env`,
      presety, `doctor`, `systemctl enable --now`); żadnych sekretów, żadnych wartości przykładowych kluczy.
- [ ] H07: README sekcja „Watching the library” opisuje `--headless`; AGENTS `cli` i `platform` zaktualizowane;
      bramki root zielone.
- [ ] H08: właściciel: `anishift watch --headless` na Windows przetworzył wrzucony plik bez okna.

## Nie-cel

Dostawa na Drive, retencja, rclone, VPN, qbittorrent-nox, instalator Linuksa, Docker, zmiany w oknie partii.

## Authority i baseline

[spec.md](../spec.md) W01–W03, W07; [research.md](../research.md) fakty o kodzie; kod: `anishift/cli/watch.py`
(`run_daemon`, `_watch_loop`, `Spawner`, `Child`), `anishift/cli/run.py` (`prepare_auto_run`, `execute_plan`,
`RunEventSink`), `anishift/cli/interactive/app.py` (`_finish_batch`, `run_exit_code`), `anishift/setup/doctor.py`,
`anishift/platform/{autostart,binaries}.py`, testy `tests/cli/test_watch_daemon.py`, `tests/cli/test_run.py`.

## Różnica

```text
CURRENT STATE
  _watch_loop → spawner(batch_command(ids)) → osobny proces z oknem Prompt Toolkit → poll() → exit code
    ↓
GAP
  bez TTY okno nie startuje; Linux nie ma schtasks; doctor zakłada binaria z external/
    ↓
TARGET STATE
  _watch_loop → strategia partii: Window (dziś) | InProcess (headless) → oba dają exit code do ledgera
  systemd zamiast schtasks; doctor: PATH na Linuksie
```

## Target design

```text
anishift/cli/watch.py            # MODIFY: BatchRunner Protocol: start(group_ids) -> Child; WindowBatch (spawner, dziś),
                                 #         InProcessBatch(service, stop_check) uruchamia partię w wątku i zwraca Child
                                 #         z poll() → kod po zakończeniu; run_daemon(..., batch: BatchRunner | None)
anishift/cli/headless.py         # NEW: run_batch(service, group_ids, *, cancel, log) -> int  (prepare_auto_run + execute_plan
                                 #      + LoggingSink); jeden moduł, bez Prompt Toolkit
anishift/cli/main.py             # MODIFY: watch --headless; watch batch bez zmian
anishift/setup/doctor.py         # MODIFY: binaria „from PATH” na Linuksie; autostart SKIP poza Windows
deploy/anishift-watch.service    # NEW
deploy/README.md                 # NEW (5–10 linii)
docs/plans/remote-automation/deploy.md   # NEW: instrukcja Ubuntu ARM64
tests/cli/test_watch_daemon.py, tests/cli/test_headless.py, tests/setup/test_doctor.py
```

Reguły: partia w procesie trwa w wątku `anishift-batch`, pętla czuwania dalej co 5 s sprawdza flagę stop i `poll()`;
stop → `cancel.cancel()`; wątek kończy się kodem 4; wyjątek w wątku → kod 1 i `logger.warning`. Sink logu:
`Stage started {stage, group}`, `Stage finished {stage, group, ok}`, `Group failed {group, error_class}` bez ścieżek.
`--headless` na Windows dozwolony (test odbioru H08).

## Wykonanie

1. `headless.py` + `InProcessBatch` + `--headless` z testami (fałszywy serwis jak w `test_watch_daemon.py`).
2. Doctor dla Linuksa z testami monkeypatchującymi platformę.
3. systemd, deploy docs, README/AGENTS.
4. Smoke bez TTY (H04) i próba właściciela (H08).

## Dowód

Unit: strategia partii, stop w trakcie, wyjątek, kody; doctor na `linux`. Integracja: H04 subprocess bez TTY
z fałszywym presetem TXT (jak sonda z planu 01 lokalnego). Human: H08.
