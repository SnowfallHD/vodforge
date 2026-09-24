# VODForge engineering-quality harness

## Qt artwork and Forge visual ownership — 2026-09-24

The earlier Watch/Library source tests counted bounded artwork requests and
checked the projected owner, but did not require an image to appear after the
asynchronous artwork worker completed. A native Library/Watch inspection
therefore exposed blank cards even with a usable cached thumbnail. The
four-case rendered QML regression now resolves one local JPEG through the
real artwork owner in Watch/Library group and media routes and checks the
final image source. Watch media also reached a Library-only bridge gate; the
test failed with the image still empty after five artwork results were ready.
The bridge now admits the Watch route and the QML bindings depend on the
notified scene projection, so completion repaints the cards. This covers
representative local-cache paths; native packages and remote thumbnail
acquisition still need separate evidence.
An exact Mac `88f6700` package then showed that the source regression was
insufficient for a real profile: an artwork worker remained in an OS file
open while the visible Watch groups had valid private cached JPEGs. The
single queued artwork lane prevented those later jobs from finishing. The
existing `QtArtwork` adapter now exposes only the bounded app-owned stable
thumbnail cache path immediately, while its background owner remains
responsible for role-specific and acquired art. A blocked-lane test asserts
media, playlist and avatar requests all return their real cached image URL
before the first job can finish. The first package remains a failed visual
gate. The corrected exact `677aa6a` Mac package visibly renders the Watch
hero/group and Library collection images, and its welcome first/third slides
show the emblem rows and slider. The exact Genesis package passed a synthetic
cached-image pixel check in its interactive desktop: both red/green channel
images and both Library media images appear. These are focused visual gates;
the remaining package, installed, telemetry and release journeys are separate.

The Forge/Welcome scene test previously verified the slider object and emblem
URL but not the final arrangement. It now checks the Tk-derived Activity to
Source Details split, popup size, centered heading and exhibit order. The
rendered captures are in `build/qt-port-package/parity-*.png`. Mac/Genesis
package visuals remain a separate release gate.

## Qt consent and lifecycle ownership — 2026-09-23

The Qt presentation binds the existing analytics consent, product telemetry,
run-recovery, shared download worker, and local conversion owners. It must not
derive permission from a region timeout, create an outbox in a disabled build,
record a playback attempt after consent changes, or report a local conversion
complete before Library history is durable. The Qt adapter's old product
outbox path call used an unsupported `data_dir` argument; this would fail in
an enabled packaged build while disabled source smoke stayed green.

`test_qt_analytics_session.py` covers disabled policy, both opt-in and unknown
prompt modes, grant/revoke, existing consent with recovery reporting, exact
private state paths, and failed consent writes. The worker-owner and local
conversion cases cover actual queue/terminal event order, URL-free dimensions,
and completion only after Library commit. Existing consent/telemetry owner
tests remain authoritative for outbox delivery and revocation. These are
representative cross-owner handoffs; source-native tests cannot prove the
packaged preview-D1 journey, installed platform UI, or production policy.

The Qt Library action test also removes a projected saved row after its owner
was captured: Play refuses to bind it to another history index, and Copy path
does not substitute another file. The Qt queue test verifies the removed run
is absent from durable recovery and never starts after the active run ends.
The Stop/Skip test checks the actual shared-worker flags and child interruption
handoff. It does not substitute for packaged mid-download cancellation and
Skip results on both platforms.

## Full-cover shared artwork during resize — 2026-09-22

`MatteBackdrop` owns one display-sized motif image per window and theme. The
image is shared by scene underlays and projected labels, and normal resize
events only move the image; they do not resample it. The old 1200×800 image
left a 150 px uncovered strip in a 1350 px Mac window. The expanded-window
native case failed before the repair and now checks coverage across three
sizes, unchanged image identity, and the final captured surface. The same
coverage case is required on Mac and Windows through
`test_matte_projection_resize_native.py`. This is a structural and rendered
native check; the held-pointer test below remains a separate release blocker.

## Windows live-resize paint gate — 2026-09-22

`test_windows_resize_inflight_native.py` is required by the Windows
`native_surface_contract`. It runs the real Forge window in an interactive
session, injects two OS window-edge drags, and samples a fixed, verified
interior crop of its owned HWND from a separate process every 50 ms. A sample
is discarded if native bounds change during the grab; foreign top-level
overlap is checked before and after it. The static fixture fails when an interior frame
is still more than 2% different from the end of the same-size interval after
200 ms. Both drags must change native window width by at least 80 px, and at
least four distinct window sizes must be captured. Empty or missing transition
evidence fails. The pure oracle test has a
synthetic delayed-control negative control; a normal static sequence passes.

This gate was added because the earlier Windows probe recorded geometry and
callback gaps, but no rendered frames. On `desktop-genesis`, the pre-change
Forge held one window size for up to 1.9 seconds while the composer, labels,
buttons and Run Deck repainted in stages. A plain Tk baseline followed the
same drag without the long holds. Restricting the existing shared matte
projection to redraw text on actual widget/content changes improved callback
gaps and geometry cadence, but the exact Windows native gate still fails. The
`4427088` source-native Genesis run had two admitted native drags (315 and
327 px), a maximum overlapping timer gap of 98.8 ms, and a same-bounds
Forge epoch still 5.4% different after 403 ms. Root Configure was delivered
before that epoch, but the old breakpoint layout remained visible. Narrowing
the existing layout owner to visible-view and changed-placement work made the
pixel gate pass twice at `d0e1412`, with 111.4 ms maximum UI timer gap on the
first run. The separate pointer/edge gate below still fails.
The resize remains a **release blocker**; sampled HWND frames are server-side window
pixels, not physical display refresh or packaged-app proof. Do not claim the
resize is fixed from a settled screenshot, an empty capture, or the improved
timing alone.

The diagnostic recorder saves only a fixed interior of the attested VODForge
HWND. An earlier moving desktop crop could include pixels outside the window;
those frames were removed. An earlier recorder also associated pixels with
bounds read before a 60–70 ms grab, even if the window resized during it.
`test_window_capture.py` now rejects that mixed-size case. Win32 descendant
compositing was tested in an isolated QA candidate; it failed both pixel and
timer gates and was removed. Keep physical display and packaged validation
separate after the source-native gate passes.

### Held pointer must track the native edge

The paint gate cannot detect a window that moves in large jumps while its
controls remain together. `assess_pointer_tracking` now pairs independent
held-pointer and native-frame observations during two real OS drags. Each drag
needs at least 30 sound samples and 80 px of both pointer and edge travel; its
95th-percentile edge lag and largest pointer travel while the edge is stationary
must each stay within 24 px. Samples whose pointer/frame query spans more than
20 ms are excluded. Synthetic smooth and jump cases and actual plain-Tk
baselines establish the oracle: Genesis baseline p95 4 px and Mac baseline
p95 3 px. A failed or unobserved drag cannot pass.

The exact `d0e1412` Forge source still fails: Genesis corner-drag p95 lag was
67/66 px, with 78/70 px stationary-edge pointer travel; Mac right-edge p95
lag was 90/87 px with 47/49 px stationary-edge travel. A clean `e31d6e1`
Genesis right-edge run without pixel capture still failed at 44/47 px p95,
versus the 4 px plain-Tk baseline. Mac Library without records also lagged
40/43 px. Windows runs separate required pixel and right-edge pointer tests;
`test_macos_resize_pointer_native.py` is required by the Mac
`native_surface_contract`. No packaging or release promotion can use
the paint-only pass to clear this live-drag defect. The next fix must reduce
the frame motion lag without bypassing either shared rendering or native edge
authority.

## Header action material ownership — 2026-09-22

Invariant: a visible navigation action must receive one complete shared stone
face at its final size, with its icon and label on that face. Resting is raised;
hover and selection are recessed. The Forge composer remains the shared recessed
field with a continuous face behind its children. The prior header routed a
nonstretchable full button image through ttk's nine-slice layout, so ttk could
repeat fragments and produce seams. A later style application could also replace
the material layout. Style-name and producer-image checks missed the consumer's
actual image, label, and screen pixels.

The header now uses the existing canvas action adapter and renders
`action_button_image` at the allocated control size. The shared button metrics
provide its height and content allowance; its label, icon, and surface are
owned by that one control. `test_shared_header_action_native.py` is required
by `native_surface_contract` on Mac and Windows. It checks owner, item count,
full-size image, icon/label, idle/hover/selected pixels, compact width, theme
reapplication, and a producer mutation that the selected-depth oracle rejects.
`test_matte_native.py` also checks the composer and a separate scene navigation
consumer with a flattened producer. The Library inline-copy test now observes
the scene owner's actual image replacement on hover and press; its old
`pointer-state` border oracle described a retired rendering path. These are
representative cross-owner checks, not proof of every control or Windows packaged rendering. Native source
passes still require exact packaged visual and interaction qualification.

The Mac player overlay keeps its static lower control gradient and keyboard
focus stroke. `test_player_control_hover_keeps_static_gradient_without_filled_state`
exercises the AppKit drawing owner for hover, press, and keyboard focus; a
transient filled path fails it. Native playback and packaged video compositing
remain separate acceptance gates.

## Material states and first-map geometry — v139

Invariant: each enabled hover role must change rendered material, and every
projected backdrop/scroll body must match actual settled geometry on first map,
ancestor movement, and remap. Mac Done exposed a default ttk role omitted from
recessed shading; previous scene-renderer and color-role tests did not execute
that owner. `test_ttk_owner_renders_raised_to_recessed_hover` failed before the
one-role fix; actual Settings Enter/Leave raster tests reproduce and verify the
response plus secondary action and own-popup192. Raised resting is preserved.

Windows packaged evidence exposed correct Canvas item width but stale actual
child allocation, plus an unchanged-size matte canvas moved by an ancestor.
Previous Settings bounds tests resized before checking, masking first-map failure.
`test_native_initial_geometry.py` checks first-open before any resize, ancestor
movement/remap/retirement, and deliberate allocation/projection mutations. Fixes
extend existing owners; no independent geometry or rendering subsystem. Bounded
coverage is default and injected192 locally plus targeted actual Windows192;
fractional/mixed-monitor and full package release qualification remain separate.

## Constrained high-density Welcome — v142

Invariant: scale fonts and their containing layout together, and keep complete
actions reachable without shrinking text. The enabled Welcome entry shared a
frame carousel with disabled automatic showcases, but its fixed590x560 shell and
135px caption did not scale with inherited buttons. Earlier carousel tests covered
only default units. New enabled-entry tests independently measure fonts and every
visible action's requested width over all six slides, default/192, minimum/wide/
return; rendered review caught a clipped Skip label missed by rectangle containment.
Native text requests now drive footer reflow. The existing scroll surface handles
constrained high-density content, including caption reach and descendant wheel
routing; default centering and explicit Try it dismissal remain checked. No new
onboarding behavior or automatic invocation. Physical Windows192 is separate from
local injected metrics, and neither proves fractional/mixed-monitor qualification.

## Start here

Use the [harness operating and maintenance guide](HARNESS_GUIDE.md) for how the
harness works, how to run and extend checks, and the required before/during/after
evidence standard across every behavioral domain, including restrained controls,
clear task flow, and explicit usability review throughout UI interactions. It also identifies current
enforcement gaps: existing passing reports must not be mistaken for complete
interaction coverage. [Release gates](RELEASE_GATE.md) define artifact promotion.


Encoder quality, size and speed calibration lives in the companion
[fine-tuning harness](../fine-tuning/README.md). Its measurements select settings;
this harness verifies production behavior. Set `VODFORGE_NVENC_TESTS=1` on a
supported NVIDIA Windows host to include the real preset worker GPU tests.
A skipped GPU test is not hardware verification.

## DPI caller overrides and fitted artwork — 2026-09-20

Canonical dimensions must convert once at the actual window owner; measured child
requests must remain measured. Primitive-only DPI tests missed Forge and Output
Details callers overriding scaled font defaults and width, run-deck capacity
using physical width with canonical tile size, and PRO artwork fixed at20 pixels.
New root default/192 checks cover the actual820 minimum, narrow/wide/return, URL
usable allocation, destination/action reachability, capacity and empty copy.
Output Details covers its own popup units independently of root, lossless scroll,
section tags and protected Done. PRO tests require window height and native backing.
All have retained prior failures. Root brand/icon and Library field/sidebar/card
checks provide representative cross-owner coverage, not every consumer/platform.

Media image logical bounds must preserve aspect when physical backing is larger.
Square/landscape/portrait matrices caught a native-adapter intermediate stretching
fitted pixels into the full slot. Native real portrait and brand-placeholder cases
now verify fitted and full-slot dimensions independently. Existing image ownership
and renderer are reused. Actual Windows v136 card/menu/search/Forge proof is separate
from local injected DPI and from outstanding packaged Dock/taskbar qualification.

## Native list focus is distinct from selection — 2026-09-19

Three current readonly list consumers (Library locations, folder ancestry and
player ChapterList) had selected-only style maps. Actual keyboard focus moved
and OS Down selected the next row, but focused/unfocused RGB captures were
identical. Existing chapter selection tests asserted values and selection only;
they could not detect missing focus presentation. Settings contains no Treeview;
that earlier inventory label was incorrect.

