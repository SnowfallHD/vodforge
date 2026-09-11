# Task-based MP4 export presets

The output selector is now **Optimize for**: Everyday, Streaming, Editing, Sharing, CTV, Custom. Everyday is the default for a fresh profile. Existing Auto CBR preferences continue as CTV; existing manual preferences continue as Custom. This is implemented on the current feature lane, not publicly released or installed over the user's private app.

## Final policy

All automatic MP4 presets select the best suitable available SDR source within the explicit quality ceiling, preserve its dimensions/aspect ratio and encode H.264 High, 8-bit yuv420p, MP4 faststart and AAC stereo at 48 kHz. No upscaling, invented detail or HDR-to-SDR conversion is claimed. An HDR-only source now fails with an actionable SDR explanation instead of risking incorrect colors. These presets transcode; automatic stream copying and mezzanine codecs are not part of this implementation.

| Preset | Video | Keyframes / timing | AAC target |
| --- | --- | --- | --- |
| Everyday | x264 medium, CRF 21 | About 5 seconds maximum, natural source timing | Source-informed 128–192 kbps |
| Streaming | x264 medium, CRF 20 with resolution/frame-rate VBV cap | About 2 seconds maximum, explicit constant frame rate at source rate | Source-informed 160–192 kbps |
| Editing | x264 medium, CRF 18 | About 1 second maximum, explicit constant frame rate at source rate | Source-informed 192–256 kbps |
| Sharing | x264 medium, CRF 25 | About 5 seconds maximum, natural source timing | Source-informed 96–128 kbps |
| CTV | Source-derived constrained CBR; 1080p tier targets 2.5–10 Mbps | About 2 seconds maximum, explicit constant frame rate at source rate | Existing source-informed AAC policy |
| Custom | User-selected CBR or x264 quality CRF 1–51, encoding speed | Existing encoder defaults | User-selected AAC or MP3, bitrate, sample rate, channels |

Automatic quality presets honor the saved Windows NVIDIA preference. CPU uses
x264 medium with the CRF values above. NVENC uses independently tuned CQ:
Everyday 24, Streaming 23, Editing 20 and Sharing 27, with p6/HQ, temporal AQ,
20-frame lookahead, three B-frames and full-resolution multipass. These are
encoder-specific targets, not equivalent numerical scales or a promise of
identical quality/file size on every source or GPU. CPU remains the default.

Streaming's NVENC bitrate cap is 1.5 times the CPU cap. Automatic CTV allows up
to 1.75 times its CPU bitrate target, rounded up to 500 kbps, bounded by the greater of the existing target
and the resolution/frame-rate cap, to compensate for encoder efficiency. The
measured 1080p floor remains 2,000 kbps; resolution, frame timing, keyframes and
audio contracts are unchanged. Custom CBR preserves the user's exact bitrate;
Custom quality remains explicitly x264 CRF, rather than inventing an uncalibrated
CQ translation for arbitrary manual values. The NVIDIA checkbox and descriptions
state this distinction.

The reproducible harness now lives in [fine-tuning](../fine-tuning/README.md).
Its NVIDIA evidence uses an RTX 2080 Ti; other GPU generations and drivers still
need their own receipts. Original CPU measurements below remain CPU results.
In Custom, the unused bitrate/CRF control is disabled, and unused bitrate does
not affect quality-mode duplicate identity. CRF 0 is excluded because lossless
x264 is incompatible with the fixed High profile contract.

Streaming reuses the existing resolution/frame-rate cap table (for example 5 Mbps at 720p, 10 Mbps at 1080p30, 14 Mbps at 1080p60) with a two-second VBV buffer. These are rate-control constraints, not exact file-size promises; short clips can have an average above the nominal cap due to the initial buffer. Existing 18% measured-rate tolerance applies to the maximum for this profile. Quality-mode video otherwise has no invented bitrate floor; positive, finite measured rate and the independent stream/codec/profile/pixel format/geometry/duration/audio checks remain mandatory.

CTV retains the old Auto CBR source/codec estimation policy and lower/upper tier limits. At the 1080p tier it adds 25% target headroom (rounded to existing clean bitrate steps), bounded to 2.5–10 Mbps. The 2.5 Mbps target floor gives space for short-clip encoder startup while validation enforces the user's actual **2,000 kbps measured video minimum**. Widescreen 1080p-tier sources such as 1920x1012 receive that same contract. This floor is a delivery requirement, not proof that a poor source has good detail. No AAC minimum has been reinstated: quiet audio remains valid, and the regression corpus checks decoded signal energy independently.

## Calibration and results

First compared the six candidate policies, then added Streaming's VBV constraint and CTV's extra headroom and repeated all 24 exports through the production planner, command builder and validator. Four six-second fixtures cover the actual ocean clip, a static 1080p chart, motion at 720p60, and deterministic grain at 720p24. Synthetic fixtures use explicit compressed-source bitrate hints; they are not measurements of a lossless source's compression quality. Ocean's source hint is 4 Mbps, approximating the original selection. VMAF is measured against the decoded source with frame indices aligned to remove millisecond container timebase differences. These are relative fidelity measurements, not subjective scores of source quality.

All 24 final exports passed production validation and full decoding. Measured keyframe gaps matched the intended intervals within one frame. On the static 1080p fixture, CTV measured 2,418 kbps, above the enforced 2,000 kbps floor. The initial 2,000 kbps target measured below that minimum; this supports raising the target floor without relaxing validation. Static Everyday was about 58 KB versus CTV's 1.82 MB. On grain, the capped Streaming output was 4.29 MB versus the uncapped candidate's 17.49 MB, with final VMAF 97.72. Editing intentionally retained more grain/detail at 29.24 MB.

