"""Required diagnostic outcomes; transport success alone is insufficient."""

from __future__ import annotations


def verify_scenario_events(case: str, events: list[dict]) -> None:
    if case.startswith("qt_"):
        qt_events = [
            event
            for event in events
            if event.get("feature") == "presentation_operation"
            and event["dimensions"].get("presentation_surface") == "library"
        ]
        assert qt_events, (case, "Qt scene produced no presentation events")
        assert any(
            event["action"] == "settled"
            and event["dimensions"]["artwork_state"] == "ready"
            for event in qt_events
        ), (case, "Qt artwork never settled visibly")
        if case.endswith("_fault"):
            role = case.removeprefix("qt_").removesuffix("_fault")
            faults = [
                event
                for event in qt_events
                if event["action"] == "fault"
                and event["dimensions"]["missing_image_role"] == role
            ]
            assert faults, (case, "Qt did not observe the actual image error")
            assert any(
                event["action"] == "recovered"
                and event["dimensions"]["operation_id"]
                == fault["dimensions"]["operation_id"]
                for fault in faults
                for event in qt_events
            ), (case, "Qt image recovery lost operation identity")
        if case == "qt_resize":
            assert any(
                event["dimensions"]["presentation_trigger"] == "resize"
                for event in qt_events
            ), (case, "Qt resize transition was not observed")
        return
    presentation = [
        e
        for e in events
        if e.get("feature") == "presentation_operation"
        and e["dimensions"].get("presentation_surface") == "watch"
    ]
    actions = [e for e in events if e.get("feature") == "library_action_operation"]

    def seen(action=None, **dimensions):
        return any(
            (action is None or e["action"] == action)
            and all(e["dimensions"].get(k) == v for k, v in dimensions.items())
            for e in presentation
        )

    if case == "player_description":
        descriptions = [e for e in events if e.get("feature") == "player"]
        assert [e["action"] for e in descriptions] == [
            "description_opened",
            "description_closed",
        ]
        assert all(not e["dimensions"] for e in descriptions)
    elif case == "library_disclosure":
        disclosure = [e for e in events if e.get("feature") == "library"]
        assert [e["action"] for e in disclosure] == [
            "selection_started",
            "selection_finished",
            "menu_opened",
        ]
        assert all(not e["dimensions"] for e in disclosure)
    elif case.startswith("watch_queue_"):
        queue = [e for e in events if e.get("feature") == "watch_queue_operation"]
        reason = case.removeprefix("watch_queue_")
        missing = reason in {"record_removed", "saved_output_missing"}
        opening = reason.startswith("open_")
        failure = missing or opening or reason in {"failed", "unexpected_ended"}
        expected = ["requested"]
        if not opening and reason != "unexpected_ended":
            expected.append("started")
        if reason in {"ordered", "shuffle", "large"} or missing:
            expected.append("advanced")
        expected.append(
            "failed"
            if failure
            else "cancelled"
            if reason in {"cancelled", "cancel_after_ended"}
            else "completed"
        )
        assert [e["action"] for e in queue] == expected
        assert len({e["dimensions"]["operation_id"] for e in queue}) == 1
        assert [e["dimensions"]["operation_step"] for e in queue] == [
            str(i + 1) for i in range(len(expected))
        ]
        for e in queue:
            dims = e["dimensions"]
            assert dims["queue_kind"] == (
                "channel" if reason == "shuffle" else "playlist"
            )
            assert dims["queue_order"] == (
                "shuffle" if reason == "shuffle" else "ordered"
            )
            assert dims["item_count_bucket"] == (
                "101_plus"
                if reason == "large"
                else "1"
                if reason == "single"
                else "2_5"
            )
            assert "queue_position_bucket" in dims and "queue_completed_bucket" in dims
        terminal = queue[-1]["dimensions"]
        assert terminal["queue_completed_bucket"] == (
            "1"
            if missing or reason in {"single", "cancel_after_ended"}
            else "0"
            if failure or reason == "cancelled"
            else "101_plus"
            if reason == "large"
            else "2_5"
        )
        if failure:
            boundary = (
                "metadata"
                if missing
                else reason.removeprefix("open_")
                if opening
                else "provider"
                if reason == "failed"
                else "unexpected_end"
            )
            failure_reason = (
                "source_removed"
                if reason == "record_removed"
                else "saved_output_missing"
                if missing
                else "permission_denied"
                if opening
                else "provider_failed"
                if reason == "failed"
                else "ended_before_playing"
            )
            assert terminal["queue_failure_boundary"] == boundary
            assert terminal["queue_failure_reason"] == failure_reason
            if opening:
                assert queue[-1]["failure_detail"]["os_error"] == 13
                assert queue[-1]["failure_reason"] == "permission_denied"
        else:
            assert (
                "queue_failure_boundary" not in terminal
                and "queue_failure_reason" not in terminal
            )
    elif case.startswith("relink_"):
        relink = [e for e in events if e.get("feature") == "archive_relink_operation"]
        matching = case == "relink_matching"
        expected = (
            ["requested", "verified", "commit_requested", "committed"]
            if matching
            else ["requested", "verified", "cancelled"]
        )
        assert [e["action"] for e in relink] == expected
        assert len({e["dimensions"]["operation_id"] for e in relink}) == 1
        assert [e["dimensions"]["operation_step"] for e in relink] == [
            str(i + 1) for i in range(len(expected))
        ]
        dimensions = relink[1]["dimensions"]
        mismatch = case in {
            "relink_legacy_format",
            "relink_canonical_format",
            "relink_companion_identity",
        }
        assert dimensions["identity_mismatch_count"] == ("1" if mismatch else "0")
        assert dimensions["verified_count"] == ("1" if matching else "0")
        assert dimensions["unresolved_count"] == ("0" if matching else "1")
        assert (
            dimensions["collision_count"]
            == dimensions["missing_count"]
            == dimensions["unavailable_count"]
            == "0"
        )
    elif case.startswith("opening_"):
        playback = [e for e in events if e.get("feature") == "playback_operation"]
        assert [e["action"] for e in playback] == ["requested", "failed"]
        assert len({e["dimensions"]["operation_id"] for e in playback}) == 1
        assert [e["dimensions"]["operation_step"] for e in playback] == ["1", "2"]
        failure = playback[-1]
        boundary = case.removeprefix("opening_")
        assert failure["dimensions"]["playback_failure_boundary"] == boundary
        assert failure["dimensions"]["player_surface"] == "embedded"
        assert failure["dimensions"]["playback_origin"] == "watch"
        assert failure["failure_detail"]["stage"] == "playback"
        assert failure["failure_reason"] == (
            "dependency_missing"
            if boundary == "dependency"
            else "permission_denied"
            if boundary == "load"
            else "unknown"
        )
        if boundary == "load":
            assert failure["failure_detail"]["os_error"] == 13
        if boundary == "readiness":
            assert failure["failure_detail"]["failure_code"] == "timeout"
    elif case in {"cold_ready", "resize_pending"}:
        assert seen(artwork_state="pending"), (case, "missing pending observation")
        assert seen("settled", artwork_state="ready"), (case, "missing settled artwork")
        if case == "resize_pending":
            assert seen(presentation_trigger="resize")
    elif case == "unavailable_artwork":
        assert seen("settled", artwork_state="unavailable")
        assert not seen("fault")
    elif case == "missing_control":
        faults = [
            e
            for e in presentation
            if e["action"] == "fault"
            and e["dimensions"]["missing_image_role"] == "control"
        ]
        assert faults
        assert any(
            e["action"] == "recovered"
            and e["dimensions"]["operation_id"] == fault["dimensions"]["operation_id"]
            for fault in faults
            for e in presentation
        )
    elif case == "missing_artwork":
        assert seen(
            "fault", missing_image_role="artwork", presentation_visibility="hidden"
        )
        assert seen("settled", artwork_state="ready", presentation_visibility="visible")
    elif case == "invalid_default_mode":
        assert seen(
            "settled",
            presentation_mode="collections",
            mode_origin="default",
            eligible_bucket="2_5",
            mode_eligible_bucket="0",
            matching_bucket="0",
            query_state="inactive",
        )
    elif case == "intentional_empty_search":
        assert seen(
            "settled",
            mode_eligible_bucket="2_5",
            matching_bucket="0",
            query_state="active",
        )
    elif case == "hidden_return":
        assert seen(
            presentation_trigger="data",
            presentation_visibility="hidden",
            presentation_scene="retained",
        )
        assert seen(
            "settled",
            presentation_trigger="entry",
            presentation_visibility="visible",
            artwork_state="ready",
        )
        assert not seen("fault")
    elif case == "hidden_control_fault":
        assert seen(
            "fault", missing_image_role="control", presentation_visibility="hidden"
        )
    elif case == "late_fault_after_sampling":
        sampled = [
            i
            for i, e in enumerate(presentation)
            if e["action"] == "sampled"
            and e["dimensions"]["presentation_sampling"] == "healthy_sampled"
        ]
        faults = [
            i
            for i, e in enumerate(presentation)
            if e["action"] == "fault"
            and e["dimensions"]["missing_image_role"] == "control"
        ]
        assert sampled and faults and min(sampled) < max(faults), (
            "No persisted late control fault after healthy sampling"
        )
        assert seen(
            "fault", presentation_visibility="hidden", presentation_scene="retained"
        )
    elif case.startswith(("retry_", "supersession_")):
        refused = "_refused_" in case
        expected = (
            ["requested", "rejected"]
            if refused
            else ["requested", "admitted", "annotation_retained", "completed"]
        )
        assert [e["action"] for e in actions] == expected
        event = actions[-1] if refused else actions[2]
        permission = case.endswith("permission")
        assert event["failure_reason"] == (
            "permission_denied" if permission else "disk_full"
        )
        assert event["failure_detail"]["os_error"] == (13 if permission else 28)
        assert event["failure_detail"]["source_module"] == (
            "run_state" if refused else "library_annotations"
        )
        assert event["dimensions"]["library_boundary"] == (
            ("queue" if "_queue_" in case else "launch") if refused else "annotation"
        )
        assert actions[0]["dimensions"]["library_subject"] == (
            "terminal" if case.startswith("retry_") else "run"
        )
        assert actions[-1]["dimensions"]["library_boundary"] == (
            "queue" if "_queue_" in case else "launch"
        )
    else:
        expected = {
            "accepted_queue": ["requested", "admitted", "completed"],
            "refused_queue": ["requested", "rejected"],
            "refused_launch": ["requested", "rejected"],
            "duplicate_focus": ["requested", "duplicate_focused"],
            "accepted_annotation_retained": [
                "requested",
                "admitted",
                "annotation_retained",
                "completed",
            ],
            "accepted_preview_callback_fault": ["requested", "admitted"],
            "removal_refused": ["requested", "rejected"],
            "removal_cancelled": ["requested", "cancelled"],
            "refused_queue_permission": ["requested", "rejected"],
            "refused_queue_disk_full": ["requested", "rejected"],
            "refused_launch_disk_full": ["requested", "rejected"],
        }[case]
        assert [e["action"] for e in actions] == expected, (
            case,
            "missing or wrong admission outcome",
        )
        if case.endswith(("permission", "disk_full")):
            assert actions[-1]["failure_reason"] == (
                "permission_denied" if case.endswith("permission") else "disk_full"
            )
            assert actions[-1]["failure_detail"]["os_error"] == (
                13 if case.endswith("permission") else 28
            )
            assert actions[-1]["failure_detail"]["source_module"] == "run_state"
        if case in {"refused_launch", "refused_launch_disk_full"}:
            assert actions[-1]["dimensions"]["library_boundary"] == "launch"
