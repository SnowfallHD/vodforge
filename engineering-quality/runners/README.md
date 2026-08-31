# Packaged-app UI driver protocol

`./engineering-quality/run packaged-e2e --candidate <candidate-artifact.json>` freshly extracts the frozen candidate ZIP, then launches the real packaged VODForge application with isolated state, a loopback legal-media origin, and a versioned evidence session. It deliberately does not replace VODForge's UI or worker with test doubles.

Do not drive the app until `session.json` reports `driver_ready: true`. At that point the direct child PID, process group, executable path/hash, full bundle tree, runtime version, environment, state paths, nonce, and app-written startup attestation agree. The window title contains the launch-specific token from `current_launch`.

The current macOS driver is automation-assisted: use a visible desktop driver to perform each instruction in `session.json`, capture the resulting VODForge window, and record the event in the exact listed order:

Use the app's real-user `Command+1`, `Command+2`, and `Command+3` shortcuts to select Forge, Library, and Activity. The Library screenshot must visibly show the completed item; sending `Command+2` is navigation, not evidence by itself.

```bash
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<session>/session.json \
  --event app_visible \
  --screenshot /path/to/current-vodforge-window.png \
  --window-pid <current_launch.pid> \
  --window-owner-pid <CoreGraphics-owner-pid> \
  --window-id <CoreGraphics-window-id> \
  --window-title-token <current_launch.window_token>
```

The recorder independently queries CoreGraphics for that native window ID and accepts the event only when the onscreen application-layer window's owner PID and exact nonce-bearing title match the attested launch. It then copies the screenshot into the session, hashes it, timestamps the event, rejects duplicates/out-of-order events, and updates `driver-events.json`. `restart_requested` is the only non-visual control event and can request relaunch atomically; it still requires the current launch/window identity arguments:

```bash
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<session>/session.json \
  --event restart_requested \
  --window-pid <current_launch.pid> \
  --window-owner-pid <CoreGraphics-owner-pid> \
  --window-id <CoreGraphics-window-id> \
  --window-title-token <current_launch.window_token> \
  --control-action relaunch
```

After `restart_observed`, request the final normal quit with `--control-action finish` on that visible event. A receipt is not accepted merely because event names exist: the collector validates order, timezone-aware timestamps, native window receipts, screenshots and hashes, two clean launches, immutable candidate/archive/bundle identity before and after the journey, bundled ffprobe readability, pipeline diagnostics, persistent history, stable output hashes, and cleanup.

This recorder standardizes evidence collection; it is not itself a UI automation engine. Until a repository-owned native driver can reliably address VODForge's custom Tk navigation, the tier remains explicitly automation-assisted and reports missing UI evidence as a benchmark gap rather than promoting headless success.
