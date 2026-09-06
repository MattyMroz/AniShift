---
kind: runbook
status: current
updated: 2026-09-06
---

# Deploy: AniShift watch on Ubuntu 24.04 LTS ARM64

Installs one headless worker: the same repository, the same `workspace/<Series>/` layout, a systemd unit
running `anishift watch --headless`. Delivery to Drive, retention and the VPN tunnel belong to later plans;
this runbook stops at a worker that processes what lands in its workspace.

Every command runs over SSH on the server. Nothing here writes a secret into the repository.

## 1. User and directories

```bash
sudo adduser --system --group --home /srv/anishift --shell /usr/sbin/nologin anishift
sudo mkdir -p /srv/anishift/app /srv/anishift/workspace
sudo chown -R anishift:anishift /srv/anishift
```

`/srv/anishift/app` holds the checkout, `/srv/anishift/workspace` the library. They stay separate so an
update never touches media.

## 2. External binaries

```bash
sudo apt update
sudo apt install -y ffmpeg mkvtoolnix git
```

`anishift setup` downloads binaries on Windows only; on Linux the resolver takes `ffmpeg`, `mkvextract`
and `mkvmerge` from `PATH`, which is what the doctor then reports.

## 3. uv and the checkout

```bash
sudo -u anishift -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u anishift -H git clone https://github.com/<owner>/AniShift.git /srv/anishift/app
sudo -u anishift -H bash -lc 'cd /srv/anishift/app && ~/.local/bin/uv sync --frozen'
```

`uv sync --frozen` creates `/srv/anishift/app/.venv` from the committed lock, which is the interpreter the
unit runs.

## 4. Credentials

```bash
sudo -u anishift -H touch /srv/anishift/app/.env
sudo -u anishift -H chmod 600 /srv/anishift/app/.env
sudo -u anishift -H editor /srv/anishift/app/.env
```

The file holds one `NAME=value` line per credential the worker needs. These are the variable names the
doctor reports; fill in only the ones the configured engines use, and never commit the file:

```text
ANISHIFT_DEEPL_API_KEY
ANISHIFT_ELEVENLABS_API_KEY
ANISHIFT_ANTHROPIC_API_KEY
ANISHIFT_GEMINI_API_KEY
ANISHIFT_OPENAI_API_KEY
ANISHIFT_DEEPSEEK_API_KEY
ANISHIFT_OPENROUTER_API_KEY
ANISHIFT_OPENAI_COMPATIBLE_API_KEY
ANISHIFT_QBITTORRENT_URL
ANISHIFT_QBITTORRENT_USERNAME
ANISHIFT_QBITTORRENT_PASSWORD
```

The Windows `sapi` voice does not exist here, so the TTS engine in `config/settings.json` must be one of
`edge`, `elevenbytes` or `elevenlabs`.

## 5. The remote preset

The watch runs the default preset of `config/presets.json`. The remote worker produces an MP4 with the
Polish lector, so the phone can play it, and keeps the narration track beside it:

```json
{
  "schema_version": 1,
  "default_preset_id": "remote",
  "presets": [
    {
      "preset_id": "remote",
      "name": "Remote lector",
      "products": {
        "requested_products": ["mp4", "narration_audio"],
        "burn_subtitle_product": "none",
        "mkv_tracks": [],
        "mp4_audio_source": "narration"
      },
      "subtitle_source_policy": "auto",
      "translation_action": "auto",
      "source_subtitle_language": null,
      "subtitle_output_format": "preserve"
    }
  ]
}
```

```bash
sudo -u anishift -H editor /srv/anishift/app/config/presets.json
```

`default_preset_id` must name a preset in the same file, otherwise the file is rejected and the bundled
default runs instead.

## 6. Diagnostics before the service

```bash
sudo -u anishift -H bash -lc 'cd /srv/anishift/app && ANISHIFT_WORKSPACE_ROOT=/srv/anishift/workspace .venv/bin/anishift doctor'
```

Expected on this system: `binaries: ffmpeg, mkvextract, mkvmerge from PATH`, `api_keys: configured: ...`,
`workspace: workspace ready at /srv/anishift/workspace`, `torrent_client: qBittorrent is managed on
Windows only`, `autostart: systemd manages the service on this system`. A `FAIL` row exits non-zero; fix
it before installing the unit.

## 7. The unit

```bash
sudo install -m 644 /srv/anishift/app/deploy/anishift-watch.service /etc/systemd/system/anishift-watch.service
sudo systemctl daemon-reload
sudo systemctl enable --now anishift-watch
systemctl status anishift-watch
journalctl -u anishift-watch -f
```

Adjust `User`, `WorkingDirectory`, `Environment` and `ExecStart` in the installed copy if the paths differ.
The unit starts after `network-online.target` and `qbittorrent-nox.service`; drop the latter from `After=`
while no torrent client runs on the server.

## 8. Verify with a probe file

```bash
sudo -u anishift -H mkdir -p /srv/anishift/workspace/Test
sudo -u anishift -H cp <one small episode> /srv/anishift/workspace/Test/
journalctl -u anishift-watch -f
```

A source group becomes a candidate ten seconds after its last change, so the log answers within about
twenty seconds:

```text
Watch started            headless=true
Batch started            groups=1
Stage started            stage=extract_subtitles group=...
Stage finished           stage=extract_subtitles group=... ok=true
Batch finished           groups=1 exit_code=0
```

`exit_code` is `0` for a full success, `1` for a refusal before the run, `3` for a failed or partial run
and `4` for a cancelled one. Products land beside the source in `/srv/anishift/workspace/Test/`.

## 9. Stopping

`anishift watch stop` writes a flag the loop reads between scans; the daemon finishes the running batch,
cancels it when one is still open, records its exit code and leaves with `0`:

```bash
sudo -u anishift -H bash -lc 'cd /srv/anishift/app && .venv/bin/anishift watch stop'
```

`systemctl stop anishift-watch` is the harder variant: systemd sends `SIGTERM`, which ends the process
without waiting for the current batch. Use `watch stop` first when a batch may be running, then
`systemctl stop` to keep systemd's own state in sync. `systemctl restart` covers both after an update.

## 10. Update

```bash
sudo -u anishift -H bash -lc 'cd /srv/anishift/app && .venv/bin/anishift watch stop && git pull && ~/.local/bin/uv sync --frozen && ANISHIFT_WORKSPACE_ROOT=/srv/anishift/workspace .venv/bin/anishift doctor'
sudo systemctl restart anishift-watch
```

A non-zero doctor stops the update before the restart.
