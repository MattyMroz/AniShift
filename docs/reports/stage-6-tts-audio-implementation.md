# Stage 6 TTS and Audio Implementation Report

Date: 2026-07-29

Branch: `feature/tts-audio`

Validated implementation HEAD: `0b2fdd3`

## Outcome

Stage 6 now provides a provider-neutral TTS API, four engine adapters, persistent
clip resume, deterministic subtitle-to-speech mapping, serialized narration
timelines, original-audio mixing, six output profiles, pipeline streaming,
terminal settings and recovery.

The final real-episode run completed for both the already-Polish and translated
paths. Both resulting E-AC-3 sidecars pass full FFmpeg decode and strict FFprobe
validation.

## Implemented boundaries

- `anishift.services.tts`
  - lazy engine registry;
  - shared configuration, typed failures and availability;
  - concurrent scheduler, retry ownership and provider circuit;
  - cancellation and late-result commit gate;
  - persistent clip manifest, fingerprints and resume;
  - Edge, ElevenBytes, official ElevenLabs and Windows SAPI adapters.
- `anishift.services.audio`
  - provider-clip normalization;
  - stable no-truncation timeline;
  - narrator PCM and RF64-safe WAV;
  - explicit mono, stereo, 5.1 and 7.1 channel plans;
  - original-plus-narrator mixing;
  - MP3, WAV, E-AC-3, Opus, FLAC and M4A AAC output;
  - validated atomic output replacement and resume.
- Pipeline and CLI
  - immediate TTS enqueue after Polish spoken text becomes available;
  - natsorted file admission;
- one progress row per file across extraction, translation, TTS and audio in
  automatic mode;
  - provider-wide recovery with retry, settings and finish actions;
  - aggregate provider, request, retry, timing and drift summaries.

## Real episode validation

Engine: Edge

Model: `edge-default`

Voice: `pl-PL-MarekNeural`

Native settings: `+40%` rate, `+0%` volume, `+0Hz` resolved pitch

Output: E-AC-3, 48 kHz, stereo, 384 kb/s

| Source | Path | Spoken events | Final successful TTS | Retries | Result |
|---|---|---:|---:|---:|---|
| `[shisha] Youjo Senki II - 01.mkv` | already Polish | 336 | 336 resume hits, 0 new calls | 0 | done |
| `[SubsPlease] Mushoku Tensei S3 - 03 (1080p) [8488B15C].mkv` | Gemini translation | 348 | 226 resume hits, 122 new calls | 0 | done |

The translated rerun produced some different Polish lines, so 122 exact TTS
fingerprints changed and were synthesized again. The other 226 clips were reused.
The already-Polish source reused all 336 clips without another provider request.

### Wall-clock runs

| Run | Duration | Purpose | Outcome |
|---|---:|---|---|
| Initial full synthesis | 03:08 | 684 Edge clips and first audio render | exposed inaccurate ADTS AAC duration validation |
| Diagnostic resume | 01:31 | verify clip and narrator resume | reproduced the audio-only failure |
| Final validation | 01:28 | resume, exact duration, mix and commit | both files done |

These are whole harness wall times, not isolated provider benchmarks.

### Final sidecars

| Sidecar | Size | MKV duration | Sidecar duration | Difference | Decode |
|---|---:|---:|---:|---:|---|
| `[shisha] Youjo Senki II - 01.eac3` | 68,163,072 B | 1420.053 s | 1420.064 s | +11 ms | pass |
| `[SubsPlease] Mushoku Tensei S3 - 03 (1080p) [8488B15C].eac3` | 68,166,144 B | 1420.109 s | 1420.128 s | +19 ms | pass |

FFprobe confirmed `eac3`, `48000 Hz`, two channels, `stereo` and `384000 b/s`
for both files. FFmpeg decoded both complete sidecars to the null sink without
an error.

## Defects found by real validation

### Partial Edge native settings

The persisted Edge profile supplied rate and volume while omitting pitch. Edge
correctly resolved pitch to `+0Hz`, but request validation compared the partial
tuple with the fully resolved tuple and rejected every request.

The adapter now:

- validates each explicitly supplied native field independently;
- inherits omitted fields from resolved engine configuration;
- stores fully resolved rate, volume and pitch in the canonical synthesis
  fingerprint.

Regression coverage verifies the partial profile and resolved fingerprint.

### Inaccurate raw ADTS AAC duration

FFprobe estimates duration from bitrate for raw ADTS AAC and can be substantially
wrong:

- Youjo metadata reported 1399.538 s while full decode reported about 1420.053 s;
- Mushoku metadata reported 1361.646 s while full decode reported about 1420.109 s.

The previous strict output validator rejected the correctly rendered sidecars.
AniShift now measures original-audio duration from a complete FFmpeg decode and
uses metadata probing only for codec and channel layout.

