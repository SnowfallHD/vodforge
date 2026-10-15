## Shared fixture deltas, reuse sidecars and exact latency roster — 2026-10-11

- One bounded 54-scenario regeneration at clean harness source `018f5105eeed5b1240a60b369cba3cf3d9b31bc9` replaced only lost raw observations. All 54 functional scenarios passed; independent review initially retained 50 passes and four failures. Those failures were two incorrect global-empty fixture assumptions, a reuse oracle rejecting the production atomic thumbnail-sidecar staging transaction, and three missing resumed-format-hint cases in the exact artwork-latency roster. Original functional results, the initial failed independent assessment and every raw source identity remain unchanged.
- Narrow harness fixes now require a complete pre-worker fixture ledger, immutable history prefix, exact response-count delta and absolute/elapsed clock agreement; earlier completed source requests are allowed. Media reuse permits only a private POSIX staging directory containing its exact regular `sidecar` path during the owned worker interval, with no media progress and no staging at return. Existing independent media SHA/probe/history invariants remain required. The reviewed latency roster adds exactly the three saved-resume-format cases; no minimum, required selector or per-case equality was removed. Its test fixture now carries the actual 208-case successor JUnit and original constituents.
- New valid prior-traffic and sidecar-repair cases failed three times before the fixes; 15 negative controls already failed closed. After corrections, 1,415 focused HTTP404/reliability/duplicate/source-suite cases pass; an additional exact-integer counter control passes separately. The first after attempt retained two failures distinguishing missing clock evidence from contradictory evidence; the corrected evaluator preserves `unproven` for missing constituents. Ruff, format and diff checks pass.
- Independent reevaluation of the same untouched 54 raw observations now passes all 54 with complete phase/assertion mappings. Original 100-job soak completed 100/100, zero retained DownloadJob/YoutubeDL delta, zero descriptor delta, zero owned children/zombies/staging; RSS increased 11,517,952 bytes, so no zero-RSS-growth claim. The raw workspace was archived byte-for-byte (2,828 files, 130,698,709 bytes) with every regular-file hash verified. Receipt paths remain original; archive copies are preservation evidence, not rewritten profiles.
- Evidence: task `release-completion-20261010/gate-missing-observations-018f510/results.json`, `missing-observation-regeneration-assessment.json`, `missing-observation-regeneration-reassessment.json`, `oracle-tests-before.log`, `oracle-tests-after.log`, `oracle-tests-after-attempt2.log`, `oracle-tests-final.log`, and `preserved-regenerated-observations/archive-receipt.json`. Final signed runtime remains `5e581d06cbc00084926a0435e30eb51521ac2f9b`; no product/gate thresholds/candidate bytes changed and no rebuild is needed for these harness fixes. Public 0.2.6 remains unpublished pending exact profile/source composition, four unenrolled domain evaluators, final candidate-bound packaged acceptance and complete Mac/Windows preview telemetry journeys. No already valid native, updater, file-move or process-cleanup check was repeated.

# VODForge change and test log

Consult this log and its linked receipts before assigning or repeating work.
Record changes, actual results and remaining unknowns; do not run tests merely
to populate history. A repeat needs a concrete changed code path, dependency,
configuration, build/environment difference, or defect in the earlier evidence.
Generic final-candidate QA is not a repeat justification. Prior bounded passes
remain bounded passes even when their containing journey failed elsewhere.

Checkpoint: 2026-10-10 23:51 UTC. Released baseline: 0.2.5. Candidate source:
1a4bf9944af4d35fd0d10b930a147039150316e0. No public 0.2.6 release.

| Date UTC | Change / artifact | Platform / scope | Result | Evidence / reuse limits |
|---|---|---|---|---|
| Oct 10 | bf8a46f predecessor | Windows native exports, CPU/NVENC presets, queue removal/Skip/local Stop, player Fit/Fill/float/seek/fullscreen, picker path paste, missing loaded list | PASS, bounded; wrapper FAILED/incomplete | [Native predecessor](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-native-bf8a46f). Retain; bf8a46f→1a4bf99 changed PlayerScene Watch rail presentation plus README/tests only. These runtime paths were unchanged. |
| Oct 10 | 0cc03da / 1a4bf99 | Watch right More to Watch; bottom Recently Added and adjacent > See All | PASS source; PASS Mac bottom native; wider recommendation state UNTESTED | Targeted 13 + adjacent 20 source checks; Mac receipts039–040. Only affected Watch presentation needs further verification. |
| Oct 10 | 1a4bf99 | CI tests / signed build | PASS | Tests38086190293 all six; Build38086253652 all three platforms, artifacts_only. No publication. |
| Oct 10 | 1a4bf99 | Local repository/component/scene | PASS respective suites; selected static scenario FAILED solely nonblocking complexity; three telemetry scenarios PASS | [Selected run](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/normal-1a4bf99-unresolved/results.json): 3465 / 595 / 205 passed. Not a complete NORMAL receipt. |
| Oct 10 | 1a4bf99 | 100-job process and memory lifecycle | PASS | [Soak](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/deep-1a4bf99-soak100/results.json). No children/FD/zombie/staging accumulation; post-warmup RSS −13.6MB. Total allocator growth +105MB is retained, not a zero-growth claim. No changed process path since. |
| Oct 10 | signed Windows 1a4bf99 | CI real production-helper update and legacy handoff | PASS | [Update journeys](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/ci-1a4bf99-windows-update/build/update-journeys). Window visible4563ms. Not native Repair + D1 proof. |
| Oct 10 | signed Windows 1a4bf99 | Live two-source batch titles/artwork/aggregate progress; retry Same/Change; below-fold dropdown scroll | PASS, bounded | [Current native receipts](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-native-1a4bf99), images132/137 and retry/Manual controls. Formal journey incomplete. No repeat without affected change. |
| Oct 10 23:48 | signed Windows 1a4bf99 | Loose import → foreign/nested → another folder | PASS files/scope; FAIL open Detail identity after first move | Native receipts184–201. Video SHA B7FEEE…F8E2D unchanged; both unrelated siblings unchanged; foreign nested folder remained empty. New selection defect requires focused fix and affected validation. |
| Oct 10 23:48 | Developer ID ARM 1a4bf99, pre-notarization | Native export, Description, normal quit/restart | PASS smoke11; not release eligible | [Original result](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/mac-arm64-prenotary-native/e2e-result.json), normal two exits. Telemetry off; direct-artifact development policy. Not promoted to notarized acceptance. |
| Oct 10 | same ARM app | Held resize/release/pointer, selected-item continuous scroll | PASS bounded native observations; acceptance review OPEN | Native030–032/035: intermediate layout responds while held; bounds stable after release; 18 distinct scroll frames. Reconcile existing observations before considering another run. |
| Oct 10 | same ARM app | All runs three-dot hover | PASS; redundant repeat acknowledged | Native044–047. User confirmed prior fix and testing; unchanged path. Do not repeat. |
| Oct 10 23:19 | current Windows QA IID76f6cab0… | Production D1 isolation | PASS scoped checkpoint | [D1 read](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-native-1a4bf99/telemetry-2319-checkpoint.json): zero installations, clients and product events in production; preview operations present. Final consent/update reconciliation OPEN. |
| Oct 10 23:35 | ARM submission ec7378c2-b0e4-4c36-b28e-d45517da2818 | Apple notarization | PENDING | Existing submission In Progress. Do not duplicate; timestamp refers to latest read. |
| Oct 10 | signed/notarized Intel 1a4bf99 | Gatekeeper/runtime; native GUI20s guard | PASS signing/runtime; FAIL startup guard | Frozen20261010T222801Z-b48adc6c; [diagnosis](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/intel-coldlaunch-diagnostic/diagnostic.json) reaches Qt32.427s in image plugin dlopen/Rosetta. Do not repeat unchanged20s attempts or silently relax gate. |

Move selection correction is currently uncommitted. Its original-pump negative
control fails all four cases; the corrected code passes all35 focused cases,
normal Ruff/format/diff and the file-owner type check. The regressions were
placed in existing `tests/test_qt_inspector_actions.py`, which is already in
the maintained Qt test partition. Initial invalid synthetic fixtures are
retained and not used as product-failure evidence.

Receipts: [original negative control](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/move-selection-original-pump-negative.log),
[focused result](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/move-selection-final-focused.log).
Its changed consumer invalidates prior move UI selection/annotation acceptance
only. Export, queue, playback, updater and telemetry implementation are unchanged.
New package/signature identity still needs binding; this is not permission to
repeat unrelated behavioral journeys.

Unknown historical checks remain unknown. Remaining native interrupted single /
batch resume and multiselect standard-nest observations must be checked against
existing receipts before any work is assigned. Formal sequence gaps are not
evidence that an already passing behavior needs to run again.

## Oct 11 resumed-run format hint correction

Native Windows single Resume completed after a normal active quit/restart and
composer detachment/MP3/destination edits. The admitted job and actual independently
probed H.264/AAC export retained its saved MP4/Everyday/1080p/original destination;
the new composer destination stayed empty.
[Bounded native assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-resume-1a4bf99/single-resume-assessment.json).

That native run exposed one stale format hint: Main.qml read the pending composer
format while the selected active job used its saved format. It now reads the
existing forgeDisplayType projection. Actual paused-job recovery plus changed
composer and Resume regressions fail all3 before, pass all3 after; the4 adjacent
saved-settings recovery cases also pass (7 total). Ruff/format/diff checks pass.
[Before](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/resume-format-hint-before.log),
[after](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/resume-format-hint-after.log).
Only this displayed format hint changed. No download, worker, journal, export,
move, updater or telemetry behavior changed; retain their prior valid passes.
The successor package must bind the changed QML bytes. Native abrupt batch
recovery and multiselect standard nests remain open. No public release.

Move selection/annotation correction is committed and pushed as139579b. Its
35 focused passes and original4 negative controls remain valid; successor
artifacts-only Build38097117973 is still running. Windows job passed; Mac
jobs are pending. Existing Apple ARM submission remains In Progress at00:23UTC.


## Oct 11 01:28 UTC — successor artifacts and popup test setup

Runtime source 5e581d06cbc00084926a0435e30eb51521ac2f9b is pushed. Build38098493152
passed all three platforms with artifacts_only; nothing was published. Both Mac
archives are now Developer ID signed, notarized, stapled and Gatekeeper accepted.
The ARM candidate passed the unchanged normal startup guard. Intel native startup
remains open. Their source bindings remain 5e581d0 after this test-only change.

Tests38098316279 passed five jobs and failed Windows/Python3.13 in the popup matrix:
the profile trigger was absent after the initial resize/click; 695 component tests
passed, 9 skipped and 1 failed. The exact isolated failed case passed on
Desktop-Genesis/Python3.13.1. No deterministic product failure was reproduced.
A local resize diagnostic showed pre-polish pointer bounds differing from the
settled layout. The test now waits80ms for the initial resize layout before its
first pointer gesture and reports actual popup/label state instead of StopIteration.
The controlled deferred-polish attempt passed in both conditions; it is not a
negative control or proof of the CI root cause. All25 focused popup cases pass,
plus Ruff/format/diff. Exact successor Windows CI remains required.
[Original failure](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/tests-5e581d0-windows313-failed.log),
[focused pass](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/popup-layout-focused.log).
This change touches tests and this log only; do not rebuild unchanged runtime
archives or repeat unrelated behavioral passes.

The native interrupted single and abrupt batch resume checks now pass within
recorded scope. The batch recovered after an actual process kill, retained the
first completed MP3 hash, resumed the remaining source using saved settings and
destination despite composer changes and the missing original list, and completed
with independently decoded MP3 output. Normal exit0 left no owned children.
[Batch assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-resume-1a4bf99/batch-abrupt-resume-assessment.json).
This is process interruption evidence, not a physical power-cut experiment.
Read-only production D1 found zero installation/client/product-event rows for the
fresh QA installation ID; actual consent and first-launch cloud confirmations are
false. [Isolation](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-resume-1a4bf99/production-isolation-after-resume.json).

Five real saved media items, including two playlist exports, have been moved
through the native current-account Windows picker twice. All9 owned files exist
at the second destination and their old paths are absent. Third move, hash/sibling
assessment, and affected open-Detail selection acceptance are still in progress.
No failed generic journey has been promoted or backfilled. Full release evidence
reconciliation and remaining native Watch layout observations remain open.


## Oct 11 01:53 UTC — final native move/rendering scope and Intel qualification

The signed5e581d0 Windows candidate completed three real native five-item
multiselect moves, including two canonical playlist exports. All9 owned-file
hashes remained unchanged; both intermediate owned paths disappeared, complete
playlist nests survived all three moves, and an unrelated foreign-folder sibling
remained intact. [21-check assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-final-5e581d0/standard-nest-multi-move-assessment.json).
A loose import then moved twice through a foreign nested location from its open
Detail: only its video moved, its open selection and saved note survived both
moves, and unrelated source/nested siblings remained unchanged.
[12-check affected acceptance](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-final-5e581d0/loose-selection-native-assessment.json).
Windows exited normally0 with no owned candidate processes or workers surviving.

The notarized ARM5e581d0 wide player shows More to Watch at right and Recently
Added below. Eleven passive native frame samples around one guarded Library tab
click show rendered content throughout the sampled transition; this is not a
subframe-flash or physical-trackpad claim.
[Bounded assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/mac-final-5e581d0-arm64-layout-attempt3/bounded-watch-tab-assessment.json).
Distinct four-owner artwork was observed in Library, Watch rail and Watch See All
grid, with13 checks passing and normal exit0/no survivors. Those four records are
explicit synthetic rendering fixtures with real media copies; they cannot count
as successful downloads or telemetry coverage.
[Artwork assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/mac-final-5e581d0-controlled-artwork/channel-artwork-assessment.json).
Both fresh Mac QA installation IDs have zero production installation/client/event
rows. The read-only query reports zero writes; QA first-launch/cloud confirmations
remainfalse. [D1 isolation](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/mac-new-qa-production-d1-isolation.json).

Exact notarized Intel5e581d0 failed the unchanged20s startup-attestation guard on
this ARM Mac through Rosetta. Original failure remains FAILED; no owned process
survived and no installation ID was persisted. Prior32.427s plugin diagnostic and
7.71s debug-plugin diagnostic are diagnostics only, not qualification.
A focused manual CI workflow now qualifies existing signed bytes on macos-15-intel
without rebuilding or rerunning export/regression suites. It verifies frozen
archive/executable/tree hashes, release signature/notarization/Gatekeeper, actual
native architecture, the existing20s launch guard, an independent onscreen owned
window and normal exit/no survivors. All telemetry is disabled. The existing
private draft receives a uniquely named QA archive, without replacing old assets
or publishing. Qualification is pending. No runtime source changed.

The popup-repair CI38101705123 currently has both Mac jobs and Ubuntu3.11 passed;
both Windows and Ubuntu3.13 remain running. Focused25 cases and lint/format retain
their passes. Full telemetry consent/update and formal release-receipt gaps remain
explicit; failed wrappers are not promoted or backfilled. No public release.


## Oct 11 02:04 UTC — Windows CI and private Intel access failure

Tests38101705123 finished with five platform jobs passed, including Windows
Python3.13 and its updater fault cases. Windows Python3.11 failed only
`test_pending_artwork_retains_only_the_same_owner[False-False]` at the probe's
unchanged12s subprocess deadline;695 other component cases passed,9 skipped.
The failure lacks the child output and does not establish a product rendering
assertion or a startup/cleanup cause. Original log remains retained. Focused
reproduction uses an isolated Python3.11 environment in the existing Genesis
QA tree, with the unchanged test/provider source; no new checkout.
[Original Windows failure](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/tests-8e7314d-windows311-failed.log).

Native Intel workflow38103306042 failed at private-draft download before any
candidate launch. Its read-only Actions token cannot see the draft. Original
failure remains retained and is not a product startup result. A proposed
job-only contents:write permission with disabled persisted checkout credentials
was blocked by automatic approval review as repository write authority beyond
recognized explicit approval. No rejected change was applied; mainfb33f79
remains clean/pushed. The explicit approval question is pending. No workaround
for the rejected permission boundary is used. All telemetry and Update/Repair
evidence limits recorded above remain open. No public release.

The exact original Windows artwork case passes in the isolated Genesis
Python3.11.0 environment at7.30s overall/6.23s call, with the unchanged12s
deadline. This does not establish the original CI cause (CI uses3.11.9).
The test now records bounded stage timings and an8s faulthandler snapshot into
a child log included on timeout/failure, instead of losing output in the
Windows subprocess communication failure. Existing rendering assertions and
12s deadline are unchanged. Four current cases pass in10.08s; the existing
clear-before-ready negative control still fails at the same-owner pending
assertion with its child diagnostics retained. Ruff/format/AST/YAML/diff pass.
The focused manual read-only Windows workflow runs these four cases and the
previously skipped3.11 scene/updater partitions; it does not repeat the passed
repository/component partitions or other OS jobs. Its CI result remains pending.
No runtime or signed archive changed.

## Oct 11 02:24 UTC — focused Windows CI and actual consent isolation

Read-only focused CI38104047004 on177adee passed4 artwork cases with the
unchanged12s subprocess deadline,207 scene cases/1skip and28 updater fault
cases/4skip. Original CI38101705123 remains FAILED at one artwork timeout;
five platform-job passes and695 other Windows3.11 component passes retain their
scope. The original timeout has no established cause. Child stage logs and
negative-control failure remain preserved. No runtime/signed archive changed;
no passed unaffected suite was repeated.
[Original focused CI log](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-ci-focused-177adee.log).

Exact signed5e581d0 Windows native consent proof passes24 bounded checks.
Actual Share analytics delivered2 startup/settings events to preview D1 only.
Actual Settings toggle withdrawal survived restart as Off. The scoped preview
installation/client/event dataset is identical after denied restart and after
globally disabled launch; production has0 rows for that installation. All3
attested launches normally exited0 with no owned survivors. Disabled-session
privacy wording is visually observed in the original screenshot; that static
Text is absent from the AX tree, so no AX-text assertion is claimed.
[Consent assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-consent-5e581d0/consent-isolation-assessment.json).

Supplemental launch attempts1/3 failed before app launch at QA API arity/Windows
UTF-8 reads; their original errors and native10 not-ready refusal remain intact.
Automatic approval review rejected a recursive evidence-folder copy as possibly
including credential state. Safer collection uses an explicit10-file allowlist
of original launch/cleanup/errors, excluding profile/credential/key files.
This is bounded consent proof, not a completed36-event journey or Update/Repair
telemetry proof. The previous Windows Update/Repair profile had no completed
media. A fresh bounded retention test stages the verified public0.2.5 installer
and exact final0.2.6 installer, preserves ordinary registration/shortcuts/data
before mutation, and uses the existing isolated profile's real completed media.
Its transactions and final ordinary restoration remain pending. Intel native
CI draft-token permission approval remains pending; no rejected permission
change or public release occurred.

## Oct 11 02:42 UTC — approved focused Intel draft access

The user approved the exact pending focused QA permission on Oct11 02:41:15UTC,
relayed with the original question and direct user reply by the parent task.
The earlier automatic approval rejection remains preserved. Apply only job-level
contents:write in the manual native Intel startup workflow, leave global token
permission read-only, and disable saved checkout credentials. No publication or
other write step is added. Source/archive/hash/startup20s/native architecture
checks remain unchanged. Native qualification on the existing signed archive
will be recorded separately; this permission change is not a passing startup.

## Oct 11 02:48 UTC — Intel native observer and Windows retention completion

Focused native Intel CI38106036141 successfully read the private draft and
verified the exact signed/notarized5e581d0 archive. Native x86_64 startup attested
in8.03s under the unchanged20s guard; the immediate single Quartz query returned
no owned onscreen windows and qualification FAILED. Cause is not established;
this is missing native visibility evidence, not a proven app startup failure.
Original6-file artifact/log preserved, forced cleanup left no owned survivors.
The observer now waits only until started+20s, independently requiring the exact
owner, layer0 and positive bounds; it records every sample and rechecks live
launch identity. It adds no new deadline, synthetic window or artifact change.
Eight focused cases pass, including delayed publication, wrong owner, invalid
geometry, expired original deadline, query finishing late and exited owner.
Ruff passes; initial format failure is corrected. Successor CI remains pending.
[Original Intel outcome](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/native-intel-ci-attempt2/startup-result.json).

Real Windows native public0.2.5→signed final0.2.6 Update and actual Repair both
return original helper statusrelaunched/installerexit0/data-preservedtrue and
exact final executable/signature. All13 media/sidecar files, including six real
media across standard playlist nests and the separately moved loose import,
and3 history/annotations/journal hashes match all4 before/after snapshots.
Actual updated/repaired Library shows All Media6. Fresh helper session nonces
are bound from original startup attestations after PID/path/hash/creation-time
checks; initial ad-hoc stale-nonce refusals remain failed, not app crashes.
Normal close exits0. Feed/descendants/task are gone; ordinary0.2.3 binary,27 data
file hashes, registration and shortcuts restored. Preview readback has linked
Update handoff/relaunched and Repair handoff/relaunched/repair_completed, one
installation/client and unchanged first-launch identity. Production has0 rows
for the QA IID. This is bounded native transaction proof, not a completed
36-event wrapper or formal release-gate pass.

Ad-hoc preparation originally omitted existing telemetry-off/handoff flags,
launching public baseline once in session0. Exact unplanned process was stopped;
only43 ordinary activity-log bytes changed, original prefix/hash verified and
restored. Production ordinary IID first launch remains August27/last seenOct5,
with0 events since this setup. Original setup and administrator-ACL refusal
retained. Downloads-only snapshot originally found5 of6 media; separate loose
folder added without moving or fabricating files. First binding helper collided
with automatic PowerShell Matches; original failure retained, task-only variable
renamed. One D1 full dataset response was column-truncated; it is retained but
not used as complete evidence. Supplemental structured columns preserve all33
actual updater/startup events without truncation. No runtime or signed archive
changed; no public release.

## Oct 11 02:59 UTC — native Intel passed and release evidence reconciled

Native Intel CI38106410614 passes using the unchanged signed/notarized5e581d0
archive, native x86_64/Rosettafalse. Startup checks7.067s and independently owned
onscreen window9.669s are inside the original20s deadline; normal exit0 and no
owned survivors. Earlier single-query CI failure and local Rosetta20s failures
remain unchanged. No runtime or archive change and no repeat qualification.
[Original Intel receipt](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/native-intel-ci-attempt3/startup-result.json).

Windows real public0.2.5→final0.2.6 Update/Repair assessment passes20 bounded
checks, including six existing real media,13 sidecar/media and3 state-file
hashes, actual Library6 after both transactions, linked preview D1 updater
receipts and production0. Cleanup normally exits0 and restores ordinary app/
registration/shortcuts/27 data hashes. Earlier setup/guard/readback failures
remain preserved. This closes the actual retention/linkage scope; it is not a
complete36-event/native preview journey or an installation version-transition
claim (the existing QA identity already had current version0.2.6).
[Original Windows assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/windows-retention-update-5e581d0/retention-assessment.json).

Read-only original-receipt reconciliation runs the unchanged maintained release
evaluator. It remains FAILED: the predecessor full NORMAL has separately fixed
telemetry failures, DEEP contains only the passed100-job soak, packaged Mac
smoke has no final immutable binding, source commits differ, and complete
exact-artifact preview-D1/native receipts for both platforms are absent. No
original status/source was changed, no synthetic observation appended, no gate
weakened and no unaffected valid check repeated. Its248 nonpassing requirements
include duplicated/missing scope and are not248 reproduced product bugs.
[Reconciliation](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/release-evidence-reconciliation.json).

Four qualified signed release files were copied to a task-local publication
folder and their source/destination SHA256 verified against the existing signed
manifest; checksums and public notes prepared. Read-only draft still has old
assets/target and temporaryQA archive. Nothing published or replaced. Remaining
work is exact release-evidence closure, draft asset/source replacement, removal
of temporaryQA archive, publication/public-byte/updater verification and website
manifest sync (website currently0.2.5).
[Prepared files](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/prepared-release-5e581d0/preparation-receipt.json).

## Oct 11 03:30 UTC — final Mac preview delivery completed; formal release dependency remains

Exact signed/notarized/stapled5e581d0 ARM archive7cd6df185c49c98648feb8a5a2d8fbee6982724b12c095111cc3b31f930b7d13
passes43 bounded checks in a fresh isolated profile. Unknown-consent preview rows
are0; actual native Share analytics creates one installation/client and one
app_opened. Normal same-version reopen adds the second app_opened, advances
last_seen and preserves installation/created/first-launch/version, with no
client_update. One actual native MP4 export delivers linked run_started,
media_exported,run_completed and processing-stage observations. Independent
probe and full decode pass (24.033s media, SHA2270c3db1c6736d4e831e17b3c365a31571deb3c79ea529274605f7cf310c30b).

Actual native analytics withdrawal, denied restart/navigation, and explicitly
disabled fourth launch retain identical complete scalar installation/client/
event projections. Disabled UI visibly says Usage analytics is disabled for
this session. All4 original launches exit0; no owned survivors/staging, archive
integrity retained and prior sessions unchanged. Preview has24 unique schema-v2
events; operation revision and all425 current bounded dimension fields validate
through5 original100-row SQL pages. Production readback has0 installation/client/
event rows for this Mac IID4d98dd07-53a3-4bbe-9179-dc17e0df48e3 and the retained
final Windows QA IID4fb91fc1-621e-486c-9a40-db8dfed42cba.

Limit: wide D1 JSON-string columns and the first200-row dimension response were
tool-truncated and rejected. Original readbacks retained. Historical privacy
comparison excludes truncated dimension strings; it does not claim full payload
or credential-secret equality. Separate current complete field pages validate
dimensions. Task relative-profile launch was correctly disabled/refused and
owned cleanup retained. Foreground/argument refusals sent no input; original
first refusal is in tool transcript because task filename allocation collided,
then allocator corrected. No layout/playback/move/installer test was repeated.

[Original bounded assessment](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/mac-final-5e581d0-preview-delivery-attempt2/bounded-preview-assessment.json).

No live operation is waiting. The concrete remaining publication dependency is
the unchanged mandatory release gate, not a Mac delivery transport failure or a
Windows sign-in requirement. RELEASE_GATE.md requires full FAST/NORMAL/DEEP,
interaction enrollment, exact final packaged receipts and both telemetry gates.
telemetry_release.py requires one complete final36-event journey per platform,
all215 feature/action pairs and a genuine same-identity old→new transition.
Current final QA readbacks cover7/215 Mac and20/215 Windows pairs; those counts
are scoped to those identities and do not invalidate historical bounded passes.
Original source wrappers remain failed/incomplete, and the current gate cannot
compose their independently passed partitions. Completing specifically missing
required observations or implementing/validating a reviewed linked-receipt
adoption policy is still necessary; no gate, source binding, original status or
trace was rewritten. Existing user authorization to release remains in force.

[Concrete dependency](/Users/coop/Documents/Codex/2026-10-09/task/release-completion-20261010/mac-final-5e581d0-preview-delivery-attempt2/telemetry-evidence-dependency.json).
Four signed files/checksums/notes remain prepared. Private draft/old assets/QA
asset unchanged and unpublished; website still0.2.5. Once eligible, replace
draft assets/source, remove QA archive, publish, verify public bytes/update feed
and synchronize website. No new runtime feature, checkout or worktree.


## Public-source refusal evaluator — 2026-10-11

The one previously absent DEEP public-W3C boundary probe now has retained raw
observations in the task's persistent evidence-workspaces directory. The first
launch refused because the configured workspace parent did not exist; its log
is preserved. The actual second worker run refused source selection with
no_video_stream / unsupported_format, no selectable video/audio formats, no
transfer, no published output or staging, and no owned survivors. Functional
acceptance passed, but the original interaction evaluator failed because its
bounded cause allowlist recognized network/extractor errors only. That original
failed interaction receipt remains unchanged.

The existing public-boundary evaluator now also recognizes this narrowly typed
first-party export_planning refusal. It still requires exact ordered ownership,
analysis stage, a positive format count, zero video/audio formats, clean files,
retired observer/children, and all previous refusal assertions. No runtime or
release gate changed. The new positive case failed before; 15 malformed cause
variants fail closed after. The existing public-boundary controls and new cases
pass together: 63 tests. Ruff, formatting and diff checks pass. The same original
raw bytes independently reevaluate to 11 passing assertions; no worker rerun or
original status/source rewriting was needed.

Evidence: task/release-completion-20261010/{gate-missing-public-boundary-attempt2,
public-no-video-before.log,public-no-video-after.log,
public-boundary-reassessment.json}. This closes only the bounded public generic
source refusal/cleanup gap, never provider support, successful public decoding,
complete DEEP profile, native usability or public release eligibility.


## 2026-10-11 — Exact-candidate evidence composition and four domain oracles

Added strictly linked profile composition. Original scenario objects, commits,
raw receipts and their failures remain immutable. All constituents require full
before/after source identities; product, dependency, packaging and workflow
inputs must exactly match the frozen 5e581d0 candidate. Only qualification/prose
changes may differ. Missing manifests, wrong candidates, source changes, absent
scenarios, duplicate selection, altered raw bytes and rewritten statuses refuse
adoption. This does not relabel a commit or qualify changed runtime bytes.

Three explicitly bounded source domains now capture admission/execution/final
source authority and independently evaluate complete required commands, JUnit
case outcomes, actual imports, collected Qt case rosters, twelve real local
diagnostic producers, delivery order and persisted payload equality. Sequential
command durations must fit the observed phase. Documented native/platform opt-in
exclusions remain visible and prove no interaction; unexpected skips and all-
skipped suites fail. Targeted Qt groups still require every case to execute.
These source domains have explicit contextual-UX nonapplicability and cannot
substitute for packaged/native acceptance.

The fourth oracle reevaluates exact packaged candidate/archive/bundle bytes,
ordered attested native events, decodable frames, hash-bound pipeline logs,
session time bounds, normal exits, media probe processes/payloads, restart bytes
and staging/owned-process cleanup. Seven contextual UX dimensions remain
required and bind to reviewed native frames; a separately hashed review may be
linked to the original journey hash, session nonce and candidate without editing
the original receipt. Raw pass flags do not satisfy these observations.

Validation: 196 focused evaluator/gate/import/native-report controls passed in
5.34 seconds; the final temporal assertion then passed all 50 aggregate controls
in 0.99 seconds. The temporal assertion initially rejected two synthetic positive
fixtures whose 1-second phase could not contain twelve 0.1-second commands. Only
those clearly synthetic fixture intervals were corrected; the impossible-time
negative remains. Earlier tests also exposed and closed reversed diagnostic
delivery ordering and timestamp-normalization mismatches. Ruff checks pass for
all harness sources/tests, formatting passes for 157 files, and diff whitespace
checks pass. Two preexisting harness import-order findings were corrected.

Evidence retained under task/release-completion-20261010:
harness-domains-final.{log,xml}, aggregate-timing-final.{log,xml},
aggregate-timing-corrected.{log,xml}, packaged-final-controls.{log,xml}.
Synthetic controls prove evaluator behavior only. No native full journey, D1
matrix or public release is claimed here. The prior 54 successful observations
and archived original failures remain unchanged. Signed application files were
not rebuilt or changed. Remaining acceptance is the missing source aggregate
observations and exact signed Mac/Windows telemetry journeys/readbacks, followed
by the unchanged fail-closed publication gate.


## Source qualification recovery — 2026-10-11

The e97f5e6 three-domain run retained its complete stable source manifests and
original failures under task/release-completion-20261010/source-domain-observations-e97f5e6.
The offscreen native-surface aggregate passes and will not be repeated. The repository
aggregate failed one stale report assertion that still demanded contextual UX for the
explicit source-only native-surface domain; the assertion now verifies that narrow
nonapplicability, while unknown owners retain their separate unproven tests. No timing
or command-success threshold changed.

The local diagnostic Worker exited before ready because Homebrew Node25 referenced
missing libsimdjson.29.dylib. The original loader error is retained at
task/release-completion-20261010/diagnostic-worker-startup-reproduction.json.
Installed Node24.21.0 runs successfully and will be selected in this test's PATH.
The harness now retains the actual pre-ready exit and delivered count instead of
trying an uninitialized snapshot callback; a real Python subprocess exiting7 proves
the original error is preserved, with no invented D1 success.

Exact-candidate composition now recognizes only the reviewed SHA256 bytes of the two
dispatch-only QA observation workflows. Changed bytes, symlinks, missing files and
build/runtime inputs still refuse adoption. These workflows download existing
candidates and cannot rebuild or publish them. All52 focused recovery controls pass
in1.96seconds; Ruff, five-file format checks and diff whitespace pass. Only the two
failed source domains require successor observations. Signed runtime5e581d0 and all
publication bytes remain unchanged; release is still unpublished.


## Oct 11 07:14 UTC — Windows restart passed; native applicability corrected

Windows exact signed5e581d0 normal quit/relaunch passes8 bounded checks: all19
history/output hashes remain identical, no staging, normal first exit, attested
same-artifact second launch, preview-only isolation and full Description geometry
before/after. Actual UI receipts108–124 retain the observations; no download or
move was repeated. Current same-version D1 continuity independently passes8
checks, using expected two app-open events from actual L1/L2 launches rather than
observed database totals. Privacy reuse recomputes18 bounded checks and verifies
all49 original Mac hashes; original cohorts, partial dimension limits and failed
full wrappers remain unchanged.

The release evaluator required player/controls_fallback on both platforms even
though its sole emitter is the legacy Tk Mac overlay: the owner returns before
creation on Windows and Qt's presentation slot does not admit it. The vocabulary
is unchanged. The evaluator omits only this demonstrably inapplicable action for
Windows and verified Qt Mac launches; unknown/unverified/mixed Mac renderers
retain the requirement. All other missing actions, event counts, privacy,
version-transition, artifact provenance and ordered native gates still fail
closed. Original applicability controls fail3/10 before; corrected telemetry and
release-gate controls pass55/55, including real owner behavior on both platforms.
An initial test fake lacked its dispatch callback; that failed receipt is retained
separately and the fake alone was corrected. Ruff/format/diff checks pass.

Read-only remaining matrix verifies215 tracked Python/QML product files byte for
byte against frozen5e581d0. Retained final-candidate native cohorts show24 applicable
pairs on Mac and41 on Windows;190 and173 native readbacks remain unproven. Counts
are a planning union across original cohorts, not a fabricated same-installation
full acceptance. One pair is inapplicable per platform. Twenty-seven legacy-only
literal candidates remain required pending actual owner/call-path review; string
absence never waives them. Existing bounded behavior passes remain closed.

Evidence: task/release-completion-20261010/final-gate-inputs-current/
native-remaining-matrix.{json,md}, native-telemetry-applicability-audit.json,
retained-privacy-reuse-assessment.json; windows-full-final-5e581d0/
restart-persistence-assessment.json and same-version-reopen-assessment.json;
native-applicability-before.{log,xml}, native-applicability-gate-final.{log,xml}
and native-applicability-gate-corrected.{log,xml}. Signed files are unchanged;
0.2.6 remains unpublished. No Mac foreground/input changes during the user's
live Kryden test. Current Windows owned app is26336, titleVFQ-da1dd493cdb9-L2.


## Oct 11 07:20 UTC — original Windows deadline finalized the session

Read-only guard diagnosis supersedes the last-known live PID26336 note above.
Original Windows wrapper finalized at07:12:31 after the two-hour overall deadline:
L1 exited normally0 and its bounded restart/Description proof remains passed;
L2 is timed_out, harness_forced_terminationtrue, exit1, unexpected_process_exitfalse
and zero owned survivors. The attempted new organization action125 was refused
before dispatch because driver_readyfalse/session_finalized; no media annotation
was changed and no additional native telemetry coverage is claimed. Original
session/e2e JSONs are preserved at windows-full-final-5e581d0/
session-final-after-deadline.json and e2e-result-original-finalized.json.

The compact native matrix and current continuation checkpoint are under task/
release-completion-20261010/final-gate-inputs-current/native-remaining-matrix.md
and task/release-completion-20261010/checkpoint-current.json. Twenty-seven legacy
producer mappings remain required pending source-owner review; none was waived
by absence of a Qt literal. No Mac foreground/input was changed during the user's
live Kryden work. No release publication, runtime changes or candidate rebuild.


## Oct 11 — Qt observation completion and Windows evidence portability

Implemented the 18 supported Qt observations from the source-owner review,
including actual folder-inspector admission, visible hover readiness, first relink
cancel request and Qt Help replacement. Seven distinct legacy Tk semantics are
excluded only by verified Qt launch attestations; shared reuse and Qt Help
replacement remain required. Unknown, unverified and mixed renderer controls retain
all legacy requirements. Universal schema/vocabulary and strict native gates remain
unchanged.

