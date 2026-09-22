"""Bounded product vocabulary. Never pass user content to this module.

Feature owners report facts; ProductTelemetryOwner owns consent, identity and
transport. This vocabulary is shared by producers, validation and QA inventories.
"""

from __future__ import annotations

import json
import platform
import re
import uuid
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit

from .failure_diagnostics import FAILURE_CODES, FAILURE_REASONS

FEATURE_ACTIONS: dict[str, frozenset[str]] = {
    "settings": frozenset({"snapshot"}),
    "archive": frozenset(
        {
            "folders",
            "all_media",
            "activity",
            "folder_opened",
            "location_copied",
            "version_selected",
            "scene_navigated",
            "scene_sorted",
            "scene_paged",
            "scene_scrolled",
            "volume_selected",
            "file_opened",
            "inspector_opened",
            "history_deferred",
            "history_recovered",
            "history_defer_failed",
            "history_recovery_failed",
            "artwork_loaded",
            "artwork_unavailable",
        }
    ),
    "watch": frozenset(
        {
            "opened",
            "searched",
            "search_focused",
            "playlists",
            "channels",
            "channel_opened",
            "collections",
            "rail_scrolled",
            "catalog_scrolled",
            "details",
            "details_retired",
            "singleton_shown",
            "hero_shown",
            "hero_played",
            "artwork_loaded",
            "artwork_unavailable",
        }
    ),
    "library": frozenset(
        {
            "opened",
            "searched",
            "search_focused",
            "filtered",
            "selected",
            "selection_started",
            "selection_finished",
            "menu_opened",
            "removed",
            "source_tags_copied",
            "source_description_copied",
            "personal_tags_copied",
            "personal_note_copied",
            "thumbnail_url_copied",
            "youtube_url_copied",
        }
    ),
    "organization": frozenset(
        {"notes_saved", "tags_saved", "category_saved", "description_saved"}
    ),
    "player": frozenset(
        {
            "description_opened",
            "description_closed",
            "completed",
            "failed",
            "seek",
            "chapter",
            "heatmap",
            "preview",
            "details_opened",
            "details_closed",
            "detail_viewed",
            "related_shown",
            "related_selected",
            "related_details",
            "fit",
            "fill",
            "fullscreen",
            "floating",
            "returned",
            "captions_selected",
            "controls_fallback",
            "control_failed",
            "controls_hidden",
            "controls_shown",
            "hover_preview_shown",
            "hover_preview_unavailable",
            "caption_fit_applied",
            "caption_fill_restored",
            "caption_fill_unavailable",
        }
    ),
    "missing_media": frozenset({"offered", "accepted", "completed", "preset_migrated"}),
    "announcement": frozenset({"shown", "try_it"}),
    "guidance": frozenset({"technical_opened", "recovery_selected"}),
    "appearance": frozenset({"changed", "transition_shown", "transition_skipped"}),
    "updater": frozenset(
        {
            "download_started",
            "download_completed",
            "handoff",
            "relaunched",
            "failed",
            "repair_started",
            "repair_completed",
        }
    ),
}
# Per-operation observations are separate from legacy once-per-session usage.
OPERATION_FEATURES = {
    "run_control_operation": frozenset({"admitted", "rejected"}),
    "run_recovery_operation": frozenset(
        {"failed", "start_blocked", "restored_without_retry"}
    ),
    "watch_queue_operation": frozenset(
        {
            "requested",
            "started",
            "advanced",
            "completed",
            "cancelled",
            "failed",
        }
    ),
    "presentation_operation": frozenset(
        {
            "observed",
            "superseded",
            "sampled",
            "settled",
            "retired",
            "fault",
            "recovered",
        }
    ),
    "library_action_operation": frozenset(
        {
            "requested",
            "admitted",
            "completed",
            "rejected",
            "duplicate_focused",
            "cancelled",
            "annotation_retained",
        }
    ),
    "library_file_operation": frozenset(
        {"requested", "started", "completed", "needs_attention", "cancelled"}
    ),
    "library_import_operation": frozenset(
        {"requested", "completed", "failed", "cancelled"}
    ),
    "archive_history_operation": frozenset(
        {"started", "deferred", "recovered", "completed", "failed"}
    ),
    "archive_location_operation": frozenset(
        {"requested", "completed", "failed", "cancelled", "timed_out"}
    ),
    "archive_relink_operation": frozenset(
        {
            "requested",
            "verified",
            "cancel_requested",
            "commit_requested",
            "committed",
            "failed",
            "cancelled",
            "timed_out",
            "stale",
        }
    ),
    "download_operation": frozenset(
        {
            "started",
            "stage",
            "candidate_rejected",
            "reused",
            "committed",
            "completed",
            "failed",
            "cancelled",
        }
    ),
    "local_conversion_operation": frozenset(
        {"started", "committed", "completed", "failed", "cancelled"}
    ),
    "help_operation": frozenset(
        {
            "requested",
            "popup_returned",
            "selected",
            "dispatched",
            "shown",
            "blocked",
            "closed",
            "replaced",
            "failed",
        }
    ),
    "playback_operation": frozenset(
        {
            "requested",
            "focused",
            "ready",
            "started",
            "completed",
            "failed",
            "closed",
            "cancelled",
            "volume_pending",
            "volume_applied",
            "volume_failed",
            "volume_unresolved",
            "control_failed",
            "resume_requested",
            "resume_completed",
            "resume_failed",
            "resume_cancelled",
            "progress_saved",
            "progress_save_failed",
        }
    ),
    "resize_operation": frozenset({"settled"}),
}
FEATURE_ACTIONS.update(OPERATION_FEATURES)
DIMENSION_PATTERNS = {
    "operation_id": r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    "operation_step": r"(?:[1-9]|[1-5][0-9]|6[0-4])",
    "build_revision": r"(?:[0-9a-f]{40}|unknown)",
}
DIMENSION_RANGES = {
    key: (0, 10000)
    for key in (
        "item_count",
        "committed_count",
        "reused_count",
        "failed_count",
        "skipped_count",
        "sidecar_failure_count",
        "observation_drop_count",
    )
}
DIMENSION_RANGES.update(
    {
        "volume_request": (1, 999999),
        "volume_requested": (0, 100),
        "volume_observed": (0, 100),
        "observed_audio_bitrate_kbps": (1, 100000),
        "observed_audio_sample_rate_hz": (1, 768000),
        "observed_audio_channels": (1, 64),
        "namespace_media_file_count": (0, 128),
        "peer_comparison_count": (0, 32),
        **{
            key: (0, 5000)
            for key in (
                "verified_count",
                "unresolved_count",
                "collision_count",
                "identity_mismatch_count",
                "missing_count",
                "unavailable_count",
            )
        },
    }
)
DIMENSION_CHOICES: dict[str, frozenset[str]] = {
    "run_control_action": frozenset(["cancel", "skip_item", "skip_source"]),
    "run_control_origin": frozenset(["run_menu"]),
    "run_control_owner": frozenset(["current", "retired"]),
    "recovery_entry": frozenset({"startup", "run_admission", "queue_update"}),
    "recovery_cause": frozenset(
        {
            "missing_retry_url",
            "invalid_record",
            "malformed_json",
            "invalid_encoding",
            "read_failed",
            "write_failed",
            "unsupported_schema",
            "size_limit",
            "live_owner",
            "invalid_staging",
            "child_ownership",
            "cleanup_failed",
        }
    ),
    "recovery_stage": frozenset(
        {
            "terminal_restore",
            "journal_read",
            "journal_validation",
            "journal_write",
            "owner_check",
            "staging_validation",
            "child_cleanup",
            "staging_cleanup",
            "queue_loading",
        }
    ),
    "recovery_schema": frozenset({"1"}),
    "recovery_disposition": frozenset({"blocked_preserved", "restored_without_retry"}),
    "file_action": frozenset({"move", "delete", "recovery"}),
    "queue_kind": frozenset({"channel", "playlist"}),
    "queue_order": frozenset({"ordered", "shuffle"}),
    "queue_position_bucket": frozenset({"1", "2_5", "6_20", "21_100", "101_plus"}),
    "queue_completed_bucket": frozenset(
        {"0", "1", "2_5", "6_20", "21_100", "101_plus"}
    ),
    "queue_failure_boundary": frozenset(
        {
            "metadata",
            "resolve",
            "dependency",
            "initialization",
            "readiness",
            "load",
            "surface",
            "provider",
            "unexpected_end",
            "constructor",
            "presentation",
            "unknown",
        }
    ),
    "queue_failure_reason": FAILURE_REASONS
    | frozenset(
        {
            "source_removed",
            "saved_output_missing",
            "provider_failed",
            "ended_before_playing",
            "open_failed",
            "storage_wait_expired",
            "surface_unavailable",
        }
    ),
    "playback_control_origin": frozenset({"user", "caption_safety", "caption_restore"}),
    "playback_control": frozenset(
        {
            "fit",
            "fill",
            "captions",
            "fullscreen",
            "floating",
            "return",
            "seek",
            "volume",
            "toggle",
            "unknown",
        }
    ),
    "playback_view": frozenset({"embedded", "fullscreen", "floating", "unknown"}),
    "control_failure_kind": frozenset({"provider_error", "unexpected_error"}),
    "artwork_source": frozenset(
        {
            "thumbnail",
            "local_frame",
            "embedded_art",
            "channel_avatar",
            "channel_banner",
            "mixed",
            "none",
        }
    ),
    "artwork_role": frozenset({"media", "avatar", "banner", "playlist", "mixed"}),
    "resume_reason": frozenset(
        {
            "provider_failed",
            "seek_rejected",
            "seek_timeout",
            "media_changed",
            "manual_seek",
            "closed",
        }
    ),
    "scene_route": frozenset(
        {
            "home",
            "all",
            "detail",
            "videos",
            "audio",
            "channels",
            "playlists",
            "collections",
            "playlist",
            "channel",
        }
    ),
    "mode_eligible_bucket": frozenset({"0", "1", "2_5", "6_20", "21_100", "101_plus"}),
    "query_state": frozenset({"active", "inactive"}),
    "filter_state": frozenset({"active", "inactive"}),
    "presentation_surface": frozenset({"watch", "library"}),
    "presentation_mode": frozenset(
        {
            "channel",
            "all",
            "channels",
            "activity",
            "folders",
            "playlists",
            "collections",
        }
    ),
    "mode_origin": frozenset({"user", "default"}),
    "presentation_population": frozenset({"library_projection", "saved_media"}),
    "presentation_trigger": frozenset(
        {"artwork", "entry", "resize", "data", "filter", "navigation", "hide", "theme"}
    ),
    "presentation_replacement": frozenset(
        {
            "artwork",
            "entry",
            "resize",
            "data",
            "filter",
            "navigation",
            "hide",
            "theme",
            "none",
        }
    ),
    "presentation_visibility": frozenset({"visible", "hidden"}),
    "presentation_scene": frozenset({"retired", "current", "awaiting", "retained"}),
    "artwork_state": frozenset(
        {"pending", "unavailable", "decoded_awaiting_render", "mixed", "ready", "none"}
    ),
    "missing_image_role": frozenset(
        {"artwork", "surface", "control", "unknown", "mixed", "none"}
    ),
    "presentation_sampling": frozenset(
        {"healthy_sampled", "transition_limited", "exhausted", "full"}
    ),
    "presentation_audit": frozenset({"under_2ms", "50ms_plus", "2_9ms", "10_49ms"}),
    "artwork_batch": frozenset({"current", "superseded"}),
    "eligible_bucket": frozenset({"21_100", "2_5", "101_plus", "1", "0", "6_20"}),
    "matching_bucket": frozenset({"21_100", "2_5", "101_plus", "1", "0", "6_20"}),
    "rendered_bucket": frozenset({"21_100", "2_5", "101_plus", "1", "0", "6_20"}),
    "artwork_expected_bucket": frozenset(
        {"21_100", "2_5", "101_plus", "1", "0", "6_20"}
    ),
    "artwork_displayed_bucket": frozenset(
        {"21_100", "2_5", "101_plus", "1", "0", "6_20"}
    ),
    "artwork_unavailable_bucket": frozenset(
        {"21_100", "2_5", "101_plus", "1", "0", "6_20"}
    ),
    "missing_image_bucket": frozenset({"21_100", "2_5", "101_plus", "1", "0", "6_20"}),
    "library_intent": frozenset(
        {"source_start", "preview_start", "run_start", "remove"}
    ),
    "library_subject": frozenset(
        {"source", "preview", "queued", "active", "terminal", "saved", "run"}
    ),
    "library_boundary": frozenset(
        {
            "validation",
            "duplicate",
            "queue",
            "launch",
            "confirmation",
            "history",
            "annotation",
            "closing",
            "completed",
        }
    ),
    "history_boundary": frozenset({"startup", "settlement", "defer"}),
    "history_document": frozenset({"main", "pending", "unknown"}),
    "history_phase": frozenset(
        {"read", "parse", "validate", "write", "retire", "unknown"}
    ),
    "archive_mode": frozenset({"folders", "all", "activity"}),
    "watch_mode": frozenset({"playlists", "channels", "collections"}),
    "storage_kind": frozenset({"local", "drive", "network", "external", "unknown"}),
    "location_action": frozenset({"open", "check"}),
    "relink_mode": frozenset({"file", "folder"}),
    "archive_result": frozenset(
        {
            "available",
            "opened",
            "missing",
            "unavailable",
            "foreign_platform",
            "cancelled",
            "timed_out",
            "stale",
            "changed",
            "write_failed",
            "unknown",
        }
    ),
    "playback_origin": frozenset({"library", "watch", "unknown"}),
    "player_surface": frozenset({"embedded", "window"}),
    "volume_outcome": frozenset({"pending", "applied", "failed", "pending_at_close"}),
    "volume_cause": frozenset(
        {
            "requested",
            "output_reset",
            "provider_rejected",
            "readback_unavailable",
            "readback_mismatch",
            "readback_exception",
            "setter_exception",
        }
    ),
    "volume_phase": frozenset(
        {
            "idle",
            "ready",
            "starting",
            "playing",
            "paused",
            "stopped",
            "ended",
            "failed",
            "closed",
            "unknown",
        }
    ),
    "playback_failure_boundary": frozenset(
        {
            "provider_event",
            "state_read",
            "start",
            "pause",
            "seek",
            "stop",
            "unknown",
            "resolve",
            "constructor",
            "dependency",
            "initialization",
            "readiness",
            "load",
        }
    ),
    "detail_target": frozenset(
        {"chapters", "info", "source", "output", "notes", "moments"}
    ),
    "intent_relation": frozenset(
        {
            "first_observed",
            "same_intent",
            "different_settings",
            "different_destination_or_organization",
            "unknown",
        }
    ),
    "instrumentation": frozenset({"diagnostics_v1"}),
    "stage": frozenset(
        {
            "preparation",
            "analysis",
            "reuse",
            "staging",
            "download",
            "transcode",
            "validation",
            "commit",
            "sidecars",
            "history",
            "dispatch",
            "playback",
            "unknown",
        }
    ),
    "output_observation": frozenset({"single", "multiple", "unavailable"}),
    "observed_audio_state": frozenset({"single", "multiple", "none", "unknown"}),
    "observed_audio_codec": frozenset(
        {
            "aac",
            "mp3",
            "opus",
            "vorbis",
            "flac",
            "alac",
            "pcm_s16le",
            "pcm_s24le",
            "other",
        }
    ),
    "namespace_scan_state": frozenset(
        {"complete", "capped", "missing", "unreadable", "unknown", "not_applicable"}
    ),
    "peer_namespace_state": frozenset(
        {
            "distinct",
            "shared_directory",
            "shared_artifact",
            "no_comparable",
            "missing",
            "unreadable",
            "capped",
            "unknown",
            "not_applicable",
        }
    ),
    "storage_namespace": frozenset({"variant", "owned_legacy", "unknown"}),
    "reuse_rejection": frozenset(
        {
            "no_eligible_candidate",
            "validation_failed",
            "plan_mismatch",
            "custom_artwork_unverifiable",
            "probe_unavailable",
        }
    ),
    "sidecar_kind": frozenset({"metadata", "thumbnail", "library_artwork"}),
    "sidecar_context": frozenset({"committed_media", "reused_media"}),
    "sidecar_outcome": frozenset(
        {
            "created",
            "repaired",
            "rewritten",
            "already_present",
            "not_requested",
            "unavailable",
            "failed",
            "unknown",
        }
    ),
    "reuse_result": frozenset({"hit", "miss", "unavailable"}),
    "help_target": frozenset({"menu", "feedback", "review", "welcome"}),
    "ui_blocker": frozenset({"closed", "panel", "grab", "unknown"}),
    "view": frozenset({"forge", "library", "watch", "activity", "unknown"}),
    "row_count_bucket": frozenset({"0", "1_25", "26_500", "501_5000", "5001_plus"}),
    "lag_bucket": frozenset(
        {"under_50ms", "50_99ms", "100_249ms", "250_999ms", "1000ms_plus"}
    ),
    "window_change": frozenset({"resize", "state"}),
    "lag_measurement": frozenset({"ui_pump_delay"}),
    "failure_code": FAILURE_CODES,
    "cookie_access": frozenset({"disabled", "browser", "file", "unconfigured"}),
    "provider": frozenset({"youtube", "other"}),
    "encoder_preference": frozenset({"cpu", "nvidia"}),
    "architecture": frozenset({"arm64", "x64", "other"}),
    "update_stage": frozenset(
        {
            "check",
            "download",
            "handoff",
            "waiting_for_exit",
            "downloading_repair",
            "backing_up",
            "verifying",
            "installing",
            "verifying_install",
            "checking_data",
            "relaunching",
            "unknown",
        }
    ),
    "preset": frozenset(
        {"everyday", "streaming", "editing", "sharing", "ctv", "custom", "legacy"}
    ),
    "encoder": frozenset({"cpu", "nvidia", "copy"}),
    "rate_control": frozenset({"cbr", "quality", "copy"}),
    "input_kind": frozenset({"single", "playlist", "url_list", "local"}),
    "resolution": frozenset(
        {"audio", "sd", "720p", "1080p", "1440p", "2160p", "above_2160p"}
    ),
    "source_resolution": frozenset(
        {"audio", "sd", "720p", "1080p", "1440p", "2160p", "above_2160p"}
    ),
    "artwork": frozenset({"none", "thumbnail", "custom"}),
    "metadata": frozenset({"enabled", "disabled"}),
    "outcome": frozenset({"complete", "partial", "failed", "stopped", "skipped"}),
    "duration_bucket": frozenset(
        {"under_10s", "under_1m", "under_5m", "under_30m", "under_2h", "2h_plus"}
    ),
    "processing_bucket": frozenset(
        {"under_10s", "under_1m", "under_5m", "under_30m", "under_2h", "2h_plus"}
    ),
    "wait_bucket": frozenset(
        {"under_10s", "under_1m", "under_5m", "under_30m", "under_2h", "2h_plus"}
    ),
    "size_bucket": frozenset(
        {"under_1mb", "under_10mb", "under_100mb", "under_1gb", "1gb_plus"}
    ),
    "item_count_bucket": frozenset({"1", "2_5", "6_20", "21_100", "101_plus"}),
    "theme": frozenset({"violet", "cobalt", "jade", "ember", "rose", "custom"}),
}


