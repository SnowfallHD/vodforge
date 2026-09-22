# Using and maintaining the engineering-quality harness

This is the operating and extension guide for the engineering-quality harness.
[README](README.md) owns setup, command reference, evidence tiers, and historical
defect-class records. [RELEASE_GATE](RELEASE_GATE.md) owns immutable candidates and
release receipts. This guide owns the cross-cutting acceptance standard and the
workflow for changing checks. Keep these guides linked rather than duplicating
architecture or command specifications.

## Find the workflow you need

- Understand the architecture: [How a run works](#how-a-run-works).
- Set up and run checks: [Running a check](#running-a-check) and [setup](README.md#setup).
- Review interaction quality: [Observe before, during, and after](#observe-before-during-and-after) and [the complete user journey](#review-the-complete-user-journey).
- Add a feature or repair a missed defect: [Updating a check or adding a feature](#updating-a-check-or-adding-a-feature).
- Record results and gaps: [Recording a review](#recording-a-review).
- Qualify telemetry: [Full-application telemetry acceptance pass](#full-application-telemetry-acceptance-pass).
- Decide whether a candidate can advance: [Acceptance and promotion](#acceptance-and-promotion) and [release gates](RELEASE_GATE.md).

## Current enforcement status

The Forge worker integration in `tests/test_forge_activity_ui.py` complements
the controlled-worker queue tests: it starts the real worker, delivers controlled
source-stage events, persists an admitted queue, follows failure into the next
worker, cancels through the actual control, and reads durable terminal state.
Its real telemetry producer writes to a local fake-transport outbox; private
fixture values must be absent, and navigation after disabling telemetry must
leave that outbox empty. The source boundary deliberately performs no network
download. Mac captures establish settled active/queued/error/cancel composition;
other platforms retain the functional checks without claiming those captures.
Native alert appearance/dismissal, preview D1 delivery, complete media download,
physical input and packaged execution remain separate evidence.

The same worker journey caught a stale secondary queue count after handoff:
durable queue and Run Deck were current, but an enqueue-only footer setter was
not. The footer now explains sequential execution without duplicating live
counts. Run Deck remains the existing projection for those counts. Previous
queue persistence tests checked admitted jobs and projection ownership, not the
separate visible footer; the native case now retains the prior failure and
checks the composed handoff. Do not add another independently maintained count.

Review both friendly and technical Activity modes at their actual parent size.
The friendly child previously used north/east/west anchoring while its technical
sibling filled the same grid cell. Wrapped errors therefore clipped inside a
short child despite unused parent space. Both now fill the existing viewport;
native checks require equal available height, reachable final text and lossless
contents after scrolling. Earlier tests asserted full height only in technical
mode, which missed this sibling-adapter defect.

The during-operation standard below is required for acceptance across the harness.
It is not a claim that all existing scenarios already enforce it. The central
scenario runner now records an interaction-coverage assessment for
every executed scenario, reports show functional, temporal and usability results
side by side, and NORMAL/DEEP release evaluation adds separate required blockers
for unreviewed temporal and usability coverage. Machine-readable assessments include explicit
before/during/after statuses and the seven usability dimensions. Known native UI
coverage requires usability review; unknown applicability stays unreviewed rather
than becoming exempt. These fields expose pending work, not automated aesthetic
approval or completed reviewer enrollment. Unknown or
new scenarios default to unproven. The exact static change-surface analysis has
a documented non-applicable classification; the broad unit_static tier does not.

This is an initial fail-closed migration, not completed domain coverage. No
behavioral scenario has yet been admitted as temporally complete by this new
assessment. Existing traces/assertions must be reviewed and connected to domain
evaluators, with negative controls, before removing their blockers. Native JUnit
success alone still does not prove temporal acceptance. The maintained
private-install command now invokes the same NORMAL temporal/usability coverage
evaluation before any installation mutation, alongside exact candidate,
negative-control prerequisites and the checkout-owned user-defect ledger. Legacy
ad-hoc replacement is superseded. Behavioral enrollment remains incomplete, so
current candidates are blocked.

The September 17, 2026 hands-on rejection of private v34 reopens scrolling,
in-drag layout, artwork composition, tab transitions, and release-of-resize
acceptance despite earlier passing source/native checks. Preserve those passing
checks as evidence of their narrow contracts, alongside the failures. Neither
their count nor a subsequent settled screenshot resolves the reported failures.

## Product standard: powerful without a cockpit

VODForge is for people who want to manage and watch their videos without becoming
technical experts. This standard applies throughout the application and to every
applicable harness review, including Forge, Library, Watch, settings, menus,
dialogs, source/output details and error recovery.

Judge whether a user can understand the current task and its next useful action.
Keep the default view restrained; reveal secondary actions and technical detail
when they help with that task. Prefer familiar words and recognizable controls.
An unexplained arrow, a wall of settings, or a technically correct outcome behind
a confusing interaction is a usability defect. Restraint must not hide necessary
status, remove keyboard access, or make recovery harder to discover.

Review the whole screen and its transitions against the approved VODForge
references. Check typography, content hierarchy, spacing and control consistency
together, including sparse playlists and expanded views. A polished isolated
button or final screenshot cannot stand in for that review.

For each applicable check, show functional, before/during/after and usability
results together. Record evidence, reviewer, gaps and applicability reasons.
A functional pass with unreviewed usability remains unreviewed overall for that
claim. Automated assertions support this review; they do not infer beauty or
intuitiveness from widget counts. See the phase and dimension tables below.

## How a run works

1. The CLI selects a profile or exact scenario and establishes isolated state and
   diagnostic paths. Preserve isolation: never substitute a user's library,
   settings, media destinations, or telemetry account for controlled fixtures.
2. The scenario registry selects production-owner exercises and required contract
   suites. A test file existing in the repository does not establish enrollment.
3. Pipeline scenarios invoke production orchestration with generated media,
   loopback faults, real media tools, and independent output inspection.
   Native scenarios require a real display; packaged journeys bind the launched
   process and evidence to the immutable candidate.
4. Existing queue traces, resource samplers, lifecycle checkpoints, native reports,
   and packaged event receipts retain observations. Observations become acceptance
   evidence only when a meaningful assertion evaluates the required behavior.
5. Results and raw evidence feed reports and release evaluation. Inspect failures,
   skips, unavailable measurements, source binding, and coverage gaps before
   interpreting the final status. A process exit code is not a coverage argument.

Implementation owners, relative to this directory:

| Responsibility | Existing owner |
| --- | --- |
| Commands, environment, profiles | quality_harness/cli.py |
| Scenario enrollment and aggregation | quality_harness/scenarios.py |
| Production jobs and queue traces | quality_harness/pipeline.py |
| Resource and lifecycle measurements | quality_harness/metrics.py |
| Source-native invocation and completion | quality_harness/native_ui_checks.py |
| Process-local native startup and child launches | quality_harness/native_process.py |
| Native incremental results/import binding | quality_harness/native_reports.py |
| Packaged journeys and provenance | quality_harness/packaged_e2e.py, quality_harness/e2e_provenance.py |
| Packaged observations | quality_harness/e2e_record.py |
| Reports and acceptance receipts | quality_harness/report.py, quality_harness/release_gate.py |
| Source content snapshots | quality_harness/source_identity.py |
| Interaction coverage review | quality_harness/interaction_coverage.py |
| Typed negative evidence | quality_harness/negative_controls.py |
| Native scrolling pixel evaluation | quality_harness/scroll_observations.py |
| Private replacement and open defects | quality_harness/private_review.py, acceptance/user-reported-defects.json |
| Serialized contracts | schemas/ |

Extend the relevant owner. Do not create a second runtime state owner merely to
observe it, or let instrumentation become responsible for product correctness.

## Running a check

Follow [setup and commands](README.md#setup), then use the smallest relevant
scenario for diagnosis. For example, from the repository root:

```sh
./engineering-quality/run doctor
./engineering-quality/run normal --scenario reliability.cancel_during_slow_download
./engineering-quality/run fast
```

Read the selected scenario's assertions and fixture before interpreting its
result. Preserve the command, environment, source identity, raw observations, and
report path. Run the required broader profile after relevant changes; a focused
pass does not replace NORMAL, DEEP, native, or exact-package requirements.
[The release workflow](RELEASE_GATE.md) describes candidate and receipt commands.

Native or packaged checks can take over the desktop. Respect an active user/GUI
hold; continue source inspection, documentation, and headless checks while held.
Permission to work on code is not a reason to interrupt a user's active review.

## Observe before, during, and after

Every behavioral check must identify its applicable phases: initial state,
accepted intent, in-flight work, commit or cancellation, and cleanup/recovery.
Observe and assert the relevant invariants during the operation, not just after
waiting for it to settle. A transient violation remains a failure even if the
final state repairs itself.

For each acceptance claim, maintain an explicit mapping with:

- Requirement and supported behavior; production owner and affected integrations.
- Enrolled scenario and exact test/assertion identifiers.
- Fixture, load, platform, source or artifact identity, and input mechanism.
- Required phases, independent observable outcomes, and observation cadence.
- Pass/fail rules, threshold rationale, and handling of unavailable evidence.
- Raw evidence and evaluated result; negative control or prior-failure receipt.
- Remaining gaps and the acceptance claims they block.

To admit a behavioral scenario, extend interaction_coverage.py with a reviewed
domain evaluator and explicit requirement/assertion mapping, bound raw execution
evidence, and demonstrated negative controls. Do not replace its unproven default
with a blanket passed exception or trust a scenario-supplied coverage flag.

A pure static check can mark interaction phases not applicable with a specific
reason, such as parsing source for prohibited dependencies. A scenario's legacy
`unit_static` label is not sufficient: that tier also contains behavioral and
native contracts. Do not invent interaction evidence for lint or force every
domain to use a UI frame recorder.

## Domain-specific assertions

| Domain | During-operation evidence and assertions |
| --- | --- |
| UI input and resize | Input/button state and mechanism, window geometry, content layout, rendered frames, and input-to-visible-response timing; assert adaptation while pressed and no continued resize after release. |
| Artwork and view reuse | Nonuniform calibrated images, card/owner/generation identity, image shape and position, intended layer count, and stale-result retirement throughout resize and after release. |
| Scrolling and transitions | Actual event cadence, visible frame sequence, latency distribution and worst gaps, correct content ownership; assert absence of blank, duplicate, or stale layers rather than only endpoint position. |
| Workers and queues | Accepted job identity, progress and phase order, active ownership, cancellation boundary, late-result rejection, and successor isolation. |
| Storage and history | Staging topology and namespace changes while active, atomic commit boundary, durable identity, forbidden writes after cancellation, and restart reconciliation. |
| Playback | Readiness and actual provider state, latest intent during seek/pause/volume changes, media replacement, and late callback rejection. |
| Telemetry | Consent at collection and delivery, bounded payloads, attempt identity and ordering, retry/withdrawal effects, and independent delivery readback where required. |
| Updater | Candidate identity through download, verification and handoff; interruption and failure must preserve the usable installation and prevent premature success. |
| Resource/lifecycle | Samples during load plus teardown, ownership release, child processes and retained-resource trends; missing measurements remain unavailable. |
| Static/security analysis | Evaluate the stated static invariant; dynamic security boundaries separately observe attempted and actual effects, including forbidden intermediate effects. |

The table defines required review dimensions, not completed scenario coverage.
Use applicable supported behavior; do not invent a cancellation or recovery
contract that the product does not support.

For UI restraint and usability, assert the visible task flow as well as mechanics:
clear primary actions, comprehensible labels, contextual secondary controls,
readable hierarchy, and detail disclosure when needed. Dense control inventories,
widget counts, or pixel snapshots alone do not prove intuitive interaction.
Retain human review for these judgments and record what automated checks cover.

### Keep usability visible throughout each interaction

The engineering report must expose the applicable interaction and usability
assessment beside each journey's functional result. A green completion assertion
must not hide an unreviewed, confusing, or visually broken intermediate state.
Apply the same standard to every UI surface, including settings, dialogs,
expanded source/output details, and recovery flows.

| Phase | Questions the review must answer |
| --- | --- |
| Before input | Can the user identify their location, the content they are acting on, and the next useful action? Are secondary or advanced controls disclosed in context? |
| During input and work | Is acknowledgement visible? Do focus, selection, progress and content ownership remain clear through press, drag, scroll, loading and transitions? Does the layout remain readable without exposing distracting controls? |
| After completion or interruption | Is the outcome understandable, with preserved context and an obvious next step? Can the user recover or return without technical knowledge? Have temporary controls and stale states retired? |

Record each applicable dimension as reviewed, failed, or unproven, with evidence
and reviewer identity. Automated checks may establish focus, clipping, response
timing, disclosure state and action behavior; visual hierarchy and intuitive flow
also need contextual review against the approved VODForge references. Reference
images are design evidence, not proof that the running application behaves well.

For checks without a user interface, retain their domain-specific temporal
invariants and a reason that visual review is not applicable. Do not mark an
entire mixed suite exempt because some checks are static. The requirement is
harness-wide visibility of applicable evidence and gaps, not additional controls
or diagnostic clutter in the product. Current enrollment limits above still apply.

### Review the complete user journey

VODForge is a powerful, approachable consumer application. Review the complete
screen and the path through it, including loading, expanded details, errors,
cancellation, and recovery. The default view must remain restrained while
advanced capability is discoverable in context.

For every affected journey, retain an explicit usability assessment alongside
the behavioral assertions:

| Review dimension | Required evidence |
| --- | --- |
| Orientation and navigation | Current location, meaningful destination labels, predictable Back behavior, and preserved context. |
| Action hierarchy | An obvious next action, plain-language labels, consistent control styling, and secondary actions disclosed where relevant. Unexplained arrows do not substitute for named actions. |
| Progressive disclosure | Useful summaries before source/output details; expanded states remain readable and can be dismissed predictably. |
| Visual hierarchy | Legible typography, spacing, alignment, artwork treatment, and consistent primary/secondary emphasis across the whole view. |
| Sparse and busy content | Empty state, one downloaded video, short and long playlists, many channels, long titles, missing artwork, and constrained window sizes. |
| Feedback during work | Timely acknowledgement, truthful progress/status, retained navigation context, and clear completion or recovery. |
| Accessible interaction | Keyboard reachability, visible focus, meaningful accessible names, and feedback that does not depend only on color or hover. |

Use the approved VODForge mockups as the visual target, with additional references
for expanded details and source/output views. External inspiration informs
hierarchy and craft; it is not a specification to copy. Preserve approved depth,
glows, and fades when optimizing rendering. A faster diagnostic stripped of those
treatments does not qualify the intended design.

Record each dimension as reviewed, failed, or unproven with its evidence and
reviewer. These are acceptance review requirements, not claims of automated
aesthetic scoring. Automated tests should enforce observable contracts such as
disclosure state, label availability, focus movement, and clipping; human review
must judge clarity, restraint, and visual coherence. Keep diagnostic detail in
harness reports rather than exposing an instrumentation cockpit in the product.

### Shared components and consistent controls

The same semantic control must use the same maintained component contract across
Forge, Library, Watch, details, and popups. Shared colors alone are not component
reuse. Default primary and secondary controls must have consistent typography,
height, padding, focus, hover, pressed, disabled, and activation behavior.
A compact or icon variant requires an explicit semantic use and documented
metrics; a view-local override is not an approved variant by default.

Maintain the implementation and use-site inventory in
[the UI component catalog](../docs/ui-components.md). For each common component,
record its contract owner, rendering adapters, semantic and size variants, active
callers, legacy unused helpers, and known bypasses. Report these counts separately:
three rendering adapters are not three semantic variants, and a common palette
does not reduce independent implementations to one. Cover buttons, inputs,
selectors, disclosures, navigation, menus, dialogs, cards, rails, scrollbars,
focus and feedback surfaces as applicable.

Changes to a shared component require:

1. An inventory check that detects an unregistered implementation, local metric
   override, or caller bypass. Source declarations identify candidates; confirm
   active call paths before reporting adoption.
2. Rendered parity checks in actual representative Forge, Library, Watch and
   popup contexts. Compare the same role and size at the same platform scale,
   including long labels, constrained space and keyboard focus.
3. A controlled change to the shared specification that reaches every registered
   adapter and relevant live use site. This demonstrates dependency on the common
   owner rather than coincidentally matching duplicated constants.
4. Behavioral checks for disabled activation, press/release retirement, focus,
   owner replacement and per-instance callback isolation.
5. A known-bad bypass or drift case that the inventory or parity oracle detects,
   plus an explicit report of unexecuted platforms and adapters.

Run the current action-site inventory from the repository root:

~~~sh
python engineering-quality/runners/component_inventory.py
python engineering-quality/runners/component_inventory.py --write
~~~

The first command checks the recorded callers and rejects explicit labeled-action
metric overrides or direct tk.Button/ttk.Button bypasses of ProductButton. Use --write after reviewing an intentional
caller change; it refreshes evidence, not approval. It also refreshes direct sites
for the explicitly reviewed control-family names in UI_CONTROL_FAMILIES.json;
new families and dynamic factories require an inventory review. The scanner covers direct
ProductButton, direct ttk.Button/tk.Button bypasses and ScenePainter p.button calls. Aliased constructors,
dynamic factories, other component families, geometry-manager inflation and all
state appearance still require audit and native evidence; this initial scanner
does not claim to detect every possible bypass. The opt-in native registry enrolls
test_button_parity_native.py for actual application parity, shared-spec changes,
and the original local-padding negative control.

The whole-journey review still decides whether a control is needed and disclosed
at the right time. Component consistency must not create a permanent toolbar of
every available action. Keep action ownership local to the current content while
sharing the implementation. These are required migration and acceptance checks;
the inventory and rendered parity suite must be implemented and executed before
claiming app-wide shared-component compliance.

### Completing the current qualification work

Use this completion map with the component catalog and current defect ledger.
A family-wide gap does not erase a passed bounded contract. Keep the bounded
result, its evidence tier and its limits visible while closing the next gap.
These are implementation and qualification steps, not newly claimed passes.

| Family | Existing owner and bounded evidence | Remaining gap and next qualification |
| --- | --- | --- |
| Action buttons | ProductButton, ui_button_contract, ScenePainter; representative native parity and shared-spec propagation pass. | Five Library scene icon sites now use shared inline/default metrics with live size propagation and wrong-variant detection. Complete player variants and remaining adapter states, including keyboard focus and disabled treatment. |
| Text and search | ProductEntry, PlaceholderEntry, LibrarySearchField, EditableTextSection, FactsText, ActivityLogText. | Review plain Tk entry/text callers against their semantic role; exercise typing, hint separation, long text, save failure and owner replacement in actual source/output details. |
| Choices and segments | ChoiceDropdown/Menu/Popover and SegmentedSelector; changed-option snapshot retirement has before-failing native evidence. | Qualify keyboard selection, disabled state and popup focus through replacement and both rendering contexts; verify values and callbacks independently. |
| Toggles | ModernCheckbox and native check/radio adapters; scoped press-release repairs retained. | Inventory live native variants and verify independent state, keyboard activation, disabled/replaced callbacks and readable labels in actual settings. |
| Navigation tabs | ttk.Notebook, ActivityModeSlider and ViewTransition; activity gesture retirement has three before-failing cases and valid controls. | Consolidate duplicated role behavior where semantics match, then record actual destination/context and visible transition frames; preserve separate tab-flicker defect. |
| Sliders and player | Native player overlay, PlayerTransportButton, PosterPlayButton and scale adapters. | Exercise actual seek/volume/play state across drag, release, media replacement and fullscreen; independently read provider state and confirm one active transport. |
| Scrollbars and routing | SleekScrollbar, ScrollBinding and SceneRail; outside-track drag and retirement have real OS-input positive/negative evidence. | Qualify nested rail/outer scrolling and sustained frame delivery under load; scrollbar correctness alone does not establish smoothness. |
| Menus | ChoiceMenu/Popover, RunHoverMenu and tk.Menu. | Audit dispatch/lifetime ownership across all callers; exercise dismiss, focus transfer, stale owner and reopen with exact callback/target assertions. |
| Dialogs, focus and keyboard | ActionDialogSurface, KeyboardScope and Toplevel adapters. | Qualify nested modal close, valid focus restoration, constrained footer reachability and edit-key precedence in actual dialogs. |
| Lists, tables and selection | Listbox, Treeview, ChapterList; PixelScrollTable has no direct constructor sites in the current inventory. | Verify live selection identity through sort/filter/data replacement and keyboard traversal; confirm indirect uses before retiring or migrating a helper. |
| Progress and feedback | SleekProgressbar; real Tcl trace/timer disposal failures repaired, with shared-variable successor control. | Exercise all four direct contexts, determinate/indeterminate transitions and truthful completion/error feedback; qualify layout and accessible status independently. |

All families require relevant Mac and Windows source-native execution and exact
packaged evidence before cross-platform/package claims. Physical device evidence
is required only for claims about physical mouse/trackpad behavior; injected input
remains useful, explicitly bounded evidence. Contextual visual review may be
performed by the engineer reviewing the actual rendered journey, with identity,
images and rationale recorded. An external reviewer is not a universal prerequisite.
User acceptance of the original reported failures remains distinct. Automated
measurements must never be labeled machine certification of intuitive design.

| Open work | Owner and next bounded step | Completion evidence |
| --- | --- | --- |
| Library delayed resize completion | Library scene scheduling/artwork presentation and native window lifecycle: correlate queued drawing with native resize-end, then change the measured bottleneck. | Same paired workload and independent OS geometry/input sampling; retain current failure and distinguish layout, native completion and presentation. |
| Resize retained until another click | Native input/window lifecycle: preserve the separate edge/reentry/outside-release/focus-loss matrix and investigate a reproducing device case. | Existing eight injected-input passes and two detected faults stay narrow; no closure of the physical report without supporting evidence. |
| Sustained scrolling | ScrollBinding, scene paging/rails and scroll_observations: exercise repeated loaded traversals with independent visible-frame observation. | Per-movement latency, worst gaps, complete tail and observer validity; genuine late and frozen-middle controls must still fail. |
| Artwork composition | archive_artwork/presentation and scene renderers: delayed decode plus resize/reuse with calibrated nonuniform artwork. | Visible owner, layer count, shape and placement during the operation; detect duplicate/circular-over-rectangular and stale layers. |
| Tab flicker | ViewTransition and destination preparation: inspect actual repeated transitions under slow artwork and player teardown. | Captured intermediate pixels plus owner/state assertions; settled screenshots alone are insufficient. |
| Full telemetry | Existing producers/outbox, public serializer and authenticated ingestion/storage owners: enumerate missing producer journeys and complete one contract at a time. | Actual event through local outbox, authenticated backend and stored readback; consent/withdrawal, offline/retry, duplicates, privacy, useful query and explicit denominator limits. Local backend proof does not certify deployed delivery. |
| Coverage enrollment | interaction_coverage and domain evaluators: enroll bounded reviewed assertions from retained real evidence, starting with a repaired owner journey. | Explicit phase/dimension mapping, content-bound evidence and detected behavioral negative; report qualified dimensions without promoting unsupported ones. |

Do not hold every claim unproven until the entire application is finished.
Enroll completed bounded contracts with their supported platform and input tier.
Do not replace migration gaps with self-attested passed flags, or remove a
required blocker without a reviewed evidence path.

### Native resource retention during interactions

The Mac native registry includes test_surface_memory_native.py. Its isolated
child runs quality_harness.native_surface_memory against the production
CanvasSurfaceCache and image factory. The probe warms a complete 96-size working
set, then records six 24-frame replacement cycles, teardown and a one-second
settle through the actual Tk mainloop. It records current RSS independently of
managed cache bytes, Tcl image counts and process lifetime highwater.

The surface-cache regression also exercises an oversized displayed hero, smaller
controls, repeated identical frames, size/scale/palette replacement, interrupted
rendering and clear. Reuse must preserve exact pixels without growing the unused
LRU. The native Watch contextual-action test caught repeated hero reconstruction;
its passing redraw count does not establish a native RSS plateau.

The plateau allowance is derived from the existing 8 MiB unused-cache budget
plus two largest native backings in the fixed workload (old/new overlap).
It is not a threshold adjusted to a candidate's result. Warmup, complete cycles,
runtime library paths/content hashes, source stability and during-operation
samples are required. Missing coverage remains unproven. Sample gaps over 50 ms
are invalid for this claim; preserved samples can expose a mid-cycle violation
even if the settled endpoint recovers. RSS allocator retention is not itself a
leak: review repeated growth after warmup separately from the lifetime peak.
This is a finite component workload, not a universal process-memory ceiling.

Run the maintained component check from the repository root:

~~~sh
VODFORGE_NATIVE_UI_TESTS=1 PYTHONPATH=.:engineering-quality python -m pytest -q tests/test_surface_memory_native.py
~~~

The test starts only its isolated QA process. Crash-restoration suppression is
process-local; it does not change persistent OS preferences. Do not add forced
collection, global autorelease pools, manual native releases or relaxed limits
to manufacture a plateau. Bind any diagnostic dependency override to the actual
loaded binary, including path, hash, version and source/patch provenance.
A modified runtime is not the installed app or an approved distribution dependency.

The current Tk 9.0.4 native image path fails this retained-memory check even when
the declared cache is empty and Tcl image names retire. An isolated reference-
balance patch passes the bounded plateau and native lifecycle controls, but is
not adopted for distribution. The raw RGBA optimization was rejected and reverted;
the managed PhotoImage alternative also failed the narrow Watch resize-release
check. Keep native retention and resize acceptance open. These findings show why
pixel equality and ownership-unit checks alone cannot certify native resources.

### Pipeline observer lifecycle

The existing pipeline runner records run-correlated control observations from
worker start through control request/dispatch and retirement. When the worker
finishes, a delayed cancellation predicate loses authority to change its state
or terminate children. Polling stops; a stuck or failed observer is reported as
a harness error even if the product endpoint otherwise appears correct.
This protects later jobs from the harness itself. It does not by itself qualify
all pipeline phases: staging, progress, commit, and recovery still need their own
independent assertions and negative controls.

## Evidence quality and limits

Use monotonic ordering within a process and explicit correlation across processes.
Bind observations to the current operation and owner/generation. Record clock
limitations, sampling gaps, dropped observations, observer errors, and capture
overhead. A missing interval cannot establish absence of a short-lived defect.
Keep evidence bounded and privacy-safe; retain aggregate counts plus relevant
failure windows without silently dropping the events needed by an assertion.

Distinguish physical input, OS-injected input, generated Tk events, programmatic
geometry, headless owner calls, and static analysis. None silently substitutes
for another. Frame scheduling or callback completion is not proof that pixels
were presented. Resource sampling is not proof of responsiveness.

Choose performance thresholds before accepting the result, with a documented
workload and user-visible rationale. Retain distributions and worst gaps; an
average can hide stalls. Compare the same machine, load, data, input sequence,
and instrumentation. A generous liveness timeout is not a smoothness budget.

The reported Channels defect includes circular artwork over rectangular artwork
and duplicated images in different formats, not only stretched aspect ratios.
A valid oracle must check intended visible layers, shape, placement and owner
through delayed decode, resize and view reuse. A solid-color image or final
width assertion cannot detect this class.

## Updating a check or adding a feature

1. Preserve the report, artifact identity and reproducer before editing. User
   observations can reopen acceptance without requiring the user to supply a
   video or an automated trace.
2. Identify what the old assertion actually established and why it missed the
   failure. Separate confirmed facts from proposed product causes.
3. Add or update the requirement mapping and fixture. Cover relevant in-flight
   states, owner replacement, delay, failure, cancellation and recovery.
4. Extend the existing recorder/probe and add independent behavioral assertions.
   Logging more timestamps alone is not a harness improvement sufficient to
   close the coverage gap.
5. Demonstrate detection against the known-bad implementation or a bounded,
   realistic fault. A transient violation followed by successful completion must
   still fail. Missing evidence, stale identity and observer failure must not
   become passes. A broken fixture or collection error is not defect detection.
6. Verify corrected behavior at the appropriate tier, then verify enrollment,
   report propagation, schema compatibility, and acceptance blocking. Add harness
   self-tests for those decisions, not just tests mirroring the recorder.
7. Update this guide when the workflow changes, the domain ledger when coverage
   changes, and the release guide when promotion requirements change. Record
   executed results separately from planned checks and outstanding limitations.

Tests live in the production test suite and this directory's `tests/`; scenario
enrollment lives in the registry and domain contract modules. Update both where
necessary. Preserve previous failed receipts rather than overwriting them with a
rerun. New features require their regression, harness, and applicable telemetry
coverage together.

### Maintenance checklist for every affected feature

Use this checklist when opening the change and again when reviewing its evidence.
It applies to new features, shared-control changes, bug fixes, and changes to the
harness itself. Record explicit applicability reasons rather than silently
omitting a dimension.

| Change surface | Required maintenance |
| --- | --- |
| User flow or appearance | Update the journey's before/during/after assertions and restraint review. Exercise default, expanded, loading, interrupted, and recovery states that the feature supports. Include sparse content and constrained layouts. |
| Shared component | Update its catalog and reviewed use-site inventory; exercise affected adapters and callers, keyboard/focus behavior, ownership retirement, and a detected drift or bypass. |
| Runtime behavior | Add an independent regression for the defect class, meaningful valid controls, and relevant ordering/fault variations. Preserve the original failure. |
| Scenario or oracle | Verify registry enrollment, raw evidence binding, evaluator self-tests, report propagation, and the required gate's failure behavior. Missing or incomplete observations remain unproven. |
| Telemetry | Update the producer/backend contract and coverage ledger together. Verify applicable consent, offline/retry, duplicate handling, bounded causes, stored readback, and the query the event is intended to support. State missing denominators and delivery boundaries. |
| Operating instructions | Update this guide if ownership or workflow changes, the setup guide if commands/dependencies change, and the release guide if promotion rules change. Check their links and examples. |
| Acceptance record | Attach exact commands, source/artifact identity, raw and evaluated evidence, human review, and outstanding platform/tier gaps. Keep historical receipts intact. |

A feature is not fully qualified merely because its happy-path test passes.
The report must make functional behavior, interaction continuity, usability review,
and telemetry applicability visible together. Keep technical diagnostics in the
engineering evidence; the product should give users only the controls and
feedback useful for their current task.

When the harness misses a defect, update both the product regression and the
harness's ability to detect that class. When an oracle is wrong, retain its old
verdict and the raw trace, document the corrected interpretation, and demonstrate
that genuine bad behavior still fails. Do not relax a threshold solely to make a
candidate pass.

## Acceptance and promotion

Report passed, failed, skipped and unproven separately at the claim level.
A required missing phase, weak oracle, unexecuted tier, or unresolved user failure
blocks the affected acceptance claim. Do not aggregate unrelated passes into
permission to promote. A source fix does not certify an older installed package.

This applies to private review replacements as well as public release decisions.
Do not present a known-rejected candidate as completed work. Explicitly scoped
diagnostic artifacts remain diagnostic; the standard is not waived by calling
an artifact private. Public distribution additionally requires all existing
signing, immutable-artifact and telemetry gates.

The initial NORMAL/DEEP blockers are implemented; domain evaluator enrollment and
domain negative-control evaluation remain incomplete. The private-install entry
point shares the blockers; reviewers must retain those
gaps explicitly. The implementation status must remain visible;
documentation, a recorder, or a proposed test matrix is not proof that the entire
harness now enforces the standard.


## Native scrolling evidence

The paired scrolling check exercises Library Channels, Watch Channels, the
Library media grid, Watch home, and the All runs popup with the same OS-injected
pixel-wheel cadence. It separately records accepted input, scroll callbacks,
heartbeat samples, renderer timing, and own-window pixel frames. Run it through
the native harness, which includes the engineering-quality package on PYTHONPATH.

The current pixel evaluator requires an initial stable frame, observed movement,
complete ordered timestamps, capture overhead and sampling gaps at most 50ms,
and a first visible response and a changed frame following accepted movement within
100ms. Reaching a scroll boundary does not require continued pixel movement.
Pixels may update before the scroll callback returns; that is valid during-operation
feedback, not a missing later frame. The 100ms bound detects conspicuous delayed response or freezes; it is not
a 60Hz smoothness claim. Missing or slow capture is unproven. A settled final
position, quick callback, or later successful redraw cannot clear a transient
failure. Preserve the paired reference run and source identity. Physical wheel,
trackpad inertia, more loads, and refresh-rate acceptance remain separate tiers.

## Native resize observation boundaries

The Channels resize probe schedules OS-injected drag events against monotonic
deadlines. A separate sampler observes window-server geometry and global button
state; it records each call interval and actual cadence. Sampling no longer
extends the driver's intended interval. Shared-process scheduling can still
perturb both, so retain actual post timestamps and sampling overhead.

The same receipt records AppKit frame observations, Configure events, Canvas
layout commits, the final commanded drag position, and source manifests before
and after execution. These are distinct observations: posting mouse-up does not
prove AppKit consumed it, and a committed Canvas layout does not prove compositor
presentation. Samples that straddle release cannot establish post-release geometry.

Compare repeated identical drags with both a stationary and a moving pointer
after release. Geometry that keeps changing while the pointer is stationary
supports delayed drag processing; it does not establish pointer-follow. Keep the
original release-stability failure open in either case. Do not add a settling
delay or loosen acceptance merely because final geometry eventually matches.

The probe requires real calibrated artwork and actual resizing before evaluating
scene behavior. Disabled rendering must fail the content-adaptation oracle.
Omitting controls, artwork or entire canvases is diagnostic isolation only;
such experiments cannot qualify the product's visual or interaction acceptance.
Other edges, reverse drags, physical devices and compositor timing remain
separate unproven coverage.

## Recording a review

Use this compact record in the run's evidence directory for each affected journey.
Link its assertion identifiers and raw artifacts from the report; do not mark a
requirement covered merely because this record exists.

~~~text
Requirement / journey:
Production owner and enrolled scenario:
Source manifest or exact packaged identity:
Platform, fixture/load, viewport, input mechanism:
Before / during / after assertions:
Observer cadence, overhead, missing intervals, clock limits:
Negative control and observed detection:
Corrected run and raw evidence paths:
Usability review: orientation; action hierarchy; disclosure; visual hierarchy;
  sparse/busy content; feedback; accessible interaction.
Each review dimension: reviewed / failed / unproven, evidence, reviewer.
Shared component roles/adapters/use sites, parity evidence and remaining bypasses:
Telemetry contract and consent/privacy checks, or applicability reason:
Result by claim: passed / failed / skipped / unproven.
Remaining blockers and next required tier:
~~~

Keep machine assertions separate from the human design review. For example,
a one-video playlist can pass correct playback, keyboard focus, and unclipped
text checks while its composition remains unreviewed. A source-detail expansion
can expose all fields correctly while still failing the requirement for a clear
summary and restrained default controls. Both results belong in the same journey
record so neither disappears behind a green test total.

### Current native drawing limitation

The Mac child-viewport scrolling seam currently services at most six idle
batches after one complete scroll dispatch, checking a 40ms scheduling budget
between batches. This is a soft scheduling bound: an individual callback cannot
be preempted. A toplevel guard prevents recursive draining; lifetime tests cover
navigation, destruction, nested scrolling, and rescheduled work.

These lifecycle checks do not establish sustained smoothness. The four-batch,
8ms experiment failed Watch home response and its negative control had insufficient
sampling. A revised six-batch/40ms run passed all eleven pixel and lifecycle cases,
including the negative control, with unchanged response and sampling thresholds.
The diagnostic observed three to five drawing stages taking about 13-39ms.
Preserve both runs. Sustained and alternating input, nested-axis backlog, comparison
against All runs, and physical trackpad acceptance remain unproven; the soft budget
cannot preempt a slow callback.

## Full-application telemetry acceptance pass

Track qualification in the [full telemetry inventory](acceptance/TELEMETRY_COVERAGE.md).

The required scope now includes every supported user journey and application
lifecycle, not just existing event producers. Track startup/bootstrap/settings,
updates and recovery; Forge source/local conversion/presets/queues/downloads/
retry/cancel/export; Library discovery/organization/source and output details/
storage/file actions/missing or offline media; Watch and playback controls;
navigation/popups/keyboard/scroll/resize/presentation; persistence/workers/process
ownership/shutdown; and telemetry transport itself.

For each journey map intent, admission, progress/latency, result, failure,
cancellation, abandonment, and recovery where applicable. Identify authoritative
producers, source/build/platform/config context, safe correlation, stable causes,
denominators, and the usability questions a stored query can answer. Explicitly
review failed, no-op, and dead-end actions. Unsupported features or inappropriate
observations require a meaningful exclusion; missing required evidence blocks
acceptance. Existing event vocabulary coverage alone is insufficient.

Verify actual producer -> bounded outbox -> authenticated ingestion -> stored
readback and analytical usefulness. Inject early startup and late shutdown
failures, duplicates, offline delivery, withdrawal and disabled consent, transport
failure, and realistic complete journeys. Distinguish input arrival from rendering
and presentation limits without disruptive sampling. Preserve consent epochs,
privacy, bounded retention and sampling; do not collect raw keystrokes, media
content, screenshots, filenames, paths, URLs or secrets. This pass remains open:
it cannot promise diagnosis of every future bug or replace unknown evidence with
a generic failure count. Local verification and production deployment are separate.

## Control styling follows shared ownership

After the all-control ownership audit, consolidation, and functional bug fixes
are complete, experiment with VODForge's own
matte, soft and cozy surface treatment across every theme through those maintained owners. Keep
the default violet palette and current styling during functional repairs. Matte
describes the material treatment: muted reflections and subtle depth, independent
of palette. External soft-depth examples
inform surface craft; they are not layouts or components to copy. The referenced
basic search field is not the quality target. Preserve the approved media
composition, gradients, glows and fades.

Review raised/inset depth, edge illumination, radii, icon/type alignment, and
normal, hover, pressed, focused, disabled and selected states for every applicable
control family. Context-specific state and callbacks stay with the current owner.
Do not introduce view-local styling copies to complete the appearance pass.

Qualify contrast, readable labels, keyboard focus and activation, hit areas,
narrow layouts and sparse/busy content. Compare sustained scroll, resize and
interaction costs with the same workload before and after styling; attractive
depth does not excuse delayed feedback. Keep this subsequent pass open until
ownership, contextual visual review, native behavior and relevant performance
evidence are complete. Existing defect and telemetry gates continue to apply.

## Escaped-defect example: action lifetime

The native release-outside failure exposed a general invariant: an action may
execute only for an admitted intent that still belongs to the same enabled
control and callback at its commit boundary. Prior command-invocation and final
geometry checks did not exercise pointer admission or retirement. The minimized
regression is press inside, release outside, assert no action.

The enrolled test_button_parity_native.py now has an independent intent model.
Three recorded seeds (7149, 27183, 49157), each with 32 episodes and 20 steps,
vary press/release, outside release, disable/re-enable, callback replacement,
widget destruction/replacement and direct invocation. Each prefix is checked.
The real pre-fix ttk.Button bypass fails the same model; fixture construction
errors do not count as detection. Shared ProductButton passes. Keep the seed and
trace when a generated sequence fails, then reduce that trace to a focused
regression while preserving the broader generator.

Source-bound receipt: button-generated-v8-b.log and the paired
button-generated-source-before-v8.json / button-generated-source-after-v8.json
in the September 17 UI-foundation evidence directory. The identical source
manifest SHA-256 is 8eea0432f8a83387157ad553bdc393532bfb885362cf820f0f2382979a2fb4bf. Four generated/negative-control
tests passed. This is a bounded generated-Tk event check, not physical pointer,
all interaction states, packaged or all-component certification. Additional
families require their own independent models and adoption evidence.

Apply this record structure to every escaped defect: invariant, old-oracle gap,
specific regression, broader bounded exploration, behavioral negative control,
exact source evidence and remaining limits. Use risk-weighted boundary and
pairwise variations, deterministic seeds, lifecycle faults and delayed results;
avoid an unbounded random-click suite. Keep broader exploration in the relevant
profile and preserve failing receipts.

### Keep the harness independent

Specify the user-visible invariant before changing the implementation. Do not
weaken limits, remove difficult fixtures or redefine success merely to make a
candidate pass. Correct an invalid oracle only with independent evidence of the
actual contract, preserve its old failure, and rerun a genuine negative control.
Record valid and invalid controls together. A supplied implementation detail,
internal event or model counter is not by itself evidence of user-visible success.

For generated sequences report operation reachability, meaningful outcomes,
distribution and unobserved transitions. Seed and transition totals alone do not
establish coverage. Retain bounded held-out seeds for deeper profiles, stable
reproduction and minimized failures. A no-op is useful only when the requirement
expects no effect; no-op episodes must not inflate success claims. Physical
input, generated native events, direct invocation, owner calls and stored
readbacks establish different contracts and must remain separately identified.

The model now requires a valid pointer commit and an invalid outside release in
every episode, asserts operation reachability, and records bounded full traces,
operation/state-transition histograms, accepted pointer commits, direct
invocations and retired releases. DEEP adds six fixed held-out seeds through the
actual scenario/native-runner profile. The nine-seed run passed with 357 pointer
commits, 417 direct invocations and 1,378 retired releases; these are workload
facts, not a completeness claim.

Applying the same admission invariant to ModernCheckbox exposed mouse-down
commitment at all three pointer surfaces (frame, checkmark and label). The prior
toggle/value checks did not cover the press-to-release interval. The focused
three-case run failed before the shared-owner fix; the following 76-case native
UI/shared-control/showcase run passed. Preserve checkbox-admission-before-v8.log,
checkbox-admission-before-source-v8.json and checkbox-admission-after-v8.log.
This is a second concrete escaped class caught by broader interaction review;
generated checkbox sequences and complete consumer adoption remain open.

A further lifecycle variation hides and remaps a pressed button before release.
It failed even with the first release-boundary guard, exposing a missing unmap
retirement. The same press-to-commit check failed for all three SegmentedSelector
layout modes. ProductButton now retires on unmap; the shared selector captures
the pressed segment/variable and commits only its current, visible release.
Checkbox gestures also retire on unmap. Four pre-fix failures and the following
30-case passing run are retained as control-retirement-before-v8.log and
control-retirement-after-v8.log, with pre-fix source/test hashes. This demonstrates
a coverage gap discovered while extending the invariant beyond the first fix;
it does not establish all-family completeness.


### Preserve the final response window when evaluating scrolling

Input posting can finish before the last callback and its presented pixels.
Evaluate the full recorded frame tail, retaining capture overhead and sampling-gap
checks. A truncated tail ending before an unresolved movement's 100ms response
window completes is unproven. A response later than 100ms still fails; do not add
a settling allowance.

The previous evaluator stopped at the first post-input frame and falsely rejected
five retained responsive traces whose final movement appeared 33-58ms later.
Independent timeline controls reproduced that false failure and a premature failure
from missing tail evidence. The corrected nine-case oracle suite retains transient
freeze and late-response negatives. Reevaluation of unchanged raw native evidence
still rejects the actual deferred-paint control at 345ms. Historical receipts remain
unchanged; scroll-tail-reevaluation-v8.json identifies both evaluations and raw hashes.
This correction does not close broader physical-input or sustained-scroll acceptance.

Native resize receipts also bracket the observed OS button transition, with button
read timestamps separate from geometry sampling. Posted-up and observed-up stability
are separate required assertions. Combined-session state includes injected events
and is not physical-device proof. Native stack sampling perturbed the control run:
use those profiles to rank work, not for uninstrumented timing acceptance.


Scroll response reports now retain a bound for each accepted movement. A frozen
middle must still fail even when the final movement catches up quickly. A separate
counterexample intentionally jumps at intervals below 100ms: it can satisfy the
coarse response bound while continuous_smoothness remains unproven. Eleven oracle
controls cover these distinctions, prompt in-handler pixels, delayed first/final
responses, scroll boundaries, observer failure and incomplete tail. The native
full-tail rerun plus the then-nine oracle controls passed 20 checks; the additional
two counterexamples passed separately. Do not turn either result into refresh-rate
or physical-device acceptance.

Extending action-retirement review to choice fields exposed another shared-owner
gap: replacing an option list left the old menu authorized to select stale values.
Retain choice-retirement-before-v8.log (three behavioral failures) and
choice-retirement-after-v8.log (92 native integration passes). The owner now retires
changed option snapshots while preserving identical-value updates and fresh valid
selection. This expands the class beyond buttons, toggles and segments; it does not
close the remaining control-family inventory.


### Verify the input target, not only the final result

A native input test must demonstrate that it reached the intended control during
the intended phase. For example, the shared scrollbar regression records actual
Canvas movement while pressed, preserves the other axis, and rejects unintended
window movement/resizing. Input posting runs independently of the UI loop so an
OS tracking loop cannot prevent the driver from releasing its own button.

A fixture that hits native window chrome instead of the control is invalid
evidence even if a final assertion later passes. Preserve the trace and explain
the invalidation; repair the target/driver and add an assertion that detects the
same fixture mistake. Exercise the repaired oracle against the old broken
behavior. Keep physical-device, presentation-latency and sustained-smoothness
claims separate from OS-injected control ownership.


### Separate delayed resize completion from a retained drag

The defect ledger keeps resize-delayed-completion separate from
resize-release-following-pointer. The first compares posted/observed button
release with pending layout and native geometry completion, including stationary
pointer input. The second observes actual native bounds during free movement
and re-entry after native resize ends, without another click. A bounded delayed
finish does not reproduce the user's report of continued resizing until a click.

The retained-drag matrix exercises lower-right, left and bottom edges on Library
and Watch, release outside the original window, and seven free pointer positions.
Two additional cases transfer focus to another isolated native window while the
button is held and verify that focus actually changed. They retain the process/
window identity, native resize-end observation, independent button/bounds samples,
input trace and exact source binding. Missing native end, missed input, insufficient
sampling or an unexercised focus transfer cannot establish a pass.

A controlled fault that changes native geometry on free pointer movement after
resize end demonstrates the observer detects a stuck-drag-shaped violation. It is
an oracle sensitivity control, not proof that the original product fault has been
reproduced. Keep physical-device, other gesture sequences and compositor coverage
explicitly open. Local AppKit event monitors may miss events consumed by native
tracking loops; a resize-end notification is a lifecycle boundary, not a direct
timestamp for handling mouse-up.

For telemetry timing, test the meaning of the measurement, not only its schema.
The [presentation audit deadline regression](../docs/telemetry-features.md#presentation-audit-scheduling-delay)
checks that repeated scheduling cannot erase an existing wait and that replacement
operations do not inherit another owner's delay. Its local producer-to-readback
query is evidence for that bounded metric, not an interaction-performance pass.

The resource decoder rejects negative, nonfinite and boolean counters, including
samples preceding warmup. Receipts report initial/warm/peak absolute RSS beside
the backing and cache budgets. A large warm baseline can hide retained memory:
passing this finite replacement check is not absolute-footprint acceptance.
Slow growth below its finite allowance is also not ruled out. Independent longer
runs, held-out working sets/scales and complete native teardown journeys remain
required deeper evidence before runtime adoption; do not tune this allowance to
the candidate's observed growth.

A later native run found an OS notification window covering the vertical
scrollbar target while the QA window was key and active. Window-server bounds,
missing Tk delivery and the unobstructed horizontal control distinguished this
fixture failure from scrollbar behavior. Preserve the failed run; move only the
isolated QA fixture clear of the obstruction. The maintained check now requires
actual press/motion/release delivery at its control. Both repaired targets pass,
and reinstating the old Leave handler still fails both movement assertions.
Never treat key-window state or a Tk hit test alone as proof of input delivery.

The segmented-choice focus regression likewise records before/during/after
pixels, including selected and unselected options, rather than inferring visible
orientation from focus ownership. Its three original layouts failed before the
shared renderer repair. Qualify focus visibility, unchanged selection and layout,
restoration, and keyboard activation separately; this is one bounded usability
dimension, not whole-control or whole-application acceptance.

Context-menu lifetime checks use real Tcl widgets and command registration.
Repeated opening and source hiding failed for both Library and Watch before
shared ContextMenu adoption. Check bounded widget/callback counts, a valid
queued callback after native popup return, rejection after owner retirement,
fresh successor actions, cascade teardown and independent windows. A fake
unposted popup isolates command lifetime; it does not qualify native menu
placement or physical input. Retain that distinction in the report.

### Running deeper native resource checks

The maintained Mac resource test selects its workload set from
VODFORGE_NATIVE_PROFILE. From the configured repository environment:

~~~sh
PYTHONPATH=.:engineering-quality VODFORGE_NATIVE_UI_TESTS=1 VODFORGE_DISABLE_TELEMETRY=1 VODFORGE_NATIVE_PROFILE=deep VODFORGE_NATIVE_EVIDENCE_DIR=/absolute/path/to/new-evidence python -m quality_harness.native_process -p quality_harness.native_reports tests/test_surface_memory_native.py -q
~~~

Use a new evidence directory for each run. Omitting the deep profile runs only
the normal workload. These are source-native checks, not package acceptance.
Each receipt records loaded Tcl/Tk paths and hashes; a diagnostic runtime result
must not be attributed to the installed runtime.

| Workload | Warmup replacements | Measured replacements | Working set | Scale |
| --- | ---: | ---: | ---: | ---: |
| normal | 96 | 144 | 96 | 3 |
| long_scale3 | 96 | 960 | 96 | 3 |
| heldout_scale1 | 122 | 610 | 61 | 1 |
| heldout_scale2 | 146 | 730 | 73 | 2 |

The decoder accepts only the enrolled workload definitions. It retains the
existing backing/cache-derived allowance, samples throughout replacement and
teardown, and reports absolute initial/warm/peak RSS alongside finite growth.
Cycle trends are descriptive, not a separate indefinite-leak pass. A safety
abort, missing observations or modified workload cannot become a pass.

Interpret matched controls per workload. A control that passes at a smaller
scale does not demonstrate sensitivity to the original larger-scale defect.
The diagnostic paired run retained in memory-deep-patched-v8 and
memory-deep-control-heldout-v8 illustrates this: all four patched cases passed,
but the unmodified heldout_scale1 control also passed. Preserve both results.
Neither qualifies whole-application memory, physical resize behavior or runtime
adoption. Complete native application teardown and exact-package journeys remain
separate requirements.

### Unexpected native lifecycle warnings fail qualification

The native_reports plugin turns PytestUnraisableExceptionWarning and
PytestUnhandledThreadExceptionWarning into failures. A completed test assertion
cannot qualify a run whose finalizer failed or whose worker crashed. The existing
native runner loads this plugin; use the same plugin in focused native commands.
There are currently no approved blanket Tk/thread warning exceptions. Any future
expected diagnostic fault must be narrowly scoped, explained and asserted by its
test; never hide the warning class globally.

The subprocess controls in test_native_lifecycle_warning_gate.py demonstrate
that ordinary success passes while a failed destructor and an unhandled worker
exception each make pytest fail. Raw incremental phase results retain the error.

The retained 64-pass run's Tk Variable finalizer warning was not a clean lifecycle
pass. Instrumented reruns changed collection timing and did not reproduce it;
that nondetection did not close the issue. A controlled real-widget sequence
showed checkbox, segmented-selector and choice-field cycles retaining their
variables after destruction. Later worker-side collection attempted Tk access.
Allocation/disposal stacks and worker completion were recorded separately.

The maintained regression holds each destroyed widget alive and requires prompt
release of its no-longer-owned variable without calling garbage collection.
An externally owned variable must remain usable. Product destruction now releases
those references and retires callbacks/press state on the UI thread. An isolated
adversarial collection diagnostic demonstrates the failure before and absence
after; it is a fault-injection test, never a product GC workaround. This repairs
the demonstrated ownership class, not an assertion that all future lifecycle
failures have been ruled out.

### Retired player input is not a successful interaction

The player retirement matrix extends lifecycle coverage to lists, timelines,
previews and volume. It runs a valid action before retirement, then repeats the
captured callback after explicit close or external widget destruction. Assert
both absence of stale widget errors and absence of provider/feature calls.
A destroyed widget that raises TclError is a failure even if playback ultimately
stops. Conversely, silently invoking an already-shutdown provider is not harmless
success. The source-native runner enrolls test_player_action_retirement_native.py;
keep its controlled-provider scope separate from real playback and packaged runs.

The player successor matrix additionally replaces media on an open owner,
including the same path and a different backend. Media-bound timestamps and
chapter/preview coordinates must retire before old widget access. Valid original
actions and valid fresh current-transport commands are separate positive controls.
Provider tests distinguish prevalidation rejection from replacement failures after
provider mutation. Keep serialized UI admission separate from untested concurrent
provider mutation. The actual app's new-player-per-launch path remains the primary
integration contract.

The native reporter also fails ObjCPointerWarning on macOS. Its fresh-process
negative control intentionally requests an unregistered NSColor.CGColor bridge;
the positive player test loads the actual overlay and verifies a typed CGColorRef.
No warning is filtered away. Quartz is an explicit platform dependency, so a
passing workstation with an incidental framework install cannot substitute for
dependency declaration or eventual package qualification.

When extending lifecycle coverage, include field variables, raster images,
registered bindings and pending idle work. A destroyed widget held by another
Python object must not retain obsolete Tk resources until worker-side garbage
collection. Preserve externally owned variables and other live field instances.
The shared-controls field matrix now includes placeholder/search owners and their
shared border renderer. Passive cleanup has no new usage event; unexpected errors
remain visible through the strict native reporter. This does not mark full text
editing or cross-platform usability coverage complete.

Root-level image owners need a distinct shutdown test: a child dialog closing
must preserve shared styles, while actual root destruction releases every owned
image even when a Python reference to the owner remains. Check late requests
without relying on collection, and retain the pre-fix weak-reference failure.


### Native QA startup and nested processes

The source-native runner uses native_process.native_pytest_command. On macOS it
registers process-local startup defaults before importing the application and
passes process-local flags that avoid restoring a previous QA window. It never
writes persistent macOS preferences. Windows retains the ordinary pytest command.
Focused native checks can use python -m quality_harness.native_process with their
pytest arguments; preserve PYTHONPATH, native opt-in and isolated evidence settings.

A native test that launches another Python process must use
native_process.native_python_command for that child too. Parent initialization
does not initialize a child process. Data arguments keep their positions; macOS
launch flags follow them and are removed before pytest parses options.

The retained recovery-child timeout in root-chrome-after-v9 was followed by a
successful isolated child with this startup initialization. The original30second
limit and product assertions remain unchanged. Keep the failed receipt and do not
dismiss another timeout as startup without evidence.


### Distinct artwork identity during resize

The source-native scene suite now includes
~~~text
tests/test_scene_inflight_native.py::test_distinct_artwork_pixels_during_stepped_resize
~~~
It supplies distinct local channel images through the production artwork worker,
binds expected ownership at the caller boundary, and captures only its own window
on an independent observer thread. Captured pixels are converted using their ICC
profile to sRGB before comparison. A capture crossing a layout generation or
native geometry change, or whose native width differs from the committed layout,
is ambiguous rather than an identity pass. Observation gaps remain explicit.

The bounded check requires before/during/after observations, at least three widths
while the button is pressed, continued presence of the initially visible owners,
and correct interior identity patches. Its wrong-owner control substitutes a real
cached image while retaining the requested owner's expected identity and geometry.
The independent pixel evaluator also has a repeated-image negative control.
An empty artwork list cannot qualify as an absence-of-duplication pass.

This exposed Watch's default-size invalidation clearing unchanged explicit-size
avatars during resize. The shared artwork owner now retains cached explicit
tile/hero specifications; default-sized pixels still retire, changed sizes and
metadata keep distinct keys, and existing bounded cache and revalidation owners
remain responsible for freshness. The regression also covers changed avatar size,
metadata replacement, and retirement of default-sized pixels. Retained spec
accounting is the union of valid cached and currently requested specifications,
not accumulation of every intermediate size.

Keep the original failed runs and observer corrections. This fixture proves
sampled center-patch identity under stepped OS input, not aspect ratio, complete
composition, continuous smoothness, physical input, or resize-release stability.
The fast resize gates remain unchanged. Existing artwork collection/load and
presentation telemetry remain authoritative; a cache hit is not a new load event.
Full telemetry readback, broader artwork loads, Windows and packaged qualification
remain separate requirements.


### Mixed content during real tab transitions

The source-native view-transition suite now exercises real Forge, Library, Watch
and Activity navigation commands while an independent thread captures only the
test window. It retains complete frames, capture intervals and the command
intervals. This is command invocation, not physical mouse input. The fixed
980-by-600 / 18-item and 1280-by-760 / 180-item fixtures compare meaningful
content regions against the outgoing
sharp/blurred and settled destination references; navigation selection itself is
outside the evaluated content regions.

The regional oracle in quality_harness/transition_observations.py detects old
and new content appearing in separate parts of one captured window. It requires
at least four distinguishable reference regions, treats unknown pixels as
unproven, and has unchanged-old, unchanged-new, mixed-image and unknown-image
controls. Two old and two new regions establish a mixed-frame failure; this
does not claim to detect every possible seam. The native check retains two
pre-input samples and requires capture overhead and gaps within 50ms throughout
the measured interaction; earlier capture warmup is retained separately.

The maintained test exposed a product failure: Watch's
hero can appear while old Library collections/storage or Forge content remain
under its lower rail area. A subsequent correct frame does not erase the failure.
The first maintained run also had an 84ms initial capture warmup; its receipt
separately records mixed-frame failures. Coverage starts with the two pre-input
reference samples, not that earlier warmup. No interaction threshold was relaxed.

Do not equate a finished Python render callback, a completed Tcl idle callback,
or an AppKit display request with complete presented content. A one-idle
transition-cover change appeared clean in one diagnostic but failed the
maintained test and was reverted. Immediate native display, rail-window reuse,
and disabling the cover also failed isolated diagnostics. An early idle-drawing
probe incorrectly targeted the root rather than a Canvas and did not exercise
that intervention; preserve it as an invalid fixture, not evidence against the
shared drawing owner. The approved blur effect remains.

Window-server image samples are not display-refresh timestamps. This check
establishes sampled mixed content, not continuous smoothness or physical-display
coverage. Broader tab-transition acceptance remains open; headless passes and
the existing synthetic transition test cannot override missing native, physical,
Windows or exact-package evidence.


#### Complete child drawing before revealing the destination

On the installed runtime, the application now calls the existing shared
present_pending_drawing owner on the destination frame while the outgoing cover
is still visible. It services the shared interpreter once per pass, then checks
the transition generation again before deciding whether to reveal. Navigation or teardown
during an idle callback must retire the old completion without removing a newer
transition. Ordinary scrolling retains the same implementation through its
present_scrolled_canvas adapter, restricted to child-containing canvases where
scrolling needs it; there is no second drawing implementation or Tk patch.

The helper bounds idle batches to six and checks a 40ms soft deadline between
batches. It cannot preempt an individual callback; observed diagnostic calls took
approximately 21-59ms in the compact probe and up to about 99ms in a larger
probe. Do not present the soft deadline as a hard latency guarantee.
It checks the Tcl widget command before each batch so root destruction cannot
cause a later query through a retired Tk command. The guard is released in finally.

If pending work exhausts a pass, the transition keeps its cover and yields for
8ms before trying again. Three passes is the maximum; continuously pending work
cannot keep a cover indefinitely. The third pass falls back to reveal, so a
bounded completion is not proof that every possible load drew cleanly. Navigation,
input and destruction still cancel the pending generation. Tests cover normal
completion, yield/retry, never-idle work, cancellation between passes and
replacement during a drawing callback. Scrolling does not add these retries.

The own-view snapshot avoids PNG encoding for a validated opaque, interleaved
8-bit RGBA native bitmap (format zero, bounded dimensions and valid stride).
It copies pixels before releasing native storage. Transparent, unsupported or
short-buffer representations retain the native PNG path. The same-representation
native fidelity check compares exact RGBA bytes against PNG decoding; headless
checks cover row padding, fallback and mutation after return. The diagnostic TIFF
alternative produced identical pixels but a much larger intermediate encoding;
it was not adopted. Raw-byte access initially assumed an objc.varlist; the runtime
returns a memoryview. Preserve that failed diagnostic separately from the
corrected result. Capture timing still determines whether the optional effect is
available; neither byte equality nor reduced encoding work proves tab latency.

The earlier Canvas-only destination search missed Activity: a later native frame
showed strips of old Watch imagery across the new Activity header. Its regional
oracle reported unproven rather than passed, and visual inspection confirmed a
partial-drawing fault. Preserve text-fit-integration-v11/actual-tabs/frame-043.png.
The shared owner now services frame and leaf-widget destinations too. The
before-failing no-child-Canvas test guards this routing gap; root-destruction
coverage exercises both scrolling and whole-destination entry points.

The maintained real-tab test runs both the production path and a negative control
that retains the outgoing cover over half the mapped destination for160ms. This
injects actual old pixels into the live window; captured evidence is never edited.
Both retain the same observation rules and50ms cadence/overhead limits. The positive
requires all evaluated regions to pass; the negative must detect mixed generations. Inadequate sampling cannot count as
successful defect detection. The observer retains each captured image and its actual ICC profile. Conversion
and image-file writes happen after input completes; transforms are reused only
while the profile is unchanged. Acquisition intervals still include the native
capture and byte readback. Pixel color conversion and thresholds remain unchanged.
Preserve the earlier 51.6ms compact capture gap and the 65.7/60.0ms larger-fixture
capture gaps as unqualified evidence, not successful negative-control detection.

Native successor tests schedule actual navigation during child drawing and inspect
ownership at the return of the older completion. Checking only after an outer
event-loop update can miss that boundary because the successor may legitimately
finish too. Rapid tab replacement, immediate internal navigation and root teardown
are separate assertions; a clean sampled frame does not prove their ownership.

The existing appearance.transition_shown event means the cover was shown. It does
not certify destination pixels or successful interaction quality. Retain that
meaning rather than adding a premature success event. Wider loads, physical input,
Windows, full telemetry readback and exact packaging still require qualification.


#### A pixel improvement can still be an unsafe runtime change

A separate Tk publication diagnostic drained up to 16 pending idle batches before
publishing the shared bitmap. Matched clean-control/candidate runs, including
reversed order, detected mixed content on the control and passed the candidate's
tab-pixel checks. Both runtimes still failed the unchanged resize-release gates.

The publication candidate was rejected: invoking its native updateLayer entry
with queued Python idle callbacks aborted the isolated process with a
PyEval_RestoreThread thread-state error. All four direct-entry cases
(slow rescheduling, nested update, context reset and root destruction) aborted;
the matched clean control exited normally without dispatching those callbacks.
Those crashes prevent lifecycle/latency qualification. Sixteen batches bounds a
count, not an individual callback's duration, and does not justify a time-bound
claim. Do not work around this by changing Python thread state or global pools.

Retain the exact runtime hash, source patch, command, loaded-library receipt,
pixel results and crash logs together. Keep publication, retention and earlier
resize variants separate; no combined patch is qualified by separate positives.
The application uses the existing runtime. A future dependency change must
requalify memory, lifecycle, rapid/internal navigation, input latency, drawing,
resize and exact packaging, in addition to these sampled pixel checks.


### Bound repeated text measurement without stale layout

Long-title scrolling must retain the same fitted text while avoiding duplicate
native font measurements inside one fitting operation. The shared
ui_layout.ellipsize_wrapped_text owner uses a local 128-entry measurement cache.
It is discarded after each fit, so another font, scale or width calculation
cannot inherit stale metrics. Full document line counting keeps its existing
contract; this optimization does not truncate source metadata or descriptions.

test_text_fit_work includes a before-failing repeated-prefix case and a changed
font-measurement control, alongside exact visible-capacity and full-line-count
checks. The retained diagnostic measured 173 width calls for 65 unique prefixes
before the change. This structural reduction is not a sustained-smoothness or
resize-release pass: rerun the relevant native journey and retain its independent
pixel, input and timing evidence. No usage event is emitted per text measurement;
existing presentation observations remain the diagnostic owner.


Larger tab fixtures keep the original 230-by-130 region size and extend the grid;
they do not stretch the same 16 regions over a larger area. Stretching diluted
sparse Activity/Forge controls and produced only two distinguishable references,
so that comparison was correctly unproven. Retain those receipts. Fixed spatial
resolution restores meaningful reference separation without changing the
four-reference, two-old/two-new or distance thresholds. The sparse large-view
oracle test covers old, new and mixed pixels. A corrected observer must still
detect the known large Watch mixed-content failure; recalculated historical
receipts are diagnostic reinterpretations, not fresh product executions.


### A transition cover must not transfer an action to an unseen owner

The outgoing blurred pixels do not authorize a button at the same coordinates
on the destination. The real-widget cover-press regression failed because the
old handler removed the cover and generated a new press on the underlying button.
Releasing then committed that unrelated action. A cover press now cancels the
effect only; the next fresh press can activate the visible destination. Wheel
navigation keeps its existing route. The test verifies both rejection and a fresh
valid shared-button action, separately from physical-input qualification. The
initial wrong ProductButton import was a fixture error, not defect detection.
No additional usage event is emitted for a rejected, uncommitted button action.


### Calibrated avatar shape during resize

The same source-native recorder now also runs
tests/test_scene_inflight_native.py::test_artwork_aspect_during_stepped_resize.
Its alternating portrait and landscape fixtures contain centered white circles
with diameter three quarters of the shorter source edge. Square cover fitting
must preserve the circle's diameter, center, circular shape and full circumference.
The independent artwork_observations evaluator inspects captured pixels; it does
not derive expected pixels by calling the production fitting implementation.
Pure controls include stretching in either direction, offset, clipping, filling,
duplication and absence, plus correct rings at multiple sizes.

The native negative replaces cover fitting with straight resizing only for the
controlled non-square fixtures. Center identity remains correct while the shape
oracle must fail before, during and after the drag. Valid fixtures must preserve
both identity and geometry, with three observed pressed widths and the original
stable-capture association requirements. The identity and shape journeys share
one recorder rather than maintaining divergent capture or input implementations.
The existing native scene suite enrolls both entry points.

Before input, record the actual combined button state and native live-resize flag;
both must be neutral without injecting a reset release. Pre-press capture samples
must also remain neutral. Keep pointer and scripted coordinates in the receipt.
An interrupted fixture is unqualified, never repaired into a pass by discarding
its bad frames. Setup neutrality is not proof that product release handling works.
The first Watch shape run was interrupted by user-confirmed manual resizing;
its original log and frames remain, and the separate neutral rerun passed all
eight identity/shape positive and negative cases.

This establishes calibrated avatar composition at sampled frames. It does not
qualify hero/banner/media crops, all artwork layers, continuous smoothness,
physical input, fast-resize release, Windows or an installed package. Existing
artwork/presentation telemetry retains its meaning; evaluating calibration shapes
does not create product usage events.


A rejected isolated Tk experiment also demonstrates why geometry alone is not
artwork acceptance. Its unchanged-size guard, single expose and two-idle-batch
cap passed both live fast-resize geometry cases while captured frames showed
old-sized content and uncovered native background. The calibrated avatar tests
failed both Library and Watch for wrong identity and shape on that same runtime,
with valid neutral input and all required phases observed. Preserve these
contradictory narrow results together: geometry passes cannot override a
presented-pixel failure. The experimental runtime was not adopted.


### Partial repaint must preserve the underlying surface

A settled full-image comparison can miss damage caused by a later small repaint.
The native surface suite now creates and removes an overlay at two locations
over a nonuniform calibration grid. It captures only that window through Quartz
and compares flat cell interiors at their original positions, binding coordinates
to the actual Canvas and native window bounds. Both captures must have equal
dimensions and color profiles. The test verifies that the requested image backend
was actually used; an ordinary-image fallback cannot qualify an nsimage claim.

The ordinary PhotoImage controls preserve the interior pixels. Clean Tk9.0.4
nsimage changes them: its display routine maps a damaged source subrectangle
across the full image destination. The original exact-whole-image diagnostic also
caught ordinary edge antialias differences; those receipts remain. Maintained
assertions use independent flat interiors, where the control is stable, rather
than widening the threshold to admit the native corruption.

A source-rectangle-only isolated Tk correction preserves the full source and
existing destination/clipping. It passed the four partial-repaint cases and the
broader surface/artwork cases, but both fast-resize release checks still failed.
The runtime is not adopted, and the maintained native suite correctly exposes
the unresolved installed-runtime defect. This static repaint check does not
certify continuous resize, all image roles, lifecycle, or packaging. Existing
surface ownership and telemetry contracts remain unchanged.


### Watch hero presence during resize

test_watch_hero_artwork_during_stepped_resize uses the same native recorder as
the avatar checks. It observes the actual Watch home hero before, during at least
three changed pressed widths, and after release. The expected owner comes from
the caller; an independently calibrated upper-right patch avoids the intentional
text gradient. A wrong-owner image must be detected in each phase. Missing
artwork, contaminated input, insufficient phase coverage and source changes
cannot become a pass. Keep the initial blank-hero failure alongside subsequent
results. The hero starts near the left edge to leave room for its scripted outward drag.
Count at least three changed widths, excluding the starting width; record actual
sampled widths rather than assuming every requested drag coordinate was achieved.

The decoded-original repair also has headless tests for recovering a crop marker
that was absent in the narrower presentation, no storage/decode on resize,
metadata/expiry/unavailability retirement, unchanged-file revalidation, oversized
rendered-image availability and worker/cache bounds. The original implementation
must fail the marker/continuity case because it returns no image at the new size.
Use the documented source-native invocation and select this test by node ID for
an isolated rerun; the normal scene registry already includes its test file.

Hero presence and owner patches do not qualify the complete hero crop, rail
composition, every frame, continuous smoothness, physical input, Windows or an
exact package. The two fast-resize release gates remain independent and unchanged.
Existing artwork-load and presentation telemetry keeps its meaning: refitting a
cached original is not a new file load. Full producer-to-storage qualification
remains required separately.


### Pixel evidence at fast resize cadence

test_artwork_pixels_during_fast_resize reuses the artwork recorder and independent
identity/ring evaluators at 24 drag steps, 8 by 2 pixels per step, on a 45 ms
deadline cadence, followed by 16 ordinary pointer moves. This matches the input
cadence of the independent geometry/release gate. It remains a separate calibrated
18-item pixel fixture, not the geometry gate's 40-item delayed-artwork workload.
Run both; passing one does not qualify the other or all rendered controls.

Capture acquisition binds raw own-window pixels, ICC profile, button state,
native geometry and an immutable layout generation. Frames crossing geometry or
layout changes remain ambiguous and excluded. ICC conversion, shape analysis and
PNG compression run after input finishes, so their cost cannot erase the entire
during phase. At most 120 frames / 384 MiB of raw RGB may be retained; exceeding either allowance
invalidates the run. Preserve capture begin/end times and sampling gaps. These
are window-server samples, not refresh-rate or physical-device guarantees.

The fast check requires neutral setup, completed observers, unchanged source,
before/during/after samples and at least three changed pressed widths. Real
straight-resize distortion must fail shape in each phase while owner identity
stays correct. The discarded Tk coalesced-expose/idle-cap build also fails both
positive fast pixel cases with valid coverage: it can improve window geometry
while showing stale artwork and uncovered native background. Preserve that
genuine failing control and verify the actually loaded runtime hash when using
isolated runtime candidates. Never adopt it to make geometry gates green.

An external native-only notification observer can diagnose resize boundaries
without calling Python from AppKit or changing event dispatch. It records
will-start/did-resize/did-end notifications and returns locally observed events
unchanged, with a bounded buffer and a native/Python clock bracket. Missing
events, overflow and clock uncertainty must remain visible. Native resize-end,
posted release, observed button-up and visible frame completion are distinct;
a finite queued completion is not evidence of indefinite pointer-follow.


The fast Library fixture also compares its fixed-size, unchanged search control
against its own settled pre-input appearance, translated to the current Canvas
window-item bounds. The generic transition_observations.compare_unchanged_regions
evaluator preserves owner and dimensions, rejects clipped/missing references and
marks changed dimensions unproven. A difference over eight channel levels in more
than 0.5 percent of a region's pixels fails this calibrated consistency check.
This is not a universal aesthetics metric or approval of the reference design.

The preserved-backing Tk experiment is a required caution: avatar identity and
shape stayed correct, yet the moving search field lost its rounded border.
Installed-runtime control pixels matched exactly; the experimental control lost
696 pixels against a40pixel allowance with valid during-input coverage. Keep both
receipts. The expanded maintained check rejects the experiment, rather than
promoting an artwork-only pass to whole-UI acceptance. Other controls, changing
states/sizes, focus, hover, overlays and full-scene composition need their own
scoped references and tests.

Fixed-size control comparisons require every enrolled reference owner in every qualified observation. A missing control region invalidates the observation; comparing only the surviving controls cannot establish a pass.

Native evidence visibility: the maintained native_reports plugin writes
native-evidence.jsonl as each test finishes and native-evidence.json at session
completion. Each entry identifies the test and hashes files created or changed
during it. The final index marks evidence intact, changed_after_test, or missing,
and binds the session's source before/after. Native scenario reports link this
index beside functional results and import identities. This exposes overwritten
screenshots and missing artifacts rather than silently reusing the latest file
as an earlier check's evidence.

These are pytest-case boundaries, not inferred user-interaction phases. A
before/pressed/released capture must still be produced and evaluated by the
interaction's existing check. An empty index entry, a file hash or a green test
does not qualify temporal coverage or any usability dimension. Indexing happens
after the test/teardown, outside its measured input interval; the final index
does not replace independent timing or pixel observations.


File-action telemetry regressions belong in tests/test_library_file_actions.py,
using the existing operation owner and temporary history. Exercise permission
changes between preview and confirmation, failed binding/recording, cancellation
and durable outcomes. Export actual allowed public payloads with
VODFORGE_FILE_ACTION_FIXTURE_DIR, review them for private data, and update the
backend's file-action-producer-events.json fixture before running enrolled
storage tests. See telemetry-features for interpretation and denominators.
The native file-action suite remains separate; headless producer success cannot
certify dialog interaction or system file effects.


The Markdown report lists each scenario's declared evidence artifacts directly
under its functional result. Open native-evidence.json to find per-test files,
identity checks and source binding, then review the relevant captures and
assertions. Links are navigation, not evidence validation: a missing file stays
a missing file and a linked functional pass cannot close temporal/usability gaps.


Native window adapter checks must distinguish reusable function bindings from
window lifetime. tests/test_native_window_binding.py checks changing native peers,
zero-pointer teardown and failed-then-successful symbol lookup. Source tests do
not establish resize speed; run the native window/chrome and temporal scene cases
for current-window behavior, retaining their independent release and pixel gates.
No per-lookup usage telemetry is emitted; presentation observations retain their
existing meaning.


### Updating saved-folder observation fixtures

Run tests/test_archive_location_consent.py with VODFORGE_LOCATION_FIXTURE_DIR
pointing to a fresh evidence directory to export actual allowed producer payloads.
The test's production_telemetry_contract fixture enables release policy only with
its controlled offline transports; do not enable or send real analytics to qualify it.
Keep denied, late-granted, revoked/regranted and observer-failure cases in the run.

Import those exported cases into the backend location-producer-events fixture
and run the authenticated storage/readback/replay checks. Bind both checkouts'
identities and retain the before-fix failure. Inspect the stored operation query
and its denominator limits in telemetry-features.md. A fixture update, passing
functional test, or local database result does not qualify native interaction,
whole-family usability, exact packaging or deployed transport.


### Relink review input and consent checks

The Mac source-native suite enrolls tests/test_relink_consent_native.py. Its six
contexts cover allowed, denied, late-granted, revoked/regranted, unavailable and
failing observation. Verification submission is deliberately held pending; the
test uses the real review and return button. Each context retains before-press,
pressed and returned-view captures plus scope metadata in the native evidence index.

Preview isolation normally suppresses all analytics. This check restores the
production record method only on its temporary owner with both transports replaced
by controlled offline recorders. Never restore live transports for this fixture.
The allowed case emits producer-events.json for backend relink-cancel fixture
readback and replay. Retain source identities, prior failures and raw phase files.
A pressed-state assertion and three captures do not prove every intervening frame,
physical input, keyboard accessibility or whole-screen usability; review those
claims separately instead of inferring them from this functional pass.

### Relink navigation across the save boundary

The Mac profile also enrolls tests/test_relink_navigation_native.py. It runs
the real ArchiveWorkOwner, destination existence checks and atomic history writer
against temporary files. A controlled scheduling gate pauses immediately before
the commit call or after the durable save returns. Library, Watch and scoped
Escape each request cancellation while the result is pending. Assert callback
retention and visible review during that interval, then release the gate and
compare in-memory history with the loaded durable result. Cancellation before
save must preserve the original records; an already completed save must be
adopted. Verify the return label and subsequent navigation after settlement.

Run with the documented native process wrapper and a fresh
VODFORGE_NATIVE_EVIDENCE_DIR. Keep the before/during/after captures, scope receipts,
source identities and original failing run. Seed canonical startup records via
load_history before asserting exact equality: the generic scene seed contains
unsanitized legacy fields and omits the saved timestamp. Never remove the
durable-result assertion to accommodate fixture differences.

Input is direct invocation of the real navigation button or Tk-generated Escape,
not physical pointer/keyboard input. The media bytes establish existence only;
they are not a playback fixture. These checks do not qualify Windows, installed
artifacts, every intermediate rendered frame, or whole-screen usability. Review
the captured hierarchy, status clarity and control restraint separately.

Keep process stdout/stderr logs outside VODFORGE_NATIVE_EVIDENCE_DIR. The evidence
index detects later mutation: a shared process log grows after earlier cases and
is correctly flagged changed_after_test. Preserve old flags; do not relabel them
intact. Phase captures and per-case receipts belong inside the indexed directory.

### Relink worker admission and early cancellation

The Mac native profile includes tests/test_relink_admission_native.py. Close the
real worker after successful verification to test refusal; for queued cancellation,
hold a newly constructed real worker before its run loop, admit the update, and
cancel through the real Watch button or expire the existing poller's deadline.
Release the gate and assert actual settlement, unchanged on-disk bytes and
in-memory history, usable recovery text and no pending callback. Do not substitute
a fake completion result. Always release the gate in cleanup.

Each boundary runs six consent/observer contexts using the same temporary offline
owner isolation as the review consent fixture. Allowed cases export the actual
producer payloads; denied/retired/unavailable/failing contexts must emit none and
must leave the same authoritative UI/file results. Backend tests must ingest the
exports with authentication, compare stored fields, replay exact events and reject
added private path fields. Keep all native scope metadata: direct button invocation,
controlled worker scheduling and a forced timeout deadline are not physical input,
a genuinely slow filesystem, Windows or exact-package evidence.

### Settled reviews and late verification results

Continue the existing relink admission tests through the real Back to Library
button and capture the returned view. Require exactly one terminal outcome;
correct in-flight events followed by an invented cancellation on dismissal fail
the check. Review lifetime and operation lifetime are distinct.

The same native module holds a real verification worker for failure/timeout
tests across six consent/observer contexts. Expire the existing poller deadline,
release the worker, and verify that its retired result cannot revive status,
enable Update or change history. Assert settled headline and item labels before
return, then check the real offline event sequence after return. Preserve actual
before/during/settled/returned captures, failure receipts and producer exports.
This is bounded operation evidence, not whole-product usability approval.

### Refused verification must settle its review

Extend the existing relink admission fixture for a worker closed before verification
submission. Assert both headline and per-file rows leave the pending state, Update
remains disabled, history is unchanged and the actual Back control closes the review
without a second terminal observation. Exercise allowed, denied, late-granted,
regranted, unavailable and failing observers through the real offline telemetry owner.
An immediate refusal has no in-flight worker phase: label its during capture as the
synchronous outcome rather than claiming a pending interval. The prior implementation
fails all six refusal contexts. Source-native evidence and authenticated local backend
readback do not establish native-picker, physical-input, Windows or package acceptance.

### Settled captures cannot qualify ordinary presentation

The relink refusal review exposed a capture/acceptance gap. Widget-state assertions
passed while an immediate native view-cache image still showed the prior Library.
The capture helper now services events for 150 ms before settled-state snapshots;
this is observer intervention and must be disclosed. It proves neither natural
response latency nor absence of intermediate blank, mixed or stale frames.

Observe the ordinary mainloop separately with an independent own-window recorder.
Do not call update/update_idletasks, cacheDisplay or a capture-driven flush during
that interval. Preserve the raw sequence, monotonic action/acquisition times, source,
runtime and input mechanism; encode frames after observation where possible.
The bounded refusal probe showed blank content and then partial review rendering,
with its first sampled review-region match at about369ms. Its pytest success only
validated diagnostic collection; presentation acceptance failed. Preserve that
failure separately from the48functional/settled-state passes. A delayed screenshot
or a longer observer wait cannot clear it. Response and no-blank-frame gates need
ordinary-loop evidence against their existing criteria before promotion.

### Exact document sizing is separate from frame presentation

The enrolled test_relink_layout_native.py records actual Text height queries from
the production review while the ordinary mainloop runs. It compares queries at
the final wrap width against an exact native metric collected only after the
observation interval. One/25-item reviews at980/1440pixels all fail on cached
intermediate metrics. The expanded check also includes the5000-item supported
limit, verifies that measured lines are bounded by viewport height, and compares
the rendered clamp with a full exact reference obtained only after observation.
The initial all-document synchronous candidate took625ms at5000items and fails
the bounded-work check; that failure is retained. The bounded prefix refresh
must preserve both exact sizing and full scrollable text. No capture helper pumps or refreshes those measurements.
The production correction refreshes only the document's line metrics before
requesting its surface height; it does not process general idle/input events.
Keep this narrow sizing contract separate from the independent blank/partial-frame
failure. Faster or fewer layout steps alone cannot clear temporal UI acceptance.


### Relink review staging and return

The Mac native profile includes test_archive_overlay_reveal_native.py and
test_widget_reveal_native.py. The frame check records own-window Quartz pixels on
an independent thread while the application runs its ordinary main loop.
Preparation may settle fixtures; observation must not call update,
update_idletasks or cacheDisplay to repair the state under test. Images are
encoded after observation. Retain all frames, action timestamps, region results
and source identities, including failing negative-control frames.

Both relink and initial playback-loading entry/return must show a complete old or new view without blank,
unknown or mixed content regions. Entry and return faults must be detected independently. The sparse loading
screen also has measured label/button regions and a deliberately omitted loading
label; coarse whole-content regions alone can dilute that omission.
Lifecycle assertions separately check scoped input retirement, stale release,
cancellation, supersession, scoped Escape, button/canvas retirement, intentionally
hidden branches, destruction and Tcl callback ownership. Their setup
pumping is not evidence of natural frame presentation. The test records synthetic
production action invocation; it does not certify physical pointer behavior,
completed video playback, Windows, installed packaging or whole-view aesthetic parity.
Existing relink operation telemetry remains independently covered by its consent
and admission suites; frame evidence is not a fabricated product telemetry event.


The recorder targets 20 ms between capture starts and rejects measured gaps or
capture durations over 50 ms. This is a sampled observation bound, not display
refresh proof. A 35 ms target missed a return blank frame subsequently seen at
the faster cadence; preserve the older narrow pass alongside the later failure.
A capture-gap rejection is unavailable temporal evidence, not an application pass.
Raw acquisition files are written before these assertions. An unchanged viewport
is required; manual resizing invalidates this fixed-window presentation fixture.

### Deleted surface recovery and complete native runs

The surface-raster native suite deletes real Tcl images while their Python
wrappers remain cached. It covers ordinary and Retina images, reusable and
oversized frame-borrowed surfaces, rebuilding once, unrelated live-image reuse,
byte accounting and teardown. Preserve the four before-failing cases alongside
the repaired run. The presentation native test separately verifies the real
fault/recovered/settled operation in the local telemetry outbox, with private
content excluded. No new event schema or compositor-latency claim is implied.

Runtime-provenance diagnostic filenames must use bounded identifiers, such as
a hash of the full test node ID; retain the full node ID inside the receipt.
Parameterized content must not become an unbounded filesystem component. A
failed diagnostic hook can prevent a test body from running and is not a product
failure or a tested pass.

The complete source-native suite has a 1800-second process envelope. The previous
900-second run reached 440 completed calls and timed out during the resize suite,
leaving enrolled suites unexecuted. This outer bound permits the expanded suite
to finish; individual readiness, release, capture-cadence and resource assertions
are unchanged. Preserve timed-out incremental results and source manifests.
Neither increasing the process envelope nor fixing stale labels/layout fixtures
clears an interaction failure or qualifies an installed package.


### Negative controls must still produce their claimed fault

Disabling an optional drawing helper does not guarantee a visible defect on every
runtime or workload. The full native rerun exposed escaped scrolling and tab
controls; keep those failures. The scrolling fixture now blocks its first target
scroll callback for250ms before movement, records the actual interval and requires
the unchanged100ms response evaluator to fail. The capture/input threads remain
independent. Healthy short and sustained routes use the same recorder without
the injected delay.

The tab fixture leaves half the actual outgoing cover visible for160ms, then
retires it through the original transition owner. It requires sampled mixed
generations and clean later reference frames, preserving the50ms observation
limits. This is controlled visible corruption, not a claim that disabling a
particular helper always recreates it. Historical helper-disabled receipts retain
their original meaning.

When assembling isolated Tk candidates, record every included patch. A resize
candidate that omitted the earlier NSImage ownership correction grew by about
878MB after warmup and failed the maintained memory gate. Combining corrections
requires fresh memory, image lifetime/fidelity, input, resize and whole-suite
validation; separate passing experiments do not establish combined behavior.
The existing source ownership correction balances copied/allocated and borrowed
NSImage references. It does not change GIL handling, event dispatch or pool scope.
Keep the candidate isolated until all promotion requirements are satisfied.

Native action-label fixtures use button_metrics and named shared variants;
removed per-call height/font arguments must not remain in enrolled tests.
Preserve full labels and actual text-within-hit-area assertions when migrating
fixtures. Passing imports or headless tests cannot validate an unexecuted native
adapter call.


### Resize release boundaries

The resize observer reads button state before querying geometry. Include the first
observed released sample: filtering its sample start against its own button-read
end incorrectly discards that sample and can hide a final size change. Retain
posted-release stability separately from observed-button and native-end stability;
none substitutes for the others. Record AppKit start/resize/end notifications and
optional continuous own-window captures alongside input and render times. Capture
intervals are observation bounds, not compositor refresh timestamps. Deferred
layout, artwork changes and overlays need pixel review; settled images or geometry
alone cannot qualify them. VODFORGE_RESIZE_CAPTURE_PIXELS=1 enables diagnostic
20ms-target capture in the scene resize test; images are saved after input ends.
Capture-enabled and capture-disabled runs must remain distinct because observing
can perturb scheduling. No release latency allowance was introduced.

Use VODFORGE_RESIZE_CAPTURE_PIXELS=process for the separate-process recorder
(quality_harness.window_capture). It shares the window server but not the app GIL;
startup requires an observed baseline, stop/exit/errors are checked and raw PNGs
are saved after input. Both modes report actual capture duration and gaps. Their
pixel assessment remains diagnostic-only: missing samples cannot prove zero
unsampled changes. VODFORGE_RESIZE_SAMPLE_STACKS=1 additionally records a two-second
native stack sample; profile runs do not replace unprofiled comparisons. A local
NSEvent monitor was tested and removed: native resize tracking did not deliver all
gesture events through it, and a later cleanup-up event is not release delivery.


### Approved artwork fidelity

Branding checks must compare exported rich artwork with the approved source pixels,
not merely assert file presence or a recognizable silhouette. The rejected polygon
reconstruction is retained as failed work. tests/test_brand_assets.py asserts source
identity, exact crop RGB, transparency, icon sizes and manifest integrity. The native
suite enrolls test_brand_native.py to check real Tk pixels and compact/wide header
visibility. This catches loss of the compact mark when wordmark text hides. Site
preview and packaged/installed icon checks remain separate. See docs/branding.md
for the extraction and export workflow. Static branding introduces no telemetry
event; existing feature/download/consent telemetry must continue passing.

## Matte theme and material coverage

Run tests/test_matte_theme.py and engineering-quality/tests/test_theme_contract.py
for contrast, hue consistency, alpha geometry, bounded masks and negative controls
for import-time token capture/private raster face clones. The static audit is
scoped to known adapter families; it is not proof that every popup was exercised.

tests/test_matte_native.py is enrolled with source-native checks. It traverses all
six themes and four tabs, captures Settings and a production-control gallery,
checks stored preferences and appearance-change observations, verifies no motif
raster rebuild on configure, and perturbs a shared primary paint across native
ttk, poster and visible scene actions. The expected perturbation hue is evaluated
from actual pixels. macOS nsimage is not a Pillow PhotoImage: use an independent
window capture, not ImageTk.getimage, for that representation.

When adding a control, extend its existing family, add it to the shared-token
propagation probe and preserve instance callback/selection ownership. New primary
sites must pass existing metric propagation as well as material propagation.
Record default/hover/pressed/selected/focus/disabled and error recovery separately.
A stale theme at startup, in an already open popup, or in a later-created control
is a regression. Keep real media colored and assert it separately.

Run resize, scrolling, transition and memory checks after material changes.
A static cached decoration proves only its bounded allocation strategy; it does
not waive compositor timing or scrolling requirements. Preserve initial failing
runs and source binding. No source-native or palette result certifies Windows,
installed Dock icons, physical input, signed packages, or release eligibility.

### Full-composition matte review

Preserve rejected visual iterations alongside accepted evidence. The v39 strip
and hard-shadow captures are useful counterexamples; unit tests passing never
made them visual acceptance. Capture default and contrasting botanical themes
at native size, plus website desktop/mobile. Review whole composition, quiet
content zones, material direction, foreground contrast, readable metadata,
normal/hover/pressed/focus/disabled states and narrow-layout behavior.

The artwork contrast assertion uses rendered bitmap channel maxima as a
conservative background bound. Keep the constructor/shared-paint negative
controls and actual native pixel perturbation when updating owners. A static
material manifest does not establish interaction correctness. The native suite
also checks short-path versus long-path line positions through mapped Text
geometry, so an unconditional path-wrap regression is observable.

The enclosing Forge panel was rejected. Decorative frame underlays share one
cached texture and move only; do not substitute full-window Gaussian redraws
on every Configure. Rerun temporal, scroll, cache/memory and
player integration checks when material or container ownership changes. Keep
source bindings and pre-existing release defects; a new appearance pass cannot
waive them.


### Revised foreground and composition direction

The user reference separates matte surfaces from colored content. Material faces,
backgrounds and artwork remain monochrome per theme. Foreground roles action,
icon, selection, progress, success, warning and danger provide limited intentional
color; ordinary text remains neutral. Status also requires words or symbols.
Do not enforce one hue over every rendered pixel or recolor actual media. Shared
owners consume these roles; no screen-local palette copies.

Plain rectangular backing behind noninteractive labels, status and metadata is
not accepted. Frame underlays alone do not solve opaque leaf widgets. Acceptance
requires actual native captures across empty, active, completed and error states,
with resize/theme seam and stale-backing checks. Preserve native text selection
and accessibility. This documented requirement is not a claim that all adapters
currently meet it. Retain failed captures and distinguish the isolated qualified
Tk runtime from stock and packaged runtime results.


### Smooth etched stone material

The authoritative reference is a continuous smooth matte stone-like substrate.
Each theme chooses one material hue shared by the background, artwork, control
faces, cards and popups. Recesses are carved into that same material; raised
controls emerge gently from it. Geometry stays crisp and directional light and
ambient occlusion supply depth. Avoid separate plastic-looking plates and rough
granite wallpaper. Background artwork is a restrained tonal surface treatment.
Selective colored foreground glyphs and indicators read as inlays; ordinary text
remains neutral. Verify actual per-theme rendered scene/control hue relationships,
not token existence alone, plus full scene switches and the interaction gates.


### Native read-only text over scene artwork

MatteTextProjection in ui_materials owns presentation over existing read-only
Text and Label widgets. Their documents, variables, geometry, selection and
keyboard bindings remain native; a nonfocusable child canvas paints aligned
artwork and text using native font geometry. Pointer coordinates are forwarded
to the document, and variable/modification/theme/geometry invalidation is scoped
to the owner. Destruction retires pending paint, traces and bindings. It does not
enroll editable fields or change data/selection models. Forge and Activity use this shared adapter. Native viewport notifications keep
scrollbars, keyboard movement and see() synchronized; visible display-row bounds
avoid scanning hidden wide-line tails. Embedded document images and status labels
retain their native owners, and elided tokens remain selectable without being painted.
This is not complete app-wide adoption or accessibility qualification. Direct
NSAccessibility inspection of the isolated Tk content view exposed AXUnknown and
no children both before and after projection; external assistive-technology behavior
is still unproven.

The source-native regression uses an independent two-tone background to amplify
seams, inserts a real opaque rectangle as a negative control, and checks native
selection, resizes and teardown. A prior hide-overlay control failed to produce
a visible fault on the tested Tk runtime; that failed evidence is retained.
Add active/completed/error states, theme changes, long documents and keyboard/
accessibility/performance checks when extending this owner. Keep physical-pixel
captures and their backing-scale metadata alongside logical previews.


Controls must stand alone on the shared substrate. Audit residual wrapper fills,
rectangular raster halos, duplicate borders and idle highlights across all control
families, screens and popups. Preserve meaningful keyboard focus, shaped to the
control, and distinguish idle/hover/mouse-focus/keyboard-focus/pressed/disabled
and focus exit. Patterned backgrounds expose unwanted rectangular support; check
pixels outside the intentional shaped material/shadow, not only control centers.
No blanket translucent overlay substitutes for removing a redundant wrapper.


### Unintended surface and decoration detection

The canonical design rule is in docs/ui-components.md: standalone controls on one
continuous smooth material, with shaped depth and appropriate keyboard focus.
quality_harness.surface_artifacts compares actual captures with a separately
captured backdrop outside an explicit allowed material/shadow/text/focus region.
Define that region from reviewed design geometry before evaluating the image;
never enlarge it to contain a faulty output. Record its geometry, capture size,
state, source/runtime binding and tolerance with each consumer's evidence.

outside_allowed_surface reports unexpected pixel count and bounds. Its scope is
differences, not automatic attribution. clipped_shadow_edges applies only to RGBA
raised-control rasters whose free perimeter must reach zero alpha; flush surfaces
and media crops are explicit exclusions. stale_decoration requires matched
content, hover, selection and theme before focus and after focus exits, with proof
that focus actually entered and exited. Mask dynamic content explicitly.

Run engineering-quality/tests/test_surface_artifacts.py. Positive controls cover
legitimate shaped depth, soft shadows and allowed keyboard focus. Genuine negative
controls insert an opaque wrapper, clip an alpha edge and retain a visible focus
ring. Striped and tonal backdrops expose different failures. Keep negative-control
failures; passing this framework is not proof of all-family native coverage.

Each newly integrated control family must supply actual native capture pairs over
varied backgrounds for idle, hover, pressed, disabled, mouse/keyboard focus and
focus exit, plus popup close/open, theme changes and resize. Preserve callback,
selection, keyboard and accessibility behavior separately. The initial native
text projection check covers selection, seam amplification, resize and teardown;
it does not yet qualify every required state or platform. No pixel sameness rule
may forbid intentional shadows, depth, media or current keyboard focus.


### Projected documents must follow the native document

The short selection/resize projection test missed viewport-origin changes, clipped
wide lines, embedded status images and hidden tokens. The maintained
`test_matte_projection_native.py` now exercises vertical/horizontal scrollbar
commands, see(), all visible rows of a wide document, replacement/restoration of
existing viewport callbacks, and actual ActivityLogText image/label/token content.
The pre-repair viewport cases failed three times; the wide-row and embedded-image
cases each independently failed. Preserve those failures, not just final counts.

Viewport callbacks still belong to the native document and are chained rather
than dropped; destroying the presentation restores the current callback and
retires its Tcl commands. The row walk follows native visible geometry and skips
hidden tails. Source content remains unchanged. Native field focus must visibly
follow its rounded contour, preserve geometry/interior and restore idle; the old
ring-free expectation contradicted the current design and is superseded.

These checks use generated Tk input and settled own-view captures. They do not
qualify physical input, independent in-flight presentation, Windows, external
screen-reader behavior or packages. Run the related resource, scroll and
transition contracts after integrating the shared compositor.

### Windows shared-contract repair qualification (v41, 2026-09-19)

The preserved Windows NORMAL/native failures exposed assumptions that the Mac
baseline could not exercise: read-only fsync descriptors, platform-specific path
separators, optional Tk event availability, relative DASH muxer output, and huge
implicit pytest parameter IDs. The existing owners now require a write-capable
nontruncating history descriptor, canonical slash source/artifact keys, and an
interpreter capability query before registering TouchpadScroll. Ordinary wheel
behavior and callback retirement remain common contracts. No machine policy or
permission is changed to obtain a pass.

Fixture generation runs the DASH muxer inside its declared output directory and
checks the generated static timeline's nonempty resources before returning the
corpus, including cached manifests. A missing resource fails setup before provider
retries. Absolute and relative corpus roots, an independent relative-file writer,
real WebM decoding, and a removed segment exercise this output-ownership class.
The first decode test assumed an optional DASH demuxer unavailable in the Mac
FFmpeg build; that failure is retained. The corrected oracle resolves manifest
references and decodes the corresponding concatenated WebM bytes.

Eleven previously Darwin-only enrollments are common native contracts on both
platforms: foundation acceptance, Library file actions, relink consent/navigation/
admission/layout, widget reveal, button parity, inline description, player layout,
and startup update. Their shared capture service already has Mac and Windows
adapters. Enrollment is not execution or success. The sixteen remaining
Darwin-only modules (restraint, overlay reveal, platform trash, shared controls,
catalog scale, description readability, window chrome, branding, matte,
matte projection, scene/scroll in-flight, scroll idle, raster, memory, transition)
remain explicit Windows coverage gaps. Do not count these omissions as passes or
claim platform equivalence. The zero-skip native completion rule is unchanged.

Existing tests missed this class because fsync passed on POSIX read descriptors,
path keys were tested only with native POSIX paths, and fake Tk bindings accepted
all events. The native enrollment test itself asserted the incorrect Darwin-only
classification of common behavior. New tests check writable descriptor capability
without changing file content, Windows-style relative paths over the same bytes,
unsupported event fallback with no registered callback, and both platform
selection lists. The oversized corrupt-image input remains intact; only its
pytest ID is shortened. Native desktop, physical rendering, actual Windows,
package and installed-state evidence remain separate from local contracts.

The v41 real Windows follow-up uncovered a second authority defect after durable
flush became usable: Python 3.12.14 path-stat ctime reported file creation, while
fstat ctime reported mutation time for the same NTFS file. The independent native
FILE_BASIC_INFO probe agreed with the latter. Existing POSIX tests missed this
because both observations use the same timestamp semantics there. v42 uses the
existing platform-services boundary to obtain handle ChangeTime and the existing
file-operation owner to bind path observations to that same handle timestamp.
Device/inode, regular-file/single-link, reparse, size/mtime, and post-open path
rechecks remain required. Neither ctime removal nor birthtime substitution is an
acceptable repair. Real same-size, restored-mtime mutation and replacement tests
must reject stale authority. Unsupported native queries fail closed.

The first v41 SSH contract run also correctly refused ancestors under Julie's
Documents directory, which the standard SSH account cannot stat. Its explicitly
shared QA child directory does not authorize the parent. Preserve that failure;
use the executing account's own isolated test profile. Do not loosen application
ancestor checks or grant additional machine access for a test. Symlink privilege
and missing SSH Git remain separate environment gaps. The historical Windows
run, new source-native run, and any patched diagnostic must retain separate
source/runtime receipts; no passing subset is full Windows acceptance.

v43 qualification caught a mistake in the initial optional-event fix: Tk8.6 bind
lookup returns an empty result even for an unsupported event; it does not parse
it. A real unknown-event case fails the old probe on Mac as well as Windows.
The corrected service parses a literal Tcl script on a unique unattached tag,
creates no Python callback, and clears only that tag. A preexisting tag is refused
without replacement or cleanup. WidgetReveal uses the same service; it no longer
creates a Python callback before learning that TouchpadScroll is unsupported.
The old fake tests incorrectly modeled lookup as validation and have been corrected.
Actual native supported/unsupported and ownership/callback-retirement outcomes,
plus ordinary-wheel behavior, qualify the common input contract.

The targeted Windows native runner must keep its evidence directory separate
from run TEMP and application profiles. Run675aeced completed78passes/16call
failures/2setup+2teardown errors, then reporter hashing a locked temporary file
caused pytest internalexit3 (bridgeexit1). Retain that observerfailure and all
incremental cases. Do not suppress permission errors or count the partial suite
as passing; the next runner must point evidence at its own native subdirectory.

Hidden matte documents defer rendering until native Map/Expose and use current
native content on first reveal. The new hidden/remap case fails before the guard;
nine projection cases pass afterward. This does not repair the separate startup
250ms requirement: observed344ms still fails. Foreground-role tests independently
exposed six violations acrossJade/Ember selection,progress and combobox glyphs;
shared styles now delegate selection/progress/icon roles instead of material hue.
Material fills retain their theme colors, and original media is not recolored.


### Native owner organization and qualification

Native implementations now have named `platforms/macos` and `platforms/windows`
locations; the public platform-services API, shared UI/input intent, archive authority
and player/update policies remain shared. See the canonical architecture owner map.
Source manifests must include tracked missing paths during moves, preserve the bound
previous source before removal, and reject unexpected drift. Test imports, package
discovery, native binding and bounded diagnostic labels move with their owners.
Headless opposite-platform import checks must distinguish standard-library capability
probes from actual foreign native initialization. Actual native adapter outcomes are
still required separately on each OS; a source move cannot inherit installed proof.

Windows sharpness is an unresolved user-reported condition. Required diagnostic
evidence: resolution/scaling/effective DPI; process/thread/window awareness; Tk
version/scaling; physical window/client/capture sizes; raster backing sizes; and
identical shared controls/text/media fixtures at intended logical size on both OSes.
Capture only the owned test window and retain original unscaled pixels. Distinguish
phone-photo/screenshot resampling from product output. Do not clear this condition
from token/color tests or assume a monitor/platform cause.


### State-image lifetime and temporal reference coverage

The shared RoundedFieldBorder keeps the same Tcl image across focus, hover and
theme changes at unchanged dimensions; resize may replace its backing. Native
focus/hover/theme repeated-state tests require changed/restored pixels, stable
handle identity and retirement. Prior image replacement failed all three cases;
existing same-intent thumbnail tests missed this different-state/same-dimensions
instance. The original all-Tcl-command popover assertion remains unchanged.

A full-size canvas raster and a stretched ttk nine-slice backing have different
edge alpha recipes. Both require the same independent focus contour, stable face,
restoration and alpha support; focus must differ from idle. The former equality
assertion missed intentional accessible focus and confused backing with final
geometry. The reused contour oracle rejects missing, rectangular, stale and
equal-alpha color faults; physical density remains a separate qualification.

Continuous materials reduced the distinction between empty Activity/Forge
fixtures below the fixed four-region temporal oracle requirement. Retained
pre/post-extraction failures are unproven, not passes. Active Forge content with
decoded bundled artwork and realistic progress/logs restores representative
coverage without changing regions or thresholds; actual retained-half-outgoing
pixel faults still must be detected in both tested viewport sizes.


### Large tagged-document replacement

Relink keeps one native Text and submits each complete tagged replacement in one
interpreter call. Native Tk owns Unicode indices and tag ranges. Prior per-field
insertions made 25 records cross Python/Tcl hundreds of times; the Windows5000
review had requested564px but remained at its initial120px after the unchanged
1.2s observation. The existing bounded Text-measurement test correctly checked
metrics, but did not bound document insertion or prove geometry had settled on
Windows. Keep both timing/clamp and insertion/copy/tag checks. New representative
checks retain every selected path, all title ranges and first/last Unicode text;
record native insert duration and payload size so one large insert cannot hide
a moved stall. No event-loop pumping or deadline waiver is part of the fix.

Relink preview performance: the original metadata-only tests checked collision and authority outcomes but did not detect reparsing the same selected source during the collision pass. `test_preview_reuses_validated_sources_only_within_one_snapshot` counts actual parser-owner calls, verifies unresolved-source collision protection, and changes the saved directory before a new proposal to prove invalid-record rejection and no cross-proposal cache. Native layout evidence retains the 1.2-second ordinary mainloop and records open/fit/quit callback boundaries without scheduling extra event processing. The Windows v48 tagged-insertion optimization alone still failed the 5000-row geometry gate; retain that failure. cProfile observations add overhead and are not acceptance timings. The supported proposal limit remains 5000 records, with full tagged/copyable document contents; arbitrary-size responsiveness is not claimed.

Mac field density qualification: `test_field_density_native.py` is enrolled in the Mac source-native surface gate. It observes actual 2x native view captures at unchanged logical field dimensions, including styles installed before mapping, existing canvas and ttk field adapters, state/theme/resize/destruction, live image/command identity, and physical focus restoration. A transport-boundary oracle rejects an actual producer mutation returning a 1x bitmap, rather than accepting an `nsimage` label alone. Explicit 1x fallback backing tests retain their independent contour/alpha/RGB fault oracles; they force 1x to remain meaningful alongside native-density tests. Physical focus uses independently specified 10-logical-pixel radius, 5-pixel band allowance and 2-pixel antialias support at measured 2x; missing, rectangular and stale focus faults must fail. Earlier hard-mask failure (64 RGB1-3 corner antialias pixels) remains evidence, not a product defect claim. Prior coverage inspected only PhotoImage pixels at 1x and therefore missed native raster density and first-map scale selection. Source-native captures do not certify installed Tk, physical-input feel, cross-monitor transitions or Windows DPI rendering. Density-only and later tonal captures are separate so a shadow change cannot masquerade as sharper rasterization. Full existing native/packaged gates remain required independently.


### Actual Forge outcome identity and legal-media qualification

`tests/test_forge_activity_ui.py::test_legal_media_failure_retry_completion_and_skip_identity`
is enrolled through the existing native Forge module. It uses the maintained generated
local HTTP corpus and real yt-dlp/FFmpeg worker: injected HTTP 503 failure, visible Retry
button, a new linked execution, independently ffprobe-readable/full-decoded completed
output, and Skip during actual slow media transfer. It reads the existing durable
terminal store and verifies queue/staging cleanup and worker retirement. macOS own-widget
captures are a separate adapter; this is not physical input, external service telemetry,
Windows qualification from a Mac run, or packaged acceptance.

The earlier controlled worker source boundary fails before extractor item expansion,
so it did not cover execution-to-item terminal identity. A generic extractor can create
a child item with its own `run_id`; its `execution_run_id` binds it to the submitted
execution. Waiting on the parent job's mutable terminal field is not a valid Skip
oracle. The new test follows the durable relationship and retains the original Failed
record before Retry intentionally supersedes it. Historical external diagnostics
preserve the actual parent-object false failure, unsupported-quality fixture request,
and missing idle-settle assertion; none is evidence of a runtime defect. This extends
representative outcome coverage within existing owners, not a new diagnostic subsystem
or a claim about every provider/interleaving. The quality corpus must offer the requested
format, and UI remapping is observed after the ordinary event loop.


The existing actual MP4 provider journey now separately invokes the native floating
window button, verifies the topmost owned host and preserved paused provider, then
invokes Return and verifies host destruction/rehosting. Its floating capture is
bound to the overlay's exact native window ID and cross-checked against owned
on-screen windows. Fullscreen alone did not cover this floating-host lifecycle;
this addition is OS-injected source-native evidence, not physical PiP usability or
all-platform/package acceptance.
