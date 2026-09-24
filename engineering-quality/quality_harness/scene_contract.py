"""Required source defect classes for media browsing and durable scene state.

These classes do not stand in for complete native scene review, actual rendered
video transitions, packaged execution, or external playback-device evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .recovery_contract import recovery_class_contract

SCENE_CLASSES = {
    "file_action_integrity": (
        107,
        ("tests/test_archive_file_operations.py", "tests/test_library_file_actions.py"),
    ),
    "shared_scroll_ownership": (17, ("tests/test_shared_input.py",)),
    "shared_keyboard_ownership": (4, ("tests/test_shared_keyboard.py",)),
    "shared_pointer_ownership": (7, ("tests/test_canvas_actions.py",)),
    "readable_descriptions": (
        50,
        ("tests/test_description_readability.py", "tests/test_text_fit_work.py"),
    ),
    "library_restraint": (35, ("tests/test_library_restraint.py",)),
    "watch_queue": (79, ("tests/test_watch_queue.py",)),
    "window_chrome": (
        19,
        ("tests/test_window_chrome.py", "tests/test_view_transition.py"),
    ),
    "channel_membership": (
        26,
        ("tests/test_watch_channels.py", "tests/test_watch_media_counts.py"),
    ),
    "channel_artwork": (
        60,
        ("tests/test_channel_artwork.py", "tests/test_thumbnail_network.py"),
    ),
    "artwork_fidelity": (
        34,
        (
            "tests/test_archive_artwork.py",
            "tests/test_library_artwork_source.py",
            "tests/test_presentation_diagnostics.py::test_canvas_snapshot_includes_owned_horizontal_rail_images",
        ),
    ),
    "progress_lifetime": (
        39,
        ("tests/test_watch_progress.py", "tests/test_playback_progress_binding.py"),
    ),
    "volume_truth": (13, ("tests/test_volume_storage.py",)),
    "bounded_navigation": (
        47,
        (
            "tests/test_scene_paging.py",
            "tests/test_scene_navigation.py",
            "tests/test_scene_projection.py",
        ),
    ),
    "import_integrity": (
        19,
        ("tests/test_library_import.py", "tests/test_library_scene_telemetry.py"),
    ),
    "detail_geometry": (
        86,
        ("tests/test_library_detail_geometry.py", "tests/test_watch_scene_geometry.py"),
    ),
    "annotation_ownership": (16, ("tests/test_library_scene_actions.py",)),
    "history_publication": (6, ("tests/test_history_publication.py",)),
    "player_related": (26, ("tests/test_player_related.py",)),
    "player_presentation": (
        126,
        (
            "tests/test_player_presentation.py",
            "tests/test_libvlc_backend.py",
            "tests/test_player_hover_preview.py",
            "tests/test_media_preview.py",
            "tests/test_player_caption_layout.py",
        ),
    ),
}
SCENE_REQUIRED_TESTS = {
    "readable_descriptions": (
        "tests/test_text_fit_work.py::test_long_title_fit_does_not_measure_every_invisible_line",
        "tests/test_text_fit_work.py::test_fitted_monospaced_title_preserves_exact_visible_capacity",
        "tests/test_text_fit_work.py::test_full_line_count_remains_exact_for_long_documents",
        "tests/test_text_fit_work.py::test_each_prefix_is_measured_once_within_a_fit_but_not_across_fonts",
    ),
    "file_action_integrity": (
        "tests/test_archive_file_operations.py::test_kept_uncertain_delete_preserves_committed_absence_against_late_delta",
        "tests/test_library_file_actions.py::test_single_file_decision_does_not_start_competing_inspector_work",
        "tests/test_archive_file_operations.py::test_startup_never_retires_receipts_when_recovery_is_unsettled",
        "tests/test_archive_file_operations.py::test_oversized_initial_receipt_fails_before_media_or_history_effect",
        "tests/test_archive_file_operations.py::test_receipt_inventory_rejects_aggregate_before_parsing",
        "tests/test_archive_file_operations.py::test_journal_admission_reserves_recovery_growth_before_effect",
        "tests/test_archive_file_operations.py::test_original_run_delta_follows_repeated_move_and_delete",
        "tests/test_archive_file_operations.py::test_same_session_delta_remains_protected_after_many_operations",
        "tests/test_archive_file_operations.py::test_recovery_rejects_receipt_change_after_validation",
        "tests/test_archive_file_operations.py::test_startup_replays_pending_delta_before_retiring_prior_session_receipts",
        "tests/test_archive_file_operations.py::test_removed_cleanup_recovery_preserves_replacements",
        "tests/test_archive_file_operations.py::test_late_delta_reconciliation_rejects_unreadable_receipts",
        "tests/test_archive_file_operations.py::test_staged_same_run_record_does_not_restore_old_path_or_deleted_entry",
        "tests/test_archive_file_operations.py::test_history_write_lease_is_payload_scoped_and_cleared_after_exception",
        "tests/test_archive_file_operations.py::test_published_move_recovers_in_a_fresh_process",
        "tests/test_archive_file_operations.py::test_replacement_after_retirement_boundary_is_preserved",
        "tests/test_archive_file_operations.py::test_trash_failure_never_falls_back_to_permanent_delete",
        "tests/test_archive_file_operations.py::test_fresh_process_reads_recovery_gate_and_actual_history",
        "tests/test_library_file_actions.py::test_uncertain_worker_result_reloads_authority_before_any_deferred_writer",
        "tests/test_library_file_actions.py::test_file_observations_obey_consent_and_exclude_file_content",
    ),
    "channel_membership": (
        "tests/test_watch_media_counts.py::test_playlist_presentation_counts_match_its_actual_content",
    ),
    "annotation_ownership": (
        "tests/test_library_scene_actions.py::test_detail_version_choice_resolves_current_owner_and_retains_origin",
    ),
    "player_presentation": (
        "tests/test_player_presentation.py::test_queue_host_show_does_not_focus_background_embedded_window",
    ),
    "window_chrome": (
        "tests/test_view_transition.py::test_replacement_retires_timer_and_old_callback_cannot_remove_new_cover",
        "tests/test_view_transition.py::test_within_view_navigation_retires_pending_reveal_and_images",
        "tests/test_view_transition.py::test_optional_transition_observations_are_content_free_bounded_and_isolated",
        "tests/test_view_transition.py::test_player_release_precedes_old_capture_and_new_tab_reveal",
        "tests/test_view_transition.py::test_destroyed_source_is_not_captured",
        "tests/test_view_transition.py::test_owner_destroy_cancels_timer_and_late_callbacks_cannot_restore_overlay",
    ),
    "bounded_navigation": (
        "tests/test_scene_navigation.py::test_watch_back_restores_search_scope_and_scroll_after_playlist_navigation",
        "tests/test_scene_navigation.py::test_global_search_display_follows_active_view_without_reapplying_filters",
        "tests/test_scene_projection.py::test_repaint_reuses_projection_but_new_snapshot_retires_identity",
        "tests/test_scene_projection.py::test_channel_query_and_collection_projections_remain_separate_and_bounded",
        "tests/test_scene_projection.py::test_annotation_only_replacement_rebuilds_personal_collection",
        "tests/test_scene_projection.py::test_record_replacement_releases_hidden_scene_projection_before_repaint",
        "tests/test_scene_projection.py::test_same_query_reacts_to_title_edit_without_media_membership_change",
        "tests/test_scene_projection.py::test_channel_and_collection_filter_use_current_records",
        "tests/test_scene_projection.py::test_library_repaint_cache_tracks_query_sort_and_annotation_replacement",
        "tests/test_scene_projection.py::test_library_hidden_record_replacement_releases_projection_snapshot",
        "tests/test_scene_paging.py::test_virtual_rows_cover_first_middle_end_and_remain_bounded",
        "tests/test_scene_paging.py::test_virtual_rows_reject_invalid_geometry_and_clamp_removed_tail",
        "tests/test_scene_navigation.py::test_watch_continuous_media_window_reaches_all_items_and_returns_to_start",
        "tests/test_scene_navigation.py::test_library_continuous_renderer_reaches_all_records_and_returns_to_start",
        "tests/test_scene_navigation.py::test_library_group_card_routes_to_exact_membership_after_scrolling",
        "tests/test_scene_navigation.py::test_watch_continuous_group_renderer_reaches_all_records",
        "tests/test_scene_navigation.py::test_home_rails_keep_collections_between_recent_and_playlists",
        "tests/test_scene_navigation.py::test_horizontal_row_usage_is_bounded_to_current_visit",
    ),
    "artwork_fidelity": (
        "tests/test_archive_artwork.py::test_returning_to_evicted_artwork_reloads_without_waiting_for_retry_timer",
        "tests/test_presentation_diagnostics.py::test_canvas_snapshot_includes_owned_horizontal_rail_images",
    ),
}
REQUIRED_SCENARIOS = frozenset("unit_static.scene_" + name for name in SCENE_CLASSES)


def scene_class_contract(
    repo_root: Path,
    output_dir: Path,
    regression_class: str,
    *,
    source_root: Path | None = None,
):
    return recovery_class_contract(
        repo_root,
        output_dir,
        regression_class,
        source_root=source_root,
        specification=SCENE_CLASSES[regression_class],
        scenario_prefix="unit_static.scene_",
        required_nodes=SCENE_REQUIRED_TESTS.get(regression_class, ()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--class", dest="classes", choices=SCENE_CLASSES, action="append"
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    scenarios = [
        scene_class_contract(repo, args.output / name, name, source_root=args.source)[0]
        for name in (args.classes or SCENE_CLASSES)
    ]
    payload = {
        "scope": "Bound source outcomes only; native scenes and packaged/device tiers remain separate",
        "scenarios": scenarios,
        "passed": all(s["status"] == "passed" for s in scenarios),
    }
    (args.output / "scene-contract.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    print(json.dumps({s["id"]: s["status"] for s in scenarios}, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
