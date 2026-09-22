# Recovery and presentation regression classes

These five scenarios are mandatory in the NORMAL and DEEP release gates and run
by default in the engineering-quality scenario registry. Missing, skipped,
failed, timed-out, or reduced case coverage fails the scenario. Each receipt
binds the production Python tree before and after execution and hashes its
maintained probes; changing production sources during a run invalidates it.

| Required scenario | Defect class and maintained coverage | Owner |
| --- | --- | --- |
| unit_static.recovery_canonical_facts | Repeated destination updates must read canonical facts, never ingest label/value display projections. Windows, POSIX and Unicode paths; replacement and repeated update. Actual native resize companion: test_forge_destination_stays_single_across_resizes_and_path_changes. | FactsText snapshot and Forge coordinator |
| unit_static.recovery_selected_item | One selected missing item cannot replay its playlist/batch; unsafe/missing identity fails closed; admission must precede exact history retirement and migration telemetry. | LibraryMediaRecoveryOwner and admission owner |
| unit_static.recovery_retired_presets | Original saved intent is validated before migration. Retired MP4 presets become Everyday; current CTV, Custom, modern presets and audio settings retain their intent. Incomplete profiles require review, with recognized retired labels preselected to Everyday. | LibraryMediaRecoveryOwner |
| unit_static.recovery_bounded_expansion | A validated recovery uses captured playlist organization and one selected input without rereading the playlist. Ordinary downloads and mismatched/bulk inputs retain provider resolution; per-item format preflight remains mandatory. | Execution source-expansion owner |
| unit_static.recovery_draft_coherence | Actual headless Tcl traces must keep visible choice, hero, hint, facts and submitted preset coherent. Explicit draft edits work; source change, clearing and send retire the draft; returning to the old source cannot revive it; saved preset/destination defaults remain unchanged. | Recovery session owner; Forge renders effective state |

Run one through the ordinary harness, for example:

~~~sh
./engineering-quality/run normal --scenario unit_static.recovery_selected_item --output-dir build/recovery-selected
~~~

Run the full focused contract without opening GUI windows or media/network work:

~~~sh
PYTHONPATH=engineering-quality:. python -m quality_harness.recovery_contract --output build/recovery-contract
~~~

For a before/after comparison, use the same maintained harness/probes with explicit,
immutable source trees. Each run needs a fresh evidence directory:

~~~sh
PYTHONPATH=engineering-quality:. python -m quality_harness.recovery_contract --source /absolute/before/source --output build/recovery-before
PYTHONPATH=engineering-quality:. python -m quality_harness.recovery_contract --source /absolute/candidate/source --output build/recovery-after
~~~

The older artifact's extracted code must separately match the before source,
and the candidate's extracted code must match the candidate source. Those
bindings establish source equivalence; they do not turn these controlled
behavioral probes into packaged GUI tests. Retain actual old-artifact screenshots,
source-native before/after resize receipts, and independent replays alongside
the contract receipts. Run the same-candidate native/packaged journey when the
user's app is available for testing. A source pass cannot waive that gate.

Telemetry uses the bounded missing_media/preset_migrated action with
preset=everyday,input_kind=single only after successful direct-redownload
admission. Declined admission emits neither acceptance nor migration. No source
URL, title, path, or old profile text is collected. Python and backend vocabularies
must match, and the backend must reject arbitrary/private dimensions.

Policy remains in LibraryMediaRecoveryOwner: original-intent validation,
selected-item reconstruction, retired/current preset classification, and session
draft lifetime. The dialog derives copy from its immutable plan. Forge coordinates
selection/admission and reads one effective-preset accessor for presentation and
submission. Serialized records retain original authority until validation.
The existing large app.py remains architecture debt; this work does not claim
that debt is eliminated.

## Durable writer and cold-reader agreement

The durable_roundtrip class is enrolled with the existing recovery runner.
Every newly executable source must survive privacy-preserving serialization and
cold deserialization. Mixed batches commit all validated entries or leave the
prior journal byte-for-byte unchanged; silently dropping an entry is a failure.
A separate historical fixture path directly writes old schema records so stricter
new admission never substitutes for backward recovery coverage.

The writer guard is shared by ActiveRunStore.begin and replace_queue.
Terminal-attempt and history metadata serialization remains tolerant. The only
production DownloadJob constructor is the validated app submission path; the
deserializer is the other constructor. Five production persistence paths were audited: active job, active queued jobs,
queue replacement, terminal-attempt record and app history metadata. The first
three now call the strict executable adapter; terminal/history paths retain the
tolerant serializer. The serializer itself has three direct production callers:
that adapter, terminal-attempt recording and app history metadata. No local conversion owner constructs DownloadJob.

Three deterministic seeds vary one-to-six-job queue contents, invalid-source
position and failure class over 24 iterations each. New store instances read the
committed journal; every rejected mutation preserves bytes. Focused invalid
sources cover empty, unsupported local scheme, malformed port, control characters
and length boundary. Thirteen cases failed before the writer guard; 59 combined
writer/history/recovery/observation tests passed after it. Older malformed fixture
construction was changed to direct old-record writes because the current writer
now correctly rejects it; reader assertions were retained.

New local records carry bounded retry_source_state/retry_source_states values:
retained, sanitized, missing_original, unsupported_scheme or invalid_source.
An absent/unrecognized status reads as legacy_unknown; do not infer the original
failure cause from a legacy blank source. These fields do not retain rejected
input or restore secret query parameters. Their local persistence is not yet
end-to-end telemetry qualification. The live incident's original writer branch
remains unknown despite the confirmed journal lockout and successful workaround.


### Runtime refusal observation

The durable_roundtrip scenario additionally enrolls real invalid-source and
write-denial refusals at run admission and queue replacement, disabled consent,
observer/diagnostic faults, and repeated-intent identity checks. Its required suite
is now 39 cases; exact nodes, unchanged source/probe hashes and JUnit completion
determine success, not the count alone.

Four pre-change cases preserved journal bytes but emitted no event. The runtime
observer now reports refusal without poisoning startup availability. The 79-case
focused run covers related owners and harness checks. Fourteen actual producer
fixtures passed authenticated local backend ingestion/readback and duplicate/privacy
checks; the full backend suite passed 243 checks. These are source/local-backend
receipts, not production deployment or complete telemetry qualification. Preserve
runtime-journal-before-v8.log and the versioned after logs.
