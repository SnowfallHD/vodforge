# Pointer-owned nested vertical scrolling

The release path uses the user-approved simple fallback. When a field has actual vertical overflow, it owns wheel/trackpad input under the pointer, including at top and bottom. Move the pointer outside the field to scroll the page. Non-overflowing fields route immediately to the nearest overflowing ancestor. Current geometry is evaluated on every event, so content growth/shrink and viewport changes do not retain obsolete gesture ownership.

VerticalScrollChain no longer uses gestureActive, mayChain, a 180ms idle timer, or begin/end/momentum classification to transfer input. Vertical movement is clamped once at its owner; horizontal-only input remains unaccepted for existing handlers. Existing keyboard, selection/copy, focus and accessibility declarations are unchanged.

The open app was observed read-only as /Applications/VODForge.app, version0.2.4, revision410dddc48f30e9581aeecd8d65bbab552f489aca, PID8487. Its VerticalScrollChain.qml is byte-identical to the fdec43f6 baseline. This identifies the relevant code; no physical reproduction is claimed.

Same new vertical/selection tests against baseline:23failed/19passed. Patched combined vertical, selection/copy, real description geometry, scroll lifecycle and hidden focus suite:55passed in45.11s. Tests include mouse angle/pixel input, native phase labels, non-overflow at zero/equal/smaller heights, top/bottom, repeated large deltas, pause/momentum/new begin, reversal, pointer outside, content resize, keyboard movement and actual Library description long-to-short transition. Offscreen synthetic input is not native trackpad acceptance.

Qt's generic QML WheelEvent documentation does not list phase, but the pinned runtime probe observes numeric phase values on this WheelHandler event; a missing QML phase is not a demonstrated cause. One immediate synthetic ScrollUpdate did not emit the probe callback. The fallback depends on neither phase exposure nor an inferred timeout.

Private double-scroll work is retained separately at local branch codex/double-scroll-preview-baseline (fdec43f6). That branch preserves the prior mechanism, not a corrected native-qualified experiment. A later private prototype must observe real begin/update/end/momentum and distinguish phase-less mouse input without claiming idle is a reliable gesture delimiter. It does not block this simple release path.

Native acceptance remains pending a coordinated GUI lease. Frozen candidate, installed app and public artifacts are untouched. This commit has no public publication approval.
