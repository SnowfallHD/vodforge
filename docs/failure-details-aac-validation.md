# Failure details and quiet AAC validation — 2026-09-10

The reported Ocean Sea Waves run (`IxF55qB4CuQ`, formats `137+140-drc`)
finished conversion but failed the MP4 audio-bitrate check. Re-encoding the
same audio with the signed 0.2.0 candidate's bundled FFmpeg produced 2.274
kbps at a requested target of 160 kbps. The old validator required at least
40% of that target. Silence and very quiet AAC can legitimately fall below
that floor; an average bitrate cannot prove that the requested encoder
settings were used. FFmpeg documents bitrate as a target average:
https://github.com/FFmpeg/FFmpeg/blob/master/doc/codecs.texi

The fix removes only the target-relative AAC minimum. Missing, zero,
negative and excessive measured rates still fail. MP3 rate checks and MP4
stream presence, codec, dimensions, profile, duration, sample rate, channels
and metadata validation remain in place. Encoder-command tests continue to
check the requested target. Rate mismatch explanations now include the
measurement so the next failure is diagnosable.

Separately, bounded failure-message changes in `0ce58cd` sent the friendly
summary to the terminal event but left the actual cause only in diagnostics.
Technical reads the run activity, so its request to consult Technical was
circular. Single, playlist-item and batch-terminal failures now emit a
bounded, redacted cause through the existing run-log event before terminal
handling. Friendly presentation and terminal summaries are unchanged.

## Why coverage missed it

- The AAC floor predates 0.2.0 (present in August 29 history). Mock probes
  covered half-target AAC and incorrectly classified lower AAC rates as
  necessarily invalid. The real media corpus uses a steady sine tone.
- Failure tests asserted friendly terminal text, not delivery of the cause
  into run activity. The slider test used manually supplied log strings.
- The slider test file was absent from the required native surface gate.

## Added evidence

Before the fix, new real-encoder silence and quiet-tone cases and the worker
cause-delivery case fail; the steady-tone control passes. The fixed cases
pass. Harness self-tests now encode silence, quiet tone and ordinary tone
through the production command builder, validate the resulting MP4, decode
it fully and reject an incorrect sample-rate plan. Worker/native tests
verify the cause reaches Technical and never enters Friendly. The required
native gate now includes the slider tests.

The exact downloaded ocean source also passes the fixed production command
builder and full artifact validator with the release's bundled FFmpeg and
ffprobe, then decodes without errors. Evidence is retained locally under
`build/aac-failure-repro/`, including before-test failures, exact-source
probe/result and native receipts. This is source/native and real-media
verification, not a rebuilt installed app or a new public release.

## Actionable failure follow-up

The subsequent request expands friendly presentation: failures now pair a
bounded explanation with a next step. The existing failure classifier supplies
all 17 categories, and the presentation mapping is checked against that closed
vocabulary. Disk-space failures recommend freeing space or choosing another
drive; rate limiting recommends waiting; unavailable formats recommend another
format or lower quality. Validation failures recommend one retry with the same
settings and feedback with diagnostics if repeated. No measured bitrate is
turned into a guessed manual setting. Unknown failures advise checking Library
before retrying and reporting a repeat failure with diagnostics.

Technical includes a category, bounded redacted exception detail, nested causes
and process stderr where supplied, plus the recommendation. Process command
arguments are excluded. Empty exceptions explicitly say no further detail was
provided. This is available for single and batch failures, playlist children,
metadata previews and optional-file failures. Partial results retain the valid
media and direct users to the individual issues. Friendly uses terminal summaries
rather than raw technical log text.

Failed playlist child snapshots now carry their own cause. The existing run
journal retains the latest bounded technical block with its terminal summary,
rather than a complete log, and restores it when reopening. Older records with
no detail explicitly report that limitation; no historical reason is invented.
No retry, settings change, or diagnostics submission is automatic.

Verification: 488 focused presentation, worker, state-authority, recovery and
failure-classifier tests passed; the required native gate passed all 91 checks.
The broader repository/harness run passed 1058 tests with 99 skips and one
sandbox-blocked loopback case, which passed on permitted retry. The final focused
run includes the subsequently added preview separation test. Ruff, formatting,
canonical mypy (76 files) and Bandit pass. This follow-up remains source-only.
