# Finite 0.2.6 recovery checklist

Cooper authorized public app release and new site publication on October15.
Public0.2.5 is still current because final source/artifact/native gates remain
pending; publication permission itself is no longer blocked. Mac support claims
stay unchanged until actual AppleSilicon15 testing. Historical HELD statements
below retain their original timestamps and are superseded only as to permission.
This is the single recovery decision list; automation alone is not readiness.

Accepted appearance reference: private ARM f96149759b66a79f0a34e4d74b09ae70fa261c85,
executable 521461e6130bf4c67d4649de9f0b470cde218ba57f9de0a86ab5dcced9efb4d5.
Its exact-path native launch is recorded at October 12 18:27:41 UTC (1:27 PM CDT).
It is the last evidenced review launch before the user's 6:13 PM CDT feedback;
this is not a continuously sampled process proof at that precise feedback time.

| Required user-visible gate | Source/isolated result | Exact packaged native result | Remaining blocker |
|---|---|---|---|
| Continuous resize without extra breakpoint padding | Five bad-source failures retained; six focused checks pass after minimal inset change. Accepted 1100x740 spacing retained. | Old review FAILED by supplied screenshots; Cooper explicitly tested recovery.1: “resize looks great”. USER-VERIFIED acceptance; exact PID75446/package bound by launch receipt. | Accepted by Cooper; preserve the continuous-inset source and bounded regression evidence. |
| No edge stick or first-drag delay, including return from fullscreen | Root cause UNRESOLVED. Existing simulated native-handoff tests are bounded and do not establish OS behavior. | FAILED by user report; fresh controlled native reproduction UNTESTED. | Coordinate physical first side/corner drag at each edge and after fullscreen; measure press/movement and retained pointer ownership. No OS setting changes or invented snap cause. |
| Original Options style/morph, working requested controls | 9 existing affected Options checks pass alongside resize checks. Matching f961/current offscreen MP4 quick, MP4 Custom and Original audio endpoints are pixel-identical in the controlled fixture. Midpoint differs slightly after f26 cached-material optimization. | Cooper explicitly tested recovery.1: “options panel is super responsive”. USER-VERIFIED responsiveness acceptance; two requested narrow UI follow-ups recorded separately. | Add themed SETTINGS heading/aligned YouTube access to side-by-side Options settings column; preserve accepted morph/control owner. User did not separately attest every control. |
| Move/delete hierarchy, old and new media | Actual review PYZ contains25b cleanup, but15 legacy non-import rows lack persisted root. New strict canonical-boundary recovery, missing-media companion/empty-folder cleanup and recognized empty sibling handling pass58 hierarchy cases; final tests reject bad baseline11fail/47pass.159 affected boundary cases,7 failed-run routes and3 actual Mac Trash API fixtures pass. | FAILED by old review; compiled recovery.1 contains correction, frozen GUI transaction UNTESTED. | Exercise the prepared old/new, nested/partial/empty/shared fixtures through exact successor UI on each platform; preserve root, other-item files, unknown directories/files and redirects. No real media sweep. |

Source evidence and supplied screenshots:
`build/recovery-20261011/resize-scope-audit-20261014/`.

Retain unaffected existing signed core/queue/Skip/media/data/privacy/Update/Repair
receipts from the change-and-test log under their original identities. Current
inset changes do not alter those runtime owners. Repeat only checks whose source,
dependency/configuration or evidence defect actually affects the result. Keep
exact new-binary smoke and the four affected native gates; do not restart broad
campaigns for documentation or QA-reader changes.

The source-hash-matched Intel posthog.2 package finished signing/notarization
after the pause (archive 6bd8511bdb15d7177e8da99645ee1a737b078f706aa1cc916a6ec240e37c98e0).
It is HELD locally, predates the recovery corrections, was not transferred/launched
on Air, and is not successor acceptance. Actual corrected Intel macOS15.8.1
functional/rendered acceptance remains UNTESTED. Keep the user's Pro review app
and both machines' profiles intact until coordinated replacement.

