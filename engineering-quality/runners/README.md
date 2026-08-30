# Packaged-app UI driver protocol

`./engineering-quality/run packaged-e2e` launches the real packaged VODForge application with an isolated home, a loopback legal-media origin, and a versioned evidence session. It deliberately does not replace VODForge's UI or worker with test doubles.

The current macOS driver is automation-assisted: use a visible desktop driver to perform each instruction in `session.json`, capture the resulting VODForge window, and record the event in the exact listed order:

Use the app's real-user `Command+1`, `Command+2`, and `Command+3` shortcuts to select Forge, Library, and Activity. The Library screenshot must visibly show the completed item; sending `Command+2` is navigation, not evidence by itself.

```bash
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<session>/session.json \
  --event app_visible \
  --screenshot /path/to/current-vodforge-window.png
```

The recorder copies the screenshot into the session, hashes it, timestamps the event, rejects duplicates/out-of-order events, and updates `driver-events.json`. `restart_requested` is the only non-visual control event and can request relaunch atomically:

```bash
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<session>/session.json \
  --event restart_requested \
  --control-action relaunch
```

After `restart_observed`, request the final normal quit with `--control-action finish` on the last visible event or update the session control file through the same driver. A receipt is not accepted merely because event names exist: the collector validates order, timezone-aware timestamps, screenshots and hashes, two clean launches, exact artifact identity, bundled ffprobe readability, pipeline diagnostics, persistent history, stable output hashes, and cleanup.

This recorder standardizes evidence collection; it is not itself a UI automation engine. Until a repository-owned native driver can reliably address VODForge's custom Tk navigation, the tier remains explicitly automation-assisted and reports missing UI evidence as a benchmark gap rather than promoting headless success.
