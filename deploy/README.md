# deploy

Unit files for an AniShift worker that watches the library without a terminal.
Step-by-step installation: [docs/plans/remote-automation/deploy.md](../docs/plans/remote-automation/deploy.md).

`anishift-watch.service` runs `anishift watch --headless` as the `anishift` user from a
checkout in `/srv/anishift/app` with its workspace in `/srv/anishift/workspace`. Adjust the
paths and the user in the copy, never in the repository file.

```bash
sudo install -m 644 deploy/anishift-watch.service /etc/systemd/system/anishift-watch.service
sudo systemctl daemon-reload
sudo systemctl enable --now anishift-watch
journalctl -u anishift-watch -f
```

The unit owns no secrets: `.env` stays in `/srv/anishift/app/.env`, owned by `anishift` with
mode `600`, and the workspace directory belongs to the same user.
