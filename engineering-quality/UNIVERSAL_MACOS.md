# Private universal2 implementation

Public architecture-specific ZIPs and website pointers stay unchanged. This work
is not a release gate waiver. Public support remains native Apple Silicon26+ and
Intel15+ until intended-host compatibility is separately qualified.

## Implemented owners

- `scripts/build_universal_macos.py`: inspect native input slices and per-slice
  deployment floors; reject missing inputs/thin natives/dirty source; construct a
  fresh private PyInstaller `--target-arch universal2` build from a selected
  interpreter/environment and helper directory. No package has yet been built.
- `scripts/build_macos_dmg.py`: refuse wrong/thin bundles before staging; require
  strict signature/staple; create branded Retina background, Applications link
  and HFS+ Finder layout with no Finder/AppleScript control. Convert and verify
  compressed image. A real universal application DMG is not available yet.
- Updater: prefer exact-version `VODForge-macOS-universal2-vVERSION.zip`; fall back
  to existing architecture-specific names. SHA/trusted-URL/tampered partial-file
  guards remain. DMG is the human installer; ZIP remains the updater transport.

Run read-only input qualification with:

```
python -m scripts.build_universal_macos --input PATH --report REPORT.json
```

The future private build entry is `--build --source CLEAN_SOURCE --python
UNIVERSAL_VENV/bin/python --tools QUALIFIED_HELPERS --output FRESH_OUTPUT --report
REPORT.json`. The input check is conservative: currently every inspected native
file must contain both slices. It does not yet implement a per-architecture
dependency graph permitting architecture-specific shared libraries. Full bundle
closure, runtime smoke and physical/native acceptance remain separate gates.

## First implementation evidence

`build/universal2-implementation-20261017/` retains source regressions, official
Python installer/hash/trust evidence, extraction, corrected ARM/Rosetta runtime
logs, hash-verified PyPI input wheels and assembled dependency wheels, import
probes, helper refusal, and DMG layout test metadata. Python remains task-local;
no system installer ran. Loader environment variables apply only to these owned
headless processes. Intel/Rosetta probes are not physical Intel acceptance.

Tests cover new asset selection plus existing Windows/Mac download SHA checks,
tampered cleanup, foreign/empty/thin/nested native inputs, per-arch OS floors,
dirty source refusal, explicit universal recipe construction, wrong/thin DMG
refusal, preserved output, and Retina layout geometry. Generalized invariant:
an architecture label or dual-arch launcher does not establish a compatible
native dependency closure. Existing thin-package passes did not cover that class.

## Remaining engineering work

1. Complete the universal environment and native helper closure. Existing helpers
   are thin; ARM x265 uses ABI217 and Intel ABI216. Do not blindly merge or call
   those trees a qualified universal closure. Rebuild matching dependency inputs
   or implement and test an explicit per-architecture dependency layout/graph.
2. Assemble a clean-source universal app, audit every loaded dependency per
   architecture, and verify the actual frozen source/resource bindings.
3. Preserve signing policy. Existing signing script applies Intel's executable
   memory entitlement whenever any x86_64 slice exists; do not silently extend
   that permission to ARM. A compatible slice-aware signing policy requires
   verification before signing a universal candidate; no new permissions are
   authorized by this task.
4. Build/sign/notarize a real application DMG, inspect actual Finder rendering and
   drag-to-Applications, and qualify both architectures and intended OS minimums.
   The retained layout image has an empty fictional .app and is NOT distributable.
5. Keep legacy architecture asset names/checksums available through a tested
   official0.2.5 update migration. Existing released clients cannot discover only
   a universal asset. Identical qualified bytes under legacy aliases are a future
   migration option, not an executed upload. Test manual/automatic/Repair/data
   preservation and subsequent universal updates before site adoption.

No new user credentials, macOS grants, spending, production telemetry or public
publication is part of this implementation. Remaining helper work is engineering
work within the authorized scope, not a request for Cooper to solve the inputs.