Broader invariant: observation follows an actual admitted or visible outcome,
retains original consent for delayed work, never changes a media operation on sink
failure, and never serializes private values. Representative cross-owner controls
use the real durable telemetry outbox and actual QML callbacks; denied/regranted,
stale-owner, hidden/not-ready, repeated request and actual cancellation cases are
covered. Before-fix failures and corrected fixture limitations are retained.

The three Windows CI failures at8117d58 were evidence portability defects: LF
translation in source logs and evaluation of recorded POSIX roots through Windows
Path rules. Preserve original log bytes and validate both path dialects; additional
negative controls keep absolute, drive-relative and traversing file keys rejected.
No stdout normalization or candidate/source binding waiver was introduced.

Validation:375 affected telemetry/privacy/Qt controls passed;683 affected
source/local-D1/presentation/evaluator controls passed;120 applicability controls
passed, with14 prior failures; the affected Watch wheel behavior control passed.
Lint, format and diff checks accompany the final patch. Detailed scope, ownership,
prior-failure proof and evidence paths:engineering-quality/
qt-telemetry-observation-review.md. QtHelpObservations owns only instrumentation;
ProductTelemetry owns consent/durable events; app.py gained no responsibility.
Legacy renderer behavior remains explicit deferred debt.

Runtime changed: one consolidated signed successor is required. Existing
behavior passes and original native evidence remain preserved; new source-tier
passes do not qualify signed native/preview-D1 evidence. Mac foreground and
production D1 were untouched.0.2.6 remains unpublished.


## Oct 11 — orientation fixture compatibility in the consolidated build

Consolidated build38123807665 stopped before producing the Mac archive on the
existing manual-orientation test; both Mac CI jobs38123792159 found the same
failure (724 other Qt component checks passed in each). The test replaced the
real QtAnalyticsSession with SimpleNamespace(settled=False) and omitted its
existing optional telemetry member, now observed by the Help instrumentation.
The actual owner always initializes telemetry, including disabled mode.

The test fake now includes telemetry=None. Its consent/modal assertions remain
unchanged; no product/runtime file changed. All23 orientation checks pass in the
focused module; Ruff/format/diff pass. Original failed CI and build logs are
retained under task/release-completion-20261010/build-ed66244-macos-arm64-failed.log
and ci-ed66244-macos{311,313}-failed.log; local proof is
qt-orientation-fixture-after.{log,xml}. Build continuation is justified by this
actual pre-packaging fixture failure, not by rechecking proven behavior. Native
Windows source has advanced in its existing checkout; no successor native input,
production D1 write, Mac foreground change or public release occurred.


## Oct 11 — battery-pause continuation and Intel finalization

Existing Intel Apple submission df4bdc91-7342-4011-aea0-1274662083da was
Accepted after the battery pause. Its app CDHash matches the original accepted
Apple ticket. No resigning, resubmission or rebuild occurred. Strict/deep
signature, stapler validation, Gatekeeper and isolated telemetry-disabled runtime
smoke pass. Final archive SHA256:
66694068b3f8ce15f757c96fa76f3af4c0e1fd3355100a1ec18cab858a73bfc4.
Frozen original clean5854619 candidate:
engineering-quality/candidates/mac-5854619-x64/20261011T125821Z-9715e7e3/candidate-artifact.json.
ARM and Windows candidate identities and all earlier behavior passes stay intact.

The original maintained continuation rejects the actual retained Mac vfq temp
root because it requires an obsolete .runs parent. Its unchanged original files
and failure are retained in task/release-completion-20261010/
short-workspace-resume-before.json. The real short-workspace producer regression
fails before; 15 ownership/evidence negative controls pass before.
The harness now accepts only the exact retained workspace receipt, canonical
non-symlink root and unchanged state layout, candidate, prior clean process exits,
trace provenance and screenshots. Legacy .runs sessions keep their prior guard.

A verified pause also must not advance the formal journey phase. The original
validator rejects 28 actual-shaped continuation observations solely because it
hardcodes process ordinals. The successor derives phase reuse only from ordered
retained continuation wrappers with exact hashes, unchanged prior launch records
and observation prefixes, and recursively valid prior provenance. Actual process
ordinals, PID/create time, window identity/token, executable/tree hashes, ordered
screenshots and disabled-telemetry attestation remain required. A fifth process
without a retained continuation remains rejected; no prior observation is
rewritten or duplicated. Incomplete pre-export state is not adopted as the
post-export restart baseline. Fixture continuation binds the original loopback
port and refuses an occupied port instead of changing saved URLs.

118 focused continuation/receipt/short-workspace checks pass, including changed
receipt hashes, launch/trace prefixes, nonce, live/failed/remaining processes,
phase, consent, symlinks and foreign/colliding fixture origins. Initial test
fixture/API and lint failures are preserved. Source changes are harness/tests
only; frozen product bytes remain5854619 and no new build is required.
Evidence: task/release-completion-20261010/continuation-tests-final-with-origin.log,
continuation-phases-before.json, signed-5854619/signing-result-x64.json,
signed-5854619/x64-notary-info-after-pause.json and candidate-freeze-x64.json.

No second cleanup proposal object was changed. The exact 106-object cleanup set
remains unapproved and untouched. No public0.2.6 release or production write.
Native continuation itself is still pending; Mac reports AC Power but13percent
and discharging, and the charger clarification is pending. Original Mac/Windows
QA profiles, partial wrappers and process-clean exits remain preserved.



## Oct 11 — frozen-candidate Windows continuation preflight

The first actual Windows continuation attempt exited before app launch.
Authenticode, publisher, timestamp and version checks passed; the inspector
rejected only because it compared frozen product5854619 to harness-onlya91f0a6.
Original preflight failure, failed launcher and zero-process readback are retained
under task/release-completion-20261010/windows-observations-ed66244/.

The maintained native runner now supplies only its verified frozen source binding.
Windows inspection requires embedded revision equality to that binding, Git
ancestry, and no committed, staged, dirty or untracked product/build input changes
outside engineering-quality. Direct archive inspection still requires current
HEAD; no candidate is relabeled, resigned, rebuilt or made from changed source.
Authenticode, runnable dependencies and exact frozen archive/executable/tree
checks remain unchanged. Resuming additionally matches the frozen source receipt.

The refused preflight preserved continuation-1 before stopping. A retry may reuse
it only when every original filename and byte matches, all entries and sources
are regular non-symlink files, and no extra object exists. It never overwrites an
archive or edits prior screenshots/traces/results. The before control fails with
FileExistsError; positive controls preserve all bytes and modification times.

100 focused continuation, artifact and existing provenance controls pass; the
actual Windows-kernel process test is correctly skipped on Mac and its prior
native pass remains intact. Two additional original-source-binding negative
controls pass. Real temporary Git fixtures reject product/build changes, dirty
or untracked inputs, foreign ancestry and invalid signed identity. Initial
platform-fake and sandbox loopback failures remain preserved separately; the
corrected focused run is continuation-preflight-tests-final.log. Lint, format and
diff checks pass. This patch contains only harness/tests/evidence-log changes.

Native continuation remains pending, not qualified by unit controls. Original
Windows session stays finalized, current_launch null, driver_ready false and
zero app/harness processes at13:29Z. Mac reports AC Power but11percent discharging;
heavy local work remains paused awaiting charger confirmation. The106-object
second cleanup set remains unapproved and untouched.0.2.6 remains unpublished.


## Oct 11 19:40 UTC — connected-host recovery: retained native environment blocked

Recovered actual shell, Mac CUA inventory and existing authorized Genesis SSH
access on canonical clean harness30ff582. SSH's initial sandbox socket refusal
was resolved with authorized execution; COOPS-PC\coop responds. No credentials,
access configuration or desktop permissions changed. Mac power improved from
10percent charging to12percent charging on AC; actual free space is83.54GiB.
No build, signing pass or valid test was repeated; the106 proposed cleanup objects
remain untouched.

Both maintained retained-session continuations failed before app launch. Mac
refuses its original isolated layout because protected temp root
`/private/var/folders/h3/mk90sh3d3r788x4r5stp5vwm0000gn/T/vfq-9r8eqfae`
is absent, including the profile and extracted candidate. Its saved inventory
contains hashes only; task preservation directories contain other source-run
roots, with no matching backup identified. No continuation directory was created
and no original receipt was rewritten or profile manufactured. The cause of the
missing directory is unknown; do not attribute it to cleanup or reboot without
further evidence.

Windows continuation-2 passes into fixture server setup but fails WinError10013
binding its retained127.0.0.1:63186 origin. Read-only netsh confirms63186 now lies
inside excluded TCP range63170–63269, with no listener. All original preflight
receipt hashes remain unchanged. Its original FAILED launch log and exit1
completion remain preserved. The first process diagnostic self-matched its own
cmd/PowerShell command text; the corrected executable-scoped query confirms no
owned app/Python harness. Its completed one-shot scheduled task remained Ready
and was removed after checking exit1 and nonrunning state; cleanup readback has
no remaining task. An intermediate diagnostic command had a shell quoting error
and did not execute. No port/reservation,
firewall or saved URL was changed.

Evidence: `build/recovery-20261011/recovery-status.json`,
`mac-continuation-launch.log`, `windows-continuation-2-launch-original.log`,
`windows-recovery-diagnostic.log`, `windows-owned-processes-final.json`,
`windows-completed-task-cleanup.json`.
Candidate5854619 and all earlier bounded passes retain their identity. Recovery
requires an intact original Mac workspace and an available original Windows
origin, or separately authorized fresh cohorts with explicit evidence limits.
Full native/preview-D1 and strict release gates remain incomplete;0.2.6 was not
published, production data was untouched, and no QA application remains open.

## Oct 11 20:04 UTC — authorized separate fresh cohorts executing

Parent explicitly authorized fresh cohorts after the preserved retained-environment
failures above. Reused frozen5854619 archives and harness30ff582 without rebuilding
or rerunning unaffected tests. Fresh Mac `mac-recovery-5854619-20261011` PID7574
has14/36 ordered native observations through real local MP4 conversion; network
MP4/MP3/Original-audio completed and actual playback observed. Windows
`E:\VODForgeQA\incoming\recovery-5854619-20261011` PID48376 has7/36 through
Library; first real MP4 completed, Description inspection active. Ordinary new
fixture ports50147/60795 bound without access/network changes. These new cohorts
do not repair, replace or relabel previous failed receipts.

Both new preview identities have actual zero-row unknown baselines followed by
one installation, one credential and one exact5854619 app_opened after native
opt-in; raw readbacks and snapshots retained in `build/recovery-20261011/` and
new cohort directories. Scoped production SELECT for both identities returned
zero installation/client/event rows, zero writes. An unnecessary account-list
connector request was rejected by automatic review; direct scoped D1 reads
succeeded without broader account access. CLI snapshot transport failed before
creating a snapshot; connector raw readbacks are retained as actual provenance.
Mac ordered player_features attempt was refused out of order and retained;
no event was backfilled. Current power22percent charging on AC,84GiBfree.
Native journeys/coverage remain in progress, not release acceptance. Updated
checkpoint preserves preceding blocked snapshot. No publication or cleanup.

## Oct 11 20:21 UTC — fresh native progress and announcement coverage blocker

Mac cohort reached23/36 maintained observations through real missing-media relink;
Windows reached14/36 through local MP4 conversion. Mac six preset exports complete,
queue removal/actual source skip and local failure/Stop observed. CPU fixtures are
bounded; power25percent charging. Native screenshots/driver traces retain actual
outcomes; these counts are not full feature-vocabulary or release acceptance.

The exact Mac package's eight-slide What's New tour ends with Done, observed in
`mac-recovery-5854619-20261011/029-029-announcement-final-done-only.png`.
Current unchanged product source `editorialFinishLabel` permits Try it only for
`did-you-know` or one `output-settings` slide; actual SHOWCASE_MODE is `whats-new`
and HIGHLIGHTS has eight slides. EditorialPopup passes true only for literal Try
it; `dismissEditorial` emits announcement/try_it only for true. The maintained
release evaluator nevertheless requires both announcement actions whenever mode
is not none. This is a concrete native reachability/gate mismatch requiring
resolution before release. No runtime/configuration/gate changes or false event
were made. Prior update evidence is not relabeled as new5854619 delivery.

Mac query-suffixed custom fixture ID `normal?preset=custom-1` was correctly refused
by missing-media redownload's safe ID syntax; the real moved file successfully
relinked with identical SHA256. That observation proves relink only, not redownload.
The fixture move and hashes are `build/recovery-20261011/mac-missing-media-fixture.json`.
A larger connector response was internally truncated and is preserved as partial;
its events must not be treated as a complete snapshot. Small scoped count readback
succeeded; final datasets require bounded pagination. Production writes remain0.

## Oct 11 20:36 UTC — concrete announcement applicability analysis

Delegated follow-up requested evidence/recommendation before correction. Exact
candidate source hashes for five relevant producer/UI/vocabulary files match the
frozen manifest (`build/recovery-20261011/announcement-source-binding.json`).
Written TELEMETRY_RELEASE_GATE requirement279 says Try it when enabled for the
candidate. Both Qt and legacy owners expose it only for Did You Know or one
output-settings slide; frozen5854619 has eight What's New slides and native Done.
No legitimate profile/fixture switch enables the other compiled configuration.
This proves a harness applicability mismatch, not missing product telemetry.

Read-only synthetic gate probe uses existing fixture and removes only try_it,
updating its count/privacy copies: baseline accepts; resulting sole rejection is
missing announcement/try_it. Native records are not fabricated from that probe.
Existing enabled-mode test synthesizes all vocabulary actions and removes the
whole announcement feature, missing per-action reachability. Existing Qt owner
coverage monkeypatches Did You Know rather than the shipped configuration.
Concrete proposal and bounded rejection/negative-control matrix are in
`build/recovery-20261011/announcement-correction-analysis.md`. No implementation,
gate bypass, product edit or rebuild. Recommendation is a source-bound harness
applicability correction retaining shown, required Try it modes, impossible-action
rejections and every unrelated gate. Parent asked for analysis first.

Mac24/36 through bounded announcement/guidance/appearance observation; receipt
explicitly excludes try_it. Bounded D1 pages preserve349Mac/151Windows unique rows
through rowids8228/8226, all SELECT writes0; assembled snapshots are watermark
progress, not events_complete or a passed journey. Windows original retry fixture
64799 had no listener and is now excluded64743–64842; both connection-refused
attempts remain. Same-port recovery bind failed10013 without access changes.
Separate loopback18089 attached SSH fixture produced six actual503 responses;
native Retry Same settings after source-ready is now being checked. No Windows
reservation/firewall change. Power32percent charging,84GiBfree at20:27.

At20:37 Windows actual stable-fixture Retry completes and maintained observation16
is recorded (`windows-fresh/076-stable-retry-complete-record.json`); earlier
connection-refused and six503 attempts preserved. Both native cohorts remain
alive for the requested bounded-path decision (Mac7574,Windows48376); first-launch
QA deadlines approximately21:42/21:43UTC. Checkpoint contains session IDs and next
ordered actions; do not allow timeout or invent missing observations. Latest
scoped production read for both new IDs is0installations/0clients/0events and0writes
(`production-new-cohorts-2037-raw.json`). Power36percent charging. Remaining full
native/D1/Update/Repair/privacy gates still open;0.2.6 unpublished.

## Oct 11 20:47 UTC — authorized bounded announcement harness correction

Applied only harness/docs/tests after delegated authorization. Applicability reads
canonical editorial AST without executing candidate source and verifies five
producer/UI/vocabulary files against the frozen candidate manifest, candidate
source identity and verified known renderer. Done remains distinct; shown remains
required for enabled modes, true Try it modes retain their action, impossible
announcement events fail, and missing/changed/unverified evidence grants no
exclusion. Full release checks pass the actual candidate into this evaluator.
No runtime files, enum, event producers or signed artifacts changed.

Focused affected suite140passes (`announcement-harness-final.log`), including20
new bounded configuration/binding/real-owner cases; earlier120case intermediate
pass and140casefirstmatrix pass retained. Final test edit specifically strengthened
valid-manifest/wrong-file and missing-producer rejections, justifying the final
rerun. Ruff/format/diff pass after import-only formatting. Earlier native Done,
source hashes and sole-error prior gate probe retained. Exact5854619 manifest plus
actual Mac launch returns only shown in `announcement-exact-candidate-decision.json`;
this is applicability proof, not a passed native/full-release receipt. Bug-class
learning and why previous vocabulary-generated fixtures missed reachability are
in README and TELEMETRY_RELEASE_GATE.

Mac main QA was normally closed for separate updater work because maintained
launcher forbids another VODForge process. Original partial wrapper retained:
24/36 ordered, process provenance/artifact integrity passed,12independently readable
media, PID7574exit0/no survivors. Its original temp root/profile remains intact.
New separate signed QA0.2.2 baseline (not public compatibility proof) PID12341 is
preview-only with actual zero installation/client/event baseline and explicit UI
opt-in, serving exact5854619 archive via guarded loopback feed. First feed bind
was sandbox-denied before start; separate authorized feed now running. No OS
permissions or signature rules changed. Current Windows main17/36 remains alive.

## Oct 11 21:00 UTC — exact Mac Update/Repair and reconnect binding blocker

Harness-only correction committed459f578;140 focused checks and Ruff/format/diff
passed; runtime/candidate5854619 unchanged and no rebuild. Exact Mac native Update
and Repair original helper receipts both report relaunched, repairfalse/true and
executableb0fa25357b0fd30299e77788b385952abad7aa89ec4885670721e7b8d094d668.
Same isolated preview installationbec1e027-2189-4c49-8cb0-6c453d977c3b has exactly
one0.2.2→0.2.6 transition, explicit Later, controlled503 check failure and linked
repair_completed attempt55318635-e862-4969-98f3-e9f9de2dd2c7. All four history,
media, metadata and thumbnail hashes preserved across both transactions; final
independent media decode exits0. Bounded pass is
`build/recovery-20261011/native-update-repair-proof.json`; original generic baseline
wrapper remains failed/incomplete. Signed QA0.2.2 is not public compatibility proof.

After20:53 reconnect callback, actual shell works,44percent charging on AC/82GiBfree
at20:55. Original main Mac process7574 already normally exited0 with24/36; retained
profile remains resumable. Repaired helper app12930 is live, exact archive/executable
and preview-only attestation bound by Quartz window786 and its actual screenshot.
CUA instead returns plain VODForge/29 ordinary runs, different geometry/content,
even after exact-path rebinding and JS reset; macOS window-ID selection unsupported.
No clicks/keys sent to that mismatched UI. Actual local process enumeration finds
only QA12930 and its child12931, so the native-control surface mismatch is unresolved;
do not infer it is the current executor desktop. Clean final repair shutdown not
claimed. Terminal screenshot/attestation receipt remains authoritative bounded data.

Windows authorized SSH and guarded native controller remain working. Six actual
native preset exports complete; durable history has validated Everyday, Streaming,
Editing, Sharing, CTV and Custom profiles. Custom is CBR10000k/AAC320k/medium CPU,
not NVIDIA acceptance. Maintained observation18 recorded at
`windows-fresh/111-presets-record.json`; actual PID48376 remains alive with
approximately21:43UTC deadline. Remaining ordered19–36 and full feature vocabulary,
NVIDIA, Windows Update/Repair, restart/privacy and complete D1 gates remain open.
Latest scoped production SELECT for both main QA IDs plus the updater QA ID is
zero installations/clients/events, writes0 in production-three-cohorts-2107-raw.json.
No publication, production mutation, everyday app replacement or obsolete-object
deletion. Checkpoint preserves actual live ownership and native-control blocker.

The2107/2110 suffixes on the newest readback/checkpoint files are labels, not
observation timestamps; actual tool clock at checkpoint completion was21:00:26UTC.
Use embedded recorded_at/updated_at and tool results for time provenance.

## Oct 11 21:26 UTC — Windows continuation and updater baseline

Windows main added actual six-preset, native queue removal/Skip, local validation
failure/Stop, organization and bounded player controls; ordered22/36. Native
organization owner readback has category Recovery QA, qa-recovery tag, fictional
private note and edited noncanonical description. Initial wrong-file history
readback was empty; canonical library-annotations.json readback verifies actual
owner run373aea9ced3449a5a520d37c8dfdabea. Source sentinel item unchanged.
167 newly read preview rows after8226 through8462 join prior151 to318 unique events,
all SELECT writes0; not events_complete. Earlier rows were not reread.

Preserved failures: unstarted invalid URL-list fixture corrected before launch;
category151 occlusion guard refused, fresh152 screenshot and unchanged guarded153
succeeded; hidden back10 and already-retired floating target refused. Escape from
fullscreen returned directly inline. Initial same-byte media rename was denied by
Windows because player retained an open handle; no bytes moved. Subsequent176
Play was ordinary existing-file playback, not missing-file proof;177/178 targets
were absent/refused. No missing-media observation recorded yet.

Main Windows normal Alt-F4 receipt179 reports exit0 at21:23:49. Partial maintained
wrapper completed21:24:13:22/36 ordered, artifact/provenance passed,12media probes,
zero staging,zero owned survivors; missing23–36 remain, original failed status kept.
Temp/profileE:\SystemCache\Temp\Coop\vfq-7z_z88p5 remains for maintained continuation.
E:19.71GiB is below20GiB extraction reserve; no new extraction on E. C:75GiB allowed
separate retained signed public0.2.5 archive preparation at
C:\Users\Coop\AppData\Local\Temp\VODForgeQA-update-5854619-20261011.
Expected executable0AA2E2DD.../valid Authenticode/version0.2.5 verified, source archive
EE179E09... retained. Existing bounded updater worker copied with only scope/hash
substitutions and PowerShell syntax check; long encoded upload refused before write,
readback confirmed none staged, authorized SCP succeeded. Ordinary registration,
shortcuts and27ordinary data file hashes backed up by existing preserve workflow.
Loopback feed59609 advertises exact585 installer923bcb4f...; no install yet.
Baseline PID50560 now preview-only, IID2eb1d877-ac4b-4e7a-a840-032b0c86e5bf, actual
unknown0rows before native Share analytics. Actual updater/native proof still pending.

Mac exact-PID focus succeeds and confirms12930 already foreground, but CUA still
returns unrelated plain29-run window. Exact-path bind, reset and supported focus
have not restored controller target; no click/key sent to mismatched window.
Mac main paused24/36; repaired helper app12930 remains alive. Power57percent charging.
No new runtime/build/test rerun/publication/deletion/production mutation.

## Oct 11 21:30 UTC — user-requested model handoff and audit pause

User requested immediate pause of test/harness expansion for a change-impact audit,
then end this turn so the parent can resume on GPT-6.1 Sol medium. Current model
identifier is not exposed to this session; no model identity claim. No new tests,
builds, publication or deletion for this handoff. Canonical checkpoint saved with
prior checkpoint preserved and local model-handoff-checkpoint.json copy.
Windows main remains normally closed exit0 at22/36. Separate public0.2.5 updater
baseline import006 failed a clipboard operation; no successful import claimed.
Normal close007 reports closed=true/exit_code0; receipt retains initial
process_exited=false field, so no independent zero-survivor claim for that baseline.
No Windows update/Repair installer was executed. Mac repaired QA12930 and child12931
remain alive because CUA is bound to the wrong window; no unsafe input sent.
Loopback feed helpers may remain. Power61% charging on AC. Next work is factual
shipped0.2.5-to5854619 change-impact audit, not another full journey or new test run.

## Oct 11 — change-impact audit and read-only continuation planning

User requested an actual impact audit before more QA, then authorized demonstrated
harness corrections. Read the retained signed public Windows0.2.5 bundle revision:
850e19e6699c7bbd047d6be43851309bfe7d53fb. Candidate5854619 has eight product
commits/28 app files since that baseline;585 itself only fixes a test fake.
Audit/source inventory saved under build/recovery-20261011/change-impact-audit.md
and change-impact-source-inventory.json. The redesign already shipped in0.2.5.
New behavior is interrupted-run/batch recovery, six focused follow-ups and18 Qt
observation callbacks. Existing scoped behavior/build/signature passes remain
valid; audit distinguishes remaining risk from profile/port/test/control failures.
Windows updater baseline50560 independently absent on read-only SSH process query.
No new native journey, product build, production mutation or deletion for audit.

Demonstrated harness usability defect: inspecting resumability through the prior
loader archives continuation evidence, and normal runner requires launch access
before exposing retained coverage. Added --plan-only using the same source/archive,
artifact, owner-clean-exit and trace guards, returning before preservation/mutation.
It reports retained observations and only the remainder, original receipt hashes,
next observation and explicit not-release-acceptance/not-launch-readiness limits.
It neither combines older sources nor waives any existing release requirement.
Four new controls exercise unchanged original bytes/no archive and fail-closed
changed candidate/invalid trace/live owner;12 affected existing loader controls
remain passing (16 total,0.25s). Ruff/format/diff pass. Actual retained Mac24/36
read-only plan succeeds with12 missing; all six original receipt/log SHA and
mtime_ns identical before/after. Receipt:mac-read-only-continuation-plan.json.
No product input changed; no signed rebuild needed. Full release evaluator's
cross-receipt composition remains unresolved; do not hide this limitation.

## Oct 11 — scoped native receipt composition and owned QA closure

User authorized fixing the demonstrated whole-wrapper reuse defect after the
impact audit. Added native-compose with immutable receipt/session/trace references,
exact candidate/source/archive/tree/platform, live-recorded executable/attestation
ownership, original frame SHA, owned process time interval, clean exits and
staging guards. Independent presentation scope composes; export, queue/cancel
and restart chains stay within an original session. Consent/readback identities
stay per cohort. Original failed wrappers and raw files retain status/bytes/time.
The release evaluator recognizes recomputed aggregate native coverage and still
requires a designated independently qualified core pipeline/media/restart/cleanup
receipt. It does not mark either current partial dataset release eligible. Separate
full preview-D1 checks remain required; no thresholds or source bindings waived.

Actual Mac composition revalidates24 observations plus separate original helper
Update/Repair transactions. Helpers/attestations/frames/durable hashes are reread
by their original SHA; updater IID is never merged into main counts/privacy and
original clean-exit/public-baseline limits remain visible. Mac349-event/54-action
inventory retains watermark8228, but original pages omit rowid/query bounds;
watermark binding remains unproven, no complete/privacy checkpoint invented.
Actual Genesis evaluator accepts22 observations with three original receipt SHA
and mtime unchanged. Its first import lacked checkout root; original refusal kept.
A repeated archive verification exceeded SSH45s: no result/process survived, no
native QA launched. Successor reuses the original hash-bound successful frozen
candidate receipt rather than repeating signature/archive checks. Consent files
were originally retained on Mac; byte-identical copies were supplied separately.
The installed C:\Python313 runtime lacked psutil, exposed by an unnecessary
telemetry-module import for two target constants. Moved those unchanged constants
to a tiny shared harness-only telemetry_target module; no dependency installed.
Actual Windows paged inventory reassembles318 events/30 pairs through8462 with
original offset/total/range checks; rowid boundary remains unproven.

Focused composition/rejection controls39pass. Existing release-gate module had
12pass/1fail; the failure reproduced using pre-composition HEAD gate code because
its synthetic candidate omitted the earlier announcement producer manifest.
Adding the existing telemetry fixture's binding preserves its temporal/debt
assertions; only that case reran and passes. Two affected target-isolation contracts
pass.54 focused passes total across these nonrepeated runs, not a broad suite.
Ruff/format/diff pass. Earlier16 continuation-plan controls remain valid.
Evidence:build/recovery-20261011/{native-composition-final.log,
native-composition-release-gate-compat.log,
native-composition-preexisting-gate-failure-control.log,
native-composition-gate-fixture-corrected.log,composition-target-contracts.log,
mac-native-composition-result.json,windows-native-composition-result.json,
windows-composed-page-inventory.json,composition-final-actual-revalidation.json}.
The actual Mac aggregate still fails the release gate on its missing native scopes.

Mac12930 normal Command-Q dispatched only after exact create-time/executable SHA,
original attestation SHA, Quartz786/PID/title and AX foreground guards. Initial
keyword-only API misuse refused with0dispatches and is preserved. Root gone;
child12931 remained as an orphan. Bounded read found a second native application
from the same QA executable with plain VODForge window787 (also Window819),
not merely an external-controller hypothesis. Exact PID/create-time/source checks
then requested normal NSRunningApplication termination. Follow-up ps finds neither
PID. No exit0 claim without an owned wait handle; separate normal-close receipts
are successors, original updater proof limits/status/hash are not edited. No CUA
input or unrelated app action. The ambiguous same-path instances are local evidence;
which CUA instance was chosen remains unproved. Future input must use exact owner/
nonce-window guards. A new ordinary-profile hash comparison has no current matching
baseline here, so ordinary-profile immutability is not newly claimed by this closure.
Mac feed session87216 closed with KeyboardInterrupt130; verified Windows private
feed task/process removed, no ordinary installer/profile/registration change.
Power74% charging. No app rebuild, broad journey, D1 request/write, publication,
obsolete-object deletion, new credentials or access change. Smallest remaining
work is linked receipt/readback closure, missing changed recovery/UI evidence,
queue/restart/privacy scopes and final updater linkage; do not replay24/22 prefixes.

Preview receipt integration now accepts the independently recomputed native
aggregate for only its native UI/full-journey predicate. Existing main-installation
D1 count, consent, event-schema, watermark/snapshot and update-transition checks
remain required; no events or identities are merged. Four focused adapter cases
pass: qualified native composition, archive mismatch, real denied-data mutation
and malformed composition. Only affected adapter cases reran after the added
malformed-input guard.58 unique focused passes across composition/gate/target/
adapter scopes; no broad run. Corrected a test-only import order finding; final
Ruff/format/diff pass. Later user reply "fix the event then" addresses the earlier
announcement question; candidate-bound correction459f578 already resolves that
mismatch, retains shown and true Try it configurations, with140 retained passes.
No need to fabricate Try it on Done or rebuild unchanged candidate5854619.
Parent supplied actual original user release authorization dated2026-10-10T22:09;
publication remains conditional on genuine final readiness, with missing gates open.

## Oct 11 — separate optional UX review from release acceptance

User authorized retaining useful checks and retiring unfinished scoring that
obstructs release (22:17:37 UTC). Targeted source search found no click-distance
calculator or screen-distance score consumed by release_gate; this does not
prove no adjacent mapping document exists. The actual related blocker was every
scenario's seven-dimension usability enrollment (orientation/navigation, action
hierarchy, progressive disclosure, visual hierarchy, sparse/busy content,
feedback, accessibility). Made only these `.usability.*` reviews nonrequired;
original status/evidence remain visible and explicitly labelled optional.
Interaction/temporal assertions remain required, as do scenario results, native
package provenance/media, updater/data preservation, telemetry and privacy.
Aggregate counts were already reporting-only, not the publication decision.

Two focused positive/negative controls prove failed/unproven UX mapping cannot
block a required pass and cannot mask an actual HTTP404-cleanup interaction
failure. Both pass. Legacy fixture still blocks missing temporal assertions and
now excludes optional UX from blockers (one pass). Three existing required-
evidence/privacy/package-provenance controls pass. Six unique affected checks;
Ruff/format/diff pass. Initial two new tests incorrectly expected an optional-only
checkset to pass; gate correctly says unproven when no required checks exist.
Corrected tests include a required pass; original failed test log preserved.
No product files, candidate bytes, source test matrix, telemetry completeness
policy, or safety thresholds changed. No rebuild/publication/deletion.

Charging-only assertion is in ignored recovery resume-mac.py, not an explicit
user hold: `assert 'AC Power' in power and ' charging;' in power, power`.
Successive bounded reads remain82% with AC/discharging and7h20–8h estimated
battery time. Earlier user concern was10% discharging and heavy work, not a
permanent charging-only native QA requirement. Bounded native checks can use
current high stable charge; heavy work remains excluded by original no-build
scope. Do not alter space or explicit low-battery safeguards.

## Oct 11 — Qt retirement branch: neutral service extraction

Explicit user requested full Tk retirement and one checkout/ordinary branches.
Created qt-retirement from47767dd in canonical checkout; frozen5854619 artifacts
remain untouched and independent reviewer owns both GUI desktops. No build.
Extracted shared worker/media/diagnostic helpers into download_service; neutral
worker_events, product_theme, visual_chrome/materials, button_metrics and recovery
prompt replace Qt imports of legacy app/UI modules. Qt worker, metadata, artwork
and local conversion now use neutral owners; headless pipeline uses the same core.
AST receipt records212 unchanged original top-level definitions (including the
worker), with only debug_preflight/runtime_smoke tool-locator references changed
from inherited DownloaderApp to DownloadWorkerCore. This is bounded provenance,
not a universal behavior claim. Existing data formats and worker implementations
are unchanged. Shared test imports migrated with their owner.

Original blocked-import control fails at legacy app.py importing tkinter; after
extraction actual Qt module loads with tkinter/PIL.ImageTk rejected, legacy app
absent from sys.modules. Permanent subprocess import regression1pass. Existing
metadata/batch-outcome/Qt-worker controls24pass in1.27s. Initial system-Python
attempt lacked Pillow and was invalid; retained; valid venv prior failure retained.
No GUI created. This is the first incremental source commit, not full retirement:
legacy files/tests, entry/build defaults, Tk-only dependencies and workflow paths
still require inventoried removal or functional migration. Do not call complete.

## Oct 11 — Qt retirement branch: ordinary Qt entry/build defaults

main.py now starts the existing Qt application; qt_main.py remains an explicit
Qt alias. Both platform build scripts require/default to qt, include QML/Qt
Multimedia and exclude tkinter/PIL.ImageTk/vlc. Removed Tk presence prerequisite
and unreachable legacy libVLC bundling branch. macOS dependency installation and
release workflow no longer request python-tk or libVLC; ordinary macOS runtime
probe uses neutral service and Qt dependency scope. README/stale entry comments
updated. This changes future source/build paths only; no build or frozen artifact
mutation. Prior shared-service worker/data behavior remains unchanged.

Exact ordinary/explicit entry imports with Tk unavailable1pass. Bash syntax
passes. Windows PowerShell parser reports0errors via existing authorized SSH,
parsing source only (no build/app execution). First encoded parser command exceeded
Windows argument limit before parsing; stdin transport passed, no remote files
created. Ruff/diff pass. Legacy app/widget source and obsolete test/workflow paths
still remain pending inventory/removal; full retirement is not complete yet.

## Oct 11 — Qt retirement: remove widget entry and migrate useful copy/service controls

Replaced legacy app.py widget owner with Qt/non-GUI command dispatch; preserved
artwork worker and debug-preflight commands. Shared worker test factories now live
in tests/worker_fixtures instead of importing a mixed UI test module. Migrated
metadata/helper consumers and neutral security/reliability/pipeline imports.
Metadata303 service/data controls pass (299 first; four retained import-string
failures corrected and pass). Fifteen old widget-specific metadata cases are
retired against Qt owner controls; seven selected current Qt counterparts pass.
They cover close/pending preferences, blocked artwork retirement/cache, stable
run selection, retry settings and tooltip bounds. No wholesale mixed file removed.
Remaining consumer collection initially found421cases plus old copy-fixture import
failure; that copy module is now ported, not erased.

Preserved source-tags/original-description/thumbnail-URL copy capabilities in Qt
Source Details through an existing shared popup/control route. Existing personal
copy controls retain their behavior. Neutral library_text reads canonical owner
records, not display placeholders. Fourteen actual Qt handler controls pass,
including unknown/empty owner, explicit owner identity and real private-outbox
consent/no-private-content controls with injected transports. No real clipboard,
production telemetry or GUI input. Offscreen existing copy/QML integration1pass
(no native foreground); first compile rejected unsupported tooltipText property,
removed it and retained original failure. Source/default command dispatch26pass
with one old mixed fixture import failure; after neutral fixture extraction that
case passes separately. No frozen artifact/build/release modification.

Full Tk retirement remains in progress: remaining widget/mixin consumers, pure
history/data equivalents, obsolete source/workflows and dependencies still need
migration/removal. Inventory based only on direct class methods undercounts mixin
consumers; don't treat its “pure” grouping as a proof. Current source is a separate
successor change and is not packaged verification of5854619.

## Qt retirement — neutral Library history and preserved data/privacy controls

Extracted ledger load/deferred settlement/publication from widget hosts into
LibraryHistory and migrated actual diagnostic, journal ordering and publication
regressions. Qt runtime uses the same owner for startup and successful publication;
its existing job identity, file transaction reconciliation and data schemas stay.
Publication updates the cached projection only after save_history succeeds.

This uncovered a source Qt startup gap: damaged main/unsupported schema/pending
ledgers raised out of the runtime constructor. Three actual temporary-file controls
fail before, pass after neutral load; existing bytes remain unchanged and new work
is refused with nonprivate recovery copy. App availability is source-tested; no
frozen5854619 native corrupt-profile claim or byte change is made.

