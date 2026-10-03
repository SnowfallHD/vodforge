#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The macOS application must be built on macOS."
  exit 1
fi

python_bin="${VODFORGE_PYTHON:-}"
if [[ -z "$python_bin" && -x ".venv/bin/python" ]]; then
  python_bin=".venv/bin/python"
fi
if [[ -z "$python_bin" ]] && command -v python3.13 >/dev/null 2>&1; then
  python_bin="$(command -v python3.13)"
fi
if [[ -z "$python_bin" && -x "/opt/homebrew/opt/python@3.13/bin/python3.13" ]]; then
  python_bin="/opt/homebrew/opt/python@3.13/bin/python3.13"
fi
if [[ -z "$python_bin" ]]; then
  echo "Python 3.13 with Tk was not found. Run ./install_macos_dependencies.sh first."
  exit 1
fi

if ! "$python_bin" -c 'import tkinter' >/dev/null 2>&1; then
  echo "The selected Python does not include Tk: $python_bin"
  echo "Run ./install_macos_dependencies.sh or set VODFORGE_PYTHON to a Tk-enabled Python 3.11+."
  exit 1
fi

if [[ "$python_bin" != ".venv/bin/python" ]]; then
  "$python_bin" -m venv .venv
  python_bin=".venv/bin/python"
fi

