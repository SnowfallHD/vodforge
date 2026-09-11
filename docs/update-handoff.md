# Update handoff repair

The Windows updater previously launched Inno Setup and assumed Restart Manager
would close/restart the app. It did not update the download label or observe
installation success. Its test asserted argv only. Installer QA separately
installed an app; neither check proved an upgrade of a running older version.

## Runtime changes

- Windows signature verification and the detached PowerShell helper use
  `CREATE_NO_WINDOW`. PowerShell scripts resolve only their runtime’s built-in
  modules, avoiding incompatible module paths inherited from PowerShell 7. The helper additionally specifies Hidden. The installer
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

These changes ship in 0.2.1 after signed-artifact and running-upgrade gates.
They do not retrofit an installer already downloaded by users. Genesis was diagnosed separately: earlier QA registration directed its successful
update into the other installed copy. The new helper was then observed updating
the actual running directory, correcting registration and reopening the app
without a visible PowerShell console. That demonstration used the signed public
0.2.0 installer; it does not publish these newer recovery changes.

## Actionable recovery and repair

Failures before app exit use the existing in-app modal surface. Detached Windows
failures use an app-styled, borderless Windows Forms surface because the main
application may no longer run. Both expose Repair VODForge, Open download page,
Later, and a separate Technical details view. The detached surface uses the last
app content bounds and clamps placement to the monitor work area. It has its own
close/drag/keyboard controls; it does not inherit the Windows title bar.

Repair explicitly fetches the latest stable official installer, checks the
published SHA-256 and timestamped publisher signature, and installs into the
same executable directory. Downloaded checksum content can be text or byte[] on
Windows PowerShell; both are parsed, and missing/duplicate hashes are rejected.
The helper is written to a uniquely named UTF-8 script instead of exceeding
Windows' command-line limit with an encoded script. It still starts hidden and
must acknowledge readiness before the app closes.

After graceful exit, root saved-data files are copied to a per-handoff backup
and their hashes verified. Logs/update payload directories are excluded; media
is never moved or deleted by repair. The original backup is retained across
retries. Data hashes are checked after installation and before relaunch. A data
change disables automatic repair/relaunch and retains the backup rather than
claiming preservation. This does not claim that later app migrations leave
saved files byte-identical.

Installer failure, wrong installed version, signature rejection, parent timeout,
backup failure, changed saved data, relaunch failure, and repair-download failure
have distinct next steps. Raw errors and the receipt path remain in Technical
details. Manual fallback names the correct installation folder and tells the
user to open the Windows setup file and click Install without uninstalling first.

Recovery regressions execute successful retry, offline repair, data-change
refusal, original-backup preservation, and text/byte checksum responses. The
required native gate includes hidden/revealed cause, visible actions, callback,
and in-app centering. A Windows Forms check verifies owned chrome, bounded
buttons, and app-relative placement on Windows.

Genesis visible demonstrations use real recovery code with explicit OS/download
doubles and disposable files. The user observed successful test repairs in
cases 1–4; their layout feedback drove the owned chrome and app-relative placement.
A separate real download check fetched signed public 0.2.0, SHA-256
`bf7117a864c34cf2ed45d603572c390c9d5919b217278cab2629442f40b09ded`, without
executing it. This is not a newly packaged full repair-installation receipt.