Current isolated ARM validation candidate: `0.2.6-dev.recovery.1`, archive
`0aab0759b446cc63b166045c9145f935c9d1491bc689a334ac942376164fd740`, executable
`3e930f78a17ab520d5222bba40ddf27b1987c87a799e400227e8c3dd5a70200e`.
Developer ID/strict signature and actual isolated frozen smoke pass;6,258 sealed
entries match archive,384 ARM runtime floors<=15.0. Not notarized or native-UI
accepted. Fictional four-case profile and Move destination are prepared under
`build/recovery-20261011/recovery-arm-20261014/native-fixture/`.
No launch/replacement yet. Current task lacks a callable CUA/native-input tool;
parent must coordinate Cooper's physical review or an existing supported CUA
observer before first edge/corner drags, fullscreen return, matching-mode Options
and actual Move/Delete. No new OS grant or unsupported input fallback requested.

## Original request-to-evidence reconciliation

These rows retain the original asks; they do not create a second broad campaign.
Source-only means the behavior is implemented/tested but the current successor's
native interaction is not established. Existing valid bounded receipts retain
their exact source/platform/artifact identities.

| Request | Current source / saved evidence | Disposition |
|---|---|---|
| Failed/interrupted Run Remove removes associated owned files |0d0b26b introduced requestRunRemoval→shared file transaction→finish only after successful cleanup. Current7 targeted test outcomes verify confirmation, indexed owned files, failure/changed/active refusals. Unverified/unindexed partial files remain protected.|Implemented and source-verified; corrected package native UNTESTED. Completed-run Play/Library/Folder is not this evidence.|
| Issues & Recovery item/right-click Remove, Open Issues & Recovery, failed action row under progress |0d0b26b/Main.qml and actual Bridge source controls; retained test_qt_recovery_ui_loads_and_create_footer_fits plus inspector action-contract/action suites.|Source-only for present successor; retain earlier source checks, no nonexistent UI actions required.|
| Loaded-list picker/typed path/clear/concave toggle |0d0b26b test_qt_list_composer_sync_picker_edits_and_toggle and test_missing_list_clears_only_unsubmitted_composer. Earlier bounded Windows picker/list receipt remains predecessor-specific.|Implemented/source-verified; no new current native claim or repeat for unrelated label/docs changes.|
| Create Video Close/Create MP4 bottom padding |Existing localConversionPopup footer bottomMargin8. Strengthened same recovery/footer test now independently checks both visible button bottoms at two sizes;1pass.|Source-only; current exact native visual gap UNTESTED.|
| Forge Skip/Stop one-line tooltips |Main.qml uses singleLine:true; retained test_qt_short_tooltip_single_line_and_clamped_edges.|Source-only retained; no tooltip redesign/repeated broad campaign.|
| Dynamic Windows drive names |c41849e canonical drive labels and retained source/native Windows review receipts.|Implemented/verified within original Windows evidence scope; no Mac-drive claim.|
| Preset vs Rate control, redundant File path removal |25b4d94 metadata projection and retained Qt fact/copy tests.|Implemented/source-verified; retained limits apply.|
| Selectable details, chapters after Recently Added, source/personal tags and note |d17194c owner-bound source/clipboard/selection tests and native review launch receipts.|Implemented/bounded verified; standard Qt editing menu does not prove native OS menu.|
| Subtitles and language mapping |Retained French/Spanish successes, explicit unavailable-language failure, provider429 refusal and actual subtitle-selector callback tests.|Reuse exact observations; no duplicate provider downloads or per-language campaign. Native popup callback/fluidity still covered by the open Options gate.|

Delete cleanup boundary: old provider records may reconstruct a root only when
durable title/id/channel metadata exactly reproduces one supported canonical
hierarchy. Explicit invalid roots, imports, redirects and metadata mismatches
remain refused. Unindexed empty video branches are recognized only in canonical
channel/group/video structure with provider-shaped identity; arbitrary empty
personal directories remain protected. Metadata-only/thumbnail-only siblings
block higher pruning. A selected standalone thumbnail without ownership metadata
is protected too; do not silently infer ownership to make a fixture pass.


October14 user acceptance via parent01a13c6a: recovery.1 resize and Options responsiveness accepted by Cooper; this is user testimony, not executor pixel/native observation. Follow-up scope: Settings heading/alignment in three-column Options; direct collection context Delete and correct collection labels; complete disposable Mac/Windows Trash matrix including sole-video-in-channel and sole-video-with-unrelated-files. No public-release approval.


## Recovery.3 actual GUI successor checkpoint — 2026-10-15

