# Stage 6 TTS performance optimization

## 1. Goal

Reduce the cold ElevenBytes end-to-end runtime for:

`workspace/[shisha] Youjo Senki II - 01.mkv`

without increasing the provider concurrency above 85 and without weakening the
correctness guarantees of TTS resume, cancellation, retry, audio layout, or
atomic output publication.

The minimum accepted improvement is 2 seconds against the measured AniShift
cold baseline. The preferred improvement is 4–6 seconds.

## 2. Benchmark contract

Every accepted measurement must:

1. use the `elevenbytes/run6` engine and the Dallin voice;
2. use provider concurrency 85;
3. remove exactly
   `workspace/tmp/scope-2c257d7818eef544fa93cd72`
   before the run;
4. preserve the source MKV;
5. run the real pipeline, including extraction, TTS, normalization, timeline,
   mix, final validation, and atomic output replacement;
6. report wall time and phase timestamps;
7. reject resume/cache hits as performance evidence;
8. preserve the final sidecar only when it passes the existing output checks.

Network variance means a single result is not enough to attribute a small gain.
Changes are compared using repeated cold runs and phase-level timings.

## 3. Baseline

Cold AniShift run:

| Phase | Measured wall time |
| --- | ---: |
| Extraction and TTS setup | about 0.83 s |
| ElevenBytes request stream and TTS commit | about 13.20 s |
| Audio normalization, timeline, mix, and validation | 4.89 s |
| Full pipeline | 19.12 s |

Observed checkpoints:

- first committed TTS clip: 2.68 s;
- final committed TTS clip: 14.03 s;
- audio normalization phase: 14.43 s;
- timeline phase: 14.60 s;
- mixing phase: 16.63 s;
- completed output: 19.11 s.

Historical references:

- user-observed AniShift run: about 17.69 s;
- old `mm_avh` run: about 14.70 s.

The old implementation also uses a rolling pool with 85 active requests. It
does not wait for an entire wave of 85 requests before scheduling the next one.

## 4. Correctness invariants

Optimization must preserve all of the following:

- no more than 85 simultaneous provider requests;
- a completed provider request frees capacity immediately;
- retry work has priority over new work;
- provider retry and circuit-breaking remain owned by the shared scheduler;
- malformed or incomplete provider audio is never committed;
- an invalid result remains eligible for typed retry;
- late results cannot commit after cancellation;
- every committed clip is owned by the current scope and request identity;
- resume hits are fully revalidated before reuse;
- manifest snapshots remain atomic and crash-safe;
- final audio replaces the destination only after validation;
- the final duration remains the maximum of source audio and narrator;
- the channel map and narrator placement remain explicit;
- Ctrl+C remains responsive and stops subprocesses;
- progress callbacks remain observers and cannot own execution.

## 5. Confirmed waste

### 5.1 Duplicate fresh-clip validation

The fresh provider path currently performs:

1. FFprobe in `_ProviderAttempt.accept_result`;
2. full FFmpeg decode in `_ProviderAttempt.accept_result`;
3. the same FFprobe again in `TtsResumeRepository.commit_clip`;
4. the same full FFmpeg decode again in `TtsResumeRepository.commit_clip`.

For 336 single-part events this means 672 FFprobe processes and 672 full decode
processes before normalization.

The second validation does not add information when the same owned temporary
path is committed unchanged. The validated metadata should travel with that
exact path to the repository. Multi-part output remains different: the joined
artifact must be validated because it is a newly created file.

### 5.2 Validation occupies provider workers

The scheduler has 85 workers. Each worker currently waits for local FFprobe and
decode after the HTTP response before it can fetch another provider request.
Consequently the actual network concurrency falls while local validation is in
progress.

Acceptance should be separated from provider-request capacity:

- at most 85 provider calls remain active;
- after a response arrives, the network slot becomes available immediately;
- validation continues as tracked local work;
- only validated work can finish or retry;
- close and cancellation wait for or cancel tracked acceptance tasks.

This change is more invasive than removing duplicate validation and therefore
follows it only if measurements show a remaining provider-slot stall.

### 5.3 Large intermediate narrator

The audio scope writes roughly 320 MiB of uncompressed narrator data, wraps it
as WAV, probes and decodes it, then FFmpeg reads it again to produce the final
E-AC-3 sidecar.

