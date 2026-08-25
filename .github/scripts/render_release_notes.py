#!/usr/bin/env python3
"""Render clear, architecture-specific VODForge GitHub Release notes."""

from __future__ import annotations

import argparse
import re


REPOSITORY = "SnowfallHD/vodforge"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def asset_url(version: str, filename: str) -> str:
    return f"https://github.com/{REPOSITORY}/releases/download/v{version}/{filename}"


def render_release_notes(version: str, *, draft: bool = False) -> str:
    if not VERSION_RE.fullmatch(version):
        raise ValueError("Version must use semantic versioning, for example 1.2.3.")

    mac_arm = f"VODForge-macOS-arm64-v{version}.zip"
    mac_intel = f"VODForge-macOS-x64-v{version}.zip"
    windows_installer = f"VODForge-Windows-Setup-v{version}.exe"
    windows_portable = f"VODForge-Windows-Portable-v{version}.zip"
    draft_notice = ""
    if draft:
        draft_notice = (
            "> **Release-team draft:** Do not publish until both Mac downloads have been "
            "Developer ID signed, notarized, stapled, independently verified, and the "
            "checksums regenerated.\n\n"
        )

    return f"""{draft_notice}## Download VODForge

### Newer Macs — Apple silicon

**Usually Macs from late 2020 and newer. Recommended for most Mac users.**

[Download VODForge for Apple silicon]({asset_url(version, mac_arm)})

Choose this when **About This Mac** shows a **Chip** such as Apple M1, M2, M3, M4, or newer.

### Older Macs — Intel-based

**Generally Macs from 2020 and earlier.**

[Download VODForge for an Intel-based Mac]({asset_url(version, mac_intel)})

Choose this only when **About This Mac** shows an **Intel Processor**. Using this download on an Apple silicon Mac can cause macOS to display an Intel-app compatibility warning.

### Windows

**Recommended:** [Download the Windows installer]({asset_url(version, windows_installer)})

[Download the portable Windows version]({asset_url(version, windows_portable)}) only if you specifically do not want an installed app.

## About this release

- Download either **MP4 video** or **MP3 audio** from the same Forge field, with separate format-aware controls.
- MP3 exports default to the highest-quality available source and offer up to 320 kbps, source sample-rate preservation, channel and ID3 controls, plus no art, YouTube art, or custom embedded cover art.
- YouTube format discovery now uses the current bundled yt-dlp, Deno, and EJS solver stack so 1080p and 4K sources are found more reliably when the video provides them.
- MP4 and MP3 runs now reuse provider analysis, reduce redundant network and disk work, coalesce UI progress updates, and keep preview work from delaying the active download.
- Downloads finish through isolated same-volume staging, media validation, and an atomic final commit so cancellation or a failed encode cannot replace a valid destination with a partial file.
- **Library** keeps the original YouTube source and final VODForge output details together, including resolution, codecs, frame rate, video and audio bitrates, sample rate, channels, size, and saved location.
- Library artwork now stays compact enough to preserve useful space for tags and descriptions at full-size layouts.
- Playlist protection is enabled by default, cookie access is organized into clear public, cookies.txt, or browser choices, and explanatory tooltips clarify batch and access controls.
- The optional **VODForge Cloud** early-access link now opens a privacy-narrow waitlist that records only one anonymous seen → clicked → joined funnel per installation.
- VODForge continues to check stable GitHub Releases automatically and verifies approved updates before installation.
- Windows downloads are signed by Kryden Ventures, LLC.
- Mac downloads are Developer ID signed, notarized, and provided separately for Apple silicon and Intel-based Macs.

Checksums for every download are available in `SHA256SUMS.txt` below.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--draft", action="store_true")
    args = parser.parse_args()
    print(render_release_notes(args.version, draft=args.draft), end="")


if __name__ == "__main__":
    main()
