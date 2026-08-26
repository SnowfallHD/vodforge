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
- Forge now keeps queued, active, completed, skipped, stopped, and failed runs isolated under stable run identities, so selecting Library items or older runs cannot overwrite the current run's title, thumbnail, progress, activity, or output details.
- Failed downloads offer **Retry Download**, while skipped or stopped downloads offer **Restart Download**. Each action creates a fresh run and safely joins the sequential queue.
- Metadata previews now focus immediately, report **Preview complete** truthfully, and provide direct **Start download** actions in Forge and Library. Sending the same URL promotes the preview into the new active run without a duplicate preview card.
- The pixel-scrolling Library table now has discoverable draggable column dividers with minimum widths and session-persistent sizing, while retaining responsive layouts and horizontal overflow.
- Removing a Library entry also removes its matching Forge recent card and reconciles the selected hero, without deleting downloaded media, sidecars, active work, or queued work.
- Forge activity stays owned by the selected run, and the separate Activity tab retains a bounded private application log across restarts. Live output follows only while the reader is already at the bottom.
- Exact submitted URL context now preserves YouTube playlist organization even for one-item scope, while shortened links remain safely under the no-playlist destination instead of guessing membership.
- Downloads use isolated same-volume staging, contract validation, and an atomic final commit so cancellation or a failed encode cannot replace a valid destination with a partial file.
- YouTube format discovery uses the bundled yt-dlp, Deno, and EJS solver stack so 1080p and 4K sources are found more reliably when the video provides them.
- MP4 and MP3 runs reuse provider analysis and retain format-aware quality, metadata, artwork, and encoding controls.
- **Library** keeps the original YouTube source and final VODForge output details together, including resolution, codecs, frame rate, bitrates, sample rate, channels, size, and saved location.
- The optional **VODForge Cloud** early-access funnel remains privacy-narrow: one random anonymous installation identifier records the seen → clicked → joined journey alongside only OS family and app version.
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