The existing ui_styles owner now shares focused-selected accent-dark/on-accent
and unfocused-selected accent-surface/text maps across these three styles. No
list implementation, keyboard behavior or data owner changed. New maintained
shared-controls cases measure the selected-row RGB region with true focus states,
OS Down, readonly OS typing, and focus-withheld/restoration negative. All three
fail before the style change. Existing segmented-control and player-volume focus
cases provide representative cross-owner coverage of the invariant: selection
or a stored value is not keyboard focus, and losing focus restores presentation
without changing content. Results are source-bound in the worker handoff. One
current theme is qualified, not all themes/platforms/physical input or external AX.

## Reveal readiness excludes intentionally undisplayed content — 2026-09-19

Default Library missing-media dismissal exposed an indefinite restore cover:
`WidgetReveal._managed` treated an offscreen canvas Entry and its placed hint
as required mapped descendants. The logical overlay retired, but the visible
error frame remained and intercepted a fresh intended click. Readiness must
wait for required visible work, never for work excluded by the current viewport.
The existing shared reveal owner now recognizes hidden/offscreen canvas windows
and hints placed relative to them. Visible children retain geometry checks;
owner-supplied readiness, cancellation and lifetime guards remain unchanged.

`test_default_library_missing_media_dismissal_does_not_activate_underlying_item`
uses the default Library fixture (not the legacy folder autouse fixture), two
isolated subjects, OS Play/Back input, observed new playback intents, durable
history/queue comparisons and fresh intended second-subject input. Initial
fixture registration, offscreen driver target and duplicate accepted-operation
counting errors are retained separately from the confirmed surviving-cover
failure under `mac-resume-v60`. The prior generic reveal test excluded only an
unmanaged Frame: it missed canvas-managed yet intentionally unmapped content.
Three added shared-owner cases cover offscreen windows, hidden window items and
placed hints; all fail with the prior implementation. Each also keeps a genuinely
visible one-pixel control unready, then verifies completion after usable geometry.
Existing reveal lifecycle cases cover cancel, destroy, replacement, Escape and
stale callbacks. Representative composed consumers are playback and relink
entry/return; cross-owner latest-intent/settings and telemetry-revocation matrices
remain separate safeguards for excluding retired work from active progress.
Executed source-bound outcomes are recorded in the worker handoff; this is bounded
representative coverage, not every visibility/interleaving or packaged proof.

## Viewport work must preserve reachability without rendering invisible rows — 2026-09-19

The full-app native resize profile exposed home Recent Downloads rebuilding
four offscreen cards at y669 on every changed Configure. Catalog and Watch
virtualization already bounded visible rows, but home used a fixed one-page
loop; existing count/paging tests did not compare that page with the viewport.
The same Library catalog row, scroll-notification and anchor owner now handles
the bounded home recent row with zero overscan. A wholly offscreen row has no
rendered card or hit target, while its full extent and matching count remain.
Scrolling admits the canonical row; its context identities and Details action
remain current. No visible layout is deferred and no redraw debounce is added.

The actual home regression fails before the fix and passes afterward across
three widths, scroll admission and Details. Shared row-window tests cover both
boundaries and retain ordinary catalog overscan/removed-tail behavior; existing
Library/Watch pixel/aspect fault cases provide representative cross-owner proof.
The native before failure is resize-home-v107-before. Current exact-source
results remain in continuity. This fixes excess invisible work; it does not
establish fluid native-frame tracking or waive the original resize gate.

A native-backed large-background experiment improved frame cadence but failed
bounded theme-replacement RSS checks, including the real mainloop. RGB/RGBA
and explicit cache-policy controls did not resolve it. Both runtime experiments
were removed; the original PhotoImage background passes the same memory bound.
Keep this failure visible before expanding native-image adoption to large
textures. Small-surface/native lifetime checks had not covered that workload.

## Native drag observations must retain crossing intervals — 2026-09-19

The v104 full-app/baseline native drag comparison exposed a diagnostic omission:
heartbeat gaps were included only when both callbacks fell inside the gesture.
A timer deferred until after mouse-up therefore disappeared from the summary.
Original app/baseline traces show overlapping gaps of3107.51/2967.36ms; legacy
contained-only summaries reported about17ms. Neither metric measures native
frame tracking; independent cursor/frame observations remain separate.

The invariant is that an observation spanning an interaction boundary must not
be discarded precisely because the event loop was unavailable. The existing
resize_observations owner now selects overlapping callback intervals without
double-counting a gap spanning multiple gestures. Tests vary down/up crossings,
whole-gesture stalls, ordinary interior samples, unrelated callbacks and no
intervals, alongside the existing first-released-geometry checks:9pass. The
prior contained predicate drops all3crossing examples; the corrected predicate
retains them. Evidence is resize-frame-v104-heartbeat-{reconciliation,mutation}.json.
Existing release-geometry tests inspected spatial samples only and never tested
timer interval selection. Original receipts and legacy metric fields are retained;
the runner adds explicitly labeled overlapping statistics. This is a diagnostic
repair, not a performance fix, new latency threshold or release-gate promotion.

## When and how to strengthen the harness

Every confirmed product bug is an input to harness improvement, whether discovered
by a user, telemetry, support, development, or a release run. Do this as part of the
same fix, before describing that work as complete. A specific regression test and
a harness improvement serve different purposes; one is not a substitute for the other.

1. Preserve the concrete reproducer and add a regression for the reported failure.
2. Identify the invariant that failed, independently of the affected screen or tool.
   Examples: accepted intent survives delayed readiness; only the current owner may
   commit a result; failed effects never report success; retries preserve identity;
   cancellation/consent withdrawal stops future effects; teardown cannot deadlock.
3. Review where that same invariant applies across existing subsystems. Select a
   bounded, risk-based set of representative owners rather than auditing the whole
   application. For lifecycle/sequencing bugs, consider player/provider readiness,
   settings persistence, queued work, telemetry transport, updater handoff, and
   asynchronous UI results—not just another control in the original screen.
4. Extend existing scenarios with meaningful variations: ordering, delayed readiness,
   failed-then-successful effects, repeated commands, owner replacement, stale/late
   callbacks, shutdown, restart, and permission changes. Choose only variations that
   apply to the owner's contract. Do not invent behavior for an unsupported operation.
5. Assert independent observable outcomes: provider state, durable files, identity,
   delivery receipts, or absence of external effects. A displayed value or successful
   method return alone is insufficient. Exercise production owners with controlled
   faults; avoid testing only a parallel toy implementation.
6. Verify the exact regression fails before the fix when feasible. Demonstrate that
   the generalized checks detect the broken invariant using the prior implementation
   or a bounded fault/mutation, then pass with the fix. Record any unexecuted tier.
7. In the fix's evidence/continuity record, identify the root cause, invariant, affected
   owners, added or reused scenarios, variations, executed results, and remaining
   coverage limits. If existing harness coverage already exercises the class, name
   that coverage and explain why it missed this instance; update its fixture, gate,
   or execution requirements as appropriate. Never say “covered” solely because a
   new regression lives under pytest.

Apply this process when a bug exposes a coverage gap, a new lifecycle/provider
boundary is introduced, or a supported behavior changes. Preserve the bounded
review budget: extend the relevant class, do not automatically rerun every E2E
journey or build a generalized runtime framework. Final publication still follows
its existing exact-artifact release requirements. Previously passed evidence does
not prove newly changed behavior.

Current cross-owner sequencing coverage is in
`tests/test_cross_owner_lifecycle.py` and `tests/test_playback_control_lifecycle.py`
(relative to this directory). The required repository suite runs these through
`pytest_harness`. They vary debounce/write failures, delivery retries/withdrawal,
readiness delays, replacement/replay, latest intent, and callback lock ordering.
The packaged playback probe additionally verifies actual provider volume after
pre-play changes and file switches. These are representative checks, not a claim
that every subsystem or possible interleaving is covered.


## Original reuse must share the fresh preservation contract (2026-09-16)

The independent persisted-first H audit found two same-intent Original commits,
with a directory count increasing from one to two. Independent artifact probes
confirmed two identical, fully decodable M4A files. H is immutable evidence of
the bug, not a successful Original reuse run. The first driver only asserted
successful export outcomes, so it missed the duplicate despite recording it.

Reuse omitted the source-preservation plan required by Original validation.
Its shared AudioExportPlan matcher also assumed MP3 codec, CBR targets, and MP3
metadata controls. Fresh Original validation followed a separate preservation
branch and passed. Four AAC/Opus regression cases fail on the prior source:
see original-reuse-before.log under build/variant-help-20260916.

The invariant is that a valid artifact accepted at commit must remain eligible
under the same source-preservation intent, while changed codec/container,
sample rate, channels, unexpected video, truncated duration, or corrupt media
must still fail closed. Fresh and reused Original audio now share the same
preservation matcher. Advertised source bitrate is not a CBR encode target;
Original source metadata is not an MP3 metadata toggle. Reuse receives the
actual plan. Tests vary AAC and Opus across both owners and isolate diagnostic
callback failure from candidate validation.

The existing reliability.duplicate_artifact_transitions gate now generates
audio-only AAC HLS and Opus DASH fixtures, uses actual yt-dlp/FFmpeg/probing,
persists and reloads real history, then repeats and repairs a missing sidecar.
It asserts an explicit reuse receipt, no media download progress, unchanged
physical namespace and hashes, readable outputs, restored metadata, and cleanup.
The expanded gate passed all 14 actual jobs, including MP4/MP3 variant/retry
checks and six Original jobs. The producer follow-up must additionally assert
persisted reused_count and unchanged media files, not just success_count.

Miss observations now report the last bounded candidate rejection category
with privacy-safe validation provenance where available, or explicitly report
no eligible candidate / unavailable probe. This is not a reconstruction of
every rejected file or a guaranteed root cause. Existing coverage missed the
class because it tested fresh Original preservation and MP3/MP4 reuse separately;
it had no real audio-only source feeding Original fresh -> history -> reuse.
No existing duplicate user files are deleted. Source/harness and preview
evidence do not certify new signed packages or native resize smoothness.

## Observed output facts must survive later projections (2026-09-16)

The independent MP3 producer/D1 audit found that requested settings and a variant
label did not establish the actual output properties or physical separation.
A second regression exposed a sequencing error: validated bytes were physically
committed, then a metadata projection failure prevented the commit observation.
The pre-fix test in build/variant-help-20260916/download-postcommit-observation-before.log
fails with an existing destination file and zero committed observations.

The invariant is that a durable effect is observed at its boundary, independently
of later presentation/history work, and optional observations never own media
success. Download fresh commits and validated reuse now project only the existing
successful ffprobe facts. Local conversion sends its actual committed path and
validation probe through its existing local event queue. Observation failures are
isolated; consent is checked before adding filesystem work and again by the
telemetry owner before recording. No new probe, timer, subsystem, or fallback to
requested settings was added.

tests/test_output_observations.py varies MP4, MP3, and Original containers;
fresh commit and reuse before a metadata fault; local conversion; absent,
multiple, malformed and out-of-range probe values; identical bytes in distinct
directories; shared directory and hardlink identity; same-intent reuse; missing
or unreadable peers; symlinks; malformed history; and independent scan caps.
It checks physical files, field absence, privacy, and continued commit recording
when enrichment fails. tests/test_local_audio_video.py also proves a broken
commit observer cannot prevent history metadata or cleanup. Backend integration
persists the new facts in D1, rejects private/unbounded fields, and retains
cross-language vocabulary parity.

Bounded in-memory mutations detected both removed physical identity comparison
(two failing collision cases) and falsely substituted bitrate (four failing
fresh/local observation cases). See observations-mutations.json and its logs.
These mutations do not change repository source. The original sequencing case
and the generalized variants pass with the fix. Earlier coverage asserted
requested intent, folder names, and aggregate commit/reuse counts; it did not
compare persisted outcome properties or insert a fault between commit and
metadata projection.

Scope is deliberately limited. Stream bitrate is the probe-reported value
rounded to kbps, not an instantaneous VBR claim. Directory counts cover recognized
regular media files in a shallow scan of at most 128 entries, not a universal
principal-artifact count. Physical comparisons cover at most 32 comparable
retained peers within 5,000 history rows. Missing, capped, unreadable, unknown,
multiple, and no-comparable states remain explicit. A distinct result is a
point-in-time observation, not race exclusion or proof that no overwrite occurred.
Source fixture tests and local D1 checks do not replace the fresh preview
producer packet, native GUI checks, or exact signed-package acceptance.

## Forge geometry must not replay data projection (2026-09-16)

The native unprofiled Forge5000 comparison still had a491ms maximum heartbeat
gap after the earlier selected-view fix (baseline760ms). Forge rebuilt persisted
run history both for its header and for capacity changes. The renderer's existing
snapshot no-op check came after that expensive work. Geometry now reuses its last
data projection and summary; ordinary data/progress refreshes replace it, and
forced view entry reacquires current history. Only four display candidates plus full-history summary/count are retained.
No list-identity invalidation, additional polling timer, or new data owner is introduced.

