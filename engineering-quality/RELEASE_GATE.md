# VODForge release gate

The gate binds one source commit to one immutable ZIP and never treats a rebuild as equivalent. It preserves the existing architecture and complexity findings as visible debt; only explicitly reviewed debt is nonblocking.

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
