import json
import queue
import threading
import time
from io import BytesIO
from pathlib import Path

import pytest

import yt_downloader.app as app_module
from yt_downloader.app import (
    RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS,
    AUDIO_BITRATE,
    AUDIO_SAMPLE_RATE,
    DownloadJob,
    DownloaderApp,
    ExportMode,
    QUALITY_OPTIONS,
    VIDEO_TARGET_BITRATE,
    ManualExportSettings,
    apply_manual_export_settings,
    build_auto_export_plan,
    build_encoding_summary_display,
    build_encoding_summary_metadata,
    build_failed_encoding_summary_metadata,
    build_description_display_text,
    clean_single_video_url,
    single_video_url_requires_video_id_error,
    build_tags_display_text,
    build_vod_ffmpeg_command,
    choose_audio_bitrate_kbps,
    choose_best_audio_format,
    choose_best_video_format,
    choose_windows_output_directory,
    cleanup_legacy_encode_sidecars,
    compact_video_metadata,
    run_cancellable_blocking_step,
    format_duration,
    iter_video_infos,
    package_downloaded_media_from_staging,
    append_batch_failure_report,
    apply_ytdlp_cookie_options,
    best_thumbnail_for_download,
    format_ytdlp_user_error,
    parse_url_list_text,
    diagnostics_dir,
    bounded_window_size,
    download_layout_mode,
    bundled_asset_path,
    configure_windows_app_identity,
    metadata_layout_mode,
    platform_font_families,
    prepare_batch_item_url,
    playlist_folder_name,
    run_ffprobe_json,
    runtime_version_command,
    save_thumbnail_image,
    staging_output_template,
    transcode_temp_paths,
    transcode_to_vod_streaming_settings,
    runtime_executable_candidates,
    video_list_row_values,
    video_file_name,
    video_output_dir,
    ytdlp_ffmpeg_location,
    write_compact_video_metadata,
)


def test_platform_diagnostics_paths_follow_native_conventions(tmp_path: Path):
    assert diagnostics_dir(platform_name="darwin", home=tmp_path) == tmp_path / "Library" / "Logs" / "VODForge"
    assert diagnostics_dir(platform_name="linux", home=tmp_path) == tmp_path / ".vodforge" / "logs"
    assert diagnostics_dir(platform_name="win32", home=tmp_path, local_app_data="C:/Users/Test/AppData/Local") == (
        Path("C:/Users/Test/AppData/Local") / "VODForge" / "logs"
    )


def test_platform_fonts_use_macos_and_windows_system_families():
    assert platform_font_families("darwin") == ("Helvetica Neue", "Menlo")
    assert platform_font_families("win32") == ("Segoe UI", "Cascadia Mono")
    assert platform_font_families("linux") == ("TkDefaultFont", "TkFixedFont")


def test_initial_window_size_leaves_room_for_screen_chrome():
    assert bounded_window_size(1920, 1080) == (1180, 900)
    assert bounded_window_size(1366, 768) == (1180, 648)
    assert bounded_window_size(1280, 720) == (1180, 600)
    assert bounded_window_size(800, 600) == (776, 552)


def test_download_layout_uses_inline_details_whenever_they_fit():
    assert download_layout_mode(1120, 480) == "wide-expanded"
    assert download_layout_mode(1120, 430) == "wide-expanded"
    assert download_layout_mode(1120, 380) == "wide-compact"
    assert download_layout_mode(900, 700) == "stacked-expanded"
    assert download_layout_mode(900, 560) == "stacked-compact"


def test_manual_override_requires_room_for_all_inline_fields():
    assert download_layout_mode(1120, 560, manual_override=True) == "wide-compact"
    assert download_layout_mode(1120, 600, manual_override=True) == "wide-expanded"
    assert download_layout_mode(900, 760, manual_override=True) == "stacked-compact"
    assert download_layout_mode(900, 840, manual_override=True) == "stacked-expanded"


