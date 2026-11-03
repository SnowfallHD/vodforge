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

Distinguish physical input, OS-injected input, generated Qt events, programmatic
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

## Earlier qualification notes

Qualification notes, probes and escaped-defect examples written while the app had
its Tk interface (through October 2026) are in
[harness guide: Tk era](history/harness-guide-tk-era.md). Many name tests and
components that no longer exist; the evidence standard above still applies.
