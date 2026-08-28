import json
import inspect
import queue
import threading
import time
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import yt_downloader.app as app_module
from yt_downloader.history import history_output_dir, sanitize_history_record, upsert_history
from yt_downloader.app import (
    AudioExportPlan,
    CookieSource,
    DEFAULT_IGNORE_PLAYLISTS,
    RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS,
    AUDIO_BITRATE,
    AUDIO_SAMPLE_RATE,
    DownloadJob,
    DownloadOutcome,
    DownloaderApp,
    ExportPlan,
    ExportMode,
    ManualAudioCodec,
    EXPORT_MODES,
    Mp3ExportSettings,
    OutputType,
    QUALITY_OPTIONS,
    VIDEO_TARGET_BITRATE,
    ManualExportSettings,
    apply_playlist_context,
    apply_manual_export_settings,
    build_auto_export_plan,
    export_mode_description,
    export_mode_display_name,
    export_mode_from_display_name,
    build_mp3_export_plan,
    build_encoding_summary_display,
    build_encoding_summary_metadata,
    build_failed_encoding_summary_metadata,
    summary_label_color,
    build_description_display_text,
    clean_single_video_url,
    canonical_youtube_url,
    cookie_inputs_for_source,
    center_alpha_content,
    cached_thumbnail_path,
    existing_cached_thumbnail_path,
    legacy_cached_thumbnail_path,
    embed_custom_mp3_cover_art,
    existing_output_candidate_dirs,
    find_valid_existing_output,
    output_artifact_matches_plan,
    playlist_context_from_extraction,
    pointer_inside_widget_bounds,
    retry_url_for_item,
    single_video_url_requires_video_id_error,
    build_tags_display_text,
    build_vod_ffmpeg_command,
    choose_audio_bitrate_kbps,
    choose_best_audio_format,
    choose_best_video_format,
    choose_windows_output_directory,
    cleanup_legacy_encode_sidecars,
    compact_video_metadata,
    create_staging_dir,
    run_cancellable_blocking_step,
    format_duration,
    iter_video_infos,
    load_yt_dlp,
    package_downloaded_media_from_staging,
    append_batch_failure_report,
    apply_youtube_runtime_options,
    apply_ytdlp_cookie_options,
    best_thumbnail_for_download,
    format_ytdlp_user_error,
    parse_url_list_text,
    diagnostics_dir,
    download_bounded_url_bytes,
    download_job_display_title,
    bounded_window_size,
    download_layout_mode,
    bundled_asset_path,
    configure_windows_app_identity,
    flatten_alpha_image,
    focus_icon_color_variant,
    focus_hero_thumbnail_visible,
    focus_library_layout_mode,
    focus_library_vertical_layout_mode,
    focus_library_horizontal_padding,
    pixel_table_visible_row_window,
    focus_metadata_profile_text,
    focus_layout_mode,
    focus_run_deck_capacity,
    focus_wheel_pixels,
    pixel_scroll_target,
    initial_window_geometry,
    is_metadata_preview,
    accumulated_row_scroll,
    library_thumbnail_size,
    thumbnail_size_within,
    render_monochrome_icon,
    rounded_contain_image,
    rounded_cover_image,
    rounded_fit_image,
    runtime_window_icon_asset,
    metadata_layout_mode,
    metadata_indices_for_output_type,
    metadata_output_type,
    metadata_run_key,
    preview_output_summary_display,
    responsive_table_stretch_indices,
    resized_table_column_width,
    stretched_table_column_widths,
    resolved_video_output_target,
    platform_font_families,
    prepare_batch_item_url,
    prepare_custom_cover_art,
    playlist_folder_name,
    process_download_from_preflight,
    run_ffprobe_json,
    runtime_version_command,
    save_thumbnail_image,
    save_cached_thumbnail_image,
    save_custom_cached_thumbnail_image,
    staging_output_template,
    transcode_temp_paths,
    transcode_to_vod_streaming_settings,
    terminate_and_reap_process,
    runtime_executable_candidates,
    video_list_row_values,
    video_file_name,
    video_output_dir,
    youtube_thumbnail_size,
    youtube_url_playlist_id,
    youtube_url_video_id,
    ytdlp_ffmpeg_location,
    validate_output_artifact,
    validate_output_directory_access,
    write_compact_video_metadata,
)


def test_platform_diagnostics_paths_follow_native_conventions(tmp_path: Path):
    assert diagnostics_dir(platform_name="darwin", home=tmp_path) == tmp_path / "Library" / "Logs" / "VODForge"
    assert diagnostics_dir(platform_name="linux", home=tmp_path) == tmp_path / ".vodforge" / "logs"
    assert diagnostics_dir(platform_name="win32", home=tmp_path, local_app_data="C:/Users/Test/AppData/Local") == (
        Path("C:/Users/Test/AppData/Local") / "VODForge" / "logs"
    )


def test_diagnostics_writer_reuses_and_resets_its_line_buffered_sink(monkeypatch, tmp_path: Path):
    log_path = tmp_path / "latest.log"
    monkeypatch.setattr(app_module, "DIAGNOSTICS_LOG_PATH", log_path)

    app_module.write_diagnostic("first")
    first_handle = app_module._DIAGNOSTICS_LOG_HANDLE
    app_module.write_diagnostic("second")

    assert app_module._DIAGNOSTICS_LOG_HANDLE is first_handle
    assert "first" in log_path.read_text(encoding="utf-8")
    assert "second" in log_path.read_text(encoding="utf-8")

    app_module.reset_diagnostics_log()
    assert log_path.read_text(encoding="utf-8") == ""
    app_module.write_diagnostic("after reset")
    assert "after reset" in log_path.read_text(encoding="utf-8")
    with app_module._DIAGNOSTICS_LOG_LOCK:
        app_module._DIAGNOSTICS_LOG_HANDLE.close()
        app_module._DIAGNOSTICS_LOG_HANDLE = None
        app_module._DIAGNOSTICS_LOG_HANDLE_PATH = None


def test_persistent_activity_log_survives_reopen_and_stays_bounded(monkeypatch, tmp_path: Path):
    log_path = tmp_path / "activity.log"
    monkeypatch.setattr(app_module, "ACTIVITY_LOG_MAX_BYTES", 120)
    monkeypatch.setattr(app_module, "ACTIVITY_LOG_COMPACT_BYTES", 80)
    app_module.prepare_activity_log(log_path)

    for index in range(12):
        app_module.append_activity_log(f"activity line {index:02d}", log_path)

    with app_module._ACTIVITY_LOG_LOCK:
        app_module._close_activity_log_locked()
    app_module.prepare_activity_log(log_path)
    restored = app_module.load_activity_log_tail(log_path)

    assert "activity line 11" in restored
    assert "activity line 00" not in restored
    assert log_path.stat().st_size <= app_module.ACTIVITY_LOG_COMPACT_BYTES


def test_persistent_activity_log_does_not_store_cookie_file_path(tmp_path: Path):
    log_path = tmp_path / "activity.log"

    app_module.append_activity_log(
        "Loaded YouTube cookies file: /Users/example/private/cookies.txt",
        log_path,
    )
    with app_module._ACTIVITY_LOG_LOCK:
        app_module._close_activity_log_locked()

    assert app_module.load_activity_log_tail(log_path) == "Loaded YouTube cookies file."
    assert "/Users/example/private/cookies.txt" not in log_path.read_text(encoding="utf-8")


def test_platform_fonts_use_macos_and_windows_system_families():
    assert platform_font_families("darwin") == ("Helvetica Neue", "Menlo")
    assert platform_font_families("win32") == ("Segoe UI", "Cascadia Mono")
    assert platform_font_families("linux") == ("TkDefaultFont", "TkFixedFont")


def test_yt_dlp_loader_imports_once_and_reuses_the_module(monkeypatch):
    sentinel = object()
    calls: list[str] = []
    monkeypatch.setattr(app_module, "yt_dlp", None)
    monkeypatch.setattr(app_module, "YTDLP_IMPORT_ERROR", None)
    monkeypatch.setattr(app_module, "_YTDLP_IMPORT_ATTEMPTED", False)
    monkeypatch.setattr(
        app_module.importlib,
        "import_module",
        lambda name: calls.append(name) or sentinel,
    )

    assert load_yt_dlp() is sentinel
    assert load_yt_dlp() is sentinel
    assert calls == ["yt_dlp"]


def test_macos_uses_bundle_icns_without_a_runtime_png_override():
    assert runtime_window_icon_asset("darwin") is None
    assert runtime_window_icon_asset("win32") == "VODForge.ico"
    assert runtime_window_icon_asset("linux") == "VODForge.png"


def test_focus_icon_colors_select_exact_vector_variants():
    assert focus_icon_color_variant(app_module.THEME["muted"]) == "muted"
    assert focus_icon_color_variant(app_module.THEME["accent"]) == "accent"
    assert focus_icon_color_variant(app_module.THEME["text"]) == "text"
    assert focus_icon_color_variant("#FFFFFF") == "white"
    assert focus_icon_color_variant("#123456") is None


def test_initial_window_size_leaves_room_for_screen_chrome():
    assert bounded_window_size(1920, 1080) == (1180, 900)
    assert bounded_window_size(1366, 768) == (1180, 648)
    assert bounded_window_size(1280, 720) == (1180, 600)
    assert bounded_window_size(800, 600) == (776, 552)


def test_initial_window_geometry_is_centered_and_dock_safe():
    assert initial_window_geometry(1440, 900, platform_name="darwin") == "1180x780+130+28"
    assert initial_window_geometry(1920, 1080, platform_name="win32") == "1180x900+370+90"


def test_download_layout_uses_inline_details_whenever_they_fit():
    assert download_layout_mode(1120, 480) == "wide-expanded"
    assert download_layout_mode(1120, 430) == "wide-expanded"
    assert download_layout_mode(1120, 380) == "wide-compact"
    assert download_layout_mode(900, 700) == "stacked-expanded"
    assert download_layout_mode(900, 560) == "stacked-compact"


def test_unresolved_run_titles_never_expose_the_raw_source_url(tmp_path: Path):
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=private-source-token",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    assert download_job_display_title(job) == "Preparing video run"
    assert download_job_display_title(job, queued=True) == "Queued video run"
    job.preview_info = {"title": "Resolved title"}
    assert download_job_display_title(job) == "Resolved title"


def test_focus_run_records_use_one_active_run_authority_without_preview_duplicate(tmp_path: Path):
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    active_info = {"id": "active-id", "title": "Current title", "vodforge_output_type": "MP4"}
    active_job = DownloadJob(
        url="https://www.youtube.com/watch?v=active-id",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
        preview_info=dict(active_info),
        metadata_keys={metadata_run_key(active_info)},
    )
    app = DownloaderApp.__new__(DownloaderApp)
    app._focus_preview_runs = None
    app._focus_active_override = False
    app.active_job = active_job
    app.worker = None
    app.pending_jobs = []
    app._terminal_jobs = []
    app.metadata_items = [
        active_info,
        {
            "id": "older",
            "title": "Older preview",
            "vodforge_output_type": "MP4",
            "vodforge_preview_complete": True,
        },
    ]
    app.url_var = Value("")
    app.focus_active_title_var = Value("stale previous title")
    app.focus_active_detail_var = Value("Current creator")
    app.status_var = Value("Downloading")
    app.progress_var = Value(54)

    records = app._focus_run_records()

    assert [(record["kind"], record["title"]) for record in records] == [
        ("active", "Current title"),
        ("preview", "Older preview"),
    ]
    assert all(record["title"] != active_job.url for record in records)


def test_failed_run_replaces_its_ephemeral_metadata_card(tmp_path: Path):
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    failed_info = {"id": "failed-id", "title": "Resolved failure", "vodforge_output_type": "MP4"}
    failed_job = DownloadJob(
        url="https://youtu.be/failed-id",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
        preview_info=dict(failed_info),
        metadata_keys={metadata_run_key(failed_info)},
        terminal_status="Failed",
        terminal_message="No output produced",
    )
    app = DownloaderApp.__new__(DownloaderApp)
    app._focus_preview_runs = None
    app._focus_active_override = False
    app.active_job = None
    app.worker = None
    app.pending_jobs = []
    app._terminal_jobs = [failed_job]
    app.metadata_items = [failed_info]
    app.url_var = Value("")

    records = app._focus_run_records()

    assert len(records) == 1
    assert records[0]["kind"] == "failed"
    assert records[0]["title"] == "Resolved failure"
    assert records[0]["job"] is failed_job


def test_failed_run_retry_creates_a_fresh_run_identity_with_the_same_settings(tmp_path: Path):
    failed_job = DownloadJob(
        url="https://youtu.be/retry-id",
        output_dir=tmp_path,
        output_type=OutputType.MP3,
        quality_label="Best available up to 4K",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(bitrate_kbps=320),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=["producer"],
        preview_info={"id": "retry-id", "title": "Retry me", "vodforge_output_type": "MP3"},
        metadata_keys={("retry-id", "MP3")},
        terminal_status="Failed",
        terminal_message="Temporary failure",
    )
    app = DownloaderApp.__new__(DownloaderApp)
    app._terminal_jobs = [failed_job]
    app.active_job = None
    app.worker = None
    launched: list[DownloadJob] = []
    app._launch_download_job = launched.append

    app._retry_terminal_job(failed_job)

    assert app._terminal_jobs == []
    assert len(launched) == 1
    retry_job = launched[0]
    assert retry_job.run_id != failed_job.run_id
    assert retry_job.url == failed_job.url
    assert retry_job.output_type == OutputType.MP3
    assert retry_job.mp3_settings.bitrate_kbps == 320
    assert retry_job.tags == ["producer"]
    assert retry_job.metadata_keys == set()
    assert retry_job.terminal_status is None


def test_manual_override_requires_room_for_all_inline_fields():
    assert download_layout_mode(1120, 560, manual_override=True) == "wide-compact"
    assert download_layout_mode(1120, 600, manual_override=True) == "wide-expanded"
    assert download_layout_mode(900, 760, manual_override=True) == "stacked-compact"
    assert download_layout_mode(900, 840, manual_override=True) == "stacked-expanded"


def test_metadata_layout_keeps_all_surfaces_visible_at_each_width():
    assert metadata_layout_mode(1120) == "three-column"
    assert metadata_layout_mode(700) == "three-column"
    assert metadata_layout_mode(699) == "two-column"


def test_focus_layout_collapses_before_live_details_are_clipped():
    assert focus_layout_mode(1180, 780) == "wide"
    assert focus_layout_mode(1000, 720) == "balanced"
    assert focus_layout_mode(920, 650) == "compact"
    assert focus_layout_mode(820, 560) == "compact"


def test_fraction_addressed_pixel_scroll_uses_the_visible_viewport_ratio():
    # Canvas-style surfaces expose a visible fraction; converting a 36 px
    # gesture through that ratio must move precisely and clamp at the tail.
    target = pixel_scroll_target(0.0, 0.1, 47, 36)

    assert target == pytest.approx(0.0765957447)
    assert pixel_scroll_target(0.9, 1.0, 47, 36) == pytest.approx(0.9)
    assert pixel_scroll_target(0.0, 1.0, 47, 36) == 0.0


def test_tooltip_hit_testing_uses_exact_visible_widget_bounds():
    class WidgetBounds:
        def __init__(self, left, top, width, height, *, mapped=True):
            self.left = left
            self.top = top
            self.width = width
            self.height = height
            self.mapped = mapped

        def winfo_ismapped(self):
            return self.mapped

        def winfo_rootx(self):
            return self.left

        def winfo_rooty(self):
            return self.top

        def winfo_width(self):
            return self.width

        def winfo_height(self):
            return self.height

    public = WidgetBounds(100, 50, 48, 24)
    cookies = WidgetBounds(148, 50, 76, 24)
    hidden_browser = WidgetBounds(224, 50, 64, 24, mapped=False)

    targets = (public, cookies, hidden_browser)
    assert pointer_inside_widget_bounds(targets, 100, 50)
    assert pointer_inside_widget_bounds(targets, 223, 73)
    assert not pointer_inside_widget_bounds(targets, 224, 60)
    assert not pointer_inside_widget_bounds(targets, 120, 74)


def test_tooltips_share_one_delayed_pointer_verified_window_controller():
    tooltip_source = inspect.getsource(app_module.ToolTip)
    controller_source = inspect.getsource(app_module._TooltipController)
    selector_source = inspect.getsource(app_module.SegmentedSelector)

    assert "_vodforge_tooltip_controller" in tooltip_source
    assert "targets_provider" in tooltip_source
    assert 'target.bind("<ButtonPress>"' in tooltip_source
    assert "TOOLTIP_DELAY_MS" in controller_source
    assert "TOOLTIP_POINTER_POLL_MS" in controller_source
    assert "not tooltip.contains_pointer()" in controller_source
    assert "def _destroy_tip" in controller_source
    assert "self._cancel_pointer_poll()" in controller_source
    assert "def tooltip_targets" in selector_source
    assert "tuple(self._labels.values())" in selector_source


def test_focus_library_layout_protects_selected_item_at_medium_widths():
    assert focus_library_layout_mode(1180) == "wide"
    assert focus_library_layout_mode(1080) == "wide"
    assert focus_library_layout_mode(1000) == "wide"
    assert focus_library_layout_mode(999) == "balanced"
    assert focus_library_layout_mode(920) == "balanced"
    assert focus_library_layout_mode(919) == "compact"


def test_focus_library_vertical_layout_protects_description_before_it_can_collapse():
    assert focus_library_vertical_layout_mode(920) == "wide"
    assert focus_library_vertical_layout_mode(919) == "balanced"
    assert focus_library_vertical_layout_mode(740) == "balanced"
    assert focus_library_vertical_layout_mode(739) == "compact"


def test_table_spare_width_expands_every_eligible_column_and_respects_limits():
    assert stretched_table_column_widths([40, 100, 60], 260, {0: None, 1: None}) == [70, 130, 60]
    assert stretched_table_column_widths([40, 100, 60], 300, {0: 50, 1: None}) == [50, 190, 60]
    assert stretched_table_column_widths([40, 100, 60], 260, {}) == [40, 100, 60]
    assert stretched_table_column_widths([80, 100], 120, {0: None, 1: None}) == [80, 100]