Mac exact943140...1fe4c: two actual transactions, six native Trash payload hashes pass; newly failing empty reserved bucket case now removes whole eligible channel while root/unknown sibling remain. Protected notes/other MP4 remain with parents. Anchored collection menu, separated selectable paths and accepted Options pass. Smaller-height/many-record RunDeck remains unqualified; 1100x740 two cards visible. See observer report `.../task-2/vodforge-recovery3-native-qa/report.md`.

Windows original QA2 three absent payloads are **UNRESOLVED POTENTIAL DATA LOSS**, not accepted. New QA3 first transaction stops truthfully at first file: native Bin video hash matches and native restore to disposable original location matches; two companions/history retained. New receipt code rejected successful positive HRESULT0x00270008; corrected source six affected cases pass, corrected real-app package pending. Long-path abort-only native probe reports non-recyclable flags and verifies raised HRESULT abort preserves bytes; old provider's Python integer return does not supply that abort. Do not claim the original missing payloads recovered or permanent deletion confirmed without evidence. Full case-by-case native hierarchy and recoverability matrix remains pending Windows. Public release held.


## Current bounded native disposition — 2026-10-15

This supersedes earlier UNTESTED cells only for the affected checks listed here; historical receipts retain their original package identities.

| Gate | Mac | Windows | Remaining |
|---|---|---|---|
| Empty reserved bucket and eligible channel pruning | recovery.3 two actual successor transactions/6payloadhashes; root/unknown/peer preservation passes | recovery.4 34record outcomes in5GUItransactions,84nativepayloadhashes; per-case hierarchy/protected bytes/history independently pass | OriginalQA2 three missing payloads remain UNRESOLVED POTENTIAL DATA LOSS, not repaired by successor proof |
| Native recoverability | Six exact Mac Trash hashes |84exact native Bin hashes; first3restored natively with exact bytes;81remain | Corrected Windows package is local unsigned QA, not normal review install/release |
| Non-recyclable long path | Not applicable to Windows provider correction |353char actual GUI refused/all files+folders+history retained/0transfers; true HRESULT abort | Long-path Trash remains unsupported and fails safely; journal needs_attention retained |
| Filename/full-path readable blocks | Native exact full-path selection and separate facts pass |Native fullpath selection/copy exact/clipboardrestored; filename blocks/dividers/wrapping/footer inspected | None for bounded reported dialog |
| Settings/Options heading | Native3column settings/acceptedOptions pass |Native3column themed SETTINGS and aligned YouTube row pass | Existing accepted morph/control source coverage retained |
| RunDeck clipping/reachability |1100x740two cards visible; shorterheight/many-record unqualified |Actual34record deck fullcards/footer reachable at1100x640and1100x560 via outer scroll | Mac shorterheight physical/native observation; first-drag/edge timing remains unresolved |

No main merge/publication, normal Windows replacement, OS security/settings/access or dependency changes. See `build/recovery-20261011/windows-recovery4-gui/REPORT.md` with all explicit per-case paths/bytes and original failure preservation.


OriginalQA2follow-up: read-only retainedNTFSjournal confirms exact3originalFRNs/parentFILE_DELETE|CLOSEduringactual006/noRename. Originalobjectdeletion is now evidenced; destination/payloadrecovery remainsUNRESOLVED. This supersedes only the earlier lack-of-OS-deletion-evidence, not original failed receipts. CorrectedWindowsreviewhandoff is `build/recovery-20261011/windows-recovery4-gui/WINDOWS-ARTIFACT-HANDOFF.md` (NotSigned/localQA, no replacement/publication).

Mac24-recordfreshattestedfollow-up interim: actualnativebottomedge740→640/topedge→560; supportedouterAXscrollbar0→100exposesfull4cards/All24/footeratbothheights. Genericwheelinitiallydidnotreachouterowner; notclaimedfixedfromscrollbarproof. Edges/corners/fullscreenfinalreportandfirstpainttiminglimitation pending; no native Trashrepeat.


## Final Mac native follow-up and remaining release gates — 2026-10-15

