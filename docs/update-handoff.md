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

## Successor automatic updates — 2026-10-16 (unpublished)

Cooper explicitly requested a single default-on **Update automatically** setting,
then clarified installation should happen on normal application close. This
supersedes the earlier no-auto-update-setting scope; the old signed candidates
and their native acceptance receipts do not qualify this new runtime.

The shipped 0.2.5 and predecessor Qt startup already scheduled the metadata check
at `QTimer.singleShot(0)`. There was no intentional one-minute initial delay.
The check uses a 15-second network timeout; a busy updater retries scheduling in
30 seconds. The header previously concealed the checking state. That is a proven
presentation gap, not a measured explanation of Cooper's entire observed delay.
The successor exposes an unobtrusive checking notice immediately and retains the
existing discoverable availability notice without opening a modal. Existing
local logs now record check start, elapsed completion and applied availability;
no URL, release body, new analytics event or network request is added for timing.

`automatic_updates` lives in the existing atomic settings file. Missing means On;
explicit False stays Off. Malformed settings, failed writes or an app location
where the replacement lease cannot be owned fail closed for automatic updates.
Explicit On checks immediately, or reauthorizes an already verified staged
newer update. Off revokes automatic handoff immediately and cancels an active
automatic download at its next chunk boundary (an outstanding socket read may
finish first). Manual Check, Download, Restart and Repair remain available. Startup checks and
availability notices stay on even when this setting is Off. While an automatic
download is running or ready, the same existing popup primary action becomes
**Install now**: it promotes that same payload to the existing explicit manual
restart flow, with no duplicate download. Off does not cancel this explicit
manual request. Hiding or ignoring the offer leaves automatic staging and
normal-close/no-relaunch behavior intact; no extra button or popup is added.

The existing download owner fetches official release metadata and its checksum
manifest, checks exact asset size/SHA-256 and verifies the platform signature.
The downloaded archive/installer is the durable stage: a later launch must fetch
a fresh trusted manifest and revalidate exact cached bytes before reuse. It then
prepares a new target-specific Mac stage or revalidates Windows Authenticode.
No mutable saved JSON path is trusted as authorization to install. Unique owned
`.part` files are never promoted after an interrupted download. There is no
installer/helper launched merely because a staged update exists or work is idle.

Only `aboutToQuit` authorizes the automatic close handoff, after the existing
settings/history/runtime owners have flushed. Work/recovery uncertainty before
or after cleanup, an unready download, cleanup failure, a failed fresh settings
read, saved Off or a prior handoff prevents it. Other `Bridge.close()` cleanup
paths have no normal-quit authorization. A canceled window close starts no helper.
Crashes and forced termination cannot run this authorization path; next launch
may recover cached bytes but must wait for another accepted normal quit.

Automatic helpers wait for the exact parent exit, install with **no relaunch**,
and record `installed` rather than `relaunched`. Manual explicit restart retains
its original relaunch behavior. Existing Mac team/bundle/notarization/Gatekeeper
checks and swap rollback remain; Windows rechecks the timestamped publisher,
bound installer digest/version and data preservation before returning. Windows
backs up app data, not a complete rollback of installed application binaries.
Staged payload hash and release version are bound through the existing owner and
rechecked at replacement; installer creation alone is never a success receipt.

The packaged app holds a shared OS lifetime lease adjacent to its target;
automatic helpers require the matching exclusive lease after parent exit. If a
second app opens first the helper defers; if replacement already owns the lease,
startup reports that the update is finishing and exits without loading the app
being replaced. No competing process is killed. The lease is acquired at Python application
startup, after the frozen bootloader/import phase; it does not claim to serialize
the kernel's initial executable load. A reopen during replacement currently
reports the short retry message on stderr and exits; it is not a seamless waiting
window. Windows loaded-file refusal is an installation failure, not proof of a
completed update or complete binary rollback. macOS uses matching BSD `flock`/`lockf -kn -t 0`;
Windows uses shared CRT byte locks and the helper's exclusive .NET byte lock.
Locks release on process exit/crash; an empty leftover lock file is not a pending
update or reason to install. Unwritable/unsafe lock locations leave ordinary app
use available with automatic updates unavailable. The additional exact-target
process check also conservatively refuses replacement of an already running copy.

### Evidence and remaining gates

`tests/test_automatic_updates.py` exercises settings durability/failure, explicit
On/Off, late ready results, cancellation, normal-close-only authorization, saved
Off at handoff, state-flush failure/uncertainty, actual canceled Qt window close,
no install while open, cache reuse/tamper and helper no-relaunch/signature contracts.
The in-memory negative control removes only the normal-quit admission gate; the
cleanup-close test then fails. Canonical files are not mutated by that test.
Earlier checks covered explicit one-click restart/active jobs, not the newly
introduced default automatic close/late-revocation lifecycle; that is why those
valid checks alone could not establish this behavior.

Actual isolated Windows probes independently verify both directions of CRT shared
vs .NET exclusive byte-lock exclusion and successful reacquisition after release.
They are locking evidence, not a signed helper installation or native update UI
transaction. Local helper-runtime tests execute Mac temporary-folder swaps with
signing/launch tools doubled; they do not confer Apple or Windows package trust.

Before public release, rebuild/freeze this exact runtime on each supported
architecture, repeat affected signed native close-install/no-relaunch and next
launch checks, exercise Off while staged and canceled-close with actual active
work, and retain data/profile hashes. Windows additionally needs real signed
installer acceptance in the maintained isolated installer fixture. Physical Intel
GUI acceptance and the old Windows startup diagnostic gap stay separate. No prior
44 artifact or headless portable smoke may be relabeled as these new guarantees.

The first actual Mac helper/lease fixture exposed an implementation mistake:
`lockf -n` means existing-file-only and waits indefinitely by default; the utility
uses BSD locks rather than POSIX record locks. Its original 15-second timeout is
retained. The corrected matching `flock` plus `lockf -kn -t 0` passes actual OS
exclusion in both directions and the generated temporary-bundle no-relaunch swap.
No owned helper survived the original timeout. This source-level fixture doubles
signature commands and is still distinct from a signed native update transaction.

Final source qualification receipts are under
`build/automatic-updates-20261016/`: `final-source-matrix.log` has 109 passed / 19
platform skips, with additional retained 39-case explicit-manual owner coverage.
`windows-semantic/transport-result.json` has 12 actual Windows helper control-flow
passes with OS/installer/signature doubles, including close-installed/no PID and
manual relaunch. The Windows helper function is byte-identical to that executed
fixture (`windows-semantic/final-function-binding.json`). Actual Windows locking
probes in both directions are adjacent to the root's Windows private qualification
receipts. The corrected actual Mac helper/reopen/lock checks pass three cases.
Scoped updater/settings/session mypy passes; Qt main still reports 81 existing
Qt-stub/decorator errors, exactly matching the same-module HEAD shadow baseline
with no added or removed errors. This is not a blanket typecheck pass.

Automatic package installation is supported only where an official matching Mac
or Windows asset and a writable existing app location pass all checks. A missing
platform asset retains manual download-page guidance. No new installer privilege,
credential, permission grant, public feed or release publication is introduced.