def test_manual_table_widths_stay_exact_while_other_columns_fill_the_viewport():
    columns = ("index", "title", "duration")
    widths = [44, 360, 72]
    eligible = set(columns)

    title_manual = responsive_table_stretch_indices(
        columns,
        eligible,
        {"title"},
        last_resized_column="title",
    )
    assert title_manual == [0, 2]
    assert stretched_table_column_widths(
        widths,
        600,
        {index: None for index in title_manual},
    ) == [106, 360, 134]
    assert stretched_table_column_widths(
        widths,
        800,
        {index: None for index in title_manual},
    ) == [206, 360, 234]

    all_manual = responsive_table_stretch_indices(
        columns,
        eligible,
        set(columns),
        last_resized_column="duration",
    )
    assert all_manual == [0, 1]
    assert stretched_table_column_widths(
        widths,
        800,
        {index: None for index in all_manual},
    ) == [206, 522, 72]


def test_ultrawide_library_workspace_is_bounded_and_centered():
    assert focus_library_horizontal_padding(1180) == 18
    assert focus_library_horizontal_padding(1600) == 18
    assert focus_library_horizontal_padding(2560) == 480
    assert focus_library_horizontal_padding(2000) == focus_library_horizontal_padding(2015)
    assert focus_library_horizontal_padding(2016) > focus_library_horizontal_padding(2015)


def test_virtual_table_clamps_a_stale_scroll_offset_after_filtering_to_fewer_rows():
    offset, first_row, last_row = pixel_table_visible_row_window(
        total_rows=3,
        row_height=30,
        viewport_height=60,
        y_offset=1200,
    )

    assert offset == 30
    assert (first_row, last_row) == (0, 3)


def test_library_column_resize_clamps_only_at_the_column_minimum():
    assert resized_table_column_width(320, 80, 200) == 400
    assert resized_table_column_width(320, -40, 200) == 280
    assert resized_table_column_width(320, -500, 200) == 200


def test_preview_and_completed_profiles_omit_redundant_media_placeholders():
    mp4_preview = {"vodforge_output_type": "MP4"}
    mp3_completed = {
        "vodforge_output_type": "MP3",
        "vodforge_encoding_summary": {
            "output": {
                "Resolution": "Audio only",
                "Output rate-control mode": "CBR",
            }
        },
    }
    mp4_completed = {
        "vodforge_output_type": "MP4",
        "vodforge_encoding_summary": {
            "output": {
                "Resolution": "1920x1080",
                "Output rate-control mode": "CBR",
            }
        },
    }

    assert focus_metadata_profile_text(mp4_preview, "preview") == "MP4  •  Preview complete"
    assert focus_metadata_profile_text(mp3_completed, "completed") == "MP3  •  CBR"
    assert focus_metadata_profile_text(mp4_completed, "completed") == "MP4  •  1920x1080  •  CBR"
    assert focus_metadata_profile_text({"vodforge_output_type": "MP4"}, "failed") == "MP4"
    assert preview_output_summary_display() == (
        "Output status: Preview complete\n"
        "Output file path: Not produced\n"
        "Next action: Start download in Forge"
    )


def test_only_explicit_completed_metadata_is_a_preview():
    assert is_metadata_preview({"id": "preview", "vodforge_preview_complete": True})
    assert not is_metadata_preview({"id": "active-metadata"})
    assert not is_metadata_preview(
        {
            "id": "terminal-preview",
            "vodforge_preview_complete": True,
            "vodforge_terminal_status": "Failed",
        }
    )
    assert not is_metadata_preview(
        {
            "id": "saved-preview",
            "vodforge_preview_complete": True,
            "vodforge_output_dir": "/tmp/saved-preview",
        }
    )


def test_bundled_asset_path_uses_packaged_or_source_asset_root(tmp_path: Path):
    assert bundled_asset_path("VODForge.ico", meipass=tmp_path) == tmp_path / "assets" / "VODForge.ico"
    assert bundled_asset_path("VODForge.png", meipass=None, repo_root=tmp_path) == tmp_path / "assets" / "VODForge.png"


def test_rounded_cover_image_fills_slot_and_keeps_only_rounded_corners_transparent():
    source = Image.new("RGB", (640, 360), "#336699")

    rendered = rounded_cover_image(source, (160, 90), 10)

    assert rendered.size == (160, 90)
    assert rendered.mode == "RGBA"
    assert rendered.getpixel((0, 0))[3] == 0
    assert any(0 < rendered.getpixel((x, y))[3] < 255 for x in range(10) for y in range(10))
    assert rendered.getpixel((80, 45)) == (51, 102, 153, 255)


def test_youtube_thumbnail_slots_use_standard_16_by_9_geometry():
    assert youtube_thumbnail_size(152) == (152, 86)
    assert youtube_thumbnail_size(80) == (80, 45)
    assert youtube_thumbnail_size(64) == (64, 36)


def test_library_thumbnail_stays_16_by_9_but_caps_its_metadata_footprint():
    assert library_thumbnail_size(196) == (196, 110)
    assert library_thumbnail_size(320) == (240, 135)
    assert library_thumbnail_size(600) == (240, 135)


def test_thumbnail_size_is_bounded_without_cropping_or_distortion():
    assert thumbnail_size_within((1280, 720), (240, 135)) == (240, 135)
    assert thumbnail_size_within((480, 360), (240, 135)) == (180, 135)
    assert thumbnail_size_within((720, 1280), (240, 135)) == (76, 135)
    assert thumbnail_size_within((0, 360), (240, 135)) == (1, 1)


def test_rounded_fit_thumbnail_preserves_full_source_aspect_inside_maximum_box():
    source = Image.new("RGB", (480, 360), "#ff0000")
    rendered = rounded_fit_image(source, (240, 135), 10)

    assert rendered.size == (180, 135)
    assert rendered.getpixel((90, 67))[:3] == (255, 0, 0)


def test_focus_deck_capacity_and_hero_art_follow_available_width_not_density_label():
    assert focus_run_deck_capacity(1100) == 4
    assert focus_run_deck_capacity(880) == 4
    assert focus_run_deck_capacity(700) == 3
    assert focus_run_deck_capacity(500) == 2
    assert focus_run_deck_capacity(200) == 1
    assert focus_hero_thumbnail_visible(720)
    assert not focus_hero_thumbnail_visible(719)


def test_focus_run_drop_up_normalizes_trackpad_and_mouse_wheel_motion_to_pixels():
    assert focus_wheel_pixels(0) == 0
    assert focus_wheel_pixels(3) == -3
    assert focus_wheel_pixels(-7) == 7
    assert focus_wheel_pixels(0.4) == -1
    assert focus_wheel_pixels(-0.4) == 1
    assert focus_wheel_pixels(120) == -36
    assert focus_wheel_pixels(-120) == 36
    assert focus_wheel_pixels(480) == -72


def test_row_scrollers_accumulate_trackpad_pixels_without_amplifying_each_event():
    rows, remainder = accumulated_row_scroll(0, 7, 30)
    assert rows == 0
    assert remainder == 7
    rows, remainder = accumulated_row_scroll(remainder, 25, 30)
    assert rows == 1
    assert remainder == 2
    rows, remainder = accumulated_row_scroll(remainder, -33, 30)
    assert rows == -1
    assert remainder == -1


def test_rounded_contain_image_preserves_placeholder_artwork_without_cropping():
    source = Image.new("RGB", (100, 100), "#ff0000")

    rendered = rounded_contain_image(source, (160, 90), 10, "#121419")

    assert rendered.size == (160, 90)
    assert rendered.getpixel((0, 0))[3] == 0
    assert rendered.getpixel((8, 45)) == (18, 20, 25, 255)
    assert rendered.getpixel((80, 45)) == (255, 0, 0, 255)


def test_thumbnail_flattening_bakes_antialiased_edges_against_the_ui_background():
    source = Image.new("RGB", (640, 360), "#336699")
    rounded = rounded_cover_image(source, (160, 90), 10)

    rendered = flatten_alpha_image(rounded, "#08090a")

    assert rendered.size == (160, 90)
    assert rendered.getpixel((0, 0)) == (8, 9, 10, 255)
    assert rendered.getextrema()[3] == (255, 255)
    assert any(rendered.getpixel((x, y))[:3] not in {(8, 9, 10), (51, 102, 153)} for x in range(10) for y in range(10))


def test_center_alpha_content_moves_visible_bounds_to_the_canvas_center():
    source = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    for x in range(1, 10):
        for y in range(3, 15):
            source.putpixel((x, y), (255, 255, 255, 255))

    rendered = center_alpha_content(source)
    left, top, right, bottom = rendered.getchannel("A").getbbox() or (0, 0, 0, 0)

    assert abs((left + right) - 24) <= 1
    assert abs((top + bottom) - 24) <= 1


def test_monochrome_icon_renderer_preserves_hard_centers_and_antialiased_edges():
    source = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(12, 52):
        for y in range(20, 44):
            source.putpixel((x, y), (0, 0, 0, 255))

    rendered = render_monochrome_icon(source, 16, "#ffffff")

    assert rendered.size == (16, 16)
    assert rendered.getpixel((8, 8)) == (255, 255, 255, 255)
    assert rendered.getpixel((0, 0))[3] == 0


def test_accepted_run_resets_source_field_and_batch_state_for_the_next_send():
    class Variable:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Entry:
        focused = False

        def focus_set(self):
            self.focused = True

    app = object.__new__(DownloaderApp)
    app.batch_urls = ["https://example.test/one", "https://example.test/two"]
    app.url_list_file_var = Variable("two URLs loaded")
    app.url_var = Variable("https://example.test/one")
    app.focus_url_entry = Entry()

    DownloaderApp._reset_source_input_after_send(app)

    assert app.batch_urls == []
    assert app.url_list_file_var.get() == "No URL list loaded"
    assert app.url_var.get() == ""
    assert app.focus_url_entry.focused is True


def test_library_actions_feedback_keeps_one_fixed_button_width():
    class ButtonProbe:
        def __init__(self):
            self.calls = []

        def configure(self, **kwargs):
            self.calls.append(kwargs)

    app = object.__new__(DownloaderApp)
    app.focus_library_menu_button = ButtonProbe()
    app._focus_library_action_feedback_after_id = None
    scheduled = {}
    app.after_cancel = lambda _after_id: None

    def schedule(delay, callback):
        scheduled["delay"] = delay
        scheduled["callback"] = callback
        return "feedback-1"

    app.after = schedule

    DownloaderApp._run_library_copy_action(app, lambda: True)

    assert app.focus_library_menu_button.calls == [{"text": "Copied", "width": 7}]
    assert scheduled["delay"] == 900
    assert app._focus_library_action_feedback_after_id == "feedback-1"

    scheduled["callback"]()
    assert app.focus_library_menu_button.calls[-1] == {"text": "Actions", "width": 7}
    assert app._focus_library_action_feedback_after_id is None

    calls_before = list(app.focus_library_menu_button.calls)
    DownloaderApp._run_library_copy_action(app, lambda: False)
    assert app.focus_library_menu_button.calls == calls_before


def test_windows_app_identity_is_a_noop_on_other_platforms():
    assert configure_windows_app_identity("darwin") is False
    assert configure_windows_app_identity("linux") is False


def test_windows_output_picker_isolated_process_returns_network_path(monkeypatch: pytest.MonkeyPatch):
    class StartupInfo:
        dwFlags = 0

    monkeypatch.setattr(app_module.subprocess, "STARTUPINFO", StartupInfo, raising=False)
    monkeypatch.setattr(app_module.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    observed = {}

    def runner(command, **kwargs):
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        return app_module.subprocess.CompletedProcess(command, 0, '{"path":"\\\\\\\\nas\\\\vods"}', "")

    assert choose_windows_output_directory(r"Z:\\VODs", runner=runner) == r"\\nas\vods"
    assert observed["command"][:3] == ["powershell.exe", "-NoProfile", "-STA"]
    assert observed["environment"]["VODFORGE_INITIAL_OUTPUT_DIR"] == r"Z:\\VODs"


def test_windows_output_picker_failure_is_reported_without_closing_app(monkeypatch: pytest.MonkeyPatch):
    class StartupInfo:
        dwFlags = 0

    monkeypatch.setattr(app_module.subprocess, "STARTUPINFO", StartupInfo, raising=False)
    monkeypatch.setattr(app_module.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)

    def runner(command, **_kwargs):
        return app_module.subprocess.CompletedProcess(command, 1, "", "network provider failed")

    with pytest.raises(RuntimeError, match="network provider failed"):
        choose_windows_output_directory(r"Z:\\VODs", runner=runner)


def test_macos_runtime_candidates_cover_bundle_vendor_and_homebrew_paths():
    candidates = runtime_executable_candidates(
        "ffmpeg",
        platform_name="darwin",
        frozen=True,
        executable=Path("/Applications/VODForge.app/Contents/MacOS/VODForge"),
        meipass=Path("/Applications/VODForge.app/Contents/Frameworks"),
        repo_root=Path("/source/vodforge"),
    )

    assert Path("/Applications/VODForge.app/Contents/MacOS/ffmpeg") in candidates
    assert Path("/Applications/VODForge.app/Contents/Frameworks/ffmpeg") in candidates
    assert Path("/source/vodforge/vendor/ffmpeg/bin/ffmpeg") in candidates
    assert Path("/opt/homebrew/bin/ffmpeg") in candidates
    assert Path("/usr/local/bin/ffmpeg") in candidates


def test_windows_runtime_candidates_keep_exe_compatibility():
    candidates = runtime_executable_candidates(
        "deno",
        platform_name="win32",
        frozen=False,
        repo_root=Path("C:/source/vodforge"),
    )

    assert candidates[0] == Path("C:/source/vodforge/deno.exe")
    assert Path("C:/source/vodforge/vendor/deno/deno.exe") in candidates


def test_ytdlp_ffmpeg_location_uses_parent_for_standard_executable_names():
    assert ytdlp_ffmpeg_location("/opt/homebrew/bin/ffmpeg") == "/opt/homebrew/bin"
    assert ytdlp_ffmpeg_location("C:/vendor/ffmpeg.exe") == "C:/vendor"
    assert ytdlp_ffmpeg_location(r"C:\vendor\ffmpeg.exe") == r"C:\vendor"
    assert ytdlp_ffmpeg_location("/bundle/ffmpeg-custom") == "/bundle/ffmpeg-custom"


def test_runtime_version_commands_use_each_tool_cli_contract():
    assert runtime_version_command("ffmpeg", "/bundle/ffmpeg") == ["/bundle/ffmpeg", "-version"]
    assert runtime_version_command("ffprobe", "/bundle/ffprobe") == ["/bundle/ffprobe", "-version"]
    assert runtime_version_command("deno", "/bundle/deno") == ["/bundle/deno", "--version"]


def test_runtime_smoke_timeout_allows_bounded_rosetta_cold_translation():
    assert RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS == 60


def test_build_tags_display_text_uses_comma_space_for_copying():
    info = {"tags": ["zebra", "alpha", "alpha", "  spaced  ", ""]}

    assert build_tags_display_text(info) == "zebra, alpha, spaced"


def test_cancellable_blocking_step_returns_quickly_when_cancel_requested():
    started = threading.Event()
    release = threading.Event()
    cancel = threading.Event()

    def slow_step() -> str:
        started.set()
        release.wait(timeout=5)
        return "finished too late"

    thread = threading.Thread(target=lambda: (started.wait(timeout=1), cancel.set()), daemon=True)
    thread.start()
    begin = time.monotonic()

    with pytest.raises(RuntimeError, match="cancelled"):
        run_cancellable_blocking_step(slow_step, cancel.is_set, timeout_seconds=10, poll_seconds=0.01, label="analysis")

    elapsed = time.monotonic() - begin
    release.set()
    assert elapsed < 1


def test_cancellable_blocking_step_times_out_bounded_step():
    release = threading.Event()

    def slow_step() -> str:
        release.wait(timeout=5)
        return "finished too late"

    begin = time.monotonic()
    with pytest.raises(TimeoutError, match="timed out"):
        run_cancellable_blocking_step(slow_step, lambda: False, timeout_seconds=0.05, poll_seconds=0.01, label="analysis")

    elapsed = time.monotonic() - begin
    release.set()
    assert elapsed < 1


def test_cancellable_blocking_step_reports_waiting_status_before_timeout():
    release = threading.Event()
    notices: list[float] = []

    def slow_step() -> str:
        release.wait(timeout=5)
        return "finished too late"

    with pytest.raises(TimeoutError, match="timed out"):
        run_cancellable_blocking_step(
            slow_step,
            lambda: False,
            timeout_seconds=0.08,
            poll_seconds=0.01,
            label="analysis",
            on_wait=notices.append,
            wait_notice_seconds=0.02,
        )

    release.set()
    assert notices


def test_build_description_display_text_uses_description_field():
    assert build_description_display_text({"description": "Line 1\nLine 2"}) == "Line 1\nLine 2"


def test_quality_options_require_audio_and_never_fall_back_to_video_only():
    for format_selector in QUALITY_OPTIONS.values():
        for alternative in format_selector.split("/"):
            if alternative.startswith("bestvideo"):
                assert "+bestaudio" in alternative
            if alternative.startswith("best["):
                assert "[acodec!=none]" in alternative


def test_compact_video_metadata_keeps_only_useful_tag_and_thumbnail_fields():
    info = {
        "id": "abc123",
        "title": "Example",
        "webpage_url": "https://youtube.com/watch?v=abc123",
        "tags": ["one", "two"],
        "categories": ["Education"],
        "thumbnail": "https://i.ytimg.com/example.jpg",
        "thumbnails": [{"url": "small"}, {"url": "large", "width": 1280}],
        "formats": [1, 2, 3],
        "automatic_captions": {"en": []},
    }

    compact = compact_video_metadata(info, extra_tags=["extra"])

    assert compact == {
        "id": "abc123",
        "title": "Example",
        "webpage_url": "https://youtube.com/watch?v=abc123",
        "tags": ["one", "two"],
        "extra_tags": ["extra"],
        "categories": ["Education"],
        "thumbnail": "https://i.ytimg.com/example.jpg",
        "best_thumbnail": {"url": "large", "width": 1280},
        "vodforge_output_type": "MP4",
    }


def test_write_compact_video_metadata_uses_short_metadata_filename(tmp_path: Path):
    long_title = "Very Long Metadata Title " * 8
    out = write_compact_video_metadata(
        tmp_path,
        {"id": "abc123", "title": long_title, "tags": ["one", "two"]},
        extra_tags=[],
    )

    text = out.read_text(encoding="utf-8")
    assert "\n  \"tags\": [\n" in text
    assert json.loads(text)["tags"] == ["one", "two"]
    assert out.name == "metadata.json"


def test_playlist_folder_and_video_output_dir_are_windows_safe(tmp_path: Path):
    playlist = {"_type": "playlist", "title": "Cool: Playlist?", "id": "PL123"}
    video = {"title": "Video / One", "id": "abc123", "playlist_index": 7, "playlist_title": "Cool: Playlist?", "playlist_id": "PL123", "uploader": "Creator: One"}

    assert playlist_folder_name(playlist) == "Cool_ Playlist_"
    assert video_output_dir(tmp_path, video) == tmp_path / "Creator_ One" / "playlists" / "Cool_ Playlist_" / "Video _ One [abc123]"


def test_single_video_output_dir_uses_channel_parent_and_bounded_title_folder(tmp_path: Path):
    long_title = "Very Long Video Title " * 20
    single = {"title": long_title, "id": "abc123", "channel": "Main Channel"}

    output = video_output_dir(tmp_path, single)

    assert output.parent == tmp_path / "Main Channel" / "videos - no playlist"
    assert output.name.endswith("[abc123]")
    assert len(output.name) <= 96
    assert "000 -" not in output.name


def test_clean_single_video_url_removes_playlist_params_but_keeps_video_id():
    cases = [
        ("watch?v=abc&t=30s&list=PL", "watch?v=abc&t=30s"),
        ("watch?list=PL&v=abc&t=30s", "watch?v=abc&t=30s"),
        ("watch?v=abc&index=4&list=PL", "watch?v=abc"),
        ("https://youtu.be/abc?list=PL&t=30s", "https://youtu.be/abc?t=30s"),
    ]

    for original, expected in cases:
        assert clean_single_video_url(original) == expected


def test_canonical_youtube_url_keeps_item_and_proven_playlist_context_only():
    assert canonical_youtube_url(
        {
            "id": "abc123",
            "playlist_id": "PLsafe",
            "webpage_url": "https://www.youtube.com/watch?v=abc123&list=PLsafe&index=4&t=10&token=secret",
        }
    ) == "https://www.youtube.com/watch?v=abc123&list=PLsafe"
    assert canonical_youtube_url({}, "https://example.com/watch?v=abc123") is None


def test_canonical_youtube_url_strips_untrusted_query_data_without_an_item_id():
    assert canonical_youtube_url(
        {
            "playlist_id": "PLsafe",
            "webpage_url": "https://www.youtube.com/playlist?list=PLsafe&si=tracking&token=secret",
        }
    ) == "https://www.youtube.com/playlist?list=PLsafe"
    assert canonical_youtube_url(
        {},
        "https://www.youtube.com/@Creator/videos?si=tracking&token=secret#featured",
    ) == "https://www.youtube.com/@Creator/videos"


def test_single_video_toggle_blocks_playlist_url_without_video_id():
    url = "https://www.youtube.com/playlist?list=PL"

    assert clean_single_video_url(url) == url
    assert single_video_url_requires_video_id_error(url) == (
        "This link is a playlist. Turn off ‘Ignore playlists’ to download every item."
    )


def test_single_video_toggle_allows_watch_and_short_urls_with_video_id():
    assert single_video_url_requires_video_id_error("https://www.youtube.com/watch?list=PL&v=abc&t=30s") is None
    assert single_video_url_requires_video_id_error("https://youtu.be/abc?list=PL&t=30s") is None


def test_ignore_playlists_is_the_safe_default():
    assert DEFAULT_IGNORE_PLAYLISTS is True


def test_batch_watch_urls_with_playlist_context_are_processed_as_single_videos():
    url = "https://www.youtube.com/watch?v=abc123&list=PLmix&index=12&t=30s"

    preserved_url, single_video_only = prepare_batch_item_url(url)

    assert preserved_url == url
    assert single_video_only is True
    assert youtube_url_video_id(preserved_url) == "abc123"
    assert youtube_url_playlist_id(preserved_url) == "PLmix"


def test_existing_playlist_output_candidates_include_canonical_and_legacy_paths(tmp_path: Path):
    info = {
        "id": "abc123",
        "title": "One song",
        "uploader": "Creator",
        "playlist_id": "PLmix",
        "playlist_title": "The Mix",
    }

    candidates = existing_output_candidate_dirs(tmp_path, info, "One song.mp4")

    assert candidates[0] == tmp_path / "Creator" / "playlists" / "The Mix" / "One song [abc123]"
    assert tmp_path / "Creator" / "videos - no playlist" / "One song [abc123]" in candidates


def test_valid_legacy_single_output_is_reused_by_later_playlist_run(monkeypatch, tmp_path: Path):
    info = {
        "id": "abc123",
        "title": "One song",
        "uploader": "Creator",
        "playlist_id": "PLmix",
        "playlist_title": "The Mix",
    }
    legacy = tmp_path / "Creator" / "videos - no playlist" / "One song [abc123]" / "One song.mp4"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"valid-media")
    probe = {"format": {"duration": "30", "format_name": "mp4"}, "streams": []}
    validated: list[Path] = []

    def validate(path, *_args, **_kwargs):
        validated.append(path)
        return probe

    monkeypatch.setattr(app_module, "validate_output_artifact", validate)

    found = find_valid_existing_output(tmp_path, info, OutputType.MP4, "ffprobe")

    assert found == (legacy, probe)
    assert validated == [legacy]


