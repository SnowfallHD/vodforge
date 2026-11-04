# Universal macOS app and DMG

From the next public release, every Mac gets one download: a DMG that installs a
universal2 `VODForge.app` (native arm64 and x86_64). The legacy Apple silicon and
Intel ZIP names keep carrying that same universal app so VODForge 0.2.5 and earlier
can still update. The release-facing plan is in [Releasing VODForge](../docs/release.md).

Per-architecture minimums are unchanged: Apple silicon needs macOS 26 or newer and
Intel needs macOS 15 or newer, until the older OS is actually tested.

## Current status (November 2026)

- **In the release pipeline.** The **Build Release Draft** workflow builds the
  unsigned universal app (`macos-universal` job), and `finalize_macos_release.sh`
  signs it, builds the installer and DMG, and uploads all Mac files. The steps
  are described in [Releasing VODForge](../docs/release.md).
- **Not yet run end to end in CI.** The pipeline was assembled in November 2026
  from the scripts used for the private builds of Oct 17–18, 2026 (universal app
  and installer DMG Developer ID signed, notarized and stapled; Apple submission
  for the DMG `1722a79b-db9b-4cfe-a397-e9921ae19c21`). Helper collection and wheel
  fusing were exercised locally on Apple silicon. The first draft run is the
  first time the whole chain runs together; watch its `macos-universal` job.
- **Not yet verified end to end:** updating a signed 0.2.5 install to the
  universal app on both architectures (including Repair). Signed universal builds
  passed the packaged smoke test under Rosetta on Oct 19–20 after the Intel
  startup fix below; an Intel Mac ran the app normally.

The evidence from the private builds (receipts, Apple submission IDs, hashes) is
recorded in `change-and-test-log.md` entries from Oct 16–20, 2026.

## How the release builds it

| Step | Where | What it does |
| --- | --- | --- |
| 1. Helpers per architecture | `scripts/collect_macos_helpers.py` on the Apple silicon and Intel runners | Copies FFmpeg, ffprobe and Deno plus every non-system library they load into a flat folder, stored under the names the loader asks for. |
| 2. Universal Python | `scripts/create_universal_python_env.py` | Installs the pinned python.org universal2 Python (SHA-256 and Apple signature checked), creates a virtual environment, downloads each dependency for both architectures at the same version, and fuses packages that only publish separate arm64 and x86_64 wheels into universal2 wheels. Refuses any package whose architectures differ in more than compiled code. Checks that both architectures import the app's dependencies. |
| 3. Universal helpers | `scripts/assemble_universal_helpers.py` | Combines the two helper folders with `lipo` and rebases each library reference. It keeps the distinct ARM x265 ABI 217 and Intel ABI 216. It never merges finished apps. |
| 4. App | `scripts/build_universal_macos.py --build` | Read-only input check (universal executables and extensions, per-architecture deployment floors, no wrong or unused thin libraries), then PyInstaller `--target-arch universal2` from clean source, with the same contents as the regular build (`scripts/macos_package_contents.py`). The finished app's dependency closure is audited. |
| 5. Sign the app | `scripts/sign_universal_macos.py` | Developer ID signature with no entitlements on either architecture, notarization (notarytool profile `kryden`), stapling and Gatekeeper check. |
| 6. Installer and DMG | `scripts/finalize_universal_macos.py` (calls `build_macos_installer.py` and `build_macos_dmg.py`) | Builds the single-icon **Install VODForge** app around the signed app and signs, notarizes and staples it without re-signing the app inside. Then builds the branded DMG and signs, notarizes and staples it. Also writes the universal update ZIP and its two legacy-name copies. |

Steps 1–4 run in CI; steps 5–6 run on the signing Mac.

**Python version:** the universal environment uses python.org 3.13.17, the newest
3.13 release with a macOS installer (later 3.13 releases are source-only). To move
on, update `PYTHON_VERSION` and `PYTHON_PKG_SHA256` in
`scripts/create_universal_python_env.py` from python.org's release file list.

**Intel and entitlements:** the per-architecture Intel app used to be signed with
`com.apple.security.cs.allow-unsigned-executable-memory` because PyObjC and ctypes
callbacks allocated libffi closures at startup. Those paths were replaced with a
compiled native bridge (Oct 19, 2026), and the universal app runs on Intel with no
entitlements. Don't add that entitlement back; if a new Intel startup hang appears,
look for a new libffi closure first.

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