Possible future optimization:

- stream the raw narrator timeline directly into the final render process;
- avoid the raw PCM → narrator WAV → final read round trip;
- retain an optional resumable narrator artifact only when needed;
- validate the final product exactly as today.

This has a potentially large gain but changes the audio artifact lifecycle, so
it must not be mixed into the first low-risk TTS optimization.

## 6. Ranked implementation plan

### Iteration A — reuse one trusted validation

1. Introduce an internal validated-temporary-clip receipt.
2. Bind it to the exact owned temporary path and expected format.
3. Produce it during provider-result acceptance.
4. Store it with that attempt only.
5. Pass it to `commit_clip` for the unchanged single-part artifact.
6. Make `commit_clip` validate normally when no receipt is supplied.
7. Make joined multi-part artifacts validate normally.
8. Test that a fresh single-part success invokes the validator once.
9. Test that invalid audio is discarded and retried.
10. Test that direct repository callers cannot commit an unrelated path through
    a receipt.

Expected result: remove 336 FFprobe and 336 decode subprocesses without changing
the acceptance standard.

### Iteration B — keep all 85 provider slots productive

Only if Iteration A does not meet the target:

1. Track acceptance tasks separately from provider workers.
2. Return the provider worker to the ready queue immediately after HTTP.
3. Keep the admission permit until acceptance reaches a terminal result.
4. Route validation failure through the existing typed retry path.
5. Preserve retry-first priority.
6. Include acceptance tasks in close and cancellation.
7. Test delayed validation with a fake engine to prove that the next provider
   call begins before validation finishes.
8. Test that provider calls never exceed 85.

Expected result: overlap network requests with local FFmpeg validation.

### Iteration C — reduce manifest and filesystem overhead

1. Keep the current one-snapshot-per-batch manifest behavior.
2. Measure hashing and snapshot time rather than guessing.
3. Avoid reloading unchanged process-local state during a single-writer batch
   only if profiling proves it material.
4. Preserve atomic replace and orphan recovery.

### Iteration D — remove the 320 MiB narrator round trip

Only if the TTS-side changes still leave at least 2 seconds of avoidable audio
work:

1. add a streaming narrator source accepted by the render command;
2. write timeline PCM into FFmpeg stdin or a bounded pipe;
3. mix and encode while timeline data is produced;
4. keep deterministic serialization and channel mapping;
5. preserve `duration=longest`;
6. preserve cancellation, timeout, and process cleanup;
7. validate and atomically publish only the final sidecar;
8. benchmark disk traffic and wall time;
9. retain the current file-based path as a fallback until equivalence tests are
   green.

## 7. Rejected shortcuts

- Increasing concurrency above 85.
- Trusting only HTTP status or MIME type.
- Removing full decode validation without another equivalent validation point.
- Committing audio before cancellation and ownership checks.
- Counting a resume hit as an optimization.
- Skipping final E-AC-3 validation.
- Deleting all workspace temporary data instead of the exact benchmark scope.
- Comparing runs made with different voices, models, source files, or settings.
- Changing output codec or quality to win the benchmark.

## 8. Verification

Focused tests:

- TTS service success, retry, cancellation, and resume;
- scheduler concurrency, priority, close, and cancellation;
- audio normalization and final output;
- the exact live ElevenBytes cold smoke run.

Repository gates:

