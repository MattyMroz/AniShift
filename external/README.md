# external/

External binaries live here — outside the Python package and outside git.

```text
external/
├── README.md          # this file (tracked)
├── bin_hashes.json    # SHA256 + size + source URL per file (tracked)
├── docs/              # official manuals for the pinned versions (tracked)
│   ├── mkvtoolnix/    # mkvextract, mkvmerge
│   └── ffmpeg/        # ffmpeg, ffprobe, filters, codecs, formats, utils
└── bin/               # binaries themselves (gitignored)
    ├── mkvtoolnix/    # mkvextract, mkvmerge
    ├── ffmpeg/        # ffmpeg, ffprobe
    ├── 7zip/          # 7zr.exe, 7z.exe, 7z.dll
    └── qbittorrent/   # qbittorrent.exe, qt.conf
```

## Why not in git

Binaries are large and platform-specific. Instead of committing them, the repo
ships `bin_hashes.json` — a manifest of the exact files needed (SHA256 + size +
official download URL). `anishift setup` downloads the missing binaries and
verifies each against its hash. `anishift doctor` reports what is present.

On Linux, `mkvtoolnix` and `ffmpeg` from the system package manager (on `PATH`)
are used as a fallback when not bundled here.

The resident prepares its own qBittorrent 5.2.3 on the first download
order. The installer verifies the official Windows distribution, then extracts
the executable and Qt configuration without running a system installer. It uses
verified 7-Zip 26.03 tools: `7zr.exe` extracts `7z.exe` and `7z.dll`, which extract
the qBittorrent distribution. Helpers stay in `bin/7zip/` and the client stays in
`bin/qbittorrent/`; only extraction staging uses temporary directories.

The private profile is in `config/qbittorrent/`, or the corresponding directory
under `ANISHIFT_CONFIG_DIR`. It has its own credentials, ports and torrent
history. Media go to the workspace. `anishift doctor` checks binary
readiness without installing or starting the client.
