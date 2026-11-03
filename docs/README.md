# VODForge documentation

## Current

| Topic | Document |
| --- | --- |
| How the app is built and who owns what | [Architecture](architecture.md) |
| Screens and navigation | [Current design](current-design.md) |
| Rules for every new UI feature | [UI components](ui-components.md) |
| Brand artwork | [Branding](branding.md) |
| MP4 export presets | [Export presets](export-presets.md) |
| Updates and Repair | [Update handoff](update-handoff.md) |
| Releasing a version | [Releasing VODForge](release.md) |
| Telemetry the app sends | [Telemetry features](telemetry-features.md), [desktop analytics contract](posthog-desktop-contract.md), [readiness and limits](telemetry-readiness.md) |
| Welcome, feedback and ratings | [Welcome, feedback and reviews](welcome-feedback-reviews.md) |
| Approved design references | [references/](references/) |

Testing and release evidence live in the
[engineering-quality harness](../engineering-quality/README.md).

## History

Past work, kept as a record. Each file starts with a note on what it covers and
what replaced it.

| Topic | Document |
| --- | --- |
| The macOS header and menu bar (Sept–Oct 2026): what was tried, why it failed, the fix and lessons | [macos-header.md](history/macos-header.md) |
| Architecture while the app had its Tk interface | [architecture-tk-era.md](history/architecture-tk-era.md) |
| UI component notes from the Tk interface | [ui-components-tk-era.md](history/ui-components-tk-era.md) |
| Removing the Tk interface (Oct 2026) | [qt-retirement.md](history/qt-retirement.md) |
| How the Tk-era player chose libVLC | [playback-backend-evaluation.md](history/playback-backend-evaluation.md) |
| macOS minimum-version evidence | [macos-runtime-support.md](history/macos-runtime-support.md) |
| Quiet-AAC validation fix (Sept 2026) | [failure-details-aac-validation.md](history/failure-details-aac-validation.md) |
| Telemetry metric audit (Sept 2026) | [telemetry-metric-audit.md](history/telemetry-metric-audit.md) |
| Diagnostic telemetry plan (implemented Oct 2026) | [diagnostic-telemetry-plan.md](history/diagnostic-telemetry-plan.md) |
| Desktop PostHog integration log | [posthog-local-integration.md](history/posthog-local-integration.md) |
| Output ownership and deferred Help commands | [export-variants-help-menu.md](history/export-variants-help-menu.md) |
| Tk-era What's New previews | [whats-new-native-previews.md](history/whats-new-native-previews.md) |

Engineering investigations and checkpoints are in
[engineering-quality/history/](../engineering-quality/history/); the full record of
changes and checks is the [change and test log](../engineering-quality/change-and-test-log.md).
