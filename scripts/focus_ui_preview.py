from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("VODFORGE_LEGACY_UI", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yt_downloader.app import DownloaderApp

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
            "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "desert-sunset.jpg"),
        },
        {
            "id": "created-works",
            "title": "Created for Good Works",
            "uploader": "Study Archive",
            "duration": 1284,
            "description": "Completed and available in Library.",
            "tags": ["study", "completed"],
            "vodforge_output_dir": "/Users/coop/Downloads/Created for Good Works",
            "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "rainforest-falls.jpg"),
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch a no-download VODForge visual QA state.")
    parser.add_argument("--view", choices=("forge", "library", "activity"), default="forge")
    parser.add_argument("--size", default="1180x780")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--run-actions", action="store_true")
    args = parser.parse_args()

    app = DownloaderApp()
    app.title("VODForge — UI Review")
    app.geometry(args.size)
    app.url_var.set("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    app.metadata_items = preview_metadata()
    app._render_metadata_tree(selected_index=0)

    app._focus_active_override = True
    app.focus_active_title_var.set("Good Desires vs. Bad Desires (How Do We Know the Difference?)")
    app.focus_active_detail_var.set("BibleProject")
    app.focus_active_profile_var.set("1080p Full HD  •  Auto CBR")
    app.focus_active_duration_var.set("32:47")
    app.progress_var.set(73)
    app.status_var.set("ETA 1m 26s  •  8.7 MB/s")
    app.focus_transfer_var.set("5.23 GB / 7.12 GB")
    app.cancel_button.configure(state="normal")
    app.skip_video_button.configure(state="normal")
    app.skip_url_button.configure(state="normal")
    app._focus_preview_runs = [
        {"title": "Good Desires vs. Bad Desires", "status": "73%  •  1m 26s left", "progress": 73, "kind": "active", "metadata_index": 0, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "alpine-lake.jpg")},
        {"title": "Walk in the Spirit", "status": "Next", "progress": 0, "kind": "queued", "metadata_index": 1, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "forest-river.jpg")},
        {"title": "Fruit of the Spirit", "status": "Queued", "progress": 0, "kind": "queued", "metadata_index": 2, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "desert-sunset.jpg")},
        {"title": "Created for Good Works", "status": "Completed", "progress": 100, "kind": "completed", "metadata_index": 3, "preview_thumbnail_path": str(PREVIEW_THUMBNAILS / "rainforest-falls.jpg")},
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
    )
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
    )
    def apply_preview_state() -> None:
        app.focus_active_title_var.set("Good Desires vs. Bad Desires (How Do We Know the Difference?)")
        app.focus_active_detail_var.set("BibleProject")
        app.focus_active_profile_var.set("1080p Full HD  •  Auto CBR")
        app.focus_active_duration_var.set("32:47")
        app.progress_var.set(73)
        app.status_var.set("ETA 1m 26s  •  8.7 MB/s")
        app.focus_run_status_var.set("73%  •  1m 26s left")
        app.focus_transfer_var.set("5.23 GB / 7.12 GB")
        app._set_focus_update_state("Up to date", "#35d07f")
        app._load_thumbnail_file(PREVIEW_THUMBNAILS / "alpine-lake.jpg")
        app._set_text(app.focus_log, log_lines, disabled=True)
        app._set_text(app.log, log_lines, disabled=True)
        app._set_text(app.focus_summary_text, output_lines, disabled=True)
        app._set_text(
            app.source_summary_text,
            "Format selector: 137 + 140\nVideo: H.264 / 1920x1080 / 30fps\nAudio: AAC / 128 kbps / stereo\nSource duration: 32:47",
            disabled=True,
        )
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
    app.mainloop()


if __name__ == "__main__":
    main()
