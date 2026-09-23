# Tk presentation owner review for the Qt port

The source index (`.venv/bin/python engineering-quality/runners/qt-port-source-index.py --output build/qt-port-package/source-index.json`) parses and hashes every tracked or untracked code file: product Python/QML, tests, engineering harness, packaging, CI, scripts, structured configuration, and dependency entrypoints. This review names every current product file that directly paints Tk, binds a Tk control, or controls a Tk presentation transition. A file may be a presentation owner without importing `tkinter` directly; `watch_scene_ui.py`, `library_scene_layout.py`, and `library_detail_layout.py` are examples. The Qt path is an implementation lead, not proof of parity. Every row remains subject to the feature, visual, native, telemetry and package gates in `qt-port-code-parity.md`.

| Tk presentation owner | Qt path to verify | Current open obligation |
| --- | --- | --- |
| `yt_downloader/activity_ui.py` | `qt_quick/ActivityScene.qml` | Log token styling, live and durable content |
| `yt_downloader/analytics_consent_ui.py` | `qt_quick/Main.qml`, `qt_quick/analytics.py` | First-run consent popup and focus |
| `yt_downloader/analytics_qa_probe.py` | Qt harness and telemetry readback | Native QA parity |
| `yt_downloader/analytics_startup.py` | `qt_quick/main.py`, `qt_quick/analytics.py` | Startup consent sequencing |
| `yt_downloader/app.py` | `qt_quick/main.py`, `qt_quick/runtime.py`, QML scenes | Audit every reachable action and event; shared worker retained |
| `yt_downloader/archive_artwork.py` | `qt_quick/artwork.py`, `library_artwork_source.py` | All artwork roles and invalidation |
| `yt_downloader/archive_browser_ui.py` | `qt_quick/LibraryFolders.qml`, `archive_browser.py` | Folder selection, activity, relink, geometry |
| `yt_downloader/archive_library_ui.py` | `qt_quick/LibraryScene.qml`, `qt_quick/LibraryDetail.qml` | All inspector actions and saved variants |
| `yt_downloader/choice_popover.py` | QML shared popup controls | Selection, keyboard, focus, placement |
| `yt_downloader/detail_ui.py` | `qt_quick/LibraryDetail.qml` | Output facts and copy actions |
| `yt_downloader/engagement_ui.py` | `qt_quick/Main.qml`, `qt_quick/EditorialPopup.qml` | Welcome, help, review, foreground order |
| `yt_downloader/focus_settings.py` | `qt_quick/Main.qml`, `qt_quick/ManualMp4Settings.qml` | Exact settings controls, adaptive layout, PRO |
| `yt_downloader/forge_activity_ui.py` | `qt_quick/Main.qml`, `forge_activity.py` | Friendly and technical log presentation |
| `yt_downloader/library_annotation_ui.py` | `qt_quick/LibraryDetail.qml`, `qt_quick/Main.qml` | Dialog and inline editing parity |
| `yt_downloader/library_collection_ui.py` | `qt_quick/Main.qml`, `library_annotations.py` | Edit and remove membership |
| `yt_downloader/library_detail_layout.py` | `qt_quick/LibraryDetail.qml` | Effective bounds, scroll and variants |
| `yt_downloader/library_file_actions_ui.py` | `qt_quick/main.py`, `qt_quick/library_files.py` | Native move, Trash, recovery journey |
| `yt_downloader/library_media_recovery_ui.py` | `qt_quick/Main.qml`, `qt_quick/relink.py` | Native prompt and folder-wide relink |
| `yt_downloader/library_scene_layout.py` | `qt_quick/LibraryScene.qml` | Sidebar, tile, card and toolbar bounds |
| `yt_downloader/library_scene_ui.py` | `qt_quick/LibraryScene.qml`, `qt_quick/scene_projection.py` | Selection, paging, routes and scroll restoration |
| `yt_downloader/library_search_ui.py` | `qt_quick/LibraryScene.qml` | Search focus, filters, responsive wrapping |
| `yt_downloader/local_audio_video_ui.py` | `qt_quick/Main.qml`, `qt_quick/local_conversion.py` | Input and progress/error dialog journey |
| `yt_downloader/media_player_ui.py` | `qt_quick/PlayerScene.qml`, `qt_quick/CaptionTracks.qml`, `qt_quick/Main.qml` | Playback, captions, seek, volume and native decode |
| `yt_downloader/modal_backdrop.py` | `qt_quick/StoneField.qml`, QML Popup | Material and dismiss behavior |
| `yt_downloader/platform_services.py` | Qt native dialogs, shared path helpers | Every platform UI branch |
| `yt_downloader/platforms/macos/surfaces.py` | Qt native video surface | Packaged macOS presentation |
| `yt_downloader/platforms/macos/windowing.py` | Qt Window geometry | macOS window/focus behavior |
| `yt_downloader/playback_probe.py` | Qt native playback harness | Installed player proof |
| `yt_downloader/playback_surface.py` | Qt `VideoOutput` | Surface replacement and close |
| `yt_downloader/player_presentation_ui.py` | `qt_quick/PlayerScene.qml`, `qt_quick/Main.qml` | Fullscreen/floating return and queue |
| `yt_downloader/player_scene_ui.py` | `qt_quick/PlayerScene.qml`, `qt_quick/CaptionTracks.qml`, `player_related.py` | Chapters, previews, related/captions |
| `yt_downloader/presentation_diagnostics.py` | Qt telemetry and native harness | Presentation transition evidence |
| `yt_downloader/run_hover_menu.py` | `qt_quick/RunDeck.qml` | Every active/queued/terminal/preview action |
| `yt_downloader/scene_components.py` | QML scenes, `StoneButton.qml`, `StoneField.qml` | Control positions and card rendering |
| `yt_downloader/scene_rail.py` | `qt_quick/WatchScene.qml` | Horizontal rail scroll and focus |
| `yt_downloader/support_ui.py` | `qt_quick/Main.qml`, `qt_quick/support.py` | Help menu, support and feedback flow |
| `yt_downloader/ui_button_contract.py` | `qt_quick/StoneButton.qml`, `qt_quick/main.py:Materials` | One shared material-to-screen path |
| `yt_downloader/ui_canvas_actions.py` | QML input and shared controls | Hover, press, release, keyboard |
| `yt_downloader/ui_chrome.py` | `qt_quick/main.py:Materials` | Button, field, background geometry |
| `yt_downloader/ui_context_menu.py` | QML shared popup controls | Menu items use shared concave controls |
| `yt_downloader/ui_editable_text.py` | `qt_quick/LibraryDetail.qml` | Edit, cancel, copy, measured height |
| `yt_downloader/ui_events.py` | `qt_quick/main.py`, `qt_quick/runtime.py` | Event-by-event parity and stale guards |
| `yt_downloader/ui_materials.py` | `qt_quick/main.py:Materials` | Image stretch and coverage invariants |
| `yt_downloader/ui_scrolling.py` | QML ScrollView routes | Wheel, trackpad and scroll restoration |
| `yt_downloader/ui_styles.py` | QML shared controls and `ui_theme.py` | Typography and state material |
| `yt_downloader/ui_theme.py` | `qt_quick/main.py`, QML theme context | All appearance modes and reapply |
| `yt_downloader/ui_transition.py` | Qt transitions and native harness | Drag/resize paint continuity |
| `yt_downloader/ui_widgets.py` | QML shared controls | Every reusable control behavior |
| `yt_downloader/update_recovery.py` | `qt_quick/update_session.py`, `qt_quick/Main.qml` | Installed Repair/recovery journey |
| `yt_downloader/watch_scene_ui.py` | `qt_quick/WatchScene.qml`, `qt_quick/scene_projection.py` | Every route, action, measured layout |
| `yt_downloader/watch_ui.py` | `qt_quick/WatchScene.qml` | Watch activation and progress |
| `yt_downloader/whats_new_activity_demo.py` | `qt_quick/FeaturePreview.qml` | Activity demo interaction |
| `yt_downloader/whats_new_audio_demo.py` | `qt_quick/FeaturePreview.qml` | Original audio demo interaction |
| `yt_downloader/whats_new_feature_preview.py` | `qt_quick/FeaturePreview.qml` | Every declared preview renderer |
| `yt_downloader/whats_new_ui.py` | `qt_quick/EditorialPopup.qml` | Slides, next/previous, focus, updates |

The other product modules are reusable state, export, playback, history, telemetry, update, network, and storage owners or Qt adapters. They are present in the complete source index and must be exercised through the corresponding feature gate. The index is regenerated after code changes; a source file's presence alone does not clear its behavioral or native acceptance gate.
