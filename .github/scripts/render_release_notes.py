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

- **New in 0.2.0:** a native welcome tour and a **Did you know?** tip for YouTube access and age restrictions. Try Browser in Settings and select the browser where you are signed in to YouTube. Your account must have access; age verification may still be required.
- **Help & feedback and public reviews** offer explicit, bounded submissions, optional failure diagnostics, and abuse-protected delivery independent of analytics consent.
- **Recovery and retries:** failed downloads retry with current settings; previously successful downloads retain their saved output profile. Older Library destinations recover without duplicating nested folders or changing your saved default.
- **Forge refinements:** Load URL list is available below the composer, local MP3-to-video conversion has a full Image preview and folder chooser, and All N runs combines hover navigation with click-to-Library.
- **UI consistency:** dropdowns stay attached while scrolling, detail values retain wrapping indentation, error messages are shorter and actionable, and warning/error rows share aligned markers.
- **Original audio** preserves the best available supported Opus or AAC source without another lossy encode. Outputs use .opus or .m4a, with Library filtering and built-in playback.
- Choose **MP4**, **MP3**, or **Original audio** from one polished dropdown. Shared dropdown styling is consistent throughout the app on macOS and Windows.
- Forge now offers clear, friendly progress stages and a smile/frown slider for the detailed technical log. Activity keeps the full technical view with aligned event markers and readable wrapped lines.
- Native showcase exhibits stay sharp at display resolution. This release uses **Did you know?** instead of **What's new**; routine version changes do not reopen an acknowledged showcase.
- Run Deck reflects completed Library items during a playlist instead of waiting for the whole playlist. Skipping a non-final item immediately follows the next item, and thumbnails remain attached to the correct video.
- Quality caps honor YouTube's named quality tiers, including wide-aspect 1080p streams whose height is not exactly 1080 pixels. Routine bitrate and temporary-file messages no longer appear as misleading failure warnings.
- The optional analytics choice now governs installation, update, attribution, and usage telemetry. Existing installations evaluate the region policy once if needed; opt-in and unknown regions require consent. Saved choices persist, and existing users do not restart the first-install browser-link flow.
- Usage sharing uses an in-app, centered prompt with a fully dimmed backdrop. The first-install thank-you page remains independent of analytics permission.
- Refined Forge, Library, Settings, and Player surfaces improve spacing, typography, hover states, and control consistency.
- Downloads continue to use isolated staging, output validation, and atomic final commits. Stable updates are verified before installation.
- Windows downloads are signed by Kryden Ventures, LLC. Mac downloads are Developer ID signed, notarized, and available separately for Apple silicon and Intel Macs.

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