def test_metadata_layout_keeps_all_surfaces_visible_at_each_width():
    assert metadata_layout_mode(1120) == "three-column"
    assert metadata_layout_mode(700) == "three-column"
    assert metadata_layout_mode(699) == "two-column"


def test_bundled_asset_path_uses_packaged_or_source_asset_root(tmp_path: Path):
    assert bundled_asset_path("VODForge.ico", meipass=tmp_path) == tmp_path / "assets" / "VODForge.ico"
    assert bundled_asset_path("VODForge.png", meipass=None, repo_root=tmp_path) == tmp_path / "assets" / "VODForge.png"


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


def test_single_video_toggle_blocks_playlist_url_without_video_id():
    url = "https://www.youtube.com/playlist?list=PL"

    assert clean_single_video_url(url) == url
    assert single_video_url_requires_video_id_error(url) == (
        "This is a playlist URL. Turn off Single video only to process the whole playlist."
    )


def test_single_video_toggle_allows_watch_and_short_urls_with_video_id():
    assert single_video_url_requires_video_id_error("https://www.youtube.com/watch?list=PL&v=abc&t=30s") is None
    assert single_video_url_requires_video_id_error("https://youtu.be/abc?list=PL&t=30s") is None


def test_batch_watch_urls_with_playlist_context_are_processed_as_single_videos():
    url = "https://www.youtube.com/watch?v=abc123&list=PLmix&index=12&t=30s"

    cleaned_url, single_video_only = prepare_batch_item_url(url)

    assert cleaned_url == "https://www.youtube.com/watch?v=abc123&t=30s"
    assert single_video_only is True


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


def test_staging_output_template_never_targets_real_final_folders(tmp_path: Path):
    template = staging_output_template(tmp_path)

    assert "Single Videos" not in template
    assert "%(playlist_title" not in template
    assert "%(title)" not in template
    assert "video [%(id)s].%(ext)s" in template


def test_save_thumbnail_image_writes_single_thumbnail_jpeg(monkeypatch, tmp_path: Path):
    Image = pytest.importorskip("PIL.Image")
    buf = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="WEBP")
    payload = buf.getvalue()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return payload

    monkeypatch.setattr("yt_downloader.app.urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    path = save_thumbnail_image(tmp_path, {"thumbnail": "https://i.ytimg.com/example.webp"})

    assert path == tmp_path / "thumbnail.jpeg"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["thumbnail.jpeg"]
    with Image.open(path) as image:
        assert image.format == "JPEG"


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
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return payload

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


def test_auto_source_selection_prefers_true_1080p_h264_when_effective_quality_wins():
    formats = [
        {"format_id": "137", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "tbr": 1517, "fps": 30},
        {"format_id": "248", "height": 1080, "width": 1920, "ext": "webm", "vcodec": "vp9", "acodec": "none", "tbr": 754, "fps": 30},
        {"format_id": "399", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "av01.0.08M.08", "acodec": "none", "tbr": 583, "fps": 30},
    ]

    selected = choose_best_video_format(formats, max_height=1080)

    assert selected is not None
    assert selected["format_id"] == "137"


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
    source_labels = [line.split(":", 1)[0] for line in source_two.splitlines()]
    output_labels = [line.split(":", 1)[0] for line in output_two.splitlines()]
    assert source_labels[:10] == output_labels[:10]


def test_failed_video_encoding_summary_preserves_source_and_no_output_reason():
    info = _summary_test_info()
    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR, max_height=1080)

    failed = build_failed_encoding_summary_metadata(info, plan, "yt-dlp failed")
    source_text, output_text = build_encoding_summary_display(failed)

    assert "Format selector: 137+251" in source_text
    assert "Format selector: Not applicable" in output_text
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
        ManualExportSettings(video_bitrate_kbps=15000, audio_bitrate_kbps=256, audio_sample_rate="44100", audio_channels="1", x264_preset="fast"),
    )

    assert manual.format_selector == "137+140"
    assert manual.video_format_id == "137"
    assert manual.audio_format_id == "140"
    assert manual.video_bitrate_kbps == 15000
    assert manual.audio_bitrate_kbps == 256
    assert manual.audio_sample_rate == "44100"
    assert manual.audio_channels == "1"
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


