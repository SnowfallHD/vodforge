# VODForge

[![Tests](https://github.com/SnowfallHD/vodforge/actions/workflows/tests.yml/badge.svg)](https://github.com/SnowfallHD/vodforge/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D4)](#quick-start)

A Windows desktop app that turns YouTube videos and playlists into organized, VOD-ready MP4 files using `yt-dlp` and FFmpeg.

VODForge analyzes the available source streams, chooses a practical video/audio pair, and exports predictable H.264/AAC files without pretending a low-quality source has more detail than it does.

## What it does

- Downloads individual videos, playlists, or a batch of URLs.
- Supports quality caps from 360p through 4K when the source provides them.
- Defaults to source-aware **Auto CBR** with resolution-specific bitrate floors and caps.
- Includes **Strict Compliance** mode for fixed H.264 10 Mbps video and AAC 320 kbps audio.
- Offers a manual override when you need exact export settings.
- Embeds useful metadata and thumbnails in the MP4 when supported.
- Writes a compact, readable `metadata.json` beside each video.
- Keeps playlist and non-playlist downloads organized in collision-safe folders.
- Includes browser-cookie and `cookies.txt` options for videos you are authorized to access.
- Shows progress, speed, ETA, diagnostics, and per-item batch failures.

## Quick start

### Option 1: Download the Windows app

1. Open the [latest release](https://github.com/SnowfallHD/vodforge/releases/latest).
2. Download `VODForge-Windows.zip`.
3. Extract the entire ZIP.
4. Open the extracted `VODForge` folder and run `VODForge.exe`.

> Keep `VODForge.exe` beside the `_internal` folder. Running only the EXE or launching it from inside the ZIP viewer will not work.

### Option 2: Run from source

You need Windows and Python 3.11 or newer.

```powershell
git clone https://github.com/SnowfallHD/vodforge.git
cd vodforge
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\install_ffmpeg_windows.ps1
.\install_deno_windows.ps1
python main.py
```

FFmpeg is required. Deno is strongly recommended because current YouTube extraction increasingly relies on a JavaScript runtime.

## Using VODForge

1. Paste one YouTube URL, choose a playlist URL, or load a text file containing one URL per line.
2. Pick an output folder and quality cap.
3. Leave **Auto CBR** selected for normal use, or choose another export mode when a platform has a specific requirement.
4. Start the download.

Typical output:

```text
<output>/
└── <channel>/
    ├── playlists/
    │   └── <playlist>/
    │       └── <video title> [video-id]/
    │           ├── <video title>.mp4
    │           ├── metadata.json
    │           └── thumbnail.jpeg
    └── videos - no playlist/
        └── <video title> [video-id]/
            ├── <video title>.mp4
            ├── metadata.json
            └── thumbnail.jpeg
```

Diagnostics are written to `%LOCALAPPDATA%\VODForge\logs\`.

## Build the Windows app

Install the portable dependencies, then build and smoke-test:

```powershell
.\install_ffmpeg_windows.ps1
.\install_deno_windows.ps1
.\build_windows.ps1
.\smoke_launch.ps1
```

The runnable folder is created at:

```text
dist\VODForge\
```

To build and package a ZIP:

```powershell
.\build_and_package_windows.ps1 -Version "0.1.0"
```

## Development

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q yt_downloader main.py
```

The test suite focuses on export planning, FFmpeg command construction, metadata, path safety, batch parsing, cookie options, diagnostics, and source-format fallbacks.

## Important notes

- Available resolutions and formats depend on the source video and YouTube.
- A larger output bitrate cannot restore detail that was not present in the source.
- Browser-cookie import reads cookies through `yt-dlp`; VODForge does not upload or store cookie contents.
- Download only content you own or have permission to use, and follow the applicable platform terms and laws.

## Contributing

Bug reports and focused pull requests are welcome. Please include reproduction steps for download failures and run `python -m pytest -q` before opening a PR. Never attach cookie files or diagnostics containing private URLs.

## License

MIT — see [LICENSE](LICENSE).
