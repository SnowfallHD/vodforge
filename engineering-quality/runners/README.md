# Packaged-app UI driver protocol

## Unattended pre-release journey

`release_journey.py` runs one packaged app through the pre-release journey
without anyone at the keyboard: hard kill mid-download, relaunch, a new
download while the interrupted run is held, Resume, real YouTube MP4 and MP3,
then a normal quit and reopen. It finds controls by accessible name (macOS
Accessibility, Windows UI Automation through pywinauto), dismisses prompts a
user would, and probes every saved file with the app's own ffprobe. State lives
in the output folder and telemetry is off. On Windows, run it through
`windows-release-journey.ps1` (interactive-session task; `-Installer` for the
signed installer with the PC's registration restored afterwards). This journey
replaces the per-commit native controller scripts earlier rounds wrote by hand;
the screenshot-backed recorder below remains for release receipts.

On an Apple silicon Mac, `--arch x86_64` runs a universal app as Intel code
under Rosetta and fails unless macOS reports the process as translated
(`P_TRANSLATED`); the result records `app_arch` and, at launch, `rosetta`.

`mac-remote-journey.sh <tailscale-machine> <user> <app> <folder>` runs the
journey on another Mac, such as the Intel test Mac (`julies-macbook-air`, user
`julie`). It pins the host key Tailscale reports, keeps everything on the
remote side in `~/VODForgeQA` (app copy, harness, a uv-managed Python 3.13 with
pyobjc, the run), stops early if SSH sessions there lack Accessibility
permission, and copies `journey-result.json` back. The remote Mac's own
VODForge install is not touched.


`deletion_journey.py` deletes saved media through the app's own Library
buttons (Details, More actions, Move media to Trash) in the same isolated
profile: one YouTube video saved as MP4, MP3 and Original audio under one
channel. It checks that deleting one item keeps the channel, that an emptied
sibling folder doesn't keep it, and that a user's own file does. Every moved
file is found in the real Trash or Recycle Bin at the path the app recorded,
compared with the original, and taken back out. Run it like the release journey;
remotely with `JOURNEY=deletion_journey.py mac-remote-journey.sh ...` or
`windows-release-journey.ps1 -Journey deletion_journey.py`.

`VODFORGE_NATIVE_TRASH_RECEIPTS=<file.jsonl> pytest tests/test_archive_trash_hierarchy.py`
runs the 56 deletion-hierarchy cases through the real system Trash on macOS or
Windows instead of a stand-in folder, writing one receipt per file.

## Reproducing a Windows test failure

`windows-dev-tests.ps1 -Source <checkout> -Tests <a,b,...>` runs pytest on the
Windows test PC the way CI does (offscreen, software Qt). It fails with exit 2
if the account's real VODForge folder changed during the run: tests on that PC
run as its real user, so restore the profile first if that ever happens.

## Windows Genesis probes

The `windows-*.ps1` / `windows-*-probe.py` runners use `E:\VODForgeQA` and
explicit source/run identities. Bootstrap accepts an exact Git archive plus
SHA-256, builds a telemetry-disabled development executable, and records its
hash. The installer runner requires authorization to replace the machine's
existing VODForge registration; it must not be used on an ordinary user's PC.
Its Inno compiler download must pass Authenticode publisher verification.

`windows-interactive-qa.ps1 -SourceCommit <40hex> -JobId <32hex> -Suite <suite>`
creates a disposable task in the logged-in interactive session (never session
0). Suites are `native`, `playback`, `portable-playback`, `installed-playback`,
`browser`, and `app`. Read `runs/<JobId>/receipt.json`, the suite-specific
receipt/log, and screenshots before concluding success. Dispatch success is
not test success. After completion, unregister only that exact task. Preserve
failed evidence and use a fresh JobId for retries. Do not stop unrelated apps.

Browser matrix scripts need a freshly built site ZIP in
`artifacts/site-client-current.zip`; they use a separate Brave process/profile,
intercept external/API traffic, and exercise the built claim-page JavaScript.
The default-browser probe is separately loopback-only and never reads cookies
or changes browser configuration. These receipts are **not** interchangeable
with the strict full-app E2E recorder below. See `../history/ANALYTICS_JOURNEY_QA.md` for
executed coverage and remaining combined-journey gaps.

## Canonical full-app recorder

`./engineering-quality/run packaged-e2e --candidate <candidate-artifact.json>` freshly extracts the frozen candidate ZIP, then launches the real packaged VODForge application with isolated state, a loopback legal-media origin, and a versioned evidence session. It deliberately does not replace VODForge's UI or worker with test doubles.

Do not drive the app until `session.json` reports `driver_ready: true`. At that point the direct child PID, process group, executable path/hash, full bundle tree, runtime version, environment, state paths, nonce, and app-written startup attestation agree. The window title contains the launch-specific token from `current_launch`.

The current macOS driver is automation-assisted: use a visible desktop driver to perform each instruction in `session.json`, capture the resulting VODForge window, and record the event in the exact listed order:

Use the app's real-user `Command+1`, `Command+2`, and `Command+3` shortcuts to select Forge, Library, and Activity. The Library screenshot must visibly show the completed item; sending `Command+2` is navigation, not evidence by itself.

```bash
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<session>/session.json \
  --event app_visible \
  --screenshot /path/to/current-vodforge-window.png \
  --window-pid <current_launch.pid> \
  --window-owner-pid <CoreGraphics-owner-pid> \
  --window-id <CoreGraphics-window-id> \
  --window-title-token <current_launch.window_token>
```

The recorder independently queries CoreGraphics for that native window ID and accepts the event only when the onscreen application-layer window's owner PID and exact nonce-bearing title match the attested launch. It then copies the screenshot into the session, hashes it, timestamps the event, rejects duplicates/out-of-order events, and updates `driver-events.json`. `restart_requested` is the only non-visual control event and can request relaunch atomically; it still requires the current launch/window identity arguments:

The same event recorder supports an attested Windows driver session. Its native
witness uses Win32 to verify the live top-level HWND, owning PID, exact title and
visible bounds. Process identity retains executable hash, creation time, direct
parent, isolated environment and startup-attestation checks; POSIX process groups
are not asserted on Windows. The Windows driver owns normal process shutdown and
relaunch. It must not invoke the Mac process-group cleanup routines. The driver
must prepare the actual session from `attest_owned_launch` and never invent
verified flags. Use the declared engineering-quality dependencies and an isolated
QA temp directory. Separate Windows player/dialog captures use the verified window
bounds with a second identity check after capture, recorded explicitly as
`win32-window-bounds`; inspect them for occlusion before accepting the UI state.

```bash
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<session>/session.json \
  --event restart_requested \
  --window-pid <current_launch.pid> \
  --window-owner-pid <CoreGraphics-owner-pid> \
  --window-id <CoreGraphics-window-id> \
  --window-title-token <current_launch.window_token> \
  --control-action relaunch
```

After `restart_observed`, request the final normal quit with `--control-action finish` on that visible event. A receipt is not accepted merely because event names exist: the collector validates order, timezone-aware timestamps, native window receipts, screenshots and hashes, two clean launches, immutable candidate/archive/bundle identity before and after the journey, bundled ffprobe readability, pipeline diagnostics, persistent history, stable output hashes, and cleanup.

This recorder standardizes evidence collection; it is not itself a UI automation engine. Until a repository-owned native driver can reliably address VODForge's custom Tk navigation, the tier remains explicitly automation-assisted and reports missing UI evidence as a benchmark gap rather than promoting headless success.
