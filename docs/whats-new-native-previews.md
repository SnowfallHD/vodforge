# Native What’s New previews

Release editorial selection: `SHOWCASE_MODE` in `whats_new.py` selects
`whats-new` or `did-you-know`. Only change it when requested for a release;
assign a new `SHOWCASE_ID` when enabling that release's announcement. The tip
replaces release highlights rather than adding a second startup popup. Both use
the same seen setting, consent/modal readiness gate, and fresh-user welcome
suppression. Routine updates do not reset acknowledgement. The prepared tip is
not enabled by adding its catalog entry alone. The next release selects
`whats-new` with ID `output-settings-presets-v1` and only the updated output
settings highlight. Its native Optimize for selector uses the production choices
and descriptions with local-only state; it does not change saved preferences.
The previous YouTube-access tip remains available in the tip catalog.

The expanded access exhibit uses an embedded production ChoiceMenu with three
visible rows (scroll for other browsers). Browser/Chrome are local examples only.

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
   Each exhibit owns a compact content envelope: its preferred width and height
   must describe the visible content, not an oversized empty production viewport.
   Center that envelope horizontally and vertically in the preview. Internal
   text may remain left-aligned for readability; unused trailing space must not
   make the visible group appear left-heavy. Apply this to welcome slides too,
   including interactive states. Pagination stays centered independently of
   secondary dismissal text, which belongs at the footer's trailing edge.
5. Exercise all slides at normal and minimum window sizes with
   `VODFORGE_NATIVE_UI_TESTS=1 pytest tests/test_whats_new_ui.py`, and inspect
   captures from `scripts/focus_ui_preview.py --approved --public-fixture
   --whats-new --whats-new-slide N --capture PATH`.

Animated exhibits own and cancel their timers on destruction. Re-rendering the
same slide preserves its widget instance. Escape and X acknowledge the showcase;
app shutdown does not. Adding a preview must not change these persistence rules.
The welcome activity-mode exhibit reuses ActivityDemo at 200 ms per phase
(a three-second loop), automatically switching the real slider and activity view.
It remains offline and cancels its loop when the slide is removed.

The Age Restricted Content welcome exhibit uses the shared access choice catalog:
Public, Browser, cookies.txt. Browser and Chrome are illustrative local selections,
not changes to the saved Public default or authorization to read browser storage.
Its browser dropdown uses the production choices and stays inside a compact,
centered content envelope. Copy must not promise to bypass age verification.

The old `assets/whats-new` screenshots are retained as before/after visual QA
references for this migration, but are no longer bundled or rendered. Both build
scripts bundle only the media artwork used by the native player exhibit.
