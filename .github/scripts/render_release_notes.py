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

- **Task-based MP4 output settings:** Everyday, Streaming, Editing, Sharing, CTV, and Custom. Automatic presets adapt to the source; existing Auto CBR settings retain the CTV delivery intent.
- **CPU and NVIDIA tuning:** CPU remains the default. Optional Windows NVENC uses independently measured quality settings instead of treating CQ and CRF as equivalent. Explore the open [fine-tuning harness](https://github.com/SnowfallHD/vodforge/tree/main/fine-tuning) and [export-settings guide](https://getvodforge.com/mp4-export-settings/).
- **One What’s new slide** introduces the output settings, with **Try it** opening Settings.
- **Actionable failures:** Friendly explains the next step; Technical retains the actual recorded cause. Valid nearly silent AAC no longer fails an arbitrary minimum-bitrate check.
- **Reliable updates and repair:** Windows targets the running app’s folder, hides the PowerShell helper, verifies installation, and relaunches. macOS also closes safely and relaunches. Recovery offers clear steps and verified repair with saved-data backups.
- **Queue and UI fixes:** closing cannot start another queued worker. The composer format selector works correctly, Settings text and Library Description fit their surfaces, and the player Play overlay blends into its poster on Mac and Windows.
- **Original audio** continues to preserve supported Opus or AAC without another lossy encode. Quality caps honor YouTube's named quality tiers; outputs use validation and atomic final commits.
- Your optional analytics choice governs installation, update, attribution, and usage telemetry; opt-in and unknown regions require consent. Saved choices persist.
- Windows downloads are signed by Kryden Ventures, LLC. Mac downloads are Developer ID signed and notarized, with separate Apple silicon and Intel builds.

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
