# VODForge

[![Tests](https://github.com/SnowfallHD/vodforge/actions/workflows/tests.yml/badge.svg)](https://github.com/SnowfallHD/vodforge/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows | macOS](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-59636e)](#quick-start)

A Windows and macOS desktop app that turns YouTube videos and playlists into organized, VOD-ready MP4 files using `yt-dlp` and FFmpeg.

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
- Keeps a private, local Metadata Browser history of completed downloads and their saved folders across app restarts.
- Checks versioned, stable GitHub Releases for updates; it never installs code directly from the repository's `main` branch.

## Install a packaged release

GitHub Releases are the intended public download channel. On Windows, use the per-user `VODForge-Windows-Setup` installer. It installs under `%LOCALAPPDATA%\Programs\VODForge`, keeps the packaged `_internal` runtime beside the app automatically, adds normal shortcuts, and provides an uninstaller. The portable ZIP remains available for users who specifically want it.

The macOS release is a normal `VODForge.app`; its bundled runtime is inside the application package. Public macOS releases are Developer ID signed, notarized, stapled, and Gatekeeper-checked before publication. Unsigned workflow artifacts are explicitly named `unsigned-review` and are never public-ready downloads.

## Quick start

You need Python 3.11 or newer with Tk support.

### macOS

Homebrew is used to install a Tk-enabled Python, FFmpeg, and Deno. The application remains a lightweight Python/Tk desktop app; it does not require Electron.

```bash
git clone https://github.com/SnowfallHD/vodforge.git
cd vodforge
./install_macos_dependencies.sh
.venv/bin/python main.py
```

### Windows

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

Diagnostics are written to `%LOCALAPPDATA%\VODForge\logs\` on Windows and `~/Library/Logs/VODForge/` on macOS.

Completed-download history is written to `%LOCALAPPDATA%\VODForge\download-history.json` on Windows and `~/Library/Application Support/VODForge/download-history.json` on macOS. It contains an allow-listed copy of display metadata and the saved output folder. It never stores cookie files, cookie contents, tokens, passwords, or browser-session data. A missing external drive or moved folder is reported without deleting the history entry.

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

To build the primary per-user installer and the optional portable ZIP, install Inno Setup 6 and run:

```powershell
.\build_and_package_windows.ps1 -Version "0.1.0"
```

Use `-PortableOnly` only when you intentionally do not want an installer.

## Build the macOS app

Install dependencies, build the `.app`, and run its offline runtime smoke test:

```bash
./install_macos_dependencies.sh
./build_macos.sh
```

The local unsigned application is created at:

```text
dist/VODForge.app
```

To package an unsigned ZIP for internal testing:

```bash
./build_and_package_macos.sh 0.1.0
```

The build bundles FFmpeg, ffprobe, and Deno so a Finder-launched app does not depend on shell `PATH` configuration. Public distribution still requires an Apple Developer ID signature and notarization; the build scripts do not claim or perform those steps.

## Release workflow

The manually dispatched **Build Release Draft** GitHub Actions workflow builds:

- a Windows per-user installer;
- an optional Windows portable ZIP;
- separate Apple Silicon and Intel macOS review archives; and
- `SHA256SUMS.txt` for every artifact.

It creates a GitHub **draft** release only. Windows application and installer signing uses Azure Artifact Signing through a repository-specific OIDC identity; no long-lived Azure password is stored in GitHub. The macOS jobs produce explicit unsigned review archives for both architectures. On the signing Mac, `./finalize_macos_release.sh <version>` downloads those review builds, Developer ID signs them, submits each to Apple notarization, staples and Gatekeeper-checks them, runs the packaged-runtime smoke tests, uploads the final archives, removes the unsigned review assets, and regenerates `SHA256SUMS.txt`.

After the draft assets and checksums are reviewed, publishing the draft makes it the update source. The app's update check reads only the latest public, stable GitHub Release. On Windows it downloads the matching signed installer, verifies its exact size and SHA-256 checksum from the same release, and starts the updater. macOS opens the verified release page until an in-app signed replacement path is implemented.

## Development

Windows:

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q yt_downloader main.py
```

macOS:

```bash
./install_macos_dependencies.sh
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q yt_downloader main.py macos_smoke_test.py
.venv/bin/python macos_smoke_test.py
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
