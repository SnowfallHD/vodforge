# Qt retirement change set

Branch:qt-retirement, canonical checkout only. Frozen signed5854619 is immutable and independently assessed. Source cleanup is a successor change; no new build or publication is authorized by these edits.

Completed increments:

-7ca33fc extracts download_service, worker_events, product_theme, visual_chrome/materials, button_metrics and Library recovery prompt. Qt no longer imports app.py or a Tk presentation module.212 unchanged service definitions have AST provenance;24 existing affected controls pass. Qt entry import fails with Tk blocked on prior source and passes after, without creating GUI.
-142b582 makes main.py and both packaging defaults Qt, excludes Tk/ImageTk/legacy libVLC, removes Tk installer prerequisite and stale docs/comments. Ordinary/explicit imports pass with Tk unavailable; both build-script syntax checks pass. No package built.

Remaining source retirement:

1. Retire legacy app.py widget owner after migrating its pure-helper consumers to download_service. Keep worker, media, history, run-state and durable schemas unchanged. Do not keep a fake DownloaderApp class solely to inflate old test counts.
2. Version-remove legacy Tk UI modules using their existing Qt owners (Main.qml, LibraryScene/Detail/FolderInspector, WatchScene, PlayerScene/Overlay, RunDeck, update_session, support, Qt native window integration). Preserve source rollback in Git, not extra copies.
3. Remove Tk-only platform_services functions and Linux Tk font aliases; keep shared filesystem/tool discovery/trash/diagnostics functions. Shared pure layout helpers may stay when used by maintained Qt; stale Tk docs are not a runtime dependency.
4. Migrate shared service tests and individually review mixed widget/worker tests before retiring widget-only cases. Inventory identifies53 direct Tk source modules,262 legacy widget methods and87 app-consumer testfiles;58 reference legacy widget methods. These counts are an inventory, not a gate or claim of incomplete Qt features. Preserve data-recovery, annotations, cancellation, metadata, updater and privacy invariants in Qt/service tests; no blanket skip or deletion of useful mixed tests.
5. Retire obsolete Tk/libVLC-only runners/workflows/dependency declarations; redirect maintained harness imports to neutral owners. Do not develop new diagnostics or click/coverage mapping.
6. Validate static imports and package exclusions with Tk unavailable, affected source regressions and representative Qt scene controls. Native successor validation must use the reviewer-coordinated desktop later; frozen585 review cannot qualify these source changes. Build only after applicable obsolete-output cleanup and explicit release-scope reconciliation.

Known constraint: independent reviewer owns Mac/Genesis GUI. No competing source app launch, build, profile mutation or fixture server. Current committed extraction/default changes are source-only. Full retirement is not claimed until remaining source/tests/packaging consumers are removed or migrated. Historical receipts/logs and user data remain untouched.

Direct-Tk source inventory (not deletion approval for generated artifacts):

- yt_downloader/platform_services.py
- yt_downloader/forge_activity_ui.py
- yt_downloader/scene_rail.py
- yt_downloader/update_recovery.py
- yt_downloader/scene_components.py
- yt_downloader/archive_library_ui.py
- yt_downloader/focus_settings.py
- yt_downloader/whats_new_activity_demo.py
- yt_downloader/modal_backdrop.py
- yt_downloader/ui_chrome.py
- yt_downloader/media_player_ui.py
- yt_downloader/ui_widgets.py
- yt_downloader/whats_new_ui.py
- yt_downloader/choice_popover.py
- yt_downloader/ui_styles.py
- yt_downloader/library_file_actions_ui.py
- yt_downloader/whats_new_feature_preview.py
- yt_downloader/playback_surface.py
- yt_downloader/library_annotation_ui.py
- yt_downloader/playback_probe.py
- yt_downloader/ui_transition.py
- yt_downloader/player_scene_ui.py
- yt_downloader/library_scene_ui.py
- yt_downloader/ui_context_menu.py
- yt_downloader/engagement_ui.py
- yt_downloader/presentation_diagnostics.py
- yt_downloader/ui_scrolling.py
- yt_downloader/ui_button_contract.py
- yt_downloader/activity_ui.py
- yt_downloader/local_audio_video_ui.py
- yt_downloader/analytics_consent_ui.py
- yt_downloader/ui_canvas_actions.py
- yt_downloader/run_hover_menu.py
- yt_downloader/player_presentation_ui.py
- yt_downloader/whats_new_audio_demo.py
- yt_downloader/watch_ui.py
- yt_downloader/analytics_qa_probe.py
- yt_downloader/archive_artwork.py
- yt_downloader/archive_browser_ui.py
- yt_downloader/app.py
- yt_downloader/ui_events.py
- yt_downloader/library_search_ui.py
- yt_downloader/archive_presentation.py
- yt_downloader/library_collection_ui.py
- yt_downloader/library_media_recovery_ui.py
- yt_downloader/ui_theme.py
- yt_downloader/detail_ui.py
- yt_downloader/ui_editable_text.py
- yt_downloader/support_ui.py
- yt_downloader/analytics_startup.py
- yt_downloader/ui_materials.py
- yt_downloader/platforms/macos/surfaces.py
- yt_downloader/platforms/macos/windowing.py

Oct 12 incremental checkpoint:

- Widget entry is gone (242510c); LibraryHistory is a neutral durable owner (6f28b81).
- Explicit announcement Try it source correction is e1ff771; HeyCatch desktop transport removal is f42d6eb. Both affect a successor only.
-54 widget/platform source files and legacy previews/probes are retired in the next incremental commit. Mixed service/data test consumers preserve actual worker, recovery, publication and privacy owners. Disposition receipts name retired definitions; implementation rollback stays in Git.
-Full collection6994/zero import errors; retained affected data suites188pass; Qt entry/diagnostic/package-receipt import controls6pass. These counts describe actual checks, not acceptance parity.
-Remaining: reconcile old EQH scene/recovery selectors and dynamic synthetic Tk producer calls, update source-bound selectors, then verify affected current-owner boundaries. Packaging/native/update/privacy qualification is separate and untested for this successor. No new build until retention cleanup prerequisites resolve.
