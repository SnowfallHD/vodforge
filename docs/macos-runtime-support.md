# macOS runtime support assessment

This is a read-only packaging assessment, not a new build or OS compatibility matrix.

| Inputs/artifact | Apple Silicon minimum | Intel minimum | Evidence |
| --- | --- | --- | --- |
| Official published0.2.5 checked primary tools/libraries |26.0|15.0|Site owner's `/tmp/vodforge-seo-qa/published-package-runtime-targets.json`: Python26/15, FFmpeg+ffprobe26/14, PySide15/15, QtCore13/13. Bounded release-ZIP reads, no execution. |
| Frozen5854619 CI bundles |15.0|15.0|`build/recovery-20261011/candidate-585-minimum-os-audit.json`:460 ARM/462 Intel Mach-O files, no scan errors, highest declared target15.0. |
| Current local Mac build inputs |26.0|Not an Intel toolchain|`build/recovery-20261011/local-build-runtime-minimums.json`: Homebrew Python/FFmpeg/ffprobe26.0; PySide15.0; Deno12.0. |
| Unbuilt successor |Undetermined|Undetermined|Must follow the actual qualified build inputs and final dependency audit. |

No repository support policy or deployment-target setting intentionally selects26. The release workflow uses macOS15 builders for both architectures; the local build defaults to the existing venv and installed tools. The published ARM26 requirement is dependency/toolchain-driven, not a QtCore13 requirement. Current pinned PySide6.11.2 imposes at least15 even with an older bootloader/Python. The generic installer uses Homebrew without a fixed dependency deployment target, so its products can vary by builder.

Reusing this Mac's current inputs for an ARM successor would retain a necessary26 floor. A successor based on compatible macOS15 CI inputs could retain the frozen candidate's declared15 floor, but it has not been built or qualified and must not be advertised as supported now. Neither a lower plist value nor MACOSX_DEPLOYMENT_TARGET can make already compiled newer-target dependencies work on an older system.

Before a final support claim: select and record the build inputs; inspect the final tool/library/plugin targets and load dependencies; verify the intended oldest OS/architecture with the exact package; then publish matching metadata/copy. Declared minimums are necessary conditions, not proof of every supported OS version. No metadata, tools, credentials, build environment or frozen artifact were modified by this assessment.
