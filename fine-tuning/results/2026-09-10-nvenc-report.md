# NVIDIA preset tuning — September 10, 2026

## Decision

Keep the task names and CPU default. Honor the user's Windows NVIDIA preference
for Everyday, Streaming, Editing, Sharing and CTV with encoder-specific settings.
Do not treat NVIDIA CQ as a numerical synonym for x264 CRF.

| Task | CPU | NVIDIA |
| --- | --- | --- |
| Everyday | x264 medium, CRF 21 | NVENC CQ 24 |
| Streaming | x264 medium, CRF 20, bounded bitrate | NVENC CQ 23, encoder-adjusted bitrate cap |
| Editing | x264 medium, CRF 18 | NVENC CQ 20 |
| Sharing | x264 medium, CRF 25 | NVENC CQ 27 |
| CTV | Source-informed constrained CBR | Source-informed constrained CBR with additional headroom |
| Custom | Explicit CRF or CBR settings | Exact Custom CBR target; explicit Custom CRF remains CPU |

NVENC uses H.264 p6/HQ, temporal adaptive quantization, 20-frame lookahead, three
B-frames and full-resolution multipass. Automatic CTV's GPU headroom is 1.75×
the CPU target, rounded up to 500 kbps and bounded by the greater of the original
target and the resolution/frame-rate cap. Streaming's GPU cap is 1.5× its CPU cap.
These changes preserve source resolution, audio policy, keyframe intervals and
validation; the 1080p CTV measured floor remains 2,000 kbps. They do not change
Custom's user-entered bitrate or invent a translation for arbitrary manual CRF.

## What the measurements support

Fifty final exports passed production validation, full decoding, equal decoded
frame-count checks and full-frame VMAF measurement: four six-second fixtures plus
an eight-second ocean segment that was not used to choose the settings. The
measured production files match source checkpoint `71763a9`. Hardware: RTX 2080 Ti,
driver 610.88, Windows 10 build 19045, FFmpeg 9.0.1 Gyan essentials.

On the unused ocean segment, NVENC took about one third of the CPU encoding time.
Its quality presets produced files 43–51% larger, with mean VMAF 0.77–1.70 points
below their CPU counterparts. CTV was 70% larger and scored 1.25 points higher.
This is an acceptable opt-in acceleration tradeoff for these samples, not a claim
of identical quality or size. CPU remains the default for compression efficiency.

The synthetic results show why one universal “GPU is X% better” statement would
be wrong: grain was much smaller on NVIDIA at similar or higher VMAF; motion60
Sharing was 2.28× the CPU file size with a higher score; static clips were slower
on NVIDIA because this tiny workload does not amortize overhead. Each GPU task
still expresses its own quality/size tradeoff. No source-specific exception or
hardcoded video ID exists in the application.

CTV required a second adjustment: the old p4/same-bitrate ocean sample measured
81.72 VMAF. The tuned configuration with additional bitrate measured 89.91,
compared with CPU 91.76. The added bits are a disclosed quality cost, not evidence
that NVENC is equally efficient at the original target.

## Original four scenes

Values compare CPU and NVIDIA within one scene and task. MB is decimal. VMAF is
source-relative fidelity, not percent original quality. Timing is one subprocess
wall-time measurement per final case, including software decode and startup.

