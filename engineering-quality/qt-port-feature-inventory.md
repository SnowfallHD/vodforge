# Qt port feature inventory

Source: current Tk code at `d67b11c8297dff409b05944357f0b8b8bd46ebc0`, inspected on 2026-09-23. The Tk screenshots are a **state and feature index**, not a pixel oracle: preserve the newer intended Qt concave design and controls where the Tk render is old or broken. The source owners below define behavior and reachability. The Qt column describes the current port, not release qualification.

## Shared shell and Forge

| Feature in Tk | Tk owner | Qt state |
| --- | --- | --- |
| Four views, brand, global search, navigation, responsive background cover | `app.py` focus chrome and view selection | Qt measured header now stacks one shared navigation row at narrow widths; 820×560 AX bounds pass, while full geometry comparison remains open. Full-cover artwork remains PreserveAspectCrop. |
| URL entry, format choice, presets, output destination, settings, download and queue | `app.py` Forge composer and submission | Core actions present; composer layout now being translated from current Tk. |
| Batch URL list and single/playlist control | `app.py`, `url_list_inputs.py` | Present at core level; verify visual and validation states. |
| Local audio and image to video conversion | `local_audio_video_ui.py` | Core action and Qt dialog present; visual and packaged journey pending. |
| Live title/artwork/progress, friendly/technical activity, source/output details | `app.py`, `forge_activity_ui.py`, `detail_ui.py` | Qt now reads the same run-owned friendly projection and current-run technical lines, with a rendered source toggle; title/artwork, complete output facts and detail dialogs remain open. |
| Run Deck: active, queued, terminal and completed cards; overflow, actions, retry/skip/cancel | `app.py` `_focus_run_records`, `run_hover_menu.py`, `run_deck_renderer.py`, `library_state.py` | Runtime actions exist; Qt visual deck and completed-history projection missing. |

## Library and Watch

| Feature in Tk | Tk owner | Qt state |
| --- | --- | --- |
| Library sidebar and counts: All Media, Channels, Playlists, Videos, Audio | `library_scene_layout.py`, `library_scene_ui.py`, `watch_library.py` | Qt sidebar and routes rendered; responsive bounds and details remain open. |
| Library home category cards, collections, recent media, artwork and storage tile | `library_scene_layout.py`, `library_scene_ui.py` | Qt scene, artwork, collection cards and shared capacity owner wired; visual/interaction parity remains open. |
| Search, sort, type/category filters, selection and paging/scroll position | `library_scene_ui.py`, `library_scene_layout.py` | Search and sort route wired, including group query; category filter core exists. Selection, paging and scroll restoration remain open. |
| Library item details, output details, source variants, notes/tags/category | `library_detail_layout.py`, `library_scene_facts.py`, `library_annotation_ui.py` | Qt detail scene now reads shared source/output facts and saved annotations; version selector, direct editing and complete detail actions remain open. |
| Create collection and assign media to it | `library_collection_ui.py`, `app.py` `_show_library_collection_editor` | Qt editor persists membership through shared annotations and both scenes now read that projection; editing/removing membership and dialog parity remain open. |
| Import local media | `app.py` `_import_library_media`, `library_import.py` | Qt native picker, shared inspection and durable commit wired; package/native journey remains open. |
| Open saved location; remove card; move to folder/Trash; relink/recovery | `library_file_actions_ui.py`, `library_media_recovery_ui.py`, `app.py` | Basic open/remove/move/Trash and recovery core exist; compare complete dialogs and relink states. |
| Watch home hero, playlists/channels/collections rails and routes | `watch_scene_ui.py`, `watch_library.py`, `watch_ui.py`, `library_artwork_source.py` | Qt browse scene now projects the shared hero metadata and saved progress, source-role artwork for media/playlist/avatar/banner, and channel header counts/description. Full-cover Qt hero and channel source captures exist. Exact cards, related content, scroll restoration and responsive geometry remain open. |
| Watch queue, shuffle, back/search context and related media | `watch_scene_ui.py`, `player_scene_ui.py`, `watch_queue.py` | Group queue and shuffle now reach the shared queue owner. A source Qt run with two real local audio files advanced through both items and completed. Search filters through the shared Watch rail owner; a bounded route stack restores results on Back. Scroll/selection restoration and related media remain open. |
| Playback controls, volume, chapters, heatmap, preview moments, details, window modes | `media_player_ui.py`, `player_scene_ui.py`, `player_presentation_ui.py`, `player_related.py` | `PlayerScene.qml` keeps the current control material and per-open provider generation, and reads the shared Up Next/recent plan, identity, annotations and source/output facts. It exposes Edit your details and related Play/Details actions. Five midpoint thumbnails now use the existing offline `MediaPreviewOwner` through a bounded Qt session; replacement retires prior results and moment buttons use the shared seek path. Correctly resized wide/narrow source captures and 820×560 AX bounds passed before the preview addition; native video, moments on screen, scrolled information sections and window modes need package proof. Complete telemetry parity remains open. |

## Activity, help and release surfaces

| Feature in Tk | Tk owner | Qt state |
| --- | --- | --- |
| Activity timeline/log and run history | `activity_ui.py`, `forge_activity_ui.py`, `app.py` | Qt now uses the shared private log owner and current-run event binding; token typography, selected-run detail and package journey remain open. |
| Settings including output, format, network, cookies and analytics | `focus_settings.py`, `app.py` bindings | Core preferences and several Qt panels present; section/detail parity needs state review. |
| Consent and privacy | `analytics_consent_ui.py`, `analytics_startup.py` | Qt consent core and popup present; visual/first-run journey pending. |
| Welcome tour, What's New, Did You Know (editorial mode currently `none`) | `engagement_ui.py`, `engagement_state.py`, `whats_new.py`, `whats_new_ui.py`, `whats_new_feature_preview.py` | Qt now uses `EngagementState` for first-run/rating eligibility and the shared highlight data/preview enum for a native QML carousel. Every declared preview key has a QML renderer using shared controls. The welcome popup was rendered and inspected; optional showcase mode is still `none`. All slide variants, automatic foreground sequencing and exact feature preview controls need rendered/package checks. |
| Help menu, feedback, review and support diagnostics | `engagement_ui.py`, `support_ui.py`, `support_payload.py`, `support_transport.py` | Qt Help button, shared-control feedback/review forms, reason/rating/message/reply and explicit diagnostics/video-URL consent now use one shared payload validator and the existing transport. Recent failed-run context is projected read-only into feedback. Wide/narrow source forms rendered; live delivery, verification handoff and full Help menu actions remain open. |
| Update check/download/install/repair and recovery | `app.py`, `updates.py`, `qt_quick/update_session.py` | Core Qt updater and popup present; exact packaged update/repair proof pending. |

## Capture coverage

- `build/qt-port-package/tk-reference-d67/manifest.json`: 14 real Tk route captures using isolated saved media.
- `build/qt-port-package/tk-detail-d67-v2/detail-manifest.json`: focused detail-state matrix, including both player formats, annotation/collection editors, settings, announcements, consent and native menus/alerts. See each case's outcome; a capture is evidence of a rendered state only.
- Still to capture or exercise before claiming parity: Library item detail and local import, Watch playlist/channel detail and queue, player window modes and related content, file move/relink/recovery dialogs, update install/repair states, help/support, empty and error states, narrow/large window layouts, Windows packaged captures.

Qt release status: **blocked on feature and visual parity plus packaged Mac/Windows journeys**. Source tests, screenshots, and runtime smoke do not by themselves qualify a release.
