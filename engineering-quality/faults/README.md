# Fault model

Faults are injected outside production code through a loopback HTTP server, controlled output-directory state, process signals, and deliberately failing child executables. The harness does not replace yt-dlp, FFmpeg, ffprobe, VODForge staging, or VODForge commit logic.

The first version covers deterministic HTTP failure/retry, slow transfer cancellation, malformed input, unwritable destinations, child failure, stale staging detection, duplicate/concurrent jobs, Unicode/path attacks, and symlink traversal. Deep-profile extensions are documented in the main README.