The integration regression creates a real VBR ADTS AAC file whose metadata says
about 137 seconds although it decodes to about 20 seconds. The final E-AC-3 must
match decoded duration within the existing 32 ms tolerance. The tolerance was
not weakened.

## Post-validation corrections

- ElevenBytes `run6` returns valid MP3 bytes with an incorrect
  `Content-Type: text/html` header. AniShift now validates the MP3 signature
  before considering the header. A real adapter request produced a decodable
  36,824-byte MP3 lasting about 2.23 seconds.
- The ElevenBytes profile default is now 16 workers. The earlier live benchmark
  proved concurrency up to 12; 16 is a later user-selected, configurable
  performance default, not a claimed live benchmark result.
- Every committed provider clip enters one run-scoped normalization pool
  immediately while the remaining TTS requests continue. The global pool is
  capped at 16 across all active files, and the final render reuses the prepared
  PCM without a second transcode.
- A 64-clip normalization benchmark improved from about 5.70 seconds
  sequentially to about 0.39 seconds with 16 workers. All 336 cached clips from
  the reference episode normalized in about 2.05 seconds.
- Exact TTS resume hits reuse metadata from the already validated manifest after
  checking the path, size and SHA-256. The reference ElevenBytes resume run
  completed 336 clips with zero provider calls in 6.24 seconds total, including
  2.33 seconds reported for Audio.
- A validated new `{stem}.<codec>` atomically replaces an existing sidecar even
  without an AniShift ownership record. Render or validation failure preserves
  the previous target bit for bit.
- The official ElevenLabs selector lists the three current Polish TTS models:
  Multilingual v2, Flash v2.5 and Eleven v3. A shared 5,000-character request
  limit prevents oversized Eleven v3 calls.

## Automated verification

Final repository gates:

```text
ruff check: pass
ruff format --check: pass
mypy: pass
pytest: 1564 passed, 8 skipped
```

The eight skips are five opt-in translation network tests, one unavailable
symlink test and two unavailable directory-symlink resume tests.

Build and packaging:

- `uv build`: pass;
- wheel: `anishift-0.1.0-py3-none-any.whl`;
- 345 wheel entries;
- 59 TTS package entries;
- 16 Audio package entries;
- packaged `sapi_worker.ps1`: present;
- import from a fresh Python 3.14 venv and `site-packages`: pass;
- installed CLI `--help`: pass;
- offline `doctor`: controlled missing-dependency report, no traceback;
- FFmpeg, FFprobe, mkvextract and mkvmerge process leaks after smoke: none.

Provider validation already recorded during implementation:

- ElevenBytes run6 network and concurrency smoke: pass;
- Edge live concurrency and two-episode synthesis: pass;
- SAPI x64/x86 synthesis, decode, timeout and restart: pass;
- official ElevenLabs authenticated metadata probes: pass;
- the single authorized ElevenLabs synthesis POST returned HTTP 400 and produced
  no audio. No second potentially paid POST was made.

## Manual listening checklist

The agent environment cannot hear system audio. Listening is therefore the one
human validation gate that remains.

Open these files with their matching MKVs:

- `workspace/[shisha] Youjo Senki II - 01.eac3`;
- `workspace/[SubsPlease] Mushoku Tensei S3 - 03 (1080p) [8488B15C].eac3`.

Check:

1. the first spoken line and several fast dialogue sequences;
2. overlapping subtitle windows;
3. narration after long silent gaps;
4. the final spoken line and the end of the episode;
5. no clipped words, clicks or artificial chunk pauses;
6. narrator audibility without losing anime music and effects;
7. no obvious clipping;
8. stable stereo image and matching total duration.

## Manual interruption check

Automated cancellation tests cover one cancel request, admission stop, late
result rejection, FFmpeg termination, manifest safety and bounded return. The
real run additionally proved clip reuse after a later audio-stage failure.

For the literal keyboard gate:

1. choose a TTS profile that does not already have cached clips for the source;
2. start one episode and wait for at least 20 committed clips;
3. press `Ctrl+C` once;
4. run the same episode with the same profile;
5. confirm non-zero resume hits and no provider calls for completed request IDs;
6. let it finish and decode-check the sidecar.

## Known limitations

- A complete original-audio decode is now performed before mixing. It was below
  one second for each 23-minute AAC reference track, but it uses the shared
  30-second operation timeout. Exceptionally slow or very long media may later
  need a dedicated duration-measurement timeout.
- A fresh LLM translation is not guaranteed to be byte-identical. Changed lines
  intentionally invalidate only their corresponding TTS fingerprints.
- Drift placements are available on a newly built narration timeline. A pure
  narration/output resume does not currently reload placements from the Audio
  manifest, so the CLI may omit drift metrics on that resume-only run.
- Listening quality and the literal keyboard interruption remain human checks;
  they are not reported as passed by automation.