Mac exact943140...1fe4c/fresh24recordattestedPID12183: actualnativeouter scrollbar exposesfullfourRunDeckcards/actions/All24/footerat1100x640and1100x560. Prior short-height unknown is now qualified for bounded scroll reach, not genericwheel/physicaltrackpad. Firstbottom/topedgeandbottom-rightcornerchangedgeometry; otherrecordedfirstedges/cornersdidnotresize. Fullscreenentered but supportednormalreturnattemptsdidnotexposereturnedwindow; after-fullscreenwindoweddragsunqualified. DiscreteCUA cannotmeasurehigh-resolutionpress-to-firstpaint; toolroundtripisnotlatencyproof. NormalQuit/noownedprocess,24payloadhashes+24historyrecordsunchanged,nojournal. Report `/Users/coop/Documents/Codex/2026-10-14/task-2/vodforge-recovery3-layout-qa/report.md`.

Remaining gates/limits:
1. Resolve/dispose recorded Mac no-resize first edges/corners and unsuccessful supported fullscreen return; qualify after-fullscreen/first-paint timing through a supported observation route. No universal first-drag pass.
2. OriginalQA2threeobjectdeletions nowOS-evidenced; recoverydestination/bytes stillunresolved. Parent/user review the incident disposition. CurrentforwardWindowsmatrix passes; non-recyclable longpaths refuse safely ratherthan Trash successfully.
3. Review/freeze intended source changes; generate recognized final signed Windows/ARM/Intel artifacts bound to that source. QA4islocalNotSigned; ARMrecovery3isprivateDeveloperID/notnotarized; retainedIntelposthog.2predatesrecovery. No matching correctedIntel/Air rendered acceptance yet; prior Air observation-route limitation retained.
4. Coordinate successor ordinary private app replacement/userreview; old ordinaryWindowsf961 remainsopen/preserved. No ordinarymediaTrashtrial and no silentprofilechanges. Original request-to-evidence rows above retain source-only/nativeunknown limitations; do not relabel them as currentnativepasses.
5. Preserve/reuse valid unaffected core/queue/media/privacy/UpdateRepair receipts under original identities; no broad rerun justified solely by labels/QA readers. Explicit parent/user lift of0.2.6publicationhold is stillrequired; public0.2.5unchanged.

## Fullscreen successor disposition — 2026-10-15

Source-supported classification: View had no fullscreen Action/standard shortcut, so the attempted main-window shortcut had no application return route. Added state-derived Enter/Exit Full Screen with public Qt APIs; two real-QML cases fail before/pass after on ARM and two pass on existing Intel environment. Native Space return is still pending exact successor observation. Unsuccessful edge/corner gestures remain application-versus-CUA unresolved; retain successful observed drags and do not alter native hit zones without evidence. No first-paint timing claim.

Private recovery.5 ARM/Intel outputs are fresh and source-hash-bound. ARM Developer ID signing/384runtimefloor≤15 audit passes; Apple submission3d68002c-c36b-43e7-a637-a3baa2a7072f is In Progress at readback. Intel packaging underway. No final archive/native acceptance claim yet. Existing Air Tailscale route timed out exit255 before identity; no remote qualification or access changes. Reports/freeze-review sequence: `build/recovery-20261011/fullscreen-return-20261015/{REPORT.md,PRIVATE-REVIEW-PLAN.md}`. Public release hold remains.

## Final private recovery.5 disposition — 2026-10-15

This supersedes only earlier recovery.5 build/notary/native pending text. Both ARM and Intel private candidates now signed/notarized/stapled/Gatekeeper accepted; exact hashes, complete bundle/archive/source binding and local signed-smoke0 are in `build/recovery-20261011/fullscreen-return-20261015/PRIVATE-REVIEW-HANDOFF.md` and `final-summary.json`.

ARM actual native menu fullscreen return and exactly one after-return bottom-edge resize PASS on recovery.5. Actual shortcut and first-paint latency unverified; other no-resize edge/corner observations remain application-vs-CUA unresolved. Do not infer a universal resize pass or change hit zones without evidence.

Intel physical Air successor qualification remains BLOCKED at existing TailscaleSSH timeout255 before identity. Essential rendering also retains earlier supported-observation-route limitation. Local Rosetta smoke is not physical Intel acceptance; no access/security changes or guessed grant instructions. Prior Intel1ba receipts retain original identities.

Original Windows QA2 NTFS deletion/recovery unresolved, final Windows signing/ordinary private review and source/publication approval remain separate gates. No accepted34record/84payload or MacTrash campaign repeated for this Mac-only QML fix. Public0.2.5 unchanged,0.2.6HELD. All owned VOD heavy/sign/native intervals released.

