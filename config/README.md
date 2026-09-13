# config/

Preferences and hand-written runtime files live here, not in `workspace/`.

This directory holds every hand-editable runtime file AniShift keeps next to
the code:

- `settings.json` stores workflow and engine preferences;
- `presets.json` stores reusable run presets and the default preset;
- `anishift.models.jsonc` is the local model catalog copied from
  `anishift.models.example.jsonc`;
- `subscriptions.json` stores followed series and episode scheduling;
- `watch/` stores resident control state and its local endpoint credentials;
- `qbittorrent/` stores the resident's private client profile, process
  receipt and credentials. The executable is in `external/bin/qbittorrent/`.

`ANISHIFT_CONFIG_DIR` replaces this directory entirely, so a test or a second
account can keep its own preferences, watch state and subscriptions elsewhere.

`watch/runs/` holds processing checkpoints and `watch/relocations/` holds unfinished
moves into `workspace/ready/`. These contain state, never media.
Shared locations are defined in `anishift/paths.py`; resolving a path does not create it.
Durable products are published beside their source and collect in `workspace/ready/`, never here.
Per-machine files are gitignored; only this README and the model-catalog
example are tracked.

The private torrent profile is restricted to the current account. Its first
creation imports only speed and connection-count preferences from an existing
personal qBittorrent profile. It does not import torrents, history, credentials,
ports or media paths. Downloads run concurrently; completed torrents stop
seeding, and only a proven, idle private process is shut down. The personal
client is not stopped or reconfigured.

## LLM translation prompts

Translation prompts are versioned application resources under
`anishift/services/translation/engines/llm/prompts/`, not runtime config.
The fixed files are `system.md`, `translation.md` and `retry.md`; selectable
styles are immediate `styles/*.md` files.

`settings.json` stores only the selected style name in
`llm_translation_style`. To add a style, add and ship another UTF-8 Markdown
file in the module's `styles/` directory. Missing, empty or invalid packaged
resources are configuration errors.
