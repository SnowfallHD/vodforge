# VODForge release gate

The gate binds one source commit to one immutable ZIP and never treats a rebuild as equivalent. It preserves the existing architecture and complexity findings as visible debt; only explicitly reviewed debt is nonblocking.

## Behavioral acceptance prerequisite

Apply the [harness-wide evidence and acceptance standard](HARNESS_GUIDE.md)
before private review promotion or public release. Required in-flight evidence,
independent assertions, and unresolved user failures are acceptance blockers;
settled-state passes and test totals do not waive them. NORMAL/DEEP evaluation now adds required interaction-coverage checks and defaults
unreviewed behavioral scenarios to unproven. This initial migration blocks
promotion; it does not claim domain coverage is implemented. The private-install
entry point uses the same blockers. Detailed domain evaluator enrollment remains
incomplete; record and enforce those remaining gaps explicitly.
A known-rejected installed artifact remains failed acceptance evidence.

## Required telemetry journey

Every public release additionally requires [the preview-D1 telemetry gate](TELEMETRY_RELEASE_GATE.md)
on macOS and Windows using the final signed artifacts. Telemetry-off-only E2E is
not sufficient. Use `packaged-e2e --profile telemetry --telemetry preview` for the positive journey and
retain separate denied-consent/disabled negative checks. Both platform readbacks
are mandatory inputs to the release receipt; missing evidence blocks publication.

## Profiles

FAST / pre-commit:

```sh
./engineering-quality/run fast
```

FAST runs the repository and harness self-tests, compilation, Ruff, formatting, mypy, Bandit, Vulture, dependency checks/audit, and the bounded mutation scenario. Complexity signals remain in the receipt without making an otherwise clean FAST run fail.

NORMAL / pre-merge:

```sh
./engineering-quality/run normal --output-dir engineering-quality/reports/<normal-id>
```

NORMAL includes FAST evidence plus all normal headless production-pipeline correctness, reliability, concurrency, lifecycle, and security scenarios.

DEEP / pre-release:

```sh
./engineering-quality/run deep \
  --soak-jobs 100 \
  --e2e-result engineering-quality/reports/<e2e-id>/e2e-result.json \
  --output-dir engineering-quality/reports/<deep-id>
```

DEEP requires the 100-job retained-object/lifecycle contract, deep/public/fault coverage, and a separately completed packaged E2E receipt bound to the exact candidate.

## Immutable candidate workflow

For a local development candidate, build without publishing:

```sh
VODFORGE_PYTHON=.venv/bin/python \
VODFORGE_UNSIGNED_REVIEW=1 \
./build_and_package_macos.sh <version>-dev
```

Freeze that exact ZIP and record the clean source commit, build argv/environment, machine, bundle tree, dependencies, signing state, and archive hash:

```sh
./engineering-quality/run candidate \
  --archive dist/release/VODForge-macOS-arm64-v<version>-dev-unsigned-review.zip \
  --version <version>-dev \
  --artifact-policy development \
  --build-command "./build_and_package_macos.sh <version>-dev" \
  --build-env VODFORGE_PYTHON=.venv/bin/python \
  --build-env VODFORGE_UNSIGNED_REVIEW=1
```

The command copies the ZIP to a private, read-only candidate directory. Packaged E2E freshly extracts that frozen copy; it does not drive `dist/VODForge.app` or the first inspection extraction:

```sh
./engineering-quality/run packaged-e2e \
  --candidate engineering-quality/candidates/<candidate-id>/candidate-artifact.json \
  --profile smoke \
  --output-dir engineering-quality/reports/<e2e-id>
```

The runner fails before UI control if another VODForge process exists or if artifact, PID, executable, version, environment, state paths, app startup attestation, native window owner/title, or candidate hashes do not agree. It only cleans the process group it launched.

After FAST, NORMAL, packaged E2E, and DEEP, bind the receipts:

```sh
./engineering-quality/run release-receipt \
  --candidate engineering-quality/candidates/<candidate-id>/candidate-artifact.json \
  --fast-result engineering-quality/reports/<fast-id>/engineering-quality/results.json \
  --normal-result engineering-quality/reports/<normal-id>/results.json \
  --deep-result engineering-quality/reports/<deep-id>/results.json \
  --e2e-result engineering-quality/reports/<e2e-id>/e2e-result.json \
  --telemetry-result engineering-quality/reports/<mac-journey>/telemetry-result.json \
  --telemetry-result engineering-quality/reports/<windows-journey>/telemetry-result.json \
  --output-dir engineering-quality/reports/<receipt-id> \
  --command "./engineering-quality/run fast ..." \
  --command "./engineering-quality/run normal ..." \
  --command "./engineering-quality/run packaged-e2e ..." \
  --command "./engineering-quality/run deep ..."
```

