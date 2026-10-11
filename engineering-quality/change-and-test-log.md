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
