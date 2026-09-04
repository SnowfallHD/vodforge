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

- Library now includes search, reusable category filters, and private notes and tags for saved media.
- The internal offline player now uses bundled libVLC for synchronized MP4/MP3 playback, responsive seeking and volume, and VODForge-owned chapters and preview controls. It opens on artwork with a Play overlay; the engine warms in the background and closing the player no longer waits for runtime teardown.
- **MP3 + image → MP4** turns local audio and a still image into a video, with independent 1080p Standard, 2160p 4K, 720p Compact, and 1080p Strict 2 Mbps CBR profiles. Output goes directly into the selected folder and appears in Library's MP4 view.
- Missing or moved media can be re-downloaded with saved settings into the original base output folder, reusing existing folders without duplicating the channel/playlist hierarchy.
- Theme and accent changes apply immediately. Dropdowns, checkboxes, table selection, and field borders are refined in place; Settings supports trackpad scrolling, and dialog actions and progress remain visible as content changes.
- Anonymous website-to-install attribution respects browser analytics choices. The **Share anonymous usage analytics** setting controls new coarse app/feature events; first-party installation and Cloud funnel counts remain separate. Media URLs, filenames, searches, notes, tags, and playback positions are excluded from usage events.
- Output destinations and export preferences now persist across app restarts, while queued runs retain their order and resume through the normal sequential launcher.
- Closing VODForge now terminates and reaps its owned download/transcode processes. A hard exit is recovered safely on the next launch as the existing **Failed** state, with abandoned `.vfstage` transactions reconciled by the staging owner instead of leaving invisible background work.
- Library is now a deterministic, run-ID-first projection of durable run and history state. Queued, Preparing, Downloading, Transcoding, Completed, Failed, Stopped, and retry transitions update one canonical row, eliminating orphan placeholders, temporary disappearance, and stale or duplicated terminal rows.
- Exact duplicate submissions now focus or supersede the correct attempt, reuse an already-valid output without retranscoding, repair missing metadata or thumbnail sidecars, and keep genuinely distinct settings or destinations as distinct Library artifacts.
- Fast cancellation and restart are durable even before provider metadata arrives. Stopped attempts remain visible after relaunch, while retry and output-detail actions stay attached to the exact run they control.
- Run Deck, Library table, and progress surfaces now have local render owners that no-op on identical immutable snapshots, patch value-only changes, and rebuild only for real structural changes. Active download progress beside queued MP3 work no longer causes card flicker.
- Window resizing and responsive Library transitions are substantially smoother on macOS and Windows, with breakpoint changes applied during the drag instead of after release.
- The pixel-scrolling Library table keeps draggable, session-persistent columns while making divider placement, hit tracking, and large MP4/MP3 list switches more responsive.
- Selected Library details now use a bounded responsive rail with clearer title, metadata, saved-location, thumbnail, tags, and description hierarchy. Tags and descriptions retain usable independently scrollable space, and ultrawide layouts no longer stretch the table into empty space.
- Library and Forge menus now include **Copy YouTube URL** using a canonical item or playlist link without unrelated query data, Library actions stay behind one stable **Actions** menu at every size, and the Run Deck fills its available card capacity consistently.
- MP4 **Manual Override** can select AAC or MP3 audio inside the MP4 container, with codec-aware bitrate validation, FFmpeg output, retry, history, and final-output summaries.
- Removing a Library item now stops its exact active run or removes its exact queued run before it starts, then removes the matching Library and Forge presentation history. Downloaded media and folders remain untouched, and unrelated work is preserved.
- Forge's MP4/MP3 selector and output settings configure only the next run; a selected active, queued, completed, failed, stopped, or preview item keeps its own format and output details.
- Failed downloads retain **Retry Download**, while skipped or stopped downloads retain **Restart Download**. Preview items retain direct **Start download** actions in Forge and Library.
- Path-safe output folders preserve recognizable channel, playlist, and video titles within Windows path limits instead of falling back to opaque hashes, while retaining compatibility with older saved locations.
- Forge, Library, and the Run Deck now share a bounded private thumbnail cache, so moved media can retain its artwork. Re-downloading a genuinely missing item replaces the stale saved location instead of creating a duplicate, while temporarily unavailable external storage remains preserved.
- Downloads still use isolated same-volume staging, contract validation, and an atomic final commit so cancellation or a failed encode cannot replace a valid destination with a partial file.
- Download either **MP4 video** or **MP3 audio** from the same Forge field. Bundled yt-dlp, Deno, and EJS format discovery continues to find 1080p and 4K sources when the video provides them, while **Library** keeps the original YouTube source and final VODForge output details together.
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