### Ocean sample: final production exports

| Preset | File size (decimal MB) | VMAF | Measured video kbps |
| --- | ---: | ---: | ---: |
| Everyday | 5.81 | 94.55 | 7728 |
| Streaming | 6.48 | 95.43 | 8616 |
| Editing | 8.09 | 96.96 | 10769 |
| Sharing | 4.46 | 90.50 | 5932 |
| CTV | 4.87 | 91.72 | 6469 |
| Custom | 7.65 | 96.95 | 10177 |

The baseline 5 Mbps CTV candidate scored 87.65; the final 6 Mbps target scored 91.72. Everyday and Sharing retain their initial CRF choices: on this sample Sharing saves about 23% versus Everyday with the expected detail tradeoff. Editing preserves more detail for another export. Visual inspection of matched ocean frames confirms the scene, proportions and colors remain intact; this is not a broad subjective viewing study.

### Reproduce

```sh
PYTHONPATH=. .venv/bin/python fine-tuning/benchmark_export_presets.py --production \
  --ffmpeg dist/VODForge.app/Contents/Frameworks/ffmpeg \
  --ffprobe dist/VODForge.app/Contents/Frameworks/ffprobe \
  --ocean build/aac-failure-repro/full-source.mp4 \
  --output build/task-presets/recheck
```

Omit `--production` to run the frozen pre-tuning candidates. `--fixtures` can reuse the generated lossless fixture directory. Receipts include actual commands, size, encode time, VMAF, measured bitrate and keyframe gaps. The initial misaligned VMAF attempt was superseded by the corrected frame-aligned calibration; no decisions use those scores.

## Compatibility evidence and limits

- [Roku streaming specifications](https://developer.roku.com/dev/docs/media) describe AVC High/Main, up to 1080p and 10 Mbps, supported natural frame rates and IDR-aligned segments. Roku's final playback profiles are different from ingest-master requirements.
- [Apple HLS authoring specification](https://developer.apple.com/documentation/http-live-streaming/hls-authoring-specification-for-apple-devices/) recommends IDRs every two seconds and natural VOD frame rates.
- [Fire TV specifications](https://developer.amazon.com/docs/device-specs/device-specifications-fire-tv-streaming-media-player.html) document H.264 High and AAC-LC decoding, with model-specific limits.
- [OBS media sources](https://obsproject.com/kb/media-sources) expose hardware decoding subject to the actual device and configuration. No OBS installation was available on this Mac for an application-level playback check.

CTV is an **upload master for the user's network to transcode**. It is not an HLS packager, does not generate rendition ladders, and is not certified against the network's unavailable ingest specification or physical Roku/Fire TV/Apple TV hardware. Above-1080p sources remain upload masters; universal direct H.264 4K playback is not promised. Editing is an editing-friendly MP4, not ProRes/DNxHR or an NLE benchmark.

## Persistence, ownership and regression coverage

Old durable `Auto CBR` / `Manual Override` enum values are deliberately retained beneath the CTV / Custom labels to preserve retry records and identities. Removed Strict Compliance settings migrate to Custom with the former 10 Mbps / 320 kbps AAC / 48 kHz stereo / medium CBR settings. Existing queued legacy Strict jobs remain interpretable. No history rewrite, network mutation or automatic telemetry change occurs.

Existing owners remain authoritative: export_planning selects policy and sources; ExportPlan carries the contract; the existing FFmpeg builder executes it; output_validation verifies it; settings/run_state/run_identity retain preferences, retries and equivalence. app.py adds composition and command parameters in its existing encoding boundary, not a new subsystem. FocusSettingsDialog owns the new controls and removes its variable trace on destruction. Shared failure presentation adds the HDR-specific recommendation; Technical still receives the original bounded cause. No new durable source of truth or architectural family is introduced.

Required native tests cover all six selections, Custom control enablement and dialog close/reopen. Real AAC tests span all six presets with float-PCM silence, quiet tone and ordinary tone, checking both export contracts and decoded signal energy. The new offline-provider worker test exercises real transcode, validation, atomic commit and successful reuse for all six plus Custom quality. Planner tests cover every preset across 360p through 4K, legacy preferences, CRF versus CBR validation, source bitrate independence, HDR rejection, and Custom restart/duplicate identity. Tests are included in the existing repository and harness discovery paths.

Evidence: `build/task-presets/`, `build/task-presets-*.log`. Source/native/media evidence is distinct from a new installed or publicly released package.

## Final verification — 2026-09-10

- Full repository and harness suite: **1,131 passed, 100 skipped** in the permitted environment. The first sandboxed pass had one local-loopback PermissionError; the full permitted run resolved it. Skips are not claimed as execution proof.
- Required native gate: **92 passed**, no skips, `build/task-presets-native-final.xml`.
- Eight real worker/semantic tests pass, including all six tasks, Custom quality, valid-file reuse, and independently measured Sharing < Everyday < Editing size/SSIM ordering.
- Eighteen real encoder AAC cases pass using float PCM references and decoded RMS checks.
- Ruff/check-format, compileall, canonical mypy (76 files) and Bandit (zero findings) pass.
- Actual Settings rendering inspected in `build/task-presets/custom-settings.png`; all six native menu choices exercised by the required gate.
- No installed-app replacement, production release, push, device certification or network ingest test performed for this checkpoint.
