"""Synthetic valid contexts for exhaustive transport/release-validator tests.

These are fixture values, not producer evidence. The producer pipeline obtains
its dimensions from the actual native/source owners.
"""


def diagnostic_context(feature: str, action: str) -> dict[str, str]:
    if feature == "run_control_operation":
        return {
            "run_control_action": "cancel",
            "run_control_origin": "run_menu",
            "run_control_owner": "current" if action == "admitted" else "retired",
        }
    if feature == "run_recovery_operation":
        restored = action == "restored_without_retry"
        return {
            "recovery_cause": "missing_retry_url" if restored else "malformed_json",
            "recovery_stage": "terminal_restore" if restored else "journal_read",
            "recovery_schema": "1",
            "recovery_disposition": "restored_without_retry"
            if restored
            else "blocked_preserved",
            **({"item_count_bucket": "1"} if restored else {}),
        }
    if feature == "watch_queue_operation":
        return {
            "queue_kind": "playlist",
            "queue_order": "ordered",
            "item_count_bucket": "2_5",
            "queue_position_bucket": "1",
            "queue_completed_bucket": "0",
            **(
                {
                    "queue_failure_boundary": "provider",
                    "queue_failure_reason": "provider_failed",
                }
                if action == "failed"
                else {}
            ),
        }
    if feature == "library_action_operation":
        boundary = {
            "requested": "validation",
            "admitted": "queue",
            "completed": "queue",
            "rejected": "queue",
            "duplicate_focused": "duplicate",
            "cancelled": "confirmation",
            "annotation_retained": "annotation",
        }[action]
        return {
            "library_intent": "preview_start",
            "library_subject": "preview",
            "library_boundary": boundary,
        }
    if feature != "presentation_operation":
        return {}
    context = {
        "presentation_surface": "watch",
        "presentation_mode": "playlists",
        "mode_origin": "default",
        "presentation_population": "saved_media",
        "presentation_trigger": "entry",
        "presentation_visibility": "visible",
        "presentation_scene": "current",
        "eligible_bucket": "2_5",
        "mode_eligible_bucket": "2_5",
        "matching_bucket": "2_5",
        "rendered_bucket": "2_5",
        "query_state": "inactive",
        "filter_state": "inactive",
        "artwork_expected_bucket": "2_5",
        "artwork_displayed_bucket": "2_5",
        "artwork_unavailable_bucket": "0",
        "artwork_state": "ready",
        "missing_image_bucket": "0",
        "missing_image_role": "none",
        "presentation_sampling": "full",
        "presentation_audit": "under_2ms",
        "lag_bucket": "under_50ms",
        "lag_measurement": "ui_pump_delay",
        "artwork_batch": "current",
    }
    if action == "fault":
        context.update(missing_image_bucket="1", missing_image_role="control")
    if action in {"settled", "superseded", "retired"}:
        context["presentation_replacement"] = (
            "resize" if action == "superseded" else "none"
        )
    if action == "retired":
        context["presentation_scene"] = "retired"
    if action == "sampled":
        context["presentation_sampling"] = "healthy_sampled"
    return context
