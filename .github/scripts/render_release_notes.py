#!/usr/bin/env python3
"""Render the VODForge GitHub Release notes for one version."""

from __future__ import annotations

import argparse
import re

REPOSITORY = "SnowfallHD/vodforge"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")

# Highlights per public version. Add an entry before rendering a new release so
# published notes never fall back to another version's text.
HIGHLIGHTS = {
    "0.2.6": """- One Mac download: a single installer for every Mac. It installs a universal app that runs natively on Apple silicon and Intel.
- The Mac toolbar is now drawn by macOS, so in full screen it keeps its size and slides with the menu bar.
- Interrupted single downloads and URL batches return as Paused, with Resume in Forge and Run Deck. Resume keeps the run’s saved settings and destination; batches continue with the remaining URLs and retain earlier results and issues.
- URL batches show the current video’s title and thumbnail and progress across the whole list. Paused batches retain their last thumbnail, with a VODForge placeholder when none was fetched.
- Watch’s Recently Added rail and See All now share newest-first ordering. See All sits beside the rail heading as a text link.
- Retry opens a choice of the same settings or the selected item’s expanded recovery settings. Recovery uses the shared folder control and keeps the inspector within its column.
- Custom Options keeps selections open, hides the unused CRF or CBR field, and scrolls expanded selectors into view. All runs remains open when hovering over its action controls.
- On Windows, downloads now work when antivirus software or a company network checks secure connections.
- On Windows, fixed a rare case where every download was refused after a restart.
- Updated the YouTube download component (yt-dlp 2026.10.26), with browser impersonation support, and the bundled certificate list, which includes a security fix.
- Usage analytics are optional and can be turned off in Settings with **Share usage analytics**. In the European Economic Area, the UK and wherever the region can’t be determined, VODForge asks first and analytics stay off unless you agree. Analytics never include links, video titles, file names or paths. See [Privacy](https://getvodforge.com/privacy/) for details.
- When analytics is on, failure reports say more about why a video couldn’t be downloaded (for example age-restricted, private, members-only, region-blocked or not yet live), so these problems can be fixed faster.
""",
}


def asset_url(version: str, filename: str) -> str:
    return f"https://github.com/{REPOSITORY}/releases/download/v{version}/{filename}"


def render_release_notes(version: str, *, draft: bool = False) -> str:
    if not VERSION_RE.fullmatch(version):
        raise ValueError("Version must use semantic versioning, for example 1.2.3.")
    highlights = HIGHLIGHTS.get(version)
    if highlights is None and not draft:
        raise ValueError(
            f"Add the {version} highlights to HIGHLIGHTS before rendering final notes."
        )

    mac_dmg = f"VODForge-macOS-universal2-v{version}.dmg"
    windows_installer = f"VODForge-Windows-Setup-v{version}.exe"
    windows_portable = f"VODForge-Windows-Portable-v{version}.zip"
    draft_notice = ""
    if draft:
        draft_notice = (
            "> **Release-team draft:** Do not publish until the Mac DMG and update "
            "files have been Developer ID signed, notarized, stapled and verified, "
            "the checksums regenerated, and these notes finalized.\n\n"
        )
    whats_new = f"\n## What’s new in {version}\n\n{highlights}" if highlights else ""

    return f"""{draft_notice}## Download VODForge

### Mac

[Download VODForge for Mac]({asset_url(version, mac_dmg)})

One download for every Mac. Open it and double-click **Install VODForge**; it sets up a version that runs natively on Apple silicon (macOS 26 or newer) and Intel (macOS 15 or newer).

### Windows

**Recommended:** [Download the Windows installer]({asset_url(version, windows_installer)})

[Download the portable Windows version]({asset_url(version, windows_portable)}) only if you specifically do not want an installed app.

Already using VODForge? It updates itself: choose **Check for updates**, or wait for the update prompt.
{whats_new}
Checksums for every download are available in `SHA256SUMS.txt` below. The Mac ZIP files are in-app update files: `VODForge-macOS-universal2` for VODForge 0.2.6 and later, and `VODForge-macOS-arm64` and `VODForge-macOS-x64` (the same app under the names older versions look for) for 0.2.5 and earlier. New installs should use the Mac download above.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--draft", action="store_true")
    args = parser.parse_args()
    print(render_release_notes(args.version, draft=args.draft), end="")


if __name__ == "__main__":
    main()
