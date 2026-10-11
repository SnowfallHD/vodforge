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