Retained tests: diagnostic/private outbox38passes (37 first, one old patch namespace
fixed); publication6passes (5 first, one erroneous positive-case raises assertion
corrected); pending journal19passes; Qt startup/normal-admission5 and existing
write-preservation6 pass together; two owned batch publication/checkpoint controls
pass. Original failure logs retained. All tests source-only; no foreground GUI,
credentials, production transport or candidate/release mutation. Ruff/diff pass.
Remaining source/mixin/test consumers still require retirement; not complete.

## Oct 12 — explicit announcement event correction

User answered “fix the event then”. Successor What's New final action now says
Try it and follows the existing acknowledged(true) route to Settings. That explicit
action emits announcement/try_it once; close/dismiss still emits none. No synthetic
Done acknowledgement, backfilled event or frozen5854619 mutation. Actual Bridge
regression failed before at Done; all24 maintained orientation checks pass after
(announcement-event-before.log/announcement-event-after.log under recovery-20261011).
This is source/offscreen proof; successor packaged UI/preview evidence remains
untested and requires the separately constrained build/retention workflow.

## Oct 12 — remove HeyCatch desktop transport

Explicit user requested removal from VODForge and site; separate owner handles
canonical website. Removed app capture implementation and both injected secondary
transport APIs. Product events retire only on genuine first-party acknowledgement;
first-launch/session and first-party browser campaign claim routes remain. No
remote account, credentials, production data/schema or frozen585 bytes changed.
Legacy installation acknowledgement stays inert for file compatibility; legacy
queued secondary acknowledgement is ignored and cannot replace first-party receipt.
No ordinary profile or stored service data accessed/migrated/deleted.

Existing affected checks139pass;21 failures are retired widget/app imports in the
mixed telemetry-features suite (named in heycatch-focused-final.log), not asserted
passes. Original11 obsolete secondary-contract failures were ported to first-party
retry/acknowledgement/claim controls, preserving consent and private payload checks.
Two new actual legacy-outbox read/retry cases pass (heycatch-legacy-queue.log).
Ruff focused source/owner tests passes. Frozen package/new native delivery remains
untested for this successor. No rebuild/publication. App now has no active HeyCatch
transport; historical QA documents/deny-list domains and inert installation fields
are deliberately historical/compatibility data, not enabled integrations.

## Oct 12 — retire widget implementation and retain neutral data consumers

Version-remove54 obsolete widget/platform presentation source files and legacy
Tk previews/probes. Qt's existing scenes, worker core, typed events and neutral
history/prompt/material owners remain. Removed Tk-only platform helpers and font
aliases; generic presentation observations stay. Pure local-conversion recovery,
sidecar publication, output observations, event constructors, history and platform
controls were retained from mixed files. Removed widget-owned cases only; named
per-definition disposition receipts are under recovery-20261011 (mixed-widget,
nested-widget, retired-widget-fixture and legacy-widget-test disposition JSON).
Git preserves retired implementation; no generated binary/object cleanup performed.

Full collection6994cases, zero errors (retirement-full-collection.log). Actual
retained data controls188pass in1.21s (retirement-retained-controls-after.log).
First attempt242passed/29failed on additional dynamic legacy imports; failures
retained and retired against their widget owner, not relabeled as passes. Remaining
Qt entry, diagnostic selector and immutable packaged-receipt import controls6pass
in1.18s (retirement-entry-contracts.log). Current modified Python Ruff/format and
diff checks pass. Tk/PIL.ImageTk source import inventory empty. No foreground GUI,
new package, frozen artifact mutation, production write, secret/profile read.

This is an incremental retirement checkpoint, NOT completion or release acceptance.
Residual old EQH scene/recovery selectors and dynamic synthetic Tk producer calls
still need migration/reconciliation; zero collection errors does not execute them.
Some legacy source-bound tests need current-owner selectors. Native successor and
new package/update/privacy qualification remain untested; retained frozen585 proof
cannot qualify source changes. Existing actual Qt counterparts include runtime event
identity/batch publication/restart, scene annotation ownership, queue generation,
metadata ownership, copy private-outbox, playback/frame and interaction invariants.
No blanket skip, fake DownloaderApp or fabricated native event is introduced.

## Oct 12 — close lazy Tk presentation adapter and neutral batch probe

Follow-up indentation-aware source scan found the lazy PresentationProbe TclError
import, missed by the earlier top-level-only inventory. Removed that unused widget
adapter and canvas_snapshot; current QtPresentationProbe still consumes unchanged
PresentationObservations. Ten maintained bounded observation/privacy controls pass
(retirement-presentation-owner-after.log). Initial command named a nonexistent
batch test file and executed no tests; retained, not counted.

Migrated existing batch-report refusal probe and original-audio script to actual
DownloadWorkerCore, with settings constructors from models. Direct bounded probe
passes: zero media worker calls after reset refusal, old report preserved, clear
error emitted; console evidence in this task (temporary raw fixture removed after
run, no lasting native receipt claimed). Ruff/format/diff pass. Actual source scan
including nested imports now has no Tk imports. Remaining EQH dynamic legacy calls
and selectors are still explicitly pending; no build or release qualification.

## Oct 12 — restore announcement product semantics after focused review

Parent explicitly requested no manufactured product behavior for an old harness
expectation. Current eight-slide tour ends with folder/download fixes, not a
settings task. e1ff771's general Try it label/settings navigation was harness-
motivated, not a demonstrated user-facing requirement; restore Done for that tour.
Existing did-you-know/single output-settings Try it remains an actual settings
intent, records once only on explicit activation; dismissal records no such event.
Twenty-five orientation checks pass (announcement-product-semantics.log). e1ff771
and its original checks remain historical Git/log evidence, not successor product
requirements. Frozen585 is untouched; its candidate-bound producer applicability
correction459f578 remains separate from this source/product decision. No fabricated
Done event, schema/data change, gate waiver, build or publication.

## Oct 12 — reconcile remaining retirement callers and preserve historical evidence

Useful restart/staging helpers now use actual Qt runtime/recovery/projection;
metadata-copy/history producers use actual Qt handlers and LibraryHistory. Retired
widget-only hero/disclosure/VLC producer adapters and Tk cache generation with
explicit existing Qt telemetry/player controls retained separately. Removed obsolete
VLC installers/bootstrap calls and nonfunctional playback-smoke workflow; current
Qt packaged checks/signing/installer paths remain. Maintainability still reports the
large neutral worker, rather than falsely passing because app.py became small.

Current scene/recovery rosters resolve to maintained nodes. Collection-only roster
refresh27domains/618unique nodes is NOT execution evidence or a campaign. Historical
v1 catalog and original source-suite observations untouched; current v2 receipts
cannot relabel those passes. Original generic v2 history adapter11cases passed but
binding unproven due missing exact roster; retained. Separate current v2 run11/11
and source/constituent binding passes, no backfill. Legacy source-receipt positive
and negative controls1084pass after restoring the valid modern app entry provenance
anchor. Initial28fail/1164pass attempt retains old selector/bootstrap failures; its
negative-only passes were not used to claim current baseline qualification.

Current roster/recovery/real queue adapter16pass; two focused adapter/theme checks
pass; release-path19pass initially, missing new Qt history/import process separation
fails then passes after explicit enrollment in build_mac/tests workflow. All20unique
release checks now pass. No compiler/package invoked (bash syntax only). Full current
collection6829/zero errors; source AST scan includes nested imports and finds zero
Tk imports. Modified Python compile/Ruff and diff checks pass. Source results only.

Explicit limits/dependencies: Library fix6f28b81 targets the original585 malformed
main/schema999/malformed-pending availability defect, preserving bytes and refusing
new work; actual successor damaged-profile GUI/recovery still untested. Optional
neutral-worker frame location is omitted because the existing app/server catalog
has no new module label; actual captured helper exception confirms this without a
transport. No incorrect alias or production/wire/schema expansion. Required versus
optional checks and the bounded remaining checklist are in docs/qt-retirement.md.
No frozen mutation, build, production change, permission expansion or publication.

## Oct 12 — macOS dependency floors, read-only

Site owner's official0.2.5 bounded ZIP evidence confirms primary Python26/15,
FFmpeg+ffprobe26/14, PySide15/15 and QtCore13/13 (ARM/Intel). This means necessary
26/15 floors, not an OS support matrix. Existing frozen585 full native-file scan
460ARM/462Intel finds highest declared15.0 and zero scan errors. Current local
Python and FFmpeg tools declare26.0, so a local ARM rebuild reusing them would
retain26. No intentional26 policy/deployment target found; CI uses15 builders.
Successor floor is undetermined until build inputs/final dependencies/oldest-OS
execution are qualified. Metadata-only lowering is invalid. Exact receipts under
recovery-20261011; docs/macos-runtime-support.md describes the packaging choice.
No build/tool install/environment or package mutation occurred.

## Oct 12 — successor prebuild retention and CI dispatch

Parent authorized focused successor artifact-only CI after cleanup owner completed
minimal18 recoverable renames. Fresh independent checks confirm originals absent,
quarantine inode/device/mtime unchanged, inventories present and protected roots'
identities preserved. Existing candidate_space_guard(build) passes at01:39:42UTC:
zero obsolete blockers,85,778,202,624bytes free,20GiB required; no bytes reclaimed.
Review receipt under recovery-20261011/successor-cleanup-verification.json.

Local planned download/extract/sign/freeze/QA staging peak8,637,126,911bytes plus
separate20GiB reserve gives30,111,963,391bytes required, versus85,606,400,000free.
This is a conservative known585-size envelope, NOT a measured successor peak;
actual new archive sizes must be checked before staging/signing. No local compile.
Remote hosted builds use existing macOS15 ARM/Intel and Windows workflows.

Tests workflow lacked an explicit dispatch trigger on candidate branches; add only
workflow_dispatch to run its existing unchanged six-platform matrix against one
exact source. No new campaign/test set/permissions. Release workflow artifacts_only
prevents draft/release/tag mutation. Current source will be frozen after this
increment; publication remains held pending exact qualification/gap review. Initial
sandbox GitHub read failed connectivity; authorized network read succeeded. No
unrelated site/CRM source included, optional frame catalogs unchanged.

## Oct 12 — first successor CI collection failure retained

Tests38193054062 on exact4ceba74 fails all six backend jobs before tests execute.
Original Mac311 failed log retained at recovery-20261011/ci-4ceba74-mac311-failed.log.
Root-level CI collection includes fine-tuning/tests and windows_smoke_test.py,
which the earlier explicitly scoped tests+engineering-quality collection omitted.
Both still imported old app helper/DownloaderApp symbols. Migrate actual pure
benchmark/validation calls and Windows dependency-report script to DownloadWorkerCore/
download_service; no UI alias/fake class or skipped coverage. Four fine-tuning
controls pass; whole-root collection6833/zero errors in27.62s. Windows report now
runs only through main instead of printing/reading tools on import. No benchmark,
training, local build or package exists for failed4ceba74; it cannot qualify release.
The focused correction supersedes that unqualified source freeze; all successor
artifacts/checks must bind the one corrected commit. No historical evidence relabeled.

## Oct 12 — remaining retirement consumers corrected

Exact workflow backend local attempt retained at recovery-20261011/successor-backend-exact-command-v2.log: 231 failed,5612 passed,38 skipped. Failures identified retired app imports, stale widget-only selectors/provenance, and sandbox socket/process denial. This is a failed gate, not acceptance. Current shared worker helpers now bind download_service/models; historical worker receipts accept their original closed label while current receipts use the neutral owner. Announcement source binds actual Main.qml; actual Bridge completion/dismissal behavior remains tested. No candidate receipt was relabeled.

Widget-only cases were retired with named retained Qt/shared equivalents in remaining-widget-test-disposition.json. Durable archive/shared-folder and error privacy controls remain; actual Bridge runtime completion events now exercise rating admission (partial/error/stopped do not count; three completed current jobs do). Source helper native runner tests bind current Qt groups and per-group XML, preserving timeout/skip/contamination failures. Component inventory now requires zero production Python widget buttons and actual shared Qt StoneButton usage; synthetic bypass rejection controls remain.

Focused source-binding corrections269 pass; adapter/theme/metadata335 pass with one timeout-test adapter error then focused repaired timeout1 pass; rating owner1 pass; component inventory5 pass. Remaining failed-file rerun with authorized fixture-local network/process access311 pass,4 platform skips,1 stale component assertion, corrected by the five-case component run. Logs remain under recovery-20261011. These overlapping focused results do not claim full backend/platform/package qualification. Scoped Ruff/format and diff checks pass after formatting correction. Next exact CI must bind the corrected commit; frozen585 and historical failures stay untouched. User overnight release authorization lifts the earlier publication hold once real bounded release checks pass. Optional EQH completeness/frame catalogs are not shipping gates.

## Oct 12 — actual successor CI policy/selector correction

Tests38196074791 on a9e094f: both Linux and both Mac backend jobs fail only four stale assertions, with 5815/5820 passes and42/37 skips respectively. Windows jobs still running at this correction. Original per-job logs preserved in recovery-20261011/ci-a9e094f-*-job.log. Three assertions still expected the earlier usability-required policy despite explicit47767dd/user authorization making only those rows optional; update them to require optional usability AND required interaction checks. Fourth references the retired widget category-mode selector; remove that obsolete node/count while preserving both current Qt membership/card-count selectors and four shared membership/data controls. No runtime change/gate relaxation introduced by this correction. Focused interaction/scene contract14 pass; Ruff/format/diff pass. New full CI must bind corrected source. Full Qt source processes are running separately; package/native/publication remain untested.

## Oct 12 — Windows origin fix and seven current membership controls

Both Windows jobs38196074791 additionally fail live-origin collision and CP1252 scene source decoding; original logs preserved. Source readers use UTF-8. Fixture server now uses Windows SO_EXCLUSIVEADDRUSE with reuse disabled, while POSIX verified closed-origin continuation retains reuse. Existing actual collision/restoration/scene controls26 pass locally; Windows execution pending. Test-only screenshots now save in private tmp_path; three original failures at out-of-checkout save pass5.17s, with all selection assertions retained.

Full local Qt attempt remains interrupted/incomplete, ending exit-11 at recorded-preview create_engine around interruption; original log retained, no full-suite pass or isolated crash cause asserted. Isolated recorded-preview five cases pass6.92s, not a waiver for combined/native qualification. Hosted full Qt suites executing15daabb.

Automatic approval review rejected lowering catalog minimum7→6 as gate weakening. Safe alternative restores scene minimum7 and replaces the removed widget category-mode node with the existing real Qt saved-collection projection/detail/return control. Current catalog also keeps minimum7; historical v1 unchanged. All seven shared/current Qt membership cases and two selector controls pass9 total in2.09s. No customer behavior or remaining behavioral gate weakened. Optional frame catalogs unchanged; no package/publication claimed.

## Oct 12 — historical owner-map reconciliation and final build-source freeze

Completed15daabb Linux311/Mac313 Qt component jobs each have734 passes,9 native skips and one owner-map assertion failure. Original logs retained ci-15daabb-*-job.log. Assertion requires every historical Tk row's retired source file still exist; runtime assertions passed. Preserve all52 retired rows as Git links after verifying each file in exact frozen585; current rows still use code paths and must exist. New current presentation candidates still require reviewed ownership; test code/behavioral requirements unchanged. Historical obligations are not relabeled native passes. Focused owner-map and actual Qt-without-Tk controls4 pass0.91s.

beed8c0 all six backend jobs pass, including both Windows actual exclusive-origin/UTF-8 cases. Its Qt suites continue; any later failure stays actionable. Final documentation-only source increment will run existing Tests and artifact-only release workflows concurrently on one exact clean revision, avoiding local compilation and publication/draft mutation. Build scripts retain their own source/runtime gates; promotion remains contingent on genuine required results. User overnight authorization covers private builds/signing and release only once bounded acceptance passes. Current battery ~36% discharging; sign/native power reassessment required.

## Oct 12 — remaining batch event-owner binding correction

Actual3b9a3c0 source CI Linux313/Mac313: backend5819/5824pass42/37skip, component735pass9skip. Scene suite fails exactly three outcome variants importing retired ui_events.job_info_event, with205/206pass1/0skip. Preserve original job logs under successor-3b9a3c0/ci-*-job.log. Port import to retained canonical worker_events; all success/failure/skipped progress/title/thumbnail/stale-child assertions remain and3 pass1.68s. Scoped Ruff corrected import order; format/diff pass. AST walk over every tracked Python file checks974 product-module imports, zero missing owners. Initial recursive generated-tree audit interrupted and NOT used; no full Qt rerun was claimed locally.

3b9a3c0 Windows artifact build38197714106 passes signatures/runtime/installer/production and legacy published-baseline upgrade. Original Windows helper receipt reports data_preserved_before_relaunch=true but no updater UI-click claim or independently seeded media proof. Artifacts retained with their own3b revision: portable909c6f313f8b767ca849912e0107bf9ab02337eb12bb18db2533de9c40312b46; installerd62ad1f849f1e3aee3614a616ee49ac29b40828271ad317b789013a33f1451f0. They cannot be relabeled as the corrected source. Mac builds not qualified; next corrected single-source artifacts are required. Exact official Mac0.2.5 baseline verified5c71a2c6b3415f9abe5761b46b977f73b7ef3623a16fe9eb85b0756622ebba83; retained Windows0.2.5 installer matches public760a9bf0833f76c0d827c827858970e2edad00283f2c356fd8860bcb334a3b79. Existing signing identity/profile available, no secrets exposed; battery56%charging. Windows source reused same existing checkout via verified incremental bundle, no origin/clone/worktree/access change. Native Windows occupied-origin/UTF-8 controls2 pass12.12s. Release and native gates still pending.


## Oct 12 — exact A22 native results and recovery guidance correction

Exact a22fd50 Tests38199285801 passes all six jobs. Build38199287378 Windows and ARM pass; ARM signed/notarized/stapled/frozen at candidates/mac-a22fd50-arm64/20261012T040359Z-a0dabbd6. Intel attempts1/2 failed; original logs preserved under build/recovery-20261011/successor-a22fd50. Attempt2 has two Watch wheel no-movement assertions and the 2000/1900 thumbnail subprocess120s timeout (696pass9skip). No third blind retry or timeout relaxation. Local original five failed controls and thumbnail3cases pass separately; these do not establish Intel resolution.

Exact signed Windows A22 actual core journey passes17 ordered observations, two independent media decode checks, playback, real cancel/automatic queue, two normal exits0 and unchanged history/media after restart. Complete sealed ZIP-to-working comparison4258files passes. Generic factory binding remains unproven in its unchanged original receipt; independent archive/executable/tree/signature binding is retained separately. Denied-state119 complete event rows have identical canonical SHA before/after native routes; disabled-session preview/production scoped counts remain0/0/0. Truncated original large snapshots remain partial, not repaired. All receipts under successor-a22fd50/windows-native. Native successor Update/Repair and other two damaged-ledger cases remain untested. Mac native fresh preflight remains paused behind a lingering OS Keychain prompt from another task; no credential/protected-control interaction or release occurred.

Windows malformed-main native refusal preserves original bytes/mtime/media, and compatible restoration renders both retained videos and exits normally0. Actual rejection guidance incorrectly suggests disk/access repairs. Existing runtime startup tests checked availability/refusal/preservation but missed the Bridge feedback channel. Three actual Bridge admission cases (malformed main, schema999 main, malformed pending) fail before the correction (ledger-guidance-before.log). A specific read-only history-blocked property now selects constant compatible-ledger restoration guidance without exposing exception text; journal-write and missing-link guidance retain their separate meanings. Representative owner/cause privacy matrix covers all three causes with and without history recovery. Runtime/startup/run-state38 focused checks pass after (ledger-guidance-after.log). No new wire cause/schema, evidence rewriting or weakened admission. This runtime change requires successor artifacts; A22 native results remain bound only to A22.

Intel wheel failure is reproduced locally after1.2s settling: both cases fail with actual editorialPopup visible and welcome kind (intel-wheel-modal-before.log). The Watch test now explicitly begins after onboarding, retains the delay to expose the prior race, asserts no blocking popup, and preserves real wheel movement, exact event counts and denied-consent assertions. Both cases pass5.00s after. Separate thumbnail timeout remains unresolved; its unchanged120s failure now prints complete phase receipts plus all-thread stack capture at100s. All2000-item/pixel/153-capture/owner limits remain. This improves next hosted diagnosis, not a claimed timeout fix.

Combined affected startup/telemetry/thumbnail/run-state source qualification91pass58.71s (recovery-focused-after.log); Ruff/format/diff pass. Normal NSRunningApplication termination of identity/hash-verified blocked MacQA72720 succeeds, no force, so no native QA remains held open. Its incomplete preflight receipt remains failed. No user-owned process or OS prompt control was touched.


## Oct 12 — 4b platform results, native evidence defects, and public AppKit ownership

Exact4b5e390 Tests38210308474 all six jobs pass: backend5819/5824/5844 by Linux/Mac/Windows, Qt components741/9skip everywhere, scene208/1skip Linux+Windows and209 Mac, Windows updater faults28/4skip. Build38210311709 all platform jobs pass, draft skipped. Mac ARM/Intel build source gates5860/37skip,705/9skip,209scenes and runtime smoke pass. Original logs retained under recovery-20261011/successor-4b5e390. Both signed/notarized/stapled/Gatekeeper candidates frozen: ARM32b05cf82218901ad61b7a41d944bf141573a8518c0f8a4f8d689c0e4544acb9 and Intel d2e62b511ee29d64c94cd26cd82a050f856a33155aff49cc03ba25010ee826ec. Actual444/446 runtime Mach-O floors<=15, zeroerrors; necessary floor only. Windows portable5a60c9b5fe9751aa29a8b18a6fff3b32abb2838680f75c118407ecf64ee42e7f, installer ca5ad23a9875e3f306634487ce59b5e00cb76a37b62934eb4979919bd8649dac. All4258 working files equal ZIP, staged ZIP equals factory ZIP; factory verifies on existing qt-retirement branch. Limited interactive task cannot read protected factory receipt; no permissions changed. Direct native wrapper retains its false/unproven aggregate binding flag; independent evidence stays separate.

4b Windows preview: unknown before native Share analytics has0/0/0 in preview and production; actual optin creates1installation/1client/24events with exact4b appOpened and1run start/complete/export. Production0/0/0. First ordered native attempt remains failed due late progress recorder after completion, despite an earlier actual active-progress screenshot. Fresh telemetry-off attempt records actual active progress06:54:29, completion, Library, exact Description geometry, real slowrun/queue/cancel/Stopped. Its later queue-start recorder also missed the already-completed job; original refused checkpoints are retained, not backfilled. These are orchestration evidence defects, not claimed product failures or complete generic journey passes. Future active start/progress/queue recording must stay in one bounded execution batch. Current exact4b core/profile/media/restart completion remains pending; source change below requires successor-bound native acceptance. All9 ordinary Mac JSON hashes unchanged after normally closed blocked preflight72720. Mac GUI still awaits user dismissal of orphan other-task OS prompt.

Exact signed Intel native38216435372 opens one actual onscreen window16.2918s within unchanged20s guard, then fails normal exit with SIGBUS(-10), zero owned survivors. Original startup/launch/native observation/stderr receipts preserved under intel-native-first-failure. No blind retry, timeout relaxation, crash dump or replay collection. Stderr identifies NSThemeFrame adding an unknown NSVisualEffectView. Source inspection confirms native frost is attached as a sibling inside that private frame. Apple's documented public contentView is the highest accessible owner (https://developer.apple.com/documentation/appkit/nswindow/contentview?language=objc). The safety correction permits siblings only when their parent is that public contentView, retaining readable opaque fallback otherwise and preserving native header controls. This fixes an independently proven ownership violation; it does NOT yet establish the SIGBUS cause or normal Intel exit acceptance.

No existing source test exercised this Cocoa attachment boundary; offscreen builds bypass it, and earlier native5e581d0 exit passed without proving every teardown. New independent insertion/state matrix fails before for private-frame attachment and missing-owner opacity, passes after for private/missing/public/rejected-public outcomes (4cases0.13s). Actual public insertion preserves frost; rejected insertion removes partial effect and restores original native state. Source comments/limits documented; new test is in existing component partitions rather than backend mixing. Next exact candidate must pass unchanged native startup AND normal exit before release. 4b immutable artifacts/receipts remain untouched; their passes cannot be relabeled as corrected runtime.


## Oct 12 09:31 UTC — exact 0b native Windows and Intel completion; Mac GUI held

Runtime source remains clean/pushed0b3a6a30a49d5699fadc9fa0d22d1ed82843e46f before this documentation-only update. Tests38219210325 all six jobs pass; Build38219213240 ARM/Intel/Windows all pass, draft skipped. Original logs are preserved under build/recovery-20261011/successor-0b3a6a3. ARM signed/notarized/stapled/Gatekeeper/frozen archivef2f5c2c1c4a203bd8dce4919dab4e391dfbd32ceab64a20e44017f2341f40f12, receipt candidates/mac-0b3a6a3-arm64/20261012T082508Z-5ef88f78. Intel runtime446MachO floors<=15, zeroerrors; signed/notarized/stapled/Gatekeeper/frozen archive2df4e7cdc32c0257a58f728458ccb35082988afa72c0c2ece803319784dfdcb2, receipt candidates/mac-0b3a6a3-x64/20261012T085949Z-d2adb7e6. First freeze used systemPython without mandatoryjsonschema and failed; original failed log and partial generated attempt retained. Corrected freeze uses existing qualified.venv, no rebuild. Native signed Intel38227222882 passes actualx86_64/Rosettafalse onscreenwindow9.087s under unchanged20s guard, normalexit0 and zeroowned survivors. Original4b SIGBUS remains failed; source correction plus successor pass does not prove that crash's rootcause.

Final exact signed Windows archive d417d4ce0d7798fe081f9474694782d5b6bf5c3820d15e1f9fffba0a71ff6f4e, installer538a8418bbf164724dc756e0fbdd1b9e2d03dd361f3cd2837ddd92416c86fc3f, executablee9872e55dd694c8869245900d6427327c40ffa7ba7eea35161ee1d3f0f1c52b9. All4258 working files equal sealed ZIP. Original maintained windows-native/e2e-result-original.json now passes17 ordered actual observations: export, progress, actualcancel/Stopped/automaticqueue, Description, normalrestart. Atomic driver's second-launch folder ambiguity is preserved; only the still-pending actual17th Description/restart observation was completed through the visible unique original-media route. No late/backfilled event or original receipt rewrite. Both launchreturncodes0, stable history/media hashes, zero staging and owned survivors. Independent final full decode checks both actual H264/AAC24.0333s exports pass, SHA715a649cb50cb06a8e32aa161458baaf548c3e2d5057c78484be3277497c90ab. Generic immutable-factory binding remains false/unproven in original receipt; independent sealed archive/sign/source/tree/executable evidence remains separate, not relabeled aggregate factory acceptance.

Native Windows Update starts from actual published0.2.5/850e19e portable ZIPee179e0917d6baa51401726ca0b9a10d472181bc5feeebf082f143ecf2066122 in isolated existing-account private QA. Ordinary executable27datafiles/two uninstallkeys/two shortcuts preserved first. Actual native import creates two media entries and two generated thumbnail JPEGs; five durable history/media/thumbnail files hash-bound. ActualLater and private loopback503 failure observed, restored healthy feed offers signed successor. NativeDownload update produces original helper repairfalse/installerexit0/dataPreservedtrue and real33652/E987 relaunch. Actual current-successor503 recovery popup Repair VODForge produces original repairtrue/installerexit0/dataPreservedtrue and real48824/E987 relaunch. Independently all five durable files byte-identical after each. Original old-PID snapshot refusal, welcome navigation and parser-error attempts preserved; no claim those are product failures. Original receipts and bounded summary under windows-update-native.

Private previewunknown before actual Share analytics has0installation/0client/0events in both databases. Nativeoptin delivers exact publicbaseline then0b appOpened, oneclient_update0.2.5→0.2.6, checkfailure/relaunch evidence and onerepair_started/onerepair_completed. ActualLater is retained as a native UI observation, not claimed a delivered Later event. ActualnativeOff followed by Library/Watch/Forge routes and normalexit0 preserves complete61event canonicalSHAca79b16abb2521b16154f1d7a815ec75d2716f25abf63fb098bfecc6ded2d949 and complete scoped installation/client digests. Outboxabsent/0events; this does not claim an actual queued-event purge attempt. Telemetry-disabled exact45304 attests previewfalse/productionfalse, native routes and normalexit0; same complete datasets remain identical. Scoped productionfinal0/0/0, every connector query rows_written0. No credential content selected. First60-row baseline preceded laterHelp closure and is retained; immediate61-row baseline is actual withdrawal comparison. Original connector read receipts, no truncated snapshot repair.

Ordinary Windows registration restored to E:\Applications\VODForge0.2.3, original executable and all27datahashes/two shortcuts unchanged. ZeroVODForge apps; exact private loopbackserver51380 stopped after command/executable identityverification. Four exact idle owned scheduled-task definitions retained as XML then unregistered, no unrelated task/process touched. No localheavy job/hang, MacAC100%,58GiBfree at09:24. No obsolete permanent deletion.

Three corrected native Windows ledger cases remain valid scoped4b evidence in successor-4b5e390/windows-native/ledger-native-bounded-summary.json; only production change4b→0b is mac_windowing public-parent attachment, which returns before AppKit on Windows. No repeat/relabelling of unaffected ledger passes. Mac native exact0b core/playback/cancel/queue/restart, recovery/privacy and Update/Repair/data-preservation remain untested/held behind the existing owner-held OS Keychain prompt awaiting manual clearance. No protected-app action, permission change or new credentials. Public latest read still0.2.5/850e19e; private draft holds uniquely named QAIntel0b artifact only, no clobber/publication. Release remains held. Canonical ongoing checkpoint build/recovery-20261011/execution-checkpoint-current.json records current scopes and remaining gates.

## Oct 12 — Mac bounded gates complete; release-wide editorial change

Exact0b3a6a3 Mac core17 passed with two clean exits, actual playback/cancel/automatic queue/restart and stable history/media. Three ledger refusal/restoration cases pass. Public0.2.5 Update passed exact successor executable/tree and seven durable data hashes. First Repair strict tree check failed on1747 symlink modes under inherited QA umask077; original failure retained. Bounded ditto022/077 control reproduced the environment cause. Existing-root chmod was rejected by automatic review and was not executed. Fresh OS-created owner-only temporary fixture with ordinary022 launch passed actual Repair, exact full tree/executable and all seven data hashes. Unknown and scoped production datasets stay zero; actual native withdrawal preserves privacy-safe aggregate preview snapshots, not claimed raw-row hashes. All nine ordinary Mac JSON hashes unchanged. Native apps/feed closed; desktop released13:28:45UTC. Receipts: successor-0b3a6a3/bounded-release-qualification.json, mac-native-fresh/e2e-result.json, mac-ledger-bounded-summary.json, mac-public-update/after-update.json, mac-repair-fresh-private/after-repair.json, mac-final-d1-original.json and mac-final-cleanup-ordinary-hashes.json. Windows generic factory flag remains false; independent complete archive-byte binding passes. Original failures and scoped limitations retained.

Latest user instruction requires disabling What's New for publication0.2.6. Exact qualified0b has hardcoded SHOWCASE_MODE=whats-new and no release-metadata override; publishing it would violate that instruction. Publication held, staged immutable artifacts and old private draft preserved. Minimal runtime correction changes only editorial selector to none. Enabled catalog fixtures now explicitly opt in; actual release choice checks no automatic presentation. First affected suite10 failed because fixtures assumed enabled default; retained announcement-disabled-026-focused.log. Corrected fixtures plus release-choice check36 passed7.14s; Ruff/diff pass. No updater, ledger, media, telemetry consent or persistence behavior changed. Successor package/signing/startup and absence-of-editorial verification required; unaffected bounded core/data/privacy receipts retain exact0b scope and are not relabeled.

## Oct 12 — release hold, screenshot diagnosis and announcement harness source binding

User explicitly holds publication pending drive-label/completed-action investigation. Three supplied Library photographs materialized with identity and viewed as pixels. Actual WindowsC: VolumeNameOS, total249381777408/free71905050624 matches photograph. GetVolumeInformationW prefers actual label since4743757; public0.2.5 uses identical logic, no disk renamed. Both requested completed titles match one ordinary history row each, have run IDs and present actual media; ordinary historySHA db8279745cb4a51f8c9442e821e8e43ffcc1fad7173eba90c91540a5c7c33665 unchanged. Menu predicates exclude completed from every conditional action; ViewActivity alone remains.9674e2f intentionally removed saved records/actions from work deck;7e8b91d reintroduced completed records without menu actions. Public0.2.5 has same omission. Main selected panel retains owner-bound Play/Library/Folder controls, visibly present in photograph. No drive/menu change made before desired behavior clarified. Original bounded associations and findings under user-action-investigation and successor-0b3a6a3/windows-visible-user.

bdaaa09 artifact workflow38258383514: Windows passes; MacARM repository5854pass37skip/6failed announcement-harness assumptions; Intel fail-fast cancelled, not a tested failure. Original log retained successor-bdaaa09-build-failed-original.log. Candidate-bound enabled editorial source must not inherit current disabled source's blanket rejection. Harness now derives disabled decision from verified candidate producer actions; invalid source bindings retain errors/full requirements. Synthetic enabled tests explicitly declare enabled source/config; source-less enabled fallback negative controls remain. First bounded correction172pass2fail retained; corrected affected174pass8.10s, Ruff/format/diff pass. Runtime selector remains only product delta; no gate relaxed, no public publication. Further packaging awaits resolved user direction.

## Oct 12 — authorized completed Run Deck menu restoration

Parent/user authorized correcting the confirmed omission; publication still held for review. RunDeck shared action popup now exposes Play, Show in Library and Show in Folder for completed saved owners, so both the direct card and AllRuns use identical routing. ViewActivity retained; drive label unchanged. Routes reuse existing unique saved owner lookup/openLibraryOwner/openLibraryDetails/openLibraryFolder. One shared existing-Bridge availability slot checks actual associated file and catches unreadable filesystem errors; menu and selected panel disable Play/Folder for missing media while Library remains available for recovery. Folder opener now reports OS launch failure instead of silently ignoring false. No new owner/module/subsystem, no ordinary history/media change.

Existing selected-panel next-actions and saved-owner tests covered routing/owner safety but missed the two completed popup entry points. New rendered physical-QTest pointer cases cover both menus, exact selected owner among different saved items, missing media with durable Library access, owner replacement while popup remains open, and folder-opener failure without data change. Related existing hover/seam/fifth-owner overflow and selected-panel controls remain passed.24 focused checks pass33.94s in completed-menu-focused-final.log. Initial before/after-v1 attempts retain six dict-versus-QJSValue test reader errors; not mislabeled product failures. Corrected prior-QML negative control is retained separately and restores working source in finally; all eight actual menu cases fail because actions absent. Scope is source-rendered bounded UI, not exact packaged or universal interaction acceptance. New successor private platform artifacts and actual visible completed menus remain required; earlier core/privacy/ledger/Update+Repair evidence remains scoped unchanged predecessor proof.

## Oct 12 — dynamic Windows drive letters, no Mac label change

User explicitly requested volume name plus dynamically resolved Windows drive letter; C: is only an example. StorageVolume display_label derives letter from its existing resolved root identity, preserving raw volume label/path. Named C/D/E/F and mappedZ display names include their own letter; unnamed drive keeps Drive D:, existing-letter labels do not duplicate. UNC shares and Mac mount paths receive no invented letter. Qt capacity summary/selection and shared saved-location labels use this display fact; capacity, selection and action identity remain exact existing path. No volume rename. Actual Mac diskutil root VolumeNameMacintosh HD, mount/, current canonical volume owner labelMacintosh HD/local verified with existing.venv. Initial non-escalated diskutil read and systemPython missingpsutil retained as tool/runtime limitations, not product failure. Historical label-name preference introduced4743757 on Sep22 18:10Central;3e444b4 Sep23 19:20Central corrected malformed Windows root escaping. No proven specific historical ordinary Windows appearance beyond source evidence; user's C: recollection is not dismissed.

Focused volume/menu39pass16.70s, including12 named/unnamed/already-letter/mapped/UNC/Mac cases and duplicate E/F saved locations with unchanged path identities; existing actual menu routing/missing/stale/folder-failure cases pass. Ruff/format/diff pass. Drive-letter source committed separately atop completed-menu fix, before final batched successor build. Parent reports imminent further user observations: no additional build dispatched now; existing d8cd6f8 build38261179241 and CI38261274974 continue, no cancellation. d8 packages do not contain this drive-letter increment and cannot be claimed complete. User-visible Windows candidate remains untouched0b. Publication held pending corrected-candidate review. No broad deep campaign; only affected checks and future quick startup/required signatures/menu/drive visibility.