OriginalQA2 recovery clarification01:08:56UTC: all three original synthetic payload contents have current verified ordinary peer copies (20/25/4921bytes, exact manifest hashes, pre-incident timestamps) and localvideoextra. No copying/restoration/undelete performed. OriginalNTFSobjectidentity/nativeBindestinationrecoveryremainsunproved; failedoriginalTrashoperationnotrelabeled. Map/report `build/recovery-20261011/original-loss-copy-audit-20261015/`; no invasive recovery necessary to obtain these fixture bytes. Remaining resize finite native follow-up is coordinated after Kryden normal release, outcome pending.

Remainingresizefiniteactualfollow-up01:11:56UTC: exactrecovery5fresh1100x740abovebothminima leftedge1100→1080/right1080→1060PASS. Top-leftboundsunchanged/hitregionunknown. Top-rightCUAwindowNotFoundAtPositionbeforeconfirmedgesturecompletion: TOOLtargetinglimitation, notappdefectproof. No retry/sourcefixjustified; no generalcorner/firstpaintpass. Normalquit/zeroownedprocess/emptyfixtures/nojournal/exehashunchanged. Fullreport `.../task-2/vodforge-recovery5-remaining-resize-qa/report.md`; allownednativeintervalsreleasedafterKrydennormalrelease, no competition. Original3payloadnormalcopiesverifiedseparately; originalidentity/nativeBindestinationunproved. Publicheld.

Explicitcornergateclassification: top-left observedresizeFAIL(nochange), targetunqualified/appregressionunproved; top-rightCUAtargetingFAILED/productresizeUNTESTED. CompleteresizeacceptanceNOTACCEPTED. No blindrepeatgesture or sourcefix proposed fromthese results.

CurrentAircheck Oct14 11:44p.m.Chicago: existingTailscalebackendRunning, exactAirpeerOffline/Inactive,lastseen11:10p.m.; noSSHretry/nativeinput/accesschange. PhysicalIntelgateblockedonexistingpeerreachability,notnewbuild/signing. RetainedoriginalWindows3identities independentlyjoinedjournal→USN(noRename/nullnativeTrashdestination); originalidentityrecoveryunproved, ALL3payloadcontentshaveverifiedordinarycopies. No repair/undelete/newdeletion/rebuild/matrixrepeat. Currentreport `build/recovery-20261011/air-current-route-20261015/REPORT.md`. Resource “released” ≠ publication; publicholdremains.

SiliconlowerOSgate: privateengineeringfloor15 is implemented/audited; actualexactcompatible/recoveryARMruntime27.0.1only. ARM15nativeacceptanceOPEN; IntelAir/sourceCI/runnerconfignotreplacement. Latestimmutable recovery5plistminimumABSENT; futurecanonicalwriterfixed5beforefail→5afterpass. BeforeNEXTcandidatefreeze recordLSMinimumSystemVersionmatchingconfiguredinputtargetandfullbundlefloorceiling; shared/privateadaptedrecipesmustcarrythatfinalization. Existingartifactsremainunchanged. See silicon-support-20261015/REPORT.md. macOS14-or-earlierneedscompatibledependencysetbecausecurrentPySidefloor15; no guessedclaim/rebuild/publication.


## Current publication authorization and PostHog qualification — October15

PublicholdliftedbyCooper; publicMacminimumunchanged. Newsourcecaptureenabledonlywithseparateproviderconsent; replay/experimentsoff.26affectedtests/Ruff/format/diffpass. Actualsynthetictesttransport200/readbackproved; insert-ID-only duplicatefailurepreserved, correctedtop-levelUUID5twoidenticalrequestsreadbackone. Notpackaged/nativeadoptionproof. Currentrecovery5artifactsdev-labelled/predateanalyticschanges; WindowsQA4NotSigned. Finalstablesourcefreeze/build/signing/affectedruntimechecks/feedsstillrequired. Existingcompletecorner/firstpaintandphysicalIntelgapsnotwaivedormisrepresented; ARM15runtimeexplicitlydeferred, no publiclowerfloorclaim. Capacitylatest4.096GB; no cleanupapproved. Fullconcreteplan/status: build/recovery-20261011/posthog-release-20261015/RELEASE-PLAN.md and release-status.json. Canonicalsiteowneractive/authorizedpublicationafteritsownchecks, retainingexisting0.2.5linksuntilfinalassets. No newpublicreleaseclaim.
