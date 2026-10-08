# Library reflow fixture isolation

The Library thumbnail reflow probe tests painted artwork during scrolling and resizing. It already marks welcome and What’s New as seen. It must also mark the unrelated social invitation dismissed so the normal idle invitation cannot dim the canvas while pixel samples are collected.

On unchanged 9c862eb, an instrumented 2,000-item / 1,900-scroll probe observed the automatic social invitation at 11.880 seconds and visibility at frame 1. It produced 1,518 mismatched samples; every mismatched frame had the modal visible. The first incorrect color was #34577b, matching the ARM CI failure. The baseline screenshot shows the actual social invitation over Library.

With only `bridge._settings["social_invitation_dismissed"] = True` added beside existing editorial fixture state, the same diagnostic completed 153 frames over 19.441 seconds with no modal and no pixel mismatch. Production scheduling and popup behavior are unchanged. All existing assertion ASTs are identical.

Evidence is preserved in the release owner’s `qualification-now/social-fixture-fix` directory: `CAUSAL-RESULT.json`, `ASSERTIONS-UNCHANGED.json`, baseline/fixed proof and screenshots, and test logs. Focused reflow plus What’s New tests passed (23 cases). Full local Mac gates passed: backend 4,002 passed / 817 skipped (128.91s); Qt 560 passed / 9 skipped / 2 warnings (503.30s); scene 168 passed (109.30s). The exact maintained three-batch commands are preserved in `full-mac-gates-supported.sh`; execution exited 0. These are local Apple Silicon gates, not a new Intel artifact qualification.
