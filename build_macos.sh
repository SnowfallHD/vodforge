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
  echo "Python 3.13 was not found. Run ./install_macos_dependencies.sh first."
  exit 1
fi



if [[ "$python_bin" != ".venv/bin/python" ]]; then
  "$python_bin" -m venv .venv
  python_bin=".venv/bin/python"
fi

"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -r requirements-dev.txt -r engineering-quality/requirements.txt
native_arch="$("$python_bin" -c 'import platform; print(platform.machine())')"
minimum_macos="$("$python_bin" -c 'import os,sys; from scripts.build_macos_fullscreen import deployment_minimum; print(deployment_minimum(sys.argv[1], os.environ.get("VODFORGE_MACOS_MIN_VERSION")))' "$native_arch")"
# Reject incompatible host inputs before source campaigns and PyInstaller work.
# The sealed bundle and actual target OS still require their own qualification.
"$python_bin" scripts/check_macos_runtime_inputs.py --python-inputs \
  --maximum "$minimum_macos" \
  --report "${VODFORGE_COMPATIBILITY_REPORT:-build/macos-input-compatibility.json}"
"$python_bin" -m compileall -q yt_downloader main.py qt_main.py macos_smoke_test.py
(
  # Build policy belongs to the packaged bytes, not to source tests that may
  # create live Qt bridges and telemetry owners in the same process.
  unset VODFORGE_UI VODFORGE_BUILD_TELEMETRY VODFORGE_BUILD_VERSION VODFORGE_DIST_DIR
  QT_QUICK_CONTROLS_STYLE=Basic QT_QUICK_BACKEND=software "$python_bin" -m pytest -q \
    tests engineering-quality/tests fine-tuning/tests \
    --ignore=tests/test_qt_application_fullscreen.py \
    --ignore=tests/test_qt_import_failure_status.py \
    --ignore=tests/test_qt_local_conversion_validation.py \
    --ignore=tests/test_qt_navigation_selection.py \
    --ignore=tests/test_qt_popup_lifecycle_wait.py \
    --ignore=tests/test_qt_resource_recovery.py \
    --ignore=tests/test_qt_review_spacing_metrics.py \
    --ignore=tests/test_qt_shared_popup_motion.py \
    --ignore=tests/test_qt_native_toolbar_header.py \
    --ignore=tests/test_qt_options_panel_motion.py \
    --ignore=tests/test_qt_dropdown_hover_material.py \
    --ignore=tests/test_qt_forge_compact_actions.py \
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
    --ignore=tests/test_qt_completed_run_menu.py \
    --ignore=tests/test_qt_update_check_guidance.py \
    --ignore=tests/test_qt_options_shared_settings.py \
    --ignore=tests/test_qt_options_rendered_presence.py \
    --ignore=tests/test_qt_watch_scroll_extent.py \
    --ignore=tests/test_qt_resize_continuity.py \
    --ignore=tests/test_qt_player_responsive_stage.py \
    --ignore=tests/test_qt_player_resize_continuity.py \
    --ignore=tests/test_qt_retry_recovery_membership.py \
    --ignore=tests/test_automatic_updates.py \
    --ignore=tests/test_library_shutdown_pending.py \
    --ignore=tests/test_resource_recovery_issues.py \
    --ignore=tests/test_run_completion_sidecar_identity.py \
    --ignore=tests/test_run_deck_terminal_order.py \
    --ignore=tests/test_workflow_coverage.py \
    --ignore=tests/test_qt_without_tk.py \
    --ignore=tests/test_qt_history_startup.py \
    --ignore=tests/test_qt_mac_windowing_ownership.py \
    --ignore=tests/test_qt_runtime_event_ownership.py \
    --ignore=tests/test_qt_saved_output_access.py \
    --ignore=tests/test_qt_terminal_dismissal.py \
    --ignore=tests/test_qt_worker_control_context.py \
    --ignore=tests/test_qt_analytics_session.py \
    --ignore=tests/test_qt_automatic_attribution.py \
    --ignore=tests/test_qt_artwork_continuity.py \
    --ignore=tests/test_qt_card_material_bounds.py \
    --ignore=tests/test_qt_click_reliability.py \
    --ignore=tests/test_qt_library_section_selection.py \
    --ignore=tests/test_qt_popup_toggle_order.py \
    --ignore=tests/test_qt_watch_close_hero_refresh.py \
    --ignore=tests/test_qt_mac_native_runtime.py \
    --ignore=tests/test_qt_mac_preferences.py \
    --ignore=tests/test_qt_optional_sidecar_recovery.py \
    --ignore=tests/test_qt_run_artwork.py \
    --ignore=tests/test_qt_sidecar_recovery_controls.py \
    --ignore=tests/test_qt_windows_frame_resize.py \
    --ignore=tests/test_qt_artwork_image.py \
    --ignore=tests/test_qt_metadata_preview.py \
    --ignore=tests/test_qt_preview_refusal.py \
    --ignore=tests/test_qt_startup_update_check.py \
    --ignore=tests/test_qt_presentation_diagnostics.py \
    --ignore=tests/test_qt_previews.py \
    --ignore=tests/test_qt_quality_e2e.py \
    --ignore=tests/test_qt_relink.py \
    --ignore=tests/test_qt_recovery_draft_retirement.py \
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
    --ignore=tests/test_qt_description_keyboard.py \
    --ignore=tests/test_qt_output_picker.py \
    --ignore=tests/test_qt_material_visibility.py \
    --ignore=tests/test_qt_interaction_invariants.py \
    --ignore=tests/test_qt_composer_feedback.py \
    --ignore=tests/test_qt_composer_custom_options.py \
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
  QT_QUICK_CONTROLS_STYLE=Basic QT_QUICK_BACKEND=software "$python_bin" -m pytest -q --tb=short \
    tests/test_qt_application_fullscreen.py \
    tests/test_qt_import_failure_status.py \
    tests/test_qt_local_conversion_validation.py \
    tests/test_qt_navigation_selection.py \
    tests/test_qt_popup_lifecycle_wait.py \
    tests/test_qt_resource_recovery.py \
    tests/test_qt_review_spacing_metrics.py \
    tests/test_qt_shared_popup_motion.py \
    tests/test_qt_native_toolbar_header.py \
    tests/test_qt_options_panel_motion.py \
    tests/test_qt_dropdown_hover_material.py \
    tests/test_qt_forge_compact_actions.py \
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
    tests/test_qt_completed_run_menu.py \
    tests/test_qt_update_check_guidance.py \
    tests/test_qt_options_shared_settings.py \
    tests/test_qt_options_rendered_presence.py \
    tests/test_qt_watch_scroll_extent.py \
    tests/test_qt_resize_continuity.py \
    tests/test_qt_player_responsive_stage.py \
    tests/test_qt_player_resize_continuity.py \
    tests/test_qt_retry_recovery_membership.py \
    tests/test_automatic_updates.py \
    tests/test_library_shutdown_pending.py \
    tests/test_resource_recovery_issues.py \
    tests/test_run_completion_sidecar_identity.py \
    tests/test_run_deck_terminal_order.py \
    tests/test_workflow_coverage.py \
    tests/test_qt_without_tk.py \
    tests/test_qt_history_startup.py \
    tests/test_qt_mac_windowing_ownership.py \
    tests/test_qt_runtime_event_ownership.py \
    tests/test_qt_saved_output_access.py \
    tests/test_qt_terminal_dismissal.py \
    tests/test_qt_worker_control_context.py \
    tests/test_qt_analytics_session.py \
    tests/test_qt_automatic_attribution.py \
    tests/test_qt_artwork_continuity.py \
    tests/test_qt_card_material_bounds.py \
    tests/test_qt_click_reliability.py \
    tests/test_qt_library_section_selection.py \
    tests/test_qt_popup_toggle_order.py \
    tests/test_qt_watch_close_hero_refresh.py \
    tests/test_qt_mac_native_runtime.py \
    tests/test_qt_mac_preferences.py \
    tests/test_qt_optional_sidecar_recovery.py \
    tests/test_qt_run_artwork.py \
    tests/test_qt_sidecar_recovery_controls.py \
    tests/test_qt_windows_frame_resize.py \
    tests/test_qt_artwork_image.py \
    tests/test_qt_metadata_preview.py \
    tests/test_qt_preview_refusal.py \
    tests/test_qt_startup_update_check.py \
    tests/test_qt_presentation_diagnostics.py \
    tests/test_qt_previews.py \
    tests/test_qt_quality_e2e.py \
    tests/test_qt_relink.py \
    tests/test_qt_recovery_draft_retirement.py \
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
    tests/test_qt_description_keyboard.py \
    tests/test_qt_output_picker.py \
    tests/test_qt_material_visibility.py \
    tests/test_qt_interaction_invariants.py \
    tests/test_qt_composer_feedback.py \
    tests/test_qt_composer_custom_options.py \
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
  QT_QUICK_CONTROLS_STYLE=Basic QT_QUICK_BACKEND=software "$python_bin" -m pytest -q --tb=short tests/test_qt_scene_port.py
)

