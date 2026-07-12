# external/

External binaries live here — outside the Python package and outside git.

```
external/
├── README.md          # this file (tracked)
├── bin_hashes.json    # SHA256 + size + source URL per file (tracked)
└── bin/               # binaries themselves (gitignored)
    ├── mkvtoolnix/    # mkvextract, mkvmerge
    ├── ffmpeg/        # ffmpeg, ffprobe
    └── balabolka/     # balcon.exe (Windows-only)
```

## Why not in git

Binaries are large and platform-specific. Instead of committing them, the repo
ships `bin_hashes.json` — a manifest of the exact files needed (SHA256 + size +
official download URL). `anishift setup` downloads the missing binaries and
verifies each against its hash. `anishift doctor` reports what is present.

On Linux, `mkvtoolnix` and `ffmpeg` from the system package manager (on `PATH`)
are used as a fallback when not bundled here.
