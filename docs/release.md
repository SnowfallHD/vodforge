# Releasing VODForge

This is the step-by-step guide for shipping a public release. The evidence rules
it relies on are defined in [the release gate](../engineering-quality/RELEASE_GATE.md)
and [the telemetry release gate](../engineering-quality/TELEMETRY_RELEASE_GATE.md).

A release is one source commit on `main`, built once, signed once, tested as the
exact signed files, and published unchanged. Rebuilding or re-signing after testing
creates new files and restarts testing.

## What a release publishes

| File | Who uses it |
| --- | --- |
| `VODForge-macOS-universal2-v<version>.dmg` | **The Mac download on the website and in the release notes.** Opens the single-icon installer window and installs one universal app that runs natively on Apple silicon and Intel Macs. |
| `VODForge-macOS-universal2-v<version>.zip` | In-app updates for VODForge 0.2.6 and later, whose updater asks for this file first. |
| `VODForge-macOS-arm64-v<version>.zip` | In-app updates for VODForge 0.2.5 and earlier on Apple silicon. **Legacy only**: see below. |
| `VODForge-macOS-x64-v<version>.zip` | In-app updates for VODForge 0.2.5 and earlier on Intel. **Legacy only**: see below. |
| `VODForge-Windows-Setup-v<version>.exe` | The Windows download, and Windows in-app updates. |
| `VODForge-Windows-Portable-v<version>.zip` | Windows portable download. |
| `SHA256SUMS.txt` | Checksums for every file above; in-app updates refuse files that don't match. |

The website offers exactly one Mac download, the DMG. It never links the ZIP files.

Mac minimums stay per architecture inside the universal app: macOS 26 or newer on
Apple silicon, macOS 15 or newer on Intel (`src/lib/platform-requirements.ts` in the
website repo). Don't change those claims without testing on the older OS.

## Why the Apple silicon and Intel ZIPs still exist

Releases up to 0.2.5 shipped a separate app per architecture, and their built-in
updater only looks for `VODForge-macOS-arm64-v<version>.zip` or
`VODForge-macOS-x64-v<version>.zip`. They can't open a DMG. Many users don't update
often, so those installs will keep asking for these names for a long time.

The legacy ZIPs therefore contain **the same universal app** as
`VODForge-macOS-universal2-v<version>.zip`, under the old names. That works because
the 0.2.5 updater checks only that the app is VODForge, signed by our Developer ID
team, notarized and accepted by Gatekeeper. It doesn't check the architecture, and
it accepts files up to 4 GB. After one such update the user is on the universal
app, and its updater asks for the universal file from then on.

**When to stop publishing the legacy names:** when the CRM's version breakdown shows
essentially no active Macs on 0.2.5 or earlier over the last 30 days. After that,
anyone still on an old version sees "This release does not include an update for
this computer" and can install the DMG from the website, which replaces the old app
normally. At the same time, remove the architecture-name fallback in
`release_asset_for_platform` (`yt_downloader/updates.py`), which only exists for
releases that predate the universal file.

## Before a release

Run these on the exact commit being released. A failure blocks the release; don't
waive it by rerunning until it passes.

1. **Website and backend first.** Deploy any website/Worker change the app depends
   on, apply its D1 migrations, and register the new version in
   `released_app_versions` (one migration per release, for example
   `migrations/0026_release_0_2_6.sql` in the website repo). Without this, the server
   rejects the new version's telemetry. See the website repo's
   `docs/telemetry-operations.md`.
2. **CI.** The **Tests** workflow passes on all six jobs (macOS, Windows and Linux,
   Python 3.11 and 3.13).
3. **Engineering-quality harness.** On the signing Mac:

   ```sh
   ./engineering-quality/run fast
   ./engineering-quality/run normal --output-dir engineering-quality/reports/<normal-id>
   ./engineering-quality/run deep --soak-jobs 100 \
     --e2e-result engineering-quality/reports/<e2e-id>/e2e-result.json \
     --output-dir engineering-quality/reports/<deep-id>
   ```

   Then freeze the final signed archive as a candidate, run the packaged journey
   against it, and bind everything with `release-receipt`. The exact commands are in
   [the release gate](../engineering-quality/RELEASE_GATE.md). The receipt must report
   every required check as passed.