ui_mode="${VODFORGE_UI:-qt}"
if [[ "$ui_mode" != "qt" ]]; then
  echo "VODFORGE_UI must be qt."
  exit 1
fi
entrypoint="main.py"

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

# Build this candidate's native phase owner explicitly; app startup never
# compiles or searches for an external helper. Keep failures/receipts for review.
native_build_root="$(mktemp -d build/macos-fullscreen-XXXXXX)"
"$python_bin" -m scripts.build_macos_fullscreen \
  --source yt_downloader/platforms/macos/fullscreen_lifecycle.m \
  --output "$native_build_root/helper" --arch "$native_arch"
native_helper="$native_build_root/helper/libvodforge_fullscreen.dylib"

# The bundle's contents are listed once, in scripts/macos_package_contents.py,
# which the universal build uses too.
package_args=()
while IFS= read -r -d '' option; do
  package_args+=("$option")
done < <("$python_bin" -m scripts.macos_package_contents \
  --version-dir "$build_version_dir" \
  --native-helper "$native_helper" \
  --ffmpeg "$ffmpeg" --ffprobe "$ffprobe" --deno "$deno")
if [[ "${#package_args[@]}" -eq 0 ]]; then
  echo "The macOS package contents could not be listed."
  exit 1
fi

# --clean only clears the selected cache; candidate-specific caches otherwise
# accumulate. This wrapper owns and retires only this invocation's binary cache,
# including command failure. PyInstaller work diagnostics and dist stay intact.
"$python_bin" scripts/run_with_ephemeral_pyinstaller_cache.py "$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --target-arch "$native_arch" \
  --distpath "$dist_dir" \
  "${package_args[@]}" \
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

# Match the input-floor gate above; this declares the package requirement and
# does not lower deployment commands in any already compiled dependency.
: "${minimum_macos:?Target architecture minimum was not selected}"
if /usr/libexec/PlistBuddy -c "Print :LSMinimumSystemVersion" "$app_plist" >/dev/null 2>&1; then
  /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion $minimum_macos" "$app_plist"
else
  /usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string $minimum_macos" "$app_plist"
fi

if [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app_plist")" != "$bundle_version" ]] || \
   [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app_plist")" != "$bundle_version" ]] || \
   [[ "$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "$app_plist")" != "$minimum_macos" ]]; then
  echo "Packaged macOS version/minimum metadata does not match $bundle_version / $minimum_macos."
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
