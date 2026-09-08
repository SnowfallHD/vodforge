# Native What’s New previews

Every `FeatureHighlight` must declare a `NativePreview`. Screenshot artwork and
crop coordinates are no longer part of the slide contract. Unsupported preview
types fail at construction rather than silently rendering a blurry/blank image.

To announce a feature:

1. Add curated copy and a supported native preview to `HIGHLIGHTS` in
   `yt_downloader/whats_new.py`. Change `SHOWCASE_ID` only when intentionally
   shipping a new showcase, not for routine fixes.
2. Reuse an existing preview, or add a native exhibit in
   `whats_new_feature_preview.py`. Use the same production controls and canonical
   choices as the product. Example values must stay local and must not invoke
   downloads, telemetry, persistence, file pickers, or a playback engine.
3. Keep text and UI chrome native. Raster images are permitted for media content
   only, never for screenshots of controls or text. Exhibits are compact feature
   samples, not replicas of the full app layout.
4. The carousel owns centering, fixed viewport, transitions, caption, and footer.
   Do not resize the card per slide or put navigation inside the exhibit.
5. Exercise all slides at normal and minimum window sizes with
   `VODFORGE_NATIVE_UI_TESTS=1 pytest tests/test_whats_new_ui.py`, and inspect
   captures from `scripts/focus_ui_preview.py --approved --public-fixture
   --whats-new --whats-new-slide N --capture PATH`.

Animated exhibits own and cancel their timers on destruction. Re-rendering the
same slide preserves its widget instance. Escape and X acknowledge the showcase;
app shutdown does not. Adding a preview must not change these persistence rules.

The old `assets/whats-new` screenshots are retained as before/after visual QA
references for this migration, but are no longer bundled or rendered. Both build
scripts bundle only the media artwork used by the native player exhibit.