# Explicit projection: unknown/future preferences are excluded until reviewed.
SETTINGS_CHOICES = {
    "local_video_profile": {
        "1080p Standard (Recommended)",
        "2160p 4K",
        "1080p Strict 2 Mbps CBR",
        "720p Compact",
    },
    "manual_crf": {str(value) for value in range(52)},
    "output_type": {"MP4", "MP3", "Original audio"},
    "quality": {
        "Best available up to 4K",
        "2160p / 4K",
        "1440p / 2K",
        "1080p Full HD",
        "720p HD",
        "480p",
        "360p",
    },
    "export_mode": {
        "Everyday",
        "Streaming",
        "Editing",
        "Sharing",
        "Auto CBR",
        "Strict Compliance",
        "Manual Override",
    },
    "manual_audio_codec": {"AAC", "MP3"},
    "manual_sample_rate": {"44100", "48000"},
    "manual_channels": {"Mono", "Stereo"},
    "manual_preset": {"ultrafast", "veryfast", "fast", "medium", "slow"},
    "manual_rate_control": {"CBR", "Quality"},
    "mp3_quality": {
        "Maximum — 320 kbps CBR",
        "High — 256 kbps CBR",
        "Standard — 192 kbps CBR",
        "Compact — 128 kbps CBR",
    },
    "mp3_sample_rate": {"Preserve source", "48 kHz — video / DAW", "44.1 kHz — music"},
    "mp3_channels": {"Preserve source", "Stereo", "Mono"},
    "mp3_cover_art_mode": {"No Art", "YouTube art", "Custom art"},
    "appearance_theme": {
        "Violet",
        "Cobalt",
        "Jade",
        "Ember",
        "Rose",
        "Custom",
        "violet",
        "cobalt",
        "jade",
        "ember",
        "rose",
        "custom",
    },
}
SETTINGS_BOOLEANS = {
    "single_video_only",
    "use_nvenc",
    "embed_thumbnail",
    "write_thumbnail",
    "embed_metadata",
    "write_info_json",
    "mp3_embed_metadata",
}
for _key, _choices in SETTINGS_CHOICES.items():
    DIMENSION_CHOICES["setting_" + _key] = frozenset(_choices)
