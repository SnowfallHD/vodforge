# Universal macOS app and DMG

From the next public release, every Mac gets one download: a DMG that installs a
universal2 `VODForge.app` (native arm64 and x86_64). The legacy Apple silicon and
Intel ZIP names keep carrying that same universal app so VODForge 0.2.5 and earlier
can still update. The release-facing plan is in [Releasing VODForge](../docs/release.md).

Per-architecture minimums are unchanged: Apple silicon needs macOS 26 or newer and
Intel needs macOS 15 or newer, until the older OS is actually tested.

## Current status (November 2026)

- **Built privately, not yet in the release script.** Universal apps were built,
  Developer ID signed with empty entitlements on both architectures, notarized and
  stapled on Oct 17–18, 2026. The single-icon installer DMG was built, signed and
  notarized too (last refresh: Apple submission `1722a79b-db9b-4cfe-a397-e9921ae19c21`,
  Oct 18). On an Intel Mac the installer completed a default install into
  Applications; on Apple silicon only its Replace/Cancel prompt was observed.
- **Release automation is the remaining gap.** `finalize_macos_release.sh` still
  signs separate arm64 and x64 apps. The steps below run by hand and must be folded
  into it before the first DMG release.
- **Not yet verified end to end:** updating a signed 0.2.5 install to the universal
  app on both architectures (including Repair), and Intel under Rosetta in the
  headless smoke test. A signed Rosetta smoke run timed out in its Qt phase on
  Oct 17, with the cause unknown; an Intel Mac ran the app normally.

The evidence from those private builds (receipts, Apple submission IDs, hashes) is
recorded in `change-and-test-log.md` entries from Oct 16–18, 2026. The build folders
themselves were removed in the Oct 30 cleanup.

## Build steps and their owners

| Step | Script | What it does |
| --- | --- | --- |
| 1. Helpers | `scripts/assemble_universal_helpers.py --arm A --intel B --output OUT` | Combines the verified thin helper binaries (FFmpeg, ffprobe and Deno, with their libraries) from the two architectures into universal ones. It keeps the distinct ARM x265 ABI 217 and Intel ABI 216 and rebases each load edge. It never merges finished apps. |
| 2. Inputs check | `python -m scripts.build_universal_macos --input PATH --report REPORT.json` | Read-only. Requires universal executables and extensions, checks each architecture's deployment floor, and rejects wrong, missing or unused thin libraries. |
| 3. App | `python -m scripts.build_universal_macos --build --source CLEAN_SOURCE --python UNIVERSAL_VENV/bin/python --tools HELPERS --output OUT --report REPORT.json --version V` | PyInstaller `--target-arch universal2` from a clean source tree. The finished app is audited for loader, executable and rpath dependencies before the build receipt is written. |
| 4. Sign | `python -m scripts.sign_universal_macos --app APP --output OUT` | Developer ID signature with no entitlements on either architecture, notarization (notarytool profile `kryden`), stapling and Gatekeeper check. The thin-build script applies Intel's executable-memory entitlement to the whole binary, so don't use it for universal apps. |
| 5. Installer | `python -m scripts.build_macos_installer --payload SIGNED_APP --output OUT` | Builds the single-icon **Install VODForge** app. Sign and notarize it like step 4. |
| 6. DMG | `python -m scripts.build_macos_dmg --app SIGNED_INSTALLER --output VODForge-macOS-universal2-vV.dmg` | Refuses thin or unsigned inputs and creates the branded Retina window without Finder scripting. Then sign, notarize and staple the DMG itself and re-verify its checksum. |

**Universal Python environment (step 3):** use the official python.org universal2
Python, hash-verified PyPI wheels, and universal Qt and PyObjC wheels. Where a
dependency publishes only thin wheels, combine the arm64 and x86_64 wheels. The
environment from the private builds was not kept, so the release automation must
recreate it from pinned hashes.

## Update behavior

- The current updater (`release_asset_for_platform` in `yt_downloader/updates.py`)
  asks for `VODForge-macOS-universal2-v<version>.zip` first and falls back to the
  architecture names for releases that predate it.
- VODForge 0.2.5 and earlier know only the architecture names. Publishing the
  universal app under those names moves them onto it in one update. Their updater
  verifies identity, team, signature, notarization and Gatekeeper but not the
  architecture, and accepts files up to 4 GB.

## Invariant

An architecture label or a dual-architecture launcher doesn't prove a compatible
native dependency closure. Every native file must be checked per architecture.
Thin-package test passes never covered this class of failure.