The broader invariant is that presentation-only changes must not replay data work,
while actual state transitions must remain authoritative. The25/5000record
state-authority regression failed before the fix: one initial render plus three
capacity changes made four projections. It now makes one. The same production
renderer checks queue promotion, active57percent progress, completion, and removal,
including mutation of the same list/record. Existing Library phase reconciliation,
padding burst/latest intent and RunDeck active progress tests provide the bounded
cross-owner comparisons; all132state-authority tests pass. Earlier renderer tests
asserted widget rebuild counts, so they missed work before the no-op decision.

The required native surface suite now varies empty/25/5000history, real root/deck
geometry, hidden-history mutation, re-entry, and removal-to-empty; it asserts
visible tile text, mapped geometry and capacity. Windows source-native execution passed all seven focused cases. Unprofiled
measurement on sourcef7 recorded5000row max100ms versus7c948ms;25rows108ms,
empty43ms. All four runs subsequently hit the existing thumbnail destruction
callback fault, so these are pre-shutdown measurements, not clean completion.
Full raw geometry/gap/CPU traces remain in build/variant-help-20260916/native-forge-f7af1a8.
CPU remained high (large9.875s before versus10.56s after per12s drag). Programmatic Tk geometry,
headless owner tests, source native drags and exact-package acceptance remain
separate evidence; no CPU-efficiency or Chrome-equivalence claim follows from
projection counts. Active job event frequency and very large-history projection
on actual model changes remain outside this geometry-only optimization.


### Thumbnail teardown and measurement lifetime

The native resize runs exposed a Configure callback accessing an already-destroyed
sibling thumbnail label. Python widget existence did not imply a live Tcl command.
The production thumbnail owner now rejects a closing application or missing Tcl
surfaces before image work. The prior source owner fails both closing and removed
sibling variations with TclError; current source passes. The required native test
removes the sibling, generates the bound Configure event, and exercises the normal
application close protocol, checking no callback errors and actual window exit.

The broader closed-owner invariant already appears in choice popover anchor
destruction and delayed player/telemetry callbacks. Those tests did not cover
Configure delivery during recursive sibling destruction. New coverage extends
that concrete lifecycle boundary without changing the renderer or shutdown owner.
Separately, the probe's error callback recursively called destroy and amplified
the product error into an access violation. It now exits the loop without recursive
destruction; normal completion uses the application's existing close authority,
and the final receipt is written after shutdown with all late callback errors.
An intermediate measurement file is explicitly not a clean-completion receipt.
Fresh native execution of the new guard/probe is pending; no old receipt is relabeled.

### Thumbnail render admission during resize

Background-only programmatic profiling on f041 isolated repeated thumbnail image
work during Library resize. The mapped thumbnail wrapper emitted Configure for
position changes while its render inputs stayed identical. The existing owner
rebuilt both the Library and active-job images anyway. Two reversed-order
experiments skipped 206 identical render requests per run: Library request
lateness p95 fell from 259/262 ms to 9.30/8.85 ms and heartbeat p95 from about
52 ms to 25 ms. All 360 requested geometries were observed without mismatch.
These are controlled source experiments, not OS-drag or presented-paint proof.
Total CPU stayed near one core; the common Tk layout/native drawing cost and
Windows drag qualification remain open. Root Configure filtering and rounded
button image reuse did not resolve that CPU cost and were not landed.

The production thumbnail owner now retains only its last committed input/output
snapshot. It checks source object identity, target dimensions, placeholder mode,
source paths, palette, actual label bindings, and live Tcl image resources before
reusing pixels. Source references prevent object-id reuse; failed renders never
advance the snapshot. New source content at the same path, palette/size changes,
cleared labels, and retired native handles still require new images. It neither
defers real changes nor freezes the display during resize.

The broader invariant is that presentation events must not replay expensive work
when the semantic state and committed effect still agree. The existing Run Deck
projection/capacity checks in test_state_authority and the SegmentedSelector
snapshot behavior are representative comparisons. They missed the thumbnail
owner's unconditional rasterization before any no-op decision. The new required
test_native_thumbnail_rendering module extends that boundary with real Tk image
identity and pixel checks, mapped Configure delivery, independent active/Library
source replacement, same-path replacement, geometry/palette changes, failed then
successful rendering, cleared labels, retired resources, and normal application
shutdown. Its generalized same-intent matrix also exercises SegmentedSelector.
Eight of thirteen cases fail on the prior thumbnail owner. The focused checks
also verify externally changed label text before admitting render reuse. The native gate explicitly enrolls the module, so headless skips cannot hide
it. Existing teardown and Run Deck state-authority checks remain in the gate.

The string-image lifecycle case uses real Tcl photo resources through the
production native-image ownership/deletion path; it does not qualify the AppKit
decoder. Source images are refreshed through the existing source owner, not a new
filesystem watcher. Very large image decoding, all timing interleavings, exact
signed packages, foreground native drag, and Chrome parity remain outside this
bounded proof. Early profiling observer overhead, a test fixture that initially
did not pump asynchronous shutdown, and a hidden-wrapper fixture were preserved
as invalid evidence and corrected before the fail-before run.

## Native control lifecycle gate

`unit_static.native_surface_contract` runs the opt-in source-native control suite
with a real Tk display. NORMAL/DEEP release evaluation requires this scenario.
Missing, empty, skipped, or failing native evidence is not a pass. Coverage includes
outside clicks (including targets that stop event propagation), Escape, owner/anchor
unmapping, window focus transfer, repeated cleanup, field chrome coverage and
Canvas/ttk field-image parity. These checks complement, not replace, packaged
Mac/Windows interaction evidence and actual cross-application switching.

The runner supplies the intended source and harness roots to its child process,
ahead of inherited Python search paths. The native report plugin records actual
imported production/harness module paths, executable, arguments and working
directory in native-imports.json and rejects imports outside those roots before
tests run. Run from an unrelated directory or an inherited Python path must not
silently select a different checkout. Bound freeze executions also retain source
manifests before and after validation; an import receipt alone is not a source hash.

Each setup, call and teardown result is written immediately to
native-results.jsonl, preserving failures even if a later case times out.
The final native XML and process result remain the completion gate. Partial logs,
split focused reruns and an interrupted process cannot substitute for a clean,
uninterrupted combined execution and teardown. Keep OS-injected and physical
input claims separate. Only one native GUI owner may run on a host at a time.

The earlier choice-control audit excluded `tk.Menu` command/context menus and
checked selection rather than dismissal lifetime. Native command menus remain
intentional separate controls, not migrated choice fields. Do not describe that
inventory as all menus. Standard fields share `ui_chrome.field_border_image`;
adapters retain native editing/layout mechanics, not separate border designs.

This directory is an isolated adversarial test system for answering a bounded question with receipts:

> Is VODForge actually well engineered, performant, reliable, secure, and maintainable under the scenarios we executed?

The harness is intentionally not another downloader. Its high-volume integration layer constructs a real production `DownloadJob` and calls the shared `DownloadWorkerCore._download_worker_single` owner without constructing Tk. From that point onward VODForge performs its own yt-dlp preflight/download, export planning, `.vfstage` ownership, FFmpeg post-processing/transcode, ffprobe validation, atomic final commit, metadata/thumbnail sidecars, and worker events. Tk and Qt consume this same worker owner.

## Evidence tiers

Every scenario has one of three non-interchangeable evidence tiers:

1. `unit_static` — existing/unit/property tests plus direct production-helper contracts, lint, type, security, dependency, dead-code, complexity, mutation, and change-surface signals. These scenarios do not claim to execute the complete worker.
2. `headless_production_pipeline` — real VODForge worker orchestration with real yt-dlp, FFmpeg, ffprobe, files, local HTTP faults, and process/resource measurement, but no Tk UI.
3. `packaged_app_e2e` — an exact packaged artifact driven through its visible UI, real worker, yt-dlp/FFmpeg, final media, shutdown/restart behavior, and independent artifact/output receipts.

A headless pass is never reported as full-application proof. If the packaged tier did not run, the report says `skipped` and leaves UI/settings/queue/lifecycle integration unproven.

### Analytics permission journeys

The repository suite covers bounded region retries, late response rejection,
one-shot browser opening, durable refusal and permission-dependent telemetry.
The `unit_static.telemetry_local_contract` scenario explicitly tests unknown and
denied permission before granting permission and exercising real Python HTTP
serialization against the loopback Worker/D1. No claim receipt substitutes for
analytics permission.

Run real Tk event-loop timing checks separately with:

```sh
VODFORGE_DISABLE_TELEMETRY=1 VODFORGE_NATIVE_UI_TESTS=1 PYTHONPATH=. \
  .venv/bin/pytest -q -s tests/test_analytics_native_journey.py
```

These intercept region responses, browser opening and claim transport. They
measure the source owner's browser-request/prompt timing, not OS browser focus.

For browser regression QA, start the companion site on loopback port 4321 and
execute `quality_harness/analytics_browser_journey.js` through Playwright's
`browser_run_code` filename input. It uses isolated browser contexts and
intercepts every API and external HTTPS request, covering browser consent,
GPC, closed tabs, source persistence, separate profiles, transient errors,
claim expiry and the final ten seconds of the permission window. Boundary
tests use the browser's virtual clock. This is an explicit manual browser
regression step, not an automatic NORMAL or packaged-app pass. A real-clock
two-minute run and OS/default-browser behavior require separate receipts.

### Original audio verification

With the harness dependencies installed and `ffmpeg` / `ffprobe` on `PATH`, run:

```sh
PYTHONPATH=.:engineering-quality .venv/bin/python scripts/verify_original_audio.py
```

On Windows, set `$env:PYTHONPATH = ".;engineering-quality"` and use
`.venv\Scripts\python.exe scripts\verify_original_audio.py`.

This networked probe downloads a single public test video through the production
worker with telemetry disabled and isolated persistence. Controlled source-family
filters exercise Opus and AAC availability separately; production Original audio
does not force either codec. It compares compressed packet hashes before and
after packaging, fully decodes the result, and records output counts, child
processes, and staging residue in `build/original-audio-verification/receipt.json`.
This is headless pipeline evidence, not packaged UI or playback proof. Use an
empty probe output directory for a fresh run; preserve older receipts separately.

## Setup

From a clean checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r engineering-quality/requirements.txt
```

Production dependencies remain in the repository's existing requirements files. Harness-only tools are isolated in `engineering-quality/requirements.txt`.

A complete FFmpeg installation containing both `ffmpeg` and `ffprobe` must be on `PATH` for headless runs. `imageio-ffmpeg` alone is insufficient because it does not supply the independent `ffprobe` executable. On macOS, Homebrew's `ffmpeg` package satisfies both. Verify the environment before spending time on a run:

```sh
./engineering-quality/run doctor
```

The packaged tier additionally needs an existing VODForge artifact. Use a locally built exact-checkpoint artifact or an independently checksum-verified release extraction; the harness does not silently build or download one and then treat it as the artifact under test.

## Commands

The release-facing FAST/NORMAL/DEEP commands and immutable candidate workflow are documented in [RELEASE_GATE.md](RELEASE_GATE.md).

FAST pre-commit gate:

```sh
./engineering-quality/run fast
```

Normal adversarial run (generated local corpus, real pipeline, faults, short soak, concurrency attack, security probes, repository tests, a bounded mutation campaign, and static signals):

```sh
./engineering-quality/run normal
```

Deeper run (longer fixtures/soak plus the first default-download W3C public boundary; the larger manifest remains an explicit candidate set rather than implied coverage):

```sh
./engineering-quality/run deep
```

The deep profile uses a controlled 50-job worker soak. If its post-warmup signal
persists and needs a longer observation under the same contract, run 100 jobs
explicitly:

```sh
./engineering-quality/run deep \
  --scenario lifecycle.repeated_job_soak \
  --soak-jobs 100
```

Run the 50-job form first. The 100-job option is diagnostic evidence, not a
machine-independent memory gate.

Add the W3C public-media boundary to a normal run:

```sh
./engineering-quality/run normal --include-public
```

Run one exact scenario:

```sh
./engineering-quality/run normal --scenario reliability.cancel_during_slow_download
```

The NORMAL gate includes `lifecycle.staging_transaction_transitions`. It polls
the real output root while the production worker downloads and transcodes,
records the `.vfstage` topology without reading media contents, skips an active
item, completes a fresh successor, and invokes the real Library-removal path.
The scenario requires private run directories and partial files to appear only
while owned, exact item-level terminal receipts, no idle `.vfstage` root after
skip or completion (including Finder-created `.DS_Store`), and proof that
removing an unrelated Library record cannot delete another active transaction.
Raw timestamped topology traces are retained with the ignored case artifacts.

Compare with a prior machine-readable result:

```sh
./engineering-quality/run normal --compare engineering-quality/reports/<baseline>/results.json
```

Start a full packaged-app session from a frozen candidate:

```sh
./engineering-quality/run packaged-e2e \
  --profile smoke \
  --candidate engineering-quality/candidates/<candidate-id>/candidate-artifact.json