## Oct 12 — combined user-found UI/Trash batch source completion

Publication remains explicitly held for private review. User asks normal closure of existing idle VODForge instances and visible exact fixed candidate on Mac/Genesis after one combined signed build; active downloads must finish safely, no forced termination. Current Windows0b user app remains untouched while source checks run. MacAC100%,53GiBfree. Temporary exec-server disconnect was verified recovered by actual pwd/source commands, not inferred from catalog status. Kryden has current bounded diagnostic window and will release before VODForge native/signing use.

Options now reuses the single actual Settings form through visual reparenting, same controls/backing Bridge and preference scope; MP4/MP3/original/export/YouTube browser+cookies choices/thumbnail/metadata/NVENC capability/appearance/privacy remain their existing owners. No duplicated preferences or browser/OS permissions. Top reserved gap removed by using existing full-form layout. Functional checks cover normal/minimum windows, vertical reachability, toggles/durable settings, active-run unchanged, access-return and manual dropdown/unused-field retention. Old separate-left-column geometry expectations updated for explicitly requested full form, not retained as fictitious acceptance. Source renders options-full/custom and Library/Organize tags inspected as actual pixels; no new aesthetic scoring. Original QML implicitHeight read-only error and QJSValue/dict/test delegate reader attempts preserved under options-investigation/options*.logs; fixed in source/tests.111 related option/copy/tag/metadata/enrollment tests pass99.44s; tags-folder-editor one pass2.20s.

Library/Player Output Details maps known export-mode values from the legacy Output rate-control mode field to Preset, preserving distinct Video rate control Quality/CBR and true audio/stream-copy values; requested/measured rates untouched. File path display removed; actual Saved Filename and Saved Location retained, raw metadata untouched. Source/user tag projections separate read-only source and editable user lists; Tags copy is combined case-insensitive deduplicated, Copy source tags remains originals-only, Notes never reuse descriptions. Source chips visible in Library, Watch details and the screenshot-identified Organize Library item popup; metadata file editor binds userTags only to prevent accidental source migration. Source/user data storage unchanged.30 dedicated tag/copy/metadata checks pass13.74s.

Trash cause: completed media/companion transfer and durable history removal returned without invoking existing Move's empty-source cleanup. Shared cleanup now runs after successful durable completion only. Refined channel scan uses canonical channel metadata/layout plus retained root, no-follow bounded scan. ANY other media, metadata, thumbnail, unknown file, redirect or scan error retains every higher ancestor; only selected verified empty video folder may prune. With no remaining artifacts, independently durable-owned empty branches prune bottom-up through channel, root retained. Arbitrary unindexed empty sibling directories have no persisted ownership marker and remain preserved; do not imply their removal. Literal Channel/Playlists/Playlist/Video, legacy/current roots, orphanMP4/FLAC/metadata/thumb same/different playlist, unknown files/empty dirs, scan/read/transfer/history/receipt failures and Windows lexical case/UNC/containment are disposable fixtures only. Earlier original6failed/12passed and subsequent intermediate failures preserved. Current177 related checks pass4.42s. Actual MacNSFileManager Trash API at14:56:06UTC transfers3fictional files with returned Trash locations and independently matching bytes; verified empty chain pruned/root retained. First /tmp lexical-symlink fixture refused before Trash, preserved; resolved /private/tmp fixture passes. Windows RecycleBin native route not repeated, Windows bug is user-observed; no claim Macuser reproduction or actual customer leftover cleanup. Evidence successor-0b3a6a3/windows-visible-user/trash-channel-policy-final.log and native Trash fixture receipts.

Watch cause: correct page extent existed, but outer wheel handler only observed/delegated scrolling to Qt; pure-horizontal TouchPad events also never reached vertically oriented RailWheelHandler. Outer page now applies bounded vertical delta; existing rail owner retains vertical/mixed gestures plus a horizontal-only companion on same parent, axis guards prevent double application. No extra content item/owner/framework.19 related tests pass38.53s; all matching10 cases fail actual prior source12.04s and current QML restored in finally. Empty/populated, normal/small, Mouse/syntheticTouchPad, momentum/reversal and exact one normalized horizontal/vertical delta with drift covered.0.5px allowance handles fractional end alignment262vs261.875 only, does not allow doubled movement. Physical trackpad timing/native device acceptance untested. Original duplicate horizontal228vs114/failure/diagnosis logs preserved. Source docs confirm Qt orientation defaultVertical; link https://doc.qt.io/qt-6/qml-qtquick-wheelhandler.html.

CI d8cd6f8 actual backend failures came from missing Qt test enrollment, not native product startup. New completed-menu, shared-options and watch-scroll modules each excluded exactly once from backend and enrolled exactly once in Qt stage in build_macos.sh/Tests workflow. Original source/build logs retained, no check discarded. Existing dependable broad regression/build/runtime gates retained; no media/update/privacy/native36 campaign restarted. Compact real-flow checklist build/recovery-20261011/held-batch-user-flow-checklist.md states evidence/remaining native review and why specific existing tests missed each instance. No coverage-percent or universal EQH optimization claim. All original exact0b receipts remain source-scoped; no relabeling. Combined signed artifacts, brief native review and visible ordinary-profile launch remain pending.

## Oct 12 — combined review candidate stale annotation fixture

Exact25b4d94 Mac313 Tests38267268024 component job retains original failed log at build/recovery-20261011/successor-25b4d94/ci-mac313-failed-original.log:773pass/9skip and one assertion failure. The existing exact annotationValues fixture expects only personal note/tags/category, while the authorized source/personal separation adds readonly sourceTags. This fixture has no source tags, so explicitly require sourceTags=[] and retain all personal-note/tag/category/playback restoration assertions. All three projection tests pass1.09s; Ruff/diff pass. Test-only correction does not change candidate runtime; exact25b private review artifacts remain bound to25b, not relabeled as the harness follow-up. Full CI result remains failed until corrected existing workflow completes.

Windows private exact25b build38267264224 passes signing/runtime/installer/fault/actual-upgrade gates. Portable6e42e2afbcfbe1d0e4766e1320ddc85847f518119dfc4a0ee879891214c66f47, exe d861239d2e02d3016355622730c2432eaf324f366d3f6b0917706724d57e3664; all4258remote files match ZIP. Existing ordinary idle0b25332 closed normally, exact25b52868 is visibly open session1. Original launch receipt remains false because an actively opened log rejects Get-FileHash, not a startup failure; independent durable profile/media readback pending. Mac AC100%charged/52GiBfree, desktop clear; Mac artifacts still pending. Publication explicitly held. No obsolete deletion, credentials/permissions changes or ordinary install/registry replacement.

## Oct 12 — replacement owner: preserve quick Options and explicit subtitle requests

Replacement continued the SAME canonical qt-retirement checkout at8cefd57; inherited uncommitted Main.qml Options restoration preserved in build/recovery-20261011/private-review-successor/Main-inherited.qml before edits. No clone/worktree or parallel editor. No .agents directory/skills exists in this checkout. User15:55 clarification overrides the earlier full-form interpretation: Options retains original quick-select surface, Custom width/column liquid morph and reduced-motion behavior, and adds browser/cookie access, thumbnail embed/save, NVENC/export/MP3 preferences via existing Bridge bindings. Settings remains its own form. Updated affected functional tests inspect quick controls, durable shared settings, unchanged active job, access return, Custom manual scrolling/selector lifetime and close. Existing output-mode display contract now passes unchanged with the restored real Repeater; no assertion disabled.13 checks passed22.26s; two actual morph intermediate/reduced-motion checks passed5.30s. HEAD prior-QML fails both morph cases; original negative control saved, working QML restored in finally.

Read-only Genesis process read confirmed actual51068/session1 and active-run.json present at16:06UTC; no close, native resize, duplicate download or retry. Existing bounded log identifies exact qu subtitle HTTP429; Runasimi's qu mapping is correct. Current subtitle behavior fails on provider transport refusal; no missing translation marked successful. Source fix now additionally refuses explicit unavailable/unverifiable translation before transfer instead of silently committing originals-only; Off and same-original requests retain prior behavior. Friendly429 guidance names subtitles, preserves failure, asks wait or an explicit Off choice.58 affected subtitle/error tests pass0.98s;13 original-caption tests pass0.66s. Four prior-source cases fail (missing target/source/Runasimi refusal and specific429 guidance), original logs retained. No network used by tests, actual media/subtitle roundtrip uses disposable local fixtures. Provider429 remains external; no guarantee a later request succeeds.

Windows geometry: reviewed actual supplied photograph and existing complete native frame captures/geometry. Earlier52868 genuinely paints over the native header and short at right/bottom at96DPI/1100x740 client. Same-process reversible resize and fresh SAME signed25b51068 show correct client rendering; fresh Qt/native both report client origin30,30,1100x740 and frame top31. Existing summary windows-review/windows-frame-investigation-summary.json retains the blocked SW_RESTORE reintroduction control (active user work). Initial helper SW_RESTORE is a supported inference, not proven cause. No speculative DPI/windowing runtime patch, no fresh native geometry mutation while active work. Full frame/client bounds remain required for brief successor native review; source/offscreen geometry cannot close this native defect.

Mac workflow38270283969 is actually FAILED ARM before packaging / Intel cancelled, no8ce signed candidate exists. Existing logs retained; affected old output-mode Repeater expectation now passes after genuine product restoration. Replacement attempted parent foreground coordination via app tool, returned thread-not-found; Kryden owner explicitly reports no GUI/heavy job and private app open for manual use. Do not touch Kryden/keychain, do not assume parent foreground granted. Mac/Windows successor signed artifacts and visible fixed launches pending. Public remains0.2.5;0.2.6 publication HELD. Original0b broad acceptance remains exactly scoped; no repeat campaign or relabeling.

## Oct 12 — additional private review: chapters, personal detail groups, selectable text

User16:17–16:19 instructions add horizontal Chapters AFTER Recently Added, ONE copy emblem for the entire chapter list (superseding the initial per-item interpretation), clearer Source tags/Your tags/Your note groups, and selectable informational text. Three supplied images materialized with current Library helper and identity into private-review-successor/chapter-reference and inspected as pixels. Existing cff9bbe artifacts are predecessor-only and do not contain this batch; no source/artifact relabeling.

Player uses existing ScrollView/RailWheelHandler, horizontal chapter cards, one existing CopyButton with existing feedback, and owner-bound copyPlayerChapters. Clipboard contains complete sanitized timestamps/titles in plain text, including hour formatting; no links or new telemetry vocabulary. Separate seek control preserves chapter navigation while selection/copy cannot seek. Source/personal tags and note now have labels, wrapping and subtle separators; private editable owner/copy semantics retained. Existing SelectableText now uses read-only/plain TextArea and Qt's lazy built-in editing menu. Expanded to player title/creator/description/facts/personal details/chapter text, Library title and Source URL and Forge fact values. Source URL has a separate open action so selecting does not open a browser. Buttons/chips retain their control behavior; no blanket editor substitution or hidden/password text exposed.

Affected source pass:22 cases in the combined player/copy/selection/hover sequence initially passed, four new open-action center failures retained; center fixed and the copy-target reader changed to identify factLabel rather than first accessible action after adding a distinct opener. All four actual pointer/normal+wrapped/minimum+wide copy targets pass9.11s. Three chapter/group cases pass4.79s; subsequent hour-boundary two-case pass3.60s. Standard Qt menu/action performs independent clipboard copy and leaves readonly text/navigation unchanged1pass2.32s.6 completed-menu routing checks pass9.78s. Three prior-PlayerScene failures and prior-SelectableText menu failure retained, working files restored in finally. Original fixture visibility/QObject-delegate reader and menu API attempts preserved separately; no assertions disabled. Actual source screenshots player-chapters.png and player-personal.png inspected, no aesthetic scoring. Ruff/format/diff pass.

Native source attempt in fictional isolated HOME is NOT packaged acceptance. First probe omitted required Basic style and emitted customization warnings, retained as invalid environment. Matched Basic-style Native-popup preference also produced CUA context query timeout; both probe executor readbacks exit139 after cancellation, no normal-exit/root-cause claim or crash dump read. Native-popup preference removed; final component uses Qt's built-in Basic popup, not claimed true OS-native. Fallback source probe actual Cocoa title focus/Cmd-A exposes selected Fictional chapter review. Right-click did not crash the immediate readback but separate popup/menu copy is not independently verified. Later scroll tool waited80s then Transport closed; executor session lost/pong_timeout, no normal quit claim. Actual psutil read confirmed owned17419 absent/no children; Kryden independently confirms no Python/VOD window/process. Ordinary profiles/apps untouched. Native GUI slot released, message tool itself also Transport closed; do not attribute disconnects to user cancellation. Native Mac/Windows packaged selection/context-copy and exact combined visible launches remain required.

Existing cff source CI38275602041: four Mac/Linux jobs pass, Windows311 backend fails process_cleanup_soak timeout at unreaped PID assertion (5903pass/17skip, no source causal attribution/repeat); Windows313 component774pass/9skip/two Show-in-Folder test failures are slash-only QUrl.toLocalFile versus nativePath spelling. Test now compares exact selected-owner Path identities; calls/data-preservation assertions retained. Windows actual fixture identity still checked, no opener/runtime change. Logs original under private-review-successor. cff build38275597950 signed Windows and unsigned ARM pass; Intel still pending at last read. No restart of old broad core/privacy/ledger/update/Repair campaigns. Current combined successor packaging/launch is pending;0.2.6 remains HELD, public0.2.5 untouched.

## Oct 12 — exact d171 private launches and responsive Options successor

Exact d17194c signed Windows build38280794882 passes runtime/signatures/installer/fault/actual-upgrade gates. All4258working files match sealed archive885db85db8639c85bf18d86780e060e1168fb6d19846de2cb71c5c3d541929f3, executabled3363aff9396d6f44142765a3e1e0eef27e07fc3fb551cf7649779923d150ca6. Fresh17:05:44native read verifies51068visible/stateidle/queue0/children0/busy0; presence of idle journal is not active work. Preserved40ordinary files, normally closed exact visible owned window via WM_CLOSE (not force; Process.MainWindowHandle was empty), new57272session1 visibly opens17:11:30UTC. Initial receipt flags oneMP4+metadata/thumbnail and watchprogress; original retained. Independent17:12:27Python readback matches all14media/companions and backups, only watchprogress differs. No restoration/overwrite performed; initial transient discrepancy cause remains unknown, not claimed repaired. History unchanged. Full actual native window screenshot inspected,96DPI/client1100x740/origin30,30/frameTop31; caption above header and painting reaches client right/bottom. No SW_RESTORE or speculative DPI/runtime patch. SW_RESTORE causality remains unproved. Options native probe refuses user-changed foreground before any input; new app left open. Receipts under private-review-d17194c: complete-package-binding.json, visible-launch.json, preservation-readback.json, window-frame-fresh-ready.json/png, native-options.json.

Exact ARM hosted build passes,444runtime MachO floors<=15/noerrors. DeveloperID/notary/staple/Gatekeeper passed; frozen candidate20261012T172754Z-58356bfa archivef5c09292d26e3643d46f4c64dc5c1fea2d9eba95138b71c3d7f50d6b6dc1d065. Signing-policy eligibility alone does not lift review hold or imply release-wide acceptance. Ordinary Mac25792 visibly opens17:28:31UTC, CUA confirms actual VODForge Cocoa window, readyfile nativeheaderintegrated/frameTop0. All115profile+16media/companions unchanged at17:33:15, history unchanged; backup verified. User appears reviewing Options; app left open, no source probe/current signing job. CUA transport recovered after earlier failures; parent app-message tool still cannot find cloud parent. Exact d171 Tests38280798036 all six jobs PASS; no old broad core/privacy/ledger/Update+Repair campaign restarted. Context-menu native copy remains unverified; standard Qt menu source proof is not OS-native acceptance.

User17:25 adds new Options layout correction; supplied Library photograph materialized with existing supported helper and identity, inspected under options-responsive-reference. d171 visible apps/frozen candidate do NOT contain this later change. Source now removes40px reserved top strip, uses third right column for extras in normal MP4, adds manual fourth group when available width can support all groups, and falls back to independent left/manual and right/quick scrolling columns. Column minima/gaps determine fit; no screen-resolution lookup. Audio formats stay compact. Existing quick selectors/liquid reveal/reduced-motion/shared Bridge bindings retained; Settings remains independent. Extras keep their single owner and precede Custom summary after visual reparenting. Existing VerticalScrollChain reused per viewport for mouse/trackpad phases and edge ownership; no new module/subsystem/dependency/telemetry vocabulary.

Existing size/capped-height/set-contentY checks missed group placement, top gap, relocated child order and wheel ownership. New rendered group/bounds cases cover normal+Custom at narrow/middle/wide sizes, live wide→narrow→wide relocation, one input owner, no duplicate controls, real synthetic wheel movement without moving sibling viewport, shrink bounds and last-field reachability. Earlier direct left-wheel integration fails with0movement; preserved. Final22affected checks pass34.90s including prior bindings/active-job preservation/access return/manual dropdown/morph contracts. Four genuine prior-source layout failures retained; working Main restored in finally. Source three/wide/narrow images inspected without aesthetic scoring; physical trackpad timing and exact new package native behavior remain open. Original first3stale-width failures/QML reference error, then2test-callback NameErrors from overly broad test edit, and fixture-no-overflow attempt retained and corrected; no assertions disabled.

Predecessor cff Intel build original failure is customReveal0.99077 after fixed350ms,739pass/9skip. Test-only helper now bounds endpoint wait while retaining exact endpoint, intermediate morph, width and reduced-motion assertions. Two initial endpoint cases pass5.99s; full affected22 also pass after correcting callback reader. New successor private packaging/visible launches required for responsive layout; do not relabel d171. Public0.2.5 untouched;0.2.6 publication HELD. Provider Runasimi/qu HTTP429 remains external, no duplicate network retry or language substitution.

Responsive follow-up: source285225f geometry/bindings/wheel checks passed but covered only customReveal/width motion. Added independent height-change sampling reproduces an introduced instant height jump (normal1fail/reduced1pass, height-morph-before.log); expanded groups made the height cap apply immediately. Popup now interpolates separately bounded collapsed/expanded heights with the SAME liquid reveal, preserving frame intermediates and reduced-motion endpoints. All22affected cases pass37.05s in height-layout-final.log, Ruff/format/diff pass. This actual runtime sizing change invalidates285 packaging for final UI acceptance; artifact-only38286439356 cancelled early and preserved, no artifact download/signing/native launch from it. d171 opened candidate all Build38280794882 platform jobs nowPASS/draftskipped and Tests38280798036 allsixPASS; these remain exact d171 proof, not successor proof. Open user apps were untouched; final responsive+height successor requires its own private build/sign/brieflaunch checks.

## Oct 12 — exact f961 private launches, review hold retained

Exact f96149759b66a79f0a34e4d74b09ae70fa261c85 artifact-only workflow38287312757 Windows and ARM jobs pass; Intel remains in progress. Windows all4258package entries match sealed ZIP eafb944544b749dd92ee5a40f219c7a465e357a815c84907c01f68c286f0f556; signed executable eb689eeabfaf398331500fa4167d43dbb4bf1e19b47216a6233064cc90791bd8. Fresh strict idle/queue/children guards and40file backup before visible PID56632/session1 at18:20:59UTC. Initial Get-FileHash receipt flags3media companions; preserved original. Independent Python18:21:20 readback confirms all40files unchanged, no restoration. Cause of original discrepancy remains unknown. History unchanged. App left open; no SW_RESTORE or duplicate download.

ARM444MachO runtime floors<=15/noerrors; exact DeveloperID strict signature/notarization/stapling/Gatekeeper pass. Frozen candidate engineering-quality/candidates/mac-f961497-arm64/20261012T182718Z-15ae08e1/candidate-artifact.json archive1f601d0de3ca40d57ee2b6db1c30f75dab4399cb52b8abc925d0f21734f98eec, executable521461e6130bf4c67d4649de9f0b470cde218ba57f9de0a86ab5dcced9efb4d5. Fresh ordinary idle/noapp guard, backup115profile+16media/companions verified. PID36284 launched18:27:41UTC, actual exact-path CUA AX/window/screenshot verified; initial premature getApp procNotFound retained, ready observation succeeds. Cocoa ready visible/nativeheaderintegrated/frameTop0/1100x740. Independent18:28:35readback all131files unchanged. App left open for user review, no preferences/UI mutation. Receipts under build/recovery-20261011/private-review-f961497: windows-visible-launch.json, windows-preservation-readback.json, mac-visible-launch.json, mac-preservation-readback.json, arm-sign-notarize.log, arm-freeze.log. Earlier d171 Mac normalexit0 at18:01:11; Windows readback18:01 noapp with exitcause/code unproved, so historical launches never imply continuously open.

Both exact f961 private launches now delivered; bounded affected native Options/context-menu and Windows fullframe checks remain separate from launch proof. No expanded core/privacy/ledger/Update+Repair campaign. Public0.2.5 unchanged;0.2.6 publication HELD. Candidate signing-policy eligibility does not lift hold or imply global release acceptance. Runasimi/qu provider429 unresolved. No credentials/security/access changes.

## Oct 12 — read-only production backend checkpoint

Authenticated20:39:37UTC intervalfrom15:08:28Workerrequests/0runtimeerrors/1clientDisconnected; internalstatusnotcustomerHTTPfailureproof.17D1readsonly/0rowswritten/quick_checkok/noFKviolations. Accepted4630 vsreconstructedcutoff4623(+7):Windows0.1.8+4/0.2.5+3, nonewfailure/rejectionaggregates; acceptedtimestampdifferences483.998–557.621s remainclock/outboxambiguous.34schemaentries/28migrations, changesvsOct11historyexactmatchlocalmigration27/28; deploy/migrationtimesbeforecutoff. Exact15:08savedreceiptunavailablelocally, notclaimedcompared/equal; reconstructedcutoffandOct11historyscopedexplicitly. Publicsite/feed20020:40:21–22UTC/v0.2.5.8downloadrecords/assetcountincreasesnotadoption, monitoringnotexcluded. KnowncustomerHTTP/rejectionvisibilitygapdeduplicated. Sanitizeddatedbaselineandhashes: build/recovery-20261011/backend-monitor-20261012T2039/REPORT.md, backend.json, supplement.json, comparison.json, schema-baseline.json, public.json, SHA256.json. No secrets/events/mutations/access/subscription/GUIinputs/publication. Privateapps/reviewuntouched.

Monitoring clarification: priorOct11morning/night REPORT.md explicitly retaincustomerHTTP/rejectionvisibilitylimit; notnewlylostcoverage. Missingexact15:08receiptislocalcomparisonavailability, notauthenticatedaccess/monitoringloss (currentreadsallpassed). OneclientDisconnected/0errorsisobservedoutcome, noestablishedmeaningfulregression. SavedCOVERAGE-CLARIFICATION.md; noproductionqueriesrerun.

## Oct 12 — same-original subtitle warning correction (local source only)

Removed only obsolete unavailable-translation/original-only fallback log branch in DownloadWorkerCore._download_item_to_staging. apply_original_caption_options already refuses any genuinely missing explicit target before transfer; the remaining reachable false warning was when selected target equals evidenced original language. Selection, options, transfer, validation, commit, settings and failure guidance unchanged. Diagnostic invariant: report the actual selected outcome, not infer failure from absence of a second translated track. Earlier selector/stream/error checks covered track integrity but did not traverse worker reporting. New bounded real-worker fixture covers Off, same-original, available translation, and absentRunasimi: captured logs/track metadata/unchanged choice plus zero transfer on true unavailable error. Before:1fail(same-original)/3pass0.84s; after62affected subtitle/error tests pass0.84s including existing real local subtitle roundtrip. Ruff/format/diff pass; no duplicate broad campaign. Receipts build/recovery-20261011/private-review-successor/same-original-warning-before.log and same-original-warning-after.log. No live network/download/build/app launch/UI action. Open f961497 private apps do NOT contain this later source patch. Runasimi/qu HTTP429 remains upstream refusal, not fixed; public0.2.5 unchanged/0.2.6held. Preexisting uncommitted launch/backend-monitor log entries preserved separately from this scoped commit.

## Oct 12 — responsive Options subtitle owner, readable names, bounded morph materials

Cooper review reports translated selector works inSettings/unresponsive inOptions, plus laggyliquidmorph. Source callback uses same Bridge/menu; Options extras occupy independent rightscrollowner, but AnchoredPopup checked anchorvisibility against composerOptionsScroll. Correct viewport now follows sideBySideExtras vs stackedowner; sharedSettings path unchanged. Added normal/Custom at1100x740/820x560 regression: keepmenu openpast100msanchorcheck, invoke actualGreekchoice callback, verify sharedselectedcode/label,closeandreopen/noSettingsnavigation. Prior4fail7.59s:2normalclose-on-wrongviewport,2Customlabelassertions. After strongeractualcallback visualtree reader corrected (originalQObject-findChild4fail preserved),4pass7.76s. Original binding tests had onlySettingsengine lookup/Bridge setters and missed popupowner containment.

Language labels previouslyQLocale.nativeLanguageName:Greekscript/Russianscript/Runasimi are native names, notwrongcodes. NowEnglishQLocale.languageToString; providershortcodes retained, Qtunsupportedlocale fallsbacktocode ratherthanmislabelC. Greek(el)/Russian(ru)/Quechua(qu) andfallbackae labels checked; settings/runtimeprefs3pass1.98s. Catalogue is supportedISOselectorcodes, not a guarantee everyYouTubevideo offers everytranslation. MP4 independently selects evidenced originalmanual/automatic captions withOff, adds explicittranslation only whenavailable/matchedlang+tlang, validates embeddedstreams; playerreads embeddedcaptiontracks. Existing localfixtures prove acquisition/embed/transcode/parsing; no all-languageproviderclaim. qu429 remains actualupstreamsubtitle-fetch refusal.

Morph width/height/280ms/reducedmotion/quickselectdesign retained. Existing synchronous material renderer generatedlargepopupborder/blurredshadow perintermediate geometry. Popupopts into fixedexpandedrasterdimensions onlywhilecustomRevealintermediate, stretchescachedmaterials then restores actualendpointdimensions. StoneField/StonePopup optionalmaterialdimensions defaulttophysicalbounds everywhereelse. Existingnormal/reducedwidth+heightmorph test nowboundsactualshadow source changes:priornormal12uniqueupdatesfails/reducedpasses4.18s,afteratmost2.29affected Options/morph/preferences tests pass45.51s; finalstrengthenedmenu4pass andnewlabels3pass asabove. Sharedvisiblepixel/hiddenmaterialadmission2pass3.72s. Ruff/format/diff pass. Thisboundsmaterialwork, not a nativeframe-time/fluidityacceptanceclaim; no nativeprobe/download/build/launch/publish. No selection/export/providerchanges, locala24d076 preserved; currentlyopenf961497 apps doNOTcontain thissourcebatch. Native review of exactlatercombinedprivateartifact stillneeded, public0.2.5unchanged/0.2.6held. Receipts private-review-successor/subtitle-popup-before.log,morph-material-before.log,options-subtitle-morph-after.log,options-subtitle-binding-final.log(failedreader),options-subtitle-binding-v2.log,subtitle-labels-final.log,morph-shared-material-parity.log.

Combinedprivatef26cdb8 workflow38321698194: Windowssuccess/all4258localsealedfiles/sourceexact/archive80fc702b27252f3a163798a903a590858d86b2fcc542242772ee794cbaab11b7. ARMfailedbeforepackaging2Customsubmenuvisible assertions (True1100/820);754pass9skip1103.53s;originalbuild-failed-original.log retained. Intelcancelled/draftskipped. ARMwatcher3867 exit1/noartifact;Windows66563exit0. Notclaimedfixtureflakiness/rootcause;source/geometrydiagnosisneeded. No duplicatebuild/sign/nativeactions, foregroundreviewholdretained.

## Oct 13 — geometry-aware subtitle menu test, runtime unchanged

Cooper explicitly approved updating failedARMCustomsubtitle test/rebuildingprivateMacartifact. Controlledoriginaltest with instant/reducedmotion reproduces same2Customfailures/2normalpasses6.66s: originalanchor y566/546 vsviewport heights524/504 (40pxbutton), stalecontentY17/37 althoughsettledcontentHeight873. Animationendpoint didnotguarantee nestedpositioner/content geometrysettled; programmatic signalactivatedoffscreenanchor, which existingpopupguardcorrectlycloses. CIreceiptitselfhadnogeometry/reducedmotionstate, so controlledboundaryprovesdefectiveprecondition withoutinventing exactCIenvironmentcause. Noactualproductregressiondemonstrated; correctednormalowner productguard retained.

Testreusespolish_scene, scrollstargettrigger/languagechoice/reopentriggerintoview, assertsfullverticalbounds/centerhorizontalintersection/enabledvisibility, usesactualQTestpointerclicks (notactivatedsignal), retains150msmenu-persistence/Greekselectedcode/sharedlabel/close/reopen/Settingsabsencechecks. Snapshotgeometryprinted/saveonfailure. Normal/reducedmotion xnormal/Custom x1100/820 eightcases pass13.50s. Firstnewfixturechoiceparentwasnon-Flickable andfailed4TypeError; originalretained, readernowwalkstoactualcontentYowner; second4casespass7.26s before8matrix. Sourceproductsunchanged/Ruff/format/diffpass. Receipts private-review-f26cdb8/original-zero-motion.log/test_original_zero_motion.py,geometry-aware-first.log,geometry-aware-v2.log,geometry-aware-final.log. ExistingWindowsf26artifact runtimevalid4258sealed; do notrenameasnewtestcommit. OnlyMacARM/Intelprivateartifactrebuildneeded, existingpriorworkflowfailure/Intelcancel retained. No liveproviderdownloads/nativeinput/ordinaryappclosure/replacement/publication. Krydenheadlesspackage slotreleased/coordinateincomingARMsign; foregroundholdstillapplies.

Exactccb14edARMworkflow38325728703passed5924repository/37skip,760Qtcomponent/9skip,209scene,frozenruntimeSmoke.444MachOruntimefloors<=15/noerrors. DeveloperIDstrict/notary/staple/Gatekeeperpassed; immutablecandidate20261013T004254Z-6327f53a archivec33fa0dfb048ad6152676daf051c8bb373a15df4823832b62f096a3411035256. Factoryclean-commitrequires temporarily preserved documentationonlyinrecoverablestash506201f17448857b1baa81eaab70fd2166cc0dbd+bytecopy;finallyrestorebyte-identicalverified. Signer95581/freeze66487exit0/localslotreleased. Intelstillinprogress;existingWindowsf26artifactretained/no relabel. Noappclosure/replacement/nativeinput/publication; signing-policyeligibilitydoesnotliftholdorglobalreleasegate. Receipts private-review-ccb14ed/arm-job-original.log,arm-sign-notarize.log,arm-freeze.log,arm-qualified-summary.json,freeze-documentation-preservation.json.

Intelccb14edjob115063825876/workflow38325728703TERMINALPASS.5924repository/37skip673.07s,760Qt/9skip2156.00s,209scene527.37s,runtimeSmokeOK01:16:48.998UTC. Longelapsedphaseprogressed, no stuck-processblockerremains; priorlive-log404BlobNotFoundpreserved/notauthenticationloss. Exactartifact11783151106 downloaded; all6328regularfile/linkbytesmatchZIP/noextras/mismatch; archive62caf33163c4a8dd4b51ac01f9b902c7dab0e5254243c15e560d3e45fc09e04c, executable1a1297770c26bf284fe493c6bf4151907d2991793a73b3e22363833fb8605952.446runtimeMachOx86_64/floors<=15/noerrors;ad-hocdeepstrictsignaturevalid/TeamIdentifierunset, NOTDeveloperID/notarized/nativeIntelacceptance. EntireMac-onlyworkflowSUCCESS/Windowsanddraftskipped, no duplicatebuilds. ARMDeveloperIDcandidate retained/Windowsf26separatevalidruntimeartifact/notrelabeled. Receipts private-review-ccb14ed/intel-job-original.log,intel-job-terminal.json,intel-complete-binding.json,intel-runtime-floor-audit.json,intel-ad-hoc-verification.log,intel-qualified-summary.json. No appclosure/replacement/foregroundinput/publication;Krydenvoice-reviewholdretained.

Readonlybackend02:21–02:24UTC vs20:39UTC:176Workerrequests/0errors, D1quick_checkok/noFK/34schema+28migrations+deployment/settingsidentical/18reads0writes. Accepted4630→4664(+34,Mac0.2.3+13/Windows+21). NEWoneMac0.2.3attempt HTTPError403/downloadstage00:56:22UTC,2correlatedacceptedfailureevents/1attempt, no sameattemptlatercompletion; endpoint/rootcauseunproved, notbackendoutage. Publicsite/feed200/0.2.5;oneARMdownloadnotadoption. Knownvisibility/clock/outboxlimitsdeduped. InitialmonitorSQL102variable7500readererrorpreserved/correctedread-only, notprod-ingestion/accessfailure. Sanitizedbaseline build/recovery-20261011/backend-monitor-20261013T0221/REPORT.md/comparison.json/failure-diagnostics.json/alert-ledger.json/SHA256.json. No builds/nativeactions/dataproduction/deploy/access/credentialschanges;publicationholdretained.


## Oct 13 — Windows main-window drag-corrected displacement follow-up

Cooper confirmed Windows main window. Original25b full-frame pixels were inspected: native caption overlaps content/right-bottom paint stops short at96DPI; same-process resize and fresh same-binary launch correct it. Original blocked SW_RESTORE control remains blocked/unproved, no causal relabel. Current read-only SSH inventory03:52:30UTC finds exact privatef961 PID56632/session1. Direct HWND owner queries from SSH return0 and refuse further reads; initial signed-handle reader and pointer-corrected attempt preserved, current geometry/pixels/idle unverified. Qt Windows entry uses ordinary Window/content-fill, Cocoa-only backdrop does not explain this platform. Existing offscreen/logical/player-resize checks omit first native composed main frame/client origin; no redundant pass reruns or speculative product patch. Bounded disposable-profile first-visible-before-move/restore/resize and separate move/resize/restore controls documented in build/recovery-20261011/windows-frame-20261013/REPORT.md. Awaiting requested Windows availability; no native input, app close/restart, build, provider download, profile/display/security change. Kryden owned operations released but human review/prompts remain preserved. Sourceccb14ed/runtimeunchanged; public0.2.5/0.2.6 hold retained.


Independent frame source diagnostics: exact-incident user clarification directly says “Windows main window”; not inferred from Mac client or prior photograph. Private candidate windows-frame-20261013/test_qt_initial_frame_candidate.py uses actual Bridge/Main.qml, isolated profiles/offscreen/software;20cases pass across scale1/1.25/1.5/2 (9.27/7.34/10.60/7.71s). Initial pre-expose0x0 content reconciles after event delivery; resize exposes new QWindow/raster dimensions before content event delivery, then reconciles without drag; move-only and hidden/show restore pass. Injected X/Y/stale-width/stale-height controls are rejected. Original5failed candidate asserted before expose and remains preserved as fixture-precondition failure, not product reproduction. Signals/geometry/raster/DPR receipts retained. Ruff/format pass. Header drag only callsstartSystemMove; no Windows custom-frame source override found. No forced-resize/timer/DPI productpatch or source-fixclaim; nativeWin32/D3D/fullframe beforedrag/control remains pending Windowsavailability. No runtime/app/profile/publication changes.


Readonly production backend08:43–08:44UTC/Oct13 03:43–03:44CDT vs02:21baseline:28Workerinvocations/0runtimeerrors, D1quick_checkok/noFK/34schema+28migrations+deploymentidentical/16reads0writes. Accepted4664 unchanged/allversiongroupsidentical/no new acceptedfailureorrefusalaggregates; absence notfailed-delivery/rejected-event proof. KnownMac0.2.3download403same2events/1attempt/1installation, no later same-attempt outcome; dedupkeyretained/notify_againfalse. Site/feedGET200/public0.2.5/samecontentbindings;feedcounterbodyonlydelta5assetdownloads,12unattributeddownloadrowsnotadoption. ExistingHTTP/pre-ingestionrejection/clientoutboxcoveragegapsretained, no newaccessloss/outageclaim. Evidence backend-monitor-20261013T0843/REPORT.md,comparison.json,alert-ledger.json,SHA256.json. No secrets/events/mutations/deploy/access/GUIinputs/builds/publication;Windowsnativeholdretained.

Deployment comparison scope: current snapshotcontains10historicalentriesvspriornormalizedcurrentobject; initialaggregatefalse comparison preserved in comparison-first-full-list.json. Latestactiveid/versionpercentages/created_on exactlymatchbaseline; no deploymentchange. Reader-shape difference only; initial local normalization KeyError retained in tooloutput, no API mutation.