"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -r requirements-dev.txt -r engineering-quality/requirements.txt
"$python_bin" -m compileall -q yt_downloader main.py qt_main.py macos_smoke_test.py
(
  # Build policy belongs to the packaged bytes, not to source tests that may
  # create live Qt bridges and telemetry owners in the same process.
  unset VODFORGE_UI VODFORGE_BUILD_TELEMETRY VODFORGE_BUILD_VERSION VODFORGE_DIST_DIR
  QT_QUICK_CONTROLS_STYLE=Basic QT_QUICK_BACKEND=software "$python_bin" -m pytest -q \
    --ignore=tests/test_qt_action_feedback_ownership.py \
    --ignore=tests/test_qt_file_recovery_actions.py \
    --ignore=tests/test_qt_floating_player_chrome.py \
    --ignore=tests/test_qt_folder_columns_responsive.py \
    --ignore=tests/test_qt_inspector_action_contract.py \
    --ignore=tests/test_qt_inspector_actions.py \
    --ignore=tests/test_qt_inspector_description_geometry.py \
    --ignore=tests/test_qt_inspector_recovery_details.py \
    --ignore=tests/test_qt_library_group_selection.py \
    --ignore=tests/test_qt_library_playlist_art.py \
    --ignore=tests/test_qt_overflow_action_pointer.py \
    --ignore=tests/test_qt_player_responsive_stage.py \
    --ignore=tests/test_qt_player_resize_continuity.py \
    --ignore=tests/test_qt_retry_recovery_membership.py \
    --ignore=tests/test_qt_runtime_event_ownership.py \
    --ignore=tests/test_qt_saved_output_access.py \
    --ignore=tests/test_qt_terminal_dismissal.py \
    --ignore=tests/test_qt_worker_control_context.py \
    --ignore=tests/test_qt_analytics_session.py \
    --ignore=tests/test_qt_artwork_continuity.py \
    --ignore=tests/test_qt_artwork_image.py \
    --ignore=tests/test_qt_metadata_preview.py \
    --ignore=tests/test_qt_presentation_diagnostics.py \
    --ignore=tests/test_qt_previews.py \
    --ignore=tests/test_qt_quality_e2e.py \
    --ignore=tests/test_qt_relink.py \
    --ignore=tests/test_qt_terminal_item_events.py \
    --ignore=tests/test_qt_scene_port.py \
    --ignore=tests/test_qt_telemetry_coverage.py \
    --ignore=tests/test_qt_fullscreen_native.py \
    --ignore=tests/test_qt_whats_new.py \
    --ignore=tests/test_qt_recorded_feature_preview.py \
    --ignore=tests/test_qt_output_config.py \
    --ignore=tests/test_qt_settings_theme.py \
    --ignore=tests/test_qt_scroll_lifecycle.py \
    --ignore=tests/test_qt_all_runs_hover_seam.py \
    --ignore=tests/test_qt_legacy_preset_preferences.py \
    --ignore=tests/test_qt_library_details_copy.py \
    --ignore=tests/test_qt_library_window_model.py \
    --ignore=tests/test_qt_library_thumbnail_reflow.py \
    --ignore=tests/test_qt_settings_privacy.py \
    --ignore=tests/test_qt_titlebar_drag.py \
    --ignore=tests/test_qt_vertical_scroll_chain.py \
    --ignore=tests/test_qt_material_visibility.py \
    --ignore=tests/test_qt_interaction_invariants.py \
    --ignore=tests/test_qt_composer_feedback.py \
    --ignore=tests/test_qt_dual_captions.py \
    --ignore=tests/test_qt_hidden_scene_focus.py \
    --ignore=tests/test_qt_library_selection_bar_placement.py \
    --ignore=tests/test_qt_move_dialog_content_fit.py \
    --ignore=tests/test_qt_move_root_notice.py \
    --ignore=tests/test_qt_output_path_layout.py \
    --ignore=tests/test_qt_overflow_glyph_centering.py \
    --ignore=tests/test_qt_player_frame_handoff.py \
    --ignore=tests/test_qt_player_hover_aspect.py \
    --ignore=tests/test_qt_player_presentation_return.py \
    --ignore=tests/test_qt_player_related_fallback.py \
    --ignore=tests/test_qt_recently_added_aspect.py \
    --ignore=tests/test_qt_run_deck_responsive_labels.py \
    --ignore=tests/test_qt_selectable_information.py \
    --ignore=tests/test_qt_thumbnail_reduction.py \
    --ignore=tests/test_qt_translated_subtitle_preferences.py \
    --ignore=tests/test_qt_watch_group_tile_aspect.py \
    --ignore=engineering-quality/tests/test_qt_analytics_session.py \
    --ignore=engineering-quality/tests/test_qt_diagnostic_gate.py \
    --ignore=engineering-quality/tests/test_qt_library_files.py \
    --ignore=engineering-quality/tests/test_qt_library_projection.py \
    --ignore=engineering-quality/tests/test_qt_library_removal.py \
    --ignore=engineering-quality/tests/test_qt_local_telemetry.py \
    --ignore=engineering-quality/tests/test_qt_port_owner_review.py \
    --ignore=engineering-quality/tests/test_qt_stone_button_accessibility.py \
    --ignore=engineering-quality/tests/test_qt_update_session.py \
    --ignore=engineering-quality/tests/test_qt_worker_owner.py
  QT_QUICK_CONTROLS_STYLE=Basic QT_QUICK_BACKEND=software "$python_bin" -m pytest -q \
    tests/test_qt_action_feedback_ownership.py \
    tests/test_qt_file_recovery_actions.py \
    tests/test_qt_floating_player_chrome.py \
    tests/test_qt_folder_columns_responsive.py \
    tests/test_qt_inspector_action_contract.py \
    tests/test_qt_inspector_actions.py \
    tests/test_qt_inspector_description_geometry.py \
    tests/test_qt_inspector_recovery_details.py \
    tests/test_qt_library_group_selection.py \
    tests/test_qt_library_playlist_art.py \
    tests/test_qt_overflow_action_pointer.py \
    tests/test_qt_player_responsive_stage.py \
    tests/test_qt_player_resize_continuity.py \
    tests/test_qt_retry_recovery_membership.py \
    tests/test_qt_runtime_event_ownership.py \
    tests/test_qt_saved_output_access.py \
    tests/test_qt_terminal_dismissal.py \
    tests/test_qt_worker_control_context.py \
    tests/test_qt_analytics_session.py \
    tests/test_qt_artwork_continuity.py \
    tests/test_qt_artwork_image.py \
    tests/test_qt_metadata_preview.py \
    tests/test_qt_presentation_diagnostics.py \
    tests/test_qt_previews.py \
    tests/test_qt_quality_e2e.py \
    tests/test_qt_relink.py \
    tests/test_qt_terminal_item_events.py \
    tests/test_qt_telemetry_coverage.py \
    tests/test_qt_fullscreen_native.py \
    tests/test_qt_whats_new.py \
    tests/test_qt_recorded_feature_preview.py \
    tests/test_qt_output_config.py \
    tests/test_qt_settings_theme.py \
    tests/test_qt_scroll_lifecycle.py \
    tests/test_qt_all_runs_hover_seam.py \
    tests/test_qt_legacy_preset_preferences.py \
    tests/test_qt_library_details_copy.py \
    tests/test_qt_library_window_model.py \
    tests/test_qt_library_thumbnail_reflow.py \
    tests/test_qt_settings_privacy.py \
    tests/test_qt_titlebar_drag.py \
    tests/test_qt_vertical_scroll_chain.py \
    tests/test_qt_material_visibility.py \
    tests/test_qt_interaction_invariants.py \
    tests/test_qt_composer_feedback.py \
    tests/test_qt_dual_captions.py \
    tests/test_qt_hidden_scene_focus.py \
    tests/test_qt_library_selection_bar_placement.py \
    tests/test_qt_move_dialog_content_fit.py \
    tests/test_qt_move_root_notice.py \
    tests/test_qt_output_path_layout.py \
    tests/test_qt_overflow_glyph_centering.py \
    tests/test_qt_player_frame_handoff.py \
    tests/test_qt_player_hover_aspect.py \
    tests/test_qt_player_presentation_return.py \
    tests/test_qt_player_related_fallback.py \
    tests/test_qt_recently_added_aspect.py \
    tests/test_qt_run_deck_responsive_labels.py \
    tests/test_qt_selectable_information.py \
    tests/test_qt_thumbnail_reduction.py \
    tests/test_qt_translated_subtitle_preferences.py \
    tests/test_qt_watch_group_tile_aspect.py \
    engineering-quality/tests/test_qt_analytics_session.py \
    engineering-quality/tests/test_qt_diagnostic_gate.py \
    engineering-quality/tests/test_qt_library_files.py \
    engineering-quality/tests/test_qt_library_projection.py \
    engineering-quality/tests/test_qt_library_removal.py \
    engineering-quality/tests/test_qt_local_telemetry.py \
    engineering-quality/tests/test_qt_port_owner_review.py \
    engineering-quality/tests/test_qt_stone_button_accessibility.py \
    engineering-quality/tests/test_qt_update_session.py \
    engineering-quality/tests/test_qt_worker_owner.py
  QT_QUICK_CONTROLS_STYLE=Basic QT_QUICK_BACKEND=software "$python_bin" -m pytest -q tests/test_qt_scene_port.py
)