def test_deep_root_still_reuses_a_valid_v015_emergency_output_before_rejecting_new_allocation(monkeypatch, tmp_path: Path):
    output_root = tmp_path
    segment = 0
    while len(str(output_root).encode("utf-16-le")) // 2 <= app_module.WINDOWS_SAFE_PATH_LIMIT:
        output_root /= f"deep-{segment:02d}"
        segment += 1
    info = {"id": "abc123", "title": "One song", "uploader": "Creator"}
    legacy = output_root / "path-safe videos" / "abc123" / "One song.mp4"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"valid legacy media")
    probe = {"format": {"duration": "30", "format_name": "mp4"}, "streams": []}
    monkeypatch.setattr(app_module, "validate_output_artifact", lambda *_args, **_kwargs: probe)

    found = find_valid_existing_output(output_root, info, OutputType.MP4, "ffprobe")

    assert found == (legacy, probe)
    with pytest.raises(ValueError, match="shorter output folder"):
        resolved_video_output_target(output_root, info, ".mp4")


def test_invalid_existing_output_is_not_treated_as_downloaded(monkeypatch, tmp_path: Path):
    info = {"id": "abc123", "title": "One song", "uploader": "Creator"}
    candidate = tmp_path / "Creator" / "videos - no playlist" / "One song [abc123]" / "One song.mp4"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"corrupt")
    monkeypatch.setattr(
        app_module,
        "validate_output_artifact",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("corrupt")),
    )

    assert find_valid_existing_output(tmp_path, info, OutputType.MP4, "ffprobe") is None


def test_batch_playlist_urls_remain_playlist_jobs():
    url = "https://www.youtube.com/playlist?list=PLmix"

    cleaned_url, single_video_only = prepare_batch_item_url(url)

    assert cleaned_url == url
    assert single_video_only is False


def test_parse_url_list_text_extracts_url_before_tab_or_title_text():
    text = "https://www.youtube.com/watch?v=abc123\tCopied title\nhttps://youtu.be/def456 more copied title\n"

    assert parse_url_list_text(text) == [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/def456",
    ]


def test_iter_video_infos_handles_playlist_and_single_video():
    playlist = {"_type": "playlist", "entries": [{"id": "one"}, None, {"id": "two"}]}
    single = {"id": "solo"}

    assert [item["id"] for item in iter_video_infos(playlist)] == ["one", "two"]
    assert [item["id"] for item in iter_video_infos(single)] == ["solo"]


def test_single_video_output_dir_is_video_folder_not_single_videos_parent(tmp_path: Path):
    single = {"title": "My Single Video", "id": "abc123", "uploader": "Creator"}

    assert video_output_dir(tmp_path, single) == tmp_path / "Creator" / "videos - no playlist" / "My Single Video [abc123]"


def test_same_title_videos_in_same_channel_get_distinct_video_folders(tmp_path: Path):
    first = {"title": "Same Title", "id": "one", "uploader": "Creator"}
    second = {"title": "Same Title", "id": "two", "uploader": "Creator"}

    assert video_output_dir(tmp_path, first) == tmp_path / "Creator" / "videos - no playlist" / "Same Title [one]"
    assert video_output_dir(tmp_path, second) == tmp_path / "Creator" / "videos - no playlist" / "Same Title [two]"


def test_long_windows_paths_keep_full_media_filename_with_compact_title_folder(tmp_path: Path):
    long_title = "John MacArthur, a Gifted Bible Teacher and Pastor, Goes Home to Heaven"
    info = {
        "title": long_title,
        "id": "Hi4j2pF4AAM",
        "channel": "American Family Radio",
        "playlist_title": long_title,
        "playlist_id": "PL123",
    }
    output_dir = Path("C:/Users/DequanBrown/Downloads")

    target_dir = app_module.resolved_video_output_dir(output_dir, info, f"{long_title}.mp4")

    assert target_dir.parent == output_dir / "American Family Radio" / "playlists" / long_title
    assert target_dir.name.startswith("John MacArthur")
    assert target_dir.name.endswith("[Hi4j2pF4AAM]")
    assert target_dir.name != f"{long_title} [Hi4j2pF4AAM]"
    assert len(str(target_dir / f"{long_title}.mp4")) <= app_module.WINDOWS_SAFE_PATH_LIMIT
    assert (target_dir / f"{long_title}.mp4").name == f"{long_title}.mp4"


def test_path_budget_keeps_channel_playlist_and_truncated_title_instead_of_an_id_only_fallback():
    info = {
        "title": "A descriptive production title " * 8,
        "id": "Hi4j2pF4AAM",
        "channel": "Production Channel",
        "playlist_title": "A long but meaningful playlist name " * 3,
        "playlist_id": "PL123",
    }
    output_dir = Path("C:/Users/Viewer/OneDrive - Company/Deep/Approved/Delivery/Root")

    target_dir, target_name = resolved_video_output_target(output_dir, info, ".mp4")

    assert target_dir.parts[-4].startswith("Production Chan")
    assert target_dir.parts[-3] == "playlists"
    assert "path-safe videos" not in target_dir.parts
    assert target_dir.name.endswith("[Hi4j2pF4AAM]")
    assert target_dir.name != "Hi4j2pF4AAM"
    assert len(str(target_dir / target_name).encode("utf-16-le")) // 2 <= app_module.WINDOWS_SAFE_PATH_LIMIT


def test_windows_reserved_device_names_are_never_used_as_raw_directories(tmp_path: Path):
    output = video_output_dir(tmp_path, {"title": "NUL", "id": "abc", "channel": "CON"})

    assert output.parts[-3] == "_CON"
    assert output.name.startswith("_NUL")


def test_package_downloaded_media_from_staging_only_moves_current_job_files(tmp_path: Path):
    output_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    old_download = output_dir / "Old Video [old123]"
    old_download.mkdir(parents=True)
    (old_download / "video [old123].mp4").write_text("old")

    current_stage = staging_dir / "abc123"
    current_stage.mkdir(parents=True)
    (current_stage / "video [abc123].mp4").write_text("new video")
    (current_stage / "video [abc123].webp").write_text("transient thumbnail")
    info = {"title": "My Single Video", "id": "abc123", "uploader": "Creator"}

    moved = package_downloaded_media_from_staging(staging_dir, output_dir, info)
    expected_dir = output_dir / "Creator" / "videos - no playlist" / "My Single Video [abc123]"

    assert moved == [expected_dir / "My Single Video.mp4"]
    assert (expected_dir / "My Single Video.mp4").read_text() == "new video"
    assert (old_download / "video [old123].mp4").read_text() == "old"
    assert not (expected_dir / "video [abc123].webp").exists()
    assert not any("Single Videos" in str(path) for path in output_dir.rglob("*"))


def test_package_downloaded_media_from_staging_handles_playlist_without_touching_old_files(tmp_path: Path):
    output_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    old_download = output_dir / "Old Video [old123]"
    old_download.mkdir(parents=True)
    (old_download / "video [old123].mp4").write_text("old")
    for video_id in ("one", "two"):
        current_stage = staging_dir / video_id
        current_stage.mkdir(parents=True)
        (current_stage / f"video [{video_id}].mp4").write_text(video_id)
    playlist = {
        "_type": "playlist",
        "title": "Playlist Title",
        "id": "PL1",
        "entries": [
            {"title": "First", "id": "one", "playlist_index": 1, "uploader": "Shared Channel"},
            {"title": "Second", "id": "two", "playlist_index": 2, "uploader": "Shared Channel"},
        ],
    }

    moved = package_downloaded_media_from_staging(staging_dir, output_dir, playlist)

    assert [path.relative_to(output_dir).as_posix() for path in moved] == [
        "Shared Channel/playlists/Playlist Title/First [one]/First.mp4",
        "Shared Channel/playlists/Playlist Title/Second [two]/Second.mp4",
    ]
    assert (old_download / "video [old123].mp4").read_text() == "old"
    assert len([path for path in output_dir.rglob("*.mp4")]) == 3


def test_package_downloaded_media_uses_title_only_filename_with_sanitized_youtube_title(tmp_path: Path):
    output_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    current_stage = staging_dir / "abc123"
    current_stage.mkdir(parents=True)
    (current_stage / "video [abc123].mp4").write_text("new video")
    info = {"title": "Video / One: The Real? Title*", "id": "abc123", "uploader": "Creator"}

    moved = package_downloaded_media_from_staging(staging_dir, output_dir, info)

    assert moved == [output_dir / "Creator" / "videos - no playlist" / "Video _ One_ The Real_ Title_ [abc123]" / "Video _ One_ The Real_ Title_.mp4"]
    assert "abc123" not in moved[0].name
    assert "video [" not in moved[0].name


def test_package_downloaded_mp3_moves_only_the_single_audio_result(tmp_path: Path):
    output_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    current_stage = staging_dir / "abc123"
    current_stage.mkdir(parents=True)
    (current_stage / "video [abc123].mp3").write_bytes(b"mp3 audio")
    (current_stage / "video [abc123].jpg").write_bytes(b"temporary cover")
    info = {
        "title": "Producer Beat",
        "id": "abc123",
        "uploader": "Beat Channel",
        "vodforge_output_type": "MP3",
    }

    moved = package_downloaded_media_from_staging(
        staging_dir,
        output_dir,
        info,
        expected_extension=".mp3",
    )

    expected = output_dir / "Beat Channel" / "videos - no playlist" / "Producer Beat [abc123]" / "Producer Beat.mp3"
    assert moved == [expected]
    assert expected.read_bytes() == b"mp3 audio"
    assert not list(output_dir.rglob("*.jpg"))


def test_atomic_package_failure_preserves_existing_valid_output(monkeypatch, tmp_path: Path):
    output_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    staged_dir = staging_dir / "abc123"
    staged_dir.mkdir(parents=True)
    staged = staged_dir / "video [abc123].mp4"
    staged.write_bytes(b"new output")
    info = {"title": "Video", "id": "abc123", "uploader": "Creator"}
    target = output_dir / "Creator" / "videos - no playlist" / "Video [abc123]" / "Video.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"known good output")

    monkeypatch.setattr(app_module.os, "replace", lambda _source, _target: (_ for _ in ()).throw(OSError("disk unavailable")))

    with pytest.raises(OSError, match="disk unavailable"):
        package_downloaded_media_from_staging(staging_dir, output_dir, info)

    assert target.read_bytes() == b"known good output"
    assert staged.read_bytes() == b"new output"


def test_cancel_barrier_prevents_atomic_commit_and_preserves_existing_output(tmp_path: Path):
    output_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    staged_dir = staging_dir / "abc123"
    staged_dir.mkdir(parents=True)
    staged = staged_dir / "video [abc123].mp4"
    staged.write_bytes(b"new output")
    info = {"title": "Video", "id": "abc123", "uploader": "Creator"}
    target = output_dir / "Creator" / "videos - no playlist" / "Video [abc123]" / "Video.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"known good output")

    with pytest.raises(RuntimeError, match="cancelled"):
        package_downloaded_media_from_staging(
            staging_dir,
            output_dir,
            info,
            control_check=lambda: (_ for _ in ()).throw(RuntimeError("cancelled")),
        )

    assert target.read_bytes() == b"known good output"
    assert staged.read_bytes() == b"new output"


def test_staging_output_template_never_targets_real_final_folders(tmp_path: Path):
    template = staging_output_template(tmp_path)

    assert "Single Videos" not in template
    assert "%(playlist_title" not in template
    assert "%(title)" not in template
    assert template.endswith("%(id)s.%(ext)s")


def test_short_same_volume_staging_fits_when_the_previous_layout_would_exhaust_windows_path_budget(tmp_path: Path):
    output_root = tmp_path
    segment = 0
    while len(str(output_root).encode("utf-16-le")) // 2 < 180:
        output_root /= f"delivery-{segment:02d}"
        segment += 1
    output_root.mkdir(parents=True)

    staging = create_staging_dir(output_root)
    video_id = "Hi4j2pF4AAM"
    # yt-dlp may append temporary suffixes while writing, so the proof must
    # cover the longest enabled in-flight form rather than only the final name.
    actual_artifact = staging / f"{video_id}.mp4.part"
    previous_artifact = (
        output_root
        / ".yt-dlp-downloader-staging"
        / ("a" * 32)
        / video_id
        / f"video [{video_id}].mp4.part"
    )

    assert staging.parent.name == ".vfstage"
    assert len(staging.name) == 8
    assert app_module._path_would_exceed_windows_safe_limit(actual_artifact) is False
    assert app_module._path_would_exceed_windows_safe_limit(previous_artifact) is True


