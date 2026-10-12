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