for _key in SETTINGS_BOOLEANS:
    DIMENSION_CHOICES["setting_" + _key] = frozenset({"enabled", "disabled"})
for _key in ("manual_video_bitrate", "manual_audio_bitrate"):
    DIMENSION_CHOICES["setting_" + _key] = frozenset(
        {
            "under_32",
            "32_127",
            "128_319",
            "320_999",
            "1000_1999",
            "2000_4999",
            "5000_9999",
            "10000_plus",
        }
    )


def settings_dimensions(values: Mapping) -> dict[str, str]:
    result = {}
    for key, choices in SETTINGS_CHOICES.items():
        value = values.get(key)
        if isinstance(value, str) and value in choices:
            result["setting_" + key] = value
    for key in SETTINGS_BOOLEANS:
        value = values.get(key)
        if type(value) is bool:
            result["setting_" + key] = "enabled" if value else "disabled"
    for key in ("manual_video_bitrate", "manual_audio_bitrate"):
        value = values.get(key)
        if type(value) not in (str, int) or not str(value).isdigit():
            continue
        number = int(str(value))
        if not 0 <= number <= 100000:
            continue
        for upper, label in (
            (32, "under_32"),
            (128, "32_127"),
            (320, "128_319"),
            (1000, "320_999"),
            (2000, "1000_1999"),
            (5000, "2000_4999"),
            (10000, "5000_9999"),
            (100001, "10000_plus"),
        ):
            if number < upper:
                result["setting_" + key] = label
                break
    return result