| Scene | Task | CPU MB | NVIDIA MB | CPU VMAF | NVIDIA VMAF | CPU / NVIDIA seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| ocean | Everyday | 5.806 | 9.754 | 94.547 | 93.656 | 5.277 / 1.794 |
| ocean | Streaming | 6.472 | 10.712 | 95.453 | 94.424 | 5.278 / 1.703 |
| ocean | Editing | 8.086 | 12.506 | 96.962 | 95.266 | 5.272 / 1.721 |
| ocean | Sharing | 4.459 | 6.909 | 90.475 | 89.671 | 4.901 / 1.721 |
| ocean | CTV | 4.872 | 7.727 | 91.763 | 89.909 | 5.114 / 1.734 |
| static | Everyday | 0.058 | 0.063 | 97.29 | 97.369 | 0.885 / 1.199 |
| static | Streaming | 0.075 | 0.101 | 97.347 | 97.396 | 0.972 / 1.197 |
| static | Editing | 0.13 | 0.155 | 97.357 | 97.418 | 0.865 / 1.195 |
| static | Sharing | 0.05 | 0.071 | 97.0 | 97.197 | 0.922 / 1.142 |
| static | CTV | 1.823 | 3.272 | 97.419 | 97.416 | 0.972 / 1.165 |
| motion60 | Everyday | 4.257 | 6.842 | 95.857 | 97.683 | 1.802 / 1.25 |
| motion60 | Streaming | 4.357 | 5.785 | 95.888 | 97.116 | 1.843 / 1.275 |
| motion60 | Editing | 5.791 | 9.755 | 97.071 | 98.376 | 1.698 / 1.266 |
| motion60 | Sharing | 2.361 | 5.388 | 93.266 | 96.88 | 1.657 / 1.306 |
| motion60 | CTV | 4.205 | 3.926 | 95.703 | 95.631 | 1.747 / 1.297 |
| grain | Everyday | 10.454 | 3.434 | 98.737 | 99.236 | 3.865 / 1.078 |
| grain | Streaming | 4.304 | 4.327 | 97.618 | 99.494 | 3.013 / 1.242 |
| grain | Editing | 29.261 | 7.045 | 99.361 | 99.66 | 5.284 / 1.309 |
| grain | Sharing | 2.107 | 2.303 | 96.593 | 98.448 | 2.266 / 1.232 |
| grain | CTV | 4.054 | 3.928 | 97.569 | 99.447 | 3.178 / 1.211 |

## Unused ocean segment

The eight-second reference covers seconds 20–28 of the same original source.
Video and audio timestamps were reset before encoding. It is a temporal holdout,
not a second independent real-world video.

| Task | CPU MB | NVIDIA MB | CPU VMAF | NVIDIA VMAF | CPU / NVIDIA seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Everyday | 7.872 | 11.876 | 95.345 | 93.649 | 6.935 / 2.227 |
| Streaming | 8.895 | 13.315 | 96.075 | 94.646 | 7.286 / 2.176 |
| Editing | 11.342 | 16.16 | 97.496 | 95.95 | 7.069 / 2.157 |
| Sharing | 5.874 | 8.402 | 90.799 | 90.032 | 6.545 / 2.205 |
| CTV | 5.984 | 10.148 | 90.386 | 91.636 | 6.565 / 2.218 |

## Search history and checks

The archived search contains 115 completed measurements: 12 from an interrupted
initial range, 25 from a refined but interrupted range, 72 using every fourth
frame for exploratory VMAF, and six full-frame temporal-AQ comparisons. Sampled
scores are never treated as final scores. A 40-output candidate verification
preceded the final CTV adjustment and is retained locally, not mixed into the
final matrix.

An initial ten-output holdout attempt had a nonzero video start time. CFR padding
then made index-based VMAF compare different frames. Those scores were rejected;
the fixture was normalized and the harness now rejects nonzero reference starts,
unequal decoded frame counts, and sampled final verification. A regression uses
a real offset-timestamp media fixture to prove that scoring is refused.

The real Windows worker regression passed all 15 cases, including CPU and NVIDIA
encoding through validation, atomic commit and reuse, plus the existing quality
tradeoff check. Custom CRF correctly remained CPU. Local repository/harness tests:
1,192 passed, 127 explicitly skipped; native checks: 53 passed; canonical mypy:
78 files passed; Ruff/format and Bandit passed. Ordinary CI's skipped NVIDIA
cases are not hardware evidence. Source and hardware-worker proof do not replace
a packaged release journey or physical TV/OBS testing.

A matched two-second frame from the holdout CPU and NVIDIA Everyday exports
was inspected: scene timing, proportions and colors matched; fine foam texture
showed small differences. This is a bounded visual check, not a viewer study.

## Limits and reproducibility

Only one GPU/driver was tested. Other NVIDIA generations, long files, complex
edits, HDR workflows, actual OBS playback and network ingest require separate
measurements. Scores cannot recover detail missing from the source. Synthetic
fixtures use documented compressed-source bitrate hints for planning; the
lossless decoded files are the VMAF references. No original video is distributed.

See the [harness commands and methodology](../README.md),
[raw final receipts](2026-09-10-rtx2080ti-final.json),
[raw holdout receipts](2026-09-10-rtx2080ti-holdout.json), and
[calibration archive](2026-09-10-rtx2080ti-calibration.json).