The JSON and Markdown receipt retain `passed`, `failed`, `skipped`, and `unproven` as distinct states. Any required non-passing state blocks publication.

## Development versus public release evidence

An ad-hoc-signed development candidate can prove current-source application behavior, but its receipt remains ineligible for public release. It does not prove Developer ID identity, Apple notarization, stapling, or Gatekeeper acceptance.

For a public macOS candidate, the byte-changing order is:

1. start from the clean source commit;
2. build the app;
3. apply the final Developer ID signature;
4. submit for notarization;
5. staple the accepted ticket to the app;
6. verify strict code signing, identity/team, stapling, and Gatekeeper;
7. create the final distribution ZIP exactly once;
8. freeze and hash that ZIP as the candidate;
9. freshly extract and run packaged E2E against that exact ZIP;
10. re-hash the frozen ZIP and publish only those same bytes.

Signing or stapling after E2E creates a new artifact and invalidates the candidate receipt. The release process must not rebuild or re-archive after the tested hash is established.

Schemas: [candidate-artifact.schema.json](schemas/candidate-artifact.schema.json), [release-receipt.schema.json](schemas/release-receipt.schema.json), and [run-result.schema.json](schemas/run-result.schema.json).

Schema-v2 telemetry additions must satisfy the full feature/action, attempt/retry,
export-dimension and updater-outcome requirements in
[TELEMETRY_RELEASE_GATE.md](TELEMETRY_RELEASE_GATE.md). Deploy the compatible D1
migration and backend before the desktop release. A passing serializer probe or
telemetry-disabled app smoke cannot substitute for final-artifact preview-D1 UI
journeys on both Mac and Windows.


## Recovery and presentation regression gates

The five classes in [RECOVERY_REGRESSION_CLASSES.md](RECOVERY_REGRESSION_CLASSES.md) are mandatory NORMAL/DEEP scenarios. Run the maintained before/after source contract and retain exact-artifact code binding separately from native/packaged GUI evidence. Source checks never waive the packaged journey gate.


## Private review installation

Use the maintained private installation entry point; do not repeat ad-hoc bundle
swaps. It evaluates NORMAL's required checks including interaction coverage,
packaged journey and exact candidate bindings, negative-control prerequisites,
and the checkout-owned acceptance/user-reported-defects.json ledger before any
extraction or installed-app mutation:

~~~sh
./engineering-quality/run private-install \
  --candidate engineering-quality/candidates/<id>/candidate-artifact.json \
  --normal-result engineering-quality/reports/<normal-id>/results.json \
  --e2e-result engineering-quality/reports/<e2e-id>/e2e-result.json \
  --negative-controls engineering-quality/reports/<id>/negative-controls.json \
  --target /absolute/path/to/VODForge.app
~~~

The installation must be closed. The command preserves a uniquely named adjacent
rollback app, does not launch the replacement, and does not touch user data.
It uses the existing immutable-candidate verifier and materializer, including
fresh tree verification. A private install confers no public release eligibility.

Current migration state: behavioral coverage is still unproven, so this entry
point blocks current candidates. The five user-reported defects remain open in
the ledger even where a focused source check improved. Closing one requires
verified full source-manifest binding and its negative-control requirement mapping.
Commit identity alone is insufficient for dirty source trees. The normal runner
captures source content before/after checks; candidate creation and materialization
propagate that identity. Private installation rejects a changed source snapshot
or a different candidate between preflight and namespace mutation.

The native_channels_v1 negative evaluator currently recomputes three narrow
invariants from ordered observations: duplicate artwork bounds, layout updates
while the drag is held, and geometry movement after release. It rejects invalid
or incomplete traces and requires a distinct known-bad source identity. It does
not certify compositor frames, physical input, scrolling, transitions, or other
domains. A supplied status or hash alone does not prove detection. Do not remove the default coverage blockers before
those evaluators and their integration tests are complete.


Source-manifest labels are checked against the canonical manifest payload in both
the candidate and NORMAL receipt. Materialization must return the same manifest
identity that passed preflight. Matching commit or hash strings alone do not
qualify changed payloads.