def test_cookiefile_option_is_only_added_when_user_enabled_cookies(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    enabled = apply_ytdlp_cookie_options({}, use_cookies=True, cookie_file=cookies)
    disabled = apply_ytdlp_cookie_options({}, use_cookies=False, cookie_file=cookies)

    assert enabled["cookiefile"] == str(cookies)
    assert "cookiefile" not in disabled


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


def test_transcode_accepts_valid_complete_output_when_ffmpeg_returns_nonzero_near_end(monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("yt_downloader.app._ffprobe_for_ffmpeg", lambda _ffmpeg: "ffprobe")
    monkeypatch.setattr(
        "yt_downloader.app.run_ffprobe_json",
        lambda _ffprobe, _path: {"format": {"duration": "10.0"}, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]},
    )

    result = transcode_to_vod_streaming_settings(source, "ffmpeg", duration_seconds=10.0, use_nvenc=True)

    assert result == source
    assert source.read_bytes() == b"complete encoded output"
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

    app._download_worker_single = fake_single
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=ok1",
        urls=["https://www.youtube.com/watch?v=ok1", "https://www.youtube.com/watch?v=bad", "https://www.youtube.com/watch?v=ok2"],
        output_dir=tmp_path,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
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
    done_messages = [payload for kind, payload in list(app.events.queue) if kind == "done"]
    assert any("1 failed" in str(message) for message in done_messages)


# ---------------------------------------------------------------------------
# Tests for multi-client extractor args and relaxed format selection
# ---------------------------------------------------------------------------


def test_apply_youtube_extractor_args_sets_player_client():
    """VODForge should configure yt-dlp to try multiple YouTube player clients.

    yt-dlp 2026.x expects player_client as a *list*, not a comma-separated
    string.  A string gets iterated character-by-character, silently skipping
    every "unsupported client" and falling back to defaults that fail on some
    videos.
    """
    from yt_downloader.app import apply_youtube_extractor_args

    opts: dict = {}
    apply_youtube_extractor_args(opts)
    assert "extractor_args" in opts
    youtube_args = opts["extractor_args"]["youtube"]
    assert "player_client" in youtube_args
    clients = youtube_args["player_client"]
    # Must be a list, not a comma-separated string
    assert isinstance(clients, list), f"player_client must be a list, got {type(clients)}"
    # Must include 'android' (works without JS runtime) and at least one web client
    assert "android" in clients
    assert any(c.startswith("web") for c in clients), f"Expected a web client in {clients}"


def test_apply_youtube_extractor_args_preserves_existing_player_client():
    """If caller already set player_client, don't overwrite it."""
    from yt_downloader.app import apply_youtube_extractor_args

    opts = {"extractor_args": {"youtube": {"player_client": ["web"]}}}
    apply_youtube_extractor_args(opts)
    assert opts["extractor_args"]["youtube"]["player_client"] == ["web"]


def test_player_client_list_not_string_to_prevent_char_splitting():
    """Regression: player_client must be a list, not a comma-separated string.

    yt-dlp 2026.x iterates player_client as a list of client names. If a
    string like "default,android" is passed, yt-dlp iterates over individual
    characters ("d","e","f",...) and silently skips every "unsupported
    client", causing intermittent video download failures.
    """
    from yt_downloader.app import apply_youtube_extractor_args

    opts: dict = {}
    apply_youtube_extractor_args(opts)
    clients = opts["extractor_args"]["youtube"]["player_client"]
    assert isinstance(clients, list)
    # No element should be a single character or comma
    for c in clients:
        assert len(c) > 1, f"Client name '{c}' looks like a split character"
        assert "," not in c, f"Client name '{c}' contains a comma"


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
