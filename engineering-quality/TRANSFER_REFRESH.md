# Bounded split-transfer recovery

A completed video can be followed by an HTTP403 when the selected audio URL is opened. Configured yt-dlp HTTP retries do not retry that status. A `/best` selector alternative also does not restart a transfer after a selected stream fails.

The private successor permits one fresh metadata extraction, using the same source, runtime/client policy and in-memory session. It does not reopen cookie files/browser profiles, change credentials, proxies, geographic policy or identities. Existing bounded source-analysis retries, timeout and cancellation polling remain authoritative.

Recovery requires a finished video progress event for the exact selected format and a regular file inside owned staging. The error chain must identify HTTP403 for the originally selected audio URL; unrelated requests, video failure, completed audio and unknown request identity do not qualify. Original metadata marked restricted or DRM does not qualify.

Fresh metadata must preserve source ID and duration and both selected format IDs, codec, dimensions/frame rate, bitrate, audio sample rate/channels/language and DRM state. The completed file must retain its recorded size, timestamp and inode. The refreshed audio URL must differ. The second transfer explicitly reselects the same pair without `/best`; existing yt-dlp staging filenames reuse the completed video. There is only one transfer retry, and another403 ends with a clear error. Missing/changed formats, unchanged rejected URL, restricted metadata, timeout or cancellation stops recovery. No alternate-format substitution or quality downgrade is attempted.

This narrow path applies to split MP4 transfers without selected subtitle acquisition. Audio-only, muxed, caption-bearing and ambiguous failures retain their existing behavior. Successful recovery follows the unchanged validation/atomic-commit pipeline. Incomplete failed runs retain the existing staging cleanup policy; this is not durable resumable-download support. The sharing-lock preservation of validated complete exports from fcced1e is unchanged.

Tests use synthetic metadata and loopback-only media. The real pinned yt-dlp probe completes video, receives403 for audio, obtains synthetic fresh metadata and produces one decodable merged output with one video request. Fixtures cover one-retry bounds, exact quality/access guards, failed extraction, cancellation before/after extraction, unchanged staged video, same-session ownership and the analysis timeout boundary. Logs from an actual user are separate evidence: client version/identity and the cause of403 are not established by telemetry cohorts.

No provider reproduction, native Windows behavior, production telemetry, public source push, dependency update or release is implied by these tests. A fresh provider extraction might return the same forbidden URL or report an access restriction; this implementation deliberately stops in those cases.
