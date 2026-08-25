from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("VODFORGE_LEGACY_UI", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yt_downloader.app import DownloaderApp, OutputType

PREVIEW_THUMBNAILS = Path(__file__).resolve().parents[1] / "assets" / "preview_thumbnails"


def preview_metadata() -> list[dict[str, object]]:
    return [
        {
            "id": "dQw4w9WgXcQ",
            "title": "Good Desires vs. Bad Desires (How Do We Know the Difference?)",
            "uploader": "BibleProject",
            "duration": 1967,
            "description": "A thoughtful visual exploration of desire, wisdom, and the final commandment.",
            "tags": ["wisdom", "BibleProject", "desire", "commandments"],
            "format_id": "137+140",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "vcodec": "avc1.640028",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "alpine-lake.jpg"),
        },
        {
            "id": "walk-spirit",
            "title": "Walk in the Spirit",
            "uploader": "Study Archive",
            "duration": 1422,
            "description": "Queued for the same VOD-ready output profile.",
            "tags": ["study", "archive"],
            "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "forest-river.jpg"),
        },
        {
            "id": "fruit-spirit",
            "title": "Fruit of the Spirit",
            "uploader": "Study Archive",
            "duration": 1108,
            "description": "Waiting in the run deck.",
            "tags": ["study", "playlist"],
            "vodforge_output_type": "MP3",
            "vodforge_encoding_summary": {
                "source": {
                    "Source format selector used": "251",
                    "Audio format ID": "251",
                    "Source container/ext": "webm",
                    "Source audio codec": "opus",
                    "Source audio bitrate": "160 kbps",
                    "Source audio sample rate": "48000",
                    "Source audio channels": "2",
                    "Effective MP3-equivalent audio bitrate": "208 kbps",
                    "Reason selected": "highest-quality available audio-only source",
                },
                "output": {
                    "Output file path": "/Users/coop/Downloads/Fruit of the Spirit.mp3",
                    "Output container": "mp3",
                    "Output audio codec": "MP3 (libmp3lame)",
                    "Target audio bitrate": "320 kbps",
                    "Measured audio bitrate": "320 kbps",
                    "Audio sample rate": "48000",
                    "Audio channels": "2",
                    "Output rate-control mode": "CBR",
                    "Embedded ID3 metadata": "Yes",
                    "Embedded cover art": "None (clean MP3)",
                    "Validation status": "Validated",
                },
                "warnings": [],
            },
            "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "desert-sunset.jpg"),
        },
        {
            "id": "created-works",
            "title": "Created for Good Works",
            "uploader": "Study Archive",
            "duration": 1284,
            "description": "Completed and available in Library.",
            "tags": ["study", "completed"],
            "vodforge_output_type": "MP3",
            "vodforge_output_dir": "/Users/coop/Downloads/Created for Good Works",
            "vodforge_encoding_summary": {
                "source": {
                    "Source format selector used": "251",
                    "Audio format ID": "251",
                    "Source container/ext": "webm",
                    "Source audio codec": "opus",
                    "Source audio bitrate": "160 kbps",
                    "Source audio sample rate": "48000",
                    "Source audio channels": "2",
                    "Effective MP3-equivalent audio bitrate": "208 kbps",
                    "Reason selected": "highest-quality available audio-only source",
                },
                "output": {
                    "Output file path": "/Users/coop/Downloads/Created for Good Works/Created for Good Works.mp3",
                    "Output container": "mp3",
                    "Output audio codec": "MP3 (libmp3lame)",
                    "Target audio bitrate": "320 kbps",
                    "Measured audio bitrate": "320 kbps",
                    "Audio sample rate": "48000",
                    "Audio channels": "2",
                    "Output rate-control mode": "CBR",
                    "Embedded ID3 metadata": "Yes",
                    "Embedded cover art": "Custom image",
                    "Validation status": "Validated",
                },
                "warnings": [],
            },
            "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "rainforest-falls.jpg"),
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch a no-download VODForge visual QA state.")
    parser.add_argument("--view", choices=("forge", "library", "activity"), default="forge")
    parser.add_argument("--size", default="1180x780")
    parser.add_argument("--output-type", choices=("MP4", "MP3"), default="MP4")
    parser.add_argument("--cover-mode", choices=("Clean MP3", "YouTube art", "Custom art"), default="Clean MP3")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--run-actions", action="store_true")
    parser.add_argument("--overflow", action="store_true")
    parser.add_argument("--copy-feedback", choices=("tags", "description", "thumbnail"))
    args = parser.parse_args()

    app = DownloaderApp()
    app.title("VODForge — UI Review")
    app.geometry(args.size)
    output_type = OutputType(args.output_type)
    if args.cover_mode == "Custom art":
        custom_art = PREVIEW_THUMBNAILS / "rainforest-falls.jpg"
        app.mp3_custom_cover_art_path = custom_art
        app.mp3_custom_cover_art_var.set(custom_art.name)
    app.output_type_var.set(output_type.value)
    app.library_output_type_var.set(output_type.value)
    app.mp3_cover_art_mode_var.set(args.cover_mode)
    app.url_var.set("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    app.metadata_items = preview_metadata()
    if args.overflow:
        seed_items = list(app.metadata_items)
        for index in range(4, 32):
            seed = dict(seed_items[index % len(seed_items)])
            seed["id"] = f"visual-qa-{index + 1:03d}"
            seed["title"] = f"{seed['title']} — Visual QA {index + 1:02d}"
            app.metadata_items.append(seed)
    selected_index = 0 if output_type == OutputType.MP4 else 2
    app._render_metadata_tree(selected_index=selected_index)

    app._focus_active_override = True
    app.focus_active_title_var.set("Good Desires vs. Bad Desires (How Do We Know the Difference?)")
    app.focus_active_detail_var.set("BibleProject")
    app.focus_active_profile_var.set("1080p Full HD  •  Auto CBR" if output_type == OutputType.MP4 else "MP3  •  320 kbps  •  Source rate")
    app.focus_active_duration_var.set("32:47")
    app.progress_var.set(73)
    app.status_var.set("ETA 1m 26s  •  8.7 MB/s")
    app.focus_transfer_var.set("5.23 GB / 7.12 GB" if output_type == OutputType.MP4 else "83.4 MB / 114.2 MB")
    app.cancel_button.configure(state="normal")
    app.skip_video_button.configure(state="normal")
    app.skip_url_button.configure(state="normal")
    app._focus_preview_runs = [
        {"title": "Good Desires vs. Bad Desires", "status": f"73%  •  1m 26s left  •  {output_type.value}", "progress": 73, "kind": "active", "metadata_index": selected_index, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "alpine-lake.jpg")},
        {"title": "Walk in the Spirit", "status": "Next  •  MP4", "progress": 0, "kind": "queued", "metadata_index": 1, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "forest-river.jpg")},
        {"title": "Fruit of the Spirit", "status": "Queued  •  MP3", "progress": 0, "kind": "queued", "metadata_index": 2, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "desert-sunset.jpg")},
        {"title": "Created for Good Works", "status": "Completed  •  MP3", "progress": 100, "kind": "completed", "metadata_index": 3, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "rainforest-falls.jpg")},
    ]
    log_lines = "\n".join(
        (
            "14:28:17   [info]      Starting download",
            "14:28:18   [info]      Fetching video information",
            "14:28:19   [info]      Retrieving formats",
            "14:28:20   [info]      Selected format: 1080p (137)",
            "14:28:23   [download]  5.23 GB of 7.12 GB (73.4%) at 8.7 MB/s",
            "14:28:24   [info]      Converting to MP4 (H.264 + AAC)",
            "14:28:25   [info]      Writing output file",
            "14:28:25   [info]      Processing…",
        )
        if output_type == OutputType.MP4
        else (
            "14:28:17   [info]      Starting MP3 audio run",
            "14:28:18   [info]      Fetching video information",
            "14:28:19   [info]      Retrieving audio formats",
            "14:28:20   [info]      Selected best audio: Opus (251)",
            "14:28:23   [download]  83.4 MB of 114.2 MB (73.0%)",
            "14:28:24   [info]      Encoding MP3 at 320 kbps CBR",
            f"14:28:25   [info]      Cover art: {args.cover_mode}",
            "14:28:25   [info]      Validating final audio file…",
        )
    )
    if args.overflow:
        log_lines = "\n".join(f"{line}  /  pass {pass_index + 1}" for pass_index in range(8) for line in log_lines.splitlines())
    output_lines = "\n".join(
        (
            "Format        MP4",
            "Video         H.264  /  1920x1080  /  30fps",
            "Audio         AAC  /  128 kbps  /  stereo",
            "Output mode   Auto CBR",
            "File size     7.12 GB estimated",
            "Save to       /Users/coop/Downloads",
            "Status        Downloading",
        )
        if output_type == OutputType.MP4
        else (
            "Format        MP3",
            "Source        Opus  /  160 kbps  /  48 kHz",
            "Output        MP3  /  320 kbps CBR",
            "Sample rate   Preserve source",
            "Cover art     " + args.cover_mode,
            "Save to       /Users/coop/Downloads",
            "Status        Downloading",
        )
    )
    def apply_preview_state() -> None:
        app.url_var.set("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        app.focus_active_title_var.set("Good Desires vs. Bad Desires (How Do We Know the Difference?)")
        app.focus_active_detail_var.set("BibleProject")
        app.focus_active_profile_var.set("1080p Full HD  •  Auto CBR" if output_type == OutputType.MP4 else "MP3  •  320 kbps  •  Source rate")
        app.focus_active_duration_var.set("32:47")
        app.progress_var.set(73)
        app.status_var.set("ETA 1m 26s  •  8.7 MB/s")
        app.focus_run_status_var.set("73%  •  1m 26s left")
        app.focus_transfer_var.set("5.23 GB / 7.12 GB" if output_type == OutputType.MP4 else "83.4 MB / 114.2 MB")
        app._set_focus_update_state("Up to date", "#35d07f")
        active_art = (
            PREVIEW_THUMBNAILS / "rainforest-falls.jpg"
            if output_type == OutputType.MP3 and args.cover_mode == "Custom art"
            else PREVIEW_THUMBNAILS / "alpine-lake.jpg"
        )
        app._load_thumbnail_file(active_art)
        app._set_text(app.focus_log, log_lines, disabled=True)
        app._set_text(app.log, log_lines, disabled=True)
        app._set_text(app.focus_summary_text, output_lines, disabled=True)
        source_lines = (
            "Format selector: 137 + 140\nVideo: H.264 / 1920x1080 / 30fps\nAudio: AAC / 128 kbps / stereo\nSource duration: 32:47"
            if output_type == OutputType.MP4
            else "Format selector: 251\nAudio: Opus / 160 kbps / stereo\nSample rate: 48 kHz\nReason selected: highest-quality available audio source"
        )
        app._set_text(app.source_summary_text, source_lines, disabled=True)
        app._set_text(app.output_summary_text, output_lines, disabled=True)
        app._set_focus_run_controls_visible(True)
        app._select_focus_view(args.view)
        app._apply_focus_layout(force=True)
        app._refresh_focus_run_deck()

    apply_preview_state()
    app.after(450, apply_preview_state)
    if args.settings:
        app.after(300, app._show_focus_settings)
    if args.run_actions:
        app.after(
            700,
            lambda: app._show_focus_run_actions_menu(
                app._focus_preview_runs[-1],
                SimpleNamespace(x_root=840, y_root=560),
            ),
        )
    if args.copy_feedback:
        app.after(1200, lambda: app._show_copy_feedback(args.copy_feedback))
    app.mainloop()


if __name__ == "__main__":
    main()
