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