```text
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

## 9. Decision log

- Provider concurrency remains 85.
- Clean-scope live tests are required.
- Strong validation remains required.
- The first implementation is trusted validation reuse because it removes
  confirmed duplicate work without changing scheduling or audio semantics.
- Network/validation overlap is second because it changes scheduler lifecycle.
- Streaming final render is third because it changes audio resume semantics.

## 10. Implemented results

### 10.1 Trusted validation receipt

Implemented:

- fresh provider output is fully probed and decoded once;
- the result is bound to the repository instance, exact resolved path, format,
  file size, and modification timestamp;
- an unchanged single-part artifact reuses that receipt at commit;
- a missing, foreign, or stale receipt falls back to normal full validation;
- joined multi-part output still receives its own full validation;
- resume hits retain their existing integrity checks.

Focused tests prove that a normal single-part synthesis invokes the validator
once and that existing retry/resume/cancellation behavior remains green.

### 10.2 Provider and acceptance overlap

Implemented:

- the scheduler still has exactly `max_concurrency` provider workers;
- after the HTTP result arrives, acceptance runs as separately tracked work;
- the provider worker can immediately fetch the next ready request;
- the admission permit remains held until acceptance succeeds, retries, or
  fails;
- close waits for provider workers and tracked acceptance tasks;
- retry continues through the existing typed scheduler path.

A deterministic test with provider concurrency one proves that request two
starts while request one is still being accepted and that active provider work
never exceeds one.

### 10.3 ElevenBytes connection reuse

Implemented:

- HTTP transport retries remain zero;
- maximum connections equal configured TTS concurrency;
- maximum retained keep-alive connections also equal configured concurrency;
- the Dallin benchmark remains capped at 85.

### 10.4 Local audio work

Implemented:

- fresh narrator metadata obtained before atomic publication is reused instead
  of probing the same narrator again;
- fresh FFmpeg-produced narrator and final sidecar use producer success,
  non-empty artifact checks, FFprobe metadata, semantic format/layout/duration
  validation, and atomic publication;
- full decode remains enabled for provider output and resume artifacts;
- exact source duration is measured using a complete packet-copy scan;
- packet scan failure or incomplete progress falls back to the previous full
  decode implementation.

The packet scan is important for raw VBR AAC: ordinary FFprobe metadata was
observed to under-report this episode by about 20.5 seconds, while packet-copy
scan matched the full decode duration.

### 10.5 Single-process MP3 validation

Implemented:

- provider MP3 keeps a complete FFmpeg decode before it can be committed;
- the same decode reports the exact decoded duration;
- sample rate and channel count come from two consecutive MPEG Layer III frame
  headers rather than a separate FFprobe process;
- an optional ID3v2 tag is skipped using its sync-safe declared size;
- malformed headers, inconsistent consecutive frames, incomplete decode, and
  unsupported non-MP3 data remain validation failures;
- non-MP3 provider formats retain the previous FFprobe plus FFmpeg path.

Across the 336 Dallin clips, the MPEG reader agreed with FFprobe for every
sample. Three local runs of the previous validation took 3.46, 3.50, and
4.26 seconds. Three runs of the single-process validation took 2.24, 1.89, and
1.80 seconds.

## 11. Cold benchmark results

All accepted runs removed exactly the required scope before execution and
processed all 336 spoken events through the real ElevenBytes pipeline.

| Variant | Full wall time | TTS terminal | Audio tail | Notes |
| --- | ---: | ---: | ---: | --- |
| Initial baseline | 19.12 s | 14.03 s | 4.89 s | duplicate validation |
| Validation receipt | 16.29 s | 11.46 s | 4.83 s | 2.83 s faster |
| Network-slow sample | 26.17 s | 21.29 s | 4.88 s | rejected as comparison evidence |
| Full optimized sample A | 21.15 s | 17.41 s | 3.74 s | provider network slow |
| Full optimized sample B | 15.44 s | 12.22 s | 3.22 s | 3.68 s faster |
| Single-process MP3 sample A | 33.25 s | 30.14 s | 3.11 s | provider network slow |
| Single-process MP3 sample B | 14.08 s | 10.98 s | 3.10 s | 5.04 s faster |
| Single-process MP3 sample C | 14.03 s | 10.81 s | 3.22 s | 5.09 s faster |

These are individual observations, not a statistically valid before/after
median. The fastest optimized observation is 14.03 seconds, 5.09 seconds below
the single clean 19.12-second baseline and about 3.66 seconds below the earlier
17.69-second AniShift observation. The 21-33 second samples demonstrate that
provider variance can dominate wall time. Deterministic evidence is the local
validation benchmark plus focused concurrency tests; the two network-comparable
single-process MP3 runs were independently within 0.05 seconds of each other.

## 12. Deferred performance work

The following work is promising but intentionally deferred because it requires
a larger correctness surface:

1. batch 16-32 clip normalizations into fewer FFmpeg processes with command
   length guards and per-item fallback;
2. remove the raw PCM to narrator WAV to final read round trip through a bounded
   streaming render path;
3. consolidate progress callback offloads and remove the current quadratic
   snapshot construction;
4. cache process-local resume manifest parsing while retaining external change
   detection;
5. reuse already calculated clip hashes across TTS, normalization, and
   narration fingerprints.