4. **Telemetry journeys.** Run the preview-D1 telemetry journey on the final signed
   Mac and Windows builds, plus the consent-denied and telemetry-off checks
   ([telemetry release gate](../engineering-quality/TELEMETRY_RELEASE_GATE.md)).
5. **Hands-on testing on three machines**, using the final signed files:
   - **Apple silicon Mac:** install from the DMG. Download an MP4 and an MP3, check
     Library, Watch playback, My Files and Issues & Recovery, enter and leave full
     screen, reveal the menu bar, resize the window, then quit and relaunch.
   - **Intel Mac:** the same, from the same DMG.
   - **Windows PC:** the same, with both the installer and the portable ZIP.
     Windows runs go through the established SSH route and the QA folder
     `E:\VODForgeQA` (see `engineering-quality/runners/README.md`).
6. **Updates from the previous public release.** On each of the three machines,
   install the current public version in an isolated test profile and point its
   updater at the candidate through the local QA update feed instead of GitHub
   (`python -m quality_harness.update_fixture` with `VODFORGE_QA_UPDATE_FEED` on the
   Macs; `engineering-quality/runners/windows-update-qa.ps1` on Windows). Nothing is
   published for this test. Confirm the update installs and relaunches, then run
   **Repair**, and confirm saved history and media are untouched. On the Macs this
   is the test that a 0.2.5 install accepts the universal app under its legacy name.
7. **Known defects.** `engineering-quality/acceptance/user-reported-defects.json` has
   no open item that this release claims to fix without packaged evidence.
8. **Release notes.** `.github/scripts/render_release_notes.py <version>` renders
   them; check the text describes this release.

## Performing the release

1. **Draft.** With clean, pushed `main`, run the **Build Release Draft** workflow in
   GitHub Actions with the version (for example `0.2.6`). It builds and signs the
   Windows installer and portable ZIP with Azure Artifact Signing, builds unsigned
   review Mac apps for arm64 and x64, and creates a **draft** release. Nothing is
   public yet.
2. **Mac signing.** On the signing Mac, from clean `main`:

   ```sh
   ./finalize_macos_release.sh <version>
   ```

   This downloads the review builds, signs, notarizes, staples and Gatekeeper-checks
   them, runs the packaged runtime smoke test, uploads the signed archives,
   regenerates `SHA256SUMS.txt` and refreshes the release notes.

   > **Not automated yet: the universal DMG.** `finalize_macos_release.sh` still
   > produces separate arm64 and x64 apps. The universal app and DMG are built from
   > existing scripts that have so far only been run by hand for private builds:
   > `scripts/assemble_universal_helpers.py` (combine the two architectures' helper
   > binaries), `scripts/build_universal_macos.py --build` (universal app from a
   > universal Python environment), `scripts/sign_universal_macos.py` (sign,
   > notarize, staple), `scripts/build_macos_installer.py` (single-icon installer
   > app) and `scripts/build_macos_dmg.py` (the DMG). Folding these into
   > `finalize_macos_release.sh` is required before the first DMG release. It must
   > upload the DMG, the universal ZIP and the same universal app under both legacy
   > names, with all of them in `SHA256SUMS.txt`. See
   > [universal macOS packaging](../engineering-quality/UNIVERSAL_MACOS.md).
3. **Test the draft's files.** Run everything in "Before a release" against the files
   attached to the draft, not local rebuilds.
4. **Publish.** Publish the draft in GitHub. It becomes the latest release, and
   installed apps see the update within six hours or on **Check for updates**.
5. **Website.** Push the website repo's `main`. Its build reads the latest release
   (`npm run sync:release`) and refuses to build if the DMG, Windows files or
   checksums are missing, so the website can only go out once the release is
   public. Apply any pending D1 migrations first, in the order given in the
   website README ("Pending production migrations"). Confirm the live site offers
   the new version's DMG and Windows downloads, and that the old
   `/download/mac-arm` and `/download/mac-intel` links land on the DMG. Then
   regenerate the session-replay text allowlist from that build
   (`python3 scripts/generate-replay-public-content.py`) and commit it.
6. **Afterwards.** Watch the CRM for `client_update` events and updater failures over
   the next days. Check that downloads from the website start correctly.

## After the release

- Record what shipped and what was tested in
  `engineering-quality/change-and-test-log.md`.
- Keep the legacy Mac ZIP names in every release until the retirement condition
  above is met.