```

That command re-hashes and freshly extracts the frozen ZIP, verifies the declared development or release policy, rejects any pre-existing VODForge process, creates isolated state paths, launches the exact executable in its own process group, and waits for the app's startup attestation before setting `driver_ready=true`. A visible UI driver performs the journey. Record each event with the versioned recorder rather than hand-editing JSON; the native window ID and owner PID must come from the observed window:

```sh
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<e2e-run>/session.json \
  --event app_visible \
  --screenshot /path/to/current-vodforge-window.png \
  --window-pid <attested-pid> \
  --window-owner-pid <native-owner-pid> \
  --window-id <native-window-id> \
  --window-title-token <session-window-token>
```

For a separate player or dialog window, keep the main session window arguments
and replace `--screenshot` with `--capture-window-id <actual-window-id>` and
`--capture-window-title <exact-native-title>`. The recorder verifies the separate
window belongs to the same attested process, captures that window directly, and
stores both window identities. Do not attribute a player screenshot to the main
window or substitute an image from another process.

For Qt, return to Library > Folders > the saved item > Description after the
driver-requested restart. Record `restart_observed` there with
`--observed-text` set to the exact fixture Description. The verifier binds that
event to the second launch's private Qt visibility receipt and checks rendered
geometry, selected owner and projection identity. Tk continues to require its
own post-restart history-load activity line.

If a UI surface cannot be reached, keep it missing and use `--allow-gap` only
when recording the next later event. The recorder adds the skipped event names
to the receipt; it never turns the gap into a pass.

Normal shutdown finalizes `e2e-result.json`. It passes only when ordered timezone-aware UI events, CoreGraphics window ownership/title receipts, screenshot existence and hashes, candidate/archive/bundle identity, real production stage diagnostics, output readability using the artifact's own bundled `ffprobe`, two clean launches, history/output hash persistence, cleanup, and process exit all agree. See [the driver protocol](runners/README.md).

Include a completed packaged receipt in a normal/deep comparison:

```sh
./engineering-quality/run normal --e2e-result engineering-quality/reports/<e2e-run>/e2e-result.json
```

## Full-app driver protocol

`packaged-e2e` writes exact paths and URLs to `session.json`. The required first journey is:

1. observe the packaged window;
2. enter the provided loopback URL in the visible URL field;
3. open and observe/change real Settings;
4. start Forge through the UI;
5. observe progress produced by the real worker;
6. observe truthful completion;
7. use `Command+2` (`Ctrl+2` on Windows/Linux) to open Library and inspect the committed item;
8. prove the known nonempty fixture Description is visibly inside the unchanged 360 px Selected Item rail, taller than the two-line-capped Tags region, and capped at the Library table's lower edge while the extreme title retains at least two measured visible lines;
9. request normal app shutdown.

Each observation is a structured event in `driver-events.json`: `app_visible`, `url_entered`, `settings_observed`, `forge_started`, `progress_observed`, `completion_observed`, `library_observed`, `library_description_observed`, `shutdown_requested`, `restart_requested`, and `restart_observed`. The recorder copies screenshots under the session's `ui/` directory, hashes them, timestamps the event, and rejects duplicates or wrong order. `library_description_observed` must include the exact visible fixture text. A private, launch-bound Tk receipt independently proves that the Description heading/body are mapped and contained, its first display line is visible, its body is taller than Tags and ends at the measured Library table edge, the rail's configured height remains the pre-existing 360 px while any responsive grid allocation is recorded separately, Tags is bounded to two requested text lines, the stress title retains at least two font-measured visible lines, and the stress title/path were ellipsized. The `control.json` action `relaunch` makes the session reopen the same exact artifact with the same isolated app data so restart/history and media hashes can be checked before the final quit.

The deeper packaged profile is first-class rather than an implied consequence of the smoke journey:

```sh
./engineering-quality/run packaged-e2e \
  --profile deep \
  --candidate engineering-quality/candidates/<candidate-id>/candidate-artifact.json
```

It additionally requires visible receipts for a throttled active run, a second run queued through the UI, cancellation requested through the UI, a clean cancelled state, the queued job advancing, and that queued job reaching completion. A smoke pass therefore proves only the happy path plus restart and does not claim queue/cancellation coverage.

The UI driver is observation/control only. It does not call production Python helpers, forge outputs, or synthesize worker events. VODForge exposes real-user view shortcuts (`Command+1/2/3` on macOS, `Ctrl+1/2/3` on Windows/Linux) through the same canonical view authority as the visible navigation. This gives native drivers a stable route when Tk children are not exposed through accessibility. Missing Library evidence still fails the tier instead of being replaced by shortcut existence or headless evidence.

### Native driver keyboard fallback

If a coordinate click only changes hover and does not invoke the control, stop
repeating it. A hover screenshot is not proof of activation or an app click defect.
Use ordinary keyboard navigation and observe the resulting window:

- With focus in the Forge URL entry, press Tab twice (format selector, then
  Settings) and Space. Verify that **VODForge Settings** actually opens before
  recording `settings_observed`. This route was observed in the signed 0.2.0
  macOS arm64 candidate; recheck focus/order for other layouts and platforms.
- Escape closes Settings. Verify the Forge window before continuing.
- Use the existing view shortcuts above for Library and Activity.

Do not assume Command-comma is implemented or use invisible callback invocation
as a substitute. Keep failed/limited runs intact; retry with new session evidence.
The keyboard Settings observation alone does not prove download, completion,
Library, or restart steps.

## Corpus policy

The tracked [manifest](corpus/manifest.json) separates generated, default-download public, external-boundary, and optional platform candidates.

- Generated fixtures come only from FFmpeg `testsrc2` and `sine` filters.
- W3C media was explicitly published for HTML media testing and is the preferred public default-download boundary.
- Blender-hosted open-movie files carry explicit Creative Commons terms.
- YouTube Creative Commons candidates separate copyright permission from platform automation authorization. They are metadata-only/download-disabled by default; a Creative Commons label alone is not treated as unconditional authorization to automate YouTube.
- Cookies, browser profiles, authenticated/private media, DRM, commercial music, and random creator uploads are out of scope.

External format IDs, exact bitrates, item counts, and hashes are not pinned unless the publisher supplies an immutable artifact. Source properties and generated-output properties are stored separately and compared from evidence captured in the same run.

## Fault and measurement model

The loopback origin injects HTTP errors, retryable failures, throttled transfer, connection interruption, metadata/thumbnail stress, Unicode, punctuation, and long titles. Other probes use controlled unwritable paths, symlinks, deliberately wrong ffprobe contracts, child failures, cancellation, repeated jobs, and simultaneous unsupported worker attacks.

The harness records:

- source-analysis/job-initialization, download/post-process, transcode, validation, commit, cleanup, and total time where available;
- progress bytes, effective throughput, CPU, process-tree RSS, child count, zombies, file descriptors, threads, output bytes, peak disk, and staging residue;
- independent ffprobe container/stream/codec/bitrate/duration evidence;
- scenario status, raw evidence paths, classified findings, and suggested fixes;
- machine, load, disk, Git SHA/dirtiness, tool versions, and optional baseline deltas.

The controlled deep soak additionally writes incremental post-GC observations
for root RSS/USS where available, traced Python allocations, GC-tracked object
types, FDs, Python and OS threads, process children, private thumbnail-cache
state, on-disk history state, isolated temp files, and staging residue. It reuses
one exact source identity and releases each full pipeline result before sampling
so harness receipts do not create a linear retention signal. Tracemalloc keeps
only baseline/final raw snapshots and bounded intermediate deltas.

This headless tier never constructs Tk or pumps UI events. Tk image counts,
in-memory Library history, and completed-run image ownership are therefore
reported as unavailable, not zero. Those require packaged/UI evidence.

Performance values are not universal pass/fail constants. Compare like-for-like machines and corpus conditions; comparison refuses metric deltas when profiles, scenario/tier sets, or explicit workload contracts differ and reports commit/machine equality separately. A soak records memory/FD trends but does not convert a single machine's arbitrary byte threshold into a leak conclusion.

## Result contract

Each run writes:

```text
engineering-quality/reports/<run-id>/
  results.json
  summary.md
