# Completed-media sharing locks

A synthetic Windows sharing error at final commit reproduced two gaps on04d69e6: no retry for a short lock, and unconditional deletion of already validated staging media after a persistent lock. This does not identify who held the reported file; OneDrive-shaped local directory tests do not simulate OneDrive syncing.

The commit wrapper retries only OSError winerror32/33, at most five attempts with nominal delays0.1/0.2/0.4/0.8seconds. Each attempt repeats full existing containment/reparse/collision checks. Backoff polls cancellation every50ms. Access denial, missing files and unsafe redirects are not retried; no overwrite or copy fallback is added.

The download worker preserves remaining validated staging media only when final commit fails with a sharing violation. It reports the retained directory in activity, continues existing batch-failure policy and does not count failed commits as successes. Completed retention detaches only an owned staging entry from durable abandoned-run cleanup after child ownership has settled. Partial downloads and validation failures still clean up. Retained media is manually recoverable, not an automatic resume promise. If durable retention ownership cannot be saved, the diagnostic reports it; later crash recovery may still own that transaction.

FFmpeg already calls wait before returning and child-finalization runs before final commit; no evidence establishes an owned process as the reported lock holder.

Source requirement and exact04d69e6 frozen runtime smoke both identify yt-dlp2026.08.19. VODForge source analysis retries only transient status408/425/429/5xx. The upstream pinned HTTP downloader rethrows403 rather than retrying as5xx. There is no new403 refresh/bypass patch: logs and exact failing URL/app build remain needed. Primary source: https://raw.githubusercontent.com/yt-dlp/yt-dlp/2026.08.19/yt_dlp/downloader/http.py

Regression evidence: initial five-case source baseline4failed/1passed; expanded final596passed across download worker, safe output, process lifecycle, run recovery, original audio, local conversion and archive file operations. Ruff/format/diff/mypy169source files pass. Native Windows holding-process/OneDrive tests remain unrun; no private successor package or full FAST gate is claimed.