ui_mode="${VODFORGE_UI:-tk}"
entrypoint="main.py"
qt_args=()
if [[ "$ui_mode" == "qt" ]]; then
  entrypoint="qt_main.py"
  qt_args=(
    --hidden-import PySide6.QtMultimedia
    --hidden-import PySide6.QtQuickControls2
  )
  for qml_file in yt_downloader/qt_quick/*.qml; do
    qt_args+=(--add-data "$qml_file:yt_downloader/qt_quick")
  done
elif [[ "$ui_mode" != "tk" ]]; then
  echo "VODFORGE_UI must be tk or qt."
  exit 1
fi

build_version="${VODFORGE_BUILD_VERSION:-0.1.0-dev}"
if [[ ! "$build_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  echo "VODFORGE_BUILD_VERSION must use semantic versioning, for example 1.2.3."
  exit 1
fi
dist_dir="${VODFORGE_DIST_DIR:-dist}"
app_bundle="$dist_dir/VODForge.app"
build_version_dir="build/version"
mkdir -p "$build_version_dir"
build_version_file="$build_version_dir/VODFORGE_VERSION"
printf '%s' "$build_version" > "$build_version_file"
"$python_bin" scripts/write_build_revision.py "$build_version_dir/VODFORGE_BUILD_REVISION"
telemetry_policy="${VODFORGE_BUILD_TELEMETRY:-disabled}"
if [[ "$telemetry_policy" != "disabled" && "$telemetry_policy" != "production" && "$telemetry_policy" != "preview" ]]; then
  echo "VODFORGE_BUILD_TELEMETRY must be disabled, production, or preview."
  exit 1
fi
printf '%s' "$telemetry_policy" > "$build_version_dir/VODFORGE_TELEMETRY_POLICY"
icon_file="assets/VODForge.icns"
icon_png="assets/VODForge.png"
macos_icon_source="assets/VODForge-macos.png"
icon_asset_dir="assets/icons/lucide"
if [[ ! -f "$icon_file" || ! -f "$icon_png" || ! -f "$macos_icon_source" || ! -d "$icon_asset_dir" ]]; then
  echo "VODForge icon assets are missing."
  exit 1
fi

ffmpeg="$(command -v ffmpeg || true)"
ffprobe="$(command -v ffprobe || true)"
deno="$(command -v deno || true)"
if [[ -z "$ffmpeg" || -z "$ffprobe" || -z "$deno" ]]; then
  echo "FFmpeg, ffprobe, and Deno are required for a self-contained app."
  echo "Run ./install_macos_dependencies.sh first."
  exit 1
fi
vlc_args=(--exclude-module vlc)
if [[ "$ui_mode" == "tk" ]]; then
  vlc_version="3.0.23"
  vlc_root="${VODFORGE_VLC_RUNTIME:-}"
  if [[ -z "$vlc_root" && -f "vendor/vlc/VODFORGE_VLC_VERSION" ]]; then
    vlc_root="vendor/vlc"
  fi
  vlc_root="${vlc_root:-/Applications/VLC.app/Contents/MacOS}"
  vlc_library="$vlc_root/lib/libvlc.dylib"
  vlc_core="$vlc_root/lib/libvlccore.dylib"
  vlc_plugins="$vlc_root/plugins"
  if [[ ! -f "$vlc_library" || ! -f "$vlc_core" || ! -d "$vlc_plugins" ]]; then
    echo "A complete libVLC runtime was not found at $vlc_root."
    echo "Install the VLC cask or set VODFORGE_VLC_RUNTIME."
    exit 1
  fi
  if [[ -f "$vlc_root/VODFORGE_VLC_VERSION" ]]; then
    resolved_vlc_version="$(<"$vlc_root/VODFORGE_VLC_VERSION")"
  elif [[ -f "$vlc_root/../Info.plist" ]]; then
    resolved_vlc_version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$vlc_root/../Info.plist")"
  else
    resolved_vlc_version=""
  fi
  if [[ "$resolved_vlc_version" != "$vlc_version" ]]; then
    echo "The macOS libVLC runtime must be pinned to $vlc_version; found ${resolved_vlc_version:-unknown}."
    echo "Run ./install_vlc_macos.sh or set VODFORGE_VLC_RUNTIME to the pinned runtime."
    exit 1
  fi
  vlc_args=(
    --add-binary "$vlc_library:vlc/lib"
    --add-binary "$vlc_core:vlc/lib"
    --add-data "$vlc_plugins:vlc/plugins"
    --hidden-import vlc
  )
fi

"$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "VODForge" \
  --distpath "$dist_dir" \
  --collect-all yt_dlp \
  --collect-data certifi \
  --osx-bundle-identifier "com.snowfallhd.vodforge" \
  --icon "$icon_file" \
  --add-data "$build_version_file:." \
  --add-data "$build_version_dir/VODFORGE_BUILD_REVISION:." \
  --add-data "$build_version_dir/VODFORGE_TELEMETRY_POLICY:." \
  --add-data "$icon_png:assets" \
  --add-data "assets/brand:assets/brand" \
  --add-data "assets/materials:assets/materials" \
  --add-data "$icon_asset_dir:assets/icons/lucide" \
  --add-data "assets/watch-welcome-scenic.png:assets" \
  --add-data "assets/preview_thumbnails/alpine-lake.jpg:assets/preview_thumbnails" \
  --add-data "THIRD_PARTY_NOTICES.md:." \
  --add-binary "$ffmpeg:." \
  --add-binary "$ffprobe:." \
  --add-binary "$deno:." \
  "${vlc_args[@]}" \
  "${qt_args[@]}" \
  "$entrypoint"

app_binary="$app_bundle/Contents/MacOS/VODForge"
if [[ ! -x "$app_binary" ]]; then
  echo "Expected application executable was not created: $app_binary"
  exit 1
fi

app_plist="$app_bundle/Contents/Info.plist"
bundle_version="${build_version%%-*}"
for version_key in CFBundleShortVersionString CFBundleVersion; do
  if /usr/libexec/PlistBuddy -c "Print :$version_key" "$app_plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :$version_key $bundle_version" "$app_plist"
  else
    /usr/libexec/PlistBuddy -c "Add :$version_key string $bundle_version" "$app_plist"
  fi
done

if [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app_plist")" != "$bundle_version" ]] || \
   [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app_plist")" != "$bundle_version" ]]; then
  echo "Packaged macOS version metadata does not match $bundle_version."
  exit 1
fi

bundle_icon_name="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIconFile' "$app_plist")"
bundle_icon="$app_bundle/Contents/Resources/$bundle_icon_name"
if [[ "$bundle_icon_name" != "VODForge.icns" ]] || [[ ! -f "$bundle_icon" ]] || ! cmp -s "$icon_file" "$bundle_icon"; then
  echo "Packaged macOS Finder and Dock icon must both use the exact VODForge.icns asset."
  exit 1
fi

# PyInstaller ad-hoc signs the initial bundle, but the version metadata above is
# intentionally finalized afterward. Re-sign only after every local bundle
# mutation so the test application is structurally valid on disk. Public
# releases still replace this ad-hoc signature with Developer ID signing.
/usr/bin/codesign --force --deep --sign - "$app_bundle"
/usr/bin/codesign --verify --deep --strict "$app_bundle"

"$app_binary" --runtime-smoke
echo "Built ad-hoc signed local VODForge v${build_version}: $app_bundle"
echo "Developer ID signing and notarization are still required before public distribution."
