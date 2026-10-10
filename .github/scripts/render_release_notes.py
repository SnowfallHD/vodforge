#!/usr/bin/env python3
"""Render clear, architecture-specific VODForge GitHub Release notes."""

from __future__ import annotations

import argparse
import re

REPOSITORY = "SnowfallHD/vodforge"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")


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

    release_details = (
        """
## What’s new in 0.2.6

- Interrupted single downloads and URL batches return as Paused, with Resume in Forge and Run Deck. Resume keeps the run’s saved settings and destination; batches continue with the remaining URLs.
- URL batches show the current video’s title and thumbnail and progress across the whole list. Paused batches retain their last thumbnail, with a VODForge placeholder when none was fetched.
- Watch’s Recently Added rail and See All now share newest-first ordering. See All sits beside the rail heading as a text link.
- Retry opens a choice of the same settings or the selected item’s expanded recovery settings. Recovery uses the shared folder control and keeps the inspector within its column.
- Custom Options keeps selections open, hides the unused CRF or CBR field, and scrolls expanded selectors into view. All runs remains open when hovering over its action controls.
- The packaged download runtime includes browser impersonation support. Additional bounded diagnostics and process-cleanup regressions cover provider failures and interrupted runs.
"""
        if version == "0.2.6"
        else ""
    )

    notes = f"""{draft_notice}## Download VODForge

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

{release_details}
## About this release

- **Qt Quick desktop interface:** Forge, Library, Watch and Activity use the shared stone controls and retain their familiar layout. Run progress now shows failure in red, stopped or skipped work in orange, and completed work in green.
- **More reliable optional analytics:** app-open observations, export outcomes, retries and feature usage now share a validated telemetry contract. Attempt identifiers are installation-scoped and do not contain media URLs, filenames or content.
- **Consent stays in control:** pending updater observations are discarded when analytics permission is withdrawn, including across a later opt-in.
- **Focused release checks:** regression coverage and bounded Mac/Windows preview-telemetry checks verify copy actions, playback outcomes and privacy suppression.
- **One-click updates:** Download update shows progress, verifies the download and safely restarts the app. Repair download remains available for recovery.
- **Library browsing:** visible cards retain their owners through scrolling and column reflow, with bounded viewport loading.
- **Original audio preference:** automatic selection respects provider-marked original audio instead of choosing a higher-bitrate dubbed track. Explicit format choices remain in control.
- **Converter profiles:** Everyday, 4K, Broadcast and Smaller File use the same existing encoding settings and saved profile identities.
- **In-app guidance:** What’s New and Did You Know retain their illustrated feature examples.

Checksums for every download are available in `SHA256SUMS.txt` below.
"""
    if version == "0.2.6":
        return notes.split("## About this release", 1)[0] + (
            "Checksums for every download are available in `SHA256SUMS.txt` below.\n"
        )
    return notes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--draft", action="store_true")
    args = parser.parse_args()
    print(render_release_notes(args.version, draft=args.draft), end="")


if __name__ == "__main__":
    main()