Readonly production backend14:57–14:58UTC/Oct13 09:57–09:58CDT vs08:43baseline:268Workerinvocations/0runtimeerrors, D1quick_checkok/noFK/34schema+28migrations+latestdeploymentidentical/19reads0writes. Accepted4664→4829(+165Windows0.2.5/2installationIDsnotpeople), maxclient/serverdifference575.725sclock/outboxambiguous. NEWsameinstallation updater check_started12:53:32UTC→URLError/network/analysisfailed12:53:33→genericupdaterfailed12:53:36, bothfailureattempt_idabsent; exactattemptcount/linkageunverified, no subsequentupdateroutcome. Appsidefailureacceptedbytelemetry, notbackendoutage/rejection/systemiccauseproof; parent singleevidenceepisode candidate. KnownMac0.2.3download403unchanged/deduped. Site/feed200/public0.2.5/samecontentbindings,5assetcounterdelta notadoption. Evidence backend-monitor-20261013T1457/REPORT.md,comparison.json,failure-diagnostics.json,alert-ledger.json,SHA256.json. No secrets/syntheticevents/mutations/deploy/access/GUI/builds/publication;Windowsnativeholdretained.


Bounded readonly updater investigation15:02:58UTC: automaticcheck/under10s, RuntimeError>URLError>other, sourceupdates.py102, networkreason; HTTP/errno/Winerror/TLSverify/failurecodeabsent. dimensions.update_attempt internallylinks1check_started+failed operation despiteattempt_idNULL; genericsummarydimensionabsent/directlinkunverified, sourceemitsadjacent summary. No recurrence/later updater outcome recorded. DefaultpublicpathGitHublatestrelease; actualURLnotserialized. Errorwrapperpreservesreasonclassmessage/raise-from; inspect_textfalse skipsfailurecodeclassification/unknownclassother; poll replacespreparedmessagewithgenericRepairguidance. Exactunderlyingreason/networkcategory/clientrequestcontextmissing, no DNS/TLS/outageguess. FourSELECTs0writes, threefilesunchangedvs0.2.5source850e19e (notclienthashbinding). Evidence backend-monitor-20261013T1457/updater-investigation/REPORT.md,metadata.json,source-excerpts.txt,SHA256.json; existingalertledgeraugmented/no duplicatealert. No fixes/tests/apps/permissions/deploy/publication; holdsretained.


## Oct 13 — failed update checks retain safe retry guidance

Approved local guidance correction separates release-metadata checks from installation recovery. Automatic/manual check failures now retain the app, clear pending install, expose Check again and Download page, and select constant guidance from structured network/rate-limit/HTTP refusal/service unavailable/TLS verification categories. Unclassified failures explicitly say the cause is unknown. Exception messages, private paths and sensitive URLs are never used in visible guidance. Download/verification/helper recovery retains its existing Repair behavior; no telemetry schema, permission, provider or install changes.

Existing popup state tests manually set recovery on a download error and did not traverse a failed metadata request. New real request-wrapper/worker/poll tests cover automatic and manual paths, privacy-safe guidance and a rendered pointer retry that returns to current state without invoking Repair. Original source fails14new cases in5.87s; retained before.log. Expanded final guidance18pass4.63s covers network/429/403/503/404/TLS/unknown; affected popup, verified update/handoff and update unit checks initially87pass/4skip with4sandbox-localhost failures. Only those socket cases rerun with read-only local-fixture permission:4pass/4platformskip2.32s. Unique affected result95pass/4skip; Ruff/format/diff pass. Earlier socket failure evidence remains intact. No broad campaign restart.

Receipts: build/recovery-20261011/updater-guidance-20261013/before.log,after.log,guidance-final.log,local-feed-socket-retry.log,qualification.json,SHA256.json. Source/offscreen/local-fixture evidence only: exact successor package/native popup/retry acceptance remains pending. Existing open binaries are unchanged, Windows/native holds remain, public0.2.5/0.2.6 publication HELD. No build/sign/deploy/publication or GUI input. Unrelated earlier log entries preserved unstaged; scoped commit includes only this new evidence section.


## Oct 13 — private packaged updater retry acceptance and separate subtitle/adoption evidence

Runtime fix f258221 is qualified in exact local ARM 9227134. Follow-ups 7b21989, 861ae92 and 9227134 change tests/build integration only: register the new Qt test in its partition, retain all maintained test roots including fine-tuning/tests, and correct stale owner-test preconditions. The first build was mistakenly interrupted after buffered progress (3,285 passed / nine skipped, exit 2); its partial receipt remains. The next build passed 5,919 backend checks / 38 skips but exposed two old Qt assumptions among 776 passes / nine skips. Tests now use actual repair admission and distinguish metadata failure from download recovery, retaining downgrade refusal, no-download, privacy, HTTP 503 and failed-helper assertions. An initially mis-targeted edit failed two tests among 34 passes; it was corrected, and all 36 affected checks pass. Runtime remains unchanged. Final maintained build: 5,923 backend passes / 38 skips, 778 Qt passes / nine skips, 209 scene passes, packaged runtime smoke passed.

Developer ID signing, notarization, stapling and Gatekeeper passed. Archive SHA-256 4c723723b34bff012b3db79955d85946541a62b21379d4d74985198e5beecf18; executable SHA-256 165b5a522c33263eabb31d741f7db99f54778da84927a62998058379ff507951. All 6,327 sealed files/links bind without extras. Actual isolated, denied-consent native PID 78842 received automatic then manual 503 responses. The popup rendered Update check unavailable, constant service-unavailable guidance, Download page, Close and Check again, with no Repair. After the disposable feed returned 200, one pointer click on Check again rendered up-to-date. Normal popup Close/Cmd-Q exited 0 at 16:40:51 UTC; zero owned private/signing/fixture processes remain, and bundle tree is unchanged. Production telemetry was attested false; consent stayed denied and no outbox was created. This is metadata retry proof, not install/Repair transactions or Windows network-cause proof.

All 444 runtime Mach-O files were readable, but local Homebrew dependencies declare a highest minimum of macOS 27 on the current 27.0.1 host. The <=15 assertion FAILED and remains preserved. This package supports private current-host acceptance only; public supported-floor qualification requires a hosted successor. No binary minimum commands were altered. Public remains 0.2.5 and 0.2.6 publication is HELD. Previously uncommitted documentation was restored byte-for-byte after build provenance was recorded; recovery stash remains. Receipts: build/recovery-20261011/private-review-f258221/REPORT.md, qualification.json, SHA256.json, original build/sign/floor logs, failure/success screenshots and AX, feed requests, launch/exit/startup attestation/process/bundle proof.

Separate signed ccb14ed subtitle lane, with unchanged subtitle pipeline, is not f258 packaged acceptance. French manual fr (The Egg) and Spanish manual es (vaccines) produced playable 360p H264/AAC outputs with original/translated mov_text streams, 152 French and 87 Spanish cues; full AV decode passed and native playback was observed. German automatic de (Rick Astley) subtitle fetch returned 429 and truthfully Failed with no output, retry or substitute; specific Issues guidance was visible. Three actual media attempts, once each; the previous Runasimi source was not retried. Normal exit 0 at 16:09:55 UTC; no VOD process remained. Onscreen selected-track rendering and automatic-translation success are unproved. subtitle-sample/REPORT.md, media-verification.json, sample-results.json and SHA256.json bind results and retain earlier harness errors.

Read-only production update-adoption snapshot: 5,406 accepted events / 63 identities, September 5–October 13 at 15:38:43 UTC. Seven-day active consenting denominator: 10 identities, six old (two Mac/four Windows), four current 0.2.5 Windows; not people or customer conversion. Five old identities with latest availability report resolvable revisions c6684b2, 410dddc and 55e4073. All support shown/update_attempt telemetry and keep automatic offers hidden in Settings. No shown/later-download evidence on the five; this does not establish refusal or loss. Strongest source-supported recommendation is a persistent non-blocking Update available entry opening the existing updater and preserving active work/Later. No adoption UI was implemented. Customer/private-QA classification, independent binary binding and session-to-operation linkage are unknown; population causality is unmeasured. update-adoption-20261013/REPORT.md and API/SQL/source/SHA256 receipts preserve the analysis; zero SQL writes.

Native/heavy resources are released and Kryden owner was notified. No ordinary app control, permission/security change or prompt interaction. Windows frame reproduction hold remains unchanged.


## Oct 13 — persistent non-blocking updater entry, locally approved

Cooper explicitly approved local implementation after the read-only adoption diagnosis. Main.qml now places an Update available entry beneath the shared header, outside page scrolling. It follows existing availability/manual/recovery/check-failure/download/ready/handoff state, does not open automatically, and disappears when a successful check says current. Explicit opening uses the existing popup without invoking a check, download or restart. Later retains the entry; repeated clicks while open do not reopen or create duplicate work. No new updater owner, telemetry schema or network route.

Existing popup tests manually opened the offer and missed ordinary discovery. New bounded cross-owner coverage verifies automatic check/poll availability and current transitions, all four routes at 620/1100 widths, actual pointer repeat/Later/reopen, Return/Space activation, existing operation-boundary shown deduplication, unchanged active/queued jobs and 11 owner states. Prior source failed two discovery cases in 8.03s. First implementation run: 29 passed / four failed in 21.52s retained: reader used wrong settings object name and unused observations list; corrected to actual object and operation boundary, not product assertion removal. Focused: 33 passed in 27.07s; strengthened discovery/keyboard: four passed in 6.32s (two strengthened cases plus two new), 35 unique affected guidance/notice checks. Existing popup/recovery/verified handoff: 42 passed in 21.70s; 77 total unique affected passes. Ruff/format/diff pass. No broad build/CI campaign repeated.

Tests use isolated HOME, disabled telemetry, stubbed metadata and no provider/paid calls. All GUI tests are offscreen: no native foreground input, packaging/signing, ordinary app closure, permission/settings change or deployment. Kryden notified of source/offscreen-only scope. No native/B.Edit lease needed or taken. Exact successor package, native visual/physical input and measured adoption effect remain untested. Existing signed 922 artifact lacks this entry; no predecessor relabel. Public 0.2.5 remains; 0.2.6 publication HELD. Evidence build/recovery-20261011/update-notice-20261013/before.log,after-first.log,after-v2.log,discovery-keyboard-final.log,recovery-affected.log,REPORT.md,qualification.json,SHA256.json. Earlier uncommitted documentation remains preserved and unstaged.


## Oct 13 — exact update-entry private package ready, native lease pending

Parent requested continuing889c046 through private package/native qualification. Kryden explicitly released headless slot; maintained packaging segment reused with77 valid affected checks, without broad campaign restart or predecessor-test relabel. Exact embedded889 revision and packaged Main.qml bytes match. Runtime smoke, DeveloperID strict signing, notarization, stapling and Gatekeeper pass. All6327 sealed files/links bind/no mismatches/extras; archive6b0843c42c8f97ef5c4cc24dab5ba361a6f63a2d335969467488f3e1cfd386fc, executable738ab0e02b027a8bc5ca09d401b3b7b0079e072e5dcfc2570d350e86bf1d4dbd. Fresh444 MachO audit remains highestfloor27, <=15FAILED/preserved; current-host private artifact only, public held. Uncommitted log preserved recoverably for clean provenance and restored byte-for-byte; stash retained.

Original B.Edit owner had no native lease. Parent identified new collector01a13648-c504-74e6-8d3c-cf10f63bc0e2, which explicitly requested protected bounded Messages/Bebe review. VOD native launch/input is HELD until its explicit release, then Kryden short identity interval, then VOD fixture. Owner coordination acknowledged; headless VOD slot released. Existing app/profile/prompts untouched; no actual new native observations claimed. Prepared denied-consent loopback fixture serves availability metadata/prerecorded local media and controlled metadata/verification failure, never an installer. Report/checkpoint/binding at build/recovery-20261011/private-review-889c046/.


## Oct 13 — bounded packaged update-entry acceptance complete

Exact 889c046 signed/notarized/stapled ARM package verified actual visible automatic entry, no automatic modal, Shift-Tab/Return/Space, Later persistence, reopening and repeated-click stability. Controlled checksum 503 retained existing Repair recovery; metadata 503 kept safe retry without Repair; current retry removed entry. Initial direct-MP4 fixture failed format admission before download and remains preserved. Corrected localhost HLS explicit stream metadata admitted one real run; it stayed active through offer interactions and verification refusal, then naturally completed under the same run ID. Output 640x360 H264/AAC, 486.040s, full AV decode exit 0, SHA-256 cf39adb14f51a9a37880d16d8999ddd8c872e7867376d465514f8850fe1550e5; zero staging. Both app instances normal Cmd-Q/exit 0; final 13:11:11 CDT, zero survivors, signed tree unchanged. Native interval released to B.Edit/Kryden notified; ordinary apps/profiles/security untouched.

Stale AX capture index opened Window menu, cancelled and Later repeated correctly. Late active-ledger assertion raced natural completion; original idle ledger retained, independent active/transcoding snapshots and completed same-run history bind outcome. No relabeled generic E2E/installer/Repair-success proof. Public 0.2.5/0.2.6 held; runtime floor 27 and Windows/Intel/narrow native/interleaving/adoption limitations remain. REPORT.md/qualification.json/SHA256 and original evidence under build/recovery-20261011/private-review-889c046. After completed verification, unified exec command transport disconnected; final receipts were written via filesystem-only native runtime, no further GUI input.


## Oct 13 — compatible-input macOS private ARM qualification

Parent authorized independent compatible build diagnosis with Windows explicitly unauthorized. Original889 local runtime floor27 comes from Homebrew OpenSSL/libvmaf, with Python/FFmpeg26; no intentional support policy selects26/27. Existing pinned PySide/CI builder baseline makes15 the engineering target, not older-OS support acceptance. Isolated existing standalone Python3.11.15 plus retained immutable-CI-verified FFmpeg dependency inputs and pinned PyPI requirements produced fresh889 private ARM packaging. First final audit found host SQLite26 despite other inputs<=15; originalfailed audit/library retained. Explicit immutable-CI-verified SQLite input corrected fresh package:384 Mach-O/max15/zero scan errors/no external non-system absolute links, matching LSMinimumSystemVersion15. No load-command target lowering.54 affected updater pass/18 platform skips;6 real encode/probe/decode pass; Python+Qt SQLite transaction checks pass after retained missing-QCoreApplication fixture error; frozen smoke and packaged High H264/AAC export/probe/full decode pass.6256 sealed files/links bind/no extras, strict ad-hoc signature pass. Current-host only/no GUI/olderOS/Intel/Windows acceptance. Original accepted bundle intact; all owned jobs terminal/no process matches.

Automatic approval review REJECTED Apple notarization disclosure using existing credentials before execution; no upload/retry/workaround. Explicit user approval question pending; bounded local ad-hoc package ready. Exact compatible artifact archive25807153130071aac597441cc07e6b172c7f4b7c09144a754f0d8fa9274d8b24/executable63e62427aab9b82b2145d0cb7e0b7be33e74ec4bbd64c92354b4af9e385a8a44. REPORT.md/qualification/input/failed+passingfloor/media/archive/approval/SHA receipts at build/recovery-20261011/macos-floor-20261013. No public release/deploy, permissions/security changes, native input, provider/paid calls or unauthorized Windows access. Public0.2.5/0.2.6 HELD. Exact remaining native Mac15/Intel/Windows main-frame/update/Repair/physical interaction tests documented; no broad campaign repetition. Earlier uncommitted documentation preserved.


## Oct 13 — authorized compatible private Apple notarization complete

Cooper explicitly approved the exact private Apple upload18:38UTC. Preserved ad-hoc archive/tree hashes verified before one approved retry; no approval text injected into the tool request and no bypass. Existing secure identity/profile only: Developer ID strict signature, Apple terminalAccepted (767661de-140a-4b7c-9d1e-ec45b701eecb), staple validation and GatekeeperNotarizedDeveloperID pass. Signed384-file audit remainsmax15/zero errors; marker889/QML unchanged. Final6257 sealed files/links bind/no extras; archivec605fc2529de91fa8e7d432c7b417eb28320b222a5fa916b78cd533836d6941e/executable100d1fff6e22d4471fb300a60742b41c91a14ae7865f06a3f3c71f6eb03d1054. Isolated hardened-runtime smoke exits0; exact signed/stapled bundle tree unchanged afterward. Read-only process check no owned package/sign/notary/smoke processes; slot released. Original rejected-review receipt, ad-hoc archive/binding, failedSQLite26 audit and original failures preserved; REPORT/qualification/checkpoint/SHA updated under macos-floor-20261013. No native launch/input/ordinary app or profile replacement, new credentials/security changes, Windows access/public deploy/release. Mac15/Intel/Windows actual runtime and signed Update/Repair transaction/physical interaction gaps remain; public0.2.5/0.2.6 HELD.


## Oct 13 — scheduled20:38UTC read-only production backend check

Actual authenticated observations20:40:38–20:46:17UTC, public20:41:17–18 vs14:57 baseline. Worker1251 invocations/all success/0 runtime errors; D1quick_checkok/noFK/34exact schema/28migrations/latestdeployment+releaseadmission unchanged;25 SELECT/PRAGMA/0rowswritten/changed_dbfalse. Accepted4829→6055(+1226:Mac0.2.3+1201,Mac0.2.4+13,Windows0.2.5+12), identifiers not people/adoption. NEW Mac15:44:29–15:45:11receipt HTTP403/download13diagnostics under1attempt/1installation; no same-attempt completion, later16exports+1completed underanotherattempt notrecoveryproof. NEW Windows17:28:39–41receipt DownloadError operation+run_failed under1attempt; reasontranscoding/stagedownload, HTTP/causeunknown, no later same-attempt completion. Both app failures accepted, notWorker/ingestionrejection. OldMac00:56:22 unchanged/deduped; oldWinupdaterURLError alreadyreported, NEW later independent same-installation check_started/current16:48:40/47 receipts, no originalcause/sameattemptrecoveryclaim. Latestaccepted17:28:41→3h11m57absenceatprimaryread; expectedactivity/requeststatus/outbox unavailable, notfailed-deliveryproof. Newmaxclock/outbox offset492.619s withinprior575.725. Site/feed200/public0.2.5/sitebytes+artifactbindings unchanged, +8assetcounters/8trackedrows notadoption; no binary/trackedroute GET. Raw tool schema/versionarray truncation preserved, bounded34SQLexactcomparison+compact15-groupcounts correctedreceiptdefect; no schemachangeinference. Evidence backend-monitor-20261013T2040/REPORT.md,comparison.json,API/SQL/public/diagnostic/ledger/SHA receipts. No usernotification/externalmessage, secrets/events/writes/deploy/access/UI/build/publication/Windowsinput; parent ownsnotification. Earlier log/uncommitted work preserved.


Oct13 media-incident clarification20:52:31–20:55:29UTC:3successful scoped aggregate SELECTs/0writes, no rawIDs/privateURL/title/message/content/secrets. BOTH media downloads, provider categoryYouTube fromsame-attempt intent, notappupdates; exactfailinghostnameunrecorded. Mac0.2.3MP3/cookiesdisabled/CPU,13HTTP403failures across13operationIDs under1outerattempt/1installation, client15:40:44–15:41:30/server15:44:29–15:45:11Oct13; not13users/retries/outerruns. Windows0.2.5MP4CTV/cookiesdisabled/CPU,1operation+run_failed/sameattempt, client17:20:32/server17:28:39–41Oct13; DownloadError>other/reasontranscoding/stagedownload, noHTTP/failurecode/toolExit/cookieerror; encoder/causeunproved. Known850e19e callbackapp2787 processespreflightmedia; FailureDiagnostic sourceunchanged inprivate889. Noevidence eitherfixed; updaterchangesunrelated, no recordsubtitle/429/unavailabletargetmatch, MacMP3notMP4subtitleissue. Cookiesoffnotcausalproof/nosettingchange. Sourcecomparisonnotindependentclientbinarybinding. Evidence backend-monitor-20261013T2040/incident-clarification/REPORT.md/metadata/counts/source/SHA. No newincidentnotification/message, productionmutation, retry/download/UI or publication. Earlierrecords/workpreserved.


## Oct 13 — scoped release checklist and Air SSH route inspection

Current889 compatible package changes the Python/Qt/SQLite/media dependency inputs,
so retained ledger source checks were rerun only in that isolated runtime:
tests/test_qt_history_startup.py11pass1.39s (offscreen/software), preserving
malformed main/schema999/malformed pending refusal bytes and valid absence
behavior. Original log release-checklist-20261013/compatible-ledger-source-original.log.
No GUI/platform acceptance substituted; older0b validated unaffected invariants
remain scoped predecessor evidence, while current compatible final-binary native
acceptance remains pending. No broad campaign restart.

Air inspection confirms Windows SSH transports commands/files into an Interactive
Limited scheduled task with locked/session guards. Maintained macOS native_input
and native Intel startup runner provide the QA layer; a remote SSH-to-Aqua route
still needs reachable authorized authentication, logged-in/unlocked session and
actual responsible-process Accessibility/capture permission verification. Offline
Codex environment is not proof SSH unavailable; no Air network/auth/UI attempt,
key/RemoteLogin/grant/agent/credential change. Intel requires fresh current889 x64
artifact; ARM cannot qualify it. Evidence air-ssh-route-20261013/REPORT.md.

Parent authorized exact compatible ARM acceptance after B.Edit/GLU native release.
Separate disposable compatible-native-889c046 fixture/plan prepared; no native
launch/input yet, signed artifact untouched. Existing local media/localhost only,
installer deliberately refused; ordinary profiles preserved. Windows20offscreen
passes and before/after pixel reproduction remain valid but do not establish
DWM/client-origin cause. No speculative DPI/forced-resize edit or duplicate test.
Public0.2.5/0.2.6 publication HELD; earlier uncommitted documentation preserved.

Compatible-runtime player follow-up:11resize-continuity/presentation-return source checks PASS14.29s under isolated compatiblePython/Qt offscreen/software; two existing rotation deprecation warnings. New dependency inputs justify this bounded repeat; not native final-binary/fullscreenSpace proof. Original player-compatible-source-original.log under compatible-native-889c046. No product edits or foreground input.


## Oct13 — exact compatible ARM partial native acceptance; tool interruption

Actual signed compatible889 startup/Options shared metadata summary/update offer
Later/checksum503Repair recovery pass. Controlledmetadata503Checkagain/current
retry pass while actuallocalHLSMP3active+MP4queued; actualMP4cancelStopped and
independentMP3automaticqueuehandoff pass. Nativecorecompletion/playback/fullscreen/
restart/installtransactions remainUNPROVED: tool/sessionreset interrupted24351,
exec86759unknown/noexitreceipt. OriginalfailedQAcontainment/directMP4preflight/
HLSoutputguard attempts retained; correctedfixtures do notrelaxproductguards.
CUApostquitobservation/resetreattachment reopenedcandidateordinaryprofile23595/
25051; bothidle normallyCmdQclosed, nosetting/mediaactions, ordinaryprofilehash
preservation notattested. Exactbundle/exe unchanged; originalscreenshots/logs/
journals retained. NoownedVOD/fixtureprocess remains; explicitnativerelease toCTV
owner01a13648, nofurtherVODinput.12seclocalstreamcopyfixture independentlyprobe/
decode0/hashbound forremainingbriefcorequalification, notnativelyusedyet.
Evidence compatible-native-889c046/REPORT.md,qualification.json,fixture-errors.json,
bundle-after-interrupted-native.json,originalpartialandpassingreceipts. Public
0.2.5/0.2.6HELD; no source/security/production edits ornewproviderdownloads.


## Oct 13 — fresh exact compatible ARM native core acceptance passed

After CTV's explicit release, fresh isolated PID26610 completed CPU H264High/AAC
640x360 MP4 and independently queued MP3. Probe and full decode both pass for
both outputs (12.12s MP4;12.010667s MP3). Actual native MP3 advanced288→5736ms/
paused6048ms; MP4 rendered6337ms and retained natural-end frame. Fullscreen
retained-frame presentation→Escape embedded return12120ms passes. Native zoom
changes2200x1480→2880x1636→2200x1480 with retained frame/layout; corner drag
unchanged dimensions is NOT resize proof. Initial fixed-PNG-header audit was
invalid because CUA captures JPEG; failed interpretation retained, actual formats
and dimensions independently validated without changing image bytes.

Cmd-Q26610exit0; normal restart27436/same isolated profile shows two Completed
runs; four history/media/metadata hashes match across restart/final quit and zero
staging files remain. Cmd-Q27436exit0; read-only process check no owned app/feed.
Exact sealed bundle/executable unchanged. Original interrupted journey/fixture
errors/ordinary-profile tool side effects remain separately preserved, never
backfilled or adopted as isolated acceptance. Native slot explicitly RELEASED
to CTV/Kryden; no further input/build/sign job. No product regression established.

Evidence compatible-native-889c046/REPORT.md,qualification.json, native-output-
verification.json, native-image-geometry.json,bundle-after-fresh-native.json and
raw two-launch AX/pixels/feed/exit/preservation receipts. Compatible payload
successful Update/Repair, older OS/Intel/Windows and physical timing remain
untested; no broader release claim. Public0.2.5/0.2.6 HELD. No product source edit,
external provider download, grants/security change or deployment/publication.
Existing uncommitted documents and original failed receipts preserved.


## Oct13 — compatible889 actual Update/Repair transactions

Private retained official0.2.5 Update→exact compatible signed889 PASS: originalhelper repairfalse relaunch/exe/treeexact, sevenhistory/media/metadata/thumbnail hashesunchanged. ActualsamepayloadRepair PASS afterfresh normalparent022 launch/newhelper repairtrue/exactexe+tree/sevenhashes. FirstRepairexacttreefailure preserved: QAhelper direct executable inherited077 changed1737symlinkmodes755→700;sealedbytes/targets anddataunchanged. No manualbundle normalization. Prior0b normalenvironmentreceipt motivatedboundedrepeat; no broadcampaign. Firstobserverhandoffracefailed; independentcompletedrelaunchpass. Finalapp visiblyverified thenCmdQ/processabsent (finalexitcodeunobserved), ownedfeedSIGINTstopped; frozenarchive/exe/treeunchanged. Native/heavyslotsreleased. Evidence compatible-update-repair-889c046/REPORT.md, after-update.json,after-repair-normal-environment.json,final-release.json.

Airexplicitjulie@100.84.96.112 strictreadonlySSH reachedserver butfirst-seenED25519unknownhosttrustblocked beforeauthentication. Advertisedunverifiedfingerprint SHA256:yhz4A4VDiG56DcVGv7FL5rB+pACW/Pwcf2asWsioVZ8; no trustedexpected fingerprint/knownhostwrite/securitychange. Userlocalcomparison/securefirstconnection approvalneeded; remoteOS/session/TCC/Intelbuildnotreached. Evidence air-ssh-route-20261013/preflight/result.json. Windowsframecauseremainsunconfirmed. Public0.2.5/0.2.6HELD; no sourceedits/publication. Earlieruncommitteddocumentationpreserved.


## Oct14 — Windows first-frame readiness audit; no repeated source tests

Read-only retainedreceipt/scriptaudit at889c046 found originalbeforecapture
skipped (anotherforegroundPID) and originallaunchalreadySW_RESTORE; fresh
correctfocus-onlylaunchstillraises; restorecontrolrefusedactivework. Existing
20logicalgeometrypassesremainvalid/unrepeated, noaffectedsource/envchange.
Sourcecandidate/nativeprotocolprepared; historicalordinaryprofilelaunchers
arecontrols/reference, notdisposablepre-activationfirstframeprotocol. Precise
gateinwindows-frame-20261013/first-frame-readiness-audit-20261014.json andREPORT.
Causeunconfirmed/noproductfix; noWindowsoperation/Macforeground/sourcepatch/
frozenARMchange. Nativepre-controlfullpixels+Qt/Win32bounds/eventorderrequired
beforeminimalcorrection. Parentrefinement honored; duplicateworkstopped.
Public0.2.5/0.2.6HELD.


## Oct14 — Windows route access dependency

Local retained scripts verify SSH→Interactive/Limited console task route with
account/session/unlocked/idle/native-owner guards. Coordinator00:37UTC reports
connected but taskauthorizationfalse; no independent environment-list tool here.
No remote attempt/denial bypass/access change. Current explicit environment/route
authorization is first dependency, then existing authentication/session and idle
checks. Source20checks unrepeated; fresh-firstframeprotocol held. Evidence
windows-frame-20261013/windows-route-access-dependency-20261014.json.


## Oct14 — actual Windows SSH first-launch/restore controls completed

Cooper corrected route: allWindowsworkviaexistingSSH/Krydenreleasekey. Actual
strict-hostSSH succeeds COOPS-PC\Coop activeconsole1. Previous desktopflag
blockerinference incorrect; priorreceipt preserved. StandingworkflowAGENTS
recorded; no credentials/security/accesschange. Idlejournalstateidle/queue0
verified despitepresence-only oldguardfalse; noUIbusy/children. Existingf961
56632neverclosed/operated. Exactsigned25b private57600firstvisibleblanknative
capture thencorrectcomposedheader/fullclient BEFOREnativecontrol; lateRestore/
move/resizecorrect. Private56560earlyRestore beforefirstsettledQtframe also
correct. Both96DPI/1100x740/offset8,31/Qtframetop31; pixelsSHA/dimensionspass.
Normalclose/WaitForExittrue, exitcodeobjectsnull (no0claim); independentonly
ordinary56632remains, ownedtasksretired. NineordinaryJSONhashesunchangedboth.
Causeunconfirmed/notfixed; restorehypothesisnotreproduced. Originalbadframe
retained. LimitsfirstblanknotQtpaint/subframeunmeasured/privateprofilecontext/
old25bnot889qualification/onephysicalscale. No20sourcecasesrerun/sourcepatch/
Macforeground/frozenARMchange. Evidencewindows-frame-20261013/ssh-native-20261014/
REPORT.md,qualification.json,native-result.json,early-restore,normal-release.json.
Public0.2.5/0.2.6HELD. Nativeownedslotsreleased.


## Oct14 — exact889 Windows-only signed qualification started

No exact889 Windowsartifact existed. Added narrowly scoped privateWindows-only
selector and optional40hex sourcepin to maintainedreleaseworkflow; existing
signer unchanged, non-privatecheckout/publishingguard unchanged.22workflow
checks pass;2newcases failagainstpriorworkflow;Ruff/format/diffpass. Workflowonly
commit0eac7fc pushedexistingqt-retirement; payloadsourcepinned889c046. Private
run38492450524 active actualBuildWindowsinstaller; Macjobconfirmedskipped,
artifacts_onlytrue/publicreleaseHELD. No broadsource/Maccampaignrestart.
PreparingexistingguardedWindowsnative/UI/updateharness withisolatedprofile/
localHLS, preservingrunningordinaryf96156632. No exact889nativeinput yet.
Evidence windows-private-889c046/execution-plan.json/workflow-prior-failure.json.
Earlieruncommitteddocs preserved; no source/runtimeedit/frozenARMchange.


## Oct14 — architecture aggregate/support assessment and website OS CTA

Four authorized readonlyaggregateSELECTs reusesnapshotrowid5406/Sept5–Oct13
15:38:43UTC:63observedinstallations42Windows/21Mac. Mac2arm64process-only,
19missing/0x64observed; NOT0Intelusers. Windows14x64/28missing. Newer0.2.3+
app-openOS+archpresent;oldversionsmissing. process.machine cannotdistinguish
Intel/Rosetta;proposeboundedhardware/translationfacts only,notimplemented.
No rawIDs/IPs/secrets/messages/schema/deploy/events;rows_written0/changed_dbfalse.
Evidencearchitecture-usage-20261014/REPORT.md+rawaggregatequeries. Global
latestreleaseexactversionx64filenamecouplingmeansARM/Windows-onlypromotion
wouldremoveIntelautomaticpath;independentqualificationrecommended,nopolicy/
feed/publicationchange. AppleWWDC25TahoeIntelphaseoutprimaryreferenceread.

UserselectedhomepageOSforegroundCTA implementedincanonicalvodforge-site
throughapprovedfilesystemescalation (delegatedwebsite_os_download). Windows
installer/Macexplicitchipchooser+AboutThisMac/mobileemail/unknownfallback;
allbelowfoldchoices preserved.13focusedOS cases,Astro82filescheck/build,8
headlessactualfull-pagecontexts/dialogfocus/responsiverestorationpass. External
APIunavailablemock/noPOST/noexecutabledownloads;allownedheadlessprocessesclosed.
Fourcanonicalsitefiles uncommitted, no sync-release/commit/push/deploy/feed/
publication. Liveemaildeliveryuntested. Report+canonical-final.patch under
website-os-download-20261014. Macforegroundnever taken. Exact889Windows
CI38492450524 updaterjourneyawaited independently;no889nativeresultyet.


## Oct14 — Windows signed artifact recovery after unavailable hosted gate

Original38492450524 updater began01:01:12UTC, stillactive01:40:37. Officialgh logs unavailableuntilcompletion;originalerrorretained;no889nativeacceptance/artifact. Workflow-only1ba2653 addsprivatepre-gate signedupload and40minute privategatebound, preservesproduction+legacy/publicguards.23affectedchecks pass/newcasefailsprior/Ruffformatdiffpass. Recovery38497177265 pinned889 started01:42;Macskipped/publichold. Necessaryrebuild becauseoriginalsignedbytes inaccessible, notvalidacceptancerepeat. Originalnotcancelled. Nativeharness/privateprofile/media staged;ordinaryf96156632 untouched. Evidencewindows-private-889c046/CHECKPOINT-20261014-0144.md;noMacownednative/heavywork.


## Oct14 — exact889 Windows artifact and native acceptance underway

