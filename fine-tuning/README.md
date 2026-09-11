# VODForge fine-tuning harness

[Read the NVIDIA tuning report and measured results](results/2026-09-10-nvenc-report.md).

The engineering-quality harness asks whether the application works correctly.
This harness asks which encoder settings best serve each export task, and records
the evidence behind those choices. It uses the production source selector, export
planner, FFmpeg command builder and output validator. Calibration may override
encoder options explicitly; final verification must use production settings.

## Reproduce a run

Use the repository Python environment (`requirements-dev.txt` and
`engineering-quality/requirements.txt`), FFmpeg with libx264, h264_nvenc and libvmaf,
and the matching ffprobe. NVIDIA runs require a supported GPU and driver. These
commands never download media, install software, or change app settings.

First prepare the original four decoded six-second reference samples. Supply your
own lawful ocean source; it is not distributed with this repository:

```sh
python fine-tuning/benchmark_export_presets.py \
  --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe \
  --ocean /path/to/ocean.mp4 --output build/tuning-fixtures
```

This also reproduces the original CPU calibration. Synthetic static, motion60 and
grain samples are generated deterministically; the ocean sample is source-dependent.
Use identical fixture files across machines and compare the hashes in receipts.

```sh
python fine-tuning/run.py \
  --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe \
  --fixtures build/tuning-fixtures --output build/nvenc-search \
  --stage sweep --offsets=1,4,7 --speeds p6 --bframes 3 \
  --source-commit "$(git rev-parse HEAD)"

python fine-tuning/run.py \
  --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe \
  --fixtures build/tuning-fixtures --output build/nvenc-verification \
  --stage verify --source-commit "$(git rev-parse HEAD)"
```

Windows accepts the same arguments with Windows paths. Quote paths containing
spaces. `--names` and `--presets` select comma-separated bounded subsets.
`--aq` selects disabled (`0`), spatial (`1`), or temporal adaptation.
`--vmaf-subsample 4` accelerates exploratory scoring only; do not compare it with
full-frame scores. Final verification uses the default full-frame VMAF.
Use a new output directory for every run; existing receipts are never overwritten.
The legacy `scripts/benchmark_export_presets.py` entry point remains supported.

## What the receipts mean

Each output records its command, file hash, size, measured video bitrate, encoding
wall time, source-relative VMAF mean/minimum, keyframe interval, production
validation, and full decode result. The run records fixture hashes, FFmpeg/Python
versions, GPU/driver, source identity and relevant source-file hashes. `complete`
means the selected matrix finished; an interrupted run is not a passing receipt.
Generated media stays in the chosen output directory, outside tracked results.

Quality scores compare each output with its own decoded source. They do not mean
“percent original quality,” recover lost source detail, or certify an OBS, CTV,
Roku, Fire TV, or Apple TV playback/ingest workflow. Six-second fixtures are useful
for tuning, but are not a representative video collection or a long-file soak.
Encoding wall time includes startup and software decoding; it is not pure GPU
throughput and depends on the host. Compare timing within the same run.

CPU CRF and NVIDIA CQ are different scales. Keep the task, resolution, audio and
keyframe intent fixed; search NVIDIA settings independently. Assess quality loss,
size growth and speed together rather than optimizing VMAF alone. Inspect matched
frames and verify the chosen policy through the actual worker before shipping.

References: [NVIDIA FFmpeg guide](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/ffmpeg-with-nvidia-gpu/index.html),
[FFmpeg NVENC implementation](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/nvenc_h264.c),
[Netflix VMAF](https://github.com/Netflix/vmaf).

CPU-only hosts can use `--encoders cpu`; they do not need an NVIDIA driver.
A final score requires equal decoded frame counts and a zero-based reference
video timeline. When preparing a segment with `-ss`, normalize it with
`-vf setpts=PTS-STARTPTS -af asetpts=PTS-STARTPTS` before using it as a fixture.
The harness refuses a nonzero start or a frame-count mismatch instead of
publishing a misleading index-aligned score.

Run the worker regression on the same NVIDIA machine after tuning:

```powershell
$env:VODFORGE_NVENC_TESTS = '1'
python -m pytest engineering-quality/tests/test_export_preset_pipeline.py -q
```

Put the intended FFmpeg/ffprobe directory first on PATH. This runs real encoding,
validation, atomic output commit and existing-file reuse with an offline provider
fixture. It includes Custom CBR and explicit CPU Custom CRF. Normal CI has no
NVIDIA hardware; its skipped cases do not prove the GPU path.
