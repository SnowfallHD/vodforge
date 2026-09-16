# Output ownership and deferred native Help commands

This source patch addresses two user-reported regressions and an adjacent confirmed
output-preservation defect. Release qualification is still pending. Source-native,
headless, and signed packaged evidence are separate tiers.

## Requested output owns its directory

Before this patch, queue/history identity included requested settings but the
physical directory used only provider identity and title. Distinct MP4 or MP3
settings consequently shared a folder. Collision-safe filenames prevented
overwrite but did not preserve item ownership. Original audio used the same
directory owner and is included in the variation matrix.

The existing canonical requested-output contract now supplies a readable directory
label plus a deterministic digest. Custom MP4 labels expose CRF/bitrate and audio
settings; MP3 labels expose bitrate, sample rate, channel layout and artwork mode.
The digest retains distinctions omitted by the short label. Compact paths retain
provider identity and the digest under the existing Windows UTF-16 path budget.
Identical settings retain the same namespace. New variant lookups do not adopt
unscoped legacy folders. Existing durable history can identify an exact legacy
artifact for the same item and requested contract; no new ownership ledger exists.
Existing media, safe staging and collision-preserving commits remain authoritative.

Prior failure evidence: build/variant-help-20260916/variants-before.log
contains three failing separation cases (MP4, MP3, Original), plus a passing
collision-preservation case. The real-worker reliability.duplicate_artifact_transitions
scenario independently observes history, output directories, file hashes, validated
media, staging cleanup and child-process cleanup. Its six additional jobs include
two different MP4 settings whose source fits both, two MP3 bitrates, and identical
repeats. A probe-compatible file is not sufficient proof of identical intent.

Earlier coverage checked filename collisions, media validity and duplicate queue
identity separately; it did not cross the history-to-directory ownership boundary.
A previous sidecar-repair fixture also changed write-thumbnail intent while calling
the attempts identical. It now holds intent fixed and removes only the sidecar.

## Windows native popup lifetime

Windows Tk 8.6 queues the selected Tcl callback until after tk_popup returns.
Destroying the menu in finally deleted the callback before it invoked any action.
The existing EngagementUI owner retains at most one menu, dispatches after idle,
dismisses its own menu before opening a modal, and cancels pending work on
replacement or shutdown. It releases only a grab it owns.

The maintained Windows probe performs native mouse input against a controlled
source Tk application, observes process ownership, actual SupportPanel/WhatsNewPanel
visibility and modal grab ownership, and preserves screenshots and traces.
variant-help-native-matrix-b contains an expected failure with the original module
and passing Feedback, Rate, Welcome, Escape, outside-click and reopen cases.
Deferred native tests cover closure, replacement, repeated requests and a foreign
grab. A root-teardown case was added subsequently and requires a fresh native run.

Earlier callback tests did not reproduce Tk's deferred native command lifetime.
The source-native probe is not a signed packaged-app receipt. The fixed QA geometry
is deliberately bounded; it must never be used as blind arbitrary desktop input.

## Optional output shares the same preservation boundary

The surrounding audit reproduced optional metadata and thumbnail writes following
leaf symlinks and overwriting unrelated files. Reuse lookup also adopted redirected
child folders. sidecar-before.log preserves six failing cases, including independently
read outside-file bytes. Existing safe media commit tests did not exercise sidecar
writers or reuse selection.

Optional output now stages through the existing safe_output owner and commits with
its no-descendant-redirection checks. Workers pass the original selected root.
The selected root itself may be a user-chosen symlink. Reuse rejects linked children
even when their targets remain inside that root. Coverage includes real JSON/JPEG
writes, leaf and ancestor redirects, selected-root links, interrupted encoding,
and a directory swap after encoding but before commit. Failure preserves existing
bytes and cleans private staging. Reuse validation tests isolate the media validator;
real-worker coverage supplies actual media proof separately.

These are representative ownership/lifecycle variations, not proof of every
filesystem race or UI interleaving. Windows reparse behavior and final signed bytes
still require the platform and packaged gates. No publication has occurred.