```

Raw case diagnostics and media stay in ignored `engineering-quality/.runs/<run-id>/`. The JSON contract is defined in [run-result.schema.json](schemas/run-result.schema.json). Every negative finding includes an area, reproduction, evidence, severity, classification, and suggested fix. Findings use only these requested classifications:

- correctness defect
- reliability defect
- security defect
- performance defect
- maintainability risk
- code smell
- stylistic preference

Static-tool output is a signal, not proof. A security issue is reported only when a safe reproducer demonstrates the broken property and its preconditions are stated.

## Maintainability change probes

[change-probes.json](maintainability/change-probes.json) measures the current reference/test surface for adding an output mode, changing filename organization, adding metadata, altering playlist behavior, and extending the downloader backend. These probes do not pretend to be completed changes; they identify coupling and protection surfaces. Deep evolution benchmarks should apply each change in a repository-owned temporary worktree, run the full relevant gates, record actual files touched/regressions, and then remove the worktree only after clean containment verification.

## Current first-version boundaries

### Telemetry contract checks

Ownership is a cross-entry-point invariant, not an enrollment-only test. The local
contract exercises fresh, claim, cloud-seen, cloud-click, legacy-launch and waitlist
creation before enrollment. It requires authenticated retries, second-credential
rejection, exactly one durable credential, and no legacy mutation after enrollment.
An omitted matrix case fails the receipt. Harness self-tests reject green delivery
results with duplicate credentials or unauthorized writes. The site suite adds
reverse order, concurrent enrollment and revoked-credential coverage.

The gap addressed here was split fixtures: claim-first tested metadata while
exclusive ownership was tested only on a fresh row. The old loopback probe never
issued a real claim and read only version/event counts. Future identity or durable
row creators must be added to both matrices; these checks do not imply exhaustive
security verification or official-binary attestation.

NORMAL/DEEP include the sibling `vodforge-site` backend suite and a local-only
Python client → production Worker owner → ephemeral D1 contract check. Set
`VODFORGE_SITE_REPO` if the site checkout is elsewhere; it must be clean with its
Node dependencies installed. Receipts record the site commit before/after.
The contract exercises first launch, version updates, event deduplication, and
real injected HTTP failures serialized through the product-event owner. It is
source integration evidence, not deployed routing or packaged-app proof.

Headless profile runs force telemetry suppression. Public releases additionally require the [packaged preview-D1 telemetry journey](TELEMETRY_RELEASE_GATE.md) on macOS and Windows; use `packaged-e2e --profile telemetry --telemetry preview` for that separate positive gate. A harness-process audit guard
blocks production telemetry hosts and fails the isolation receipt even if a
caller swallows the exception. The local Worker denies outbound fetches and
uses only explicitly supplied local bindings/migrations; no production D1 is
accessed. Child processes inherit suppression; the Python audit hook itself
does not cover child processes. FAST also checks the isolation receipt.

The first version makes real local MP4/MP3 output, same-run source-quality selection, HTTP 404/503, connection interruption, slow transfer, download and transcode cancellation, unwritable destinations, FFmpeg dependency failure, fresh-output validation, symlink/path, URL-secret, soak, defensive simultaneous-worker attack, static/test, bounded history mutation, maintainability, and packaged happy-path/restart journeys runnable. The packaged deep protocol includes queue and cancellation but still needs a stable repository-owned native UI automation engine.

Highest-value additions are forced process-kill/restart with stale-stage accounting, low-disk volumes, real provider playlist scaling, duplicate/queue mutation through packaged UI, active-run updater shutdown, blocked-analysis slot exhaustion, multi-hour soak, actual temporary-worktree change implementations, and a wider mutation campaign.

Expanded feature telemetry is documented in
[`docs/telemetry-features.md`](../docs/telemetry-features.md). The backend gate
checks cross-language vocabulary parity, and the preview release gate checks
feature/action coverage and attempt relationships as well as event counts.
`python -m quality_harness.telemetry_feature_probe --site ../vodforge-site
--version <registered-version> --output <fresh-evidence-directory>` is an opt-in
preview serializer/D1 contract check. Supply the QA key through the environment.
It is not native UI or release proof; final artifacts must follow
[TELEMETRY_RELEASE_GATE.md](TELEMETRY_RELEASE_GATE.md).


### Pre-publication update fixture

`quality_harness.update_fixture` serves only explicitly listed final release
archives on a scoped loopback URL. The existing isolated preview mode can use
that feed for native update and Repair journeys without publishing first or
changing signed bytes. It records hashes and requests, supports a real HTTP503
fault, and preserves normal publisher verification. See the
[telemetry release gate](TELEMETRY_RELEASE_GATE.md#isolated-updater-feed-before-publication)
for the baseline, launch environment and required D1/UI evidence.

### Consent withdrawal and prospective operation evidence (2026-09-16)

The telemetry owner must not recreate an outbox after withdrawal or resume a
pre-withdrawal observation after a failed purge, restart, or rapid re-enable.
The prior owner fails test_revocation_survives_locked_outbox_and_restart_without_replay:
an independently recorded sink receives the old row after denied consent and a
locked outbox. Prior-source receipt:
build/variant-help-20260916/privacy-revocation-before.log. A private epoch in
existing consent settings/outbox now invalidates old observations; it is excluded
from the wire. Separate tests cover permission-to-write ordering, revocation
between the two sinks, immutable replay and fresh post-enable observations.
An already in-flight request cannot be unsent. Previous tests assumed successful
purging or stopped before re-enable, so they missed this cross-lifecycle defect.

Operation observations are prospective, separate from session feature presence.
The actual local converter captures failure facts before formatting display text;
controlled failures at preparation/image/transcode/validation/commit assert the
independently observed exception, final files/staging state, and persisted typed
event. Playback checks provider failure followed by actual Playing and Ended.
The source-native Windows Help runner pairs OS input, visible modal/grab receipts
and local outbox events; the injected collection policy and local sinks are
explicitly labeled, never packaged/preview proof. Its first instrumented matrix
caught missing forced-tour closure telemetry even though the tour was visible;
forced teardown now retires the existing operation owner.

The resize invariant is that hidden primary views do not consume geometry work or
history projection, while selected views restore current layout on re-entry.
The actual native view-allocation test fails on old source and passes after the
change. Profiled quiet drags reveal the expensive hidden history path; absolute
performance qualification still requires unprofiled before/after comparisons with
runtime/driver hashes, CPU intervals, commanded and delivered geometry, and no
screenshots during measurement. Empty/normal/large Library, Forge, panel/focus/
scale/teardown variations and Mac/exact signed artifacts remain distinct required
tiers. Event counts are not frame rate or Chrome parity.

Backend migration tests preserve historical columns, indexes and FKs, reject
null/non-failure action diagnostics, and exercise immutable replay through the
enrolled route. CRM tests use mixed legacy/new/source/channel fixtures,
out-of-order arrival and incomplete sequences; commits/reuse count only at their
actual observation, never again in completion summaries. These are source checks;
fresh preview D1, blinded investigation, native consent-positive and denied/off
signed artifacts, Update/Repair and full release gates remain required.

The local converter also observes the successful physical commit before later
metadata construction, using its existing worker event queue. A prior-source
case produces an independently verified file but no commit observation when
metadata then fails (local-commit-observation-before.log). The regression checks
preserved bytes, one observation, history-stage failure and cleaned staging.
Earlier conversion tests stopped at commit failures or fully successful results,
so they missed the committed-file/later-history boundary. This complements the
download sidecar-partial case; neither proof infers an absent event means zero.

Native support testing also found reply-enabled Feedback at bounded small window
sizes collapsed the message field to 17px. Existing modal layout ownership now
allocates reply-field height while retaining the parent bound. The unchanged
independent field-height/footer/backdrop checks failed twice before and all
25 native cases passed afterward. Exact packaged visual checks remain required.

### Blind packet follow-up: observations cannot interfere with work

The coordinator assessed only persisted preview-D1 events and approved context
before the fixture was revealed. It identified the failing app frame and explicit
retry, distinguished two commits from two reuse observations, and explicitly
could not establish exact trigger, sidecar cause or same-source settings history.
The locked assessment is maintained in the separate coordinator audit workspace.

The revealed malformed in-memory history row fault occurred inside the newly
added observation comparison. The normal durable loader already discards
non-mapping rows, so this injection does not establish a reachable on-disk user
failure. Observations now return unknown for absent/malformed evidence, and the
existing legacy-ownership lookup skips non-mapping rows while retaining exact
signature/path requirements. Cross-owner CPU pipeline tests deliberately carry
invalid rows through actual transcode, validation, commit, reuse and optional
sidecar failure; 35 focused cases pass. No actual media error is swallowed.

A separate independently verified bug mislabeled new variant reuse as owned
legacy by comparing a suffix with a whole path component. Namespace observations
now compare the actual validated artifact directory with the existing output
planner's target and require actual legacy-path membership otherwise. The prior
real-pipeline test fails (namespace-sidecar-before.log); the corrected cases pass
across every CPU preset. Optional artwork, metadata and thumbnail failures now
emit a bounded sidecars-stage diagnostic at both fresh and reuse boundaries,
with failed media count zero and sidecar count one; completed partial observations
remain separate. This closes a blind-investigation limit without raw messages.

The initial producer driver mistakenly tried to populate history from the
content-only metadata sidecar; it therefore retained empty history, making its
first_observed values accurate but useless for same-source claims. Follow-up
must consume actual history_record events through the existing history owner.
Never reinterpret the original packet as stronger evidence.


### Reuse-candidate diagnostics must survive every real boundary

The controlled corrupt AAC candidate in producer I completed a valid replacement
while preserving the rejected file, but the proposed rejection observation was
lost. The app passed typed failure detail with action stage; the real telemetry
owner correctly rejected that combination. Its allocated ordinal was absent and
the next event incorrectly reported zero drops. Two pre-fix regressions failed
in reuse-rejection-transport-before.log. Earlier reuse tests used a permissive
collector and therefore bypassed the actual outbox validator.

The existing operation owner now records candidate_rejected for actual candidate
rejection and keeps ordinary no-candidate misses as stage observations. This is
not an operation failure. Typed details remain bounded and apply only to this
explicit action or existing failure actions. Exceptions after ordinal allocation
increment the bounded observation-drop count; the next retained observation
reports the gap and a later retained observation resets the counter. Nine real
owner cases cover typed and untyped candidate rejection, a normal empty lookup,
and drop/reset behavior across download, conversion, Help, playback and resize.

The first enrolled-route persistence regression also failed against the previous
database constraint. Migration 0020 expands only the download-candidate boundary,
preserves every existing event column and index, and retains foreign keys and
cascade behavior. Actual enrolled-handler tests verify immutable replay, later
successful completion, exclusion from failed-action counts and rejection of
private messages or wrong feature/action combinations. Cross-language vocabulary
parity remains required. CRM labels the fact as a rejected reuse candidate.

Source checks do not establish delivered production data or packaged behavior.
Producer I is preserved as incomplete evidence; a fresh preview run must verify
real media reuse/repair, the retained typed rejection and natural outbox delivery.
Missing facts remain missing; a drop count does not reconstruct their contents.


### Optional companions need explicit outcomes, not absence-of-error inference

The J persisted-first review could identify commits and reuse but could not tell
whether missing metadata or artwork was repaired. Five real-owner outbox cases
failed before this patch (sidecar-outcomes-before.log). Existing reuse coverage
proved preserved media and recreated files, while sidecar telemetry described
only failures; neither absence of a failure nor overall media success established
an actual companion-file action.

The existing metadata, thumbnail and private artwork owners now optionally report
their real write or validated-cache-return boundary. No new durable owner or
sidecar identity is introduced. Closed kind, outcome and media-context fields
distinguish created, repaired, rewritten, already_present, not_requested,
unavailable, failed and unknown. Repaired means filling a missing companion next
to validated reused media, or replacing an unusable private cache entry. It does
not reconstruct whether a companion had existed earlier. Rewritten means an
existing regular file was written again; it does not assert bytes changed.
Already_present applies only to an actual validated cache return. Unknown
filesystem observations never become asserted creation. These are best-effort
point-in-time facts, not cross-process race guarantees.

Fourteen new cases use the real telemetry owner and independent files: fresh and
repeated writes, all three missing companions on media reuse, disabled settings
versus unavailable artwork, invalid cache recovery, both fresh/reuse optional
write failures, unavailable prior state, collection disabled, unexpected
observation errors and callback failures across all four writers. Media bytes
remain unchanged during repair and optional failures. Production write/validation
errors retain their behavior; optional diagnostic exceptions cannot break writes.
The callback is admitted by current consent and collection is checked again at
the telemetry owner. An already-started observation cannot be retrospectively
undone. A successful write may precede a later cache-maintenance failure, so
success and failure observations must retain their sequence rather than be
collapsed into one inferred final state.

Backend tests persist/replay all 24 kind/outcome combinations and reject private
paths, filenames, hashes and arbitrary outcomes. CRM explains historical gaps
without backfill. Source checks and fixture assertions are not packaged proof;
fresh preview evidence is required for prospective repair/failure diagnosis.

### Keep intentional diagnostic isolation explicit in every static gate

The frozen aab31d5 FAST receipt exposed seven Bandit B110 findings in the
previously reviewed reuse, download, local conversion and namespace-observation
boundaries. Ruff BLE001/S110 comments did not annotate Bandit's independent rule.
Each boundary was reviewed: it catches optional diagnostic work only, preserves
unknown facts where collection fails, and leaves actual validation, write and
commit failures outside the catch. Existing observation-noninterference and
rejected-candidate transport tests cover the behavior; their earlier passes could
not establish that a different static tool accepted the documented exception.

The fix adds only narrow B110 annotations with the existing boundary reason.
Before/after Python ASTs are identical for all three files. No global severity
filter, disabled gate or runtime rewrite is used. Preserve the failed FAST receipt
and rerun the mandatory gate; complexity debt remains separately visible.

### Typed safe-output refusals must survive diagnostic boundaries

The K persisted-first review identified an optional metadata failure but only
stored reason=unknown and safe_output:342. Physical truth later established a
directory at the requested metadata leaf. Existing optional-write tests used a
PermissionError double, and path-containment tests proved refusal/preservation
without inspecting the real durable telemetry owner. Eight new assertions failed
before this fix, including actual metadata/thumbnail conflicts on fresh and reused
media and both POSIX and portable commit owners.

The existing UnsafeOutputPathError now contributes its actual closed type and
output_conflict reason. Its local message is not parsed; misleading wrapper text
cannot supply a fabricated failure code. Actual nested OS evidence still
distinguishes permission denial, disk full and I/O errors. An unrelated exception
with the same class name does not acquire this classification. No raw path or
message is serialized, no write/containment behavior changes, and no new owner or
schema migration is introduced. Thirteen focused variations cover these invariants, retained
media/blocked destinations and opaque exception text. The backend route persists
and replays the real bounded shape; its first regression failed before the
allowlist addition.

This class reports an unsafe output-path refusal, not the exact leaf type or
whether a redirect was malicious. Unknown nested causes remain unknown. K is
immutable; historical unknown events are not relabeled. Source tests require a
bounded prospective preview proof before claiming delivered diagnosis.


### Native click intent and late media facts (2026-09-16)

The exact signed Windows a0434ee candidate exposed two readiness errors. A pointer
could enter a ChoiceMenu and click without a preceding Motion event; commit then
used an older keyboard/hover selection. A generated MP4 had no extractor duration
but libVLC later reported six seconds; Preview Moments had already extracted five
zero-second images and never refreshed their captions. The transport and preview
click targets used the later duration, so visible evidence disagreed with behavior.

Shared invariant: a committed action must bind to the current event's intent, and
derived asynchronous UI must bind to the current media facts and owner lifetime.
Hover is presentation, not a prerequisite for selecting the clicked row. Unknown
duration must remain unknown rather than becoming five apparently valid zero
timestamps. When facts change, timestamps and images refresh together; obsolete
worker results cannot replace the current generation. One preview worker runs at
a time, and an unavailable/invalid image does not trigger an unbounded retry loop.
These changes extend the existing ChoiceMenu and MediaPlayerWindow; no new owner
or telemetry vocabulary is introduced.

Coverage gap: prior native Settings and Feedback tests explicitly called
selection_set before ButtonRelease, bypassing the user input boundary. The
shared menu test exercised hover and keyboard separately. Existing player tests
covered fixed metadata, volume/readiness and shutdown, but not delayed duration
invalidating already derived imagery. The new native interaction matrix includes
four inline/form/scrolled click cases, unknown-to-known duration, in-flight
replacement with independently checked image pixels, seek/caption agreement,
unchanged-snapshot deduplication, pending-close retirement, and two extraction
failure cases. The existing real Settings quality-selector and modal Feedback
tests now click coordinates instead of preselecting their answer. This extends
the contract across output planning, support forms and playback. Existing
settings/telemetry latest-intent and player readiness harness matrices remain
complementary coverage.

Prior-failure evidence: seven new assertions fail against a0434ee, and both
strengthened real Settings/Feedback cases also fail with the old ChoiceMenu.
Windows receipts 037/065 and separated pointer move/click 077-079 preserve the
native symptom, including the actual stationary click; keyboard selection passed.
Generated-video playback and the six-second end state are independent of the
preview strip. Limits: native Tk regressions use controlled backend/preview
boundaries to schedule races; they do not qualify a newly signed artifact,
physical pointer behavior on both OSes, every possible scheduling interleaving,
or frame presentation performance. Exact rebuilt-package checks remain required.


Validation checkpoint: 121 native Tk cases passed together; after preview state
initialization was grouped with its existing strip builder, the focused
interaction/backend suite passed again. Full source suite: 1653 passed,
166 environment/opt-in skips in the isolated worktree. Canonical Ruff/format,
mypy (79 files) and Bandit (zero findings) passed. Complexity findings remain
191, identical to a0434ee; this is not an all-green maintainability claim.

### Choice admission must be checked when the action commits (2026-09-16)

Independent review of de92d0b found pre-existing cancellation/admission gaps:
ButtonRelease ignored its own coordinates, and an already-open dropdown could
still commit after the field became disabled. The review used extracted methods;
the product Tk boundary then reproduced both, plus a queued retired-menu callback
that emitted a selection and closed a replacement popover. These are residual
bugs, not regressions attributed to the preceding press-coordinate fix.

The shared invariant is that an effect needs current intent, permission and owner
at its commit boundary. ChoiceMenu now shares coordinate hit testing between
hover/press and release; a release outside a visible row cancels. Disabling a
ChoiceDropdown immediately retires its popover, and commit rejects a disabled
field or a callback from a retired menu. Valid keyboard Return still commits;
Escape, outside release and permission withdrawal emit no selection. Re-enabling
the field creates a fresh usable menu. No new runtime owner is introduced.

The native matrix adds 15 fail-before cases across inline and form fields:
horizontal exit, both vertical padding regions, release at a new row without an
intermediate Motion event, queued mouse/Return after disabling, re-enable and
selection, and a late callback after owner replacement. It checks the independent
StringVar outcome and actual ComboboxSelected delivery, not just popup visibility.
The existing Return/Escape focus-and-Tab test now also changes the selected row
and checks value/event preservation. Settings preset selection now sends actual
press/release coordinates; its previous zero-coordinate release depended on the
same bypass. The shared hover test likewise dispatches a real Motion event. Prior positive click coverage missed release
cancellation and dynamic permission changes; prior lifetime coverage checked
popup destruction without asserting absence of committed selection.

Representative cross-owner checks are the existing settings durable-commit and
telemetry retry/permission-withdrawal matrix in
tests/test_cross_owner_lifecycle.py and player replacement/closed-callback matrix
in tests/test_playback_control_lifecycle.py (paths relative to this directory).
These retain independent durable files, delivery attempts and provider outcomes.
They did not exercise the native menu's event admission boundary. The new native
cases extend that broader class rather than substituting one local regression.
The de92 before-fix log preserves all 15 failures. Native generated events do not
prove physical drag delivery on Windows or macOS, painted-frame performance,
every possible callback interleaving, or a rebuilt signed artifact. Those tiers
remain separately identified in the release evidence.

Validation checkpoint: 136 native cases pass together, and the existing 72
cross-owner lifecycle cases pass. Full source suite: 1653 passed, 181 opt-in or
environment skips; Ruff/format, mypy (79 files), and Bandit (zero findings) pass.
Complexity remains 191 findings. A prior native batch's sample showed
off-thread garbage collection entering Tk while the main thread waited for an
import lock; the sample does not identify the exact collected object graph. The
test fixture now collects unreachable test-process objects on the Tk thread before
creating the next root and explicitly acquires focus for its owned window. The
crashed and intermediate failing runs are retained. This is fixture hygiene, not a
product lifecycle repair, and does not relax application lifecycle assertions.

Final gate review found that the explicit native_surface_contract file list did
not include the new interaction matrix. The headless repository suite skipped its
opt-in cases, so adding the regression file alone did not enforce the new class.
The required NORMAL/DEEP source-native scenario now includes that matrix alongside
the existing popover, polish, support, activity and consent tests. Its existing
JUnit verifier rejects empty, skipped, failed or errored reports. FAST remains a
headless gate and cannot substitute for executing this native scenario. The new
case list is not a waiver for exact packaged-artifact or OS-input qualification.

## Archive, Watch and embedded-player boundaries

See [the feature validation ledger](ARCHIVE_WATCH_QA.md) for the new required
regression, class lifecycle, native and telemetry acceptance coverage. The native
surface gate now enrolls test_archive_native.py and test_archive_actual_playback.py;
skipped cases cannot count as
source-native acceptance. Current WIP evidence and unexecuted tiers remain explicit.


The existing bounded history mutation gate also exercises pending-delta staging
and restart replay through test_history_pending.py. Its unmodified copied suite
must pass first; all five targeted mutants must produce actual JUnit test
failures. Import/collection/setup errors, skipped cases, empty reports, timeout
or unavailable runners cannot qualify as detection. This is a bounded
history/privacy/recovery score, not a repository-wide mutation score.


## Recovery and presentation regression gates

The five classes in [RECOVERY_REGRESSION_CLASSES.md](RECOVERY_REGRESSION_CLASSES.md) are mandatory NORMAL/DEEP scenarios. Run the maintained before/after source contract and retain exact-artifact code binding separately from native/packaged GUI evidence. Source checks never waive the packaged journey gate.


### Fixed-DPI shared-control prototype (v65–v66, bounded qualification)

The observed Windows 200-percent virtualization and flag-only clipping share an
invariant: intended geometry, font pixels, contour geometry and native pointer
coordinates must describe the same admitted window. Earlier Mac backing-density
checks validated raster transport but did not exercise a Windows PMv2 physical
coordinate domain. The bounded opt-in metrics contract keeps measured positions
physical and converts only canonical dimensions; default windows are unchanged.
`test_window_logical_metrics.py` compares target-pixel chrome to the independent
existing density rendering recipe and detects an unscaled-edge negative. Native
shared-control checks cover editing, text fit, menu bounds and lifecycle at
baseline/2x geometry; these are not Windows physical-resolution acceptance.
Independent Windows capture, actual awareness/DPI and native hit provenance are
required separately. Fixed 96/192 DPI only; mixed-monitor changes, whole-app
adoption and installed packages remain outside this prototype.


The v66 review strengthens two independent checks: RGBA equality now compares
RGB and alpha separately and rejects a color-only/same-alpha negative (RGBA
`getbbox()` alone can miss it). A surviving-interpreter native case destroys and
recreates Toplevel entries at both admitted scales, queries live Tcl images and
editing behavior, and checks no new images after warm-up. Density variants live
in the existing interpreter ProductChromeOwner, not retired Toplevel objects.
Earlier whole-root teardown could not expose stale per-window style images.


The final fixed-192-DPI Windows fixture now has independent physical-client
capture and native pointer/keyboard provenance, including the actual focused
native ancestor and exact Tk leaf. OS long editing changes only the intended
value; one effective palette change restores contour pixels/image handles.
Actual wrong geometry, double font and downsampled checker/gradient faults are
rejected, with positive restoration. Original receipts live in
`mac-resume-v66/windows-remaining-passed`, bound by `remaining-proof-binding.json`.
This covers the explicit prototype only: production awareness stays off, Windows
100-percent/mixed-monitor/all-consumer and packaged behavior are not inferred.
Synthetic focus/confirmation predicates remain distinct from native outcomes.


### Continuous control material, September 19

The hover navigation checks previously accepted any changed pixel plus one
unchanged face pixel. Thin disconnected contour strokes passed those checks
without producing a concave well. The top ttk adapter also tiled a small image
with a zero-border layout and painted selection on a separate narrower canvas.
The existing material owner now uses the same diffuse recessed rim as the Forge
selector, with fixed corner regions and a stretched interior; canvas navigation
consumes that same recipe at its actual bounds. The user's latest direction
removes all navigation underlines. Persistent concavity and semantic icon/text
roles indicate selection; focus remains a separate accessibility contour.

The native matte case observes upper inner shading across both halves, records
unresampled physical idle/hover/selected/focus captures, and injects a producer
fault removing the shared rim. It verifies the physical shadow disappears and
returns after restoration. The initial injection did not invalidate the native
display until a state transition; that failed observation is preserved separately.
These checks and independent scene review cover representative ttk and sidebar
owners, not all consumers, themes, Windows, physical input or packaged artifacts.


### Owned capture must contain the composed children

Windows PrintWindow success did not establish usable pixels: the old client-only
path returned an almost black view while the independently observed Library was
fully rendered. The transition then displayed that buffer as its blur cover.
The existing Windows capture adapter now requests full content from the same
owned HWND. It never captures desktop pixels. The speculative RedrawWindow
mitigation was removed because it did not repair this source-buffer defect.

The maintained Windows native capture test samples independently chosen regions
of a Frame, Canvas and nested child, including legitimate black content; it forces
the actual former print flag, observes missing composition, restores exact pixels,
and verifies an unavailable capture returns None. Facade tests keep invalid
geometry out of the native adapter. The actual full-app before/after captures
and source binding are under windows-transition-v74. The first independent
physical temporal observer refused to capture after foreground ownership was
lost; it yielded zero frames and cannot qualify transition growth or continuity.
No generic dark-pixel heuristic rejects legitimate media. Prior settled-pixel and
Mac transition tests missed the Windows-specific incomplete capture path.


### Canonical units and the exact font used by a native control

The opt-in button adapter initially measured a newly copied font rather than the
font tuple given to ttk. Python Font(font=tuple) resolves actual attributes first;
on Mac the pixel-to-point-to-pixel round trip changed line height, producing86px
instead of the required88px. Querying Tcl metrics for the original tuple fixes
that discrepancy without weakening geometry. The bounded native metrics suite
now covers buttons alongside fields/menu owners: default sibling44px, opted-in
88px, wrong-base-style negative, disabled callback exclusion, Toplevel retirement,
image identity, rendered focus, effective theme change and exact pixel restoration.

Canonical dimensions convert once; measured owner coordinates and recovery
content height stay unchanged. Checkbox box, label and glyph now share those
window units and use the existing backing-density image adapter. Native default
and2x checkbox captures and valid-release/disabled cases support that consumer.
The old source-string assertion requiring literal size12 was updated to its
canonical12-through-metrics expression; actual native dimensions are the outcome
check. Mac metrics tests and Windows composed-capture tests are enrolled in their
respective existing source-native harness branches. Production DPI awareness is
still off; fractional/mixed-monitor/full-consumer/package qualification is absent.


### Native storage capability is separate from pixel format

A 2x tooltip capture exposed PyObjC `objc.varlist` storage despite ordinary
RGBA8 metadata. The existing fast capture guard assumed every bitmapData result
had a length. It now requires contiguous buffer-protocol storage and sufficient
byte capacity; unsupported storage uses the existing native PNG encoder. The
unsized-storage case fails before the repair and passes afterward alongside
opaque, alpha, alternate-format and truncated-buffer cases. Existing coverage
missed this because every fake supplied a memoryview and the full-app native
fixture supplies supported storage. The separate real full-app pixel-fidelity
check still passes without invoking the encoder. Tooltip default/2x native
captures pass after the repair; no universal native-storage or performance claim.


The same units boundary now covers FactsText and ActivityLogText. Their native
fixtures preserve source text, selection/reflow, no-op snapshots and decoration
retirement while canonical fonts/gaps scale once. Density changes also update
embedded severity labels: the prior default-metrics case failed because only
the containing Text font changed. Existing spelling/wrap tests covered creation
but missed that transition; the new default and injected2x cases exercise it.
Host macOS, injected192 per-window metrics, native backing/capture ratio2.0;
physical OS DPI unmeasured. This is not Windows DPI or full-app qualification.


Scrollbar unit coverage tests both orientations with default and injected2x
metrics: canonical track/minimum thumb/stroke scale; measured pointer travel
produces the same fractional scroll result. Existing cross-axis drag and
retirement checks remain enrolled. The integrated shared metrics native suite
passes19 cases across fields, choices, buttons, toggles, segments, hints,
documents and scrollbars. This remains bounded Mac fixture coverage.


### State material, resting depth and nine-slice continuity

A nonzero focused pixel difference did not exclude legacy perimeter rings, and
an unchanged edge sample encoded the old flat-navigation assumption. The current
contract requires raised resting interactive controls, concave interaction
states and distinct focus without bright outlines/underlines. Tests now cover
actual Tab/Shift-Tab, selected+focused state, restoration, unchanged values and
foreground roles across five presets. Original ring captures and failed
editor/list/volume cases remain. The scene action owner changes its base image
for focus; adding a shaded surround over a still-raised action produced a double
contour and was rejected by independent visual review.

Feeding an unflattened raised source image into the existing nine-slice element
produced a repeated grid. The fixed producer uses the existing stretch contract.
The independent native oracle samples horizontal continuity over the blank area
above the label at three widths, default and injected2x metrics; the old
stretch=False producer mutation must violate the same<=1 channel-variation
criterion and restoration must be exact. The first single-row mutation-strength
check measured3 but required>3; it remains a failed test attempt. The corrected
oracle strengthens the positive check to the whole blank upper band; old grids
reach7. Six cases pass, including actual prior-renderer mutation. Source image
flags or successful geometry alone are not visual proof. Mac injected metrics
remain distinct from actual Windows DPI. No broad release journey was restarted.


### Search-field children share their owner's units and material

The v95 finite-consumer pass found LibrarySearchField's chrome already using the
window metrics while entry, placeholder, shortcut hint, icon and padding retained
ordinary dimensions. The new injected192 native case fails before the repair
(point font11 instead of pixel font-29); default sizing passes. Existing
`test_shared_control_geometry_font_and_popup_lifetime` exercised ProductEntry,
ChoiceDropdown and PillAction, so it did not cover the search-specific children.
LibrarySearchField now reuses the existing metrics and backing-density icon
adapter, keeping character-count widths and measured coordinates unchanged.

Rendered focus inspection also found icon/hint rectangles retaining the resting
background after the entry adopted focus_surface. The same owner now applies its
semantic background to its labels. New background checks fail on both prior
sizes. Existing field-edge tests check obstruction at the contour, which cannot
detect a wrong interior child color. New native checks preserve Unicode text,
selection/caret through compact mode and theme refresh, placeholder return and
safe variable writes after retirement; existing cross-owner contour and lifetime
cases pass alongside them (26 native cases). This is bounded source-native Mac
proof, not physical Windows DPI, every palette, or packaged acceptance.

The suspected copied-font measurement issue in ChoiceMenu and PillAction was
NOT reproduced: six native width/ellipsis/measurement cases pass before any
runtime change. Their measurement implementations remain unchanged. ChoiceMenu's
forced smaller test canvas can clip when its requested width exceeds its actual
width; normal ChoicePopover refuses an oversized popup. That observation alone
is not a production regression or authorization for a popup redesign. Revisit
with an enabled constrained consumer if its labels demonstrably truncate.


### Placeholder and editable-section children inherit the same unit boundary

The v96 placeholder cases exercise the same font/inset/material invariant as
search, under a different owner (ttk ProductEntry). Default focus retained a
light hint rectangle; injected192 also retained the ordinary hint font. Both
failures are preserved. The fix reuses the entry's actual font and window metrics
and keeps the hint visible in an empty focused entry with a separate caret.
Existing `test_collection_footer_placeholder_scoped_keys_and_input_lifetime`
checked presence, content isolation, keyboard save and footer visibility, but not
hint-font parity or interior background. That actual OS-key dialog journey still
passes alongside the new density checks and cross-owner retirement checks.

The v97 editor checks add an independent durable-save boundary: failed save keeps
exact Unicode draft and editing state; successful retry sends the same owner/text;
cancel after another edit restores the last saved value. Existing ordinary
caption/footer and scoped cancel/owner-replacement checks pass. The prior
injected192 case fails at body font size, because buttons/scrollbar had converted
while labels, text and padding had not. The existing editor now converts canonical
sizes once, retains measured requested heights, and measures/draws one explicitly
pixel-sized font. No new owner or storage model. Native calculated-height footer
checks at injected192 are prepared but NOT executed because GUI ownership was
yielded. The first failed-save screenshot preceded a render pump: it proves
neither visible error feedback nor settled caption layout. A pump was added and
that rendered receipt remains pending. Do not promote source assertions to those
unobserved native outcomes.


### Follow-up qualification and native-window isolation

The v97 resume completes the previously pending injected192 editor checks:
11 native cases pass on unchanged source, including settled failed-save feedback,
calculated-height caption/footer bounds at widths760/1120, and cross-owner
placeholder/search cases. Earlier unpumped screenshots remain historical only.

The v98 dialog shell check fails before at injected192 because the existing
ActionDialogSurface retained24px shell padding instead of48px. It now converts
its canonical padding, footer/status gap and scrollbar spacing once using the
popup's existing metrics; all14 current callers provide canonical constants or
defaults. Existing protected-action tests exercised ordinary metrics only. The
new native cases independently verify child geometry and action visibility,
Save invocation and parent-metric preservation after popup destruction; the
actual collection keyboard/footer journey still passes (3 native cases total).

A separate native Toplevel intentionally does not inherit its parent's admitted
DPI merely through Python ancestry. The default child of an injected192 parent
remains ordinary, while an explicitly admitted192 child uses its own metrics.
In-window ChoicePopover is a Frame and already uses the same native window.
Production PMv2 remains off. Future native-popup adoption must use that popup's
actual PMv2/DPI admission before controls, with content fonts/minima/work-area
checks; Mac injection is not evidence of physical Windows monitor inheritance.


### Native list styles must remain local to their window units

The v99 finite list audit found PixelScrollTable has no production constructor
call (current Library creates ArchiveBrowser), so no speculative conversion was
made there. Active ChapterList retained38px rows and ordinary fonts/columns under
injected192. The new native row-height case fails before (38 instead of76).
ChapterList now derives a Dpi variant from its existing Player.Chapters.Treeview
style, scales fixed column dimensions and uses the window font tuple. Native
input, selection and inherited palette mappings remain owned by ttk.

Existing `test_readonly_native_list_selection_and_rendered_focus` exercised OS
Down, readonly rows and focus withholding across chapter/folder/location owners,
but only ordinary geometry. New default/injected192 cases verify actual row
bounds, exact font units, time/title columns, final-row scroll reachability,
selection/data preservation through style refresh and an ordinary sibling that
stays38px before/after popup retirement. All5 native cases pass; the actual old
38px implementation fails the new case. This does not establish physical2x OS-key
input, complete player geometry or Windows behavior.


### Slider geometry and pointer fractions share one conversion

The v100 volume case fails before because injected192 retains92x22 geometry
instead of184x44. PlayerVolumeControl now converts its canonical size, endpoint
insets, thumb/stroke and focus material together, while actual pointer coordinates
and0..100 values stay unscaled. The existing shared matte-track renderer accepts
an explicit unit_scale, default1 for unchanged other consumers. New native cases
assert actual0/50/100 endpoint/midpoint mapping and one callback per request,
5-unit step, exact track/thumb bounds, trace retirement and theme refresh.
Existing three ordinary volume focus tests additionally prove instance isolation
and exact restoration at0/50/100, but previously omitted the injected geometry
and pointer boundary. Five native cases pass after; original failing receipt kept.
PlayerTransportButton retains its native style/input owner; only its18px icon
request now uses window units and existing backing adapter at construction/theme
refresh. Pause/Play image dimensions are checked. Full-player/native-overlay
input and physical Windows remain separate qualification work.


### Conversion must include the clipping parent and pointer insets

v101 progress native cases retain actual400px width while25/75percent draw at100/300,
convert only canonical thickness/minimums and retire timers/traces. The old192
height fails5vs10;5native cases pass after with existing retirement coverage.

v102 extends the existing native-list style derivation used by chapters to actual
archive location/folder constructors. Before two ordinary cases pass and two192
row-height cases fail. After six row/font/selection/end-scroll/sibling checks pass,
but the actual location capture remains clipped because its parent sidebar kept
184px. Row-height assertions alone missed that parent boundary. Sidebar width,
padding and heading font are now converted together in source; native parent-width
and viewport assertions passed in the33-case v103 dependency suite after the lease.
The corrected2x capture was inspected. Preserve the initial clipped capture and
keep physical/platform-wide acceptance separate.

v103 timeline source tests show fixed10px pointer insets seek5.26percent instead of
zero at a doubled visual inset. The existing current-media guard is checked too.
Pointer insets, drawn track/handle/markers and transport spacing/labels/icons now
use one window metrics boundary while measured width/coordinates, durations,
fractions and heatmap bucket count remain unchanged.48focused headless checks
pass. Prepared native tests use the actual transport builder to inspect endpoint
containment, maximal heatmap, measured endpoint mapping and child bounds. They
passed in the33-case v103 dependency suite, including existing ordinary compact
timeline and stale-media retirement checks. Physical/platform input remains open. No global scene-font scaling was added:
ScenePainter text, caller card/footer geometry, artwork bounds and CanvasActions
hit targets must be converted together in their existing owners.


### Menu scale must preserve measured text, row targeting and owner containment

RunHoverMenu kept400px canvas width and31px rows under injected192 even though
its existing ChoicePopover and scrollbar already used the window metrics. Both
above/below192 cases fail before (400 versus800). The same menu owner now
converts its canonical width, rows, padding, scroll increments and text together.
It creates one explicit-size font object for both drawing and ellipsis measurement;
actual canvas coordinates and selected record identities are not scaled. A full
label that fits is preserved even when appending an unnecessary ellipsis would
overflow. No native-window owner or input subsystem was added.

Existing selected-material/Return dispatch proof only covered ordinary geometry
and short labels, so it missed the unit boundary. New actual native cases cover
ordinary/injected192 above/below placement, measured Unicode truncation, exact-fit
labels, final-row scroll/dispatch, image retirement and out-of-viewport dismissal.
Cross-owner ChoiceMenu width/ellipsis and existing scrolled-dropdown/command
lifetime cases pass alongside them:11native cases in6.40s, exact source unchanged
9c68fc59e83cfd7211c1e7bb6aba0510efb270889da6344ef9149474f8a9799f.
Restoring the prior unconditional ellipsis predicate fails the new exact-fit
assertion in a separate bounded native mutation; first helper-indent failure is
retained and the corrected mutation passes.69headless run-identity/material/unit
cases pass. This does not prove OS-key input at physical2x, native tk.Menu, all
platforms, monitor transitions or RunHover focus-return semantics.


### Native dialog units include content, minimum size and failure feedback

Collection Listbox text remained ordinary18px line spacing when an explicitly
admitted192 popup required34px. Its shell/buttons already scaled independently;
the prior ordinary OS-key collection test did not exercise native popup admission
or the font/parent coupling. The actual new default case passes before and the
192 case fails. The dialog now uses its own metrics for fonts, padding and wheel
row units, and reuses bounded_window_size for scaled initial/minimum dimensions.
Centering uses measured coordinates. An ordinary popup remains ordinary even
when its parent has injected192 metrics; production admission is unchanged.

Minimum-size validation exposed a second same-owner issue: feedback wrap width
remained492/984 after available width shrank452/904. Both native cases fail
before the local Configure binding; the description and feedback labels now
wrap to their actual allocated width. Current font/list/selection, screen bounds,
final-item pointer dispatch, failed-save draft/selection retention, minimum-size
feedback/footer and successful retry pass. Existing real OS Return/Escape, nested
grab/input-lifetime, ordinary editor/volume focus and own-window shell cases
provide representative cross-owner checks:8native cases in9.76s;47headless
shell/material/units/annotation cases pass. Initial wrong test-node collection
error is retained separately; the corrected suite ran all8. The scaled minimum
capture visibly retains full feedback and raised Save/Cancel controls.

This is Mac source-native default/injected192 proof; it does not establish
automatic popup DPI admission, physical Windows, mixed monitors, arbitrary long
error text or all dialog contents. Existing failures and original release gates
remain separate.


### Scroll chrome allocation and item endpoints share one units boundary

SceneRail previously reserved12px even when its SleekScrollbar requested16px plus
8px padding under injected192 metrics. Tk allocated the expanding canvas first,
clipping the scrollbar to8px. Existing scrollbar primitive and ordinary Watch/Player
rail tests did not cover this scaled parent allocation. The new ordinary case
passes before; the injected192 case fails on actual allocated scrollbar height.

The existing rail now reserves measured scrollbar request plus converted canonical
padding, and uses its converted14px item gap for content extent and focus reveal.
Caller y/width/height/stride remain measured. Native tests independently check actual
child allocation, exact extent, final target at the viewport edge, one Return dispatch,
measured resize and cache/target retirement. Existing Watch nested-scroll/endpoints
and Player related-row/viewport journeys pass alongside the two new cases:4 native
cases in19.18s with exact unchanged source a5e00067e6de41a590e0afcfd2330d8eb159fd941bfc6dd3ea0b83aa76463b91.
58 headless paging/metrics/material checks pass. Prior failure and ordinary/192
captures are retained. Full caller card/font conversion, physical DPI, actual
Windows and full-player native video/input remain outside this bounded proof.


### Editable dialog content must remain reachable at its bounded minimum

Annotation editor proof exposed both a units boundary and parent allocation issue:
ordinary popup geometry inherited192 parent sizing, injected192 note text remained
18px versus34px, and after conversion the bounded body could squeeze the note to1px.
The existing owner now derives its fonts/spacing/sizing from its own metrics and
wraps explanatory text to measured allocation. The original ordinary430px minimum
also clipped the note below the footer;500px preserves a visible editable area.

The existing ActionDialogSurface scrolling body is admitted only for enlarged
metrics, whose complete document cannot fit the measured screen. Ordinary layout
remains adaptive and non-scrolling. Local FocusIn reveals note/category fields;
footer actions remain protected. The source rule now names this explicit bounded
exception and asserts its admission condition, supported by retained native
failures. Initial unconditional-scroll candidate was narrowed after the existing
source rule caught it. No new input/selection/persistence owner was introduced.

Prior annotation/retry lineage cases covered real durable failures and identity,
but ordinary geometry only. Those12 parameterized cases plus collection OS-key
and4 new geometry cases passed17native cases on the first scrolling candidate.
Final enlarged-only/ordinary-minimum source passes6 native cases (4 annotation,
2 collection), covering both category constructors, exact text/font units, failed
save retention, final-line reach, focus reveal, measured wraps and footer bounds.
47 focused headless cases pass. Earlier source/constructor/minimum failures remain
retained. Physical Windows, native-popup admission, arbitrary heading lengths and
extreme work areas are outside this bounded default/injected192 Mac proof.


The v123 continuation consolidates the repaired editors' duplicate placement into
existing centered_toplevel_geometry(target=popup). The popup owns units/screen
limits; centering uses measured owner coordinates. Existing callers without target
retain their contract, and height_is_measured remains unscaled. Four parent/target
scale combinations and screen clamping extend the headless boundary;51 focused
cases and6 actual editor/collection cases pass. This does not automatically admit
other native windows or prove physical/mixed-monitor placement.


### Measured label width still includes native text insets

Missing-media recovery had the same parent-versus-popup geometry boundary and
unscaled body typography. Default/injected192 across reconnect, legacy folder
review and exact-profile redownload first failed width/font checks. Existing
actual relinked-media recovery covered identity/actions at ordinary geometry,
not separate popup admission. The owner now reuses target-aware geometry and
its own font roles/spacing; requested content height remains measured.

The first converted candidate exposed a second constraint: a ttk.Label wrapping
at its full allocated488px requested491px including native edge insets. Two real
ordinary prompts failed the independent requested-versus-allocated width check.
Local wrap calculation reserves4 canonical pixels, preserving the full copy.
Final10native cases include the6new variants,2existing actual relinked recovery
cases and2collection checks;92focused source cases pass. First precheck's wrong
FONT_UI expectation was corrected to the actual Muted FONT_UI_SMALL role before
runtime work, and both initial receipts remain. No text, action or recovery owner
was replaced. Ambiguous longest-heading/extreme-screen/physical monitor behavior
remains outside this bounded proof.


The first v124 containment pass was insufficient: full default screenshot showed
780px window height while settled content requested342px. The new content-height
assertion fails that candidate. A withdrawn Configure allocation had fed unstable
wrap width into initial requested height. Since this dialog is non-resizable,
its existing owner now sets bounded text width (including native insets) before
measuring height; the dynamic callback is removed. Heading uses that same wrap
boundary. Final12native cases include two ambiguous longest-heading variants and
exact settled height;92source cases pass. Current compact default and wrapped
scaled-heading captures were inspected. Initial overlarge capture remains a
rejected visual sample; containment alone is not layout acceptance.


### Informational word fit and action visibility are separate contracts

Consent's own192 metrics did not reach its benefit font/vector/spacing/layout;
ordinary geometry passed while192 text stayed16px versus32px. After conversion,
footer containment passed but narrow4column text split information across lines.
The existing grid now derives4/2columns from exact measured longest-word width;
enlarged content uses the existing document viewport while choices/privacy remain
protected. Tests reach each benefit row and compare every word to actual wrap
width. A temporary minimum-width0 predicate mutation recreates fixed4column
splitting and is detected; restoration returns2columns. Initial mutation got
corrected by normal Configure and is retained as a failed test attempt.

Six native cases cover both unit modes, two parent sizes, scaled vector bounds,
readable scrolling, repeated-finish single dispatch and focus/grab retirement,
plus existing ordinary native consent/backdrop and collection controls.75focused
source cases pass. No telemetry permission authority or copy changed. Physical
Windows/fractional/mixed-monitor and platform accessibility remain separate.


### Mode-control drawing, pointer midpoint and sibling viewport scale together

ActivityLogText already scaled, while ActivityModeSlider stayed30x116 with a58px
pointer midpoint and its parent retained8px gap. Existing ordinary disclosure and
retired-gesture tests missed the coupled192 boundary. New ordinary case passes;
192 size fails before. The same owners now convert shape/stroke/size/midpoint/gap,
keeping event coordinates and log contents measured/unchanged. Six native cases
cover actual midpoint transitions, released drag, hidden/replaced callback,
keyboard switching, resize, repeated draw stability and lossless log text.39
headless cases pass;7native cases explicitly skip outside the native runner.
This does not qualify the enclosing root layout, physical input or Windows.


### Retained icons must preserve unit dimensions during palette updates

The root loader and its existing live-theme callback both used canonical18/20px
sizes directly while their containing controls could be admitted192. Headless
actual-method cases with real Pillow assets pass ordinary and fail injected2x
before. Both paths now use the same root metrics; canonical per-root cache keys
and retained image identity stay unchanged. The strict image adapter rejects
wrong-sized theme paste, and tests verify a changed tint plus byte-exact reverse
palette restoration.46new/related headless cases pass. Native Tk image/paste,
control containment and actual root theme integration remain pending GUI lease;
this source proof does not qualify whole-app scale or physical backing density.

## Repeated presentation application preserves material ownership (2026-09-19)

Theme/style application must preserve a control's rendering contract and geometry
when the effective palette is unchanged. The v128 root live-theme sequence found
that legacy navigation layouts replaced material elements after first creation.
The existing material owner is retained; obsolete flat layouts were removed.
`tests/test_root_logical_metrics_native.py` now compares actual native control
pixels and dimensions before and after repeated application across root, Archive
and Media navigation aliases. The prior source fails; corrected source passes.
The v93 material/seam tests missed this because they installed styles once and
then changed states. Root integration also checks all header siblings and actual
URL children, beyond the earlier nav-only containment checks. This bounded class
coverage does not establish every theme, every consumer or physical Windows DPI.

## Transparent material must preserve its actual parent backdrop (2026-09-19)

An alpha-correct rounded raster can still form a square visible box when its
canvas uses a flat background over textured ancestors. Shared matte enrollment
now includes the existing URL/rounded-field/PillAction material canvases. Native
root tests expose the real parent independently by lowering each control, compare
transparent corners, remove the projected backdrop as a negative control, and
restore it across state/theme/width changes. v93 raster/seam tests and prior
projected-button tests missed canvas-owned fields because those were not enrolled.
Alpha interpolation and the single physical widget clipping edge are measured
separately; the actual material contribution and interior corners retain a
one-RGB-level bound. Existing projected-button and text lifecycle cases also run.
This proves bounded source-native continuity, not all materials or physical DPI.

### Window units, native artwork, and reachable root controls (v132–v133)

The invariant is that a consumer allocates room for the actual scaled control,
while artwork is sampled at window units times display backing density exactly
once. Shared control metrics alone do not establish caller correctness. Existing
brand source/export tests checked approved pixels and ordinary native headers;
existing field tests checked their own requests, missing the Library scene's fixed
200×40 allocation. New root actual-bound brand/placeholder tests exercise ordinary
and injected192 units; Library tests exercise real child requested/allocated/font
heights. Before fixes both brand cases and10 enlarged Library allocation cases
failed. Integrated18 native tests pass, including thumbnail identity, palette,
failed-render retry, and search child fit. Headless library regression85 pass.
Windows exact79fae9 actual192 measured400×80 outer and242×42 Entry,40px linespace;
physical search/filter/clear and Unicode Forge input passed. Native Mac P3 capture
is converted to sRGB and an independent rendered source reference retains exact
pixel comparison across quantization. Package/Dock/taskbar and full-scene units
remain separate; partial caller repair does not qualify every ScenePainter owner.

The related reachability invariant is that scaling cannot hide an enabled action
below the client viewport. Existing dialog overflow tests covered ActionDialogSurface
and native consent/settings; root Forge did not use that owner. At900×640 injected192,
Output details was unmapped. Enlarged Forge now reuses ActionDialogSurface with
ordinary density unchanged, and reveals only its own descendants on focus. Native
root reachability/header4 pass; lifecycle2 pass covers compact900/1180×640,
Violet/Cobalt, focus down/up, unrelated header focus, descendant wheel routing and
Library/Forge navigation. Shadow lifecycle2 also passed with the new parentage.
The first lifecycle fixture used1180×740, where Details is intentionally removed
in favor of the expanded summary; preserve failed evidence, test the real compact
launcher at1180×640 instead. Source tests alone do not prove physical Windows
scrolling or full-root typography. Resize performance remains parked.

The Library search follow-up also exposed the remap boundary: a caller that owns
its own scene texture must project that texture into nested rounded chrome. The
Forge-only v131 enrollment matrix missed this independent Library scene owner.
Actual Windows inspection proved the backdrop absent; local projection fixed the
missing enrollment. Default-DPI native movement/theme then caught a stale old
position and old image after a same-sized field remap. The production field Map
hook now refreshes projection after mapping; Configure alone cannot establish
that invariant. Actual image black/white draws independently identify transparent
pixels for either native NSImage or PhotoImage. Both scales retain the strict
RGB1 interior oracle, deliberate missing-backdrop failure and exact restoration
across home/all routes, reflow, scroll, themes and retirement. This is representative
nested-owner coverage, not proof that every field in the app is enrolled.

### Activity rows preserve their complete rendered structure (2026-09-24)

The Qt Forge activity and welcome preview shared the correct emblem image, but
both omitted the thin divider drawn by the Tk `ActivityLogText` owner. The old
Qt scene test only looked for the success image URL, so a visibly bare row
passed. `ActivityLines.qml` now owns the divider, emblem and caption as one row.
The rendered scene regression checks their ordered positions in the welcome
exhibit and the divider's presence in Forge. Running that regression against
the previous QML fails; corrected source passes all 76 Qt scene tests. An
1100×740 source capture at `build/qt-port-package/activity-divider-welcome.png`
was inspected. This is representative cross-consumer coverage; exact native
Mac and Genesis packages built after this edit and every activity token variant
remain separate checks.

### Editorial examples render their actual control hierarchy (2026-09-24)

The Qt carousel advertised Library categories, tags and notes with one flat
`Text` item. Tk's preview owner instead composes a category dropdown and two
recessed entries; the shared visual material alone was absent in Qt. The same
flat-text shortcut existed for local video inputs/profile. `FeaturePreview.qml`
now uses the existing StoneButton and StoneField controls for both exhibits,
with illustrative values kept local. A rendered QML interaction test checks
three ordered Library controls, shared field backgrounds, example text and
category-menu opening; it also checks the local-video fields/profile. The test
fails on the prior bare-text QML and passes after the change. The 1100×740
Welcome six-slide matrix and Library/local-video frames were inspected under
`build/qt-port-package/welcome-matrix-5791e51/`. This covers these two exhibit
variants at source density; post-change native Mac/Genesis packages and all
other editorial previews still need qualification.

### Secondary-window close must not veto application Quit (2026-09-24)

After a packaged Mac video entered Floating mode and returned to Watch, both
Command-Q and the native Quit menu left the process running. A process sample
showed the main Qt event loop idle, not a decoder deadlock. The presentation
`Window.onClosing` unconditionally set `accepted=false`; source QML proved its
close still returned false after it was hidden. The floating window now returns
to the embedded surface without vetoing close. The presentation regression
checks close acceptance before showing, while floating, and after returning,
plus the one-player surface binding. It fails against the previous QML and
passes with the fix. This covers the close-event contract for floating and
fullscreen reuse; fresh packaged Mac/Genesis Quit journeys must still pass
before clearing the native lifecycle gate.

Exact `ccaaa17` packaged follow-up: isolated Mac playback then Floating →
Return → Command-Q exited 0. On Genesis, the exact clean-source EXE played,
floated, returned, restored embedded controls and exited 0 after main-window
`WM_CLOSE`. The Windows observer binds executable hash, embedded revision,
PID and visible-window identity in
`build/qt-port-package/genesis-ccaaa17-player-result.json`; the Mac journey
is recorded in `build/qt-port-package/mac-ccaaa17-player-result.json`.
Separate exact-package Mac and Genesis journeys directly closed the active
Floating window, observed embedded controls return and exited 0; receipts
`build/qt-port-package/mac-ccaaa17-direct-close-result.json` and
`build/qt-port-package/genesis-ccaaa17-direct-close-result.json`.
The first Genesis attempt stopped before Play because the saved item displayed
`Resume`; a native UI tree diagnosed the harness label assumption. The retry
accepted Play or Resume and passed without changing runtime code. Full
installed-app lifecycle remains unproven.

### Qt port static guard cleanup (2026-09-24)

The fast repository gate exposed six Bandit `B101` signals in Qt code already
being ported. They were real optimized-Python guard omissions: consent,
Library move, retry status and runtime-smoke branches relied on `assert`.
Those paths now use captured owners or explicit checks. The Qt-scoped Bandit
scan reports zero findings; two prior non-guard signals were checked against
their use and annotated precisely: importing only `SubprocessError`, and an
empty UI identity sentinel. The pre-change Bandit output and new scan are
retained in `build/qt-port-package/fast-be5c85b/engineering-quality/results.json`
and `build/qt-port-package/qt-bandit-after.json`.

The current PySide6 runtime accepts `QImage.fromData(data, "PNG")`; its type
stub incorrectly asks for bytes. Focused tests demonstrated that changing to
`b"PNG"` raises at runtime. The runtime argument is retained with a local
typing exception. Existing cross-owner Qt analytics/Library tests passed
15/15, Qt scene and quality tests passed 78/78, and the full source suite
passed 3688 with 813 skips. The repository fast gate still fails unrelated
format, complexity and mypy signals. Fresh exact `e16ee3e` Mac/Genesis
packages passed focused native routes; earlier `ccaaa17` receipts remain
historical.

The subsequent `aaa4c44` fast rerun is still failed, with 391 complexity
findings and 140 mypy errors. Ruff checks, formatting, Bandit, source tests,
bounded mutations and telemetry isolation passed. Exact receipt:
`build/qt-port-package/fast-aaa4c44/fast-gate.json`. Of the complexity
findings, 26 are in `qt_quick`; the remainder spans older owners. No static
threshold was relaxed and this receipt does not qualify release.