def test_download_reuses_preflight_result_without_mutating_it():
    preflight = {
        "id": "abc123",
        "title": "Video",
        "formats": [{"format_id": "137"}],
        "requested_downloads": [{"filepath": "old"}],
        "requested_formats": [{"format_id": "old"}],
        "filepath": "old.mp4",
        "__files_to_move": {"old": "new"},
        "__postprocessors": ["old"],
    }

    copied_cookies: list[object] = []

    class CookieJar:
        def set_cookie(self, cookie):
            copied_cookies.append(cookie)

    class FakeYDL:
        cookiejar = CookieJar()

        def process_ie_result(self, info, *, download):
            assert download is True
            assert info["formats"] == [{"format_id": "137"}]
            assert not ({"requested_downloads", "requested_formats", "filepath", "__files_to_move", "__postprocessors"} & info.keys())
            return {**info, "downloaded": True}

    session_cookie = object()
    result = process_download_from_preflight(
        FakeYDL(),
        preflight,
        session_cookies=(session_cookie,),
    )

    assert result["downloaded"] is True
    assert preflight["requested_formats"] == [{"format_id": "old"}]
    assert copied_cookies == [session_cookie]


def test_save_thumbnail_image_writes_single_thumbnail_jpeg(monkeypatch, tmp_path: Path):
    Image = pytest.importorskip("PIL.Image")
    buf = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="WEBP")
    payload = buf.getvalue()

    class Response:
        def __init__(self):
            self.buffer = BytesIO(payload)
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size=-1):
            return self.buffer.read(size)

    monkeypatch.setattr("yt_downloader.app.urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    path = save_thumbnail_image(tmp_path, {"thumbnail": "https://i.ytimg.com/example.webp"})

    assert path == tmp_path / "thumbnail.jpeg"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["thumbnail.jpeg"]
    with Image.open(path) as image:
        assert image.format == "JPEG"


def test_thumbnail_download_rejects_non_http_and_oversized_responses(monkeypatch):
    with pytest.raises(RuntimeError, match="HTTP or HTTPS"):
        download_bounded_url_bytes("file:///private/data")

    class Response:
        headers = {"Content-Length": "1001"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size=-1):
            raise AssertionError("an oversized declared response must not be read")

    monkeypatch.setattr(app_module.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(RuntimeError, match="safety limit"):
        download_bounded_url_bytes("https://i.ytimg.com/oversized.jpg", max_bytes=1000)


def test_thumbnail_download_enforces_bound_for_chunked_response(monkeypatch):
    class Response:
        headers = {}

        def __init__(self):
            self.buffer = BytesIO(b"x" * 1001)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size=-1):
            return self.buffer.read(size)

    monkeypatch.setattr(app_module.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(RuntimeError, match="safety limit"):
        download_bounded_url_bytes("https://i.ytimg.com/chunked.jpg", max_bytes=1000)


def test_thumbnail_decoder_rejects_excessive_decoded_dimensions(monkeypatch):
    class OversizedImage:
        size = (app_module.THUMBNAIL_MAX_DIMENSION + 1, 1)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def verify(self):
            return None

    monkeypatch.setattr(app_module.Image, "open", lambda *_args, **_kwargs: OversizedImage())

    with pytest.raises(RuntimeError, match="safe preview limit"):
        app_module.decode_bounded_thumbnail(b"compressed image")


def test_private_thumbnail_cache_is_read_through_without_a_second_network_fetch(monkeypatch, tmp_path: Path):
    info = {"id": "beat123", "thumbnail": "https://i.ytimg.com/beat123.jpg"}
    cached = cached_thumbnail_path(info, data_dir=tmp_path)
    assert cached is not None
    cached.parent.mkdir(parents=True)
    Image.new("RGB", (16, 9), "purple").save(cached, format="JPEG")
    monkeypatch.setattr(
        app_module,
        "save_thumbnail_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache miss unexpectedly fetched the network")),
    )

    assert save_cached_thumbnail_image(info, data_dir=tmp_path) == cached


def test_thumbnail_cache_key_is_stable_when_history_keeps_a_different_thumbnail_variant(tmp_path: Path):
    full = {
        "id": "beat123",
        "vodforge_output_type": "MP4",
        "thumbnails": [{"url": "https://i.ytimg.com/beat123/maxres.jpg", "width": 1280}],
    }
    compact = {
        "id": "beat123",
        "vodforge_output_type": "MP4",
        "thumbnail": "https://i.ytimg.com/beat123/default.jpg",
    }
    canonical = cached_thumbnail_path(full, data_dir=tmp_path)
    assert canonical == cached_thumbnail_path(compact, data_dir=tmp_path)
    assert canonical is not None
    canonical.parent.mkdir(parents=True)
    Image.new("RGB", (16, 9), "purple").save(canonical, format="JPEG")
    assert existing_cached_thumbnail_path(compact, data_dir=tmp_path) == canonical
    assert legacy_cached_thumbnail_path(full, data_dir=tmp_path) != canonical


def test_v015_thumbnail_variant_is_found_and_migrated_after_a_cold_history_restart(tmp_path: Path):
    old_variant = "https://i.ytimg.com/vi/beat123/maxresdefault.jpg"
    history_variant = "https://i.ytimg.com/vi/beat123/default.jpg"
    old_cache = legacy_cached_thumbnail_path(
        {"id": "beat123", "thumbnail": old_variant},
        data_dir=tmp_path,
    )
    assert old_cache is not None
    old_cache.parent.mkdir(parents=True)
    Image.new("RGB", (32, 18), "purple").save(old_cache, format="JPEG")
    full_info = {
        "id": "beat123",
        "vodforge_output_type": "MP4",
        "thumbnail": history_variant,
        "thumbnails": [
            {"url": history_variant, "width": 120, "height": 90},
            {"url": old_variant, "width": 1280, "height": 720},
        ],
    }
    history = sanitize_history_record(full_info, tmp_path / "saved")
    assert history["thumbnail"] == history_variant
    assert "thumbnails" not in history
    assert "best_thumbnail" not in history
    stable = cached_thumbnail_path(history, data_dir=tmp_path)
    assert stable is not None and not stable.exists()

    found = existing_cached_thumbnail_path(history, data_dir=tmp_path)

    assert found == stable
    assert stable.is_file()
    assert app_module.decode_bounded_thumbnail(stable.read_bytes()).size == (32, 18)
    assert old_cache.is_file()


def test_private_thumbnail_cache_deduplicates_concurrent_fetches_atomically(monkeypatch, tmp_path: Path):
    info = {"id": "beat123", "thumbnail": "https://i.ytimg.com/beat123.jpg"}
    destinations: list[Path] = []

    def fake_save(output_dir, _info, *, filename):
        destination = output_dir / filename
        destinations.append(destination)
        time.sleep(0.02)
        Image.new("RGB", (16, 9), "purple").save(destination, format="JPEG")
        return destination

    monkeypatch.setattr(app_module, "save_thumbnail_image", fake_save)
    results: list[Path | None] = []
    threads = [
        threading.Thread(target=lambda: results.append(save_cached_thumbnail_image(info, data_dir=tmp_path)))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    canonical = cached_thumbnail_path(info, data_dir=tmp_path)
    assert canonical is not None
    assert len(destinations) == 1
    assert all(path != canonical and path.name.startswith(".") for path in destinations)
    assert results == [canonical, canonical]
    assert app_module.decode_bounded_thumbnail(canonical.read_bytes()).size == (16, 9)
    assert not list(canonical.parent.glob(".*.tmp"))


def test_existing_mp4_must_match_the_requested_export_plan_not_only_container_and_codecs():
    plan = ExportPlan(
        mode=ExportMode.AUTO_CBR,
        video_format_id="137",
        audio_format_id="251",
        format_selector="137+251",
        output_width=1920,
        output_height=1080,
        source_video_kbps=3000,
        effective_video_kbps=3000,
        video_bitrate_kbps=2000,
        source_audio_kbps=130,
        effective_audio_kbps=130,
        audio_bitrate_kbps=192,
        audio_sample_rate="48000",
        audio_channels="2",
    )
    matching = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "bit_rate": "1999000",
                "pix_fmt": "yuv420p",
                "profile": "High",
            },
            {"codec_type": "audio", "codec_name": "aac", "bit_rate": "194000", "sample_rate": "48000", "channels": 2},
        ],
        "format": {"format_name": "mov,mp4", "tags": {}},
    }
    sidecar_summary = {
        "Output rate-control mode": "Auto CBR",
        "Target video bitrate": "2000 kbps",
        "Target audio bitrate": "192 kbps",
    }
    stale_360p = {
        **matching,
        "streams": [{**matching["streams"][0], "width": 640, "height": 360}, matching["streams"][1]],
    }

    assert output_artifact_matches_plan(
        matching,
        plan,
        embed_metadata=False,
        embed_cover_art=False,
        custom_cover_art=False,
        expected_tags=[],
        sidecar_summary=sidecar_summary,
    )
    assert not output_artifact_matches_plan(
        stale_360p,
        plan,
        embed_metadata=False,
        embed_cover_art=False,
        custom_cover_art=False,
        expected_tags=[],
        sidecar_summary=sidecar_summary,
    )
    assert not output_artifact_matches_plan(
        {**matching, "streams": [{**matching["streams"][0], "profile": "Main"}, matching["streams"][1]]},
        plan,
        embed_metadata=False,
        embed_cover_art=False,
        custom_cover_art=False,
        expected_tags=[],
        sidecar_summary=sidecar_summary,
    )


def test_existing_mp3_rejects_stale_bitrate_and_custom_cover_request():
    plan = AudioExportPlan(
        output_type=OutputType.MP3,
        audio_format_id="251",
        format_selector="251",
        source_audio_kbps=130,
        effective_audio_kbps=130,
        audio_bitrate_kbps=320,
        source_sample_rate="48000",
        output_sample_rate="48000",
        source_channels="2",
        output_channels="2",
        audio_codec="opus",
        embed_metadata=False,
        embed_cover_art=False,
        cover_art_source="No Art",
    )
    probe = {
        "streams": [{"codec_type": "audio", "codec_name": "mp3", "bit_rate": "128000", "sample_rate": "48000", "channels": 2}],
        "format": {"format_name": "mp3", "tags": {}},
    }
    sidecar_summary = {
        "Output rate-control mode": "CBR",
        "Target audio bitrate": "320 kbps",
    }

    assert not output_artifact_matches_plan(
        probe,
        plan,
        embed_metadata=False,
        embed_cover_art=False,
        custom_cover_art=False,
        expected_tags=[],
        sidecar_summary=sidecar_summary,
    )
    probe["streams"][0]["bit_rate"] = "320000"
    assert not output_artifact_matches_plan(
        probe,
        plan,
        embed_metadata=False,
        embed_cover_art=True,
        custom_cover_art=True,
        expected_tags=[],
        sidecar_summary=sidecar_summary,
    )


def test_retry_url_and_playlist_context_preserve_real_playlist_identity_only():
    retry = retry_url_for_item(
        {"id": "video123", "playlist_id": "PLreal"},
        "https://youtu.be/video123",
    )
    assert retry == "https://www.youtube.com/watch?v=video123&list=PLreal"
    playlist = {"_type": "playlist", "id": "PLreal", "title": "Real playlist", "entries": []}
    ordinary_video = {"id": "video123", "title": "Ordinary video"}
    assert playlist_context_from_extraction(playlist, retry) is playlist
    assert playlist_context_from_extraction(ordinary_video, retry) == {"webpage_url": retry}


def test_ignore_playlists_preserves_supplied_playlist_identity_for_canonical_output(tmp_path: Path):
    source_url = "https://www.youtube.com/watch?v=video123&list=PLreal&index=4"
    info = {"id": "video123", "title": "Playlist item", "uploader": "Creator"}
    playlist = {
        "_type": "playlist",
        "id": "PLreal",
        "title": "Real playlist",
        "entries": [{"id": "video123", "playlist_index": 4}],
    }

    contextual = apply_playlist_context(info, playlist["entries"][0], playlist, source_url, 1)

    assert contextual["playlist_id"] == "PLreal"
    assert contextual["playlist_title"] == "Real playlist"
    assert contextual["playlist_index"] == 4
    assert video_output_dir(tmp_path, contextual) == (
        tmp_path / "Creator" / "playlists" / "Real playlist" / "Playlist item [video123]"
    )


def test_playlist_id_in_source_url_is_retained_when_flat_extraction_loses_playlist_root(tmp_path: Path):
    source_url = "https://youtu.be/video123?list=PLfallback"
    info = {"id": "video123", "title": "Playlist item", "uploader": "Creator"}

    contextual = apply_playlist_context(info, {"id": "video123"}, {"webpage_url": source_url}, source_url, 1)

    assert contextual["playlist_id"] == "PLfallback"
    assert contextual.get("playlist_title") is None
    assert video_output_dir(tmp_path, contextual) == (
        tmp_path / "Creator" / "playlists" / "PLfallback" / "Playlist item [video123]"
    )


def test_plain_share_url_does_not_invent_playlist_authority(tmp_path: Path):
    source_url = "https://youtu.be/video123?si=share-token"
    info = {"id": "video123", "title": "Single item", "uploader": "Creator"}

    contextual = apply_playlist_context(info, {"id": "video123"}, {"webpage_url": source_url}, source_url, 1)

    assert contextual.get("playlist_id") is None
    assert contextual.get("playlist_title") is None
    assert video_output_dir(tmp_path, contextual) == (
        tmp_path / "Creator" / "videos - no playlist" / "Single item [video123]"
    )


def test_output_directory_access_probe_is_eager_and_leaves_no_temp_file(tmp_path: Path):
    output_dir = tmp_path / "Downloads"

    validate_output_directory_access(output_dir)

    assert output_dir.is_dir()
    assert list(output_dir.iterdir()) == []


def test_removed_library_record_is_rediscovered_from_disk_and_readded_without_duplicate(monkeypatch, tmp_path: Path):
    info = {
        "id": "video123",
        "title": "Playlist item",
        "uploader": "Creator",
        "playlist_id": "PLreal",
        "playlist_title": "Real playlist",
        "duration": 60,
        "vodforge_output_type": "MP4",
    }
    target_dir = video_output_dir(tmp_path, info)
    target_dir.mkdir(parents=True)
    target = target_dir / video_file_name(info, ".mp4")
    target.write_bytes(b"existing validated media")
    plan = ExportPlan(
        mode=ExportMode.AUTO_CBR,
        video_format_id="137",
        audio_format_id="251",
        format_selector="137+251",
        output_width=1920,
        output_height=1080,
        source_video_kbps=3000,
        effective_video_kbps=3000,
        video_bitrate_kbps=2000,
        source_audio_kbps=130,
        effective_audio_kbps=130,
        audio_bitrate_kbps=192,
        audio_sample_rate="48000",
        audio_channels="2",
    )
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "bit_rate": "2000000",
                "pix_fmt": "yuv420p",
                "profile": "High",
            },
            {"codec_type": "audio", "codec_name": "aac", "bit_rate": "192000", "sample_rate": "48000", "channels": 2},
        ],
        "format": {"format_name": "mov,mp4", "duration": "60", "tags": {}},
    }
    monkeypatch.setattr(app_module, "validate_output_artifact", lambda *_args, **_kwargs: probe)
    write_compact_video_metadata(
        target_dir,
        build_encoding_summary_metadata(info, plan, output_path=target, ffprobe_data=probe, validation_status="Validated"),
        [],
    )

    removed_library_history: list[dict] = []
    found = find_valid_existing_output(
        tmp_path,
        info,
        OutputType.MP4,
        "ffprobe",
        plan=plan,
        embed_metadata=False,
        embed_cover_art=False,
        expected_tags=[],
        expected_duration_seconds=60,
    )
    assert found is not None and found[0] == target
    restored_history = upsert_history(removed_library_history, info, found[0].parent)
    assert len(restored_history) == 1
    assert history_output_dir(restored_history[0]) == target.parent
    assert target.is_file()


def test_moved_media_with_leftover_sidecars_redownloads_to_same_single_library_identity(tmp_path: Path):
    info = {
        "id": "video123",
        "title": "Playlist item",
        "uploader": "Creator",
        "playlist_id": "PLreal",
        "playlist_title": "Real playlist",
        "duration": 60,
        "vodforge_output_type": "MP4",
    }
    item_dir = video_output_dir(tmp_path, info)
    item_dir.mkdir(parents=True)
    media = item_dir / video_file_name(info, ".mp4")
    media.write_bytes(b"original media")
    (item_dir / "thumbnail.jpeg").write_bytes(b"sidecar art")
    (item_dir / "metadata.json").write_text("{}", encoding="utf-8")
    history = upsert_history([], info, item_dir)

    moved_dir = tmp_path / "User organized elsewhere"
    moved_dir.mkdir()
    moved_media = moved_dir / media.name
    media.replace(moved_media)

    assert find_valid_existing_output(tmp_path, info, OutputType.MP4, "ffprobe") is None
    assert moved_media.read_bytes() == b"original media"
    assert (item_dir / "thumbnail.jpeg").is_file()
    assert (item_dir / "metadata.json").is_file()

    # A later successful download returns to the same canonical item folder.
    media.write_bytes(b"new canonical media")
    refreshed = upsert_history(history, info, item_dir)
    assert len(refreshed) == 1
    assert history_output_dir(refreshed[0]) == item_dir
    assert moved_media.is_file()
    assert media.is_file()


def test_moved_media_never_reuses_valid_vodforge_transcode_backups(monkeypatch, tmp_path: Path):
    info = {"id": "video123", "title": "Video", "uploader": "Creator"}
    item_dir = video_output_dir(tmp_path, info)
    item_dir.mkdir(parents=True)
    target_name = video_file_name(info, ".mp4")
    for backup_name in (
        "__vodforge-original.mp4",
        "__vodforge-tmp.mp4",
        f"{Path(target_name).stem}.pre-vodforge.mp4",
        f"{Path(target_name).stem}.vodforge-tmp.mp4",
    ):
        (item_dir / backup_name).write_bytes(b"valid-looking backup")
    monkeypatch.setattr(
        app_module,
        "validate_output_artifact",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("transient backup must not be probed")),
    )

    assert find_valid_existing_output(tmp_path, info, OutputType.MP4, "ffprobe") is None


