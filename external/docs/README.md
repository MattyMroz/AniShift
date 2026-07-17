# external/docs/

Official documentation for the binaries in `bin/`, extracted from the very
archives `bin_hashes.json` pins — so these pages describe the exact versions
the app downloads and runs, not whatever is current upstream.

```text
docs/
├── mkvtoolnix/     # from mkvtoolnix-64-bit-100.0.zip (doc/en/)
│   ├── mkvextract.html
│   └── mkvmerge.html
└── ffmpeg/         # from ffmpeg-N-125628-ga5e6c0175a-win64-gpl.zip (doc/)
    ├── ffmpeg.html
    ├── ffprobe.html
    ├── ffmpeg-filters.html
    ├── ffmpeg-codecs.html
    ├── ffmpeg-formats.html
    └── ffmpeg-utils.html
```

## Why these are in git

The pipeline drives both tools as subprocesses, so their command-line contract
*is* our contract. Reading it beats guessing: the port from mm_avh inherits
workarounds whose necessity was never checked against the manual, and a flag we
never knew existed is indistinguishable from a flag that does not exist.

Keeping the pages next to the manifest pins them to a version. Reading the same
docs online answers a question about a different build.

## Refreshing

When `bin_hashes.json` moves to a new version, re-extract from the new archive
rather than downloading from the projects' websites — same file, same hash,
guaranteed to match.

Only the pages the pipeline actually needs are kept; both archives ship far more
(translations, GUI manuals, ffplay).