Recovery38497177265 terminalsuccess;production+legacy updaterreceipts bindinstaller3140af51/exe700c2825/source889 andvisibility1530/254ms. Original38492450524 terminalfailure: officialannotationhostedrunnerlostcommunication;underlyingreasonunknown,lognotfound/noactualinstallerstallclaim. ExactZIP7d7efa5f resource889/version0.2.6;PC4258memberbytebinding andbothKrydentimestampedValid signaturespassed. Native53788 launched01:57:34; earliest+settleduntouched96DPIframesnormal/notshiftfix. ActualquickOptions+YouTubechoices,MP4/MP3exports,MP4frame,mute/fullscreenEscape/mainmaximize-restorepass. OwnedscheduledPowerShellfocus refusals retained;harness distinguishesexactworker/selfinputticks fromhuman/foreignforeground;10secondprior-taskwaitavoidscommandoverwrite. Ordinaryf96156632untouched/9JSONfreshbaseline. Captionfilespairedbyte-for-bytewithgenuineoriginal-rolemetadata+localthumbnails/noproviderduplicate. Nativecontinuing;noMacforeground/publicchanges. Evidencewindows-private-889c046/*.json/ci-update-evidence.


## Oct14 — exact889 Windows native core, restart, Update/Repair and normal release

Completed 2026-10-14T03:21:41.138779+00:00. Four actual exports + one saved-caption import fullprobe/decodepass; nativeOptions/cookiechooser/playback/mute/fullscreenEscape/maxrestore/English+Frenchseek/cancelStopped+automaticqueue pass. ExplicitquunavailableFailed/nooutput; sameURL OffCompleted. Sevenruns/fivecompleted retainednormalrestart; all14durablehashes unchanged restart+actualofficial0.2.5Update+samepayloadRepair. Originalhelperreceipts bothinstaller0/relaunched exact700c/source889, repairfalse/true; actualupdated/repairedGUI visible.4258sealedmembersmatch;931byte-identicaloldbaselinefiles+2uninstallerextrasretained, notexactdirectorytree. Core/restart/finalnormalclose0; bothservers0;3ownedReady tasksremoved/no survivors/staging. Ordinaryf96156632 unchanged/open;9JSONsame/39profilefiles+normalbinary unchanged;registration/shortcuts restored. Historicalshiftnotreproduced96DPI, nofixclaim; initialbaseline081firstframecapture refused/retained. RecoveryCI38497177265 success; originalrunnercommunicationfailure retained/underlyingcauseunknown. No broad rerun/source edit/publication. Public0.2.5,0.2.6HELD. Evidence windows-private-889c046/REPORT.md+qualification.json+originalhandoffs+finalcleanup. Scheduledhealth latest20:46monitorreused, no duplicatefailurealert;two laterWindowsupdatercheck/current, Worker0errors/D1integrityschema+migrationssame/public200. Website reference patch9headlesscontexts qualifiedunpublished;IntelAirtrust/supportfeeddecision unresolved. All owned resources released; noMacforeground used.


## Oct14 — IntelAir authenticated Tailscale route correction

SavedserverbannerTailscale;OpenSSH/etc/sshfingerprintrequestwrongroute/withdrawn. ActualauthenticatedstatusbindsonlineJulies-MacBook-Air100.84.96.112;existingtailscalesshcoordination-serverhostverificationpassed/nohostcheckdisable/noACLkeycredentialchange.03:37:44–45actualreadonlyremotejulie/x86_64/macOS15.8.1/consolejulie/exited0noreauth. ExistingCLT/Python3.9.6/Aqua/425GiB;systemPythonSSHSDKfalseAX/screen/zero requests,notfuture-app proof. PrivateIntelonlyrun38507530444 at1ba2653(workflow/test-onlydiffsince889runtime)started/noARMWindows/publiccampaign;Intelgatepassed,packagepending. Evidenceair-tailscale-route-20261014/REPORT.md+originalstatus/connect/SDKreceipts. PreviousunverifiedOpenSSHreceiptpreserved,nativeinputpausedpendingexactroutepermission.


## Oct14 — bounded dashboard claim reconciliation

Saved receipts plus one authorized aggregate zero-write SELECT reconcile fixed rowid5406/Oct13 15:38:43UTC: 10 seven-day identities (4 latest/6 older), 44 thirty-day (4 latest/40 older),37 no-event registry identities unknown.59 historical latest-event older identities is supported,25 specifically0.2.2; CRM actual query absent/no first-run mislabel established. Four updater_failed events/2repair_started/no observedrepair_completed; recent Windows diagnostics oneattempt. Click-to-launch cohorts unjoined; intent/WAU/waitlist/monthly claims unverified without originalqueries. Saved publicARM primaryfloor26/archive270.44MiB and nearbycardrequirements documented; unpublished OS choices qualified separately. Minimalbrowser/claimtransport recommendation only/no newcollection/Pro/deploy. Evidence dashboard-claims-20261014/REPORT.md+originalboundreceipts. Intel38507530444 stillsingleactiveunsignedbuild; novalidcheckrepeated.


## Oct14 — exact private Intel sign and physical Air bounded qualification

Intel38507530444 terminalsuccess52m30s:9hover/5927repository37skip/795Qt9skip/209scene/frozensmokepass; source1ba/workflowtest-onlydifffromruntime889. All446runtimeIntelMachOfloors<=15.0. ExistingDeveloperID/notaryaccepted64bff5b6/staple/Gatekeeperpass. Finalarchive9e92404a/exee23f1365/all7290sealedentries verified onphysicalx86_64Air15.8.1. Frozenruntime+ffmpeg/ffprobe/deno+actualHighAAC/320kMP3encode/probe/full decode pass. Firstdirectnative20secwindowreceiptFAILEDpreserved, normalexit0; actualSSHCGSessionnull/allwindowcounts0, notproductcause/permissioncure. JustifiedordinaryLaunchServices followup(noheadlessrepeat) attests3.82sec/exactapp/AppKitfinished-active-not-hidden; normalclose/open-W0. Profilesunchanged;final7290entries/archive same/noownedapps. Windowpixels/input remainunqualified; earlierSSHSDKfalse isnotGUIgrantrecipientproof/no grants. Report intel-private-1ba2653/REPORT.md+originalreceipts. Userrequestedlocalwebsite/newChromehttp127.0.0.1:4323 visiblyAX+pixels loaded, canonicaluncommittedOSpatch/server3775retained,CTVtabs/profile preserved/nativelease released. Dashboardcohorts separatelyready; public0.2.5/0.2.6HELD/no pushdeploy.


## Oct14 — authorized Intel graphical-context boundary

Existing gui/501 disposable observer bootstrap/normal retirement passed; nativeSDK session present/11on-screenwindows, ScreenRecordingpreflightfalse/AXfalse/no requests. JXA absentSDKexport and earlier driver pre-execution quoting failure preserved; corrected ctypes observation worked without permission change. Actual idle-guarded isolated signed1ba LaunchServices startup5.08sec/PID9602; independent GUIWindowServer owned327 at1100x740, exactAppKit active/not-hidden owner. No pixelcapture/input; essential rendering unmet because currentobserver capturepreflightfalse. Normal terminate/open-W0; profilehashsame. Three ephemeral services absent/readback113 and six script/plist files removed; noownedapps; all7290signedentries/archive same. Functional/build checks reused. REPORT.md/qualification.json and air-gui-receipts-original bind limits. Cooper localpreview/CTV/Kryden preserved; public0.2.5/0.2.6HELD/no grants/settings/publish.


## Oct14 — authorized full local website theme extension

Canonical site main cf872207 remains unpublished/uncommitted. Current accepted split mono hero retained and existing VODForge violet/dark tokens applied through shared reference-theme.css/BaseLayout on all18page routes; five guides get same split opening, standalone verification imports theme. Existing copy/scripts/data bindings, OS chooser, fourdownloads, links, accessibility owners and nativeimage bytes preserved. DevToolbar disabled after actual local overlay blocked mobileconsent controls; no analytics/privacy behavior change. Final82file Astrocheck zero diagnostics/direct QAbuildpass. Independent headless36desktop/mobile cases,32internal targets,18additional320/768/1440breakpoint checks and tabkeyboard/disclosure/menu/emailclose-focus pass; no backend writes/download/provider submits, all owned browsers closed. Original stalecache/hiddenimage/404/hiddendisclosure oracle and devToolbar failures retained; invalid checks corrected, valid desktop/source evidence reused. Six sourcepaths changed thisbatch; three preexisting OS newfiles preserved. Evidence /tmp/vodforge-theme-20261014/qualification.json/results.json/source-preservation.json/screenshots. Physicalpreview show pendingfreshcallguard (existing lowusagepopup maskscontrols), no Krydeninput/dismissal. Local18576server retained/URL4323; CTV/userprofiles preserved. No commit/push/deploy/publication; public0.2.5/0.2.6HELD.

- Website theme handoff 2026-10-14: implementation and 36 route + 18 breakpoint cases complete; 32 internal targets and final Astro check/build pass. Seven final screenshots uploaded successfully to ChatGPT Library; receipt /tmp/vodforge-theme-20261014/library-deliverables.json. Existing Chrome selection/refresh pending only: usage popup obscures live call controls; persisted lifecycle/jobs clear at 06:06:18 UTC does not establish human inactivity. Parent requests screenshots now. No popup dismissal/native input/publication; preview PID18576 retained on port4323.

## Oct14 — user-requested Windows integrated frame source

Shared application-painted Windows frame for main/player uses existing StoneButton controls; native Windows caption/thickframe/system/minmax retained beneath nonclient layout removal, signed current-DPI hit testing and monitor-work-area maximize.21 affected checks/Ruff/format/diff/scopedadaptermypy pass. Original209scene run208pass/1sharedrenderer violation preserved; correctedproduct tosharedStoneButton, affectedcasepasses; no testdisable. Native successor/build and actualresize/drag/system/snap/fullscreen/popout remainpending; no shiftedbugcause claim. User supersededMac-image draft withgenuineWindowscontrols/captures anddisposablefictionaldemo. No websiteassets replaced/nativeapp/profile touched. Receipt windows-frame-20261014/source-checks.json and engineering-quality/windows-integrated-frame-20261014.md.

- Windows frame024c2ae committedlocal; automaticreview rejectedexistingbranchpush firstforunverifieddestination, thenafterreadonlyownerADMINverificationforpublicsourcepublicationnotexplicitlyauthorizedbyprivatebuildrequest. Bothpushesunsent; exacthumanapprovalquestionpending. No indirectsourceexport/pushworkaround. Recognizedhostedprivatebuild/nativeacceptance/capturesheld; unrelateddemo fixturepreparationcontinues. Evidence windows-frame-20261014/approval-blocker.json.

- Windows frame024c2ae interim:8/8generalizedhitregions rejectHTCLIENT-only mutation(no runtimeedit);21affectedpass/208unaffectedscenevalid. Nine isolatedlocalfictionalmedia actualdurationprobe pass(6MP4/3MP3); separatetmpHOME/deniedconsent/noURLs submitted/no customeraudio; notcopiedtoPC. ExistingWindowsimg0wallpaper exactSHAa63ed4cf copiedread-only, settingsunchanged. Ordinaryf96156632 idle/0queue confirmed. No successorbuild/nativeacceptance/capture yet becausepublicbranchpushapprovalpending afterautomaticreview rejection.

- Source8406ce7 actualWindows continuation: localsourcecompile/import Qt6.11.2/Python3.13.1 fromrecognized889runtime(no dependencydownload/globalinstall/publicupload). Actualmainpaint/fullclient1100x740at96DPI, maximize to3440x1400workarea, restore/minimize, captiondrag30,30→130,90 andactualClose pass.33affectedlocalchecks pass. Firstblank/behindbrowser image andfailednative maximize retained; MSGhWnd/cache andnonclientgesture fixes added.008guardfailedafterprocessstart(57104rootownedpid), soexistingowner reused by009, no duplicate launch. Demo/private/tmp pathmapping corrected; Playnowenabled. NormalcheckpointClose012; ownedtaskretired, ordinaryf96156632preserved. Signedpackage/nativeplayer/resize/doubleclick/system/snap/MultiMonitor/changedDPI remainunqualified. Librarysourceproof libfile_bd8a4212cdf0819196aac940db87e95e, metadata receiptpending. Websiteimagesunchanged/public0.2.5/0.2.6HELD; publicpushapprovalpending.


## Oct14 — Windows source frame native continuation and clean capture checkpoint

Exact840source mainresize1220x820/captiondoublemax3440x1400+restore/nativeAltSpace menu/WinLeft1720x1400pass; floating780x471header32/maxrestore/fullscreen3440x1440/Escape/samevideoClose-returnreadbackpass. Originalobserver022/034retiredHWND screenshotfailuresretained/captureownerfixed;015/019recentinputrefusalsretained.043 ordinaryworkguard stoppedRecoveryclick; followoncapturewronglylabelledRecovery actuallyMyFiles hashidentical/excluded. SixunalteredactualQtwindowPNGs hashboundcapture-manifest-840.json; noUIredraw/normalprofilecopy/downloads. Source53008 normallyretired046/exit0readback047, Readyownedtaskremoved048 at08:03:33UTC; ordinaryf96156632 preserved/latestidle0queue. NoMacinput/heavyjob/publicpushretry. Remainingfloatingresize/min/directReturn/physicalDPI-monitor/Win11flyout/signedsuccessor; websitecomposition+responsiveQA+Maccleanups pending. Evidencewindows-frame-20261014/CHECKPOINT-20261014-0804.md.


## Oct14 — finished local Windows website imagery

At2026-10-14T08:26:58.660100+00:00, canonicalvodforge-site/URL4323/PID30431 retains seven actualsource840Windows Qt windows over verifiedWindowswallpaper viaCSS, unalteredPNGs; homepage/genericWindowsguides/claim/MP4/press updated. GenuineMacguide/14historicassetbindings unchanged.83Astrozero diagnostics/directfinalQAbuildpass;18desktop-mobile+6narrowtablet cases/sixworkspacetabinteractionspass,allbrowsersclosed,API mocked/no downloads. Fourinline-scriptowners preserved; originalregexselfclosingtagfalsefailure retained/corrected. Windowspreviewkit7nativehashes/provenancebound;public0.2.5unchanged/no publication. RecoveryfictionalStopped ownerseed/actualnativeexpandedchoices052–054 captured/no retry/download. Floatingremaining056and061guardrefusedordinarywork; stopped. Demo45704 normal059/exit0readback060/sourceabsent+taskremoved066; ordinaryf96156632preserved.13Libraryfiles saved/metadata13pass; preparedhelper unavailablebeforereservation, availabledirectcreate ordered/no duplicate. Evidencewindows-frame-20261014/WEBSITE-FINISHED-20261014.md+website-final-qualification.json; /tmp/vodforge-windows-site-20261014. NoMacinput/signjob/pushretry. Platformlimits untestedfloatingresize/min/directReturn/physicalDPI-monitor/Win11flyout/signed840successor, notlocalwebsitedeliveryblockers.

- Directpeerrelease notice rejectedbyautomaticapprovalreview: lackofdirectend-userauthorization, delegatedmessages insufficient. Not sent/retried/indirectlyrouted; automaticparentoutcome only. Localwebsitefinish unaffected.


## Oct14 — scheduled read-only health check after03:23 baseline

At2026-10-14T08:35:19.270006+00:00, actualCloudflare/D1 authreads succeed. Exact03:22:16→2026-10-14T08:32:18.473Z workerwindow56invocations/allstatussuccess/0runtimeerrors; noallcustomerHTTPstatusclaim. D1server2026-10-14T08:32:24.521Z/quick_checkok/noFKviolations/34schema+28migrations+15versiongroups exactbaselineequal;6057accepted/latestOct13 22:48:43, zero newevent/failuregroups. Eightactualreadstatementsrows_written0/changed_dbfalse. Publicsite+establishedreleasefeed200/v0.2.5; no trackeddownload/syntheticevent/deploy/credential/access/monitorchange. Existingpre-ingest/outbox/customerHTTPstatusgaps deduplicated, no-trafficnotdeliveryfailure. Nativefloatingresize/minimizeguardreason056/061retained/no inputretried/publicpushunapproved. Evidencebuild/recovery-20261011/backend-monitor-20261014T0832/REPORT.md+originalfullresponses+comparison+hashes.

## Oct14 — local PostHog integration qualification in progress

User-authorized project664300/public ingestion binding staged with capture/replay/experiments disabled. New separate provider opt-in and epoch-bound best-effort desktop mirror preserve custom telemetry; website manual closed-vocabulary events, replay masking and installation-help route are local/unpublished. First Astro check retained six genuine SDK/API type errors in /tmp/vodforge-posthog-20261014/astro-check-first.log; corrections invalidate only that failed compile pass. Python compileall passed; affected behavior/privacy tests and responsive checks pending. No production event, replay, flag, billing/access mutation, deployment, public push or native foreground input. Project IP anonymization and capture caps remain parent acceptance blockers. Existing historical functional checks reused.

## Oct14 — local PostHog and installation-help qualification

Source-only/unpublished optional project664300 integration qualified; capture/replay/experiments allfalse inbothconfigs.68affecteddesktop+59attribution/build/privacy pass; final27first-run/epoch/idle/admission casespass;36webtests/87Astrozero diagnostics/finalQAbuildpass.28responsivecases/zeroexternaltraffic/12text-fixturedownloadrequests; actualSDKpositive3interceptedbatches plusGPCzero/withdrawal/private-sentinel/envelopechecks pass. Generalizeddimensionsleakmutationdetected/noruntimeedit. OriginalsixSDKtypefailures, dataclassfixturefailure, fivefirst-runpolicyfixturefailures, twoobsoletewebassertions and enabledSDKfailures retained. ActualSDKrequiredpublicroutingtokenwasstripped: repairedonlyverifiedpublictokenretention, closedenvelope/personfieldsremoved. Remoteconfigwasstillrequestedbyfeature-onlydisable: actualadvanced_disable_flagsnowpreventswhenexperimentsoff. StaleViteprebundle andheadlessbotfixtures corrected/noSDKbotprotectionrelaxation; verifiedownedpreviewnormallyrestarted/same4323. Existingfunctional/nativechecksreused, no broad campaign. Sourcehashes/report build/recovery-20261011/posthog-local-20261014/qualification.json+REPORT.md; originals/screenshots /tmp/vodforge-posthog-20261014. IPprojectfalse/capsunreadable/replayutility/flag/privateprovideracceptance and signeddesktopsuccessor remainheld. No liveproviderrequest/nativeinput/accessbillingchange/commitpushdeploy/publication. Public0.2.5/0.2.6HELD;Krydenvoice/CTVprofilespreserved.

## Oct14 — authorized capture-disabled private PostHog successor

Parent/user authorized recognized local package/sign independently of remaining provider activation. Separate posthog-private-20261014 output and PyInstallerwork preserve installed dist/rollback; current runtime inputs hashbound, dirtysource revisionhonestlyunknown/HEAD8406basis. Existing package-only maintained recipe uses localPython3.13.14/installedtools, no dependency download/fullcampaign/nativeinput. Candidate0.2.6-dev.posthog.1 retainsproductioncustompolicy but providerconfig capture/replay/experimentsfalse; isolatedoffscreen smoke planned. No notarization upload/publication authorized/needed for private signing. Ownedprocess preflight showsnoVODsign/buildconflict, currentKrydenuntouched. Budgetapproval10:47:48UTC supersedes earliercapsblocker: useracceptsdefaults, no budgetchanges/$0caprequirement/access expansion; parenthandlesprivacyread independently.

## Oct14 — signed PostHog private artifact and precise privacy alignment

Recognized package-only source build0.2.6-dev.posthog.1 succeeded; separateapp/rollbackretained; existingDeveloperID76G5W4954G/hardened/timestamp/deepstrictpass.444MachO actualfloor27/current27.0.1/plist27, noolderOSclaim. Actualsignedoffscreenisolatedsmoke0;4compiledPYZboundarycasespass(providerfalsebeatenvtrue/zeroHTTP/customack/privateprojection).6328archivefiles+links equal;archive22171cca/sourcehashes+rollbackexesame. OriginalspecrelativepathandmissingplistSetfailuresretained/corrected; no broadcampaign/normalreplacement/nativeinput/notaryupload. Artifact/reportposthog-private-20261014. ParentprivacyverifiedanonymizeIPstrue/inputs+private-text masks/consolefalse/bodyheadersfalse/replaydisabled/noevent; defaultbudgetsaccepted unchanged. Websitealignment preserves reviewedpubliccopy/controlattrs, rejectsunapprovedtext/attrs, addsactualnon-inputphmask statuses+challengephblock. FirstmanifestoraclecaughtwrongdistinsteadQA dist-preview; corrected/37tests+87Astrozeropass. Replay/providerliveacceptance remainsuntested andcapturefalse; no pendingIPconfiguration/budgetblocker.

- Final replay scope alignment after userclarification passes38websitechecks/87Astrozero/finalQAbuild. Explicitphmask addedbeforewaitlistmembershiptext, email/server-status/claimtext tagged, challengephblock; reviewedpublicDOMcopy+attrs retained/unknownvisitorvalues dropped. ProjectIPprivacy nowverifiedtrue byparent/defaultbudgetsaccepted; thoseearlierblockerssuperseded. No liveproviderrecordingacceptance/activationclaim. Signedprivate6328entry22171ccaartifact remainsunchanged;allownedheavy/sign/smokejobsended;localhostpreviewrestored/noforegroundinput.

## Oct14 — PostHog compatibility regression diagnosis and correction

Parent rejects macOS27 testingcandidate as compatibility successor. Actualaudit75runtimebinariesabove15 matchesknownordinaryHomebrew contamination:Python/FFmpeg/SQLite26,OpenSSL/libvmaf27; zeroPostHognativebinaries orrequirementschanges. Myordinary-toolchain selection wasincorrectfor established15 lane; 27artifact22171cca retaineddiagnostic-only/notrelease-ready. Read macos-floor-20261013 REPORT/inputreceipts/SQLitefailure; retainedPython3.11.15+21-file ownCItoolgraph+explicitcompatibleSQLite hashesallmatch.75affectedPostHog/product/consent/Qt tests passactualcompatibilityenvironment; pipcheckpass. Samecanonicalsource hashes retained/dirtyrevisionunknown; separateposthog-private-macos15-20261014 packagingstarted usingmaintainedrecipe andverifiedinputs/no downloads/no minloadcommandlowering/no ordinaryapp replacement/nativeinput/providercapture. Fullbundle<=15audit/sign/currenthostsmoke andarchivebinding pending; actualMac15nativeacceptance remainsseparate.

## Oct14 — macOS15 PostHog private successor qualified

Correction completed usingestablishedretainedcompatibleinputs/no downloads/oldcode reuse/mincommand lowering. ActualPython3.11.15 affected75pass/pipcheckpass; finalDeveloperID/hardened/timestamp/deepstrictpass; signed384MachO max15.0/errors0/no nonsystemabsolute dependencies. Exactsignedisolatedoffscreen smoke0 +4compiledmirrorboundaries +actualbundledH264High/AACencode/probe/fullAVdecodepass.6258archiveentries match/noextras; archivebcc069ce/exe90880f59; currentruntime sourcehashes androllbackexeunchanged. PostHog allfalse/customproductionpolicyretained; dirtyrevisionhonestlyunknown. Report/artifactposthog-private-macos15-20261014;27candidate22171cca remainsdiagnostic-only. No currentbuild/sign/nativejobs; ordinaryKryden/CTV/foreground andallrollbackbundlespreserved. Actualmac15native/notarization/staple/Gatekeeper/IntelWindows/liveprovider remainuntested; nobuildtoolchainblocker. Public0.2.5/0.2.6HELD/no publication.

## Oct14 — authorized scheduled production health check14:27UTC

Comparedsaved08:32baseline. ExistingmanagedCloudflareauthenticatedreads succeeded/no secret orcredential access. Worker08:32:18.473→14:27:18.017UTC347invocations/allstatussuccess/0runtimeerrors; notHTTPstatus/telemetry-endpoint counts. D1server14:27:25.775/quick_checkok/noFK/34schema+28migrations+15versiongroups exactsame;6057accepted/latestOct13 22:48:43/no newaccepted orfailuregroups. Eight SQLPRAGMAreads rows_written0/changed_dbfalse. Publicsite/feed14:26:33HTTP200/version0.2.5/allpublishedassetdigests same. No meaningful newalert;quietdoesnotprovefailed/abnormaldelivery without activeclient attempt context. Pre-ingest refusals/outboxes/customerHTTPstatus gaps unchanged/deduplicated. REPORT/comparison/originals/SHA256 backend-monitor-20261014T1424. No synth event/trackeddownload/deploy/data/settings/access/monitoring change/native input orreleaseactivationwork.


## Production backend read-only health — 2026-10-14 20:50 UTC

No meaningful new alert. Exact prior receipts confirm 347 Worker invocations/zero runtime errors, 6,057 accepted events, 34 schema entries, 28 migrations and 15 version/platform/channel groups. The compressed schema60/57events figures were incorrect.

Authenticated Worker window 14:27:18.017–20:49:46.594 UTC has 16 invocations, all success, zero runtime errors. This is general Worker traffic, not customer adoption or telemetry-endpoint delivery evidence. Monitor availability requests may contribute; this run's public GET occurred after that window. Lower volume alone is not a failure.

D1 server check 20:49:52.448 UTC: quick_check ok, foreign_key_check empty; exact schema, migrations and all accepted app-version/platform/channel aggregates unchanged. Still 6,057 accepted events, latest October 13 22:48:43 UTC; no new accepted events or failure/rejection-action groups. All eight statements report zero rows written and changed_db false. Quiet accepted telemetry does not prove failed delivery without expected consented-client attempts; client outboxes, pre-ingest refusals and individual customer HTTP statuses remain unobserved. Other customer tables were not equality audited.

Public checks completed 20:50:13 UTC: https://getvodforge.com/ HTTP200, full 32,421-byte body identical; established update metadata https://api.github.com/repos/SnowfallHD/vodforge/releases/latest HTTP200, v0.2.5, draft/prerelease false, all five asset names/sizes/digests unchanged. No binary downloads or tracked download routes. Initial restricted-network DNS failures are retained separately; authorized external-network public GETs succeeded.

Original managed authenticated responses, exact read-only SQL batch/window and public bodies are retained in this directory. No synthetic events, database writes, deployments, credential/permission/subscription/monitoring changes, desktop GUI input or foreground interference. No new jobs created. User notices remain parent-owned.

Receipt: `build/recovery-20261011/backend-monitor-20261014-latest/REPORT.md` and `comparison.json`.


## User-requested private Mac launch — 2026-10-14T21:35:39.029365+00:00

Verified archive SHA256 bcc069ce3925630bc6e0c4b7e23d9292f305c504046c9b2183600efebf6b3a59, executable90880f597aa3824cbd32ae3eb124fea092a4d2b9aa009089da95fc7a4ba1ce0b and all6,258 sealed entries before launch. Deep strict Developer ID signature passes outside sandbox; initial sandbox verification falsely reported invalid signature, retained as verification-context limitation; no bundle modification/re-signing/security bypass performed.

No existing VODForge process before launch. Exact qualified private0.2.6-dev.posthog.2 bundle opened through LaunchServices. Native NSWorkspace confirms PID49905, exact bundle path, finished-launching/active/not-hidden; CGWindowList confirms actual on-screen main window VODForge,1100x740,alpha1/layer0. This is native window-presence evidence, not a screenshot/pixel or comprehensive functional review. Existing installed executable and all nine normal profile JSON files remain byte-identical after launch. Product telemetry permission remains false; private provider flags remain disabled. App left open for Cooper's review; no automated UI journey/download or synthetic analytics.

No installation replacement, privacy/credentials/security changes, deployment/publication or Air operation. Actual macOS15 acceptance remains separate and parent-coordinated; current Mac observation does not satisfy it. No owned build/sign job or further native input remains.

Receipt: `build/recovery-20261011/posthog-private-macos15-20261014/native-review/launch-observation.json`.


## Air existing-route readiness — 2026-10-14T21:37:54.275094+00:00

Fresh existing Tailscale SSH read-only connection succeeds; julie/x86_64/macOS15.8.1 build24H32, consolejulie, activegui/501. No VODForge/FFmpeg process observed. Retained executable e23f13656e98a44b349afd6afbdcbe04cc25c27d47e85668b734995a737bb43f and embedded source1ba2653895bc2e0023cc3a736cbc7fe22fc50d6c match original qualified Intel receipt. Desktop environment offline listing does not establish Air unreachable.

Current qualified Intel artifact: version0.2.6 at exact1ba2653, archive9e92404afd58d293cec34bf501f88e08521652ea580e4def91c3558ac3aa6138, runtimebasis889c046, signed/notarized/stapled/Gatekeeperpass. Existing valid physicalAir frozenruntime/tool/H264HighAAC/320kbpsMP3 encode/probe/full decode, native5.08sec startup/owned1100x740WindowServerwindow, normalclose/exit0/profilepreservation receipts remain valid and were not repeated. See ../intel-private-1ba2653/REPORT.md.

For that exact Intel artifact, essential rendered-content inspection remains unmet. Last GUI-bound systemPython observer CGPreflightScreenCaptureAccess=false, AXIsProcessTrusted=false. No screen-access/capture/permission request or native input was retried now. Screen Recording permission for the actual gui/501 observation route (systemPython launched by disposable LaunchAgent) is missing; exact user-visible TCC recipient/label is not established, so do not tell the user to grant VODForge or a guessed Settings row. Accessibility also denied for that observer; required only if proceeding to AX-controlled interaction. An already-supported permitted visual observation route could satisfy rendering without that grant; none is currently established.

Build distinction: Intel1ba2653 predates local PostHog work. Current openedMacBookPro candidate0.2.6-dev.posthog.2/archivebcc069ce is ARM-only and dirty-source-hash-bound; it is not a matching Intel artifact and cannot validate IntelAir. No matching PostHogIntel package identified in maintained receipts. Therefore permission is the remaining rendering gate for existing1ba; it is not the sole prerequisite for accepting the latestPostHogsource onIntelAir, which additionally needs a source-bound Intel successor qualification. No broad campaign/build initiated or old proof relabeled.

No new credentials/keys/access/security changes, remote checkout/install/profile mutation, screen capture, localPro input/restart or publication. User's Pro review app remains untouched. Parent coordination needed for a permitted visual route and, if latestPostHogIntel acceptance is required, exact successor packaging scope.

Receipt: `build/recovery-20261011/air-readiness-20261014-evening/readiness.json`.


## 0.2.6 finite resize/Options scope recovery — 2026-10-14T22:03:07.369220+00:00

ActualQML five density/gutter boundary regressions fail before; six resize+nine Options15pass after continuousinsets preserving1100x740. Supplied3LibraryPNGs inspected. Acceptedf961 source matchingmode popup endpoints pixelidentical; controlledmidpoint smallcache delta, nativeuserreport remainsopen. Edgefirstdragrootunresolved/no OSsettingsguess. Existingworkflow reusepolicy clarified; cheapinputpreflightrejects actualincompatible HomebrewPython/passes boundIntelinputs. No broadchecks/nativeinput/reviewreplacement. ExistingIntelnotaryfinishedAccepted/archive6bd8511b heldlocally/predatesfix/noAirtransfer. Exactsource/method/OS/hash bindings,scopeauthorizationmap,originalfailed andafterreceipts in `build/recovery-20261011/resize-scope-audit-20261014/REPORT.md`; singlefinitegate list `engineering-quality/release-026-recovery-checklist.md`. No release-ready claim.


## Finite recovery — legacy hierarchy/partial ownership — 2026-10-14T22:29:07.144151+00:00

ActualreviewPYZ contains25bcleanup/call; sourcehash7e0fb414 matches. Ordinaryreadonlyaggregate15of27nonimportrecords lackroot/all15exactcanonicalmatches; incidentlastrecordjoinunknown. Addeduniquedurablecanonicalrootrecovery, missingmediaownedcompanions/emptyfoldercleanup, recognizedemptyvideopeers; arbitraryemptydirs/unknownfiles/symlinks/otheritems/rootprotected. Finalbadbaseline11fail47pass then58pass;159affectedboundaries/7failed-runroutes/1strengthenedfooterpass; compatiblePython3.11hierarchy+resize64pass. Original13andintermediate5failure/oraclecorrectionsretained. ActualMacTrash3fixtures8ownedfictionalfiles hashverified; sourceAPI only/no frozenUI orWindowsclaim. No realmedia/profile/app input. Report `build/recovery-20261011/delete-hierarchy-20261014/REPORT.md`; newARMrecoverycandidatequalifiedseparately, existingProreviewpreserved. No broadcampaign/release.


## Isolated recovery ARM candidate — 2026-10-14T22:33:27.477188+00:00

Boundedresize+hierarchysource nowDeveloperIDsigned0.2.6-dev.recovery.1; archive0aab0759b446cc63b166045c9145f935c9d1491bc689a334ac942376164fd740/exe3e930f78a17ab520d5222bba40ddf27b1987c87a799e400227e8c3dd5a70200e;6258sealedentries exactarchive/384ARMmachO max15/noexternalabsolutelinks. Actualsignedisolatedsmoke0,compiledPYZlegacyrootcleanup+Main.qml bindingspass. Notnotarized/nativeaccepted/releaseeligible. CheappreflightcaughtDeno hostSQLite/lcms26; correctedreaderbuilt-in/selfIDissuespreserved; copiedportable24fileowntoolgraph/preflightpass/badHomebrewreject retained. QA-onlypartition+footeroracle changesafterfreeze explicitlymapped;1partitioncontractpass/no rebuild. Fictional4caseprofile+Move destination prepared/notlaunched; Proreview49905 lastobserved22:21untouched. Nativeinput/CUAabsentin task; needsparentcoordinatedphysical/CUAstep, no permissionbypass. Report `build/recovery-20261011/recovery-arm-20261014/REPORT.md`; no broadcampaign/publication/Airtransfer.


## Parent-coordinated isolated recovery launch — 2026-10-14T22:40:04.950668+00:00

Exact signed0.2.6-dev.recovery.1 launched through LaunchServices, PID75446; executable3e930f78a17ab520d5222bba40ddf27b1987c87a799e400227e8c3dd5a70200e. Native readiness/attestation confirms fictional isolated HOME/history/output and telemetry production/preview false. NSRunningApplication active/finished/not-hidden; WindowServer title VODForge [Recovery-1-FIXTURES], layer0/alpha1,1440x817 at0,30. Metadata only, not pixel verification. Older ordinary-profile review PID49905 remains open; cooperative hide returnedfalse, so not claimed hidden. No close/terminate or further fallback input. Candidate is distinctly tagged; all real profiles/media preserved by isolation, no contemporary full normal-profile equality claim. Four native manual gates remain open: continuousresize, edge/firstdrag/fullscreen, accepted Options morph/controls, GUI Move/Delete hierarchy. No public release/notarization/native acceptance claim. Receipt `build/recovery-20261011/recovery-arm-20261014/native-fixture/launch-observation.json`. Owned launch step released; user review remains open.


## Requested Settings/Collections and both-OS Trash closure — 2026-10-14T23:03:15.340460+00:00

ThreeQMLonly: themeSETTINGS heading/alignedYouTube in side-by-sideOptions; directrightclick/MoreDeletecollection via existing scoped transaction/confirmation with noselectionmode; collectionlabels fixed/sourceplaylistterms preserved. Cooper acceptedrecovery.1resize/Optionsresponsiveness explicitly; usertestimony,notexecutorobservation.21Options+14collectioncasespass;finalcontext/sourceplaylist1pass;priorQMLnegativecontrol5fail2pass;Ruff/format/diffpass. Signedprivate0.2.6-dev.recovery.2 compiledresourcebinding/finalfrozenSmoke0/6258archiveentriespass;archive0b441b348c24dfe3045db0eca9c75e3561cd7b204571365a41ed1518f4c4294a/exe5fb15da703b5fff58111d8b92cdc4f78ea77ecabf0449cdfecc45b1f3b280d7e. Notlaunched/notnotarized/publicheld. RealOSsharedsourceTrashmatrix34/34Mac+34/34Windows;84recoverablepayloadhasheseach, exactbefore/afterpaths. Initialreaderfailurespreserved/reevaluatedwithoutdeletionrepeat. No realmedia/collections/Profile/ordinaryapp input orTrashemptying. Fullcase report `build/recovery-20261011/trash-matrix-20261014/REPORT.md`; build/report `build/recovery-20261011/recovery-arm-2-20261014/REPORT.md`. PackagedGUIMac/Windowssuccessortransactionstilluntested;Windowsopenf961untouched. Directobservercoordinationtoolrejected byautomaticapprovalreview; parenthandoffneeded. Noownedheavy/native/SSHjob remains.


## Actual Windows recovery.2 GUI and user-found successor corrections — 2026-10-14T23:26:15.936441+00:00

Retainedprivate-finalenvbuild/smoke0/noinstalls. ActualPID53328/session1/96DPI1100x740,exe589f7ba3132062695c08daaa2daf5736d27bc1eb9662f291306336a0ace14ee1. Nativepixelsinspected.1actualGUIcollectionrightclick/3filesTrash/ownerremoved;rootpersonalfilepreserved/33rowsremain;GUIrecoverabilityUNVERIFIED(initialreader0of3matches), notclaimed.33remainingGUIcasesprepared,notcompleted. CurrentQAappopen;ordinary56632untouched. ParentMac13GUIrecord/31Trashhashacceptancepreservedwithitslimits. Nativecaughtintroducedmissinganchorassignment/sourcefix1beforefail1afterpass. UserRunDeck151vs139clipping:4beforefail/10resize-deckafterpass. Structuredread-onlyfilepathblocks2widthspassaftervisualreaderrepair;buttonsunchanged;actualsuccessorWindowsrenderpending. Newlyuncoveredreservedemptybucketcleanup6beforefail15afterpass;noAPI34suite repeat. Consolidatedsourceawaitsrecovery.3package/nativehandoff. Report `build/recovery-20261011/windows-recovery2-gui/CHECKPOINT.md`. Public0.2.6held.


## GUI recoverability acceptance held — 2026-10-14T23:30:43.977486+00:00

FirstWindowsGUItransaction journalcompleted/3filesgone/selectedhistoryownerremoved/rootnotepreserved, but recoverabilityreaderexpected3matched0. Vacuousallhashes-matchflagNOTaccepted. Ownedprefixandboundedoperationtime/hashreadbacksC/Ealso0;2knownpriorAPIpayloadsstillexist. No rootcauseclaim/no additionaldeletions/APIrepeat. GUIcaseNOTPASSuntilrecoverabilityproven. Exactcurrentstate/readersunder `build/recovery-20261011/windows-recovery2-gui/`; noownedbuild/sign/inputactive. Sourceonlysuccessorfixesqualifiedbutnotyetpackaged/nativeaccepted.


## Consolidated recovery.3 build checkpoint — 2026-10-14T23:53:31.725800+00:00

Macprivate3strictsigned/smoke0/archivebe4982e2e60488e16b087fb69ff5143d8fbdf4cd18d1e4adf09b8819986c9ef2/exe943140e6704402ab3fc9d2ed10b662a24fd4d082bd3ac22ba0d82e6ae091fe4c/6258entries/384ARMmax15pass; actualGUIpending. Compiledarchiveowner+QtBridge source and4QML exactlybound; Windows-only nativeadapterpostfreeze delta mapped as notMacexecutedinput. Windowsprivate3maintainedbuild+smoke0completed; exactbindingreaderUTF8repairinprogress,nolaunchyet. NativeTrashoriginalGUIrecoveryacceptanceFAILED:allaccessibleC/E/Fbins/SIDs0of3matches, expectedGUIownerSIDverified,prior84payloadsremain. No permanentloss/rootcauseassertion; original3whereaboutsunknown. Windowsadapter nowraisesCOMHRESULTbeforenonrecycleandrequiresnativePostDelete destinationbeforeack;5prior-sourcefail/5correctedpass with fakeoperations/realbindings(noOSdeletion). Originalpytestparentdrive-discoveryerrorretained/fixedreaderonly. NoAPIcampaignrepeat/noadditionalGUIdeletions. OldGUI2PID53328lastsnapshotvalid/33rows/finishedresult;ordinary56632untouched. Mac GUIhandoff `build/recovery-20261011/recovery-arm-3-20261014/MAC-GUI-HANDOFF.md`; nextguardedrealWindows3transition/firstnative-receipt trial. Public0.2.6held.

Windowsrecovery.3binding reader repaired toUTF8 against unchanged artifact:3compiledmodules+4QMLmatch; exea40c6876d0b772712cda87632b8bf53706dfc56180f00be0df1598e0648c47e5. No rebuildforreaderfix. ReadyforguardedGUItransition,nolaunchyet.


## Windows recovery.3 first GUI receipt diagnosis — 2026-10-15T00:05:04.883201+00:00

QA2normalcloseexit0/independentabsent,ordinary56632preserved. QA3a40c6876PID54988isolatedstartup. Actual1100x740outerwheelshowsfullRunDeckcards/footer; initialtopneeds scroll,longpath. Anchoredmenuand3separatedpathblockspixelsinspected. Firstc00GUItransactionneeds_attention/firstfileonly; actualnativeBinvideoexists+exacthash,2companionsunchanged/history34. NohierarchyPASS. NativeprobePostDeletepositiveHRESULT0x00270008revealsnewreceiptcheckbug; highbitcorrection1beforefail5pass→6pass. Longabort-onlyprobe nativeflags514nonrecyclevs642short; trueCOMexceptionabortpreservesbytes. OriginalQA2potentialdata-loss3payloadwhereaboutsUNRESOLVED; priorproviderintegerabortweakness+longpathboundaryidentified,originalcallbacktraceabsent. Nofurthermatrixdeletions/nopublication. CurrentexactpackagepredatesHRESULTcorrection; successorrequired. Detailedreceipt `build/recovery-20261011/windows-recovery3-gui/CHECKPOINT.md`.


## Mac recovery.3 actual GUI and Windows potential-loss diagnosis — 2026-10-15T00:08:29.054109+00:00

Parentobserverexact943140..1fe4c2nativeGUItransactions/2completedjournals/6of6nativeTrashpayloadhashesPASS: nestedwholechannelwithemptyownedbranches+reservedbucketremoved/rootunknownsiblingretained; secondcaseprotectedselected/channelnotes+peerMP4unchanged/parentsretained. Anchoredmenu/fullpathselection/3columnOptionsPASS.1100x740twoRunDeckcardsvisible; shorterheight/manyrecordscrollUNQUALIFIED(onecornerdragnoeffect). NormalquitPID1508. Original13recordcampaignnotrepeated. Report `/Users/coop/Documents/Codex/2026-10-14/task-2/vodforge-recovery3-native-qa/report.md`.

WindowsQA3firstvideonativeRecycleBinbytesverifiedandnativeundelete restoredexactdisposableoriginalpath/hash;2companionsremain/history34. StaleBinmetadataremainedatfirstreadback,notclaimedfullyretired. Separatelongabort-onlynativeprobesourcebytespreserved;flags514lacksrecycle128versus642shortpath. OldproviderreturnsE_FAILintegerandcommentexplicitlywarnsdoesnotstop; pywin32gatewayreturnsInvokeViaPolicyHRESULTratherthanPythoninteger. OriginalQA2callbacktraceabsent; treatasUNRESOLVEDPOTENTIALDATA-LOSS,notreceipt-only. CorrectedproviderraisesCOMExceptionbeforeunrecyclabledeleteandrequiresactualpayload. Follow-upsuccessHRESULTfix6affectedactualWindowsbindingtestsPASS/RuffformatdiffPASS; prior1fail5passretained. NoOSsettings/securitychanges/ordinarymedia. NecessaryseparateWindowsrecovery4buildstartedretainedSSH; firstdetachedattemptneverexecuted/zerologs,noartifact,preserved.


## Corrected Windows actual-app matrix and recovery — 2026-10-15T00:26:44.164194+00:00

NecessaryprivateWindowsrecovery.4build/frozenSmoke0; compiled3modules+4QMLmatch,execd975480d6bf966233f3dd9d264f257985856250d32dda0f8d8dd6cad9c8893b,NotSigned/privateonly. QA3normallyclosed54988/preservedjournal; QA4PID58648attestedisolatedsession1. FirstcollectionGUI3filescompleted/3nativeBinpayloadhashes,wholeeligiblechannelgone/rootkept; all3nativeundelete restoredoriginalvacantfixturelocationswith3exacthashes. FourfilteredGUIbatches10/7/9/7records complete; full34currentpackagerecordoutcomes/84nativepayloadhashes. Per-caseexpectedremovals,actualremainingpaths,otherbytes,historyandBinbytes separated; zero-owned-filecasesN/Aforrecovery,notvacuousPASS.81payloadsremain/3restored. Long353charreal-appTrashrefusedbeforemutation/all3hashes+allfolders+historyretained,0Bintransfers/pendingjournalpreserved. InitialCP1252readerfalseownerabsentfixedtoUTF8againstunchangedtrial;noOSoperationrepeat. OriginalQA2potentialdata-loss3payloadsUNRESOLVED. ExactoriginalGUI2Send2Trash2.1.0/pywin32312modulesbound; no explicitUIpermanentfallback(permanentFalse), unsafeoldintegercallbackidentified/trueCOMHRESULTabortproven.

ActualWinRunDeckfullcards/footerreachable1100x640and1100x560viaouterForge scroll,34records. WindowsactualfullpathCtrlA/Cexact/clipboardrestored; separatedblocks/dividers/footerpixelsPASS; SETTINGSheadingfirstYouTubealignednativePASS. No physicaldrag/OS125%DPIclaim. Report `build/recovery-20261011/windows-recovery4-gui/REPORT.md` andROOT-CAUSE.md; public0.2.6HELD,ordinaryreview56632notreplaced.


Finalownedrelease 2026-10-15T00:27:10.2738142Z: WindowsQA4normalexit0/noQA2-4survivors; exact3ownedReadyinputtasksretired. Ordinary56632unchangedpath/all9JSONhashesunchanged. NoownedMac/Windowsheavy/sign/nativejob. CurrentcorrectedWindowsartifactisolatedunsignedonly,ordinaryf961notreplaced; publicheld. No furtherordinarymediaTrashtrial.


## OriginalQA2 read-only NTFS evidence — 2026-10-15T00:35:25.800916+00:00

ExistingOSlogs35secondownedpathfilter0matches. ExistingNTFSUSNread-onlyvolumehandle/capturedjournalrangecomplete; only3exactoriginalfileIDnamespersisted. Creation23:13:07 and originalparentFRNmatch; eachFILE_DELETE|CLOSE0x80000200 at23:17:49.328598/49.403368/49.463850UTC fallsinsideoriginalnativeUI006interval23:17:47.8336206→50.8357201. Norenameeventsforall3acrossretainedcreation→deletionrange. Originalpaths359/363/363UTF16units. OriginalNTFSobjectdeletionnowOS-evidenced; recoverydestination/bytesstillUNRESOLVED,notsecure-erasure/rawrecoverabilityproof. CorrectedQA4threeexistingBinpayloadsretainoriginalFRNs/samevolumecontrol. Nodiskrecovery/restore/deletion/permission/logenable/journalcreate/profilechanges. Fullreceiptsandlimits `build/recovery-20261011/windows-recovery4-gui/ROOT-CAUSE.md`; exactreviewartifactpath/hashinWINDOWS-ARTIFACT-HANDOFF.md.

ParentexplicitlyauthorizedMacobservercoordination; handoffaccepted, observerreleasedKrydenandstartedqueuedfreshisolatedmany-recordRunDeck/drag/fullscreenfollow-up. ThislaneholdsnoMacnative/heavyjob; Windowsnativeworkremainsreleased.


## Mac bounded layout/native release — 2026-10-15T00:41:49.600984+00:00

Observerexact943140...1fe4c/PID12183/fresh24recordattestation: actualouterbarfull4RunDeckcards/actions/All24/footer1100x640and1100x560PASS. Genericwheeldidnotmoveouter,notpassed. Firstbottom/topedgeandbottom-rightcornerchangedbounds; otherrecordedfirstedges/cornersdidnotresize. Fullscreenentered/supportedreturnattemptsdidnotexposereturnedwindow; afterfullscreenwindoweddragsandpressfirstpainttimingUNQUALIFIED. CUAtoolroundtripnotpaintlatency. NormalQuit/zeroownedprocess/24payloadhashes+historyunchanged/nojournal. No Trashrepeat/download/ordinaryprofileinput. Report `/Users/coop/Documents/Codex/2026-10-14/task-2/vodforge-recovery3-layout-qa/report.md`. NativeownershipreleasedforqueuedKryden387; thislaneownsnojobs.

## Mac fullscreen return classification/correction — 2026-10-15

Recovery.3 actual 24-record outer-scroll640/560 acceptance retained; several edge/corner inputs changed bounds, several did not. Application-vs-CUA cause of unsuccessful drags remains unresolved; no resize hit-zone modification. Source inspection finds no main fullscreen menu/standard shortcut; View/CtrlCmdF lacked an application return path. Added state-derived Enter/Exit Full Screen/public Qt methods, available while navigation is blocked, preserving per-navigation guards. Two actual-QML/QQuickWindow cases fail before and pass after; initial enum-reader failure preserved/corrected, Ruff/format pass. Offscreen does not prove native Space retirement. Fresh exact ARM/Intel successors now necessary solely for changed QML; existing Trash campaign not invalidated. Report `build/recovery-20261011/fullscreen-return-20261015/REPORT.md`. Public0.2.6held; no ordinary app replacement/native input.

Recovery.5 build progress: ARM final DeveloperID/notaryAccepted3d68002c/staple/Gatekeeper pass, exe4cb98de04a35bbd3efa402ccf76060575078f86486530a03db771abc886e574c/archive54f69bfcc70a3b0764a58ffae21e4ee22c0a33945358af4eb765d81df5f437a1;118actualcompiledmodules+47QMLbound,7210finalsealedentries. Exact immutable native handoff sent to observer for fullscreen return/one after-return drag only. Intel built/smoke0/DeveloperID; stable386x64MachOfloors≤15pass. Original unsigned audit overlappedcodesign, encountered .cstemp files and failed; preserved, superseded only by stable signed audit. Intel Applewait pending. Two fullscreen cases moved unchanged into already-registered test_qt_resize_continuity lane (2pass/10deselected); no workflowexpansion.

Space preflight then guarded cleanup: removed only five VOD-owned rebuildable caches and two new duplicate COLLECT staging trees, after no-PyInstaller and no-app-symlink-dependency checks; accepted apps/archives/receipts/source/tools/profiles/incidentfixtures preserved. Both executable hashes unchanged/internal links resolve. Free1,458,176,000→7,577,714,688bytes; receipt fullscreen-return-20261015/transient-cleanup-result.json. Localheavy/sign explicitly released to Kryden; only Intelnotarynetworkwait/finalseal remains, ~400MBarchive reserved. No Mac foreground input in this lane.

Recovery.5 actual ARM native closure: freshattestedemptyHOME/PID24112/exe4cb98de0..e574c, nativegreenfullscreen→actualmacOS View Exit Full Screen→exact1100x740returned;ONEafterreturnbottomedgedrag→1100x640. NormalCmdQ/noownedprocess/history-outputempty/nojournal/exehashunchanged. Menu-basedreturn+oneedgePASS; actualshortcutunverified/firstpainttimingunqualified/otherno-resizegesturesnotrelabeled. Observer report `.../task-2/vodforge-recovery5-fullscreen-qa/report.md`; ownerreadreport+returnedwindowpixels. No priorcampaignrepeat. Nativeownershipreleased; ordinaryapps/profilespreserved.

## Recovery.5 final private seal — 2026-10-15

ARM archive54f69bfcc70a3b0764a58ffae21e4ee22c0a33945358af4eb765d81df5f437a1/exe4cb98de04a35bbd3efa402ccf76060575078f86486530a03db771abc886e574c; Intel archive110bd511075397f95906d646a95a0371bb626d6729f7b165c878af26061831c2/exe5821441267fcbf0ec04a78f02a2ef7b0f51ab1e92647ecdc0f3648275a456cce. BothDeveloperID/AppleAccepted(ARM3d68002c,Intelca42059d)/staple/Gatekeeper/isolatedsignedSmoke0 pass.118actualcompiledapplicationmodules+47QMLbindeach, full7210ARM/7214Intelentryarchivemembership/bytes/links/noextras pass; floors384ARM/386Intel≤15.0. Intel localruntime usesexistingRosetta, NOTphysicalAir. ExistingAirSSHtimeout255 beforeidentity means physicalcurrentruntime/renderingBLOCKED; laterpeerstatusattemptinterrupted/noresult, no accessretry/change.

Final strengthenedmenu test additionallychecks View reachable while all4navActions retainblockedguard; initialreader countedbothActionsandMenuItems(8), originalfailedreaderretained; correctedAction-classreader2pass/10deselected, Ruff/format/diffpass. No furtherproductedit/buildneeded. Two changedtestreadererrors are not runtimefailures; originalmissing-action2beforefail remainsvalid.

Reviewdeliverable/finalfreezeplan `build/recovery-20261011/fullscreen-return-20261015/PRIVATE-REVIEW-HANDOFF.md`; exactartifacts+pendingphysicalgates `final-summary.json`,checkpointrecovery_20261015 updated. PriorWindows34/84andMac13+2Trashreceiptsretained/no campaignrepeat. OriginalQA2confirmedNTFSobjectdeletions/recoveryUNRESOLVED. Localheavy/sign/nativeexplicitlyreleasedtoKryden/observer; no ordinary appreplacement, commit/push/publication. Public0.2.5/0.2.6HELD.

## Original QA2 normal content copies — 2026-10-15T01:08:56UTC

Parentrequestedretained-evidence/read-onlyrecoverydiagnosisonly. Originalmanifest/seedshowsharedsyntheticbytes; retainedlocal4921bytevideo exactlymatches originald3f939... hash. NewtargetedexistingGenesisSSHreader checks ONLY3untouchedoriginalQA2legacy-peerfiles+3originalpathexistence: metadata20bytes/thumbnail25/video4921allnormalreadable/nonsymlink/SHA256exactoriginalvictimmanifest;mtime23:13:07UTCpredatesdeletion23:17:49. Alloriginalpathsabsent. Thus ALL3payloadcontentshaveexistingnormalcopies; no generatedreplacement/copy/restore/undelete/write. OriginalNTFSobjectsdeleted/nativeBindestinationunproved; rawrecoverabilityunassessed. PriorBinexactidentityreadersproperlyexcludedduplicatehashesandremainvalid; thisdistinctcontent-availabilityquestionwasnotansweredbythem. Firstencodedcommandtoolengthfailedbeforeexecution; sameboundedreaderstdintransportexit0, originalsretained. Exactcopymap/report `build/recovery-20261011/original-loss-copy-audit-20261015/`. No diskrepair/forensicwrites/newdeletion/OSchange/appinput/Airretry/publication.

Parentauthorizedfiniteactualremainingresizefollow-up queuedstrictlyAFTERKrydenimmediaterun. Observer reportsKrydennormalrelease01:08:56UTCandstartsnewguard/freshfictionalHOMEonimmutablerecovery5,left/right/top-cornersabove minimaonly; nofullscreen/Trash/download/24recordcampaignrepeat. Thislanehasnoownednative/heavyjob.

## Finite remaining resize actual result — 2026-10-15T01:11:56UTC

ParentcoordinatedobserverwaitedforKrydennormalrelease, thenexactimmutableARMrecovery5exe4cb98de0..e574c/PID26282/freshattestedemptyHOME/telemetryfalse.1100x740above820x560minima. ONEleftedge[2,740]→[42,740]2200x1480→2160x1480PASS;ONEright[2157,740]→[2117,740]→2120x1480PASS. ONEtop-left[8,22]→[48,62]unchanged; nativehitregion/causeunestablished. ONEtop-right[2112,22]→[2072,62]CUAwindowNotFoundAtPosition(screen1126,69), appstillobservable; completedgestureUNQUALIFIED, concrete tooltargetinglimitation notapplicationrejectionproof. No retry/sourcefix/fullscreen/Trash/download/campaignrepeat. Roundtrip559/1188/888msNOTpainttiming. NormalCmdQ/zeroownedprocess/emptyhistory-output/nojournal/exacthashunchanged. Report `/Users/coop/Documents/Codex/2026-10-14/task-2/vodforge-recovery5-remaining-resize-qa/report.md`. Priorrecovery3failed/no-resizeinputsretained; newabove-minimumleft/rightPASSdoesnotrelabeleverycorner. Checkpointupdated; no VODownednative/heavyjob, Airunretried/publicheld.

Parentexplicitclassificationclarification: recovery5top-left is FAIL for observedresize(no dimensionchange), withpointerhitregionUNQUALIFIED/appregressionUNPROVED. Top-right is TOOLFAILEDwindowNotFoundAtPosition; productresizeUNTESTED because target/gesturecompletionnotestablished. SideedgesPASSonlyboundedabove-minimumcase. CompleteresizeacceptanceNOTACCEPTED; no furtherrun/sourcefixproposed,noblindrepeat. Actualobserverreport+rawobservationsread; normalreleasepreserved.

## Current Air state and retained identity join — Oct14 11:44p.m. Chicago

Renewed parent scope: remaining privatequalification only, no nativeinput/rebuild/acceptedmatrixrepeat. ExistingTailscale status readexit0/backendRunning: exactAir100.84.96.112 Onlinefalse/Activefalse, LastSeen2026-10-15T04:10:00.1Z (Oct14 11:10p.m.Chicago). No SSH retry againstofflinepeer, no access/security/key/route changes. PhysicalIntelrecovery5runtime/renderingstillBLOCKED; retainedsigned/notarized/localRosettaproofsunchanged, notrelabeled. Receipt `build/recovery-20261011/air-current-route-20261015/peer-state.json`.

Fallbacklocalretained-evidencejoincompleted: all3originaljournalartifactstamps/sourcepaths match independentUSNfileIDs3096224744811075/76/77, exactparent3096224744811074,creationseen, FILE_DELETE|CLOSEwithinGUIwindow/noRename; each originaljournalnativeTrashdestinationnull. JoinedcorrespondingSHA/sizes20/25/4921withpreviouslyverifiednormalcopymap; all3contentsstillhaveverifiedexistingcopies(notcalledlost, no repeatremotechecks). Originalidentity/nativeBinlocationunproved; retainedmetadatahasnoclusterrecoverabilityproof. No diskrepair/undelete/copywrites/newdeletion/Windowsconnection/nativeinput. Report `build/recovery-20261011/air-current-route-20261015/REPORT.md`, machinecheckretained-identity-audit.json. Prior “released” messagesmeanresourceclearance, notpublication; no separatepublicationreceipt,0.2.6HELD. Recovery5artifacts/acceptedresults/incidentreceiptspreserved; noownedheavy/native/signjob.

## Apple Silicon lower-macOS support audit / metadata carry-forward — Oct15 Chicago

Parentaskedlower-versionSiliconsupport. Retainedauthorizedcompatible889target15alreadyimplemented/signed/notarized, explicitplist15, native/runtimehost27.0.1; olderOSacceptancefalse. Currentrecovery5whole384ARMMachOauditmax15/zeroerrors; bootloaderPython11,QtCore13,PySide15,FFmpeg-probe15,SQLite15,Deno12. Public0.2.5boundedprimarytoolreceiptobservesPython/FFmpeg26 (notcompletegraph). No currentexactARM15runtimeproof; macos-15releasebuilderconfigandmacos-26sourceCIarenotexactolderOSacceptance. ExistingstartupworkflowIntel-only/AirIntel15.8.1cannotqualifyARM15. NeedauthorizedARM15device/GUIfixture orreviewedmatchinghostedqualificationroute, notOSdowngrade/grants.

Concreteunfinishedpackaginggap: immutablecurrentrecovery5LSMinimumSystemVersionABSENT; no olderOScompatibilityinferred. Canonicalbuildnowwrites/validates sameexistingVODFORGE_MACOS_MIN_VERSION(default15.0) asinputfloorgate beforefinalsigning. Fiveactualbuild-block/PlistBuddyfixtures failbefore→5passafter: missing/stalehigher/stalelower/overrides; unrelatedmetadataandversionpreserved. Existingbinary-floorcoverage missedplistdeclarationcarry-forward; newboundedregressioncoversdeclared-targetdrift acrosssharedMacpackaging path. Ruff/format/bashsyntax/diffpass. Fullreceipt `build/recovery-20261011/silicon-support-20261015/REPORT.md`/support-evidence.json. No newbuild/sign/nativeinput/matrixrepeat. Postfreezeimpactonlybuild_macos.sh; allfrozenproductPython/QML/assetsunchanged, exactARMexe/archiveSHAverifiedunchanged. Docs/currentcheckpointupdated. Nextcandidaterecipemustcarrythismetadatafixandrecordplisttargetalongsideallbinaryfloors; doNOTrelabelexistingrecovery5metadata. Publicheld/resourceclearance≠publication.

## Smallest older-OS fixture plan — Oct15 12:20a.m. Chicago

Read-onlyconnectedhostMac14,7/M2/8CPUcores/24GBRAM,free5,324,800,000bytes. NoVMapps/CLI/fixturesfoundinApplications/PATH/standardlocations; noIPSWDownloads. ExistingmountsreportonlysameAPFSlowspace; noexternalcapacityidentified. PublicApplemodelidentification/SequoiasupportconfirmsM2modelclasseligible. RestrictedSDKVZisSupportedfalse/sysctldenied preserved; SAMEread-onlynormalhostcontext VZtrue/kern.hv_support1, no OS permission/entitlementchanges/VMconfiguration created. Exact15.0IPSWnotpresent soimagehardwaremodel is NOT verified; installedSDK/publicAppleAPI requiresimageisSupported+non-nilsupportedconfiguration+hardwaremodelisSupported beforecreation.

Plan ONEUTMAppleVirtualizationbaseline15.0VM, proposed2CPU/6GiBRAM/64GiBsparsedisk;budget~80GBavailableforimagestaging/guest/growth, explicitlyestimate notmeasuredchosenimage. Disk5.3GBblockssetup; no cleanup/install/image download/VMcreation. OfficialUTMfreeGitHubroute; Tartalternatequickstartexample25GB/default2CPU4GB, notinstalled. ExistingreleaseARMmacos-15+Intelmacos-15-intel; sourceTestsmacos-latestdrifts; signedsignedbytestartupworkflowANDrunnerIntel-only. OfficialGitHubcurrentARM15imagereports15.7.9(24G830), not15.0; ARMhostednestedvirtualizationunsupported. ProposedreviewexistingstartupguardarchitecturematrixfornativeCIpatch-levelchecks, ONEpinned15.0VMforminfloor, existingrealM2/Intelwhenreachableformediahardwarebehavior. No billableCI started orcostassumption.

ApprovalneededbeforeVMtool/Appleimage/VMcreation/specificstorageorcleanup/CIworkflow+privateassetstaging+anyminutesbudget. No changes/nativeinput/purchases/securitysettings/publication orbuildmatrixrepeat. Fullsourcedplan/rawinventory/capabilitycontextreceipts `build/recovery-20261011/lower-os-fixture-plan-20261015/REPORT.md`; checkpointupdated. Currentbuildspreserved/publicheld.

Coststeering: preferredlocalUTMofficialGitHubdistributionisfree/samefeaturesaspaidAppStoreperofficialdocs; no paidAppStore/rental/Tart/CIrequiredforoneguest. CIoptional/separatelyauthorized. HostM2/24GB/virtualizationtruebut5.3GBstoragegate remains; no storagepurchase/deletionassumed. Exactfuturego-ahead:approvedstorageplan+freeUTMinstall+Apple15imagevalidation/download+oneVMcreation(2CPU/6GiBRAM/64GiBsparse,80GBplanningreserve). Useraskedcostonly,nosetupstarted. Reportcostsectionupdated; buildspreserved/publicheld.


## Authorized publication preparation / bounded PostHog / disk audit — 2026-10-15

Cooperexplicitlyliftedpublicationholdforapp+newsitewithPostHog;publicMacrequirementsunchangedpendingactualARM15runtime. PreviousHELDstatementsarehistoricalpermissiononly;othergatesnotwaived. ActualpublicGitHubreadbackstillstablev0.2.5/850e19e,5assets,notdraft/prerelease. Final0.2.6sourcefreeze/signing/runtime/nativegatespending; recovery5dev-labelledandpredatesnewtelemetry,WindowsQA4unsigned. No publicreleaseclaim; canonicalsiteowneractivelyauthorizedownsource/privacy/ingestiongates+publicationretaining0.2.5downloadsuntilfinalassets. No duplicatedeployment.

PostHogsourceenabledwithseparateexplicitproviderconsent/epochandenvfalsekill-switch;replay/experimentsremainoff. Mirrorsafeenumprocessing/wait/duration/size/export/outcome/failure-stagefactsratherthandropallusefuldimensions. Newperformancecase1beforefail4negativepass;activationcasebeforefail;UUIDenvelopecasebeforefail.26affectedafterpass/Ruffformatdiffpass. Actualsynthetic-onlytestchanneltransport: property-onlyinsertID2HTTP200→2receivedrowsFAILEDdedup; top-levelstableUUID5correction2HTTP200→1matchingreceivedrowPASS. NeitherprovesnativeoptinUI/packagedruntime/adoption. Optionalproject-getautomaticallyrejectedtoken-returningread;noindirectretry/credentialread/settingschange. Permittedpublicingestion+eventqueryworks. Exactreceipts/docs/plan: build/recovery-20261011/posthog-release-20261015/.

Read-onlydevelopmentdiskaudit: VOD226.077GB/build183.030GB/engineering40.298GB; onecanonicalVODworktree/36dirtyuntrackedentriespreserved.58ignoredintermediate/cachetargets42.606GB,23historicalcandidateexpandedapps17.883GB,25historicalreplacementexpandedapps21.216GB=81.704GBgrossCONDITIONALopportunity,notapprovedsafe/netreclaim. All23P2candidateZIP+extractedtree/source/version/policymetadatafreshverifyPASSviaexistingreadonlyboundary;archives/receiptsretained. P1/P3bindingconditionsremain. Latestfree4.096GB;zeromoves/deletions/Trashpurges/VMdownloads. Allrecovery5/Windowsincidentjournals/QAproof/sourceassets/profilesprotected;Krydenownercanonical91GiBmixedprotectedhistory/8c75allsevenbundlesexcluded,Bebeownercoordpending/noBebepathaction. Histcleanproduction-sourceclone1.080GB+twohistoricalsiteworktrees1.501GB/25.575MBidentified,sourcecommitexistscanonicalbutallrefs/ignoredpreservationstillrequired.17.435GBnogitconsolidationsnapshotisnotcalledclone. NoactiveVODbuildpathprocessobservedpointintime;freshguardsstillrequired. Onecanonicalcheckout/commit-tag/immutableoutputworkflowdocumented,nocloneperDMG/no branchswitchdirtyoractive. Report/manifests build/recovery-20261011/disk-consolidation-audit-20261015/REPORT.md. Permanentcleanuprequiresexactper-targetapprovalafterrecoverability; movingTrashdoesnotfreespace. Noownedheavy/sign/nativejob.


## Site published / clean canonical app source / release qualification running — 2026-10-15T06:16Z

ActualsitepublicationACCEPTED: canonicalowner0f314e978e7b956cbbad81be6212a73e2daf58ef/maincleanpushed, existingCloudflarebuild3d7e42f2-3280-47ce-84f7-616dbdc8a918success, Worker6d77fb70-8af1-443e-b8b3-105555f55416at100%, https://getvodforge.com/ .305tests/build/24live390+1440pagechecksPASS; separateconsent/GPC/DNT/withdrawal/replay-off.1SDK-generatedtestpageview78fc269d-66f9-40a6-9399-71e4bc1ee776HTTP200→1exactUUIDrow. Notbrowserdedup/adoptionproof; CTA/outcome/performance/returnobservationsremainunobserved. Currentdownloadlinks0.2.5andpublicMac26ARM/15Intelunchanged. Receiptread /Users/coop/Documents/Codex/2026-10-11/task-2/vodforge-posthog-site-publication.json .No duplicatereview/deploy.

Appreviewbatch2384d53d9fa5889aa0e64c5e105856595746c6d0committed/pushedexistingqt-retirement. Followup4469ec4onlytest_qt_scene_port.py:3enabledproviderconsentgeometry/defaultunchecked/unsentchoicecasesPASSat1100/860/820width560height,alltransportsdisabled/privatefixtures.1982187onlygitignore: localgeneratedreviewreferenceoutsidepackageinputs, preservedSHA856abe7c3bbbb19f8482f1df99bdfa97f6ab53237dceef77a28e1fb44ee4d888;noGitpackageinputreferences. Canonicalstatusclean/provenancewriter1982187,onecheckout,nobranchswitch/noclone. No productPython/QML/assets/buildrecipechangesafter2384d53. Subsequentdocumentationcommitdoesnotrelabelartifactsourceidentity.

RequirednewsourceCIonce: Tests38690013666 pinned2384d53(sixplatform/Pythonlanes), compilation/backendpass,Qtcomponentsinprogressatreadback. Windows-onlyartifacts-onlyrecognizedBuildReleaseDraft38689991964same2384d53/version0.2.6: AzureexeSigning/strictverification/signedruntimesmokePASS;installerconstruction/signing/upgradegatespendingatreadback. Thisnewruntime/config/sourcebatchinvalidatesoldercommitCIidentity;oldunaffectednative/media/Trashreceiptsnotrepeated. No releasecreated/modified; publicapp0.2.5remains. No localbuild/sign/nativejob, onlypassiveCIwatchers. Currentremaininggates: finalstablesignedMac/Windowsartifact/source/version/feedqualification,priornativecorner/firstpaint/physicalInteldisposition,andlocalcapacity. ARM15runtimeexplicitlydeferred/nolowerpublicclaim,notusedaspublicationpermissionblock.

Diskfollowup: all23P2candidateZIP/extractedtrees/source/version/policymetadatafreshPASS17,882,636,288expandedbytes;exactpermanentremovalquestionpending(noapproval/noaction). Further20oldsourceZIPsfreshhashmatchretainedcanonicalcandidateZIPs5,795,266,560bytes;3absentoriginalsexcluded. P4separateapprovalrequired,notcoveredbyP2question. ConditionalgrossP1+P2+P3+P4=87,499,517,952bytes,beforebackup/APFSoverhead;notapprovedsafe/netreclaim. Currentapps/ZIPs/recovery5/Kryden8c75/profiles/evidence/journals/sourceassetsprotected. Nofilemoves/deletions/Trashpurge/VMdownload. Historicalretirementwouldmakeoldexpandedpathverificationcorrectlyfailuntilrestore; preserveoriginalreceipts+newretirement/recoveryrecord,nobackfill. Fullplan/manifests under build/recovery-20261011/disk-consolidation-audit-20261015/ .


## Approved P2 retirement / stable ARM sealing / CI fixture diagnosis — 2026-10-15

Cooper approved exactly the 23 expanded historical candidate apps in the verified P2 manifest. Fresh recoverability and process/path guards passed; only those 23 expanded app directories were permanently removed. All 23 retained ZIPs and original receipts stayed unchanged, along with current recovery.5 apps, profiles, source, journals and evidence. Measured free-space gain 17,929,805,824 bytes (17.93 GB); this is not an 80 GB reclaim. P1/P3/P4 remain unapproved and untouched. Exact per-path hashes/recovery mapping and retained metadata are in build/recovery-20261011/disk-consolidation-audit-20261015/P2-removal-result.json . Older extracted-path checks require restoration first; original receipts were not rewritten.

Stable 0.2.6 ARM package from clean ad17697 (runtime 2384d53) passed isolated frozen smoke, 384-runtime Mach-O/dependency audit, 118 compiled product-module and 47 QML source binding. Developer ID strict signature, Apple Accepted c3ac698f-2daf-49a0-8618-a8b67c88d6d3, staple and Gatekeeper pass. Final executable bac75c4cdfc4aaa432dbb92596087423b5089585c4f0a0fc3b2fd0dcbd4ace97; final file/source binding under build/release-026-ad17697-20261015/arm64/. Public ARM minimum stays 26; no ARM15 runtime claim. Initial relative-assets packaging failure retained; absolute canonical data paths corrected in the task launcher, with no product changes. Intel not yet built at this checkpoint.

Recognized Windows artifacts-only 38689991964 on 2384d53 succeeded: signed exe/installer, frozen smoke, updater faults and real isolated running upgrades production 1784ms/legacy 505ms. Both report relaunched 0.2.6, ui_click_verified=false; this does not prove an updater-button click. Production/legacy receipt and signed hashes are under build/recovery-20261011/posthog-release-20261015/windows-update-evidence/. No public app release has occurred.

Required Tests38690013666 backend/compile passes; Qt component failures retained per job in posthog-release-20261015/tests-38690013666-*.log. Test-only repair: layout-only review explicitly supplies Trash availability without deleting; portable directory avoids trailing spaces/excess path length; attribution double implements consent-epoch/mirror interfaces and realistic first-launch fields, verifies one mirror with no provider epoch; independent-scroll case expands enough genuine choices for platform font metrics; rate-control visibility waits for existing popup reveal completion. Original exact failing assertions retained. Existing checks missed ambient Trash availability, Windows path legality, evolving fake-owner interfaces, font-dependent overflow and parent animation readiness. Four affected test scopes pass 14 cases; final shorter-path fixture rerun separately. No runtime/QML/assets change or accepted native campaign repeat. Required CI successor remains necessary; prior failed CI is not relabeled passed. Public app remains 0.2.5; site publication already separately accepted. Remaining native corner/first-paint and physical Intel dispositions are unchanged.


## Stable packages sealed / owned signing slot released — 2026-10-15T06:53Z

Stable Intel0.2.6 on clean771f378 (test-only delta from ARMad17697, runtime2384d53 unchanged) now passes existing DeveloperID/deepstrict signature, AppleAccepted2c5dd592-bb3b-4df9-978e-75abb85c3267, staple/Gatekeeper, signed frozen Rosetta runtime smoke0,386runtime MachO audit,118compiled product modules+47QML source binding,7214sealed ZIP entries. Final owned ZIP renamed x86_64→x64 without byte changes to match existing updater contract. SHA1d7d6d42b0cfdf6d3b22bdd850a0ac4b5350b6391b9fd83d2d736a4495c80de4; executabled63c8377b86a405249785e55608f2726a8549666f868b72c076ad8191028a53e. ARM sealed7210entries/archiveeaecec112e4fdadbe72b09e4260473963379b82c28898c8c7aec7548c20ae98c retainsad17697 identity. Public minimum plist ARM26/Intel15 and consent-gated capture/replayoff verified in both actual packages. Local Rosetta is not physical Air acceptance.

Signed Windows artifact11952485283 downloaded once,644794897bytes/SHA0f7eb95e6adf4fe69f5a0b1699a6fdedaa31f02502eb4c4b91985fbd85414ce7. InstallerSHA63f2fc9d8bf92e9619e9b629dbb898b6f12725f4234577138c4ad51df607d44f and portable executableSHAd3b77ccfb798866ca43de445fe7dc8bad4e2323086216854ba84a5ab7382557f match independent original CIupgrade receipts; packaged buildrevision2384d53/provider capture configuration read. Not a new nativeWindows/UIclick campaign. Four actual release-asset hashes/checksum manifest and offline actual updater platform selection PASS at build/release-026-ad17697-20261015/publication-assets.json; public release/feed not changed.

Required test-only successor38693908550 is running once, all6compilepassed and Qt components underway; original38690013666 remainsfailed with all6logs retained. No redundant localfullsuite or old native/Trash repeat. Observer native coordination submission returned earlier-turn-not-confirmed, so delivery/availability NOT established; exact frozen provider-consent UI remainsunobtained. Existing fullcorner/firstpaint disposition and physical correctedIntel/Air native acceptance remainunresolved. No ARM15 runtime requirement imposed beyond explicitdeferral. Currentpublic readbackstillv0.2.5; site independentlypublished/downloads0.2.5. Local heavy/sign jobs finished and slot explicitlyreleased toKrydenowner; no nativeforeground/input/profileaction. Currentfree14,540,800,000bytes after release builds, distinct from measuredP2retirement gain17,929,805,824bytes. Full handoff build/release-026-ad17697-20261015/RELEASE-HANDOFF.md; ignored status/checkpoint current. Documentation-only checkpoint does not relabel signed binaries or invalidate existing runtime checks.


## Overnight continuation / source-bound Windows payload / stale scene expectation — 2026-10-15

Parent explicitly directs continuing through CI terminal result and permitted native acceptance. No cleanup beyond approved23. Existing Python3.13/PyInstaller read actual signed Windows executable from downloaded portableZIP: all118 frozen product code objects match canonical source after normalizing only co_filename; all47QML UTF8text match with explicit GitWindowsCRLF conversion (rawbytes differ for all47). No Windows UI/runtime/provider trial. Receipt posthog-release-20261015/windows-release-38689991964/frozen-source-binding.json . Main-integration merge-tree preview is conflict-free and exactly currentHEADtree78e7ab546ac6b93d56dab58026bfd6948381d0ba; no checkout/branch mutation. Existing authorized optionalUX policy already matches localmain; no scoring/gate relaxation needed.

Existing privatev0.2.6draft found (targete614d2018f7af9a7f7a2c1d4c876cb94b8da0bef), with four stale canonical assets/oldchecksums and three historicalQAattachments. Inventory/hashes saved existing-draft-026.json and existing-draft-disposition.json under release-026-ad17697-20261015; no deletion/clobber/rename/release mutation. New local signed packages/checksums are not thisold draft. Publicapp remains0.2.5.

RequiredCI38693908550 both Mac Qtcomponents pass848/9skip; Mac3.11scene211pass/1fail exposes stale1180x790 Forge golden row expecting removed breakpointpadding120/94. Standalone same assertion fails before with actual acceptedcontinuousinset62/78. Correct only that independent expected row (URLwidth799/destinationx270); all exact controlorder/bounds assertions retained, no timing wait or relaxed tolerance. Target after1pass/Ruffformatdiffpass. Existing cross-breakpoint/reversal/defaultinset coverage and actualCooper recovery1 acceptance retain identities; no product/QML change or build repetition. Other matrix jobs stillrunning; preserve terminal originals and collect other failures before one further requiredCI dispatch.

Fresh authorized Air status06:58:39Z: exact100.84.96.112 Julies-MacBook-Air Onlinefalse/Activefalse, LastSeen06:50; noSSH attempt/wakeup/access change. Native registry has noCUA/js_repl; observer submissions including explicit returnedhostdurable remain Earlierturnsubmissionnotconfirmed, parentmcpthread notfound. No native lease/input established. Prepared only fictional native-consent-fixture HOME via existing AnalyticsConsentOwner cachedopt-inregion, analyticsfalse/PostHogfalse/nochoices; avoids policy lookup without hiding production UI. Exactapp/hash/procedure/attestation local, notnativeproof. Physicalcorner/firstpaint/Intel acceptance unresolved; ARM15explicitlydeferred. Localheavy/sign clear and Krydenheadlessslot coordinated/released independently.


## Terminal CI oracle failures consolidated with rendered evidence — 2026-10-15

38693908550 is terminalFAILED, all6compile/backend and all6Qtcomponent lanesPASS848/9skip. Original six per-job logs retained: Macscene211pass/1fail; Linux210pass/1fail/1skip; Windows207pass/4fail/1skip. Mac/Linux only obsolete1180x790 breakpointpadding expectation; Windows additionally rawcontent-origin32pxoffset and iconprobe globaltop-leftcrop contaminated by integratedcaption titleglyphs. No new productfailure inferred from these test-oracle defects.

39ea2a8 exactcontinuous-inset expectation now supported by actual production-QML source renders820x560/1100x740/1180x790: at1180 command62,78,1056,48; URL799; Download precedes Options, allcomposerbuttons fullyvisible. Before standalone1fail; after1pass. Screenshots and geometry/source/environment SHA receipts are in composer-render-evidence/. Both1100/1180pixels inspected. Native Windows retained840capture additionally inspected/hashmatched2b96abba2af54645153e0c65c33abe6b6f58fd298c02ecbae955b63c45eb13e4; actualcaption32px, currentWindowsFrame.qml byte-identical to840source andsameMain content-toprule. It is prior native evidence, not new signedWindowsUI proof.

Test-only Windows followup adds independent32pxcaption origin to exactheader/navigation/library/composer yassertions and independently asserts visiblecaptionbutton32pxheight. No x/width/controlorder/tolerance/assertion removal. Iconpixelcontract now uses separate96x96QQuickWindow containingactualSceneIcon; connectedcomponents==1 and width/height extents unchanged. Bothisolatediconrenders inspected; strictMacfocused4casespass in5.71s/Ruffformatdiffpass. Windows runtime result remains to be checked by the single consolidated requiredCI successor; no unsupportednative/physicaltiming claim. Broader owner-boundary lesson addedREADME, no runtime/QML/assets/dependency/build changes, no rebuild/unrelatednativecampaign.

Standalone nativeconsent review remains prepared/unlaunched; noCUA/js_repl and observermessage delivery unconfirmed evenexplicitdurablehost. ExactAir peer offline at06:58:39, noSSHattempt. Existing stale0.2.6private draft inventoried/unmodified; allnewstablepackages locallysealed, expectedbundle/team/runtimeidentityverified. Publicapp0.2.5 andpublishedsiteunchanged. Parentovernightauthorizationretained; continue requiredCI through terminal result and any permittednativework, withno broadercleanup.

## Draft upload review and production version admission — 2026-10-15

The exact four sealed signed 0.2.6 packages plus SHA256SUMS upload to SnowfallHD/vodforge unpublished draft was rejected by automatic approval review before the upload process started: possible proprietary package disclosure and unclear exact payload/destination authorization. No new assets or release were created. A prior reversible draft metadata rename was rolled back: same release ID, original e614d201 target/body/title/draft status and all eight asset IDs/sizes/digests retained. GitHub regenerated the private untagged URL; both URLs and exact rejection/rollback are recorded in build/release-026-ad17697-20261015/upload-approval-blocker.json. Existing draft contains stale packages and must not be published as-is. Additional read-only evidence confirms the repository is public with viewer ADMIN, published source ref and all 118 compiled product modules/47QML plus 101/101/102 packaged product assets bound to canonical source. No alternative upload route attempted. Exact-payload draft-upload approval question is pending; native acceptance remains independent.

Canonical website owner performed one metadata-only production SELECT: stable 0.2.6 already has enabled=1/release_order=17, one row read/zero written/database unchanged. No separate registry mutation required. Original owner receipt copied to build/release-026-ad17697-20261015/production-version-registry-read.json; no duplicate DB query. Latest site copy-only376f290/Worker4a0d137d passed33focused/build/12live state checks; collection/consent/replay/downloads0.2.5 unchanged. Required CI38699401218 still running at this checkpoint; Mac3.11/Mac3.13/Linux3.11 passed, other lanes pending. No build/sign/native repetition.

Fresh Intel peer metadata08:02:49UTC still Offline/Inactive, LastSeen06:50; no SSH attempt/wakeup/access changes. Initial sandbox Tailscale CLI preference-load failure retained; authorized host read succeeds. Native tool registry still has no CUA/js_repl, so final packaged enabled-provider consent fixture remains unlaunched. Prepared release text now explicitly states existing ARM26/Intel15 requirements, no artifact or public download change. ARM15 runtime remains deliberately deferred. P2-only23-copy retirement remains the sole approved/performed cleanup; no further deletion.

## Final six-lane CI success — 2026-10-15T08:17Z

Required Tests38699401218 on exact cb571c7 is terminal SUCCESS, all six Mac/Linux/Windows Python3.11/3.13 lanes. Backend per lane: Mac5954pass/43skip, Linux5944/53, Windows5975/22. All six component suites848pass/9skip; scenesMac212pass, Linux/Windows211pass/1skip. Windows updater faults28pass/4skip each. Six completed original logs with SHA256 and exact summaries saved in build/recovery-20261011/posthog-release-20261015/tests-38699401218-terminal.json. Strict continuous-inset/caption-origin/connected-icon assertions now pass on all intended platforms; no skip/tolerance relaxation. Earlier38690013666/38693908550 failures remain preserved. This documentation-only checkpoint does not change product inputs or require rebuilding sealed ARMad17697/Intel771f378/Windows2384d53 artifacts; runtime remains2384d53.

All local build/sign/native operations and passive CI watcher are finished. Public latest/downloads remain0.2.5. Exact draft upload approval remains unanswered; no approval inferred and no upload attempted after rejection. Native consent fixture unlaunched due unavailable supported controller; physical Intel remains offline; retained corner/first-paint limits unchanged. Handoff, exact publication manifest/checksums, approval blocker and native blocker are under build/release-026-ad17697-20261015/. No additional cleanup, user profile change, ordinary app input, broad media/Trash campaign, or production registry mutation.

## Comprehensive desktop PostHog successor source — 2026-10-15 evening

Cooper explicitly authorized comprehensive additive desktop+website PostHog implementation and actual production verification, preserving existing custom analytics. Canonical qt-retirement remains the sole checkout; earlier sealed stable packages/evidence stay unchanged. Actual framework is PySide6 Qt Quick/QML. Live PostHog documentation lists webJS/RN/iOS/Android/Flutter replay SDKs, no Qt/Python recorder. Implemented semantic sessions/ordered safe feature and operation events, standard $screen companions from actual closed routes, categorized manual $exception companions with static values/empty frames, bounded performance/count categories and build/source context. No screenshot, accessibility tree, media, content, raw errors/stacks/locals, credentials, source URLs or paths are captured. Existing15 custom event names, first-party queue/credential/acknowledgement and first-launch path retained.

Shared schema2 contract coordinated with website owner: additive application_lifecycle nine actions, required closed views/exception categories, no operation correlation on lifecycle. Actual local app/site vocabulary comparison PASS. Provider-only UUIDv7 session/sequence/coarse elapsed time and QA labels remain absent from the first-party public envelope. QA sets release_channel=test/measurement_scope=qa/is_test=true plus UUID4 qa_run_id/validation_id; dashboards must exclude all three QA predicates, including historical test traffic. No alias/cross-device join or completed GitHub transfer claim. Separate connector reviewer owns dashboards; no duplicate dashboard writes here.

Fresh regional provider metadata version2 uses resolved=true plus generic default-on and explicit posthog_mode=default-on from the parent-reviewed policy. Missing provider metadata/old generic cache cannot grant provider permission; all saved general/provider refusals persist. Existing optional choice UI remains in opt-in branches. Provider outage previously lost an event after custom ack; current existing-outbox retry persists separate outcomes/backoff, stable UUIDs and first-run mirrors, does not resend custom ack or head-of-line block custom delivery, and records explicit capacity/expiration discard rather than fabricated ack. Legacy already-settled mirrors are not backfilled.

Prior-source negative controls on4c12a78 independently fail lost session/QA projection and provider failure persistence; current controls pass. Initial control runner import-path failure retained separately, not claimed as a product failure. New lifecycle insertion initially triggered idle retry before startup consent settlement; corrected at the Qt session scheduling owner, retaining the original idle retry assertions. A broad vocabulary fixture now supplies required exception/view fields rather than disabling actions. Final affected owner/privacy/attribution suite134pass; affected Qt/privacy/producer/credential suite146pass; three enabled-provider scene cases included, strict bounds/choice assertions retained. Ruff/format/diff checks pass at source checkpoint. Original intermediate failures/logs remain under build/posthog-comprehensive-20261015/source/. Mandatory broader lesson added README.

A bounded QA CLI seam requires an exact UUID4 label, attested fictional HOME/LOCALAPPDATA, fresh contained receipt and offscreen renderer; it cannot grant consent or choose transports. Planned new immutable private ARM version0.2.6/sourceSHA output uses existing version admission and ARM26 floor; old packages are not replaced or uploaded. Follow with independent exact labeled PostHog AND first-party production readback after website validator deployment. No new credentials/settings/grants/spending/publication. New runtime changes invalidate earlier CI/package identity as successor proof; new required CI/build is necessary, without repeating accepted Trash/media/native campaigns. Native replay, physical Intel/native UI acceptance and actual production outcomes remain unproved at this source checkpoint.

The maintained telemetry-release contract generator initially failed25 cases because its broad positive fixture omitted the new required exception/view dimensions. Added only those required closed fixture values, retaining every generated action and validator assertion; successor148pass/1.42s. Original failure and successor logs retained. Live replay documentation additionally lists Unity; no Qt/Python recording SDK has been found, and both requested experimental recording paths are being investigated separately on synthetic offscreen UI. No production recording enabled.

## Comprehensive desktop actual frozen production proof — 2026-10-15

Exact runtime dc4c61067548a33005fb1d086daf52f1c560c2af committed. Public push was first rejected by automatic approval review for destination/exact-source authorization; live canonical public SnowfallHD/vodforge ADMIN verification alone did not resolve it. Cooper explicitly approved this exact source and CI at19:27:33UTC; one retry succeeded, required Tests38794177948 dispatched once. No binary release upload/replacement/publication. New targeted Windows artifacts-only source-pinned CI is separate from release publication. Prior sealed assets remain unchanged.

Local maintained backend suite5967pass/44skip/13sandbox PermissionError failures; only those13 localhost/process cases reran with required host access and all13pass/6.45s. Initial interpreter-resolution harness failure retained separately; not a product failure. ARM maintained recipe/runtime smoke pass;120 compiled product modules and47QML source-bound. Apple notarization Accepted f1ccb72b-44da-4e80-be97-3529b7865805, staple/Gatekeeper pass. Archive SHA2562a146259809ef1aa372b81b37eb8e7b67b024c1baa5800b4f953654aef59b617; executable1ebf13251efecb5021d295c7f3b190ce5dc301c15be2f690433374982240efe1. Actual frozen-module97focusedchecks pass. Full sealed file/link comparison after QA has zero changes; host strict signature verifies. Sandbox codesign alone misleadingly reported invalid despite unchanged bytes; host read-only verification succeeds, no re-sign or candidate repair.

Website validator dc92f947ca4b2fea2b0e946a2b56df0e7c41ac05 deployed through existing main-trigger build6aff6780, Workerf24c3ca9 at100%, no DB migration. Only then ran exact signed frozen app with fictional explicitly consented profile, offscreen/label62f703a9-a27f-42b7-ba9e-be2f7dbe929e. Normal exit0; canonical first launch acknowledged; custom/provider outbox empty. Independent PostHog query has18rows, one UUIDv7 session, all QA filtered:1app_opened,14feature_used,1first_run_confirmed,1screen,1exception. Exception issue ID exists, static content/empty frames; no controlled raw error text. Website owner independently queried production D1: exact same15 canonical IDs once each and first-launch/version0.2.6; rows_written0. Independent set comparison passes. No adoption/media activation/binary transfer or all-vocabulary claim. Denied isolated profile expected exit3/refusal, firstlaunchfalse/outbox0; provider exact-label zero rows. No ordinary profile/native foreground input. Both-pipeline receipts, original queries and limits under build/posthog-comprehensive-20261015/dc4c610/arm64/.

Parent-requested replay alternatives tested separately in ignored replay-investigation/: actual installed PostHog rrweb player accepts synthetic semantic and Qt-JPEG streams at0/15/29seconds; separate viewer session/frame hashes match.13fail-closed cases, private-value pixel invariance and deliberate leak negative control pass.30frames960x600: JPEG715090bytes, semantic JSON5806/gzip664, image JSON958907/gzip190492. Public-only mirror excludes media/text/artwork; not original app/GPU visual capture. Live docs additionally list Unity; no Qt/Python recorder or supported custom-import contract found. No provider snapshot upload/storage provisioning/production recording. Report contains measured overhead, cost assumptions, access/retention/retry/privacy requirements and remaining actual provider/native gaps.

First-party attribution boundary discovered: Qt explicitly disables browser-opening adapter, so an unopened pending claim does not poll on normal restart. No local state backfill/forced claim/opening or inferred provider join. A possible separate fresh controlled browser claim consume is coordinated with website owner and must be labeled as that fixture only. Intel source-aligned private candidate is building separately after actual reserve/process guards; Windows artifacts-only dispatch targeted to exact approved source. CI and these successor artifacts remain pending at this checkpoint; no prior package relabeled.

## Explicit recoverable Qt installation-link action — local successor, 2026-10-15

Parent explicitly authorized repairing the actual Qt non-opening adapter after browser-only proof. Existing signed dc4c610 remains immutable; this later source is not included in its accepted packages or CI. Added explicit Settings Link this installation action and browser disclosure, guarded by general analytics permission (provider choice stays independent). Worker preparation never opens a browser; actual QDesktopServices dispatch occurs on the GUI polling owner only after the user's request, then canonical opened acknowledgement and claim polling run. Startup still uses the non-opening adapter. No new endpoint/event vocabulary, automatic browser launch, provider alias/raw token, manual success flags or production retry.

Two shared-owner regressions independently failed before: browser acknowledgement persisted after withdrawal, and an old claim response confirmed a replacement capability. Added token-conditioned durable transitions, consent-epoch/cancellation checks around asynchronous boundaries, and explicit retry preparation without reopening at startup. Existing expired-claim acknowledgement semantics retained after the original test exposed an over-broad clear-state change. Migrated profiles remain ineligible for automatic enrollment but an actual explicitly opened claim can poll.109 attribution/cloud/Qt-owner/consent/provider/lifecycle/QA cases pass, including new/legacy profiles and denied/reenrolled/closed/browser-failed paths. Six affected actual scene checks pass; two additional rendered cases pass with inspected820x560 and1100x560 screenshots, actual QML click, canonical mocked status acknowledgement, disabled consent control and reachable action/footer. Initial scene harness used the wrong pump name, then its intentionally disabled global transport also blocked the mocked domain; both originals retained and corrected fixture setup keeps all real transports off. Initial broad test command named an absent file, retained as collection failure. No assertion/timeout/gate weakening. Ruff/diff pass at checkpoint. Broader owner-boundary lesson added README.

Fresh authorized normal-browser attribution proof is separately complete for old signed dc4c610 fixture4eaa640b-d133-463e-be52-2c88675af7d0: installed normal Chrome with isolated profile/no UA-brand-webdriver overrides, one canonical consume claimed, one tagged D1 browser link/download-intent row, one provider vf_web_installation_link_confirmed715cd058-02a3-4c41-9976-992db354f867. Raw capability/install UUID absent from provider; no alias/replay/binary transfer; browser/port closed. App-local opened/confirmed remain false in that old package and were not changed. Prior partial fixture retained; its zero provider rows came from bot-filtered HeadlessChrome, while actual duplicate controller admission was fixed in site0b3273a via main-triggered build7321e447/Worker87af5f63 at100%. Root copied original D1/provider/E2E receipts. These are distinct from local successor private tests.

Intel dc4c610 build/runtime smoke97frozen checks/386Mach-O audit<=15 all pass. Signing tool session disappeared with no surviving process and an empty local result; no duplicate submission. Existing Apple history/log recovered Accepted50fd29bf-8927-4826-8570-543dd8c2decd with SHA256 exactly matching submitted ZIP67ed591a03b510162d43fb219788895c5f78bbcac19a09cbb33982a44d24929a. Continued only staple/Gatekeeper/seal, source-bound120modules/47QML. Final archivea6ef25a34b9e3596b356faef0beeeaed9995926facb2b7d4ba3048b7605b9b41, executablee06c8dddf784526246e176ae1bc9dd2e07e2632f3ae56a55efa0c216879ceffb. Physical Intel acceptance remains absent.

Windows artifacts-only38795764166 failed at baseline cold-window visibility30182ms, BEFORE candidate handoff. Candidate build, signatures/runtime smoke passed; failed baseline PID6768 had only invisible/untitled measured windows. No new-runtime cause inferred, no30second guard relaxation/retry. Original log,1.6KB diagnostic artifact and signed diagnostic artifact IDs retained under dc4c610/windows; archive artifact645538604bytes retained remotely. Release job skipped. Required Tests38794177948 five lanes passed, finalWindows3.11 pending at this checkpoint. User's exact older ad17697 publication-manifest draft approval recorded separately and not applied to changed analytics bytes. Public0.2.5/assets/ordinary profiles remain untouched.

## Private attribution artifact and Windows phase diagnosis — 2026-10-15T20:31Z

Runtime914b0eb457d092ee54d2e585f5be7303c0e1b1c8 remains local/private. Maintained ARM0.2.6 build/runtime smoke passed, Apple Accepted01441cac-2570-4521-80ef-ebd20be9be75, staple/Gatekeeper/seal pass.137tests import actual frozen product modules and pass;120compiledmodules/47QML bind exact source.384runtimeMachO objects have ARM slices/no errors; highest internal declaration15, package policy floor26 retained (no ARM15 hardware acceptance or floor change). Earlier dc4c610 six-lane Tests38794177948 is now terminalSUCCESS with original full log retained; this CI does not cover914. No914public source push or binary upload/user app replacement occurred. Strict5GiB space/process guards passed serial builds; no historical/user/cache cleanup. Only the completed Intel signing helper's own temp submission ZIP was normally retired after preserving accepted SHA-bound log/final archive and interrupted empty result.

Windows38795764166 original receipt/runner ordering proves failure in baseline_startup30182ms before candidate handoff, not updated-startup. PID6768 remained alive with two invisible untitled768x519 windows; activity only says Session started. Baseline startup/renderer/host cause remains unresolved; cached public0.2.5 source is not a measured hash binding to this failed CI launch. Candidate build/sign/runtime smoke passed, native upgrade acceptance did not. No duplicate expensive CI or user-device app launch. Recoverable diagnostic defect fixed separately: explicit baseline/updated visibility subject, phase before fallible operations, baseline PID/hash/version and candidate/installer hashes recorded before baseline wait. Production30second/PID/path contract unchanged. Actual existing Genesis SSH identity guard then in-memory PowerShell control-flow execution passes delayed-window, wrong-path, updated invisible and baseline invisible cases; no remote files/apps/install/profile/native input. Local Mac PowerShell case skips; unchanged diagnostics process test again hit sandbox PermissionError (prior same-source host-context pass remains valid), not a new product failure. Do not infer native acceptance from these doubles.

User explicitly approved only the older release-026-ad17697 publication manifest's4packages+checksums. Fresh5file hashes/size/checksum mapping match; current914/dc4bytes are not substituted. A separate clearly pre-comprehensive unpublished review draft preserves existing assets. Initial GitHub422 invalid short target was retained; expanded the already-public ancestor to fullad176976655a3b937175ca6f6675ead880a83d41 and resumed only the same authorized payload. Upload verification is pending at this checkpoint; publiclatest0.2.5 remains the baseline. Parent-requested owned website provider-replay UI playback remains unverified because current native/browser-controller tools are absent; no signed-in-state or playback claim was inferred.


## Exact D1 QA reconciliation and approved draft completion — 2026-10-15

Health inspection found30 macOS0.2.6 D1 rows retained production release_channel without inlineQA fields. Provider-only labeling was insufficient for first-party health/adoption; exclusions should have been registered before the two controlled runs. Independent metadata-only production SELECT returned30rows/zero writes. Local reconciliation compares UUID plus event_name/feature/action against the two original provider/run receipts:15each for62f703a9-a27f-42b7-ba9e-be2f7dbe929e and4eaa640b-d133-463e-be52-2c88675af7d0,30exactmatches/zero duplicates/zero unmatched. Both controlled unhandled_exception rows are QA. Exact-ID mapping and read-only anti-join saved source/first-party-qa-reconciliation/{reconciliation.json,exclude-owned-qa.sql} under build/posthog-comprehensive-20261015; health owner received the complete portable UUID groups. No rows renamed/deleted/relabeled, no broad time/version exclusion and no adoption claim. Future production QA held until preregistered exclusions or separately supported first-party QA markers. Contract documentation now makes this cross-sink distinction explicit; no runtime change or repeated campaign.

User-approved older manifest upload completed: separate unpublished review-0.2.6-manifest-20261015T065057Z draft, four exact packages plus SHA256SUMS.txt,1,260,681,378bytes. Independent remote inventory matches all5approved names/sizes/SHA256 digests, uploaded state and drafttrue. Public latest release ID/tag and every public asset identity/size/digest remain unchanged atv0.2.5. No currentdc4/914binary substitution, no existing-draft overwrite and no publication. Evidence source/approved-old-draft-upload/{verification.json,remote-final.json,public-latest-before.json,public-latest-after.json}; private URL https://github.com/SnowfallHD/vodforge/releases/tag/untagged-8634bc5cb075f6e8001a . Earlier upload rejection and short-target validation failure remain preserved. Native source914live-claim acceptance, Windows baseline-startup cause, physicalIntel acceptance and owned website replay provider-UI playback remain unresolved; no native/browser-controller capability exists in current tool registry. All owned build/sign/upload operations finished; ordinary apps/profiles unchanged.


## Windows baseline diagnosis and exposed acceptance routes — 2026-10-15

Source/log-only follow-up confirms38795764166 selected public0.2.5 installer (retained published SHA760a9bf0833f76c0d827c827858970e2edad00283f2c356fd8860bcb334a3b79), installed successfully and launchedPID6768 in isolated installed path; failed30.182s first baseline visibility wait. Old receipt lacks measured installedhash/version, so exact failed baselinebytes cannot be retroactively asserted. Candidate0.2.6 installer was built/signed/verified but NEVERexecuted in this journey; no helper/legacyhandoff. Underlyingstartupcauseunknown. Sessionstarted precedes remaining Bridgeconstruction/QMLload, invisiblehelperwindows alone cannotlocalizestall. No graphics/timeout workaround inferred.

Local harness now captures baseline stdout/stderr and its existing--ready-file acknowledgement under already retainedfailure-diagnostics; exactPID/path/30sgateunchanged. Actual Windows PowerShell ASTparsePASS through identity-guarded existingSSH; no application/installer/filefixture/profile/nativeinput. Prior four-case windowcontrolflow pass still applies to unchanged gate; not repeated. Complete diagnosis/nextboundedbaseline-only disposableCIrecipe saved build/posthog-comprehensive-20261015/dc4c610/windows/BASELINE-DIAGNOSIS.md. No newCI/build/sourcepush/nativeacceptance.

Supportedroutes rechecked: no cua_repl/js_repl/browsercontroller/toolsearch in actualregistry. TerminalPlaywright cachedCLIworks with appbundledNode; nativeHomebrewNode failsmissinglibsimdjson29, no systemrepair. Supportedread-onlyCLIlist returnedbrowsers[]; no authenticatedexistingChrome session exposed and ordinaryloginstateunknown. Dependencyloader reportslocal-thread-only. No permission/CDP/extension/profile/authchange or browserlaunch. ProviderownedQAplayer stillrequires existingChromeuserPlay confirmation;137frozenownertests remain NOT live Qtclaimacceptance. FutureproductionQA exclusionregistration remainsrequired.


## Live repaired ARM fixture launch and native ownership transfer — 2026-10-15T22:17Z

Cooper22:13UTC explicitlyrequestedlivetest; created one fictional914profile with general/providerconsentfalse, claimflagsfalse, no manuallyacknowledgedstate. Healthownerpreregistered exactinstallation andproviderQAlabel16e7a584-c164-46f9-a782-58e8d47b9312 BEFORElaunch; actualeventUUIDreconciliationfollowsadmission. Exactsealedexecutable2bc4b475523fbce870c057e94ee115d23b2ed1536ef684ff87e9ba9d5832d5ca launchedonce22:16:52UTC PID25448. ActualQtreadycocoa/visibletrue/nativeheadertrue1100x740; independentAppKit+CGmetadata22:17:23confirms onscreenVODForgewindow15201/alpha1/layer0. No rootUIactions; firstlaunch/opened/confirmedfalseattransfer. Originalmetadata serializationfailedNSDictionary then corrected todict, no applauchrepeat. Receiptroot build/posthog-comprehensive-20261015/914b0eb/arm64/live-claim-ui/.

Rootregistryhasnonativecontroller andnopromptAXfalse; no grant/bypass. Parentcreatedseparatelivetesttask01a141a4; soleexistingprocess/profileownershiptransferredandacknowledged. That task's supportedcua_repl works: actualGetstarted/Settings/Privacyclicks and Off/Off/disabledlink observed, exacthashverified, no duplicatelaunch. Rootdenial is contextspecific, notclaimofhost-wideunavailability. All further UI/browser/fixtureobservation ownedbylivetesttask; rootcontinues onlyindependentsource/logwork. No Windowscontact: taskauthorizationfalse; Inteloffline/unauthedunchanged. No137testsubstituteforliveclaim.

IndependentretainedWindowscomparison finds source2384d53 production/legacyupdatepasses withmeasuredbaseline0aa2e2.. andbaselinevisibility10202/5333ms, updated1784/505ms. Currentfailurebeforehandoffcannotestablishnewcandidateinitializationregression; missingcurrentbaselinehashpreventsabsoluteequalityclaim. WindowsworkflowoffscreenassignmentsaremacOS-only; childruntimesmoke doesnotsetparentenvironment. No offscreen/rendererfixinferred. Priorreceiptshashboundin dc4c610/windows/prior-baseline-comparison.json; no acceptedcheckrepeated.


## Actual repaired claim acceptance and denied cold-display defect — 2026-10-15

Separateauthorizednativeowner01a141a4 performed actual914Settingsconsent actions, oneLinkclick, app-openedcanonicalbrowserclaim, observed Installationlinked and canonicalfirstlaunch/opened/confirmedtrue. General/providergrant/refusal retained across Off/On; finalsaveddenied/denied. Normalquitpreservedflags; samefixturecoldrelaunchPID28819 retaineddenied/denied andallclaimflags, no surprisebrowser, but UIincorrectlyshowedgenericdisabledLink. Originalclaimsuccessremainsvalid; cold-displayFAILpreserved. Healthindependentreadbackexact17D1/sevenprovider sets unchangedafterdeniedcoldlaunchthrough22:25:50UTC; exclusionspreregistered/nodatamutation. Freshwebsite-refusalnotcovered. Nativeownerquitnormally/released; rootdidnotinspect/controltransferredprofile. Sanitizedoriginalreceipts copiedhashboundunder914b0eb/arm64/live-ui-results/.

Sourcecause: constructorneverhydratedlinkpresentation, refreshreturnedoffbeforeloadingconfirmedfact. Localfixhydratesonconstruction/choiceandchecksconfirmedlocalstatebeforeactionpermission; browserrequest/deliveryguardsunchanged. Sixcoldmatrixcasesconfirmed/pending/absent×allowed/deniedconstructtwice, installationbytesunchanged/deniedbrowserforbidden. Originalfirstfixturehadinvalid48charclaimtoken; correctedto43beforegenuineprior-sourceevaluation. Correctedprior5fail/1pass, afterall22sessiontestsPASS;69attribution/cloud/consent/sessioncasesPASS. Ruff/format/diffPASS. BroaderlessonREADME. This is sourcefixonly, notlivefixedpackageacceptance; sealed914bytesunchanged.

SuccessorbuildspacepreflightusesexistingcompleteARM2,520,051,712byteenvelope+419,430,400temporaryreservation+5GiBreserve=8,308,191,232bytesrequired. Actualfreebelowguard; no build/sign/nativejourneyorcleanupstarted, reserveunchanged. Exactbytesreceipt source/cold-link-successor-space-preflight.json. Windowsunauthorized/Intelofflineuntouched; nopublicpush/release.


## Read-only cache cleanup proposal — 2026-10-15T22:31Z

Parentrequestedexactapprovalcandidateinventory; no delete/move. Restrictedthreeoldtask-ownedPyInstallercaches: dc4c610/arm64=680419328allocatedbytes, dc4c610/x86_64=809005056,914b0eb/arm64=680419328; total2169843712allocated/2167670061logical. Zero symlinks/hardlinkedfiles; retained--cleanrecipes/pinnedvenv/originaltools+Git regeneratetheintermediates. All dist outputs/ZIPs/seals/source/metadata/profiles/fixtures/media/failedreceipts protected. pyinstaller-work~159.6MBdiagnostics deliberatelynotproposed. Onecanonicalworktreeonly. Freshhostprocesspath/openfilecheck no cacheusehits/no unreadablecheckedboundary; onlyinventoryprocessrepo-related. Threecandidateexecutable+archivehashpairs freshlymatchsealedreceipts; metadatafingerprintsretained.

Atinventoryfree6307840000, required8308191232 inclunchanged5GiBreserve; estimatedafterexactthreecaches8477683712, surplus169492480. APFSsharedextent/diskfluctuationmeanreclaimnotguaranteed; freshguardrequiredafterexactapproval, no reservechange. Read-onlyreport build/posthog-comprehensive-20261015/source/cleanup-inventory-20261015/REVIEW.md plus inventory/process-use/protected-preservation JSON. No actionauthorizedbythisproposal.

Potentialfuturehelper-onlysaving: retireonlynewnotarysubmissionZIPafterAcceptedSHA/result/logpreservationandstaple/verify, beforefinalZIPcreation; avoids~288MBoverlap, insufficientalone. No helpers/oldtempfilesmodified. COLLECT/BUNDLEoroldcache-reusechangesnotadopted; preserve maintained build/provenance. Source9846eb0regressions69PASSremainvalid; no unchangedtests/buildlooprepeated. Nativecoldsuccessorawaits capacityandexactsignedcandidatehandoff.


## Automatic website-owned attribution restoration and build-cache lifetime — 2026-10-15

User explicitly superseded manual prerequisite/no-startup-browser and app-usage gate for browser attribution. Qt now supplies real GUI-owner QDesktopServices opening, once per new eligible installation via durable attempt admission; failed dispatch/cold restart does not repeat opening. Opened pending capabilities resume bounded canonical polling only. Manual Settings action remains recovery. Usage Off still prevents usage first-launch enrollment/events/provider; browser claim confirmation no longer turns usage On. Operational claim issue/status remains build/cancel/token-owner guarded and independent of app usage. Website must separately require eligible retained referral + applicable browser permission and stage issue without canonical acquisition creation. Site owner is implementing that additive staging/consume contract; not deployed or live-qualified here. No historical production automatic-completion proof claimed.

Four actual automatic-opening regressions fail before; 82 affected attribution/cloud/consent/Qt cases pass after. Six strict real Privacy scenes pass after compact copy and grouped10px section spacing; long-copy/intermediate geometry failures preserved, no assertion relaxation. Earlier21Options checks remain valid. New Qt module added to both build/CI process-isolation lists. Broadened affected build-policy suite found disabled deliver_first_launch instantiated a consent owner before its global-policy fence, creating installation state: fixed by returning before owner construction; unchanged denial/no-persistence assertion now passes. Final combined99tests pass (automatic/session/attribution/cloud, cache child-process, release/preflight/metadata/build-policy); mypy prior3modules pass, Ruff and shell syntax/diff pass. Original failures remain under build/posthog-comprehensive-20261015/source/. Signed914/dc4 artifacts unchanged; no successor build, production QA, source push or public release.

Disk audit confirms exactly ONE canonical Git worktree; source checkout duplication is not the cause. `du` build total193150472KiB (~184.2GiB allocated), .git211376KiB; accumulated retained candidate outputs dominate. Recent comprehensive root7795568KiB includes three dist trees4626588KiB, final ZIPs880168KiB, three binary caches2118988KiB and159641600bytes work diagnostics. --clean only resets the selected PyInstaller cache; per-candidate old caches were never automatically retired. Signing's EXIT trap retires its own temporary submission directory, not retained candidates; final ZIP overlaps submission ZIP until exit. Reproducible caches and immutable evidence had been retained together too broadly.

Maintained macOS recipe now runs PyInstaller through scripts/run_with_ephemeral_pyinstaller_cache.py: a fresh invocation-private cache is removed on normal child success/failure, without touching any caller cache, dist/rollback/archive, work diagnostics or receipt. Two real subprocess cases verify exit0/7, cache absent afterward, retained caller sentinel/output preserved. Abrupt host/process death can still orphan a temp directory; no universal cleanup guarantee. Existing caches are NOT retroactively deleted. Exact three-path2,169,843,712byte retirement proposal remains separate approval, documented cleanup-inventory-20261015/REVIEW.md; old23-expanded-app approval does not cover it. No cache/output/user/shared deletion or move occurred. Unchanged5GiB reserve,8,308,191,232byte required envelope; last inventory6,307,840,000free =>2,000,351,232short. Fresh guard mandatory after exact approval; APFS reclaim/disk movement can invalidate projected169MB surplus.

Independent read-only0.2.5 history: actual remotev0.2.5 ref850e19e/publishedOct10 verified. Released app uses generic mutable server mode with cached version1; release-era/current site source both EEA+GB opt-in/other resolved codes default-on, no desktop PostHog/replay integration. Exact release-day Worker state unrecovered; no research/legal clearance inferred from implementation. Source copies/rationale/report retained source/historical-025/REPORT.md. No new tests or runtime changes for that historical question.