def test_custom_mp3_cover_is_normalized_and_becomes_private_cached_artwork(tmp_path: Path):
    source = tmp_path / "artist-cover.png"
    Image.new("RGB", (2000, 1200), (118, 78, 255)).save(source, format="PNG")
    staging = tmp_path / "staging"
    staging.mkdir()

    prepared = prepare_custom_cover_art(source, staging)
    info = {
        "id": "beat123",
        "title": "Producer Beat",
        "thumbnail": "https://i.ytimg.com/vi/beat123/maxresdefault.jpg",
    }
    cached = save_custom_cached_thumbnail_image(info, prepared, data_dir=tmp_path / "data")

    assert prepared == staging / "__vodforge-custom-cover.jpeg"
    assert prepared.is_file()
    assert cached == cached_thumbnail_path(info, data_dir=tmp_path / "data")
    assert cached is not None and cached.is_file()
    with Image.open(cached) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 1600
        red, green, blue = image.convert("RGB").getpixel((0, 0))
        assert red > green and blue > green


def test_custom_mp3_cover_embedding_is_atomic_and_marks_front_cover(monkeypatch, tmp_path: Path):
    mp3 = tmp_path / "beat.mp3"
    cover = tmp_path / "cover.jpeg"
    mp3.write_bytes(b"original mp3")
    cover.write_bytes(b"jpeg")
    commands: list[list[str]] = []
    run_kwargs: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = "embedded"

    def fake_run(command, **kwargs):
        commands.append(command)
        run_kwargs.update(kwargs)
        Path(command[-1]).write_bytes(b"mp3 with custom cover")
        return Result()

    monkeypatch.setattr(app_module, "run_cancellable_process_capture", fake_run)

    result = embed_custom_mp3_cover_art(mp3, cover, "/bundle/ffmpeg")

    assert result == mp3
    assert mp3.read_bytes() == b"mp3 with custom cover"
    assert len(commands) == 1
    command = commands[0]
    assert command[:6] == ["/bundle/ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error"]
    assert ["-map", "0:a:0"] in [command[index : index + 2] for index in range(len(command) - 1)]
    assert "attached_pic" in command
    assert "comment=Cover (front)" in command
    assert run_kwargs["timeout_seconds"] == app_module.FFMPEG_COVER_TIMEOUT_SECONDS
    assert not list(tmp_path.glob(".*.vodforge-cover-*.mp3"))


def test_best_thumbnail_for_download_prefers_largest_known_under_300kb():
    info = {
        "thumbnails": [
            {"url": "tiny", "width": 120, "height": 90, "filesize": 20_000},
            {"url": "right", "width": 1280, "height": 720, "filesize_approx": 280_000},
            {"url": "huge", "width": 1920, "height": 1080, "filesize": 700_000},
        ]
    }

    assert best_thumbnail_for_download(info)["url"] == "right"


def test_save_thumbnail_image_compresses_large_thumbnail_below_300kb(monkeypatch, tmp_path: Path):
    Image = pytest.importorskip("PIL.Image")
    noisy = Image.effect_noise((2200, 1600), 100).convert("RGB")
    buf = BytesIO()
    noisy.save(buf, format="PNG")
    payload = buf.getvalue()
    requested_urls: list[str] = []

    class Response:
        def __init__(self):
            self.buffer = BytesIO(payload)
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size=-1):
            return self.buffer.read(size)

    def fake_urlopen(url, **_kwargs):
        requested_urls.append(url)
        return Response()

    monkeypatch.setattr("yt_downloader.app.urllib.request.urlopen", fake_urlopen)

    path = save_thumbnail_image(
        tmp_path,
        {
            "thumbnails": [
                {"url": "https://example.invalid/huge.png", "width": 2200, "height": 1600},
            ]
        },
    )

    assert requested_urls == ["https://example.invalid/huge.png"]
    assert path is not None
    assert path.stat().st_size <= app_module.THUMBNAIL_MAX_BYTES
    with Image.open(path) as image:
        assert image.format == "JPEG"


def test_format_duration_uses_readable_hours_minutes_seconds():
    assert format_duration(None) == "—"
    assert format_duration(65) == "1:05"
    assert format_duration(3661) == "1:01:01"


def test_video_list_row_values_preserves_full_long_title_and_identifiers():
    long_title = "A very long video title " * 8
    item = {"playlist_index": 12, "title": long_title, "id": "abc123", "duration": 3661, "uploader": "Creator"}

    values = video_list_row_values(item, fallback_index=1)

    assert values == ("012", long_title.strip(), "1:01:01", "Creator", "abc123")
    assert len(values[1]) > 120