def validate_dimensions(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("telemetry dimensions must be an object")
    result = dict(value)
    for key, item in result.items():
        if not isinstance(item, str):
            raise TypeError("unsupported telemetry dimension")
        if key in DIMENSION_CHOICES and item in DIMENSION_CHOICES[key]:
            continue
        if key in DIMENSION_PATTERNS and re.fullmatch(DIMENSION_PATTERNS[key], item):
            continue
        if key in DIMENSION_RANGES and re.fullmatch(r"0|[1-9][0-9]{0,5}", item):
            low, high = DIMENSION_RANGES[key]
            if low <= int(item) <= high:
                continue
        raise ValueError("unsupported telemetry dimension")
    if (
        len(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        > 2048
    ):
        raise ValueError("telemetry dimensions exceed limit")
    return result


PRESENTATION_REQUIRED_DIMENSIONS = frozenset(
    [
        "mode_eligible_bucket",
        "query_state",
        "filter_state",
        "presentation_surface",
        "presentation_mode",
        "mode_origin",
        "presentation_population",
        "presentation_trigger",
        "presentation_visibility",
        "presentation_scene",
        "eligible_bucket",
        "matching_bucket",
        "rendered_bucket",
        "artwork_expected_bucket",
        "artwork_displayed_bucket",
        "artwork_unavailable_bucket",
        "artwork_state",
        "missing_image_bucket",
        "missing_image_role",
        "presentation_sampling",
        "presentation_audit",
        "lag_bucket",
        "lag_measurement",
        "artwork_batch",
    ]
)
LIBRARY_REQUIRED_DIMENSIONS = frozenset(
    ["library_intent", "library_subject", "library_boundary"]
)


def validate_operation_fields(
    feature: str | None, dimensions: Mapping[str, str], action: str | None = None
) -> None:
    if feature in OPERATION_FEATURES:
        required = {
            "operation_id",
            "operation_step",
            "instrumentation",
            "build_revision",
        }
        if not required.issubset(dimensions):
            raise ValueError("operation correlation is required")
    elif "operation_id" in dimensions or "operation_step" in dimensions:
        raise ValueError("unexpected operation correlation")
    if feature == "run_control_operation":
        if not {
            "run_control_action",
            "run_control_origin",
            "run_control_owner",
        }.issubset(dimensions):
            raise ValueError("run control context is required")
        expected_owner = {"admitted": "current", "rejected": "retired"}.get(
            action or ""
        )
        if dimensions["run_control_owner"] != expected_owner:
            raise ValueError("run control owner conflicts with admission")
    if feature == "run_recovery_operation":
        if not {
            "recovery_cause",
            "recovery_stage",
            "recovery_schema",
            "recovery_disposition",
        }.issubset(dimensions):
            raise ValueError("run recovery context is required")
        restored = action == "restored_without_retry"
        if restored != (dimensions["recovery_disposition"] == "restored_without_retry"):
            raise ValueError("recovery disposition conflicts with action")
        if restored and (
            dimensions["recovery_cause"] != "missing_retry_url"
            or dimensions["recovery_stage"] != "terminal_restore"
            or "item_count_bucket" not in dimensions
        ):
            raise ValueError("restored source context is required")

    if feature == "watch_queue_operation":
        if not {
            "queue_kind",
            "queue_order",
            "item_count_bucket",
            "queue_position_bucket",
            "queue_completed_bucket",
        }.issubset(dimensions):
            raise ValueError("watch queue context is required")
        failure_fields = {"queue_failure_boundary", "queue_failure_reason"}
        if action == "failed":
            if not failure_fields.issubset(dimensions):
                raise ValueError("watch queue failure context is required")
        elif failure_fields.intersection(dimensions):
            raise ValueError("healthy watch queue cannot have failure context")
    if feature == "library_action_operation":
        if not LIBRARY_REQUIRED_DIMENSIONS.issubset(dimensions):
            raise ValueError("library action context is required")
        boundaries = {
            "requested": {"validation", "confirmation"},
            "admitted": {"queue", "launch"},
            "completed": {"queue", "launch", "completed"},
            "rejected": {"validation", "queue", "launch", "history", "closing"},
            "duplicate_focused": {"duplicate"},
            "cancelled": {"confirmation"},
            "annotation_retained": {"annotation"},
        }
        if dimensions["library_boundary"] not in boundaries.get(action or "", set()):
            raise ValueError("library action boundary conflicts with outcome")
    if feature == "presentation_operation":
        if not PRESENTATION_REQUIRED_DIMENSIONS.issubset(dimensions):
            raise ValueError("presentation context is required")
        missing = dimensions["missing_image_role"] != "none"
        if missing == (dimensions["missing_image_bucket"] == "0"):
            raise ValueError("missing image evidence conflicts")
        if action == "fault" and not missing:
            raise ValueError("fault needs missing image evidence")
        if action in {"observed", "recovered", "settled"} and missing:
            raise ValueError("healthy presentation cannot have missing images")
        if (
            action in {"settled", "superseded", "retired"}
            and "presentation_replacement" not in dimensions
        ):
            raise ValueError("presentation terminal context is required")
        if action == "superseded" and dimensions["presentation_replacement"] == "none":
            raise ValueError("supersession needs a replacement trigger")
        if action == "retired" and dimensions["presentation_scene"] != "retired":
            raise ValueError("retirement needs a retired scene")
        if action == "settled" and (
            dimensions["presentation_scene"] == "awaiting"
            or dimensions["artwork_state"] in {"pending", "decoded_awaiting_render"}
        ):
            raise ValueError("pending presentation cannot be settled")
        if action == "sampled" and dimensions["presentation_sampling"] == "full":
            raise ValueError("sampling needs an explicit limit")


def attempt_identifier(install_id: str, run_id: str) -> str:
    """Installation-scoped opaque correlation; never emit the local run key."""
    return str(uuid.uuid5(uuid.UUID(install_id), "vodforge:attempt:" + run_id))


def time_bucket(seconds: float) -> str:
    for upper, label in (
        (10, "under_10s"),
        (60, "under_1m"),
        (300, "under_5m"),
        (1800, "under_30m"),
        (7200, "under_2h"),
    ):
        if seconds < upper:
            return label
    return "2h_plus"


def export_dimensions(job: object) -> dict[str, str]:
    """Configured intent only; actual encoder/output facts belong to completion."""
    mode = getattr(getattr(job, "export_mode", None), "value", "")
    preset = {
        "Auto CBR": "ctv",
        "Manual Override": "custom",
        "Strict Compliance": "legacy",
    }.get(mode, mode.lower())
    result = (
        {"preset": preset}
        if preset in DIMENSION_CHOICES["preset"]
        and getattr(getattr(job, "output_type", None), "value", "") == "MP4"
        else {}
    )
    result["cookie_access"] = (
        "disabled"
        if not getattr(job, "use_cookies", False)
        else "file"
        if getattr(job, "cookie_file", None)
        else "browser"
        if getattr(job, "cookie_browser", None)
        else "unconfigured"
    )
    host = (urlsplit(getattr(job, "url", "")).hostname or "").lower()
    result["provider"] = (
        "youtube"
        if host
        in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "music.youtube.com",
        }
        else "other"
    )
    result["encoder_preference"] = (
        "nvidia" if getattr(job, "use_nvenc", False) else "cpu"
    )
    machine = platform.machine().lower()
    result["architecture"] = (
        "arm64"
        if machine in {"arm64", "aarch64"}
        else "x64"
        if machine in {"amd64", "x86_64"}
        else "other"
    )
    result["input_kind"] = (
        "url_list"
        if getattr(job, "batch_mode", False)
        else "single"
        if getattr(job, "single_video_only", True)
        or not parse_qs(urlsplit(getattr(job, "url", "")).query).get("list")
        else "playlist"
    )
    count = max(1, len(getattr(job, "urls", [])))
    result["item_count_bucket"] = (
        "1"
        if count == 1
        else "2_5"
        if count <= 5
        else "6_20"
        if count <= 20
        else "21_100"
        if count <= 100
        else "101_plus"
    )
    if result["input_kind"] == "playlist":
        result.pop("item_count_bucket", None)
    result["metadata"] = (
        "enabled" if getattr(job, "embed_metadata", False) else "disabled"
    )
    mp3 = getattr(job, "mp3_settings", None)
    if (
        getattr(getattr(job, "output_type", None), "value", "") == "MP3"
        and mp3 is not None
    ):
        result["artwork"] = (
            "none"
            if not mp3.embed_cover_art
            else "custom"
            if mp3.custom_cover_art_path
            else "thumbnail"
        )
        result["metadata"] = "enabled" if mp3.embed_metadata else "disabled"
    return result


def job_intent_dimensions(job: object) -> dict[str, str]:
    output = getattr(getattr(job, "output_type", None), "value", "")
    values = {
        "output_type": output,
        "quality": getattr(job, "quality_label", None),
        "export_mode": getattr(getattr(job, "export_mode", None), "value", None),
        **{key: getattr(job, key, None) for key in SETTINGS_BOOLEANS},
    }
    manual = getattr(job, "manual_settings", None)
    if (
        output == "MP4"
        and values["export_mode"] == "Manual Override"
        and manual is not None
    ):
        values.update(
            manual_crf=str(manual.video_crf) if manual.video_crf is not None else None,
            manual_video_bitrate=manual.video_bitrate_kbps,
            manual_audio_bitrate=manual.audio_bitrate_kbps,
            manual_sample_rate=str(manual.audio_sample_rate),
            manual_channels={1: "Mono", 2: "Stereo"}.get(manual.audio_channels),
            manual_audio_codec=manual.audio_codec.value,
            manual_preset=manual.x264_preset,
            manual_rate_control="Quality" if manual.video_crf is not None else "CBR",
        )
    mp3 = getattr(job, "mp3_settings", None)
    if output == "MP3" and mp3 is not None:
        values = {
            key: value
            for key, value in values.items()
            if key in {"output_type", "single_video_only"}
        }
        values.update(
            mp3_quality={
                320: "Maximum — 320 kbps CBR",
                256: "High — 256 kbps CBR",
                192: "Standard — 192 kbps CBR",
                128: "Compact — 128 kbps CBR",
            }.get(mp3.bitrate_kbps),
            mp3_sample_rate={
                "48000": "48 kHz — video / DAW",
                "44100": "44.1 kHz — music",
            }.get(str(mp3.sample_rate), "Preserve source"),
            mp3_channels={"1": "Mono", "2": "Stereo"}.get(
                str(mp3.channels), "Preserve source"
            ),
            mp3_embed_metadata=mp3.embed_metadata,
            mp3_cover_art_mode="Custom art"
            if mp3.custom_cover_art_path
            else "YouTube art"
            if mp3.embed_cover_art
            else "No Art",
        )
    return {**export_dimensions(job), **settings_dimensions(values)}


def resolution_bucket(height: float) -> str:
    for maximum, label in (
        (0, "audio"),
        (576, "sd"),
        (720, "720p"),
        (1080, "1080p"),
        (1440, "1440p"),
        (2160, "2160p"),
    ):
        if height <= maximum:
            return label
    return "above_2160p"


def measured_dimensions(
    probe: Mapping, *, source_height: float | None = None
) -> dict[str, str]:
    """Extract bucketed media facts only from an independently validated probe."""
    result: dict[str, str] = {}
    streams = probe.get("streams", [])
    videos = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
        and not stream.get("disposition", {}).get("attached_pic")
    ]
    result["resolution"] = (
        resolution_bucket(float(videos[0].get("height", 0))) if videos else "audio"
    )
    if source_height is not None:
        result["source_resolution"] = resolution_bucket(source_height)
    fmt = probe.get("format", {})
    try:
        result["duration_bucket"] = time_bucket(float(fmt["duration"]))
    except (KeyError, ValueError, TypeError):
        pass
    try:
        size = float(fmt["size"])
        result["size_bucket"] = next(
            (
                label
                for maximum, label in (
                    (1048576, "under_1mb"),
                    (10485760, "under_10mb"),
                    (104857600, "under_100mb"),
                    (1073741824, "under_1gb"),
                )
                if size < maximum
            ),
            "1gb_plus",
        )
    except (KeyError, ValueError, TypeError):
        pass
    return result


def committed_export_dimensions(
    job, plan, probe, *, source_height=None
) -> dict[str, str]:
    """Successful command selection and probe facts; no media labels or paths."""
    from .models import ExportPlan, OutputType

    result = {
        **export_dimensions(job),
        **measured_dimensions(probe, source_height=source_height),
    }
    result.pop("item_count_bucket", None)
    result["encoder"] = (
        "nvidia"
        if isinstance(plan, ExportPlan)
        and job.use_nvenc
        and (plan.video_crf is None or plan.nvenc_cq is not None)
        else "cpu"
    )
    result["rate_control"] = (
        "quality"
        if isinstance(plan, ExportPlan) and plan.video_crf is not None
        else "cbr"
    )
    if job.output_type == OutputType.ORIGINAL:
        result.update(encoder="copy", rate_control="copy")
    return result
