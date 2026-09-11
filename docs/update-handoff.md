# Update handoff repair

The Windows updater previously launched Inno Setup and assumed Restart Manager
would close/restart the app. It did not update the download label or observe
installation success. Its test asserted argv only. Installer QA separately
installed an app; neither check proved an upgrade of a running older version.

## Runtime changes

- Windows signature verification and the detached PowerShell helper use
  `CREATE_NO_WINDOW`. The helper additionally specifies Hidden. The installer
  may show installation progress or a useful error; no PowerShell console is
  intended to appear.
- The helper signals readiness before the UI schedules the existing safe-close
  owner. It waits for the exact parent to exit, rechecks the publisher signature,
  installs into the running executable's directory, checks installer exit code
  and PE product version, then explicitly relaunches that executable with a
  reset PyInstaller environment. It records exit status, stage, version, PID,
  executable hash, and installer log. A launch that immediately exits is failure.
- The UI blocks installation during active downloads, queued downloads or local
  conversion. Startup failure leaves the app open with recovery guidance.
- The new installer also handles calls from older updaters: its hidden,
  Unicode-safe preparation script requests normal close only for VODForge
  processes at its exact installation path. Refusal or timeout stops installation
  with an actionable message. Its normal postinstall launch now runs in silent
  mode too. New helpers opt out with `/VODFORGEHANDOFF=1` to avoid double launch.
- macOS retains the existing verified swap, explicit `open`, and rollback on
  relaunch-command failure. The app now uses safe close rather than direct Tk
  destruction before the swap. Existing signature/notarization checks remain.

The updater does not claim installation success from process creation alone.
It does not prove long-term application health merely because the relaunched
process stays alive for three seconds. It does not forcibly terminate media work.

## Tests and release gate

`tests/test_update_ui.py` verifies status transitions, safe-close scheduling,
blocked media work and launch failure. `tests/test_updates.py` covers readiness,
fixed hidden argv, path quoting, signature verification and failure to start.

`engineering-quality/tests/test_update_handoff_runtime.py` executes the generated
PowerShell control flow with OS doubles for success, signature failure, installer
failure, parent timeout, wrong installed version and relaunch failure. On macOS,
`VODFORGE_QA_POWERSHELL=/absolute/path/to/pwsh` enables these semantic tests; this
is not Windows process/installer evidence. The same file executes the macOS swap
against real temporary app folders, with signing and launch tools doubled, to
verify success, relaunch failure rollback and signature refusal.

`engineering-quality/runners/windows-update-qa.ps1` requires signed baseline and
candidate installers plus the exact candidate executable. Run in a disposable
interactive Windows QA account, since installers update that account's uninstall
and shortcut registration. It uses isolated media/settings roots and disables
telemetry. It starts the baseline visibly, runs the production handoff, verifies
old-process exit, new-process visibility/path and exact candidate hash. Its
`-LegacyHandoff` mode separately reproduces the flags sent by old updaters.
It explicitly does not claim a click through the updater UI.

The Windows release workflow runs both modes before uploading distributable
artifacts. Failures block the Windows job and downstream release publication;
evidence is uploaded even when the job fails. Windows CI also runs fault tests.
Missing Windows execution must remain unproven, never be reported as passed
because the tests were skipped on a Mac.

## Deployment boundary

These are source and test changes until a fresh signed release is built, passes
the running-upgrade gates and is published. They do not retrofit the installer
already downloaded by users. Existing affected users can close VODForge and run
a verified installer manually. Genesis's exact install failure remains
unconfirmed without its process paths, version and installer outcome evidence.