def test_vod_ffmpeg_command_matches_requested_h264_aac_cbr_summary(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"

    command = build_vod_ffmpeg_command("ffmpeg", source, output)
    joined = " ".join(command)

    assert "-progress pipe:1" in joined
    assert "-nostats" in command
    assert "-c:v libx264" in joined
    assert "-b:v 10000k" in joined
    assert "-minrate 10000k" in joined
    assert "-maxrate 10000k" in joined
    assert "-bufsize 20000k" in joined
    assert "-pass" not in command
    assert f"-c:a aac -b:a {AUDIO_BITRATE} -ar {AUDIO_SAMPLE_RATE} -ac 2" in joined


def test_vod_ffmpeg_command_uses_nvenc_without_changing_bitrate_targets(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"

    command = build_vod_ffmpeg_command("ffmpeg", source, output, video_bitrate_kbps=10000, use_nvenc=True)
    joined = " ".join(command)

    assert "-c:v h264_nvenc" in joined
    assert "-rc cbr" in joined
    assert "-b:v 10000k" in joined
    assert "-minrate 10000k" in joined
    assert "-maxrate 10000k" in joined
    assert "-bufsize 20000k" in joined
    assert "-c:v libx264" not in joined
    assert "-x264-params" not in command
    assert "-progress pipe:1" in joined


def test_vod_ffmpeg_command_keeps_cpu_encoder_by_default(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"

    command = build_vod_ffmpeg_command("ffmpeg", source, output)
    joined = " ".join(command)

    assert "-c:v libx264" in joined
    assert "-c:v h264_nvenc" not in joined

def test_vod_ffmpeg_command_uses_manual_override_audio_and_preset(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"

    command = build_vod_ffmpeg_command(
        "ffmpeg",
        source,
        output,
        video_bitrate_kbps=15000,
        audio_bitrate_kbps=256,
        audio_sample_rate="44100",
        audio_channels="1",
        x264_preset="fast",
    )
    joined = " ".join(command)

    assert "-preset fast" in joined
    assert "-b:v 15000k" in joined
    assert "-c:a aac -b:a 256k -ar 44100 -ac 1" in joined


def test_manual_override_can_encode_mp3_audio_inside_the_mp4_container(tmp_path: Path):
    command = build_vod_ffmpeg_command(
        "ffmpeg",
        tmp_path / "source.mp4",
        tmp_path / "output.mp4",
        audio_codec=ManualAudioCodec.MP3,
    )

    assert "-c:a libmp3lame" in " ".join(command)
    assert "-c:a aac" not in " ".join(command)


def test_auto_source_selection_prefers_true_1080p_h264_when_effective_quality_wins():
    formats = [
        {"format_id": "137", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
        {"format_id": "248", "height": 1080, "width": 1920, "ext": "webm", "vcodec": "vp9", "acodec": "none", "tbr": 754, "fps": 30},
        {"format_id": "399", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "av01.0.08M.08", "acodec": "none", "tbr": 583, "fps": 30},
    ]

    selected = choose_best_video_format(formats, max_height=1080)

    assert selected is not None
    assert selected["format_id"] == "137"


def test_video_source_prefers_direct_only_inside_existing_quality_window():
    formats = [
        {"format_id": "hls-best", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 3000, "fps": 30, "protocol": "m3u8_native"},
        {"format_id": "direct-low", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 2400, "fps": 30, "protocol": "https"},
    ]

    assert choose_best_video_format(formats, max_height=1080)["format_id"] == "hls-best"

    formats[1]["tbr"] = 2700
    formats.append(
        {"format_id": "dash-fragments", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 2900, "fps": 30, "protocol": "http_dash_segments"}
    )
    assert choose_best_video_format(formats, max_height=1080)["format_id"] == "direct-low"


def _summary_test_info() -> dict:
    return {
        "id": "abc123",
        "title": "Example",
        "formats": [
            {
                "format_id": "137",
                "height": 1080,
                "width": 1920,
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "tbr": 1517,
                "fps": 30,
                "filesize_approx": 125000000,
                "dynamic_range": "SDR",
            },
            {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160, "asr": 48000, "audio_channels": 2, "filesize_approx": 14000000},
        ],
    }


def test_encoding_summary_metadata_includes_source_and_planned_output():
    info = _summary_test_info()
    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    enriched = build_encoding_summary_metadata(info, plan, output_path=Path("C:/Videos/video [abc123].mp4"))
    source = enriched["vodforge_encoding_summary"]["source"]
    output = enriched["vodforge_encoding_summary"]["output"]

    assert source["Source format selector used"] == "137+251"
    assert source["Video format ID"] == "137"
    assert source["Audio format ID"] == "251"
    assert source["Source resolution"] == "1920x1080"
    assert source["Source video codec"] == "avc1.640028"
    assert source["Source audio codec"] == "opus"
    assert source["HDR/SDR status"] == "SDR"
    assert source["Reason selected"] == "true 1080p available; preferred H.264 source"
    assert output["Output file path"] == str(Path("C:/Videos/video [abc123].mp4"))
    assert output["Output rate-control mode"] == "Auto CBR"
    assert output["Target video bitrate"] == "2000 kbps"
    assert output["Validation status"] == "Pending"


def test_encoding_summary_metadata_includes_final_ffprobe_output_values():
    info = _summary_test_info()
    plan = build_auto_export_plan(info, mode=ExportMode.STRICT_COMPLIANCE, max_height=1080)
    ffprobe = {
        "format": {"filename": "C:/Videos/final.mp4", "format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "65.2", "size": "50000000"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001", "bit_rate": "9800000", "pix_fmt": "yuv420p", "profile": "High"},
            {"codec_type": "audio", "codec_name": "aac", "bit_rate": "318000", "sample_rate": "48000", "channels": 2},
        ],
    }

    enriched = build_encoding_summary_metadata(info, plan, output_path=Path("C:/Videos/final.mp4"), ffprobe_data=ffprobe)
    output = enriched["vodforge_encoding_summary"]["output"]

    assert output["Output file path"] == str(Path("C:/Videos/final.mp4"))
    assert output["Output container"] == "mp4"
    assert output["Output video codec"] == "h264"
    assert output["Output frame rate"] == "29.97 fps"
    assert output["Measured video bitrate"] == "9800 kbps"
    assert output["Pixel format"] == "yuv420p"
    assert output["H.264 profile"] == "High"
    assert output["Measured audio bitrate"] == "318 kbps"
    assert output["Output file size"] == "47.7 MB"
    assert output["Output duration"] == "1:05"
    assert output["Validation status"] == "Validated"


def test_mp3_plan_uses_highest_quality_audio_only_source_and_truthful_summary():
    info = {
        "id": "beat123",
        "formats": [
            {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a.40.2", "abr": 96, "protocol": "https"},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "asr": 44100, "audio_channels": 2, "protocol": "https"},
            {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160, "asr": 48000, "audio_channels": 2, "protocol": "m3u8_native"},
        ],
    }

    plan = build_mp3_export_plan(info)
    enriched = build_encoding_summary_metadata(info, plan, output_path=Path("Producer Beat.mp3"))
    source_text, output_text = build_encoding_summary_display(enriched)

    assert isinstance(plan, AudioExportPlan)
    assert plan.output_type == OutputType.MP3
    assert plan.audio_format_id == "251"
    assert plan.format_selector == "251"
    assert plan.audio_bitrate_kbps == 320
    assert plan.embed_metadata is True
    assert plan.embed_cover_art is False
    assert plan.cover_art_source == "None (no art)"
    assert metadata_output_type(enriched) == OutputType.MP3
    assert "Audio format ID: 251" in source_text
    assert "Effective/target audio bitrate: 320 kbps" in output_text
    assert "Embedded cover art: None (no art)" in output_text
    assert "Video format ID" not in source_text + output_text


def test_mp3_summary_uses_measured_audio_values_without_video_rows():
    info = {
        "id": "beat123",
        "formats": [
            {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160, "asr": 48000, "audio_channels": 2},
        ],
    }
    plan = build_mp3_export_plan(info, Mp3ExportSettings(sample_rate="44100", channels="2"))
    ffprobe = {
        "format": {"filename": "Producer Beat.mp3", "format_name": "mp3", "duration": "60", "size": "2400000"},
        "streams": [{"codec_type": "audio", "codec_name": "mp3", "bit_rate": "320000", "sample_rate": "44100", "channels": 2}],
    }

    enriched = build_encoding_summary_metadata(
        info,
        plan,
        output_path=Path("Producer Beat.mp3"),
        ffprobe_data=ffprobe,
        validation_status="Validated",
    )
    source_text, output_text = build_encoding_summary_display(enriched)

    assert "Audio bitrate: 320 kbps" in output_text
    assert "Audio sample rate: 44100" in output_text
    assert "Validation status: Validated" in output_text
    assert "Video codec" not in source_text + output_text


def test_encoding_summary_display_switches_per_selected_video_and_handles_missing_fields():
    one = {"id": "one", "vodforge_encoding_summary": {"source": {"Video format ID": "137"}, "output": {"Output file path": "one.mp4", "Validation status": "Validated"}, "warnings": []}}
    two = {"id": "two", "vodforge_encoding_summary": {"source": {"Video format ID": "136"}, "output": {"Output file path": "two.mp4", "Validation status": "Pending"}, "warnings": ["source limited"]}}

    source_one, output_one = build_encoding_summary_display(one)
    source_two, output_two = build_encoding_summary_display(two)
    source_missing, output_missing = build_encoding_summary_display({"id": "missing"})

    assert "Video format ID: 137" in source_one
    assert "Output file path: one.mp4" in output_one
    assert "Video format ID: 136" in source_two
    assert "Warnings: source limited" in output_two
    assert "None" not in source_missing + output_missing
    assert "Format selector: Not available" in source_missing
    assert "Output file path: Not produced" in output_missing
    assert "Format selector:" not in output_two
    assert "Video format ID:" not in output_two
    assert "Audio format ID:" not in output_two


def test_encoding_summary_comparison_labels_use_stable_restrained_colors():
    comparable_labels = [
        "Container/ext",
        "Resolution",
        "Frame rate",
        "Video codec",
        "Video bitrate",
        "Audio codec",
        "Audio bitrate",
        "File size",
    ]
    colors = [summary_label_color(label) for label in comparable_labels]

    assert len(colors) == len(set(colors))
    assert all(color.startswith("#") and len(color) == 7 for color in colors)
    assert summary_label_color("Output status") == app_module.THEME["muted"]


def test_failed_video_encoding_summary_preserves_source_and_no_output_reason():
    info = _summary_test_info()
    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    failed = build_failed_encoding_summary_metadata(info, plan, "yt-dlp failed")
    source_text, output_text = build_encoding_summary_display(failed)

    assert "Format selector: 137+251" in source_text
    assert "Format selector:" not in output_text
    assert "Video format ID:" not in output_text
    assert "Audio format ID:" not in output_text
    assert "Output file path: Not produced" in output_text
    assert "Validation status: Failed" in output_text
    assert "Failure reason: yt-dlp failed" in output_text


def test_playlist_results_preserve_per_video_encoding_metadata():
    playlist = {"_type": "playlist", "entries": []}
    for video_id, format_id in [("one", "137"), ("two", "136")]:
        info = _summary_test_info()
        info["id"] = video_id
        info["formats"][0]["format_id"] = format_id
        plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)
        playlist["entries"].append(build_encoding_summary_metadata(info, plan, output_path=Path(f"{video_id}.mp4")))

    entries = iter_video_infos(playlist)

    assert entries[0]["vodforge_encoding_summary"]["source"]["Video format ID"] == "137"
    assert entries[1]["vodforge_encoding_summary"]["source"]["Video format ID"] == "136"
    assert entries[0]["vodforge_encoding_summary"]["output"]["Output file path"] == "one.mp4"
    assert entries[1]["vodforge_encoding_summary"]["output"]["Output file path"] == "two.mp4"


def test_auto_export_plan_calculates_source_aware_1080p_cbr_floor_and_audio():
    info = {
        "formats": [
            {"format_id": "137", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    assert plan.video_format_id == "137"
    assert plan.audio_format_id == "140"
    assert plan.output_width == 1920
    assert plan.output_height == 1080
    assert plan.video_bitrate_kbps == 2000
    assert plan.audio_bitrate_kbps in {160, 192}
    assert plan.format_selector == "137+140"
    assert "/137" not in plan.format_selector
    assert "true 1080p source" in plan.summary


def test_export_mode_labels_mark_auto_recommended_without_changing_canonical_values():
    assert EXPORT_MODES == ["Auto CBR (Recommended)", "Strict Compliance", "Manual Override"]
    assert export_mode_display_name(ExportMode.AUTO_CBR) == "Auto CBR (Recommended)"
    assert export_mode_from_display_name("Auto CBR (Recommended)") == ExportMode.AUTO_CBR
    assert export_mode_from_display_name("Auto CBR") == ExportMode.AUTO_CBR
    assert ExportMode.AUTO_CBR.value == "Auto CBR"
    assert ExportMode.STRICT_COMPLIANCE.value == "Strict Compliance"


def test_export_mode_descriptions_state_the_actual_rate_control_behavior():
    auto = export_mode_description(ExportMode.AUTO_CBR)
    strict = export_mode_description(ExportMode.STRICT_COMPLIANCE)
    manual = export_mode_description(ExportMode.MANUAL_OVERRIDE)

    assert auto.startswith("Recommended.")
    assert "source quality and resolution" in auto
    assert "10 Mbps video" in strict
    assert "320 kbps audio" in strict
    assert "cannot add detail" in strict
    assert "exact video bitrate, audio codec, audio bitrate, and encoding speed" in manual


def test_manual_override_keeps_source_selection_but_replaces_encode_settings():
    info = {
        "formats": [
            {"format_id": "137", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.MANUAL_OVERRIDE, max_height=1080)
    manual = apply_manual_export_settings(
        plan,
        ManualExportSettings(video_bitrate_kbps=15000, audio_bitrate_kbps=256, audio_sample_rate="44100", audio_channels="1", audio_codec=ManualAudioCodec.MP3, x264_preset="fast"),
    )

    assert manual.format_selector == "137+140"
    assert manual.video_format_id == "137"
    assert manual.audio_format_id == "140"
    assert manual.video_bitrate_kbps == 15000
    assert manual.audio_bitrate_kbps == 256
    assert manual.audio_sample_rate == "44100"
    assert manual.audio_channels == "1"
    assert manual.output_audio_codec is ManualAudioCodec.MP3
    assert manual.x264_preset == "fast"


def test_auto_export_plan_never_falls_back_to_video_only_selector():
    info = {
        "formats": [
            {"format_id": "video-dynamic", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
            {"format_id": "audio-dynamic", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 96, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    assert plan.format_selector == "video-dynamic+audio-dynamic"
    assert "/video-dynamic" not in plan.format_selector


def test_auto_export_plan_requires_audio_instead_of_creating_video_only_output():
    info = {
        "formats": [
            {"format_id": "video-only", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
        ]
    }

    with pytest.raises(RuntimeError, match="No usable audio"):
        build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)


def test_sanity_no_1080p_selects_720p_and_does_not_apply_1080p_floor():
    info = {
        "formats": [
            {"format_id": "136", "height": 720, "width": 1280, "ext": "mp4", "vcodec": "avc1.64001f", "acodec": "none", "tbr": 1100, "fps": 30},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    assert plan.video_format_id == "136"
    assert plan.output_height == 720
    assert plan.video_bitrate_kbps == 1500
    assert plan.video_bitrate_kbps < 2000
    assert "not available in 1080p" in " ".join(plan.warnings)


def test_sanity_high_quality_1080p_calculates_above_minimum_floor():
    info = {
        "formats": [
            {"format_id": "hq1080", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 5200, "fps": 30},
            {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 192, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    assert plan.video_format_id == "hq1080"
    assert plan.output_height == 1080
    assert plan.video_bitrate_kbps > 2000
    assert plan.video_bitrate_kbps == 6000


def test_strict_compliance_uses_fixed_requested_profile_with_source_limited_warnings():
    info = {
        "formats": [
            {"format_id": "399", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "av01.0.08M.08", "acodec": "none", "tbr": 583, "fps": 30},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.STRICT_COMPLIANCE, max_height=1080)

    assert plan.video_bitrate_kbps == 10000
    assert plan.audio_bitrate_kbps == 320
    assert any("Strict Compliance target is far above" in warning for warning in plan.warnings)


def test_strict_compliance_uses_same_source_selection_as_auto_cbr():
    info = {
        "formats": [
            {"format_id": "399", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "av01.0.08M.08", "acodec": "none", "tbr": 583, "fps": 30},
            {"format_id": "137", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
            {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160, "asr": 48000, "audio_channels": 2},
        ]
    }

    auto_plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)
    strict_plan = build_auto_export_plan(info, mode=ExportMode.STRICT_COMPLIANCE, max_height=1080)

    assert auto_plan.video_format_id == "137"
    assert strict_plan.video_format_id == auto_plan.video_format_id
    assert strict_plan.audio_format_id == auto_plan.audio_format_id
    assert strict_plan.format_selector == auto_plan.format_selector
    assert strict_plan.video_bitrate_kbps == 10000
    assert strict_plan.audio_bitrate_kbps == 320


def test_selector_does_not_combine_progressive_av_format_with_separate_audio_when_video_only_exists():
    info = {
        "formats": [
            {"format_id": "22", "height": 720, "width": 1280, "ext": "mp4", "vcodec": "avc1.64001f", "acodec": "mp4a.40.2", "tbr": 1100, "abr": 128, "fps": 30},
            {"format_id": "136", "height": 720, "width": 1280, "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none", "tbr": 1000, "fps": 30},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    assert plan.video_format_id == "136"
    assert plan.audio_format_id == "140"
    assert plan.format_selector == "136+140"
    assert plan.format_selector != "22+140"


def test_selector_uses_progressive_av_format_directly_when_no_video_only_format_exists():
    info = {
        "formats": [
            {"format_id": "22", "height": 720, "width": 1280, "ext": "mp4", "vcodec": "avc1.64001f", "acodec": "mp4a.40.2", "tbr": 1100, "abr": 128, "fps": 30},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        ]
    }

    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    assert plan.video_format_id == "22"
    assert plan.audio_format_id == "22"
    assert plan.format_selector == "22"


def test_windows_safe_filenames_strip_hidden_format_chars_without_shortening_titles():
    info = {"title": "How to trust God @PastorNfluence\u200b", "id": "YqLLmjKkM1Y"}

    filename = video_file_name(info, ".mp4")

    assert "\u200b" not in filename
    assert filename == "How to trust God @PastorNfluence.mp4"


def test_transcode_uses_short_backend_temp_names_to_preserve_user_facing_title(monkeypatch, tmp_path: Path):
    title = "A Jurassic Adventure_ A T-Rex Hunt! 🦕 _ Dinosaur Videos with Sky and Finn"
    source = tmp_path / f"{title}.mp4"
    source.write_bytes(b"original")
    temp_output, backup = transcode_temp_paths(source)

    assert temp_output.name == "__vodforge-tmp.mp4"
    assert backup.name == "__vodforge-original.mp4"
    assert title not in temp_output.name
    assert title not in backup.name

    class FakePopen:
        def __init__(self, command, **kwargs):
            Path(command[-1]).write_bytes(b"complete encoded output")
            self.stdout = iter(["out_time_ms=1000000\n", "progress=end\n"])

        def wait(self):
            return 0

    seen: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return FakePopen(command, **kwargs)

    monkeypatch.setattr("yt_downloader.app.subprocess.Popen", fake_popen)

    transcode_to_vod_streaming_settings(source, "ffmpeg", duration_seconds=1.0)

    assert source.name == f"{title}.mp4"
    assert source.read_bytes() == b"complete encoded output"
    assert Path(seen["command"][-1]).name == "__vodforge-tmp.mp4"
    assert seen["kwargs"]["encoding"] == "utf-8"
    assert seen["kwargs"]["errors"] == "replace"


def test_transcode_atomic_replace_failure_preserves_downloaded_source(monkeypatch, tmp_path: Path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"downloaded source")

    class FakePopen:
        def __init__(self, command, **_kwargs):
            Path(command[-1]).write_bytes(b"encoded output")
            self.stdout = iter(["progress=end\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(app_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(app_module.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("commit failed")))

    with pytest.raises(RuntimeError, match="commit failed"):
        transcode_to_vod_streaming_settings(source, "ffmpeg")

    assert source.read_bytes() == b"downloaded source"
    assert not (tmp_path / "__vodforge-tmp.mp4").exists()


def test_terminate_and_reap_escalates_from_terminate_to_kill():
    calls: list[object] = []

    class Process:
        wait_calls = 0

        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def kill(self):
            calls.append("kill")

        def wait(self, *, timeout):
            calls.append(("wait", timeout))
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise app_module.subprocess.TimeoutExpired("ffmpeg", timeout)
            return -9

    terminate_and_reap_process(Process(), timeout_seconds=0.01)

    assert calls == ["terminate", ("wait", 0.01), "kill", ("wait", 0.01)]


def test_live_child_stays_registered_when_exit_cannot_be_confirmed():
    class Process:
        def poll(self):
            return None

        def terminate(self):
            return None

        def kill(self):
            return None

        def wait(self, *, timeout):
            raise app_module.subprocess.TimeoutExpired("child", timeout)

    process = Process()
    app_module.register_active_child_process(process)
    try:
        assert app_module.finalize_active_child_process(process) is False
        with app_module._ACTIVE_CHILD_PROCESS_LOCK:
            assert process in app_module._ACTIVE_CHILD_PROCESSES
    finally:
        app_module.unregister_active_child_process(process)


def test_yt_dlp_owned_subprocess_is_registered_and_reaped():
    import yt_dlp.postprocessor.ffmpeg as ffmpeg_postprocessor

    original_class = ffmpeg_postprocessor.Popen
    observed: list[bool] = []

    def operation():
        assert ffmpeg_postprocessor.Popen is not original_class
        process = ffmpeg_postprocessor.Popen(
            [app_module.sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=app_module.subprocess.PIPE,
            stderr=app_module.subprocess.PIPE,
        )
        with app_module._ACTIVE_CHILD_PROCESS_LOCK:
            observed.append(process in app_module._ACTIVE_CHILD_PROCESSES)
        app_module.terminate_and_reap_process(process, timeout_seconds=0.2)

    app_module.run_tracked_ytdlp_operation(operation)

    assert observed == [True]
    assert ffmpeg_postprocessor.Popen is original_class
    with app_module._ACTIVE_CHILD_PROCESS_LOCK:
        assert not app_module._ACTIVE_CHILD_PROCESSES


def test_cancelled_yt_dlp_operation_cannot_spawn_an_unowned_child():
    import yt_dlp.postprocessor.ffmpeg as ffmpeg_postprocessor

    checks = 0

    def control_check():
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise RuntimeError("cancelled")

    def operation():
        ffmpeg_postprocessor.Popen(
            [app_module.sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=app_module.subprocess.PIPE,
            stderr=app_module.subprocess.PIPE,
        )

    with pytest.raises(RuntimeError, match="cancelled"):
        app_module.run_tracked_ytdlp_operation(
            operation,
            control_check=control_check,
        )

    assert checks >= 2
    with app_module._ACTIVE_CHILD_PROCESS_LOCK:
        assert not app_module._ACTIVE_CHILD_PROCESSES


def test_tracked_ytdlp_operation_restores_popen_alias_imported_mid_operation():
    import sys
    import types
    import yt_dlp.utils as ytdlp_utils

    original_class = ytdlp_utils.Popen
    synthetic_name = "yt_dlp.synthetic_vodforge_test"
    synthetic = types.ModuleType(synthetic_name)

    def operation():
        synthetic.Popen = ytdlp_utils.Popen
        sys.modules[synthetic_name] = synthetic
        assert synthetic.Popen is not original_class

    try:
        app_module.run_tracked_ytdlp_operation(operation)
        assert synthetic.Popen is original_class
    finally:
        sys.modules.pop(synthetic_name, None)


def test_application_close_cancels_work_reaps_owned_child_then_destroys():
    class Process:
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def wait(self, *, timeout):
            assert timeout == app_module.PROCESS_TERMINATE_TIMEOUT_SECONDS
            return self.returncode

        def kill(self):
            self.returncode = -9

    class Value:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

    class Button:
        def config(self, **_kwargs):
            return None

    process = Process()
    app_module.register_active_child_process(process)
    app = DownloaderApp.__new__(DownloaderApp)
    app._closing = False
    app._close_terminator = None
    app.cancel_requested = False
    app.pending_jobs = [object()]
    app.worker = None
    app.status_var = Value()
    app.download_button = Button()
    app.cancel_button = Button()
    app.skip_video_button = Button()
    app.skip_url_button = Button()
    callbacks: list[object] = []
    destroyed: list[bool] = []
    app.after = lambda _delay, callback: callbacks.append(callback)
    app.destroy = lambda: destroyed.append(True)

    app._request_application_close()
    app._close_terminator.join(timeout=2)
    callbacks.pop(0)()

    assert app.cancel_requested is True
    assert app.pending_jobs == []
    assert process.poll() == -15
    assert destroyed == [True]
    with app_module._ACTIVE_CHILD_PROCESS_LOCK:
        assert process not in app_module._ACTIVE_CHILD_PROCESSES


def test_application_close_deadline_destroys_window_without_claiming_cleanup(monkeypatch):
    class AliveWorker:
        def is_alive(self):
            return True

    messages: list[str] = []
    destroyed: list[bool] = []
    app = DownloaderApp.__new__(DownloaderApp)
    app.worker = AliveWorker()
    app._close_terminator = None
    app._close_deadline = 0.0
    app.destroy = lambda: destroyed.append(True)
    monkeypatch.setattr(app_module, "write_diagnostic", messages.append)
    monkeypatch.setattr(app_module, "terminate_all_active_child_processes", lambda **_kwargs: None)

    app._finish_application_close_when_idle()

    assert destroyed == [True]
    assert any("cleanup could not be confirmed" in message for message in messages)


def test_close_time_worker_error_is_logged_without_modal_or_new_queue_work(monkeypatch):
    app = DownloaderApp.__new__(DownloaderApp)
    app._closing = True
    app.events = queue.Queue()
    app.events.put(("error", "Download cancelled by user"))
    logged: list[str] = []
    scheduled: list[object] = []
    app._append_log = logged.append
    app.after = lambda _delay, callback: scheduled.append(callback)
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda *_args, **_kwargs: pytest.fail("close-time errors must not open a modal"),
    )

    app._pump_events()

    assert logged == ["ERROR during application close: Download cancelled by user"]
    assert len(scheduled) == 1


def test_close_time_metadata_and_update_errors_do_not_open_modals(monkeypatch):
    app = DownloaderApp.__new__(DownloaderApp)
    app._closing = True
    app.events = queue.Queue()
    app.events.put(("metadata_error", "provider unavailable"))
    app.events.put(("update_check_error", "release host unavailable"))
    logged: list[str] = []
    diagnostics: list[str] = []
    scheduled: list[object] = []
    app._append_log = logged.append
    app.after = lambda _delay, callback: scheduled.append(callback)
    monkeypatch.setattr(app_module, "write_diagnostic", diagnostics.append)
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda *_args, **_kwargs: pytest.fail("close-time metadata errors must not open a modal"),
    )
    monkeypatch.setattr(
        app_module.messagebox,
        "showinfo",
        lambda *_args, **_kwargs: pytest.fail("close-time update errors must not open a modal"),
    )

    app._pump_events()

    assert logged == ["Metadata preview ended during application close: provider unavailable"]
    assert diagnostics == ["update check ended during application close: release host unavailable"]
    assert len(scheduled) == 1


def test_transcode_cancellation_is_checked_while_ffmpeg_is_quiet(monkeypatch, tmp_path: Path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"downloaded source")
    terminated = threading.Event()
    killed = threading.Event()

    class BlockingOutput:
        def __iter__(self):
            return self

        def __next__(self):
            terminated.wait(timeout=2)
            raise StopIteration

    class FakePopen:
        def __init__(self, *_args, **_kwargs):
            self.stdout = BlockingOutput()

        def poll(self):
            return None if not terminated.is_set() else -15

        def terminate(self):
            terminated.set()

        def kill(self):
            killed.set()
            terminated.set()

        def wait(self, timeout=None):
            if timeout is not None and not terminated.wait(timeout=timeout):
                raise app_module.subprocess.TimeoutExpired("ffmpeg", timeout)
            return -15

    monkeypatch.setattr(app_module.subprocess, "Popen", FakePopen)

    with pytest.raises(RuntimeError, match="cancelled"):
        transcode_to_vod_streaming_settings(
            source,
            "ffmpeg",
            control_check=lambda: (_ for _ in ()).throw(RuntimeError("cancelled")),
        )

    assert terminated.is_set()
    assert not killed.is_set()
    assert source.read_bytes() == b"downloaded source"


def test_transcode_rechecks_cancellation_after_encoder_output_closes(monkeypatch, tmp_path: Path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"downloaded source")

    class FakePopen:
        def __init__(self, *_args, **_kwargs):
            self.stdout = iter(())

        def poll(self):
            return -15

        def terminate(self):
            return None

        def kill(self):
            return None

        def wait(self, timeout=None):
            return -15

    checks = 0

    def control_check():
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise RuntimeError("Download cancelled by user")

    monkeypatch.setattr(app_module.subprocess, "Popen", FakePopen)

    with pytest.raises(RuntimeError, match="cancelled"):
        transcode_to_vod_streaming_settings(source, "ffmpeg", control_check=control_check)

    assert source.read_bytes() == b"downloaded source"


def test_ffprobe_json_uses_unicode_safe_decoding(monkeypatch, tmp_path: Path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs

        class Result:
            stdout = '{"format": {"format_name": "mov,mp4,m4a"}, "streams": []}'

        return Result()

    monkeypatch.setattr("yt_downloader.app.subprocess.run", fake_run)

    data = run_ffprobe_json("ffprobe", video)

    assert data["format"]["format_name"] == "mov,mp4,m4a"
    assert seen["kwargs"]["encoding"] == "utf-8"
    assert seen["kwargs"]["errors"] == "replace"
    assert seen["kwargs"]["timeout"] == app_module.FFPROBE_TIMEOUT_SECONDS
    assert "-show_entries" in seen["command"]
    assert "-show_streams" not in seen["command"]
    show_entries = seen["command"][seen["command"].index("-show_entries") + 1]
    assert "format_tags" in show_entries
    assert "stream_disposition" in show_entries


def test_output_validator_accepts_expected_mp4_and_mp3_streams(tmp_path: Path):
    mp4 = tmp_path / "video.mp4"
    mp3 = tmp_path / "audio.mp3"
    mp4.write_bytes(b"mp4 bytes")
    mp3.write_bytes(b"mp3 bytes")
    mp4_probe = {
        "format": {"format_name": "mov,mp4,m4a", "duration": "60.0"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    mp3_probe = {
        "format": {"format_name": "mp3", "duration": "60.0"},
        "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
    }

    assert validate_output_artifact(mp4, OutputType.MP4, "ffprobe", expected_duration_seconds=60, ffprobe_data=mp4_probe) is mp4_probe
    assert validate_output_artifact(mp3, OutputType.MP3, "ffprobe", expected_duration_seconds=60, ffprobe_data=mp3_probe) is mp3_probe


def test_output_validator_honors_the_selected_manual_mp4_audio_codec(tmp_path: Path):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"mp4 bytes")
    probe = {
        "format": {"format_name": "mov,mp4", "duration": "60.0"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "mp3"},
        ],
    }

    assert validate_output_artifact(
        output,
        OutputType.MP4,
        "ffprobe",
        expected_audio_codec="mp3",
        ffprobe_data=probe,
    ) is probe
    with pytest.raises(RuntimeError, match="AAC audio"):
        validate_output_artifact(output, OutputType.MP4, "ffprobe", ffprobe_data=probe)


@pytest.mark.parametrize(
    ("probe", "message"),
    [
        (
            {"format": {"format_name": "mov,mp4", "duration": "60"}, "streams": [{"codec_type": "video", "codec_name": "h264"}]},
            "AAC audio",
        ),
        (
            {"format": {"format_name": "mov,mp4", "duration": "60"}, "streams": [{"codec_type": "audio", "codec_name": "aac"}]},
            "H.264 video",
        ),
        (
            {"format": {"format_name": "mov,mp4", "duration": "20"}, "streams": [{"codec_type": "video", "codec_name": "h264"}, {"codec_type": "audio", "codec_name": "aac"}]},
            "truncated",
        ),
    ],
)
def test_output_validator_rejects_invalid_or_truncated_mp4(tmp_path: Path, probe, message):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"candidate")

    with pytest.raises(RuntimeError, match=message):
        validate_output_artifact(
            output,
            OutputType.MP4,
            "ffprobe",
            expected_duration_seconds=60,
            ffprobe_data=probe,
        )


def test_output_validator_rejects_empty_and_wrong_codec_mp3(tmp_path: Path):
    empty = tmp_path / "empty.mp3"
    empty.touch()
    with pytest.raises(RuntimeError, match="empty"):
        validate_output_artifact(empty, OutputType.MP3, "ffprobe", ffprobe_data={})

    output = tmp_path / "audio.mp3"
    output.write_bytes(b"candidate")
    probe = {
        "format": {"format_name": "mp3", "duration": "10"},
        "streams": [{"codec_type": "audio", "codec_name": "aac"}],
    }
    with pytest.raises(RuntimeError, match="valid MP3 audio"):
        validate_output_artifact(output, OutputType.MP3, "ffprobe", ffprobe_data=probe)


def test_cookiefile_option_is_only_added_when_user_enabled_cookies(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    enabled = apply_ytdlp_cookie_options({}, use_cookies=True, cookie_file=cookies)
    disabled = apply_ytdlp_cookie_options({}, use_cookies=False, cookie_file=cookies)

    assert enabled["cookiefile"] == str(cookies)
    assert "cookiefile" not in disabled


def test_cookie_source_selection_keeps_public_file_and_browser_modes_exclusive(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"

    assert cookie_inputs_for_source(CookieSource.PUBLIC, cookies, "Firefox") == (False, None, None)
    assert cookie_inputs_for_source(CookieSource.FILE, cookies, "Firefox") == (True, cookies, None)
    assert cookie_inputs_for_source(CookieSource.BROWSER, cookies, "Firefox") == (True, None, "firefox")
    assert cookie_inputs_for_source("invalid", cookies, "Firefox") == (False, None, None)


def test_browser_cookie_option_uses_selected_browser_without_cookie_file(monkeypatch):
    monkeypatch.setattr(app_module.sys, "platform", "linux")

    enabled = apply_ytdlp_cookie_options({}, use_cookies=True, cookie_file=None, cookie_browser="chrome")
    disabled = apply_ytdlp_cookie_options({}, use_cookies=False, cookie_file=None, cookie_browser="chrome")

    assert enabled["cookiesfrombrowser"] == ("chrome",)
    assert "cookiesfrombrowser" not in disabled


def test_cookie_file_takes_precedence_over_browser_cookie_import(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    opts = apply_ytdlp_cookie_options({}, use_cookies=True, cookie_file=cookies, cookie_browser="chrome")

    assert opts["cookiefile"] == str(cookies)
    assert "cookiesfrombrowser" not in opts


def test_windows_chromium_cookie_error_is_actionable(monkeypatch):
    monkeypatch.setattr(app_module.sys, "platform", "win32")

    with pytest.raises(RuntimeError, match="exported YouTube cookies.txt"):
        apply_ytdlp_cookie_options({}, use_cookies=True, cookie_file=None, cookie_browser="Chrome")


def test_windows_firefox_browser_cookie_import_remains_allowed(monkeypatch):
    monkeypatch.setattr(app_module.sys, "platform", "win32")

    opts = apply_ytdlp_cookie_options({}, use_cookies=True, cookie_file=None, cookie_browser="Firefox")

    assert opts["cookiesfrombrowser"] == ("firefox",)


def test_ytdlp_cookie_and_503_errors_are_rewritten_for_users():
    cookie_message = format_ytdlp_user_error("ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271 for more info")
    unavailable_message = format_ytdlp_user_error("ERROR: [download] Got error HTTP Error 503: Service Unavailable. Giving up after 10 retries")

    assert "exported YouTube cookies.txt" in cookie_message
    assert "Firefox browser cookies" in cookie_message
    assert "YouTube returned HTTP 503" in unavailable_message
    assert "cookies.txt" in unavailable_message


def test_sanity_different_audio_codec_selects_best_available_audio_and_outputs_aac(tmp_path: Path):
    formats = [
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160, "asr": 48000, "audio_channels": 2},
    ]

    selected = choose_best_audio_format(formats)
    info = {
        "formats": [
            {"format_id": "137", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
            *formats,
        ]
    }
    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)
    command = build_vod_ffmpeg_command("ffmpeg", tmp_path / "source.mp4", tmp_path / "out.mp4", video_bitrate_kbps=plan.video_bitrate_kbps, audio_bitrate_kbps=plan.audio_bitrate_kbps)
    joined = " ".join(command)

    assert selected is not None
    assert selected["format_id"] == "251"
    assert plan.audio_format_id == "251"
    assert plan.format_selector == "137+251"
    assert "-c:a aac" in joined
    assert f"-b:a {plan.audio_bitrate_kbps}k" in joined
    assert choose_audio_bitrate_kbps(129) == 160
    assert choose_audio_bitrate_kbps(208) == 256


def test_mp4_audio_source_does_not_trade_material_quality_for_direct_transport():
    formats = [
        {"format_id": "hls-best", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 160, "protocol": "m3u8_native"},
        {"format_id": "direct-low", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 96, "protocol": "https"},
    ]

    assert choose_best_audio_format(formats)["format_id"] == "hls-best"

    formats[1]["abr"] = 150
    assert choose_best_audio_format(formats)["format_id"] == "direct-low"


def test_library_media_filter_keeps_original_metadata_indices():
    items = [
        {"id": "old-defaults-to-mp4"},
        {"id": "audio", "vodforge_output_type": "MP3"},
        {"id": "video", "vodforge_output_type": "MP4"},
        {"id": "inferred-audio", "vodforge_encoding_summary": {"output": {"Output file path": "beat.mp3"}}},
    ]

    assert metadata_indices_for_output_type(items, OutputType.MP4) == [0, 2]
    assert metadata_indices_for_output_type(items, OutputType.MP3) == [1, 3]


def test_thumbnail_cache_path_is_private_deterministic_and_filename_safe(tmp_path: Path):
    info = {
        "id": "../../private/video",
        "title": "Beat",
        "thumbnail": "https://i.ytimg.com/vi/example/maxresdefault.jpg?token=value",
    }

    first = cached_thumbnail_path(info, data_dir=tmp_path)
    second = cached_thumbnail_path(info, data_dir=tmp_path)

    assert first == second
    assert first is not None
    assert first.parent == tmp_path / "thumbnail-cache"
    assert first.suffix == ".jpeg"
    assert len(first.stem) == 32
    assert all(character in "0123456789abcdef" for character in first.stem)


def test_sanity_missing_audio_raises_instead_of_video_only_output():
    info = {
        "formats": [
            {"format_id": "video-only", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
        ]
    }

    with pytest.raises(RuntimeError, match="No usable audio"):
        build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)


def test_vod_ffmpeg_command_accepts_per_file_cbr_bitrates(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"

    command = build_vod_ffmpeg_command("ffmpeg", source, output, video_bitrate_kbps=2000, audio_bitrate_kbps=192)
    joined = " ".join(command)

    assert "-b:v 2000k -minrate 2000k -maxrate 2000k -bufsize 4000k" in joined
    assert "-pix_fmt yuv420p" in joined
    assert "-profile:v high" in joined
    assert "-x264-params nal-hrd=cbr:force-cfr=1" in joined
    assert "-movflags +faststart" in joined
    assert "-map 0:a:0?" in joined
    assert "-map 0:a?" not in joined
    assert "-c:a aac -b:a 192k -ar 48000 -ac 2" in joined
    assert "-pass" not in command


def test_cleanup_legacy_encode_sidecars_removes_old_passlog_and_temp_files(tmp_path: Path):
    video = tmp_path / "video [abc123].mp4"
    video.write_text("final")
    leftovers = [
        tmp_path / "video [abc123].ffmpeg-passlog-0",
        tmp_path / "video [abc123].ffmpeg-passlog-0.log.mbtree",
        tmp_path / "video [abc123].vodforge-cbr-tmp.mp4",
        tmp_path / "video [abc123].vodforge-tmp.mp4",
        tmp_path / "video [abc123].pre-vodforge.mp4",
    ]
    for path in leftovers:
        path.write_text("leftover")

    cleanup_legacy_encode_sidecars(video)

    assert video.read_text() == "final"
    assert all(not path.exists() for path in leftovers)


def test_transcode_rejects_nonzero_ffmpeg_exit_even_when_output_reaches_near_end(monkeypatch, tmp_path: Path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"original")

    class FakePopen:
        def __init__(self, command, **_kwargs):
            Path(command[-1]).write_bytes(b"complete encoded output")
            self.stdout = iter([
                "out_time_ms=9900000\n",
                "progress=continue\n",
                "[h264] Late SEI is not implemented\n",
            ])

        def wait(self):
            return 1

    monkeypatch.setattr("yt_downloader.app.subprocess.Popen", FakePopen)
    with pytest.raises(RuntimeError, match="ffmpeg exited with code 1"):
        transcode_to_vod_streaming_settings(source, "ffmpeg", duration_seconds=10.0, use_nvenc=True)

    assert source.read_bytes() == b"original"
    assert not (tmp_path / "video.vodforge-cbr-tmp.mp4").exists()
    assert not (tmp_path / "video.pre-vodforge.mp4").exists()


def test_transcode_rejects_nonzero_output_when_temp_duration_is_incomplete(monkeypatch, tmp_path: Path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"original")

    class FakePopen:
        def __init__(self, command, **_kwargs):
            Path(command[-1]).write_bytes(b"truncated output")
            self.stdout = iter(["out_time_ms=5000000\n", "progress=continue\n"])

        def wait(self):
            return 1

    monkeypatch.setattr("yt_downloader.app.subprocess.Popen", FakePopen)
    monkeypatch.setattr("yt_downloader.app._ffprobe_for_ffmpeg", lambda _ffmpeg: "ffprobe")
    monkeypatch.setattr(
        "yt_downloader.app.run_ffprobe_json",
        lambda _ffprobe, _path: {"format": {"duration": "5.0"}, "streams": [{"codec_type": "video"}]},
    )

    with pytest.raises(RuntimeError, match="ffmpeg exited with code 1"):
        transcode_to_vod_streaming_settings(source, "ffmpeg", duration_seconds=10.0, use_nvenc=True)

    assert source.read_bytes() == b"original"
    assert not (tmp_path / "video.vodforge-cbr-tmp.mp4").exists()


def test_parse_url_list_text_reads_one_youtube_url_per_line_and_ignores_comments():
    text = """
    # batch file for VODForge
    https://www.youtube.com/watch?v=one

    https://www.youtube.com/playlist?list=PL123
    <https://youtu.be/two?list=PL&t=30s|youtu.be/two?list=PL&t=30s>
    not a url
    """

    assert parse_url_list_text(text) == [
        "https://www.youtube.com/watch?v=one",
        "https://www.youtube.com/playlist?list=PL123",
        "https://youtu.be/two?list=PL&t=30s",
    ]


def test_append_batch_failure_report_writes_each_failed_url_and_issue(tmp_path: Path):
    report = tmp_path / "batch-url-failures.txt"

    append_batch_failure_report(report, "https://www.youtube.com/watch?v=bad", "source analysis failed")
    append_batch_failure_report(report, "https://www.youtube.com/playlist?list=PL", RuntimeError("one playlist item failed"))

    text = report.read_text(encoding="utf-8")
    assert "https://www.youtube.com/watch?v=bad" in text
    assert "source analysis failed" in text
    assert "https://www.youtube.com/playlist?list=PL" in text
    assert "one playlist item failed" in text
    assert text.count("URL:") == 2


def test_batch_worker_continues_after_failed_url_and_writes_failure_report(monkeypatch, tmp_path: Path):
    report = tmp_path / "batch-url-failures.txt"
    monkeypatch.setattr(app_module, "BATCH_FAILURE_REPORT_PATH", report)
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app._active_progress_context = None
    processed: list[str] = []

    def fake_single(job, *, emit_done=True, re_raise=False):
        processed.append(job.url)
        if "bad" in job.url:
            raise RuntimeError("bad video unavailable")
        return DownloadOutcome(success_count=1)

    app._download_worker_single = fake_single
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=ok1",
        urls=["https://www.youtube.com/watch?v=ok1", "https://www.youtube.com/watch?v=bad", "https://www.youtube.com/watch?v=ok2"],
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=False,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    app._download_worker(job)

    assert processed == job.urls
    report_text = report.read_text(encoding="utf-8")
    assert "https://www.youtube.com/watch?v=bad" in report_text
    assert "bad video unavailable" in report_text
    partial_messages = [payload for kind, payload in list(app.events.queue) if kind == "partial"]
    assert any("2 valid output(s)" in str(message) and "1 failed" in str(message) for message in partial_messages)
    assert not any(kind == "done" for kind, _payload in list(app.events.queue))


def test_batch_worker_never_reports_completion_when_every_url_fails(monkeypatch, tmp_path: Path):
    report = tmp_path / "batch-url-failures.txt"
    monkeypatch.setattr(app_module, "BATCH_FAILURE_REPORT_PATH", report)
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app._active_progress_context = None
    app._download_worker_single = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider failure"))
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=bad1",
        urls=["https://www.youtube.com/watch?v=bad1", "https://www.youtube.com/watch?v=bad2"],
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=False,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    app._download_worker(job)

    events = list(app.events.queue)
    assert any(kind == "error" and "no valid output" in str(payload).lower() for kind, payload in events)
    assert not any(kind in {"done", "partial"} for kind, _payload in events)


@pytest.mark.parametrize("successes_before_cancel", [0, 1])
def test_batch_cancellation_reports_stopped_or_partial_truthfully(monkeypatch, tmp_path: Path, successes_before_cancel: int):
    monkeypatch.setattr(app_module, "BATCH_FAILURE_REPORT_PATH", tmp_path / "batch-url-failures.txt")
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app._active_progress_context = None
    calls = 0

    def fake_single(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls > successes_before_cancel:
            raise RuntimeError("Download cancelled by user")
        return DownloadOutcome(success_count=1)

    app._download_worker_single = fake_single
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=one",
        urls=["https://www.youtube.com/watch?v=one", "https://www.youtube.com/watch?v=two"],
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    app._download_worker(job)

    events = list(app.events.queue)
    expected_kind = "partial" if successes_before_cancel else "stopped"
    assert any(kind == expected_kind and "cancel" in str(payload).lower() for kind, payload in events)
    assert not any(kind in {"done", "error"} for kind, _payload in events)


def test_default_single_video_pipeline_uses_one_extractor_pass(monkeypatch, tmp_path: Path):
    preflight = {
        "id": "abc123",
        "title": "Fast Path",
        "uploader": "Creator",
        "webpage_url": "https://www.youtube.com/watch?v=abc123",
        "duration": 30,
        "formats": [
            {
                "format_id": "137",
                "height": 1080,
                "width": 1920,
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "tbr": 3000,
                "fps": 30,
                "protocol": "https",
            },
            {
                "format_id": "251",
                "ext": "webm",
                "vcodec": "none",
                "acodec": "opus",
                "abr": 128,
                "asr": 48000,
                "audio_channels": 2,
                "protocol": "https",
            },
        ],
    }
    calls = {"extract": 0, "process": 0}

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, *, download):
            assert download is False
            calls["extract"] += 1
            return dict(preflight)

        def process_ie_result(self, info, *, download):
            assert download is True
            calls["process"] += 1
            staged = Path(
                self.opts["outtmpl"]
                .replace("%(id)s", "abc123")
                .replace("%(ext)s", "mp4")
            )
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(b"downloaded media")
            return dict(info)

    class FakeYtDlp:
        YoutubeDL = FakeYoutubeDL

    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: FakeYtDlp)
    monkeypatch.setattr(app_module, "transcode_to_vod_streaming_settings", lambda path, *_args, **_kwargs: path)
    probe = {
        "format": {"format_name": "mov,mp4,m4a", "duration": "30"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    monkeypatch.setattr(app_module, "validate_output_artifact", lambda *_args, **_kwargs: probe)
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app.skip_video_requested = False
    app.skip_url_requested = False
    app._active_progress_context = None
    app._last_progress_event_at = 0.0
    app._find_ffmpeg = lambda: "ffmpeg"
    app._find_ffprobe = lambda: "ffprobe"
    app._find_deno = lambda: None
    job = DownloadJob(
        url=preflight["webpage_url"],
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    outcome = app._download_worker_single(job)

    expected = tmp_path / "Creator" / "videos - no playlist" / "Fast Path [abc123]" / "Fast Path.mp4"
    assert calls == {"extract": 1, "process": 1}
    assert outcome == DownloadOutcome(success_count=1)
    assert expected.read_bytes() == b"downloaded media"
    emitted_events = list(app.events.queue)
    assert any(kind == "done" for kind, _payload in emitted_events)
    assert any(
        kind == "job_metadata" and payload["job"] is job and payload["info"]["id"] == "abc123"
        for kind, payload in emitted_events
    )
    assert not any(kind == "metadata" for kind, _payload in emitted_events)


def test_ignore_playlists_worker_keeps_full_watch_url_playlist_route(monkeypatch, tmp_path: Path):
    source_url = "https://www.youtube.com/watch?v=abc123&list=PLreal&index=4"
    preflight = {
        "id": "abc123",
        "title": "Playlist Item",
        "uploader": "Creator",
        "webpage_url": "https://www.youtube.com/watch?v=abc123",
        "duration": 30,
        "formats": [
            {
                "format_id": "137",
                "height": 1080,
                "width": 1920,
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "tbr": 3000,
                "fps": 30,
                "protocol": "https",
            },
            {
                "format_id": "251",
                "ext": "webm",
                "vcodec": "none",
                "acodec": "opus",
                "abr": 128,
                "asr": 48000,
                "audio_channels": 2,
                "protocol": "https",
            },
        ],
    }
    calls: list[tuple[str, bool]] = []

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, *, download):
            assert download is False
            calls.append((url, bool(self.opts.get("extract_flat"))))
            if self.opts.get("extract_flat") == "in_playlist":
                return {
                    "_type": "playlist",
                    "id": "PLreal",
                    "title": "Real Playlist",
                    "entries": [
                        {
                            "id": "abc123",
                            "playlist_index": 4,
                            "webpage_url": "https://www.youtube.com/watch?v=abc123",
                        }
                    ],
                }
            return dict(preflight)

        def process_ie_result(self, info, *, download):
            assert download is True
            staged = Path(
                self.opts["outtmpl"]
                .replace("%(id)s", "abc123")
                .replace("%(ext)s", "mp4")
            )
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(b"downloaded media")
            return dict(info)

    class FakeYtDlp:
        YoutubeDL = FakeYoutubeDL

    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: FakeYtDlp)
    monkeypatch.setattr(app_module, "transcode_to_vod_streaming_settings", lambda path, *_args, **_kwargs: path)
    probe = {
        "format": {"format_name": "mov,mp4,m4a", "duration": "30"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    monkeypatch.setattr(app_module, "validate_output_artifact", lambda *_args, **_kwargs: probe)
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app.skip_video_requested = False
    app.skip_url_requested = False
    app._active_progress_context = None
    app._last_progress_event_at = 0.0
    app._find_ffmpeg = lambda: "ffmpeg"
    app._find_ffprobe = lambda: "ffprobe"
    app._find_deno = lambda: None
    job = DownloadJob(
        url=source_url,
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    outcome = app._download_worker_single(job)

    expected = tmp_path / "Creator" / "playlists" / "Real Playlist" / "Playlist Item [abc123]" / "Playlist Item.mp4"
    assert calls[0] == (source_url, True)
    assert outcome == DownloadOutcome(success_count=1)
    assert expected.read_bytes() == b"downloaded media"
    emitted_metadata = [payload for kind, payload in app.events.queue if kind == "job_metadata"]
    assert emitted_metadata
    assert emitted_metadata[-1]["info"]["playlist_id"] == "PLreal"
    assert emitted_metadata[-1]["info"]["playlist_title"] == "Real Playlist"


@pytest.mark.parametrize("output_type", [OutputType.MP4, OutputType.MP3])
def test_ytdlp_format_probes_use_the_per_run_staging_directory(monkeypatch, tmp_path: Path, output_type: OutputType):
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app._find_ffmpeg = lambda: "ffmpeg"
    app._find_deno = lambda: None
    staging_dir = tmp_path / "output" / ".yt-dlp-downloader-staging" / "run-id"
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=source",
        output_dir=tmp_path / "output",
        output_type=output_type,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    opts = app._build_ydl_options(job, staging_dir, format_selector="251" if output_type == OutputType.MP3 else "137+251")

    assert opts["paths"] == {"home": str(staging_dir), "temp": str(staging_dir)}
    assert Path(opts["paths"]["temp"]).is_absolute()
    ytdlp_module = load_yt_dlp()
    assert ytdlp_module is not None
    with ytdlp_module.YoutubeDL(opts) as ydl:
        assert Path(ydl.get_output_path("temp")) == staging_dir


def test_playlist_loads_cookie_source_once_and_reuses_memory_session(monkeypatch, tmp_path: Path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    session_cookie = object()
    option_history: list[dict[str, object]] = []

    def video_info(video_id: str) -> dict[str, object]:
        return {
            "id": video_id,
            "title": f"Video {video_id}",
            "uploader": "Creator",
            "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
            "duration": 30,
            "formats": [
                {
                    "format_id": "137",
                    "height": 1080,
                    "width": 1920,
                    "ext": "mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "tbr": 3000,
                    "fps": 30,
                    "protocol": "https",
                },
                {
                    "format_id": "251",
                    "ext": "webm",
                    "vcodec": "none",
                    "acodec": "opus",
                    "abr": 128,
                    "asr": 48000,
                    "audio_channels": 2,
                    "protocol": "https",
                },
            ],
        }

    class CookieJar(list):
        def set_cookie(self, cookie):
            if cookie not in self:
                self.append(cookie)

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts
            option_history.append(dict(opts))
            self.cookiejar = CookieJar([session_cookie] if "cookiefile" in opts else [])

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, *, download):
            assert download is False
            assert session_cookie in self.cookiejar
            if self.opts.get("extract_flat") == "in_playlist":
                return {
                    "id": "playlist",
                    "title": "Playlist",
                    "entries": [
                        {"id": "one", "webpage_url": "https://www.youtube.com/watch?v=one"},
                        {"id": "two", "webpage_url": "https://www.youtube.com/watch?v=two"},
                    ],
                }
            return video_info("two" if "two" in url else "one")

        def process_ie_result(self, info, *, download):
            assert download is True
            assert session_cookie in self.cookiejar
            staged = Path(
                self.opts["outtmpl"]
                .replace("%(id)s", str(info["id"]))
                .replace("%(ext)s", "mp4")
            )
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(b"downloaded media")
            return dict(info)

    class FakeYtDlp:
        YoutubeDL = FakeYoutubeDL

    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: FakeYtDlp)
    monkeypatch.setattr(app_module, "transcode_to_vod_streaming_settings", lambda path, *_args, **_kwargs: path)
    monkeypatch.setattr(
        app_module,
        "validate_output_artifact",
        lambda *_args, **_kwargs: {
            "format": {"format_name": "mov,mp4,m4a", "duration": "30"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        },
    )
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app.skip_video_requested = False
    app.skip_url_requested = False
    app._active_progress_context = None
    app._last_progress_event_at = 0.0
    app._find_ffmpeg = lambda: "ffmpeg"
    app._find_ffprobe = lambda: "ffprobe"
    app._find_deno = lambda: None
    job = DownloadJob(
        url="https://www.youtube.com/playlist?list=playlist",
        output_dir=tmp_path / "output",
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=False,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
        use_cookies=True,
        cookie_file=cookie_file,
    )

    outcome = app._download_worker_single(job)

    assert outcome == DownloadOutcome(success_count=2)
    assert len(option_history) == 5
    assert sum("cookiefile" in opts for opts in option_history) == 1
    assert all("cookiesfrombrowser" not in opts for opts in option_history)


def test_progress_hook_coalesces_high_frequency_updates(monkeypatch):
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app.skip_video_requested = False
    app.skip_url_requested = False
    app._active_progress_context = None
    app._last_progress_event_at = 0.0
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 10.0)

    for downloaded in range(1, 1001):
        app._progress_hook(
            {
                "status": "downloading",
                "downloaded_bytes": downloaded,
                "total_bytes": 1000,
                "speed": 1_000_000,
                "eta": 1,
                "filename": "sample.mp4",
            }
        )

    events = list(app.events.queue)
    assert len(events) == 6
    assert sum(kind == "progress" for kind, _payload in events) == 2


def test_queued_preview_worker_serializes_preview_fetches(tmp_path: Path):
    app = DownloaderApp.__new__(DownloaderApp)
    app.pending_jobs = []
    app._queued_preview_requests = None
    app._queued_preview_thread = None
    active = 0
    maximum_active = 0
    completed = 0
    lock = threading.Lock()

    def fake_preview(_job):
        nonlocal active, maximum_active, completed
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.005)
        with lock:
            active -= 1
            completed += 1

    app._queue_preview_worker = fake_preview
    for index in range(12):
        job = DownloadJob(
            url=f"https://www.youtube.com/watch?v={index}",
            output_dir=tmp_path,
            output_type=OutputType.MP4,
            quality_label="1080p Full HD",
            export_mode=ExportMode.AUTO_CBR,
            manual_settings=ManualExportSettings(),
            mp3_settings=Mp3ExportSettings(),
            single_video_only=True,
            use_nvenc=False,
            embed_thumbnail=False,
            write_thumbnail=False,
            embed_metadata=False,
            write_info_json=False,
            tags=[],
        )
        app.pending_jobs.append(job)
        app._enqueue_queue_preview(job)

    app._queued_preview_requests.join()

    assert completed == 12
    assert maximum_active == 1


def test_provider_coordinator_defers_preview_for_primary_intent():
    coordinator = app_module.ProviderNetworkCoordinator()
    preview_started = threading.Event()
    preview_finished = threading.Event()
    coordinator.begin_primary()

    def preview() -> None:
        coordinator.run_preview(lambda: preview_started.set())
        preview_finished.set()

    thread = threading.Thread(target=preview)
    thread.start()
    assert not preview_started.wait(timeout=0.05)

    coordinator.end_primary()
    thread.join(timeout=1)

    assert preview_started.is_set()
    assert preview_finished.is_set()


def test_abandoned_primary_operation_keeps_optional_preview_blocked():
    coordinator = app_module.ProviderNetworkCoordinator()
    primary_started = threading.Event()
    release_primary = threading.Event()
    preview_started = threading.Event()
    coordinator.begin_primary()

    def primary() -> None:
        coordinator.run_primary(
            lambda: (primary_started.set(), release_primary.wait(timeout=1))
        )

    primary_thread = threading.Thread(target=primary)
    primary_thread.start()
    assert primary_started.wait(timeout=1)
    coordinator.end_primary()

    preview_thread = threading.Thread(
        target=lambda: coordinator.run_preview(lambda: preview_started.set())
    )
    preview_thread.start()
    assert not preview_started.wait(timeout=0.05)

    release_primary.set()
    primary_thread.join(timeout=1)
    preview_thread.join(timeout=1)

    assert preview_started.is_set()


def test_delayed_abandoned_primary_runner_waits_for_active_preview():
    coordinator = app_module.ProviderNetworkCoordinator()
    release_runner = threading.Event()
    preview_started = threading.Event()
    release_preview = threading.Event()
    primary_started = threading.Event()
    coordinator.begin_primary()

    primary_thread = threading.Thread(
        target=lambda: (
            release_runner.wait(timeout=1),
            coordinator.run_primary(lambda: primary_started.set()),
        )
    )
    primary_thread.start()
    coordinator.end_primary()

    preview_thread = threading.Thread(
        target=lambda: coordinator.run_preview(
            lambda: (preview_started.set(), release_preview.wait(timeout=1))
        )
    )
    preview_thread.start()
    assert preview_started.wait(timeout=1)

    release_runner.set()
    assert not primary_started.wait(timeout=0.05)

    release_preview.set()
    preview_thread.join(timeout=1)
    primary_thread.join(timeout=1)
    assert primary_started.is_set()


def test_queued_preview_request_cap_drops_only_optional_preview(tmp_path: Path):
    app = DownloaderApp.__new__(DownloaderApp)
    requests: queue.Queue[DownloadJob] = queue.Queue(maxsize=1)
    existing = DownloadJob(
        url="https://www.youtube.com/watch?v=existing",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )
    incoming = app_module.replace(existing, url="https://www.youtube.com/watch?v=incoming")
    requests.put(existing)
    app._queued_preview_requests = requests

    class AliveWorker:
        def is_alive(self):
            return True

    app._queued_preview_thread = AliveWorker()

    app._enqueue_queue_preview(incoming)

    assert requests.qsize() == 1
    assert requests.get_nowait() is existing


def test_mp3_ytdlp_options_extract_audio_embed_cover_and_apply_producer_settings(monkeypatch, tmp_path: Path):
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    monkeypatch.setattr(DownloaderApp, "_find_ffmpeg", staticmethod(lambda: "/bundle/ffmpeg"))
    monkeypatch.setattr(DownloaderApp, "_find_deno", staticmethod(lambda: None))
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=beat",
        output_dir=tmp_path,
        output_type=OutputType.MP3,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(
            bitrate_kbps=320,
            sample_rate="44100",
            channels="2",
            embed_metadata=True,
            embed_cover_art=True,
        ),
        single_video_only=False,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=["beat", "producer"],
    )

    opts = app._build_ydl_options(job, tmp_path / "staging", format_selector="251")

    assert opts["format"] == "251"
    assert "merge_output_format" not in opts
    assert opts["writethumbnail"] is True
    assert opts["writeinfojson"] is False
    assert opts["postprocessors"] == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
        {"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True},
        {"key": "EmbedThumbnail", "already_have_thumbnail": False},
    ]
    assert opts["postprocessor_args"]["extractaudio+ffmpeg_o"] == ["-ar", "44100", "-ac", "2"]
    assert opts["postprocessor_args"]["metadata+ffmpeg_o"] == ["-metadata", "keywords=beat,producer"]


def test_mp3_ytdlp_options_leave_no_cover_or_metadata_sidecars_when_disabled(monkeypatch, tmp_path: Path):
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    monkeypatch.setattr(DownloaderApp, "_find_ffmpeg", staticmethod(lambda: "/bundle/ffmpeg"))
    monkeypatch.setattr(DownloaderApp, "_find_deno", staticmethod(lambda: None))
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=beat",
        output_dir=tmp_path,
        output_type=OutputType.MP3,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(embed_metadata=False, embed_cover_art=False),
        single_video_only=False,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=["ignored"],
    )

    opts = app._build_ydl_options(job, tmp_path / "staging", format_selector="251")

    assert opts["writethumbnail"] is False
    assert opts["postprocessors"] == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
    ]
    assert opts["postprocessor_args"] == {}


def test_mp3_ytdlp_options_do_not_fetch_youtube_art_when_custom_cover_is_selected(monkeypatch, tmp_path: Path):
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    monkeypatch.setattr(DownloaderApp, "_find_ffmpeg", staticmethod(lambda: "/bundle/ffmpeg"))
    monkeypatch.setattr(DownloaderApp, "_find_deno", staticmethod(lambda: None))
    custom_cover = tmp_path / "artist-cover.png"
    Image.new("RGB", (600, 600), "purple").save(custom_cover)
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=beat",
        output_dir=tmp_path,
        output_type=OutputType.MP3,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(
            embed_metadata=True,
            embed_cover_art=False,
            custom_cover_art_path=custom_cover,
        ),
        single_video_only=False,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )

    opts = app._build_ydl_options(job, tmp_path / "staging", format_selector="251")

    assert opts["writethumbnail"] is False
    assert not any(processor["key"] == "EmbedThumbnail" for processor in opts["postprocessors"])
    assert opts["postprocessors"][-1]["key"] == "FFmpegMetadata"


# ---------------------------------------------------------------------------
# Tests for YouTube runtime configuration and relaxed format selection
# ---------------------------------------------------------------------------


def test_apply_youtube_runtime_options_uses_deno_without_pinning_player_clients():
    opts: dict = {}
    apply_youtube_runtime_options(opts, deno_path="/bundle/deno")

    assert opts["js_runtimes"] == {"deno": {"path": "/bundle/deno"}}
    assert "remote_components" not in opts
    assert "extractor_args" not in opts


def test_apply_youtube_runtime_options_preserves_explicit_extractor_args():
    opts = {"extractor_args": {"youtube": {"player_client": ["web"]}}}
    apply_youtube_runtime_options(opts, deno_path="/bundle/deno")

    assert opts["extractor_args"]["youtube"]["player_client"] == ["web"]


def test_apply_youtube_runtime_options_without_deno_leaves_defaults_untouched():
    opts: dict = {}
    apply_youtube_runtime_options(opts, deno_path=None)

    assert opts == {}


def test_choose_best_video_format_relaxes_bitrate_requirement():
    """When no formats have bitrate metadata, still return a format instead of None."""
    formats = [
        {"format_id": "137", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "fps": 30},
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
    ]
    # No tbr/vbr/filesize on the video format — strict pass would reject it
    result = choose_best_video_format(formats, max_height=1080)
    assert result is not None
    assert result["format_id"] == "137"


def test_choose_best_video_format_relaxes_hdr_filter():
    """When only HDR formats are available, still return one instead of None."""
    formats = [
        {"format_id": "337", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 5000, "fps": 30, "dynamic_range": "HDR"},
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
    ]
    result = choose_best_video_format(formats, max_height=1080)
    assert result is not None
    assert result["format_id"] == "337"


def test_choose_best_audio_format_relaxes_bitrate_requirement():
    """When no audio formats have bitrate metadata, still return one."""
    formats = [
        {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "asr": 48000, "audio_channels": 2},
    ]
    result = choose_best_audio_format(formats)
    assert result is not None
    assert result["format_id"] == "251"


def test_build_auto_export_plan_falls_back_to_any_video_format():
    """When strict and progressive selectors fail, pick any format with a video codec."""
    # A format with weird fps (>120) and no bitrate — all strict filters reject it
    info = {
        "formats": [
            {"format_id": "999", "height": 720, "width": 1280, "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none", "fps": 240},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "asr": 48000, "audio_channels": 2},
        ]
    }
    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)
    assert plan.video_format_id == "999"
    assert plan.audio_format_id == "140"


def test_format_ytdlp_user_error_catches_video_unavailable():
    """'Video unavailable' errors should include actionable guidance."""
    error = RuntimeError("[youtube] abc123: Video unavailable")
    result = format_ytdlp_user_error(error)
    assert "marked 'for kids'" in result
    assert "Deno" in result
    assert "Original yt-dlp error" in result


def test_format_ytdlp_user_error_catches_no_video_formats():
    """'No video formats found' errors should include actionable guidance."""
    error = RuntimeError("ERROR: [youtube] abc123: No video formats found!")
    result = format_ytdlp_user_error(error)
    assert "JavaScript runtime" in result
    assert "Original yt-dlp error" in result


def test_format_ytdlp_user_error_catches_sign_in_to_confirm():
    """Bot detection errors should guide users to use cookies."""
    error = RuntimeError("Sign in to confirm you're not a bot")
    result = format_ytdlp_user_error(error)
    assert "cookies" in result.lower()
    assert "Original yt-dlp error" in result
